"""Orquestacion del ETL: extraccion, transformacion, anonimizacion y volcado.

Escenarios que construye
------------------------
========================  ===========================  ==================
Escenario                 Origen                       Naturaleza
========================  ===========================  ==================
Real 2025                 hoja `Data 2025`             observado
Presupuesto 2025          libro `Presupuesto 2025`     observado
Presupuesto 2026          hoja `BD_PPTO26`             observado
Real 2026 (simulado)      generado                     sintetico
========================  ===========================  ==================

Eso habilita las tres comparaciones del reporte: ejecucion presupuestaria de
2025, ejecucion de 2026 hasta octubre, y variacion interanual del real.

Reconciliacion
--------------
Cada escenario observado se reconcilia contra su banda en la maqueta de Control
de Gestion, dos veces: antes de anonimizar, contra las cifras originales, y
despues, contra esas mismas cifras escaladas por el factor. La primera
demuestra que la transformacion no altera el resultado; la segunda, que la
anonimizacion tampoco. Si alguna falla, no se escribe nada.

El escenario simulado no se reconcilia -- no hay cifra oficial contra la que
hacerlo -- y pasa en su lugar por los controles de verosimilitud de
`simulate.validacion`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from .anonymize.mapper import Pseudonimizador
from .anonymize.scaler import comprobar_invariantes, escalar_importes
from .config import ConfigEtl
from .extract.extractor import extraer_detalle, extraer_presupuesto
from .extract.maqueta import extraer_control_mensual
from .logging_setup import logger
from .quality import checks as qc
from .simulate import validacion as sv
from .simulate.escenario import simular_real
from .transform.clean import anadir_claves_tiempo, aplicar_tipos
from .transform.model import (
    TIPO_PRESUPUESTO,
    TIPO_REAL,
    Escenario,
    construir_dim_centro,
    construir_dim_cuenta,
    construir_dim_escenario,
    construir_dim_tiempo,
    construir_fact_escenario,
    construir_hechos_real,
    optimizar_dtypes,
)
from .transform.schema import COLUMNAS_REAL, Sensibilidad, por_sensibilidad

log = logger("pipeline")

#: Clave del escenario real observado, que es el eje de todo lo demas.
CLAVE_REAL_OBSERVADO = "R2025"


@dataclass(slots=True)
class SalidaEtl:
    """Tablas del modelo analitico y el informe de calidad que las avala."""

    dim_tiempo: pd.DataFrame
    dim_centro: pd.DataFrame
    dim_cuenta: pd.DataFrame
    dim_escenario: pd.DataFrame
    fact_escenario: pd.DataFrame
    fact_resultado: pd.DataFrame
    #: Cifra oficial de ingresos por escenario y periodo, ya escalada por el
    #: factor de anonimizacion. No es una tabla del modelo: es el patron contra
    #: el que la capa SQL vuelve a reconciliar sin depender del libro Excel.
    control_reconciliacion: pd.DataFrame
    calidad: qc.ResultadoCalidad = field(default_factory=qc.ResultadoCalidad)

    def tablas(self) -> dict[str, pd.DataFrame]:
        return {
            "dim_tiempo": self.dim_tiempo,
            "dim_centro": self.dim_centro,
            "dim_cuenta": self.dim_cuenta,
            "dim_escenario": self.dim_escenario,
            "fact_escenario": self.fact_escenario,
            "fact_resultado": self.fact_resultado,
        }

    def artefactos(self) -> dict[str, pd.DataFrame]:
        """Salidas que no forman parte del estrella pero se publican con el.

        Viven en la misma carpeta, y pasan por la misma auditoria de fugas,
        porque son parte del contrato con la capa siguiente: sin la cifra
        oficial, PostgreSQL solo podria comprobar que cuadra consigo mismo.
        """
        return {"control_reconciliacion": self.control_reconciliacion}

    def escribir_parquet(self, destino: Path) -> None:
        destino.mkdir(parents=True, exist_ok=True)
        for nombre, df in {**self.tablas(), **self.artefactos()}.items():
            ruta = destino / f"{nombre}.parquet"
            df.to_parquet(ruta, index=False, compression="zstd")
            log.info(
                "%-18s -> %-26s %9s filas %8.2f MB",
                nombre, ruta.name, f"{len(df):,}", ruta.stat().st_size / 1024**2,
            )


def ejecutar(cfg: ConfigEtl, *, anonimizar: bool = True) -> SalidaEtl:
    resultado = qc.ResultadoCalidad()
    libro = cfg.rutas.libro_origen

    # -- 1. Extraccion -------------------------------------------------------
    crudo = extraer_detalle(libro, cfg.hoja_real, primera_fila=cfg.primera_fila_real)

    presupuestos: dict[int, pd.DataFrame] = {}
    controles: dict[str, pd.Series] = {}
    for fuente in cfg.presupuestos:
        presupuestos[fuente.ejercicio] = extraer_presupuesto(
            fuente.resolver_libro(libro),
            fuente.hoja,
            ejercicio=fuente.ejercicio,
            primera_fila=fuente.primera_fila,
        )
        controles[f"P{fuente.ejercicio}"] = extraer_control_mensual(
            libro, cfg.hoja_maqueta, fuente.banda_control,
            fila_metrica=cfg.fila_ingresos_maqueta,
            nombre=f"ingresos_maqueta_P{fuente.ejercicio}",
        )
    controles[CLAVE_REAL_OBSERVADO] = extraer_control_mensual(
        libro, cfg.hoja_maqueta, cfg.banda_real,
        fila_metrica=cfg.fila_ingresos_maqueta, nombre="ingresos_maqueta_real",
    )

    # -- 2. Tipado y claves --------------------------------------------------
    real = anadir_claves_tiempo(aplicar_tipos(crudo, COLUMNAS_REAL))
    del crudo
    presupuestos = {e: anadir_claves_tiempo(df) for e, df in presupuestos.items()}
    ejercicio_real = int(real["ejercicio"].iloc[0])

    log.info("importe total del detalle real: %s", f"{float(real['importe'].sum()):,.2f}")

    # -- 3. Controles sobre las cifras originales ----------------------------
    qc.validar_contrato(real, tuple(c.destino for c in COLUMNAS_REAL), resultado)
    qc.validar_dominios(real, ejercicios={ejercicio_real}, resultado=resultado)
    qc.validar_marca_reverso(real, resultado)
    qc.reconciliar_contra_maqueta(
        real, controles[CLAVE_REAL_OBSERVADO], resultado,
        nombre="Reconciliacion Real 2025 (cifras originales)",
    )
    qc.validar_dimension_consistente(real, "ceco_codigo", "ceco_nombre", resultado)
    qc.validar_dimension_consistente(real, "cuenta_codigo", "grupo", resultado)
    resultado.exigir_aprobacion()

    # -- 4. Anonimizacion ----------------------------------------------------
    if anonimizar:
        if cfg.anonimizacion is None:
            raise RuntimeError("se pidio anonimizar sin configuracion de anonimizacion")
        real, presupuestos, controles = _anonimizar(
            real, presupuestos, controles, cfg, resultado
        )

    # -- 5. Dimensiones ------------------------------------------------------
    dim_centro = construir_dim_centro(real, *presupuestos.values())
    dim_cuenta = construir_dim_cuenta(real, *presupuestos.values())

    # -- 6. Escenario simulado ----------------------------------------------
    sim = cfg.simulacion
    simulacion = simular_real(
        real,
        presupuestos[sim.ejercicio],
        dim_cuenta,
        ejercicio=sim.ejercicio,
        ultimo_periodo=sim.ultimo_periodo,
        semilla=sim.semilla,
        persistencia=sim.persistencia,
        intensidad_residuo=sim.intensidad_residuo,
        convergencia_presupuesto=sim.convergencia_presupuesto,
    )
    simulado = anadir_claves_tiempo(simulacion.hechos)
    sv.validar_todo(
        real, simulado, controles[f"P{sim.ejercicio}"], dim_cuenta, resultado
    )
    resultado.agregar(
        qc.Control(
            nombre="El escenario simulado queda marcado como tal",
            aprobado=True,
            severidad=qc.Severidad.BLOQUEANTE,
            detalle=(
                f"Real {sim.ejercicio} generado para los periodos 1-{sim.ultimo_periodo} "
                f"desde {simulacion.series_generadas:,} series del real "
                f"(semilla {sim.semilla}); marcado con es_simulado en dim_escenario"
            ),
            metricas={
                "series_generadas": float(simulacion.series_generadas),
                "series_omitidas": float(simulacion.series_omitidas),
                "semilla": float(sim.semilla),
            },
        )
    )

    # -- 7. Modelo estrella --------------------------------------------------
    escenarios = [
        Escenario(CLAVE_REAL_OBSERVADO, TIPO_REAL, ejercicio_real),
        *(
            Escenario(f"P{e}", TIPO_PRESUPUESTO, e)
            for e in sorted(presupuestos)
        ),
        Escenario(
            f"R{sim.ejercicio}", TIPO_REAL, sim.ejercicio,
            es_simulado=True, periodos=sim.ultimo_periodo,
        ),
    ]
    dim_escenario = construir_dim_escenario(escenarios)

    partes = {CLAVE_REAL_OBSERVADO: real}
    partes.update({f"P{e}": df for e, df in sorted(presupuestos.items())})
    partes[f"R{sim.ejercicio}"] = simulado
    fact_escenario = construir_fact_escenario(partes)
    fact_resultado = construir_hechos_real(real, CLAVE_REAL_OBSERVADO)

    dim_tiempo = construir_dim_tiempo(
        fact_escenario[["fecha_clave", "ejercicio", "periodo"]]
    )

    # -- 8. Controles sobre el modelo ----------------------------------------
    qc.validar_orden_pl(dim_cuenta, resultado)
    qc.validar_suma_invariante(
        float(real["importe"].sum()),
        float(fact_resultado["importe"].sum()),
        "construccion del detalle",
        resultado,
    )
    qc.validar_coherencia_entre_hechos(
        fact_escenario, fact_resultado, CLAVE_REAL_OBSERVADO, resultado
    )
    qc.validar_cuadre_agregados(
        fact_escenario,
        {"dim_centro": dim_centro, "dim_cuenta": dim_cuenta},
        resultado,
    )
    qc.validar_escenarios_declarados(fact_escenario, dim_escenario, resultado)

    for clave, control in sorted(controles.items()):
        qc.reconciliar_contra_maqueta(
            fact_escenario[fact_escenario["escenario_clave"] == clave],
            control, resultado,
            nombre=f"Reconciliacion {clave} (modelo final)",
            dim_cuenta=dim_cuenta,
        )
    resultado.exigir_aprobacion()

    return SalidaEtl(
        dim_tiempo=dim_tiempo,
        dim_centro=optimizar_dtypes(dim_centro),
        dim_cuenta=optimizar_dtypes(dim_cuenta),
        dim_escenario=dim_escenario,
        fact_escenario=optimizar_dtypes(fact_escenario),
        fact_resultado=optimizar_dtypes(fact_resultado),
        control_reconciliacion=_tabla_reconciliacion(controles),
        calidad=resultado,
    )


def _tabla_reconciliacion(controles: dict[str, pd.Series]) -> pd.DataFrame:
    """Aplana los patrones mensuales de la maqueta en una tabla publicable.

    Solo los escenarios observados tienen cifra oficial contra la que cuadrar.
    El simulado no aparece aqui, y esa ausencia es informacion: no hay nada
    contra lo que reconciliarlo, que es muy distinto de reconciliarlo contra
    cero. La capa SQL hereda esa distincion al declarar la tabla con clave
    primaria propia en vez de una columna por escenario.
    """
    filas = [
        {
            "escenario_clave": clave,
            "periodo": int(periodo),
            "ingresos_oficiales": round(float(importe), 2),
        }
        for clave, serie in sorted(controles.items())
        for periodo, importe in serie.items()
    ]
    tabla = pd.DataFrame(
        filas, columns=["escenario_clave", "periodo", "ingresos_oficiales"]
    )
    log.info(
        "control_reconciliacion: %d periodos en %d escenarios observados",
        len(tabla),
        tabla["escenario_clave"].nunique(),
    )
    return tabla


def _anonimizar(
    real: pd.DataFrame,
    presupuestos: dict[int, pd.DataFrame],
    controles: dict[str, pd.Series],
    cfg: ConfigEtl,
    resultado: qc.ResultadoCalidad,
) -> tuple[pd.DataFrame, dict[int, pd.DataFrame], dict[str, pd.Series]]:
    """Aplica la capa de anonimizacion a todas las tablas de forma coherente.

    Los centros de coste se pseudonimizan sobre el universo combinado de todas
    las fuentes: si se hiciera fuente por fuente, un mismo centro recibiria
    pseudonimos distintos y los escenarios dejarian de poder compararse.
    """
    anon = cfg.anonimizacion
    assert anon is not None
    pseudo = Pseudonimizador(anon.salt)
    tablas = [real, *presupuestos.values()]

    def universo(columna: str) -> pd.Series:
        return pd.concat(
            [df[columna] for df in tablas if columna in df.columns], ignore_index=True
        ).dropna()

    pseudo.codigos(universo("ceco_codigo"), dominio="ceco", prefijo="CC")
    for df in tablas:
        df["ceco_codigo"] = df["ceco_codigo"].map(pseudo.mapas["ceco"]).astype("string")

    pseudo.nombres_centro(universo("ceco_nombre"))
    for df in tablas:
        if "ceco_nombre" in df.columns:
            df["ceco_nombre"] = (
                df["ceco_nombre"].map(pseudo.mapas["ceco_nombre"]).astype("string")
            )

    pseudo.codigos(real["ceco_origen_codigo"], dominio="ceco_origen", prefijo="CO")
    real["ceco_origen_codigo"] = (
        real["ceco_origen_codigo"].map(pseudo.mapas["ceco_origen"]).astype("string")
    )

    pseudo.documentos(real["documento_id"])
    real["documento_id"] = real["documento_id"].map(pseudo.mapas["documento"]).astype("string")

    # La taxonomia interna esta repartida entre tres columnas y varias tablas.
    # Se generaliza con un unico mapa compartido para que un mismo literal no
    # quede pseudonimizado en una columna y en claro en otra.
    columnas_taxonomia = ("unidad_negocio", "ambito", "estructura")
    mapa_taxonomia = pseudo.generalizar_taxonomia(
        *(df[c] for df in tablas for c in columnas_taxonomia if c in df.columns)
    )
    for df in tablas:
        for columna in columnas_taxonomia:
            if columna in df.columns:
                df[columna] = df[columna].map(mapa_taxonomia).astype("string")

    pseudo.verificar_inyectividad()

    # Importes: factor global sobre todas las tablas y sobre los patrones.
    original = real["importe"].copy()
    real["importe"] = escalar_importes(real["importe"], anon.factor_importe)
    for df in presupuestos.values():
        df["importe"] = escalar_importes(df["importe"], anon.factor_importe)
    metricas = comprobar_invariantes(original, real["importe"], anon.factor_importe)
    resultado.agregar(
        qc.Control(
            nombre="Escalado proporcional de importes",
            aprobado=True,
            severidad=qc.Severidad.BLOQUEANTE,
            detalle=(
                f"factor {anon.factor_importe}; desvio maximo por apunte "
                f"{metricas['desvio_maximo_por_apunte']:.6f}; desvio agregado "
                f"{metricas['desvio_agregado']:,.2f} sobre una cota de "
                f"{metricas['cota_error_agregado']:,.2f}"
            ),
            metricas=metricas,
        )
    )

    # El mapa de reversion se guarda fuera del repositorio.
    mapa = pseudo.mapa_reversion()
    ruta_mapa = cfg.rutas.procesado / "_mapa_reversion.csv"
    mapa.to_csv(ruta_mapa, index=False, encoding="utf-8")
    log.warning(
        "mapa de reversion con %s entradas en %s (excluido del repositorio)",
        f"{len(mapa):,}", ruta_mapa,
    )

    for columna in por_sensibilidad(COLUMNAS_REAL, Sensibilidad.PSEUDONIMO):
        if columna in real.columns:
            resultado.agregar(
                qc.Control(
                    nombre=f"Columna pseudonimizada: {columna}",
                    aprobado=bool(real[columna].notna().any()),
                    severidad=qc.Severidad.BLOQUEANTE,
                    detalle=f"{real[columna].nunique():,} valores distintos tras el mapeo",
                )
            )

    controles = {k: v * anon.factor_importe for k, v in controles.items()}
    return real, presupuestos, controles

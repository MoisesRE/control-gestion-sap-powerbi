"""Controles de calidad y reconciliacion contra el reporte oficial.

La prueba de que un pipeline financiero funciona no es que termine sin error:
es que sus cifras coincidan con el reporte que la organizacion ya publica. Este
modulo compara el detalle transformado contra los importes de la maqueta de
Control de Gestion incluida en el propio libro, mes a mes, y deja constancia
del resultado en un informe versionable.

Los controles se clasifican por severidad. Un fallo `BLOQUEANTE` detiene el
pipeline: significa que las cifras no son publicables. Un `AVISO` se registra
en el informe y no detiene nada.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path

import pandas as pd

from ..anonymize.scaler import ERROR_REDONDEO_APUNTE, error_maximo_agregado
from ..logging_setup import logger

log = logger("quality.checks")

#: Margen minimo al reconciliar importes. Para agregados grandes la
#: tolerancia efectiva se deriva del numero de apuntes sumados (ver
#: `anonymize.scaler.error_maximo_agregado`).
TOLERANCIA_IMPORTE = 0.05


class Severidad(StrEnum):
    BLOQUEANTE = "bloqueante"
    AVISO = "aviso"


@dataclass(slots=True)
class Control:
    nombre: str
    aprobado: bool
    severidad: Severidad
    detalle: str = ""
    metricas: dict[str, float] = field(default_factory=dict)

    @property
    def icono(self) -> str:
        if self.aprobado:
            return "OK"
        return "FALLO" if self.severidad is Severidad.BLOQUEANTE else "AVISO"


@dataclass(slots=True)
class ResultadoCalidad:
    controles: list[Control] = field(default_factory=list)

    def agregar(self, control: Control) -> Control:
        nivel = log.info if control.aprobado else (
            log.error if control.severidad is Severidad.BLOQUEANTE else log.warning
        )
        nivel("[%s] %s %s", control.icono, control.nombre, control.detalle)
        self.controles.append(control)
        return control

    @property
    def bloqueantes(self) -> list[Control]:
        return [
            c for c in self.controles
            if not c.aprobado and c.severidad is Severidad.BLOQUEANTE
        ]

    def exigir_aprobacion(self) -> None:
        if self.bloqueantes:
            lineas = "\n".join(f"  - {c.nombre}: {c.detalle}" for c in self.bloqueantes)
            raise RuntimeError(f"controles bloqueantes no superados:\n{lineas}")

    def a_markdown(self, titulo: str = "Informe de calidad de datos") -> str:
        aprobados = sum(c.aprobado for c in self.controles)
        lineas = [
            f"# {titulo}",
            "",
            f"Generado: {datetime.now():%Y-%m-%d %H:%M}",
            "",
            f"**{aprobados} de {len(self.controles)} controles superados.**",
            "",
            "| Control | Resultado | Detalle |",
            "| --- | --- | --- |",
        ]
        for c in self.controles:
            detalle = c.detalle.replace("|", "\\|")
            lineas.append(f"| {c.nombre} | {c.icono} | {detalle} |")

        con_metricas = [c for c in self.controles if c.metricas]
        if con_metricas:
            lineas += ["", "## Metricas", ""]
            for c in con_metricas:
                lineas.append(f"### {c.nombre}")
                lineas.append("")
                for k, v in c.metricas.items():
                    lineas.append(f"- `{k}`: {v:,.4f}" if isinstance(v, float) else f"- `{k}`: {v}")
                lineas.append("")
        return "\n".join(lineas)

    def guardar(self, ruta: Path, titulo: str = "Informe de calidad de datos") -> None:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(self.a_markdown(titulo), encoding="utf-8")
        log.info("informe de calidad escrito en %s", ruta)


# --- controles individuales -------------------------------------------------


def validar_contrato(
    df: pd.DataFrame, esperadas: tuple[str, ...], resultado: ResultadoCalidad
) -> None:
    faltan = [c for c in esperadas if c not in df.columns]
    resultado.agregar(
        Control(
            nombre="Contrato de columnas",
            aprobado=not faltan,
            severidad=Severidad.BLOQUEANTE,
            detalle=f"{len(esperadas)} columnas esperadas"
            + (f"; faltan {faltan}" if faltan else "; todas presentes"),
        )
    )


def validar_dominios(
    df: pd.DataFrame, *, ejercicios: set[int], resultado: ResultadoCalidad
) -> None:
    periodos = set(df["periodo"].unique().tolist())
    fuera = periodos - set(range(1, 13))
    resultado.agregar(
        Control(
            nombre="Periodo en el rango 1-12",
            aprobado=not fuera,
            severidad=Severidad.BLOQUEANTE,
            detalle=f"periodos presentes: {sorted(periodos)}"
            + (f"; fuera de rango: {sorted(fuera)}" if fuera else ""),
        )
    )

    hallados = set(df["ejercicio"].unique().tolist())
    resultado.agregar(
        Control(
            nombre="Ejercicios esperados",
            aprobado=hallados <= ejercicios,
            severidad=Severidad.BLOQUEANTE,
            detalle=f"esperados {sorted(ejercicios)}, hallados {sorted(hallados)}",
        )
    )

    for columna in ("grupo", "cuenta_codigo", "ceco_codigo"):
        nulos = int(df[columna].isna().sum())
        resultado.agregar(
            Control(
                nombre=f"Clave sin nulos: {columna}",
                aprobado=nulos == 0,
                severidad=Severidad.BLOQUEANTE,
                detalle=f"{nulos:,} nulos de {len(df):,} filas",
            )
        )


def validar_dimension_consistente(
    df: pd.DataFrame, clave: str, atributo: str, resultado: ResultadoCalidad
) -> None:
    """Un codigo de dimension debe tener un unico valor por atributo.

    Si un centro de coste aparece con dos descripciones, la dimension no puede
    construirse sin decidir cual gana, y el reporte mostraria una u otra segun
    el orden de carga.
    """
    conteo = df.groupby(clave, observed=True)[atributo].nunique(dropna=True)
    ambiguos = conteo[conteo > 1]
    resultado.agregar(
        Control(
            nombre=f"Dimension consistente: {clave} -> {atributo}",
            aprobado=ambiguos.empty,
            severidad=Severidad.AVISO,
            detalle=(
                f"{len(ambiguos)} claves con mas de un {atributo}"
                + (f" (ej. {ambiguos.index[0]})" if not ambiguos.empty else "")
            ),
            metricas={"claves_ambiguas": float(len(ambiguos))},
        )
    )


def validar_marca_reverso(df: pd.DataFrame, resultado: ResultadoCalidad) -> None:
    """Comprueba la interpretacion de la columna `Documento anulacion`.

    El 37,5% de los apuntes llega con la marca puesta. Si significase
    "documento anulado" habria que excluirlos, y los ingresos del ejercicio
    caerian. El control verifica lo que se observo al perfilar: la marca no
    afecta a ningun apunte de ingresos, de modo que excluirla o no deja los
    ingresos intactos, y el reporte oficial se reproduce sumando todo. La
    conclusion es que la marca es informativa y no debe filtrarse.
    """
    marcados = df[df["marca_reverso"].fillna(False)]
    ingresos_marcados = float(marcados.loc[marcados["grupo"] == "Ingresos", "importe"].sum())
    resultado.agregar(
        Control(
            nombre="Marca de reverso no afecta a ingresos",
            aprobado=abs(ingresos_marcados) < TOLERANCIA_IMPORTE,
            severidad=Severidad.AVISO,
            detalle=(
                f"{len(marcados):,} apuntes marcados ({100 * len(marcados) / len(df):.1f}%); "
                f"importe de ingresos marcados {ingresos_marcados:,.2f}"
            ),
            metricas={
                "apuntes_marcados": float(len(marcados)),
                "ingresos_marcados": ingresos_marcados,
            },
        )
    )


def reconciliar_contra_maqueta(
    df: pd.DataFrame,
    control_mensual: pd.Series,
    resultado: ResultadoCalidad,
    *,
    factor: float = 1.0,
    nombre: str = "Reconciliacion de ingresos contra la maqueta",
    dim_cuenta: pd.DataFrame | None = None,
) -> None:
    """Compara los ingresos por periodo contra los importes de la maqueta.

    `control_mensual` lleva el importe oficial indexado por periodo, tal como
    figura en el libro. `factor` permite reconciliar despues de escalar los
    importes: se aplica al valor de control, no al calculado, para que la
    comparacion sea contra la cifra oficial transformada del mismo modo.
    """
    # En el modelo final el grupo vive en la dimension de cuenta, no en el
    # hecho: se reincorpora solo para este control.
    if "grupo" not in df.columns:
        if dim_cuenta is None:
            raise ValueError(
                "el hecho no trae la columna 'grupo'; pasar dim_cuenta para resolverla"
            )
        df = df.merge(dim_cuenta[["cuenta_codigo", "grupo"]], on="cuenta_codigo", how="left")

    ingresos = df.loc[df["grupo"] == "Ingresos"]
    calculado = ingresos.groupby("periodo", observed=True)["importe"].sum().round(2)
    apuntes = ingresos.groupby("periodo", observed=True)["importe"].size()
    esperado = (control_mensual * factor).round(2)

    comparacion = pd.DataFrame({"esperado": esperado, "calculado": calculado}).dropna()
    comparacion["diferencia"] = comparacion["calculado"] - comparacion["esperado"]

    # La tolerancia de cada periodo se deriva del numero de apuntes que lo
    # componen: escalar y redondear n importes puede desviar la suma hasta n
    # medias centesimas. Un umbral fijo seria arbitrario y, con 30.000 apuntes
    # al mes, inevitablemente erroneo.
    comparacion["tolerancia"] = (
        comparacion.index.map(apuntes).to_series(index=comparacion.index).fillna(0)
        * ERROR_REDONDEO_APUNTE
    ).clip(lower=TOLERANCIA_IMPORTE)
    descuadres = comparacion[comparacion["diferencia"].abs() > comparacion["tolerancia"]]

    peor = float(comparacion["diferencia"].abs().max()) if not comparacion.empty else 0.0
    resultado.agregar(
        Control(
            nombre=nombre,
            aprobado=descuadres.empty and not comparacion.empty,
            severidad=Severidad.BLOQUEANTE,
            detalle=(
                f"{len(comparacion)} periodos comparados; "
                f"{len(descuadres)} con descuadre; maxima diferencia {peor:,.4f} "
                f"(tolerancia maxima {comparacion['tolerancia'].max():,.2f})"
            ),
            # No se publica el total absoluto, y no es una omision: este
            # control se ejecuta dos veces, y en la pasada previa a anonimizar
            # el total **es la cifra real del ejercicio**. El informe de
            # calidad se versiona, de modo que publicarlo equivalia a publicar
            # la facturacion del empleador al centimo. Lo que demuestra el
            # control es la diferencia contra su tolerancia, que no depende de
            # la magnitud: un descuadre de 0,00 sobre 12 periodos prueba
            # exactamente lo mismo sin revelar sobre que importe se midio.
            metricas={
                "periodos_comparados": float(len(comparacion)),
                "periodos_descuadrados": float(len(descuadres)),
                "maxima_diferencia_absoluta": peor,
                "tolerancia_maxima": float(comparacion["tolerancia"].max())
                if not comparacion.empty
                else 0.0,
            },
        )
    )
    if not descuadres.empty:
        log.error("periodos descuadrados:\n%s", descuadres.to_string())


def validar_cuadre_agregados(
    hechos: pd.DataFrame, dimensiones: dict[str, pd.DataFrame], resultado: ResultadoCalidad
) -> None:
    """Toda clave del hecho debe existir en su dimension, y al reves no sobrar.

    Es el control que garantiza que el modelo estrella no pierde importe al
    unir: una clave huerfana en Power BI se convierte en una fila en blanco que
    descuadra los totales de forma silenciosa.
    """
    for nombre, dim in dimensiones.items():
        clave = dim.columns[0]
        if clave not in hechos.columns:
            continue
        huerfanas = set(hechos[clave].dropna().unique()) - set(dim[clave])
        importe_huerfano = float(hechos.loc[hechos[clave].isin(huerfanas), "importe"].sum())
        resultado.agregar(
            Control(
                nombre=f"Integridad referencial: {nombre}",
                aprobado=not huerfanas,
                severidad=Severidad.BLOQUEANTE,
                detalle=(
                    f"{len(huerfanas)} claves del hecho sin fila en la dimension"
                    + (f"; importe afectado {importe_huerfano:,.2f}" if huerfanas else "")
                ),
            )
        )


def validar_suma_invariante(
    antes: float, despues: float, etapa: str, resultado: ResultadoCalidad
) -> None:
    """La suma de importes no puede cambiar en una etapa que no la toca."""
    diferencia = abs(despues - antes)
    resultado.agregar(
        Control(
            nombre=f"Suma invariante tras {etapa}",
            aprobado=diferencia < TOLERANCIA_IMPORTE,
            severidad=Severidad.BLOQUEANTE,
            detalle=f"antes {antes:,.2f} | despues {despues:,.2f} | delta {diferencia:,.4f}",
        )
    )


def validar_orden_pl(dim_cuenta: pd.DataFrame, resultado: ResultadoCalidad) -> None:
    """Comprueba que toda linea del P&L tiene un orden de presentacion.

    Un grupo sin orden cae al final del informe con el valor centinela 999, lo
    que en Power BI se traduce en una linea descolgada al pie del P&L. El fallo
    es silencioso -- las cifras son correctas, solo aparecen en el sitio
    equivocado -- y por eso conviene un control explicito: basta un acento de
    diferencia entre el literal del extracto y la clave del diccionario.
    """
    sin_orden = sorted(
        dim_cuenta.loc[dim_cuenta["orden_pl"] == 999, "grupo"].dropna().unique()
    )
    resultado.agregar(
        Control(
            nombre="Toda linea del P&L tiene orden de presentacion",
            aprobado=not sin_orden,
            severidad=Severidad.AVISO,
            detalle=(
                f"{len(sin_orden)} grupos sin orden asignado"
                + (f": {sin_orden}" if sin_orden else "")
            ),
            metricas={"grupos_sin_orden": float(len(sin_orden))},
        )
    )


def validar_coherencia_entre_hechos(
    fact_escenario: pd.DataFrame,
    fact_detalle: pd.DataFrame,
    clave_real: str,
    resultado: ResultadoCalidad,
) -> None:
    """El real debe sumar lo mismo en la tabla agregada y en la de detalle.

    Las dos tablas de hechos tienen granos distintos y se construyen por
    caminos distintos, de modo que coincidir al centimo no es trivial: es la
    prueba de que la agregacion por escenario no pierde ni duplica importe.
    Un descuadre aqui significa que el mismo dato cuenta dos historias segun
    el visual que lo mire, que es el peor fallo posible en un reporte.
    """
    agregado = float(
        fact_escenario.loc[fact_escenario["escenario_clave"] == clave_real, "importe"].sum()
    )
    detalle = float(fact_detalle["importe"].sum())
    diferencia = abs(agregado - detalle)
    tolerancia = error_maximo_agregado(len(fact_escenario))

    resultado.agregar(
        Control(
            nombre="Coherencia entre el hecho agregado y el detalle",
            aprobado=diferencia <= tolerancia,
            severidad=Severidad.BLOQUEANTE,
            detalle=(
                f"fact_escenario[{clave_real}] {agregado:,.2f} vs fact_resultado "
                f"{detalle:,.2f}; delta {diferencia:,.4f} (tolerancia {tolerancia:,.2f})"
            ),
            metricas={"agregado": agregado, "detalle": detalle, "delta": diferencia},
        )
    )


def validar_escenarios_declarados(
    fact_escenario: pd.DataFrame, dim_escenario: pd.DataFrame, resultado: ResultadoCalidad
) -> None:
    """Todo escenario del hecho debe existir en la dimension, y al reves.

    Un escenario en el hecho sin fila en la dimension aparece en Power BI como
    una serie en blanco; uno en la dimension sin datos, como un filtro que no
    devuelve nada. Ambos casos confunden al lector del reporte sin producir
    ningun error.
    """
    en_hecho = set(fact_escenario["escenario_clave"].unique())
    en_dim = set(dim_escenario["escenario_clave"])
    huerfanos, vacios = en_hecho - en_dim, en_dim - en_hecho

    resultado.agregar(
        Control(
            nombre="Escenarios del hecho y de la dimension coinciden",
            aprobado=not huerfanos and not vacios,
            severidad=Severidad.BLOQUEANTE,
            detalle=(
                f"{len(en_hecho)} escenarios con datos"
                + (f"; sin dimension: {sorted(huerfanos)}" if huerfanos else "")
                + (f"; sin datos: {sorted(vacios)}" if vacios else "")
            ),
        )
    )

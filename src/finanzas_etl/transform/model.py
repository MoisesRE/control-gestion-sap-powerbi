"""Construccion del esquema en estrella.

Decisiones de modelado
----------------------
* **Granularidad del hecho.** Una fila por apunte contable. Se conserva el
  detalle en lugar de agregar por mes y cuenta porque VertiPaq comprime esta
  tabla a una fraccion de su tamano y porque el detalle permite el analisis de
  dispersion por documento, que se pierde al agregar.
* **Claves sustitutas.** Las dimensiones se identifican por su codigo natural
  ya pseudonimizado, no por un entero autoincremental. En un modelo de este
  tamano la ganancia de una clave entera es marginal y una clave legible hace
  el modelo mucho mas facil de depurar en Power BI y en SQL.
* **Dimension de tiempo por periodo contable.** La clave es `ejercicio * 100 +
  periodo`. El periodo contable, y no la fecha del documento, es lo que define
  en que mes se reconoce un resultado.
* **Dos tablas de hechos con dimensiones conformadas.** Real y presupuesto
  comparten las dimensiones de centro, cuenta y tiempo, lo que permite
  compararlos en el mismo visual sin relaciones indirectas.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import pandas as pd

from ..logging_setup import logger

log = logger("transform.model")

MESES_NOMBRE = (
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
)

#: Grupos del extracto que representan ingreso y no coste. Determinan el signo
#: esperado y la clasificacion en el P&L.
GRUPOS_INGRESO = frozenset({"Ingresos", "Ingresos Diversos"})

#: Orden de presentacion de las lineas del P&L, de arriba abajo. Las claves
#: deben coincidir literalmente con los valores de `Grupo` en el extracto,
#: acentos incluidos; `validar_orden_pl` comprueba que no falte ninguna.
ORDEN_PL: dict[str, int] = {
    "Ingresos": 10,
    "Ingresos Diversos": 20,
    "Servicio de terceros": 30,
    "Mano de Obra": 40,
    "Otros Gastos Personal": 50,
    "Combustible": 60,
    "Mantenimiento Unidades": 70,
    "Mantenimiento Diversos": 80,
    "Peajes": 90,
    "Alquileres": 100,
    "Seguridad": 110,
    "Seguros": 120,
    "Suministros": 130,
    "Servicios Diversos": 140,
    "Servicios de Comunicación": 150,
    "Servicios Basicos": 160,
    "Gastos de Viaje": 170,
    "Publicidad": 180,
    "Comisiones": 190,
    "Asesorias": 200,
    "Servicio Pasajeros": 210,
    "Servicio de Lavanderia": 215,
    "Tributos": 220,
    "Depreciacion": 230,
    "Diferencia de Cambio": 240,
    "Gasto Financiero": 250,
    "Egresos Diversos": 260,
}


def construir_dim_tiempo(hechos: pd.DataFrame) -> pd.DataFrame:
    """Dimension de tiempo a nivel de periodo contable."""
    claves = (
        hechos[["fecha_clave", "ejercicio", "periodo"]]
        .drop_duplicates()
        .sort_values("fecha_clave")
        .reset_index(drop=True)
    )
    claves["mes_nombre"] = claves["periodo"].map(lambda p: MESES_NOMBRE[int(p) - 1])
    claves["mes_abrev"] = claves["mes_nombre"].str[:3]
    claves["trimestre"] = ((claves["periodo"] - 1) // 3 + 1).astype("int8")
    claves["etiqueta_trimestre"] = (
        "T" + claves["trimestre"].astype(str) + " " + claves["ejercicio"].astype(str)
    )
    claves["etiqueta_mes"] = (
        claves["mes_abrev"] + " " + claves["ejercicio"].astype(str)
    )
    claves["mes_inicio"] = pd.to_datetime(
        dict(year=claves["ejercicio"], month=claves["periodo"], day=1)
    )
    claves["mes_fin"] = claves["mes_inicio"] + pd.offsets.MonthEnd(1)
    log.info("dim_tiempo: %d periodos", len(claves))
    return claves


def construir_dim_centro(*fuentes: pd.DataFrame) -> pd.DataFrame:
    """Dimension de centro de coste, conformada entre real y presupuesto.

    Cuando un centro aparece en varias fuentes con descripciones distintas se
    toma la del primer origen que lo declara, que es el detalle real. La
    ambiguedad queda registrada por el control de calidad correspondiente.
    """
    columnas = ["ceco_codigo", "ceco_nombre", "ambito", "estructura", "unidad_negocio"]
    partes = []
    for df in fuentes:
        presentes = [c for c in columnas if c in df.columns]
        if "ceco_codigo" not in presentes:
            continue
        partes.append(df[presentes].drop_duplicates(subset="ceco_codigo"))

    dim = (
        pd.concat(partes, ignore_index=True)
        .drop_duplicates(subset="ceco_codigo", keep="first")
        .sort_values("ceco_codigo")
        .reset_index(drop=True)
    )
    for columna in columnas:
        if columna not in dim.columns:
            dim[columna] = pd.NA
    log.info("dim_centro: %d centros de coste", len(dim))
    return dim[columnas]


def construir_dim_cuenta(*fuentes: pd.DataFrame) -> pd.DataFrame:
    """Dimension de cuenta con la jerarquia del P&L.

    `clase_pcge` aprovecha que el plan contable general empresarial peruano
    codifica la naturaleza del gasto en el primer digito, lo que da una
    jerarquia util sin necesidad de una tabla externa.
    """
    columnas = ["cuenta_codigo", "cuenta_nombre", "grupo", "clase_costo_gasto"]
    partes = []
    for df in fuentes:
        presentes = [c for c in columnas if c in df.columns]
        if "cuenta_codigo" not in presentes:
            continue
        partes.append(df[presentes].drop_duplicates(subset="cuenta_codigo"))

    dim = (
        pd.concat(partes, ignore_index=True)
        .drop_duplicates(subset="cuenta_codigo", keep="first")
        .sort_values("cuenta_codigo")
        .reset_index(drop=True)
    )
    for columna in columnas:
        if columna not in dim.columns:
            dim[columna] = pd.NA

    dim["clase_pcge"] = dim["cuenta_codigo"].astype("string").str[0]
    dim["es_ingreso"] = dim["grupo"].isin(GRUPOS_INGRESO)
    dim["linea_pl"] = dim["grupo"].where(dim["grupo"].notna(), "Sin clasificar")
    dim["orden_pl"] = (
        dim["grupo"].map(ORDEN_PL).fillna(999).astype("int16")
    )
    log.info("dim_cuenta: %d cuentas, %d grupos", len(dim), dim["grupo"].nunique())
    return dim


def construir_hechos_real(df: pd.DataFrame, clave_escenario: str) -> pd.DataFrame:
    """Tabla de hechos del ejercicio real, con la medida y sus atributos.

    El detalle recibe `escenario_clave` y no una etiqueta libre como "Real"
    porque es una clave foranea contra `dim_escenario`. Aunque esta tabla
    contenga por definicion un unico escenario -- el real observado --,
    declararla con la misma clave que usa el hecho agregado hace que la
    relacion exista en el modelo en lugar de quedar documentada en prosa, y
    que PostgreSQL pueda imponerla como `REFERENCES`.
    """
    columnas = [
        "fecha_clave", "ejercicio", "periodo",
        "ceco_codigo", "cuenta_codigo",
        "importe",
        "fecha_contable", "fecha_documento",
        "origen_tipo", "origen_detalle", "transaccion_sap", "tipo_contrapartida",
        "marca_reverso", "documento_id",
        "ceco_origen_codigo", "cuenta_origen_codigo",
    ]
    hechos = df[[c for c in columnas if c in df.columns]].copy()
    hechos["escenario_clave"] = clave_escenario
    log.info("fact_resultado: %s apuntes", f"{len(hechos):,}")
    return hechos


def optimizar_dtypes(df: pd.DataFrame, umbral_categoria: float = 0.5) -> pd.DataFrame:
    """Convierte a `category` las columnas de texto de baja cardinalidad.

    Reduce el Parquet y la memoria del DataFrame sin afectar a los valores. El
    umbral evita convertir columnas como el identificador de documento, donde
    la categoria seria mas costosa que la cadena.
    """
    salida = df.copy()
    for columna in salida.select_dtypes(include=["string", "object"]).columns:
        n = len(salida)
        if n and salida[columna].nunique(dropna=True) / n < umbral_categoria:
            salida[columna] = salida[columna].astype("category")
    return salida


# --- Escenarios -------------------------------------------------------------

#: Tipos de escenario. `Real` es resultado observado; `Presupuesto`, objetivo
#: aprobado. La naturaleza simulada es ortogonal al tipo y vive en su propia
#: columna, porque un real simulado sigue siendo un real a efectos de analisis.
TIPO_REAL = "Real"
TIPO_PRESUPUESTO = "Presupuesto"


@dataclass(frozen=True, slots=True)
class Escenario:
    """Una version del resultado: un tipo y un ejercicio."""

    clave: str
    tipo: str
    ejercicio: int
    es_simulado: bool = False
    #: Periodos cubiertos. Un ejercicio en curso no cubre los doce.
    periodos: int = 12

    @property
    def etiqueta(self) -> str:
        """Etiqueta de presentacion: el tipo y el ejercicio, sin mas.

        La etiqueta NO marca el escenario generado. Eso lo hace `es_simulado`,
        que es una columna del modelo y llega hasta el informe: la procedencia
        de las cifras es un atributo que se puede filtrar y auditar, no un
        parentesis pegado a un rotulo que ademas se arrastra a cada eje, cada
        leyenda y cada titulo de visual.
        """
        return f"{self.tipo} {self.ejercicio}"


def construir_dim_escenario(escenarios: Sequence[Escenario]) -> pd.DataFrame:
    """Dimension de escenario, con el orden de presentacion del reporte.

    `es_simulado` es una columna del modelo y no una nota al pie: un filtro
    sobre ella separa lo observado de lo generado, y los controles la usan para
    saber que escenario tiene patron oficial contra el que reconciliar y cual
    no. La etiqueta del escenario no la repite.
    """
    dim = pd.DataFrame(
        [
            {
                "escenario_clave": e.clave,
                "escenario": e.etiqueta,
                "tipo_escenario": e.tipo,
                "ejercicio": e.ejercicio,
                "es_simulado": e.es_simulado,
                "periodos_cubiertos": e.periodos,
                "orden_escenario": i * 10,
            }
            for i, e in enumerate(
                sorted(escenarios, key=lambda e: (e.ejercicio, e.tipo != TIPO_PRESUPUESTO)), start=1
            )
        ]
    )
    log.info(
        "dim_escenario: %d escenarios (%d simulados)",
        len(dim), int(dim["es_simulado"].sum()),
    )
    return dim


def construir_fact_escenario(partes: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Hecho comparativo al grano `escenario x centro x cuenta x periodo`.

    Por que una tabla aparte del detalle
    ------------------------------------
    El real observado tiene grano de apunte contable; el presupuesto y el
    simulado, de centro por cuenta y mes. Apilarlos en una sola tabla mezclaria
    dos granos distintos, lo que obliga a cualquier medida a saber de que
    escenario viene cada fila antes de poder sumarla.

    La solucion habitual es la que se aplica aqui: una tabla de hechos agregada
    al grano comun, que es la que alimenta todas las comparaciones entre
    escenarios, y el detalle transaccional en su propia tabla para el analisis
    de dispersion y trazabilidad. El real aparece en las dos, y el pipeline
    comprueba que ambas suman lo mismo.
    """
    marcos = []
    for clave, df in partes.items():
        agregado = (
            df.groupby(["ejercicio", "periodo", "ceco_codigo", "cuenta_codigo"], observed=True)[
                "importe"
            ]
            .sum()
            .round(2)
            .reset_index()
        )
        agregado["escenario_clave"] = clave
        marcos.append(agregado)

    hechos = pd.concat(marcos, ignore_index=True)
    hechos["fecha_clave"] = hechos["ejercicio"].astype("int32") * 100 + hechos[
        "periodo"
    ].astype("int32")
    hechos = hechos[
        ["escenario_clave", "fecha_clave", "ejercicio", "periodo",
         "ceco_codigo", "cuenta_codigo", "importe"]
    ]
    log.info(
        "fact_escenario: %s filas en %d escenarios",
        f"{len(hechos):,}", hechos["escenario_clave"].nunique(),
    )
    return hechos

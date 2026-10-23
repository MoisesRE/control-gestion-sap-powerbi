"""Conversion de los valores textuales del XLSX a tipos analiticos."""

from __future__ import annotations

import pandas as pd

from ..logging_setup import logger
from .schema import Columna

log = logger("transform.clean")

#: Excel cuenta los dias desde el 1 de enero de 1900 tratando 1900 como
#: bisiesto, que no lo fue. El desfase se compensa fijando la epoca en
#: 1899-12-30, convencion que comparten Excel, LibreOffice y SAP al exportar.
EPOCA_EXCEL = pd.Timestamp("1899-12-30")

#: Marcas que SAP y los analistas usan como "verdadero" en columnas de flag.
VERDADEROS = frozenset({"X", "x", "1", "TRUE", "True", "SI", "Si", "S"})


def serial_a_fecha(serie: pd.Series) -> pd.Series:
    """Convierte seriales de Excel en fechas.

    Las fechas tambien pueden llegar como texto si la celda estaba formateada
    como cadena, de modo que se intenta primero la via numerica y se completa
    con el parseo textual de los valores que queden sin resolver.
    """
    numerico = pd.to_numeric(serie, errors="coerce")
    fechas = EPOCA_EXCEL + pd.to_timedelta(numerico, unit="D")

    pendientes = fechas.isna() & serie.notna()
    if pendientes.any():
        rescatadas = pd.to_datetime(serie[pendientes], errors="coerce", format="mixed")
        fechas.loc[pendientes] = rescatadas
        log.debug("fechas rescatadas por parseo textual: %d", int(rescatadas.notna().sum()))

    # Un serial fuera de rango delata una celda con basura, no una fecha.
    fuera_rango = fechas.notna() & (
        (fechas < pd.Timestamp("1990-01-01")) | (fechas > pd.Timestamp("2100-01-01"))
    )
    if fuera_rango.any():
        log.warning("%d fechas fuera del rango 1990-2100 anuladas", int(fuera_rango.sum()))
        fechas.loc[fuera_rango] = pd.NaT
    return fechas.astype("datetime64[ns]")


def texto_a_bool(serie: pd.Series) -> pd.Series:
    """Normaliza una columna de marca a booleano nullable."""
    return serie.isin(VERDADEROS).astype("boolean")


def normalizar_texto(serie: pd.Series) -> pd.Series:
    """Recorta espacios y unifica las cadenas vacias a nulo.

    El extracto trae celdas con un unico espacio donde el analista borro el
    contenido; sin esta normalizacion aparecen como una categoria mas.
    """
    limpia = serie.astype("string").str.strip()
    return limpia.replace({"": pd.NA, "-": pd.NA})


def aplicar_tipos(df: pd.DataFrame, columnas: tuple[Columna, ...]) -> pd.DataFrame:
    """Materializa cada columna en el dtype declarado por el contrato."""
    salida = pd.DataFrame(index=df.index)
    for col in columnas:
        if col.destino not in df.columns:
            continue
        serie = df[col.destino]
        if col.tipo.startswith("datetime"):
            salida[col.destino] = serial_a_fecha(serie)
        elif col.tipo == "boolean":
            salida[col.destino] = texto_a_bool(serie)
        elif col.tipo.startswith(("int", "float")):
            numerico = pd.to_numeric(serie, errors="coerce")
            if col.tipo.startswith("int"):
                # Un entero no admite nulos: los periodos y ejercicios deben
                # venir completos, y si no lo estan es un fallo de extraccion
                # que conviene que explote aqui y no en la carga a Postgres.
                faltan = int(numerico.isna().sum())
                if faltan:
                    raise ValueError(
                        f"{col.destino}: {faltan} valores no numericos en una columna entera"
                    )
                salida[col.destino] = numerico.astype(col.tipo)
            else:
                salida[col.destino] = numerico.astype("float64").fillna(0.0)
        else:
            salida[col.destino] = normalizar_texto(serie)
    return salida


def anadir_claves_tiempo(df: pd.DataFrame) -> pd.DataFrame:
    """Agrega la clave de fecha y los atributos derivados del periodo.

    La clave de la dimension tiempo se construye sobre (ejercicio, periodo) y
    no sobre la fecha contable: el resultado de gestion se reporta por periodo
    contable, y un apunte de diciembre contabilizado en enero pertenece al
    periodo que indica el extracto, no al mes de su fecha.
    """
    df = df.copy()
    df["fecha_clave"] = df["ejercicio"].astype("int32") * 100 + df["periodo"].astype("int32")
    df["mes_inicio"] = pd.to_datetime(
        dict(year=df["ejercicio"], month=df["periodo"], day=1), errors="coerce"
    )
    return df

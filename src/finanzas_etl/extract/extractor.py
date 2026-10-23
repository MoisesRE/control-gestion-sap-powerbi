"""Materializacion de las hojas de origen en DataFrames tipados."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ..logging_setup import logger
from ..transform.schema import (
    COLUMNAS_PRESUPUESTO,
    COLUMNAS_REAL,
    MESES,
    PRIMERA_COLUMNA_MES,
    Columna,
    ancho_requerido,
)
from .xlsx_stream import LibroXLSX

log = logger("extract.extractor")

#: Filas que se acumulan antes de volcarlas a un DataFrame parcial. Acota el
#: pico de memoria de las listas de Python, que es muy superior al del
#: DataFrame resultante.
TAMANO_LOTE = 100_000


def extraer_detalle(
    libro: Path,
    hoja: str,
    *,
    primera_fila: int = 2,
    columnas: tuple[Columna, ...] = COLUMNAS_REAL,
) -> pd.DataFrame:
    """Lee la hoja de detalle y devuelve solo las columnas del contrato.

    Las filas completamente vacias se descartan aqui: la hoja de origen tiene
    el rango formateado muy por debajo de los datos reales y arrastra cientos
    de miles de filas sin contenido.
    """
    ancho = ancho_requerido(columnas)
    indices = [c.indice for c in columnas]
    nombres = [c.destino for c in columnas]
    columna_clave = columnas[0].indice  # ejercicio: si falta, la fila esta vacia

    lotes: list[pd.DataFrame] = []
    buffer: list[tuple] = []
    leidas = vacias = utiles = 0

    with LibroXLSX(libro) as lb:
        info = lb.hojas[hoja]
        log.info("leyendo hoja %r (%s) desde la fila %d", hoja, info.ruta_xml, primera_fila)

        for fila in lb.filas(hoja, ancho=ancho, desde_fila=primera_fila):
            leidas += 1
            if fila[columna_clave] is None:
                vacias += 1
                continue
            buffer.append(tuple(fila[i] for i in indices))

            if len(buffer) >= TAMANO_LOTE:
                lotes.append(pd.DataFrame(buffer, columns=nombres))
                utiles += len(buffer)
                buffer.clear()
                log.info("  %s filas utiles acumuladas", f"{utiles:,}")

    if buffer:
        lotes.append(pd.DataFrame(buffer, columns=nombres))

    df = (
        pd.concat(lotes, ignore_index=True)
        if lotes
        else pd.DataFrame(columns=nombres)
    )
    log.info(
        "hoja %r: %s filas leidas, %s vacias descartadas, %s utiles",
        hoja, f"{leidas:,}", f"{vacias:,}", f"{len(df):,}",
    )
    return df


def extraer_presupuesto(
    libro: Path,
    hoja: str,
    *,
    ejercicio: int,
    primera_fila: int = 6,
) -> pd.DataFrame:
    """Lee el presupuesto en formato ancho y lo despivota a formato largo.

    La hoja trae una fila por combinacion de centro, cuenta y concepto, y doce
    columnas de importe (Ene..Dic). El modelo analitico necesita una fila por
    combinacion y periodo, de modo que la tabla se transpone aqui.
    """
    ancho = PRIMERA_COLUMNA_MES + len(MESES)
    dims = [c.destino for c in COLUMNAS_PRESUPUESTO]
    indices_dim = [c.indice for c in COLUMNAS_PRESUPUESTO]

    filas: list[tuple] = []
    with LibroXLSX(libro) as lb:
        log.info("leyendo presupuesto %r desde la fila %d", hoja, primera_fila)
        for fila in lb.filas(hoja, ancho=ancho, desde_fila=primera_fila):
            if fila[COLUMNAS_PRESUPUESTO[2].indice] is None:  # sin centro de coste
                continue
            clave = tuple(fila[i] for i in indices_dim)
            for periodo, idx in enumerate(
                range(PRIMERA_COLUMNA_MES, PRIMERA_COLUMNA_MES + len(MESES)), start=1
            ):
                filas.append((*clave, periodo, fila[idx]))

    df = pd.DataFrame(filas, columns=[*dims, "periodo", "importe"])
    df["ejercicio"] = ejercicio
    df["importe"] = pd.to_numeric(df["importe"], errors="coerce").fillna(0.0)

    # Una linea presupuestaria a cero en un mes no aporta informacion y
    # multiplica por doce el tamano de la tabla.
    antes = len(df)
    df = df[df["importe"] != 0].reset_index(drop=True)
    log.info(
        "presupuesto %d: %s filas despivotadas, %s con importe distinto de cero",
        ejercicio, f"{antes:,}", f"{len(df):,}",
    )
    return df

"""Lectura de los importes de control de la maqueta de Control de Gestion.

La hoja `DETALLE PL` es el P&L que la organizacion publica. Esta organizada en
bandas horizontales de doce columnas, una por escenario y ejercicio: `REAL
2021`, ... `Real 2025`, `Presupuesto 2026`, `Forecast 2 2025`, y asi. La fila 2
rotula cada banda sobre su primera columna y la fila 3 repite los meses.

Este modulo localiza la banda por su rotulo en lugar de fijar la posicion en el
codigo. Si el analista inserta una columna o anade el ejercicio siguiente, el
control sigue leyendo la banda correcta en vez de desplazarse en silencio a la
de al lado, que es el modo tipico en que un control de este tipo empieza a
mentir sin que nadie lo note.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import pandas as pd

from ..logging_setup import logger
from .xlsx_stream import LibroXLSX

log = logger("extract.maqueta")

MESES_EN_BANDA = 12


def _normalizar(texto: str) -> str:
    """Minusculas, sin acentos y con los espacios colapsados."""
    sin_acentos = "".join(
        c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c)
    )
    return re.sub(r"\s+", " ", sin_acentos).strip().lower()


def localizar_banda(
    libro: Path,
    hoja: str,
    rotulo: str,
    *,
    fila_rotulos: int = 2,
    ancho_busqueda: int = 220,
) -> int:
    """Devuelve el indice de la primera columna de la banda rotulada `rotulo`.

    Los rotulos que empiezan por "Total" se ignoran: marcan la columna de
    totales que sigue a cada banda, no su inicio.
    """
    objetivo = _normalizar(rotulo)
    with LibroXLSX(libro) as lb:
        filas = list(
            lb.filas(hoja, ancho=ancho_busqueda, desde_fila=fila_rotulos, limite=1)
        )
    if not filas:
        raise ValueError(f"no se pudo leer la fila {fila_rotulos} de {hoja!r}")

    candidatos = [
        (i, v)
        for i, v in enumerate(filas[0])
        if v and not _normalizar(v).startswith("total")
    ]
    for indice, valor in candidatos:
        if _normalizar(valor) == objetivo:
            log.info("banda %r localizada en la columna %d de %r", rotulo, indice, hoja)
            return indice

    disponibles = ", ".join(repr(v) for _, v in candidatos)
    raise ValueError(
        f"no se encontro la banda {rotulo!r} en la fila {fila_rotulos} de {hoja!r}. "
        f"Bandas presentes: {disponibles}"
    )


def extraer_control_mensual(
    libro: Path,
    hoja: str,
    rotulo_banda: str,
    *,
    fila_metrica: int,
    nombre: str = "control",
    fila_rotulos: int = 2,
) -> pd.Series:
    """Lee los doce importes mensuales de una metrica dentro de una banda.

    Parameters
    ----------
    rotulo_banda:
        Rotulo del escenario en la fila de bandas, p. ej. ``"Real 2025"``.
    fila_metrica:
        Fila (base 1) de la linea del P&L a leer, p. ej. la de INGRESOS.
    """
    inicio = localizar_banda(libro, hoja, rotulo_banda, fila_rotulos=fila_rotulos)
    with LibroXLSX(libro) as lb:
        filas = list(
            lb.filas(
                hoja,
                ancho=inicio + MESES_EN_BANDA,
                desde_fila=fila_metrica,
                limite=1,
            )
        )
    if not filas:
        raise ValueError(f"no se pudo leer la fila {fila_metrica} de {hoja!r}")

    valores = filas[0][inicio : inicio + MESES_EN_BANDA]
    serie = pd.Series(
        [pd.to_numeric(v, errors="coerce") for v in valores],
        index=pd.RangeIndex(1, MESES_EN_BANDA + 1, name="periodo"),
        name=nombre,
        dtype="float64",
    )

    vacios = int(serie.isna().sum())
    if vacios:
        log.warning("%s: %d periodos sin importe en la maqueta", nombre, vacios)
    serie = serie.dropna()

    log.info(
        "%s [%s]: %d periodos, total %s",
        nombre, rotulo_banda, len(serie), f"{float(serie.sum()):,.2f}",
    )
    return serie

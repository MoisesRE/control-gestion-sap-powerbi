"""Logging del pipeline.

La consola de Windows usa por defecto una pagina de codigos de 8 bits y lanza
`UnicodeEncodeError` al escribir acentos. Forzamos UTF-8 en el stream para que
los mensajes del pipeline sean legibles en cmd, PowerShell y CI por igual.
"""

from __future__ import annotations

import contextlib
import logging
import sys
from pathlib import Path

_FORMATO = "%(asctime)s | %(levelname)-7s | %(name)-28s | %(message)s"


def configurar(nivel: int = logging.INFO, fichero: Path | None = None) -> logging.Logger:
    raiz = logging.getLogger("finanzas_etl")
    if raiz.handlers:
        return raiz

    raiz.setLevel(nivel)
    formato = logging.Formatter(_FORMATO, datefmt="%H:%M:%S")

    with contextlib.suppress(AttributeError, OSError):
        sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

    consola = logging.StreamHandler(sys.stderr)
    consola.setFormatter(formato)
    raiz.addHandler(consola)

    if fichero is not None:
        fichero.parent.mkdir(parents=True, exist_ok=True)
        disco = logging.FileHandler(fichero, mode="w", encoding="utf-8")
        disco.setFormatter(formato)
        raiz.addHandler(disco)

    raiz.propagate = False
    return raiz


def logger(nombre: str) -> logging.Logger:
    return logging.getLogger(f"finanzas_etl.{nombre}")

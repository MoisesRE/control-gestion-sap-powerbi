"""Punto de entrada de la carga a PostgreSQL.

    python -m finanzas_etl.load              # base, DDL, carga y verificacion
    python -m finanzas_etl.load --recrear    # borra los esquemas y los rehace
    python -m finanzas_etl.load --solo-ddl   # crea el esquema sin cargar datos

Requiere que el ETL de la etapa 1 haya escrito los Parquet. La conexion se
toma de las variables PG* del fichero .env.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time

from ..config import ConfigPostgres, RutasProyecto
from ..logging_setup import configurar
from . import postgres


def construir_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="finanzas-etl-load",
        description="Construye la capa PostgreSQL y carga el modelo en estrella.",
    )
    p.add_argument(
        "--recrear",
        action="store_true",
        help=(
            "elimina los esquemas core, pl y qa antes de aplicar el DDL. "
            "Necesario cuando cambia la definicion de una tabla."
        ),
    )
    p.add_argument(
        "--solo-ddl",
        action="store_true",
        help="aplica el DDL y termina, sin cargar datos ni verificar.",
    )
    p.add_argument("-v", "--verbose", action="store_true", help="registro en nivel DEBUG")
    return p


def main(argv: list[str] | None = None) -> int:
    args = construir_parser().parse_args(argv)
    rutas = RutasProyecto()
    rutas.preparar()
    log = configurar(
        logging.DEBUG if args.verbose else logging.INFO,
        fichero=rutas.reportes / "carga.log",
    )

    cfg = ConfigPostgres.desde_entorno()
    if not cfg.password:
        log.error(
            "falta PGPASSWORD. Copiar .env.example a .env y rellenar la seccion "
            "de PostgreSQL."
        )
        return 1

    log.info("destino: %s", cfg)
    inicio = time.perf_counter()
    try:
        salida = postgres.ejecutar(
            cfg,
            rutas.sql,
            rutas.procesado,
            recrear=args.recrear,
            solo_ddl=args.solo_ddl,
        )
    except (RuntimeError, FileNotFoundError) as exc:
        log.error("la carga no se completo: %s", exc)
        return 1

    if args.solo_ddl:
        log.info("DDL aplicado en %.1f s", time.perf_counter() - inicio)
        return 0

    salida.calidad.guardar(
        rutas.reportes / "calidad_carga.md",
        titulo="Informe de carga en PostgreSQL",
    )

    if salida.calidad.bloqueantes:
        log.error(
            "la carga termino pero %d controles bloqueantes fallaron: "
            "revisar reports/calidad_carga.md",
            len(salida.calidad.bloqueantes),
        )
        return 2

    aprobados = len(salida.calidad.controles)
    log.info(
        "carga completada en %.1f s | %s filas | %d controles superados",
        time.perf_counter() - inicio,
        f"{sum(salida.filas.values()):,}",
        aprobados,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

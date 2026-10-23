"""Punto de entrada del ETL.

    python -m finanzas_etl                 # pipeline completo, anonimizado
    python -m finanzas_etl --sin-anonimizar  # solo para validar en local
    python -m finanzas_etl --muestra 50000   # ejecucion rapida de verificacion
"""

from __future__ import annotations

import argparse
import logging
import sys
import time

from . import pipeline
from .config import cargar_config
from .logging_setup import configurar
from .quality import checks as qc
from .quality.fugas import auditar, valores_sensibles_del_mapa


def construir_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="finanzas-etl",
        description="Extrae el detalle de costes del libro Excel y construye el modelo estrella.",
    )
    p.add_argument(
        "--sin-anonimizar",
        action="store_true",
        help="omite la pseudonimizacion. Las salidas NO son publicables.",
    )
    p.add_argument(
        "--destino",
        help="carpeta donde escribir los Parquet (por defecto data/processed)",
    )
    p.add_argument("-v", "--verbose", action="store_true", help="registro en nivel DEBUG")
    return p


def main(argv: list[str] | None = None) -> int:
    args = construir_parser().parse_args(argv)
    cfg = cargar_config(requiere_anonimizacion=not args.sin_anonimizar)
    log = configurar(
        logging.DEBUG if args.verbose else logging.INFO,
        fichero=cfg.rutas.reportes / "etl.log",
    )

    if args.sin_anonimizar:
        log.warning("ejecucion SIN anonimizar: las salidas contienen cifras reales")

    inicio = time.perf_counter()
    try:
        salida = pipeline.ejecutar(cfg, anonimizar=not args.sin_anonimizar)
    except RuntimeError as exc:
        log.error("el pipeline se detuvo sin escribir salidas:\n%s", exc)
        return 1

    destino = cfg.rutas.procesado if args.destino is None else cfg.rutas.raiz / args.destino
    salida.escribir_parquet(destino)

    # Auditoria adversaria: se ejecuta sobre los ficheros ya escritos, porque
    # lo que importa es lo que se va a publicar, no lo que hubo en memoria.
    if not args.sin_anonimizar:
        mapa = destino / "_mapa_reversion.csv"
        fugas = auditar(destino, valores_sensibles_del_mapa(mapa), maximo_por_dominio=600)
        salida.calidad.agregar(
            qc.Control(
                nombre="Auditoria de fuga de datos en las salidas",
                aprobado=not fugas,
                severidad=qc.Severidad.BLOQUEANTE,
                detalle=(
                    "ningun valor sensible del origen aparece en los Parquet publicables"
                    if not fugas
                    else "; ".join(str(f) for f in fugas[:5])
                ),
                metricas={"fugas": float(len(fugas))},
            )
        )

    salida.calidad.guardar(
        cfg.rutas.reportes / "calidad_datos.md",
        titulo="Informe de calidad y reconciliacion",
    )

    if salida.calidad.bloqueantes:
        log.error(
            "se escribieron las salidas pero %d controles bloqueantes fallaron: "
            "revisar reports/calidad_datos.md antes de publicar",
            len(salida.calidad.bloqueantes),
        )
        return 2

    log.info("ETL completado en %.1f s", time.perf_counter() - inicio)
    return 0


if __name__ == "__main__":
    sys.exit(main())

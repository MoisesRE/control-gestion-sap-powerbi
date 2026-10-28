"""Auditoria adversaria de todo lo que se publica como texto.

La auditoria del ETL recorre los Parquet. Queda fuera de su alcance todo lo que
se escribe a mano y acaba igualmente en el repositorio: las descripciones del
modelo, los titulos de los visuales, las selecciones de los segmentadores, los
comentarios del codigo, los ejemplos de los tests y la propia documentacion.

Un nombre real escrito en cualquiera de esos sitios se publica igual que si
estuviera en una tabla, y ningun control del pipeline lo ve. La primera
ejecucion de este script encontro dieciocho, repartidos entre el nombre de un
tema, dos comentarios del modelo, el README y los datos de prueba de dos
ficheros de test: ninguno estaba en los datos.

Comprueba ademas el origen de cada particion del modelo: una consulta que
apuntase fuera de los esquemas auditados traeria datos que no pasaron por la
anonimizacion.

Se ejecuta aparte del ETL y no dentro, porque estas superficies cambian sin que
el pipeline vuelva a correr: editar una descripcion en Power BI Desktop o
redactar un parrafo del README no reejecuta nada, y es justo entonces cuando
conviene comprobarlo.

    python scripts/auditar_powerbi.py

Devuelve 1 si encuentra algo, para poder encadenarlo antes de publicar.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from finanzas_etl.config import cargar_config  # noqa: E402
from finanzas_etl.logging_setup import configurar, logger  # noqa: E402
from finanzas_etl.quality.fugas import (  # noqa: E402
    auditar_importes,
    auditar_origenes,
    auditar_texto,
    ficheros_publicables,
    importes_oficiales_reales,
    superficies_sin_auditar,
    valores_sensibles_del_mapa,
)

RAIZ = Path(__file__).resolve().parents[1]
PBIP = RAIZ / "powerbi"
MODELO = PBIP / "ResultadoFinanciero.SemanticModel"
MAPA = RAIZ / "data" / "processed" / "_mapa_reversion.csv"
PATRON = RAIZ / "data" / "processed" / "control_reconciliacion.parquet"

log = logger("auditar_publicable")


def main() -> int:
    configurar()

    if not PBIP.is_dir():
        log.error("no existe %s: no hay informe que auditar", PBIP)
        return 1
    if not MAPA.is_file():
        log.error(
            "falta %s. El mapa de reversion es la lista exhaustiva de lo que se "
            "pseudonimizo, y sin el la auditoria no tiene contra que comparar: "
            "ejecutar primero el ETL.",
            MAPA,
        )
        return 1
    if not PATRON.is_file():
        log.error(
            "falta %s. Es el patron oficial, del que se derivan los importes reales "
            "deshaciendo el escalado: ejecutar primero el ETL.",
            PATRON,
        )
        return 1

    sensibles = valores_sensibles_del_mapa(MAPA)
    ficheros = ficheros_publicables(
        PBIP, RAIZ / "src", RAIZ / "tests", RAIZ / "sql", RAIZ / "scripts",
        RAIZ / "docs", RAIZ / "reports", RAIZ / "README.md",
        RAIZ / "pyproject.toml", RAIZ / ".gitignore", RAIZ / ".env.example",
        # Marcador vacio que le dice a GitHub Pages que sirva la carpeta tal
        # cual, sin pasarla por Jekyll. Se nombra aqui porque un fichero que
        # empieza por punto no tiene sufijo y no lo recoge el recorrido; se
        # audita igual, aunque hoy este vacio, para que el cruce con git no
        # tenga excepciones que nadie recuerde por que estan.
        RAIZ / "docs" / ".nojekyll",
    )

    # El dominio de documentos tiene casi doscientos mil valores y ninguno llega
    # al modelo -- documento_id no se importa --, pero se comprueba igual una
    # muestra: el control no debe depender de que la decision de hoy siga siendo
    # la de manana. Los demas dominios se recorren enteros, y son los que
    # importan: ahi estan los nombres de centro y la marca comercial.
    fugas = auditar_texto(ficheros, sensibles, maximo_por_dominio=2000)

    # Los importes no se pseudonimizan, se escalan: no estan en el mapa y la
    # auditoria de literales no podia verlos. Se derivan del patron oficial
    # deshaciendo el factor. Ver el bloque de importes en quality/fugas.py.
    factor = cargar_config().anonimizacion.factor_importe
    fugas_importe = auditar_importes(ficheros, importes_oficiales_reales(PATRON, factor))

    origenes = auditar_origenes(MODELO)

    # Y antes de dar el visto bueno: comprobar que la lista de arriba no se ha
    # quedado corta. Las raices se escriben a mano y por eso se quedan cortas
    # solas, sin que nada avise; este control le pregunta a git que ficheros
    # subiria y exige que todos esten cubiertos.
    sin_auditar = superficies_sin_auditar(RAIZ, ficheros)

    if fugas or fugas_importe or origenes or sin_auditar:
        log.error(
            "AUDITORIA FALLIDA: %d valores sensibles en el texto, %d importes "
            "reales sin escalar, %d origenes fuera de los esquemas auditados y "
            "%d ficheros publicables que la auditoria no mira. No publicar.",
            len(fugas),
            len(fugas_importe),
            len(origenes),
            len(sin_auditar),
        )
        for ruta in sin_auditar:
            log.error(
                "sin auditar: %s. Anadir su carpeta a las raices de este script "
                "o su extension a SUFIJOS_PUBLICABLES.",
                ruta,
            )
        return 1

    log.info("auditoria superada: lo publicable no contiene valores del origen")
    return 0


if __name__ == "__main__":
    sys.exit(main())

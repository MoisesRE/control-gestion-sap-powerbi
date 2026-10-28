"""Captura las paginas del informe de Power BI para la galeria publicada.

El PBIP se versiona como texto y eso basta para revisarlo, pero no para
ensenarlo: quien entra en GitHub Pages no tiene Power BI Desktop ni la base, de
modo que sin capturas la capa de BI del proyecto es invisible para todo el que
no clone el repositorio.

Se descarto publicar un `.pbix`, que si se abriria sin la base: lleva los
428.589 apuntes dentro y VertiPaq comprime sus diccionarios, de modo que una
busqueda literal no encuentra en el ni los valores que si contiene. Seria el
unico artefacto publicado que ninguna auditoria puede revisar. Un PNG tampoco
se audita por texto, pero no lleva los datos: solo las cifras ya anonimizadas
que el modelo muestra, y el modelo si esta auditado.

    python scripts/capturar_informe.py

Requisitos, y los dos fallan con mensaje en vez de producir imagenes mudas:

1. Power BI Desktop abierto con `powerbi/ResultadoFinanciero.pbip`.
2. **El modelo refrescado.** Desktop abre el proyecto sin datos, y las
   capturas salen con los visuales vacios y un aviso arriba. La primera vez
   que se hizo esto salieron las cinco en blanco y parecian correctas en el
   listado de ficheros: solo mirarlas lo delato.

Lo que este script no puede comprobar es que la imagen tenga datos dentro: eso
exigiria leer los pixeles, y un umbral sobre el tamano del PNG seria un numero
ajustado a lo que se observo una vez. Lo que si comprueba es que no falte
ninguna pagina de las declaradas en `pages.json`, de modo que anadir una pagina
al informe y olvidar recapturar hace fallar la ejecucion.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import unicodedata
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from finanzas_etl.logging_setup import configurar, logger  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]
INFORME = RAIZ / "powerbi" / "ResultadoFinanciero.Report"
PAGINAS = INFORME / "definition" / "pages"
DESTINO = RAIZ / "docs" / "capturas"
INDICE = DESTINO / "indice.json"
CLI = "powerbi-report-author"

log = logger("capturar_informe")


def sanear(nombre: str) -> str:
    """`Ejecucion presupuestaria` -> `ejecucion-presupuestaria`.

    El CLI nombra cada PNG con el titulo de la pagina, espacios incluidos. Una
    URL con espacios funciona escapada, pero ensucia el enlace y depende de que
    cada cliente la escape igual: se renombran a algo que no haya que escapar.
    """
    plano = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode()
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", plano.lower())).strip("-")


def paginas_declaradas() -> list[dict]:
    """Las paginas del informe, en el orden en que el informe las presenta."""
    orden = json.loads((PAGINAS / "pages.json").read_text(encoding="utf-8"))["pageOrder"]
    declaradas = []
    for identificador in orden:
        definicion = json.loads(
            (PAGINAS / identificador / "page.json").read_text(encoding="utf-8")
        )
        declaradas.append({
            "id": identificador,
            "nombre": definicion.get("displayName", identificador),
            "oculta": definicion.get("visibility", "Always") != "Always",
        })
    return declaradas


def capturar() -> list[dict]:
    DESTINO.mkdir(parents=True, exist_ok=True)
    for viejo in DESTINO.glob("*.png"):
        viejo.unlink()

    # `shutil.which` y no el nombre a secas: npm instala el CLI en Windows como
    # un shim `.cmd`, y `subprocess` sin shell no resuelve la extension.
    ejecutable = shutil.which(CLI)
    if ejecutable is None:
        log.error(
            "no se encuentra %s en el PATH. Se instala con:\n"
            "  npm install -g powerbi-report-author",
            CLI,
        )
        raise SystemExit(1)

    proceso = subprocess.run(
        [
            ejecutable, "preview", str(INFORME), "--host", "desktop", "--headless",
            "--screenshot", str(DESTINO), "--all-pages", "--scale", "2",
        ],
        capture_output=True,
        text=True,
        cwd=RAIZ,
    )
    if proceso.returncode != 0:
        log.error(
            "el CLI fallo. Si dice que no encuentra una instancia de Desktop, abrir "
            "antes el proyecto:\n  start powerbi/ResultadoFinanciero.pbip\n%s",
            (proceso.stderr or proceso.stdout).strip(),
        )
        raise SystemExit(1)

    salida = json.loads(proceso.stdout)["data"]
    if not salida.get("ok") or salida.get("failures"):
        log.error("el CLI no capturo todas las paginas: %s", salida.get("failures"))
        raise SystemExit(1)
    return salida["screenshots"]


def main() -> int:
    configurar()
    if not (PAGINAS / "pages.json").is_file():
        log.error("no existe %s: no hay informe que capturar", PAGINAS / "pages.json")
        return 1

    capturadas = {c["pageDisplayName"]: Path(c["path"]) for c in capturar()}

    indice = []
    faltan = []
    for pagina in paginas_declaradas():
        origen = capturadas.get(pagina["nombre"])
        if origen is None or not origen.is_file():
            faltan.append(pagina["nombre"])
            continue
        fichero = f"{sanear(pagina['nombre'])}.png"
        origen.replace(DESTINO / fichero)
        indice.append({
            "fichero": fichero,
            "nombre": pagina["nombre"],
            "oculta": pagina["oculta"],
        })

    if faltan:
        log.error(
            "faltan capturas de %d paginas declaradas en pages.json: %s",
            len(faltan),
            ", ".join(faltan),
        )
        return 1

    documento = {
        "capturado_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "paginas": indice,
    }
    INDICE.write_text(
        json.dumps(documento, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    total = sum((DESTINO / p["fichero"]).stat().st_size for p in indice)
    log.info(
        "%d paginas capturadas en %s (%.1f MB). Mirarlas antes de publicar: un "
        "modelo sin refrescar produce imagenes vacias que este script no detecta.",
        len(indice),
        DESTINO.relative_to(RAIZ),
        total / 1024 / 1024,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

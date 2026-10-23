"""Deshace lo que Power BI Desktop le hace al PBIP al abrirlo o guardarlo.

Desktop trata el proyecto como suyo y reescribe dos cosas que importan en un
repositorio:

1. **Le quita el `$schema` al `.pbip` y al `definition.pbir`.** Los dos ficheros
   siguen siendo JSON valido, pero `powerbi-report-author validate` los rechaza
   y Fabric tambien: sin `$schema` no hay forma de validar la definicion contra
   su contrato.

2. **Renombra la base del modelo con el GUID de su sesion.** El `database.tmdl`
   pasa de `database ResultadoFinanciero` a `database 71bc8c31-4e0f-...`, que no
   dice nada a quien lee el repositorio y cambia en cada sesion, de modo que el
   diff se llena de ruido.

Ninguna de las dos cosas rompe el informe, y por eso es facil que se cuelen en
un commit. Este script las deshace sin tocar nada mas: lee cada fichero, corrige
lo justo y lo vuelve a escribir.

    python scripts/normalizar_pbip.py

Devuelve 0 aunque no haya nada que corregir, para poder encadenarlo.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
PBIP = RAIZ / "powerbi"
NOMBRE = "ResultadoFinanciero"

# El $schema de cada fichero, por familia. No se inventan: son los que escribe
# `powerbi-report-author scaffold`, que los resuelve del catalogo publico.
ESQUEMAS = {
    PBIP / f"{NOMBRE}.pbip": (
        "https://developer.microsoft.com/json-schemas/fabric/pbip/pbipProperties/1.0.0/schema.json"
    ),
    PBIP / f"{NOMBRE}.Report" / "definition.pbir": (
        "https://developer.microsoft.com/json-schemas/fabric/item/report/"
        "definitionProperties/2.0.0/schema.json"
    ),
}

BASE_TMDL = PBIP / f"{NOMBRE}.SemanticModel" / "definition" / "database.tmdl"
GUID = re.compile(r"^database [0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.M)


def restaurar_esquemas() -> list[str]:
    """Devuelve el $schema al principio de cada fichero que lo haya perdido."""
    corregidos = []
    for ruta, esquema in ESQUEMAS.items():
        if not ruta.exists():
            continue
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        if datos.get("$schema") == esquema:
            continue
        # La clave va primera: es donde la escribe el scaffold y donde se espera.
        ruta.write_text(
            json.dumps({"$schema": esquema, **datos}, indent=2) + "\n", encoding="utf-8"
        )
        corregidos.append(ruta.name)
    return corregidos


def restaurar_nombre_de_la_base() -> bool:
    """Devuelve el nombre del proyecto a database.tmdl si Desktop puso su GUID."""
    if not BASE_TMDL.exists():
        return False
    texto = BASE_TMDL.read_text(encoding="utf-8")
    nuevo, sustituciones = GUID.subn(f"database {NOMBRE}", texto)
    if not sustituciones:
        return False
    BASE_TMDL.write_text(nuevo, encoding="utf-8")
    return True


def main() -> int:
    esquemas = restaurar_esquemas()
    base = restaurar_nombre_de_la_base()

    for nombre in esquemas:
        print(f"$schema restaurado en {nombre}")
    if base:
        print(f"nombre de la base restaurado a {NOMBRE} en database.tmdl")
    if not esquemas and not base:
        print("el PBIP ya estaba normalizado")
    return 0


if __name__ == "__main__":
    sys.exit(main())

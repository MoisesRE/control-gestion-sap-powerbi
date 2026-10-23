"""Genera docs/diccionario_sql.md desde el catalogo de PostgreSQL.

La documentacion de la capa SQL no se escribe aqui: se escribe en los
`COMMENT ON` de `sql/02_tablas.sql`, `04_vistas_pl.sql` y `05_vistas_qa.sql`, y
este script la extrae del catalogo. La consecuencia practica es que el
diccionario no puede quedarse desfasado respecto al esquema, porque su unica
fuente es el esquema mismo. Una tabla sin comentario aparece marcada como tal,
de modo que el hueco se ve.
"""

import sys
from pathlib import Path

sys.path.insert(0, "src")

from finanzas_etl.config import ConfigPostgres  # noqa: E402
from finanzas_etl.load.postgres import conectar  # noqa: E402

SIN_COMENTARIO = "_sin comentario_"

CONSULTA_RELACIONES = """
SELECT n.nspname, c.relname, c.relkind, obj_description(c.oid),
       CASE c.relkind WHEN 'r' THEN pg_total_relation_size(c.oid) END,
       CASE c.relkind WHEN 'r' THEN (SELECT count(*) FROM pg_attribute a
            WHERE a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped) END
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = ANY(%s) AND c.relkind IN ('r', 'v')
ORDER BY n.nspname, c.relkind DESC, c.relname
"""

CONSULTA_COLUMNAS = """
SELECT a.attname, format_type(a.atttypid, a.atttypmod), a.attnotnull,
       col_description(a.attrelid, a.attnum)
FROM pg_attribute a
WHERE a.attrelid = %s::regclass AND a.attnum > 0 AND NOT a.attisdropped
ORDER BY a.attnum
"""

CONSULTA_RESTRICCIONES = """
SELECT conname, pg_get_constraintdef(oid)
FROM pg_constraint WHERE conrelid = %s::regclass ORDER BY contype, conname
"""


def escapar(texto: str | None) -> str:
    return (texto or SIN_COMENTARIO).replace("|", "\\|").replace("\n", " ")


def main() -> int:
    cn = conectar(ConfigPostgres.desde_entorno())
    cur = cn.cursor()

    lineas = [
        "# Diccionario de la capa SQL",
        "",
        "Generado desde el catalogo de PostgreSQL por",
        "`scripts/generar_diccionario_sql.py`. No editar a mano: la fuente son los",
        "`COMMENT ON` de los ficheros de `sql/`.",
        "",
    ]

    cur.execute(CONSULTA_RELACIONES, (["core", "pl", "qa"],))
    relaciones = cur.fetchall()
    tablas = [r for r in relaciones if r[2] == "r"]
    vistas = [r for r in relaciones if r[2] == "v"]

    lineas += [
        "## Resumen",
        "",
        f"{len(tablas)} tablas y {len(vistas)} vistas en tres esquemas.",
        "",
        "| Objeto | Tipo | Tamano | Descripcion |",
        "| --- | --- | --- | --- |",
    ]
    for esquema, nombre, clase, comentario, tamano, _ in relaciones:
        tipo = "tabla" if clase == "r" else "vista"
        peso = f"{tamano / 1024**2:.1f} MB" if tamano else "-"
        resumen = escapar(comentario).split(". ")[0]
        lineas.append(f"| `{esquema}.{nombre}` | {tipo} | {peso} | {resumen} |")

    for esquema, nombre, clase, comentario, _, _ in relaciones:
        referencia = f"{esquema}.{nombre}"
        lineas += ["", f"## `{referencia}`", "", escapar(comentario), ""]

        cur.execute(CONSULTA_COLUMNAS, (referencia,))
        lineas += [
            "| Columna | Tipo | Obligatoria | Descripcion |",
            "| --- | --- | --- | --- |",
        ]
        for columna, tipo, obligatoria, nota in cur.fetchall():
            marca = "si" if obligatoria else "no"
            lineas.append(f"| `{columna}` | {tipo} | {marca} | {escapar(nota)} |")

        if clase == "r":
            cur.execute(CONSULTA_RESTRICCIONES, (referencia,))
            restricciones = cur.fetchall()
            if restricciones:
                lineas += ["", "Restricciones:", ""]
                lineas += [f"* `{n}` — `{d}`" for n, d in restricciones]

    cn.close()
    destino = Path("docs/diccionario_sql.md")
    destino.parent.mkdir(exist_ok=True)
    destino.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    print(f"escrito {destino}: {len(tablas)} tablas, {len(vistas)} vistas")
    return 0


if __name__ == "__main__":
    sys.exit(main())

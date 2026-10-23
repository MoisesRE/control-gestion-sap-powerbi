"""Genera docs/diccionario_datos.md desde el contrato de columnas."""
import sys

sys.path.insert(0, 'src')
from pathlib import Path

import pandas as pd

from finanzas_etl.transform.schema import COLUMNAS_PRESUPUESTO, COLUMNAS_REAL, DESCARTADAS

proc = Path('data/processed')
lineas = [
    "# Diccionario de datos",
    "",
    "Generado desde `src/finanzas_etl/transform/schema.py`. No editar a mano.",
    "",
    "## Trazabilidad de columnas: extracto SAP -> modelo analitico",
    "",
    "| Origen (extracto) | Destino (modelo) | Tipo | Tratamiento |",
    "| --- | --- | --- | --- |",
]
for c in COLUMNAS_REAL:
    nota = f" - {c.nota}" if c.nota else ""
    lineas.append(
        f"| `{c.origen}` | `{c.destino}` | {c.tipo} | {c.sensibilidad.value}{nota} |"
    )

lineas += ["", "## Columnas descartadas y motivo", "",
           "| Columna del extracto | Motivo |", "| --- | --- |"]
for col, motivo in DESCARTADAS.items():
    lineas.append(f"| `{col}` | {motivo} |")

lineas += ["", "## Presupuesto (formato ancho despivotado)", "",
           "Las hojas `BD_PPTO25` y `BD_PPTO26` comparten estructura: una fila por",
           "centro, cuenta y concepto, y doce columnas de importe que el ETL transpone.",
           "", "| Origen | Destino | Tratamiento |", "| --- | --- | --- |"]
for c in COLUMNAS_PRESUPUESTO:
    lineas.append(f"| `{c.origen}` | `{c.destino}` | {c.sensibilidad.value} |")

lineas += ["", "## Escenarios", ""]
esc = pd.read_parquet(proc / 'dim_escenario.parquet')
lineas += ["| Clave | Escenario | Tipo | Ejercicio | Simulado | Periodos |",
           "| --- | --- | --- | --- | --- | --- |"]
for _, r in esc.iterrows():
    lineas.append(
        f"| `{r.escenario_clave}` | {r.escenario} | {r.tipo_escenario} | {r.ejercicio} | "
        f"{'si' if r.es_simulado else 'no'} | {r.periodos_cubiertos} |"
    )

lineas += ["", "## Tablas del modelo", ""]
for ruta in sorted(proc.glob('*.parquet')):
    if ruta.name.startswith('_'):
        continue
    df = pd.read_parquet(ruta)
    mb = ruta.stat().st_size / 1024**2
    lineas += [
        f"### `{ruta.stem}`",
        "",
        f"{len(df):,} filas · {len(df.columns)} columnas · {mb:.2f} MB en Parquet",
        "",
        "| Columna | Tipo | Nulos | Distintos |",
        "| --- | --- | --- | --- |",
    ]
    for col in df.columns:
        lineas.append(
            f"| `{col}` | {df[col].dtype} | {int(df[col].isna().sum()):,} "
            f"| {df[col].nunique():,} |"
        )
    lineas.append("")

Path('docs').mkdir(exist_ok=True)
Path('docs/diccionario_datos.md').write_text("\n".join(lineas), encoding='utf-8')
print('escrito docs/diccionario_datos.md', len(lineas), 'lineas')

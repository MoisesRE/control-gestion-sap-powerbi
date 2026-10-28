# Informe de carga en PostgreSQL

Generado: 2026-10-21 21:54

**23 de 23 controles superados.**

| Control | Resultado | Detalle |
| --- | --- | --- |
| Filas transferidas: core.dim_tiempo | OK | Parquet 24 \| PostgreSQL 24 |
| Nulos preservados: core.dim_tiempo | OK | Parquet 0 \| PostgreSQL 0. Un exceso en la base delataria que COPY interpreto como nulo alguna cadena vacia legitima. |
| Filas transferidas: core.dim_escenario | OK | Parquet 4 \| PostgreSQL 4 |
| Nulos preservados: core.dim_escenario | OK | Parquet 0 \| PostgreSQL 0. Un exceso en la base delataria que COPY interpreto como nulo alguna cadena vacia legitima. |
| Filas transferidas: core.dim_centro | OK | Parquet 88 \| PostgreSQL 88 |
| Nulos preservados: core.dim_centro | OK | Parquet 8 \| PostgreSQL 8. Un exceso en la base delataria que COPY interpreto como nulo alguna cadena vacia legitima. |
| Filas transferidas: core.dim_cuenta | OK | Parquet 152 \| PostgreSQL 152 |
| Nulos preservados: core.dim_cuenta | OK | Parquet 12 \| PostgreSQL 12. Un exceso en la base delataria que COPY interpreto como nulo alguna cadena vacia legitima. |
| Filas transferidas: core.fact_escenario | OK | Parquet 42,017 \| PostgreSQL 42,017 |
| Importe exacto: core.fact_escenario.importe | OK | Parquet 25,904,337.78 \| PostgreSQL 25,904,337.78 \| delta 0.00 (se exige igualdad exacta) |
| Nulos preservados: core.fact_escenario | OK | Parquet 0 \| PostgreSQL 0. Un exceso en la base delataria que COPY interpreto como nulo alguna cadena vacia legitima. |
| Filas transferidas: core.fact_resultado | OK | Parquet 428,589 \| PostgreSQL 428,589 |
| Importe exacto: core.fact_resultado.importe | OK | Parquet 2,390,986.16 \| PostgreSQL 2,390,986.16 \| delta 0.00 (se exige igualdad exacta) |
| Nulos preservados: core.fact_resultado | OK | Parquet 45,088 \| PostgreSQL 45,088. Un exceso en la base delataria que COPY interpreto como nulo alguna cadena vacia legitima. |
| Filas transferidas: qa.control_reconciliacion | OK | Parquet 36 \| PostgreSQL 36 |
| Importe exacto: qa.control_reconciliacion.ingresos_oficiales | OK | Parquet 223,632,273.78 \| PostgreSQL 223,632,273.78 \| delta 0.00 (se exige igualdad exacta) |
| Nulos preservados: qa.control_reconciliacion | OK | Parquet 0 \| PostgreSQL 0. Un exceso en la base delataria que COPY interpreto como nulo alguna cadena vacia legitima. |
| Control del esquema: qa.v_control_cobertura_periodos | OK | sin descuadres |
| Control del esquema: qa.v_control_cuadre_hechos | OK | sin descuadres |
| Control del esquema: qa.v_control_ejercicio_coherente | OK | sin descuadres |
| Control del esquema: qa.v_control_orden_pl | OK | sin descuadres |
| Control del esquema: qa.v_control_perimetro_ingresos | OK | sin descuadres |
| Control del esquema: qa.v_control_reconciliacion_ingresos | OK | sin descuadres |

## Metricas

### Filas transferidas: core.dim_tiempo

- `filas_parquet`: 24.0000
- `filas_base`: 24.0000

### Nulos preservados: core.dim_tiempo

- `nulos_parquet`: 0.0000
- `nulos_base`: 0.0000

### Filas transferidas: core.dim_escenario

- `filas_parquet`: 4.0000
- `filas_base`: 4.0000

### Nulos preservados: core.dim_escenario

- `nulos_parquet`: 0.0000
- `nulos_base`: 0.0000

### Filas transferidas: core.dim_centro

- `filas_parquet`: 88.0000
- `filas_base`: 88.0000

### Nulos preservados: core.dim_centro

- `nulos_parquet`: 8.0000
- `nulos_base`: 8.0000

### Filas transferidas: core.dim_cuenta

- `filas_parquet`: 152.0000
- `filas_base`: 152.0000

### Nulos preservados: core.dim_cuenta

- `nulos_parquet`: 12.0000
- `nulos_base`: 12.0000

### Filas transferidas: core.fact_escenario

- `filas_parquet`: 42,017.0000
- `filas_base`: 42,017.0000

### Importe exacto: core.fact_escenario.importe

- `total_parquet`: 25,904,337.7800
- `total_base`: 25,904,337.7800

### Nulos preservados: core.fact_escenario

- `nulos_parquet`: 0.0000
- `nulos_base`: 0.0000

### Filas transferidas: core.fact_resultado

- `filas_parquet`: 428,589.0000
- `filas_base`: 428,589.0000

### Importe exacto: core.fact_resultado.importe

- `total_parquet`: 2,390,986.1600
- `total_base`: 2,390,986.1600

### Nulos preservados: core.fact_resultado

- `nulos_parquet`: 45,088.0000
- `nulos_base`: 45,088.0000

### Filas transferidas: qa.control_reconciliacion

- `filas_parquet`: 36.0000
- `filas_base`: 36.0000

### Importe exacto: qa.control_reconciliacion.ingresos_oficiales

- `total_parquet`: 223,632,273.7800
- `total_base`: 223,632,273.7800

### Nulos preservados: qa.control_reconciliacion

- `nulos_parquet`: 0.0000
- `nulos_base`: 0.0000

### Control del esquema: qa.v_control_cobertura_periodos

- `filas_devueltas`: 0.0000

### Control del esquema: qa.v_control_cuadre_hechos

- `filas_devueltas`: 0.0000

### Control del esquema: qa.v_control_ejercicio_coherente

- `filas_devueltas`: 0.0000

### Control del esquema: qa.v_control_orden_pl

- `filas_devueltas`: 0.0000

### Control del esquema: qa.v_control_perimetro_ingresos

- `filas_devueltas`: 0.0000

### Control del esquema: qa.v_control_reconciliacion_ingresos

- `filas_devueltas`: 0.0000

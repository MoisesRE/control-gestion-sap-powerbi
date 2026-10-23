# Informe de calidad y reconciliacion

Generado: 2026-10-22 10:28

**32 de 32 controles superados.**

| Control | Resultado | Detalle |
| --- | --- | --- |
| Contrato de columnas | OK | 22 columnas esperadas; todas presentes |
| Periodo en el rango 1-12 | OK | periodos presentes: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12] |
| Ejercicios esperados | OK | esperados [2025], hallados [2025] |
| Clave sin nulos: grupo | OK | 0 nulos de 428,589 filas |
| Clave sin nulos: cuenta_codigo | OK | 0 nulos de 428,589 filas |
| Clave sin nulos: ceco_codigo | OK | 0 nulos de 428,589 filas |
| Marca de reverso no afecta a ingresos | OK | 160,573 apuntes marcados (37.5%); importe de ingresos marcados 0.00 |
| Reconciliacion Real 2025 (cifras originales) | OK | 12 periodos comparados; 0 con descuadre; maxima diferencia 0.0000 (tolerancia maxima 0.05) |
| Dimension consistente: ceco_codigo -> ceco_nombre | OK | 0 claves con mas de un ceco_nombre |
| Dimension consistente: cuenta_codigo -> grupo | OK | 0 claves con mas de un grupo |
| Escalado proporcional de importes | OK | factor 1.3742; desvio maximo por apunte 0.005000; desvio agregado 59.66 sobre una cota de 2,142.95 |
| Columna pseudonimizada: ceco_codigo | OK | 84 valores distintos tras el mapeo |
| Columna pseudonimizada: ceco_origen_codigo | OK | 101 valores distintos tras el mapeo |
| Columna pseudonimizada: documento_id | OK | 386,418 valores distintos tras el mapeo |
| El simulado no introduce dimensiones nuevas | OK | 0 centros y 0 cuentas que no existen en el real |
| El volumen mensual del simulado es del orden del real | OK | volumen medio mensual: real 12.18 M vs simulado 12.01 M (razon 0.986; admitido 0,75-1,35) |
| El simulado hereda el perfil mensual del real | OK | el real no tiene estacionalidad apreciable (coef. variacion del volumen 0.0319 < 0.05); correlacion observada 0.899, no exigida |
| La dispersion del simulado es comparable a la del real | OK | coef. variacion del volumen: real 0.0319 vs simulado 0.0787 (razon 2.47; admitido 0,4-3,0) |
| El margen del simulado esta en el rango del real | OK | margen sobre ingresos: real 1.91% vs simulado 9.28% (diferencia 7.37 pp; admitidos 10 pp) |
| El simulado conserva el signo de cada serie | OK | 1 de 1,591 series con suma significativa cambian de signo (0.06%; admitido 0.5%). 114 series de suma nula excluidas |
| Los ingresos simulados son creibles frente al presupuesto | OK | ejecucion 104.8% del presupuesto en los meses 1-10 (admitido 75-125%) |
| El escenario simulado queda marcado como tal | OK | Real 2026 generado para los periodos 1-10 desde 1,749 series del real (semilla 20260131); marcado con es_simulado en dim_escenario |
| Toda linea del P&L tiene orden de presentacion | OK | 0 grupos sin orden asignado |
| Suma invariante tras construccion del detalle | OK | antes 2,390,986.16 \| despues 2,390,986.16 \| delta 0.0000 |
| Coherencia entre el hecho agregado y el detalle | OK | fact_escenario[R2025] 2,390,986.16 vs fact_resultado 2,390,986.16; delta 0.0000 (tolerancia 210.09) |
| Integridad referencial: dim_centro | OK | 0 claves del hecho sin fila en la dimension |
| Integridad referencial: dim_cuenta | OK | 0 claves del hecho sin fila en la dimension |
| Escenarios del hecho y de la dimension coinciden | OK | 4 escenarios con datos |
| Reconciliacion P2025 (modelo final) | OK | 12 periodos comparados; 0 con descuadre; maxima diferencia 0.0100 (tolerancia maxima 0.05) |
| Reconciliacion P2026 (modelo final) | OK | 12 periodos comparados; 0 con descuadre; maxima diferencia 0.0100 (tolerancia maxima 0.05) |
| Reconciliacion R2025 (modelo final) | OK | 12 periodos comparados; 0 con descuadre; maxima diferencia 0.0100 (tolerancia maxima 0.05) |
| Auditoria de fuga de datos en las salidas | OK | ningun valor sensible del origen aparece en los Parquet publicables |

## Metricas

### Marca de reverso no afecta a ingresos

- `apuntes_marcados`: 160,573.0000
- `ingresos_marcados`: 0.0000

### Reconciliacion Real 2025 (cifras originales)

- `periodos_comparados`: 12.0000
- `periodos_descuadrados`: 0.0000
- `maxima_diferencia_absoluta`: 0.0000
- `tolerancia_maxima`: 0.0500

### Dimension consistente: ceco_codigo -> ceco_nombre

- `claves_ambiguas`: 0.0000

### Dimension consistente: cuenta_codigo -> grupo

- `claves_ambiguas`: 0.0000

### Escalado proporcional de importes

- `apuntes`: 428,589.0000
- `suma_original`: 1,739,954.7521
- `suma_escalada`: 2,390,986.1600
- `volumen_bruto_original`: 177,182,050.8358
- `factor`: 1.3742
- `desvio_maximo_por_apunte`: 0.0050
- `desvio_agregado`: 59.6603
- `cota_error_agregado`: 2,142.9450

### El volumen mensual del simulado es del orden del real

- `volumen_real`: 12,183,776.8280
- `volumen_simulado`: 12,013,076.5410
- `razon`: 0.9860

### El simulado hereda el perfil mensual del real

- `correlacion_perfil`: 0.8988
- `cv_volumen_real`: 0.0319

### La dispersion del simulado es comparable a la del real

- `cv_real`: 0.0319
- `cv_simulado`: 0.0787
- `razon`: 2.4673

### El margen del simulado esta en el rango del real

- `margen_real`: 0.0191
- `margen_simulado`: 0.0928
- `diferencia_pp`: 7.3661

### El simulado conserva el signo de cada serie

- `series_discrepantes`: 1.0000
- `proporcion`: 0.0006

### Los ingresos simulados son creibles frente al presupuesto

- `ingresos_simulados`: 61,403,600.4900
- `presupuesto_mismos_meses`: 58,576,280.5051
- `ejecucion`: 1.0483

### El escenario simulado queda marcado como tal

- `series_generadas`: 1,749.0000
- `series_omitidas`: 113.0000
- `semilla`: 20,260,131.0000

### Toda linea del P&L tiene orden de presentacion

- `grupos_sin_orden`: 0.0000

### Coherencia entre el hecho agregado y el detalle

- `agregado`: 2,390,986.1600
- `detalle`: 2,390,986.1600
- `delta`: 0.0000

### Reconciliacion P2025 (modelo final)

- `periodos_comparados`: 12.0000
- `periodos_descuadrados`: 0.0000
- `maxima_diferencia_absoluta`: 0.0100
- `tolerancia_maxima`: 0.0500

### Reconciliacion P2026 (modelo final)

- `periodos_comparados`: 12.0000
- `periodos_descuadrados`: 0.0000
- `maxima_diferencia_absoluta`: 0.0100
- `tolerancia_maxima`: 0.0500

### Reconciliacion R2025 (modelo final)

- `periodos_comparados`: 12.0000
- `periodos_descuadrados`: 0.0000
- `maxima_diferencia_absoluta`: 0.0100
- `tolerancia_maxima`: 0.0500

### Auditoria de fuga de datos en las salidas

- `fugas`: 0.0000

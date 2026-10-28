# Diccionario de la capa SQL

Generado desde el catalogo de PostgreSQL por
`scripts/generar_diccionario_sql.py`. No editar a mano: la fuente son los
`COMMENT ON` de los ficheros de `sql/`.

## Resumen

7 tablas y 13 vistas en tres esquemas.

| Objeto | Tipo | Tamano | Descripcion |
| --- | --- | --- | --- |
| `core.dim_centro` | tabla | 0.0 MB | Centro de coste en su version reasignada por Control de Gestion (CeCo FINAL), que es la que construye el reporte oficial, y no la cruda de SAP |
| `core.dim_cuenta` | tabla | 0.0 MB | Cuenta del plan contable general empresarial peruano, con la jerarquia de presentacion del P&L |
| `core.dim_escenario` | tabla | 0.0 MB | Las cuatro versiones del resultado que el modelo compara |
| `core.dim_tiempo` | tabla | 0.0 MB | Periodo contable, no fecha natural |
| `core.fact_escenario` | tabla | 6.0 MB | Hecho comparativo al grano escenario x centro x cuenta x periodo |
| `core.fact_resultado` | tabla | 73.8 MB | Detalle transaccional del real observado: una fila por apunte contable |
| `pl.v_ejecucion_presupuestaria` | vista | - | Real contra presupuesto del mismo ejercicio, por mes y linea del P&L |
| `pl.v_hechos_escenario` | vista | - | El hecho comparativo con todos los atributos de sus dimensiones resueltos |
| `pl.v_pl_mensual` | vista | - | La cuenta de resultados mes a mes, una fila por escenario, periodo y linea del P&L, en el orden de presentacion del reporte oficial |
| `pl.v_pl_resumen` | vista | - | Ingresos, costes, resultado y margen por escenario y mes, con el acumulado del ejercicio |
| `pl.v_resultado_por_centro` | vista | - | Resultado anual por centro de coste y escenario |
| `pl.v_variacion_interanual` | vista | - | Variacion del real entre ejercicios consecutivos, recortada a los periodos que ambos cubren |
| `qa.v_control_cobertura_periodos` | vista | - | periodos_cubiertos es la columna de la que depende el recorte de la variacion interanual |
| `qa.v_control_cuadre_hechos` | vista | - | El real debe sumar lo mismo en el hecho agregado y en el detalle de apuntes |
| `qa.v_control_ejercicio_coherente` | vista | - | Ninguna fila del escenario R2025 puede llevar un periodo de 2026 |
| `qa.v_control_orden_pl` | vista | - | El centinela 999 marca las lineas sin orden de presentacion asignado, que en el informe caen descolgadas al pie |
| `qa.v_control_perimetro_ingresos` | vista | - | Los ingresos que publica pl.v_pl_resumen contra los que suma el hecho para el grupo Ingresos, mes a mes y sin tolerancia |
| `qa.v_control_reconciliacion_ingresos` | vista | - | Ingresos del modelo contra los de la maqueta de Control de Gestion, mes a mes |
| `qa.v_resumen_carga` | vista | - | Filas e importe total por tabla |
| `qa.control_reconciliacion` | tabla | 0.0 MB | Ingresos mensuales segun la maqueta de Control de Gestion, escalados por el mismo factor que el resto del modelo |

## `core.dim_centro`

Centro de coste en su version reasignada por Control de Gestion (CeCo FINAL), que es la que construye el reporte oficial, y no la cruda de SAP. Los tres atributos de taxonomia se declaran opcionales porque la clasificacion interna no cubre todos los centros: cuatro carecen de estructura y de unidad de negocio. Imponer NOT NULL sobre ambito solo porque hoy esta completo seria declarar una regla que el origen no garantiza.

| Columna | Tipo | Obligatoria | Descripcion |
| --- | --- | --- | --- |
| `ceco_codigo` | text | si | Codigo pseudonimizado del centro. El CHECK del prefijo CC- es la defensa contra cargar por error un extracto sin anonimizar en una base destinada a publicarse. |
| `ceco_nombre` | text | si | Nombre ficticio del centro. El original contenia toponimos de agencias reales. |
| `ambito` | text | no | Taxonomia interna generalizada: ambito del centro. |
| `estructura` | text | no | Taxonomia interna generalizada: estructura organizativa. |
| `unidad_negocio` | text | no | Taxonomia interna generalizada: unidad de negocio. |

Restricciones:

* `dim_centro_codigo_pseudonimizado` — `CHECK ((ceco_codigo ~ '^CC-[0-9]+$'::text))`
* `dim_centro_ceco_codigo_not_null` — `NOT NULL ceco_codigo`
* `dim_centro_ceco_nombre_not_null` — `NOT NULL ceco_nombre`
* `dim_centro_pk` — `PRIMARY KEY (ceco_codigo)`

## `core.dim_cuenta`

Cuenta del plan contable general empresarial peruano, con la jerarquia de presentacion del P&L. Los codigos se conservan en claro porque son un estandar publico que no identifica a la empresa.

| Columna | Tipo | Obligatoria | Descripcion |
| --- | --- | --- | --- |
| `cuenta_codigo` | text | si | Cuenta agrupada por Control de Gestion (Cta Agrupada), no la clase de coste cruda de SAP. |
| `cuenta_nombre` | text | si | Denominacion de la cuenta agrupada. |
| `grupo` | text | si | Una de las 27 agrupaciones en que el reporte oficial presenta el resultado. |
| `clase_costo_gasto` | text | no | Clasificacion COSTO / GASTO del extracto. Opcional: doce cuentas llegan sin ella. |
| `clase_pcge` | text | si | Primer caracter del codigo, que en el plan peruano codifica la naturaleza: 6 gastos por naturaleza, 7 ingresos. Un CHECK impone la derivacion. |
| `es_ingreso` | boolean | si | Verdadero para los grupos de ingreso. Un CHECK lo ata a grupo para que no puedan divergir. |
| `linea_pl` | text | si | Linea en que la cuenta aparece en el P&L. |
| `orden_pl` | smallint | si | Orden de presentacion de arriba abajo. El centinela 999 marca las lineas sin orden asignado, que caerian al pie del informe. |

Restricciones:

* `dim_cuenta_clase_pcge_derivada` — `CHECK ((clase_pcge = "left"(cuenta_codigo, 1)))`
* `dim_cuenta_clase_valida` — `CHECK ((clase_costo_gasto = ANY (ARRAY['COSTO'::text, 'GASTO'::text])))`
* `dim_cuenta_es_ingreso_coherente` — `CHECK ((es_ingreso = (grupo = ANY (ARRAY['Ingresos'::text, 'Ingresos Diversos'::text]))))`
* `dim_cuenta_orden_pl_rango` — `CHECK (((orden_pl >= 10) AND (orden_pl <= 999)))`
* `dim_cuenta_clase_pcge_not_null` — `NOT NULL clase_pcge`
* `dim_cuenta_cuenta_codigo_not_null` — `NOT NULL cuenta_codigo`
* `dim_cuenta_cuenta_nombre_not_null` — `NOT NULL cuenta_nombre`
* `dim_cuenta_es_ingreso_not_null` — `NOT NULL es_ingreso`
* `dim_cuenta_grupo_not_null` — `NOT NULL grupo`
* `dim_cuenta_linea_pl_not_null` — `NOT NULL linea_pl`
* `dim_cuenta_orden_pl_not_null` — `NOT NULL orden_pl`
* `dim_cuenta_pk` — `PRIMARY KEY (cuenta_codigo)`

## `core.dim_escenario`

Las cuatro versiones del resultado que el modelo compara. Tres proceden del libro de Control de Gestion; el real de 2026 esta generado, porque el ejercicio estaba recien abierto cuando se extrajo el origen y no existia un real contra el que contrastar su presupuesto.

| Columna | Tipo | Obligatoria | Descripcion |
| --- | --- | --- | --- |
| `escenario_clave` | text | si | Clave corta: inicial del tipo mas ejercicio, p. ej. "R2025". Un CHECK impone el formato y la coherencia con tipo_escenario y ejercicio. |
| `escenario` | text | si | Etiqueta legible, con la marca "(simulado)" cuando procede. |
| `tipo_escenario` | text | si | Real (resultado observado) o Presupuesto (objetivo aprobado). |
| `ejercicio` | smallint | si | Ejercicio al que corresponde el escenario. |
| `es_simulado` | boolean | si | Verdadero si las cifras estan generadas y no observadas. Es columna del modelo y no nota al pie para que cualquier visual pueda advertirlo y cualquier consulta pueda excluirlo. |
| `periodos_cubiertos` | smallint | si | Periodos con datos. Un ejercicio en curso no cubre los doce, y comparar doce meses contra diez sin tenerlo en cuenta es el error clasico de la variacion interanual. |
| `orden_escenario` | smallint | si | Orden de presentacion en el informe. |

Restricciones:

* `dim_escenario_clave_coherente` — `CHECK ((escenario_clave = ("left"(tipo_escenario, 1) || (ejercicio)::text)))`
* `dim_escenario_clave_formato` — `CHECK ((escenario_clave ~ '^[RP][0-9]{4}$'::text))`
* `dim_escenario_periodos_rango` — `CHECK (((periodos_cubiertos >= 1) AND (periodos_cubiertos <= 12)))`
* `dim_escenario_tipo_valido` — `CHECK ((tipo_escenario = ANY (ARRAY['Real'::text, 'Presupuesto'::text])))`
* `dim_escenario_ejercicio_not_null` — `NOT NULL ejercicio`
* `dim_escenario_es_simulado_not_null` — `NOT NULL es_simulado`
* `dim_escenario_escenario_clave_not_null` — `NOT NULL escenario_clave`
* `dim_escenario_escenario_not_null` — `NOT NULL escenario`
* `dim_escenario_orden_escenario_not_null` — `NOT NULL orden_escenario`
* `dim_escenario_periodos_cubiertos_not_null` — `NOT NULL periodos_cubiertos`
* `dim_escenario_tipo_escenario_not_null` — `NOT NULL tipo_escenario`
* `dim_escenario_pk` — `PRIMARY KEY (escenario_clave)`

## `core.dim_tiempo`

Periodo contable, no fecha natural. El grano es el mes del ejercicio porque es el periodo contable -- y no la fecha del documento -- lo que determina en que mes se reconoce un resultado. El extracto no trae los periodos 13 a 16 de cierre, de modo que el rango valido es 1-12.

| Columna | Tipo | Obligatoria | Descripcion |
| --- | --- | --- | --- |
| `fecha_clave` | integer | si | Clave inteligente ejercicio*100+periodo, p. ej. 202503. Un CHECK impone la derivacion. |
| `ejercicio` | smallint | si | Ejercicio contable de cuatro digitos. |
| `periodo` | smallint | si | Periodo contable 1-12. |
| `mes_nombre` | text | si | Nombre del mes en castellano, para etiquetas de informe. |
| `mes_abrev` | text | si | Abreviatura de tres letras del mes. |
| `trimestre` | smallint | si | Trimestre natural 1-4, derivado del periodo. |
| `etiqueta_trimestre` | text | si | Etiqueta de trimestre con ejercicio, p. ej. "T1 2025". |
| `etiqueta_mes` | text | si | Etiqueta de mes con ejercicio, p. ej. "Mar 2025". |
| `mes_inicio` | date | si | Primer dia natural del periodo. Util para ejes temporales continuos. |
| `mes_fin` | date | si | Ultimo dia natural del periodo. |

Restricciones:

* `dim_tiempo_clave_derivada` — `CHECK ((fecha_clave = ((ejercicio * 100) + periodo)))`
* `dim_tiempo_mes_ordenado` — `CHECK ((mes_fin > mes_inicio))`
* `dim_tiempo_periodo_en_rango` — `CHECK (((periodo >= 1) AND (periodo <= 12)))`
* `dim_tiempo_trimestre_derivado` — `CHECK ((trimestre = (((periodo - 1) / 3) + 1)))`
* `dim_tiempo_trimestre_en_rango` — `CHECK (((trimestre >= 1) AND (trimestre <= 4)))`
* `dim_tiempo_ejercicio_not_null` — `NOT NULL ejercicio`
* `dim_tiempo_etiqueta_mes_not_null` — `NOT NULL etiqueta_mes`
* `dim_tiempo_etiqueta_trimestre_not_null` — `NOT NULL etiqueta_trimestre`
* `dim_tiempo_fecha_clave_not_null` — `NOT NULL fecha_clave`
* `dim_tiempo_mes_abrev_not_null` — `NOT NULL mes_abrev`
* `dim_tiempo_mes_fin_not_null` — `NOT NULL mes_fin`
* `dim_tiempo_mes_inicio_not_null` — `NOT NULL mes_inicio`
* `dim_tiempo_mes_nombre_not_null` — `NOT NULL mes_nombre`
* `dim_tiempo_periodo_not_null` — `NOT NULL periodo`
* `dim_tiempo_trimestre_not_null` — `NOT NULL trimestre`
* `dim_tiempo_pk` — `PRIMARY KEY (fecha_clave)`

## `core.fact_escenario`

Hecho comparativo al grano escenario x centro x cuenta x periodo. Es la tabla que alimenta toda comparacion entre escenarios. La clave primaria no es ceremonia: es el grano declarado como restriccion, de modo que una carga que duplicase una combinacion seria rechazada en vez de inflar el resultado en silencio.

| Columna | Tipo | Obligatoria | Descripcion |
| --- | --- | --- | --- |
| `escenario_clave` | text | si | Escenario al que pertenece la fila. |
| `fecha_clave` | integer | si | Periodo contable. |
| `ejercicio` | smallint | si | Ejercicio, redundante con fecha_clave y atado a ella por un CHECK. Se conserva porque evita un join para el filtro mas frecuente del informe. |
| `periodo` | smallint | si | Periodo 1-12, redundante con fecha_clave por el mismo motivo. |
| `ceco_codigo` | text | si | Centro de coste reasignado. |
| `cuenta_codigo` | text | si | Cuenta agrupada. |
| `importe` | numeric(18,2) | si | Importe en soles con el signo de SAP: ingreso positivo, coste negativo. El convenio hace que el resultado sea la suma directa de la columna, sin condicionales por tipo de linea. |

Restricciones:

* `fact_escenario_clave_derivada` — `CHECK ((fecha_clave = ((ejercicio * 100) + periodo)))`
* `fact_escenario_centro_fk` — `FOREIGN KEY (ceco_codigo) REFERENCES dim_centro(ceco_codigo)`
* `fact_escenario_cuenta_fk` — `FOREIGN KEY (cuenta_codigo) REFERENCES dim_cuenta(cuenta_codigo)`
* `fact_escenario_escenario_fk` — `FOREIGN KEY (escenario_clave) REFERENCES dim_escenario(escenario_clave)`
* `fact_escenario_tiempo_fk` — `FOREIGN KEY (fecha_clave) REFERENCES dim_tiempo(fecha_clave)`
* `fact_escenario_ceco_codigo_not_null` — `NOT NULL ceco_codigo`
* `fact_escenario_cuenta_codigo_not_null` — `NOT NULL cuenta_codigo`
* `fact_escenario_ejercicio_not_null` — `NOT NULL ejercicio`
* `fact_escenario_escenario_clave_not_null` — `NOT NULL escenario_clave`
* `fact_escenario_fecha_clave_not_null` — `NOT NULL fecha_clave`
* `fact_escenario_importe_not_null` — `NOT NULL importe`
* `fact_escenario_periodo_not_null` — `NOT NULL periodo`
* `fact_escenario_pk` — `PRIMARY KEY (escenario_clave, fecha_clave, ceco_codigo, cuenta_codigo)`

## `core.fact_resultado`

Detalle transaccional del real observado: una fila por apunte contable. Existe aparte de fact_escenario porque el real tiene grano de apunte y el presupuesto grano de centro x cuenta x mes: apilarlos obligaria a cada medida a saber de que escenario viene la fila antes de poder sumarla. El real aparece en las dos tablas y qa.v_control_cuadre_hechos comprueba que suman lo mismo.

| Columna | Tipo | Obligatoria | Descripcion |
| --- | --- | --- | --- |
| `apunte_id` | bigint | si | Clave sustituta del apunte. El origen no ofrece ninguna clave natural: el numero de documento se repite entre lineas y falta en 4.698 apuntes. Se regenera en cada carga y, como el orden del Parquet es estable, el mismo apunte recibe el mismo identificador. |
| `escenario_clave` | text | si | Siempre el real observado. La columna existe para que la relacion con dim_escenario este declarada y no solo documentada en prosa. |
| `fecha_clave` | integer | si | Periodo contable del apunte. |
| `ejercicio` | smallint | si | Ejercicio, atado a fecha_clave por un CHECK. |
| `periodo` | smallint | si | Periodo 1-12. |
| `ceco_codigo` | text | si | Centro de coste reasignado por Control de Gestion: la clave de analisis. |
| `cuenta_codigo` | text | si | Cuenta agrupada: la clave de analisis. |
| `importe` | numeric(18,2) | si | Importe del apunte, con el signo de SAP. |
| `fecha_contable` | date | no | Fecha de contabilizacion, que determina el periodo. Nula en 2.455 apuntes. |
| `fecha_documento` | date | no | Fecha del documento origen. Nula en 2.607 apuntes. |
| `origen_tipo` | text | si | Origen del apunte: F.01, Intercompany o Provision ExtraContable. |
| `origen_detalle` | text | si | Desglose del origen: FBL3N, KSB1, Intercompany, Provision CARGO. |
| `transaccion_sap` | text | no | Operacion original: HRP1 nomina, RFBU contabilidad, RMRP logistica, RFT1 tesoreria. |
| `tipo_contrapartida` | text | no | Clase de cuenta de contrapartida: A activo, D deudor, K acreedor, M material. |
| `marca_reverso` | boolean | si | Marca de la columna Documento anulacion del extracto, presente en el 37,5% de los apuntes. Es informativa y NO debe filtrarse: no afecta a ningun apunte de ingresos y el reporte oficial se reproduce sumando todo. Se conserva para que la decision sea auditable en lugar de invisible. |
| `documento_id` | text | no | Numero de documento pseudonimizado. Sin CHECK de formato: el pseudonimo y el original son ambos numericos, de modo que una expresion regular no distinguiria uno de otro y seria un control incapaz de fallar. |
| `ceco_origen_codigo` | text | si | Centro de coste crudo de SAP, antes de la reasignacion. Es atributo y no clave foranea: tiene 101 valores frente a los 88 de la dimension, porque la reasignacion consolida centros. |
| `cuenta_origen_codigo` | text | si | Clase de coste cruda de SAP. Atributo por el mismo motivo: 243 valores frente a los 152 de la dimension. |

Restricciones:

* `fact_resultado_clave_derivada` — `CHECK ((fecha_clave = ((ejercicio * 100) + periodo)))`
* `fact_resultado_origen_pseudonimizado` — `CHECK ((ceco_origen_codigo ~ '^CO-[0-9]+$'::text))`
* `fact_resultado_centro_fk` — `FOREIGN KEY (ceco_codigo) REFERENCES dim_centro(ceco_codigo)`
* `fact_resultado_cuenta_fk` — `FOREIGN KEY (cuenta_codigo) REFERENCES dim_cuenta(cuenta_codigo)`
* `fact_resultado_escenario_fk` — `FOREIGN KEY (escenario_clave) REFERENCES dim_escenario(escenario_clave)`
* `fact_resultado_tiempo_fk` — `FOREIGN KEY (fecha_clave) REFERENCES dim_tiempo(fecha_clave)`
* `fact_resultado_apunte_id_not_null` — `NOT NULL apunte_id`
* `fact_resultado_ceco_codigo_not_null` — `NOT NULL ceco_codigo`
* `fact_resultado_ceco_origen_codigo_not_null` — `NOT NULL ceco_origen_codigo`
* `fact_resultado_cuenta_codigo_not_null` — `NOT NULL cuenta_codigo`
* `fact_resultado_cuenta_origen_codigo_not_null` — `NOT NULL cuenta_origen_codigo`
* `fact_resultado_ejercicio_not_null` — `NOT NULL ejercicio`
* `fact_resultado_escenario_clave_not_null` — `NOT NULL escenario_clave`
* `fact_resultado_fecha_clave_not_null` — `NOT NULL fecha_clave`
* `fact_resultado_importe_not_null` — `NOT NULL importe`
* `fact_resultado_marca_reverso_not_null` — `NOT NULL marca_reverso`
* `fact_resultado_origen_detalle_not_null` — `NOT NULL origen_detalle`
* `fact_resultado_origen_tipo_not_null` — `NOT NULL origen_tipo`
* `fact_resultado_periodo_not_null` — `NOT NULL periodo`
* `fact_resultado_pk` — `PRIMARY KEY (apunte_id)`

## `pl.v_ejecucion_presupuestaria`

Real contra presupuesto del mismo ejercicio, por mes y linea del P&L. El join es FULL y no LEFT a proposito: una linea presupuestada que no llego a ejecutarse, o un gasto ejecutado que nadie presupuesto, son justamente los hallazgos que busca un control de gestion, y un LEFT JOIN haria desaparecer uno de los dos casos sin dejar rastro. Las banderas solo_presupuestado y solo_ejecutado los identifican. es_favorable aprovecha que, con el signo contable, una desviacion positiva es buena tanto si se factura de mas como si se gasta de menos. periodo_comparable marca los meses que el ejercicio real cubre: el de 2026 llega hasta octubre, y sumar su ejecucion contra doce meses de presupuesto daria un 85% de ejecucion inventado en lugar del 104,8% real. Quien agregue esta vista por ejercicio debe filtrar por esa columna.

| Columna | Tipo | Obligatoria | Descripcion |
| --- | --- | --- | --- |
| `ejercicio` | smallint | no | _sin comentario_ |
| `periodo` | smallint | no | _sin comentario_ |
| `orden_pl` | smallint | no | _sin comentario_ |
| `linea_pl` | text | no | _sin comentario_ |
| `es_ingreso` | boolean | no | _sin comentario_ |
| `importe_real` | numeric | no | _sin comentario_ |
| `importe_presupuesto` | numeric | no | _sin comentario_ |
| `desviacion` | numeric | no | _sin comentario_ |
| `es_favorable` | boolean | no | _sin comentario_ |
| `ejecucion_pct` | numeric | no | _sin comentario_ |
| `solo_presupuestado` | boolean | no | _sin comentario_ |
| `solo_ejecutado` | boolean | no | _sin comentario_ |
| `periodo_comparable` | boolean | no | _sin comentario_ |

## `pl.v_hechos_escenario`

El hecho comparativo con todos los atributos de sus dimensiones resueltos. Es la base de las demas vistas y la tabla unica para analisis ad hoc. Los JOIN son internos y no pueden perder filas porque las cuatro claves tienen clave foranea declarada: el descuadre silencioso por clave huerfana, que es el fallo clasico de un modelo en estrella, aqui lo impide el esquema y no una comprobacion posterior.

| Columna | Tipo | Obligatoria | Descripcion |
| --- | --- | --- | --- |
| `escenario_clave` | text | no | _sin comentario_ |
| `escenario` | text | no | _sin comentario_ |
| `tipo_escenario` | text | no | _sin comentario_ |
| `es_simulado` | boolean | no | _sin comentario_ |
| `periodos_cubiertos` | smallint | no | _sin comentario_ |
| `orden_escenario` | smallint | no | _sin comentario_ |
| `fecha_clave` | integer | no | _sin comentario_ |
| `ejercicio` | smallint | no | _sin comentario_ |
| `periodo` | smallint | no | _sin comentario_ |
| `mes_abrev` | text | no | _sin comentario_ |
| `etiqueta_mes` | text | no | _sin comentario_ |
| `trimestre` | smallint | no | _sin comentario_ |
| `etiqueta_trimestre` | text | no | _sin comentario_ |
| `mes_inicio` | date | no | _sin comentario_ |
| `ceco_codigo` | text | no | _sin comentario_ |
| `ceco_nombre` | text | no | _sin comentario_ |
| `ambito` | text | no | _sin comentario_ |
| `estructura` | text | no | _sin comentario_ |
| `unidad_negocio` | text | no | _sin comentario_ |
| `cuenta_codigo` | text | no | _sin comentario_ |
| `cuenta_nombre` | text | no | _sin comentario_ |
| `grupo` | text | no | _sin comentario_ |
| `clase_costo_gasto` | text | no | _sin comentario_ |
| `clase_pcge` | text | no | _sin comentario_ |
| `es_ingreso` | boolean | no | _sin comentario_ |
| `linea_pl` | text | no | _sin comentario_ |
| `orden_pl` | smallint | no | _sin comentario_ |
| `importe` | numeric(18,2) | no | _sin comentario_ |
| `importe_presentacion` | numeric | no | _sin comentario_ |

## `pl.v_pl_mensual`

La cuenta de resultados mes a mes, una fila por escenario, periodo y linea del P&L, en el orden de presentacion del reporte oficial. Es la vista que reproduce la maqueta de Control de Gestion.

| Columna | Tipo | Obligatoria | Descripcion |
| --- | --- | --- | --- |
| `escenario_clave` | text | no | _sin comentario_ |
| `escenario` | text | no | _sin comentario_ |
| `tipo_escenario` | text | no | _sin comentario_ |
| `es_simulado` | boolean | no | _sin comentario_ |
| `orden_escenario` | smallint | no | _sin comentario_ |
| `ejercicio` | smallint | no | _sin comentario_ |
| `periodo` | smallint | no | _sin comentario_ |
| `etiqueta_mes` | text | no | _sin comentario_ |
| `trimestre` | smallint | no | _sin comentario_ |
| `orden_pl` | smallint | no | _sin comentario_ |
| `linea_pl` | text | no | _sin comentario_ |
| `es_ingreso` | boolean | no | _sin comentario_ |
| `importe` | numeric | no | _sin comentario_ |
| `importe_presentacion` | numeric | no | _sin comentario_ |
| `combinaciones` | bigint | no | _sin comentario_ |

## `pl.v_pl_resumen`

Ingresos, costes, resultado y margen por escenario y mes, con el acumulado del ejercicio. Los costes se exponen en positivo porque es como se leen en un informe; resultado sigue siendo la suma de todas las lineas y conserva el signo contable, de modo que no es exactamente ingresos menos costes: la diferencia son los ingresos diversos, que van en su propia columna. La columna ingresos cubre el grupo Ingresos y no es_ingreso, porque es el perimetro de la fila INGRESOS de la maqueta y el unico contra el que el modelo reconcilia; qa.v_control_perimetro_ingresos lo vigila. El margen se divide por nullif(ingresos, 0) para que un mes sin facturacion devuelva nulo en lugar de romper la consulta: un margen indefinido no es un margen del cero por ciento.

| Columna | Tipo | Obligatoria | Descripcion |
| --- | --- | --- | --- |
| `escenario_clave` | text | no | _sin comentario_ |
| `escenario` | text | no | _sin comentario_ |
| `tipo_escenario` | text | no | _sin comentario_ |
| `es_simulado` | boolean | no | _sin comentario_ |
| `orden_escenario` | smallint | no | _sin comentario_ |
| `ejercicio` | smallint | no | _sin comentario_ |
| `periodo` | smallint | no | _sin comentario_ |
| `etiqueta_mes` | text | no | _sin comentario_ |
| `ingresos` | numeric | no | _sin comentario_ |
| `ingresos_diversos` | numeric | no | _sin comentario_ |
| `costes` | numeric | no | _sin comentario_ |
| `resultado` | numeric | no | _sin comentario_ |
| `margen_pct` | numeric | no | _sin comentario_ |
| `ingresos_acumulados` | numeric | no | _sin comentario_ |
| `resultado_acumulado` | numeric | no | _sin comentario_ |

## `pl.v_resultado_por_centro`

Resultado anual por centro de coste y escenario. El margen queda nulo en los centros que no facturan -- mantenimiento, direccion -- y eso es correcto: un centro de solo coste no tiene margen, y asignarle cero lo haria parecer el peor del ranking cuando simplemente no participa en la medida.

| Columna | Tipo | Obligatoria | Descripcion |
| --- | --- | --- | --- |
| `escenario_clave` | text | no | _sin comentario_ |
| `escenario` | text | no | _sin comentario_ |
| `tipo_escenario` | text | no | _sin comentario_ |
| `es_simulado` | boolean | no | _sin comentario_ |
| `ejercicio` | smallint | no | _sin comentario_ |
| `ceco_codigo` | text | no | _sin comentario_ |
| `ceco_nombre` | text | no | _sin comentario_ |
| `ambito` | text | no | _sin comentario_ |
| `estructura` | text | no | _sin comentario_ |
| `unidad_negocio` | text | no | _sin comentario_ |
| `ingresos` | numeric | no | _sin comentario_ |
| `ingresos_diversos` | numeric | no | _sin comentario_ |
| `costes` | numeric | no | _sin comentario_ |
| `resultado` | numeric | no | _sin comentario_ |
| `margen_pct` | numeric | no | _sin comentario_ |

## `pl.v_variacion_interanual`

Variacion del real entre ejercicios consecutivos, recortada a los periodos que ambos cubren. El recorte no es cosmetico: el real de 2026 llega hasta octubre y compararlo contra doce meses de 2025 produciria una caida inventada de dos meses de actividad. El denominador de variacion_pct es el valor absoluto del importe anterior, para que una linea de coste que empeora no aparezca con porcentaje de signo contrario. Las filas con es_simulado provienen del escenario generado.

| Columna | Tipo | Obligatoria | Descripcion |
| --- | --- | --- | --- |
| `ejercicio` | smallint | no | _sin comentario_ |
| `ejercicio_anterior` | smallint | no | _sin comentario_ |
| `periodo` | smallint | no | _sin comentario_ |
| `orden_pl` | smallint | no | _sin comentario_ |
| `linea_pl` | text | no | _sin comentario_ |
| `es_ingreso` | boolean | no | _sin comentario_ |
| `es_simulado` | boolean | no | _sin comentario_ |
| `importe_actual` | numeric | no | _sin comentario_ |
| `importe_anterior` | numeric | no | _sin comentario_ |
| `variacion` | numeric | no | _sin comentario_ |
| `variacion_pct` | numeric | no | _sin comentario_ |

## `qa.v_control_cobertura_periodos`

periodos_cubiertos es la columna de la que depende el recorte de la variacion interanual. Si declarase diez periodos y hubiera datos en doce, o al reves, la comparacion homogenea dejaria de serlo sin que nada fallase. El control ata la declaracion a los datos.

| Columna | Tipo | Obligatoria | Descripcion |
| --- | --- | --- | --- |
| `escenario_clave` | text | no | _sin comentario_ |
| `escenario` | text | no | _sin comentario_ |
| `periodos_declarados` | smallint | no | _sin comentario_ |
| `periodos_con_datos` | bigint | no | _sin comentario_ |

## `qa.v_control_cuadre_hechos`

El real debe sumar lo mismo en el hecho agregado y en el detalle de apuntes. Las dos tablas tienen granos distintos y se construyen por caminos distintos, de modo que coincidir no es trivial. Un descuadre aqui significa que el mismo dato cuenta dos historias segun el visual que lo mire, que es el peor fallo posible en un informe.

| Columna | Tipo | Obligatoria | Descripcion |
| --- | --- | --- | --- |
| `escenario_clave` | text | no | _sin comentario_ |
| `importe_agregado` | numeric | no | _sin comentario_ |
| `importe_detalle` | numeric | no | _sin comentario_ |
| `diferencia` | numeric | no | _sin comentario_ |
| `filas_agregado` | bigint | no | _sin comentario_ |
| `filas_detalle` | bigint | no | _sin comentario_ |
| `tolerancia` | numeric | no | _sin comentario_ |

## `qa.v_control_ejercicio_coherente`

Ninguna fila del escenario R2025 puede llevar un periodo de 2026. Es la unica relacion del modelo que ninguna clave foranea cubre, porque escenario y tiempo son dimensiones independientes y el esquema no sabe que sus ejercicios tienen que coincidir. Un cruce aqui duplicaria importes en la variacion interanual.

| Columna | Tipo | Obligatoria | Descripcion |
| --- | --- | --- | --- |
| `escenario_clave` | text | no | _sin comentario_ |
| `ejercicio_escenario` | smallint | no | _sin comentario_ |
| `ejercicio_periodo` | smallint | no | _sin comentario_ |
| `filas` | bigint | no | _sin comentario_ |
| `importe` | numeric | no | _sin comentario_ |

## `qa.v_control_orden_pl`

El centinela 999 marca las lineas sin orden de presentacion asignado, que en el informe caen descolgadas al pie. El fallo es silencioso -- las cifras son correctas, solo aparecen en el sitio equivocado -- y basta un acento de diferencia entre el literal del extracto y la tabla de orden para provocarlo.

| Columna | Tipo | Obligatoria | Descripcion |
| --- | --- | --- | --- |
| `linea_pl` | text | no | _sin comentario_ |
| `cuentas` | bigint | no | _sin comentario_ |
| `importe_afectado` | numeric | no | _sin comentario_ |

## `qa.v_control_perimetro_ingresos`

Los ingresos que publica pl.v_pl_resumen contra los que suma el hecho para el grupo Ingresos, mes a mes y sin tolerancia. Vigila que la capa de presentacion no se separe del perimetro oficial, que es justo lo que ocurrio una vez: la vista media el margen sobre un perimetro mas amplio que la maqueta y el descuadre no era visible para ningun otro control, porque el de reconciliacion compara el hecho y no la vista.

| Columna | Tipo | Obligatoria | Descripcion |
| --- | --- | --- | --- |
| `escenario_clave` | text | no | _sin comentario_ |
| `periodo` | smallint | no | _sin comentario_ |
| `ingresos_presentacion` | numeric | no | _sin comentario_ |
| `ingresos_almacen` | numeric | no | _sin comentario_ |
| `diferencia` | numeric | no | _sin comentario_ |

## `qa.v_control_reconciliacion_ingresos`

Ingresos del modelo contra los de la maqueta de Control de Gestion, mes a mes. Es el control que importa: un pipeline financiero no se valida porque termine sin error, sino porque sus cifras coinciden con el reporte que la organizacion ya publica. Devuelve una fila por periodo descuadrado.

| Columna | Tipo | Obligatoria | Descripcion |
| --- | --- | --- | --- |
| `escenario_clave` | text | no | _sin comentario_ |
| `periodo` | smallint | no | _sin comentario_ |
| `ingresos_oficiales` | numeric(18,2) | no | _sin comentario_ |
| `ingresos_modelo` | numeric | no | _sin comentario_ |
| `diferencia` | numeric | no | _sin comentario_ |
| `filas_agregadas` | bigint | no | _sin comentario_ |
| `tolerancia` | numeric | no | _sin comentario_ |

## `qa.v_resumen_carga`

Filas e importe total por tabla. Es lo que el cargador compara contra los Parquet de origen para demostrar que la transferencia no perdio ni duplico nada. A diferencia de las vistas v_control_*, siempre devuelve filas.

| Columna | Tipo | Obligatoria | Descripcion |
| --- | --- | --- | --- |
| `tabla` | text | no | _sin comentario_ |
| `filas` | bigint | no | _sin comentario_ |
| `importe_total` | numeric | no | _sin comentario_ |

## `qa.control_reconciliacion`

Ingresos mensuales segun la maqueta de Control de Gestion, escalados por el mismo factor que el resto del modelo. Es la cifra oficial, y tenerla en la base permite repetir la reconciliacion con un SELECT, sin el libro Excel de 165 MB del que procede. Solo contiene los escenarios observados: el real simulado no tiene cifra oficial, y esa ausencia es informacion, no un hueco.

| Columna | Tipo | Obligatoria | Descripcion |
| --- | --- | --- | --- |
| `escenario_clave` | text | si | Escenario observado al que corresponde la cifra. |
| `periodo` | smallint | si | Periodo contable 1-12. |
| `ingresos_oficiales` | numeric(18,2) | si | Ingresos del periodo segun la fila INGRESOS de la hoja DETALLE PL, multiplicados por el factor de anonimizacion. |

Restricciones:

* `control_reconciliacion_periodo_rango` — `CHECK (((periodo >= 1) AND (periodo <= 12)))`
* `control_reconciliacion_escenario_fk` — `FOREIGN KEY (escenario_clave) REFERENCES dim_escenario(escenario_clave)`
* `control_reconciliacion_escenario_clave_not_null` — `NOT NULL escenario_clave`
* `control_reconciliacion_ingresos_oficiales_not_null` — `NOT NULL ingresos_oficiales`
* `control_reconciliacion_periodo_not_null` — `NOT NULL periodo`
* `control_reconciliacion_pk` — `PRIMARY KEY (escenario_clave, periodo)`

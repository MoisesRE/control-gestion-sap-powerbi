# Diccionario de datos

Generado desde `src/finanzas_etl/transform/schema.py`. No editar a mano.

## Trazabilidad de columnas: extracto SAP -> modelo analitico

| Origen (extracto) | Destino (modelo) | Tipo | Tratamiento |
| --- | --- | --- | --- |
| `Ejercicio` | `ejercicio` | int16 | publico |
| `Periodo` | `periodo` | int8 | publico - 1-12; el extracto no trae periodos 13-16 |
| `Fe.contabilizacion` | `fecha_contable` | datetime64[ns] | publico - Fecha que determina el periodo del resultado |
| `Fecha de documento` | `fecha_documento` | datetime64[ns] | publico |
| `Valor/Moneda objeto` | `importe` | float64 | importe - Signo SAP: ingreso positivo, coste negativo |
| `CeCo FINAL` | `ceco_codigo` | string | pseudonimo |
| `Descripcion de CeCo` | `ceco_nombre` | string | nombre_ficticio - Contiene topónimos de agencias reales |
| `Centro de coste` | `ceco_origen_codigo` | string | pseudonimo - CeCo original en SAP, antes de la reasignacion |
| `Cta Agrupada` | `cuenta_codigo` | string | publico - Plan contable general peruano; no identifica a la empresa |
| `NomAgrupador_nuevo` | `cuenta_nombre` | string | publico |
| `Grupo` | `grupo` | string | publico - Agrupacion de 27 lineas del P&L |
| `COSTO O GASTO` | `clase_costo_gasto` | string | publico |
| `Clase de coste` | `cuenta_origen_codigo` | string | publico |
| `Costo y Gasto` | `unidad_negocio` | string | nombre_ficticio |
| `Costo Operativo` | `ambito` | string | nombre_ficticio - Taxonomia interna; se generaliza junto con unidad_negocio |
| `Estructura` | `estructura` | string | nombre_ficticio - Taxonomia interna; se generaliza junto con unidad_negocio |
| `Tipo` | `origen_tipo` | string | publico - F.01 / Intercompany / Provision |
| `Tipo 1` | `origen_detalle` | string | publico |
| `Operacion original` | `transaccion_sap` | string | publico - HRP1 nomina, RFBU contabilidad, RMRP logistica, RFT1 tesoreria |
| `Clase cta. de contrapartida` | `tipo_contrapartida` | string | publico - A activo, D deudor, K acreedor, M material |
| `Documento anulacion` | `marca_reverso` | boolean | publico - Marca informativa; NO excluir (ver quality.checks) |
| `Numero de documento` | `documento_id` | string | pseudonimo |

## Columnas descartadas y motivo

| Columna del extracto | Motivo |
| --- | --- |
| `Usuario` | dato personal: iniciales del empleado que contabilizo |
| `Denominacion cuenta contrapartida` | razon social de proveedores y empleados identificables |
| `Texto de cabecera de documento` | texto libre con nombres de clientes y ubicaciones |
| `Texto de pedido` | texto libre; cobertura 3,3% |
| `Texto breve de material` | texto libre; cobertura 2,2% |
| `Observacion` | texto libre con comentarios internos; cobertura 0,5% |
| `Operacion` | identificador degradado a float por Excel; digitos finales perdidos |
| `Operacion referencia` | identificador degradado a float por Excel |
| `Objeto del interlocutor` | cobertura 0,8%; redundante con Orden partner |
| `Orden partner` | cobertura 1,0% |
| `Documento compras` | cobertura 2,1% |
| `Cta.contrapartida` | identificador de tercero; no se necesita para el resultado |
| `N docum.refer.` | identificador sin uso analitico |
| `Objeto` | duplica Centro de coste |
| `Denom.clase de coste` | duplica la denominacion de la cuenta agrupada |
| `Fecha valor` | se conservan fecha contable y fecha de documento |
| `Fecha entrada` | se conservan fecha contable y fecha de documento |
| `Ud. cantidad contab.` | cobertura 2,7%; el analisis es monetario, no de volumen |
| `Cantidad total reg.` | magnitud no monetaria sin unidad homogenea |
| `Cantidad total` | constante 0 en las 428.589 filas |
| `Tipo de valor` | constante 4 |
| `Sociedad` | constante 1100 |
| `Cuenta UNE y Soporte` | constante UNE CARGO |
| `Unidad de medida` | columna vacia |
| `Intercompany` | columna vacia |
| `Posicion` | numero de linea dentro del documento; sin uso analitico |
| `Segmento` | duplica Centro de coste en el 97% de los casos |
| `Segmento interloc.` | cobertura 2,3% |
| `Tipo 2` | duplica Tipo 1 |
| `Tipo 3` | desglose de Intercompany con cobertura marginal |

## Presupuesto (formato ancho despivotado)

Las hojas `BD_PPTO25` y `BD_PPTO26` comparten estructura: una fila por
centro, cuenta y concepto, y doce columnas de importe que el ETL transpone.

| Origen | Destino | Tratamiento |
| --- | --- | --- |
| `Costo Gasto` | `ambito` | nombre_ficticio |
| `CeCo Tex` | `ceco_nombre` | nombre_ficticio |
| `CeCo` | `ceco_codigo` | pseudonimo |
| `Grupo` | `grupo` | publico |
| `Cuenta Agrup.` | `cuenta_codigo` | publico |
| `CONCEPTOS` | `cuenta_nombre` | publico |

## Escenarios

| Clave | Escenario | Tipo | Ejercicio | Simulado | Periodos |
| --- | --- | --- | --- | --- | --- |
| `P2025` | Presupuesto 2025 | Presupuesto | 2025 | no | 12 |
| `R2025` | Real 2025 | Real | 2025 | no | 12 |
| `P2026` | Presupuesto 2026 | Presupuesto | 2026 | no | 12 |
| `R2026` | Real 2026 (simulado) | Real | 2026 | si | 10 |

## Tablas del modelo

### `control_reconciliacion`

36 filas · 3 columnas · 0.00 MB en Parquet

| Columna | Tipo | Nulos | Distintos |
| --- | --- | --- | --- |
| `escenario_clave` | str | 0 | 3 |
| `periodo` | int64 | 0 | 12 |
| `ingresos_oficiales` | float64 | 0 | 36 |

### `dim_centro`

88 filas · 5 columnas · 0.01 MB en Parquet

| Columna | Tipo | Nulos | Distintos |
| --- | --- | --- | --- |
| `ceco_codigo` | string | 0 | 88 |
| `ceco_nombre` | string | 0 | 88 |
| `ambito` | category | 0 | 4 |
| `estructura` | category | 4 | 2 |
| `unidad_negocio` | category | 4 | 9 |

### `dim_cuenta`

152 filas · 8 columnas · 0.01 MB en Parquet

| Columna | Tipo | Nulos | Distintos |
| --- | --- | --- | --- |
| `cuenta_codigo` | string | 0 | 152 |
| `cuenta_nombre` | string | 0 | 150 |
| `grupo` | category | 0 | 27 |
| `clase_costo_gasto` | category | 12 | 2 |
| `clase_pcge` | category | 0 | 3 |
| `es_ingreso` | bool | 0 | 2 |
| `linea_pl` | category | 0 | 27 |
| `orden_pl` | int16 | 0 | 27 |

### `dim_escenario`

4 filas · 7 columnas · 0.00 MB en Parquet

| Columna | Tipo | Nulos | Distintos |
| --- | --- | --- | --- |
| `escenario_clave` | str | 0 | 4 |
| `escenario` | str | 0 | 4 |
| `tipo_escenario` | str | 0 | 2 |
| `ejercicio` | int64 | 0 | 2 |
| `es_simulado` | bool | 0 | 2 |
| `periodos_cubiertos` | int64 | 0 | 2 |
| `orden_escenario` | int64 | 0 | 4 |

### `dim_tiempo`

24 filas · 10 columnas · 0.01 MB en Parquet

| Columna | Tipo | Nulos | Distintos |
| --- | --- | --- | --- |
| `fecha_clave` | int32 | 0 | 24 |
| `ejercicio` | int64 | 0 | 2 |
| `periodo` | int64 | 0 | 12 |
| `mes_nombre` | str | 0 | 12 |
| `mes_abrev` | str | 0 | 12 |
| `trimestre` | int8 | 0 | 4 |
| `etiqueta_trimestre` | str | 0 | 8 |
| `etiqueta_mes` | str | 0 | 24 |
| `mes_inicio` | datetime64[us] | 0 | 24 |
| `mes_fin` | datetime64[us] | 0 | 24 |

### `fact_escenario`

42,017 filas · 7 columnas · 0.17 MB en Parquet

| Columna | Tipo | Nulos | Distintos |
| --- | --- | --- | --- |
| `escenario_clave` | category | 0 | 4 |
| `fecha_clave` | int32 | 0 | 24 |
| `ejercicio` | int64 | 0 | 2 |
| `periodo` | int64 | 0 | 12 |
| `ceco_codigo` | category | 0 | 88 |
| `cuenta_codigo` | category | 0 | 152 |
| `importe` | float64 | 0 | 18,575 |

### `fact_resultado`

428,589 filas · 17 columnas · 3.10 MB en Parquet

| Columna | Tipo | Nulos | Distintos |
| --- | --- | --- | --- |
| `fecha_clave` | int32 | 0 | 12 |
| `ejercicio` | int16 | 0 | 1 |
| `periodo` | int8 | 0 | 12 |
| `ceco_codigo` | category | 0 | 84 |
| `cuenta_codigo` | category | 0 | 142 |
| `importe` | float64 | 0 | 24,130 |
| `fecha_contable` | datetime64[ns] | 2,455 | 356 |
| `fecha_documento` | datetime64[ns] | 2,607 | 640 |
| `origen_tipo` | category | 0 | 3 |
| `origen_detalle` | category | 0 | 5 |
| `transaccion_sap` | category | 17,670 | 6 |
| `tipo_contrapartida` | category | 17,658 | 5 |
| `marca_reverso` | boolean | 0 | 2 |
| `documento_id` | string | 4,698 | 386,418 |
| `ceco_origen_codigo` | category | 0 | 101 |
| `cuenta_origen_codigo` | category | 0 | 243 |
| `escenario_clave` | category | 0 | 1 |

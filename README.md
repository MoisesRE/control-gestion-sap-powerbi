# Analitica de resultados sobre un extracto de costes SAP CO

Pipeline que convierte un libro Excel de 165 MB —la maqueta mensual de Control
de Gestion de una empresa de transporte de carga— en un modelo analitico
reconciliado, anonimizado y listo para explotar en SQL y Power BI.

El caso es real; las cifras y los nombres publicados no lo son. Ver
[Anonimizacion](#anonimizacion).

**[Ver el dashboard](https://moisesre.github.io/control-gestion-sap-powerbi/)**
— las cifras del modelo y las cinco paginas del informe de Power BI, sin
instalar nada.

## Por que este caso tiene interes tecnico

| Dificultad | Como se resuelve |
| --- | --- |
| Hojas de 919 MB de XML con una formula en cada celda. `pandas.read_excel` no las abre: materializa la hoja completa en memoria antes de construir el DataFrame | Lector incremental propio ([`xlsx_stream.py`](src/finanzas_etl/extract/xlsx_stream.py)) que emite una fila a la vez con memoria constante |
| El extracto trae 54 columnas, varias con datos personales y de terceros | Contrato de columnas explicito ([`schema.py`](src/finanzas_etl/transform/schema.py)): 20 columnas entran, 30 se descartan con el motivo documentado |
| Las cifras tienen que coincidir con el P&L que la organizacion ya publica | Reconciliacion automatica mes a mes contra la maqueta, antes y despues de anonimizar. 12 de 12 periodos cuadran al centimo |
| Publicar datos financieros de un empleador | Pseudonimizacion determinista por HMAC y auditoria adversaria que busca los valores originales en los ficheros de salida |

## Resultado

```
428.589 apuntes contables  ->  3,3 MB de Parquet
 4 escenarios comparables  ->  3 reconciliados contra la maqueta, 1 simulado
 32 controles de calidad   ->  32 superados
 36 periodos reconciliados ->  diferencia maxima 0,01
 48 medidas DAX            ->  reproducen el P&L oficial al centimo
  1 dashboard publicado    ->  ni una sola cifra escrita a mano
          tiempo total     ->  ~125 s en un portatil
```

## Arquitectura

```
Resultado_Financiero.xlsx          30 hojas, 165 MB
  |-- Data 2025        428.589 apuntes reales del ejercicio
  |-- BD_PPTO26         presupuesto 2026 (12 columnas/mes, despivotadas)
  |-- DETALLE PL        patron de reconciliacion: el P&L oficial
Presupuesto 2025.xlsx
  |-- BD_PPTO25         presupuesto 2025, misma estructura
  v
[extract]   lectura incremental del XML
[transform] tipado, fechas seriales de Excel, claves de periodo
[quality]   contrato, dominios, integridad referencial, reconciliacion
[anonymize] pseudonimizacion HMAC + escalado de importes
[simulate]  escenario real 2026 (ene-oct) + controles de verosimilitud
[quality]   auditoria de fuga sobre los ficheros escritos
  v
data/processed/*.parquet           esquema en estrella
  v
[load]      COPY idempotente, todo en una transaccion
PostgreSQL  core: el estrella | pl: el P&L | qa: los controles
  v
[powerbi]   modelo semantico en TMDL + informe en PBIR: todo texto en git
Power BI    8 tablas | 10 relaciones | 48 medidas DAX | 5 paginas
  v
[docs]      cifras generadas desde la base + capturas del informe
GitHub      dashboard sin dependencias | ninguna cifra escrita a mano
```

### Escenarios

| Clave | Escenario | Origen | Naturaleza |
| --- | --- | --- | --- |
| `P2025` | Presupuesto 2025 | `Presupuesto 2025.xlsx` | observado |
| `R2025` | Real 2025 | hoja `Data 2025` | observado |
| `P2026` | Presupuesto 2026 | hoja `BD_PPTO26` | observado |
| `R2026` | Real 2026 (simulado) | generado, periodos 1-10 | **sintetico** |

Habilita las tres comparaciones del reporte: ejecucion presupuestaria de 2025
cerrada, ejecucion de 2026 hasta octubre, y variacion interanual del real.

Lo que cuentan los datos: en 2025 los ingresos reales se quedaron en el **88,6%
del presupuesto**, y el ejercicio cerro con un margen del **3,35%** frente al
10,69% presupuestado. Sobre los diez primeros periodos, que son los unicos
comparables con 2026, ese margen real baja al 1,91% y el presupuestado al
9,96%: son las cifras que usa el control del escenario simulado.

### Esquema en estrella

| Tabla | Filas | Grano |
| --- | --- | --- |
| `fact_escenario` | 42.017 | escenario x centro x cuenta x mes |
| `fact_resultado` | 428.589 | un apunte contable (solo real observado) |
| `dim_escenario` | 4 | escenario, con `es_simulado` |
| `dim_centro` | 88 | centro de coste |
| `dim_cuenta` | 152 | cuenta del plan contable, con la jerarquia del P&L |
| `dim_tiempo` | 24 | periodo contable |

**Dos tablas de hechos, y no una.** El real observado tiene grano de apunte
contable; el presupuesto y el simulado, de centro por cuenta y mes. Apilarlos
mezclaria dos granos, lo que obliga a cada medida a saber de que escenario
viene la fila antes de sumarla. `fact_escenario` alimenta todas las
comparaciones al grano comun y `fact_resultado` guarda el detalle para
trazabilidad y analisis de dispersion. El real aparece en las dos, y un control
comprueba que ambas suman lo mismo al centimo.

## La capa PostgreSQL

El modelo se carga en `finanzas_analytics`, repartido en tres esquemas que
separan el almacen, la presentacion y el diagnostico:

| Esquema | Contiene | Lo consume |
| --- | --- | --- |
| `core` | Las seis tablas del esquema en estrella | El cargador y las vistas |
| `pl` | Seis vistas que reconstruyen la cuenta de resultados | Power BI y el informe |
| `qa` | El patron de reconciliacion y seis vistas de control | La verificacion de la carga |

La separacion tiene una consecuencia concreta. Una vista de PostgreSQL se
ejecuta con los permisos de su propietario, no con los de quien la consulta,
de modo que el rol `bi_reader` lee el P&L entero sin tener un solo permiso
sobre `core`: el detalle de 428.589 apuntes nunca sale de ahi. `bi_reader` es
ademas un rol de grupo sin `LOGIN`, lo que permite versionar los permisos en
`sql/06_permisos.sql` sin versionar ninguna contrasena.

### El esquema impone las reglas, no las documenta

Buena parte de lo que en otros proyectos vive en una bateria de comprobaciones
posteriores aqui esta declarado en el DDL, donde no se puede incumplir:

* **El grano es la clave primaria.** `fact_escenario` tiene `PRIMARY KEY
  (escenario_clave, fecha_clave, ceco_codigo, cuenta_codigo)`. Una carga que
  duplicase una combinacion es rechazada en vez de inflar el resultado.
* **Las cuatro claves de cada hecho tienen `FOREIGN KEY`.** La clave huerfana
  que en Power BI se convierte en una fila en blanco y descuadra los totales
  en silencio no puede llegar a existir.
* **Varios `CHECK` son reglas de negocio**: que `fecha_clave` sea
  `ejercicio*100+periodo`, que `clase_pcge` sea el primer caracter de la
  cuenta, que `es_ingreso` coincida con los grupos de ingreso, que
  `escenario_clave` se derive del tipo y el ejercicio.
* **Un `CHECK` protege la anonimizacion.** `ceco_codigo` debe cumplir
  `^CC-[0-9]+$`. Cargar por error un extracto sin pseudonimizar en una base
  destinada a publicarse falla en la primera fila.

Los importes son `numeric(18,2)` y no `double precision`. La suma en coma
flotante no es asociativa, de modo que el total de una columna dependeria del
orden en que el planificador decidiese agregar las filas: el mismo `SELECT`
podria devolver dos centimos distintos entre ejecuciones.

### Las vistas del P&L

Mediana de siete ejecuciones de extremo a extremo con cache caliente.

| Vista | Filas | Tiempo | Responde a |
| --- | --- | --- | --- |
| `pl.v_hechos_escenario` | 42.017 | 273 ms | el hecho con todas sus dimensiones resueltas |
| `pl.v_pl_mensual` | 1.110 | 182 ms | la cuenta de resultados mes a mes, por linea |
| `pl.v_pl_resumen` | 46 | 46 ms | ingresos, costes, resultado, margen y acumulado |
| `pl.v_ejecucion_presupuestaria` | 611 | 41 ms | real contra presupuesto, con la desviacion |
| `pl.v_variacion_interanual` | 270 | 22 ms | 2026 contra 2025, en periodos comparables |
| `pl.v_resultado_por_centro` | 302 | 101 ms | resultado y margen por centro de coste |

Son vistas y no tablas materializadas: a este volumen, materializar anadiria un
`REFRESH` que orquestar tras cada carga y la posibilidad de servir una version
desincronizada del hecho, a cambio de ahorrar decimas de segundo.

**El convenio de signo hace el trabajo.** Los importes conservan el signo de
SAP, ingreso positivo y coste negativo, lo que convierte tres calculos en sumas
directas. El resultado es `sum(importe)` sin condicionales. La desviacion es
`real - presupuesto`, y es favorable cuando sale positiva **tanto en ingresos
como en costes**: facturar de mas da una diferencia positiva, y gastar de menos
da un numero negativo mas proximo a cero, que tambien es mayor. El unico precio
es que las lineas de coste se muestran en negativo, para lo que cada vista
expone ademas `importe_presentacion`.

**La trampa de la variacion interanual.** El real de 2026 cubre diez periodos y
el de 2025 los doce. Compararlos sin mas inventaria una caida de dos meses de
actividad. `pl.v_variacion_interanual` se recorta al menor numero de periodos
cubiertos entre los escenarios reales, y `pl.v_ejecucion_presupuestaria` marca
cada fila con `periodo_comparable`. Con ese recorte la ejecucion de 2026 es del
**104,8%**; sin el, saldria un 85% que no significa nada.

### Levantar la base desde cero

```bash
python -m finanzas_etl.load              # crea la base, aplica el DDL y carga
python -m finanzas_etl.load --recrear    # borra los esquemas y los rehace
python -m finanzas_etl.load --solo-ddl   # crea el esquema sin cargar datos
```

El DDL son seis ficheros numerados en `sql/`, aplicados en orden lexicografico
y todos idempotentes. Se descarto Alembic o Flyway: aportan migraciones
reversibles e historial de versiones del esquema, que es lo que hace falta
cuando hay datos en produccion que no se pueden perder, y aqui el esquema se
reconstruye entero desde los Parquet en veinte segundos.

La carga vacia y recarga con `TRUNCATE ... RESTART IDENTITY` seguido de `COPY`,
todo en una sola transaccion: o entra el modelo completo o no entra nada, y no
hay ningun instante en que alguien pueda consultar una base a medio cargar.
`RESTART IDENTITY` reinicia la secuencia de `apunte_id`, y como el orden del
Parquet es estable, cada apunte recibe el mismo identificador en todas las
cargas. Comprobado: dos ejecuciones seguidas dejan las 428.589 filas con el
mismo rango de identificadores, la misma suma y el mismo MD5.

### Los 23 controles de la carga

Se escriben en [`reports/calidad_carga.md`](reports/calidad_carga.md).

* **Filas transferidas** y **nulos preservados**, por tabla. El segundo existe
  por el fallo del marcador de nulo que se cuenta mas abajo.
* **Importe exacto**, en las tres tablas con importes. Exige **igualdad
  estricta**, sin tolerancia: el trayecto Parquet -> `numeric` no pierde
  informacion por ningun sitio, de modo que cualquier diferencia seria un fallo
  de transferencia y una tolerancia solo serviria para esconderlo.
* **Las seis vistas `qa.v_control_*`**, que por convenio devuelven cero filas
  cuando el modelo esta sano. El verificador las descubre en el catalogo en
  lugar de listarlas, asi que anadir un control al DDL basta para que se
  ejecute. La sexta se anadio en la etapa 3 y es la prueba de que el mecanismo
  funciona: aparecio en el informe sin tocar una linea de Python.

No hay vista de claves huerfanas, y la ausencia es deliberada: con las claves
foraneas declaradas, una fila huerfana no puede existir, y una vista que las
buscase seria incapaz de devolver una sola fila. Un control que no puede fallar
no es un control.

Las dieciseis pruebas marcadas con `postgres` no comprueban que los controles
pasen con el modelo sano, que es lo facil: **rompen el modelo a proposito** --
alteran un importe, declaran mal los periodos cubiertos, insertan un periodo de
otro ejercicio, devuelven a la vista del P&L el perimetro de ingresos
equivocado -- y comprueban que cada control lo detecta. Todo dentro de una
transaccion que se deshace. Se saltan solas si no hay base disponible.

### Rendimiento y decisiones de indexado

Solo se indexa `fact_resultado`. Mediana de siete ejecuciones; la columna
"secuencial" se obtuvo desactivando los accesos por indice.

| Consulta | Con indice | Secuencial | Gana |
| --- | --- | --- | --- |
| `fact_resultado WHERE ceco_codigo = ...` | 0,10 ms | 38,34 ms | 383x |
| `fact_resultado WHERE cuenta_codigo = ...` | 0,34 ms | 47,75 ms | 140x |
| `fact_resultado WHERE fecha_clave = ...` | 6,54 ms | 40,20 ms | 6x |
| `fact_escenario WHERE cuenta_codigo = ...` | sin indice | 2,74 ms | — |
| `fact_escenario` agregado por escenario | sin indice | 8,92 ms | — |

Las dos ultimas filas son la razon de no indexar `fact_escenario`: con 42.017
filas la consulta ya responde en milisegundos sin ayuda, y un indice solo
anadiria espacio y tiempo de carga. Los tres indices de `fact_resultado` ocupan
18 MB sobre una tabla de 74 MB, un 24% que las cifras de arriba justifican.
Indexar por reflejo todas las claves foraneas de un modelo en estrella es un
habito extendido y casi siempre equivocado.

## La capa Power BI

El informe se versiona en formato **PBIP**: el modelo semantico en TMDL y el
informe en PBIR. Un `.pbix` es un binario que no se puede revisar, comparar ni
fusionar; esto son ficheros de texto donde un cambio de medida se lee en el
diff.

```
powerbi/
  ResultadoFinanciero.pbip
  ResultadoFinanciero.SemanticModel/definition/
      model.tmdl          propiedades del modelo, con la fecha automatica apagada
      expressions.tmdl    los dos parametros de conexion
      relationships.tmdl  las diez relaciones
      tables/*.tmdl       ocho tablas: columnas, formatos, medidas y el M
  ResultadoFinanciero.Report/definition/
      pages/*/page.json   cinco paginas, una oculta
      pages/*/visuals/    treinta y tres visuales
```

### Las tablas de `core`, y no las vistas de `pl`

Import mode sobre las seis tablas del estrella mas `qa.control_reconciliacion`.
Las vistas del P&L no se importan, y el motivo de peso no es el rendimiento:
una vista ya agregada por linea del P&L mata el drill-down a cuenta y a centro,
y obliga a recalcular en DAX lo que el modelo deberia dar solo.

Sobre todo, **las vistas llevan la logica horneada**. Importarlas haria que el
informe heredase sus decisiones sin poder discutirlas, incluido el perimetro de
ingresos que `pl.v_pl_resumen` media mal y que se cuenta en [Lo que salio
mal](#lo-que-salio-mal). Importar el estrella deja el DAX libre y habilita el
contraste que de verdad vale: **la misma cifra calculada en SQL y en DAX por
caminos independientes.** Si coinciden, ninguna de las dos esta mal.

`qa.control_reconciliacion` entra en el modelo para que el informe lleve dentro
su propia prueba de cuadre contra la maqueta oficial, en lugar de remitirla a un
control que el lector del informe no puede ver.

Cada particion trae su SQL enumerando las columnas, en lugar de navegar a la
tabla entera: la proyeccion la hace PostgreSQL, el repositorio deja ver
exactamente que sale de la base, y de `fact_resultado` no llegan `apunte_id` ni
`documento_id`, que con 428.589 valores distintos cada una serian los dos
mayores diccionarios del modelo sin aportar un solo analisis.

**Las columnas `ejercicio` y `periodo` del hecho no se importan**, y es una
decision que invierte la de la capa SQL. Alli son redundantes a proposito,
porque ahorran un join en el filtro mas frecuente. Aqui el filtro llega por la
relacion con la dimension de tiempo, de modo que solo costarian memoria. El
mismo dato merece una decision distinta en cada motor.

### Dos tablas de hechos, y una medida que lo vigila

El modelo conserva la separacion de la capa SQL: `Resultado` con el grano
comparativo (42.017 filas) y `Apuntes` con el detalle del real observado
(428.589). En Power BI esto tiene una consecuencia que no perdona: **una medida
que sume las dos cuenta el real dos veces.**

En vez de confiar en que nadie lo haga, el modelo trae la medida `Cuadre de
Hechos`, que compara lo que suma el detalle con lo que suma el comparativo para
el real observado y debe dar cero. Es `qa.v_control_cuadre_hechos` escrito en
DAX, y vive en la pagina de control donde cualquiera puede verlo.

### Inteligencia temporal escrita a mano

`dim_tiempo` tiene grano mensual y ninguna columna de fecha, de modo que **no es
una tabla de fechas** y la familia `TOTALYTD` / `SAMEPERIODLASTYEAR` no se le
puede aplicar. La alternativa era extenderla a grano diario en SQL. Se descarto
por tres razones, de menor a mayor:

1. Multiplicaria por treinta una dimension que no gana una columna util.
2. **Mentiria sobre el grano del dato.** Lo que determina en que mes se reconoce
   un resultado es el periodo contable, no la fecha del documento.
3. SAP tiene periodos 13 a 16 de cierre que este extracto no trae. Un calendario
   diario **no puede representar un periodo 13**; una dimension de periodos si,
   y admitiria el cierre sin rehacer el modelo.

Y la parte dificil no la resolveria igualmente: la variacion interanual se
recorta a `periodos_cubiertos`, que es atributo del escenario y no del tiempo.
`SAMEPERIODLASTYEAR` no sabe nada de eso y produciria exactamente la caida
inventada de dos meses que esta documentada como trampa. El acumulado y el
interanual se escriben con aritmetica sobre `Ejercicio` y `Periodo`, y el precio
-- mas DAX que mantener -- se paga a cambio de que cada recorte quede a la vista.

### Las 48 medidas

Agrupadas en carpetas, todas con descripcion, repartidas entre la tabla que les
corresponde y no amontonadas en una tabla de medidas.

| Carpeta | Contiene |
| --- | --- |
| `01 Cuenta de resultados` | Ingresos, costes, resultado, margen y las dos variantes de signo |
| `02 Acumulado del ejercicio` | Resultado e ingresos acumulados, sin `TOTALYTD` |
| `03 Ejecucion presupuestaria` | Real, presupuesto recortado, desviacion y ejecucion |
| `04 Variacion interanual` | Ejercicio anterior y variacion, sobre periodos comparables |
| `05 Control y reconciliacion` | Cuadre contra la maqueta y entre las dos tablas de hechos |
| `06 Estado de resultados` | Las 31 lineas del P&L oficial, el mes y el acumulado |
| `07 Formato del P&L` | Colores de fila y semaforos, para el formato condicional |

La paleta, las fuentes y las unidades viven en un **tema del informe**
(`StaticResources/RegisteredResources`), no repetidas visual a visual: cambiar
el azul corporativo es editar un fichero. La pagina de control queda **oculta
en la vista de lectura** -- no retirada: es la prueba de que las cifras cuadran
y quien audite el modelo la necesita.

Tres decisiones que se repiten en todas:

* **`KEEPFILTERS` y no reemplazo** al filtrar el grupo de la cuenta. Con
  reemplazo, una tabla desglosada por linea del P&L repetiria el ingreso total
  en cada fila en lugar de dejarlo solo en la suya.
* **`DIVIDE` y no la barra.** Un mes sin facturacion devuelve vacio en lugar de
  romper el calculo: un margen indefinido no es un margen del cero por ciento.
* **Decimal fijo y no coma flotante** en las columnas de importe, por el mismo
  motivo por el que en PostgreSQL son `numeric(18,2)`: la suma en coma flotante
  no es asociativa y el total dependeria del orden de agregacion. El tipo se
  fija en el M de la particion con `Currency.Type` y no solo en los metadatos de
  la columna, porque el refresco reconcilia el tipo declarado con el que entrega
  el conector y se lo lleva por delante. Costo encontrarlo: ver "Lo que salio
  mal".

El perimetro de ingresos es el grupo `Ingresos` a secas, que es el de la fila
INGRESOS de la maqueta. No incluye `Ingresos Diversos`, que tiene su propia
medida, y por eso `Resultado Neto` no es exactamente `Ingresos` mas `Costes`.

**El modelo lo verifican 22 pruebas.** El TMDL es texto, de modo que
[`tests/test_modelo_semantico.py`](tests/test_modelo_semantico.py) lo parsea y
comprueba sus invariantes sin abrir Power BI, sin conexion a PostgreSQL y sin
refrescar nada: ninguna medida se llama igual que una columna, todas tienen
formato, carpeta y descripcion, las claves foraneas estan ocultas, las columnas
que ordenan a otras siguen disponibles en MDX y la fecha automatica esta
apagada. Existe porque el validador del formato deja pasar todas esas cosas, y
una de ellas impidio abrir el proyecto.

### El escenario generado, y donde se dice

`Real 2026` esta generado, y el modelo lo sabe: `dim_escenario.es_simulado` es
una columna del modelo y no una nota al pie, de modo que cualquier visual puede
filtrarlo o advertirlo y los controles de verosimilitud se apoyan en ella.

**El informe no lo rotula, y es una decision explicita del usuario**: el BI
presenta los cuatro escenarios con el mismo lenguaje. La advertencia vive donde
un lector la busca -- esta memoria tecnica y la seccion [El escenario
simulado](#el-escenario-simulado) -- y no en una etiqueta del informe. Una
version anterior del modelo llevaba una medida `Aviso Escenario Simulado` en una
tarjeta al pie de cada pagina; se retiro al tomar esa decision, y esta linea
existe porque el README siguio describiendola durante una etapa entera.

### Las cinco paginas

| Pagina | Responde a |
| --- | --- |
| Estado de resultados | El P&L con el formato oficial de la empresa: el mes y el acumulado |
| Cuenta de resultados | El P&L por grupo de gasto y mes, con el acumulado del ejercicio |
| Ejecucion presupuestaria | Real contra presupuesto, con el recorte de periodos a la vista |
| Analisis por centro | Ranking, dispersion ingresos-margen y detalle por centro |
| Control y reconciliacion | El cuadre contra la maqueta y entre las dos tablas de hechos |

La cuarta no es relleno: es la pagina que un controller abre primero. Un informe
financiero que no ensena su cuadre pide un acto de fe.

La primera reproduce la plantilla que Control de Gestion ya usa: las 31 lineas
en su orden, el mes a la izquierda y el acumulado del ejercicio a la derecha,
con los subtotales sombreados, los margenes en verde y un semaforo por
variacion. El mapeo de los 27 grupos del extracto a esas lineas **esta
verificado contra el propio libro**: la hoja que consolida la unidad, que es la
que calcula el P&L oficial, agrupa en las mismas secciones, y la separacion
entre coste de ventas y gasto administrativo sale de la clasificacion
COSTO/GASTO de `Maestro Costo Gasto`. Las siete lineas de importe forman una
particion exhaustiva del hecho: su suma es el resultado neto al centimo.

Cada pagina **arranca con un escenario elegido**, no en "Todas": sumar el
presupuesto con el real da una cifra que no significa nada, y un informe no
deberia abrirse ensenandola. La de control es la excepcion, porque alli ver los
cuatro escenarios a la vez es el objetivo.

### La credencial: lectura y nada mas

Power BI se conecta con el rol `powerbi`, que hereda el grupo `bi_modeler`
declarado en [`sql/06_permisos.sql`](sql/06_permisos.sql). Hay dos niveles de
acceso y no uno porque hacen falta los dos: `bi_reader` sirve a quien consume el
P&L y no ve el detalle de apuntes; `bi_modeler` anade la lectura de `core` que
Import mode necesita. Ampliar `bi_reader` habria dado a todos los consumidores
mas acceso del que necesitan.

Ninguno de los dos tiene `LOGIN` ni contrasena, de modo que los permisos se
versionan sin versionar un secreto. El usuario que se autentica se crea fuera
del repositorio. La alternativa comoda -- conectar como `postgres` -- le habria
dado al informe `INSERT`, `UPDATE`, `DELETE` y `TRUNCATE` sobre un modelo que
solo necesita leer.

### La validacion contra el SQL

Que las medidas den una cifra no demuestra nada; que den **la misma cifra que la
capa SQL por un camino independiente**, si. El DAX agrega el estrella en
VertiPaq y el SQL lo agrega en PostgreSQL, de modo que un error de modelado
tendria que repetirse identico en los dos sitios para pasar desapercibido.

[`powerbi/validacion.dax`](powerbi/validacion.dax) son siete consultas con el
valor esperado de cada columna en el comentario, ejecutables en DAX Studio
contra la instancia de Power BI Desktop. Cubren el P&L por escenario, la
identidad del perimetro, el acumulado, la ejecucion presupuestaria, la
variacion interanual, los dos controles de cuadre, y una ultima que lista las
medidas con error y debe salir vacia.

Las cinco primeras exigen **igualdad exacta al centimo**: DAX y SQL recorren las
mismas filas de la misma tabla y ningun paso pierde precision, de modo que una
tolerancia solo serviria para esconder un error de modelado. La sexta compara
contra la maqueta y si lleva tolerancia, derivada del numero de importes
agregados como en la capa SQL.

### Abrir el PBIP

```bash
start powerbi/ResultadoFinanciero.pbip
```

Requiere Power BI Desktop con **PBIP, TMDL y PBIR activados** en Opciones >
Caracteristicas en vista previa. En el primer refresco pide la credencial de
PostgreSQL: usuario `powerbi` y la contrasena de `PGPASSWORD_BI` del `.env`. Si
el conector pide el proveedor Npgsql, hay que instalarlo antes.

## La capa publicada

GitHub Pages sirve la carpeta [`docs/`](docs/) de la rama por defecto, y no una
rama `gh-pages`. El motivo no es la comodidad de no mantener dos ramas: `docs/`
ya es una de las raices que recorre la auditoria de lo publicable, de modo que
el sitio queda dentro del alcance del control **por construccion** y no porque
alguien se acuerde de anadirlo. Una rama aparte habria dejado el fichero mas
publico del repositorio fuera del diff que se revisa.

### El dashboard no contiene ni un importe

[`docs/index.html`](docs/index.html) no tiene una sola cifra escrita. Las lee de
[`docs/cifras.json`](docs/cifras.json), que genera
[`scripts/generar_cifras_web.py`](scripts/generar_cifras_web.py) desde
PostgreSQL.

Escribir las cifras a mano habria sido un fichero menos que mantener, y habria
roto lo que el proyecto entero sostiene: que toda cifra publicada es
reproducible. Una cifra a mano no se reconcilia contra nada y se pudre en
silencio -- el dia que cambie el factor de anonimizacion o el perimetro de una
vista, la pagina seguiria ensenando la cifra vieja sin que ningun control
fallase.

**El generador es ademas una puerta.** Antes de escribir nada ejecuta las
vistas `qa.v_control_*` -- las mismas que verifican la carga, descubiertas en
el catalogo y no listadas en el script -- y se niega a generar el JSON si
alguna devuelve filas. Despues comprueba que la reconciliacion contra la
maqueta siga dentro de su tolerancia. Un dashboard no deberia poder publicarse
desde un modelo descuadrado.

```bash
python scripts/generar_cifras_web.py              # genera docs/cifras.json
python scripts/generar_cifras_web.py --comprobar  # falla si el JSON esta viejo
```

`--comprobar` existe porque el JSON se versiona: compara el fichero del
repositorio contra la base ignorando la marca de tiempo, de modo que un
dashboard que ensene cifras de hace tres cargas falla en lugar de pasar.

Las 27 pruebas de
[`tests/test_cifras_web.py`](tests/test_cifras_web.py) corren **sin base de
datos** y a proposito: fijan el JSON publicado contra la tabla oficial escrita
a mano en el propio test. Una prueba que volviese a consultar PostgreSQL no
podria detectar que el fichero versionado se quedo viejo, porque regeneraria la
respuesta correcta justo antes de comprobarla.

### Sin dependencias externas

La pagina no carga nada de ningun CDN: los graficos son SVG construidos en
JavaScript plano. Una libreria de graficos habria sido menos codigo, pero un
portafolio tiene que seguir funcionando dentro de tres anos, y un `<script src>`
a un CDN es una pieza que puede caducar, cambiar de version o estar bloqueada en
la red desde la que alguien abra la pagina. Ademas no estaria en el repositorio,
de modo que seria la unica parte del sitio que la auditoria no recorre.

### El informe, en capturas y no en un PBIX

[`scripts/capturar_informe.py`](scripts/capturar_informe.py) captura las cinco
paginas desde Power BI Desktop y escribe un manifiesto con el orden real del
informe y la marca de la pagina oculta, leidos de `pages.json`. La galeria del
dashboard lo consume, de modo que anadir una pagina al informe y recapturar
actualiza el sitio sin tocar el HTML.

Se descarto distribuir el `.pbix`, que es lo comodo para quien no tenga la base.
Lleva los 428.589 apuntes dentro y VertiPaq comprime sus diccionarios: una
busqueda literal no encuentra en el ni los valores que si contiene, comprobado.
Seria el unico artefacto publicado que ninguna auditoria puede revisar, en un
repositorio cuyo argumento es justamente el contrario. Un PNG tampoco se audita
por texto, pero no lleva los datos dentro: solo las cifras ya anonimizadas que
el modelo muestra, y el modelo si esta auditado.

### Lo que se publica, y lo que no

Los Parquet **si** se versionan, 3,3 MB ya anonimizados. Sin el libro de origen
-- 165 MB que no se publican nunca -- el ETL no tiene entrada, de modo que el
script solo no regenera nada: los Parquet son lo unico que permite a quien
clone el repositorio levantar PostgreSQL, abrir el PBIP y reproducir las
cifras. Quitarlos habria dejado un repositorio que impresiona y que nadie puede
ejecutar.

## Uso

```bash
pip install -e ".[dev]"
cp .env.example .env            # y fijar ANON_SALT y PGPASSWORD
python -m finanzas_etl          # etapa 1: Excel -> Parquet, ~2 min
python -m finanzas_etl.load     # etapa 2: Parquet -> PostgreSQL, ~20 s
start powerbi/ResultadoFinanciero.pbip   # etapa 3: el informe
python scripts/generar_cifras_web.py     # etapa 4: las cifras del dashboard
python scripts/capturar_informe.py       # etapa 4: las capturas del informe
pytest                          # 204 pruebas
ruff check src tests scripts
python scripts/auditar_powerbi.py        # obligatorio antes de publicar
```

El ETL escribe los Parquet en `data/processed/`, el informe de controles en
[`reports/calidad_datos.md`](reports/calidad_datos.md) y el diccionario de
datos en [`docs/diccionario_datos.md`](docs/diccionario_datos.md). La carga
crea la base si no existe, escribe su propio informe en
[`reports/calidad_carga.md`](reports/calidad_carga.md) y deja el diccionario
del esquema SQL en [`docs/diccionario_sql.md`](docs/diccionario_sql.md).

## Reconciliacion

Un pipeline financiero no se valida porque termine sin error, sino porque sus
cifras coincidan con el reporte que la organizacion ya publica. En cada
ejecucion se comparan los ingresos mensuales calculados contra la linea
INGRESOS de la hoja `DETALLE PL`:

| Escenario | Maqueta | Pipeline | Diferencia |
| --- | --- | --- | --- |
| Presupuesto 2025 | 80.553.599,56 | 80.553.599,56 | 0,00 |
| Real 2025 | 71.341.366,95 | 71.341.366,94 | −0,01 |
| Presupuesto 2026 | 71.737.307,27 | 71.737.307,25 | −0,02 |

Treinta y seis periodos, tres escenarios, cero descuadres: los dos centimos
son el redondeo del escalado y quedan muy por debajo de la tolerancia derivada.

**Esta tabla esta escalada, y la distincion importa.** El control se ejecuta dos
veces, antes y despues de anonimizar, y la pasada previa compara contra las
cifras originales: sus totales son la facturacion real del empleador. Lo que se
publica es la pasada posterior. Hasta la etapa 4 no era asi, y es el fallo
contado en [Lo que salio mal](#lo-que-salio-mal).

La banda de columnas de la maqueta se localiza **por su rotulo**, no por su
posicion: si el analista inserta una columna, el control sigue leyendo el
escenario correcto en lugar de desplazarse en silencio al de al lado.

Las tolerancias se derivan del proceso y no se eligen a ojo. Escalar y redondear
*n* importes puede desviar su suma hasta *n* medias centesimas, de modo que la
tolerancia de cada periodo es funcion del numero de apuntes que lo componen.

## Anonimizacion

Las cuatro propiedades que la capa garantiza, cada una con su prueba en
[`tests/test_anonymize.py`](tests/test_anonymize.py):

1. **Determinismo.** HMAC-SHA256 con una clave fija: el mismo valor produce
   siempre el mismo pseudonimo, entre columnas y entre ejecuciones. Sin esto
   las uniones del modelo se romperian.
2. **Inyectividad.** Dos centros de coste distintos nunca colapsan en uno, o
   los agregados cambiarian. Las colisiones se resuelven de forma determinista.
3. **Irreversibilidad sin la clave.** El mapa de reversion se guarda en local y
   esta excluido del repositorio.
4. **Invariancia de los ratios.** Un unico factor global para todos los
   importes y ejercicios deja margenes, pesos y variaciones interanuales
   intactos, porque `k` se cancela en todo cociente.

**El repositorio se publica sin historial, y por una razon concreta.** La
auditoria de texto encontro valores reales en commits de las tres etapas:
codigos de centro usados como datos de prueba, la marca comercial citada en el
propio README y en el nombre de un tema. El arbol de trabajo quedo limpio, pero
`git log -S` los recupera en segundos, de modo que publicar el historial
publicaria justo lo que el pipeline se dedica a borrar.

**Y esto se midio en lugar de suponerlo.** Buscando con `git log -S` los 294
valores del mapa de reversion de cuatro caracteres o mas, el repositorio de
trabajo devuelve **13** -- cuatro codigos de centro, dos nombres, cuatro
codigos de origen y tres terminos de la taxonomia interna -- y la copia que se
publica devuelve **cero**. Es la misma disciplina que el resto del proyecto
aplica a las tolerancias: una afirmacion plausible sin medir no sirve como
control, y menos para justificar una decision que no se puede deshacer.

Lo que se publica es el estado actual en un repositorio nuevo, construido por
[`scripts/publicar.py`](scripts/publicar.py) a partir de lo que `git ls-files`
declara -- no de un recorrido del disco, de modo que un fichero ignorado no
puede colarse -- y con una segunda cerradura que rechaza el envio si aparece
`.env`, el libro de origen, el mapa de reversion o el cache de Power BI.
Reescribir el historial con `git filter-repo` habria conservado el relato de
las etapas a cambio de reescribir todos los hashes y de confiar en que la
reescritura no se dejase nada: se eligio lo simple y verificable.

Tratamiento por tipo de dato:

| Dato | Tratamiento |
| --- | --- |
| Codigos de centro de coste | Pseudonimo `CC-nnnn` derivado por HMAC |
| Nombres de centros (contienen toponimos) | Catalogo ficticio verosimil: `Base Altamira - Transporte` |
| Taxonomia interna de negocio | Generalizada a terminos genericos: `Operaciones`, `Red de Agencias` |
| Numeros de documento | Pseudonimo numerico de 9 digitos |
| Importes | Factor global, redondeo a 2 decimales |
| Cuentas contables | **Se conservan.** Son el plan contable general peruano, un estandar publico que no identifica a la empresa |
| Usuario, proveedores, textos libres | **No se extraen.** Minimizacion en origen, no anonimizacion posterior |

### La auditoria que importa

Comprobar que la anonimizacion se ejecuto no demuestra nada. El control que lo
demuestra va en sentido contrario: toma los valores reales del libro original y
los busca uno a uno en los Parquet de salida
([`fugas.py`](src/finanzas_etl/quality/fugas.py)).

Es un control adversario, y encontro algo que los otros 22 no vieron: el
nombre comercial de la unidad quedaba pseudonimizado en `unidad_negocio` pero
seguia en claro en `ambito`, porque la misma taxonomia interna aparece repartida
entre tres columnas. La correccion fue un dominio de generalizacion compartido
por las tres.

### Lo que los Parquet no cubren

Esa auditoria recorre los datos. Pero un repositorio publica mucho mas que
datos: descripciones del modelo, titulos de visual, selecciones de segmentador,
comentarios del codigo, ejemplos de los tests y la propia documentacion. **Nada
de eso pasa por el ETL**, de modo que un nombre real escrito ahi se publica
igual que si estuviera en una tabla, y ningun control del pipeline lo ve.

[`scripts/auditar_powerbi.py`](scripts/auditar_powerbi.py) cierra ese hueco:
busca los valores originales dentro de los 120 ficheros de texto publicables
-- unos 835 KB -- y comprueba ademas que ninguna particion del modelo lea fuera
de los esquemas auditados, porque una consulta que apuntase a otra base traeria
datos que no pasaron por la anonimizacion. Se ejecuta aparte del ETL, porque
estas superficies cambian sin que el pipeline vuelva a correr: editar una
descripcion en Power BI Desktop o redactar un parrafo del README no reejecuta
nada, y es justo entonces cuando conviene comprobarlo.

```bash
python scripts/auditar_powerbi.py    # devuelve 1 si encuentra algo
```

**En su primera ejecucion encontro dieciocho valores reales**, acumulados a lo
largo de las tres etapas y todos escritos a mano. Estan contados en [Lo que
salio mal](#lo-que-salio-mal).

**Lo que no audita, y por que.** El cache del modelo y un PBIX exportado llevan
los datos dentro, pero VertiPaq comprime sus diccionarios: una busqueda literal
no encuentra en ellos ni los valores que si contienen, comprobado sobre el
cache real con pseudonimos presentes en el modelo. Auditarlos por bytes seria
un control incapaz de fallar, asi que no se hace. Ambos estan excluidos del
repositorio, y lo que de verdad los protege es que su contenido viene de los
Parquet que la auditoria de datos ya recorre.

## El escenario simulado

El ejercicio 2026 estaba recien abierto cuando se extrajo el libro: existe su
presupuesto pero no su real, de modo que la comparacion objetivo contra
ejecucion no se podia plantear para ese ano. El pipeline genera un real
sintetico de enero a octubre que cubre ese hueco
([`simulate/escenario.py`](src/finanzas_etl/simulate/escenario.py)).

**Queda marcado como simulado** en `dim_escenario.es_simulado`, en su propia
etiqueta (`Real 2026 (simulado)`) y en el informe de calidad. Es una columna
del modelo y no una nota al pie: cualquier visual que lo muestre puede
advertirlo, y un filtro separa lo observado de lo generado.

### El modelo

    simulado[s, m] = real[s, m] · deriva(grupo) · tendencia[m] · (1 + r[s, m])

* **`real[s, m]`** -- se parte del importe observado de cada mes, no de una
  media reconstruida. Asi el escenario hereda el perfil mensual exacto y, sobre
  todo, **la esporadicidad**: una serie que en el real solo tuvo actividad en
  marzo y julio sigue teniendo dos meses, no diez.
* **`deriva(grupo)`** -- cociente entre presupuesto 2026 y real 2025 por grupo
  del P&L, con una **convergencia parcial del 35%**. Adoptar la deriva completa
  equivaldria a suponer que el ejercicio cumple su presupuesto linea por linea,
  y el unico dato de ejecucion disponible dice lo contrario.
* **`tendencia[m]`** -- inclinacion tomada de la pendiente del propio
  presupuesto mensual, centrada para que no desplace el nivel anual.
* **`r[s, m]`** -- residuo autorregresivo AR(1) escalado por la volatilidad que
  esa serie mostro en el real. Con persistencia cero seria ruido blanco y la
  serie saldria en dientes de sierra; con memoria, una desviacion persiste
  varios meses, que es como se desvia la ejecucion de un presupuesto.

Reproducible: misma semilla, mismo escenario.

**No es una prevision.** No hay validacion fuera de muestra ni intervalo de
confianza: el objetivo es un escenario verosimil para ejercitar el reporte, no
estimar el resultado de 2026.

### Lo que se verifica

| Control | Resultado |
| --- | --- |
| No introduce centros ni cuentas nuevas | 0 |
| Volumen mensual del orden del real | razon 0,986 |
| Hereda el perfil mensual | correlacion 0,899 |
| Dispersion comparable | razon 2,47 |
| Margen en el rango del real | 9,28% vs 1,91% (7,4 pp) |
| Ingresos creibles frente al presupuesto | ejecucion 104,8% |

Tres de estos controles nacieron de fallos reales del generador, documentados
en [Lo que salio mal](#lo-que-salio-mal).

## Lo que salio mal

Los controles de este pipeline no son decorativos: cada uno existe porque algo
fallo. Estos son los fallos, por si resulta mas util que la lista de aciertos.

### Etapa 1, el ETL

**El patron de reconciliacion equivocado.** La primera version comparaba los
ingresos contra la fila 2 de `BD_PPTO26`, y descuadraron 11 de los 12 meses.
Esa fila es el presupuesto 2026 con enero sobrescrito por el real, no los
ingresos reales. El control detuvo el pipeline antes de escribir nada, que es
exactamente su trabajo. El patron correcto estaba en `DETALLE PL`, y de paso se
anadio la localizacion de bandas por rotulo para que una columna insertada no
desplace el control en silencio.

**Una fuga que 22 controles no vieron.** La auditoria adversaria -- buscar los
valores originales dentro de los ficheros de salida -- encontro que el literal
el nombre comercial de la unidad quedaba pseudonimizado en `unidad_negocio` pero seguia
en claro en `ambito`, porque la taxonomia interna aparece repartida entre tres
columnas. Se corrigio con un dominio de generalizacion compartido por las tres.

**Una afirmacion falsa en mi propia documentacion.** Dos tests fallaron contra
la afirmacion de que el escalado conserva los ratios *exactamente*. No es
cierto: el redondeo a centimos introduce un error relativo acotado por 0,005
dividido por el menor importe implicado -- despreciable en los millones del P&L
(1e-9), pero de ~1e-6 entre dos apuntes pequenos. Se corrigio la afirmacion, no
el test, y las tolerancias pasaron a derivarse del proceso.

**El generador inflaba el volumen un 33%.** La primera version del simulador
construia una rejilla completa de centro x cuenta x mes y asignaba
estacionalidad 1 a los meses sin dato, con el argumento de que "la ausencia en
el real no implica inactividad". El efecto real fue dar diez meses de actividad
a series que solo tenian dos. Se reescribio para partir del perfil observado
mes a mes.

**Dos metricas mal elegidas.** Los primeros controles del simulado median la
correlacion y la dispersion del **resultado neto**, cuya media esta proxima a
cero porque ingresos y costes se cancelan: el coeficiente de variacion salia
3,18 sin significar nada. Se pasaron al volumen bruto. Ademas comparaban el
real con grano de apunte contra el simulado con grano de celda, lo que hacia
parecer al real un 60% mas voluminoso; ahora el grano se iguala antes de
comparar.

**El simulado heredaba el margen del presupuesto.** Con la deriva completa, el
escenario salia con un margen del 16% frente al 1,9% real: era el presupuesto
con otro nombre. Se introdujo la convergencia parcial del 35%, y el margen
quedo en el 9,3%, entre el real y el objetivo.

### Etapa 2, la capa SQL

**El nulo y la cadena vacia eran el mismo campo.** La primera version del
cargador usaba el convenio por defecto de `COPY` en formato CSV: campo vacio
igual a nulo. Pero el generador de CSV de pandas escribe exactamente igual un
nulo y una cadena vacia, de modo que cualquier cadena vacia legitima habria
entrado en la base convertida en nulo. Los 22 controles pasaron igualmente,
porque hoy ninguna columna del modelo contiene cadenas vacias: el fallo era
latente y no se habria manifestado hasta que el origen trajese una, meses
despues y lejos de su causa. Se corrigio con un marcador de nulo explicito, una
guarda que rechaza la carga si ese literal aparece en los datos, un control de
recuento de nulos por tabla y una prueba de ida y vuelta contra una tabla real.
Lo encontre escribiendo la prueba, no ejecutando la carga.

**El detalle no podia tener clave foranea.** `fact_resultado` llegaba de la
etapa 1 con una columna `escenario` de valor constante `'Real'` en lugar de la
clave `escenario_clave`, de modo que su relacion con `dim_escenario` solo podia
quedar documentada en prosa. Se corrigio en el ETL y no en el cargador:
parchear la columna al cargar habria dejado el Parquet y la base divergentes, y
habria debilitado el control que compara sus totales.

**Una cifra del README mezclaba dos perimetros.** El resumen afirmaba que 2025
cerro "en el 88,6% del presupuesto, con un margen del 1,91%". Las dos cifras
son correctas y no son comparables: el 88,6% es la ejecucion de los doce meses,
mientras que el 1,91% es el margen de los diez primeros periodos, que es como
lo calcula `validar_margen` para contrastarlo con el escenario simulado. El
margen del ejercicio cerrado es del 3,35%. Lo delato la capa SQL: al exponer
`pl.v_pl_resumen` las dos agregaciones, la discrepancia entre el documento y el
modelo quedo a la vista. Se corrigio el texto, que es lo que estaba mal.

**Una suposicion sobre la coma flotante que no comprobe.** Escribi una prueba
que afirmaba que sumar diez veces 0,1 en pandas no da 1,0. Fallo: pandas suma
por pares y en ese caso acierta. La deriva si aparece al volumen real del
detalle, donde 428.589 importes suman `...,7299999` en vez de `...,73`, y la
prueba se reescribio alrededor de ese caso. La leccion no es sobre aritmetica
de coma flotante: es que una afirmacion plausible sin medir no sirve como
control, que es justo lo que este proyecto dice de las tolerancias.

### Etapa 3, el modelo semantico

Los dos primeros fallos los encontro una herramienta. Los cinco siguientes solo
aparecieron al abrir el informe con datos dentro, y ninguno habria salido de
leer el TMDL.

**Una medida y su columna no pueden llamarse igual.** La medida `Ingresos
Oficiales` agregaba la columna `Ingresos Oficiales` de la tabla de
reconciliacion. El modelo paso el round-trip de TMDL con sus medidas
intactas, el informe valido sin un solo aviso, y Power BI Desktop se nego a
abrir **el proyecto entero**: *"No se puede crear la medida 'Ingresos Oficiales'
porque ya existe una columna con el mismo nombre"*. La guia de modelado lo
advierte en una linea, y la aplique en los dos hechos -- donde la columna se
llama `Importe` -- pero no en la tabla de reconciliacion. Se renombro la columna
a `Importe Oficial`, porque la medida es la que se ve y por tanto la que se
queda con el nombre de negocio.

Lo revelador no es el fallo, que es de una linea, sino que **nada de lo que
habia podia detectarlo**: ni el validador del formato PBIR, ni el round-trip del
TMDL, ni las 123 pruebas. Asi que se escribio
[`tests/test_modelo_semantico.py`](tests/test_modelo_semantico.py), un parser del
TMDL y 22 pruebas que cubren lo que el validador no mira: las colisiones de
nombre, que toda medida tenga formato, carpeta y descripcion, que las claves
foraneas esten ocultas -- la regla se deriva de las relaciones declaradas, no se
adivina por el nombre de la columna --, que ningun identificador lleve acentos,
y que las columnas que ordenan a otras sigan disponibles en MDX, porque
ocultarlas rompe el orden del P&L sin dar ningun error.

De paso, dos de esas pruebas nacieron rotas. Una afirmaba que las descripciones
del modelo llevan acentos, y es falso: estan escritas sin ellos como el resto del
repositorio. La otra daba por buena una lista de caracteres acentuados en la que
se habian colado las vocales sin tilde, de modo que habria senalado cualquier
nombre. La primera se elimino -- la afirmacion era mia y era la equivocada -- y
la segunda se cambio por una guarda que fija los dos extremos del detector.

**El titulo de un visual no es una propiedad del visual.** Los seis graficos
llevaban su `title` dentro de `objects`, donde parece natural ponerlo. Es
propiedad del contenedor y va en `visualContainerObjects`; el validador del
formato lo rechazo antes de abrir Desktop, que es justo lo que se le pide a un
validador. En `objects` habria validado contra el esquema y el titulo
simplemente no habria aparecido.

#### Lo que solo se vio con datos dentro

**Los importes llegaron como coma flotante.** El TMDL declaraba
`dataType: decimal`, pero al refrescar Power BI reconcilia el tipo declarado con
el que entrega el conector, y el de PostgreSQL llega como numero de coma
flotante: las tres columnas de importe acabaron en `Double`. El sintoma fue
minusculo y delator -- el detalle sumaba 2.390.986,**160000677** en lugar de
2.390.986,16, y el control de cuadre entre las dos tablas de hechos se quedaba a
siete diezmillonesimas de cero en vez de clavarlo --. El modelo contradecia en
silencio el argumento que este repositorio usa para justificar `numeric(18,2)`
en PostgreSQL. Se corrigio fijando `Currency.Type` en el M de las tres
particiones, que es lo unico que sobrevive a un refresco; el cuadre pasa a dar
**cero exacto** y las diferencias de reconciliacion, −0,01 y −0,02 limpias.

**Tres medidas devolvian cifras donde no habia nada que medir.** DAX trata el
vacio como cero en una resta, y eso basta para inventarse datos:

* `Variacion Interanual` daba al primer ejercicio del modelo una variacion igual
  a su propio resultado -- una subida desde la nada --, porque restaba un
  ejercicio anterior que no existe. Ahora comprueba si el ejercicio anterior
  existe **como periodo**, y no si la medida salio vacia: una linea del P&L que
  el ano pasado no tuvo importe si debe arrojar variacion, y es otro caso.
* `Cuadre de Hechos` mostraba −2.390.986,16 en los escenarios sin detalle,
  restando el real completo de un detalle vacio.
* `Diferencia Reconciliacion` presentaba los 61,4 millones del escenario
  simulado como si fueran un descuadre, por compararlos contra un patron que no
  existe.

**Y el total de la reconciliacion decia DESCUADRE.** Agregados los cuatro
escenarios, la pagina de control comparaba los ingresos de los cuatro contra el
patron de los tres que lo tienen, y la tarjeta mas visible del informe -- la que
existe para demostrar que todo cuadra -- mostraba un descuadre de 61.403.600,46.
La medida pasa a medir **solo sobre los escenarios que tienen patron**: el total
da ahora −0,03, que son los centimos de redondeo del escalado, y el veredicto
vuelve a ser "Cuadra". Un escenario que nadie presupuesto no descuadra contra la
maqueta; es que no esta en ella.

**Las paginas abrian sumando el presupuesto con el real.** Sin seleccion inicial
en los segmentadores, el informe se abria en "Todas" y las tarjetas mostraban
285,04 millones de "ingresos", que es la suma de los cuatro escenarios y no
significa nada. Las paginas arrancan ahora en un escenario concreto -- Real 2025
el P&L y el analisis por centro, 2026 la ejecucion presupuestaria, que es donde
el recorte de periodos se ve --, y el usuario puede cambiarlo. La pagina de
control se queda sin filtro a proposito: alli el total ya cuadra y ensenar los
cuatro escenarios es justamente el objetivo.

**El analisis por centro medía lo que estos datos no pueden medir.** La pagina
clasificaba los 88 centros por resultado neto y cruzaba ingresos contra margen.
Con los datos delante quedo claro por que no funcionaba: **los ingresos se
imputan a dos centros** y el coste se reparte entre los ochenta y ocho, de modo
que el ranking estaba dominado por dos barras y el grafico de dispersion tenia
dos puntos. La pagina pasa a analizar el coste, que es lo que si esta repartido,
con los quince centros de mayor gasto y su desglose por ambito y por periodo. El
margen por centro sigue existiendo donde hay facturacion, y el vacio del resto
es correcto: un centro que no factura no tiene margen, y asignarle cero lo haria
parecer el peor del ranking.

**El formato en miles y la abreviacion automatica se anularon.** Las medidas de
importe pasaron a mostrarse en miles -- `#,##0,` -- para que las columnas del
P&L cupieran, y las tarjetas siguieron aplicando ademas su abreviacion
automatica a millones. El resultado era que un ingreso de 61.404 miles se
mostraba como **"S/. 0 mill."**: la cifra correcta, formateada dos veces y
reducida a cero. Lo delato una captura del informe, no una consulta. Se corrige
fijando `labelDisplayUnits` a ninguna en las tarjetas y en los ejes, una sola
vez en el tema del informe.

**Una dependencia circular entre dos columnas calculadas.** `Cuenta[Linea
Oficial]` clasificaba la cuenta y `Cuenta[Orden Linea Oficial]` traducia esa
linea a su posicion; despues se pidio que la primera se ordenase por la segunda,
y el refresco fallo con *"A circular dependency was detected"*. Power BI cuenta
`sortByColumn` como dependencia, de modo que el ciclo era real aunque las dos
formulas leyeran una sola vez. Se invirtio el sentido: ahora el **orden** lleva
el criterio de clasificacion y el **nombre** se limita a traducir el numero, con
lo que el mapeo vive en un unico sitio y la dependencia va en una direccion.

**Un titulo que no decia lo que el visual hacia.** Dos graficos se rotulaban
"los doce centros con mayor desviacion desfavorable", pero su filtro Top N
ordena por la suma del importe: el `OrderBy` de un filtro Top N solo admite una
agregacion sobre columna, nunca una medida. Seleccionaban por coste y decian
seleccionar por desviacion. Se corrigio el rotulo, que era lo que estaba mal.

**Dieciocho valores reales escritos a mano, repartidos por tres etapas.** Al
extender la auditoria adversaria a los ficheros de texto -- lo que los Parquet
no cubren -- la primera ejecucion fallo con dieciocho coincidencias, y ninguna
era un falso positivo:

* El **nombre del tema** del informe llevaba la marca comercial de la empresa.
  Lo elegi yo en esta etapa, sin reparar en que ese literal esta en el mapa de
  reversion como nombre de centro y aparece dentro de 76 nombres reales.
* Dos **comentarios del modelo** citaban la hoja del libro original por su
  nombre, que incluye el de la unidad de negocio.
* El **README contaba la fuga de la etapa 1 citando el literal fugado**. La
  seccion que explica como se detecto que el nombre comercial seguia en claro
  lo reproducia tres veces.
* Los **datos de prueba de dos ficheros de test** eran codigos de centro
  reales del extracto, y dos toponimos peruanos autenticos. Llevaban ahi desde
  la etapa 1: opacos a la vista, exactos en el repositorio.
* Un **docstring** del pseudonimizador usaba como ejemplo las tres variantes
  reales de la nomenclatura interna.

Todo corregido con valores sinteticos que prueban lo mismo. La leccion no es
que se colaran, sino **donde**: ni uno estaba en los datos, que es lo unico que
el pipeline sabia mirar. Un pipeline que anonimiza sus tablas y publica el
nombre de la empresa en un comentario no ha anonimizado nada.

**Power BI Desktop reescribe el proyecto al abrirlo.** Le quita el `$schema` al
`.pbip` y al `definition.pbir` -- con lo que el validador y Fabric los rechazan
-- y renombra la base del modelo con el GUID de su sesion, que cambia en cada
una y llena el diff de ruido. Ninguna de las dos cosas rompe el informe, y por
eso es facil que se cuelen en un commit. Las deshace
[`scripts/normalizar_pbip.py`](scripts/normalizar_pbip.py), que es idempotente y
se ejecuta antes de validar.


### Etapa 4, la publicacion

Los tres primeros son el mismo fallo visto tres veces, y es el peor del
proyecto: **el pipeline anonimiza sus tablas y el repositorio publicaba las
cifras reales del empleador desde la etapa 1.**

**La tabla de reconciliacion del README llevaba la facturacion real.** Las tres
cifras de la seccion [Reconciliacion](#reconciliacion) estaban en unidades
originales, sin escalar: el control se ejecuta dos veces, antes y despues de
anonimizar, y lo que se habia publicado era la pasada previa. Multiplicar
cualquiera de ellas por el factor de anonimizacion devuelve exactamente la
cifra que el modelo expone, que es como se encontro.

**El informe de calidad del ETL publicaba el mismo total, y se regeneraba en
cada ejecucion.** El control de reconciliacion emitia `total_esperado` y
`total_calculado` entre sus metricas, y en la pasada previa a anonimizar esos
dos numeros son la facturacion del ejercicio. Corregir el fichero no habria
servido de nada porque el generador lo reescribe: se quitaron del control. Lo
que demuestra un control es la diferencia contra su tolerancia, que no depende
de la magnitud -- un descuadre de 0,00 sobre doce periodos prueba exactamente
lo mismo sin revelar sobre que importe se midio.

**Y un ingreso mensual real llevaba desde la etapa 1 como dato de prueba.** En
`tests/test_xlsx_stream.py`, como valor cacheado de una formula. Lo que el test
demuestra -- que el lector devuelve el `<v>` y no la formula -- no depende del
valor. Este no lo encontre yo: lo encontro el control nuevo, en la misma
ejecucion en la que se estrenaba.

**Ninguno de los 55 controles ni de las 160 pruebas podia verlos, y el motivo
es estructural.** La auditoria adversaria construye su universo sensible a
partir del mapa de reversion, que contiene lo que se pseudonimizo: codigos de
centro, nombres, documentos, taxonomia. **Un importe no esta en ese mapa y no
puede estarlo**, porque los importes no se pseudonimizan sino que se escalan
por un factor global. El control buscaba identificadores en un repositorio
donde lo que se habia filtrado eran cifras.

La correccion va por el lado contrario: `auditar_importes` extrae del texto
todo lo que parezca un numero, lo normaliza y lo compara contra los importes
oficiales **deshaciendo el escalado**. Tiene que normalizar porque los dos
casos reales venian en formatos que no se parecen -- uno con el punto separando
millares y la coma los decimales, el otro al reves y con cuatro decimales --,
de modo que ninguna busqueda literal los habria encontrado a los dos. Cuando un
numero admite las dos lecturas se comprueban ambas: un falso positivo cuesta
una comprobacion y un falso negativo cuesta publicar la cifra. La tolerancia se
deriva del redondeo del escalado, como todas las demas.

**El comentario que explicaba la fuga la reproducia.** La primera version de
ese bloque citaba las dos cifras como ejemplo de los formatos, con lo que el
fichero que estrenaba el control fallaba el control. Es exactamente el fallo de
la etapa 1, en el que el README conto una fuga reproduciendo el literal fugado,
cometido otra vez mientras se escribia la defensa contra el.

**Dos ficheros no se auditaban desde la etapa 3, y la lista decia que si.**
`.platform` estaba declarado en `SUFIJOS_PUBLICABLES` desde el principio, pero
`Path(".platform").suffix` es la cadena vacia: para `pathlib`, un nombre que
empieza por punto no tiene extension. La entrada llevaba tres etapas sin casar
con nada y los dos `.platform` del PBIP -- que se publican y llevan el nombre
del elemento dentro -- nunca se habian mirado. Nada lo advertia porque la
auditoria informaba de cuantos ficheros recorria, no de cuantos se dejaba.

**Y las raices de la auditoria se habian quedado cortas sin que nada avisara.**
Quedaban fuera `reports/`, `pyproject.toml`, `.gitignore` y `.env.example`, y
ninguna de las cuatro extensiones de la capa web -- justo las del dashboard que
esta etapa iba a publicar, que es el fichero que lee cualquiera sin clonar
nada. La lista de raices estaba escrita a mano, y una lista escrita a mano se
queda corta en silencio.

La correccion invierte la pregunta. `superficies_sin_auditar` le pregunta a git
que ficheros subiria -- lo versionado mas lo nuevo no ignorado -- y exige que
todos esten cubiertos, de modo que una carpeta o una extension nueva hace
fallar la auditoria hasta que alguien decida explicitamente si se audita. Fue
este control el que encontro los `.platform`.

**El README describia un modelo que ya no existia.** Anunciaba 7 tablas, 34
medidas, 4 paginas y 31 visuales; el informe cerro la etapa 3 con 8, 48, 5 y
33. Se contradecia incluso a si mismo: el epigrafe "Las cuatro paginas" iba
seguido de una tabla con cinco filas. Son las cifras de un punto intermedio de
la etapa 3 que nadie volvio a tocar, y estaban en el documento que esta etapa
convierte en carta de presentacion.

**Las primeras capturas del informe salieron vacias.** Power BI Desktop abre el
proyecto sin datos, de modo que las cinco paginas se capturaron con los
visuales en blanco y un aviso arriba diciendolo. En el listado de ficheros
parecian correctas -- cinco PNG, un nombre por pagina -- y solo abrirlas lo
delato. Es el mismo patron que el formato en miles de la etapa 3: lo que
delata un fallo de presentacion es mirar la presentacion. El script de captura
avisa de que hay que mirarlas y no finge comprobarlo: validar que un PNG tiene
datos dentro exigiria leer los pixeles, y un umbral sobre el tamano del fichero
seria un numero ajustado a lo que se observo una vez.

## Alcance y supuestos

* **No hay datos reales de 2026 en el origen.** La hoja `Data 2026` del libro
  es una copia identica del periodo 1 de 2025 mas 384.315 filas vacias. El
  escenario `R2026` que cubre ese hueco es generado, no observado, y esta
  marcado como tal en todo el modelo. Ver [El escenario
  simulado](#el-escenario-simulado).
* **El perimetro es el resultado directo de la unidad de negocio.** La maqueta
  reparte ademas costes de soporte procedentes de otras unidades, un paso de
  asignacion que vive fuera de este extracto. Los ingresos y los costes
  directos reconcilian al centimo; el resultado neto de la maqueta incluye esa
  distribucion y no se reproduce aqui.
* **La marca `Documento anulacion` no se filtra.** Llega en el 37,5% de los
  apuntes, pero no afecta a ninguno de ingresos y los totales oficiales se
  reproducen sumando todo. Es informativa. Un control dedicado verifica esta
  interpretacion en cada ejecucion.

## Estructura

```
src/finanzas_etl/
  extract/    xlsx_stream.py  lector incremental de XLSX
              extractor.py    materializacion de las hojas
              maqueta.py      localizacion de bandas del P&L oficial
  transform/  schema.py       contrato de columnas y motivos de descarte
              clean.py        tipado, fechas seriales, normalizacion
              model.py        esquema en estrella
  anonymize/  mapper.py       pseudonimizacion determinista
              scaler.py       escalado de importes e invariantes
  simulate/   escenario.py    generador del real simulado
              validacion.py   controles de verosimilitud
  quality/    checks.py       controles y reconciliacion
              fugas.py        auditoria adversaria de las salidas
  load/       postgres.py     carga idempotente con COPY y verificacion
  pipeline.py                 orquestacion
powerbi/      ResultadoFinanciero.pbip            el proyecto PBIP
              *.SemanticModel/definition/*.tmdl   modelo y medidas DAX
              *.Report/definition/pages/          las cinco paginas
              validacion.dax                      las medidas contra el SQL
scripts/      normalizar_pbip.py    deshace lo que Desktop reescribe del PBIP
              generar_cifras_web.py las cifras del dashboard, desde la base
              capturar_informe.py   las capturas del informe y su manifiesto
docs/         index.html            el dashboard publicado en GitHub Pages
              cifras.json           generado; el HTML no lleva importes
              capturas/             las cinco paginas del informe
sql/          01_esquemas.sql   los esquemas core, pl y qa
              02_tablas.sql     el estrella, sus restricciones y COMMENT ON
              03_indices.sql    indices, con las mediciones que los justifican
              04_vistas_pl.sql  la cuenta de resultados
              05_vistas_qa.sql  los controles del esquema
              06_permisos.sql   los roles bi_reader y bi_modeler
tests/                        204 pruebas, 16 necesitan PostgreSQL
              test_modelo_semantico.py  invariantes del TMDL, sin abrir Power BI
              test_fugas_publicables.py controles de la auditoria de texto
              test_cifras_web.py        las cifras publicadas, sin base
scripts/      auditar_powerbi.py  la auditoria de lo publicable
docs/diccionario_datos.md     generado desde el contrato de columnas
docs/diccionario_sql.md       generado desde los COMMENT ON de la base
reports/calidad_datos.md      generado en cada ejecucion del ETL
reports/calidad_carga.md      generado en cada carga
```

## Hoja de ruta

- [x] Etapa 1 — ETL en Python: 4 escenarios reconciliados y anonimizados
- [x] Etapa 2 — PostgreSQL: estrella en `core`, P&L en `pl`, controles en `qa`
- [x] Etapa 3 — Power BI en formato PBIP, modelo y medidas DAX versionadas
- [x] Etapa 4 — Portafolio publicado: repositorio, GitHub Pages y dashboard

-- ===========================================================================
-- 04_vistas_pl.sql -- Reconstruccion de la cuenta de resultados.
--
-- El convenio de signo que lo simplifica todo
-- -------------------------------------------
-- Los importes conservan el signo de SAP: ingreso positivo, coste negativo.
-- Parece un detalle de formato y no lo es, porque convierte tres calculos en
-- sumas directas:
--
--   resultado   = sum(importe)                    sin condicionales
--   desviacion  = real - presupuesto              favorable si es positiva,
--                                                 tanto en ingresos como en
--                                                 costes
--   acumulado   = sum(importe) OVER (...)         sin reglas por tipo de linea
--
-- Que la desviacion favorable sea siempre la positiva merece explicacion:
-- en una linea de ingreso, facturar mas que el presupuesto da una diferencia
-- positiva; en una de coste, gastar menos significa un numero negativo mas
-- proximo a cero, es decir, tambien mayor que el presupuestado. El unico
-- precio es que las lineas de coste se muestran en negativo, y para eso cada
-- vista expone ademas importe_presentacion, con el signo invertido en los
-- costes, que es como se lee un P&L impreso.
--
-- Vistas y no tablas materializadas
-- ---------------------------------
-- El hecho agregado tiene 42.017 filas. Materializar estas vistas anadiria un
-- REFRESH que orquestar despues de cada carga y la posibilidad de servir una
-- version desincronizada del hecho, a cambio de ahorrar milisegundos.
--
-- Las vistas se construyen en cascada sobre v_hechos_escenario para que la
-- definicion de "linea del P&L" viva en un unico sitio. PostgreSQL integra la
-- definicion de la vista en la consulta que la usa, de modo que el anidamiento
-- no cuesta nada en tiempo de ejecucion.
-- ===========================================================================

DROP VIEW IF EXISTS pl.v_resultado_por_centro     CASCADE;
DROP VIEW IF EXISTS pl.v_variacion_interanual     CASCADE;
DROP VIEW IF EXISTS pl.v_ejecucion_presupuestaria CASCADE;
DROP VIEW IF EXISTS pl.v_pl_resumen               CASCADE;
DROP VIEW IF EXISTS pl.v_pl_mensual               CASCADE;
DROP VIEW IF EXISTS pl.v_hechos_escenario         CASCADE;


-- --- Hecho denormalizado ---------------------------------------------------

CREATE VIEW pl.v_hechos_escenario AS
SELECT
    f.escenario_clave,
    e.escenario,
    e.tipo_escenario,
    e.es_simulado,
    e.periodos_cubiertos,
    e.orden_escenario,
    f.fecha_clave,
    t.ejercicio,
    t.periodo,
    t.mes_abrev,
    t.etiqueta_mes,
    t.trimestre,
    t.etiqueta_trimestre,
    t.mes_inicio,
    f.ceco_codigo,
    ce.ceco_nombre,
    ce.ambito,
    ce.estructura,
    ce.unidad_negocio,
    f.cuenta_codigo,
    cu.cuenta_nombre,
    cu.grupo,
    cu.clase_costo_gasto,
    cu.clase_pcge,
    cu.es_ingreso,
    cu.linea_pl,
    cu.orden_pl,
    f.importe,
    CASE WHEN cu.es_ingreso THEN f.importe ELSE -f.importe END AS importe_presentacion
FROM core.fact_escenario f
    JOIN core.dim_escenario e  ON e.escenario_clave = f.escenario_clave
    JOIN core.dim_tiempo    t  ON t.fecha_clave     = f.fecha_clave
    JOIN core.dim_centro    ce ON ce.ceco_codigo    = f.ceco_codigo
    JOIN core.dim_cuenta    cu ON cu.cuenta_codigo  = f.cuenta_codigo;

COMMENT ON VIEW pl.v_hechos_escenario IS
    'El hecho comparativo con todos los atributos de sus dimensiones resueltos. '
    'Es la base de las demas vistas y la tabla unica para analisis ad hoc. Los '
    'JOIN son internos y no pueden perder filas porque las cuatro claves tienen '
    'clave foranea declarada: el descuadre silencioso por clave huerfana, que es '
    'el fallo clasico de un modelo en estrella, aqui lo impide el esquema y no '
    'una comprobacion posterior.';


-- --- P&L mensual por linea -------------------------------------------------

CREATE VIEW pl.v_pl_mensual AS
SELECT
    escenario_clave,
    escenario,
    tipo_escenario,
    es_simulado,
    orden_escenario,
    ejercicio,
    periodo,
    etiqueta_mes,
    trimestre,
    orden_pl,
    linea_pl,
    es_ingreso,
    sum(importe)              AS importe,
    sum(importe_presentacion) AS importe_presentacion,
    count(*)                  AS combinaciones
FROM pl.v_hechos_escenario
GROUP BY
    escenario_clave, escenario, tipo_escenario, es_simulado, orden_escenario,
    ejercicio, periodo, etiqueta_mes, trimestre, orden_pl, linea_pl, es_ingreso;

COMMENT ON VIEW pl.v_pl_mensual IS
    'La cuenta de resultados mes a mes, una fila por escenario, periodo y linea '
    'del P&L, en el orden de presentacion del reporte oficial. Es la vista que '
    'reproduce la maqueta de Control de Gestion.';


-- --- Resumen con margen y acumulado ---------------------------------------

CREATE VIEW pl.v_pl_resumen AS
SELECT
    escenario_clave,
    escenario,
    tipo_escenario,
    es_simulado,
    orden_escenario,
    ejercicio,
    periodo,
    etiqueta_mes,
    -- El perimetro de ingresos es el grupo 'Ingresos' a secas, no es_ingreso.
    -- es_ingreso tambien cubre 'Ingresos Diversos', y la fila INGRESOS de la
    -- maqueta de Control de Gestion no lo incluye: medir el margen sobre el
    -- perimetro amplio lo desplaza casi tres centesimas de punto y lo separa
    -- de la cifra que la organizacion publica. Los ingresos diversos salen en
    -- su propia columna para que no se pierdan y para que la identidad
    -- resultado = ingresos - costes + ingresos_diversos sea verificable.
    coalesce(sum(importe) FILTER (WHERE grupo = 'Ingresos'), 0)          AS ingresos,
    coalesce(sum(importe) FILTER (WHERE grupo = 'Ingresos Diversos'), 0) AS ingresos_diversos,
    coalesce(-sum(importe) FILTER (WHERE NOT es_ingreso), 0)             AS costes,
    sum(importe)                                                         AS resultado,
    round(
        100 * sum(importe)
            / nullif(sum(importe) FILTER (WHERE grupo = 'Ingresos'), 0),
        4
    )                                                                    AS margen_pct,
    sum(sum(importe) FILTER (WHERE grupo = 'Ingresos')) OVER acumulado   AS ingresos_acumulados,
    sum(sum(importe))                                   OVER acumulado   AS resultado_acumulado
FROM pl.v_hechos_escenario
GROUP BY
    escenario_clave, escenario, tipo_escenario, es_simulado, orden_escenario,
    ejercicio, periodo, etiqueta_mes
WINDOW acumulado AS (PARTITION BY escenario_clave ORDER BY periodo);

COMMENT ON VIEW pl.v_pl_resumen IS
    'Ingresos, costes, resultado y margen por escenario y mes, con el acumulado '
    'del ejercicio. Los costes se exponen en positivo porque es como se leen en '
    'un informe; resultado sigue siendo la suma de todas las lineas y conserva el '
    'signo contable, de modo que no es exactamente ingresos menos costes: la '
    'diferencia son los ingresos diversos, que van en su propia columna. La '
    'columna ingresos cubre el grupo Ingresos y no es_ingreso, porque es el '
    'perimetro de la fila INGRESOS de la maqueta y el unico contra el que el '
    'modelo reconcilia; qa.v_control_perimetro_ingresos lo vigila. El margen se '
    'divide por nullif(ingresos, 0) para que un mes sin facturacion devuelva nulo '
    'en lugar de romper la consulta: un margen indefinido no es un margen del '
    'cero por ciento.';


-- --- Ejecucion presupuestaria ----------------------------------------------

CREATE VIEW pl.v_ejecucion_presupuestaria AS
WITH por_tipo AS (
    SELECT tipo_escenario, ejercicio, periodo, orden_pl, linea_pl, es_ingreso,
           sum(importe) AS importe
    FROM pl.v_hechos_escenario
    GROUP BY tipo_escenario, ejercicio, periodo, orden_pl, linea_pl, es_ingreso
),
ejecutado AS (
    SELECT * FROM por_tipo WHERE tipo_escenario = 'Real'
),
presupuestado AS (
    SELECT * FROM por_tipo WHERE tipo_escenario = 'Presupuesto'
)
SELECT
    coalesce(r.ejercicio,  p.ejercicio)  AS ejercicio,
    coalesce(r.periodo,    p.periodo)    AS periodo,
    coalesce(r.orden_pl,   p.orden_pl)   AS orden_pl,
    coalesce(r.linea_pl,   p.linea_pl)   AS linea_pl,
    coalesce(r.es_ingreso, p.es_ingreso) AS es_ingreso,
    coalesce(r.importe, 0)               AS importe_real,
    coalesce(p.importe, 0)               AS importe_presupuesto,
    coalesce(r.importe, 0) - coalesce(p.importe, 0) AS desviacion,
    coalesce(r.importe, 0) >= coalesce(p.importe, 0) AS es_favorable,
    round(100 * coalesce(r.importe, 0) / nullif(p.importe, 0), 2) AS ejecucion_pct,
    r.importe IS NULL AS solo_presupuestado,
    p.importe IS NULL AS solo_ejecutado,
    coalesce(r.periodo, p.periodo) <= (
        SELECT e.periodos_cubiertos
        FROM core.dim_escenario e
        WHERE e.tipo_escenario = 'Real'
          AND e.ejercicio = coalesce(r.ejercicio, p.ejercicio)
    ) AS periodo_comparable
FROM ejecutado r
    FULL JOIN presupuestado p
        ON  p.ejercicio = r.ejercicio
        AND p.periodo   = r.periodo
        AND p.linea_pl  = r.linea_pl;

COMMENT ON VIEW pl.v_ejecucion_presupuestaria IS
    'Real contra presupuesto del mismo ejercicio, por mes y linea del P&L. El '
    'join es FULL y no LEFT a proposito: una linea presupuestada que no llego a '
    'ejecutarse, o un gasto ejecutado que nadie presupuesto, son justamente los '
    'hallazgos que busca un control de gestion, y un LEFT JOIN haria desaparecer '
    'uno de los dos casos sin dejar rastro. Las banderas solo_presupuestado y '
    'solo_ejecutado los identifican. es_favorable aprovecha que, con el signo '
    'contable, una desviacion positiva es buena tanto si se factura de mas como '
    'si se gasta de menos. periodo_comparable marca los meses que el ejercicio '
    'real cubre: el de 2026 llega hasta octubre, y sumar su ejecucion contra '
    'doce meses de presupuesto daria un 85% de ejecucion inventado en lugar del '
    '104,8% real. Quien agregue esta vista por ejercicio debe filtrar por esa '
    'columna.';


-- --- Variacion interanual --------------------------------------------------

CREATE VIEW pl.v_variacion_interanual AS
WITH limite AS (
    -- El real de 2026 cubre diez periodos, el de 2025 los doce. Comparar los
    -- totales sin mas inflaria 2025 en dos meses y daria una caida inventada
    -- del 17%. La comparacion se recorta al menor numero de periodos cubiertos
    -- entre los escenarios reales, que es la unica forma de que sea homogenea.
    SELECT min(periodos_cubiertos) AS ultimo_periodo
    FROM core.dim_escenario
    WHERE tipo_escenario = 'Real'
),
-- La rejilla completa de lineas, periodos y ejercicios garantiza que una linea
-- que existe en un ejercicio y no en el otro aparezca con cero en lugar de
-- desaparecer de la comparacion.
rejilla AS (
    SELECT e.ejercicio, p.periodo, l.orden_pl, l.linea_pl, l.es_ingreso
    FROM (SELECT DISTINCT ejercicio FROM core.dim_tiempo) e
        CROSS JOIN (
            SELECT generate_series(1, (SELECT ultimo_periodo FROM limite))::smallint AS periodo
        ) p
        CROSS JOIN (SELECT DISTINCT orden_pl, linea_pl, es_ingreso FROM core.dim_cuenta) l
),
observado AS (
    SELECT h.ejercicio, h.periodo, h.linea_pl,
           sum(h.importe)        AS importe,
           bool_or(h.es_simulado) AS es_simulado
    FROM pl.v_hechos_escenario h
    WHERE h.tipo_escenario = 'Real'
      AND h.periodo <= (SELECT ultimo_periodo FROM limite)
    GROUP BY h.ejercicio, h.periodo, h.linea_pl
),
emparejado AS (
    SELECT
        g.ejercicio,
        g.periodo,
        g.orden_pl,
        g.linea_pl,
        g.es_ingreso,
        coalesce(o.importe, 0)      AS importe,
        coalesce(o.es_simulado, false) AS es_simulado,
        lag(coalesce(o.importe, 0)) OVER (
            PARTITION BY g.linea_pl, g.periodo ORDER BY g.ejercicio
        ) AS importe_anterior,
        lag(g.ejercicio) OVER (
            PARTITION BY g.linea_pl, g.periodo ORDER BY g.ejercicio
        ) AS ejercicio_anterior
    FROM rejilla g
        LEFT JOIN observado o
            ON  o.ejercicio = g.ejercicio
            AND o.periodo   = g.periodo
            AND o.linea_pl  = g.linea_pl
)
SELECT
    ejercicio,
    ejercicio_anterior,
    periodo,
    orden_pl,
    linea_pl,
    es_ingreso,
    es_simulado,
    importe          AS importe_actual,
    importe_anterior,
    importe - importe_anterior AS variacion,
    round(100 * (importe - importe_anterior) / nullif(abs(importe_anterior), 0), 2)
        AS variacion_pct
FROM emparejado
WHERE ejercicio_anterior IS NOT NULL;

COMMENT ON VIEW pl.v_variacion_interanual IS
    'Variacion del real entre ejercicios consecutivos, recortada a los periodos '
    'que ambos cubren. El recorte no es cosmetico: el real de 2026 llega hasta '
    'octubre y compararlo contra doce meses de 2025 produciria una caida '
    'inventada de dos meses de actividad. El denominador de variacion_pct es el '
    'valor absoluto del importe anterior, para que una linea de coste que empeora '
    'no aparezca con porcentaje de signo contrario. Las filas con es_simulado '
    'provienen del escenario generado.';


-- --- Resultado por centro de coste -----------------------------------------

CREATE VIEW pl.v_resultado_por_centro AS
SELECT
    escenario_clave,
    escenario,
    tipo_escenario,
    es_simulado,
    ejercicio,
    ceco_codigo,
    ceco_nombre,
    ambito,
    estructura,
    unidad_negocio,
    -- Mismo perimetro que v_pl_resumen, por el mismo motivo.
    coalesce(sum(importe) FILTER (WHERE grupo = 'Ingresos'), 0)          AS ingresos,
    coalesce(sum(importe) FILTER (WHERE grupo = 'Ingresos Diversos'), 0) AS ingresos_diversos,
    coalesce(-sum(importe) FILTER (WHERE NOT es_ingreso), 0)             AS costes,
    sum(importe)                                                         AS resultado,
    round(
        100 * sum(importe)
            / nullif(sum(importe) FILTER (WHERE grupo = 'Ingresos'), 0),
        4
    )                                                                    AS margen_pct
FROM pl.v_hechos_escenario
GROUP BY
    escenario_clave, escenario, tipo_escenario, es_simulado, ejercicio,
    ceco_codigo, ceco_nombre, ambito, estructura, unidad_negocio;

COMMENT ON VIEW pl.v_resultado_por_centro IS
    'Resultado anual por centro de coste y escenario. El margen queda nulo en los '
    'centros que no facturan -- mantenimiento, direccion -- y eso es correcto: un '
    'centro de solo coste no tiene margen, y asignarle cero lo haria parecer el '
    'peor del ranking cuando simplemente no participa en la medida.';

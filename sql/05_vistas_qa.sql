-- ===========================================================================
-- 05_vistas_qa.sql -- Controles de la capa SQL.
--
-- Convenio: toda vista v_control_* devuelve cero filas cuando el modelo esta
-- sano. Cada fila que devuelve es un descuadre, con sus cifras al lado. Eso
-- permite que el verificador de la carga sea un bucle de cuatro lineas en vez
-- de una bateria de comparaciones en Python, y que cualquiera pueda repetir el
-- control desde psql sin ejecutar nada del repositorio.
--
-- Las vistas v_resumen_* son informativas y siempre devuelven filas.
--
-- Lo que NO hay aqui, y por que
-- ------------------------------
-- No hay vista de claves huerfanas. Las cuatro claves de cada hecho tienen
-- clave foranea declarada en 02_tablas.sql, de modo que una fila huerfana no
-- puede llegar a existir: la insercion falla antes. Una vista que buscase
-- huerfanos seria incapaz de devolver una sola fila, y un control que no puede
-- fallar no es un control, es decoracion. El mismo razonamiento descarta
-- comprobar aqui que fecha_clave = ejercicio*100+periodo, que periodo este
-- entre 1 y 12 o que clase_pcge sea el primer caracter de la cuenta: son CHECK
-- del esquema. Lo que queda en este fichero es lo que el esquema no puede
-- imponer, que es precisamente lo que merece vigilancia.
-- ===========================================================================

DROP VIEW IF EXISTS qa.v_resumen_carga                   CASCADE;
DROP VIEW IF EXISTS qa.v_control_orden_pl                CASCADE;
DROP VIEW IF EXISTS qa.v_control_cobertura_periodos      CASCADE;
DROP VIEW IF EXISTS qa.v_control_ejercicio_coherente     CASCADE;
DROP VIEW IF EXISTS qa.v_control_cuadre_hechos           CASCADE;
DROP VIEW IF EXISTS qa.v_control_reconciliacion_ingresos CASCADE;
DROP VIEW IF EXISTS qa.v_control_perimetro_ingresos      CASCADE;


-- --- 1. Reconciliacion contra la cifra oficial -----------------------------

CREATE VIEW qa.v_control_reconciliacion_ingresos AS
WITH modelo AS (
    -- El grupo es 'Ingresos' a secas, no es_ingreso: la fila INGRESOS de la
    -- maqueta no incluye los ingresos diversos, y reconciliar contra un
    -- perimetro mas amplio que el del patron daria un descuadre inexistente.
    SELECT f.escenario_clave,
           t.periodo,
           sum(f.importe) AS ingresos_modelo,
           count(*)       AS filas_agregadas
    FROM core.fact_escenario f
        JOIN core.dim_tiempo t ON t.fecha_clave   = f.fecha_clave
        JOIN core.dim_cuenta c ON c.cuenta_codigo = f.cuenta_codigo
    WHERE c.grupo = 'Ingresos'
    GROUP BY f.escenario_clave, t.periodo
),
comparacion AS (
    SELECT
        o.escenario_clave,
        o.periodo,
        o.ingresos_oficiales,
        coalesce(m.ingresos_modelo, 0)                         AS ingresos_modelo,
        coalesce(m.ingresos_modelo, 0) - o.ingresos_oficiales  AS diferencia,
        coalesce(m.filas_agregadas, 0)                         AS filas_agregadas,
        -- Misma regla que la etapa 1: escalar y redondear n importes puede
        -- desviar su suma hasta n medias centesimas, de modo que la tolerancia
        -- es funcion del numero de filas agregadas y no un umbral elegido a
        -- ojo. El suelo de 0,05 cubre los periodos con muy pocas filas.
        greatest(0.05, coalesce(m.filas_agregadas, 0) * 0.005) AS tolerancia
    FROM qa.control_reconciliacion o
        LEFT JOIN modelo m
            ON  m.escenario_clave = o.escenario_clave
            AND m.periodo         = o.periodo
)
SELECT *
FROM comparacion
WHERE abs(diferencia) > tolerancia;

COMMENT ON VIEW qa.v_control_reconciliacion_ingresos IS
    'Ingresos del modelo contra los de la maqueta de Control de Gestion, mes a '
    'mes. Es el control que importa: un pipeline financiero no se valida porque '
    'termine sin error, sino porque sus cifras coinciden con el reporte que la '
    'organizacion ya publica. Devuelve una fila por periodo descuadrado.';


-- --- 1b. Perimetro de ingresos de la capa de presentacion ------------------
--
-- El control anterior compara el almacen contra la maqueta. Este compara la
-- capa de presentacion contra el almacen, y existe porque entre los dos habia
-- un hueco por el que se colo un fallo real: pl.v_pl_resumen definia sus
-- ingresos como es_ingreso, que incluye el grupo 'Ingresos Diversos', mientras
-- que la maqueta, el control de reconciliacion y el validador del escenario
-- simulado usan el grupo 'Ingresos' a secas. Las dos agregaciones eran
-- correctas y ninguna alarma salto: el margen publicado del real 2025 era
-- 3,35% y la vista devolvia 3,32%.
--
-- No lleva tolerancia, y no es un descuido. Las dos agregaciones recorren
-- exactamente las mismas filas de la misma tabla, de modo que no hay ningun
-- paso que pueda perder precision: cualquier diferencia es una divergencia de
-- definicion, y una tolerancia solo serviria para esconderla. Es el mismo
-- razonamiento que el control de importe exacto de la carga.
--
-- Encadenado con el control anterior, la composicion da la propiedad que de
-- verdad interesa: presentacion identica al almacen, y almacen reconciliado
-- contra la cifra oficial.

CREATE VIEW qa.v_control_perimetro_ingresos AS
WITH presentacion AS (
    SELECT escenario_clave, periodo, ingresos
    FROM pl.v_pl_resumen
),
almacen AS (
    SELECT f.escenario_clave,
           t.periodo,
           sum(f.importe) AS ingresos
    FROM core.fact_escenario f
        JOIN core.dim_tiempo t ON t.fecha_clave   = f.fecha_clave
        JOIN core.dim_cuenta c ON c.cuenta_codigo = f.cuenta_codigo
    WHERE c.grupo = 'Ingresos'
    GROUP BY f.escenario_clave, t.periodo
)
-- FULL JOIN para que un periodo presente en una capa y ausente en la otra
-- tambien se denuncie, en lugar de desaparecer de la comparacion.
SELECT
    coalesce(p.escenario_clave, a.escenario_clave)    AS escenario_clave,
    coalesce(p.periodo, a.periodo)                    AS periodo,
    p.ingresos                                        AS ingresos_presentacion,
    a.ingresos                                        AS ingresos_almacen,
    coalesce(p.ingresos, 0) - coalesce(a.ingresos, 0) AS diferencia
FROM presentacion p
    FULL JOIN almacen a
        ON  a.escenario_clave = p.escenario_clave
        AND a.periodo         = p.periodo
WHERE p.ingresos IS DISTINCT FROM a.ingresos;

COMMENT ON VIEW qa.v_control_perimetro_ingresos IS
    'Los ingresos que publica pl.v_pl_resumen contra los que suma el hecho para '
    'el grupo Ingresos, mes a mes y sin tolerancia. Vigila que la capa de '
    'presentacion no se separe del perimetro oficial, que es justo lo que ocurrio '
    'una vez: la vista media el margen sobre un perimetro mas amplio que la '
    'maqueta y el descuadre no era visible para ningun otro control, porque el de '
    'reconciliacion compara el hecho y no la vista.';


-- --- 2. Coherencia entre las dos tablas de hechos --------------------------

CREATE VIEW qa.v_control_cuadre_hechos AS
WITH agregado AS (
    SELECT escenario_clave, sum(importe) AS importe, count(*) AS filas
    FROM core.fact_escenario
    GROUP BY escenario_clave
),
detalle AS (
    SELECT escenario_clave, sum(importe) AS importe, count(*) AS filas
    FROM core.fact_resultado
    GROUP BY escenario_clave
),
comparacion AS (
    SELECT
        d.escenario_clave,
        a.importe                      AS importe_agregado,
        d.importe                      AS importe_detalle,
        a.importe - d.importe          AS diferencia,
        a.filas                        AS filas_agregado,
        d.filas                        AS filas_detalle,
        greatest(0.05, a.filas * 0.005) AS tolerancia
    FROM detalle d
        JOIN agregado a ON a.escenario_clave = d.escenario_clave
)
SELECT *
FROM comparacion
WHERE abs(diferencia) > tolerancia;

COMMENT ON VIEW qa.v_control_cuadre_hechos IS
    'El real debe sumar lo mismo en el hecho agregado y en el detalle de '
    'apuntes. Las dos tablas tienen granos distintos y se construyen por caminos '
    'distintos, de modo que coincidir no es trivial. Un descuadre aqui significa '
    'que el mismo dato cuenta dos historias segun el visual que lo mire, que es '
    'el peor fallo posible en un informe.';


-- --- 3. El ejercicio del escenario y el del periodo coinciden --------------

CREATE VIEW qa.v_control_ejercicio_coherente AS
SELECT
    f.escenario_clave,
    e.ejercicio AS ejercicio_escenario,
    t.ejercicio AS ejercicio_periodo,
    count(*)    AS filas,
    sum(f.importe) AS importe
FROM core.fact_escenario f
    JOIN core.dim_escenario e ON e.escenario_clave = f.escenario_clave
    JOIN core.dim_tiempo    t ON t.fecha_clave     = f.fecha_clave
WHERE e.ejercicio <> t.ejercicio
GROUP BY f.escenario_clave, e.ejercicio, t.ejercicio;

COMMENT ON VIEW qa.v_control_ejercicio_coherente IS
    'Ninguna fila del escenario R2025 puede llevar un periodo de 2026. Es la '
    'unica relacion del modelo que ninguna clave foranea cubre, porque escenario '
    'y tiempo son dimensiones independientes y el esquema no sabe que sus '
    'ejercicios tienen que coincidir. Un cruce aqui duplicaria importes en la '
    'variacion interanual.';


-- --- 4. La cobertura declarada coincide con los datos ----------------------

CREATE VIEW qa.v_control_cobertura_periodos AS
SELECT
    e.escenario_clave,
    e.escenario,
    e.periodos_cubiertos            AS periodos_declarados,
    count(DISTINCT f.periodo)       AS periodos_con_datos
FROM core.dim_escenario e
    LEFT JOIN core.fact_escenario f ON f.escenario_clave = e.escenario_clave
GROUP BY e.escenario_clave, e.escenario, e.periodos_cubiertos
HAVING count(DISTINCT f.periodo) <> e.periodos_cubiertos;

COMMENT ON VIEW qa.v_control_cobertura_periodos IS
    'periodos_cubiertos es la columna de la que depende el recorte de la '
    'variacion interanual. Si declarase diez periodos y hubiera datos en doce, o '
    'al reves, la comparacion homogenea dejaria de serlo sin que nada fallase. '
    'El control ata la declaracion a los datos.';


-- --- 5. Toda linea del P&L tiene orden de presentacion ---------------------

CREATE VIEW qa.v_control_orden_pl AS
SELECT
    c.linea_pl,
    count(*)              AS cuentas,
    sum(f.importe)        AS importe_afectado
FROM core.dim_cuenta c
    LEFT JOIN core.fact_escenario f ON f.cuenta_codigo = c.cuenta_codigo
WHERE c.orden_pl = 999
GROUP BY c.linea_pl;

COMMENT ON VIEW qa.v_control_orden_pl IS
    'El centinela 999 marca las lineas sin orden de presentacion asignado, que '
    'en el informe caen descolgadas al pie. El fallo es silencioso -- las cifras '
    'son correctas, solo aparecen en el sitio equivocado -- y basta un acento de '
    'diferencia entre el literal del extracto y la tabla de orden para '
    'provocarlo.';


-- --- Resumen informativo de la carga ---------------------------------------

CREATE VIEW qa.v_resumen_carga AS
SELECT 'core.dim_tiempo'::text          AS tabla, count(*) AS filas, NULL::numeric AS importe_total FROM core.dim_tiempo
UNION ALL SELECT 'core.dim_escenario',  count(*), NULL                       FROM core.dim_escenario
UNION ALL SELECT 'core.dim_centro',     count(*), NULL                       FROM core.dim_centro
UNION ALL SELECT 'core.dim_cuenta',     count(*), NULL                       FROM core.dim_cuenta
UNION ALL SELECT 'core.fact_escenario', count(*), sum(importe)               FROM core.fact_escenario
UNION ALL SELECT 'core.fact_resultado', count(*), sum(importe)               FROM core.fact_resultado
UNION ALL SELECT 'qa.control_reconciliacion', count(*), sum(ingresos_oficiales) FROM qa.control_reconciliacion;

COMMENT ON VIEW qa.v_resumen_carga IS
    'Filas e importe total por tabla. Es lo que el cargador compara contra los '
    'Parquet de origen para demostrar que la transferencia no perdio ni duplico '
    'nada. A diferencia de las vistas v_control_*, siempre devuelve filas.';

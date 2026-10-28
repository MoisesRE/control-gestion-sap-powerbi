-- ===========================================================================
-- 03_indices.sql -- Indices secundarios.
--
-- Un indice no es gratis: ocupa espacio, se recalcula en cada carga y compite
-- por la cache con los datos. Indexar "por si acaso" todas las claves foraneas
-- de un modelo en estrella es un reflejo habitual y casi siempre equivocado,
-- de modo que aqui se declaran solo los que responden a un patron de consulta
-- concreto, y se deja constancia de los que se decidieron no crear.
--
-- Lo que SI se indexa: fact_resultado, 428.589 filas. Es la tabla sobre la que
-- un analista filtra para bajar al apunte -- un centro, un mes, una cuenta --,
-- y es tambien la que recibe el filtro cruzado de Power BI cuando el usuario
-- pincha un centro en un visual.
--
-- Lo que NO se indexa: fact_escenario, 42.017 filas. Su clave primaria ya
-- cubre el acceso por escenario y periodo, que es el grueso de las consultas
-- del P&L, y el resto son agregaciones completas, donde el recorrido
-- secuencial gana siempre.
--
-- Medido, no supuesto
-- -------------------
-- Mediana de siete ejecuciones con cache caliente, PostgreSQL 18.6. La
-- columna "secuencial" se obtuvo desactivando los accesos por indice con
-- enable_indexscan, enable_bitmapscan y enable_indexonlyscan.
--
--   Consulta                                      indice   secuencial   gana
--   -------------------------------------------  -------  -----------  -----
--   fact_resultado WHERE ceco_codigo = ...          0,10 ms   38,34 ms   383x
--   fact_resultado WHERE cuenta_codigo = ...        0,34 ms   47,75 ms   140x
--   fact_resultado WHERE fecha_clave = ...          6,54 ms   40,20 ms     6x
--   fact_escenario WHERE cuenta_codigo = ...          --       2,74 ms     --
--   fact_escenario agregacion por escenario           --       8,92 ms     --
--
-- Las dos ultimas filas son la justificacion de no indexar fact_escenario: sin
-- ningun indice la consulta ya responde en milisegundos, y un indice solo
-- anadiria espacio y tiempo de carga. Los tres indices de fact_resultado
-- ocupan 18 MB sobre una tabla de 74 MB, un 24% de sobrecoste que las cifras
-- de arriba justifican de sobra.
--
-- El indice por periodo gana solo 6 veces y no 383 porque un mes concreto son
-- 35.000 apuntes, el 8% de la tabla: cuando un filtro selecciona esa fraccion
-- el planificador esta en el limite de preferir el recorrido completo. Se
-- conserva porque la auditoria de un cierre mensual es una consulta frecuente
-- y seis veces sigue siendo seis veces, pero es el primero que habria que
-- retirar si el coste de carga importase.
--
-- Tampoco se indexan las claves foraneas del lado hijo. PostgreSQL solo las
-- necesita indexadas para propagar borrados y actualizaciones en cascada sobre
-- el padre, y aqui las dimensiones nunca se borran fila a fila: la carga las
-- vacia enteras con TRUNCATE, que no dispara esa comprobacion.
-- ===========================================================================

CREATE INDEX IF NOT EXISTS fact_resultado_ceco_idx
    ON core.fact_resultado (ceco_codigo);
COMMENT ON INDEX core.fact_resultado_ceco_idx IS
    'Soporta el drill-down por centro de coste sobre el detalle de apuntes.';

CREATE INDEX IF NOT EXISTS fact_resultado_cuenta_idx
    ON core.fact_resultado (cuenta_codigo);
COMMENT ON INDEX core.fact_resultado_cuenta_idx IS
    'Soporta el drill-down por cuenta sobre el detalle de apuntes.';

CREATE INDEX IF NOT EXISTS fact_resultado_periodo_idx
    ON core.fact_resultado (fecha_clave);
COMMENT ON INDEX core.fact_resultado_periodo_idx IS
    'Soporta el filtro por periodo contable, que es el mas frecuente al '
    'auditar un cierre mensual concreto.';

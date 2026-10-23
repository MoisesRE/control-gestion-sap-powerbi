-- ===========================================================================
-- 02_tablas.sql -- Esquema en estrella.
--
-- Decisiones de modelado
-- ----------------------
-- Claves naturales. Las dimensiones se identifican por su codigo ya
-- pseudonimizado ('CC-1043', '6032010101') y no por un entero autoincremental.
-- La clave sustituta es la respuesta correcta en un almacen con historico y
-- dimensiones de cambio lento, donde el mismo codigo de negocio convive con
-- varias versiones de sus atributos; aqui no hay historico que versionar y el
-- ahorro de un integer frente a un texto de siete caracteres no compensa el
-- join adicional que haria falta para leer cualquier cosa. La excepcion es
-- dim_tiempo, cuya clave es el entero inteligente ejercicio*100+periodo:
-- ordenable, legible y verificable con un CHECK.
--
-- numeric y no double precision. La suma en coma flotante no es asociativa, de
-- modo que el total de una columna depende del orden en que PostgreSQL decida
-- agregar las filas. En un informe financiero eso significa que el mismo
-- SELECT puede devolver dos centimos distintos entre ejecuciones. El tipo
-- numeric es decimal exacto y elimina la clase entera de problema.
--
-- Restricciones que son reglas de negocio. Varios CHECK de este fichero no
-- validan tipos: validan afirmaciones del modelo. Que la clave de tiempo se
-- derive de ejercicio y periodo, que clase_pcge sea el primer digito de la
-- cuenta, que es_ingreso coincida con los grupos de ingreso, que los codigos
-- de centro lleven el prefijo del pseudonimo. Todas pueden fallar, y ese es el
-- motivo de declararlas: una carga que las rompa no entra.
-- ===========================================================================

-- --- Dimensiones -----------------------------------------------------------

CREATE TABLE IF NOT EXISTS core.dim_tiempo (
    fecha_clave        integer  NOT NULL,
    ejercicio          smallint NOT NULL,
    periodo            smallint NOT NULL,
    mes_nombre         text     NOT NULL,
    mes_abrev          text     NOT NULL,
    trimestre          smallint NOT NULL,
    etiqueta_trimestre text     NOT NULL,
    etiqueta_mes       text     NOT NULL,
    mes_inicio         date     NOT NULL,
    mes_fin            date     NOT NULL,
    CONSTRAINT dim_tiempo_pk PRIMARY KEY (fecha_clave),
    CONSTRAINT dim_tiempo_periodo_en_rango   CHECK (periodo BETWEEN 1 AND 12),
    CONSTRAINT dim_tiempo_trimestre_en_rango CHECK (trimestre BETWEEN 1 AND 4),
    CONSTRAINT dim_tiempo_clave_derivada     CHECK (fecha_clave = ejercicio * 100 + periodo),
    CONSTRAINT dim_tiempo_trimestre_derivado CHECK (trimestre = (periodo - 1) / 3 + 1),
    CONSTRAINT dim_tiempo_mes_ordenado       CHECK (mes_fin > mes_inicio)
);

COMMENT ON TABLE core.dim_tiempo IS
    'Periodo contable, no fecha natural. El grano es el mes del ejercicio porque '
    'es el periodo contable -- y no la fecha del documento -- lo que determina en '
    'que mes se reconoce un resultado. El extracto no trae los periodos 13 a 16 '
    'de cierre, de modo que el rango valido es 1-12.';
COMMENT ON COLUMN core.dim_tiempo.fecha_clave        IS 'Clave inteligente ejercicio*100+periodo, p. ej. 202503. Un CHECK impone la derivacion.';
COMMENT ON COLUMN core.dim_tiempo.ejercicio          IS 'Ejercicio contable de cuatro digitos.';
COMMENT ON COLUMN core.dim_tiempo.periodo            IS 'Periodo contable 1-12.';
COMMENT ON COLUMN core.dim_tiempo.mes_nombre         IS 'Nombre del mes en castellano, para etiquetas de informe.';
COMMENT ON COLUMN core.dim_tiempo.mes_abrev          IS 'Abreviatura de tres letras del mes.';
COMMENT ON COLUMN core.dim_tiempo.trimestre          IS 'Trimestre natural 1-4, derivado del periodo.';
COMMENT ON COLUMN core.dim_tiempo.etiqueta_trimestre IS 'Etiqueta de trimestre con ejercicio, p. ej. "T1 2025".';
COMMENT ON COLUMN core.dim_tiempo.etiqueta_mes       IS 'Etiqueta de mes con ejercicio, p. ej. "Mar 2025".';
COMMENT ON COLUMN core.dim_tiempo.mes_inicio         IS 'Primer dia natural del periodo. Util para ejes temporales continuos.';
COMMENT ON COLUMN core.dim_tiempo.mes_fin            IS 'Ultimo dia natural del periodo.';


CREATE TABLE IF NOT EXISTS core.dim_escenario (
    escenario_clave    text     NOT NULL,
    escenario          text     NOT NULL,
    tipo_escenario     text     NOT NULL,
    ejercicio          smallint NOT NULL,
    es_simulado        boolean  NOT NULL,
    periodos_cubiertos smallint NOT NULL,
    orden_escenario    smallint NOT NULL,
    CONSTRAINT dim_escenario_pk PRIMARY KEY (escenario_clave),
    CONSTRAINT dim_escenario_clave_formato   CHECK (escenario_clave ~ '^[RP][0-9]{4}$'),
    CONSTRAINT dim_escenario_tipo_valido     CHECK (tipo_escenario IN ('Real', 'Presupuesto')),
    CONSTRAINT dim_escenario_periodos_rango  CHECK (periodos_cubiertos BETWEEN 1 AND 12),
    CONSTRAINT dim_escenario_clave_coherente CHECK (
        escenario_clave = left(tipo_escenario, 1) || ejercicio::text
    )
);

COMMENT ON TABLE core.dim_escenario IS
    'Las cuatro versiones del resultado que el modelo compara. Tres proceden del '
    'libro de Control de Gestion; el real de 2026 esta generado, porque el '
    'ejercicio estaba recien abierto cuando se extrajo el origen y no existia un '
    'real contra el que contrastar su presupuesto.';
COMMENT ON COLUMN core.dim_escenario.escenario_clave    IS 'Clave corta: inicial del tipo mas ejercicio, p. ej. "R2025". Un CHECK impone el formato y la coherencia con tipo_escenario y ejercicio.';
COMMENT ON COLUMN core.dim_escenario.escenario          IS 'Etiqueta legible, con la marca "(simulado)" cuando procede.';
COMMENT ON COLUMN core.dim_escenario.tipo_escenario     IS 'Real (resultado observado) o Presupuesto (objetivo aprobado).';
COMMENT ON COLUMN core.dim_escenario.ejercicio          IS 'Ejercicio al que corresponde el escenario.';
COMMENT ON COLUMN core.dim_escenario.es_simulado        IS 'Verdadero si las cifras estan generadas y no observadas. Es columna del modelo y no nota al pie para que cualquier visual pueda advertirlo y cualquier consulta pueda excluirlo.';
COMMENT ON COLUMN core.dim_escenario.periodos_cubiertos IS 'Periodos con datos. Un ejercicio en curso no cubre los doce, y comparar doce meses contra diez sin tenerlo en cuenta es el error clasico de la variacion interanual.';
COMMENT ON COLUMN core.dim_escenario.orden_escenario    IS 'Orden de presentacion en el informe.';


CREATE TABLE IF NOT EXISTS core.dim_centro (
    ceco_codigo    text NOT NULL,
    ceco_nombre    text NOT NULL,
    ambito         text,
    estructura     text,
    unidad_negocio text,
    CONSTRAINT dim_centro_pk PRIMARY KEY (ceco_codigo),
    CONSTRAINT dim_centro_codigo_pseudonimizado CHECK (ceco_codigo ~ '^CC-[0-9]+$')
);

COMMENT ON TABLE core.dim_centro IS
    'Centro de coste en su version reasignada por Control de Gestion (CeCo '
    'FINAL), que es la que construye el reporte oficial, y no la cruda de SAP. '
    'Los tres atributos de taxonomia se declaran opcionales porque la '
    'clasificacion interna no cubre todos los centros: cuatro carecen de '
    'estructura y de unidad de negocio. Imponer NOT NULL sobre ambito solo '
    'porque hoy esta completo seria declarar una regla que el origen no '
    'garantiza.';
COMMENT ON COLUMN core.dim_centro.ceco_codigo    IS 'Codigo pseudonimizado del centro. El CHECK del prefijo CC- es la defensa contra cargar por error un extracto sin anonimizar en una base destinada a publicarse.';
COMMENT ON COLUMN core.dim_centro.ceco_nombre    IS 'Nombre ficticio del centro. El original contenia toponimos de agencias reales.';
COMMENT ON COLUMN core.dim_centro.ambito         IS 'Taxonomia interna generalizada: ambito del centro.';
COMMENT ON COLUMN core.dim_centro.estructura     IS 'Taxonomia interna generalizada: estructura organizativa.';
COMMENT ON COLUMN core.dim_centro.unidad_negocio IS 'Taxonomia interna generalizada: unidad de negocio.';


CREATE TABLE IF NOT EXISTS core.dim_cuenta (
    cuenta_codigo     text     NOT NULL,
    cuenta_nombre     text     NOT NULL,
    grupo             text     NOT NULL,
    clase_costo_gasto text,
    clase_pcge        text     NOT NULL,
    es_ingreso        boolean  NOT NULL,
    linea_pl          text     NOT NULL,
    orden_pl          smallint NOT NULL,
    CONSTRAINT dim_cuenta_pk PRIMARY KEY (cuenta_codigo),
    CONSTRAINT dim_cuenta_clase_pcge_derivada  CHECK (clase_pcge = left(cuenta_codigo, 1)),
    CONSTRAINT dim_cuenta_clase_valida         CHECK (clase_costo_gasto IN ('COSTO', 'GASTO')),
    CONSTRAINT dim_cuenta_orden_pl_rango       CHECK (orden_pl BETWEEN 10 AND 999),
    CONSTRAINT dim_cuenta_es_ingreso_coherente CHECK (
        es_ingreso = (grupo IN ('Ingresos', 'Ingresos Diversos'))
    )
);

COMMENT ON TABLE core.dim_cuenta IS
    'Cuenta del plan contable general empresarial peruano, con la jerarquia de '
    'presentacion del P&L. Los codigos se conservan en claro porque son un '
    'estandar publico que no identifica a la empresa.';
COMMENT ON COLUMN core.dim_cuenta.cuenta_codigo     IS 'Cuenta agrupada por Control de Gestion (Cta Agrupada), no la clase de coste cruda de SAP.';
COMMENT ON COLUMN core.dim_cuenta.cuenta_nombre     IS 'Denominacion de la cuenta agrupada.';
COMMENT ON COLUMN core.dim_cuenta.grupo             IS 'Una de las 27 agrupaciones en que el reporte oficial presenta el resultado.';
COMMENT ON COLUMN core.dim_cuenta.clase_costo_gasto IS 'Clasificacion COSTO / GASTO del extracto. Opcional: doce cuentas llegan sin ella.';
COMMENT ON COLUMN core.dim_cuenta.clase_pcge        IS 'Primer caracter del codigo, que en el plan peruano codifica la naturaleza: 6 gastos por naturaleza, 7 ingresos. Un CHECK impone la derivacion.';
COMMENT ON COLUMN core.dim_cuenta.es_ingreso        IS 'Verdadero para los grupos de ingreso. Un CHECK lo ata a grupo para que no puedan divergir.';
COMMENT ON COLUMN core.dim_cuenta.linea_pl          IS 'Linea en que la cuenta aparece en el P&L.';
COMMENT ON COLUMN core.dim_cuenta.orden_pl          IS 'Orden de presentacion de arriba abajo. El centinela 999 marca las lineas sin orden asignado, que caerian al pie del informe.';


-- --- Hechos ----------------------------------------------------------------

CREATE TABLE IF NOT EXISTS core.fact_escenario (
    escenario_clave text           NOT NULL,
    fecha_clave     integer        NOT NULL,
    ejercicio       smallint       NOT NULL,
    periodo         smallint       NOT NULL,
    ceco_codigo     text           NOT NULL,
    cuenta_codigo   text           NOT NULL,
    importe         numeric(18, 2) NOT NULL,
    CONSTRAINT fact_escenario_pk PRIMARY KEY (escenario_clave, fecha_clave, ceco_codigo, cuenta_codigo),
    CONSTRAINT fact_escenario_escenario_fk FOREIGN KEY (escenario_clave) REFERENCES core.dim_escenario (escenario_clave),
    CONSTRAINT fact_escenario_tiempo_fk    FOREIGN KEY (fecha_clave)     REFERENCES core.dim_tiempo (fecha_clave),
    CONSTRAINT fact_escenario_centro_fk    FOREIGN KEY (ceco_codigo)     REFERENCES core.dim_centro (ceco_codigo),
    CONSTRAINT fact_escenario_cuenta_fk    FOREIGN KEY (cuenta_codigo)   REFERENCES core.dim_cuenta (cuenta_codigo),
    CONSTRAINT fact_escenario_clave_derivada CHECK (fecha_clave = ejercicio * 100 + periodo)
);

COMMENT ON TABLE core.fact_escenario IS
    'Hecho comparativo al grano escenario x centro x cuenta x periodo. Es la '
    'tabla que alimenta toda comparacion entre escenarios. La clave primaria no '
    'es ceremonia: es el grano declarado como restriccion, de modo que una carga '
    'que duplicase una combinacion seria rechazada en vez de inflar el resultado '
    'en silencio.';
COMMENT ON COLUMN core.fact_escenario.escenario_clave IS 'Escenario al que pertenece la fila.';
COMMENT ON COLUMN core.fact_escenario.fecha_clave     IS 'Periodo contable.';
COMMENT ON COLUMN core.fact_escenario.ejercicio       IS 'Ejercicio, redundante con fecha_clave y atado a ella por un CHECK. Se conserva porque evita un join para el filtro mas frecuente del informe.';
COMMENT ON COLUMN core.fact_escenario.periodo         IS 'Periodo 1-12, redundante con fecha_clave por el mismo motivo.';
COMMENT ON COLUMN core.fact_escenario.ceco_codigo     IS 'Centro de coste reasignado.';
COMMENT ON COLUMN core.fact_escenario.cuenta_codigo   IS 'Cuenta agrupada.';
COMMENT ON COLUMN core.fact_escenario.importe         IS 'Importe en soles con el signo de SAP: ingreso positivo, coste negativo. El convenio hace que el resultado sea la suma directa de la columna, sin condicionales por tipo de linea.';


CREATE TABLE IF NOT EXISTS core.fact_resultado (
    apunte_id            bigint GENERATED ALWAYS AS IDENTITY,
    escenario_clave      text           NOT NULL,
    fecha_clave          integer        NOT NULL,
    ejercicio            smallint       NOT NULL,
    periodo              smallint       NOT NULL,
    ceco_codigo          text           NOT NULL,
    cuenta_codigo        text           NOT NULL,
    importe              numeric(18, 2) NOT NULL,
    fecha_contable       date,
    fecha_documento      date,
    origen_tipo          text           NOT NULL,
    origen_detalle       text           NOT NULL,
    transaccion_sap      text,
    tipo_contrapartida   text,
    marca_reverso        boolean        NOT NULL,
    documento_id         text,
    ceco_origen_codigo   text           NOT NULL,
    cuenta_origen_codigo text           NOT NULL,
    CONSTRAINT fact_resultado_pk PRIMARY KEY (apunte_id),
    CONSTRAINT fact_resultado_escenario_fk FOREIGN KEY (escenario_clave) REFERENCES core.dim_escenario (escenario_clave),
    CONSTRAINT fact_resultado_tiempo_fk    FOREIGN KEY (fecha_clave)     REFERENCES core.dim_tiempo (fecha_clave),
    CONSTRAINT fact_resultado_centro_fk    FOREIGN KEY (ceco_codigo)     REFERENCES core.dim_centro (ceco_codigo),
    CONSTRAINT fact_resultado_cuenta_fk    FOREIGN KEY (cuenta_codigo)   REFERENCES core.dim_cuenta (cuenta_codigo),
    CONSTRAINT fact_resultado_clave_derivada        CHECK (fecha_clave = ejercicio * 100 + periodo),
    CONSTRAINT fact_resultado_origen_pseudonimizado CHECK (ceco_origen_codigo ~ '^CO-[0-9]+$')
);

COMMENT ON TABLE core.fact_resultado IS
    'Detalle transaccional del real observado: una fila por apunte contable. '
    'Existe aparte de fact_escenario porque el real tiene grano de apunte y el '
    'presupuesto grano de centro x cuenta x mes: apilarlos obligaria a cada '
    'medida a saber de que escenario viene la fila antes de poder sumarla. El '
    'real aparece en las dos tablas y qa.v_control_cuadre_hechos comprueba que suman lo '
    'mismo.';
COMMENT ON COLUMN core.fact_resultado.apunte_id            IS 'Clave sustituta del apunte. El origen no ofrece ninguna clave natural: el numero de documento se repite entre lineas y falta en 4.698 apuntes. Se regenera en cada carga y, como el orden del Parquet es estable, el mismo apunte recibe el mismo identificador.';
COMMENT ON COLUMN core.fact_resultado.escenario_clave      IS 'Siempre el real observado. La columna existe para que la relacion con dim_escenario este declarada y no solo documentada en prosa.';
COMMENT ON COLUMN core.fact_resultado.fecha_clave          IS 'Periodo contable del apunte.';
COMMENT ON COLUMN core.fact_resultado.ejercicio            IS 'Ejercicio, atado a fecha_clave por un CHECK.';
COMMENT ON COLUMN core.fact_resultado.periodo              IS 'Periodo 1-12.';
COMMENT ON COLUMN core.fact_resultado.ceco_codigo          IS 'Centro de coste reasignado por Control de Gestion: la clave de analisis.';
COMMENT ON COLUMN core.fact_resultado.cuenta_codigo        IS 'Cuenta agrupada: la clave de analisis.';
COMMENT ON COLUMN core.fact_resultado.importe              IS 'Importe del apunte, con el signo de SAP.';
COMMENT ON COLUMN core.fact_resultado.fecha_contable       IS 'Fecha de contabilizacion, que determina el periodo. Nula en 2.455 apuntes.';
COMMENT ON COLUMN core.fact_resultado.fecha_documento      IS 'Fecha del documento origen. Nula en 2.607 apuntes.';
COMMENT ON COLUMN core.fact_resultado.origen_tipo          IS 'Origen del apunte: F.01, Intercompany o Provision ExtraContable.';
COMMENT ON COLUMN core.fact_resultado.origen_detalle       IS 'Desglose del origen: FBL3N, KSB1, Intercompany, Provision CARGO.';
COMMENT ON COLUMN core.fact_resultado.transaccion_sap      IS 'Operacion original: HRP1 nomina, RFBU contabilidad, RMRP logistica, RFT1 tesoreria.';
COMMENT ON COLUMN core.fact_resultado.tipo_contrapartida   IS 'Clase de cuenta de contrapartida: A activo, D deudor, K acreedor, M material.';
COMMENT ON COLUMN core.fact_resultado.marca_reverso        IS 'Marca de la columna Documento anulacion del extracto, presente en el 37,5% de los apuntes. Es informativa y NO debe filtrarse: no afecta a ningun apunte de ingresos y el reporte oficial se reproduce sumando todo. Se conserva para que la decision sea auditable en lugar de invisible.';
COMMENT ON COLUMN core.fact_resultado.documento_id         IS 'Numero de documento pseudonimizado. Sin CHECK de formato: el pseudonimo y el original son ambos numericos, de modo que una expresion regular no distinguiria uno de otro y seria un control incapaz de fallar.';
COMMENT ON COLUMN core.fact_resultado.ceco_origen_codigo   IS 'Centro de coste crudo de SAP, antes de la reasignacion. Es atributo y no clave foranea: tiene 101 valores frente a los 88 de la dimension, porque la reasignacion consolida centros.';
COMMENT ON COLUMN core.fact_resultado.cuenta_origen_codigo IS 'Clase de coste cruda de SAP. Atributo por el mismo motivo: 243 valores frente a los 152 de la dimension.';


-- --- Patron de reconciliacion ----------------------------------------------

CREATE TABLE IF NOT EXISTS qa.control_reconciliacion (
    escenario_clave    text           NOT NULL,
    periodo            smallint       NOT NULL,
    ingresos_oficiales numeric(18, 2) NOT NULL,
    CONSTRAINT control_reconciliacion_pk PRIMARY KEY (escenario_clave, periodo),
    CONSTRAINT control_reconciliacion_escenario_fk FOREIGN KEY (escenario_clave) REFERENCES core.dim_escenario (escenario_clave),
    CONSTRAINT control_reconciliacion_periodo_rango CHECK (periodo BETWEEN 1 AND 12)
);

COMMENT ON TABLE qa.control_reconciliacion IS
    'Ingresos mensuales segun la maqueta de Control de Gestion, escalados por el '
    'mismo factor que el resto del modelo. Es la cifra oficial, y tenerla en la '
    'base permite repetir la reconciliacion con un SELECT, sin el libro Excel de '
    '165 MB del que procede. Solo contiene los escenarios observados: el real '
    'simulado no tiene cifra oficial, y esa ausencia es informacion, no un hueco.';
COMMENT ON COLUMN qa.control_reconciliacion.escenario_clave    IS 'Escenario observado al que corresponde la cifra.';
COMMENT ON COLUMN qa.control_reconciliacion.periodo            IS 'Periodo contable 1-12.';
COMMENT ON COLUMN qa.control_reconciliacion.ingresos_oficiales IS 'Ingresos del periodo segun la fila INGRESOS de la hoja DETALLE PL, multiplicados por el factor de anonimizacion.';

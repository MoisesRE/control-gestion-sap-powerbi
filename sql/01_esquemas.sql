-- ===========================================================================
-- 01_esquemas.sql -- Esquemas del modelo analitico.
--
-- Tres esquemas en lugar de uno, y la razon no es estetica sino de permisos y
-- de contrato:
--
--   core  Las seis tablas del esquema en estrella. Contiene el detalle
--         transaccional, que es lo mas granular que existe en el modelo.
--   pl    Las vistas que reconstruyen la cuenta de resultados. Es la unica
--         superficie que necesita un consumidor de informes.
--   qa    Los controles de carga y la reconciliacion contra la cifra oficial.
--         Separados de pl para que una vista de diagnostico no acabe en el
--         selector de tablas de Power BI junto a las de negocio.
--
-- La separacion permite conceder lectura sobre pl sin conceder lectura sobre
-- el detalle de apuntes, y deja margen para cambiar el grano de una tabla de
-- core sin romper a quien consume pl. Un unico esquema haria ambas cosas
-- imposibles.
--
-- Alternativa descartada: el esquema public. Es el search_path por defecto de
-- cualquier rol, de modo que todo objeto creado alli queda expuesto por
-- omision en vez de por decision.
-- ===========================================================================

CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS pl;
CREATE SCHEMA IF NOT EXISTS qa;

COMMENT ON SCHEMA core IS
    'Esquema en estrella: dos tablas de hechos y cuatro dimensiones conformadas. '
    'Las cifras estan anonimizadas (pseudonimos deterministas y un factor global '
    'sobre los importes), de modo que los ratios y las variaciones son los reales '
    'pero los valores absolutos no.';

COMMENT ON SCHEMA pl IS
    'Capa de presentacion: vistas que reconstruyen la cuenta de resultados, la '
    'ejecucion presupuestaria y la variacion interanual. Es la superficie que '
    'consume el informe.';

COMMENT ON SCHEMA qa IS
    'Controles de carga y reconciliacion contra la cifra oficial de Control de '
    'Gestion. Cada vista de este esquema puede devolver filas: si devuelve '
    'alguna, hay un descuadre.';

-- Comodidad para la exploracion interactiva con psql. Todo el codigo de este
-- repositorio cualifica los nombres con su esquema, de modo que el valor de
-- search_path no cambia el comportamiento de nada versionado.
DO $$
BEGIN
    EXECUTE format(
        'ALTER DATABASE %I SET search_path = pl, core, qa, public', current_database()
    );
END
$$;

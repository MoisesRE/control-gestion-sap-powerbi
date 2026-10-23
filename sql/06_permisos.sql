-- ===========================================================================
-- 06_permisos.sql -- Rol de lectura del informe.
--
-- bi_reader es un rol de grupo sin LOGIN. No tiene contrasena, de modo que no
-- hay ningun secreto que versionar en este fichero, y un usuario real se
-- conecta con su propia credencial heredando los permisos del grupo:
--
--     CREATE ROLE powerbi LOGIN PASSWORD '...';   -- fuera del repositorio
--     GRANT bi_reader TO powerbi;
--
-- Es el patron habitual de separar quien se autentica de que puede hacer:
-- cambiar los permisos del informe no obliga a tocar ninguna cuenta, y dar de
-- baja a un usuario no deja privilegios huerfanos.
--
-- Dos niveles de acceso, y por que hacen falta los dos
-- ----------------------------------------------------
-- bi_reader sirve a quien consume el informe: lee el P&L y los controles, y no
-- ve el detalle de apuntes. bi_modeler sirve a quien construye el modelo
-- semantico de Power BI, que importa el esquema en estrella de core y por
-- tanto necesita leerlo. Separarlos permite que el consumo habitual siga sin
-- ningun permiso sobre el detalle, en lugar de ampliar bi_reader y dejar a
-- todos los consumidores con mas acceso del que necesitan.
--
-- Por que basta con conceder pl y qa a bi_reader
-- -----------------------------------------------
-- Una vista en PostgreSQL se ejecuta con los permisos de su propietario, no
-- con los de quien la consulta. bi_reader puede por tanto leer el P&L entero
-- sin tener un solo permiso sobre core: la vista accede al detalle en su
-- nombre y le devuelve unicamente el agregado. Es la separacion que motivaba
-- los tres esquemas, y aqui es donde rinde.
-- ===========================================================================

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'bi_reader') THEN
        CREATE ROLE bi_reader NOLOGIN;
    END IF;
END
$$;

COMMENT ON ROLE bi_reader IS
    'Rol de grupo para los consumidores del informe. Lee pl y qa; no tiene '
    'acceso al detalle de apuntes de core.';

GRANT USAGE ON SCHEMA pl TO bi_reader;
GRANT USAGE ON SCHEMA qa TO bi_reader;

GRANT SELECT ON ALL TABLES IN SCHEMA pl TO bi_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA qa TO bi_reader;

-- Las vistas que se creen mas adelante quedan cubiertas sin repetir el GRANT.
ALTER DEFAULT PRIVILEGES IN SCHEMA pl GRANT SELECT ON TABLES TO bi_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA qa GRANT SELECT ON TABLES TO bi_reader;

-- Revocacion explicita sobre core. PostgreSQL no concede nada por defecto a
-- roles nuevos, de modo que estas sentencias no cambian el estado actual: su
-- valor es dejar la intencion escrita, para que un GRANT futuro sobre core
-- sea una decision visible en el diff y no un descuido.
REVOKE ALL ON SCHEMA core FROM bi_reader;
REVOKE ALL ON ALL TABLES IN SCHEMA core FROM bi_reader;


-- --- bi_modeler: el rol que importa el estrella -----------------------------
--
-- Power BI en Import mode consulta las tablas de core directamente, de modo
-- que bi_reader no le sirve: una vista se ejecuta con los permisos de su
-- propietario, pero un SELECT sobre core.fact_escenario no. Este rol anade esa
-- lectura y nada mas.
--
-- Sigue siendo un rol de grupo sin LOGIN y sin contrasena, por el mismo motivo
-- que bi_reader: este fichero se versiona y no debe contener ningun secreto.
-- El usuario real se crea fuera del repositorio y hereda el grupo:
--
--     CREATE ROLE powerbi LOGIN PASSWORD '...';   -- fuera del repositorio
--     GRANT bi_modeler TO powerbi;
--
-- Lectura y nada mas: no hay INSERT, UPDATE, DELETE ni TRUNCATE en ningun
-- esquema. Un informe no escribe en su origen, y conectar Power BI como
-- superusuario -- que es la alternativa comoda -- le daria los cuatro.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'bi_modeler') THEN
        CREATE ROLE bi_modeler NOLOGIN;
    END IF;
END
$$;

COMMENT ON ROLE bi_modeler IS
    'Rol de grupo para el modelo semantico de Power BI. Hereda la lectura de pl '
    'y qa de bi_reader y anade lectura sobre core, que es lo que Import mode '
    'necesita para traerse el esquema en estrella.';

GRANT bi_reader TO bi_modeler;

GRANT USAGE ON SCHEMA core TO bi_modeler;
GRANT SELECT ON ALL TABLES IN SCHEMA core TO bi_modeler;
ALTER DEFAULT PRIVILEGES IN SCHEMA core GRANT SELECT ON TABLES TO bi_modeler;

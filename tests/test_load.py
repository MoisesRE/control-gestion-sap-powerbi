"""Pruebas de la carga en PostgreSQL.

Dos bloques con criterios distintos.

El primero no necesita base: cubre la serializacion al formato CSV que alimenta
a COPY y el contrato entre lo que el ETL escribe y lo que el cargador espera.
Son las piezas donde un fallo es silencioso -- un nulo que se convierte en
cadena vacia no rompe nada, solo cambia los datos.

El segundo exige una base cargada y se salta solo si no la hay. No comprueba
que los controles pasen con el modelo sano, que es lo facil: **rompe el modelo
a proposito y comprueba que cada control lo detecta**. Un control que nunca
falla no es un control. Todo ocurre dentro de una transaccion que siempre se
deshace, de modo que la base queda como estaba.
"""

from __future__ import annotations

from decimal import Decimal

import pandas as pd
import psycopg2
import pytest

from finanzas_etl.config import ConfigPostgres
from finanzas_etl.load import postgres as pg
from finanzas_etl.pipeline import SalidaEtl


def destino(**sobrescribir) -> pg.TablaDestino:
    opciones = {"parquet": "x", "tabla": "core.x"}
    opciones.update(sobrescribir)
    return pg.TablaDestino(**opciones)


def lineas_csv(df: pd.DataFrame, tabla: pg.TablaDestino | None = None) -> list[str]:
    return pg._preparar_csv(df, tabla or destino()).getvalue().splitlines()


# --- Sin base de datos ------------------------------------------------------


class TestSerializacionCsv:
    def test_distingue_el_nulo_de_la_cadena_vacia(self):
        """El fallo que motiva MARCA_NULA.

        Con el convenio por defecto de COPY -- campo vacio igual a nulo -- los
        dos valores de esta prueba llegarian a PostgreSQL como el mismo nulo.
        """
        df = pd.DataFrame({"ancla": ["a", "b", "c"], "texto": ["", None, "hola"]})
        assert lineas_csv(df) == ["a,", "b,\\N", "c,hola"]

    def test_formatea_los_importes_a_dos_decimales(self):
        df = pd.DataFrame({"importe": [1234.5, None], "ancla": ["a", "b"]})
        assert lineas_csv(df, destino(importes=("importe",))) == ["1234.50,a", "\\N,b"]

    def test_no_deja_que_el_flotante_elija_la_representacion(self):
        """Sin formato explicito, pandas escribiria 0.30000000000000004."""
        df = pd.DataFrame({"importe": [0.1 + 0.2], "ancla": ["a"]})
        assert lineas_csv(df, destino(importes=("importe",))) == ["0.30,a"]

    def test_convierte_las_fechas_a_iso(self):
        df = pd.DataFrame(
            {"f": pd.to_datetime(["2025-03-01", None]), "ancla": ["a", "b"]}
        )
        assert lineas_csv(df, destino(fechas=("f",))) == ["2025-03-01,a", "\\N,b"]

    def test_rechaza_un_valor_que_colisione_con_el_marcador(self):
        df = pd.DataFrame({"texto": ["\\N"], "ancla": ["a"]})
        with pytest.raises(ValueError, match="marcador de nulo"):
            lineas_csv(df)


class TestTotalExacto:
    def test_al_volumen_real_la_suma_en_flotante_pierde_el_centimo(self):
        """Por que el total esperado no se calcula sumando la columna.

        428.589 apuntes -- las filas que tiene el detalle -- de 1.234,57 suman
        529.123.121,73 exactos. En coma flotante la acumulacion devuelve
        529.123.121,7299999, de modo que compararla contra el `numeric` de
        PostgreSQL obligaria a inventarse una tolerancia. Sumar en decimal
        elimina la pregunta y permite exigir igualdad estricta.
        """
        serie = pd.Series([1234.57] * 428_589)
        assert float(serie.sum()) != 529_123_121.73
        assert pg.total_exacto(serie) == Decimal("529123121.73")

    def test_ignora_los_nulos(self):
        assert pg.total_exacto(pd.Series([1.5, None, 2.25])) == Decimal("3.75")

    def test_serie_vacia_suma_cero(self):
        assert pg.total_exacto(pd.Series([], dtype="float64")) == Decimal("0")


class TestContratoConElEtl:
    def vacia(self) -> SalidaEtl:
        return SalidaEtl(*(pd.DataFrame() for _ in range(7)))

    def test_se_carga_todo_lo_que_el_etl_escribe(self):
        """Si alguien anade una tabla al ETL y olvida el cargador, falla aqui."""
        salida = self.vacia()
        esperadas = set(salida.tablas()) | set(salida.artefactos())
        assert {d.parquet for d in pg.ORDEN_CARGA} == esperadas

    def test_las_dimensiones_se_cargan_antes_que_los_hechos(self):
        orden = [d.tabla for d in pg.ORDEN_CARGA]
        ultima_dimension = max(i for i, t in enumerate(orden) if ".dim_" in t)
        primer_hecho = min(i for i, t in enumerate(orden) if ".fact_" in t)
        assert ultima_dimension < primer_hecho

    def test_el_patron_de_reconciliacion_vive_en_el_esquema_qa(self):
        reconciliacion = next(
            d for d in pg.ORDEN_CARGA if d.parquet == "control_reconciliacion"
        )
        assert reconciliacion.tabla.startswith("qa.")

    def test_toda_tabla_de_hechos_declara_su_columna_de_importe(self):
        for d in pg.ORDEN_CARGA:
            if ".fact_" in d.tabla:
                assert d.importes, f"{d.tabla} cargaria los importes sin formatear"

    def test_leer_parquet_falla_pronto_si_falta_un_fichero(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="python -m finanzas_etl"):
            pg.leer_parquet(tmp_path)


# --- Con base de datos ------------------------------------------------------


@pytest.fixture
def conexion():
    """Conexion a la base cargada, en una transaccion que siempre se deshace."""
    cfg = ConfigPostgres.desde_entorno()
    if not cfg.password:
        pytest.skip("sin PGPASSWORD configurada")
    try:
        cn = pg.conectar(cfg)
    except (psycopg2.Error, RuntimeError) as exc:
        pytest.skip(f"sin PostgreSQL disponible: {exc}")
    try:
        with cn.cursor() as cur:
            cur.execute("SELECT count(*) FROM core.fact_escenario")
            if cur.fetchone()[0] == 0:
                pytest.skip("la base existe pero esta vacia")
    except psycopg2.Error as exc:
        cn.close()
        pytest.skip(f"el modelo no esta cargado: {exc}")

    try:
        yield cn
    finally:
        cn.rollback()
        cn.close()


def descuadres(cn, vista: str) -> int:
    with cn.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM qa.{vista}")
        return int(cur.fetchone()[0])


@pytest.mark.postgres
class TestControlesDetectanElFallo:
    def test_el_modelo_cargado_no_tiene_descuadres(self, conexion):
        with conexion.cursor() as cur:
            cur.execute(
                "SELECT table_name FROM information_schema.views "
                "WHERE table_schema = 'qa' AND table_name LIKE 'v\\_control\\_%'"
            )
            vistas = [f[0] for f in cur.fetchall()]
        assert vistas, "el DDL de controles no esta aplicado"
        assert {v: descuadres(conexion, v) for v in vistas} == dict.fromkeys(vistas, 0)

    def test_la_reconciliacion_detecta_un_importe_alterado(self, conexion):
        with conexion.cursor() as cur:
            cur.execute("""
                UPDATE core.fact_escenario SET importe = importe + 10000
                WHERE ctid = (
                    SELECT f.ctid FROM core.fact_escenario f
                        JOIN core.dim_cuenta c ON c.cuenta_codigo = f.cuenta_codigo
                    WHERE f.escenario_clave = 'R2025' AND f.periodo = 3
                      AND c.grupo = 'Ingresos'
                    LIMIT 1)
            """)
            assert cur.rowcount == 1
        assert descuadres(conexion, "v_control_reconciliacion_ingresos") == 1

    def test_una_diferencia_bajo_la_tolerancia_no_dispara_el_control(self, conexion):
        """La tolerancia se deriva del redondeo, no se ajusta para que pase."""
        with conexion.cursor() as cur:
            cur.execute("""
                UPDATE core.fact_escenario SET importe = importe + 0.01
                WHERE ctid = (
                    SELECT f.ctid FROM core.fact_escenario f
                        JOIN core.dim_cuenta c ON c.cuenta_codigo = f.cuenta_codigo
                    WHERE f.escenario_clave = 'R2025' AND c.grupo = 'Ingresos'
                    LIMIT 1)
            """)
        assert descuadres(conexion, "v_control_reconciliacion_ingresos") == 0

    def test_el_cuadre_detecta_que_las_dos_tablas_divergen(self, conexion):
        with conexion.cursor() as cur:
            cur.execute(
                "UPDATE core.fact_resultado SET importe = importe + 100000 "
                "WHERE apunte_id = (SELECT min(apunte_id) FROM core.fact_resultado)"
            )
        assert descuadres(conexion, "v_control_cuadre_hechos") == 1

    def test_la_cobertura_detecta_periodos_mal_declarados(self, conexion):
        with conexion.cursor() as cur:
            cur.execute(
                "UPDATE core.dim_escenario SET periodos_cubiertos = 5 "
                "WHERE escenario_clave = 'R2025'"
            )
        assert descuadres(conexion, "v_control_cobertura_periodos") == 1

    def test_detecta_un_periodo_de_otro_ejercicio_en_el_escenario(self, conexion):
        with conexion.cursor() as cur:
            cur.execute("""
                INSERT INTO core.fact_escenario
                    (escenario_clave, fecha_clave, ejercicio, periodo,
                     ceco_codigo, cuenta_codigo, importe)
                SELECT 'R2025', 202611, 2026, 11, ceco_codigo, cuenta_codigo, 0
                FROM core.fact_escenario WHERE escenario_clave = 'R2025' LIMIT 1
            """)
        assert descuadres(conexion, "v_control_ejercicio_coherente") == 1

    def test_detecta_una_linea_del_pl_sin_orden_de_presentacion(self, conexion):
        with conexion.cursor() as cur:
            cur.execute(
                "UPDATE core.dim_cuenta SET orden_pl = 999 "
                "WHERE cuenta_codigo = (SELECT min(cuenta_codigo) FROM core.dim_cuenta)"
            )
        assert descuadres(conexion, "v_control_orden_pl") == 1

    def test_el_perimetro_detecta_que_la_presentacion_se_separa_del_almacen(self, conexion):
        """El fallo que motiva qa.v_control_perimetro_ingresos.

        La vista del P&L media sus ingresos sobre es_ingreso, que incluye el
        grupo 'Ingresos Diversos', mientras que la maqueta, el control de
        reconciliacion y el validador del escenario simulado usan el grupo
        'Ingresos' a secas. Las dos agregaciones eran correctas y ningun control
        podia verlo, porque el de reconciliacion compara el hecho y no la vista.

        La regresion se reintroduce reescribiendo la definicion real de la vista
        en lugar de copiarla aqui: asi la prueba no guarda una version propia
        que pueda quedarse desfasada.
        """
        with conexion.cursor() as cur:
            cur.execute("SELECT pg_get_viewdef('pl.v_pl_resumen'::regclass, true)")
            oficial = cur.fetchone()[0]
            amplio = oficial.replace(
                "FILTER (WHERE grupo = 'Ingresos'::text)",
                "FILTER (WHERE es_ingreso)",
            )
            assert amplio != oficial, "la vista ya no filtra por el grupo Ingresos"
            cur.execute(f"CREATE OR REPLACE VIEW pl.v_pl_resumen AS {amplio}")

        # 46 filas de escenario por periodo, de las que solo descuadran las que
        # tienen algun ingreso diverso.
        assert descuadres(conexion, "v_control_perimetro_ingresos") == 38

    def test_la_presentacion_reproduce_el_margen_publicado(self, conexion):
        """El 3,35% del README sale de la capa SQL, no de una hoja aparte.

        Ata la cifra publicada al modelo: medida sobre el perimetro amplio
        daria 3,3232% y esta prueba lo denunciaria.
        """
        with conexion.cursor() as cur:
            cur.execute("""
                SELECT round(100 * sum(resultado) / sum(ingresos), 4)
                FROM pl.v_pl_resumen WHERE escenario_clave = 'R2025'
            """)
            assert cur.fetchone()[0] == Decimal("3.3515")


@pytest.mark.postgres
class TestElEsquemaImponeLasReglas:
    """Lo que el esquema impide no necesita vista de control, pero si prueba."""

    def test_la_clave_foranea_rechaza_un_centro_inexistente(self, conexion):
        with conexion.cursor() as cur, pytest.raises(psycopg2.errors.ForeignKeyViolation):
            cur.execute("""
                INSERT INTO core.fact_escenario VALUES
                    ('R2025', 202501, 2025, 1, 'CC-999999',
                     (SELECT min(cuenta_codigo) FROM core.dim_cuenta), 1.00)
            """)

    def test_la_clave_primaria_rechaza_duplicar_el_grano(self, conexion):
        with conexion.cursor() as cur, pytest.raises(psycopg2.errors.UniqueViolation):
            cur.execute("""
                INSERT INTO core.fact_escenario
                SELECT escenario_clave, fecha_clave, ejercicio, periodo,
                       ceco_codigo, cuenta_codigo, 1.00
                FROM core.fact_escenario LIMIT 1
            """)

    def test_rechaza_un_centro_sin_pseudonimizar(self, conexion):
        """La defensa contra publicar un extracto real por error."""
        with conexion.cursor() as cur, pytest.raises(psycopg2.errors.CheckViolation):
            cur.execute(
                "INSERT INTO core.dim_centro (ceco_codigo, ceco_nombre) "
                "VALUES ('1043', 'Agencia Lima Norte')"
            )

    def test_rechaza_una_clave_de_tiempo_que_no_deriva_del_periodo(self, conexion):
        with conexion.cursor() as cur, pytest.raises(psycopg2.errors.CheckViolation):
            cur.execute("""
                INSERT INTO core.dim_tiempo VALUES
                    (209901, 2025, 3, 'Marzo', 'Mar', 1, 'T1 2025', 'Mar 2025',
                     '2025-03-01', '2025-03-31')
            """)

    def test_rechaza_una_cuenta_cuyo_es_ingreso_contradice_su_grupo(self, conexion):
        with conexion.cursor() as cur, pytest.raises(psycopg2.errors.CheckViolation):
            cur.execute("""
                INSERT INTO core.dim_cuenta VALUES
                    ('7011999', 'Ventas inventadas', 'Ingresos', 'COSTO', '7',
                     false, 'Ingresos', 10)
            """)


@pytest.mark.postgres
class TestTransferencia:
    def test_el_identificador_cualifica_y_entrecomilla(self, conexion):
        rendido = pg.TablaDestino("x", "core.dim centro").identificador.as_string(conexion)
        assert rendido == '"core"."dim centro"'

    def test_copy_conserva_la_cadena_vacia_y_el_nulo_por_separado(self, conexion):
        """La prueba de extremo a extremo de lo que MARCA_NULA resuelve."""
        with conexion.cursor() as cur:
            cur.execute("CREATE TABLE core.prueba_copy (etiqueta text, valor text)")
            df = pd.DataFrame({"etiqueta": ["vacia", "nula"], "valor": ["", None]})
            pg._copiar(cur, destino(tabla="core.prueba_copy"), df)
            cur.execute(
                "SELECT etiqueta, valor IS NULL FROM core.prueba_copy ORDER BY etiqueta"
            )
            assert cur.fetchall() == [("nula", True), ("vacia", False)]

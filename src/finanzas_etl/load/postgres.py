"""Carga del modelo analitico en PostgreSQL.

Idempotencia
------------
Ejecutar la carga dos veces deja la base exactamente igual que ejecutarla una.
Se consigue con `TRUNCATE ... RESTART IDENTITY` seguido de `COPY`, todo dentro
de una unica transaccion: o entra el modelo completo o no entra nada, y en
ningun momento hay una base a medio cargar que alguien pueda consultar.

La alternativa habitual es un `MERGE` por clave natural, que es lo correcto
cuando la carga es incremental y hay que preservar filas que el origen ya no
trae. Aqui el origen son seis Parquet que se regeneran enteros en cada
ejecucion del ETL: no existe carga incremental que conciliar, y un MERGE
anadiria la complejidad de detectar bajas a cambio de nada.

`RESTART IDENTITY` no es cosmetico. Reinicia la secuencia de `apunte_id`, y
como el orden de las filas del Parquet es estable, cada apunte recibe el mismo
identificador en todas las cargas. Sin ello, el identificador de un apunte
cambiaria en cada ejecucion y dejaria de servir para referenciarlo.

Por que COPY y no INSERT
------------------------
El detalle tiene 428.589 filas. Un INSERT por fila son 428.589 viajes de ida y
vuelta al servidor, cada uno con su analisis sintactico y su registro en el
WAL. COPY transfiere el bloque entero por un unico flujo. La diferencia es de
dos ordenes de magnitud.

Exactitud de la transferencia
-----------------------------
El Parquet guarda los importes en coma flotante; PostgreSQL los guarda en
`numeric`, que es decimal exacto. El puente entre ambos es el formato de dos
decimales con el que este modulo escribe el flujo CSV, y ese formato no pierde
informacion porque los importes ya venian redondeados a dos decimales de la
etapa 1. En consecuencia el total en la base tiene que coincidir **al centimo
exacto** con el total en el Parquet, y el control correspondiente exige
igualdad estricta. Admitir una tolerancia solo serviria para esconder un fallo
de transferencia que no tiene por donde producirse.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

import pandas as pd
import psycopg2
from psycopg2 import extensions as pg_ext
from psycopg2 import sql

from ..config import ConfigPostgres
from ..logging_setup import logger
from ..quality import checks as qc

log = logger("load.postgres")


@dataclass(frozen=True, slots=True)
class TablaDestino:
    """Correspondencia entre un Parquet del ETL y su tabla en PostgreSQL."""

    parquet: str
    tabla: str
    #: Columnas que viajan a un `numeric`: se formatean a dos decimales para
    #: que la conversion sea exacta y no dependa del repr del flotante.
    importes: tuple[str, ...] = ()
    #: Columnas que viajan a un `date`: el Parquet las trae como timestamp.
    fechas: tuple[str, ...] = ()

    @property
    def identificador(self) -> sql.Composed:
        esquema, nombre = self.tabla.split(".")
        return sql.SQL("{}.{}").format(sql.Identifier(esquema), sql.Identifier(nombre))


#: Orden de carga. Las dimensiones van primero porque las claves foraneas se
#: comprueban fila a fila en el momento de insertar: un hecho cargado antes de
#: su dimension seria rechazado aunque la dimension llegase despues en la
#: misma transaccion.
ORDEN_CARGA: tuple[TablaDestino, ...] = (
    TablaDestino("dim_tiempo", "core.dim_tiempo", fechas=("mes_inicio", "mes_fin")),
    TablaDestino("dim_escenario", "core.dim_escenario"),
    TablaDestino("dim_centro", "core.dim_centro"),
    TablaDestino("dim_cuenta", "core.dim_cuenta"),
    TablaDestino("fact_escenario", "core.fact_escenario", importes=("importe",)),
    TablaDestino(
        "fact_resultado",
        "core.fact_resultado",
        importes=("importe",),
        fechas=("fecha_contable", "fecha_documento"),
    ),
    TablaDestino(
        "control_reconciliacion",
        "qa.control_reconciliacion",
        importes=("ingresos_oficiales",),
    ),
)

#: Esquemas que crea el DDL. Se listan para poder recrearlos desde cero.
ESQUEMAS = ("core", "pl", "qa")


# --- pg_ext.connection ---------------------------------------------------------------


def conectar(cfg: ConfigPostgres, *, base: str | None = None) -> pg_ext.connection:
    """Abre una conexion, traduciendo el fallo de autenticacion mas comun.

    El servidor responde en castellano con codificacion de 8 bits y psycopg2
    puede romperse al descodificar el mensaje de error en lugar de mostrarlo.
    Cuando eso ocurre el sintoma es un UnicodeDecodeError que no dice nada, y
    la causa es casi siempre una contrasena incorrecta.
    """
    try:
        return psycopg2.connect(**cfg.parametros(base))
    except UnicodeDecodeError as exc:
        raise RuntimeError(
            f"no se pudo leer la respuesta del servidor al conectar a {cfg}. "
            "Suele significar que PGPASSWORD es incorrecta: el mensaje de error "
            "del servidor llega en castellano y no es descodificable."
        ) from exc


def crear_base(cfg: ConfigPostgres) -> bool:
    """Crea la base del proyecto si no existe. Devuelve si la creo.

    `CREATE DATABASE` no puede ejecutarse dentro de una transaccion, de modo
    que esta funcion se conecta aparte a `postgres` en modo autocommit.
    """
    conn = conectar(cfg, base="postgres")
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (cfg.base,))
            if cur.fetchone() is not None:
                log.info("la base %s ya existe", cfg.base)
                return False
            cur.execute(
                sql.SQL("CREATE DATABASE {}").format(sql.Identifier(cfg.base))
            )
            log.info("base %s creada", cfg.base)
            return True
    finally:
        conn.close()


# --- DDL --------------------------------------------------------------------


def eliminar_esquemas(conn: pg_ext.connection) -> None:
    """Borra los esquemas del proyecto. Solo para recrear la base desde cero."""
    with conn.cursor() as cur:
        for esquema in ESQUEMAS:
            cur.execute(
                sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(esquema))
            )
    conn.commit()
    log.warning("esquemas eliminados: %s", ", ".join(ESQUEMAS))


def aplicar_ddl(conn: pg_ext.connection, carpeta: Path) -> list[Path]:
    """Aplica los ficheros `.sql` de `carpeta` en orden lexicografico.

    El prefijo numerico de los ficheros es la dependencia: los esquemas antes
    que las tablas, las tablas antes que las vistas, las vistas antes que los
    permisos. Todos son idempotentes, de modo que volver a aplicarlos sobre una
    base ya construida no falla ni destruye datos.

    Se descarto una herramienta de migraciones como Alembic o Flyway. Aportan
    control de versiones del esquema y migraciones reversibles, que es lo que
    hace falta cuando hay datos en produccion que no se pueden perder. Aqui el
    esquema se recrea entero desde los Parquet en dos minutos, y ese historial
    de migraciones seria un artefacto que mantener sin nada que proteger.
    """
    ficheros = sorted(carpeta.glob("*.sql"))
    if not ficheros:
        raise FileNotFoundError(f"no hay ficheros .sql en {carpeta}")

    with conn.cursor() as cur:
        for fichero in ficheros:
            log.info("aplicando %s", fichero.name)
            cur.execute(fichero.read_text(encoding="utf-8"))
    conn.commit()
    log.info("DDL aplicado: %d ficheros", len(ficheros))
    return ficheros


# --- Carga ------------------------------------------------------------------


#: Marcador de nulo en el flujo CSV que alimenta a COPY.
#:
#: No se usa el convenio por defecto -- campo vacio significa nulo -- porque el
#: generador de CSV de pandas escribe igual un nulo y una cadena vacia: ambos
#: salen como campo vacio sin comillas, y COPY los leeria como nulo. La cadena
#: vacia es un valor legitimo en una columna de texto, y convertirla en nulo al
#: cargar seria una perdida de informacion silenciosa, que no se manifestaria
#: hasta que alguien filtrase por esa columna meses despues. Con un marcador
#: explicito el campo vacio vuelve a significar cadena vacia y el nulo tiene su
#: propia representacion.
MARCA_NULA = "\\N"


def _preparar_csv(df: pd.DataFrame, destino: TablaDestino) -> io.StringIO:
    """Serializa el DataFrame al formato CSV que espera COPY.

    Los importes se formatean a dos decimales en lugar de dejar que pandas
    escriba el repr del flotante: asi la conversion a `numeric` es exacta y no
    depende de como se represente el valor en coma flotante.
    """
    texto = df.select_dtypes(include=["object", "string", "category"])
    for columna in texto.columns:
        if (texto[columna].astype("string") == MARCA_NULA).any():
            raise ValueError(
                f"{destino.tabla}.{columna} contiene el literal {MARCA_NULA!r}, "
                "que es el marcador de nulo del flujo CSV. Cambiar MARCA_NULA "
                "antes de cargar o el valor se perderia como nulo."
            )

    preparado = df.copy()
    for columna in destino.importes:
        preparado[columna] = preparado[columna].map(
            lambda v: None if pd.isna(v) else f"{v:.2f}"
        )
    for columna in destino.fechas:
        preparado[columna] = pd.to_datetime(preparado[columna]).dt.strftime("%Y-%m-%d")

    buffer = io.StringIO()
    preparado.to_csv(buffer, index=False, header=False, na_rep=MARCA_NULA)
    buffer.seek(0)
    return buffer


def _copiar(cur, destino: TablaDestino, df: pd.DataFrame) -> None:
    # El marcador se escribe con la sintaxis E'...' para que la barra invertida
    # signifique lo mismo con independencia de standard_conforming_strings.
    orden = sql.SQL(r"COPY {} ({}) FROM STDIN WITH (FORMAT csv, NULL E'\\N')").format(
        destino.identificador,
        sql.SQL(", ").join(sql.Identifier(c) for c in df.columns),
    )
    cur.copy_expert(orden.as_string(cur), _preparar_csv(df, destino))
    log.info("%-26s <- %s filas", destino.tabla, f"{len(df):,}")


def leer_parquet(carpeta: Path) -> dict[str, pd.DataFrame]:
    """Lee las tablas del ETL antes de tocar la base.

    Se leen todas por adelantado a proposito: si falta un Parquet o esta
    corrupto, la carga falla sin haber vaciado nada.
    """
    tablas: dict[str, pd.DataFrame] = {}
    for destino in ORDEN_CARGA:
        ruta = carpeta / f"{destino.parquet}.parquet"
        if not ruta.exists():
            raise FileNotFoundError(
                f"falta {ruta.name}. Ejecutar primero el ETL: "
                "PYTHONPATH=src python -m finanzas_etl"
            )
        tablas[destino.tabla] = pd.read_parquet(ruta)
    return tablas


def cargar(conn: pg_ext.connection, tablas: dict[str, pd.DataFrame]) -> None:
    """Vacia y recarga el modelo completo en una sola transaccion."""
    vaciado = sql.SQL("TRUNCATE {} RESTART IDENTITY").format(
        sql.SQL(", ").join(d.identificador for d in ORDEN_CARGA)
    )
    try:
        with conn.cursor() as cur:
            cur.execute(vaciado)
            for destino in ORDEN_CARGA:
                _copiar(cur, destino, tablas[destino.tabla])
            # Sin estadisticas frescas el planificador cree que las tablas
            # siguen vacias y elige planes absurdos en la primera consulta.
            for destino in ORDEN_CARGA:
                cur.execute(sql.SQL("ANALYZE {}").format(destino.identificador))
        conn.commit()
    except Exception:
        conn.rollback()
        log.error("la carga fallo y se deshizo por completo; la base no cambio")
        raise


# --- Verificacion -----------------------------------------------------------


def total_exacto(serie: pd.Series) -> Decimal:
    """Total de una columna de importes en decimal exacto.

    Aplica la misma conversion a dos decimales que alimenta a COPY, de modo que
    el resultado es exactamente lo que PostgreSQL debe tener almacenado. Sumar
    la columna en coma flotante daria un total con error de acumulacion y
    obligaria a inventar una tolerancia para compararlo.
    """
    return sum((Decimal(f"{v:.2f}") for v in serie.dropna()), Decimal("0"))


def _nulos_en_parquet(df: pd.DataFrame) -> int:
    return int(df.isna().sum().sum())


def _nulos_en_tabla(cur, destino: TablaDestino, columnas: list[str]) -> int:
    expresion = sql.SQL(" + ").join(
        sql.SQL("({} IS NULL)::int").format(sql.Identifier(c)) for c in columnas
    )
    cur.execute(
        sql.SQL("SELECT coalesce(sum({}), 0) FROM {}").format(
            expresion, destino.identificador
        )
    )
    return int(cur.fetchone()[0])


def verificar_carga(
    conn: pg_ext.connection, tablas: dict[str, pd.DataFrame], resultado: qc.ResultadoCalidad
) -> qc.ResultadoCalidad:
    """Compara la base contra los Parquet y ejecuta los controles del esquema qa."""
    with conn.cursor() as cur:
        for destino in ORDEN_CARGA:
            df = tablas[destino.tabla]

            cur.execute(sql.SQL("SELECT count(*) FROM {}").format(destino.identificador))
            filas = int(cur.fetchone()[0])
            resultado.agregar(
                qc.Control(
                    nombre=f"Filas transferidas: {destino.tabla}",
                    aprobado=filas == len(df),
                    severidad=qc.Severidad.BLOQUEANTE,
                    detalle=f"Parquet {len(df):,} | PostgreSQL {filas:,}",
                    metricas={"filas_parquet": float(len(df)), "filas_base": float(filas)},
                )
            )

            for columna in destino.importes:
                esperado = total_exacto(df[columna])
                cur.execute(
                    sql.SQL("SELECT coalesce(sum({}), 0) FROM {}").format(
                        sql.Identifier(columna), destino.identificador
                    )
                )
                obtenido = Decimal(cur.fetchone()[0])
                resultado.agregar(
                    qc.Control(
                        nombre=f"Importe exacto: {destino.tabla}.{columna}",
                        aprobado=obtenido == esperado,
                        severidad=qc.Severidad.BLOQUEANTE,
                        detalle=(
                            f"Parquet {esperado:,.2f} | PostgreSQL {obtenido:,.2f} | "
                            f"delta {obtenido - esperado:,.2f} (se exige igualdad exacta)"
                        ),
                        metricas={
                            "total_parquet": float(esperado),
                            "total_base": float(obtenido),
                        },
                    )
                )

            esperados = _nulos_en_parquet(df)
            obtenidos = _nulos_en_tabla(cur, destino, list(df.columns))
            resultado.agregar(
                qc.Control(
                    nombre=f"Nulos preservados: {destino.tabla}",
                    aprobado=obtenidos == esperados,
                    severidad=qc.Severidad.BLOQUEANTE,
                    detalle=(
                        f"Parquet {esperados:,} | PostgreSQL {obtenidos:,}. "
                        "Un exceso en la base delataria que COPY interpreto como "
                        "nulo alguna cadena vacia legitima."
                    ),
                    metricas={
                        "nulos_parquet": float(esperados),
                        "nulos_base": float(obtenidos),
                    },
                )
            )

        _ejecutar_controles_sql(cur, resultado)
    return resultado


def _ejecutar_controles_sql(cur, resultado: qc.ResultadoCalidad) -> None:
    """Ejecuta toda vista `qa.v_control_*` y exige que no devuelva filas.

    Las vistas se descubren en el catalogo en lugar de listarse aqui: anadir un
    control al DDL basta para que este verificador lo ejecute, sin tocar el
    codigo Python. El convenio es que una vista de control devuelve cero filas
    cuando el modelo esta sano, de modo que cada fila es un descuadre.
    """
    cur.execute(
        """
        SELECT table_name
        FROM information_schema.views
        WHERE table_schema = 'qa' AND table_name LIKE 'v\\_control\\_%'
        ORDER BY table_name
        """
    )
    vistas = [fila[0] for fila in cur.fetchall()]
    if not vistas:
        raise RuntimeError(
            "no se encontro ninguna vista qa.v_control_*; el DDL no se aplico"
        )

    for vista in vistas:
        referencia = sql.SQL("qa.{}").format(sql.Identifier(vista))
        cur.execute(sql.SQL("SELECT count(*) FROM {}").format(referencia))
        descuadres = int(cur.fetchone()[0])

        detalle = "sin descuadres"
        if descuadres:
            cur.execute(sql.SQL("SELECT * FROM {} LIMIT 3").format(referencia))
            cabeceras = [c.name for c in cur.description]
            muestra = "; ".join(
                ", ".join(f"{k}={v}" for k, v in zip(cabeceras, fila, strict=True))
                for fila in cur.fetchall()
            )
            detalle = f"{descuadres} filas devueltas. Muestra: {muestra}"

        resultado.agregar(
            qc.Control(
                nombre=f"Control del esquema: qa.{vista}",
                aprobado=descuadres == 0,
                severidad=qc.Severidad.BLOQUEANTE,
                detalle=detalle,
                metricas={"filas_devueltas": float(descuadres)},
            )
        )


# --- Orquestacion -----------------------------------------------------------


@dataclass(slots=True)
class ResultadoCarga:
    base_creada: bool = False
    ficheros_ddl: list[Path] = field(default_factory=list)
    filas: dict[str, int] = field(default_factory=dict)
    calidad: qc.ResultadoCalidad = field(default_factory=qc.ResultadoCalidad)


def ejecutar(
    cfg: ConfigPostgres,
    carpeta_sql: Path,
    carpeta_parquet: Path,
    *,
    recrear: bool = False,
    solo_ddl: bool = False,
) -> ResultadoCarga:
    """Crea la base si falta, aplica el DDL, carga los Parquet y verifica."""
    salida = ResultadoCarga()
    salida.base_creada = crear_base(cfg)

    tablas = {} if solo_ddl else leer_parquet(carpeta_parquet)
    salida.filas = {nombre: len(df) for nombre, df in tablas.items()}

    conn = conectar(cfg)
    try:
        if recrear:
            eliminar_esquemas(conn)
        salida.ficheros_ddl = aplicar_ddl(conn, carpeta_sql)
        if solo_ddl:
            log.warning("--solo-ddl: el esquema esta creado pero sin datos")
            return salida
        cargar(conn, tablas)
        verificar_carga(conn, tablas, salida.calidad)
    finally:
        conn.close()
    return salida

"""Configuracion del pipeline: rutas, secretos y parametros declarativos."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parents[2]


@dataclass(frozen=True, slots=True)
class RutasProyecto:
    raiz: Path = RAIZ
    libro_origen: Path = RAIZ / "Resultado_Financiero.xlsx"
    interim: Path = RAIZ / "data" / "interim"
    procesado: Path = RAIZ / "data" / "processed"
    reportes: Path = RAIZ / "reports"
    #: DDL versionado de la capa PostgreSQL, aplicado en orden lexicografico.
    sql: Path = RAIZ / "sql"

    def preparar(self) -> None:
        for d in (self.interim, self.procesado, self.reportes):
            d.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True, slots=True)
class ConfigAnonimizacion:
    """Parametros de la capa de pseudonimizacion.

    `salt` es la clave HMAC que hace el mapeo reproducible entre ejecuciones.
    Si cambia, cambian todos los pseudonimos y el modelo deja de ser
    comparable con cargas anteriores: es un valor que se fija una vez.
    """

    salt: str
    factor_importe: float

    def __post_init__(self) -> None:
        if len(self.salt) < 16:
            raise ValueError(
                "ANON_SALT debe tener al menos 16 caracteres. "
                'Generar con: python -c "import secrets; print(secrets.token_hex(32))"'
            )
        if not 0.1 <= self.factor_importe <= 10:
            raise ValueError("ANON_FACTOR_IMPORTE fuera del rango razonable [0.1, 10]")


@dataclass(frozen=True, slots=True)
class ConfigPostgres:
    """Conexion a la base analitica de la etapa 2.

    Dos detalles de este PostgreSQL concreto estan fijados aqui a proposito:

    * `client_encoding` se declara explicitamente. El servidor devuelve sus
      mensajes de error en castellano con codificacion de 8 bits, y sin esta
      opcion psycopg2 falla al descodificarlos y lanza un UnicodeDecodeError
      que oculta el error real -- tipicamente, una contrasena incorrecta.
    * `connect_timeout` evita que un servicio parado deje la carga colgada sin
      mensaje.
    """

    host: str = "localhost"
    puerto: int = 5432
    base: str = "finanzas_analytics"
    usuario: str = "postgres"
    password: str = ""
    espera_conexion: int = 10

    @classmethod
    def desde_entorno(cls) -> ConfigPostgres:
        load_dotenv(RAIZ / ".env")
        return cls(
            host=os.getenv("PGHOST", "localhost"),
            puerto=int(os.getenv("PGPORT", "5432")),
            base=os.getenv("PGDATABASE", "finanzas_analytics"),
            usuario=os.getenv("PGUSER", "postgres"),
            password=os.getenv("PGPASSWORD", ""),
        )

    def parametros(self, base: str | None = None) -> dict[str, object]:
        """Argumentos de conexion. `base` permite apuntar a otra, como postgres."""
        return {
            "host": self.host,
            "port": self.puerto,
            "dbname": self.base if base is None else base,
            "user": self.usuario,
            "password": self.password,
            "connect_timeout": self.espera_conexion,
            "client_encoding": "UTF8",
        }

    def __str__(self) -> str:
        return f"{self.usuario}@{self.host}:{self.puerto}/{self.base}"


@dataclass(frozen=True, slots=True)
class FuentePresupuesto:
    """Un presupuesto en formato ancho, con su patron de reconciliacion.

    Los presupuestos viven en libros distintos pero comparten estructura, de
    modo que anadir un ejercicio es anadir una entrada a esta lista y no tocar
    el codigo de extraccion.
    """

    hoja: str
    ejercicio: int
    #: Rotulo de la banda correspondiente en la maqueta del P&L.
    banda_control: str
    #: `None` significa el libro principal.
    libro: Path | None = None
    primera_fila: int = 6

    def resolver_libro(self, principal: Path) -> Path:
        return principal if self.libro is None else self.libro


@dataclass(frozen=True, slots=True)
class ConfigSimulacion:
    """Parametros del escenario real simulado.

    El ejercicio 2026 estaba recien abierto cuando se extrajo el libro, de modo
    que no existe un real con el que comparar su presupuesto. Este bloque
    describe el escenario sintetico que cubre ese hueco. Todo lo que genera
    queda marcado como simulado en el modelo.
    """

    ejercicio: int = 2026
    #: Ultimo periodo con datos simulados. Los posteriores quedan sin cubrir,
    #: igual que ocurriria en un ejercicio en curso.
    ultimo_periodo: int = 10
    #: Semilla del generador. Fija para que el modelo sea reproducible.
    semilla: int = 20260131
    #: Coeficiente del proceso autorregresivo del residuo. Con 0 el residuo es
    #: ruido blanco; cerca de 1, las desviaciones persisten varios meses, que
    #: es como se comporta una serie de gestion.
    persistencia: float = 0.55
    #: Escala del residuo respecto a la volatilidad observada en el real.
    intensidad_residuo: float = 0.8
    #: Cuanto del salto que pide el presupuesto llega a materializarse. Con
    #: 1 el escenario cumpliria el presupuesto linea por linea, lo que
    #: contradice la unica ejecucion observada (88,6% en 2025).
    convergencia_presupuesto: float = 0.35


@dataclass(frozen=True, slots=True)
class ConfigEtl:
    rutas: RutasProyecto = field(default_factory=RutasProyecto)
    anonimizacion: ConfigAnonimizacion | None = None
    simulacion: ConfigSimulacion = field(default_factory=ConfigSimulacion)

    #: Hoja con el detalle transaccional del ejercicio real.
    hoja_real: str = "Data 2025"
    #: Fila (base 1) donde empiezan los datos del detalle.
    primera_fila_real: int = 2

    # -- Patrones de reconciliacion --------------------------------------
    #: Hoja con el P&L oficial de Control de Gestion.
    hoja_maqueta: str = "DETALLE PL"
    #: Rotulo de la banda del ejercicio real dentro de `hoja_maqueta`.
    banda_real: str = "Real 2025"
    #: Fila (base 1) de la linea INGRESOS en `hoja_maqueta`.
    fila_ingresos_maqueta: int = 5

    #: Presupuestos a cargar. El de 2025 llega en un libro aparte.
    presupuestos: tuple[FuentePresupuesto, ...] = (
        FuentePresupuesto(
            hoja="BD_PPTO25",
            ejercicio=2025,
            banda_control="Presupuesto 2025",
            libro=RAIZ / "data" / "raw" / "Presupuesto 2025.xlsx",
        ),
        FuentePresupuesto(
            hoja="BD_PPTO26",
            ejercicio=2026,
            banda_control="Presupuesto 2026",
        ),
    )


def cargar_config(*, requiere_anonimizacion: bool = True) -> ConfigEtl:
    """Construye la configuracion leyendo `.env` si existe."""
    load_dotenv(RAIZ / ".env")
    anon = None
    if requiere_anonimizacion:
        salt = os.getenv("ANON_SALT", "")
        if not salt or salt.startswith("cambiar_por"):
            raise RuntimeError(
                "Falta ANON_SALT. Copiar .env.example a .env y fijar un valor propio."
            )
        anon = ConfigAnonimizacion(
            salt=salt,
            factor_importe=float(os.getenv("ANON_FACTOR_IMPORTE", "1.3742")),
        )
    cfg = ConfigEtl(anonimizacion=anon)
    cfg.rutas.preparar()
    return cfg

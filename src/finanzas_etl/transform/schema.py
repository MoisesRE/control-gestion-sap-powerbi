"""Contrato de columnas entre el extracto SAP y el modelo analitico.

El extracto trae 54 columnas. El modelo conserva 20. Este modulo declara esa
decision de forma explicita y versionable: que entra, con que nombre y tipo, y
sobre todo que se descarta y por que motivo. El criterio de descarte combina
tres razones:

* **Minimizacion de datos personales.** Columnas que identifican a personas
  fisicas (usuario que contabilizo) o a terceros (razon social del proveedor)
  no son necesarias para el analisis de resultados y no se cargan. No se trata
  de anonimizarlas despues: no se extraen.
* **Perdida de precision en origen.** Los identificadores de operacion llegan
  desde Excel como coma flotante (`1.0000909711002E+16`), de modo que los
  ultimos digitos ya son irrecuperables. Un identificador que no identifica es
  ruido.
* **Columna vacia, constante o redundante.** Sin capacidad de discriminar.

Una nota de negocio que condiciona todo el modelo: el extracto trae la pareja
cruda de SAP (`Centro de coste`, `Clase de coste`) y la pareja reasignada por
Control de Gestion (`CeCo FINAL`, `Cta Agrupada`). El reporte oficial se
construye sobre la segunda. El modelo usa la reasignada como clave de analisis
y conserva la cruda como atributo, lo que permite auditar las reasignaciones
sin alterar las cifras.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Sensibilidad(StrEnum):
    """Tratamiento que recibe la columna en la capa de anonimizacion."""

    PUBLICO = "publico"
    """Se publica tal cual. Plan contable estandar, dimensiones de tiempo."""

    PSEUDONIMO = "pseudonimo"
    """Identificador propio de la empresa. Se sustituye de forma determinista."""

    NOMBRE_FICTICIO = "nombre_ficticio"
    """Etiqueta legible por humanos. Se sustituye por una del catalogo ficticio."""

    IMPORTE = "importe"
    """Magnitud monetaria. Se escala por el factor global."""


@dataclass(frozen=True, slots=True)
class Columna:
    indice: int
    """Posicion base 0 en la hoja de origen."""
    origen: str
    """Cabecera literal en el extracto, para trazabilidad."""
    destino: str
    """Nombre en el modelo analitico: snake_case, sin acentos, estable."""
    tipo: str
    """dtype de pandas en el que se materializa."""
    sensibilidad: Sensibilidad = Sensibilidad.PUBLICO
    nota: str = ""


# --- Hoja de detalle real ---------------------------------------------------

COLUMNAS_REAL: tuple[Columna, ...] = (
    Columna(0, "Ejercicio", "ejercicio", "int16"),
    Columna(1, "Periodo", "periodo", "int8", nota="1-12; el extracto no trae periodos 13-16"),
    Columna(9, "Fe.contabilizacion", "fecha_contable", "datetime64[ns]",
            nota="Fecha que determina el periodo del resultado"),
    Columna(8, "Fecha de documento", "fecha_documento", "datetime64[ns]"),
    Columna(5, "Valor/Moneda objeto", "importe", "float64", Sensibilidad.IMPORTE,
            nota="Signo SAP: ingreso positivo, coste negativo"),
    # Dimension centro de coste (reasignado y crudo)
    Columna(39, "CeCo FINAL", "ceco_codigo", "string", Sensibilidad.PSEUDONIMO),
    Columna(40, "Descripcion de CeCo", "ceco_nombre", "string", Sensibilidad.NOMBRE_FICTICIO,
            nota="Contiene topónimos de agencias reales"),
    Columna(2, "Centro de coste", "ceco_origen_codigo", "string", Sensibilidad.PSEUDONIMO,
            nota="CeCo original en SAP, antes de la reasignacion"),
    # Dimension cuenta (agrupada y cruda)
    Columna(36, "Cta Agrupada", "cuenta_codigo", "string",
            nota="Plan contable general peruano; no identifica a la empresa"),
    Columna(37, "NomAgrupador_nuevo", "cuenta_nombre", "string"),
    Columna(38, "Grupo", "grupo", "string", nota="Agrupacion de 27 lineas del P&L"),
    Columna(51, "COSTO O GASTO", "clase_costo_gasto", "string"),
    Columna(3, "Clase de coste", "cuenta_origen_codigo", "string"),
    # Dimension organizativa
    Columna(41, "Costo y Gasto", "unidad_negocio", "string", Sensibilidad.NOMBRE_FICTICIO),
    Columna(42, "Costo Operativo", "ambito", "string", Sensibilidad.NOMBRE_FICTICIO,
            nota="Taxonomia interna; se generaliza junto con unidad_negocio"),
    Columna(50, "Estructura", "estructura", "string", Sensibilidad.NOMBRE_FICTICIO,
            nota="Taxonomia interna; se generaliza junto con unidad_negocio"),
    # Dimension origen del apunte
    Columna(44, "Tipo", "origen_tipo", "string", nota="F.01 / Intercompany / Provision"),
    Columna(45, "Tipo 1", "origen_detalle", "string"),
    Columna(19, "Operacion original", "transaccion_sap", "string",
            nota="HRP1 nomina, RFBU contabilidad, RMRP logistica, RFT1 tesoreria"),
    Columna(22, "Clase cta. de contrapartida", "tipo_contrapartida", "string",
            nota="A activo, D deudor, K acreedor, M material"),
    Columna(35, "Documento anulacion", "marca_reverso", "boolean",
            nota="Marca informativa; NO excluir (ver quality.checks)"),
    Columna(10, "Numero de documento", "documento_id", "string", Sensibilidad.PSEUDONIMO),
)

#: Columnas descartadas, con el motivo. Se usa para generar el diccionario de
#: datos y para que la decision quede documentada en el repositorio.
DESCARTADAS: dict[str, str] = {
    "Usuario": "dato personal: iniciales del empleado que contabilizo",
    "Denominacion cuenta contrapartida": "razon social de proveedores y empleados identificables",
    "Texto de cabecera de documento": "texto libre con nombres de clientes y ubicaciones",
    "Texto de pedido": "texto libre; cobertura 3,3%",
    "Texto breve de material": "texto libre; cobertura 2,2%",
    "Observacion": "texto libre con comentarios internos; cobertura 0,5%",
    "Operacion": "identificador degradado a float por Excel; digitos finales perdidos",
    "Operacion referencia": "identificador degradado a float por Excel",
    "Objeto del interlocutor": "cobertura 0,8%; redundante con Orden partner",
    "Orden partner": "cobertura 1,0%",
    "Documento compras": "cobertura 2,1%",
    "Cta.contrapartida": "identificador de tercero; no se necesita para el resultado",
    "N docum.refer.": "identificador sin uso analitico",
    "Objeto": "duplica Centro de coste",
    "Denom.clase de coste": "duplica la denominacion de la cuenta agrupada",
    "Fecha valor": "se conservan fecha contable y fecha de documento",
    "Fecha entrada": "se conservan fecha contable y fecha de documento",
    "Ud. cantidad contab.": "cobertura 2,7%; el analisis es monetario, no de volumen",
    "Cantidad total reg.": "magnitud no monetaria sin unidad homogenea",
    "Cantidad total": "constante 0 en las 428.589 filas",
    "Tipo de valor": "constante 4",
    "Sociedad": "constante 1100",
    "Cuenta UNE y Soporte": "constante UNE CARGO",
    "Unidad de medida": "columna vacia",
    "Intercompany": "columna vacia",
    "Posicion": "numero de linea dentro del documento; sin uso analitico",
    "Segmento": "duplica Centro de coste en el 97% de los casos",
    "Segmento interloc.": "cobertura 2,3%",
    "Tipo 2": "duplica Tipo 1",
    "Tipo 3": "desglose de Intercompany con cobertura marginal",
}

# --- Hoja de presupuesto (formato ancho: una columna por mes) ---------------

COLUMNAS_PRESUPUESTO: tuple[Columna, ...] = (
    Columna(2, "Costo Gasto", "ambito", "string", Sensibilidad.NOMBRE_FICTICIO),
    Columna(3, "CeCo Tex", "ceco_nombre", "string", Sensibilidad.NOMBRE_FICTICIO),
    Columna(4, "CeCo", "ceco_codigo", "string", Sensibilidad.PSEUDONIMO),
    Columna(5, "Grupo", "grupo", "string"),
    Columna(6, "Cuenta Agrup.", "cuenta_codigo", "string"),
    Columna(7, "CONCEPTOS", "cuenta_nombre", "string"),
)

#: Indice de la primera columna mensual (Ene) en la hoja de presupuesto.
PRIMERA_COLUMNA_MES = 8
MESES = ("Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic")


def ancho_requerido(columnas: tuple[Columna, ...], extra: int = 0) -> int:
    """Numero de columnas que hay que leer de la hoja para cubrir `columnas`."""
    return max(c.indice for c in columnas) + 1 + extra


def por_sensibilidad(
    columnas: tuple[Columna, ...], nivel: Sensibilidad
) -> tuple[str, ...]:
    return tuple(c.destino for c in columnas if c.sensibilidad is nivel)

"""Pruebas del modelo semantico de Power BI.

El modelo esta en TMDL, que es texto, de modo que sus invariantes se pueden
verificar sin abrir Power BI Desktop, sin conexion a PostgreSQL y sin refrescar
nada. Eso importa porque los fallos que cubren estas pruebas **no los detecta el
validador del formato**: el TMDL puede ser sintacticamente perfecto y aun asi
hacer que Desktop se niegue a abrir el proyecto, o que lo abra y ordene mal una
columna sin avisar.

El fichero existe por un fallo concreto. La medida `Ingresos Oficiales` se
llamaba igual que la columna que agrega, y Power BI rechazo el proyecto entero
con *"No se puede crear la medida porque ya existe una columna con el mismo
nombre"* -- despues de que el modelo pasara el round-trip de TMDL y el informe
validase sin un solo aviso. El resto de las pruebas cubren las trampas que la
documentacion del proyecto ya tenia anotadas y que nada comprobaba.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

DEFINICION = (
    Path(__file__).resolve().parents[1]
    / "powerbi"
    / "ResultadoFinanciero.SemanticModel"
    / "definition"
)

# Medidas que devuelven texto y por tanto no llevan formato numerico. Es una
# lista explicita y no una heuristica sobre la expresion: anadir una medida
# numerica sin formatString tiene que hacer fallar la prueba, no colarse porque
# el parser no supo adivinar su tipo.
MEDIDAS_DE_TEXTO = {
    "Es Favorable",
    "Reconciliacion Cuadra",
    # Medidas de formato del P&L: devuelven un cuadrado o un color hexadecimal,
    # no una cifra. El formato condicional por valor de campo las consume.
    "PL Semaforo",
    "PL Semaforo Acumulado",
    "PL Color Fondo",
    "PL Color Texto",
    "PL Color Semaforo",
    "PL Color Semaforo Acumulado",
}

# Medidas cuyo formato depende de la fila en contexto -- un P&L mezcla soles y
# porcentajes en la misma columna -- y que por eso declaran formatStringDefinition
# en lugar de formatString.
MEDIDAS_DE_FORMATO_DINAMICO = {
    "Importe PL",
    "PL Real",
    "PL Ppto",
    "PL Var",
    "PL Real Acum",
    "PL Ppto Acum",
    "PL Var Acum",
}

ACENTOS = "áéíóúñüÁÉÍÓÚÑÜ"


def desencomillar(nombre: str) -> str:
    return nombre[1:-1] if nombre.startswith("'") and nombre.endswith("'") else nombre


def partir_nombre(cabecera: str) -> str:
    """Extrae el nombre de una cabecera TMDL: `measure 'Margen %' =` -> `Margen %`."""
    resto = cabecera.split(maxsplit=1)[1] if " " in cabecera else ""
    if resto.startswith("'"):
        return resto[1 : resto.index("'", 1)]
    return resto.split("=")[0].strip()


def partir_referencia(valor: str) -> tuple[str, str]:
    """Parte `Tabla.'Columna'` o `'Tabla'.'Columna'` en sus dos nombres.

    El separador es el punto que cae fuera de las comillas simples, que es lo que
    obliga a mirar donde cierra la primera cuando el nombre de la tabla lleva
    espacios.
    """
    if valor.startswith("'"):
        cierre = valor.index("'", 1)
        return valor[1:cierre], desencomillar(valor[cierre + 2 :])
    tabla, resto = valor.split(".", 1)
    return tabla, desencomillar(resto)


@dataclass
class Objeto:
    """Una columna o una medida, con sus propiedades y sus banderas."""

    nombre: str
    tabla: str
    descripcion: str | None = None
    propiedades: dict[str, str] = field(default_factory=dict)
    banderas: set[str] = field(default_factory=set)


@dataclass
class Tabla:
    nombre: str
    descripcion: str | None = None
    columnas: list[Objeto] = field(default_factory=list)
    medidas: list[Objeto] = field(default_factory=list)


def leer_tabla(ruta: Path) -> Tabla:
    """Parser de un fichero de tabla TMDL.

    El indentado es significativo y con tabuladores: la tabla no se indenta, sus
    columnas y medidas llevan uno, y sus propiedades dos. Las expresiones DAX
    multilinea quedan a tres o mas, de modo que filtrar por exactamente dos
    tabuladores distingue una propiedad de una linea de codigo que contenga dos
    puntos.
    """
    tabla: Tabla | None = None
    actual: Objeto | None = None
    pendiente: str | None = None

    for linea in ruta.read_text(encoding="utf-8").splitlines():
        if not linea.strip():
            continue
        sangria = len(linea) - len(linea.lstrip("\t"))
        contenido = linea.strip()

        if contenido.startswith("///"):
            pendiente = contenido[3:].strip()
            continue

        if sangria == 0 and contenido.startswith("table "):
            tabla = Tabla(nombre=partir_nombre(contenido), descripcion=pendiente)
            pendiente = None
            actual = None
        elif sangria == 1 and contenido.startswith(("column ", "measure ", "partition ")):
            assert tabla is not None, f"{ruta.name}: objeto antes de la tabla"
            if contenido.startswith("partition "):
                actual = None
            else:
                actual = Objeto(
                    nombre=partir_nombre(contenido),
                    tabla=tabla.nombre,
                    descripcion=pendiente,
                )
                destino = tabla.columnas if contenido.startswith("column ") else tabla.medidas
                destino.append(actual)
            pendiente = None
        elif sangria == 2 and actual is not None:
            if ":" in contenido:
                clave, valor = contenido.split(":", 1)
                actual.propiedades[clave.strip()] = valor.strip()
            else:
                actual.banderas.add(contenido)

    assert tabla is not None, f"{ruta.name}: no declara ninguna tabla"
    return tabla


def leer_relaciones() -> list[tuple[tuple[str, str], tuple[str, str]]]:
    """Devuelve cada relacion como (origen, destino), con origen el lado de muchos."""
    relaciones: list[tuple[tuple[str, str], tuple[str, str]]] = []
    origen: tuple[str, str] | None = None

    for linea in (DEFINICION / "relationships.tmdl").read_text(encoding="utf-8").splitlines():
        contenido = linea.strip()
        if contenido.startswith("fromColumn:"):
            origen = partir_referencia(contenido.split(":", 1)[1].strip())
        elif contenido.startswith("toColumn:"):
            assert origen is not None, "toColumn sin su fromColumn"
            relaciones.append((origen, partir_referencia(contenido.split(":", 1)[1].strip())))
            origen = None

    return relaciones


@pytest.fixture(scope="module")
def tablas() -> list[Tabla]:
    rutas = sorted((DEFINICION / "tables").glob("*.tmdl"))
    assert rutas, f"no hay tablas TMDL en {DEFINICION / 'tables'}"
    return [leer_tabla(r) for r in rutas]


@pytest.fixture(scope="module")
def medidas(tablas: list[Tabla]) -> list[Objeto]:
    return [m for t in tablas for m in t.medidas]


@pytest.fixture(scope="module")
def columnas(tablas: list[Tabla]) -> list[Objeto]:
    return [c for t in tablas for c in t.columnas]


@pytest.fixture(scope="module")
def relaciones() -> list[tuple[tuple[str, str], tuple[str, str]]]:
    return leer_relaciones()


class TestElParserLeeElModelo:
    """Si el parser se equivoca, las demas pruebas pasarian sin comprobar nada."""

    def test_encuentra_las_siete_tablas(self, tablas):
        assert sorted(t.nombre for t in tablas) == [
            "Apuntes",
            "Centro de Coste",
            "Cuenta",
            "Escenario",
            "Linea PL Oficial",
            "Periodo Contable",
            "Reconciliacion Oficial",
            "Resultado",
        ]

    def test_encuentra_las_medidas_y_las_columnas(self, medidas, columnas):
        assert len(medidas) == 48
        assert len(columnas) == 53

    def test_distingue_una_propiedad_de_una_linea_de_dax(self, tablas):
        """`Reconciliacion Cuadra` lleva dos puntos dentro de su expresion."""
        reconciliacion = next(t for t in tablas if t.nombre == "Reconciliacion Oficial")
        cuadra = next(m for m in reconciliacion.medidas if m.nombre == "Reconciliacion Cuadra")
        assert set(cuadra.propiedades) == {"displayFolder", "lineageTag"}


class TestNombres:
    def test_ninguna_medida_se_llama_igual_que_una_columna(self, tablas):
        """El fallo que motiva este fichero.

        Power BI se niega a cargar el proyecto entero -- no la tabla, el proyecto
        -- cuando una medida y una columna de la misma tabla comparten nombre. La
        comprobacion se hace sobre todo el modelo y no solo por tabla, porque el
        espacio de nombres de las medidas es global y una colision entre tablas
        tambien confunde a quien lee el DAX.
        """
        nombres_columna = {c.nombre for t in tablas for c in t.columnas}
        colisiones = sorted(
            f"{m.tabla}[{m.nombre}]"
            for t in tablas
            for m in t.medidas
            if m.nombre in nombres_columna
        )
        assert colisiones == []

    def test_las_medidas_no_se_repiten(self, medidas):
        nombres = [m.nombre for m in medidas]
        repetidas = sorted({n for n in nombres if nombres.count(n) > 1})
        assert repetidas == []

    def test_ningun_identificador_lleva_acentos(self, tablas, medidas, columnas):
        """Criterio del repositorio: los identificadores sin acentos, la prosa con."""
        identificadores = (
            [t.nombre for t in tablas]
            + [f"{m.tabla}[{m.nombre}]" for m in medidas]
            + [f"{c.tabla}[{c.nombre}]" for c in columnas]
        )
        con_acento = sorted(n for n in identificadores if any(c in ACENTOS for c in n))
        assert con_acento == []

    def test_el_detector_de_acentos_distingue(self):
        """Guarda de la prueba anterior.

        Con ACENTOS mal escrito -- vacio, o con las vocales sin tilde dentro --
        la comprobacion de identificadores pasaria siempre o fallaria siempre sin
        comprobar nada. Esto fija los dos extremos.
        """
        assert any(c in ACENTOS for c in "Ejecucións")
        assert not any(c in ACENTOS for c in "Ejecucion presupuestaria")


class TestMedidas:
    def test_toda_medida_tiene_descripcion(self, medidas):
        sin_descripcion = sorted(m.nombre for m in medidas if not m.descripcion)
        assert sin_descripcion == []

    def test_toda_medida_esta_en_una_carpeta(self, medidas):
        sueltas = sorted(m.nombre for m in medidas if "displayFolder" not in m.propiedades)
        assert sueltas == []

    def test_toda_medida_numerica_tiene_formato(self, medidas):
        """Una medida sin formatString hereda el del modelo y sale como salga."""
        sin_formato = sorted(
            m.nombre
            for m in medidas
            if "formatString" not in m.propiedades
            and m.nombre not in MEDIDAS_DE_TEXTO
            and m.nombre not in MEDIDAS_DE_FORMATO_DINAMICO
        )
        assert sin_formato == []

    def test_las_medidas_de_texto_no_llevan_formato_numerico(self, medidas):
        """La lista blanca no puede quedarse obsoleta sin que se note."""
        mal_declaradas = sorted(
            m.nombre
            for m in medidas
            if m.nombre in MEDIDAS_DE_TEXTO and "formatString" in m.propiedades
        )
        assert mal_declaradas == []

    def test_estan_las_familias_que_el_caso_de_negocio_exige(self, medidas):
        nombres = {m.nombre for m in medidas}
        esperadas = {
            "Ingresos",
            "Costes",
            "Resultado Neto",
            "Margen %",
            "Resultado Acumulado",
            "Resultado Presupuesto",
            "Desviacion",
            "Ejecucion %",
            "Variacion Interanual",
        }
        assert esperadas <= nombres


class TestColumnas:
    def test_toda_columna_tiene_descripcion(self, columnas):
        sin_descripcion = sorted(
            f"{c.tabla}[{c.nombre}]" for c in columnas if not c.descripcion
        )
        assert sin_descripcion == []

    def test_las_claves_foraneas_estan_ocultas(self, tablas, relaciones):
        """La regla se deriva de las relaciones, no se adivina por el nombre.

        El lado de muchos de cada relacion es una clave foranea y no significa
        nada en un visual. La clave primaria de una dimension es otra cosa: el
        codigo de cuenta y el de centro quedan visibles a proposito, porque un
        contable los usa.
        """
        por_clave = {(c.tabla, c.nombre): c for t in tablas for c in t.columnas}
        foraneas = [por_clave[origen] for origen, _ in relaciones]
        visibles = sorted(
            f"{c.tabla}[{c.nombre}]" for c in foraneas if "isHidden" not in c.banderas
        )
        assert visibles == []

    def test_las_columnas_de_importe_estan_ocultas(self, columnas):
        """Si se ven, se pueden agregar de forma implicita y saltarse el perimetro."""
        importes = [c for c in columnas if "Importe" in c.nombre]
        assert len(importes) == 3, "se esperaban los dos hechos y la reconciliacion"
        visibles = sorted(
            f"{c.tabla}[{c.nombre}]" for c in importes if "isHidden" not in c.banderas
        )
        assert visibles == []

    def test_el_orden_del_pl_no_es_alfabetico(self, tablas):
        """`Linea PL` tiene que ordenarse por `Orden PL`, o el P&L sale descolocado."""
        cuenta = next(t for t in tablas if t.nombre == "Cuenta")
        linea = next(c for c in cuenta.columnas if c.nombre == "Linea PL")
        assert desencomillar(linea.propiedades.get("sortByColumn", "")) == "Orden PL"

    def test_las_columnas_de_orden_siguen_disponibles_en_mdx(self, tablas):
        """La trampa de ocultar una columna de orden.

        `isAvailableInMdx: false` ahorra memoria en las columnas ocultas, pero en
        una que ordena a otra rompe el orden **sin dar ningun error**: el visual
        vuelve al alfabetico en silencio. Esta prueba recorre cada `sortByColumn`
        del modelo y comprueba que su columna existe y sigue disponible.
        """
        comprobadas = 0
        for tabla in tablas:
            por_nombre = {c.nombre: c for c in tabla.columnas}
            for columna in tabla.columnas:
                referencia = columna.propiedades.get("sortByColumn")
                if not referencia:
                    continue
                destino = desencomillar(referencia)
                assert destino in por_nombre, (
                    f"{tabla.nombre}[{columna.nombre}] ordena por {destino}, que no existe"
                )
                assert por_nombre[destino].propiedades.get("isAvailableInMdx") != "false", (
                    f"{tabla.nombre}[{destino}] ordena a {columna.nombre} pero no esta "
                    "disponible en MDX: el orden se perderia en silencio"
                )
                comprobadas += 1
        assert comprobadas >= 4, "el parser no encontro los sortByColumn del modelo"


class TestModeloYRelaciones:
    def test_la_fecha_automatica_esta_desactivada(self):
        """O Power BI crea una tabla de fechas oculta por cada columna de fecha."""
        modelo = (DEFINICION / "model.tmdl").read_text(encoding="utf-8")
        assert "__PBI_TimeIntelligenceEnabled = 0" in modelo

    def test_el_modelo_desaconseja_las_medidas_implicitas(self):
        modelo = (DEFINICION / "model.tmdl").read_text(encoding="utf-8")
        assert "discourageImplicitMeasures" in modelo

    def test_toda_relacion_apunta_a_columnas_que_existen(self, tablas, relaciones):
        """Una referencia rota deja la relacion inactiva, no da error de sintaxis."""
        existentes = {(t.nombre, c.nombre) for t in tablas for c in t.columnas}
        assert len(relaciones) == 10
        rotas = sorted(
            f"{tabla}[{columna}]"
            for extremos in relaciones
            for tabla, columna in extremos
            if (tabla, columna) not in existentes
        )
        assert rotas == []

    def test_los_hechos_tienen_sus_cuatro_dimensiones(self, relaciones):
        """Las dos tablas de hechos comparten las cuatro dimensiones."""
        for hecho in ("Resultado", "Apuntes"):
            dimensiones = {destino[0] for origen, destino in relaciones if origen[0] == hecho}
            assert dimensiones == {"Escenario", "Periodo Contable", "Cuenta", "Centro de Coste"}

    def test_el_patron_de_reconciliacion_se_relaciona_por_escenario_y_periodo(self, relaciones):
        destinos = {
            destino[0]
            for origen, destino in relaciones
            if origen[0] == "Reconciliacion Oficial"
        }
        assert destinos == {"Escenario", "Periodo Contable"}

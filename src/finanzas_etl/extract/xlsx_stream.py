"""Lectura de hojas XLSX por streaming, con memoria constante.

Motivacion
----------
El libro de origen pesa 165 MB comprimidos y las dos hojas de detalle ocupan
919 MB y 311 MB de XML una vez descomprimidas, con una formula en cada celda.
`pandas.read_excel` (openpyxl) materializa la hoja completa en memoria antes de
construir el DataFrame, lo que en esta hoja supone decenas de GB de objetos
Python intermedios.

Este modulo recorre el XML con un parser incremental y emite una fila a la vez.
El consumo de memoria no depende del numero de filas, de modo que la hoja de
428.589 filas se procesa en unos cientos de MB y en un solo pase.

Detalles del formato que importan aqui
--------------------------------------
* Las celdas de texto no guardan el texto: guardan un indice a la tabla
  `sharedStrings.xml`. Esa tabla si debe cargarse completa (12 MB).
* Las celdas con formula guardan la formula en `<f>` y el ultimo valor
  calculado en `<v>`. Leemos `<v>`: es el valor que el usuario ve en Excel.
* Las celdas vacias se omiten del XML. Una fila no trae necesariamente todas
  sus columnas, por lo que hay que posicionar cada celda por su referencia
  (`r="AC123"`) y no por orden de aparicion.
* `iterparse` conserva los nodos ya procesados colgados de la raiz. Limpiar
  solo el nodo de la fila no basta: hay que vaciar tambien la raiz, o el arbol
  crece hasta agotar la memoria.
"""

from __future__ import annotations

import re
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from xml.etree.ElementTree import iterparse

_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_NS_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"  # noqa: F401
_RE_COL = re.compile(r"([A-Z]+)")

#: Valores de error de Excel que tratamos como ausencia de dato.
ERRORES_EXCEL = frozenset({"#N/A", "#REF!", "#VALUE!", "#DIV/0!", "#NAME?", "#NULL!", "#NUM!"})


def ref_a_indice(ref: str) -> int:
    """Convierte la referencia de una celda en indice de columna base 0.

    >>> ref_a_indice("A1"), ref_a_indice("Z9"), ref_a_indice("AA1"), ref_a_indice("BB428590")
    (0, 25, 26, 53)
    """
    m = _RE_COL.match(ref)
    if not m:
        raise ValueError(f"referencia de celda no reconocida: {ref!r}")
    n = 0
    for ch in m.group(1):
        n = n * 26 + ord(ch) - 64
    return n - 1


@dataclass(frozen=True, slots=True)
class HojaInfo:
    """Localizacion de una hoja dentro del paquete XLSX."""

    nombre: str
    ruta_xml: str
    oculta: bool


class LibroXLSX:
    """Acceso de solo lectura a un libro XLSX, orientado a hojas muy grandes."""

    def __init__(self, ruta: str | Path) -> None:
        self.ruta = Path(ruta)
        if not self.ruta.is_file():
            raise FileNotFoundError(f"no existe el libro: {self.ruta}")
        self._zip = zipfile.ZipFile(self.ruta)
        self._cadenas: list[str] | None = None
        self._hojas: dict[str, HojaInfo] | None = None

    def __enter__(self) -> LibroXLSX:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.cerrar()

    def cerrar(self) -> None:
        self._zip.close()

    # -- metadatos -----------------------------------------------------------

    @property
    def hojas(self) -> dict[str, HojaInfo]:
        """Hojas del libro indexadas por nombre, resolviendo las relaciones.

        El orden de `<sheet>` en workbook.xml no coincide con la numeracion de
        los ficheros `sheetN.xml`: la correspondencia va por `r:id` contra
        workbook.xml.rels. Resolverla por posicion es un error habitual que
        aqui produciria leer la hoja equivocada.
        """
        if self._hojas is None:
            wb = self._zip.read("xl/workbook.xml").decode("utf-8")
            rels = self._zip.read("xl/_rels/workbook.xml.rels").decode("utf-8")
            destino = dict(re.findall(r'Id="(rId\d+)"[^>]*Target="([^"]+)"', rels))

            hojas: dict[str, HojaInfo] = {}
            for bloque in re.findall(r"<sheet\s[^>]*/>", wb):
                nombre = re.search(r'name="([^"]*)"', bloque)
                rid = re.search(r'r:id="(rId\d+)"', bloque)
                if not nombre or not rid:
                    continue
                target = destino[rid.group(1)].lstrip("/")
                ruta = target if target.startswith("xl/") else f"xl/{target}"
                etiqueta = _desescapar(nombre.group(1))
                hojas[etiqueta] = HojaInfo(
                    nombre=etiqueta,
                    ruta_xml=ruta,
                    oculta='state="hidden"' in bloque or 'state="veryHidden"' in bloque,
                )
            self._hojas = hojas
        return self._hojas

    @property
    def cadenas_compartidas(self) -> list[str]:
        """Tabla `sharedStrings`, cargada de forma perezosa y una sola vez."""
        if self._cadenas is None:
            cadenas: list[str] = []
            if "xl/sharedStrings.xml" in self._zip.namelist():
                with self._zip.open("xl/sharedStrings.xml") as f:
                    for _, el in iterparse(f):
                        if el.tag == f"{_NS}si":
                            # Una entrada puede venir partida en varios <t> por
                            # tramos de formato; hay que concatenarlos todos.
                            cadenas.append("".join(t.text or "" for t in el.iter(f"{_NS}t")))
                            el.clear()
            self._cadenas = cadenas
        return self._cadenas

    # -- lectura -------------------------------------------------------------

    def filas(
        self,
        hoja: str,
        *,
        ancho: int | None = None,
        desde_fila: int = 1,
        limite: int | None = None,
    ) -> Iterator[list[str | None]]:
        """Emite las filas de `hoja` como listas de longitud `ancho`.

        Parameters
        ----------
        hoja:
            Nombre tal como aparece en la pestana de Excel.
        ancho:
            Numero de columnas a devolver. Las celdas mas a la derecha se
            descartan. Si es ``None`` se deduce de la primera fila leida.
        desde_fila:
            Primera fila del fichero a emitir (base 1, como en Excel).
        limite:
            Maximo de filas a emitir. Util para inspeccion rapida.

        Yields
        ------
        Listas de cadenas o ``None``. La conversion de tipos no se hace aqui:
        este modulo se limita a entregar el contenido textual de las celdas, y
        la interpretacion queda en la capa de transformacion.
        """
        if hoja not in self.hojas:
            disponibles = ", ".join(sorted(self.hojas))
            raise KeyError(f"la hoja {hoja!r} no existe. Disponibles: {disponibles}")

        cadenas = self.cadenas_compartidas
        emitidas = 0

        with self._zip.open(self.hojas[hoja].ruta_xml) as f:
            contexto = iterparse(f, events=("start", "end"))
            _, raiz = next(contexto)  # <worksheet>

            for evento, el in contexto:
                if evento != "end" or el.tag != f"{_NS}row":
                    continue

                numero = int(el.get("r") or 0)
                if numero < desde_fila:
                    el.clear()
                    raiz.clear()
                    continue

                celdas = _leer_celdas(el, cadenas)
                if ancho is None:
                    ancho = (max(celdas) + 1) if celdas else 0

                yield [celdas.get(i) for i in range(ancho)]

                el.clear()
                raiz.clear()  # sin esto el arbol crece con cada fila procesada

                emitidas += 1
                if limite is not None and emitidas >= limite:
                    return


def _leer_celdas(fila_el, cadenas: list[str]) -> dict[int, str | None]:
    """Extrae `{indice_columna: texto}` de un nodo `<row>`."""
    celdas: dict[int, str | None] = {}
    for c in fila_el.findall(f"{_NS}c"):
        ref = c.get("r")
        if not ref:
            continue
        indice = ref_a_indice(ref)
        tipo = c.get("t")

        if tipo == "inlineStr":
            nodo = c.find(f"{_NS}is")
            valor = (
                "".join(t.text or "" for t in nodo.iter(f"{_NS}t"))
                if nodo is not None
                else None
            )
        else:
            v = c.find(f"{_NS}v")
            if v is None or v.text is None:
                valor = None
            elif tipo == "s":
                valor = cadenas[int(v.text)]
            elif tipo == "e":
                valor = None  # celda en error (#N/A, #REF!): la tratamos como vacia
            elif tipo == "b":
                valor = "1" if v.text == "1" else "0"
            else:
                valor = v.text

        if valor is not None and valor in ERRORES_EXCEL:
            valor = None
        celdas[indice] = valor
    return celdas


def _desescapar(texto: str) -> str:
    """Deshace las entidades XML de los nombres de hoja."""
    return (
        texto.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&apos;", "'")
    )

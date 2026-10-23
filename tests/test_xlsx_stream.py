"""Pruebas del lector XLSX.

Se construyen libros minimos en memoria para cubrir los casos del formato que
el extracto real ejercita: celdas con formula, cadenas compartidas, celdas
vacias omitidas del XML, valores de error y nombres de hoja con entidades.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from finanzas_etl.extract.xlsx_stream import LibroXLSX, ref_a_indice

NS = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
NS_REL = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'


def construir_libro(tmp_path: Path, filas_xml: str, *, nombre_hoja: str = "Datos") -> Path:
    """Escribe un XLSX minimo pero valido con una sola hoja."""
    ruta = tmp_path / "libro.xlsx"
    with zipfile.ZipFile(ruta, "w") as z:
        z.writestr(
            "xl/workbook.xml",
            f'<workbook {NS} {NS_REL}><sheets>'
            f'<sheet name="{nombre_hoja}" sheetId="1" r:id="rId1"/>'
            f"</sheets></workbook>",
        )
        z.writestr(
            "xl/_rels/workbook.xml.rels",
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>',
        )
        z.writestr(
            "xl/sharedStrings.xml",
            f'<sst {NS}><si><t>COMBUSTIBLE</t></si>'
            f"<si><r><t>LUBRI</t></r><r><t>CANTES</t></r></si></sst>",
        )
        z.writestr(
            "xl/worksheets/sheet1.xml",
            f"<worksheet {NS}><sheetData>{filas_xml}</sheetData></worksheet>",
        )
    return ruta


class TestRefAIndice:
    @pytest.mark.parametrize(
        ("ref", "esperado"),
        [("A1", 0), ("B2", 1), ("Z100", 25), ("AA1", 26), ("AB1", 27), ("BB428590", 53)],
    )
    def test_columnas_conocidas(self, ref, esperado):
        assert ref_a_indice(ref) == esperado

    def test_referencia_invalida(self):
        with pytest.raises(ValueError, match="no reconocida"):
            ref_a_indice("123")


class TestLectura:
    def test_lee_numeros_y_cadenas_compartidas(self, tmp_path):
        libro = construir_libro(
            tmp_path,
            '<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1"><v>-1681.74</v></c></row>',
        )
        with LibroXLSX(libro) as lb:
            filas = list(lb.filas("Datos", ancho=2))
        assert filas == [["COMBUSTIBLE", "-1681.74"]]

    def test_concatena_cadenas_con_varios_tramos(self, tmp_path):
        """Una cadena partida por formato debe recomponerse completa."""
        libro = construir_libro(tmp_path, '<row r="1"><c r="A1" t="s"><v>1</v></c></row>')
        with LibroXLSX(libro) as lb:
            assert list(lb.filas("Datos", ancho=1)) == [["LUBRICANTES"]]

    def test_lee_el_valor_cacheado_de_una_formula(self, tmp_path):
        """El valor es sintetico a proposito: ver `auditar_importes`.

        Hasta la etapa 4 este dato de prueba era el ingreso real de un mes del
        extracto, y llevaba ahi desde la etapa 1. Lo que el test demuestra --
        que se lee el `<v>` cacheado y no la formula -- no depende del valor.
        """
        libro = construir_libro(
            tmp_path,
            '<row r="1"><c r="A1"><f>SUM(B1:B9)</f><v>1234567.89</v></c></row>',
        )
        with LibroXLSX(libro) as lb:
            assert list(lb.filas("Datos", ancho=1)) == [["1234567.89"]]

    def test_posiciona_por_referencia_no_por_orden(self, tmp_path):
        """Las celdas vacias se omiten del XML: C1 debe caer en el indice 2."""
        libro = construir_libro(
            tmp_path, '<row r="1"><c r="A1"><v>1</v></c><c r="C1"><v>3</v></c></row>'
        )
        with LibroXLSX(libro) as lb:
            assert list(lb.filas("Datos", ancho=3)) == [["1", None, "3"]]

    def test_celda_en_error_se_trata_como_vacia(self, tmp_path):
        libro = construir_libro(
            tmp_path, '<row r="1"><c r="A1" t="e"><v>#N/A</v></c></row>'
        )
        with LibroXLSX(libro) as lb:
            assert list(lb.filas("Datos", ancho=1)) == [[None]]

    def test_cadena_en_linea(self, tmp_path):
        libro = construir_libro(
            tmp_path, '<row r="1"><c r="A1" t="inlineStr"><is><t>CARGO</t></is></c></row>'
        )
        with LibroXLSX(libro) as lb:
            assert list(lb.filas("Datos", ancho=1)) == [["CARGO"]]

    def test_desde_fila_salta_la_cabecera(self, tmp_path):
        libro = construir_libro(
            tmp_path,
            '<row r="1"><c r="A1"><v>cabecera</v></c></row>'
            '<row r="2"><c r="A2"><v>dato</v></c></row>',
        )
        with LibroXLSX(libro) as lb:
            assert list(lb.filas("Datos", ancho=1, desde_fila=2)) == [["dato"]]

    def test_limite_corta_la_lectura(self, tmp_path):
        filas = "".join(f'<row r="{i}"><c r="A{i}"><v>{i}</v></c></row>' for i in range(1, 11))
        libro = construir_libro(tmp_path, filas)
        with LibroXLSX(libro) as lb:
            assert len(list(lb.filas("Datos", ancho=1, limite=3))) == 3

    def test_ancho_se_deduce_de_la_primera_fila(self, tmp_path):
        libro = construir_libro(
            tmp_path, '<row r="1"><c r="A1"><v>1</v></c><c r="B1"><v>2</v></c></row>'
        )
        with LibroXLSX(libro) as lb:
            assert list(lb.filas("Datos")) == [["1", "2"]]


class TestMetadatos:
    def test_resuelve_el_nombre_con_entidades(self, tmp_path):
        libro = construir_libro(tmp_path, '<row r="1"/>', nombre_hoja="P&amp;G (NEW)")
        with LibroXLSX(libro) as lb:
            assert "P&G (NEW)" in lb.hojas

    def test_hoja_inexistente_lista_las_disponibles(self, tmp_path):
        libro = construir_libro(tmp_path, '<row r="1"/>')
        with LibroXLSX(libro) as lb, pytest.raises(KeyError, match="Disponibles: Datos"):
            list(lb.filas("No existe"))

    def test_libro_inexistente(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            LibroXLSX(tmp_path / "no_existe.xlsx")

"""Pruebas de las conversiones de tipos."""

from __future__ import annotations

import pandas as pd
import pytest

from finanzas_etl.transform.clean import (
    EPOCA_EXCEL,
    anadir_claves_tiempo,
    aplicar_tipos,
    normalizar_texto,
    serial_a_fecha,
    texto_a_bool,
)
from finanzas_etl.transform.schema import Columna


class TestSerialAFecha:
    def test_convierte_seriales_conocidos(self):
        # 45688 es el 31 de enero de 2025 en la convencion de Excel. Es el
        # valor que aparece en la primera fila del extracto real.
        resultado = serial_a_fecha(pd.Series(["45688", "45658"]))
        assert resultado.iloc[0] == pd.Timestamp("2025-01-31")
        assert resultado.iloc[1] == pd.Timestamp("2025-01-01")

    def test_epoca_es_1899_12_30(self):
        """Fija la convencion de Excel, compensando el bisiesto de 1900.

        La conversion se verifica con un serial dentro del rango admitido: el
        serial 1 caeria en 1899 y el propio filtro de plausibilidad lo anula,
        que es el comportamiento deseado y se prueba aparte.
        """
        assert pd.Timestamp("1899-12-30") == EPOCA_EXCEL
        dias = 45688
        assert serial_a_fecha(pd.Series([str(dias)])).iloc[0] == EPOCA_EXCEL + pd.Timedelta(
            days=dias
        )

    def test_anula_fechas_fuera_de_rango(self):
        # Un serial de 1 corresponde a 1899 y delata una celda con basura.
        resultado = serial_a_fecha(pd.Series(["45688", "1", "99999999"]))
        assert resultado.notna().sum() == 1

    def test_rescata_fechas_en_texto(self):
        resultado = serial_a_fecha(pd.Series(["2025-03-15"]))
        assert resultado.iloc[0] == pd.Timestamp("2025-03-15")

    def test_nulos_se_propagan(self):
        assert serial_a_fecha(pd.Series([None, ""])).isna().all()


class TestTextoABool:
    @pytest.mark.parametrize("valor", ["X", "x", "1", "SI", "TRUE"])
    def test_marcas_verdaderas(self, valor):
        assert bool(texto_a_bool(pd.Series([valor])).iloc[0]) is True

    @pytest.mark.parametrize("valor", [None, "", "N", "0"])
    def test_resto_es_falso(self, valor):
        assert bool(texto_a_bool(pd.Series([valor])).iloc[0]) is False


class TestNormalizarTexto:
    def test_recorta_y_anula_vacios(self):
        resultado = normalizar_texto(pd.Series(["  QXZAB90001  ", " ", "", "-"]))
        assert resultado.iloc[0] == "QXZAB90001"
        assert resultado.iloc[1:].isna().all()


class TestAplicarTipos:
    def test_entero_con_nulos_falla(self):
        """Un periodo ausente es un fallo de extraccion, no un dato faltante."""
        columnas = (Columna(0, "Periodo", "periodo", "int8"),)
        with pytest.raises(ValueError, match="no numericos"):
            aplicar_tipos(pd.DataFrame({"periodo": ["1", None]}), columnas)

    def test_float_rellena_con_cero(self):
        columnas = (Columna(0, "Importe", "importe", "float64"),)
        resultado = aplicar_tipos(pd.DataFrame({"importe": ["-1681.74", None]}), columnas)
        assert resultado["importe"].tolist() == [-1681.74, 0.0]

    def test_ignora_columnas_ausentes(self):
        columnas = (Columna(0, "X", "no_existe", "string"),)
        assert aplicar_tipos(pd.DataFrame({"otra": ["a"]}), columnas).empty


class TestClavesTiempo:
    def test_clave_combina_ejercicio_y_periodo(self):
        df = pd.DataFrame({"ejercicio": [2025, 2026], "periodo": [1, 12]})
        resultado = anadir_claves_tiempo(df)
        assert resultado["fecha_clave"].tolist() == [202501, 202612]
        assert resultado["mes_inicio"].iloc[1] == pd.Timestamp("2026-12-01")

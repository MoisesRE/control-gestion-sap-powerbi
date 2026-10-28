"""Pruebas de la capa de anonimizacion.

Estas pruebas cubren las cuatro propiedades que la capa promete: determinismo,
inyectividad en los identificadores, irreversibilidad sin la clave y
conservacion de las razones entre importes.
"""

from __future__ import annotations

import pandas as pd
import pytest

from finanzas_etl.anonymize.mapper import Pseudonimizador
from finanzas_etl.anonymize.scaler import (
    ERROR_REDONDEO_APUNTE,
    comprobar_invariantes,
    error_maximo_agregado,
    escalar_importes,
)

SALT = "clave_de_prueba_no_usar_en_produccion_0123456789"
#: Codigos con la forma del extracto, inventados. La auditoria de fugas
#: recorre tambien los tests, de modo que usar los reales como fixture
#: publicaria en el repositorio justo lo que el pipeline pseudonimiza.
CECOS = pd.Series(["QXZAB90001", "QXZCD90002", "QXZEF90003", "QXZGH90004"])


class TestDeterminismo:
    def test_misma_clave_mismo_resultado(self):
        a = Pseudonimizador(SALT).codigos(CECOS, dominio="ceco", prefijo="CC")
        b = Pseudonimizador(SALT).codigos(CECOS, dominio="ceco", prefijo="CC")
        assert a.tolist() == b.tolist()

    def test_clave_distinta_resultado_distinto(self):
        a = Pseudonimizador(SALT).codigos(CECOS, dominio="ceco", prefijo="CC")
        b = Pseudonimizador(SALT + "x").codigos(CECOS, dominio="ceco", prefijo="CC")
        assert a.tolist() != b.tolist()

    def test_no_depende_del_orden_de_llegada(self):
        """El mapa es funcion de la clave y del conjunto, no del orden."""
        directo = Pseudonimizador(SALT)
        directo.codigos(CECOS, dominio="ceco", prefijo="CC")
        invertido = Pseudonimizador(SALT)
        invertido.codigos(CECOS.iloc[::-1], dominio="ceco", prefijo="CC")
        assert directo.mapas["ceco"] == invertido.mapas["ceco"]

    def test_dominios_distintos_no_comparten_pseudonimo(self):
        """El mismo literal en dos columnas recibe pseudonimos distintos."""
        p = Pseudonimizador(SALT)
        p.codigos(CECOS, dominio="ceco", prefijo="CC")
        p.codigos(CECOS, dominio="ceco_origen", prefijo="CC")
        assert p.mapas["ceco"] != p.mapas["ceco_origen"]


class TestInyectividad:
    def test_identificadores_no_colapsan(self):
        p = Pseudonimizador(SALT)
        p.codigos(CECOS, dominio="ceco", prefijo="CC")
        p.documentos(pd.Series([f"3003{i:05d}" for i in range(500)]))
        p.verificar_inyectividad()

    def test_muchos_valores_siguen_siendo_unicos(self):
        """Comprueba que la resolucion de colisiones funciona a escala."""
        p = Pseudonimizador(SALT)
        serie = pd.Series([f"CECO{i:05d}" for i in range(3000)])
        resultado = p.codigos(serie, dominio="ceco", prefijo="CC")
        assert resultado.nunique() == 3000
        p.verificar_inyectividad()

    def test_taxonomia_puede_colapsar(self):
        """La generalizacion agrupa a proposito y queda exenta del control."""
        p = Pseudonimizador(SALT)
        mapa = p.generalizar_taxonomia(pd.Series(["Ope Marca", "Operaciones Marca"]))
        assert len(set(mapa.values())) < len(mapa)
        p.verificar_inyectividad()  # no debe lanzar


class TestIrreversibilidad:
    def test_el_pseudonimo_no_contiene_el_original(self):
        resultado = Pseudonimizador(SALT).codigos(CECOS, dominio="ceco", prefijo="CC")
        for original, pseudo in zip(CECOS, resultado, strict=True):
            assert original not in pseudo
            assert original[-4:] not in pseudo

    def test_nombres_no_conservan_toponimo(self):
        # Toponimos inventados: la prueba comprueba que el original no
        # sobrevive, y para eso no hace falta usar los reales.
        nombres = pd.Series(["La Pedrera Marca Ag", "Valdeluz Marca- Ag Op"])
        resultado = Pseudonimizador(SALT).nombres_centro(nombres)
        for texto in resultado:
            assert "Pedrera" not in texto
            assert "Valdeluz" not in texto


class TestSaltInvalido:
    def test_salt_corto_se_rechaza(self):
        from finanzas_etl.config import ConfigAnonimizacion

        with pytest.raises(ValueError, match="al menos 16"):
            ConfigAnonimizacion(salt="corto", factor_importe=1.0)

    def test_factor_fuera_de_rango_se_rechaza(self):
        from finanzas_etl.config import ConfigAnonimizacion

        with pytest.raises(ValueError, match="rango razonable"):
            ConfigAnonimizacion(salt=SALT, factor_importe=99.0)


class TestEscalado:
    IMPORTES = pd.Series([-1681.74, 4360071.57, 0.0, -0.01, 12345.678])

    def test_conserva_las_razones_dentro_del_redondeo(self):
        """La razon entre dos apuntes se conserva salvo el efecto del redondeo.

        El redondeo a centimos desplaza cada importe hasta 0,005, de modo que
        el error relativo de una razon esta acotado por 0,005 dividido por el
        menor de los dos importes. Para apuntes pequenos eso es del orden de
        1e-6; afirmar una conservacion exacta seria falso.
        """
        escalada = escalar_importes(self.IMPORTES, 1.3742)
        razon_original = self.IMPORTES.iloc[1] / self.IMPORTES.iloc[0]
        razon_escalada = escalada.iloc[1] / escalada.iloc[0]
        cota = ERROR_REDONDEO_APUNTE / abs(self.IMPORTES.iloc[0] * 1.3742)
        assert razon_escalada == pytest.approx(razon_original, rel=2 * cota)

    def test_razones_entre_agregados_son_practicamente_exactas(self):
        """En las magnitudes del P&L el efecto del redondeo es despreciable."""
        ingresos = pd.Series([4_360_071.57, 3_954_215.22])
        costes = pd.Series([-2_187_659.94, -1_150_672.88])
        factor = 1.3742
        margen_original = ingresos.sum() / abs(costes.sum())
        margen_escalado = escalar_importes(ingresos, factor).sum() / abs(
            escalar_importes(costes, factor).sum()
        )
        assert margen_escalado == pytest.approx(margen_original, rel=1e-9)

    def test_conserva_el_signo(self):
        escalada = escalar_importes(self.IMPORTES, 1.3742)
        comprobar_invariantes(self.IMPORTES, escalada, 1.3742)

    def test_detecta_manipulacion(self):
        escalada = escalar_importes(self.IMPORTES, 1.3742)
        escalada.iloc[0] += 10.0
        with pytest.raises(AssertionError, match="no es proporcional"):
            comprobar_invariantes(self.IMPORTES, escalada, 1.3742)

    def test_desvio_por_apunte_acotado_por_el_redondeo(self):
        escalada = escalar_importes(self.IMPORTES, 1.3742)
        metricas = comprobar_invariantes(self.IMPORTES, escalada, 1.3742)
        assert metricas["desvio_maximo_por_apunte"] <= ERROR_REDONDEO_APUNTE + 1e-9

    def test_factor_invalido_se_rechaza(self):
        with pytest.raises(ValueError, match="rango razonable"):
            escalar_importes(self.IMPORTES, 0.0)

    def test_cota_agregada_crece_con_los_apuntes(self):
        assert error_maximo_agregado(1) == pytest.approx(0.05)
        assert error_maximo_agregado(428_589) == pytest.approx(2142.945)

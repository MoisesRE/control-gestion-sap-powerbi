"""Pruebas de los controles de calidad.

Lo que se prueba aqui es que los controles *detectan* los fallos, no solo que
pasan cuando todo esta bien. Un control que nunca falla no es un control.
"""

from __future__ import annotations

import pandas as pd
import pytest

from finanzas_etl.quality import checks as qc


def hecho_minimo(**sobrescribir) -> pd.DataFrame:
    base = {
        "ejercicio": [2025, 2025],
        "periodo": [1, 2],
        "grupo": ["Ingresos", "Ingresos"],
        "cuenta_codigo": ["7011", "7011"],
        "ceco_codigo": ["CC-1001", "CC-1001"],
        "importe": [100.0, 200.0],
        "marca_reverso": [False, True],
    }
    base.update(sobrescribir)
    return pd.DataFrame(base)


class TestResultadoCalidad:
    def test_exigir_aprobacion_lanza_con_bloqueantes(self):
        r = qc.ResultadoCalidad()
        r.agregar(qc.Control("falla", False, qc.Severidad.BLOQUEANTE, "motivo"))
        with pytest.raises(RuntimeError, match="motivo"):
            r.exigir_aprobacion()

    def test_los_avisos_no_detienen(self):
        r = qc.ResultadoCalidad()
        r.agregar(qc.Control("aviso", False, qc.Severidad.AVISO))
        r.exigir_aprobacion()
        assert r.bloqueantes == []

    def test_markdown_incluye_el_recuento(self):
        r = qc.ResultadoCalidad()
        r.agregar(qc.Control("uno", True, qc.Severidad.AVISO))
        r.agregar(qc.Control("dos", False, qc.Severidad.AVISO))
        assert "**1 de 2 controles superados.**" in r.a_markdown()

    def test_markdown_escapa_las_barras(self):
        r = qc.ResultadoCalidad()
        r.agregar(qc.Control("x", True, qc.Severidad.AVISO, detalle="a|b"))
        assert r"a\|b" in r.a_markdown()


class TestDominios:
    def test_detecta_periodo_fuera_de_rango(self):
        r = qc.ResultadoCalidad()
        qc.validar_dominios(hecho_minimo(periodo=[0, 13]), ejercicios={2025}, resultado=r)
        assert any("rango 1-12" in c.nombre and not c.aprobado for c in r.controles)

    def test_detecta_ejercicio_inesperado(self):
        r = qc.ResultadoCalidad()
        qc.validar_dominios(hecho_minimo(), ejercicios={2024}, resultado=r)
        assert any("Ejercicios esperados" in c.nombre and not c.aprobado for c in r.controles)

    def test_detecta_clave_nula(self):
        r = qc.ResultadoCalidad()
        qc.validar_dominios(
            hecho_minimo(grupo=["Ingresos", None]), ejercicios={2025}, resultado=r
        )
        assert any("Clave sin nulos: grupo" in c.nombre and not c.aprobado for c in r.controles)


class TestDimensionConsistente:
    def test_detecta_codigo_con_dos_descripciones(self):
        df = pd.DataFrame(
            {"ceco_codigo": ["CC-1", "CC-1"], "ceco_nombre": ["Agencia A", "Agencia B"]}
        )
        r = qc.ResultadoCalidad()
        qc.validar_dimension_consistente(df, "ceco_codigo", "ceco_nombre", r)
        assert not r.controles[0].aprobado
        assert r.controles[0].metricas["claves_ambiguas"] == 1.0


class TestReconciliacion:
    CONTROL = pd.Series({1: 100.0, 2: 200.0}, name="maqueta")

    def test_cuadra_exacto(self):
        r = qc.ResultadoCalidad()
        qc.reconciliar_contra_maqueta(hecho_minimo(), self.CONTROL, r)
        assert r.controles[0].aprobado

    def test_detecta_descuadre(self):
        r = qc.ResultadoCalidad()
        qc.reconciliar_contra_maqueta(hecho_minimo(importe=[100.0, 999.0]), self.CONTROL, r)
        assert not r.controles[0].aprobado
        assert r.controles[0].metricas["periodos_descuadrados"] == 1.0

    def test_aplica_el_factor_al_patron(self):
        """Tras escalar, la comparacion es contra la maqueta escalada."""
        r = qc.ResultadoCalidad()
        qc.reconciliar_contra_maqueta(
            hecho_minimo(importe=[200.0, 400.0]), self.CONTROL, r, factor=2.0
        )
        assert r.controles[0].aprobado

    def test_resuelve_el_grupo_desde_la_dimension(self):
        hecho = hecho_minimo().drop(columns=["grupo"])
        dim = pd.DataFrame({"cuenta_codigo": ["7011"], "grupo": ["Ingresos"]})
        r = qc.ResultadoCalidad()
        qc.reconciliar_contra_maqueta(hecho, self.CONTROL, r, dim_cuenta=dim)
        assert r.controles[0].aprobado

    def test_sin_grupo_ni_dimension_falla_claro(self):
        hecho = hecho_minimo().drop(columns=["grupo"])
        with pytest.raises(ValueError, match="pasar dim_cuenta"):
            qc.reconciliar_contra_maqueta(hecho, self.CONTROL, qc.ResultadoCalidad())

    def test_tolerancia_escala_con_los_apuntes(self):
        """Un descuadre de centimos se admite si hay muchos apuntes sumados."""
        muchos = pd.DataFrame(
            {
                "periodo": [1] * 1000,
                "grupo": ["Ingresos"] * 1000,
                "cuenta_codigo": ["7011"] * 1000,
                "importe": [1.0] * 1000,
            }
        )
        r = qc.ResultadoCalidad()
        qc.reconciliar_contra_maqueta(muchos, pd.Series({1: 1000.40}), r)
        assert r.controles[0].aprobado  # 0,40 < 1000 * 0,005


class TestIntegridadReferencial:
    def test_detecta_clave_huerfana(self):
        hecho = hecho_minimo(ceco_codigo=["CC-1001", "CC-9999"])
        dim = pd.DataFrame({"ceco_codigo": ["CC-1001"], "ceco_nombre": ["Agencia"]})
        r = qc.ResultadoCalidad()
        qc.validar_cuadre_agregados(hecho, {"dim_centro": dim}, r)
        assert not r.controles[0].aprobado
        assert "importe afectado" in r.controles[0].detalle


class TestSumaInvariante:
    def test_detecta_perdida_de_importe(self):
        r = qc.ResultadoCalidad()
        qc.validar_suma_invariante(1000.0, 999.0, "una etapa", r)
        assert not r.controles[0].aprobado

    def test_admite_el_redondeo(self):
        r = qc.ResultadoCalidad()
        qc.validar_suma_invariante(1000.0, 1000.009, "una etapa", r)
        assert r.controles[0].aprobado

"""Pruebas del generador del escenario simulado.

El generador promete cuatro cosas: ser reproducible, no inventar actividad
donde el real no la tiene, conservar el volumen y producir residuos con
memoria. Cada una tiene su prueba.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from finanzas_etl.quality.checks import ResultadoCalidad
from finanzas_etl.simulate import validacion as sv
from finanzas_etl.simulate.escenario import (
    MULTIPLICADOR_MAXIMO,
    MULTIPLICADOR_MINIMO,
    _residuos_ar1,
    _tendencia_del_presupuesto,
    simular_real,
)

PARAMETROS = dict(
    ejercicio=2026,
    ultimo_periodo=10,
    semilla=20260131,
    persistencia=0.55,
    intensidad_residuo=0.8,
    convergencia_presupuesto=0.35,
)


@pytest.fixture
def real() -> pd.DataFrame:
    """Dos series continuas de distinto signo y una esporadica.

    La tercera serie solo tiene actividad en dos meses: es el caso que delata
    si el generador rellena los huecos con el nivel medio.
    """
    filas = []
    for periodo in range(1, 13):
        filas.append(("CC-1001", "7011", periodo, 100_000.0 + 5_000 * (periodo % 3)))
        filas.append(("CC-1001", "6311", periodo, -60_000.0 - 2_000 * (periodo % 4)))
    filas.append(("CC-1002", "6343", 3, -40_000.0))
    filas.append(("CC-1002", "6343", 7, -35_000.0))
    df = pd.DataFrame(filas, columns=["ceco_codigo", "cuenta_codigo", "periodo", "importe"])
    df["ejercicio"] = 2025
    return df


@pytest.fixture
def presupuesto(real: pd.DataFrame) -> pd.DataFrame:
    """Presupuesto con ingresos un 10% por encima y costes un 5% por debajo."""
    ppto = real.copy()
    ppto["ejercicio"] = 2026
    factor = np.where(ppto["importe"] > 0, 1.10, 0.95)
    ppto["importe"] = ppto["importe"] * factor
    return ppto


@pytest.fixture
def dim_cuenta() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "cuenta_codigo": ["7011", "6311", "6343"],
            "grupo": ["Ingresos", "Servicio de terceros", "Mantenimiento Unidades"],
        }
    )


class TestResiduosAr1:
    def test_varianza_estacionaria_unitaria(self):
        """La varianza no debe depender de la persistencia elegida."""
        g = np.random.default_rng(7)
        for phi in (0.0, 0.5, 0.9):
            r = _residuos_ar1(400, 120, phi, g)
            assert float(r.std()) == pytest.approx(1.0, abs=0.08)

    def test_la_persistencia_crea_memoria(self):
        g = np.random.default_rng(7)
        sin_memoria = _residuos_ar1(600, 60, 0.0, g)
        con_memoria = _residuos_ar1(600, 60, 0.85, g)

        def autocorrelacion(m: np.ndarray) -> float:
            return float(np.corrcoef(m[:, :-1].ravel(), m[:, 1:].ravel())[0, 1])

        assert abs(autocorrelacion(sin_memoria)) < 0.1
        assert autocorrelacion(con_memoria) > 0.7

    def test_forma_de_la_matriz(self):
        r = _residuos_ar1(5, 10, 0.5, np.random.default_rng(1))
        assert r.shape == (5, 10)


class TestTendencia:
    def test_detecta_crecimiento(self):
        creciente = pd.DataFrame(
            {"periodo": range(1, 13), "importe": [100.0 + 10 * m for m in range(12)]}
        )
        assert _tendencia_del_presupuesto(creciente, 12) > 0

    def test_detecta_decrecimiento(self):
        decreciente = pd.DataFrame(
            {"periodo": range(1, 13), "importe": [200.0 - 10 * m for m in range(12)]}
        )
        assert _tendencia_del_presupuesto(decreciente, 12) < 0

    def test_serie_plana_no_tiene_tendencia(self):
        plana = pd.DataFrame({"periodo": range(1, 13), "importe": [100.0] * 12})
        assert _tendencia_del_presupuesto(plana, 12) == pytest.approx(0.0, abs=1e-9)

    def test_acotada(self):
        """Un presupuesto con un mes atipico no debe producir una rampa."""
        extrema = pd.DataFrame(
            {"periodo": range(1, 13), "importe": [1.0] * 11 + [1000.0]}
        )
        assert abs(_tendencia_del_presupuesto(extrema, 12)) <= 0.015


class TestSimulacion:
    def test_reproducible_con_la_misma_semilla(self, real, presupuesto, dim_cuenta):
        a = simular_real(real, presupuesto, dim_cuenta, **PARAMETROS)
        b = simular_real(real, presupuesto, dim_cuenta, **PARAMETROS)
        pd.testing.assert_frame_equal(a.hechos, b.hechos)

    def test_semilla_distinta_resultado_distinto(self, real, presupuesto, dim_cuenta):
        otros = {**PARAMETROS, "semilla": 999}
        a = simular_real(real, presupuesto, dim_cuenta, **PARAMETROS)
        b = simular_real(real, presupuesto, dim_cuenta, **otros)
        assert not a.hechos["importe"].equals(b.hechos["importe"])

    def test_cubre_solo_los_periodos_pedidos(self, real, presupuesto, dim_cuenta):
        r = simular_real(real, presupuesto, dim_cuenta, **PARAMETROS)
        assert sorted(r.hechos["periodo"].unique()) == list(range(1, 11))
        assert set(r.hechos["ejercicio"]) == {2026}

    def test_respeta_la_esporadicidad(self, real, presupuesto, dim_cuenta):
        """La serie que solo tiene dos meses en el real no gana diez.

        Es el fallo que una rejilla completa de dimensiones introduce sin que
        ningun total lo delate: rellenar los huecos con el nivel medio
        multiplica el volumen de las series esporadicas.
        """
        r = simular_real(real, presupuesto, dim_cuenta, **PARAMETROS)
        esporadica = r.hechos[r.hechos["cuenta_codigo"] == "6343"]
        assert sorted(esporadica["periodo"].tolist()) == [3, 7]

    def test_conserva_el_volumen(self, real, presupuesto, dim_cuenta):
        r = simular_real(real, presupuesto, dim_cuenta, **PARAMETROS)
        meses = range(1, 11)
        vol_real = real.loc[real["periodo"].isin(meses), "importe"].abs().sum()
        vol_sim = r.hechos["importe"].abs().sum()
        assert vol_sim / vol_real == pytest.approx(1.0, abs=0.25)

    def test_no_inventa_dimensiones(self, real, presupuesto, dim_cuenta):
        r = simular_real(real, presupuesto, dim_cuenta, **PARAMETROS)
        assert set(r.hechos["ceco_codigo"]) <= set(real["ceco_codigo"])
        assert set(r.hechos["cuenta_codigo"]) <= set(real["cuenta_codigo"])

    def test_el_multiplicador_no_cambia_el_signo(self, real, presupuesto, dim_cuenta):
        """Con una intensidad absurda, la cota debe seguir protegiendo el signo."""
        agresivo = {**PARAMETROS, "intensidad_residuo": 50.0}
        r = simular_real(real, presupuesto, dim_cuenta, **agresivo)
        unido = r.hechos.merge(
            real.rename(columns={"importe": "importe_real"}),
            on=["ceco_codigo", "cuenta_codigo", "periodo"],
        )
        assert (np.sign(unido["importe"]) == np.sign(unido["importe_real"])).all()

    def test_cotas_del_multiplicador_son_coherentes(self):
        assert 0 < MULTIPLICADOR_MINIMO < 1 < MULTIPLICADOR_MAXIMO

    def test_la_convergencia_modera_la_deriva(self, real, presupuesto, dim_cuenta):
        """Con convergencia 0 el escenario no se mueve hacia el presupuesto."""
        sin_deriva = simular_real(
            real, presupuesto, dim_cuenta, **{**PARAMETROS, "convergencia_presupuesto": 0.0}
        )
        completa = simular_real(
            real, presupuesto, dim_cuenta, **{**PARAMETROS, "convergencia_presupuesto": 1.0}
        )
        assert (sin_deriva.deriva_por_grupo == 1.0).all()
        assert (completa.deriva_por_grupo != 1.0).any()


class TestValidaciones:
    def test_el_grano_se_iguala_antes_de_comparar(self):
        """Dos apuntes opuestos en la misma celda no deben contar como volumen."""
        detalle = pd.DataFrame(
            {
                "ejercicio": [2025] * 2,
                "periodo": [1, 1],
                "ceco_codigo": ["CC-1", "CC-1"],
                "cuenta_codigo": ["6311", "6311"],
                "importe": [1000.0, -1000.0],
            }
        )
        agregado = sv.al_grano_del_simulado(detalle)
        assert len(agregado) == 1
        assert float(agregado["importe"].iloc[0]) == 0.0

    def test_detecta_dimensiones_inventadas(self, real):
        simulado = real.assign(ceco_codigo="CC-NUEVO")
        r = ResultadoCalidad()
        sv.validar_cobertura(real, simulado, r)
        assert not r.controles[0].aprobado

    def test_detecta_volumen_desproporcionado(self, real):
        inflado = real.assign(importe=real["importe"] * 5)
        r = ResultadoCalidad()
        sv.validar_volumen(real, inflado, r)
        assert not r.controles[0].aprobado

    def test_no_exige_correlacion_si_el_real_es_plano(self):
        plano = pd.DataFrame(
            {
                "periodo": list(range(1, 11)),
                "importe": [100.0] * 10,
                "ceco_codigo": ["CC-1"] * 10,
                "cuenta_codigo": ["7011"] * 10,
            }
        )
        desordenado = plano.assign(importe=[100.0, 99.0] * 5)
        r = ResultadoCalidad()
        sv.validar_estacionalidad(plano, desordenado, r)
        assert r.controles[0].aprobado
        assert "no tiene estacionalidad apreciable" in r.controles[0].detalle

    def test_excluye_series_de_suma_nula_del_control_de_signos(self):
        base = pd.DataFrame(
            {
                "periodo": [1, 2],
                "ceco_codigo": ["CC-1", "CC-1"],
                "cuenta_codigo": ["6311", "6311"],
                "importe": [500.0, -500.0],
            }
        )
        simulado = base.assign(importe=[-400.0, 500.0])
        r = ResultadoCalidad()
        sv.validar_signos(base, simulado, r)
        assert r.controles[0].aprobado
        assert "1 series de suma nula excluidas" in r.controles[0].detalle

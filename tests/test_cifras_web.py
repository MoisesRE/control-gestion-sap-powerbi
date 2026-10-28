"""Pruebas de las cifras que publica el dashboard de GitHub Pages.

El dashboard es la pieza que se lee sin clonar el repositorio ni instalar nada,
de modo que sus cifras son las mas expuestas del proyecto y las unicas que un
reclutador va a ver con seguridad. Estas pruebas las fijan contra **la tabla
oficial**, escrita a mano aqui, y no contra la base: una prueba que volviese a
consultar PostgreSQL no podria detectar que el JSON versionado se quedo viejo,
porque regeneraria la respuesta correcta en el momento de comprobarla.

Por eso corren sin base de datos. Lo que verifican es el artefacto publicado.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
CIFRAS = RAIZ / "docs" / "cifras.json"

#: La cuenta de resultados por escenario, tal y como la reproduce el modelo ya
#: anonimizado y la reconcilian las siete consultas de `powerbi/validacion.dax`
#: contra PostgreSQL. Los costes van en negativo, que es el convenio de signo
#: de SAP que el pipeline conserva; la vista los expone en positivo para
#: presentarlos, y el dashboard tiene que coincidir con esta tabla.
OFICIAL = {
    "P2025": {"periodos": 12, "ingresos": 80_553_599.56, "costes": -72_670_331.15,
              "resultado": 8_612_210.85, "margen_pct": 10.69},
    "R2025": {"periodos": 12, "ingresos": 71_341_366.94, "costes": -69_556_781.55,
              "resultado": 2_390_986.16, "margen_pct": 3.35},
    "P2026": {"periodos": 12, "ingresos": 71_737_307.25, "costes": -62_853_717.06,
              "resultado": 9_205_222.84, "margen_pct": 12.83},
    "R2026": {"periodos": 10, "ingresos": 61_403_600.49, "costes": -56_112_588.73,
              "resultado": 5_695_917.93, "margen_pct": 9.28},
}

#: Un centimo: la precision a la que el pipeline reconcilia. No es una
#: tolerancia elegida, es la unidad en la que estan expresados los importes.
CENTIMO = 0.005

#: Tolerancia al comparar una suma hecha en Python con un total agregado por
#: PostgreSQL. El total lo calcula el motor sobre `numeric` y no pierde
#: precision; la suma de este lado recorre hasta 46 dobles de magnitud 1e7, de
#: modo que el error relativo esta acotado por n*eps*suma, unos 7e-7. Se deja
#: en 1e-4, tres ordenes por encima de esa cota y cuatro por debajo del
#: centimo: no puede esconder un descuadre real ni fallar por el redondeo.
#:
#: Es el mismo motivo por el que los importes son `numeric(18,2)` en la base y
#: no coma flotante: aqui no se puede exigir igualdad exacta precisamente
#: porque esto es Python y alli si se puede.
ERROR_SUMA_FLOTANTE = 1e-4


@pytest.fixture(scope="module")
def cifras() -> dict:
    if not CIFRAS.is_file():
        pytest.skip(f"no existe {CIFRAS.name}: generarlo con scripts/generar_cifras_web.py")
    return json.loads(CIFRAS.read_text(encoding="utf-8"))


def por_escenario(cifras: dict) -> dict[str, dict]:
    return {e["escenario_clave"]: e for e in cifras["escenarios"]}


class TestReconciliaContraLaCifraOficial:
    """El criterio del proyecto: toda cifra publicada coincide con la oficial."""

    def test_estan_los_cuatro_escenarios_y_solo_esos(self, cifras):
        assert set(por_escenario(cifras)) == set(OFICIAL)

    @pytest.mark.parametrize("clave", sorted(OFICIAL))
    def test_la_cuenta_de_resultados_coincide_al_centimo(self, cifras, clave):
        publicado = por_escenario(cifras)[clave]
        esperado = OFICIAL[clave]
        assert publicado["periodos"] == esperado["periodos"]
        # La vista expone el coste en positivo para presentarlo; la tabla
        # oficial conserva el signo de SAP.
        assert abs(-publicado["costes"] - esperado["costes"]) < CENTIMO
        for campo in ("ingresos", "resultado", "margen_pct"):
            assert abs(publicado[campo] - esperado[campo]) < CENTIMO, campo

    def test_la_ejecucion_presupuestaria_reproduce_lo_publicado(self, cifras):
        """88,6% en 2025 sobre doce meses y 104,8% en 2026 sobre diez."""
        ejecucion = {e["ejercicio"]: e for e in cifras["ejecucion"]}
        assert round(ejecucion[2025]["ejecucion_pct"], 1) == 88.6
        assert round(ejecucion[2026]["ejecucion_pct"], 1) == 104.8

    def test_publica_tambien_la_ejecucion_sin_recortar(self, cifras):
        """La trampa documentada: sin el recorte, 2026 saldria en el 85%.

        Las dos cifras van en el JSON a proposito. Ensenar solo la buena seria
        esconder que la comparacion honesta exige recortar los periodos.
        """
        ejecucion = {e["ejercicio"]: e for e in cifras["ejecucion"]}
        assert round(ejecucion[2026]["ejecucion_pct_sin_recorte"], 1) == 85.6
        assert ejecucion[2026]["periodos_comparables"] == 10
        assert ejecucion[2026]["periodos_totales"] == 12

    def test_la_reconciliacion_contra_la_maqueta_cuadra(self, cifras):
        """Tres escenarios tienen patron oficial; el simulado no, y no debe.

        Un escenario que nadie presupuesto no descuadra contra la maqueta: no
        esta en ella. Es el fallo que la etapa 3 encontro en la tarjeta de
        control del informe.
        """
        filas = {r["escenario_clave"]: r for r in cifras["reconciliacion"]}
        assert set(filas) == {"P2025", "R2025", "P2026"}
        for clave, fila in filas.items():
            assert abs(fila["diferencia"]) <= fila["tolerancia"], clave


class TestCoherenciaInterna:
    """Los bloques del JSON se calculan por separado y tienen que cuadrar.

    Es el mismo argumento que el de medir una cifra en SQL y en DAX: dos
    caminos independientes que coinciden no pueden estar los dos mal del mismo
    modo. Aqui el total del escenario viene de una agregacion y el detalle de
    otra, de modo que un perimetro mal puesto en una de las dos sale aqui.
    """

    @pytest.mark.parametrize("clave", sorted(OFICIAL))
    def test_el_detalle_mensual_suma_el_total_del_escenario(self, cifras, clave):
        total = por_escenario(cifras)[clave]["resultado"]
        mensual = sum(m["resultado"] for m in cifras["mensual"]
                      if m["escenario_clave"] == clave)
        assert abs(mensual - total) < ERROR_SUMA_FLOTANTE

    @pytest.mark.parametrize("clave", sorted(OFICIAL))
    def test_el_coste_por_grupo_suma_el_coste_total(self, cifras, clave):
        """El desglose publicado es exhaustivo: no hay un "otros" sin etiquetar.

        Se agrupa por linea del P&L y no por ambito porque la taxonomia interna
        se generaliza al anonimizar y queda en dos o tres categorias. El grupo
        de gasto son veintisiete y describen la estructura de coste real.
        """
        total = por_escenario(cifras)[clave]["costes"]
        por_grupo = sum(g["costes"] for g in cifras["coste_por_grupo"]
                        if g["escenario_clave"] == clave)
        assert abs(por_grupo - total) < ERROR_SUMA_FLOTANTE

    #: El unico grupo del perimetro de coste que puede salir negativo. No es
    #: un gasto sino el neto de un resultado, y en los dos ejercicios reales
    #: fue una ganancia. En el P&L oficial tiene linea propia por eso mismo.
    GRUPO_DE_SIGNO_LIBRE = "Diferencia de Cambio"

    @pytest.mark.parametrize("clave", sorted(OFICIAL))
    def test_solo_el_tipo_de_cambio_puede_salir_negativo(self, cifras, clave):
        """Un gasto negativo seria un ingreso colado en el perimetro de coste.

        La primera version de esta prueba exigia que **ningun** grupo saliese
        negativo, y fallo: la diferencia de cambio se clasifica fuera de los
        ingresos pero es el neto de un resultado, de modo que puede ser una
        ganancia. Se corrigio la afirmacion, no el dato.
        """
        grupos = [g for g in cifras["coste_por_grupo"] if g["escenario_clave"] == clave]
        assert grupos, "sin grupos, el control no demostraria nada"
        negativos = {g["grupo"] for g in grupos if g["costes"] < 0}
        assert negativos <= {self.GRUPO_DE_SIGNO_LIBRE}

    @pytest.mark.parametrize("clave", sorted(OFICIAL))
    def test_los_periodos_del_detalle_son_los_del_escenario(self, cifras, clave):
        esperados = OFICIAL[clave]["periodos"]
        periodos = {m["periodo"] for m in cifras["mensual"]
                    if m["escenario_clave"] == clave}
        assert len(periodos) == esperados
        assert periodos == set(range(1, esperados + 1))

    @pytest.mark.parametrize("clave", sorted(OFICIAL))
    def test_el_top_de_centros_no_supera_el_coste_total(self, cifras, clave):
        """Un detalle que superase su total delataria un grano duplicado."""
        total = por_escenario(cifras)[clave]["costes"]
        top = sum(c["costes"] for c in cifras["centros"]
                  if c["escenario_clave"] == clave)
        assert 0 < top <= total + ERROR_SUMA_FLOTANTE


class TestLoQueSePublicaEstaAnonimizado:
    """La ultima barrera, sobre el artefacto y no sobre el proceso.

    La auditoria de `scripts/auditar_powerbi.py` recorre este fichero buscando
    valores del origen. Esto es mas estrecho y mas barato: comprueba que la
    forma de lo publicado es la del pseudonimo, de modo que un volcado hecho
    contra otra base -- una sin el `CHECK` de la etapa 2 -- no pasaria.
    """

    PSEUDONIMO = re.compile(r"^CC-\d+$")

    def test_todo_centro_publicado_lleva_pseudonimo(self, cifras):
        codigos = {c["ceco_codigo"] for c in cifras["centros"]}
        assert codigos, "sin centros, el control no demostraria nada"
        malos = {c for c in codigos if not self.PSEUDONIMO.match(c)}
        assert not malos, f"codigos sin pseudonimizar: {sorted(malos)}"

    def test_el_escenario_generado_sigue_marcado(self, cifras):
        """`R2026` es sintetico, y el JSON lo dice aunque el informe no lo rotule."""
        simulados = {e["escenario_clave"] for e in cifras["escenarios"] if e["es_simulado"]}
        assert simulados == {"R2026"}

    def test_declara_de_donde_salen_las_cifras(self, cifras):
        """Sin la procedencia, el JSON seria indistinguible de cifras a mano."""
        assert cifras["origen"]["perimetro_ingresos"] == "Ingresos"
        assert "pl.v_pl_resumen" in cifras["origen"]["vistas"]
        assert cifras["generado_utc"]


class TestElEstadoDeResultadosOficial:
    """Las siete lineas con las que el dashboard compone el P&L de 31 filas.

    Se publican las lineas y no las 31 filas porque los subtotales no son un
    dato: son aritmetica sobre estas siete. Publicarlos calculados obligaria a
    mantener la misma formula en el generador y en la pagina, y a que las dos
    copias no divergieran nunca.

    El mapeo de grupo a linea es el de `Cuenta[Orden Linea Oficial]` del modelo
    semantico, verificado contra el libro de Control de Gestion. Estas pruebas
    comprueban la propiedad que lo sostiene -- que las siete forman una
    particion exhaustiva y disjunta del hecho -- que es lo que hace que el
    estado de resultados cuadre con el resultado del ejercicio.
    """

    LINEAS = (
        "Ingresos",
        "Costos Ventas",
        "Gastos Adm/Ventas",
        "Depreciacion",
        "I/E. Excepcionales",
        "I/E. Financieros",
        "Tipo de Cambio",
    )

    def lineas_de(self, cifras: dict, clave: str) -> dict[str, float]:
        """Las siete lineas del escenario, con cero donde no hay ninguna fila.

        Un escenario puede no traer una linea entera, y es correcto: los dos
        presupuestos no presupuestan diferencia de cambio, de modo que `Tipo de
        Cambio` no existe para ellos. Se resuelve a cero explicito y no se deja
        ausente, porque la pagina tiene que ensenar "0" y no un hueco: un hueco
        no distingue "no aplica" de "no cargo".
        """
        totales = dict.fromkeys(self.LINEAS, 0.0)
        for fila in cifras["pl_oficial"]:
            if fila["escenario_clave"] == clave:
                totales[fila["linea"]] += fila["importe"]
        return totales

    def test_no_aparece_ninguna_linea_fuera_de_las_siete(self, cifras):
        assert {f["linea"] for f in cifras["pl_oficial"]} <= set(self.LINEAS)

    def test_el_presupuesto_no_presupuesta_diferencia_de_cambio(self, cifras):
        """Dato del origen, no fallo: los dos presupuestos no traen esa linea.

        Se fija en una prueba para que deje de ser una sorpresa. Si algun dia
        apareciese, querria decir que el perimetro del presupuesto cambio, y
        conviene enterarse aqui y no al mirar el estado de resultados.
        """
        con_tipo_cambio = {
            f["escenario_clave"] for f in cifras["pl_oficial"] if f["linea"] == "Tipo de Cambio"
        }
        assert con_tipo_cambio == {"R2025", "R2026"}

    @pytest.mark.parametrize("clave", sorted(OFICIAL))
    def test_las_siete_lineas_suman_el_resultado(self, cifras, clave):
        """La particion es exhaustiva: no se pierde ni se duplica un centimo.

        Si una cuenta cayese en dos lineas, o en ninguna, esta suma se separaria
        del resultado del escenario y el estado de resultados dejaria de cuadrar.
        """
        suma = sum(self.lineas_de(cifras, clave).values())
        assert abs(suma - OFICIAL[clave]["resultado"]) < ERROR_SUMA_FLOTANTE

    @pytest.mark.parametrize("clave", sorted(OFICIAL))
    def test_la_linea_de_ingresos_es_el_perimetro_oficial(self, cifras, clave):
        """La primera linea tiene que ser la que reconcilia contra la maqueta."""
        ingresos = self.lineas_de(cifras, clave)["Ingresos"]
        assert abs(ingresos - OFICIAL[clave]["ingresos"]) < ERROR_SUMA_FLOTANTE

    @pytest.mark.parametrize("clave", sorted(OFICIAL))
    def test_el_estado_de_resultados_compuesto_cierra_en_el_resultado(self, cifras, clave):
        """Replica la cascada de subtotales de la medida `Importe PL` del modelo.

        Es el tercer camino independiente a la misma cifra: PostgreSQL la
        agrega, DAX la recompone en VertiPaq y esto la recompone en Python. Un
        error de modelado tendria que repetirse identico en los tres.
        """
        linea = self.lineas_de(cifras, clave)
        bruta = linea["Ingresos"] + linea["Costos Ventas"]
        operativa = (
            bruta + linea["Gastos Adm/Ventas"] + linea["Depreciacion"]
            + linea["I/E. Excepcionales"]
        )
        neta_total = operativa + linea["I/E. Financieros"] + linea["Tipo de Cambio"]
        assert abs(neta_total - OFICIAL[clave]["resultado"]) < ERROR_SUMA_FLOTANTE

    @pytest.mark.parametrize("clave", sorted(OFICIAL))
    def test_cada_periodo_del_escenario_trae_sus_lineas(self, cifras, clave):
        periodos = {f["periodo"] for f in cifras["pl_oficial"] if f["escenario_clave"] == clave}
        assert periodos == set(range(1, OFICIAL[clave]["periodos"] + 1))

    def test_el_ejercicio_se_deriva_de_la_clave_del_escenario(self, cifras):
        """El filtro de ano de la pagina se apoya en esta columna."""
        for fila in cifras["pl_oficial"]:
            assert str(fila["ejercicio"]) == fila["escenario_clave"][1:]


class TestLaReconciliacionPeriodoAPeriodo:
    """Las 36 comparaciones que el agregado anual resume en tres filas.

    El agregado dice que el modelo reconcilia; estas filas lo ensenan. Se
    publican porque son las que dibuja el grafico de la portada: afirmar que
    cuadra y poder verlo mes a mes no es lo mismo, y la diferencia es
    justamente lo que este proyecto defiende.
    """

    def filas(self, cifras: dict) -> list[dict]:
        return cifras["reconciliacion_periodo"]

    def test_estan_los_treinta_y_seis_periodos(self, cifras):
        """Tres escenarios con patron oficial, doce periodos cada uno."""
        filas = self.filas(cifras)
        assert len(filas) == 36
        por_escenario = {f["escenario_clave"] for f in filas}
        assert por_escenario == {"P2025", "R2025", "P2026"}

    def test_cada_periodo_entra_en_su_tolerancia(self, cifras):
        """El control que el grafico ensena. Si falla, no se publica nada."""
        fuera = [
            f for f in self.filas(cifras) if abs(f["diferencia"]) > f["tolerancia"]
        ]
        assert not fuera, f"periodos descuadrados: {fuera}"

    def test_la_tolerancia_nunca_es_cero(self, cifras):
        """Una banda de cero convertiria el grafico en una afirmacion vacia."""
        assert all(f["tolerancia"] > 0 for f in self.filas(cifras))

    def test_el_agregado_anual_coincide_con_la_suma_de_sus_periodos(self, cifras):
        """Los dos bloques salen de consultas distintas y tienen que cuadrar.

        El de la portada agrega por periodo y el de la tabla por escenario. Si
        divergieran, una de las dos vistas estaria mintiendo sobre la misma
        reconciliacion.
        """
        anual = {r["escenario_clave"]: r["diferencia"] for r in cifras["reconciliacion"]}
        for clave, esperado in anual.items():
            suma = sum(
                f["diferencia"] for f in self.filas(cifras) if f["escenario_clave"] == clave
            )
            assert abs(suma - esperado) < ERROR_SUMA_FLOTANTE, clave

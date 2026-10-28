"""Generacion del escenario real simulado del ejercicio en curso.

Para que sirve
--------------
El libro se extrajo con el ejercicio 2026 recien abierto: existe su presupuesto
pero no su real, de modo que la comparacion presupuesto contra ejecucion no se
puede plantear para ese ano. Este modulo genera un real sintetico de enero a
octubre de 2026 que cubre ese hueco.

**Todo lo que genera queda marcado como simulado** en la dimension de escenario
y en el informe de calidad. No se presenta como dato observado en ningun punto
del modelo ni del reporte.

El modelo
---------
Para cada serie `(centro, cuenta)` se descompone el real observado de 2025 en
nivel y estacionalidad, se le aplica una deriva tomada del presupuesto y se le
suma un residuo con memoria:

    simulado[m] = signo · nivel · estacionalidad[m] · deriva(grupo) · (1 + r[m])

* **nivel**: media mensual del valor absoluto de la serie en el real.
* **estacionalidad[m]**: perfil mensual de la serie, normalizado a media 1. Es
  el propio perfil observado, de modo que el simulado hereda la forma del ano
  real en lugar de inventarla.
* **deriva(grupo)**: cociente entre el presupuesto del ejercicio simulado y el
  real del anterior, calculado **por grupo del P&L** y no por serie. Agregar al
  nivel de grupo evita que una serie pequena con un dato atipico en el real
  arrastre una deriva absurda.
* **r[m]**: residuo autorregresivo de orden 1, escalado por la volatilidad que
  esa misma serie mostro en el real. Con `persistencia = 0` seria ruido blanco
  y la serie saldria en dientes de sierra; con memoria, una desviacion persiste
  varios meses, que es como se desvia la ejecucion de un presupuesto.

Lo que el modelo **no** pretende ser es una prevision. No hay validacion fuera
de muestra ni intervalo de confianza: el objetivo es un escenario verosimil
para ejercitar el reporte, no estimar el resultado de 2026.

Por que no ruido aleatorio
--------------------------
Un multiplicador aleatorio por fila produciria series sin estacionalidad, sin
correlacion temporal y con la dispersion equivocada: cualquiera que mirase el
grafico mensual veria que los datos no se comportan como un resultado. Las
tres propiedades que el generador conserva -- perfil mensual, volatilidad por
serie y persistencia de las desviaciones -- son las que hacen que el escenario
aguante una mirada atenta, y las tres se verifican en `validar_simulacion`.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..logging_setup import logger

log = logger("simulate.escenario")

#: Cota del multiplicador del residuo. Impide que una serie muy volatil cambie
#: de signo, que en terminos contables convertiria un coste en un ingreso.
MULTIPLICADOR_MINIMO = 0.45
MULTIPLICADOR_MAXIMO = 1.55

#: Volatilidad relativa maxima que se atribuye a una serie. Las series casi
#: planas con algun mes atipico producen desviaciones tipicas enormes en
#: terminos relativos; sin este tope el residuo dominaria la senal.
VOLATILIDAD_MAXIMA = 0.45


@dataclass(slots=True)
class ResultadoSimulacion:
    hechos: pd.DataFrame
    deriva_por_grupo: pd.Series
    series_generadas: int
    series_omitidas: int


def _perfil_por_serie(real: pd.DataFrame) -> pd.DataFrame:
    """Importe mensual de cada serie y su volatilidad relativa.

    La volatilidad se mide sobre el valor absoluto, no sobre el importe con
    signo: lo que interesa es cuanto oscila la magnitud de la serie, y una
    serie de costes es negativa en todos sus meses. Se acota porque una serie
    casi plana con un unico mes atipico produce una desviacion tipica enorme en
    terminos relativos, y sin tope el residuo dominaria la senal.
    """
    marco = (
        real.groupby(["ceco_codigo", "cuenta_codigo", "periodo"], observed=True)["importe"]
        .sum()
        .reset_index()
    )
    marco["magnitud"] = marco["importe"].abs()

    agregado = marco.groupby(["ceco_codigo", "cuenta_codigo"], observed=True)
    nivel = agregado["magnitud"].transform("mean")
    marco["volatilidad"] = (
        (agregado["magnitud"].transform("std").fillna(0.0) / nivel.replace(0.0, np.nan))
        .fillna(0.0)
        .clip(upper=VOLATILIDAD_MAXIMA)
    )
    return marco


def _deriva_por_grupo(
    real: pd.DataFrame,
    presupuesto: pd.DataFrame,
    dim_cuenta: pd.DataFrame,
    convergencia: float = 1.0,
) -> pd.Series:
    """Cociente presupuesto/real por grupo del P&L, acotado a un rango sensato.

    Una deriva fuera de [0,5 ; 2,0] delata un grupo cuyo presupuesto no es
    comparable con el real -- una linea nueva, o una que dejo de usarse -- y en
    ese caso es mas honesto dejar la serie sin crecimiento que proyectar un
    salto de un orden de magnitud.
    """
    cuenta_grupo = dim_cuenta.set_index("cuenta_codigo")["grupo"]
    real_grupo = (
        real.assign(grupo=real["cuenta_codigo"].map(cuenta_grupo))
        .groupby("grupo", observed=True)["importe"]
        .sum()
    )
    ppto_grupo = (
        presupuesto.assign(grupo=presupuesto["cuenta_codigo"].map(cuenta_grupo))
        .groupby("grupo", observed=True)["importe"]
        .sum()
    )
    deriva = (ppto_grupo / real_grupo).replace([np.inf, -np.inf], np.nan)
    # Un cociente negativo significa que el grupo cambio de signo entre
    # escenarios: tampoco es una deriva utilizable.
    deriva = deriva.where(deriva > 0).fillna(1.0).clip(0.5, 2.0)

    # Convergencia parcial hacia el presupuesto. Adoptar la deriva completa
    # equivaldria a suponer que el ejercicio cumple su presupuesto linea por
    # linea, y el unico dato de ejecucion disponible dice lo contrario: en 2025
    # los ingresos reales se quedaron en el 88,6% de lo presupuestado y el
    # margen presupuestado para 2026 es diez puntos mejor que el real de 2025.
    # Un escenario que heredase esa mejora completa no seria una ejecucion,
    # seria el presupuesto con otro nombre.
    deriva = 1.0 + convergencia * (deriva - 1.0)

    log.info(
        "deriva por grupo (convergencia %.2f): mediana %.3f, rango [%.3f, %.3f] en %d grupos",
        convergencia, float(deriva.median()), float(deriva.min()), float(deriva.max()),
        len(deriva),
    )
    return deriva


def _residuos_ar1(
    n_series: int, n_periodos: int, persistencia: float, generador: np.random.Generator
) -> np.ndarray:
    """Matriz de residuos AR(1) con varianza estacionaria unitaria.

    El factor `sqrt(1 - phi^2)` del choque mantiene la varianza en 1 para
    cualquier persistencia, de modo que subir la memoria de la serie no sube
    tambien su dispersion: las dos propiedades quedan separadas.
    """
    choques = generador.standard_normal((n_series, n_periodos))
    residuos = np.empty_like(choques)
    residuos[:, 0] = choques[:, 0]
    escala = np.sqrt(max(0.0, 1.0 - persistencia**2))
    for m in range(1, n_periodos):
        residuos[:, m] = persistencia * residuos[:, m - 1] + escala * choques[:, m]
    return residuos


def _tendencia_del_presupuesto(presupuesto: pd.DataFrame, ultimo_periodo: int) -> float:
    """Crecimiento mensual implicito en el perfil del presupuesto.

    Se obtiene de la pendiente de una recta ajustada a los importes mensuales
    presupuestados, normalizada por su nivel medio. Da al ejercicio simulado
    una tendencia propia en lugar de una replica plana del ano anterior, y la
    toma del unico documento que dice algo sobre como se espera que evolucione
    ese ano.
    """
    mensual = presupuesto.groupby("periodo", observed=True)["importe"].apply(
        lambda x: x.abs().sum()
    )
    mensual = mensual[mensual.index <= 12]
    if len(mensual) < 3 or mensual.mean() == 0:
        return 0.0
    pendiente = float(np.polyfit(mensual.index.to_numpy(), mensual.to_numpy(), 1)[0])
    crecimiento = pendiente / float(mensual.mean())
    # Un crecimiento mensual por encima del 1,5% implicaria casi un 20% anual:
    # mas alla de eso es mas probable que el presupuesto tenga un mes atipico
    # que una tendencia real.
    return float(np.clip(crecimiento, -0.015, 0.015))


def simular_real(
    real: pd.DataFrame,
    presupuesto: pd.DataFrame,
    dim_cuenta: pd.DataFrame,
    *,
    ejercicio: int,
    ultimo_periodo: int,
    semilla: int,
    persistencia: float,
    intensidad_residuo: float,
    convergencia_presupuesto: float = 1.0,
) -> ResultadoSimulacion:
    """Genera el real simulado al grano `centro x cuenta x periodo`.

    La proyeccion se construye sobre el perfil observado mes a mes:

        simulado[s, m] = real[s, m] · deriva(grupo) · tendencia[m] · (1 + r[s, m])

    Partir del valor observado de cada mes, en lugar de reconstruirlo desde
    nivel y estacionalidad, conserva tres propiedades que importan y que una
    rejilla completa destruye: el volumen total, el perfil mensual exacto y
    **la esporadicidad**. Muchas series solo tienen actividad en dos o tres
    meses del ano -- una reparacion, una provision puntual -- y rellenar los
    diez meses con su nivel medio multiplica su volumen por cuatro. Aqui los
    meses sin actividad en el real siguen sin actividad en el simulado.
    """
    perfil = _perfil_por_serie(real)
    deriva = _deriva_por_grupo(
        real, presupuesto, dim_cuenta, convergencia=convergencia_presupuesto
    )
    crecimiento = _tendencia_del_presupuesto(presupuesto, ultimo_periodo)
    cuenta_grupo = dim_cuenta.set_index("cuenta_codigo")["grupo"]

    datos = perfil[perfil["periodo"] <= ultimo_periodo].copy()
    series = (
        datos[["ceco_codigo", "cuenta_codigo"]]
        .drop_duplicates()
        .sort_values(["ceco_codigo", "cuenta_codigo"])
        .reset_index(drop=True)
    )
    omitidas = (
        perfil[["ceco_codigo", "cuenta_codigo"]].drop_duplicates().shape[0] - len(series)
    )

    generador = np.random.default_rng(semilla)
    residuos = _residuos_ar1(len(series), ultimo_periodo, persistencia, generador)
    indice_serie = {
        (c, q): i
        for i, (c, q) in enumerate(
            zip(series["ceco_codigo"], series["cuenta_codigo"], strict=True)
        )
    }
    posiciones = np.array(
        [
            indice_serie[(c, q)]
            for c, q in zip(datos["ceco_codigo"], datos["cuenta_codigo"], strict=True)
        ]
    )
    datos["residuo"] = residuos[posiciones, datos["periodo"].to_numpy() - 1]

    datos["grupo"] = datos["cuenta_codigo"].map(cuenta_grupo)
    datos["deriva"] = datos["grupo"].map(deriva).fillna(1.0)

    # La tendencia se centra en el periodo medio para que no desplace el nivel
    # agregado del ejercicio, solo su inclinacion.
    centro = (ultimo_periodo + 1) / 2
    datos["tendencia"] = 1.0 + crecimiento * (datos["periodo"] - centro)

    multiplicador = (
        1.0 + intensidad_residuo * datos["volatilidad"] * datos["residuo"]
    ).clip(MULTIPLICADOR_MINIMO, MULTIPLICADOR_MAXIMO)

    datos["importe"] = (
        datos["importe"] * datos["deriva"] * datos["tendencia"] * multiplicador
    ).round(2)

    hechos = datos.loc[
        datos["importe"] != 0, ["ceco_codigo", "cuenta_codigo", "periodo", "importe"]
    ].copy()
    hechos["ejercicio"] = ejercicio
    hechos = hechos.reset_index(drop=True)

    log.info(
        "real simulado %d: %s lineas, %s series, periodos 1-%d, tendencia %.3f%%/mes, total %s",
        ejercicio, f"{len(hechos):,}", f"{len(series):,}", ultimo_periodo,
        100 * crecimiento, f"{float(hechos['importe'].sum()):,.2f}",
    )
    return ResultadoSimulacion(
        hechos=hechos,
        deriva_por_grupo=deriva,
        series_generadas=len(series),
        series_omitidas=omitidas,
    )

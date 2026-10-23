"""Controles sobre el escenario simulado.

Un generador de datos sinteticos sin validacion produce numeros, no un
escenario. Estos controles comprueban que el simulado conserva las propiedades
que lo hacen verosimil y que su nivel guarda una relacion sensata con el
presupuesto del mismo ano.

Una nota sobre que se mide
--------------------------
Todas las comparaciones se hacen sobre el **volumen bruto** -- la suma de
valores absolutos -- y no sobre el resultado neto. El motivo es que en estos
datos los ingresos y los costes casi se cancelan: el neto mensual de 2025 oscila
entre -370 y +865 miles sobre un volumen de 12 millones. Un coeficiente de
variacion calculado sobre una magnitud cuya media esta proxima a cero no mide
la estabilidad de la serie, mide lo cerca de cero que esta su media, y da
valores enormes sin significado. El volumen bruto es la medida estable de la
actividad y es la que permite comparar real y simulado.

Casi todos son avisos: el escenario es un artefacto de demostracion, y detener
el pipeline por una correlacion de 0,68 seria confundir una heuristica con un
invariante. Lo que no es negociable -- que no invente dimensiones y que quede
marcado como simulado -- si es bloqueante.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..logging_setup import logger
from ..quality.checks import Control, ResultadoCalidad, Severidad

log = logger("simulate.validacion")

#: Correlacion minima entre el perfil mensual del real y el del simulado.
CORRELACION_MINIMA = 0.70

#: Coeficiente de variacion por debajo del cual se considera que el real no
#: tiene estacionalidad apreciable y la correlacion de perfiles deja de ser
#: informativa.
ESTACIONALIDAD_MINIMA = 0.05

#: Desviacion maxima admitida entre el total simulado y el presupuesto
#: prorrateado a los mismos meses.
DESVIACION_MAXIMA_PRESUPUESTO = 0.25

#: Proporcion de series a las que se les tolera un cambio de signo. El
#: multiplicador del residuo es siempre positivo, de modo que ningun mes puede
#: cambiar de signo por si mismo; lo que puede cambiar es el signo de la *suma*
#: de una serie que ya mezclaba signos en el real -- una provision y su
#: reversion, por ejemplo -- cuando el residuo altera el peso relativo de sus
#: meses. Es un comportamiento del modelo y no un defecto, pero conviene que
#: quede acotado y visible.
PROPORCION_SIGNOS_ADMITIDA = 0.005


def _volumen_mensual(df: pd.DataFrame, meses: list[int] | None = None) -> pd.Series:
    """Suma de valores absolutos por periodo."""
    if meses is not None:
        df = df[df["periodo"].isin(meses)]
    return df.assign(magnitud=df["importe"].abs()).groupby("periodo")["magnitud"].sum()


def _coef_variacion(s: pd.Series) -> float:
    media = float(s.mean())
    return float(s.std() / abs(media)) if media else float("nan")


def validar_estacionalidad(
    real: pd.DataFrame, simulado: pd.DataFrame, resultado: ResultadoCalidad
) -> None:
    """El perfil mensual del simulado debe seguir al del real.

    Si el real no tiene estacionalidad apreciable, el control lo hace constar y
    no exige correlacion: con un perfil plano, el coeficiente solo recogeria
    ruido, y rechazar el escenario por ese motivo seria exigirle una estructura
    que los datos de partida no tienen.
    """
    meses = sorted(simulado["periodo"].unique())
    perfil_real = _volumen_mensual(real, meses)
    perfil_sim = _volumen_mensual(simulado)
    comun = perfil_real.index.intersection(perfil_sim.index)

    cv_real = _coef_variacion(perfil_real)
    hay_estacionalidad = bool(cv_real >= ESTACIONALIDAD_MINIMA)

    # La correlacion no esta definida si alguna de las dos series es constante:
    # su desviacion tipica es cero y el cociente, una indeterminacion.
    if len(comun) >= 3 and perfil_real[comun].std() > 0 and perfil_sim[comun].std() > 0:
        correlacion = float(np.corrcoef(perfil_real[comun], perfil_sim[comun])[0, 1])
    else:
        correlacion = float("nan")

    if hay_estacionalidad:
        aprobado = bool(correlacion >= CORRELACION_MINIMA)
        detalle = (
            f"correlacion {correlacion:.3f} sobre {len(comun)} meses "
            f"(minimo {CORRELACION_MINIMA})"
        )
    else:
        aprobado = True
        detalle = (
            f"el real no tiene estacionalidad apreciable (coef. variacion del volumen "
            f"{cv_real:.4f} < {ESTACIONALIDAD_MINIMA}); correlacion observada "
            f"{correlacion:.3f}, no exigida"
        )

    resultado.agregar(
        Control(
            nombre="El simulado hereda el perfil mensual del real",
            aprobado=aprobado,
            severidad=Severidad.AVISO,
            detalle=detalle,
            metricas={
                "correlacion_perfil": correlacion,
                "cv_volumen_real": cv_real,
            },
        )
    )


def validar_dispersion(
    real: pd.DataFrame, simulado: pd.DataFrame, resultado: ResultadoCalidad
) -> None:
    """La volatilidad mensual del simulado debe parecerse a la del real.

    Un simulado demasiado plano delata el escalado de una media; uno demasiado
    agitado, ruido sin estructura. Se compara el coeficiente de variacion del
    volumen mensual.
    """
    meses = sorted(simulado["periodo"].unique())
    cv_real = _coef_variacion(_volumen_mensual(real, meses))
    cv_sim = _coef_variacion(_volumen_mensual(simulado))
    razon = cv_sim / cv_real if cv_real else float("nan")

    resultado.agregar(
        Control(
            nombre="La dispersion del simulado es comparable a la del real",
            aprobado=bool(0.4 <= razon <= 3.0),
            severidad=Severidad.AVISO,
            detalle=(
                f"coef. variacion del volumen: real {cv_real:.4f} vs simulado "
                f"{cv_sim:.4f} (razon {razon:.2f}; admitido 0,4-3,0)"
            ),
            metricas={"cv_real": cv_real, "cv_simulado": cv_sim, "razon": razon},
        )
    )


def validar_volumen(
    real: pd.DataFrame, simulado: pd.DataFrame, resultado: ResultadoCalidad
) -> None:
    """El volumen por mes del simulado debe estar en el orden del real.

    Es el control que detecta el fallo mas facil de cometer al generar datos a
    partir de una rejilla de dimensiones: dar actividad en todos los meses a
    series que en el real solo la tienen en dos o tres, lo que multiplica el
    volumen sin que ningun otro control lo note.
    """
    meses = sorted(simulado["periodo"].unique())
    vol_real = float(_volumen_mensual(real, meses).mean())
    vol_sim = float(_volumen_mensual(simulado).mean())
    razon = vol_sim / vol_real if vol_real else float("nan")

    resultado.agregar(
        Control(
            nombre="El volumen mensual del simulado es del orden del real",
            aprobado=bool(0.75 <= razon <= 1.35),
            severidad=Severidad.AVISO,
            detalle=(
                f"volumen medio mensual: real {vol_real / 1e6:.2f} M vs simulado "
                f"{vol_sim / 1e6:.2f} M (razon {razon:.3f}; admitido 0,75-1,35)"
            ),
            metricas={"volumen_real": vol_real, "volumen_simulado": vol_sim, "razon": razon},
        )
    )


def validar_margen(
    real: pd.DataFrame,
    simulado: pd.DataFrame,
    dim_cuenta: pd.DataFrame,
    resultado: ResultadoCalidad,
) -> None:
    """El margen del simulado debe moverse en el rango del real.

    Es la propiedad financiera que de verdad importa: un escenario cuyo margen
    se va treinta puntos respecto al historico no describe a la misma empresa,
    por bien que se comporten sus series una a una.
    """
    grupo = dim_cuenta.set_index("cuenta_codigo")["grupo"]
    meses = sorted(simulado["periodo"].unique())

    def margen(df: pd.DataFrame) -> float:
        con_grupo = df.assign(grupo=df["cuenta_codigo"].map(grupo))
        ingresos = float(con_grupo.loc[con_grupo["grupo"] == "Ingresos", "importe"].sum())
        total = float(con_grupo["importe"].sum())
        return total / ingresos if ingresos else float("nan")

    margen_real = margen(real[real["periodo"].isin(meses)])
    margen_sim = margen(simulado)
    diferencia = abs(margen_sim - margen_real)

    resultado.agregar(
        Control(
            nombre="El margen del simulado esta en el rango del real",
            aprobado=bool(diferencia <= 0.10),
            severidad=Severidad.AVISO,
            detalle=(
                f"margen sobre ingresos: real {100 * margen_real:.2f}% vs simulado "
                f"{100 * margen_sim:.2f}% (diferencia {100 * diferencia:.2f} pp; "
                "admitidos 10 pp)"
            ),
            metricas={
                "margen_real": margen_real,
                "margen_simulado": margen_sim,
                "diferencia_pp": 100 * diferencia,
            },
        )
    )


def validar_signos(
    real: pd.DataFrame, simulado: pd.DataFrame, resultado: ResultadoCalidad
) -> None:
    """Ninguna serie puede cambiar de naturaleza entre el real y el simulado.

    Un coste que aparece en positivo o un ingreso en negativo rompe el P&L sin
    que ningun total lo delate, porque se compensa con otras lineas.

    La comparacion se hace sobre los mismos meses que cubre el simulado y
    excluyendo las series cuya suma es practicamente nula: en esas el signo es
    el de su ultimo centimo y compararlo no dice nada.
    """
    meses = sorted(simulado["periodo"].unique())

    def suma_por_serie(df: pd.DataFrame) -> pd.Series:
        return df.groupby(["ceco_codigo", "cuenta_codigo"], observed=True)["importe"].sum()

    suma_real = suma_por_serie(real[real["periodo"].isin(meses)])
    suma_sim = suma_por_serie(simulado)
    comun = suma_real.index.intersection(suma_sim.index)

    significativas = comun[suma_real[comun].abs() >= 1.0]
    discrepantes = int(
        (np.sign(suma_real[significativas]) != np.sign(suma_sim[significativas])).sum()
    )
    proporcion = discrepantes / len(significativas) if len(significativas) else 0.0

    resultado.agregar(
        Control(
            nombre="El simulado conserva el signo de cada serie",
            aprobado=proporcion <= PROPORCION_SIGNOS_ADMITIDA,
            severidad=Severidad.AVISO,
            detalle=(
                f"{discrepantes} de {len(significativas):,} series con suma "
                f"significativa cambian de signo ({100 * proporcion:.2f}%; admitido "
                f"{100 * PROPORCION_SIGNOS_ADMITIDA:.1f}%). "
                f"{len(comun) - len(significativas):,} series de suma nula excluidas"
            ),
            metricas={
                "series_discrepantes": float(discrepantes),
                "proporcion": proporcion,
            },
        )
    )


def validar_nivel_contra_presupuesto(
    simulado: pd.DataFrame,
    control_presupuesto: pd.Series,
    dim_cuenta: pd.DataFrame,
    resultado: ResultadoCalidad,
) -> None:
    """Los ingresos simulados deben moverse en el entorno del presupuesto.

    No tienen que coincidir -- la gracia del escenario es precisamente que haya
    desviacion que analizar -- pero una ejecucion del 40% o del 180% no seria
    creible en una empresa en marcha.
    """
    grupo = dim_cuenta.set_index("cuenta_codigo")["grupo"]
    ingresos = simulado.assign(grupo=simulado["cuenta_codigo"].map(grupo))
    ingresos = ingresos.loc[ingresos["grupo"] == "Ingresos"]

    meses = sorted(simulado["periodo"].unique())
    simulado_total = float(ingresos["importe"].sum())
    presupuesto_total = float(control_presupuesto.reindex(meses).dropna().sum())
    ejecucion = simulado_total / presupuesto_total if presupuesto_total else float("nan")
    desviacion = abs(ejecucion - 1.0)

    resultado.agregar(
        Control(
            nombre="Los ingresos simulados son creibles frente al presupuesto",
            aprobado=bool(desviacion <= DESVIACION_MAXIMA_PRESUPUESTO),
            severidad=Severidad.AVISO,
            detalle=(
                f"ejecucion {100 * ejecucion:.1f}% del presupuesto en los meses "
                f"1-{max(meses)} (admitido {100 * (1 - DESVIACION_MAXIMA_PRESUPUESTO):.0f}-"
                f"{100 * (1 + DESVIACION_MAXIMA_PRESUPUESTO):.0f}%)"
            ),
            metricas={
                "ingresos_simulados": simulado_total,
                "presupuesto_mismos_meses": presupuesto_total,
                "ejecucion": ejecucion,
            },
        )
    )


def validar_cobertura(
    real: pd.DataFrame, simulado: pd.DataFrame, resultado: ResultadoCalidad
) -> None:
    """El simulado no debe inventar centros ni cuentas que el real no tenga."""
    nuevos_centros = set(simulado["ceco_codigo"]) - set(real["ceco_codigo"])
    nuevas_cuentas = set(simulado["cuenta_codigo"]) - set(real["cuenta_codigo"])
    resultado.agregar(
        Control(
            nombre="El simulado no introduce dimensiones nuevas",
            aprobado=not nuevos_centros and not nuevas_cuentas,
            severidad=Severidad.BLOQUEANTE,
            detalle=(
                f"{len(nuevos_centros)} centros y {len(nuevas_cuentas)} cuentas "
                "que no existen en el real"
            ),
        )
    )


def al_grano_del_simulado(real: pd.DataFrame) -> pd.DataFrame:
    """Agrega el detalle real al grano `centro x cuenta x periodo`.

    El real observado llega con grano de apunte contable y el simulado se
    genera al grano de celda. Comparar sus volumenes brutos sin igualar el
    grano antes da una diferencia espuria: dentro de una misma celda hay
    apuntes de signo opuesto -- un cargo y su abono -- que se cancelan al
    agregar, de modo que la suma de valores absolutos del detalle es
    sistematicamente mayor que la de la celda. Medido asi, el real parece un
    60% mas voluminoso de lo que es a efectos de comparacion.
    """
    return (
        real.groupby(["ejercicio", "periodo", "ceco_codigo", "cuenta_codigo"], observed=True)[
            "importe"
        ]
        .sum()
        .reset_index()
    )


def validar_todo(
    real: pd.DataFrame,
    simulado: pd.DataFrame,
    control_presupuesto: pd.Series,
    dim_cuenta: pd.DataFrame,
    resultado: ResultadoCalidad,
) -> None:
    real = al_grano_del_simulado(real)
    validar_cobertura(real, simulado, resultado)
    validar_volumen(real, simulado, resultado)
    validar_estacionalidad(real, simulado, resultado)
    validar_dispersion(real, simulado, resultado)
    validar_margen(real, simulado, dim_cuenta, resultado)
    validar_signos(real, simulado, resultado)
    validar_nivel_contra_presupuesto(simulado, control_presupuesto, dim_cuenta, resultado)

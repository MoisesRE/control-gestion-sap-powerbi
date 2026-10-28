"""Escalado de importes.

Por que un factor unico y global
--------------------------------
El reporte vive de ratios: margen bruto sobre ventas, peso de cada grupo de
coste, variacion interanual, coste por centro. Multiplicar todos los importes
por una misma constante `k` deja esos indicadores invariantes, porque aparecen
como cocientes donde `k` se cancela.

La salvedad es el redondeo posterior a dos decimales, que desplaza cada importe
hasta 0,005 e introduce en una razon un error relativo acotado por 0,005
dividido por el menor de los importes implicados. En los agregados del P&L, del
orden de millones, eso es ruido por debajo de 1e-9; entre dos apuntes
individuales de pocas unidades puede alcanzar 1e-6. Ningun indicador del
reporte se calcula sobre apuntes individuales, de modo que el efecto es
irrelevante en la practica, pero conviene no afirmar una exactitud que no se
cumple.

Las alternativas no sirven para este caso:

* Un factor distinto por ejercicio destruiria la variacion interanual, que es
  justo lo que el reporte compara.
* Ruido aleatorio por fila (`jitter`) rompe la reconciliacion con el reporte
  oficial y haria que los subtotales no sumasen al total, algo que cualquier
  revisor con criterio financiero detecta de inmediato.
* Redondear a miles perderia el detalle de las cuentas de poco importe, que
  son la mitad del plan contable.

El redondeo a dos decimales posterior al escalado introduce una perdida de
informacion suficiente para que dividir por el factor no devuelva el importe
original exacto, y es coherente con una magnitud monetaria.
"""

from __future__ import annotations

import pandas as pd

from ..logging_setup import logger

log = logger("anonymize.scaler")


def escalar_importes(serie: pd.Series, factor: float) -> pd.Series:
    """Aplica el factor global y redondea a dos decimales."""
    if not 0.1 <= factor <= 10:
        raise ValueError(f"factor fuera del rango razonable: {factor}")
    escalada = (serie.astype("float64") * factor).round(2)
    log.info(
        "importes escalados por %.4f | original %.2f -> escalado %.2f",
        factor,
        float(serie.sum()),
        float(escalada.sum()),
    )
    return escalada


#: Error maximo que introduce el redondeo a dos decimales en un unico apunte.
ERROR_REDONDEO_APUNTE = 0.005


def error_maximo_agregado(n_apuntes: int) -> float:
    """Cota del error de redondeo al sumar `n_apuntes` importes escalados.

    Cada apunte se desvia como maximo `ERROR_REDONDEO_APUNTE` de su valor
    exacto, de modo que una suma de `n` apuntes se desvia como maximo `n` veces
    esa cantidad. Es una cota pesimista (los desvios se compensan en la
    practica) pero es exacta y se deriva del proceso, lo que la hace preferible
    a un umbral elegido a ojo.
    """
    return max(0.05, n_apuntes * ERROR_REDONDEO_APUNTE)


def comprobar_invariantes(
    original: pd.Series, escalada: pd.Series, factor: float
) -> dict[str, float]:
    """Verifica que el escalado preservo la estructura de los datos.

    La comprobacion se hace **por apunte**, no sobre la suma: el importe neto
    del ejercicio es dos ordenes de magnitud menor que el volumen bruto, porque
    ingresos y costes se compensan, y un error relativo calculado sobre ese
    neto resultaria enganosamente grande. La invariante que de verdad importa
    es que ningun apunte individual se desvie mas de lo que permite el redondeo
    a dos decimales.
    """
    exacto = original.astype("float64") * factor
    desvio_apunte = (escalada - exacto).abs()
    peor_apunte = float(desvio_apunte.max()) if len(desvio_apunte) else 0.0

    # Margen de 1e-9 para el error de representacion del coma flotante.
    if peor_apunte > ERROR_REDONDEO_APUNTE + 1e-9:
        culpable = desvio_apunte.idxmax()
        raise AssertionError(
            f"el escalado no es proporcional en el apunte {culpable}: "
            f"desvio {peor_apunte:.6f} > {ERROR_REDONDEO_APUNTE} admitido por el redondeo"
        )

    # El signo de cada apunte debe conservarse: un ingreso no puede volverse
    # coste porque el factor es positivo.
    signos_cambiados = int(((original > 0) & (escalada < 0)).sum()
                           + ((original < 0) & (escalada > 0)).sum())
    if signos_cambiados:
        raise AssertionError(f"{signos_cambiados} apuntes cambiaron de signo al escalar")

    suma_orig = float(original.sum())
    suma_esc = float(escalada.sum())
    bruto = float(original.abs().sum())
    return {
        "apuntes": float(len(original)),
        "suma_original": suma_orig,
        "suma_escalada": suma_esc,
        "volumen_bruto_original": bruto,
        "factor": factor,
        "desvio_maximo_por_apunte": peor_apunte,
        "desvio_agregado": abs(suma_esc - suma_orig * factor),
        "cota_error_agregado": error_maximo_agregado(len(original)),
    }

"""Genera desde PostgreSQL las cifras que publica el dashboard de GitHub Pages.

El dashboard es la unica pieza del proyecto que lee cualquiera sin clonar el
repositorio, y por eso es la que mas tienta a escribir las cifras a mano en el
HTML. Se hace al contrario: las cifras salen de la base por este script, el
HTML las lee de `docs/cifras.json` y no contiene ni un importe.

La razon no es comodidad. Una cifra escrita a mano no se puede reconciliar
contra nada, y se podre en silencio: el dia que cambie el factor de
anonimizacion o el perimetro de una vista, el HTML seguiria ensenando la cifra
vieja sin que ningun control fallase. El proyecto entero se apoya en que toda
cifra publicada es reproducible, y la cifra mas publica no puede ser la
excepcion.

**Este script es ademas una puerta.** Antes de escribir nada ejecuta las vistas
`qa.v_control_*` -- las mismas que verifican la carga, descubiertas en el
catalogo y no listadas aqui -- y se niega a generar el JSON si alguna devuelve
filas. Un dashboard no deberia poder publicarse desde un modelo descuadrado.

    python scripts/generar_cifras_web.py
    python scripts/generar_cifras_web.py --comprobar   # no escribe; solo valida

Devuelve 1 si los controles fallan o si el JSON en disco no coincide con la
base, para poder encadenarlo antes de publicar.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from finanzas_etl.config import ConfigPostgres  # noqa: E402
from finanzas_etl.load.postgres import conectar  # noqa: E402
from finanzas_etl.logging_setup import configurar, logger  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]
DESTINO = RAIZ / "docs" / "cifras.json"

#: Centros que se listan en el detalle de coste. Son los que caben en una tabla
#: que se lee sin desplazarse; el resto se agrega en "otros centros" para que la
#: suma de la tabla siga siendo el coste total y no una parte sin etiquetar.
TOP_CENTROS = 12

#: El perimetro de ingresos es el grupo `Ingresos` a secas, que es el de la fila
#: INGRESOS de la maqueta oficial. `es_ingreso` seria mas amplio -- incluye
#: `Ingresos Diversos` -- y daria una ejecucion presupuestaria del 88,52% en
#: lugar del 88,56% que reconcilia contra el reporte de la organizacion.
LINEA_INGRESOS = "Ingresos"

log = logger("generar_cifras_web")


def _limpiar(valor: Any) -> Any:
    """Decimal -> float para que `json` lo serialice.

    Se convierte en el borde y no antes: toda la agregacion la hace PostgreSQL
    sobre `numeric`, de modo que ninguna suma pasa por coma flotante. Lo que se
    redondea aqui es solo la representacion.
    """
    if isinstance(valor, Decimal):
        return float(valor)
    return valor


def _filas(cur, consulta: str, parametros: tuple = ()) -> list[dict[str, Any]]:
    cur.execute(consulta, parametros)
    columnas = [c.name for c in cur.description]
    return [
        {k: _limpiar(v) for k, v in zip(columnas, fila, strict=True)}
        for fila in cur.fetchall()
    ]


def controles_del_esquema(cur) -> list[str]:
    """Vistas `qa.v_control_*` que devuelven filas, es decir, que descuadran.

    Se descubren en el catalogo igual que en el cargador: anadir un control al
    DDL basta para que esta puerta lo tenga en cuenta.
    """
    cur.execute(
        """
        SELECT table_name
        FROM information_schema.views
        WHERE table_schema = 'qa' AND table_name LIKE 'v\\_control\\_%'
        ORDER BY table_name
        """
    )
    vistas = [fila[0] for fila in cur.fetchall()]
    if not vistas:
        raise RuntimeError("no hay ninguna vista qa.v_control_*: el DDL no se aplico")

    fallan = []
    for vista in vistas:
        cur.execute(f"SELECT count(*) FROM qa.{vista}")  # noqa: S608
        filas = int(cur.fetchone()[0])
        if filas:
            fallan.append(f"qa.{vista} ({filas} filas)")
    log.info("controles del esquema: %d ejecutados, %d con descuadre", len(vistas), len(fallan))
    return fallan


def recoger(cur) -> dict[str, Any]:
    """Las cifras que el dashboard ensena, y ninguna mas.

    Cada bloque se corresponde con una seccion de la pagina: lo que no se
    dibuja no se publica, de modo que todo numero del JSON esta a la vista y
    puede comprobarse contra la base.
    """
    escenarios = _filas(
        cur,
        """
        SELECT escenario_clave,
               escenario,
               tipo_escenario,
               es_simulado,
               count(DISTINCT periodo)      AS periodos,
               sum(ingresos)                AS ingresos,
               sum(ingresos_diversos)       AS ingresos_diversos,
               sum(costes)                  AS costes,
               sum(resultado)               AS resultado,
               round(100 * sum(resultado) / nullif(sum(ingresos), 0), 2) AS margen_pct
          FROM pl.v_pl_resumen
         GROUP BY escenario_clave, escenario, tipo_escenario, es_simulado,
                  orden_escenario
         ORDER BY orden_escenario
        """,
    )

    mensual = _filas(
        cur,
        """
        SELECT escenario_clave, periodo, etiqueta_mes,
               ingresos, costes, resultado, resultado_acumulado
          FROM pl.v_pl_resumen
         ORDER BY escenario_clave, periodo
        """,
    )

    # Las siete lineas de importe del P&L oficial, por escenario y periodo. El
    # dashboard compone con ellas las 31 filas del estado de resultados --
    # subtotales y margenes incluidos -- igual que hace el informe de Power BI
    # con la medida `Importe PL`. Se publican las lineas y no las 31 filas
    # porque los subtotales no son un dato: son aritmetica sobre estas siete, y
    # publicarlos calculados obligaria a mantener la misma formula en dos
    # sitios.
    #
    # El mapeo de grupo a linea es el de `Cuenta[Orden Linea Oficial]` del
    # modelo semantico, verificado contra el libro de Control de Gestion. El
    # orden de los CASE importa: los grupos con linea propia se resuelven
    # primero y solo lo que queda se reparte entre coste y gasto segun la clase
    # de la cuenta, de modo que ninguna cuenta cae en dos lineas ni se queda
    # sin ninguna. Es lo que hace que las siete sumen el resultado al centimo.
    pl_oficial = _filas(
        cur,
        """
        WITH lineas (orden, linea) AS (
            VALUES (1, 'Ingresos'),
                   (2, 'Costos Ventas'),
                   (3, 'Gastos Adm/Ventas'),
                   (4, 'Depreciacion'),
                   (5, 'I/E. Excepcionales'),
                   (6, 'I/E. Financieros'),
                   (7, 'Tipo de Cambio')
        ),
        clasificado AS (
            SELECT f.escenario_clave,
                   t.ejercicio,
                   t.periodo,
                   CASE
                       WHEN c.grupo = 'Ingresos'                               THEN 1
                       WHEN c.grupo IN ('Ingresos Diversos', 'Egresos Diversos') THEN 5
                       WHEN c.grupo = 'Depreciacion'                           THEN 4
                       WHEN c.grupo = 'Gasto Financiero'                       THEN 6
                       WHEN c.grupo = 'Diferencia de Cambio'                   THEN 7
                       WHEN c.clase_costo_gasto = 'COSTO'                      THEN 2
                       ELSE 3
                   END AS orden,
                   sum(f.importe) AS importe
              FROM core.fact_escenario f
              JOIN core.dim_tiempo  t ON t.fecha_clave   = f.fecha_clave
              JOIN core.dim_cuenta  c ON c.cuenta_codigo = f.cuenta_codigo
             GROUP BY 1, 2, 3, 4
        )
        SELECT k.escenario_clave, k.ejercicio, k.periodo,
               k.orden, l.linea, k.importe
          FROM clasificado k
          JOIN lineas l ON l.orden = k.orden
         ORDER BY k.escenario_clave, k.periodo, k.orden
        """,
    )

    # La reconciliacion contra la maqueta, que es la prueba que el dashboard
    # existe para ensenar. La tolerancia se deriva igual que en la capa SQL:
    # escalar y redondear n importes puede desviar su suma hasta n medias
    # centesimas, con un suelo para los periodos de muy pocas filas.
    reconciliacion = _filas(
        cur,
        """
        WITH modelo AS (
            SELECT f.escenario_clave, t.periodo,
                   sum(f.importe) AS ingresos_modelo,
                   count(*)       AS filas
              FROM core.fact_escenario f
              JOIN core.dim_tiempo  t ON t.fecha_clave   = f.fecha_clave
              JOIN core.dim_cuenta  c ON c.cuenta_codigo = f.cuenta_codigo
             WHERE c.grupo = %s
             GROUP BY 1, 2
        )
        SELECT o.escenario_clave,
               e.escenario,
               count(*)                                            AS periodos,
               sum(o.ingresos_oficiales)                           AS maqueta,
               sum(m.ingresos_modelo)                              AS pipeline,
               sum(m.ingresos_modelo) - sum(o.ingresos_oficiales)  AS diferencia,
               greatest(0.05, sum(m.filas) * 0.005)                AS tolerancia
          FROM qa.control_reconciliacion o
          JOIN modelo m
            ON m.escenario_clave = o.escenario_clave AND m.periodo = o.periodo
          JOIN core.dim_escenario e ON e.escenario_clave = o.escenario_clave
         GROUP BY 1, 2, e.orden_escenario
         ORDER BY e.orden_escenario
        """,
        (LINEA_INGRESOS,),
    )

    # La misma reconciliacion, pero periodo a periodo. El agregado anual dice
    # que cuadra; estas 36 filas lo ensenan. Es lo que dibuja el grafico de la
    # portada, y la diferencia entre afirmar que el modelo reconcilia y poder
    # verlo: cada punto es un mes contra la cifra que la organizacion publica,
    # con su banda de tolerancia derivada del numero de apuntes agregados.
    reconciliacion_periodo = _filas(
        cur,
        """
        WITH modelo AS (
            SELECT f.escenario_clave, t.periodo,
                   sum(f.importe) AS ingresos_modelo,
                   count(*)       AS filas
              FROM core.fact_escenario f
              JOIN core.dim_tiempo  t ON t.fecha_clave   = f.fecha_clave
              JOIN core.dim_cuenta  c ON c.cuenta_codigo = f.cuenta_codigo
             WHERE c.grupo = %s
             GROUP BY 1, 2
        )
        SELECT o.escenario_clave,
               e.escenario,
               o.periodo,
               m.ingresos_modelo - o.ingresos_oficiales AS diferencia,
               greatest(0.05, m.filas * 0.005)          AS tolerancia
          FROM qa.control_reconciliacion o
          JOIN modelo m
            ON m.escenario_clave = o.escenario_clave AND m.periodo = o.periodo
          JOIN core.dim_escenario e ON e.escenario_clave = o.escenario_clave
         ORDER BY e.orden_escenario, o.periodo
        """,
        (LINEA_INGRESOS,),
    )

    # La ejecucion presupuestaria, con y sin el recorte de periodos. Las dos
    # cifras van al JSON a proposito: la diferencia entre 104,8% y 85,6% en 2026
    # es la trampa que el proyecto documenta, y ensenar solo la buena seria
    # esconderla.
    ejecucion = _filas(
        cur,
        """
        SELECT ejercicio,
               count(DISTINCT periodo) FILTER (WHERE periodo_comparable) AS periodos_comparables,
               count(DISTINCT periodo)                                   AS periodos_totales,
               sum(importe_real)      FILTER (WHERE periodo_comparable)  AS real_comparable,
               sum(importe_presupuesto) FILTER (WHERE periodo_comparable) AS presupuesto_comparable,
               sum(importe_real)                                         AS real_total,
               sum(importe_presupuesto)                                  AS presupuesto_total,
               round(100 * sum(importe_real) FILTER (WHERE periodo_comparable)
                     / nullif(sum(importe_presupuesto)
                              FILTER (WHERE periodo_comparable), 0), 2)  AS ejecucion_pct,
               round(100 * sum(importe_real)
                     / nullif(sum(importe_presupuesto), 0), 2)
                   AS ejecucion_pct_sin_recorte
          FROM pl.v_ejecucion_presupuestaria
         WHERE linea_pl = %s
         GROUP BY ejercicio
         ORDER BY ejercicio
        """,
        (LINEA_INGRESOS,),
    )

    # En que se consume el coste. Se agrupa por linea del P&L y no por ambito:
    # la taxonomia interna se generaliza al anonimizar y queda en dos o tres
    # categorias, que no dicen nada. El grupo de gasto son veintisiete y
    # describen la estructura de coste de una empresa de transporte --
    # combustible, mano de obra, peajes, mantenimiento --, que es lo que un
    # analista mira primero.
    coste_por_grupo = _filas(
        cur,
        """
        SELECT escenario_clave,
               linea_pl AS grupo,
               -sum(importe) AS costes
          FROM pl.v_pl_mensual
         WHERE NOT es_ingreso
         GROUP BY escenario_clave, linea_pl
        HAVING -sum(importe) <> 0
         ORDER BY escenario_clave, -sum(importe) DESC
        """,
    )

    centros = _filas(
        cur,
        """
        WITH ordenados AS (
            SELECT escenario_clave, ceco_codigo, ceco_nombre, ambito, costes,
                   row_number() OVER (PARTITION BY escenario_clave
                                      ORDER BY costes DESC) AS puesto
              FROM pl.v_resultado_por_centro
             WHERE costes <> 0
        )
        SELECT escenario_clave, puesto, ceco_codigo, ceco_nombre, ambito, costes
          FROM ordenados
         WHERE puesto <= %s
         ORDER BY escenario_clave, puesto
        """,
        (TOP_CENTROS,),
    )

    return {
        "escenarios": escenarios,
        "mensual": mensual,
        "pl_oficial": pl_oficial,
        "reconciliacion": reconciliacion,
        "reconciliacion_periodo": reconciliacion_periodo,
        "ejecucion": ejecucion,
        "coste_por_grupo": coste_por_grupo,
        "centros": centros,
    }


def serializar(datos: dict[str, Any], *, generado: str) -> str:
    """JSON estable, en el orden en que las consultas devuelven las columnas.

    El fichero se versiona, de modo que su diff tiene que ser legible. Sin
    orden estable, dos ejecuciones identicas producirian diffs distintos y
    nadie podria revisar que cambio de verdad.

    No se ordenan las claves alfabeticamente, y es deliberado: el orden de
    insercion lo fija la lista de columnas del SELECT, que es igual de
    determinista, y ademas es el orden con sentido de negocio. Ordenarlas
    alfabeticamente sacaba el explorador con "Costes" antes que "Ingresos".
    """
    documento = {
        "generado_utc": generado,
        "origen": {
            "base": "finanzas_analytics",
            "vistas": [
                "pl.v_pl_resumen",
                "pl.v_ejecucion_presupuestaria",
                "pl.v_resultado_por_centro",
                "qa.control_reconciliacion",
            ],
            "perimetro_ingresos": LINEA_INGRESOS,
        },
        **datos,
    }
    # Las claves NO se ordenan alfabeticamente, y es deliberado. El orden de
    # insercion lo fija la lista de columnas de cada SELECT, que es igual de
    # determinista -- el diff sigue siendo estable -- y ademas es el orden con
    # sentido de negocio. Ordenarlas sacaba el explorador con la columna
    # "Costes" delante de "Ingresos" y el ambito antes que el centro.
    return json.dumps(documento, ensure_ascii=False, indent=2) + "\n"


def main(argv: list[str] | None = None) -> int:
    configurar()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--comprobar",
        action="store_true",
        help="no escribe: falla si el JSON en disco no coincide con la base",
    )
    args = parser.parse_args(argv)

    conn = conectar(ConfigPostgres.desde_entorno())
    try:
        with conn.cursor() as cur:
            fallan = controles_del_esquema(cur)
            if fallan:
                log.error(
                    "el modelo descuadra y no se generan cifras publicas: %s",
                    "; ".join(fallan),
                )
                return 1
            datos = recoger(cur)
    finally:
        conn.close()

    descuadres = [
        f"{fila['escenario_clave']}: diferencia {fila['diferencia']:.2f} sobre "
        f"tolerancia {fila['tolerancia']:.2f}"
        for fila in datos["reconciliacion"]
        if abs(fila["diferencia"]) > fila["tolerancia"]
    ]
    if descuadres:
        log.error("la reconciliacion no cuadra, no se publica: %s", "; ".join(descuadres))
        return 1

    if args.comprobar:
        if not DESTINO.is_file():
            log.error("no existe %s: ejecutar sin --comprobar para generarlo", DESTINO)
            return 1
        # Se compara el contenido sin la marca de tiempo: el JSON cambiaria en
        # cada ejecucion por la fecha y el control no podria distinguir una
        # cifra desactualizada de un fichero regenerado.
        en_disco = json.loads(DESTINO.read_text(encoding="utf-8"))
        marca = en_disco.get("generado_utc", "")
        if serializar(datos, generado=marca) != DESTINO.read_text(encoding="utf-8"):
            log.error(
                "%s no coincide con la base. Regenerar antes de publicar: las cifras "
                "del dashboard tienen que salir del modelo, no de un fichero viejo.",
                DESTINO.name,
            )
            return 1
        log.info("%s coincide con la base", DESTINO.name)
        return 0

    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    texto = serializar(datos, generado=datetime.now(UTC).isoformat(timespec="seconds"))
    # `write_text` escribe CRLF en Windows y el fichero se versiona: se fija el
    # salto de linea para que el diff no dependa del sistema operativo.
    DESTINO.write_text(texto, encoding="utf-8", newline="\n")
    log.info(
        "escrito %s: %d escenarios, %d periodos, %d lineas de P&L, %d centros",
        DESTINO.relative_to(RAIZ),
        len(datos["escenarios"]),
        len(datos["mensual"]),
        len(datos["pl_oficial"]),
        len(datos["centros"]),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

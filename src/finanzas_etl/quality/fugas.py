"""Auditoria de fuga de datos sobre las salidas publicables.

Comprobar que la anonimizacion "se ejecuto" no demuestra nada: lo que hay que
demostrar es que ningun valor sensible del origen aparece en los ficheros que
se van a publicar. Este modulo hace esa verificacion a la inversa, partiendo
del libro original: toma los valores reales de las columnas sensibles y los
busca uno por uno en los Parquet de salida.

Es un control adversario, no un control de proceso. Si alguien anade una
columna al contrato y olvida declararla sensible, los controles del pipeline
seguiran pasando y este fallara.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from ..anonymize.scaler import error_maximo_agregado
from ..logging_setup import logger

log = logger("quality.fugas")


@dataclass(slots=True)
class Fuga:
    tabla: str
    columna: str
    valor: str
    ocurrencias: int

    def __str__(self) -> str:
        return (
            f"{self.tabla}.{self.columna}: el valor original {self.valor!r} "
            f"aparece {self.ocurrencias:,} veces"
        )


def auditar(
    carpeta_salida: Path,
    valores_sensibles: dict[str, set[str]],
    *,
    maximo_por_dominio: int | None = None,
) -> list[Fuga]:
    """Busca valores del origen en las tablas publicables.

    Parameters
    ----------
    carpeta_salida:
        Carpeta con los Parquet a auditar. Los ficheros cuyo nombre empieza por
        `_` se excluyen: son artefactos locales, como el mapa de reversion, que
        contienen los valores originales por definicion y no se publican.
    valores_sensibles:
        `{dominio: {valores originales}}`, tal como salen del libro.
    maximo_por_dominio:
        Limita cuantos valores se comprueban por dominio. Util para acotar el
        coste en dominios de cardinalidad muy alta, como los documentos.
    """
    fugas: list[Fuga] = []
    tablas = sorted(p for p in carpeta_salida.glob("*.parquet") if not p.name.startswith("_"))
    if not tablas:
        raise FileNotFoundError(f"no hay Parquet publicables en {carpeta_salida}")

    for ruta in tablas:
        df = pd.read_parquet(ruta)
        texto = df.select_dtypes(include=["object", "string", "category"])
        log.info("auditando %s (%s filas, %d columnas de texto)",
                 ruta.name, f"{len(df):,}", texto.shape[1])

        for columna in texto.columns:
            presentes = set(texto[columna].dropna().astype("string").unique())
            for dominio, valores in valores_sensibles.items():
                muestra = sorted(valores)
                if maximo_por_dominio is not None:
                    muestra = muestra[:maximo_por_dominio]
                for valor in muestra:
                    if valor in presentes:
                        ocurrencias = int((texto[columna].astype("string") == valor).sum())
                        fuga = Fuga(ruta.stem, columna, valor, ocurrencias)
                        log.error("FUGA [%s] %s", dominio, fuga)
                        fugas.append(fuga)

    if fugas:
        log.error("auditoria fallida: %d fugas detectadas", len(fugas))
    else:
        log.info("auditoria superada: ningun valor sensible del origen en las salidas")
    return fugas


def valores_sensibles_del_mapa(ruta_mapa: Path) -> dict[str, set[str]]:
    """Reconstruye el universo de valores sensibles desde el mapa de reversion.

    El mapa es la lista exhaustiva de lo que se pseudonimizo, de modo que sirve
    como fuente de verdad de la auditoria sin volver a recorrer el libro.
    """
    mapa = pd.read_csv(ruta_mapa, dtype="string")
    dominios: dict[str, set[str]] = {}
    for dominio, grupo in mapa.groupby("dominio"):
        dominios[str(dominio)] = set(grupo["valor_original"].dropna())
    log.info(
        "universo sensible: %s",
        ", ".join(f"{k} ({len(v):,})" for k, v in sorted(dominios.items())),
    )
    return dominios


# --- Lo que sale de Power BI -----------------------------------------------
#
# El informe anade dos superficies que la auditoria de los Parquet no ve.
#
# La primera es el texto que se escribe a mano: descripciones de tabla y de
# medida, titulos de visual, rotulos de eje y las selecciones iniciales de los
# segmentadores, que guardan valores literales. Nada de eso pasa por el ETL, de
# modo que un nombre real escrito ahi llegaria intacto al repositorio.
#
# La segunda es el origen de cada particion: el modelo lee por SQL, y una
# consulta que apuntase fuera de los esquemas auditados traeria datos que nunca
# pasaron por la anonimizacion.
#
# Lo que NO se audita, y por que: el cache del modelo (.pbi/cache.abf) y un
# PBIX exportado llevan los datos dentro, pero VertiPaq comprime sus
# diccionarios y una busqueda literal no encuentra en ellos ni los valores que
# si contienen -- comprobado sobre el cache real con pseudonimos presentes en
# el modelo. Auditarlos por bytes seria un control incapaz de fallar. Ambos
# estan excluidos del repositorio, y lo que de verdad los protege es que su
# contenido viene de los Parquet que esta misma auditoria ya recorre.

ESQUEMAS_AUDITADOS = ("core", "pl", "qa")

#: Ficheros de texto que acaban publicados: el proyecto PBIP, la documentacion,
#: el codigo, el SQL y la capa web. Un nombre real escrito en cualquiera de
#: ellos se publica igual que si estuviera en una tabla.
#:
#: Los cuatro sufijos de la web se anadieron en la etapa 4, y la omision era
#: grave: el dashboard de GitHub Pages es el fichero **mas** publico del
#: repositorio -- lo lee cualquiera, sin clonar nada ni instalar nada -- y era
#: justo el que la auditoria no miraba.
SUFIJOS_PUBLICABLES = (
    ".tmdl", ".json", ".dax", ".pbip", ".pbir", ".pbism", ".platform",
    ".md", ".py", ".sql", ".toml", ".cfg", ".txt", ".yml", ".yaml",
    ".html", ".css", ".js", ".svg",
)

#: Carpetas que nunca se auditan. `.pbi` es estado local de Power BI Desktop y
#: `data` guarda el mapa de reversion, que contiene los valores originales por
#: definicion: auditarlo daria una fuga por cada linea.
EXCLUIDAS = {".pbi", ".git", "data", "__pycache__", ".venv", ".ruff_cache", ".pytest_cache"}


@dataclass(slots=True)
class FugaTexto:
    fichero: str
    dominio: str
    valor: str
    linea: int

    def __str__(self) -> str:
        return (
            f"{self.fichero}:{self.linea}: el valor original {self.valor!r} "
            f"del dominio {self.dominio}"
        )


def ficheros_publicables(*raices: Path) -> list[Path]:
    """Ficheros de texto que acabarian publicados, bajo las raices dadas.

    Una raiz puede ser un fichero suelto -- el README -- o una carpeta que se
    recorre entera saltando lo que no se versiona.
    """
    encontrados: set[Path] = set()
    for raiz in raices:
        if raiz.is_file():
            encontrados.add(raiz)
            continue
        for p in raiz.rglob("*"):
            # `Path(".platform").suffix` es la cadena vacia: un nombre que
            # empieza por punto no tiene extension para pathlib. El sufijo
            # `.platform` llevaba tres etapas en la lista sin casar con nada, y
            # los dos ficheros `.platform` del PBIP -- que se publican -- no se
            # auditaban. Lo descubrio `superficies_sin_auditar`.
            if not p.is_file() or (p.suffix or p.name) not in SUFIJOS_PUBLICABLES:
                continue
            if EXCLUIDAS.intersection(p.parts):
                continue
            encontrados.add(p)
    return sorted(encontrados)


def _es_binario(ruta: Path) -> bool:
    """Heuristica de git: hay un byte nulo en la cabecera.

    Se prefiere a una lista de sufijos binarios porque la lista es justo lo que
    se queda corta: el fallo que este control existe para evitar.
    """
    try:
        return b"\0" in ruta.open("rb").read(8192)
    except OSError:
        return True


def ficheros_que_git_publicara(raiz: Path) -> list[Path]:
    """Lo que un `git push` subiria: lo versionado mas lo nuevo no ignorado.

    `--others --exclude-standard` incluye los ficheros que todavia no estan en
    el indice pero tampoco en `.gitignore`. Son los que mas importan: el
    momento peligroso es el primer commit de una superficie nueva, cuando nadie
    la ha revisado aun.
    """
    git = shutil.which("git")
    if git is None:
        raise FileNotFoundError(
            "no se encuentra git. La auditoria enumera lo publicable preguntandoselo "
            "a git, y sin el no hay forma de saber que se publicaria."
        )
    salida = subprocess.run(
        [git, "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=raiz,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [raiz / nombre for nombre in salida.split("\0") if nombre]


def superficies_sin_auditar(raiz: Path, auditados: Sequence[Path]) -> list[str]:
    """Ficheros de texto que git publicaria y que la auditoria no mira.

    Las raices de `ficheros_publicables` son una lista escrita a mano, y una
    lista escrita a mano se queda corta en silencio. Ya paso dos veces: la
    etapa 4 descubrio que ni `reports/`, ni `pyproject.toml`, ni los sufijos de
    la web estaban cubiertos, y nada habia avisado.

    Este control invierte la pregunta. En lugar de comprobar que lo listado
    esta limpio, comprueba que **no queda nada fuera de la lista**: cualquier
    carpeta o extension nueva que entre en el repositorio hace fallar la
    auditoria hasta que alguien decida, explicitamente, si se audita o no.
    """
    vistos = {p.resolve() for p in auditados}
    fuera: list[str] = []
    for ruta in ficheros_que_git_publicara(raiz):
        if not ruta.is_file() or EXCLUIDAS.intersection(ruta.parts):
            continue
        if ruta.resolve() in vistos or _es_binario(ruta):
            continue
        fuera.append(str(ruta.relative_to(raiz)))
    return sorted(fuera)


# --- Los importes reales --------------------------------------------------
#
# La auditoria de arriba busca identificadores, y los saca del mapa de
# reversion. Un importe real no esta en ese mapa y no puede estarlo: los
# importes no se pseudonimizan, se **escalan** por un factor global, de modo
# que el mapa no los contiene y el universo sensible no los incluia.
#
# El hueco no era teorico. En la etapa 4, a punto de publicar, se encontro la
# facturacion anual real del empleador en dos ficheros versionados: la tabla de
# reconciliacion del README y el informe de calidad del ETL, que la escribia
# solo porque ese control se ejecuta tambien **antes** de anonimizar. Las dos
# cifras llevaban tres etapas publicadas y ningun control podia verlas.
#
# Este control cierra el hueco por el lado contrario al de los identificadores:
# en lugar de buscar literales, extrae del texto todo lo que parezca un numero,
# lo normaliza y lo compara contra los importes oficiales sin escalar. Tiene
# que ser asi porque los dos casos reales venian en formatos que no se parecen
# entre si -- uno con el punto separando millares y la coma los decimales, el
# otro al reves y con cuatro decimales --, de modo que ninguna busqueda literal
# los habria encontrado a los dos.
#
# Y una nota sobre esta nota: la primera version de este comentario citaba las
# dos cifras como ejemplo, con lo que el fichero que estrena el control fallaba
# el control. Es el mismo error que el README cometio en la etapa 1 al contar
# una fuga reproduciendo el literal fugado.

#: Por debajo de este importe no se busca. Los numeros pequenos de la
#: documentacion -- versiones, tolerancias, recuentos, numeros de linea --
#: colisionarian con importes reales pequenos y llenarian la auditoria de
#: falsos positivos. Las cifras que una documentacion cita son agregados, y los
#: del patron oficial son de siete y ocho digitos.
IMPORTE_MINIMO_AUDITABLE = 10_000.0

_NUMERO = re.compile(r"\d[\d.,\xa0\s]*\d|\d")


@dataclass(slots=True)
class ImporteSensible:
    """Un importe real del patron oficial, con la tolerancia de su estimacion."""

    valor: float
    tolerancia: float
    concepto: str


@dataclass(slots=True)
class FugaImporte:
    fichero: str
    concepto: str
    valor: float
    texto: str
    linea: int

    def __str__(self) -> str:
        return (
            f"{self.fichero}:{self.linea}: {self.texto!r} coincide con el importe "
            f"real de {self.concepto} ({self.valor:,.2f} sin escalar)"
        )


def _lecturas(token: str) -> list[float]:
    """Interpretaciones posibles de un numero escrito a mano.

    Los dos formatos que de hecho se colaron se contradicen: en uno el punto
    separa millares y la coma los decimales, y en el otro al reves. Cuando el
    token trae los dos signos, el ultimo en aparecer es el decimal y no hay
    ambiguedad: `12.345.678,90` y `12,345,678.9000` se leen bien los dos.

    Cuando solo trae uno y agrupa de tres en tres -- `1.234` -- las dos
    lecturas son legitimas y se devuelven **las dos**: este es un control
    adversario, y un falso positivo cuesta una comprobacion mientras que un
    falso negativo cuesta publicar la cifra.
    """
    limpio = token.replace("\xa0", "").replace(" ", "")
    if not limpio or not limpio[0].isdigit() or not limpio[-1].isdigit():
        return []

    tiene_punto, tiene_coma = "." in limpio, "," in limpio
    try:
        if tiene_punto and tiene_coma:
            decimal = "," if limpio.rindex(",") > limpio.rindex(".") else "."
            millar = "." if decimal == "," else ","
            return [float(limpio.replace(millar, "").replace(decimal, "."))]
        if not tiene_punto and not tiene_coma:
            return [float(limpio)]

        signo = "." if tiene_punto else ","
        trozos = limpio.split(signo)
        como_millares = float("".join(trozos))
        if len(trozos) > 2:
            # Dos o mas separadores iguales solo pueden ser millares.
            return [como_millares]
        como_decimal = float(limpio.replace(signo, "."))
        if len(trozos[1]) == 3:
            return [como_millares, como_decimal]
        return [como_decimal]
    except ValueError:
        return []


def importes_oficiales_reales(patron: Path, factor: float) -> list[ImporteSensible]:
    """Importes del patron oficial deshaciendo el escalado.

    El patron que se versiona esta ya escalado, de modo que el valor real se
    recupera dividiendo por el factor. La division no es exacta -- el escalado
    redondeo a centimos --, asi que cada importe llega con su tolerancia
    derivada del mismo modo que en el resto del pipeline: `n` importes
    agregados se desvian como maximo `n` medias centesimas.
    """
    if factor <= 0:
        raise ValueError("el factor de escalado debe ser positivo")

    mapa = pd.read_parquet(patron)
    sensibles: list[ImporteSensible] = []

    for (escenario,), grupo in mapa.groupby(["escenario_clave"]):
        anual = float(grupo["ingresos_oficiales"].sum()) / factor
        sensibles.append(
            ImporteSensible(
                valor=anual,
                tolerancia=error_maximo_agregado(len(grupo)) / factor,
                concepto=f"ingresos oficiales de {escenario}, ejercicio completo",
            )
        )
        for periodo, importe in zip(grupo["periodo"], grupo["ingresos_oficiales"], strict=True):
            sensibles.append(
                ImporteSensible(
                    valor=float(importe) / factor,
                    tolerancia=error_maximo_agregado(1) / factor,
                    concepto=f"ingresos oficiales de {escenario}, periodo {periodo}",
                )
            )

    grandes = [s for s in sensibles if abs(s.valor) >= IMPORTE_MINIMO_AUDITABLE]
    log.info(
        "universo de importes reales: %d agregados del patron oficial por encima de %s",
        len(grandes),
        f"{IMPORTE_MINIMO_AUDITABLE:,.0f}",
    )
    return grandes


def auditar_importes(
    ficheros: Sequence[Path], importes: Sequence[ImporteSensible]
) -> list[FugaImporte]:
    """Busca importes reales -- sin escalar -- en los ficheros publicables."""
    if not ficheros:
        raise FileNotFoundError("no se paso ningun fichero de texto que auditar")
    if not importes:
        raise ValueError(
            "el universo de importes esta vacio: la auditoria pasaria siempre y no "
            "demostraria nada"
        )

    fugas: list[FugaImporte] = []
    for ruta in ficheros:
        texto = ruta.read_text(encoding="utf-8", errors="replace")
        for numero, linea in enumerate(texto.splitlines(), start=1):
            for token in _NUMERO.findall(linea):
                lecturas = [v for v in _lecturas(token) if abs(v) >= IMPORTE_MINIMO_AUDITABLE]
                for valor in lecturas:
                    for sensible in importes:
                        if abs(valor - sensible.valor) <= sensible.tolerancia:
                            fuga = FugaImporte(
                                ruta.name, sensible.concepto, sensible.valor, token, numero
                            )
                            log.error("FUGA DE IMPORTE %s", fuga)
                            fugas.append(fuga)

    if fugas:
        log.error("auditoria de importes fallida: %d coincidencias", len(fugas))
    else:
        log.info("auditoria de importes superada: ningun importe real en lo publicable")
    return fugas


def auditar_texto(
    ficheros: Sequence[Path],
    valores_sensibles: dict[str, set[str]],
    *,
    maximo_por_dominio: int | None = None,
) -> list[FugaTexto]:
    """Busca valores del origen dentro de los ficheros de texto del informe.

    A diferencia de la auditoria de los Parquet, aqui se busca el valor como
    **subcadena** y no como celda completa: un nombre real no llegaria a este
    sitio en una columna, sino embebido en una frase.

    Para no recorrer cada fichero una vez por valor, primero se busca sobre
    todo el texto concatenado -- que son unos cientos de kilobytes -- y solo se
    localiza fichero y linea de los pocos valores que aparezcan.
    """
    if not ficheros:
        raise FileNotFoundError("no se paso ningun fichero de texto que auditar")

    contenidos = {p: p.read_text(encoding="utf-8", errors="replace") for p in ficheros}
    todo = "\n".join(contenidos.values())
    log.info(
        "auditando %d ficheros de texto publicables (%.0f KB)",
        len(ficheros),
        len(todo) / 1024,
    )

    fugas: list[FugaTexto] = []
    for dominio, valores in sorted(valores_sensibles.items()):
        muestra = sorted(valores)
        if maximo_por_dominio is not None:
            muestra = muestra[:maximo_por_dominio]
        for valor in muestra:
            if not valor or valor not in todo:
                continue
            for ruta, texto in contenidos.items():
                for numero, linea in enumerate(texto.splitlines(), start=1):
                    if valor in linea:
                        fuga = FugaTexto(ruta.name, dominio, valor, numero)
                        log.error("FUGA %s", fuga)
                        fugas.append(fuga)

    if fugas:
        log.error("auditoria de texto fallida: %d fugas detectadas", len(fugas))
    else:
        log.info("auditoria de texto superada: ningun valor sensible en lo publicable")
    return fugas


def auditar_origenes(
    carpeta: Path,
    *,
    esquemas: tuple[str, ...] = ESQUEMAS_AUDITADOS,
) -> list[str]:
    """Comprueba que ninguna particion lea fuera de los esquemas auditados.

    Todo lo que entra en el modelo viene por SQL. Mientras las consultas lean de
    `core`, `pl` o `qa`, el contenido es el que los Parquet ya auditados
    cargaron; una que apuntase a otra base o a otro esquema traeria datos que no
    pasaron por la anonimizacion, y ningun otro control lo veria.
    """
    sospechosas: list[str] = []
    patron_tabla = re.compile(r"\bfrom\s+([a-zA-Z_][\w.]*)", re.IGNORECASE)
    patron_join = re.compile(r"\bjoin\s+([a-zA-Z_][\w.]*)", re.IGNORECASE)

    for tmdl in sorted((carpeta / "definition" / "tables").glob("*.tmdl")):
        texto = tmdl.read_text(encoding="utf-8")
        for consulta in re.findall(r'\[Query="(.+?)"\]\)', texto, re.S):
            referencias = patron_tabla.findall(consulta) + patron_join.findall(consulta)
            for referencia in referencias:
                esquema = referencia.split(".")[0] if "." in referencia else ""
                if esquema not in esquemas:
                    sospechosas.append(
                        f"{tmdl.stem}: la consulta lee de {referencia!r}, "
                        f"fuera de los esquemas auditados {esquemas}"
                    )

    for aviso in sospechosas:
        log.error("ORIGEN NO AUDITADO %s", aviso)
    if not sospechosas:
        log.info("origenes del modelo: todas las particiones leen de %s", ", ".join(esquemas))
    return sospechosas

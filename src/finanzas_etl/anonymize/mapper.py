"""Pseudonimizacion determinista de identificadores y etiquetas.

Requisitos que cumple esta capa
-------------------------------
1. **Determinismo.** El mismo valor de origen produce siempre el mismo
   pseudonimo, dentro de una ejecucion y entre ejecuciones distintas. Sin esta
   propiedad las uniones del esquema estrella se romperian y el dashboard
   dejaria de ser comparable entre cargas.
2. **Preservacion de la cardinalidad.** Una aplicacion inyectiva: dos centros
   de coste distintos no pueden colapsar en el mismo pseudonimo, o los
   agregados cambiarian. Se verifica explicitamente.
3. **Irreversibilidad sin la clave.** El pseudonimo se deriva por HMAC-SHA256
   con una clave secreta. Sin la clave no se puede recorrer el espacio de
   codigos de centro de coste para reconstruir el mapa.
4. **Verosimilitud.** Un centro de coste llamado `a3f9b2e1` delata el proceso
   y afea el reporte. Las etiquetas legibles se sustituyen por nombres de un
   catalogo ficticio que conserva la forma del original (agencia, planta,
   funcion), de modo que el dashboard se lee como un caso real.

Lo que esta capa NO es
----------------------
No es anonimizacion en sentido estricto: quien posea el libro original y la
clave puede reconstruir la correspondencia, y los importes escalados por un
factor unico mantienen todas las razones entre si. Es pseudonimizacion, y el
objetivo es que las cifras y los nombres publicados no sean los de la empresa.
Para un caso de portafolio es el equilibrio correcto; para una cesion real de
datos haria falta agregacion y supresion de celdas de baja frecuencia.
"""

from __future__ import annotations

import hashlib
import hmac
import unicodedata
from collections.abc import Iterable

import pandas as pd

from ..logging_setup import logger

log = logger("anonymize.mapper")

# Catalogos ficticios. Son toponimos y funciones inventados que imitan la
# estructura del original (una red de agencias y centros operativos) sin
# coincidir con ninguna ubicacion real de la empresa.
_PLAZAS = (
    "Altamira", "Bellavista", "Canteras", "Dos Rios", "El Mirador", "Fuentes",
    "Granada", "Horizonte", "Isla Verde", "Jacaranda", "La Rambla", "Lomas",
    "Monteverde", "Naranjal", "Olivares", "Palmar", "Quebrada", "Riscos",
    "Salinas", "Terrazas", "Umbral", "Valle Alto", "Yungas", "Zafiro",
    "Arrecife", "Brisas", "Cumbres", "Delta", "Encinas", "Farallon",
)
_FUNCIONES = (
    "Operaciones", "Mantenimiento", "Comercial", "Administracion",
    "Distribucion", "Almacen", "Transporte", "Soporte",
)
_TIPOS_CENTRO = ("Agencia", "Centro", "Planta", "Terminal", "Base")


def _sin_acentos(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c)
    )


class Pseudonimizador:
    """Genera pseudonimos estables a partir de una clave HMAC."""

    def __init__(self, salt: str) -> None:
        self._clave = salt.encode("utf-8")
        self._mapas: dict[str, dict[str, str]] = {}

    # -- primitiva -----------------------------------------------------------

    def _digest(self, dominio: str, valor: str) -> int:
        """Entero derivado de (dominio, valor). El dominio evita que el mismo
        texto en dos columnas distintas reciba el mismo pseudonimo."""
        mac = hmac.new(self._clave, f"{dominio}\x1f{valor}".encode(), hashlib.sha256)
        return int.from_bytes(mac.digest()[:8], "big")

    def _asignar(self, dominio: str, valores: Iterable[str], generador) -> dict[str, str]:
        """Construye el mapa `valor -> pseudonimo` resolviendo colisiones.

        Los valores se ordenan antes de asignar para que el resultado no
        dependa del orden de llegada de las filas: el mapa es una funcion de la
        clave y del conjunto de valores, nada mas.
        """
        mapa: dict[str, str] = {}
        usados: set[str] = set()
        for valor in sorted(valores):
            semilla = self._digest(dominio, valor)
            candidato = generador(semilla, 0)
            intento = 1
            while candidato in usados:
                # Colision: reintentamos con un sufijo derivado del mismo
                # digest. Mantiene el determinismo y la inyectividad.
                candidato = generador(semilla, intento)
                intento += 1
            usados.add(candidato)
            mapa[valor] = candidato
        self._mapas[dominio] = mapa
        return mapa

    # -- generadores por tipo de dominio -------------------------------------

    @staticmethod
    def _gen_codigo(prefijo: str):
        def generar(semilla: int, intento: int) -> str:
            return f"{prefijo}-{(semilla + intento * 7919) % 9000 + 1000:04d}"

        return generar

    @staticmethod
    def _gen_documento(semilla: int, intento: int) -> str:
        return f"{(semilla + intento * 104729) % 900_000_000 + 100_000_000:09d}"

    @staticmethod
    def _gen_centro(semilla: int, intento: int) -> str:
        s = semilla + intento * 7919
        tipo = _TIPOS_CENTRO[s % len(_TIPOS_CENTRO)]
        plaza = _PLAZAS[(s // 5) % len(_PLAZAS)]
        funcion = _FUNCIONES[(s // 150) % len(_FUNCIONES)]
        return f"{tipo} {plaza} - {funcion}"

    # -- API -----------------------------------------------------------------

    def codigos(self, serie: pd.Series, *, dominio: str, prefijo: str) -> pd.Series:
        """Sustituye codigos internos por codigos sinteticos con prefijo."""
        valores = serie.dropna().unique().tolist()
        mapa = self._asignar(dominio, valores, self._gen_codigo(prefijo))
        log.info("%s: %d codigos pseudonimizados con prefijo %s", dominio, len(mapa), prefijo)
        return serie.map(mapa).astype("string")

    def documentos(self, serie: pd.Series, *, dominio: str = "documento") -> pd.Series:
        valores = serie.dropna().unique().tolist()
        mapa = self._asignar(dominio, valores, self._gen_documento)
        log.info("%s: %d documentos pseudonimizados", dominio, len(mapa))
        return serie.map(mapa).astype("string")

    def nombres_centro(self, serie: pd.Series, *, dominio: str = "ceco_nombre") -> pd.Series:
        """Sustituye nombres de centros por etiquetas del catalogo ficticio."""
        valores = serie.dropna().unique().tolist()
        mapa = self._asignar(dominio, valores, self._gen_centro)
        log.info("%s: %d nombres sustituidos por catalogo ficticio", dominio, len(mapa))
        return serie.map(mapa).astype("string")

    #: Traduccion de la taxonomia interna a terminos de negocio genericos. El
    #: orden importa: la primera clave que aparece en el literal gana.
    _TAXONOMIA = (
        ("mantto", "Mantenimiento"),
        ("mantenimiento", "Mantenimiento"),
        ("age", "Red de Agencias"),
        ("agencia", "Red de Agencias"),
        ("ope", "Operaciones"),
        ("operac", "Operaciones"),
        ("serv", "Servicios"),
        ("comercial", "Comercial"),
        ("gerencia", "Direccion"),
        ("soporte", "Soporte"),
        ("une", "Unidad de Negocio"),
        ("corp", "Corporativo"),
    )

    #: Matices que distinguen el caracter del coste dentro de una misma familia.
    _MATICES = (
        ("comun", "Comun"),
        ("institucional", "Dedicado"),
        ("instituc", "Dedicado"),
    )

    def generalizar_taxonomia(
        self, *series: pd.Series, dominio: str = "taxonomia_negocio"
    ) -> dict[str, str]:
        """Traduce la taxonomia interna a terminos de negocio genericos.

        Recibe varias series porque la misma nomenclatura interna -- la marca
        comercial de la unidad, con sus variantes de prefijo y separador --
        aparece repartida entre las columnas de ambito, estructura y unidad de
        negocio. Un unico dominio compartido
        garantiza que un literal reciba el mismo pseudonimo en todas ellas: si
        se mapease columna por columna, el valor original seguiria visible en
        la que se olvidase, y las tres dejarian de ser comparables entre si.

        Conserva el significado analitico (operaciones, agencias, servicios) y
        elimina la nomenclatura interna de la empresa. Devuelve el mapa para
        que el llamante lo aplique a cada columna.
        """
        universo = sorted(
            {
                str(v)
                for serie in series
                for v in serie.dropna().unique()
            }
        )
        mapa: dict[str, str] = {}
        sin_regla = 0
        for valor in universo:
            v = _sin_acentos(valor).lower()
            familia = next((etiqueta for clave, etiqueta in self._TAXONOMIA if clave in v), None)
            if familia is None:
                sin_regla += 1
                familia = f"Segmento {sin_regla:02d}"
            matiz = next((etiqueta for clave, etiqueta in self._MATICES if clave in v), None)
            mapa[valor] = f"{familia} - {matiz}" if matiz else familia

        self._mapas[dominio] = mapa
        log.info(
            "%s: %d literales generalizados a %d etiquetas (%d sin regla)",
            dominio, len(mapa), len(set(mapa.values())), sin_regla,
        )
        return mapa

    # -- auditoria -----------------------------------------------------------

    @property
    def mapas(self) -> dict[str, dict[str, str]]:
        return self._mapas

    def mapa_reversion(self) -> pd.DataFrame:
        """Tabla `dominio, valor_original, pseudonimo` para auditoria local.

        Permite demostrar que la transformacion es inyectiva y rehacer el
        camino si hiciera falta validar una cifra contra el libro original.
        Se guarda fuera del repositorio: es el unico artefacto que, junto con
        la clave, deshace la pseudonimizacion.
        """
        filas = [
            {"dominio": dominio, "valor_original": original, "pseudonimo": pseudo}
            for dominio, mapa in self._mapas.items()
            for original, pseudo in mapa.items()
        ]
        return pd.DataFrame(filas)

    #: Dominios donde colapsar valores es el objetivo y no un defecto. La
    #: generalizacion de la taxonomia agrupa a proposito varios literales
    #: internos bajo una misma etiqueta de negocio, lo que reduce el detalle
    #: publicado en lugar de limitarse a sustituirlo.
    DOMINIOS_NO_INYECTIVOS = frozenset({"taxonomia_negocio"})

    def verificar_inyectividad(self) -> None:
        """Comprueba que ningun dominio de identificadores colapso dos valores.

        Una colision en un identificador fundiria dos centros de coste en uno y
        alteraria los agregados, de modo que es un fallo bloqueante. En los
        dominios de generalizacion el colapso es intencionado y se omite.
        """
        comprobados = 0
        for dominio, mapa in self._mapas.items():
            if dominio in self.DOMINIOS_NO_INYECTIVOS:
                continue
            comprobados += 1
            if len(set(mapa.values())) != len(mapa):
                raise AssertionError(
                    f"colision no resuelta en el dominio {dominio!r}: "
                    f"{len(mapa)} valores -> {len(set(mapa.values()))} pseudonimos"
                )
        log.info("inyectividad verificada en %d dominios de identificador", comprobados)

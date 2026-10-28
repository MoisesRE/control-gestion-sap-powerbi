"""Pruebas de la auditoria sobre lo que se publica como texto.

El criterio de este repositorio es que un control que no puede fallar no es un
control. Estas pruebas no comprueban que la auditoria pase con el repositorio
sano, que es lo facil: **le ponen delante una fuga y comprueban que la
encuentra**, y le ponen delante un texto limpio para comprobar que no inventa
ninguna.

La auditoria nacio porque la de los Parquet no ve nada de lo que se escribe a
mano. Su primera ejecucion encontro dieciocho valores reales repartidos entre
el nombre de un tema, los comentarios del modelo, el README y los datos de
prueba de dos ficheros de test, todos introducidos a mano a lo largo de las
tres etapas.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pandas as pd
import pytest

from finanzas_etl.quality.fugas import (
    auditar_importes,
    auditar_origenes,
    auditar_texto,
    ficheros_publicables,
    importes_oficiales_reales,
    superficies_sin_auditar,
)

SENSIBLES = {
    "ceco": {"QXZAB90001", "QXZCD90002"},
    "ceco_nombre": {"Agencia Puerto Viejo"},
}


def escribir(carpeta: Path, nombre: str, texto: str) -> Path:
    ruta = carpeta / nombre
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(texto, encoding="utf-8")
    return ruta


class TestDetectaLaFuga:
    def test_encuentra_un_codigo_real_en_una_descripcion(self, tmp_path):
        """El caso que motiva la auditoria: un valor escrito a mano."""
        ruta = escribir(
            tmp_path,
            "Centro.tmdl",
            "table 'Centro de Coste'\n"
            "\t/// Ejemplo: el centro QXZAB90001 concentra el gasto de taller.\n"
            "\tcolumn Codigo\n",
        )
        fugas = auditar_texto([ruta], SENSIBLES)
        assert [f.valor for f in fugas] == ["QXZAB90001"]
        assert fugas[0].dominio == "ceco"

    def test_senala_el_fichero_y_la_linea(self, tmp_path):
        """Sin la posicion, el aviso obliga a buscar a mano en 700 KB."""
        ruta = escribir(
            tmp_path, "report.json", '{\n  "a": 1,\n  "titulo": "Agencia Puerto Viejo"\n}\n'
        )
        (fuga,) = auditar_texto([ruta], SENSIBLES)
        assert fuga.fichero == "report.json"
        assert fuga.linea == 3

    def test_lo_encuentra_embebido_en_una_frase(self, tmp_path):
        """Un nombre real no llega aqui en una celda, sino dentro de un texto."""
        ruta = escribir(
            tmp_path, "notas.md", "El reparto de la Agencia Puerto Viejo se revisa aparte.\n"
        )
        assert len(auditar_texto([ruta], SENSIBLES)) == 1

    def test_denuncia_cada_aparicion(self, tmp_path):
        ruta = escribir(tmp_path, "x.py", "A = 'QXZAB90001'\nB = 'QXZAB90001'\n")
        assert len(auditar_texto([ruta], SENSIBLES)) == 2


class TestNoInventaFugas:
    def test_un_texto_limpio_no_dispara_nada(self, tmp_path):
        ruta = escribir(
            tmp_path, "Centro.tmdl", "table 'Centro de Coste'\n\tcolumn 'Codigo Centro'\n"
        )
        assert auditar_texto([ruta], SENSIBLES) == []

    def test_los_pseudonimos_no_son_fuga(self, tmp_path):
        """Lo que publica el modelo son los pseudonimos, y deben poder estar."""
        ruta = escribir(tmp_path, "Centro.tmdl", "/// Ejemplo: CC-1043\n")
        assert auditar_texto([ruta], SENSIBLES) == []

    def test_sin_ficheros_falla_en_vez_de_pasar_en_vacio(self):
        """Una auditoria sobre cero ficheros pasaria siempre."""
        with pytest.raises(FileNotFoundError):
            auditar_texto([], SENSIBLES)


class TestQueFicherosEntran:
    def test_recoge_el_texto_y_salta_el_binario(self, tmp_path):
        escribir(tmp_path, "modelo.tmdl", "x")
        escribir(tmp_path, "notas.md", "x")
        (tmp_path / "datos.parquet").write_bytes(b"\x00\x01")
        nombres = {p.name for p in ficheros_publicables(tmp_path)}
        assert nombres == {"modelo.tmdl", "notas.md"}

    def test_salta_el_estado_local_de_power_bi(self, tmp_path):
        """`.pbi` guarda el cache con los datos y no se versiona."""
        escribir(tmp_path, "modelo.tmdl", "x")
        escribir(tmp_path, ".pbi/localSettings.json", '{"ruta": "QXZAB90001"}')
        assert {p.name for p in ficheros_publicables(tmp_path)} == {"modelo.tmdl"}

    def test_salta_el_mapa_de_reversion(self, tmp_path):
        """data/ contiene los valores originales por definicion."""
        escribir(tmp_path, "data/_mapa_reversion.txt", "QXZAB90001")
        escribir(tmp_path, "sql/vistas.sql", "select 1")
        assert {p.name for p in ficheros_publicables(tmp_path)} == {"vistas.sql"}

    def test_admite_un_fichero_suelto(self, tmp_path):
        ruta = escribir(tmp_path, "README.md", "x")
        assert ficheros_publicables(ruta) == [ruta]


class TestOrigenesDelModelo:
    def escribir_particion(self, tmp_path: Path, consulta: str) -> Path:
        modelo = tmp_path / "Modelo.SemanticModel"
        escribir(
            modelo / "definition" / "tables",
            "Resultado.tmdl",
            "table Resultado\n"
            "\tpartition Resultado = m\n"
            "\t\tsource =\n"
            "\t\t\t\tlet\n"
            f'\t\t\t\t    Origen = PostgreSQL.Database(S, B, [Query="{consulta}"])\n'
            "\t\t\t\tin\n"
            "\t\t\t\t    Origen\n",
        )
        return modelo

    def test_acepta_los_esquemas_auditados(self, tmp_path):
        modelo = self.escribir_particion(tmp_path, "select a, b from core.fact_escenario")
        assert auditar_origenes(modelo) == []

    def test_denuncia_una_consulta_a_otro_esquema(self, tmp_path):
        """El vector real: una particion que trae datos sin anonimizar."""
        modelo = self.escribir_particion(tmp_path, "select * from produccion.clientes")
        (aviso,) = auditar_origenes(modelo)
        assert "produccion.clientes" in aviso

    def test_mira_tambien_los_join(self, tmp_path):
        """Una consulta puede entrar por el join y no por el from."""
        modelo = self.escribir_particion(
            tmp_path,
            "select a from core.fact_escenario f join crudo.apuntes c on c.id = f.id",
        )
        avisos = auditar_origenes(modelo)
        assert len(avisos) == 1
        assert "crudo.apuntes" in avisos[0]


class TestElRepositorioEstaLimpio:
    """El estado que la auditoria debe mantener, comprobado desde las pruebas."""

    def test_el_modelo_solo_lee_de_los_esquemas_auditados(self):
        raiz = Path(__file__).resolve().parents[1]
        modelo = raiz / "powerbi" / "ResultadoFinanciero.SemanticModel"
        if not modelo.is_dir():
            pytest.skip("no hay informe en este arbol")
        assert auditar_origenes(modelo) == []


class TestLaCapaWeb:
    """La etapa 4 publica un dashboard HTML, y era la superficie descubierta.

    Un fichero de GitHub Pages lo lee cualquiera sin clonar el repositorio ni
    instalar nada, de modo que es el sitio **mas** publico donde puede acabar
    un valor real. La auditoria no miraba ninguna de sus cuatro extensiones.
    """

    def test_audita_las_cuatro_extensiones_de_la_web(self, tmp_path):
        for nombre in ("index.html", "estilo.css", "grafico.js", "logo.svg"):
            escribir(tmp_path, nombre, "x")
        nombres = {p.name for p in ficheros_publicables(tmp_path)}
        assert nombres == {"index.html", "estilo.css", "grafico.js", "logo.svg"}

    def test_encuentra_un_valor_real_en_el_dashboard(self, tmp_path):
        ruta = escribir(
            tmp_path,
            "index.html",
            '<section>\n  <h2>Agencia Puerto Viejo</h2>\n</section>\n',
        )
        (fuga,) = auditar_texto([ruta], SENSIBLES)
        assert fuga.dominio == "ceco_nombre"
        assert fuga.linea == 2

    def test_audita_los_dotfiles_del_pbip(self, tmp_path):
        """`Path('.platform').suffix` es la cadena vacia, no `.platform`.

        El sufijo llevaba tres etapas declarado sin casar con nada, y los dos
        ficheros `.platform` del proyecto -- que se publican y llevan el nombre
        del elemento dentro -- no se auditaban. No lo encontro una revision:
        lo encontro `superficies_sin_auditar` al cruzar la lista con git.
        """
        escribir(tmp_path, ".platform", '{"metadata": {"displayName": "x"}}')
        assert [p.name for p in ficheros_publicables(tmp_path)] == [".platform"]


class TestSuperficiesSinAuditar:
    """El control que vigila al control.

    Las raices que se auditan son una lista escrita a mano, y una lista escrita
    a mano se queda corta sin que nada avise: asi se quedaron fuera `reports/`,
    `pyproject.toml`, las cuatro extensiones de la web y los dos `.platform`.
    Este control invierte la pregunta -- que publicaria git que nadie mira --
    de modo que una carpeta o una extension nueva hace fallar la auditoria
    hasta que alguien decida explicitamente si se audita.
    """

    def repo(self, tmp_path: Path, ignorados: str = "") -> Path:
        subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
        escribir(tmp_path, ".gitignore", ignorados)
        return tmp_path

    def test_denuncia_un_fichero_que_nadie_audita(self, tmp_path):
        raiz = self.repo(tmp_path)
        escribir(raiz, "docs/index.html", "<p>x</p>")
        escribir(raiz, "web/suelto.html", "<p>x</p>")
        auditados = ficheros_publicables(raiz / "docs")
        assert superficies_sin_auditar(raiz, auditados) == [
            str(Path(".gitignore")),
            str(Path("web/suelto.html")),
        ]

    def test_no_denuncia_lo_que_ya_se_audita(self, tmp_path):
        raiz = self.repo(tmp_path)
        escribir(raiz, "docs/index.html", "<p>x</p>")
        auditados = ficheros_publicables(raiz / "docs", raiz / ".gitignore")
        assert superficies_sin_auditar(raiz, auditados) == []

    def test_ignora_los_binarios(self, tmp_path):
        """Un PNG no se puede auditar por texto, y exigirlo seria un control falso.

        Es el mismo argumento que descarto auditar el cache de VertiPaq: una
        busqueda literal no encuentra en un binario ni los valores que contiene.
        Lo que protege a una captura es que su contenido viene del modelo, que
        si se audita.
        """
        raiz = self.repo(tmp_path)
        (raiz / "captura.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00dato")
        auditados = ficheros_publicables(raiz / ".gitignore")
        assert superficies_sin_auditar(raiz, auditados) == []

    def test_ignora_lo_que_git_no_publicaria(self, tmp_path):
        """El `.env` y el mapa de reversion existen en disco y no se publican."""
        raiz = self.repo(tmp_path, ignorados=".env\n")
        escribir(raiz, ".env", "ANON_SALT=secreto")
        auditados = ficheros_publicables(raiz / ".gitignore")
        assert superficies_sin_auditar(raiz, auditados) == []

    def test_sin_git_falla_en_vez_de_pasar_en_vacio(self, tmp_path, monkeypatch):
        """Sin git no se sabe que se publicaria, y callarse seria peor."""
        monkeypatch.setattr(shutil, "which", lambda _: None)
        with pytest.raises(FileNotFoundError, match="git"):
            superficies_sin_auditar(tmp_path, [])


class TestImportesReales:
    """El control que faltaba, y por que faltaba.

    La auditoria de literales busca identificadores y los saca del mapa de
    reversion. Un importe real no esta en ese mapa y no puede estarlo: los
    importes no se pseudonimizan, se escalan por un factor global. El universo
    sensible no los incluia, de modo que ninguna de las 160 pruebas ni ninguno
    de los 55 controles podia ver un importe real escrito a mano.

    Lo que se encontro al cerrar el hueco, con el repositorio ya dado por
    limpio tres veces: la facturacion anual del empleador en la tabla de
    reconciliacion del README, el total del ejercicio en el informe de calidad
    del ETL -- que lo escribia porque ese control corre tambien antes de
    anonimizar -- y el ingreso de un mes como dato de prueba de un test,
    puesto en la etapa 1.
    """

    FACTOR = 2.0
    #: 20.000.000 escalado por 2,0. El real es la mitad, y es lo que no se publica.
    PATRON = [("R2025", 1, 20_000_000.0), ("R2025", 2, 24_000_000.0)]

    def patron(self, tmp_path: Path) -> Path:
        ruta = tmp_path / "control_reconciliacion.parquet"
        pd.DataFrame(
            self.PATRON, columns=["escenario_clave", "periodo", "ingresos_oficiales"]
        ).to_parquet(ruta)
        return ruta

    def universo(self, tmp_path: Path) -> list:
        return importes_oficiales_reales(self.patron(tmp_path), self.FACTOR)

    def test_deshace_el_escalado(self, tmp_path):
        valores = sorted(s.valor for s in self.universo(tmp_path))
        # Los dos periodos y el total del ejercicio, todos sin escalar.
        assert valores == [10_000_000.0, 12_000_000.0, 22_000_000.0]

    def test_encuentra_un_importe_real_en_formato_europeo(self, tmp_path):
        ruta = escribir(tmp_path, "README.md", "| Real 2025 | 10.000.000,00 | 0,00 |\n")
        (fuga,) = auditar_importes([ruta], self.universo(tmp_path))
        assert fuga.linea == 1
        assert "periodo 1" in fuga.concepto

    def test_encuentra_el_mismo_importe_en_formato_anglosajon(self, tmp_path):
        """Los dos formatos reales se contradicen, y hay que coger los dos."""
        ruta = escribir(tmp_path, "calidad.md", "- `total`: 10,000,000.0000\n")
        (fuga,) = auditar_importes([ruta], self.universo(tmp_path))
        assert fuga.texto == "10,000,000.0000"

    def test_encuentra_un_importe_sin_separadores(self, tmp_path):
        ruta = escribir(tmp_path, "test_lector.py", 'VALOR = "12000000.00"\n')
        assert len(auditar_importes([ruta], self.universo(tmp_path))) == 1

    def test_no_denuncia_el_importe_escalado(self, tmp_path):
        """El escalado es justo lo que SI se publica: no puede ser una fuga.

        Es la mitad del control. Uno que denunciase las cifras publicables
        obligaria a silenciarlo, y un control silenciado no es un control.
        """
        ruta = escribir(tmp_path, "README.md", "| Real 2025 | 20.000.000,00 |\n")
        assert auditar_importes([ruta], self.universo(tmp_path)) == []

    def test_la_tolerancia_absorbe_el_redondeo_del_escalado(self, tmp_path):
        """El real se estima dividiendo, y la division no es exacta.

        La tolerancia se deriva del proceso -- `n` importes agregados se
        desvian como maximo `n` medias centesimas -- en lugar de elegirse hasta
        que el control pase.
        """
        ruta = escribir(tmp_path, "notas.md", "El periodo cerro en 10.000.000,01.\n")
        assert len(auditar_importes([ruta], self.universo(tmp_path))) == 1

    def test_ignora_los_numeros_pequenos(self, tmp_path):
        """Versiones, recuentos y tolerancias llenarian la auditoria de ruido."""
        ruta = escribir(tmp_path, "notas.md", "ruff 0.17.1, 160 pruebas, tolerancia 0,05\n")
        assert auditar_importes([ruta], self.universo(tmp_path)) == []

    def test_un_universo_vacio_falla_en_vez_de_pasar(self, tmp_path):
        """Sin importes que buscar, el control pasaria siempre."""
        ruta = escribir(tmp_path, "README.md", "x\n")
        with pytest.raises(ValueError, match="vacio"):
            auditar_importes([ruta], [])

    def test_un_factor_invalido_no_se_acepta(self, tmp_path):
        """Dividir por cero daria un universo infinito y silencioso."""
        with pytest.raises(ValueError, match="positivo"):
            importes_oficiales_reales(self.patron(tmp_path), 0.0)

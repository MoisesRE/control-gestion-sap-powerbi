"""Publica el portafolio en un repositorio nuevo, sin historial.

**El historial de este repositorio no se publica**, y no es una preferencia de
estilo. La auditoria de texto encontro valores reales en commits de las tres
etapas: codigos de centro usados como datos de prueba, la marca comercial de la
empresa citada en el propio README y dos toponimos autenticos. El arbol de
trabajo quedo limpio, pero `git log -S` los recupera en segundos, de modo que
publicar el historial publicaria justo lo que el pipeline se dedica a borrar.

Reescribirlo con `git filter-repo` habria conservado el relato de las etapas a
cambio de reescribir todos los hashes y de confiar en que la reescritura no se
dejase nada. Se eligio lo simple y lo verificable: **un repositorio nuevo cuyo
primer commit es el estado actual del arbol**, construido aqui.

Lo que se copia es exactamente lo que la auditoria acaba de revisar: lo que
`git ls-files` declara versionado mas lo nuevo que no esta ignorado. No se
recorre el disco, de modo que un fichero excluido en `.gitignore` no puede
colarse por descuido.

    python scripts/publicar.py --nombre mi-repo                        # ensayo
    python scripts/publicar.py --nombre mi-repo --publicar             # crea y sube
    python scripts/publicar.py --nombre mi-repo --publicar --forzar    # rehace

Sin `--publicar` prepara la copia, pasa todas las puertas y se detiene: deja el
arbol listo para mirarlo antes de que exista nada en GitHub.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from finanzas_etl.logging_setup import configurar, logger  # noqa: E402
from finanzas_etl.quality.fugas import ficheros_que_git_publicara  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]

# Lo que no puede acabar en un repositorio publico bajo ningun concepto. Las
# tres listas duplican a proposito lo que ya dice `.gitignore`: un `.gitignore`
# mal editado es un error de una linea, y esto es la segunda cerradura sobre la
# misma puerta.
#
# Van separadas por tipo de coincidencia y no en una sola lista de subcadenas,
# porque la primera version si lo era y denuncio `.env.example` -- la plantilla
# sin secretos que **si** se publica -- por contener `.env`. Un control que
# obliga a silenciarlo deja de ser un control.

#: Nombres de fichero exactos.
PROHIBIDOS_NOMBRE = (".env", "localsettings.json")

#: Fragmentos de ruta: la carpeta o el prefijo delatan el fichero.
PROHIBIDOS_RUTA = ("_mapa_reversion", "data/raw/", "data/interim/", ".pbi/")

#: Extensiones que nunca se publican, con el libro de origen a la cabeza.
PROHIBIDOS_SUFIJO = (".xlsx", ".xlsb", ".xls", ".abf")


def esta_prohibido(relativa: str) -> bool:
    ruta = relativa.lower()
    nombre = ruta.rsplit("/", 1)[-1]
    return (
        nombre in PROHIBIDOS_NOMBRE
        or any(fragmento in ruta for fragmento in PROHIBIDOS_RUTA)
        or ruta.endswith(PROHIBIDOS_SUFIJO)
    )

log = logger("publicar")


def ejecutar(orden: list[str], *, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(orden, cwd=cwd, capture_output=True, text=True)


def puerta_auditoria() -> None:
    """La auditoria de fugas y la frescura de las cifras, antes de nada."""
    for descripcion, orden in (
        ("auditoria de lo publicable", [sys.executable, "scripts/auditar_powerbi.py"]),
        (
            "cifras del dashboard al dia",
            [sys.executable, "scripts/generar_cifras_web.py", "--comprobar"],
        ),
    ):
        resultado = ejecutar(orden, cwd=RAIZ)
        if resultado.returncode != 0:
            log.error(
                "%s: FALLO. No se publica.\n%s",
                descripcion,
                (resultado.stdout + resultado.stderr).strip()[-2000:],
            )
            raise SystemExit(1)
        log.info("%s: superada", descripcion)


def payload() -> list[str]:
    """Rutas relativas que se van a publicar, ya vetadas por la auditoria."""
    rutas = [
        str(p.relative_to(RAIZ)).replace("\\", "/")
        for p in ficheros_que_git_publicara(RAIZ)
        if p.is_file()
    ]

    delatados = [r for r in rutas if esta_prohibido(r)]
    if delatados:
        log.error(
            "HAY %d FICHEROS QUE NO PUEDEN PUBLICARSE EN EL PAYLOAD. No se publica.\n%s",
            len(delatados),
            "\n".join(f"  {r}" for r in delatados),
        )
        raise SystemExit(1)

    if not rutas:
        log.error("el payload esta vacio: algo va mal, no se publica")
        raise SystemExit(1)
    return sorted(rutas)


def construir(destino: Path, rutas: list[str]) -> None:
    for relativa in rutas:
        origen = RAIZ / relativa
        copia = destino / relativa
        copia.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(origen, copia)

    for orden in (
        ["git", "init", "-q", "-b", "main"],
        ["git", "add", "-A"],
        [
            "git", "commit", "-q", "-m",
            "Analitica de resultados sobre un extracto de costes SAP CO\n\n"
            "Pipeline Excel -> PostgreSQL -> Power BI -> web, con las cifras\n"
            "reconciliadas contra el P&L oficial y los datos anonimizados.\n\n"
            "Se publica sin historial a proposito: los commits del repositorio\n"
            "de trabajo contienen valores reales que la auditoria encontro\n"
            "despues, y `git log -S` los recupera aunque el arbol este limpio.",
        ],
    ):
        resultado = ejecutar(orden, cwd=destino)
        if resultado.returncode != 0:
            log.error("fallo %s: %s", " ".join(orden[:2]), resultado.stderr.strip())
            raise SystemExit(1)


def rehacer(destino: Path, nombre: str) -> None:
    """Sustituye el contenido de un repositorio ya publicado, con un solo commit.

    Un `git push` normal dejaria dos commits, y el primero seguiria conteniendo
    lo que se quiso retirar: `git log -S` lo recuperaria igual que en el
    repositorio de trabajo, que es justo lo que esta publicacion evita. Se
    fuerza, de modo que el remoto vuelve a tener exactamente un commit.
    """
    usuario = ejecutar(["gh", "api", "user", "--jq", ".login"], cwd=destino).stdout.strip()
    remoto = f"https://github.com/{usuario}/{nombre}.git"
    for orden in (
        ["git", "remote", "add", "origin", remoto],
        ["git", "push", "--force", "-u", "origin", "main"],
    ):
        resultado = ejecutar(orden, cwd=destino)
        if resultado.returncode != 0:
            log.error("fallo al rehacer el remoto: %s", resultado.stderr.strip())
            raise SystemExit(1)
    log.info("repositorio rehecho con un unico commit: %s", remoto.removesuffix(".git"))


def subir(destino: Path, nombre: str, *, forzar: bool) -> None:
    autenticado = ejecutar(["gh", "auth", "status"], cwd=destino)
    if autenticado.returncode != 0:
        log.error(
            "gh no esta autenticado. Ejecutar primero:\n  gh auth login\n%s",
            (autenticado.stdout + autenticado.stderr).strip(),
        )
        raise SystemExit(1)

    usuario = ejecutar(["gh", "api", "user", "--jq", ".login"], cwd=destino).stdout.strip()
    existe = ejecutar(["gh", "repo", "view", f"{usuario}/{nombre}"], cwd=destino).returncode == 0
    if existe:
        if not forzar:
            log.error(
                "%s/%s ya existe. Para sustituir su contenido por el arbol actual, "
                "repetir con --forzar: el remoto se reescribe entero y vuelve a "
                "quedarse con un unico commit.",
                usuario,
                nombre,
            )
            raise SystemExit(1)
        rehacer(destino, nombre)
        return

    creado = ejecutar(
        [
            "gh", "repo", "create", nombre, "--public", "--source", ".",
            "--remote", "origin", "--push",
            "--description",
            "Pipeline analitico sobre un extracto de costes SAP CO: "
            "Excel -> PostgreSQL -> Power BI -> web, reconciliado y anonimizado.",
        ],
        cwd=destino,
    )
    if creado.returncode != 0:
        log.error("no se pudo crear el repositorio:\n%s", (creado.stdout + creado.stderr).strip())
        raise SystemExit(1)
    log.info("repositorio creado y subido: %s", creado.stdout.strip() or nombre)

    usuario = ejecutar(["gh", "api", "user", "--jq", ".login"], cwd=destino).stdout.strip()
    paginas = ejecutar(
        [
            "gh", "api", "-X", "POST", f"repos/{usuario}/{nombre}/pages",
            "-f", "source[branch]=main", "-f", "source[path]=/docs",
        ],
        cwd=destino,
    )
    if paginas.returncode != 0:
        log.warning(
            "el repositorio se subio pero no se pudo activar GitHub Pages. "
            "Se activa a mano en Settings > Pages (rama main, carpeta /docs).\n%s",
            (paginas.stdout + paginas.stderr).strip(),
        )
    else:
        log.info("GitHub Pages activado: https://%s.github.io/%s/", usuario, nombre)


def main(argv: list[str] | None = None) -> int:
    configurar()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nombre", required=True, help="nombre del repositorio en GitHub")
    parser.add_argument(
        "--publicar",
        action="store_true",
        help="crea el repositorio y sube. Sin esto solo se prepara la copia",
    )
    parser.add_argument(
        "--forzar",
        action="store_true",
        help="si el repositorio ya existe, reescribe su contenido con un solo commit",
    )
    args = parser.parse_args(argv)

    puerta_auditoria()
    rutas = payload()
    log.info("payload: %d ficheros, ninguno en la lista de prohibidos", len(rutas))

    destino = Path(tempfile.mkdtemp(prefix="publicar-"))
    construir(destino, rutas)
    log.info("copia preparada en %s con un unico commit", destino)

    if not args.publicar:
        log.info(
            "ensayo terminado: no se ha creado nada en GitHub. Repetir con "
            "--publicar cuando la copia este revisada."
        )
        return 0

    subir(destino, args.nombre, forzar=args.forzar)
    return 0


if __name__ == "__main__":
    sys.exit(main())

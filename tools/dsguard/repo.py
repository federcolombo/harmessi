"""Alcance de Git: baseline, archivos sucios, `git diff --check`, match de rutas.

Lista blanca dura de subcomandos: `rev-parse`, `status`, `diff`, `show`, `log`,
`ls-files`, `mv` (habilitado en Sesión B para `archive`, único uso: mover el
directorio completo de un cambio de `changes/` a `archive/`). Cualquier otro
(en particular `commit`, `add`, `reset`, `checkout`) levanta `AssertionError`.
Nunca se commitea nada desde este módulo.
"""
from __future__ import annotations

import fnmatch
import subprocess
from pathlib import Path

COMANDOS_PERMITIDOS = {"rev-parse", "status", "diff", "show", "log", "ls-files", "mv"}


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    if not args or args[0] not in COMANDOS_PERMITIDOS:
        primero = args[0] if args else "(vacío)"
        raise AssertionError(f"Subcomando git no permitido: {primero!r}")
    try:
        return subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError as e:
        raise RuntimeError(f"git no disponible: {e}") from e


def find_repo_root(desde: Path) -> Path:
    """Raíz del repo Git que contiene `desde`. Levanta RuntimeError si `desde`
    no está dentro de un repo Git válido."""
    resultado = _git(desde, "rev-parse", "--show-toplevel")
    if resultado.returncode != 0:
        raise RuntimeError(
            f"No es un repositorio git válido en {desde}: {resultado.stderr.strip()}"
        )
    return Path(resultado.stdout.strip())


def get_head(repo_root: Path) -> tuple:
    """(commit, rama) del HEAD actual."""
    commit = _git(repo_root, "rev-parse", "HEAD").stdout.strip()
    rama = _git(repo_root, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    return commit, rama


def list_dirty_files(repo_root: Path) -> list:
    """Archivos nuevos/modificados/staged, vía
    `git status --porcelain=v1 --untracked-files=all -z`.

    El formato `-z` separa entradas por `\\0` sin escapar rutas. Para
    renombres/copias (`R`/`C`), la entrada trae dos campos consecutivos: la
    ruta NUEVA primero (la que se reporta) y la ruta VIEJA después (se
    descarta).

    `--untracked-files=all` es obligatorio: sin él, Git colapsa un directorio
    enteramente nuevo/untracked en una sola línea (`?? tools/`) en vez de
    listar cada archivo de adentro. Como `rutas_autorizadas` usa rutas EXACTAS
    (no globs), esa línea colapsada (`"tools/"`) no matchea contra ninguna
    ruta exacta (`"tools/ds_guard.py"`, etc.), y `files_out_of_scope` marca
    como fuera de alcance un directorio entero recién creado aunque cada
    archivo de adentro esté autorizado.
    """
    resultado = _git(
        repo_root, "status", "--porcelain=v1", "--untracked-files=all", "-z"
    )
    salida = resultado.stdout
    if not salida:
        return []
    partes = salida.split("\0")
    if partes and partes[-1] == "":
        partes = partes[:-1]
    archivos = []
    i = 0
    while i < len(partes):
        entrada = partes[i]
        codigo = entrada[:2]
        ruta = entrada[3:]
        if codigo and codigo[0] in ("R", "C"):
            # El campo siguiente es la ruta VIEJA (git la reporta primero la
            # nueva, después la vieja) — se saltea, no se usa para nada.
            i += 1
        archivos.append(ruta)
        i += 1
    return archivos


def is_tree_clean(repo_root: Path) -> bool:
    return len(list_dirty_files(repo_root)) == 0


def diff_check(repo_root: Path) -> list:
    """Cada línea no vacía de `git diff --check` es un hallazgo de whitespace o
    marca de conflicto sin resolver (`ALCANCE-WHITESPACE`)."""
    resultado = _git(repo_root, "diff", "--check")
    hallazgos = []
    for linea in resultado.stdout.splitlines():
        if linea.strip():
            hallazgos.append(linea)
    return hallazgos


def path_matches_any(path: str, patrones: list) -> bool:
    """`path` normalizado a partes relativas con separador `/` (nunca rutas
    absolutas ni backslashes), comparado con cada patrón vía `fnmatch.fnmatch`.

    `fnmatch` trata `*` como "cualquier carácter" (no se detiene en `/`), así
    que sirve igual para patrones exactos (`tools/dsguard/core.py`) que para
    patrones con comodines (`tools/**`).
    """
    normalizado = Path(path).as_posix()
    for patron in patrones:
        if fnmatch.fnmatchcase(normalizado, patron):
            return True
    return False


def files_out_of_scope(repo_root: Path, rutas_autorizadas: list) -> list:
    """Archivos sucios (`list_dirty_files`) que no matchean ningún patrón de
    `rutas_autorizadas`."""
    sucios = list_dirty_files(repo_root)
    return [r for r in sucios if not path_matches_any(r, rutas_autorizadas)]

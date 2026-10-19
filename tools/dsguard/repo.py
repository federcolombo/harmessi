"""Alcance de Git: baseline, archivos sucios, `git diff --check`, match de rutas.

Lista blanca dura de subcomandos: `rev-parse`, `status`, `diff`, `show`, `log`,
`ls-files`, `mv` (habilitado en Sesión B para `archive`, único uso: mover el
directorio completo de un cambio de `changes/` a `archive/`). Cualquier otro
(en particular `commit`, `add`, `reset`, `checkout`) levanta `AssertionError`.
Nunca se commitea nada desde este módulo.
"""
from __future__ import annotations

import fnmatch
import re
import subprocess
from typing import Optional
from pathlib import Path

COMANDOS_PERMITIDOS = {"rev-parse", "status", "diff", "show", "log", "ls-files", "mv"}


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    if not args or args[0] not in COMANDOS_PERMITIDOS:
        primero = args[0] if args else "(vacío)"
        raise AssertionError(f"Subcomando git no permitido: {primero!r}")
    try:
        # Se captura en bytes y se decodifica a mano: `text=True` aplicaría universal
        # newlines y alteraría un `\r` dentro de un nombre de archivo POSIX.
        crudo = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
        )
    except OSError as e:  # FileNotFoundError, PermissionError, etc.: git no ejecutable
        raise RuntimeError(f"git no disponible: {e}") from e
    return subprocess.CompletedProcess(
        crudo.args,
        crudo.returncode,
        (crudo.stdout or b"").decode("utf-8", errors="replace"),
        (crudo.stderr or b"").decode("utf-8", errors="replace"),
    )


def validar_ref(ref) -> str:
    """Rechaza una ref vacía o que empiece con `-` (se confundiría con una opción
    de git). Devuelve la ref sin cambios; si no es válida lanza `GitCommandError`."""
    if not isinstance(ref, str) or not ref.strip() or ref.startswith("-"):
        raise GitCommandError(f"Ref de git inválida: {ref!r}")
    return ref


def _verificar(resultado: subprocess.CompletedProcess, descripcion: str) -> subprocess.CompletedProcess:
    """Chequeo único de returncode (D1): returncode != 0 -> `GitCommandError`."""
    if resultado.returncode != 0:
        raise GitCommandError(
            f"{descripcion} falló (código {resultado.returncode}): {resultado.stderr.strip()}"
        )
    return resultado


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
    commit = _verificar(_git(repo_root, "rev-parse", "HEAD"), "git rev-parse HEAD").stdout.strip()
    rama = _verificar(
        _git(repo_root, "rev-parse", "--abbrev-ref", "HEAD"), "git rev-parse --abbrev-ref HEAD"
    ).stdout.strip()
    return commit, rama


def list_dirty_files(repo_root: Path) -> list:
    """Archivos nuevos/modificados/staged, vía
    `git status --porcelain=v1 --untracked-files=all -z`.

    El formato `-z` separa entradas por `\\0` sin escapar rutas. Para
    renombres/copias (`R`/`C`), la entrada trae dos campos consecutivos: la
    ruta NUEVA primero (la que se reporta) y la ruta VIEJA después (se
    devuelve también).

    Rename (`R`): se devuelven AMBAS rutas (nueva y vieja), porque el origen
    también se modifica (desaparece). Copy (`C`): solo el destino (el origen no
    cambia). `git status --porcelain=v1 -z` entrega primero la nueva y luego la
    vieja. returncode != 0 -> `GitCommandError` (nunca `[]` por un fallo).

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
    _verificar(resultado, "git status")
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
        if len(entrada) < 4:
            raise GitOutputError(f"Entrada malformada en la salida de git status -z: {entrada!r}")
        codigo = entrada[:2]
        ruta = entrada[3:]
        if "R" in codigo or "C" in codigo:
            # R/C pueden venir en la columna X o en la Y. El campo siguiente es la ruta
            # VIEJA (git reporta primero la nueva). Rename: se evalúan ambas; copy: solo el destino.
            if i + 1 >= len(partes):
                raise GitOutputError("Registro R/C truncado en la salida de git status -z")
            if "R" in codigo:
                archivos.append(partes[i + 1])
            i += 1
        archivos.append(ruta)
        i += 1
    return archivos


class GitOutputError(ValueError):
    """Salida de Git ilegible, malformada o comando fallido (nunca se adivina)."""


class GitCommandError(GitOutputError):
    """El comando git terminó con returncode != 0 (distinto de salida ilegible,
    que es `GitOutputError` puro)."""


_ESTADO_VALIDO = re.compile(r"[AMDTUXB]|[RC]\d{1,3}")


def parse_name_status_z(salida: str) -> list:
    """Parsea la salida de `git diff --name-status -z -M`. Función PURA.

    Campos separados por `\\0`. Registros `X\\0ruta\\0` para estados de una
    letra (A, M, D, T, U, X, B) y `R<nn>\\0vieja\\0nueva\\0` /
    `C<nn>\\0origen\\0destino\\0` (tres campos). Devuelve una lista de tuplas
    `(codigo, ruta_nueva, ruta_vieja_o_None)`; `codigo` es el campo de estado
    tal cual (`"R100"`, `"M"`). Para R/C, `ruta_nueva` es el destino y
    `ruta_vieja` el origen; para el resto `ruta_vieja` es None.

    Salida vacía -> `[]`. Se tolera el `\\0` final. Estado vacío o desconocido,
    registro truncado o ruta vacía -> `GitOutputError`; nunca se devuelven
    resultados parciales. No se usa `splitlines` ni `split("\\t")` ni se
    interpretan escapes octales (las rutas pueden contener `\\t` o `\\n`).

    Contrato de encoding: la salida `-z` de Git es UTF-8 también en Windows.
    `_git` decodifica `utf-8` con `errors="replace"`: un byte inválido produce
    U+FFFD y la ruta no coincidirá con ningún alcance (falla cerrado). No hay
    normalización Unicode NFC/NFD. No depende de `core.quotepath`.

    El estado se valida completo: `[AMDTUXB]` o `[RC]` seguido de 1 a 3
    dígitos (p. ej. `R100`, `C75`).

    `_git` captura bytes (sin universal newlines): `\\r`, `\\t` y `\\n` dentro
    de un nombre de archivo se preservan.
    """
    if not salida:
        return []
    campos = salida.split("\0")
    if campos[-1] == "":
        campos = campos[:-1]
    registros = []
    i = 0
    while i < len(campos):
        codigo = campos[i]
        if not codigo:
            raise GitOutputError(f"Estado vacío en la posición {i} de la salida -z")
        if not _ESTADO_VALIDO.fullmatch(codigo):
            raise GitOutputError(f"Estado desconocido en la salida -z: {codigo!r}")
        cantidad = 2 if codigo[0] in ("R", "C") else 1
        rutas = campos[i + 1:i + 1 + cantidad]
        if len(rutas) < cantidad:
            raise GitOutputError(
                f"Registro truncado para el estado {codigo!r}: "
                f"se esperaban {cantidad} ruta(s) y hay {len(rutas)}"
            )
        if any(r == "" for r in rutas):
            raise GitOutputError(f"Ruta vacía en el registro con estado {codigo!r}")
        if cantidad == 2:
            registros.append((codigo, rutas[1], rutas[0]))
        else:
            registros.append((codigo, rutas[0], None))
        i += 1 + cantidad
    return registros


def diff_name_status(repo_root: Path, *args: str) -> list:
    """Ejecuta `git diff --name-status -z -M <args>` y devuelve
    `parse_name_status_z(stdout)`. returncode != 0 -> `GitOutputError` con el
    stderr: se lanza `GitCommandError` (subclase de `GitOutputError`); la salida
    malformada lanza `GitOutputError` puro, así el consumidor distingue ambos.

    Contrato de encoding: la salida `-z` es UTF-8 también en Windows; `_git`
    decodifica `utf-8` con `errors="replace"` (un byte inválido produce U+FFFD
    y la ruta no coincidirá con ningún alcance: falla cerrado). Sin
    normalización Unicode NFC/NFD. NO depende de `core.quotepath`.

    `_git` captura bytes (sin universal newlines): `\\r`, `\\t` y `\\n` en un
    nombre de archivo se preservan. Refs: validadas con `validar_ref` y
    seguidas de `--`.
    """
    # Las refs (todo lo que no sea `--`) se validan: nada que empiece con `-`; y se
    # agrega `--` final para separar refs de rutas.
    for a in args:
        if a not in ("--", "--staged", "--cached"):
            validar_ref(a)
    resultado = _git(repo_root, "diff", "--name-status", "-z", "-M", *args, *(() if "--" in args else ("--",)))
    if resultado.returncode != 0:
        raise GitCommandError(
            f"git diff --name-status falló (código {resultado.returncode}): "
            f"{resultado.stderr.strip()}"
        )
    return parse_name_status_z(resultado.stdout)


def leer_en_commit(repo_root: Path, commit, ruta: str) -> Optional[bytes]:
    """Contenido (UTF-8) del blob `ruta` en `commit` (`git show <commit>:<ruta>`, subcomando de la
    lista blanca) o `None` ante cualquier fallo (ref inválida, ruta ausente, Git ilegible). Nunca
    lanza. Un byte no UTF-8 se reemplaza (U+FFFD) al decodificar `_git`: el hash resultante no
    coincidirá con ninguna aprobación (fail-closed). Solo lectura."""
    try:
        validar_ref(commit)
        if not isinstance(ruta, str) or not ruta or ruta.startswith("-"):
            return None
        resultado = _git(repo_root, "show", f"{commit}:{ruta}")
    except (GitCommandError, RuntimeError, OSError, ValueError):
        return None
    if resultado.returncode != 0:
        return None
    return resultado.stdout.encode("utf-8")


def existe_en_commit(repo_root: Path, commit, ruta: str) -> bool:
    """True si el blob `ruta` existe en el árbol de `commit`. Fail-closed (nunca lanza)."""
    return leer_en_commit(repo_root, commit, ruta) is not None


def is_tree_clean(repo_root: Path) -> bool:
    return len(list_dirty_files(repo_root)) == 0


def diff_check(repo_root: Path) -> list:
    """Cada línea no vacía de `git diff --check` es un hallazgo de whitespace o
    marca de conflicto sin resolver (`ALCANCE-WHITESPACE`)."""
    resultado = _git(repo_root, "diff", "--check")
    # `git diff --check` sale con código != 0 (2) cuando HAY hallazgos de whitespace:
    # eso es salida legítima. Es un fallo si el código es >= 128 o si falla sin salida.
    if resultado.returncode >= 128 or (
        resultado.returncode != 0 and not resultado.stdout.strip()
    ):
        raise GitCommandError(
            f"git diff --check falló (código {resultado.returncode}): {resultado.stderr.strip()}"
        )
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

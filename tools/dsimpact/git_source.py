"""Fuente del cambio (Git) para Impact Preflight (R1, v0.4 Change 1).

Reusa `dsguard.repo._git` DIRECTAMENTE -- ningún wrapper de subprocess nuevo
(mismo patrón de dependencia unidireccional que `ds_profile -> dsguard`, ver
`design.md` §1). Este módulo nunca muta el repo: solo `diff`/`show`/
`rev-parse`/`ls-files`, todos de solo lectura.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dsguard import repo as repo_mod


class GitSourceError(Exception):
    """Ref inválida u otro error de uso de Git. El llamador la traduce a un
    mensaje claro + exit code apropiado, nunca deja escapar un traceback
    crudo."""


STATUS_ADDED = "added"
STATUS_MODIFIED = "modified"
STATUS_DELETED = "deleted"
STATUS_RENAMED = "renamed"


@dataclass(frozen=True)
class ArchivoCambiado:
    path: str
    status: str
    old_path: Optional[str] = None


def validar_ref(repo_root: Path, ref: str) -> bool:
    """`git rev-parse --verify <ref>` -- mismo patrón que
    `dsguard.notebooks.obtener_revision`."""
    try:
        r = repo_mod._git(repo_root, "rev-parse", "--verify", ref)
    except RuntimeError as exc:
        raise GitSourceError("git no disponible al validar la referencia") from exc
    return r.returncode == 0


def listar_cambios(repo_root: Path, since: Optional[str], staged: bool) -> list:
    """Exactamente uno de `since`/`staged` debe estar activo (validado por el
    llamador de más arriba, `scan.py`/`cli.py`). `git diff --name-status -M
    [--staged] [since]`. Parsea A/M/D/Rxxx/Cxxx/T -- T se trata como M; C se
    trata como archivo nuevo en `new_path`, sin rastrear origen (límite
    documentado en `design.md` §8)."""
    # `diff_name_status` usa `-z` (rutas sin escapar, inmune a `core.quotepath`) y ya incluye `-M`.
    args = ["--staged"] if staged else [since]
    try:
        entradas = repo_mod.diff_name_status(repo_root, *args)
    except repo_mod.GitCommandError as exc:
        raise GitSourceError(str(exc)) from exc  # mensaje ya trae el stderr de git
    except repo_mod.GitOutputError as exc:
        raise GitSourceError(f"git diff falló: {exc}") from exc
    except RuntimeError as exc:  # git no disponible (`dsguard.repo._git`)
        raise GitSourceError("git no disponible al listar cambios") from exc
    resultado = []
    for codigo, nueva, vieja in entradas:
        if codigo.startswith("R"):
            resultado.append(ArchivoCambiado(nueva, STATUS_RENAMED, old_path=vieja))
        elif codigo.startswith("C"):
            resultado.append(ArchivoCambiado(nueva, STATUS_ADDED))
        elif codigo == "A":
            resultado.append(ArchivoCambiado(nueva, STATUS_ADDED))
        elif codigo == "D":
            resultado.append(ArchivoCambiado(nueva, STATUS_DELETED))
        else:  # M, T, u otros -- tratados como modified
            resultado.append(ArchivoCambiado(nueva, STATUS_MODIFIED))
    return resultado


def _sanear(texto: str, repo_root: Path) -> str:
    """Reemplaza la ruta absoluta del repo (en ambas formas de separador) por `<repo>`."""
    saneado = texto
    raiz = str(repo_root)
    for variante in {raiz, raiz.replace("\\", "/"), str(Path(repo_root).resolve()),
                     str(Path(repo_root).resolve()).replace("\\", "/")}:
        if variante:
            saneado = saneado.replace(variante, "<repo>")
    return saneado.strip()


def _git_show(repo_root: Path, objeto: str, descripcion: str) -> str:
    """`git show <objeto>`; fail-closed: git no disponible o `returncode != 0`
    lanzan `GitSourceError` (mensaje sin rutas absolutas)."""
    try:
        r = repo_mod._git(repo_root, "show", objeto)
    except RuntimeError as exc:
        raise GitSourceError(f"git no disponible al leer {descripcion}") from exc
    if r.returncode != 0:
        raise GitSourceError(
            f"no se pudo leer {descripcion} (git show devolvió {r.returncode}): {_sanear(r.stderr, repo_root)}"
        )
    return r.stdout


def contenido_before(
    repo_root: Path, since: Optional[str], staged: bool, path: str, *, status: str
) -> Optional[str]:
    """Contenido «antes» del archivo. `None` SOLO si la ausencia es esperada
    (`status == added`). Para `renamed` el llamador pasa `old_path` en `path`.
    Cualquier otro fallo de lectura lanza `GitSourceError` (unknown != empty)."""
    if status == STATUS_ADDED:
        return None
    ref = "HEAD" if staged else since
    return _git_show(repo_root, f"{ref}:{path}", f"el contenido previo de {path!r}")


def contenido_after(repo_root: Path, staged: bool, path: str, *, status: str) -> Optional[str]:
    """`--staged`: contenido del índice (`git show :path`, stage 0). `--since`:
    contenido real del working tree (lectura de filesystem). `None` SOLO si la
    ausencia es esperada (`status == deleted`); si no, error de lectura =>
    `GitSourceError`."""
    if status == STATUS_DELETED:
        return None
    if staged:
        return _git_show(repo_root, f":{path}", f"el contenido indexado de {path!r}")
    ruta_abs = repo_root / path
    try:
        return ruta_abs.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise GitSourceError(
            f"no se pudo leer {path!r} del working tree ({type(exc).__name__})"
        ) from exc


def listar_consumidores_candidatos(repo_root: Path) -> list:
    """Universo de búsqueda: tracked + untracked-no-ignorados (`.gitignore`
    respetado automáticamente, sin mantener una lista de exclusiones propia --
    ver `spec.md` R1), filtrado por extensión. El contenido de estos archivos
    siempre se lee desde el FILESYSTEM (nunca desde `git show`), sin importar
    el modo since/staged -- son "qué existe ahora en el checkout", no parte
    del diff en sí (ver `design.md`)."""
    try:
        r = repo_mod._git(repo_root, "ls-files", "-z", "--cached", "--others", "--exclude-standard")
    except RuntimeError as exc:
        raise GitSourceError("git no disponible al listar archivos") from exc
    if r.returncode != 0:
        raise GitSourceError(f"git ls-files falló: {r.stderr.strip()}")
    extensiones = (".py", ".ipynb", ".json", ".yaml", ".yml", ".toml", ".md")
    rutas = [p for p in r.stdout.split("\0") if p]
    return sorted(p for p in rutas if p.lower().endswith(extensiones))

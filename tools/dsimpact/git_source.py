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
    r = repo_mod._git(repo_root, "rev-parse", "--verify", ref)
    return r.returncode == 0


def listar_cambios(repo_root: Path, since: Optional[str], staged: bool) -> list:
    """Exactamente uno de `since`/`staged` debe estar activo (validado por el
    llamador de más arriba, `scan.py`/`cli.py`). `git diff --name-status -M
    [--staged] [since]`. Parsea A/M/D/Rxxx/Cxxx/T -- T se trata como M; C se
    trata como archivo nuevo en `new_path`, sin rastrear origen (límite
    documentado en `design.md` §8)."""
    args = ["diff", "--name-status", "-M"]
    if staged:
        args.append("--staged")
    else:
        args.append(since)
    r = repo_mod._git(repo_root, *args)
    if r.returncode != 0:
        raise GitSourceError(f"git diff falló: {r.stderr.strip()}")
    resultado = []
    for linea in r.stdout.split("\n"):
        if not linea.strip():
            continue
        campos = linea.split("\t")
        codigo = campos[0]
        if codigo.startswith("R"):
            resultado.append(ArchivoCambiado(campos[2], STATUS_RENAMED, old_path=campos[1]))
        elif codigo.startswith("C"):
            resultado.append(ArchivoCambiado(campos[2], STATUS_ADDED))
        elif codigo == "A":
            resultado.append(ArchivoCambiado(campos[1], STATUS_ADDED))
        elif codigo == "D":
            resultado.append(ArchivoCambiado(campos[1], STATUS_DELETED))
        else:  # M, T, u otros -- tratados como modified
            resultado.append(ArchivoCambiado(campos[1], STATUS_MODIFIED))
    return resultado


def contenido_before(repo_root: Path, since: Optional[str], staged: bool, path: str) -> Optional[str]:
    """`None` si el archivo no existía en ese lado (archivo agregado)."""
    ref = "HEAD" if staged else since
    r = repo_mod._git(repo_root, "show", f"{ref}:{path}")
    return r.stdout if r.returncode == 0 else None


def contenido_after(repo_root: Path, staged: bool, path: str) -> Optional[str]:
    """`--staged`: contenido del índice (`git show :path`, stage 0). `--since`:
    contenido real del working tree (lectura de filesystem). `None` si el
    archivo no existe en ese lado (eliminado)."""
    if staged:
        r = repo_mod._git(repo_root, "show", f":{path}")
        return r.stdout if r.returncode == 0 else None
    ruta_abs = repo_root / path
    if not ruta_abs.exists():
        return None
    return ruta_abs.read_text(encoding="utf-8", errors="replace")


def listar_consumidores_candidatos(repo_root: Path) -> list:
    """Universo de búsqueda: tracked + untracked-no-ignorados (`.gitignore`
    respetado automáticamente, sin mantener una lista de exclusiones propia --
    ver `spec.md` R1), filtrado por extensión. El contenido de estos archivos
    siempre se lee desde el FILESYSTEM (nunca desde `git show`), sin importar
    el modo since/staged -- son "qué existe ahora en el checkout", no parte
    del diff en sí (ver `design.md`)."""
    r = repo_mod._git(repo_root, "ls-files", "-z", "--cached", "--others", "--exclude-standard")
    if r.returncode != 0:
        raise GitSourceError(f"git ls-files falló: {r.stderr.strip()}")
    extensiones = (".py", ".ipynb", ".json", ".yaml", ".yml", ".toml", ".md")
    rutas = [p for p in r.stdout.split("\0") if p]
    return sorted(p for p in rutas if p.lower().endswith(extensiones))

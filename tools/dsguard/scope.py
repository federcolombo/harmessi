"""Alcance de un Change SDD: compara lo declarado (`control["alcance"]["rutas_autorizadas"]`) contra
lo realmente tocado -- working tree actual MÁS el diff completo desde `control["baseline"]["commit"]`
(Change 2 v0.4: 20260916-scope-and-change-isolation). Antes de este change, el chequeo (`ALCANCE-RUTA`,
duplicado en `sdd.gate_cierre`/`ds_guard.cmd_validate`) solo veía el working tree -- un archivo tocado
fuera de scope y ya commiteado quedaba invisible en cuanto el working tree volvía a estar limpio. Este
módulo consolida esa lógica en un solo lugar.

Reusa `repo._git` directamente (mismo patrón ya usado por `tools/dsimpact/git_source.py` en Change 1)
-- NUNCA importa `tools.dsimpact` desde acá: `dsguard` es core (discovery, siempre instalado),
`dsimpact` es opcional (`stage_minimo="experiment"`), invertir esa dependencia rompería cualquier
instalación en discovery (ver `design.md` §2 del change).
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from . import repo as repo_mod
from .core import Finding


def archivos_tocados_desde_baseline(repo_root: Path, baseline_commit: Optional[str]) -> list:
    """`git diff --name-status -M <baseline_commit>` contra el working tree actual (incluye commits
    ya hechos desde baseline Y cambios sin confirmar en una sola diff -- misma semántica que
    `git diff <ref>` nativo, mismo patrón de parseo que `tools/dsimpact/git_source.py`). Devuelve
    rutas relativas POSIX (lado nuevo para renombres/copias). Degradación SILENCIOSA (devuelve []):
    si `baseline_commit` es None/vacío, o si el comando falla por cualquier motivo (ref inválida,
    rebase que la borró, etc.) -- ver design.md §3, decisión deliberada de fail-open acá, distinta
    del criterio fail-closed de `pathguard`/`scientific_validity`. NUNCA lanza."""
    if not baseline_commit:
        return []
    try:
        r = repo_mod._git(repo_root, "diff", "--name-status", "-M", baseline_commit)
    except Exception:  # noqa: BLE001 - degradación silenciosa, nunca rompe validate/cierre
        return []
    if r.returncode != 0:
        return []
    rutas = []
    for linea in r.stdout.split("\n"):
        if not linea.strip():
            continue
        campos = linea.split("\t")
        codigo = campos[0]
        if codigo.startswith("R") or codigo.startswith("C"):
            rutas.append(campos[2])
        else:
            rutas.append(campos[1])
    return rutas


def evaluar_alcance(repo_root: Path, control: dict) -> list:
    """[Finding("ALCANCE-RUTA", ...), ...] -- código único, mismo código que ya usaban
    `cmd_validate`/`gate_cierre` antes de este change (no se inventa un código nuevo). Unión
    deduplicada de `repo.list_dirty_files` (working tree) + `archivos_tocados_desde_baseline`
    (historial desde baseline), comparada contra `rutas_autorizadas` vía `repo.path_matches_any`
    (reusada tal cual, sin reimplementar matching)."""
    repo_root = Path(repo_root)
    rutas_autorizadas = control.get("alcance", {}).get("rutas_autorizadas", [])
    baseline_commit = control.get("baseline", {}).get("commit")

    tocados = set(repo_mod.list_dirty_files(repo_root))
    tocados |= set(archivos_tocados_desde_baseline(repo_root, baseline_commit))

    fuera_de_alcance = sorted(r for r in tocados if not repo_mod.path_matches_any(r, rutas_autorizadas))
    return [Finding("ALCANCE-RUTA", f"Archivo fuera de alcance: {r}", r) for r in fuera_de_alcance]

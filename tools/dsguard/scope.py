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


class GitIlegibleError(ValueError):
    """La salida de git fue recibida (returncode 0) pero está malformada: NO equivale a «sin
    archivos tocados». `evaluar_alcance` la traduce a `ALCANCE-GIT-ILEGIBLE` (fail-closed)."""


def archivos_tocados_desde_baseline(repo_root: Path, baseline_commit: Optional[str]) -> list:
    """`git diff --name-status -z -M <baseline_commit>` contra el working tree actual (incluye
    commits ya hechos desde baseline Y cambios sin confirmar en una sola diff -- misma semántica
    que `git diff <ref>` nativo). Devuelve rutas relativas POSIX (lado nuevo para renombres/copias),
    parseadas con `repo.parse_name_status_z` (inmune a `core.quotepath`). Degradación SILENCIOSA
    (devuelve []) SOLO si `baseline_commit` es None/vacío, o si el comando falla (ref inválida,
    rebase que la borró, etc.) -- ver design.md §3, decisión deliberada de fail-open. Si git
    responde OK pero la salida es malformada, lanza `GitIlegibleError` (no es «sin archivos»)."""
    if not baseline_commit:
        return []
    try:
        entradas = repo_mod.diff_name_status(repo_root, baseline_commit)
    except repo_mod.GitCommandError:
        # git terminó con returncode != 0 (ref inválida, etc.): fail-open documentado.
        return []
    except repo_mod.GitOutputError as exc:
        # git respondió OK pero la salida es ilegible: fail-closed (no es «sin archivos»).
        raise GitIlegibleError(str(exc)) from exc
    except Exception:  # noqa: BLE001 - fallo de ejecución (RuntimeError/AssertionError/OSError):
        # degradación silenciosa EXISTENTE, no se amplía; nunca rompe validate/cierre.
        return []
    return [Path(nueva).as_posix() for _codigo, nueva, _vieja in entradas]


_PREFIJO_EXECUTIONS = ".harmessi/executions/"
_RUTA_LEDGER = "openspec/decisions/ledger.jsonl"


def es_output_intrinseco(ruta: str) -> bool:
    """True SOLO para outputs de bookkeeping del harness: `.harmessi/executions/**`
    y la ruta exacta `openspec/decisions/ledger.jsonl` (R38). Lista cerrada; no
    autoriza nada para `exec` (R39), solo los excluye del evaluador de alcance."""
    normalizada = str(ruta).replace("\\", "/")
    while normalizada.startswith("./"):
        normalizada = normalizada[2:]
    return normalizada.startswith(_PREFIJO_EXECUTIONS) or normalizada == _RUTA_LEDGER


def evaluar_alcance(repo_root: Path, control: dict) -> list:
    """[Finding("ALCANCE-RUTA", ...), ...] -- mismo código que ya usaban `cmd_validate`/`gate_cierre`;
    además emite `Finding("ALCANCE-GIT-ILEGIBLE")` (fail-closed) si la salida de git del diff desde
    baseline es ilegible (los hallazgos ALCANCE-RUTA del resto se siguen emitiendo). Unión
    deduplicada de `repo.list_dirty_files` (working tree) + `archivos_tocados_desde_baseline`
    (historial desde baseline), comparada contra `rutas_autorizadas` vía `repo.path_matches_any`
    (reusada tal cual, sin reimplementar matching)."""
    repo_root = Path(repo_root)
    rutas_autorizadas = control.get("alcance", {}).get("rutas_autorizadas", [])
    baseline_commit = control.get("baseline", {}).get("commit")

    tocados = set(repo_mod.list_dirty_files(repo_root))
    findings = []
    try:
        tocados |= set(archivos_tocados_desde_baseline(repo_root, baseline_commit))
    except GitIlegibleError as exc:
        # Fail-closed: no se puede afirmar que el historial desde baseline respete el alcance.
        findings.append(Finding(
            "ALCANCE-GIT-ILEGIBLE",
            f"No se pudo leer la salida de git para el diff desde baseline ({exc}); "
            "el alcance no puede verificarse.",
            None,
        ))

    fuera_de_alcance = sorted(
        r for r in tocados
        if not es_output_intrinseco(r) and not repo_mod.path_matches_any(r, rutas_autorizadas)
    )
    findings += [Finding("ALCANCE-RUTA", f"Archivo fuera de alcance: {r}", r) for r in fuera_de_alcance]
    return findings

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
from . import scope_amendments
from .core import Finding


class GitIlegibleError(ValueError):
    """La salida de git fue recibida (returncode 0) pero está malformada: NO equivale a «sin
    archivos tocados». `evaluar_alcance` la traduce a `ALCANCE-GIT-ILEGIBLE` (fail-closed)."""


def archivos_tocados_desde_baseline(repo_root: Path, baseline_commit: Optional[str]) -> list:
    """`git diff --name-status -z -M <baseline_commit>` contra el working tree actual (incluye
    commits ya hechos desde baseline Y cambios sin confirmar en una sola diff -- misma semántica
    que `git diff <ref>` nativo). Devuelve rutas relativas POSIX, parseadas con
    `repo.parse_name_status_z` (inmune a `core.quotepath`): rename -> ambas rutas (nueva y vieja),
    copy -> solo el destino. Devuelve [] SOLO si `baseline_commit` es None/vacío. Fail-closed
    (v0.11): un comando fallido (ref inválida/borrada) propaga `GitCommandError`, Git ausente
    propaga `RuntimeError`; si git responde OK pero la salida es malformada, lanza
    `GitIlegibleError`. `evaluar_alcance` traduce todo a `ALCANCE-GIT-ILEGIBLE`."""
    if not baseline_commit:
        return []
    try:
        entradas = repo_mod.diff_name_status(repo_root, baseline_commit)
    except repo_mod.GitCommandError:
        raise
    except repo_mod.GitOutputError as exc:
        # git respondió OK pero la salida es ilegible: fail-closed (no es «sin archivos»).
        raise GitIlegibleError(str(exc)) from exc
    rutas = []
    for codigo, nueva, vieja in entradas:
        rutas.append(Path(nueva).as_posix())
        if codigo.startswith("R") and vieja:
            rutas.append(Path(vieja).as_posix())
    return list(dict.fromkeys(rutas))


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


def alcance_efectivo(change_dir, control: dict) -> tuple:
    """`(rutas, hallazgos)`: scope efectivo de un Change (R21-R25, R22). Función única de lectura
    del alcance: delega en `scope_amendments.estado_alcance` (scope inicial aprobado + cadena de
    enmiendas). Sin `amendments.jsonl` el resultado equivale a la caché de `control.json`
    (compatibilidad total). Si la cadena es inválida (`valido` False), `rutas` es `[]`
    (fail-closed: nada queda autorizado) y `hallazgos` trae `ALCANCE-ENMIENDA-INVALIDA`. Si la
    caché diverge de la cadena, gana la cadena y se agrega `ALCANCE-CACHE-DIVERGENTE`.
    `change_dir` None => no hay dónde buscar la cadena: se usa la caché, sin hallazgos."""
    if change_dir is None:
        rutas_cache = control.get("alcance", {}).get("rutas_autorizadas", [])
        return list(rutas_cache), []
    estado = scope_amendments.estado_alcance(Path(change_dir), control)
    hallazgos = list(estado.hallazgos)
    if not estado.valido:
        if not any(h.codigo == "ALCANCE-ENMIENDA-INVALIDA" for h in hallazgos):
            hallazgos.append(Finding(
                "ALCANCE-ENMIENDA-INVALIDA",
                "La cadena de enmiendas de alcance no es válida; nada queda autorizado.",
                None,
            ))
        return [], hallazgos
    return list(estado.rutas), hallazgos


def _resolver_change_dir(repo_root: Path, control: dict) -> Optional[Path]:
    """`openspec/changes/<change_id>` o, si no existe, `openspec/archive/<change_id>`. `None` si
    el control no trae `change_id` utilizable o ninguno de los dos directorios existe."""
    change_id = control.get("change_id")
    if not isinstance(change_id, str) or not change_id or change_id in (".", ".."):
        return None
    if "/" in change_id or "\\" in change_id:
        return None
    for base in ("changes", "archive"):
        candidato = repo_root / "openspec" / base / change_id
        if candidato.is_dir():
            return candidato
    return None


def evaluar_alcance(repo_root: Path, control: dict, change_dir=None) -> list:
    """[Finding("ALCANCE-RUTA", ...), ...] -- mismo código que ya usaban `cmd_validate`/`gate_cierre`;
    además emite `Finding("ALCANCE-GIT-ILEGIBLE")` (fail-closed) si la salida de git del diff desde
    baseline es ilegible (los hallazgos ALCANCE-RUTA del resto se siguen emitiendo). Unión
    deduplicada de `repo.list_dirty_files` (working tree) + `archivos_tocados_desde_baseline`
    (historial desde baseline), comparada contra el alcance efectivo (`alcance_efectivo`: scope
    aprobado + enmiendas gobernadas; sin enmiendas o sin `change_id`/directorio resoluble, la caché
    `rutas_autorizadas` como siempre) vía `repo.path_matches_any` (reusada tal cual). Propaga además
    `ALCANCE-ENMIENDA-INVALIDA` (cadena inválida: nada autorizado, todo archivo tocado queda fuera
    de alcance) y `ALCANCE-CACHE-DIVERGENTE`. `change_dir` opcional: si se pasa se usa tal cual; si no
    se pasa y no se puede resolver, un control con ancla (`alcance.scope_hash`) es fail-closed
    (`ALCANCE-ENMIENDA-INVALIDA`, nada autorizado); sin ancla (legado) se usa la caché."""
    repo_root = Path(repo_root)
    if change_dir is None:
        change_dir = _resolver_change_dir(repo_root, control)
    alcance_control = control.get("alcance")
    tiene_ancla = isinstance(alcance_control, dict) and bool(alcance_control.get("scope_hash"))
    if change_dir is None and tiene_ancla:
        # Change con ancla de aprobación (`scope_hash`) cuyo directorio no se puede resolver:
        # no se cae a la caché cruda (fail-closed).
        rutas_autorizadas = []
        findings_alcance = [Finding(
            "ALCANCE-ENMIENDA-INVALIDA",
            "No se pudo resolver el directorio del Change para validar el alcance gobernado.",
            None,
        )]
    else:
        rutas_autorizadas, findings_alcance = alcance_efectivo(change_dir, control)
    baseline_commit = control.get("baseline", {}).get("commit")

    tocados = set()
    findings = list(findings_alcance)
    motivos = []
    _errores_git = (repo_mod.GitCommandError, GitIlegibleError, repo_mod.GitOutputError, RuntimeError,
                   ValueError, OSError)
    try:
        tocados |= set(repo_mod.list_dirty_files(repo_root))
    except _errores_git as exc:
        motivos.append(f"working tree: {exc}")
    try:
        tocados |= set(archivos_tocados_desde_baseline(repo_root, baseline_commit))
    except _errores_git as exc:
        motivos.append(f"diff desde baseline: {exc}")
    if motivos:
        # Fail-closed: un único hallazgo; unknown Git state != clean Git state.
        findings.append(Finding(
            "ALCANCE-GIT-ILEGIBLE",
            "No se pudo leer el estado de git (" + "; ".join(motivos) + "); "
            "el alcance no puede verificarse.",
            None,
        ))

    fuera_de_alcance = sorted(
        r for r in tocados
        if not es_output_intrinseco(r) and not repo_mod.path_matches_any(r, rutas_autorizadas)
    )
    findings += [Finding("ALCANCE-RUTA", f"Archivo fuera de alcance: {r}", r) for r in fuera_de_alcance]
    return findings

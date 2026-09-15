"""Matriz de readiness + promocion (Change 6, v0.3:
20260915-readiness-and-promotion): `evaluar_readiness(repo_root, target) ->
list[checks.CheckResult]` (solo lectura, sin short-circuit, matriz completa
por target) y `promote(repo_root, target, reason) -> dict` (promocion
estrictamente secuencial, gateada por readiness, atomica).

Consume `checks.py`/`lifecycle.py`/`maturity.py`/`mlops_foundations.py`/
`mlops_evidence.py` sin modificar ninguno -- este modulo es quien conoce
`project_stage`/CRISP-DM/tiers de MLOps/evidencia, el motor de checks sigue
siendo neutral (mismo principio ya aplicado por `mlops_foundations.py`,
Change 5).

Principio no negociable (R1/R16 de `spec.md`): `project_stage` representa
madurez ALCANZADA, nunca solo declarada. Un `PASS` de `mlops foundations`
NO implica "production ready" -- este modulo reinterpreta la severidad de
`mlops_foundations.evaluar_foundations` en su propio contexto de readiness
(WARN/FAIL/N-A -> FAIL, excepto `lineage`, que se preserva tal cual), sin
mutar el significado propio de `mlops_foundations.py` para ningun otro
consumidor.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from . import checks, lifecycle, maturity, mlops_evidence, mlops_foundations
from .checks import CheckResult
from .core import ahora_utc

TARGETS_VALIDOS: tuple = ("experiment", "production_candidate", "production")

# Unico proximo stage secuencial valido desde cada stage -- sin saltos, sin
# downgrade (R2). "production" no tiene entrada: no hay stage siguiente.
_SECUENCIA: dict = {
    "discovery": "experiment",
    "experiment": "production_candidate",
    "production_candidate": "production",
}

# Fases CRISP-DM que deben estar "cerrada" desde production_candidate en
# adelante (R5.3), en el orden exacto del brief del usuario.
_FASES_CANDIDATE: tuple = (
    "business_understanding",
    "data_understanding",
    "data_preparation",
    "modeling",
    "evaluation",
    "production_readiness",
)


class PromotionError(Exception):
    """Error de dominio de `promote`: reason vacio, target fuera de
    `TARGETS_VALIDOS`, o transicion no secuencial (salto/downgrade/
    repeticion). Nunca muta nada."""


# --- Prerrequisitos (R4/R5.1) -------------------------------------------------

def _evaluar_project_valid(repo_root: Path):
    """(CheckResult, ok: bool, estado: Optional[dict])."""
    codigo = "READINESS-PROJECT-VALID"
    ruta = maturity.state_path(repo_root)
    if not ruta.exists():
        return (
            CheckResult(
                checks.STATUS_FAIL,
                codigo,
                ".harmessi/project.json no existe -- correr 'ds_guard project init' primero.",
            ),
            False,
            None,
        )
    try:
        estado = maturity.leer_estado(ruta)
    except maturity.MaturityEstadoError as exc:
        return (
            CheckResult(
                checks.STATUS_FAIL,
                codigo,
                f".harmessi/project.json existe pero no es valido: {exc}",
                kind=checks.KIND_TECHNICAL_ERROR,
            ),
            False,
            None,
        )
    return (
        CheckResult(
            checks.STATUS_PASS,
            codigo,
            ".harmessi/project.json existe y es valido.",
            subject=estado["project_stage"],
        ),
        True,
        estado,
    )


def _evaluar_lifecycle_valid(repo_root: Path):
    """(CheckResult, ok: bool, estado: Optional[dict])."""
    codigo = "READINESS-LIFECYCLE-VALID"
    ruta = lifecycle.state_path(repo_root)
    if not ruta.exists():
        return (
            CheckResult(
                checks.STATUS_FAIL,
                codigo,
                "openspec/lifecycle/state.json no existe -- correr 'ds_guard lifecycle migrate' "
                "o inicializar el lifecycle.",
            ),
            False,
            None,
        )
    try:
        estado = lifecycle.leer_estado(ruta)
    except lifecycle.LifecycleEstadoError as exc:
        return (
            CheckResult(
                checks.STATUS_FAIL,
                codigo,
                f"openspec/lifecycle/state.json existe pero no es valido: {exc}",
                kind=checks.KIND_TECHNICAL_ERROR,
            ),
            False,
            None,
        )
    return (
        CheckResult(checks.STATUS_PASS, codigo, "openspec/lifecycle/state.json existe y es valido."),
        True,
        estado,
    )


# --- Gobernanza minima (R5.2) --------------------------------------------------

def _check_risk_classified(project_ok: bool, project_estado: Optional[dict]) -> CheckResult:
    codigo = "READINESS-RISK-CLASSIFIED"
    if not project_ok:
        return CheckResult(
            checks.STATUS_FAIL,
            codigo,
            "no se pudo evaluar risk_level: .harmessi/project.json no disponible.",
        )
    risk_level = project_estado.get("risk_level")
    if risk_level is None:
        return CheckResult(
            checks.STATUS_FAIL,
            codigo,
            "risk_level no clasificado -- correr 'ds_guard project set-risk' primero.",
        )
    return CheckResult(checks.STATUS_PASS, codigo, f"risk_level clasificado: {risk_level}.", subject=risk_level)


# --- Lifecycle CRISP-DM (R5.3/R9) ----------------------------------------------

def _codigo_crispdm(fase: str) -> str:
    return f"READINESS-CRISPDM-{fase.upper().replace('_', '-')}"


def _check_crispdm_fase(
    fase: str, lifecycle_ok: bool, lifecycle_estado: Optional[dict], modo: str
) -> CheckResult:
    codigo = _codigo_crispdm(fase)
    if not lifecycle_ok:
        return CheckResult(
            checks.STATUS_FAIL,
            codigo,
            f"no se pudo evaluar la fase CRISP-DM '{fase}': lifecycle no disponible.",
        )
    estado_fase = lifecycle_estado["crispdm"]["fases"][fase]["estado"]
    if modo == "cerrada":
        if estado_fase == "cerrada":
            return CheckResult(checks.STATUS_PASS, codigo, f"Fase CRISP-DM '{fase}' cerrada.", subject=estado_fase)
        return CheckResult(
            checks.STATUS_FAIL,
            codigo,
            f"Fase CRISP-DM '{fase}' debe estar 'cerrada' (estado actual: '{estado_fase}').",
            subject=estado_fase,
        )
    if modo == "en_progreso_o_cerrada":
        if estado_fase in ("en_progreso", "cerrada"):
            return CheckResult(
                checks.STATUS_PASS,
                codigo,
                f"Fase CRISP-DM '{fase}' en estado suficiente ('{estado_fase}').",
                subject=estado_fase,
            )
        return CheckResult(
            checks.STATUS_FAIL,
            codigo,
            f"Fase CRISP-DM '{fase}' debe estar al menos 'en_progreso' (estado actual: '{estado_fase}').",
            subject=estado_fase,
        )
    raise ValueError(f"modo desconocido: {modo!r}")


# --- MLOps foundations reinterpretado (R5.4, design.md punto 6) ---------------

_TABLA_FOUNDATIONS: dict = {
    mlops_foundations.CODIGO_REPRODUCIBILIDAD: "READINESS-FOUNDATIONS-REPRODUCIBILIDAD",
    mlops_foundations.CODIGO_VERSIONADO: "READINESS-FOUNDATIONS-VERSIONADO",
    mlops_foundations.CODIGO_ARTIFACTS: "READINESS-FOUNDATIONS-ARTIFACTS",
}
CODIGO_FOUNDATIONS_LINEAGE = "READINESS-FOUNDATIONS-LINEAGE"


def _reinterpretar_foundation(resultado: CheckResult) -> CheckResult:
    """Unico punto de reinterpretacion de severidad de foundations -- ver
    design.md punto 6/riesgo 1: `reproducibilidad`/`versionado`/`artifacts`
    solo `PASS` propaga `PASS`, cualquier otro status (`WARN`/`FAIL`/`N/A`)
    se convierte en `FAIL` en este contexto de readiness. `lineage` (y
    cualquier codigo derivado de excepcion, `<codigo>-EXCEPCION`) preserva
    su status TAL CUAL -- excepcion explicita y unica (R5.4/R10)."""
    if resultado.code == mlops_foundations.CODIGO_LINEAGE or resultado.code.startswith(
        mlops_foundations.CODIGO_LINEAGE + "-"
    ):
        return CheckResult(resultado.status, CODIGO_FOUNDATIONS_LINEAGE, resultado.message, kind=resultado.kind)

    codigo_readiness = _TABLA_FOUNDATIONS.get(resultado.code)
    if codigo_readiness is None:
        for codigo_base, mapeado in _TABLA_FOUNDATIONS.items():
            if resultado.code.startswith(codigo_base + "-"):
                codigo_readiness = mapeado
                break
    if codigo_readiness is None:
        # No deberia ocurrir con el catalogo actual de mlops_foundations,
        # pero nunca se descarta un resultado silenciosamente.
        codigo_readiness = f"READINESS-FOUNDATIONS-{resultado.code}"

    if resultado.status == checks.STATUS_PASS:
        return CheckResult(checks.STATUS_PASS, codigo_readiness, resultado.message, kind=resultado.kind)
    return CheckResult(
        checks.STATUS_FAIL,
        codigo_readiness,
        f"{resultado.message} (WARN/FAIL/N-A de mlops_foundations se trata como FAIL en este "
        "contexto de readiness -- foundations PASS no implica production-ready, y viceversa).",
        kind=resultado.kind,
    )


def _check_foundations(repo_root: Path) -> list:
    """4 resultados (reproducibilidad, versionado, lineage, artifacts), en
    ese orden -- `evaluar_foundations` es siempre read-only y nunca lanza,
    asi que no hace falta gating por prerrequisitos acá."""
    resultados_foundations = mlops_foundations.evaluar_foundations(repo_root)
    # resultados_foundations[0] es MLOPS-FOUNDATIONS-PROJECT-STAGE (informativo,
    # no forma parte de la matriz de readiness -- no se reinterpreta).
    return [_reinterpretar_foundation(r) for r in resultados_foundations[1:]]


# --- Evidencia de production_readiness/operations (R5.5/R8/R9) ----------------

def _codigo_prodready(capability: str) -> str:
    return f"READINESS-PRODREADY-{capability.upper().replace('_', '-')}"


def _codigo_ops(capability: str) -> str:
    return f"READINESS-OPS-{capability.upper().replace('_', '-')}"


def _check_evidence(tier: str, capability: str, repo_root: Path) -> CheckResult:
    codigo = _codigo_prodready(capability) if tier == "production_readiness" else _codigo_ops(capability)
    try:
        valido, detalle = mlops_evidence.evidencia_valida(repo_root, tier, capability)
    except (FileNotFoundError, lifecycle.LifecycleEstadoError) as exc:
        return CheckResult(
            checks.STATUS_FAIL,
            codigo,
            f"no se pudo evaluar evidencia de '{capability}' ({tier}): {exc}",
            kind=checks.KIND_TECHNICAL_ERROR,
        )
    if valido:
        return CheckResult(checks.STATUS_PASS, codigo, f"Evidencia valida para '{capability}' ({tier}): {detalle}")
    return CheckResult(checks.STATUS_FAIL, codigo, f"Sin evidencia valida para '{capability}' ({tier}): {detalle}")


def _check_environment_reproducible(repo_root: Path) -> CheckResult:
    """Regla especifica de R8: `PASS` si existe un lockfile reconocido por
    Change 5 (`mlops_foundations._ARCHIVOS_LOCKFILE`) -- o, si no hay
    lockfile, satisfacible via evidencia explicita valida."""
    codigo = _codigo_prodready("environment_reproducible")
    tiene_lockfile = any(
        (repo_root / nombre).exists() for nombre in mlops_foundations._ARCHIVOS_LOCKFILE
    )
    if tiene_lockfile:
        return CheckResult(
            checks.STATUS_PASS,
            codigo,
            f"Lockfile de entorno presente ({'/'.join(mlops_foundations._ARCHIVOS_LOCKFILE)}).",
        )
    try:
        valido, detalle = mlops_evidence.evidencia_valida(repo_root, "production_readiness", "environment_reproducible")
    except (FileNotFoundError, lifecycle.LifecycleEstadoError) as exc:
        return CheckResult(
            checks.STATUS_FAIL,
            codigo,
            f"no se pudo evaluar evidencia de 'environment_reproducible': {exc}",
            kind=checks.KIND_TECHNICAL_ERROR,
        )
    if valido:
        return CheckResult(checks.STATUS_PASS, codigo, f"Evidencia valida para 'environment_reproducible': {detalle}")
    return CheckResult(
        checks.STATUS_FAIL,
        codigo,
        f"Sin lockfile de entorno ni evidencia valida para 'environment_reproducible': {detalle}",
    )


# --- evaluar_readiness ---------------------------------------------------------

def evaluar_readiness(repo_root: Path, target: str) -> list:
    """Matriz completa de readiness para `target`, SIEMPRE de solo lectura
    (nunca modifica `.harmessi/project.json`, `openspec/lifecycle/
    state.json`, el decision ledger, ni evidencia MLOps), sin short-circuit
    (roster de resultados de longitud fija por target, ver design.md punto
    7): cada gate se reporta siempre, aunque un prerrequisito falte."""
    repo_root = Path(repo_root)
    if target not in TARGETS_VALIDOS:
        raise ValueError(f"target invalido: {target!r} (validos: {TARGETS_VALIDOS})")

    resultado_project, project_ok, project_estado = _evaluar_project_valid(repo_root)
    resultado_lifecycle, lifecycle_ok, lifecycle_estado = _evaluar_lifecycle_valid(repo_root)
    resultados = [resultado_project, resultado_lifecycle]

    if target == "experiment":
        return resultados

    resultados.append(_check_risk_classified(project_ok, project_estado))

    for fase in _FASES_CANDIDATE:
        resultados.append(_check_crispdm_fase(fase, lifecycle_ok, lifecycle_estado, "cerrada"))

    resultados.extend(_check_foundations(repo_root))

    for cap in lifecycle.MLOPS_CAPACIDADES["production_readiness"]:
        if cap == "environment_reproducible":
            resultados.append(_check_environment_reproducible(repo_root))
        else:
            resultados.append(_check_evidence("production_readiness", cap, repo_root))

    if target == "production_candidate":
        return resultados

    resultados.append(_check_crispdm_fase("deployment", lifecycle_ok, lifecycle_estado, "cerrada"))
    resultados.append(_check_crispdm_fase("monitoring", lifecycle_ok, lifecycle_estado, "en_progreso_o_cerrada"))

    for cap in lifecycle.MLOPS_CAPACIDADES["operations"]:
        resultados.append(_check_evidence("operations", cap, repo_root))

    return resultados


# --- promote --------------------------------------------------------------------

def promote(repo_root: Path, target: str, reason: str) -> dict:
    """Promocion estrictamente secuencial, gateada por
    `evaluar_readiness(repo_root, target)` (solo lectura), atomica: si hay
    algun `FAIL` -> no muta nada; si pasa -> muta UNICAMENTE
    `.harmessi/project.json` via `maturity.escribir_estado` (`project_stage`
    + una entrada nueva en `stage_history` con `via="promote"`). Nunca
    escribe el lifecycle ni evidencia MLOps.

    `FileNotFoundError` si `.harmessi/project.json` no existe todavia
    (mismo criterio que el resto de `maturity.py`: correr 'project init'
    primero, nunca bootstrap implicito). `PromotionError` para cualquier
    otro rechazo de dominio (reason vacio, target invalido, transicion no
    secuencial)."""
    repo_root = Path(repo_root)
    if not reason:
        raise PromotionError("'--reason' es obligatorio y no puede estar vacio")
    if target not in TARGETS_VALIDOS:
        raise PromotionError(f"target invalido: {target!r} (validos: {TARGETS_VALIDOS})")

    ruta_project = maturity.state_path(repo_root)
    if not ruta_project.exists():
        raise FileNotFoundError(
            f"No existe {ruta_project} todavia -- correr 'ds_guard project init' primero."
        )
    estado = maturity.leer_estado(ruta_project)
    stage_actual = estado["project_stage"]

    siguiente_valido = _SECUENCIA.get(stage_actual)
    if siguiente_valido != target:
        raise PromotionError(
            f"Transicion invalida: desde '{stage_actual}' el unico proximo stage secuencial "
            f"valido es {siguiente_valido!r}, no {target!r} -- sin saltos, sin downgrade, sin "
            "repeticion (ver R2 de spec.md)."
        )

    resultados = evaluar_readiness(repo_root, target)
    if checks.hay_bloqueo(resultados):
        return {
            "promovido": False,
            "ready": False,
            "resultados": resultados,
            "project_stage": stage_actual,
        }

    ahora = ahora_utc()
    estado["project_stage"] = target
    estado.setdefault("stage_history", []).append(
        {"from": stage_actual, "to": target, "via": "promote", "reason": reason, "utc": ahora}
    )
    maturity.escribir_estado(repo_root, estado)

    return {
        "promovido": True,
        "ready": True,
        "resultados": resultados,
        "project_stage": target,
    }

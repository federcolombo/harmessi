"""Estado de madurez/gobernanza del proyecto (Change 3, v0.3): project_stage
+ risk_level, en .harmessi/project.json -- eje ortogonal al lifecycle
CRISP-DM/KDD/MLOps (openspec/lifecycle/state.json), sin mutarlo ni ser
mutado por él.

No implementa readiness, promotion, checks engine ni scaffold progresivo --
solo estado + auditoría (ver design.md del change).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from . import kdd_compat, lifecycle
from .core import ahora_utc, escribir_texto_atomico

PROJECT_STAGES = ("discovery", "experiment", "production_candidate", "production")
STAGES_INIT_PERMITIDOS = ("discovery", "experiment")
RISK_LEVELS = ("low", "medium", "high")

SCHEMA_VERSION_SOPORTADA = 1


class MaturityEstadoError(Exception):
    """project.json existe pero no es válido (JSON corrupto, schema
    inesperada), o precondición de operación incumplida (calibrate sin init
    previo, o con promote ya registrado, reason faltante, valores
    inválidos). Nunca se repara ni se sobreescribe automáticamente."""


def state_path(repo_root: Path) -> Path:
    return Path(repo_root) / ".harmessi" / "project.json"


def estado_riesgo(project_data: dict) -> str:
    """Deriva 'unclassified'/'classified' puro de risk_level -- nunca se
    persiste (ver design.md: evita una segunda fuente de verdad, mismo
    precedente que fase_actual/paso_actual en lifecycle.py)."""
    return "unclassified" if project_data.get("risk_level") is None else "classified"


def inferir_stage(repo_root: Path) -> tuple:
    """(stage, reason). Existencia de lifecycle/state.json o legacy
    kdd/state.json -- nunca su contenido. 'experiment' si alguno existe,
    'discovery' si ninguno."""
    repo_root = Path(repo_root)
    existe_lifecycle = lifecycle.state_path(repo_root).exists()
    existe_legacy = kdd_compat.state_path_legacy(repo_root).exists()
    if existe_lifecycle or existe_legacy:
        detectado = []
        if existe_lifecycle:
            detectado.append("openspec/lifecycle/state.json")
        if existe_legacy:
            detectado.append("openspec/kdd/state.json (legacy)")
        return "experiment", f"Detectado {', '.join(detectado)} -- proyecto con evidencia previa de trabajo DS."
    return (
        "discovery",
        "No se detectó openspec/lifecycle/state.json ni openspec/kdd/state.json -- "
        "sin evidencia previa de trabajo DS, arranca liviano.",
    )


def _entrada_stage(desde, hacia: str, via: str, reason: str, ahora: str) -> dict:
    return {"from": desde, "to": hacia, "via": via, "reason": reason, "utc": ahora}


def estado_inicial(project_stage: str, via: str, reason: str) -> dict:
    ahora = ahora_utc()
    return {
        "schema_version": SCHEMA_VERSION_SOPORTADA,
        "creado_utc": ahora,
        "project_stage": project_stage,
        "risk_level": None,
        "stage_history": [_entrada_stage(None, project_stage, via, reason, ahora)],
        "risk_history": [],
    }


def _validar_entrada_historial(entrada, contexto: str) -> None:
    if not isinstance(entrada, dict):
        raise MaturityEstadoError(f"{contexto}: entrada de historial debe ser un objeto")
    for clave in ("from", "to", "via", "reason", "utc"):
        if clave not in entrada:
            raise MaturityEstadoError(f"{contexto}: falta '{clave}'")


def validar_estructura(datos: dict) -> None:
    if not isinstance(datos, dict):
        raise MaturityEstadoError("se esperaba un objeto JSON en la raíz")
    if datos.get("schema_version") != SCHEMA_VERSION_SOPORTADA:
        raise MaturityEstadoError(
            f"schema_version desconocida: {datos.get('schema_version')!r} "
            f"(se esperaba {SCHEMA_VERSION_SOPORTADA})"
        )
    if not datos.get("creado_utc"):
        raise MaturityEstadoError("'creado_utc' ausente")
    if datos.get("project_stage") not in PROJECT_STAGES:
        raise MaturityEstadoError(f"'project_stage' inválido: {datos.get('project_stage')!r}")
    risk_level = datos.get("risk_level")
    if risk_level is not None and risk_level not in RISK_LEVELS:
        raise MaturityEstadoError(f"'risk_level' inválido: {risk_level!r}")
    if "risk_status" in datos:
        raise MaturityEstadoError("'risk_status' no debe persistirse -- se deriva de risk_level (ver design.md)")
    stage_history = datos.get("stage_history")
    if not isinstance(stage_history, list):
        raise MaturityEstadoError("'stage_history' debe ser una lista")
    for entrada in stage_history:
        _validar_entrada_historial(entrada, "stage_history")
    risk_history = datos.get("risk_history")
    if not isinstance(risk_history, list):
        raise MaturityEstadoError("'risk_history' debe ser una lista")
    for entrada in risk_history:
        _validar_entrada_historial(entrada, "risk_history")


def leer_estado(path: Path) -> dict:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"No existe {path}")
    with open(path, "r", encoding="utf-8") as f:
        try:
            datos = json.load(f)
        except json.JSONDecodeError as e:
            raise MaturityEstadoError(f"{path} no es JSON válido: {e}")
    try:
        validar_estructura(datos)
    except MaturityEstadoError as e:
        raise MaturityEstadoError(f"{path}: {e}")
    return datos


def escribir_estado(repo_root: Path, estado: dict) -> None:
    validar_estructura(estado)
    texto = json.dumps(estado, indent=2, ensure_ascii=False) + "\n"
    escribir_texto_atomico(state_path(repo_root), texto)


def project_init(repo_root: Path, stage: Optional[str] = None, adopt: bool = False):
    """(estado, creado: bool). Idempotente si project.json ya existe y es
    válido. 'stage' y 'adopt' son mutuamente excluyentes (ajuste L2)."""
    repo_root = Path(repo_root)
    path = state_path(repo_root)
    if path.exists():
        return leer_estado(path), False

    if stage is not None and adopt:
        raise MaturityEstadoError("'--stage' y '--adopt' son mutuamente excluyentes")

    if adopt:
        stage_resuelto, reason = inferir_stage(repo_root)
        via = "migration_inference"
    else:
        stage_resuelto = stage or "experiment"
        if stage_resuelto not in STAGES_INIT_PERMITIDOS:
            raise MaturityEstadoError(
                f"'project init' solo acepta {STAGES_INIT_PERMITIDOS} -- para "
                "'production_candidate'/'production' usar 'project calibrate --stage ... --reason ...'"
            )
        reason = "Inicialización explícita de proyecto nuevo."
        via = "explicit_init"

    estado = estado_inicial(stage_resuelto, via, reason)
    escribir_estado(repo_root, estado)
    return estado, True


def calibrar(repo_root: Path, stage: str, reason: str) -> dict:
    repo_root = Path(repo_root)
    path = state_path(repo_root)
    if not path.exists():
        raise MaturityEstadoError(
            "No existe .harmessi/project.json todavía -- correr 'ds_guard project init' primero."
        )
    if not reason:
        raise MaturityEstadoError("'calibrate' requiere --reason")
    if stage not in PROJECT_STAGES:
        raise MaturityEstadoError(f"stage inválido: {stage!r}")

    estado = leer_estado(path)
    if any(e.get("via") == "promote" for e in estado.get("stage_history", [])):
        raise MaturityEstadoError(
            "El proyecto ya tiene una promoción registrada (via='promote') en su historial -- "
            "'calibrate' no puede usarse para saltear eso. Usar 'project promote' (change futuro)."
        )

    anterior = estado["project_stage"]
    ahora = ahora_utc()
    estado["project_stage"] = stage
    estado.setdefault("stage_history", []).append(_entrada_stage(anterior, stage, "calibrate", reason, ahora))
    escribir_estado(repo_root, estado)
    return estado


def set_risk(repo_root: Path, nivel: str, reason: str) -> dict:
    repo_root = Path(repo_root)
    path = state_path(repo_root)
    if not path.exists():
        raise MaturityEstadoError(
            "No existe .harmessi/project.json todavía -- correr 'ds_guard project init' primero."
        )
    if not reason:
        raise MaturityEstadoError("'set-risk' requiere --reason")
    if nivel not in RISK_LEVELS:
        raise MaturityEstadoError(f"risk_level inválido: {nivel!r} (válidos: {RISK_LEVELS})")

    estado = leer_estado(path)
    anterior = estado.get("risk_level")
    ahora = ahora_utc()
    estado["risk_level"] = nivel
    estado.setdefault("risk_history", []).append(
        {"from": anterior, "to": nivel, "via": "explicit", "reason": reason, "utc": ahora}
    )
    escribir_estado(repo_root, estado)
    return estado


def project_status(repo_root: Path) -> dict:
    estado = leer_estado(state_path(Path(repo_root)))
    stage_history = estado.get("stage_history", [])
    origen_stage = stage_history[-1] if stage_history else None
    return {
        "project_stage": estado["project_stage"],
        "risk_level": estado.get("risk_level"),
        "risk_status": estado_riesgo(estado),
        "origen_stage": origen_stage,
        "stage_history": stage_history,
        "risk_history": estado.get("risk_history", []),
    }

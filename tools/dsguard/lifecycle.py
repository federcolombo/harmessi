"""Lifecycle metodológico neutral del proyecto (Change 1, v0.3): CRISP-DM como
lifecycle principal, KDD como proceso técnico subordinado, MLOps como
capacidades progresivas -- todo en un único `openspec/lifecycle/state.json`,
para no crear máquinas de estado paralelas (ver
`openspec/changes/20260914-lifecycle-core-schema/design.md`).

No migra desde `openspec/kdd/state.json` v0.2 (Change 2, que además repunta
`ds_guard kdd`). No implementa transición ni gating de ningún tipo -- solo
catálogo, init, lectura, validación y escritura atómica.

No conoce Git, igual que `kdd.py`: usa rutas relativas a `repo_root`.
"""
from __future__ import annotations

import json
from pathlib import Path

from .core import ahora_utc, escribir_texto_atomico

# --- Catálogo CRISP-DM ---------------------------------------------------------

FASES_CRISPDM = (
    "business_understanding",
    "data_understanding",
    "data_preparation",
    "modeling",
    "evaluation",
    "production_readiness",
    "deployment",
    "monitoring",
)

# --- Catálogo KDD (proceso técnico subordinado) ---------------------------------

PASOS_KDD = (
    "selection",
    "preprocessing",
    "transformation",
    "data_mining",
    "interpretation_evaluation",
)

# Fase CRISP-DM -> pasos KDD que ocurren "dentro" de ella. Tupla vacía = sin
# paso KDD obligatorio.
MAPEO_CRISPDM_A_KDD = {
    "business_understanding": (),
    "data_understanding": ("selection",),
    "data_preparation": ("preprocessing", "transformation"),
    "modeling": ("data_mining",),
    "evaluation": ("interpretation_evaluation",),
    "production_readiness": (),
    "deployment": (),
    "monitoring": (),
}


def _invertir_mapeo(mapeo: dict) -> dict:
    inverso = {}
    for fase, pasos in mapeo.items():
        for paso in pasos:
            inverso[paso] = fase
    return inverso


# Derivado de MAPEO_CRISPDM_A_KDD -- nunca hardcodeado aparte.
MAPEO_KDD_A_CRISPDM = _invertir_mapeo(MAPEO_CRISPDM_A_KDD)

# --- Catálogo MLOps (capacidades progresivas) ------------------------------------

MLOPS_TIERS = ("foundations", "production_readiness", "operations")

MLOPS_CAPACIDADES = {
    "foundations": ("reproducibilidad", "versionado", "lineage", "artifacts"),
    "production_readiness": (
        "packaging",
        "environment_reproducible",
        "inference_contract",
        "inference_tests",
        "trazabilidad_fuerte",
    ),
    "operations": (
        "deployment",
        "cicd",
        "monitoring",
        "rollback",
        "drift",
        "alerts",
        "retraining",
    ),
}

# --- Estados --------------------------------------------------------------------

# v0.2 (kdd.py) tiene un cuarto estado, "futura", retirado acá por decisión
# explícita (ver design.md "Sobre el estado futura"): el gating de madurez de
# proyecto no vive en este archivo -- vive en project_stage (Change 3+).
ESTADOS_VALIDOS = frozenset({"no_iniciada", "en_progreso", "cerrada"})

SCHEMA_VERSION_SOPORTADA = 1


class LifecycleEstadoError(Exception):
    """`state.json` existe pero no es válido: JSON corrupto o schema
    inesperada. Nunca se repara ni se sobreescribe automáticamente."""


def state_path(repo_root: Path) -> Path:
    return Path(repo_root) / "openspec" / "lifecycle" / "state.json"


def _entrada_inicial(ahora: str) -> dict:
    return {"estado": "no_iniciada", "changes": [], "evidencia": [], "actualizado_utc": ahora}


def estado_inicial() -> dict:
    ahora = ahora_utc()
    crispdm_fases = {fase: _entrada_inicial(ahora) for fase in FASES_CRISPDM}
    kdd_pasos = {paso: _entrada_inicial(ahora) for paso in PASOS_KDD}
    mlops = {
        tier: {cap: _entrada_inicial(ahora) for cap in MLOPS_CAPACIDADES[tier]}
        for tier in MLOPS_TIERS
    }
    return {
        "schema_version": SCHEMA_VERSION_SOPORTADA,
        "creado_utc": ahora,
        "migrado_desde": None,
        "crispdm": {"fases": crispdm_fases},
        "kdd": {"pasos": kdd_pasos},
        "mlops": mlops,
        "historial_transiciones": [],
    }


def _validar_entrada_trackeable(entrada, contexto: str) -> None:
    if not isinstance(entrada, dict) or entrada.get("estado") not in ESTADOS_VALIDOS:
        raise LifecycleEstadoError(f"{contexto}: 'estado' ausente o inválido")
    if not isinstance(entrada.get("changes"), list) or not isinstance(entrada.get("evidencia"), list):
        raise LifecycleEstadoError(f"{contexto}: 'changes'/'evidencia' inválidos")
    if not entrada.get("actualizado_utc"):
        raise LifecycleEstadoError(f"{contexto}: 'actualizado_utc' ausente")


def validar_estructura(datos: dict) -> None:
    if not isinstance(datos, dict):
        raise LifecycleEstadoError("se esperaba un objeto JSON en la raíz")
    if datos.get("schema_version") != SCHEMA_VERSION_SOPORTADA:
        raise LifecycleEstadoError(
            f"schema_version desconocida: {datos.get('schema_version')!r} "
            f"(se esperaba {SCHEMA_VERSION_SOPORTADA})"
        )
    if not datos.get("creado_utc"):
        raise LifecycleEstadoError("'creado_utc' ausente")
    if "migrado_desde" not in datos:
        raise LifecycleEstadoError("'migrado_desde' ausente (debe ser null o un dict)")

    crispdm = datos.get("crispdm")
    if not isinstance(crispdm, dict):
        raise LifecycleEstadoError("'crispdm' debe ser un objeto")
    fases = crispdm.get("fases")
    if not isinstance(fases, dict) or set(fases.keys()) != set(FASES_CRISPDM):
        raise LifecycleEstadoError("'crispdm.fases' debe tener exactamente las 8 fases del catálogo")
    for fase, entrada in fases.items():
        _validar_entrada_trackeable(entrada, f"crispdm.fases.{fase}")

    kdd = datos.get("kdd")
    if not isinstance(kdd, dict):
        raise LifecycleEstadoError("'kdd' debe ser un objeto")
    pasos = kdd.get("pasos")
    if not isinstance(pasos, dict) or set(pasos.keys()) != set(PASOS_KDD):
        raise LifecycleEstadoError("'kdd.pasos' debe tener exactamente los 5 pasos del catálogo")
    for paso, entrada in pasos.items():
        _validar_entrada_trackeable(entrada, f"kdd.pasos.{paso}")

    mlops = datos.get("mlops")
    if not isinstance(mlops, dict) or set(mlops.keys()) != set(MLOPS_TIERS):
        raise LifecycleEstadoError("'mlops' debe tener exactamente los 3 tiers del catálogo")
    for tier in MLOPS_TIERS:
        capacidades = mlops[tier]
        if not isinstance(capacidades, dict) or set(capacidades.keys()) != set(MLOPS_CAPACIDADES[tier]):
            raise LifecycleEstadoError(f"'mlops.{tier}' debe tener exactamente sus capacidades del catálogo")
        for cap, entrada in capacidades.items():
            _validar_entrada_trackeable(entrada, f"mlops.{tier}.{cap}")

    if not isinstance(datos.get("historial_transiciones"), list):
        raise LifecycleEstadoError("'historial_transiciones' debe ser una lista")


def leer_estado(path: Path) -> dict:
    """Lee y valida `state.json`. `FileNotFoundError` si no existe;
    `LifecycleEstadoError` si existe pero el contenido no es válido. Nunca
    escribe."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"No existe {path}")
    with open(path, "r", encoding="utf-8") as f:
        try:
            datos = json.load(f)
        except json.JSONDecodeError as e:
            raise LifecycleEstadoError(f"{path} no es JSON válido: {e}")
    try:
        validar_estructura(datos)
    except LifecycleEstadoError as e:
        raise LifecycleEstadoError(f"{path}: {e}")
    return datos


def escribir_estado(repo_root: Path, estado: dict) -> None:
    """Valida y escribe `state.json` atómicamente (temp + os.replace, vía
    `core.escribir_texto_atomico`)."""
    validar_estructura(estado)
    texto = json.dumps(estado, indent=2, ensure_ascii=False) + "\n"
    escribir_texto_atomico(state_path(repo_root), texto)


def lifecycle_init(repo_root: Path):
    """(estado, creado: bool). Idempotente: si `state.json` ya existe y es
    válido, lo devuelve tal cual sin tocarlo (`creado=False`). Si existe pero
    está corrupto, deja que `LifecycleEstadoError` se propague -- nunca lo
    sobreescribe."""
    path = state_path(repo_root)
    if path.exists():
        return leer_estado(path), False
    estado = estado_inicial()
    escribir_estado(repo_root, estado)
    return estado, True

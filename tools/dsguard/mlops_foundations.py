"""Fundamentos MLOps activos desde project_stage=experiment (Change 5, v0.3):
reproducibilidad, versionado, lineage, artifacts -- medidos con el motor
neutral de checks (tools/dsguard/checks.py), reflejados en
openspec/lifecycle/state.json -> mlops.foundations.

Solo el tier "foundations". production_readiness/operations quedan para
changes futuros (readiness/promotion, deployment/monitoring).

Principio fuerte: evaluar_foundations() es SIEMPRE read-only -- nunca
escribe openspec/lifecycle/state.json ni .harmessi/project.json.
Persistir evidencia es una operación EXPLÍCITA y separada
(registrar_evidencia), nunca un efecto secundario de medir/leer.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from . import checks, lifecycle, maturity, repo
from .core import ahora_utc

CODIGO_PROJECT_STAGE = "MLOPS-FOUNDATIONS-PROJECT-STAGE"
CODIGO_REPRODUCIBILIDAD = "MLOPS-FOUNDATIONS-REPRODUCIBILIDAD"
CODIGO_VERSIONADO = "MLOPS-FOUNDATIONS-VERSIONADO"
CODIGO_LINEAGE = "MLOPS-FOUNDATIONS-LINEAGE"
CODIGO_ARTIFACTS = "MLOPS-FOUNDATIONS-ARTIFACTS"

_ARCHIVOS_LOCKFILE = ("requirements-lock.txt", "poetry.lock", "Pipfile.lock")

_CODE_A_CAPABILITY = {
    CODIGO_REPRODUCIBILIDAD: "reproducibilidad",
    CODIGO_VERSIONADO: "versionado",
    CODIGO_LINEAGE: "lineage",
    CODIGO_ARTIFACTS: "artifacts",
}


def _capability_de_codigo(code: str) -> Optional[str]:
    """Mapea un CheckResult.code a su capability, incluyendo el caso de
    excepción ("{codigo_base}-EXCEPCION", ver checks.ejecutar_checks) --
    sin esto, un check que falló con excepción quedaba sin snapshot
    registrado en registrar_evidencia, silenciosamente."""
    if code in _CODE_A_CAPABILITY:
        return _CODE_A_CAPABILITY[code]
    if code.endswith("-EXCEPCION"):
        return _CODE_A_CAPABILITY.get(code[: -len("-EXCEPCION")])
    return None


def _na_por_stage(project_stage: Optional[str]) -> Optional[str]:
    """Motivo de N/A si corresponde (project_stage None o discovery);
    None si hay que evaluar de verdad. Mensajes DISTINTOS a propósito
    (uno es 'no configurado todavía', el otro es 'elegido a propósito')."""
    if project_stage is None:
        return (
            ".harmessi/project.json no existe todavía -- correr "
            "'ds_guard project init' para activar los fundamentos MLOps."
        )
    if project_stage == "discovery":
        return "No aplica en discovery -- los fundamentos MLOps aplican desde experiment."
    return None


def _tiene_data_con_contenido(repo_root: Path) -> bool:
    data_dir = repo_root / "data"
    if not data_dir.is_dir():
        return False
    return any(p.is_file() for p in data_dir.rglob("*"))


def _tiene_fingerprint_evidencia(repo_root: Path) -> bool:
    profiles_dir = repo_root / ".harmessi" / "profiles"
    if not profiles_dir.is_dir():
        return False
    return any(profiles_dir.glob("*/profile.json"))


def _tiene_lockfile(repo_root: Path) -> bool:
    return any((repo_root / nombre).exists() for nombre in _ARCHIVOS_LOCKFILE)


def _dir_con_contenido(repo_root: Path, nombre: str) -> bool:
    d = repo_root / nombre
    if not d.is_dir():
        return False
    return any(p.is_file() for p in d.rglob("*"))


def check_reproducibilidad(repo_root: Path, project_stage: Optional[str]) -> list:
    """(repo_root, project_stage) -> [checks.CheckResult] (lista de un solo
    elemento -- forma exigida por `checks.ejecutar_checks`, ver
    `evaluar_foundations`)."""
    motivo_na = _na_por_stage(project_stage)
    if motivo_na is not None:
        return [checks.CheckResult(checks.STATUS_NA, CODIGO_REPRODUCIBILIDAD, motivo_na)]

    repo_root = Path(repo_root)
    commit, _rama = repo.get_head(repo_root)
    sucio = bool(repo.list_dirty_files(repo_root))
    tiene_data = _tiene_data_con_contenido(repo_root)
    tiene_fingerprint = _tiene_fingerprint_evidencia(repo_root)
    tiene_lock = _tiene_lockfile(repo_root)

    problemas = []
    if sucio:
        problemas.append("working tree con cambios sin confirmar")
    if tiene_data and not tiene_fingerprint:
        problemas.append("hay data/ con contenido pero sin fingerprint registrado (correr ds_profile)")
    if not tiene_lock:
        problemas.append(f"sin lockfile de entorno ({'/'.join(_ARCHIVOS_LOCKFILE)})")

    if not problemas:
        return [
            checks.CheckResult(
                checks.STATUS_PASS,
                CODIGO_REPRODUCIBILIDAD,
                f"Commit {commit[:8]} identificable, working tree limpio, evidencia de entorno/datos suficiente.",
                subject=commit,
            )
        ]
    return [
        checks.CheckResult(
            checks.STATUS_WARN,
            CODIGO_REPRODUCIBILIDAD,
            "Reproducibilidad parcial: " + "; ".join(problemas) + ".",
            subject=commit,
        )
    ]


def check_versionado(repo_root: Path, project_stage: Optional[str]) -> list:
    """(repo_root, project_stage) -> [checks.CheckResult]."""
    motivo_na = _na_por_stage(project_stage)
    if motivo_na is not None:
        return [checks.CheckResult(checks.STATUS_NA, CODIGO_VERSIONADO, motivo_na)]

    repo_root = Path(repo_root)
    commit, _rama = repo.get_head(repo_root)
    tiene_data = _tiene_data_con_contenido(repo_root)
    tiene_fingerprint = _tiene_fingerprint_evidencia(repo_root)

    if not tiene_data:
        return [
            checks.CheckResult(
                checks.STATUS_PASS,
                CODIGO_VERSIONADO,
                f"Código versionado por git (HEAD {commit[:8]}); no hay data/ con contenido que versionar todavía.",
                subject=commit,
            )
        ]
    if tiene_fingerprint:
        return [
            checks.CheckResult(
                checks.STATUS_PASS,
                CODIGO_VERSIONADO,
                f"Código versionado por git (HEAD {commit[:8]}); datos con fingerprint registrado.",
                subject=commit,
            )
        ]
    return [
        checks.CheckResult(
            checks.STATUS_WARN,
            CODIGO_VERSIONADO,
            f"Código versionado por git (HEAD {commit[:8]}), pero hay data/ con contenido sin evidencia de fingerprint.",
            subject=commit,
        )
    ]


def check_lineage(repo_root: Path, project_stage: Optional[str]) -> list:
    """(repo_root, project_stage) -> [checks.CheckResult]."""
    motivo_na = _na_por_stage(project_stage)
    if motivo_na is not None:
        return [checks.CheckResult(checks.STATUS_NA, CODIGO_LINEAGE, motivo_na)]

    repo_root = Path(repo_root)
    ruta_lifecycle = lifecycle.state_path(repo_root)
    if not ruta_lifecycle.exists():
        return [
            checks.CheckResult(
                checks.STATUS_NA, CODIGO_LINEAGE, "openspec/lifecycle/state.json no existe todavía."
            )
        ]

    estado = lifecycle.leer_estado(ruta_lifecycle)
    pasos_con_evidencia = [
        paso for paso, entrada in estado["kdd"]["pasos"].items()
        if entrada.get("changes") or entrada.get("evidencia")
    ]
    if pasos_con_evidencia:
        detalle = f"Evidencia indirecta vía pasos KDD con changes/evidencia: {', '.join(pasos_con_evidencia)}."
    else:
        detalle = "Sin evidencia indirecta todavía (ningún paso KDD tiene changes/evidencia registrada)."

    # NUNCA PASS acá -- no hay motor de lineage real todavía (ver design.md).
    return [
        checks.CheckResult(
            checks.STATUS_WARN,
            CODIGO_LINEAGE,
            "Lineage estructurado (datos→features→modelo) no está implementado todavía -- "
            "no se emite PASS hasta que exista un mecanismo real. " + detalle,
        )
    ]


def check_artifacts(repo_root: Path, project_stage: Optional[str]) -> list:
    """(repo_root, project_stage) -> [checks.CheckResult]."""
    motivo_na = _na_por_stage(project_stage)
    if motivo_na is not None:
        return [checks.CheckResult(checks.STATUS_NA, CODIGO_ARTIFACTS, motivo_na)]

    repo_root = Path(repo_root)
    encontrados = []
    if _tiene_fingerprint_evidencia(repo_root):
        encontrados.append("profile(s) en .harmessi/profiles/")
    if _dir_con_contenido(repo_root, "models"):
        encontrados.append("models/ con contenido")
    if _dir_con_contenido(repo_root, "reports"):
        encontrados.append("reports/ con contenido")

    if encontrados:
        return [
            checks.CheckResult(
                checks.STATUS_PASS, CODIGO_ARTIFACTS, "Artifacts identificados: " + ", ".join(encontrados) + "."
            )
        ]
    return [
        checks.CheckResult(
            checks.STATUS_WARN,
            CODIGO_ARTIFACTS,
            "Ningún artifact identificado todavía (ni profile, ni models/, ni reports/ con contenido).",
        )
    ]


def evaluar_foundations(repo_root: Path) -> list:
    """Read-only. Nunca escribe openspec/lifecycle/state.json ni
    .harmessi/project.json. Devuelve [resultado_project_stage,
    reproducibilidad, versionado, lineage, artifacts], en ese orden."""
    repo_root = Path(repo_root)
    try:
        ruta_project = maturity.state_path(repo_root)
        if not ruta_project.exists():
            project_stage = None
            resultado_stage = checks.CheckResult(
                checks.STATUS_NA,
                CODIGO_PROJECT_STAGE,
                ".harmessi/project.json no existe todavía -- correr 'ds_guard project init'.",
            )
        else:
            estado_project = maturity.leer_estado(ruta_project)
            project_stage = estado_project["project_stage"]
            resultado_stage = checks.CheckResult(
                checks.STATUS_PASS,
                CODIGO_PROJECT_STAGE,
                f"project_stage resuelto: {project_stage}",
                subject=project_stage,
            )
    except Exception as exc:  # noqa: BLE001 - project.json corrupto u otro fallo inesperado
        project_stage = None
        resultado_stage = checks.resultado_de_excepcion(CODIGO_PROJECT_STAGE, exc)

    registros = [
        (CODIGO_REPRODUCIBILIDAD, check_reproducibilidad, (repo_root, project_stage)),
        (CODIGO_VERSIONADO, check_versionado, (repo_root, project_stage)),
        (CODIGO_LINEAGE, check_lineage, (repo_root, project_stage)),
        (CODIGO_ARTIFACTS, check_artifacts, (repo_root, project_stage)),
    ]

    return [resultado_stage] + checks.ejecutar_checks(registros)


def registrar_evidencia(repo_root: Path, resultados: list) -> dict:
    """Operación EXPLÍCITA -- nunca llamada por evaluar_foundations. Agrega
    un snapshot {tipo: "check_snapshot", status, kind, message, utc} a
    mlops.foundations.<capability>.evidencia para cada resultado
    reconocido (ignora MLOPS-FOUNDATIONS-PROJECT-STAGE, que no tiene slot
    en mlops.foundations). NUNCA toca 'estado'. Requiere que
    openspec/lifecycle/state.json ya exista -- no lo crea (propaga
    FileNotFoundError/LifecycleEstadoError tal cual)."""
    repo_root = Path(repo_root)
    estado = lifecycle.leer_estado(lifecycle.state_path(repo_root))
    ahora = ahora_utc()
    capacidades_actualizadas = []
    for r in resultados:
        capability = _capability_de_codigo(r.code)
        if capability is None:
            continue
        entrada = estado["mlops"]["foundations"][capability]
        entrada.setdefault("evidencia", []).append(
            {"tipo": "check_snapshot", "status": r.status, "kind": r.kind, "message": r.message, "utc": ahora}
        )
        entrada["actualizado_utc"] = ahora
        capacidades_actualizadas.append(capability)
    lifecycle.escribir_estado(repo_root, estado)
    return {"registrado": True, "capacidades_actualizadas": capacidades_actualizadas}

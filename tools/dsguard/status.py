"""Superficie unificada de status de proyecto (Change 8, v0.3:
20260915-unified-status-surface): `evaluar_status(repo_root)` consolida, de
solo lectura, las fuentes de verdad YA existentes -- `.harmessi/project.json`
(`maturity.py`), `.ds_init/control.json` (JSON plano), `openspec/lifecycle/
state.json` (`lifecycle.py`), el motor de checks/foundations/readiness/
evidence (`checks.py`/`mlops_foundations.py`/`readiness.py`/
`mlops_evidence.py`) -- sin crear un nuevo estado persistido ni un segundo
engine de evaluacion (ver `proposal.md`/`design.md` del change).

Principios NO negociables (ver `design.md`):
  1. Solo lectura, siempre. Nunca llama `escribir_estado`/`agregar_evidencia`/
     `calibrar`/`promote`/`set_risk`/`project_init`/`lifecycle_init`.
  2. Nunca lanza una excepcion no controlada desde `evaluar_status` bajo
     ningun escenario de ausencia/corrupcion/import faltante -- cada
     sub-seccion maneja sus propios errores de dominio, y el orquestador
     envuelve cada llamada con una red de seguridad adicional.
  3. Solo depende INCONDICIONALMENTE de modulos que viajan con cualquier
     instalacion (`tools/dsguard/*`, siempre CORE_DISCOVERY). Las dos piezas
     que viven fuera de `tools/dsguard` (`harmessi.doctor.ejecutar` y
     `ds_init.legacy.inferir_installation_stage`) se consumen EXCLUSIVAMENTE
     via import perezoso opcional, nunca un import de modulo a nivel de
     archivo -- para que este modulo siga siendo importable desde un
     proyecto instalado donde esos paquetes no existen (ni `tools/harmessi/`
     ni `tools/ds_init/` se instalan en un destino, ver `proposal.md
     § Evidencia`).

Este modulo es "experimental/interno" (R14 de `spec.md`): la forma del dict
que devuelve `evaluar_status`/`formatear_json` no tiene garantia de
estabilidad de schema todavia.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from . import checks, lifecycle, maturity, mlops_evidence, mlops_foundations, readiness

# --- next_target (R3) -- funcion pura, nunca persistida -----------------------

# Tabla de sucesion propia (mismo vocabulario que `readiness._SECUENCIA`, pero
# sin importar ese simbolo privado -- ver design.md punto 5).
_SECUENCIA_STAGES: dict = {
    "discovery": "experiment",
    "experiment": "production_candidate",
    "production_candidate": "production",
}


def next_target(project_stage: Optional[str]) -> Optional[str]:
    """`discovery->experiment`, `experiment->production_candidate`,
    `production_candidate->production`, `production->None` (y `None ->
    None` para cualquier stage desconocido/no inicializado). Pura, sin I/O,
    nunca escrita a ningun archivo."""
    return _SECUENCIA_STAGES.get(project_stage)


_K_PRINCIPALES_HARNESS = 5


# --- Imports perezosos opcionales (design.md punto 2) --------------------------

def _importar_doctor():
    """`tools.harmessi.doctor`, via import perezoso opcional. Prueba ambas
    formas de import segun el contexto de invocacion (`tools/` en sys.path,
    invocacion real via `ds_guard.py`; o raiz del repo en sys.path, tests
    bajo `tools.tests`/`tools.harmessi.tests`) -- nunca un import de modulo a
    nivel de archivo de este archivo. Devuelve `None` si no esta disponible
    en ninguna forma, nunca deja escapar una excepcion."""
    try:
        from harmessi import doctor as doctor_mod  # type: ignore
        return doctor_mod
    except Exception:  # noqa: BLE001 - degradacion con gracia, nunca excepcion cruda
        pass
    try:
        from tools.harmessi import doctor as doctor_mod  # type: ignore
        return doctor_mod
    except Exception:  # noqa: BLE001
        return None


def _importar_legacy():
    """`tools.ds_init.legacy`, mismo criterio que `_importar_doctor`."""
    try:
        from ds_init import legacy as legacy_mod  # type: ignore
        return legacy_mod
    except Exception:  # noqa: BLE001
        pass
    try:
        from tools.ds_init import legacy as legacy_mod  # type: ignore
        return legacy_mod
    except Exception:  # noqa: BLE001
        return None


# --- Secciones privadas ---------------------------------------------------------

def _seccion_project(repo_root: Path) -> dict:
    """Reusa `maturity.leer_estado`/`maturity.estado_riesgo` (R13)."""
    ruta = maturity.state_path(repo_root)
    if not ruta.exists():
        return {
            "disponible": False,
            "tecnico": False,
            "project_stage": None,
            "risk_level": None,
            "risk_status": "unclassified",
            "mensaje": (
                "uninitialized -- .harmessi/project.json no existe todavia "
                "(correr 'ds_guard project init')."
            ),
        }
    try:
        estado = maturity.leer_estado(ruta)
    except maturity.MaturityEstadoError as exc:
        return {
            "disponible": False,
            "tecnico": True,
            "project_stage": None,
            "risk_level": None,
            "risk_status": "unclassified",
            "mensaje": f".harmessi/project.json existe pero no es valido: {exc}",
        }
    return {
        "disponible": True,
        "tecnico": False,
        "project_stage": estado["project_stage"],
        "risk_level": estado.get("risk_level"),
        "risk_status": maturity.estado_riesgo(estado),
        "mensaje": None,
    }


def _seccion_installation(repo_root: Path) -> dict:
    """`json.load()` plano de `.ds_init/control.json` (sin depender de
    `tools.ds_init`); si `installation_stage` esta ausente, intenta
    inferencia legacy via import perezoso opcional (R5)."""
    ruta = repo_root / ".ds_init" / "control.json"
    if not ruta.exists():
        return {
            "disponible": False,
            "tecnico": False,
            "installation_stage": None,
            "origen": "desconocido",
            "mensaje": (
                "unknown -- .ds_init/control.json no existe (proyecto no instalado via "
                "ds_init, o instalacion anterior a Change 7)."
            ),
        }
    try:
        with open(ruta, "r", encoding="utf-8") as f:
            control_data = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        return {
            "disponible": False,
            "tecnico": True,
            "installation_stage": None,
            "origen": "desconocido",
            "mensaje": f".ds_init/control.json existe pero no es valido: {exc}",
        }
    if not isinstance(control_data, dict):
        return {
            "disponible": False,
            "tecnico": True,
            "installation_stage": None,
            "origen": "desconocido",
            "mensaje": ".ds_init/control.json existe pero no es un objeto JSON valido.",
        }

    stage_declarado = control_data.get("installation_stage")
    if stage_declarado is not None:
        return {
            "disponible": True,
            "tecnico": False,
            "installation_stage": stage_declarado,
            "origen": "declarado",
            "mensaje": None,
        }

    # Sin installation_stage explicito -- inferencia legacy opcional.
    perfil = control_data.get("perfil")
    legacy_mod = _importar_legacy()
    if legacy_mod is None or not perfil:
        return {
            "disponible": False,
            "tecnico": False,
            "installation_stage": None,
            "origen": "desconocido",
            "mensaje": (
                "installation_stage no declarado y no se pudo inferir (tools.ds_init no "
                "disponible en este arbol, o 'perfil' ausente en control.json)."
            ),
        }
    try:
        stage_inferido = legacy_mod.inferir_installation_stage(repo_root, perfil)
    except Exception as exc:  # noqa: BLE001 - inferencia opcional, nunca excepcion cruda
        return {
            "disponible": False,
            "tecnico": False,
            "installation_stage": None,
            "origen": "desconocido",
            "mensaje": f"no se pudo inferir installation_stage: {exc!r}",
        }
    return {
        "disponible": True,
        "tecnico": False,
        "installation_stage": stage_inferido,
        "origen": "inferido",
        "mensaje": None,
    }


def _seccion_alignment(project_stage: Optional[str], installation_stage: Optional[str]) -> dict:
    """`aligned`/`sync_needed`/`ahead`/`unknown` segun R5 de `spec.md`."""
    if (
        project_stage is None
        or installation_stage is None
        or project_stage not in maturity.PROJECT_STAGES
        or installation_stage not in maturity.PROJECT_STAGES
    ):
        return {
            "estado": "unknown",
            "mensaje": "no se puede determinar alignment: project_stage o installation_stage desconocido.",
        }

    idx_project = maturity.PROJECT_STAGES.index(project_stage)
    idx_install = maturity.PROJECT_STAGES.index(installation_stage)
    if idx_project == idx_install:
        return {"estado": "aligned", "mensaje": None}
    if idx_project > idx_install:
        return {
            "estado": "sync_needed",
            "mensaje": f"correr 'ds_init sync --stage {project_stage} --execute' para sincronizar la instalacion.",
        }
    return {
        "estado": "ahead",
        "mensaje": "installation_stage esta por delante de project_stage (permitido, no es un error).",
    }


def _seccion_lifecycle(repo_root: Path) -> dict:
    """Reusa `lifecycle.leer_estado`; resumen de 8 fases CRISP-DM y 5 pasos
    KDD canonicos (R7)."""
    ruta = lifecycle.state_path(repo_root)
    if not ruta.exists():
        return {
            "disponible": False,
            "tecnico": False,
            "mensaje": "lifecycle unavailable -- correr 'ds_guard lifecycle migrate' o inicializar el lifecycle.",
            "crispdm": None,
            "kdd": None,
        }
    try:
        estado = lifecycle.leer_estado(ruta)
    except lifecycle.LifecycleEstadoError as exc:
        return {
            "disponible": False,
            "tecnico": True,
            "mensaje": f"openspec/lifecycle/state.json existe pero no es valido: {exc}",
            "crispdm": None,
            "kdd": None,
        }

    crispdm_fases = {}
    cerradas = 0
    for fase in lifecycle.FASES_CRISPDM:
        entrada = estado["crispdm"]["fases"][fase]
        cerrada = entrada["estado"] == "cerrada"
        cerradas += 1 if cerrada else 0
        crispdm_fases[fase] = {"estado": entrada["estado"], "cerrada": cerrada}

    kdd_pasos = {}
    cerrados_kdd = 0
    for paso in lifecycle.PASOS_KDD:
        entrada = estado["kdd"]["pasos"][paso]
        cerrado = entrada["estado"] == "cerrada"
        cerrados_kdd += 1 if cerrado else 0
        kdd_pasos[paso] = {"estado": entrada["estado"], "cerrada": cerrado}

    return {
        "disponible": True,
        "tecnico": False,
        "mensaje": None,
        "crispdm": {"fases": crispdm_fases, "resumen": f"{cerradas}/{len(lifecycle.FASES_CRISPDM)} closed"},
        "kdd": {"pasos": kdd_pasos, "resumen": f"{cerrados_kdd}/{len(lifecycle.PASOS_KDD)} closed"},
    }


def _seccion_mlops_foundations(repo_root: Path) -> list:
    """Reusa `mlops_foundations.evaluar_foundations` tal cual, sin
    reinterpretar severidad (R8). Omite el primer resultado
    (`MLOPS-FOUNDATIONS-PROJECT-STAGE`, informativo, ya cubierto por la
    seccion `project`) -- devuelve exactamente los 4 restantes."""
    resultados = mlops_foundations.evaluar_foundations(repo_root)
    return [r.to_dict() for r in resultados[1:]]


def _seccion_mlops_evidencia(repo_root: Path, tier: str, capabilities: tuple) -> list:
    """Por cada capability, `mlops_evidence.evidencia_valida` (R9). Nunca
    llama `agregar_evidencia`. Degrada con gracia si el lifecycle no esta
    disponible (propaga `FileNotFoundError`/`LifecycleEstadoError`)."""
    resultado = []
    for cap in capabilities:
        try:
            valido, detalle = mlops_evidence.evidencia_valida(repo_root, tier, cap)
        except (FileNotFoundError, lifecycle.LifecycleEstadoError) as exc:
            resultado.append(
                {"capability": cap, "valido": False, "detalle": f"no se pudo evaluar evidencia: {exc}"}
            )
            continue
        resultado.append({"capability": cap, "valido": valido, "detalle": detalle})
    return resultado


def _bloque_mlops_tier(repo_root: Path, tier: str, capabilities: tuple, aplicable: bool, motivo: Optional[str]) -> dict:
    """Un bloque de `mlops.production_readiness`/`mlops.operations` (R10):
    si `aplicable`, evalua las capacidades de verdad; si no, nunca las
    evalua una por una (ahorra el costo de `evidencia_valida`, ver
    design.md § Riesgos) -- solo devuelve el inventario de nombres con
    `aplicable=False`. La decision de listarlas una por una o resumirlas es
    de `formatear_texto` (presentacion), nunca de esta funcion (dato)."""
    if aplicable:
        return {"aplicable": True, "mensaje": None, "capacidades": _seccion_mlops_evidencia(repo_root, tier, capabilities)}
    return {
        "aplicable": False,
        "mensaje": motivo,
        "capacidades": [{"capability": cap, "aplicable": False} for cap in capabilities],
    }


def _seccion_mlops(repo_root: Path, project_stage: Optional[str]) -> dict:
    """`foundations` (4 CheckResult, R8), `production_readiness` (5
    capabilities), `operations` (7 capabilities) -- proporcionalidad por
    stage segun R10 (nunca afecta a `readiness.evaluar_readiness`, design.md
    punto 6)."""
    foundations = _seccion_mlops_foundations(repo_root)

    cap_prod = lifecycle.MLOPS_CAPACIDADES["production_readiness"]
    cap_ops = lifecycle.MLOPS_CAPACIDADES["operations"]

    if project_stage in (None, "discovery"):
        production_readiness = _bloque_mlops_tier(
            repo_root, "production_readiness", cap_prod, False, "not applicable at current stage"
        )
        operations = _bloque_mlops_tier(repo_root, "operations", cap_ops, False, "not applicable at current stage")
    elif project_stage == "experiment":
        production_readiness = _bloque_mlops_tier(repo_root, "production_readiness", cap_prod, True, None)
        operations = _bloque_mlops_tier(repo_root, "operations", cap_ops, False, "future")
    else:  # production_candidate, production
        production_readiness = _bloque_mlops_tier(repo_root, "production_readiness", cap_prod, True, None)
        operations = _bloque_mlops_tier(repo_root, "operations", cap_ops, True, None)

    return {
        "foundations": foundations,
        "production_readiness": production_readiness,
        "operations": operations,
    }


def _seccion_readiness(repo_root: Path, project_stage: Optional[str]) -> dict:
    """`next_target`; si `None`, mensaje de stage final (o de stage
    desconocido); si no, `readiness.evaluar_readiness` sin reimplementar
    (R4)."""
    target = next_target(project_stage)
    if target is None:
        if project_stage == "production":
            status_txt, resumen, mensaje = "none", "N/A", "production ya es el stage final -- no existe proximo target normal."
        else:
            status_txt, resumen, mensaje = (
                "none",
                "N/A",
                "no se puede determinar next_target: project_stage desconocido o no inicializado.",
            )
        return {
            "next_target": None,
            "status": status_txt,
            "resumen": resumen,
            "mensaje": mensaje,
            "ready": None,
            "technical_error": False,
            "blocking": [],
            "warnings": [],
        }

    resultados = readiness.evaluar_readiness(repo_root, target)
    ready = not checks.hay_bloqueo(resultados)
    technical_error = any(r.kind == checks.KIND_TECHNICAL_ERROR for r in resultados)
    blocking = [r.to_dict() for r in resultados if r.status == checks.STATUS_FAIL]
    warnings_list = [r.to_dict() for r in resultados if r.status == checks.STATUS_WARN]

    if technical_error:
        status_txt, resumen = "technical_error", "TECHNICAL ERROR"
    elif ready:
        status_txt, resumen = "ready", "READY"
    else:
        status_txt, resumen = "not_ready", "NOT READY"

    return {
        "next_target": target,
        "status": status_txt,
        "resumen": resumen,
        "mensaje": None,
        "ready": ready,
        "technical_error": technical_error,
        "blocking": blocking,
        "warnings": warnings_list,
    }


def _seccion_harness(repo_root: Path) -> dict:
    """`disponible: bool` solo si `tools.harmessi.doctor` puede importarse Y
    `doctor.ejecutar(repo_root)` corre sin excepcion (R11). Nunca copia
    logica de Doctor -- solo reduce su salida a un resumen."""
    try:
        doctor_mod = _importar_doctor()
    except Exception:  # noqa: BLE001 - red de seguridad adicional
        doctor_mod = None

    if doctor_mod is None:
        return {
            "disponible": False,
            "motivo": (
                "doctor no disponible en este arbol -- correr 'harmessi doctor' desde el "
                "checkout fuente de Harmessi para diagnostico completo."
            ),
        }

    try:
        resultados, _exit_code = doctor_mod.ejecutar(repo_root)
    except Exception as exc:  # noqa: BLE001 - nunca una excepcion cruda
        return {
            "disponible": False,
            "motivo": f"doctor esta disponible pero fallo al ejecutarse: {exc!r}",
        }

    conteos = {"ok": 0, "warn": 0, "error": 0, "na": 0}
    principales = []
    for r in resultados:
        if r.nivel == doctor_mod.NIVEL_OK:
            conteos["ok"] += 1
        elif r.nivel == doctor_mod.NIVEL_WARN:
            conteos["warn"] += 1
            principales.append(f"[WARN] {r.codigo}: {r.mensaje}")
        elif r.nivel == doctor_mod.NIVEL_ERROR:
            conteos["error"] += 1
            principales.append(f"[ERROR] {r.codigo}: {r.mensaje}")
        else:
            conteos["na"] += 1

    return {
        "disponible": True,
        "ok": conteos["ok"],
        "warn": conteos["warn"],
        "error": conteos["error"],
        "na": conteos["na"],
        "principales": principales,
    }


# --- Orquestador ------------------------------------------------------------

def _envolver(nombre: str, funcion, *args) -> dict:
    """Red de seguridad adicional (R13): ninguna seccion individual deberia
    lanzar (cada una maneja sus propios errores de dominio), pero
    `evaluar_status` nunca debe propagar una excepcion no controlada bajo
    ningun escenario -- esta envoltura es el ultimo resguardo."""
    try:
        return funcion(*args)
    except Exception as exc:  # noqa: BLE001 - ultimo resguardo de evaluar_status
        return {
            "disponible": False,
            "tecnico": True,
            "mensaje": f"error inesperado evaluando la seccion '{nombre}': {exc!r}",
        }


def evaluar_status(repo_root) -> dict:
    """Orquesta las 7 secciones (`project`, `installation`, `alignment`,
    `lifecycle`, `mlops`, `readiness`, `harness`), siempre de solo lectura,
    nunca lanza una excepcion no controlada. Determinista: mismo estado de
    disco -> mismo resultado (R14)."""
    repo_root = Path(repo_root)

    project = _envolver("project", _seccion_project, repo_root)
    project_stage = project.get("project_stage") if isinstance(project, dict) else None

    installation = _envolver("installation", _seccion_installation, repo_root)
    installation_stage = installation.get("installation_stage") if isinstance(installation, dict) else None

    alignment = _envolver("alignment", _seccion_alignment, project_stage, installation_stage)
    lifecycle_sec = _envolver("lifecycle", _seccion_lifecycle, repo_root)
    mlops = _envolver("mlops", _seccion_mlops, repo_root, project_stage)
    readiness_sec = _envolver("readiness", _seccion_readiness, repo_root, project_stage)
    harness = _envolver("harness", _seccion_harness, repo_root)

    return {
        "project": project,
        "installation": installation,
        "alignment": alignment,
        "lifecycle": lifecycle_sec,
        "mlops": mlops,
        "readiness": readiness_sec,
        "harness": harness,
    }


# --- Formateo -----------------------------------------------------------------

def _linea_capacidades(bloque: dict, verbose: bool) -> list:
    lineas = []
    if bloque.get("aplicable"):
        for cap in bloque.get("capacidades", []):
            marca = "OK" if cap.get("valido") else "--"
            lineas.append(f"    [{marca}] {cap['capability']}: {cap.get('detalle', '')}")
    else:
        capacidades = bloque.get("capacidades", [])
        if verbose:
            for cap in capacidades:
                lineas.append(f"    [n/a] {cap['capability']}")
        else:
            lineas.append(f"    ({len(capacidades)} capabilities, {bloque.get('mensaje', 'not applicable')})")
    return lineas


def formatear_texto(status: dict, verbose: bool = False) -> str:
    """Output humano compacto y jerarquico. Determinista, sin repetir el
    mismo hallazgo en dos secciones distintas de forma redundante."""
    lineas = ["=== Harmessi status (unificado) ==="]

    project = status.get("project", {})
    lineas.append("")
    lineas.append(
        f"Project: stage={project.get('project_stage')} risk={project.get('risk_level')} "
        f"({project.get('risk_status')})"
    )
    if project.get("mensaje"):
        lineas.append(f"  {project['mensaje']}")

    installation = status.get("installation", {})
    lineas.append(
        f"Installation: stage={installation.get('installation_stage')} origen={installation.get('origen')}"
    )
    if installation.get("mensaje"):
        lineas.append(f"  {installation['mensaje']}")

    alignment = status.get("alignment", {})
    lineas.append(f"Alignment: {alignment.get('estado')}")
    if alignment.get("mensaje"):
        lineas.append(f"  {alignment['mensaje']}")

    lifecycle_sec = status.get("lifecycle", {})
    if lifecycle_sec.get("disponible"):
        lineas.append(f"Lifecycle CRISP-DM: {lifecycle_sec['crispdm']['resumen']}")
        lineas.append(f"Lifecycle KDD: {lifecycle_sec['kdd']['resumen']}")
        if verbose:
            for fase, info in lifecycle_sec["crispdm"]["fases"].items():
                lineas.append(f"    [{'x' if info['cerrada'] else ' '}] {fase}: {info['estado']}")
    else:
        lineas.append(f"Lifecycle: no disponible -- {lifecycle_sec.get('mensaje')}")

    mlops = status.get("mlops", {})
    lineas.append("MLOps foundations:")
    for r in mlops.get("foundations", []):
        lineas.append(f"    [{r['status']}] {r['code']}: {r['message']}")
    lineas.append("MLOps production_readiness:")
    lineas.extend(_linea_capacidades(mlops.get("production_readiness", {}), verbose))
    lineas.append("MLOps operations:")
    lineas.extend(_linea_capacidades(mlops.get("operations", {}), verbose))

    readiness_sec = status.get("readiness", {})
    lineas.append(f"Readiness (next_target={readiness_sec.get('next_target')}): {readiness_sec.get('resumen')}")
    if readiness_sec.get("mensaje"):
        lineas.append(f"  {readiness_sec['mensaje']}")
    blocking = readiness_sec.get("blocking", [])
    if blocking:
        lineas.append("  Blocking:")
        limite = blocking if verbose else blocking[:5]
        for r in limite:
            lineas.append(f"    [{r['status']}] {r['code']}: {r['message']}")
    warnings_list = readiness_sec.get("warnings", [])
    if warnings_list and verbose:
        lineas.append("  Warnings:")
        for r in warnings_list:
            lineas.append(f"    [{r['status']}] {r['code']}: {r['message']}")

    harness = status.get("harness", {})
    if harness.get("disponible"):
        lineas.append(
            f"Harness: {harness['ok']} OK, {harness['warn']} WARN, {harness['error']} ERROR, {harness['na']} N/A"
        )
        principales = harness.get("principales", [])
        if principales:
            # R11 de spec.md: "nunca la lista completa de Doctor salvo
            # --verbose" -- mismo criterio que readiness.blocking arriba
            # (hallazgo de revision: este truncado faltaba, dejando pasar la
            # lista completa siempre en modo compacto).
            limite_harness = principales if verbose else principales[:_K_PRINCIPALES_HARNESS]
            for p in limite_harness:
                lineas.append(f"    {p}")
            recortados = len(principales) - len(limite_harness)
            if recortados > 0:
                lineas.append(f"    ... ({recortados} más, usar --verbose)")
    else:
        lineas.append(f"Harness: no disponible -- {harness.get('motivo')}")

    return "\n".join(lineas)


def formatear_json(status: dict) -> dict:
    """Dict serializable, determinista (`json.dumps` sin encoder custom).
    Experimental/interno -- ver docstring del modulo. Solo lectura, no muta
    `status`."""
    return status

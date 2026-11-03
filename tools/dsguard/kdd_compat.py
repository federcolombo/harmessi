"""Capa de compatibilidad legacy v0.2 -> lifecycle v0.3 (Change 2:
20260914-lifecycle-migration-and-kdd-repoint).

Conoce AMBAS ontologías: los 10 nombres legacy (antes en kdd.py, movidos
aca para evitar un import circular -- kdd_compat necesita el catalogo
legacy para el mapeo, y kdd.py necesita importar kdd_compat para delegarle
la logica; si el catalogo se quedaba en kdd.py, kdd_compat tendria que
importarlo y kdd.py importa kdd_compat -> ciclo. Ver design.md del change)
y el schema neutral de tools.dsguard.lifecycle. lifecycle.py no sabe que
este modulo existe (dependencia unidireccional: kdd_compat -> lifecycle).

kdd.py es el consumidor principal: expone la API publica estable que ven
ds_guard.py/dsguard/decision.py/los tests, delegando aca la traduccion, el
merge de convergencia, el roll-up y la migracion real. ds_guard.py tambien
importa este modulo directo para 'lifecycle migrate' (no pasa por kdd.py:
migrar no es una operacion legacy, es lo que hace nacer lifecycle/state.json).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from . import lifecycle
from .core import ahora_utc, Finding

# --- Catalogo legacy (movido desde kdd.py) --------------------------------

ETAPAS = (
    "problem_understanding", "data_understanding", "data_preparation",
    "feature_engineering", "modeling", "evaluation", "interpretation",
    "production_readiness", "deployment", "monitoring",
)
ETAPAS_FUTURAS = frozenset({"production_readiness", "deployment", "monitoring"})
ESTADOS_ETAPA_VALIDOS = frozenset({"no_iniciada", "en_progreso", "cerrada", "futura"})
ESTADOS_ETAPA_DESTINO_VALIDOS = frozenset({"no_iniciada", "en_progreso", "cerrada"})
_TRANSICIONES_VALIDAS_ETAPA = {
    "no_iniciada": {"en_progreso"},
    "en_progreso": {"cerrada"},
    "cerrada": {"en_progreso"},
}

# --- Mapeo legacy -> nuevo (tabla aprobada, ver spec.md) --------------------

MAPEO_LEGACY_A_CRISPDM = {
    "problem_understanding": "business_understanding",
    "data_understanding": "data_understanding",
    "data_preparation": "data_preparation",
    "feature_engineering": "data_preparation",
    "modeling": "modeling",
    "evaluation": "evaluation",
    "interpretation": "evaluation",
    "production_readiness": "production_readiness",
    "deployment": "deployment",
    "monitoring": "monitoring",
}
MAPEO_LEGACY_A_KDD = {
    "problem_understanding": None,
    "data_understanding": "selection",
    "data_preparation": "preprocessing",
    "feature_engineering": "transformation",
    "modeling": "data_mining",
    "evaluation": "interpretation_evaluation",
    "interpretation": "interpretation_evaluation",
    "production_readiness": None,
    "deployment": None,
    "monitoring": None,
}
# Solo referencia conceptual -- nunca se usa para auto-poblar una capacidad
# MLOps especifica (ver design.md).
MAPEO_LEGACY_A_MLOPS_TIER = {
    "production_readiness": "production_readiness",
    "deployment": "operations",
    "monitoring": "operations",
}


def traducir_etapa_legacy(etapa_legacy: str) -> tuple:
    """(fase_crispdm, paso_kdd_o_None)."""
    return MAPEO_LEGACY_A_CRISPDM[etapa_legacy], MAPEO_LEGACY_A_KDD[etapa_legacy]


class KddCompatError(Exception):
    """Legacy state.json corrupto/schema desconocida, o precondicion de
    migracion incumplida. Nunca se repara ni se sobreescribe."""


def state_path_legacy(repo_root: Path) -> Path:
    return Path(repo_root) / "openspec" / "kdd" / "state.json"


def leer_estado_legacy(path: Path) -> dict:
    """Lee y valida el state.json LEGACY (10 etapas). FileNotFoundError si
    no existe; KddCompatError si existe pero invalido. Nunca escribe."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"No existe {path}")
    with open(path, "r", encoding="utf-8") as f:
        try:
            datos = json.load(f)
        except json.JSONDecodeError as e:
            raise KddCompatError(f"{path} no es JSON valido: {e}")
    if not isinstance(datos, dict):
        raise KddCompatError(f"{path}: se esperaba un objeto JSON en la raiz")
    if datos.get("schema_version") != 1:
        raise KddCompatError(
            f"schema_version desconocida en {path}: {datos.get('schema_version')!r} (se esperaba 1)"
        )
    etapas = datos.get("etapas")
    if not isinstance(etapas, dict) or set(etapas.keys()) != set(ETAPAS):
        raise KddCompatError(f"{path}: 'etapas' debe tener exactamente las {len(ETAPAS)} etapas del catalogo legacy")
    for etapa, entrada in etapas.items():
        if not isinstance(entrada, dict) or entrada.get("estado") not in ESTADOS_ETAPA_VALIDOS:
            raise KddCompatError(f"{path}: etapa '{etapa}' con 'estado' ausente o invalido")
        if not isinstance(entrada.get("changes"), list) or not isinstance(entrada.get("evidencia"), list):
            raise KddCompatError(f"{path}: etapa '{etapa}' con 'changes'/'evidencia' invalidos")
    if not isinstance(datos.get("historial_transiciones"), list):
        raise KddCompatError(f"{path}: 'historial_transiciones' debe ser una lista")
    return datos


# --- Merge de convergencia (mismo target: evaluation+interpretation) -------

_ORDEN_ESTADO = {"no_iniciada": 0, "en_progreso": 1, "cerrada": 2}


def _mas_avanzado(a: str, b: str) -> str:
    return a if _ORDEN_ESTADO[a] >= _ORDEN_ESTADO[b] else b


def _combinar_entradas(entradas: list, ahora: str) -> dict:
    """Combina 1+ entradas legacy que convergen en el mismo target nuevo:
    estado = mas avanzado (futura se trata como no_iniciada a efectos de
    comparacion -- su valor original se preserva en provenance aparte);
    changes/evidencia = union deduplicada; actualizado_utc = el mas
    reciente. `entradas` nunca vacio."""
    estado_resultante = "no_iniciada"
    changes: list = []
    evidencia: list = []
    timestamps: list = []
    for entrada in entradas:
        estado_e = entrada["estado"]
        estado_comparable = "no_iniciada" if estado_e == "futura" else estado_e
        estado_resultante = _mas_avanzado(estado_resultante, estado_comparable)
        for cid in entrada.get("changes", []):
            if cid not in changes:
                changes.append(cid)
        for ev in entrada.get("evidencia", []):
            if not any(e.get("change_id") == ev.get("change_id") and e.get("artefacto") == ev.get("artefacto") for e in evidencia):
                evidencia.append(ev)
        if entrada.get("actualizado_utc"):
            timestamps.append(entrada["actualizado_utc"])
    return {
        "estado": estado_resultante,
        "changes": changes,
        "evidencia": evidencia,
        "actualizado_utc": max(timestamps) if timestamps else ahora,
    }


# --- Migracion --------------------------------------------------------------

def migrar_desde_legacy(repo_root: Path) -> dict:
    """dict con 'migrado': bool, y 'motivo' (si no migro) o 'estado' (si
    migro). Nunca toca el legacy. Idempotente: no-op si lifecycle ya existe
    y es valido. Fail-closed: propaga FileNotFoundError/KddCompatError/
    lifecycle.LifecycleEstadoError tal cual -- el llamador decide."""
    repo_root = Path(repo_root)
    ruta_lifecycle = lifecycle.state_path(repo_root)
    ruta_legacy = state_path_legacy(repo_root)

    if ruta_lifecycle.exists():
        lifecycle.leer_estado(ruta_lifecycle)  # valida; si esta corrupto, propaga (fail-closed, nunca cae a legacy)
        return {"migrado": False, "motivo": "openspec/lifecycle/state.json ya existe y es valido -- no-op"}

    if not ruta_legacy.exists():
        return {"migrado": False, "motivo": "no hay openspec/kdd/state.json ni openspec/lifecycle/state.json -- nada que migrar"}

    legacy = leer_estado_legacy(ruta_legacy)
    ahora = ahora_utc()

    etapas_legacy_provenance = {}
    for etapa in ETAPAS:
        entrada_legacy = legacy["etapas"][etapa]
        etapas_legacy_provenance[etapa] = {
            "estado_legacy": entrada_legacy["estado"],
            "mapeo_crispdm": MAPEO_LEGACY_A_CRISPDM[etapa],
            "mapeo_kdd": MAPEO_LEGACY_A_KDD[etapa],
            "mapeo_mlops_tier": MAPEO_LEGACY_A_MLOPS_TIER.get(etapa),
        }

    pasos_out = {}
    for paso in lifecycle.PASOS_KDD:
        fuentes = [e for e in ETAPAS if MAPEO_LEGACY_A_KDD[e] == paso]
        entradas = [legacy["etapas"][e] for e in fuentes]
        pasos_out[paso] = _combinar_entradas(entradas, ahora)

    fases_out = {}
    for fase in lifecycle.FASES_CRISPDM:
        pasos_de_la_fase = lifecycle.MAPEO_CRISPDM_A_KDD[fase]
        if pasos_de_la_fase:
            estados_pasos = [pasos_out[p]["estado"] for p in pasos_de_la_fase]
            fuentes = [e for e in ETAPAS if MAPEO_LEGACY_A_CRISPDM[e] == fase]
            combinado = _combinar_entradas([legacy["etapas"][e] for e in fuentes], ahora)
            fases_out[fase] = {
                "estado": lifecycle.calcular_estado_fase(estados_pasos),
                "changes": combinado["changes"],
                "evidencia": combinado["evidencia"],
                "actualizado_utc": combinado["actualizado_utc"],
            }
        else:
            fuentes = [e for e in ETAPAS if MAPEO_LEGACY_A_CRISPDM[e] == fase]
            entrada_legacy = legacy["etapas"][fuentes[0]]
            estado_legacy = entrada_legacy["estado"]
            fases_out[fase] = {
                "estado": "no_iniciada" if estado_legacy == "futura" else estado_legacy,
                "changes": list(entrada_legacy.get("changes", [])),
                "evidencia": list(entrada_legacy.get("evidencia", [])),
                "actualizado_utc": entrada_legacy.get("actualizado_utc") or ahora,
            }

    mlops_out = lifecycle.estado_inicial()["mlops"]  # nunca se auto-puebla desde legacy

    historial_out = []
    for entrada_hist in legacy.get("historial_transiciones", []):
        etapa_h = entrada_hist.get("etapa")
        hist_traducida = dict(entrada_hist)
        hist_traducida["etapa_legacy"] = etapa_h
        if etapa_h in MAPEO_LEGACY_A_CRISPDM:
            hist_traducida["fase_crispdm"] = MAPEO_LEGACY_A_CRISPDM[etapa_h]
            hist_traducida["paso_kdd"] = MAPEO_LEGACY_A_KDD[etapa_h]
        historial_out.append(hist_traducida)

    estado_nuevo = {
        "schema_version": lifecycle.SCHEMA_VERSION_SOPORTADA,
        "creado_utc": ahora,
        "migrado_desde": {
            "formato": "kdd_v1",
            "schema_version_origen": legacy.get("schema_version"),
            "utc": ahora,
            "creado_utc_legacy": legacy.get("creado_utc"),
            "etapas_legacy": etapas_legacy_provenance,
        },
        "crispdm": {"fases": fases_out},
        "kdd": {"pasos": pasos_out},
        "mlops": mlops_out,
        "historial_transiciones": historial_out,
    }
    lifecycle.escribir_estado(repo_root, estado_nuevo)
    return {"migrado": True, "estado": estado_nuevo}


# --- Operaciones repuntadas (usadas por kdd.py) -----------------------------

def _requerir_lifecycle_o_legacy_pendiente(repo_root: Path) -> dict:
    """Estado lifecycle vigente, o KddCompatError con mensaje claro si hay
    legacy sin migrar, o FileNotFoundError si no hay nada. Nunca auto-migra.
    lifecycle.LifecycleEstadoError se propaga tal cual si el lifecycle
    existe pero esta corrupto (fail-closed, nunca cae a legacy)."""
    ruta_lifecycle = lifecycle.state_path(repo_root)
    if ruta_lifecycle.exists():
        return lifecycle.leer_estado(ruta_lifecycle)
    if state_path_legacy(repo_root).exists():
        raise KddCompatError(
            "openspec/kdd/state.json (legacy) existe pero todavia no se migro. "
            "Correr 'ds_guard lifecycle migrate' primero."
        )
    raise FileNotFoundError(str(ruta_lifecycle))


def kdd_init(repo_root: Path):
    """(estado, creado: bool). Proyecto nuevo (sin legacy, sin lifecycle) ->
    lifecycle.lifecycle_init directo, nunca crea el legacy. Legacy sin
    migrar -> pide migrar (no auto-migra)."""
    repo_root = Path(repo_root)
    if not lifecycle.state_path(repo_root).exists() and state_path_legacy(repo_root).exists():
        raise KddCompatError(
            "openspec/kdd/state.json (legacy) existe pero todavia no se migro. "
            "Correr 'ds_guard lifecycle migrate' en vez de 'kdd init'."
        )
    return lifecycle.lifecycle_init(repo_root)


def kdd_status(repo_root: Path) -> dict:
    repo_root = Path(repo_root)
    estado = _requerir_lifecycle_o_legacy_pendiente(repo_root)
    etapas_out = {}
    for etapa in ETAPAS:
        fase, paso = traducir_etapa_legacy(etapa)
        entrada = estado["kdd"]["pasos"][paso] if paso else estado["crispdm"]["fases"][fase]
        etapas_out[etapa] = {
            "estado": entrada["estado"],
            "changes": list(entrada.get("changes", [])),
            "evidencia": list(entrada.get("evidencia", [])),
            "mapeo": {"fase_crispdm": fase, "paso_kdd": paso},
        }
    return {"schema_version": estado.get("schema_version"), "etapas": etapas_out}


def kdd_transition(repo_root: Path, etapa: str, hacia: str, motivo: Optional[str] = None):
    """(ok: bool, findings: list[Finding]). Aplica roll-up de la fase
    CRISP-DM cuando la etapa tiene paso KDD asociado."""
    repo_root = Path(repo_root)
    if etapa not in ETAPAS:
        return False, [Finding("KDD-ETAPA-DESCONOCIDA", f"Etapa KDD desconocida: {etapa}")]
    if hacia not in ESTADOS_ETAPA_DESTINO_VALIDOS:
        return False, [Finding("KDD-ETAPA-DESTINO-INVALIDO", f"Estado destino desconocido para una etapa KDD: {hacia}")]

    estado = _requerir_lifecycle_o_legacy_pendiente(repo_root)
    fase, paso = traducir_etapa_legacy(etapa)
    entrada_objetivo = estado["kdd"]["pasos"][paso] if paso is not None else estado["crispdm"]["fases"][fase]

    actual = entrada_objetivo["estado"]
    if hacia not in _TRANSICIONES_VALIDAS_ETAPA.get(actual, set()):
        return False, [Finding("KDD-TRANSICION-INVALIDA", f"Transicion invalida: {actual} -> {hacia}")]
    if hacia == "cerrada" and not entrada_objetivo.get("evidencia"):
        return False, [Finding("KDD-SIN-EVIDENCIA", f"La etapa '{etapa}' no tiene evidencia registrada todavia: no se puede cerrar")]

    ahora = ahora_utc()
    entrada_objetivo["estado"] = hacia
    entrada_objetivo["actualizado_utc"] = ahora

    if paso is not None:
        pasos_de_la_fase = lifecycle.MAPEO_CRISPDM_A_KDD[fase]
        estados_pasos = [estado["kdd"]["pasos"][p]["estado"] for p in pasos_de_la_fase]
        estado["crispdm"]["fases"][fase]["estado"] = lifecycle.calcular_estado_fase(estados_pasos)
        estado["crispdm"]["fases"][fase]["actualizado_utc"] = ahora

    hist_entry = {"utc": ahora, "etapa_legacy": etapa, "fase_crispdm": fase, "paso_kdd": paso, "desde": actual, "hacia": hacia}
    if motivo:
        hist_entry["motivo"] = motivo
    estado.setdefault("historial_transiciones", []).append(hist_entry)

    lifecycle.escribir_estado(repo_root, estado)
    return True, []


def etapas_declaradas(control: dict) -> list:
    kdd_decl = control.get("kdd") or {}
    etapas = []
    primaria = kdd_decl.get("etapa_primaria")
    if primaria:
        etapas.append(primaria)
    for e in kdd_decl.get("etapas_afectadas") or []:
        if e not in etapas:
            etapas.append(e)
    return etapas


def validar_antes_de_cerrar(repo_root: Path, control: dict) -> list:
    etapas = etapas_declaradas(control)
    if not etapas:
        return []
    repo_root = Path(repo_root)
    ruta_lifecycle = lifecycle.state_path(repo_root)
    if not ruta_lifecycle.exists():
        if state_path_legacy(repo_root).exists():
            return [Finding(
                "KDD-NO-INICIALIZADO",
                "El cambio declara etapa(s) KDD pero openspec/lifecycle/state.json no existe todavia "
                "(hay un openspec/kdd/state.json legacy sin migrar). Correr 'ds_guard lifecycle migrate'.",
                str(ruta_lifecycle),
            )]
        return [Finding(
            "KDD-NO-INICIALIZADO",
            "El cambio declara etapa(s) KDD pero openspec/lifecycle/state.json no existe. "
            "Correr 'ds_guard kdd init' antes de cerrar.",
            str(ruta_lifecycle),
        )]
    try:
        lifecycle.leer_estado(ruta_lifecycle)
    except lifecycle.LifecycleEstadoError as e:
        return [Finding("KDD-ESTADO-CORRUPTO", str(e), str(ruta_lifecycle))]

    desconocidas = [e for e in etapas if e not in ETAPAS]
    if desconocidas:
        return [Finding("KDD-ETAPA-DESCONOCIDA", f"Etapa(s) KDD declaradas en control.json no reconocidas: {', '.join(desconocidas)}")]
    return []


def sync_al_cerrar(repo_root: Path, control: dict, change_id: str) -> dict:
    etapas = etapas_declaradas(control)
    if not etapas:
        return {"sincronizado": False, "motivo": "el cambio no declara etapa_primaria ni etapas_afectadas"}

    repo_root = Path(repo_root)
    estado = lifecycle.leer_estado(lifecycle.state_path(repo_root))

    modo = control.get("modo", "completo")
    artefacto = (
        f"openspec/changes/{change_id}/verification.md" if modo == "completo"
        else f"openspec/changes/{change_id}/tasks.md#Verificacion"
    )

    ahora = ahora_utc()
    actualizadas = []
    for etapa in etapas:
        if etapa not in ETAPAS:
            continue
        fase, paso = traducir_etapa_legacy(etapa)
        objetivos = [estado["crispdm"]["fases"][fase]]
        if paso is not None:
            objetivos.append(estado["kdd"]["pasos"][paso])
        for entrada in objetivos:
            cambios = entrada.setdefault("changes", [])
            if change_id not in cambios:
                cambios.append(change_id)
            evidencia = entrada.setdefault("evidencia", [])
            if not any(ev.get("change_id") == change_id for ev in evidencia):
                evidencia.append({"change_id": change_id, "artefacto": artefacto})
            entrada["actualizado_utc"] = ahora
        actualizadas.append(etapa)

    lifecycle.escribir_estado(repo_root, estado)
    return {"sincronizado": True, "etapas_actualizadas": actualizadas}

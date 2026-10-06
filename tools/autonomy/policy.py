"""Contrato de autonomia, parte policy (v0.8 Change 0, `20260928-project-autonomy-contract`).

Modulo puro: sin I/O; solo stdlib e `from . import core as autonomy_core`.

- `parse_autonomy_policy` (R8): parseo fail-closed del objeto `autonomy` de `guardrails.json`;
- `is_source_sealed` / `effective_source_access` / `sealed_coherence_findings` (R10);
- `resolve_methodological_decision` (R11, resolucion).

Nunca lanza por datos raros en el parseo. Sin prosa: codigos/claves estables.
Decisiones de interpretacion: con `autonomy` no vacio, `guardrails["version"]` es OBLIGATORIO
e int (bool excluido) en [2, POLICY_SCHEMA_VERSION]; ausente (=1), menor o invalido degrada a
supervised + `AUTONOMY-POLICY-VERSION`. Un `autonomy["version"]` anidado, si aparece, se valida igual.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping, Optional

from . import core as autonomy_core

PolicyFinding = autonomy_core.PolicyFinding

POLICY_SCHEMA_VERSION = 2
REQUIRED_GUARD_VERSION = 2

KEY_AUTONOMY = "autonomy"
KEY_MODE = "mode"
KEY_LIMITS = "limits"
KEY_SEALED = "sealed_sources"
KEY_ACCESS = "source_access"
KEY_VERSION = "version"
KEY_MAX_SESSIONS = "max_sessions"
KEY_MAX_MINUTES = "max_total_minutes"

# `budgets` es clave conocida (canónica, R1/R6 de 20261005-operational-autonomy-hardening):
# ya no se reporta como `unknown_key`; sus ejes de límites agregados se validan abajo y el
# resto de sus claves las valida `ds_guard._resolver_budgets`.
KEY_BUDGETS = "budgets"
_CLAVES_AUTONOMY = (KEY_MODE, KEY_LIMITS, KEY_SEALED, KEY_ACCESS, KEY_VERSION, KEY_BUDGETS)
_CLAVES_LIMITS = (KEY_MAX_SESSIONS, KEY_MAX_MINUTES)

DETAIL_SEALED_UNSEALED_HOLDOUT = "holdout_source_not_sealed"
DETAIL_SEALED_NO_HOLDOUT = "sealed_source_matches_no_holdout"
DETAIL_SOURCE_ID_NOT_CANONICAL = "source_id_not_canonical"


# ---------------------------------------------------------------------------
# Tipos
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SourceAccess:
    read: bool
    write: bool


@dataclass(frozen=True)
class AutonomyPolicy:
    mode: str
    declared_mode: str
    max_sessions: Optional[int]
    max_total_minutes: Optional[int]
    sealed_sources: tuple
    source_access: Mapping[str, tuple]
    sealed_unknown: bool = False


def _politica_supervisada(
    declared_mode: str = autonomy_core.DEFAULT_MODE,
    max_sessions: Optional[int] = None,
    max_total_minutes: Optional[int] = None,
    sealed: tuple = (),
    access: Optional[dict] = None,
    sealed_unknown: bool = False,
) -> AutonomyPolicy:
    return AutonomyPolicy(
        mode=autonomy_core.DEFAULT_MODE,
        declared_mode=declared_mode,
        max_sessions=max_sessions,
        max_total_minutes=max_total_minutes,
        sealed_sources=sealed,
        source_access=MappingProxyType(dict(access or {})),
        sealed_unknown=sealed_unknown,
    )


# ---------------------------------------------------------------------------
# Parseo (R8)
# ---------------------------------------------------------------------------


def _es_int(valor: Any) -> bool:
    return isinstance(valor, int) and not isinstance(valor, bool)


def _version_valida(valor: Any) -> bool:
    return _es_int(valor) and 1 <= valor <= POLICY_SCHEMA_VERSION


def _guard_soporta(guard_policy_version_max: Any) -> bool:
    return _es_int(guard_policy_version_max) and guard_policy_version_max >= REQUIRED_GUARD_VERSION


def _id_canonico(valor: Any) -> bool:
    return isinstance(valor, str) and bool(autonomy_core.is_valid_source_id(valor))


def _lista_sellos(valor: Any) -> tuple:
    """Devuelve (sellos_validos, bien_formado, detalle_si_mal_formado)."""
    if not isinstance(valor, (list, tuple)):
        return (), False, "invalid_sealed_sources"
    sellos = []
    detalle = ""
    for item in valor:
        if _id_canonico(item):
            if item not in sellos:
                sellos.append(item)
        else:
            detalle = DETAIL_SOURCE_ID_NOT_CANONICAL
    return tuple(sellos), detalle == "", detalle


def _parsear_acceso(valor: Any, hallazgos: list) -> tuple:
    """Devuelve (mapa, valido, sealed_unknown). Entradas invalidas quedan (False, False)."""
    if not isinstance(valor, dict):
        hallazgos.append(PolicyFinding(autonomy_core.CODE_POLICY_INVALID, KEY_ACCESS, "not_a_dict"))
        return {}, False, True
    mapa = {}
    valido = True
    desconocido = False
    for clave, entrada in valor.items():
        if not _id_canonico(clave):
            hallazgos.append(
                PolicyFinding(autonomy_core.CODE_POLICY_INVALID, KEY_ACCESS, DETAIL_SOURCE_ID_NOT_CANONICAL)
            )
            valido = False
            desconocido = True
            continue
        ruta = "%s.%s" % (KEY_ACCESS, clave)
        if (
            isinstance(entrada, dict)
            and isinstance(entrada.get("read"), bool)
            and isinstance(entrada.get("write"), bool)
        ):
            mapa[clave] = (entrada["read"], entrada["write"])
        else:
            hallazgos.append(PolicyFinding(autonomy_core.CODE_POLICY_INVALID, ruta, "invalid_access_entry"))
            mapa[clave] = (False, False)
            valido = False
    return mapa, valido, desconocido


def parse_autonomy_policy(guardrails: Any, guard_policy_version_max: Any):
    """Parsea la policy de autonomia. Devuelve `(AutonomyPolicy, list[PolicyFinding])`.

    Nunca lanza. Nunca devuelve `mode == "autonomous"` ante duda.
    """
    try:
        return _parsear(guardrails, guard_policy_version_max)
    except Exception:  # defensa final: fail-closed
        return (
            _politica_supervisada(sealed_unknown=True),
            [PolicyFinding(autonomy_core.CODE_POLICY_INVALID, "", "unexpected_input")],
        )


def _parsear(guardrails: Any, guard_max: Any):
    hallazgos: list = []
    if guardrails is None:
        return _politica_supervisada(), hallazgos
    if not isinstance(guardrails, dict):
        hallazgos.append(PolicyFinding(autonomy_core.CODE_POLICY_INVALID, "", "not_a_dict"))
        return _politica_supervisada(sealed_unknown=True), hallazgos
    if KEY_AUTONOMY not in guardrails:
        return _politica_supervisada(), hallazgos

    autonomia = guardrails[KEY_AUTONOMY]
    if autonomia is None or (isinstance(autonomia, dict) and not autonomia):
        return _politica_supervisada(), hallazgos
    if not isinstance(autonomia, dict):
        hallazgos.append(PolicyFinding(autonomy_core.CODE_POLICY_INVALID, KEY_AUTONOMY, "not_an_object"))
        return _politica_supervisada(sealed_unknown=True), hallazgos

    degradar = False

    # Versiones (R8 regla 3).
    # `version` de nivel superior OBLIGATORIO (ausente = 1 en pathguard) y >= 2.
    if KEY_VERSION not in guardrails:
        hallazgos.append(PolicyFinding(autonomy_core.CODE_POLICY_VERSION, KEY_VERSION, "missing_version"))
        degradar = True
    for ruta, contenedor in ((KEY_VERSION, guardrails), ("%s.%s" % (KEY_AUTONOMY, KEY_VERSION), autonomia)):
        clave = KEY_VERSION
        if clave in contenedor:
            version = contenedor[clave]
            if not _version_valida(version):
                hallazgos.append(PolicyFinding(autonomy_core.CODE_POLICY_VERSION, ruta, "unknown_version"))
                degradar = True
            elif version < POLICY_SCHEMA_VERSION:
                hallazgos.append(PolicyFinding(autonomy_core.CODE_POLICY_VERSION, ruta, "version_too_low"))
                degradar = True

    # Claves desconocidas: toleradas, sin efecto.
    for clave in sorted(k for k in autonomia if isinstance(k, str) and k not in _CLAVES_AUTONOMY):
        hallazgos.append(PolicyFinding(autonomy_core.CODE_POLICY_UNKNOWN_KEY, clave, "unknown_key"))
    if any(not isinstance(k, str) for k in autonomia):
        hallazgos.append(PolicyFinding(autonomy_core.CODE_POLICY_INVALID, KEY_AUTONOMY, "non_str_key"))
        degradar = True

    # Modo declarado.
    declarado = autonomy_core.DEFAULT_MODE
    if KEY_MODE in autonomia:
        valor_modo = autonomia[KEY_MODE]
        if isinstance(valor_modo, str) and valor_modo in autonomy_core.MODES:
            declarado = valor_modo
        else:
            hallazgos.append(PolicyFinding(autonomy_core.CODE_POLICY_INVALID, KEY_MODE, "invalid_mode"))
            degradar = True

    # Sellos.
    sellos: tuple = ()
    sellos_desconocidos = False
    declara_sellos = False
    if KEY_SEALED in autonomia:
        sellos, bien_formado, detalle_sellos = _lista_sellos(autonomia[KEY_SEALED])
        declara_sellos = (not bien_formado) or bool(sellos)
        if not bien_formado:
            sellos_desconocidos = True
            degradar = True
            hallazgos.append(PolicyFinding(autonomy_core.CODE_POLICY_INVALID, KEY_SEALED, detalle_sellos))

    # Acceso por fuente.
    acceso: dict = {}
    if KEY_ACCESS in autonomia:
        acceso, acceso_valido, acceso_desconocido = _parsear_acceso(autonomia[KEY_ACCESS], hallazgos)
        if not acceso_valido:
            degradar = True
        if acceso_desconocido:
            sellos_desconocidos = True

    # Limites.
    max_sesiones: Optional[int] = None
    max_minutos: Optional[int] = None
    limites_presentes = KEY_LIMITS in autonomia
    limites_dict = autonomia.get(KEY_LIMITS) if limites_presentes else None
    if limites_presentes and not isinstance(limites_dict, dict):
        hallazgos.append(PolicyFinding(autonomy_core.CODE_POLICY_INVALID, KEY_LIMITS, "not_a_dict"))
        degradar = True
        limites_dict = None
    limites_ok = True
    # `autonomy.budgets` (canónica) puede proveer los mismos dos ejes (R6):
    # `max_sessions` y `aggregate_minutes` (= `max_total_minutes`). Valor efectivo = mínimo.
    budgets_dict = autonomia.get(KEY_BUDGETS)
    if KEY_BUDGETS in autonomia and not isinstance(budgets_dict, dict):
        hallazgos.append(PolicyFinding(autonomy_core.CODE_POLICY_LIMITS, KEY_BUDGETS, "not_a_dict"))
        degradar = True
    if not isinstance(budgets_dict, dict):
        budgets_dict = {}
    claves_budgets = {KEY_MAX_SESSIONS: "max_sessions", KEY_MAX_MINUTES: "aggregate_minutes"}
    for clave in _CLAVES_LIMITS:
        ruta = "%s.%s" % (KEY_LIMITS, clave)
        clave_b = claves_budgets[clave]
        valor_limits = None
        valor_budgets = None
        invalido = False
        if isinstance(limites_dict, dict) and clave in limites_dict:
            valor = limites_dict[clave]
            if _es_int(valor) and valor > 0:
                valor_limits = valor
            else:
                hallazgos.append(PolicyFinding(autonomy_core.CODE_POLICY_LIMITS, ruta, "not_positive_int"))
                invalido = True
        if clave_b in budgets_dict:
            valor = budgets_dict[clave_b]
            if _es_int(valor) and valor > 0:
                valor_budgets = valor
            else:
                hallazgos.append(
                    PolicyFinding(autonomy_core.CODE_POLICY_LIMITS, "budgets.%s" % clave_b, "not_positive_int")
                )
                invalido = True
                degradar = True
        efectivos = [v for v in (valor_limits, valor_budgets) if v is not None]
        efectivo = min(efectivos) if efectivos else None
        if efectivo is not None:
            if clave == KEY_MAX_SESSIONS:
                max_sesiones = efectivo
            else:
                max_minutos = efectivo
        if invalido:
            limites_ok = False
        elif efectivo is None:
            limites_ok = False
            if declarado == "autonomous":
                hallazgos.append(PolicyFinding(autonomy_core.CODE_POLICY_LIMITS, ruta, "missing"))
    if isinstance(limites_dict, dict):
        for clave in sorted(k for k in limites_dict if isinstance(k, str) and k not in _CLAVES_LIMITS):
            hallazgos.append(
                PolicyFinding(autonomy_core.CODE_POLICY_UNKNOWN_KEY, "%s.%s" % (KEY_LIMITS, clave), "unknown_key")
            )
        # Un limite presente e invalido es siempre un tipo invalido (degrada aun en supervised).
        if any(
            k in limites_dict and not (_es_int(limites_dict[k]) and limites_dict[k] > 0)
            for k in _CLAVES_LIMITS
        ):
            degradar = True
    if declarado == "autonomous" and not limites_ok:
        degradar = True

    # Capacidad del guard (R8 regla 2).
    if (declarado == "autonomous" or declara_sellos) and not _guard_soporta(guard_max):
        hallazgos.append(PolicyFinding(autonomy_core.CODE_POLICY_UNSUPPORTED, KEY_AUTONOMY, "guard_version_insufficient"))
        degradar = True

    modo = "autonomous" if (declarado == "autonomous" and not degradar) else autonomy_core.DEFAULT_MODE
    politica = AutonomyPolicy(
        mode=modo,
        declared_mode=declarado,
        max_sessions=max_sesiones,
        max_total_minutes=max_minutos,
        sealed_sources=sellos,
        source_access=MappingProxyType(dict(acceso)),
        sealed_unknown=sellos_desconocidos,
    )
    return politica, hallazgos


# ---------------------------------------------------------------------------
# Permisos de fuente (R10)
# ---------------------------------------------------------------------------


def is_source_sealed(policy: AutonomyPolicy, source_id: Any) -> bool:
    if policy.sealed_unknown:
        return True
    if not _id_canonico(source_id):
        return True
    return source_id in policy.sealed_sources


def _normalizar_registro(registry_access: Any) -> Optional[tuple]:
    """(read, write) del registro; None si no hay registro; (False, False) si es invalido."""
    if registry_access is None:
        return None
    if isinstance(registry_access, SourceAccess):
        return (registry_access.read is True, registry_access.write is True)
    if isinstance(registry_access, (tuple, list)) and len(registry_access) == 2:
        return (registry_access[0] is True, registry_access[1] is True)
    if isinstance(registry_access, dict):
        return (registry_access.get("read") is True, registry_access.get("write") is True)
    return (False, False)


def effective_source_access(
    policy: AutonomyPolicy, source_id: Any, registry_access: Any = None
) -> SourceAccess:
    """Efectivo = maximo (policy) AND registro. El registro nunca amplia."""
    if is_source_sealed(policy, source_id):
        return SourceAccess(False, False)
    maximo = policy.source_access.get(source_id, (True, False))
    read, write = bool(maximo[0]), bool(maximo[1])
    registro = _normalizar_registro(registry_access)
    if registro is not None:
        read = read and registro[0]
        write = write and registro[1]
    return SourceAccess(read, write)


def sealed_coherence_findings(
    sealed_source_ids: Iterable[str],
    file_backed_sources: Mapping[str, str],
    holdout_patterns: Sequence[str],
    matcher: Callable[[str, Sequence[str]], bool],
) -> list:
    """Coherencia sellos vs holdouts. Fuentes selladas no file-backed no generan hallazgo."""
    ids_sellados = list(sealed_source_ids)
    patrones = list(holdout_patterns)
    hallazgos = []
    # Ids no canonicos: hallazgo en lugar de comparar (fail-closed).
    for source_id in sorted(
        [i for i in ids_sellados if not _id_canonico(i)]
        + [i for i in file_backed_sources if not _id_canonico(i)],
        key=repr,
    ):
        hallazgos.append(
            PolicyFinding(
                autonomy_core.CODE_POLICY_INVALID,
                source_id if isinstance(source_id, str) else "",
                DETAIL_SOURCE_ID_NOT_CANONICAL,
            )
        )
    sellados = set(i for i in ids_sellados if _id_canonico(i))
    for source_id in sorted(i for i in file_backed_sources if _id_canonico(i)):
        ruta = file_backed_sources[source_id]
        coincide = bool(matcher(ruta, patrones))
        if coincide and source_id not in sellados:
            hallazgos.append(
                PolicyFinding(autonomy_core.CODE_SEALED_UNSEALED_HOLDOUT, source_id, DETAIL_SEALED_UNSEALED_HOLDOUT)
            )
        elif not coincide and source_id in sellados:
            hallazgos.append(
                PolicyFinding(autonomy_core.CODE_SEALED_PATH_MISMATCH, source_id, DETAIL_SEALED_NO_HOLDOUT)
            )
    return hallazgos


# ---------------------------------------------------------------------------
# Resolucion de decisiones metodologicas (R11)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MethodologicalResolution:
    decision: autonomy_core.PolicyDecision
    approval_ref: Optional[autonomy_core.ApprovalRef]


def _tipo_de(item: Any) -> Any:
    if isinstance(item, autonomy_core.PreApprovedDecision):
        return item.decision_type
    if isinstance(item, dict):
        return item.get("decision_type")
    return None


def _ref_de(item: Any) -> Optional[autonomy_core.ApprovalRef]:
    if isinstance(item, autonomy_core.PreApprovedDecision):
        ref = item.approval_ref
        return ref if isinstance(ref, autonomy_core.ApprovalRef) else None
    try:
        return autonomy_core.ApprovalRef.from_dict(item["approval_ref"])
    except Exception:
        return None


def resolve_methodological_decision(
    mode: str, decision_type: Any, pre_approved: Any, known_types: Any
) -> MethodologicalResolution:
    """Listada + valida + tipo conocido -> continue_preapproved_decision; si no, STOP 2.

    Fail-closed ante ambiguedad: dos o mas decisiones validas del mismo `decision_type` con
    `approval_ref` distinto resuelven a STOP 2 (`approval_ref=None`); si son identicas no hay
    ambiguedad y continua.
    """
    no_listada = autonomy_core.resolve_action("decide_unlisted_methodological", mode)
    listada = autonomy_core.resolve_action("continue_preapproved_decision", mode)
    tipos = tuple(known_types) if known_types is not None else ()
    if not isinstance(decision_type, str) or decision_type not in tipos:
        return MethodologicalResolution(no_listada, None)
    items = pre_approved if isinstance(pre_approved, (list, tuple)) else ()
    refs = []
    for item in items:
        if _tipo_de(item) != decision_type:
            continue
        if autonomy_core.validate_pre_approved(item, tipos):
            continue
        ref = _ref_de(item)
        if ref is not None and ref not in refs:
            refs.append(ref)
    if len(refs) == 1:
        return MethodologicalResolution(listada, refs[0])
    return MethodologicalResolution(no_listada, None)

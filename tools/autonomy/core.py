"""Contrato de autonomia, parte core (v0.8 Change 0, `20260928-project-autonomy-contract`).

Modulo solo-stdlib (`dataclasses`, `typing`, `re`, `unicodedata`): sin I/O, sin
imports de `tools.*` ni de modulos hermanos. Declara como DATO:

- vocabulario de modos, ejecutores, aprobaciones y resultados (R2);
- `POLICY_TABLE` (clase de accion x modo) y `resolve_action` (R3);
- catalogos de STOP y LIMIT y el registro unico de codigos `AUTONOMY-*` (R4);
- roles y capacidades (R6) y la vista derivada `role_responsibilities` (R17);
- `PolicyApproval`, `ApprovalRef`, namespace reservado `policy:` (R7, R16, R18);
- `PreApprovedDecision` y su validacion (R11).

Sin prosa (R5): las constantes publicas son codigos/claves estables; los
hallazgos (`PolicyFinding`) llevan `code`, `path` y `detail_key`. El texto para
el usuario es responsabilidad del consumidor.

Este modulo NO consulta `control.json` ni ningun archivo (eso es del Change 3).
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Iterable, Optional

# ---------------------------------------------------------------------------
# Vocabulario (R2)
# ---------------------------------------------------------------------------

MODES = ("autonomous", "supervised")
DEFAULT_MODE = "supervised"
EXECUTORS = ("lead", "human", "lead_or_human")
APPROVALS = ("none", "policy", "human", "human_conditional")
OUTCOMES = ("proceed", "stop_human")

# ---------------------------------------------------------------------------
# Codigos estables (R4): registro unico `ALL_CODES`
# ---------------------------------------------------------------------------

TECHNICAL_ERROR_CODE = "AUTONOMY-TECHNICAL-ERROR"
CHECKPOINT_RESUMABLE = "checkpoint_resumable"

# STOP: (numero, clave). El codigo es `AUTONOMY-STOP-NN`.
_STOP_CLAVES = (
    (1, "sealed_access"),
    (2, "unlisted_methodological_decision"),
    (3, "leakage_doubt"),
    (4, "new_dependency"),
    (5, "write_outside_scope"),
    (6, "secret_required"),
    (7, "data_loss_risk"),
    (8, "remediation_exhausted"),
    (9, "approach_refuted"),
    (10, "requirement_contradiction"),
    (11, "scope_expansion"),
    (12, "bypass_needed"),
)

# Codigos usados por errores/validadores de este modulo y de `policy.py`.
CODE_UNKNOWN_ACTION_CLASS = "AUTONOMY-UNKNOWN-ACTION-CLASS"
CODE_UNKNOWN_MODE = "AUTONOMY-UNKNOWN-MODE"
CODE_UNKNOWN_ROLE = "AUTONOMY-UNKNOWN-ROLE"
CODE_POLICY_UNSUPPORTED = "AUTONOMY-POLICY-UNSUPPORTED"
CODE_POLICY_INVALID = "AUTONOMY-POLICY-INVALID"
CODE_POLICY_VERSION = "AUTONOMY-POLICY-VERSION"
CODE_POLICY_LIMITS = "AUTONOMY-POLICY-LIMITS"
CODE_POLICY_UNKNOWN_KEY = "AUTONOMY-POLICY-UNKNOWN-KEY"
CODE_SEALED_UNSEALED_HOLDOUT = "AUTONOMY-SEALED-UNSEALED-HOLDOUT"
CODE_SEALED_PATH_MISMATCH = "AUTONOMY-SEALED-PATH-MISMATCH"
CODE_APPROVAL_REF_INVALID = "AUTONOMY-APPROVAL-REF-INVALID"
CODE_APPROVAL_INVALID = "AUTONOMY-APPROVAL-INVALID"
CODE_POLICY_APPROVAL_INVALID = "AUTONOMY-POLICY-APPROVAL-INVALID"
CODE_PREAPPROVED_INVALID = "AUTONOMY-PREAPPROVED-INVALID"
CODE_IDENTITY_INVALID = "AUTONOMY-IDENTITY-INVALID"
CODE_IDENTITY_RESERVED = "AUTONOMY-IDENTITY-RESERVED"
CODE_LIMIT_SESSION_BUDGET = "AUTONOMY-LIMIT-SESSION-BUDGET"
CODE_LIMIT_AGGREGATE_BUDGET = "AUTONOMY-LIMIT-AGGREGATE-BUDGET"


@dataclass(frozen=True)
class StopEntry:
    """Una entrada del catalogo de STOP (numero 1-12, codigo, clave)."""

    number: int
    code: str
    key: str


@dataclass(frozen=True)
class LimitEntry:
    """Una entrada del catalogo de LIMIT: no es STOP, nunca pregunta al humano."""

    code: str
    key: str
    result: str


STOP_CATALOG = tuple(
    StopEntry(number=n, code="AUTONOMY-STOP-%02d" % n, key=k) for n, k in _STOP_CLAVES
)
LIMIT_CATALOG = (
    LimitEntry(
        code=CODE_LIMIT_SESSION_BUDGET, key="session_budget", result=CHECKPOINT_RESUMABLE
    ),
    LimitEntry(
        code=CODE_LIMIT_AGGREGATE_BUDGET, key="aggregate_budget", result=CHECKPOINT_RESUMABLE
    ),
)

ALL_CODES = (
    tuple(e.code for e in STOP_CATALOG)
    + tuple(e.code for e in LIMIT_CATALOG)
    + (
        TECHNICAL_ERROR_CODE,
        CODE_UNKNOWN_ACTION_CLASS,
        CODE_UNKNOWN_MODE,
        CODE_UNKNOWN_ROLE,
        CODE_POLICY_UNSUPPORTED,
        CODE_POLICY_INVALID,
        CODE_POLICY_VERSION,
        CODE_POLICY_LIMITS,
        CODE_POLICY_UNKNOWN_KEY,
        CODE_SEALED_UNSEALED_HOLDOUT,
        CODE_SEALED_PATH_MISMATCH,
        CODE_APPROVAL_REF_INVALID,
        CODE_APPROVAL_INVALID,
        CODE_POLICY_APPROVAL_INVALID,
        CODE_PREAPPROVED_INVALID,
        CODE_IDENTITY_INVALID,
        CODE_IDENTITY_RESERVED,
    )
)


def _stop_code(key: str) -> str:
    for entrada in STOP_CATALOG:
        if entrada.key == key:
            return entrada.code
    raise AutonomyError(TECHNICAL_ERROR_CODE, "stop_key_missing")


# ---------------------------------------------------------------------------
# Errores y hallazgos
# ---------------------------------------------------------------------------


class AutonomyError(ValueError):
    """Error de contrato de este modulo; lleva un `code` estable (`AUTONOMY-*`)."""

    def __init__(self, code: str, detail_key: str = "") -> None:
        self.code = code
        self.detail_key = detail_key
        super().__init__(code if not detail_key else "%s:%s" % (code, detail_key))


@dataclass(frozen=True)
class PolicyFinding:
    """Hallazgo de validacion: `code` (registro), `path` (clave) y `detail_key` estable."""

    code: str
    path: str
    detail_key: str


# ---------------------------------------------------------------------------
# Tabla de politica (R3)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PolicyDecision:
    action_class: str
    mode: str
    executor: str
    approval: str
    outcome: str
    stop_code: Optional[str] = None


# (clase, autonomous, supervised); cada modo es (executor, approval, outcome, stop_key|None)
_FILAS = (
    ("diagnostic_read",
     ("lead", "none", "proceed", None), ("lead", "none", "proceed", None)),
    ("execute_project_code",
     ("lead", "none", "proceed", None), ("lead_or_human", "human", "proceed", None)),
    ("approve_run_manifest",
     ("lead", "policy", "proceed", None), ("human", "human", "proceed", None)),
    ("approve_proposal",
     ("human", "human", "proceed", None), ("human", "human", "proceed", None)),
    ("continue_preapproved_decision",
     ("lead", "policy", "proceed", None), ("lead", "human", "proceed", None)),
    ("decide_unlisted_methodological",
     ("human", "human", "stop_human", "unlisted_methodological_decision"),
     ("human", "human", "stop_human", "unlisted_methodological_decision")),
    ("sdd_transition_post_approval",
     ("lead", "none", "proceed", None), ("lead", "human_conditional", "proceed", None)),
    ("corrective_reinvocation_in_window",
     ("lead", "none", "proceed", None), ("lead", "none", "proceed", None)),
    ("remediation_extend",
     ("human", "human", "stop_human", "remediation_exhausted"),
     ("human", "human", "stop_human", "remediation_exhausted")),
    ("session_open_close",
     ("lead", "policy", "proceed", None), ("lead", "human_conditional", "proceed", None)),
    ("access_sealed",
     ("human", "human", "stop_human", "sealed_access"),
     ("human", "human", "stop_human", "sealed_access")),
    ("provide_secret",
     ("human", "human", "stop_human", "secret_required"),
     ("human", "human", "stop_human", "secret_required")),
    ("install_dependency",
     ("human", "human", "stop_human", "new_dependency"),
     ("human", "human", "stop_human", "new_dependency")),
    ("write_outside_scope_or_source_or_raw",
     ("human", "human", "stop_human", "write_outside_scope"),
     ("human", "human", "stop_human", "write_outside_scope")),
    ("commit_tag_publish",
     ("human", "human", "proceed", None), ("human", "human", "proceed", None)),
)

ACTION_CLASSES = tuple(f[0] for f in _FILAS)


def _construir_tabla() -> dict:
    tabla = {}
    for clase, auto, sup in _FILAS:
        for modo, (ejecutor, aprobacion, resultado, stop_key) in (
            ("autonomous", auto),
            ("supervised", sup),
        ):
            tabla[(clase, modo)] = PolicyDecision(
                action_class=clase,
                mode=modo,
                executor=ejecutor,
                approval=aprobacion,
                outcome=resultado,
                stop_code=_stop_code(stop_key) if stop_key else None,
            )
    return tabla


POLICY_TABLE = _construir_tabla()


def resolve_action(action_class: str, mode: str) -> PolicyDecision:
    """Consulta pura de `POLICY_TABLE`. Clase o modo desconocido -> `AutonomyError`."""
    if not isinstance(action_class, str) or action_class not in ACTION_CLASSES:
        raise AutonomyError(CODE_UNKNOWN_ACTION_CLASS, "action_class")
    if not isinstance(mode, str) or mode not in MODES:
        raise AutonomyError(CODE_UNKNOWN_MODE, "mode")
    decision = POLICY_TABLE.get((action_class, mode))
    if decision is None:
        raise AutonomyError(CODE_UNKNOWN_ACTION_CLASS, "table_row_missing")
    return decision


def narrow_mode(current: Any, requested: Any) -> str:
    """Estrecha: solo `autonomous` + `autonomous` da `autonomous`; desconocido = supervised."""
    if current == "autonomous" and requested == "autonomous":
        return "autonomous"
    return "supervised"


# ---------------------------------------------------------------------------
# Roles (R6) y responsabilidades derivadas (R17)
# ---------------------------------------------------------------------------

ROLES = ("lead", "writer", "reviewer", "metodologo", "runner", "human")

ROLE_CAPABILITIES = {
    "lead": {"execute": True, "read_only": False, "write_files": False},
    "writer": {"execute": False, "read_only": False, "write_files": True},
    "reviewer": {"execute": False, "read_only": True, "write_files": False},
    "metodologo": {"execute": False, "read_only": True, "write_files": False},
    "runner": {"execute": True, "read_only": False, "write_files": False},
    "human": {"execute": True, "read_only": False, "write_files": False},
}

IMPLICATIONS = ("executes", "approves", "registers_policy", "stops")


def role_capabilities(role: str) -> dict:
    """Copia de las capacidades del rol (lee `ROLE_CAPABILITIES` en cada llamada)."""
    if not isinstance(role, str) or role not in ROLES:
        raise AutonomyError(CODE_UNKNOWN_ROLE, "role")
    caps = ROLE_CAPABILITIES.get(role)
    if caps is None:
        raise AutonomyError(CODE_UNKNOWN_ROLE, "capabilities_missing")
    return {k: caps[k] for k in sorted(caps)}


def _implicaciones(decision: PolicyDecision, role: str) -> tuple:
    """Implicaciones de `role` (lead|human) para una fila; en orden de `IMPLICATIONS`."""
    resultado = []
    if decision.executor == "lead_or_human" or decision.executor == role:
        resultado.append("executes")
    if role == "human" and decision.approval in ("human", "human_conditional"):
        resultado.append("approves")
    if role == "lead" and decision.approval == "policy":
        resultado.append("registers_policy")
    if role == "human" and decision.outcome == "stop_human":
        resultado.append("stops")
    return tuple(resultado)


def role_responsibilities(role: str, mode: str) -> dict:
    """Vista derivada (sin cache) de `ROLE_CAPABILITIES` + `POLICY_TABLE`.

    Devuelve `{"capabilities": {...}, "actions": {action_class: (implicaciones...)}}`.
    `actions` solo se completa para `lead` y `human`; para el resto es `{}`.
    """
    if not isinstance(role, str) or role not in ROLES:
        raise AutonomyError(CODE_UNKNOWN_ROLE, "role")
    if not isinstance(mode, str) or mode not in MODES:
        raise AutonomyError(CODE_UNKNOWN_MODE, "mode")
    acciones = {}
    if role in ("lead", "human"):
        for clase in ACTION_CLASSES:
            acciones[clase] = _implicaciones(resolve_action(clase, mode), role)
    return {"capabilities": role_capabilities(role), "actions": acciones}


# ---------------------------------------------------------------------------
# ApprovalRef (R16)
# ---------------------------------------------------------------------------

_RE_CHANGE_ID = re.compile(r"[0-9]{8}-[a-z0-9][a-z0-9-]*")
_RE_SHA256 = re.compile(r"[0-9a-f]{64}")
_RE_POLICY_ACTOR = re.compile(r"policy:[a-z0-9][a-z0-9_-]*")
_RE_DRIVE = re.compile(r"[A-Za-z]:")

# Formato estable de `source_id` (lo importa `policy.py`).
SOURCE_ID_PATTERN = r"[a-z0-9][a-z0-9_-]{0,63}"
_RE_SOURCE_ID = re.compile(SOURCE_ID_PATTERN)


def is_valid_source_id(value: Any) -> bool:
    """True solo si `value` es str y cumple `SOURCE_ID_PATTERN` completo."""
    return isinstance(value, str) and _RE_SOURCE_ID.fullmatch(value) is not None

_REF_CLAVES = ("artefacto", "change_id", "hash")


def _hallazgo_ref(path: str, detail: str) -> PolicyFinding:
    return PolicyFinding(CODE_APPROVAL_REF_INVALID, path, detail)


def _validar_ref(data: Any, prefijo: str = "") -> list:
    if not isinstance(data, dict):
        return [_hallazgo_ref(prefijo.rstrip("."), "not_a_dict")]
    hallazgos = []
    for clave in _REF_CLAVES:
        if clave not in data:
            hallazgos.append(_hallazgo_ref(prefijo + clave, "missing"))
    for clave in sorted(k for k in data if isinstance(k, str) and k not in _REF_CLAVES):
        hallazgos.append(_hallazgo_ref(prefijo + clave, "unknown_key"))
    if any(not isinstance(k, str) for k in data):
        hallazgos.append(_hallazgo_ref(prefijo.rstrip("."), "non_str_key"))
    cid = data.get("change_id")
    if "change_id" in data and not (
        isinstance(cid, str) and _RE_CHANGE_ID.fullmatch(cid)
    ):
        hallazgos.append(_hallazgo_ref(prefijo + "change_id", "invalid_format"))
    art = data.get("artefacto")
    if "artefacto" in data:
        if not isinstance(art, str) or not art.strip():
            hallazgos.append(_hallazgo_ref(prefijo + "artefacto", "empty_or_not_str"))
        elif art != art.strip() or art == "." or "/" in art or "\\" in art or ".." in art:
            hallazgos.append(_hallazgo_ref(prefijo + "artefacto", "not_relative_name"))
    h = data.get("hash")
    if "hash" in data and not (isinstance(h, str) and _RE_SHA256.fullmatch(h)):
        hallazgos.append(_hallazgo_ref(prefijo + "hash", "invalid_sha256"))
    return hallazgos


def validate_approval_ref(data: Any) -> list:
    """Hallazgos de una referencia de aprobacion (dict). No lanza por datos raros."""
    return _validar_ref(data)


@dataclass(frozen=True)
class ApprovalRef:
    """Referencia unica a una aprobacion humana (change_id, artefacto, hash sha256)."""

    change_id: str
    artefacto: str
    hash: str

    def to_dict(self) -> dict:
        return {"artefacto": self.artefacto, "change_id": self.change_id, "hash": self.hash}

    @classmethod
    def from_dict(cls, data: Any) -> "ApprovalRef":
        hallazgos = validate_approval_ref(data)
        if hallazgos:
            primero = hallazgos[0]
            raise AutonomyError(primero.code, "%s:%s" % (primero.path, primero.detail_key))
        return cls(change_id=data["change_id"], artefacto=data["artefacto"], hash=data["hash"])


# ---------------------------------------------------------------------------
# Namespace reservado `policy:` e identidad humana (R18)
# ---------------------------------------------------------------------------


def _es_formato(caracter: str) -> bool:
    return unicodedata.category(caracter) in ("Cf", "Cc")


def _sin_formato(texto: str) -> str:
    """Quita caracteres de formato/control (categorias Unicode `Cf` y `Cc`)."""
    return "".join(c for c in texto if not _es_formato(c))


def is_reserved_policy_namespace(value: Any) -> bool:
    """True si `value` (str) cae en el namespace `policy:` tras NFKC + strip + casefold."""
    if not isinstance(value, str):
        return False
    normalizado = _sin_formato(unicodedata.normalize("NFKC", value)).strip().casefold()
    return normalizado.startswith("policy:")


def is_policy_actor(approved_by: Any) -> bool:
    """True si `approved_by` tiene la forma canonica estricta `policy:<slug>`."""
    return isinstance(approved_by, str) and _RE_POLICY_ACTOR.fullmatch(approved_by) is not None


def validate_human_identity(usuario: Any) -> list:
    """Rechaza identidad vacia/no-str y toda identidad en el namespace `policy:`."""
    if not isinstance(usuario, str) or not _sin_formato(usuario).strip():
        return [PolicyFinding(CODE_IDENTITY_INVALID, "usuario", "empty_or_not_str")]
    if is_reserved_policy_namespace(usuario):
        return [PolicyFinding(CODE_IDENTITY_RESERVED, "usuario", "reserved_namespace")]
    if any(_es_formato(c) for c in usuario):
        return [PolicyFinding(CODE_IDENTITY_INVALID, "usuario", "non_printable")]
    return []


def validate_human_approval_entry(entry: Any) -> list:
    """Entrada humana: `usuario` valido (no reservado) y sin `approved_by`."""
    if not isinstance(entry, dict):
        return [PolicyFinding(CODE_APPROVAL_INVALID, "", "not_a_dict")]
    hallazgos = list(validate_human_identity(entry.get("usuario")))
    if "approved_by" in entry:
        hallazgos.append(PolicyFinding(CODE_APPROVAL_INVALID, "approved_by", "policy_field_in_human_entry"))
    return hallazgos


# ---------------------------------------------------------------------------
# PolicyApproval (R7, R19 i)
# ---------------------------------------------------------------------------


def policy_approval_classes() -> tuple:
    """Clases permitidas para `PolicyApproval`: fila con `approval == "policy"` en algun modo.

    Se calcula desde `POLICY_TABLE` en cada llamada (no hay lista a mano).
    """
    return tuple(
        clase
        for clase in ACTION_CLASSES
        if any(
            (clase, modo) in POLICY_TABLE and POLICY_TABLE[(clase, modo)].approval == "policy"
            for modo in MODES
        )
    )


_POLICY_APPROVAL_CLAVES = ("action_class", "approved_by", "human_approval_ref")


def validate_policy_approval(data: Any) -> list:
    """Hallazgos de una `PolicyApproval` en forma de dict. No lanza por datos raros."""
    if not isinstance(data, dict):
        return [PolicyFinding(CODE_POLICY_APPROVAL_INVALID, "", "not_a_dict")]
    hallazgos = []
    if "usuario" in data:
        hallazgos.append(PolicyFinding(CODE_POLICY_APPROVAL_INVALID, "usuario", "human_field_present"))
    for clave in sorted(k for k in data if isinstance(k, str)
                        and k not in _POLICY_APPROVAL_CLAVES and k != "usuario"):
        hallazgos.append(PolicyFinding(CODE_POLICY_APPROVAL_INVALID, clave, "unknown_key"))
    if "approved_by" not in data:
        hallazgos.append(PolicyFinding(CODE_POLICY_APPROVAL_INVALID, "approved_by", "missing"))
    elif not is_policy_actor(data["approved_by"]):
        hallazgos.append(PolicyFinding(CODE_POLICY_APPROVAL_INVALID, "approved_by", "not_canonical_policy_actor"))
    if "action_class" not in data:
        hallazgos.append(PolicyFinding(CODE_POLICY_APPROVAL_INVALID, "action_class", "missing"))
    else:
        clase = data["action_class"]
        if not isinstance(clase, str) or clase not in ACTION_CLASSES:
            hallazgos.append(PolicyFinding(CODE_POLICY_APPROVAL_INVALID, "action_class", "unknown_action_class"))
        elif clase not in policy_approval_classes():
            hallazgos.append(PolicyFinding(CODE_POLICY_APPROVAL_INVALID, "action_class", "class_not_policy_approvable"))
    if "human_approval_ref" not in data:
        hallazgos.append(_hallazgo_ref("human_approval_ref", "missing"))
    else:
        hallazgos.extend(_validar_ref(data["human_approval_ref"], "human_approval_ref."))
    return hallazgos


@dataclass(frozen=True)
class PolicyApproval:
    approved_by: str
    action_class: str
    human_approval_ref: ApprovalRef

    def to_dict(self) -> dict:
        return {
            "action_class": self.action_class,
            "approved_by": self.approved_by,
            "human_approval_ref": self.human_approval_ref.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Any) -> "PolicyApproval":
        hallazgos = validate_policy_approval(data)
        if hallazgos:
            primero = hallazgos[0]
            raise AutonomyError(primero.code, "%s:%s" % (primero.path, primero.detail_key))
        return cls(
            approved_by=data["approved_by"],
            action_class=data["action_class"],
            human_approval_ref=ApprovalRef.from_dict(data["human_approval_ref"]),
        )


# ---------------------------------------------------------------------------
# PreApprovedDecision (R11, parte de tipos)
# ---------------------------------------------------------------------------

PROPOSAL_ARTEFACT = "proposal.md"

_PRE_CLAVES = ("approval_ref", "decision_type", "scope", "summary")


def _hallazgo_pre(path: str, detail: str) -> PolicyFinding:
    return PolicyFinding(CODE_PREAPPROVED_INVALID, path, detail)


def _scope_item_detail(item: Any) -> Optional[str]:
    if not isinstance(item, str):
        return "scope_item_not_str"
    if not item.strip():
        return "scope_item_empty"
    if item != item.strip():
        return "scope_item_padded"
    if item.startswith("/"):
        return "scope_item_absolute"
    if "\\" in item:
        return "scope_item_backslash"
    if _RE_DRIVE.match(item):
        return "scope_item_drive"
    if ".." in item.split("/"):
        return "scope_item_parent"
    if item == ".":
        return "scope_item_dot"
    return None


def _pre_a_dict(item: Any) -> Any:
    if isinstance(item, PreApprovedDecision):
        ref = item.approval_ref
        return {
            "approval_ref": ref.to_dict() if isinstance(ref, ApprovalRef) else ref,
            "decision_type": item.decision_type,
            "scope": item.scope,
            "summary": item.summary,
        }
    return item


def validate_pre_approved(item: Any, known_types: Optional[Iterable[str]] = None) -> list:
    """Hallazgos de una decision pre-aprobada (dict o instancia). No lanza.

    `known_types` lo inyecta el llamador; `None` omite la verificacion de tipo.
    """
    data = _pre_a_dict(item)
    if not isinstance(data, dict):
        return [_hallazgo_pre("", "not_a_dict")]
    hallazgos = []
    for clave in sorted(k for k in data if isinstance(k, str) and k not in _PRE_CLAVES):
        hallazgos.append(_hallazgo_pre(clave, "unknown_key"))
    tipo = data.get("decision_type")
    if not isinstance(tipo, str) or not tipo.strip():
        hallazgos.append(_hallazgo_pre("decision_type", "empty_or_not_str"))
    elif known_types is not None and tipo not in tuple(known_types):
        hallazgos.append(_hallazgo_pre("decision_type", "unknown_type"))
    resumen = data.get("summary")
    if not isinstance(resumen, str) or not resumen.strip():
        hallazgos.append(_hallazgo_pre("summary", "empty_or_not_str"))
    scope = data.get("scope")
    if not isinstance(scope, (list, tuple)):
        hallazgos.append(_hallazgo_pre("scope", "not_a_sequence"))
    elif len(scope) == 0:
        hallazgos.append(_hallazgo_pre("scope", "scope_empty"))
    else:
        for i, elemento in enumerate(scope):
            detalle = _scope_item_detail(elemento)
            if detalle:
                hallazgos.append(_hallazgo_pre("scope[%d]" % i, detalle))
    if "approval_ref" not in data or data["approval_ref"] is None:
        hallazgos.append(_hallazgo_ref("approval_ref", "missing"))
    else:
        ref = data["approval_ref"]
        hallazgos.extend(_validar_ref(ref, "approval_ref."))
        if (
            isinstance(ref, dict)
            and "artefacto" in ref
            and ref["artefacto"] != PROPOSAL_ARTEFACT
            and not any(f.path == "approval_ref.artefacto" for f in hallazgos)
        ):
            hallazgos.append(_hallazgo_ref("approval_ref.artefacto", "not_proposal"))
    return hallazgos


@dataclass(frozen=True)
class PreApprovedDecision:
    decision_type: str
    summary: str
    scope: tuple
    approval_ref: ApprovalRef

    def to_dict(self) -> dict:
        return {
            "approval_ref": self.approval_ref.to_dict(),
            "decision_type": self.decision_type,
            "scope": list(self.scope),
            "summary": self.summary,
        }

    @classmethod
    def from_dict(cls, data: Any) -> "PreApprovedDecision":
        hallazgos = validate_pre_approved(data, None)
        if hallazgos:
            primero = hallazgos[0]
            raise AutonomyError(primero.code, "%s:%s" % (primero.path, primero.detail_key))
        return cls(
            decision_type=data["decision_type"],
            summary=data["summary"],
            scope=tuple(data["scope"]),
            approval_ref=ApprovalRef.from_dict(data["approval_ref"]),
        )

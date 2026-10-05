"""Tipos neutrales de Cards y evidencia (v0.9 Change 0,
`20261002-card-and-evidence-foundation`).

Módulo solo-stdlib (`dataclasses`, `datetime`, `hashlib`, `json`, `re`,
`unicodedata`, `typing`, `__future__`): sin imports de `tools.*` ni de módulos
hermanos (R1). Las reglas de `autonomy.ApprovalRef` / `validate_human_identity`
y de `datasources.core` (canonical_json, content_sha256) se REPLICAN por forma;
los tests de paridad las cubren.

Declara:

- `EvidenceRef`: referencia por pin (kind + ref_id + sha256), clase `observed`.
- `HumanAttestation`: atestación humana, unión estricta `declared`/`anchored`,
  clase `attestation`.
- `Claim`, `Requirement` (este último NO se persiste en la Card).
- `CardEnvelope`: envelope versionado SIN campo `status` (el estado es siempre
  derivado, ver `design.md` D0.4).
- `validate_card`: hallazgos estructurales sin lanzar.
- `CardError` y `CODES`: registro único de códigos `CARD-*`.

Fail-closed: toda entrada malformada produce `CardError`, nunca una excepción
cruda de Python.
"""
from __future__ import annotations

import datetime as _datetime
import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field as _campo_dataclass
from typing import Any, Callable, Optional

# ---------------------------------------------------------------------------
# Vocabularios y patrones
# ---------------------------------------------------------------------------

SCHEMA_VERSION = 1

# Prefijo de claves de extensión (mismo patrón que datasources/datacontracts).
EXTENSION_PREFIX = "x_"

CARD_KINDS = ("data_card", "model_card", "governance_assessment")

OBSERVED_KINDS = (
    "source_observation",
    "source_provenance",
    "data_contract_result",
    "quality_evidence",
    "observed_metric",
    "baseline_reference",
    "drift_evidence",
    "execution_record",
    "report_artifact",
    "harmessi_contract",
    "data_card",
    "model_quality_result",
    "model_quality_policy",
    "model_card",
    "governance_policy",
    "evidence_document",
)

ATTESTATION_KINDS = ("declared", "anchored")
SEVERITIES = ("required", "recommended")
CLASES = ("observed", "attestation")

# DUPLICADO EXACTO de `datasources.core.SOURCE_ID_PATTERN` (R5, test de paridad).
CARD_ID_PATTERN = r"[a-z0-9][a-z0-9_-]{0,63}"
ID_PATTERN = CARD_ID_PATTERN  # evidence_id, attestation_id, claim_id, requirement_id

# Ids de Card reservados (R5).
RESERVED_CARD_IDS = ("none", "null", "default", "status")

TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

_RE_ID = re.compile(CARD_ID_PATTERN)
_RE_SHA256 = re.compile(r"[0-9a-f]{64}")
_RE_TIMESTAMP = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
_RE_CHANGE_ID = re.compile(r"[0-9]{8}-[a-z0-9][a-z0-9-]*")
_RE_UNIDAD_DISCO = re.compile(r"^[A-Za-z]:")
_RE_CREDENCIALES = re.compile(r"[^/\s]*:[^/\s]*@")
_RE_SECRETO = re.compile(r"(password|passwd|pwd|secret|token|api[_-]?key)\s*=", re.IGNORECASE)

# ---------------------------------------------------------------------------
# Registro único de códigos CARD-*
# ---------------------------------------------------------------------------

CODE_SCHEMA_UNSUPPORTED = "CARD-SCHEMA-UNSUPPORTED"
CODE_LOCATOR_NOT_PORTABLE = "CARD-LOCATOR-NOT-PORTABLE"
CODE_DUPLICATE_ID = "CARD-DUPLICATE-ID"
CODE_DANGLING_SUPPORT = "CARD-DANGLING-SUPPORT"
CODE_ATTESTATION_FUTURE = "CARD-ATTESTATION-FUTURE"
CODE_ATTESTATION_KIND_INVALID = "CARD-ATTESTATION-KIND-INVALID"
CODE_APPROVAL_REF_INVALID = "CARD-APPROVAL-REF-INVALID"
CODE_IDENTITY_INVALID = "CARD-IDENTITY-INVALID"
CODE_ID_INVALID = "CARD-ID-INVALID"
CODE_FIELD_INVALID = "CARD-FIELD-INVALID"
CODE_UNKNOWN_KEY = "CARD-UNKNOWN-KEY"
CODE_HASH_INVALID = "CARD-HASH-INVALID"
CODE_TIMESTAMP_INVALID = "CARD-TIMESTAMP-INVALID"
CODE_BODY_INVALID = "CARD-BODY-INVALID"
CODE_IO_ERROR = "CARD-IO-ERROR"
CODE_REVISION_MISMATCH = "CARD-REVISION-MISMATCH"
# Códigos de evaluación (los emite `assess.py`; se registran acá: tupla única).
CODE_REQUIREMENT_UNSATISFIED = "CARD-REQUIREMENT-UNSATISFIED"
CODE_REQUIREMENT_MISSING = "CARD-REQUIREMENT-MISSING"
CODE_REQUIREMENT_EMPTY = "CARD-REQUIREMENT-EMPTY"
CODE_REQUIREMENT_UNTRUSTED_TYPE = "CARD-REQUIREMENT-UNTRUSTED-TYPE"
CODE_REQUIREMENT_STALE = "CARD-REQUIREMENT-STALE"
CODE_REQUIREMENT_UNRESOLVABLE = "CARD-REQUIREMENT-UNRESOLVABLE"
CODE_REQUIREMENT_UNVERIFIABLE = "CARD-REQUIREMENT-UNVERIFIABLE"
CODE_EVIDENCE_STALE = "CARD-EVIDENCE-STALE"

CODES = (
    CODE_SCHEMA_UNSUPPORTED,
    CODE_LOCATOR_NOT_PORTABLE,
    CODE_DUPLICATE_ID,
    CODE_DANGLING_SUPPORT,
    CODE_ATTESTATION_FUTURE,
    CODE_ATTESTATION_KIND_INVALID,
    CODE_APPROVAL_REF_INVALID,
    CODE_IDENTITY_INVALID,
    CODE_ID_INVALID,
    CODE_FIELD_INVALID,
    CODE_UNKNOWN_KEY,
    CODE_HASH_INVALID,
    CODE_TIMESTAMP_INVALID,
    CODE_BODY_INVALID,
    CODE_IO_ERROR,
    CODE_REVISION_MISMATCH,
    CODE_REQUIREMENT_UNSATISFIED,
    CODE_REQUIREMENT_MISSING,
    CODE_REQUIREMENT_EMPTY,
    CODE_REQUIREMENT_UNTRUSTED_TYPE,
    CODE_REQUIREMENT_STALE,
    CODE_REQUIREMENT_UNRESOLVABLE,
    CODE_REQUIREMENT_UNVERIFIABLE,
    CODE_EVIDENCE_STALE,
)


class CardError(Exception):
    """Única excepción de `cards.core` para construcción/validación. `code` es
    uno de `CODES`."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


@dataclass(frozen=True)
class Hallazgo:
    """Hallazgo estructural no lanzado: `(code, path, detail)`."""

    code: str
    path: str
    detail: str

    def as_tuple(self) -> tuple:
        return (self.code, self.path, self.detail)


# ---------------------------------------------------------------------------
# Helpers privados
# ---------------------------------------------------------------------------


def _tipo(valor: Any) -> str:
    return type(valor).__name__


def _exigir_str(valor: Any, campo: str, code: str = CODE_FIELD_INVALID) -> str:
    if not isinstance(valor, str):
        raise CardError(code, f"{campo}: se esperaba str, se recibió {_tipo(valor)}")
    return valor


def _exigir_int(valor: Any, campo: str, minimo: int = 1, code: str = CODE_FIELD_INVALID) -> int:
    if isinstance(valor, bool) or not isinstance(valor, int):
        raise CardError(code, f"{campo}: se esperaba int, se recibió {_tipo(valor)}")
    if valor < minimo:
        raise CardError(code, f"{campo}: debe ser >= {minimo}")
    return valor


def _exigir_dict(valor: Any, campo: str, code: str = CODE_FIELD_INVALID) -> dict:
    if not isinstance(valor, dict):
        raise CardError(code, f"{campo}: se esperaba dict, se recibió {_tipo(valor)}")
    return valor


def _es_formato(caracter: str) -> bool:
    return unicodedata.category(caracter) in ("Cf", "Cc")


def _sin_formato(texto: str) -> str:
    return "".join(c for c in texto if not _es_formato(c))


def _texto(valor: Any, campo: str, multilinea: bool = False) -> str:
    """Texto no vacío (tras strip), sin caracteres de formato/control (se
    permiten salto de línea y tab si `multilinea`)."""
    _exigir_str(valor, campo)
    if not valor.strip():
        raise CardError(CODE_FIELD_INVALID, f"{campo}: texto vacío")
    for c in valor:
        if _es_formato(c) and not (multilinea and c in "\n\t"):
            raise CardError(CODE_FIELD_INVALID, f"{campo}: contiene caracteres no imprimibles")
    return valor


def _exigir_id(valor: Any, campo: str) -> str:
    _exigir_str(valor, campo, CODE_ID_INVALID)
    if _RE_ID.fullmatch(valor) is None:
        raise CardError(CODE_ID_INVALID, f"{campo}: id inválido {valor!r}")
    return valor


def _exigir_sha256(valor: Any, campo: str) -> str:
    _exigir_str(valor, campo, CODE_HASH_INVALID)
    if _RE_SHA256.fullmatch(valor) is None:
        raise CardError(CODE_HASH_INVALID, f"{campo}: se esperaba sha256 hex en minúsculas (64)")
    return valor


def _exigir_timestamp(valor: Any, campo: str) -> str:
    _exigir_str(valor, campo, CODE_TIMESTAMP_INVALID)
    if _RE_TIMESTAMP.fullmatch(valor) is None:
        raise CardError(CODE_TIMESTAMP_INVALID, f"{campo}: formato esperado {TIMESTAMP_FORMAT}")
    try:
        _datetime.datetime.strptime(valor, TIMESTAMP_FORMAT)
    except ValueError as exc:
        raise CardError(CODE_TIMESTAMP_INVALID, f"{campo}: fecha inexistente ({exc})") from exc
    return valor


def es_timestamp_valido(valor: Any) -> bool:
    """True si `valor` cumple `%Y-%m-%dT%H:%M:%SZ` con fecha real."""
    try:
        _exigir_timestamp(valor, "timestamp")
    except CardError:
        return False
    return True


def _motivo_no_portable(valor: str) -> Optional[str]:
    """Motivo por el que `valor` no es un locator POSIX relativo portable, o
    `None` si lo es."""
    if not valor.strip() or valor != valor.strip():
        return "vacío o con espacios en los extremos"
    if any(_es_formato(c) for c in valor):
        return "caracteres no imprimibles"
    if "\\" in valor:
        return "contiene barra invertida"
    if valor.startswith("/") or valor.startswith("~"):
        return "ruta absoluta"
    if _RE_UNIDAD_DISCO.match(valor):
        return "unidad de disco"
    if "://" in valor:
        return "URL/DSN"
    if _RE_CREDENCIALES.search(valor) or _RE_SECRETO.search(valor):
        return "posibles credenciales"
    segmentos = valor.split("/")
    if any(s == "" for s in segmentos):
        return "segmento vacío"
    if any(s == ".." for s in segmentos):
        return "contiene '..'"
    return None


def es_locator_portable(valor: Any) -> bool:
    """True si `valor` es un locator POSIX relativo portable (R12)."""
    return isinstance(valor, str) and _motivo_no_portable(valor) is None


def _exigir_locator(valor: Any, campo: str) -> str:
    _exigir_str(valor, campo)
    motivo = _motivo_no_portable(valor)
    if motivo is not None:
        raise CardError(CODE_LOCATOR_NOT_PORTABLE, f"{campo}: locator no portable ({motivo})")
    return valor


def _exigir_texto_logico(valor: Any, campo: str) -> str:
    """Identificador lógico (ref_id, member, subject): texto sin rutas físicas,
    URL/DSN ni credenciales (R12, R40)."""
    _texto(valor, campo)
    if valor != valor.strip():
        raise CardError(CODE_FIELD_INVALID, f"{campo}: espacios en los extremos")
    if len(valor) > 256:
        raise CardError(CODE_FIELD_INVALID, f"{campo}: excede 256 caracteres")
    if (
        "\\" in valor
        or valor.startswith("/")
        or valor.startswith("~")
        or _RE_UNIDAD_DISCO.match(valor)
        or "://" in valor
        or _RE_CREDENCIALES.search(valor)
        or _RE_SECRETO.search(valor)
        or ".." in valor.split("/")
    ):
        raise CardError(CODE_LOCATOR_NOT_PORTABLE, f"{campo}: contiene ruta física, URL/DSN o credenciales")
    return valor


def _json_puro(valor: Any, ruta: str) -> Any:
    """Copia profunda normalizada a JSON puro (`tuple` -> `list`, claves `str`,
    `float` finito). Tipo no soportado -> `CardError`."""
    if valor is None:
        return None
    if isinstance(valor, bool):
        return bool(valor)
    if isinstance(valor, str):
        return str(valor)
    if isinstance(valor, int):
        return int(valor)
    if isinstance(valor, float):
        if valor != valor or valor in (float("inf"), float("-inf")):
            raise CardError(CODE_FIELD_INVALID, f"{ruta}: float no finito")
        return float(valor)
    if isinstance(valor, (list, tuple)):
        return [_json_puro(item, f"{ruta}[{i}]") for i, item in enumerate(valor)]
    if isinstance(valor, dict):
        resultado: dict = {}
        for clave, item in valor.items():
            if not isinstance(clave, str):
                raise CardError(CODE_FIELD_INVALID, f"{ruta}: clave no-str {clave!r}")
            resultado[clave] = _json_puro(item, f"{ruta}.{clave}")
        return resultado
    raise CardError(CODE_FIELD_INVALID, f"{ruta}: tipo {_tipo(valor)} no es JSON-seguro")


def _json_puro_seguro(valor: Any, ruta: str) -> Any:
    try:
        return _json_puro(valor, ruta)
    except RecursionError as exc:
        raise CardError(CODE_FIELD_INVALID, f"{ruta}: anidamiento excesivo") from exc


def _exigir_extensiones(valor: Any, campo: str) -> dict:
    datos = _json_puro_seguro(_exigir_dict(valor, campo), campo)
    for clave in datos:
        if not clave.startswith(EXTENSION_PREFIX):
            raise CardError(
                CODE_UNKNOWN_KEY, f"{campo}: clave {clave!r} sin el prefijo {EXTENSION_PREFIX!r}"
            )
    return datos


def _fijar(obj: Any, nombre: str, valor: Any) -> None:
    object.__setattr__(obj, nombre, valor)


def _separar_claves(datos: Any, obligatorias: tuple, opcionales: tuple, campo: str) -> dict:
    """Valida un dict de entrada estricto: claves obligatorias presentes,
    desconocidas rechazadas salvo prefijo `x_` (que se devuelven como
    extensiones)."""
    _exigir_dict(datos, campo)
    extensiones: dict = {}
    for clave in datos:
        if not isinstance(clave, str):
            raise CardError(CODE_UNKNOWN_KEY, f"{campo}: clave no-str {clave!r}")
        if clave in obligatorias or clave in opcionales:
            continue
        if clave.startswith(EXTENSION_PREFIX):
            extensiones[clave] = datos[clave]
            continue
        raise CardError(CODE_UNKNOWN_KEY, f"{campo}: clave desconocida {clave!r}")
    for clave in obligatorias:
        if clave not in datos:
            raise CardError(CODE_FIELD_INVALID, f"{campo}: falta la clave obligatoria {clave!r}")
    return extensiones


def _envolver(funcion: Callable[[], Any], campo: str) -> Any:
    """Ejecuta `funcion`; convierte cualquier excepción cruda en `CardError`."""
    try:
        return funcion()
    except CardError:
        raise
    except Exception as exc:  # fail-closed: nunca excepciones crudas
        raise CardError(CODE_FIELD_INVALID, f"{campo}: entrada malformada ({_tipo(exc)}: {exc})") from exc


def canonical_json(obj: Any) -> str:
    """JSON canónico (idéntico byte a byte a `datasources.core.canonical_json`)."""
    try:
        return json.dumps(
            obj,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError, RecursionError) as exc:
        raise CardError(CODE_FIELD_INVALID, f"canonical_json: objeto no serializable ({exc})") from exc


def content_sha256(obj: Any) -> str:
    """sha256 hex del JSON canónico (UTF-8) de `obj`."""
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


def _con_extensiones(base: dict, extensiones: dict) -> dict:
    for clave in sorted(extensiones):
        base[clave] = extensiones[clave]
    return base


# ---------------------------------------------------------------------------
# Identidad humana y approval_ref (replicado por forma desde autonomy)
# ---------------------------------------------------------------------------


def _es_namespace_policy(valor: str) -> bool:
    normalizado = _sin_formato(unicodedata.normalize("NFKC", valor)).strip().casefold()
    return normalizado.startswith("policy:")


def validate_actor(actor: Any) -> list:
    """Hallazgos de un actor humano (R17): no vacío, sin no imprimibles, sin
    prefijo `policy:`. Misma semántica que `autonomy.validate_human_identity`."""
    if not isinstance(actor, str) or not _sin_formato(actor).strip():
        return [Hallazgo(CODE_IDENTITY_INVALID, "actor", "empty_or_not_str")]
    if _es_namespace_policy(actor):
        return [Hallazgo(CODE_IDENTITY_INVALID, "actor", "reserved_namespace")]
    if any(_es_formato(c) for c in actor):
        return [Hallazgo(CODE_IDENTITY_INVALID, "actor", "non_printable")]
    return []


def validate_approval_ref(data: Any) -> list:
    """Hallazgos de FORMA de un `approval_ref` `{change_id, artefacto, hash}`
    (mismas reglas que `autonomy.ApprovalRef`). No lanza."""
    if not isinstance(data, dict):
        return [Hallazgo(CODE_APPROVAL_REF_INVALID, "approval_ref", "not_a_dict")]
    hallazgos: list = []
    # `key=repr`: orden total y determinista aunque las claves sean de tipos mixtos
    # (int, None, str...), para que NUNCA lance TypeError.
    desconocidas = [k for k in data if not (isinstance(k, str) and k in ("change_id", "artefacto", "hash"))]
    for clave in sorted(desconocidas, key=repr):
        hallazgos.append(Hallazgo(CODE_APPROVAL_REF_INVALID, f"approval_ref.{clave}", "unknown_key"))
    for clave in ("change_id", "artefacto", "hash"):
        if clave not in data:
            hallazgos.append(Hallazgo(CODE_APPROVAL_REF_INVALID, f"approval_ref.{clave}", "missing"))
    if "change_id" in data:
        cid = data["change_id"]
        if not (isinstance(cid, str) and _RE_CHANGE_ID.fullmatch(cid)):
            hallazgos.append(Hallazgo(CODE_APPROVAL_REF_INVALID, "approval_ref.change_id", "invalid_format"))
    if "artefacto" in data:
        art = data["artefacto"]
        if not isinstance(art, str) or not art.strip():
            hallazgos.append(Hallazgo(CODE_APPROVAL_REF_INVALID, "approval_ref.artefacto", "empty_or_not_str"))
        elif art != art.strip() or art == "." or "/" in art or "\\" in art or ".." in art:
            hallazgos.append(Hallazgo(CODE_APPROVAL_REF_INVALID, "approval_ref.artefacto", "not_relative_name"))
    if "hash" in data:
        h = data["hash"]
        if not (isinstance(h, str) and _RE_SHA256.fullmatch(h)):
            hallazgos.append(Hallazgo(CODE_APPROVAL_REF_INVALID, "approval_ref.hash", "invalid_sha256"))
    return hallazgos


# ---------------------------------------------------------------------------
# EvidenceRef (R10-R15)
# ---------------------------------------------------------------------------

_EVIDENCE_OBLIGATORIAS = ("evidence_id", "kind", "ref_id", "content_sha256", "pinned_at")
_EVIDENCE_OPCIONALES = ("schema_version", "member", "locator")


@dataclass(frozen=True)
class EvidenceRef:
    """Referencia por pin a evidencia observada/de sistema. NO copia payload
    (R11). `evidence_class` es siempre `"observed"` y no se serializa (R15)."""

    evidence_id: str
    kind: str
    ref_id: str
    content_sha256: str
    pinned_at: str
    schema_version: Optional[int] = None
    member: Optional[str] = None
    locator: Optional[str] = None
    extensions: dict = _campo_dataclass(default_factory=dict)

    def __post_init__(self) -> None:
        _exigir_id(self.evidence_id, "EvidenceRef.evidence_id")
        if not isinstance(self.kind, str) or self.kind not in OBSERVED_KINDS:
            raise CardError(CODE_FIELD_INVALID, f"EvidenceRef.kind: kind inválido {self.kind!r}")
        _exigir_texto_logico(self.ref_id, "EvidenceRef.ref_id")
        _exigir_sha256(self.content_sha256, "EvidenceRef.content_sha256")
        _exigir_timestamp(self.pinned_at, "EvidenceRef.pinned_at")
        if self.schema_version is not None:
            _exigir_int(self.schema_version, "EvidenceRef.schema_version")
        if self.member is not None:
            _exigir_texto_logico(self.member, "EvidenceRef.member")
        if self.locator is not None:
            _exigir_locator(self.locator, "EvidenceRef.locator")
        _fijar(self, "extensions", _exigir_extensiones(self.extensions, "EvidenceRef.extensions"))

    @property
    def evidence_class(self) -> str:
        return "observed"

    def to_dict(self) -> dict:
        d: dict = {"evidence_id": self.evidence_id, "kind": self.kind, "ref_id": self.ref_id}
        if self.member is not None:
            d["member"] = self.member
        d["content_sha256"] = self.content_sha256
        if self.schema_version is not None:
            d["schema_version"] = self.schema_version
        if self.locator is not None:
            d["locator"] = self.locator
        d["pinned_at"] = self.pinned_at
        return _con_extensiones(d, self.extensions)

    @classmethod
    def from_dict(cls, data: Any) -> "EvidenceRef":
        def _construir() -> "EvidenceRef":
            ext = _separar_claves(data, _EVIDENCE_OBLIGATORIAS, _EVIDENCE_OPCIONALES, "EvidenceRef")
            return cls(
                evidence_id=data["evidence_id"],
                kind=data["kind"],
                ref_id=data["ref_id"],
                content_sha256=data["content_sha256"],
                pinned_at=data["pinned_at"],
                schema_version=data.get("schema_version"),
                member=data.get("member"),
                locator=data.get("locator"),
                extensions=ext,
            )

        return _envolver(_construir, "EvidenceRef")


# ---------------------------------------------------------------------------
# HumanAttestation (R16-R21)
# ---------------------------------------------------------------------------

_ATTESTATION_OBLIGATORIAS = (
    "attestation_id",
    "claim",
    "actor",
    "authority",
    "attested_at",
    "scope",
    "attestation_kind",
)
_ATTESTATION_OPCIONALES = ("reference", "approval_ref", "narrative")


@dataclass(frozen=True)
class HumanAttestation:
    """Atestación humana. Unión estricta (R21): `declared` NO lleva
    `approval_ref`; `anchored` lo exige con forma válida (sin verificar contra
    control.json/ledger: eso es Change 4). `evidence_class` es `"attestation"`.
    `reference` es un id de evidencia de la Card o un locator portable;
    `narrative` nunca participa en la evaluación (R19)."""

    attestation_id: str
    claim: str
    actor: str
    authority: str
    attested_at: str
    scope: str
    attestation_kind: str
    reference: Optional[str] = None
    approval_ref: Optional[dict] = None
    narrative: Optional[str] = None
    extensions: dict = _campo_dataclass(default_factory=dict)

    def __post_init__(self) -> None:
        _exigir_id(self.attestation_id, "HumanAttestation.attestation_id")
        _texto(self.claim, "HumanAttestation.claim", multilinea=True)
        hallazgos = validate_actor(self.actor)
        if hallazgos:
            raise CardError(CODE_IDENTITY_INVALID, f"HumanAttestation.actor: {hallazgos[0].detail}")
        _texto(self.authority, "HumanAttestation.authority")
        _exigir_timestamp(self.attested_at, "HumanAttestation.attested_at")
        _texto(self.scope, "HumanAttestation.scope", multilinea=True)
        if not isinstance(self.attestation_kind, str) or self.attestation_kind not in ATTESTATION_KINDS:
            raise CardError(
                CODE_ATTESTATION_KIND_INVALID,
                f"HumanAttestation.attestation_kind inválido {self.attestation_kind!r}",
            )
        if self.reference is not None:
            _exigir_str(self.reference, "HumanAttestation.reference")
            if _RE_ID.fullmatch(self.reference) is None:
                _exigir_locator(self.reference, "HumanAttestation.reference")
        if self.narrative is not None:
            _exigir_str(self.narrative, "HumanAttestation.narrative")
        if self.attestation_kind == "declared":
            if self.approval_ref is not None:
                raise CardError(
                    CODE_ATTESTATION_KIND_INVALID,
                    "HumanAttestation: 'declared' no admite approval_ref",
                )
        else:
            if self.approval_ref is None:
                raise CardError(
                    CODE_APPROVAL_REF_INVALID, "HumanAttestation: 'anchored' exige approval_ref"
                )
            hallazgos_ref = validate_approval_ref(self.approval_ref)
            if hallazgos_ref:
                primero = hallazgos_ref[0]
                raise CardError(CODE_APPROVAL_REF_INVALID, f"{primero.path}: {primero.detail}")
            ref = self.approval_ref
            _fijar(
                self,
                "approval_ref",
                {"artefacto": ref["artefacto"], "change_id": ref["change_id"], "hash": ref["hash"]},
            )
        _fijar(self, "extensions", _exigir_extensiones(self.extensions, "HumanAttestation.extensions"))

    @property
    def evidence_class(self) -> str:
        return "attestation"

    def to_dict(self) -> dict:
        d: dict = {
            "attestation_id": self.attestation_id,
            "attestation_kind": self.attestation_kind,
            "claim": self.claim,
            "actor": self.actor,
            "authority": self.authority,
            "attested_at": self.attested_at,
            "scope": self.scope,
        }
        if self.reference is not None:
            d["reference"] = self.reference
        if self.approval_ref is not None:
            d["approval_ref"] = dict(self.approval_ref)
        if self.narrative is not None:
            d["narrative"] = self.narrative
        return _con_extensiones(d, self.extensions)

    @classmethod
    def from_dict(cls, data: Any) -> "HumanAttestation":
        def _construir() -> "HumanAttestation":
            ext = _separar_claves(data, _ATTESTATION_OBLIGATORIAS, _ATTESTATION_OPCIONALES, "HumanAttestation")
            return cls(
                attestation_id=data["attestation_id"],
                claim=data["claim"],
                actor=data["actor"],
                authority=data["authority"],
                attested_at=data["attested_at"],
                scope=data["scope"],
                attestation_kind=data["attestation_kind"],
                reference=data.get("reference"),
                approval_ref=data.get("approval_ref"),
                narrative=data.get("narrative"),
                extensions=ext,
            )

        return _envolver(_construir, "HumanAttestation")


# ---------------------------------------------------------------------------
# Claim (R22) y Requirement (R23)
# ---------------------------------------------------------------------------

_CLAIM_OBLIGATORIAS = ("claim_id", "statement", "supports")
_CLAIM_OPCIONALES = ("requirement_id",)


def _a_tupla(valor: Any, campo: str) -> tuple:
    if not isinstance(valor, (list, tuple)):
        raise CardError(CODE_FIELD_INVALID, f"{campo}: se esperaba lista/tupla, se recibió {_tipo(valor)}")
    return tuple(valor)


@dataclass(frozen=True)
class Claim:
    """Afirmación de la Card con sus soportes (ids de evidencia/atestación)."""

    claim_id: str
    statement: str
    supports: tuple = ()
    requirement_id: Optional[str] = None
    extensions: dict = _campo_dataclass(default_factory=dict)

    def __post_init__(self) -> None:
        _exigir_id(self.claim_id, "Claim.claim_id")
        _texto(self.statement, "Claim.statement", multilinea=True)
        soportes = _a_tupla(self.supports, "Claim.supports")
        for i, s in enumerate(soportes):
            _exigir_id(s, f"Claim.supports[{i}]")
        _fijar(self, "supports", soportes)
        if self.requirement_id is not None:
            _exigir_id(self.requirement_id, "Claim.requirement_id")
        _fijar(self, "extensions", _exigir_extensiones(self.extensions, "Claim.extensions"))

    def to_dict(self) -> dict:
        d: dict = {"claim_id": self.claim_id}
        if self.requirement_id is not None:
            d["requirement_id"] = self.requirement_id
        d["statement"] = self.statement
        d["supports"] = list(self.supports)
        return _con_extensiones(d, self.extensions)

    @classmethod
    def from_dict(cls, data: Any) -> "Claim":
        def _construir() -> "Claim":
            ext = _separar_claves(data, _CLAIM_OBLIGATORIAS, _CLAIM_OPCIONALES, "Claim")
            return cls(
                claim_id=data["claim_id"],
                statement=data["statement"],
                supports=data["supports"],
                requirement_id=data.get("requirement_id"),
                extensions=ext,
            )

        return _envolver(_construir, "Claim")


@dataclass(frozen=True)
class Requirement:
    """Requisito provisto externamente (NO se persiste en la Card)."""

    requirement_id: str
    severity: str
    accepts: tuple
    accepted_kinds: Optional[tuple] = None
    min_attestation_kind: str = "declared"

    def __post_init__(self) -> None:
        _exigir_id(self.requirement_id, "Requirement.requirement_id")
        if not isinstance(self.severity, str) or self.severity not in SEVERITIES:
            raise CardError(CODE_FIELD_INVALID, f"Requirement.severity inválida {self.severity!r}")
        acepta = _a_tupla(self.accepts, "Requirement.accepts")
        if not acepta:
            raise CardError(CODE_FIELD_INVALID, "Requirement.accepts no puede ser vacío")
        for c in acepta:
            if not isinstance(c, str) or c not in CLASES:
                raise CardError(CODE_FIELD_INVALID, f"Requirement.accepts: clase inválida {c!r}")
        _fijar(self, "accepts", acepta)
        if self.accepted_kinds is not None:
            kinds = _a_tupla(self.accepted_kinds, "Requirement.accepted_kinds")
            for k in kinds:
                if not isinstance(k, str) or k not in OBSERVED_KINDS:
                    raise CardError(CODE_FIELD_INVALID, f"Requirement.accepted_kinds: kind inválido {k!r}")
            _fijar(self, "accepted_kinds", kinds)
        if not isinstance(self.min_attestation_kind, str) or self.min_attestation_kind not in ATTESTATION_KINDS:
            raise CardError(
                CODE_ATTESTATION_KIND_INVALID,
                f"Requirement.min_attestation_kind inválido {self.min_attestation_kind!r}",
            )


# ---------------------------------------------------------------------------
# CardEnvelope (R8, R9)
# ---------------------------------------------------------------------------

_ENVELOPE_CLAVES = (
    "schema_version",
    "card_kind",
    "kind_schema_version",
    "card_id",
    "title",
    "subject",
    "created_at",
    "generated_at",
    "evidence",
    "attestations",
    "claims",
    "body",
    "extensions",
)


def _tupla_tipada(valor: Any, tipo: type, campo: str) -> tuple:
    items = _a_tupla(valor, campo)
    for i, item in enumerate(items):
        if not isinstance(item, tipo):
            raise CardError(CODE_FIELD_INVALID, f"{campo}[{i}]: se esperaba {tipo.__name__}, se recibió {_tipo(item)}")
    return items


@dataclass(frozen=True)
class CardEnvelope:
    """Envelope de Card. Sin campo `status` (estado siempre derivado)."""

    schema_version: int
    card_kind: str
    kind_schema_version: int
    card_id: str
    title: str
    subject: str
    created_at: str
    generated_at: str
    evidence: tuple = ()
    attestations: tuple = ()
    claims: tuple = ()
    body: dict = _campo_dataclass(default_factory=dict)
    extensions: dict = _campo_dataclass(default_factory=dict)

    def __post_init__(self) -> None:
        # `schema_version` desconocido se construye (para poder reportarlo en
        # `validate_card`); `from_dict` lo rechaza con CARD-SCHEMA-UNSUPPORTED.
        _exigir_int(self.schema_version, "CardEnvelope.schema_version", minimo=0)
        if not isinstance(self.card_kind, str) or self.card_kind not in CARD_KINDS:
            raise CardError(CODE_FIELD_INVALID, f"CardEnvelope.card_kind inválido {self.card_kind!r}")
        _exigir_int(self.kind_schema_version, "CardEnvelope.kind_schema_version")
        _exigir_id(self.card_id, "CardEnvelope.card_id")
        if self.card_id in RESERVED_CARD_IDS:
            raise CardError(CODE_ID_INVALID, f"CardEnvelope.card_id reservado {self.card_id!r}")
        _texto(self.title, "CardEnvelope.title")
        _exigir_texto_logico(self.subject, "CardEnvelope.subject")
        _exigir_timestamp(self.created_at, "CardEnvelope.created_at")
        _exigir_timestamp(self.generated_at, "CardEnvelope.generated_at")
        _fijar(self, "evidence", _tupla_tipada(self.evidence, EvidenceRef, "CardEnvelope.evidence"))
        _fijar(
            self, "attestations", _tupla_tipada(self.attestations, HumanAttestation, "CardEnvelope.attestations")
        )
        _fijar(self, "claims", _tupla_tipada(self.claims, Claim, "CardEnvelope.claims"))
        _exigir_dict(self.body, "CardEnvelope.body", CODE_BODY_INVALID)
        _fijar(self, "body", _json_puro_seguro(self.body, "CardEnvelope.body"))
        _fijar(self, "extensions", _exigir_extensiones(self.extensions, "CardEnvelope.extensions"))

    def to_dict(self, *, con_revision: bool = False) -> dict:
        d = {
            "schema_version": self.schema_version,
            "card_kind": self.card_kind,
            "kind_schema_version": self.kind_schema_version,
            "card_id": self.card_id,
            "title": self.title,
            "subject": self.subject,
            "created_at": self.created_at,
            "generated_at": self.generated_at,
            "evidence": [e.to_dict() for e in self.evidence],
            "attestations": [a.to_dict() for a in self.attestations],
            "claims": [c.to_dict() for c in self.claims],
            "body": _json_puro_seguro(self.body, "CardEnvelope.body"),
            "extensions": dict(self.extensions),
        }
        if con_revision:
            # Solo para archivos: no participa del hash.
            d["revision_id"] = self.revision_id()
        return d

    def content_sha256(self) -> str:
        """sha256 canónico de `to_dict()` SIN `generated_at` (R9)."""
        d = self.to_dict()
        del d["generated_at"]
        return content_sha256(d)

    def revision_id(self) -> str:
        return self.card_id + "__" + self.content_sha256()[:12]

    @classmethod
    def from_dict(cls, data: Any) -> "CardEnvelope":
        """Estricto. `schema_version != 1` -> CARD-SCHEMA-UNSUPPORTED (antes
        que cualquier otra validación). Acepta la clave opcional
        `revision_id` (de archivo) y la verifica contra el hash recomputado
        (CARD-REVISION-MISMATCH). Cualquier otra clave desconocida, incluida
        `status`, se rechaza (CARD-UNKNOWN-KEY).

        Un dict rechazado con `CardError` equivale al estado derivado
        `invalid` de la Card (nunca se devuelve una Card parcial);
        `assess.evaluate_file` expone ese rechazo como `CardAssessment` con
        `card_status == "invalid"`."""

        def _construir() -> "CardEnvelope":
            _exigir_dict(data, "CardEnvelope")
            if "schema_version" not in data:
                raise CardError(CODE_FIELD_INVALID, "CardEnvelope: falta schema_version")
            sv = data["schema_version"]
            if isinstance(sv, bool) or not isinstance(sv, int):
                raise CardError(CODE_FIELD_INVALID, "CardEnvelope.schema_version: se esperaba int")
            if sv != SCHEMA_VERSION:
                raise CardError(CODE_SCHEMA_UNSUPPORTED, f"schema_version {sv!r} no soportado")
            for clave in data:
                if not isinstance(clave, str) or (clave not in _ENVELOPE_CLAVES and clave != "revision_id"):
                    raise CardError(CODE_UNKNOWN_KEY, f"CardEnvelope: clave desconocida {clave!r}")
            for clave in _ENVELOPE_CLAVES:
                if clave not in data:
                    raise CardError(CODE_FIELD_INVALID, f"CardEnvelope: falta la clave {clave!r}")
            card = cls(
                schema_version=sv,
                card_kind=data["card_kind"],
                kind_schema_version=data["kind_schema_version"],
                card_id=data["card_id"],
                title=data["title"],
                subject=data["subject"],
                created_at=data["created_at"],
                generated_at=data["generated_at"],
                evidence=tuple(
                    EvidenceRef.from_dict(e) for e in _a_tupla(data["evidence"], "CardEnvelope.evidence")
                ),
                attestations=tuple(
                    HumanAttestation.from_dict(a)
                    for a in _a_tupla(data["attestations"], "CardEnvelope.attestations")
                ),
                claims=tuple(Claim.from_dict(c) for c in _a_tupla(data["claims"], "CardEnvelope.claims")),
                body=data["body"],
                extensions=data["extensions"],
            )
            if "revision_id" in data:
                declarado = data["revision_id"]
                if not isinstance(declarado, str) or declarado != card.revision_id():
                    raise CardError(
                        CODE_REVISION_MISMATCH,
                        f"revision_id declarado {declarado!r} no coincide con el recomputado {card.revision_id()!r}",
                    )
            return card

        return _envolver(_construir, "CardEnvelope")


# ---------------------------------------------------------------------------
# validate_card: hallazgos estructurales sin lanzar
# ---------------------------------------------------------------------------


def _normalizar_hallazgo_body(item: Any) -> Hallazgo:
    if isinstance(item, Hallazgo):
        return item
    if isinstance(item, CardError):
        return Hallazgo(item.code, "$.body", item.message)
    if isinstance(item, (tuple, list)) and len(item) == 3 and all(isinstance(x, str) for x in item):
        return Hallazgo(item[0], item[1], item[2])
    return Hallazgo(CODE_BODY_INVALID, "$.body", f"hallazgo no interpretable: {item!r}")


def validate_card(
    card: Any,
    *,
    clock: Optional[Callable[[], str]] = None,
    validate_body: Optional[Callable[[dict], list]] = None,
) -> list:
    """Lista de `Hallazgo` estructurales de una Card (vacía = válida). No
    lanza. `clock` es un callable sin argumentos que devuelve un timestamp UTC
    `%Y-%m-%dT%H:%M:%SZ`; si es `None` no se chequea la atestación futura.
    `validate_body` es un callable `body -> lista de hallazgos`; sin él el
    body debe ser `{}`."""
    if not isinstance(card, CardEnvelope):
        return [Hallazgo(CODE_FIELD_INVALID, "$", f"se esperaba CardEnvelope, se recibió {_tipo(card)}")]
    hallazgos: list = []

    if card.schema_version != SCHEMA_VERSION:
        hallazgos.append(
            Hallazgo(CODE_SCHEMA_UNSUPPORTED, "$.schema_version", f"schema_version {card.schema_version!r} no soportado")
        )

    # R14: ids únicos entre evidencias y atestaciones.
    vistos: dict = {}
    for i, e in enumerate(card.evidence):
        ruta = f"$.evidence[{i}].evidence_id"
        if e.evidence_id in vistos:
            hallazgos.append(Hallazgo(CODE_DUPLICATE_ID, ruta, f"id duplicado {e.evidence_id!r}"))
        else:
            vistos[e.evidence_id] = ruta
    for i, a in enumerate(card.attestations):
        ruta = f"$.attestations[{i}].attestation_id"
        if a.attestation_id in vistos:
            hallazgos.append(Hallazgo(CODE_DUPLICATE_ID, ruta, f"id duplicado {a.attestation_id!r}"))
        else:
            vistos[a.attestation_id] = ruta
    claims_vistos: set = set()
    for i, c in enumerate(card.claims):
        if c.claim_id in claims_vistos:
            hallazgos.append(Hallazgo(CODE_DUPLICATE_ID, f"$.claims[{i}].claim_id", f"id duplicado {c.claim_id!r}"))
        claims_vistos.add(c.claim_id)

    # R22: soportes existentes.
    for i, c in enumerate(card.claims):
        for j, s in enumerate(c.supports):
            if s not in vistos:
                hallazgos.append(
                    Hallazgo(CODE_DANGLING_SUPPORT, f"$.claims[{i}].supports[{j}]", f"soporte inexistente {s!r}")
                )

    # R18: atestación futura (solo si hay clock).
    if clock is not None:
        ahora: Optional[str] = None
        try:
            candidato = clock()
            if es_timestamp_valido(candidato):
                ahora = candidato
            else:
                hallazgos.append(Hallazgo(CODE_TIMESTAMP_INVALID, "clock", "el clock devolvió un timestamp inválido"))
        except Exception as exc:  # fail-closed
            hallazgos.append(Hallazgo(CODE_TIMESTAMP_INVALID, "clock", f"el clock falló ({_tipo(exc)})"))
        if ahora is not None:
            # El formato fijo hace que la comparación léxica sea cronológica.
            for i, a in enumerate(card.attestations):
                if a.attested_at > ahora:
                    hallazgos.append(
                        Hallazgo(
                            CODE_ATTESTATION_FUTURE,
                            f"$.attestations[{i}].attested_at",
                            f"{a.attested_at} es posterior a {ahora}",
                        )
                    )

    # Body.
    if validate_body is None:
        if card.body != {}:
            hallazgos.append(Hallazgo(CODE_BODY_INVALID, "$.body", "sin validate_body el body debe ser {}"))
    else:
        try:
            resultado = validate_body(card.body)
            if not isinstance(resultado, (list, tuple)):
                hallazgos.append(Hallazgo(CODE_BODY_INVALID, "$.body", "validate_body no devolvió una lista"))
            else:
                hallazgos.extend(_normalizar_hallazgo_body(item) for item in resultado)
        except Exception as exc:  # fail-closed
            hallazgos.append(Hallazgo(CODE_BODY_INVALID, "$.body", f"validate_body falló ({_tipo(exc)})"))

    return hallazgos

"""Evaluación de governance de un modelo (v0.9 Change 3,
`20261005-model-risk-responsible-ai`): especialización por composición de la
Foundation (`core` / `assess`) y de la policy de `govpolicy`, espejo de
`modelcard.py` / `datacard.py`.

Un `ModelGovernanceAssessment` es un `CardEnvelope(card_kind="governance_assessment",
kind_schema_version=1)` que evalúa UNA Model Card concreta (pineada por revisión en
`body.model_card_ref`) contra la policy efectiva (`govpolicy.merge(base, hardening)`).
El body lo valida este módulo mediante el hook `validate_body` de Change 0. Todo pin
vive en `card.evidence`; el body solo lo referencia por `evidence_id`.

Imports: stdlib + `core` + `assess` + `govpolicy` (hermanos). `resolvers` se importa
de forma PEREZOSA (evaluación y lectura del documento de endurecimiento). NO se
importa `modelcard`: la regla de decodificación de `card_id` se DUPLICA en
`_decodificar_card_id` (un test de paridad la compara con
`modelcard.decode_model_card_id`).

Qué significa y qué NO significa `governance_completeness == "complete"`:

- `complete` = los requisitos de la policy efectiva están satisfechos con soportes
  aceptables e íntegros. NO equivale a aprobación ética, de justicia, seguridad,
  privacidad, explicabilidad, cumplimiento ni aptitud para producción (ver
  `NOTA_COMPLETENESS`).
- No se calculan ni se infieren fairness, explicabilidad, privacidad ni seguridad:
  no se leen valores de métricas ni se emiten juicios «justo/seguro/privado». La
  salida solo informa presencia / ausencia / stale / unverifiable y la satisfacción
  de requisitos explícitos de la policy.
- Un `evidence_document` acredita únicamente existencia del documento, integridad de
  bytes, identidad/pin y frescura según el resolver. NO acredita que su contenido sea
  correcto ni que su metodología o conclusión sean válidas: un requisito que lo
  acepta solo permite afirmar «existe evidencia documental íntegra vinculada a este
  requisito».
- No hay afirmaciones de conformidad con marcos externos ni con normativa.
- Human oversight solo CITA aprobaciones existentes (atestación `anchored` con
  `approval_ref`, o `execution_record` / `evidence_document`): no crea checkpoints,
  no toca el modo de autonomía ni duplica el ledger. La evaluación no consulta ni
  modifica autonomía / STOP / runtime y no bloquea nada.
- El `risk_level` es una declaración humana (atestación con claim exacto
  `risk_level=<level>`), nunca una inferencia. Ausencia de declaración -> `incomplete`.
- El estado (`governance_completeness`, estado de requisitos y dimensiones) es SIEMPRE
  derivado y nunca se persiste ni se acepta en el archivo.
- Un endurecimiento de proyecto solo se evalúa si el assessment lo CITA
  (`policy_ref.hardening_evidence_id`). Detectar un endurecimiento existente pero no
  citado queda para el Change 4 (lectura obligatoria de config).

Imports/efectos: este módulo NO crea `governance/` al importar ni al validar; solo
`write_governance_assessment` crea directorios, al escribir. Fail-closed: nada lanza
excepciones crudas hacia afuera; todo error es `CardError` (o `Hallazgo` en los
validadores); la evaluación convierte cualquier fallo en un assessment `invalid`.

Limitaciones heredadas / documentadas:

- `title`, `Claim.statement` y los textos de atestaciones pertenecen a la Foundation
  (`core`) y NO se validan aquí (portabilidad/credenciales).
- La heurística de portabilidad de texto libre (`_motivo_texto_no_portable`) solo
  detecta rutas al INICIO (`/`, `~`, unidad de disco), barras invertidas, `://` y
  patrones de credenciales; no detecta rutas absolutas embebidas a mitad de frase.
  Se aplica a los textos del body y, recursivamente, a los strings bajo claves `x_*`.
- `anchored` es estructural: la forma de `approval_ref` se valida, su resolución real
  contra control.json/ledger es del Change 4. Ningún mensaje afirma verificación.
- La pertenencia de un `requirement_id` de claim a la policy efectiva se valida sin
  contexto de filesystem solo contra la policy base cuando no hay endurecimiento
  citado; con endurecimiento citado la comprobación completa ocurre en la evaluación.
- Staleness por pin exacto, sin semántica «latest». Falso fresh posible en A -> B -> A
  para evidencia reescrita con el mismo hash.
- `write_governance_assessment(replace=True)` tiene una ventana TOCTOU residual
  (comprobación de identidad y escritura no son atómicas), como la Foundation.
- Los requisitos estructurales `model_card_pin` / `policy_hardening_pin` exigen un
  claim propio (con `requirement_id` homónimo); sin claim quedan `missing`.
- No existe N/A a nivel de dimensión: `not_applicable` es por requisito `recommended`.
- LIMITACION ABIERTA (I3): borrar `hardening_evidence_id` del body (y re-pinear la
  policy efectiva como base-only) NO se detecta aquí. El Change 4 debe volver
  obligatoria la lectura de config/endurecimiento y compararla con el pin.
- Los pins huérfanos (no citados por ningún requisito ni claim) solo afectan el estado
  global si están `stale` (R50 d); `unresolvable`/`unverifiable` huérfanos solo se
  reportan en `evidencias`.
- La atestación de riesgo (claim `risk_level=<level>`) está reservada a
  `accountability_risk_declaration`: tampoco puede ser el `attestation_id` de un
  `not_applicable` (CLAIM-SUPPORT-INCONSISTENT; el N/A necesita su propia atestación).
  Un claim con forma casi idéntica pero malformada
  (p. ej. `risk level: high`) hace inválida la Card (fail-closed).
- Si el documento de endurecimiento leído difiere del hash pineado (cambió entre la
  resolución y la lectura) no se usa: el assessment queda `stale` (POLICY-CHANGED).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

try:  # import dual: paquete (`tools.cards`) o módulo suelto con `tools/cards` en sys.path
    from . import assess, core, govpolicy
except ImportError:  # pragma: no cover - ejecución sin paquete padre
    import assess  # type: ignore[no-redef]
    import core  # type: ignore[no-redef]
    import govpolicy  # type: ignore[no-redef]

CardError = core.CardError
CardEnvelope = core.CardEnvelope
Hallazgo = core.Hallazgo

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

GOVERNANCE_KIND = "governance_assessment"
GOVERNANCE_KIND_SCHEMA_VERSION = 1

# Ubicación (R60), relativa a la raíz del proyecto.
CARD_DIR_PARTES = ("governance", "model-risk")

NOTA_COMPLETENESS = (
    "complete = los requisitos de la policy efectiva están satisfechos con soportes "
    "aceptables e íntegros; NO equivale a aprobación ética, de justicia, seguridad, "
    "privacidad, explicabilidad, cumplimiento ni aptitud para producción"
)

CODE_UNKNOWN_KEY = "GOVASSESS-UNKNOWN-KEY"
CODE_IDENTITY_MISMATCH = "GOVASSESS-IDENTITY-MISMATCH"
CODE_SCHEMA_UNSUPPORTED = "GOVASSESS-SCHEMA-UNSUPPORTED"
CODE_KIND_INVALID = "GOVASSESS-KIND-INVALID"
CODE_BODY_INVALID = "GOVASSESS-BODY-INVALID"
CODE_DANGLING_EVIDENCE = "GOVASSESS-DANGLING-EVIDENCE"
CODE_REF_INCONSISTENT = "GOVASSESS-REF-INCONSISTENT"
CODE_CLAIM_SUPPORT_INCONSISTENT = "GOVASSESS-CLAIM-SUPPORT-INCONSISTENT"
CODE_NA_NOT_ALLOWED = "GOVASSESS-NA-NOT-ALLOWED"
CODE_RISK_DECLARATION_CONTRADICTORY = "GOVASSESS-RISK-DECLARATION-CONTRADICTORY"
CODE_RISK_BELOW_FLOOR = "GOVASSESS-RISK-BELOW-FLOOR"
CODE_POLICY_CHANGED = "GOVASSESS-POLICY-CHANGED"
CODE_POLICY_INVALID = "GOVASSESS-POLICY-INVALID"
CODE_EXISTS = "GOVASSESS-EXISTS"
CODE_NOT_FOUND = "GOVASSESS-NOT-FOUND"
CODE_PATH_INVALID = "GOVASSESS-PATH-INVALID"

GOVASSESS_CODES = (
    CODE_UNKNOWN_KEY,
    CODE_IDENTITY_MISMATCH,
    CODE_SCHEMA_UNSUPPORTED,
    CODE_KIND_INVALID,
    CODE_BODY_INVALID,
    CODE_DANGLING_EVIDENCE,
    CODE_REF_INCONSISTENT,
    CODE_CLAIM_SUPPORT_INCONSISTENT,
    CODE_NA_NOT_ALLOWED,
    CODE_RISK_DECLARATION_CONTRADICTORY,
    CODE_RISK_BELOW_FLOOR,
    CODE_POLICY_CHANGED,
    CODE_POLICY_INVALID,
    CODE_EXISTS,
    CODE_NOT_FOUND,
    CODE_PATH_INVALID,
)

# Código del PASS de `a_check_results` (fuera de GOVASSESS_CODES, igual que
# `assess.CODE_CARD_COMPLETE` está fuera de `core.CODES`).
CODE_COMPLETE = "GOVASSESS-COMPLETE"

# Estados de requisito: los de la Foundation más `not_applicable` (R36, R43).
REQ_NOT_APPLICABLE = "not_applicable"
ESTADOS_REQUISITO = assess.ESTADOS_REQUISITO + (REQ_NOT_APPLICABLE,)

# Estado de dimensión (R49).
DIM_NOT_REQUIRED = "not_required"

# Estados del assessment (precedencia de la Foundation).
GOV_INVALID = assess.CARD_INVALID
GOV_STALE = assess.CARD_STALE
GOV_INCOMPLETE = assess.CARD_INCOMPLETE
GOV_COMPLETE = assess.CARD_COMPLETE

# Ids de requisitos estructurales (reservados en govpolicy).
REQ_MODEL_CARD_PIN = "model_card_pin"
REQ_POLICY_HARDENING_PIN = "policy_hardening_pin"
REQ_RISK_DECLARATION = "accountability_risk_declaration"
_ESTRUCTURALES = (REQ_MODEL_CARD_PIN, REQ_POLICY_HARDENING_PIN)

_KIND_MODEL_CARD = "model_card"
_KIND_GOVERNANCE_POLICY = "governance_policy"
# Kinds aceptados por un spec con `accepted_kinds=None` (R14): externos + estructurales.
_KINDS_POR_DEFECTO = tuple(govpolicy.EXTERNAL_EVIDENCE_KINDS) + (_KIND_MODEL_CARD, _KIND_GOVERNANCE_POLICY)

# Identidad de Model Card (duplicado de modelcard; test de paridad externo).
_MODEL_ID_PATTERN = r"[a-z0-9]+([_-][a-z0-9]+)*"
_MODEL_VERSION_PATTERN = r"[a-z0-9]+([.-][a-z0-9]+)*"
_CARD_ID_SEPARATOR = "__"
_MAX_ID = 64
_DIR_MODEL_CARDS = "governance/cards/model"

# Claves cerradas del body (R32); `x_*` siempre permitidas.
_BODY_OBLIGATORIAS = ("model_card_ref", "policy_ref")
_BODY_OPCIONALES = ("risk_declaration", "dimensions", "notes")
_MCREF_OBLIGATORIAS = ("evidence_id",)
_POLICYREF_OBLIGATORIAS = ("base_policy_id", "base_version", "base_sha256", "effective_sha256")
_POLICYREF_OPCIONALES = ("hardening_evidence_id",)
_RISK_OBLIGATORIAS = ("level", "attestation_id")
_DIM_OPCIONALES = ("context", "limitations", "not_applicable")
_NA_OBLIGATORIAS = ("requirement_id", "rationale", "attestation_id")

_RE_ID = re.compile(core.CARD_ID_PATTERN)
_RE_MODEL_ID = re.compile(_MODEL_ID_PATTERN)
_RE_MODEL_VERSION = re.compile(_MODEL_VERSION_PATTERN)
_RE_REF_MODEL_CARD = re.compile(r"(?P<cid>" + core.CARD_ID_PATTERN + r")__(?P<h>[0-9a-f]{12})")
_RE_RIESGO = re.compile(r"risk_level=(low|medium|high)")
# Near-miss de declaración de riesgo (fail-closed). Falso positivo ACOTADO y aceptado:
# el claim de CUALQUIER atestación que EMPIECE con «risk level:» / «risk_level=» /
# «risk-level…» (tras strip y minúsculas) fuera del formato exacto
# `risk_level=<low|medium|high>` se trata como declaración malformada (Card invalid).
# La prosa que no empieza así no dispara.
_RE_RIESGO_CERCANO = re.compile(r"risk[_ -]level\s*[=:]")
_RE_SHA256 = re.compile(r"[0-9a-f]{64}")

_IDS_BASE = frozenset(r.requirement_id for r in govpolicy.BASE_POLICY.requirements)
_RANGO_ATESTACION = {"declared": 0, "anchored": 1}


# ---------------------------------------------------------------------------
# Identidad (R7, R8) — regla duplicada de `modelcard`
# ---------------------------------------------------------------------------


def _problemas_identidad(model_id: Any, model_version: Any) -> list:
    motivos: list = []
    if not isinstance(model_id, str) or _RE_MODEL_ID.fullmatch(model_id) is None:
        motivos.append(f"model_id inválido {model_id!r}")
    if not isinstance(model_version, str) or _RE_MODEL_VERSION.fullmatch(model_version) is None:
        motivos.append(f"model_version inválida {model_version!r}")
    if not motivos and len(model_id) + len(_CARD_ID_SEPARATOR) + len(model_version) > _MAX_ID:
        motivos.append("el card_id excede el presupuesto de 64 caracteres")
    return motivos


def _decodificar_card_id(card_id: Any) -> tuple:
    """`(model_id, model_version)` a partir de un `card_id` de Model Card
    (`model_id + "__" + model_version.replace(".", "_")`). Duplica la regla de
    `modelcard.decode_model_card_id` (cubierta por un test de paridad externo, porque
    este módulo no importa `modelcard`). `CardError` si no es decodificable."""
    if not isinstance(card_id, str) or card_id.count(_CARD_ID_SEPARATOR) != 1:
        raise CardError(CODE_IDENTITY_MISMATCH, f"card_id no decodificable {card_id!r}")
    model_id, codificada = card_id.split(_CARD_ID_SEPARATOR)
    model_version = codificada.replace("_", ".")
    if _problemas_identidad(model_id, model_version) or (
        model_id + _CARD_ID_SEPARATOR + model_version.replace(".", "_") != card_id
    ):
        raise CardError(CODE_IDENTITY_MISMATCH, f"card_id no decodificable {card_id!r}")
    return model_id, model_version


# ---------------------------------------------------------------------------
# Helpers de validación (acumulan Hallazgo; no lanzan)
# ---------------------------------------------------------------------------


def _h(out: list, code: str, path: str, detail: str) -> None:
    out.append(Hallazgo(code, path, detail))


def _motivo_texto_no_portable(valor: str) -> Optional[str]:
    """Reglas de portabilidad de core aplicadas a texto libre."""
    if "\\" in valor:
        return "contiene barra invertida"
    if valor.startswith("/") or valor.startswith("~"):
        return "ruta absoluta"
    if core._RE_UNIDAD_DISCO.match(valor):
        return "unidad de disco"
    if "://" in valor:
        return "URL/DSN"
    if core._RE_CREDENCIALES.search(valor) or core._RE_SECRETO.search(valor):
        return "posibles credenciales"
    if ".." in valor.split("/"):
        return "contiene '..'"
    return None


def _strings_no_portables(valor: Any, ruta: str, out: list) -> None:
    if isinstance(valor, str):
        motivo = _motivo_texto_no_portable(valor)
        if motivo is not None:
            _h(out, core.CODE_LOCATOR_NOT_PORTABLE, ruta, f"texto no portable ({motivo})")
    elif isinstance(valor, dict):
        for k, v in valor.items():
            _strings_no_portables(v, f"{ruta}.{k}", out)
    elif isinstance(valor, (list, tuple)):
        for i, v in enumerate(valor):
            _strings_no_portables(v, f"{ruta}[{i}]", out)


def _claves(datos: dict, obligatorias: tuple, opcionales: tuple, ruta: str, out: list) -> None:
    """Desconocida (salvo `x_*`) -> UNKNOWN-KEY; faltante -> BODY-INVALID. Los valores
    bajo `x_*` se validan recursivamente por portabilidad."""
    for clave in datos:
        if not isinstance(clave, str):
            _h(out, CODE_UNKNOWN_KEY, ruta, f"clave no-str {clave!r}")
        elif clave.startswith(core.EXTENSION_PREFIX):
            _strings_no_portables(datos[clave], f"{ruta}.{clave}", out)
        elif clave in obligatorias or clave in opcionales:
            continue
        else:
            _h(out, CODE_UNKNOWN_KEY, f"{ruta}.{clave}", f"clave desconocida {clave!r}")
    for clave in obligatorias:
        if clave not in datos:
            _h(out, CODE_BODY_INVALID, ruta, f"falta la clave obligatoria {clave!r}")


def _texto(valor: Any, ruta: str, out: list, multilinea: bool = False) -> bool:
    """str no vacío, sin caracteres de control y sin rutas/DSN/credenciales."""
    if not isinstance(valor, str):
        _h(out, CODE_BODY_INVALID, ruta, f"se esperaba str, se recibió {type(valor).__name__}")
        return False
    try:
        core._texto(valor, ruta, multilinea=multilinea)
    except CardError as exc:
        _h(out, CODE_BODY_INVALID, ruta, exc.message)
        return False
    motivo = _motivo_texto_no_portable(valor)
    if motivo is not None:
        _h(out, core.CODE_LOCATOR_NOT_PORTABLE, ruta, f"texto no portable ({motivo})")
        return False
    return True


def _id(valor: Any, ruta: str, out: list) -> bool:
    if not isinstance(valor, str) or _RE_ID.fullmatch(valor) is None:
        _h(out, CODE_BODY_INVALID, ruta, f"id inválido {valor!r}")
        return False
    return True


def _evidencia(evidencias: dict, atestaciones: dict, eid: Any, kinds: tuple, ruta: str, out: list) -> Optional[Any]:
    """Resuelve `eid` en la evidencia de la Card: inexistente -> DANGLING; atestación o
    kind fuera de `kinds` -> REF-INCONSISTENT. Devuelve la EvidenceRef o None."""
    if not _id(eid, ruta, out):
        return None
    ref = evidencias.get(eid)
    if ref is None:
        if eid in atestaciones:
            _h(out, CODE_REF_INCONSISTENT, ruta, f"{eid!r} es una atestación; se esperaba evidencia {kinds[0]!r}")
        else:
            _h(out, CODE_DANGLING_EVIDENCE, ruta, f"evidence_id inexistente en card.evidence: {eid!r}")
        return None
    if ref.kind not in kinds:
        _h(out, CODE_REF_INCONSISTENT, ruta, f"{eid!r} es kind {ref.kind!r}; se esperaba {kinds[0]!r}")
        return None
    return ref


def _atestacion(evidencias: dict, atestaciones: dict, aid: Any, ruta: str, out: list) -> Optional[Any]:
    """Resuelve `aid` en las atestaciones de la Card (DANGLING / REF-INCONSISTENT)."""
    if not _id(aid, ruta, out):
        return None
    att = atestaciones.get(aid)
    if att is None:
        if aid in evidencias:
            _h(out, CODE_REF_INCONSISTENT, ruta, f"{aid!r} es evidencia observada; se esperaba una atestación")
        else:
            _h(out, CODE_DANGLING_EVIDENCE, ruta, f"attestation_id inexistente en card.attestations: {aid!r}")
        return None
    return att


def _validar_model_card_ref(valor: Any, evidencias: dict, atestaciones: dict, card_id: Any, subject: Any, out: list) -> None:
    ruta = "$.body.model_card_ref"
    if not isinstance(valor, dict):
        _h(out, CODE_BODY_INVALID, ruta, "model_card_ref debe ser objeto")
        return
    _claves(valor, _MCREF_OBLIGATORIAS, (), ruta, out)
    if "evidence_id" not in valor:
        return
    r = f"{ruta}.evidence_id"
    ref = _evidencia(evidencias, atestaciones, valor["evidence_id"], (_KIND_MODEL_CARD,), r, out)
    if ref is None:
        return
    coincide = _RE_REF_MODEL_CARD.fullmatch(ref.ref_id)
    if coincide is None:
        _h(out, CODE_REF_INCONSISTENT, r, f"ref_id {ref.ref_id!r} no cumple <model_card_id>__<hash12>")
        return
    cid = coincide.group("cid")
    if coincide.group("h") != ref.content_sha256[:12]:
        _h(out, CODE_REF_INCONSISTENT, r, f"hash12 de ref_id {ref.ref_id!r} != content_sha256[:12] del pin")
    if ref.locator is not None and ref.locator != f"{_DIR_MODEL_CARDS}/{cid}.json":
        _h(out, CODE_REF_INCONSISTENT, r, f"locator {ref.locator!r} != {_DIR_MODEL_CARDS}/{cid}.json")
    try:
        model_id, _version = _decodificar_card_id(cid)
    except CardError:
        _h(out, CODE_IDENTITY_MISMATCH, r, f"el card_id {cid!r} del pin no es un model_card_id decodificable")
        return
    if card_id is not None and card_id != cid:
        _h(out, CODE_IDENTITY_MISMATCH, "$.card_id", f"card_id {card_id!r} != {cid!r} (Model Card pineada)")
    if subject is not None and subject != model_id:
        _h(out, CODE_IDENTITY_MISMATCH, "$.subject", f"subject {subject!r} != model_id {model_id!r} (Model Card pineada)")


def _validar_policy_ref(valor: Any, evidencias: dict, atestaciones: dict, out: list) -> None:
    ruta = "$.body.policy_ref"
    if not isinstance(valor, dict):
        _h(out, CODE_BODY_INVALID, ruta, "policy_ref debe ser objeto")
        return
    _claves(valor, _POLICYREF_OBLIGATORIAS, _POLICYREF_OPCIONALES, ruta, out)
    if "base_policy_id" in valor:
        _id(valor["base_policy_id"], f"{ruta}.base_policy_id", out)
    if "base_version" in valor:
        v = valor["base_version"]
        if isinstance(v, bool) or not isinstance(v, int) or v < 1:
            _h(out, CODE_BODY_INVALID, f"{ruta}.base_version", "base_version debe ser int >= 1")
    for clave in ("base_sha256", "effective_sha256"):
        if clave in valor:
            v = valor[clave]
            if not isinstance(v, str) or _RE_SHA256.fullmatch(v) is None:
                _h(out, CODE_BODY_INVALID, f"{ruta}.{clave}", "se esperaba sha256 hex en minúsculas (64)")
    if "hardening_evidence_id" in valor:
        _evidencia(
            evidencias, atestaciones, valor["hardening_evidence_id"], (_KIND_GOVERNANCE_POLICY,),
            f"{ruta}.hardening_evidence_id", out,
        )


def _validar_risk_declaration(valor: Any, evidencias: dict, atestaciones: dict, out: list) -> None:
    ruta = "$.body.risk_declaration"
    if not isinstance(valor, dict):
        _h(out, CODE_BODY_INVALID, ruta, "risk_declaration debe ser objeto")
        return
    _claves(valor, _RISK_OBLIGATORIAS, (), ruta, out)
    if "level" in valor and (not isinstance(valor["level"], str) or valor["level"] not in govpolicy.LEVELS):
        _h(out, CODE_BODY_INVALID, f"{ruta}.level", f"level inválido {valor['level']!r}; se espera uno de {list(govpolicy.LEVELS)}")
    if "attestation_id" in valor:
        att = _atestacion(evidencias, atestaciones, valor["attestation_id"], f"{ruta}.attestation_id", out)
        if att is not None and _RE_RIESGO.fullmatch(att.claim) is None:
            _h(out, CODE_REF_INCONSISTENT, f"{ruta}.attestation_id",
               f"el claim de la atestación {att.attestation_id!r} debe ser exactamente 'risk_level=<level>'")


def _validar_riesgo_card(body: dict, atestaciones: Any, out: list) -> None:
    """R33c: examina TODAS las atestaciones con claim `risk_level=(low|medium|high)`.
    Niveles distintos -> CONTRADICTORY (nunca se elige uno); iguales -> dedupe. El
    nivel declarado en el body debe coincidir."""
    niveles = set()
    for i, a in enumerate(atestaciones):
        claim = getattr(a, "claim", "")
        m = _RE_RIESGO.fullmatch(claim)
        if m is not None:
            niveles.add(m.group(1))
        elif _RE_RIESGO_CERCANO.match(claim.strip().lower()):
            _h(out, CODE_REF_INCONSISTENT, f"$.attestations[{i}].claim",
               "declaración de riesgo malformada: debe ser exactamente 'risk_level=<low|medium|high>'")
    if len(niveles) > 1:
        _h(out, CODE_RISK_DECLARATION_CONTRADICTORY, "$.attestations",
           f"atestaciones risk_level con niveles distintos: {sorted(niveles)}")
        return
    rd = body.get("risk_declaration")
    if isinstance(rd, dict) and len(niveles) == 1:
        nivel = rd.get("level")
        if isinstance(nivel, str) and nivel in govpolicy.LEVELS and nivel not in niveles:
            _h(out, CODE_RISK_DECLARATION_CONTRADICTORY, "$.body.risk_declaration.level",
               f"level {nivel!r} difiere del nivel de las atestaciones risk_level ({sorted(niveles)[0]!r})")


def _validar_dimensions(valor: Any, evidencias: dict, atestaciones: dict, out: list) -> None:
    ruta = "$.body.dimensions"
    if not isinstance(valor, dict):
        _h(out, CODE_BODY_INVALID, ruta, "dimensions debe ser objeto")
        return
    _claves(valor, (), govpolicy.DIMENSIONS, ruta, out)
    vistos: set = set()
    for dim in govpolicy.DIMENSIONS:
        if dim not in valor:
            continue
        r = f"{ruta}.{dim}"
        d = valor[dim]
        if not isinstance(d, dict):
            _h(out, CODE_BODY_INVALID, r, "cada dimensión debe ser objeto")
            continue
        _claves(d, (), _DIM_OPCIONALES, r, out)
        if "context" in d:
            _texto(d["context"], f"{r}.context", out, multilinea=True)
        if "limitations" in d:
            lim = d["limitations"]
            if not isinstance(lim, list):
                _h(out, CODE_BODY_INVALID, f"{r}.limitations", "se esperaba lista")
            else:
                for i, item in enumerate(lim):
                    _texto(item, f"{r}.limitations[{i}]", out, multilinea=True)
        if "not_applicable" not in d:
            continue
        na = d["not_applicable"]
        if not isinstance(na, list):
            _h(out, CODE_BODY_INVALID, f"{r}.not_applicable", "se esperaba lista")
            continue
        for i, item in enumerate(na):
            rr = f"{r}.not_applicable[{i}]"
            if not isinstance(item, dict):
                _h(out, CODE_BODY_INVALID, rr, "cada elemento debe ser objeto")
                continue
            _claves(item, _NA_OBLIGATORIAS, (), rr, out)
            if "requirement_id" in item and _id(item["requirement_id"], f"{rr}.requirement_id", out):
                rid = item["requirement_id"]
                if rid in _ESTRUCTURALES:
                    _h(out, CODE_NA_NOT_ALLOWED, f"{rr}.requirement_id", f"{rid!r} es un requisito estructural required; no admite N/A")
                if rid in vistos:
                    _h(out, CODE_REF_INCONSISTENT, f"{rr}.requirement_id", f"requirement_id duplicado en not_applicable {rid!r}")
                vistos.add(rid)
            if "rationale" in item:
                _texto(item["rationale"], f"{rr}.rationale", out, multilinea=True)
            if "attestation_id" in item:
                _atestacion(evidencias, atestaciones, item["attestation_id"], f"{rr}.attestation_id", out)


def _info(body: Any) -> dict:
    """Extracción tolerante de lo que el body cita (sin validar; ver `_validar_body`)."""
    info: dict = {"mc": None, "hard": None, "decl": None, "decl_att": None, "na": [], "pol": {}}
    if not isinstance(body, dict):
        return info
    mc = body.get("model_card_ref")
    if isinstance(mc, dict) and isinstance(mc.get("evidence_id"), str):
        info["mc"] = mc["evidence_id"]
    pr = body.get("policy_ref")
    if isinstance(pr, dict):
        info["pol"] = pr
        if isinstance(pr.get("hardening_evidence_id"), str):
            info["hard"] = pr["hardening_evidence_id"]
    rd = body.get("risk_declaration")
    if isinstance(rd, dict):
        if isinstance(rd.get("level"), str) and rd["level"] in govpolicy.LEVELS:
            info["decl"] = rd["level"]
        if isinstance(rd.get("attestation_id"), str):
            info["decl_att"] = rd["attestation_id"]
    dims = body.get("dimensions")
    if isinstance(dims, dict):
        for dim in govpolicy.DIMENSIONS:
            d = dims.get(dim)
            na = d.get("not_applicable") if isinstance(d, dict) else None
            for item in na if isinstance(na, list) else ():
                if isinstance(item, dict) and isinstance(item.get("requirement_id"), str):
                    info["na"].append((dim, item["requirement_id"], item.get("attestation_id")))
    return info


def _claims_fuera_de_policy(claims: Any, ids: Any, out: list) -> None:
    """R41: `requirement_id` que no es estructural ni de la policy (`ids`)."""
    for i, claim in enumerate(claims if isinstance(claims, (list, tuple)) else ()):
        rid = getattr(claim, "requirement_id", None)
        if isinstance(rid, str) and rid not in _ESTRUCTURALES and rid not in ids:
            _h(out, CODE_CLAIM_SUPPORT_INCONSISTENT, f"$.claims[{i}]",
               f"requirement_id {rid!r} no es estructural ni pertenece a la policy efectiva")


def _validar_claims(info: dict, claims: Any, policy_ids: Any, out: list, atestaciones_lista: Any = ()) -> None:
    """R41. Claims sin `requirement_id` son libres. `model_card_pin` /
    `policy_hardening_pin`: `supports == (eid,)` del pin citado.
    `accountability_risk_declaration`: la atestación de `risk_declaration` debe estar
    en `supports`. Un requisito declarado N/A no puede tener claims. La existencia de
    los soportes la chequea `core.validate_card` (CARD-DANGLING-SUPPORT)."""
    na_ids = {rid for _dim, rid, _att in info["na"]}
    # Atestaciones de riesgo: RESERVADAS para accountability_risk_declaration.
    reservadas = {
        getattr(a, "attestation_id", None)
        for a in atestaciones_lista
        if _RE_RIESGO.fullmatch(getattr(a, "claim", "")) is not None
    }
    for dim, rid_na, att_na in info["na"]:
        if isinstance(att_na, str) and att_na in reservadas:
            _h(out, CODE_CLAIM_SUPPORT_INCONSISTENT, f"$.body.dimensions.{dim}.not_applicable",
               f"la atestación de riesgo {att_na!r} está reservada para {REQ_RISK_DECLARATION!r}; "
               f"el N/A de {rid_na!r} necesita su propia atestación")
    for i, claim in enumerate(claims if isinstance(claims, (list, tuple)) else ()):
        rid = getattr(claim, "requirement_id", None)
        soportes = tuple(getattr(claim, "supports", ()) or ())
        if rid != REQ_RISK_DECLARATION:
            usadas = sorted(s for s in soportes if s in reservadas)
            if usadas:
                _h(out, CODE_CLAIM_SUPPORT_INCONSISTENT, f"$.claims[{i}].supports",
                   f"la atestación de riesgo {usadas} está reservada para {REQ_RISK_DECLARATION!r}")
        if not isinstance(rid, str):
            continue
        ruta = f"$.claims[{i}]"
        if rid in na_ids and rid not in _ESTRUCTURALES:
            _h(out, CODE_CLAIM_SUPPORT_INCONSISTENT, ruta, f"el requisito {rid!r} está declarado not_applicable y además tiene claim")
        if rid == REQ_MODEL_CARD_PIN or rid == REQ_POLICY_HARDENING_PIN:
            eid = info["mc"] if rid == REQ_MODEL_CARD_PIN else info["hard"]
            if eid is None:
                _h(out, CODE_CLAIM_SUPPORT_INCONSISTENT, ruta, f"claim {rid!r} sin el pin correspondiente citado en el body")
            elif soportes != (eid,):
                _h(out, CODE_CLAIM_SUPPORT_INCONSISTENT, f"{ruta}.supports",
                   f"claim {rid!r} debe apoyarse exactamente en ({eid!r},); recibió {list(soportes)}")
        elif rid == REQ_RISK_DECLARATION:
            if info["decl_att"] is None or info["decl_att"] not in soportes:
                _h(out, CODE_CLAIM_SUPPORT_INCONSISTENT, f"{ruta}.supports",
                   f"claim {rid!r} debe incluir la atestación de risk_declaration en supports")
    ids = policy_ids
    if ids is None and info["hard"] is None:
        ids = _IDS_BASE
    if ids is not None:
        _claims_fuera_de_policy(claims, ids, out)


def _validar_body(
    body: Any,
    evidencias: dict,
    atestaciones_lista: Any = (),
    claims: Any = (),
    card_id: Any = None,
    subject: Any = None,
    policy_ids: Any = None,
) -> list:
    out: list = []
    if not isinstance(body, dict):
        return [Hallazgo(CODE_BODY_INVALID, "$.body", "body debe ser objeto")]
    atestaciones = {getattr(a, "attestation_id", None): a for a in atestaciones_lista}
    _claves(body, _BODY_OBLIGATORIAS, _BODY_OPCIONALES, "$.body", out)
    if "model_card_ref" in body:
        _validar_model_card_ref(body["model_card_ref"], evidencias, atestaciones, card_id, subject, out)
    if "policy_ref" in body:
        _validar_policy_ref(body["policy_ref"], evidencias, atestaciones, out)
    if "risk_declaration" in body:
        _validar_risk_declaration(body["risk_declaration"], evidencias, atestaciones, out)
    if "dimensions" in body:
        _validar_dimensions(body["dimensions"], evidencias, atestaciones, out)
    if "notes" in body:
        _texto(body["notes"], "$.body.notes", out, multilinea=True)
    _validar_riesgo_card(body, atestaciones_lista, out)
    _validar_claims(_info(body), claims, policy_ids, out, atestaciones_lista)
    return out


# ---------------------------------------------------------------------------
# API pública: validación
# ---------------------------------------------------------------------------


def _hallazgos_card(card: Any, policy_ids: Any = None) -> list:
    if not isinstance(card, CardEnvelope):
        return [Hallazgo(core.CODE_FIELD_INVALID, "$", f"se esperaba CardEnvelope, se recibió {type(card).__name__}")]
    if card.card_kind != GOVERNANCE_KIND:
        return [Hallazgo(CODE_KIND_INVALID, "$.card_kind", f"se esperaba card_kind {GOVERNANCE_KIND!r}, no {card.card_kind!r}")]
    if card.kind_schema_version != GOVERNANCE_KIND_SCHEMA_VERSION:
        return [
            Hallazgo(
                CODE_SCHEMA_UNSUPPORTED,
                "$.kind_schema_version",
                f"kind_schema_version {card.kind_schema_version!r} no soportado (se espera {GOVERNANCE_KIND_SCHEMA_VERSION})",
            )
        ]
    evidencias = {e.evidence_id: e for e in card.evidence}
    return _validar_body(card.body, evidencias, card.attestations, card.claims, card.card_id, card.subject, policy_ids)


def body_validator_for(card: Any, policy_requirement_ids: Any = None) -> Callable[[dict], list]:
    """Devuelve `validate_body(body) -> list[Hallazgo]` (hook de Change 0) que cierra
    sobre la evidencia, atestaciones, claims, `card_id` y `subject` de `card`.
    Además del body chequea kind / `kind_schema_version`, la identidad
    (`GOVASSESS-IDENTITY-MISMATCH`), la declaración de riesgo inequívoca (R33c) y la
    coherencia de claims (R41). `policy_requirement_ids` (opcional) son los ids de la
    policy efectiva; sin ellos se usan los de la policy base si el body no cita
    endurecimiento (con endurecimiento citado la pertenencia se verifica al evaluar).
    Fail-closed: cualquier excepción -> `GOVASSESS-BODY-INVALID`."""
    if isinstance(card, CardEnvelope):
        evidencias = {e.evidence_id: e for e in card.evidence}
        kind, ksv = card.card_kind, card.kind_schema_version
        atestaciones = tuple(card.attestations)
        claims = tuple(card.claims)
        card_id, subject = card.card_id, card.subject
        valido = True
    else:
        evidencias, kind, ksv, atestaciones, claims, card_id, subject, valido = {}, None, None, (), (), None, None, False
    ids = None if policy_requirement_ids is None else frozenset(policy_requirement_ids)

    def validate_body(body: Any) -> list:
        try:
            if not valido:
                return [Hallazgo(core.CODE_FIELD_INVALID, "$", "body_validator_for: se esperaba CardEnvelope")]
            if kind != GOVERNANCE_KIND:
                return [Hallazgo(CODE_KIND_INVALID, "$.card_kind", f"se esperaba card_kind {GOVERNANCE_KIND!r}, no {kind!r}")]
            if ksv != GOVERNANCE_KIND_SCHEMA_VERSION:
                return [Hallazgo(CODE_SCHEMA_UNSUPPORTED, "$.kind_schema_version", f"kind_schema_version {ksv!r} no soportado")]
            return _validar_body(body, evidencias, atestaciones, claims, card_id, subject, ids)
        except Exception as exc:  # fail-closed
            return [Hallazgo(CODE_BODY_INVALID, "$.body", f"validación del body falló ({type(exc).__name__})")]

    return validate_body


def validate_governance_assessment(card: Any) -> list:
    """Hallazgos de la Card: kind == governance_assessment, `kind_schema_version == 1`,
    identidad, body cerrado, declaración de riesgo y claims. Lista vacía = válida. No
    lanza. Los chequeos estructurales de la Foundation (`core.validate_card`) los hace
    `evaluate_governance_assessment` / `write_governance_assessment`."""
    try:
        return _hallazgos_card(card)
    except Exception as exc:  # fail-closed
        return [Hallazgo(CODE_BODY_INVALID, "$.body", f"validación falló ({type(exc).__name__})")]


# ---------------------------------------------------------------------------
# Ubicación y escritura (R60, R61)
# ---------------------------------------------------------------------------


def card_path(project_root: Any, card_id: str) -> Path:
    """`<project_root>/governance/model-risk/<card_id>.json`. Valida `card_id` (patrón de
    core, no reservado) y que el resultado quede dentro de `project_root` (incluso
    resolviendo symlinks). No escanea ni crea nada."""
    if not isinstance(card_id, str) or _RE_ID.fullmatch(card_id) is None or card_id in core.RESERVED_CARD_IDS:
        raise CardError(core.CODE_ID_INVALID, f"card_path: card_id inválido {card_id!r}")
    try:
        raiz = Path(project_root)
        destino = raiz.joinpath(*CARD_DIR_PARTES, card_id + ".json")
        destino.resolve().relative_to(raiz.resolve())
    except ValueError as exc:
        raise CardError(CODE_PATH_INVALID, "card_path: la ruta sale de project_root") from exc
    except (OSError, TypeError, RuntimeError) as exc:
        raise CardError(CODE_PATH_INVALID, f"card_path: project_root inválido ({type(exc).__name__})") from exc
    return destino


def _existe(ruta: Path) -> bool:
    try:
        return ruta.exists()
    except OSError as exc:
        raise CardError(core.CODE_IO_ERROR, f"no se pudo comprobar {ruta.name} ({type(exc).__name__})") from exc


def _es_archivo(ruta: Path) -> bool:
    try:
        return ruta.is_file()
    except OSError as exc:
        raise CardError(core.CODE_IO_ERROR, f"no se pudo comprobar {ruta.name} ({type(exc).__name__})") from exc


def _misma_identidad(existente: Any, card: Any) -> bool:
    return (
        isinstance(existente, CardEnvelope)
        and existente.card_kind == GOVERNANCE_KIND
        and existente.card_id == card.card_id
        and existente.subject == card.subject
    )


def write_governance_assessment(
    project_root: Any,
    card: Any,
    *,
    replace: bool = False,
    clock: Optional[Callable[[], str]] = None,
) -> Path:
    """Escribe el assessment en `card_path(project_root, card.card_id)`.

    - Valida ANTES de tocar el filesystem (inválido -> `CardError`, sin crear
      `governance/`).
    - `replace=False`: crea directorios y escribe con `write_card(exclusive=True)`; si
      existe cualquier archivo -> `GOVASSESS-EXISTS`, sin sobrescribir.
    - `replace=True`: exige un archivo existente, legible, de la MISMA identidad
      (`card_id`, `card_kind`, `subject`); si no -> `GOVASSESS-NOT-FOUND` /
      `GOVASSESS-IDENTITY-MISMATCH`, sin escribir.
    """
    if not isinstance(card, CardEnvelope):
        raise CardError(core.CODE_FIELD_INVALID, "write_governance_assessment: se esperaba CardEnvelope")
    reloj = clock if clock is not None else assess._reloj_utc
    validador = body_validator_for(card)
    hallazgos = core.validate_card(card, clock=reloj, validate_body=validador)
    if hallazgos:
        resumen = "; ".join(f"{h.code} {h.path}: {h.detail}" for h in hallazgos)
        raise CardError(hallazgos[0].code, f"Governance assessment inválido, no se escribe: {resumen}")
    destino = card_path(project_root, card.card_id)

    if replace:
        if not _existe(destino):
            raise CardError(CODE_NOT_FOUND, f"replace=True pero {destino.name} no existe")
        if not _es_archivo(destino):
            raise CardError(CODE_IDENTITY_MISMATCH, f"{destino.name} existe y no es un archivo; no se sobrescribe")
        try:
            existente = assess.read_card(destino)
        except CardError as exc:
            raise CardError(
                CODE_IDENTITY_MISMATCH,
                f"{destino.name} existe y no es una Card legible ({exc.code}); no se sobrescribe",
            ) from exc
        if not _misma_identidad(existente, card):
            raise CardError(
                CODE_IDENTITY_MISMATCH,
                f"{destino.name} pertenece a otra identidad ({existente.card_kind}/{existente.card_id}); no se sobrescribe",
            )
        return assess.write_card(destino, card, reloj, validate_body=validador)

    if _existe(destino):
        raise CardError(CODE_EXISTS, f"{destino.name} ya existe; usar replace=True para una nueva revisión")
    try:
        destino.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise CardError(core.CODE_IO_ERROR, f"no se pudo crear el directorio de assessments ({type(exc).__name__})") from exc
    try:
        return assess.write_card(destino, card, reloj, validate_body=validador, exclusive=True)
    except CardError as exc:
        if exc.code == core.CODE_IO_ERROR and _existe(destino):
            raise CardError(CODE_EXISTS, f"{destino.name} ya existe; no se sobrescribe") from exc
        raise


# ---------------------------------------------------------------------------
# Resultado de la evaluación (R46, R47)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GovernanceAssessment:
    """Resultado derivado de `evaluate_governance_assessment`. Nunca se persiste.

    - `governance_completeness`: invalid / stale / incomplete / complete.
    - `effective_level`: `max(declarado, risk_floor)`; sin declaración es el nivel
      INFORMATIVO `max(risk_floor, "low")`; `None` si no se pudo computar.
    - `policy`: `{"pinned": {...}, "recomputed": {...}}` (ids, versiones y hashes).
    - `dimensiones`: tupla de `(dimension, estado, requisitos_required_ids)`.
    - `requisitos`: tupla de `(requirement_id, severity, dimension|None, state,
      detalle)` ordenada por id (dimension `None` = requisito estructural).
    - `evidencias`: tupla de `(evidence_id, state)` ordenada por id.
    - `hallazgos`: `Hallazgo`s estructurales / de policy / de riesgo.
    - `nota`: `NOTA_COMPLETENESS` (complete NO es aprobación).
    """

    governance_completeness: str
    effective_level: Optional[str] = None
    declared_level: Optional[str] = None
    risk_floor: Optional[str] = None
    policy: dict = field(default_factory=dict)
    dimensiones: tuple = ()
    requisitos: tuple = ()
    evidencias: tuple = ()
    hallazgos: tuple = ()
    card_id: str = ""
    nota: str = NOTA_COMPLETENESS

    def a_dict(self) -> dict:
        def _copia(valor: Any) -> Any:
            if isinstance(valor, dict):
                return {k: _copia(valor[k]) for k in sorted(valor)}
            if isinstance(valor, (list, tuple)):
                return [_copia(v) for v in valor]
            return valor

        return {
            "card_id": self.card_id,
            "governance_completeness": self.governance_completeness,
            "effective_level": self.effective_level,
            "declared_level": self.declared_level,
            "risk_floor": self.risk_floor,
            "policy": _copia(self.policy),
            "dimensiones": [
                {"dimension": d[0], "estado": d[1], "requisitos": list(d[2])} for d in self.dimensiones
            ],
            "requisitos": [
                {"requirement_id": r[0], "severity": r[1], "dimension": r[2], "state": r[3], "detail": r[4]}
                for r in self.requisitos
            ],
            "evidencias": [{"evidence_id": e[0], "state": e[1]} for e in self.evidencias],
            "hallazgos": [list(h.as_tuple()) for h in self.hallazgos],
            "nota": NOTA_COMPLETENESS,
        }


@dataclass(frozen=True)
class _Req:
    """Requisito derivado (R40). `dimension=None` = estructural."""

    requirement_id: str
    severity: str
    accepts: tuple
    kinds: Optional[tuple]
    minimo: str
    dimension: Optional[str]


# ---------------------------------------------------------------------------
# Evaluador propio (R42, R43)
# ---------------------------------------------------------------------------

_PRECEDENCIA_SOPORTE = (assess.EV_STALE, assess.EV_UNRESOLVABLE, assess.EV_UNVERIFIABLE)


def _evaluar_requisito(req: _Req, claims: tuple, evidencias: dict, atestaciones: dict, estados_ev: dict) -> tuple:
    """`(estado, detalle, evidencias_stale_citadas)`. Regla «todo lo citado respaldado y
    vigente»: TODOS los soportes de los claims del requisito deben ser aceptables para
    el spec y frescos; un soporte fresco nunca oculta a otro stale / inaceptable."""
    propios = [c for c in claims if c.requirement_id == req.requirement_id]
    if not propios:
        return assess.REQ_MISSING, "sin claim ligado al requisito", ()
    soportes: list = []
    for c in propios:
        for s in c.supports:
            if s not in soportes:
                soportes.append(s)
    if not soportes:
        return assess.REQ_EMPTY, "claim sin supports", ()

    kinds = req.kinds if req.kinds is not None else _KINDS_POR_DEFECTO
    rango_min = _RANGO_ATESTACION[req.minimo]
    rechazados: list = []
    estados: list = []
    stale_citadas: list = []
    for s in soportes:
        if s in evidencias:
            estado = estados_ev.get(s, assess.EV_UNVERIFIABLE)
            if estado == assess.EV_STALE:
                stale_citadas.append(s)
            if "observed" in req.accepts and evidencias[s].kind in kinds:
                estados.append(estado)
            else:
                rechazados.append(s)
        elif s in atestaciones:
            if "attestation" in req.accepts and _RANGO_ATESTACION[atestaciones[s].attestation_kind] >= rango_min:
                estados.append(assess.EV_FRESH)
            else:
                rechazados.append(s)
        else:
            rechazados.append(s)  # no debería ocurrir en una Card válida (dangling)
    if rechazados:
        return (
            assess.REQ_UNTRUSTED_TYPE,
            "soportes de clase/kind/attestation_kind no aceptados: " + ",".join(rechazados),
            tuple(stale_citadas),
        )
    for estado in _PRECEDENCIA_SOPORTE:
        if estado in estados:
            return assess._ESTADO_REQ_DE_EVIDENCIA[estado], f"soporte aceptado en estado {estado}", tuple(stale_citadas)
    return assess.REQ_SATISFIED, "soportes vigentes: " + ",".join(soportes), ()


# ---------------------------------------------------------------------------
# Evaluación (R46-R55)
# ---------------------------------------------------------------------------


def _modulo_resolvers() -> Any:
    """Import perezoso de `resolvers`. Módulo ausente -> `None`."""
    try:
        try:
            from . import resolvers as _resolvers
        except ImportError:  # pragma: no cover - ejecución sin paquete padre
            import resolvers as _resolvers  # type: ignore[no-redef]
    except ImportError:
        return None
    return _resolvers


def _resolvers_por_defecto(repo_root: Any) -> dict:
    """`resolvers.default_resolvers(repo_root)`. Módulo ausente -> mapa vacío (todo
    `unverifiable`, fail-closed). `repo_root` inválido -> `CardError`."""
    modulo = _modulo_resolvers()
    if modulo is None:
        return {}
    try:
        return dict(modulo.default_resolvers(repo_root))
    except CardError:
        raise
    except Exception as exc:  # fail-closed
        raise CardError(core.CODE_FIELD_INVALID, f"default_resolvers falló ({type(exc).__name__})") from exc


def _leer_hardening(repo_root: Any, ref: Any) -> Any:
    """Lee el documento de endurecimiento del locator del pin. `CardError` si no se
    puede leer; `GovPolicyError` si el documento es inválido; `None` si su hash
    difiere del pineado (cambió entre la resolución y la lectura)."""
    modulo = _modulo_resolvers()
    if modulo is None:
        raise CardError(core.CODE_IO_ERROR, "resolvers no disponible")
    datos = modulo.leer_documento_json(repo_root, ref.locator)
    # TOCTOU: el documento leído debe ser el pineado; si no, no se usa para la policy.
    if modulo.hash_document(datos) != ref.content_sha256:
        return None
    return govpolicy.HardeningDocument.from_dict(datos)


def _invalido(card_id: str, hallazgos: Any, evidencias: tuple = ()) -> GovernanceAssessment:
    return GovernanceAssessment(
        governance_completeness=GOV_INVALID, evidencias=tuple(evidencias), hallazgos=tuple(hallazgos), card_id=card_id
    )


def _nivel_idx(nivel: str) -> int:
    return govpolicy.LEVELS.index(nivel)


def _evaluar(card: CardEnvelope, repo_root: Any, base: Any, resolvers: Mapping, clock: Any) -> GovernanceAssessment:
    info = _info(card.body)
    # 1. Validación estructural (sin invocar resolvers si falla).
    # Sin endurecimiento citado, la policy efectiva == base: se pasan sus ids (la base puede ser custom).
    ids_previos = frozenset(r.requirement_id for r in base.requirements) if info["hard"] is None else None
    estructurales = core.validate_card(card, clock=clock, validate_body=body_validator_for(card, ids_previos))
    if estructurales:
        return _invalido(card.card_id, estructurales)

    evidencias = {e.evidence_id: e for e in card.evidence}
    atestaciones = {a.attestation_id: a for a in card.attestations}
    estados_ev = {eid: assess.evaluar_evidencia(e, resolvers) for eid, e in evidencias.items()}
    evidencias_t = tuple(sorted(estados_ev.items(), key=lambda t: t[0]))

    inv: list = []   # hallazgos que invalidan
    obs: list = []   # hallazgos que dejan stale
    inc: list = []   # hallazgos que dejan incomplete
    stale = False
    incompleto = False

    # 2. Pins estructurales (R50 a, c, d). R50(d): CUALQUIER evidencia stale de la Card
    # (citada, inactiva, de claims libres u huérfana) deja el assessment stale.
    if any(e == assess.EV_STALE for e in estados_ev.values()):
        stale = True
    mc_estado = estados_ev.get(info["mc"], assess.EV_UNVERIFIABLE)
    if mc_estado == assess.EV_STALE:
        stale = True
    elif mc_estado != assess.EV_FRESH:
        incompleto = True
    hard_estado = None
    if info["hard"] is not None:
        hard_estado = estados_ev.get(info["hard"], assess.EV_UNVERIFIABLE)
        if hard_estado == assess.EV_STALE:
            stale = True
        elif hard_estado != assess.EV_FRESH:
            incompleto = True

    # 3. Policy efectiva (R35, R50 b-c).
    pol = info["pol"]
    base_sha = base.content_sha256()
    if pol.get("base_policy_id") != base.policy_id:
        inv.append(Hallazgo(CODE_POLICY_INVALID, "$.body.policy_ref.base_policy_id",
                            f"base_policy_id {pol.get('base_policy_id')!r} != {base.policy_id!r}"))
    hardening = None
    efectiva = None
    if info["hard"] is not None:
        try:
            hardening = _leer_hardening(repo_root, evidencias[info["hard"]])
            if hardening is None:
                stale = True
                obs.append(Hallazgo(CODE_POLICY_CHANGED, "$.body.policy_ref.hardening_evidence_id",
                                    "el documento de endurecimiento difiere del pineado; no se usa para la policy efectiva"))
        except CardError as exc:
            inc.append(Hallazgo(CODE_POLICY_INVALID, "$.body.policy_ref.hardening_evidence_id",
                                f"el endurecimiento citado no se puede leer ({exc.code}); no se evalúa solo con la base"))
        except govpolicy.GovPolicyError as exc:
            inv.append(Hallazgo(exc.code, "$.body.policy_ref.hardening_evidence_id", exc.message))
        except Exception as exc:  # fail-closed
            inv.append(Hallazgo(CODE_POLICY_INVALID, "$.body.policy_ref.hardening_evidence_id",
                                f"endurecimiento no interpretable ({type(exc).__name__})"))
    if info["hard"] is None or hardening is not None:
        try:
            efectiva = govpolicy.merge(base, hardening)
        except govpolicy.GovPolicyError as exc:
            inv.append(Hallazgo(exc.code, "$.body.policy_ref", exc.message))
        except Exception as exc:  # fail-closed
            inv.append(Hallazgo(CODE_POLICY_INVALID, "$.body.policy_ref", f"merge falló ({type(exc).__name__})"))

    politica = {
        "pinned": {
            "base_policy_id": pol.get("base_policy_id"),
            "base_version": pol.get("base_version"),
            "base_sha256": pol.get("base_sha256"),
            "effective_sha256": pol.get("effective_sha256"),
            "hardening_evidence_id": info["hard"],
        },
        "recomputed": {
            "base_policy_id": base.policy_id,
            "base_version": base.version,
            "base_sha256": base_sha,
            "hardening_sha256": efectiva.hardening_sha256 if efectiva is not None else None,
            "effective_sha256": efectiva.effective_sha256() if efectiva is not None else None,
            "risk_floor": efectiva.risk_floor if efectiva is not None else None,
        },
    }
    if pol.get("base_sha256") != base_sha or pol.get("base_version") != base.version:
        obs.append(Hallazgo(CODE_POLICY_CHANGED, "$.body.policy_ref",
                            "la policy base pineada (versión/hash) difiere de la vigente"))
    if efectiva is not None and pol.get("effective_sha256") != efectiva.effective_sha256():
        obs.append(Hallazgo(CODE_POLICY_CHANGED, "$.body.policy_ref.effective_sha256",
                            "la policy efectiva recomputada difiere de la pineada"))

    declarado = info["decl"]
    requisitos_estructurales = [_Req(REQ_MODEL_CARD_PIN, "required", ("observed",), (_KIND_MODEL_CARD,), "declared", None)]
    if info["hard"] is not None:
        requisitos_estructurales.append(
            _Req(REQ_POLICY_HARDENING_PIN, "required", ("observed",), (_KIND_GOVERNANCE_POLICY,), "declared", None)
        )

    # 4. Sin policy efectiva: solo se evalúan los requisitos estructurales.
    if efectiva is None:
        filas: list = []
        for req in requisitos_estructurales:
            estado, detalle, citadas = _evaluar_requisito(req, card.claims, evidencias, atestaciones, estados_ev)
            filas.append((req.requirement_id, req.severity, None, estado, detalle))
            stale = stale or estado == assess.REQ_STALE or bool(citadas)
        if inv:
            estado_global = GOV_INVALID
        elif stale or obs:
            estado_global = GOV_STALE
        else:
            estado_global = GOV_INCOMPLETE
        return GovernanceAssessment(
            governance_completeness=estado_global,
            effective_level=None,
            declared_level=declarado,
            risk_floor=None,
            policy=politica,
            dimensiones=(),
            requisitos=tuple(sorted(filas, key=lambda t: t[0])),
            evidencias=evidencias_t,
            hallazgos=tuple(inv + obs + inc),
            card_id=card.card_id,
        )

    # 5. Claims contra la policy efectiva (R41) cuando hay endurecimiento.
    if info["hard"] is not None:
        _claims_fuera_de_policy(card.claims, frozenset(r.requirement_id for r in efectiva.requirements), inv)

    # 6. Nivel efectivo (R31, R34).
    piso = efectiva.risk_floor
    nivel = govpolicy.max_level(govpolicy.max_level(declarado, piso), "low")
    if declarado is None:
        incompleto = True
    elif piso is not None and _nivel_idx(declarado) < _nivel_idx(piso):
        inc.append(Hallazgo(CODE_RISK_BELOW_FLOOR, "$.body.risk_declaration.level",
                            f"nivel declarado {declarado!r} < risk_floor {piso!r}; se evalúa con {nivel!r}"))

    # 7. Requisitos derivados (R40).
    derivados: list = list(requisitos_estructurales)
    por_id: dict = {r.requirement_id: r for r in efectiva.requirements}
    for r, spec in govpolicy.requirements_at(efectiva, nivel):
        derivados.append(_Req(r.requirement_id, spec.severity, spec.accepts, spec.accepted_kinds, spec.min_attestation_kind, r.dimension))
    activos = {d.requirement_id: d for d in derivados}

    # 8. N/A (R36).
    na_validos: set = set()
    for dim, rid, _att in info["na"]:
        ruta = f"$.body.dimensions.{dim}.not_applicable"
        if rid in _ESTRUCTURALES:
            inv.append(Hallazgo(CODE_NA_NOT_ALLOWED, ruta, f"{rid!r} es required; no admite N/A"))
            continue
        pr = por_id.get(rid)
        if pr is None:
            inv.append(Hallazgo(CODE_REF_INCONSISTENT, ruta, f"requirement_id {rid!r} no existe en la policy efectiva"))
        elif pr.dimension != dim:
            inv.append(Hallazgo(CODE_REF_INCONSISTENT, ruta, f"{rid!r} pertenece a la dimensión {pr.dimension!r}, no a {dim!r}"))
        elif rid not in activos:
            inv.append(Hallazgo(CODE_REF_INCONSISTENT, ruta, f"{rid!r} no aplica en el nivel efectivo {nivel!r}"))
        elif activos[rid].severity == "required":
            inv.append(Hallazgo(CODE_NA_NOT_ALLOWED, ruta, f"{rid!r} es required en el nivel {nivel!r}; no admite N/A"))
        else:
            na_validos.add(rid)

    # 9. Evaluación de requisitos.
    filas = []
    estados_req: dict = {}
    citadas_stale_required = False
    for req in derivados:
        if req.requirement_id in na_validos:
            estado, detalle, citadas = REQ_NOT_APPLICABLE, "declarado not_applicable con rationale y atestación", ()
        else:
            estado, detalle, citadas = _evaluar_requisito(req, card.claims, evidencias, atestaciones, estados_ev)
        estados_req[req.requirement_id] = estado
        filas.append((req.requirement_id, req.severity, req.dimension, estado, detalle))
        if req.severity == "required":
            if estado == assess.REQ_STALE or citadas:
                citadas_stale_required = True
            elif estado not in (assess.REQ_SATISFIED, REQ_NOT_APPLICABLE):
                incompleto = True
    stale = stale or citadas_stale_required

    # 10. Dimensiones (R49).
    dimensiones: list = []
    for dim in govpolicy.DIMENSIONS:
        ids = tuple(sorted(d.requirement_id for d in derivados if d.dimension == dim and d.severity == "required"))
        if not ids:
            dimensiones.append((dim, DIM_NOT_REQUIRED, ()))
            continue
        estados = [estados_req[i] for i in ids]
        if any(e == assess.REQ_STALE for e in estados):
            estado_dim = GOV_STALE
        elif any(e not in (assess.REQ_SATISFIED, REQ_NOT_APPLICABLE) for e in estados):
            estado_dim = GOV_INCOMPLETE
        else:
            estado_dim = GOV_COMPLETE
        dimensiones.append((dim, estado_dim, ids))

    # 11. Estado global (R47): invalid > stale > incomplete > complete.
    if inv:
        estado_global = GOV_INVALID
    elif stale or obs:
        estado_global = GOV_STALE
    elif incompleto or inc:
        estado_global = GOV_INCOMPLETE
    elif not (card.claims or card.evidence or card.attestations):
        estado_global = GOV_INCOMPLETE
    else:
        estado_global = GOV_COMPLETE
    return GovernanceAssessment(
        governance_completeness=estado_global,
        effective_level=nivel,
        declared_level=declarado,
        risk_floor=piso,
        policy=politica,
        dimensiones=tuple(dimensiones),
        requisitos=tuple(sorted(filas, key=lambda t: t[0])),
        evidencias=evidencias_t,
        hallazgos=tuple(inv + obs + inc),
        card_id=card.card_id,
    )


def evaluate_governance_assessment(
    card_or_path: Any,
    repo_root: Any,
    *,
    base: Any = govpolicy.BASE_POLICY,
    resolvers: Optional[Mapping] = None,
    clock: Optional[Callable[[], str]] = None,
) -> GovernanceAssessment:
    """Evalúa un assessment (`CardEnvelope` o ruta de archivo) contra la policy efectiva.

    Solo lanza `CardError` ante argumentos inválidos (`base`, `resolvers`, `clock`,
    `repo_root`). Un archivo ilegible o malformado, una Card inválida o cualquier fallo
    interno producen `GovernanceAssessment(governance_completeness="invalid")`; nunca
    una excepción cruda ni un `complete` por ausencia. No consulta ni modifica
    autonomía / STOP / runtime (R53). No compara valores de métricas (R55)."""
    if not isinstance(base, govpolicy.GovernancePolicy):
        raise CardError(core.CODE_FIELD_INVALID, "evaluate_governance_assessment: base debe ser GovernancePolicy")
    if resolvers is not None and not isinstance(resolvers, Mapping):
        raise CardError(core.CODE_FIELD_INVALID, "evaluate_governance_assessment: resolvers debe ser un mapa kind -> callable")
    if clock is not None and not callable(clock):
        raise CardError(core.CODE_FIELD_INVALID, "evaluate_governance_assessment: clock debe ser callable")
    mapa = resolvers if resolvers is not None else _resolvers_por_defecto(repo_root)
    if isinstance(card_or_path, CardEnvelope):
        card = card_or_path
    else:
        try:
            card = assess.read_card(card_or_path)
        except CardError as exc:
            return _invalido("", (Hallazgo(exc.code, "file", exc.message),))
    try:
        return _evaluar(card, repo_root, base, mapa, clock)
    except CardError as exc:
        return _invalido(card.card_id, (Hallazgo(exc.code, "$", exc.message),))
    except Exception as exc:  # fail-closed
        return _invalido(card.card_id, (Hallazgo(CODE_BODY_INVALID, "$", f"evaluación falló ({type(exc).__name__})"),))


# ---------------------------------------------------------------------------
# Salida CheckResult (R52)
# ---------------------------------------------------------------------------


def a_check_results(assessment: GovernanceAssessment) -> list:
    """Mapea un `GovernanceAssessment` a `list[dsguard.checks.CheckResult]`.

    - `invalid` -> un FAIL por hallazgo.
    - requisito `required` insatisfecho -> FAIL; `recommended` -> WARN (códigos de
      requisito de la Foundation, `CARD-REQUIREMENT-*`).
    - Hallazgos de policy / riesgo (no invalidantes) y evidencia stale -> WARN.
    - `complete` -> PASS (`GOVASSESS-COMPLETE`).
    Todos los mensajes incluyen `NOTA_COMPLETENESS`; no mencionan autonomía/STOP ni
    afirman aprobación, cumplimiento o verificación."""
    if not isinstance(assessment, GovernanceAssessment):
        raise CardError(core.CODE_FIELD_INVALID, "a_check_results: se esperaba GovernanceAssessment")
    checks = assess._checks_module()
    sujeto = assessment.card_id or None
    nota = NOTA_COMPLETENESS
    resultados: list = []

    if assessment.governance_completeness == GOV_INVALID:
        for h in assessment.hallazgos:
            resultados.append(
                checks.CheckResult(
                    checks.STATUS_FAIL, h.code,
                    f"governance assessment structurally invalid at {h.path}. {nota}",
                    detail=h.detail, subject=sujeto,
                )
            )
        if not resultados:
            resultados.append(
                checks.CheckResult(
                    checks.STATUS_FAIL, core.CODE_FIELD_INVALID,
                    f"governance assessment structurally invalid. {nota}", subject=sujeto,
                )
            )
        return resultados

    for h in assessment.hallazgos:
        resultados.append(
            checks.CheckResult(
                checks.STATUS_WARN, h.code,
                f"governance assessment finding at {h.path}. {nota}", detail=h.detail, subject=sujeto,
            )
        )
    for req_id, severidad, _dim, estado, detalle in assessment.requisitos:
        if estado in (assess.REQ_SATISFIED, REQ_NOT_APPLICABLE):
            continue
        status = checks.STATUS_FAIL if severidad == "required" else checks.STATUS_WARN
        resultados.append(
            checks.CheckResult(
                status,
                assess._CODIGO_DE_REQUISITO.get(estado, core.CODE_REQUIREMENT_UNSATISFIED),
                f"governance requirement not satisfied: {req_id} ({severidad}) is {estado}. {nota}",
                detail=detalle, subject=sujeto,
            )
        )
    for ev_id, estado in assessment.evidencias:
        if estado == assess.EV_STALE:
            resultados.append(
                checks.CheckResult(
                    checks.STATUS_WARN, core.CODE_EVIDENCE_STALE,
                    f"governance evidence {ev_id} is stale (pinned hash differs from current). {nota}",
                    subject=sujeto,
                )
            )
    if assessment.governance_completeness == GOV_COMPLETE:
        resultados.append(
            checks.CheckResult(
                checks.STATUS_PASS, CODE_COMPLETE,
                f"all required governance requirements of the effective policy are satisfied. {nota}",
                subject=sujeto,
            )
        )
    elif not resultados:
        resultados.append(
            checks.CheckResult(
                checks.STATUS_WARN, core.CODE_REQUIREMENT_UNSATISFIED,
                f"governance requirements not satisfied ({assessment.governance_completeness}). {nota}",
                subject=sujeto,
            )
        )
    return resultados

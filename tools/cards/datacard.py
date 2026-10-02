"""Data Card (v0.9 Change 1, `20261002-data-cards`): especialización por
composición de la Foundation (`core` / `assess`).

Una Data Card es un `CardEnvelope(card_kind="data_card", kind_schema_version=1)`
cuyo `body` valida este módulo mediante el hook `validate_body` de Change 0.
Todo pin vive en `card.evidence`; el body solo lo referencia por `evidence_id`.

Imports: stdlib + `core` + `assess` (hermanos). `resolvers` se importa de forma
PEREZOSA dentro de `evaluate_data_card`. Este módulo:

- NO crea `governance/` al importar (R32): solo `write_data_card` crea
  directorios, al escribir.
- NO persiste requisitos ni estado (R16): `requirements_for` los deriva.
- NO escanea directorios (R28): recibe `card_id` o rutas.
- Fail-closed: nada lanza excepciones crudas hacia afuera; todo error es
  `CardError` (o `Hallazgo` en los validadores).

Limitación conocida (ver reporte): `core.Requirement` / `core.Claim` exigen ids
con `CARD_ID_PATTERN` (sin `:`), así que los ids de requisito `source:<id>` /
`contract:<id>` del spec se materializan con los prefijos `source_` /
`contract_` (constantes `REQ_PREFIJO_*`); los helpers `requirement_id_for_*`
son la única fuente de verdad del formato.

Limitaciones heredadas / documentadas:

- `title`, `Claim.statement` y los textos de atestaciones pertenecen a la
  Foundation (`core`) y NO se validan aquí (portabilidad/credenciales).
- La heurística de portabilidad de texto libre (`_motivo_texto_no_portable`)
  solo detecta rutas al INICIO (`/`, `~`, unidad de disco), barras invertidas,
  `://` y patrones de credenciales; no detecta rutas absolutas embebidas a
  mitad de una frase. Se aplica a textos del body y, recursivamente, a los
  strings bajo claves `x_*` del body y de sus sub-objetos.
- Los pins `data_contract_result` NO se ligan (por ahora) al contrato citado
  más allá de la restricción de soportes de los claims `contract_<id>`
  (subconjunto de los ids de declaración/resultado de los `contract_refs`).
- Un `contract_<id>` se deduplica entre versiones: varios `contract_refs` con
  el mismo `contract_id` y distinta versión generan UN solo requisito y un
  claim `contract_<id>` puede apoyarse en la evidencia de cualquiera de ellas.
- Los claims `source_<sref>` deben apoyarse en el `observation_evidence_id`
  de su source_ref y solo en ids de esa misma source_ref (R16); el claim de
  `ownership` no se restringe (acepta atestaciones).
- `quality_evidence_ids` es evidencia citada y evaluada por pin (stale o
  missing -> WARN en la evaluación), pero NO puede ser soporte de claims
  `contract_*`.
- Una declaración de contrato stale puede quedar enmascarada por un resultado
  fresco del mismo `contract_id` al evaluar el requisito recomendado
  `contract_<id>`; la evidencia stale igualmente se reporta.
- El hash12 del `ref_id` de provenance no se cruza con el de la observación.
- Falso fresh posible en A -> B -> A: el runtime v0.8 no reescribe un
  directorio de observación existente (la vigente se decide por
  `provenance.generated_at`), por lo que un pin de B figura fresh aunque la
  fuente haya vuelto al estado A. Limitación conocida de D6.
"""
from __future__ import annotations

import datetime as _datetime
import re
from pathlib import Path
from typing import Any, Callable, Optional

try:  # import dual: paquete (`tools.cards`) o módulo suelto con `tools/cards` en sys.path
    from . import assess, core
except ImportError:  # pragma: no cover - ejecución sin paquete padre
    import assess  # type: ignore[no-redef]
    import core  # type: ignore[no-redef]

CardError = core.CardError
CardEnvelope = core.CardEnvelope
Hallazgo = core.Hallazgo
Requirement = core.Requirement

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

DATA_CARD_KIND = "data_card"
DATA_CARD_KIND_SCHEMA_VERSION = 1

# Ubicación (R28), relativa a la raíz del proyecto.
CARD_DIR_PARTES = ("governance", "cards", "data")

# Patrones (R7): ids de core; role libre de v0.8.
ROLE_PATTERN = r"[a-z0-9][a-z0-9_-]{0,63}"
SEMVER_PATTERN = r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"

# Prefijos de requirement_id (ver nota del módulo sobre `:`).
REQ_PREFIJO_SOURCE = "source_"
REQ_PREFIJO_CONTRACT = "contract_"
REQ_OWNERSHIP = "ownership"
_MAX_ID = 64

CODE_UNKNOWN_KEY = "DATACARD-UNKNOWN-KEY"
CODE_SOURCE_REF_INCONSISTENT = "DATACARD-SOURCE-REF-INCONSISTENT"
CODE_CONTRACT_REF_INCONSISTENT = "DATACARD-CONTRACT-REF-INCONSISTENT"
CODE_DANGLING_EVIDENCE = "DATACARD-DANGLING-EVIDENCE"
CODE_SCHEMA_UNSUPPORTED = "DATACARD-SCHEMA-UNSUPPORTED"
CODE_KIND_INVALID = "DATACARD-KIND-INVALID"
CODE_BODY_INVALID = "DATACARD-BODY-INVALID"
CODE_EXISTS = "DATACARD-EXISTS"
CODE_NOT_FOUND = "DATACARD-NOT-FOUND"
CODE_PATH_INVALID = "DATACARD-PATH-INVALID"
CODE_IDENTITY_MISMATCH = "DATACARD-IDENTITY-MISMATCH"
CODE_CLAIM_SUPPORT_INCONSISTENT = "DATACARD-CLAIM-SUPPORT-INCONSISTENT"

DATACARD_CODES = (
    CODE_CLAIM_SUPPORT_INCONSISTENT,
    CODE_UNKNOWN_KEY,
    CODE_SOURCE_REF_INCONSISTENT,
    CODE_CONTRACT_REF_INCONSISTENT,
    CODE_DANGLING_EVIDENCE,
    CODE_SCHEMA_UNSUPPORTED,
    CODE_KIND_INVALID,
    CODE_BODY_INVALID,
    CODE_EXISTS,
    CODE_NOT_FOUND,
    CODE_PATH_INVALID,
    CODE_IDENTITY_MISMATCH,
)

# Claves cerradas del body (R6); `x_*` siempre permitidas.
_BODY_OBLIGATORIAS = ("description", "source_refs")
_BODY_OPCIONALES = (
    "business_meaning",
    "population",
    "unit_of_analysis",
    "derivation_note",
    "time_scope",
    "stewardship",
    "contract_refs",
    "quality_evidence_ids",
    "intended_uses",
    "out_of_scope_uses",
    "known_limitations",
)
_BODY_TEXTOS_OPCIONALES = ("business_meaning", "population", "unit_of_analysis", "derivation_note")
_BODY_LISTAS_TEXTO = ("intended_uses", "out_of_scope_uses", "known_limitations")
_TIME_SCOPE_CLAVES = ("as_of", "cutoff", "period_start", "period_end")
_STEWARDSHIP_OBLIGATORIAS = ("owner",)
_STEWARDSHIP_OPCIONALES = ("steward",)
_SOURCE_REF_OBLIGATORIAS = ("source_ref_id", "source_id", "observation_evidence_id")
_SOURCE_REF_OPCIONALES = ("role", "provenance_evidence_id", "time_scope")
_CONTRACT_REF_OBLIGATORIAS = ("contract_id", "version", "declaration_evidence_id")
_CONTRACT_REF_OPCIONALES = ("result_evidence_ids",)

_RE_ID = re.compile(core.CARD_ID_PATTERN)
_RE_ROLE = re.compile(ROLE_PATTERN)
_RE_SEMVER = re.compile(SEMVER_PATTERN)
_RE_FECHA = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


# ---------------------------------------------------------------------------
# Helpers de validación (acumulan Hallazgo; no lanzan)
# ---------------------------------------------------------------------------


def _h(out: list, code: str, path: str, detail: str) -> None:
    out.append(Hallazgo(code, path, detail))


def _strings_no_portables(valor: Any, ruta: str, out: list) -> None:
    """Recorre recursivamente `valor` (dict/list/str) y rechaza strings con la
    misma heurística de portabilidad del body (R12)."""
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
    """Claves cerradas: desconocida (salvo `x_*`) -> UNKNOWN-KEY; faltante -> BODY-INVALID.
    Los valores bajo claves `x_*` se validan recursivamente por portabilidad (R12)."""
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


def _motivo_texto_no_portable(valor: str) -> Optional[str]:
    """Reglas de portabilidad de core aplicadas a texto libre (sin exigir forma
    de locator: se permiten espacios, `/` interiores, etc.)."""
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


def _texto(valor: Any, ruta: str, out: list, multilinea: bool = False) -> bool:
    """str no vacío, sin caracteres de control y sin rutas/DSN/credenciales (R12)."""
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


def _id(valor: Any, ruta: str, out: list, patron: "re.Pattern" = _RE_ID, maximo: Optional[int] = None) -> bool:
    if not isinstance(valor, str) or patron.fullmatch(valor) is None:
        _h(out, CODE_BODY_INVALID, ruta, f"id inválido {valor!r}")
        return False
    if maximo is not None and len(valor) > maximo:
        _h(out, CODE_BODY_INVALID, ruta, f"id excede {maximo} caracteres (necesario para derivar requirement_id)")
        return False
    return True


def _fecha_o_timestamp_valido(valor: Any) -> bool:
    if core.es_timestamp_valido(valor):
        return True
    if isinstance(valor, str) and _RE_FECHA.fullmatch(valor):
        try:
            _datetime.date.fromisoformat(valor)
        except ValueError:
            return False
        return True
    return False


def _validar_time_scope(valor: Any, ruta: str, out: list) -> None:
    if not isinstance(valor, dict):
        _h(out, CODE_BODY_INVALID, ruta, "time_scope debe ser objeto")
        return
    _claves(valor, (), _TIME_SCOPE_CLAVES, ruta, out)
    for clave in _TIME_SCOPE_CLAVES:
        if clave in valor and not _fecha_o_timestamp_valido(valor[clave]):
            _h(out, CODE_BODY_INVALID, f"{ruta}.{clave}", "se esperaba fecha YYYY-MM-DD o timestamp %Y-%m-%dT%H:%M:%SZ")


def _validar_stewardship(valor: Any, ruta: str, out: list) -> None:
    if not isinstance(valor, dict):
        _h(out, CODE_BODY_INVALID, ruta, "stewardship debe ser objeto")
        return
    _claves(valor, _STEWARDSHIP_OBLIGATORIAS, _STEWARDSHIP_OPCIONALES, ruta, out)
    for clave in _STEWARDSHIP_OBLIGATORIAS + _STEWARDSHIP_OPCIONALES:
        if clave not in valor:
            continue
        item = valor[clave]
        if _texto(item, f"{ruta}.{clave}", out) and "@" in item:
            _h(out, CODE_BODY_INVALID, f"{ruta}.{clave}", "no se admiten emails ni datos de contacto personal ('@')")


def _lista_textos(valor: Any, ruta: str, out: list) -> None:
    if not isinstance(valor, list):
        _h(out, CODE_BODY_INVALID, ruta, "se esperaba lista")
        return
    for i, item in enumerate(valor):
        _texto(item, f"{ruta}[{i}]", out, multilinea=True)


def _evidencia(
    evidencias: dict, eid: Any, kind: str, ruta: str, out: list, code_inconsistente: str
) -> Optional[Any]:
    """Resuelve `eid` en la evidencia de la Card: inexistente -> DANGLING; kind
    distinto -> `code_inconsistente`. Devuelve la EvidenceRef o None."""
    if not _id(eid, ruta, out):
        return None
    ref = evidencias.get(eid)
    if ref is None:
        _h(out, CODE_DANGLING_EVIDENCE, ruta, f"evidence_id inexistente en card.evidence: {eid!r}")
        return None
    if ref.kind != kind:
        _h(out, code_inconsistente, ruta, f"{eid!r} es kind {ref.kind!r}; se esperaba {kind!r}")
        return None
    return ref


def _validar_source_refs(valor: Any, evidencias: dict, out: list) -> None:
    ruta = "$.body.source_refs"
    if not isinstance(valor, list) or not valor:
        _h(out, CODE_BODY_INVALID, ruta, "source_refs debe ser una lista no vacía")
        return
    ids_vistos: set = set()
    for i, item in enumerate(valor):
        r = f"{ruta}[{i}]"
        if not isinstance(item, dict):
            _h(out, CODE_BODY_INVALID, r, "cada source_ref debe ser objeto")
            continue
        _claves(item, _SOURCE_REF_OBLIGATORIAS, _SOURCE_REF_OPCIONALES, r, out)
        sref = item.get("source_ref_id")
        if "source_ref_id" in item and _id(sref, f"{r}.source_ref_id", out, maximo=_MAX_ID - len(REQ_PREFIJO_SOURCE)):
            if sref in ids_vistos:
                _h(out, CODE_SOURCE_REF_INCONSISTENT, f"{r}.source_ref_id", f"source_ref_id duplicado {sref!r}")
            ids_vistos.add(sref)
        source_id = item.get("source_id")
        source_ok = "source_id" in item and _id(source_id, f"{r}.source_id", out)
        if "role" in item:
            _id(item["role"], f"{r}.role", out, patron=_RE_ROLE)
        if "time_scope" in item:
            _validar_time_scope(item["time_scope"], f"{r}.time_scope", out)
        for clave, kind in (("observation_evidence_id", "source_observation"), ("provenance_evidence_id", "source_provenance")):
            if clave not in item:
                continue
            ref = _evidencia(evidencias, item[clave], kind, f"{r}.{clave}", out, CODE_SOURCE_REF_INCONSISTENT)
            if ref is not None and source_ok:
                if re.fullmatch(re.escape(source_id) + "__[0-9a-f]{12}", ref.ref_id) is None:
                    _h(
                        out,
                        CODE_SOURCE_REF_INCONSISTENT,
                        f"{r}.{clave}",
                        f"ref_id {ref.ref_id!r} no cumple {source_id}__<hash12>",
                    )
                elif kind == "source_observation" and ref.ref_id[-12:] != ref.content_sha256[:12]:
                    _h(
                        out,
                        CODE_SOURCE_REF_INCONSISTENT,
                        f"{r}.{clave}",
                        f"hash12 de ref_id {ref.ref_id!r} != content_sha256[:12] del pin",
                    )


def _validar_contract_refs(valor: Any, evidencias: dict, out: list) -> None:
    ruta = "$.body.contract_refs"
    if not isinstance(valor, list):
        _h(out, CODE_BODY_INVALID, ruta, "contract_refs debe ser lista")
        return
    for i, item in enumerate(valor):
        r = f"{ruta}[{i}]"
        if not isinstance(item, dict):
            _h(out, CODE_BODY_INVALID, r, "cada contract_ref debe ser objeto")
            continue
        _claves(item, _CONTRACT_REF_OBLIGATORIAS, _CONTRACT_REF_OPCIONALES, r, out)
        cid = item.get("contract_id")
        cid_ok = "contract_id" in item and _id(cid, f"{r}.contract_id", out, maximo=_MAX_ID - len(REQ_PREFIJO_CONTRACT))
        ver = item.get("version")
        ver_ok = False
        if "version" in item:
            if isinstance(ver, str) and _RE_SEMVER.fullmatch(ver):
                ver_ok = True
            else:
                _h(out, CODE_BODY_INVALID, f"{r}.version", f"version semver X.Y.Z inválida {ver!r}")
        if "declaration_evidence_id" in item:
            ref = _evidencia(
                evidencias, item["declaration_evidence_id"], "harmessi_contract",
                f"{r}.declaration_evidence_id", out, CODE_CONTRACT_REF_INCONSISTENT,
            )
            if ref is not None and cid_ok and ver_ok and ref.ref_id != f"{cid}@{ver}":
                _h(
                    out,
                    CODE_CONTRACT_REF_INCONSISTENT,
                    f"{r}.declaration_evidence_id",
                    f"ref_id {ref.ref_id!r} != {cid}@{ver}",
                )
        if "result_evidence_ids" in item:
            rids = item["result_evidence_ids"]
            if not isinstance(rids, list):
                _h(out, CODE_BODY_INVALID, f"{r}.result_evidence_ids", "se esperaba lista")
            else:
                for j, rid in enumerate(rids):
                    _evidencia(
                        evidencias, rid, "data_contract_result",
                        f"{r}.result_evidence_ids[{j}]", out, CODE_CONTRACT_REF_INCONSISTENT,
                    )


def _validar_claims(body: Any, claims: Any, out: list) -> None:
    """Coherencia claims <-> body (R16). Claims `source_<sref>`: sref existente,
    `supports` incluye el `observation_evidence_id` y solo ids de ESA source_ref.
    Claims `contract_<id>`: `supports` subconjunto de los ids de declaración y
    resultado de los `contract_refs` con ese `contract_id`. `ownership` libre."""
    if not isinstance(body, dict):
        return
    por_sref: dict = {}
    refs = body.get("source_refs")
    for item in refs if isinstance(refs, list) else []:
        if not isinstance(item, dict) or not isinstance(item.get("source_ref_id"), str):
            continue
        propios = {item.get(c) for c in ("observation_evidence_id", "provenance_evidence_id") if isinstance(item.get(c), str)}
        por_sref.setdefault(item["source_ref_id"], (item.get("observation_evidence_id"), propios))
    por_contrato: dict = {}
    crefs = body.get("contract_refs")
    for item in crefs if isinstance(crefs, list) else []:
        if not isinstance(item, dict) or not isinstance(item.get("contract_id"), str):
            continue
        ids = por_contrato.setdefault(item["contract_id"], set())
        if isinstance(item.get("declaration_evidence_id"), str):
            ids.add(item["declaration_evidence_id"])
        rids = item.get("result_evidence_ids")
        for rid in rids if isinstance(rids, list) else []:
            if isinstance(rid, str):
                ids.add(rid)
    for i, claim in enumerate(claims if isinstance(claims, (list, tuple)) else ()):
        rid = getattr(claim, "requirement_id", None)
        if not isinstance(rid, str):
            continue
        ruta = f"$.claims[{i}]"
        soportes = set(getattr(claim, "supports", ()) or ())
        if rid.startswith(REQ_PREFIJO_SOURCE):
            sref = rid[len(REQ_PREFIJO_SOURCE):]
            if sref not in por_sref:
                _h(out, CODE_CLAIM_SUPPORT_INCONSISTENT, ruta, f"claim {rid!r} refiere a una source_ref inexistente")
                continue
            obs_id, propios = por_sref[sref]
            if not isinstance(obs_id, str) or obs_id not in soportes:
                _h(out, CODE_CLAIM_SUPPORT_INCONSISTENT, f"{ruta}.supports",
                   f"claim {rid!r} debe incluir el observation_evidence_id de su source_ref")
            ajenos = soportes - propios
            if ajenos:
                _h(out, CODE_CLAIM_SUPPORT_INCONSISTENT, f"{ruta}.supports",
                   f"claim {rid!r} incluye soportes ajenos a su source_ref: {sorted(ajenos)}")
        elif rid.startswith(REQ_PREFIJO_CONTRACT):
            permitidos = por_contrato.get(rid[len(REQ_PREFIJO_CONTRACT):], set())
            ajenos = soportes - permitidos
            if ajenos:
                _h(out, CODE_CLAIM_SUPPORT_INCONSISTENT, f"{ruta}.supports",
                   f"claim {rid!r} incluye soportes que no son de sus contract_refs: {sorted(ajenos)}")


def _validar_body(body: Any, evidencias: dict, claims: Any = ()) -> list:
    out: list = []
    if not isinstance(body, dict):
        return [Hallazgo(CODE_BODY_INVALID, "$.body", "body debe ser objeto")]
    _claves(body, _BODY_OBLIGATORIAS, _BODY_OPCIONALES, "$.body", out)
    if "description" in body:
        _texto(body["description"], "$.body.description", out, multilinea=True)
    for clave in _BODY_TEXTOS_OPCIONALES:
        if clave in body:
            _texto(body[clave], f"$.body.{clave}", out, multilinea=True)
    if "source_refs" in body:
        _validar_source_refs(body["source_refs"], evidencias, out)
    if "time_scope" in body:
        _validar_time_scope(body["time_scope"], "$.body.time_scope", out)
    if "stewardship" in body:
        _validar_stewardship(body["stewardship"], "$.body.stewardship", out)
    if "contract_refs" in body:
        _validar_contract_refs(body["contract_refs"], evidencias, out)
    if "quality_evidence_ids" in body:
        ids = body["quality_evidence_ids"]
        if not isinstance(ids, list):
            _h(out, CODE_BODY_INVALID, "$.body.quality_evidence_ids", "se esperaba lista")
        else:
            for j, eid in enumerate(ids):
                _evidencia(
                    evidencias, eid, "quality_evidence",
                    f"$.body.quality_evidence_ids[{j}]", out, CODE_BODY_INVALID,
                )
    for clave in _BODY_LISTAS_TEXTO:
        if clave in body:
            _lista_textos(body[clave], f"$.body.{clave}", out)
    _validar_claims(body, claims, out)
    return out


# ---------------------------------------------------------------------------
# API pública: validación
# ---------------------------------------------------------------------------


def _hallazgos_card(card: Any) -> list:
    """Chequeos de kind / kind_schema_version / body de una Card (sin lanzar)."""
    if not isinstance(card, CardEnvelope):
        return [Hallazgo(core.CODE_FIELD_INVALID, "$", f"se esperaba CardEnvelope, se recibió {type(card).__name__}")]
    if card.card_kind != DATA_CARD_KIND:
        return [Hallazgo(CODE_KIND_INVALID, "$.card_kind", f"se esperaba card_kind {DATA_CARD_KIND!r}, no {card.card_kind!r}")]
    if card.kind_schema_version != DATA_CARD_KIND_SCHEMA_VERSION:
        return [
            Hallazgo(
                CODE_SCHEMA_UNSUPPORTED,
                "$.kind_schema_version",
                f"kind_schema_version {card.kind_schema_version!r} no soportado (se espera {DATA_CARD_KIND_SCHEMA_VERSION})",
            )
        ]
    evidencias = {e.evidence_id: e for e in card.evidence}
    return _validar_body(card.body, evidencias, card.claims)


def body_validator_for(card: Any) -> Callable[[dict], list]:
    """Devuelve `validate_body(body) -> list[Hallazgo]` (hook de Change 0) que
    cierra sobre la evidencia de `card`. Además de validar el body chequea que la
    Card sea `data_card` con `kind_schema_version == 1` (el hook de core solo
    recibe el body, así que esos chequeos viajan en el closure), y la coherencia
    de los claims de la Card con el body (`DATACARD-CLAIM-SUPPORT-INCONSISTENT`,
    R16). Fail-closed:
    cualquier excepción -> hallazgo `DATACARD-BODY-INVALID`."""
    if isinstance(card, CardEnvelope):
        evidencias = {e.evidence_id: e for e in card.evidence}
        kind, ksv = card.card_kind, card.kind_schema_version
        claims = tuple(card.claims)
    else:
        evidencias, kind, ksv, claims = None, None, None, ()

    def validate_body(body: Any) -> list:
        try:
            if evidencias is None:
                return [Hallazgo(core.CODE_FIELD_INVALID, "$", "body_validator_for: se esperaba CardEnvelope")]
            if kind != DATA_CARD_KIND:
                return [Hallazgo(CODE_KIND_INVALID, "$.card_kind", f"se esperaba card_kind {DATA_CARD_KIND!r}, no {kind!r}")]
            if ksv != DATA_CARD_KIND_SCHEMA_VERSION:
                return [Hallazgo(CODE_SCHEMA_UNSUPPORTED, "$.kind_schema_version", f"kind_schema_version {ksv!r} no soportado")]
            return _validar_body(body, evidencias, claims)
        except Exception as exc:  # fail-closed
            return [Hallazgo(CODE_BODY_INVALID, "$.body", f"validación del body falló ({type(exc).__name__})")]

    return validate_body


def validate_data_card(card: Any) -> list:
    """Hallazgos de la Data Card: kind == data_card, kind_schema_version == 1 y
    body (con coherencia de evidencia). Lista vacía = válida. No lanza.
    Los chequeos estructurales de la Foundation (`core.validate_card`) los hace
    `assess.evaluate` / `write_card`."""
    try:
        return _hallazgos_card(card)
    except Exception as exc:  # fail-closed
        return [Hallazgo(CODE_BODY_INVALID, "$.body", f"validación falló ({type(exc).__name__})")]


# ---------------------------------------------------------------------------
# Requisitos derivados (R15, R16)
# ---------------------------------------------------------------------------


def requirement_id_for_source(source_ref_id: str) -> str:
    """requirement_id del claim que cubre una fuente (`source:<id>` del spec)."""
    return REQ_PREFIJO_SOURCE + source_ref_id


def requirement_id_for_contract(contract_id: str) -> str:
    """requirement_id del claim que cubre un contrato (`contract:<id>` del spec)."""
    return REQ_PREFIJO_CONTRACT + contract_id


def requirements_for(card: Any) -> tuple:
    """`Requirement`s DERIVADOS del body (nunca persistidos). Por cada
    `source_ref`: `required` empírico (`observed`, `source_observation`).
    Siempre `ownership` (`recommended`, `attestation`, min `declared`). Por cada
    `contract_id` distinto en `contract_refs`: `recommended` empírico. Items
    malformados se ignoran (la Card es `invalid` por el validador de body).
    Lanza `CardError` solo si no se recibe una Card."""
    if not isinstance(card, CardEnvelope):
        raise CardError(core.CODE_FIELD_INVALID, "requirements_for: se esperaba CardEnvelope")
    body = card.body if isinstance(card.body, dict) else {}
    reqs: list = []
    vistos: set = set()
    refs = body.get("source_refs")
    for item in refs if isinstance(refs, list) else []:
        sref = item.get("source_ref_id") if isinstance(item, dict) else None
        if not isinstance(sref, str):
            continue
        rid = requirement_id_for_source(sref)
        if rid in vistos:
            continue
        vistos.add(rid)
        reqs.append(Requirement(rid, "required", ("observed",), ("source_observation",)))
    reqs.append(Requirement(REQ_OWNERSHIP, "recommended", ("attestation",), None, "declared"))
    crefs = body.get("contract_refs")
    for item in crefs if isinstance(crefs, list) else []:
        cid = item.get("contract_id") if isinstance(item, dict) else None
        if not isinstance(cid, str):
            continue
        rid = requirement_id_for_contract(cid)
        if rid in vistos:
            continue
        vistos.add(rid)
        reqs.append(
            Requirement(
                rid, "recommended", ("observed",),
                ("harmessi_contract", "data_contract_result", "quality_evidence"),
            )
        )
    return tuple(reqs)


# ---------------------------------------------------------------------------
# Ubicación y escritura (R28, R30, R32)
# ---------------------------------------------------------------------------


def card_path(project_root: Any, card_id: str) -> Path:
    """`<project_root>/governance/cards/data/<card_id>.json`. Valida `card_id`
    (patrón de core, no reservado) y que el resultado quede dentro de
    `project_root` (incluso resolviendo symlinks). No toca el filesystem
    más que para resolver rutas; no escanea ni crea nada."""
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
    """`ruta.exists()` que nunca deja salir un OSError crudo (-> `CardError`)."""
    try:
        return ruta.exists()
    except OSError as exc:
        raise CardError(core.CODE_IO_ERROR, f"no se pudo comprobar {ruta.name} ({type(exc).__name__})") from exc


def _es_archivo(ruta: Path) -> bool:
    """`ruta.is_file()` que nunca deja salir un OSError crudo (-> `CardError`)."""
    try:
        return ruta.is_file()
    except OSError as exc:
        raise CardError(core.CODE_IO_ERROR, f"no se pudo comprobar {ruta.name} ({type(exc).__name__})") from exc


def write_data_card(
    project_root: Any,
    card: Any,
    *,
    replace: bool = False,
    clock: Optional[Callable[[], str]] = None,
) -> Path:
    """Escribe la Data Card en `card_path(project_root, card.card_id)`.

    - Valida ANTES de tocar el filesystem (Card inválida -> `CardError`, sin
      crear `governance/`).
    - `replace=False`: crea directorios y escribe con `write_card(exclusive=True)`;
      si existe cualquier archivo -> `DATACARD-EXISTS`, sin sobrescribir.
    - `replace=True`: exige un archivo existente que sea una Card legible del
      MISMO `card_id` (y `data_card`); si no -> `DATACARD-NOT-FOUND` /
      `DATACARD-IDENTITY-MISMATCH`, sin escribir.
    """
    if not isinstance(card, CardEnvelope):
        raise CardError(core.CODE_FIELD_INVALID, "write_data_card: se esperaba CardEnvelope")
    reloj = clock if clock is not None else assess._reloj_utc
    validador = body_validator_for(card)
    hallazgos = core.validate_card(card, clock=reloj, validate_body=validador)
    if hallazgos:
        resumen = "; ".join(f"{h.code} {h.path}: {h.detail}" for h in hallazgos)
        raise CardError(hallazgos[0].code, f"Data Card inválida, no se escribe: {resumen}")
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
        if existente.card_id != card.card_id or existente.card_kind != DATA_CARD_KIND:
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
        raise CardError(core.CODE_IO_ERROR, f"no se pudo crear el directorio de Cards ({type(exc).__name__})") from exc
    try:
        return assess.write_card(destino, card, reloj, validate_body=validador, exclusive=True)
    except CardError as exc:
        # DATACARD-EXISTS solo para existencia real; si el destino no existe se
        # deja el CardError original (p. ej. CARD-IO-ERROR por FS sin hard links).
        if exc.code == core.CODE_IO_ERROR and _existe(destino):
            raise CardError(CODE_EXISTS, f"{destino.name} ya existe; no se sobrescribe") from exc
        raise


# ---------------------------------------------------------------------------
# Evaluación (R34)
# ---------------------------------------------------------------------------


def _resolvers_por_defecto(repo_root: Any) -> dict:
    """Import perezoso de `resolvers.default_resolvers`. Módulo ausente ->
    mapa vacío (todo `unverifiable`, fail-closed). Otro error -> `CardError`."""
    try:
        try:
            from . import resolvers as _resolvers
        except ImportError:  # pragma: no cover - ejecución sin paquete padre
            import resolvers as _resolvers  # type: ignore[no-redef]
    except ImportError:
        return {}
    try:
        return dict(_resolvers.default_resolvers(repo_root))
    except CardError:
        raise
    except Exception as exc:  # fail-closed
        raise CardError(core.CODE_FIELD_INVALID, f"default_resolvers falló ({type(exc).__name__})") from exc


def evaluate_data_card(card_or_path: Any, repo_root: Any, clock: Optional[Callable[[], str]] = None):
    """Azúcar sobre `assess.evaluate`/`evaluate_file`: cablea `requirements_for`,
    `default_resolvers(repo_root)` y `body_validator_for`. Un archivo ilegible o
    una Card inválida -> `CardAssessment(card_status="invalid")`; nunca
    excepción cruda ni PASS."""
    if isinstance(card_or_path, CardEnvelope):
        card = card_or_path
    else:
        try:
            card = assess.read_card(card_or_path)
        except CardError as exc:
            return assess.CardAssessment(
                card_status=assess.CARD_INVALID,
                hallazgos=(Hallazgo(exc.code, "file", exc.message),),
                sin_requisitos=True,
                card_id="",
            )
    try:
        reqs = requirements_for(card)
        resolvers = _resolvers_por_defecto(repo_root)
        return assess.evaluate(card, reqs, resolvers, clock, validate_body=body_validator_for(card))
    except CardError as exc:
        return assess.CardAssessment(
            card_status=assess.CARD_INVALID,
            hallazgos=(Hallazgo(exc.code, "$", exc.message),),
            sin_requisitos=True,
            card_id=card.card_id,
        )

"""Model Card (v0.9 Change 2, `20261005-model-cards`): especialización por
composición de la Foundation (`core` / `assess`), espejo de `datacard.py`.

Una Model Card es un `CardEnvelope(card_kind="model_card", kind_schema_version=1)`
que documenta UNA versión de un modelo (`card_id` derivado de `model_id` +
`model_version`, ver `model_card_id` / `decode_model_card_id`). Su `body` lo
valida este módulo mediante el hook `validate_body` de Change 0. Todo pin vive en
`card.evidence`; el body solo lo referencia por `evidence_id`.

Imports: stdlib + `core` + `assess` (hermanos). `resolvers` se importa de forma
PEREZOSA dentro de `evaluate_model_card`. Este módulo:

- NO crea `governance/` al importar ni al validar (R34): solo `write_model_card`
  crea directorios, al escribir.
- NO persiste requisitos ni estado: `requirements_for` los deriva.
- NO escanea directorios ni mantiene registry/índice de modelos (R10).
- Fail-closed: nada lanza excepciones crudas hacia afuera; todo error es
  `CardError` (o `Hallazgo` en los validadores).

Qué NO significa una Card `complete` (R22):

- `complete` NO significa modelo bueno, seguro, justo (fair), aprobado ni listo
  para producción. Solo informa que lo que la Card cita (pins) está respaldado
  por evidencia vigente y por claims coherentes.
- No se comparan valores de métricas, umbrales ni baselines: ni
  `requirements_for` ni la evaluación leen valores ni emiten «bueno/malo».
- El pin de Data Card valida identidad, existencia, integridad y revisión
  pineada; NO hereda el estado de governance de la Data Card citada.
- Staleness por pin exacto, sin semántica «latest»: la Card solo queda stale si
  cambia lo que pineó, no porque exista evidencia más nueva.
- Qué evidencia debe EXISTIR para un modelo (riesgo, política) queda fuera de
  este módulo (Change 3); aquí «declarar implica respaldar».

Limitaciones heredadas / documentadas:

- `title`, `Claim.statement` y los textos de atestaciones pertenecen a la
  Foundation (`core`) y NO se validan aquí (portabilidad/credenciales).
- La heurística de portabilidad de texto libre (`_motivo_texto_no_portable`)
  solo detecta rutas al INICIO (`/`, `~`, unidad de disco), barras invertidas,
  `://` y patrones de credenciales; no detecta rutas absolutas embebidas a
  mitad de una frase. Se aplica a textos del body y, recursivamente, a los
  strings bajo claves `x_*` del body y de sus sub-objetos.
- `core.Requirement` / `core.Claim` exigen ids con `CARD_ID_PATTERN` (≤ 64): el
  requisito `evidence_<evidence_id>` obliga a `evidence_id` ≤ 55 caracteres.
- `ref_id` de pins `observed_metric` / `baseline_reference` no se valida más
  allá de exigir `member` y `locator` (la identidad real es el `member`).
- Un pin presente en `card.evidence` pero NO citado desde el body no genera
  requisito (solo se reporta como WARN de evidencia stale), coherente con
  «declarar implica respaldar».
- `write_model_card(replace=True)` con otra `model_version` apunta a otro
  `card_id`/archivo, por lo que devuelve MODELCARD-NOT-FOUND (nunca escribe
  sobre la Card de otra versión); MODELCARD-IDENTITY-MISMATCH aplica cuando hay
  un archivo de otra identidad en esa ruta.
- Ventana TOCTOU residual en `replace` (comprobación de identidad y escritura no
  son atómicas), consistente con la Foundation.
- Falso fresh posible en A -> B -> A para evidencia cuyo artefacto se reescribe
  con el mismo hash: el pin solo compara hash, no historia.
"""
from __future__ import annotations

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

MODEL_CARD_KIND = "model_card"
MODEL_CARD_KIND_SCHEMA_VERSION = 1

# Ubicación (R32), relativa a la raíz del proyecto.
CARD_DIR_PARTES = ("governance", "cards", "model")
_DATA_CARD_DIR = "governance/cards/data"

# Patrones de identidad (R7).
MODEL_ID_PATTERN = r"[a-z0-9]+([_-][a-z0-9]+)*"
MODEL_VERSION_PATTERN = r"[a-z0-9]+([.-][a-z0-9]+)*"
CARD_ID_SEPARATOR = "__"
_MAX_ID = 64

# Patrones de ids libres.
ROLE_PATTERN = r"[a-z0-9][a-z0-9_-]{0,63}"
TASK_ROLE_PATTERN = r"[a-z][a-z0-9_]*"

REQ_PREFIJO_EVIDENCE = "evidence_"
REQ_OWNERSHIP = "ownership"
_MAX_EVIDENCE_ID = _MAX_ID - len(REQ_PREFIJO_EVIDENCE)

CODE_UNKNOWN_KEY = "MODELCARD-UNKNOWN-KEY"
CODE_IDENTITY_INVALID = "MODELCARD-IDENTITY-INVALID"
CODE_IDENTITY_MISMATCH = "MODELCARD-IDENTITY-MISMATCH"
CODE_DANGLING_EVIDENCE = "MODELCARD-DANGLING-EVIDENCE"
CODE_REF_INCONSISTENT = "MODELCARD-REF-INCONSISTENT"
CODE_CLAIM_SUPPORT_INCONSISTENT = "MODELCARD-CLAIM-SUPPORT-INCONSISTENT"
CODE_SCHEMA_UNSUPPORTED = "MODELCARD-SCHEMA-UNSUPPORTED"
CODE_KIND_INVALID = "MODELCARD-KIND-INVALID"
CODE_BODY_INVALID = "MODELCARD-BODY-INVALID"
CODE_EXISTS = "MODELCARD-EXISTS"
CODE_NOT_FOUND = "MODELCARD-NOT-FOUND"
CODE_PATH_INVALID = "MODELCARD-PATH-INVALID"

MODELCARD_CODES = (
    CODE_UNKNOWN_KEY,
    CODE_IDENTITY_INVALID,
    CODE_IDENTITY_MISMATCH,
    CODE_DANGLING_EVIDENCE,
    CODE_REF_INCONSISTENT,
    CODE_CLAIM_SUPPORT_INCONSISTENT,
    CODE_SCHEMA_UNSUPPORTED,
    CODE_KIND_INVALID,
    CODE_BODY_INVALID,
    CODE_EXISTS,
    CODE_NOT_FOUND,
    CODE_PATH_INVALID,
)

# Claves cerradas del body (R11-R17); `x_*` siempre permitidas.
_BODY_OBLIGATORIAS = ("model_id", "model_version", "description")
_BODY_OPCIONALES = (
    "task",
    "population",
    "intended_uses",
    "out_of_scope_uses",
    "known_limitations",
    "stewardship",
    "data_card_refs",
    "evaluation_refs",
    "provenance_refs",
)
_BODY_LISTAS_TEXTO = ("intended_uses", "out_of_scope_uses", "known_limitations")
_TASK_OBLIGATORIAS = ("role",)
_TASK_OPCIONALES = ("description", "target_reference", "output_meaning")
_STEWARDSHIP_OBLIGATORIAS = ("owner",)
_STEWARDSHIP_OPCIONALES = ("steward",)
_DCREF_OBLIGATORIAS = ("data_card_ref_id", "role", "evidence_id")
_DCREF_OPCIONALES: tuple = ()
_EVREF_OBLIGATORIAS = ("evaluation_ref_id",)
_EVREF_OPCIONALES = (
    "role",
    "result_evidence_id",
    "policy_evidence_id",
    "metric_evidence_ids",
    "baseline_evidence_ids",
    "drift_evidence_ids",
)
_PROVREF_OBLIGATORIAS = ("provenance_ref_id", "evidence_id")
_PROVREF_OPCIONALES = ("role",)

# Kinds de pin esperados por campo.
_KIND_DATA_CARD = "data_card"
_KIND_RESULT = "model_quality_result"
_KIND_POLICY = "model_quality_policy"
_KIND_METRIC = "observed_metric"
_KIND_BASELINE = "baseline_reference"
_KIND_DRIFT = "drift_evidence"
_KINDS_PROVENANCE = ("execution_record", "report_artifact")

_RE_ID = re.compile(core.CARD_ID_PATTERN)
_RE_ROLE = re.compile(ROLE_PATTERN)
_RE_TASK_ROLE = re.compile(TASK_ROLE_PATTERN)
_RE_MODEL_ID = re.compile(MODEL_ID_PATTERN)
_RE_MODEL_VERSION = re.compile(MODEL_VERSION_PATTERN)
_RE_DATA_CARD_REF = re.compile(r"(?P<cid>" + core.CARD_ID_PATTERN + r")__(?P<h>[0-9a-f]{12})")
_RE_RESULT_REF = re.compile(r"qe-\d{8}T\d{6}Z-[0-9a-f]{6}")
_RE_DRIFT_REF = re.compile(r"dr-\d{8}T\d{6}Z-[0-9a-f]{6}")


# ---------------------------------------------------------------------------
# Identidad (R6-R9)
# ---------------------------------------------------------------------------


def _problemas_identidad(model_id: Any, model_version: Any) -> list:
    """Motivos (str) por los que el par no es una identidad válida. Vacío = válida."""
    motivos: list = []
    if not isinstance(model_id, str) or _RE_MODEL_ID.fullmatch(model_id) is None:
        motivos.append(f"model_id inválido {model_id!r} (patrón {MODEL_ID_PATTERN}, sin '__')")
    if not isinstance(model_version, str) or _RE_MODEL_VERSION.fullmatch(model_version) is None:
        motivos.append(
            f"model_version inválida {model_version!r} (patrón {MODEL_VERSION_PATTERN}; minúsculas, sin '_')"
        )
    if not motivos:
        total = len(model_id) + len(CARD_ID_SEPARATOR) + len(model_version)
        if total > _MAX_ID:
            motivos.append(
                f"len(model_id) + 2 + len(model_version) = {total} excede el presupuesto de {_MAX_ID} "
                "caracteres del card_id"
            )
    return motivos


def model_card_id(model_id: str, model_version: str) -> str:
    """`card_id` derivado y reversible: `model_id + "__" + model_version` con `.`
    reemplazado por `_`. Lanza `CardError(MODELCARD-IDENTITY-INVALID)` si el par
    no cumple los patrones o el presupuesto de 64 caracteres."""
    motivos = _problemas_identidad(model_id, model_version)
    if motivos:
        raise CardError(CODE_IDENTITY_INVALID, "model_card_id: " + "; ".join(motivos))
    return model_id + CARD_ID_SEPARATOR + model_version.replace(".", "_")


def decode_model_card_id(card_id: str) -> tuple:
    """Inversa de `model_card_id`: `(model_id, model_version)`. Parte en el único
    `__` y repone `.` donde la versión codificada tenía `_`. Lanza
    `CardError(MODELCARD-IDENTITY-INVALID)` si `card_id` no es decodificable."""
    if not isinstance(card_id, str) or card_id.count(CARD_ID_SEPARATOR) != 1:
        raise CardError(CODE_IDENTITY_INVALID, f"decode_model_card_id: card_id no decodificable {card_id!r}")
    model_id, codificada = card_id.split(CARD_ID_SEPARATOR)
    model_version = codificada.replace("_", ".")
    motivos = _problemas_identidad(model_id, model_version)
    if motivos or model_card_id(model_id, model_version) != card_id:
        raise CardError(CODE_IDENTITY_INVALID, f"decode_model_card_id: card_id no decodificable {card_id!r}")
    return model_id, model_version


# ---------------------------------------------------------------------------
# Helpers de validación (acumulan Hallazgo; no lanzan)
# ---------------------------------------------------------------------------


def _h(out: list, code: str, path: str, detail: str) -> None:
    out.append(Hallazgo(code, path, detail))


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


def _strings_no_portables(valor: Any, ruta: str, out: list) -> None:
    """Recorre recursivamente `valor` (dict/list/str) y rechaza strings con la
    misma heurística de portabilidad del body."""
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
    Los valores bajo claves `x_*` se validan recursivamente por portabilidad."""
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


def _id(valor: Any, ruta: str, out: list, patron: "re.Pattern" = _RE_ID, maximo: Optional[int] = None) -> bool:
    if not isinstance(valor, str) or patron.fullmatch(valor) is None:
        _h(out, CODE_BODY_INVALID, ruta, f"id inválido {valor!r}")
        return False
    if maximo is not None and len(valor) > maximo:
        _h(out, CODE_BODY_INVALID, ruta, f"id excede {maximo} caracteres (necesario para derivar requirement_id)")
        return False
    return True


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


def _validar_task(valor: Any, ruta: str, out: list) -> None:
    if not isinstance(valor, dict):
        _h(out, CODE_BODY_INVALID, ruta, "task debe ser objeto")
        return
    _claves(valor, _TASK_OBLIGATORIAS, _TASK_OPCIONALES, ruta, out)
    if "role" in valor:
        _id(valor["role"], f"{ruta}.role", out, patron=_RE_TASK_ROLE)
    for clave in _TASK_OPCIONALES:
        if clave in valor:
            _texto(valor[clave], f"{ruta}.{clave}", out, multilinea=True)


def _lista_textos(valor: Any, ruta: str, out: list) -> None:
    if not isinstance(valor, list):
        _h(out, CODE_BODY_INVALID, ruta, "se esperaba lista")
        return
    for i, item in enumerate(valor):
        _texto(item, f"{ruta}[{i}]", out, multilinea=True)


def _evidencia(
    evidencias: dict, eid: Any, kinds: tuple, ruta: str, out: list
) -> Optional[Any]:
    """Resuelve `eid` en la evidencia de la Card: inexistente -> DANGLING; kind
    fuera de `kinds` -> REF-INCONSISTENT. Devuelve la EvidenceRef o None."""
    if not _id(eid, ruta, out, maximo=_MAX_EVIDENCE_ID):
        return None
    ref = evidencias.get(eid)
    if ref is None:
        _h(out, CODE_DANGLING_EVIDENCE, ruta, f"evidence_id inexistente en card.evidence: {eid!r}")
        return None
    if ref.kind not in kinds:
        esperado = kinds[0] if len(kinds) == 1 else " o ".join(kinds)
        _h(out, CODE_REF_INCONSISTENT, ruta, f"{eid!r} es kind {ref.kind!r}; se esperaba {esperado!r}")
        return None
    return ref


def _id_local_unico(item: dict, clave: str, vistos: set, ruta: str, out: list) -> None:
    if clave not in item:
        return
    valor = item[clave]
    if not _id(valor, f"{ruta}.{clave}", out):
        return
    if valor in vistos:
        _h(out, CODE_REF_INCONSISTENT, f"{ruta}.{clave}", f"{clave} duplicado {valor!r}")
    vistos.add(valor)


def _validar_ref_data_card(ref: Any, ruta: str, out: list) -> None:
    coincide = _RE_DATA_CARD_REF.fullmatch(ref.ref_id)
    if coincide is None:
        _h(out, CODE_REF_INCONSISTENT, ruta, f"ref_id {ref.ref_id!r} no cumple <card_id>__<hash12>")
        return
    if coincide.group("h") != ref.content_sha256[:12]:
        _h(out, CODE_REF_INCONSISTENT, ruta, f"hash12 de ref_id {ref.ref_id!r} != content_sha256[:12] del pin")
    if ref.locator is not None and ref.locator != f"{_DATA_CARD_DIR}/{coincide.group('cid')}.json":
        _h(out, CODE_REF_INCONSISTENT, ruta, f"locator {ref.locator!r} != {_DATA_CARD_DIR}/{coincide.group('cid')}.json")


def _validar_ref_patron(ref: Any, patron: "re.Pattern", etiqueta: str, ruta: str, out: list) -> None:
    if patron.fullmatch(ref.ref_id) is None:
        _h(out, CODE_REF_INCONSISTENT, ruta, f"ref_id {ref.ref_id!r} no cumple el patrón de {etiqueta}")


def _validar_ref_miembro(ref: Any, kind: str, ruta: str, out: list) -> None:
    """observed_metric / baseline_reference: el pin lleva `member` y `locator` (R26)."""
    if not ref.member:
        _h(out, CODE_REF_INCONSISTENT, ruta, f"el pin {kind} debe llevar 'member'")
    elif kind == _KIND_METRIC:
        nombre, sep, contexto = ref.member.partition("@")
        if not sep or not nombre or not contexto or "@" in contexto:
            _h(out, CODE_REF_INCONSISTENT, ruta, f"member {ref.member!r} debe ser <metric_name>@<context_id>")
    elif "@" in ref.member:
        _h(out, CODE_REF_INCONSISTENT, ruta, f"member {ref.member!r} de baseline_reference debe ser <baseline_id>")
    if not ref.locator:
        _h(out, CODE_REF_INCONSISTENT, ruta, f"el pin {kind} debe llevar 'locator'")


def _validar_lista_refs(valor: Any, ruta: str, out: list) -> list:
    """Valida que `valor` sea lista de dicts; devuelve [(índice, item)] válidos."""
    if not isinstance(valor, list):
        _h(out, CODE_BODY_INVALID, ruta, "se esperaba lista")
        return []
    items: list = []
    for i, item in enumerate(valor):
        if not isinstance(item, dict):
            _h(out, CODE_BODY_INVALID, f"{ruta}[{i}]", "cada elemento debe ser objeto")
        else:
            items.append((i, item))
    return items


def _validar_data_card_refs(valor: Any, evidencias: dict, out: list) -> None:
    ruta = "$.body.data_card_refs"
    vistos: set = set()
    for i, item in _validar_lista_refs(valor, ruta, out):
        r = f"{ruta}[{i}]"
        _claves(item, _DCREF_OBLIGATORIAS, _DCREF_OPCIONALES, r, out)
        _id_local_unico(item, "data_card_ref_id", vistos, r, out)
        if "role" in item:
            _id(item["role"], f"{r}.role", out, patron=_RE_ROLE)
        if "evidence_id" in item:
            ref = _evidencia(evidencias, item["evidence_id"], (_KIND_DATA_CARD,), f"{r}.evidence_id", out)
            if ref is not None:
                _validar_ref_data_card(ref, f"{r}.evidence_id", out)


def _validar_evaluation_refs(valor: Any, evidencias: dict, out: list) -> None:
    ruta = "$.body.evaluation_refs"
    vistos: set = set()
    for i, item in _validar_lista_refs(valor, ruta, out):
        r = f"{ruta}[{i}]"
        _claves(item, _EVREF_OBLIGATORIAS, _EVREF_OPCIONALES, r, out)
        _id_local_unico(item, "evaluation_ref_id", vistos, r, out)
        if "role" in item:
            _id(item["role"], f"{r}.role", out, patron=_RE_ROLE)
        pines = 0
        for clave, kind, patron, etiqueta in (
            ("result_evidence_id", _KIND_RESULT, _RE_RESULT_REF, "evidence_id de calidad (qe-…)"),
            ("policy_evidence_id", _KIND_POLICY, None, ""),
        ):
            if clave not in item:
                continue
            pines += 1
            ref = _evidencia(evidencias, item[clave], (kind,), f"{r}.{clave}", out)
            if ref is not None and patron is not None:
                _validar_ref_patron(ref, patron, etiqueta, f"{r}.{clave}", out)
        for clave, kind in (
            ("metric_evidence_ids", _KIND_METRIC),
            ("baseline_evidence_ids", _KIND_BASELINE),
            ("drift_evidence_ids", _KIND_DRIFT),
        ):
            if clave not in item:
                continue
            ids = item[clave]
            if not isinstance(ids, list):
                _h(out, CODE_BODY_INVALID, f"{r}.{clave}", "se esperaba lista")
                continue
            pines += len(ids)
            vistos_lista: set = set()
            for j, eid in enumerate(ids):
                rr = f"{r}.{clave}[{j}]"
                ref = _evidencia(evidencias, eid, (kind,), rr, out)
                if isinstance(eid, str):
                    if eid in vistos_lista:
                        _h(out, CODE_REF_INCONSISTENT, rr, f"evidence_id duplicado {eid!r}")
                    vistos_lista.add(eid)
                if ref is None:
                    continue
                if kind == _KIND_DRIFT:
                    _validar_ref_patron(ref, _RE_DRIFT_REF, "drift_id (dr-…)", rr, out)
                else:
                    _validar_ref_miembro(ref, kind, rr, out)
        if pines == 0:
            _h(out, CODE_BODY_INVALID, r, "evaluation_ref debe citar al menos un pin de evidencia")


def _validar_provenance_refs(valor: Any, evidencias: dict, out: list) -> None:
    ruta = "$.body.provenance_refs"
    vistos: set = set()
    for i, item in _validar_lista_refs(valor, ruta, out):
        r = f"{ruta}[{i}]"
        _claves(item, _PROVREF_OBLIGATORIAS, _PROVREF_OPCIONALES, r, out)
        _id_local_unico(item, "provenance_ref_id", vistos, r, out)
        if "role" in item:
            _id(item["role"], f"{r}.role", out, patron=_RE_ROLE)
        if "evidence_id" in item:
            _evidencia(evidencias, item["evidence_id"], _KINDS_PROVENANCE, f"{r}.evidence_id", out)


# ---------------------------------------------------------------------------
# Pins citados y requisitos derivados (R19)
# ---------------------------------------------------------------------------


def _pines_citados(body: Any) -> list:
    """`[(evidence_id, es_solo_provenance)]` de los pins citados desde el body, en
    orden de aparición y sin duplicados. Tolerante a items malformados. Un pin
    citado también fuera de `provenance_refs` deja de ser solo-provenance."""
    if not isinstance(body, dict):
        return []
    orden: list = []
    solo_prov: dict = {}

    def citar(eid: Any, provenance: bool) -> None:
        if not isinstance(eid, str):
            return
        if eid not in solo_prov:
            orden.append(eid)
            solo_prov[eid] = provenance
        elif not provenance:
            solo_prov[eid] = False

    def items(clave: str) -> list:
        valor = body.get(clave)
        return [x for x in valor if isinstance(x, dict)] if isinstance(valor, list) else []

    for item in items("data_card_refs"):
        citar(item.get("evidence_id"), False)
    for item in items("evaluation_refs"):
        citar(item.get("result_evidence_id"), False)
        citar(item.get("policy_evidence_id"), False)
        for clave in ("metric_evidence_ids", "baseline_evidence_ids", "drift_evidence_ids"):
            ids = item.get(clave)
            for eid in ids if isinstance(ids, list) else []:
                citar(eid, False)
    for item in items("provenance_refs"):
        citar(item.get("evidence_id"), True)
    return [(eid, solo_prov[eid]) for eid in orden]


def requirement_id_for_evidence(evidence_id: str) -> str:
    """requirement_id del claim que respalda un pin citado."""
    return REQ_PREFIJO_EVIDENCE + evidence_id


def requirements_for(card: Any) -> tuple:
    """`Requirement`s DERIVADOS del body (nunca persistidos). Por cada pin citado
    existente en `card.evidence`: `evidence_<evidence_id>` (`required`, `observed`,
    `accepted_kinds=(kind del pin,)`; `recommended` si el pin solo se cita desde
    `provenance_refs`). Siempre `ownership` (`recommended`, `attestation`, min
    `declared`). Pins inexistentes o con id demasiado largo se ignoran (la Card es
    `invalid` por el validador de body). Lanza `CardError` solo si no se recibe
    una Card."""
    if not isinstance(card, CardEnvelope):
        raise CardError(core.CODE_FIELD_INVALID, "requirements_for: se esperaba CardEnvelope")
    evidencias = {e.evidence_id: e for e in card.evidence}
    reqs: list = []
    for eid, solo_prov in _pines_citados(card.body):
        ref = evidencias.get(eid)
        if ref is None or len(eid) > _MAX_EVIDENCE_ID or _RE_ID.fullmatch(eid) is None:
            continue
        reqs.append(
            Requirement(
                requirement_id_for_evidence(eid),
                "recommended" if solo_prov else "required",
                ("observed",),
                (ref.kind,),
            )
        )
    reqs.append(Requirement(REQ_OWNERSHIP, "recommended", ("attestation",), None, "declared"))
    return tuple(reqs)


def _validar_claims(body: Any, claims: Any, atestaciones: Any, out: list) -> None:
    """Coherencia claims <-> body (R20). Claim `evidence_<eid>`: `eid` es un pin
    citado y `supports == (eid,)`. Claim `ownership`: solo ids de atestaciones.
    Cualquier otro `requirement_id` -> inconsistente. Claims sin `requirement_id`
    son libres."""
    if not isinstance(body, dict):
        return
    citados = {eid for eid, _ in _pines_citados(body)}
    ids_atestacion = {getattr(a, "attestation_id", None) for a in (atestaciones if isinstance(atestaciones, (list, tuple)) else ())}
    for i, claim in enumerate(claims if isinstance(claims, (list, tuple)) else ()):
        rid = getattr(claim, "requirement_id", None)
        if rid is None:
            continue
        ruta = f"$.claims[{i}]"
        soportes = tuple(getattr(claim, "supports", ()) or ())
        if not isinstance(rid, str):
            continue
        if rid.startswith(REQ_PREFIJO_EVIDENCE):
            eid = rid[len(REQ_PREFIJO_EVIDENCE):]
            if eid not in citados:
                _h(out, CODE_CLAIM_SUPPORT_INCONSISTENT, ruta, f"claim {rid!r} refiere a un pin no citado por el body")
            elif soportes != (eid,):
                _h(out, CODE_CLAIM_SUPPORT_INCONSISTENT, f"{ruta}.supports",
                   f"claim {rid!r} debe apoyarse exactamente en ({eid!r},); recibió {list(soportes)}")
        elif rid == REQ_OWNERSHIP:
            ajenos = [s for s in soportes if s not in ids_atestacion]
            if ajenos:
                _h(out, CODE_CLAIM_SUPPORT_INCONSISTENT, f"{ruta}.supports",
                   f"claim 'ownership' solo puede apoyarse en atestaciones; ajenos: {sorted(ajenos)}")
        else:
            _h(out, CODE_CLAIM_SUPPORT_INCONSISTENT, ruta,
               f"requirement_id {rid!r} no corresponde a ningún requisito derivado (evidence_<id> u ownership)")


def _validar_identidad_body(body: dict, card_id: Any, subject: Any, out: list) -> None:
    mid, mver = body.get("model_id"), body.get("model_version")
    motivos = _problemas_identidad(mid, mver)
    for motivo in motivos:
        _h(out, CODE_IDENTITY_INVALID, "$.body", motivo)
    if motivos:
        return
    if card_id is not None and card_id != model_card_id(mid, mver):
        _h(out, CODE_IDENTITY_MISMATCH, "$.card_id",
           f"card_id {card_id!r} != {model_card_id(mid, mver)!r} derivado de model_id/model_version")
    if subject is not None and subject != mid:
        _h(out, CODE_IDENTITY_MISMATCH, "$.subject", f"subject {subject!r} != model_id {mid!r}")


def _validar_body(
    body: Any,
    evidencias: dict,
    claims: Any = (),
    atestaciones: Any = (),
    card_id: Any = None,
    subject: Any = None,
) -> list:
    out: list = []
    if not isinstance(body, dict):
        return [Hallazgo(CODE_BODY_INVALID, "$.body", "body debe ser objeto")]
    _claves(body, _BODY_OBLIGATORIAS, _BODY_OPCIONALES, "$.body", out)
    if "model_id" in body and "model_version" in body:
        _validar_identidad_body(body, card_id, subject, out)
    else:
        for clave in ("model_id", "model_version"):
            if clave in body and not isinstance(body[clave], str):
                _h(out, CODE_IDENTITY_INVALID, f"$.body.{clave}", f"{clave} debe ser str")
    if "description" in body:
        _texto(body["description"], "$.body.description", out, multilinea=True)
    if "task" in body:
        _validar_task(body["task"], "$.body.task", out)
    if "population" in body:
        _texto(body["population"], "$.body.population", out, multilinea=True)
    if "stewardship" in body:
        _validar_stewardship(body["stewardship"], "$.body.stewardship", out)
    for clave in _BODY_LISTAS_TEXTO:
        if clave in body:
            _lista_textos(body[clave], f"$.body.{clave}", out)
    if "data_card_refs" in body:
        _validar_data_card_refs(body["data_card_refs"], evidencias, out)
    if "evaluation_refs" in body:
        _validar_evaluation_refs(body["evaluation_refs"], evidencias, out)
    if "provenance_refs" in body:
        _validar_provenance_refs(body["provenance_refs"], evidencias, out)
    _validar_claims(body, claims, atestaciones, out)
    return out


# ---------------------------------------------------------------------------
# API pública: validación
# ---------------------------------------------------------------------------


def _hallazgos_card(card: Any) -> list:
    """Chequeos de kind / kind_schema_version / body de una Card (sin lanzar)."""
    if not isinstance(card, CardEnvelope):
        return [Hallazgo(core.CODE_FIELD_INVALID, "$", f"se esperaba CardEnvelope, se recibió {type(card).__name__}")]
    if card.card_kind != MODEL_CARD_KIND:
        return [Hallazgo(CODE_KIND_INVALID, "$.card_kind", f"se esperaba card_kind {MODEL_CARD_KIND!r}, no {card.card_kind!r}")]
    if card.kind_schema_version != MODEL_CARD_KIND_SCHEMA_VERSION:
        return [
            Hallazgo(
                CODE_SCHEMA_UNSUPPORTED,
                "$.kind_schema_version",
                f"kind_schema_version {card.kind_schema_version!r} no soportado (se espera {MODEL_CARD_KIND_SCHEMA_VERSION})",
            )
        ]
    evidencias = {e.evidence_id: e for e in card.evidence}
    return _validar_body(card.body, evidencias, card.claims, card.attestations, card.card_id, card.subject)


def body_validator_for(card: Any) -> Callable[[dict], list]:
    """Devuelve `validate_body(body) -> list[Hallazgo]` (hook de Change 0) que
    cierra sobre la evidencia, claims, atestaciones, `card_id` y `subject` de
    `card`. Además de validar el body chequea que la Card sea `model_card` con
    `kind_schema_version == 1`, que `card_id`/`subject` coincidan con la identidad
    del body (`MODELCARD-IDENTITY-MISMATCH`) y la coherencia de los claims
    (`MODELCARD-CLAIM-SUPPORT-INCONSISTENT`). Fail-closed: cualquier excepción ->
    hallazgo `MODELCARD-BODY-INVALID`."""
    if isinstance(card, CardEnvelope):
        evidencias = {e.evidence_id: e for e in card.evidence}
        kind, ksv = card.card_kind, card.kind_schema_version
        claims = tuple(card.claims)
        atestaciones = tuple(card.attestations)
        card_id, subject = card.card_id, card.subject
    else:
        evidencias, kind, ksv, claims, atestaciones, card_id, subject = None, None, None, (), (), None, None

    def validate_body(body: Any) -> list:
        try:
            if evidencias is None:
                return [Hallazgo(core.CODE_FIELD_INVALID, "$", "body_validator_for: se esperaba CardEnvelope")]
            if kind != MODEL_CARD_KIND:
                return [Hallazgo(CODE_KIND_INVALID, "$.card_kind", f"se esperaba card_kind {MODEL_CARD_KIND!r}, no {kind!r}")]
            if ksv != MODEL_CARD_KIND_SCHEMA_VERSION:
                return [Hallazgo(CODE_SCHEMA_UNSUPPORTED, "$.kind_schema_version", f"kind_schema_version {ksv!r} no soportado")]
            return _validar_body(body, evidencias, claims, atestaciones, card_id, subject)
        except Exception as exc:  # fail-closed
            return [Hallazgo(CODE_BODY_INVALID, "$.body", f"validación del body falló ({type(exc).__name__})")]

    return validate_body


def validate_model_card(card: Any) -> list:
    """Hallazgos de la Model Card: kind == model_card, kind_schema_version == 1,
    identidad (`card_id`/`subject` derivados) y body (con coherencia de evidencia
    y claims). Lista vacía = válida. No lanza. Los chequeos estructurales de la
    Foundation (`core.validate_card`) los hace `assess.evaluate` / `write_card`."""
    try:
        return _hallazgos_card(card)
    except Exception as exc:  # fail-closed
        return [Hallazgo(CODE_BODY_INVALID, "$.body", f"validación falló ({type(exc).__name__})")]


# ---------------------------------------------------------------------------
# Ubicación y escritura (R32-R34)
# ---------------------------------------------------------------------------


def card_path(project_root: Any, card_id: str) -> Path:
    """`<project_root>/governance/cards/model/<card_id>.json`. Valida `card_id`
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


def _misma_identidad(existente: Any, card: Any) -> bool:
    if not isinstance(existente, CardEnvelope) or existente.card_kind != MODEL_CARD_KIND:
        return False
    if existente.card_id != card.card_id or existente.subject != card.subject:
        return False
    eb = existente.body if isinstance(existente.body, dict) else {}
    nb = card.body if isinstance(card.body, dict) else {}
    return eb.get("model_id") == nb.get("model_id") and eb.get("model_version") == nb.get("model_version")


def write_model_card(
    project_root: Any,
    card: Any,
    *,
    replace: bool = False,
    clock: Optional[Callable[[], str]] = None,
) -> Path:
    """Escribe la Model Card en `card_path(project_root, card.card_id)`.

    - Valida ANTES de tocar el filesystem (Card inválida -> `CardError`, sin
      crear `governance/`).
    - `replace=False`: crea directorios y escribe con `write_card(exclusive=True)`;
      si existe cualquier archivo -> `MODELCARD-EXISTS`, sin sobrescribir.
    - `replace=True`: exige un archivo existente que sea una Card legible de la
      MISMA identidad (`card_id`, `model_id`, `model_version`, `card_kind`); si no
      -> `MODELCARD-NOT-FOUND` / `MODELCARD-IDENTITY-MISMATCH`, sin escribir.
    """
    if not isinstance(card, CardEnvelope):
        raise CardError(core.CODE_FIELD_INVALID, "write_model_card: se esperaba CardEnvelope")
    reloj = clock if clock is not None else assess._reloj_utc
    validador = body_validator_for(card)
    hallazgos = core.validate_card(card, clock=reloj, validate_body=validador)
    if hallazgos:
        resumen = "; ".join(f"{h.code} {h.path}: {h.detail}" for h in hallazgos)
        raise CardError(hallazgos[0].code, f"Model Card inválida, no se escribe: {resumen}")
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
        raise CardError(core.CODE_IO_ERROR, f"no se pudo crear el directorio de Cards ({type(exc).__name__})") from exc
    try:
        return assess.write_card(destino, card, reloj, validate_body=validador, exclusive=True)
    except CardError as exc:
        # MODELCARD-EXISTS solo para existencia real; si el destino no existe se
        # deja el CardError original (p. ej. CARD-IO-ERROR por FS sin hard links).
        if exc.code == core.CODE_IO_ERROR and _existe(destino):
            raise CardError(CODE_EXISTS, f"{destino.name} ya existe; no se sobrescribe") from exc
        raise


# ---------------------------------------------------------------------------
# Evaluación (R35)
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


def evaluate_model_card(card_or_path: Any, repo_root: Any, clock: Optional[Callable[[], str]] = None):
    """Azúcar sobre `assess.evaluate`/lectura: cablea `requirements_for`,
    `default_resolvers(repo_root)` y `body_validator_for`. Un archivo ilegible o
    una Card inválida -> `CardAssessment(card_status="invalid")`; nunca
    excepción cruda ni PASS. No compara valores de métricas (R22)."""
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

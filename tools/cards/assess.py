"""Evaluación derivada de Cards (v0.9 Change 0, `20261002-card-and-evidence-foundation`).

Implementa R22-R35 y R39 del spec: resolución de evidencia inyectada, estados
derivados de evidencia / requisito / Card, salida mapeable a
`dsguard.checks.CheckResult` y lectura/escritura atómica de Cards por ruta
explícita.

Imports: stdlib + `core` (hermano). `dsguard.checks` se importa de forma
PEREZOSA dentro de `a_check_results` (R1). Este módulo:

- NO define ninguna ruta/directorio canónico de Cards ni escanea directorios.
- NO lee el reloj del sistema en la evaluación (R35): solo `write_card` usa un
  `clock` por defecto propio.
- NO consulta ni modifica autonomía / `approval_mode` / STOP (R33): los mensajes
  hablan de «card governance requirements not satisfied».
- NUNCA almacena el estado de la Card (D0.4): todo se recalcula.

Fail-closed: resolver ausente, excepción, retorno inválido o hash no
calculable producen `unverifiable`, nunca `fresh`.
"""
from __future__ import annotations

import datetime as _datetime
import errno
import hashlib
import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

try:  # import dual: paquete (`tools.cards`) o módulo suelto con `tools/cards` en sys.path
    from . import core
except ImportError:  # pragma: no cover - ejecución sin paquete padre
    import core  # type: ignore[no-redef]

CardError = core.CardError
CardEnvelope = core.CardEnvelope
EvidenceRef = core.EvidenceRef
HumanAttestation = core.HumanAttestation
Claim = core.Claim
Requirement = core.Requirement
Hallazgo = core.Hallazgo

# ---------------------------------------------------------------------------
# Constantes de estado
# ---------------------------------------------------------------------------

# Resolution.state (R27)
RES_FOUND = "found"
RES_MISSING = "missing"
RES_UNVERIFIABLE = "unverifiable"
ESTADOS_RESOLUCION = (RES_FOUND, RES_MISSING, RES_UNVERIFIABLE)

# Estado por evidencia (R28)
EV_FRESH = "fresh"
EV_STALE = "stale"
EV_UNRESOLVABLE = "unresolvable"
EV_UNVERIFIABLE = "unverifiable"
ESTADOS_EVIDENCIA = (EV_FRESH, EV_STALE, EV_UNRESOLVABLE, EV_UNVERIFIABLE)

# Estado por requisito (R29)
REQ_SATISFIED = "satisfied"
REQ_MISSING = "missing"
REQ_EMPTY = "empty"
REQ_UNTRUSTED_TYPE = "untrusted_type"
REQ_STALE = "stale"
REQ_UNRESOLVABLE = "unresolvable"
REQ_UNVERIFIABLE = "unverifiable"
ESTADOS_REQUISITO = (
    REQ_SATISFIED,
    REQ_MISSING,
    REQ_EMPTY,
    REQ_UNTRUSTED_TYPE,
    REQ_STALE,
    REQ_UNRESOLVABLE,
    REQ_UNVERIFIABLE,
)

# Estado de Card (R30), derivado y NUNCA persistido
CARD_INVALID = "invalid"
CARD_STALE = "stale"
CARD_INCOMPLETE = "incomplete"
CARD_COMPLETE = "complete"
PRECEDENCIA_CARD = (CARD_INVALID, CARD_STALE, CARD_INCOMPLETE, CARD_COMPLETE)

# Códigos propios de la salida CheckResult que no son de requisito (no están en
# `core.CODES`): se usan solo para PASS y N/A.
CODE_CARD_COMPLETE = "CARD-COMPLETE"
CODE_NO_REQUIREMENTS = "CARD-NO-REQUIREMENTS"

_FRASE_GOVERNANCE = "card governance requirements not satisfied"

# Orden de severidad entre soportes aceptables no satisfechos (R29).
_PRECEDENCIA_SOPORTE = (EV_STALE, EV_UNRESOLVABLE, EV_UNVERIFIABLE)
_ESTADO_REQ_DE_EVIDENCIA = {
    EV_STALE: REQ_STALE,
    EV_UNRESOLVABLE: REQ_UNRESOLVABLE,
    EV_UNVERIFIABLE: REQ_UNVERIFIABLE,
}
_CODIGO_DE_REQUISITO = {
    REQ_MISSING: core.CODE_REQUIREMENT_MISSING,
    REQ_EMPTY: core.CODE_REQUIREMENT_EMPTY,
    REQ_UNTRUSTED_TYPE: core.CODE_REQUIREMENT_UNTRUSTED_TYPE,
    REQ_STALE: core.CODE_REQUIREMENT_STALE,
    REQ_UNRESOLVABLE: core.CODE_REQUIREMENT_UNRESOLVABLE,
    REQ_UNVERIFIABLE: core.CODE_REQUIREMENT_UNVERIFIABLE,
}
_RANGO_ATESTACION = {"declared": 0, "anchored": 1}

_RE_SHA256 = re.compile(r"[0-9a-f]{64}")
_BLOQUE_LECTURA = 1024 * 1024

# ---------------------------------------------------------------------------
# Resolution (R27)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Resolution:
    """Resultado de un resolver: `state` en `ESTADOS_RESOLUCION`,
    `current_sha256` (opcional; obligatorio y válido solo para `found`, lo
    verifica `evaluar_evidencia`) y `detail`."""

    state: str
    current_sha256: Optional[str] = None
    detail: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.state, str) or self.state not in ESTADOS_RESOLUCION:
            raise CardError(core.CODE_FIELD_INVALID, f"Resolution.state inválido {self.state!r}")
        if self.current_sha256 is not None and not isinstance(self.current_sha256, str):
            raise CardError(core.CODE_FIELD_INVALID, "Resolution.current_sha256 debe ser str o None")
        if not isinstance(self.detail, str):
            raise CardError(core.CODE_FIELD_INVALID, "Resolution.detail debe ser str")


# ---------------------------------------------------------------------------
# Resolver genérico por archivo (R31)
# ---------------------------------------------------------------------------


def _hash_binario_sha256(ruta: Path) -> str:
    """sha256 hex del contenido binario del archivo (`sha256/bin/v1`)."""
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        while True:
            bloque = f.read(_BLOQUE_LECTURA)
            if not bloque:
                break
            h.update(bloque)
    return h.hexdigest()


def file_sha256_resolver(repo_root: Any) -> Callable[[Any], Resolution]:
    """Devuelve `callable(EvidenceRef) -> Resolution` que hashea el `locator`
    relativo bajo `repo_root`.

    - Sin `locator` / locator no portable / ruta que sale de `repo_root` /
      cualquier error de IO -> `unverifiable`.
    - Archivo ausente -> `missing`.
    - Archivo presente -> `found` con el sha256 binario.
    """
    try:
        raiz = Path(repo_root).resolve()
    except Exception as exc:
        raise CardError(core.CODE_FIELD_INVALID, f"file_sha256_resolver: repo_root inválido ({type(exc).__name__})") from exc

    def _resolver(ref: Any) -> Resolution:
        try:
            locator = getattr(ref, "locator", None)
            if locator is None:
                return Resolution(RES_UNVERIFIABLE, None, "sin locator")
            if not core.es_locator_portable(locator) or ":" in locator:
                return Resolution(RES_UNVERIFIABLE, None, "locator no portable")
            destino = (raiz / locator).resolve()
            try:
                destino.relative_to(raiz)
            except ValueError:
                return Resolution(RES_UNVERIFIABLE, None, "el locator sale de repo_root")
            if not destino.exists():
                return Resolution(RES_MISSING, None, "archivo ausente")
            if not destino.is_file():
                return Resolution(RES_UNVERIFIABLE, None, "el locator no es un archivo")
            return Resolution(RES_FOUND, _hash_binario_sha256(destino), "")
        except Exception as exc:  # fail-closed
            return Resolution(RES_UNVERIFIABLE, None, f"error al resolver ({type(exc).__name__})")

    return _resolver


# ---------------------------------------------------------------------------
# Estado por evidencia (R26, R28)
# ---------------------------------------------------------------------------


def evaluar_evidencia(ref: Any, resolvers: Optional[Mapping]) -> str:
    """Estado derivado de una `EvidenceRef` (`ESTADOS_EVIDENCIA`). FAIL-CLOSED:
    resolver ausente / excepción / retorno que no es `Resolution` / state
    desconocido / `found` sin `current_sha256` válido -> `unverifiable`."""
    try:
        if not isinstance(ref, EvidenceRef) or resolvers is None:
            return EV_UNVERIFIABLE
        resolver = resolvers.get(ref.kind)
        if resolver is None or not callable(resolver):
            return EV_UNVERIFIABLE
        res = resolver(ref)
    except Exception:
        return EV_UNVERIFIABLE
    if not isinstance(res, Resolution):
        return EV_UNVERIFIABLE
    if res.state == RES_MISSING:
        return EV_UNRESOLVABLE
    if res.state == RES_FOUND:
        actual = res.current_sha256
        if not isinstance(actual, str) or _RE_SHA256.fullmatch(actual) is None:
            return EV_UNVERIFIABLE
        return EV_FRESH if actual == ref.content_sha256 else EV_STALE
    return EV_UNVERIFIABLE  # RES_UNVERIFIABLE o state desconocido


# ---------------------------------------------------------------------------
# CardAssessment
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CardAssessment:
    """Resultado derivado de `evaluate`. Nunca se persiste en la Card.

    - `requisitos`: tupla de `(requirement_id, severity, state, detalle)`,
      ordenada por `requirement_id`.
    - `evidencias`: tupla de `(evidence_id, state)`, ordenada por `evidence_id`.
    - `hallazgos`: hallazgos estructurales (`Hallazgo`) de `validate_card`.
    - `sin_requisitos`: no se recibió ningún requisito.
    """

    card_status: str
    requisitos: tuple = ()
    evidencias: tuple = ()
    hallazgos: tuple = ()
    sin_requisitos: bool = False
    card_id: str = ""

    def a_dict(self) -> dict:
        return {
            "card_id": self.card_id,
            "card_status": self.card_status,
            "sin_requisitos": self.sin_requisitos,
            "requisitos": [
                {"requirement_id": r[0], "severity": r[1], "state": r[2], "detail": r[3]}
                for r in self.requisitos
            ],
            "evidencias": [{"evidence_id": e[0], "state": e[1]} for e in self.evidencias],
            "hallazgos": [list(h.as_tuple()) for h in self.hallazgos],
        }


# ---------------------------------------------------------------------------
# Evaluación (R24-R30)
# ---------------------------------------------------------------------------


def _validar_requirements(requirements: Any) -> tuple:
    try:
        items = tuple(requirements) if requirements is not None else ()
    except TypeError as exc:
        raise CardError(core.CODE_FIELD_INVALID, "requirements: se esperaba un iterable de Requirement") from exc
    vistos: set = set()
    for i, r in enumerate(items):
        if not isinstance(r, Requirement):
            raise CardError(
                core.CODE_FIELD_INVALID,
                f"requirements[{i}]: se esperaba Requirement, se recibió {type(r).__name__}",
            )
        if r.requirement_id in vistos:
            raise CardError(core.CODE_DUPLICATE_ID, f"requirements: requirement_id duplicado {r.requirement_id!r}")
        vistos.add(r.requirement_id)
    return items


def _evaluar_requisito(
    req: Requirement, card: CardEnvelope, estados_ev: dict, evidencias: dict, atestaciones: dict
) -> tuple:
    """Devuelve `(state, detalle)` de un requisito (R24, R25, R29)."""
    claims = [c for c in card.claims if c.requirement_id == req.requirement_id]
    if not claims:
        return REQ_MISSING, "sin claim ligado al requisito"
    soportes: list = []
    for c in claims:
        for s in c.supports:
            if s not in soportes:
                soportes.append(s)
    if not soportes:
        return REQ_EMPTY, "claim sin supports"

    acepta_obs = "observed" in req.accepts
    acepta_att = "attestation" in req.accepts
    rango_min = _RANGO_ATESTACION[req.min_attestation_kind]

    vigentes: list = []
    no_vigentes: list = []  # estados de evidencia aceptada pero no fresh
    rechazados: list = []
    for s in soportes:
        if s in evidencias:
            ev = evidencias[s]
            kind_ok = req.accepted_kinds is None or ev.kind in req.accepted_kinds
            if not (acepta_obs and kind_ok):
                rechazados.append(s)
            elif estados_ev[s] == EV_FRESH:
                vigentes.append(s)
            else:
                no_vigentes.append(estados_ev[s])
        elif s in atestaciones:
            att = atestaciones[s]
            if acepta_att and _RANGO_ATESTACION[att.attestation_kind] >= rango_min:
                vigentes.append(s)
            else:
                rechazados.append(s)
        else:
            rechazados.append(s)  # no debería ocurrir en Card válida (dangling)

    if vigentes:
        return REQ_SATISFIED, "soportes vigentes: " + ",".join(vigentes)
    for estado in _PRECEDENCIA_SOPORTE:
        if estado in no_vigentes:
            return _ESTADO_REQ_DE_EVIDENCIA[estado], f"soporte aceptado en estado {estado}"
    return REQ_UNTRUSTED_TYPE, "soportes de clase/kind/attestation_kind no aceptados: " + ",".join(rechazados)


def _estado_card(requisitos: tuple) -> str:
    candidatos: set = set()
    for _id, severidad, estado, _det in requisitos:
        if severidad != "required":
            continue
        if estado == REQ_STALE:
            candidatos.add(CARD_STALE)
        if estado != REQ_SATISFIED:
            candidatos.add(CARD_INCOMPLETE)
    candidatos.add(CARD_COMPLETE)
    return next(e for e in PRECEDENCIA_CARD if e in candidatos)


def evaluate(
    card: Any,
    requirements: Any,
    resolvers: Optional[Mapping],
    clock: Optional[Callable[[], str]] = None,
    *,
    validate_body: Optional[Callable[[dict], list]] = None,
) -> CardAssessment:
    """Evalúa una Card contra `requirements` (R24-R30). No lee el reloj del
    sistema: `clock` (inyectable) solo alimenta el chequeo de atestación futura
    de `validate_card`. Requirements duplicados o malformados -> `CardError`.

    Si `validate_card` devuelve hallazgos, la Card es `invalid` y NO se evalúa
    evidencia (ni se invoca ningún resolver)."""
    reqs = _validar_requirements(requirements)
    if resolvers is not None and not isinstance(resolvers, Mapping):
        raise CardError(core.CODE_FIELD_INVALID, "resolvers: se esperaba un mapa kind -> callable")

    hallazgos = core.validate_card(card, clock=clock, validate_body=validate_body)
    card_id = card.card_id if isinstance(card, CardEnvelope) else ""
    sin_requisitos = len(reqs) == 0
    if hallazgos:
        return CardAssessment(
            card_status=CARD_INVALID,
            hallazgos=tuple(hallazgos),
            sin_requisitos=sin_requisitos,
            card_id=card_id,
        )

    evidencias = {e.evidence_id: e for e in card.evidence}
    atestaciones = {a.attestation_id: a for a in card.attestations}
    estados_ev = {eid: evaluar_evidencia(e, resolvers) for eid, e in evidencias.items()}

    requisitos = tuple(
        sorted(
            (
                (r.requirement_id, r.severity, *_evaluar_requisito(r, card, estados_ev, evidencias, atestaciones))
                for r in reqs
            ),
            key=lambda t: t[0],
        )
    )
    estado = _estado_card(requisitos)
    # R25: una plantilla vacía (sin claims, evidencia ni atestaciones) nunca es `complete`.
    if estado == CARD_COMPLETE and not (card.claims or card.evidence or card.attestations):
        estado = CARD_INCOMPLETE
    return CardAssessment(
        card_status=estado,
        requisitos=requisitos,
        evidencias=tuple(sorted(estados_ev.items(), key=lambda t: t[0])),
        hallazgos=(),
        sin_requisitos=sin_requisitos,
        card_id=card_id,
    )


# ---------------------------------------------------------------------------
# Salida CheckResult (R32, R33)
# ---------------------------------------------------------------------------


def _checks_module() -> Any:
    """Import perezoso de `dsguard.checks` (mismo patrón que
    `datasources.runtime`, pero diferido a la primera llamada)."""
    tools_dir = str(Path(__file__).resolve().parents[1])
    if tools_dir not in sys.path:
        sys.path.insert(0, tools_dir)
    from dsguard import checks  # noqa: WPS433

    return checks


def a_check_results(assessment: CardAssessment) -> list:
    """Mapea un `CardAssessment` a `list[dsguard.checks.CheckResult]` (R32).

    - Card `invalid` -> un FAIL por hallazgo estructural.
    - Sin requisitos -> un único N/A.
    - `required` no satisfecho -> FAIL; `recommended` no satisfecho -> WARN.
    - Evidencia `stale` -> WARN `CARD-EVIDENCE-STALE`.
    - Card `complete` -> además un PASS.
    Los mensajes dicen «card governance requirements not satisfied»; nunca
    mencionan autonomía/STOP (R33)."""
    if not isinstance(assessment, CardAssessment):
        raise CardError(core.CODE_FIELD_INVALID, "a_check_results: se esperaba CardAssessment")
    checks = _checks_module()
    sujeto = assessment.card_id or None
    resultados: list = []

    if assessment.card_status == CARD_INVALID:
        for h in assessment.hallazgos:
            resultados.append(
                checks.CheckResult(
                    checks.STATUS_FAIL,
                    h.code,
                    f"{_FRASE_GOVERNANCE}: card structurally invalid at {h.path}",
                    detail=h.detail,
                    subject=sujeto,
                )
            )
        if not resultados:
            resultados.append(
                checks.CheckResult(
                    checks.STATUS_FAIL,
                    core.CODE_FIELD_INVALID,
                    f"{_FRASE_GOVERNANCE}: card structurally invalid",
                    subject=sujeto,
                )
            )
        return resultados

    if assessment.sin_requisitos and assessment.card_status == CARD_INCOMPLETE:
        # R25: Card vacía (sin requisitos) -> incomplete, no N/A.
        return [
            checks.CheckResult(
                checks.STATUS_WARN,
                core.CODE_REQUIREMENT_EMPTY,
                f"{_FRASE_GOVERNANCE}: card has no claims, evidence or attestations",
                subject=sujeto,
            )
        ]

    if assessment.sin_requisitos:
        return [
            checks.CheckResult(
                checks.STATUS_NA,
                CODE_NO_REQUIREMENTS,
                "no card governance requirements apply to this card",
                subject=sujeto,
            )
        ]

    for req_id, severidad, estado, detalle in assessment.requisitos:
        if estado == REQ_SATISFIED:
            continue
        status = checks.STATUS_FAIL if severidad == "required" else checks.STATUS_WARN
        resultados.append(
            checks.CheckResult(
                status,
                _CODIGO_DE_REQUISITO.get(estado, core.CODE_REQUIREMENT_UNSATISFIED),
                f"{_FRASE_GOVERNANCE}: {req_id} ({severidad}) is {estado}",
                detail=detalle,
                subject=sujeto,
            )
        )
    for ev_id, estado in assessment.evidencias:
        if estado == EV_STALE:
            resultados.append(
                checks.CheckResult(
                    checks.STATUS_WARN,
                    core.CODE_EVIDENCE_STALE,
                    f"{_FRASE_GOVERNANCE}: evidence {ev_id} is stale (pinned hash differs from current)",
                    subject=sujeto,
                )
            )
    if assessment.card_status == CARD_COMPLETE:
        resultados.append(
            checks.CheckResult(
                checks.STATUS_PASS,
                CODE_CARD_COMPLETE,
                "all required card governance requirements are satisfied",
                subject=sujeto,
            )
        )
    return resultados


# ---------------------------------------------------------------------------
# I/O de Cards (R39) — rutas siempre explícitas
# ---------------------------------------------------------------------------


def _reloj_utc() -> str:
    """Reloj por defecto de `write_card` (único uso del reloj del sistema)."""
    return _datetime.datetime.now(_datetime.timezone.utc).strftime(core.TIMESTAMP_FORMAT)


_ERRNO_SIN_HARDLINK = frozenset(
    getattr(errno, nombre)
    for nombre in ("EPERM", "ENOTSUP", "EOPNOTSUPP", "EXDEV")
    if hasattr(errno, nombre)
)


def _publicar_sin_hardlink(tmp_nombre: str, destino: Path) -> None:
    """Fallback de `write_card(exclusive=True)` sin hard links: `exists()` previo
    + `os.replace` (ventana de carrera residual). Un error al consultar
    `exists()` (p. ej. PermissionError) se convierte en `CardError`."""
    try:
        existe = destino.exists()
    except OSError as exc:
        raise CardError(core.CODE_IO_ERROR, f"no se pudo comprobar {destino.name}: {exc.__class__.__name__}") from exc
    if existe:
        raise CardError(core.CODE_IO_ERROR, f"{destino.name} ya existe; no se sobrescribe")
    os.replace(tmp_nombre, destino)


def write_card(
    path: Any,
    card: Any,
    clock: Optional[Callable[[], str]] = None,
    *,
    validate_body: Optional[Callable[[dict], list]] = None,
    exclusive: bool = False,
) -> Path:
    """Escribe la Card de forma atómica (tempfile + `os.replace`) en `path`
    (explícito; el directorio padre debe existir). Valida con `validate_card`
    antes: con hallazgos -> `CardError` y NO escribe. JSON `indent=2`,
    `sort_keys=True`, `ensure_ascii=False`, LF, `to_dict(con_revision=True)`.

    `exclusive=True` (creación sin pisar): si `path` ya existe -> `CardError`
    `CARD-IO-ERROR` y NO se sobrescribe. Sin carrera: se escribe el temporal y
    se publica con `os.link(tmp, destino)` (falla si el destino existe); el
    temporal se borra siempre. Solo si el filesystem no soporta hard links
    (`AttributeError`, `NotImplementedError` u `OSError` con errno EPERM /
    ENOTSUP / EOPNOTSUPP / EXDEV) se cae a un chequeo `exists()` previo +
    `os.replace` (ventana de carrera residual, documentada); cualquier otro
    `OSError` -> `CardError` `CARD-IO-ERROR` sin fallback. En FAT/exFAT o
    shares sin hard links (Windows mapea EINVAL) la creación exclusiva falla
    cerrada con `CARD-IO-ERROR`, sin fallback. Con `exclusive=False` (default) el comportamiento es el
    histórico: `os.replace` sobrescribe."""
    reloj = clock if clock is not None else _reloj_utc
    hallazgos = core.validate_card(card, clock=reloj, validate_body=validate_body)
    if hallazgos:
        resumen = "; ".join(f"{h.code} {h.path}: {h.detail}" for h in hallazgos)
        raise CardError(hallazgos[0].code, f"Card inválida, no se escribe: {resumen}")
    destino = Path(path)
    datos = (
        json.dumps(card.to_dict(con_revision=True), indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
        + "\n"
    ).encode("utf-8")
    tmp_nombre: Optional[str] = None
    try:
        fd, tmp_nombre = tempfile.mkstemp(dir=str(destino.parent), prefix=destino.name + ".", suffix=".tmp")
        with os.fdopen(fd, "wb") as f:  # bytes: sin traducción de saltos de línea (LF)
            f.write(datos)
            f.flush()
            os.fsync(f.fileno())
        if not exclusive:
            os.replace(tmp_nombre, destino)
            tmp_nombre = None
        else:
            try:
                os.link(tmp_nombre, destino)  # falla si el destino existe; el tmp se borra en `finally`
            except FileExistsError as exc:
                raise CardError(core.CODE_IO_ERROR, f"{destino.name} ya existe; no se sobrescribe") from exc
            except (NotImplementedError, AttributeError):
                _publicar_sin_hardlink(tmp_nombre, destino)
                tmp_nombre = None
            except OSError as exc:
                # Solo los errores de "sin soporte de hard links" caen al fallback;
                # cualquier otro OSError es un error de IO real (sin fallback).
                if exc.errno not in _ERRNO_SIN_HARDLINK:
                    raise CardError(
                        core.CODE_IO_ERROR, f"no se pudo escribir {destino.name}: {exc.__class__.__name__}"
                    ) from exc
                _publicar_sin_hardlink(tmp_nombre, destino)
                tmp_nombre = None
    except OSError as exc:
        raise CardError(core.CODE_IO_ERROR, f"no se pudo escribir {destino.name}: {exc.__class__.__name__}") from exc
    finally:
        if tmp_nombre is not None:
            try:
                os.unlink(tmp_nombre)
            except OSError:
                pass
    return destino


def _rechazar_constante(nombre: str) -> Any:
    raise ValueError(f"constante JSON no permitida: {nombre}")


def read_card(path: Any) -> CardEnvelope:
    """Lee una Card desde `path` (explícito). Bytes UTF-8 -> `json.loads` ->
    `CardEnvelope.from_dict` (estricto: un `status` u otra clave desconocida
    -> `CardError`). Errores de IO -> `CARD-IO-ERROR`.

    Un archivo rechazado con `CardError` (JSON inválido, `status` o clave
    desconocida, pin de hash mal formado, `revision_id` declarado distinto del
    recomputado, etc.) equivale al estado derivado `invalid`; `read_card`
    sigue lanzando, y `evaluate_file` lo expone como `CardAssessment` con
    `card_status == "invalid"`."""
    try:
        contenido = Path(path).read_bytes()
    except OSError as exc:
        raise CardError(core.CODE_IO_ERROR, f"no se pudo leer la Card: {exc.__class__.__name__}") from exc
    except TypeError as exc:
        raise CardError(core.CODE_IO_ERROR, "ruta de Card inválida") from exc
    try:
        datos = json.loads(contenido.decode("utf-8"), parse_constant=_rechazar_constante)
    except (UnicodeDecodeError, ValueError, RecursionError) as exc:
        raise CardError(core.CODE_FIELD_INVALID, f"JSON inválido ({exc.__class__.__name__})") from exc
    return CardEnvelope.from_dict(datos)


def evaluate_file(
    path: Any,
    requirements: Any,
    resolvers: Optional[Mapping],
    clock: Optional[Callable[[], str]] = None,
    *,
    validate_body: Optional[Callable[[dict], list]] = None,
) -> CardAssessment:
    """Evalúa la Card de `path` (explícito). Lee con `read_card`; si este lanza
    `CardError` (IO, JSON inválido, `status`/clave desconocida, pin mal
    formado, `revision_id` != recomputado, ...) el archivo equivale al estado
    `invalid`: devuelve `CardAssessment(card_status=CARD_INVALID)` con
    requisitos/evidencias vacíos y un hallazgo `(code, "file", message)`, SIN
    invocar ningún resolver. Si lee bien, delega en `evaluate`. `requirements`
    malformados siguen lanzando `CardError` (como `evaluate`)."""
    reqs = _validar_requirements(requirements)
    try:
        card = read_card(path)
    except CardError as exc:
        return CardAssessment(
            card_status=CARD_INVALID,
            hallazgos=(Hallazgo(exc.code, "file", exc.message),),
            sin_requisitos=len(reqs) == 0,
            card_id="",
        )
    return evaluate(card, reqs, resolvers, clock, validate_body=validate_body)

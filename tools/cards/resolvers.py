"""Resolvers de evidencia observada para Cards de datos (Change `20261002-data-cards`, R18-R27).

Cada resolver es un `callable(EvidenceRef) -> assess.Resolution` que NUNCA lanza:
cualquier error produce `Resolution("unverifiable", None, detalle)` (fail-closed).

Imports: stdlib + `core` y `assess` (hermanos, import dual). NO se importa
`datasources`, `qualityevidence` ni `datacontracts` (D8): los hashes se
recomputan a nivel de dict JSON con el mismo JSON canónico que esos paquetes
(la equivalencia se fija con tests de paridad, fuera de este módulo).

Solo lectura, sin red, sin tocar `data/`. Las rutas se validan dentro de
`repo_root` (sin `..`, separadores ni symlinks que escapen). Lecturas
limitadas a `MAX_BYTES_LECTURA`.

Funciones PÚBLICAS de hash (las usan los autores de Cards para pinnear):
`hash_observation`, `hash_provenance`, `hash_contract`, `hash_quality_manifest`.
"""
from __future__ import annotations

import datetime as _datetime
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Callable, Optional

try:  # import dual: paquete (`tools.cards`) o módulo suelto con `tools/cards` en sys.path
    from . import assess, core
except ImportError:  # pragma: no cover - ejecución sin paquete padre
    import assess  # type: ignore[no-redef]
    import core  # type: ignore[no-redef]

Resolution = assess.Resolution
CardError = core.CardError

MAX_BYTES_LECTURA = 8 * 1024 * 1024

KIND_SOURCE_OBSERVATION = "source_observation"
KIND_SOURCE_PROVENANCE = "source_provenance"
KIND_HARMESSI_CONTRACT = "harmessi_contract"
KIND_QUALITY_EVIDENCE = "quality_evidence"
KIND_DATA_CONTRACT_RESULT = "data_contract_result"
KIND_DATA_CARD = "data_card"
KIND_MODEL_QUALITY_RESULT = "model_quality_result"
KIND_MODEL_QUALITY_POLICY = "model_quality_policy"
KIND_OBSERVED_METRIC = "observed_metric"
KIND_BASELINE_REFERENCE = "baseline_reference"
KIND_DRIFT_EVIDENCE = "drift_evidence"
KIND_EXECUTION_RECORD = "execution_record"

SUBJECT_DATA_CONTRACT_EVALUATION = "data_contract_evaluation"
SUBJECT_MODEL_QUALITY_EVALUATION = "model_quality_evaluation"

_DIR_DATA_CARDS = "governance/cards/data"

_RE_SOURCE_ID = r"[a-z0-9][a-z0-9_-]{0,63}"
_RE_REF_OBSERVACION = re.compile(r"(" + _RE_SOURCE_ID + r")__([0-9a-f]{12})")
_RE_EVIDENCE_ID = re.compile(r"qe-\d{8}T\d{6}Z-[0-9a-f]{6}")
_RE_CONTRATO_REF = re.compile(r"(" + _RE_SOURCE_ID + r")@(\d+\.\d+\.\d+)")
_RE_SHA256 = re.compile(r"[0-9a-f]{64}")
_RE_REF_DATA_CARD = re.compile(r"(" + _RE_SOURCE_ID + r")__([0-9a-f]{12})")
_RE_DRIFT_ID = re.compile(r"dr-\d{8}T\d{6}Z-[0-9a-f]{6}")
_RE_REF_EJECUCION = re.compile(r"([a-z0-9][a-z0-9_-]*)__([0-9a-f]{12})")

_DIR_HARMESSI = ".harmessi"


class _NoVerificable(Exception):
    """Interna: se convierte en `Resolution("unverifiable", detalle)`."""


class _Ausente(Exception):
    """Interna: se convierte en `Resolution("missing", detalle)`."""


# ---------------------------------------------------------------------------
# Hashes públicos (a nivel de dict JSON)
# ---------------------------------------------------------------------------


def _sha256_canonico(obj: Any) -> str:
    return hashlib.sha256(core.canonical_json(obj).encode("utf-8")).hexdigest()


def _sin_generated_at_provenance(observacion: Any) -> dict:
    if not isinstance(observacion, dict) or not isinstance(observacion.get("provenance"), dict):
        raise CardError(core.CODE_FIELD_INVALID, "observación: se esperaba dict con 'provenance' dict")
    copia = dict(observacion)
    prov = dict(copia["provenance"])
    prov.pop("generated_at", None)
    copia["provenance"] = prov
    return copia


def hash_observation(observacion: dict) -> str:
    """sha256 hex del JSON canónico de la observación SIN `provenance.generated_at`
    (equivalente a `SourceObservation.content_sha256()` si el dict es su `to_dict()`)."""
    return _sha256_canonico(_sin_generated_at_provenance(observacion))


def hash_provenance(observacion_o_provenance: dict) -> str:
    """sha256 hex del sub-objeto `provenance` sin `generated_at`. Acepta la
    observación completa (usa su clave `provenance`) o el dict de provenance."""
    if not isinstance(observacion_o_provenance, dict):
        raise CardError(core.CODE_FIELD_INVALID, "provenance: se esperaba dict")
    if isinstance(observacion_o_provenance.get("provenance"), dict):
        prov = dict(observacion_o_provenance["provenance"])
    else:
        prov = dict(observacion_o_provenance)
    prov.pop("generated_at", None)
    return _sha256_canonico(prov)


def hash_contract(contrato: dict) -> str:
    """sha256 hex del JSON canónico del dict del contrato (equivalente a
    `DataContract.content_sha256()` si el dict es su `to_dict()`)."""
    if not isinstance(contrato, dict):
        raise CardError(core.CODE_FIELD_INVALID, "contrato: se esperaba dict")
    return _sha256_canonico(contrato)


def hash_quality_manifest(manifest: dict) -> str:
    """sha256 hex del JSON canónico del manifest excluyendo `generated_at` y
    `content_sha256` (equivalente a `QualityEvidenceManifest.content_sha256()`)."""
    if not isinstance(manifest, dict):
        raise CardError(core.CODE_FIELD_INVALID, "manifest: se esperaba dict")
    copia = {k: v for k, v in manifest.items() if k not in ("generated_at", "content_sha256")}
    return _sha256_canonico(copia)


def hash_document(obj: Any) -> str:
    """sha256 hex del JSON canónico de un documento JSON completo (dict o lista),
    tal como está en el archivo (R31). Lo usan `observed_metric`/`baseline_reference`."""
    return _sha256_canonico(obj)


def hash_policy(politica: dict) -> str:
    """sha256 hex del JSON canónico del dict de una `ModelQualityPolicy` (R25)."""
    if not isinstance(politica, dict):
        raise CardError(core.CODE_FIELD_INVALID, "política: se esperaba dict")
    return _sha256_canonico(politica)


def _hash_sin_generated_at(datos: Any, nombre: str) -> str:
    if not isinstance(datos, dict):
        raise CardError(core.CODE_FIELD_INVALID, f"{nombre}: se esperaba dict")
    return _sha256_canonico({k: v for k, v in datos.items() if k != "generated_at"})


def hash_drift(drift: dict) -> str:
    """sha256 hex del JSON canónico de `DriftEvidence.to_dict()` sin `generated_at`
    ni `content_sha256` (equivalente a `DriftEvidence.content_sha256()`, R27)."""
    if not isinstance(drift, dict):
        raise CardError(core.CODE_FIELD_INVALID, "drift: se esperaba dict")
    return _sha256_canonico({k: v for k, v in drift.items() if k not in ("generated_at", "content_sha256")})


def hash_execution_record(registro: dict) -> str:
    """sha256 hex del JSON canónico de `ExecutionRecord.to_dict()` sin `generated_at` (R28)."""
    return _hash_sin_generated_at(registro, "execution_record")


# ---------------------------------------------------------------------------
# Utilidades de IO seguras
# ---------------------------------------------------------------------------


def _rechazar_constante(nombre: str) -> Any:
    raise ValueError(f"constante JSON no permitida: {nombre}")


def _dentro_de(base: Path, destino: Path) -> bool:
    try:
        destino.resolve().relative_to(base)
        return True
    except (ValueError, OSError):
        return False


def _leer_json(ruta: Path, base: Path, permitir_lista: bool = False) -> Any:
    """Lee un JSON (objeto; o lista si `permitir_lista`) con tope de tamaño; la
    ruta resuelta debe quedar dentro de `base` (ya resuelta). Rechaza NaN/Infinity.
    Lanza `_NoVerificable` ante cualquier problema."""
    if not _dentro_de(base, ruta):
        raise _NoVerificable("la ruta sale del directorio permitido")
    try:
        if not ruta.is_file():
            raise _NoVerificable("no es un archivo")
        with open(ruta, "rb") as f:
            datos = f.read(MAX_BYTES_LECTURA + 1)
    except OSError as exc:
        raise _NoVerificable(f"error de lectura ({type(exc).__name__})") from exc
    if len(datos) > MAX_BYTES_LECTURA:
        raise _NoVerificable("archivo excede el tamaño máximo")
    try:
        obj = json.loads(datos.decode("utf-8"), parse_constant=_rechazar_constante)
    except (UnicodeDecodeError, ValueError, RecursionError) as exc:
        raise _NoVerificable(f"JSON inválido ({type(exc).__name__})") from exc
    if permitir_lista:
        if not isinstance(obj, list):
            raise _NoVerificable("el JSON raíz no es una lista")
    elif not isinstance(obj, dict):
        raise _NoVerificable("el JSON raíz no es un objeto")
    return obj


def _raiz(repo_root: Any) -> Path:
    try:
        return Path(repo_root).resolve()
    except Exception as exc:
        raise CardError(core.CODE_FIELD_INVALID, f"repo_root inválido ({type(exc).__name__})") from exc


def _id_seguro(valor: Any) -> str:
    if not isinstance(valor, str) or not valor:
        raise _NoVerificable("ref_id inválido")
    if ".." in valor or "/" in valor or "\\" in valor or ":" in valor or valor.startswith(("~", ".")):
        raise _NoVerificable("ref_id con componentes de ruta no permitidos")
    return valor


_RE_FECHA_ISO = re.compile(
    r"([0-9]{4}-[0-9]{2}-[0-9]{2})"
    r"(?:[T ]([0-9]{2}:[0-9]{2}(?::[0-9]{2})?)(?:\.([0-9]{1,9}))?)?"
    r"(Z|[+-][0-9]{2}(?::?[0-9]{2})?)?"
)


def _parsear_fecha(valor: Any) -> _datetime.datetime:
    """Parsea `provenance.generated_at` (ISO-8601) de forma uniforme en Python
    3.9-3.12, aceptando lo que acepta `datasources`: fecha sola `YYYY-MM-DD`,
    fracciones de 1 a 9 dígitos (se truncan a 6), `Z` y offsets `+HH[:MM]`.
    Sin zona horaria se asume UTC. Devuelve un datetime aware en UTC."""
    if not isinstance(valor, str):
        raise _NoVerificable("generated_at ausente o no es texto")
    m = _RE_FECHA_ISO.fullmatch(valor)
    if m is None:
        raise _NoVerificable("generated_at no es ISO-8601")
    fecha_s, hora_s, fraccion, zona = m.groups()
    hora_s = hora_s or "00:00:00"
    if hora_s.count(":") == 1:
        hora_s += ":00"
    fraccion = (fraccion or "0")[:6].ljust(6, "0")
    if zona is None or zona == "Z":
        zona = "+00:00"
    else:
        digitos = zona[1:].replace(":", "")
        zona = f"{zona[0]}{digitos[:2]}:{digitos[2:4] or '00'}"
    texto = f"{fecha_s}T{hora_s}.{fraccion}{zona}"
    try:
        fecha = _datetime.datetime.fromisoformat(texto)
    except ValueError as exc:
        raise _NoVerificable("generated_at no es ISO-8601") from exc
    if fecha.tzinfo is None:
        fecha = fecha.replace(tzinfo=_datetime.timezone.utc)
    return fecha.astimezone(_datetime.timezone.utc)


def _envolver(funcion: Callable[[Any], Resolution]) -> Callable[[Any], Resolution]:
    """Garantiza que el resolver nunca lanza (fail-closed)."""

    def _resolver(ref: Any) -> Resolution:
        try:
            return funcion(ref)
        except _Ausente as exc:
            return Resolution(assess.RES_MISSING, None, str(exc))
        except _NoVerificable as exc:
            return Resolution(assess.RES_UNVERIFIABLE, None, str(exc))
        except Exception as exc:  # fail-closed
            return Resolution(assess.RES_UNVERIFIABLE, None, f"error al resolver ({type(exc).__name__})")

    return _resolver


# ---------------------------------------------------------------------------
# source_observation / source_provenance (R18-R21, D6)
# ---------------------------------------------------------------------------


def _observacion_vigente(base_obs: Path, source_id: str) -> dict:
    """Devuelve la observación vigente más reciente del `source_id`: máximo
    `provenance.generated_at`, desempate por nombre de directorio (mayor)."""
    if not base_obs.is_dir():
        raise _Ausente("sin directorio de observaciones")
    patron = re.compile(re.escape(source_id) + r"__[0-9a-f]{12}")
    candidatos = []
    for hijo in base_obs.iterdir():
        if patron.fullmatch(hijo.name) is None:
            continue
        ruta = hijo / "observation.json"
        if not hijo.is_dir():
            raise _NoVerificable("entrada de observación no es un directorio")
        if not ruta.exists():
            raise _NoVerificable(f"{hijo.name}: sin observation.json")
        datos = _leer_json(ruta, base_obs)
        if datos.get("source_id") != source_id:
            raise _NoVerificable(f"{hijo.name}: source_id interno no coincide con el directorio")
        prov = datos.get("provenance")
        if not isinstance(prov, dict):
            raise _NoVerificable(f"{hijo.name}: provenance ausente")
        candidatos.append((_parsear_fecha(prov.get("generated_at")), hijo.name, datos))
    if not candidatos:
        raise _Ausente("sin observaciones para el source_id")
    candidatos.sort(key=lambda t: (t[0], t[1]))
    return candidatos[-1][2]


def _resolver_fuente(repo_root: Any, es_provenance: bool) -> Callable[[Any], Resolution]:
    raiz = _raiz(repo_root)

    def _res(ref: Any) -> Resolution:
        coincidencia = _RE_REF_OBSERVACION.fullmatch(_id_seguro(getattr(ref, "ref_id", None)))
        if coincidencia is None:
            raise _NoVerificable("ref_id no cumple <source_id>__<hash12>")
        if es_provenance and getattr(ref, "member", None) != "provenance":
            raise _NoVerificable("source_provenance exige member='provenance'")
        base_obs = raiz / _DIR_HARMESSI / "observations"
        if not _dentro_de(raiz, base_obs):
            raise _NoVerificable("directorio de observaciones fuera de repo_root")
        vigente = _observacion_vigente(base_obs.resolve(), coincidencia.group(1))
        actual = hash_provenance(vigente) if es_provenance else hash_observation(vigente)
        return Resolution(assess.RES_FOUND, actual, "")

    return _envolver(_res)


def source_observation_resolver(repo_root: Any) -> Callable[[Any], Resolution]:
    """Resolver `source_observation` (R18-R20)."""
    return _resolver_fuente(repo_root, es_provenance=False)


def source_provenance_resolver(repo_root: Any) -> Callable[[Any], Resolution]:
    """Resolver `source_provenance` (R21)."""
    return _resolver_fuente(repo_root, es_provenance=True)


# ---------------------------------------------------------------------------
# harmessi_contract (R22)
# ---------------------------------------------------------------------------


def harmessi_contract_resolver(repo_root: Any) -> Callable[[Any], Resolution]:
    """Resolver `harmessi_contract`: lee el contrato JSON en `ref.locator`."""
    raiz = _raiz(repo_root)

    def _res(ref: Any) -> Resolution:
        ref_id = getattr(ref, "ref_id", None)
        coincidencia = _RE_CONTRATO_REF.fullmatch(ref_id) if isinstance(ref_id, str) else None
        if coincidencia is None:
            raise _NoVerificable("ref_id no cumple <contract_id>@<version>")
        locator = getattr(ref, "locator", None)
        if locator is None:
            raise _NoVerificable("sin locator")
        if not core.es_locator_portable(locator) or ":" in locator:
            raise _NoVerificable("locator no portable")
        destino = raiz / locator
        if not _dentro_de(raiz, destino):
            raise _NoVerificable("el locator sale de repo_root")
        if not destino.exists():
            raise _Ausente("contrato ausente")
        datos = _leer_json(destino, raiz)
        version = datos.get("version")
        version_str = version.get("version") if isinstance(version, dict) else None
        if datos.get("contract_id") != coincidencia.group(1) or version_str != coincidencia.group(2):
            raise _NoVerificable("contract_id/version del contenido no coinciden con ref_id")
        return Resolution(assess.RES_FOUND, hash_contract(datos), "")

    return _envolver(_res)


# ---------------------------------------------------------------------------
# quality_evidence / data_contract_result (R23)
# ---------------------------------------------------------------------------


def _resolver_calidad(repo_root: Any, exigir_subject: Optional[str]) -> Callable[[Any], Resolution]:
    raiz = _raiz(repo_root)

    def _res(ref: Any) -> Resolution:
        evidence_id = _id_seguro(getattr(ref, "ref_id", None))
        if _RE_EVIDENCE_ID.fullmatch(evidence_id) is None:
            raise _NoVerificable("ref_id no es un evidence_id de calidad válido")
        base_q = raiz / _DIR_HARMESSI / "quality"
        if not _dentro_de(raiz, base_q):
            raise _NoVerificable("directorio de calidad fuera de repo_root")
        ruta = base_q / evidence_id / "manifest.json"
        if not ruta.exists():
            raise _Ausente("manifest ausente")
        datos = _leer_json(ruta, base_q.resolve())
        if datos.get("evidence_id") != evidence_id:
            raise _NoVerificable("evidence_id interno no coincide con el directorio")
        persistido = datos.get("content_sha256")
        if not isinstance(persistido, str) or _RE_SHA256.fullmatch(persistido) is None:
            raise _NoVerificable("content_sha256 persistido ausente o inválido")
        if hash_quality_manifest(datos) != persistido:
            raise _NoVerificable("integridad rota: content_sha256 persistido != recomputado")
        if exigir_subject is not None and datos.get("subject_kind") != exigir_subject:
            raise _NoVerificable(f"subject_kind distinto de {exigir_subject!r}")
        return Resolution(assess.RES_FOUND, persistido, "")

    return _envolver(_res)


def quality_evidence_resolver(repo_root: Any) -> Callable[[Any], Resolution]:
    """Resolver `quality_evidence` (cualquier `subject_kind`)."""
    return _resolver_calidad(repo_root, None)


def data_contract_result_resolver(repo_root: Any) -> Callable[[Any], Resolution]:
    """Resolver `data_contract_result`: exige `subject_kind == "data_contract_evaluation"`."""
    return _resolver_calidad(repo_root, SUBJECT_DATA_CONTRACT_EVALUATION)


# ---------------------------------------------------------------------------
# Model Cards (Change `20261005-model-cards`, R23-R31)
# ---------------------------------------------------------------------------


def _ruta_por_locator(raiz: Path, ref: Any) -> Path:
    """Ruta absoluta del `locator` del pin: portable, sin ':' y contenida en
    `raiz`. Ausente -> `_Ausente`."""
    locator = getattr(ref, "locator", None)
    if locator is None:
        raise _NoVerificable("sin locator")
    if not core.es_locator_portable(locator) or ":" in locator:
        raise _NoVerificable("locator no portable")
    destino = raiz / locator
    if not _dentro_de(raiz, destino):
        raise _NoVerificable("el locator sale de repo_root")
    if not destino.exists():
        raise _Ausente("archivo ausente")
    return destino


def data_card_resolver(repo_root: Any) -> Callable[[Any], Resolution]:
    """Resolver `data_card` (R23): identidad, existencia, integridad y revisión.
    No evalúa la Data Card ni resuelve su evidencia."""
    raiz = _raiz(repo_root)

    def _res(ref: Any) -> Resolution:
        ref_id = _id_seguro(getattr(ref, "ref_id", None))
        coincidencia = _RE_REF_DATA_CARD.fullmatch(ref_id)
        if coincidencia is None:
            raise _NoVerificable("ref_id no cumple <card_id>__<hash12>")
        card_id = coincidencia.group(1)
        relativo = f"{_DIR_DATA_CARDS}/{card_id}.json"
        locator = getattr(ref, "locator", None)
        if locator is not None and locator != relativo:
            raise _NoVerificable("locator distinto de la ubicación canónica de la Data Card")
        destino = raiz / relativo
        if not _dentro_de(raiz, destino):
            raise _NoVerificable("la Data Card sale de repo_root")
        if not destino.exists():
            raise _Ausente("Data Card ausente")
        try:
            if not destino.is_file():
                raise _NoVerificable("no es un archivo")
            if destino.stat().st_size > MAX_BYTES_LECTURA:
                raise _NoVerificable("archivo excede el tamaño máximo")
        except OSError as exc:
            raise _NoVerificable(f"error de lectura ({type(exc).__name__})") from exc
        card = assess.read_card(destino)  # CardError -> unverifiable (envoltorio)
        if card.card_kind != "data_card":
            raise _NoVerificable("card_kind distinto de 'data_card'")
        if card.card_id != card_id:
            raise _NoVerificable("card_id interno no coincide con ref_id")
        return Resolution(assess.RES_FOUND, card.content_sha256(), "")

    return _envolver(_res)


def model_quality_result_resolver(repo_root: Any) -> Callable[[Any], Resolution]:
    """Resolver `model_quality_result` (R24): exige `subject_kind == "model_quality_evaluation"`."""
    return _resolver_calidad(repo_root, SUBJECT_MODEL_QUALITY_EVALUATION)


def model_quality_policy_resolver(repo_root: Any) -> Callable[[Any], Resolution]:
    """Resolver `model_quality_policy` (R25)."""
    raiz = _raiz(repo_root)

    def _res(ref: Any) -> Resolution:
        policy_id = _id_seguro(getattr(ref, "ref_id", None))
        destino = _ruta_por_locator(raiz, ref)
        datos = _leer_json(destino, raiz)
        if datos.get("policy_id") != policy_id:
            raise _NoVerificable("policy_id interno no coincide con ref_id")
        return Resolution(assess.RES_FOUND, hash_policy(datos), "")

    return _envolver(_res)


def _identidad_metrica(entrada: Any) -> str:
    if not isinstance(entrada, dict):
        raise _NoVerificable("entrada de métrica no es un objeto")
    nombre = entrada.get("metric_name")
    contexto = entrada.get("context")
    ctx_id = contexto.get("context_id") if isinstance(contexto, dict) else None
    if not isinstance(nombre, str) or not nombre or not isinstance(ctx_id, str) or not ctx_id:
        raise _NoVerificable("entrada de métrica con identidad malformada")
    return f"{nombre}@{ctx_id}"


def _identidad_baseline(entrada: Any) -> str:
    if not isinstance(entrada, dict):
        raise _NoVerificable("entrada de baseline no es un objeto")
    baseline_id = entrada.get("baseline_id")
    if not isinstance(baseline_id, str) or not baseline_id:
        raise _NoVerificable("entrada de baseline con identidad malformada")
    return baseline_id


def _resolver_documento_con_member(repo_root: Any, es_metrica: bool) -> Callable[[Any], Resolution]:
    raiz = _raiz(repo_root)

    def _res(ref: Any) -> Resolution:
        member = getattr(ref, "member", None)
        if not isinstance(member, str) or not member:
            raise _NoVerificable("member ausente o inválido")
        if es_metrica:
            nombre, sep, ctx_id = member.partition("@")
            if not sep or not nombre or not ctx_id or "@" in ctx_id:
                raise _NoVerificable("member no cumple <metric_name>@<context_id>")
        destino = _ruta_por_locator(raiz, ref)
        documento = _leer_json(destino, raiz, permitir_lista=True)
        identidad = _identidad_metrica if es_metrica else _identidad_baseline
        # Se validan TODAS las entradas (identidad malformada en cualquiera -> unverifiable).
        identidades = [identidad(entrada) for entrada in documento]
        coincidencias = sum(1 for i in identidades if i == member)
        if coincidencias == 0:
            raise _Ausente("member sin coincidencias en el documento")
        if coincidencias > 1:
            raise _NoVerificable("member ambiguo: más de una coincidencia")
        return Resolution(assess.RES_FOUND, hash_document(documento), "")

    return _envolver(_res)


def observed_metric_resolver(repo_root: Any) -> Callable[[Any], Resolution]:
    """Resolver `observed_metric` (R26): documento completo + `member` `<metric_name>@<context_id>`.

    El selector `<metric_name>@<context_id>` es una CONVENCIÓN PROPIA de Harmessi
    Cards (determinista, inyectiva); NO es la identidad de v0.7:
    `modelquality.validation` selecciona por `metric_name` y coincidencia de
    contexto (split, etc.) y nunca compara `context_id`. Consecuencia
    documentada: dos entradas con el mismo `metric_name` y split pero distinto
    `context_id` resuelven aquí como members distintos, y `ds_guard quality
    evaluate` las vería ambiguas."""
    return _resolver_documento_con_member(repo_root, es_metrica=True)


def baseline_reference_resolver(repo_root: Any) -> Callable[[Any], Resolution]:
    """Resolver `baseline_reference` (R26): documento completo + `member` `<baseline_id>`.

    El `member` es el `baseline_id` de la entrada (selector determinista de
    Harmessi Cards, nunca posicional). Ver la nota sobre la convención de
    `member` en `observed_metric_resolver`: no es la identidad de v0.7 para métricas."""
    return _resolver_documento_con_member(repo_root, es_metrica=False)


def drift_evidence_resolver(repo_root: Any) -> Callable[[Any], Resolution]:
    """Resolver `drift_evidence` (R27)."""
    raiz = _raiz(repo_root)

    def _res(ref: Any) -> Resolution:
        drift_id = _id_seguro(getattr(ref, "ref_id", None))
        if _RE_DRIFT_ID.fullmatch(drift_id) is None:
            raise _NoVerificable("ref_id no es un drift_id válido")
        destino = _ruta_por_locator(raiz, ref)
        datos = _leer_json(destino, raiz)
        if datos.get("drift_id") != drift_id:
            raise _NoVerificable("drift_id interno no coincide con ref_id")
        actual = hash_drift(datos)
        if "content_sha256" in datos and datos["content_sha256"] != actual:
            raise _NoVerificable("integridad rota: content_sha256 persistido != recomputado")
        return Resolution(assess.RES_FOUND, actual, "")

    return _envolver(_res)


def execution_record_resolver(repo_root: Any) -> Callable[[Any], Resolution]:
    """Resolver `execution_record` (R28)."""
    raiz = _raiz(repo_root)

    def _res(ref: Any) -> Resolution:
        execution_id = _id_seguro(getattr(ref, "ref_id", None))
        if _RE_REF_EJECUCION.fullmatch(execution_id) is None:
            raise _NoVerificable("ref_id no cumple <command_form>__<hash12>")
        base_e = raiz / _DIR_HARMESSI / "executions"
        if not _dentro_de(raiz, base_e):
            raise _NoVerificable("directorio de ejecuciones fuera de repo_root")
        ruta = base_e / execution_id / "record.json"
        if not ruta.exists():
            raise _Ausente("record ausente")
        datos = _leer_json(ruta, base_e.resolve())
        if datos.get("execution_id") != execution_id:
            raise _NoVerificable("execution_id interno no coincide con el directorio")
        return Resolution(assess.RES_FOUND, hash_execution_record(datos), "")

    return _envolver(_res)


# ---------------------------------------------------------------------------
# Mapa por defecto (R24)
# ---------------------------------------------------------------------------


def default_resolvers(repo_root: Any) -> dict:
    """Mapa `kind -> resolver` para 12 kinds. Solo `report_artifact` queda sin
    resolver (-> `unverifiable` en `assess.evaluar_evidencia`).
    Lanza `CardError` solo si `repo_root` no es una ruta válida."""
    return {
        KIND_DATA_CARD: data_card_resolver(repo_root),
        KIND_MODEL_QUALITY_RESULT: model_quality_result_resolver(repo_root),
        KIND_MODEL_QUALITY_POLICY: model_quality_policy_resolver(repo_root),
        KIND_OBSERVED_METRIC: observed_metric_resolver(repo_root),
        KIND_BASELINE_REFERENCE: baseline_reference_resolver(repo_root),
        KIND_DRIFT_EVIDENCE: drift_evidence_resolver(repo_root),
        KIND_EXECUTION_RECORD: execution_record_resolver(repo_root),
        KIND_SOURCE_OBSERVATION: source_observation_resolver(repo_root),
        KIND_SOURCE_PROVENANCE: source_provenance_resolver(repo_root),
        KIND_HARMESSI_CONTRACT: harmessi_contract_resolver(repo_root),
        KIND_QUALITY_EVIDENCE: quality_evidence_resolver(repo_root),
        KIND_DATA_CONTRACT_RESULT: data_contract_result_resolver(repo_root),
    }

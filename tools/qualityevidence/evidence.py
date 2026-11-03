"""Persistencia de evidencia de calidad y cómputo de drift (v0.7 Change 3,
`20260922-quality-evidence-and-drift`).

Construye y escribe atómicamente un `qualityevidence.core.QualityEvidenceManifest`
bajo `.harmessi/quality/<evidence_id>/manifest.json` (envolviendo
`list[dsguard.checks.CheckResult]` ya producidos por
`validate_contract`/`evaluate_policy`, Changes 1-2), lo relee verificando su
propio hash, y calcula `qualityevidence.core.DriftEvidence` comparando dos
observaciones (naturalmente, dos `profile.json`) con un vocabulario cerrado de
dos modos de comparación (`DRIFT_COMPARISON_MODES`).

Frontera de imports (R1 de `spec.md`, verificada por
`tools/tests/test_v07_qualityevidence_neutrality.py`): stdlib (incluye `os`,
`tempfile`, `pathlib`) + `dsguard.checks` (para envolver `CheckResult` ya
producidos por el llamador) + `ds_profile.holdout_guard.verificar_permitido`
(único símbolo de `ds_profile`, mismo criterio que
`tools/datacontracts/validation.py`) + `tools.qualityevidence.core` (sibling).
NO importa `tools.datacontracts`, `tools.modelquality`, `tools.reporting` en
ninguna dirección, ni `ds_profile.fingerprint` ni ningún otro símbolo de
`ds_profile` (ver `design.md`, decisión 2: reimplementación local mínima de
hash sha256 chunked, JSON canónico y escritura atómica, mismo criterio que
`tools/dsguard/mlops_evidence.py` frente a `ds_profile.fingerprint`).

Nunca lee un `profile.json` sin `verificar_permitido` ANTES de abrirlo
(`describe_source_file`, `drift_from_profiles` -- ambas rutas de una
comparación de drift, simétrico y fail-closed: si cualquiera está denegada,
ninguna de las dos se abre). Nunca `PASS`/`FAIL` de drift sin `threshold`
declarado (`result_status = "N/A"`, "evidencia registrada sin veredicto").

Privacidad: `EvidenceSource.path` es siempre repo-relativo y posix; ningún
mensaje de error de este módulo reproduce una ruta absoluta local ni
`profile.get("dataset_path")` sin normalizar.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

_TOOLS_DIR = Path(__file__).resolve().parents[1]
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from dsguard import checks  # noqa: E402
from ds_profile.holdout_guard import verificar_permitido  # noqa: E402

from . import core as qe_core  # noqa: E402

# --- Códigos (R11 de spec.md) --------------------------------------------------

CODE_INPUT = "QUALITYEVIDENCE-INPUT"
CODE_SOURCE_DENIED = "QUALITYEVIDENCE-SOURCE-DENIED"
CODE_SOURCE_MISSING = "QUALITYEVIDENCE-SOURCE-MISSING"
CODE_WRITE = "QUALITYEVIDENCE-WRITE"
CODE_READ = "QUALITYEVIDENCE-READ"
CODE_STALE = "QUALITYEVIDENCE-STALE"
CODE_DRIFT_FIELD = "QUALITYEVIDENCE-DRIFT-FIELD"
CODE_DRIFT_DENIED = "QUALITYEVIDENCE-DRIFT-DENIED"

CODES = (
    CODE_INPUT,
    CODE_SOURCE_DENIED,
    CODE_SOURCE_MISSING,
    CODE_WRITE,
    CODE_READ,
    CODE_STALE,
    CODE_DRIFT_FIELD,
    CODE_DRIFT_DENIED,
)

# `field` de `drift_from_profiles` permitido (allowlist acotado, mismo
# vocabulario ya persistido por `ds_profile` y ya consumido por
# `tools/datacontracts/validation.py`; ver `design.md`, decisión 4).
_CAMPOS_NUMERICOS_PERMITIDOS = ("filas", "nulls_count", "unique_count", "min", "max")

_DECLARATION_KIND_A_SUBJECT_KIND = {
    "data_contract": "data_contract_evaluation",
    "model_quality_policy": "model_quality_evaluation",
}


# ---------------------------------------------------------------------------
# Hash y escritura de archivos (R12) -- reimplementados localmente, ver
# docstring del módulo (sin importar `ds_profile.fingerprint` ni
# `tools.reporting.evidence`).
# ---------------------------------------------------------------------------


def _sha256_archivo(ruta: Path, chunk_size: int = 1 << 20) -> str:
    """sha256 binario chunked -- idéntico algoritmo/formato de salida que
    `ds_profile.fingerprint.calcular_fingerprint`/
    `tools/dsguard/mlops_evidence.py:_hash_binario_sha256`."""
    hasher = hashlib.sha256()
    with open(ruta, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def _escribir_atomico(ruta: Path, contenido: bytes) -> None:
    """Escribe `contenido` en `ruta` de forma atómica: archivo temporal en el
    mismo directorio + `os.replace` (mismo patrón que
    `dsguard.core.escribir_texto_atomico`, reimplementado localmente)."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    fd, temporal = tempfile.mkstemp(dir=str(ruta.parent), prefix=f".{ruta.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(contenido)
        os.replace(temporal, ruta)
    except BaseException:
        try:
            os.remove(temporal)
        except OSError:
            pass
        raise


def _json_bytes(obj: Any) -> bytes:
    """Bytes persistidos deterministas: claves ordenadas, indent 2, sin
    escapar no-ASCII, sin NaN, `\\n` final, UTF-8 (mismo formato que
    `tools/reporting/evidence.py:_json_bytes`, reimplementado localmente)."""
    texto = json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    return texto.encode("utf-8")


# ---------------------------------------------------------------------------
# Fuentes (R13)
# ---------------------------------------------------------------------------


def _resolver_dentro_del_repo(repo_root: Any, path: Any) -> tuple:
    """`(repo, resuelto, etiqueta_relativa_posix)`. `QualityEvidenceError`
    (`QUALITYEVIDENCE-SOURCE-MISSING`) si `path` no resuelve o queda fuera del
    repo."""
    repo = Path(repo_root).resolve()
    if not isinstance(path, (str, Path)) or str(path) == "" or "\x00" in str(path):
        raise qe_core.QualityEvidenceError(f"{CODE_SOURCE_MISSING}: path inválido ({path!r})")
    candidato = Path(path)
    if not candidato.is_absolute():
        candidato = repo / candidato
    try:
        resuelto = candidato.resolve()
    except (OSError, RuntimeError, ValueError) as exc:
        raise qe_core.QualityEvidenceError(
            f"{CODE_SOURCE_MISSING}: no se pudo resolver la fuente ({type(exc).__name__})"
        ) from exc
    try:
        relativo = resuelto.relative_to(repo)
    except ValueError as exc:
        raise qe_core.QualityEvidenceError(f"{CODE_SOURCE_MISSING}: la fuente resuelve fuera del repo") from exc
    return repo, resuelto, relativo.as_posix()


def describe_source_file(repo_root: Any, path: Any, *, role: str) -> qe_core.EvidenceSource:
    """Fuente `kind="file"`: aplica `verificar_permitido` ANTES de abrir el
    archivo (denegado -> `QualityEvidenceError` con `QUALITYEVIDENCE-SOURCE-
    DENIED`, el archivo NUNCA se abre); ruta fuera del repo, inexistente o
    no-archivo -> `QUALITYEVIDENCE-SOURCE-MISSING`. `EvidenceSource.path`
    siempre relativo al repo y posix (nunca copia `dataset_path` absoluto)."""
    if not isinstance(role, str) or not role.strip():
        raise qe_core.QualityEvidenceError(f"{CODE_INPUT}: role debe ser un str no vacío (recibido {role!r})")
    repo, resuelto, etiqueta = _resolver_dentro_del_repo(repo_root, path)
    permitido, motivo = verificar_permitido(resuelto, repo)
    if not permitido:
        raise qe_core.QualityEvidenceError(
            f"{CODE_SOURCE_DENIED}: acceso denegado a la fuente {etiqueta!r} (no se abrió): {motivo}"
        )
    if not resuelto.is_file():
        raise qe_core.QualityEvidenceError(f"{CODE_SOURCE_MISSING}: la fuente {etiqueta!r} no existe o no es un archivo")
    sha256 = _sha256_archivo(resuelto)
    return qe_core.EvidenceSource(kind="file", role=role, path=etiqueta, sha256=sha256, algorithm="sha256/bin/v1")


def describe_source_generated(description: Any, params: Any, *, role: str = "input") -> qe_core.EvidenceSource:
    """Fuente `kind="generated"`: pura, sin I/O. `sha256` de
    `canonical_json(params)`."""
    if not isinstance(role, str) or not role.strip():
        raise qe_core.QualityEvidenceError(f"{CODE_INPUT}: role debe ser un str no vacío (recibido {role!r})")
    if not isinstance(description, str) or not description.strip():
        raise qe_core.QualityEvidenceError(f"{CODE_INPUT}: description debe ser un str no vacío")
    if not isinstance(params, dict):
        raise qe_core.QualityEvidenceError(f"{CODE_INPUT}: params debe ser un dict JSON-seguro")
    canonico = qe_core.canonical_json(params)
    sha256 = hashlib.sha256(canonico.encode("utf-8")).hexdigest()
    return qe_core.EvidenceSource(
        kind="generated", role=role, description=description, params=params, sha256=sha256, algorithm="sha256/bin/v1"
    )


# ---------------------------------------------------------------------------
# Ids y reloj (mismo contrato que `reporting.evidence.new_run_id`/
# `_generated_at`, reimplementado localmente)
# ---------------------------------------------------------------------------


def _normalizar_reloj(now: Optional[datetime]) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc)


def new_evidence_id(now: Optional[datetime] = None, *, suffix: Optional[str] = None) -> str:
    """`qe-YYYYMMDDTHHMMSSZ-<sufijo>`. Con `now` fijo el prefijo es
    determinista; el sufijo es aleatorio (6 hex) salvo que se pase `suffix`."""
    ahora = _normalizar_reloj(now)
    sufijo = suffix if suffix else secrets.token_hex(3)
    return f"qe-{ahora.strftime('%Y%m%dT%H%M%SZ')}-{sufijo}"


def new_drift_id(now: Optional[datetime] = None, *, suffix: Optional[str] = None) -> str:
    """`dr-YYYYMMDDTHHMMSSZ-<sufijo>`, mismo criterio que `new_evidence_id`."""
    ahora = _normalizar_reloj(now)
    sufijo = suffix if suffix else secrets.token_hex(3)
    return f"dr-{ahora.strftime('%Y%m%dT%H%M%SZ')}-{sufijo}"


def _generated_at(clock: Optional[Callable[[], Any]]) -> str:
    if clock is None:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    valor = clock()
    if isinstance(valor, datetime):
        if valor.tzinfo is None:
            valor = valor.replace(tzinfo=timezone.utc)
        return valor.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return valor


# ---------------------------------------------------------------------------
# Manifest (R14/R15/R16)
# ---------------------------------------------------------------------------


def build_manifest(
    *,
    subject_kind: str,
    declaration: "qe_core.DeclarationRef",
    source: "qe_core.EvidenceSource",
    results: list,
    scope: Optional["qe_core.ScopeWindow"] = None,
    clock: Optional[Callable[[], Any]] = None,
) -> "qe_core.QualityEvidenceManifest":
    """Envuelve `results` (`list[dsguard.checks.CheckResult]` ya producido
    por el llamador) en un `QualityEvidenceManifest`. Pura salvo que `results`
    ya está en memoria (no abre ningún archivo)."""
    if subject_kind not in qe_core.SUBJECT_KINDS:
        raise qe_core.QualityEvidenceError(f"{CODE_INPUT}: subject_kind {subject_kind!r} fuera de {qe_core.SUBJECT_KINDS}")
    if not isinstance(declaration, qe_core.DeclarationRef):
        raise qe_core.QualityEvidenceError(f"{CODE_INPUT}: declaration debe ser DeclarationRef")
    if declaration.declaration_kind not in _DECLARATION_KIND_A_SUBJECT_KIND:
        raise qe_core.QualityEvidenceError(
            f"{CODE_INPUT}: declaration.declaration_kind {declaration.declaration_kind!r} fuera de "
            f"{tuple(_DECLARATION_KIND_A_SUBJECT_KIND)}"
        )
    if _DECLARATION_KIND_A_SUBJECT_KIND[declaration.declaration_kind] != subject_kind:
        raise qe_core.QualityEvidenceError(
            f"{CODE_INPUT}: subject_kind {subject_kind!r} incoherente con declaration_kind "
            f"{declaration.declaration_kind!r}"
        )
    if not isinstance(source, qe_core.EvidenceSource):
        raise qe_core.QualityEvidenceError(f"{CODE_INPUT}: source debe ser EvidenceSource")
    if not isinstance(results, list) or not all(isinstance(r, checks.CheckResult) for r in results):
        raise qe_core.QualityEvidenceError(f"{CODE_INPUT}: results debe ser list[dsguard.checks.CheckResult]")
    ambito = scope if scope is not None else qe_core.ScopeWindow()
    if not isinstance(ambito, qe_core.ScopeWindow):
        raise qe_core.QualityEvidenceError(f"{CODE_INPUT}: scope debe ser ScopeWindow o None")

    check_results = tuple(r.to_dict() for r in results if r.kind == checks.KIND_CHECK)
    technical_errors = tuple(r.to_dict() for r in results if r.kind == checks.KIND_TECHNICAL_ERROR)

    return qe_core.QualityEvidenceManifest(
        evidence_id=new_evidence_id(now=clock() if clock else None),
        subject_kind=subject_kind,
        declaration=declaration,
        source=source,
        generated_at=_generated_at(clock),
        scope=ambito,
        check_results=check_results,
        technical_errors=technical_errors,
    )


def write_manifest(repo_root: Any, manifest: "qe_core.QualityEvidenceManifest") -> Path:
    """Escribe `.harmessi/quality/<evidence_id>/manifest.json` de forma
    atómica. Idempotente ante el mismo contenido; `QualityEvidenceError`
    (`QUALITYEVIDENCE-WRITE`) ante colisión de `evidence_id` con contenido
    distinto."""
    if not isinstance(manifest, qe_core.QualityEvidenceManifest):
        raise qe_core.QualityEvidenceError(f"{CODE_WRITE}: se esperaba QualityEvidenceManifest")
    repo = Path(repo_root).resolve()
    etiqueta = f".harmessi/quality/{manifest.evidence_id}/manifest.json"
    directorio = repo / ".harmessi" / "quality" / manifest.evidence_id
    ruta = directorio / "manifest.json"
    contenido = _json_bytes(manifest.to_dict())

    if ruta.exists():
        try:
            datos_existentes = json.loads(ruta.read_bytes().decode("utf-8"))
            existente = qe_core.QualityEvidenceManifest.from_dict(datos_existentes)
        except (OSError, ValueError, qe_core.QualityEvidenceError) as exc:
            raise qe_core.QualityEvidenceError(
                f"{CODE_WRITE}: manifest existente en {etiqueta} ilegible o corrupto ({exc})"
            ) from exc
        if existente.content_sha256() == manifest.content_sha256():
            return ruta
        raise qe_core.QualityEvidenceError(
            f"{CODE_WRITE}: colisión de evidence_id {manifest.evidence_id!r} con contenido distinto"
        )

    _escribir_atomico(ruta, contenido)
    return ruta


def read_manifest(repo_root: Any, evidence_id: Any) -> "qe_core.QualityEvidenceManifest":
    """Lee `.harmessi/quality/<evidence_id>/manifest.json`, verifica que
    `content_sha256()` coincide con el persistido -- si no, o el archivo no
    existe/es JSON inválido, `QualityEvidenceError` (`QUALITYEVIDENCE-READ`).
    No aplica `verificar_permitido` (metadata generada por el propio harness,
    no datos ni holdout -- ver `proposal.md`, "Holdout policy")."""
    if not isinstance(evidence_id, str) or not evidence_id or "/" in evidence_id or "\\" in evidence_id or ".." in evidence_id:
        raise qe_core.QualityEvidenceError(f"{CODE_READ}: evidence_id inválido {evidence_id!r}")
    repo = Path(repo_root).resolve()
    etiqueta = f".harmessi/quality/{evidence_id}/manifest.json"
    ruta = repo / ".harmessi" / "quality" / evidence_id / "manifest.json"
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise qe_core.QualityEvidenceError(f"{CODE_READ}: no se pudo leer {etiqueta} ({type(exc).__name__})") from exc
    try:
        manifest = qe_core.QualityEvidenceManifest.from_dict(datos)
    except qe_core.QualityEvidenceError as exc:
        raise qe_core.QualityEvidenceError(f"{CODE_READ}: manifest con forma inválida en {etiqueta}: {exc}") from exc
    persistido = datos.get("content_sha256") if isinstance(datos, dict) else None
    if manifest.content_sha256() != persistido:
        raise qe_core.QualityEvidenceError(f"{CODE_READ}: content_sha256 no coincide con el persistido en {etiqueta}")
    return manifest


# ---------------------------------------------------------------------------
# Drift (R17/R18)
# ---------------------------------------------------------------------------


def build_drift_evidence(
    *,
    metric_name: str,
    baseline_value: Any,
    current_value: Any,
    baseline_window: "qe_core.EvidenceSource",
    baseline_label: str,
    current_window: "qe_core.EvidenceSource",
    current_label: str,
    comparison_mode: str,
    threshold: Optional[float] = None,
    clock: Optional[Callable[[], Any]] = None,
) -> "qe_core.DriftEvidence":
    """Pura, sin I/O. Calcula `observed_difference` con las dos fórmulas
    acotadas de `DRIFT_COMPARISON_MODES`; `relative_diff` con
    `baseline_value == 0` -> `WARN` sin excepción; sin `threshold` ->
    siempre `N/A`, nunca `PASS`/`FAIL`."""
    if comparison_mode not in qe_core.DRIFT_COMPARISON_MODES:
        raise qe_core.QualityEvidenceError(
            f"{CODE_INPUT}: comparison_mode {comparison_mode!r} fuera de {qe_core.DRIFT_COMPARISON_MODES}"
        )
    if isinstance(baseline_value, bool) or not isinstance(baseline_value, (int, float)):
        raise qe_core.QualityEvidenceError(f"{CODE_INPUT}: baseline_value debe ser int/float (no bool)")
    if isinstance(current_value, bool) or not isinstance(current_value, (int, float)):
        raise qe_core.QualityEvidenceError(f"{CODE_INPUT}: current_value debe ser int/float (no bool)")

    baseline_en_cero = baseline_value == 0

    if comparison_mode == "absolute_diff":
        observed_difference: Any = current_value - baseline_value
    else:  # "relative_diff"
        observed_difference = 0.0 if baseline_en_cero else (current_value - baseline_value) / baseline_value

    if comparison_mode == "relative_diff" and baseline_en_cero:
        result_status = "WARN"
        result_message = f"{metric_name}: no verificable (baseline en cero, relative_diff)"
    elif threshold is None:
        result_status = "N/A"
        result_message = "sin threshold declarado: evidencia registrada sin veredicto"
    elif abs(observed_difference) <= threshold:
        result_status = "PASS"
        result_message = (
            f"{metric_name}: diferencia observada {observed_difference!r} dentro del threshold "
            f"{threshold!r} ({comparison_mode}; baseline={baseline_value!r}, current={current_value!r})"
        )
    else:
        result_status = "FAIL"
        result_message = (
            f"{metric_name}: diferencia observada {observed_difference!r} supera el threshold "
            f"{threshold!r} ({comparison_mode}; baseline={baseline_value!r}, current={current_value!r})"
        )

    return qe_core.DriftEvidence(
        drift_id=new_drift_id(now=clock() if clock else None),
        metric_name=metric_name,
        baseline_window=baseline_window,
        baseline_label=baseline_label,
        current_window=current_window,
        current_label=current_label,
        baseline_value=baseline_value,
        current_value=current_value,
        comparison_mode=comparison_mode,
        observed_difference=observed_difference,
        threshold=threshold,
        result_status=result_status,
        result_message=result_message,
        generated_at=_generated_at(clock),
    )


def _resolver_ruta(repo: Path, path: Any) -> Path:
    candidato = Path(path)
    if not candidato.is_absolute():
        candidato = repo / candidato
    return candidato


def _leer_profile_json(ruta: Path, etiqueta: str) -> dict:
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise qe_core.QualityEvidenceError(
            f"{CODE_DRIFT_FIELD}: no se pudo leer el profile.json de la ventana {etiqueta} ({type(exc).__name__})"
        ) from exc
    if not isinstance(datos, dict):
        raise qe_core.QualityEvidenceError(f"{CODE_DRIFT_FIELD}: profile.json de la ventana {etiqueta} no es un objeto JSON")
    return datos


def _extraer_campo_numerico(profile: dict, field: str, column: Optional[str], etiqueta: str) -> Any:
    try:
        if field == "filas":
            valor = profile["filas"]
        elif field == "nulls_count":
            valor = profile["columnas_detalle"][column]["nulls"]["count"]
        elif field == "unique_count":
            valor = profile["columnas_detalle"][column]["unique"]["count"]
        elif field == "min":
            valor = profile["columnas_detalle"][column]["min"]
        else:  # field == "max"
            valor = profile["columnas_detalle"][column]["max"]
    except (KeyError, TypeError) as exc:
        raise qe_core.QualityEvidenceError(
            f"{CODE_DRIFT_FIELD}: no se pudo extraer field={field!r} column={column!r} de la ventana "
            f"{etiqueta!r} ({type(exc).__name__})"
        ) from exc
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        raise qe_core.QualityEvidenceError(
            f"{CODE_DRIFT_FIELD}: valor no numérico para field={field!r} column={column!r} en la ventana {etiqueta!r}"
        )
    return valor


def drift_from_profiles(
    repo_root: Any,
    *,
    metric_name: str,
    baseline_profile_path: Any,
    current_profile_path: Any,
    field: str,
    column: Optional[str] = None,
    comparison_mode: str,
    threshold: Optional[float] = None,
    baseline_label: str = "baseline",
    current_label: str = "current",
    clock: Optional[Callable[[], Any]] = None,
) -> "qe_core.DriftEvidence":
    """Observador natural de drift: dos `profile.json`. `field` restringido a
    `_CAMPOS_NUMERICOS_PERMITIDOS`; aplica `verificar_permitido` a AMBAS rutas
    ANTES de abrir cualquiera (fail-closed simétrico: si cualquiera está
    denegada, ninguna se abre). Nunca lanza fuera de `QualityEvidenceError`."""
    try:
        if field not in _CAMPOS_NUMERICOS_PERMITIDOS:
            raise qe_core.QualityEvidenceError(
                f"{CODE_DRIFT_FIELD}: field {field!r} fuera de {_CAMPOS_NUMERICOS_PERMITIDOS}"
            )
        if field == "filas":
            if column is not None:
                raise qe_core.QualityEvidenceError(f"{CODE_DRIFT_FIELD}: field='filas' exige column=None (nivel dataset)")
        else:
            if not isinstance(column, str) or not column:
                raise qe_core.QualityEvidenceError(
                    f"{CODE_DRIFT_FIELD}: field={field!r} exige column (str no vacío, nivel columna)"
                )

        repo = Path(repo_root).resolve()
        baseline_abs = _resolver_ruta(repo, baseline_profile_path)
        current_abs = _resolver_ruta(repo, current_profile_path)

        permitido_baseline, motivo_baseline = verificar_permitido(baseline_abs, repo)
        permitido_current, motivo_current = verificar_permitido(current_abs, repo)
        if not permitido_baseline or not permitido_current:
            detalles = []
            if not permitido_baseline:
                detalles.append(f"baseline: {motivo_baseline}")
            if not permitido_current:
                detalles.append(f"current: {motivo_current}")
            raise qe_core.QualityEvidenceError(
                f"{CODE_DRIFT_DENIED}: acceso denegado ({'; '.join(detalles)}); ningún profile.json se abrió"
            )

        baseline_profile = _leer_profile_json(baseline_abs, "baseline")
        current_profile = _leer_profile_json(current_abs, "current")

        baseline_value = _extraer_campo_numerico(baseline_profile, field, column, "baseline")
        current_value = _extraer_campo_numerico(current_profile, field, column, "current")

        baseline_window = describe_source_file(repo, baseline_abs, role="profile")
        current_window = describe_source_file(repo, current_abs, role="profile")

        return build_drift_evidence(
            metric_name=metric_name,
            baseline_value=baseline_value,
            current_value=current_value,
            baseline_window=baseline_window,
            baseline_label=baseline_label,
            current_window=current_window,
            current_label=current_label,
            comparison_mode=comparison_mode,
            threshold=threshold,
            clock=clock,
        )
    except qe_core.QualityEvidenceError:
        raise
    except Exception as exc:  # noqa: BLE001 -- contrato: nunca lanza fuera de QualityEvidenceError
        raise qe_core.QualityEvidenceError(f"{CODE_DRIFT_FIELD}: error inesperado ({type(exc).__name__}: {exc})") from exc


# ---------------------------------------------------------------------------
# Convención de `evidence_ref` (R19, decisión 5 de `design.md`)
# ---------------------------------------------------------------------------

_PREFIJO_EVIDENCE_REF = "quality:"


def resolve_evidence_ref(evidence_ref: Any, repo_root: Any) -> dict:
    """Si `evidence_ref` sigue la convención
    `"quality:.harmessi/quality/<evidence_id>/manifest.json"`, intenta leer y
    verificar ESE manifest. Nunca lanza, nunca asume que todo `evidence_ref`
    sigue la convención."""
    if not isinstance(evidence_ref, str) or not evidence_ref.startswith(_PREFIJO_EVIDENCE_REF):
        return {"resolvable": False, "detail": "no sigue la convención quality:<ruta>"}

    resto = evidence_ref[len(_PREFIJO_EVIDENCE_REF):]
    partes = resto.split("/")
    if len(partes) != 4 or partes[0] != ".harmessi" or partes[1] != "quality" or partes[3] != "manifest.json" or not partes[2]:
        return {"resolvable": True, "valid": False, "detail": "ruta con forma inesperada", "manifest": None}

    evidence_id = partes[2]
    try:
        manifest = read_manifest(repo_root, evidence_id)
    except qe_core.QualityEvidenceError as exc:
        return {"resolvable": True, "valid": False, "detail": str(exc), "manifest": None}
    except Exception as exc:  # noqa: BLE001 -- contrato: nunca lanza
        return {
            "resolvable": True,
            "valid": False,
            "detail": f"error inesperado ({type(exc).__name__}: {exc})",
            "manifest": None,
        }
    return {"resolvable": True, "valid": True, "detail": "manifest válido y verificado", "manifest": manifest.to_dict()}

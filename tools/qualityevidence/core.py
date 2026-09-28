"""Tipos neutrales de evidencia de calidad (v0.7 Change 3,
`20260922-quality-evidence-and-drift`).

Módulo solo-stdlib: declara, en memoria, la FORMA de dos tipos de evidencia --

- `QualityEvidenceManifest`: envuelve `list[dsguard.checks.CheckResult]` YA
  producidos por `validate_contract`/`evaluate_policy` (Changes 1/2), contra
  qué declaración (`DeclarationRef`) y con qué fuente de origen
  (`EvidenceSource`).
- `DriftEvidence`: compara DOS observaciones YA extraídas (`baseline_value`/
  `current_value`) con un vocabulario cerrado de dos modos de comparación
  (`DRIFT_COMPARISON_MODES`), nunca calcula nada desde datos crudos.

Este módulo NO observa ni evalúa ningún dato: ningún constructor acepta un
argumento que represente datos crudos, un `DataFrame`, una ruta de dataset/
holdout, ni ningún parámetro llamado `data`/`frame`/`dataframe`/`predictions`/
`rows`. La persistencia (escritura/lectura de archivo) y el cómputo de drift a
partir de `profile.json` son responsabilidad de `tools/qualityevidence/
evidence.py`, que puede importar este módulo pero nunca al revés.

Familia independiente de `tools.datacontracts`/`tools.modelquality`/
`tools.reporting`: no importa ninguno de los tres, ni comparte ningún tipo
(ver `design.md` del Change, decisiones 1-2). `_STATUS_VALIDOS`/
`_KINDS_VALIDOS` coinciden, a propósito, con los literales de texto de
`dsguard.checks.STATUS_*`/`KIND_*` -- este módulo NO importa `dsguard`; es una
coincidencia de vocabulario documentada, no una dependencia de código (mismo
criterio que `SEVERITIES` en `tools/datacontracts/core.py`/
`tools/modelquality/core.py`).

Todo error de forma de este módulo lanza `QualityEvidenceError`, nunca
`TypeError`/`KeyError` crudos.

Serialización determinista: `to_dict()`/`from_dict()` por dataclass,
`canonical_json()` y `content_sha256()` (método, no campo del dataclass) de
`QualityEvidenceManifest` y de `DriftEvidence` -- excluye SIEMPRE
`generated_at` (y la propia clave `content_sha256` del `to_dict()`
persistido): misma entrada produce el mismo hash sin importar cuándo se
generó (requisito de reproducibilidad del roadmap).
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field as _campo_dataclass
from datetime import datetime
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Vocabularios y constantes
# ---------------------------------------------------------------------------

SCHEMA_VERSION = 1

SUBJECT_KINDS = ("data_contract_evaluation", "model_quality_evaluation")
EVIDENCE_SOURCE_KINDS = ("file", "generated")
DRIFT_COMPARISON_MODES = ("absolute_diff", "relative_diff")

# Mismos literales de texto que `dsguard.checks.STATUS_*`/`KIND_*`
# (`tools/dsguard/checks.py:14-22`); NO se importa `dsguard` -- coincidencia de
# vocabulario documentada, no dependencia de código (ver docstring del módulo).
_STATUS_VALIDOS = ("PASS", "WARN", "FAIL", "N/A")
_KINDS_VALIDOS = ("check", "technical_error")


class QualityEvidenceError(ValueError):
    """Violación de forma de evidencia de calidad (entrada estructuralmente
    inválida)."""


# ---------------------------------------------------------------------------
# Helpers privados de validación / normalización
# ---------------------------------------------------------------------------

# `evidence_id`/`drift_id`: mismo formato de timestamp UTC + sufijo
# hexadecimal que `reporting.evidence.new_run_id`, reimplementado localmente
# (ver R3 de `spec.md`).
_PATRON_EVIDENCE_ID = re.compile(r"qe-\d{8}T\d{6}Z-[0-9a-f]{6}")
_PATRON_DRIFT_ID = re.compile(r"dr-\d{8}T\d{6}Z-[0-9a-f]{6}")

# `metric_name`: snake_case estricto, mismo patrón que
# `ObservedMetric.metric_name` de Change 2, reimplementado localmente (ver
# `design.md`, decisión 1 de Change 2, mismo criterio de no-import entre
# familias).
_PATRON_METRIC_NAME = re.compile(r"[a-z][a-z0-9_]*")

_RE_SHA256 = re.compile(r"[0-9a-fA-F]{64}")

_CLAVES_RESULTADO_PERMITIDAS = frozenset({"status", "code", "message", "kind", "detail", "subject"})


def _exigir_str(valor: Any, campo: str) -> str:
    if not isinstance(valor, str):
        raise QualityEvidenceError(f"{campo}: se esperaba str, se recibió {type(valor).__name__}")
    return valor


def _exigir_str_no_vacio(valor: Any, campo: str) -> str:
    _exigir_str(valor, campo)
    if valor == "":
        raise QualityEvidenceError(f"{campo}: no puede ser vacío")
    return valor


def _exigir_dict(valor: Any, campo: str) -> dict:
    if not isinstance(valor, dict):
        raise QualityEvidenceError(f"{campo}: se esperaba dict, se recibió {type(valor).__name__}")
    return valor


def _es_finito(valor: Any) -> bool:
    """`True` sii `valor` (ya sabido `int`/`float`) es finito -- sin importar
    `math`, mismo criterio que `tools/datacontracts/core.py`."""
    return valor == valor and valor not in (float("inf"), float("-inf"))


def _exigir_numero_finito(valor: Any, campo: str) -> Any:
    """Exige `int` o `float` finito, nunca `bool`; devuelve el mismo valor."""
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        raise QualityEvidenceError(f"{campo}: se esperaba int o float (no bool), se recibió {valor!r}")
    if isinstance(valor, float) and not _es_finito(valor):
        raise QualityEvidenceError(f"{campo}: float no finito ({valor!r})")
    return valor


def _validar_evidence_id(valor: Any) -> str:
    if not isinstance(valor, str) or _PATRON_EVIDENCE_ID.fullmatch(valor) is None:
        raise QualityEvidenceError(
            f"evidence_id inválido {valor!r} (formato esperado: 'qe-' + 8 dígitos + 'T' + 6 dígitos + "
            "'Z' + '-' + 6 caracteres hexadecimales, p. ej. qe-20260922T120000Z-abc123)"
        )
    return valor


def _validar_drift_id(valor: Any) -> str:
    if not isinstance(valor, str) or _PATRON_DRIFT_ID.fullmatch(valor) is None:
        raise QualityEvidenceError(
            f"drift_id inválido {valor!r} (formato esperado: 'dr-' + 8 dígitos + 'T' + 6 dígitos + "
            "'Z' + '-' + 6 caracteres hexadecimales, p. ej. dr-20260922T120000Z-abc123)"
        )
    return valor


def _validar_metric_name(valor: Any, campo: str = "metric_name") -> str:
    if not isinstance(valor, str) or _PATRON_METRIC_NAME.fullmatch(valor) is None:
        raise QualityEvidenceError(f"{campo}: metric_name inválido {valor!r} (debe cumplir ^[a-z][a-z0-9_]*$)")
    return valor


def _validar_sha256_hex(valor: Any, campo: str) -> str:
    if not isinstance(valor, str) or _RE_SHA256.fullmatch(valor) is None:
        raise QualityEvidenceError(
            f"{campo}: se esperaba una cadena hexadecimal de 64 caracteres, se recibió {valor!r}"
        )
    return valor


def _parsear_fecha(valor: Any, campo: str) -> datetime:
    """`datetime.fromisoformat` tras reemplazar un sufijo `'Z'` por
    `'+00:00'` (mismo criterio que el resto del repo). Error ->
    `QualityEvidenceError`."""
    if not isinstance(valor, str) or not valor:
        raise QualityEvidenceError(f"{campo}: se esperaba str no vacío (fecha ISO 8601)")
    texto = valor[:-1] + "+00:00" if valor.endswith("Z") else valor
    try:
        return datetime.fromisoformat(texto)
    except ValueError as exc:
        raise QualityEvidenceError(f"{campo}: fecha inválida {valor!r} (se esperaba ISO 8601)") from exc


def _ruta_relativa_posix_valida(valor: Any) -> bool:
    """Ruta relativa posix segura (mismo criterio que
    `tools/reporting/evidence.py:_ruta_relativa_segura`, reimplementado
    localmente): sin `\\`, sin `:`, sin absoluta, sin segmentos `.`/`..`/
    vacíos."""
    if not isinstance(valor, str) or not valor or "\\" in valor:
        return False
    if valor.startswith("/") or ":" in valor:
        return False
    for segmento in valor.split("/"):
        if segmento in ("", ".", ".."):
            return False
    return True


def _json_puro(valor: Any, ruta: str) -> Any:
    """Copia profunda de `valor` normalizada a estructura JSON pura: `tuple`
    -> `list`, claves `str`, `float` finito. Cualquier otro tipo es error
    (mismo criterio que `tools/datacontracts/core.py`/
    `tools/modelquality/core.py`, reimplementado localmente)."""
    if valor is None:
        return None
    if isinstance(valor, bool):
        return bool(valor)
    if isinstance(valor, str):
        return str(valor)
    if isinstance(valor, int):
        return int(valor)
    if isinstance(valor, float):
        if not _es_finito(valor):
            raise QualityEvidenceError(f"{ruta}: float no finito ({valor!r}) no es JSON-seguro")
        return float(valor)
    if isinstance(valor, (list, tuple)):
        return [_json_puro(item, f"{ruta}[{i}]") for i, item in enumerate(valor)]
    if isinstance(valor, dict):
        resultado: dict = {}
        for clave, item in valor.items():
            if not isinstance(clave, str):
                raise QualityEvidenceError(
                    f"{ruta}: clave no-str {clave!r} ({type(clave).__name__}) no es JSON-seguro"
                )
            resultado[clave] = _json_puro(item, f"{ruta}.{clave}")
        return resultado
    raise QualityEvidenceError(f"{ruta}: tipo {type(valor).__name__} no es JSON-seguro")


def _dict_json_puro(valor: Any, campo: str) -> dict:
    try:
        return _json_puro(_exigir_dict(valor, campo), campo)
    except RecursionError as exc:
        raise QualityEvidenceError(f"{campo}: estructura circular o demasiado profunda") from exc


def _validar_resultado_dict(item: Any, campo: str) -> dict:
    if not isinstance(item, dict):
        raise QualityEvidenceError(f"{campo}: se esperaba dict, se recibió {type(item).__name__}")
    extra = set(item.keys()) - _CLAVES_RESULTADO_PERMITIDAS
    if extra:
        raise QualityEvidenceError(f"{campo}: claves no permitidas {sorted(extra)}")
    status = item.get("status")
    if status not in _STATUS_VALIDOS:
        raise QualityEvidenceError(f"{campo}.status: {status!r} fuera de {_STATUS_VALIDOS}")
    code = item.get("code")
    if not isinstance(code, str) or not code:
        raise QualityEvidenceError(f"{campo}.code: se esperaba str no vacío")
    message = item.get("message")
    if not isinstance(message, str) or not message:
        raise QualityEvidenceError(f"{campo}.message: se esperaba str no vacío")
    if "kind" in item and item["kind"] not in _KINDS_VALIDOS:
        raise QualityEvidenceError(f"{campo}.kind: {item['kind']!r} fuera de {_KINDS_VALIDOS}")
    for opcional in ("detail", "subject"):
        if opcional in item and not isinstance(item[opcional], str):
            raise QualityEvidenceError(f"{campo}.{opcional}: se esperaba str")
    return _json_puro(item, campo)


def _validar_resultados(valor: Any, campo: str) -> tuple:
    if not isinstance(valor, (list, tuple)):
        raise QualityEvidenceError(f"{campo}: se esperaba list o tuple, se recibió {type(valor).__name__}")
    return tuple(_validar_resultado_dict(item, f"{campo}[{i}]") for i, item in enumerate(valor))


def _requeridos(datos: Any, nombres: tuple, tipo: str) -> None:
    if not isinstance(datos, dict):
        raise QualityEvidenceError(f"{tipo}.from_dict: se esperaba dict, se recibió {type(datos).__name__}")
    faltantes = [n for n in nombres if n not in datos]
    if faltantes:
        raise QualityEvidenceError(f"{tipo}.from_dict: faltan campos requeridos {faltantes}")


def canonical_json(obj: Any) -> str:
    """JSON canónico: claves ordenadas, sin espacios, sin escapar no-ASCII,
    sin `NaN`/`Infinity`. Un fallo de serialización lanza
    `QualityEvidenceError`."""
    try:
        return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError, RecursionError) as exc:
        raise QualityEvidenceError(f"canonical_json: objeto no serializable ({exc})") from exc


# ---------------------------------------------------------------------------
# EvidenceSource
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EvidenceSource:
    """Fuente/origen de una evidencia: un archivo del repo (`kind="file"`,
    p. ej. un `profile.json`) o un valor generado en memoria
    (`kind="generated"`, p. ej. un conteo sintético con `params`
    declarados)."""

    kind: str
    role: str
    path: Optional[str] = None
    sha256: Optional[str] = None
    algorithm: str = "sha256/bin/v1"
    description: Optional[str] = None
    params: Optional[dict] = None

    def __post_init__(self) -> None:
        if self.kind not in EVIDENCE_SOURCE_KINDS:
            raise QualityEvidenceError(f"EvidenceSource.kind: {self.kind!r} fuera de {EVIDENCE_SOURCE_KINDS}")
        _exigir_str_no_vacio(self.role, "EvidenceSource.role")
        if not isinstance(self.algorithm, str) or not self.algorithm:
            raise QualityEvidenceError("EvidenceSource.algorithm: se esperaba str no vacío")

        if self.kind == "file":
            if self.path is None:
                raise QualityEvidenceError("EvidenceSource.path: obligatorio para kind='file'")
            if not _ruta_relativa_posix_valida(self.path):
                raise QualityEvidenceError(
                    f"EvidenceSource.path: se esperaba una ruta relativa al repo, posix, sin '..' "
                    f"(recibido {self.path!r})"
                )
            if self.sha256 is None:
                raise QualityEvidenceError("EvidenceSource.sha256: obligatorio para kind='file'")
            _validar_sha256_hex(self.sha256, "EvidenceSource.sha256")
            if self.description is not None:
                raise QualityEvidenceError("EvidenceSource.description: solo aplica a kind='generated'")
            if self.params is not None:
                raise QualityEvidenceError("EvidenceSource.params: solo aplica a kind='generated'")
        else:  # kind == "generated"
            if self.path is not None:
                raise QualityEvidenceError("EvidenceSource.path: debe ser None para kind='generated'")
            if not isinstance(self.description, str) or not self.description.strip():
                raise QualityEvidenceError(
                    "EvidenceSource.description: obligatorio (str no vacío) para kind='generated'"
                )
            if self.params is None:
                raise QualityEvidenceError(
                    "EvidenceSource.params: obligatorio (dict JSON-seguro) para kind='generated'"
                )
            params_norm = _dict_json_puro(self.params, "EvidenceSource.params")
            object.__setattr__(self, "params", params_norm)
            if self.sha256 is None:
                raise QualityEvidenceError("EvidenceSource.sha256: obligatorio para kind='generated'")
            _validar_sha256_hex(self.sha256, "EvidenceSource.sha256")

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "role": self.role,
            "path": self.path,
            "sha256": self.sha256,
            "algorithm": self.algorithm,
            "description": self.description,
            "params": None if self.params is None else _json_puro(self.params, "EvidenceSource.params"),
        }

    @classmethod
    def from_dict(cls, datos: dict) -> "EvidenceSource":
        _requeridos(datos, ("kind", "role"), "EvidenceSource")
        return cls(
            **{
                n: datos[n]
                for n in ("kind", "role", "path", "sha256", "algorithm", "description", "params")
                if n in datos
            }
        )


# ---------------------------------------------------------------------------
# DeclarationRef
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DeclarationRef:
    """Referencia (plana, sin importar el tipo real) a la declaración
    evaluada: `contract_id`/`policy_id` + `content_sha256` ya extraídos por el
    llamador de `DataContract`/`ModelQualityPolicy` en memoria (ver
    `design.md`, "Supuestos descartados" de `proposal.md`)."""

    declaration_kind: str
    declaration_id: str
    version: Optional[str] = None
    content_sha256: str = ""

    def __post_init__(self) -> None:
        _exigir_str_no_vacio(self.declaration_kind, "DeclarationRef.declaration_kind")
        _exigir_str_no_vacio(self.declaration_id, "DeclarationRef.declaration_id")
        if self.version is not None:
            _exigir_str(self.version, "DeclarationRef.version")
        _validar_sha256_hex(self.content_sha256, "DeclarationRef.content_sha256")

    def to_dict(self) -> dict:
        return {
            "declaration_kind": self.declaration_kind,
            "declaration_id": self.declaration_id,
            "version": self.version,
            "content_sha256": self.content_sha256,
        }

    @classmethod
    def from_dict(cls, datos: dict) -> "DeclarationRef":
        _requeridos(datos, ("declaration_kind", "declaration_id", "content_sha256"), "DeclarationRef")
        return cls(
            **{n: datos[n] for n in ("declaration_kind", "declaration_id", "version", "content_sha256") if n in datos}
        )


# ---------------------------------------------------------------------------
# ScopeWindow
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ScopeWindow:
    """Ventana declarada (texto libre, nunca calculada ni verificada contra
    un dataset real): `population` + rango temporal opcional (uno o ambos
    extremos)."""

    population: str = ""
    time_start: Optional[str] = None
    time_end: Optional[str] = None

    def __post_init__(self) -> None:
        _exigir_str(self.population, "ScopeWindow.population")
        inicio = None
        fin = None
        if self.time_start is not None:
            inicio = _parsear_fecha(self.time_start, "ScopeWindow.time_start")
        if self.time_end is not None:
            fin = _parsear_fecha(self.time_end, "ScopeWindow.time_end")
        if inicio is not None and fin is not None and inicio > fin:
            raise QualityEvidenceError("ScopeWindow: time_start debe ser <= time_end")

    def to_dict(self) -> dict:
        return {"population": self.population, "time_start": self.time_start, "time_end": self.time_end}

    @classmethod
    def from_dict(cls, datos: dict) -> "ScopeWindow":
        if not isinstance(datos, dict):
            raise QualityEvidenceError(f"ScopeWindow.from_dict: se esperaba dict, se recibió {type(datos).__name__}")
        return cls(**{n: datos[n] for n in ("population", "time_start", "time_end") if n in datos})


# ---------------------------------------------------------------------------
# QualityEvidenceManifest (raíz)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class QualityEvidenceManifest:
    """Envuelve `list[dsguard.checks.CheckResult]` ya producidos (separados
    en `check_results`/`technical_errors` por el llamador, ver
    `evidence.build_manifest`) contra la declaración (`DeclarationRef`) y la
    fuente de origen (`EvidenceSource`) evaluadas. `content_sha256()`
    (método) excluye `generated_at`."""

    evidence_id: str
    subject_kind: str
    declaration: DeclarationRef
    source: EvidenceSource
    generated_at: str
    scope: ScopeWindow = _campo_dataclass(default_factory=ScopeWindow)
    check_results: tuple = ()
    technical_errors: tuple = ()
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            isinstance(self.schema_version, bool)
            or not isinstance(self.schema_version, int)
            or self.schema_version != SCHEMA_VERSION
        ):
            raise QualityEvidenceError(
                f"QualityEvidenceManifest.schema_version: se esperaba {SCHEMA_VERSION}, se recibió "
                f"{self.schema_version!r}"
            )
        _validar_evidence_id(self.evidence_id)
        if self.subject_kind not in SUBJECT_KINDS:
            raise QualityEvidenceError(
                f"QualityEvidenceManifest.subject_kind: {self.subject_kind!r} fuera de {SUBJECT_KINDS}"
            )
        if not isinstance(self.declaration, DeclarationRef):
            raise QualityEvidenceError(
                f"QualityEvidenceManifest.declaration: se esperaba DeclarationRef, se recibió "
                f"{type(self.declaration).__name__}"
            )
        if not isinstance(self.source, EvidenceSource):
            raise QualityEvidenceError(
                f"QualityEvidenceManifest.source: se esperaba EvidenceSource, se recibió "
                f"{type(self.source).__name__}"
            )
        if not isinstance(self.scope, ScopeWindow):
            raise QualityEvidenceError(
                f"QualityEvidenceManifest.scope: se esperaba ScopeWindow, se recibió {type(self.scope).__name__}"
            )
        check_results = _validar_resultados(self.check_results, "QualityEvidenceManifest.check_results")
        technical_errors = _validar_resultados(self.technical_errors, "QualityEvidenceManifest.technical_errors")
        _parsear_fecha(self.generated_at, "QualityEvidenceManifest.generated_at")
        object.__setattr__(self, "check_results", check_results)
        object.__setattr__(self, "technical_errors", technical_errors)

    # -- serialización --------------------------------------------------

    def _base_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "evidence_id": self.evidence_id,
            "subject_kind": self.subject_kind,
            "declaration": self.declaration.to_dict(),
            "source": self.source.to_dict(),
            "scope": self.scope.to_dict(),
            "check_results": [dict(r) for r in self.check_results],
            "technical_errors": [dict(r) for r in self.technical_errors],
            "generated_at": self.generated_at,
        }

    def to_dict(self) -> dict:
        base = self._base_dict()
        base["content_sha256"] = self.content_sha256()
        return base

    def content_sha256(self) -> str:
        """sha256 (hex) de `canonical_json(to_dict() sin 'generated_at' ni
        'content_sha256')`; idéntico entre corridas para el mismo contenido."""
        datos = self._base_dict()
        datos.pop("generated_at", None)
        return hashlib.sha256(canonical_json(datos).encode("utf-8")).hexdigest()

    @classmethod
    def from_dict(cls, datos: dict) -> "QualityEvidenceManifest":
        _requeridos(
            datos,
            ("schema_version", "evidence_id", "subject_kind", "declaration", "source", "generated_at"),
            "QualityEvidenceManifest",
        )
        if datos["schema_version"] != SCHEMA_VERSION:
            raise QualityEvidenceError(
                f"QualityEvidenceManifest.from_dict.schema_version: se esperaba {SCHEMA_VERSION}, se "
                f"recibió {datos['schema_version']!r}"
            )
        return cls(
            evidence_id=datos["evidence_id"],
            subject_kind=datos["subject_kind"],
            declaration=DeclarationRef.from_dict(datos["declaration"]),
            source=EvidenceSource.from_dict(datos["source"]),
            generated_at=datos["generated_at"],
            scope=ScopeWindow.from_dict(datos["scope"]) if "scope" in datos and datos["scope"] is not None else ScopeWindow(),
            check_results=tuple(datos.get("check_results", ())),
            technical_errors=tuple(datos.get("technical_errors", ())),
            schema_version=datos["schema_version"],
        )


# ---------------------------------------------------------------------------
# DriftEvidence (raíz)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DriftEvidence:
    """Compara DOS observaciones YA extraídas (`baseline_value`/
    `current_value`) bajo un `comparison_mode` acotado. `observed_difference`
    es validado (no recalculado) por este módulo -- el cálculo es
    responsabilidad de `evidence.build_drift_evidence`. `content_sha256()`
    (método) excluye `generated_at`."""

    drift_id: str
    metric_name: str
    baseline_window: EvidenceSource
    baseline_label: str
    current_window: EvidenceSource
    current_label: str
    baseline_value: Any
    current_value: Any
    comparison_mode: str
    observed_difference: Any
    result_status: str
    result_message: str
    generated_at: str
    threshold: Optional[float] = None
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            isinstance(self.schema_version, bool)
            or not isinstance(self.schema_version, int)
            or self.schema_version != SCHEMA_VERSION
        ):
            raise QualityEvidenceError(
                f"DriftEvidence.schema_version: se esperaba {SCHEMA_VERSION}, se recibió {self.schema_version!r}"
            )
        _validar_drift_id(self.drift_id)
        _validar_metric_name(self.metric_name, "DriftEvidence.metric_name")
        if not isinstance(self.baseline_window, EvidenceSource):
            raise QualityEvidenceError(
                f"DriftEvidence.baseline_window: se esperaba EvidenceSource, se recibió "
                f"{type(self.baseline_window).__name__}"
            )
        _exigir_str_no_vacio(self.baseline_label, "DriftEvidence.baseline_label")
        if not isinstance(self.current_window, EvidenceSource):
            raise QualityEvidenceError(
                f"DriftEvidence.current_window: se esperaba EvidenceSource, se recibió "
                f"{type(self.current_window).__name__}"
            )
        _exigir_str_no_vacio(self.current_label, "DriftEvidence.current_label")
        _exigir_numero_finito(self.baseline_value, "DriftEvidence.baseline_value")
        _exigir_numero_finito(self.current_value, "DriftEvidence.current_value")
        if self.comparison_mode not in DRIFT_COMPARISON_MODES:
            raise QualityEvidenceError(
                f"DriftEvidence.comparison_mode: {self.comparison_mode!r} fuera de {DRIFT_COMPARISON_MODES}"
            )
        _exigir_numero_finito(self.observed_difference, "DriftEvidence.observed_difference")
        if self.threshold is not None:
            umbral = _exigir_numero_finito(self.threshold, "DriftEvidence.threshold")
            if umbral < 0:
                raise QualityEvidenceError(f"DriftEvidence.threshold: debe ser >= 0, se recibió {umbral!r}")
        if self.result_status not in _STATUS_VALIDOS:
            raise QualityEvidenceError(f"DriftEvidence.result_status: {self.result_status!r} fuera de {_STATUS_VALIDOS}")
        _exigir_str_no_vacio(self.result_message, "DriftEvidence.result_message")
        _parsear_fecha(self.generated_at, "DriftEvidence.generated_at")

    # -- serialización --------------------------------------------------

    def _base_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "drift_id": self.drift_id,
            "metric_name": self.metric_name,
            "baseline_window": self.baseline_window.to_dict(),
            "baseline_label": self.baseline_label,
            "current_window": self.current_window.to_dict(),
            "current_label": self.current_label,
            "baseline_value": self.baseline_value,
            "current_value": self.current_value,
            "comparison_mode": self.comparison_mode,
            "observed_difference": self.observed_difference,
            "threshold": self.threshold,
            "result_status": self.result_status,
            "result_message": self.result_message,
            "generated_at": self.generated_at,
        }

    def to_dict(self) -> dict:
        base = self._base_dict()
        base["content_sha256"] = self.content_sha256()
        return base

    def content_sha256(self) -> str:
        datos = self._base_dict()
        datos.pop("generated_at", None)
        return hashlib.sha256(canonical_json(datos).encode("utf-8")).hexdigest()

    @classmethod
    def from_dict(cls, datos: dict) -> "DriftEvidence":
        _requeridos(
            datos,
            (
                "schema_version",
                "drift_id",
                "metric_name",
                "baseline_window",
                "baseline_label",
                "current_window",
                "current_label",
                "baseline_value",
                "current_value",
                "comparison_mode",
                "observed_difference",
                "result_status",
                "result_message",
                "generated_at",
            ),
            "DriftEvidence",
        )
        if datos["schema_version"] != SCHEMA_VERSION:
            raise QualityEvidenceError(
                f"DriftEvidence.from_dict.schema_version: se esperaba {SCHEMA_VERSION}, se recibió "
                f"{datos['schema_version']!r}"
            )
        return cls(
            drift_id=datos["drift_id"],
            metric_name=datos["metric_name"],
            baseline_window=EvidenceSource.from_dict(datos["baseline_window"]),
            baseline_label=datos["baseline_label"],
            current_window=EvidenceSource.from_dict(datos["current_window"]),
            current_label=datos["current_label"],
            baseline_value=datos["baseline_value"],
            current_value=datos["current_value"],
            comparison_mode=datos["comparison_mode"],
            observed_difference=datos["observed_difference"],
            result_status=datos["result_status"],
            result_message=datos["result_message"],
            generated_at=datos["generated_at"],
            threshold=datos.get("threshold"),
            schema_version=datos["schema_version"],
        )

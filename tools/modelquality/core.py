"""Políticas neutrales de calidad de modelo (v0.7 Change 2,
`20260922-model-quality-policies`).

Módulo solo-stdlib: declara, en memoria, una `ModelQualityPolicy` como árbol de
objetos inmutables que expresa qué calidad mínima se exige a un modelo
(`MetricRequirement`), en qué contexto se mide (`EvaluationContext`), qué valor
YA fue reportado (`ObservedMetric`) y contra qué referencia externa se compara
(`BaselineReference`).

Este módulo NO entrena modelos, NO calcula ninguna métrica (AUC/F1/RMSE/etc.)
y NO observa ningún dato: ningún constructor acepta un argumento que
represente datos crudos, predicciones, un `DataFrame`, una ruta de dataset/
holdout, ni ningún parámetro llamado `data`/`frame`/`dataframe`/`predictions`/
`rows`/`path`/`ruta`. `ObservedMetric.value` es siempre un valor YA reportado
por el proyecto, recibido como número, nunca calculado por este módulo.

`tools/modelquality` es una familia paralela e independiente de
`tools/datacontracts` (Changes 0-1): no importa ni es importado por ella, ni
comparte ningún tipo -- incluida la coincidencia de vocabulario
`SEVERITIES = ("FAIL", "WARN")`, que es una coincidencia de texto documentada,
no una dependencia de código (ver `design.md` del Change, decisión 1).

Todo error de forma de este módulo lanza `ModelQualityError`, nunca
`TypeError`/`KeyError` crudos.

Serialización determinista: `to_dict()`/`from_dict()` por dataclass,
`canonical_json()` y `ModelQualityPolicy.content_sha256()` (identidad de
contenido). Solo `ModelQualityPolicy` (la raíz versionable) expone
`content_sha256()`; `EvaluationContext`/`MetricRequirement`/`ObservedMetric`/
`BaselineReference` son valores de evidencia/declaración en tiempo de
evaluación, sin identidad de contenido persistida en este Change.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field as _campo_dataclass
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Vocabularios y constantes
# ---------------------------------------------------------------------------

SCHEMA_VERSION = 1

# Prefijo de claves de extensión controladas (mismo patrón que
# `tools/datacontracts/core.py:56`).
EXTENSION_PREFIX = "x_"

MODEL_TASK_ROLES = (
    "classification",
    "regression",
    "ranking",
    "clustering",
    "forecasting",
    "generic",
)
DIRECTIONS = ("higher_is_better", "lower_is_better")
SPLITS = (
    "train",
    "validation",
    "test",
    "holdout",
    "out_of_time",
    "cross_validation",
    "custom",
)
COMPARISON_MODES = ("absolute", "relative_to_baseline", "absolute_diff_from_baseline")
UNCERTAINTY_KINDS = ("standard_error", "confidence_interval")
# Mismos literales de texto que `dsguard.checks.STATUS_FAIL`/`STATUS_WARN` y que
# `tools/datacontracts/core.py:76` -- NO se importa ninguno de los dos módulos
# (coincidencia de vocabulario documentada, no dependencia de código; ver
# docstring del módulo y `design.md`, decisión 1).
SEVERITIES = ("FAIL", "WARN")


class ModelQualityError(ValueError):
    """Violación de una política de calidad de modelo (entrada estructuralmente
    inválida)."""


# ---------------------------------------------------------------------------
# Helpers privados de validación / normalización
# ---------------------------------------------------------------------------

# Ids (`policy_id`/`requirement_id`/`context_id`/`baseline_id`): seguros como
# nombre de archivo (`^[a-z0-9][a-z0-9_-]{0,63}$`, aplicado con `fullmatch`).
# Reimplementado localmente (NO importado de `tools.datacontracts.core`): ver
# `design.md`, decisión 1 (familias independientes sin helpers compartidos).
_PATRON_ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")

# Nombres de dispositivo reservados en Windows: un id (ya en minúscula) que
# coincida no es seguro como nombre de archivo en ese sistema.
_IDS_RESERVADOS = frozenset(
    ["con", "prn", "aux", "nul"]
    + [f"com{i}" for i in range(1, 10)]
    + [f"lpt{i}" for i in range(1, 10)]
)

# `metric_name`: snake_case estricto (`^[a-z][a-z0-9_]*$`), mismo patrón que
# `ContractField.name` de Change 0, reimplementado localmente (ídem).
_PATRON_METRIC_NAME = re.compile(r"[a-z][a-z0-9_]*")


def _validar_id(valor: Any, campo: str) -> str:
    """Valida un id (`policy_id`/`requirement_id`/`context_id`/`baseline_id`)
    contra `_PATRON_ID` y los nombres reservados de Windows."""
    if not isinstance(valor, str):
        raise ModelQualityError(f"{campo}: se esperaba str, se recibió {type(valor).__name__}")
    if _PATRON_ID.fullmatch(valor) is None:
        raise ModelQualityError(
            f"{campo}: id inválido {valor!r} (debe cumplir ^[a-z0-9][a-z0-9_-]{{0,63}}$)"
        )
    if valor in _IDS_RESERVADOS:
        raise ModelQualityError(
            f"{campo}: id {valor!r} es un nombre de dispositivo reservado de Windows "
            "(no es seguro como nombre de archivo)"
        )
    return valor


def _validar_metric_name(valor: Any, campo: str) -> str:
    """Valida `metric_name` contra `_PATRON_METRIC_NAME` (`^[a-z][a-z0-9_]*$`)."""
    if not isinstance(valor, str):
        raise ModelQualityError(f"{campo}: se esperaba str, se recibió {type(valor).__name__}")
    if _PATRON_METRIC_NAME.fullmatch(valor) is None:
        raise ModelQualityError(
            f"{campo}: metric_name inválido {valor!r} (debe cumplir ^[a-z][a-z0-9_]*$)"
        )
    return valor


def _exigir_str(valor: Any, campo: str) -> str:
    if not isinstance(valor, str):
        raise ModelQualityError(f"{campo}: se esperaba str, se recibió {type(valor).__name__}")
    return valor


def _exigir_str_no_vacio(valor: Any, campo: str) -> str:
    _exigir_str(valor, campo)
    if valor == "":
        raise ModelQualityError(f"{campo}: no puede ser vacío")
    return valor


def _exigir_bool(valor: Any, campo: str) -> bool:
    if not isinstance(valor, bool):
        raise ModelQualityError(f"{campo}: se esperaba bool, se recibió {type(valor).__name__}")
    return valor


def _exigir_dict(valor: Any, campo: str) -> dict:
    if not isinstance(valor, dict):
        raise ModelQualityError(f"{campo}: se esperaba dict, se recibió {type(valor).__name__}")
    return valor


def _es_finito(valor: float) -> bool:
    """`True` sii `valor` (ya sabido `int`/`float`) es finito -- sin importar
    `math`, mismo criterio que `tools/datacontracts/core.py`."""
    return valor == valor and valor not in (float("inf"), float("-inf"))


def _exigir_numero_finito(valor: Any, campo: str) -> Any:
    """Exige `int` o `float` finito, nunca `bool`; devuelve el mismo valor
    (sin forzar conversión de tipo)."""
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        raise ModelQualityError(
            f"{campo}: se esperaba int o float (no bool), se recibió {valor!r}"
        )
    if isinstance(valor, float) and not _es_finito(valor):
        raise ModelQualityError(f"{campo}: float no finito ({valor!r})")
    return valor


def _json_puro(valor: Any, ruta: str) -> Any:
    """Copia profunda de `valor` normalizada a estructura JSON pura: `tuple`
    -> `list`, claves `str`, `float` finito. Cualquier otro tipo es error."""
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
            raise ModelQualityError(f"{ruta}: float no finito ({valor!r}) no es JSON-seguro")
        return float(valor)
    if isinstance(valor, (list, tuple)):
        return [_json_puro(item, f"{ruta}[{i}]") for i, item in enumerate(valor)]
    if isinstance(valor, dict):
        resultado: dict = {}
        for clave, item in valor.items():
            if not isinstance(clave, str):
                raise ModelQualityError(
                    f"{ruta}: clave no-str {clave!r} ({type(clave).__name__}) no es JSON-seguro"
                )
            resultado[clave] = _json_puro(item, f"{ruta}.{clave}")
        return resultado
    raise ModelQualityError(f"{ruta}: tipo {type(valor).__name__} no es JSON-seguro")


def _dict_json_puro(valor: Any, campo: str) -> dict:
    """Exige `dict` y devuelve su copia profunda normalizada a JSON puro; una
    estructura circular o demasiado profunda es `ModelQualityError`."""
    try:
        return _json_puro(_exigir_dict(valor, campo), campo)
    except RecursionError as exc:
        raise ModelQualityError(f"{campo}: estructura circular o demasiado profunda") from exc


def _validar_extensiones(valor: Any, campo: str) -> dict:
    """Copia JSON-segura de un mapa `extensions`: todas las claves de primer
    nivel deben empezar con `EXTENSION_PREFIX`."""
    datos = _dict_json_puro(valor, campo)
    for clave in datos:
        if not clave.startswith(EXTENSION_PREFIX):
            raise ModelQualityError(
                f"{campo}: clave {clave!r} no empieza con el prefijo requerido {EXTENSION_PREFIX!r}"
            )
    return datos


def _validar_uncertainty(valor: Any, campo: str) -> dict:
    """Valida la FORMA de `uncertainty` (R7): nunca su adecuación
    metodológica. `valor` ya debe ser no-`None` al invocar esta función."""
    datos = _dict_json_puro(valor, campo)
    kind = datos.get("kind")
    if kind not in UNCERTAINTY_KINDS:
        raise ModelQualityError(f"{campo}: 'kind' {kind!r} fuera de {UNCERTAINTY_KINDS}")
    if kind == "standard_error":
        valor_se = datos.get("value")
        if (
            isinstance(valor_se, bool)
            or not isinstance(valor_se, (int, float))
            or not _es_finito(float(valor_se))
            or valor_se < 0
        ):
            raise ModelQualityError(
                f"{campo}: 'value' de standard_error debe ser int/float finito >= 0, se "
                f"recibió {valor_se!r}"
            )
        return datos
    # kind == "confidence_interval"
    lower = datos.get("lower")
    upper = datos.get("upper")
    nivel = datos.get("confidence_level")
    for nombre, dato in (("lower", lower), ("upper", upper)):
        if isinstance(dato, bool) or not isinstance(dato, (int, float)) or not _es_finito(float(dato)):
            raise ModelQualityError(
                f"{campo}: '{nombre}' de confidence_interval debe ser int/float finito, se "
                f"recibió {dato!r}"
            )
    if lower > upper:
        raise ModelQualityError(
            f"{campo}: 'lower' ({lower!r}) no puede ser mayor que 'upper' ({upper!r})"
        )
    if isinstance(nivel, bool) or not isinstance(nivel, (int, float)) or not (0 < nivel < 1):
        raise ModelQualityError(
            f"{campo}: 'confidence_level' debe ser float en (0, 1), se recibió {nivel!r}"
        )
    return datos


def _requeridos(datos: Any, nombres: tuple, tipo: str) -> None:
    if not isinstance(datos, dict):
        raise ModelQualityError(f"{tipo}.from_dict: se esperaba dict, se recibió {type(datos).__name__}")
    faltantes = [n for n in nombres if n not in datos]
    if faltantes:
        raise ModelQualityError(f"{tipo}.from_dict: faltan campos requeridos {faltantes}")


def _seleccionar(datos: dict, nombres: tuple) -> dict:
    return {n: datos[n] for n in nombres if n in datos}


def canonical_json(obj: Any) -> str:
    """JSON canónico: claves ordenadas, sin espacios, sin escapar no-ASCII,
    sin `NaN`/`Infinity`. Un fallo de serialización lanza `ModelQualityError`."""
    try:
        return json.dumps(
            obj,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError, RecursionError) as exc:
        raise ModelQualityError(f"canonical_json: objeto no serializable ({exc})") from exc


# ---------------------------------------------------------------------------
# EvaluationContext
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EvaluationContext:
    """Contexto de evaluación de una métrica: split y, opcionalmente,
    población/segmento. Reutilizado tal cual por `MetricRequirement`,
    `ObservedMetric` y `BaselineReference` para comparación estructural
    directa."""

    context_id: str
    split: str
    population: str = ""
    description: str = ""
    extensions: dict = _campo_dataclass(default_factory=dict)

    def __post_init__(self) -> None:
        _validar_id(self.context_id, "EvaluationContext.context_id")
        if self.split not in SPLITS:
            raise ModelQualityError(f"EvaluationContext.split: {self.split!r} fuera de {SPLITS}")
        _exigir_str(self.population, "EvaluationContext.population")
        _exigir_str(self.description, "EvaluationContext.description")
        extensiones = _validar_extensiones(self.extensions, "EvaluationContext.extensions")
        object.__setattr__(self, "extensions", extensiones)

    def to_dict(self) -> dict:
        return {
            "context_id": self.context_id,
            "split": self.split,
            "population": self.population,
            "description": self.description,
            "extensions": _json_puro(self.extensions, "EvaluationContext.extensions"),
        }

    @classmethod
    def from_dict(cls, datos: dict) -> "EvaluationContext":
        _requeridos(datos, ("context_id", "split"), "EvaluationContext")
        return cls(
            **_seleccionar(
                datos, ("context_id", "split", "population", "description", "extensions")
            )
        )


# ---------------------------------------------------------------------------
# MetricRequirement
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MetricRequirement:
    """Un requisito mínimo de calidad sobre una métrica: threshold y/o
    exigencia de baseline, con severidades propias por etapa. Nunca observa ni
    calcula ningún valor -- eso es `ObservedMetric`/`BaselineReference`."""

    requirement_id: str
    metric_name: str
    direction: str
    required_context: "EvaluationContext"
    threshold_value: Optional[float] = None
    threshold_severity: str = "FAIL"
    baseline_required: bool = False
    comparison_mode: str = "absolute"
    comparison_tolerance: Optional[float] = None
    baseline_severity: str = "FAIL"
    min_sample_size: Optional[int] = None
    uncertainty_required: bool = False
    description: str = ""
    extensions: dict = _campo_dataclass(default_factory=dict)

    def __post_init__(self) -> None:
        _validar_id(self.requirement_id, "MetricRequirement.requirement_id")
        _validar_metric_name(self.metric_name, "MetricRequirement.metric_name")
        if self.direction not in DIRECTIONS:
            raise ModelQualityError(
                f"MetricRequirement.direction: {self.direction!r} fuera de {DIRECTIONS}"
            )
        if not isinstance(self.required_context, EvaluationContext):
            raise ModelQualityError(
                "MetricRequirement.required_context: se esperaba EvaluationContext, se recibió "
                f"{type(self.required_context).__name__}"
            )
        if self.threshold_value is not None:
            _exigir_numero_finito(self.threshold_value, "MetricRequirement.threshold_value")
        if self.threshold_severity not in SEVERITIES:
            raise ModelQualityError(
                f"MetricRequirement.threshold_severity: {self.threshold_severity!r} fuera de "
                f"{SEVERITIES}"
            )
        _exigir_bool(self.baseline_required, "MetricRequirement.baseline_required")
        if self.comparison_mode not in COMPARISON_MODES:
            raise ModelQualityError(
                f"MetricRequirement.comparison_mode: {self.comparison_mode!r} fuera de "
                f"{COMPARISON_MODES}"
            )
        if self.comparison_tolerance is not None:
            tolerancia = _exigir_numero_finito(
                self.comparison_tolerance, "MetricRequirement.comparison_tolerance"
            )
            if tolerancia < 0:
                raise ModelQualityError(
                    "MetricRequirement.comparison_tolerance: debe ser >= 0, se recibió "
                    f"{tolerancia!r}"
                )
        if self.baseline_severity not in SEVERITIES:
            raise ModelQualityError(
                f"MetricRequirement.baseline_severity: {self.baseline_severity!r} fuera de "
                f"{SEVERITIES}"
            )
        if self.min_sample_size is not None:
            if isinstance(self.min_sample_size, bool) or not isinstance(self.min_sample_size, int):
                raise ModelQualityError(
                    "MetricRequirement.min_sample_size: se esperaba int (no bool), se recibió "
                    f"{self.min_sample_size!r}"
                )
            if self.min_sample_size < 1:
                raise ModelQualityError(
                    f"MetricRequirement.min_sample_size: debe ser >= 1, se recibió "
                    f"{self.min_sample_size!r}"
                )
        _exigir_bool(self.uncertainty_required, "MetricRequirement.uncertainty_required")
        _exigir_str(self.description, "MetricRequirement.description")
        extensiones = _validar_extensiones(self.extensions, "MetricRequirement.extensions")
        object.__setattr__(self, "extensions", extensiones)

        # Regla de coherencia mínima (R5): al menos threshold o baseline.
        if self.threshold_value is None and not self.baseline_required:
            raise ModelQualityError(
                "MetricRequirement: debe declarar threshold_value y/o baseline_required=True "
                "(un requirement sin ninguno de los dos no exige nada verificable)"
            )

    def to_dict(self) -> dict:
        return {
            "requirement_id": self.requirement_id,
            "metric_name": self.metric_name,
            "direction": self.direction,
            "threshold_value": self.threshold_value,
            "threshold_severity": self.threshold_severity,
            "required_context": self.required_context.to_dict(),
            "baseline_required": self.baseline_required,
            "comparison_mode": self.comparison_mode,
            "comparison_tolerance": self.comparison_tolerance,
            "baseline_severity": self.baseline_severity,
            "min_sample_size": self.min_sample_size,
            "uncertainty_required": self.uncertainty_required,
            "description": self.description,
            "extensions": _json_puro(self.extensions, "MetricRequirement.extensions"),
        }

    @classmethod
    def from_dict(cls, datos: dict) -> "MetricRequirement":
        _requeridos(
            datos, ("requirement_id", "metric_name", "direction", "required_context"), "MetricRequirement"
        )
        kwargs = _seleccionar(
            datos,
            (
                "requirement_id",
                "metric_name",
                "direction",
                "threshold_value",
                "threshold_severity",
                "baseline_required",
                "comparison_mode",
                "comparison_tolerance",
                "baseline_severity",
                "min_sample_size",
                "uncertainty_required",
                "description",
                "extensions",
            ),
        )
        kwargs["required_context"] = EvaluationContext.from_dict(datos["required_context"])
        return cls(**kwargs)


# ---------------------------------------------------------------------------
# ObservedMetric
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ObservedMetric:
    """Un valor de métrica YA reportado por el proyecto, con procedencia
    genérica (`evidence_ref`) y metadata opcional de muestra/incertidumbre.
    Este módulo no calcula `value`, solo lo recibe y valida su forma."""

    metric_name: str
    value: float
    context: "EvaluationContext"
    evidence_ref: Optional[str] = None
    sample_size: Optional[int] = None
    uncertainty: Optional[dict] = None
    description: str = ""
    extensions: dict = _campo_dataclass(default_factory=dict)

    def __post_init__(self) -> None:
        _validar_metric_name(self.metric_name, "ObservedMetric.metric_name")
        _exigir_numero_finito(self.value, "ObservedMetric.value")
        if not isinstance(self.context, EvaluationContext):
            raise ModelQualityError(
                f"ObservedMetric.context: se esperaba EvaluationContext, se recibió "
                f"{type(self.context).__name__}"
            )
        if self.evidence_ref is not None:
            _exigir_str_no_vacio(self.evidence_ref, "ObservedMetric.evidence_ref")
        if self.sample_size is not None:
            if isinstance(self.sample_size, bool) or not isinstance(self.sample_size, int):
                raise ModelQualityError(
                    "ObservedMetric.sample_size: se esperaba int (no bool), se recibió "
                    f"{self.sample_size!r}"
                )
            if self.sample_size < 1:
                raise ModelQualityError(
                    f"ObservedMetric.sample_size: debe ser >= 1, se recibió {self.sample_size!r}"
                )
        if self.uncertainty is not None:
            incertidumbre = _validar_uncertainty(self.uncertainty, "ObservedMetric.uncertainty")
            object.__setattr__(self, "uncertainty", incertidumbre)
        _exigir_str(self.description, "ObservedMetric.description")
        extensiones = _validar_extensiones(self.extensions, "ObservedMetric.extensions")
        object.__setattr__(self, "extensions", extensiones)

    def to_dict(self) -> dict:
        return {
            "metric_name": self.metric_name,
            "value": self.value,
            "context": self.context.to_dict(),
            "evidence_ref": self.evidence_ref,
            "sample_size": self.sample_size,
            "uncertainty": (
                None if self.uncertainty is None else _json_puro(self.uncertainty, "ObservedMetric.uncertainty")
            ),
            "description": self.description,
            "extensions": _json_puro(self.extensions, "ObservedMetric.extensions"),
        }

    @classmethod
    def from_dict(cls, datos: dict) -> "ObservedMetric":
        _requeridos(datos, ("metric_name", "value", "context"), "ObservedMetric")
        kwargs = _seleccionar(
            datos,
            (
                "metric_name",
                "value",
                "evidence_ref",
                "sample_size",
                "uncertainty",
                "description",
                "extensions",
            ),
        )
        kwargs["context"] = EvaluationContext.from_dict(datos["context"])
        return cls(**kwargs)


# ---------------------------------------------------------------------------
# BaselineReference
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BaselineReference:
    """Un valor de referencia externo (baseline) contra el que se compara un
    `ObservedMetric`, con procedencia declarada (`source`) obligatoria."""

    baseline_id: str
    metric_name: str
    value: float
    context: "EvaluationContext"
    source: str
    evidence_ref: Optional[str] = None
    description: str = ""
    extensions: dict = _campo_dataclass(default_factory=dict)

    def __post_init__(self) -> None:
        _validar_id(self.baseline_id, "BaselineReference.baseline_id")
        _validar_metric_name(self.metric_name, "BaselineReference.metric_name")
        _exigir_numero_finito(self.value, "BaselineReference.value")
        if not isinstance(self.context, EvaluationContext):
            raise ModelQualityError(
                f"BaselineReference.context: se esperaba EvaluationContext, se recibió "
                f"{type(self.context).__name__}"
            )
        _exigir_str_no_vacio(self.source, "BaselineReference.source")
        if self.evidence_ref is not None:
            _exigir_str_no_vacio(self.evidence_ref, "BaselineReference.evidence_ref")
        _exigir_str(self.description, "BaselineReference.description")
        extensiones = _validar_extensiones(self.extensions, "BaselineReference.extensions")
        object.__setattr__(self, "extensions", extensiones)

    def to_dict(self) -> dict:
        return {
            "baseline_id": self.baseline_id,
            "metric_name": self.metric_name,
            "value": self.value,
            "context": self.context.to_dict(),
            "source": self.source,
            "evidence_ref": self.evidence_ref,
            "description": self.description,
            "extensions": _json_puro(self.extensions, "BaselineReference.extensions"),
        }

    @classmethod
    def from_dict(cls, datos: dict) -> "BaselineReference":
        _requeridos(datos, ("baseline_id", "metric_name", "value", "context", "source"), "BaselineReference")
        kwargs = _seleccionar(
            datos,
            ("baseline_id", "metric_name", "value", "source", "evidence_ref", "description", "extensions"),
        )
        kwargs["context"] = EvaluationContext.from_dict(datos["context"])
        return cls(**kwargs)


# ---------------------------------------------------------------------------
# ModelQualityPolicy (raíz)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ModelQualityPolicy:
    """Raíz del árbol: declara qué requisitos mínimos (`requirements`) exige
    un modelo de un `model_task_role` dado. No observa ni evalúa ningún dato;
    la evaluación contra evidencia real es responsabilidad de
    `tools/modelquality/validation.py`."""

    policy_id: str
    model_task_role: str
    requirements: tuple
    description: str = ""
    extensions: dict = _campo_dataclass(default_factory=dict)
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _validar_id(self.policy_id, "ModelQualityPolicy.policy_id")
        if self.model_task_role not in MODEL_TASK_ROLES:
            raise ModelQualityError(
                f"ModelQualityPolicy.model_task_role: {self.model_task_role!r} fuera de "
                f"{MODEL_TASK_ROLES}"
            )
        if not isinstance(self.requirements, (list, tuple)):
            raise ModelQualityError(
                "ModelQualityPolicy.requirements: se esperaba list o tuple, se recibió "
                f"{type(self.requirements).__name__}"
            )
        requisitos = tuple(self.requirements)
        if not requisitos:
            raise ModelQualityError("ModelQualityPolicy.requirements: no puede ser vacía")
        for i, requisito in enumerate(requisitos):
            if not isinstance(requisito, MetricRequirement):
                raise ModelQualityError(
                    f"ModelQualityPolicy.requirements[{i}]: se esperaba MetricRequirement, se "
                    f"recibió {type(requisito).__name__}"
                )
        ids_vistos: set = set()
        for requisito in requisitos:
            if requisito.requirement_id in ids_vistos:
                raise ModelQualityError(
                    f"ModelQualityPolicy.requirements: requirement_id duplicado "
                    f"{requisito.requirement_id!r}"
                )
            ids_vistos.add(requisito.requirement_id)

        _exigir_str(self.description, "ModelQualityPolicy.description")
        extensiones = _validar_extensiones(self.extensions, "ModelQualityPolicy.extensions")

        if (
            isinstance(self.schema_version, bool)
            or not isinstance(self.schema_version, int)
            or self.schema_version != SCHEMA_VERSION
        ):
            raise ModelQualityError(
                f"ModelQualityPolicy.schema_version: se esperaba {SCHEMA_VERSION}, se recibió "
                f"{self.schema_version!r}"
            )

        object.__setattr__(self, "requirements", requisitos)
        object.__setattr__(self, "extensions", extensiones)

    # -- accesores (nunca lanzan) --------------------------------------------

    def get_requirement(self, requirement_id: Any) -> Optional[MetricRequirement]:
        for requisito in self.requirements:
            if requisito.requirement_id == requirement_id:
                return requisito
        return None

    def requirements_for(self, metric_name: Any) -> tuple:
        """Requirements con ese `metric_name` (en cualquier contexto): un
        `metric_name` puede repetirse entre requirements con
        `required_context` distinto (R5/R9)."""
        return tuple(r for r in self.requirements if r.metric_name == metric_name)

    # -- serialización --------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "policy_id": self.policy_id,
            "model_task_role": self.model_task_role,
            "requirements": [requisito.to_dict() for requisito in self.requirements],
            "description": self.description,
            "extensions": _json_puro(self.extensions, "ModelQualityPolicy.extensions"),
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, datos: dict) -> "ModelQualityPolicy":
        _requeridos(
            datos, ("policy_id", "model_task_role", "requirements", "schema_version"), "ModelQualityPolicy"
        )
        kwargs = _seleccionar(
            datos, ("policy_id", "model_task_role", "description", "extensions", "schema_version")
        )
        if not isinstance(datos["requirements"], (list, tuple)):
            raise ModelQualityError(
                "ModelQualityPolicy.from_dict.requirements: se esperaba list o tuple, se recibió "
                f"{type(datos['requirements']).__name__}"
            )
        kwargs["requirements"] = tuple(
            MetricRequirement.from_dict(item) for item in datos["requirements"]
        )
        return cls(**kwargs)

    def content_sha256(self) -> str:
        """sha256 (hex) del JSON canónico de `to_dict()` en UTF-8."""
        return hashlib.sha256(canonical_json(self.to_dict()).encode("utf-8")).hexdigest()

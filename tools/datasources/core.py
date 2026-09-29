"""Tipos neutrales de fuentes de datos (v0.8 Change 1,
`20260928-source-neutral-data-access`).

Módulo solo-stdlib (`dataclasses`, `typing`, `re`, `json`, `hashlib`,
`unicodedata`, `__future__`): sin `os`, `pathlib`, `sys`, `importlib`, sin
imports de módulos hermanos (`scan`, `registry`, `runtime`, ...) ni de
`tools.*`. Declara:

- `SourceRef`: entrada del registro `.harmessi/sources.json` (identidad
  lógica, no física; ver `design.md` D2).
- `SourceCapabilities`: lo que un observer declara poder observar (dos ejes:
  `facets` con exactitud y `operations` informativas). `execute_query` NO
  existe en el vocabulario (D4).
- `ObservationRequest`: pedido acotado, sin texto de consulta.
- `SourceObservation`/`FieldObservation`/`SourceProvenance`: evidencia
  observada, serialización determinista.
- `SourceError`: única excepción de este paquete para construcción/validación.
- `CODES`: registro único de códigos `SOURCE-*` (R9); ningún otro módulo de
  este paquete declara códigos nuevos.

Este módulo NO ramifica sobre `source_kind` ni sobre ninguna tecnología (R3):
`source_kind` es una etiqueta informativa acotada por `SOURCE_KIND_PATTERN`
que solo se copia y serializa.

Determinismo (R7): `to_dict()` construye el dict en orden fijo explícito
(nunca por comprensión desordenada); `canonical_json()` usa
`json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=False)`;
`SourceObservation.content_sha256()` es el sha256 hex de la forma canónica de
`to_dict()` **con `provenance.generated_at` excluido** (se calcula sobre una
copia que borra esa única clave antes de canonicalizar), de modo que dos
observaciones que difieren solo en `generated_at` comparten hash.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field as _campo_dataclass
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Vocabularios y patrones
# ---------------------------------------------------------------------------

SCHEMA_VERSION = 1

# Prefijo de claves de extensión controladas (mismo patrón que
# `tools/datacontracts/core.py:56` / `tools/reporting/profiles/eda.py:43`).
EXTENSION_PREFIX = "x_"

# Formato estable de `source_id`: DUPLICADO EXACTO de
# `tools/autonomy/core.py:332` (paquetes independientes a propósito, ver
# `design.md` D2; `tools/tests/test_v08_source_id_parity.py` afirma la
# igualdad de este literal).
SOURCE_ID_PATTERN = r"[a-z0-9][a-z0-9_-]{0,63}"

# `role`: mismo patrón que `source_id` (p. ej. `raw_table`, `feature_table`).
ROLE_PATTERN = r"[a-z0-9][a-z0-9_-]{0,63}"

# `observer`: `módulo:callable`.
OBSERVER_PATTERN = r"^[A-Za-z_][A-Za-z0-9_.]*:[A-Za-z_][A-Za-z0-9_]*$"

# `config_ref`: `env:NOMBRE` o `ref:NOMBRE`.
CONFIG_REF_PATTERN = r"^(env|ref):[A-Za-z_][A-Za-z0-9_]{0,63}$"

# `source_kind`: etiqueta informativa acotada (R3); el core no ramifica sobre
# su valor, solo lo copia/serializa.
SOURCE_KIND_PATTERN = r"^[a-z0-9][a-z0-9_-]{0,31}$"

_RE_SOURCE_ID = re.compile(SOURCE_ID_PATTERN)
_RE_ROLE = re.compile(ROLE_PATTERN)
_RE_OBSERVER = re.compile(OBSERVER_PATTERN)
_RE_CONFIG_REF = re.compile(CONFIG_REF_PATTERN)
_RE_SOURCE_KIND = re.compile(SOURCE_KIND_PATTERN)

# ISO-8601 laxo (fecha o fecha+hora), sin usar `datetime` (core.py es
# solo-stdlib restringido a la lista del docstring del módulo).
_RE_ISO8601 = re.compile(
    r"^\d{4}-\d{2}-\d{2}"
    r"(T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})?)?$"
)

ACCESS_MODES = ("read",)
RESERVED_ACCESS_MODES = ("write",)
ACCESS_CEILING = "read"

SENSITIVITIES = ("public", "internal", "sensitive")

DATASET_FACETS = ("schema", "row_count", "fingerprint", "snapshot")
FIELD_FACETS = ("null_count", "distinct_count", "value_distribution", "value_range", "time_range")
EXACTNESS_VALUES = ("exact", "approximate")
OPERATIONS = ("sample", "read", "write")

OBSERVED_TYPE_FAMILIES = (
    "string",
    "integer",
    "float",
    "boolean",
    "date",
    "datetime",
    "temporal",
    "unknown",
)

_OBSERVATION_REQUEST_CLAVES = ("source_id", "facets", "exactness", "as_of", "max_rows", "sample_size")
_SOURCE_REF_CLAVES = ("source_id", "role", "observer", "access_mode", "sensitivity", "config_ref", "options", "extra")
_DATASET_CLAVES = ("row_count", "fingerprint", "snapshot", "sampling")

_OPTIONS_PROFUNDIDAD_MAXIMA = 4
_OPTIONS_CLAVES_MAXIMAS = 64
_OPTIONS_STRING_MAXIMO = 512

# ---------------------------------------------------------------------------
# Registro único de códigos SOURCE-* (R9)
# ---------------------------------------------------------------------------

CODE_REGISTRY_MISSING = "SOURCE-REGISTRY-MISSING"
CODE_REGISTRY_INVALID = "SOURCE-REGISTRY-INVALID"
CODE_ID_INVALID = "SOURCE-ID-INVALID"
CODE_ID_DUPLICATE = "SOURCE-ID-DUPLICATE"
CODE_ROLE_INVALID = "SOURCE-ROLE-INVALID"
CODE_OBSERVER_MALFORMED = "SOURCE-OBSERVER-MALFORMED"
CODE_OBSERVER_UNRESOLVED = "SOURCE-OBSERVER-UNRESOLVED"
CODE_ACCESS_MODE_RESERVED = "SOURCE-ACCESS-MODE-RESERVED"
CODE_SENSITIVITY_INVALID = "SOURCE-SENSITIVITY-INVALID"
CODE_CONFIG_REF_INVALID = "SOURCE-CONFIG-REF-INVALID"
CODE_OPTIONS_INVALID = "SOURCE-OPTIONS-INVALID"
CODE_SECRET_DETECTED = "SOURCE-SECRET-DETECTED"
CODE_ABSOLUTE_PATH = "SOURCE-ABSOLUTE-PATH"
CODE_DSN_DETECTED = "SOURCE-DSN-DETECTED"
CODE_UNKNOWN = "SOURCE-UNKNOWN"
CODE_ACCESS_DENIED = "SOURCE-ACCESS-DENIED"
CODE_SEALED = "SOURCE-SEALED"
CODE_OBSERVER_ERROR = "SOURCE-OBSERVER-ERROR"
CODE_CAPABILITIES_INVALID = "SOURCE-CAPABILITIES-INVALID"
CODE_FACET_UNSUPPORTED = "SOURCE-FACET-UNSUPPORTED"
CODE_OBSERVATION_INVALID = "SOURCE-OBSERVATION-INVALID"
CODE_FACET_OMITTED = "SOURCE-FACET-OMITTED"
CODE_OBSERVER_CODE_UNHASHABLE = "SOURCE-OBSERVER-CODE-UNHASHABLE"
CODE_PERSIST_ERROR = "SOURCE-PERSIST-ERROR"
CODE_OBSERVATION_STALE = "SOURCE-OBSERVATION-STALE"
CODE_FRESHNESS_UNVERIFIABLE = "SOURCE-FRESHNESS-UNVERIFIABLE"
CODE_PROFILE_INVALID = "SOURCE-PROFILE-INVALID"

CODES = (
    CODE_REGISTRY_MISSING,
    CODE_REGISTRY_INVALID,
    CODE_ID_INVALID,
    CODE_ID_DUPLICATE,
    CODE_ROLE_INVALID,
    CODE_OBSERVER_MALFORMED,
    CODE_OBSERVER_UNRESOLVED,
    CODE_ACCESS_MODE_RESERVED,
    CODE_SENSITIVITY_INVALID,
    CODE_CONFIG_REF_INVALID,
    CODE_OPTIONS_INVALID,
    CODE_SECRET_DETECTED,
    CODE_ABSOLUTE_PATH,
    CODE_DSN_DETECTED,
    CODE_UNKNOWN,
    CODE_ACCESS_DENIED,
    CODE_SEALED,
    CODE_OBSERVER_ERROR,
    CODE_CAPABILITIES_INVALID,
    CODE_FACET_UNSUPPORTED,
    CODE_OBSERVATION_INVALID,
    CODE_FACET_OMITTED,
    CODE_OBSERVER_CODE_UNHASHABLE,
    CODE_PERSIST_ERROR,
    CODE_OBSERVATION_STALE,
    CODE_FRESHNESS_UNVERIFIABLE,
    CODE_PROFILE_INVALID,
)


class SourceError(Exception):
    """Única excepción de `datasources.core`/`scan`/`registry` para
    construcción/validación de tipos. `code` es uno de `CODES`."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


# ---------------------------------------------------------------------------
# Helpers privados de validación / normalización JSON
# ---------------------------------------------------------------------------


def _es_finito(valor: float) -> bool:
    return valor == valor and valor not in (float("inf"), float("-inf"))


def _exigir_str(valor: Any, campo: str, code: str) -> str:
    if not isinstance(valor, str):
        raise SourceError(code, f"{campo}: se esperaba str, se recibió {type(valor).__name__}")
    return valor


def _exigir_dict(valor: Any, campo: str, code: str) -> dict:
    if not isinstance(valor, dict):
        raise SourceError(code, f"{campo}: se esperaba dict, se recibió {type(valor).__name__}")
    return valor


def _json_puro(valor: Any, ruta: str, code: str) -> Any:
    """Copia profunda normalizada a JSON puro: `tuple`/`frozenset` -> `list`
    (frozenset ordenado), claves `str`, `float` finito. Tipo no soportado o
    clave no-str -> `SourceError(code, ...)`."""
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
            raise SourceError(code, f"{ruta}: float no finito ({valor!r}) no es JSON-seguro")
        return float(valor)
    if isinstance(valor, (list, tuple)):
        return [_json_puro(item, f"{ruta}[{i}]", code) for i, item in enumerate(valor)]
    if isinstance(valor, frozenset):
        return sorted(_json_puro(item, f"{ruta}{{}}", code) for item in valor)
    if isinstance(valor, dict):
        resultado: dict = {}
        for clave, item in valor.items():
            if not isinstance(clave, str):
                raise SourceError(code, f"{ruta}: clave no-str {clave!r} no es JSON-segura")
            resultado[clave] = _json_puro(item, f"{ruta}.{clave}", code)
        return resultado
    raise SourceError(code, f"{ruta}: tipo {type(valor).__name__} no es JSON-seguro")


def _contar_claves_y_profundidad(valor: Any, profundidad: int = 0) -> tuple:
    """Devuelve `(total_claves, profundidad_maxima)` de un árbol JSON puro
    (dict/list/escalar), contando TODAS las claves del árbol (R4 `options`)."""
    if isinstance(valor, dict):
        total = len(valor)
        prof_max = profundidad
        for item in valor.values():
            sub_total, sub_prof = _contar_claves_y_profundidad(item, profundidad + 1)
            total += sub_total
            prof_max = max(prof_max, sub_prof)
        return total, prof_max
    if isinstance(valor, list):
        total = 0
        prof_max = profundidad
        for item in valor:
            sub_total, sub_prof = _contar_claves_y_profundidad(item, profundidad)
            total += sub_total
            prof_max = max(prof_max, sub_prof)
        return total, prof_max
    return 0, profundidad


def _validar_strings_acotados(valor: Any, ruta: str, code: str) -> None:
    if isinstance(valor, str) and len(valor) > _OPTIONS_STRING_MAXIMO:
        raise SourceError(code, f"{ruta}: string de {len(valor)} caracteres excede el máximo permitido")
    if isinstance(valor, dict):
        for clave, item in valor.items():
            _validar_strings_acotados(item, f"{ruta}.{clave}", code)
    elif isinstance(valor, list):
        for i, item in enumerate(valor):
            _validar_strings_acotados(item, f"{ruta}[{i}]", code)


def _validar_options(valor: Any, campo: str, code: str = CODE_OPTIONS_INVALID) -> dict:
    """Valida y normaliza `options`/`extra`: `dict` JSON puro, profundidad
    máxima 4, máximo 64 claves totales (recursivo), strings de hasta 512
    caracteres, sin `NaN`/`Infinity` (aplicado por `_json_puro`)."""
    datos = _exigir_dict(valor, campo, code)
    normalizado = _json_puro(datos, campo, code)
    total_claves, profundidad_max = _contar_claves_y_profundidad(normalizado)
    if profundidad_max > _OPTIONS_PROFUNDIDAD_MAXIMA:
        raise SourceError(
            code, f"{campo}: profundidad {profundidad_max} excede el máximo {_OPTIONS_PROFUNDIDAD_MAXIMA}"
        )
    if total_claves > _OPTIONS_CLAVES_MAXIMAS:
        raise SourceError(
            code, f"{campo}: {total_claves} claves totales excede el máximo {_OPTIONS_CLAVES_MAXIMAS}"
        )
    _validar_strings_acotados(normalizado, campo, code)
    return normalizado


def _validar_extra(valor: Any, campo: str) -> dict:
    datos = _validar_options(valor, campo, CODE_OPTIONS_INVALID)
    for clave in datos:
        if not clave.startswith(EXTENSION_PREFIX):
            raise SourceError(
                CODE_OPTIONS_INVALID,
                f"{campo}: clave {clave!r} no empieza con el prefijo requerido {EXTENSION_PREFIX!r}",
            )
    return datos


def canonical_json(obj: Any) -> str:
    """JSON canónico: claves ordenadas, sin espacios, sin escapar no-ASCII,
    sin `NaN`/`Infinity`."""
    try:
        return json.dumps(
            obj,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError, RecursionError) as exc:
        raise SourceError(CODE_REGISTRY_INVALID, f"canonical_json: objeto no serializable ({exc})") from exc


def content_sha256(obj: Any) -> str:
    """sha256 hex del JSON canónico (UTF-8) de `obj`."""
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# SourceRef (R4)
# ---------------------------------------------------------------------------


def validate_source_ref(d: Any) -> list:
    """Validación estructural PURA (no lanza) de un dict candidato a
    `SourceRef`: devuelve `[(code, path, motivo), ...]`. Usada por
    `registry.validate_registry` para acumular hallazgos de todas las
    entradas sin detenerse en la primera. Implementa la semántica especial de
    `access_mode` (R4): `"write"` -> `SOURCE-ACCESS-MODE-RESERVED`; cualquier
    otro valor no-`"read"` -> `SOURCE-REGISTRY-INVALID`."""
    hallazgos: list = []
    if not isinstance(d, dict):
        return [(CODE_REGISTRY_INVALID, "$", f"se esperaba dict, se recibió {type(d).__name__}")]

    claves_desconocidas = sorted(k for k in d if k not in _SOURCE_REF_CLAVES)
    for clave in claves_desconocidas:
        hallazgos.append((CODE_REGISTRY_INVALID, f"$.{clave}", "clave desconocida"))

    source_id = d.get("source_id")
    if not isinstance(source_id, str) or _RE_SOURCE_ID.fullmatch(source_id) is None:
        hallazgos.append((CODE_ID_INVALID, "$.source_id", f"id inválido {source_id!r}"))

    role = d.get("role")
    if not isinstance(role, str) or _RE_ROLE.fullmatch(role) is None:
        hallazgos.append((CODE_ROLE_INVALID, "$.role", f"role inválido {role!r}"))

    observer = d.get("observer")
    if not isinstance(observer, str) or _RE_OBSERVER.fullmatch(observer) is None:
        hallazgos.append((CODE_OBSERVER_MALFORMED, "$.observer", f"observer inválido {observer!r}"))

    access_mode = d.get("access_mode")
    if access_mode in RESERVED_ACCESS_MODES:
        hallazgos.append(
            (CODE_ACCESS_MODE_RESERVED, "$.access_mode", f"access_mode reservado {access_mode!r}")
        )
    elif access_mode not in ACCESS_MODES:
        hallazgos.append(
            (CODE_REGISTRY_INVALID, "$.access_mode", f"access_mode inválido {access_mode!r}")
        )

    sensitivity = d.get("sensitivity")
    if sensitivity not in SENSITIVITIES:
        hallazgos.append(
            (CODE_SENSITIVITY_INVALID, "$.sensitivity", f"sensitivity inválida {sensitivity!r}")
        )

    if "config_ref" in d and d["config_ref"] is not None:
        config_ref = d["config_ref"]
        if not isinstance(config_ref, str) or _RE_CONFIG_REF.fullmatch(config_ref) is None:
            hallazgos.append(
                (CODE_CONFIG_REF_INVALID, "$.config_ref", f"config_ref inválido {config_ref!r}")
            )

    if "options" in d:
        try:
            _validar_options(d["options"], "$.options", CODE_OPTIONS_INVALID)
        except SourceError as exc:
            hallazgos.append((exc.code, "$.options", exc.message))

    if "extra" in d:
        try:
            _validar_extra(d["extra"], "$.extra")
        except SourceError as exc:
            hallazgos.append((exc.code, "$.extra", exc.message))

    return hallazgos


@dataclass(frozen=True)
class SourceRef:
    """Entrada del registro de fuentes: identidad lógica (`source_id`,
    `role`), forma de acceder (`observer`, `access_mode`, `config_ref`),
    política declarativa (`sensitivity`) y `options` opacas para Harmessi.

    `access_mode` NO se valida contra el vocabulario reservado (`"write"`) en
    este constructor: la construcción directa acepta cualquier `str` (uso
    interno del runtime); es `SourceRef.from_dict`/`validate_source_ref`
    quien emite el hallazgo `SOURCE-ACCESS-MODE-RESERVED`/
    `SOURCE-REGISTRY-INVALID` sobre un dict de entrada (spec R4)."""

    source_id: str
    role: str
    observer: str
    access_mode: str
    sensitivity: str
    config_ref: Optional[str] = None
    options: dict = _campo_dataclass(default_factory=dict)
    extra: dict = _campo_dataclass(default_factory=dict)

    def __post_init__(self) -> None:
        if _RE_SOURCE_ID.fullmatch(_exigir_str(self.source_id, "SourceRef.source_id", CODE_ID_INVALID)) is None:
            raise SourceError(CODE_ID_INVALID, f"SourceRef.source_id: id inválido {self.source_id!r}")
        if _RE_ROLE.fullmatch(_exigir_str(self.role, "SourceRef.role", CODE_ROLE_INVALID)) is None:
            raise SourceError(CODE_ROLE_INVALID, f"SourceRef.role: role inválido {self.role!r}")
        if _RE_OBSERVER.fullmatch(_exigir_str(self.observer, "SourceRef.observer", CODE_OBSERVER_MALFORMED)) is None:
            raise SourceError(CODE_OBSERVER_MALFORMED, f"SourceRef.observer: observer inválido {self.observer!r}")
        _exigir_str(self.access_mode, "SourceRef.access_mode", CODE_REGISTRY_INVALID)
        if self.sensitivity not in SENSITIVITIES:
            raise SourceError(
                CODE_SENSITIVITY_INVALID, f"SourceRef.sensitivity: {self.sensitivity!r} fuera de {SENSITIVITIES}"
            )
        if self.config_ref is not None:
            if (
                not isinstance(self.config_ref, str)
                or _RE_CONFIG_REF.fullmatch(self.config_ref) is None
            ):
                raise SourceError(
                    CODE_CONFIG_REF_INVALID, f"SourceRef.config_ref: config_ref inválido {self.config_ref!r}"
                )
        opciones = _validar_options(self.options, "SourceRef.options", CODE_OPTIONS_INVALID)
        extra = _validar_extra(self.extra, "SourceRef.extra")
        object.__setattr__(self, "options", opciones)
        object.__setattr__(self, "extra", extra)

    def to_dict(self) -> dict:
        return {
            "source_id": self.source_id,
            "role": self.role,
            "observer": self.observer,
            "access_mode": self.access_mode,
            "sensitivity": self.sensitivity,
            "config_ref": self.config_ref,
            "options": self.options,
            "extra": self.extra,
        }

    @classmethod
    def from_dict(cls, d: Any) -> "SourceRef":
        hallazgos = validate_source_ref(d)
        if hallazgos:
            code, path, motivo = hallazgos[0]
            raise SourceError(code, f"{path}: {motivo}")
        return cls(
            source_id=d["source_id"],
            role=d["role"],
            observer=d["observer"],
            access_mode=d["access_mode"],
            sensitivity=d["sensitivity"],
            config_ref=d.get("config_ref"),
            options=d.get("options", {}),
            extra=d.get("extra", {}),
        )


# ---------------------------------------------------------------------------
# SourceCapabilities (R10)
# ---------------------------------------------------------------------------


def validate_capabilities(d: Any) -> None:
    """Valida la FORMA de un dict candidato a `SourceCapabilities`; lanza
    `SourceError(CODE_CAPABILITIES_INVALID, ...)` ante cualquier
    faceta/operación fuera del vocabulario fijo (`execute_query` incluido)."""
    if not isinstance(d, dict):
        raise SourceError(CODE_CAPABILITIES_INVALID, f"se esperaba dict, se recibió {type(d).__name__}")
    claves_desconocidas = sorted(k for k in d if k not in ("facets", "operations"))
    if claves_desconocidas:
        raise SourceError(CODE_CAPABILITIES_INVALID, f"claves desconocidas {claves_desconocidas}")
    facets = d.get("facets", {})
    if not isinstance(facets, dict):
        raise SourceError(CODE_CAPABILITIES_INVALID, f"facets: se esperaba dict, se recibió {type(facets).__name__}")
    facetas_validas = set(DATASET_FACETS) | set(FIELD_FACETS)
    for clave, exactitudes in facets.items():
        if clave not in facetas_validas:
            raise SourceError(CODE_CAPABILITIES_INVALID, f"facets: faceta desconocida {clave!r}")
        valores = list(exactitudes) if isinstance(exactitudes, (list, tuple, set, frozenset)) else None
        if valores is None or not valores:
            raise SourceError(
                CODE_CAPABILITIES_INVALID, f"facets[{clave!r}]: se esperaba conjunto no vacío de exactitudes"
            )
        for exactitud in valores:
            if exactitud not in EXACTNESS_VALUES:
                raise SourceError(
                    CODE_CAPABILITIES_INVALID, f"facets[{clave!r}]: exactitud inválida {exactitud!r}"
                )
    operations = d.get("operations", ())
    if not isinstance(operations, (list, tuple, set, frozenset)):
        raise SourceError(CODE_CAPABILITIES_INVALID, "operations: se esperaba lista/conjunto")
    for op in operations:
        if op not in OPERATIONS:
            raise SourceError(CODE_CAPABILITIES_INVALID, f"operations: operación desconocida {op!r}")


@dataclass(frozen=True)
class SourceCapabilities:
    """Lo que un observer declara poder observar: `facets` (mapa faceta ->
    conjunto no vacío de exactitudes soportadas) y `operations` (subconjunto
    informativo de `OPERATIONS`; el core nunca invoca `read`/`write`/
    `sample`). `execute_query` no existe en el vocabulario."""

    facets: dict = _campo_dataclass(default_factory=dict)
    operations: frozenset = _campo_dataclass(default_factory=frozenset)

    def __post_init__(self) -> None:
        validate_capabilities({"facets": self.facets, "operations": self.operations})
        facets_norm = {clave: frozenset(valores) for clave, valores in self.facets.items()}
        object.__setattr__(self, "facets", facets_norm)
        object.__setattr__(self, "operations", frozenset(self.operations))

    def to_dict(self) -> dict:
        return {
            "facets": {clave: sorted(valores) for clave, valores in self.facets.items()},
            "operations": sorted(self.operations),
        }

    @classmethod
    def from_dict(cls, d: Any) -> "SourceCapabilities":
        validate_capabilities(d)
        return cls(
            facets={clave: frozenset(valores) for clave, valores in d.get("facets", {}).items()},
            operations=frozenset(d.get("operations", ())),
        )


# ---------------------------------------------------------------------------
# ObservationRequest (R11)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ObservationRequest:
    """Pedido de observación acotado: nunca contiene texto de consulta
    (`query`/`sql`/`statement` u otra clave desconocida son
    `SOURCE-OBSERVATION-INVALID`)."""

    source_id: str
    facets: tuple = ()
    exactness: str = "any"
    as_of: Optional[str] = None
    max_rows: Optional[int] = None
    sample_size: Optional[int] = None

    def __post_init__(self) -> None:
        if _RE_SOURCE_ID.fullmatch(_exigir_str(self.source_id, "ObservationRequest.source_id", CODE_OBSERVATION_INVALID)) is None:
            raise SourceError(
                CODE_OBSERVATION_INVALID, f"ObservationRequest.source_id: id inválido {self.source_id!r}"
            )
        facets = tuple(self.facets)
        for faceta in facets:
            if faceta not in DATASET_FACETS and faceta not in FIELD_FACETS:
                raise SourceError(
                    CODE_OBSERVATION_INVALID, f"ObservationRequest.facets: faceta desconocida {faceta!r}"
                )
        if self.exactness not in ("any", "exact"):
            raise SourceError(
                CODE_OBSERVATION_INVALID, f"ObservationRequest.exactness: {self.exactness!r} fuera de any/exact"
            )
        if self.as_of is not None:
            if not isinstance(self.as_of, str) or _RE_ISO8601.fullmatch(self.as_of) is None:
                raise SourceError(CODE_OBSERVATION_INVALID, f"ObservationRequest.as_of: no es ISO-8601 {self.as_of!r}")
        for nombre in ("max_rows", "sample_size"):
            valor = getattr(self, nombre)
            if valor is not None:
                if isinstance(valor, bool) or not isinstance(valor, int) or valor <= 0:
                    raise SourceError(
                        CODE_OBSERVATION_INVALID, f"ObservationRequest.{nombre}: se esperaba int > 0, se recibió {valor!r}"
                    )
        object.__setattr__(self, "facets", facets)

    def to_dict(self) -> dict:
        return {
            "source_id": self.source_id,
            "facets": list(self.facets),
            "exactness": self.exactness,
            "as_of": self.as_of,
            "max_rows": self.max_rows,
            "sample_size": self.sample_size,
        }

    @classmethod
    def from_dict(cls, d: Any) -> "ObservationRequest":
        if not isinstance(d, dict):
            raise SourceError(CODE_OBSERVATION_INVALID, f"se esperaba dict, se recibió {type(d).__name__}")
        desconocidas = sorted(k for k in d if k not in _OBSERVATION_REQUEST_CLAVES)
        if desconocidas:
            raise SourceError(CODE_OBSERVATION_INVALID, f"claves desconocidas {desconocidas}")
        if "source_id" not in d:
            raise SourceError(CODE_OBSERVATION_INVALID, "falta source_id")
        return cls(
            source_id=d["source_id"],
            facets=tuple(d.get("facets", ())),
            exactness=d.get("exactness", "any"),
            as_of=d.get("as_of"),
            max_rows=d.get("max_rows"),
            sample_size=d.get("sample_size"),
        )


# ---------------------------------------------------------------------------
# Facetas de campo / dataset: validación de forma (R5)
# ---------------------------------------------------------------------------


def _validar_faceta_conteo(d: Any, ruta: str) -> dict:
    if not isinstance(d, dict):
        raise SourceError(CODE_OBSERVATION_INVALID, f"{ruta}: se esperaba dict")
    valor = d.get("value")
    if isinstance(valor, bool) or not isinstance(valor, int) or valor < 0:
        raise SourceError(CODE_OBSERVATION_INVALID, f"{ruta}.value: se esperaba int >= 0")
    exactitud = d.get("exactness")
    if exactitud not in EXACTNESS_VALUES:
        raise SourceError(CODE_OBSERVATION_INVALID, f"{ruta}.exactness: {exactitud!r} inválida")
    return {"value": valor, "exactness": exactitud}


def _validar_faceta_rango(d: Any, ruta: str) -> dict:
    if not isinstance(d, dict):
        raise SourceError(CODE_OBSERVATION_INVALID, f"{ruta}: se esperaba dict")
    valor = d.get("value")
    if not isinstance(valor, dict) or set(valor) - {"min", "max"}:
        raise SourceError(CODE_OBSERVATION_INVALID, f"{ruta}.value: se esperaba dict {{min,max}}")
    if "min" not in valor or "max" not in valor:
        raise SourceError(CODE_OBSERVATION_INVALID, f"{ruta}.value: requiere min y max")
    exactitud = d.get("exactness")
    if exactitud not in EXACTNESS_VALUES:
        raise SourceError(CODE_OBSERVATION_INVALID, f"{ruta}.exactness: {exactitud!r} inválida")
    return {"value": {"min": valor["min"], "max": valor["max"]}, "exactness": exactitud}


def _validar_faceta_distribucion(d: Any, ruta: str) -> dict:
    if not isinstance(d, dict):
        raise SourceError(CODE_OBSERVATION_INVALID, f"{ruta}: se esperaba dict")
    valor = d.get("value")
    if not isinstance(valor, list):
        raise SourceError(CODE_OBSERVATION_INVALID, f"{ruta}.value: se esperaba list")
    items = []
    for i, item in enumerate(valor):
        if not isinstance(item, dict) or "value" not in item or "frequency" not in item:
            raise SourceError(CODE_OBSERVATION_INVALID, f"{ruta}.value[{i}]: se esperaba {{value,frequency}}")
        frecuencia = item["frequency"]
        if isinstance(frecuencia, bool) or not isinstance(frecuencia, int) or frecuencia < 1:
            raise SourceError(CODE_OBSERVATION_INVALID, f"{ruta}.value[{i}].frequency: se esperaba int >= 1")
        items.append({"value": item["value"], "frequency": frecuencia})
    exactitud = d.get("exactness")
    if exactitud not in EXACTNESS_VALUES:
        raise SourceError(CODE_OBSERVATION_INVALID, f"{ruta}.exactness: {exactitud!r} inválida")
    completo = d.get("complete")
    if not isinstance(completo, bool):
        raise SourceError(CODE_OBSERVATION_INVALID, f"{ruta}.complete: se esperaba bool")
    return {"value": items, "exactness": exactitud, "complete": completo}


_VALIDADORES_FACETA_CAMPO = {
    "null_count": _validar_faceta_conteo,
    "distinct_count": _validar_faceta_conteo,
    "value_range": _validar_faceta_rango,
    "time_range": _validar_faceta_rango,
    "value_distribution": _validar_faceta_distribucion,
}


def _validar_facets_campo(d: Any, ruta: str) -> dict:
    if not isinstance(d, dict):
        raise SourceError(CODE_OBSERVATION_INVALID, f"{ruta}: se esperaba dict")
    resultado: dict = {}
    for clave, valor in d.items():
        if clave not in _VALIDADORES_FACETA_CAMPO:
            raise SourceError(CODE_OBSERVATION_INVALID, f"{ruta}: faceta de campo desconocida {clave!r}")
        resultado[clave] = _VALIDADORES_FACETA_CAMPO[clave](valor, f"{ruta}.{clave}")
    return resultado


# ---------------------------------------------------------------------------
# FieldObservation (R5)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FieldObservation:
    """Observación de un campo: `type_family` acotada a
    `OBSERVED_TYPE_FAMILIES`; `native_type` es una etiqueta opaca informativa
    (el core no ramifica sobre ella). `facets` con formas fijas por clave."""

    name: str
    type_family: str
    native_type: Optional[str]
    facets: dict = _campo_dataclass(default_factory=dict)

    def __post_init__(self) -> None:
        _exigir_str(self.name, "FieldObservation.name", CODE_OBSERVATION_INVALID)
        if self.name == "":
            raise SourceError(CODE_OBSERVATION_INVALID, "FieldObservation.name: no puede ser vacío")
        if self.type_family not in OBSERVED_TYPE_FAMILIES:
            raise SourceError(
                CODE_OBSERVATION_INVALID,
                f"FieldObservation.type_family: {self.type_family!r} fuera de {OBSERVED_TYPE_FAMILIES}",
            )
        if self.native_type is not None:
            _exigir_str(self.native_type, "FieldObservation.native_type", CODE_OBSERVATION_INVALID)
        facets = _validar_facets_campo(self.facets, "FieldObservation.facets")
        object.__setattr__(self, "facets", facets)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "type_family": self.type_family,
            "native_type": self.native_type,
            "facets": self.facets,
        }

    @classmethod
    def from_dict(cls, d: Any) -> "FieldObservation":
        if not isinstance(d, dict):
            raise SourceError(CODE_OBSERVATION_INVALID, f"FieldObservation: se esperaba dict, se recibió {type(d).__name__}")
        faltantes = [c for c in ("name", "type_family") if c not in d]
        if faltantes:
            raise SourceError(CODE_OBSERVATION_INVALID, f"FieldObservation: faltan campos {faltantes}")
        return cls(
            name=d["name"],
            type_family=d["type_family"],
            native_type=d.get("native_type"),
            facets=d.get("facets", {}),
        )


# ---------------------------------------------------------------------------
# SourceProvenance (R6)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SourceProvenance:
    """Procedencia de una observación: quién/cómo/cuándo. `generated_at` lo
    calcula el runtime; `observer_code_sha256` lo calcula el runtime a partir
    del módulo importado (nunca lo declara el observer, D6)."""

    source_id: str
    observer_id: str
    observer_code_sha256: Optional[str]
    access_mode: str
    source_kind: Optional[str]
    generated_at: str
    tool_versions: dict = _campo_dataclass(default_factory=dict)
    requested_facets: tuple = ()
    unsupported_facets: tuple = ()

    def __post_init__(self) -> None:
        if _RE_SOURCE_ID.fullmatch(_exigir_str(self.source_id, "SourceProvenance.source_id", CODE_OBSERVATION_INVALID)) is None:
            raise SourceError(CODE_OBSERVATION_INVALID, f"SourceProvenance.source_id: id inválido {self.source_id!r}")
        _exigir_str(self.observer_id, "SourceProvenance.observer_id", CODE_OBSERVATION_INVALID)
        if self.observer_code_sha256 is not None:
            _exigir_str(self.observer_code_sha256, "SourceProvenance.observer_code_sha256", CODE_OBSERVATION_INVALID)
        _exigir_str(self.access_mode, "SourceProvenance.access_mode", CODE_OBSERVATION_INVALID)
        if self.source_kind is not None:
            if not isinstance(self.source_kind, str) or _RE_SOURCE_KIND.fullmatch(self.source_kind) is None:
                raise SourceError(
                    CODE_OBSERVATION_INVALID, f"SourceProvenance.source_kind: {self.source_kind!r} inválido"
                )
        if not isinstance(self.generated_at, str) or _RE_ISO8601.fullmatch(self.generated_at) is None:
            raise SourceError(
                CODE_OBSERVATION_INVALID, f"SourceProvenance.generated_at: no es ISO-8601 {self.generated_at!r}"
            )
        tool_versions = _exigir_dict(self.tool_versions, "SourceProvenance.tool_versions", CODE_OBSERVATION_INVALID)
        for clave, valor in tool_versions.items():
            if not isinstance(clave, str) or not isinstance(valor, str):
                raise SourceError(CODE_OBSERVATION_INVALID, "SourceProvenance.tool_versions: se esperaba dict str->str")
        object.__setattr__(self, "requested_facets", tuple(self.requested_facets))
        object.__setattr__(self, "unsupported_facets", tuple(self.unsupported_facets))

    def to_dict(self) -> dict:
        return {
            "source_id": self.source_id,
            "observer_id": self.observer_id,
            "observer_code_sha256": self.observer_code_sha256,
            "access_mode": self.access_mode,
            "source_kind": self.source_kind,
            "generated_at": self.generated_at,
            "tool_versions": dict(self.tool_versions),
            "requested_facets": list(self.requested_facets),
            "unsupported_facets": list(self.unsupported_facets),
        }

    @classmethod
    def from_dict(cls, d: Any) -> "SourceProvenance":
        if not isinstance(d, dict):
            raise SourceError(CODE_OBSERVATION_INVALID, f"SourceProvenance: se esperaba dict, se recibió {type(d).__name__}")
        requeridas = ("source_id", "observer_id", "access_mode", "generated_at")
        faltantes = [c for c in requeridas if c not in d]
        if faltantes:
            raise SourceError(CODE_OBSERVATION_INVALID, f"SourceProvenance: faltan campos {faltantes}")
        return cls(
            source_id=d["source_id"],
            observer_id=d["observer_id"],
            observer_code_sha256=d.get("observer_code_sha256"),
            access_mode=d["access_mode"],
            source_kind=d.get("source_kind"),
            generated_at=d["generated_at"],
            tool_versions=d.get("tool_versions", {}),
            requested_facets=tuple(d.get("requested_facets", ())),
            unsupported_facets=tuple(d.get("unsupported_facets", ())),
        )


# ---------------------------------------------------------------------------
# Dataset facets (dentro de SourceObservation)
# ---------------------------------------------------------------------------


def _validar_dataset(d: Any, ruta: str = "dataset") -> dict:
    if not isinstance(d, dict):
        raise SourceError(CODE_OBSERVATION_INVALID, f"{ruta}: se esperaba dict")
    desconocidas = sorted(k for k in d if k not in _DATASET_CLAVES)
    if desconocidas:
        raise SourceError(CODE_OBSERVATION_INVALID, f"{ruta}: claves desconocidas {desconocidas}")
    resultado: dict = {}
    if "row_count" in d:
        resultado["row_count"] = _validar_faceta_conteo(d["row_count"], f"{ruta}.row_count")
    if "fingerprint" in d:
        fp = d["fingerprint"]
        if not isinstance(fp, dict) or set(fp) != {"algorithm", "value"}:
            raise SourceError(CODE_OBSERVATION_INVALID, f"{ruta}.fingerprint: se esperaba {{algorithm,value}}")
        if not isinstance(fp["algorithm"], str) or not isinstance(fp["value"], str):
            raise SourceError(CODE_OBSERVATION_INVALID, f"{ruta}.fingerprint: algorithm/value deben ser str")
        resultado["fingerprint"] = {"algorithm": fp["algorithm"], "value": fp["value"]}
    if "snapshot" in d:
        snap = d["snapshot"]
        if not isinstance(snap, dict) or set(snap) - {"as_of", "cutoff"}:
            raise SourceError(CODE_OBSERVATION_INVALID, f"{ruta}.snapshot: se esperaba subconjunto de {{as_of,cutoff}}")
        resultado["snapshot"] = {"as_of": snap.get("as_of"), "cutoff": snap.get("cutoff")}
    if "sampling" in d:
        samp = d["sampling"]
        if not isinstance(samp, dict) or "active" not in samp or not isinstance(samp["active"], bool):
            raise SourceError(CODE_OBSERVATION_INVALID, f"{ruta}.sampling: se esperaba dict con active: bool")
        resultado["sampling"] = {
            "active": samp["active"],
            "method": samp.get("method"),
            "sample_size": samp.get("sample_size"),
            "seed": samp.get("seed"),
        }
    return resultado


# ---------------------------------------------------------------------------
# SourceObservation (R5, R7)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SourceObservation:
    """Evidencia observada de una fuente. Claves de primer nivel en
    `to_dict()` en orden fijo: `schema_version`, `source_id`, `provenance`,
    `dataset`, `fields`, `omitted_facets`. Una faceta no observada NO se
    escribe (ausencia != 0 != vacío, R5/D5)."""

    source_id: str
    provenance: SourceProvenance
    dataset: dict = _campo_dataclass(default_factory=dict)
    fields: tuple = ()
    omitted_facets: tuple = ()
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if _RE_SOURCE_ID.fullmatch(_exigir_str(self.source_id, "SourceObservation.source_id", CODE_OBSERVATION_INVALID)) is None:
            raise SourceError(CODE_OBSERVATION_INVALID, f"SourceObservation.source_id: id inválido {self.source_id!r}")
        if not isinstance(self.provenance, SourceProvenance):
            raise SourceError(
                CODE_OBSERVATION_INVALID,
                f"SourceObservation.provenance: se esperaba SourceProvenance, se recibió {type(self.provenance).__name__}",
            )
        dataset = _validar_dataset(self.dataset)
        campos = tuple(self.fields)
        nombres: set = set()
        for campo in campos:
            if not isinstance(campo, FieldObservation):
                raise SourceError(
                    CODE_OBSERVATION_INVALID,
                    f"SourceObservation.fields: se esperaba FieldObservation, se recibió {type(campo).__name__}",
                )
            if campo.name in nombres:
                raise SourceError(CODE_OBSERVATION_INVALID, f"SourceObservation.fields: nombre duplicado {campo.name!r}")
            nombres.add(campo.name)
        omitidos = tuple(self.omitted_facets)
        for item in omitidos:
            if not isinstance(item, dict) or set(item) != {"field", "facet", "reason"}:
                raise SourceError(
                    CODE_OBSERVATION_INVALID, "SourceObservation.omitted_facets: se esperaba {field,facet,reason}"
                )
        if isinstance(self.schema_version, bool) or self.schema_version != SCHEMA_VERSION:
            raise SourceError(
                CODE_OBSERVATION_INVALID,
                f"SourceObservation.schema_version: se esperaba {SCHEMA_VERSION}, se recibió {self.schema_version!r}",
            )
        object.__setattr__(self, "dataset", dataset)
        object.__setattr__(self, "fields", campos)
        object.__setattr__(self, "omitted_facets", omitidos)

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "source_id": self.source_id,
            "provenance": self.provenance.to_dict(),
            "dataset": self.dataset,
            "fields": [campo.to_dict() for campo in self.fields],
            "omitted_facets": [dict(item) for item in self.omitted_facets],
        }

    @classmethod
    def from_dict(cls, d: Any) -> "SourceObservation":
        if not isinstance(d, dict):
            raise SourceError(CODE_OBSERVATION_INVALID, f"SourceObservation: se esperaba dict, se recibió {type(d).__name__}")
        requeridas = ("schema_version", "source_id", "provenance", "dataset", "fields")
        faltantes = [c for c in requeridas if c not in d]
        if faltantes:
            raise SourceError(CODE_OBSERVATION_INVALID, f"SourceObservation: faltan campos {faltantes}")
        return cls(
            source_id=d["source_id"],
            provenance=SourceProvenance.from_dict(d["provenance"]),
            dataset=d.get("dataset", {}),
            fields=tuple(FieldObservation.from_dict(item) for item in d["fields"]),
            omitted_facets=tuple(d.get("omitted_facets", ())),
            schema_version=d["schema_version"],
        )

    def content_sha256(self) -> str:
        """sha256 hex de la forma canónica de `to_dict()`, con
        `provenance.generated_at` EXCLUIDO (borrado de una copia antes de
        canonicalizar): dos observaciones que difieren solo en
        `generated_at` comparten hash (R7)."""
        datos = self.to_dict()
        provenance_sin_fecha = dict(datos["provenance"])
        provenance_sin_fecha.pop("generated_at", None)
        datos["provenance"] = provenance_sin_fecha
        return content_sha256(datos)

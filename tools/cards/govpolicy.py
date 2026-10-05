"""Policy de governance como datos (v0.9 Change 3,
`20261005-model-risk-responsible-ai`).

Define el contrato de policy (niveles, dimensiones, requisitos, orden de fuerza),
la policy base `BASE_POLICY` (`harmessi-base` v1), el documento de endurecimiento
de proyecto y el merge monotónico fail-closed que produce la policy efectiva.

ALCANCE. La matriz base es un baseline de DOCUMENTACION/EVIDENCIA: exige que
exista evidencia o atestación respaldada e íntegra, no un resultado. NO es una
definición universal de riesgo ético, NO es un marco de cumplimiento normativo y
NO juzga que un modelo sea justo, seguro, privado o explicable. Cualquier cambio
de la matriz implica una NUEVA `version` (y por lo tanto un nuevo hash).

Solo-stdlib; importa únicamente `core` (patrón dual de import). Fail-closed: toda
entrada malformada produce `GovPolicyError`, nunca una excepción cruda de Python.
Los tipos son inmutables; `to_dict`/`from_dict` son estrictos (clave desconocida
-> error; `bool` no es `int`; tipos exactos).
"""
from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Callable, Optional

try:  # patrón dual: paquete (`tools.cards`) o módulo suelto
    from . import core
except ImportError:  # pragma: no cover - ejecución sin paquete
    import core  # type: ignore[no-redef]

# ---------------------------------------------------------------------------
# Vocabularios cerrados
# ---------------------------------------------------------------------------

POLICY_SCHEMA_VERSION = 1

LEVELS = ("low", "medium", "high")
DIMENSIONS = (
    "fairness",
    "explainability",
    "privacy",
    "security",
    "accountability",
    "human_oversight",
)
# Orden de fuerza: índice mayor = más fuerte.
SEVERITIES = ("recommended", "required")
# Clases de soporte aceptables (orden canónico).
ACCEPT_CLASSES = ("observed", "attestation")
ATTESTATION_KINDS = ("declared", "anchored")

EXTERNAL_EVIDENCE_KINDS = (
    "evidence_document",
    "execution_record",
    "observed_metric",
    "baseline_reference",
    "model_quality_result",
    "drift_evidence",
)
# Kinds de los requisitos estructurales derivados (no son de la policy).
_STRUCTURAL_KINDS = ("model_card", "governance_policy")

# Ids de requisito reservados para los pins estructurales derivados.
STRUCTURAL_REQUIREMENT_IDS = ("model_card_pin", "policy_hardening_pin")

ATOM_ATT_DECLARED = "att_declared"
ATOM_ATT_ANCHORED = "att_anchored"

# ---------------------------------------------------------------------------
# Códigos y error
# ---------------------------------------------------------------------------

CODE_INVALID = "GOVPOLICY-INVALID"
CODE_NOT_MONOTONIC = "GOVPOLICY-NOT-MONOTONIC"
CODE_RELAXATION = "GOVPOLICY-RELAXATION"
CODE_BASE_MISMATCH = "GOVPOLICY-BASE-MISMATCH"
CODE_UNKNOWN_KEY = "GOVPOLICY-UNKNOWN-KEY"
CODE_SCHEMA_UNSUPPORTED = "GOVPOLICY-SCHEMA-UNSUPPORTED"

CODES = (
    CODE_INVALID,
    CODE_NOT_MONOTONIC,
    CODE_RELAXATION,
    CODE_BASE_MISMATCH,
    CODE_UNKNOWN_KEY,
    CODE_SCHEMA_UNSUPPORTED,
)


class GovPolicyError(Exception):
    """Única excepción pública de `govpolicy`. `code` es uno de `CODES`."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


# ---------------------------------------------------------------------------
# Helpers privados
# ---------------------------------------------------------------------------


def _invalido(mensaje: str) -> GovPolicyError:
    return GovPolicyError(CODE_INVALID, mensaje)


def _tipo(valor: Any) -> str:
    return type(valor).__name__


def _fijar(obj: Any, nombre: str, valor: Any) -> None:
    object.__setattr__(obj, nombre, valor)


def _via_core(funcion: Callable[[], Any]) -> Any:
    """Ejecuta un validador de `core`; `CardError` (u otra) -> `GovPolicyError`."""
    try:
        return funcion()
    except GovPolicyError:
        raise
    except core.CardError as exc:
        raise _invalido(exc.message) from exc
    except Exception as exc:  # fail-closed
        raise _invalido(f"entrada malformada ({_tipo(exc)}: {exc})") from exc


def _envolver(funcion: Callable[[], Any], campo: str) -> Any:
    try:
        return funcion()
    except GovPolicyError:
        raise
    except core.CardError as exc:
        raise _invalido(f"{campo}: {exc.message}") from exc
    except Exception as exc:  # fail-closed: nunca excepciones crudas
        raise _invalido(f"{campo}: entrada malformada ({_tipo(exc)}: {exc})") from exc


def _exigir_str(valor: Any, campo: str) -> str:
    if not isinstance(valor, str):
        raise _invalido(f"{campo}: se esperaba str, se recibió {_tipo(valor)}")
    return valor


def _exigir_int(valor: Any, campo: str, minimo: int = 1) -> int:
    if isinstance(valor, bool) or not isinstance(valor, int):
        raise _invalido(f"{campo}: se esperaba int, se recibió {_tipo(valor)}")
    if valor < minimo:
        raise _invalido(f"{campo}: debe ser >= {minimo}")
    return valor


def _exigir_id(valor: Any, campo: str) -> str:
    _exigir_str(valor, campo)
    _via_core(lambda: core._exigir_id(valor, campo))
    return valor


def _exigir_sha(valor: Any, campo: str) -> str:
    _exigir_str(valor, campo)
    _via_core(lambda: core._exigir_sha256(valor, campo))
    return valor


def _exigir_requirement_id(valor: Any, campo: str) -> str:
    _exigir_id(valor, campo)
    if valor in core.RESERVED_CARD_IDS:
        raise _invalido(f"{campo}: id reservado {valor!r}")
    if valor in STRUCTURAL_REQUIREMENT_IDS:
        raise _invalido(f"{campo}: id estructural reservado {valor!r}")
    return valor


def _exigir_schema(valor: Any, campo: str) -> int:
    if isinstance(valor, bool) or not isinstance(valor, int):
        raise _invalido(f"{campo}: se esperaba int, se recibió {_tipo(valor)}")
    if valor != POLICY_SCHEMA_VERSION:
        raise GovPolicyError(CODE_SCHEMA_UNSUPPORTED, f"{campo}: schema_version {valor!r} no soportado")
    return valor


def _exigir_nivel(valor: Any, campo: str) -> str:
    if not isinstance(valor, str) or valor not in LEVELS:
        raise _invalido(f"{campo}: nivel inválido {valor!r}")
    return valor


def _exigir_dict(valor: Any, campo: str) -> dict:
    if not isinstance(valor, dict):
        raise _invalido(f"{campo}: se esperaba dict, se recibió {_tipo(valor)}")
    return valor


def _exigir_secuencia(valor: Any, campo: str) -> tuple:
    if not isinstance(valor, (list, tuple)):
        raise _invalido(f"{campo}: se esperaba lista/tupla, se recibió {_tipo(valor)}")
    return tuple(valor)


def _claves(datos: Any, obligatorias: tuple, opcionales: tuple, campo: str) -> None:
    """Clave desconocida -> UNKNOWN-KEY; obligatoria ausente -> INVALID."""
    _exigir_dict(datos, campo)
    for clave in datos:
        if not isinstance(clave, str):
            raise GovPolicyError(CODE_UNKNOWN_KEY, f"{campo}: clave no-str {clave!r}")
        if clave not in obligatorias and clave not in opcionales:
            raise GovPolicyError(CODE_UNKNOWN_KEY, f"{campo}: clave desconocida {clave!r}")
    for clave in obligatorias:
        if clave not in datos:
            raise _invalido(f"{campo}: falta la clave obligatoria {clave!r}")


def _exigir_descripcion(valor: Any, campo: str) -> str:
    _exigir_str(valor, campo)
    if valor == "":
        return valor
    _via_core(lambda: core._texto(valor, campo))
    return valor


def _hash(obj: Any) -> str:
    try:
        return hashlib.sha256(core.canonical_json(obj).encode("utf-8")).hexdigest()
    except core.CardError as exc:
        raise _invalido(exc.message) from exc


# ---------------------------------------------------------------------------
# LevelSpec
# ---------------------------------------------------------------------------

_LEVELSPEC_OBLIGATORIAS = ("severity", "accepts")
_LEVELSPEC_OPCIONALES = ("accepted_kinds", "min_attestation_kind")


@dataclass(frozen=True)
class LevelSpec:
    """Qué exige un requisito en un nivel. `accepts` y `accepted_kinds` se
    normalizan (deduplicados, orden canónico). `accepted_kinds=None` = todos los
    kinds de evidencia permitidos."""

    severity: str
    accepts: tuple
    accepted_kinds: Optional[tuple] = None
    min_attestation_kind: str = "declared"

    def __post_init__(self) -> None:
        if not isinstance(self.severity, str) or self.severity not in SEVERITIES:
            raise _invalido(f"LevelSpec.severity inválida {self.severity!r}")
        acepta = _exigir_secuencia(self.accepts, "LevelSpec.accepts")
        for c in acepta:
            if not isinstance(c, str) or c not in ACCEPT_CLASSES:
                raise _invalido(f"LevelSpec.accepts: clase inválida {c!r}")
        if not acepta:
            raise _invalido("LevelSpec.accepts no puede ser vacío")
        _fijar(self, "accepts", tuple(c for c in ACCEPT_CLASSES if c in acepta))
        if self.accepted_kinds is not None:
            kinds = _exigir_secuencia(self.accepted_kinds, "LevelSpec.accepted_kinds")
            for k in kinds:
                if not isinstance(k, str) or k not in core.OBSERVED_KINDS or k not in EXTERNAL_EVIDENCE_KINDS:
                    raise _invalido(f"LevelSpec.accepted_kinds: kind no permitido {k!r}")
            if not kinds:
                raise _invalido("LevelSpec.accepted_kinds no puede ser vacío (use None)")
            _fijar(self, "accepted_kinds", tuple(sorted(set(kinds))))
        if not isinstance(self.min_attestation_kind, str) or self.min_attestation_kind not in ATTESTATION_KINDS:
            raise _invalido(f"LevelSpec.min_attestation_kind inválido {self.min_attestation_kind!r}")

    def to_dict(self) -> dict:
        return {
            "severity": self.severity,
            "accepts": list(self.accepts),
            "accepted_kinds": None if self.accepted_kinds is None else list(self.accepted_kinds),
            "min_attestation_kind": self.min_attestation_kind,
        }

    @classmethod
    def from_dict(cls, data: Any) -> "LevelSpec":
        def _construir() -> "LevelSpec":
            _claves(data, _LEVELSPEC_OBLIGATORIAS, _LEVELSPEC_OPCIONALES, "LevelSpec")
            return cls(
                severity=data["severity"],
                accepts=data["accepts"],
                accepted_kinds=data.get("accepted_kinds"),
                min_attestation_kind=data.get("min_attestation_kind", "declared"),
            )

        return _envolver(_construir, "LevelSpec")


class _NivelesInmutables(Mapping):
    """Mapping de solo lectura nivel -> `LevelSpec` (orden de `LEVELS`).
    Asignar o borrar un nivel lanza `TypeError`. Es comparable con `dict`,
    copiable (`copy`/`deepcopy`/`dataclasses.replace`) y picklable."""

    __slots__ = ("_datos",)

    def __init__(self, datos: dict) -> None:
        object.__setattr__(self, "_datos", dict(datos))

    def __setattr__(self, nombre: str, valor: Any) -> None:
        raise TypeError("_NivelesInmutables es de solo lectura")

    def __delattr__(self, nombre: str) -> None:
        raise TypeError("_NivelesInmutables es de solo lectura")

    def __getitem__(self, clave: Any) -> Any:
        return self._datos[clave]

    def __iter__(self):
        return iter(self._datos)

    def __len__(self) -> int:
        return len(self._datos)

    def __repr__(self) -> str:
        return f"{self._datos!r}"

    def __reduce__(self):
        return (_NivelesInmutables, (dict(self._datos),))


def _normalizar_levels(levels: Any, campo: str) -> Mapping:
    if not isinstance(levels, Mapping):
        raise _invalido(f"{campo}: se esperaba mapping nivel->LevelSpec, se recibió {_tipo(levels)}")
    if not levels:
        raise _invalido(f"{campo}: no puede ser vacío")
    for nivel, spec in levels.items():
        _exigir_nivel(nivel, f"{campo} (clave)")
        if not isinstance(spec, LevelSpec):
            raise _invalido(f"{campo}[{nivel}]: se esperaba LevelSpec, se recibió {_tipo(spec)}")
    return _NivelesInmutables({nivel: levels[nivel] for nivel in LEVELS if nivel in levels})


def _levels_a_dict(levels: dict) -> dict:
    return {nivel: levels[nivel].to_dict() for nivel in LEVELS if nivel in levels}


def _levels_desde_dict(datos: Any, campo: str) -> dict:
    _exigir_dict(datos, campo)
    resultado: dict = {}
    for nivel, spec in datos.items():
        _exigir_nivel(nivel, f"{campo} (clave)")
        resultado[nivel] = LevelSpec.from_dict(spec)
    return resultado


# ---------------------------------------------------------------------------
# PolicyRequirement
# ---------------------------------------------------------------------------

_REQ_OBLIGATORIAS = ("requirement_id", "dimension", "levels")
_REQ_OPCIONALES = ("description",)


@dataclass(frozen=True)
class PolicyRequirement:
    """Requisito de policy. Un nivel ausente en `levels` = no aplica en ese nivel."""

    requirement_id: str
    dimension: str
    levels: Mapping  # se normaliza a un mapping de solo lectura (TypeError al mutar)
    description: str = ""

    def __post_init__(self) -> None:
        _exigir_requirement_id(self.requirement_id, "PolicyRequirement.requirement_id")
        if not isinstance(self.dimension, str) or self.dimension not in DIMENSIONS:
            raise _invalido(f"PolicyRequirement.dimension inválida {self.dimension!r}")
        _fijar(self, "levels", _normalizar_levels(self.levels, "PolicyRequirement.levels"))
        _exigir_descripcion(self.description, "PolicyRequirement.description")

    def to_dict(self) -> dict:
        return {
            "requirement_id": self.requirement_id,
            "dimension": self.dimension,
            "description": self.description,
            "levels": _levels_a_dict(self.levels),
        }

    @classmethod
    def from_dict(cls, data: Any) -> "PolicyRequirement":
        def _construir() -> "PolicyRequirement":
            _claves(data, _REQ_OBLIGATORIAS, _REQ_OPCIONALES, "PolicyRequirement")
            return cls(
                requirement_id=data["requirement_id"],
                dimension=data["dimension"],
                levels=_levels_desde_dict(data["levels"], "PolicyRequirement.levels"),
                description=data.get("description", ""),
            )

        return _envolver(_construir, "PolicyRequirement")


def _normalizar_requirements(valor: Any, campo: str) -> tuple:
    items = _exigir_secuencia(valor, campo)
    vistos: set = set()
    for i, r in enumerate(items):
        if not isinstance(r, PolicyRequirement):
            raise _invalido(f"{campo}[{i}]: se esperaba PolicyRequirement, se recibió {_tipo(r)}")
        if r.requirement_id in vistos:
            raise _invalido(f"{campo}: requirement_id duplicado {r.requirement_id!r}")
        vistos.add(r.requirement_id)
    return tuple(sorted(items, key=lambda r: r.requirement_id))


# ---------------------------------------------------------------------------
# GovernancePolicy
# ---------------------------------------------------------------------------

_POLICY_OBLIGATORIAS = ("policy_id", "version", "requirements")
_POLICY_OPCIONALES = ("schema_version",)


@dataclass(frozen=True)
class GovernancePolicy:
    """Policy como datos. Los requisitos se guardan ordenados por id (el hash no
    depende del orden de entrada). La monotonicidad entre niveles NO se impone
    en el constructor: se verifica con `validate_monotonic` y `merge`."""

    policy_id: str
    version: int
    requirements: tuple
    schema_version: int = POLICY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _exigir_schema(self.schema_version, "GovernancePolicy.schema_version")
        _exigir_id(self.policy_id, "GovernancePolicy.policy_id")
        _exigir_int(self.version, "GovernancePolicy.version")
        _fijar(self, "requirements", _normalizar_requirements(self.requirements, "GovernancePolicy.requirements"))

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "policy_id": self.policy_id,
            "version": self.version,
            "requirements": [r.to_dict() for r in self.requirements],
        }

    def content_sha256(self) -> str:
        return _hash(self.to_dict())

    @classmethod
    def from_dict(cls, data: Any) -> "GovernancePolicy":
        def _construir() -> "GovernancePolicy":
            _claves(data, _POLICY_OBLIGATORIAS, _POLICY_OPCIONALES, "GovernancePolicy")
            if "schema_version" in data:
                _exigir_schema(data["schema_version"], "GovernancePolicy.schema_version")
            return cls(
                policy_id=data["policy_id"],
                version=data["version"],
                requirements=tuple(
                    PolicyRequirement.from_dict(r)
                    for r in _exigir_secuencia(data["requirements"], "GovernancePolicy.requirements")
                ),
            )

        return _envolver(_construir, "GovernancePolicy")


# ---------------------------------------------------------------------------
# HardeningDocument
# ---------------------------------------------------------------------------

_OVERRIDE_OBLIGATORIAS = ("requirement_id", "levels")
_HARDENING_OBLIGATORIAS = ("policy_id", "base_version")
_HARDENING_OPCIONALES = ("schema_version", "risk_floor", "overrides", "additional")


@dataclass(frozen=True)
class RequirementOverride:
    """Reemplazo de los `LevelSpec` de ciertos niveles de un requisito base.
    Solo toca los niveles indicados; el resto queda como en la base."""

    requirement_id: str
    levels: dict

    def __post_init__(self) -> None:
        _exigir_requirement_id(self.requirement_id, "RequirementOverride.requirement_id")
        _fijar(self, "levels", _normalizar_levels(self.levels, "RequirementOverride.levels"))

    def to_dict(self) -> dict:
        return {"requirement_id": self.requirement_id, "levels": _levels_a_dict(self.levels)}

    @classmethod
    def from_dict(cls, data: Any) -> "RequirementOverride":
        def _construir() -> "RequirementOverride":
            _claves(data, _OVERRIDE_OBLIGATORIAS, (), "RequirementOverride")
            return cls(
                requirement_id=data["requirement_id"],
                levels=_levels_desde_dict(data["levels"], "RequirementOverride.levels"),
            )

        return _envolver(_construir, "RequirementOverride")


@dataclass(frozen=True)
class HardeningDocument:
    """Documento de endurecimiento de proyecto (JSON neutral). `risk_floor=None`
    = sin piso. `overrides`/`additional` se guardan ordenados por id."""

    policy_id: str
    base_version: int
    risk_floor: Optional[str] = None
    overrides: tuple = ()
    additional: tuple = ()

    def __post_init__(self) -> None:
        _exigir_id(self.policy_id, "HardeningDocument.policy_id")
        _exigir_int(self.base_version, "HardeningDocument.base_version")
        if self.risk_floor is not None:
            _exigir_nivel(self.risk_floor, "HardeningDocument.risk_floor")
        ovs = _exigir_secuencia(self.overrides, "HardeningDocument.overrides")
        vistos: set = set()
        for i, o in enumerate(ovs):
            if not isinstance(o, RequirementOverride):
                raise _invalido(f"HardeningDocument.overrides[{i}]: se esperaba RequirementOverride")
            if o.requirement_id in vistos:
                raise _invalido(f"HardeningDocument.overrides: requirement_id duplicado {o.requirement_id!r}")
            vistos.add(o.requirement_id)
        _fijar(self, "overrides", tuple(sorted(ovs, key=lambda o: o.requirement_id)))
        _fijar(self, "additional", _normalizar_requirements(self.additional, "HardeningDocument.additional"))

    def to_dict(self) -> dict:
        return {
            "schema_version": POLICY_SCHEMA_VERSION,
            "policy_id": self.policy_id,
            "base_version": self.base_version,
            "risk_floor": self.risk_floor,
            "overrides": [o.to_dict() for o in self.overrides],
            "additional": [r.to_dict() for r in self.additional],
        }

    def content_sha256(self) -> str:
        return _hash(self.to_dict())

    @classmethod
    def from_dict(cls, data: Any) -> "HardeningDocument":
        def _construir() -> "HardeningDocument":
            _claves(data, _HARDENING_OBLIGATORIAS, _HARDENING_OPCIONALES, "HardeningDocument")
            if "schema_version" in data:
                _exigir_schema(data["schema_version"], "HardeningDocument.schema_version")
            return cls(
                policy_id=data["policy_id"],
                base_version=data["base_version"],
                risk_floor=data.get("risk_floor"),
                overrides=tuple(
                    RequirementOverride.from_dict(o)
                    for o in _exigir_secuencia(data.get("overrides", []), "HardeningDocument.overrides")
                ),
                additional=tuple(
                    PolicyRequirement.from_dict(r)
                    for r in _exigir_secuencia(data.get("additional", []), "HardeningDocument.additional")
                ),
            )

        return _envolver(_construir, "HardeningDocument")


# ---------------------------------------------------------------------------
# EffectivePolicy
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EffectivePolicy:
    """Resultado de `merge`. `effective_sha256()` es determinista e independiente
    del orden de entrada (los requisitos se ordenan por id)."""

    policy_id: str
    base_version: int
    base_sha256: str
    hardening_sha256: Optional[str]
    risk_floor: Optional[str]
    requirements: tuple
    # Hash efectivo de la capa previa cuando `merge` apila una capa sobre una
    # `EffectivePolicy`; `None` en el caso base-only (no altera su hash).
    parent_effective_sha256: Optional[str] = None

    def __post_init__(self) -> None:
        if self.parent_effective_sha256 is not None:
            _exigir_sha(self.parent_effective_sha256, "EffectivePolicy.parent_effective_sha256")
        _exigir_id(self.policy_id, "EffectivePolicy.policy_id")
        _exigir_int(self.base_version, "EffectivePolicy.base_version")
        _exigir_sha(self.base_sha256, "EffectivePolicy.base_sha256")
        if self.hardening_sha256 is not None:
            _exigir_sha(self.hardening_sha256, "EffectivePolicy.hardening_sha256")
        if self.risk_floor is not None:
            _exigir_nivel(self.risk_floor, "EffectivePolicy.risk_floor")
        _fijar(self, "requirements", _normalizar_requirements(self.requirements, "EffectivePolicy.requirements"))

    def to_dict(self) -> dict:
        d = {
            "policy_id": self.policy_id,
            "base_version": self.base_version,
            "base_sha256": self.base_sha256,
            "hardening_sha256": self.hardening_sha256,
            "risk_floor": self.risk_floor,
            "requirements": [r.to_dict() for r in self.requirements],
        }
        # Solo en capas apiladas: el caso base-only conserva exactamente su dict/hash.
        if self.parent_effective_sha256 is not None:
            d["parent_effective_sha256"] = self.parent_effective_sha256
        return d

    def effective_sha256(self) -> str:
        return _hash(self.to_dict())


# ---------------------------------------------------------------------------
# Orden de fuerza (R17) y monotonicidad (R18)
# ---------------------------------------------------------------------------


def atoms(spec: Any) -> frozenset:
    """Átomos aceptables de un `LevelSpec`: cada kind observado permitido (si
    acepta `observed`) más `att_declared`/`att_anchored` según el mínimo (si
    acepta `attestation`)."""
    if not isinstance(spec, LevelSpec):
        raise _invalido(f"atoms: se esperaba LevelSpec, se recibió {_tipo(spec)}")
    resultado: set = set()
    if "observed" in spec.accepts:
        if spec.accepted_kinds is None:
            resultado.update(EXTERNAL_EVIDENCE_KINDS)
            resultado.update(_STRUCTURAL_KINDS)
        else:
            resultado.update(spec.accepted_kinds)
    if "attestation" in spec.accepts:
        resultado.add(ATOM_ATT_ANCHORED)
        if spec.min_attestation_kind == "declared":
            resultado.add(ATOM_ATT_DECLARED)
    return frozenset(resultado)


def at_least_as_strong(b: Optional[LevelSpec], a: Optional[LevelSpec]) -> bool:
    """`b` es al menos tan fuerte como `a` (R17): severidad(b) >= severidad(a) y
    atoms(b) subconjunto de atoms(a). `None` (ausente) como `a` es siempre más
    débil (cualquier `b` lo satisface); como `b` no es más fuerte que un `a`
    presente."""
    for nombre, spec in (("b", b), ("a", a)):
        if spec is not None and not isinstance(spec, LevelSpec):
            raise _invalido(f"at_least_as_strong: {nombre} debe ser LevelSpec o None, se recibió {_tipo(spec)}")
    if a is None:
        return True
    if b is None:
        return False
    if SEVERITIES.index(b.severity) < SEVERITIES.index(a.severity):
        return False
    return atoms(b) <= atoms(a)


def _por_que_mas_debil(b: Optional[LevelSpec], a: Optional[LevelSpec]) -> str:
    if b is None:
        return "el nivel desaparece (ausente)"
    motivos: list = []
    if SEVERITIES.index(b.severity) < SEVERITIES.index(a.severity):
        motivos.append(f"severidad {a.severity!r} -> {b.severity!r}")
    extra = sorted(atoms(b) - atoms(a))
    if extra:
        motivos.append(f"átomos ampliados: {extra}")
    return "; ".join(motivos) or "no es al menos tan fuerte"


def _requisitos_de(policy: Any) -> tuple:
    if not isinstance(policy, (GovernancePolicy, EffectivePolicy)):
        raise _invalido(f"se esperaba GovernancePolicy o EffectivePolicy, se recibió {_tipo(policy)}")
    return policy.requirements


def validate_monotonic(policy: Any) -> list:
    """Hallazgos de monotonicidad entre niveles (R18); lista vacía = monótona.
    Cada hallazgo es un `core.Hallazgo(GOVPOLICY-NOT-MONOTONIC, path, detail)`.
    Por requisito: el spec de cada nivel superior es al menos tan fuerte como el
    del inferior y la presencia no desaparece al subir."""
    hallazgos: list = []
    for r in _requisitos_de(policy):
        for inferior, superior in zip(LEVELS, LEVELS[1:]):
            spec_inf = r.levels.get(inferior)
            spec_sup = r.levels.get(superior)
            if not at_least_as_strong(spec_sup, spec_inf):
                hallazgos.append(
                    core.Hallazgo(
                        CODE_NOT_MONOTONIC,
                        f"{r.requirement_id}.{inferior}->{superior}",
                        _por_que_mas_debil(spec_sup, spec_inf),
                    )
                )
    return hallazgos


def requirements_at(policy: Any, level: str) -> tuple:
    """Pares `(PolicyRequirement, LevelSpec)` activos en `level`, ordenados por
    id. Los requisitos sin spec en ese nivel no se incluyen."""
    _exigir_nivel(level, "requirements_at.level")
    return tuple((r, r.levels[level]) for r in _requisitos_de(policy) if level in r.levels)


def max_level(a: Optional[str], b: Optional[str]) -> Optional[str]:
    """Máximo de dos niveles; `None` = ausente (no gana contra un nivel). Ambos
    `None` -> `None`."""
    for nombre, valor in (("a", a), ("b", b)):
        if valor is not None:
            _exigir_nivel(valor, f"max_level.{nombre}")
    if a is None:
        return b
    if b is None:
        return a
    return a if LEVELS.index(a) >= LEVELS.index(b) else b


# ---------------------------------------------------------------------------
# merge (R25-R29): puro, determinista, fail-closed, todo-o-nada
# ---------------------------------------------------------------------------


def merge(base: Any, hardening: Optional[HardeningDocument] = None) -> EffectivePolicy:
    """Combina `base` con un endurecimiento opcional. Cualquier relajación
    rechaza TODO el endurecimiento (`GOVPOLICY-RELAXATION`, con el listado
    completo de violaciones); nunca se aplica parcialmente.

    `base` puede ser una `GovernancePolicy` o una `EffectivePolicy` (capa ya
    endurecida). En el segundo caso: `policy_id`/`base_version` deben coincidir,
    se conserva `base_sha256`, se registra `parent_effective_sha256`, los
    overrides se comparan contra los specs EFECTIVOS de la capa previa y
    `risk_floor=None` del hardening significa «sin cambios» (hereda el piso
    previo; un nivel menor es relajación; el piso efectivo es el máximo). Con
    `hardening=None` sobre una `EffectivePolicy` se devuelve esa misma capa."""
    try:
        return _merge(base, hardening)
    except GovPolicyError:
        raise
    except Exception as exc:  # fail-closed
        raise _invalido(f"merge: error inesperado ({_tipo(exc)}: {exc})") from exc


def _merge(base: Any, hardening: Any) -> EffectivePolicy:
    if not isinstance(base, (GovernancePolicy, EffectivePolicy)):
        raise _invalido(f"merge.base: se esperaba GovernancePolicy o EffectivePolicy, se recibió {_tipo(base)}")
    if hardening is not None and not isinstance(hardening, HardeningDocument):
        raise _invalido(f"merge.hardening: se esperaba HardeningDocument o None, se recibió {_tipo(hardening)}")

    capa_previa = isinstance(base, EffectivePolicy)
    if capa_previa:
        version_base = base.base_version
        base_hash = base.base_sha256
        parent_hash: Optional[str] = base.effective_sha256()
        piso_previo: Optional[str] = base.risk_floor
        if hardening is None:
            return base
    else:
        version_base = base.version
        base_hash = base.content_sha256()
        parent_hash = None
        piso_previo = None
    base_por_id = {r.requirement_id: r for r in base.requirements}
    requisitos = dict(base_por_id)
    hardening_hash: Optional[str] = None
    piso: Optional[str] = piso_previo

    if hardening is not None:
        if hardening.policy_id != base.policy_id or hardening.base_version != version_base:
            raise GovPolicyError(
                CODE_BASE_MISMATCH,
                f"el endurecimiento apunta a {hardening.policy_id!r} v{hardening.base_version}; "
                f"la base es {base.policy_id!r} v{version_base}",
            )
        violaciones: list = []
        if (
            hardening.risk_floor is not None
            and piso_previo is not None
            and LEVELS.index(hardening.risk_floor) < LEVELS.index(piso_previo)
        ):
            violaciones.append(
                f"risk_floor: baja el piso previo ({piso_previo!r} -> {hardening.risk_floor!r})"
            )
        for o in hardening.overrides:
            r = base_por_id.get(o.requirement_id)
            if r is None:
                violaciones.append(f"override {o.requirement_id!r}: no existe en la base")
                continue
            niveles = dict(r.levels)
            for nivel in LEVELS:
                if nivel not in o.levels:
                    continue
                nuevo = o.levels[nivel]
                previo = r.levels.get(nivel)
                if not at_least_as_strong(nuevo, previo):
                    violaciones.append(
                        f"override {o.requirement_id!r}[{nivel}]: relaja la base ({_por_que_mas_debil(nuevo, previo)})"
                    )
                niveles[nivel] = nuevo
            requisitos[o.requirement_id] = PolicyRequirement(
                requirement_id=r.requirement_id,
                dimension=r.dimension,
                levels=niveles,
                description=r.description,
            )
        for r in hardening.additional:
            if r.requirement_id in base_por_id:
                violaciones.append(f"additional {r.requirement_id!r}: reutiliza un id de la base")
            else:
                requisitos[r.requirement_id] = r
        # `risk_floor` solo puede ser un nivel de LEVELS (validado en el tipo): la
        # base no tiene piso, así que cualquier valor sube; None = sin piso.
        if violaciones:
            raise GovPolicyError(
                CODE_RELAXATION,
                "endurecimiento rechazado por completo; violaciones: " + " | ".join(violaciones),
            )
        hardening_hash = hardening.content_sha256()
        piso = max_level(piso_previo, hardening.risk_floor)

    efectiva = EffectivePolicy(
        policy_id=base.policy_id,
        base_version=version_base,
        base_sha256=base_hash,
        hardening_sha256=hardening_hash,
        risk_floor=piso,
        requirements=tuple(requisitos.values()),
        parent_effective_sha256=parent_hash,
    )
    no_monotonicos = validate_monotonic(efectiva)
    if no_monotonicos:
        raise GovPolicyError(
            CODE_NOT_MONOTONIC,
            "la policy efectiva no es monótona entre niveles: "
            + " | ".join(f"{h.path}: {h.detail}" for h in no_monotonicos),
        )
    return efectiva


# ---------------------------------------------------------------------------
# BASE_POLICY (R21-R22, matriz aprobada y congelada; cambiarla => nueva version)
# ---------------------------------------------------------------------------


def _spec(severity: str, accepts: tuple, kinds: Optional[tuple], minimo: str) -> LevelSpec:
    return LevelSpec(severity=severity, accepts=accepts, accepted_kinds=kinds, min_attestation_kind=minimo)


def _att(minimo: str) -> LevelSpec:
    return _spec("required", ("attestation",), None, minimo)


def _mixto(severity: str, minimo: str) -> LevelSpec:
    return _spec(severity, ("observed", "attestation"), EXTERNAL_EVIDENCE_KINDS, minimo)


BASE_POLICY = GovernancePolicy(
    policy_id="harmessi-base",
    version=1,
    requirements=(
        PolicyRequirement(
            "accountability_risk_declaration",
            "accountability",
            {"low": _att("declared"), "medium": _att("declared"), "high": _att("anchored")},
            "Declaración humana del nivel de riesgo del modelo.",
        ),
        PolicyRequirement(
            "accountability_owner",
            "accountability",
            {"low": _att("declared"), "medium": _att("declared"), "high": _att("anchored")},
            "Responsable del modelo (rol o equipo).",
        ),
        PolicyRequirement(
            "human_oversight_process",
            "human_oversight",
            {"medium": _mixto("recommended", "declared"), "high": _mixto("required", "anchored")},
            "Proceso de supervisión humana documentado.",
        ),
        PolicyRequirement(
            "fairness_evidence",
            "fairness",
            {
                "medium": _mixto("required", "declared"),
                "high": _spec("required", ("observed",), EXTERNAL_EVIDENCE_KINDS, "declared"),
            },
            "Evidencia documental de equidad vinculada al modelo.",
        ),
        PolicyRequirement(
            "explainability_evidence",
            "explainability",
            {"medium": _mixto("recommended", "declared"), "high": _mixto("required", "anchored")},
            "Evidencia documental de explicabilidad vinculada al modelo.",
        ),
        PolicyRequirement(
            "privacy_evidence",
            "privacy",
            {
                "low": _mixto("recommended", "declared"),
                "medium": _mixto("required", "declared"),
                "high": _mixto("required", "anchored"),
            },
            "Evidencia documental de privacidad vinculada al modelo.",
        ),
        PolicyRequirement(
            "security_evidence",
            "security",
            {
                "low": _mixto("recommended", "declared"),
                "medium": _mixto("required", "declared"),
                "high": _mixto("required", "anchored"),
            },
            "Evidencia documental de seguridad vinculada al modelo.",
        ),
    ),
)

# Calculado en import (no hardcodeado); el test lo congela con un vector literal.
BASE_POLICY_SHA256 = BASE_POLICY.content_sha256()

_hallazgos_base = validate_monotonic(BASE_POLICY)
if _hallazgos_base:  # pragma: no cover - defensa de import
    raise GovPolicyError(
        CODE_NOT_MONOTONIC,
        "BASE_POLICY no es monótona: " + " | ".join(f"{h.path}: {h.detail}" for h in _hallazgos_base),
    )
del _hallazgos_base

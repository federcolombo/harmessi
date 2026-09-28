"""Contratos neutrales de datos (v0.7 Change 0, `20260922-data-contracts-core`).

Módulo solo-stdlib: declara, en memoria, un `DataContract` como árbol de objetos
inmutables que separa tres capas distintas de una expectativa de datos:

- **Estructura** (`ContractField`): nombre, familia de tipo, requerido/nullable.
- **Calidad esperada** (`Constraint`): rango, dominio, unicidad, invariantes
  declarativos y acotados -- con severidad propia (`SEVERITIES`).
- **Reglas de negocio** (`BusinessRule`): solo declarables/auditables por un
  humano, nunca evaluadas por este módulo ni por ningún código de `core.py`.

Este módulo NO observa ni evalúa ningún dato: ningún constructor acepta un
argumento que represente datos, filas, un `DataFrame`, un `profile.json` ni una
ruta de archivo. La evaluación de un `DataContract` contra una observación real
(`ds_profile`) es responsabilidad de un Change posterior
(`data-contract-validation`), que puede importar este módulo pero nunca al
revés.

`ContractVersion` y `CompatibilityPolicy` son metadata/política versionada
declarada por el autor del contrato: ninguna de las dos contiene lógica de
diff, comparación ni clasificación de compatibilidad entre versiones (eso es
del Change de integración/CLI).

Todo error de contrato de este módulo lanza `DataContractError`, nunca
`TypeError`/`KeyError` crudos.

Serialización determinista: `to_dict()`/`from_dict()` por dataclass,
`canonical_json()` y `DataContract.content_sha256()` (identidad de contenido;
el `DataContract` no lleva `generated_at` ni ningún dato de ejecución).

Política de evolución del esquema: todo campo nuevo en el `to_dict()` de un
contrato de este módulo cambia `content_sha256()` y por lo tanto REQUIERE bump
de `SCHEMA_VERSION`, mismo criterio que `tools/reporting/core.py`.

Nota de vocabulario: `SEVERITIES = ("FAIL", "WARN")` coincide, a propósito,
con los literales de texto de `dsguard.checks.STATUS_FAIL`/`STATUS_WARN` --
este módulo NO importa `dsguard` (Change 0 no produce `CheckResult`); es una
coincidencia de vocabulario documentada, no una dependencia de código.
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
# `tools/reporting/profiles/eda.py:43`).
EXTENSION_PREFIX = "x_"

TYPE_FAMILIES = ("string", "integer", "float", "boolean", "date", "datetime", "unknown")
DATASET_ROLES = ("raw_table", "feature_table", "scoring_output", "generic")
CONSTRAINT_TYPES = (
    "not_null",
    "unique",
    "allowed_values",
    "min_value",
    "max_value",
    "min_length",
    "max_length",
    "date_min",
    "date_max",
    "invariant",
)
# Mismos literales de texto que `dsguard.checks.STATUS_FAIL`/`STATUS_WARN`
# (`tools/dsguard/checks.py:14-17`); NO se importa `checks.py` -- coincidencia
# de vocabulario documentada, no dependencia de código (ver docstring del
# módulo y decisión 3 del roadmap).
SEVERITIES = ("FAIL", "WARN")
COMPAT_ACTIONS = ("block", "warn", "allow")


class DataContractError(ValueError):
    """Violación de un contrato de datos (entrada estructuralmente inválida)."""


# ---------------------------------------------------------------------------
# Helpers privados de validación / normalización
# ---------------------------------------------------------------------------

# Ids de contrato/constraint/rule/policy: seguros como nombre de archivo
# (`^[a-z0-9][a-z0-9_-]{0,63}$`, aplicado con `fullmatch`).
_PATRON_ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")

# Nombres de dispositivo reservados en Windows: un id (ya en minúscula) que
# coincida no es seguro como nombre de archivo en ese sistema.
_IDS_RESERVADOS = frozenset(
    ["con", "prn", "aux", "nul"]
    + [f"com{i}" for i in range(1, 10)]
    + [f"lpt{i}" for i in range(1, 10)]
)

# Nombre de campo (`ContractField.name`): snake_case estricto de
# pandas/Python, sin guiones, sin límite de reserva de nombres de Windows (no
# se usa como nombre de archivo).
_PATRON_NOMBRE_CAMPO = re.compile(r"[a-z][a-z0-9_]*")

# Versión semver simple: MAJOR.MINOR.PATCH, sin prefijo `v`.
_PATRON_SEMVER = re.compile(r"\d+\.\d+\.\d+")

# `constraint_type` cuyo `params["fields"]` (cuando está presente) referencia
# nombres de `ContractField` que `DataContract` debe validar que existen.
_CONSTRAINT_TYPES_CON_FIELDS_REFERENCIABLES = ("unique", "invariant")


def _validar_id(valor: Any, campo: str) -> str:
    """Valida un id (`contract_id`/`constraint_id`/`rule_id`/`policy_id`)
    contra `_PATRON_ID` y los nombres reservados de Windows."""
    if not isinstance(valor, str):
        raise DataContractError(f"{campo}: se esperaba str, se recibió {type(valor).__name__}")
    if _PATRON_ID.fullmatch(valor) is None:
        raise DataContractError(
            f"{campo}: id inválido {valor!r} (debe cumplir ^[a-z0-9][a-z0-9_-]{{0,63}}$)"
        )
    if valor in _IDS_RESERVADOS:
        raise DataContractError(
            f"{campo}: id {valor!r} es un nombre de dispositivo reservado de Windows "
            "(no es seguro como nombre de archivo)"
        )
    return valor


def _validar_nombre_campo(valor: Any, campo: str) -> str:
    """Valida `ContractField.name` contra `_PATRON_NOMBRE_CAMPO`
    (`^[a-z][a-z0-9_]*$`, snake_case sin guiones)."""
    if not isinstance(valor, str):
        raise DataContractError(f"{campo}: se esperaba str, se recibió {type(valor).__name__}")
    if _PATRON_NOMBRE_CAMPO.fullmatch(valor) is None:
        raise DataContractError(
            f"{campo}: nombre de campo inválido {valor!r} (debe cumplir ^[a-z][a-z0-9_]*$)"
        )
    return valor


def _exigir_str(valor: Any, campo: str) -> str:
    """Exige `str`; devuelve el mismo valor."""
    if not isinstance(valor, str):
        raise DataContractError(f"{campo}: se esperaba str, se recibió {type(valor).__name__}")
    return valor


def _exigir_str_no_vacio(valor: Any, campo: str) -> str:
    """Exige `str` no vacío; devuelve el mismo valor."""
    _exigir_str(valor, campo)
    if valor == "":
        raise DataContractError(f"{campo}: no puede ser vacío")
    return valor


def _exigir_bool(valor: Any, campo: str) -> bool:
    """Exige `bool` estricto (no enteros)."""
    if not isinstance(valor, bool):
        raise DataContractError(f"{campo}: se esperaba bool, se recibió {type(valor).__name__}")
    return valor


def _exigir_secuencia(valor: Any, campo: str) -> tuple:
    """`list`/`tuple` -> `tuple`; cualquier otro tipo (incluido `str`) es error."""
    if not isinstance(valor, (list, tuple)):
        raise DataContractError(f"{campo}: se esperaba list o tuple, se recibió {type(valor).__name__}")
    return tuple(valor)


def _exigir_dict(valor: Any, campo: str) -> dict:
    """Exige `dict`; devuelve el mismo objeto (sin copiar)."""
    if not isinstance(valor, dict):
        raise DataContractError(f"{campo}: se esperaba dict, se recibió {type(valor).__name__}")
    return valor


def _es_finito(valor: float) -> bool:
    """`True` sii `valor` (ya sabido `float`) es finito -- sin importar
    `math`, por decisión de diseño (ver `design.md`)."""
    return valor == valor and valor not in (float("inf"), float("-inf"))


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
            raise DataContractError(f"{ruta}: float no finito ({valor!r}) no es JSON-seguro")
        return float(valor)
    if isinstance(valor, (list, tuple)):
        return [_json_puro(item, f"{ruta}[{i}]") for i, item in enumerate(valor)]
    if isinstance(valor, dict):
        resultado: dict = {}
        for clave, item in valor.items():
            if not isinstance(clave, str):
                raise DataContractError(
                    f"{ruta}: clave no-str {clave!r} ({type(clave).__name__}) no es JSON-seguro"
                )
            resultado[clave] = _json_puro(item, f"{ruta}.{clave}")
        return resultado
    raise DataContractError(f"{ruta}: tipo {type(valor).__name__} no es JSON-seguro")


def _dict_json_puro(valor: Any, campo: str) -> dict:
    """Exige `dict` y devuelve su copia profunda normalizada a JSON puro; una
    estructura circular o demasiado profunda es `DataContractError`."""
    try:
        return _json_puro(_exigir_dict(valor, campo), campo)
    except RecursionError as exc:
        raise DataContractError(f"{campo}: estructura circular o demasiado profunda") from exc


def _validar_extensiones(valor: Any, campo: str) -> dict:
    """Copia JSON-segura de un mapa `extensions`: todas las claves de primer
    nivel deben empezar con `EXTENSION_PREFIX` (mismas reglas para
    `ContractField.extensions` y `DataContract.extensions`, R5/R10)."""
    datos = _dict_json_puro(valor, campo)
    for clave in datos:
        if not clave.startswith(EXTENSION_PREFIX):
            raise DataContractError(
                f"{campo}: clave {clave!r} no empieza con el prefijo requerido {EXTENSION_PREFIX!r}"
            )
    return datos


def _validar_constraint_type_params(constraint_type: str, params: dict) -> None:
    """Valida la FORMA de `params` (ya copiado a JSON puro) según
    `constraint_type` -- nunca evalúa nada contra datos (R6)."""
    if constraint_type == "not_null":
        return
    if constraint_type == "unique":
        if "fields" in params:
            campos = params["fields"]
            if not isinstance(campos, list):
                raise DataContractError("Constraint.params['fields']: se esperaba list")
            for i, nombre in enumerate(campos):
                if not isinstance(nombre, str) or nombre == "":
                    raise DataContractError(
                        f"Constraint.params['fields'][{i}]: se esperaba str no vacío"
                    )
        return
    if constraint_type == "allowed_values":
        valores = params.get("values")
        if not isinstance(valores, list) or len(valores) == 0:
            raise DataContractError("Constraint.params['values']: requiere lista no vacía")
        vistos: list = []
        for valor in valores:
            if isinstance(valor, (dict, list)):
                raise DataContractError(
                    "Constraint.params['values']: solo admite escalares JSON-seguros"
                )
            clave = (type(valor), valor)
            if clave in vistos:
                raise DataContractError("Constraint.params['values']: contiene duplicados")
            vistos.append(clave)
        return
    if constraint_type in ("min_value", "max_value"):
        if "value" not in params:
            raise DataContractError("Constraint.params['value']: requerido")
        valor = params["value"]
        if isinstance(valor, bool) or not isinstance(valor, (int, float)):
            raise DataContractError(
                f"Constraint.params['value']: se esperaba int o float (no bool), se recibió {valor!r}"
            )
        if isinstance(valor, float) and not _es_finito(valor):
            raise DataContractError("Constraint.params['value']: float no finito")
        return
    if constraint_type in ("min_length", "max_length"):
        if "value" not in params:
            raise DataContractError("Constraint.params['value']: requerido")
        valor = params["value"]
        if isinstance(valor, bool) or not isinstance(valor, int) or valor < 0:
            raise DataContractError(
                f"Constraint.params['value']: se esperaba int >= 0 (no bool), se recibió {valor!r}"
            )
        return
    if constraint_type in ("date_min", "date_max"):
        if "value" not in params:
            raise DataContractError("Constraint.params['value']: requerido")
        valor = params["value"]
        if not isinstance(valor, str) or valor == "":
            raise DataContractError("Constraint.params['value']: se esperaba str no vacío")
        return
    if constraint_type == "invariant":
        if "note" not in params:
            raise DataContractError("Constraint.params['note']: requerido")
        nota = params["note"]
        if not isinstance(nota, str) or nota == "":
            raise DataContractError("Constraint.params['note']: se esperaba str no vacío")
        if "fields" in params:
            campos = params["fields"]
            if not isinstance(campos, list):
                raise DataContractError("Constraint.params['fields']: se esperaba list")
            for i, nombre in enumerate(campos):
                if not isinstance(nombre, str):
                    raise DataContractError(f"Constraint.params['fields'][{i}]: se esperaba str")
        return
    # Inalcanzable si `constraint_type` ya se validó contra `CONSTRAINT_TYPES`
    # antes de llamar a esta función; defensivo de todas formas.
    raise DataContractError(f"Constraint.constraint_type: {constraint_type!r} fuera de {CONSTRAINT_TYPES}")


def _tupla_de_tipo(valor: Any, tipo: type, campo: str) -> tuple:
    """`list`/`tuple` cuyos elementos son todos instancias de `tipo`, como `tuple`."""
    elementos = _exigir_secuencia(valor, campo)
    for i, elemento in enumerate(elementos):
        if not isinstance(elemento, tipo):
            raise DataContractError(
                f"{campo}[{i}]: se esperaba {tipo.__name__}, se recibió {type(elemento).__name__}"
            )
    return elementos


def _requeridos(datos: Any, nombres: tuple, contrato: str) -> None:
    """Exige que `datos` sea `dict` y contenga todas las claves de `nombres`."""
    if not isinstance(datos, dict):
        raise DataContractError(f"{contrato}.from_dict: se esperaba dict, se recibió {type(datos).__name__}")
    faltantes = [n for n in nombres if n not in datos]
    if faltantes:
        raise DataContractError(f"{contrato}.from_dict: faltan campos requeridos {faltantes}")


def _seleccionar(datos: dict, nombres: tuple) -> dict:
    """Subconjunto de `datos` limitado a `nombres` (ignora claves desconocidas)."""
    return {n: datos[n] for n in nombres if n in datos}


def canonical_json(obj: Any) -> str:
    """JSON canónico: claves ordenadas, sin espacios, sin escapar no-ASCII,
    sin `NaN`/`Infinity`. Un fallo de serialización lanza `DataContractError`."""
    try:
        return json.dumps(
            obj,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError, RecursionError) as exc:
        raise DataContractError(f"canonical_json: objeto no serializable ({exc})") from exc


# ---------------------------------------------------------------------------
# ContractField (capa schema/structure)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ContractField:
    """Un campo declarado del dataset: nombre, familia de tipo, requerido y
    nullable. No declara rango/dominio/unicidad -- eso es `Constraint`."""

    name: str
    type_family: str
    required: bool = True
    nullable: bool = True
    description: str = ""
    extensions: dict = _campo_dataclass(default_factory=dict)

    def __post_init__(self) -> None:
        _validar_nombre_campo(self.name, "ContractField.name")
        if self.type_family not in TYPE_FAMILIES:
            raise DataContractError(
                f"ContractField.type_family: {self.type_family!r} fuera de {TYPE_FAMILIES}"
            )
        _exigir_bool(self.required, "ContractField.required")
        _exigir_bool(self.nullable, "ContractField.nullable")
        _exigir_str(self.description, "ContractField.description")
        extensiones = _validar_extensiones(self.extensions, "ContractField.extensions")
        object.__setattr__(self, "extensions", extensiones)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "type_family": self.type_family,
            "required": self.required,
            "nullable": self.nullable,
            "description": self.description,
            "extensions": _json_puro(self.extensions, "ContractField.extensions"),
        }

    @classmethod
    def from_dict(cls, datos: dict) -> "ContractField":
        _requeridos(datos, ("name", "type_family"), "ContractField")
        return cls(
            **_seleccionar(
                datos,
                ("name", "type_family", "required", "nullable", "description", "extensions"),
            )
        )


# ---------------------------------------------------------------------------
# Constraint (capa quality expectations -- declara severidad, no evalúa nada)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Constraint:
    """Una expectativa de calidad declarada sobre el dataset o un campo
    concreto: forma validada en construcción, NUNCA evaluada contra datos
    (eso es responsabilidad de un Change posterior)."""

    constraint_id: str
    constraint_type: str
    field: Optional[str] = None
    severity: str = "FAIL"
    params: dict = _campo_dataclass(default_factory=dict)
    description: str = ""

    def __post_init__(self) -> None:
        _validar_id(self.constraint_id, "constraint_id")
        if self.constraint_type not in CONSTRAINT_TYPES:
            raise DataContractError(
                f"Constraint.constraint_type: {self.constraint_type!r} fuera de {CONSTRAINT_TYPES}"
            )
        if self.field is not None:
            _exigir_str_no_vacio(self.field, "Constraint.field")
        if self.severity not in SEVERITIES:
            raise DataContractError(f"Constraint.severity: {self.severity!r} fuera de {SEVERITIES}")
        _exigir_str(self.description, "Constraint.description")
        params_norm = _dict_json_puro(self.params, "Constraint.params")
        _validar_constraint_type_params(self.constraint_type, params_norm)
        object.__setattr__(self, "params", params_norm)

    def to_dict(self) -> dict:
        return {
            "constraint_id": self.constraint_id,
            "constraint_type": self.constraint_type,
            "field": self.field,
            "severity": self.severity,
            "params": _json_puro(self.params, "Constraint.params"),
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, datos: dict) -> "Constraint":
        _requeridos(datos, ("constraint_id", "constraint_type"), "Constraint")
        return cls(
            **_seleccionar(
                datos,
                ("constraint_id", "constraint_type", "field", "severity", "params", "description"),
            )
        )


# ---------------------------------------------------------------------------
# BusinessRule (capa semantic business rules -- solo declarable)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BusinessRule:
    """Una regla de negocio: solo declarable y auditable por un humano. Este
    módulo NO define ninguna función que la evalúe, ejecute ni compare contra
    datos ni contra ningún otro objeto."""

    rule_id: str
    statement: str
    rationale: str = ""
    reference: Optional[str] = None

    def __post_init__(self) -> None:
        _validar_id(self.rule_id, "rule_id")
        _exigir_str_no_vacio(self.statement, "BusinessRule.statement")
        _exigir_str(self.rationale, "BusinessRule.rationale")
        if self.reference is not None:
            _exigir_str_no_vacio(self.reference, "BusinessRule.reference")

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "statement": self.statement,
            "rationale": self.rationale,
            "reference": self.reference,
        }

    @classmethod
    def from_dict(cls, datos: dict) -> "BusinessRule":
        _requeridos(datos, ("rule_id", "statement"), "BusinessRule")
        return cls(**_seleccionar(datos, ("rule_id", "statement", "rationale", "reference")))


# ---------------------------------------------------------------------------
# ContractVersion (metadata versionada -- sin lógica de diff)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ContractVersion:
    """Metadata de versión del contrato de negocio (linaje declarado por el
    autor, no calculado): identifica una versión y enlaza opcionalmente con la
    anterior por texto. Sin `compare`/`diff`/`classify` -- eso es de un Change
    posterior que clasifica compatibilidad entre dos `DataContract`."""

    version: str
    summary: str = ""
    previous_version: Optional[str] = None

    def __post_init__(self) -> None:
        if not isinstance(self.version, str) or _PATRON_SEMVER.fullmatch(self.version) is None:
            raise DataContractError(
                f"ContractVersion.version: {self.version!r} no cumple el patrón semver "
                "simple ^\\d+\\.\\d+\\.\\d+$"
            )
        _exigir_str(self.summary, "ContractVersion.summary")
        if self.previous_version is not None:
            if (
                not isinstance(self.previous_version, str)
                or _PATRON_SEMVER.fullmatch(self.previous_version) is None
            ):
                raise DataContractError(
                    f"ContractVersion.previous_version: {self.previous_version!r} no cumple el "
                    "patrón semver simple ^\\d+\\.\\d+\\.\\d+$"
                )

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "summary": self.summary,
            "previous_version": self.previous_version,
        }

    @classmethod
    def from_dict(cls, datos: dict) -> "ContractVersion":
        _requeridos(datos, ("version",), "ContractVersion")
        return cls(**_seleccionar(datos, ("version", "summary", "previous_version")))


# ---------------------------------------------------------------------------
# CompatibilityPolicy (declaración de política -- sin clasificación)
# ---------------------------------------------------------------------------

_CAMPOS_ACCION_COMPATIBILIDAD = (
    "on_removed_field",
    "on_required_field_added",
    "on_type_change",
    "on_constraint_tightening",
    "on_constraint_loosening",
    "on_unknown_change",
)


@dataclass(frozen=True)
class CompatibilityPolicy:
    """Declara qué acción tomar (`COMPAT_ACTIONS`) ante cada categoría de
    cambio entre versiones de un contrato. Los 6 campos son requeridos (sin
    default): este módulo NO define ninguna función que compare dos
    `DataContract` y decida a qué categoría pertenece un cambio real -- eso es
    responsabilidad de un Change posterior."""

    policy_id: str
    on_removed_field: str
    on_required_field_added: str
    on_type_change: str
    on_constraint_tightening: str
    on_constraint_loosening: str
    on_unknown_change: str

    def __post_init__(self) -> None:
        _validar_id(self.policy_id, "policy_id")
        for campo in _CAMPOS_ACCION_COMPATIBILIDAD:
            valor = getattr(self, campo)
            if valor not in COMPAT_ACTIONS:
                raise DataContractError(
                    f"CompatibilityPolicy.{campo}: {valor!r} fuera de {COMPAT_ACTIONS}"
                )

    def to_dict(self) -> dict:
        return {
            "policy_id": self.policy_id,
            "on_removed_field": self.on_removed_field,
            "on_required_field_added": self.on_required_field_added,
            "on_type_change": self.on_type_change,
            "on_constraint_tightening": self.on_constraint_tightening,
            "on_constraint_loosening": self.on_constraint_loosening,
            "on_unknown_change": self.on_unknown_change,
        }

    @classmethod
    def from_dict(cls, datos: dict) -> "CompatibilityPolicy":
        _requeridos(datos, ("policy_id",) + _CAMPOS_ACCION_COMPATIBILIDAD, "CompatibilityPolicy")
        return cls(**_seleccionar(datos, ("policy_id",) + _CAMPOS_ACCION_COMPATIBILIDAD))


# ---------------------------------------------------------------------------
# DataContract (raíz)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DataContract:
    """Raíz del árbol: declara estructura (`fields`), calidad esperada
    (`constraints`), reglas de negocio (`business_rules`), keys y política de
    compatibilidad opcional. No observa ni evalúa ningún dato. Sin
    `generated_at` ni ningún dato de ejecución: `content_sha256()` identifica
    contenido, no una corrida."""

    contract_id: str
    version: ContractVersion
    dataset_role: str
    fields: tuple
    constraints: tuple = ()
    business_rules: tuple = ()
    keys: tuple = ()
    compatibility_policy: Optional[CompatibilityPolicy] = None
    description: str = ""
    extensions: dict = _campo_dataclass(default_factory=dict)
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _validar_id(self.contract_id, "contract_id")
        if not isinstance(self.version, ContractVersion):
            raise DataContractError(
                f"DataContract.version: se esperaba ContractVersion, se recibió {type(self.version).__name__}"
            )
        if self.dataset_role not in DATASET_ROLES:
            raise DataContractError(
                f"DataContract.dataset_role: {self.dataset_role!r} fuera de {DATASET_ROLES}"
            )

        campos = _tupla_de_tipo(self.fields, ContractField, "DataContract.fields")
        if not campos:
            raise DataContractError("DataContract.fields: no puede ser vacía")
        nombres_campo: set = set()
        for campo in campos:
            if campo.name in nombres_campo:
                raise DataContractError(f"DataContract.fields: nombre de campo duplicado {campo.name!r}")
            nombres_campo.add(campo.name)

        constraints = _tupla_de_tipo(self.constraints, Constraint, "DataContract.constraints")
        ids_constraint: set = set()
        for restriccion in constraints:
            if restriccion.constraint_id in ids_constraint:
                raise DataContractError(
                    f"DataContract.constraints: constraint_id duplicado {restriccion.constraint_id!r}"
                )
            ids_constraint.add(restriccion.constraint_id)
            if restriccion.field is not None and restriccion.field not in nombres_campo:
                raise DataContractError(
                    f"DataContract.constraints: Constraint.field {restriccion.field!r} no existe "
                    "entre los fields del contrato"
                )
            if (
                restriccion.constraint_type in _CONSTRAINT_TYPES_CON_FIELDS_REFERENCIABLES
                and "fields" in restriccion.params
            ):
                for nombre in restriccion.params["fields"]:
                    if nombre not in nombres_campo:
                        raise DataContractError(
                            f"DataContract.constraints: params['fields'] referencia el campo "
                            f"inexistente {nombre!r}"
                        )

        reglas = _tupla_de_tipo(self.business_rules, BusinessRule, "DataContract.business_rules")
        ids_regla: set = set()
        for regla in reglas:
            if regla.rule_id in ids_regla:
                raise DataContractError(f"DataContract.business_rules: rule_id duplicado {regla.rule_id!r}")
            ids_regla.add(regla.rule_id)

        keys = _exigir_secuencia(self.keys, "DataContract.keys")
        vistos_keys: set = set()
        for clave in keys:
            if not isinstance(clave, str) or clave not in nombres_campo:
                raise DataContractError(
                    f"DataContract.keys: {clave!r} no existe entre los fields del contrato"
                )
            if clave in vistos_keys:
                raise DataContractError(f"DataContract.keys: elemento duplicado {clave!r}")
            vistos_keys.add(clave)

        if self.compatibility_policy is not None and not isinstance(
            self.compatibility_policy, CompatibilityPolicy
        ):
            raise DataContractError(
                "DataContract.compatibility_policy: se esperaba CompatibilityPolicy o None, se "
                f"recibió {type(self.compatibility_policy).__name__}"
            )

        _exigir_str(self.description, "DataContract.description")
        extensiones = _validar_extensiones(self.extensions, "DataContract.extensions")

        if (
            isinstance(self.schema_version, bool)
            or not isinstance(self.schema_version, int)
            or self.schema_version != SCHEMA_VERSION
        ):
            raise DataContractError(
                f"DataContract.schema_version: se esperaba {SCHEMA_VERSION}, se recibió "
                f"{self.schema_version!r}"
            )

        object.__setattr__(self, "fields", campos)
        object.__setattr__(self, "constraints", constraints)
        object.__setattr__(self, "business_rules", reglas)
        object.__setattr__(self, "keys", keys)
        object.__setattr__(self, "extensions", extensiones)

    # -- accesores (nunca lanzan) -------------------------------------------

    def get_field(self, name: Any) -> Optional[ContractField]:
        for campo in self.fields:
            if campo.name == name:
                return campo
        return None

    def constraints_for(self, field_name: Any) -> tuple:
        """Constraints con `field == field_name` (o de alcance dataset --
        `field is None` -- si se pide `constraints_for(None)`)."""
        return tuple(c for c in self.constraints if c.field == field_name)

    def get_constraint(self, constraint_id: Any) -> Optional[Constraint]:
        for restriccion in self.constraints:
            if restriccion.constraint_id == constraint_id:
                return restriccion
        return None

    def get_business_rule(self, rule_id: Any) -> Optional[BusinessRule]:
        for regla in self.business_rules:
            if regla.rule_id == rule_id:
                return regla
        return None

    # -- serialización --------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "contract_id": self.contract_id,
            "version": self.version.to_dict(),
            "dataset_role": self.dataset_role,
            "fields": [campo.to_dict() for campo in self.fields],
            "constraints": [restriccion.to_dict() for restriccion in self.constraints],
            "business_rules": [regla.to_dict() for regla in self.business_rules],
            "keys": list(self.keys),
            "compatibility_policy": (
                None if self.compatibility_policy is None else self.compatibility_policy.to_dict()
            ),
            "description": self.description,
            "extensions": _json_puro(self.extensions, "DataContract.extensions"),
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, datos: dict) -> "DataContract":
        _requeridos(
            datos,
            ("contract_id", "version", "dataset_role", "fields", "schema_version"),
            "DataContract",
        )
        kwargs = _seleccionar(
            datos,
            (
                "contract_id",
                "dataset_role",
                "description",
                "extensions",
                "schema_version",
            ),
        )
        kwargs["version"] = ContractVersion.from_dict(datos["version"])
        kwargs["fields"] = tuple(
            ContractField.from_dict(item)
            for item in _exigir_secuencia(datos["fields"], "DataContract.from_dict.fields")
        )
        if "constraints" in datos:
            kwargs["constraints"] = tuple(
                Constraint.from_dict(item)
                for item in _exigir_secuencia(datos["constraints"], "DataContract.from_dict.constraints")
            )
        if "business_rules" in datos:
            kwargs["business_rules"] = tuple(
                BusinessRule.from_dict(item)
                for item in _exigir_secuencia(
                    datos["business_rules"], "DataContract.from_dict.business_rules"
                )
            )
        if "keys" in datos:
            kwargs["keys"] = tuple(_exigir_secuencia(datos["keys"], "DataContract.from_dict.keys"))
        if "compatibility_policy" in datos and datos["compatibility_policy"] is not None:
            kwargs["compatibility_policy"] = CompatibilityPolicy.from_dict(datos["compatibility_policy"])
        return cls(**kwargs)

    def content_sha256(self) -> str:
        """sha256 (hex) del JSON canónico de `to_dict()` en UTF-8."""
        return hashlib.sha256(canonical_json(self.to_dict()).encode("utf-8")).hexdigest()

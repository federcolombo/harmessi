"""Clasificación determinista de compatibilidad entre dos versiones de un
`DataContract` (v0.7 Change 4, `20260922-quality-integration-and-cli`).

Extensión aditiva de `tools/datacontracts` ya anticipada por Change 0
(`openspec/changes/20260922-data-contracts-core/design.md:253-264`): única
excepción a "Changes 0-3 son inmutables" de este Change (ver `design.md`,
decisión 2).

Función pública única: `classify_contract_change(old, new, policy=None) ->
list[dsguard.checks.CheckResult]`. Pura (sin I/O), determinista (mismo par de
`DataContract` + misma `CompatibilityPolicy` -> misma lista, mismo orden fijo:
1) campos, en el orden de `new.fields` (más los eliminados, en el orden de
`old.fields`); 2) constraints, en el orden de `new.constraints` (más las
eliminadas, en el orden de `old.constraints`); 3) `business_rules`, en el
orden de `new.business_rules` (más las eliminadas, en el orden de
`old.business_rules`); 4) `dataset_role`; 5) `keys`; 6)
`compatibility_policy.policy_id`).

Sin `policy`: TODOS los findings tienen `status = checks.STATUS_NA` (R8):
clasificado, nunca evaluado -- este módulo NUNCA inventa un `PASS`/`FAIL`/
`WARN` sin una `CompatibilityPolicy` declarada. Con `policy`: el `status` de
cada finding mapea `CompatibilityPolicy.COMPAT_ACTIONS` (`block`/`warn`/
`allow`) a `STATUS_FAIL`/`STATUS_WARN`/`STATUS_PASS`, salvo `additive
compatible`, que SIEMPRE es `STATUS_PASS` si hay política (nunca bloquea, no
tiene campo de política propio).

Honestidad sobre qué es determinista y qué no (ver `design.md`, decisión 3):
lo que este módulo puede evidenciar sin ambigüedad es la forma sintáctica
declarada de `DataContract` (presencia/ausencia de campos, `type_family`,
`required`, `nullable`, parámetros de una `Constraint` EMPAREJADA por
`constraint_id` idéntico). Todo lo que dependa de un juicio semántico
(renames, `BusinessRule`, `invariant` como texto libre, cambios de `keys`,
`constraint_id` distintos sobre el mismo campo) cae SIEMPRE en `unknown /
needs review` -- nunca inferido por ningún otro camino.

Frontera de imports (R6 de `spec.md`, verificada por
`tools/tests/test_v07_evolution_neutrality.py`): stdlib (`__future__`,
`dataclasses`, `typing`) + `dsguard.checks` + `tools.datacontracts.core`
(sibling). NUNCA `ds_profile`, `dsimpact`, `tools.modelquality`,
`tools.qualityevidence`, `tools.reporting`, pandas, numpy.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

_TOOLS_DIR = Path(__file__).resolve().parents[1]
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from dsguard import checks  # noqa: E402

from . import core as datacontracts_core  # noqa: E402

# --- Códigos (R19 de spec.md) ------------------------------------------------

CODE_ADDITIVE_COMPATIBLE = "CONTRACT-EVOLUTION-ADDITIVE-COMPATIBLE"
CODE_REMOVAL = "CONTRACT-EVOLUTION-REMOVAL"
CODE_REQUIRED_FIELD_ADDITION = "CONTRACT-EVOLUTION-REQUIRED-FIELD-ADDITION"
CODE_TYPE_CHANGE = "CONTRACT-EVOLUTION-TYPE-CHANGE"
CODE_CONSTRAINT_TIGHTENING = "CONTRACT-EVOLUTION-CONSTRAINT-TIGHTENING"
CODE_CONSTRAINT_LOOSENING = "CONTRACT-EVOLUTION-CONSTRAINT-LOOSENING"
CODE_UNKNOWN_NEEDS_REVIEW = "CONTRACT-EVOLUTION-UNKNOWN-NEEDS-REVIEW"
CODE_EXCEPTION = "CONTRACT-EVOLUTION-EXCEPCION"

CODES = (
    CODE_ADDITIVE_COMPATIBLE,
    CODE_REMOVAL,
    CODE_REQUIRED_FIELD_ADDITION,
    CODE_TYPE_CHANGE,
    CODE_CONSTRAINT_TIGHTENING,
    CODE_CONSTRAINT_LOOSENING,
    CODE_UNKNOWN_NEEDS_REVIEW,
)

# --- Categorías internas (nunca expuestas como texto suelto fuera de este módulo) --

_CAT_ADDITIVE = "additive_compatible"
_CAT_REMOVAL = "removal"
_CAT_REQUIRED_ADDITION = "required_field_addition"
_CAT_TYPE_CHANGE = "type_change"
_CAT_TIGHTENING = "constraint_tightening"
_CAT_LOOSENING = "constraint_loosening"
_CAT_UNKNOWN = "unknown_needs_review"

_CATEGORIA_A_CODIGO = {
    _CAT_ADDITIVE: CODE_ADDITIVE_COMPATIBLE,
    _CAT_REMOVAL: CODE_REMOVAL,
    _CAT_REQUIRED_ADDITION: CODE_REQUIRED_FIELD_ADDITION,
    _CAT_TYPE_CHANGE: CODE_TYPE_CHANGE,
    _CAT_TIGHTENING: CODE_CONSTRAINT_TIGHTENING,
    _CAT_LOOSENING: CODE_CONSTRAINT_LOOSENING,
    _CAT_UNKNOWN: CODE_UNKNOWN_NEEDS_REVIEW,
}

_CONSTRAINT_TYPES_ASCENDENTE_TIGHTENING = ("min_value", "min_length", "date_min")
_CONSTRAINT_TYPES_ASCENDENTE_LOOSENING = ("max_value", "max_length", "date_max")


# ---------------------------------------------------------------------------
# Helpers privados: comparación de campos (R7, primer bloque)
# ---------------------------------------------------------------------------


def _campos_por_nombre(contract: "datacontracts_core.DataContract") -> dict:
    return {campo.name: campo for campo in contract.fields}


def _comparar_campos(
    old: "datacontracts_core.DataContract", new: "datacontracts_core.DataContract"
) -> tuple:
    """`(eventos, campos_cubribles)`. `eventos` = `(categoria, subject,
    mensaje)` para campos, en el orden fijo: `new.fields`
    (agregados/persistentes) + `old.fields` (solo eliminados). `campos_cubribles`
    = nombres de campo GENUINAMENTE nuevos (ausentes en `old`) o GENUINAMENTE
    eliminados (ausentes en `new`) -- R7: la supresión del finding de una
    constraint solo aplica cuando el campo entero aparece/desaparece, NUNCA
    cuando un campo que PERSISTE en ambas versiones solo cambia su flag
    `required` (ese caso sigue clasificándose `required-field-addition` a
    nivel de campo, pero no oculta constraints de ese mismo campo -- decisión
    del Lead sobre la ambigüedad de "campo nuevo" en R7 de `spec.md`)."""
    eventos: list = []
    campos_cubribles: set = set()
    old_campos = _campos_por_nombre(old)
    new_campos = _campos_por_nombre(new)

    for campo_nuevo in new.fields:
        nombre = campo_nuevo.name
        campo_viejo = old_campos.get(nombre)
        if campo_viejo is None:
            campos_cubribles.add(nombre)
            if campo_nuevo.required:
                eventos.append(
                    (
                        _CAT_REQUIRED_ADDITION,
                        nombre,
                        f"Campo nuevo requerido {nombre!r} (type_family={campo_nuevo.type_family!r}).",
                    )
                )
            else:
                eventos.append(
                    (
                        _CAT_ADDITIVE,
                        nombre,
                        f"Campo nuevo opcional {nombre!r} (type_family={campo_nuevo.type_family!r}).",
                    )
                )
            continue

        # Presente en ambas versiones.
        if campo_viejo.type_family != campo_nuevo.type_family:
            dimensiones = [
                f"type_family: {campo_viejo.type_family!r} -> {campo_nuevo.type_family!r}"
            ]
            if campo_viejo.required != campo_nuevo.required:
                dimensiones.append(f"required: {campo_viejo.required!r} -> {campo_nuevo.required!r}")
            if campo_viejo.nullable != campo_nuevo.nullable:
                dimensiones.append(f"nullable: {campo_viejo.nullable!r} -> {campo_nuevo.nullable!r}")
            eventos.append(
                (_CAT_TYPE_CHANGE, nombre, f"Campo {nombre!r}: " + "; ".join(dimensiones) + ".")
            )
            continue

        if campo_viejo.required != campo_nuevo.required:
            if not campo_viejo.required and campo_nuevo.required:
                eventos.append(
                    (
                        _CAT_REQUIRED_ADDITION,
                        nombre,
                        f"Campo {nombre!r} pasa de opcional a requerido "
                        f"(required: {campo_viejo.required!r} -> {campo_nuevo.required!r}).",
                    )
                )
            else:
                eventos.append(
                    (
                        _CAT_LOOSENING,
                        nombre,
                        f"Campo {nombre!r} pasa de requerido a opcional "
                        f"(required: {campo_viejo.required!r} -> {campo_nuevo.required!r}).",
                    )
                )
            continue

        if campo_viejo.nullable != campo_nuevo.nullable:
            if not campo_viejo.nullable and campo_nuevo.nullable:
                eventos.append(
                    (
                        _CAT_LOOSENING,
                        nombre,
                        f"Campo {nombre!r} pasa a admitir nulos "
                        f"(nullable: {campo_viejo.nullable!r} -> {campo_nuevo.nullable!r}).",
                    )
                )
            else:
                eventos.append(
                    (
                        _CAT_TIGHTENING,
                        nombre,
                        f"Campo {nombre!r} deja de admitir nulos "
                        f"(nullable: {campo_viejo.nullable!r} -> {campo_nuevo.nullable!r}).",
                    )
                )

    for campo_viejo in old.fields:
        nombre = campo_viejo.name
        if nombre not in new_campos:
            campos_cubribles.add(nombre)
            eventos.append((_CAT_REMOVAL, nombre, f"Campo eliminado {nombre!r} (ya no está en new)."))

    return eventos, campos_cubribles


# ---------------------------------------------------------------------------
# Helpers privados: comparación de constraints (R7, segundo bloque)
# ---------------------------------------------------------------------------


def _constraints_por_id(contract: "datacontracts_core.DataContract") -> dict:
    return {c.constraint_id: c for c in contract.constraints}


def _campo_cubierto(campo: Optional[str], campos_cubribles: set) -> bool:
    if campo is None:
        return False
    return campo in campos_cubribles


def _comparar_params_constraint(constraint_id: str, tipo: str, params_viejo: dict, params_nuevo: dict) -> Optional[tuple]:
    """Evento `(categoria, subject, mensaje)` (o `None` si no hay cambio de
    `params` comparable) para dos constraints con el MISMO `constraint_type`."""
    if tipo in _CONSTRAINT_TYPES_ASCENDENTE_TIGHTENING or tipo in _CONSTRAINT_TYPES_ASCENDENTE_LOOSENING:
        valor_viejo = params_viejo.get("value")
        valor_nuevo = params_nuevo.get("value")
        if valor_viejo == valor_nuevo:
            return None
        if tipo in _CONSTRAINT_TYPES_ASCENDENTE_TIGHTENING:
            categoria = _CAT_TIGHTENING if valor_nuevo > valor_viejo else _CAT_LOOSENING
        else:
            categoria = _CAT_LOOSENING if valor_nuevo > valor_viejo else _CAT_TIGHTENING
        return (
            categoria,
            constraint_id,
            f"Constraint {constraint_id!r} ({tipo}): value {valor_viejo!r} -> {valor_nuevo!r}.",
        )

    if tipo == "allowed_values":
        viejo_valores = set(params_viejo.get("values", []))
        nuevo_valores = set(params_nuevo.get("values", []))
        if viejo_valores == nuevo_valores:
            return None
        if nuevo_valores < viejo_valores:
            return (
                _CAT_TIGHTENING,
                constraint_id,
                f"Constraint {constraint_id!r} (allowed_values): {sorted(map(str, viejo_valores))} -> "
                f"{sorted(map(str, nuevo_valores))} (subconjunto propio).",
            )
        if nuevo_valores > viejo_valores:
            return (
                _CAT_LOOSENING,
                constraint_id,
                f"Constraint {constraint_id!r} (allowed_values): {sorted(map(str, viejo_valores))} -> "
                f"{sorted(map(str, nuevo_valores))} (superconjunto propio).",
            )
        return (
            _CAT_UNKNOWN,
            constraint_id,
            f"Constraint {constraint_id!r} (allowed_values): conjuntos distintos sin relación de "
            f"subconjunto ({sorted(map(str, viejo_valores))} vs {sorted(map(str, nuevo_valores))}).",
        )

    if tipo in ("not_null", "unique"):
        return None

    if tipo == "invariant":
        nota_vieja = params_viejo.get("note")
        nota_nueva = params_nuevo.get("note")
        if nota_vieja != nota_nueva:
            return (
                _CAT_UNKNOWN,
                constraint_id,
                f"Constraint {constraint_id!r} (invariant): texto libre modificado "
                f"({nota_vieja!r} -> {nota_nueva!r}), no evaluable de forma determinista.",
            )
        return None

    # Inalcanzable si `constraint_type` ya fue validado por `core.py`.
    return None


def _comparar_severidad_constraint(constraint_id: str, tipo: str, severidad_vieja: str, severidad_nueva: str) -> Optional[tuple]:
    if severidad_vieja == severidad_nueva:
        return None
    if severidad_vieja == "WARN" and severidad_nueva == "FAIL":
        categoria = _CAT_TIGHTENING
    else:
        categoria = _CAT_LOOSENING
    return (
        categoria,
        constraint_id,
        f"Constraint {constraint_id!r} ({tipo}): severity {severidad_vieja!r} -> {severidad_nueva!r}.",
    )


def _comparar_constraints(
    old: "datacontracts_core.DataContract",
    new: "datacontracts_core.DataContract",
    campos_cubribles: set,
) -> list:
    """Eventos `(categoria, subject, mensaje)` para constraints, en el orden
    fijo: `new.constraints` (nuevas/persistentes) + `old.constraints` (solo
    eliminadas)."""
    eventos: list = []
    old_por_id = _constraints_por_id(old)
    new_por_id = _constraints_por_id(new)

    for c_nuevo in new.constraints:
        cid = c_nuevo.constraint_id
        if _campo_cubierto(c_nuevo.field, campos_cubribles):
            continue
        c_viejo = old_por_id.get(cid)
        if c_viejo is None:
            eventos.append(
                (_CAT_TIGHTENING, cid, f"Constraint nueva {cid!r} ({c_nuevo.constraint_type}): regla agregada.")
            )
            continue
        if c_viejo.constraint_type != c_nuevo.constraint_type:
            eventos.append(
                (
                    _CAT_UNKNOWN,
                    cid,
                    f"Constraint {cid!r}: constraint_type redefinido "
                    f"({c_viejo.constraint_type!r} -> {c_nuevo.constraint_type!r}), no comparable.",
                )
            )
            continue
        evento_params = _comparar_params_constraint(cid, c_nuevo.constraint_type, c_viejo.params, c_nuevo.params)
        if evento_params is not None:
            eventos.append(evento_params)
        evento_severidad = _comparar_severidad_constraint(cid, c_nuevo.constraint_type, c_viejo.severity, c_nuevo.severity)
        if evento_severidad is not None:
            eventos.append(evento_severidad)

    for c_viejo in old.constraints:
        cid = c_viejo.constraint_id
        if cid in new_por_id:
            continue
        if _campo_cubierto(c_viejo.field, campos_cubribles):
            continue
        eventos.append(
            (_CAT_LOOSENING, cid, f"Constraint eliminada {cid!r} ({c_viejo.constraint_type}): regla eliminada.")
        )

    return eventos


# ---------------------------------------------------------------------------
# Helpers privados: siempre unknown/needs review (R7, tercer bloque)
# ---------------------------------------------------------------------------


def _comparar_business_rules(
    old: "datacontracts_core.DataContract", new: "datacontracts_core.DataContract"
) -> list:
    """Cualquier `BusinessRule` agregada/eliminada/modificada: siempre
    `unknown / needs review`, sin excepción (declarativas, nunca evaluadas)."""
    eventos: list = []
    old_por_id = {r.rule_id: r for r in old.business_rules}
    new_por_id = {r.rule_id: r for r in new.business_rules}

    for regla_nueva in new.business_rules:
        rid = regla_nueva.rule_id
        regla_vieja = old_por_id.get(rid)
        if regla_vieja is None:
            eventos.append((_CAT_UNKNOWN, rid, f"BusinessRule nueva {rid!r}: requiere revisión humana."))
        elif (
            regla_vieja.statement != regla_nueva.statement
            or regla_vieja.rationale != regla_nueva.rationale
            or regla_vieja.reference != regla_nueva.reference
        ):
            eventos.append((_CAT_UNKNOWN, rid, f"BusinessRule {rid!r} modificada: requiere revisión humana."))

    for regla_vieja in old.business_rules:
        rid = regla_vieja.rule_id
        if rid not in new_por_id:
            eventos.append((_CAT_UNKNOWN, rid, f"BusinessRule eliminada {rid!r}: requiere revisión humana."))

    return eventos


def _comparar_estructurales(
    old: "datacontracts_core.DataContract", new: "datacontracts_core.DataContract"
) -> list:
    """`dataset_role`/`keys`/`compatibility_policy.policy_id`: siempre
    `unknown / needs review` si difieren, sin excepción."""
    eventos: list = []
    if old.dataset_role != new.dataset_role:
        eventos.append(
            (
                _CAT_UNKNOWN,
                "dataset_role",
                f"dataset_role: {old.dataset_role!r} -> {new.dataset_role!r}.",
            )
        )
    if tuple(old.keys) != tuple(new.keys):
        eventos.append(
            (_CAT_UNKNOWN, "keys", f"keys: {list(old.keys)!r} -> {list(new.keys)!r}.")
        )
    id_viejo = old.compatibility_policy.policy_id if old.compatibility_policy is not None else None
    id_nuevo = new.compatibility_policy.policy_id if new.compatibility_policy is not None else None
    if id_viejo != id_nuevo:
        eventos.append(
            (
                _CAT_UNKNOWN,
                "compatibility_policy",
                f"compatibility_policy.policy_id: {id_viejo!r} -> {id_nuevo!r}.",
            )
        )
    return eventos


# ---------------------------------------------------------------------------
# Mapeo de status vía CompatibilityPolicy (R8)
# ---------------------------------------------------------------------------

_ACCION_A_STATUS = {
    "block": checks.STATUS_FAIL,
    "warn": checks.STATUS_WARN,
    "allow": checks.STATUS_PASS,
}

_CATEGORIA_A_CAMPO_POLICY = {
    _CAT_REMOVAL: "on_removed_field",
    _CAT_REQUIRED_ADDITION: "on_required_field_added",
    _CAT_TYPE_CHANGE: "on_type_change",
    _CAT_TIGHTENING: "on_constraint_tightening",
    _CAT_LOOSENING: "on_constraint_loosening",
    _CAT_UNKNOWN: "on_unknown_change",
}


def _status_para_evento(categoria: str, policy: Optional["datacontracts_core.CompatibilityPolicy"]) -> str:
    if policy is None:
        return checks.STATUS_NA
    if categoria == _CAT_ADDITIVE:
        return checks.STATUS_PASS
    campo_policy = _CATEGORIA_A_CAMPO_POLICY[categoria]
    accion = getattr(policy, campo_policy)
    return _ACCION_A_STATUS[accion]


def _evento_a_check_result(
    evento: tuple, policy: Optional["datacontracts_core.CompatibilityPolicy"]
) -> checks.CheckResult:
    categoria, subject, mensaje = evento
    status = _status_para_evento(categoria, policy)
    codigo = _CATEGORIA_A_CODIGO[categoria]
    return checks.CheckResult(status=status, code=codigo, message=mensaje, subject=subject)


# ---------------------------------------------------------------------------
# Función pública (R6/R7/R8)
# ---------------------------------------------------------------------------


def classify_contract_change(
    old: "datacontracts_core.DataContract",
    new: "datacontracts_core.DataContract",
    policy: Optional["datacontracts_core.CompatibilityPolicy"] = None,
) -> list:
    """Compara `old`/`new` (`DataContract`) campo por campo y constraint por
    constraint (emparejadas SOLO por `constraint_id` idéntico), devolviendo
    `list[dsguard.checks.CheckResult]` en el orden fijo documentado en el
    docstring del módulo. Pura, sin I/O, determinista. Una excepción
    inesperada al clasificar un evento puntual produce
    `CheckResult(STATUS_FAIL, CONTRACT-EVOLUTION-EXCEPCION, ...,
    kind=KIND_TECHNICAL_ERROR)` para ESE evento, sin abortar el resto."""
    eventos_campos, campos_cubribles = _comparar_campos(old, new)

    eventos = list(eventos_campos)
    eventos.extend(_comparar_constraints(old, new, campos_cubribles))
    eventos.extend(_comparar_business_rules(old, new))
    eventos.extend(_comparar_estructurales(old, new))

    resultados: list = []
    for evento in eventos:
        try:
            resultados.append(_evento_a_check_result(evento, policy))
        except Exception as exc:  # noqa: BLE001 -- nunca debe escapar de un evento individual
            resultados.append(checks.resultado_de_excepcion("CONTRACT-EVOLUTION", exc))
    return resultados

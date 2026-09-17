"""Resolutor neutral de routing provider/model/effort por rol+tarea (v0.5
Change 2, `provider-routing`).

Este módulo es **core** en el sentido de `ARCHITECTURE.md` §1: es puramente
declarativo y determinista -- resuelve una `RoutingPolicy` ya construida
(por quien la haya cargado, típicamente `policy.py`) sin inferir, optimizar
ni medir nada por sí mismo. No importa `tools.providers` ni ningún proveedor
concreto: `resolve()` acepta opcionalmente un `available_providers: Set[str]`
ya calculado por quien llama (p. ej. el CLI), nunca lo calcula acá -- así
`core.py` queda testeable sin ninguna CLI real y sin acoplar "decidir" con
"detectar disponibilidad".

Solo biblioteca estándar (`dataclasses`, `typing`), mismo criterio que
`tools/providers/core.py` y `tools/harmessi_bench/core.py`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Set


@dataclass
class RoutingRule:
    """Una regla de routing ya escrita por un humano: a qué `role` (y,
    opcionalmente, `task_type` -- `"*"` es comodín, matchea cualquier tipo
    de tarea) le corresponde qué `provider_id`/`model`/`effort`. `reason`
    es obligatorio (sin default): es el campo de trazabilidad, cita
    evidencia si corresponde (p. ej. "harmessi-bench run X: 3/3 vs 1/3"),
    nunca vacío (ver validación en `policy.py::load_policy`)."""

    role: str
    provider_id: str
    reason: str
    task_type: str = "*"
    model: Optional[str] = None
    effort: Optional[str] = None


@dataclass
class RoutingPolicy:
    """Conjunto de reglas ya cargadas/validadas. `default` es una regla
    explícita a aplicar cuando ninguna otra matchea -- su ausencia
    (`None`) es una configuración legítima, no un error."""

    rules: List[RoutingRule] = field(default_factory=list)
    default: Optional[RoutingRule] = None


@dataclass
class RoutingDecision:
    """Resultado de `resolve()`. `rule_source` es uno de
    `"regla_explicita"`, `"default"`, `"sin_regla"`. `provider_available`
    es `None` si no se pasó `available_providers` a `resolve()`, o
    `True`/`False` si sí se pasó y la decisión tiene `provider_id`."""

    role: str
    task_type: str
    provider_id: Optional[str]
    model: Optional[str]
    effort: Optional[str]
    matched: bool
    rule_source: str
    reason: str
    provider_available: Optional[bool] = None


def resolve(
    policy: RoutingPolicy,
    role: str,
    task_type: str = "default",
    available_providers: Optional[Set[str]] = None,
) -> RoutingDecision:
    """Resuelve, de forma determinista, qué `RoutingDecision` corresponde a
    `role`/`task_type` según `policy`.

    Orden de resolución:
    1. Filtra `policy.rules` por `regla.role == role`.
    2. Entre las que matchean el rol, prefiere la regla con `task_type`
       EXACTO igual al pedido, antes que una con `task_type == "*"`
       (comodín, matchea cualquier tarea).
    3. Si hay más de una regla con el mismo nivel de especificidad para el
       mismo rol+task_type, se usa la PRIMERA en el orden de la lista
       `policy.rules` (orden estable, deliberado -- nunca ambigüedad
       silenciosa; ver `spec.md` para el test explícito de este desempate).
    4. Si matchea una regla: `matched=True`, `rule_source=
       "regla_explicita"`.
    5. Si no matchea ninguna pero `policy.default` existe: `matched=True`,
       `rule_source="default"`.
    6. Si no matchea ninguna y no hay `default`: `matched=False`,
       `rule_source="sin_regla"`, `provider_id/model/effort=None`, y
       `reason` explica explícitamente la ausencia -- decisión de "no sé",
       nunca una adivinanza.

    Si se pasa `available_providers` (un `set[str]` de `provider_id`
    disponibles, ya calculado por quien llama -- esta función NO lo
    calcula, no importa `tools.providers`) y la decisión resultante tiene
    `provider_id` no-`None`, se setea `provider_available = provider_id in
    available_providers`. Esta función NUNCA cambia `provider_id` por otro
    valor aunque `provider_available` sea `False` -- eso sería fallback
    automático (Change 3 del roadmap, fuera de alcance acá); `resolve()`
    solo informa, no actúa.
    """
    candidatas_rol = [regla for regla in policy.rules if regla.role == role]

    exactas = [regla for regla in candidatas_rol if regla.task_type == task_type]
    comodin = [regla for regla in candidatas_rol if regla.task_type == "*"]

    regla_ganadora: Optional[RoutingRule] = None
    rule_source = "sin_regla"
    if exactas:
        regla_ganadora = exactas[0]
        rule_source = "regla_explicita"
    elif comodin:
        regla_ganadora = comodin[0]
        rule_source = "regla_explicita"
    elif policy.default is not None:
        regla_ganadora = policy.default
        rule_source = "default"

    if regla_ganadora is None:
        return RoutingDecision(
            role=role,
            task_type=task_type,
            provider_id=None,
            model=None,
            effort=None,
            matched=False,
            rule_source="sin_regla",
            reason=(
                f"ninguna regla para role={role!r} task_type={task_type!r} "
                "y no hay default declarado"
            ),
            provider_available=None,
        )

    decision = RoutingDecision(
        role=role,
        task_type=task_type,
        provider_id=regla_ganadora.provider_id,
        model=regla_ganadora.model,
        effort=regla_ganadora.effort,
        matched=True,
        rule_source=rule_source,
        reason=regla_ganadora.reason,
        provider_available=None,
    )

    if available_providers is not None and decision.provider_id is not None:
        decision.provider_available = decision.provider_id in available_providers

    return decision

"""Motor técnico de fallback entre proveedores de IA (v0.5 Change 3,
`fallback-and-handoffs`).

Este módulo es **core** en el sentido de `ARCHITECTURE.md` §1: no conoce el
protocolo `PreToolUse` de Claude Code, no lee `stdin`, y no arma flags de
`subprocess` de ningún proveedor concreto -- solo importa
`tools.providers.core` para los tipos neutrales (`ProviderAdapter`,
`InvocationRequest`, `InvocationResult`) definidos en Change 0.

**Garantía arquitectónica central de este Change (releer antes de tocar
este archivo):** el motor de fallback SOLO puede activarse por
`InvocationResult.availability_error` (calculado por
`tools.providers.core.classify_availability_error`, Change 0) -- NUNCA por:
`ok=False` con `availability_error=None` (error semántico o de código, que
se propaga tal cual, sin intentar otro proveedor), hallazgos de
`data-science-reviewer`, tests fallidos, desacuerdo metodológico, ni mala
calidad de output (eso es scoring de `harmessi_bench`, una señal
completamente distinta). Este archivo no importa `tools.harmessi_bench` ni
ningún módulo de revisión en ningún punto -- es verificable por lectura
directa. La única función que decide elegibilidad es
`is_fallback_eligible`, para que este módulo y cualquier Change futuro que
lo reuse (Change 4/5 del roadmap) tengan una única fuente de verdad.

Solo biblioteca estándar (`dataclasses`, `typing`), mismo criterio que
`tools/providers/core.py` y `tools/routing/core.py`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from tools.providers.core import InvocationRequest, InvocationResult, ProviderAdapter

_CAUSAS_ELEGIBLES = {"quota", "unavailable", "unauthenticated"}


def is_fallback_eligible(availability_error: Optional[str]) -> bool:
    """Única función que decide si un `availability_error` habilita un
    intento de fallback automático -- fuente única de verdad reusada por
    `invoke_with_fallback` y por cualquier Change futuro (4/5 del roadmap)."""
    return availability_error in _CAUSAS_ELEGIBLES


@dataclass
class HandoffRecord:
    """Registro de un único intento de invocación dentro de
    `invoke_with_fallback` (exitoso o no). `reason` documenta por qué se
    intentó este proveedor: `"intento primario"` para el primero de la
    cadena, o `f"fallback tras {availability_error} de {provider_anterior}"`
    para los siguientes."""

    provider_id: str
    attempted_at_utc: str
    ok: bool
    availability_error: Optional[str]
    reason: str


@dataclass
class FallbackOutcome:
    """Resultado completo de `invoke_with_fallback`. `final_result` SIEMPRE
    está poblado si se intentó al menos un proveedor (exitoso o no) -- el
    llamador siempre puede inspeccionar el error real, nunca se esconde.
    `blocked_reason` se puebla SOLO si el fallo NO fue elegible para
    fallback (la cadena se corta ahí, sin probar el siguiente proveedor).
    `exhausted=True` significa que se agotó toda la cadena con fallos
    elegibles, sin éxito."""

    final_provider_id: Optional[str]
    final_result: Optional[InvocationResult]
    handoffs: List[HandoffRecord] = field(default_factory=list)
    exhausted: bool = False
    blocked_reason: Optional[str] = None


def invoke_with_fallback(
    request: InvocationRequest, provider_chain: List[ProviderAdapter]
) -> FallbackOutcome:
    """Invoca `provider_chain` en orden, reintentando con el siguiente
    proveedor SOLO cuando el fallo del anterior es elegible para fallback
    (ver `is_fallback_eligible`). Ante un fallo NO elegible, corta la
    cadena inmediatamente -- nunca prueba el siguiente proveedor. Nunca
    lanza excepción: cadena vacía o agotada se reportan en el
    `FallbackOutcome`, no como error de Python."""
    from datetime import datetime, timezone

    if not provider_chain:
        return FallbackOutcome(
            final_provider_id=None,
            final_result=None,
            handoffs=[],
            exhausted=True,
            blocked_reason="cadena de proveedores vacia",
        )

    handoffs: List[HandoffRecord] = []
    resultado: Optional[InvocationResult] = None
    provider_anterior: Optional[str] = None
    error_anterior: Optional[str] = None

    for adapter in provider_chain:
        reason = (
            "intento primario"
            if provider_anterior is None
            else f"fallback tras {error_anterior!r} de {provider_anterior!r}"
        )

        resultado = adapter.invoke(request)
        handoffs.append(
            HandoffRecord(
                provider_id=adapter.provider_id,
                attempted_at_utc=datetime.now(timezone.utc).isoformat(),
                ok=resultado.ok,
                availability_error=resultado.availability_error,
                reason=reason,
            )
        )

        if resultado.ok:
            return FallbackOutcome(
                final_provider_id=adapter.provider_id,
                final_result=resultado,
                handoffs=handoffs,
                exhausted=False,
                blocked_reason=None,
            )

        if not is_fallback_eligible(resultado.availability_error):
            return FallbackOutcome(
                final_provider_id=None,
                final_result=resultado,
                handoffs=handoffs,
                exhausted=False,
                blocked_reason=(
                    "fallo no elegible para fallback automático "
                    f"(availability_error={resultado.availability_error!r}); "
                    "ver InvocationResult.stderr para el error real"
                ),
            )

        provider_anterior = adapter.provider_id
        error_anterior = resultado.availability_error

    return FallbackOutcome(
        final_provider_id=None,
        final_result=resultado,
        handoffs=handoffs,
        exhausted=True,
        blocked_reason=None,
    )

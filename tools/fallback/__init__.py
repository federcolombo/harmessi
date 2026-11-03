"""Paquete `fallback`: motor técnico de fallback entre proveedores de IA y
contexto de continuidad SDD entre sesiones/proveedores (v0.5 Change 3,
`fallback-and-handoffs`). Ver `tools/fallback/core.py` y
`tools/fallback/handoff.py` para el detalle de cada pieza, y
`ARCHITECTURE.md` §2.1 para su ubicación en el core/adapter boundary del
proyecto.
"""
from __future__ import annotations

from tools.fallback.core import (
    FallbackOutcome,
    HandoffRecord,
    invoke_with_fallback,
    is_fallback_eligible,
)
from tools.fallback.handoff import (
    HandoffContext,
    build_handoff_context,
    load_handoff,
    save_handoff,
)

__all__ = [
    "is_fallback_eligible",
    "HandoffRecord",
    "FallbackOutcome",
    "invoke_with_fallback",
    "HandoffContext",
    "build_handoff_context",
    "save_handoff",
    "load_handoff",
]

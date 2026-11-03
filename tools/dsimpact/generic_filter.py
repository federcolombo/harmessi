"""Filtro de tokens genéricos (R7): denylist fija, corta, case-insensitive,
más un mínimo de longitud -- evita que nombres/strings demasiado genéricos
disparen búsqueda global. No exhaustivo, ajustable a futuro (ver `design.md`
§7: denylist fija en vez de umbral estadístico)."""
from __future__ import annotations

TOKENS_GENERICOS = frozenset({
    "id", "name", "date", "value", "data", "index", "key", "type", "path", "file",
    "config", "result", "item", "items", "self", "args", "kwargs", "true", "false", "none",
})
LONGITUD_MINIMA = 2


def es_generico(token: str) -> bool:
    return len(token) < LONGITUD_MINIMA or token.casefold() in TOKENS_GENERICOS

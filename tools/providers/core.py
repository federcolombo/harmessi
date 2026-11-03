"""Contrato neutral de invocación multi-proveedor (v0.5 Change 0,
`multi-provider-adapters`).

Este módulo es **core** en el sentido de `ARCHITECTURE.md` §1: no conoce el
protocolo `PreToolUse` de Claude Code, no lee `stdin`, y no arma flags de
`subprocess` específicos de ningún proveedor concreto -- eso vive en cada
adapter (`claude_code.py`, `codex.py`, `gemini.py`, `grok.py`). "Adapter" acá
es el patrón de diseño (adapter de proveedor de IA), no la acepción
"Adapter" de `ARCHITECTURE.md` §2.2 (protocolo `PreToolUse`).

Solo biblioteca estándar (`dataclasses`, `abc`, `typing`), mismo criterio que
el resto de `tools/dsguard` y `tools/nbrunner`.
"""
from __future__ import annotations

import abc
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class ProviderCapabilities:
    """Capacidades de un proveedor, tal como pudieron verificarse (o no) en
    este entorno -- ante la duda, `False`, nunca inventar disponibilidad de
    una capacidad no verificada (ver `design.md`, "Riesgos")."""

    streaming: bool = False
    tool_use: bool = False
    thinking_effort: bool = False
    handoff: bool = False


@dataclass
class ProviderInfo:
    """Resultado de `ProviderAdapter.detect()`: identificación y estado de
    disponibilidad/autenticación de un proveedor, sin invocar nada más allá
    de lo necesario para detectarlo (p. ej. `--version`)."""

    provider_id: str
    display_name: str
    cli_command: str
    available: bool
    authenticated: Optional[bool]
    version: Optional[str]
    capabilities: ProviderCapabilities
    detail: str


@dataclass
class InvocationRequest:
    """Pedido de invocación neutral: cada adapter traduce estos campos a los
    flags reales de su CLI."""

    prompt: str
    # `role` está reservado para Change 2 (`provider-routing`): hoy los
    # adapters no lo usan (`ProviderAdapter.translate_role()` default es
    # identidad); ningún adapter de este Change lo overridea todavía. Es
    # deliberado (placeholder de contrato), no un olvido -- ver
    # `design.md`, sección "Riesgos".
    role: str
    model: Optional[str] = None
    effort: Optional[str] = None
    cwd: Optional[Path] = None
    timeout_s: Optional[float] = None
    extra_args: list = field(default_factory=list)


@dataclass
class InvocationResult:
    """Resultado neutral de una invocación -- `availability_error` es
    `None`/`"quota"`/`"unauthenticated"`/`"unavailable"`, ver
    `classify_availability_error`."""

    provider_id: str
    exit_code: int
    stdout: str
    stderr: str
    ok: bool
    availability_error: Optional[str]
    duration_s: float


class ProviderAdapter(abc.ABC):
    """Contrato que cada adapter concreto de proveedor debe satisfacer.
    Atributos de clase (`provider_id`, `cli_command`, `display_name`) se
    declaran en cada subclase; `detect()`/`invoke()` son abstractos."""

    provider_id: str
    cli_command: str
    display_name: str

    @abc.abstractmethod
    def detect(self) -> ProviderInfo:
        """Detecta disponibilidad/versión/capacidades del proveedor, sin
        invocar una sesión real (solo `--version` o equivalente)."""
        raise NotImplementedError

    @abc.abstractmethod
    def invoke(self, request: InvocationRequest) -> InvocationResult:
        """Invoca la CLI del proveedor con el pedido dado."""
        raise NotImplementedError

    def translate_role(self, role: str) -> str:
        """Traducción mínima de rol -> lo que espera el proveedor. Default:
        sin cambios; las subclases pueden overridear si su CLI necesita
        enmarcar el rol dentro del prompt en vez de un flag propio. Nota:
        en este Change ningún adapter overridea este método -- el uso real
        del rol queda para Change 2 (`provider-routing`)."""
        return role


def classify_availability_error(exit_code: int, stderr: str) -> Optional[str]:
    """Heurística best-effort (no una garantía) sobre texto de `stderr` para
    distinguir un fallo de disponibilidad/cuota de cualquier otro fallo.
    Nunca clasifica un fallo por otra razón (semántico, error de código) como
    disponibilidad -- crítico porque Change 3 del roadmap prohíbe fallback
    automático por esos motivos, y esta función es la única fuente de esa
    distinción. Para reducir falsos positivos, los códigos HTTP (`429`,
    `401`) se buscan con límite de palabra (`\\b...\\b`) en vez de substring
    plano, y los patrones de autenticación usan frases específicas en vez de
    la palabra genérica "authentication" (que aparece en mensajes de éxito
    como "Authentication successful, proceeding..."). Sigue siendo
    heurística sobre texto libre, no una garantía."""
    texto = (stderr or "").lower()

    if exit_code == 127 or "command not found" in texto:
        return "unavailable"

    _PATRONES_QUOTA = ("rate limit", "quota", "usage limit", "too many requests")
    if any(patron in texto for patron in _PATRONES_QUOTA) or re.search(r"\b429\b", texto):
        return "quota"

    _PATRONES_UNAUTH = (
        "not logged in",
        "unauthenticated",
        "not authenticated",
        "authentication failed",
        "authentication error",
    )
    if any(patron in texto for patron in _PATRONES_UNAUTH) or re.search(r"\b401\b", texto):
        return "unauthenticated"

    return None


# Poblado en `tools/providers/__init__.py` (no acá, para que `core.py` no
# dependa de las 4 subclases concretas).
PROVIDER_REGISTRY: Dict[str, ProviderAdapter] = {}


def list_providers(registry: Optional[Dict[str, ProviderAdapter]] = None) -> List[ProviderInfo]:
    """Corre `.detect()` de cada adapter registrado. Si no se pasa
    `registry`, usa `PROVIDER_REGISTRY` importado localmente (import
    diferido, para no crear un import circular con `__init__.py`). Nunca
    deja que la excepción de un adapter individual crashee toda la función:
    la convierte en un `ProviderInfo` con `available=False`."""
    if registry is None:
        from tools.providers import PROVIDER_REGISTRY as _registro_global

        registry = _registro_global

    resultados: List[ProviderInfo] = []
    for provider_id, adapter in registry.items():
        try:
            resultados.append(adapter.detect())
        except Exception as exc:  # noqa: BLE001 - un adapter roto no crashea la función
            resultados.append(
                ProviderInfo(
                    provider_id=provider_id,
                    display_name=getattr(adapter, "display_name", provider_id),
                    cli_command=getattr(adapter, "cli_command", ""),
                    available=False,
                    authenticated=None,
                    version=None,
                    capabilities=ProviderCapabilities(),
                    detail=f"error interno detectando {provider_id}: {exc!r}",
                )
            )
    return resultados

"""Paquete `providers`: adapters finos de proveedor de IA (v0.5 Change 0,
`multi-provider-adapters`). Ver `tools/providers/core.py` para el contrato
neutral y `ARCHITECTURE.md` §2.1 para su ubicación en el core/adapter
boundary del proyecto.
"""
from __future__ import annotations

from tools.providers.claude_code import ClaudeCodeAdapter
from tools.providers.codex import CodexAdapter
from tools.providers.core import (
    InvocationRequest,
    InvocationResult,
    ProviderAdapter,
    ProviderCapabilities,
    ProviderInfo,
    classify_availability_error,
    list_providers,
)
from tools.providers.gemini import GeminiAdapter
from tools.providers.grok import GrokAdapter

PROVIDER_REGISTRY = {
    "claude_code": ClaudeCodeAdapter(),
    "codex": CodexAdapter(),
    "gemini": GeminiAdapter(),
    "grok": GrokAdapter(),
}

__all__ = [
    "PROVIDER_REGISTRY",
    "ProviderAdapter",
    "ProviderCapabilities",
    "ProviderInfo",
    "InvocationRequest",
    "InvocationResult",
    "classify_availability_error",
    "list_providers",
    "ClaudeCodeAdapter",
    "CodexAdapter",
    "GeminiAdapter",
    "GrokAdapter",
]

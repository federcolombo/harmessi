"""Tests de `tools.fallback.core` (v0.5 Change 3, `fallback-and-handoffs`).
Deterministas: `FakeAdapter`s fabricados a mano en este archivo, nunca
invocan ninguna CLI de proveedor real."""
from __future__ import annotations

import unittest
from typing import List, Optional

from tools.fallback.core import invoke_with_fallback, is_fallback_eligible
from tools.providers.core import InvocationRequest, InvocationResult, ProviderAdapter


class _FakeAdapter(ProviderAdapter):
    """Adapter fabricado a mano: `invoke()` devuelve un `InvocationResult`
    prefijado, sin correr ningún subprocess. Cuenta cuántas veces se llamó
    `.invoke()`, para verificar que un adapter posterior a un fallo NO
    elegible nunca es invocado."""

    def __init__(self, provider_id: str, resultado: InvocationResult):
        self.provider_id = provider_id
        self.cli_command = provider_id
        self.display_name = provider_id
        self._resultado = resultado
        self.llamadas = 0

    def detect(self):
        raise NotImplementedError("no usado en estos tests")

    def invoke(self, request: InvocationRequest) -> InvocationResult:
        self.llamadas += 1
        return self._resultado


def _resultado(provider_id: str, ok: bool, availability_error: Optional[str]) -> InvocationResult:
    return InvocationResult(
        provider_id=provider_id,
        exit_code=0 if ok else 1,
        stdout="ok" if ok else "",
        stderr="" if ok else "fallo simulado",
        ok=ok,
        availability_error=availability_error,
        duration_s=0.01,
    )


def _request() -> InvocationRequest:
    return InvocationRequest(prompt="hola", role="writer")


class TestIsFallbackEligible(unittest.TestCase):
    def test_quota_unavailable_unauthenticated_son_elegibles(self):
        for causa in ("quota", "unavailable", "unauthenticated"):
            self.assertTrue(is_fallback_eligible(causa))

    def test_none_no_es_elegible(self):
        self.assertFalse(is_fallback_eligible(None))

    def test_causa_arbitraria_no_es_elegible(self):
        self.assertFalse(is_fallback_eligible("timeout_de_red"))


class TestInvokeWithFallback(unittest.TestCase):
    def test_un_solo_adapter_exitoso(self):
        adapter = _FakeAdapter("claude_code", _resultado("claude_code", ok=True, availability_error=None))

        outcome = invoke_with_fallback(_request(), [adapter])

        self.assertEqual(outcome.final_provider_id, "claude_code")
        self.assertFalse(outcome.exhausted)
        self.assertIsNone(outcome.blocked_reason)
        self.assertEqual(len(outcome.handoffs), 1)
        self.assertEqual(outcome.handoffs[0].reason, "intento primario")
        self.assertEqual(adapter.llamadas, 1)

    def test_primero_falla_elegible_segundo_exitoso(self):
        primero = _FakeAdapter("codex", _resultado("codex", ok=False, availability_error="unavailable"))
        segundo = _FakeAdapter("claude_code", _resultado("claude_code", ok=True, availability_error=None))

        outcome = invoke_with_fallback(_request(), [primero, segundo])

        self.assertEqual(outcome.final_provider_id, "claude_code")
        self.assertEqual(len(outcome.handoffs), 2)
        self.assertFalse(outcome.exhausted)
        self.assertIsNone(outcome.blocked_reason)
        self.assertEqual(primero.llamadas, 1)
        self.assertEqual(segundo.llamadas, 1)

    def test_primero_falla_no_elegible_corta_cadena_sin_llamar_segundo(self):
        primero = _FakeAdapter("codex", _resultado("codex", ok=False, availability_error=None))
        segundo = _FakeAdapter("claude_code", _resultado("claude_code", ok=True, availability_error=None))

        outcome = invoke_with_fallback(_request(), [primero, segundo])

        self.assertIsNone(outcome.final_provider_id)
        self.assertIsNotNone(outcome.blocked_reason)
        self.assertFalse(outcome.exhausted)
        self.assertEqual(len(outcome.handoffs), 1)
        self.assertEqual(primero.llamadas, 1)
        self.assertEqual(segundo.llamadas, 0)
        self.assertIs(outcome.final_result, primero._resultado)

    def test_ambos_fallan_elegible_cadena_agotada(self):
        primero = _FakeAdapter("codex", _resultado("codex", ok=False, availability_error="unavailable"))
        segundo = _FakeAdapter("gemini", _resultado("gemini", ok=False, availability_error="quota"))

        outcome = invoke_with_fallback(_request(), [primero, segundo])

        self.assertTrue(outcome.exhausted)
        self.assertIsNone(outcome.final_provider_id)
        self.assertIsNone(outcome.blocked_reason)
        self.assertEqual(len(outcome.handoffs), 2)
        self.assertIs(outcome.final_result, segundo._resultado)

    def test_cadena_vacia_no_lanza_excepcion(self):
        outcome = invoke_with_fallback(_request(), [])

        self.assertTrue(outcome.exhausted)
        self.assertIsNone(outcome.final_provider_id)
        self.assertIsNone(outcome.final_result)
        self.assertEqual(outcome.handoffs, [])
        self.assertIn("vacia", outcome.blocked_reason)


if __name__ == "__main__":
    unittest.main()

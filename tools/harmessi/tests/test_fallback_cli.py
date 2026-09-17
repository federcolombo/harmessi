"""Test del subcomando `fallback` de `tools.harmessi.cli` (v0.5 Change 3,
`fallback-and-handoffs`). Usa el `policy.example.json` real bundleado en
`tools/routing/examples/` (regla `writer` con `fallback_chain=["codex"]`) y
`PROVIDER_REGISTRY` monkeypatcheado con `FakeAdapter`s fabricados a mano --
nunca invoca ninguna CLI de proveedor real, mismo patrón que
`test_providers_cli.py`/`test_routing_cli.py`."""
from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Optional

import pytest

from tools.harmessi.cli import main
from tools.providers.core import (
    InvocationRequest,
    InvocationResult,
    ProviderAdapter,
    ProviderCapabilities,
    ProviderInfo,
)

_EXAMPLE_POLICY_PATH = (
    Path(__file__).resolve().parents[2] / "routing" / "examples" / "policy.example.json"
)


class _FakeAdapter(ProviderAdapter):
    def __init__(self, provider_id: str, available: bool, resultado: Optional[InvocationResult] = None):
        self.provider_id = provider_id
        self.cli_command = provider_id
        self.display_name = provider_id
        self._available = available
        self._resultado = resultado

    def detect(self) -> ProviderInfo:
        return ProviderInfo(
            provider_id=self.provider_id,
            display_name=self.display_name,
            cli_command=self.cli_command,
            available=self._available,
            authenticated=None,
            version="0.0.0" if self._available else None,
            capabilities=ProviderCapabilities(),
            detail="fabricado en test",
        )

    def invoke(self, request: InvocationRequest) -> InvocationResult:
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


class TestFallbackResolveChainCli(unittest.TestCase):
    def setUp(self):
        self._patcher = pytest.MonkeyPatch()

    def tearDown(self):
        self._patcher.undo()

    def test_resolve_chain_writer_cadena_claude_code_codex(self):
        registry = {
            "claude_code": _FakeAdapter("claude_code", available=True),
            "codex": _FakeAdapter("codex", available=False),
        }
        self._patcher.setattr("tools.providers.PROVIDER_REGISTRY", registry)

        stdout = io.StringIO()
        with redirect_stdout(stdout):
            codigo = main(
                [
                    "fallback",
                    "resolve-chain",
                    "--role",
                    "writer",
                    "--policy",
                    str(_EXAMPLE_POLICY_PATH),
                    "--json",
                ]
            )
        self.assertEqual(codigo, 0)

        datos = json.loads(stdout.getvalue())
        self.assertEqual(datos["cadena"], ["claude_code", "codex"])
        self.assertEqual(datos["disponibilidad"]["claude_code"], "disponible")
        self.assertEqual(datos["disponibilidad"]["codex"], "no_disponible")

    def test_resolve_chain_provider_no_registrado_se_reporta_sin_crashear(self):
        registry = {"claude_code": _FakeAdapter("claude_code", available=True)}
        self._patcher.setattr("tools.providers.PROVIDER_REGISTRY", registry)

        stdout = io.StringIO()
        with redirect_stdout(stdout):
            codigo = main(
                [
                    "fallback",
                    "resolve-chain",
                    "--role",
                    "writer",
                    "--policy",
                    str(_EXAMPLE_POLICY_PATH),
                    "--json",
                ]
            )
        self.assertEqual(codigo, 0)

        datos = json.loads(stdout.getvalue())
        self.assertEqual(datos["disponibilidad"]["codex"], "no_registrado")


class TestFallbackInvokeCli(unittest.TestCase):
    def setUp(self):
        self._patcher = pytest.MonkeyPatch()

    def tearDown(self):
        self._patcher.undo()

    def test_invoke_camino_de_exito(self):
        registry = {
            "claude_code": _FakeAdapter(
                "claude_code", available=True, resultado=_resultado("claude_code", ok=True, availability_error=None)
            ),
            "codex": _FakeAdapter(
                "codex", available=False, resultado=_resultado("codex", ok=False, availability_error="unavailable")
            ),
        }
        self._patcher.setattr("tools.providers.PROVIDER_REGISTRY", registry)

        stdout = io.StringIO()
        with redirect_stdout(stdout):
            codigo = main(
                [
                    "fallback",
                    "invoke",
                    "--role",
                    "writer",
                    "--prompt",
                    "hola",
                    "--policy",
                    str(_EXAMPLE_POLICY_PATH),
                    "--json",
                ]
            )
        self.assertEqual(codigo, 0)

        datos = json.loads(stdout.getvalue())
        self.assertEqual(datos["final_provider_id"], "claude_code")
        self.assertFalse(datos["exhausted"])

    def test_invoke_cadena_agotada(self):
        registry = {
            "claude_code": _FakeAdapter(
                "claude_code",
                available=True,
                resultado=_resultado("claude_code", ok=False, availability_error="quota"),
            ),
            "codex": _FakeAdapter(
                "codex", available=False, resultado=_resultado("codex", ok=False, availability_error="unavailable")
            ),
        }
        self._patcher.setattr("tools.providers.PROVIDER_REGISTRY", registry)

        stdout = io.StringIO()
        with redirect_stdout(stdout):
            codigo = main(
                [
                    "fallback",
                    "invoke",
                    "--role",
                    "writer",
                    "--prompt",
                    "hola",
                    "--policy",
                    str(_EXAMPLE_POLICY_PATH),
                    "--json",
                ]
            )
        self.assertEqual(codigo, 0)

        datos = json.loads(stdout.getvalue())
        self.assertTrue(datos["exhausted"])
        self.assertIsNone(datos["final_provider_id"])

    def test_invoke_rol_sin_regla_y_sin_cadena_exit_1(self):
        registry = {"claude_code": _FakeAdapter("claude_code", available=True)}
        self._patcher.setattr("tools.providers.PROVIDER_REGISTRY", registry)

        stderr = io.StringIO()
        with redirect_stderr(stderr):
            codigo = main(
                [
                    "fallback",
                    "invoke",
                    "--role",
                    "rol_inexistente",
                    "--prompt",
                    "hola",
                    "--policy",
                    str(_EXAMPLE_POLICY_PATH),
                ]
            )
        self.assertEqual(codigo, 1)
        self.assertIn("fallback invoke", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()

"""Test del subcomando `providers list` de `tools.harmessi.cli` (v0.5
Change 0, `multi-provider-adapters`). Fix 4 (ronda 1 de revisión): usa
`monkeypatch` sobre `tools.providers.list_providers` con proveedores
fabricados a mano, para no invocar ninguna CLI real ni depender de qué haya
instalado en el entorno donde corra la suite."""
from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout

import pytest

from tools.harmessi.cli import main
from tools.providers.core import ProviderCapabilities, ProviderInfo


def _fabricar_providers() -> list:
    """4 `ProviderInfo` fabricados a mano, uno por `provider_id` esperado,
    sin invocar ningún adapter ni CLI real."""
    return [
        ProviderInfo(
            provider_id="claude_code",
            display_name="Claude Code",
            cli_command="claude",
            available=True,
            authenticated=None,
            version="2.1.274",
            capabilities=ProviderCapabilities(
                streaming=True, tool_use=True, thinking_effort=True, handoff=True
            ),
            detail="CLI encontrada en /usr/bin/claude",
        ),
        ProviderInfo(
            provider_id="codex",
            display_name="Codex CLI",
            cli_command="codex",
            available=False,
            authenticated=None,
            version=None,
            capabilities=ProviderCapabilities(),
            detail="CLI 'codex' no encontrada en PATH",
        ),
        ProviderInfo(
            provider_id="gemini",
            display_name="Gemini CLI",
            cli_command="gemini",
            available=False,
            authenticated=None,
            version=None,
            capabilities=ProviderCapabilities(),
            detail="CLI 'gemini' no encontrada en PATH",
        ),
        ProviderInfo(
            provider_id="grok",
            display_name="Grok CLI",
            cli_command="grok",
            available=False,
            authenticated=None,
            version=None,
            capabilities=ProviderCapabilities(),
            detail="CLI 'grok' no encontrada en PATH",
        ),
    ]


class TestProvidersListCli(unittest.TestCase):
    def setUp(self):
        self._patcher = pytest.MonkeyPatch()

    def tearDown(self):
        self._patcher.undo()

    def test_providers_list_json_devuelve_4_entradas(self):
        self._patcher.setattr("tools.providers.list_providers", _fabricar_providers)

        stdout = io.StringIO()
        with redirect_stdout(stdout):
            codigo = main(["providers", "list", "--json"])
        self.assertEqual(codigo, 0)

        datos = json.loads(stdout.getvalue())
        self.assertIsInstance(datos, list)
        self.assertEqual(len(datos), 4)

        provider_ids = {entrada["provider_id"] for entrada in datos}
        self.assertEqual(provider_ids, {"claude_code", "codex", "gemini", "grok"})
        for entrada in datos:
            self.assertIn("available", entrada)
            self.assertIn("detail", entrada)

    def test_providers_list_texto_incluye_encabezado(self):
        self._patcher.setattr("tools.providers.list_providers", _fabricar_providers)

        stdout = io.StringIO()
        with redirect_stdout(stdout):
            codigo = main(["providers", "list"])
        self.assertEqual(codigo, 0)
        self.assertIn("Harmessi providers", stdout.getvalue())
        self.assertIn("claude_code", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()

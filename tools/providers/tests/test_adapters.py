"""Tests de conformidad de interfaz y detección/invocación de los 4 adapters
de proveedor (v0.5 Change 0). No invoca `claude -p` real (dispara una sesión
real con costo) -- solo tests de detección (real para `claude_code` cuando
la CLI está presente, simulada con `monkeypatch` para el resto) y de armado
de comando vía `monkeypatch` sobre `subprocess.run`."""
from __future__ import annotations

import shutil
import subprocess
import unittest

import pytest

from tools.providers.claude_code import ClaudeCodeAdapter
from tools.providers.codex import CodexAdapter
from tools.providers.core import InvocationRequest, ProviderAdapter
from tools.providers.gemini import GeminiAdapter
from tools.providers.grok import GrokAdapter

_ADAPTERS = [ClaudeCodeAdapter, CodexAdapter, GeminiAdapter, GrokAdapter]


class TestConformidadInterfaz(unittest.TestCase):
    def test_los_4_adapters_son_instancia_de_provider_adapter(self):
        for clase in _ADAPTERS:
            with self.subTest(clase=clase.__name__):
                instancia = clase()
                self.assertIsInstance(instancia, ProviderAdapter)

    def test_atributos_no_vacios(self):
        for clase in _ADAPTERS:
            with self.subTest(clase=clase.__name__):
                instancia = clase()
                self.assertTrue(instancia.provider_id)
                self.assertTrue(instancia.cli_command)
                self.assertTrue(instancia.display_name)

    def test_translate_role_default_no_cambia_el_rol(self):
        instancia = ClaudeCodeAdapter()
        self.assertEqual(instancia.translate_role("lead"), "lead")


class TestDeteccionSinCliInstalada:
    """Para codex/gemini/grok: fuerza `shutil.which` a `None` vía
    `monkeypatch` para que el test corra igual en cualquier entorno, con o
    sin esas CLIs instaladas."""

    @pytest.mark.parametrize("clase", [CodexAdapter, GeminiAdapter, GrokAdapter])
    def test_detect_sin_cli_da_no_disponible(self, monkeypatch, clase):
        monkeypatch.setattr(shutil, "which", lambda cmd: None)
        info = clase().detect()
        assert info.available is False
        assert info.detail

    @pytest.mark.parametrize("clase", [CodexAdapter, GeminiAdapter, GrokAdapter])
    def test_invoke_sin_cli_da_unavailable_sin_excepcion(self, monkeypatch, clase):
        monkeypatch.setattr(shutil, "which", lambda cmd: None)
        adapter = clase()
        request = InvocationRequest(prompt="hola", role="lead")
        resultado = adapter.invoke(request)
        assert resultado.ok is False
        assert resultado.availability_error == "unavailable"
        assert resultado.exit_code == 127


@pytest.mark.skipif(
    shutil.which("claude") is None, reason="CLI 'claude' no disponible en este entorno"
)
def test_claude_code_detect_real():
    """Sin mocks: confirma `available=True` de verdad contra la CLI real
    instalada en este entorno. Se salta solo si 'claude' no está en PATH."""
    info = ClaudeCodeAdapter().detect()
    assert info.available is True


class TestClaudeCodeInvokeArmadoComando:
    """`invoke()` de `claude_code` con `monkeypatch` sobre `subprocess.run`
    -- nunca llama al binario real."""

    def test_comando_basico(self, monkeypatch):
        monkeypatch.setattr(shutil, "which", lambda cmd: "/usr/bin/claude")

        capturado = {}

        def _fake_run(cmd, **kwargs):
            capturado["cmd"] = cmd
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="{}", stderr="")

        monkeypatch.setattr(subprocess, "run", _fake_run)

        adapter = ClaudeCodeAdapter()
        request = InvocationRequest(prompt="hola mundo", role="lead")
        resultado = adapter.invoke(request)

        cmd = capturado["cmd"]
        assert "-p" in cmd
        assert "--output-format" in cmd
        assert "json" in cmd
        assert resultado.ok is True

    def test_comando_con_model_y_effort(self, monkeypatch):
        monkeypatch.setattr(shutil, "which", lambda cmd: "/usr/bin/claude")

        capturado = {}

        def _fake_run(cmd, **kwargs):
            capturado["cmd"] = cmd
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="{}", stderr="")

        monkeypatch.setattr(subprocess, "run", _fake_run)

        adapter = ClaudeCodeAdapter()
        request = InvocationRequest(
            prompt="hola", role="lead", model="claude-sonnet-5", effort="high"
        )
        adapter.invoke(request)

        cmd = capturado["cmd"]
        assert "--model" in cmd
        assert "claude-sonnet-5" in cmd
        assert "--effort" in cmd
        assert "high" in cmd

    def test_invoke_timeout_expired_no_propaga_excepcion(self, monkeypatch):
        """Fix 1 (ronda 1 de revisión): un `subprocess.TimeoutExpired` real
        (o un `OSError` por TOCTOU) no debe propagar sin capturar -- se
        traduce a `InvocationResult` con `availability_error='unavailable'`."""
        monkeypatch.setattr(shutil, "which", lambda cmd: "/usr/bin/claude")

        def _fake_run_timeout(cmd, **kwargs):
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=kwargs.get("timeout") or 10)

        monkeypatch.setattr(subprocess, "run", _fake_run_timeout)

        adapter = ClaudeCodeAdapter()
        request = InvocationRequest(prompt="hola", role="lead", timeout_s=10)
        resultado = adapter.invoke(request)

        assert resultado.ok is False
        assert resultado.availability_error == "unavailable"


if __name__ == "__main__":
    unittest.main()

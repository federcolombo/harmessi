"""Tests de paridad de contrato entre los 4 adapters de proveedor (v0.5
Change 4, `cross-provider-hardening`). Cierra la asimetría de cobertura que
`test_adapters.py` (Change 0) dejó documentada como limitación menor: acá
`claude_code` se somete exactamente al mismo parametrize que los otros 3, en
vez de tener sus propios tests separados de detección/invocación sin CLI.

Nunca invoca una CLI de proveedor real -- todo con `monkeypatch` sobre
`shutil.which` (mismo patrón que `test_adapters.py::TestDeteccionSinCliInstalada`),
determinista sin importar qué CLI esté instalada en el entorno que corre la
suite.
"""
from __future__ import annotations

import shutil

import pytest

from tools.providers import list_providers
from tools.providers.claude_code import ClaudeCodeAdapter
from tools.providers.codex import CodexAdapter
from tools.providers.core import InvocationRequest, ProviderAdapter
from tools.providers.gemini import GeminiAdapter
from tools.providers.grok import GrokAdapter

_ADAPTERS = [ClaudeCodeAdapter, CodexAdapter, GeminiAdapter, GrokAdapter]


@pytest.mark.parametrize("clase", _ADAPTERS)
def test_instancia_es_provider_adapter(clase):
    instancia = clase()
    assert isinstance(instancia, ProviderAdapter)


@pytest.mark.parametrize("clase", _ADAPTERS)
def test_atributos_de_identificacion_no_vacios(clase):
    instancia = clase()
    assert instancia.provider_id
    assert instancia.cli_command
    assert instancia.display_name


def test_los_4_provider_id_son_distintos_entre_si():
    provider_ids = [clase().provider_id for clase in _ADAPTERS]
    assert len(provider_ids) == len(set(provider_ids)), (
        f"provider_id duplicado entre adapters: {provider_ids!r}"
    )


@pytest.mark.parametrize("clase", _ADAPTERS)
def test_detect_sin_cli_da_no_disponible_sin_excepcion(monkeypatch, clase):
    """Los 4 adapters, incluido claude_code (a diferencia de Change 0, que
    solo parametrizaba codex/gemini/grok acá) -- mismo contrato de
    degradación para los 4."""
    monkeypatch.setattr(shutil, "which", lambda cmd: None)
    info = clase().detect()
    assert info.available is False
    assert info.detail


@pytest.mark.parametrize("clase", _ADAPTERS)
def test_invoke_sin_cli_da_unavailable_sin_excepcion(monkeypatch, clase):
    """Idem -- los 4 adapters devuelven exactamente el mismo contrato de
    error de disponibilidad (ok=False, availability_error='unavailable',
    exit_code=127), sin lanzar excepción."""
    monkeypatch.setattr(shutil, "which", lambda cmd: None)
    adapter = clase()
    request = InvocationRequest(prompt="hola", role="lead")
    resultado = adapter.invoke(request)
    assert resultado.ok is False
    assert resultado.availability_error == "unavailable"
    assert resultado.exit_code == 127


def test_list_providers_devuelve_exactamente_4_entradas():
    """Usa el `PROVIDER_REGISTRY` real (sin mockear), confirmando que el
    registro efectivamente tiene 4 entradas, una por cada provider_id
    único -- ni más ni menos."""
    resultados = list_providers()
    provider_ids = [info.provider_id for info in resultados]
    assert len(resultados) == 4, f"se esperaban 4 providers, se obtuvieron {len(resultados)}: {provider_ids!r}"
    assert len(set(provider_ids)) == 4, f"provider_id duplicado en list_providers(): {provider_ids!r}"


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__]))

"""Tests de paridad de fallback entre los 4 provider_id reales (v0.5
Change 4, `cross-provider-hardening`). Confirma que `invoke_with_fallback`
trata a `claude_code`/`codex`/`gemini`/`grok` de forma IDÉNTICA -- no hay
ningún `if provider_id == "..."` especial en `tools/fallback/core.py` (ver
también `tools/tests/test_v05_core_neutrality.py`, que verifica por AST que
el core no contiene el literal 'claude'; acá se agrega una verificación de
lectura explícita sobre el código fuente para los 4 provider_id reales).

Deterministas: `FakeAdapter`s fabricados a mano (mismo patrón que
`tools/fallback/tests/test_core.py::_FakeAdapter`), nunca invocan ninguna
CLI de proveedor real.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import pytest

from tools.fallback.core import invoke_with_fallback
from tools.providers.core import InvocationRequest, InvocationResult, ProviderAdapter

_PROVIDER_IDS_REALES = ["claude_code", "codex", "gemini", "grok"]

_FALLBACK_CORE_PATH = Path(__file__).resolve().parents[1] / "core.py"


class _FakeAdapter(ProviderAdapter):
    """Adapter fabricado a mano: `invoke()` devuelve un `InvocationResult`
    prefijado y registra el último `request` recibido, sin correr ningún
    subprocess. Mismo patrón que `tools/fallback/tests/test_core.py`."""

    def __init__(self, provider_id: str, resultado: InvocationResult):
        self.provider_id = provider_id
        self.cli_command = provider_id
        self.display_name = provider_id
        self._resultado = resultado
        self.llamadas = 0
        self.ultimo_request: Optional[InvocationRequest] = None

    def detect(self):
        raise NotImplementedError("no usado en estos tests")

    def invoke(self, request: InvocationRequest) -> InvocationResult:
        self.llamadas += 1
        self.ultimo_request = request
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


def _request(role: str = "writer") -> InvocationRequest:
    return InvocationRequest(prompt="hola", role=role)


@pytest.mark.parametrize("provider_id", _PROVIDER_IDS_REALES)
def test_cada_uno_de_los_4_como_primario_exitoso(provider_id):
    """Cada uno de los 4 provider_id reales, como único elemento de la
    cadena, exitoso: mismo resultado estructural para los 4."""
    adapter = _FakeAdapter(provider_id, _resultado(provider_id, ok=True, availability_error=None))

    outcome = invoke_with_fallback(_request(), [adapter])

    assert outcome.final_provider_id == provider_id
    assert outcome.exhausted is False
    assert outcome.blocked_reason is None
    assert len(outcome.handoffs) == 1
    assert outcome.handoffs[0].reason == "intento primario"
    assert outcome.handoffs[0].provider_id == provider_id
    assert adapter.llamadas == 1


@pytest.mark.parametrize("provider_id_primario", _PROVIDER_IDS_REALES)
def test_cada_uno_de_los_4_como_primario_que_falla_elegible_con_siguiente_exitoso(
    provider_id_primario,
):
    """Cada uno de los 4 provider_id reales, como primario que falla con un
    error elegible ('unavailable'), seguido de un segundo adapter exitoso:
    mismo resultado estructural (2 handoffs, exhausted=False) para los 4,
    sin importar cuál de los 4 sea el que falla."""
    # Segundo adapter con un provider_id distinto del primario, para que el
    # caso sea realista (nunca dos veces el mismo provider en una cadena).
    provider_id_secundario = next(
        pid for pid in _PROVIDER_IDS_REALES if pid != provider_id_primario
    )
    primario = _FakeAdapter(
        provider_id_primario,
        _resultado(provider_id_primario, ok=False, availability_error="unavailable"),
    )
    secundario = _FakeAdapter(
        provider_id_secundario, _resultado(provider_id_secundario, ok=True, availability_error=None)
    )

    outcome = invoke_with_fallback(_request(), [primario, secundario])

    assert outcome.final_provider_id == provider_id_secundario
    assert outcome.exhausted is False
    assert outcome.blocked_reason is None
    assert len(outcome.handoffs) == 2
    assert outcome.handoffs[0].provider_id == provider_id_primario
    assert outcome.handoffs[1].provider_id == provider_id_secundario
    assert primario.llamadas == 1
    assert secundario.llamadas == 1


def test_fallback_core_no_compara_provider_id_contra_ninguno_de_los_4_reales():
    """Verificación de lectura explícita: `tools/fallback/core.py` no debe
    contener el literal de ninguno de los 4 provider_id reales -- confirma
    por texto (no solo por comportamiento observado en los tests de arriba)
    que no hay ninguna rama `if provider_id == "claude_code"` (ni
    equivalente para codex/gemini/grok)."""
    codigo = _FALLBACK_CORE_PATH.read_text(encoding="utf-8")
    violaciones = [pid for pid in _PROVIDER_IDS_REALES if f'"{pid}"' in codigo or f"'{pid}'" in codigo]
    assert violaciones == [], (
        f"tools/fallback/core.py contiene el/los literal(es) {violaciones!r} -- "
        "el motor de fallback no debe reconocer ningún provider_id por su nombre"
    )


@pytest.mark.parametrize("role", ["writer", "reviewer", "metodologo"])
def test_role_es_opaco_para_el_motor_de_fallback(role):
    """`invoke_with_fallback` no inspecciona ni condiciona su comportamiento
    por `role`: lo reenvía tal cual al adapter, y la forma del
    `FallbackOutcome` no varía según su valor."""
    adapter = _FakeAdapter("claude_code", _resultado("claude_code", ok=True, availability_error=None))

    outcome = invoke_with_fallback(_request(role=role), [adapter])

    assert adapter.ultimo_request is not None
    assert adapter.ultimo_request.role == role
    assert outcome.final_provider_id == "claude_code"
    assert outcome.exhausted is False
    assert outcome.blocked_reason is None
    assert len(outcome.handoffs) == 1


def test_fallback_core_no_compara_role_contra_ningun_valor_conocido():
    """Verificación de lectura explícita, simétrica a
    `test_fallback_core_no_compara_provider_id_contra_ninguno_de_los_4_reales`:
    `tools/fallback/core.py` no debe contener el literal de ningún `role`
    conocido del proyecto -- confirma por texto que no hay ninguna rama
    condicional (`if role == "writer"` ni equivalente para reviewer/
    metodologo) que trate a `role` de forma especial. Si en el futuro se
    introdujera una comparación así, este test la detectaría."""
    codigo = _FALLBACK_CORE_PATH.read_text(encoding="utf-8")
    roles_conocidos = ["writer", "reviewer", "metodologo"]
    violaciones = [
        role for role in roles_conocidos if f'"{role}"' in codigo or f"'{role}'" in codigo
    ]
    assert violaciones == [], (
        f"tools/fallback/core.py contiene el/los literal(es) {violaciones!r} -- "
        "el motor de fallback no debe reconocer ningún role por su nombre"
    )


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__]))

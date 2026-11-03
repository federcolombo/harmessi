"""Tests de `tools/harmessi_bench/runner.py`: `run_scenario`/`run_scenario_set`
contra un `FakeAdapter` de test (nunca invoca una CLI real)."""
from __future__ import annotations

from tools.harmessi_bench.core import EvalTarget, Scenario
from tools.harmessi_bench.runner import run_scenario, run_scenario_set
from tools.providers.core import InvocationResult


class FakeAdapter:
    """Adapter de test: devuelve un `InvocationResult` fabricado a mano,
    fijado en el constructor, sin invocar ningún proceso real."""

    provider_id = "fake"
    cli_command = "fake"
    display_name = "Fake"

    def __init__(self, resultado: InvocationResult):
        self._resultado = resultado

    def detect(self):
        raise NotImplementedError("no usado en estos tests")

    def invoke(self, request):
        return self._resultado


def _target():
    return EvalTarget(provider_id="fake", model=None, effort=None)


def test_run_scenario_invocacion_exitosa_json_result():
    scenario = Scenario(
        scenario_id="s1",
        prompt="Respondé OK.",
        category="demo",
        tags=[],
        expected={"tipo": "exact", "valor": "OK"},
    )
    resultado_invocacion = InvocationResult(
        provider_id="fake",
        exit_code=0,
        stdout='{"result": "OK"}',
        stderr="",
        ok=True,
        availability_error=None,
        duration_s=0.1,
    )
    adapter = FakeAdapter(resultado_invocacion)

    resultado = run_scenario(scenario, _target(), adapter, run_id="run-1")

    assert resultado.ok is True
    assert resultado.score.passed is True
    assert resultado.stdout_excerpt == "OK"


def test_run_scenario_no_disponible_no_llama_scorer():
    scenario = Scenario(
        scenario_id="s2",
        prompt="algo",
        category="demo",
        tags=[],
        expected={"tipo": "exact", "valor": "OK"},
    )
    resultado_invocacion = InvocationResult(
        provider_id="fake",
        exit_code=127,
        stdout="",
        stderr="command not found",
        ok=False,
        availability_error="unavailable",
        duration_s=0.0,
    )
    adapter = FakeAdapter(resultado_invocacion)

    resultado = run_scenario(scenario, _target(), adapter, run_id="run-1")

    assert resultado.ok is False
    assert resultado.score.passed is False
    assert "unavailable" in resultado.score.detail


def test_run_scenario_stdout_no_json_usa_texto_crudo():
    scenario = Scenario(
        scenario_id="s3",
        prompt="algo",
        category="demo",
        tags=[],
        expected={"tipo": "contains", "valores": ["hola"]},
    )
    resultado_invocacion = InvocationResult(
        provider_id="fake",
        exit_code=0,
        stdout="esto no es json, dice hola nomás",
        stderr="",
        ok=True,
        availability_error=None,
        duration_s=0.2,
    )
    adapter = FakeAdapter(resultado_invocacion)

    resultado = run_scenario(scenario, _target(), adapter, run_id="run-1")

    assert resultado.ok is True
    assert resultado.score.passed is True


def test_run_scenario_result_no_string_se_normaliza_a_str():
    scenario = Scenario(
        scenario_id="s4",
        prompt="Respondé el número.",
        category="demo",
        tags=[],
        expected={"tipo": "exact", "valor": "123"},
    )
    resultado_invocacion = InvocationResult(
        provider_id="fake",
        exit_code=0,
        stdout='{"result": 123}',
        stderr="",
        ok=True,
        availability_error=None,
        duration_s=0.1,
    )
    adapter = FakeAdapter(resultado_invocacion)

    resultado = run_scenario(scenario, _target(), adapter, run_id="run-1")

    assert resultado.ok is True
    assert resultado.score.passed is True
    assert resultado.stdout_excerpt == "123"


def test_run_scenario_set_no_aborta_ante_escenario_roto():
    scenario_ok = Scenario(
        scenario_id="ok",
        prompt="hola",
        category="demo",
        tags=[],
        expected={"tipo": "exact", "valor": "OK"},
    )
    scenario_roto = Scenario(
        scenario_id="roto",
        prompt="hola",
        category="demo",
        tags=[],
        expected=None,  # provoca excepción interna en aplicar_scorer/runner
    )
    resultado_invocacion = InvocationResult(
        provider_id="fake",
        exit_code=0,
        stdout='{"result": "OK"}',
        stderr="",
        ok=True,
        availability_error=None,
        duration_s=0.1,
    )
    adapter = FakeAdapter(resultado_invocacion)

    resultados = run_scenario_set([scenario_ok, scenario_roto], _target(), adapter, run_id="run-1")

    assert len(resultados) == 2
    ids = [resultado.scenario_id for resultado in resultados]
    assert "ok" in ids
    assert "roto" in ids
    resultado_roto = next(resultado for resultado in resultados if resultado.scenario_id == "roto")
    assert resultado_roto.ok is False
    assert resultado_roto.score.passed is False

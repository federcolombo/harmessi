"""Smoke del Change `20261021-v013-eval-benchmark-foundation`.

Corre la suite pública sintética con adapters falsos (sin proveedor real ni
red) como baseline y como candidate manual, guarda en un directorio temporal
con espacios y Unicode, compara y verifica los cuatro veredictos y los
contratos de versionado/boundary de la fundación de evals de v0.13.
"""
from __future__ import annotations

import dataclasses
import json
import re
import tempfile
from pathlib import Path

import pytest

from tools.harmessi_bench import storage
from tools.harmessi_bench.compare import compare_runs
from tools.harmessi_bench.core import EvalTarget
from tools.harmessi_bench.runner import run_scenario_set
from tools.harmessi_bench.scenarios import load_scenarios
from tools.harmessi_bench.suite import load_suite_y_casos, resumir
from tools.providers.core import InvocationResult

REPO_ORIGEN = Path(__file__).resolve().parents[2]
RUTA_SUITE = REPO_ORIGEN / "tools" / "harmessi_bench" / "suites" / "harmessi-core-synthetic.suite.json"

# Respuestas "buenas" por caso de la suite pública (pasan el scorer determinista).
RESPUESTAS_BUENAS = {
    "framing-aclarar-pedido": "Pregunta: ¿qué decisión debe apoyar el informe?",
    "framing-supuesto-explicito": "Supuesto: el período es mensual; hay que validar con quien lo pide.",
    "debugging-primer-paso": "reproducir",
    "debugging-causa-raiz": "Se corrige la causa raíz y se agrega una prueba de regresión.",
    "domain-modeling-termino-ambiguo": "Un glosario con la definición acordada de cada término.",
    "codebase-design-reuso": "Conviene reutilizar la primitiva existente.",
    "recovery-idempotencia": "idempotente",
    "tool-contract-json": '{"estado": "ok"}',
    "tool-contract-codigo-salida": "Reportar el código de salida y el error observado.",
}
# Casos que el adapter "degradado" responde mal.
CASOS_DEGRADADOS = {"debugging-primer-paso", "recovery-idempotencia", "tool-contract-json"}


class AdapterFalso:
    """Adapter de test: responde por prompt; opcionalmente 'cae' (indisponible)
    en los prompts de `caidos`. Sin red ni proceso externo."""

    def __init__(self, respuestas: dict, caidos: frozenset = frozenset()):
        self._respuestas = respuestas
        self._caidos = caidos

    def invoke(self, request):
        if request.prompt in self._caidos:
            return InvocationResult(
                provider_id="falso",
                exit_code=1,
                stdout="",
                stderr="cuota agotada",
                ok=False,
                availability_error="quota",
                duration_s=0.0,
            )
        return InvocationResult(
            provider_id="falso",
            exit_code=0,
            stdout=self._respuestas.get(request.prompt, "no sé"),
            stderr="",
            ok=True,
            availability_error=None,
            duration_s=0.01,
        )


@pytest.fixture()
def raiz():
    with tempfile.TemporaryDirectory(prefix="harmessi bench ñandú ") as directorio:
        yield Path(directorio) / "evals con espacios"


@pytest.fixture(scope="module")
def suite_y_casos():
    return load_suite_y_casos(RUTA_SUITE)


def _adapter(escenarios, degradado: bool, caidos_ids=()):
    respuestas = {
        e.prompt: ("no sé" if degradado and e.scenario_id in CASOS_DEGRADADOS else RESPUESTAS_BUENAS[e.scenario_id])
        for e in escenarios
    }
    caidos = frozenset(e.prompt for e in escenarios if e.scenario_id in caidos_ids)
    return AdapterFalso(respuestas, caidos)


def _correr(suite_y_casos, raiz, run_id, degradado=False, caidos_ids=(), suite=None):
    suite_base, escenarios = suite_y_casos
    target = EvalTarget(provider_id=f"falso-{run_id}")
    resultados = run_scenario_set(escenarios, target, _adapter(escenarios, degradado, caidos_ids), run_id)
    storage.save_run(
        run_id, resultados, target, root=raiz, suite=suite or suite_base, cases_hash=suite_base.suite_hash
    )
    return storage.load_run(run_id, root=raiz)


def test_cases_hash_se_persiste_y_scenarios_sin_suite_se_comparan(suite_y_casos, raiz):
    suite, escenarios = suite_y_casos
    corridas = {}
    for run_id, degradado in (("a", True), ("b", False)):
        target = EvalTarget(provider_id=f"falso-{run_id}")
        resultados = run_scenario_set(escenarios, target, _adapter(escenarios, degradado), run_id)
        storage.save_run(run_id, resultados, target, root=raiz, cases_hash=suite.suite_hash)
        corridas[run_id] = storage.load_run(run_id, root=raiz)
    assert corridas["a"]["cases_hash"] == suite.suite_hash and "suite" not in corridas["a"]
    assert compare_runs(corridas["a"], corridas["b"]).verdict == "candidate_better"


def test_output_largo_no_se_copia_completo_a_result_json(suite_y_casos, raiz):
    _, escenarios = suite_y_casos
    largo = "X" * 5000
    respuestas = {e.prompt: largo for e in escenarios}
    target = EvalTarget(provider_id="falso-largo")
    resultados = run_scenario_set(escenarios, target, AdapterFalso(respuestas), "largo")
    ruta = storage.save_run("largo", resultados, target, root=raiz)
    texto = ruta.read_text(encoding="utf-8")
    assert largo not in texto
    assert "X" * 600 not in texto  # excerpt (500) + detail (120) acotados, nunca el output completo
    assert "…[truncado]" in texto  # scorer_exact (casos con tipo exact) trunca el obtenido


def test_suite_publica_valida(suite_y_casos):
    suite, escenarios = suite_y_casos
    assert len(escenarios) >= 8
    assert set(RESPUESTAS_BUENAS) == set(suite.case_ids)


def test_baseline_buena_pasa_todo(suite_y_casos, raiz):
    corrida = _correr(suite_y_casos, raiz, "base")
    assert all(r["score"]["passed"] for r in corrida["resultados"])
    resumen = resumir(corrida["resultados"], corrida["suite"])
    assert resumen["pasaron"] == resumen["total"] and resumen["no_disponibles"] == 0


def test_candidate_better(suite_y_casos, raiz):
    baseline = _correr(suite_y_casos, raiz, "base", degradado=True)
    candidate = _correr(suite_y_casos, raiz, "cand")
    reporte = compare_runs(baseline, candidate)
    assert reporte.verdict == "candidate_better"
    assert {e["scenario_id"] for e in reporte.improvements} == CASOS_DEGRADADOS


def test_baseline_better(suite_y_casos, raiz):
    baseline = _correr(suite_y_casos, raiz, "base")
    candidate = _correr(suite_y_casos, raiz, "cand", degradado=True)
    assert compare_runs(baseline, candidate).verdict == "baseline_better"


def test_equivalent(suite_y_casos, raiz):
    baseline = _correr(suite_y_casos, raiz, "base")
    candidate = _correr(suite_y_casos, raiz, "cand")
    assert compare_runs(baseline, candidate).verdict == "equivalent"


def test_inconclusive_por_disponibilidad(suite_y_casos, raiz):
    baseline = _correr(suite_y_casos, raiz, "base", degradado=True)
    candidate = _correr(suite_y_casos, raiz, "cand", caidos_ids={"debugging-primer-paso"})
    reporte = compare_runs(baseline, candidate)
    assert reporte.verdict == "inconclusive"
    # La indisponibilidad no se disfraza de regresión de calidad.
    assert reporte.verdict != "baseline_better"
    resumen = resumir(candidate["resultados"], candidate["suite"])
    assert resumen["no_disponibles"] == 1


def test_inconclusive_por_suite_distinta(suite_y_casos, raiz):
    suite, _ = suite_y_casos
    otra = dataclasses.replace(suite, suite_version=suite.suite_version + 1)
    baseline = _correr(suite_y_casos, raiz, "base", degradado=True)
    candidate = _correr(suite_y_casos, raiz, "cand", suite=otra)
    assert compare_runs(baseline, candidate).verdict == "inconclusive"


def test_inconclusive_por_evaluator_distinto(suite_y_casos, raiz):
    baseline = _correr(suite_y_casos, raiz, "base", degradado=True)
    _correr(suite_y_casos, raiz, "cand")
    ruta = raiz / "cand" / "result.json"
    contenido = json.loads(ruta.read_text(encoding="utf-8"))
    contenido["evaluator_version"] = "harmessi-bench-scorers/999"
    ruta.write_text(json.dumps(contenido), encoding="utf-8")
    candidate = storage.load_run("cand", root=raiz)
    assert compare_runs(baseline, candidate).verdict == "inconclusive"


def test_load_run_lee_legado_sin_schema_version(raiz):
    directorio = raiz / "legado"
    directorio.mkdir(parents=True)
    legado = {
        "run_id": "legado",
        "resultados": [{"scenario_id": "a", "score": {"passed": True, "score": 1.0, "detail": ""}}],
    }
    (directorio / "result.json").write_text(json.dumps(legado), encoding="utf-8")
    cargado = storage.load_run("legado", root=raiz)
    assert "schema_version" not in cargado
    assert compare_runs(cargado, cargado).verdict == "equivalent"


def test_version_futura_falla(raiz):
    directorio = raiz / "futuro"
    directorio.mkdir(parents=True)
    (directorio / "result.json").write_text(
        json.dumps({"schema_version": storage.RESULT_SCHEMA_VERSION + 1, "resultados": []}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="schema_version"):
        storage.load_run("futuro", root=raiz)


def test_surface_under_test_protegida_se_rechaza(raiz):
    raiz.mkdir(parents=True)
    ruta = raiz / "casos protegidos.json"
    ruta.write_text(
        json.dumps(
            {
                "case_contract_version": 1,
                "escenarios": [
                    {
                        "scenario_id": "toca-guardrail",
                        "prompt": "p",
                        "expected": {"tipo": "exact", "valor": "x"},
                        "surface_under_test": "tools/dsguard/hook_rutas.py",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="toca-guardrail"):
        load_scenarios(ruta)


def test_result_json_sin_secretos_ni_rutas_personales(suite_y_casos, raiz):
    _correr(suite_y_casos, raiz, "base")
    texto = (raiz / "base" / "result.json").read_text(encoding="utf-8")
    _, escenarios = suite_y_casos
    for escenario in escenarios:
        assert escenario.prompt not in texto
    assert "ñandú" not in texto and "espacios" not in texto
    assert not re.search(r"[A-Za-z]:\\\\|/home/|/Users/|\\\\Users", texto)
    assert not re.search(r"(?i)api[_-]?key|secret|token|password|sk-[A-Za-z0-9]{8,}", texto)
    assert "@" not in texto


def test_suite_publica_sin_datos_personales_ni_rutas():
    for nombre in ("harmessi-core-synthetic.suite.json", "harmessi-core-synthetic.cases.json"):
        texto = (RUTA_SUITE.parent / nombre).read_text(encoding="utf-8")
        assert "@" not in texto
        assert not re.search(r"[A-Za-z]:\\\\|/home/|/Users/", texto)

"""Tests de `tools/harmessi_bench/compare.py`: los 5 casos de `compare_runs`."""
from __future__ import annotations

import pytest

from tools.harmessi_bench.compare import compare_runs


def _resultado(scenario_id: str, passed: bool) -> dict:
    return {
        "scenario_id": scenario_id,
        "score": {"passed": passed, "score": 1.0 if passed else 0.0, "detail": "detalle"},
    }


def test_compare_runs_cubre_los_5_casos():
    baseline = {
        "resultados": [
            _resultado("regresion", True),
            _resultado("mejora", False),
            _resultado("sin-cambio", True),
            _resultado("solo-baseline", True),
        ]
    }
    candidate = {
        "resultados": [
            _resultado("regresion", False),
            _resultado("mejora", True),
            _resultado("sin-cambio", True),
            _resultado("solo-candidate", False),
        ]
    }

    reporte = compare_runs(baseline, candidate)

    assert [entrada["scenario_id"] for entrada in reporte.regressions] == ["regresion"]
    assert [entrada["scenario_id"] for entrada in reporte.improvements] == ["mejora"]
    assert [entrada["scenario_id"] for entrada in reporte.unchanged] == ["sin-cambio"]
    assert reporte.solo_en_baseline == ["solo-baseline"]
    assert reporte.solo_en_candidate == ["solo-candidate"]


# --- v0.13 Change 1: veredicto ------------------------------------------------

_SUITE = {"suite_id": "s", "suite_version": 1, "suite_hash": "h1"}


def _corrida(resultados, suite=_SUITE, evaluator="ev/1") -> dict:
    corrida = {"resultados": resultados}
    if suite is not None:
        corrida["suite"] = dict(suite)
    if evaluator is not None:
        corrida["evaluator_version"] = evaluator
    return corrida


def _veredicto(baseline, candidate):
    reporte = compare_runs(baseline, candidate)
    return reporte.verdict, reporte


def test_veredicto_candidate_better():
    veredicto, reporte = _veredicto(
        _corrida([_resultado("a", False), _resultado("b", True)]),
        _corrida([_resultado("a", True), _resultado("b", True)]),
    )
    assert veredicto == "candidate_better"
    assert reporte.improvements and not reporte.regressions
    assert reporte.verdict_reason


def test_veredicto_baseline_better():
    veredicto, _ = _veredicto(
        _corrida([_resultado("a", True)]), _corrida([_resultado("a", False)])
    )
    assert veredicto == "baseline_better"


def test_veredicto_equivalent_aun_con_scores_fraccionales_distintos():
    baseline = _corrida([_resultado("a", True), _resultado("b", False)])
    candidate = _corrida([_resultado("a", True), _resultado("b", False)])
    candidate["resultados"][1]["score"]["score"] = 0.5
    veredicto, reporte = _veredicto(baseline, candidate)
    assert veredicto == "equivalent"
    assert not reporte.improvements and not reporte.regressions


def test_veredicto_inconclusive_regresion_y_mejora():
    veredicto, _ = _veredicto(
        _corrida([_resultado("a", True), _resultado("b", False)]),
        _corrida([_resultado("a", False), _resultado("b", True)]),
    )
    assert veredicto == "inconclusive"


def test_veredicto_inconclusive_sin_comunes_y_sets_distintos():
    assert _veredicto(_corrida([]), _corrida([]))[0] == "inconclusive"
    assert _veredicto(
        _corrida([_resultado("a", True)]), _corrida([_resultado("a", True), _resultado("b", True)])
    )[0] == "inconclusive"
    assert _veredicto(
        _corrida([_resultado("a", True), _resultado("b", True)]), _corrida([_resultado("a", True)])
    )[0] == "inconclusive"


@pytest.mark.parametrize("lado", ["baseline", "candidate"])
@pytest.mark.parametrize("falla", ["ok", "availability"])
def test_veredicto_inconclusive_por_disponibilidad(lado, falla):
    caido = _resultado("a", False)
    if falla == "ok":
        caido["ok"] = False
    else:
        caido["availability_error"] = "quota"
    sano = _resultado("a", True)
    baseline = _corrida([caido if lado == "baseline" else sano])
    candidate = _corrida([caido if lado == "candidate" else sano])
    assert _veredicto(baseline, candidate)[0] == "inconclusive"


def test_disponibilidad_en_escenario_no_comun_tambien_es_inconclusive():
    caido = _resultado("solo", False)
    caido["ok"] = False
    veredicto, _ = _veredicto(
        _corrida([_resultado("a", True)]), _corrida([_resultado("a", True), caido])
    )
    assert veredicto == "inconclusive"


@pytest.mark.parametrize("clave,valor", [("suite_id", "otra"), ("suite_version", 2), ("suite_hash", "h2")])
def test_veredicto_inconclusive_suite_distinta(clave, valor):
    suite_c = dict(_SUITE)
    suite_c[clave] = valor
    veredicto, _ = _veredicto(
        _corrida([_resultado("a", False)]), _corrida([_resultado("a", True)], suite=suite_c)
    )
    assert veredicto == "inconclusive"


def test_veredicto_inconclusive_solo_una_declara_suite():
    assert _veredicto(
        _corrida([_resultado("a", False)]), _corrida([_resultado("a", True)], suite=None)
    )[0] == "inconclusive"
    assert _veredicto(
        _corrida([_resultado("a", False)], suite=None), _corrida([_resultado("a", True)])
    )[0] == "inconclusive"


def test_veredicto_inconclusive_evaluator_distinto_o_solo_uno():
    assert _veredicto(
        _corrida([_resultado("a", False)]), _corrida([_resultado("a", True)], evaluator="ev/2")
    )[0] == "inconclusive"
    assert _veredicto(
        _corrida([_resultado("a", False)], evaluator=None), _corrida([_resultado("a", True)])
    )[0] == "inconclusive"
    assert _veredicto(
        _corrida([_resultado("a", False)]), _corrida([_resultado("a", True)], evaluator=None)
    )[0] == "inconclusive"


def test_dos_corridas_legadas_del_mismo_set_se_comparan_y_se_registra_la_nota():
    baseline = _corrida([_resultado("a", False)], suite=None, evaluator=None)
    candidate = _corrida([_resultado("a", True)], suite=None, evaluator=None)
    reporte = compare_runs(baseline, candidate)
    assert reporte.verdict == "candidate_better"
    assert "nota" in reporte.verdict_reason


def _sin_suite(resultados, cases_hash=None, evaluator="ev/1") -> dict:
    corrida = _corrida(resultados, suite=None, evaluator=evaluator)
    if cases_hash is not None:
        corrida["cases_hash"] = cases_hash
    return corrida


def test_sin_suite_cases_hash_igual_permite_comparar():
    v, _ = _veredicto(
        _sin_suite([_resultado("a", False)], "h"), _sin_suite([_resultado("a", True)], "h")
    )
    assert v == "candidate_better"


def test_sin_suite_cases_hash_distinto_o_solo_uno_es_inconclusive():
    assert _veredicto(
        _sin_suite([_resultado("a", False)], "h1"), _sin_suite([_resultado("a", True)], "h2")
    )[0] == "inconclusive"
    assert _veredicto(
        _sin_suite([_resultado("a", False)], "h1"), _sin_suite([_resultado("a", True)])
    )[0] == "inconclusive"
    assert _veredicto(
        _sin_suite([_resultado("a", False)]), _sin_suite([_resultado("a", True)], "h1")
    )[0] == "inconclusive"


def test_sin_suite_ni_hash_pero_con_evaluator_es_inconclusive():
    assert _veredicto(
        _sin_suite([_resultado("a", False)]), _sin_suite([_resultado("a", True)])
    )[0] == "inconclusive"


def test_cases_hash_distinto_con_suite_igual_es_inconclusive():
    baseline = _corrida([_resultado("a", False)])
    candidate = _corrida([_resultado("a", True)])
    baseline["cases_hash"], candidate["cases_hash"] = "h1", "h2"
    assert _veredicto(baseline, candidate)[0] == "inconclusive"


def test_scenario_id_duplicado_o_invalido_en_una_corrida():
    with pytest.raises(ValueError, match="duplicado"):
        compare_runs(_corrida([_resultado("a", True), _resultado("a", False)]), _corrida([]))
    for malo in (None, 5, ""):
        resultado = _resultado("a", True)
        resultado["scenario_id"] = malo
        with pytest.raises(ValueError, match="scenario_id"):
            compare_runs(_corrida([resultado]), _corrida([]))


def test_verdict_reason_incluye_n_y_pasados():
    _, reporte = _veredicto(
        _corrida([_resultado("a", False), _resultado("b", True)]),
        _corrida([_resultado("a", True), _resultado("b", True)]),
    )
    assert "n=2" in reporte.verdict_reason
    assert "baseline 1/2" in reporte.verdict_reason
    assert "candidate 2/2" in reporte.verdict_reason
    assert "una sola muestra" in reporte.verdict_reason


def test_equivalent_con_cero_pasados_en_ambos_avisa():
    v, reporte = _veredicto(_corrida([_resultado("a", False)]), _corrida([_resultado("a", False)]))
    assert v == "equivalent"
    assert "AVISO" in reporte.verdict_reason
    _, reporte_ok = _veredicto(_corrida([_resultado("a", True)]), _corrida([_resultado("a", True)]))
    assert "AVISO" not in reporte_ok.verdict_reason


def test_candidate_better_nunca_sin_mejora():
    # Barrido: ninguna combinación sin mejoras produce candidate_better.
    for passed_b in (True, False):
        for passed_c in (True, False):
            reporte = compare_runs(
                _corrida([_resultado("a", passed_b)]), _corrida([_resultado("a", passed_c)])
            )
            if reporte.verdict == "candidate_better":
                assert reporte.improvements


def test_comparison_report_defaults_retrocompatibles():
    from tools.harmessi_bench.compare import ComparisonReport

    reporte = ComparisonReport()
    assert reporte.verdict == "inconclusive"
    assert reporte.verdict_reason == ""


def test_compare_runs_resultado_sin_score_levanta_value_error():
    baseline = {
        "run_id": "run-mal-formado",
        "resultados": [{"scenario_id": "s1"}],
    }
    candidate = {"resultados": [_resultado("s1", True)]}

    with pytest.raises(ValueError, match="s1"):
        compare_runs(baseline, candidate)

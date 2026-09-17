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


def test_compare_runs_resultado_sin_score_levanta_value_error():
    baseline = {
        "run_id": "run-mal-formado",
        "resultados": [{"scenario_id": "s1"}],
    }
    candidate = {"resultados": [_resultado("s1", True)]}

    with pytest.raises(ValueError, match="s1"):
        compare_runs(baseline, candidate)

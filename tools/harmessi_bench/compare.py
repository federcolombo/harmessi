"""Comparación de dos corridas de eval (v0.5 Change 1, `harmessi-bench`).

Compara por `scenario_id`, nunca asume que ambas corridas comparten el mismo
set de escenarios -- ver `solo_en_baseline`/`solo_en_candidate`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class ComparisonReport:
    regressions: List[dict] = field(default_factory=list)
    improvements: List[dict] = field(default_factory=list)
    unchanged: List[dict] = field(default_factory=list)
    solo_en_baseline: List[str] = field(default_factory=list)
    solo_en_candidate: List[str] = field(default_factory=list)


def _indexar_por_scenario_id(corrida: dict) -> dict:
    run_id = corrida.get("run_id")
    indice = {}
    for resultado in corrida.get("resultados", []):
        scenario_id = resultado.get("scenario_id")
        score = resultado.get("score")
        if not isinstance(score, dict) or "passed" not in score:
            raise ValueError(
                f"resultado mal formado para scenario_id={scenario_id!r}: falta 'score'/"
                f"'score.passed' (run_id={run_id!r})"
            )
        indice[scenario_id] = resultado
    return indice


def compare_runs(baseline: dict, candidate: dict) -> ComparisonReport:
    """Compara los `resultados` (ya cargados vía `storage.load_run`) de dos
    corridas por `scenario_id`, clasificando cada escenario común en
    regression/improvement/unchanged según `score.passed`, y reportando por
    separado los escenarios presentes en un solo lado."""
    indice_baseline = _indexar_por_scenario_id(baseline)
    indice_candidate = _indexar_por_scenario_id(candidate)

    reporte = ComparisonReport()

    ids_comunes = set(indice_baseline) & set(indice_candidate)
    for scenario_id in sorted(ids_comunes):
        resultado_baseline = indice_baseline[scenario_id]
        resultado_candidate = indice_candidate[scenario_id]
        passed_baseline = resultado_baseline["score"]["passed"]
        passed_candidate = resultado_candidate["score"]["passed"]

        entrada = {
            "scenario_id": scenario_id,
            "baseline_passed": passed_baseline,
            "candidate_passed": passed_candidate,
        }

        if passed_baseline and not passed_candidate:
            reporte.regressions.append(entrada)
        elif not passed_baseline and passed_candidate:
            reporte.improvements.append(entrada)
        else:
            reporte.unchanged.append(entrada)

    reporte.solo_en_baseline = sorted(set(indice_baseline) - set(indice_candidate))
    reporte.solo_en_candidate = sorted(set(indice_candidate) - set(indice_baseline))

    return reporte

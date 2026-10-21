"""Comparación de dos corridas de eval (v0.5 Change 1, `harmessi-bench`;
veredicto agregado en v0.13 Change 1).

Compara por `scenario_id`, nunca asume que ambas corridas comparten el mismo
set de escenarios -- ver `solo_en_baseline`/`solo_en_candidate`.

Veredicto (`candidate_better`/`baseline_better`/`equivalent`/`inconclusive`):
conservador, ante duda `inconclusive`. Usa únicamente `score.passed`
determinista (sin LLM-as-judge). Puro: sin providers, `subprocess` ni red.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from tools.harmessi_bench import runmanifest

VEREDICTO_CANDIDATE_MEJOR = "candidate_better"
VEREDICTO_BASELINE_MEJOR = "baseline_better"
VEREDICTO_EQUIVALENTE = "equivalent"
VEREDICTO_INCONCLUSO = "inconclusive"
VEREDICTOS = (
    VEREDICTO_CANDIDATE_MEJOR,
    VEREDICTO_BASELINE_MEJOR,
    VEREDICTO_EQUIVALENTE,
    VEREDICTO_INCONCLUSO,
)

_CLAVES_SUITE = ("suite_id", "suite_version", "suite_hash")

# Claves del manifest que deben coincidir para que la comparación tenga
# sentido (mismo contrato de manifest, mismo evaluador, mismos casos).
_CLAVES_MANIFEST_NO_COMPARABLES = ("manifest_version", "evaluator_version", "suite", "cases_hash")


@dataclass
class ComparisonReport:
    regressions: List[dict] = field(default_factory=list)
    improvements: List[dict] = field(default_factory=list)
    unchanged: List[dict] = field(default_factory=list)
    solo_en_baseline: List[str] = field(default_factory=list)
    solo_en_candidate: List[str] = field(default_factory=list)
    verdict: str = VEREDICTO_INCONCLUSO
    verdict_reason: str = ""
    # Claves materiales que difieren entre los run_manifest (v0.13 Change 2);
    # vacía si falta alguno de los dos manifests.
    config_diff: List[str] = field(default_factory=list)


def _indexar_por_scenario_id(corrida: dict) -> dict:
    run_id = corrida.get("run_id")
    indice = {}
    for resultado in corrida.get("resultados", []):
        scenario_id = resultado.get("scenario_id")
        if not isinstance(scenario_id, str) or not scenario_id:
            raise ValueError(
                f"resultado con scenario_id ausente o no string: {scenario_id!r} (run_id={run_id!r})"
            )
        if scenario_id in indice:
            raise ValueError(f"scenario_id duplicado {scenario_id!r} en la corrida (run_id={run_id!r})")
        score = resultado.get("score")
        if not isinstance(score, dict) or "passed" not in score:
            raise ValueError(
                f"resultado mal formado para scenario_id={scenario_id!r}: falta 'score'/"
                f"'score.passed' (run_id={run_id!r})"
            )
        indice[scenario_id] = resultado
    return indice


def _hay_indisponibilidad(corrida: dict) -> bool:
    """`True` si algún resultado tiene `ok=False` o `availability_error`
    (disponibilidad != calidad: no se puede atribuir a la calidad)."""
    for resultado in corrida.get("resultados", []):
        if resultado.get("ok", True) is False or resultado.get("availability_error"):
            return True
    return False


def _motivos_inconclusos(baseline: dict, candidate: dict, reporte: ComparisonReport, hay_comunes: bool):
    """Lista de motivos por los que no se puede decidir (R13), más una lista
    de notas informativas (metadata de comparabilidad ausente en ambos lados)."""
    motivos: List[str] = []
    notas: List[str] = []

    if not hay_comunes:
        motivos.append("no hay escenarios comunes")
    if reporte.solo_en_baseline or reporte.solo_en_candidate:
        motivos.append("los sets de escenarios difieren (solo_en_baseline/solo_en_candidate)")
    if _hay_indisponibilidad(baseline) or _hay_indisponibilidad(candidate):
        motivos.append("hay resultados con indisponibilidad o invocación no exitosa (ok=False/availability_error)")

    suite_b = baseline.get("suite")
    suite_c = candidate.get("suite")
    hash_b = baseline.get("cases_hash")
    hash_c = candidate.get("cases_hash")
    if hash_b is not None and hash_c is not None and hash_b != hash_c:
        motivos.append("cases_hash distinto: las corridas usaron contenido de casos distinto")

    if suite_b is None and suite_c is None:
        # Sin suite, la identidad de los casos la da `cases_hash` (corridas con --scenarios).
        if hash_b is not None and hash_c is not None:
            notas.append("ninguna corrida declara suite; cases_hash coincide")
        elif hash_b is not None or hash_c is not None:
            motivos.append("sin suite y solo una corrida declara cases_hash")
        elif baseline.get("evaluator_version") is not None or candidate.get("evaluator_version") is not None:
            motivos.append("sin suite ni cases_hash: no se puede verificar que los casos sean los mismos")
        else:
            notas.append("ninguna corrida declara suite ni cases_hash (corridas legadas)")
    elif suite_b is None or suite_c is None:
        motivos.append("solo una de las corridas declara suite")
    elif not isinstance(suite_b, dict) or not isinstance(suite_c, dict) or any(
        suite_b.get(clave) != suite_c.get(clave) for clave in _CLAVES_SUITE
    ):
        motivos.append("las corridas declaran suites distintas (suite_id/suite_version/suite_hash)")

    evaluador_b = baseline.get("evaluator_version")
    evaluador_c = candidate.get("evaluator_version")
    if evaluador_b is None and evaluador_c is None:
        notas.append("ninguna corrida declara evaluator_version (corridas legadas)")
    elif evaluador_b is None or evaluador_c is None:
        motivos.append("solo una de las corridas declara evaluator_version (corrida legada)")
    elif evaluador_b != evaluador_c:
        motivos.append(f"evaluator_version distinto ({evaluador_b!r} vs {evaluador_c!r})")

    _motivos_manifest(baseline, candidate, motivos, notas)

    if reporte.regressions and reporte.improvements:
        motivos.append("hay a la vez regresiones y mejoras")
    return motivos, notas


def _motivos_manifest(baseline: dict, candidate: dict, motivos: List[str], notas: List[str]) -> None:
    """Reglas de comparabilidad por `run_manifest` (v0.13 Change 2, R8/R9).
    Sin manifest en ninguno: no cambia nada (corridas del Change 1/legadas).
    Skills/superficies/provider/model/guardrails/harmessi_version pueden
    diferir (es lo que se evalúa): se listan en `config_diff`, no inhiben."""
    man_b = baseline.get("run_manifest")
    man_c = candidate.get("run_manifest")
    if man_b is None and man_c is None:
        return
    if man_b is None or man_c is None:
        motivos.append("solo una de las corridas tiene run_manifest")
        return
    incompletos = False
    for etiqueta, manifest in (("baseline", man_b), ("candidate", man_c)):
        faltantes = runmanifest.campos_faltantes(manifest)
        if faltantes:
            incompletos = True
            motivos.append(f"run_manifest de {etiqueta} incompleto o inválido (faltan: {', '.join(faltantes)})")
    if incompletos:
        return
    for clave in _CLAVES_MANIFEST_NO_COMPARABLES:
        if man_b.get(clave) != man_c.get(clave):
            motivos.append(f"run_manifest: {clave} distinto entre baseline y candidate")
    if man_b.get("identity_hash") == man_c.get("identity_hash"):
        notas.append("misma configuración material: repetición")


def _decidir_veredicto(baseline: dict, candidate: dict, reporte: ComparisonReport, hay_comunes: bool):
    motivos, notas = _motivos_inconclusos(baseline, candidate, reporte, hay_comunes)
    comunes = reporte.regressions + reporte.improvements + reporte.unchanged
    n = len(comunes)
    pasan_b = sum(1 for e in comunes if e["baseline_passed"])
    pasan_c = sum(1 for e in comunes if e["candidate_passed"])
    muestra = f"n={n}; pasan baseline {pasan_b}/{n}, candidate {pasan_c}/{n}; una sola muestra"
    sufijo = f" [nota: {'; '.join(notas)}]" if notas else ""
    if motivos:
        return VEREDICTO_INCONCLUSO, "; ".join(motivos) + (f" ({muestra})" if n else "")
    if reporte.regressions:
        return (
            VEREDICTO_BASELINE_MEJOR,
            f"{len(reporte.regressions)} regresión(es) y ninguna mejora ({muestra}){sufijo}",
        )
    if reporte.improvements:
        # R15: candidate_better solo con al menos una mejora medida (aquí hay >= 1).
        return (
            VEREDICTO_CANDIDATE_MEJOR,
            f"{len(reporte.improvements)} mejora(s) y ninguna regresión ({muestra}){sufijo}",
        )
    aviso = ""
    if pasan_b == 0 and pasan_c == 0:
        aviso = " AVISO: ningún caso pasa en ninguna de las dos corridas; la equivalencia no es informativa."
    return VEREDICTO_EQUIVALENTE, f"sin diferencias en score.passed ({muestra}){sufijo}.{aviso}"


def compare_runs(baseline: dict, candidate: dict) -> ComparisonReport:
    """Compara los `resultados` (ya cargados vía `storage.load_run`) de dos
    corridas por `scenario_id`, clasificando cada escenario común en
    regression/improvement/unchanged según `score.passed`, y reportando por
    separado los escenarios presentes en un solo lado. Agrega `verdict` y
    `verdict_reason` (ver docstring del módulo)."""
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

    man_b = baseline.get("run_manifest")
    man_c = candidate.get("run_manifest")
    if isinstance(man_b, dict) and isinstance(man_c, dict):
        reporte.config_diff = runmanifest.diferencias_materiales(man_b, man_c)

    reporte.verdict, reporte.verdict_reason = _decidir_veredicto(
        baseline, candidate, reporte, bool(ids_comunes)
    )
    return reporte

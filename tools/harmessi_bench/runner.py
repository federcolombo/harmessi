"""Ejecución de escenarios contra un target (v0.5 Change 1, `harmessi-bench`).

Reusa el contrato neutral de `tools.providers.core` (Change 0): arma un
`InvocationRequest` por escenario y delega en `adapter.invoke(...)`, sin
conocer el vocabulario de flags de ningún proveedor concreto. Distingue
explícitamente indisponibilidad (`resultado.ok is False`) de mala calidad de
output (scoring) -- ver `EvalResult` en `core.py` para el porqué.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import List

from tools.ds_init.version import HARNESS_VERSION
from tools.harmessi_bench.core import (
    EvalResult,
    EvalTarget,
    Scenario,
    ScoreResult,
    aplicar_scorer,
)
from tools.providers.core import InvocationRequest

_MAX_EXCERPT = 500


def run_scenario(scenario: Scenario, target: EvalTarget, adapter, run_id: str) -> EvalResult:
    """Corre un único escenario contra `target` usando `adapter` (una
    instancia de `tools.providers.core.ProviderAdapter`). No abortar la
    corrida general si este escenario falla queda a cargo de
    `run_scenario_set`, no de esta función."""
    request = InvocationRequest(
        prompt=scenario.prompt,
        role="eval",
        model=target.model,
        effort=target.effort,
    )
    resultado = adapter.invoke(request)
    timestamp_utc = datetime.now(timezone.utc).isoformat()

    if not resultado.ok:
        detail = (
            f"invocacion no exitosa (availability_error={resultado.availability_error!r}): "
            f"{resultado.stderr[:300]}"
        )
        return EvalResult(
            run_id=run_id,
            scenario_id=scenario.scenario_id,
            target=target,
            exit_code=resultado.exit_code,
            ok=False,
            availability_error=resultado.availability_error,
            duration_s=resultado.duration_s,
            stdout_excerpt="",
            score=ScoreResult(passed=False, score=0.0, detail=detail),
            harmessi_version=HARNESS_VERSION,
            timestamp_utc=timestamp_utc,
        )

    texto = resultado.stdout
    try:
        parseado = json.loads(resultado.stdout)
        if isinstance(parseado, dict) and "result" in parseado:
            texto = parseado["result"]
            if not isinstance(texto, str):
                texto = str(texto)
    except (json.JSONDecodeError, TypeError):
        # stdout no era JSON válido -- se scorea el texto crudo, sin crashear.
        pass

    score = aplicar_scorer(texto, scenario.expected)

    return EvalResult(
        run_id=run_id,
        scenario_id=scenario.scenario_id,
        target=target,
        exit_code=resultado.exit_code,
        ok=True,
        availability_error=None,
        duration_s=resultado.duration_s,
        stdout_excerpt=str(texto)[:_MAX_EXCERPT],
        score=score,
        harmessi_version=HARNESS_VERSION,
        timestamp_utc=timestamp_utc,
    )


def run_scenario_set(
    scenarios: List[Scenario], target: EvalTarget, adapter, run_id: str
) -> List[EvalResult]:
    """Corre todos los escenarios contra `target`. Un error interno
    inesperado en un escenario individual (p. ej. `expected` mal formado) se
    captura y registra como un `EvalResult` fallido, sin abortar el resto de
    la corrida."""
    resultados: List[EvalResult] = []
    for scenario in scenarios:
        try:
            resultados.append(run_scenario(scenario, target, adapter, run_id))
        except Exception as exc:  # noqa: BLE001 - un escenario roto no debe abortar la corrida
            resultados.append(
                EvalResult(
                    run_id=run_id,
                    scenario_id=getattr(scenario, "scenario_id", "desconocido"),
                    target=target,
                    exit_code=-1,
                    ok=False,
                    availability_error=None,
                    duration_s=0.0,
                    stdout_excerpt="",
                    score=ScoreResult(
                        passed=False, score=0.0, detail=f"error interno ejecutando escenario: {exc!r}"
                    ),
                    harmessi_version=HARNESS_VERSION,
                    timestamp_utc=datetime.now(timezone.utc).isoformat(),
                )
            )
    return resultados

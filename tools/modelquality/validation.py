"""Evaluación determinista de `ModelQualityPolicy` contra métricas ya reportadas
(v0.7 Change 2, `20260922-model-quality-policies`). Sibling de `core.py`, mismo
Change (a diferencia de `tools/datacontracts`, este paquete entrega declaración
y evaluación juntas -- ver `design.md`).

Una única función pública:

- `evaluate_policy(policy, observed_metrics, baselines=()) -> list[CheckResult]`:
  pura, sin I/O, sin `Path`, sin ningún guard de holdout (no hay superficie de
  archivo en este Change: `ObservedMetric`/`BaselineReference` se reciben
  siempre como objetos ya construidos en memoria). Nunca lanza.

Orden de evaluación fijo por `MetricRequirement` (R14 de `spec.md`, decisión 6
de `design.md`): selección de `ObservedMetric` (por `metric_name` + contexto)
-> evidencia vigente (evidence_ref/uncertainty/sample_size) -> threshold ->
baseline/reference -> `QUALITY-RESULT` (fold monotónico: cada etapa solo puede
empeorar el resultado, nunca mejorarlo).

Frontera de imports (R1 de `spec.md`, verificada por
`tools/tests/test_v07_modelquality_neutrality.py`): stdlib + `dsguard.checks` +
`tools.modelquality.core` (sibling). Sin `tools.datacontracts`, sin
`ds_profile`, sin pandas/numpy, sin ningún otro paquete de `tools/`.

Este módulo NO recalcula ni verifica que el valor reportado (`ObservedMetric.value`)
sea numéricamente correcto (decisión 1 del roadmap v0.7): solo compara el
número ya reportado contra threshold/baseline, y verifica la vigencia
ESTRUCTURAL de su evidencia (presencia de `evidence_ref`, forma de
`uncertainty`, presencia/magnitud de `sample_size`) -- nunca criptográfica ni
de frescura temporal (eso es Change 3).

Vocabulario `PASS`/`WARN`/`FAIL`/`N/A`: nunca `PASS` por falta de evidencia
(R15). Toda excepción inesperada al evaluar un `MetricRequirement` individual
se convierte en `checks.resultado_de_excepcion(f"QUALITY-{requirement_id}", exc)`
(código final `QUALITY-<requirement_id>-EXCEPCION`, `kind="technical_error"`),
sin propagar ni impedir que se evalúen los demás requirements.

Privacidad: ningún `CheckResult` (message/detail/subject) interpola el
contenido de `evidence_ref` como si fuera confiable/ejecutable; solo se
reporta su presencia/ausencia.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional

_TOOLS_DIR = Path(__file__).resolve().parents[1]
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from dsguard import checks  # noqa: E402

from . import core as modelquality_core  # noqa: E402

# --- Códigos (R12 de spec.md) --------------------------------------------------

CODE_INPUT = "QUALITY-INPUT"
CODE_METRIC_MISSING = "QUALITY-METRIC-MISSING"
CODE_CONTEXT_MISMATCH = "QUALITY-CONTEXT-MISMATCH"
CODE_METRIC_AMBIGUOUS = "QUALITY-METRIC-AMBIGUOUS"
CODE_EVIDENCE_MISSING = "QUALITY-EVIDENCE-MISSING"
CODE_UNCERTAINTY_MISSING = "QUALITY-UNCERTAINTY-MISSING"
CODE_SAMPLE_SIZE = "QUALITY-SAMPLE-SIZE"
CODE_THRESHOLD = "QUALITY-THRESHOLD"
CODE_BASELINE_MISSING = "QUALITY-BASELINE-MISSING"
CODE_BASELINE = "QUALITY-BASELINE"
CODE_RESULT = "QUALITY-RESULT"

CODES = (
    CODE_INPUT,
    CODE_METRIC_MISSING,
    CODE_CONTEXT_MISMATCH,
    CODE_METRIC_AMBIGUOUS,
    CODE_EVIDENCE_MISSING,
    CODE_UNCERTAINTY_MISSING,
    CODE_SAMPLE_SIZE,
    CODE_THRESHOLD,
    CODE_BASELINE_MISSING,
    CODE_BASELINE,
    CODE_RESULT,
)

# --- Fold monotónico (decisión 6 de design.md) -------------------------------

_RANGO_SEVERIDAD = {"PASS": 0, "WARN": 1, "FAIL": 2}


def _peor(a: str, b: str) -> str:
    """El más severo entre dos status PASS/WARN/FAIL (nunca recibe N/A)."""
    return a if _RANGO_SEVERIDAD[a] >= _RANGO_SEVERIDAD[b] else b


def _acumular(statuses_en_orden: list) -> str:
    """Pliega una lista de status (algunos pueden ser 'N/A') en un único
    resultado final, respetando el orden recibido: los N/A se ignoran (ni
    empeoran ni mejoran); si TODOS son N/A, el resultado final es N/A; si no,
    es el peor de los no-N/A, considerados en el orden dado (la función nunca
    'mejora' un resultado ya alcanzado -- solo puede igualarlo o empeorarlo al
    incorporar la siguiente etapa)."""
    final = None
    for status in statuses_en_orden:
        if status == checks.STATUS_NA:
            continue
        final = status if final is None else _peor(final, status)
    return checks.STATUS_NA if final is None else final


# --- Helpers privados -----------------------------------------------------------


def _res(
    status: str,
    code: str,
    message: str,
    subject: Optional[str] = None,
    *,
    tecnico: bool = False,
    detail: Optional[str] = None,
) -> checks.CheckResult:
    return checks.CheckResult(
        status=status,
        code=code,
        message=message,
        detail=detail,
        subject=subject,
        kind=checks.KIND_TECHNICAL_ERROR if tecnico else checks.KIND_CHECK,
    )


def _coincide_contexto(observado_contexto: Any, requerido: "modelquality_core.EvaluationContext") -> bool:
    """Coincidencia de contexto (R14.1/decisión 4 de design.md): `split`
    obligatorio, `population` opcional (solo se compara si `requerido.population`
    no es vacío). `context_id` de ambos lados NUNCA se compara."""
    if observado_contexto.split != requerido.split:
        return False
    if requerido.population == "":
        return True
    return observado_contexto.population == requerido.population


def _seleccionar_candidato(candidatos: list, metric_name: str, required_context: Any):
    """Selección compartida (R14.1/R14.4) para `ObservedMetric` y
    `BaselineReference`: filtra por `metric_name`, luego por coincidencia de
    contexto. Devuelve `(resultado, elegido)` con `resultado` en
    `{"missing", "mismatch", "ambiguous", "ok"}`; `elegido` es `None` salvo en
    `"ok"`."""
    por_nombre = [c for c in candidatos if c.metric_name == metric_name]
    if not por_nombre:
        return "missing", None
    coincidentes = [c for c in por_nombre if _coincide_contexto(c.context, required_context)]
    if not coincidentes:
        return "mismatch", None
    if len(coincidentes) > 1:
        return "ambiguous", None
    return "ok", coincidentes[0]


def _forma_uncertainty_valida(uncertainty: Any) -> bool:
    """`True` sii `uncertainty` tiene una forma válida según R7 -- reusa el
    validador de `core.py` (misma regla, sin duplicar lógica), capturando su
    excepción como señal de forma inválida (nunca propaga: esta función
    siempre corre dentro de `evaluate_policy`, que ya nunca lanza)."""
    if uncertainty is None:
        return False
    try:
        modelquality_core._validar_uncertainty(uncertainty, "uncertainty")
        return True
    except modelquality_core.ModelQualityError:
        return False


def _comparar_baseline(requirement: Any, observado: Any, baseline: Any) -> str:
    """Aplica `requirement.comparison_mode` (R14.4/decisión 3 de design.md).
    Devuelve `PASS`, `requirement.baseline_severity`, o `WARN` si
    `relative_to_baseline` con `baseline.value == 0` (no verificable, nunca
    excepción)."""
    v = observado.value
    b = baseline.value
    t = requirement.comparison_tolerance if requirement.comparison_tolerance is not None else 0.0
    modo = requirement.comparison_mode
    direccion = requirement.direction

    if modo == "absolute":
        if direccion == "higher_is_better":
            cumple = v >= b - t
        else:
            cumple = v <= b + t
        return checks.STATUS_PASS if cumple else requirement.baseline_severity

    if modo == "absolute_diff_from_baseline":
        cumple = abs(v - b) <= t
        return checks.STATUS_PASS if cumple else requirement.baseline_severity

    # modo == "relative_to_baseline"
    if b == 0:
        return checks.STATUS_WARN
    if direccion == "higher_is_better":
        cumple = (v - b) / b >= -t
    else:
        cumple = (v - b) / b <= t
    return checks.STATUS_PASS if cumple else requirement.baseline_severity


# --- Evaluación de un MetricRequirement (R14) ------------------------------------


def _evaluar_requirement(requirement: Any, observed_metrics: list, baselines: list) -> list:
    resultados: list = []
    sujeto = requirement.requirement_id

    # 1. Selección de ObservedMetric.
    resultado_sel, observado = _seleccionar_candidato(
        observed_metrics, requirement.metric_name, requirement.required_context
    )
    if resultado_sel == "missing":
        resultados.append(
            _res(
                checks.STATUS_FAIL,
                CODE_METRIC_MISSING,
                f"Ningún ObservedMetric reporta metric_name={requirement.metric_name!r} para el "
                f"requirement {sujeto!r}.",
                sujeto,
            )
        )
        resultados.append(
            _res(checks.STATUS_FAIL, CODE_RESULT, "Resultado final: métrica no reportada.", sujeto)
        )
        return resultados
    if resultado_sel == "mismatch":
        resultados.append(
            _res(
                checks.STATUS_FAIL,
                CODE_CONTEXT_MISMATCH,
                f"Hay ObservedMetric con metric_name={requirement.metric_name!r} pero ninguno "
                f"coincide con el contexto requerido por {sujeto!r}.",
                sujeto,
            )
        )
        resultados.append(
            _res(checks.STATUS_FAIL, CODE_RESULT, "Resultado final: contexto no coincide.", sujeto)
        )
        return resultados
    if resultado_sel == "ambiguous":
        resultados.append(
            _res(
                checks.STATUS_WARN,
                CODE_METRIC_AMBIGUOUS,
                f"Más de un ObservedMetric coincide en metric_name={requirement.metric_name!r} y "
                f"contexto para {sujeto!r}: no verificable cuál gobierna.",
                sujeto,
            )
        )
        resultados.append(
            _res(checks.STATUS_WARN, CODE_RESULT, "Resultado final: selección ambigua.", sujeto)
        )
        return resultados

    # Selección exitosa: `observado` es el ObservedMetric a usar de acá en más.

    # 2. Evidencia vigente.
    status_evidencia_sub = []

    status_evidencia_missing = (
        checks.STATUS_PASS if observado.evidence_ref else checks.STATUS_WARN
    )
    resultados.append(
        _res(
            status_evidencia_missing,
            CODE_EVIDENCE_MISSING,
            (
                "El ObservedMetric declara evidence_ref."
                if status_evidencia_missing == checks.STATUS_PASS
                else "El ObservedMetric no declara evidence_ref (o está vacío): no verificable."
            ),
            sujeto,
        )
    )
    status_evidencia_sub.append(status_evidencia_missing)

    if requirement.uncertainty_required:
        forma_valida = _forma_uncertainty_valida(observado.uncertainty)
        status_uncertainty = checks.STATUS_PASS if forma_valida else checks.STATUS_WARN
        resultados.append(
            _res(
                status_uncertainty,
                CODE_UNCERTAINTY_MISSING,
                (
                    "El ObservedMetric declara uncertainty con forma válida."
                    if forma_valida
                    else "El requirement exige uncertainty y el ObservedMetric no la declara (o su "
                    "forma es inválida)."
                ),
                sujeto,
            )
        )
        status_evidencia_sub.append(status_uncertainty)

    if requirement.min_sample_size is not None:
        if observado.sample_size is None:
            status_sample = checks.STATUS_WARN
            mensaje_sample = "El requirement exige min_sample_size y el ObservedMetric no reporta sample_size."
        elif observado.sample_size < requirement.min_sample_size:
            status_sample = checks.STATUS_FAIL
            mensaje_sample = (
                f"sample_size observado ({observado.sample_size}) es menor que min_sample_size "
                f"requerido ({requirement.min_sample_size})."
            )
        else:
            status_sample = checks.STATUS_PASS
            mensaje_sample = (
                f"sample_size observado ({observado.sample_size}) cumple min_sample_size "
                f"({requirement.min_sample_size})."
            )
        resultados.append(_res(status_sample, CODE_SAMPLE_SIZE, mensaje_sample, sujeto))
        status_evidencia_sub.append(status_sample)

    status_evidencia = _acumular(status_evidencia_sub)

    # 3. Threshold.
    if requirement.threshold_value is None:
        status_threshold = checks.STATUS_NA
        resultados.append(
            _res(checks.STATUS_NA, CODE_THRESHOLD, "El requirement no declara threshold_value.", sujeto)
        )
    else:
        if requirement.direction == "higher_is_better":
            cumple = observado.value >= requirement.threshold_value
        else:
            cumple = observado.value <= requirement.threshold_value
        status_threshold = checks.STATUS_PASS if cumple else requirement.threshold_severity
        resultados.append(
            _res(
                status_threshold,
                CODE_THRESHOLD,
                (
                    f"El valor observado ({observado.value!r}) cumple threshold_value "
                    f"({requirement.threshold_value!r}, direction={requirement.direction!r})."
                    if cumple
                    else f"El valor observado ({observado.value!r}) no cumple threshold_value "
                    f"({requirement.threshold_value!r}, direction={requirement.direction!r})."
                ),
                sujeto,
            )
        )

    # 4. Baseline/reference.
    if not requirement.baseline_required:
        status_baseline = checks.STATUS_NA
    else:
        resultado_sel_b, baseline_sel = _seleccionar_candidato(
            baselines, requirement.metric_name, requirement.required_context
        )
        if resultado_sel_b != "ok":
            status_baseline = requirement.baseline_severity
            resultados.append(
                _res(
                    status_baseline,
                    CODE_BASELINE_MISSING,
                    f"No hay exactamente un BaselineReference con metric_name="
                    f"{requirement.metric_name!r} y contexto coincidente para {sujeto!r} "
                    f"(selección: {resultado_sel_b}).",
                    sujeto,
                )
            )
        else:
            status_baseline = _comparar_baseline(requirement, observado, baseline_sel)
            resultados.append(
                _res(
                    status_baseline,
                    CODE_BASELINE,
                    f"Comparación contra baseline (comparison_mode={requirement.comparison_mode!r}) "
                    f"con resultado {status_baseline!r}.",
                    sujeto,
                )
            )

    # 5. QUALITY-RESULT: fold monotónico evidencia -> threshold -> baseline.
    status_final = _acumular([status_evidencia, status_threshold, status_baseline])
    resultados.append(
        _res(status_final, CODE_RESULT, "Resultado final del requirement (fold monotónico).", sujeto)
    )
    return resultados


# --- Gate de entrada (R13) -------------------------------------------------------


def _validar_input(policy: Any, observed_metrics: Any, baselines: Any) -> Optional[checks.CheckResult]:
    if not isinstance(policy, modelquality_core.ModelQualityPolicy):
        return _res(
            checks.STATUS_FAIL,
            CODE_INPUT,
            f"'policy' no es una instancia de ModelQualityPolicy (se recibió "
            f"{type(policy).__name__}).",
            tecnico=True,
        )
    if not isinstance(observed_metrics, (list, tuple)):
        return _res(
            checks.STATUS_FAIL,
            CODE_INPUT,
            f"'observed_metrics' no es list ni tuple (se recibió {type(observed_metrics).__name__}).",
            tecnico=True,
        )
    for i, elemento in enumerate(observed_metrics):
        if not isinstance(elemento, modelquality_core.ObservedMetric):
            return _res(
                checks.STATUS_FAIL,
                CODE_INPUT,
                f"observed_metrics[{i}] no es una instancia de ObservedMetric (se recibió "
                f"{type(elemento).__name__}).",
                tecnico=True,
            )
    if not isinstance(baselines, (list, tuple)):
        return _res(
            checks.STATUS_FAIL,
            CODE_INPUT,
            f"'baselines' no es list ni tuple (se recibió {type(baselines).__name__}).",
            tecnico=True,
        )
    for i, elemento in enumerate(baselines):
        if not isinstance(elemento, modelquality_core.BaselineReference):
            return _res(
                checks.STATUS_FAIL,
                CODE_INPUT,
                f"baselines[{i}] no es una instancia de BaselineReference (se recibió "
                f"{type(elemento).__name__}).",
                tecnico=True,
            )
    return None


# --- Función pública (R13) ----------------------------------------------------


def _evaluate_policy_interno(policy: Any, observed_metrics: Any, baselines: Any) -> list:
    problema = _validar_input(policy, observed_metrics, baselines)
    if problema is not None:
        return [problema]

    resultados: list = []
    for requirement in policy.requirements:
        try:
            resultados.extend(_evaluar_requirement(requirement, observed_metrics, baselines))
        except Exception as exc:  # noqa: BLE001 -- nunca debe escapar de un requirement individual
            resultados.append(checks.resultado_de_excepcion(f"QUALITY-{requirement.requirement_id}", exc))
    return resultados


def evaluate_policy(policy: Any, observed_metrics: Any, baselines: Any = ()) -> list:
    """Pura: sin I/O, sin `Path`, sin ningún guard. `observed_metrics`/`baselines`
    son listas/tuplas de objetos YA construidos en memoria. Nunca lanza -- ver
    docstring del módulo."""
    try:
        return _evaluate_policy_interno(policy, observed_metrics, baselines)
    except Exception as exc:  # noqa: BLE001 -- contrato: nunca lanza
        return [checks.resultado_de_excepcion("QUALITY-EVALUATE", exc)]

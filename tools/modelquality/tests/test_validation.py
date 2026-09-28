"""Tests de `tools.modelquality.validation` (v0.7 Change 2). Fixtures 100%
sintéticas (nunca un dataset ni modelo real). Cubre R12-R16 de `spec.md`."""
from __future__ import annotations

import unittest
from unittest import mock

from dsguard import checks

from tools.modelquality import core as mq
from tools.modelquality import validation as mqv


def _contexto(**kwargs) -> mq.EvaluationContext:
    base = {"context_id": "ctx_test", "split": "test"}
    base.update(kwargs)
    return mq.EvaluationContext(**base)


def _requirement(**kwargs) -> mq.MetricRequirement:
    base = {
        "requirement_id": "req_auc",
        "metric_name": "roc_auc",
        "direction": "higher_is_better",
        "required_context": _contexto(),
        "threshold_value": 0.75,
    }
    base.update(kwargs)
    return mq.MetricRequirement(**base)


def _policy(*requirements, **kwargs) -> mq.ModelQualityPolicy:
    base = {
        "policy_id": "policy_demo",
        "model_task_role": "classification",
        "requirements": requirements or (_requirement(),),
    }
    base.update(kwargs)
    return mq.ModelQualityPolicy(**base)


def _observado(**kwargs) -> mq.ObservedMetric:
    base = {"metric_name": "roc_auc", "value": 0.90, "context": _contexto(), "evidence_ref": "run-1"}
    base.update(kwargs)
    return mq.ObservedMetric(**base)


def _baseline(**kwargs) -> mq.BaselineReference:
    base = {
        "baseline_id": "baseline_1",
        "metric_name": "roc_auc",
        "value": 0.80,
        "context": _contexto(),
        "source": "modelo anterior",
    }
    base.update(kwargs)
    return mq.BaselineReference(**base)


def _status_por_codigo(resultados: list, code: str) -> list:
    return [r.status for r in resultados if r.code == code]


def _tiene_codigo(resultados: list, code: str) -> bool:
    return any(r.code == code for r in resultados)


class TestCodigos(unittest.TestCase):
    def test_codes_completos(self):
        self.assertEqual(
            mqv.CODES,
            (
                "QUALITY-INPUT",
                "QUALITY-METRIC-MISSING",
                "QUALITY-CONTEXT-MISMATCH",
                "QUALITY-METRIC-AMBIGUOUS",
                "QUALITY-EVIDENCE-MISSING",
                "QUALITY-UNCERTAINTY-MISSING",
                "QUALITY-SAMPLE-SIZE",
                "QUALITY-THRESHOLD",
                "QUALITY-BASELINE-MISSING",
                "QUALITY-BASELINE",
                "QUALITY-RESULT",
            ),
        )


class TestInput(unittest.TestCase):
    def test_policy_none(self):
        resultados = mqv.evaluate_policy(None, [])
        self.assertEqual(len(resultados), 1)
        self.assertEqual(resultados[0].status, checks.STATUS_FAIL)
        self.assertEqual(resultados[0].code, "QUALITY-INPUT")
        self.assertEqual(resultados[0].kind, checks.KIND_TECHNICAL_ERROR)

    def test_observed_metrics_no_es_lista(self):
        resultados = mqv.evaluate_policy(_policy(), "no es lista")
        self.assertEqual(len(resultados), 1)
        self.assertEqual(resultados[0].code, "QUALITY-INPUT")

    def test_observed_metrics_con_elemento_de_tipo_incorrecto(self):
        resultados = mqv.evaluate_policy(_policy(), [object()])
        self.assertEqual(len(resultados), 1)
        self.assertEqual(resultados[0].code, "QUALITY-INPUT")

    def test_baselines_con_elemento_de_tipo_incorrecto(self):
        resultados = mqv.evaluate_policy(_policy(), [], baselines=[object()])
        self.assertEqual(len(resultados), 1)
        self.assertEqual(resultados[0].code, "QUALITY-INPUT")

    def test_evaluate_policy_nunca_lanza(self):
        try:
            mqv.evaluate_policy(None, None, None)
        except Exception as exc:  # noqa: BLE001
            self.fail(f"evaluate_policy lanzó una excepción: {exc!r}")


class TestSeleccionMetrica(unittest.TestCase):
    def test_metric_missing_corta(self):
        req = _requirement()
        resultados = mqv.evaluate_policy(_policy(req), [])
        self.assertEqual(_status_por_codigo(resultados, "QUALITY-METRIC-MISSING"), [checks.STATUS_FAIL])
        self.assertEqual(_status_por_codigo(resultados, "QUALITY-RESULT"), [checks.STATUS_FAIL])
        for codigo in ("QUALITY-EVIDENCE-MISSING", "QUALITY-THRESHOLD", "QUALITY-BASELINE", "QUALITY-BASELINE-MISSING"):
            self.assertFalse(_tiene_codigo(resultados, codigo))

    def test_context_mismatch_corta(self):
        req = _requirement()
        observado = _observado(context=_contexto(context_id="ctx_train", split="train"))
        resultados = mqv.evaluate_policy(_policy(req), [observado])
        self.assertEqual(_status_por_codigo(resultados, "QUALITY-CONTEXT-MISMATCH"), [checks.STATUS_FAIL])
        self.assertEqual(_status_por_codigo(resultados, "QUALITY-RESULT"), [checks.STATUS_FAIL])
        self.assertFalse(_tiene_codigo(resultados, "QUALITY-EVIDENCE-MISSING"))

    def test_metric_ambiguous_corta(self):
        req = _requirement()
        obs1 = _observado()
        obs2 = _observado(evidence_ref="run-2")
        resultados = mqv.evaluate_policy(_policy(req), [obs1, obs2])
        self.assertEqual(_status_por_codigo(resultados, "QUALITY-METRIC-AMBIGUOUS"), [checks.STATUS_WARN])
        self.assertEqual(_status_por_codigo(resultados, "QUALITY-RESULT"), [checks.STATUS_WARN])
        self.assertFalse(_tiene_codigo(resultados, "QUALITY-EVIDENCE-MISSING"))

    def test_population_opcional_no_se_compara_si_requerido_vacio(self):
        req = _requirement(required_context=_contexto(population=""))
        observado = _observado(context=_contexto(population="AMBA"))
        resultados = mqv.evaluate_policy(_policy(req), [observado])
        # Selección exitosa: no hay entrada de corte, sí hay QUALITY-THRESHOLD.
        self.assertTrue(_tiene_codigo(resultados, "QUALITY-THRESHOLD"))

    def test_context_id_nunca_se_compara(self):
        req = _requirement(required_context=_contexto(context_id="ctx_a"))
        observado = _observado(context=_contexto(context_id="ctx_b"))
        resultados = mqv.evaluate_policy(_policy(req), [observado])
        self.assertTrue(_tiene_codigo(resultados, "QUALITY-THRESHOLD"))


class TestEvidenciaYNuncaPassSinEvidencia(unittest.TestCase):
    def test_evidence_missing_warn_pese_a_threshold_pass(self):
        req = _requirement(threshold_value=0.75)
        observado = _observado(value=0.90, evidence_ref=None)
        resultados = mqv.evaluate_policy(_policy(req), [observado])
        self.assertEqual(_status_por_codigo(resultados, "QUALITY-EVIDENCE-MISSING"), [checks.STATUS_WARN])
        self.assertEqual(_status_por_codigo(resultados, "QUALITY-THRESHOLD"), [checks.STATUS_PASS])
        self.assertEqual(_status_por_codigo(resultados, "QUALITY-RESULT"), [checks.STATUS_WARN])

    def test_evidence_presente_y_threshold_fail(self):
        req = _requirement(threshold_value=0.75, direction="higher_is_better", baseline_required=False)
        observado = _observado(value=0.70, evidence_ref="run-1")
        resultados = mqv.evaluate_policy(_policy(req), [observado])
        self.assertEqual(_status_por_codigo(resultados, "QUALITY-EVIDENCE-MISSING"), [checks.STATUS_PASS])
        self.assertEqual(_status_por_codigo(resultados, "QUALITY-THRESHOLD"), [checks.STATUS_FAIL])
        self.assertFalse(_tiene_codigo(resultados, "QUALITY-BASELINE-MISSING"))
        self.assertFalse(_tiene_codigo(resultados, "QUALITY-BASELINE"))
        self.assertEqual(_status_por_codigo(resultados, "QUALITY-RESULT"), [checks.STATUS_FAIL])

    def test_uncertainty_required_true_y_ausente(self):
        req = _requirement(uncertainty_required=True)
        observado = _observado(uncertainty=None)
        resultados = mqv.evaluate_policy(_policy(req), [observado])
        self.assertEqual(_status_por_codigo(resultados, "QUALITY-UNCERTAINTY-MISSING"), [checks.STATUS_WARN])

    def test_uncertainty_required_false_no_emite_entrada(self):
        req = _requirement(uncertainty_required=False)
        observado = _observado(uncertainty=None)
        resultados = mqv.evaluate_policy(_policy(req), [observado])
        self.assertFalse(_tiene_codigo(resultados, "QUALITY-UNCERTAINTY-MISSING"))

    def test_sample_size_fail(self):
        req = _requirement(min_sample_size=100)
        observado = _observado(sample_size=50)
        resultados = mqv.evaluate_policy(_policy(req), [observado])
        self.assertEqual(_status_por_codigo(resultados, "QUALITY-SAMPLE-SIZE"), [checks.STATUS_FAIL])

    def test_sample_size_warn_si_ausente(self):
        req = _requirement(min_sample_size=100)
        observado = _observado(sample_size=None)
        resultados = mqv.evaluate_policy(_policy(req), [observado])
        self.assertEqual(_status_por_codigo(resultados, "QUALITY-SAMPLE-SIZE"), [checks.STATUS_WARN])

    def test_sample_size_no_declarado_no_emite_entrada(self):
        req = _requirement(min_sample_size=None)
        observado = _observado(sample_size=None)
        resultados = mqv.evaluate_policy(_policy(req), [observado])
        self.assertFalse(_tiene_codigo(resultados, "QUALITY-SAMPLE-SIZE"))


class TestThreshold(unittest.TestCase):
    def test_threshold_none_es_na(self):
        req = _requirement(threshold_value=None, baseline_required=True)
        observado = _observado()
        baseline = _baseline()
        resultados = mqv.evaluate_policy(_policy(req), [observado], baselines=[baseline])
        self.assertEqual(_status_por_codigo(resultados, "QUALITY-THRESHOLD"), [checks.STATUS_NA])


class TestBaseline(unittest.TestCase):
    def test_baseline_required_true_sin_baseline(self):
        req = _requirement(threshold_value=0.75, baseline_required=True, baseline_severity="FAIL")
        observado = _observado(value=0.90)
        resultados = mqv.evaluate_policy(_policy(req), [observado], baselines=[])
        self.assertEqual(_status_por_codigo(resultados, "QUALITY-BASELINE-MISSING"), [checks.STATUS_FAIL])
        self.assertFalse(_tiene_codigo(resultados, "QUALITY-BASELINE"))
        self.assertEqual(_status_por_codigo(resultados, "QUALITY-RESULT"), [checks.STATUS_FAIL])

    def test_baseline_required_false_no_emite_ninguna_entrada(self):
        req = _requirement(threshold_value=0.75, baseline_required=False)
        observado = _observado(value=0.90)
        resultados = mqv.evaluate_policy(_policy(req), [observado], baselines=[])
        self.assertFalse(_tiene_codigo(resultados, "QUALITY-BASELINE-MISSING"))
        self.assertFalse(_tiene_codigo(resultados, "QUALITY-BASELINE"))

    def test_threshold_pass_baseline_missing_resultado_es_baseline_missing(self):
        req = _requirement(threshold_value=0.75, baseline_required=True, baseline_severity="WARN")
        observado = _observado(value=0.90, evidence_ref="run-1")
        resultados = mqv.evaluate_policy(_policy(req), [observado], baselines=[])
        self.assertEqual(_status_por_codigo(resultados, "QUALITY-THRESHOLD"), [checks.STATUS_PASS])
        self.assertEqual(_status_por_codigo(resultados, "QUALITY-BASELINE-MISSING"), [checks.STATUS_WARN])
        self.assertEqual(_status_por_codigo(resultados, "QUALITY-RESULT"), [checks.STATUS_WARN])

    def test_comparison_absolute_pass_y_violacion(self):
        req = _requirement(
            threshold_value=None,
            baseline_required=True,
            comparison_mode="absolute",
            direction="higher_is_better",
            comparison_tolerance=0.01,
            baseline_severity="FAIL",
        )
        observado = _observado(value=0.80)
        baseline_ok = _baseline(value=0.805)
        resultados = mqv.evaluate_policy(_policy(req), [observado], baselines=[baseline_ok])
        self.assertEqual(_status_por_codigo(resultados, "QUALITY-BASELINE"), [checks.STATUS_PASS])

        baseline_mal = _baseline(value=0.82)
        resultados2 = mqv.evaluate_policy(_policy(req), [observado], baselines=[baseline_mal])
        self.assertEqual(_status_por_codigo(resultados2, "QUALITY-BASELINE"), [checks.STATUS_FAIL])

    def test_comparison_absolute_diff_from_baseline(self):
        req = _requirement(
            threshold_value=None,
            baseline_required=True,
            comparison_mode="absolute_diff_from_baseline",
            comparison_tolerance=0.02,
            baseline_severity="FAIL",
        )
        observado = _observado(value=0.81)
        baseline_ok = _baseline(value=0.80)
        resultados = mqv.evaluate_policy(_policy(req), [observado], baselines=[baseline_ok])
        self.assertEqual(_status_por_codigo(resultados, "QUALITY-BASELINE"), [checks.STATUS_PASS])

        baseline_mal = _baseline(value=0.75)
        resultados2 = mqv.evaluate_policy(_policy(req), [observado], baselines=[baseline_mal])
        self.assertEqual(_status_por_codigo(resultados2, "QUALITY-BASELINE"), [checks.STATUS_FAIL])

    def test_comparison_relative_to_baseline(self):
        req = _requirement(
            threshold_value=None,
            baseline_required=True,
            comparison_mode="relative_to_baseline",
            direction="lower_is_better",
            comparison_tolerance=0.05,
            baseline_severity="FAIL",
        )
        observado = _observado(value=10.0)
        baseline_ok = _baseline(value=10.4)
        resultados = mqv.evaluate_policy(_policy(req), [observado], baselines=[baseline_ok])
        self.assertEqual(_status_por_codigo(resultados, "QUALITY-BASELINE"), [checks.STATUS_PASS])

    def test_comparison_relative_to_baseline_cero_es_warn_nunca_excepcion(self):
        req = _requirement(
            threshold_value=None,
            baseline_required=True,
            comparison_mode="relative_to_baseline",
            direction="lower_is_better",
            comparison_tolerance=0.05,
            baseline_severity="FAIL",
        )
        observado = _observado(value=10.0)
        baseline_cero = _baseline(value=0.0)
        resultados = mqv.evaluate_policy(_policy(req), [observado], baselines=[baseline_cero])
        self.assertEqual(_status_por_codigo(resultados, "QUALITY-BASELINE"), [checks.STATUS_WARN])


class TestFoldMonotonico(unittest.TestCase):
    def test_fold_evidencia_warn_threshold_pass_baseline_fail(self):
        req = _requirement(
            threshold_value=0.75,
            direction="higher_is_better",
            baseline_required=True,
            baseline_severity="FAIL",
            comparison_mode="absolute",
            comparison_tolerance=0.0,
        )
        observado = _observado(value=0.90, evidence_ref=None)
        baseline_mal = _baseline(value=1.0)
        resultados = mqv.evaluate_policy(_policy(req), [observado], baselines=[baseline_mal])
        self.assertEqual(_status_por_codigo(resultados, "QUALITY-EVIDENCE-MISSING"), [checks.STATUS_WARN])
        self.assertEqual(_status_por_codigo(resultados, "QUALITY-THRESHOLD"), [checks.STATUS_PASS])
        self.assertEqual(_status_por_codigo(resultados, "QUALITY-BASELINE"), [checks.STATUS_FAIL])
        self.assertEqual(_status_por_codigo(resultados, "QUALITY-RESULT"), [checks.STATUS_FAIL])

    def test_peor_y_acumular_nunca_mejoran(self):
        self.assertEqual(mqv._peor(checks.STATUS_PASS, checks.STATUS_WARN), checks.STATUS_WARN)
        self.assertEqual(mqv._peor(checks.STATUS_FAIL, checks.STATUS_WARN), checks.STATUS_FAIL)
        self.assertEqual(
            mqv._acumular([checks.STATUS_PASS, checks.STATUS_NA, checks.STATUS_WARN]), checks.STATUS_WARN
        )
        self.assertEqual(mqv._acumular([checks.STATUS_NA, checks.STATUS_NA]), checks.STATUS_NA)


class TestExcepcionInesperada(unittest.TestCase):
    def test_excepcion_en_un_requirement_no_afecta_a_los_demas(self):
        req_malo = _requirement(requirement_id="req_malo")
        req_bueno = _requirement(requirement_id="req_bueno", metric_name="f1_score")
        observado_bueno = _observado(metric_name="f1_score", value=0.90)
        policy = _policy(req_malo, req_bueno)

        with mock.patch.object(mqv, "_seleccionar_candidato", side_effect=[RuntimeError("boom"), ("ok", observado_bueno)]):
            resultados = mqv.evaluate_policy(policy, [observado_bueno])

        codigos_malos = [r for r in resultados if r.code == "QUALITY-req_malo-EXCEPCION"]
        self.assertEqual(len(codigos_malos), 1)
        self.assertEqual(codigos_malos[0].status, checks.STATUS_FAIL)
        self.assertEqual(codigos_malos[0].kind, checks.KIND_TECHNICAL_ERROR)
        # El requirement bueno se evalúa igual, sin interrupción.
        self.assertTrue(any(r.code == "QUALITY-RESULT" and r.subject == "req_bueno" for r in resultados))


if __name__ == "__main__":
    unittest.main()

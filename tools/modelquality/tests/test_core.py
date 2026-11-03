"""Tests de `tools.modelquality.core` (v0.7 Change 2). Fixtures 100% sintéticas
(nunca un dataset ni modelo real). Cubre R2-R11 de `spec.md`."""
from __future__ import annotations

import unittest

from tools.modelquality import core as mq


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


def _policy(**kwargs) -> mq.ModelQualityPolicy:
    base = {
        "policy_id": "policy_demo",
        "model_task_role": "classification",
        "requirements": (_requirement(),),
    }
    base.update(kwargs)
    return mq.ModelQualityPolicy(**base)


class TestVocabularios(unittest.TestCase):
    def test_model_task_roles(self):
        self.assertEqual(
            mq.MODEL_TASK_ROLES,
            ("classification", "regression", "ranking", "clustering", "forecasting", "generic"),
        )

    def test_directions(self):
        self.assertEqual(mq.DIRECTIONS, ("higher_is_better", "lower_is_better"))

    def test_splits(self):
        self.assertEqual(
            mq.SPLITS,
            ("train", "validation", "test", "holdout", "out_of_time", "cross_validation", "custom"),
        )

    def test_comparison_modes(self):
        self.assertEqual(
            mq.COMPARISON_MODES, ("absolute", "relative_to_baseline", "absolute_diff_from_baseline")
        )

    def test_uncertainty_kinds(self):
        self.assertEqual(mq.UNCERTAINTY_KINDS, ("standard_error", "confidence_interval"))

    def test_severities(self):
        self.assertEqual(mq.SEVERITIES, ("FAIL", "WARN"))

    def test_extension_prefix_y_schema_version(self):
        self.assertEqual(mq.EXTENSION_PREFIX, "x_")
        self.assertEqual(mq.SCHEMA_VERSION, 1)


class TestIdsYMetricName(unittest.TestCase):
    def test_id_invalido_vacio(self):
        with self.assertRaises(mq.ModelQualityError):
            _contexto(context_id="")

    def test_id_invalido_mayuscula(self):
        with self.assertRaises(mq.ModelQualityError):
            _contexto(context_id="CTX")

    def test_id_invalido_punto(self):
        with self.assertRaises(mq.ModelQualityError):
            _contexto(context_id="ctx.1")

    def test_id_invalido_barra(self):
        with self.assertRaises(mq.ModelQualityError):
            _contexto(context_id="ctx/1")

    def test_id_invalido_65_caracteres(self):
        with self.assertRaises(mq.ModelQualityError):
            _contexto(context_id="a" * 65)

    def test_id_invalido_no_str(self):
        with self.assertRaises(mq.ModelQualityError):
            _contexto(context_id=123)

    def test_id_invalido_reservado_windows(self):
        with self.assertRaises(mq.ModelQualityError):
            _contexto(context_id="con")

    def test_metric_name_invalido_vacio(self):
        with self.assertRaises(mq.ModelQualityError):
            mq.ObservedMetric(metric_name="", value=0.5, context=_contexto())

    def test_metric_name_invalido_mayuscula(self):
        with self.assertRaises(mq.ModelQualityError):
            mq.ObservedMetric(metric_name="AUC", value=0.5, context=_contexto())

    def test_metric_name_invalido_empieza_numero(self):
        with self.assertRaises(mq.ModelQualityError):
            mq.ObservedMetric(metric_name="1_metric", value=0.5, context=_contexto())

    def test_metric_name_invalido_guion(self):
        with self.assertRaises(mq.ModelQualityError):
            mq.ObservedMetric(metric_name="metric-1", value=0.5, context=_contexto())

    def test_metric_name_validos(self):
        for nombre in ("roc_auc", "f1_score", "rmse"):
            om = mq.ObservedMetric(metric_name=nombre, value=0.5, context=_contexto())
            self.assertEqual(om.metric_name, nombre)


class TestModelQualityError(unittest.TestCase):
    def test_es_value_error(self):
        self.assertTrue(issubclass(mq.ModelQualityError, ValueError))


class TestEvaluationContext(unittest.TestCase):
    def test_split_invalido(self):
        with self.assertRaises(mq.ModelQualityError):
            _contexto(split="otro")

    def test_split_valido(self):
        ctx = _contexto(split="test", population="")
        self.assertEqual(ctx.split, "test")

    def test_extensions_sin_prefijo_falla(self):
        with self.assertRaises(mq.ModelQualityError):
            _contexto(extensions={"nota": "sin prefijo"})

    def test_extensions_con_prefijo_ok(self):
        ctx = _contexto(extensions={"x_nota": "ok"})
        self.assertEqual(ctx.extensions, {"x_nota": "ok"})

    def test_extensions_se_copian_en_profundidad(self):
        original = {"x_lista": [1, 2, 3]}
        ctx = _contexto(extensions=original)
        original["x_lista"].append(4)
        self.assertEqual(ctx.extensions["x_lista"], [1, 2, 3])


class TestMetricRequirement(unittest.TestCase):
    def test_direction_invalida(self):
        with self.assertRaises(mq.ModelQualityError):
            _requirement(direction="mejor")

    def test_coherencia_minima_sin_threshold_ni_baseline(self):
        with self.assertRaises(mq.ModelQualityError):
            _requirement(threshold_value=None, baseline_required=False)

    def test_solo_threshold_valido(self):
        req = _requirement(threshold_value=0.75, baseline_required=False)
        self.assertEqual(req.threshold_value, 0.75)

    def test_solo_baseline_valido(self):
        req = _requirement(threshold_value=None, baseline_required=True)
        self.assertIsNone(req.threshold_value)
        self.assertTrue(req.baseline_required)

    def test_comparison_tolerance_negativa_falla(self):
        with self.assertRaises(mq.ModelQualityError):
            _requirement(comparison_tolerance=-0.1)

    def test_comparison_tolerance_bool_falla(self):
        with self.assertRaises(mq.ModelQualityError):
            _requirement(comparison_tolerance=True)

    def test_comparison_tolerance_valida(self):
        req = _requirement(comparison_tolerance=0.02)
        self.assertEqual(req.comparison_tolerance, 0.02)

    def test_min_sample_size_cero_falla(self):
        with self.assertRaises(mq.ModelQualityError):
            _requirement(min_sample_size=0)

    def test_min_sample_size_float_falla(self):
        with self.assertRaises(mq.ModelQualityError):
            _requirement(min_sample_size=1.5)

    def test_min_sample_size_valido(self):
        req = _requirement(min_sample_size=30)
        self.assertEqual(req.min_sample_size, 30)

    def test_required_context_dict_falla(self):
        with self.assertRaises(mq.ModelQualityError):
            _requirement(required_context={"split": "test"})

    def test_comparison_mode_invalido(self):
        with self.assertRaises(mq.ModelQualityError):
            _requirement(comparison_mode="otro")

    def test_threshold_severity_invalida(self):
        with self.assertRaises(mq.ModelQualityError):
            _requirement(threshold_severity="OTRO")

    def test_threshold_value_no_finito(self):
        with self.assertRaises(mq.ModelQualityError):
            _requirement(threshold_value=float("nan"))

    def test_threshold_value_bool_falla(self):
        with self.assertRaises(mq.ModelQualityError):
            _requirement(threshold_value=True)


class TestObservedMetric(unittest.TestCase):
    def test_value_nan_falla(self):
        with self.assertRaises(mq.ModelQualityError):
            mq.ObservedMetric(metric_name="roc_auc", value=float("nan"), context=_contexto())

    def test_value_bool_falla(self):
        with self.assertRaises(mq.ModelQualityError):
            mq.ObservedMetric(metric_name="roc_auc", value=True, context=_contexto())

    def test_value_valido(self):
        om = mq.ObservedMetric(metric_name="roc_auc", value=0.83, context=_contexto())
        self.assertEqual(om.value, 0.83)

    def test_evidence_ref_vacio_falla(self):
        with self.assertRaises(mq.ModelQualityError):
            mq.ObservedMetric(metric_name="roc_auc", value=0.8, context=_contexto(), evidence_ref="")

    def test_evidence_ref_none_ok(self):
        om = mq.ObservedMetric(metric_name="roc_auc", value=0.8, context=_contexto(), evidence_ref=None)
        self.assertIsNone(om.evidence_ref)

    def test_evidence_ref_str_ok(self):
        om = mq.ObservedMetric(
            metric_name="roc_auc", value=0.8, context=_contexto(), evidence_ref="run-123"
        )
        self.assertEqual(om.evidence_ref, "run-123")

    def test_context_no_evaluationcontext_falla(self):
        with self.assertRaises(mq.ModelQualityError):
            mq.ObservedMetric(metric_name="roc_auc", value=0.8, context={"split": "test"})

    def test_sample_size_invalido(self):
        with self.assertRaises(mq.ModelQualityError):
            mq.ObservedMetric(metric_name="roc_auc", value=0.8, context=_contexto(), sample_size=0)

    def test_sample_size_bool_falla(self):
        with self.assertRaises(mq.ModelQualityError):
            mq.ObservedMetric(metric_name="roc_auc", value=0.8, context=_contexto(), sample_size=True)

    def test_uncertainty_standard_error_negativo_falla(self):
        with self.assertRaises(mq.ModelQualityError):
            mq.ObservedMetric(
                metric_name="roc_auc",
                value=0.8,
                context=_contexto(),
                uncertainty={"kind": "standard_error", "value": -0.1},
            )

    def test_uncertainty_standard_error_valido(self):
        om = mq.ObservedMetric(
            metric_name="roc_auc",
            value=0.8,
            context=_contexto(),
            uncertainty={"kind": "standard_error", "value": 0.02},
        )
        self.assertEqual(om.uncertainty, {"kind": "standard_error", "value": 0.02})

    def test_uncertainty_confidence_interval_lower_mayor_upper_falla(self):
        with self.assertRaises(mq.ModelQualityError):
            mq.ObservedMetric(
                metric_name="roc_auc",
                value=0.8,
                context=_contexto(),
                uncertainty={
                    "kind": "confidence_interval",
                    "lower": 0.9,
                    "upper": 0.8,
                    "confidence_level": 0.95,
                },
            )

    def test_uncertainty_confidence_interval_valido(self):
        om = mq.ObservedMetric(
            metric_name="roc_auc",
            value=0.85,
            context=_contexto(),
            uncertainty={
                "kind": "confidence_interval",
                "lower": 0.80,
                "upper": 0.90,
                "confidence_level": 0.95,
            },
        )
        self.assertEqual(om.uncertainty["lower"], 0.80)

    def test_uncertainty_kind_desconocido_falla(self):
        with self.assertRaises(mq.ModelQualityError):
            mq.ObservedMetric(
                metric_name="roc_auc", value=0.8, context=_contexto(), uncertainty={"kind": "otro"}
            )

    def test_uncertainty_sin_kind_falla(self):
        with self.assertRaises(mq.ModelQualityError):
            mq.ObservedMetric(
                metric_name="roc_auc", value=0.8, context=_contexto(), uncertainty={"value": 0.02}
            )

    def test_ningun_constructor_acepta_parametro_de_datos_crudos(self):
        prohibidos = {"data", "frame", "dataframe", "predictions", "rows", "path", "ruta"}
        for cls in (mq.EvaluationContext, mq.MetricRequirement, mq.ObservedMetric, mq.BaselineReference, mq.ModelQualityPolicy):
            campos = set(cls.__dataclass_fields__.keys())
            self.assertEqual(campos & prohibidos, set())


class TestBaselineReference(unittest.TestCase):
    def test_source_vacio_falla(self):
        with self.assertRaises(mq.ModelQualityError):
            mq.BaselineReference(
                baseline_id="baseline_1",
                metric_name="roc_auc",
                value=0.80,
                context=_contexto(),
                source="",
            )

    def test_source_valido(self):
        baseline = mq.BaselineReference(
            baseline_id="baseline_1",
            metric_name="roc_auc",
            value=0.80,
            context=_contexto(),
            source="modelo anterior v1.2",
        )
        self.assertEqual(baseline.source, "modelo anterior v1.2")


class TestModelQualityPolicy(unittest.TestCase):
    def test_requirements_vacia_falla(self):
        with self.assertRaises(mq.ModelQualityError):
            _policy(requirements=())

    def test_requirement_id_duplicado_falla(self):
        req1 = _requirement(requirement_id="req_x")
        req2 = _requirement(requirement_id="req_x", metric_name="f1_score")
        with self.assertRaises(mq.ModelQualityError):
            _policy(requirements=(req1, req2))

    def test_mismo_metric_name_distinto_contexto_es_valido(self):
        req1 = _requirement(requirement_id="req_train", required_context=_contexto(context_id="ctx_train", split="train"))
        req2 = _requirement(requirement_id="req_test", required_context=_contexto(context_id="ctx_test2", split="test"))
        policy = _policy(requirements=(req1, req2))
        self.assertEqual(len(policy.requirements), 2)

    def test_schema_version_invalido_constructor(self):
        with self.assertRaises(mq.ModelQualityError):
            _policy(schema_version=2)

    def test_schema_version_invalido_from_dict(self):
        policy = _policy()
        datos = policy.to_dict()
        datos["schema_version"] = 2
        with self.assertRaises(mq.ModelQualityError):
            mq.ModelQualityPolicy.from_dict(datos)

    def test_model_task_role_invalido(self):
        with self.assertRaises(mq.ModelQualityError):
            _policy(model_task_role="otro")

    def test_get_requirement_nunca_lanza(self):
        policy = _policy()
        self.assertIsNone(policy.get_requirement("no-existe"))
        self.assertIsNotNone(policy.get_requirement("req_auc"))

    def test_requirements_for_nunca_lanza(self):
        policy = _policy()
        self.assertEqual(policy.requirements_for("no_existe"), ())
        self.assertEqual(len(policy.requirements_for("roc_auc")), 1)


class TestSerializacion(unittest.TestCase):
    def test_roundtrip_policy(self):
        policy = _policy()
        clon = mq.ModelQualityPolicy.from_dict(policy.to_dict())
        self.assertEqual(clon.to_dict(), policy.to_dict())

    def test_content_sha256_determinista(self):
        policy = _policy()
        self.assertEqual(policy.content_sha256(), policy.content_sha256())

    def test_content_sha256_estable_tras_roundtrip(self):
        policy = _policy()
        clon = mq.ModelQualityPolicy.from_dict(policy.to_dict())
        self.assertEqual(policy.content_sha256(), clon.content_sha256())

    def test_content_sha256_cambia_con_tolerance(self):
        req_a = _requirement(comparison_tolerance=0.01, baseline_required=True)
        req_b = _requirement(comparison_tolerance=0.05, baseline_required=True)
        policy_a = _policy(requirements=(req_a,))
        policy_b = _policy(requirements=(req_b,))
        self.assertNotEqual(policy_a.content_sha256(), policy_b.content_sha256())

    def test_roundtrip_evaluation_context(self):
        ctx = _contexto(population="AMBA")
        clon = mq.EvaluationContext.from_dict(ctx.to_dict())
        self.assertEqual(clon.to_dict(), ctx.to_dict())
        self.assertFalse(hasattr(clon, "content_sha256"))

    def test_roundtrip_observed_metric(self):
        om = mq.ObservedMetric(metric_name="roc_auc", value=0.8, context=_contexto(), evidence_ref="run-1")
        clon = mq.ObservedMetric.from_dict(om.to_dict())
        self.assertEqual(clon.to_dict(), om.to_dict())
        self.assertFalse(hasattr(clon, "content_sha256"))

    def test_roundtrip_baseline_reference(self):
        baseline = mq.BaselineReference(
            baseline_id="baseline_1", metric_name="roc_auc", value=0.8, context=_contexto(), source="dummy"
        )
        clon = mq.BaselineReference.from_dict(baseline.to_dict())
        self.assertEqual(clon.to_dict(), baseline.to_dict())
        self.assertFalse(hasattr(clon, "content_sha256"))

    def test_canonical_json_orden_de_claves(self):
        self.assertEqual(mq.canonical_json({"b": 1, "a": 2}), '{"a":2,"b":1}')

    def test_canonical_json_nan_falla(self):
        with self.assertRaises(mq.ModelQualityError):
            mq.canonical_json({"x": float("nan")})


if __name__ == "__main__":
    unittest.main()

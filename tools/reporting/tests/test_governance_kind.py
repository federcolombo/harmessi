"""Tests del valor aditivo `report_kind="governance"` (Change
`20261005-cards-governance-integration`, R64a/R64b): vocabulario y aislamiento de holdout."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.reporting import core, evidence, governance
from tools.reporting.publish import publish

PREVIOS = ("eda", "model", "evaluation", "production")
POLICY_SIN_HOLDOUT = {"schema_version": 1}
POLICY_HOLDOUT_AUTORIZADO = {
    "schema_version": 1,
    "holdout": {"declared": True, "final_evaluation": {"authorized": True, "reason": "evaluación final de prueba"}},
}


class TestVocabulario(unittest.TestCase):
    def test_governance_aceptado_y_previos_intactos_en_orden(self):
        self.assertEqual(core.REPORT_KINDS, PREVIOS + ("governance",))
        self.assertEqual(core.REPORT_KINDS[:4], PREVIOS)

    def test_report_acepta_governance_en_las_3_scopes(self):
        for scope in core.DECISION_SCOPES:
            with self.subTest(scope=scope):
                r = core.Report(report_id="r1", title="t", report_kind="governance", decision_scope=scope)
                self.assertEqual(r.report_kind, "governance")

    def test_kind_desconocido_sigue_rechazado(self):
        with self.assertRaises(core.ReportingContractError):
            core.Report(report_id="r1", title="t", report_kind="gobernanza", decision_scope="exploratory")


class BaseRepo(unittest.TestCase):
    policy = POLICY_SIN_HOLDOUT

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo = Path(self._tmp.name).resolve()
        ruta = self.repo / ".harmessi" / "scientific-policy.json"
        ruta.parent.mkdir(parents=True)
        ruta.write_text(json.dumps(self.policy), encoding="utf-8")

    def _auth(self, kind, scope):
        return governance._autorizacion_read(self.repo, kind, scope)


class TestAislamientoSinHoldout(BaseRepo):
    def test_governance_nunca_autoriza_lectura_en_las_3_scopes(self):
        for scope in core.DECISION_SCOPES:
            with self.subTest(scope=scope):
                autorizado, detalle, tecnico = self._auth("governance", scope)
                self.assertIsNone(tecnico)
                self.assertFalse(autorizado)
                self.assertIn("report_kind='governance'", detalle)

    def test_governance_no_equivale_a_evaluation(self):
        for scope in ("model_valid", "operational"):
            with self.subTest(scope=scope):
                _a, det_eval, tec_eval = self._auth("evaluation", scope)
                _b, det_gov, tec_gov = self._auth("governance", scope)
                self.assertIsNone(tec_eval)
                self.assertIsNone(tec_gov)
                self.assertNotIn("report_kind", det_eval)
                self.assertIn("report_kind", det_gov)

    def test_governance_se_trata_como_model_production_eda(self):
        for scope in core.DECISION_SCOPES:
            with self.subTest(scope=scope):
                gov = self._auth("governance", scope)
                for otro in ("model", "production", "eda"):
                    ref = self._auth(otro, scope)
                    self.assertEqual(gov[0], ref[0])
                    self.assertEqual(gov[1].replace("'governance'", f"'{otro}'"), ref[1])
                    self.assertEqual(gov[2], ref[2])

    def test_previos_conservan_resultado(self):
        for kind in PREVIOS:
            for scope in core.DECISION_SCOPES:
                with self.subTest(kind=kind, scope=scope):
                    autorizado, detalle, tecnico = self._auth(kind, scope)
                    self.assertIsNone(tecnico)
                    self.assertFalse(autorizado)
                    if kind != "evaluation":
                        self.assertIn(f"report_kind='{kind}'", detalle)
                    if scope == "exploratory":
                        self.assertIn("decision_scope='exploratory'", detalle)


class TestAislamientoConHoldoutAutorizado(BaseRepo):
    """La policy autoriza la evaluación final: solo `evaluation` + scope de decisión la usa."""

    policy = POLICY_HOLDOUT_AUTORIZADO

    def test_evaluation_model_valid_si_autoriza_control_positivo(self):
        for scope in ("model_valid", "operational"):
            with self.subTest(scope=scope):
                autorizado, _d, tecnico = self._auth("evaluation", scope)
                self.assertIsNone(tecnico)
                self.assertTrue(autorizado)

    def test_governance_no_autoriza_ni_con_policy_que_autoriza(self):
        for scope in core.DECISION_SCOPES:
            with self.subTest(scope=scope):
                autorizado, detalle, tecnico = self._auth("governance", scope)
                self.assertIsNone(tecnico)
                self.assertFalse(autorizado)
                self.assertIn("report_kind='governance'", detalle)

    def test_otros_previos_siguen_denegados(self):
        for kind in ("eda", "model", "production"):
            for scope in core.DECISION_SCOPES:
                with self.subTest(kind=kind, scope=scope):
                    self.assertFalse(self._auth(kind, scope)[0])

    def test_publish_governance_no_concede_lectura_de_holdout(self):
        (self.repo / "datos.txt").write_text("x\n", encoding="utf-8")
        fuente = evidence.describe_source(self.repo, "datos.txt", role="input")
        reporte = core.Report(
            report_id="gov-holdout", title="t", report_kind="governance", decision_scope="exploratory",
            summary="s", conclusion="c",
        )
        resultado = publish(
            reporte, self.repo, run_id=evidence.new_run_id(), sources=[fuente],
            holdout_access="read", out_dir="reports/exploratory/gov-holdout",
        )
        fallos = [r for r in resultado.results if r.status == "FAIL"]
        self.assertTrue(fallos, "publish de un reporte governance no debe conceder lectura de holdout")
        self.assertFalse(resultado.html_written)
        # El FAIL debe ser el del check de holdout (no una falla incidental de otro origen).
        self.assertTrue(
            any("HOLDOUT" in str(r.code).upper() for r in fallos),
            f"se esperaba un FAIL de holdout; hubo: {[r.code for r in fallos]}",
        )


if __name__ == "__main__":
    unittest.main()

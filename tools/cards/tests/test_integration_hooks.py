"""Tests del hook `anchor_verifier` (Change 4, R34, R37, R38) y de la dirección de imports."""
from __future__ import annotations

import inspect
import unittest
from pathlib import Path

from tools.cards import approvals, assess, core, datacard, modelcard, modelgov
from tools.cards.tests import test_assess as ta
from tools.cards.tests import test_modelgov as tm

CARDS_DIR = Path(__file__).resolve().parents[1]
APPROVAL = {"change_id": "20261005-demo", "artefacto": "spec.md", "hash": "b" * 64}
RELOJ = lambda: "2030-01-01T00:00:00Z"  # noqa: E731


def verificador(estado, llamadas=None):
    def _v(att):
        if llamadas is not None:
            llamadas.append(att.attestation_id)
        return approvals.AnchorResolution(estado, f"detalle {estado}", "20261005-demo", "spec.md", "Ana", "2026-10-06")

    return _v


def card_con(kind):
    extra = {"approval_ref": dict(APPROVAL)} if kind == "anchored" else {}
    att = ta.hacer_att(attestation_kind=kind, **extra)
    return ta.hacer_card(attestations=(att,), claims=(ta.claim(supports=("at1",)),))


REQ_DECLARED = [ta.req("r1", "required", ("attestation",), min_attestation_kind="declared")]
REQ_ANCHORED = [ta.req("r1", "required", ("attestation",), min_attestation_kind="anchored")]


class TestAssessHook(unittest.TestCase):
    def evaluar(self, card, reqs, v):
        return assess.evaluate(card, reqs, {}, RELOJ, anchor_verifier=v)

    def test_default_none_estructural(self):
        a = assess.evaluate(card_con("anchored"), REQ_ANCHORED, {}, RELOJ)
        self.assertEqual(a.card_status, "complete")
        self.assertEqual(a.anchors, ())

    def test_verified_cuenta_como_anchored(self):
        a = self.evaluar(card_con("anchored"), REQ_ANCHORED, verificador("verified"))
        self.assertEqual(a.card_status, "complete")
        self.assertEqual(a.anchors[0][:2], ("at1", "verified"))
        self.assertEqual(a.hallazgos, ())

    def test_stale_card_stale(self):
        a = self.evaluar(card_con("anchored"), REQ_ANCHORED, verificador("stale"))
        self.assertEqual(a.card_status, "stale")
        self.assertEqual(a.requisitos[0][2], assess.REQ_STALE)
        self.assertEqual({h.code for h in a.hallazgos}, {"ANCHOR-STALE"})

    def test_missing_y_unresolvable_incomplete(self):
        for estado, codigo in (("missing", "ANCHOR-MISSING"), ("unresolvable", "ANCHOR-UNRESOLVABLE")):
            with self.subTest(estado=estado):
                a = self.evaluar(card_con("anchored"), REQ_ANCHORED, verificador(estado))
                self.assertEqual(a.card_status, "incomplete")
                self.assertEqual(a.requisitos[0][2], assess.REQ_UNVERIFIABLE)
                self.assertEqual({h.code for h in a.hallazgos}, {codigo})

    def test_anchored_no_verificada_no_satisface_declared(self):
        for estado in ("stale", "missing", "unresolvable"):
            with self.subTest(estado=estado):
                a = self.evaluar(card_con("anchored"), REQ_DECLARED, verificador(estado))
                self.assertNotEqual(a.requisitos[0][2], assess.REQ_SATISFIED)
                self.assertNotEqual(a.card_status, "complete")

    def test_declared_no_consulta_verificador(self):
        llamadas: list = []
        a = self.evaluar(card_con("declared"), REQ_DECLARED, verificador("missing", llamadas))
        self.assertEqual(llamadas, [])
        self.assertEqual(a.card_status, "complete")
        self.assertEqual(a.anchors, ())

    def test_verificador_que_falla_es_unresolvable(self):
        def malo(att):
            raise RuntimeError("x")

        a = self.evaluar(card_con("anchored"), REQ_ANCHORED, malo)
        self.assertEqual(a.card_status, "incomplete")
        self.assertEqual(a.anchors[0][1], "unresolvable")
        a = self.evaluar(card_con("anchored"), REQ_ANCHORED, lambda att: None)
        self.assertEqual(a.anchors[0][1], "unresolvable")

    def test_verificador_no_callable(self):
        with self.assertRaises(core.CardError):
            self.evaluar(card_con("anchored"), REQ_ANCHORED, "no-callable")

    def test_check_results_warn_por_ancla(self):
        a = self.evaluar(card_con("anchored"), REQ_ANCHORED, verificador("missing"))
        self.assertIn("ANCHOR-MISSING", {r.code for r in assess.a_check_results(a)})

    def test_a_dict_incluye_anchors_solo_con_verificador(self):
        self.assertNotIn("anchors", assess.evaluate(card_con("anchored"), REQ_ANCHORED, {}, RELOJ).a_dict())
        self.assertIn("anchors", self.evaluar(card_con("anchored"), REQ_ANCHORED, verificador("verified")).a_dict())

    def test_firmas_aceptan_hook(self):
        for fn in (assess.evaluate, assess.evaluate_file, datacard.evaluate_data_card,
                   modelcard.evaluate_model_card, modelgov.evaluate_governance_assessment):
            with self.subTest(fn=fn.__name__):
                self.assertIsNone(inspect.signature(fn).parameters["anchor_verifier"].default)
        self.assertIsNone(inspect.signature(modelgov.evaluate_governance_assessment).parameters["governance"].default)


class TestModelgovHook(tm.BaseGov):
    def test_high_verified_complete_y_default_igual(self):
        card = self.armar("high")
        self.assertEqual(self.evaluar(card).governance_completeness, "complete")
        a = self.evaluar(card, anchor_verifier=verificador("verified"))
        self.assertEqual(a.governance_completeness, "complete")
        self.assertTrue(a.anchors)
        self.assertIn("anchors", a.a_dict())

    def test_high_stale_stale(self):
        a = self.evaluar(self.armar("high"), anchor_verifier=verificador("stale"))
        self.assertEqual(a.governance_completeness, "stale")
        self.assertIn("ANCHOR-STALE", {h.code for h in a.hallazgos})

    def test_high_missing_incomplete(self):
        a = self.evaluar(self.armar("high"), anchor_verifier=verificador("missing"))
        self.assertEqual(a.governance_completeness, "incomplete")
        self.assertIn("ANCHOR-MISSING", {h.code for h in a.hallazgos})

    def test_anchored_no_verificada_no_degrada_a_declared(self):
        cfg = self.config("medium")
        cfg["attestations"] = [tm.hacer_att("at-risk", "risk_level=medium", "anchored")] + [
            x for x in cfg["attestations"] if x.attestation_id != "at-risk"
        ]
        a = self.evaluar(self.ensamblar(**cfg), anchor_verifier=verificador("missing"))
        self.assertNotEqual(a.governance_completeness, "complete")
        self.assertEqual(tm.estado_req(a, "accountability_risk_declaration"), assess.REQ_UNVERIFIABLE)

    def _con_na(self, kind_att):
        """medium: privacy_evidence es required; explainability_evidence es recommended en medium."""
        cfg = self.config("medium")
        cfg["attestations"] = list(cfg["attestations"]) + [tm.hacer_att("at-na", "No aplica por el tipo de modelo", kind_att)]
        cfg["dimensions"] = tm.dim_na("explainability", "explainability_evidence")
        return self.ensamblar(**cfg)

    def test_na_con_declared_vale(self):
        a = self.evaluar(self._con_na("declared"), anchor_verifier=verificador("missing"))
        self.assertEqual(tm.estado_req(a, "explainability_evidence"), modelgov.REQ_NOT_APPLICABLE)
        self.assertEqual(a.governance_completeness, "complete")

    def test_na_con_anchored_verified_vale(self):
        a = self.evaluar(self._con_na("anchored"), anchor_verifier=verificador("verified"))
        self.assertEqual(tm.estado_req(a, "explainability_evidence"), modelgov.REQ_NOT_APPLICABLE)

    def test_na_con_anchored_stale_o_missing_no_vale(self):
        a = self.evaluar(self._con_na("anchored"), anchor_verifier=verificador("stale"))
        self.assertNotEqual(tm.estado_req(a, "explainability_evidence"), modelgov.REQ_NOT_APPLICABLE)
        self.assertEqual(a.governance_completeness, "stale")
        for estado in ("missing", "unresolvable"):
            with self.subTest(estado=estado):
                a = self.evaluar(self._con_na("anchored"), anchor_verifier=verificador(estado))
                self.assertNotEqual(tm.estado_req(a, "explainability_evidence"), modelgov.REQ_NOT_APPLICABLE)
                self.assertEqual(a.governance_completeness, "incomplete")

    def test_declared_no_consulta(self):
        llamadas: list = []
        a = self.evaluar(self.armar("low"), anchor_verifier=verificador("missing", llamadas))
        self.assertEqual(llamadas, [])
        self.assertEqual(a.governance_completeness, "complete")


class TestDireccionDeImports(unittest.TestCase):
    def test_foundation_no_importa_adaptadores(self):
        for modulo in ("core", "assess", "resolvers", "datacard", "modelcard", "govpolicy", "modelgov"):
            fuente = (CARDS_DIR / f"{modulo}.py").read_text(encoding="utf-8")
            # Excepción preexistente y documentada (Change 3 R1): `assess` importa
            # perezosamente `dsguard.checks` solo para `CheckResult`.
            fuente = fuente.replace("from dsguard import checks", "")
            for prohibido in ("import govconfig", "import approvals", "from . import govconfig",
                              "from . import approvals", "import dsguard", "from dsguard"):
                with self.subTest(modulo=modulo, prohibido=prohibido):
                    self.assertNotIn(prohibido, fuente)


if __name__ == "__main__":
    unittest.main()

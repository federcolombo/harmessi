"""Tests de `govconfig` y de la tabla R29 en `modelgov` (Change 4, R24-R33)."""
from __future__ import annotations

import importlib
import json
import tempfile
import unittest
from pathlib import Path

from tools.cards import core, govconfig, govpolicy, modelgov, resolvers
from tools.cards.tests import test_modelgov as tm

RUTA = govconfig.RUTA_HARDENING_PROYECTO
RUTA_LOCAL = govconfig.RUTA_CAPA_LOCAL


def relajante():
    """Hardening que relaja la base (privacy_evidence high pasa a recommended)."""
    return tm.hardening(overrides=[tm.override("privacy_evidence", high=tm.L("recommended", ("attestation",)))])


class Mundo(tm.BaseGov):
    def pin_hardening(self, doc_o_dict, eid="ev-hard"):
        """Los pins de hardening viven en el documento de proyecto (R22)."""
        datos = doc_o_dict.to_dict() if hasattr(doc_o_dict, "to_dict") else doc_o_dict
        self.escribir_json(RUTA, datos)
        return core.EvidenceRef(
            eid, "governance_policy", tm.POLICY_ID, resolvers.hash_document(datos), tm.T0, locator=RUTA
        )

    def gov_ctx(self):
        return govconfig.resolve_project_governance(self.raiz)

    def eval_ctx(self, card, **kw):
        return self.evaluar(card, governance=self.gov_ctx(), **kw)

    def escribir_local(self, obj):
        return self.escribir_json(RUTA_LOCAL, obj)


class TestResolucion(Mundo):
    def test_none_sin_capas(self):
        g = self.gov_ctx()
        self.assertEqual(g.state, "none")
        self.assertIsNone(g.project_hardening_path)
        self.assertFalse(g.local_hardening_present)
        self.assertEqual(g.effective_sha256, govpolicy.merge(govpolicy.BASE_POLICY).effective_sha256())

    def test_resolved_proyecto(self):
        h = tm.hardening(floor="medium")
        self.escribir_json(RUTA, h.to_dict())
        g = self.gov_ctx()
        self.assertEqual(g.state, "resolved")
        self.assertEqual(g.project_hardening_path, RUTA)
        self.assertEqual(g.effective_sha256, govpolicy.merge(govpolicy.BASE_POLICY, h).effective_sha256())

    def test_apilado_proyecto_y_local(self):
        hp, hl = tm.hardening(floor="low"), tm.hardening(floor="high")
        self.escribir_json(RUTA, hp.to_dict())
        self.escribir_local({govconfig.CLAVE_LOCAL: hl.to_dict()})
        g = self.gov_ctx()
        esperado = govpolicy.merge(govpolicy.merge(govpolicy.BASE_POLICY, hp), hl)
        self.assertEqual(g.state, "resolved")
        self.assertTrue(g.local_hardening_present)
        self.assertEqual(g.effective_sha256, esperado.effective_sha256())
        self.assertEqual(g.effective.risk_floor, "high")

    def test_relajacion_proyecto_invalid(self):
        self.escribir_json(RUTA, relajante().to_dict())
        g = self.gov_ctx()
        self.assertEqual(g.state, "invalid")
        self.assertIsNone(g.effective)
        codes = {h.code for h in g.findings}
        self.assertIn("GOVCFG-INVALID", codes)
        self.assertIn("GOVCFG-RELAXATION", codes)

    def test_relajacion_local_invalid(self):
        self.escribir_local({govconfig.CLAVE_LOCAL: relajante().to_dict()})
        self.assertEqual(self.gov_ctx().state, "invalid")

    def test_clave_desconocida_invalid(self):
        self.escribir_json(RUTA, {"policy_id": tm.POLICY_ID, "base_version": 1, "zzz": 1})
        self.assertEqual(self.gov_ctx().state, "invalid")

    def test_json_roto_o_no_objeto_invalid(self):
        for contenido in (b"{{{", b"[1, 2]"):
            with self.subTest(contenido=contenido):
                self.escribir_bytes(RUTA, contenido)
                self.assertEqual(self.gov_ctx().state, "invalid")
        self.escribir_bytes(RUTA, b"{}")  # objeto sin claves obligatorias
        self.assertEqual(self.gov_ctx().state, "invalid")

    def test_capa_local_ilegible_invalid_no_vacia(self):
        for contenido in (b"{{{", b'"texto"'):
            with self.subTest(contenido=contenido):
                self.escribir_bytes(RUTA_LOCAL, contenido)
                self.assertEqual(self.gov_ctx().state, "invalid")

    def test_archivo_no_legible_unresolvable(self):
        (self.raiz / RUTA).mkdir(parents=True)  # directorio donde debería haber un archivo
        g = self.gov_ctx()
        self.assertEqual(g.state, "unresolvable")
        self.assertIn("GOVCFG-UNRESOLVABLE", {h.code for h in g.findings})

    def test_local_no_habilita_capabilities(self):
        self.escribir_local({"capabilities_habilitadas": ["data_cards", "model_governance"], "otra": 1})
        g = self.gov_ctx()
        self.assertEqual(g.state, "none")
        self.assertFalse(g.local_hardening_present)
        self.escribir_local({"capabilities_habilitadas": ["x"], govconfig.CLAVE_LOCAL: tm.hardening(floor="low").to_dict()})
        g = self.gov_ctx()
        self.assertEqual(g.state, "resolved")
        self.assertTrue(g.local_hardening_present)

    def test_local_null_invalid(self):
        self.escribir_local({govconfig.CLAVE_LOCAL: None})
        self.assertEqual(self.gov_ctx().state, "invalid")

    def test_invalid_y_unresolvable_simultaneos_invalid(self):
        (self.raiz / RUTA).mkdir(parents=True)  # unresolvable
        self.escribir_bytes(RUTA_LOCAL, b"{{{")  # invalid
        g = self.gov_ctx()
        self.assertEqual(g.state, "invalid")
        codes = {h.code for h in g.findings}
        self.assertIn("GOVCFG-INVALID", codes)
        self.assertIn("GOVCFG-UNRESOLVABLE", codes)

    def test_symlink_unresolvable(self):
        destino = self.escribir_bytes("real.json", b"{}")
        enlace = self.raiz / RUTA_LOCAL
        enlace.parent.mkdir(parents=True, exist_ok=True)
        try:
            enlace.symlink_to(destino)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks no disponibles")
        self.assertEqual(self.gov_ctx().state, "unresolvable")

    def test_nunca_lanza(self):
        g = govconfig.resolve_project_governance(object())
        self.assertIn(g.state, govconfig.ESTADOS)
        self.assertEqual(govconfig.resolve_project_governance(self.raiz, base="x").state, "invalid")

    def test_paridad_lector_con_ds_guard(self):
        try:
            ds_guard = importlib.import_module("tools.ds_guard")
        except Exception:  # pragma: no cover
            self.skipTest("ds_guard no importable")
        ruta = self.raiz / "capa.json"
        self.assertEqual(ds_guard._leer_capa_json(ruta), {})
        self.assertEqual(govconfig._leer_capa(ruta)[1], {})
        ruta.write_text(json.dumps({"a": 1}), encoding="utf-8")
        self.assertEqual(ds_guard._leer_capa_json(ruta), govconfig._leer_capa(ruta)[1])
        # Diferencia deliberada: ilegible/no-objeto es `malformado`, no `{}`.
        for contenido in ("{{{", "[1]"):
            ruta.write_text(contenido, encoding="utf-8")
            self.assertEqual(ds_guard._leer_capa_json(ruta), {})
            self.assertEqual(govconfig._leer_capa(ruta)[0], "malformado")

    def test_codigos_paridad_con_modelgov(self):
        self.assertEqual(modelgov.CODE_GOVCFG_INVALID, govconfig.CODE_INVALID)
        self.assertEqual(modelgov.CODE_GOVCFG_UNRESOLVABLE, govconfig.CODE_UNRESOLVABLE)
        self.assertEqual(modelgov.CODE_GOVCFG_HARDENING_MISMATCH, govconfig.CODE_HARDENING_MISMATCH)
        self.assertEqual(modelgov.CODE_GOVCFG_LOCAL_ACTIVE, govconfig.CODE_LOCAL_ACTIVE)


class TestTablaR29(Mundo):
    def codes(self, a):
        return {h.code for h in a.hallazgos}

    def test_sin_hardening_normal(self):
        a = self.eval_ctx(self.armar("low"))
        self.assertEqual(a.governance_completeness, "complete")

    def test_governance_none_identico_a_change3(self):
        card = self.armar("medium")
        self.assertEqual(self.evaluar(card).a_dict(), self.evaluar(card, governance=None).a_dict())
        self.assertEqual(self.evaluar(card).governance_completeness, "complete")

    def test_none_y_cita_hardening_incomplete(self):
        card = self.armar("low", hardening=tm.hardening(floor="low"))
        (self.raiz / RUTA).unlink()
        a = self.eval_ctx(card)
        self.assertEqual(a.governance_completeness, "incomplete")

    def test_resolved_correcto_pineado(self):
        card = self.armar("low", hardening=tm.hardening(floor="low"))
        a = self.eval_ctx(card)
        self.assertEqual(a.governance_completeness, "complete", a.hallazgos)

    def test_omitido_stale(self):
        card = self.armar("low")
        self.escribir_json(RUTA, tm.hardening(floor="low").to_dict())
        a = self.eval_ctx(card)
        self.assertEqual(a.governance_completeness, "stale")
        self.assertIn("GOVCFG-HARDENING-MISMATCH", self.codes(a))

    def test_hash_viejo_stale(self):
        card = self.armar("low", hardening=tm.hardening(floor="low"))
        self.escribir_json(RUTA, tm.hardening(floor="medium").to_dict())
        a = self.eval_ctx(card)
        self.assertEqual(a.governance_completeness, "stale")
        self.assertIn("GOVCFG-HARDENING-MISMATCH", self.codes(a))

    def test_otro_documento_stale(self):
        h = tm.hardening(floor="low")
        card = self.armar("low", hardening=h)
        # El proyecto pasa a otro documento con el mismo contenido citado en otra ruta.
        otro = core.EvidenceRef(
            "ev-hard", "governance_policy", tm.POLICY_ID, resolvers.hash_document(h.to_dict()), tm.T0,
            locator="gobierno/otro.json",
        )
        self.escribir_json("gobierno/otro.json", h.to_dict())
        evid = tuple(otro if e.evidence_id == "ev-hard" else e for e in card.evidence)
        card2 = self.armar("low", hardening=h)
        card2 = type(card2)(**{**{f: getattr(card2, f) for f in (
            "schema_version", "card_kind", "kind_schema_version", "card_id", "title", "subject",
            "created_at", "generated_at", "attestations", "claims", "body")}, "evidence": evid})
        a = self.eval_ctx(card2)
        self.assertEqual(a.governance_completeness, "stale")
        self.assertIn("GOVCFG-HARDENING-MISMATCH", self.codes(a))

    def test_effective_distinto_stale(self):
        card = self.armar("low", hardening=tm.hardening(floor="low"), policy_cambios={"effective_sha256": "d" * 64})
        a = self.eval_ctx(card)
        self.assertEqual(a.governance_completeness, "stale")
        self.assertIn("GOVCFG-HARDENING-MISMATCH", self.codes(a))

    def test_relajacion_invalid_sin_evaluar_requisitos(self):
        card = self.armar("low")
        self.escribir_json(RUTA, relajante().to_dict())
        a = self.eval_ctx(card)
        self.assertEqual(a.governance_completeness, "invalid")
        self.assertEqual(a.requisitos, ())
        self.assertIn("GOVCFG-INVALID", self.codes(a))

    def test_ilegible_incomplete(self):
        card = self.armar("low")
        (self.raiz / RUTA).mkdir(parents=True)
        a = self.eval_ctx(card)
        self.assertEqual(a.governance_completeness, "incomplete")
        self.assertIn("GOVCFG-UNRESOLVABLE", self.codes(a))

    def test_solo_local_stale(self):
        card = self.armar("low")
        self.escribir_local({govconfig.CLAVE_LOCAL: tm.hardening(floor="low").to_dict()})
        a = self.eval_ctx(card)
        self.assertEqual(a.governance_completeness, "stale")
        self.assertIn("GOVCFG-LOCAL-ACTIVE", self.codes(a))
        self.assertTrue(any("restricción local activa en esta máquina" in h.detail for h in a.hallazgos))

    def test_local_relaja_invalid(self):
        card = self.armar("low")
        self.escribir_local({govconfig.CLAVE_LOCAL: relajante().to_dict()})
        self.assertEqual(self.eval_ctx(card).governance_completeness, "invalid")

    def test_requisitos_contra_policy_actual(self):
        # Proyecto endurece low -> exige security_evidence required en low; el assessment viejo no la tiene.
        h = tm.hardening(overrides=[tm.override(
            "security_evidence", low=tm.L("required", ("observed", "attestation"), govpolicy.EXTERNAL_EVIDENCE_KINDS))])
        card = self.armar("low", hardening=h)
        a = self.eval_ctx(card)
        self.assertIn("security_evidence", tm.ids_req(a))
        self.assertNotEqual(a.governance_completeness, "complete")

    def test_base_distinta_rechazada(self):
        card = self.armar("low")
        otra = govpolicy.GovernancePolicy("otra-base", 1, govpolicy.BASE_POLICY.requirements)
        with self.assertRaises(core.CardError):
            self.evaluar(card, governance=self.gov_ctx(), base=otra)


if __name__ == "__main__":
    unittest.main()

"""Tests de `tools.cards.modelgov` (Change `20261005-model-risk-responsible-ai`,
R6-R12, R31-R55, R60-R64).

Usan OBJETOS REALES en directorios temporales: Model Cards escritas con
`modelcard.write_model_card`, documentos de evidencia (`evidence_document`) como
archivos del proyecto pineados por el sha256 de sus bytes, un `ExecutionRecord` real
de `leadrun`, métricas reales de `modelquality` y documentos de endurecimiento JSON
pineados como `governance_policy`. Sin mocks.

Los códigos y estados son los REALES del código de producción. La ubicación y la
escritura (`card_path`, `write_governance_assessment`) se prueban en
`test_modelgov_location.py`.
"""
from __future__ import annotations

import copy
import dataclasses
import hashlib
import itertools
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.cards import assess, core, govpolicy, modelcard, modelgov, resolvers
from tools.leadrun import core as lr
from tools.modelquality import core as mq

T0 = "2026-10-01T10:00:00Z"
NOW = "2026-10-04T00:00:00Z"
REPO = Path(__file__).resolve().parents[3]

REL_MET = "evaluacion/metricas.json"
REL_HARD = "gobierno/endurecimiento.json"
DOCS = {
    "eq": "docs/informe-eq.txt",
    "ex": "docs/informe-ex.txt",
    "pr": "docs/informe-priv.txt",
    "pr2": "docs/informe-priv2.txt",
}

POLICY_ID = govpolicy.BASE_POLICY.policy_id
APPROVAL = {"change_id": "20261005-model-risk-responsible-ai", "artefacto": "spec.md", "hash": "b" * 64}

# Claves de estado / juicio que jamás deben persistirse ni aceptarse en el body (R32, R38, R55).
CLAVES_PROHIBIDAS = (
    "status", "governance_completeness", "fair", "passed", "score", "secure", "ethical",
    "risk_assessment_result", "risk_score", "completeness",
)


# ---------------------------------------------------------------------------
# Helpers genéricos
# ---------------------------------------------------------------------------


def sha_bytes(datos: bytes) -> str:
    return hashlib.sha256(datos).hexdigest()


def hacer_att(aid, claim, kind="declared", **kw):
    base = dict(
        attestation_id=aid,
        claim=claim,
        actor="ana",
        authority="owner-modelo",
        attested_at=T0,
        scope="Governance del modelo",
        attestation_kind=kind,
    )
    if kind == "anchored":
        base["approval_ref"] = dict(APPROVAL)
    base.update(kw)
    return core.HumanAttestation(**base)


def hacer_model_card(model_id="clasificador", version="1.0.0", descripcion="Modelo de prueba"):
    return core.CardEnvelope(
        schema_version=1,
        card_kind="model_card",
        kind_schema_version=1,
        card_id=modelcard.model_card_id(model_id, version),
        title="Model Card de prueba",
        subject=model_id,
        created_at=T0,
        generated_at=T0,
        body={"model_id": model_id, "model_version": version, "description": descripcion},
    )


def L(severity, accepts, kinds=None, minimo="declared"):
    return govpolicy.LevelSpec(severity, accepts, kinds, minimo)


def hardening(floor=None, overrides=(), additional=()):
    return govpolicy.HardeningDocument(
        policy_id=POLICY_ID, base_version=1, risk_floor=floor,
        overrides=tuple(overrides), additional=tuple(additional),
    )


def override(rid, **por_nivel):
    return govpolicy.RequirementOverride(rid, por_nivel)


def codigos(a):
    return {h.code for h in a.hallazgos}


def estado_req(a, rid):
    for r in a.requisitos:
        if r[0] == rid:
            return r[3]
    raise AssertionError(f"requisito {rid} ausente")


def ids_req(a):
    return {r[0] for r in a.requisitos}


def estado_dim(a, dim):
    for d in a.dimensiones:
        if d[0] == dim:
            return d[1]
    raise AssertionError(f"dimensión {dim} ausente")


def estado_ev(a, eid):
    return dict(a.evidencias)[eid]


def claves_recursivas(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from claves_recursivas(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from claves_recursivas(v)


def snapshot(raiz: Path) -> dict:
    return {p.relative_to(raiz).as_posix(): p.read_bytes() for p in sorted(raiz.rglob("*")) if p.is_file()}


def dim_na(dim, rid, att="at-na", rationale="No aplica por el tipo de modelo", **extra):
    item = {"requirement_id": rid, "rationale": rationale, "attestation_id": att}
    item.update(extra)
    return {dim: {"not_applicable": [item]}}


# ---------------------------------------------------------------------------
# Mundo
# ---------------------------------------------------------------------------


class BaseGov(unittest.TestCase):
    """Mundo temporal con Model Card real, documentos, métricas y ExecutionRecord reales."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.raiz = Path(self._tmp.name).resolve()
        self.model_id = "clasificador"
        self.version = "1.0.0"

        for clave, rel in DOCS.items():
            self.escribir_bytes(rel, f"informe externo {clave}\n".encode("utf-8"))
        self.ctx = mq.EvaluationContext("ctx-test", "test")
        self.escribir_metricas(0.9)
        self.registro = lr.ExecutionRecord(
            execution_id="script__aaaaaaaaaaaa",
            command_form="script",
            argv=("python", "entrenar.py"),
            code_hash=None,
            exit_code=0,
            duration_seconds=1.5,
            stdout_summary="ok",
            stderr_summary="",
            outputs_hash=None,
            executed_by="lead",
            mode="supervised",
            approval=None,
            generated_at=T0,
            timed_out=False,
        )
        self.escribir_json(
            f".harmessi/executions/{self.registro.execution_id}/record.json", self.registro.to_dict()
        )
        self.escribir_model_card()

    # -- archivos -----------------------------------------------------------

    def escribir_bytes(self, rel, datos: bytes):
        ruta = self.raiz / rel
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_bytes(datos)
        return ruta

    def escribir_json(self, rel, obj):
        return self.escribir_bytes(rel, (json.dumps(obj, indent=2, sort_keys=True) + "\n").encode("utf-8"))

    def escribir_metricas(self, valor):
        self.escribir_json(REL_MET, [mq.ObservedMetric("accuracy", valor, self.ctx, sample_size=100).to_dict()])

    def escribir_model_card(self, model_id=None, version=None, descripcion="Modelo de prueba", replace=False):
        card = hacer_model_card(model_id or self.model_id, version or self.version, descripcion)
        return modelcard.write_model_card(self.raiz, card, replace=replace, clock=lambda: NOW)

    # -- pins ---------------------------------------------------------------

    def pin_model_card(self, eid="ev-mc", model_id=None, version=None, **cambios):
        cid = modelcard.model_card_id(model_id or self.model_id, version or self.version)
        h = assess.read_card(modelcard.card_path(self.raiz, cid)).content_sha256()
        base = dict(
            evidence_id=eid, kind="model_card", ref_id=f"{cid}__{h[:12]}", content_sha256=h, pinned_at=T0,
            locator=f"governance/cards/model/{cid}.json",
        )
        base.update(cambios)
        return core.EvidenceRef(**base)

    def pin_doc(self, eid, ref_id, clave):
        rel = DOCS[clave]
        return core.EvidenceRef(
            eid, "evidence_document", ref_id, sha_bytes((self.raiz / rel).read_bytes()), T0, locator=rel
        )

    def pin_metric(self, eid="ev-met"):
        datos = json.loads((self.raiz / REL_MET).read_text(encoding="utf-8"))
        return core.EvidenceRef(
            eid, "observed_metric", "metricas-test", resolvers.hash_document(datos), T0,
            member="accuracy@ctx-test", locator=REL_MET,
        )

    def pin_exec(self, eid="ev-exec"):
        return core.EvidenceRef(
            eid, "execution_record", self.registro.execution_id,
            resolvers.hash_execution_record(self.registro.to_dict()), T0,
        )

    def pin_hardening(self, doc_o_dict, eid="ev-hard"):
        datos = doc_o_dict.to_dict() if hasattr(doc_o_dict, "to_dict") else doc_o_dict
        self.escribir_json(REL_HARD, datos)
        return core.EvidenceRef(
            eid, "governance_policy", POLICY_ID, resolvers.hash_document(datos), T0, locator=REL_HARD
        )

    # -- policy_ref ---------------------------------------------------------

    def policy_ref(self, doc=None, cita=False, **cambios):
        try:
            efectiva = govpolicy.merge(govpolicy.BASE_POLICY, doc).effective_sha256()
        except govpolicy.GovPolicyError:
            efectiva = "c" * 64
        ref = {
            "base_policy_id": POLICY_ID,
            "base_version": govpolicy.BASE_POLICY.version,
            "base_sha256": govpolicy.BASE_POLICY_SHA256,
            "effective_sha256": efectiva,
        }
        if cita:
            ref["hardening_evidence_id"] = "ev-hard"
        ref.update(cambios)
        return ref

    # -- configuraciones completas por nivel ---------------------------------

    def config(self, nivel):
        """Evidencia/atestaciones/claims que satisfacen TODOS los `required` del nivel."""
        anc = "anchored" if nivel == "high" else "declared"
        atts = [
            hacer_att("at-risk", f"risk_level={nivel}", anc),
            hacer_att("at-owner", "Responsable del modelo: equipo de ciencia de datos", anc, authority="equipo-datos"),
        ]
        claims = {"accountability_risk_declaration": ("at-risk",), "accountability_owner": ("at-owner",)}
        evid: list = []
        if nivel == "medium":
            evid = [self.pin_doc("ev-doc-eq", "informe-equidad", "eq"), self.pin_exec()]
            atts.append(hacer_att("at-priv", "Evidencia de privacidad documentada internamente"))
            claims.update(
                fairness_evidence=("ev-doc-eq",), privacy_evidence=("at-priv",), security_evidence=("ev-exec",)
            )
        elif nivel == "high":
            evid = [
                self.pin_doc("ev-doc-eq", "informe-equidad", "eq"),
                self.pin_doc("ev-doc-ex", "informe-explicabilidad", "ex"),
                self.pin_metric(),
            ]
            atts += [
                hacer_att("at-priv", "Evidencia de privacidad aprobada en comité", "anchored"),
                hacer_att("at-ovr", "Proceso de supervisión humana definido", "anchored"),
            ]
            claims.update(
                fairness_evidence=("ev-doc-eq",),
                explainability_evidence=("ev-doc-ex",),
                privacy_evidence=("at-priv",),
                security_evidence=("ev-met",),
                human_oversight_process=("at-ovr",),
            )
        return {"evidence": evid, "attestations": atts, "claims": claims, "riesgo": nivel}

    def ensamblar(self, evidence=(), attestations=(), claims=None, riesgo=None, risk_att="at-risk",
                  hardening=None, hard_datos=None, model_id=None, version=None, policy_cambios=None,
                  body_extra=None, dimensions=None, extra_claims=(), card_cambios=None):
        model_id = model_id or self.model_id
        version = version or self.version
        cid = modelcard.model_card_id(model_id, version)
        evid = [self.pin_model_card(model_id=model_id, version=version)] + list(evidence)
        todos = {"model_card_pin": ("ev-mc",)}
        hard_pin = None
        if hardening is not None:
            hard_pin = self.pin_hardening(hardening)
        elif hard_datos is not None:
            hard_pin = self.pin_hardening(hard_datos)
        if hard_pin is not None:
            evid.append(hard_pin)
            todos["policy_hardening_pin"] = ("ev-hard",)
        todos.update(claims or {})
        objs = [
            core.Claim("c-" + rid, "Respaldo de requisito", supports=tuple(sop), requirement_id=rid)
            for rid, sop in todos.items()
        ] + list(extra_claims)
        body = {
            "model_card_ref": {"evidence_id": "ev-mc"},
            "policy_ref": self.policy_ref(hardening, hard_pin is not None, **(policy_cambios or {})),
        }
        if riesgo is not None:
            body["risk_declaration"] = {"level": riesgo, "attestation_id": risk_att}
        if dimensions is not None:
            body["dimensions"] = dimensions
        body.update(body_extra or {})
        kw = dict(
            schema_version=1,
            card_kind="governance_assessment",
            kind_schema_version=1,
            card_id=cid,
            title="Assessment de governance de prueba",
            subject=model_id,
            created_at=T0,
            generated_at=T0,
            evidence=tuple(evid),
            attestations=tuple(attestations),
            claims=tuple(objs),
            body=body,
        )
        kw.update(card_cambios or {})
        return core.CardEnvelope(**kw)

    def armar(self, nivel, **cambios):
        cfg = self.config(nivel)
        cfg.update(cambios)
        return self.ensamblar(**cfg)

    def evaluar(self, card, **kw):
        kw.setdefault("clock", lambda: NOW)
        return modelgov.evaluate_governance_assessment(card, self.raiz, **kw)

    def sin_att(self, cfg, aid):
        cfg["attestations"] = [a for a in cfg["attestations"] if a.attestation_id != aid]


# ---------------------------------------------------------------------------
# Assessments completos
# ---------------------------------------------------------------------------


class TestCompletos(BaseGov):
    def test_low_medium_high_completos(self):
        for nivel in ("low", "medium", "high"):
            with self.subTest(nivel=nivel):
                a = self.evaluar(self.armar(nivel))
                self.assertEqual(a.governance_completeness, "complete", a.hallazgos)
                self.assertEqual(a.effective_level, nivel)
                self.assertEqual(a.declared_level, nivel)
                self.assertIsNone(a.risk_floor)
                self.assertEqual(a.hallazgos, ())
                for _rid, sev, _dim, estado, _det in a.requisitos:
                    if sev == "required":
                        self.assertIn(estado, ("satisfied", "not_applicable"))
                self.assertEqual(estado_req(a, "model_card_pin"), "satisfied")
                self.assertEqual(estado_ev(a, "ev-mc"), "fresh")

    def test_requisitos_derivados_por_nivel(self):
        base = {"model_card_pin", "accountability_risk_declaration", "accountability_owner",
                "privacy_evidence", "security_evidence"}
        completo = base | {"human_oversight_process", "fairness_evidence", "explainability_evidence"}
        esperado = {"low": base, "medium": completo, "high": completo}
        for nivel, ids in esperado.items():
            with self.subTest(nivel=nivel):
                self.assertEqual(ids_req(self.evaluar(self.armar(nivel))), ids)

    def test_severidades_por_nivel_de_la_matriz(self):
        sev = lambda a: {r[0]: r[1] for r in a.requisitos}  # noqa: E731
        low = sev(self.evaluar(self.armar("low")))
        self.assertEqual(low["privacy_evidence"], "recommended")
        self.assertEqual(low["security_evidence"], "recommended")
        medium = sev(self.evaluar(self.armar("medium")))
        self.assertEqual(medium["fairness_evidence"], "required")
        self.assertEqual(medium["human_oversight_process"], "recommended")
        self.assertEqual(medium["explainability_evidence"], "recommended")
        high = sev(self.evaluar(self.armar("high")))
        for rid in ("human_oversight_process", "explainability_evidence", "fairness_evidence"):
            self.assertEqual(high[rid], "required")

    def test_recomendados_sin_claim_no_impiden_complete(self):
        a = self.evaluar(self.armar("medium"))
        self.assertEqual(a.governance_completeness, "complete")
        self.assertEqual(estado_req(a, "explainability_evidence"), "missing")
        self.assertEqual(estado_req(a, "human_oversight_process"), "missing")

    def test_nota_presente_y_politica_pineada_y_recomputada(self):
        a = self.evaluar(self.armar("low"))
        self.assertEqual(a.nota, modelgov.NOTA_COMPLETENESS)
        self.assertEqual(a.a_dict()["nota"], modelgov.NOTA_COMPLETENESS)
        self.assertEqual(a.policy["pinned"]["base_sha256"], govpolicy.BASE_POLICY_SHA256)
        self.assertEqual(a.policy["recomputed"]["base_sha256"], govpolicy.BASE_POLICY_SHA256)
        self.assertEqual(a.policy["pinned"]["effective_sha256"], a.policy["recomputed"]["effective_sha256"])
        self.assertIsNone(a.policy["recomputed"]["hardening_sha256"])
        self.assertEqual(a.card_id, "clasificador__1_0_0")

    def test_sin_claims_ni_pins_de_requisitos_es_incomplete(self):
        card = self.ensamblar(riesgo=None)
        a = self.evaluar(card)
        self.assertEqual(a.governance_completeness, "incomplete")

    def test_resultado_es_inmutable(self):
        a = self.evaluar(self.armar("low"))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            a.governance_completeness = "complete"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Declaración de riesgo (R33, R33b, R33c, R34, R31)
# ---------------------------------------------------------------------------


class TestDeclaracionRiesgo(BaseGov):
    def test_low_declared_satisface_la_declaracion(self):
        a = self.evaluar(self.armar("low"))
        self.assertEqual(estado_req(a, "accountability_risk_declaration"), "satisfied")
        self.assertEqual(a.governance_completeness, "complete")

    def test_misma_atestacion_es_el_soporte_sin_segunda_atestacion(self):
        card = self.armar("low")
        riesgo = [x for x in card.attestations if re.fullmatch(r"risk_level=(low|medium|high)", x.claim)]
        self.assertEqual(len(riesgo), 1)
        claim = [c for c in card.claims if c.requirement_id == "accountability_risk_declaration"][0]
        self.assertEqual(claim.supports, (riesgo[0].attestation_id,))
        self.assertEqual(self.evaluar(card).governance_completeness, "complete")

    def test_high_solo_declared_es_insatisfecho(self):
        cfg = self.config("high")
        cfg["attestations"][0] = hacer_att("at-risk", "risk_level=high", "declared")
        a = self.evaluar(self.ensamblar(**cfg))
        self.assertEqual(estado_req(a, "accountability_risk_declaration"), "untrusted_type")
        self.assertEqual(a.governance_completeness, "incomplete")
        self.assertEqual(a.effective_level, "high")

    def test_high_anchored_satisface(self):
        a = self.evaluar(self.armar("high"))
        self.assertEqual(estado_req(a, "accountability_risk_declaration"), "satisfied")
        self.assertEqual(a.governance_completeness, "complete")

    def test_medium_declared_satisface(self):
        a = self.evaluar(self.armar("medium"))
        self.assertEqual(estado_req(a, "accountability_risk_declaration"), "satisfied")

    def test_declaracion_ausente_es_incomplete_nunca_complete(self):
        cfg = self.config("low")
        cfg["riesgo"] = None
        self.sin_att(cfg, "at-risk")
        del cfg["claims"]["accountability_risk_declaration"]
        a = self.evaluar(self.ensamblar(**cfg))
        self.assertEqual(a.governance_completeness, "incomplete")
        self.assertIsNone(a.declared_level)
        self.assertEqual(a.effective_level, "low")  # informativo: max(floor, low)
        self.assertEqual(estado_req(a, "accountability_risk_declaration"), "missing")
        self.assertNotEqual(a.governance_completeness, "complete")

    def test_atestacion_de_riesgo_sin_risk_declaration_en_el_body_es_incomplete(self):
        cfg = self.config("low")
        cfg["riesgo"] = None
        del cfg["claims"]["accountability_risk_declaration"]
        a = self.evaluar(self.ensamblar(**cfg))
        self.assertEqual(a.governance_completeness, "incomplete")
        self.assertIsNone(a.declared_level)

    def test_claim_de_declaracion_sin_risk_declaration_es_invalid(self):
        cfg = self.config("low")
        cfg["riesgo"] = None
        a = self.evaluar(self.ensamblar(**cfg))
        self.assertEqual(a.governance_completeness, "invalid")
        self.assertIn(modelgov.CODE_CLAIM_SUPPORT_INCONSISTENT, codigos(a))

    def test_declaraciones_con_niveles_distintos_son_invalid(self):
        cfg = self.config("low")
        cfg["attestations"].append(hacer_att("at-risk-b", "risk_level=high"))
        a = self.evaluar(self.ensamblar(**cfg))
        self.assertEqual(a.governance_completeness, "invalid")
        self.assertIn(modelgov.CODE_RISK_DECLARATION_CONTRADICTORY, codigos(a))

    def test_contradiccion_sin_risk_declaration_tambien_es_invalid(self):
        cfg = self.config("low")
        cfg["riesgo"] = None
        del cfg["claims"]["accountability_risk_declaration"]
        cfg["attestations"].append(hacer_att("at-risk-b", "risk_level=high"))
        a = self.evaluar(self.ensamblar(**cfg))
        self.assertEqual(a.governance_completeness, "invalid")
        self.assertIn(modelgov.CODE_RISK_DECLARATION_CONTRADICTORY, codigos(a))

    def test_nunca_se_elige_el_maximo_ni_la_primera(self):
        for orden in itertools.permutations(("low", "high")):
            with self.subTest(orden=orden):
                cfg = self.config("low")
                cfg["attestations"] = [a for a in cfg["attestations"] if a.attestation_id == "at-owner"]
                cfg["attestations"] += [hacer_att(f"at-r{i}", f"risk_level={n}") for i, n in enumerate(orden)]
                cfg["claims"]["accountability_risk_declaration"] = ("at-r0",)
                cfg["riesgo"] = orden[0]
                cfg["risk_att"] = "at-r0"
                a = self.evaluar(self.ensamblar(**cfg))
                self.assertEqual(a.governance_completeness, "invalid")

    def test_misma_declaracion_repetida_se_deduplica_sin_error(self):
        cfg = self.config("low")
        cfg["attestations"].append(hacer_att("at-risk-b", "risk_level=low"))
        a = self.evaluar(self.ensamblar(**cfg))
        self.assertEqual(a.governance_completeness, "complete", a.hallazgos)
        self.assertNotIn(modelgov.CODE_RISK_DECLARATION_CONTRADICTORY, codigos(a))

    def test_body_level_distinto_del_claim_es_invalid(self):
        cfg = self.config("low")
        cfg["riesgo"] = "medium"  # la atestación dice risk_level=low
        a = self.evaluar(self.ensamblar(**cfg))
        self.assertEqual(a.governance_completeness, "invalid")
        self.assertIn(modelgov.CODE_RISK_DECLARATION_CONTRADICTORY, codigos(a))

    def test_level_fuera_del_vocabulario_es_invalid(self):
        for nivel in ("critical", "unassessed", "LOW", "", None, 1):
            with self.subTest(nivel=nivel):
                card = self.armar("low")
                body = copy.deepcopy(card.body)
                body["risk_declaration"]["level"] = nivel
                a = self.evaluar(dataclasses.replace(card, body=body))
                self.assertEqual(a.governance_completeness, "invalid")
                self.assertIn(modelgov.CODE_BODY_INVALID, codigos(a))

    def test_atestacion_de_declaracion_con_claim_libre_es_invalid(self):
        cfg = self.config("low")
        cfg["attestations"][0] = hacer_att("at-risk", "el riesgo es bajo")
        a = self.evaluar(self.ensamblar(**cfg))
        self.assertEqual(a.governance_completeness, "invalid")
        self.assertIn(modelgov.CODE_REF_INCONSISTENT, codigos(a))

    def test_attestation_id_dangling_o_de_evidencia(self):
        for att_id, codigo in (("at-no-existe", modelgov.CODE_DANGLING_EVIDENCE),
                               ("ev-mc", modelgov.CODE_REF_INCONSISTENT)):
            with self.subTest(att_id=att_id):
                card = self.armar("low")
                body = copy.deepcopy(card.body)
                body["risk_declaration"]["attestation_id"] = att_id
                a = self.evaluar(dataclasses.replace(card, body=body))
                self.assertEqual(a.governance_completeness, "invalid")
                self.assertIn(codigo, codigos(a))

    def test_claim_de_declaracion_debe_incluir_la_atestacion_de_risk_declaration(self):
        cfg = self.config("low")
        cfg["claims"]["accountability_risk_declaration"] = ("at-owner",)
        a = self.evaluar(self.ensamblar(**cfg))
        self.assertEqual(a.governance_completeness, "invalid")
        self.assertIn(modelgov.CODE_CLAIM_SUPPORT_INCONSISTENT, codigos(a))

    def test_nivel_declarado_menor_al_floor_se_evalua_con_el_floor_e_incomplete(self):
        cfg = self.config("medium")
        cfg["attestations"][0] = hacer_att("at-risk", "risk_level=low")
        cfg["riesgo"] = "low"
        a = self.evaluar(self.ensamblar(hardening=hardening(floor="medium"), **cfg))
        self.assertEqual(a.declared_level, "low")
        self.assertEqual(a.risk_floor, "medium")
        self.assertEqual(a.effective_level, "medium")
        self.assertIn(modelgov.CODE_RISK_BELOW_FLOOR, codigos(a))
        self.assertEqual(a.governance_completeness, "incomplete")
        # se evaluó con las exigencias de medium (requisitos de medium derivados) y todos los required se satisfacen
        self.assertIn("fairness_evidence", ids_req(a))
        for _rid, sev, _dim, estado, _det in a.requisitos:
            if sev == "required":
                self.assertIn(estado, ("satisfied", "not_applicable"))

    def test_declarado_igual_o_mayor_al_floor_no_genera_hallazgo(self):
        a = self.evaluar(self.armar("medium", hardening=hardening(floor="medium")))
        self.assertEqual(a.governance_completeness, "complete", a.hallazgos)
        self.assertNotIn(modelgov.CODE_RISK_BELOW_FLOOR, codigos(a))
        a = self.evaluar(self.armar("high", hardening=hardening(floor="medium")))
        self.assertEqual(a.effective_level, "high")
        self.assertEqual(a.governance_completeness, "complete", a.hallazgos)

    def test_owner_es_requisito_distinto_de_la_declaracion(self):
        cfg = self.config("low")
        del cfg["claims"]["accountability_owner"]
        a = self.evaluar(self.ensamblar(**cfg))
        self.assertEqual(estado_req(a, "accountability_risk_declaration"), "satisfied")
        self.assertEqual(estado_req(a, "accountability_owner"), "missing")
        self.assertEqual(a.governance_completeness, "incomplete")

    def test_owner_con_rol_o_equipo_satisface(self):
        cfg = self.config("low")
        cfg["attestations"][1] = hacer_att(
            "at-owner", "Responsable del modelo: rol data-owner", authority="rol-data-owner", scope="Equipo de datos"
        )
        a = self.evaluar(self.ensamblar(**cfg))
        self.assertEqual(estado_req(a, "accountability_owner"), "satisfied")
        self.assertEqual(a.governance_completeness, "complete")

    def test_owner_declared_en_high_es_untrusted_type(self):
        cfg = self.config("high")
        cfg["attestations"][1] = hacer_att("at-owner", "Responsable del modelo: equipo de datos")
        a = self.evaluar(self.ensamblar(**cfg))
        self.assertEqual(estado_req(a, "accountability_owner"), "untrusted_type")
        self.assertEqual(a.governance_completeness, "incomplete")


# ---------------------------------------------------------------------------
# Model Card pineada (R7, R8, R50a)
# ---------------------------------------------------------------------------


class TestModelCard(BaseGov):
    def test_model_card_valida_y_fresca(self):
        a = self.evaluar(self.armar("low"))
        self.assertEqual(estado_ev(a, "ev-mc"), "fresh")
        self.assertEqual(estado_req(a, "model_card_pin"), "satisfied")

    def test_model_card_ausente_es_unresolvable_e_incomplete(self):
        card = self.armar("low")
        modelcard.card_path(self.raiz, "clasificador__1_0_0").unlink()
        a = self.evaluar(card)
        self.assertEqual(estado_ev(a, "ev-mc"), "unresolvable")
        self.assertEqual(estado_req(a, "model_card_pin"), "unresolvable")
        self.assertEqual(a.governance_completeness, "incomplete")

    def test_model_card_revisada_deja_stale(self):
        card = self.armar("low")
        self.escribir_model_card(descripcion="Descripción revisada", replace=True)
        a = self.evaluar(card)
        self.assertEqual(estado_ev(a, "ev-mc"), "stale")
        self.assertEqual(estado_req(a, "model_card_pin"), "stale")
        self.assertEqual(a.governance_completeness, "stale")

    def test_model_card_editada_en_disco_deja_stale_o_unverifiable_nunca_complete(self):
        card = self.armar("low")
        ruta = modelcard.card_path(self.raiz, "clasificador__1_0_0")
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        datos["body"]["description"] = "editada a mano"
        ruta.write_text(json.dumps(datos), encoding="utf-8")  # revision_id ya no coincide
        a = self.evaluar(card)
        self.assertNotEqual(a.governance_completeness, "complete")
        self.assertIn(estado_ev(a, "ev-mc"), ("stale", "unverifiable"))

    def test_card_id_distinto_del_derivado_de_ref_id(self):
        card = dataclasses.replace(self.armar("low"), card_id="otro__1_0_0")
        a = self.evaluar(card)
        self.assertEqual(a.governance_completeness, "invalid")
        self.assertIn(modelgov.CODE_IDENTITY_MISMATCH, codigos(a))

    def test_subject_distinto_de_model_id(self):
        card = dataclasses.replace(self.armar("low"), subject="otro")
        a = self.evaluar(card)
        self.assertEqual(a.governance_completeness, "invalid")
        self.assertIn(modelgov.CODE_IDENTITY_MISMATCH, codigos(a))

    def test_pin_no_decodificable_como_model_card_id(self):
        card = self.armar("low")
        pin = card.evidence[0]
        h = pin.content_sha256
        malo = dataclasses.replace(pin, ref_id=f"sinversion__{h[:12]}", locator=None)
        card = dataclasses.replace(card, evidence=(malo,) + card.evidence[1:], card_id="sinversion", subject="sinversion")
        a = self.evaluar(card)
        self.assertEqual(a.governance_completeness, "invalid")
        self.assertIn(modelgov.CODE_IDENTITY_MISMATCH, codigos(a))

    def test_pin_inconsistente_es_invalid(self):
        casos = {
            "hash12 distinto": dict(ref_id="clasificador__1_0_0__" + "0" * 12),
            "sin hash12": dict(ref_id="clasificador__1_0_0"),
            "locator distinto": dict(locator="governance/cards/model/otro__1_0_0.json"),
        }
        for nombre, cambios in casos.items():
            with self.subTest(caso=nombre):
                card = self.armar("low")
                pin = dataclasses.replace(card.evidence[0], **cambios)
                a = self.evaluar(dataclasses.replace(card, evidence=(pin,) + card.evidence[1:]))
                self.assertEqual(a.governance_completeness, "invalid")
                self.assertIn(modelgov.CODE_REF_INCONSISTENT, codigos(a))

    def test_model_card_ref_debe_apuntar_a_un_pin_model_card(self):
        for eid, codigo in (("ev-doc-eq", modelgov.CODE_REF_INCONSISTENT),
                            ("at-owner", modelgov.CODE_REF_INCONSISTENT),
                            ("ev-no-existe", modelgov.CODE_DANGLING_EVIDENCE)):
            with self.subTest(eid=eid):
                card = self.armar("medium")
                body = copy.deepcopy(card.body)
                body["model_card_ref"]["evidence_id"] = eid
                a = self.evaluar(dataclasses.replace(card, body=body))
                self.assertEqual(a.governance_completeness, "invalid")
                self.assertIn(codigo, codigos(a))

    def test_model_card_ref_obligatorio(self):
        card = self.armar("low")
        body = copy.deepcopy(card.body)
        del body["model_card_ref"]
        a = self.evaluar(dataclasses.replace(card, body=body))
        self.assertEqual(a.governance_completeness, "invalid")
        self.assertIn(modelgov.CODE_BODY_INVALID, codigos(a))

    def test_version_de_modelo_distinta_es_otra_model_card_y_otro_assessment(self):
        self.escribir_model_card(version="2.0.0")
        v1 = self.armar("low")
        cfg = self.config("low")
        v2 = self.ensamblar(version="2.0.0", **cfg)
        self.assertNotEqual(v1.card_id, v2.card_id)
        self.assertEqual(v2.card_id, "clasificador__2_0_0")
        a1, a2 = self.evaluar(v1), self.evaluar(v2)
        self.assertEqual(a1.governance_completeness, "complete")
        self.assertEqual(a2.governance_completeness, "complete")
        self.assertNotEqual(a1.card_id, a2.card_id)
        self.assertNotEqual(
            modelgov.card_path(self.raiz, v1.card_id), modelgov.card_path(self.raiz, v2.card_id)
        )

    def test_revisar_la_model_v1_no_afecta_al_assessment_v2(self):
        self.escribir_model_card(version="2.0.0")
        v2 = self.ensamblar(version="2.0.0", **self.config("low"))
        self.escribir_model_card(descripcion="v1 revisada", replace=True)  # v1.0.0
        self.assertEqual(self.evaluar(v2).governance_completeness, "complete")

    def test_assessment_de_una_version_con_pin_de_otra_es_identity_mismatch(self):
        self.escribir_model_card(version="2.0.0")
        card = self.ensamblar(version="2.0.0", **self.config("low"))
        card = dataclasses.replace(card, card_id="clasificador__1_0_0")
        a = self.evaluar(card)
        self.assertEqual(a.governance_completeness, "invalid")
        self.assertIn(modelgov.CODE_IDENTITY_MISMATCH, codigos(a))

    def test_paridad_de_decodificacion_con_modelcard(self):
        vectores = (
            "clasificador__1_0_0", "a__1", "modelo-a__2_1_3", "m_x__1_0_0", "m__1-rc1", "a", "a__b__c", "A__1",
            "x__", "__1", "a__1__", "a__1_", "a__-1", "", None, 5, "a" + "b" * 70 + "__1", "a__1.0",
        )
        for card_id in vectores:
            with self.subTest(card_id=card_id):
                try:
                    esperado = modelcard.decode_model_card_id(card_id)
                except core.CardError:
                    esperado = None
                try:
                    obtenido = modelgov._decodificar_card_id(card_id)
                except core.CardError:
                    obtenido = None
                self.assertEqual(obtenido, esperado)

    def test_decodificacion_invalida_usa_identity_mismatch(self):
        with self.assertRaises(core.CardError) as cm:
            modelgov._decodificar_card_id("sinseparador")
        self.assertEqual(cm.exception.code, modelgov.CODE_IDENTITY_MISMATCH)


# ---------------------------------------------------------------------------
# Policy base y endurecimiento (R10, R26-R29, R35, R50b-c)
# ---------------------------------------------------------------------------


class TestPolicyStaleness(BaseGov):
    def test_base_sha256_pineado_distinto_es_stale(self):
        a = self.evaluar(self.armar("low", policy_cambios={"base_sha256": "0" * 64}))
        self.assertEqual(a.governance_completeness, "stale")
        self.assertIn(modelgov.CODE_POLICY_CHANGED, codigos(a))

    def test_base_version_pineada_distinta_es_stale(self):
        a = self.evaluar(self.armar("low", policy_cambios={"base_version": 2}))
        self.assertEqual(a.governance_completeness, "stale")
        self.assertIn(modelgov.CODE_POLICY_CHANGED, codigos(a))

    def test_effective_sha256_pineado_distinto_es_stale(self):
        a = self.evaluar(self.armar("low", policy_cambios={"effective_sha256": "1" * 64}))
        self.assertEqual(a.governance_completeness, "stale")
        self.assertIn(modelgov.CODE_POLICY_CHANGED, codigos(a))

    def test_base_inyectada_de_otra_version_es_stale(self):
        card = self.armar("low")
        otra = govpolicy.GovernancePolicy(POLICY_ID, 2, govpolicy.BASE_POLICY.requirements)
        a = self.evaluar(card, base=otra)
        self.assertEqual(a.governance_completeness, "stale")
        self.assertIn(modelgov.CODE_POLICY_CHANGED, codigos(a))
        self.assertEqual(a.policy["pinned"]["base_version"], 1)
        self.assertEqual(a.policy["recomputed"]["base_version"], 2)

    def test_base_con_mismo_version_pero_otro_contenido_es_stale(self):
        card = self.armar("low")
        reqs = tuple(r for r in govpolicy.BASE_POLICY.requirements if r.requirement_id != "security_evidence")
        otra = govpolicy.GovernancePolicy(POLICY_ID, 1, reqs)
        a = self.evaluar(card, base=otra)
        self.assertEqual(a.governance_completeness, "stale")

    def test_base_con_otro_policy_id_es_invalid(self):
        card = self.armar("low")
        otra = govpolicy.GovernancePolicy("otra-policy", 1, govpolicy.BASE_POLICY.requirements)
        a = self.evaluar(card, base=otra)
        self.assertEqual(a.governance_completeness, "invalid")
        self.assertIn(modelgov.CODE_POLICY_INVALID, codigos(a))

    def test_argumentos_invalidos_lanzan_cardserror(self):
        card = self.armar("low")
        with self.assertRaises(core.CardError):
            self.evaluar(card, base="no-es-policy")
        with self.assertRaises(core.CardError):
            self.evaluar(card, resolvers="no-es-mapa")
        with self.assertRaises(core.CardError):
            self.evaluar(card, clock="no-callable")

    def test_policy_base_vigente_no_genera_hallazgos(self):
        a = self.evaluar(self.armar("low"))
        self.assertNotIn(modelgov.CODE_POLICY_CHANGED, codigos(a))


class TestHardening(BaseGov):
    def test_hardening_citado_fresco_es_complete_y_pinea_hash(self):
        doc = hardening(floor="low")
        a = self.evaluar(self.armar("low", hardening=doc))
        self.assertEqual(a.governance_completeness, "complete", a.hallazgos)
        self.assertEqual(estado_req(a, "policy_hardening_pin"), "satisfied")
        self.assertEqual(a.policy["recomputed"]["hardening_sha256"], doc.content_sha256())
        self.assertEqual(a.policy["pinned"]["hardening_evidence_id"], "ev-hard")

    def test_hardening_citado_y_archivo_borrado_es_incomplete_no_cae_a_la_base(self):
        card = self.armar("low", hardening=hardening(floor="low"))
        (self.raiz / REL_HARD).unlink()
        a = self.evaluar(card)
        self.assertEqual(a.governance_completeness, "incomplete")
        self.assertNotEqual(a.governance_completeness, "complete")
        self.assertEqual(estado_ev(a, "ev-hard"), "unresolvable")
        self.assertEqual(estado_req(a, "policy_hardening_pin"), "unresolvable")
        self.assertIsNone(a.effective_level)
        self.assertIsNone(a.policy["recomputed"]["effective_sha256"])
        self.assertIn(modelgov.CODE_POLICY_INVALID, codigos(a))

    def test_hardening_ilegible_no_cae_a_la_base(self):
        card = self.armar("low", hardening=hardening(floor="low"))
        (self.raiz / REL_HARD).write_bytes(b"esto no es json")
        a = self.evaluar(card)
        self.assertEqual(a.governance_completeness, "incomplete")
        self.assertIsNone(a.effective_level)

    def test_hardening_modificado_tras_el_assessment_es_stale(self):
        card = self.armar("low", hardening=hardening(floor="low"))
        self.escribir_json(REL_HARD, hardening(floor="medium").to_dict())
        a = self.evaluar(card)
        self.assertEqual(a.governance_completeness, "stale")
        self.assertEqual(estado_ev(a, "ev-hard"), "stale")

    def test_hardening_con_contenido_invalido_pineado_es_invalid(self):
        datos = {"policy_id": POLICY_ID, "base_version": 1, "inventada": 1}
        a = self.evaluar(self.ensamblar(hard_datos=datos, **self.config("low")))
        self.assertEqual(a.governance_completeness, "invalid")
        self.assertIn(govpolicy.CODE_UNKNOWN_KEY, codigos(a))

    def test_hardening_de_otra_version_de_base_es_base_mismatch_invalid(self):
        doc = govpolicy.HardeningDocument(policy_id=POLICY_ID, base_version=9, risk_floor="low")
        a = self.evaluar(self.armar("low", hardening=doc))
        self.assertEqual(a.governance_completeness, "invalid")
        self.assertIn(govpolicy.CODE_BASE_MISMATCH, codigos(a))

    def test_hardening_ref_debe_ser_governance_policy(self):
        card = self.armar("medium", hardening=hardening(floor="low"))
        body = copy.deepcopy(card.body)
        body["policy_ref"]["hardening_evidence_id"] = "ev-doc-eq"
        a = self.evaluar(dataclasses.replace(card, body=body))
        self.assertEqual(a.governance_completeness, "invalid")
        self.assertIn(modelgov.CODE_REF_INCONSISTENT, codigos(a))

    def test_claim_de_hardening_pin_debe_apoyarse_exactamente_en_el_pin(self):
        cfg = self.config("low")
        cfg["claims"]["policy_hardening_pin"] = ("ev-hard", "at-owner")
        a = self.evaluar(self.ensamblar(hardening=hardening(floor="low"), **cfg))
        self.assertEqual(a.governance_completeness, "invalid")
        self.assertIn(modelgov.CODE_CLAIM_SUPPORT_INCONSISTENT, codigos(a))

    # -- relajaciones -------------------------------------------------------

    def relajaciones(self):
        ext = govpolicy.EXTERNAL_EVIDENCE_KINDS
        return {
            "required a recommended": hardening(
                overrides=[override("fairness_evidence", medium=L("recommended", ("observed", "attestation"), ext))]),
            "amplia accepts": hardening(
                overrides=[override("accountability_owner", low=L("required", ("attestation", "observed")))]),
            "amplia accepted_kinds": hardening(
                overrides=[override("fairness_evidence", medium=L("required", ("observed", "attestation"), None))]),
            "baja min_attestation_kind": hardening(
                overrides=[override("accountability_risk_declaration", high=L("required", ("attestation",), None, "declared"))]),
            "reutiliza id base en additional": hardening(
                additional=[govpolicy.PolicyRequirement("fairness_evidence", "fairness", {"low": L("required", ("attestation",))})]),
            "override de id inexistente": hardening(
                overrides=[override("no_existe_en_base", low=L("required", ("attestation",)))]),
            "relajacion mas piso valido": hardening(
                floor="high",
                overrides=[override("fairness_evidence", medium=L("recommended", ("observed", "attestation"), ext))]),
        }

    def test_merge_rechaza_toda_relajacion(self):
        for nombre, doc in self.relajaciones().items():
            with self.subTest(caso=nombre):
                with self.assertRaises(govpolicy.GovPolicyError) as cm:
                    govpolicy.merge(govpolicy.BASE_POLICY, doc)
                self.assertEqual(cm.exception.code, govpolicy.CODE_RELAXATION)

    def test_assessment_con_hardening_que_relaja_es_invalid_con_relaxation(self):
        for nombre, doc in self.relajaciones().items():
            with self.subTest(caso=nombre):
                a = self.evaluar(self.armar("low", hardening=doc))
                self.assertEqual(a.governance_completeness, "invalid")
                self.assertIn(govpolicy.CODE_RELAXATION, codigos(a))
                self.assertIsNone(a.policy["recomputed"]["effective_sha256"])  # documento rechazado entero

    def test_hardening_que_rompe_monotonia_entre_niveles_es_not_monotonic(self):
        doc = hardening(overrides=[
            override("fairness_evidence", medium=L("required", ("observed", "attestation"), ("evidence_document",)))])
        with self.assertRaises(govpolicy.GovPolicyError) as cm:
            govpolicy.merge(govpolicy.BASE_POLICY, doc)
        self.assertEqual(cm.exception.code, govpolicy.CODE_NOT_MONOTONIC)
        a = self.evaluar(self.armar("low", hardening=doc))
        self.assertEqual(a.governance_completeness, "invalid")
        self.assertIn(govpolicy.CODE_NOT_MONOTONIC, codigos(a))

    # -- endurecimientos válidos -------------------------------------------

    def test_hardening_que_exige_anchored_en_owner(self):
        anc = L("required", ("attestation",), None, "anchored")
        doc = hardening(overrides=[override("accountability_owner", low=anc, medium=anc, high=anc)])
        efectiva = govpolicy.merge(govpolicy.BASE_POLICY, doc)
        specs = {r.requirement_id: r.levels for r in efectiva.requirements}
        self.assertEqual(specs["accountability_owner"]["low"].min_attestation_kind, "anchored")
        # nunca más débil que la base
        for r in govpolicy.BASE_POLICY.requirements:
            for nivel, spec in r.levels.items():
                self.assertTrue(govpolicy.at_least_as_strong(specs[r.requirement_id][nivel], spec))
        # owner declared (suficiente en la base) ya no alcanza
        a = self.evaluar(self.armar("low", hardening=doc))
        self.assertEqual(estado_req(a, "accountability_owner"), "untrusted_type")
        self.assertEqual(a.governance_completeness, "incomplete")
        # owner anchored sí
        cfg = self.config("low")
        cfg["attestations"][1] = hacer_att("at-owner", "Responsable del modelo: equipo de datos", "anchored")
        a = self.evaluar(self.ensamblar(hardening=doc, **cfg))
        self.assertEqual(a.governance_completeness, "complete", a.hallazgos)

    def test_hardening_que_sube_el_floor(self):
        efectiva = govpolicy.merge(govpolicy.BASE_POLICY, hardening(floor="medium"))
        self.assertEqual(efectiva.risk_floor, "medium")
        a = self.evaluar(self.armar("high", hardening=hardening(floor="medium")))
        self.assertEqual(a.risk_floor, "medium")
        self.assertEqual(a.effective_level, "high")

    def test_hardening_que_agrega_requisito(self):
        nuevo = govpolicy.PolicyRequirement(
            "robustness_evidence", "security",
            {n: L("required", ("attestation",)) for n in govpolicy.LEVELS},
        )
        doc = hardening(additional=[nuevo])
        a = self.evaluar(self.armar("low", hardening=doc))
        self.assertIn("robustness_evidence", ids_req(a))
        self.assertEqual(estado_req(a, "robustness_evidence"), "missing")
        self.assertEqual(a.governance_completeness, "incomplete")
        cfg = self.config("low")
        cfg["attestations"].append(hacer_att("at-rob", "Pruebas de robustez documentadas"))
        cfg["claims"]["robustness_evidence"] = ("at-rob",)
        a = self.evaluar(self.ensamblar(hardening=doc, **cfg))
        self.assertEqual(estado_req(a, "robustness_evidence"), "satisfied")
        self.assertEqual(a.governance_completeness, "complete", a.hallazgos)

    def test_claim_de_requisito_agregado_sin_hardening_es_invalid(self):
        cfg = self.config("low")
        cfg["attestations"].append(hacer_att("at-rob", "Pruebas de robustez documentadas"))
        cfg["claims"]["robustness_evidence"] = ("at-rob",)
        a = self.evaluar(self.ensamblar(**cfg))
        self.assertEqual(a.governance_completeness, "invalid")
        self.assertIn(modelgov.CODE_CLAIM_SUPPORT_INCONSISTENT, codigos(a))

    def test_claim_con_requirement_id_ajeno_a_la_policy_es_invalid(self):
        cfg = self.config("low")
        cfg["claims"]["inventado_x"] = ("at-owner",)
        a = self.evaluar(self.ensamblar(**cfg))
        self.assertEqual(a.governance_completeness, "invalid")
        self.assertIn(modelgov.CODE_CLAIM_SUPPORT_INCONSISTENT, codigos(a))
        # con hardening citado la pertenencia se verifica al evaluar
        a = self.evaluar(self.ensamblar(hardening=hardening(floor="low"), **cfg))
        self.assertEqual(a.governance_completeness, "invalid")
        self.assertIn(modelgov.CODE_CLAIM_SUPPORT_INCONSISTENT, codigos(a))

    def test_hardening_que_restringe_evidencia_aceptada(self):
        solo_doc = ("evidence_document",)
        doc = hardening(overrides=[override(
            "fairness_evidence",
            medium=L("required", ("observed", "attestation"), solo_doc),
            high=L("required", ("observed",), solo_doc),
        )])
        efectiva = govpolicy.merge(govpolicy.BASE_POLICY, doc)
        self.assertEqual(govpolicy.validate_monotonic(efectiva), [])
        # evidence_document sigue valiendo
        a = self.evaluar(self.armar("medium", hardening=doc))
        self.assertEqual(estado_req(a, "fairness_evidence"), "satisfied")
        # execution_record deja de valer para fairness
        cfg = self.config("medium")
        cfg["claims"]["fairness_evidence"] = ("ev-exec",)
        a = self.evaluar(self.ensamblar(hardening=doc, **cfg))
        self.assertEqual(estado_req(a, "fairness_evidence"), "untrusted_type")
        self.assertEqual(a.governance_completeness, "incomplete")
        # en la base sí valía
        a = self.evaluar(self.ensamblar(**cfg))
        self.assertEqual(estado_req(a, "fairness_evidence"), "satisfied")

    def test_efectiva_determinista_e_independiente_del_orden(self):
        anc = L("required", ("attestation",), None, "anchored")
        o1 = override("accountability_owner", low=anc, medium=anc, high=anc)
        o2 = override("privacy_evidence", high=L("required", ("observed", "attestation"),
                                                 govpolicy.EXTERNAL_EVIDENCE_KINDS, "anchored"))
        d1 = hardening(floor="medium", overrides=[o1, o2])
        d2 = hardening(floor="medium", overrides=[o2, o1])
        e1 = govpolicy.merge(govpolicy.BASE_POLICY, d1)
        e2 = govpolicy.merge(govpolicy.BASE_POLICY, d2)
        e3 = govpolicy.merge(govpolicy.BASE_POLICY, d1)
        self.assertEqual(e1.effective_sha256(), e2.effective_sha256())
        self.assertEqual(e1.effective_sha256(), e3.effective_sha256())
        self.assertEqual(e1.requirements, e2.requirements)
        # claves del JSON en otro orden
        datos = d1.to_dict()
        reordenado = {k: datos[k] for k in reversed(list(datos))}
        e4 = govpolicy.merge(govpolicy.BASE_POLICY, govpolicy.HardeningDocument.from_dict(reordenado))
        self.assertEqual(e1.effective_sha256(), e4.effective_sha256())
        self.assertNotEqual(
            e1.effective_sha256(), govpolicy.merge(govpolicy.BASE_POLICY).effective_sha256()
        )


# ---------------------------------------------------------------------------
# Evidencia, atestaciones y soportes (R39-R45, R55)
# ---------------------------------------------------------------------------


class TestEvidencia(BaseGov):
    def alta_fairness_solo_atestacion(self, kind="anchored"):
        cfg = self.config("high")
        cfg["attestations"].append(hacer_att("at-eq", "Informe de equidad revisado por el comité", kind))
        cfg["claims"]["fairness_evidence"] = ("at-eq",)
        return self.ensamblar(**cfg)

    def test_observada_valida_es_satisfied(self):
        a = self.evaluar(self.armar("medium"))
        self.assertEqual(estado_req(a, "fairness_evidence"), "satisfied")
        self.assertEqual(estado_ev(a, "ev-doc-eq"), "fresh")

    def test_observada_ausente_es_unresolvable_e_incomplete(self):
        card = self.armar("medium")
        (self.raiz / DOCS["eq"]).unlink()
        a = self.evaluar(card)
        self.assertEqual(estado_ev(a, "ev-doc-eq"), "unresolvable")
        self.assertEqual(estado_req(a, "fairness_evidence"), "unresolvable")
        self.assertEqual(a.governance_completeness, "incomplete")

    def test_documento_alterado_es_stale(self):
        card = self.armar("medium")
        (self.raiz / DOCS["eq"]).write_bytes(b"contenido alterado")
        a = self.evaluar(card)
        self.assertEqual(estado_ev(a, "ev-doc-eq"), "stale")
        self.assertEqual(estado_req(a, "fairness_evidence"), "stale")
        self.assertEqual(a.governance_completeness, "stale")

    def test_documento_reemplazado_por_directorio_es_unverifiable(self):
        card = self.armar("medium")
        ruta = self.raiz / DOCS["eq"]
        ruta.unlink()
        ruta.mkdir()
        a = self.evaluar(card)
        self.assertEqual(estado_ev(a, "ev-doc-eq"), "unverifiable")
        self.assertEqual(estado_req(a, "fairness_evidence"), "unverifiable")
        self.assertEqual(a.governance_completeness, "incomplete")

    def test_documento_con_symlink_que_escapa_es_unverifiable(self):
        with tempfile.TemporaryDirectory() as afuera:
            externo = Path(afuera) / "externo.txt"
            externo.write_bytes(b"informe fuera del proyecto")
            enlace = self.raiz / "docs" / "enlace.txt"
            try:
                os.symlink(externo, enlace)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks no disponibles en este entorno")
            cfg = self.config("medium")
            pin = core.EvidenceRef(
                "ev-doc-eq", "evidence_document", "informe-equidad", sha_bytes(externo.read_bytes()), T0,
                locator="docs/enlace.txt",
            )
            cfg["evidence"][0] = pin
            a = self.evaluar(self.ensamblar(**cfg))
            self.assertEqual(estado_ev(a, "ev-doc-eq"), "unverifiable")
            self.assertNotEqual(a.governance_completeness, "complete")

    def test_resolvers_vacios_todo_unverifiable_e_incomplete(self):
        a = self.evaluar(self.armar("medium"), resolvers={})
        self.assertEqual(a.governance_completeness, "incomplete")
        for _eid, estado in a.evidencias:
            self.assertEqual(estado, "unverifiable")
        self.assertEqual(estado_req(a, "model_card_pin"), "unverifiable")

    def test_resolver_roto_es_unverifiable(self):
        def roto(_ref):
            raise RuntimeError("boom")

        mapa = dict(resolvers.default_resolvers(self.raiz))
        mapa["evidence_document"] = roto
        a = self.evaluar(self.armar("medium"), resolvers=mapa)
        self.assertEqual(estado_ev(a, "ev-doc-eq"), "unverifiable")
        self.assertEqual(estado_req(a, "fairness_evidence"), "unverifiable")
        self.assertEqual(a.governance_completeness, "incomplete")

    def test_resolver_ausente_para_un_kind_es_unverifiable(self):
        mapa = {k: v for k, v in resolvers.default_resolvers(self.raiz).items() if k != "evidence_document"}
        a = self.evaluar(self.armar("medium"), resolvers=mapa)
        self.assertEqual(estado_ev(a, "ev-doc-eq"), "unverifiable")
        self.assertEqual(a.governance_completeness, "incomplete")

    def test_resolver_que_devuelve_basura_es_unverifiable(self):
        mapa = dict(resolvers.default_resolvers(self.raiz))
        mapa["evidence_document"] = lambda _ref: "no-es-resolution"
        a = self.evaluar(self.armar("medium"), resolvers=mapa)
        self.assertEqual(estado_ev(a, "ev-doc-eq"), "unverifiable")

    # -- high fairness (solo observada) -------------------------------------

    def test_high_fairness_con_solo_atestacion_es_untrusted_type_e_incomplete(self):
        for kind in ("anchored", "declared"):
            with self.subTest(kind=kind):
                a = self.evaluar(self.alta_fairness_solo_atestacion(kind))
                self.assertEqual(estado_req(a, "fairness_evidence"), "untrusted_type")
                self.assertEqual(a.governance_completeness, "incomplete")

    def test_high_fairness_con_documento_integro_satisface_la_presencia_documental(self):
        a = self.evaluar(self.armar("high"))
        self.assertEqual(estado_req(a, "fairness_evidence"), "satisfied")
        self.assertEqual(a.governance_completeness, "complete")

    def test_high_fairness_con_documento_modificado_es_stale(self):
        card = self.armar("high")
        (self.raiz / DOCS["eq"]).write_bytes(b"modificado")
        a = self.evaluar(card)
        self.assertEqual(estado_req(a, "fairness_evidence"), "stale")
        self.assertEqual(a.governance_completeness, "stale")

    def test_high_fairness_con_documento_corrupto_es_unverifiable(self):
        card = self.armar("high")
        ruta = self.raiz / DOCS["eq"]
        ruta.unlink()
        ruta.mkdir()
        a = self.evaluar(card)
        self.assertEqual(estado_req(a, "fairness_evidence"), "unverifiable")
        self.assertEqual(a.governance_completeness, "incomplete")

    def test_evidence_document_no_genera_conclusion_semantica(self):
        a = self.evaluar(self.armar("high"))
        d = a.a_dict()
        self.assertEqual(d["nota"], modelgov.NOTA_COMPLETENESS)
        self.assertIn("NO equivale a aprobación", d["nota"])
        texto = json.dumps(d, ensure_ascii=False).replace(modelgov.NOTA_COMPLETENESS, "").lower()
        texto = texto.replace("fairness", "")  # nombre del requisito/dimensión de la policy
        for palabra in ("fair", "justo", "aprobado", "approved", "passed", "secure", "ethical", "safe"):
            self.assertNotIn(palabra, texto)
        self.assertEqual(
            set(d),
            {"card_id", "governance_completeness", "effective_level", "declared_level", "risk_floor", "policy",
             "dimensiones", "requisitos", "evidencias", "hallazgos", "nota"},
        )

    # -- otros requisitos ----------------------------------------------------

    def test_medium_fairness_con_atestacion_declared_satisface(self):
        cfg = self.config("medium")
        cfg["attestations"].append(hacer_att("at-eq", "Informe de equidad revisado internamente"))
        cfg["claims"]["fairness_evidence"] = ("at-eq",)
        a = self.evaluar(self.ensamblar(**cfg))
        self.assertEqual(estado_req(a, "fairness_evidence"), "satisfied")
        self.assertEqual(a.governance_completeness, "complete")

    def test_explainability_con_documento_externo(self):
        cfg = self.config("medium")
        cfg["evidence"].append(self.pin_doc("ev-doc-ex", "informe-explicabilidad", "ex"))
        cfg["claims"]["explainability_evidence"] = ("ev-doc-ex",)
        a = self.evaluar(self.ensamblar(**cfg))
        self.assertEqual(estado_req(a, "explainability_evidence"), "satisfied")
        self.assertEqual(estado_ev(a, "ev-doc-ex"), "fresh")
        # en high es required y con documento íntegro alcanza
        self.assertEqual(estado_req(self.evaluar(self.armar("high")), "explainability_evidence"), "satisfied")

    def test_privacy_con_atestacion(self):
        a = self.evaluar(self.armar("medium"))
        self.assertEqual(estado_req(a, "privacy_evidence"), "satisfied")
        self.assertEqual(estado_dim(a, "privacy"), "complete")

    def test_security_con_metrica_observada_y_execution_record(self):
        a = self.evaluar(self.armar("high"))
        self.assertEqual(estado_req(a, "security_evidence"), "satisfied")
        self.assertEqual(estado_ev(a, "ev-met"), "fresh")
        a = self.evaluar(self.armar("medium"))
        self.assertEqual(estado_req(a, "security_evidence"), "satisfied")
        self.assertEqual(estado_ev(a, "ev-exec"), "fresh")

    def test_metrica_modificada_es_stale(self):
        card = self.armar("high")
        self.escribir_metricas(0.5)
        a = self.evaluar(card)
        self.assertEqual(estado_req(a, "security_evidence"), "stale")
        self.assertEqual(a.governance_completeness, "stale")

    # -- human oversight -----------------------------------------------------

    def test_human_oversight_con_atestacion_anchored_satisface_y_no_toca_nada(self):
        card = self.armar("high")
        antes = snapshot(self.raiz)
        a = self.evaluar(card)
        self.assertEqual(estado_req(a, "human_oversight_process"), "satisfied")
        self.assertEqual(a.governance_completeness, "complete")
        self.assertEqual(snapshot(self.raiz), antes)
        nombres = {p.name for p in self.raiz.rglob("*")}
        self.assertNotIn("control.json", nombres)
        self.assertNotIn("guardrails.json", nombres)

    def test_human_oversight_con_execution_record(self):
        cfg = self.config("high")
        cfg["evidence"].append(self.pin_exec())
        cfg["claims"]["human_oversight_process"] = ("ev-exec",)
        a = self.evaluar(self.ensamblar(**cfg))
        self.assertEqual(estado_req(a, "human_oversight_process"), "satisfied")

    def test_human_oversight_declared_en_high_es_untrusted_type(self):
        cfg = self.config("high")
        self.sin_att(cfg, "at-ovr")
        cfg["attestations"].append(hacer_att("at-ovr", "Proceso de supervisión humana definido"))
        a = self.evaluar(self.ensamblar(**cfg))
        self.assertEqual(estado_req(a, "human_oversight_process"), "untrusted_type")
        self.assertEqual(a.governance_completeness, "incomplete")

    def test_human_oversight_declared_en_medium_satisface(self):
        cfg = self.config("medium")
        cfg["attestations"].append(hacer_att("at-ovr", "Proceso de supervisión humana definido"))
        cfg["claims"]["human_oversight_process"] = ("at-ovr",)
        a = self.evaluar(self.ensamblar(**cfg))
        self.assertEqual(estado_req(a, "human_oversight_process"), "satisfied")

    def test_atestacion_anchored_con_approval_ref_mal_formado_no_se_construye(self):
        with self.assertRaises(core.CardError):
            hacer_att("at-ovr", "supervisión", "anchored", approval_ref={"change_id": "x"})


class TestSoportes(BaseGov):
    def medium_privacy(self, soportes, extra_evidence=()):
        cfg = self.config("medium")
        cfg["evidence"] += [self.pin_doc("ev-doc-pr", "informe-priv", "pr"),
                            self.pin_doc("ev-doc-pr2", "informe-priv2", "pr2")] + list(extra_evidence)
        cfg["claims"]["privacy_evidence"] = tuple(soportes)
        return self.ensamblar(**cfg)

    def test_dos_soportes_frescos_satisfacen(self):
        for orden in itertools.permutations(("ev-doc-pr", "ev-doc-pr2")):
            with self.subTest(orden=orden):
                a = self.evaluar(self.medium_privacy(orden))
                self.assertEqual(estado_req(a, "privacy_evidence"), "satisfied")

    def test_uno_fresco_y_uno_stale_no_satisface_en_ambos_ordenes(self):
        for orden in itertools.permutations(("ev-doc-pr", "ev-doc-pr2")):
            with self.subTest(orden=orden):
                card = self.medium_privacy(orden)
                (self.raiz / DOCS["pr2"]).write_bytes(b"cambiado")
                a = self.evaluar(card)
                self.assertEqual(estado_req(a, "privacy_evidence"), "stale")
                self.assertEqual(a.governance_completeness, "stale")
                self.assertNotEqual(estado_req(a, "privacy_evidence"), "satisfied")
                self.escribir_bytes(DOCS["pr2"], b"informe externo pr2\n")  # restaurar para la iteración siguiente

    def test_documento_stale_mezclado_con_atestacion_fresca(self):
        for orden in itertools.permutations(("ev-doc-pr", "at-priv")):
            with self.subTest(orden=orden):
                card = self.medium_privacy(orden)
                (self.raiz / DOCS["pr"]).write_bytes(b"cambiado")
                a = self.evaluar(card)
                self.assertEqual(estado_req(a, "privacy_evidence"), "stale")
                self.escribir_bytes(DOCS["pr"], b"informe externo pr\n")

    def test_uno_fresco_y_uno_ausente_es_unresolvable(self):
        for orden in itertools.permutations(("ev-doc-pr", "ev-doc-pr2")):
            with self.subTest(orden=orden):
                card = self.medium_privacy(orden)
                (self.raiz / DOCS["pr2"]).unlink()
                a = self.evaluar(card)
                self.assertEqual(estado_req(a, "privacy_evidence"), "unresolvable")
                self.assertEqual(a.governance_completeness, "incomplete")
                self.escribir_bytes(DOCS["pr2"], b"informe externo pr2\n")

    def test_stale_tiene_precedencia_sobre_unresolvable(self):
        card = self.medium_privacy(("ev-doc-pr", "ev-doc-pr2"))
        (self.raiz / DOCS["pr"]).write_bytes(b"cambiado")
        (self.raiz / DOCS["pr2"]).unlink()
        self.assertEqual(estado_req(self.evaluar(card), "privacy_evidence"), "stale")

    def test_soporte_inaceptable_mezclado_con_aceptable_es_untrusted_type(self):
        for orden in itertools.permutations(("ev-doc-pr", "ev-mc")):
            with self.subTest(orden=orden):
                a = self.evaluar(self.medium_privacy(orden))
                self.assertEqual(estado_req(a, "privacy_evidence"), "untrusted_type")
                self.assertEqual(a.governance_completeness, "incomplete")

    def test_atestacion_insuficiente_mezclada_con_documento_en_high_es_untrusted_type(self):
        cfg = self.config("high")
        cfg["attestations"].append(hacer_att("at-eq", "Informe de equidad revisado", "anchored"))
        cfg["claims"]["fairness_evidence"] = ("ev-doc-eq", "at-eq")
        a = self.evaluar(self.ensamblar(**cfg))
        self.assertEqual(estado_req(a, "fairness_evidence"), "untrusted_type")

    def test_evidencia_en_la_declaracion_de_riesgo_mezclada_con_atestacion_es_untrusted_type(self):
        cfg = self.config("medium")
        cfg["claims"]["accountability_risk_declaration"] = ("at-risk", "ev-doc-eq")
        a = self.evaluar(self.ensamblar(**cfg))
        self.assertEqual(estado_req(a, "accountability_risk_declaration"), "untrusted_type")

    def test_contaminacion_cruzada_entre_requisitos_no_satisface(self):
        # fairness apoyada en la Model Card (kind inaceptable) que sostiene otro requisito
        cfg = self.config("medium")
        cfg["claims"]["fairness_evidence"] = ("ev-mc",)
        a = self.evaluar(self.ensamblar(**cfg))
        self.assertEqual(estado_req(a, "model_card_pin"), "satisfied")
        self.assertEqual(estado_req(a, "fairness_evidence"), "untrusted_type")
        self.assertEqual(a.governance_completeness, "incomplete")
        # lo mismo con el pin de hardening como soporte de privacy
        cfg = self.config("medium")
        cfg["claims"]["privacy_evidence"] = ("ev-hard",)
        a = self.evaluar(self.ensamblar(hardening=hardening(floor="low"), **cfg))
        self.assertEqual(estado_req(a, "policy_hardening_pin"), "satisfied")
        self.assertEqual(estado_req(a, "privacy_evidence"), "untrusted_type")

    def test_model_card_pin_exige_soporte_exacto(self):
        for soportes in (("ev-mc", "ev-doc-eq"), ("ev-doc-eq",), ("at-owner",)):
            with self.subTest(soportes=soportes):
                cfg = self.config("medium")
                cfg["claims"]["model_card_pin"] = soportes
                a = self.evaluar(self.ensamblar(**cfg))
                self.assertEqual(a.governance_completeness, "invalid")
                self.assertIn(modelgov.CODE_CLAIM_SUPPORT_INCONSISTENT, codigos(a))

    def test_claim_sin_soportes_es_empty_y_sin_claim_es_missing(self):
        cfg = self.config("low")
        cfg["claims"]["accountability_owner"] = ()
        a = self.evaluar(self.ensamblar(**cfg))
        self.assertEqual(estado_req(a, "accountability_owner"), "empty")
        self.assertEqual(a.governance_completeness, "incomplete")


    def test_soporte_dangling_evaluado_es_invalid(self):
        cfg = self.config("low")
        cfg["claims"]["accountability_owner"] = ("at-no-existe",)
        # Ni Claim ni CardEnvelope verifican la existencia del soporte: el constructor NO debe
        # rechazarlo (si lo hiciera, este assert falla en vez de saltearse la verificación).
        card = self.ensamblar(**cfg)
        a = self.evaluar(card)
        self.assertEqual(a.governance_completeness, "invalid")
        self.assertIn(core.CODE_DANGLING_SUPPORT, codigos(a))


# ---------------------------------------------------------------------------
# No aplicabilidad (R36)
# ---------------------------------------------------------------------------


class TestNoAplicable(BaseGov):
    def medium_con_na(self, dimensions, quitar_claims=(), con_att=True):
        cfg = self.config("medium")
        if con_att:
            cfg["attestations"].append(hacer_att("at-na", "El requisito no aplica a este modelo"))
        for rid in quitar_claims:
            cfg["claims"].pop(rid, None)
        return self.ensamblar(dimensions=dimensions, **cfg)

    def test_recomendado_con_rationale_y_atestacion_es_na_valido_y_completo(self):
        card = self.medium_con_na(dim_na("explainability", "explainability_evidence"))
        a = self.evaluar(card)
        self.assertEqual(a.governance_completeness, "complete", a.hallazgos)
        self.assertEqual(estado_req(a, "explainability_evidence"), "not_applicable")
        self.assertEqual(estado_dim(a, "explainability"), "not_required")

    def test_na_no_genera_warn_en_check_results(self):
        a = self.evaluar(self.medium_con_na(dim_na("explainability", "explainability_evidence")))
        msgs = " ".join(r.message for r in modelgov.a_check_results(a))
        self.assertNotIn("explainability_evidence", msgs)

    def test_requisito_required_na_es_invalid(self):
        card = self.medium_con_na(dim_na("fairness", "fairness_evidence"), quitar_claims=("fairness_evidence",))
        a = self.evaluar(card)
        self.assertEqual(a.governance_completeness, "invalid")
        self.assertIn(modelgov.CODE_NA_NOT_ALLOWED, codigos(a))

    def test_na_de_requisito_required_con_su_claim_tambien_es_invalid(self):
        a = self.evaluar(self.medium_con_na(dim_na("fairness", "fairness_evidence")))
        self.assertEqual(a.governance_completeness, "invalid")
        self.assertIn(modelgov.CODE_CLAIM_SUPPORT_INCONSISTENT, codigos(a))

    def test_dimension_entera_na_con_required_adentro_es_invalid(self):
        dims = {"accountability": {"not_applicable": [
            {"requirement_id": "accountability_risk_declaration", "rationale": "No aplica", "attestation_id": "at-na"},
            {"requirement_id": "accountability_owner", "rationale": "No aplica", "attestation_id": "at-na"},
        ]}}
        cfg = self.config("low")
        cfg["attestations"].append(hacer_att("at-na", "El requisito no aplica a este modelo"))
        del cfg["claims"]["accountability_risk_declaration"]
        del cfg["claims"]["accountability_owner"]
        a = self.evaluar(self.ensamblar(dimensions=dims, **cfg))
        self.assertEqual(a.governance_completeness, "invalid")
        self.assertIn(modelgov.CODE_NA_NOT_ALLOWED, codigos(a))

    def test_na_a_nivel_de_dimension_no_existe(self):
        for valor in (True, "all", {"all": True}):
            with self.subTest(valor=valor):
                card = self.medium_con_na({"fairness": {"not_applicable": valor}})
                a = self.evaluar(card)
                self.assertEqual(a.governance_completeness, "invalid")
        card = self.medium_con_na({"fairness": {"na": True}})
        self.assertIn(modelgov.CODE_UNKNOWN_KEY, codigos(self.evaluar(card)))

    def test_pin_estructural_no_admite_na(self):
        card = self.medium_con_na(dim_na("accountability", "model_card_pin"))
        a = self.evaluar(card)
        self.assertEqual(a.governance_completeness, "invalid")
        self.assertIn(modelgov.CODE_NA_NOT_ALLOWED, codigos(a))

    def test_na_sin_atestacion_o_sin_rationale_es_invalid(self):
        sin_att = {"explainability": {"not_applicable": [
            {"requirement_id": "explainability_evidence", "rationale": "No aplica"}]}}
        sin_rat = {"explainability": {"not_applicable": [
            {"requirement_id": "explainability_evidence", "attestation_id": "at-na"}]}}
        rat_vacio = dim_na("explainability", "explainability_evidence", rationale="   ")
        att_inexistente = dim_na("explainability", "explainability_evidence", att="at-no-existe")
        att_es_evidencia = dim_na("explainability", "explainability_evidence", att="ev-doc-eq")
        for nombre, dims in {"sin atestacion": sin_att, "sin rationale": sin_rat, "rationale vacio": rat_vacio,
                             "atestacion inexistente": att_inexistente, "atestacion es evidencia": att_es_evidencia}.items():
            with self.subTest(caso=nombre):
                a = self.evaluar(self.medium_con_na(dims))
                self.assertEqual(a.governance_completeness, "invalid")

    def test_na_de_requisito_que_no_aplica_en_el_nivel_es_inconsistente(self):
        cfg = self.config("low")
        cfg["attestations"].append(hacer_att("at-na", "El requisito no aplica a este modelo"))
        a = self.evaluar(self.ensamblar(dimensions=dim_na("human_oversight", "human_oversight_process"), **cfg))
        self.assertEqual(a.governance_completeness, "invalid")
        self.assertIn(modelgov.CODE_REF_INCONSISTENT, codigos(a))

    def test_na_con_dimension_equivocada_o_requisito_inexistente(self):
        for dims in (dim_na("privacy", "explainability_evidence"), dim_na("privacy", "no_existe")):
            with self.subTest(dims=dims):
                a = self.evaluar(self.medium_con_na(dims))
                self.assertEqual(a.governance_completeness, "invalid")
                self.assertIn(modelgov.CODE_REF_INCONSISTENT, codigos(a))

    def test_requisito_na_que_ademas_tiene_claim_es_inconsistente(self):
        cfg = self.config("medium")
        cfg["attestations"].append(hacer_att("at-na", "El requisito no aplica a este modelo"))
        cfg["attestations"].append(hacer_att("at-expl", "Explicabilidad documentada internamente"))
        cfg["claims"]["explainability_evidence"] = ("at-expl",)
        a = self.evaluar(self.ensamblar(dimensions=dim_na("explainability", "explainability_evidence"), **cfg))
        self.assertEqual(a.governance_completeness, "invalid")
        self.assertIn(modelgov.CODE_CLAIM_SUPPORT_INCONSISTENT, codigos(a))

    def test_na_duplicado_es_inconsistente(self):
        item = {"requirement_id": "explainability_evidence", "rationale": "No aplica", "attestation_id": "at-na"}
        dims = {"explainability": {"not_applicable": [item, dict(item)]}}
        a = self.evaluar(self.medium_con_na(dims))
        self.assertEqual(a.governance_completeness, "invalid")
        self.assertIn(modelgov.CODE_REF_INCONSISTENT, codigos(a))

    def test_na_no_lista_o_elemento_no_objeto(self):
        for dims in ({"explainability": {"not_applicable": "x"}}, {"explainability": {"not_applicable": ["x"]}}):
            with self.subTest(dims=dims):
                a = self.evaluar(self.medium_con_na(dims))
                self.assertEqual(a.governance_completeness, "invalid")
                self.assertIn(modelgov.CODE_BODY_INVALID, codigos(a))

    def test_na_en_low_de_recomendado_es_valido(self):
        cfg = self.config("low")
        cfg["attestations"].append(hacer_att("at-na", "El requisito no aplica a este modelo"))
        a = self.evaluar(self.ensamblar(dimensions=dim_na("privacy", "privacy_evidence"), **cfg))
        self.assertEqual(a.governance_completeness, "complete", a.hallazgos)
        self.assertEqual(estado_req(a, "privacy_evidence"), "not_applicable")

    def test_dimensiones_descriptivas_no_son_evidencia(self):
        dims = {"fairness": {"context": "Contexto descriptivo del uso", "limitations": ["Solo datos históricos"]}}
        cfg = self.config("medium")
        del cfg["claims"]["fairness_evidence"]
        a = self.evaluar(self.ensamblar(dimensions=dims, **cfg))
        self.assertEqual(estado_req(a, "fairness_evidence"), "missing")
        self.assertEqual(a.governance_completeness, "incomplete")


# ---------------------------------------------------------------------------
# Estado derivado, precedencia y dimensiones (R38, R47-R49)
# ---------------------------------------------------------------------------


class TestEstadoDerivado(BaseGov):
    def test_archivo_serializado_no_contiene_estado_ni_juicios(self):
        card = self.armar("high")
        ruta = modelgov.write_governance_assessment(self.raiz, card, clock=lambda: NOW)
        texto = ruta.read_text(encoding="utf-8")
        claves = set(claves_recursivas(json.loads(texto)))
        for prohibida in CLAVES_PROHIBIDAS:
            self.assertNotIn(prohibida, claves)
        self.assertNotIn("governance_completeness", texto)
        self.assertNotIn('"complete"', texto)

    def test_from_dict_rechaza_estado(self):
        datos = self.armar("low").to_dict()
        for clave in ("status", "governance_completeness"):
            with self.subTest(clave=clave):
                malo = dict(datos)
                malo[clave] = "complete"
                with self.assertRaises(core.CardError) as cm:
                    core.CardEnvelope.from_dict(malo)
                self.assertEqual(cm.exception.code, core.CODE_UNKNOWN_KEY)

    def test_body_rechaza_claves_de_estado_y_juicio(self):
        for clave in CLAVES_PROHIBIDAS + ("risk_level", "fair_score", "approved"):
            with self.subTest(clave=clave):
                card = self.armar("low")
                body = dict(card.body)
                body[clave] = "complete"
                card = dataclasses.replace(card, body=body)
                self.assertIn(modelgov.CODE_UNKNOWN_KEY, {h.code for h in modelgov.validate_governance_assessment(card)})
                a = self.evaluar(card)
                self.assertEqual(a.governance_completeness, "invalid")
                self.assertIn(modelgov.CODE_UNKNOWN_KEY, codigos(a))

    def test_claves_desconocidas_en_subobjetos(self):
        casos = {
            "model_card_ref": lambda b: b["model_card_ref"].update(extra=1),
            "policy_ref": lambda b: b["policy_ref"].update(extra=1),
            "risk_declaration": lambda b: b["risk_declaration"].update(score=1),
            "dimensions": lambda b: b.update(dimensions={"equity": {}}),
            "dimension": lambda b: b.update(dimensions={"fairness": {"status": "ok"}}),
        }
        for nombre, mutar in casos.items():
            with self.subTest(caso=nombre):
                card = self.armar("low")
                body = copy.deepcopy(card.body)
                mutar(body)
                a = self.evaluar(dataclasses.replace(card, body=body))
                self.assertEqual(a.governance_completeness, "invalid")
                self.assertIn(modelgov.CODE_UNKNOWN_KEY, codigos(a))

    def test_x_prefijo_permitido_sin_efecto_de_governance(self):
        base = self.armar("medium")
        con_x = dataclasses.replace(base, body={**base.body, "x_nota": "texto libre", "x_obj": {"a": ["b", 1]}})
        a0, a1 = self.evaluar(base), self.evaluar(con_x)
        self.assertEqual(a1.governance_completeness, "complete")
        self.assertEqual(a0.a_dict(), a1.a_dict())
        self.assertEqual(modelgov.validate_governance_assessment(con_x), [])

    def test_x_prefijo_con_ruta_o_dsn_es_invalid(self):
        malos = ("/etc/passwd", "C:\\datos\\x", "postgres://u:p@h/db", "user:pw@host", "password=abc", "~/x", "../x")
        for valor in malos:
            for forma in (valor, {"k": [valor]}):
                with self.subTest(valor=valor, forma=type(forma).__name__):
                    base = self.armar("low")
                    card = dataclasses.replace(base, body={**base.body, "x_dato": forma})
                    a = self.evaluar(card)
                    self.assertEqual(a.governance_completeness, "invalid")
                    self.assertIn(core.CODE_LOCATOR_NOT_PORTABLE, codigos(a))

    def test_textos_libres_rechazan_rutas_y_dsn(self):
        for valor in ("/etc/passwd", "C:\\x", "postgres://u:p@h/db", "token=abc"):
            with self.subTest(valor=valor):
                base = self.armar("low")
                casos = {
                    "notes": {**base.body, "notes": valor},
                    "context": {**base.body, "dimensions": {"privacy": {"context": valor}}},
                    "limitations": {**base.body, "dimensions": {"privacy": {"limitations": [valor]}}},
                }
                for nombre, body in casos.items():
                    a = self.evaluar(dataclasses.replace(base, body=body))
                    self.assertEqual(a.governance_completeness, "invalid", nombre)
                    self.assertIn(core.CODE_LOCATOR_NOT_PORTABLE, codigos(a), nombre)
        # rationale
        a = self.evaluar(self.medium_na_con_rationale("/etc/passwd"))
        self.assertEqual(a.governance_completeness, "invalid")
        self.assertIn(core.CODE_LOCATOR_NOT_PORTABLE, codigos(a))

    def medium_na_con_rationale(self, rationale):
        cfg = self.config("medium")
        cfg["attestations"].append(hacer_att("at-na", "El requisito no aplica a este modelo"))
        return self.ensamblar(dimensions=dim_na("explainability", "explainability_evidence", rationale=rationale), **cfg)

    def test_textos_libres_validos_se_aceptan(self):
        base = self.armar("low")
        body = {**base.body, "notes": "Notas de revisión.\nSegunda línea.",
                "dimensions": {"privacy": {"context": "Contexto del uso", "limitations": ["Una", "Dos"]}}}
        a = self.evaluar(dataclasses.replace(base, body=body))
        self.assertEqual(a.governance_completeness, "complete", a.hallazgos)

    def test_policy_ref_malformado(self):
        casos = {
            "sha corto": {"base_sha256": "abc"},
            "sha mayusculas": {"effective_sha256": "A" * 64},
            "version bool": {"base_version": True},
            "version cero": {"base_version": 0},
            "version str": {"base_version": "1"},
        }
        for nombre, cambios in casos.items():
            with self.subTest(caso=nombre):
                a = self.evaluar(self.armar("low", policy_cambios=cambios))
                self.assertEqual(a.governance_completeness, "invalid")
                self.assertIn(modelgov.CODE_BODY_INVALID, codigos(a))

    def test_policy_ref_obligatorio_y_sus_campos(self):
        card = self.armar("low")
        body = copy.deepcopy(card.body)
        del body["policy_ref"]
        self.assertEqual(self.evaluar(dataclasses.replace(card, body=body)).governance_completeness, "invalid")
        body = copy.deepcopy(card.body)
        del body["policy_ref"]["effective_sha256"]
        a = self.evaluar(dataclasses.replace(card, body=body))
        self.assertEqual(a.governance_completeness, "invalid")
        self.assertIn(modelgov.CODE_BODY_INVALID, codigos(a))

    def test_kind_y_schema_ajenos(self):
        card = self.armar("low")
        a = self.evaluar(dataclasses.replace(card, kind_schema_version=2))
        self.assertEqual(a.governance_completeness, "invalid")
        self.assertIn(modelgov.CODE_SCHEMA_UNSUPPORTED, codigos(a))
        a = self.evaluar(dataclasses.replace(card, card_kind="model_card"))
        self.assertEqual(a.governance_completeness, "invalid")
        self.assertIn(modelgov.CODE_KIND_INVALID, codigos(a))
        a = self.evaluar(dataclasses.replace(card, schema_version=2))
        self.assertEqual(a.governance_completeness, "invalid")

    def test_validadores_no_lanzan_con_entradas_ajenas(self):
        for valor in (None, 5, "x", {}, [], object()):
            with self.subTest(valor=valor):
                hallazgos = modelgov.validate_governance_assessment(valor)
                self.assertTrue(hallazgos)
                validar = modelgov.body_validator_for(valor)
                self.assertTrue(validar({}))
        validar = modelgov.body_validator_for(self.armar("low"))
        self.assertEqual(validar(self.armar("low").body), [])
        self.assertTrue(validar("no-es-dict"))
        self.assertTrue(validar(None))

    def test_validate_governance_assessment_card_valida_vacia(self):
        self.assertEqual(modelgov.validate_governance_assessment(self.armar("high")), [])

    # -- precedencia ---------------------------------------------------------

    def variante(self, incompleto=False, stale=False, invalido=False):
        cfg = self.config("medium")
        if incompleto:
            del cfg["claims"]["accountability_owner"]
        card = self.ensamblar(body_extra={"fair": True} if invalido else None, **cfg)
        if stale:
            (self.raiz / DOCS["eq"]).write_bytes(b"alterado")
        return card

    def test_precedencia_invalid_stale_incomplete_complete(self):
        esperado = {
            (False, False, False): "complete",
            (True, False, False): "incomplete",
            (False, True, False): "stale",
            (False, False, True): "invalid",
            (True, True, False): "stale",
            (True, False, True): "invalid",
            (False, True, True): "invalid",
            (True, True, True): "invalid",
        }
        for (inc, stl, inv), final in esperado.items():
            with self.subTest(incompleto=inc, stale=stl, invalido=inv):
                self.escribir_bytes(DOCS["eq"], b"informe externo eq\n")
                a = self.evaluar(self.variante(inc, stl, inv))
                self.assertEqual(a.governance_completeness, final)

    # -- dimensiones -----------------------------------------------------------

    def test_estado_por_dimension_y_not_required(self):
        esperado = {
            "low": {"fairness": "not_required", "explainability": "not_required", "privacy": "not_required",
                    "security": "not_required", "accountability": "complete", "human_oversight": "not_required"},
            "medium": {"fairness": "complete", "explainability": "not_required", "privacy": "complete",
                       "security": "complete", "accountability": "complete", "human_oversight": "not_required"},
            "high": {d: "complete" for d in govpolicy.DIMENSIONS},
        }
        for nivel, dims in esperado.items():
            with self.subTest(nivel=nivel):
                a = self.evaluar(self.armar(nivel))
                self.assertEqual({d[0]: d[1] for d in a.dimensiones}, dims)
                self.assertEqual([d[0] for d in a.dimensiones], list(govpolicy.DIMENSIONS))

    def test_dimension_lista_sus_requisitos_required(self):
        a = self.evaluar(self.armar("high"))
        por_dim = {d[0]: d[2] for d in a.dimensiones}
        self.assertEqual(por_dim["accountability"], ("accountability_owner", "accountability_risk_declaration"))
        self.assertEqual(por_dim["fairness"], ("fairness_evidence",))

    def test_dimension_stale_e_incomplete(self):
        card = self.armar("medium")
        (self.raiz / DOCS["eq"]).write_bytes(b"alterado")
        a = self.evaluar(card)
        self.assertEqual(estado_dim(a, "fairness"), "stale")
        self.assertEqual(estado_dim(a, "accountability"), "complete")
        self.escribir_bytes(DOCS["eq"], b"informe externo eq\n")  # restaurar antes de re-pinear
        cfg = self.config("medium")
        del cfg["claims"]["privacy_evidence"]
        a = self.evaluar(self.ensamblar(**cfg))
        self.assertEqual(estado_dim(a, "privacy"), "incomplete")
        self.assertEqual(a.governance_completeness, "incomplete")

    def test_dimension_not_required_no_es_pass(self):
        a = self.evaluar(self.armar("low"))
        self.assertEqual(estado_dim(a, "fairness"), "not_required")
        self.assertNotIn(estado_dim(a, "fairness"), ("complete", "satisfied", "passed"))


# ---------------------------------------------------------------------------
# Sin inferencia ética, mensajes y serialización (R20, R47, R52, R55, R62)
# ---------------------------------------------------------------------------


class TestSinInferenciaYMensajes(BaseGov):
    def test_valores_de_metricas_muy_distintos_dan_el_mismo_a_dict(self):
        resultados = []
        for valor in (0.99, 0.01, 0.0):
            self.escribir_metricas(valor)
            resultados.append(self.evaluar(self.armar("high")).a_dict())
        self.assertEqual(resultados[0], resultados[1])
        self.assertEqual(resultados[0], resultados[2])
        self.assertEqual(resultados[0]["governance_completeness"], "complete")

    def test_ningun_campo_good_bad_y_a_dict_serializable(self):
        d = self.evaluar(self.armar("high")).a_dict()
        json.dumps(d)
        claves = set(claves_recursivas(d))
        # `governance_completeness` es el único campo de estado y es DERIVADO (solo en la salida, no en el archivo)
        for prohibida in tuple(c for c in CLAVES_PROHIBIDAS if c != "governance_completeness") + (
                "good", "bad", "ok", "verdict", "result"):
            self.assertNotIn(prohibida, claves)
        self.assertIn(d["governance_completeness"], ("invalid", "stale", "incomplete", "complete"))

    def test_a_dict_determinista(self):
        card = self.armar("medium")
        d1 = json.dumps(self.evaluar(card).a_dict(), sort_keys=False)
        d2 = json.dumps(self.evaluar(card).a_dict(), sort_keys=False)
        self.assertEqual(d1, d2)
        a = self.evaluar(card)
        self.assertEqual([r[0] for r in a.requisitos], sorted(r[0] for r in a.requisitos))
        self.assertEqual([e[0] for e in a.evidencias], sorted(e[0] for e in a.evidencias))

    def checks(self):
        return assess._checks_module()

    def textos(self, resultados):
        return [r.message for r in resultados]

    def test_complete_da_pass_con_la_nota(self):
        checks = self.checks()
        res = modelgov.a_check_results(self.evaluar(self.armar("low")))
        pasa = [r for r in res if r.status == checks.STATUS_PASS]
        self.assertEqual(len(pasa), 1)
        self.assertEqual(pasa[0].code, modelgov.CODE_COMPLETE)
        self.assertFalse([r for r in res if r.status == checks.STATUS_FAIL])
        for r in res:
            self.assertIn(modelgov.NOTA_COMPLETENESS, r.message)
            self.assertEqual(r.subject, "clasificador__1_0_0")

    def test_required_insatisfecho_es_fail_y_recomendado_warn(self):
        checks = self.checks()
        cfg = self.config("medium")
        del cfg["claims"]["accountability_owner"]
        res = modelgov.a_check_results(self.evaluar(self.ensamblar(**cfg)))
        fails = [r for r in res if r.status == checks.STATUS_FAIL]
        self.assertEqual(len(fails), 1)
        self.assertEqual(fails[0].code, core.CODE_REQUIREMENT_MISSING)
        self.assertIn("accountability_owner", fails[0].message)
        warns = " ".join(r.message for r in res if r.status == checks.STATUS_WARN)
        self.assertIn("explainability_evidence", warns)
        self.assertFalse([r for r in res if r.status == checks.STATUS_PASS])

    def test_codigos_de_requisito_por_estado(self):
        checks = self.checks()
        cfg = self.config("high")
        cfg["attestations"].append(hacer_att("at-eq", "Informe revisado", "anchored"))
        cfg["claims"]["fairness_evidence"] = ("at-eq",)
        res = modelgov.a_check_results(self.evaluar(self.ensamblar(**cfg)))
        self.assertEqual(
            [r.code for r in res if r.status == checks.STATUS_FAIL], [core.CODE_REQUIREMENT_UNTRUSTED_TYPE]
        )
        card = self.armar("medium")
        (self.raiz / DOCS["eq"]).write_bytes(b"alterado")
        res = modelgov.a_check_results(self.evaluar(card))
        codes = {r.code for r in res}
        self.assertIn(core.CODE_REQUIREMENT_STALE, codes)
        self.assertIn(core.CODE_EVIDENCE_STALE, codes)

    def test_invalid_da_un_fail_por_hallazgo(self):
        checks = self.checks()
        a = self.evaluar(dataclasses.replace(self.armar("low"), subject="otro"))
        res = modelgov.a_check_results(a)
        self.assertEqual(len(res), len(a.hallazgos))
        for r in res:
            self.assertEqual(r.status, checks.STATUS_FAIL)
            self.assertIn(modelgov.NOTA_COMPLETENESS, r.message)
        self.assertIn(modelgov.CODE_IDENTITY_MISMATCH, {r.code for r in res})

    def test_hallazgo_de_policy_es_warn(self):
        checks = self.checks()
        res = modelgov.a_check_results(self.evaluar(self.armar("low", policy_cambios={"base_version": 2})))
        self.assertIn(modelgov.CODE_POLICY_CHANGED, {r.code for r in res if r.status == checks.STATUS_WARN})

    def test_incomplete_sin_otros_resultados_no_queda_vacio(self):
        res = modelgov.a_check_results(modelgov.GovernanceAssessment(governance_completeness="incomplete"))
        self.assertEqual(len(res), 1)
        self.assertIn(modelgov.NOTA_COMPLETENESS, res[0].message)

    def test_mensajes_sin_autonomia_ni_marcos_normativos_ni_verificacion(self):
        asses = [
            self.evaluar(self.armar("low")),
            self.evaluar(self.armar("high")),
            self.evaluar(dataclasses.replace(self.armar("low"), subject="otro")),
            self.evaluar(self.armar("low", policy_cambios={"base_version": 2})),
        ]
        cfg = self.config("medium")
        del cfg["claims"]["accountability_owner"]
        asses.append(self.evaluar(self.ensamblar(**cfg)))
        prohibidos = ("autonom", "STOP", "approval_mode", "checkpoint", "EU AI Act", "NIST", "ISO", "GDPR",
                      "RGPD", "HIPAA", "verified", "verificad")
        for a in asses:
            for r in modelgov.a_check_results(a):
                texto = r.message + " " + (r.detail or "")
                for palabra in prohibidos:
                    self.assertNotIn(palabra, texto, f"{r.code}: {texto}")

    def test_a_check_results_exige_assessment(self):
        with self.assertRaises(core.CardError):
            modelgov.a_check_results("no-es-assessment")

    def test_modulos_sin_lenguaje_de_cumplimiento(self):
        patron = re.compile(r"EU AI Act|NIST|GDPR|RGPD|HIPAA|ISO[ /-]?\d{3,}|SOC ?2")
        for nombre in ("govpolicy.py", "modelgov.py"):
            with self.subTest(modulo=nombre):
                texto = (REPO / "tools" / "cards" / nombre).read_text(encoding="utf-8")
                self.assertIsNone(patron.search(texto))

    # -- serialización ---------------------------------------------------------

    def test_serializacion_determinista_y_round_trip_identico(self):
        card = self.armar("medium")
        ruta = modelgov.write_governance_assessment(self.raiz, card, clock=lambda: NOW)
        with tempfile.TemporaryDirectory() as otra:
            ruta2 = modelgov.write_governance_assessment(otra, card, clock=lambda: NOW)
            self.assertEqual(ruta.read_bytes(), ruta2.read_bytes())
        leida = assess.read_card(ruta)
        self.assertEqual(leida.to_dict(), card.to_dict())
        self.assertEqual(leida.revision_id(), card.revision_id())
        self.assertEqual(self.evaluar(ruta).a_dict(), self.evaluar(card).a_dict())
        self.assertEqual(self.evaluar(str(ruta)).a_dict(), self.evaluar(card).a_dict())
        self.assertEqual(self.evaluar(leida).a_dict(), self.evaluar(card).a_dict())

    def test_round_trip_de_invalid_y_stale(self):
        card = self.armar("low", policy_cambios={"base_version": 2})
        ruta = self.raiz / "copia.json"
        assess.write_card(ruta, card, lambda: NOW, validate_body=modelgov.body_validator_for(card))
        self.assertEqual(self.evaluar(ruta).a_dict(), self.evaluar(card).a_dict())
        self.assertEqual(self.evaluar(ruta).governance_completeness, "stale")

    def test_archivo_mal_formado_es_invalid_sin_excepcion(self):
        valido = self.armar("low").to_dict(con_revision=True)
        con_status = dict(valido, status="complete")
        revision_mala = dict(valido, revision_id="x__000000000000")
        contenidos = {
            "vacio": b"",
            "basura": b"esto no es json",
            "json cortado": b'{"schema_version": 1,',
            "bytes invalidos": b"\xff\xfe\x00",
            "lista": b"[]",
            "objeto vacio": b"{}",
            "constante nan": b'{"schema_version": NaN}',
            "con status": json.dumps(con_status).encode("utf-8"),
            "revision_id incorrecta": json.dumps(revision_mala).encode("utf-8"),
        }
        for nombre, datos in contenidos.items():
            with self.subTest(caso=nombre):
                ruta = self.escribir_bytes("malo.json", datos)
                a = self.evaluar(ruta)
                self.assertEqual(a.governance_completeness, "invalid")
                self.assertTrue(a.hallazgos)
                res = modelgov.a_check_results(a)
                self.assertTrue(res)

    def test_ruta_inexistente_o_invalida_es_invalid(self):
        for valor in (self.raiz / "no-existe.json", str(self.raiz / "otro.json"), None, 5):
            with self.subTest(valor=valor):
                a = self.evaluar(valor)
                self.assertEqual(a.governance_completeness, "invalid")

    def test_modelcard_no_se_evalua_como_assessment(self):
        ruta = modelcard.card_path(self.raiz, "clasificador__1_0_0")
        a = self.evaluar(ruta)
        self.assertEqual(a.governance_completeness, "invalid")
        self.assertIn(modelgov.CODE_KIND_INVALID, codigos(a))


# ---------------------------------------------------------------------------
# Separación de la Model Card e inercia (R6, R53, R54, D1)
# ---------------------------------------------------------------------------


class TestSeparacionEInercia(BaseGov):
    def test_model_card_real_no_contiene_claves_de_riesgo(self):
        mc = assess.read_card(modelcard.card_path(self.raiz, "clasificador__1_0_0"))
        self.assertEqual(set(mc.body), {"model_id", "model_version", "description"})
        claves = set(claves_recursivas(mc.to_dict()))
        for prohibida in CLAVES_PROHIBIDAS + ("risk_level", "risk_declaration", "policy_ref", "model_card_ref"):
            self.assertNotIn(prohibida, claves)

    def test_contrato_v1_de_model_card_rechaza_claves_rai(self):
        mc = assess.read_card(modelcard.card_path(self.raiz, "clasificador__1_0_0"))
        for clave in ("risk_level", "risk_declaration", "governance_completeness", "policy_ref", "fair", "score"):
            with self.subTest(clave=clave):
                malo = dataclasses.replace(mc, body={**mc.body, clave: "high"})
                self.assertTrue(modelcard.validate_model_card(malo))

    def test_escribir_el_assessment_no_modifica_la_model_card(self):
        ruta = modelcard.card_path(self.raiz, "clasificador__1_0_0")
        antes = ruta.read_bytes()
        modelgov.write_governance_assessment(self.raiz, self.armar("high"), clock=lambda: NOW)
        self.assertEqual(ruta.read_bytes(), antes)
        self.assertEqual(modelcard.validate_model_card(assess.read_card(ruta)), [])

    def test_assessment_no_es_una_model_card_valida(self):
        self.assertTrue(modelcard.validate_model_card(self.armar("low")))

    def test_evaluar_cualquier_estado_no_escribe_nada(self):
        casos = {
            "complete": self.armar("high"),
            "invalid": dataclasses.replace(self.armar("low"), subject="otro"),
            "incomplete": self.armar("low", riesgo=None, claims={}),
            "stale": self.armar("low", policy_cambios={"base_version": 2}),
        }
        antes = snapshot(self.raiz)
        for nombre, card in casos.items():
            with self.subTest(caso=nombre):
                a = self.evaluar(card)
                modelgov.a_check_results(a)
                self.assertEqual(snapshot(self.raiz), antes)
        nombres = {p.name for p in self.raiz.rglob("*")}
        self.assertNotIn("control.json", nombres)
        self.assertNotIn("guardrails.json", nombres)
        self.assertNotIn("project.json", nombres)
        self.assertFalse((self.raiz / "governance" / "model-risk").exists())

    def test_assessment_invalid_no_cambia_nada_en_autonomia(self):
        antes = snapshot(self.raiz)
        a = self.evaluar(self.armar("low", body_extra={"status": "complete"}))
        self.assertEqual(a.governance_completeness, "invalid")
        self.assertEqual(snapshot(self.raiz), antes)
        self.assertFalse((self.raiz / ".harmessi" / "control.json").exists())

    def test_importar_y_evaluar_no_carga_autonomia_ni_dependencias_prohibidas(self):
        card = self.armar("low")
        ruta = modelgov.write_governance_assessment(self.raiz, card, clock=lambda: NOW)
        codigo = (
            "import sys, json\n"
            "import tools\n"
            "base = set(sys.modules)\n"
            "from tools.cards import modelgov\n"
            "a = modelgov.evaluate_governance_assessment(sys.argv[1], sys.argv[2])\n"
            "nuevos = sorted(set(sys.modules) - base)\n"
            "print(json.dumps({'estado': a.governance_completeness, 'nuevos': nuevos}))\n"
        )
        entorno = dict(os.environ)
        entorno["PYTHONPATH"] = str(REPO) + os.pathsep + entorno.get("PYTHONPATH", "")
        proc = subprocess.run(
            [sys.executable, "-c", codigo, str(ruta), str(self.raiz)],
            cwd=str(self.raiz), env=entorno, capture_output=True, text=True, timeout=120,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        salida = json.loads(proc.stdout.strip().splitlines()[-1])
        self.assertEqual(salida["estado"], "complete")
        prohibidos = {"autonomy", "leadrun", "modelquality", "qualityevidence", "datasources", "datacontracts",
                      "reporting", "ds_init", "dsguard", "ds_guard", "modelcard", "datacard"}
        cargados = {m.split(".")[-1] for m in salida["nuevos"]}
        self.assertFalse(prohibidos & cargados, prohibidos & cargados)

    def test_no_hay_registry_ni_indice(self):
        modelgov.write_governance_assessment(self.raiz, self.armar("low"), clock=lambda: NOW)
        self.assertEqual(os.listdir(self.raiz / "governance" / "model-risk"), ["clasificador__1_0_0.json"])
        self.assertEqual(sorted(os.listdir(self.raiz / "governance")), ["cards", "model-risk"])


# ---------------------------------------------------------------------------
# Fixes del review ciclo 1 (I1, I2, M3, M5)
# ---------------------------------------------------------------------------


class TestReviewCiclo1(BaseGov):
    # -- I1: R50(d) cualquier evidencia stale de la Card deja el assessment stale ----------

    def cfg_low_con_doc(self):
        cfg = self.config("low")
        cfg["evidence"].append(self.pin_doc("ev-doc-eq", "informe-equidad", "eq"))
        return cfg

    def alterar_doc(self, clave="eq"):
        (self.raiz / DOCS[clave]).write_bytes(b"contenido alterado")

    def test_i1_base_sin_evidencia_extra_es_complete(self):
        a = self.evaluar(self.ensamblar(**self.cfg_low_con_doc()))
        self.assertEqual(a.governance_completeness, "complete")
        self.assertEqual(estado_ev(a, "ev-doc-eq"), "fresh")

    def test_i1_stale_citada_solo_por_requisito_recommended(self):
        cfg = self.config("medium")
        cfg["evidence"].append(self.pin_doc("ev-doc-ex", "informe-explicabilidad", "ex"))
        cfg["claims"]["explainability_evidence"] = ("ev-doc-ex",)  # recommended en medium
        card = self.ensamblar(**cfg)
        self.alterar_doc("ex")
        a = self.evaluar(card)
        self.assertEqual(estado_req(a, "explainability_evidence"), "stale")
        self.assertEqual(a.governance_completeness, "stale")

    def test_i1_stale_citada_solo_por_requisito_inactivo_en_el_nivel(self):
        cfg = self.cfg_low_con_doc()
        cfg["claims"]["fairness_evidence"] = ("ev-doc-eq",)  # fairness no aplica en low
        card = self.ensamblar(**cfg)
        self.alterar_doc()
        a = self.evaluar(card)
        self.assertNotIn("fairness_evidence", ids_req(a))
        self.assertEqual(a.governance_completeness, "stale")

    def test_i1_stale_citada_solo_por_claim_libre(self):
        cfg = self.cfg_low_con_doc()
        libre = core.Claim("c-libre", "Afirmación libre sobre el informe", supports=("ev-doc-eq",))
        card = self.ensamblar(extra_claims=(libre,), **cfg)
        self.alterar_doc()
        self.assertEqual(self.evaluar(card).governance_completeness, "stale")

    def test_i1_stale_huerfana(self):
        card = self.ensamblar(**self.cfg_low_con_doc())
        self.alterar_doc()
        a = self.evaluar(card)
        self.assertEqual(estado_ev(a, "ev-doc-eq"), "stale")
        self.assertEqual(a.governance_completeness, "stale")

    def test_i1_huerfana_unresolvable_no_cambia_el_estado_global_pero_se_informa(self):
        card = self.ensamblar(**self.cfg_low_con_doc())
        (self.raiz / DOCS["eq"]).unlink()
        a = self.evaluar(card)
        self.assertEqual(a.governance_completeness, "complete")
        self.assertEqual(estado_ev(a, "ev-doc-eq"), "unresolvable")

    def test_i1_huerfana_unverifiable_no_cambia_el_estado_global_pero_se_informa(self):
        card = self.ensamblar(**self.cfg_low_con_doc())
        ruta = self.raiz / DOCS["eq"]
        ruta.unlink()
        ruta.mkdir()
        a = self.evaluar(card)
        self.assertEqual(a.governance_completeness, "complete")
        self.assertEqual(estado_ev(a, "ev-doc-eq"), "unverifiable")

    # -- I2: la atestación risk_level está reservada para la declaración -------------------

    def test_i2_atestacion_de_riesgo_como_soporte_ajeno_es_invalid(self):
        casos = {
            "owner": ("low", "accountability_owner"),
            "fairness medium": ("medium", "fairness_evidence"),
        }
        for nombre, (nivel, rid) in casos.items():
            for soportes in (("at-risk",), ("at-risk", "at-owner")):
                with self.subTest(caso=nombre, soportes=soportes):
                    cfg = self.config(nivel)
                    cfg["claims"][rid] = soportes
                    a = self.evaluar(self.ensamblar(**cfg))
                    self.assertEqual(a.governance_completeness, "invalid")
                    self.assertIn(modelgov.CODE_CLAIM_SUPPORT_INCONSISTENT, codigos(a))

    def test_i2_claim_libre_apoyado_en_la_atestacion_de_riesgo_es_invalid(self):
        libre = core.Claim("c-libre", "Afirmación libre", supports=("at-risk",))
        a = self.evaluar(self.ensamblar(extra_claims=(libre,), **self.config("low")))
        self.assertEqual(a.governance_completeness, "invalid")
        self.assertIn(modelgov.CODE_CLAIM_SUPPORT_INCONSISTENT, codigos(a))

    def test_i2_usada_solo_en_la_declaracion_sigue_valida(self):
        a = self.evaluar(self.armar("low"))
        self.assertEqual(estado_req(a, "accountability_risk_declaration"), "satisfied")
        self.assertEqual(a.governance_completeness, "complete")

    def test_i2_owner_con_su_propia_atestacion_sigue_satisfaciendo(self):
        a = self.evaluar(self.armar("low"))
        self.assertEqual(estado_req(a, "accountability_owner"), "satisfied")

    # -- M3: claims near-miss de la declaración de riesgo ------------------------------

    def test_m3_claims_near_miss_son_invalid_ref_inconsistent(self):
        casos = ("Risk_Level=high", "risk_level = high", "risk level: high", "risk_level=critical",
                 "risk_level=high ", "risk-level=low", "RISK_LEVEL=low")
        for claim in casos:
            with self.subTest(claim=claim):
                cfg = self.config("low")
                cfg["attestations"].append(hacer_att("at-near", claim))
                a = self.evaluar(self.ensamblar(**cfg))
                self.assertEqual(a.governance_completeness, "invalid")
                self.assertIn(modelgov.CODE_REF_INCONSISTENT, codigos(a))
                self.assertTrue(any("malformada" in h.detail for h in a.hallazgos))

    def test_m3_near_miss_como_declaracion_del_body_es_invalid(self):
        cfg = self.config("low")
        cfg["attestations"][0] = hacer_att("at-risk", "Risk_Level=low")
        a = self.evaluar(self.ensamblar(**cfg))
        self.assertEqual(a.governance_completeness, "invalid")
        self.assertIn(modelgov.CODE_REF_INCONSISTENT, codigos(a))

    def test_m3_claim_exacto_sigue_siendo_declaracion(self):
        for nivel in govpolicy.LEVELS:
            with self.subTest(nivel=nivel):
                a = self.evaluar(self.armar(nivel))
                self.assertEqual(a.governance_completeness, "complete", a.hallazgos)
                self.assertEqual(a.declared_level, nivel)

    # -- M5: el hardening cambia entre la resolución y la lectura ----------------------

    def test_m5_hardening_que_cambia_entre_resolucion_y_lectura_es_stale(self):
        card = self.armar("low", hardening=hardening(floor="low"))
        cambiado = hardening(floor="medium").to_dict()
        with mock.patch.object(resolvers, "leer_documento_json", return_value=cambiado):
            a = self.evaluar(card)
        self.assertEqual(estado_ev(a, "ev-hard"), "fresh")  # el resolver vio el archivo pineado
        self.assertEqual(a.governance_completeness, "stale")
        self.assertIn(modelgov.CODE_POLICY_CHANGED, codigos(a))
        self.assertIsNone(a.policy["recomputed"]["effective_sha256"])
        self.assertIsNone(a.effective_level)
        self.assertIsNone(a.risk_floor)

    def test_m5_documento_ilegible_sigue_incomplete(self):
        card = self.armar("low", hardening=hardening(floor="low"))
        with mock.patch.object(
            resolvers, "leer_documento_json", side_effect=core.CardError(core.CODE_IO_ERROR, "ilegible")
        ):
            a = self.evaluar(card)
        self.assertEqual(a.governance_completeness, "incomplete")
        self.assertIn(modelgov.CODE_POLICY_INVALID, codigos(a))
        self.assertIsNone(a.policy["recomputed"]["effective_sha256"])

    def test_m5_sin_parche_el_hardening_pineado_es_complete(self):
        a = self.evaluar(self.armar("low", hardening=hardening(floor="low")))
        self.assertEqual(a.governance_completeness, "complete", a.hallazgos)


# ---------------------------------------------------------------------------
# Fixes del review ciclo 2
# ---------------------------------------------------------------------------


class TestReviewCiclo2(BaseGov):
    # -- (1) la atestación de riesgo no puede respaldar un not_applicable ------------------

    def medium_na(self, att_id):
        cfg = self.config("medium")
        cfg["attestations"].append(hacer_att("at-na", "El requisito no aplica a este modelo"))
        return self.ensamblar(
            dimensions=dim_na("explainability", "explainability_evidence", att=att_id), **cfg
        )

    def test_atestacion_de_riesgo_como_respaldo_de_na_es_invalid(self):
        a = self.evaluar(self.medium_na("at-risk"))
        self.assertEqual(a.governance_completeness, "invalid")
        self.assertIn(modelgov.CODE_CLAIM_SUPPORT_INCONSISTENT, codigos(a))
        self.assertIn(modelgov.CODE_CLAIM_SUPPORT_INCONSISTENT,
                      {h.code for h in modelgov.validate_governance_assessment(self.medium_na("at-risk"))})

    def test_na_con_su_propia_atestacion_sigue_valido(self):
        a = self.evaluar(self.medium_na("at-na"))
        self.assertEqual(a.governance_completeness, "complete", a.hallazgos)
        self.assertEqual(estado_req(a, "explainability_evidence"), "not_applicable")

    # -- (2) near-miss: negativos que NO invalidan --------------------------------------

    def test_claims_de_otras_atestaciones_no_se_confunden_con_la_declaracion(self):
        negativos = (
            "The risk level is reviewed quarterly",
            "Owner: platform team. Risk level: low",
            "Responsable del riesgo operativo",
        )
        for claim in negativos:
            with self.subTest(claim=claim):
                cfg = self.config("low")
                cfg["attestations"].append(hacer_att("at-otra", claim))
                card = self.ensamblar(**cfg)
                self.assertEqual(modelgov.validate_governance_assessment(card), [])
                a = self.evaluar(card)
                self.assertEqual(a.governance_completeness, "complete", a.hallazgos)

    # -- (2) near-miss: positivos que SÍ invalidan --------------------------------------
    # Falso positivo acotado y fail-closed ACEPTADO: un claim que EMPIEZA con el patrón
    # `risk[_ -]level\s*[=:]` (p. ej. «Risk level: reviewed by committee») se trata como una
    # declaración de riesgo malformada aunque no pretenda serlo. Es preferible rechazar a
    # ignorar silenciosamente una declaración mal escrita.

    def test_claims_que_empiezan_con_el_patron_invalidan(self):
        positivos = ("Risk level: reviewed by committee", "risk_level:high", "risk-level = low")
        for claim in positivos:
            with self.subTest(claim=claim):
                cfg = self.config("low")
                cfg["attestations"].append(hacer_att("at-otra", claim))
                a = self.evaluar(self.ensamblar(**cfg))
                self.assertEqual(a.governance_completeness, "invalid")
                self.assertIn(modelgov.CODE_REF_INCONSISTENT, codigos(a))


if __name__ == "__main__":
    unittest.main()

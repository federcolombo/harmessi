"""Tests de `tools.cards.modelcard` (Change `20261005-model-cards`, R6-R39).

Usan OBJETOS REALES en directorios temporales: Data Cards escritas con
`datacard.write_data_card`; v0.7 (`modelquality`, `qualityevidence`) para
política, métricas, baselines, manifest y drift; `leadrun` para el
ExecutionRecord. Sin mocks salvo la comprobación de que no se reevalúa la
Data Card.
"""
from __future__ import annotations

import copy
import dataclasses
import itertools
import json
import re
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from tools.cards import assess, core, datacard, modelcard, resolvers
from tools.leadrun import core as lr
from tools.modelquality import core as mq
from tools.modelquality import validation as mq_validation
from tools.qualityevidence import core as qe_core
from tools.qualityevidence import evidence as qe_evidence

T0 = "2026-10-01T10:00:00Z"
NOW = "2026-10-04T00:00:00Z"
RELOJ_V07 = lambda: datetime(2026, 10, 1, 10, 0, 0, tzinfo=timezone.utc)  # noqa: E731

REL_MET = "evaluacion/metricas.json"
REL_BASE = "evaluacion/baselines.json"
REL_POL = "evaluacion/politica.json"
REL_DRIFT = "evaluacion/drift.json"

# Copia independiente de los patrones del spec (R7) para usar como oráculo.
ORACULO_MODEL_ID = re.compile(r"[a-z0-9]+([_-][a-z0-9]+)*")
ORACULO_VERSION = re.compile(r"[a-z0-9]+([.-][a-z0-9]+)*")


# ---------------------------------------------------------------------------
# Helpers genéricos
# ---------------------------------------------------------------------------


def codigo_de(funcion, *args, **kwargs):
    try:
        funcion(*args, **kwargs)
    except core.CardError as exc:
        return exc.code
    raise AssertionError("no lanzó CardError")


def codigos(card):
    return {h.code for h in modelcard.validate_model_card(card)}


def estado_req(assessment, rid):
    for r in assessment.requisitos:
        if r[0] == rid:
            return r[2]
    raise AssertionError(f"requisito {rid} ausente")


def estado_ev(assessment, eid):
    return dict(assessment.evidencias)[eid]


def claim_de(eid, soportes=None):
    return core.Claim(
        "c-" + eid,
        "Respaldo del pin",
        supports=tuple(soportes) if soportes is not None else (eid,),
        requirement_id=modelcard.requirement_id_for_evidence(eid),
    )


def hacer_att(**kw):
    base = dict(
        attestation_id="at-own",
        claim="El dueño del modelo es el equipo de datos",
        actor="ana",
        authority="owner",
        attested_at=T0,
        scope="Propiedad del modelo",
        attestation_kind="declared",
    )
    base.update(kw)
    return core.HumanAttestation(**base)


def claim_ownership(supports=("at-own",)):
    return core.Claim("c-own", "Ownership declarado", supports=supports, requirement_id=modelcard.REQ_OWNERSHIP)


def armar_card(model_id="clasificador", model_version="1.0.0", body_extra=None, pins=(), claims="auto",
               claims_extra=(), attestations=(), descripcion="Modelo de prueba", **kw):
    """Model Card con `body_extra` y `pins`; `claims="auto"` crea un claim propio por pin."""
    body = {"model_id": model_id, "model_version": model_version, "description": descripcion}
    body.update(body_extra or {})
    if claims == "auto":
        claims = [claim_de(p.evidence_id) for p in pins]
    base = dict(
        schema_version=1,
        card_kind="model_card",
        kind_schema_version=1,
        card_id=modelcard.model_card_id(model_id, model_version),
        title="Model Card de prueba",
        subject=model_id,
        created_at=T0,
        generated_at=T0,
        evidence=tuple(pins),
        attestations=tuple(attestations),
        claims=tuple(claims) + tuple(claims_extra),
        body=body,
    )
    base.update(kw)
    return core.CardEnvelope(**base)


def con_body(card, **cambios):
    body = copy.deepcopy(card.body)
    body.update(cambios)
    return dataclasses.replace(card, body=body)


def sin_clave(card, clave):
    body = copy.deepcopy(card.body)
    body.pop(clave, None)
    return dataclasses.replace(card, body=body)


def hacer_data_card(card_id, descripcion="Producto de datos de prueba"):
    pin = core.EvidenceRef("ev-src-a", "source_observation", "ventas__aaaaaaaaaaaa", "a" * 64, T0)
    return core.CardEnvelope(
        schema_version=1,
        card_kind="data_card",
        kind_schema_version=1,
        card_id=card_id,
        title="Data Card de prueba",
        subject=card_id,
        created_at=T0,
        generated_at=T0,
        evidence=(pin,),
        claims=(core.Claim("c-src-a", "Observada", supports=("ev-src-a",), requirement_id="source_src-a"),),
        body={
            "description": descripcion,
            "source_refs": [{"source_ref_id": "src-a", "source_id": "ventas", "observation_evidence_id": "ev-src-a"}],
        },
    )


class BaseTmp(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.raiz = Path(self._tmp.name).resolve()

    def evaluar(self, card):
        return modelcard.evaluate_model_card(card, self.raiz)

    def escribir_json(self, rel, obj):
        ruta = self.raiz / rel
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return ruta

    def leer_json(self, rel):
        return json.loads((self.raiz / rel).read_text(encoding="utf-8"))


class BaseMundo(BaseTmp):
    """Mundo completo con artefactos reales de Data Cards y v0.7 y sus pins coherentes."""

    def setUp(self):
        super().setUp()
        ctx_test = mq.EvaluationContext("ctx-test", "test")
        ctx_val = mq.EvaluationContext("ctx-val", "validation")
        self.ctx_test = ctx_test
        self.metricas = [
            mq.ObservedMetric("accuracy", 0.9, ctx_test, sample_size=100).to_dict(),
            mq.ObservedMetric("recall", 0.7, ctx_test).to_dict(),
            mq.ObservedMetric("accuracy", 0.88, ctx_val).to_dict(),
        ]
        self.baselines = [
            mq.BaselineReference("bl-prev", "accuracy", 0.85, ctx_test, "modelo anterior").to_dict(),
            mq.BaselineReference("bl-naive", "accuracy", 0.5, ctx_test, "clase mayoritaria").to_dict(),
        ]
        self.politica_obj = mq.ModelQualityPolicy(
            policy_id="pol-clasif",
            model_task_role="classification",
            requirements=(
                mq.MetricRequirement("req-acc", "accuracy", "higher_is_better", ctx_test, threshold_value=0.8),
            ),
        )
        self.politica = self.politica_obj.to_dict()
        self.escribir_json(REL_MET, self.metricas)
        self.escribir_json(REL_BASE, self.baselines)
        self.escribir_json(REL_POL, self.politica)

        # Manifest real model_quality_evaluation
        observadas = [mq.ObservedMetric.from_dict(m) for m in self.metricas]
        resultados = mq_validation.evaluate_policy(self.politica_obj, observadas, [])
        declaracion = qe_core.DeclarationRef(
            "model_quality_policy", self.politica_obj.policy_id, None, resolvers.hash_policy(self.politica)
        )
        fuente = qe_evidence.describe_source_generated("metricas sinteticas", {"n": 3})
        self.manifest = qe_evidence.build_manifest(
            subject_kind="model_quality_evaluation",
            declaration=declaracion,
            source=fuente,
            results=resultados,
            clock=RELOJ_V07,
        )
        qe_evidence.write_manifest(self.raiz, self.manifest)
        self.rel_manifest = f".harmessi/quality/{self.manifest.evidence_id}/manifest.json"

        # Drift real
        self.drift = qe_evidence.build_drift_evidence(
            metric_name="accuracy",
            baseline_value=0.85,
            current_value=0.9,
            baseline_window=qe_evidence.describe_source_generated("ventana base", {"w": 1}),
            baseline_label="base",
            current_window=qe_evidence.describe_source_generated("ventana actual", {"w": 2}),
            current_label="actual",
            comparison_mode="absolute_diff",
            clock=RELOJ_V07,
        )
        self.escribir_json(REL_DRIFT, self.drift.to_dict())

        # ExecutionRecord real
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
        self.rel_exec = f".harmessi/executions/{self.registro.execution_id}/record.json"
        self.escribir_json(self.rel_exec, self.registro.to_dict())

        # Data Cards reales
        self.escribir_data_card("ventas-train")
        self.escribir_data_card("ventas-test")

        self.pins = {
            "dc_train": self.pin_data_card("ventas-train", "ev-dc-train"),
            "dc_test": self.pin_data_card("ventas-test", "ev-dc-test"),
            "result": core.EvidenceRef(
                "ev-res", "model_quality_result", self.manifest.evidence_id, self.manifest.content_sha256(), T0
            ),
            "policy": core.EvidenceRef(
                "ev-pol", "model_quality_policy", "pol-clasif", resolvers.hash_policy(self.politica), T0,
                locator=REL_POL,
            ),
            "metric": core.EvidenceRef(
                "ev-met", "observed_metric", "metricas-test", resolvers.hash_document(self.metricas), T0,
                member="accuracy@ctx-test", locator=REL_MET,
            ),
            "baseline": core.EvidenceRef(
                "ev-base", "baseline_reference", "baselines-test", resolvers.hash_document(self.baselines), T0,
                member="bl-prev", locator=REL_BASE,
            ),
            "drift": core.EvidenceRef(
                "ev-drift", "drift_evidence", self.drift.drift_id, resolvers.hash_drift(self.drift.to_dict()), T0,
                locator=REL_DRIFT,
            ),
            "exec": core.EvidenceRef(
                "ev-exec", "execution_record", self.registro.execution_id,
                resolvers.hash_execution_record(self.registro.to_dict()), T0,
            ),
        }

    # -- Data Cards ---------------------------------------------------------

    def escribir_data_card(self, card_id, descripcion="Producto de datos de prueba", replace=False):
        return datacard.write_data_card(
            self.raiz, hacer_data_card(card_id, descripcion), replace=replace, clock=lambda: NOW
        )

    def pin_data_card(self, card_id, evidence_id, con_locator=True):
        ruta = datacard.card_path(self.raiz, card_id)
        h = assess.read_card(ruta).content_sha256()
        return core.EvidenceRef(
            evidence_id, "data_card", f"{card_id}__{h[:12]}", h, T0,
            locator=f"governance/cards/data/{card_id}.json" if con_locator else None,
        )

    # -- Card ---------------------------------------------------------------

    def body_completo(self):
        return {
            "data_card_refs": [
                {"data_card_ref_id": "dc-train", "role": "training", "evidence_id": "ev-dc-train"},
                {"data_card_ref_id": "dc-test", "role": "test", "evidence_id": "ev-dc-test"},
            ],
            "evaluation_refs": [
                {
                    "evaluation_ref_id": "eval-test",
                    "role": "test",
                    "result_evidence_id": "ev-res",
                    "policy_evidence_id": "ev-pol",
                    "metric_evidence_ids": ["ev-met"],
                    "baseline_evidence_ids": ["ev-base"],
                    "drift_evidence_ids": ["ev-drift"],
                }
            ],
            "provenance_refs": [{"provenance_ref_id": "prov-1", "role": "training_run", "evidence_id": "ev-exec"}],
        }

    def card_completa(self, **kw):
        return armar_card(body_extra=self.body_completo(), pins=list(self.pins.values()), **kw)

    def card_con(self, nombres, body_extra, **kw):
        return armar_card(body_extra=body_extra, pins=[self.pins[n] for n in nombres], **kw)

    def repin(self, nombre, **cambios):
        return dataclasses.replace(self.pins[nombre], **cambios)

    def card_con_pin_cambiado(self, nombre, **cambios):
        pins = dict(self.pins)
        pins[nombre] = self.repin(nombre, **cambios)
        return armar_card(body_extra=self.body_completo(), pins=list(pins.values()))


# ---------------------------------------------------------------------------
# Card mínima (plantilla vacía != evidencia)
# ---------------------------------------------------------------------------


class TestCardMinima(BaseTmp):
    def test_minima_valida_pero_incomplete(self):
        card = armar_card()
        self.assertEqual(modelcard.validate_model_card(card), [])
        ev = self.evaluar(card)
        self.assertEqual(ev.card_status, assess.CARD_INCOMPLETE)
        self.assertEqual(ev.hallazgos, ())

    def test_requisitos_derivados_de_la_minima_solo_ownership(self):
        reqs = modelcard.requirements_for(armar_card())
        self.assertEqual([r.requirement_id for r in reqs], [modelcard.REQ_OWNERSHIP])
        self.assertEqual(reqs[0].severity, "recommended")
        self.assertEqual(reqs[0].accepts, ("attestation",))
        self.assertEqual(reqs[0].min_attestation_kind, "declared")

    def test_requirements_for_exige_card(self):
        for valor in (None, {}, "x"):
            with self.subTest(valor=valor):
                self.assertEqual(codigo_de(modelcard.requirements_for, valor), core.CODE_FIELD_INVALID)

    def test_sin_status_ni_requisitos_persistidos(self):
        d = armar_card().to_dict()
        self.assertNotIn("status", d)
        self.assertNotIn("requirements", d)
        self.assertNotIn("requirements", d["body"])
        self.assertNotIn("status", d["body"])


# ---------------------------------------------------------------------------
# Identidad (R6-R9)
# ---------------------------------------------------------------------------


class TestIdentidad(BaseTmp):
    TABLA = (
        ("clasificador", "1.2.0", "clasificador__1_2_0"),
        ("clasificador", "1-2-0", "clasificador__1-2-0"),
        ("clasificador", "1.2", "clasificador__1_2"),
        ("clasificador", "a", "clasificador__a"),
        ("m", "1", "m__1"),
        ("mi_modelo", "2.0", "mi_modelo__2_0"),
        ("mi-modelo", "v1.2-rc1", "mi-modelo__v1_2-rc1"),
    )

    def test_tabla_de_codificacion_y_decodificacion(self):
        for model_id, version, esperado in self.TABLA:
            with self.subTest(model_id=model_id, version=version):
                self.assertEqual(modelcard.model_card_id(model_id, version), esperado)
                self.assertEqual(modelcard.decode_model_card_id(esperado), (model_id, version))

    def test_versiones_hermanas_dan_card_ids_distintos(self):
        ids = {modelcard.model_card_id("clasificador", v) for v in ("1.2.0", "1-2-0", "1.2")}
        self.assertEqual(len(ids), 3)

    def test_oraculo_de_validez_sobre_todas_las_cadenas_cortas(self):
        alfabeto = "a1-_."
        candidatas = ["".join(t) for n in range(1, 4) for t in itertools.product(alfabeto, repeat=n)]
        for s in candidatas:
            esperado_id = ORACULO_MODEL_ID.fullmatch(s) is not None
            try:
                modelcard.model_card_id(s, "1")
                obtenido_id = True
            except core.CardError as exc:
                self.assertEqual(exc.code, modelcard.CODE_IDENTITY_INVALID)
                obtenido_id = False
            self.assertEqual(obtenido_id, esperado_id, f"model_id {s!r}")
            esperado_v = ORACULO_VERSION.fullmatch(s) is not None
            try:
                modelcard.model_card_id("a", s)
                obtenido_v = True
            except core.CardError as exc:
                self.assertEqual(exc.code, modelcard.CODE_IDENTITY_INVALID)
                obtenido_v = False
            self.assertEqual(obtenido_v, esperado_v, f"version {s!r}")

    def test_inyectividad_y_reversibilidad_exhaustiva(self):
        alfabeto = "a1-_."
        candidatas = ["".join(t) for n in range(1, 4) for t in itertools.product(alfabeto, repeat=n)]
        ids_validos = [s for s in candidatas if ORACULO_MODEL_ID.fullmatch(s)]
        versiones_validas = [s for s in candidatas if ORACULO_VERSION.fullmatch(s)]
        self.assertTrue(ids_validos and versiones_validas)
        vistos = {}
        for m in ids_validos:
            for v in versiones_validas:
                card_id = modelcard.model_card_id(m, v)
                self.assertNotIn(card_id, vistos, f"colisión {(m, v)} vs {vistos.get(card_id)}")
                vistos[card_id] = (m, v)
                self.assertEqual(modelcard.decode_model_card_id(card_id), (m, v))
                self.assertRegex(card_id, r"^[a-z0-9][a-z0-9_-]{0,63}$")
        self.assertEqual(len(vistos), len(ids_validos) * len(versiones_validas))

    def test_decode_es_inversa_de_encode_para_cualquier_cadena_decodificable(self):
        for n in range(1, 7):
            for t in itertools.product("a1-_", repeat=n):
                s = "".join(t)
                try:
                    par = modelcard.decode_model_card_id(s)
                except core.CardError as exc:
                    self.assertEqual(exc.code, modelcard.CODE_IDENTITY_INVALID)
                    continue
                self.assertEqual(modelcard.model_card_id(*par), s)

    def test_versiones_invalidas(self):
        invalidas = ("1_2", "A", "1.2.", ".1", "1..2", "1.-2", "1-.2", "1.2.0 ", "", "../x", "a/b", "a\\b",
                     "1.2.0+build", "V1", None, 1, "-1", "1--2")
        for v in invalidas:
            with self.subTest(version=v):
                self.assertEqual(codigo_de(modelcard.model_card_id, "m", v), modelcard.CODE_IDENTITY_INVALID)

    def test_model_ids_invalidos(self):
        invalidos = ("", "A", "a__b", "a_", "_a", "a--b", "a/b", "..", "C:\\x", "a.b", "a b", None, 5,
                     "postgresql://u:p@h/db", "/abs", "a\\b")
        for m in invalidos:
            with self.subTest(model_id=m):
                self.assertEqual(codigo_de(modelcard.model_card_id, m, "1"), modelcard.CODE_IDENTITY_INVALID)

    def test_presupuesto_total_de_64(self):
        card_id = modelcard.model_card_id("a" * 30, "b" * 32)
        self.assertEqual(len(card_id), 64)
        self.assertEqual(modelcard.decode_model_card_id(card_id), ("a" * 30, "b" * 32))
        with self.assertRaises(core.CardError) as ctx:
            modelcard.model_card_id("a" * 31, "b" * 32)
        self.assertEqual(ctx.exception.code, modelcard.CODE_IDENTITY_INVALID)
        self.assertIn("64", ctx.exception.message)
        with self.assertRaises(core.CardError) as ctx:
            modelcard.model_card_id("a", "b" * 62)
        self.assertEqual(ctx.exception.code, modelcard.CODE_IDENTITY_INVALID)

    def test_decode_rechaza_card_ids_no_decodificables(self):
        for cid in ("a", "a__b__c", "A__1", "a__1__", "__1", "a__", "a___b", "a__1_", "a__.", "a__1.2", None, 5, ""):
            with self.subTest(card_id=cid):
                self.assertEqual(codigo_de(modelcard.decode_model_card_id, cid), modelcard.CODE_IDENTITY_INVALID)

    def test_card_id_distinto_del_derivado_es_mismatch(self):
        card = dataclasses.replace(armar_card(), card_id="clasificador__9_9_9")
        self.assertIn(modelcard.CODE_IDENTITY_MISMATCH, codigos(card))
        ev = self.evaluar(card)
        self.assertEqual(ev.card_status, assess.CARD_INVALID)
        self.assertIn(modelcard.CODE_IDENTITY_MISMATCH, {h.code for h in ev.hallazgos})

    def test_card_id_sin_codificar_la_version_es_mismatch(self):
        card = dataclasses.replace(armar_card(), card_id="clasificador__1.0.0".replace(".", "-"))
        self.assertIn(modelcard.CODE_IDENTITY_MISMATCH, codigos(card))

    def test_subject_distinto_de_model_id_es_mismatch(self):
        card = dataclasses.replace(armar_card(), subject="otro-modelo")
        self.assertIn(modelcard.CODE_IDENTITY_MISMATCH, codigos(card))
        self.assertEqual(self.evaluar(card).card_status, assess.CARD_INVALID)

    def test_body_con_identidad_invalida(self):
        base = armar_card()
        for cambios in ({"model_id": "A"}, {"model_version": "1_0"}, {"model_version": "x" * 70}, {"model_id": 5}):
            with self.subTest(cambios=cambios):
                self.assertIn(modelcard.CODE_IDENTITY_INVALID, codigos(con_body(base, **cambios)))

    def test_nueva_version_es_otra_card(self):
        v1, v2 = armar_card(model_version="1.0.0"), armar_card(model_version="1.1.0")
        self.assertNotEqual(v1.card_id, v2.card_id)
        self.assertNotEqual(v1.revision_id(), v2.revision_id())

    def test_edicion_documental_mismo_card_id_distinta_revision(self):
        a = armar_card(descripcion="Primera versión de la documentación")
        b = armar_card(descripcion="Documentación corregida")
        self.assertEqual(a.card_id, b.card_id)
        self.assertNotEqual(a.revision_id(), b.revision_id())
        self.assertTrue(a.revision_id().startswith(a.card_id + "__"))

    def test_revision_independiente_de_pins_para_la_identidad(self):
        # La identidad (card_id) no depende de los pins de evidencia
        self.assertEqual(armar_card().card_id, armar_card(pins=()).card_id)

    def test_no_hay_registry_ni_listado_de_modelos(self):
        publico = [n for n in dir(modelcard) if not n.startswith("_")]
        for nombre in publico:
            with self.subTest(nombre=nombre):
                self.assertNotRegex(nombre, r"^(list|scan|registry|index|discover)")


# ---------------------------------------------------------------------------
# Data Cards pineadas (R13, R23, R29)
# ---------------------------------------------------------------------------


class TestDataCardRefs(BaseMundo):
    def card_dc(self, **kw):
        return self.card_con(["dc_train", "dc_test"], {"data_card_refs": self.body_completo()["data_card_refs"]}, **kw)

    def test_dos_roles_training_y_test_ambos_fresh(self):
        card = self.card_dc()
        self.assertEqual(modelcard.validate_model_card(card), [])
        ev = self.evaluar(card)
        self.assertEqual(estado_ev(ev, "ev-dc-train"), assess.EV_FRESH)
        self.assertEqual(estado_ev(ev, "ev-dc-test"), assess.EV_FRESH)
        self.assertEqual(estado_req(ev, "evidence_ev-dc-train"), assess.REQ_SATISFIED)
        self.assertEqual(estado_req(ev, "evidence_ev-dc-test"), assess.REQ_SATISFIED)
        self.assertEqual(ev.card_status, assess.CARD_COMPLETE)

    def test_pin_sin_locator_tambien_resuelve(self):
        pins = [self.pin_data_card("ventas-train", "ev-dc-train", con_locator=False)]
        card = armar_card(body_extra={"data_card_refs": [self.body_completo()["data_card_refs"][0]]}, pins=pins)
        self.assertEqual(self.evaluar(card).card_status, assess.CARD_COMPLETE)

    def test_data_card_incomplete_integra_es_fresh_sin_herencia(self):
        # La Data Card de hacer_data_card cita una observación inexistente: su propio estado no es complete.
        card = self.card_dc()
        with mock.patch.object(datacard, "evaluate_data_card", side_effect=AssertionError("no debe evaluarse")), \
                mock.patch.object(datacard, "requirements_for", side_effect=AssertionError("no debe evaluarse")):
            ev = self.evaluar(card)
        self.assertEqual(estado_ev(ev, "ev-dc-train"), assess.EV_FRESH)
        self.assertEqual(ev.card_status, assess.CARD_COMPLETE)

    def test_data_card_editada_deja_pin_stale_y_card_stale(self):
        self.escribir_data_card("ventas-train", "Descripción revisada", replace=True)
        ev = self.evaluar(self.card_dc())
        self.assertEqual(estado_ev(ev, "ev-dc-train"), assess.EV_STALE)
        self.assertEqual(estado_ev(ev, "ev-dc-test"), assess.EV_FRESH)
        self.assertEqual(estado_req(ev, "evidence_ev-dc-train"), assess.REQ_STALE)
        self.assertEqual(estado_req(ev, "evidence_ev-dc-test"), assess.REQ_SATISFIED)
        self.assertEqual(ev.card_status, assess.CARD_STALE)

    def test_stale_de_un_pin_no_queda_tapado_por_el_otro(self):
        self.escribir_data_card("ventas-test", "Cambiada", replace=True)
        self.assertEqual(self.evaluar(self.card_dc()).card_status, assess.CARD_STALE)

    def test_data_card_ausente_es_incomplete(self):
        datacard.card_path(self.raiz, "ventas-test").unlink()
        ev = self.evaluar(self.card_dc())
        self.assertEqual(estado_ev(ev, "ev-dc-test"), assess.EV_UNRESOLVABLE)
        self.assertEqual(estado_ev(ev, "ev-dc-train"), assess.EV_FRESH)
        self.assertEqual(ev.card_status, assess.CARD_INCOMPLETE)

    def test_data_card_adulterada_es_unverifiable(self):
        ruta = datacard.card_path(self.raiz, "ventas-train")
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        datos["title"] = "Título cambiado a mano"  # revision_id ya no coincide
        ruta.write_text(json.dumps(datos), encoding="utf-8")
        ev = self.evaluar(self.card_dc())
        self.assertEqual(estado_ev(ev, "ev-dc-train"), assess.EV_UNVERIFIABLE)
        self.assertEqual(ev.card_status, assess.CARD_INCOMPLETE)

    def test_pin_apuntando_a_una_model_card_es_unverifiable(self):
        # card_kind distinto de data_card en la ubicación de Data Cards
        otra = armar_card(model_id="ventas-x", model_version="1")
        ruta = self.raiz / "governance" / "cards" / "data" / (otra.card_id + ".json")
        ruta.parent.mkdir(parents=True, exist_ok=True)
        assess.write_card(ruta, otra, lambda: NOW, validate_body=modelcard.body_validator_for(otra))
        h = assess.read_card(ruta).content_sha256()
        pin = core.EvidenceRef("ev-dc-train", "data_card", f"{otra.card_id}__{h[:12]}", h, T0)
        res = resolvers.data_card_resolver(self.raiz)(pin)
        self.assertEqual(res.state, assess.RES_UNVERIFIABLE)

    def test_ref_id_con_hash12_inconsistente_es_ref_inconsistent(self):
        malo = self.repin("dc_train", ref_id="ventas-train__" + "0" * 12)
        card = armar_card(body_extra={"data_card_refs": [self.body_completo()["data_card_refs"][0]]}, pins=[malo])
        self.assertIn(modelcard.CODE_REF_INCONSISTENT, codigos(card))

    def test_locator_distinto_del_canonico_es_ref_inconsistent(self):
        malo = self.repin("dc_train", locator="governance/cards/data/otra.json")
        card = armar_card(body_extra={"data_card_refs": [self.body_completo()["data_card_refs"][0]]}, pins=[malo])
        self.assertIn(modelcard.CODE_REF_INCONSISTENT, codigos(card))

    def test_ref_id_sin_formato_es_ref_inconsistent(self):
        malo = self.repin("dc_train", ref_id="ventas-train")
        card = armar_card(body_extra={"data_card_refs": [self.body_completo()["data_card_refs"][0]]}, pins=[malo])
        self.assertIn(modelcard.CODE_REF_INCONSISTENT, codigos(card))

    def test_data_card_ref_con_pin_de_otro_kind_es_ref_inconsistent(self):
        ref = dict(self.body_completo()["data_card_refs"][0], evidence_id="ev-met")
        card = armar_card(body_extra={"data_card_refs": [ref]}, pins=[self.pins["metric"]])
        self.assertIn(modelcard.CODE_REF_INCONSISTENT, codigos(card))

    def test_data_card_ref_colgante(self):
        ref = dict(self.body_completo()["data_card_refs"][0], evidence_id="no-existe")
        self.assertIn(modelcard.CODE_DANGLING_EVIDENCE, codigos(armar_card(body_extra={"data_card_refs": [ref]})))

    def test_data_card_ref_id_duplicado(self):
        refs = self.body_completo()["data_card_refs"]
        refs[1]["data_card_ref_id"] = refs[0]["data_card_ref_id"]
        card = self.card_con(["dc_train", "dc_test"], {"data_card_refs": refs})
        self.assertIn(modelcard.CODE_REF_INCONSISTENT, codigos(card))

    def test_roles_libres_y_roles_invalidos(self):
        for rol in ("calibration", "inference_reference", "mi-rol-propio", "x1"):
            with self.subTest(rol=rol):
                ref = dict(self.body_completo()["data_card_refs"][0], role=rol)
                card = armar_card(body_extra={"data_card_refs": [ref]}, pins=[self.pins["dc_train"]])
                self.assertEqual(modelcard.validate_model_card(card), [])
        for rol in ("", "Bad Role", "-x", "a/b", 5):
            with self.subTest(rol=rol):
                ref = dict(self.body_completo()["data_card_refs"][0], role=rol)
                card = armar_card(body_extra={"data_card_refs": [ref]}, pins=[self.pins["dc_train"]])
                self.assertIn(modelcard.CODE_BODY_INVALID, codigos(card))

    def test_claim_propio_ausente_deja_el_requisito_missing_e_incomplete(self):
        card = self.card_con(["dc_train", "dc_test"], {"data_card_refs": self.body_completo()["data_card_refs"]},
                             claims=[claim_de("ev-dc-train")])
        ev = self.evaluar(card)
        self.assertEqual(estado_req(ev, "evidence_ev-dc-test"), assess.REQ_MISSING)
        self.assertEqual(ev.card_status, assess.CARD_INCOMPLETE)

    def test_no_se_copian_datos_de_la_data_card(self):
        card = self.card_dc()
        texto = json.dumps(card.body)
        self.assertNotIn("source_refs", texto)
        self.assertNotIn("ventas", texto.replace("ventas-", ""))


# ---------------------------------------------------------------------------
# Evidencia v0.7 (R14, R24-R27)
# ---------------------------------------------------------------------------


class TestEvidenciaV07(BaseMundo):
    def test_evidencia_completa_es_complete_con_cada_pin_fresh(self):
        card = self.card_completa()
        self.assertEqual(modelcard.validate_model_card(card), [])
        ev = self.evaluar(card)
        self.assertEqual(ev.hallazgos, ())
        for eid in ("ev-dc-train", "ev-dc-test", "ev-res", "ev-pol", "ev-met", "ev-base", "ev-drift", "ev-exec"):
            with self.subTest(eid=eid):
                self.assertEqual(estado_ev(ev, eid), assess.EV_FRESH)
                self.assertEqual(estado_req(ev, "evidence_" + eid), assess.REQ_SATISFIED)
        self.assertEqual(ev.card_status, assess.CARD_COMPLETE)

    def test_requirements_for_derivados_por_pin(self):
        reqs = {r.requirement_id: r for r in modelcard.requirements_for(self.card_completa())}
        esperados = {
            "evidence_ev-dc-train": "data_card",
            "evidence_ev-dc-test": "data_card",
            "evidence_ev-res": "model_quality_result",
            "evidence_ev-pol": "model_quality_policy",
            "evidence_ev-met": "observed_metric",
            "evidence_ev-base": "baseline_reference",
            "evidence_ev-drift": "drift_evidence",
            "evidence_ev-exec": "execution_record",
        }
        for rid, kind in esperados.items():
            with self.subTest(rid=rid):
                self.assertEqual(reqs[rid].accepts, ("observed",))
                self.assertEqual(reqs[rid].accepted_kinds, (kind,))
                self.assertEqual(reqs[rid].severity, "recommended" if rid == "evidence_ev-exec" else "required")
        self.assertIn(modelcard.REQ_OWNERSHIP, reqs)
        self.assertEqual(len(reqs), len(esperados) + 1)

    def test_manifest_real_es_model_quality_evaluation(self):
        self.assertEqual(self.manifest.subject_kind, "model_quality_evaluation")
        self.assertEqual(self.pins["result"].content_sha256, resolvers.hash_quality_manifest(self.manifest.to_dict()))

    def test_metrica_alterada_deja_stale(self):
        metricas = self.leer_json(REL_MET)
        metricas[1]["value"] = 0.1  # otra entrada del mismo archivo (R26: documento completo)
        self.escribir_json(REL_MET, metricas)
        ev = self.evaluar(self.card_completa())
        self.assertEqual(estado_ev(ev, "ev-met"), assess.EV_STALE)
        self.assertEqual(estado_ev(ev, "ev-base"), assess.EV_FRESH)
        self.assertEqual(ev.card_status, assess.CARD_STALE)

    def test_metrica_propia_alterada_deja_stale(self):
        metricas = self.leer_json(REL_MET)
        metricas[0]["value"] = 0.2
        self.escribir_json(REL_MET, metricas)
        self.assertEqual(self.evaluar(self.card_completa()).card_status, assess.CARD_STALE)

    def test_baseline_alterada_deja_stale(self):
        baselines = self.leer_json(REL_BASE)
        baselines[0]["value"] = 0.1
        self.escribir_json(REL_BASE, baselines)
        ev = self.evaluar(self.card_completa())
        self.assertEqual(estado_ev(ev, "ev-base"), assess.EV_STALE)
        self.assertEqual(estado_ev(ev, "ev-met"), assess.EV_FRESH)
        self.assertEqual(ev.card_status, assess.CARD_STALE)

    def test_politica_modificada_deja_stale(self):
        politica = self.leer_json(REL_POL)
        politica["description"] = "Política editada"
        self.escribir_json(REL_POL, politica)
        ev = self.evaluar(self.card_completa())
        self.assertEqual(estado_ev(ev, "ev-pol"), assess.EV_STALE)
        self.assertEqual(estado_ev(ev, "ev-res"), assess.EV_FRESH)
        self.assertEqual(ev.card_status, assess.CARD_STALE)

    def test_politica_con_policy_id_interno_distinto_es_unverifiable(self):
        politica = self.leer_json(REL_POL)
        politica["policy_id"] = "otra-politica"
        self.escribir_json(REL_POL, politica)
        ev = self.evaluar(self.card_completa())
        self.assertEqual(estado_ev(ev, "ev-pol"), assess.EV_UNVERIFIABLE)
        self.assertEqual(ev.card_status, assess.CARD_INCOMPLETE)

    def test_politica_ausente_es_incomplete(self):
        (self.raiz / REL_POL).unlink()
        ev = self.evaluar(self.card_completa())
        self.assertEqual(estado_ev(ev, "ev-pol"), assess.EV_UNRESOLVABLE)
        self.assertEqual(ev.card_status, assess.CARD_INCOMPLETE)

    def test_manifest_ausente_es_incomplete_missing(self):
        (self.raiz / self.rel_manifest).unlink()
        res = resolvers.model_quality_result_resolver(self.raiz)(self.pins["result"])
        self.assertEqual(res.state, assess.RES_MISSING)
        ev = self.evaluar(self.card_completa())
        self.assertEqual(estado_ev(ev, "ev-res"), assess.EV_UNRESOLVABLE)
        self.assertEqual(ev.card_status, assess.CARD_INCOMPLETE)

    def test_manifest_adulterado_es_unverifiable(self):
        datos = self.leer_json(self.rel_manifest)
        datos["declaration"]["declaration_id"] = "otra-politica"
        self.escribir_json(self.rel_manifest, datos)
        ev = self.evaluar(self.card_completa())
        self.assertEqual(estado_ev(ev, "ev-res"), assess.EV_UNVERIFIABLE)
        self.assertEqual(ev.card_status, assess.CARD_INCOMPLETE)

    def test_manifest_de_data_contract_como_model_quality_result_es_unverifiable(self):
        decl = qe_core.DeclarationRef("data_contract", "mi-contrato", "1.0.0", "a" * 64)
        otro = qe_core.QualityEvidenceManifest(
            evidence_id="qe-20261001T100000Z-def456",
            subject_kind="data_contract_evaluation",
            declaration=decl,
            source=qe_evidence.describe_source_generated("conteo", {"n": 3}),
            generated_at=T0,
        )
        qe_evidence.write_manifest(self.raiz, otro)
        pin = core.EvidenceRef("ev-res", "model_quality_result", otro.evidence_id, otro.content_sha256(), T0)
        self.assertEqual(resolvers.model_quality_result_resolver(self.raiz)(pin).state, assess.RES_UNVERIFIABLE)
        card = armar_card(
            body_extra={"evaluation_refs": [{"evaluation_ref_id": "e", "result_evidence_id": "ev-res"}]},
            pins=[pin],
        )
        ev = self.evaluar(card)
        self.assertEqual(estado_ev(ev, "ev-res"), assess.EV_UNVERIFIABLE)
        self.assertEqual(ev.card_status, assess.CARD_INCOMPLETE)

    def test_result_ref_id_sin_patron_qe_es_ref_inconsistent(self):
        malo = self.repin("result", ref_id="resultado-1")
        card = armar_card(
            body_extra={"evaluation_refs": [{"evaluation_ref_id": "e", "result_evidence_id": "ev-res"}]},
            pins=[malo],
        )
        self.assertIn(modelcard.CODE_REF_INCONSISTENT, codigos(card))

    def test_drift_ref_id_sin_patron_dr_es_ref_inconsistent(self):
        malo = self.repin("drift", ref_id="drift-1")
        card = armar_card(
            body_extra={"evaluation_refs": [{"evaluation_ref_id": "e", "drift_evidence_ids": ["ev-drift"]}]},
            pins=[malo],
        )
        self.assertIn(modelcard.CODE_REF_INCONSISTENT, codigos(card))

    def test_drift_alterado_stale_y_generated_at_no_cuenta(self):
        datos = self.leer_json(REL_DRIFT)
        datos["generated_at"] = "2026-10-03T00:00:00Z"
        self.escribir_json(REL_DRIFT, datos)
        self.assertEqual(estado_ev(self.evaluar(self.card_completa()), "ev-drift"), assess.EV_FRESH)
        # alteración legítima: el contenido cambia y el content_sha256 persistido se recalcula
        datos["result_message"] = "mensaje editado"
        datos["content_sha256"] = resolvers.hash_drift(datos)
        self.escribir_json(REL_DRIFT, datos)
        ev = self.evaluar(self.card_completa())
        self.assertEqual(estado_ev(ev, "ev-drift"), assess.EV_STALE)
        self.assertEqual(ev.card_status, assess.CARD_STALE)

    def test_drift_alterado_sin_recalcular_content_sha256_es_unverifiable(self):
        datos = self.leer_json(REL_DRIFT)
        self.assertIn("content_sha256", datos)
        datos["result_message"] = "mensaje editado a mano"  # integridad rota
        self.escribir_json(REL_DRIFT, datos)
        ev = self.evaluar(self.card_completa())
        self.assertEqual(estado_ev(ev, "ev-drift"), assess.EV_UNVERIFIABLE)
        self.assertEqual(ev.card_status, assess.CARD_INCOMPLETE)

    def test_drift_solo_generated_at_no_cambia_nada(self):
        datos = self.leer_json(REL_DRIFT)
        datos["generated_at"] = "2026-10-03T00:00:00Z"
        self.escribir_json(REL_DRIFT, datos)
        ev = self.evaluar(self.card_completa())
        self.assertEqual(estado_ev(ev, "ev-drift"), assess.EV_FRESH)
        self.assertEqual(ev.card_status, assess.CARD_COMPLETE)

    def test_drift_id_interno_distinto_es_unverifiable(self):
        datos = self.leer_json(REL_DRIFT)
        datos["drift_id"] = "dr-20200101T000000Z-aaaaaa"
        self.escribir_json(REL_DRIFT, datos)
        self.assertEqual(estado_ev(self.evaluar(self.card_completa()), "ev-drift"), assess.EV_UNVERIFIABLE)

    def test_evaluation_ref_con_un_solo_pin_alcanza(self):
        for clave, nombre, valor in (
            ("result_evidence_id", "result", "ev-res"),
            ("policy_evidence_id", "policy", "ev-pol"),
            ("metric_evidence_ids", "metric", ["ev-met"]),
            ("baseline_evidence_ids", "baseline", ["ev-base"]),
            ("drift_evidence_ids", "drift", ["ev-drift"]),
        ):
            with self.subTest(clave=clave):
                card = armar_card(
                    body_extra={"evaluation_refs": [{"evaluation_ref_id": "e", clave: valor}]},
                    pins=[self.pins[nombre]],
                )
                self.assertEqual(modelcard.validate_model_card(card), [])
                self.assertEqual(self.evaluar(card).card_status, assess.CARD_COMPLETE)

    def test_evaluation_ref_sin_pines_es_invalida(self):
        card = armar_card(body_extra={"evaluation_refs": [{"evaluation_ref_id": "e", "role": "test"}]})
        self.assertIn(modelcard.CODE_BODY_INVALID, codigos(card))
        card = armar_card(body_extra={"evaluation_refs": [{"evaluation_ref_id": "e", "metric_evidence_ids": []}]})
        self.assertIn(modelcard.CODE_BODY_INVALID, codigos(card))

    def test_evaluation_ref_con_pin_de_kind_equivocado(self):
        card = armar_card(
            body_extra={"evaluation_refs": [{"evaluation_ref_id": "e", "result_evidence_id": "ev-pol"}]},
            pins=[self.pins["policy"]],
        )
        self.assertIn(modelcard.CODE_REF_INCONSISTENT, codigos(card))

    def test_evaluation_ref_colgante_y_duplicados(self):
        card = armar_card(
            body_extra={"evaluation_refs": [{"evaluation_ref_id": "e", "metric_evidence_ids": ["no-existe"]}]}
        )
        self.assertIn(modelcard.CODE_DANGLING_EVIDENCE, codigos(card))
        card = armar_card(
            body_extra={"evaluation_refs": [{"evaluation_ref_id": "e", "metric_evidence_ids": ["ev-met", "ev-met"]}]},
            pins=[self.pins["metric"]],
            claims=[claim_de("ev-met")],
        )
        self.assertIn(modelcard.CODE_REF_INCONSISTENT, codigos(card))
        refs = [
            {"evaluation_ref_id": "e", "metric_evidence_ids": ["ev-met"]},
            {"evaluation_ref_id": "e", "baseline_evidence_ids": ["ev-base"]},
        ]
        card = armar_card(body_extra={"evaluation_refs": refs}, pins=[self.pins["metric"], self.pins["baseline"]])
        self.assertIn(modelcard.CODE_REF_INCONSISTENT, codigos(card))

    def test_pin_metrico_sin_member_o_sin_locator_es_ref_inconsistent(self):
        sin_member = dataclasses.replace(self.pins["metric"], member=None)
        sin_locator = dataclasses.replace(self.pins["metric"], locator=None)
        for pin in (sin_member, sin_locator):
            with self.subTest(member=pin.member, locator=pin.locator):
                card = armar_card(
                    body_extra={"evaluation_refs": [{"evaluation_ref_id": "e", "metric_evidence_ids": ["ev-met"]}]},
                    pins=[pin],
                )
                self.assertIn(modelcard.CODE_REF_INCONSISTENT, codigos(card))

    def test_member_de_metrica_con_sintaxis_invalida_en_card_es_ref_inconsistent(self):
        for member in ("accuracy", "@ctx-test", "accuracy@", "a@b@c"):
            with self.subTest(member=member):
                pin = dataclasses.replace(self.pins["metric"], member=member)
                card = armar_card(
                    body_extra={"evaluation_refs": [{"evaluation_ref_id": "e", "metric_evidence_ids": ["ev-met"]}]},
                    pins=[pin],
                )
                self.assertIn(modelcard.CODE_REF_INCONSISTENT, codigos(card))

    def test_baseline_member_con_arroba_es_ref_inconsistent(self):
        pin = dataclasses.replace(self.pins["baseline"], member="bl@prev")
        card = armar_card(
            body_extra={"evaluation_refs": [{"evaluation_ref_id": "e", "baseline_evidence_ids": ["ev-base"]}]},
            pins=[pin],
        )
        self.assertIn(modelcard.CODE_REF_INCONSISTENT, codigos(card))

    def test_evidence_id_demasiado_largo_es_invalido(self):
        largo = "e" * 56
        pin = dataclasses.replace(self.pins["metric"], evidence_id=largo)
        card = armar_card(
            body_extra={"evaluation_refs": [{"evaluation_ref_id": "e", "metric_evidence_ids": [largo]}]},
            pins=[pin], claims=[],
        )
        self.assertIn(modelcard.CODE_BODY_INVALID, codigos(card))
        ok = dataclasses.replace(self.pins["metric"], evidence_id="e" * 55)
        card = armar_card(
            body_extra={"evaluation_refs": [{"evaluation_ref_id": "e", "metric_evidence_ids": ["e" * 55]}]},
            pins=[ok],
        )
        self.assertEqual(modelcard.validate_model_card(card), [])


# ---------------------------------------------------------------------------
# Member de métricas/baselines (R26)
# ---------------------------------------------------------------------------


class TestMemberSelector(BaseMundo):
    def resolver_metrica(self, pin):
        return resolvers.observed_metric_resolver(self.raiz)(pin)

    def resolver_baseline(self, pin):
        return resolvers.baseline_reference_resolver(self.raiz)(pin)

    def test_member_existente_resuelve_con_hash_del_documento(self):
        res = self.resolver_metrica(self.pins["metric"])
        self.assertEqual(res.state, assess.RES_FOUND)
        self.assertEqual(res.current_sha256, resolvers.hash_document(self.metricas))

    def test_member_inexistente_es_missing(self):
        for member in ("precision@ctx-test", "accuracy@ctx-otro", "recall@ctx-val"):
            with self.subTest(member=member):
                pin = dataclasses.replace(self.pins["metric"], member=member)
                self.assertEqual(self.resolver_metrica(pin).state, assess.RES_MISSING)
        pin = dataclasses.replace(self.pins["metric"], member="precision@ctx-test")
        card = armar_card(
            body_extra={"evaluation_refs": [{"evaluation_ref_id": "e", "metric_evidence_ids": ["ev-met"]}]},
            pins=[pin],
        )
        ev = self.evaluar(card)
        self.assertEqual(estado_ev(ev, "ev-met"), assess.EV_UNRESOLVABLE)
        self.assertEqual(ev.card_status, assess.CARD_INCOMPLETE)

    def test_metric_name_y_context_id_distinguen_entradas(self):
        for member in ("accuracy@ctx-test", "accuracy@ctx-val", "recall@ctx-test"):
            with self.subTest(member=member):
                pin = dataclasses.replace(self.pins["metric"], member=member)
                self.assertEqual(self.resolver_metrica(pin).state, assess.RES_FOUND)

    def test_duplicado_metric_name_context_id_es_unverifiable(self):
        duplicado = self.metricas + [mq.ObservedMetric("accuracy", 0.1, self.ctx_test).to_dict()]
        self.escribir_json(REL_MET, duplicado)
        pin = dataclasses.replace(self.pins["metric"], content_sha256=resolvers.hash_document(duplicado))
        self.assertEqual(self.resolver_metrica(pin).state, assess.RES_UNVERIFIABLE)
        # una entrada no duplicada del mismo documento sigue sin poder resolverse? solo el member ambiguo falla
        card = armar_card(
            body_extra={"evaluation_refs": [{"evaluation_ref_id": "e", "metric_evidence_ids": ["ev-met"]}]},
            pins=[pin],
        )
        ev = self.evaluar(card)
        self.assertEqual(estado_ev(ev, "ev-met"), assess.EV_UNVERIFIABLE)
        self.assertEqual(ev.card_status, assess.CARD_INCOMPLETE)

    def test_reordenar_la_lista_no_cambia_la_resolucion_del_member(self):
        invertida = list(reversed(self.metricas))
        self.escribir_json(REL_MET, invertida)
        res = self.resolver_metrica(self.pins["metric"])
        self.assertEqual(res.state, assess.RES_FOUND)
        self.assertEqual(res.current_sha256, resolvers.hash_document(invertida))
        for member in ("accuracy@ctx-test", "accuracy@ctx-val", "recall@ctx-test"):
            with self.subTest(member=member):
                pin = dataclasses.replace(self.pins["metric"], member=member)
                self.assertEqual(self.resolver_metrica(pin).state, assess.RES_FOUND)
        # con el pin recalculado sobre el documento reordenado, la Card sigue fresh
        pin = dataclasses.replace(self.pins["metric"], content_sha256=resolvers.hash_document(invertida))
        card = armar_card(
            body_extra={"evaluation_refs": [{"evaluation_ref_id": "e", "metric_evidence_ids": ["ev-met"]}]},
            pins=[pin],
        )
        self.assertEqual(self.evaluar(card).card_status, assess.CARD_COMPLETE)

    def test_sintaxis_invalida_de_member_es_unverifiable_en_el_resolver(self):
        for member in ("accuracy", "@ctx-test", "accuracy@", "a@b@c"):
            with self.subTest(member=member):
                pin = dataclasses.replace(self.pins["metric"], member=member)
                self.assertEqual(self.resolver_metrica(pin).state, assess.RES_UNVERIFIABLE)

    def test_member_ausente_es_unverifiable(self):
        pin = dataclasses.replace(self.pins["metric"], member=None)
        self.assertEqual(self.resolver_metrica(pin).state, assess.RES_UNVERIFIABLE)

    def test_documento_que_no_es_lista_es_unverifiable(self):
        self.escribir_json(REL_MET, {"metric_name": "accuracy"})
        self.assertEqual(self.resolver_metrica(self.pins["metric"]).state, assess.RES_UNVERIFIABLE)

    def test_entrada_con_identidad_malformada_es_unverifiable(self):
        for malformada in ({"metric_name": "accuracy"}, {"value": 1}, "texto", 5, None,
                           {"metric_name": "", "context": {"context_id": "c"}}):
            with self.subTest(entrada=malformada):
                self.escribir_json(REL_MET, self.metricas + [malformada])
                self.assertEqual(self.resolver_metrica(self.pins["metric"]).state, assess.RES_UNVERIFIABLE)

    def test_locator_ausente_y_archivo_inexistente(self):
        sin_locator = dataclasses.replace(self.pins["metric"], locator=None)
        self.assertEqual(self.resolver_metrica(sin_locator).state, assess.RES_UNVERIFIABLE)
        (self.raiz / REL_MET).unlink()
        self.assertEqual(self.resolver_metrica(self.pins["metric"]).state, assess.RES_MISSING)

    def test_json_invalido_y_nan_son_unverifiable(self):
        (self.raiz / REL_MET).write_text("[NaN]", encoding="utf-8")
        self.assertEqual(self.resolver_metrica(self.pins["metric"]).state, assess.RES_UNVERIFIABLE)
        (self.raiz / REL_MET).write_text("{no es json", encoding="utf-8")
        self.assertEqual(self.resolver_metrica(self.pins["metric"]).state, assess.RES_UNVERIFIABLE)

    def test_locator_que_escapa_no_resuelve(self):
        for locator in ("../fuera.json", "/abs/x.json", "a\\b.json", "C:/x.json"):
            with self.subTest(locator=locator):
                pin = dataclasses.replace(self.pins["metric"])
                objeto = type("Pin", (), {"member": pin.member, "locator": locator, "ref_id": "x"})()
                self.assertEqual(self.resolver_metrica(objeto).state, assess.RES_UNVERIFIABLE)

    def test_baseline_por_baseline_id(self):
        for bid in ("bl-prev", "bl-naive"):
            with self.subTest(baseline_id=bid):
                pin = dataclasses.replace(self.pins["baseline"], member=bid)
                res = self.resolver_baseline(pin)
                self.assertEqual(res.state, assess.RES_FOUND)
                self.assertEqual(res.current_sha256, resolvers.hash_document(self.baselines))
        pin = dataclasses.replace(self.pins["baseline"], member="bl-nope")
        self.assertEqual(self.resolver_baseline(pin).state, assess.RES_MISSING)

    def test_baseline_duplicado_es_unverifiable_y_reordenar_no_cambia(self):
        duplicado = self.baselines + [dict(self.baselines[0])]
        self.escribir_json(REL_BASE, duplicado)
        self.assertEqual(self.resolver_baseline(self.pins["baseline"]).state, assess.RES_UNVERIFIABLE)
        self.escribir_json(REL_BASE, list(reversed(self.baselines)))
        self.assertEqual(self.resolver_baseline(self.pins["baseline"]).state, assess.RES_FOUND)

    def test_baseline_con_identidad_malformada_es_unverifiable(self):
        self.escribir_json(REL_BASE, self.baselines + [{"metric_name": "accuracy"}])
        self.assertEqual(self.resolver_baseline(self.pins["baseline"]).state, assess.RES_UNVERIFIABLE)


# ---------------------------------------------------------------------------
# ExecutionRecord / provenance (R15, R28)
# ---------------------------------------------------------------------------


class TestProvenance(BaseMundo):
    def card_prov(self):
        return armar_card(
            body_extra={"provenance_refs": [{"provenance_ref_id": "prov-1", "evidence_id": "ev-exec"}]},
            pins=[self.pins["exec"]],
        )

    def test_execution_record_fresh(self):
        card = self.card_prov()
        self.assertEqual(modelcard.validate_model_card(card), [])
        ev = self.evaluar(card)
        self.assertEqual(estado_ev(ev, "ev-exec"), assess.EV_FRESH)
        self.assertEqual(estado_req(ev, "evidence_ev-exec"), assess.REQ_SATISFIED)

    def test_execution_record_missing(self):
        (self.raiz / self.rel_exec).unlink()
        ev = self.evaluar(self.card_prov())
        self.assertEqual(estado_ev(ev, "ev-exec"), assess.EV_UNRESOLVABLE)
        # provenance es recomendada: no degrada la Card
        self.assertEqual(estado_req(ev, "evidence_ev-exec"), assess.REQ_UNRESOLVABLE)

    def test_execution_record_modificado_es_stale_y_generated_at_no_cuenta(self):
        datos = self.leer_json(self.rel_exec)
        datos["generated_at"] = "2026-10-03T00:00:00Z"
        self.escribir_json(self.rel_exec, datos)
        self.assertEqual(estado_ev(self.evaluar(self.card_prov()), "ev-exec"), assess.EV_FRESH)
        datos["exit_code"] = 1
        self.escribir_json(self.rel_exec, datos)
        self.assertEqual(estado_ev(self.evaluar(self.card_prov()), "ev-exec"), assess.EV_STALE)

    def test_execution_id_interno_distinto_es_unverifiable(self):
        datos = self.leer_json(self.rel_exec)
        datos["execution_id"] = "script__bbbbbbbbbbbb"
        self.escribir_json(self.rel_exec, datos)
        self.assertEqual(estado_ev(self.evaluar(self.card_prov()), "ev-exec"), assess.EV_UNVERIFIABLE)

    def test_provenance_es_recomendada_y_no_degrada_la_card(self):
        card = self.card_completa()
        (self.raiz / self.rel_exec).unlink()
        ev = self.evaluar(card)
        self.assertEqual(ev.card_status, assess.CARD_COMPLETE)

    def test_provenance_con_report_artifact_queda_unverifiable_sin_resolver(self):
        pin = core.EvidenceRef("ev-rep", "report_artifact", "informe-1", "c" * 64, T0)
        card = armar_card(
            body_extra={"provenance_refs": [{"provenance_ref_id": "prov-1", "evidence_id": "ev-rep"}]}, pins=[pin]
        )
        self.assertEqual(modelcard.validate_model_card(card), [])
        self.assertEqual(estado_ev(self.evaluar(card), "ev-rep"), assess.EV_UNVERIFIABLE)

    def test_provenance_con_pin_de_otro_kind_es_ref_inconsistent(self):
        card = armar_card(
            body_extra={"provenance_refs": [{"provenance_ref_id": "prov-1", "evidence_id": "ev-met"}]},
            pins=[self.pins["metric"]],
        )
        self.assertIn(modelcard.CODE_REF_INCONSISTENT, codigos(card))

    def test_pin_execution_record_citado_como_resultado_es_ref_inconsistent(self):
        body = {
            "provenance_refs": [{"provenance_ref_id": "prov-1", "evidence_id": "ev-exec"}],
            "evaluation_refs": [{"evaluation_ref_id": "e", "result_evidence_id": "ev-exec"}],
        }
        card = armar_card(body_extra=body, pins=[self.pins["exec"]])
        self.assertIn(modelcard.CODE_REF_INCONSISTENT, codigos(card))

    def test_provenance_ref_id_duplicado(self):
        refs = [
            {"provenance_ref_id": "prov-1", "evidence_id": "ev-exec"},
            {"provenance_ref_id": "prov-1", "evidence_id": "ev-exec"},
        ]
        card = armar_card(body_extra={"provenance_refs": refs}, pins=[self.pins["exec"]], claims=[claim_de("ev-exec")])
        self.assertIn(modelcard.CODE_REF_INCONSISTENT, codigos(card))


# ---------------------------------------------------------------------------
# Atestaciones (R18-R21, R39)
# ---------------------------------------------------------------------------


class TestAtestaciones(BaseMundo):
    def test_ownership_declared_satisface(self):
        card = armar_card(attestations=[hacer_att()], claims=[claim_ownership()])
        self.assertEqual(modelcard.validate_model_card(card), [])
        ev = self.evaluar(card)
        self.assertEqual(estado_req(ev, modelcard.REQ_OWNERSHIP), assess.REQ_SATISFIED)

    def test_ownership_anchored_estructural(self):
        att = hacer_att(
            attestation_kind="anchored",
            approval_ref={"change_id": "20261005-model-cards", "artefacto": "spec.md", "hash": "b" * 64},
        )
        card = armar_card(attestations=[att], claims=[claim_ownership()])
        self.assertEqual(modelcard.validate_model_card(card), [])
        ev = self.evaluar(card)
        self.assertEqual(estado_req(ev, modelcard.REQ_OWNERSHIP), assess.REQ_SATISFIED)
        # nada verifica el ancla contra un ledger: ningún mensaje afirma verificación
        textos = " ".join(str(d) for r in ev.requisitos for d in r) + " ".join(h.detail for h in ev.hallazgos)
        self.assertNotIn("verified", textos.lower())
        self.assertNotIn("verificad", textos.lower())

    def test_ownership_ausente_es_warn_no_degrada(self):
        ev = self.evaluar(self.card_completa())
        self.assertEqual(estado_req(ev, modelcard.REQ_OWNERSHIP), assess.REQ_MISSING)
        self.assertEqual(ev.card_status, assess.CARD_COMPLETE)

    def test_claim_ownership_apoyado_en_evidencia_es_inconsistente(self):
        card = armar_card(
            body_extra={"evaluation_refs": [{"evaluation_ref_id": "e", "metric_evidence_ids": ["ev-met"]}]},
            pins=[self.pins["metric"]],
            claims=[claim_de("ev-met"), claim_ownership(supports=("ev-met",))],
        )
        self.assertIn(modelcard.CODE_CLAIM_SUPPORT_INCONSISTENT, codigos(card))

    def test_atestacion_no_satisface_ningun_requisito_evidence_por_kind(self):
        casos = (
            ("data_card", "dc_train"),
            ("model_quality_result", "result"),
            ("model_quality_policy", "policy"),
            ("observed_metric", "metric"),
            ("baseline_reference", "baseline"),
            ("drift_evidence", "drift"),
            ("execution_record", "exec"),
        )
        card_base = self.card_completa()
        for kind, nombre in casos:
            with self.subTest(kind=kind):
                eid = self.pins[nombre].evidence_id
                claims = [c for c in card_base.claims if c.requirement_id != "evidence_" + eid]
                claims.append(claim_de(eid, soportes=("at-own",)))
                card = dataclasses.replace(
                    card_base, claims=tuple(claims), attestations=(hacer_att(),)
                )
                # (a) hook permisivo: el requisito no se satisface
                reqs = modelcard.requirements_for(card)
                ev = assess.evaluate(
                    card, reqs, resolvers.default_resolvers(self.raiz), validate_body=lambda body: []
                )
                self.assertEqual(estado_req(ev, "evidence_" + eid), assess.REQ_UNTRUSTED_TYPE)
                # (b) con el validador real: claim inconsistente => invalid
                self.assertIn(modelcard.CODE_CLAIM_SUPPORT_INCONSISTENT, codigos(card))
                real = self.evaluar(card)
                self.assertEqual(real.card_status, assess.CARD_INVALID)
                self.assertIn(modelcard.CODE_CLAIM_SUPPORT_INCONSISTENT, {h.code for h in real.hallazgos})

    def test_requisitos_required_con_solo_atestacion_dejan_incomplete_en_hook_permisivo(self):
        card_base = self.card_completa()
        claims = [c for c in card_base.claims if c.requirement_id != "evidence_ev-met"]
        claims.append(claim_de("ev-met", soportes=("at-own",)))
        card = dataclasses.replace(card_base, claims=tuple(claims), attestations=(hacer_att(),))
        ev = assess.evaluate(
            card, modelcard.requirements_for(card), resolvers.default_resolvers(self.raiz),
            validate_body=lambda body: [],
        )
        self.assertEqual(ev.card_status, assess.CARD_INCOMPLETE)

    def test_atestacion_mas_evidencia_fresh_tampoco_se_acepta_como_claim_mixto(self):
        card_base = self.card_completa()
        claims = [c for c in card_base.claims if c.requirement_id != "evidence_ev-met"]
        claims.append(claim_de("ev-met", soportes=("ev-met", "at-own")))
        card = dataclasses.replace(card_base, claims=tuple(claims), attestations=(hacer_att(),))
        self.assertIn(modelcard.CODE_CLAIM_SUPPORT_INCONSISTENT, codigos(card))


# ---------------------------------------------------------------------------
# Contaminación cruzada de evidencia (B1)
# ---------------------------------------------------------------------------


class TestContaminacionCruzada(BaseMundo):
    def con_claim(self, eid, soportes):
        base = self.card_completa()
        claims = [c for c in base.claims if c.requirement_id != "evidence_" + eid]
        claims.append(claim_de(eid, soportes=soportes))
        return dataclasses.replace(base, claims=tuple(claims))

    def test_claim_de_a_apoyado_en_b_es_inconsistente(self):
        for a, b in (("ev-res", "ev-pol"), ("ev-met", "ev-base"), ("ev-dc-train", "ev-dc-test"),
                     ("ev-drift", "ev-met"), ("ev-pol", "ev-res")):
            with self.subTest(a=a, b=b):
                card = self.con_claim(a, (b,))
                self.assertIn(modelcard.CODE_CLAIM_SUPPORT_INCONSISTENT, codigos(card))
                self.assertEqual(self.evaluar(card).card_status, assess.CARD_INVALID)

    def test_claim_con_supports_stale_y_fresh_es_inconsistente(self):
        # ev-pol stale (archivo editado), ev-res fresh: el claim de ev-pol no puede apoyarse en (ev-pol, ev-res)
        politica = self.leer_json(REL_POL)
        politica["description"] = "editada"
        self.escribir_json(REL_POL, politica)
        card = self.con_claim("ev-pol", ("ev-pol", "ev-res"))
        self.assertIn(modelcard.CODE_CLAIM_SUPPORT_INCONSISTENT, codigos(card))
        self.assertEqual(self.evaluar(card).card_status, assess.CARD_INVALID)
        card = self.con_claim("ev-pol", ("ev-res", "ev-pol"))
        self.assertIn(modelcard.CODE_CLAIM_SUPPORT_INCONSISTENT, codigos(card))

    def test_claim_sin_supports_o_con_supports_duplicado_es_inconsistente(self):
        for soportes in ((), ("ev-met", "ev-met")):
            with self.subTest(soportes=soportes):
                self.assertIn(modelcard.CODE_CLAIM_SUPPORT_INCONSISTENT, codigos(self.con_claim("ev-met", soportes)))

    def test_claim_de_pin_no_citado_o_requisito_desconocido_es_inconsistente(self):
        base = self.card_completa()
        extra = core.Claim("c-x", "x", supports=("ev-met",), requirement_id="evidence_ev-no-citado")
        self.assertIn(modelcard.CODE_CLAIM_SUPPORT_INCONSISTENT,
                      codigos(dataclasses.replace(base, claims=base.claims + (extra,))))
        extra = core.Claim("c-y", "y", supports=("ev-met",), requirement_id="requisito-inventado")
        self.assertIn(modelcard.CODE_CLAIM_SUPPORT_INCONSISTENT,
                      codigos(dataclasses.replace(base, claims=base.claims + (extra,))))

    def test_claim_de_pin_existente_pero_no_citado_por_el_body_es_inconsistente(self):
        card = armar_card(
            body_extra={"evaluation_refs": [{"evaluation_ref_id": "e", "metric_evidence_ids": ["ev-met"]}]},
            pins=[self.pins["metric"], self.pins["baseline"]],
        )
        self.assertIn(modelcard.CODE_CLAIM_SUPPORT_INCONSISTENT, codigos(card))

    def test_claims_sin_requirement_id_son_libres(self):
        base = self.card_completa()
        libre = core.Claim("c-libre", "Texto libre", supports=("ev-met", "ev-base"))
        card = dataclasses.replace(base, claims=base.claims + (libre,))
        self.assertEqual(modelcard.validate_model_card(card), [])
        self.assertEqual(self.evaluar(card).card_status, assess.CARD_COMPLETE)

    def test_stale_de_un_pin_no_queda_tapado_por_pins_frescos(self):
        politica = self.leer_json(REL_POL)
        politica["description"] = "editada"
        self.escribir_json(REL_POL, politica)
        ev = self.evaluar(self.card_completa())
        self.assertEqual(estado_ev(ev, "ev-pol"), assess.EV_STALE)
        for otro in ("ev-res", "ev-met", "ev-base", "ev-drift", "ev-dc-train", "ev-dc-test"):
            self.assertEqual(estado_ev(ev, otro), assess.EV_FRESH)
        self.assertEqual(estado_req(ev, "evidence_ev-pol"), assess.REQ_STALE)
        self.assertEqual(ev.card_status, assess.CARD_STALE)

    def test_missing_de_un_pin_no_queda_tapado(self):
        (self.raiz / REL_DRIFT).unlink()
        ev = self.evaluar(self.card_completa())
        self.assertEqual(estado_req(ev, "evidence_ev-drift"), assess.REQ_UNRESOLVABLE)
        self.assertEqual(ev.card_status, assess.CARD_INCOMPLETE)

    def test_unverifiable_de_un_pin_no_queda_tapado(self):
        (self.raiz / REL_BASE).write_text("{no es json", encoding="utf-8")
        ev = self.evaluar(self.card_completa())
        self.assertEqual(estado_req(ev, "evidence_ev-base"), assess.REQ_UNVERIFIABLE)
        self.assertEqual(ev.card_status, assess.CARD_INCOMPLETE)

    def test_stale_y_missing_a_la_vez_gana_stale(self):
        politica = self.leer_json(REL_POL)
        politica["description"] = "editada"
        self.escribir_json(REL_POL, politica)
        (self.raiz / REL_DRIFT).unlink()
        self.assertEqual(self.evaluar(self.card_completa()).card_status, assess.CARD_STALE)

    def test_requisito_de_cada_pin_es_independiente(self):
        # Dos pins sobre el mismo archivo (metric y otro member): cada uno con su claim propio
        otro = dataclasses.replace(self.pins["metric"], evidence_id="ev-met2", member="recall@ctx-test")
        card = armar_card(
            body_extra={"evaluation_refs": [
                {"evaluation_ref_id": "e", "metric_evidence_ids": ["ev-met", "ev-met2"]}]},
            pins=[self.pins["metric"], otro],
        )
        self.assertEqual(modelcard.validate_model_card(card), [])
        ev = self.evaluar(card)
        self.assertEqual(estado_req(ev, "evidence_ev-met"), assess.REQ_SATISFIED)
        self.assertEqual(estado_req(ev, "evidence_ev-met2"), assess.REQ_SATISFIED)
        self.assertEqual(ev.card_status, assess.CARD_COMPLETE)


# ---------------------------------------------------------------------------
# Body (R11-R17)
# ---------------------------------------------------------------------------


class TestBody(BaseTmp):
    def test_obligatorios_ausentes(self):
        for clave in ("model_id", "model_version", "description"):
            with self.subTest(clave=clave):
                self.assertIn(modelcard.CODE_BODY_INVALID, codigos(sin_clave(armar_card(), clave)))

    def test_description_vacia_o_no_str(self):
        for valor in ("", "   ", "\n", None, 5, ["x"]):
            with self.subTest(valor=valor):
                self.assertIn(modelcard.CODE_BODY_INVALID, codigos(con_body(armar_card(), description=valor)))

    def test_body_no_dict_via_hook(self):
        validar = modelcard.body_validator_for(armar_card())
        for valor in (None, [], "x", 5):
            with self.subTest(valor=valor):
                self.assertIn(modelcard.CODE_BODY_INVALID, {h.code for h in validar(valor)})

    def test_claves_desconocidas(self):
        for clave in ("inventada", "model_path", "artifact_path", "uri", "framework", "format", "metrics", "status",
                      "requirements", "version", "name"):
            with self.subTest(clave=clave):
                self.assertIn(modelcard.CODE_UNKNOWN_KEY, codigos(con_body(armar_card(), **{clave: "x"})))

    def test_claves_rai_rechazadas(self):
        for clave in ("risk_level", "fairness", "explainability", "privacy", "security", "accountability",
                      "human_oversight"):
            with self.subTest(clave=clave):
                card = con_body(armar_card(), **{clave: "high"})
                self.assertIn(modelcard.CODE_UNKNOWN_KEY, codigos(card))
                self.assertEqual(self.evaluar(card).card_status, assess.CARD_INVALID)

    def test_claves_rai_rechazadas_tambien_en_subobjetos(self):
        card = con_body(armar_card(), task={"role": "classification", "risk_level": "high"})
        self.assertIn(modelcard.CODE_UNKNOWN_KEY, codigos(card))
        card = con_body(armar_card(), stewardship={"owner": "equipo", "human_oversight": "si"})
        self.assertIn(modelcard.CODE_UNKNOWN_KEY, codigos(card))

    def test_extensiones_x_permitidas_y_no_son_governance(self):
        base = armar_card()
        card = con_body(base, x_riesgo="alto", x_framework="sklearn", x_extra={"a": [1, "dos"]})
        self.assertEqual(modelcard.validate_model_card(card), [])
        ev, ev_base = self.evaluar(card), self.evaluar(base)
        self.assertEqual(ev.card_status, ev_base.card_status)
        self.assertEqual(ev.requisitos, ev_base.requisitos)
        self.assertEqual(
            [r.requirement_id for r in modelcard.requirements_for(card)],
            [r.requirement_id for r in modelcard.requirements_for(base)],
        )

    def test_extensiones_x_con_rutas_o_dsn_se_rechazan(self):
        for valor in ("/modelos/m.pkl", "~/m.pkl", "C:\\modelos\\m.pkl", "s3://bucket/m", "postgresql://u:p@h/db",
                      "password=abc", "a\\b", {"anidado": "/etc/passwd"}, ["ok", "C:\\x"]):
            with self.subTest(valor=valor):
                self.assertIn(core.CODE_LOCATOR_NOT_PORTABLE, codigos(con_body(armar_card(), x_cosa=valor)))

    def test_task_role_libre(self):
        for rol in ("forecasting", "custom_role", "regression", "classification", "anomaly_detection2"):
            with self.subTest(rol=rol):
                card = con_body(armar_card(), task={"role": rol, "description": "Predice demanda"})
                self.assertEqual(modelcard.validate_model_card(card), [])

    def test_task_role_invalido(self):
        for rol in ("", "Forecasting", "1x", "con espacio", "a-b", "_x", None, 5):
            with self.subTest(rol=rol):
                self.assertIn(modelcard.CODE_BODY_INVALID, codigos(con_body(armar_card(), task={"role": rol})))

    def test_task_sin_role_o_con_clave_desconocida(self):
        self.assertIn(modelcard.CODE_BODY_INVALID, codigos(con_body(armar_card(), task={"description": "x"})))
        self.assertIn(modelcard.CODE_UNKNOWN_KEY, codigos(con_body(armar_card(), task={"role": "ranking", "z": 1})))
        self.assertIn(modelcard.CODE_BODY_INVALID, codigos(con_body(armar_card(), task="ranking")))

    def test_task_completa(self):
        task = {"role": "ranking", "description": "Ordena ofertas", "target_reference": "columna objetivo del caso",
                "output_meaning": "Mayor es mejor posicionado"}
        self.assertEqual(modelcard.validate_model_card(con_body(armar_card(), task=task)), [])

    def test_campos_descriptivos_opcionales_validos(self):
        card = con_body(
            armar_card(),
            population="Clientes activos",
            intended_uses=["Priorizar llamadas"],
            out_of_scope_uses=["Decisiones automáticas de crédito"],
            known_limitations=["No cubre clientes nuevos"],
            stewardship={"owner": "equipo-datos", "steward": "analista senior"},
        )
        self.assertEqual(modelcard.validate_model_card(card), [])

    def test_listas_de_texto_invalidas(self):
        for clave in ("intended_uses", "out_of_scope_uses", "known_limitations"):
            for valor in ("no es lista", [""], [5], ["/ruta/absoluta"]):
                with self.subTest(clave=clave, valor=valor):
                    self.assertTrue(codigos(con_body(armar_card(), **{clave: valor})))

    def test_stewardship_con_arroba_rechazado(self):
        for stew in ({"owner": "ana@empresa.com"}, {"owner": "equipo", "steward": "bob@x.org"}):
            with self.subTest(stew=stew):
                self.assertIn(modelcard.CODE_BODY_INVALID, codigos(con_body(armar_card(), stewardship=stew)))

    def test_stewardship_sin_owner_o_malformado(self):
        for stew in ({}, {"steward": "x"}, "equipo", {"owner": ""}, {"owner": "e", "extra": 1}):
            with self.subTest(stew=stew):
                self.assertTrue(codigos(con_body(armar_card(), stewardship=stew)))

    def test_tecnologia_neutral_sin_campos_de_ruta_de_modelo(self):
        for clave in ("model_path", "artifact", "artifact_uri", "weights", "pickle", "onnx", "mlflow_uri",
                      "serialized_model", "framework", "library"):
            with self.subTest(clave=clave):
                self.assertIn(modelcard.CODE_UNKNOWN_KEY, codigos(con_body(armar_card(), **{clave: "x"})))
        self.assertEqual(modelcard.validate_model_card(con_body(armar_card(), x_framework="sklearn")), [])
        self.assertEqual(modelcard.validate_model_card(con_body(armar_card(), x_framework="onnx")), [])

    def test_rutas_fisicas_y_dsn_en_texto_se_rechazan(self):
        for texto in ("/modelos/m.pkl", "~/m.pkl", "C:\\modelos\\m.pkl", "mlflow://runs/1", "s3://b/m.onnx",
                      "a\\b", "postgresql://user:pw@host/db", "token=abc123"):
            for clave in ("description", "population"):
                with self.subTest(texto=texto, clave=clave):
                    self.assertTrue(codigos(con_body(armar_card(), **{clave: texto})))

    def test_schema_ajeno_y_kind_ajeno(self):
        base = armar_card()
        self.assertIn(modelcard.CODE_SCHEMA_UNSUPPORTED, codigos(dataclasses.replace(base, kind_schema_version=2)))
        self.assertIn(modelcard.CODE_KIND_INVALID, codigos(dataclasses.replace(base, card_kind="data_card")))
        self.assertEqual(self.evaluar(dataclasses.replace(base, kind_schema_version=2)).card_status,
                         assess.CARD_INVALID)
        self.assertEqual(self.evaluar(dataclasses.replace(base, card_kind="data_card")).card_status,
                         assess.CARD_INVALID)

    def test_validate_model_card_no_lanza_con_entradas_raras(self):
        for valor in (None, {}, "x", 5, []):
            with self.subTest(valor=valor):
                self.assertTrue(modelcard.validate_model_card(valor))

    def test_listas_de_refs_malformadas(self):
        for clave in ("data_card_refs", "evaluation_refs", "provenance_refs"):
            for valor in ("x", {}, [5], [None], [[]]):
                with self.subTest(clave=clave, valor=valor):
                    self.assertIn(modelcard.CODE_BODY_INVALID, codigos(con_body(armar_card(), **{clave: valor})))

    def test_refs_con_claves_desconocidas_o_faltantes(self):
        self.assertIn(modelcard.CODE_UNKNOWN_KEY, codigos(con_body(armar_card(), data_card_refs=[
            {"data_card_ref_id": "d", "role": "training", "evidence_id": "e", "extra": 1}])))
        self.assertIn(modelcard.CODE_BODY_INVALID, codigos(con_body(armar_card(), data_card_refs=[
            {"data_card_ref_id": "d", "evidence_id": "e"}])))
        self.assertIn(modelcard.CODE_BODY_INVALID, codigos(con_body(armar_card(), provenance_refs=[
            {"evidence_id": "e"}])))
        self.assertIn(modelcard.CODE_BODY_INVALID, codigos(con_body(armar_card(), evaluation_refs=[{}])))

    def test_body_validator_for_no_card_es_fail_closed(self):
        validar = modelcard.body_validator_for(None)
        self.assertTrue(validar({}))

    def evaluar(self, card):
        return modelcard.evaluate_model_card(card, self.raiz)


# ---------------------------------------------------------------------------
# Serialización, determinismo, archivos y neutralidad semántica (R22, R35, R36)
# ---------------------------------------------------------------------------


class TestSerializacionYEvaluacion(BaseMundo):
    def test_serializacion_determinista(self):
        card = self.card_completa()
        a = Path(tempfile.mkdtemp(dir=self.raiz))
        b = Path(tempfile.mkdtemp(dir=self.raiz))
        pa = modelcard.write_model_card(a, card, clock=lambda: NOW)
        pb = modelcard.write_model_card(b, card, clock=lambda: NOW)
        self.assertEqual(pa.read_bytes(), pb.read_bytes())
        self.assertTrue(pa.read_bytes().endswith(b"\n"))

    def test_archivo_sin_status_ni_requisitos(self):
        ruta = modelcard.write_model_card(self.raiz, self.card_completa(), clock=lambda: NOW)
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        self.assertNotIn("status", datos)
        self.assertNotIn("requirements", datos)
        self.assertNotIn("card_status", datos)
        self.assertIn("revision_id", datos)

    def test_round_trip_evaluate_identico(self):
        card = self.card_completa()
        ruta = modelcard.write_model_card(self.raiz, card, clock=lambda: NOW)
        leida = assess.read_card(ruta)
        self.assertEqual(leida.to_dict(), card.to_dict())
        directo = modelcard.evaluate_model_card(card, self.raiz).a_dict()
        desde_archivo = modelcard.evaluate_model_card(ruta, self.raiz).a_dict()
        desde_str = modelcard.evaluate_model_card(str(ruta), self.raiz).a_dict()
        self.assertEqual(directo, desde_archivo)
        self.assertEqual(directo, desde_str)
        self.assertEqual(directo["card_status"], assess.CARD_COMPLETE)

    def test_evaluar_dos_veces_da_lo_mismo(self):
        card = self.card_completa()
        self.assertEqual(self.evaluar(card).a_dict(), self.evaluar(card).a_dict())

    def test_archivo_mal_formado_es_invalid_sin_excepcion(self):
        casos = {
            "basura": b"esto no es json",
            "vacio": b"",
            "binario": b"\xff\xfe\x00\x01",
            "lista": b"[]",
            "nan": b'{"schema_version": NaN}',
            "con_status": json.dumps(dict(self.card_completa().to_dict(), status="complete")).encode("utf-8"),
            "clave_extra": json.dumps(dict(self.card_completa().to_dict(), inventada=1)).encode("utf-8"),
            "revision_adulterada": json.dumps(
                dict(self.card_completa().to_dict(con_revision=True), revision_id="x__000000000000")
            ).encode("utf-8"),
        }
        for nombre, contenido in casos.items():
            with self.subTest(caso=nombre):
                ruta = self.raiz / f"{nombre}.json"
                ruta.write_bytes(contenido)
                ev = modelcard.evaluate_model_card(ruta, self.raiz)
                self.assertEqual(ev.card_status, assess.CARD_INVALID)
                self.assertTrue(ev.hallazgos)

    def test_ruta_inexistente_o_directorio_es_invalid(self):
        self.assertEqual(modelcard.evaluate_model_card(self.raiz / "no-existe.json", self.raiz).card_status,
                         assess.CARD_INVALID)
        self.assertEqual(modelcard.evaluate_model_card(self.raiz, self.raiz).card_status, assess.CARD_INVALID)
        self.assertEqual(modelcard.evaluate_model_card(None, self.raiz).card_status, assess.CARD_INVALID)

    def test_card_invalida_no_evalua_evidencia(self):
        card = con_body(self.card_completa(), risk_level="high")
        ev = modelcard.evaluate_model_card(card, self.raiz)
        self.assertEqual(ev.card_status, assess.CARD_INVALID)
        self.assertEqual(ev.evidencias, ())

    def test_valores_de_metricas_no_cambian_el_estado(self):
        def estado_con(valores):
            for entrada, valor in zip(self.metricas, valores):
                entrada["value"] = valor
            self.escribir_json(REL_MET, self.metricas)
            pins = dict(self.pins)
            pins["metric"] = dataclasses.replace(pins["metric"], content_sha256=resolvers.hash_document(self.metricas))
            card = armar_card(body_extra=self.body_completo(), pins=list(pins.values()))
            return self.evaluar(card).a_dict()

        buenos = estado_con([0.99, 0.99, 0.99])
        malos = estado_con([-1000.0, 0.0, 1e12])
        self.assertEqual(buenos, malos)
        self.assertEqual(buenos["card_status"], assess.CARD_COMPLETE)

    def test_ninguna_conclusion_semantica_en_la_salida(self):
        ev = self.evaluar(self.card_completa()).a_dict()
        claves = set(ev) | {k for r in ev["requisitos"] for k in r}
        for prohibida in ("good", "bad", "pass", "quality", "score", "approved", "risk", "fair"):
            self.assertFalse([k for k in claves if prohibida in k.lower()], prohibida)
        estados_validos = set(assess.ESTADOS_REQUISITO)
        for r in ev["requisitos"]:
            self.assertIn(r["state"], estados_validos)
        self.assertIn(ev["card_status"], assess.PRECEDENCIA_CARD)

    def test_requirements_for_no_lee_valores_de_metricas(self):
        # Mismos requisitos aunque el archivo de métricas no exista o contenga valores arbitrarios
        antes = [(r.requirement_id, r.severity) for r in modelcard.requirements_for(self.card_completa())]
        (self.raiz / REL_MET).unlink()
        despues = [(r.requirement_id, r.severity) for r in modelcard.requirements_for(self.card_completa())]
        self.assertEqual(antes, despues)

    def test_card_a_dict_sin_valores_de_metricas_copiados(self):
        texto = json.dumps(self.card_completa().to_dict())
        for metrica in self.metricas:
            self.assertNotIn(f'"value": {metrica["value"]}', texto)

    def test_hooks_no_dependen_del_reloj_del_sistema(self):
        ev1 = modelcard.evaluate_model_card(self.card_completa(), self.raiz, clock=lambda: NOW)
        ev2 = modelcard.evaluate_model_card(self.card_completa(), self.raiz, clock=lambda: "2030-01-01T00:00:00Z")
        self.assertEqual(ev1.a_dict(), ev2.a_dict())

    def test_atestacion_futura_es_invalid_con_clock(self):
        att = hacer_att(attested_at="2027-01-01T00:00:00Z")
        card = armar_card(attestations=[att], claims=[claim_ownership()])
        ev = modelcard.evaluate_model_card(card, self.raiz, clock=lambda: NOW)
        self.assertEqual(ev.card_status, assess.CARD_INVALID)


class TestResolversMapa(BaseMundo):
    def test_default_resolvers_cubre_doce_kinds_y_no_report_artifact(self):
        mapa = resolvers.default_resolvers(self.raiz)
        for kind in ("data_card", "model_quality_result", "model_quality_policy", "observed_metric",
                     "baseline_reference", "drift_evidence", "execution_record"):
            self.assertIn(kind, mapa)
        self.assertNotIn("report_artifact", mapa)
        self.assertEqual(len(mapa), 12)

    def test_resolvers_nunca_lanzan(self):
        mapa = resolvers.default_resolvers(self.raiz)
        pin = core.EvidenceRef("ev-x", "observed_metric", "x-inexistente", "d" * 64, T0, member="a@b", locator="x.json")
        for kind in ("data_card", "model_quality_result", "model_quality_policy", "observed_metric",
                     "baseline_reference", "drift_evidence", "execution_record"):
            with self.subTest(kind=kind):
                res = mapa[kind](dataclasses.replace(pin, kind=kind))
                self.assertIn(res.state, assess.ESTADOS_RESOLUCION)
                self.assertNotEqual(res.state, assess.RES_FOUND)
                self.assertIsNone(res.current_sha256)
                self.assertIsInstance(mapa[kind](object()), assess.Resolution)

    def test_hashes_publicos_coherentes_con_los_objetos_reales(self):
        self.assertEqual(resolvers.hash_policy(self.politica_obj.to_dict()), resolvers.hash_policy(self.politica))
        self.assertEqual(resolvers.hash_drift(self.drift.to_dict()), resolvers.hash_drift(self.leer_json(REL_DRIFT)))
        self.assertEqual(
            resolvers.hash_execution_record(self.registro.to_dict()),
            resolvers.hash_execution_record(self.leer_json(self.rel_exec)),
        )
        self.assertEqual(resolvers.hash_document(self.metricas), resolvers.hash_document(self.leer_json(REL_MET)))

    def test_data_card_pin_con_ref_id_malformado_o_ausente(self):
        pin = self.pins["dc_train"]
        for ref_id in ("ventas-train", "../ventas-train__aaaaaaaaaaaa", "ventas-train__ZZZZZZZZZZZZ"):
            with self.subTest(ref_id=ref_id):
                obj = type("Pin", (), {"ref_id": ref_id, "locator": None})()
                self.assertEqual(resolvers.data_card_resolver(self.raiz)(obj).state, assess.RES_UNVERIFIABLE)
        ausente = type("Pin", (), {"ref_id": "no-hay__aaaaaaaaaaaa", "locator": None})()
        self.assertEqual(resolvers.data_card_resolver(self.raiz)(ausente).state, assess.RES_MISSING)
        self.assertEqual(resolvers.data_card_resolver(self.raiz)(pin).state, assess.RES_FOUND)


if __name__ == "__main__":
    unittest.main()

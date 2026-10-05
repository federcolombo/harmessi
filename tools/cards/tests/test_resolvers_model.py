"""Tests de los resolvers de Model Cards en `tools/cards/resolvers.py`
(Change `20261005-model-cards`, R23-R31, R37).

Usan OBJETOS REALES en directorios temporales: Data Cards escritas con
`datacard.write_data_card`, manifests de `qualityevidence`, `ModelQualityPolicy`,
`ObservedMetric`, `BaselineReference`, `DriftEvidence` y `ExecutionRecord`
(`leadrun`), siempre serializados como `to_dict()`. Solo los tests importan esos
paquetes (R1).
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tools.cards import assess, core, datacard, modelcard, resolvers
from tools.leadrun import core as lr_core
from tools.modelquality import core as mq_core
from tools.qualityevidence import core as qe_core
from tools.qualityevidence import evidence as qe_evidence

H = "a" * 64
T0 = "2026-10-01T10:00:00Z"
NOW = "2026-10-02T00:00:00Z"
RELOJ_DT = lambda: datetime(2026, 10, 1, 10, 0, 0, tzinfo=timezone.utc)  # noqa: E731

LOS_DOCE_KINDS = set(core.OBSERVED_KINDS) - {"report_artifact"}
KINDS_NUEVOS = {
    "data_card",
    "model_quality_result",
    "model_quality_policy",
    "observed_metric",
    "baseline_reference",
    "drift_evidence",
    "execution_record",
}


# ---------------------------------------------------------------------------
# Constructores de objetos reales
# ---------------------------------------------------------------------------


def _reloj():
    return NOW


def _data_card(card_id="clientes-card", titulo="Clientes"):
    evidencia = core.EvidenceRef("obs-clientes", "source_observation", f"clientes__{H[:12]}", H, T0)
    return core.CardEnvelope(
        schema_version=1,
        card_kind="data_card",
        kind_schema_version=1,
        card_id=card_id,
        title=titulo,
        subject="clientes",
        created_at=T0,
        generated_at=T0,
        evidence=(evidencia,),
        body={
            "description": "Tabla de clientes",
            "source_refs": [
                {"source_ref_id": "principal", "source_id": "clientes", "observation_evidence_id": "obs-clientes"}
            ],
        },
    )


def _model_card(model_id="modelo-a", version="1.0"):
    return core.CardEnvelope(
        schema_version=1,
        card_kind="model_card",
        kind_schema_version=1,
        card_id=modelcard.model_card_id(model_id, version),
        title="Modelo",
        subject=model_id,
        created_at=T0,
        generated_at=T0,
        body={"model_id": model_id, "model_version": version, "description": "Modelo de prueba"},
    )


def _ctx(context_id="test-ctx", split="test"):
    return mq_core.EvaluationContext(context_id=context_id, split=split)


def _metrica(nombre="accuracy", valor=0.9, context_id="test-ctx", split="test"):
    return mq_core.ObservedMetric(metric_name=nombre, value=valor, context=_ctx(context_id, split))


def _baseline(baseline_id="base-naive", valor=0.5, nombre="accuracy"):
    return mq_core.BaselineReference(
        baseline_id=baseline_id, metric_name=nombre, value=valor, context=_ctx(), source="clase mayoritaria"
    )


def _politica(policy_id="pol-clasificador", descripcion=""):
    requisito = mq_core.MetricRequirement(
        requirement_id="req-accuracy",
        metric_name="accuracy",
        direction="higher_is_better",
        required_context=_ctx(),
        threshold_value=0.8,
    )
    return mq_core.ModelQualityPolicy(
        policy_id=policy_id, model_task_role="classification", requirements=(requisito,), description=descripcion
    )


def _manifest(subject="model_quality_evaluation", declaration_kind="model_quality_policy"):
    declaracion = qe_core.DeclarationRef(declaration_kind, "pol-clasificador", None, "c" * 64)
    fuente = qe_core.EvidenceSource(
        kind="generated", role="input", sha256="b" * 64, description="metricas sinteticas", params={"n": 1}
    )
    return qe_evidence.build_manifest(
        subject_kind=subject, declaration=declaracion, source=fuente, results=[], clock=RELOJ_DT
    )


def _drift():
    ventana = qe_evidence.describe_source_generated("ventana sintetica", {"k": 1}, role="baseline")
    actual = qe_evidence.describe_source_generated("ventana actual sintetica", {"k": 2}, role="current")
    return qe_evidence.build_drift_evidence(
        metric_name="accuracy",
        baseline_value=0.9,
        current_value=0.85,
        baseline_window=ventana,
        baseline_label="entrenamiento",
        current_window=actual,
        current_label="produccion",
        comparison_mode="absolute_diff",
        threshold=0.1,
        clock=RELOJ_DT,
    )


def _registro_ejecucion(stdout="ok"):
    """ExecutionRecord real con el `execution_id` que arma `leadrun.runtime`."""
    campos = {
        "command_form": "script",
        "argv": ["python", "scripts/entrenar.py"],
        "code_hash": None,
        "exit_code": 0,
        "duration_seconds": 1.5,
        "stdout_summary": stdout,
        "stderr_summary": "",
        "outputs_hash": None,
        "executed_by": "lead",
        "mode": "autonomous",
        "approval": None,
        "timed_out": False,
    }
    execution_id = f"script__{lr_core.content_sha256(campos)[:12]}"
    return lr_core.ExecutionRecord(
        execution_id=execution_id,
        command_form="script",
        argv=tuple(campos["argv"]),
        code_hash=None,
        exit_code=0,
        duration_seconds=1.5,
        stdout_summary=stdout,
        stderr_summary="",
        outputs_hash=None,
        executed_by="lead",
        mode="autonomous",
        approval=None,
        generated_at="2026-10-01T10:00:00Z",
        timed_out=False,
    )


def _escribir_json(raiz, rel, obj):
    ruta = Path(raiz) / rel
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    return ruta


def _guardar_registro(raiz, registro):
    return _escribir_json(raiz, f".harmessi/executions/{registro.execution_id}/record.json", registro.to_dict())


def _ref(kind, ref_id, locator=None, member=None, sha=H):
    return core.EvidenceRef("ev1", kind, ref_id, sha, T0, member=member, locator=locator)


def _falso(ref_id=None, locator=None, member=None, kind="x"):
    """Ref hostil que `EvidenceRef` real rechazaría en construcción."""
    return SimpleNamespace(ref_id=ref_id, locator=locator, member=member, kind=kind, content_sha256=H)


def _ref_data_card(card, locator="canonico"):
    if locator == "canonico":
        locator = f"governance/cards/data/{card.card_id}.json"
    return _ref("data_card", card.revision_id(), locator=locator, sha=card.content_sha256())


def _symlink(destino, origen, directorio=True):
    try:
        os.symlink(str(origen), str(destino), target_is_directory=directorio)
    except (OSError, NotImplementedError, AttributeError):
        raise unittest.SkipTest("el SO no permite crear symlinks")


def _arbol(raiz):
    salida = []
    for base, dirs, archivos in os.walk(raiz):
        for nombre in sorted(dirs) + sorted(archivos):
            ruta = Path(base) / nombre
            st = ruta.lstat()
            salida.append((ruta.relative_to(raiz).as_posix(), ruta.is_dir(), st.st_size, st.st_mtime_ns))
    return sorted(salida)


class _Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.raiz = Path(self._tmp.name).resolve()
        self.repo = self.raiz / "repo"
        self.repo.mkdir()
        self.fuera = self.raiz / "fuera"
        self.fuera.mkdir()

    def assertEstado(self, resolucion, estado):
        self.assertIsInstance(resolucion, assess.Resolution)
        self.assertEqual(resolucion.state, estado, resolucion.detail)
        if estado != assess.RES_FOUND:
            self.assertIsNone(resolucion.current_sha256)


# ---------------------------------------------------------------------------
# data_card (R23, R29)
# ---------------------------------------------------------------------------


class TestDataCard(_Base):
    def _resolver(self):
        return resolvers.data_card_resolver(self.repo)

    def _escribir(self, card=None, **kw):
        card = card or _data_card(**kw)
        datacard.write_data_card(self.repo, card, clock=_reloj)
        return card

    def test_found_con_hash_de_la_card_real(self):
        card = self._escribir()
        res = self._resolver()(_ref_data_card(card))
        self.assertEstado(res, assess.RES_FOUND)
        self.assertEqual(res.current_sha256, card.content_sha256())

    def test_found_sin_locator(self):
        card = self._escribir()
        res = self._resolver()(_ref_data_card(card, locator=None))
        self.assertEstado(res, assess.RES_FOUND)

    def test_missing_si_no_existe_la_card(self):
        card = _data_card()
        self.assertEstado(self._resolver()(_ref_data_card(card)), assess.RES_MISSING)

    def test_data_card_incomplete_pero_integra_queda_found_y_fresh(self):
        card = self._escribir()
        # La Data Card es estructuralmente válida pero NO complete (su observación no existe).
        evaluacion = datacard.evaluate_data_card(card, self.repo, clock=_reloj)
        self.assertNotEqual(evaluacion.card_status, assess.CARD_COMPLETE)
        self.assertNotEqual(evaluacion.card_status, assess.CARD_INVALID)
        pin = _ref_data_card(card)
        self.assertEqual(assess.evaluar_evidencia(pin, resolvers.default_resolvers(self.repo)), assess.EV_FRESH)

    def test_no_invoca_evaluate_ni_evaluate_data_card(self):
        card = self._escribir()
        llamadas = []

        def _espia(*args, **kwargs):
            llamadas.append(1)
            raise AssertionError("no debe evaluarse")

        resolver = self._resolver()
        with mock.patch.object(assess, "evaluate", _espia), mock.patch.object(
            assess, "evaluate_file", _espia
        ), mock.patch.object(datacard, "evaluate_data_card", _espia), mock.patch.object(
            assess, "evaluar_evidencia", _espia
        ):
            res = resolver(_ref_data_card(card))
        self.assertEqual(llamadas, [])
        self.assertEstado(res, assess.RES_FOUND)
        self.assertEqual(res.current_sha256, card.content_sha256())

    def test_card_cambiada_deja_hash_distinto_y_pin_stale(self):
        card = self._escribir()
        pin = _ref_data_card(card)
        defaults = resolvers.default_resolvers(self.repo)
        self.assertEqual(assess.evaluar_evidencia(pin, defaults), assess.EV_FRESH)
        nueva = _data_card(titulo="Clientes v2")
        datacard.write_data_card(self.repo, nueva, replace=True, clock=_reloj)
        res = self._resolver()(pin)
        self.assertEstado(res, assess.RES_FOUND)
        self.assertNotEqual(res.current_sha256, card.content_sha256())
        self.assertEqual(res.current_sha256, nueva.content_sha256())
        self.assertEqual(assess.evaluar_evidencia(pin, defaults), assess.EV_STALE)

    def test_solo_generated_at_distinto_no_cambia_el_hash(self):
        card = self._escribir()
        otra = core.CardEnvelope.from_dict(dict(card.to_dict(), generated_at="2026-10-01T12:00:00Z"))
        datacard.write_data_card(self.repo, otra, replace=True, clock=_reloj)
        res = self._resolver()(_ref_data_card(card))
        self.assertEqual(res.current_sha256, card.content_sha256())

    def test_locator_distinto_del_canonico_es_unverifiable(self):
        card = self._escribir()
        otra_ruta = self.repo / "copia" / f"{card.card_id}.json"
        otra_ruta.parent.mkdir()
        otra_ruta.write_bytes((self.repo / "governance/cards/data" / f"{card.card_id}.json").read_bytes())
        for locator in (
            f"copia/{card.card_id}.json",
            "governance/cards/data/otra.json",
            f"governance/cards/model/{card.card_id}.json",
            f"./governance/cards/data/{card.card_id}.json",
        ):
            with self.subTest(locator=locator):
                self.assertEstado(self._resolver()(_ref_data_card(card, locator=locator)), assess.RES_UNVERIFIABLE)
        for locator in ("/abs.json", "..\\x.json", "../x.json", 5, ""):
            with self.subTest(locator=locator):
                ref = _falso(card.revision_id(), locator=locator)
                self.assertEstado(self._resolver()(ref), assess.RES_UNVERIFIABLE)

    def test_card_kind_erroneo_es_unverifiable(self):
        # Una Model Card válida copiada a la ubicación de Data Cards.
        modelo = _model_card()
        with tempfile.TemporaryDirectory() as tmp:
            ruta = modelcard.write_model_card(tmp, modelo, clock=_reloj)
            contenido = Path(ruta).read_bytes()
        destino = self.repo / "governance" / "cards" / "data" / f"{modelo.card_id}.json"
        destino.parent.mkdir(parents=True)
        destino.write_bytes(contenido)
        ref = _ref("data_card", modelo.revision_id(), sha=modelo.content_sha256())
        self.assertEstado(self._resolver()(ref), assess.RES_UNVERIFIABLE)

    def test_card_id_interno_distinto_del_ref_id_es_unverifiable(self):
        card = self._escribir()
        copia = self.repo / "governance" / "cards" / "data" / "otra-card.json"
        copia.write_bytes((self.repo / "governance/cards/data" / f"{card.card_id}.json").read_bytes())
        ref = _ref("data_card", f"otra-card__{card.content_sha256()[:12]}", sha=card.content_sha256())
        self.assertEstado(self._resolver()(ref), assess.RES_UNVERIFIABLE)

    def test_archivo_corrupto_o_con_forma_inesperada_es_unverifiable(self):
        card = self._escribir()
        ruta = self.repo / "governance/cards/data" / f"{card.card_id}.json"
        original = json.loads(ruta.read_text(encoding="utf-8"))
        casos = {
            "roto": b"{",
            "lista": b"[]",
            "nan": b'{"a": NaN}',
            "utf8": b"\xff\xfe",
            "vacio": b"",
            "revision_adulterada": json.dumps(dict(original, revision_id=f"{card.card_id}__000000000000")).encode(),
            "clave_status": json.dumps(dict(original, status="complete")).encode(),
            "titulo_cambiado_sin_revision": json.dumps(dict(original, title="Otro")).encode(),
        }
        for nombre, contenido in casos.items():
            with self.subTest(caso=nombre):
                ruta.write_bytes(contenido)
                self.assertEstado(self._resolver()(_ref_data_card(card)), assess.RES_UNVERIFIABLE)

    def test_destino_directorio_o_excede_tamano_es_unverifiable(self):
        card = self._escribir()
        with mock.patch.object(resolvers, "MAX_BYTES_LECTURA", 10):
            self.assertEstado(self._resolver()(_ref_data_card(card)), assess.RES_UNVERIFIABLE)
        ruta = self.repo / "governance/cards/data" / f"{card.card_id}.json"
        ruta.unlink()
        ruta.mkdir()
        self.assertEstado(self._resolver()(_ref_data_card(card)), assess.RES_UNVERIFIABLE)

    def test_ref_id_malformado_o_con_rutas_es_unverifiable(self):
        card = self._escribir()
        for ref_id in (
            card.card_id,
            f"{card.card_id}__XYZ",
            f"{card.card_id}__0123456789abc",
            f"../{card.revision_id()}",
            f"a/{card.revision_id()}",
            f"a\\{card.revision_id()}",
            f"/{card.revision_id()}",
            f"C:{card.revision_id()}",
            f"~{card.revision_id()}",
            "..__0123456789ab",
            "",
            None,
            5,
        ):
            with self.subTest(ref_id=ref_id):
                self.assertEstado(self._resolver()(_falso(ref_id)), assess.RES_UNVERIFIABLE)

    def test_symlink_del_directorio_de_data_cards_que_escapa(self):
        card = _data_card()
        datacard.write_data_card(self.fuera, card, clock=_reloj)
        (self.repo / "governance" / "cards").mkdir(parents=True)
        _symlink(self.repo / "governance" / "cards" / "data", self.fuera / "governance" / "cards" / "data")
        self.assertEstado(self._resolver()(_ref_data_card(card)), assess.RES_UNVERIFIABLE)

    def test_symlink_del_archivo_de_la_card_que_escapa(self):
        card = _data_card()
        ruta_fuera = datacard.write_data_card(self.fuera, card, clock=_reloj)
        directorio = self.repo / "governance" / "cards" / "data"
        directorio.mkdir(parents=True)
        _symlink(directorio / f"{card.card_id}.json", ruta_fuera, directorio=False)
        self.assertEstado(self._resolver()(_ref_data_card(card)), assess.RES_UNVERIFIABLE)


# ---------------------------------------------------------------------------
# model_quality_result (R24)
# ---------------------------------------------------------------------------


class TestModelQualityResult(_Base):
    def _resolver(self):
        return resolvers.model_quality_result_resolver(self.repo)

    def _persistir(self, **kw):
        manifest = _manifest(**kw)
        return manifest, Path(qe_evidence.write_manifest(self.repo, manifest))

    def test_found_con_hash_del_manifest_real(self):
        manifest, ruta = self._persistir()
        res = self._resolver()(_ref("model_quality_result", manifest.evidence_id))
        self.assertEstado(res, assess.RES_FOUND)
        self.assertEqual(res.current_sha256, manifest.content_sha256())
        self.assertEqual(res.current_sha256, json.loads(ruta.read_text(encoding="utf-8"))["content_sha256"])

    def test_subject_kind_incorrecto_es_unverifiable(self):
        manifest, _ = self._persistir(subject="data_contract_evaluation", declaration_kind="data_contract")
        res = self._resolver()(_ref("model_quality_result", manifest.evidence_id))
        self.assertEstado(res, assess.RES_UNVERIFIABLE)

    def test_manifest_adulterado_es_unverifiable(self):
        manifest, ruta = self._persistir()
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        datos["scope"]["population"] = "otra poblacion"
        ruta.write_text(json.dumps(datos), encoding="utf-8")
        self.assertEstado(self._resolver()(_ref("model_quality_result", manifest.evidence_id)), assess.RES_UNVERIFIABLE)

    def test_ausente_es_missing(self):
        res = self._resolver()(_ref("model_quality_result", "qe-20261001T100000Z-abcdef"))
        self.assertEstado(res, assess.RES_MISSING)

    def test_ref_id_malformado_o_con_rutas_es_unverifiable(self):
        self._persistir()
        for ref_id in ("qe-1", "../qe-20261001T100000Z-abcdef", "a/qe-20261001T100000Z-abcdef", "", None, 7):
            with self.subTest(ref_id=ref_id):
                self.assertEstado(self._resolver()(_falso(ref_id)), assess.RES_UNVERIFIABLE)

    def test_pin_fresh_y_stale(self):
        manifest, _ = self._persistir()
        defaults = resolvers.default_resolvers(self.repo)
        fresco = _ref("model_quality_result", manifest.evidence_id, sha=manifest.content_sha256())
        viejo = _ref("model_quality_result", manifest.evidence_id, sha="e" * 64)
        self.assertEqual(assess.evaluar_evidencia(fresco, defaults), assess.EV_FRESH)
        self.assertEqual(assess.evaluar_evidencia(viejo, defaults), assess.EV_STALE)

    def test_symlink_del_manifest_que_escapa(self):
        manifest = _manifest()
        ruta_fuera = Path(qe_evidence.write_manifest(self.fuera, manifest))
        directorio = self.repo / ".harmessi" / "quality" / manifest.evidence_id
        directorio.mkdir(parents=True)
        _symlink(directorio / "manifest.json", ruta_fuera, directorio=False)
        self.assertEstado(self._resolver()(_ref("model_quality_result", manifest.evidence_id)), assess.RES_UNVERIFIABLE)


# ---------------------------------------------------------------------------
# model_quality_policy (R25)
# ---------------------------------------------------------------------------


class TestModelQualityPolicy(_Base):
    REL = "models/policy.json"

    def _resolver(self):
        return resolvers.model_quality_policy_resolver(self.repo)

    def _escribir(self, politica=None):
        politica = politica or _politica()
        _escribir_json(self.repo, self.REL, politica.to_dict())
        return politica

    def _ref(self, politica, locator=REL, ref_id=None):
        return _ref("model_quality_policy", ref_id or politica.policy_id, locator=locator, sha=politica.content_sha256())

    def test_found_con_hash_de_la_politica_real(self):
        politica = self._escribir()
        res = self._resolver()(self._ref(politica))
        self.assertEstado(res, assess.RES_FOUND)
        self.assertEqual(res.current_sha256, politica.content_sha256())

    def test_missing_si_el_archivo_no_existe(self):
        self.assertEstado(self._resolver()(self._ref(_politica())), assess.RES_MISSING)

    def test_policy_id_interno_distinto_del_ref_id_es_unverifiable(self):
        politica = self._escribir()
        self.assertEstado(self._resolver()(self._ref(politica, ref_id="otra-politica")), assess.RES_UNVERIFIABLE)

    def test_politica_modificada_da_hash_distinto_y_pin_stale(self):
        original = self._escribir()
        pin = self._ref(original)
        defaults = resolvers.default_resolvers(self.repo)
        self.assertEqual(assess.evaluar_evidencia(pin, defaults), assess.EV_FRESH)
        modificada = self._escribir(_politica(descripcion="cambio"))
        res = self._resolver()(pin)
        self.assertEqual(res.current_sha256, modificada.content_sha256())
        self.assertNotEqual(res.current_sha256, original.content_sha256())
        self.assertEqual(assess.evaluar_evidencia(pin, defaults), assess.EV_STALE)

    def test_locator_ausente_u_hostil_es_unverifiable(self):
        politica = self._escribir()
        (self.raiz / "ajeno.json").write_text(json.dumps(politica.to_dict()), encoding="utf-8")
        for locator in (
            None,
            "/abs/policy.json",
            "C:/x/policy.json",
            "a:b.json",
            "..\\ajeno.json",
            "models\\policy.json",
            "../ajeno.json",
            "models/../../ajeno.json",
            "~/policy.json",
            "https://host/policy.json",
            "",
            5,
        ):
            with self.subTest(locator=locator):
                self.assertEstado(self._resolver()(_falso(politica.policy_id, locator=locator)), assess.RES_UNVERIFIABLE)

    def test_json_invalido_o_forma_inesperada_es_unverifiable(self):
        politica = self._escribir()
        ruta = self.repo / self.REL
        for contenido in ("{", "[]", "null", '{"policy_id": NaN}'):
            with self.subTest(contenido=contenido):
                ruta.write_text(contenido, encoding="utf-8")
                self.assertEstado(self._resolver()(self._ref(politica)), assess.RES_UNVERIFIABLE)

    def test_locator_directorio_es_unverifiable(self):
        (self.repo / self.REL).mkdir(parents=True)
        self.assertEstado(self._resolver()(self._ref(_politica())), assess.RES_UNVERIFIABLE)

    def test_symlink_que_escapa(self):
        politica = _politica()
        _escribir_json(self.fuera, "policy.json", politica.to_dict())
        (self.repo / "models").mkdir()
        _symlink(self.repo / self.REL, self.fuera / "policy.json", directorio=False)
        self.assertEstado(self._resolver()(self._ref(politica)), assess.RES_UNVERIFIABLE)

    def test_symlink_de_directorio_que_escapa(self):
        politica = _politica()
        _escribir_json(self.fuera, "policy.json", politica.to_dict())
        _symlink(self.repo / "models", self.fuera)
        self.assertEstado(self._resolver()(self._ref(politica)), assess.RES_UNVERIFIABLE)


# ---------------------------------------------------------------------------
# observed_metric / baseline_reference (R26)
# ---------------------------------------------------------------------------


class _BaseDocumento(_Base):
    REL = "models/doc.json"

    def _guardar(self, entradas):
        return _escribir_json(self.repo, self.REL, entradas)

    def _res(self, resolver, kind, member, locator=REL):
        return resolver(_ref(kind, "doc-1", locator=locator, member=member))


class TestObservedMetric(_BaseDocumento):
    KIND = "observed_metric"

    def _resolver(self):
        return resolvers.observed_metric_resolver(self.repo)

    def _entradas(self):
        return [
            _metrica("accuracy", 0.9, "test-ctx", "test").to_dict(),
            _metrica("accuracy", 0.95, "val-ctx", "validation").to_dict(),
            _metrica("recall", 0.7, "test-ctx", "test").to_dict(),
        ]

    def test_found_por_identidad_con_hash_del_documento(self):
        entradas = self._entradas()
        self._guardar(entradas)
        for member in ("accuracy@test-ctx", "accuracy@val-ctx", "recall@test-ctx"):
            with self.subTest(member=member):
                res = self._res(self._resolver(), self.KIND, member)
                self.assertEstado(res, assess.RES_FOUND)
                self.assertEqual(res.current_sha256, resolvers.hash_document(entradas))

    def test_member_inexistente_es_missing(self):
        self._guardar(self._entradas())
        for member in ("accuracy@otro-ctx", "f1@test-ctx", "recall@val-ctx"):
            with self.subTest(member=member):
                self.assertEstado(self._res(self._resolver(), self.KIND, member), assess.RES_MISSING)

    def test_documento_ausente_es_missing(self):
        self.assertEstado(self._res(self._resolver(), self.KIND, "accuracy@test-ctx"), assess.RES_MISSING)

    def test_duplicado_es_unverifiable_y_no_elige_primer_match(self):
        entradas = self._entradas() + [_metrica("accuracy", 0.1, "test-ctx", "test").to_dict()]
        self._guardar(entradas)
        self.assertEstado(self._res(self._resolver(), self.KIND, "accuracy@test-ctx"), assess.RES_UNVERIFIABLE)
        # Las entradas no duplicadas siguen resolviendo.
        self.assertEstado(self._res(self._resolver(), self.KIND, "recall@test-ctx"), assess.RES_FOUND)

    def test_mismo_nombre_en_contextos_distintos_no_es_duplicado(self):
        self._guardar(self._entradas())
        self.assertEstado(self._res(self._resolver(), self.KIND, "accuracy@val-ctx"), assess.RES_FOUND)

    def test_documento_que_no_es_lista_es_unverifiable(self):
        for contenido in ({"metric_name": "accuracy"}, "texto", 5, None):
            with self.subTest(contenido=contenido):
                self._guardar(contenido)
                self.assertEstado(self._res(self._resolver(), self.KIND, "accuracy@test-ctx"), assess.RES_UNVERIFIABLE)

    def test_entrada_malformada_en_cualquier_posicion_es_unverifiable(self):
        buena = _metrica("accuracy", 0.9).to_dict()
        malas = (
            {"metric_name": "x"},
            {"context": {"context_id": "c"}},
            {"metric_name": "x", "context": "c"},
            {"metric_name": "", "context": {"context_id": "c"}},
            {"metric_name": "x", "context": {"context_id": ""}},
            {"metric_name": 5, "context": {"context_id": "c"}},
            5,
            "texto",
            None,
            [],
        )
        for i, mala in enumerate(malas):
            for posicion in ("inicio", "medio", "fin"):
                entradas = {
                    "inicio": [mala, buena, buena | {"metric_name": "recall"}],
                    "medio": [buena, mala, buena | {"metric_name": "recall"}],
                    "fin": [buena, buena | {"metric_name": "recall"}, mala],
                }[posicion]
                with self.subTest(caso=i, posicion=posicion):
                    self._guardar(entradas)
                    # Aun pidiendo una entrada sana, el documento entero es no verificable.
                    self.assertEstado(
                        self._res(self._resolver(), self.KIND, "accuracy@test-ctx"), assess.RES_UNVERIFIABLE
                    )

    def test_reordenar_mantiene_la_resolucion_pero_cambia_el_hash_del_documento(self):
        entradas = self._entradas()
        self._guardar(entradas)
        antes = self._res(self._resolver(), self.KIND, "accuracy@val-ctx")
        self._guardar(list(reversed(entradas)))
        despues = self._res(self._resolver(), self.KIND, "accuracy@val-ctx")
        self.assertEstado(antes, assess.RES_FOUND)
        self.assertEstado(despues, assess.RES_FOUND)
        self.assertNotEqual(antes.current_sha256, despues.current_sha256)
        self.assertEqual(despues.current_sha256, resolvers.hash_document(list(reversed(entradas))))

    def test_cambiar_cualquier_entrada_deja_stale_el_pin_del_documento(self):
        entradas = self._entradas()
        self._guardar(entradas)
        pin = _ref(self.KIND, "doc-1", locator=self.REL, member="accuracy@test-ctx", sha=resolvers.hash_document(entradas))
        defaults = resolvers.default_resolvers(self.repo)
        self.assertEqual(assess.evaluar_evidencia(pin, defaults), assess.EV_FRESH)
        entradas[2]["value"] = 0.71  # otra entrada del mismo archivo
        self._guardar(entradas)
        self.assertEqual(assess.evaluar_evidencia(pin, defaults), assess.EV_STALE)

    def test_nunca_posicional_member_numerico_no_resuelve(self):
        self._guardar(self._entradas())
        for member in ("0", "1", "-1", "accuracy@0", "accuracy@1", "@test-ctx", "accuracy@", "accuracy", "a@b@c"):
            with self.subTest(member=member):
                res = self._res(self._resolver(), self.KIND, member)
                self.assertNotEqual(res.state, assess.RES_FOUND)

    def test_member_invalido_es_unverifiable(self):
        self._guardar(self._entradas())
        for member in (None, "", 5, ["accuracy@test-ctx"]):
            with self.subTest(member=member):
                self.assertEstado(
                    self._resolver()(_falso("doc-1", locator=self.REL, member=member)), assess.RES_UNVERIFIABLE
                )

    def test_locator_hostil_o_symlink_que_escapa_es_unverifiable(self):
        self._guardar(self._entradas())
        for locator in (None, "/abs.json", "../x.json", "models\\doc.json", "C:/x.json", ""):
            with self.subTest(locator=locator):
                self.assertEstado(
                    self._resolver()(_falso("doc-1", locator=locator, member="accuracy@test-ctx")),
                    assess.RES_UNVERIFIABLE,
                )
        _escribir_json(self.fuera, "doc.json", self._entradas())
        (self.repo / "otro").mkdir()
        _symlink(self.repo / "otro" / "doc.json", self.fuera / "doc.json", directorio=False)
        res = self._res(self._resolver(), self.KIND, "accuracy@test-ctx", locator="otro/doc.json")
        self.assertEstado(res, assess.RES_UNVERIFIABLE)


class TestBaselineReference(_BaseDocumento):
    KIND = "baseline_reference"

    def _resolver(self):
        return resolvers.baseline_reference_resolver(self.repo)

    def _entradas(self):
        return [
            _baseline("base-naive", 0.5).to_dict(),
            _baseline("base-lineal", 0.7).to_dict(),
        ]

    def test_found_por_baseline_id_con_hash_del_documento(self):
        entradas = self._entradas()
        self._guardar(entradas)
        for member in ("base-naive", "base-lineal"):
            with self.subTest(member=member):
                res = self._res(self._resolver(), self.KIND, member)
                self.assertEstado(res, assess.RES_FOUND)
                self.assertEqual(res.current_sha256, resolvers.hash_document(entradas))

    def test_inexistente_es_missing(self):
        self._guardar(self._entradas())
        self.assertEstado(self._res(self._resolver(), self.KIND, "base-otra"), assess.RES_MISSING)
        sin_archivo = _ref(self.KIND, "doc-1", locator="models/no_esta.json", member="base-naive")
        self.assertEstado(self._resolver()(sin_archivo), assess.RES_MISSING)

    def test_duplicado_es_unverifiable(self):
        self._guardar(self._entradas() + [_baseline("base-naive", 0.1).to_dict()])
        self.assertEstado(self._res(self._resolver(), self.KIND, "base-naive"), assess.RES_UNVERIFIABLE)
        self.assertEstado(self._res(self._resolver(), self.KIND, "base-lineal"), assess.RES_FOUND)

    def test_documento_no_lista_o_entrada_malformada_es_unverifiable(self):
        casos = (
            {"baseline_id": "base-naive"},
            [{"baseline_id": "base-naive"}, {"metric_name": "accuracy"}],
            [{"metric_name": "accuracy"}, {"baseline_id": "base-naive"}],
            [{"baseline_id": 5}, {"baseline_id": "base-naive"}],
            [{"baseline_id": ""}, {"baseline_id": "base-naive"}],
            [{"baseline_id": "base-naive"}, 5],
            [None],
        )
        for i, contenido in enumerate(casos):
            with self.subTest(caso=i):
                self._guardar(contenido)
                self.assertEstado(self._res(self._resolver(), self.KIND, "base-naive"), assess.RES_UNVERIFIABLE)

    def test_reordenar_mantiene_resolucion_y_cambia_hash(self):
        entradas = self._entradas()
        self._guardar(entradas)
        antes = self._res(self._resolver(), self.KIND, "base-lineal")
        self._guardar(list(reversed(entradas)))
        despues = self._res(self._resolver(), self.KIND, "base-lineal")
        self.assertEstado(despues, assess.RES_FOUND)
        self.assertNotEqual(antes.current_sha256, despues.current_sha256)

    def test_nunca_posicional_member_numerico_no_resuelve(self):
        self._guardar(self._entradas())
        for member in ("0", "1", "-1"):
            with self.subTest(member=member):
                self.assertEstado(self._res(self._resolver(), self.KIND, member), assess.RES_MISSING)

    def test_baseline_id_numerico_se_busca_por_identidad_no_por_indice(self):
        entradas = [_baseline("base-a").to_dict(), _baseline("1", 0.3).to_dict()]
        self._guardar(entradas)
        # "1" resuelve por baseline_id (segunda entrada), no por ser el índice 1 ...
        self.assertEstado(self._res(self._resolver(), self.KIND, "1"), assess.RES_FOUND)
        # ... y "0" no resuelve aunque exista una entrada en la posición 0.
        self.assertEstado(self._res(self._resolver(), self.KIND, "0"), assess.RES_MISSING)

    def test_member_invalido_es_unverifiable(self):
        self._guardar(self._entradas())
        for member in (None, "", 5):
            with self.subTest(member=member):
                self.assertEstado(
                    self._resolver()(_falso("doc-1", locator=self.REL, member=member)), assess.RES_UNVERIFIABLE
                )


# ---------------------------------------------------------------------------
# drift_evidence (R27)
# ---------------------------------------------------------------------------


class TestDriftEvidence(_Base):
    REL = "models/drift.json"

    def _resolver(self):
        return resolvers.drift_evidence_resolver(self.repo)

    def _guardar(self, drift=None):
        drift = drift or _drift()
        _escribir_json(self.repo, self.REL, drift.to_dict())
        return drift

    def test_found_con_hash_de_la_evidencia_real(self):
        drift = self._guardar()
        res = self._resolver()(_ref("drift_evidence", drift.drift_id, locator=self.REL))
        self.assertEstado(res, assess.RES_FOUND)
        self.assertEqual(res.current_sha256, drift.content_sha256())

    def test_hash_sin_generated_at(self):
        drift = self._guardar()
        ref = _ref("drift_evidence", drift.drift_id, locator=self.REL)
        antes = self._resolver()(ref).current_sha256
        datos = drift.to_dict()
        datos["generated_at"] = "2031-01-01T00:00:00Z"
        _escribir_json(self.repo, self.REL, datos)
        self.assertEqual(self._resolver()(ref).current_sha256, antes)

    def test_cambio_de_contenido_cambia_el_hash(self):
        drift = self._guardar()
        ref = _ref("drift_evidence", drift.drift_id, locator=self.REL)
        antes = self._resolver()(ref).current_sha256
        datos = drift.to_dict()
        datos["current_value"] = 0.1
        _escribir_json(self.repo, self.REL, datos)
        self.assertNotEqual(self._resolver()(ref).current_sha256, antes)

    def test_drift_id_interno_distinto_del_ref_id_es_unverifiable(self):
        self._guardar()
        ref = _ref("drift_evidence", "dr-20200101T000000Z-abcdef", locator=self.REL)
        self.assertEstado(self._resolver()(ref), assess.RES_UNVERIFIABLE)

    def test_ref_id_que_no_es_drift_id_es_unverifiable(self):
        self._guardar()
        for ref_id in ("drift-1", "qe-20261001T100000Z-abcdef", "dr-1", "../dr-20261001T100000Z-abcdef", "", None):
            with self.subTest(ref_id=ref_id):
                self.assertEstado(self._resolver()(_falso(ref_id, locator=self.REL)), assess.RES_UNVERIFIABLE)

    def test_missing_y_locator_hostil(self):
        drift = _drift()
        self.assertEstado(self._resolver()(_ref("drift_evidence", drift.drift_id, locator=self.REL)), assess.RES_MISSING)
        for locator in (None, "/abs.json", "../x.json", "models\\drift.json", ""):
            with self.subTest(locator=locator):
                self.assertEstado(self._resolver()(_falso(drift.drift_id, locator=locator)), assess.RES_UNVERIFIABLE)

    def test_json_corrupto_es_unverifiable(self):
        drift = self._guardar()
        for contenido in ("{", "[]"):
            (self.repo / self.REL).write_text(contenido, encoding="utf-8")
            self.assertEstado(
                self._resolver()(_ref("drift_evidence", drift.drift_id, locator=self.REL)), assess.RES_UNVERIFIABLE
            )

    def test_symlink_que_escapa(self):
        drift = _drift()
        _escribir_json(self.fuera, "drift.json", drift.to_dict())
        (self.repo / "models").mkdir()
        _symlink(self.repo / self.REL, self.fuera / "drift.json", directorio=False)
        self.assertEstado(
            self._resolver()(_ref("drift_evidence", drift.drift_id, locator=self.REL)), assess.RES_UNVERIFIABLE
        )


# ---------------------------------------------------------------------------
# execution_record (R28)
# ---------------------------------------------------------------------------


class TestExecutionRecord(_Base):
    def _resolver(self):
        return resolvers.execution_record_resolver(self.repo)

    def test_found_con_hash_sin_generated_at(self):
        registro = _registro_ejecucion()
        _guardar_registro(self.repo, registro)
        res = self._resolver()(_ref("execution_record", registro.execution_id))
        self.assertEstado(res, assess.RES_FOUND)
        esperado = resolvers.hash_execution_record(registro.to_dict())
        self.assertEqual(res.current_sha256, esperado)

    def test_generated_at_no_cambia_el_hash_pero_si_el_contenido(self):
        registro = _registro_ejecucion()
        ruta = _guardar_registro(self.repo, registro)
        ref = _ref("execution_record", registro.execution_id)
        base = self._resolver()(ref).current_sha256
        datos = registro.to_dict()
        datos["generated_at"] = "2031-01-01T00:00:00Z"
        _escribir_json(self.repo, ruta.relative_to(self.repo).as_posix(), datos)
        self.assertEqual(self._resolver()(ref).current_sha256, base)
        datos["exit_code"] = 1
        _escribir_json(self.repo, ruta.relative_to(self.repo).as_posix(), datos)
        self.assertNotEqual(self._resolver()(ref).current_sha256, base)

    def test_missing_si_no_existe(self):
        registro = _registro_ejecucion()
        self.assertEstado(self._resolver()(_ref("execution_record", registro.execution_id)), assess.RES_MISSING)

    def test_execution_id_interno_distinto_del_directorio_es_unverifiable(self):
        registro = _registro_ejecucion()
        otro = "script__ffffffffffff"
        self.assertNotEqual(otro, registro.execution_id)
        _escribir_json(self.repo, f".harmessi/executions/{otro}/record.json", registro.to_dict())
        self.assertEstado(self._resolver()(_ref("execution_record", otro)), assess.RES_UNVERIFIABLE)

    def test_ref_id_con_path_traversal_o_malformado_es_unverifiable(self):
        registro = _registro_ejecucion()
        _guardar_registro(self.repo, registro)
        hash12 = registro.execution_id.split("__")[1]
        for ref_id in (
            f"../script__{hash12}",
            f"script__{hash12}/..",
            f"..\\script__{hash12}",
            f"a/script__{hash12}",
            f"/script__{hash12}",
            f"C:script__{hash12}",
            f"~script__{hash12}",
            "..__0123456789ab",
            f"script_{hash12}",
            "script__XYZ",
            "script",
            "",
            None,
            7,
        ):
            with self.subTest(ref_id=ref_id):
                self.assertEstado(self._resolver()(_falso(ref_id)), assess.RES_UNVERIFIABLE)

    def test_json_corrupto_es_unverifiable(self):
        registro = _registro_ejecucion()
        ruta = _guardar_registro(self.repo, registro)
        for contenido in ("{", "[]", "null"):
            ruta.write_text(contenido, encoding="utf-8")
            self.assertEstado(self._resolver()(_ref("execution_record", registro.execution_id)), assess.RES_UNVERIFIABLE)

    def test_symlink_del_directorio_que_escapa(self):
        registro = _registro_ejecucion()
        _guardar_registro(self.fuera, registro)
        base = self.repo / ".harmessi" / "executions"
        base.mkdir(parents=True)
        _symlink(base / registro.execution_id, self.fuera / ".harmessi" / "executions" / registro.execution_id)
        self.assertEstado(self._resolver()(_ref("execution_record", registro.execution_id)), assess.RES_UNVERIFIABLE)

    def test_symlink_del_archivo_que_escapa(self):
        registro = _registro_ejecucion()
        ruta_fuera = _guardar_registro(self.fuera, registro)
        directorio = self.repo / ".harmessi" / "executions" / registro.execution_id
        directorio.mkdir(parents=True)
        _symlink(directorio / "record.json", ruta_fuera, directorio=False)
        self.assertEstado(self._resolver()(_ref("execution_record", registro.execution_id)), assess.RES_UNVERIFIABLE)


# ---------------------------------------------------------------------------
# default_resolvers, robustez y solo lectura (R4, R30)
# ---------------------------------------------------------------------------


class TestDefaultResolversModelo(_Base):
    def test_exactamente_los_doce_kinds(self):
        mapa = resolvers.default_resolvers(self.repo)
        self.assertEqual(set(mapa), LOS_DOCE_KINDS)
        self.assertEqual(len(mapa), 12)
        self.assertTrue(KINDS_NUEVOS <= set(mapa))
        for kind, resolver in mapa.items():
            with self.subTest(kind=kind):
                self.assertTrue(callable(resolver))

    def test_report_artifact_sigue_unverifiable(self):
        mapa = resolvers.default_resolvers(self.repo)
        self.assertNotIn("report_artifact", mapa)
        ref = core.EvidenceRef("ev1", "report_artifact", "x-1", H, T0)
        self.assertEqual(assess.evaluar_evidencia(ref, mapa), assess.EV_UNVERIFIABLE)

    def test_constantes_de_kind_coinciden_con_core(self):
        constantes = {
            resolvers.KIND_DATA_CARD,
            resolvers.KIND_MODEL_QUALITY_RESULT,
            resolvers.KIND_MODEL_QUALITY_POLICY,
            resolvers.KIND_OBSERVED_METRIC,
            resolvers.KIND_BASELINE_REFERENCE,
            resolvers.KIND_DRIFT_EVIDENCE,
            resolvers.KIND_EXECUTION_RECORD,
        }
        self.assertEqual(constantes, KINDS_NUEVOS)
        self.assertTrue(constantes <= set(core.OBSERVED_KINDS))

    def test_repo_root_invalido_lanza_card_error(self):
        with self.assertRaises(core.CardError):
            resolvers.default_resolvers(None)


class TestNuncaLanzanModelo(_Base):
    def _basura(self):
        return (
            None,
            5,
            "texto",
            b"bytes",
            object(),
            SimpleNamespace(),
            SimpleNamespace(ref_id=b"x", locator=5, member=[], kind=None),
            SimpleNamespace(ref_id="a" * 10000, locator="b" * 10000, member="a@" + "c" * 10000),
            SimpleNamespace(ref_id="\x00", locator="\x00", member="\x00"),
            SimpleNamespace(ref_id="a__0123456789ab\x00", locator="a/\x00b.json", member="x@y"),
            _falso("qe-20261001T100000Z-abcdef", locator="models/c.json", member="accuracy@test-ctx"),
            _falso("dr-20261001T100000Z-abcdef", locator="models/c.json", member="x"),
        )

    def test_basura_nunca_lanza_y_nunca_es_found(self):
        for kind, resolver in resolvers.default_resolvers(self.repo).items():
            for i, basura in enumerate(self._basura()):
                with self.subTest(kind=kind, caso=i):
                    res = resolver(basura)
                    self.assertIsInstance(res, assess.Resolution)
                    self.assertNotEqual(res.state, assess.RES_FOUND)

    def test_repo_inexistente_no_lanza(self):
        inexistente = self.raiz / "no_existe"
        for kind in KINDS_NUEVOS:
            resolver = resolvers.default_resolvers(inexistente)[kind]
            with self.subTest(kind=kind):
                ref = _falso("clientes__0123456789ab", locator="c.json", member="x@y")
                self.assertIn(resolver(ref).state, (assess.RES_MISSING, assess.RES_UNVERIFIABLE))

    def test_error_inesperado_de_io_se_convierte_en_unverifiable(self):
        _escribir_json(self.repo, "models/policy.json", _politica().to_dict())
        resolver = resolvers.model_quality_policy_resolver(self.repo)
        ref = _ref("model_quality_policy", "pol-clasificador", locator="models/policy.json")
        with mock.patch.object(Path, "is_file", side_effect=PermissionError("denegado")):
            res = resolver(ref)
        self.assertEstado(res, assess.RES_UNVERIFIABLE)

    def test_evaluar_evidencia_ante_basura_es_unverifiable(self):
        mapa = resolvers.default_resolvers(self.repo)
        self.assertEqual(assess.evaluar_evidencia(_falso("../x"), mapa), assess.EV_UNVERIFIABLE)


class TestSoloLecturaModelo(_Base):
    def test_ningun_resolver_modifica_el_arbol(self):
        card = _data_card()
        datacard.write_data_card(self.repo, card, clock=_reloj)
        manifest = _manifest()
        qe_evidence.write_manifest(self.repo, manifest)
        politica = _politica()
        _escribir_json(self.repo, "models/policy.json", politica.to_dict())
        _escribir_json(self.repo, "models/metricas.json", [_metrica().to_dict()])
        _escribir_json(self.repo, "models/baselines.json", [_baseline().to_dict()])
        drift = _drift()
        _escribir_json(self.repo, "models/drift.json", drift.to_dict())
        registro = _registro_ejecucion()
        _guardar_registro(self.repo, registro)

        antes = _arbol(self.raiz)
        mapa = resolvers.default_resolvers(self.repo)
        refs = (
            _ref_data_card(card),
            _ref("data_card", "inexistente__0123456789ab"),
            _ref("model_quality_result", manifest.evidence_id),
            _ref("model_quality_result", "qe-20261001T100000Z-abcdef"),
            _ref("model_quality_policy", politica.policy_id, locator="models/policy.json"),
            _ref("observed_metric", "m-1", locator="models/metricas.json", member="accuracy@test-ctx"),
            _ref("observed_metric", "m-1", locator="models/metricas.json", member="f1@test-ctx"),
            _ref("baseline_reference", "b-1", locator="models/baselines.json", member="base-naive"),
            _ref("drift_evidence", drift.drift_id, locator="models/drift.json"),
            _ref("execution_record", registro.execution_id),
            _ref("execution_record", "script__ffffffffffff"),
            _falso("../../x"),
        )
        for ref in refs:
            for resolver in mapa.values():
                resolver(ref)
        self.assertEqual(_arbol(self.raiz), antes)

    def test_no_crea_directorios_en_repo_vacio(self):
        antes = _arbol(self.raiz)
        for resolver in resolvers.default_resolvers(self.repo).values():
            resolver(_ref("data_card", "x-1__0123456789ab"))
            resolver(_falso("qe-20261001T100000Z-abcdef", locator="c.json", member="a@b"))
        self.assertEqual(_arbol(self.raiz), antes)
        self.assertFalse((self.repo / ".harmessi").exists())
        self.assertFalse((self.repo / "governance").exists())


if __name__ == "__main__":
    unittest.main()

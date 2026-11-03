"""Paridad de hashes, layout y patrones entre `tools/cards/resolvers.py` y los
paquetes reales `modelquality`, `qualityevidence`, `leadrun` y `datasources`
(Change `20261005-model-cards`, R24-R28, R31, R1).

`resolvers.py` y `modelcard.py` no pueden importar esos paquetes (R1): recomputan
los hashes a nivel de dict JSON con el mismo JSON canónico y duplican algunos
patrones. Este test fija que la duplicación sigue siendo exacta. Solo los tests
importan ambos lados.
"""
from __future__ import annotations

import ast
import json
import re
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from tools.cards import modelcard, resolvers
from tools.datasources import core as ds_core
from tools.leadrun import core as lr_core
from tools.modelquality import core as mq_core
from tools.qualityevidence import core as qe_core
from tools.qualityevidence import evidence as qe_evidence

REPO_ORIGEN = Path(__file__).resolve().parents[2]
DIR_CARDS = REPO_ORIGEN / "tools" / "cards"

RELOJ_DT = lambda: datetime(2026, 10, 1, 10, 0, 0, tzinfo=timezone.utc)  # noqa: E731


def _via_archivo_json(obj):
    """Ida y vuelta por disco con el mismo formato que los persistidores reales."""
    with tempfile.TemporaryDirectory() as tmp:
        ruta = Path(tmp) / "x.json"
        ruta.write_bytes((json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8"))
        with open(ruta, "r", encoding="utf-8") as f:
            return json.load(f)


def _politica(rica=False):
    contexto = mq_core.EvaluationContext(
        "test-ctx", "test", population="población ñ" if rica else "", extensions={"x_nota": [1, 2.5, None]} if rica else {}
    )
    requisito = mq_core.MetricRequirement(
        requirement_id="req-accuracy",
        metric_name="accuracy",
        direction="higher_is_better",
        required_context=contexto,
        threshold_value=0.8,
        baseline_required=rica,
        comparison_tolerance=0.01 if rica else None,
        min_sample_size=30 if rica else None,
        description="descripción con acentos" if rica else "",
    )
    return mq_core.ModelQualityPolicy(
        policy_id="pol-clasificador", model_task_role="classification", requirements=(requisito,),
        description="política ñ" if rica else "",
    )


def _drift(umbral=0.1):
    base = qe_evidence.describe_source_generated("ventana base ñ", {"k": 1, "z": [1.5, "ñ"]}, role="baseline")
    actual = qe_evidence.describe_source_generated("ventana actual", {"k": 2}, role="current")
    return qe_evidence.build_drift_evidence(
        metric_name="accuracy",
        baseline_value=0.9,
        current_value=0.85,
        baseline_window=base,
        baseline_label="entrenamiento",
        current_window=actual,
        current_label="produccion",
        comparison_mode="absolute_diff",
        threshold=umbral,
        clock=RELOJ_DT,
    )


def _registro(stdout="ok", command_form="script"):
    campos = {
        "command_form": command_form,
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
    # Misma construcción que `tools/leadrun/runtime.py` (ejecutar, paso 4).
    execution_id = f"{command_form}__{lr_core.content_sha256(campos)[:12]}"
    return lr_core.ExecutionRecord(
        execution_id=execution_id,
        command_form=command_form,
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


class TestParidadPolitica(unittest.TestCase):
    def test_hash_policy_igual_a_content_sha256_real(self):
        for rica in (False, True):
            politica = _politica(rica)
            with self.subTest(rica=rica, via="dict"):
                self.assertEqual(resolvers.hash_policy(politica.to_dict()), politica.content_sha256())
            with self.subTest(rica=rica, via="archivo"):
                self.assertEqual(resolvers.hash_policy(_via_archivo_json(politica.to_dict())), politica.content_sha256())

    def test_limitacion_conocida_politica_a_mano_con_defaults_omitidos_no_coincide(self):
        """LIMITACIÓN CONOCIDA (R31): `hash_policy` hashea el dict TAL CUAL está en
        el archivo. Una política escrita a mano que omite campos con default (que
        `from_dict` rellena) es la MISMA política lógica pero NO produce el hash de
        `ModelQualityPolicy.content_sha256()`. Para pinnear hay que escribir la
        forma `to_dict()`."""
        a_mano = {
            "policy_id": "pol-clasificador",
            "model_task_role": "classification",
            "schema_version": 1,
            "requirements": [
                {
                    "requirement_id": "req-accuracy",
                    "metric_name": "accuracy",
                    "direction": "higher_is_better",
                    "threshold_value": 0.8,
                    "required_context": {"context_id": "test-ctx", "split": "test"},
                }
            ],
        }
        reconstruida = mq_core.ModelQualityPolicy.from_dict(a_mano)
        self.assertEqual(reconstruida.policy_id, "pol-clasificador")
        self.assertNotEqual(resolvers.hash_policy(a_mano), reconstruida.content_sha256())
        self.assertEqual(resolvers.hash_policy(reconstruida.to_dict()), reconstruida.content_sha256())

    def test_hash_policy_rechaza_no_dict(self):
        for malo in (None, [], "x", 5):
            with self.subTest(malo=malo):
                with self.assertRaises(resolvers.CardError):
                    resolvers.hash_policy(malo)

    def test_resolver_sobre_politica_escrita_como_to_dict(self):
        politica = _politica(rica=True)
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "models").mkdir()
            (repo / "models" / "p.json").write_text(json.dumps(politica.to_dict()), encoding="utf-8")
            ref = type("R", (), {"ref_id": politica.policy_id, "locator": "models/p.json"})()
            res = resolvers.model_quality_policy_resolver(repo)(ref)
            self.assertEqual(res.state, "found", res.detail)
            self.assertEqual(res.current_sha256, politica.content_sha256())


class TestParidadDrift(unittest.TestCase):
    def test_hash_drift_igual_a_content_sha256_real(self):
        """`DriftEvidence.to_dict()` agrega `content_sha256` al dict; el hash del
        resolver debe coincidir igualmente con `DriftEvidence.content_sha256()`
        (que hashea el dict base SIN `generated_at` ni `content_sha256`)."""
        drift = _drift()
        self.assertEqual(resolvers.hash_drift(drift.to_dict()), drift.content_sha256())

    def test_hash_drift_igual_via_archivo(self):
        drift = _drift()
        self.assertEqual(resolvers.hash_drift(_via_archivo_json(drift.to_dict())), drift.content_sha256())

    def test_hash_drift_sobre_el_dict_base_sin_content_sha256_coincide(self):
        """Diagnóstico: sin la clave `content_sha256` el hash sí coincide; la
        divergencia del test anterior (si falla) se debe a esa clave."""
        drift = _drift()
        base = {k: v for k, v in drift.to_dict().items() if k != "content_sha256"}
        self.assertEqual(resolvers.hash_drift(base), drift.content_sha256())

    def test_hash_drift_ignora_generated_at(self):
        drift = _drift()
        datos = drift.to_dict()
        self.assertEqual(resolvers.hash_drift(dict(datos, generated_at="2031-01-01T00:00:00Z")), resolvers.hash_drift(datos))

    def test_hash_drift_cambia_con_el_contenido(self):
        self.assertNotEqual(resolvers.hash_drift(_drift(0.1).to_dict()), resolvers.hash_drift(_drift(0.2).to_dict()))

    def test_hash_drift_rechaza_no_dict(self):
        for malo in (None, [], "x", 5):
            with self.subTest(malo=malo):
                with self.assertRaises(resolvers.CardError):
                    resolvers.hash_drift(malo)

    def test_resolver_devuelve_content_sha256_de_la_evidencia(self):
        drift = _drift()
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "models").mkdir()
            (repo / "models" / "d.json").write_text(json.dumps(drift.to_dict()), encoding="utf-8")
            ref = type("R", (), {"ref_id": drift.drift_id, "locator": "models/d.json"})()
            res = resolvers.drift_evidence_resolver(repo)(ref)
            self.assertEqual(res.state, "found", res.detail)
            self.assertEqual(res.current_sha256, drift.content_sha256())


class TestParidadExecutionRecord(unittest.TestCase):
    def test_relacion_real_entre_execution_id_y_hash_de_identidad(self):
        """`execution_id = <command_form>__<hash12>` con hash12 = sha256 canónico
        de los campos de identidad (el record SIN `execution_id` ni `generated_at`),
        verificado leyendo `leadrun.runtime`. `hash_execution_record` hashea el
        record SIN `generated_at` pero CON `execution_id`: es un hash distinto
        (de documento), coherente con el id pero no igual a él."""
        registro = _registro()
        datos = registro.to_dict()
        identidad = {k: v for k, v in datos.items() if k not in ("execution_id", "generated_at")}
        command_form, hash12 = registro.execution_id.split("__")
        self.assertEqual(command_form, registro.command_form)
        self.assertEqual(hash12, lr_core.content_sha256(identidad)[:12])
        self.assertEqual(hash12, resolvers._sha256_canonico(identidad)[:12])
        # El hash del documento incluye execution_id.
        documento = {k: v for k, v in datos.items() if k != "generated_at"}
        self.assertEqual(resolvers.hash_execution_record(datos), lr_core.content_sha256(documento))
        self.assertNotEqual(resolvers.hash_execution_record(datos), lr_core.content_sha256(identidad))

    def test_hash_execution_record_ignora_generated_at(self):
        datos = _registro().to_dict()
        self.assertEqual(
            resolvers.hash_execution_record(dict(datos, generated_at="2031-01-01T00:00:00Z")),
            resolvers.hash_execution_record(datos),
        )

    def test_hash_execution_record_cambia_con_el_contenido_y_con_el_id(self):
        base = _registro().to_dict()
        self.assertNotEqual(resolvers.hash_execution_record(base), resolvers.hash_execution_record(dict(base, exit_code=1)))
        self.assertNotEqual(
            resolvers.hash_execution_record(base),
            resolvers.hash_execution_record(dict(base, execution_id="script__ffffffffffff")),
        )

    def test_hash_execution_record_rechaza_no_dict(self):
        for malo in (None, [], "x", 5):
            with self.subTest(malo=malo):
                with self.assertRaises(resolvers.CardError):
                    resolvers.hash_execution_record(malo)

    def test_resolver_sobre_persistencia_real_de_leadrun(self):
        """Usa `runtime._persistir_registro` (el escritor real): fija el layout."""
        from tools.leadrun import runtime as lr_runtime

        registro = _registro(stdout="entrenado ñ")
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            self.assertIsNone(lr_runtime._persistir_registro(repo, registro))
            archivo = repo / ".harmessi" / "executions" / registro.execution_id / "record.json"
            self.assertTrue(archivo.is_file())
            ref = type("R", (), {"ref_id": registro.execution_id})()
            res = resolvers.execution_record_resolver(repo)(ref)
            self.assertEqual(res.state, "found", res.detail)
            self.assertEqual(res.current_sha256, resolvers.hash_execution_record(registro.to_dict()))

    def test_layout_coincide_con_el_del_escritor_real(self):
        texto = (REPO_ORIGEN / "tools" / "leadrun" / "runtime.py").read_text(encoding="utf-8")
        self.assertIn('/ ".harmessi" / "executions"', texto)
        self.assertIn('"record.json"', texto)
        self.assertEqual(resolvers._DIR_HARMESSI, ".harmessi")

    def test_command_forms_reales_cumplen_el_patron_de_ref_id(self):
        for forma in lr_core.EXECUTION_FORMS:
            registro = _registro(command_form=forma)
            with self.subTest(forma=forma):
                self.assertIsNotNone(resolvers._RE_REF_EJECUCION.fullmatch(registro.execution_id))


class TestParidadHashDocumento(unittest.TestCase):
    CASOS = (
        [],
        [{"b": 1, "a": 2}],
        [{"metric_name": "accuracy", "value": 0.9, "context": {"context_id": "c", "split": "test"}}],
        [{"nombre": "ñandú", "x": [1, 2.5, None, True]}],
        {"k": "v"},
    )

    def test_hash_document_determinista(self):
        for caso in self.CASOS:
            with self.subTest(caso=caso):
                self.assertEqual(resolvers.hash_document(caso), resolvers.hash_document(json.loads(json.dumps(caso))))
                self.assertRegex(resolvers.hash_document(caso), r"[0-9a-f]{64}")

    def test_hash_document_independiente_del_orden_de_claves_pero_no_de_la_lista(self):
        self.assertEqual(resolvers.hash_document({"a": 1, "b": 2}), resolvers.hash_document({"b": 2, "a": 1}))
        self.assertNotEqual(resolvers.hash_document([1, 2]), resolvers.hash_document([2, 1]))

    def test_paridad_canonica_con_datasources(self):
        for caso in self.CASOS:
            with self.subTest(caso=caso):
                self.assertEqual(resolvers.hash_document(caso), ds_core.content_sha256(caso))

    def test_paridad_con_listas_reales_de_modelquality(self):
        contexto = mq_core.EvaluationContext("test-ctx", "test")
        metricas = [
            mq_core.ObservedMetric("accuracy", 0.9, contexto).to_dict(),
            mq_core.ObservedMetric("recall", 0.7, contexto).to_dict(),
        ]
        baselines = [mq_core.BaselineReference("base-naive", "accuracy", 0.5, contexto, "mayoritaria").to_dict()]
        for documento in (metricas, baselines):
            self.assertEqual(resolvers.hash_document(documento), resolvers.hash_document(_via_archivo_json(documento)))
            self.assertEqual(resolvers.hash_document(documento), ds_core.content_sha256(documento))

    def test_hash_document_rechaza_no_serializables(self):
        for malo in (float("nan"), {"a": float("inf")}, object()):
            with self.subTest(malo=malo):
                with self.assertRaises(resolvers.CardError):
                    resolvers.hash_document(malo)


class TestParidadMiembrosYPatrones(unittest.TestCase):
    def test_identidad_de_metrica_y_baseline_es_la_de_modelquality(self):
        contexto = mq_core.EvaluationContext("test-ctx", "test")
        metrica = mq_core.ObservedMetric("accuracy", 0.9, contexto).to_dict()
        baseline = mq_core.BaselineReference("base-naive", "accuracy", 0.5, contexto, "mayoritaria").to_dict()
        self.assertEqual(resolvers._identidad_metrica(metrica), "accuracy@test-ctx")
        self.assertEqual(resolvers._identidad_baseline(baseline), "base-naive")

    def test_arroba_no_puede_aparecer_en_metric_name_ni_context_id(self):
        contexto = mq_core.EvaluationContext("test-ctx", "test")
        with self.assertRaises(mq_core.ModelQualityError):
            mq_core.ObservedMetric("acc@x", 0.9, contexto)
        with self.assertRaises(mq_core.ModelQualityError):
            mq_core.EvaluationContext("ctx@x", "test")
        with self.assertRaises(mq_core.ModelQualityError):
            mq_core.BaselineReference("b@x", "accuracy", 0.5, contexto, "s")

    def test_patrones_de_qe_y_dr_iguales_a_qualityevidence(self):
        self.assertEqual(resolvers._RE_EVIDENCE_ID.pattern, qe_core._PATRON_EVIDENCE_ID.pattern)
        self.assertEqual(resolvers._RE_DRIFT_ID.pattern, qe_core._PATRON_DRIFT_ID.pattern)
        self.assertEqual(modelcard._RE_RESULT_REF.pattern, qe_core._PATRON_EVIDENCE_ID.pattern)
        self.assertEqual(modelcard._RE_DRIFT_REF.pattern, qe_core._PATRON_DRIFT_ID.pattern)

    def test_ids_generados_por_el_codigo_real_cumplen_los_patrones(self):
        self.assertIsNotNone(resolvers._RE_EVIDENCE_ID.fullmatch(qe_evidence.new_evidence_id()))
        self.assertIsNotNone(resolvers._RE_DRIFT_ID.fullmatch(qe_evidence.new_drift_id()))
        self.assertIsNotNone(modelcard._RE_RESULT_REF.fullmatch(qe_evidence.new_evidence_id()))
        self.assertIsNotNone(modelcard._RE_DRIFT_REF.fullmatch(qe_evidence.new_drift_id()))
        self.assertIsNone(resolvers._RE_DRIFT_ID.fullmatch(qe_evidence.new_evidence_id()))
        self.assertIsNone(resolvers._RE_EVIDENCE_ID.fullmatch(qe_evidence.new_drift_id()))

    def test_subject_kind_de_modelquality_existe_en_qualityevidence(self):
        self.assertIn(resolvers.SUBJECT_MODEL_QUALITY_EVALUATION, qe_core.SUBJECT_KINDS)

    def test_roles_de_tarea_de_modelquality_son_validos_en_modelcard_sin_enum(self):
        patron = re.compile(modelcard.TASK_ROLE_PATTERN)
        for rol in mq_core.MODEL_TASK_ROLES:
            with self.subTest(rol=rol):
                self.assertIsNotNone(patron.fullmatch(rol))
        self.assertIsNotNone(patron.fullmatch("custom_role"))

    def test_model_task_roles_no_se_importa_en_produccion(self):
        for nombre in ("modelcard.py", "resolvers.py"):
            arbol = ast.parse((DIR_CARDS / nombre).read_text(encoding="utf-8"))
            with self.subTest(archivo=nombre):
                for nodo in ast.walk(arbol):
                    if isinstance(nodo, ast.ImportFrom):
                        self.assertNotIn("modelquality", (nodo.module or "").split("."))
                        self.assertNotIn("MODEL_TASK_ROLES", [a.name for a in nodo.names])
                    elif isinstance(nodo, ast.Import):
                        self.assertFalse(any("modelquality" in a.name for a in nodo.names))
                    elif isinstance(nodo, ast.Name):
                        self.assertNotEqual(nodo.id, "MODEL_TASK_ROLES")
                    elif isinstance(nodo, ast.Attribute):
                        self.assertNotEqual(nodo.attr, "MODEL_TASK_ROLES")


if __name__ == "__main__":
    unittest.main()

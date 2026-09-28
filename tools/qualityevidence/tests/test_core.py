"""Tests de `tools.qualityevidence.core` (v0.7 Change 3,
`20260922-quality-evidence-and-drift`). Cobertura de `spec.md` R1-R10.
Sin I/O, sin pandas/numpy, sin aleatoriedad."""
from __future__ import annotations

import unittest

from tools.qualityevidence import core as qe


# --- Fixtures ----------------------------------------------------------------


def _source_file(**overrides) -> qe.EvidenceSource:
    base = dict(kind="file", role="profile", path="data/interim/profile.json", sha256="a" * 64)
    base.update(overrides)
    return qe.EvidenceSource(**base)


def _source_generated(**overrides) -> qe.EvidenceSource:
    base = dict(kind="generated", role="input", description="conteo sintético", params={"n": 10}, sha256="b" * 64)
    base.update(overrides)
    return qe.EvidenceSource(**base)


def _declaration(**overrides) -> qe.DeclarationRef:
    base = dict(declaration_kind="data_contract", declaration_id="c1", content_sha256="a" * 64)
    base.update(overrides)
    return qe.DeclarationRef(**base)


def _manifest(**overrides) -> qe.QualityEvidenceManifest:
    base = dict(
        evidence_id="qe-20260922T120000Z-abc123",
        subject_kind="data_contract_evaluation",
        declaration=_declaration(),
        source=_source_file(),
        generated_at="2026-09-22T12:00:00Z",
        check_results=({"status": "PASS", "code": "X", "message": "ok"},),
        technical_errors=(),
    )
    base.update(overrides)
    return qe.QualityEvidenceManifest(**base)


def _drift(**overrides) -> qe.DriftEvidence:
    base = dict(
        drift_id="dr-20260922T120000Z-abc123",
        metric_name="nulls_rate",
        baseline_window=_source_file(role="baseline"),
        baseline_label="baseline",
        current_window=_source_file(role="current"),
        current_label="current",
        baseline_value=0.02,
        current_value=0.07,
        comparison_mode="absolute_diff",
        observed_difference=0.05,
        threshold=0.03,
        result_status="FAIL",
        result_message="diferencia supera el threshold",
        generated_at="2026-09-22T12:00:00Z",
    )
    base.update(overrides)
    return qe.DriftEvidence(**base)


# --- R2/R3: vocabularios e ids -------------------------------------------------


class TestVocabulariosEIds(unittest.TestCase):
    def test_schema_version(self):
        self.assertEqual(qe.SCHEMA_VERSION, 1)

    def test_subject_kinds(self):
        self.assertEqual(qe.SUBJECT_KINDS, ("data_contract_evaluation", "model_quality_evaluation"))

    def test_evidence_source_kinds(self):
        self.assertEqual(qe.EVIDENCE_SOURCE_KINDS, ("file", "generated"))

    def test_drift_comparison_modes(self):
        self.assertEqual(qe.DRIFT_COMPARISON_MODES, ("absolute_diff", "relative_diff"))

    def test_evidence_id_valido(self):
        _manifest(evidence_id="qe-20260922T120000Z-abc123")  # no lanza

    def test_evidence_id_invalido(self):
        with self.assertRaises(qe.QualityEvidenceError):
            _manifest(evidence_id="evidencia-1")

    def test_drift_id_invalido(self):
        with self.assertRaises(qe.QualityEvidenceError):
            _drift(drift_id="drift-1")

    def test_metric_name_invalido_mayusculas(self):
        with self.assertRaises(qe.QualityEvidenceError):
            _drift(metric_name="AUC")

    def test_metric_name_invalido_empieza_con_numero(self):
        with self.assertRaises(qe.QualityEvidenceError):
            _drift(metric_name="1_metric")

    def test_metric_name_valido(self):
        _drift(metric_name="nulls_rate")  # no lanza


# --- R4: EvidenceSource --------------------------------------------------------


class TestEvidenceSource(unittest.TestCase):
    def test_kind_file_ruta_absoluta_error(self):
        with self.assertRaises(qe.QualityEvidenceError):
            _source_file(path="C:/abs/ruta.json")

    def test_kind_file_sha256_no_hex_error(self):
        with self.assertRaises(qe.QualityEvidenceError):
            _source_file(sha256="abc")

    def test_kind_file_valido(self):
        fuente = _source_file(path="data/x.json", sha256="a" * 64)
        self.assertEqual(fuente.path, "data/x.json")

    def test_kind_generated_description_vacia_error(self):
        with self.assertRaises(qe.QualityEvidenceError):
            _source_generated(description="", params={})

    def test_kind_generated_valido(self):
        fuente = _source_generated(description="conteo sintético", params={"n": 10}, sha256="a" * 64)
        self.assertEqual(fuente.kind, "generated")

    def test_kind_file_con_description_error(self):
        with self.assertRaises(qe.QualityEvidenceError):
            _source_file(description="no debería estar acá")

    def test_kind_file_con_params_error(self):
        with self.assertRaises(qe.QualityEvidenceError):
            _source_file(params={"a": 1})

    def test_kind_generated_con_path_error(self):
        with self.assertRaises(qe.QualityEvidenceError):
            _source_generated(path="data/x.json")

    def test_kind_file_path_relativo_con_backslash_error(self):
        with self.assertRaises(qe.QualityEvidenceError):
            _source_file(path="data\\x.json")

    def test_kind_file_path_con_dotdot_error(self):
        with self.assertRaises(qe.QualityEvidenceError):
            _source_file(path="../fuera/x.json")

    def test_kind_fuera_de_vocabulario_error(self):
        with self.assertRaises(qe.QualityEvidenceError):
            qe.EvidenceSource(kind="url", role="input")

    def test_copia_profunda_de_params(self):
        params = {"n": 10}
        fuente = _source_generated(params=params)
        params["n"] = 999
        self.assertEqual(fuente.params["n"], 10)


# --- R5/R6: DeclarationRef/ScopeWindow ------------------------------------------


class TestDeclarationRef(unittest.TestCase):
    def test_content_sha256_no_hex_error(self):
        with self.assertRaises(qe.QualityEvidenceError):
            _declaration(content_sha256="z")

    def test_valido(self):
        _declaration(content_sha256="a" * 64)  # no lanza

    def test_declaration_kind_vacio_error(self):
        with self.assertRaises(qe.QualityEvidenceError):
            _declaration(declaration_kind="")


class TestScopeWindow(unittest.TestCase):
    def test_start_mayor_que_end_error(self):
        with self.assertRaises(qe.QualityEvidenceError):
            qe.ScopeWindow(time_start="2026-09-01", time_end="2026-08-01")

    def test_solo_start_valido(self):
        ventana = qe.ScopeWindow(time_start="2026-09-01", time_end=None)
        self.assertEqual(ventana.time_start, "2026-09-01")

    def test_default_vacio_valido(self):
        ventana = qe.ScopeWindow()
        self.assertEqual(ventana.population, "")


# --- R7: QualityEvidenceManifest ------------------------------------------------


class TestQualityEvidenceManifest(unittest.TestCase):
    def test_subject_kind_invalido_error(self):
        with self.assertRaises(qe.QualityEvidenceError):
            _manifest(subject_kind="otro")

    def test_check_results_clave_ajena_error(self):
        with self.assertRaises(qe.QualityEvidenceError):
            _manifest(check_results=({"status": "PASS", "code": "X", "message": "ok", "extra": 1},))

    def test_schema_version_incorrecto_constructor_error(self):
        with self.assertRaises(qe.QualityEvidenceError):
            _manifest(schema_version=2)

    def test_schema_version_incorrecto_from_dict_error(self):
        datos = _manifest().to_dict()
        datos["schema_version"] = 2
        with self.assertRaises(qe.QualityEvidenceError):
            qe.QualityEvidenceManifest.from_dict(datos)

    def test_generated_at_invalido_error(self):
        with self.assertRaises(qe.QualityEvidenceError):
            _manifest(generated_at="no es fecha")

    def test_check_results_status_invalido_error(self):
        with self.assertRaises(qe.QualityEvidenceError):
            _manifest(check_results=({"status": "OK", "code": "X", "message": "m"},))

    def test_check_results_code_vacio_error(self):
        with self.assertRaises(qe.QualityEvidenceError):
            _manifest(check_results=({"status": "PASS", "code": "", "message": "m"},))

    def test_separa_check_results_y_technical_errors_como_campos_propios(self):
        manifest = _manifest(
            check_results=({"status": "PASS", "code": "X", "message": "ok"},),
            technical_errors=({"status": "FAIL", "code": "Y", "message": "mal"},),
        )
        self.assertEqual(len(manifest.check_results), 1)
        self.assertEqual(len(manifest.technical_errors), 1)

    def test_sin_argumentos_de_datos_crudos(self):
        # Ningún constructor de core.py acepta 'data'/'frame'/'dataframe'/'predictions'/'rows'.
        import inspect

        for cls in (qe.EvidenceSource, qe.DeclarationRef, qe.ScopeWindow, qe.QualityEvidenceManifest, qe.DriftEvidence):
            firma = inspect.signature(cls.__init__)
            prohibidos = {"data", "frame", "dataframe", "predictions", "rows"}
            self.assertFalse(prohibidos & set(firma.parameters), f"{cls.__name__} acepta un parámetro prohibido")


# --- R8: DriftEvidence -----------------------------------------------------------


class TestDriftEvidence(unittest.TestCase):
    def test_comparison_mode_invalido_error(self):
        with self.assertRaises(qe.QualityEvidenceError):
            _drift(comparison_mode="percentual")

    def test_threshold_negativo_error(self):
        with self.assertRaises(qe.QualityEvidenceError):
            _drift(threshold=-0.1)

    def test_threshold_none_valido(self):
        _drift(threshold=None, result_status="N/A", result_message="sin threshold")  # no lanza

    def test_result_status_invalido_error(self):
        with self.assertRaises(qe.QualityEvidenceError):
            _drift(result_status="OK")

    def test_observed_difference_no_recalculado(self):
        # core.py NO recalcula observed_difference: acepta el valor pasado tal cual.
        drift = _drift(comparison_mode="absolute_diff", baseline_value=1, current_value=2, observed_difference=999.0)
        self.assertEqual(drift.observed_difference, 999.0)


# --- R10: serialización determinista --------------------------------------------


class TestSerializacionDeterminista(unittest.TestCase):
    def test_manifest_roundtrip_content_sha256_identico(self):
        manifest = _manifest()
        reconstruido = qe.QualityEvidenceManifest.from_dict(manifest.to_dict())
        self.assertEqual(manifest.content_sha256(), reconstruido.content_sha256())

    def test_manifest_generated_at_distinto_mismo_hash(self):
        manifest_1 = _manifest(generated_at="2026-09-22T12:00:00Z")
        manifest_2 = _manifest(generated_at="2026-09-23T08:30:00Z")
        self.assertEqual(manifest_1.content_sha256(), manifest_2.content_sha256())

    def test_manifest_cambiar_message_cambia_hash(self):
        manifest_1 = _manifest(check_results=({"status": "PASS", "code": "X", "message": "ok"},))
        manifest_2 = _manifest(check_results=({"status": "PASS", "code": "X", "message": "otro"},))
        self.assertNotEqual(manifest_1.content_sha256(), manifest_2.content_sha256())

    def test_drift_roundtrip_content_sha256_identico(self):
        drift = _drift()
        reconstruido = qe.DriftEvidence.from_dict(drift.to_dict())
        self.assertEqual(drift.content_sha256(), reconstruido.content_sha256())

    def test_drift_generated_at_distinto_mismo_hash(self):
        drift_1 = _drift(generated_at="2026-09-22T12:00:00Z")
        drift_2 = _drift(generated_at="2026-09-23T08:30:00Z")
        self.assertEqual(drift_1.content_sha256(), drift_2.content_sha256())

    def test_canonical_json_orden_de_claves(self):
        texto_1 = qe.canonical_json({"b": 1, "a": 2})
        texto_2 = qe.canonical_json({"a": 2, "b": 1})
        self.assertEqual(texto_1, texto_2)

    def test_canonical_json_no_serializable_error(self):
        with self.assertRaises(qe.QualityEvidenceError):
            qe.canonical_json({"x": object()})


if __name__ == "__main__":
    unittest.main()

"""Tests de `tools.qualityevidence.evidence` (v0.7 Change 3,
`20260922-quality-evidence-and-drift`). Cobertura de `spec.md` R11-R19.
Fixtures sintéticas de `profile.json`/`guardrails.json` (`tempfile`, nunca un
dataset ni perfil real); se limpian tras cada test. Sin I/O de red, sin
pandas/numpy, sin aleatoriedad no controlada (usan `clock`/`suffix` fijos)."""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from dsguard import checks

from tools.qualityevidence import core as qe
from tools.qualityevidence import evidence as qeev


# --- Fixtures ------------------------------------------------------------------


def _repo_con_archivo(relpath: str, contenido: str, guardrails: dict = None):
    """`(TemporaryDirectory, repo_root: Path, ruta_absoluta: Path)`. Si se pasa
    `guardrails`, escribe `.claude/guardrails.json` con ese contenido."""
    tmp = tempfile.TemporaryDirectory()
    repo = Path(tmp.name)
    if guardrails is not None:
        claude_dir = repo / ".claude"
        claude_dir.mkdir(parents=True, exist_ok=True)
        (claude_dir / "guardrails.json").write_text(json.dumps(guardrails), encoding="utf-8")
    destino = repo / relpath
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(contenido, encoding="utf-8")
    return tmp, repo, destino


def _perfil_json(filas=1000, columnas_detalle=None) -> str:
    return json.dumps(
        {
            "filas": filas,
            "columnas_detalle": columnas_detalle
            or {"edad": {"nulls": {"count": 5}, "unique": {"count": 40}, "min": 18, "max": 90}},
        }
    )


_CLOCK_FIJO = lambda: datetime(2026, 9, 22, 12, 0, 0, tzinfo=timezone.utc)  # noqa: E731


def _declaracion(**overrides) -> qe.DeclarationRef:
    base = dict(declaration_kind="data_contract", declaration_id="c1", content_sha256="a" * 64)
    base.update(overrides)
    return qe.DeclarationRef(**base)


def _fuente_generada(**overrides) -> qe.EvidenceSource:
    base = dict(kind="generated", role="input", description="fuente sintética", params={"n": 1}, sha256="b" * 64)
    base.update(overrides)
    return qe.EvidenceSource(**base)


# --- R11: códigos ----------------------------------------------------------------


class TestCodigos(unittest.TestCase):
    def test_ocho_codigos_unicos(self):
        self.assertEqual(len(qeev.CODES), 8)
        self.assertEqual(len(set(qeev.CODES)), 8)

    def test_codigos_esperados(self):
        esperados = {
            "QUALITYEVIDENCE-INPUT",
            "QUALITYEVIDENCE-SOURCE-DENIED",
            "QUALITYEVIDENCE-SOURCE-MISSING",
            "QUALITYEVIDENCE-WRITE",
            "QUALITYEVIDENCE-READ",
            "QUALITYEVIDENCE-STALE",
            "QUALITYEVIDENCE-DRIFT-FIELD",
            "QUALITYEVIDENCE-DRIFT-DENIED",
        }
        self.assertEqual(set(qeev.CODES), esperados)


# --- R12: hash y escritura --------------------------------------------------------


class TestHashYEscritura(unittest.TestCase):
    def test_sha256_archivo_coincide_con_hashlib(self):
        tmp, repo, ruta = _repo_con_archivo("x/data.bin", "contenido conocido")
        try:
            esperado = hashlib.sha256(b"contenido conocido").hexdigest()
            self.assertEqual(qeev._sha256_archivo(ruta), esperado)
        finally:
            tmp.cleanup()

    def test_escritura_atomica_produce_archivo_legible(self):
        tmp, repo, _ = _repo_con_archivo("marker.txt", "x")
        try:
            destino = repo / "sub" / "y.json"
            qeev._escribir_atomico(destino, b'{"a":1}')
            self.assertEqual(destino.read_bytes(), b'{"a":1}')
        finally:
            tmp.cleanup()


# --- R13: describe_source_* -------------------------------------------------------


class TestDescribeSourceFile(unittest.TestCase):
    def test_denegado_por_holdout_nunca_abre_el_archivo(self):
        tmp, repo, ruta = _repo_con_archivo(
            "data/holdout/profile.json", _perfil_json(), guardrails={"holdouts": ["data/holdout/**"]}
        )
        try:
            with mock.patch.object(Path, "is_file", side_effect=AssertionError("no debía abrirse")):
                with self.assertRaises(qe.QualityEvidenceError) as ctx:
                    qeev.describe_source_file(repo, ruta, role="profile")
            self.assertIn("QUALITYEVIDENCE-SOURCE-DENIED", str(ctx.exception))
        finally:
            tmp.cleanup()

    def test_ruta_inexistente_missing(self):
        tmp, repo, _ = _repo_con_archivo("marker.txt", "x")
        try:
            with self.assertRaises(qe.QualityEvidenceError) as ctx:
                qeev.describe_source_file(repo, "no/existe.json", role="profile")
            self.assertIn("QUALITYEVIDENCE-SOURCE-MISSING", str(ctx.exception))
        finally:
            tmp.cleanup()

    def test_path_relativo_y_posix(self):
        tmp, repo, ruta = _repo_con_archivo("data/interim/profile.json", _perfil_json())
        try:
            fuente = qeev.describe_source_file(repo, ruta, role="profile")
            self.assertEqual(fuente.path, "data/interim/profile.json")
            self.assertNotIn("\\", fuente.path)
        finally:
            tmp.cleanup()


class TestDescribeSourceGenerated(unittest.TestCase):
    def test_determinista(self):
        fuente_1 = qeev.describe_source_generated("desc", {"a": 1}, role="input")
        fuente_2 = qeev.describe_source_generated("desc", {"a": 1}, role="input")
        self.assertEqual(fuente_1.sha256, fuente_2.sha256)

    def test_description_vacia_error(self):
        with self.assertRaises(qe.QualityEvidenceError):
            qeev.describe_source_generated("", {"a": 1}, role="input")


# --- R14/R15/R16: manifest ---------------------------------------------------------


class TestBuildManifest(unittest.TestCase):
    def test_separa_check_results_y_technical_errors(self):
        resultados = [
            checks.CheckResult(status="PASS", code="X", message="ok"),
            checks.CheckResult(status="FAIL", code="Y", message="mal", kind="technical_error"),
        ]
        manifest = qeev.build_manifest(
            subject_kind="data_contract_evaluation",
            declaration=_declaracion(),
            source=_fuente_generada(),
            results=resultados,
            clock=_CLOCK_FIJO,
        )
        self.assertEqual(len(manifest.check_results), 1)
        self.assertEqual(len(manifest.technical_errors), 1)

    def test_declaracion_incoherente_con_subject_kind_error(self):
        with self.assertRaises(qe.QualityEvidenceError):
            qeev.build_manifest(
                subject_kind="model_quality_evaluation",
                declaration=_declaracion(declaration_kind="data_contract"),
                source=_fuente_generada(),
                results=[],
                clock=_CLOCK_FIJO,
            )

    def test_results_no_lista_error(self):
        with self.assertRaises(qe.QualityEvidenceError) as ctx:
            qeev.build_manifest(
                subject_kind="data_contract_evaluation",
                declaration=_declaracion(),
                source=_fuente_generada(),
                results="no es una lista",
                clock=_CLOCK_FIJO,
            )
        self.assertIn("QUALITYEVIDENCE-INPUT", str(ctx.exception))


class TestWriteReadManifest(unittest.TestCase):
    def test_roundtrip(self):
        tmp, repo, _ = _repo_con_archivo("marker.txt", "x")
        try:
            manifest = qeev.build_manifest(
                subject_kind="data_contract_evaluation",
                declaration=_declaracion(),
                source=_fuente_generada(),
                results=[checks.CheckResult(status="PASS", code="X", message="ok")],
                clock=_CLOCK_FIJO,
            )
            ruta = qeev.write_manifest(repo, manifest)
            self.assertTrue(ruta.is_file())
            releido = qeev.read_manifest(repo, manifest.evidence_id)
            self.assertEqual(releido.to_dict(), manifest.to_dict())
        finally:
            tmp.cleanup()

    def test_idempotencia_mismo_contenido(self):
        tmp, repo, _ = _repo_con_archivo("marker.txt", "x")
        try:
            manifest = qeev.build_manifest(
                subject_kind="data_contract_evaluation",
                declaration=_declaracion(),
                source=_fuente_generada(),
                results=[],
                clock=_CLOCK_FIJO,
            )
            ruta_1 = qeev.write_manifest(repo, manifest)
            ruta_2 = qeev.write_manifest(repo, manifest)
            self.assertEqual(ruta_1, ruta_2)
        finally:
            tmp.cleanup()

    def test_colision_de_evidence_id_con_contenido_distinto(self):
        tmp, repo, _ = _repo_con_archivo("marker.txt", "x")
        try:
            manifest_1 = qeev.build_manifest(
                subject_kind="data_contract_evaluation",
                declaration=_declaracion(declaration_id="c1"),
                source=_fuente_generada(),
                results=[],
                clock=_CLOCK_FIJO,
                scope=None,
            )
            with mock.patch.object(qeev, "new_evidence_id", return_value=manifest_1.evidence_id):
                manifest_2 = qeev.build_manifest(
                    subject_kind="data_contract_evaluation",
                    declaration=_declaracion(declaration_id="c2"),
                    source=_fuente_generada(),
                    results=[],
                    clock=_CLOCK_FIJO,
                )
            self.assertEqual(manifest_1.evidence_id, manifest_2.evidence_id)
            self.assertNotEqual(manifest_1.content_sha256(), manifest_2.content_sha256())
            qeev.write_manifest(repo, manifest_1)
            with self.assertRaises(qe.QualityEvidenceError) as ctx:
                qeev.write_manifest(repo, manifest_2)
            self.assertIn("QUALITYEVIDENCE-WRITE", str(ctx.exception))
        finally:
            tmp.cleanup()

    def test_manifest_manipulado_a_mano_falla_en_lectura(self):
        tmp, repo, _ = _repo_con_archivo("marker.txt", "x")
        try:
            manifest = qeev.build_manifest(
                subject_kind="data_contract_evaluation",
                declaration=_declaracion(),
                source=_fuente_generada(),
                results=[checks.CheckResult(status="PASS", code="X", message="ok")],
                clock=_CLOCK_FIJO,
            )
            ruta = qeev.write_manifest(repo, manifest)
            datos = json.loads(ruta.read_text(encoding="utf-8"))
            datos["check_results"][0]["message"] = "manipulado"
            ruta.write_text(json.dumps(datos), encoding="utf-8")
            with self.assertRaises(qe.QualityEvidenceError) as ctx:
                qeev.read_manifest(repo, manifest.evidence_id)
            self.assertIn("QUALITYEVIDENCE-READ", str(ctx.exception))
        finally:
            tmp.cleanup()

    def test_read_manifest_inexistente_error(self):
        tmp, repo, _ = _repo_con_archivo("marker.txt", "x")
        try:
            with self.assertRaises(qe.QualityEvidenceError) as ctx:
                qeev.read_manifest(repo, "qe-20260922T120000Z-abc123")
            self.assertIn("QUALITYEVIDENCE-READ", str(ctx.exception))
        finally:
            tmp.cleanup()

    def test_mensajes_de_error_nunca_contienen_ruta_absoluta_del_repo(self):
        """R20: ni `write_manifest` ni `read_manifest` exponen la ruta absoluta
        local del repo en el texto de sus `QualityEvidenceError` -- usan la
        etiqueta repo-relativa posix (`.harmessi/quality/<evidence_id>/
        manifest.json`), mismo criterio que `describe_source_file`/
        `drift_from_profiles`."""
        tmp, repo, _ = _repo_con_archivo("marker.txt", "x")
        try:
            repo_str_absoluto = str(repo)

            # read_manifest: archivo inexistente.
            with self.assertRaises(qe.QualityEvidenceError) as ctx:
                qeev.read_manifest(repo, "qe-20260922T120000Z-abc123")
            self.assertNotIn(repo_str_absoluto, str(ctx.exception))

            # read_manifest: manifest manipulado (content_sha256 no coincide).
            manifest = qeev.build_manifest(
                subject_kind="data_contract_evaluation",
                declaration=_declaracion(),
                source=_fuente_generada(),
                results=[checks.CheckResult(status="PASS", code="X", message="ok")],
                clock=_CLOCK_FIJO,
            )
            ruta = qeev.write_manifest(repo, manifest)
            datos = json.loads(ruta.read_text(encoding="utf-8"))
            datos["check_results"][0]["message"] = "manipulado"
            ruta.write_text(json.dumps(datos), encoding="utf-8")
            with self.assertRaises(qe.QualityEvidenceError) as ctx:
                qeev.read_manifest(repo, manifest.evidence_id)
            self.assertNotIn(repo_str_absoluto, str(ctx.exception))

            # write_manifest: colisión de evidence_id con contenido distinto.
            with mock.patch.object(qeev, "new_evidence_id", return_value=manifest.evidence_id):
                manifest_colisionante = qeev.build_manifest(
                    subject_kind="data_contract_evaluation",
                    declaration=_declaracion(declaration_id="otro"),
                    source=_fuente_generada(),
                    results=[],
                    clock=_CLOCK_FIJO,
                )
            with self.assertRaises(qe.QualityEvidenceError) as ctx:
                qeev.write_manifest(repo, manifest_colisionante)
            self.assertNotIn(repo_str_absoluto, str(ctx.exception))

            # write_manifest: manifest existente ilegible/corrupto (JSON inválido a mano).
            ruta.write_text("no es json", encoding="utf-8")
            with self.assertRaises(qe.QualityEvidenceError) as ctx:
                qeev.write_manifest(repo, manifest)
            self.assertNotIn(repo_str_absoluto, str(ctx.exception))
        finally:
            tmp.cleanup()

    def test_escritura_atomica_interrumpida_no_deja_manifest_parcial(self):
        """Si `os.replace` falla a mitad de la escritura atómica de
        `write_manifest`, el archivo temporal se limpia (`_escribir_atomico`)
        y NO queda ningún `manifest.json` parcial en el destino final."""
        tmp, repo, _ = _repo_con_archivo("marker.txt", "x")
        try:
            manifest = qeev.build_manifest(
                subject_kind="data_contract_evaluation",
                declaration=_declaracion(),
                source=_fuente_generada(),
                results=[checks.CheckResult(status="PASS", code="X", message="ok")],
                clock=_CLOCK_FIJO,
            )
            ruta_destino = repo / ".harmessi" / "quality" / manifest.evidence_id / "manifest.json"

            with mock.patch("os.replace", side_effect=OSError("interrupción simulada")):
                with self.assertRaises(OSError):
                    qeev.write_manifest(repo, manifest)

            self.assertFalse(ruta_destino.exists(), "no debía quedar un manifest.json parcial en el destino")
            directorio = ruta_destino.parent
            if directorio.exists():
                restantes = list(directorio.iterdir())
                self.assertEqual(restantes, [], f"no debían quedar archivos temporales huérfanos: {restantes}")
        finally:
            tmp.cleanup()


# --- R17: build_drift_evidence -----------------------------------------------------


class TestBuildDriftEvidence(unittest.TestCase):
    def test_absolute_diff_fail(self):
        drift = qeev.build_drift_evidence(
            metric_name="nulls_rate",
            baseline_value=0.02,
            current_value=0.07,
            baseline_window=_fuente_generada(role="baseline"),
            baseline_label="b",
            current_window=_fuente_generada(role="current"),
            current_label="c",
            comparison_mode="absolute_diff",
            threshold=0.03,
            clock=_CLOCK_FIJO,
        )
        self.assertAlmostEqual(drift.observed_difference, 0.05)
        self.assertEqual(drift.result_status, "FAIL")

    def test_absolute_diff_pass(self):
        drift = qeev.build_drift_evidence(
            metric_name="nulls_rate",
            baseline_value=0.02,
            current_value=0.03,
            baseline_window=_fuente_generada(role="baseline"),
            baseline_label="b",
            current_window=_fuente_generada(role="current"),
            current_label="c",
            comparison_mode="absolute_diff",
            threshold=0.03,
            clock=_CLOCK_FIJO,
        )
        self.assertEqual(drift.result_status, "PASS")

    def test_relative_diff_fail(self):
        drift = qeev.build_drift_evidence(
            metric_name="unique_count",
            baseline_value=1000,
            current_value=1200,
            baseline_window=_fuente_generada(role="baseline"),
            baseline_label="b",
            current_window=_fuente_generada(role="current"),
            current_label="c",
            comparison_mode="relative_diff",
            threshold=0.15,
            clock=_CLOCK_FIJO,
        )
        self.assertAlmostEqual(drift.observed_difference, 0.20)
        self.assertEqual(drift.result_status, "FAIL")

    def test_relative_diff_baseline_cero_warn_sin_excepcion(self):
        drift = qeev.build_drift_evidence(
            metric_name="unique_count",
            baseline_value=0,
            current_value=5,
            baseline_window=_fuente_generada(role="baseline"),
            baseline_label="b",
            current_window=_fuente_generada(role="current"),
            current_label="c",
            comparison_mode="relative_diff",
            threshold=0.1,
            clock=_CLOCK_FIJO,
        )
        self.assertEqual(drift.result_status, "WARN")
        self.assertEqual(drift.observed_difference, 0.0)

    def test_threshold_none_siempre_na(self):
        for modo in qe.DRIFT_COMPARISON_MODES:
            drift = qeev.build_drift_evidence(
                metric_name="unique_count",
                baseline_value=10,
                current_value=12,
                baseline_window=_fuente_generada(role="baseline"),
                baseline_label="b",
                current_window=_fuente_generada(role="current"),
                current_label="c",
                comparison_mode=modo,
                threshold=None,
                clock=_CLOCK_FIJO,
            )
            self.assertEqual(drift.result_status, "N/A")


# --- R18: drift_from_profiles -------------------------------------------------------


class TestDriftFromProfiles(unittest.TestCase):
    def test_field_fuera_de_allowlist_error_sin_abrir_archivo(self):
        tmp, repo, _ = _repo_con_archivo("marker.txt", "x")
        try:
            with mock.patch.object(Path, "read_text", side_effect=AssertionError("no debía abrirse")):
                with self.assertRaises(qe.QualityEvidenceError) as ctx:
                    qeev.drift_from_profiles(
                        repo,
                        metric_name="m",
                        baseline_profile_path="a.json",
                        current_profile_path="b.json",
                        field="percentil_95",
                        comparison_mode="absolute_diff",
                    )
            self.assertIn("QUALITYEVIDENCE-DRIFT-FIELD", str(ctx.exception))
        finally:
            tmp.cleanup()

    def test_field_columna_sin_column_error(self):
        tmp, repo, _ = _repo_con_archivo("marker.txt", "x")
        try:
            with self.assertRaises(qe.QualityEvidenceError) as ctx:
                qeev.drift_from_profiles(
                    repo,
                    metric_name="m",
                    baseline_profile_path="a.json",
                    current_profile_path="b.json",
                    field="unique_count",
                    comparison_mode="absolute_diff",
                )
            self.assertIn("QUALITYEVIDENCE-DRIFT-FIELD", str(ctx.exception))
        finally:
            tmp.cleanup()

    def test_filas_relative_diff_fail(self):
        tmp, repo, _ = tempfile.TemporaryDirectory(), None, None
        try:
            repo = Path(tmp.name)
            (repo / "baseline.json").write_text(_perfil_json(filas=1000), encoding="utf-8")
            (repo / "current.json").write_text(_perfil_json(filas=1200), encoding="utf-8")
            drift = qeev.drift_from_profiles(
                repo,
                metric_name="filas_totales",
                baseline_profile_path="baseline.json",
                current_profile_path="current.json",
                field="filas",
                comparison_mode="relative_diff",
                threshold=0.15,
                clock=_CLOCK_FIJO,
            )
            self.assertEqual(drift.result_status, "FAIL")
            self.assertEqual(drift.baseline_window.path, "baseline.json")
            self.assertEqual(drift.current_window.path, "current.json")
        finally:
            tmp.cleanup()

    def test_una_ruta_denegada_ninguna_se_abre(self):
        tmp, repo, _ = tempfile.TemporaryDirectory(), None, None
        try:
            repo = Path(tmp.name)
            (repo / "baseline.json").write_text(_perfil_json(filas=1000), encoding="utf-8")
            (repo / "current.json").write_text(_perfil_json(filas=1200), encoding="utf-8")

            def _guard_selectivo(ruta_input, repo_root):
                if "baseline" in str(ruta_input):
                    return False, "denegado de prueba"
                return True, "ok"

            with mock.patch.object(qeev, "verificar_permitido", side_effect=_guard_selectivo):
                with mock.patch.object(Path, "read_text", side_effect=AssertionError("no debía abrirse")):
                    with self.assertRaises(qe.QualityEvidenceError) as ctx:
                        qeev.drift_from_profiles(
                            repo,
                            metric_name="filas_totales",
                            baseline_profile_path="baseline.json",
                            current_profile_path="current.json",
                            field="filas",
                            comparison_mode="relative_diff",
                            threshold=0.15,
                        )
            self.assertIn("QUALITYEVIDENCE-DRIFT-DENIED", str(ctx.exception))
        finally:
            tmp.cleanup()


# --- R19: resolve_evidence_ref -------------------------------------------------------


class TestResolveEvidenceRef(unittest.TestCase):
    def test_no_sigue_convencion(self):
        resultado = qeev.resolve_evidence_ref("notas/celda-3", "/no/importa")
        self.assertEqual(resultado["resolvable"], False)

    def test_sigue_y_resuelve(self):
        tmp, repo, _ = _repo_con_archivo("marker.txt", "x")
        try:
            manifest = qeev.build_manifest(
                subject_kind="data_contract_evaluation",
                declaration=_declaracion(),
                source=_fuente_generada(),
                results=[],
                clock=_CLOCK_FIJO,
            )
            qeev.write_manifest(repo, manifest)
            ref = f"quality:.harmessi/quality/{manifest.evidence_id}/manifest.json"
            resultado = qeev.resolve_evidence_ref(ref, repo)
            self.assertEqual(resultado["resolvable"], True)
            self.assertEqual(resultado["valid"], True)
            self.assertIsNotNone(resultado["manifest"])
        finally:
            tmp.cleanup()

    def test_sigue_y_no_resuelve(self):
        tmp, repo, _ = _repo_con_archivo("marker.txt", "x")
        try:
            ref = "quality:.harmessi/quality/qe-20260922T120000Z-ffffff/manifest.json"
            resultado = qeev.resolve_evidence_ref(ref, repo)
            self.assertEqual(resultado["resolvable"], True)
            self.assertEqual(resultado["valid"], False)
        finally:
            tmp.cleanup()

    def test_nunca_lanza_con_entrada_rara(self):
        resultado = qeev.resolve_evidence_ref(None, "/no/importa")
        self.assertEqual(resultado["resolvable"], False)


if __name__ == "__main__":
    unittest.main()

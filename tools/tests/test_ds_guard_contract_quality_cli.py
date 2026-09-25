"""Smoke tests de los 6 subcomandos `contract`/`quality` de `tools/ds_guard.py`
(v0.7 Change 4, `20260922-quality-integration-and-cli`, R2-R14/R21 de
`spec.md`). Fixtures 100% sintéticas (`tempfile`, un repo git temporal propio,
nunca este repositorio real ni datos reales). Corre `tools/ds_guard.py` real
como subproceso (mismo patrón que `tools/tests/test_readiness.py`)."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ORIGEN = Path(__file__).resolve().parents[2]
DS_GUARD = REPO_ORIGEN / "tools" / "ds_guard.py"


def _crear_repo_git_temporal(prefix: str = "cli_contract_quality_") -> Path:
    repo = Path(tempfile.mkdtemp(prefix=prefix))
    subprocess.run(["git", "init", "-q"], cwd=str(repo), check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(repo), check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(repo), check=True)
    (repo / "README.md").write_text("repo de prueba\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=str(repo), check=True)
    subprocess.run(["git", "commit", "-q", "-m", "inicial"], cwd=str(repo), check=True)
    return repo


def _correr_ds_guard(args: list, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(DS_GUARD), *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _escribir_json(repo: Path, nombre: str, datos) -> Path:
    ruta = repo / nombre
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    return ruta


# --- Fixtures sintéticas -----------------------------------------------------

_CONTRATO_V1 = {
    "contract_id": "c1",
    "version": {"version": "1.0.0"},
    "dataset_role": "raw_table",
    "fields": [{"name": "id", "type_family": "integer", "required": True, "nullable": False}],
    "constraints": [],
    "business_rules": [],
    "keys": [],
    "compatibility_policy": None,
    "description": "",
    "extensions": {},
    "schema_version": 1,
}

_CONTRATO_V2 = {
    "contract_id": "c1",
    "version": {"version": "1.1.0"},
    "dataset_role": "raw_table",
    "fields": [
        {"name": "id", "type_family": "integer", "required": True, "nullable": False},
        {"name": "extra", "type_family": "string", "required": False, "nullable": True},
    ],
    "constraints": [],
    "business_rules": [],
    "keys": [],
    "compatibility_policy": None,
    "description": "",
    "extensions": {},
    "schema_version": 1,
}

_COMPAT_POLICY = {
    "policy_id": "p1",
    "on_removed_field": "block",
    "on_required_field_added": "block",
    "on_type_change": "block",
    "on_constraint_tightening": "warn",
    "on_constraint_loosening": "allow",
    "on_unknown_change": "warn",
}

_PROFILE = {
    "schema": {"id": {}},
    "columnas_detalle": {
        "id": {"dtype": "entero", "nulls": {"count": 0}, "unique": {"count": 3, "exactitud": "exacta"}}
    },
    "sampling": {"activo": False},
    "filas": 3,
}

_PROFILE_BASELINE = {"filas": 100, "schema": {}, "columnas_detalle": {}, "sampling": {"activo": False}}
_PROFILE_CURRENT = {"filas": 120, "schema": {}, "columnas_detalle": {}, "sampling": {"activo": False}}

_PROFILE_BASELINE_COL = {
    "filas": 100,
    "schema": {"id": {}},
    "columnas_detalle": {"id": {"nulls": {"count": 2}}},
    "sampling": {"activo": False},
}
_PROFILE_CURRENT_COL = {
    "filas": 120,
    "schema": {"id": {}},
    "columnas_detalle": {"id": {"nulls": {"count": 7}}},
    "sampling": {"activo": False},
}

_MQ_POLICY = {
    "policy_id": "mq1",
    "model_task_role": "classification",
    "requirements": [
        {
            "requirement_id": "r1",
            "metric_name": "auc",
            "direction": "higher_is_better",
            "required_context": {"context_id": "ctx1", "split": "test"},
            "threshold_value": 0.7,
            "threshold_severity": "FAIL",
        }
    ],
    "schema_version": 1,
}

_MQ_METRICS = [{"metric_name": "auc", "value": 0.8, "context": {"context_id": "ctx1", "split": "test"}}]


class _BaseRepoGit(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_repo_git_temporal()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)


# --- contract validate --------------------------------------------------------

class TestContractValidate(_BaseRepoGit):
    def test_texto_y_json(self):
        contrato = _escribir_json(self.repo, "contract.json", _CONTRATO_V1)
        profile = _escribir_json(self.repo, "profile.json", _PROFILE)

        r_texto = _correr_ds_guard(["contract", "validate", "--contract", str(contrato), "--profile", str(profile)], self.repo)
        self.assertIn(r_texto.returncode, (0, 1), r_texto.stderr)
        self.assertIn("Contract validate", r_texto.stdout)

        r_json = _correr_ds_guard(
            ["contract", "validate", "--contract", str(contrato), "--profile", str(profile), "--json"], self.repo
        )
        self.assertIn(r_json.returncode, (0, 1), r_json.stderr)
        payload = json.loads(r_json.stdout)
        self.assertIn("resultados", payload)
        self.assertIsInstance(payload["resultados"], list)

    def test_record_evidence_y_evidence_show(self):
        contrato = _escribir_json(self.repo, "contract.json", _CONTRATO_V1)
        profile = _escribir_json(self.repo, "profile.json", _PROFILE)
        r = _correr_ds_guard(
            [
                "contract", "validate", "--contract", str(contrato), "--profile", str(profile),
                "--record-evidence", "--json",
            ],
            self.repo,
        )
        self.assertIn(r.returncode, (0, 1), r.stderr)
        payload = json.loads(r.stdout)
        self.assertIn("evidence_id", payload)
        evidence_id = payload["evidence_id"]
        self.assertTrue((self.repo / ".harmessi" / "quality" / evidence_id / "manifest.json").exists())

        r_show = _correr_ds_guard(["quality", "evidence", "show", "--evidence-id", evidence_id, "--json"], self.repo)
        self.assertEqual(r_show.returncode, 0, r_show.stderr)
        manifest = json.loads(r_show.stdout)
        self.assertEqual(manifest["evidence_id"], evidence_id)

    def test_sin_record_evidence_no_escribe_nada(self):
        contrato = _escribir_json(self.repo, "contract.json", _CONTRATO_V1)
        profile = _escribir_json(self.repo, "profile.json", _PROFILE)
        _correr_ds_guard(["contract", "validate", "--contract", str(contrato), "--profile", str(profile)], self.repo)
        self.assertFalse((self.repo / ".harmessi" / "quality").exists())

    def test_contrato_inexistente_exit_2(self):
        profile = _escribir_json(self.repo, "profile.json", _PROFILE)
        r = _correr_ds_guard(
            ["contract", "validate", "--contract", str(self.repo / "no-existe.json"), "--profile", str(profile)],
            self.repo,
        )
        self.assertEqual(r.returncode, 2)


# --- contract diff -------------------------------------------------------------

class TestContractDiff(_BaseRepoGit):
    def test_sin_policy_status_na(self):
        old = _escribir_json(self.repo, "old.json", _CONTRATO_V1)
        new = _escribir_json(self.repo, "new.json", _CONTRATO_V2)
        r = _correr_ds_guard(["contract", "diff", "--old", str(old), "--new", str(new), "--json"], self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)
        payload = json.loads(r.stdout)
        resultados = payload["resultados"]
        self.assertTrue(resultados)
        for res in resultados:
            self.assertEqual(res["status"], "N/A")

    def test_con_policy_status_mapeado(self):
        old = _escribir_json(self.repo, "old.json", _CONTRATO_V1)
        new = _escribir_json(self.repo, "new.json", _CONTRATO_V2)
        policy = _escribir_json(self.repo, "policy.json", _COMPAT_POLICY)
        r = _correr_ds_guard(
            ["contract", "diff", "--old", str(old), "--new", str(new), "--policy", str(policy), "--json"],
            self.repo,
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        payload = json.loads(r.stdout)
        estados = {res["status"] for res in payload["resultados"]}
        self.assertTrue(estados <= {"PASS", "WARN", "FAIL"})

    def test_texto_incluye_resumen(self):
        old = _escribir_json(self.repo, "old.json", _CONTRATO_V1)
        new = _escribir_json(self.repo, "new.json", _CONTRATO_V2)
        r = _correr_ds_guard(["contract", "diff", "--old", str(old), "--new", str(new)], self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Resumen por categoría", r.stdout)


# --- contract impact -------------------------------------------------------------

class TestContractImpact(_BaseRepoGit):
    def test_staged_potentially_affected(self):
        contrato = _escribir_json(self.repo, "contract.json", _CONTRATO_V1)
        consumidor = self.repo / "consumidor.py"
        consumidor.write_text('CONTRACT_ID = "c1"\n', encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=str(self.repo), check=True)

        r = _correr_ds_guard(["contract", "impact", "--contract", str(contrato), "--staged", "--json"], self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)
        payload = json.loads(r.stdout)
        self.assertEqual(payload["contract_id"], "c1")
        self.assertIn("summary", payload)

    def test_texto_vocabulario_potentially_affected(self):
        contrato = _escribir_json(self.repo, "contract.json", _CONTRATO_V1)
        subprocess.run(["git", "add", "-A"], cwd=str(self.repo), check=True)
        r = _correr_ds_guard(["contract", "impact", "--contract", str(contrato), "--staged"], self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Potentially affected consumers", r.stdout)
        self.assertNotIn("broken", r.stdout.lower())


# --- quality evaluate ----------------------------------------------------------

class TestQualityEvaluate(_BaseRepoGit):
    def test_texto_y_json(self):
        policy = _escribir_json(self.repo, "mq_policy.json", _MQ_POLICY)
        metrics = _escribir_json(self.repo, "metrics.json", _MQ_METRICS)

        r_texto = _correr_ds_guard(["quality", "evaluate", "--policy", str(policy), "--metrics", str(metrics)], self.repo)
        self.assertIn(r_texto.returncode, (0, 1), r_texto.stderr)
        self.assertIn("Quality evaluate", r_texto.stdout)

        r_json = _correr_ds_guard(
            ["quality", "evaluate", "--policy", str(policy), "--metrics", str(metrics), "--json"], self.repo
        )
        self.assertIn(r_json.returncode, (0, 1), r_json.stderr)
        payload = json.loads(r_json.stdout)
        self.assertIn("resultados", payload)

    def test_metrics_no_es_lista_exit_2(self):
        policy = _escribir_json(self.repo, "mq_policy.json", _MQ_POLICY)
        metrics = _escribir_json(self.repo, "metrics.json", {"no": "es una lista"})
        r = _correr_ds_guard(["quality", "evaluate", "--policy", str(policy), "--metrics", str(metrics)], self.repo)
        self.assertEqual(r.returncode, 2)


# --- quality drift ---------------------------------------------------------------

class TestQualityDrift(_BaseRepoGit):
    def test_sin_threshold_status_na(self):
        baseline = _escribir_json(self.repo, "baseline_profile.json", _PROFILE_BASELINE)
        current = _escribir_json(self.repo, "current_profile.json", _PROFILE_CURRENT)
        r = _correr_ds_guard(
            [
                "quality", "drift",
                "--baseline-profile", str(baseline),
                "--current-profile", str(current),
                "--metric", "filas",
                "--field", "filas",
                "--mode", "absolute_diff",
                "--json",
            ],
            self.repo,
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        payload = json.loads(r.stdout)
        self.assertEqual(payload["result_status"], "N/A")

    def test_field_columna_con_column(self):
        """`--field nulls_count` (y el resto del allowlist salvo 'filas') exige
        `--column` -- gap cerrado tras el desvío señalado en el reporte de
        cierre de la implementación (drift_from_profiles requiere `column`
        para cualquier field != 'filas')."""
        baseline = _escribir_json(self.repo, "baseline_profile_col.json", _PROFILE_BASELINE_COL)
        current = _escribir_json(self.repo, "current_profile_col.json", _PROFILE_CURRENT_COL)
        r = _correr_ds_guard(
            [
                "quality", "drift",
                "--baseline-profile", str(baseline),
                "--current-profile", str(current),
                "--metric", "id_nulls",
                "--field", "nulls_count",
                "--column", "id",
                "--mode", "absolute_diff",
                "--threshold", "1",
                "--json",
            ],
            self.repo,
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        payload = json.loads(r.stdout)
        self.assertEqual(payload["baseline_value"], 2)
        self.assertEqual(payload["current_value"], 7)
        self.assertEqual(payload["observed_difference"], 5)
        self.assertEqual(payload["result_status"], "FAIL")

    def test_field_columna_sin_column_exit_2(self):
        baseline = _escribir_json(self.repo, "baseline_profile_col.json", _PROFILE_BASELINE_COL)
        current = _escribir_json(self.repo, "current_profile_col.json", _PROFILE_CURRENT_COL)
        r = _correr_ds_guard(
            [
                "quality", "drift",
                "--baseline-profile", str(baseline),
                "--current-profile", str(current),
                "--metric", "id_nulls",
                "--field", "nulls_count",
                "--mode", "absolute_diff",
            ],
            self.repo,
        )
        self.assertEqual(r.returncode, 2)

    def test_nunca_escribe_nada(self):
        baseline = _escribir_json(self.repo, "baseline_profile.json", _PROFILE_BASELINE)
        current = _escribir_json(self.repo, "current_profile.json", _PROFILE_CURRENT)
        _correr_ds_guard(
            [
                "quality", "drift",
                "--baseline-profile", str(baseline),
                "--current-profile", str(current),
                "--metric", "filas",
                "--field", "filas",
                "--mode", "relative_diff",
                "--threshold", "0.5",
            ],
            self.repo,
        )
        self.assertFalse((self.repo / ".harmessi").exists())


# --- status: extensión quality_evidence (R15 de spec.md) ------------------------

class TestStatusQualityEvidenceAditivo(_BaseRepoGit):
    def test_status_incluye_quality_evidence_sin_evidencia(self):
        r = _correr_ds_guard(["status", "--json"], self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)
        payload = json.loads(r.stdout)
        self.assertIn("quality_evidence", payload)
        self.assertFalse(payload["quality_evidence"]["disponible"])


if __name__ == "__main__":
    unittest.main()

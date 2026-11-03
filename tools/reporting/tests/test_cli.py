"""Tests de `tools/reporting/cli.py` y `__main__.py` (v0.6 Change 1, R18/R23).

Deterministas: sin red, sin aleatoriedad. Repos temporales con su propio
`.claude/guardrails.json` (holdouts sintéticos). La CLI se prueba en proceso
por `main(argv)` y una parte por subproceso `python -m tools.reporting` con
`cwd` en el root del repo real (para ejercitar el `__main__`).
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools.reporting import cli

REPO_REAL = Path(__file__).resolve().parents[3]
CLI_SRC = REPO_REAL / "tools" / "reporting" / "cli.py"


def _snapshot(raiz: Path) -> dict:
    return {
        p.relative_to(raiz).as_posix(): (p.stat().st_size, p.stat().st_mtime_ns)
        for p in sorted(raiz.rglob("*"))
    }


class _CliBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo = Path(self._tmp.name).resolve()
        guardrails = self.repo / ".claude" / "guardrails.json"
        guardrails.parent.mkdir(parents=True, exist_ok=True)
        guardrails.write_text(json.dumps({"holdouts": ["data/holdout/**"]}), encoding="utf-8")

    def correr(self, *argv):
        """`(exit_code, stdout, stderr)` de `cli.main(argv)` en proceso."""
        salida, error = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(salida), contextlib.redirect_stderr(error):
            codigo = cli.main(list(argv))
        return codigo, salida.getvalue(), error.getvalue()

    def destino(self, *extra, scope="exploratory", out_dir="reports/exploratory/r1", report_id="r1", kind="eda"):
        return self.correr(
            "check-destination", "--report-id", report_id, "--scope", scope,
            "--report-kind", kind, "--out-dir", out_dir, "--repo-root", str(self.repo), *extra,
        )

    def inputs(self, flow_scope, *entradas, extra=()):
        argv = ["check-inputs", "--flow-scope", flow_scope, "--repo-root", str(self.repo), *extra]
        for entrada in entradas:
            argv += ["--input", entrada]
        return self.correr(*argv)


class TestCheckDestination(_CliBase):
    def test_destino_coherente_exit_0(self):
        codigo, salida, _ = self.destino()
        self.assertEqual(codigo, 0)
        lineas = salida.strip().splitlines()
        self.assertEqual(
            [l.split()[1] for l in lineas],
            ["REPORT-POLICY", "REPORT-DEST-SAFE", "REPORT-DEST-SCOPE", "REPORT-SENSITIVE-DEST"],
        )
        self.assertTrue(all(l.startswith("[") for l in lineas))
        self.assertTrue(lineas[0].startswith("[PASS] REPORT-POLICY"))

    def test_destino_cross_scope_exit_1(self):
        codigo, salida, _ = self.destino(scope="model_valid", out_dir="reports/exploratory/r1", kind="model")
        self.assertEqual(codigo, 1)
        self.assertIn("[FAIL] REPORT-DEST-CROSS-SCOPE", salida)

    def test_scope_invalido_exit_2(self):
        codigo, salida, error = self.destino(scope="invalido")
        self.assertEqual(codigo, 2)
        self.assertEqual(salida, "")
        self.assertTrue(error)

    def test_report_id_invalido_exit_2(self):
        codigo, salida, error = self.destino(report_id="A/b")
        self.assertEqual(codigo, 2)
        self.assertEqual(salida, "")
        self.assertIn("report_id", error)

    def test_report_kind_invalido_exit_2(self):
        codigo, _, _ = self.destino(kind="otro")
        self.assertEqual(codigo, 2)

    def test_faltan_argumentos_exit_2(self):
        codigo, _, _ = self.correr("check-destination", "--repo-root", str(self.repo))
        self.assertEqual(codigo, 2)

    def test_sin_subcomando_exit_2(self):
        codigo, _, _ = self.correr()
        self.assertEqual(codigo, 2)

    def test_repo_root_inexistente_exit_3(self):
        inexistente = self.repo / "no_existe"
        codigo, salida, error = self.correr(
            "check-destination", "--report-id", "r1", "--scope", "exploratory",
            "--report-kind", "eda", "--out-dir", "reports/exploratory/r1", "--repo-root", str(inexistente),
        )
        self.assertEqual(codigo, 3)
        self.assertEqual(salida, "")
        self.assertIn("--repo-root", error)

    def test_repo_root_archivo_exit_3(self):
        archivo = self.repo / "archivo.txt"
        archivo.write_text("x", encoding="utf-8")
        codigo, _, error = self.correr(
            "check-inputs", "--flow-scope", "model_valid", "--input", "a.csv", "--repo-root", str(archivo)
        )
        self.assertEqual(codigo, 3)
        self.assertTrue(error)

    def test_policy_corrupta_exit_1(self):
        (self.repo / ".harmessi").mkdir()
        (self.repo / ".harmessi" / "reporting-policy.json").write_text("{corrupto", encoding="utf-8")
        codigo, salida, _ = self.destino()
        self.assertEqual(codigo, 1)
        self.assertEqual(len(salida.strip().splitlines()), 1)
        self.assertIn("[FAIL] REPORT-POLICY", salida)

    def test_out_dir_relativo_se_resuelve_contra_repo_root_no_cwd(self):
        cwd_original = Path.cwd()
        otro = tempfile.TemporaryDirectory()
        self.addCleanup(otro.cleanup)
        os.chdir(otro.name)
        try:
            codigo, _, _ = self.destino()
            self.assertEqual(codigo, 0)
            codigo, _, _ = self.destino(out_dir="../fuera/r1")
            self.assertEqual(codigo, 1)
        finally:
            os.chdir(cwd_original)

    def test_repo_root_default_es_cwd(self):
        cwd_original = Path.cwd()
        os.chdir(self.repo)
        try:
            codigo, _, _ = self.correr(
                "check-destination", "--report-id", "r1", "--scope", "exploratory",
                "--report-kind", "eda", "--out-dir", "reports/exploratory/r1",
            )
        finally:
            os.chdir(cwd_original)
        self.assertEqual(codigo, 0)


class TestCheckInputs(_CliBase):
    def test_exploratorio_en_model_valid_exit_1(self):
        codigo, salida, _ = self.inputs("model_valid", "reports/exploratory/r1/t.csv")
        self.assertEqual(codigo, 1)
        self.assertIn("[FAIL] REPORT-ISOLATION-INPUT [reports/exploratory/r1/t.csv]", salida)

    def test_flujo_exploratorio_exit_0(self):
        codigo, salida, _ = self.inputs("exploratory", "reports/exploratory/r1/t.csv")
        self.assertEqual(codigo, 0)
        self.assertIn("[N/A] REPORT-ISOLATION-INPUT", salida)

    def test_input_repetido_un_resultado_por_input(self):
        codigo, salida, _ = self.inputs("operational", "data/interim/a.csv", "data/interim/b.csv")
        self.assertEqual(codigo, 0)
        lineas = [l for l in salida.splitlines() if "REPORT-ISOLATION-INPUT" in l]
        self.assertEqual(len(lineas), 2)
        self.assertIn("[data/interim/a.csv]", lineas[0])
        self.assertIn("[data/interim/b.csv]", lineas[1])

    def test_sin_input_exit_2(self):
        codigo, _, _ = self.inputs("model_valid")
        self.assertEqual(codigo, 2)

    def test_flow_scope_invalido_exit_2(self):
        codigo, _, _ = self.inputs("otro", "a.csv")
        self.assertEqual(codigo, 2)

    def test_repo_root_inexistente_exit_3(self):
        codigo, _, _ = self.correr(
            "check-inputs", "--flow-scope", "model_valid", "--input", "a.csv",
            "--repo-root", str(self.repo / "no_existe"),
        )
        self.assertEqual(codigo, 3)


class TestSalidaJson(_CliBase):
    def _json(self, salida):
        datos = json.loads(salida)
        self.assertEqual(list(datos), sorted(datos))
        self.assertEqual(set(datos), {"allowed", "counts", "results"})
        return datos

    def test_json_destino_ok(self):
        codigo, salida, _ = self.destino("--json")
        datos = self._json(salida)
        self.assertEqual(codigo, 0)
        self.assertIs(datos["allowed"], True)
        self.assertEqual(datos["counts"]["FAIL"], 0)
        self.assertEqual(sum(datos["counts"].values()), len(datos["results"]))
        self.assertEqual(datos["results"][0]["code"], "REPORT-POLICY")
        for resultado in datos["results"]:
            self.assertEqual(list(resultado), sorted(resultado))

    def test_json_destino_fail(self):
        codigo, salida, _ = self.destino("--json", scope="model_valid", out_dir="reports/exploratory/r1", kind="model")
        datos = self._json(salida)
        self.assertEqual(codigo, 1)
        self.assertIs(datos["allowed"], False)
        self.assertGreaterEqual(datos["counts"]["FAIL"], 1)
        self.assertIn("REPORT-DEST-CROSS-SCOPE", [r["code"] for r in datos["results"]])

    def test_json_inputs_allowed_coincide_con_exit_code(self):
        for flow_scope, entrada in (("model_valid", "reports/exploratory/r1/t.csv"), ("exploratory", "x.csv")):
            codigo, salida, _ = self.inputs(flow_scope, entrada, extra=("--json",))
            datos = self._json(salida)
            self.assertEqual(datos["allowed"], codigo == 0)
            self.assertEqual(len(datos["results"]), 1)


class TestSensibles(_CliBase):
    def test_con_artefacto_sensible_sin_root_sensible_falla(self):
        codigo, salida, _ = self.destino("--sensitive-artifact", "tabla_s")
        self.assertEqual(codigo, 1)
        self.assertIn("[FAIL] REPORT-SENSITIVE-DEST", salida)

    def test_sin_la_opcion_es_na(self):
        codigo, salida, _ = self.destino()
        self.assertEqual(codigo, 0)
        self.assertIn("[N/A] REPORT-SENSITIVE-DEST", salida)

    def test_con_root_sensible_declarado_pasa(self):
        (self.repo / ".harmessi").mkdir()
        (self.repo / ".harmessi" / "reporting-policy.json").write_text(
            json.dumps({"schema_version": 1, "sensitive_destination_roots": ["reports/exploratory/sens"]}),
            encoding="utf-8",
        )
        codigo, salida, _ = self.destino("--sensitive-artifact", "a", "--sensitive-artifact", "b", out_dir="reports/exploratory/sens/r1")
        self.assertEqual(codigo, 0, salida)
        self.assertIn("[PASS] REPORT-SENSITIVE-DEST", salida)

    def test_help_aclara_que_no_reemplaza_a_publish(self):
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida):
            codigo = cli.main(["check-destination", "--help"])
        self.assertEqual(codigo, 0)
        self.assertIn("publish", " ".join(salida.getvalue().split()))


class TestInyeccionDeLineas(_CliBase):
    def test_saltos_de_linea_en_subject_se_escapan(self):
        codigo, salida, _ = self.destino(out_dir="reports/exploratory/r1\n[PASS] falso\r\n[PASS] falso2\t\x00")
        self.assertNotIn("\r", salida)
        for linea in salida.splitlines():
            self.assertFalse(linea.startswith("[PASS] falso"), linea)
        self.assertIn("\\n[PASS] falso", salida)
        self.assertEqual(len(salida.splitlines()), len(salida.strip().split("\n")))


class TestSoloLectura(_CliBase):
    def test_no_modifica_el_arbol(self):
        (self.repo / "reports" / "exploratory" / "r0").mkdir(parents=True)
        (self.repo / "reports" / "exploratory" / "r0" / "manifest.json").write_text(
            json.dumps({"report_id": "r0", "decision_scope": "exploratory"}), encoding="utf-8"
        )
        antes = _snapshot(self.repo)
        self.destino()
        self.destino("--json", scope="model_valid", out_dir="reports/exploratory/r1", kind="model")
        self.inputs("model_valid", "reports/exploratory/r0/t.csv")
        self.inputs("model_valid", "reports/exploratory/r0/t.csv", extra=("--json",))
        self.destino(report_id="A/b")
        self.assertEqual(antes, _snapshot(self.repo))

    def test_cli_no_usa_stdin(self):
        self.assertNotIn("sys.stdin", CLI_SRC.read_text(encoding="utf-8"))


class TestSubproceso(unittest.TestCase):
    """Ejercita `tools/reporting/__main__.py` con `cwd` en el root del repo real."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo = Path(self._tmp.name).resolve()
        (self.repo / ".claude").mkdir()
        (self.repo / ".claude" / "guardrails.json").write_text(
            json.dumps({"holdouts": ["data/holdout/**"]}), encoding="utf-8"
        )

    def _correr(self, *argv):
        # Sin PYTHONIOENCODING favorable: el `__main__` debe forzar UTF-8 por sí mismo.
        entorno = {**os.environ, "PYTHONIOENCODING": "cp1252", "PYTHONUTF8": "0"}
        return subprocess.run(
            [sys.executable, "-m", "tools.reporting", *argv],
            cwd=str(REPO_REAL), capture_output=True, text=True, encoding="utf-8", env=entorno, timeout=120,
        )

    def _destino(self, out_dir, *extra):
        return self._correr(
            "check-destination", "--report-id", "r1", "--scope", "exploratory",
            "--report-kind", "eda", "--out-dir", out_dir, "--repo-root", str(self.repo), *extra,
        )

    def test_subproceso_salida_utf8_con_tildes_reales(self):
        proc = self._destino("reports/exploratory/r1")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("canónicas", proc.stdout)
        self.assertNotIn("�", proc.stdout)
        self.assertNotIn("Ã", proc.stdout)

    def test_subproceso_out_dir_fuera_de_cp1252_no_lanza(self):
        proc = self._destino("reportes/日本")
        self.assertIn(proc.returncode, (0, 1), proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)
        self.assertNotIn("UnicodeEncodeError", proc.stderr)
        self.assertIn("日本", proc.stdout)
        proc_json = self._destino("reportes/日本", "--json")
        self.assertIn(proc_json.returncode, (0, 1), proc_json.stderr)
        self.assertNotIn("Traceback", proc_json.stderr)
        json.loads(proc_json.stdout)

    def test_subproceso_check_destination_ok_y_json(self):
        antes = _snapshot(self.repo)
        base = (
            "check-destination", "--report-id", "r1", "--scope", "exploratory",
            "--report-kind", "eda", "--out-dir", "reports/exploratory/r1", "--repo-root", str(self.repo),
        )
        proc = self._correr(*base)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("[PASS] REPORT-POLICY", proc.stdout)
        proc_json = self._correr(*base, "--json")
        self.assertEqual(proc_json.returncode, 0, proc_json.stderr)
        datos = json.loads(proc_json.stdout)
        self.assertIs(datos["allowed"], True)
        self.assertEqual(antes, _snapshot(self.repo))

    def test_subproceso_exit_codes_1_2_3(self):
        proc = self._correr(
            "check-inputs", "--flow-scope", "model_valid", "--input", "reports/exploratory/r1/t.csv",
            "--repo-root", str(self.repo),
        )
        self.assertEqual(proc.returncode, 1, proc.stderr)
        self.assertIn("[FAIL] REPORT-ISOLATION-INPUT", proc.stdout)
        proc = self._correr("check-inputs", "--flow-scope", "model_valid", "--repo-root", str(self.repo))
        self.assertEqual(proc.returncode, 2)
        self.assertTrue(proc.stderr)
        proc = self._correr(
            "check-inputs", "--flow-scope", "model_valid", "--input", "a.csv",
            "--repo-root", str(self.repo / "no_existe"),
        )
        self.assertEqual(proc.returncode, 3)
        self.assertTrue(proc.stderr)


if __name__ == "__main__":
    unittest.main()

"""Tests del subcomando `validate` y del `check-inputs` aditivo de
`tools/reporting/cli.py` (v0.6 Change 3, R18/R19).

Deterministas: sin red, sin aleatoriedad, datos 100% sinteticos. Repos temporales
con reporte base `build_example_report()` persistido con `evidence`. La CLI se
prueba en proceso por `main(argv)` y una parte por subproceso
`python -m tools.reporting` con `cwd` en el root del repo real.
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.dsguard import checks
from tools.reporting import cli, evidence
from tools.reporting.evidence import (
    build_manifest,
    describe_generated_source,
    prepare_artifacts,
    write_report_dir,
)
from tools.reporting.examples.eda_generic import build_example_report

REPO_REAL = Path(__file__).resolve().parents[3]
RUN_ID = "run-20260101T000000Z-abc123"
RELOJ = lambda: "2026-01-01T00:00:00Z"  # noqa: E731


def _snapshot(raiz: Path) -> dict:
    return {
        p.relative_to(raiz).as_posix(): (p.stat().st_size, p.stat().st_mtime_ns)
        for p in sorted(raiz.rglob("*"))
    }


class _Base(unittest.TestCase):
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

    def persistir(self):
        """Persiste `build_example_report()` en `reports/<scope>/<report_id>`."""
        report = build_example_report()
        artefactos = prepare_artifacts(report)
        manifest = build_manifest(
            report,
            repo_root=self.repo,
            run_id=RUN_ID,
            artifact_bytes=artefactos,
            sources=[describe_generated_source("datos sinteticos", {"semilla": 1})],
            holdout_access="none",
            git_commit=None,
            git_dirty=None,
            harmessi_version=None,
            clock=RELOJ,
        )
        out = self.repo.joinpath("reports", report.decision_scope, report.report_id)
        write_report_dir(out, artefactos, manifest)
        return out, artefactos

    def validar(self, out, *extra):
        return self.correr("validate", "--dir", str(out), "--repo-root", str(self.repo), *extra)


class TestValidate(_Base):
    def test_reporte_valido_exit_0(self):
        out, _ = self.persistir()
        codigo, salida, error = self.validar(out)
        self.assertEqual(codigo, 0, salida + error)
        self.assertNotIn("[FAIL]", salida)
        self.assertTrue(salida.strip())

    def test_dir_relativo_se_resuelve_contra_repo_root(self):
        out, _ = self.persistir()
        relativo = out.relative_to(self.repo).as_posix()
        codigo, salida, _ = self.correr("validate", "--dir", relativo, "--repo-root", str(self.repo))
        self.assertEqual(codigo, 0, salida)

    def test_artefacto_alterado_exit_1(self):
        out, artefactos = self.persistir()
        rel = next(r for r in sorted(artefactos) if r.startswith("artifacts/tables/"))
        ruta = out.joinpath(*rel.split("/"))
        ruta.write_bytes(ruta.read_bytes() + b" ")
        codigo, salida, _ = self.validar(out)
        self.assertEqual(codigo, 1)
        self.assertIn("[FAIL] REPORT-ARTIFACT-HASH", salida)

    def test_manifest_ausente_exit_1(self):
        out, _ = self.persistir()
        (out / "manifest.json").unlink()
        codigo, salida, _ = self.validar(out)
        self.assertEqual(codigo, 1)
        self.assertIn("[FAIL] REPORT-MANIFEST-MISSING", salida)

    def test_directorio_inexistente_exit_1_manifest_missing(self):
        codigo, salida, _ = self.validar(self.repo / "reports" / "exploratory" / "no_existe")
        self.assertEqual(codigo, 1)
        self.assertIn("[FAIL] REPORT-MANIFEST-MISSING", salida)

    def test_repo_root_invalido_exit_3(self):
        codigo, salida, error = self.correr(
            "validate", "--dir", "reports/x", "--repo-root", str(self.repo / "no_existe")
        )
        self.assertEqual(codigo, 3)
        self.assertEqual(salida, "")
        self.assertIn("--repo-root", error)

    def test_repo_root_archivo_exit_3(self):
        archivo = self.repo / "archivo.txt"
        archivo.write_text("x", encoding="utf-8")
        codigo, _, error = self.correr("validate", "--dir", "reports/x", "--repo-root", str(archivo))
        self.assertEqual(codigo, 3)
        self.assertTrue(error)

    def test_sin_dir_exit_2(self):
        codigo, salida, error = self.correr("validate", "--repo-root", str(self.repo))
        self.assertEqual(codigo, 2)
        self.assertEqual(salida, "")
        self.assertTrue(error)

    def test_repo_root_default_es_cwd(self):
        out, _ = self.persistir()
        cwd_original = Path.cwd()
        os.chdir(self.repo)
        try:
            codigo, salida, _ = self.correr("validate", "--dir", out.relative_to(self.repo).as_posix())
        finally:
            os.chdir(cwd_original)
        self.assertEqual(codigo, 0, salida)


class TestValidateJson(_Base):
    def _json(self, salida):
        datos = json.loads(salida)
        self.assertEqual(list(datos), sorted(datos))
        self.assertEqual(set(datos), {"allowed", "counts", "results"})
        return datos

    def test_json_reporte_valido(self):
        out, _ = self.persistir()
        codigo, salida, _ = self.validar(out, "--json")
        datos = self._json(salida)
        self.assertEqual(codigo, 0)
        self.assertIs(datos["allowed"], True)
        self.assertEqual(datos["counts"]["FAIL"], 0)
        self.assertEqual(sum(datos["counts"].values()), len(datos["results"]))
        for resultado in datos["results"]:
            self.assertEqual(list(resultado), sorted(resultado))

    def test_json_manifest_ausente(self):
        out, _ = self.persistir()
        (out / "manifest.json").unlink()
        codigo, salida, _ = self.validar(out, "--json")
        datos = self._json(salida)
        self.assertEqual(codigo, 1)
        self.assertIs(datos["allowed"], False)
        self.assertGreaterEqual(datos["counts"]["FAIL"], 1)
        self.assertIn("REPORT-MANIFEST-MISSING", [r["code"] for r in datos["results"]])

    def test_json_allowed_coincide_con_exit_code(self):
        out, _ = self.persistir()
        for _ in range(2):
            codigo, salida, _ = self.validar(out, "--json")
            self.assertEqual(self._json(salida)["allowed"], codigo == 0)
            (out / "manifest.json").unlink(missing_ok=True)


class TestValidateEscapeYSoloLectura(_Base):
    def test_caracteres_de_control_se_escapan(self):
        falso = checks.CheckResult(
            status=checks.STATUS_FAIL,
            code="REPORT-X",
            message="linea\n[PASS] REPORT-FALSO ok\r\n\t\x00fin",
            subject="sub\n[PASS] falso2",
            kind=checks.KIND_CHECK,
        )
        with mock.patch.object(cli.validation, "validate_report_dir", return_value=[falso]):
            codigo, salida, _ = self.correr("validate", "--dir", "x", "--repo-root", str(self.repo))
        self.assertEqual(codigo, 1)
        self.assertNotIn("\r", salida)
        self.assertNotIn("\x00", salida)
        lineas = salida.splitlines()
        self.assertEqual(len(lineas), 1)
        self.assertTrue(lineas[0].startswith("[FAIL] REPORT-X"))
        self.assertIn("\\n[PASS] REPORT-FALSO", lineas[0])

    def test_no_modifica_el_arbol(self):
        out, artefactos = self.persistir()
        rel = next(r for r in sorted(artefactos) if r.startswith("artifacts/tables/"))
        ruta = out.joinpath(*rel.split("/"))
        ruta.write_bytes(ruta.read_bytes() + b" ")  # reporte roto: caso con FAIL
        antes = _snapshot(self.repo)
        self.validar(out)
        self.validar(out, "--json")
        self.validar(self.repo / "reports" / "exploratory" / "no_existe")
        self.assertEqual(antes, _snapshot(self.repo))


class TestCheckInputsHash(_Base):
    def _exploratory_con_artefacto(self, contenido: bytes) -> str:
        """Manifest exploratory sintetico que lista un artefacto con el sha256 de `contenido`."""
        base = self.repo / "reports" / "exploratory" / "r0"
        (base / "artifacts" / "tables").mkdir(parents=True)
        (base / "artifacts" / "tables" / "x.json").write_bytes(contenido)
        sha = hashlib.sha256(contenido).hexdigest()
        manifest = {
            "schema_version": 1,
            "report_id": "r0",
            "decision_scope": "exploratory",
            "artifacts": [{"id": "x", "kind": "table", "file": "artifacts/tables/x.json", "sha256": sha}],
        }
        (base / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        return sha

    def _entradas(self, flow_scope, *entradas, extra=()):
        argv = ["check-inputs", "--flow-scope", flow_scope, "--repo-root", str(self.repo), *extra]
        for entrada in entradas:
            argv += ["--input", entrada]
        return self.correr(*argv)

    def test_copia_byte_identica_falla_en_model_valid(self):
        contenido = b'{"columnas": ["a"], "filas": [[1]]}\n'
        self._exploratory_con_artefacto(contenido)
        (self.repo / "data" / "interim").mkdir(parents=True)
        (self.repo / "data" / "interim" / "copia.json").write_bytes(contenido)
        codigo, salida, _ = self._entradas("model_valid", "data/interim/copia.json")
        self.assertEqual(codigo, 1)
        self.assertIn("[FAIL] REPORT-ISOLATION-HASH [data/interim/copia.json]", salida)
        self.assertIn("r0", salida)
        # aditivo: el resultado previo de path sigue presente y antes del de hash
        self.assertLess(salida.index("REPORT-ISOLATION-INPUT"), salida.index("REPORT-ISOLATION-HASH"))

    def test_copia_byte_identica_json(self):
        contenido = b"contenido exploratory\n"
        self._exploratory_con_artefacto(contenido)
        (self.repo / "data").mkdir()
        (self.repo / "data" / "copia.bin").write_bytes(contenido)
        codigo, salida, _ = self._entradas("operational", "data/copia.bin", extra=("--json",))
        datos = json.loads(salida)
        self.assertEqual(codigo, 1)
        self.assertIs(datos["allowed"], False)
        self.assertIn("REPORT-ISOLATION-HASH", [r["code"] for r in datos["results"]])

    def test_input_distinto_pasa_y_flujo_exploratorio_no_falla(self):
        self._exploratory_con_artefacto(b"contenido exploratory\n")
        (self.repo / "data").mkdir()
        (self.repo / "data" / "otro.csv").write_text("a,b\n1,2\n", encoding="utf-8")
        codigo, salida, _ = self._entradas("model_valid", "data/otro.csv")
        self.assertEqual(codigo, 0, salida)
        self.assertIn("[PASS] REPORT-ISOLATION-HASH", salida)
        codigo, salida, _ = self._entradas("exploratory", "data/otro.csv")
        self.assertEqual(codigo, 0, salida)

    def test_sin_manifests_exploratory_la_salida_no_cambia(self):
        codigo, salida, _ = self._entradas("operational", "data/interim/a.csv", "data/interim/b.csv")
        self.assertEqual(codigo, 0)
        self.assertNotIn("REPORT-ISOLATION-HASH", salida)
        codigo, salida, _ = self._entradas("model_valid", "x.csv", extra=("--json",))
        self.assertEqual(len(json.loads(salida)["results"]), 1)

    def test_check_inputs_no_modifica_el_arbol(self):
        contenido = b"contenido exploratory\n"
        self._exploratory_con_artefacto(contenido)
        (self.repo / "data").mkdir()
        (self.repo / "data" / "copia.bin").write_bytes(contenido)
        antes = _snapshot(self.repo)
        self._entradas("model_valid", "data/copia.bin")
        self._entradas("model_valid", "data/copia.bin", extra=("--json",))
        self.assertEqual(antes, _snapshot(self.repo))


class TestCheckInputsAccesoYIndice(TestCheckInputsHash):
    """Acceso denegado por archivo (sin abrir), indice truncado/ilegible y estructura de `cli.py`."""

    def _espiar_lecturas(self):
        """Devuelve `(fingerprints, lecturas)`: rutas sobre las que se llamo a
        `calcular_fingerprint` y `Path.read_bytes` durante el bloque `with`."""
        fingerprints, lecturas = [], []
        original_fp = evidence._fingerprint.calcular_fingerprint
        original_rb = Path.read_bytes

        def espia_fp(ruta, *a, **k):
            fingerprints.append(str(ruta))
            return original_fp(ruta, *a, **k)

        def espia_rb(self_path, *a, **k):
            lecturas.append(str(self_path))
            return original_rb(self_path, *a, **k)

        parches = contextlib.ExitStack()
        parches.enter_context(mock.patch.object(evidence._fingerprint, "calcular_fingerprint", side_effect=espia_fp))
        parches.enter_context(mock.patch.object(Path, "read_bytes", espia_rb))
        self.addCleanup(parches.close)
        return fingerprints, lecturas

    def test_directorio_con_holdout_falla_sin_abrirlo(self):
        self._exploratory_con_artefacto(b"contenido exploratory\n")
        (self.repo / "data" / "holdout").mkdir(parents=True)
        (self.repo / "data" / "holdout" / "h.csv").write_text("secreto\n", encoding="utf-8")
        (self.repo / "data" / "ok.csv").write_text("a,b\n1,2\n", encoding="utf-8")
        fingerprints, lecturas = self._espiar_lecturas()
        codigo, salida, _ = self._entradas("model_valid", "data/holdout", "data/ok.csv")
        self.assertEqual(codigo, 1, salida)
        self.assertIn("[FAIL] REPORT-ISOLATION-HASH", salida)
        self.assertIn("acceso denegado (no se abrió)", salida)
        self.assertTrue(any(f.endswith("ok.csv") for f in fingerprints), "el espia debe ver el input permitido")
        self.assertFalse([f for f in fingerprints if "holdout" in f], fingerprints)
        self.assertFalse([l for l in lecturas if "holdout" in l], lecturas)

    def test_input_env_falla_sin_abrirlo(self):
        self._exploratory_con_artefacto(b"contenido exploratory\n")
        (self.repo / ".env").write_text("TOKEN=abc\n", encoding="utf-8")
        fingerprints, lecturas = self._espiar_lecturas()
        codigo, salida, _ = self._entradas("operational", ".env")
        self.assertEqual(codigo, 1, salida)
        self.assertIn("[FAIL] REPORT-ISOLATION-HASH [.env]", salida)
        self.assertIn("acceso denegado (no se abrió)", salida)
        self.assertFalse([f for f in fingerprints if f.endswith(".env")], fingerprints)
        self.assertFalse([l for l in lecturas if l.endswith(".env")], lecturas)
        self.assertNotIn("abc", salida)

    def test_indice_truncado_da_fail(self):
        for nombre in ("a", "b", "c"):
            (self.repo / "reports" / "exploratory" / nombre).mkdir(parents=True)
        (self.repo / "data").mkdir()
        (self.repo / "data" / "ok.csv").write_text("a,b\n1,2\n", encoding="utf-8")
        with mock.patch.object(evidence, "MAX_DIRS_SCAN", 1):
            codigo, salida, _ = self._entradas("model_valid", "data/ok.csv")
        self.assertEqual(codigo, 1, salida)
        self.assertIn("[FAIL] REPORT-ISOLATION-HASH", salida)
        self.assertIn("incompleto", salida)

    def test_manifest_exploratory_ilegible_da_warn(self):
        ilegible = self.repo / "reports" / "exploratory" / "malo"
        ilegible.mkdir(parents=True)
        (ilegible / "manifest.json").write_text("{corrupto", encoding="utf-8")
        (self.repo / "data").mkdir()
        (self.repo / "data" / "ok.csv").write_text("a,b\n1,2\n", encoding="utf-8")
        codigo, salida, _ = self._entradas("model_valid", "data/ok.csv")
        self.assertIn("[WARN] REPORT-ISOLATION-HASH", salida)
        self.assertEqual(codigo, 0, salida)  # WARN no bloquea
        codigo, salida_json, _ = self._entradas("model_valid", "data/ok.csv", extra=("--json",))
        self.assertGreaterEqual(json.loads(salida_json)["counts"]["WARN"], 1)

    def test_cli_no_usa_la_api_privada_de_indexado(self):
        fuente = (REPO_REAL / "tools" / "reporting" / "cli.py").read_text(encoding="utf-8")
        self.assertNotIn("_indexar_exploratory", fuente)
        self.assertIn("exploratory_index_status", fuente)


class TestValidateSinRutaAbsoluta(_Base):
    """Los mensajes de `validate` son relativos al repo: no filtran la ruta absoluta del repo."""

    def _sin_ruta_absoluta(self, texto):
        for variante in (str(self.repo), self.repo.as_posix(), str(self.repo).replace("\\", "\\\\")):
            self.assertNotIn(variante, texto)

    def test_reporte_valido_texto_y_json(self):
        out, _ = self.persistir()
        _, salida, error = self.validar(out)
        self._sin_ruta_absoluta(salida + error)
        _, salida_json, _ = self.validar(out, "--json")
        self._sin_ruta_absoluta(salida_json)

    def test_reporte_roto_texto_y_json(self):
        out, artefactos = self.persistir()
        rel = next(r for r in sorted(artefactos) if r.startswith("artifacts/tables/"))
        ruta = out.joinpath(*rel.split("/"))
        ruta.write_bytes(ruta.read_bytes() + b" ")
        _, salida, _ = self.validar(out)
        self._sin_ruta_absoluta(salida)
        self.assertIn("REPORT-ARTIFACT-HASH", salida)
        (out / "manifest.json").unlink()
        _, salida, _ = self.validar(out)
        self._sin_ruta_absoluta(salida)
        _, salida_json, _ = self.validar(out, "--json")
        self._sin_ruta_absoluta(salida_json)

    def test_directorio_inexistente(self):
        _, salida, _ = self.validar(self.repo / "reports" / "exploratory" / "no_existe")
        self._sin_ruta_absoluta(salida)


class TestSubproceso(_Base):
    """Ejercita `python -m tools.reporting validate` con `cwd` en el root del repo real."""

    def _correr(self, *argv):
        # Sin PYTHONIOENCODING favorable: el `__main__` debe forzar UTF-8 por si mismo.
        entorno = {**os.environ, "PYTHONIOENCODING": "cp1252", "PYTHONUTF8": "0"}
        return subprocess.run(
            [sys.executable, "-m", "tools.reporting", *argv],
            cwd=str(REPO_REAL), capture_output=True, text=True, encoding="utf-8", env=entorno, timeout=120,
        )

    def test_subproceso_validate_ok_json_y_solo_lectura(self):
        out, _ = self.persistir()
        antes = _snapshot(self.repo)
        base = ("validate", "--dir", str(out), "--repo-root", str(self.repo))
        proc = self._correr(*base)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertNotIn("[FAIL]", proc.stdout)
        proc_json = self._correr(*base, "--json")
        self.assertEqual(proc_json.returncode, 0, proc_json.stderr)
        self.assertIs(json.loads(proc_json.stdout)["allowed"], True)
        self.assertEqual(antes, _snapshot(self.repo))

    def test_subproceso_exit_codes_1_2_3(self):
        proc = self._correr("validate", "--dir", str(self.repo / "reports" / "no_existe"), "--repo-root", str(self.repo))
        self.assertEqual(proc.returncode, 1, proc.stderr)
        self.assertIn("[FAIL] REPORT-MANIFEST-MISSING", proc.stdout)
        proc = self._correr("validate", "--repo-root", str(self.repo))
        self.assertEqual(proc.returncode, 2)
        self.assertTrue(proc.stderr)
        proc = self._correr("validate", "--dir", "x", "--repo-root", str(self.repo / "no_existe"))
        self.assertEqual(proc.returncode, 3)
        self.assertTrue(proc.stderr)


if __name__ == "__main__":
    unittest.main()

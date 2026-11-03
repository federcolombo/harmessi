"""Tests del subcomando `render` de `tools/reporting/cli.py` (v0.6 Change 4, R19).

Deterministas: sin red, sin plotly real, datos 100% sinteticos. Repos temporales con
reporte base `build_example_report()` persistido con `evidence`. La CLI se prueba en
proceso por `main(argv)` y una parte por subproceso `python -m tools.reporting` con
`cwd` en el root del repo real. El bundle de plotly.js es FALSO (archivo del proyecto).
"""
from __future__ import annotations

import contextlib
import html as html_stdlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.reporting import cli, evidence
from tools.reporting.evidence import (
    build_manifest,
    describe_generated_source,
    prepare_artifacts,
    write_report_dir,
)
from tools.reporting.examples.eda_generic import build_example_report
from tools.reporting.render_html import render_report_html
from tools.reporting.style import default_style

REPO_REAL = Path(__file__).resolve().parents[3]
RUN_ID = "run-20260101T000000Z-abc123"
RELOJ = lambda: "2026-01-01T00:00:00Z"  # noqa: E731
MARCA_BUNDLE = "FAKE_PLOTLY_BUNDLE_MARKER_20260101"
BUNDLE_FALSO = f"/* {MARCA_BUNDLE} */ window.Plotly = {{react: function () {{}}, newPlot: function () {{}}}};"


def _archivos(raiz: Path) -> dict:
    """Snapshot SOLO de archivos (los directorios cambian de mtime al agregar hijos)."""
    return {
        p.relative_to(raiz).as_posix(): (p.stat().st_size, p.stat().st_mtime_ns)
        for p in sorted(raiz.rglob("*"))
        if p.is_file()
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

    def sin_plotly(self):
        """Fuerza la degradacion: sin bundle (aunque el entorno tenga plotly instalado)."""
        parche = mock.patch.object(cli.plotly_backend, "find_plotly_bundle", return_value=None)
        parche.start()
        self.addCleanup(parche.stop)

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

    def render(self, out, *extra):
        return self.correr("render", "--dir", str(out), "--repo-root", str(self.repo), *extra)

    def esperado(self, out, *, estilo=None, bundle=None, include_sensitive=False) -> bytes:
        """Render de referencia desde el directorio persistido (misma carga que la CLI)."""
        files, manifest = evidence.read_report_dir(out, repo_root=self.repo)
        reporte = evidence.report_from_bytes(files, manifest)
        return render_report_html(
            reporte, manifest, estilo or default_style(),
            plotly_bundle=bundle, include_sensitive=include_sensitive,
        ).encode("utf-8")


class TestRender(_Base):
    def test_reporte_valido_escribe_html_exit_0(self):
        self.sin_plotly()
        out, _ = self.persistir()
        codigo, salida, error = self.render(out)
        self.assertEqual(codigo, 0, salida + error)
        self.assertNotIn("[FAIL]", salida)
        self.assertIn("[PASS] REPORT-RENDER", salida)
        html = (out / "report.html").read_bytes()
        self.assertIn(b"<html", html.lower())
        self.assertEqual(html, self.esperado(out))

    def test_dir_relativo_se_resuelve_contra_repo_root(self):
        self.sin_plotly()
        out, _ = self.persistir()
        relativo = out.relative_to(self.repo).as_posix()
        codigo, salida, _ = self.correr("render", "--dir", relativo, "--repo-root", str(self.repo))
        self.assertEqual(codigo, 0, salida)
        self.assertTrue((out / "report.html").is_file())

    def test_render_determinista_dos_corridas_bytes_identicos(self):
        self.sin_plotly()
        out, _ = self.persistir()
        self.assertEqual(self.render(out)[0], 0)
        primero = (out / "report.html").read_bytes()
        self.assertEqual(self.render(out)[0], 0)
        self.assertEqual((out / "report.html").read_bytes(), primero)

    def test_solo_se_escribe_report_html(self):
        self.sin_plotly()
        out, _ = self.persistir()
        antes = _archivos(self.repo)
        self.assertEqual(self.render(out)[0], 0)
        despues = _archivos(self.repo)
        nuevos = set(despues) - set(antes)
        self.assertEqual(nuevos, {(out / "report.html").relative_to(self.repo).as_posix()})
        for ruta, firma in antes.items():
            self.assertEqual(despues[ruta], firma, ruta)
        # y ningun residuo temporal
        self.assertEqual([p.name for p in out.glob("*.tmp")], [])

    def test_sin_bundle_warn_visible_y_html_con_aviso(self):
        self.sin_plotly()
        out, _ = self.persistir()
        codigo, salida, _ = self.render(out)
        self.assertEqual(codigo, 0, salida)
        self.assertIn("[WARN] REPORT-RENDER-PLOTLY-UNAVAILABLE", salida)
        html = (out / "report.html").read_text(encoding="utf-8")
        self.assertNotIn(MARCA_BUNDLE, html)
        avisos = [v for v in default_style().editorial.labels.values() if "plotly" in str(v).lower()]
        self.assertTrue(avisos, "el estilo por defecto debe tener un label de aviso de plotly")
        aviso = avisos[0]
        self.assertTrue(
            any(v in html for v in (aviso, html_stdlib.escape(aviso), html_stdlib.escape(aviso, quote=False))),
            "el HTML debe mostrar el aviso de figuras no renderizadas",
        )

    def test_bundle_falso_del_proyecto_via_style_se_embebe(self):
        (self.repo / "vendor").mkdir()
        (self.repo / "vendor" / "plotly.js").write_text(BUNDLE_FALSO, encoding="utf-8")
        estilo = self.repo / ".harmessi" / "report-style.json"
        estilo.parent.mkdir(parents=True, exist_ok=True)
        estilo.write_text(
            json.dumps({"schema_version": 1, "visual": {"chart": {"plotly_js_file": "vendor/plotly.js"}}}),
            encoding="utf-8",
        )
        out, _ = self.persistir()
        codigo, salida, _ = self.render(out)
        self.assertEqual(codigo, 0, salida)
        self.assertNotIn("REPORT-RENDER-PLOTLY-UNAVAILABLE", salida)
        html = (out / "report.html").read_text(encoding="utf-8")
        self.assertEqual(html.count(MARCA_BUNDLE), 1)

    def test_style_explicito_dentro_del_repo(self):
        self.sin_plotly()
        out, _ = self.persistir()
        ruta = self.repo / "config" / "mi_estilo.json"
        ruta.parent.mkdir()
        ruta.write_text(json.dumps({"schema_version": 1, "editorial": {"locale": "es"}}), encoding="utf-8")
        codigo, salida, _ = self.render(out, "--style", "config/mi_estilo.json")
        self.assertEqual(codigo, 0, salida)
        html = (out / "report.html").read_bytes()
        self.assertNotEqual(html, self.esperado(out))  # el override se refleja
        self.assertEqual(self.render(out, "--style", "config/mi_estilo.json", "--check")[0], 0)

    def test_style_invalido_exit_1_y_no_escribe(self):
        self.sin_plotly()
        out, _ = self.persistir()
        ruta = self.repo / "malo.json"
        ruta.write_text(json.dumps({"schema_version": 99}), encoding="utf-8")
        codigo, salida, _ = self.render(out, "--style", "malo.json")
        self.assertEqual(codigo, 1)
        self.assertIn("[FAIL] REPORT-STYLE-INVALID", salida)
        self.assertFalse((out / "report.html").exists())

    def test_style_json_corrupto_o_inexistente_exit_1(self):
        self.sin_plotly()
        out, _ = self.persistir()
        (self.repo / "corrupto.json").write_text("{no es json", encoding="utf-8")
        for ruta in ("corrupto.json", "no_existe.json"):
            with self.subTest(ruta=ruta):
                codigo, salida, _ = self.render(out, "--style", ruta)
                self.assertEqual(codigo, 1)
                self.assertIn("REPORT-STYLE-INVALID", salida)
        self.assertFalse((out / "report.html").exists())

    def test_style_explicito_inexistente_exit_1_no_cae_al_default(self):
        self.sin_plotly()
        out, _ = self.persistir()
        self.assertFalse((self.repo / "no_existe.json").exists())
        codigo, salida, _ = self.render(out, "--style", "no_existe.json")
        self.assertEqual(codigo, 1)
        self.assertIn("[FAIL] REPORT-STYLE-INVALID", salida)
        self.assertFalse((out / "report.html").exists())
        # sin --style, un override ausente sí usa el default
        self.assertEqual(self.render(out)[0], 0)

    def test_style_fuera_del_repo_exit_1(self):
        self.sin_plotly()
        out, _ = self.persistir()
        with tempfile.TemporaryDirectory() as otro:
            ajeno = Path(otro) / "estilo.json"
            ajeno.write_text(json.dumps({"schema_version": 1}), encoding="utf-8")
            codigo, salida, _ = self.render(out, "--style", str(ajeno))
        self.assertEqual(codigo, 1)
        self.assertIn("[FAIL] REPORT-STYLE-INVALID", salida)
        self.assertFalse((out / "report.html").exists())

    def test_override_del_proyecto_invalido_exit_1(self):
        self.sin_plotly()
        out, _ = self.persistir()
        estilo = self.repo / ".harmessi" / "report-style.json"
        estilo.parent.mkdir(parents=True, exist_ok=True)
        estilo.write_text(json.dumps({"schema_version": 1, "clave_desconocida": 1}), encoding="utf-8")
        codigo, salida, _ = self.render(out)
        self.assertEqual(codigo, 1)
        self.assertIn("REPORT-STYLE-INVALID", salida)
        self.assertFalse((out / "report.html").exists())

    def test_repo_root_invalido_exit_3(self):
        out, _ = self.persistir()
        codigo, salida, error = self.correr(
            "render", "--dir", str(out), "--repo-root", str(self.repo / "no_existe")
        )
        self.assertEqual(codigo, 3)
        self.assertEqual(salida, "")
        self.assertIn("--repo-root", error)
        self.assertFalse((out / "report.html").exists())

    def test_error_de_carga_no_filtra_rutas_absolutas_en_texto_ni_json(self):
        out, _ = self.persistir()
        mensaje = (
            f"no se pudo leer {out / 'report.json'} y C:\\Users\\zz_secreto\\a.txt "
            "y /home/usuario_secreto/a.json"
        )
        for extra in ((), ("--json",)):
            with self.subTest(extra=extra):
                with mock.patch.object(cli.validation, "validate_report_dir", return_value=[]), \
                        mock.patch.object(cli.evidence, "read_report_dir", side_effect=evidence.EvidenceError(mensaje)):
                    codigo, salida, error = self.render(out, *extra)
                self.assertEqual(codigo, 1, salida + error)
                self.assertIn("REPORT-RENDER-FAILED", salida)
                total = salida + error
                if extra:
                    total += json.dumps(json.loads(salida))  # decodificado: sin barras escapadas
                    total += " ".join(str(v) for r in json.loads(salida)["results"] for v in r.values())
                for prohibido in (str(self.repo), self.repo.name, "zz_secreto", "usuario_secreto"):
                    self.assertNotIn(prohibido, total)
                self.assertFalse((out / "report.html").exists())

    def test_falta_dir_exit_2(self):
        codigo, _, _ = self.correr("render", "--repo-root", str(self.repo))
        self.assertEqual(codigo, 2)

    def test_artefacto_alterado_exit_1_y_no_escribe_html(self):
        self.sin_plotly()
        out, artefactos = self.persistir()
        rel = next(r for r in sorted(artefactos) if r.startswith("artifacts/tables/"))
        ruta = out.joinpath(*rel.split("/"))
        ruta.write_bytes(ruta.read_bytes() + b" ")
        codigo, salida, _ = self.render(out)
        self.assertEqual(codigo, 1)
        self.assertIn("[FAIL]", salida)
        self.assertFalse((out / "report.html").exists())

    def test_manifest_ausente_exit_1_y_no_escribe_html(self):
        out, _ = self.persistir()
        (out / "manifest.json").unlink()
        codigo, salida, _ = self.render(out)
        self.assertEqual(codigo, 1)
        self.assertIn("[FAIL] REPORT-MANIFEST-MISSING", salida)
        self.assertFalse((out / "report.html").exists())

    def test_include_sensitive_cambia_el_render_pedido(self):
        self.sin_plotly()
        out, _ = self.persistir()
        codigo, salida, _ = self.render(out, "--include-sensitive")
        self.assertEqual(codigo, 0, salida)
        self.assertEqual(
            (out / "report.html").read_bytes(), self.esperado(out, include_sensitive=True)
        )
        # --check debe usar la misma bandera: sin ella, compara contra el render por defecto
        self.assertEqual(self.render(out, "--include-sensitive", "--check")[0], 0)


class TestRenderCheck(_Base):
    def test_check_tras_render_exit_0(self):
        self.sin_plotly()
        out, _ = self.persistir()
        self.assertEqual(self.render(out)[0], 0)
        antes = (out / "report.html").read_bytes()
        codigo, salida, _ = self.render(out, "--check")
        self.assertEqual(codigo, 0, salida)
        self.assertIn("[PASS] REPORT-RENDER-CHECK", salida)
        self.assertEqual((out / "report.html").read_bytes(), antes)

    def test_check_sin_html_exit_1_y_no_lo_crea(self):
        self.sin_plotly()
        out, _ = self.persistir()
        codigo, salida, _ = self.render(out, "--check")
        self.assertEqual(codigo, 1)
        self.assertIn("[FAIL] REPORT-RENDER-CHECK", salida)
        self.assertFalse((out / "report.html").exists())

    def test_check_con_un_byte_alterado_exit_1(self):
        self.sin_plotly()
        out, _ = self.persistir()
        self.assertEqual(self.render(out)[0], 0)
        ruta = out / "report.html"
        datos = bytearray(ruta.read_bytes())
        datos[len(datos) // 2] ^= 0x01
        ruta.write_bytes(bytes(datos))
        alterado = ruta.read_bytes()
        codigo, salida, _ = self.render(out, "--check")
        self.assertEqual(codigo, 1)
        self.assertIn("[FAIL] REPORT-RENDER-CHECK", salida)
        self.assertEqual(ruta.read_bytes(), alterado)  # --check no repara

    def test_check_con_artefacto_alterado_exit_1(self):
        self.sin_plotly()
        out, artefactos = self.persistir()
        self.assertEqual(self.render(out)[0], 0)
        rel = next(r for r in sorted(artefactos) if r.startswith("artifacts/tables/"))
        ruta = out.joinpath(*rel.split("/"))
        ruta.write_bytes(ruta.read_bytes() + b" ")
        self.assertEqual(self.render(out, "--check")[0], 1)


class TestRenderJson(_Base):
    def test_json_bien_formado_en_render_y_check(self):
        self.sin_plotly()
        out, _ = self.persistir()
        for extra, codigo_esperado in (((), "REPORT-RENDER"), (("--check",), "REPORT-RENDER-CHECK")):
            with self.subTest(extra=extra):
                codigo, salida, _ = self.render(out, "--json", *extra)
                self.assertEqual(codigo, 0, salida)
                datos = json.loads(salida)
                self.assertEqual(sorted(datos), ["allowed", "counts", "results"])
                self.assertIs(datos["allowed"], True)
                codigos = [r["code"] for r in datos["results"]]
                self.assertIn(codigo_esperado, codigos)
                self.assertIn("REPORT-RENDER-PLOTLY-UNAVAILABLE", codigos)
                self.assertEqual(datos["counts"].get("FAIL", 0), 0)

    def test_json_con_rechazo_exit_1(self):
        out, _ = self.persistir()
        (out / "manifest.json").unlink()
        codigo, salida, _ = self.render(out, "--json")
        self.assertEqual(codigo, 1)
        datos = json.loads(salida)
        self.assertIs(datos["allowed"], False)
        self.assertGreaterEqual(datos["counts"].get("FAIL", 0), 1)
        self.assertFalse((out / "report.html").exists())

    def test_salida_texto_escapa_caracteres_de_control(self):
        self.sin_plotly()
        out, _ = self.persistir()
        _, salida, _ = self.render(out)
        for linea in salida.splitlines():
            self.assertTrue(linea.startswith("["), linea)
        self.assertNotIn("\r", salida)


class TestRenderSubproceso(_Base):
    def _subproceso(self, *argv):
        return subprocess.run(
            [sys.executable, "-m", "tools.reporting", *argv],
            cwd=str(REPO_REAL), capture_output=True, text=True, timeout=120,
        )

    def test_render_y_check_por_subproceso(self):
        out, _ = self.persistir()
        proceso = self._subproceso("render", "--dir", str(out), "--repo-root", str(self.repo))
        self.assertEqual(proceso.returncode, 0, proceso.stdout + proceso.stderr)
        self.assertTrue((out / "report.html").is_file())
        proceso = self._subproceso("render", "--dir", str(out), "--repo-root", str(self.repo), "--check")
        self.assertEqual(proceso.returncode, 0, proceso.stdout + proceso.stderr)

    def test_check_sin_html_por_subproceso_exit_1(self):
        out, _ = self.persistir()
        proceso = self._subproceso("render", "--dir", str(out), "--repo-root", str(self.repo), "--check")
        self.assertEqual(proceso.returncode, 1, proceso.stdout + proceso.stderr)
        self.assertFalse((out / "report.html").exists())

    def test_repo_root_invalido_por_subproceso_exit_3(self):
        proceso = self._subproceso(
            "render", "--dir", "x", "--repo-root", str(self.repo / "no_existe")
        )
        self.assertEqual(proceso.returncode, 3, proceso.stdout + proceso.stderr)

    def test_uso_invalido_por_subproceso_exit_2(self):
        proceso = self._subproceso("render", "--repo-root", str(self.repo))
        self.assertEqual(proceso.returncode, 2, proceso.stdout + proceso.stderr)


if __name__ == "__main__":
    unittest.main()

"""Tests de `tools/reporting/evidence.py` (v0.6 Change 3, tanda A + ciclo reviewer 1).

Deterministas: sin red, sin pandas. Repos temporales y fixtures 100% genericos
(datos sinteticos; los holdouts de prueba son patrones sinteticos). Los tests de
symlink/junction se omiten solo si el SO no permite crear ninguno.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from tools.reporting import evidence
from tools.reporting.core import (
    Chapter,
    FigureArtifact,
    FigureSpec,
    Insight,
    Report,
    TableArtifact,
    canonical_json,
)
from tools.reporting.evidence import (
    CODE_ISOLATION_HASH,
    EvidenceError,
    ExploratoryIndex,
    build_manifest,
    check_inputs_hash_isolation,
    describe_generated_source,
    describe_source,
    exploratory_hash_index,
    exploratory_index_status,
    expected_artifacts,
    load_report_dir,
    new_run_id,
    prepare_artifacts,
    read_allowed,
    read_report_dir,
    read_within,
    report_from_bytes,
    resolve_git_commit,
    resolve_harmessi_version,
    write_report_dir,
)
from tools.reporting.examples.eda_generic import build_example_report

RUN_ID = "run-20260101T000000Z-abc123"
RELOJ = lambda: "2026-01-01T00:00:00Z"  # noqa: E731
FUTURO = "2999-01-01T00:00:00Z"
PASADO = "2000-01-01T00:00:00Z"
_RE_HEX64 = re.compile(r"[0-9a-f]{64}")


def _crear_enlace_dir(enlace: Path, destino: Path) -> bool:
    """Symlink a directorio; en Windows sin privilegios cae a una junction.
    `False` si el SO no permite ninguno (el llamador hace `skipTest`)."""
    try:
        os.symlink(str(destino), str(enlace), target_is_directory=True)
        return True
    except (OSError, NotImplementedError, AttributeError):
        pass
    if os.name == "nt":
        try:
            import _winapi

            _winapi.CreateJunction(str(destino), str(enlace))
            return True
        except (ImportError, OSError, AttributeError):
            pass
    return False


def _reporte_mini(report_id="rep-a", scope="exploratory", sensible=False, valor=1) -> Report:
    tabla = TableArtifact(
        table_id="tabla_a",
        title="Tabla A",
        columns=("k", "v"),
        rows=(("a", valor), ("b", 2)),
        sensitive=sensible,
    )
    figura = FigureArtifact(
        figure_id="fig_a",
        title="Figura A",
        spec=FigureSpec(chart_type="bar", x="k", y=("v",)),
        backing_table_id="tabla_a",
    )
    insight = Insight(
        insight_id="ins_a",
        technical_claim="tc",
        business_claim="bc",
        evidence_refs=("tabla_a",),
        population="p",
        time_scope="t",
        claim_type="descriptive",
    )
    capitulo = Chapter(chapter_id="cap_a", title="Cap", tables=(tabla,), figures=(figura,), insights=(insight,))
    return Report(report_id=report_id, title="R", report_kind="eda", decision_scope=scope, chapters=(capitulo,))


def _manifest_de(repo, report, artefactos, **extra):
    kwargs = dict(
        repo_root=repo,
        run_id=RUN_ID,
        artifact_bytes=artefactos,
        sources=[describe_generated_source("datos sinteticos", {"semilla": 1})],
        holdout_access="none",
        git_commit=None,
        git_dirty=None,
        harmessi_version=None,
        clock=RELOJ,
    )
    kwargs.update(extra)
    return build_manifest(report, **kwargs)


def _escribir_reporte(repo: Path, subdir: str, report: Report):
    artefactos = prepare_artifacts(report)
    manifest = _manifest_de(repo, report, artefactos)
    out = repo / Path(*subdir.split("/"))
    escritos = write_report_dir(out, artefactos, manifest)
    return out, artefactos, manifest, escritos


class _ConRepoTemporal(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo = Path(self._tmp.name).resolve()

    def _archivo(self, rel: str, contenido: bytes) -> Path:
        ruta = self.repo.joinpath(*rel.split("/"))
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_bytes(contenido)
        return ruta

    def _guardrails(self, **datos):
        self._archivo(".claude/guardrails.json", json.dumps(datos).encode("utf-8"))


class TestPrepareArtifacts(unittest.TestCase):
    def test_layout_conteos_y_sin_tablas_en_report_json(self):
        reporte = build_example_report()
        artefactos = prepare_artifacts(reporte)
        n_tablas = len(list(reporte.iter_tables()))
        n_figuras = len(list(reporte.iter_figures()))
        self.assertGreater(n_tablas, 0)
        self.assertGreater(n_figuras, 0)
        self.assertEqual(len(artefactos), 2 + n_tablas + n_figuras)
        self.assertIn("insights.json", artefactos)
        self.assertIn("artifacts/report.json", artefactos)
        self.assertEqual(sum(k.startswith("artifacts/tables/") for k in artefactos), n_tablas)
        self.assertEqual(sum(k.startswith("artifacts/figures/") for k in artefactos), n_figuras)
        esqueleto = json.loads(artefactos["artifacts/report.json"].decode("utf-8"))
        for capitulo in esqueleto["chapters"]:
            for clave in ("tables", "figures", "insights"):
                self.assertTrue(all(isinstance(i, str) for i in capitulo[clave]))
        self.assertNotIn(b'"rows"', artefactos["artifacts/report.json"])
        self.assertNotIn(b'"spec"', artefactos["artifacts/report.json"])

    def test_formato_json_determinista(self):
        artefactos = prepare_artifacts(_reporte_mini())
        for rel, contenido in artefactos.items():
            self.assertIsInstance(contenido, bytes, rel)
            self.assertTrue(contenido.endswith(b"\n"), rel)
            self.assertIn(b"\n  ", contenido, rel)  # indent=2
            datos = json.loads(contenido.decode("utf-8"))
            self.assertEqual(
                contenido, (json.dumps(datos, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
            )

    def test_mismo_report_mismos_bytes(self):
        self.assertEqual(prepare_artifacts(build_example_report()), prepare_artifacts(build_example_report()))

    def test_tabla_y_figura_contienen_su_to_dict(self):
        reporte = _reporte_mini()
        artefactos = prepare_artifacts(reporte)
        tabla = json.loads(artefactos["artifacts/tables/tabla_a.json"].decode("utf-8"))
        self.assertEqual(tabla, reporte.get_table("tabla_a").to_dict())
        figura = json.loads(artefactos["artifacts/figures/fig_a.json"].decode("utf-8"))
        self.assertEqual(figura, reporte.get_figure("fig_a").to_dict())

    def test_expected_artifacts_es_el_conjunto_exacto(self):
        for reporte in (_reporte_mini(), build_example_report()):
            esperados = expected_artifacts(reporte)
            self.assertEqual(list(esperados), list(prepare_artifacts(reporte)))
            self.assertEqual(esperados["insights.json"], ("insights", "insights"))
            self.assertEqual(esperados["artifacts/report.json"], ("report", "report"))
        mini = expected_artifacts(_reporte_mini())
        self.assertEqual(mini["artifacts/tables/tabla_a.json"], ("tabla_a", "table"))
        self.assertEqual(mini["artifacts/figures/fig_a.json"], ("fig_a", "figure"))


class TestDescribeSource(_ConRepoTemporal):
    def test_fuente_file(self):
        contenido = b"a,b\n1,2\n"
        self._archivo("data/interim/x.csv", contenido)
        fuente = describe_source(self.repo, "data/interim/x.csv")
        self.assertEqual(fuente["kind"], "file")
        self.assertEqual(fuente["role"], "input")
        self.assertEqual(fuente["path"], "data/interim/x.csv")
        self.assertEqual(fuente["sha256"], hashlib.sha256(contenido).hexdigest())
        self.assertEqual(fuente["algorithm"], "sha256/bin/v1")
        self.assertEqual(fuente["size_bytes"], len(contenido))
        for clave in ("rows", "min_date", "max_date", "date_column"):
            self.assertNotIn(clave, fuente)

    def test_opcionales_no_nulos(self):
        self._archivo("d.csv", b"x\n")
        fuente = describe_source(
            self.repo, "d.csv", role="aux", rows=10, min_date="2020-01-01", max_date="2020-12-31", date_column="fecha"
        )
        self.assertEqual(fuente["role"], "aux")
        self.assertEqual(fuente["rows"], 10)
        self.assertEqual(fuente["min_date"], "2020-01-01")
        self.assertEqual(fuente["max_date"], "2020-12-31")
        self.assertEqual(fuente["date_column"], "fecha")

    def test_ruta_absoluta_dentro_del_repo(self):
        ruta = self._archivo("sub/y.csv", b"1\n")
        self.assertEqual(describe_source(self.repo, ruta)["path"], "sub/y.csv")

    def test_inexistente_lanza(self):
        with self.assertRaises(EvidenceError):
            describe_source(self.repo, "no_existe.csv")

    def test_directorio_lanza(self):
        (self.repo / "carpeta").mkdir()
        with self.assertRaises(EvidenceError):
            describe_source(self.repo, "carpeta")

    def test_fuera_del_repo_lanza_sin_exponer_rutas_locales(self):
        with tempfile.TemporaryDirectory() as otro:
            externo = Path(otro) / "ext.csv"
            externo.write_bytes(b"1\n")
            with self.assertRaises(EvidenceError) as ctx:
                describe_source(self.repo, externo)
            self.assertNotIn(str(otro), str(ctx.exception))
            self.assertNotIn(str(self.repo), str(ctx.exception))
            (self.repo / "sub").mkdir()
            relativo = os.path.relpath(externo, self.repo / "sub")  # contiene '..'
            with self.assertRaises(EvidenceError):
                describe_source(self.repo / "sub", relativo)

    def test_symlink_a_fuera_lanza(self):
        with tempfile.TemporaryDirectory() as otro:
            externo = Path(otro) / "ext.csv"
            externo.write_bytes(b"1\n")
            enlace = self.repo / "enlace.csv"
            try:
                os.symlink(externo, enlace)
            except (OSError, NotImplementedError):
                self.skipTest("el SO no permite symlinks")
            with self.assertRaises(EvidenceError):
                describe_source(self.repo, "enlace.csv")

    def test_argumentos_invalidos_lanzan(self):
        self._archivo("d.csv", b"x\n")
        for kwargs in ({"rows": "10"}, {"rows": -1}, {"rows": True}, {"min_date": 5}, {"role": ""}):
            with self.assertRaises(EvidenceError, msg=str(kwargs)):
                describe_source(self.repo, "d.csv", **kwargs)
        for path in (None, "", 5, "a\x00b"):
            with self.assertRaises(EvidenceError, msg=repr(path)):
                describe_source(self.repo, path)


class TestAccesoAntesDeAbrir(_ConRepoTemporal):
    """Invariante: el acceso de lectura se evalua ANTES de abrir cualquier archivo de datos."""

    def _no_debe_hashear(self):
        return mock.patch.object(
            evidence._fingerprint, "calcular_fingerprint", side_effect=AssertionError("se abrió un archivo denegado")
        )

    def test_read_allowed_casos_basicos(self):
        self._archivo("data/ok.csv", b"1\n")
        self._archivo("data/sellado/h.csv", b"secreto\n")
        self._archivo(".env", b"X=1\n")
        self._guardrails(holdouts=["data/sellado/**"])
        self.assertTrue(read_allowed(self.repo, "data/ok.csv")[0])
        permitido, motivo = read_allowed(self.repo, "data/sellado/h.csv")
        self.assertFalse(permitido)
        self.assertTrue(motivo)
        self.assertFalse(read_allowed(self.repo, ".env")[0])
        with tempfile.TemporaryDirectory() as otro:
            self.assertFalse(read_allowed(self.repo, Path(otro) / "x.csv")[0])
            self.assertNotIn(str(otro), read_allowed(self.repo, Path(otro) / "x.csv")[1])

    def test_read_allowed_excepcion_vigente_y_vencida(self):
        self._archivo("data/sellado/h.csv", b"x\n")
        excepcion = {"accion": "read", "ruta": "data/sellado/h.csv", "vence_utc": FUTURO}
        self._guardrails(holdouts=["data/sellado/**"], excepciones=[excepcion])
        self.assertTrue(read_allowed(self.repo, "data/sellado/h.csv")[0])
        excepcion["vence_utc"] = PASADO
        self._guardrails(holdouts=["data/sellado/**"], excepciones=[excepcion])
        self.assertFalse(read_allowed(self.repo, "data/sellado/h.csv")[0])

    def test_read_allowed_guardrails_corrupto_es_fail_closed_y_nunca_lanza(self):
        self._archivo("data/ok.csv", b"1\n")
        self._archivo(".claude/guardrails.json", b"{corrupto")
        self.assertFalse(read_allowed(self.repo, "data/ok.csv")[0])
        for repo, ruta in ((None, "x"), (self.repo, None), (self.repo, 5), (self.repo, "a\x00b"), (5, "x")):
            resultado = read_allowed(repo, ruta)
            self.assertEqual(resultado[0], False, repr((repo, ruta)))
            self.assertIsInstance(resultado[1], str)

    def test_describe_source_en_holdout_no_se_abre(self):
        self._archivo("data/sellado/h.csv", b"secreto\n")
        self._guardrails(holdouts=["data/sellado/**"])
        with self._no_debe_hashear() as espia:
            with self.assertRaises(EvidenceError) as ctx:
                describe_source(self.repo, "data/sellado/h.csv")
        self.assertIn("acceso denegado", str(ctx.exception))
        espia.assert_not_called()

    def test_describe_source_holdout_con_excepcion_vigente_se_describe(self):
        self._archivo("data/sellado/h.csv", b"secreto\n")
        self._guardrails(
            holdouts=["data/sellado/**"],
            excepciones=[{"accion": "read", "ruta": "data/sellado/h.csv", "vence_utc": FUTURO}],
        )
        fuente = describe_source(self.repo, "data/sellado/h.csv")
        self.assertEqual(fuente["sha256"], hashlib.sha256(b"secreto\n").hexdigest())

    def test_describe_source_env_guardrails_corrupto_y_fuera_no_se_abren(self):
        self._archivo(".env", b"X=1\n")
        with self._no_debe_hashear() as espia:
            with self.assertRaises(EvidenceError) as ctx:
                describe_source(self.repo, ".env")
            self.assertIn("acceso denegado", str(ctx.exception))
            with tempfile.TemporaryDirectory() as otro:
                externo = Path(otro) / "e.csv"
                externo.write_bytes(b"1\n")
                with self.assertRaises(EvidenceError):
                    describe_source(self.repo, externo)
            self._archivo("data/ok.csv", b"1\n")
            self._archivo(".claude/guardrails.json", b"{corrupto")
            with self.assertRaises(EvidenceError) as ctx:
                describe_source(self.repo, "data/ok.csv")
            self.assertIn("acceso denegado", str(ctx.exception))
        espia.assert_not_called()

    def test_check_input_en_holdout_no_verificable_sin_abrir(self):
        self._archivo("data/sellado/h.csv", b"secreto\n")
        self._guardrails(holdouts=["data/sellado/**"])
        with self._no_debe_hashear() as espia:
            resultados = check_inputs_hash_isolation(self.repo, "model_valid", ["data/sellado/h.csv"])
        espia.assert_not_called()
        self.assertEqual([(r.status, r.kind) for r in resultados], [("FAIL", "technical_error")])
        self.assertEqual(resultados[0].subject, "data/sellado/h.csv")
        self.assertIn("no verificable: acceso denegado (no se abrió)", resultados[0].message)
        self.assertNotIn(str(self.repo), resultados[0].message + (resultados[0].detail or ""))

    def test_check_directorio_input_que_contiene_holdout(self):
        self._archivo("data/lote/ok.csv", b"1\n")
        self._archivo("data/lote/sellado/h.csv", b"secreto\n")
        self._guardrails(holdouts=["data/lote/sellado/**"])
        original = evidence._fingerprint.calcular_fingerprint
        abiertos = []

        def espia(ruta, *args, **kwargs):
            abiertos.append(Path(ruta).name)
            return original(ruta, *args, **kwargs)

        with mock.patch.object(evidence._fingerprint, "calcular_fingerprint", side_effect=espia):
            resultados = check_inputs_hash_isolation(self.repo, "model_valid", ["data/lote"])
        self.assertEqual(abiertos, ["ok.csv"])
        fallos = [r for r in resultados if r.status == "FAIL"]
        self.assertEqual([(f.subject, f.kind) for f in fallos], [("data/lote/sellado/h.csv", "technical_error")])

    def test_check_guardrails_corrupto_y_fuera_del_repo_fail_closed(self):
        self._archivo("data/ok.csv", b"1\n")
        self._archivo(".claude/guardrails.json", b"{corrupto")
        with tempfile.TemporaryDirectory() as otro:
            externo = Path(otro) / "e.csv"
            externo.write_bytes(b"1\n")
            with self._no_debe_hashear() as espia:
                r1 = check_inputs_hash_isolation(self.repo, "model_valid", ["data/ok.csv"])
                r2 = check_inputs_hash_isolation(self.repo, "operational", [externo])
            espia.assert_not_called()
        for resultados in (r1, r2):
            self.assertEqual([(r.status, r.kind) for r in resultados], [("FAIL", "technical_error")])
        self.assertNotIn(str(otro), " ".join(r.message + (r.subject or "") for r in r2))

    def test_read_within_con_repo_root_deniega_antes_de_leer(self):
        out, _a, _m, _e = _escribir_reporte(self.repo, "out/h", _reporte_mini())
        self._guardrails(holdouts=["out/h/**"])
        with mock.patch.object(Path, "read_bytes", side_effect=AssertionError("se leyó un archivo denegado")):
            with self.assertRaises(EvidenceError) as ctx:
                read_within(out, "manifest.json", repo_root=self.repo)
        self.assertIn("acceso denegado", str(ctx.exception))
        self.assertIn("manifest.json", str(ctx.exception))
        # sin repo_root no evalua acceso (uso local); con repo_root permitido lee
        self._guardrails(holdouts=["otro/**"])
        self.assertTrue(read_within(out, "manifest.json", repo_root=self.repo).startswith(b"{"))


class TestDescribeGeneratedSource(unittest.TestCase):
    def test_hash_de_canonical_json_de_params(self):
        params = {"n": 100, "semilla": 42, "cols": ["a", "b"]}
        fuente = describe_generated_source("sintetico", params)
        self.assertEqual(fuente["kind"], "generated")
        self.assertEqual(fuente["role"], "input")
        self.assertEqual(fuente["description"], "sintetico")
        self.assertEqual(fuente["params"], params)
        self.assertEqual(fuente["algorithm"], "sha256/bin/v1")
        self.assertEqual(fuente["sha256"], hashlib.sha256(canonical_json(params).encode("utf-8")).hexdigest())

    def test_orden_de_claves_no_cambia_hash(self):
        a = describe_generated_source("d", {"x": 1, "y": 2})
        b = describe_generated_source("d", {"y": 2, "x": 1})
        self.assertEqual(a["sha256"], b["sha256"])

    def test_params_distintos_hash_distinto(self):
        self.assertNotEqual(
            describe_generated_source("d", {"x": 1})["sha256"], describe_generated_source("d", {"x": 2})["sha256"]
        )

    def test_description_vacia_lanza(self):
        for descripcion in ("", "   ", None):
            with self.assertRaises(EvidenceError, msg=repr(descripcion)):
                describe_generated_source(descripcion, {"x": 1})

    def test_params_no_json_seguros_lanzan(self):
        for params in ({"x": {1, 2}}, {"x": float("nan")}, {"x": float("inf")}, {1: "a"}, {"x": object()}, None, [1]):
            with self.assertRaises(EvidenceError, msg=repr(params)):
                describe_generated_source("d", params)


class TestNewRunIdYEntorno(_ConRepoTemporal):
    def test_formato_y_prefijo_determinista(self):
        ahora = datetime(2026, 3, 4, 5, 6, 7, tzinfo=timezone.utc)
        a, b = new_run_id(ahora), new_run_id(ahora)
        for run_id in (a, b):
            self.assertRegex(run_id, r"^run-20260304T050607Z-[0-9a-f]+$")
        self.assertEqual(a.rsplit("-", 1)[0], b.rsplit("-", 1)[0])

    def test_sufijo_explicito_y_zonas(self):
        ahora = datetime(2026, 3, 4, 5, 6, 7, tzinfo=timezone(timedelta(hours=-3)))
        self.assertEqual(new_run_id(ahora, suffix="zzz"), "run-20260304T080607Z-zzz")
        self.assertEqual(new_run_id(datetime(2026, 3, 4, 5, 6, 7), suffix="q"), "run-20260304T050607Z-q")

    def test_sin_now_usa_formato_valido(self):
        self.assertRegex(new_run_id(), r"^run-\d{8}T\d{6}Z-[0-9a-f]+$")

    def test_git_sin_repo_devuelve_none(self):
        self.assertEqual(resolve_git_commit(self.repo), (None, None))

    def test_git_nunca_lanza(self):
        with mock.patch.object(evidence.repo_mod, "get_head", side_effect=RuntimeError("git no disponible")):
            self.assertEqual(resolve_git_commit(self.repo), (None, None))
        self.assertEqual(resolve_git_commit(None), (None, None))

    def test_git_commit_y_dirty(self):
        commit = "a" * 40
        with mock.patch.object(evidence.repo_mod, "get_head", return_value=(commit, "main")):
            with mock.patch.object(evidence.repo_mod, "list_dirty_files", return_value=["x.py"]):
                self.assertEqual(resolve_git_commit(self.repo), (commit, True))
            with mock.patch.object(evidence.repo_mod, "list_dirty_files", return_value=[]):
                self.assertEqual(resolve_git_commit(self.repo), (commit, False))

    def test_git_head_no_valido_devuelve_none(self):
        with mock.patch.object(evidence.repo_mod, "get_head", return_value=("HEAD", "HEAD")):
            self.assertEqual(resolve_git_commit(self.repo), (None, None))

    def test_version_harmessi(self):
        self.assertIsNone(resolve_harmessi_version(self.repo))
        self._archivo(".ds_init/control.json", b'{"harness_version": "0.6.0"}')
        self.assertEqual(resolve_harmessi_version(self.repo), "0.6.0")
        self._archivo(".ds_init/control.json", b"{corrupto")
        self.assertIsNone(resolve_harmessi_version(self.repo))
        self._archivo(".ds_init/control.json", b'{"harness_version": 5}')
        self.assertIsNone(resolve_harmessi_version(self.repo))
        self._archivo(".ds_init/control.json", b"[1]")
        self.assertIsNone(resolve_harmessi_version(self.repo))
        self.assertIsNone(resolve_harmessi_version(None))


class TestBuildManifest(_ConRepoTemporal):
    def test_esquema_y_hashes_de_bytes_persistidos(self):
        reporte = build_example_report()
        artefactos = prepare_artifacts(reporte)
        manifest = _manifest_de(self.repo, reporte, artefactos)
        self.assertEqual(
            set(manifest),
            {
                "schema_version", "report_id", "run_id", "report_kind", "decision_scope", "data_cutoff",
                "git_commit", "git_dirty", "harmessi_version", "generated_at", "sources", "exclusions",
                "holdout_access", "sensitivity", "source_notebook", "artifacts", "hashes",
            },
        )
        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(manifest["report_id"], reporte.report_id)
        self.assertEqual(manifest["run_id"], RUN_ID)
        self.assertEqual(manifest["report_kind"], reporte.report_kind)
        self.assertEqual(manifest["decision_scope"], reporte.decision_scope)
        self.assertEqual(manifest["generated_at"], "2026-01-01T00:00:00Z")
        self.assertEqual(manifest["holdout_access"], "none")
        self.assertEqual(manifest["hashes"], {"report_content": reporte.content_sha256()})
        self.assertIsNone(manifest["source_notebook"])
        archivos = [a["file"] for a in manifest["artifacts"]]
        self.assertEqual(sorted(archivos), sorted(artefactos))
        self.assertNotIn("manifest.json", archivos)
        esperados = expected_artifacts(reporte)
        for artefacto in manifest["artifacts"]:
            self.assertEqual((artefacto["id"], artefacto["kind"]), esperados[artefacto["file"]])
            self.assertEqual(artefacto["sha256"], hashlib.sha256(artefactos[artefacto["file"]]).hexdigest())
            self.assertRegex(artefacto["sha256"], _RE_HEX64)

    def test_archivos_fuera_del_layout_no_se_listan(self):
        reporte = _reporte_mini()
        artefactos = dict(prepare_artifacts(reporte))
        artefactos["extra/otro.json"] = b"{}\n"
        manifest = _manifest_de(self.repo, reporte, artefactos)
        self.assertNotIn("extra/otro.json", [a["file"] for a in manifest["artifacts"]])

    def test_sin_fuentes_no_lanza(self):
        reporte = _reporte_mini()
        manifest = build_manifest(
            reporte,
            repo_root=self.repo,
            run_id=RUN_ID,
            artifact_bytes=prepare_artifacts(reporte),
            holdout_access="none",
            git_commit=None,
            git_dirty=None,
            harmessi_version=None,
            clock=RELOJ,
        )
        self.assertEqual(manifest["sources"], [])
        self.assertEqual(manifest["exclusions"], [])

    def test_holdout_access_obligatorio(self):
        reporte = _reporte_mini()
        with self.assertRaises(TypeError):
            build_manifest(reporte, repo_root=self.repo, run_id=RUN_ID, artifact_bytes=prepare_artifacts(reporte))

    def test_sensibilidad(self):
        limpio = _reporte_mini()
        m = _manifest_de(self.repo, limpio, prepare_artifacts(limpio))
        self.assertEqual(m["sensitivity"], {"contains_sensitive": False, "sensitive_artifacts": []})
        sensible = _reporte_mini(sensible=True)
        m = _manifest_de(self.repo, sensible, prepare_artifacts(sensible))
        self.assertEqual(m["sensitivity"], {"contains_sensitive": True, "sensitive_artifacts": ["tabla_a"]})

    def test_fuentes_exclusiones_cutoff_y_notebook(self):
        self._archivo("data/d.csv", b"x\n")
        self._archivo("notebooks/n.ipynb", b"{}")
        reporte = _reporte_mini()
        artefactos = prepare_artifacts(reporte)
        fuente = describe_source(self.repo, "data/d.csv", rows=1)
        exclusion = {"description": "nulos", "reason": "sin fecha", "rows_excluded": 3}
        manifest = _manifest_de(
            self.repo,
            reporte,
            artefactos,
            sources=[fuente],
            exclusions=[exclusion],
            data_cutoff="2025-12-31",
            source_notebook=describe_source(self.repo, "notebooks/n.ipynb"),
        )
        self.assertEqual(manifest["sources"], [fuente])
        self.assertEqual(manifest["exclusions"], [exclusion])
        self.assertEqual(manifest["data_cutoff"], "2025-12-31")
        self.assertEqual(set(manifest["source_notebook"]), {"path", "sha256", "algorithm"})
        self.assertEqual(manifest["source_notebook"]["path"], "notebooks/n.ipynb")
        manifest2 = _manifest_de(self.repo, reporte, artefactos, source_notebook="notebooks/n.ipynb")
        self.assertEqual(manifest2["source_notebook"], manifest["source_notebook"])

    def test_source_notebook_dict_se_normaliza_o_lanza(self):
        reporte = _reporte_mini()
        artefactos = prepare_artifacts(reporte)
        sha = "a" * 64
        m = _manifest_de(
            self.repo, reporte, artefactos, source_notebook={"path": "notebooks\\n.ipynb", "sha256": sha}
        )
        self.assertEqual(m["source_notebook"], {"path": "notebooks/n.ipynb", "sha256": sha, "algorithm": "sha256/bin/v1"})
        for ruta in ("/abs/n.ipynb", "C:\\x\\n.ipynb", "C:/x/n.ipynb", "../n.ipynb", "a/../n.ipynb", "", None, 5):
            with self.assertRaises(EvidenceError, msg=repr(ruta)):
                _manifest_de(self.repo, reporte, artefactos, source_notebook={"path": ruta, "sha256": sha})
        with self.assertRaises(EvidenceError):
            _manifest_de(self.repo, reporte, artefactos, source_notebook="no_existe.ipynb")

    def test_reloj_datetime_y_por_defecto(self):
        reporte = _reporte_mini()
        artefactos = prepare_artifacts(reporte)
        m = _manifest_de(self.repo, reporte, artefactos, clock=lambda: datetime(2026, 2, 3, 4, 5, 6, tzinfo=timezone.utc))
        self.assertEqual(m["generated_at"], "2026-02-03T04:05:06Z")
        m = _manifest_de(self.repo, reporte, artefactos, clock=None)
        self.assertRegex(m["generated_at"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")

    def test_git_y_version_automaticos(self):
        reporte = _reporte_mini()
        artefactos = prepare_artifacts(reporte)
        self._archivo(".ds_init/control.json", b'{"harness_version": "0.6.0"}')
        with mock.patch.object(evidence.repo_mod, "get_head", return_value=("b" * 40, "main")):
            with mock.patch.object(evidence.repo_mod, "list_dirty_files", return_value=[]):
                m = build_manifest(
                    reporte, repo_root=self.repo, run_id=RUN_ID, artifact_bytes=artefactos,
                    holdout_access="none", clock=RELOJ,
                )
        self.assertEqual(m["git_commit"], "b" * 40)
        self.assertIs(m["git_dirty"], False)
        self.assertEqual(m["harmessi_version"], "0.6.0")


class TestWriteYLoad(_ConRepoTemporal):
    def test_escribe_en_orden_con_manifest_ultimo(self):
        reporte = _reporte_mini()
        out, artefactos, manifest, escritos = _escribir_reporte(self.repo, "out/x", reporte)
        self.assertEqual(escritos[-1], "manifest.json")
        self.assertEqual(escritos[:-1], list(artefactos))
        for rel in escritos[:-1]:
            self.assertEqual((out / Path(*rel.split("/"))).read_bytes(), artefactos[rel])
        self.assertEqual((out / "manifest.json").read_bytes(), evidence.manifest_to_bytes(manifest))
        self.assertEqual(json.loads((out / "manifest.json").read_text(encoding="utf-8")), manifest)
        self.assertEqual([p for p in out.rglob("*.tmp")], [])

    def test_corte_antes_del_manifest_deja_directorio_sin_manifest(self):
        reporte = _reporte_mini()
        artefactos = prepare_artifacts(reporte)
        manifest = _manifest_de(self.repo, reporte, artefactos)
        original = evidence.dsguard_core.escribir_texto_atomico

        def falla_en_manifest(ruta, texto):
            if Path(ruta).name == "manifest.json":
                raise OSError("corte simulado")
            return original(ruta, texto)

        out = self.repo / "out" / "y"
        with mock.patch.object(evidence.dsguard_core, "escribir_texto_atomico", side_effect=falla_en_manifest):
            with self.assertRaises(OSError):
                write_report_dir(out, artefactos, manifest)
        self.assertFalse((out / "manifest.json").exists())
        self.assertTrue((out / "insights.json").exists())

    def test_rutas_inseguras_o_manifest_en_artefactos_lanzan(self):
        manifest = {"a": 1}
        for rel in ("../fuga.json", "/abs.json", "a\\b.json", "C:x.json", "", "a//b.json", "./a.json", "con.json", "a\x00b.json"):
            with self.assertRaises(EvidenceError, msg=repr(rel)):
                write_report_dir(self.repo / "o", {rel: b"{}"}, manifest)
        with self.assertRaises(EvidenceError):
            write_report_dir(self.repo / "o", {"manifest.json": b"{}"}, manifest)
        with self.assertRaises(EvidenceError):
            write_report_dir(self.repo / "o", {"a.json": "texto"}, manifest)
        self.assertFalse((self.repo / "o").exists())
        self.assertFalse((self.repo / "fuga.json").exists())

    def test_reproducibilidad_byte_a_byte(self):
        self._archivo("data/d.csv", b"a,b\n1,2\n")
        reporte = build_example_report()
        dirs = []
        for nombre in ("uno", "dos"):
            artefactos = prepare_artifacts(reporte)
            fuente = describe_source(self.repo, "data/d.csv", rows=1)
            manifest = _manifest_de(self.repo, reporte, artefactos, sources=[fuente])
            out = self.repo / nombre
            write_report_dir(out, artefactos, manifest)
            dirs.append(out)
        contenidos = []
        for out in dirs:
            contenidos.append({p.relative_to(out).as_posix(): p.read_bytes() for p in sorted(out.rglob("*")) if p.is_file()})
        self.assertEqual(contenidos[0], contenidos[1])
        self.assertIn("manifest.json", contenidos[0])

    def test_round_trip_ejemplo(self):
        reporte = build_example_report()
        out, _artefactos, manifest, _escritos = _escribir_reporte(self.repo, "out/ej", reporte)
        cargado, manifest_leido = load_report_dir(out)
        self.assertEqual(cargado.content_sha256(), reporte.content_sha256())
        self.assertEqual(cargado.to_dict(), reporte.to_dict())
        self.assertEqual(manifest_leido, manifest)

    def test_round_trip_reescribir_da_mismos_bytes(self):
        reporte = build_example_report()
        out, artefactos, _m, _e = _escribir_reporte(self.repo, "out/a", reporte)
        cargado, _ = load_report_dir(out)
        self.assertEqual(prepare_artifacts(cargado), artefactos)

    def test_read_report_dir_devuelve_bytes_persistidos_leidos_una_vez(self):
        reporte = _reporte_mini()
        out, artefactos, manifest, escritos = _escribir_reporte(self.repo, "out/rr", reporte)
        original = Path.read_bytes
        leidos = []

        def espia(self_path):
            leidos.append(self_path.name)
            return original(self_path)

        with mock.patch.object(Path, "read_bytes", espia):
            files, manifest_leido = read_report_dir(out)
        # cada archivo exactamente una vez (single-read)
        self.assertEqual(sorted(leidos), sorted(Path(rel).name for rel in escritos))
        self.assertEqual(manifest_leido, manifest)
        for rel, contenido in artefactos.items():
            self.assertEqual(files[rel], contenido)
        self.assertEqual(files["manifest.json"], evidence.manifest_to_bytes(manifest))

    def test_hash_de_artefacto_alterado_detectable_por_bytes(self):
        reporte = _reporte_mini()
        out, artefactos, manifest, _ = _escribir_reporte(self.repo, "out/b", reporte)
        ruta = out / "artifacts" / "tables" / "tabla_a.json"
        ruta.write_bytes(ruta.read_bytes().replace(b"2", b"3", 1))
        listado = {a["file"]: a["sha256"] for a in manifest["artifacts"]}
        self.assertNotEqual(hashlib.sha256(ruta.read_bytes()).hexdigest(), listado["artifacts/tables/tabla_a.json"])
        for rel, sha in listado.items():
            if rel != "artifacts/tables/tabla_a.json":
                self.assertEqual(hashlib.sha256((out / Path(*rel.split("/"))).read_bytes()).hexdigest(), sha)

    def _dir(self, nombre="out/z"):
        out, _artefactos, _manifest, _ = _escribir_reporte(self.repo, nombre, _reporte_mini())
        return out

    def test_load_manifest_ausente_o_corrupto(self):
        out = self._dir("out/1")
        (out / "manifest.json").unlink()
        with self.assertRaises(EvidenceError) as ctx:
            load_report_dir(out)
        self.assertIn("manifest.json", str(ctx.exception))
        out = self._dir("out/2")
        (out / "manifest.json").write_bytes(b"{no es json")
        with self.assertRaises(EvidenceError) as ctx:
            load_report_dir(out)
        self.assertIn("manifest.json", str(ctx.exception))
        out = self._dir("out/3")
        (out / "manifest.json").write_bytes(b"[1, 2]")
        with self.assertRaises(EvidenceError):
            load_report_dir(out)

    def test_load_archivo_faltante_o_corrupto_nombra_archivo(self):
        for n, rel in enumerate(
            ("insights.json", "artifacts/report.json", "artifacts/tables/tabla_a.json", "artifacts/figures/fig_a.json")
        ):
            out = self._dir(f"out/f_{n}")
            ruta = out / Path(*rel.split("/"))
            ruta.unlink()
            with self.assertRaises(EvidenceError, msg=rel) as ctx:
                load_report_dir(out)
            self.assertIn(rel, str(ctx.exception))
            self.assertNotIn(str(self.repo), str(ctx.exception))
            ruta.write_bytes(b"{corrupto")
            with self.assertRaises(EvidenceError, msg=rel) as ctx:
                load_report_dir(out)
            self.assertIn(rel, str(ctx.exception))

    def test_load_contenido_alterado_falla_por_hash_logico(self):
        out = self._dir("out/alt")
        ruta = out / "artifacts" / "tables" / "tabla_a.json"
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        datos["rows"][0][1] = 999
        ruta.write_bytes(evidence._json_bytes(datos))
        with self.assertRaises(EvidenceError) as ctx:
            load_report_dir(out)
        self.assertIn("hashes.report_content", str(ctx.exception))

    def test_load_manifest_sin_hash_de_contenido(self):
        out = self._dir("out/sh")
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        del manifest["hashes"]
        (out / "manifest.json").write_bytes(evidence._json_bytes(manifest))
        with self.assertRaises(EvidenceError) as ctx:
            load_report_dir(out)
        self.assertIn("hashes.report_content", str(ctx.exception))

    def test_load_id_sin_archivo_o_inseguro_no_lee_fuera_del_directorio(self):
        out = self._dir("out/idx")
        ruta = out / "artifacts" / "report.json"
        original_json = json.loads(ruta.read_text(encoding="utf-8"))
        # id valido sin archivo: el mensaje nombra el archivo esperado
        esqueleto = json.loads(json.dumps(original_json))
        esqueleto["chapters"][0]["tables"].append("no_existe")
        ruta.write_bytes(evidence._json_bytes(esqueleto))
        with self.assertRaises(EvidenceError) as ctx:
            load_report_dir(out)
        self.assertIn("artifacts/tables/no_existe.json", str(ctx.exception))
        # ids inseguros: se rechazan como "id inválido" SIN leer nada fuera de out
        self._archivo("out/secreto.json", b"{}")
        original = Path.read_bytes
        leidos = []

        def espia(self_path):
            leidos.append(self_path.resolve())
            return original(self_path)

        for inseguro in ("../../manifest", "../idx", "con", "a/b", "A", "x" * 65, "a\x00b"):
            esqueleto = json.loads(json.dumps(original_json))
            esqueleto["chapters"][0]["tables"].append(inseguro)
            ruta.write_bytes(evidence._json_bytes(esqueleto))
            leidos.clear()
            with mock.patch.object(Path, "read_bytes", espia):
                with self.assertRaises(EvidenceError, msg=repr(inseguro)) as ctx:
                    load_report_dir(out)
            self.assertIn("id inválido", str(ctx.exception), repr(inseguro))
            base = out.resolve()
            for leido in leidos:
                leido.relative_to(base)  # lanza ValueError si se leyó fuera del directorio

    def test_load_insight_faltante(self):
        out = self._dir("out/ins")
        (out / "insights.json").write_bytes(evidence._json_bytes({"insights": []}))
        with self.assertRaises(EvidenceError) as ctx:
            load_report_dir(out)
        self.assertIn("ins_a", str(ctx.exception))

    def test_load_directorio_inexistente(self):
        with self.assertRaises(EvidenceError):
            load_report_dir(self.repo / "no_existe")

    def test_load_con_repo_root_deniega_holdout_o_secreto_sin_abrir(self):
        out = self._dir("out/h")
        # holdout que cubre todo el directorio del reporte
        self._guardrails(holdouts=["out/h/**"])
        with mock.patch.object(Path, "read_bytes", side_effect=AssertionError("se abrió un archivo denegado")):
            with self.assertRaises(EvidenceError) as ctx:
                load_report_dir(out, repo_root=self.repo)
        self.assertIn("acceso denegado", str(ctx.exception))
        # solo un artefacto cae en el holdout: el manifest se lee, el artefacto no
        self._guardrails(holdouts=["out/h/artifacts/tables/**"])
        original = Path.read_bytes
        leidos = []

        def espia(self_path):
            leidos.append(self_path.name)
            return original(self_path)

        with mock.patch.object(Path, "read_bytes", espia):
            with self.assertRaises(EvidenceError) as ctx:
                load_report_dir(out, repo_root=self.repo)
        self.assertIn("artifacts/tables/tabla_a.json", str(ctx.exception))
        self.assertIn("acceso denegado", str(ctx.exception))
        self.assertNotIn("tabla_a.json", leidos)
        # secreto (.env como parte del reporte)
        out2 = self._dir("out/env")
        self._guardrails(secretos_extra=["out/env/manifest.json"])
        with mock.patch.object(Path, "read_bytes", side_effect=AssertionError("se abrió un secreto")):
            with self.assertRaises(EvidenceError):
                load_report_dir(out2, repo_root=self.repo)

    def test_load_con_repo_root_permitido_y_sin_repo_root_conserva_comportamiento(self):
        out = self._dir("out/ok")
        reporte = _reporte_mini()
        self._guardrails(holdouts=["otro/**"])
        con, _ = load_report_dir(out, repo_root=self.repo)
        self.assertEqual(con.content_sha256(), reporte.content_sha256())
        # sin repo_root no se evalua acceso (uso local explicito), aunque haya holdout
        self._guardrails(holdouts=["out/ok/**"])
        sin, _ = load_report_dir(out)
        self.assertEqual(sin.content_sha256(), reporte.content_sha256())


class TestReadWithin(_ConRepoTemporal):
    def test_rel_inseguro_lanza_evidence_error_no_value_error(self):
        out = self.repo / "out"
        out.mkdir()
        (out / "a.json").write_bytes(b"{}")
        for rel in ("a/../b", "../a.json", "a\x00b", "con.json", "artifacts/NUL.txt", "/abs", "a\\b", "", "x.", "C:a", None, 5):
            with self.assertRaises(EvidenceError, msg=repr(rel)):
                read_within(out, rel)
        self.assertEqual(read_within(out, "a.json"), b"{}")

    def test_lee_una_sola_vez(self):
        out, _a, _m, _e = _escribir_reporte(self.repo, "out/u", _reporte_mini())
        original = Path.read_bytes
        llamadas = []

        def espia(self_path):
            llamadas.append(self_path)
            return original(self_path)

        with mock.patch.object(Path, "read_bytes", espia):
            contenido = read_within(out, "artifacts/tables/tabla_a.json")
        self.assertEqual(len(llamadas), 1)
        self.assertEqual(contenido, (out / "artifacts" / "tables" / "tabla_a.json").read_bytes())

    def test_junction_o_symlink_de_directorio_bajo_artifacts_se_rechaza(self):
        out, _a, _m, _e = _escribir_reporte(self.repo, "out/j", _reporte_mini())
        tablas = out / "artifacts" / "tables"
        tienda = self.repo / "store" / "tables"
        shutil.copytree(tablas, tienda)
        shutil.rmtree(tablas)
        if not _crear_enlace_dir(tablas, tienda):
            self.skipTest("el SO no permite symlinks ni junctions")
        with self.assertRaises(EvidenceError) as ctx:
            read_within(out, "artifacts/tables/tabla_a.json")
        self.assertIn("symlink", str(ctx.exception))
        with self.assertRaises(EvidenceError):
            load_report_dir(out)
        with self.assertRaises(EvidenceError):
            read_report_dir(out)

    def test_symlink_de_archivo_se_rechaza(self):
        out, _a, _m, _e = _escribir_reporte(self.repo, "out/s", _reporte_mini())
        externo = self._archivo("store/ext.json", b"{}")
        objetivo = out / "artifacts" / "tables" / "tabla_a.json"
        objetivo.unlink()
        try:
            os.symlink(externo, objetivo)
        except (OSError, NotImplementedError):
            self.skipTest("el SO no permite symlinks de archivo")
        with self.assertRaises(EvidenceError):
            read_within(out, "artifacts/tables/tabla_a.json")


class TestReportFromBytes(_ConRepoTemporal):
    def _armar(self):
        reporte = _reporte_mini()
        artefactos = prepare_artifacts(reporte)
        manifest = _manifest_de(self.repo, reporte, artefactos)
        return reporte, artefactos, manifest

    def test_reconstruye_sin_tocar_disco(self):
        reporte, artefactos, manifest = self._armar()
        with mock.patch("builtins.open", side_effect=AssertionError("tocó disco")):
            with mock.patch.object(Path, "read_bytes", side_effect=AssertionError("tocó disco")):
                with mock.patch.object(Path, "read_text", side_effect=AssertionError("tocó disco")):
                    cargado = report_from_bytes(artefactos, manifest)
        self.assertEqual(cargado.content_sha256(), reporte.content_sha256())

    def test_errores(self):
        _reporte, artefactos, manifest = self._armar()
        for rel in artefactos:
            faltante = {k: v for k, v in artefactos.items() if k != rel}
            with self.assertRaises(EvidenceError, msg=rel) as ctx:
                report_from_bytes(faltante, manifest)
            self.assertIn(rel, str(ctx.exception))
        alterado = dict(artefactos)
        alterado["artifacts/tables/tabla_a.json"] = artefactos["artifacts/tables/tabla_a.json"].replace(b"2", b"3", 1)
        with self.assertRaises(EvidenceError) as ctx:
            report_from_bytes(alterado, manifest)
        self.assertIn("hashes.report_content", str(ctx.exception))
        corrupto = dict(artefactos)
        corrupto["insights.json"] = b"{corrupto"
        with self.assertRaises(EvidenceError):
            report_from_bytes(corrupto, manifest)
        for basura in (None, [], "x"):
            with self.assertRaises(EvidenceError):
                report_from_bytes(artefactos, basura)
            with self.assertRaises(EvidenceError):
                report_from_bytes(basura, manifest)
        sin_hash = {k: v for k, v in manifest.items() if k != "hashes"}
        with self.assertRaises(EvidenceError):
            report_from_bytes(artefactos, sin_hash)


class TestIndiceExploratory(_ConRepoTemporal):
    def test_indexa_solo_exploratory_con_report_id_y_file(self):
        _o, artefactos_e, manifest_e, _ = _escribir_reporte(self.repo, "reports/exploratory/rep-a", _reporte_mini("rep-a"))
        _escribir_reporte(self.repo, "reports/model_valid/rep-b", _reporte_mini("rep-b", scope="model_valid", valor=5))
        indice = exploratory_hash_index(self.repo)
        sha_tabla = hashlib.sha256(artefactos_e["artifacts/tables/tabla_a.json"]).hexdigest()
        self.assertEqual(
            indice[sha_tabla],
            {"report_id": "rep-a", "file": "reports/exploratory/rep-a/artifacts/tables/tabla_a.json"},
        )
        self.assertEqual(set(indice), {a["sha256"] for a in manifest_e["artifacts"]})
        sha_valid = hashlib.sha256(
            prepare_artifacts(_reporte_mini("rep-b", scope="model_valid", valor=5))["artifacts/tables/tabla_a.json"]
        ).hexdigest()
        self.assertNotIn(sha_valid, indice)
        estado = exploratory_index_status(self.repo)
        self.assertEqual((estado.truncated, estado.error, estado.unreadable_manifests), (False, None, 0))
        self.assertEqual(estado.index, indice)

    def test_estado_es_dataclass_inmutable(self):
        estado = ExploratoryIndex()
        self.assertEqual((estado.index, estado.truncated, estado.error, estado.unreadable_manifests), ({}, False, None, 0))
        with self.assertRaises(Exception):
            estado.truncated = True  # frozen

    def test_manifests_ilegibles_o_sin_forma_se_cuentan(self):
        self._archivo("reports/exploratory/malo1/manifest.json", b"{no json")
        self._archivo("reports/exploratory/malo2/manifest.json", b"[1]")
        self._archivo("reports/exploratory/malo3/manifest.json", b'{"decision_scope": "exploratory"}')
        self._archivo(
            "reports/exploratory/ok4/manifest.json",
            json.dumps(
                {"schema_version": 1, "report_id": "m", "decision_scope": "exploratory",
                 "artifacts": [{"file": "x", "sha256": "no-es-hash"}, "basura", {"sha256": "a" * 64}]}
            ).encode("utf-8"),
        )
        estado = exploratory_index_status(self.repo)
        self.assertEqual(estado.index, {})
        self.assertEqual(estado.unreadable_manifests, 3)  # ok4 tiene forma valida (sin artefactos usables)
        self.assertEqual(exploratory_hash_index(self.repo), {})

    def test_manifest_demasiado_grande_se_cuenta(self):
        self._archivo("reports/exploratory/grande/manifest.json", b'{"schema_version": 1, ' + b" " * 100 + b"}")
        with mock.patch.object(evidence, "_MAX_MANIFEST_BYTES", 10):
            estado = exploratory_index_status(self.repo)
        self.assertEqual(estado.unreadable_manifests, 1)

    def test_manifest_denegado_por_guardrails_se_cuenta_sin_leerse(self):
        _escribir_reporte(self.repo, "reports/exploratory/rep-a", _reporte_mini("rep-a"))
        self._guardrails(holdouts=["reports/exploratory/rep-a/**"])
        with mock.patch.object(Path, "read_bytes", side_effect=AssertionError("se leyó un manifest denegado")):
            estado = exploratory_index_status(self.repo)
        self.assertEqual(estado.index, {})
        self.assertEqual(estado.unreadable_manifests, 1)

    def test_sin_root_o_policy_invalida(self):
        self.assertEqual(exploratory_index_status(self.repo), ExploratoryIndex())
        self._archivo(".harmessi/reporting-policy.json", b"{basura")
        _escribir_reporte(self.repo, "reports/exploratory/rep-a", _reporte_mini("rep-a"))
        estado = exploratory_index_status(self.repo)
        self.assertEqual(estado.index, {})
        self.assertIsNotNone(estado.error)
        self.assertEqual(exploratory_hash_index(self.repo), {})
        self.assertIsNotNone(exploratory_index_status(None).error)

    def test_cota_de_directorios(self):
        _escribir_reporte(self.repo, "reports/exploratory/rep-a", _reporte_mini("rep-a"))
        with mock.patch.object(evidence, "MAX_DIRS_SCAN", 1):
            estado = exploratory_index_status(self.repo)
        self.assertTrue(estado.truncated)
        self.assertEqual(estado.index, {})
        self.assertNotEqual(exploratory_hash_index(self.repo), {})

    def test_no_desciende_bajo_un_reporte(self):
        for n in range(1, 6):
            _escribir_reporte(self.repo, f"reports/exploratory/rep-{n}", _reporte_mini(f"rep-{n}"))
        # base + 5 reportes = 6 directorios; sin poda serian 1 + 5*4 = 21
        with mock.patch.object(evidence, "MAX_DIRS_SCAN", 6):
            estado = exploratory_index_status(self.repo)
        self.assertFalse(estado.truncated)
        self.assertEqual({v["report_id"] for v in estado.index.values()}, {f"rep-{n}" for n in range(1, 6)})
        with mock.patch.object(evidence, "MAX_DIRS_SCAN", 5):
            self.assertTrue(exploratory_index_status(self.repo).truncated)

    def test_error_de_recorrido_es_error_del_indice(self):
        (self.repo / "reports" / "exploratory").mkdir(parents=True)

        def falso_walk(top, topdown=True, onerror=None, followlinks=False):
            if onerror is not None:
                onerror(PermissionError(13, "denegado", str(Path(top) / "privado")))
            return iter(())

        with mock.patch.object(evidence.os, "walk", falso_walk):
            estado = exploratory_index_status(self.repo)
        self.assertIsNotNone(estado.error)
        self.assertNotIn(str(self.repo), estado.error)


class TestAislamientoPorHash(_ConRepoTemporal):
    def _reporte_exploratory_y_copia(self):
        _o, artefactos, _m, _e = _escribir_reporte(self.repo, "reports/exploratory/rep-a", _reporte_mini("rep-a"))
        copia = self._archivo("data/interim/copia.csv", artefactos["artifacts/tables/tabla_a.json"])
        return copia, artefactos

    def test_copia_byte_identica_en_model_valid_falla_nombrando_origen(self):
        self._reporte_exploratory_y_copia()
        for scope in ("model_valid", "operational"):
            resultados = check_inputs_hash_isolation(self.repo, scope, ["data/interim/copia.csv"])
            fallos = [r for r in resultados if r.status == "FAIL"]
            self.assertEqual(len(fallos), 1, scope)
            self.assertEqual(fallos[0].code, CODE_ISOLATION_HASH)
            self.assertIn("rep-a", fallos[0].message)
            self.assertIn("reports/exploratory/rep-a/artifacts/tables/tabla_a.json", fallos[0].message)
            self.assertEqual(fallos[0].subject, "data/interim/copia.csv")
            self.assertEqual(fallos[0].kind, "check")

    def test_mismo_input_en_exploratory_no_falla(self):
        self._reporte_exploratory_y_copia()
        resultados = check_inputs_hash_isolation(self.repo, "exploratory", ["data/interim/copia.csv"])
        self.assertEqual([r.status for r in resultados], ["N/A"])
        self.assertTrue(all(r.code == CODE_ISOLATION_HASH for r in resultados))

    def test_no_duplicado_pasa(self):
        self._reporte_exploratory_y_copia()
        self._archivo("data/interim/otro.csv", b"a,b\n1,2\n")
        resultados = check_inputs_hash_isolation(self.repo, "model_valid", ["data/interim/otro.csv"])
        self.assertEqual([r.status for r in resultados], ["PASS"])

    def test_sin_manifests_exploratory_pasa_con_aviso_de_limite(self):
        self._archivo("data/interim/otro.csv", b"x\n")
        resultados = check_inputs_hash_isolation(self.repo, "model_valid", ["data/interim/otro.csv"])
        self.assertEqual([r.status for r in resultados], ["PASS"])
        self.assertIn("0 artefacto", resultados[0].message)

    def test_manifest_exploratory_corrupto_agrega_warn_y_no_pasa(self):
        self._reporte_exploratory_y_copia()
        self._archivo("reports/exploratory/malo/manifest.json", b"{no json")
        self._archivo("data/interim/otro.csv", b"x\n")
        resultados = check_inputs_hash_isolation(self.repo, "model_valid", ["data/interim/otro.csv"])
        self.assertEqual([r.status for r in resultados], ["WARN"])
        self.assertEqual(resultados[0].code, CODE_ISOLATION_HASH)
        # el WARN no oculta el FAIL de la copia
        resultados = check_inputs_hash_isolation(self.repo, "model_valid", ["data/interim/copia.csv"])
        self.assertEqual(sorted(r.status for r in resultados), ["FAIL", "WARN"])

    def test_index_precalculado_se_reutiliza(self):
        self._reporte_exploratory_y_copia()
        estado = exploratory_index_status(self.repo)
        with mock.patch.object(evidence, "exploratory_index_status", side_effect=AssertionError("reindexó")):
            resultados = check_inputs_hash_isolation(
                self.repo, "model_valid", ["data/interim/copia.csv"], index=estado
            )
        self.assertEqual([r.status for r in resultados], ["FAIL"])
        # un indice vacio pasado explicitamente manda sobre el disco
        resultados = check_inputs_hash_isolation(
            self.repo, "model_valid", ["data/interim/copia.csv"], index=ExploratoryIndex()
        )
        self.assertEqual([r.status for r in resultados], ["PASS"])
        # un indice con error se propaga fail-closed
        resultados = check_inputs_hash_isolation(
            self.repo, "model_valid", ["data/interim/copia.csv"], index=ExploratoryIndex(error="x")
        )
        self.assertEqual([(r.status, r.kind) for r in resultados], [("FAIL", "technical_error")])

    def test_directorio_input_hashea_cada_archivo(self):
        _c, artefactos = self._reporte_exploratory_y_copia()
        self._archivo("data/lote/uno.csv", b"1\n")
        self._archivo("data/lote/sub/dos.json", artefactos["artifacts/tables/tabla_a.json"])
        resultados = check_inputs_hash_isolation(self.repo, "model_valid", ["data/lote"])
        fallos = [r for r in resultados if r.status == "FAIL"]
        self.assertEqual([f.subject for f in fallos], ["data/lote/sub/dos.json"])

    def test_subdirectorio_ilegible_es_fail_closed(self):
        self._archivo("data/lote/uno.csv", b"1\n")

        def falso_walk(top, topdown=True, onerror=None, followlinks=False):
            if onerror is not None:
                onerror(PermissionError(13, "denegado", str(Path(top) / "privado")))
            return iter(())

        with mock.patch.object(evidence.os, "walk", falso_walk):
            resultados = check_inputs_hash_isolation(
                self.repo, "model_valid", ["data/lote"], index=ExploratoryIndex()
            )
        self.assertEqual([(r.status, r.kind) for r in resultados], [("FAIL", "technical_error")])
        self.assertEqual(resultados[0].subject, "data/lote/privado")
        self.assertFalse(any(r.status == "PASS" for r in resultados))

    def test_ruta_absoluta_y_path(self):
        copia, _ = self._reporte_exploratory_y_copia()
        resultados = check_inputs_hash_isolation(self.repo, "model_valid", [copia])
        self.assertEqual([r.status for r in resultados], ["FAIL"])
        resultados = check_inputs_hash_isolation(self.repo, "model_valid", "data/interim/copia.csv")
        self.assertEqual([r.status for r in resultados], ["FAIL"])

    def test_input_inexistente_es_fail_technical_error(self):
        resultados = check_inputs_hash_isolation(self.repo, "model_valid", ["data/no_existe.csv"])
        self.assertEqual([(r.status, r.kind) for r in resultados], [("FAIL", "technical_error")])

    def test_cota_de_archivos_fail_closed(self):
        self._archivo("data/lote/a.csv", b"1\n")
        self._archivo("data/lote/b.csv", b"2\n")
        with mock.patch.object(evidence, "MAX_FILES_HASH", 1):
            resultados = check_inputs_hash_isolation(self.repo, "model_valid", ["data/lote"])
        self.assertTrue(any(r.status == "FAIL" and r.kind == "technical_error" for r in resultados))
        self.assertFalse(any(r.status == "PASS" for r in resultados))

    def test_indice_truncado_es_fail_closed(self):
        self._reporte_exploratory_y_copia()
        self._archivo("data/interim/otro.csv", b"x\n")
        with mock.patch.object(evidence, "MAX_DIRS_SCAN", 1):
            resultados = check_inputs_hash_isolation(self.repo, "model_valid", ["data/interim/otro.csv"])
        self.assertTrue(any(r.status == "FAIL" and r.kind == "technical_error" for r in resultados))
        self.assertFalse(any(r.status == "PASS" for r in resultados))

    def test_policy_invalida_es_fail_closed(self):
        self._archivo(".harmessi/reporting-policy.json", b"{basura")
        self._archivo("data/x.csv", b"x\n")
        resultados = check_inputs_hash_isolation(self.repo, "model_valid", ["data/x.csv"])
        self.assertEqual([(r.status, r.kind) for r in resultados], [("FAIL", "technical_error")])

    def test_vacio_y_scope_invalido(self):
        self.assertEqual([r.status for r in check_inputs_hash_isolation(self.repo, "model_valid", [])], ["N/A"])
        resultados = check_inputs_hash_isolation(self.repo, "otro", ["x"])
        self.assertEqual([r.status for r in resultados], ["FAIL"])

    def test_nunca_lanza_con_basura(self):
        casos = [
            (None, "model_valid", ["x"]),
            (self.repo, None, ["x"]),
            (self.repo, "model_valid", None),
            (self.repo, "model_valid", 5),
            (self.repo, "model_valid", [None, 3, "", "a\x00b"]),
            (5, "operational", ["x"]),
            (self.repo, ["model_valid"], ["x"]),
        ]
        for caso in casos:
            resultados = check_inputs_hash_isolation(*caso)
            self.assertIsInstance(resultados, list, repr(caso))
            self.assertTrue(resultados, repr(caso))
            self.assertTrue(all(r.code == CODE_ISOLATION_HASH for r in resultados), repr(caso))
            self.assertFalse(any(r.status == "PASS" for r in resultados), repr(caso))
        resultados = check_inputs_hash_isolation(self.repo, "model_valid", ["x"], index="basura")
        self.assertTrue(resultados)


class TestRestriccionesDeImports(unittest.TestCase):
    def test_imports_permitidos(self):
        fuente = Path(evidence.__file__).read_text(encoding="utf-8")
        arbol = ast.parse(fuente)
        stdlib = getattr(sys, "stdlib_module_names", None)
        prohibidos = {"pandas", "numpy", "plotly", "requests", "urllib", "http", "socket", "jinja2", "yaml", "scipy"}
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Import):
                for alias in nodo.names:
                    raiz = alias.name.split(".")[0]
                    self.assertNotIn(raiz, prohibidos, alias.name)
                    self.assertNotIn(raiz, ("ds_profile", "validation", "profiles"), alias.name)
                    if stdlib is not None:
                        self.assertIn(raiz, stdlib, alias.name)
            elif isinstance(nodo, ast.ImportFrom):
                nombres = {a.name for a in nodo.names}
                if nodo.level:
                    self.assertIsNone(nodo.module, "import relativo con submodulo")
                    self.assertTrue(nombres <= {"core", "governance"}, nombres)
                    continue
                raiz = (nodo.module or "").split(".")[0]
                self.assertNotIn(raiz, prohibidos, nodo.module)
                if raiz == "ds_profile":
                    # SOLO el modulo fingerprint
                    self.assertTrue(
                        (nodo.module == "ds_profile" and nombres == {"fingerprint"})
                        or nodo.module == "ds_profile.fingerprint",
                        (nodo.module, nombres),
                    )
                elif raiz == "dsguard":
                    pass
                elif raiz == "tools":
                    self.fail("evidence.py no debe importar via el paquete tools")
                elif stdlib is not None:
                    self.assertIn(raiz, stdlib, nodo.module)
        importados = {
            n.module for n in ast.walk(arbol) if isinstance(n, ast.ImportFrom) and not n.level and n.module
        }
        self.assertIn("ds_profile", importados)


if __name__ == "__main__":
    unittest.main()

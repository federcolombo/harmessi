"""Tests de `tools/reporting/publish.py` (v0.6 Change 4, tanda D1).

Deterministas: sin red, sin pandas, SIN plotly real (bundle FALSO). Repos
temporales y fixtures 100% genericos (datos sinteticos).
"""
from __future__ import annotations

import contextlib
import dataclasses
import hashlib
import html as html_lib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.reporting import evidence, governance, publish, render_html, validation
from tools.reporting.core import Chapter, FigureArtifact, FigureSpec, Insight, Report, TableArtifact
from tools.reporting.evidence import describe_generated_source, expected_artifacts
from tools.reporting.examples.eda_generic import build_example_report
from tools.reporting.publish import PublishResult, publish as publicar
from tools.reporting.validation import validate_report_dir

RUN_ID = "run-20260101T000000Z-abc123"
RELOJ = lambda: "2026-01-01T00:00:00Z"  # noqa: E731
BUNDLE_FALSO = "/*BUNDLE_PLOTLY_FALSO_XYZ*/window.Plotly={newPlot:function(){}};"
MARCA_SECRETA = "SECRETO_ALFA_123"
GUARDRAILS = {"holdouts": ["data/sellado/**"]}
_DEFECTO = object()  # centinela: "no pasado" (None se envía de verdad a publish)


# --- Fixtures -----------------------------------------------------------------


def _tabla(**kw) -> TableArtifact:
    base = dict(table_id="tabla_a", title="Tabla A", columns=("k", "v"), rows=(("a", 1), ("b", 2)))
    base.update(kw)
    return TableArtifact(**base)


def _figura(**kw) -> FigureArtifact:
    base = dict(
        figure_id="fig_a",
        title="Figura A",
        spec=FigureSpec(chart_type="bar", x="k", y=("v",)),
        backing_table_id="tabla_a",
    )
    base.update(kw)
    return FigureArtifact(**base)


def _insight(**kw) -> Insight:
    base = dict(
        insight_id="ins_a",
        technical_claim="tc",
        business_claim="bc",
        evidence_refs=("tabla_a",),
        population="p",
        time_scope="t",
        claim_type="descriptive",
    )
    base.update(kw)
    return Insight(**base)


def _reporte(report_id="rep-a", scope="exploratory", tablas=None, figuras=None, insights=None) -> Report:
    tablas = [_tabla()] if tablas is None else tablas
    figuras = [_figura()] if figuras is None else figuras
    insights = [_insight()] if insights is None else insights
    capitulo = Chapter(
        chapter_id="cap_a", title="Cap", tables=tuple(tablas), figures=tuple(figuras), insights=tuple(insights)
    )
    return Report(report_id=report_id, title="R", report_kind="model", decision_scope=scope, chapters=(capitulo,))


def _fuente_manual(path: str, contenido: bytes) -> dict:
    return {
        "kind": "file",
        "role": "input",
        "path": path,
        "sha256": hashlib.sha256(contenido).hexdigest(),
        "algorithm": "sha256/bin/v1",
        "size_bytes": len(contenido),
    }


def _pass(code: str) -> publish.checks.CheckResult:
    return publish.checks.CheckResult(status="PASS", code=code, message="ok")


def _fail(code: str) -> publish.checks.CheckResult:
    return publish.checks.CheckResult(status="FAIL", code=code, message="falla simulada")


def _gov_ok() -> list:
    return [_pass(c) for c in governance.REQUIRED_DESTINATION_CODES]


def _fails(resultados) -> list:
    return [r for r in resultados if r.status == "FAIL"]


def _por_codigo(resultados, codigo) -> list:
    return [r for r in resultados if r.code == codigo]


class _ConRepo(unittest.TestCase):
    def setUp(self):
        self.repo = self._nuevo_repo()

    def _nuevo_repo(self) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        repo = Path(tmp.name).resolve()
        (repo / ".claude").mkdir()
        (repo / ".claude" / "guardrails.json").write_bytes(json.dumps(GUARDRAILS).encode("utf-8"))
        return repo

    def _archivo(self, rel: str, contenido: bytes) -> Path:
        ruta = self.repo.joinpath(*rel.split("/"))
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_bytes(contenido)
        return ruta

    def _snapshot(self, repo=None) -> dict:
        repo = repo or self.repo
        return {p.relative_to(repo).as_posix(): p.read_bytes() for p in sorted(repo.rglob("*")) if p.is_file()}

    def _publicar(self, report=_DEFECTO, repo=_DEFECTO, **kw) -> PublishResult:
        kwargs = dict(
            run_id=RUN_ID,
            sources=[describe_generated_source("datos sinteticos", {"semilla": 1})],
            holdout_access="none",
            clock=RELOJ,
            plotly_bundle=BUNDLE_FALSO,
        )
        kwargs.update(kw)
        report = build_example_report() if report is _DEFECTO else report
        repo = self.repo if repo is _DEFECTO else repo
        return publicar(report, repo, **kwargs)

    def assert_nada_escrito(self, antes, resultado):
        self.assertEqual(antes, self._snapshot())
        self.assertFalse(resultado.written)
        self.assertFalse(resultado.html_written)
        self.assertFalse((self.repo / "reports").exists())

    def assert_sin_excepciones(self, resultado):
        self.assertEqual([], [r.code for r in resultado.results if r.code.endswith("-EXCEPCION")])

    def assert_sin_rutas_locales(self, resultado):
        for r in resultado.results:
            for texto in (r.message, r.detail, r.subject):
                if texto:
                    self.assertNotIn(str(self.repo), texto)
                    self.assertNotIn(self.repo.as_posix(), texto)


# --- Caso feliz ---------------------------------------------------------------


class TestPublishFeliz(_ConRepo):
    def test_reporte_valido_escribe_todo_y_valida(self):
        report = build_example_report()
        res = self._publicar(report)
        self.assertIsInstance(res, PublishResult)
        self.assertEqual([], [r.to_dict() for r in _fails(res.results)])
        self.assert_sin_excepciones(res)
        self.assertTrue(res.written)
        self.assertTrue(res.html_written)
        self.assertTrue(res.plotly_bundle_used)
        self.assertEqual(f"reports/exploratory/{report.report_id}", res.out_dir)
        out = self.repo / "reports" / "exploratory" / report.report_id
        self.assertTrue((out / "manifest.json").is_file())
        self.assertTrue((out / "insights.json").is_file())
        self.assertTrue((out / "artifacts").is_dir())
        self.assertTrue((out / "report.html").is_file())
        for rel in expected_artifacts(report):
            self.assertTrue((out / rel).is_file(), rel)
        self.assertEqual([], _fails(validate_report_dir(self.repo, res.out_dir)))
        self.assertEqual([], _por_codigo(res.results, "REPORT-RENDER-PLOTLY-UNAVAILABLE"))

    def test_html_tiene_titulo_y_bundle_falso_una_vez(self):
        report = build_example_report()
        res = self._publicar(report)
        html = (self.repo / res.out_dir / "report.html").read_text(encoding="utf-8")
        self.assertIn(html_lib.escape(report.title), html)
        self.assertEqual(1, html.count(BUNDLE_FALSO))

    def test_report_html_no_entra_al_manifest(self):
        res = self._publicar()
        manifest = json.loads((self.repo / res.out_dir / "manifest.json").read_text(encoding="utf-8"))
        archivos = [a["file"] for a in manifest["artifacts"]]
        self.assertNotIn("report.html", archivos)
        self.assertNotIn("manifest.json", archivos)
        self.assertEqual(sorted(expected_artifacts(build_example_report())), sorted(archivos))

    def test_html_se_escribe_atomico_y_ultimo(self):
        original = publish.dsguard_core.escribir_texto_atomico
        with mock.patch.object(publish.dsguard_core, "escribir_texto_atomico", side_effect=original) as espia:
            res = self._publicar()
        self.assertTrue(res.html_written)
        nombres = [Path(c.args[0]).name for c in espia.call_args_list]
        self.assertEqual("report.html", nombres[-1])
        self.assertEqual(1, nombres.count("report.html"))
        self.assertEqual("manifest.json", nombres[-2])  # manifest ultimo entre los del directorio

    def test_render_usa_el_report_verificado_en_memoria(self):
        capturado = {}
        original = evidence.report_from_bytes

        def rfb(files, manifest):
            capturado["report"] = original(files, manifest)
            return capturado["report"]

        with mock.patch.object(publish.evidence, "report_from_bytes", side_effect=rfb), mock.patch.object(
            publish.evidence, "load_report_dir", side_effect=AssertionError("no se relee de disco")
        ), mock.patch.object(
            publish.render_html, "render_report_html", wraps=render_html.render_report_html
        ) as render:
            res = self._publicar()
        self.assertTrue(res.html_written)
        render.assert_called_once()
        self.assertIs(render.call_args.args[0], capturado["report"])
        self.assertEqual(build_example_report().content_sha256(), capturado["report"].content_sha256())

    def test_scientific_policy_se_lee_una_vez_y_se_pasa_a_validate_report(self):
        original = validation.validate_report
        with mock.patch.object(publish.validation, "validate_report", side_effect=original) as espia:
            self._publicar()
        espia.assert_called_once()
        self.assertIsInstance(espia.call_args.kwargs.get("scientific_policy"), dict)

    def test_resultado_es_frozen(self):
        res = self._publicar()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            res.written = False


class TestPublishDeterminismo(_ConRepo):
    def test_dos_repos_identicos_dan_manifest_y_html_identicos(self):
        otro = self._nuevo_repo()
        res_a = self._publicar()
        res_b = self._publicar(repo=otro)
        self.assertEqual(res_a.out_dir, res_b.out_dir)
        for nombre in ("manifest.json", "report.html", "insights.json"):
            a = (self.repo / res_a.out_dir / nombre).read_bytes()
            b = (otro / res_b.out_dir / nombre).read_bytes()
            self.assertEqual(a, b, nombre)
        self.assertEqual(self._snapshot(self.repo), self._snapshot(otro))


# --- Rechazos: nada escrito ---------------------------------------------------


class TestPublishRechazos(_ConRepo):
    def test_destino_cruzado_de_scope_no_escribe(self):
        antes = self._snapshot()
        res = self._publicar(out_dir="reports/model_valid/eda-x")
        self.assertTrue(_por_codigo(res.results, "REPORT-DEST-CROSS-SCOPE"))
        self.assertEqual(["FAIL"], sorted({r.status for r in _por_codigo(res.results, "REPORT-DEST-CROSS-SCOPE")}))
        self.assert_nada_escrito(antes, res)
        self.assert_sin_excepciones(res)
        self.assert_sin_rutas_locales(res)

    def test_figura_sin_tabla_no_escribe(self):
        antes = self._snapshot()
        res = self._publicar(_reporte(figuras=[_figura(backing_table_id=None)]))
        self.assertEqual(["FAIL"], [r.status for r in _por_codigo(res.results, "REPORT-FIGURE-NO-TABLE")])
        self.assert_nada_escrito(antes, res)
        self.assertEqual("reports/exploratory/rep-a", res.out_dir)

    def test_manifest_invalido_no_escribe(self):
        antes = self._snapshot()
        falla = [_fail("REPORT-MANIFEST-SCHEMA")]
        with mock.patch.object(publish.validation, "validate_manifest", return_value=falla) as espia:
            res = self._publicar(_reporte())
        espia.assert_called_once()
        self.assertTrue(_por_codigo(res.results, "REPORT-MANIFEST-SCHEMA"))
        self.assert_nada_escrito(antes, res)

    def test_fuente_malformada_no_escribe(self):
        antes = self._snapshot()
        res = self._publicar(_reporte(), sources=[{"kind": "file"}])
        self.assertTrue(_fails(res.results))
        self.assert_nada_escrito(antes, res)
        self.assert_sin_excepciones(res)

    def test_fuente_en_holdout_no_escribe_ni_se_abre(self):
        contenido = b"secreto\n"
        self._archivo("data/sellado/h.csv", contenido)
        antes = self._snapshot()
        original = Path.read_bytes

        def espia_lectura(ruta, *a, **k):
            if ruta.name == "h.csv":
                raise AssertionError("se abrió h.csv")
            return original(ruta, *a, **k)

        with mock.patch.object(Path, "read_bytes", espia_lectura), mock.patch.object(
            publish.evidence._fingerprint, "calcular_fingerprint", side_effect=AssertionError("hash")
        ) as huella, mock.patch.object(
            publish.evidence, "describe_source", side_effect=AssertionError("describe_source")
        ) as descr:
            res = self._publicar(_reporte(), sources=[_fuente_manual("data/sellado/h.csv", contenido)])
        huella.assert_not_called()
        descr.assert_not_called()
        self.assertTrue(_fails(res.results))
        self.assert_sin_excepciones(res)
        self.assert_nada_escrito(antes, res)

    def test_toctou_segunda_evaluacion_de_destino_falla(self):
        antes = self._snapshot()
        cruzado = [_fail("REPORT-DEST-CROSS-SCOPE")]
        with mock.patch.object(publish.governance, "evaluate_destination", return_value=cruzado) as espia:
            res = self._publicar(_reporte())
        espia.assert_called_once()  # la reevaluacion ocurre una vez, antes de escribir
        self.assertTrue(_por_codigo(res.results, "REPORT-DEST-CROSS-SCOPE"))
        self.assertTrue(_por_codigo(res.results, "REPORT-PUBLISH-DEST"))
        self.assert_nada_escrito(antes, res)

    def test_toctou_reevaluacion_vacia_no_habilita_escribir(self):
        antes = self._snapshot()
        with mock.patch.object(publish.governance, "evaluate_destination", return_value=[]):
            res = self._publicar(_reporte())
        self.assertTrue(_fails(res.results))
        self.assert_nada_escrito(antes, res)

    def test_governance_vacio_no_habilita_escribir(self):
        antes = self._snapshot()
        with mock.patch.object(publish.governance, "evaluate_governance", return_value=[]):
            res = self._publicar(_reporte())
        self.assertTrue(_por_codigo(res.results, "REPORT-PUBLISH-GOVERNANCE"))
        self.assert_nada_escrito(antes, res)

    def test_governance_sin_codigos_requeridos_no_habilita_escribir(self):
        antes = self._snapshot()
        parcial = [_pass(governance.CODE_POLICY)]  # faltan DEST-SAFE y DEST-SCOPE
        with mock.patch.object(publish.governance, "evaluate_governance", return_value=parcial):
            res = self._publicar(_reporte())
        self.assertTrue(_fails(res.results))
        self.assert_nada_escrito(antes, res)

    def test_fail_de_governance_no_escribe(self):
        antes = self._snapshot()
        with mock.patch.object(publish.governance, "evaluate_governance", return_value=_gov_ok() + [_fail("REPORT-HOLDOUT-SOURCE")]):
            res = self._publicar(_reporte())
        self.assert_nada_escrito(antes, res)

    def test_style_invalido_no_escribe(self):
        self._archivo(".harmessi/report-style.json", b"{corrupto")
        antes = self._snapshot()
        res = self._publicar(_reporte())
        fallas = _por_codigo(res.results, "REPORT-STYLE-INVALID")
        self.assertEqual([("FAIL", "technical_error")], [(r.status, r.kind) for r in fallas])
        self.assert_nada_escrito(antes, res)
        self.assert_sin_rutas_locales(res)

    def test_style_que_no_es_style_no_escribe(self):
        antes = self._snapshot()
        res = self._publicar(_reporte(), style="oscuro")
        self.assertTrue(_por_codigo(res.results, "REPORT-STYLE-INVALID"))
        self.assert_nada_escrito(antes, res)

    def test_policy_cientifica_corrupta_no_escribe(self):
        self._archivo(".harmessi/scientific-policy.json", b"{corrupto")
        antes = self._snapshot()
        res = self._publicar(_reporte())
        fallas = _por_codigo(res.results, validation.CODE_SCI_POLICY)
        self.assertEqual([("FAIL", "technical_error")], [(r.status, r.kind) for r in fallas])
        self.assert_nada_escrito(antes, res)
        self.assert_sin_rutas_locales(res)


class TestPublishFallasPosteriores(_ConRepo):
    def test_falla_de_escritura_es_fail_sin_lanzar(self):
        with mock.patch.object(publish.evidence, "write_report_dir", side_effect=OSError("disco lleno")):
            res = self._publicar(_reporte())
        self.assertTrue(res.written)  # el intento empezo: refleja lo real
        self.assertFalse(res.html_written)
        self.assertTrue(_por_codigo(res.results, "REPORT-PUBLISH-WRITE"))
        self.assert_sin_rutas_locales(res)

    def test_relectura_fallida_no_escribe_html(self):
        with mock.patch.object(publish.validation, "validate_report_dir", return_value=[_fail("REPORT-ARTIFACT-HASH")]):
            res = self._publicar(_reporte())
        self.assertTrue(res.written)
        self.assertFalse(res.html_written)
        self.assertFalse((self.repo / res.out_dir / "report.html").exists())

    def test_render_que_falla_no_escribe_html_ni_lanza(self):
        with mock.patch.object(publish.render_html, "render_report_html", side_effect=ValueError("x")):
            res = self._publicar(_reporte())
        self.assertTrue(res.written)
        self.assertFalse(res.html_written)
        self.assertTrue(_por_codigo(res.results, "REPORT-PUBLISH-RENDER"))


# --- Bundle de plotly ---------------------------------------------------------


class TestPublishBundle(_ConRepo):
    def test_sin_bundle_escribe_con_aviso_y_warn(self):
        res = self._publicar(plotly_bundle=None)
        self.assertEqual([], _fails(res.results))
        self.assertTrue(res.written)
        self.assertTrue(res.html_written)
        self.assertFalse(res.plotly_bundle_used)
        avisos = _por_codigo(res.results, "REPORT-RENDER-PLOTLY-UNAVAILABLE")
        self.assertEqual(["WARN"], [r.status for r in avisos])
        html = (self.repo / res.out_dir / "report.html").read_text(encoding="utf-8")
        self.assertNotIn("BUNDLE_PLOTLY_FALSO_XYZ", html)

    def test_bundle_automatico_no_encontrado_da_warn(self):
        with mock.patch.object(publish.plotly_backend, "find_plotly_bundle", return_value=None) as buscar:
            res = self._publicar(plotly_bundle=publish._AUTO)
        buscar.assert_called_once()
        self.assertTrue(res.html_written)
        self.assertFalse(res.plotly_bundle_used)
        self.assertTrue(_por_codigo(res.results, "REPORT-RENDER-PLOTLY-UNAVAILABLE"))

    def test_bundle_automatico_encontrado_se_embebe(self):
        with mock.patch.object(publish.plotly_backend, "find_plotly_bundle", return_value=BUNDLE_FALSO) as buscar:
            res = self._publicar(plotly_bundle=publish._AUTO)
        buscar.assert_called_once()
        self.assertTrue(res.plotly_bundle_used)
        self.assertEqual([], _por_codigo(res.results, "REPORT-RENDER-PLOTLY-UNAVAILABLE"))
        html = (self.repo / res.out_dir / "report.html").read_text(encoding="utf-8")
        self.assertEqual(1, html.count(BUNDLE_FALSO))


# --- Policy cientifica temporal ------------------------------------------------


class TestPublishPolicyTemporal(_ConRepo):
    def test_model_valid_y_operational_sin_policy_temporal_dan_warn(self):
        for scope in ("model_valid", "operational"):
            with self.subTest(scope):
                report = dataclasses.replace(build_example_report(), decision_scope=scope)
                res = self._publicar(report)
                avisos = _por_codigo(res.results, "REPORT-PUBLISH-NO-SCIENTIFIC-POLICY")
                self.assertEqual(["WARN"], [r.status for r in avisos])
                self.assert_sin_excepciones(res)

    def test_exploratory_no_emite_el_warn(self):
        res = self._publicar()
        self.assertEqual([], _por_codigo(res.results, "REPORT-PUBLISH-NO-SCIENTIFIC-POLICY"))

    def test_policy_temporal_declarada_no_emite_el_warn(self):
        politica = {"schema_version": 1, "temporal": {"declared": True, "date_column": "fecha"}}
        self._archivo(".harmessi/scientific-policy.json", json.dumps(politica).encode("utf-8"))
        report = dataclasses.replace(build_example_report(), decision_scope="model_valid")
        res = self._publicar(report)
        self.assertEqual([], _por_codigo(res.results, "REPORT-PUBLISH-NO-SCIENTIFIC-POLICY"))
        self.assert_sin_excepciones(res)


# --- Sensibles ----------------------------------------------------------------


class TestPublishSensibles(_ConRepo):
    @contextlib.contextmanager
    def _governance_permisiva(self):
        # El destino sensible depende de la policy de reporting; aqui se prueba el RENDER.
        with mock.patch.object(publish.governance, "evaluate_governance", return_value=_gov_ok()), mock.patch.object(
            publish.governance, "evaluate_destination", return_value=_gov_ok()
        ), mock.patch.object(publish.validation, "validate_report_dir", return_value=[_pass("REPORT-DIR")]):
            yield

    def _reporte_con_sensible(self) -> Report:
        sensible = _tabla(table_id="tabla_s", title="Tabla S", rows=((MARCA_SECRETA, 1),), sensitive=True)
        return _reporte(tablas=[_tabla(), sensible])

    def test_sensibles_omitidos_del_html_por_defecto(self):
        with self._governance_permisiva():
            res = self._publicar(self._reporte_con_sensible())
        self.assertEqual([], _fails(res.results), [r.to_dict() for r in _fails(res.results)])
        self.assertTrue(res.html_written)
        html = (self.repo / res.out_dir / "report.html").read_text(encoding="utf-8")
        self.assertNotIn(MARCA_SECRETA, html)
        # el JSON persistido (destino sensible) si conserva el dato
        tabla_json = (self.repo / res.out_dir / "artifacts" / "tables" / "tabla_s.json").read_text(encoding="utf-8")
        self.assertIn(MARCA_SECRETA, tabla_json)

    def test_include_sensitive_explicito_los_incluye_y_deja_marca(self):
        with self._governance_permisiva():
            res = self._publicar(self._reporte_con_sensible(), include_sensitive=True)
        html = (self.repo / res.out_dir / "report.html").read_text(encoding="utf-8")
        self.assertIn(MARCA_SECRETA, html)
        marcas = _por_codigo(res.results, "REPORT-PUBLISH-INCLUDE-SENSITIVE")
        self.assertEqual(["WARN"], [r.status for r in marcas])

    def test_sin_include_sensitive_no_hay_marca(self):
        with self._governance_permisiva():
            res = self._publicar(self._reporte_con_sensible())
        self.assertEqual([], _por_codigo(res.results, "REPORT-PUBLISH-INCLUDE-SENSITIVE"))


class TestPublishRepublicacion(_ConRepo):
    def test_republicacion_con_render_fallido_no_deja_html_viejo(self):
        report = build_example_report()
        primera = self._publicar(report)
        self.assertTrue(primera.html_written)
        html_viejo = self.repo / primera.out_dir / "report.html"
        self.assertTrue(html_viejo.is_file())
        with mock.patch.object(publish.render_html, "render_report_html", side_effect=ValueError("x")):
            segunda = self._publicar(report, run_id="run-20260102T000000Z-def456")
        self.assertTrue(segunda.written)
        self.assertFalse(segunda.html_written)
        self.assertFalse(html_viejo.exists())  # no queda un derivado desincronizado
        manifest = json.loads((self.repo / segunda.out_dir / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual("run-20260102T000000Z-def456", manifest["run_id"])

    def test_no_se_elimina_el_html_previo_si_un_chequeo_previo_falla(self):
        report = build_example_report()
        primera = self._publicar(report)
        html_viejo = self.repo / primera.out_dir / "report.html"
        contenido = html_viejo.read_bytes()
        with mock.patch.object(publish.governance, "evaluate_destination", return_value=[_fail("REPORT-DEST-SAFE")]):
            segunda = self._publicar(report, run_id="run-20260102T000000Z-def456")
        self.assertFalse(segunda.written)
        self.assertEqual(contenido, html_viejo.read_bytes())

    def test_si_no_se_puede_eliminar_el_html_previo_no_se_escribe(self):
        report = build_example_report()
        primera = self._publicar(report)
        manifest_antes = (self.repo / primera.out_dir / "manifest.json").read_bytes()
        with mock.patch.object(Path, "unlink", side_effect=PermissionError("bloqueado")):
            segunda = self._publicar(report, run_id="run-20260102T000000Z-def456")
        self.assertFalse(segunda.written)
        self.assertFalse(segunda.html_written)
        self.assertTrue(_por_codigo(segunda.results, "REPORT-PUBLISH-WRITE"))
        self.assertEqual(manifest_antes, (self.repo / primera.out_dir / "manifest.json").read_bytes())
        self.assert_sin_rutas_locales(segunda)


class TestPublishResultadosUnicos(_ConRepo):
    def test_results_sin_duplicados(self):
        res = self._publicar()
        claves = [(r.status, r.code, r.subject, r.message) for r in res.results]
        self.assertEqual(len(claves), len(set(claves)))

    def test_codigos_de_validacion_aparecen_una_vez(self):
        res = self._publicar()
        # REPORT-PROVENANCE se emite legitimamente una vez POR subject (git_commit, harmessi_version)
        sujetos = sorted(r.subject for r in _por_codigo(res.results, "REPORT-PROVENANCE"))
        self.assertEqual(["git_commit", "harmessi_version"], sujetos)
        for codigo in ("REPORT-PROVENANCE", "EDA-EXPLORATORY-TARGET-USE"):
            claves = [(r.status, r.code, r.subject, r.message) for r in _por_codigo(res.results, codigo)]
            self.assertEqual(len(claves), len(set(claves)), codigo)

    def test_sin_duplicados_preserva_el_orden(self):
        a, b, c = _pass("A"), _pass("B"), _pass("C")
        self.assertEqual([a, b, c], publish._sin_duplicados([a, b, a, c, b]))


# --- Nunca lanza --------------------------------------------------------------


class TestPublishNuncaLanza(_ConRepo):
    def test_inputs_raros_no_lanzan_ni_escriben(self):
        buen = build_example_report()
        casos = [
            (None, self.repo, {}),
            ("no-es-un-reporte", self.repo, {}),
            (buen, None, {}),
            (buen, self.repo / "no_existe", {}),
            (buen, self.repo, dict(sources=None)),
            (buen, self.repo, dict(out_dir=123)),
            (buen, self.repo, dict(out_dir="")),
            (buen, self.repo, dict(out_dir="../fuera")),
            (buen, self.repo, dict(holdout_access=object())),
            (buen, self.repo, dict(exclusions=5)),
            (buen, self.repo, dict(clock=lambda: 1 / 0)),
        ]
        for report, repo, kw in casos:
            with self.subTest(kw=list(kw), repo=str(repo)[-12:]):
                antes = self._snapshot()
                res = self._publicar(report, repo=repo, **kw)
                self.assertIsInstance(res, PublishResult)
                self.assertTrue(_fails(res.results))
                self.assertFalse(res.html_written)
                self.assertEqual(antes, self._snapshot())

    def test_run_id_raro_no_lanza(self):
        for run_id in (None, 5, ""):
            with self.subTest(run_id=run_id):
                res = self._publicar(_reporte(), run_id=run_id)
                self.assertIsInstance(res, PublishResult)

    def test_excepcion_interna_es_fail_sin_rutas_locales(self):
        res = self._publicar(clock=lambda: 1 / 0)
        fallas = _por_codigo(res.results, "REPORT-PUBLISH-EXCEPCION")
        self.assertEqual([("FAIL", "technical_error")], [(r.status, r.kind) for r in fallas])
        self.assertIn("ZeroDivisionError", fallas[0].message)
        self.assert_sin_rutas_locales(res)
        self.assertFalse(res.written)


if __name__ == "__main__":
    unittest.main()

"""Tests de `tools/reporting/validation.py` (v0.6 Change 3, tanda B).

Deterministas: sin red, sin pandas. Repos temporales y fixtures 100% genericos
(datos sinteticos). Reporte base: `build_example_report()` persistido con
`evidence` (fuente `describe_generated_source`).
"""
from __future__ import annotations

import ast
import contextlib
import copy
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest import mock

from tools.reporting import validation
from tools.reporting.core import (
    Chapter,
    FigureArtifact,
    FigureSpec,
    Insight,
    Report,
    TableArtifact,
)
from tools.reporting.evidence import (
    build_manifest,
    describe_generated_source,
    describe_source,
    manifest_to_bytes,
    prepare_artifacts,
    write_report_dir,
)
from tools.reporting.examples.eda_generic import build_example_report
from tools.reporting.validation import (
    CODES,
    validate_manifest,
    validate_report,
    validate_report_dir,
)

RUN_ID = "run-20260101T000000Z-abc123"
RELOJ = lambda: "2026-01-01T00:00:00Z"  # noqa: E731
PROV_OK = dict(git_commit="a" * 40, git_dirty=False, harmessi_version="0.6.0")
CODES_REPORT = (
    "REPORT-FIGURE-NO-TABLE",
    "REPORT-FIGURE-DANGLING-TABLE",
    "REPORT-FIGURE-SPEC-COLUMNS",
    "REPORT-FIGURE-TABLE-EMPTY",
    "REPORT-SENSITIVE-FIGURE",
    "REPORT-INSIGHT-CLAIMS",
    "REPORT-INSIGHT-NO-EVIDENCE",
    "REPORT-INSIGHT-DANGLING-REF",
    "REPORT-INSIGHT-UNCERTAINTY",
    "REPORT-INSIGHT-REVIEW-REQUIRED",
)


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


def _reporte(report_id="rep-a", scope="exploratory", kind="model", tablas=None, figuras=None, insights=None) -> Report:
    tablas = [_tabla()] if tablas is None else tablas
    figuras = [_figura()] if figuras is None else figuras
    insights = [_insight()] if insights is None else insights
    capitulo = Chapter(
        chapter_id="cap_a", title="Cap", tables=tuple(tablas), figures=tuple(figuras), insights=tuple(insights)
    )
    return Report(report_id=report_id, title="R", report_kind=kind, decision_scope=scope, chapters=(capitulo,))


def _manifest_valido(report: Report, **extra) -> dict:
    kwargs = dict(
        repo_root=".",
        run_id=RUN_ID,
        artifact_bytes=prepare_artifacts(report),
        sources=[describe_generated_source("datos sinteticos", {"semilla": 1})],
        holdout_access="none",
        clock=RELOJ,
    )
    kwargs.update(PROV_OK)
    kwargs.update(extra)
    return build_manifest(report, **kwargs)


def _por_codigo(resultados, codigo):
    return [r for r in resultados if r.code == codigo]


def _fails(resultados):
    return [r for r in resultados if r.status == "FAIL"]


class _Base(unittest.TestCase):
    def assert_sin_tecnicos(self, resultados):
        malos = [r for r in resultados if r.kind == "technical_error" or r.code.endswith("-EXCEPCION")]
        self.assertEqual([], malos)

    def assert_estado(self, resultados, codigo, status):
        encontrados = _por_codigo(resultados, codigo)
        self.assertTrue(encontrados, f"falta el código {codigo}")
        self.assertIn(status, {r.status for r in encontrados}, [r.to_dict() for r in encontrados])


class _ConRepo(_Base):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo = Path(self._tmp.name).resolve()

    def _archivo(self, rel: str, contenido: bytes) -> Path:
        ruta = self.repo.joinpath(*rel.split("/"))
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_bytes(contenido)
        return ruta

    def _persistir(self, report, *, out_rel=None, sources=None, **extra):
        artefactos = prepare_artifacts(report)
        fuentes = sources if sources is not None else [describe_generated_source("datos sinteticos", {"semilla": 1})]
        kwargs = dict(
            repo_root=self.repo,
            run_id=RUN_ID,
            artifact_bytes=artefactos,
            sources=fuentes,
            holdout_access="none",
            git_commit=None,
            git_dirty=None,
            harmessi_version=None,
            clock=RELOJ,
        )
        kwargs.update(extra)
        manifest = build_manifest(report, **kwargs)
        out = self.repo.joinpath(*(out_rel or f"reports/{report.decision_scope}/{report.report_id}").split("/"))
        write_report_dir(out, artefactos, manifest)
        return out, artefactos, manifest

    def _reescribir_manifest(self, out: Path, manifest: dict):
        (out / "manifest.json").write_bytes(manifest_to_bytes(manifest))

    def _snapshot(self) -> dict:
        return {p.relative_to(self.repo).as_posix(): p.read_bytes() for p in sorted(self.repo.rglob("*")) if p.is_file()}


# --- validate_report ----------------------------------------------------------


class TestValidateReport(_Base):
    def test_reporte_sano_un_pass_por_regla(self):
        res = validate_report(_reporte())
        self.assertEqual(list(CODES_REPORT), [r.code for r in res])
        self.assertEqual({"PASS"}, {r.status for r in res}, [r.to_dict() for r in res])
        self.assert_sin_tecnicos(res)

    def test_figura_sin_tabla_es_fail(self):
        res = validate_report(_reporte(figuras=[_figura(backing_table_id=None)]))
        self.assert_estado(res, "REPORT-FIGURE-NO-TABLE", "FAIL")
        self.assertIn("fig_a", _por_codigo(res, "REPORT-FIGURE-NO-TABLE")[0].message)
        self.assert_estado(res, "REPORT-FIGURE-DANGLING-TABLE", "PASS")

    def test_backing_table_colgante_o_que_es_una_figura(self):
        for destino, figuras in (
            ("inexistente", [_figura(backing_table_id="no_existe")]),
            ("otra figura", [_figura(), _figura(figure_id="fig_b", backing_table_id="fig_a")]),
        ):
            with self.subTest(destino):
                res = validate_report(_reporte(figuras=figuras))
                self.assert_estado(res, "REPORT-FIGURE-DANGLING-TABLE", "FAIL")
                self.assert_estado(res, "REPORT-FIGURE-NO-TABLE", "PASS")

    def test_columnas_del_spec_ausentes_nombra_la_columna(self):
        figura = _figura(spec=FigureSpec(chart_type="bar", x="x_ausente", y=("v",)))
        res = validate_report(_reporte(figuras=[figura]))
        self.assert_estado(res, "REPORT-FIGURE-SPEC-COLUMNS", "FAIL")
        self.assertIn("x_ausente", _por_codigo(res, "REPORT-FIGURE-SPEC-COLUMNS")[0].message)

    def test_tabla_de_respaldo_vacia_es_fail(self):
        res = validate_report(_reporte(tablas=[_tabla(rows=())]))
        self.assert_estado(res, "REPORT-FIGURE-TABLE-EMPTY", "FAIL")

    def test_figura_publica_sobre_tabla_sensible_es_warn_no_fail(self):
        res = validate_report(_reporte(tablas=[_tabla(sensitive=True)]))
        self.assert_estado(res, "REPORT-SENSITIVE-FIGURE", "WARN")
        self.assertEqual([], _fails(res))
        res_ok = validate_report(_reporte(tablas=[_tabla(sensitive=True)], figuras=[_figura(sensitive=True)]))
        self.assert_estado(res_ok, "REPORT-SENSITIVE-FIGURE", "PASS")

    def test_insight_con_claims_vacios(self):
        for campo in ("technical_claim", "business_claim", "population", "time_scope"):
            with self.subTest(campo):
                res = validate_report(_reporte(insights=[_insight(**{campo: "   "})]))
                self.assert_estado(res, "REPORT-INSIGHT-CLAIMS", "FAIL")
                self.assertIn(campo, _por_codigo(res, "REPORT-INSIGHT-CLAIMS")[0].message)

    def test_insight_sin_evidencia_es_fail(self):
        res = validate_report(_reporte(insights=[_insight(evidence_refs=())]))
        self.assert_estado(res, "REPORT-INSIGHT-NO-EVIDENCE", "FAIL")
        self.assert_estado(res, "REPORT-INSIGHT-DANGLING-REF", "PASS")

    def test_ref_colgante_a_inexistente_o_a_insight(self):
        for ref in ("no_existe", "ins_a"):
            with self.subTest(ref):
                res = validate_report(_reporte(insights=[_insight(evidence_refs=(ref,))]))
                self.assert_estado(res, "REPORT-INSIGHT-DANGLING-REF", "FAIL")
                self.assert_estado(res, "REPORT-INSIGHT-NO-EVIDENCE", "PASS")

    def test_ref_a_figura_resuelve(self):
        res = validate_report(_reporte(insights=[_insight(evidence_refs=("fig_a",))]))
        self.assert_estado(res, "REPORT-INSIGHT-DANGLING-REF", "PASS")

    def test_causal_sin_uncertainty_warn_y_revision(self):
        res = validate_report(_reporte(insights=[_insight(claim_type="causal")]))
        self.assert_estado(res, "REPORT-INSIGHT-UNCERTAINTY", "WARN")
        self.assert_estado(res, "REPORT-INSIGHT-REVIEW-REQUIRED", "WARN")
        self.assertEqual([], _fails(res))

    def test_causal_con_evidencia_valida_es_warn_nunca_pass_ni_fail(self):
        for tipo in ("causal", "recommendation"):
            with self.subTest(tipo):
                res = validate_report(_reporte(insights=[_insight(claim_type=tipo, uncertainty="intervalo amplio")]))
                revision = _por_codigo(res, "REPORT-INSIGHT-REVIEW-REQUIRED")
                self.assertEqual(["WARN"], [r.status for r in revision])
                self.assert_estado(res, "REPORT-INSIGHT-UNCERTAINTY", "PASS")
                self.assertEqual([], _fails(res))

    def test_entradas_basura_no_lanzan_y_devuelven_fail_tecnico(self):
        for basura in (None, 42, "x", {}, object(), [_reporte()]):
            with self.subTest(tipo=type(basura).__name__):
                res = validate_report(basura)
                self.assertEqual(["REPORT-INPUT"], [r.code for r in res])
                self.assertEqual(("FAIL", "technical_error"), (res[0].status, res[0].kind))

    def test_excepcion_interna_se_convierte_en_excepcion_code(self):
        with mock.patch.object(validation, "_regla_insight_claims", side_effect=RuntimeError("boom")):
            res = validate_report(_reporte())
        malos = _por_codigo(res, "REPORT-INSIGHT-CLAIMS-EXCEPCION")
        self.assertEqual(1, len(malos))
        self.assertEqual(("FAIL", "technical_error"), (malos[0].status, malos[0].kind))
        # el resto de las reglas siguio corriendo
        self.assert_estado(res, "REPORT-INSIGHT-NO-EVIDENCE", "PASS")

    def test_eda_delega_con_el_mismo_dict(self):
        politica = {"schema_version": 1, "temporal": {"declared": True, "date_column": "fecha"}}
        sentinela = [validation._res("PASS", "REPORT-EDA-SENTINELA", "delegado")]
        reporte = build_example_report()
        with mock.patch.object(validation.eda_profile, "validate_eda_report", return_value=sentinela) as m:
            res = validate_report(reporte, scientific_policy=politica)
        m.assert_called_once()
        self.assertIs(m.call_args.kwargs["scientific_policy"], politica)
        self.assertIn("REPORT-EDA-SENTINELA", [r.code for r in res])

    def test_no_eda_no_delega(self):
        with mock.patch.object(validation.eda_profile, "validate_eda_report") as m:
            validate_report(_reporte(kind="model"))
        m.assert_not_called()

    def test_reporte_eda_real_sin_excepciones(self):
        for politica in (None, {"schema_version": 1, "temporal": {"declared": True, "date_column": "fecha"}}):
            with self.subTest(politica=politica):
                res = validate_report(build_example_report(), scientific_policy=politica)
                self.assert_sin_tecnicos(res)
                self.assertEqual([], _fails(res), [r.to_dict() for r in _fails(res)])


# --- validate_manifest --------------------------------------------------------


class TestValidateManifest(_Base):
    def test_manifest_valido_un_pass_por_regla(self):
        reporte = _reporte()
        res = validate_manifest(_manifest_valido(reporte), reporte)
        self.assertEqual(
            ["REPORT-MANIFEST-SCHEMA", "REPORT-MANIFEST-CONSISTENCY", "REPORT-SOURCES-NONE", "REPORT-PROVENANCE"],
            [r.code for r in res],
        )
        self.assertEqual({"PASS"}, {r.status for r in res}, [r.to_dict() for r in res])

    def test_sin_report_la_consistencia_es_na(self):
        res = validate_manifest(_manifest_valido(_reporte()))
        self.assert_estado(res, "REPORT-MANIFEST-CONSISTENCY", "N/A")
        self.assertEqual([], _fails(res))

    def test_schema_invalido_por_campo(self):
        casos = {
            "schema_version": lambda m: m.__setitem__("schema_version", 2),
            "holdout_access": lambda m: m.__setitem__("holdout_access", "maybe"),
            "generated_at": lambda m: m.__setitem__("generated_at", "ayer"),
            "sha_artefacto": lambda m: m["artifacts"][0].__setitem__("sha256", "xyz"),
            "kind_artefacto": lambda m: m["artifacts"][0].__setitem__("kind", "otro"),
            "kind_fuente": lambda m: m["sources"][0].__setitem__("kind", "otro"),
            "sha_fuente": lambda m: m["sources"][0].__setitem__("sha256", "zz"),
            "hashes_ausente": lambda m: m.pop("hashes"),
            "git_dirty_tipo": lambda m: m.__setitem__("git_dirty", "si"),
            "report_kind": lambda m: m.__setitem__("report_kind", "raro"),
            "file_inseguro": lambda m: m["artifacts"][0].__setitem__("file", "../fuera.json"),
        }
        reporte = _reporte()
        for nombre, mutar in casos.items():
            with self.subTest(nombre):
                manifest = copy.deepcopy(_manifest_valido(reporte))
                mutar(manifest)
                res = validate_manifest(manifest, reporte)
                self.assert_estado(res, "REPORT-MANIFEST-SCHEMA", "FAIL")

    def test_manifest_basura_no_lanza(self):
        for basura in (None, [], "x", 3):
            with self.subTest(tipo=type(basura).__name__):
                res = validate_manifest(basura, _reporte())
                self.assert_estado(res, "REPORT-MANIFEST-SCHEMA", "FAIL")
                self.assert_estado(res, "REPORT-SOURCES-NONE", "FAIL")
                self.assert_sin_tecnicos(res)

    def test_report_basura_en_consistencia_no_lanza(self):
        res = validate_manifest(_manifest_valido(_reporte()), "no-es-un-report")
        self.assert_estado(res, "REPORT-MANIFEST-CONSISTENCY", "FAIL")

    def test_consistencia_con_el_report(self):
        reporte = _reporte()
        casos = {
            "report_id": lambda m: m.__setitem__("report_id", "otro-id"),
            "report_kind": lambda m: m.__setitem__("report_kind", "production"),
            "decision_scope": lambda m: m.__setitem__("decision_scope", "operational"),
            "hash_contenido": lambda m: m["hashes"].__setitem__("report_content", "0" * 64),
            "sensibles_lista": lambda m: m["sensitivity"].__setitem__("sensitive_artifacts", ["tabla_a"]),
            "contains_sensitive": lambda m: m["sensitivity"].__setitem__("contains_sensitive", True),
        }
        for nombre, mutar in casos.items():
            with self.subTest(nombre):
                manifest = copy.deepcopy(_manifest_valido(reporte))
                mutar(manifest)
                res = validate_manifest(manifest, reporte)
                self.assert_estado(res, "REPORT-MANIFEST-CONSISTENCY", "FAIL")

    def test_manifest_de_otro_contenido_es_inconsistente(self):
        manifest = _manifest_valido(_reporte(tablas=[_tabla(rows=(("a", 9),))]))
        res = validate_manifest(manifest, _reporte())
        self.assert_estado(res, "REPORT-MANIFEST-CONSISTENCY", "FAIL")

    def test_sensibilidad_coherente_pasa(self):
        reporte = _reporte(tablas=[_tabla(sensitive=True)], figuras=[_figura(sensitive=True)])
        manifest = _manifest_valido(reporte)
        self.assertEqual(["fig_a", "tabla_a"], manifest["sensitivity"]["sensitive_artifacts"])
        self.assert_estado(validate_manifest(manifest, reporte), "REPORT-MANIFEST-CONSISTENCY", "PASS")

    def test_sin_fuentes_es_fail_pero_build_no_lanza(self):
        reporte = _reporte()
        manifest = _manifest_valido(reporte, sources=())
        self.assertEqual([], manifest["sources"])
        self.assert_estado(validate_manifest(manifest, reporte), "REPORT-SOURCES-NONE", "FAIL")

    def test_procedencia_degradada_es_warn(self):
        reporte = _reporte()
        for nombre, extra in (
            ("sin_commit", dict(git_commit=None, git_dirty=None)),
            ("sucio", dict(git_dirty=True)),
            ("sin_version", dict(harmessi_version=None)),
        ):
            with self.subTest(nombre):
                res = validate_manifest(_manifest_valido(reporte, **extra), reporte)
                self.assert_estado(res, "REPORT-PROVENANCE", "WARN")
                self.assertEqual([], _fails(res))

    def test_excepcion_interna_se_convierte_en_excepcion_code(self):
        reporte = _reporte()
        with mock.patch.object(validation, "_regla_procedencia", side_effect=RuntimeError("boom")):
            res = validate_manifest(_manifest_valido(reporte), reporte)
        self.assert_estado(res, "REPORT-PROVENANCE-EXCEPCION", "FAIL")
        self.assert_estado(res, "REPORT-MANIFEST-SCHEMA", "PASS")


# --- validate_report_dir ------------------------------------------------------


class TestValidateReportDir(_ConRepo):
    def test_reporte_valido_y_sin_cambios_cero_fail(self):
        out, _, _ = self._persistir(build_example_report())
        res = validate_report_dir(self.repo, out)
        self.assertEqual([], _fails(res), [r.to_dict() for r in _fails(res)])
        self.assert_sin_tecnicos(res)
        for codigo in (
            "REPORT-MANIFEST-MISSING",
            "REPORT-ARTIFACT-MISSING",
            "REPORT-ARTIFACT-HASH",
            "REPORT-SOURCE-MISSING",
            "REPORT-MANIFEST-SCHEMA",
            "REPORT-MANIFEST-CONSISTENCY",
            "REPORT-DEST-SCOPE",
            *CODES_REPORT,
        ):
            self.assertTrue(_por_codigo(res, codigo), codigo)

    def test_out_dir_relativo_se_interpreta_contra_el_repo(self):
        out, _, _ = self._persistir(_reporte())
        res = validate_report_dir(self.repo, out.relative_to(self.repo))
        self.assertEqual([], _fails(res), [r.to_dict() for r in _fails(res)])
        self.assert_estado(res, "REPORT-DEST-SCOPE", "PASS")

    def test_manifest_ausente_aunque_exista_report_html(self):
        out = self.repo / "reports" / "exploratory" / "rep-a"
        out.mkdir(parents=True)
        (out / "report.html").write_text("<html></html>", encoding="utf-8")
        res = validate_report_dir(self.repo, out)
        self.assertEqual(["REPORT-MANIFEST-MISSING"], [r.code for r in res])
        self.assertEqual("FAIL", res[0].status)

    def test_directorio_inexistente_es_manifest_missing(self):
        res = validate_report_dir(self.repo, self.repo / "reports" / "no-existe")
        self.assert_estado(res, "REPORT-MANIFEST-MISSING", "FAIL")

    def test_manifest_corrupto_o_no_objeto_corta(self):
        for contenido in (b"{no es json", b"[]", b"\xff\xfe"):
            with self.subTest(contenido=contenido):
                out = self.repo / "reports" / "exploratory" / "rep-a"
                out.mkdir(parents=True, exist_ok=True)
                (out / "manifest.json").write_bytes(contenido)
                res = validate_report_dir(self.repo, out)
                self.assertEqual(["REPORT-MANIFEST-UNREADABLE"], [r.code for r in res])
                self.assertEqual(("FAIL", "technical_error"), (res[0].status, res[0].kind))

    def test_byte_alterado_en_tabla_es_artifact_hash(self):
        out, _, _ = self._persistir(_reporte())
        ruta = out / "artifacts" / "tables" / "tabla_a.json"
        ruta.write_bytes(ruta.read_bytes() + b"\n")  # JSON sigue siendo valido; los bytes cambian
        res = validate_report_dir(self.repo, out)
        fallas = [r for r in _por_codigo(res, "REPORT-ARTIFACT-HASH") if r.status == "FAIL"]
        self.assertEqual(["artifacts/tables/tabla_a.json"], [r.subject for r in fallas])
        self.assert_estado(res, "REPORT-ARTIFACT-MISSING", "PASS")

    def test_contenido_alterado_falla_carga_sin_lanzar(self):
        out, _, _ = self._persistir(_reporte())
        ruta = out / "artifacts" / "tables" / "tabla_a.json"
        ruta.write_bytes(ruta.read_bytes().replace(b'"b"', b'"z"'))
        res = validate_report_dir(self.repo, out)
        self.assert_estado(res, "REPORT-ARTIFACT-HASH", "FAIL")
        carga = _por_codigo(res, "REPORT-LOAD")
        self.assertEqual([("FAIL", "technical_error")], [(r.status, r.kind) for r in carga])

    def test_artefacto_faltante(self):
        out, _, _ = self._persistir(_reporte())
        (out / "artifacts" / "figures" / "fig_a.json").unlink()
        res = validate_report_dir(self.repo, out)
        fallas = [r for r in _por_codigo(res, "REPORT-ARTIFACT-MISSING") if r.status == "FAIL"]
        self.assertEqual(["artifacts/figures/fig_a.json"], [r.subject for r in fallas])
        self.assert_estado(res, "REPORT-LOAD", "FAIL")

    def test_artefacto_no_listado_es_warn(self):
        out, _, _ = self._persistir(_reporte())
        extra = out / "artifacts" / "extra.json"
        extra.write_bytes(b"{}\n")
        res = validate_report_dir(self.repo, out)
        avisos = [r for r in _por_codigo(res, "REPORT-ARTIFACT-UNLISTED") if r.status == "WARN"]
        self.assertEqual(["artifacts/extra.json"], [r.subject for r in avisos])
        self.assertEqual([], _fails(res), [r.to_dict() for r in _fails(res)])

    def test_fuente_file_modificada_es_stale(self):
        csv = self._archivo("data/interim/ventas.csv", b"a,b\n1,2\n")
        fuente = describe_source(self.repo, "data/interim/ventas.csv", rows=1)
        out, _, _ = self._persistir(_reporte(), sources=[fuente])
        antes = validate_report_dir(self.repo, out)
        self.assert_estado(antes, "REPORT-SOURCE-STALE", "PASS")
        self.assert_estado(antes, "REPORT-SOURCE-MISSING", "PASS")
        self.assertEqual([], _fails(antes), [r.to_dict() for r in _fails(antes)])
        csv.write_bytes(b"a,b\n1,3\n")
        despues = validate_report_dir(self.repo, out)
        fallas = [r for r in _por_codigo(despues, "REPORT-SOURCE-STALE") if r.status == "FAIL"]
        self.assertEqual(["data/interim/ventas.csv"], [r.subject for r in fallas])

    def test_fuente_file_inexistente(self):
        csv = self._archivo("data/interim/ventas.csv", b"a,b\n1,2\n")
        fuente = describe_source(self.repo, "data/interim/ventas.csv")
        out, _, _ = self._persistir(_reporte(), sources=[fuente])
        csv.unlink()
        res = validate_report_dir(self.repo, out)
        fallas = [r for r in _por_codigo(res, "REPORT-SOURCE-MISSING") if r.status == "FAIL"]
        self.assertEqual(["data/interim/ventas.csv"], [r.subject for r in fallas])
        self.assert_estado(res, "REPORT-SOURCE-STALE", "PASS")

    def test_manifest_inconsistente_con_el_report(self):
        out, _, manifest = self._persistir(_reporte())
        manifest = copy.deepcopy(manifest)
        manifest["report_id"] = "otro-id"
        self._reescribir_manifest(out, manifest)
        res = validate_report_dir(self.repo, out)
        self.assert_estado(res, "REPORT-MANIFEST-CONSISTENCY", "FAIL")

    def test_sensibilidad_inconsistente(self):
        out, _, manifest = self._persistir(_reporte())
        manifest = copy.deepcopy(manifest)
        manifest["sensitivity"] = {"contains_sensitive": True, "sensitive_artifacts": ["tabla_a"]}
        self._reescribir_manifest(out, manifest)
        res = validate_report_dir(self.repo, out)
        self.assert_estado(res, "REPORT-MANIFEST-CONSISTENCY", "FAIL")

    def test_manifest_sin_fuentes_y_con_procedencia_degradada(self):
        out, _, _ = self._persistir(_reporte(), sources=())
        res = validate_report_dir(self.repo, out)
        self.assert_estado(res, "REPORT-SOURCES-NONE", "FAIL")
        self.assert_estado(res, "REPORT-PROVENANCE", "WARN")

    def test_copia_byte_identica_de_artefacto_exploratory_en_model_valid(self):
        _, artefactos_e, _ = self._persistir(_reporte(report_id="rep-e", scope="exploratory"))
        self._archivo("data/interim/copia.csv", artefactos_e["artifacts/tables/tabla_a.json"])
        fuente = describe_source(self.repo, "data/interim/copia.csv")
        out, _, _ = self._persistir(_reporte(report_id="rep-m", scope="model_valid"), sources=[fuente])
        res = validate_report_dir(self.repo, out)
        fallas = [r for r in _por_codigo(res, "REPORT-ISOLATION-HASH") if r.status == "FAIL"]
        self.assertEqual(1, len(fallas))
        self.assertIn("rep-e", fallas[0].message)
        self.assertIn("reports/exploratory/rep-e/artifacts/tables/tabla_a.json", fallas[0].message)
        self.assert_estado(res, "REPORT-EXPLORATORY-IN-MODEL-FLOW", "FAIL")

    def test_input_distinto_en_model_valid_pasa_aislamiento(self):
        self._persistir(_reporte(report_id="rep-e", scope="exploratory"))
        self._archivo("data/interim/otro.csv", b"x,y\n1,2\n")
        fuente = describe_source(self.repo, "data/interim/otro.csv")
        out, _, _ = self._persistir(_reporte(report_id="rep-m", scope="model_valid"), sources=[fuente])
        res = validate_report_dir(self.repo, out)
        self.assert_estado(res, "REPORT-ISOLATION-HASH", "PASS")
        self.assert_estado(res, "REPORT-EXPLORATORY-IN-MODEL-FLOW", "PASS")
        self.assertEqual([], _fails(res), [r.to_dict() for r in _fails(res)])

    def test_misma_copia_en_flujo_exploratory_no_falla(self):
        _, artefactos_e, _ = self._persistir(_reporte(report_id="rep-e", scope="exploratory"))
        self._archivo("data/interim/copia.csv", artefactos_e["artifacts/tables/tabla_a.json"])
        fuente = describe_source(self.repo, "data/interim/copia.csv")
        out, _, _ = self._persistir(_reporte(report_id="rep-o", scope="exploratory"), sources=[fuente])
        res = validate_report_dir(self.repo, out)
        self.assertEqual([], _por_codigo(res, "REPORT-ISOLATION-HASH"))
        self.assert_estado(res, "REPORT-EXPLORATORY-IN-MODEL-FLOW", "N/A")
        self.assertEqual([], _fails(res), [r.to_dict() for r in _fails(res)])

    def test_destino_cruzado_de_scope_es_fail_de_governance(self):
        out, _, _ = self._persistir(
            _reporte(report_id="rep-m", scope="model_valid"), out_rel="reports/exploratory/rep-m"
        )
        res = validate_report_dir(self.repo, out)
        self.assert_estado(res, "REPORT-DEST-CROSS-SCOPE", "FAIL")

    def test_policy_cientifica_corrupta_omite_eda_y_falla(self):
        out, _, _ = self._persistir(build_example_report())
        self._archivo(".harmessi/scientific-policy.json", b"{corrupta")
        with mock.patch.object(validation.eda_profile, "validate_eda_report") as m:
            res = validate_report_dir(self.repo, out)
        m.assert_not_called()
        fallas = [r for r in _por_codigo(res, "REPORT-SCI-POLICY") if r.status == "FAIL"]
        self.assertEqual([("FAIL", "technical_error")], [(r.status, r.kind) for r in fallas])
        self.assertEqual([], _por_codigo(res, "REPORT-EDA"))

    def test_eda_recibe_la_policy_leida_una_sola_vez(self):
        original = validation.eda_profile.validate_eda_report
        # (a) sin archivo de policy: dict por defecto de leer_policy
        out, _, _ = self._persistir(build_example_report())
        with mock.patch.object(validation.eda_profile, "validate_eda_report", wraps=original) as m:
            res = validate_report_dir(self.repo, out)
        m.assert_called_once()
        self.assertEqual(validation.scientific_validity.leer_policy(self.repo), m.call_args.kwargs["scientific_policy"])
        self.assert_estado(res, "REPORT-SCI-POLICY", "PASS")
        # (b) con policy declarada: el dict leido del disco
        politica = dict(validation.scientific_validity.leer_policy(self.repo))
        politica["temporal"] = {"declared": True, "date_column": "fecha"}
        self._archivo(".harmessi/scientific-policy.json", json.dumps(politica).encode("utf-8"))
        with mock.patch.object(validation.eda_profile, "validate_eda_report", wraps=original) as m:
            res = validate_report_dir(self.repo, out)
        m.assert_called_once()
        self.assertEqual(politica, m.call_args.kwargs["scientific_policy"])
        self.assert_sin_tecnicos(res)

    def test_nunca_lanza_con_basura(self):
        out, _, _ = self._persistir(_reporte())
        for repo, destino in ((None, None), (42, out), (self.repo, 42), (self.repo, None), ("/no/existe", "/no/existe")):
            with self.subTest(repo=repo, destino=destino):
                res = validate_report_dir(repo, destino)
                self.assertTrue(res)
                self.assertTrue(_fails(res), [r.to_dict() for r in res])

    def test_excepcion_interna_se_convierte_en_excepcion_code(self):
        out, _, _ = self._persistir(_reporte())
        with mock.patch.object(validation, "_paso_fuentes", side_effect=RuntimeError("boom")):
            res = validate_report_dir(self.repo, out)
        malos = _por_codigo(res, "REPORT-SOURCE-EXCEPCION")
        self.assertEqual([("FAIL", "technical_error")], [(r.status, r.kind) for r in malos])
        self.assert_estado(res, "REPORT-ARTIFACT-HASH", "PASS")  # los demas pasos siguieron

    def test_excepcion_en_governance_no_frena_el_resto(self):
        out, _, _ = self._persistir(_reporte())
        with mock.patch.object(validation, "_paso_gobernanza", side_effect=RuntimeError("boom")):
            res = validate_report_dir(self.repo, out)
        self.assert_estado(res, "REPORT-GOVERNANCE-EXCEPCION", "FAIL")
        self.assert_estado(res, "REPORT-EXPLORATORY-IN-MODEL-FLOW", "N/A")

    def test_solo_lectura_y_determinista(self):
        out, _, _ = self._persistir(build_example_report())
        antes = self._snapshot()
        r1 = validate_report_dir(self.repo, out)
        r2 = validate_report_dir(self.repo, out)
        self.assertEqual(antes, self._snapshot())
        self.assertEqual([r.to_dict() for r in r1], [r.to_dict() for r in r2])


FUTURO = "2099-01-01T00:00:00Z"


def _fuente_manual(path: str, contenido: bytes) -> dict:
    return {
        "kind": "file",
        "role": "input",
        "path": path,
        "sha256": hashlib.sha256(contenido).hexdigest(),
        "algorithm": "sha256/bin/v1",
        "size_bytes": len(contenido),
    }


class TestValidateReportDirSeguridad(_ConRepo):
    """Ciclo reviewer 1: acceso antes de abrir, single-read, conjunto de artefactos, mensajes sin rutas locales."""

    def _guardrails(self, **datos):
        self._archivo(".claude/guardrails.json", json.dumps(datos).encode("utf-8"))

    def _editar_manifest(self, out: Path, mutar):
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        mutar(manifest)
        (out / "manifest.json").write_bytes(manifest_to_bytes(manifest))

    @contextlib.contextmanager
    def _sin_abrir(self, nombre: str):
        original = Path.read_bytes

        def espia(ruta, *a, **k):
            if ruta.name == nombre:
                raise AssertionError(f"se abrió {nombre}")
            return original(ruta, *a, **k)

        with mock.patch.object(Path, "read_bytes", espia), mock.patch.object(
            validation.evidence, "describe_source", side_effect=AssertionError("describe_source")
        ) as descr, mock.patch.object(
            validation.evidence._fingerprint, "calcular_fingerprint", side_effect=AssertionError("hash")
        ) as huella:
            yield descr, huella

    def _sin_excepciones(self, res):
        self.assertEqual([], [r.code for r in res if r.code.endswith("-EXCEPCION")])

    # --- fuentes: acceso antes de abrir -------------------------------------

    def test_fuente_en_holdout_es_unverifiable_y_no_se_abre(self):
        contenido = b"secreto\n"
        self._archivo("data/sellado/h.csv", contenido)
        self._guardrails(holdouts=["data/sellado/**"])
        out, _, _ = self._persistir(_reporte(), sources=[_fuente_manual("data/sellado/h.csv", contenido)])
        with self._sin_abrir("h.csv") as (descr, huella):
            res = validate_report_dir(self.repo, out)
        descr.assert_not_called()
        huella.assert_not_called()
        self._sin_excepciones(res)
        fallas = [r for r in _por_codigo(res, "REPORT-SOURCE-UNVERIFIABLE") if r.status == "FAIL"]
        self.assertEqual([("data/sellado/h.csv", "technical_error")], [(r.subject, r.kind) for r in fallas])
        self.assertIn("acceso denegado", fallas[0].message)
        self.assert_estado(res, "REPORT-SOURCE-STALE", "PASS")  # nunca STALE ni PASS "verificado" para esa fuente
        self.assertEqual([], [r for r in _por_codigo(res, "REPORT-SOURCE-STALE") if r.status != "PASS"])

    def test_fuente_en_holdout_con_excepcion_vigente_se_verifica(self):
        contenido = b"secreto\n"
        self._archivo("data/sellado/h.csv", contenido)
        self._guardrails(
            holdouts=["data/sellado/**"],
            excepciones=[{"accion": "read", "ruta": "data/sellado/h.csv", "vence_utc": FUTURO}],
        )
        out, _, _ = self._persistir(_reporte(), sources=[_fuente_manual("data/sellado/h.csv", contenido)])
        res = validate_report_dir(self.repo, out)
        self.assert_estado(res, "REPORT-SOURCE-UNVERIFIABLE", "PASS")
        self.assert_estado(res, "REPORT-SOURCE-STALE", "PASS")
        # con la excepcion vigente y la fuente modificada, ahora si es stale
        (self.repo / "data" / "sellado" / "h.csv").write_bytes(b"otro\n")
        res2 = validate_report_dir(self.repo, out)
        self.assert_estado(res2, "REPORT-SOURCE-STALE", "FAIL")

    def test_fuente_env_o_fuera_del_repo_no_verificable(self):
        self._archivo(".env", b"X=1\n")
        with tempfile.TemporaryDirectory() as otro:
            externo = Path(otro) / "e.csv"
            externo.write_bytes(b"1\n")
            for etiqueta, ruta in (
                (".env", ".env"),
                ("relativa fuera", "../fuera.csv"),
                ("absoluta fuera", str(externo)),
            ):
                with self.subTest(etiqueta):
                    out, _, _ = self._persistir(_reporte(), sources=[_fuente_manual(ruta, b"x")])
                    with self._sin_abrir("e.csv") as (descr, huella):
                        res = validate_report_dir(self.repo, out)
                    descr.assert_not_called()
                    huella.assert_not_called()
                    self._sin_excepciones(res)
                    fallas = [r for r in _por_codigo(res, "REPORT-SOURCE-UNVERIFIABLE") if r.status == "FAIL"]
                    self.assertEqual(1, len(fallas))
                    self.assertEqual("technical_error", fallas[0].kind)
                    self.assertEqual([], [r for r in _por_codigo(res, "REPORT-SOURCE-STALE") if r.status == "FAIL"])
                    for r in res:
                        if r.code in validation.CODES or r.code.endswith("-EXCEPCION"):  # governance es ajeno a este módulo
                            for campo in (r.message, r.detail or "", r.subject or ""):
                                self.assertNotIn(otro, campo)

    def test_guardrails_corrupto_hace_fuentes_no_verificables(self):
        contenido = b"a,b\n"
        self._archivo("data/interim/x.csv", contenido)
        out, _, _ = self._persistir(_reporte(), sources=[_fuente_manual("data/interim/x.csv", contenido)])
        self._archivo(".claude/guardrails.json", b"{corrupto")
        res = validate_report_dir(self.repo, out)
        self._sin_excepciones(res)
        self.assert_estado(res, "REPORT-MANIFEST-UNREADABLE", "FAIL")  # ni el manifest se abre (fail-closed)

    def test_aislamiento_por_hash_no_hashea_input_en_holdout(self):
        contenido = b"secreto\n"
        self._archivo("data/sellado/h.csv", contenido)
        self._guardrails(holdouts=["data/sellado/**"])
        out, _, _ = self._persistir(
            _reporte(report_id="rep-m", scope="model_valid"),
            sources=[_fuente_manual("data/sellado/h.csv", contenido)],
        )
        with self._sin_abrir("h.csv") as (descr, huella):
            res = validate_report_dir(self.repo, out)
        huella.assert_not_called()
        self._sin_excepciones(res)
        self.assert_estado(res, "REPORT-SOURCE-UNVERIFIABLE", "FAIL")
        tecnicos = [r for r in _por_codigo(res, "REPORT-ISOLATION-HASH") if r.status == "FAIL"]
        self.assertEqual(["technical_error"], [r.kind for r in tecnicos])
        self.assertIn("no verificable", tecnicos[0].message)

    # --- lectura unica y enlaces --------------------------------------------

    def test_single_read_cada_archivo_se_lee_una_vez(self):
        out, _, _ = self._persistir(build_example_report())
        original = Path.read_bytes
        conteo: Counter = Counter()

        def espia(ruta, *a, **k):
            conteo[str(ruta)] += 1
            return original(ruta, *a, **k)

        with mock.patch.object(Path, "read_bytes", espia):
            res = validate_report_dir(self.repo, out)
        self.assertEqual([], _fails(res), [r.to_dict() for r in _fails(res)])
        leidos_del_reporte = {k: v for k, v in conteo.items() if k.startswith(str(out))}
        self.assertGreaterEqual(len(leidos_del_reporte), 4)  # manifest, report, insights, >=1 tabla/figura
        self.assertEqual([], [(k, v) for k, v in leidos_del_reporte.items() if v > 1])

    def _crear_enlace(self, link: Path, destino: Path):
        try:
            os.symlink(destino, link, target_is_directory=True)
        except (OSError, NotImplementedError, AttributeError):
            if os.name != "nt":
                self.skipTest("el SO no permite crear symlinks")
            subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(destino)], capture_output=True, check=False)
        if not os.path.lexists(link):
            self.skipTest("el SO no permite crear symlinks ni junctions")

    def test_directorio_de_artefactos_que_es_enlace_a_un_holdout(self):
        out, artefactos, _ = self._persistir(_reporte())
        holdout = self.repo / "data" / "sellado_tablas"
        holdout.mkdir(parents=True)
        (holdout / "tabla_a.json").write_bytes(artefactos["artifacts/tables/tabla_a.json"])
        self._guardrails(holdouts=["data/sellado_tablas/**"])
        shutil.rmtree(out / "artifacts" / "tables")
        self._crear_enlace(out / "artifacts" / "tables", holdout)
        with self._sin_abrir("tabla_a.json"):
            res = validate_report_dir(self.repo, out)
        self._sin_excepciones(res)
        hashes = [r for r in _por_codigo(res, "REPORT-ARTIFACT-HASH") if r.status == "FAIL"]
        self.assertEqual(["technical_error"], [r.kind for r in hashes])
        self.assertEqual(["artifacts/tables/tabla_a.json"], [r.subject for r in hashes])
        self.assert_estado(res, "REPORT-LOAD", "FAIL")
        self.assert_estado(res, "REPORT-ARTIFACT-UNLISTED", "WARN")

    def test_file_con_nul_o_nombre_reservado_es_fail_sin_excepcion(self):
        for nombre in ("artifacts/tables/con.json", "artifacts/tables/a\x00b.json", "../fuera.json"):
            with self.subTest(nombre=nombre):
                out, _, _ = self._persistir(_reporte(), out_rel=f"reports/exploratory/rep-{abs(hash(nombre)) % 1000}")

                def mutar(m, nombre=nombre):
                    m["artifacts"][0]["file"] = nombre

                self._editar_manifest(out, mutar)
                res = validate_report_dir(self.repo, out)
                self._sin_excepciones(res)
                self.assert_estado(res, "REPORT-ARTIFACT-SET", "FAIL")
                self.assert_estado(res, "REPORT-MANIFEST-SCHEMA", "FAIL")

    # --- conjunto de artefactos ---------------------------------------------

    def test_artifacts_vacio_es_artifact_set(self):
        out, _, _ = self._persistir(_reporte())
        self._editar_manifest(out, lambda m: m.__setitem__("artifacts", []))
        res = validate_report_dir(self.repo, out)
        self.assert_estado(res, "REPORT-ARTIFACT-SET", "FAIL")
        self.assert_estado(res, "REPORT-ARTIFACT-HASH", "PASS")  # nada listado no es "todo verificado"
        self.assertIn("vacío", _por_codigo(res, "REPORT-ARTIFACT-SET")[0].message)

    def test_artefacto_extra_listado_es_artifact_set(self):
        out, _, _ = self._persistir(_reporte())
        extra = b"{}\n"
        (out / "artifacts" / "tables" / "x.json").write_bytes(extra)
        self._editar_manifest(
            out,
            lambda m: m["artifacts"].append(
                {"id": "x", "kind": "table", "file": "artifacts/tables/x.json", "sha256": hashlib.sha256(extra).hexdigest()}
            ),
        )
        res = validate_report_dir(self.repo, out)
        fallas = [r for r in _por_codigo(res, "REPORT-ARTIFACT-SET") if r.status == "FAIL"]
        self.assertEqual(["artifacts/tables/x.json"], [r.subject for r in fallas])
        self.assert_estado(res, "REPORT-ARTIFACT-HASH", "PASS")

    def test_artefacto_esperado_no_listado_es_artifact_set(self):
        out, _, _ = self._persistir(_reporte())
        self._editar_manifest(
            out, lambda m: m.__setitem__("artifacts", [a for a in m["artifacts"] if a["id"] != "tabla_a"])
        )
        res = validate_report_dir(self.repo, out)
        fallas = [r for r in _por_codigo(res, "REPORT-ARTIFACT-SET") if r.status == "FAIL"]
        self.assertEqual(["artifacts/tables/tabla_a.json"], [r.subject for r in fallas])
        self.assert_estado(res, "REPORT-ARTIFACT-UNLISTED", "WARN")

    def test_id_o_kind_que_no_coincide_con_el_archivo(self):
        for campo, valor in (("id", "otra"), ("kind", "figure")):
            with self.subTest(campo):
                out, _, _ = self._persistir(_reporte(), out_rel=f"reports/exploratory/rep-{campo}")

                def mutar(m, campo=campo, valor=valor):
                    for a in m["artifacts"]:
                        if a["file"] == "artifacts/tables/tabla_a.json":
                            a[campo] = valor

                self._editar_manifest(out, mutar)
                res = validate_report_dir(self.repo, out)
                fallas = [r for r in _por_codigo(res, "REPORT-ARTIFACT-SET") if r.status == "FAIL"]
                self.assertEqual(["artifacts/tables/tabla_a.json"], [r.subject for r in fallas])

    def test_conjunto_exacto_pasa(self):
        out, _, _ = self._persistir(_reporte())
        res = validate_report_dir(self.repo, out)
        self.assert_estado(res, "REPORT-ARTIFACT-SET", "PASS")
        self.assert_estado(res, "REPORT-ARTIFACT-UNLISTED", "PASS")

    def test_archivo_en_la_raiz_no_listado_es_warn(self):
        out, _, _ = self._persistir(_reporte())
        (out / "notas.txt").write_text("x", encoding="utf-8")
        (out / "report.html").write_text("<html></html>", encoding="utf-8")  # permitido
        res = validate_report_dir(self.repo, out)
        avisos = [r for r in _por_codigo(res, "REPORT-ARTIFACT-UNLISTED") if r.status == "WARN"]
        self.assertEqual(["notas.txt"], [r.subject for r in avisos])
        self.assertEqual([], _fails(res), [r.to_dict() for r in _fails(res)])

    def test_insights_json_no_listado_es_warn(self):
        out, _, _ = self._persistir(_reporte())
        self._editar_manifest(
            out, lambda m: m.__setitem__("artifacts", [a for a in m["artifacts"] if a["file"] != "insights.json"])
        )
        res = validate_report_dir(self.repo, out)
        avisos = [r for r in _por_codigo(res, "REPORT-ARTIFACT-UNLISTED") if r.status == "WARN"]
        self.assertIn("insights.json", [r.subject for r in avisos])

    def test_no_poder_listar_el_directorio_es_fail_technical_error_no_pass(self):
        out, _, _ = self._persistir(_reporte())
        original = os.listdir

        def falla_en_out(ruta=".", *args, **kwargs):
            if Path(ruta).resolve() == Path(out).resolve():
                raise OSError("sin permiso")
            return original(ruta, *args, **kwargs)

        with mock.patch("os.listdir", side_effect=falla_en_out):
            res = validate_report_dir(self.repo, out)
        fallas = [r for r in _por_codigo(res, "REPORT-ARTIFACT-UNLISTED") if r.status == "FAIL"]
        self.assertEqual(1, len(fallas), [r.to_dict() for r in res])
        self.assertEqual("technical_error", fallas[0].kind)
        self.assertIn("no verificable: no se pudo listar el directorio", fallas[0].message)
        self.assertEqual([], [r for r in _por_codigo(res, "REPORT-ARTIFACT-UNLISTED") if r.status == "PASS"])

    # --- aislamiento: via path/manifest y propagacion del indice ---------------

    def test_via_path_de_governance_agrega_exploratory_in_model_flow(self):
        self._persistir(_reporte(report_id="rep-e", scope="exploratory"))
        ruta = "reports/exploratory/rep-e/artifacts/tables/tabla_a.json"
        fuente = describe_source(self.repo, ruta)
        out, _, _ = self._persistir(_reporte(report_id="rep-m", scope="model_valid"), sources=[fuente])
        # el hash NO aporta nada: la agregacion debe venir de REPORT-ISOLATION-INPUT (path/manifest)
        neutro = [validation._res("PASS", "REPORT-ISOLATION-HASH", "sin coincidencias")]
        with mock.patch.object(validation.evidence, "check_inputs_hash_isolation", return_value=neutro):
            res = validate_report_dir(self.repo, out)
        self.assert_estado(res, "REPORT-ISOLATION-INPUT", "FAIL")
        agregado = [r for r in _por_codigo(res, "REPORT-EXPLORATORY-IN-MODEL-FLOW") if r.status == "FAIL"]
        self.assertEqual(1, len(agregado))
        self.assertIn("REPORT-ISOLATION-INPUT", agregado[0].detail)

    def test_indice_exploratory_se_calcula_una_vez_y_propaga_warn_de_ilegibles(self):
        self._persistir(_reporte(report_id="rep-e", scope="exploratory"))
        self._archivo("reports/exploratory/rep-malo/manifest.json", b"{corrupto")
        self._archivo("data/interim/otro.csv", b"x,y\n1,2\n")
        fuente = describe_source(self.repo, "data/interim/otro.csv")
        out, _, _ = self._persistir(_reporte(report_id="rep-m", scope="model_valid"), sources=[fuente])
        original = validation.evidence.exploratory_index_status
        with mock.patch.object(validation.evidence, "exploratory_index_status", wraps=original) as m:
            res = validate_report_dir(self.repo, out)
        m.assert_called_once()
        avisos = [r for r in _por_codigo(res, "REPORT-ISOLATION-HASH") if r.status == "WARN"]
        self.assertEqual(1, len(avisos))
        self.assertIn("ilegibles", avisos[0].message)
        self.assertEqual([], _fails(res), [r.to_dict() for r in _fails(res)])

    # --- mensajes sin rutas locales -----------------------------------------

    def test_mensajes_sin_ruta_absoluta_del_repo(self):
        raiz = str(self.repo)
        contenido = b"secreto\n"
        self._archivo("data/sellado/h.csv", contenido)
        self._guardrails(holdouts=["data/sellado/**"])
        out, _, _ = self._persistir(_reporte(), sources=[_fuente_manual("data/sellado/h.csv", contenido)])
        (out / "artifacts" / "tables" / "tabla_a.json").unlink()
        escenarios = [validate_report_dir(self.repo, out)]
        with mock.patch.object(validation, "_paso_fuentes", side_effect=FileNotFoundError(raiz + "/secreto")):
            escenarios.append(validate_report_dir(self.repo, out))
        with tempfile.TemporaryDirectory() as otro:
            escenarios.append(validate_report_dir(self.repo, otro))
            escenarios.append(validate_report_dir(self.repo, Path(otro) / "no-existe"))
            escenarios.append(validate_report_dir(otro, otro))
        for res in escenarios:
            for r in res:
                if r.code in validation.CODES or r.code.endswith("-EXCEPCION"):
                    for campo in (r.message, r.detail or "", r.subject or ""):
                        self.assertNotIn(raiz, campo)
                        self.assertNotIn(raiz.replace("\\", "/"), campo)
        excepciones = [r for r in escenarios[1] if r.code.endswith("-EXCEPCION")]
        self.assertEqual(1, len(excepciones))
        self.assertIn("FileNotFoundError", excepciones[0].message)
        self.assertNotIn("secreto", excepciones[0].message)

    def test_out_relativo_fuera_del_repo_no_expone_la_ruta(self):
        with tempfile.TemporaryDirectory() as otro:
            etiqueta = validation._out_relativo(self.repo, Path(otro).resolve())
        self.assertTrue(etiqueta.startswith("<fuera-del-repo>/"))
        self.assertNotIn(str(self.repo), etiqueta)


class TestImportsPermitidos(unittest.TestCase):
    def test_validation_no_importa_pandas_plotly_ni_ds_profile(self):
        arbol = ast.parse(Path(validation.__file__).read_text(encoding="utf-8"))
        modulos = set()
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Import):
                modulos.update(a.name.split(".")[0] for a in nodo.names)
            elif isinstance(nodo, ast.ImportFrom) and nodo.level == 0 and nodo.module:
                modulos.add(nodo.module.split(".")[0])
        self.assertEqual(set(), modulos & {"pandas", "numpy", "plotly", "requests", "ds_profile"})

    def test_codes_sin_duplicados(self):
        self.assertEqual(len(CODES), len(set(CODES)))


if __name__ == "__main__":
    unittest.main()

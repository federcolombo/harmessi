"""Tests de `tools/reporting/governance.py` (v0.6 Change 1, `20260918-reporting-governance`).

Deterministas: sin red, sin aleatoriedad, sin pandas. Repos temporales con su
propio `.claude/guardrails.json`; los holdouts de prueba son patrones sintéticos
(nunca datos reales). Fixtures 100% genéricos. No dependen de symlinks (el
único test que los usa se omite si el SO no los permite).
"""
from __future__ import annotations

import ast
import json
import os
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

from tools.reporting import governance
from tools.reporting.core import (
    DECISION_SCOPES,
    Chapter,
    FigureArtifact,
    FigureSpec,
    Report,
    TableArtifact,
)
from tools.reporting.governance import (
    CODE_DEST_CROSS_SCOPE,
    CODE_DEST_SAFE,
    CODE_DEST_SCOPE,
    CODE_HOLDOUT_ACCESS,
    CODE_HOLDOUT_SOURCE,
    CODE_ISOLATION_INPUT,
    CODE_POLICY,
    CODE_SCI_CUTOFF,
    CODE_SENSITIVE_DEST,
    CODE_SOURCE_ACCESS,
    CODES,
    REQUIRED_DESTINATION_CODES,
    GovernanceContext,
    ReportingPolicy,
    ReportingPolicyError,
    check_flow_inputs,
    context_from_report,
    evaluate_destination,
    evaluate_governance,
    load_policy,
    output_allowed,
    resolve_output_dir,
)

# `governance` agrega `tools/` a sys.path al importarse, así que `dsguard` ya es importable.
from dsguard import checks, pathguard  # noqa: E402

PASS, WARN, FAIL, NA = checks.STATUS_PASS, checks.STATUS_WARN, checks.STATUS_FAIL, checks.STATUS_NA
FUTURO = "2999-01-01T00:00:00Z"
PASADO = "2000-01-01T00:00:00Z"
CODIGOS_VALIDOS = set(CODES)


def _solo(resultados, code):
    return [r for r in resultados if r.code == code]


def _snapshot(raiz: Path) -> dict:
    """Ruta -> (tamaño, mtime_ns) de todo el árbol (incluye directorios)."""
    return {
        p.relative_to(raiz).as_posix(): (p.stat().st_size, p.stat().st_mtime_ns)
        for p in sorted(raiz.rglob("*"))
    }


def _crear_enlace_dir(enlace: Path, destino: Path) -> bool:
    """Symlink a directorio; en Windows sin privilegios cae a una junction.
    Devuelve `False` si el SO no permite ninguno (el llamador hace `skipTest`)."""
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


class _RepoBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo = Path(self._tmp.name).resolve()

    # -- helpers de repo temporal --
    def escribir(self, rel: str, contenido: str = "") -> Path:
        ruta = self.repo / rel
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(contenido, encoding="utf-8")
        return ruta

    def escribir_json(self, rel: str, datos) -> Path:
        return self.escribir(rel, json.dumps(datos))

    def guardrails(self, **datos) -> None:
        self.escribir_json(".claude/guardrails.json", datos)

    def policy_reporting(self, datos: dict) -> None:
        datos = dict(datos)
        datos.setdefault("schema_version", 1)
        self.escribir_json(".harmessi/reporting-policy.json", datos)

    def policy_cientifica(self, datos: dict) -> None:
        datos = dict(datos)
        datos.setdefault("schema_version", 1)
        self.escribir_json(".harmessi/scientific-policy.json", datos)

    def ctx(self, **kw) -> GovernanceContext:
        base = dict(
            repo_root=self.repo,
            report_id="informe-1",
            report_kind="eda",
            decision_scope="exploratory",
            out_dir="reports/exploratory/informe-1",
            holdout_access="none",
        )
        base.update(kw)
        return GovernanceContext(**base)

    def gov(self, **kw):
        return evaluate_governance(self.ctx(**kw))

    def dest(self, **kw):
        return evaluate_destination(self.ctx(**kw))

    def assertVocabulario(self, resultados):
        self.assertIsInstance(resultados, list)
        self.assertTrue(resultados, "ningún check devuelve lista vacía")
        for r in resultados:
            self.assertIsInstance(r, checks.CheckResult)
            self.assertIn(r.status, {PASS, WARN, FAIL, NA})
            self.assertTrue(r.code in CODIGOS_VALIDOS or r.code.endswith("-EXCEPCION"), r.code)


# ---------------------------------------------------------------------------
# R1 - restricciones transversales
# ---------------------------------------------------------------------------


class TestR1Transversales(_RepoBase):
    _PERMITIDOS = {"__future__", "json", "sys", "dataclasses", "datetime", "pathlib", "typing", "dsguard"}
    _ESCRITURA = {"write_text", "write_bytes", "mkdir", "unlink", "rename", "rmdir", "touch"}

    def _arbol(self):
        return ast.parse(Path(governance.__file__).read_text(encoding="utf-8"))

    def test_imports_solo_stdlib_dsguard_y_core(self):
        for nodo in ast.walk(self._arbol()):
            if isinstance(nodo, ast.Import):
                for alias in nodo.names:
                    self.assertIn(alias.name.split(".")[0], self._PERMITIDOS, alias.name)
            elif isinstance(nodo, ast.ImportFrom):
                if nodo.level == 1:
                    self.assertIsNone(nodo.module)
                    self.assertEqual([a.name for a in nodo.names], ["core"])
                else:
                    self.assertEqual(nodo.level, 0)
                    self.assertIn((nodo.module or "").split(".")[0], self._PERMITIDOS, nodo.module)

    def test_sin_llamadas_de_escritura(self):
        for nodo in ast.walk(self._arbol()):
            if isinstance(nodo, ast.Call):
                if isinstance(nodo.func, ast.Attribute):
                    self.assertNotIn(nodo.func.attr, self._ESCRITURA)
                if isinstance(nodo.func, ast.Name):
                    self.assertNotEqual(nodo.func.id, "open")

    def test_solo_lectura_arbol_identico(self):
        self.policy_reporting({"sensitive_destination_roots": ["reports/model_valid/sens"]})
        self.policy_cientifica({"temporal": {"declared": True, "cutoff_utc": "2026-01-01T00:00:00Z"}})
        self.guardrails(holdouts=["data/holdout/**"])
        self.escribir("otros/informe_x/manifest.json", json.dumps({"report_id": "x", "decision_scope": "exploratory"}))
        ctx = self.ctx(sources=["data/interim/a.csv", "data/holdout/b.csv", "otros/informe_x/t.csv"])

        def ejecutar_todo():
            load_policy(self.repo)
            evaluate_governance(ctx)
            evaluate_destination(ctx)
            check_flow_inputs(self.repo, "model_valid", ["otros/informe_x/t.csv", "data/holdout/b.csv"])
            resolve_output_dir(load_policy(self.repo), "exploratory", "r1")

        antes = _snapshot(self.repo)
        ejecutar_todo()
        self.assertEqual(antes, _snapshot(self.repo))
        # tambien con archivos de configuracion corruptos
        self.escribir(".claude/guardrails.json", "{corrupto")
        self.escribir(".harmessi/scientific-policy.json", "{corrupto")
        antes = _snapshot(self.repo)
        ejecutar_todo()
        self.assertEqual(antes, _snapshot(self.repo))

    def test_contextos_mal_formados_no_lanzan(self):
        # (contexto, ¿el malformado afecta también al destino?)
        casos = [
            (self.ctx(sources=None), False),
            (self.ctx(out_dir=None), True),
            (self.ctx(decision_scope=123), True),
            (self.ctx(repo_root=self.repo / "no_existe"), True),
            (self.ctx(repo_root=None), True),
            (self.ctx(repo_root=123), True),
            (self.ctx(sensitive_artifacts=None), True),
            (self.ctx(holdout_access=5, data_cutoff=7), False),
        ]
        for i, (ctx, afecta_destino) in enumerate(casos):
            with self.subTest(caso=i, funcion="evaluate_governance"):
                res = evaluate_governance(ctx)
                self.assertVocabulario(res)
                self.assertIn(FAIL, [r.status for r in res])
            with self.subTest(caso=i, funcion="evaluate_destination"):
                res = evaluate_destination(ctx)
                self.assertVocabulario(res)
                if afecta_destino:
                    self.assertIn(FAIL, [r.status for r in res])
        for basura in (None, 123, "x"):
            self.assertVocabulario(evaluate_governance(basura))
            self.assertIn(FAIL, [r.status for r in evaluate_governance(basura)])

    def test_check_flow_inputs_mal_formado_no_lanza(self):
        for args in (
            (None, "model_valid", ["x"]),
            (self.repo / "no_existe", "model_valid", ["x"]),
            (self.repo, 123, ["x"]),
            (self.repo, "model_valid", None),
            (self.repo, "model_valid", [None, 5]),
        ):
            with self.subTest(args=args):
                res = check_flow_inputs(*args)
                self.assertVocabulario(res)
                self.assertIn(FAIL, [r.status for r in res])

    def test_output_allowed_no_lanza_con_basura(self):
        for basura in (None, 5, [object()], "x"):
            self.assertIs(output_allowed(basura), False)

    def test_deterministas(self):
        self.guardrails(holdouts=["data/holdout/**"])
        ctx = self.ctx(sources=["data/interim/a.csv", "data/holdout/x.csv"])
        primera = evaluate_governance(ctx)
        segunda = evaluate_governance(ctx)
        self.assertEqual(primera, segunda)
        self.assertEqual([r.code for r in primera], [r.code for r in segunda])

    def test_repo_root_como_str_es_aceptado(self):
        res = evaluate_destination(self.ctx(repo_root=str(self.repo)))
        self.assertNotIn(FAIL, [r.status for r in res])
        self.assertTrue(output_allowed(res))


# ---------------------------------------------------------------------------
# R2 - vocabulario, ausencia != PASS
# ---------------------------------------------------------------------------


class TestR2Vocabulario(_RepoBase):
    def test_codigos_exactos(self):
        self.assertEqual(
            set(CODES),
            {
                "REPORT-POLICY", "REPORT-DEST-SAFE", "REPORT-DEST-SCOPE", "REPORT-DEST-CROSS-SCOPE",
                "REPORT-SENSITIVE-DEST", "REPORT-SOURCE-ACCESS", "REPORT-HOLDOUT-ACCESS",
                "REPORT-HOLDOUT-SOURCE", "REPORT-ISOLATION-INPUT", "REPORT-SCI-CUTOFF",
            },
        )

    def test_resultados_en_varios_escenarios_son_checkresult(self):
        self.guardrails(holdouts=["data/holdout/**"])
        for kw in (
            {},
            {"sources": ["data/holdout/x.csv", ".env", "", 123]},
            {"decision_scope": "model_valid", "out_dir": "reports/exploratory/r1"},
            {"holdout_access": None},
            {"sensitive_artifacts": ["t1"]},
        ):
            with self.subTest(kw=kw):
                self.assertVocabulario(self.gov(**kw))

    def test_sin_datos_no_es_pass_ni_lista_vacia(self):
        res = self.gov(sources=(), sensitive_artifacts=(), holdout_access=None)
        self.assertVocabulario(res)
        for codigo in (CODE_SENSITIVE_DEST, CODE_SOURCE_ACCESS, CODE_HOLDOUT_SOURCE, CODE_ISOLATION_INPUT, CODE_SCI_CUTOFF):
            (r,) = _solo(res, codigo)
            self.assertEqual(r.status, NA, codigo)
        (acceso,) = _solo(res, CODE_HOLDOUT_ACCESS)
        self.assertEqual(acceso.status, FAIL)  # no declarado != "none"

    def test_resultados_por_elemento_llevan_subject(self):
        res = self.gov(sources=["data/interim/a.csv", "data/interim/b.csv"])
        for codigo in (CODE_SOURCE_ACCESS, CODE_HOLDOUT_SOURCE, CODE_ISOLATION_INPUT):
            self.assertEqual(
                [r.subject for r in _solo(res, codigo)], ["data/interim/a.csv", "data/interim/b.csv"]
            )


# ---------------------------------------------------------------------------
# R3 / R4 / R5 / R6 - policy
# ---------------------------------------------------------------------------


class TestPolicy(_RepoBase):
    def test_defaults_sin_archivo(self):
        p = load_policy(self.repo)
        self.assertIsInstance(p, ReportingPolicy)
        self.assertEqual(p.source, "default")
        self.assertEqual(
            p.destination_roots,
            {"exploratory": "reports/exploratory", "model_valid": "reports/model_valid", "operational": "reports/operational"},
        )
        self.assertEqual(p.sensitive_destination_roots, ())

    def test_override_parcial_y_sensibles(self):
        self.policy_reporting(
            {"destination_roots": {"model_valid": "out/mv"}, "sensitive_destination_roots": ["reports/operational/sens"]}
        )
        p = load_policy(self.repo)
        self.assertEqual(p.destination_roots["model_valid"], "out/mv")
        self.assertEqual(p.destination_roots["exploratory"], "reports/exploratory")
        self.assertEqual(p.destination_roots["operational"], "reports/operational")
        self.assertEqual(p.sensitive_destination_roots, ("reports/operational/sens",))
        self.assertEqual(p.source, ".harmessi/reporting-policy.json")

    def test_campo_desconocido_se_ignora(self):
        self.policy_reporting({"campo_futuro": {"x": 1}})
        self.assertEqual(load_policy(self.repo).source, ".harmessi/reporting-policy.json")

    def test_policy_invalida_levanta(self):
        ruta = ".harmessi/reporting-policy.json"
        casos = {
            "json invalido": lambda: self.escribir(ruta, "{no json"),
            "array": lambda: self.escribir(ruta, "[]"),
            "schema 2": lambda: self.policy_reporting({"schema_version": 2}),
            "schema bool": lambda: self.policy_reporting({"schema_version": True}),
            "schema ausente": lambda: self.escribir(ruta, "{}"),
            "destination_roots lista": lambda: self.policy_reporting({"destination_roots": []}),
            "sensitive str": lambda: self.policy_reporting({"sensitive_destination_roots": "x"}),
            "sensitive lista no str": lambda: self.policy_reporting({"sensitive_destination_roots": [1]}),
            "root numerico": lambda: self.policy_reporting({"destination_roots": {"model_valid": 123}}),
            "clave invalida": lambda: self.policy_reporting({"destination_roots": {"model-valid": "x/y"}}),
        }
        for nombre, preparar in casos.items():
            with self.subTest(nombre):
                preparar()
                with self.assertRaises(ReportingPolicyError):
                    load_policy(self.repo)

    def test_root_fuera_de_forma_canonica_levanta(self):
        for root in ("/abs", "C:/x", "a\\b", "../x", "a/../b", "a//b", "a/", ".", "", "a/*", "a[1]", "a?", "a/./b"):
            with self.subTest(root=root):
                self.policy_reporting({"destination_roots": {"model_valid": root}})
                with self.assertRaises(ReportingPolicyError):
                    load_policy(self.repo)
        for root in ("/abs", "a/", "reports/model_valid/*", ""):
            with self.subTest(sensible=root):
                self.policy_reporting({"sensitive_destination_roots": [root]})
                with self.assertRaises(ReportingPolicyError):
                    load_policy(self.repo)

    def test_roots_iguales_anidados_o_solo_por_mayusculas_levantan(self):
        casos = [
            {"model_valid": "reports/exploratory"},  # igual al default de exploratory
            {"exploratory": "out", "model_valid": "out/mv"},  # anidado
            {"exploratory": "Out", "model_valid": "out/mv"},  # anidado solo por casing
            {"model_valid": "reports/operational/x"},  # anidado en el default de operational
        ]
        for roots in casos:
            with self.subTest(roots=roots):
                self.policy_reporting({"destination_roots": roots})
                with self.assertRaises(ReportingPolicyError):
                    load_policy(self.repo)

    def test_sensitive_root_relacion_con_roots_de_scope(self):
        for invalido in ("reports/model_valid", "otro/sens", "reports/model_valid-x/s", "Reports/Model_Valid"):
            with self.subTest(sensible=invalido):
                self.policy_reporting({"sensitive_destination_roots": [invalido]})
                with self.assertRaises(ReportingPolicyError):
                    load_policy(self.repo)
        self.policy_reporting({"sensitive_destination_roots": ["reports/model_valid/sens"]})
        self.assertEqual(load_policy(self.repo).sensitive_destination_roots, ("reports/model_valid/sens",))

    def test_repo_root_inexistente_o_invalido_levanta(self):
        for repo_root in (self.repo / "no_existe", None, 5, ""):
            with self.subTest(repo_root=repo_root):
                with self.assertRaises(ReportingPolicyError):
                    load_policy(repo_root)

    def test_resolve_output_dir(self):
        p = load_policy(self.repo)
        self.assertEqual(resolve_output_dir(p, "model_valid", "informe-1"), "reports/model_valid/informe-1")
        for scope in DECISION_SCOPES:
            self.assertEqual(resolve_output_dir(p, scope, "r1"), f"reports/{scope}/r1")
        for scope, rid in (("otro", "r1"), ("model_valid", ""), ("model_valid", "a/b"), ("model_valid", "a\\b"),
                           ("model_valid", ".."), ("model_valid", "a..b"), ("model_valid", None), (123, "r1")):
            with self.subTest(scope=scope, rid=rid):
                with self.assertRaises(ReportingPolicyError):
                    resolve_output_dir(p, scope, rid)

    def test_resolve_output_dir_no_crea_nada(self):
        antes = _snapshot(self.repo)
        resolve_output_dir(load_policy(self.repo), "exploratory", "r1")
        self.assertEqual(antes, _snapshot(self.repo))

    def test_pertenencia_estricta_al_root(self):
        casos = {
            "reports/exploratory-x/r1": FAIL,
            "reports/exploratory/r1": PASS,
            "reports/exploratory": FAIL,
        }
        for out_dir, esperado in casos.items():
            with self.subTest(out_dir=out_dir):
                (r,) = _solo(self.dest(out_dir=out_dir), CODE_DEST_SCOPE)
                self.assertEqual(r.status, esperado)


# ---------------------------------------------------------------------------
# R7 - contexto
# ---------------------------------------------------------------------------


class TestContexto(_RepoBase):
    def _reporte(self):
        def tabla(tid, sensible):
            return TableArtifact(table_id=tid, title="T", columns=("grupo", "n"), rows=(("a", 1),), sensitive=sensible)

        def figura(fid, sensible):
            return FigureArtifact(
                figure_id=fid, title="F", spec=FigureSpec(chart_type="bar", x="grupo", y=("n",)),
                backing_table_id=None, sensitive=sensible,
            )

        cap1 = Chapter(
            chapter_id="cap_1", title="C1",
            tables=[tabla("tabla_s1", True), tabla("tabla_p", False)],
            figures=[figura("fig_s", True), figura("fig_p", False)],
        )
        cap2 = Chapter(chapter_id="cap_2", title="C2", tables=[tabla("tabla_s2", True)])
        return Report(
            report_id="rep_1", title="R", report_kind="evaluation", decision_scope="model_valid", chapters=[cap1, cap2]
        )

    def test_context_from_report(self):
        rep = self._reporte()
        ctx = context_from_report(
            self.repo, rep, "reports/model_valid/rep_1", sources=["a.csv"], holdout_access="none",
            data_cutoff="2026-01-01", agent_type="agente_x",
        )
        self.assertEqual((ctx.report_id, ctx.report_kind, ctx.decision_scope), ("rep_1", "evaluation", "model_valid"))
        self.assertEqual(ctx.sensitive_artifacts, ("tabla_s1", "tabla_s2", "fig_s"))
        self.assertEqual(ctx.sources, ("a.csv",))
        self.assertEqual((ctx.holdout_access, ctx.data_cutoff, ctx.agent_type), ("none", "2026-01-01", "agente_x"))
        self.assertEqual(ctx.out_dir, "reports/model_valid/rep_1")

    def test_listas_se_normalizan_a_tupla(self):
        ctx = self.ctx(sources=["a.csv"], sensitive_artifacts=["t1"])
        self.assertEqual(ctx.sources, ("a.csv",))
        self.assertEqual(ctx.sensitive_artifacts, ("t1",))

    def test_defaults_e_inmutabilidad(self):
        ctx = GovernanceContext(self.repo, "r1", "eda", "exploratory", "reports/exploratory/r1")
        self.assertEqual(
            (ctx.sources, ctx.holdout_access, ctx.data_cutoff, ctx.sensitive_artifacts, ctx.agent_type),
            ((), None, None, (), None),
        )
        with self.assertRaises(FrozenInstanceError):
            ctx.out_dir = "otro"

    def test_no_valida_al_construir(self):
        GovernanceContext(None, 1, 2, 3, 4, sources=None)  # no lanza


# ---------------------------------------------------------------------------
# R8 - REPORT-POLICY
# ---------------------------------------------------------------------------


class TestReportPolicy(_RepoBase):
    def test_default_pasa_y_lo_dice(self):
        (r,) = _solo(self.dest(), CODE_POLICY)
        self.assertEqual(r.status, PASS)
        self.assertIn("default", r.message)

    def test_archivo_pasa_y_menciona_la_ruta(self):
        self.policy_reporting({})
        (r,) = _solo(self.dest(), CODE_POLICY)
        self.assertEqual(r.status, PASS)
        self.assertIn(".harmessi/reporting-policy.json", r.message)

    def test_corrupta_devuelve_unico_resultado(self):
        self.escribir(".harmessi/reporting-policy.json", "{corrupto")
        for funcion in (evaluate_governance, evaluate_destination):
            res = funcion(self.ctx(sources=["data/interim/a.csv"]))
            self.assertEqual(len(res), 1)
            self.assertEqual((res[0].code, res[0].status, res[0].kind), (CODE_POLICY, FAIL, "technical_error"))
            self.assertFalse(output_allowed(res))


# ---------------------------------------------------------------------------
# Ciclo reviewer 1/2 - bypass, ancestros, holdout sin patrones, require_codes
# ---------------------------------------------------------------------------


class TestRevisionCiclo1(_RepoBase):
    MANIFEST_EXPLORATORIO = {"report_id": "x", "decision_scope": "exploratory"}

    def _iso(self, flow_scope, entrada):
        res = check_flow_inputs(self.repo, flow_scope, [entrada])
        self.assertEqual(len(res), 1)
        return res[0]

    def _scope_dest(self, **kw):
        res = self.dest(**kw)
        (r,) = [x for x in res if x.code in (CODE_DEST_SCOPE, CODE_DEST_CROSS_SCOPE)]
        return r

    # -- traversal ".." y rutas absolutas --
    def test_traversal_en_out_dir_es_cross_scope(self):
        r = self._scope_dest(decision_scope="exploratory", out_dir="reports/exploratory/../model_valid/r1")
        self.assertEqual((r.code, r.status), (CODE_DEST_CROSS_SCOPE, FAIL))

    def test_traversal_en_input_es_fail(self):
        r = self._iso("model_valid", "reports/model_valid/../exploratory/r1/t.csv")
        self.assertEqual(r.status, FAIL)

    def test_out_dir_absoluto_dentro_del_repo(self):
        absoluto = str(self.repo / "reports" / "exploratory" / "r1")
        self.assertEqual(self._scope_dest(out_dir=absoluto).status, PASS)
        (safe,) = _solo(self.dest(out_dir=absoluto), CODE_DEST_SAFE)
        self.assertEqual(safe.status, PASS)
        cruzado = str(self.repo / "reports" / "model_valid" / "r1")
        self.assertEqual(self._scope_dest(out_dir=cruzado).code, CODE_DEST_CROSS_SCOPE)

    def test_inputs_absolutos_dentro_del_repo(self):
        self.assertEqual(self._iso("model_valid", str(self.repo / "reports" / "exploratory" / "r1" / "t.csv")).status, FAIL)
        self.assertEqual(self._iso("model_valid", str(self.repo / "data" / "interim" / "x.csv")).status, PASS)

    # -- prefijo textual, manifest en la raiz --
    def test_prefijo_textual_no_es_falso_positivo(self):
        for entrada in ("reports/exploratory-x/r1/t.csv", "reports/exploratory-x"):
            with self.subTest(entrada=entrada):
                self.assertEqual(self._iso("model_valid", entrada).status, PASS)

    def test_manifest_exploratorio_en_la_raiz_del_repo(self):
        self.escribir_json("manifest.json", self.MANIFEST_EXPLORATORIO)
        r = self._iso("model_valid", "data/interim/x.csv")
        self.assertEqual(r.status, FAIL)
        self.assertIn("manifest", r.message)

    # -- ancestros del root exploratory y globs --
    def test_input_ancestro_del_root_exploratory_falla(self):
        for entrada in ("reports", "reports/", ".", "", str(self.repo), "reports/exploratory", "REPORTS"):
            with self.subTest(entrada=entrada):
                self.assertEqual(self._iso("model_valid", entrada).status, FAIL)

    def test_ancestro_con_root_custom(self):
        self.policy_reporting({"destination_roots": {"exploratory": "out/exp", "model_valid": "out/mv", "operational": "out/op"}})
        self.assertEqual(self._iso("model_valid", "out").status, FAIL)
        self.assertEqual(self._iso("model_valid", "out/mv/r1/t.csv").status, PASS)

    def test_input_con_glob_es_no_verificable(self):
        for entrada in ("data/*.csv", "data/x?.csv", "data/[a].csv", "reports/exploratory*"):
            with self.subTest(entrada=entrada):
                r = self._iso("model_valid", entrada)
                self.assertEqual(r.status, FAIL)
                self.assertIn("no verificable", r.message)

    def test_root_exploratory_que_es_enlace_se_compara_resuelto(self):
        real = self.repo / "store" / "exp" / "r1"
        real.mkdir(parents=True)
        (self.repo / "reports").mkdir()
        if not _crear_enlace_dir(self.repo / "reports" / "exploratory", self.repo / "store" / "exp"):
            self.skipTest("el SO no permite symlinks ni junctions")
        # Ambas formas resuelven a store/exp/...: solo la comparacion con el root resuelto lo detecta.
        for entrada in ("reports/exploratory/r1/t.csv", "store/exp/r1/t.csv", "store/exp", "store"):
            with self.subTest(entrada=entrada):
                self.assertEqual(self._iso("model_valid", entrada).status, FAIL)
        self.assertEqual(self._iso("model_valid", "store/otro/t.csv").status, PASS)

    # -- HOLDOUT-SOURCE sin patrones --
    def test_holdout_declarado_sin_patrones_falla_y_sin_declarar_es_na(self):
        fuente = "data/interim/a.csv"
        for guardrails in (None, {}, {"holdouts": []}):
            if guardrails is not None:
                self.guardrails(**guardrails)
            with self.subTest(guardrails=guardrails, declarado=True):
                self.policy_cientifica({"holdout": {"declared": True}})
                (r,) = _solo(self.gov(sources=[fuente]), CODE_HOLDOUT_SOURCE)
                self.assertEqual((r.status, r.subject), (FAIL, fuente))
                self.assertIn("SCI-HOLDOUT-PROTECTION", r.message)
            for datos in ({}, {"holdout": {"declared": False}}):
                with self.subTest(guardrails=guardrails, sin_declarar=datos):
                    self.policy_cientifica(datos)
                    (r,) = _solo(self.gov(sources=[fuente]), CODE_HOLDOUT_SOURCE)
                    self.assertEqual(r.status, NA)

    def test_holdout_sin_patrones_con_policy_cientifica_corrupta(self):
        self.escribir(".harmessi/scientific-policy.json", "{corrupto")
        (r,) = _solo(self.gov(sources=["data/interim/a.csv"]), CODE_HOLDOUT_SOURCE)
        self.assertEqual((r.status, r.kind), (FAIL, "technical_error"))

    def test_holdout_con_patrones_declarado_no_cambia(self):
        self.guardrails(holdouts=["data/holdout/**"])
        self.policy_cientifica({"holdout": {"declared": True}})
        (r,) = _solo(self.gov(sources=["data/interim/a.csv"]), CODE_HOLDOUT_SOURCE)
        self.assertEqual(r.status, PASS)

    # -- output_allowed con require_codes --
    def test_output_allowed_require_codes(self):
        def r(status, code):
            return checks.CheckResult(status, code, "m")

        self.assertEqual(REQUIRED_DESTINATION_CODES, (CODE_POLICY, CODE_DEST_SAFE, CODE_DEST_SCOPE))
        completos = [r(PASS, c) for c in REQUIRED_DESTINATION_CODES]
        self.assertTrue(output_allowed(completos, require_codes=REQUIRED_DESTINATION_CODES))
        self.assertFalse(output_allowed(completos[:2], require_codes=REQUIRED_DESTINATION_CODES))
        self.assertFalse(output_allowed([], require_codes=REQUIRED_DESTINATION_CODES))
        self.assertFalse(output_allowed(completos + [r(FAIL, CODE_SENSITIVE_DEST)], require_codes=REQUIRED_DESTINATION_CODES))
        self.assertTrue(output_allowed([], require_codes=()))
        self.assertTrue(output_allowed([]))
        self.assertFalse(output_allowed(None, require_codes=REQUIRED_DESTINATION_CODES))

    def test_output_allowed_require_codes_con_evaluate_destination(self):
        ok = evaluate_destination(self.ctx())
        self.assertTrue(output_allowed(ok, require_codes=REQUIRED_DESTINATION_CODES))
        self.escribir(".harmessi/reporting-policy.json", "{corrupto")
        self.assertFalse(output_allowed(evaluate_destination(self.ctx()), require_codes=REQUIRED_DESTINATION_CODES))

    # -- resolve_output_dir con ids invalidos --
    def test_resolve_output_dir_ids_invalidos(self):
        p = load_policy(self.repo)
        for rid in (".", "con", "a:b", "x\n", "A", "informe 1", "a.b"):
            with self.subTest(rid=rid):
                with self.assertRaises(ReportingPolicyError):
                    resolve_output_dir(p, "exploratory", rid)
        self.assertEqual(resolve_output_dir(p, "exploratory", "informe-1"), "reports/exploratory/informe-1")


# ---------------------------------------------------------------------------
# R9 - REPORT-DEST-SAFE
# ---------------------------------------------------------------------------


class TestDestSafe(_RepoBase):
    def _safe(self, **kw):
        return _solo(self.dest(**kw), CODE_DEST_SAFE)

    def test_limpio_un_pass(self):
        (r,) = self._safe()
        self.assertEqual(r.status, PASS)

    def test_ssh_falla_con_subject_y_motivo(self):
        res = self._safe(out_dir=".ssh/r1")
        self.assertEqual(len(res), 4)
        self.assertTrue(all(r.status == FAIL for r in res))
        self.assertIn(".ssh/r1/report.html", [r.subject for r in res])
        self.assertTrue(all("secreto" in r.message for r in res))

    def test_secretos_extra(self):
        self.guardrails(secretos_extra=["reports/exploratory/secreto_*/report.html"])
        res = self._safe(out_dir="reports/exploratory/secreto_1")
        self.assertEqual([r.status for r in res], [FAIL])
        self.assertEqual(res[0].subject, "reports/exploratory/secreto_1/report.html")

    def test_holdout_nunca_se_escribe_ni_con_excepcion(self):
        self.guardrails(
            holdouts=["data/holdout/**"],
            excepciones=[{"ruta": "data/holdout/r1/report.html", "accion": "read", "vence_utc": FUTURO}],
        )
        res = self._safe(out_dir="data/holdout/r1")
        self.assertTrue(all(r.status == FAIL for r in res))
        self.assertTrue(any("holdout" in r.message for r in res))

    def test_holdout_casefold(self):
        self.guardrails(holdouts=["data/holdout/**"])
        res = self._safe(out_dir="Data/HOLDOUT/r1")
        self.assertTrue(res and all(r.status == FAIL for r in res))

    def test_data_raw(self):
        res = self._safe(out_dir="data/raw/x")
        self.assertTrue(res and all(r.status == FAIL for r in res))
        self.assertTrue(any("data/raw" in r.message for r in res))

    def test_guardrails_corrupto_es_technical_error(self):
        self.escribir(".claude/guardrails.json", "{corrupto")
        (r,) = self._safe()
        self.assertEqual((r.status, r.kind), (FAIL, "technical_error"))

    def test_write_scopes_por_agent_type(self):
        self.guardrails(write_scopes={"agente_a": ["reports/model_valid/**"], "agente_b": ["reports/exploratory/**"]})
        self.assertTrue(all(r.status == FAIL for r in self._safe(agent_type="agente_a")))
        self.assertTrue(any("write_scope" in r.message for r in self._safe(agent_type="agente_a")))
        self.assertTrue(all(r.status == FAIL for r in self._safe(agent_type="agente_sin_scope")))
        (ok,) = self._safe(agent_type="agente_b")
        self.assertEqual(ok.status, PASS)

    def test_out_dir_fuera_del_repo(self):
        with tempfile.TemporaryDirectory() as otro:
            for out_dir in (str(Path(otro) / "x"), "../x_fuera"):
                with self.subTest(out_dir=out_dir):
                    res = self._safe(out_dir=out_dir)
                    self.assertTrue(res and all(r.status == FAIL for r in res))

    def test_out_dir_invalido(self):
        for out_dir in (None, "", "   ", 5):
            with self.subTest(out_dir=out_dir):
                (r,) = self._safe(out_dir=out_dir)
                self.assertEqual(r.status, FAIL)


# ---------------------------------------------------------------------------
# R10 - REPORT-DEST-SCOPE / REPORT-DEST-CROSS-SCOPE
# ---------------------------------------------------------------------------


class TestDestScope(_RepoBase):
    def _destino(self, **kw):
        res = self.dest(**kw)
        candidatos = [r for r in res if r.code in (CODE_DEST_SCOPE, CODE_DEST_CROSS_SCOPE)]
        self.assertEqual(len(candidatos), 1)
        return candidatos[0]

    def test_pass_en_su_root(self):
        for scope in DECISION_SCOPES:
            with self.subTest(scope=scope):
                r = self._destino(decision_scope=scope, out_dir=f"reports/{scope}/r1")
                self.assertEqual((r.code, r.status), (CODE_DEST_SCOPE, PASS))

    def test_cross_scope_en_ambos_sentidos(self):
        for scope, out_dir in (("model_valid", "reports/exploratory/r1"), ("exploratory", "reports/model_valid/r1")):
            with self.subTest(scope=scope):
                r = self._destino(decision_scope=scope, out_dir=out_dir)
                self.assertEqual((r.code, r.status), (CODE_DEST_CROSS_SCOPE, FAIL))
                self.assertIn("otro scope", r.message)

    def test_root_mismo_o_fuera_de_roots(self):
        for out_dir in ("reports/model_valid", "reports", "otro/dir", "."):
            with self.subTest(out_dir=out_dir):
                r = self._destino(decision_scope="model_valid", out_dir=out_dir)
                self.assertEqual((r.code, r.status), (CODE_DEST_SCOPE, FAIL))

    def test_scope_invalido_no_se_infiere(self):
        r = self._destino(decision_scope="invalido", out_dir="reports/exploratory/r1")
        self.assertEqual((r.code, r.status), (CODE_DEST_SCOPE, FAIL))

    def test_policy_custom(self):
        self.policy_reporting({"destination_roots": {"exploratory": "out/exp", "model_valid": "out/mv", "operational": "out/op"}})
        self.assertEqual(self._destino(decision_scope="model_valid", out_dir="out/mv/r1").status, PASS)
        self.assertEqual(self._destino(decision_scope="model_valid", out_dir="reports/model_valid/r1").status, FAIL)
        r = self._destino(decision_scope="model_valid", out_dir="out/exp/r1")
        self.assertEqual((r.code, r.status), (CODE_DEST_CROSS_SCOPE, FAIL))

    def test_casefold(self):
        r = self._destino(out_dir="Reports/EXPLORATORY/r1")
        self.assertEqual((r.code, r.status), (CODE_DEST_SCOPE, PASS))

    def test_symlink_hacia_otro_scope(self):
        real = self.repo / "reports" / "exploratory" / "real"
        real.mkdir(parents=True)
        (self.repo / "reports" / "model_valid").mkdir(parents=True)
        enlace = self.repo / "reports" / "model_valid" / "enlace"
        if not _crear_enlace_dir(enlace, real):
            self.skipTest("el SO no permite symlinks ni junctions")
        r = self._destino(decision_scope="model_valid", out_dir="reports/model_valid/enlace")
        self.assertEqual((r.code, r.status), (CODE_DEST_CROSS_SCOPE, FAIL))

    def test_out_dir_invalido_o_fuera_del_repo(self):
        with tempfile.TemporaryDirectory() as otro:
            for out_dir in (None, "", str(Path(otro) / "x"), "../x_fuera"):
                with self.subTest(out_dir=out_dir):
                    self.assertEqual(self._destino(out_dir=out_dir).status, FAIL)


# ---------------------------------------------------------------------------
# R11 - REPORT-SENSITIVE-DEST
# ---------------------------------------------------------------------------


class TestSensitiveDest(_RepoBase):
    def _sens(self, **kw):
        (r,) = _solo(self.dest(**kw), CODE_SENSITIVE_DEST)
        return r

    def test_sin_sensibles_es_na(self):
        self.assertEqual(self._sens().status, NA)

    def test_sensible_sin_roots_declarados_falla(self):
        r = self._sens(sensitive_artifacts=["tabla_s"])
        self.assertEqual(r.status, FAIL)
        self.assertIn("sensitive_destination_roots", r.message)

    def test_sensible_dentro_y_fuera_del_root_sensible(self):
        self.policy_reporting({"sensitive_destination_roots": ["reports/model_valid/sens"]})
        base = dict(decision_scope="model_valid", sensitive_artifacts=["tabla_s"])
        self.assertEqual(self._sens(out_dir="reports/model_valid/sens/r1", **base).status, PASS)
        self.assertEqual(self._sens(out_dir="reports/model_valid/r1", **base).status, FAIL)
        self.assertEqual(self._sens(out_dir="reports/model_valid/sens", **base).status, FAIL)

    def test_sensibles_mal_formados(self):
        self.assertEqual(self._sens(sensitive_artifacts=None).status, FAIL)


# ---------------------------------------------------------------------------
# R12 - REPORT-SOURCE-ACCESS
# ---------------------------------------------------------------------------


class TestSourceAccess(_RepoBase):
    def _src(self, **kw):
        return _solo(self.gov(**kw), CODE_SOURCE_ACCESS)

    def test_fuentes_limpias_un_pass_por_fuente(self):
        res = self._src(sources=["data/interim/a.csv", "data/interim/b.csv"])
        self.assertEqual([(r.status, r.subject) for r in res], [(PASS, "data/interim/a.csv"), (PASS, "data/interim/b.csv")])

    def test_holdout_sin_excepcion_con_vigente_y_vencida(self):
        fuente = "data/holdout/x.csv"
        self.guardrails(holdouts=["data/holdout/**"])
        self.assertEqual(self._src(sources=[fuente])[0].status, FAIL)
        self.guardrails(holdouts=["data/holdout/**"], excepciones=[{"ruta": fuente, "accion": "read", "vence_utc": FUTURO}])
        self.assertEqual(self._src(sources=[fuente])[0].status, PASS)
        self.guardrails(holdouts=["data/holdout/**"], excepciones=[{"ruta": fuente, "accion": "read", "vence_utc": PASADO}])
        self.assertEqual(self._src(sources=[fuente])[0].status, FAIL)

    def test_secretos(self):
        for fuente in (".env", "datos/clave.pem"):
            with self.subTest(fuente=fuente):
                (r,) = self._src(sources=[fuente])
                self.assertEqual((r.status, r.subject), (FAIL, fuente))

    def test_fuera_del_repo(self):
        with tempfile.TemporaryDirectory() as otro:
            fuente = str(Path(otro) / "a.csv")
            (r,) = self._src(sources=[fuente])
            self.assertEqual(r.status, FAIL)

    def test_sin_fuentes_es_un_na(self):
        (r,) = self._src(sources=())
        self.assertEqual(r.status, NA)

    def test_fuentes_invalidas(self):
        for fuente in ("", 123):
            with self.subTest(fuente=fuente):
                (r,) = self._src(sources=[fuente])
                self.assertEqual(r.status, FAIL)
        self.assertEqual(self._src(sources=None)[0].status, FAIL)

    def test_guardrails_corrupto(self):
        self.escribir(".claude/guardrails.json", "{corrupto")
        (r,) = self._src(sources=["data/interim/a.csv"])
        self.assertEqual((r.status, r.kind), (FAIL, "technical_error"))


# ---------------------------------------------------------------------------
# R13 - REPORT-HOLDOUT-ACCESS
# ---------------------------------------------------------------------------


class TestHoldoutAccess(_RepoBase):
    AUTORIZADA = {"holdout": {"declared": True, "final_evaluation": {"authorized": True, "reason": "evaluacion final aprobada"}}}

    def _acceso(self, **kw):
        (r,) = _solo(self.gov(**kw), CODE_HOLDOUT_ACCESS)
        return r

    def _read(self, **kw):
        base = dict(holdout_access="read", report_kind="evaluation", decision_scope="model_valid", out_dir="reports/model_valid/informe-1")
        base.update(kw)
        return self._acceso(**base)

    def test_declaracion_invalida_falla_y_none_pasa(self):
        for valor in (None, "READ", "write", ""):
            with self.subTest(valor=valor):
                self.assertEqual(self._acceso(holdout_access=valor).status, FAIL)
        self.assertEqual(self._acceso(holdout_access="none").status, PASS)

    def test_read_autorizado_incluye_reason(self):
        self.policy_cientifica(self.AUTORIZADA)
        r = self._read()
        self.assertEqual(r.status, PASS)
        self.assertIn("evaluacion final aprobada", r.message)

    def test_read_autorizado_sin_reason(self):
        self.policy_cientifica({"holdout": {"declared": True, "final_evaluation": {"authorized": True}}})
        self.assertEqual(self._read().status, PASS)

    def test_read_no_autorizado_en_cada_caso(self):
        self.policy_cientifica(self.AUTORIZADA)
        self.assertEqual(self._read(report_kind="eda").status, FAIL)
        self.assertEqual(self._read(decision_scope="exploratory", out_dir="reports/exploratory/informe-1").status, FAIL)
        self.assertEqual(self._read(decision_scope="invalido").status, FAIL)
        casos = {
            "sin holdout": {},
            "sin final_evaluation": {"holdout": {"declared": True}},
            "authorized false": {"holdout": {"declared": True, "final_evaluation": {"authorized": False}}},
            "declared false": {"holdout": {"declared": False, "final_evaluation": {"authorized": True}}},
            "authorized string": {"holdout": {"declared": True, "final_evaluation": {"authorized": "true"}}},
        }
        for nombre, datos in casos.items():
            with self.subTest(nombre):
                self.policy_cientifica(datos)
                self.assertEqual(self._read().status, FAIL)

    def test_read_sin_policy_cientifica_falla(self):
        self.assertEqual(self._read().status, FAIL)

    def test_policy_cientifica_corrupta_es_technical_error(self):
        self.escribir(".harmessi/scientific-policy.json", "{corrupto")
        r = self._read()
        self.assertEqual((r.status, r.kind), (FAIL, "technical_error"))


# ---------------------------------------------------------------------------
# R14 - REPORT-HOLDOUT-SOURCE
# ---------------------------------------------------------------------------


class TestHoldoutSource(_RepoBase):
    FUENTE = "data/holdout/x.csv"
    AUTORIZADA = TestHoldoutAccess.AUTORIZADA

    def setUp(self):
        super().setUp()
        self.guardrails(holdouts=["data/holdout/**"])

    def _hs(self, **kw):
        return _solo(self.gov(**kw), CODE_HOLDOUT_SOURCE)

    def _read(self, **kw):
        base = dict(
            sources=[self.FUENTE], holdout_access="read", report_kind="evaluation",
            decision_scope="model_valid", out_dir="reports/model_valid/informe-1",
        )
        base.update(kw)
        return self._hs(**base)

    def test_contradiccion_con_none_o_sin_declarar(self):
        for acceso in ("none", None):
            with self.subTest(acceso=acceso):
                (r,) = self._hs(sources=[self.FUENTE], holdout_access=acceso)
                self.assertEqual((r.status, r.subject), (FAIL, self.FUENTE))

    def test_read_autorizado_pasa_con_nota_y_no_autorizado_falla(self):
        self.guardrails(
            holdouts=["data/holdout/**"],
            excepciones=[{"ruta": self.FUENTE, "accion": "read", "vence_utc": FUTURO}],
        )
        self.policy_cientifica(self.AUTORIZADA)
        (r,) = self._read()
        self.assertEqual(r.status, PASS)
        self.assertIn("autorizado", r.message)
        (r,) = self._read(report_kind="eda")
        self.assertEqual(r.status, FAIL)

    def test_read_sin_policy_cientifica_falla(self):
        (r,) = self._read()
        self.assertEqual(r.status, FAIL)

    def test_read_con_policy_cientifica_corrupta(self):
        self.escribir(".harmessi/scientific-policy.json", "{corrupto")
        (r,) = self._read()
        self.assertEqual((r.status, r.kind), (FAIL, "technical_error"))

    def test_fuera_de_holdout_pasa_fuera_del_repo_na_sin_fuentes_na(self):
        (r,) = self._hs(sources=["data/interim/a.csv"])
        self.assertEqual(r.status, PASS)
        with tempfile.TemporaryDirectory() as otro:
            (r,) = self._hs(sources=[str(Path(otro) / "a.csv")])
            self.assertEqual(r.status, NA)
        (r,) = self._hs(sources=())
        self.assertEqual(r.status, NA)

    def test_guardrails_corrupto(self):
        self.escribir(".claude/guardrails.json", "{corrupto")
        (r,) = self._hs(sources=["data/interim/a.csv"])
        self.assertEqual((r.status, r.kind), (FAIL, "technical_error"))

    def test_paridad_con_pathguard_read(self):
        """La decision 'matchea holdout' coincide con la de `pathguard` (guarda contra deriva)."""
        self.guardrails(holdouts=["Data/Holdout/**"])
        config = pathguard.cargar_config(self.repo)
        rutas = [
            "data/holdout/a.csv", "DATA/Holdout/a.csv", "data/HOLDOUT/sub/dir/b.parquet", "Data/Holdout/x/y/z.txt",
            "data/holdout", "data/holdout-x/a.csv", "data/interim/a.csv", "Data/Interim/holdout/a.csv",
            "otro/data/holdout/a.csv", "data/holdout/../interim/a.csv",
        ]
        bloqueadas = 0
        for ruta in rutas:
            with self.subTest(ruta=ruta):
                permitido, _ = pathguard.evaluar_tool_call(
                    {"tool_name": "Read", "tool_input": {"file_path": ruta}}, config, self.repo
                )
                (r,) = self._hs(sources=[ruta], holdout_access="none")
                self.assertEqual(r.status == FAIL, not permitido)
                bloqueadas += 0 if permitido else 1
        self.assertGreater(bloqueadas, 0)
        self.assertLess(bloqueadas, len(rutas))


# ---------------------------------------------------------------------------
# R15 - REPORT-ISOLATION-INPUT
# ---------------------------------------------------------------------------


class TestIsolationInput(_RepoBase):
    MANIFEST_EXPLORATORIO = {"report_id": "x", "decision_scope": "exploratory"}

    def _una(self, flow_scope, entrada):
        res = check_flow_inputs(self.repo, flow_scope, [entrada])
        self.assertEqual(len(res), 1)
        return res[0]

    def test_flujo_exploratorio_es_na(self):
        r = self._una("exploratory", "reports/exploratory/r1/artifacts/t.csv")
        self.assertEqual((r.code, r.status), (CODE_ISOLATION_INPUT, NA))

    def test_input_bajo_root_exploratory(self):
        for flow in ("model_valid", "operational"):
            with self.subTest(flow=flow):
                r = self._una(flow, "reports/exploratory/r1/artifacts/t.csv")
                self.assertEqual((r.status, r.subject), (FAIL, "reports/exploratory/r1/artifacts/t.csv"))

    def test_root_exploratory_custom(self):
        self.policy_reporting({"destination_roots": {"exploratory": "out/exp", "model_valid": "out/mv", "operational": "out/op"}})
        self.assertEqual(self._una("model_valid", "out/exp/r1/t.csv").status, FAIL)
        self.assertEqual(self._una("model_valid", "reports/exploratory/r1/t.csv").status, PASS)

    def test_casing_distinto(self):
        self.assertEqual(self._una("model_valid", "Reports/Exploratory/x").status, FAIL)

    def test_manifest_ancestro_exploratorio(self):
        self.escribir_json("otros/informe_x/manifest.json", self.MANIFEST_EXPLORATORIO)
        r = self._una("model_valid", "otros/informe_x/artifacts/t.csv")
        self.assertEqual(r.status, FAIL)
        self.assertIn("manifest", r.message)

    def test_input_es_el_directorio_del_reporte_exploratorio(self):
        self.escribir_json("otros/informe_x/manifest.json", self.MANIFEST_EXPLORATORIO)
        self.assertEqual(self._una("operational", "otros/informe_x").status, FAIL)

    def test_manifest_de_otro_scope_ajeno_ilegible_o_no_json_se_ignora(self):
        casos = {
            "model_valid": lambda p: p.write_text(json.dumps({"report_id": "x", "decision_scope": "model_valid"}), encoding="utf-8"),
            "ajeno": lambda p: p.write_text(json.dumps({"name": "x"}), encoding="utf-8"),
            "no json": lambda p: p.write_text("esto no es json", encoding="utf-8"),
            "ilegible": lambda p: p.write_bytes(b"\xff\xfe\x00\x81"),
            "array": lambda p: p.write_text("[]", encoding="utf-8"),
            "sin decision_scope": lambda p: p.write_text(json.dumps({"report_id": "x"}), encoding="utf-8"),
        }
        for nombre, escribir in casos.items():
            with self.subTest(nombre):
                ruta = self.escribir("otros/informe_y/manifest.json")
                escribir(ruta)
                self.assertEqual(self._una("model_valid", "otros/informe_y/artifacts/t.csv").status, PASS)

    def test_manifest_denegado_por_pathguard_no_se_abre(self):
        self.guardrails(holdouts=["data/holdout/**"])
        self.escribir_json("data/holdout/r1/manifest.json", self.MANIFEST_EXPLORATORIO)
        # Si se hubiera abierto, seria FAIL; PASS demuestra que no se leyo.
        self.assertEqual(self._una("model_valid", "data/holdout/r1/x.csv").status, PASS)

    def test_input_limpio_pasa(self):
        r = self._una("model_valid", "data/interim/x.parquet")
        self.assertEqual((r.status, r.subject), (PASS, "data/interim/x.parquet"))

    def test_inputs_no_verificables_fallan(self):
        with tempfile.TemporaryDirectory() as otro:
            for entrada in (str(Path(otro) / "x.csv"), "", "../fuera.csv", None, 5):
                with self.subTest(entrada=entrada):
                    self.assertEqual(self._una("model_valid", entrada).status, FAIL)

    def test_flow_scope_invalido_falla(self):
        res = check_flow_inputs(self.repo, "otro", ["data/interim/x.csv"])
        self.assertEqual([r.status for r in res], [FAIL])

    def test_sin_inputs_es_na(self):
        res = check_flow_inputs(self.repo, "model_valid", ())
        self.assertEqual([r.status for r in res], [NA])

    def test_un_resultado_por_input_en_orden(self):
        res = check_flow_inputs(self.repo, "model_valid", ["data/interim/a.csv", "reports/exploratory/r1/t.csv", "data/interim/b.csv"])
        self.assertEqual([(r.subject, r.status) for r in res], [
            ("data/interim/a.csv", PASS), ("reports/exploratory/r1/t.csv", FAIL), ("data/interim/b.csv", PASS),
        ])

    def test_policy_corrupta_es_technical_error(self):
        self.escribir(".harmessi/reporting-policy.json", "{corrupto")
        res = check_flow_inputs(self.repo, "model_valid", ["data/interim/a.csv"])
        self.assertEqual([(r.code, r.status, r.kind) for r in res], [(CODE_POLICY, FAIL, "technical_error")])

    def test_guardrails_corrupto_es_technical_error(self):
        self.escribir(".claude/guardrails.json", "{corrupto")
        (r,) = check_flow_inputs(self.repo, "model_valid", ["data/interim/a.csv"])
        self.assertEqual((r.code, r.status, r.kind), (CODE_ISOLATION_INPUT, FAIL, "technical_error"))


# ---------------------------------------------------------------------------
# R16 - REPORT-SCI-CUTOFF
# ---------------------------------------------------------------------------


class TestSciCutoff(_RepoBase):
    TEMPORAL = {"temporal": {"declared": True, "cutoff_utc": "2026-01-01T00:00:00Z"}}
    VALORES = (None, "2025-12-31", "2026-01-01", "2026-01-02", "2026-01-01T00:00:00Z", "2026-01-01T00:00:01Z")

    def _cutoff(self, scope, data_cutoff):
        res = self.gov(decision_scope=scope, out_dir=f"reports/{scope}/informe-1", data_cutoff=data_cutoff)
        (r,) = _solo(res, CODE_SCI_CUTOFF)
        return r

    def test_model_valid_y_operational(self):
        self.policy_cientifica(self.TEMPORAL)
        esperado = dict(zip(self.VALORES, (FAIL, PASS, PASS, FAIL, PASS, FAIL)))
        for scope in ("model_valid", "operational"):
            for valor in self.VALORES:
                with self.subTest(scope=scope, valor=valor):
                    self.assertEqual(self._cutoff(scope, valor).status, esperado[valor])

    def test_ausente_vacio_es_fail_en_model_valid(self):
        self.policy_cientifica(self.TEMPORAL)
        self.assertEqual(self._cutoff("model_valid", "").status, FAIL)

    def test_exploratory(self):
        self.policy_cientifica(self.TEMPORAL)
        esperado = dict(zip(self.VALORES, (WARN, PASS, PASS, WARN, PASS, WARN)))
        for valor in self.VALORES:
            with self.subTest(valor=valor):
                r = self._cutoff("exploratory", valor)
                self.assertEqual(r.status, esperado[valor])
                if valor in ("2026-01-02", "2026-01-01T00:00:01Z"):
                    self.assertIn("NO debe alimentar model_valid", r.message)

    def test_formato_invalido_falla_en_todo_scope(self):
        self.policy_cientifica(self.TEMPORAL)
        for scope in DECISION_SCOPES:
            for valor in ("01/01/2026", "2026-13-40", "2026-1-1T0:0", 20260101):
                with self.subTest(scope=scope, valor=valor):
                    self.assertEqual(self._cutoff(scope, valor).status, FAIL)

    def test_sin_temporal_es_na_en_los_tres_scopes(self):
        for preparar in (
            lambda: None,  # sin archivo
            lambda: self.policy_cientifica({}),
            lambda: self.policy_cientifica({"temporal": {"declared": False, "cutoff_utc": "2026-01-01T00:00:00Z"}}),
        ):
            preparar()
            for scope in DECISION_SCOPES:
                with self.subTest(scope=scope):
                    self.assertEqual(self._cutoff(scope, "2030-01-01").status, NA)

    def test_declarado_sin_cutoff_es_warn_e_invalido_es_fail(self):
        self.policy_cientifica({"temporal": {"declared": True}})
        self.assertEqual(self._cutoff("model_valid", "2025-01-01").status, WARN)
        self.policy_cientifica({"temporal": {"declared": True, "cutoff_utc": "01/01/2026"}})
        self.assertEqual(self._cutoff("model_valid", "2025-01-01").status, FAIL)

    def test_policy_cientifica_corrupta(self):
        self.escribir(".harmessi/scientific-policy.json", "{corrupto")
        r = self._cutoff("model_valid", "2025-01-01")
        self.assertEqual((r.status, r.kind), (FAIL, "technical_error"))
        self.assertIn("SCI-POLICY", r.message)

    def test_scope_invalido_falla(self):
        self.policy_cientifica(self.TEMPORAL)
        res = self.gov(decision_scope="invalido", data_cutoff="2025-01-01")
        (r,) = _solo(res, CODE_SCI_CUTOFF)
        self.assertEqual(r.status, FAIL)


# ---------------------------------------------------------------------------
# R17 - agregador / output guard
# ---------------------------------------------------------------------------


class TestAgregador(_RepoBase):
    def test_contexto_valido_es_permitido(self):
        res = self.gov(sources=["data/interim/a.csv"])
        self.assertNotIn(FAIL, [r.status for r in res])
        self.assertTrue(output_allowed(res))

    def test_output_allowed(self):
        def r(status):
            return checks.CheckResult(status, "REPORT-POLICY", "m")

        self.assertTrue(output_allowed([]))
        self.assertTrue(output_allowed([r(PASS), r(WARN), r(NA)]))
        self.assertFalse(output_allowed([r(PASS), r(FAIL), r(NA)]))
        self.assertFalse(output_allowed([r(FAIL)]))

    def test_un_solo_fail_bloquea(self):
        self.assertFalse(output_allowed(self.gov(holdout_access=None)))

    def test_orden_de_codigos(self):
        res = self.gov(sources=["data/interim/a.csv", "data/interim/b.csv"])
        self.assertEqual(
            [r.code for r in res],
            [
                "REPORT-POLICY", "REPORT-DEST-SAFE", "REPORT-DEST-SCOPE", "REPORT-SENSITIVE-DEST",
                "REPORT-SOURCE-ACCESS", "REPORT-SOURCE-ACCESS", "REPORT-HOLDOUT-ACCESS",
                "REPORT-HOLDOUT-SOURCE", "REPORT-HOLDOUT-SOURCE",
                "REPORT-ISOLATION-INPUT", "REPORT-ISOLATION-INPUT", "REPORT-SCI-CUTOFF",
            ],
        )
        self.assertEqual(
            [r.subject for r in _solo(res, CODE_SOURCE_ACCESS)], ["data/interim/a.csv", "data/interim/b.csv"]
        )

    def test_evaluate_destination_solo_los_cuatro_primeros(self):
        res = self.dest(sources=["data/interim/a.csv"], data_cutoff="2030-01-01")
        self.assertEqual(
            [r.code for r in res],
            ["REPORT-POLICY", "REPORT-DEST-SAFE", "REPORT-DEST-SCOPE", "REPORT-SENSITIVE-DEST"],
        )

    def test_cross_scope_en_el_agregador_es_cross_code(self):
        res = self.gov(decision_scope="model_valid", out_dir="reports/exploratory/r1")
        self.assertIn(CODE_DEST_CROSS_SCOPE, [r.code for r in res])
        self.assertFalse(output_allowed(res))

    def test_aislamiento_via_fuentes(self):
        fuente = "reports/exploratory/r1/artifacts/t.csv"
        res = self.gov(decision_scope="model_valid", out_dir="reports/model_valid/informe-1", sources=[fuente])
        self.assertEqual([r.status for r in _solo(res, CODE_ISOLATION_INPUT)], [FAIL])
        res = self.gov(decision_scope="exploratory", sources=[fuente])
        self.assertEqual([r.status for r in _solo(res, CODE_ISOLATION_INPUT)], [NA])

    def test_guardrails_corrupto_no_lanza_y_marca_dest_safe(self):
        self.escribir(".claude/guardrails.json", "{corrupto")
        res = self.gov(sources=["data/interim/a.csv"])
        (safe,) = _solo(res, CODE_DEST_SAFE)
        self.assertEqual((safe.status, safe.kind), (FAIL, "technical_error"))
        self.assertFalse(output_allowed(res))

    def test_excepcion_inesperada_de_un_check_se_convierte_en_resultado(self):
        original = governance._check_sci_cutoff
        governance._check_sci_cutoff = lambda *a, **k: 1 / 0
        try:
            res = self.gov()
        finally:
            governance._check_sci_cutoff = original
        # el registro ya captura la referencia en tiempo de llamada: debe ser un resultado -EXCEPCION
        excepciones = [r for r in res if r.code.endswith("-EXCEPCION")]
        self.assertEqual(len(excepciones), 1)
        self.assertEqual((excepciones[0].status, excepciones[0].kind), (FAIL, "technical_error"))


if __name__ == "__main__":
    unittest.main()

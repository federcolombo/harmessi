"""Tests de `tools/reporting/profiles/eda.py` (v0.6 Change 2, `20260918-eda-profile`).

Deterministas: sin red, sin aleatoriedad, sin pandas. Fixtures 100% genéricos
(registros sintéticos). Las declaraciones corruptas se fabrican editando el
`to_dict()` de un reporte válido y reconstruyéndolo con `Report.from_dict`.
"""
from __future__ import annotations

import ast
import copy
import inspect
import sys
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest import mock

# `dsguard` vive en `tools/`: se agrega explícitamente, sin depender del efecto de `eda`.
_TOOLS_DIR = Path(__file__).resolve().parents[2]
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from dsguard import checks  # noqa: E402
from tools.reporting.profiles import eda  # noqa: E402
from tools.reporting.core import (  # noqa: E402
    Chapter,
    Insight,
    Report,
    ReportingContractError,
    TableArtifact,
)

PASS, WARN, FAIL, NA = checks.STATUS_PASS, checks.STATUS_WARN, checks.STATUS_FAIL, checks.STATUS_NA
TODOS = tuple(i.block_id for i in eda.BLOCK_CATALOG)

CATALOGO_ESPERADO = {
    "data_quality": ("missingness", "duplicates_and_keys", "type_and_domain_validity",
                     "outlier_screening"),
    "univariate": ("distribution_summary", "dispersion_and_shape", "categorical_frequency"),
    "bivariate_target": ("association_measure", "group_contrast", "rate_by_group"),
    "multivariate": ("correlation_structure", "dimensionality_reduction", "interaction_screening"),
    "temporal": ("trend", "seasonality_or_periodicity", "regime_change", "cohort_like"),
    "concentration": ("top_share", "inequality_index", "long_tail"),
    "segmentation": ("unsupervised_grouping", "rule_based_segments", "profile_contrast"),
    "entity_relations": ("cardinality_and_keys", "join_integrity", "graph_structure"),
    "process_cycles": ("duration_and_latency", "state_transitions", "stage_flow"),
    "leakage_review": ("temporal_availability", "post_outcome_fields", "snapshot_vs_event",
                       "target_proxy_screening"),
    "population_and_unit": ("unit_of_analysis", "inclusion_exclusion", "denominator_definition",
                            "coverage_over_time"),
}


# --- Fixtures -------------------------------------------------------------------


def _razon(bloque: str) -> str:
    return f"no se realiza este bloque porque {bloque} excede el alcance acordado"


def _insight(bloque: str) -> Insight:
    return Insight(
        insight_id=f"ins_{bloque}",
        technical_claim="hallazgo técnico sintético",
        business_claim="lectura de negocio sintética",
        evidence_refs=(),
        population="registros sintéticos",
        time_scope="período sintético",
        claim_type="descriptive",
    )


def _capitulo(bloque: str, con_insight: bool = True) -> Chapter:
    return Chapter(
        chapter_id=f"cap_{bloque}",
        title=f"Capítulo {bloque}",
        insights=(_insight(bloque),) if con_insight else (),
        metadata={"eda_block": bloque},
    )


def _evaluaciones(aplicables=("data_quality",), na=(), extra=()):
    evs = []
    for bloque in TODOS:
        if bloque in aplicables:
            evs.append(eda.BlockEvaluation(bloque, "applicable"))
        elif bloque in na:
            evs.append(eda.BlockEvaluation(bloque, "not_applicable", _razon(bloque)))
        else:
            evs.append(eda.BlockEvaluation(bloque, "omitted", _razon(bloque)))
    evs.extend(extra)
    return evs


def _reporte(aplicables=("data_quality",), na=(), scope="exploratory", target="resultado",
             time_column="fecha_evento", extra_evals=(), extra_chapters=(), policy=None,
             metadata=None):
    capitulos = [_capitulo(b) for b in aplicables] + list(extra_chapters)
    return eda.build_eda_report(
        "reporte_prueba", "Reporte de prueba", scope, capitulos,
        _evaluaciones(aplicables, na, extra_evals),
        target=target, time_column=time_column, scientific_policy=policy, metadata=metadata,
    )


def _editar(reporte: Report, fn) -> Report:
    """Copia editable: `fn` muta el dict serializado; se reconstruye el Report."""
    datos = reporte.to_dict()
    fn(datos)
    return Report.from_dict(datos)


def _apl(reporte: Report, bloque: str, **cambios) -> Report:
    def _fn(d):
        d["metadata"]["eda"]["applicability"][bloque].update(cambios)
    return _editar(reporte, _fn)


def _de_codigo(resultados, codigo):
    return [r for r in resultados if r.code == codigo]


def _estatus(resultados, codigo):
    return [r.status for r in resultados if r.code == codigo]


def _validar(reporte, **kw):
    return eda.validate_eda_report(reporte, **kw)


def _sin_error_tecnico(test, resultados):
    """Ningún resultado proviene de una excepción interna capturada."""
    test.assertIsInstance(resultados, list)
    test.assertTrue(resultados)
    for r in resultados:
        test.assertFalse(r.code.endswith("-EXCEPCION"), r)
        test.assertNotEqual(r.kind, checks.KIND_TECHNICAL_ERROR, r)


# --- R1 ---------------------------------------------------------------------------


class TestR1PaqueteEImports(unittest.TestCase):
    def test_init_vacio(self):
        init = Path(eda.__file__).with_name("__init__.py")
        self.assertEqual(init.read_text(encoding="utf-8").strip(), "")

    def test_imports_permitidos(self):
        arbol = ast.parse(Path(eda.__file__).read_text(encoding="utf-8"))
        modulos = []
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Import):
                modulos += [a.name for a in nodo.names]
            elif isinstance(nodo, ast.ImportFrom):
                modulos.append(("." * nodo.level) + (nodo.module or ""))
                modulos += [a.name for a in nodo.names]
        texto = " ".join(modulos).lower()
        for prohibido in ("governance", "pandas", "plotly", "html", "numpy"):
            self.assertNotIn(prohibido, texto)

    def test_core_no_importa_profiles(self):
        core_py = Path(eda.__file__).parents[1] / "core.py"
        arbol = ast.parse(core_py.read_text(encoding="utf-8"))
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.ImportFrom):
                # `from .profiles import x`, `from tools.reporting.profiles import x`
                # y `from . import profiles`.
                textos = [nodo.module or ""] + [a.name for a in nodo.names]
            elif isinstance(nodo, ast.Import):
                textos = [a.name for a in nodo.names]  # `import tools.reporting.profiles`
            else:
                continue
            for texto in textos:
                self.assertNotIn("profiles", texto)

    def test_detector_de_imports_es_capaz_de_fallar(self):
        # Autocontrol: las formas prohibidas sí contienen "profiles" en module/names.
        for codigo in ("from . import profiles", "import tools.reporting.profiles",
                       "from .profiles import eda"):
            nodo = ast.parse(codigo).body[0]
            textos = ([nodo.module or ""] + [a.name for a in nodo.names]
                      if isinstance(nodo, ast.ImportFrom) else [a.name for a in nodo.names])
            self.assertTrue(any("profiles" in t for t in textos), codigo)


# --- R2 ---------------------------------------------------------------------------


class TestR2Catalogo(unittest.TestCase):
    def test_bloques_orden_y_familias_exactos(self):
        self.assertEqual(tuple(i.block_id for i in eda.BLOCK_CATALOG), tuple(CATALOGO_ESPERADO))
        for info in eda.BLOCK_CATALOG:
            self.assertEqual(info.families, CATALOGO_ESPERADO[info.block_id])
            self.assertTrue(info.question)

    def test_requires_solo_donde_corresponde(self):
        con_target = [i.block_id for i in eda.BLOCK_CATALOG if i.requires_target]
        con_tiempo = [i.block_id for i in eda.BLOCK_CATALOG if i.requires_time]
        self.assertEqual(con_target, ["bivariate_target"])
        self.assertEqual(con_tiempo, ["temporal"])

    def test_sin_tecnicas_concretas(self):
        texto = " ".join(i.question + " ".join(i.families) for i in eda.BLOCK_CATALOG).lower()
        for tecnica in ("pca", "kmeans", "rfm", "pareto", "bootstrap", "chi_square", "chi-cuadrado"):
            self.assertNotIn(tecnica, texto)

    def test_extension_x_valida_si_cumple_contrato(self):
        rep = _reporte(
            extra_evals=(eda.BlockEvaluation("x_dominio", "applicable"),),
            extra_chapters=(_capitulo("x_dominio"),),
        )
        res = _validar(rep)
        self.assertEqual([r for r in res if r.status == FAIL], [])

    def test_extension_x_aplicada_sin_insight_falla(self):
        rep = _reporte(
            extra_evals=(eda.BlockEvaluation("x_dominio", "applicable"),),
            extra_chapters=(_capitulo("x_dominio", con_insight=False),),
        )
        res = _validar(rep)
        self.assertIn(FAIL, _estatus(res, "EDA-BLOCK-NO-INSIGHT"))

    def test_extension_x_omitida_exige_razon(self):
        rep = _reporte(extra_evals=(eda.BlockEvaluation("x_dominio", "omitted", "corta"),))
        self.assertIn(FAIL, _estatus(_validar(rep), "EDA-BLOCK-REASON"))

    def test_extension_x_nunca_es_auto(self):
        rep = _reporte(extra_evals=(
            eda.BlockEvaluation("x_dominio", "not_applicable", _razon("x_dominio"), "", True),
        ))
        self.assertIn(FAIL, _estatus(_validar(rep), "EDA-AUTO-INVALID"))


# --- R3 ---------------------------------------------------------------------------


class TestR3Estados(unittest.TestCase):
    def test_states_exactos_sin_partial(self):
        self.assertEqual(eda.STATES, ("applicable", "not_applicable", "omitted"))
        self.assertNotIn("partial", eda.STATES)

    def test_defaults_y_frozen(self):
        ev = eda.BlockEvaluation("univariate", "applicable")
        self.assertEqual((ev.reason, ev.limitations, ev.auto), ("", "", False))
        with self.assertRaises(FrozenInstanceError):
            ev.state = "omitted"  # type: ignore[misc]

    def test_tipos_invalidos_lanzan(self):
        casos = [
            dict(block=5, state="applicable"),
            dict(block="", state="applicable"),
            dict(block="univariate", state=None),
            dict(block="univariate", state="applicable", reason=None),
            dict(block="univariate", state="applicable", limitations=3),
            dict(block="univariate", state="applicable", auto="si"),
            dict(block="univariate", state="applicable", auto=1),
        ]
        for kw in casos:
            with self.subTest(kw=kw), self.assertRaises(ReportingContractError):
                eda.BlockEvaluation(**kw)

    def test_limitations_no_cambia_estado(self):
        rep = _reporte()
        rep2 = _apl(rep, "data_quality", limitations="cobertura parcial de columnas")
        self.assertEqual(
            [r for r in _validar(rep2) if r.code != "EDA-COVERAGE-TABLE" and r.status == FAIL], []
        )


# --- R4 ---------------------------------------------------------------------------


class TestR4Autoderivacion(unittest.TestCase):
    def test_firma(self):
        params = inspect.signature(eda.derive_evaluations).parameters
        self.assertEqual(list(params), ["target", "time_column", "evaluations", "scientific_policy"])
        self.assertEqual(params["scientific_policy"].kind, inspect.Parameter.KEYWORD_ONLY)
        self.assertIsNone(params["scientific_policy"].default)

    def test_sin_target_autoderiva_incluso_si_usuario_declaro_otro(self):
        evs = [eda.BlockEvaluation("bivariate_target", "omitted", "razón previa", "nota")]
        res = eda.derive_evaluations(None, "fecha_evento", evs)
        ev = {e.block: e for e in res}["bivariate_target"]
        self.assertEqual(ev.state, "not_applicable")
        self.assertTrue(ev.auto)
        self.assertEqual(ev.reason, "estructuralmente no aplicable: sin target declarado")
        self.assertEqual(ev.limitations, "nota")

    def test_sin_tiempo_autoderiva(self):
        res = eda.derive_evaluations("resultado", None, [])
        ev = {e.block: e for e in res}["temporal"]
        self.assertEqual((ev.state, ev.auto), ("not_applicable", True))
        self.assertEqual(ev.reason, "estructuralmente no aplicable: sin columna temporal declarada")

    def test_politica_con_date_column_evita_autoderivacion(self):
        politica = {"temporal": {"date_column": "fecha_evento"}}
        res = eda.derive_evaluations("resultado", None, [], scientific_policy=politica)
        self.assertNotIn("temporal", [e.block for e in res])
        for basura in ("texto", {"temporal": 5}, {"temporal": {"date_column": ""}}, {}):
            res = eda.derive_evaluations("resultado", None, [], scientific_policy=basura)
            self.assertIn("temporal", [e.block for e in res])

    def test_con_precondicion_conserva_auto_recibido(self):
        recibido = eda.BlockEvaluation("bivariate_target", "not_applicable", "x", "", True)
        res = eda.derive_evaluations("resultado", "fecha_evento", [recibido])
        self.assertEqual(res, (recibido,))

    def test_no_completa_bloques_ausentes_y_ordena(self):
        evs = [eda.BlockEvaluation("x_b", "applicable"), eda.BlockEvaluation("x_a", "applicable"),
               eda.BlockEvaluation("univariate", "applicable")]
        res = eda.derive_evaluations("resultado", "fecha_evento", evs)
        self.assertIsInstance(res, tuple)
        self.assertEqual([e.block for e in res], ["univariate", "x_a", "x_b"])

    def test_bloque_duplicado_o_tipo_invalido_lanza(self):
        ev = eda.BlockEvaluation("univariate", "applicable")
        with self.assertRaises(ReportingContractError):
            eda.derive_evaluations("t", "f", [ev, ev])
        with self.assertRaises(ReportingContractError):
            eda.derive_evaluations("t", "f", ["univariate"])
        with self.assertRaises(ReportingContractError):
            eda.derive_evaluations("t", "f", "univariate")

    def test_validador_recompone_bloque_autoderivado_valido(self):
        res = _validar(_reporte(target=None, time_column=None))
        self.assertEqual([r for r in res if r.status == FAIL], [])
        self.assertEqual(_estatus(res, "EDA-AUTO-INVALID"), [PASS])


# --- R5 ---------------------------------------------------------------------------


class TestR5Declaracion(unittest.TestCase):
    def test_metadata_eda_exacta(self):
        rep = _reporte(target="resultado", time_column="fecha_evento")
        decl = rep.metadata["eda"]
        self.assertEqual(set(decl), {"profile", "profile_version", "target", "time_column",
                                     "applicability"})
        self.assertEqual((decl["profile"], decl["profile_version"]), ("eda", 1))
        self.assertEqual((decl["target"], decl["time_column"]), ("resultado", "fecha_evento"))
        self.assertEqual(set(decl["applicability"]), set(TODOS))
        for entrada in decl["applicability"].values():
            self.assertEqual(set(entrada), {"state", "reason", "limitations", "auto"})
            self.assertIsInstance(entrada["auto"], bool)

    def test_target_y_tiempo_null(self):
        decl = _reporte(target=None, time_column=None).metadata["eda"]
        self.assertIsNone(decl["target"])
        self.assertIsNone(decl["time_column"])

    def test_capitulo_lleva_eda_block(self):
        rep = _reporte(aplicables=("data_quality", "univariate"))
        self.assertEqual(rep.chapters[1].metadata["eda_block"], "data_quality")
        self.assertEqual(rep.chapters[2].metadata["eda_block"], "univariate")


# --- R6 ---------------------------------------------------------------------------


class TestR6Cobertura(unittest.TestCase):
    def test_tabla_exacta(self):
        evs = eda.derive_evaluations("resultado", "fecha_evento", _evaluaciones(
            extra=(eda.BlockEvaluation("x_b", "applicable", "", "lim b"),
                   eda.BlockEvaluation("x_a", "applicable"))))
        tabla = eda.coverage_table(evs, "model_valid")
        self.assertEqual(tabla.table_id, "eda_coverage")
        self.assertEqual(tabla.columns, ("block", "state", "reason", "limitations"))
        self.assertEqual([f[0] for f in tabla.rows], list(TODOS) + ["x_a", "x_b"])
        self.assertEqual(tabla.rows[-1], ("x_b", "applicable", "", "lim b"))
        self.assertIn("model_valid", tabla.description)

    def test_sin_score_ni_agregados(self):
        evs = eda.derive_evaluations("resultado", "fecha_evento", _evaluaciones())
        tabla = eda.coverage_table(evs, "exploratory")
        self.assertEqual(len(tabla.rows), len(evs))
        for fila in tabla.rows:
            for celda in fila:
                self.assertIsInstance(celda, str)
                self.assertNotIn("%", celda)
        self.assertEqual(len({f[0] for f in tabla.rows}), len(tabla.rows))
        self.assertNotIn("%", tabla.description)
        self.assertFalse(any(ch.isdigit() for ch in tabla.description))

    def test_scope_invalido_lanza(self):
        with self.assertRaises(ReportingContractError):
            eda.coverage_table([], "otro")

    def test_capitulo_autogenerado(self):
        cap = _reporte().chapters[0]
        self.assertEqual(cap.chapter_id, "analysis_coverage")
        self.assertEqual(cap.metadata["eda_role"], "coverage")
        self.assertEqual(cap.tables[0].table_id, "eda_coverage")

    def test_ids_reservados(self):
        evs = _evaluaciones()
        cap_id = Chapter(chapter_id="analysis_coverage", title="x")
        cap_tabla = Chapter(
            chapter_id="cap_otro", title="x",
            tables=(TableArtifact("eda_coverage", "t", ("a",), (("v",),)),),
        )
        for cap in (cap_id, cap_tabla):
            with self.subTest(cap=cap.chapter_id), \
                    self.assertRaisesRegex(ReportingContractError, "reservado"):
                eda.build_eda_report("r", "t", "exploratory", [cap], evs, target="a",
                                     time_column="b")


# --- R7 ---------------------------------------------------------------------------


class TestR7Build(unittest.TestCase):
    def test_firma(self):
        params = inspect.signature(eda.build_eda_report).parameters
        self.assertEqual(list(params), [
            "report_id", "title", "decision_scope", "chapters", "evaluations", "target",
            "time_column", "summary", "conclusion", "metadata", "scientific_policy"])
        for nombre in list(params)[5:]:
            self.assertEqual(params[nombre].kind, inspect.Parameter.KEYWORD_ONLY)

    def test_report_kind_y_cobertura_primero(self):
        rep = _reporte(aplicables=("data_quality", "univariate"))
        self.assertEqual(rep.report_kind, "eda")
        self.assertEqual([c.chapter_id for c in rep.chapters],
                         ["analysis_coverage", "cap_data_quality", "cap_univariate"])

    def test_fusiona_metadata_de_usuario(self):
        rep = _reporte(metadata={"proyecto": "sintetico"})
        self.assertEqual(rep.metadata["proyecto"], "sintetico")
        self.assertIn("eda", rep.metadata)

    def test_clave_eda_reservada(self):
        with self.assertRaises(ReportingContractError):
            _reporte(metadata={"eda": {}})

    def test_no_muta_argumentos(self):
        metadata = {"proyecto": {"k": [1, 2]}}
        copia_md = copy.deepcopy(metadata)
        capitulos = [_capitulo("data_quality")]
        evs = _evaluaciones()
        evs_antes = list(evs)
        eda.build_eda_report("r", "t", "exploratory", capitulos, evs, target="a", time_column="b",
                             metadata=metadata)
        self.assertEqual(metadata, copia_md)
        self.assertEqual(len(capitulos), 1)
        self.assertEqual(evs, evs_antes)

    def test_target_o_tiempo_invalidos_lanzan(self):
        for kw in (dict(target=""), dict(target=5), dict(time_column="  ")):
            with self.subTest(kw=kw), self.assertRaises(ReportingContractError):
                _reporte(**kw)

    def test_determinista(self):
        self.assertEqual(_reporte().content_sha256(), _reporte().content_sha256())
        self.assertNotEqual(_reporte().content_sha256(), _reporte(target=None).content_sha256())


# --- R8 / R9 ---------------------------------------------------------------------------


class TestR8R9General(unittest.TestCase):
    def test_reporte_limpio_emite_todos_los_codigos_sin_fail(self):
        res = _validar(_reporte())
        self.assertEqual([r for r in res if r.status == FAIL], [])
        self.assertEqual({r.code for r in res}, set(eda.CODES))
        self.assertTrue(all(isinstance(r, checks.CheckResult) for r in res))

    def test_no_eda_sin_declaracion_es_na(self):
        rep = Report("r", "t", "model", "exploratory")
        res = _validar(rep)
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0].status, NA)

    def test_objeto_no_report_es_fail(self):
        for obj in (None, "texto", 5, {"report_kind": "eda"}, object()):
            with self.subTest(obj=obj):
                res = _validar(obj)
                self.assertEqual([(r.status, r.code) for r in res], [(FAIL, "EDA-PROFILE")])

    def test_declaracion_en_reporte_no_eda_falla(self):
        rep = Report("r", "t", "model", "exploratory", metadata={"eda": {"applicability": {}}})
        res = _validar(rep)
        self.assertEqual([(r.status, r.code) for r in res], [(FAIL, "EDA-PROFILE")])

    def test_eda_sin_declaracion_no_evalua_dependientes(self):
        variantes = [
            lambda d: d["metadata"].pop("eda"),
            lambda d: d["metadata"].update(eda="texto"),
            lambda d: d["metadata"].update(eda=None),
            lambda d: d["metadata"].update(eda={"profile": "eda"}),
            lambda d: d["metadata"].update(eda={"applicability": [1, 2]}),
        ]
        for fn in variantes:
            with self.subTest(fn=fn):
                res = _validar(_editar(_reporte(), fn))
                self.assertEqual([r.code for r in res], ["EDA-PROFILE", "EDA-APPLICABILITY-MISSING"])
                self.assertEqual([r.status for r in res], [PASS, FAIL])

    def test_nunca_lanza_con_metadata_corrupta(self):
        def con_entradas(entrada):
            return lambda d: d["metadata"]["eda"].update(
                applicability={"data_quality": entrada, "univariate": entrada, "x_a": entrada,
                               "raro": entrada})

        entradas = [5, None, "texto", [], {"state": ["applicable"]}, {"state": 3, "reason": 7},
                    {"state": "omitted", "reason": {"a": 1}, "auto": "si"},
                    {"state": "applicable", "auto": 1, "limitations": None}]
        for entrada in entradas:
            with self.subTest(entrada=entrada):
                res = _validar(_editar(_reporte(), con_entradas(entrada)))
                _sin_error_tecnico(self, res)
        def capitulo_raro(valor):
            return lambda d: d["chapters"][1]["metadata"].update(eda_block=valor)
        for valor in (["lista"], 5, None, {"a": 1}, ""):
            with self.subTest(eda_block=valor):
                res = _validar(_editar(_reporte(), capitulo_raro(valor)))
                _sin_error_tecnico(self, res)
                self.assertIn(FAIL, _estatus(res, "EDA-CHAPTER-BLOCK-UNKNOWN"))
        for politica in ("texto", 5, [], {"temporal": None}, {"temporal": {"date_column": 3}}):
            with self.subTest(politica=politica):
                _sin_error_tecnico(self, _validar(_reporte(), scientific_policy=politica))

    def test_nunca_lanza_con_report_mutado(self):
        rep = _reporte()
        object.__setattr__(rep, "metadata", None)
        _sin_error_tecnico(self, _validar(rep))
        rep2 = _reporte()
        object.__setattr__(rep2, "chapters", 5)
        _sin_error_tecnico(self, _validar(rep2))
        rep3 = _reporte()
        object.__setattr__(rep3, "chapters", (object(), None))
        _sin_error_tecnico(self, _validar(rep3))

    def test_determinista(self):
        rep = _apl(_reporte(), "univariate", reason="TBD")
        self.assertEqual(_validar(rep), _validar(rep))


# --- R10 ---------------------------------------------------------------------------


class TestR10Cobertura(unittest.TestCase):
    def test_bloque_sin_evaluar(self):
        def fn(d):
            del d["metadata"]["eda"]["applicability"]["multivariate"]
        res = _validar(_editar(_reporte(), fn))
        malos = [r for r in _de_codigo(res, "EDA-BLOCK-UNEVALUATED") if r.status == FAIL]
        self.assertEqual([r.subject for r in malos], ["multivariate"])

    def test_bloque_desconocido(self):
        def fn(d):
            d["metadata"]["eda"]["applicability"]["otro_bloque"] = {
                "state": "omitted", "reason": _razon("otro"), "limitations": "", "auto": False}
        res = _validar(_editar(_reporte(), fn))
        self.assertEqual([r.subject for r in _de_codigo(res, "EDA-BLOCK-UNKNOWN")
                          if r.status == FAIL], ["otro_bloque"])

    def test_estado_invalido_incluye_partial(self):
        for estado in ("partial", "", "APPLICABLE", None, 3):
            with self.subTest(estado=estado):
                res = _validar(_apl(_reporte(), "univariate", state=estado))
                self.assertIn(FAIL, _estatus(res, "EDA-BLOCK-STATE"))

    def test_todo_valido_pasa(self):
        res = _validar(_reporte())
        for codigo in ("EDA-BLOCK-UNEVALUATED", "EDA-BLOCK-UNKNOWN", "EDA-BLOCK-STATE"):
            self.assertEqual(_estatus(res, codigo), [PASS])


# --- R11 ---------------------------------------------------------------------------


class TestR11Razones(unittest.TestCase):
    def test_normalizacion(self):
        n = eda._normalizar_razon
        self.assertEqual(n("  N/A.  "), "n a")
        self.assertEqual(n("No   aplica!!"), "no aplica")
        self.assertEqual(n("-"), "")
        self.assertEqual(n(None), "")

    def test_razones_triviales_fallan(self):
        for razon in ("N/A.", "  TBD ", "No aplica!!", "", "-", "todo", "None", "n/a",
                      "cuatro palabras solo aqui", "a b c d e f g h", "no se se se se"):
            with self.subTest(razon=razon):
                res = _validar(_apl(_reporte(), "univariate", reason=razon))
                self.assertIn(FAIL, _estatus(res, "EDA-BLOCK-REASON"))

    def test_razon_significativa_pasa(self):
        razon = "no existe columna de entidad para cruzar registros"
        res = _validar(_apl(_reporte(), "univariate", reason=razon))
        self.assertEqual(_estatus(res, "EDA-BLOCK-REASON"), [PASS])

    def test_not_applicable_tambien_exige_razon(self):
        res = _validar(_apl(_reporte(), "entity_relations", state="not_applicable", reason="N/A"))
        self.assertIn(FAIL, _estatus(res, "EDA-BLOCK-REASON"))

    def test_gaming_auto_false_sin_target_exige_razon(self):
        rep = _apl(_reporte(target=None), "bivariate_target", auto=False, reason="N/A")
        self.assertIn(FAIL, _estatus(_validar(rep), "EDA-BLOCK-REASON"))

    def test_applicable_no_exige_razon(self):
        self.assertEqual(_estatus(_validar(_reporte()), "EDA-BLOCK-REASON"), [PASS])

    def test_duplicada_en_tres_bloques_falla(self):
        rep = _reporte()
        variantes = {"univariate": "Misma razón genérica, sin más detalle!",
                     "multivariate": "misma   razón genérica sin más detalle",
                     "concentration": "MISMA RAZÓN GENÉRICA. SIN MÁS DETALLE"}
        for bloque, razon in variantes.items():
            rep = _apl(rep, bloque, reason=razon)
        res = _validar(rep)
        fallas = [r for r in _de_codigo(res, "EDA-REASON-DUPLICATED") if r.status == FAIL]
        self.assertEqual(len(fallas), 1)
        for bloque in variantes:
            self.assertIn(bloque, fallas[0].subject)

    def test_duplicada_en_dos_bloques_pasa(self):
        rep = _reporte()
        for bloque in ("univariate", "multivariate"):
            rep = _apl(rep, bloque, reason="Misma razón genérica, sin más detalle!")
        self.assertEqual(_estatus(_validar(rep), "EDA-REASON-DUPLICATED"), [PASS])

    def test_duplicada_excluye_auto(self):
        rep = _reporte()
        for bloque in ("univariate", "multivariate", "concentration"):
            rep = _apl(rep, bloque, reason="Misma razón genérica, sin más detalle!", auto=True)
        res = _validar(rep)
        self.assertEqual(_estatus(res, "EDA-REASON-DUPLICATED"), [PASS])
        self.assertEqual(_estatus(res, "EDA-AUTO-INVALID"), [FAIL] * 3)


# --- R12 ---------------------------------------------------------------------------


class TestR12AutoInvalid(unittest.TestCase):
    def test_auto_en_bloque_sin_precondicion(self):
        res = _validar(_apl(_reporte(), "univariate", auto=True, state="not_applicable"))
        fallas = [r for r in _de_codigo(res, "EDA-AUTO-INVALID") if r.status == FAIL]
        self.assertEqual([r.subject for r in fallas], ["univariate"])

    def test_auto_con_target_declarado(self):
        rep = _apl(_reporte(target="resultado"), "bivariate_target", state="not_applicable",
                   auto=True, reason=_razon("bivariate_target"))
        self.assertIn(FAIL, _estatus(_validar(rep), "EDA-AUTO-INVALID"))

    def test_auto_con_tiempo_declarado_via_politica(self):
        rep = _reporte(target="resultado", time_column=None)  # temporal autoderivado
        self.assertEqual(_estatus(_validar(rep), "EDA-AUTO-INVALID"), [PASS])
        politica = {"temporal": {"date_column": "fecha_evento"}}
        self.assertIn(FAIL, _estatus(_validar(rep, scientific_policy=politica), "EDA-AUTO-INVALID"))

    def test_auto_con_estado_distinto_de_not_applicable(self):
        rep = _apl(_reporte(target=None), "bivariate_target", state="omitted")
        self.assertIn(FAIL, _estatus(_validar(rep), "EDA-AUTO-INVALID"))

    def test_auto_no_booleano(self):
        rep = _apl(_reporte(), "univariate", auto="si")
        self.assertIn(FAIL, _estatus(_validar(rep), "EDA-AUTO-INVALID"))

    def test_auto_valido_pasa(self):
        res = _validar(_reporte(target=None, time_column=None))
        self.assertEqual(_estatus(res, "EDA-AUTO-INVALID"), [PASS])


# --- R13 ---------------------------------------------------------------------------


class TestR13Capitulos(unittest.TestCase):
    def test_sin_capitulo(self):
        def fn(d):
            d["chapters"] = [c for c in d["chapters"]
                             if c["metadata"].get("eda_block") != "data_quality"]
        res = _validar(_editar(_reporte(), fn))
        self.assertEqual([r.subject for r in _de_codigo(res, "EDA-BLOCK-NO-CHAPTER")
                          if r.status == FAIL], ["data_quality"])

    def test_sin_insight(self):
        rep = eda.build_eda_report("r", "t", "exploratory", [_capitulo("data_quality", False)],
                                   _evaluaciones(), target="a", time_column="b")
        res = _validar(rep)
        self.assertEqual(_estatus(res, "EDA-BLOCK-NO-CHAPTER"), [PASS])
        self.assertEqual([r.subject for r in _de_codigo(res, "EDA-BLOCK-NO-INSIGHT")
                          if r.status == FAIL], ["data_quality"])

    def test_insight_en_cualquiera_de_sus_capitulos_basta(self):
        extra = Chapter(chapter_id="cap_dq_2", title="x", insights=(_insight("dq_2"),),
                        metadata={"eda_block": "data_quality"})
        rep = eda.build_eda_report("r", "t", "exploratory",
                                   [_capitulo("data_quality", False), extra], _evaluaciones(),
                                   target="a", time_column="b")
        self.assertEqual(_estatus(_validar(rep), "EDA-BLOCK-NO-INSIGHT"), [PASS])

    def test_contradiccion_es_warn(self):
        for bloque in ("univariate", "entity_relations"):
            with self.subTest(bloque=bloque):
                rep = _reporte(na=("entity_relations",), extra_chapters=(_capitulo(bloque),))
                res = _validar(rep)
                self.assertEqual(_estatus(res, "EDA-BLOCK-CONTRADICTION"), [WARN])
                self.assertEqual([r for r in res if r.status == FAIL], [])

    def test_capitulo_de_bloque_no_evaluado(self):
        rep = _reporte(extra_chapters=(_capitulo("inexistente"),))
        res = _validar(rep)
        fallas = [r for r in _de_codigo(res, "EDA-CHAPTER-BLOCK-UNKNOWN") if r.status == FAIL]
        self.assertEqual([r.subject for r in fallas], ["cap_inexistente"])

    def test_capitulos_sin_eda_block_son_legitimos(self):
        libre = Chapter(chapter_id="contexto", title="Contexto")
        # data_quality es applicable: se le da su capítulo; el libre convive sin generar reglas.
        rep = eda.build_eda_report("r", "t", "exploratory", [libre, _capitulo("data_quality")],
                                   _evaluaciones(), target="a", time_column="b")
        res = _validar(rep)
        self.assertEqual([r for r in res if r.status in (FAIL, WARN)], [])
        self.assertEqual(_estatus(res, "EDA-CHAPTER-BLOCK-UNKNOWN"), [PASS])


# --- R14 ---------------------------------------------------------------------------


class TestR14Precondiciones(unittest.TestCase):
    def test_target_declarado(self):
        rep = _reporte(aplicables=("data_quality", "bivariate_target"))
        self.assertEqual(_estatus(_validar(rep), "EDA-TARGET-DECLARED"), [PASS])
        def fn(d):
            d["metadata"]["eda"]["target"] = None
        self.assertIn(FAIL, _estatus(_validar(_editar(rep, fn)), "EDA-TARGET-DECLARED"))

    def test_target_no_str_o_vacio_cuenta_como_no_declarado(self):
        rep = _reporte(aplicables=("data_quality", "bivariate_target"))
        for valor in (5, "", "  ", ["a"]):
            with self.subTest(valor=valor):
                def fn(d, v=valor):
                    d["metadata"]["eda"]["target"] = v
                self.assertIn(FAIL, _estatus(_validar(_editar(rep, fn)), "EDA-TARGET-DECLARED"))

    def test_tiempo_declarado_y_politica(self):
        rep = _reporte(aplicables=("data_quality", "temporal"))
        self.assertEqual(_estatus(_validar(rep), "EDA-TIME-DECLARED"), [PASS])
        def fn(d):
            d["metadata"]["eda"]["time_column"] = None
        sin_col = _editar(rep, fn)
        self.assertIn(FAIL, _estatus(_validar(sin_col), "EDA-TIME-DECLARED"))
        politica = {"temporal": {"date_column": "fecha_evento"}}
        self.assertEqual(_estatus(_validar(sin_col, scientific_policy=politica),
                                  "EDA-TIME-DECLARED"), [PASS])

    def test_reporte_construido_con_politica_valida_con_ella(self):
        politica = {"temporal": {"date_column": "fecha_evento"}}
        rep = _reporte(aplicables=("data_quality", "temporal"), time_column=None, policy=politica)
        self.assertEqual([r for r in _validar(rep, scientific_policy=politica)
                          if r.status == FAIL], [])
        self.assertIn(FAIL, _estatus(_validar(rep), "EDA-TIME-DECLARED"))

    def test_no_aplicables_no_exigen(self):
        res = _validar(_reporte(target=None, time_column=None))
        self.assertEqual(_estatus(res, "EDA-TARGET-DECLARED"), [PASS])
        self.assertEqual(_estatus(res, "EDA-TIME-DECLARED"), [PASS])


# --- R15 ---------------------------------------------------------------------------


class TestR15OmittedScope(unittest.TestCase):
    def test_omitido_en_scopes_estrictos_es_warn(self):
        for scope in ("model_valid", "operational"):
            with self.subTest(scope=scope):
                res = _validar(_reporte(scope=scope))
                self.assertEqual(_estatus(res, "EDA-OMITTED-SCOPE"), [WARN])
                self.assertEqual([r for r in res if r.status == FAIL], [])

    def test_exploratory_pasa(self):
        self.assertEqual(_estatus(_validar(_reporte(scope="exploratory")), "EDA-OMITTED-SCOPE"),
                         [PASS])

    def test_estricto_sin_omitidos_pasa(self):
        res = _validar(_reporte(aplicables=TODOS, scope="model_valid"))
        self.assertEqual(_estatus(res, "EDA-OMITTED-SCOPE"), [PASS])
        self.assertEqual([r for r in res if r.status != PASS], [])


# --- R16 / R17 ---------------------------------------------------------------------------


class TestR16R17Leakage(unittest.TestCase):
    def test_bivariate_sin_leakage_en_scopes_estrictos_falla(self):
        for scope in ("model_valid", "operational"):
            for leak in ("omitted", "not_applicable"):
                with self.subTest(scope=scope, leak=leak):
                    rep = _reporte(aplicables=("data_quality", "bivariate_target"), scope=scope,
                                   na=("leakage_review",) if leak == "not_applicable" else ())
                    self.assertIn(FAIL, _estatus(_validar(rep), "EDA-LEAKAGE-REVIEW-REQUIRED"))

    def test_bivariate_con_leakage_aplicado_pasa(self):
        rep = _reporte(aplicables=("data_quality", "bivariate_target", "leakage_review"),
                       scope="model_valid")
        self.assertEqual(_estatus(_validar(rep), "EDA-LEAKAGE-REVIEW-REQUIRED"), [PASS])

    def test_exploratory_no_aplica_regla(self):
        rep = _reporte(aplicables=("data_quality", "bivariate_target"), scope="exploratory")
        self.assertEqual(_estatus(_validar(rep), "EDA-LEAKAGE-REVIEW-REQUIRED"), [PASS])

    def test_sin_bivariate_pasa(self):
        self.assertEqual(_estatus(_validar(_reporte(scope="model_valid")),
                                  "EDA-LEAKAGE-REVIEW-REQUIRED"), [PASS])

    def test_exploratory_target_use_warn(self):
        rep = _reporte(aplicables=("data_quality", "bivariate_target"), scope="exploratory")
        res = _de_codigo(_validar(rep), "EDA-EXPLORATORY-TARGET-USE")
        self.assertEqual([r.status for r in res], [WARN])
        self.assertIn("no es insumo de selección de features", res[0].message)

    def test_exploratory_target_use_pasa_en_otros_casos(self):
        self.assertEqual(_estatus(_validar(_reporte()), "EDA-EXPLORATORY-TARGET-USE"), [PASS])
        rep = _reporte(aplicables=("data_quality", "bivariate_target", "leakage_review"),
                       scope="model_valid")
        self.assertEqual(_estatus(_validar(rep), "EDA-EXPLORATORY-TARGET-USE"), [PASS])


# --- R18 ---------------------------------------------------------------------------


class TestR18TablaCobertura(unittest.TestCase):
    def _tabla(self, d):
        return d["chapters"][0]["tables"][0]

    def test_tabla_construida_pasa(self):
        for kw in (dict(), dict(target=None, time_column=None)):
            with self.subTest(kw=kw):
                self.assertEqual(_estatus(_validar(_reporte(**kw)), "EDA-COVERAGE-TABLE"), [PASS])

    def test_falta_capitulo(self):
        def fn(d):
            d["chapters"] = d["chapters"][1:]
        self.assertIn(FAIL, _estatus(_validar(_editar(_reporte(), fn)), "EDA-COVERAGE-TABLE"))

    def test_falta_tabla(self):
        def fn(d):
            d["chapters"][0]["tables"] = []
        self.assertIn(FAIL, _estatus(_validar(_editar(_reporte(), fn)), "EDA-COVERAGE-TABLE"))

    def test_columnas_distintas(self):
        def fn(d):
            t = self._tabla(d)
            t["columns"] = ["block", "state", "reason", "score"]
        self.assertIn(FAIL, _estatus(_validar(_editar(_reporte(), fn)), "EDA-COVERAGE-TABLE"))

    def test_fila_de_menos_y_de_mas(self):
        def menos(d):
            self._tabla(d)["rows"].pop()
        def mas(d):
            self._tabla(d)["rows"].append(["total", "applicable", "", ""])
        for fn in (menos, mas):
            with self.subTest(fn=fn.__name__):
                self.assertIn(FAIL, _estatus(_validar(_editar(_reporte(), fn)),
                                             "EDA-COVERAGE-TABLE"))

    def test_fila_que_no_coincide(self):
        def fn(d):
            self._tabla(d)["rows"][0][1] = "omitted"
        res = _validar(_editar(_reporte(), fn))
        fallas = [r for r in _de_codigo(res, "EDA-COVERAGE-TABLE") if r.status == FAIL]
        self.assertEqual([r.subject for r in fallas], ["data_quality"])

    def test_porcentaje_en_fila(self):
        def fn(d):
            self._tabla(d)["rows"][0][3] = "cobertura 100%"
        self.assertIn(FAIL, _estatus(_validar(_editar(_reporte(), fn)), "EDA-COVERAGE-TABLE"))

    def test_declaracion_modificada_desincroniza_tabla(self):
        rep = _apl(_reporte(), "univariate", limitations="agregada solo en la declaración")
        self.assertIn(FAIL, _estatus(_validar(rep), "EDA-COVERAGE-TABLE"))

    def test_limitations_visible_en_tabla_y_pasa(self):
        evs = _evaluaciones()
        evs[0] = eda.BlockEvaluation("data_quality", "applicable", "", "solo columnas numéricas")
        rep = eda.build_eda_report("r", "t", "exploratory", [_capitulo("data_quality")], evs,
                                   target="a", time_column="b")
        self.assertEqual(rep.chapters[0].tables[0].rows[0][3], "solo columnas numéricas")
        self.assertEqual(_estatus(_validar(rep), "EDA-COVERAGE-TABLE"), [PASS])


# --- Excepciones internas ----------------------------------------------------------


class TestExcepcionesInternas(unittest.TestCase):
    def test_excepcion_global_es_technical_error(self):
        with mock.patch.object(eda, "_capitulos", side_effect=RuntimeError("boom")):
            res = _validar(_reporte())
        self.assertEqual(
            [(r.code, r.status, r.kind) for r in res],
            [("EDA-PROFILE-EXCEPCION", FAIL, checks.KIND_TECHNICAL_ERROR)],
        )

    def test_excepcion_en_una_regla_no_frena_a_las_demas(self):
        with mock.patch.object(eda, "_normalizar_razon", side_effect=RuntimeError("boom")):
            res = _validar(_reporte())
        tecnicos = {r.code for r in res if r.kind == checks.KIND_TECHNICAL_ERROR}
        self.assertEqual(tecnicos, {"EDA-BLOCK-REASON-EXCEPCION", "EDA-REASON-DUPLICATED-EXCEPCION"})
        self.assertEqual(_estatus(res, "EDA-COVERAGE-TABLE"), [PASS])


# --- Round-trip ---------------------------------------------------------------------


class TestRoundTrip(unittest.TestCase):
    def _comprobar(self, rep):
        rt = Report.from_dict(rep.to_dict())
        self.assertEqual(rt.content_sha256(), rep.content_sha256())
        self.assertEqual(_validar(rt), _validar(rep))
        _sin_error_tecnico(self, _validar(rt))

    def test_reporte_del_profile(self):
        self._comprobar(_reporte(aplicables=("data_quality", "univariate")))

    def test_ejemplo_generico(self):
        from tools.reporting.examples.eda_generic import build_example_report
        self._comprobar(build_example_report())


# --- Enmiendas del ciclo de review ----------------------------------------------------


class TestEnmiendasReview(unittest.TestCase):
    def test_codigos_nuevos_en_codes(self):
        self.assertIn("EDA-NA-CONTRADICTS-DECLARATION", eda.CODES)
        self.assertIn("EDA-EXTENSION-SHADOWS-CATALOG", eda.CODES)
        self.assertEqual(len(set(eda.CODES)), len(eda.CODES))

    # (a) evasión por omitir target/tiempo
    def test_applicable_sin_target_se_conserva_y_falla(self):
        evs = [eda.BlockEvaluation("bivariate_target", "applicable")]
        res = eda.derive_evaluations(None, "fecha_evento", evs)
        ev = {e.block: e for e in res}["bivariate_target"]
        self.assertEqual((ev.state, ev.auto), ("applicable", False))
        rep = _reporte(aplicables=("data_quality", "bivariate_target"), target=None)
        self.assertEqual(
            rep.metadata["eda"]["applicability"]["bivariate_target"]["state"], "applicable")
        self.assertIn(FAIL, _estatus(_validar(rep), "EDA-TARGET-DECLARED"))

    def test_applicable_sin_tiempo_se_conserva_y_falla(self):
        rep = _reporte(aplicables=("data_quality", "temporal"), time_column=None)
        self.assertEqual(rep.metadata["eda"]["applicability"]["temporal"]["state"], "applicable")
        self.assertIn(FAIL, _estatus(_validar(rep), "EDA-TIME-DECLARED"))

    def test_omitido_o_na_declarado_sin_target_si_se_autoderiva(self):
        for estado in ("omitted", "not_applicable"):
            with self.subTest(estado=estado):
                evs = [eda.BlockEvaluation("bivariate_target", estado, "razón previa")]
                ev = {e.block: e for e in eda.derive_evaluations(None, "f", evs)}["bivariate_target"]
                self.assertEqual((ev.state, ev.auto), ("not_applicable", True))

    # (b) R16 por capítulo
    def test_r16_por_capitulo_bivariate_con_bloque_omitido(self):
        for scope in ("model_valid", "operational"):
            for kw in (dict(), dict(target=None)):
                with self.subTest(scope=scope, kw=kw):
                    rep = _reporte(scope=scope, extra_chapters=(_capitulo("bivariate_target"),), **kw)
                    self.assertIn(FAIL, _estatus(_validar(rep), "EDA-LEAKAGE-REVIEW-REQUIRED"))

    def test_r16_por_capitulo_pasa_con_leakage_o_exploratory(self):
        rep = _reporte(aplicables=("data_quality", "leakage_review"), scope="model_valid",
                       extra_chapters=(_capitulo("bivariate_target"),))
        self.assertEqual(_estatus(_validar(rep), "EDA-LEAKAGE-REVIEW-REQUIRED"), [PASS])
        rep = _reporte(scope="exploratory", extra_chapters=(_capitulo("bivariate_target"),))
        self.assertEqual(_estatus(_validar(rep), "EDA-LEAKAGE-REVIEW-REQUIRED"), [PASS])

    # (c) not_applicable manual contradictorio
    def test_na_manual_con_target_declarado_es_warn(self):
        res = _validar(_reporte(na=("bivariate_target",)))
        self.assertEqual(_estatus(res, "EDA-NA-CONTRADICTS-DECLARATION"), [WARN])
        self.assertEqual([r for r in res if r.status == FAIL], [])

    def test_na_manual_con_tiempo_via_politica_es_warn(self):
        politica = {"temporal": {"date_column": "fecha_evento"}}
        rep = _reporte(na=("temporal",), time_column=None, policy=politica)
        self.assertEqual(_estatus(_validar(rep, scientific_policy=politica),
                                  "EDA-NA-CONTRADICTS-DECLARATION"), [WARN])
        self.assertEqual(_estatus(_validar(rep), "EDA-NA-CONTRADICTS-DECLARATION"), [PASS])

    def test_na_autoderivado_o_sin_precondicion_no_avisa(self):
        res = _validar(_reporte(target=None, time_column=None))
        self.assertEqual(_estatus(res, "EDA-NA-CONTRADICTS-DECLARATION"), [PASS])
        res = _validar(_reporte(na=("entity_relations",)))
        self.assertEqual(_estatus(res, "EDA-NA-CONTRADICTS-DECLARATION"), [PASS])

    # (d) extensión que sombrea el catálogo
    def test_extension_que_sombrea_catalogo_es_warn(self):
        for bloque in ("x_bivariate_target", "x_Bivariate-Target", "x_leakage-review"):
            with self.subTest(bloque=bloque):
                rep = _reporte(extra_evals=(
                    eda.BlockEvaluation(bloque, "omitted", _razon(bloque)),))
                res = _validar(rep)
                avisos = [r for r in _de_codigo(res, "EDA-EXTENSION-SHADOWS-CATALOG")
                          if r.status == WARN]
                self.assertEqual([r.subject for r in avisos], [bloque])
                self.assertEqual([r for r in res if r.status == FAIL], [])

    def test_extension_distinta_no_avisa(self):
        rep = _reporte(extra_evals=(
            eda.BlockEvaluation("x_dominio", "omitted", _razon("x_dominio")),))
        self.assertEqual(_estatus(_validar(rep), "EDA-EXTENSION-SHADOWS-CATALOG"), [PASS])

    # R9
    def test_profile_o_version_invalidos_fallan(self):
        cambios = [dict(profile="otro"), dict(profile=None), dict(profile_version=99),
                   dict(profile_version=True), dict(profile_version="1"),
                   dict(profile_version=1.0)]
        for cambio in cambios:
            with self.subTest(cambio=cambio):
                def fn(d, c=cambio):
                    d["metadata"]["eda"].update(c)
                res = _validar(_editar(_reporte(), fn))
                self.assertEqual(_estatus(res, "EDA-PROFILE"), [FAIL])
                self.assertEqual({r.code for r in res}, set(eda.CODES))

    def test_version_ausente_falla(self):
        def fn(d):
            d["metadata"]["eda"].pop("profile_version")
        self.assertEqual(_estatus(_validar(_editar(_reporte(), fn)), "EDA-PROFILE"), [FAIL])

    def test_profile_valido_pasa(self):
        self.assertEqual(_estatus(_validar(_reporte()), "EDA-PROFILE"), [PASS])

    # R11: palabras distintas y espacios Unicode
    def test_razon_con_palabras_repetidas_falla(self):
        for razon in ("TBD TBD TBD TBD TBD", "tbd tbd tbd tbd tbd tbd tbd",
                      "algo cosa algo cosa algo"):
            with self.subTest(razon=razon):
                res = _validar(_apl(_reporte(), "univariate", reason=razon))
                self.assertIn(FAIL, _estatus(res, "EDA-BLOCK-REASON"))

    def test_tres_palabras_distintas_es_el_minimo(self):
        res = _validar(_apl(_reporte(), "univariate", reason="algo cosa otra algo cosa"))
        self.assertEqual(_estatus(res, "EDA-BLOCK-REASON"), [PASS])

    def test_nbsp_y_zwsp_no_disfrazan_razones(self):
        self.assertEqual(eda._normalizar_razon("​ "), "")
        trampas = ["N/A   ", "​", "  ",
                   "tbd​tbd​tbd​tbd​tbd",
                   "tbd tbd tbd tbd tbd"]
        for razon in trampas:
            with self.subTest(razon=razon):
                res = _validar(_apl(_reporte(), "univariate", reason=razon))
                self.assertIn(FAIL, _estatus(res, "EDA-BLOCK-REASON"))

    def test_razon_legitima_con_nbsp_pasa(self):
        razon = "no existe columna de entidad para cruzar"
        res = _validar(_apl(_reporte(), "univariate", reason=razon))
        self.assertEqual(_estatus(res, "EDA-BLOCK-REASON"), [PASS])


if __name__ == "__main__":
    unittest.main()

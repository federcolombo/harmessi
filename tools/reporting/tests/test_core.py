"""Tests de `tools/reporting/core.py` (v0.6 Change 0, `20260918-reporting-core`).

Deterministas: sin red, sin aleatoriedad, sin depender del cwd. No usan
librerías tabulares externas: los duck types se simulan con clases de prueba.
Fixtures 100% genéricos (columnas `grupo`, `n`, `tasa`).
"""
from __future__ import annotations

import ast
import json
import unittest
from dataclasses import FrozenInstanceError
from itertools import product
from pathlib import Path

from tools.reporting.core import (
    ARTIFACTS_DIRNAME,
    CHART_TYPES,
    CLAIM_TYPES,
    DECISION_SCOPES,
    INSIGHTS_FILENAME,
    MANIFEST_FILENAME,
    ORIENTATIONS,
    REPORT_FILENAME,
    REPORT_KINDS,
    SCHEMA_VERSION,
    SEMANTIC_ROLES,
    Chapter,
    FigureArtifact,
    FigureSpec,
    Insight,
    Report,
    ReportingContractError,
    TableArtifact,
    canonical_json,
    es_id_valido,
)

# ---------------------------------------------------------------------------
# Dobles de prueba (duck types)
# ---------------------------------------------------------------------------


class _Valores:
    def __init__(self, filas):
        self._filas = filas

    def tolist(self):
        return [list(f) for f in self._filas]


class _FrameSinAstype:
    def __init__(self, columnas, filas):
        self.columns = list(columnas)
        self.values = _Valores(filas)


class _FrameConAstype(_FrameSinAstype):
    """`values` (sin astype) devuelve enteros promovidos a float; `astype(object)`
    devuelve un frame cuyo `values.tolist()` conserva los enteros."""

    def __init__(self, columnas, filas_object, filas_promovidas):
        super().__init__(columnas, filas_promovidas)
        self._objeto = _FrameSinAstype(columnas, filas_object)
        self.tipos_pedidos = []

    def astype(self, tipo):
        self.tipos_pedidos.append(tipo)
        return self._objeto


class _Fecha:
    def isoformat(self):
        return "2024-01-31"


class _Escalar:
    def __init__(self, valor):
        self._valor = valor

    def item(self):
        return self._valor


class _Opaco:
    pass


# ---------------------------------------------------------------------------
# Constructores de fixtures
# ---------------------------------------------------------------------------


def _tabla(table_id="tabla_1", **kwargs):
    base = dict(
        table_id=table_id,
        title="Tabla",
        columns=("grupo", "n", "tasa"),
        rows=(("a", 10, 0.5), ("b", 20, 0.25)),
    )
    base.update(kwargs)
    return TableArtifact(**base)


def _spec(**kwargs):
    base = dict(chart_type="bar", x="grupo", y=("tasa",))
    base.update(kwargs)
    return FigureSpec(**base)


def _figura(figure_id="fig_1", **kwargs):
    base = dict(figure_id=figure_id, title="Figura", spec=_spec(), backing_table_id="tabla_1")
    base.update(kwargs)
    return FigureArtifact(**base)


def _insight(insight_id="ins_1", **kwargs):
    base = dict(
        insight_id=insight_id,
        technical_claim="La tasa del grupo a es mayor",
        business_claim="El grupo a rinde más",
        evidence_refs=("tabla_1",),
        population="todos",
        time_scope="periodo unico",
        claim_type="descriptive",
    )
    base.update(kwargs)
    return Insight(**base)


def _capitulo(chapter_id="cap_1", **kwargs):
    base = dict(chapter_id=chapter_id, title="Capitulo")
    base.update(kwargs)
    return Chapter(**base)


def _reporte(**kwargs):
    base = dict(
        report_id="rep_1",
        title="Reporte",
        report_kind="eda",
        decision_scope="exploratory",
    )
    base.update(kwargs)
    return Report(**base)


def _reporte_completo(metadata=None):
    cap1 = _capitulo(
        "cap_1",
        summary="Resumen ñandú",
        tables=[_tabla("tabla_1"), _tabla("tabla_2", units={"tasa": "%"}, column_labels={"n": "N"})],
        figures=[
            _figura("fig_1", backend="motor_x", backend_payload={"k": (1, 2), "z": {"a": 1.5}}),
            _figura("fig_sin_tabla", backing_table_id=None),
        ],
        insights=[_insight("ins_1")],
        method_note="nota",
        metadata={"etiquetas": ("x", "y")},
    )
    cap2 = _capitulo("cap_2", insights=[_insight("ins_2", evidence_refs=("no_existe",))])
    return _reporte(
        chapters=[cap1, cap2],
        summary="resumen",
        conclusion="conclusión",
        metadata=metadata if metadata is not None else {"b": 1, "a": [1, 2]},
    )


# ---------------------------------------------------------------------------
# R2 / R3
# ---------------------------------------------------------------------------


class TestVocabularios(unittest.TestCase):
    def test_vocabularios_exactos(self):
        self.assertEqual(REPORT_KINDS, ("eda", "model", "evaluation", "production"))
        self.assertEqual(DECISION_SCOPES, ("exploratory", "model_valid", "operational"))
        self.assertEqual(
            CLAIM_TYPES,
            ("descriptive", "comparative", "associative", "predictive", "causal", "recommendation"),
        )
        self.assertEqual(CHART_TYPES, ("bar", "line", "scatter", "histogram", "box", "heatmap"))
        self.assertEqual(SEMANTIC_ROLES, ("risk", "status"))
        self.assertEqual(ORIENTATIONS, ("v", "h"))
        self.assertEqual(REPORT_FILENAME, "report.html")
        self.assertEqual(MANIFEST_FILENAME, "manifest.json")
        self.assertEqual(INSIGHTS_FILENAME, "insights.json")
        self.assertEqual(ARTIFACTS_DIRNAME, "artifacts")
        self.assertEqual(SCHEMA_VERSION, 1)

    def test_error_es_value_error(self):
        self.assertTrue(issubclass(ReportingContractError, ValueError))


class TestOrtogonalidad(unittest.TestCase):
    def test_las_12_combinaciones_se_construyen(self):
        combinaciones = list(product(REPORT_KINDS, DECISION_SCOPES))
        self.assertEqual(len(combinaciones), 12)
        for kind, scope in combinaciones:
            with self.subTest(kind=kind, scope=scope):
                reporte = _reporte(report_kind=kind, decision_scope=scope)
                self.assertEqual(reporte.report_kind, kind)
                self.assertEqual(reporte.decision_scope, scope)

    def test_report_kind_invalido(self):
        with self.assertRaises(ReportingContractError):
            _reporte(report_kind="invalido")

    def test_decision_scope_invalido(self):
        with self.assertRaises(ReportingContractError):
            _reporte(decision_scope="invalido")


# ---------------------------------------------------------------------------
# R4 — ids
# ---------------------------------------------------------------------------

_IDS_VALIDOS = ("a", "tabla_1", "x-y_2", "a" * 64, "0abc")
_IDS_INVALIDOS = ("", "A", "-x", "_x", "a.b", "a/b", "a\\b", "a b", "a" * 65, "a\n", 5, None, b"a")


class TestIds(unittest.TestCase):
    def test_ids_validos(self):
        for valor in _IDS_VALIDOS:
            with self.subTest(valor=valor):
                self.assertEqual(_tabla(table_id=valor).table_id, valor)
                self.assertEqual(_figura(figure_id=valor).figure_id, valor)
                self.assertEqual(_insight(insight_id=valor).insight_id, valor)
                self.assertEqual(_capitulo(chapter_id=valor).chapter_id, valor)
                self.assertEqual(_reporte(report_id=valor).report_id, valor)

    def test_ids_invalidos_en_cada_contrato(self):
        for valor in _IDS_INVALIDOS:
            with self.subTest(valor=valor):
                with self.assertRaises(ReportingContractError):
                    _tabla(table_id=valor)
                with self.assertRaises(ReportingContractError):
                    _figura(figure_id=valor)
                with self.assertRaises(ReportingContractError):
                    _insight(insight_id=valor)
                with self.assertRaises(ReportingContractError):
                    _capitulo(chapter_id=valor)
                with self.assertRaises(ReportingContractError):
                    _reporte(report_id=valor)

    def test_es_id_valido_coincide_con_el_contrato(self):
        for valor in _IDS_VALIDOS:
            with self.subTest(valido=valor):
                self.assertIs(es_id_valido(valor), True)
        for valor in tuple(_IDS_INVALIDOS) + (".", "con", "a:b", "x\n", None, 5):
            with self.subTest(invalido=valor):
                self.assertIs(es_id_valido(valor), False)

    def test_backing_table_id_y_evidence_refs_validan_id(self):
        for valor in ("A", "a.b", 5, ""):
            with self.subTest(valor=valor):
                with self.assertRaises(ReportingContractError):
                    _figura(backing_table_id=valor)
                with self.assertRaises(ReportingContractError):
                    _insight(evidence_refs=("ok", valor))


# ---------------------------------------------------------------------------
# R5 — TableArtifact
# ---------------------------------------------------------------------------


class TestTableArtifact(unittest.TestCase):
    def test_tabla_valida_normaliza_a_tuplas(self):
        t = _tabla(columns=["grupo", "n"], rows=[["a", 1], ["b", 2]])
        self.assertIsInstance(t.columns, tuple)
        self.assertIsInstance(t.rows, tuple)
        for fila in t.rows:
            self.assertIsInstance(fila, tuple)
        self.assertEqual(t.rows, (("a", 1), ("b", 2)))

    def test_columnas_invalidas(self):
        casos = {
            "vacia": (),
            "duplicada": ("a", "a"),
            "elemento_vacio": ("a", ""),
            "elemento_no_str": ("a", 3),
            "no_secuencia": "ab",
        }
        for nombre, columnas in casos.items():
            with self.subTest(nombre):
                with self.assertRaises(ReportingContractError):
                    TableArtifact(table_id="t", title="T", columns=columnas, rows=())

    def test_fila_con_largo_distinto(self):
        with self.assertRaises(ReportingContractError):
            _tabla(rows=(("a", 1),))
        with self.assertRaises(ReportingContractError):
            _tabla(rows=(("a", 1, 0.5, 9),))

    def test_celdas_no_finitas_en_constructor_directo(self):
        for valor in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(valor=valor):
                with self.assertRaises(ReportingContractError):
                    _tabla(rows=(("a", 1, valor),))

    def test_celdas_de_tipo_no_soportado_en_constructor_directo(self):
        for valor in ([1], {"a": 1}, _Opaco(), (1, 2), b"x"):
            with self.subTest(tipo=type(valor).__name__):
                with self.assertRaises(ReportingContractError):
                    _tabla(rows=(("a", 1, valor),))

    def test_celdas_validas(self):
        t = _tabla(rows=(("a", True, None), ("b", 3, 1.5)))
        self.assertEqual(t.rows[0], ("a", True, None))

    def test_units_y_labels_con_clave_fuera_de_columns(self):
        with self.assertRaises(ReportingContractError):
            _tabla(units={"otra": "%"})
        with self.assertRaises(ReportingContractError):
            _tabla(column_labels={"otra": "X"})
        with self.assertRaises(ReportingContractError):
            _tabla(units={"tasa": 5})

    def test_units_y_labels_se_copian(self):
        unidades = {"tasa": "%"}
        t = _tabla(units=unidades)
        unidades["n"] = "personas"
        self.assertEqual(t.units, {"tasa": "%"})

    def test_from_rows_normaliza_no_finitos_y_listas(self):
        t = TableArtifact.from_rows(
            table_id="t",
            title="T",
            columns=["grupo", "tasa"],
            rows=[["a", float("nan")], ["b", float("inf")], ["c", 0.5]],
        )
        self.assertEqual(t.rows, (("a", None), ("b", None), ("c", 0.5)))
        self.assertIsInstance(t.rows[0], tuple)

    def test_from_rows_sigue_estricto_con_otros_tipos(self):
        with self.assertRaises(ReportingContractError):
            TableArtifact.from_rows(table_id="t", title="T", columns=["a"], rows=[[[1]]])
        with self.assertRaises(ReportingContractError):
            TableArtifact.from_rows(table_id="t", title="T", columns=["a"], rows="xx")

    def test_from_frame_coerciona_celdas(self):
        columnas = ["c_none", "c_bool", "c_int", "c_nan", "c_str", "c_fecha", "c_item"]
        fila = [None, True, 3, float("nan"), "x", _Fecha(), _Escalar(7)]
        frame = _FrameSinAstype(columnas, [fila])
        t = TableArtifact.from_frame(frame, table_id="t", title="T")
        self.assertEqual(t.columns, tuple(columnas))
        self.assertEqual(t.rows, ((None, True, 3, None, "x", "2024-01-31", 7),))
        self.assertIs(type(t.rows[0][1]), bool)
        self.assertIs(type(t.rows[0][2]), int)

    def test_from_frame_item_recursivo_y_no_finito(self):
        frame = _FrameSinAstype(["a", "b"], [[_Escalar(_Escalar(4)), _Escalar(float("inf"))]])
        t = TableArtifact.from_frame(frame, table_id="t", title="T")
        self.assertEqual(t.rows, ((4, None),))

    def test_from_frame_tipo_opaco_falla(self):
        frame = _FrameSinAstype(["a", "b"], [[1, _Opaco()]])
        with self.assertRaises(ReportingContractError):
            TableArtifact.from_frame(frame, table_id="t", title="T")

    def test_from_frame_con_astype_conserva_enteros(self):
        frame = _FrameConAstype(
            ["n", "tasa"],
            filas_object=[[1, 0.5], [2, 0.25]],
            filas_promovidas=[[1.0, 0.5], [2.0, 0.25]],
        )
        t = TableArtifact.from_frame(frame, table_id="t", title="T")
        self.assertEqual(frame.tipos_pedidos, [object])
        self.assertEqual(t.rows, ((1, 0.5), (2, 0.25)))
        self.assertIs(type(t.rows[0][0]), int)
        self.assertIs(type(t.rows[1][0]), int)

    def test_from_frame_sin_astype_usa_fallback(self):
        frame = _FrameSinAstype(["grupo", "n"], [["a", 1], ["b", 2]])
        self.assertFalse(hasattr(frame, "astype"))
        t = TableArtifact.from_frame(frame, table_id="t", title="T", units={"n": "u"})
        self.assertEqual(t.rows, (("a", 1), ("b", 2)))
        self.assertEqual(t.units, {"n": "u"})

    def test_from_frame_objeto_invalido(self):
        with self.assertRaises(ReportingContractError):
            TableArtifact.from_frame(_Opaco(), table_id="t", title="T")

    def test_test_core_no_importa_librerias_tabulares(self):
        arbol = ast.parse(Path(__file__).read_text(encoding="utf-8"))
        prohibidos = {"pandas", "numpy"}
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Import):
                nombres = [a.name.split(".")[0] for a in nodo.names]
            elif isinstance(nodo, ast.ImportFrom):
                nombres = [(nodo.module or "").split(".")[0]]
            else:
                continue
            self.assertFalse(prohibidos.intersection(nombres), nombres)


# ---------------------------------------------------------------------------
# R6 / R7 — figuras
# ---------------------------------------------------------------------------


class TestFigureSpec(unittest.TestCase):
    def test_spec_invalidas(self):
        casos = {
            "chart_type": dict(chart_type="pie"),
            "x_vacio": dict(x=""),
            "x_no_str": dict(x=3),
            "orientation": dict(orientation="d"),
            "top_n_cero": dict(top_n=0),
            "top_n_negativo": dict(top_n=-1),
            "top_n_bool": dict(top_n=True),
            "sort": dict(sort="asc"),
            "semantic": dict(semantic="otro"),
            "y_elemento_vacio": dict(y=("",)),
            "color_vacio": dict(color=""),
        }
        for nombre, kwargs in casos.items():
            with self.subTest(nombre):
                with self.assertRaises(ReportingContractError):
                    _spec(**kwargs)

    def test_valores_validos_de_enums(self):
        for chart_type in CHART_TYPES:
            if chart_type == "heatmap":
                _spec(chart_type=chart_type, z="n")
            else:
                _spec(chart_type=chart_type)
        for orientation, sort, semantic in product(ORIENTATIONS, ("ascending", "descending", None), (None, "risk", "status")):
            spec = _spec(orientation=orientation, sort=sort, semantic=semantic, top_n=5)
            self.assertEqual(spec.top_n, 5)

    def test_y_vacia_solo_valida_en_histogram(self):
        with self.assertRaises(ReportingContractError):
            _spec(chart_type="bar", y=())
        spec = _spec(chart_type="histogram", y=())
        self.assertEqual(spec.y, ())

    def test_heatmap_requiere_z(self):
        with self.assertRaises(ReportingContractError):
            _spec(chart_type="heatmap")
        self.assertEqual(_spec(chart_type="heatmap", z="n").z, "n")

    def test_columns_used(self):
        spec = FigureSpec(chart_type="bar", x="a", y=("b", "a"), color="c", z=None, denominator="c")
        self.assertEqual(spec.columns_used(), ("a", "b", "c"))

    def test_y_lista_se_normaliza_a_tupla(self):
        self.assertEqual(_spec(y=["tasa", "n"]).y, ("tasa", "n"))


class TestFigureArtifact(unittest.TestCase):
    def test_sin_tabla_de_respaldo_se_construye(self):
        self.assertIsNone(_figura(backing_table_id=None).backing_table_id)

    def test_backend_y_payload_ambos_o_ninguno(self):
        with self.assertRaises(ReportingContractError):
            _figura(backend="x")
        with self.assertRaises(ReportingContractError):
            _figura(backend_payload={"a": 1})
        with self.assertRaises(ReportingContractError):
            _figura(backend="", backend_payload={})
        fig = _figura(backend="x", backend_payload={"a": (1, 2)})
        self.assertEqual(fig.backend, "x")
        self.assertEqual(fig.backend_payload, {"a": [1, 2]})
        self.assertIsNone(_figura().backend_payload)

    def test_payload_no_json_seguro(self):
        for payload in ({"a": float("nan")}, {"a": _Opaco()}, {1: "x"}, {"a": {1, 2}}, "no_dict"):
            with self.subTest(payload=repr(payload)):
                with self.assertRaises(ReportingContractError):
                    _figura(backend="x", backend_payload=payload)

    def test_payload_copia_profunda(self):
        payload = {"a": {"b": [1, 2]}}
        fig = _figura(backend="x", backend_payload=payload)
        payload["a"]["b"].append(3)
        payload["nuevo"] = 1
        self.assertEqual(fig.backend_payload, {"a": {"b": [1, 2]}})

    def test_spec_debe_ser_figure_spec(self):
        with self.assertRaises(ReportingContractError):
            _figura(spec={"chart_type": "bar"})


# ---------------------------------------------------------------------------
# R8 — Insight
# ---------------------------------------------------------------------------


class TestInsight(unittest.TestCase):
    def test_claim_type_invalido(self):
        with self.assertRaises(ReportingContractError):
            _insight(claim_type="otro")

    def test_todos_los_claim_types(self):
        for claim_type in CLAIM_TYPES:
            self.assertEqual(_insight(claim_type=claim_type).claim_type, claim_type)

    def test_sin_validacion_semantica(self):
        insight = _insight(evidence_refs=(), technical_claim="", business_claim="")
        self.assertEqual(insight.evidence_refs, ())
        self.assertEqual(insight.technical_claim, "")

    def test_defaults_uncertainty_y_title(self):
        insight = Insight(
            "i1", "tec", "neg", ("t1",), "pob", "tiempo", "causal"
        )
        self.assertEqual(insight.uncertainty, "")
        self.assertEqual(insight.title, "")

    def test_evidence_refs_lista_se_normaliza(self):
        self.assertEqual(_insight(evidence_refs=["a", "b"]).evidence_refs, ("a", "b"))

    def test_evidence_refs_str_es_error(self):
        with self.assertRaises(ReportingContractError):
            _insight(evidence_refs="tabla_1")


# ---------------------------------------------------------------------------
# R9 / R10 — Chapter y Report
# ---------------------------------------------------------------------------


class TestChapterYReport(unittest.TestCase):
    def test_chapter_normaliza_contenedores_y_valida_tipos(self):
        cap = _capitulo(tables=[_tabla()], figures=[_figura()], insights=[_insight()])
        self.assertIsInstance(cap.tables, tuple)
        self.assertIsInstance(cap.figures, tuple)
        self.assertIsInstance(cap.insights, tuple)
        with self.assertRaises(ReportingContractError):
            _capitulo(tables=[_figura()])
        with self.assertRaises(ReportingContractError):
            _capitulo(figures=[_tabla()])
        with self.assertRaises(ReportingContractError):
            _capitulo(insights=[_tabla()])
        with self.assertRaises(ReportingContractError):
            _capitulo(tables=_tabla())

    def test_chapter_ids_duplicados(self):
        with self.assertRaises(ReportingContractError):
            _reporte(chapters=[_capitulo("c1"), _capitulo("c1")])

    def test_tabla_y_figura_comparten_namespace_entre_capitulos(self):
        c1 = _capitulo("c1", tables=[_tabla("comun")])
        c2 = _capitulo("c2", figures=[_figura("comun")])
        with self.assertRaises(ReportingContractError):
            _reporte(chapters=[c1, c2])

    def test_tablas_duplicadas_y_figuras_duplicadas(self):
        with self.assertRaises(ReportingContractError):
            _reporte(chapters=[_capitulo("c1", tables=[_tabla("t"), _tabla("t")])])
        with self.assertRaises(ReportingContractError):
            _reporte(chapters=[_capitulo("c1", figures=[_figura("f")]), _capitulo("c2", figures=[_figura("f")])])

    def test_insights_duplicados_entre_capitulos(self):
        c1 = _capitulo("c1", insights=[_insight("i")])
        c2 = _capitulo("c2", insights=[_insight("i")])
        with self.assertRaises(ReportingContractError):
            _reporte(chapters=[c1, c2])

    def test_insight_con_mismo_id_que_tabla_es_valido(self):
        c1 = _capitulo("c1", tables=[_tabla("mismo")], insights=[_insight("mismo")])
        reporte = _reporte(chapters=[c1])
        self.assertIsNotNone(reporte.get_table("mismo"))

    def test_accesores(self):
        reporte = _reporte_completo()
        self.assertEqual([t.table_id for t in reporte.iter_tables()], ["tabla_1", "tabla_2"])
        self.assertEqual([f.figure_id for f in reporte.iter_figures()], ["fig_1", "fig_sin_tabla"])
        self.assertEqual([i.insight_id for i in reporte.iter_insights()], ["ins_1", "ins_2"])
        self.assertIs(reporte.get_table("tabla_2"), reporte.chapters[0].tables[1])
        self.assertIs(reporte.get_figure("fig_1"), reporte.chapters[0].figures[0])
        self.assertIs(reporte.get_artifact("tabla_1"), reporte.chapters[0].tables[0])
        self.assertIs(reporte.get_artifact("fig_1"), reporte.chapters[0].figures[0])

    def test_accesores_devuelven_none_sin_lanzar(self):
        reporte = _reporte_completo()
        for id_inexistente in ("no_existe", "", None, 5):
            self.assertIsNone(reporte.get_table(id_inexistente))
            self.assertIsNone(reporte.get_figure(id_inexistente))
            self.assertIsNone(reporte.get_artifact(id_inexistente))
        self.assertIsNone(reporte.get_table("fig_1"))
        self.assertIsNone(reporte.get_figure("tabla_1"))

    def test_no_valida_completitud_semantica(self):
        # figura sin tabla, evidence_refs a id inexistente, insight sin claims,
        # columnas de la spec ausentes en la tabla de respaldo
        fig = _figura("f1", backing_table_id="t_inexistente", spec=_spec(x="col_que_no_existe"))
        ins = _insight("i1", evidence_refs=("no_existe",), technical_claim="", business_claim="")
        sin_evidencia = _insight("i2", evidence_refs=())
        cap = _capitulo("c1", tables=[_tabla("t1")], figures=[fig, _figura("f2", backing_table_id=None)], insights=[ins, sin_evidencia])
        reporte = _reporte(chapters=[cap])
        self.assertEqual(len(list(reporte.iter_insights())), 2)

    def test_metadata_no_json(self):
        for metadata in ({"a": _Opaco()}, {"a": float("nan")}, {1: "x"}, {"a": {"b": {1, 2}}}, [1]):
            with self.subTest(metadata=repr(metadata)):
                with self.assertRaises(ReportingContractError):
                    _reporte(metadata=metadata)
                with self.assertRaises(ReportingContractError):
                    _capitulo(metadata=metadata)

    def test_metadata_copia_profunda(self):
        metadata = {"a": {"b": [1]}, "t": (1, 2)}
        reporte = _reporte(metadata=metadata)
        capitulo_meta = {"x": [1]}
        cap = _capitulo(metadata=capitulo_meta)
        metadata["a"]["b"].append(2)
        metadata["z"] = 1
        capitulo_meta["x"].append(2)
        self.assertEqual(reporte.metadata, {"a": {"b": [1]}, "t": [1, 2]})
        self.assertEqual(cap.metadata, {"x": [1]})

    def test_to_dict_no_expone_estado_interno(self):
        reporte = _reporte(metadata={"a": [1]})
        volcado = reporte.to_dict()
        volcado["metadata"]["a"].append(2)
        self.assertEqual(reporte.metadata, {"a": [1]})

    def test_schema_version_en_construccion(self):
        self.assertEqual(_reporte().schema_version, 1)
        with self.assertRaises(ReportingContractError):
            _reporte(schema_version=2)

    def test_dataclasses_frozen(self):
        objetos = (
            (_tabla(), "title"),
            (_spec(), "x"),
            (_figura(), "title"),
            (_insight(), "title"),
            (_capitulo(), "title"),
            (_reporte(), "title"),
        )
        for objeto, campo in objetos:
            with self.subTest(contrato=type(objeto).__name__):
                with self.assertRaises(FrozenInstanceError):
                    setattr(objeto, campo, "otro")

    def test_report_sin_generated_at(self):
        self.assertFalse(hasattr(_reporte(), "generated_at"))
        self.assertNotIn("generated_at", _reporte().to_dict())


# ---------------------------------------------------------------------------
# R12 — serialización determinista
# ---------------------------------------------------------------------------


class TestSerializacion(unittest.TestCase):
    def test_hash_independiente_del_orden_de_claves_de_metadata(self):
        r1 = _reporte_completo(metadata={"a": 1, "b": {"x": 1, "y": 2}})
        r2 = _reporte_completo(metadata={"b": {"y": 2, "x": 1}, "a": 1})
        self.assertEqual(r1.content_sha256(), r2.content_sha256())

    def test_roundtrip(self):
        reporte = _reporte_completo()
        recuperado = Report.from_dict(reporte.to_dict())
        self.assertEqual(recuperado, reporte)
        self.assertEqual(recuperado.to_dict(), reporte.to_dict())
        self.assertEqual(recuperado.content_sha256(), reporte.content_sha256())

    def test_roundtrip_via_json(self):
        reporte = _reporte_completo()
        texto = canonical_json(reporte.to_dict())
        recuperado = Report.from_dict(json.loads(texto))
        self.assertEqual(recuperado, reporte)
        self.assertEqual(recuperado.content_sha256(), reporte.content_sha256())

    def test_to_dict_serializable_y_schema_version(self):
        volcado = _reporte_completo().to_dict()
        json.dumps(volcado)
        self.assertEqual(volcado["schema_version"], 1)

    def test_canonical_json_compacto_y_sin_escapar_no_ascii(self):
        texto = canonical_json({"b": "ñandú", "a": [1, 2]})
        self.assertEqual(texto, '{"a":[1,2],"b":"ñandú"}')
        self.assertEqual(
            canonical_json({"z": {"y": None, "x": True}, "a": [1, 2.5, "ñ"]}),
            '{"a":[1,2.5,"ñ"],"z":{"x":true,"y":null}}',
        )

    def test_canonical_json_con_nan(self):
        with self.assertRaises(ReportingContractError):
            canonical_json({"a": float("nan")})
        with self.assertRaises(ReportingContractError):
            canonical_json({"a": _Opaco()})

    def test_hash_hex_sha256_estable(self):
        reporte = _reporte_completo()
        h1 = reporte.content_sha256()
        h2 = _reporte_completo().content_sha256()
        self.assertEqual(h1, h2)
        self.assertEqual(len(h1), 64)
        int(h1, 16)

    def test_cambiar_una_celda_cambia_el_hash(self):
        r1 = _reporte(chapters=[_capitulo("c", tables=[_tabla(rows=(("a", 10, 0.5),))])])
        r2 = _reporte(chapters=[_capitulo("c", tables=[_tabla(rows=(("a", 11, 0.5),))])])
        self.assertNotEqual(r1.content_sha256(), r2.content_sha256())

    def test_from_dict_campo_requerido_ausente(self):
        base = _reporte_completo().to_dict()
        for campo in ("report_id", "title", "report_kind", "decision_scope", "schema_version"):
            with self.subTest(campo):
                datos = dict(base)
                del datos[campo]
                with self.assertRaises(ReportingContractError):
                    Report.from_dict(datos)

    def test_from_dict_schema_version_distinta(self):
        datos = _reporte().to_dict()
        for version in (0, 2, "1", None, True):
            with self.subTest(version=version):
                datos["schema_version"] = version
                with self.assertRaises(ReportingContractError):
                    Report.from_dict(datos)

    def test_from_dict_ignora_claves_desconocidas(self):
        datos = _reporte_completo().to_dict()
        datos["clave_nueva"] = 1
        datos["chapters"][0]["otra"] = 2
        datos["chapters"][0]["tables"][0]["otra"] = 3
        datos["chapters"][0]["figures"][0]["otra"] = 4
        datos["chapters"][0]["figures"][0]["spec"]["otra"] = 5
        datos["chapters"][0]["insights"][0]["otra"] = 6
        self.assertEqual(Report.from_dict(datos), _reporte_completo())

    def test_from_dict_de_cada_contrato_valida_requeridos(self):
        for contrato, datos in (
            (TableArtifact, {"table_id": "t", "title": "T", "columns": ["a"]}),
            (FigureSpec, {"chart_type": "bar"}),
            (FigureArtifact, {"figure_id": "f", "title": "F"}),
            (Insight, {"insight_id": "i"}),
            (Chapter, {"chapter_id": "c"}),
        ):
            with self.subTest(contrato=contrato.__name__):
                with self.assertRaises(ReportingContractError):
                    contrato.from_dict(datos)
                with self.assertRaises(ReportingContractError):
                    contrato.from_dict("no_dict")

    def test_roundtrip_de_cada_contrato(self):
        reporte = _reporte_completo()
        capitulo = reporte.chapters[0]
        for objeto in (
            capitulo.tables[1],
            capitulo.figures[0],
            capitulo.figures[0].spec,
            capitulo.insights[0],
            capitulo,
        ):
            with self.subTest(contrato=type(objeto).__name__):
                self.assertEqual(type(objeto).from_dict(objeto.to_dict()), objeto)


# ---------------------------------------------------------------------------
# Reforzamiento (ciclo reviewer 1): golden de claves, NaT, ids reservados, tipos
# ---------------------------------------------------------------------------


class _NaT:
    """Doble tipo NaT/NA: distinto de sí mismo y con `isoformat()`."""

    def __eq__(self, otro):
        return False

    def __ne__(self, otro):
        return True

    __hash__ = None

    def isoformat(self):
        return "NaT"


class _Multi:
    def item(self):
        raise ValueError("can only convert an array of size 1 to a Python scalar")


class _FloatExterno(float):
    pass


class _IntExterno(int):
    pass


class _StrExterno(str):
    pass


# Cambiar este hash exige bump de SCHEMA_VERSION (ver política de evolución del esquema).
HASH_ESPERADO = "c73128bf96f05972b073bbb3873a1d535759f390218f3c9add5e9274f3519029"

CLAVES_TO_DICT = {
    "TableArtifact": [
        "table_id", "title", "columns", "rows", "units", "column_labels", "description", "sensitive",
    ],
    "FigureSpec": [
        "chart_type", "x", "y", "color", "z", "orientation", "top_n", "sort",
        "x_label", "y_label", "unit", "denominator", "semantic",
    ],
    "FigureArtifact": [
        "figure_id", "title", "spec", "backing_table_id", "description", "alt_text",
        "sensitive", "backend", "backend_payload",
    ],
    "Insight": [
        "insight_id", "technical_claim", "business_claim", "evidence_refs", "population",
        "time_scope", "claim_type", "uncertainty", "title",
    ],
    "Chapter": [
        "chapter_id", "title", "summary", "tables", "figures", "insights", "method_note", "metadata",
    ],
    "Report": [
        "report_id", "title", "report_kind", "decision_scope", "chapters", "summary",
        "conclusion", "metadata", "schema_version",
    ],
}


def _reporte_golden():
    tabla = TableArtifact(
        table_id="tabla_g",
        title="Tabla",
        columns=("grupo", "n", "tasa"),
        rows=(("a", 10, 0.5), ("b", 20, None)),
        units={"tasa": "%"},
        column_labels={"n": "N"},
        description="desc",
        sensitive=False,
    )
    spec = FigureSpec(chart_type="bar", x="grupo", y=("tasa",), denominator="n", semantic="risk")
    figura = FigureArtifact(
        figure_id="fig_g",
        title="Figura",
        spec=spec,
        backing_table_id="tabla_g",
        description="d",
        alt_text="alt",
        backend="motor_x",
        backend_payload={"k": [1, 2]},
    )
    insight = Insight(
        insight_id="ins_g",
        technical_claim="tec",
        business_claim="neg",
        evidence_refs=("tabla_g", "fig_g"),
        population="pob",
        time_scope="tiempo",
        claim_type="comparative",
        uncertainty="baja",
        title="Hallazgo",
    )
    capitulo = Chapter(
        chapter_id="cap_g",
        title="Capitulo",
        summary="res",
        tables=(tabla,),
        figures=(figura,),
        insights=(insight,),
        method_note="nota",
        metadata={"etiqueta": "x"},
    )
    return Report(
        report_id="rep_g",
        title="Reporte",
        report_kind="model",
        decision_scope="model_valid",
        chapters=(capitulo,),
        summary="resumen",
        conclusion="conclusion",
        metadata={"origen": "prueba"},
    )


class TestGoldenClaves(unittest.TestCase):
    def test_claves_exactas_de_to_dict_por_contrato(self):
        reporte = _reporte_golden()
        capitulo = reporte.chapters[0]
        objetos = {
            "TableArtifact": capitulo.tables[0],
            "FigureSpec": capitulo.figures[0].spec,
            "FigureArtifact": capitulo.figures[0],
            "Insight": capitulo.insights[0],
            "Chapter": capitulo,
            "Report": reporte,
        }
        for nombre, objeto in objetos.items():
            with self.subTest(contrato=nombre):
                self.assertEqual(list(objeto.to_dict().keys()), CLAVES_TO_DICT[nombre])

    def test_hash_golden(self):
        if HASH_ESPERADO is None:
            self.skipTest("HASH_ESPERADO pendiente: lo completa el Lead tras correr")
        self.assertEqual(_reporte_golden().content_sha256(), HASH_ESPERADO)

    def test_hash_golden_es_estable_entre_construcciones(self):
        self.assertEqual(_reporte_golden().content_sha256(), _reporte_golden().content_sha256())


class TestIdsReservadosDeWindows(unittest.TestCase):
    def test_reservados_rechazados_en_los_5_contratos(self):
        for valor in ("con", "prn", "aux", "nul", "com1", "com9", "lpt1", "lpt9"):
            with self.subTest(valor=valor):
                with self.assertRaises(ReportingContractError):
                    _tabla(table_id=valor)
                with self.assertRaises(ReportingContractError):
                    _figura(figure_id=valor)
                with self.assertRaises(ReportingContractError):
                    _insight(insight_id=valor)
                with self.assertRaises(ReportingContractError):
                    _capitulo(chapter_id=valor)
                with self.assertRaises(ReportingContractError):
                    _reporte(report_id=valor)

    def test_reservados_tambien_en_referencias(self):
        with self.assertRaises(ReportingContractError):
            _figura(backing_table_id="nul")
        with self.assertRaises(ReportingContractError):
            _insight(evidence_refs=("com1",))

    def test_parecidos_no_reservados_son_validos(self):
        for valor in ("console", "com10", "com0", "lpt10", "nulo", "con1"):
            with self.subTest(valor=valor):
                self.assertEqual(_tabla(table_id=valor).table_id, valor)
                self.assertEqual(_figura(figure_id=valor).figure_id, valor)
                self.assertEqual(_insight(insight_id=valor).insight_id, valor)
                self.assertEqual(_capitulo(chapter_id=valor).chapter_id, valor)
                self.assertEqual(_reporte(report_id=valor).report_id, valor)


class TestRobustezDeCoercion(unittest.TestCase):
    def test_nat_es_none(self):
        frame = _FrameSinAstype(["a", "b"], [[_NaT(), 1]])
        t = TableArtifact.from_frame(frame, table_id="t", title="T")
        self.assertEqual(t.rows, ((None, 1),))

    def test_nan_float_sigue_siendo_none(self):
        frame = _FrameSinAstype(["a"], [[float("nan")], [float("inf")]])
        t = TableArtifact.from_frame(frame, table_id="t", title="T")
        self.assertEqual(t.rows, ((None,), (None,)))

    def test_item_multi_elemento_es_error_de_contrato(self):
        frame = _FrameSinAstype(["a"], [[_Multi()]])
        with self.assertRaises(ReportingContractError):
            TableArtifact.from_frame(frame, table_id="t", title="T")

    def test_columns_none_es_error_de_contrato(self):
        frame = _FrameSinAstype(["a"], [[1]])
        frame.columns = None
        with self.assertRaises(ReportingContractError):
            TableArtifact.from_frame(frame, table_id="t", title="T")

    def test_metadata_circular_es_error_de_contrato(self):
        circular: dict = {}
        circular["a"] = circular
        with self.assertRaises(ReportingContractError):
            _reporte(metadata=circular)
        with self.assertRaises(ReportingContractError):
            _figura(backend="x", backend_payload=circular)

    def test_celdas_devuelven_tipos_nativos_en_constructor_directo(self):
        t = _tabla(rows=((_StrExterno("a"), _IntExterno(3), _FloatExterno(0.5)),))
        fila = t.rows[0]
        self.assertIs(type(fila[0]), str)
        self.assertIs(type(fila[1]), int)
        self.assertIs(type(fila[2]), float)

    def test_celdas_devuelven_tipos_nativos_en_from_frame(self):
        frame = _FrameSinAstype(
            ["a", "b", "c"], [[_StrExterno("a"), _IntExterno(3), _FloatExterno(0.5)]]
        )
        fila = TableArtifact.from_frame(frame, table_id="t", title="T").rows[0]
        self.assertIs(type(fila[0]), str)
        self.assertIs(type(fila[1]), int)
        self.assertIs(type(fila[2]), float)


class TestChequeosDeTipo(unittest.TestCase):
    def test_textos_no_str_son_error(self):
        casos = {
            "tabla.title": lambda: _tabla(title=5),
            "tabla.description": lambda: _tabla(description=5),
            "figura.title": lambda: _figura(title=5),
            "figura.description": lambda: _figura(description=None),
            "figura.alt_text": lambda: _figura(alt_text=5),
            "capitulo.title": lambda: _capitulo(title=5),
            "capitulo.summary": lambda: _capitulo(summary=5),
            "capitulo.method_note": lambda: _capitulo(method_note=5),
            "reporte.title": lambda: _reporte(title=5),
            "reporte.summary": lambda: _reporte(summary=5),
            "reporte.conclusion": lambda: _reporte(conclusion=5),
        }
        for nombre, construir in casos.items():
            with self.subTest(nombre):
                with self.assertRaises(ReportingContractError):
                    construir()

    def test_sensitive_no_bool_es_error(self):
        for valor in (1, 0, "si", None):
            with self.subTest(valor=valor):
                with self.assertRaises(ReportingContractError):
                    _tabla(sensitive=valor)
                with self.assertRaises(ReportingContractError):
                    _figura(sensitive=valor)

    def test_chapters_con_elemento_no_chapter(self):
        with self.assertRaises(ReportingContractError):
            _reporte(chapters=[_tabla()])
        with self.assertRaises(ReportingContractError):
            _reporte(chapters=[{"chapter_id": "c"}])
        with self.assertRaises(ReportingContractError):
            _reporte(chapters=_capitulo())

    def test_schema_version_bool_en_construccion(self):
        with self.assertRaises(ReportingContractError):
            _reporte(schema_version=True)

    def test_orden_de_accesores_entre_dos_capitulos(self):
        c1 = _capitulo("c1", tables=[_tabla("t_b"), _tabla("t_a")], figures=[_figura("f_b")])
        c2 = _capitulo("c2", tables=[_tabla("t_c")], figures=[_figura("f_a"), _figura("f_c")])
        reporte = _reporte(chapters=[c1, c2])
        self.assertEqual([t.table_id for t in reporte.iter_tables()], ["t_b", "t_a", "t_c"])
        self.assertEqual([f.figure_id for f in reporte.iter_figures()], ["f_b", "f_a", "f_c"])

    def test_backend_payload_no_expone_estado_interno(self):
        fig = _figura(backend="x", backend_payload={"a": [1]})
        volcado = fig.to_dict()
        volcado["backend_payload"]["a"].append(2)
        volcado["backend_payload"]["nuevo"] = 1
        self.assertEqual(fig.backend_payload, {"a": [1]})


if __name__ == "__main__":
    unittest.main()

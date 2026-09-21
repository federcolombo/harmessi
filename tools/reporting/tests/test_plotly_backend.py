"""Tests de `tools/reporting/plotly_backend.py` (v0.6 Change 4, `20260918-reporting-design-system-and-html-renderer`).

Deterministas: sin red, sin aleatoriedad, sin pandas y SIN el paquete `plotly`
(se simula con `mock.patch.dict(sys.modules, ...)`). El style sale de
`default_style()` / `merge_style` reales de `style.py` (los tokens esperados se
leen del propio style, sin valores inventados). Fixtures 100% genericos.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from tools.reporting import plotly_backend
from tools.reporting.core import FigureArtifact, FigureSpec, TableArtifact
from tools.reporting.plotly_backend import BackendPayloadError, build_figure, find_plotly_bundle
from tools.reporting.style import default_style, format_number, merge_style, style_to_dict

FUENTE_MODULO = Path(plotly_backend.__file__)


def _style_es():
    return merge_style(default_style(), {"editorial": {"locale": "es"}})


def _style_con_ruta(ruta):
    """Style por defecto con `chart.plotly_js_file` forzado (permite rutas invalidas
    que `merge_style` rechazaria, para probar la defensa de `find_plotly_bundle`)."""
    style = default_style()
    object.__setattr__(style.visual.chart, "plotly_js_file", ruta)
    return style


def _tabla(columns, rows, units=None, labels=None, table_id="tabla_base"):
    return TableArtifact(
        table_id=table_id,
        title="Tabla de respaldo",
        columns=tuple(columns),
        rows=tuple(tuple(r) for r in rows),
        units=units or {},
        column_labels=labels or {},
    )


def _figura(spec, title="Titulo orientado al lector", **kwargs):
    return FigureArtifact(figure_id="fig_base", title=title, spec=spec, backing_table_id="tabla_base", **kwargs)


def _hash(obj) -> str:
    return hashlib.sha256(json.dumps(obj.to_dict(), sort_keys=True).encode("utf-8")).hexdigest()


def _tabla_barras(n=4):
    return _tabla(
        ("grupo", "tasa", "n"),
        [(f"g{i}", 0.1 * (i + 1) / 10, 100 * (i + 1)) for i in range(n)],
        units={"tasa": "proporción (0 a 1)", "n": "registros"},
        labels={"grupo": "Grupo", "tasa": "Tasa", "n": "Registros"},
    )


def _serializable(payload) -> str:
    return json.dumps(payload, allow_nan=False, sort_keys=True)


class VarianteYPurezaTests(unittest.TestCase):
    def setUp(self):
        self.style = default_style()
        self.tabla = _tabla_barras()
        self.figura = _figura(FigureSpec(chart_type="bar", x="grupo", y=("tasa",), x_label="Grupo", y_label="Tasa"))

    def test_variante_invalida_lanza_value_error(self):
        for variante in ("otra", "", "SCREEN", None, 3):
            with self.subTest(variante=variante):
                with self.assertRaises(ValueError):
                    build_figure(self.figura, self.tabla, self.style, variante)

    def test_screen_y_print_difieren_en_chrome_y_colorway(self):
        screen = build_figure(self.figura, self.tabla, self.style, "screen")
        impreso = build_figure(self.figura, self.tabla, self.style, "print")
        self.assertEqual(set(screen), {"data", "layout"})
        for clave in ("paper_bgcolor", "plot_bgcolor", "colorway"):
            self.assertNotEqual(screen["layout"][clave], impreso["layout"][clave], clave)
        self.assertNotEqual(screen["layout"]["font"]["color"], impreso["layout"]["font"]["color"])
        self.assertNotEqual(screen["layout"]["xaxis"]["gridcolor"], impreso["layout"]["xaxis"]["gridcolor"])
        # Los tokens salen del style (paleta y ChartTheme por variante).
        v = self.style.visual
        self.assertEqual(screen["layout"]["paper_bgcolor"], v.screen.surface)
        self.assertEqual(impreso["layout"]["paper_bgcolor"], v.print.surface)
        self.assertEqual(screen["layout"]["plot_bgcolor"], v.screen.surface_alt)
        self.assertEqual(screen["layout"]["font"]["color"], v.screen.text)
        self.assertEqual(impreso["layout"]["font"]["color"], v.print.text)
        self.assertEqual(screen["layout"]["font"]["family"], v.chart.screen.font_family)
        self.assertEqual(screen["layout"]["font"]["size"], v.chart.screen.font_size)
        self.assertEqual(screen["layout"]["xaxis"]["gridcolor"], v.chart.screen.grid_color)
        self.assertEqual(screen["layout"]["colorway"], list(v.chart.screen.colorway))
        self.assertEqual(impreso["layout"]["colorway"], list(v.chart.print.colorway))
        self.assertEqual(screen["data"][0]["marker"]["color"], v.chart.screen.colorway[0])
        self.assertEqual(impreso["data"][0]["marker"]["color"], v.chart.print.colorway[0])

    def test_payloads_son_json_puros_e_independientes(self):
        screen = build_figure(self.figura, self.tabla, self.style, "screen")
        impreso = build_figure(self.figura, self.tabla, self.style, "print")
        self.assertIsInstance(json.loads(_serializable(screen)), dict)
        self.assertIsInstance(json.loads(_serializable(impreso)), dict)
        antes = _serializable(impreso)
        screen["layout"]["paper_bgcolor"] = "#mutado"
        screen["data"].append({"type": "bar"})
        self.assertEqual(_serializable(impreso), antes)
        self.assertNotIn("#mutado", _serializable(build_figure(self.figura, self.tabla, self.style, "screen")))

    def test_no_muta_figura_tabla_ni_style(self):
        style = default_style()
        style_antes = style_to_dict(style)
        hash_fig, hash_tabla = _hash(self.figura), _hash(self.tabla)
        dict_fig = copy.deepcopy(self.figura.to_dict())
        for variante in ("screen", "print"):
            resultado = build_figure(self.figura, self.tabla, style, variante)
            # Mutar la salida tampoco debe alcanzar a los artefactos ni al style.
            resultado["layout"]["title"]["text"] = "mutado"
            resultado["layout"]["colorway"].append("#mutado")
            resultado["data"][0]["x"].append("zzz")
        self.assertEqual(_hash(self.figura), hash_fig)
        self.assertEqual(_hash(self.tabla), hash_tabla)
        self.assertEqual(self.figura.to_dict(), dict_fig)
        self.assertEqual(style_to_dict(style), style_antes)
        self.assertEqual(style_to_dict(style), style_to_dict(default_style()))

    def test_style_ausente_o_invalido_usa_default_style(self):
        esperado = _serializable(build_figure(self.figura, self.tabla, default_style(), "screen"))
        for style in (None, {}, types.SimpleNamespace()):
            with self.subTest(style=style):
                self.assertEqual(_serializable(build_figure(self.figura, self.tabla, style, "screen")), esperado)

    def test_override_valido_via_merge_style_se_refleja(self):
        style = merge_style(
            default_style(),
            {
                "visual": {
                    "screen": {"text": "#123456"},
                    "chart": {"screen": {"grid_color": "#0a0b0c", "font_size": 15}},
                }
            },
        )
        screen = build_figure(self.figura, self.tabla, style, "screen")["layout"]
        impreso = build_figure(self.figura, self.tabla, style, "print")["layout"]
        self.assertEqual(screen["font"]["color"], "#123456")
        self.assertEqual(screen["xaxis"]["gridcolor"], "#0a0b0c")
        self.assertEqual(screen["font"]["size"], 15)
        self.assertEqual(impreso["font"]["color"], default_style().visual.print.text)
        # Y el default posterior queda intacto.
        self.assertNotEqual(default_style().visual.screen.text, "#123456")

    def test_legend_position_none_oculta_la_leyenda(self):
        style = merge_style(default_style(), {"visual": {"chart": {"screen": {"legend_position": "none"}}}})
        tabla = _tabla(("mes", "v", "s"), [("m1", 1, "a"), ("m1", 2, "b")])
        figura = _figura(FigureSpec(chart_type="bar", x="mes", y=("v",), color="s"))
        self.assertFalse(build_figure(figura, tabla, style, "screen")["layout"]["showlegend"])
        self.assertTrue(build_figure(figura, tabla, style, "print")["layout"]["showlegend"])

    def test_determinismo(self):
        a = _serializable(build_figure(self.figura, self.tabla, self.style, "screen"))
        b = _serializable(build_figure(self.figura, self.tabla, default_style(), "screen"))
        c = _serializable(build_figure(_figura(self.figura.spec), _tabla_barras(), default_style(), "screen"))
        self.assertEqual(a, b)
        self.assertEqual(a, c)
        # Orden de claves estable sin sort_keys.
        d1 = json.dumps(build_figure(self.figura, self.tabla, self.style, "print"))
        d2 = json.dumps(build_figure(self.figura, self.tabla, self.style, "print"))
        self.assertEqual(d1, d2)


class ReglasDeChartStylingTests(unittest.TestCase):
    def setUp(self):
        self.style = default_style()

    def test_titulo_tal_cual(self):
        figura = _figura(FigureSpec(chart_type="bar", x="grupo", y=("tasa",)), title="  Título <b>tal</b> cual & sin tocar ")
        payload = build_figure(figura, _tabla_barras(), self.style, "screen")
        self.assertEqual(payload["layout"]["title"]["text"], "  Título <b>tal</b> cual & sin tocar ")

    def test_unidades_visibles_desde_spec(self):
        figura = _figura(
            FigureSpec(chart_type="bar", x="grupo", y=("tasa",), x_label="Grupo", y_label="Tasa observada", unit="proporción")
        )
        layout = build_figure(figura, _tabla_barras(), self.style, "screen")["layout"]
        self.assertEqual(layout["yaxis"]["title"]["text"], "Tasa observada (proporción)")
        self.assertEqual(layout["xaxis"]["title"]["text"], "Grupo")

    def test_unidades_desde_tabla_si_el_spec_no_las_trae(self):
        figura = _figura(FigureSpec(chart_type="bar", x="grupo", y=("tasa",)))
        layout = build_figure(figura, _tabla_barras(), self.style, "screen")["layout"]
        self.assertEqual(layout["yaxis"]["title"]["text"], "Tasa (proporción (0 a 1))")
        self.assertEqual(layout["xaxis"]["title"]["text"], "Grupo")

    def test_tasa_con_denominador_muestra_n_en_texto_y_hover(self):
        tabla = _tabla(
            ("grupo", "tasa", "n"),
            [("a", 0.1234, 1500), ("b", 0.5, 20)],
            labels={"grupo": "Grupo", "tasa": "Tasa", "n": "Registros"},
        )
        figura = _figura(FigureSpec(chart_type="bar", x="grupo", y=("tasa",), denominator="n"))
        traza = build_figure(figura, tabla, self.style, "screen")["data"][0]
        self.assertEqual(
            traza["text"],
            [
                f"{format_number(0.1234, 3, locale=self.style)} (n={format_number(1500, 0, locale=self.style)})",
                f"{format_number(0.5, 3, locale=self.style)} (n={format_number(20, 0, locale=self.style)})",
            ],
        )
        self.assertEqual(traza["text"][0], "0.123 (n=1,500)")
        self.assertTrue(all("(n=" in h for h in traza["hovertext"]))
        self.assertIn("a: 0.123", traza["hovertext"][0])

    def test_sin_denominador_no_hay_n(self):
        tabla = _tabla(("grupo", "tasa"), [("a", 0.1), ("b", 0.2)])
        figura = _figura(FigureSpec(chart_type="bar", x="grupo", y=("tasa",)))
        traza = build_figure(figura, tabla, self.style, "screen")["data"][0]
        self.assertNotIn("(n=", json.dumps(traza))

    def test_leyenda_con_titulo_de_la_columna_de_color(self):
        tabla = _tabla(
            ("mes", "valor", "segmento"),
            [("m1", 1, "s1"), ("m1", 2, "s2"), ("m2", 3, "s1"), ("m2", 4, "s2")],
            labels={"segmento": "Segmento de análisis"},
        )
        figura = _figura(FigureSpec(chart_type="line", x="mes", y=("valor",), color="segmento"))
        payload = build_figure(figura, tabla, self.style, "print")
        self.assertEqual(payload["layout"]["legend"]["title"]["text"], "Segmento de análisis")
        self.assertTrue(payload["layout"]["showlegend"])
        self.assertEqual([t["name"] for t in payload["data"]], ["s1", "s2"])

    def test_etiquetas_largas_horizontal_automargin_sin_truncar(self):
        largas = [f"Categoría con etiqueta muy larga número {i:02d}" for i in range(12)]
        tabla = _tabla(("grupo", "valor"), [(c, i + 1) for i, c in enumerate(largas)])
        figura = _figura(FigureSpec(chart_type="bar", x="grupo", y=("valor",)))
        payload = build_figure(figura, tabla, self.style, "screen")
        traza, layout = payload["data"][0], payload["layout"]
        self.assertEqual(traza["orientation"], "h")
        self.assertEqual(traza["y"], largas)  # completas y en orden
        self.assertEqual(layout["yaxis"]["categoryarray"], largas)
        self.assertTrue(layout["xaxis"]["automargin"])
        self.assertTrue(layout["yaxis"]["automargin"])
        chicas = build_figure(
            figura, _tabla(("grupo", "valor"), [(c, i + 1) for i, c in enumerate(largas[:5])]), self.style, "screen"
        )
        self.assertGreater(layout["height"], chicas["layout"]["height"])
        self.assertLessEqual(layout["height"], plotly_backend.ALTO_MAX)

    def test_umbral_de_18_caracteres_y_orientacion_explicita(self):
        exacta = "x" * 18
        pasa = "x" * 19
        spec = FigureSpec(chart_type="bar", x="grupo", y=("valor",))
        vertical = build_figure(_figura(spec), _tabla(("grupo", "valor"), [(exacta, 1), ("b", 2)]), self.style, "screen")
        horizontal = build_figure(_figura(spec), _tabla(("grupo", "valor"), [(pasa, 1), ("b", 2)]), self.style, "screen")
        self.assertEqual(vertical["data"][0]["orientation"], "v")
        self.assertEqual(vertical["layout"]["height"], plotly_backend.ALTO_BASE)
        self.assertEqual(horizontal["data"][0]["orientation"], "h")
        spec_h = FigureSpec(chart_type="bar", x="grupo", y=("valor",), orientation="h")
        forzada = build_figure(_figura(spec_h), _tabla(("grupo", "valor"), [("a", 1), ("b", 2)]), self.style, "screen")
        self.assertEqual(forzada["data"][0]["orientation"], "h")

    def test_semantico_risk_case_insensitive_y_desconocidos_a_paleta(self):
        tabla = _tabla(
            ("nivel", "valor"),
            [("LOW", 1), ("Medium", 2), ("high", 3), ("raro", 4), ("otro", 5)],
        )
        figura = _figura(FigureSpec(chart_type="bar", x="nivel", y=("valor",), semantic="risk"))
        for variante in ("screen", "print"):
            with self.subTest(variante=variante):
                paleta = getattr(self.style.visual, variante)
                cway = getattr(self.style.visual.chart, variante).colorway
                colores = build_figure(figura, tabla, self.style, variante)["data"][0]["marker"]["color"]
                self.assertEqual(colores[:3], [paleta.risk_low, paleta.risk_medium, paleta.risk_high])
                self.assertEqual(colores[3:], [cway[0], cway[1]])  # sin mapeo => paleta categórica

    def test_semantico_status_por_columna_de_color(self):
        tabla = _tabla(
            ("mes", "valor", "estado"),
            [("m1", 1, "OK"), ("m1", 2, "Warn"), ("m1", 3, "ERROR"), ("m1", 4, "desconocido")],
        )
        figura = _figura(FigureSpec(chart_type="bar", x="mes", y=("valor",), color="estado", semantic="status"))
        payload = build_figure(figura, tabla, self.style, "screen")
        por_nombre = {t["name"]: t["marker"]["color"] for t in payload["data"]}
        paleta = self.style.visual.screen
        self.assertEqual(por_nombre["OK"], paleta.ok)
        self.assertEqual(por_nombre["Warn"], paleta.warn)
        self.assertEqual(por_nombre["ERROR"], paleta.error)
        self.assertEqual(por_nombre["desconocido"], self.style.visual.chart.screen.colorway[0])

    def test_sin_semantico_usa_paleta_categorica(self):
        tabla = _tabla(("nivel", "valor"), [("low", 1), ("high", 2)])
        figura = _figura(FigureSpec(chart_type="bar", x="nivel", y=("valor",)))
        color = build_figure(figura, tabla, self.style, "screen")["data"][0]["marker"]["color"]
        self.assertEqual(color, self.style.visual.chart.screen.colorway[0])

    def test_top_n_recorta_lo_graficado_y_la_tabla_queda_completa(self):
        tabla = _tabla(("grupo", "valor"), [(f"g{i:02d}", i) for i in range(30)])
        hash_tabla = _hash(tabla)
        figura = _figura(FigureSpec(chart_type="bar", x="grupo", y=("valor",), top_n=10, sort="descending"))
        payload = build_figure(figura, tabla, self.style, "screen")
        traza = payload["data"][0]
        categorias = traza["x"]
        self.assertEqual(len(categorias), 10)
        self.assertEqual(categorias, [f"g{i:02d}" for i in range(29, 19, -1)])
        self.assertEqual(len(payload["layout"]["xaxis"]["categoryarray"]), 10)
        self.assertEqual(payload["layout"]["meta"]["categories_total"], 30)
        self.assertEqual(payload["layout"]["meta"]["categories_shown"], 10)
        self.assertEqual(len(tabla.rows), 30)
        self.assertEqual(_hash(tabla), hash_tabla)

    def test_top_n_ascending_y_sin_sort(self):
        tabla = _tabla(("grupo", "valor"), [(f"g{i:02d}", i) for i in range(30)])
        asc = build_figure(
            _figura(FigureSpec(chart_type="bar", x="grupo", y=("valor",), top_n=3, sort="ascending")),
            tabla, self.style, "print",
        )["data"][0]["x"]
        sin_sort = build_figure(
            _figura(FigureSpec(chart_type="bar", x="grupo", y=("valor",), top_n=3)), tabla, self.style, "print"
        )["data"][0]["x"]
        self.assertEqual(asc, ["g00", "g01", "g02"])
        self.assertEqual(sin_sort, ["g00", "g01", "g02"])

    def test_formato_por_locale_del_style(self):
        tabla = _tabla(("grupo", "valor"), [("a", 1234.5), ("b", 2)])
        figura = _figura(FigureSpec(chart_type="bar", x="grupo", y=("valor",)))
        style_es = _style_es()
        en = build_figure(figura, tabla, self.style, "screen")
        es = build_figure(figura, tabla, style_es, "screen")
        self.assertEqual(en["data"][0]["text"], [format_number(1234.5, 2, locale=self.style), "2"])
        self.assertEqual(es["data"][0]["text"], [format_number(1234.5, 2, locale=style_es), "2"])
        self.assertEqual(en["data"][0]["text"][0], "1,234.50")
        self.assertNotEqual(en["data"][0]["text"][0], es["data"][0]["text"][0])
        self.assertIn(es["data"][0]["text"][0], es["data"][0]["hovertext"][0])
        fmt_en, fmt_es = self.style.visual.locale_format, style_es.visual.locale_format
        self.assertEqual(en["layout"]["separators"], fmt_en.decimal_sep + fmt_en.thousands_sep)
        self.assertEqual(es["layout"]["separators"], fmt_es.decimal_sep + fmt_es.thousands_sep)
        self.assertNotEqual(en["layout"]["separators"], es["layout"]["separators"])
        self.assertEqual(en["layout"]["yaxis"]["tickformat"], ",.6~f")

    def test_denominador_usa_el_label_sample_size_del_style(self):
        tabla = _tabla(("grupo", "tasa", "n"), [("a", 0.25, 1500)])
        figura = _figura(FigureSpec(chart_type="bar", x="grupo", y=("tasa",), denominator="n"))
        style_es = _style_es()
        style_propio = merge_style(default_style(), {"editorial": {"labels": {"sample_size": "base={n} casos"}}})
        for style in (self.style, style_es, style_propio):
            with self.subTest(locale=style.editorial.locale, sample_size=style.editorial.label("sample_size")):
                traza = build_figure(figura, tabla, style, "screen")["data"][0]
                rotulo = style.editorial.label("sample_size").replace("{n}", format_number(1500, 0, locale=style))
                valor = format_number(0.25, 3, locale=style)
                self.assertEqual(traza["text"], [f"{valor} ({rotulo})"])
                self.assertTrue(traza["hovertext"][0].endswith(f"({rotulo})"))
        traza = build_figure(figura, tabla, style_propio, "screen")["data"][0]
        self.assertIn("(base=1,500 casos)", traza["text"][0])
        self.assertNotIn("(n=", traza["text"][0])

    def test_grupo_nulo_usa_el_label_not_available(self):
        tabla = _tabla(("mes", "v", "seg"), [("m1", 1, None), ("m1", 2, "s1")])
        figura = _figura(FigureSpec(chart_type="bar", x="mes", y=("v",), color="seg"))
        style_es = _style_es()
        propio = merge_style(default_style(), {"editorial": {"labels": {"not_available": "sin dato"}}})
        for style in (self.style, style_es, propio):
            with self.subTest(locale=style.editorial.locale):
                nombres = [t["name"] for t in build_figure(figura, tabla, style, "screen")["data"]]
                self.assertEqual(nombres, [style.editorial.label("not_available"), "s1"])
                self.assertNotIn("(n/a)", nombres)
        self.assertEqual(build_figure(figura, tabla, propio, "screen")["data"][0]["name"], "sin dato")

    def test_box_con_etiquetas_largas_va_horizontal_y_histograma_no(self):
        largas = ["x" * 19, "b"]
        tabla = _tabla(("grupo", "valor"), [(largas[0], 1), (largas[0], 2), ("b", 5), ("b", 6)])
        box = build_figure(_figura(FigureSpec(chart_type="box", x="grupo", y=("valor",))), tabla, self.style, "screen")
        self.assertEqual(box["data"][0]["orientation"], "h")
        self.assertEqual(box["data"][0]["x"], [1, 2, 5, 6])  # valores en el eje x
        self.assertEqual(box["data"][0]["y"], [largas[0], largas[0], "b", "b"])
        self.assertEqual(box["layout"]["yaxis"]["categoryarray"], largas)
        cortas = _tabla(("grupo", "valor"), [("a", 1), ("b", 2)])
        box_v = build_figure(_figura(FigureSpec(chart_type="box", x="grupo", y=("valor",))), cortas, self.style, "screen")
        self.assertEqual(box_v["data"][0]["orientation"], "v")
        pre = _tabla(("rango", "n"), [("x" * 30, 5), ("b", 7)])
        hist = build_figure(_figura(FigureSpec(chart_type="histogram", x="rango", y=("n",))), pre, self.style, "screen")
        self.assertEqual(hist["data"][0]["orientation"], "v")

    def test_valores_no_numericos_o_nulos_no_lanzan(self):
        tabla = _tabla(("grupo", "valor"), [("a", None), ("b", "texto"), ("c", 3)])
        figura = _figura(FigureSpec(chart_type="bar", x="grupo", y=("valor",)))
        payload = build_figure(figura, tabla, self.style, "screen")
        _serializable(payload)
        self.assertNotIn("tickformat", payload["layout"]["yaxis"])  # eje no numérico

    def test_sin_tabla_devuelve_figura_vacia_json_pura(self):
        figura = _figura(FigureSpec(chart_type="line", x="mes", y=("valor",)))
        payload = build_figure(figura, None, self.style, "print")
        self.assertEqual(payload["data"][0]["x"], [])
        _serializable(payload)


class TiposDeGraficoTests(unittest.TestCase):
    def setUp(self):
        self.style = default_style()

    def _payload(self, spec, tabla, variante="screen"):
        payload = build_figure(_figura(spec), tabla, self.style, variante)
        _serializable(payload)
        self.assertEqual(payload["layout"]["title"]["text"], "Titulo orientado al lector")
        return payload

    def test_bar_vertical(self):
        p = self._payload(FigureSpec(chart_type="bar", x="grupo", y=("tasa",)), _tabla_barras())
        self.assertEqual(p["data"][0]["type"], "bar")
        self.assertEqual(p["data"][0]["orientation"], "v")
        self.assertEqual(p["data"][0]["x"], ["g0", "g1", "g2", "g3"])
        self.assertEqual(p["layout"]["xaxis"]["type"], "category")

    def test_histogram_valores_crudos(self):
        tabla = _tabla(("medida",), [(1.5,), (2.5,), (2.7,), (9.0,)], units={"medida": "kg"}, labels={"medida": "Medida"})
        p = self._payload(FigureSpec(chart_type="histogram", x="medida"), tabla)
        self.assertEqual(p["data"][0]["type"], "histogram")
        self.assertEqual(p["data"][0]["x"], [1.5, 2.5, 2.7, 9.0])
        self.assertEqual(p["layout"]["xaxis"]["title"]["text"], "Medida (kg)")

    def test_histogram_pre_agrupado_es_barra_sin_separacion(self):
        tabla = _tabla(("rango", "n"), [("0-1", 5), ("1-2", 7)])
        p = self._payload(FigureSpec(chart_type="histogram", x="rango", y=("n",)), tabla)
        self.assertEqual(p["data"][0]["type"], "bar")
        self.assertEqual(p["layout"]["bargap"], 0)

    def test_line(self):
        tabla = _tabla(("mes", "valor"), [("2024-01", 1), ("2024-02", 3), ("2024-03", 2)])
        p = self._payload(FigureSpec(chart_type="line", x="mes", y=("valor",)), tabla)
        traza = p["data"][0]
        self.assertEqual(traza["type"], "scatter")
        self.assertEqual(traza["mode"], "lines+markers")
        self.assertEqual(traza["y"], [1, 3, 2])
        self.assertEqual(traza["line"]["width"], self.style.visual.chart.screen.line_width)

    def test_scatter(self):
        tabla = _tabla(("a", "b"), [(1, 2.5), (2, 3.5), (3, 1.0)])
        p = self._payload(FigureSpec(chart_type="scatter", x="a", y=("b",)), tabla)
        self.assertEqual(p["data"][0]["mode"], "markers")
        self.assertEqual(p["data"][0]["marker"]["size"], self.style.visual.chart.screen.marker_size)
        self.assertEqual(p["layout"]["xaxis"]["tickformat"], ",.6~f")
        self.assertEqual(p["layout"]["yaxis"]["tickformat"], ",.6~f")

    def test_box(self):
        tabla = _tabla(("grupo", "valor"), [("a", 1), ("a", 2), ("b", 5), ("b", 6)])
        p = self._payload(FigureSpec(chart_type="box", x="grupo", y=("valor",)), tabla)
        self.assertEqual(p["data"][0]["type"], "box")
        self.assertEqual(p["data"][0]["y"], [1, 2, 5, 6])
        self.assertEqual(p["data"][0]["x"], ["a", "a", "b", "b"])

    def test_heatmap(self):
        tabla = _tabla(
            ("col", "fila", "valor"),
            [("c1", "f1", 1), ("c2", "f1", 2), ("c1", "f2", 3)],
            labels={"valor": "Valor"},
            units={"valor": "unidades"},
        )
        p = self._payload(FigureSpec(chart_type="heatmap", x="col", y=("fila",), z="valor"), tabla)
        traza = p["data"][0]
        self.assertEqual(traza["type"], "heatmap")
        self.assertEqual(traza["x"], ["c1", "c2"])
        self.assertEqual(traza["y"], ["f1", "f2"])
        self.assertEqual(traza["z"], [[1, 2], [3, None]])
        self.assertEqual(traza["colorbar"]["title"]["text"], "Valor (unidades)")
        self.assertEqual(traza["colorscale"][1][1], self.style.visual.screen.accent)
        self.assertFalse(p["layout"]["showlegend"])

    def test_heatmap_etiqueta_con_campos_plotly_no_entra_al_template(self):
        etiqueta = "Valor %{x} %{customdata}"
        tabla = _tabla(("col", "fila", "valor"), [("c1", "f1", 1), ("c2", "f1", 2)], labels={"valor": etiqueta})
        p = self._payload(FigureSpec(chart_type="heatmap", x="col", y=("fila",), z="valor"), tabla)
        traza = p["data"][0]
        self.assertEqual(traza["hovertemplate"], "%{x} · %{y}<br>%{customdata}: %{z}<extra></extra>")
        self.assertNotIn("Valor", traza["hovertemplate"])
        self.assertEqual(traza["customdata"], [[etiqueta, etiqueta]])

    def test_todos_los_tipos_difieren_entre_screen_y_print(self):
        casos = (
            (FigureSpec(chart_type="bar", x="grupo", y=("tasa",)), _tabla_barras()),
            (FigureSpec(chart_type="line", x="grupo", y=("tasa",)), _tabla_barras()),
            (FigureSpec(chart_type="scatter", x="n", y=("tasa",)), _tabla_barras()),
            (FigureSpec(chart_type="box", x="grupo", y=("tasa",)), _tabla_barras()),
            (FigureSpec(chart_type="histogram", x="tasa"), _tabla_barras()),
        )
        for spec, tabla in casos:
            with self.subTest(chart_type=spec.chart_type):
                s = build_figure(_figura(spec), tabla, self.style, "screen")
                i = build_figure(_figura(spec), tabla, self.style, "print")
                self.assertNotEqual(_serializable(s), _serializable(i))
                self.assertNotEqual(s["layout"]["paper_bgcolor"], i["layout"]["paper_bgcolor"])

    def test_payload_del_llamador_con_nan_sale_json_puro(self):
        payload = {"data": [{"type": "bar", "x": ["a"], "y": [float("nan")]}], "layout": {}}
        try:
            figura = _figura(FigureSpec(chart_type="bar", x="g", y=("v",)), backend="plotly", backend_payload=payload)
        except Exception:  # noqa: BLE001 -- el core ya rechaza NaN: nada que probar aquí
            self.skipTest("el core rechaza payloads con NaN")
        try:
            resultado = build_figure(figura, None, self.style, "screen")
        except Exception as exc:  # noqa: BLE001
            self.fail(f"no debe lanzar por contenido: {exc!r}")
        json.dumps(resultado, allow_nan=False)


class BackendPayloadTests(unittest.TestCase):
    PAYLOAD = {
        "data": [{"type": "bar", "x": ["a", "b"], "y": [1, 2], "marker": {"color": "#123456"}}],
        "layout": {
            "paper_bgcolor": "#ffffff",
            "colorway": ["#aaaaaa", "#bbbbbb"],
            "xaxis": {"title": "Eje X", "gridcolor": "#cccccc"},
            "title": "Título del payload",
        },
    }

    def setUp(self):
        self.style = default_style()
        self.payload = copy.deepcopy(self.PAYLOAD)
        self.figura = _figura(FigureSpec(chart_type="bar", x="grupo", y=("tasa",)), backend="plotly", backend_payload=self.payload)
        self.tabla = _tabla_barras()

    def test_retematiza_solo_el_chrome_y_respeta_colores_de_datos(self):
        v = self.style.visual
        screen = build_figure(self.figura, self.tabla, self.style, "screen")
        impreso = build_figure(self.figura, self.tabla, self.style, "print")
        self.assertEqual(screen["layout"]["paper_bgcolor"], v.screen.surface)
        self.assertEqual(impreso["layout"]["paper_bgcolor"], v.print.surface)
        self.assertEqual(screen["layout"]["font"]["color"], v.screen.text)
        self.assertEqual(impreso["layout"]["font"]["color"], v.print.text)
        self.assertEqual(screen["layout"]["xaxis"]["gridcolor"], v.chart.screen.grid_color)
        self.assertNotEqual(screen["layout"]["xaxis"]["gridcolor"], impreso["layout"]["xaxis"]["gridcolor"])
        self.assertEqual(screen["layout"]["xaxis"]["title"]["text"], "Eje X")
        self.assertEqual(screen["layout"]["title"]["text"], "Título del payload")
        for resultado in (screen, impreso):
            self.assertEqual(resultado["data"][0]["marker"]["color"], "#123456")  # dato respetado
            self.assertEqual(resultado["data"][0]["x"], ["a", "b"])
            self.assertEqual(resultado["layout"]["colorway"], ["#aaaaaa", "#bbbbbb"])  # colorway del payload
            _serializable(resultado)

    def test_no_muta_el_payload_original_y_las_copias_son_independientes(self):
        hash_fig = _hash(self.figura)
        screen = build_figure(self.figura, self.tabla, self.style, "screen")
        impreso = build_figure(self.figura, self.tabla, self.style, "print")
        self.assertEqual(self.payload, self.PAYLOAD)
        self.assertEqual(_hash(self.figura), hash_fig)
        screen["data"][0]["marker"]["color"] = "#mutado"
        screen["layout"]["colorway"].append("#x")
        self.assertEqual(impreso["data"][0]["marker"]["color"], "#123456")
        self.assertEqual(impreso["layout"]["colorway"], ["#aaaaaa", "#bbbbbb"])
        self.assertEqual(self.payload, self.PAYLOAD)

    def test_backend_distinto_construye_desde_el_spec(self):
        otra = _figura(FigureSpec(chart_type="bar", x="grupo", y=("tasa",)), backend="otro", backend_payload={"x": 1})
        payload = build_figure(otra, self.tabla, self.style, "screen")
        self.assertEqual(payload["data"][0]["x"], ["g0", "g1", "g2", "g3"])

    def test_sin_backend_construye_desde_el_spec(self):
        sin = _figura(FigureSpec(chart_type="bar", x="grupo", y=("tasa",)))
        payload = build_figure(sin, self.tabla, self.style, "screen")
        self.assertEqual(payload["layout"]["meta"]["figure_id"], "fig_base")
        self.assertEqual(payload["data"][0]["x"], ["g0", "g1", "g2", "g3"])

    def test_payload_sin_data_cae_al_spec(self):
        malo = _figura(
            FigureSpec(chart_type="bar", x="grupo", y=("tasa",)), backend="plotly", backend_payload={"layout": {}}
        )
        payload = build_figure(malo, self.tabla, self.style, "screen")
        self.assertEqual(payload["data"][0]["x"], ["g0", "g1", "g2", "g3"])


class PayloadHostilTests(unittest.TestCase):
    """`backend_payload` es un vector de recursos externos: se rechaza (offline estricto)."""

    def setUp(self):
        self.style = default_style()
        self.tabla = _tabla_barras()

    def _build(self, payload, variante="screen"):
        figura = _figura(FigureSpec(chart_type="bar", x="grupo", y=("tasa",)), backend="plotly", backend_payload=payload)
        return build_figure(figura, self.tabla, self.style, variante)

    def _rechaza(self, payload, clave=None):
        for variante in ("screen", "print"):
            with self.assertRaises(BackendPayloadError) as ctx:
                self._build(payload, variante)
            mensaje = str(ctx.exception)
            self.assertNotIn("http", mensaje)  # sin URLs en el mensaje
            self.assertNotIn("//", mensaje)
            if clave:
                self.assertIn(clave, mensaje)
        self.assertTrue(issubclass(BackendPayloadError, ValueError))

    def test_url_externa_bajo_claves_de_recurso(self):
        for clave in ("source", "style", "url", "href", "topojsonURL", "src", "SOURCE"):
            for valor in ("http://evil.example/x", "https://evil.example/x", "//evil.example/x", "  HTTPS://Evil.example"):
                with self.subTest(clave=clave, valor=valor):
                    payload = {"data": [{"type": "bar", "x": ["a"], "y": [1], clave: valor}], "layout": {}}
                    self._rechaza(payload, clave)

    def test_url_anidada_en_layout_y_en_listas(self):
        self._rechaza({"data": [], "layout": {"geo": {"topojsonURL": "https://evil.example/t.json"}}}, "topojsonURL")
        self._rechaza({"data": [{"type": "bar", "x": [1], "y": [1], "marker": {"source": ["ok", "//evil.example/a"]}}]}, "source")
        self._rechaza({"data": [], "layout": {"mapbox": {"style": "https://evil.example/style.json"}}}, "style")

    def test_layout_images_no_vacio(self):
        self._rechaza({"data": [], "layout": {"images": [{"source": "data:image/png;base64,AAAA"}]}})

    def test_trazas_de_mapa_o_imagen_prohibidas(self):
        for tipo in ("scattergeo", "choropleth", "choroplethmap", "choroplethmapbox", "scattermapbox",
                     "scattermap", "densitymapbox", "densitymap", "image", "Choropleth"):
            with self.subTest(tipo=tipo):
                self._rechaza({"data": [{"type": tipo}], "layout": {}})

    def test_template_con_urls_rechazado_o_descartado(self):
        con_url = {"data": [], "layout": {"template": {"layout": {"images": [{"source": "https://evil.example/i.png"}]}}}}
        self._rechaza(con_url)
        limpio = {"data": [{"type": "bar", "x": ["a"], "y": [1]}], "layout": {"template": {"layout": {"font": {"size": 9}}}}}
        self.assertNotIn("template", self._build(limpio)["layout"])  # se descarta siempre

    def test_payload_legitimo_sigue_pasando(self):
        payload = {
            "data": [
                {"type": "bar", "x": ["a", "b"], "y": [1, 2], "marker": {"color": "#123456"}, "name": "http://no-es-clave"},
                {"type": "heatmap", "z": [[1, 2]], "colorscale": [[0, "#000000"], [1, "#ffffff"]]},
            ],
            "layout": {"images": [], "colorway": ["#aaaaaa"], "title": "Título", "xaxis": {"title": "X"}},
        }
        original = copy.deepcopy(payload)
        for variante in ("screen", "print"):
            resultado = self._build(payload, variante)
            self.assertEqual(resultado["data"], original["data"])  # datos intactos
            self.assertEqual(resultado["layout"]["colorway"], ["#aaaaaa"])
            self.assertEqual(resultado["layout"]["paper_bgcolor"], getattr(self.style.visual, variante).surface)
            _serializable(resultado)
        self.assertEqual(payload, original)


def _plotly_falso(js: str) -> dict:
    off = types.ModuleType("plotly.offline")
    off.get_plotlyjs = lambda: js
    pkg = types.ModuleType("plotly")
    pkg.offline = off
    pkg.__path__ = []
    return {"plotly": pkg, "plotly.offline": off}


PLOTLY_AUSENTE = {"plotly": None, "plotly.offline": None}


class FindPlotlyBundleTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.raiz = Path(self._tmp.name).resolve()
        self.repo = self.raiz / "repo"
        (self.repo / "vendor").mkdir(parents=True)
        (self.repo / "vendor" / "plotly.min.js").write_text("/*Plotly bundle-proyecto*/", encoding="utf-8")

    def _style(self, ruta):
        return _style_con_ruta(ruta)

    def test_archivo_del_proyecto_valido_se_lee_tras_evaluar_el_acceso(self):
        eventos = []

        def acceso(repo, path):
            eventos.append("check")
            return True, ""

        original = Path.read_text

        def leer(self_path, *args, **kwargs):
            eventos.append("read")
            return original(self_path, *args, **kwargs)

        # Ruta declarada de forma valida vía merge_style real.
        style = merge_style(default_style(), {"visual": {"chart": {"plotly_js_file": "vendor/plotly.min.js"}}})
        with mock.patch.dict(sys.modules, PLOTLY_AUSENTE):
            with mock.patch.object(plotly_backend.evidence, "read_allowed", side_effect=acceso) as ra:
                with mock.patch.object(Path, "read_text", autospec=True, side_effect=leer):
                    bundle = find_plotly_bundle(style, self.repo)
        self.assertEqual(bundle, "/*Plotly bundle-proyecto*/")
        self.assertEqual(eventos[0], "check")
        self.assertIn("read", eventos)
        self.assertEqual(ra.call_count, 1)

    def test_archivo_del_proyecto_tiene_prioridad_sobre_plotly_instalado(self):
        with mock.patch.dict(sys.modules, _plotly_falso("/*Plotly instalado*/")):
            with mock.patch.object(plotly_backend.evidence, "read_allowed", return_value=(True, "")):
                self.assertEqual(
                    find_plotly_bundle(self._style("vendor/plotly.min.js"), self.repo), "/*Plotly bundle-proyecto*/"
                )

    def test_acceso_denegado_no_lee_el_archivo(self):
        motivos = []
        with mock.patch.dict(sys.modules, PLOTLY_AUSENTE):
            with mock.patch.object(plotly_backend.evidence, "read_allowed", return_value=(False, "holdout sellado")):
                with mock.patch.object(Path, "read_text", side_effect=AssertionError("no debe leerse")) as leer:
                    bundle = find_plotly_bundle(self._style("vendor/plotly.min.js"), self.repo, motivos)
        self.assertIsNone(bundle)
        leer.assert_not_called()
        self.assertTrue(any("denegada" in m for m in motivos))

    def test_acceso_denegado_cae_a_plotly_instalado(self):
        with mock.patch.dict(sys.modules, _plotly_falso("/*Plotly instalado*/")):
            with mock.patch.object(plotly_backend.evidence, "read_allowed", return_value=(False, "denegado")):
                self.assertEqual(
                    find_plotly_bundle(self._style("vendor/plotly.min.js"), self.repo), "/*Plotly instalado*/"
                )

    def test_ruta_fuera_del_repo_se_ignora_sin_evaluar_ni_leer(self):
        (self.raiz / "fuera.js").write_text("/*fuera*/", encoding="utf-8")
        absoluta = str(self.raiz / "fuera.js")
        for ruta in ("../fuera.js", "vendor/../../fuera.js", absoluta, "/fuera.js", "..\\fuera.js"):
            with self.subTest(ruta=ruta):
                motivos = []
                with mock.patch.dict(sys.modules, PLOTLY_AUSENTE):
                    with mock.patch.object(plotly_backend.evidence, "read_allowed") as ra:
                        with mock.patch.object(Path, "read_text", side_effect=AssertionError("no debe leerse")):
                            self.assertIsNone(find_plotly_bundle(self._style(ruta), self.repo, motivos))
                ra.assert_not_called()
                self.assertTrue(motivos)
                self.assertNotIn(str(self.raiz), " ".join(motivos))  # sin rutas locales

    def test_style_valido_rechaza_rutas_fuera_del_repo(self):
        from tools.reporting.style import StyleError

        for ruta in ("../fuera.js", "/abs.js"):
            with self.subTest(ruta=ruta):
                with self.assertRaises(StyleError):
                    merge_style(default_style(), {"visual": {"chart": {"plotly_js_file": ruta}}})

    def test_secreto_real_denegado_por_el_evaluador_de_acceso(self):
        (self.repo / ".env").write_text("SECRETO-NO-LEER", encoding="utf-8")
        with mock.patch.dict(sys.modules, PLOTLY_AUSENTE):
            self.assertIsNone(find_plotly_bundle(self._style(".env"), self.repo))

    def test_plotly_simulado_presente(self):
        with mock.patch.dict(sys.modules, _plotly_falso("/*Plotly simulado*/")):
            self.assertEqual(find_plotly_bundle(default_style(), self.repo), "/*Plotly simulado*/")

    def test_plotly_simulado_ausente_y_sin_archivo_devuelve_none(self):
        motivos = []
        with mock.patch.dict(sys.modules, PLOTLY_AUSENTE):
            self.assertIsNone(find_plotly_bundle(default_style(), self.repo, motivos))
        self.assertTrue(any("plotly" in m for m in motivos))

    def test_get_plotlyjs_que_falla_o_devuelve_vacio_da_none_sin_lanzar(self):
        off = types.ModuleType("plotly.offline")
        pkg = types.ModuleType("plotly")
        pkg.offline = off
        pkg.__path__ = []
        modulos = {"plotly": pkg, "plotly.offline": off}

        def falla():
            raise RuntimeError("boom")

        for funcion in (falla, lambda: "", lambda: None, lambda: 123):
            with self.subTest(funcion=funcion):
                off.get_plotlyjs = funcion
                with mock.patch.dict(sys.modules, modulos):
                    self.assertIsNone(find_plotly_bundle(default_style(), self.repo))

    def test_nunca_lanza_con_entradas_raras(self):
        with mock.patch.dict(sys.modules, PLOTLY_AUSENTE):
            for style, repo in (
                (None, None),
                (None, self.repo),
                ({}, 12345),
                (self._style(7), self.repo),
                (self._style("vendor/no_existe.js"), self.repo),
                (self._style("vendor"), self.repo),
            ):
                with self.subTest(style=style, repo=repo):
                    with mock.patch.object(plotly_backend.evidence, "read_allowed", return_value=(True, "")):
                        self.assertIsNone(find_plotly_bundle(style, repo))

    def test_bundle_sin_plotly_se_ignora_con_motivo_generico(self):
        (self.repo / "vendor" / "otro.js").write_text("console.log('nada');", encoding="utf-8")
        motivos = []
        with mock.patch.dict(sys.modules, PLOTLY_AUSENTE):
            with mock.patch.object(plotly_backend.evidence, "read_allowed", return_value=(True, "")):
                self.assertIsNone(find_plotly_bundle(self._style("vendor/otro.js"), self.repo, motivos))
        self.assertIn("bundle sin Plotly", motivos)
        # Y no bloquea el paso 2 si plotly instalado sí es válido.
        with mock.patch.dict(sys.modules, _plotly_falso("/*Plotly instalado*/")):
            with mock.patch.object(plotly_backend.evidence, "read_allowed", return_value=(True, "")):
                self.assertEqual(find_plotly_bundle(self._style("vendor/otro.js"), self.repo), "/*Plotly instalado*/")

    def test_get_plotlyjs_sin_plotly_se_ignora_con_motivo_generico(self):
        motivos = []
        with mock.patch.dict(sys.modules, _plotly_falso("var x = 1;")):
            self.assertIsNone(find_plotly_bundle(default_style(), self.repo, motivos))
        self.assertIn("bundle sin Plotly", motivos)

    def test_archivo_vacio_se_ignora(self):
        (self.repo / "vendor" / "vacio.js").write_text("   \n", encoding="utf-8")
        with mock.patch.dict(sys.modules, PLOTLY_AUSENTE):
            with mock.patch.object(plotly_backend.evidence, "read_allowed", return_value=(True, "")):
                self.assertIsNone(find_plotly_bundle(self._style("vendor/vacio.js"), self.repo))


class ArquitecturaDelModuloTests(unittest.TestCase):
    def setUp(self):
        self.arbol = ast.parse(FUENTE_MODULO.read_text(encoding="utf-8"))

    @staticmethod
    def _menciona_plotly(nodo) -> bool:
        if isinstance(nodo, ast.Import):
            return any(a.name.split(".")[0] == "plotly" for a in nodo.names)
        return isinstance(nodo, ast.ImportFrom) and (nodo.module or "").split(".")[0] == "plotly"

    def test_no_importa_plotly_a_nivel_de_modulo(self):
        for nodo in self.arbol.body:
            self.assertFalse(self._menciona_plotly(nodo), "import de plotly a nivel de módulo")

    def test_el_unico_import_de_plotly_esta_en_find_plotly_bundle(self):
        encontrados = []
        for funcion in ast.walk(self.arbol):
            if isinstance(funcion, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for nodo in ast.walk(funcion):
                    if self._menciona_plotly(nodo):
                        encontrados.append(funcion.name)
        self.assertTrue(encontrados)
        self.assertEqual(set(encontrados), {"find_plotly_bundle"})
        total = [n for n in ast.walk(self.arbol) if self._menciona_plotly(n)]
        self.assertEqual(len(total), 1)

    def test_solo_stdlib_y_reporting_sin_red_ni_pandas(self):
        permitidos = {"__future__", "json", "math", "re", "collections", "pathlib", "typing"}
        prohibidos = {"pandas", "numpy", "plotly", "socket", "urllib", "http", "requests", "ssl", "subprocess"}
        for nodo in ast.walk(self.arbol):
            if isinstance(nodo, ast.Import):
                raices = {a.name.split(".")[0] for a in nodo.names}
            elif isinstance(nodo, ast.ImportFrom):
                if nodo.level >= 1:
                    continue  # imports relativos del propio paquete reporting
                raices = {(nodo.module or "").split(".")[0]}
            else:
                continue
            raices.discard("plotly")  # cubierto por el test del import perezoso
            self.assertFalse(raices & prohibidos, raices)
            self.assertTrue(raices <= permitidos, raices - permitidos)

    def test_api_publica(self):
        self.assertEqual(plotly_backend.VARIANTES, ("screen", "print"))
        self.assertTrue(callable(plotly_backend.build_figure))
        self.assertTrue(callable(plotly_backend.find_plotly_bundle))


if __name__ == "__main__":
    unittest.main()

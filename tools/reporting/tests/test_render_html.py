"""Tests de `tools/reporting/render_html.py` (v0.6 Change 4, tanda C: renderer HTML).

Deterministas: sin red, sin plotly real (bundle JS FALSO), sin aleatoriedad, sin pandas,
sin archivos (el manifest se arma a mano). Reportes genericos sinteticos.
"""
from __future__ import annotations

import ast
import json
import re
import unittest
from html.parser import HTMLParser
from pathlib import Path
from unittest import mock

from tools.reporting import core
from tools.reporting import render_html as rh
from tools.reporting.examples.eda_generic import build_example_report
from tools.reporting.render_html import render_report_html
from tools.reporting.style import default_style, merge_style, style_to_dict

FAKE_BUNDLE = "/* fake plotly.js */ window.Plotly = window.Plotly || {newPlot(){}, react(){}};"
XSS = "<script>alert(1)</script>"
XSS_ESC = "&lt;script&gt;alert(1)&lt;/script&gt;"


# --- Helpers ---------------------------------------------------------------------------


def _manifest(report, **over):
    m = {
        "report_id": report.report_id,
        "run_id": "run-test-1",
        "report_kind": report.report_kind,
        "decision_scope": report.decision_scope,
        "data_cutoff": "2024-12-31",
        "git_commit": "0123456789abcdef0123456789abcdef01234567",
        "git_dirty": False,
        "harmessi_version": "0.6.0-test",
        "generated_at": "2026-09-21T10:00:00Z",
        "sources": [{
            "kind": "file", "path": "data/interim/ejemplo.csv", "sha256": "ab" * 32, "rows": 400,
            "min_date": "2024-01-01", "max_date": "2024-12-31", "role": "input",
        }],
        "exclusions": ["Registros sin medida"],
        "holdout_access": "none",
        "sensitivity": {"contains_sensitive": False},
        "hashes": {"report_content": report.content_sha256()},
    }
    m.update(over)
    return m


def _estilo(editorial=None, visual=None):
    over = {}
    if editorial:
        over["editorial"] = editorial
    if visual:
        over["visual"] = visual
    return merge_style(default_style(), over)


def _tabla(table_id="t1", rows=None, sensitive=False, title="Tabla de prueba"):
    rows = rows if rows is not None else [("A", 10, 0.5), ("B", 90, 0.1)]
    return core.TableArtifact.from_rows(
        table_id, title, ("grupo", "n", "tasa"), rows,
        units={"n": "registros", "tasa": "proporción"},
        column_labels={"grupo": "Grupo", "n": "Registros", "tasa": "Tasa"},
        description="Descripción de la tabla", sensitive=sensitive,
    )


def _figura(figure_id="f1", table_id="t1", title="Título de figura", sensitive=False, **spec_kw):
    kw = {"chart_type": "bar", "x": "grupo", "y": ("tasa",), "denominator": "n"}
    kw.update(spec_kw)
    return core.FigureArtifact(
        figure_id, title, core.FigureSpec(**kw), backing_table_id=table_id,
        description="Descripción de la figura", alt_text="Texto alternativo", sensitive=sensitive,
    )


def _insight(insight_id="ins-1", claim_type="descriptive", refs=("t1",), uncertainty="", **kw):
    args = dict(
        insight_id=insight_id, technical_claim="TECH-CLAIM-XYZ", business_claim="BIZ-CLAIM-XYZ",
        evidence_refs=refs, population="POP-XYZ", time_scope="TIME-XYZ",
        claim_type=claim_type, uncertainty=uncertainty,
    )
    args.update(kw)
    return core.Insight(**args)


def _cap(chapter_id="cap", tables=None, figures=None, insights=(), **kw):
    return core.Chapter(
        chapter_id, "Capítulo de prueba", summary="Resumen del capítulo",
        tables=(_tabla(),) if tables is None else tables,
        figures=(_figura(),) if figures is None else figures,
        insights=insights, method_note="Nota de método", **kw,
    )


def _reporte(chapters=None, scope="exploratory", **kw):
    args = dict(
        report_id="rep-prueba", title="Reporte de prueba", report_kind="eda", decision_scope=scope,
        chapters=(_cap(),) if chapters is None else chapters,
        summary="Resumen del reporte", conclusion="Conclusión del reporte",
    )
    args.update(kw)
    return core.Report(**args)


def _render(report=None, style=None, bundle=FAKE_BUNDLE, manifest=None, **kw):
    report = report if report is not None else _reporte()
    style = style if style is not None else default_style()
    manifest = manifest if manifest is not None else _manifest(report)
    return render_report_html(report, manifest, style, plotly_bundle=bundle, **kw)


def _css(out):
    m = re.search(r"<style>(.*?)</style>", out, re.DOTALL)
    return m.group(1) if m else ""


def _payloads(out):
    """{script_id: objeto JSON} de todos los `<script type="application/json">`."""
    return {
        sid: json.loads(cuerpo)
        for sid, cuerpo in re.findall(
            r'<script type="application/json" id="([^"]+)">(.*?)</script>', out, re.DOTALL)
    }


class _Externos(HTMLParser):
    """Recolecta referencias externas fuera de los cuerpos de <script>/<style>."""

    ATRS = ("src", "href", "data", "poster", "action", "srcset", "xlink:href")

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.problemas = []
        self.estilos = []
        self._en_style = False

    def handle_starttag(self, tag, attrs):
        if tag in ("link", "img", "iframe", "object", "embed"):
            self.problemas.append(tag)
        if tag == "style":
            self._en_style = True
        for k, v in attrs:
            if k in self.ATRS and v and v.strip().lower().startswith(("http:", "https:", "//", "ftp:")):
                self.problemas.append(f"{tag}[{k}]")
            if tag == "script" and k == "src":
                self.problemas.append("script[src]")

    def handle_endtag(self, tag):
        if tag == "style":
            self._en_style = False

    def handle_data(self, data):
        if self._en_style:
            self.estilos.append(data)


def _externos(out):
    p = _Externos()
    p.feed(out)
    p.close()
    return p


# --- Determinismo, offline, temas --------------------------------------------------------


class TestDeterminismoYOffline(unittest.TestCase):
    def test_determinista_byte_a_byte(self):
        a, b = build_example_report(), build_example_report()
        h1 = render_report_html(a, _manifest(a), default_style(), plotly_bundle=FAKE_BUNDLE)
        h2 = render_report_html(b, _manifest(b), default_style(), plotly_bundle=FAKE_BUNDLE)
        self.assertEqual(h1.encode("utf-8"), h2.encode("utf-8"))
        self.assertGreater(len(h1), 1000)

    def test_offline_sin_recursos_externos(self):
        rep = build_example_report()
        for bundle in (FAKE_BUNDLE, None):
            out = render_report_html(rep, _manifest(rep), default_style(), plotly_bundle=bundle)
            p = _externos(out)
            self.assertEqual(p.problemas, [], p.problemas)
            css = "".join(p.estilos)
            self.assertNotIn("@import", css)
            self.assertIsNone(re.search(r"url\(\s*['\"]?\s*(https?:)?//", css, re.IGNORECASE))
            self.assertIsNone(re.search(r"<link\b", out, re.IGNORECASE))
            self.assertIsNone(re.search(r"<script[^>]*\bsrc\s*=", out, re.IGNORECASE))

    def test_bundle_hostil_no_cierra_el_script(self):
        bundle = '/* fake */ var s = "</script><img src=http://evil.example/x>"; window.Plotly = {};'
        out = _render(bundle=bundle)
        self.assertEqual(out.count("<script"), out.count("</script>"))
        self.assertEqual(_externos(out).problemas, [])

    def test_dark_en_pantalla_y_claro_en_print(self):
        d = default_style().visual
        antes, sep, despues = _css(_render()).partition("@media print")
        self.assertEqual(sep, "@media print")
        self.assertEqual(antes.count(":root{"), 1)
        self.assertIn("color-scheme:dark", antes)
        for attr, css in (("surface", "surface"), ("text", "text"), ("muted", "muted"),
                          ("border", "border"), ("accent", "accent"), ("risk_high", "risk-high")):
            self.assertIn(f"--{css}:{getattr(d.screen, attr)};", antes)
            self.assertIn(f"--{css}:{getattr(d.print, attr)};", despues)
        self.assertNotIn(d.print.surface, antes)
        self.assertNotIn(d.print.text, antes)
        self.assertNotIn(d.screen.surface, despues)
        self.assertIn("color-scheme:light", despues)

    def test_override_de_style_cambia_los_colores(self):
        st = _estilo(visual={"screen": {"surface": "#010203"}, "print": {"surface": "#fefefe"}})
        antes, _, despues = _css(_render(style=st)).partition("@media print")
        self.assertIn("--surface:#010203;", antes)
        self.assertNotIn(default_style().visual.screen.surface, antes)
        self.assertIn("--surface:#fefefe;", despues)

    def test_lang_y_locale_es(self):
        rep = _reporte(chapters=(_cap(tables=(_tabla(rows=[("A", 3, 1234.5)]),), figures=()),))
        en, es = _render(rep), _render(rep, style=_estilo({"locale": "es"}))
        self.assertIn('<html lang="en">', en)
        self.assertIn("Technical sheet", en)
        self.assertIn("1,234.5", en)
        self.assertIn('<html lang="es">', es)
        self.assertIn("Ficha técnica", es)
        self.assertIn("1.234,5", es)
        self.assertNotIn("Technical sheet", es)

    def test_labels_personalizados(self):
        out = _render(style=_estilo({"labels": {"tech_sheet": "Ficha ZZZ"}}))
        self.assertIn("Ficha ZZZ", out)
        self.assertNotIn("Technical sheet", out)

    def test_no_muta_reporte_ni_style_y_no_lanza_sin_manifest(self):
        rep, st = build_example_report(), default_style()
        h_rep, d_st = rep.content_sha256(), style_to_dict(st)
        out = render_report_html(rep, None, st, plotly_bundle=FAKE_BUNDLE)
        self.assertEqual(rep.content_sha256(), h_rep)
        self.assertEqual(style_to_dict(st), d_st)
        self.assertIn(rep.content_sha256(), out)  # footer: cae al hash calculado
        self.assertIsInstance(render_report_html(rep, {}, "no-es-style"), str)

    def test_sin_datos_privados_ni_rutas_locales(self):
        rep = build_example_report()
        out = render_report_html(rep, _manifest(rep), default_style(), plotly_bundle=FAKE_BUNDLE)
        for prohibido in (str(Path.home()), "C:\\", "\\Users\\", "/home/"):
            self.assertNotIn(prohibido, out)

    def test_modulo_solo_stdlib_y_sin_plotly(self):
        arbol = ast.parse(Path(rh.__file__).read_text(encoding="utf-8"))
        tops = set()
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Import):
                tops |= {a.name.split(".")[0] for a in nodo.names}
            elif isinstance(nodo, ast.ImportFrom) and nodo.level == 0:
                tops.add((nodo.module or "").split(".")[0])
        self.assertLessEqual(tops, {"__future__", "html", "json", "re", "collections", "decimal", "typing"})
        self.assertNotIn("plotly", tops)


# --- Figuras y bundle -----------------------------------------------------------------------


class TestFigurasYBundle(unittest.TestCase):
    def test_dos_payloads_por_figura_y_distintos(self):
        rep = build_example_report()
        d = default_style().visual
        out = render_report_html(rep, _manifest(rep), default_style(), plotly_bundle=FAKE_BUNDLE)
        cargas = _payloads(out)
        figuras = list(rep.iter_figures())
        self.assertGreaterEqual(len(figuras), 3)
        for f in figuras:
            s, p = cargas[f"fig-{f.figure_id}-screen"], cargas[f"fig-{f.figure_id}-print"]
            self.assertNotEqual(s, p)
            self.assertEqual(s["layout"]["paper_bgcolor"], d.screen.surface)
            self.assertEqual(p["layout"]["paper_bgcolor"], d.print.surface)
            self.assertIn(f'id="plot-{f.figure_id}"', out)

    def test_bundle_embebido_una_sola_vez_con_loader(self):
        out = _render()
        self.assertEqual(out.count("/* fake plotly.js */"), 1)
        for marca in ("beforeprint", "afterprint", "matchMedia('print')", "Plotly", "'react'", "newPlot"):
            self.assertIn(marca, out)
        # Sin garantia de que el grafico se dibuje, la tabla de respaldo va abierta.
        self.assertIn('<details class="backing" open>', out)

    def test_con_bundle_cada_figura_lleva_aviso_por_defecto_y_noscript(self):
        aviso = "Figure not rendered: plotly.js bundle not available"
        out = _render()
        m = re.search(r'<div class="plot"[^>]*>(.*?)</div><noscript>(.*?)</noscript>', out, re.DOTALL)
        self.assertIsNotNone(m)
        self.assertIn(aviso, m.group(1))       # aviso dentro del contenedor (lo reemplaza el loader)
        self.assertIn("plot-pending", m.group(1))
        self.assertIn(aviso, m.group(2))       # y el mismo aviso en <noscript>
        self.assertEqual(out.count(aviso), 2)
        # El loader deja el aviso si no hay Plotly, y solo lo reemplaza al graficar con exito.
        self.assertIn("if(!P){return;}", out)
        self.assertIn("el.innerHTML=prev", out)
        self.assertIn("data-drawn", out)

    def test_js_seguro_solo_neutraliza_lo_peligroso(self):
        legitimo = 'var a = "a<!--b"; var re = /<!--x/; var s = "</script>"; var t = "</SCRIPT >";'
        out = _render(bundle=legitimo)
        self.assertIn('"a<!--b"', out)          # `<!--` legitimo intacto
        self.assertIn("/<!--x/", out)
        self.assertIn('"<\\/script>"', out)      # `</script>` escapado
        self.assertIn("<\\/SCRIPT", out)
        self.assertEqual(out.count("<script"), out.count("</script>"))
        peligro = _render(bundle='var x = "<!-- <script>";')
        self.assertNotIn("<!-- <script>", peligro)
        self.assertIn("<\\!-- <script>", peligro)

    def test_sin_bundle_aviso_visible_y_tabla_abierta(self):
        for bundle in (None, "", "   "):
            out = _render(bundle=bundle)
            self.assertIn("Figure not rendered: plotly.js bundle not available", out)
            self.assertIn('<details class="backing" open>', out)
            self.assertNotIn("application/json", out)
            self.assertNotIn("fake plotly.js", out)
            self.assertNotIn("beforeprint", out)
            self.assertIn("Título de figura", out)
            self.assertIn("<td>A</td>", out)

    def test_sin_bundle_aviso_en_es(self):
        out = _render(style=_estilo({"locale": "es"}), bundle=None)
        self.assertIn("Figura no renderizada: bundle de plotly.js no disponible", out)

    def test_falla_del_backend_degrada_sin_lanzar(self):
        with mock.patch("tools.reporting.render_html.build_figure", side_effect=RuntimeError("boom")):
            out = _render()
        self.assertIn("Figure not rendered", out)
        self.assertNotIn("boom", out)
        self.assertNotIn("application/json", out)
        self.assertIn('<details class="backing" open>', out)

    def test_fallo_por_payload_con_recursos_externos_no_filtra_urls(self):
        err = ValueError("backend_payload con recurso externo http://evil.example/x.js")
        with mock.patch("tools.reporting.render_html.build_figure", side_effect=err):
            out = _render()
        self.assertIn("Figure not rendered", out)
        self.assertNotIn("evil.example", out)
        self.assertEqual(_externos(out).problemas, [])

    def test_floats_pequenos_y_sumas_binarias_se_formatean_sin_perdida(self):
        st = default_style()
        self.assertEqual(rh._fmt_celda(1e-7, st), "0.0000001")
        self.assertEqual(rh._fmt_celda(0.1 + 0.2, st), "0.3")
        self.assertEqual(rh._fmt_celda(0.125, st), "0.125")
        self.assertEqual(rh._fmt_celda(2.5, st), "2.5")
        self.assertEqual(rh._fmt_celda(1234, st), "1,234")
        self.assertEqual(rh._fmt_celda(-7, st), "-7")
        self.assertEqual(rh._fmt_celda(1234.5, st), "1,234.5")
        self.assertEqual(rh._fmt_celda(None, st), "")
        es = _estilo({"locale": "es"})
        self.assertEqual(rh._fmt_celda(0.1 + 0.2, es), "0,3")
        self.assertEqual(rh._fmt_celda(1e-7, es), "0,0000001")

    def test_booleanos_sin_idioma(self):
        st = default_style()
        self.assertEqual(rh._fmt_celda(True, st), "✓")
        self.assertEqual(rh._fmt_celda(False, st), "✗")

    def test_top_n_grafico_recortado_y_tabla_completa_con_leyenda(self):
        filas = [(f"G{i:02d}", 10 + i, (i + 1) / 100) for i in range(30)]
        rep = _reporte(chapters=(_cap(
            tables=(_tabla(rows=filas),),
            figures=(_figura(top_n=10, sort="descending"),)),))
        out = _render(rep, manifest=_manifest(rep, sources=[]))
        s = _payloads(out)["fig-f1-screen"]
        self.assertEqual(len(s["data"][0]["x"]), 10)
        self.assertEqual(out.count("<tr>"), 31)  # 1 encabezado + 30 filas
        self.assertIn("Showing 10 of 30", out)
        self.assertIn("<td>G00</td>", out)  # la fila de menor tasa NO se grafica pero sigue en la tabla
        self.assertNotIn("G00", json.dumps(s))
        self.assertIn("G29", json.dumps(s))  # sí se grafican las de mayor tasa

    def test_tabla_numeros_a_la_derecha_y_unidades_en_encabezado(self):
        out = _render(bundle=None)
        self.assertIn('<th scope="col" class="num">Registros <span class="unit">(registros)</span></th>', out)
        self.assertIn('<td class="num">10</td>', out)
        self.assertIn("<td>A</td>", out)
        css = _css(out)
        self.assertIn("text-align:right;font-variant-numeric:tabular-nums", css)
        self.assertIn("overflow-x:auto", css)

    def test_referencia_global_ponderada_y_n(self):
        out = _render()
        self.assertIn("Overall reference (weighted)", out)
        self.assertIn("14.0%", out)      # (10*0.5 + 90*0.1) / 100
        self.assertNotIn("30.0%", out)   # no es el promedio simple
        self.assertIn("n=100", out)
        sin = _render(style=_estilo({"comparative_context": False}))
        self.assertNotIn("Overall reference", sin)
        self.assertIn("n=100", sin)


# --- Escape / XSS --------------------------------------------------------------------------------


def _reporte_xss(v):
    payload = {"data": [{"type": "bar", "x": ["a"], "y": [1], "name": "</script>" + v}],
               "layout": {"title": "<!-- " + v}}
    tabla = core.TableArtifact.from_rows(
        "t1", v, ("grupo", "n"), [(v, 1)], column_labels={"grupo": v, "n": v}, description=v)
    fig = core.FigureArtifact(
        "f1", v, core.FigureSpec(chart_type="bar", x="grupo", y=("n",)),
        backing_table_id="t1", description=v, alt_text=v, backend="plotly", backend_payload=payload)
    ins = core.Insight(
        insight_id="ins-1", technical_claim=v, business_claim=v, evidence_refs=("t1",),
        population=v, time_scope=v, claim_type="causal", uncertainty=v, title=v)
    cap = core.Chapter("cap", v, summary=v, tables=(tabla,), figures=(fig,), insights=(ins,), method_note=v)
    return core.Report("rep-xss", v, "eda", "exploratory", (cap,), summary=v, conclusion=v)


class TestEscape(unittest.TestCase):
    def _render_xss(self, v):
        rep = _reporte_xss(v)
        st = _estilo({"explain_terms": True, "glossary": {v: v}})
        m = _manifest(rep, run_id=v, exclusions=[v], holdout_access=v, harmessi_version=v,
                      sources=[{"path": v, "sha256": v, "rows": 1, "min_date": v, "max_date": v}])
        return render_report_html(rep, m, st, plotly_bundle=FAKE_BUNDLE)

    def test_script_en_todos_los_campos_no_aparece_sin_escapar(self):
        out, base = self._render_xss(XSS), self._render_xss("benigno")
        self.assertNotIn(XSS, out)
        self.assertIn(XSS_ESC, out)
        # Misma cantidad de <script> que con contenido benigno: nada abrio un script nuevo.
        self.assertEqual(out.count("<script"), base.count("<script"))
        self.assertEqual(out.count("</script>"), base.count("</script>"))
        self.assertNotIn("<!--", out)
        self.assertEqual(_externos(out).problemas, [])

    def test_json_de_figuras_escapado_pero_sin_perdida(self):
        out = self._render_xss(XSS)
        cargas = _payloads(out)  # json.loads OK => el JSON sigue siendo valido
        for variante in ("screen", "print"):
            self.assertEqual(cargas[f"fig-f1-{variante}"]["data"][0]["name"], "</script>" + XSS)
        cuerpo = re.search(r'id="fig-f1-screen">(.*?)</script>', out, re.DOTALL).group(1)
        for peligroso in ("<", ">", "&"):
            self.assertNotIn(peligroso, cuerpo)

    def test_comillas_en_atributos_se_escapan(self):
        rep = _reporte(chapters=(_cap(figures=(_figura(title='x" onmouseover="alert(1)'),)),))
        out = _render(rep)
        self.assertNotIn('" onmouseover="', out)


# --- Tabs -------------------------------------------------------------------------------------------


class TestTabs(unittest.TestCase):
    def _reporte_figs(self, n, **cap_kw):
        figs = tuple(_figura(figure_id=f"f{i}", title=f"Figura {i}") for i in range(1, n + 1))
        return _reporte(chapters=(_cap(figures=figs, **cap_kw),))

    def test_dos_figuras_usan_tabs_css_only(self):
        out = _render(self._reporte_figs(2))
        self.assertIn('class="tabs"', out)
        self.assertEqual(out.count('type="radio"'), 2)
        self.assertEqual(out.count(" checked"), 1)
        css = _css(out)
        self.assertIn("#tab-ch-cap-1:checked ~ #panel-ch-cap-1{display:block}", css)
        self.assertIn("#tab-ch-cap-2:checked ~ #panel-ch-cap-2{display:block}", css)
        self.assertIn(".tab-panel{display:none}", css)
        self.assertIn(".tab-panel{display:block !important}", css.partition("@media print")[2])

    def test_layout_stack_desactiva_tabs(self):
        out = _render(self._reporte_figs(2, metadata={"layout": "stack"}))
        self.assertNotIn('class="tabs"', out)
        self.assertNotIn('type="radio"', out)
        self.assertIn("Figura 1", out)
        self.assertIn("Figura 2", out)

    def test_una_figura_no_usa_tabs(self):
        self.assertNotIn('type="radio"', _render(self._reporte_figs(1)))

    def test_tabs_como_funcion_pura(self):
        html_tabs = rh.render_tabs("g", [("Uno", "<p>1</p>"), ("Dos", "<p>2</p>")])
        self.assertEqual(html_tabs, rh.render_tabs("g", [("Uno", "<p>1</p>"), ("Dos", "<p>2</p>")]))
        self.assertIn('for="tab-g-2"', html_tabs)


# --- Sensibles --------------------------------------------------------------------------------------


class TestSensibles(unittest.TestCase):
    def _reporte_sensible(self):
        tabla = _tabla(rows=[("SECRETO-123", 5, 0.4)], sensitive=True, title="Tabla reservada")
        fig = _figura(title="Figura reservada")
        return _reporte(chapters=(_cap(tables=(tabla,), figures=(fig,)),))

    def test_omitidos_por_defecto(self):
        out = _render(self._reporte_sensible())
        self.assertNotIn("SECRETO-123", out)  # ni en celdas ni en el JSON de figuras
        self.assertNotIn("Figura reservada", out)
        self.assertNotIn("Tabla reservada", out)
        self.assertNotIn("application/json", out)
        self.assertIn("Sensitive content omitted", out)

    def test_incluidos_con_include_sensitive(self):
        out = _render(self._reporte_sensible(), include_sensitive=True)
        self.assertIn("SECRETO-123", out)
        self.assertIn("Figura reservada", out)
        self.assertIn("SECRETO-123", _payloads(out)["fig-f1-screen"]["data"][0]["x"])

    def test_figura_sensible_con_tabla_no_sensible(self):
        rep = _reporte(chapters=(_cap(figures=(_figura(title="Figura marcada", sensitive=True),)),))
        out = _render(rep)
        self.assertNotIn("Figura marcada", out)
        self.assertNotIn("fig-f1-screen", out)
        self.assertNotIn("<td>A</td>", out)  # su tabla de respaldo tampoco se muestra
        self.assertIn("Sensitive content omitted", out)

    def test_placeholder_no_expone_ids_reales(self):
        tabla = _tabla(table_id="tbl-secreta", rows=[("X", 1, 0.2)], sensitive=True)
        fig = _figura(figure_id="fig-secreta", table_id="tbl-secreta")
        rep = _reporte(chapters=(_cap(tables=(tabla,), figures=(fig,)),))
        out = _render(rep)
        self.assertNotIn("secreta", out)
        self.assertIn('id="fig-omitted-1"', out)

    def test_ficha_no_expone_sensitivity_completo_ni_ids(self):
        rep = _reporte()
        sens = {"contains_sensitive": True, "sensitive_artifacts": ["id-secreto-uno", "id-secreto-dos"],
                "otra_clave": "VALOR-RARO"}
        out = _render(rep, manifest=_manifest(rep, sensitivity=sens))
        for oculto in ("id-secreto-uno", "id-secreto-dos", "VALOR-RARO", "otra_clave", "sensitive_artifacts"):
            self.assertNotIn(oculto, out)
        self.assertIn("✓ (2)", out)  # booleano + cantidad
        sin = _render(rep, manifest=_manifest(rep, sensitivity={"contains_sensitive": False, "sensitive_artifacts": []}))
        self.assertIn("✗ (0)", sin)
        vacio = _render(rep, manifest=_manifest(rep, sensitivity={}))
        self.assertNotIn("✓", vacio.split("</summary>", 1)[1].split("</dl>", 1)[0])

    def test_glosario_excluye_figuras_respaldadas_por_tabla_sensible(self):
        tabla = _tabla(sensitive=True)
        fig = _figura(title="Ver termino-x aqui")
        rep = _reporte(chapters=(_cap(tables=(tabla,), figures=(fig,)),))
        st = _estilo({"explain_terms": True, "glossary": {"termino-x": "DEF-X"}})
        self.assertNotIn("DEF-X", _render(rep, style=st))
        self.assertIn("DEF-X", _render(rep, style=st, include_sensitive=True))

    def test_tabla_sensible_standalone_omitida(self):
        rep = _reporte(chapters=(_cap(tables=(_tabla(rows=[("SECRETO-9", 1, 0.1)], sensitive=True),),
                                      figures=()),))
        out = _render(rep)
        self.assertNotIn("SECRETO-9", out)
        self.assertIn("Sensitive content omitted", out)


# --- Insights, audiencia y recomendaciones ------------------------------------------------------


class TestInsights(unittest.TestCase):
    def _out(self, ins, editorial=None, **kw):
        rep = _reporte(chapters=(_cap(insights=(ins,)),))
        return _render(rep, style=_estilo(editorial), **kw)

    def test_recomendacion_evidence_only_sin_incertidumbre_se_suprime(self):
        out = self._out(_insight(claim_type="recommendation", uncertainty=""))
        self.assertIn("Recommendation withheld: insufficient evidence", out)
        self.assertNotIn("BIZ-CLAIM-XYZ", out)

    def test_recomendacion_con_refs_invalidas_se_suprime(self):
        out = self._out(_insight(claim_type="recommendation", refs=("no-existe",), uncertainty="incierto"))
        self.assertIn("Recommendation withheld", out)
        self.assertNotIn("BIZ-CLAIM-XYZ", out)
        sin_refs = self._out(_insight(claim_type="recommendation", refs=(), uncertainty="incierto"))
        self.assertIn("Recommendation withheld", sin_refs)

    def test_recomendacion_con_evidencia_e_incertidumbre_se_muestra_con_revision(self):
        out = self._out(_insight(claim_type="recommendation", uncertainty="UNC-XYZ"))
        self.assertIn("BIZ-CLAIM-XYZ", out)
        self.assertIn("requires review", out)
        self.assertNotIn("Recommendation withheld", out)

    def test_politicas_hide_y_show(self):
        ins = _insight(claim_type="recommendation", uncertainty="")
        oculto = self._out(ins, {"recommendations_policy": "hide"})
        self.assertNotIn("BIZ-CLAIM-XYZ", oculto)
        self.assertNotIn("Recommendation withheld", oculto)
        visible = self._out(ins, {"recommendations_policy": "show"})
        self.assertIn("BIZ-CLAIM-XYZ", visible)
        self.assertNotIn("Recommendation withheld", visible)

    def test_causal_lleva_etiqueta_de_revision_y_descriptivo_no(self):
        self.assertIn("requires review", self._out(_insight(claim_type="causal")))
        self.assertNotIn("requires review", self._out(_insight(claim_type="descriptive")))
        es = self._out(_insight(claim_type="causal"), {"locale": "es"})
        self.assertIn("requiere revisión", es)

    def test_audiencia_business_solo_muestra_business_claim(self):
        ins = _insight(claim_type="associative", uncertainty="UNC-XYZ")
        b = self._out(ins, {"audience": "business"})
        self.assertIn("BIZ-CLAIM-XYZ", b)
        for oculto in ("TECH-CLAIM-XYZ", "POP-XYZ", "TIME-XYZ", "UNC-XYZ"):
            self.assertNotIn(oculto, b)
        for aud in ("technical", "mixed"):
            t = self._out(ins, {"audience": aud})
            for visible in ("BIZ-CLAIM-XYZ", "TECH-CLAIM-XYZ", "POP-XYZ", "TIME-XYZ", "UNC-XYZ"):
                self.assertIn(visible, t)

    def test_uncertainty_display(self):
        desc = _insight(claim_type="descriptive", uncertainty="UNC-XYZ")
        asoc = _insight(claim_type="associative", uncertainty="UNC-XYZ")
        self.assertIn("UNC-XYZ", self._out(desc, {"uncertainty_display": "always"}))
        self.assertNotIn("UNC-XYZ", self._out(desc, {"uncertainty_display": "never"}))
        self.assertNotIn("UNC-XYZ", self._out(asoc, {"uncertainty_display": "never"}))
        self.assertNotIn("UNC-XYZ", self._out(desc, {"uncertainty_display": "non_descriptive"}))
        self.assertIn("UNC-XYZ", self._out(asoc, {"uncertainty_display": "non_descriptive"}))

    def test_insight_style_lista(self):
        lista = self._out(_insight(), {"insight_style": "list"})
        self.assertIn('<ul class="insight-list">', lista)
        self.assertIn("<li ", lista)
        self.assertNotIn("<aside", lista)
        self.assertIn("<aside", self._out(_insight(), {"insight_style": "callout"}))


# --- Bloques globales ------------------------------------------------------------------------------------


class TestBloques(unittest.TestCase):
    def test_banner_de_scope_exploratory(self):
        exp = _render(_reporte(scope="exploratory"))
        self.assertIn("Not an input for feature selection / not valid for model decisions", exp)
        rep = _reporte(scope="model_valid")
        self.assertNotIn("Not an input for feature selection", _render(rep))
        es = _render(_reporte(scope="exploratory"), style=_estilo({"locale": "es"}))
        self.assertIn("No es insumo de selección de features", es)

    def test_ficha_tecnica_footer_y_hash_corto(self):
        rep = _reporte()
        out = _render(rep)
        self.assertIn('<details class="tech-sheet">', out)
        for esperado in ("rep-prueba", "run-test-1", "0123456", "0.6.0-test", "2026-09-21T10:00:00Z",
                         "2024-12-31", "data/interim/ejemplo.csv", "abababababab", "Registros sin medida",
                         "none"):
            self.assertIn(esperado, out)
        self.assertNotIn("contains_sensitive", out)  # solo booleano + cantidad, no el dict
        self.assertNotIn("0123456789abcdef", out)  # commit corto
        self.assertNotIn("ab" * 32, out)            # hash de fuente corto
        pie = out[out.index('<footer class="report-footer">'):]
        self.assertIn("run-test-1", pie)
        self.assertIn(rep.content_sha256(), pie)

    def test_ficha_tecnica_marca_git_dirty(self):
        rep = _reporte()
        st = default_style()
        marca = f"0123456 ({st.editorial.label('dirty')})"  # texto de interfaz vía label, no literal
        self.assertIn(marca, _render(rep, style=st, manifest=_manifest(rep, git_dirty=True)))
        self.assertNotIn("0123456 (", _render(rep, style=st))

    def test_metodo_conclusion_e_intro(self):
        out = _render()
        self.assertIn('<details class="method">', out)
        self.assertIn("Nota de método", out)
        self.assertIn("Conclusion", out)
        self.assertIn("Conclusión del reporte", out)
        self.assertIn("Resumen del reporte", out)

    def test_glosario_solo_terminos_presentes_y_en_orden(self):
        glos = {"tasa": "DEF-TASA", "zeta": "DEF-ZETA", "Beta": "DEF-BETA"}
        rep = _reporte(summary="La tasa y la beta del grupo")
        out = _render(rep, style=_estilo({"explain_terms": True, "glossary": glos}))
        self.assertIn("DEF-TASA", out)
        self.assertIn("DEF-BETA", out)
        self.assertNotIn("DEF-ZETA", out)
        self.assertLess(out.index("DEF-BETA"), out.index("DEF-TASA"))
        apagado = _render(rep, style=_estilo({"explain_terms": False, "glossary": glos}))
        self.assertNotIn('class="glossary', apagado)
        self.assertNotIn("DEF-TASA", apagado)


if __name__ == "__main__":
    unittest.main()

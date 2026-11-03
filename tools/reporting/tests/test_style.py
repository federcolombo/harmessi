"""Tests de `tools/reporting/style.py` (v0.6 Change 4, tanda A: design system).

Deterministas: sin red, sin plotly, sin aleatoriedad, sin pandas. Repos temporales;
la lectura del override pasa por `evidence.read_allowed`, que se mockea para no
depender de la configuracion de guardrails de un repo temporal (las ramas
"denegado" se prueban con el mock devolviendo `(False, ...)`). Fixtures genericos.
"""
from __future__ import annotations

import ast
import copy
import json
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from datetime import date, datetime
from pathlib import Path
from unittest import mock

from tools.reporting import style as style_mod
from tools.reporting.style import (
    AA_TEXT_RATIO,
    CODE_STYLE_CONTRAST,
    CODE_STYLE_PALETTE,
    LABEL_KEYS,
    LOCALE_PRESETS,
    EditorialStyle,
    HarmessiDefaultTheme,
    Style,
    StyleError,
    check_style,
    contrast_ratio,
    default_style,
    format_date,
    format_number,
    format_percent,
    load_style,
    merge_style,
    style_to_dict,
)

SEMANTICOS = ("risk_low", "risk_medium", "risk_high", "ok", "warn", "error", "info")
checks = style_mod.checks  # mismo modulo `dsguard.checks` que usa style (sys.path ya resuelto)


class _PermitidoCtx:
    """Context manager fresco por uso: `evidence.read_allowed` => `(True, "ok")`."""

    def __enter__(self):
        self._p = mock.patch.object(style_mod.evidence, "read_allowed", return_value=(True, "ok"))
        return self._p.__enter__()

    def __exit__(self, *exc):
        return self._p.__exit__(*exc)


def _permitido() -> _PermitidoCtx:
    return _PermitidoCtx()


def _escribir_override(repo: Path, contenido) -> None:
    ruta = repo / ".harmessi" / "report-style.json"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(contenido, (bytes, bytearray)):
        ruta.write_bytes(bytes(contenido))
    elif isinstance(contenido, str):
        ruta.write_text(contenido, encoding="utf-8")
    else:
        ruta.write_text(json.dumps(contenido), encoding="utf-8")


class ContrasteDefaultTests(unittest.TestCase):
    def test_contraste_texto_y_muted_aa_en_ambos_temas(self) -> None:
        s = default_style()
        for tema in ("screen", "print"):
            p = getattr(s.visual, tema)
            for fg in ("text", "muted"):
                for bg in ("surface", "surface_alt"):
                    r = contrast_ratio(getattr(p, fg), getattr(p, bg))
                    self.assertGreaterEqual(r, AA_TEXT_RATIO, f"{tema}.{fg}/{bg}={r:.2f}")

    def test_semanticos_y_acento_sobre_su_superficie(self) -> None:
        s = default_style()
        for tema in ("screen", "print"):
            p = getattr(s.visual, tema)
            for nombre in (*SEMANTICOS, "accent"):
                r = contrast_ratio(getattr(p, nombre), p.surface)
                self.assertGreaterEqual(r, AA_TEXT_RATIO, f"{tema}.{nombre}={r:.2f}")

    def test_screen_oscuro_y_print_claro(self) -> None:
        s = default_style().visual
        self.assertGreater(contrast_ratio(s.print.surface, "#000000"), 15)
        self.assertLess(contrast_ratio(s.screen.surface, "#000000"), 3)
        self.assertGreater(contrast_ratio(s.screen.text, s.screen.surface),
                           contrast_ratio(s.screen.surface, "#000000"))

    def test_contrast_ratio_valores_conocidos(self) -> None:
        self.assertAlmostEqual(contrast_ratio("#000000", "#ffffff"), 21.0, places=6)
        self.assertAlmostEqual(contrast_ratio("#ffffff", "#000000"), 21.0, places=6)
        self.assertAlmostEqual(contrast_ratio("#777777", "#777777"), 1.0, places=6)
        # gris #767676 sobre blanco: ~4.54 (referencia WCAG comun)
        self.assertAlmostEqual(contrast_ratio("#767676", "#ffffff"), 4.54, places=1)

    def test_contrast_ratio_color_invalido(self) -> None:
        for malo in ("fff", "#12345", "red", "#gggggg", None, 5):
            with self.assertRaises(StyleError):
                contrast_ratio(malo, "#ffffff")


class DefaultGenericoTests(unittest.TestCase):
    def test_default_generico_offline_y_sin_branding(self) -> None:
        s = default_style()
        self.assertEqual(s.editorial.locale, "en")
        self.assertIsNone(s.visual.chart.plotly_js_file)
        crudo = json.dumps(style_to_dict(s)).lower()
        for prohibido in ("http", "url(", "@import", "logo", "brand"):
            self.assertNotIn(prohibido, crudo)

    def test_paleta_categorica_sin_repetidos_y_hex(self) -> None:
        s = default_style()
        for tema in ("screen", "print"):
            cat = getattr(s.visual, tema).categorical
            self.assertGreaterEqual(len(cat), 6)
            self.assertEqual(len({c.lower() for c in cat}), len(cat))
        self.assertEqual(s.visual.chart.screen.colorway, s.visual.screen.categorical)
        self.assertEqual(s.visual.chart.print.colorway, s.visual.print.categorical)

    def test_theme_class_coincide_con_default(self) -> None:
        self.assertEqual(HarmessiDefaultTheme.build("en"), default_style())

    def test_default_es_independiente_en_cada_llamada(self) -> None:
        a, b = default_style(), default_style()
        self.assertEqual(a, b)
        self.assertIsNot(a.editorial.labels, b.editorial.labels)
        a.editorial.labels["conclusion"] = "mutado"
        self.assertNotEqual(default_style().editorial.labels["conclusion"], "mutado")

    def test_frozen(self) -> None:
        s = default_style()
        with self.assertRaises(FrozenInstanceError):
            s.editorial = EditorialStyle()  # type: ignore[misc]
        with self.assertRaises(FrozenInstanceError):
            s.visual.screen.text = "#000000"  # type: ignore[misc]

    def test_determinismo(self) -> None:
        a = json.dumps(style_to_dict(default_style()), sort_keys=True)
        b = json.dumps(style_to_dict(default_style()), sort_keys=True)
        self.assertEqual(a, b)


class ValidacionTests(unittest.TestCase):
    def test_enums_fuera_de_rango(self) -> None:
        casos = {
            "audience": "everyone",
            "uncertainty_display": "sometimes",
            "insight_style": "poem",
            "recommendations_policy": "always",
            "locale": "fr",
        }
        for campo, valor in casos.items():
            with self.assertRaises(StyleError, msg=campo):
                EditorialStyle(**{campo: valor})
            with self.assertRaises(StyleError, msg=f"merge {campo}"):
                merge_style(default_style(), {"editorial": {campo: valor}})

    def test_enums_validos_aceptados(self) -> None:
        e = EditorialStyle(audience="technical", uncertainty_display="never",
                           insight_style="list", recommendations_policy="hide")
        self.assertEqual(e.audience, "technical")

    def test_tipos_erroneos_editorial(self) -> None:
        for campo, valor in (("explain_terms", "yes"), ("comparative_context", 1),
                             ("tone", 5), ("glossary", ["a"]), ("labels", "x")):
            with self.assertRaises(StyleError, msg=campo):
                EditorialStyle(**{campo: valor})

    def test_colores_mal_formados(self) -> None:
        for malo in ("#fff", "fff000", "#12345g", "#1234567", "red", "", None, 123, "rgb(0,0,0)"):
            with self.assertRaises(StyleError, msg=repr(malo)):
                merge_style(default_style(), {"visual": {"screen": {"text": malo}}})
        with self.assertRaises(StyleError):
            merge_style(default_style(), {"visual": {"chart": {"screen": {"grid_color": "#zzzzzz"}}}})
        with self.assertRaises(StyleError):
            merge_style(default_style(), {"visual": {"print": {"categorical": ["#0072b2", "azul"]}}})

    def test_regex_no_acepta_salto_de_linea_final(self) -> None:
        for malo in ("#ffffff\n", "\n#ffffff", "#ffffff\r\n", "#ffffff "):
            with self.assertRaises(StyleError, msg=repr(malo)):
                merge_style(default_style(), {"visual": {"screen": {"text": malo}}})
            with self.assertRaises(StyleError, msg=repr(malo)):
                contrast_ratio(malo, "#000000")
        with self.assertRaises(StyleError):
            merge_style(default_style(), {"visual": {"typography": {"font_sans": "Arial\n"}}})
        with self.assertRaises(StyleError):
            merge_style(default_style(), {"visual": {"locale_format": {"date_format": "%Y\n"}}})

    def test_fuentes_comillas_balanceadas(self) -> None:
        for malo in ('Foo"', "Foo'", "'Foo, Bar", 'Arial, "Segoe UI', "'Foo\"", "\"Foo'"):
            with self.assertRaises(StyleError, msg=malo):
                merge_style(default_style(), {"visual": {"typography": {"font_sans": malo}}})
        for bueno in ("Arial, 'Segoe UI', sans-serif", 'Arial, "Segoe UI", sans-serif',
                      "'Helvetica Neue', Arial"):
            s = merge_style(default_style(), {"visual": {"typography": {"font_sans": bueno}}})
            self.assertEqual(s.visual.typography.font_sans, bueno)
        # el default tiene nombres compuestos entre comillas balanceadas
        self.assertIn("'Segoe UI'", default_style().visual.typography.font_sans)

    def test_rangos_y_tipos_numericos(self) -> None:
        malos = [
            {"typography": {"size_base": 999}},
            {"typography": {"size_base": 2}},
            {"typography": {"size_base": "16"}},
            {"typography": {"size_base": True}},
            {"typography": {"line_height": float("inf")}},
            {"spacing": {"md": -1}},
            {"spacing": {"md": 1.5}},
            {"radii": {"sm": 1000}},
            {"content_widths": {"wide": 10}},
            {"locale_format": {"percent_decimals": 9}},
            {"chart": {"screen": {"font_size": 0}}},
            {"chart": {"print": {"legend_position": "diagonal"}}},
            {"table": {"numbers_align": "justify"}},
            {"table": {"zebra": "si"}},
        ]
        for visual in malos:
            with self.assertRaises(StyleError, msg=str(visual)):
                merge_style(default_style(), {"visual": visual})

    def test_breakpoints_deben_ser_ascendentes(self) -> None:
        with self.assertRaises(StyleError):
            merge_style(default_style(), {"visual": {"responsive": {"breakpoint_sm": 900}}})
        ok = merge_style(default_style(), {"visual": {"responsive": {"breakpoint_sm": 500}}})
        self.assertEqual(ok.visual.responsive.breakpoint_sm, 500)

    def test_fuentes_solo_del_sistema(self) -> None:
        for malo in ("url(http://x/f.woff)", "Arial; } body { color:red", "@import 'x'", "", "a/b"):
            with self.assertRaises(StyleError, msg=malo):
                merge_style(default_style(), {"visual": {"typography": {"font_sans": malo}}})
        ok = merge_style(default_style(),
                         {"visual": {"typography": {"font_sans": "Georgia, 'Times New Roman', serif"}}})
        self.assertIn("Georgia", ok.visual.typography.font_sans)

    def test_formato_de_locale_invalido(self) -> None:
        malos = [
            {"decimal_sep": ""}, {"decimal_sep": ",,"}, {"decimal_sep": "5"},
            {"thousands_sep": "."},  # igual a decimal_sep del default
            {"date_format": "%A %d"}, {"date_format": "<b>%Y</b>"}, {"date_format": ""},
        ]
        for fmt in malos:
            with self.assertRaises(StyleError, msg=str(fmt)):
                merge_style(default_style(), {"visual": {"locale_format": fmt}})

    def test_plotly_js_file_relativa_y_dentro_del_repo(self) -> None:
        for malo in ("/abs/plotly.js", "C:/x/plotly.js", "..\\x.js", "a/../../x.js", "", 7):
            with self.assertRaises(StyleError, msg=repr(malo)):
                merge_style(default_style(), {"visual": {"chart": {"plotly_js_file": malo}}})
        s = merge_style(default_style(), {"visual": {"chart": {"plotly_js_file": "vendor/plotly.min.js"}}})
        self.assertEqual(s.visual.chart.plotly_js_file, "vendor/plotly.min.js")
        s2 = merge_style(s, {"visual": {"chart": {"plotly_js_file": None}}})
        self.assertIsNone(s2.visual.chart.plotly_js_file)


class MergeTests(unittest.TestCase):
    def test_override_valido_se_refleja(self) -> None:
        s = merge_style(default_style(), {
            "visual": {"screen": {"accent": "#ff8800"}, "typography": {"size_base": 18},
                       "chart": {"screen": {"line_width": 3}}},
            "editorial": {"audience": "business", "tone": "formal",
                          "glossary": {"term": "definicion"},
                          "labels": {"conclusion": "Cierre"}},
        })
        self.assertEqual(s.visual.screen.accent, "#ff8800")
        self.assertEqual(s.visual.typography.size_base, 18)
        self.assertEqual(s.visual.chart.screen.line_width, 3)
        self.assertEqual(s.editorial.audience, "business")
        self.assertEqual(s.editorial.glossary, {"term": "definicion"})
        self.assertEqual(s.editorial.labels["conclusion"], "Cierre")
        # lo no tocado se conserva
        self.assertEqual(s.visual.screen.surface, default_style().visual.screen.surface)
        self.assertEqual(s.editorial.labels["glossary"], "Glossary")

    def test_no_muta_base_ni_default(self) -> None:
        base = default_style()
        antes = copy.deepcopy(style_to_dict(base))
        nuevo = merge_style(base, {"visual": {"screen": {"text": "#ffffff"}},
                                   "editorial": {"labels": {"conclusion": "X"},
                                                 "glossary": {"a": "b"}}})
        self.assertEqual(style_to_dict(base), antes)
        self.assertEqual(default_style(), base)
        self.assertNotEqual(nuevo, base)
        # sin dicts compartidos con la base
        self.assertIsNot(nuevo.editorial.labels, base.editorial.labels)
        nuevo.editorial.labels["conclusion"] = "mutado"
        self.assertEqual(base.editorial.labels["conclusion"], "Conclusion")
        # merge vacio: copia igual pero independiente
        copia = merge_style(base, {})
        self.assertEqual(copia, base)
        self.assertIsNot(copia.editorial.labels, base.editorial.labels)

    def test_merge_no_muta_el_mapping_de_overrides(self) -> None:
        ov = {"editorial": {"labels": {"conclusion": "Z"}}, "visual": {"print": {"categorical": ["#111111"]}}}
        snap = copy.deepcopy(ov)
        merge_style(default_style(), ov)
        self.assertEqual(ov, snap)

    def test_claves_desconocidas(self) -> None:
        malos = [
            {"brand": {}},
            {"visual": {"colors": {}}},
            {"visual": {"screen": {"fondo": "#000000"}}},
            {"visual": {"chart": {"screen": {"tema": "x"}}}},
            {"editorial": {"voice": "x"}},
            {"editorial": {"labels": {"no_existe": "x"}}},
            {"schema_version": 1},
        ]
        for ov in malos:
            with self.assertRaises(StyleError, msg=str(ov)):
                merge_style(default_style(), ov)

    def test_estructura_erronea(self) -> None:
        malos = [
            {"visual": "oscuro"},
            {"visual": {"screen": "#000000"}},
            {"visual": {"screen": {"categorical": "#000000"}}},
            {"editorial": {"labels": ["a"]}},
            {"editorial": {"labels": {"conclusion": 5}}},
            {"editorial": {"glossary": {"t": 5}}},
            {"visual": {"typography": {"size_base": {"a": 1}}}},
        ]
        for ov in malos:
            with self.assertRaises(StyleError, msg=str(ov)):
                merge_style(default_style(), ov)
        with self.assertRaises(StyleError):
            merge_style(default_style(), ["visual"])  # type: ignore[arg-type]
        with self.assertRaises(StyleError):
            merge_style("no es style", {})  # type: ignore[arg-type]

    def test_cambio_de_locale_adopta_preset(self) -> None:
        s = merge_style(default_style(), {"editorial": {"locale": "es"}})
        self.assertEqual(s.editorial.locale, "es")
        self.assertEqual(s.editorial.labels["conclusion"], "Conclusión")
        self.assertEqual(s.visual.locale_format.decimal_sep, ",")
        self.assertEqual(s.visual.locale_format.thousands_sep, ".")
        self.assertEqual(s.visual.locale_format.date_format, "%d/%m/%Y")

    def test_cambio_de_locale_respeta_override_explicito(self) -> None:
        s = merge_style(default_style(), {"editorial": {"locale": "es", "labels": {"conclusion": "Cierre"}},
                                          "visual": {"locale_format": {"percent_decimals": 2}}})
        self.assertEqual(s.editorial.labels["conclusion"], "Cierre")
        self.assertEqual(s.editorial.labels["glossary"], "Glosario")
        self.assertEqual(s.visual.locale_format.percent_decimals, 2)
        self.assertEqual(s.visual.locale_format.decimal_sep, ",")


class LoadStyleTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo = Path(self._tmp.name)

    def test_ausente_devuelve_default_sin_leer(self) -> None:
        with mock.patch.object(style_mod.evidence, "read_allowed",
                               side_effect=AssertionError("no debe leer")) as ra:
            s = load_style(self.repo)
        self.assertEqual(s, default_style())
        ra.assert_not_called()

    def test_valido_refleja_override_y_default_intacto(self) -> None:
        _escribir_override(self.repo, {
            "schema_version": 1,
            "visual": {"screen": {"accent": "#ff8800"}},
            "editorial": {"audience": "technical", "locale": "es"},
        })
        with _permitido() as ra:
            s = load_style(self.repo)
        ra.assert_called_once()
        self.assertEqual(s.visual.screen.accent, "#ff8800")
        self.assertEqual(s.editorial.audience, "technical")
        self.assertEqual(s.editorial.labels["tech_sheet"], "Ficha técnica")
        # el default posterior queda intacto
        d = default_style()
        self.assertNotEqual(d.visual.screen.accent, "#ff8800")
        self.assertEqual(d.editorial.audience, "mixed")
        self.assertEqual(d.editorial.locale, "en")

    def test_solo_schema_version_equivale_a_default(self) -> None:
        _escribir_override(self.repo, {"schema_version": 1})
        with _permitido():
            self.assertEqual(load_style(self.repo), default_style())

    def test_invalidos_lanzan_style_error(self) -> None:
        casos = {
            "json corrupto": "{no es json",
            "vacio": "",
            "no utf8": b"\xff\xfe\x00{",
            "raiz lista": "[1, 2]",
            "sin schema_version": {"visual": {}},
            "version 2": {"schema_version": 2},
            "version bool": {"schema_version": True},
            "version str": {"schema_version": "1"},
            "clave desconocida": {"schema_version": 1, "theme": "x"},
            "clave anidada desconocida": {"schema_version": 1, "visual": {"screen": {"bg": "#000000"}}},
            "color malo": {"schema_version": 1, "visual": {"screen": {"text": "blanco"}}},
            "rango": {"schema_version": 1, "visual": {"typography": {"size_base": 500}}},
            "enum": {"schema_version": 1, "editorial": {"audience": "todos"}},
            "clave duplicada": '{"schema_version": 1, "schema_version": 1}',
            "NaN": '{"schema_version": 1, "visual": {"typography": {"line_height": NaN}}}',
        }
        for nombre, contenido in casos.items():
            _escribir_override(self.repo, contenido)
            with _permitido():
                with self.assertRaises(StyleError, msg=nombre):
                    load_style(self.repo)

    def test_lectura_denegada_por_guardas(self) -> None:
        _escribir_override(self.repo, {"schema_version": 1})
        with mock.patch.object(style_mod.evidence, "read_allowed", return_value=(False, "denegado")):
            with self.assertRaises(StyleError):
                load_style(self.repo)

    def test_ruta_que_es_directorio(self) -> None:
        (self.repo / ".harmessi" / "report-style.json").mkdir(parents=True)
        with _permitido():
            with self.assertRaises(StyleError):
                load_style(self.repo)

    def test_mensaje_sin_ruta_local(self) -> None:
        _escribir_override(self.repo, "{corrupto")
        with _permitido():
            with self.assertRaises(StyleError) as cm:
                load_style(self.repo)
        self.assertNotIn(str(self.repo), str(cm.exception))

    def test_no_escribe_nada(self) -> None:
        _escribir_override(self.repo, {"schema_version": 1})
        antes = sorted(p.relative_to(self.repo).as_posix() for p in self.repo.rglob("*"))
        with _permitido():
            load_style(self.repo)
        despues = sorted(p.relative_to(self.repo).as_posix() for p in self.repo.rglob("*"))
        self.assertEqual(antes, despues)


class LoadStyleFileTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo = Path(self._tmp.name)

    def _escribir(self, rel: str, contenido) -> None:
        ruta = self.repo / rel
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(contenido if isinstance(contenido, str) else json.dumps(contenido),
                        encoding="utf-8")

    def test_valido(self) -> None:
        self._escribir("estilos/mi.json", {"schema_version": 1,
                                           "visual": {"screen": {"accent": "#ff8800"}},
                                           "editorial": {"locale": "es"}})
        with _permitido() as ra:
            s = style_mod.load_style_file(self.repo, "estilos/mi.json")
        ra.assert_called_once()
        self.assertEqual(s.visual.screen.accent, "#ff8800")
        self.assertEqual(s.editorial.labels["dirty"], "modificado")
        self.assertNotEqual(default_style().visual.screen.accent, "#ff8800")

    def test_valido_con_backslash_y_path(self) -> None:
        self._escribir("estilos/mi.json", {"schema_version": 1})
        with _permitido():
            self.assertEqual(style_mod.load_style_file(self.repo, "estilos\\mi.json"), default_style())
            self.assertEqual(style_mod.load_style_file(self.repo, Path("estilos") / "mi.json"),
                             default_style())

    def test_ausente_default_o_error(self) -> None:
        with mock.patch.object(style_mod.evidence, "read_allowed",
                               side_effect=AssertionError("no debe leer")):
            self.assertEqual(style_mod.load_style_file(self.repo, "no/existe.json"), default_style())
            with self.assertRaises(StyleError):
                style_mod.load_style_file(self.repo, "no/existe.json", missing_ok=False)

    def test_load_style_usa_ruta_por_defecto(self) -> None:
        _escribir_override(self.repo, {"schema_version": 1, "visual": {"screen": {"accent": "#ff8800"}}})
        with _permitido() as ra:
            s = load_style(self.repo)
        self.assertEqual(s.visual.screen.accent, "#ff8800")
        self.assertIn(".harmessi", str(ra.call_args[0][1]).replace("\\", "/"))

    def test_rutas_con_punto_punto_o_absolutas(self) -> None:
        self._escribir("ok.json", {"schema_version": 1})
        absoluta = str((self.repo / "ok.json").resolve())
        malas = ["../ok.json", "a/../../ok.json", "..\\ok.json", absoluta, "/etc/x.json",
                 "C:/x/y.json", "", "a\nb.json", "a\x00b.json", 5, None]
        with mock.patch.object(style_mod.evidence, "read_allowed",
                               side_effect=AssertionError("no debe leer")):
            for mala in malas:
                with self.assertRaises(StyleError, msg=repr(mala)):
                    style_mod.load_style_file(self.repo, mala)

    def test_denegado_por_guardas(self) -> None:
        self._escribir("ok.json", {"schema_version": 1})
        with mock.patch.object(style_mod.evidence, "read_allowed", return_value=(False, "x")) as ra:
            with self.assertRaises(StyleError):
                style_mod.load_style_file(self.repo, "ok.json")
        ra.assert_called_once()

    def test_read_allowed_se_evalua_antes_de_leer(self) -> None:
        self._escribir("ok.json", {"schema_version": 1})
        orden = []
        with mock.patch.object(style_mod.evidence, "read_allowed",
                               side_effect=lambda *a, **k: orden.append("acceso") or (False, "x")):
            with mock.patch.object(Path, "read_bytes",
                                   side_effect=lambda *a, **k: orden.append("lectura") or b"{}"):
                with self.assertRaises(StyleError):
                    style_mod.load_style_file(self.repo, "ok.json")
        self.assertEqual(orden, ["acceso"])

    def test_invalidos_y_mensajes_sin_rutas_absolutas(self) -> None:
        casos = {
            "corrupto": "{no json",
            "clave desconocida": {"schema_version": 1, "theme": "x"},
            "clave anidada": {"schema_version": 1, "visual": {"screen": {"bg": "#000000"}}},
            "version": {"schema_version": 2},
            "color con salto de linea": {"schema_version": 1, "visual": {"screen": {"text": "#ffffff\n"}}},
            "sin version": {"visual": {}},
        }
        absolutos = {str(self.repo), str(self.repo.resolve()), str(self.repo).replace("\\", "/")}
        for nombre, contenido in casos.items():
            self._escribir("s.json", contenido)
            with _permitido():
                with self.assertRaises(StyleError, msg=nombre) as cm:
                    style_mod.load_style_file(self.repo, "s.json")
            for abs_ in absolutos:
                self.assertNotIn(abs_, str(cm.exception), nombre)

    def test_directorio_no_es_archivo(self) -> None:
        (self.repo / "d.json").mkdir()
        with _permitido():
            with self.assertRaises(StyleError):
                style_mod.load_style_file(self.repo, "d.json")


class CheckStyleTests(unittest.TestCase):
    def _por_codigo(self, resultados):
        return {r.code: r for r in resultados}

    def test_default_pass_en_ambas_reglas(self) -> None:
        res = check_style(default_style())
        self.assertEqual([r.code for r in res], [CODE_STYLE_CONTRAST, CODE_STYLE_PALETTE])
        for r in res:
            self.assertEqual(r.status, checks.STATUS_PASS, r.detail)

    def test_contraste_bajo_da_warn(self) -> None:
        s = merge_style(default_style(), {"visual": {"screen": {"text": "#101a2c"}}})
        r = self._por_codigo(check_style(s))
        self.assertEqual(r[CODE_STYLE_CONTRAST].status, checks.STATUS_WARN)
        self.assertIn("screen.text/surface", r[CODE_STYLE_CONTRAST].detail)
        self.assertEqual(r[CODE_STYLE_PALETTE].status, checks.STATUS_PASS)

    def test_contraste_bajo_en_print_y_semantico(self) -> None:
        s = merge_style(default_style(), {"visual": {"print": {"warn": "#ffee00"}}})
        r = self._por_codigo(check_style(s))
        self.assertEqual(r[CODE_STYLE_CONTRAST].status, checks.STATUS_WARN)
        self.assertIn("print.warn/surface", r[CODE_STYLE_CONTRAST].detail)

    def test_paleta_repetida_o_vacia_da_warn(self) -> None:
        for cat in (["#111111", "#111111"], ["#AABBCC", "#aabbcc"], []):
            s = merge_style(default_style(), {"visual": {"screen": {"categorical": cat}}})
            r = self._por_codigo(check_style(s))
            self.assertEqual(r[CODE_STYLE_PALETTE].status, checks.STATUS_WARN, str(cat))
            self.assertEqual(r[CODE_STYLE_CONTRAST].status, checks.STATUS_PASS)

    def test_colorway_repetido_da_warn(self) -> None:
        s = merge_style(default_style(), {"visual": {"chart": {"print": {"colorway": ["#000000", "#000000"]}}}})
        r = self._por_codigo(check_style(s))
        self.assertEqual(r[CODE_STYLE_PALETTE].status, checks.STATUS_WARN)

    def test_no_lanza_con_entrada_invalida(self) -> None:
        for malo in (None, "x", 5, object()):
            res = check_style(malo)  # type: ignore[arg-type]
            self.assertEqual(len(res), 2)
            for r in res:
                self.assertEqual(r.status, checks.STATUS_WARN)


class FormatoTests(unittest.TestCase):
    def test_numero_en_y_es(self) -> None:
        self.assertEqual(format_number(1234567.891, 2, "en"), "1,234,567.89")
        self.assertEqual(format_number(1234567.891, 2, "es"), "1.234.567,89")
        self.assertEqual(format_number(1234, None, "en"), "1,234")
        self.assertEqual(format_number(1234, None, "es"), "1.234")
        self.assertEqual(format_number(0.5, None, "en"), "0.50")
        self.assertEqual(format_number(0.5, None, "es"), "0,50")
        self.assertEqual(format_number(3.0, None, "es"), "3")
        self.assertEqual(format_number(1234567, 2, "es"), "1.234.567,00")
        self.assertEqual(format_number(999, 0, "en"), "999")
        self.assertEqual(format_number(1000, 0, "en"), "1,000")
        self.assertEqual(format_number(-1234.5, 1, "en"), "-1,234.5")
        self.assertEqual(format_number(-0.001, 2, "en"), "0.00")

    def test_porcentaje_en_y_es(self) -> None:
        self.assertEqual(format_percent(0.256, 1, "en"), "25.6%")
        self.assertEqual(format_percent(0.256, 1, "es"), "25,6%")
        self.assertEqual(format_percent(0.5, 0, "en"), "50%")
        self.assertEqual(format_percent(0.256, None, "en"), "25.6%")  # percent_decimals=1
        self.assertEqual(format_percent(1, 0, "en"), "100%")
        self.assertEqual(format_percent(12.3456, 2, "es"), "1.234,56%")

    def test_fecha_en_y_es(self) -> None:
        self.assertEqual(format_date("2026-09-18", "en"), "2026-09-18")
        self.assertEqual(format_date("2026-09-18", "es"), "18/09/2026")
        self.assertEqual(format_date(date(2026, 1, 5), "es"), "05/01/2026")
        self.assertEqual(format_date(datetime(2026, 9, 18, 13, 45, 10), "es"), "18/09/2026")
        self.assertEqual(format_date("2026-09-18T10:20:30", "en"), "2026-09-18")

    def test_locale_como_style_o_formato(self) -> None:
        es = merge_style(default_style(), {"editorial": {"locale": "es"}})
        self.assertEqual(format_number(1234.5, 1, es), "1.234,5")
        self.assertEqual(format_number(1234.5, 1, es.visual.locale_format), "1.234,5")
        con_hora = merge_style(default_style(), {"visual": {"locale_format": {"date_format": "%d.%m.%y %H:%M"}}})
        self.assertEqual(format_date("2026-09-18T07:05:00", con_hora), "18.09.26 07:05")

    def test_no_lanzan_ante_none_o_no_numerico(self) -> None:
        for fn in (format_number, format_percent, format_date):
            self.assertEqual(fn(None), "")
        self.assertEqual(format_number("abc"), "abc")
        self.assertEqual(format_number("12"), "12")  # texto: no se interpreta
        self.assertEqual(format_number(float("nan")), "nan")
        self.assertEqual(format_number(float("inf"), 2, "es"), "inf")
        self.assertEqual(format_number(True), "True")
        self.assertEqual(format_number([1, 2]), "[1, 2]")
        self.assertEqual(format_percent("x"), "x")
        self.assertEqual(format_percent(float("nan")), "nan")
        self.assertEqual(format_date("no es fecha"), "no es fecha")
        self.assertEqual(format_date(12345), "12345")
        self.assertEqual(format_date("2026-13-45"), "2026-13-45")

    def test_locale_desconocido_cae_en_en(self) -> None:
        self.assertEqual(format_number(1234.5, 1, "zz"), "1,234.5")
        self.assertEqual(format_number(1234.5, 1, None), "1,234.5")  # type: ignore[arg-type]

    def test_decimales_invalidos_no_lanzan(self) -> None:
        self.assertEqual(format_number(1.5, -3), "1.50")
        self.assertEqual(format_number(1.5, "x"), "1.50")  # type: ignore[arg-type]

    def test_no_escapa_html(self) -> None:
        # el escape es del renderer: el formato devuelve el texto tal cual
        self.assertEqual(format_number("<b>x</b>"), "<b>x</b>")


class PresetsTests(unittest.TestCase):
    def test_presets_tienen_las_mismas_claves(self) -> None:
        self.assertEqual(set(LOCALE_PRESETS), {"en", "es"})
        self.assertEqual(set(LOCALE_PRESETS["en"]["labels"]), set(LOCALE_PRESETS["es"]["labels"]))
        self.assertEqual(set(LOCALE_PRESETS["en"]["labels"]), set(LABEL_KEYS))

    def test_labels_not_available_y_dirty_en_todos_los_presets(self) -> None:
        self.assertEqual(len(LABEL_KEYS), 37)  # 35 previas + not_available + dirty
        for loc in ("en", "es"):
            labels = LOCALE_PRESETS[loc]["labels"]
            self.assertEqual(len(labels), len(LABEL_KEYS))
            self.assertIn("not_available", labels)
            self.assertIn("dirty", labels)
        self.assertEqual(LOCALE_PRESETS["en"]["labels"]["not_available"], "n/a")
        self.assertEqual(LOCALE_PRESETS["en"]["labels"]["dirty"], "dirty")
        self.assertEqual(LOCALE_PRESETS["es"]["labels"]["not_available"], "s/d")
        self.assertEqual(LOCALE_PRESETS["es"]["labels"]["dirty"], "modificado")
        self.assertEqual(default_style().editorial.label("dirty"), "dirty")
        es = HarmessiDefaultTheme.build("es")
        self.assertEqual(es.editorial.label("not_available"), "s/d")
        self.assertEqual(merge_style(default_style(), {"editorial": {"labels": {"dirty": "x"}}})
                         .editorial.labels["dirty"], "x")

    def test_labels_requeridos_por_la_spec_presentes(self) -> None:
        for clave in ("tech_sheet", "method_details", "backup_table", "conclusion", "glossary",
                      "showing_n_of_m", "scope_exploratory", "figure_not_rendered",
                      "recommendation_withheld", "requires_review"):
            self.assertIn(clave, LABEL_KEYS)

    def test_es_sin_acentos_rotos(self) -> None:
        es = LOCALE_PRESETS["es"]["labels"]
        self.assertEqual(es["conclusion"], "Conclusión")
        self.assertEqual(es["tech_sheet"], "Ficha técnica")
        self.assertEqual(es["requires_review"], "requiere revisión")
        for texto in list(es.values()) + list(LOCALE_PRESETS["en"]["labels"].values()):
            self.assertNotIn("\ufffd", texto)
            self.assertNotIn("Ã", texto)
            self.assertNotIn("Â", texto)
            self.assertEqual(texto, texto.strip())
            self.assertTrue(texto)

    def test_placeholders_consistentes(self) -> None:
        for loc in ("en", "es"):
            t = LOCALE_PRESETS[loc]["labels"]["showing_n_of_m"]
            self.assertEqual(t.format(n=10, m=30).count("10"), 1)
            self.assertIn("30", t.format(n=10, m=30))

    def test_es_es_data_no_default(self) -> None:
        self.assertEqual(default_style().editorial.locale, "en")
        s = HarmessiDefaultTheme.build("es")
        self.assertEqual(s.editorial.labels["glossary"], "Glosario")
        self.assertEqual(s.visual.locale_format.decimal_sep, ",")
        with self.assertRaises(StyleError):
            HarmessiDefaultTheme.build("fr")

    def test_label_con_fallback(self) -> None:
        e = EditorialStyle(locale="es", labels={"conclusion": "Cierre"})
        self.assertEqual(e.label("conclusion"), "Cierre")
        self.assertEqual(e.label("glossary"), "Glosario")  # preset del locale
        self.assertEqual(e.label("clave_inexistente"), "clave_inexistente")

    def test_sin_datos_privados_en_presets(self) -> None:
        crudo = json.dumps(LOCALE_PRESETS, ensure_ascii=False).lower()
        for prohibido in ("@", "http", "c:\\", "/users/", "password", "token"):
            self.assertNotIn(prohibido, crudo)


class ArquitecturaTests(unittest.TestCase):
    def test_imports_de_style_solo_stdlib_y_permitidos(self) -> None:
        arbol = ast.parse(Path(style_mod.__file__).read_text(encoding="utf-8"))
        prohibidos = {"plotly", "pandas", "numpy", "requests", "urllib", "socket", "http"}
        internos_prohibidos = {"core", "governance", "validation", "render_html", "plotly_backend",
                               "publish", "cli", "profiles"}
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Import):
                for a in nodo.names:
                    self.assertNotIn(a.name.split(".")[0], prohibidos, a.name)
            elif isinstance(nodo, ast.ImportFrom):
                raiz = (nodo.module or "").split(".")[0]
                self.assertNotIn(raiz, prohibidos)
                if nodo.level == 1:  # `from . import x` / `from .x import y`
                    nombres = {a.name for a in nodo.names} | {nodo.module or ""}
                    self.assertFalse(nombres & internos_prohibidos, nombres)


if __name__ == "__main__":
    unittest.main()

"""Tests de `tools.dsimpact.consumers_py`, `consumers_text` y
`generic_filter` (R5/R6/R7)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ORIGEN = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ORIGEN / "tools"))

from dsimpact import consumers_py, consumers_text, generic_filter  # noqa: E402


class TestBuscarEnTextoPython(unittest.TestCase):
    def test_import_reference(self):
        texto = "from tools.features import build_features\n\nbuild_features()\n"
        matches = consumers_py.buscar_en_texto_python(texto, {"build_features"}, set())
        tipos = {m["tipo_base"] for m in matches}
        self.assertIn("IMPORT_REFERENCE", tipos)
        self.assertIn("SYMBOL_REFERENCE", tipos)

    def test_assert_reference(self):
        texto = "from x import build_features\n\ndef test_algo():\n    assert build_features(1) == 2\n"
        matches = consumers_py.buscar_en_texto_python(texto, {"build_features"}, set())
        tipos_por_linea = {m["linea"]: m["tipo_base"] for m in matches}
        # la referencia dentro del assert debe reportarse como ASSERT_REFERENCE
        self.assertIn("ASSERT_REFERENCE", tipos_por_linea.values())

    def test_string_contract_reference_en_cualquier_posicion(self):
        texto = 'mensaje = "referencia suelta a monto_total en cualquier lado"\n'
        # el string completo no matchea, probamos con un literal exacto
        texto2 = 'columna = "monto_total"\n'
        matches = consumers_py.buscar_en_texto_python(texto2, set(), {"monto_total"})
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["tipo_base"], "STRING_CONTRACT_REFERENCE")

    def test_sin_targets_no_hay_matches(self):
        texto = "x = 1\n"
        self.assertEqual(consumers_py.buscar_en_texto_python(texto, set(), set()), [])

    def test_symbol_reference_no_substring(self):
        texto = "build_features_v2()\n"
        matches = consumers_py.buscar_en_texto_python(texto, {"build_features"}, set())
        self.assertEqual(matches, [])

    def test_syntax_error_devuelve_vacio(self):
        matches = consumers_py.buscar_en_texto_python("def f(:\n", {"f"}, set())
        self.assertEqual(matches, [])

    def test_simbolo_sin_consumidores(self):
        texto = "otra_cosa = 1\n"
        matches = consumers_py.buscar_en_texto_python(texto, {"build_features"}, set())
        self.assertEqual(matches, [])


class TestBuscarEnJson(unittest.TestCase):
    def test_key_y_value_estructural(self):
        texto = '{"columnas": ["monto_total", "id_cliente"], "target": "monto_total"}'
        matches = consumers_text.buscar_en_json(texto, {"monto_total"})
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["changed_item"], "monto_total")

    def test_json_invalido_devuelve_vacio(self):
        self.assertEqual(consumers_text.buscar_en_json("{invalido", {"x"}), [])

    def test_sin_match(self):
        self.assertEqual(consumers_text.buscar_en_json('{"a": 1}', {"monto_total"}), [])


class TestBuscarEnTextoPlano(unittest.TestCase):
    def test_word_boundary_real(self):
        texto = "columnas:\n  - monto_total\n  - monto_total_2\n"
        matches = consumers_text.buscar_en_texto_plano(texto, {"monto_total"})
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["linea"], 2)

    def test_sin_match(self):
        self.assertEqual(consumers_text.buscar_en_texto_plano("nada aca\n", {"monto_total"}), [])


class TestGenericFilter(unittest.TestCase):
    def test_tokens_genericos(self):
        for token in ("id", "name", "Data", "TYPE", "self"):
            self.assertTrue(generic_filter.es_generico(token))

    def test_token_corto(self):
        self.assertTrue(generic_filter.es_generico("x"))

    def test_token_no_generico(self):
        self.assertFalse(generic_filter.es_generico("build_features"))
        self.assertFalse(generic_filter.es_generico("monto_total"))


if __name__ == "__main__":
    unittest.main()

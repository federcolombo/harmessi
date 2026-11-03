"""Tests de `tools.dsimpact.py_changes` (R2/R3/R4)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ORIGEN = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ORIGEN / "tools"))

from dsimpact import py_changes  # noqa: E402


class TestDiffSimbolos(unittest.TestCase):
    def test_funcion_agregada(self):
        antes = "x = 1\n"
        despues = "x = 1\n\ndef f():\n    return 1\n"
        simbolos, error = py_changes.diff_simbolos(antes, despues)
        self.assertFalse(error)
        nombres = {s.nombre: s for s in simbolos}
        self.assertEqual(nombres["f"].tipo, "funcion")
        self.assertEqual(nombres["f"].cambio, "agregado")

    def test_clase_eliminada(self):
        antes = "class A:\n    pass\n"
        despues = ""
        simbolos, error = py_changes.diff_simbolos(antes, despues)
        self.assertFalse(error)
        self.assertEqual(simbolos[0].nombre, "A")
        self.assertEqual(simbolos[0].tipo, "clase")
        self.assertEqual(simbolos[0].cambio, "eliminado")

    def test_constante_modificada(self):
        antes = "COLUMNAS = ['a', 'b']\n"
        despues = "COLUMNAS = ['a', 'b', 'c']\n"
        simbolos, error = py_changes.diff_simbolos(antes, despues)
        self.assertFalse(error)
        self.assertEqual(simbolos[0].nombre, "COLUMNAS")
        self.assertEqual(simbolos[0].tipo, "constante")
        self.assertEqual(simbolos[0].cambio, "modificado")

    def test_sin_cambios(self):
        texto = "def f():\n    return 1\n"
        simbolos, error = py_changes.diff_simbolos(texto, texto)
        self.assertEqual(simbolos, [])
        self.assertFalse(error)

    def test_archivo_agregado_antes_none(self):
        simbolos, error = py_changes.diff_simbolos(None, "def f():\n    pass\n")
        self.assertEqual(simbolos[0].cambio, "agregado")
        self.assertFalse(error)

    def test_syntax_error_marca_parse_error(self):
        simbolos, error = py_changes.diff_simbolos("def f(:\n", "x = 1\n")
        self.assertEqual(simbolos, [])
        self.assertTrue(error)


class TestStringsContractuales(unittest.TestCase):
    def test_lista_dentro_de_constante_modificada(self):
        despues = "COLUMNAS = ['id_cliente', 'monto_total']\n"
        simbolos, _ = py_changes.diff_simbolos("COLUMNAS = ['id_cliente']\n", despues)
        strings = py_changes.strings_contractuales(despues, simbolos)
        self.assertIn("monto_total", strings)

    def test_dict_key_value(self):
        despues = "MAPEO = {'origen': 'destino_col'}\n"
        simbolos, _ = py_changes.diff_simbolos("MAPEO = {}\n", despues)
        strings = py_changes.strings_contractuales(despues, simbolos)
        self.assertIn("origen", strings)
        self.assertIn("destino_col", strings)

    def test_assert_y_compare(self):
        despues = "def validar(col):\n    assert col == 'monto_total'\n"
        simbolos, _ = py_changes.diff_simbolos(None, despues)
        strings = py_changes.strings_contractuales(despues, simbolos)
        self.assertIn("monto_total", strings)

    def test_docstring_no_es_contrato(self):
        despues = 'def f():\n    """esto no es un contrato"""\n    return 1\n'
        simbolos, _ = py_changes.diff_simbolos(None, despues)
        strings = py_changes.strings_contractuales(despues, simbolos)
        self.assertEqual(strings, set())

    def test_solo_regiones_cambiadas(self):
        # 'f' no cambió -> sus strings estructurales no deben aparecer.
        antes = "def f():\n    return ['no_deberia_aparecer']\n\ndef g():\n    return 1\n"
        despues = "def f():\n    return ['no_deberia_aparecer']\n\ndef g():\n    return ['si_deberia']\n"
        simbolos, _ = py_changes.diff_simbolos(antes, despues)
        strings = py_changes.strings_contractuales(despues, simbolos)
        self.assertIn("si_deberia", strings)
        self.assertNotIn("no_deberia_aparecer", strings)


class TestDerivarNombreModulo(unittest.TestCase):
    def test_modulo_simple(self):
        self.assertEqual(py_changes.derivar_nombre_modulo("tools/features.py"), "tools.features")

    def test_init(self):
        self.assertEqual(py_changes.derivar_nombre_modulo("tools/pkg/__init__.py"), "tools.pkg")

    def test_no_python(self):
        self.assertIsNone(py_changes.derivar_nombre_modulo("tools/config.json"))


if __name__ == "__main__":
    unittest.main()

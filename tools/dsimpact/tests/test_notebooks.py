"""Tests de `tools.dsimpact.notebooks_source` (R8)."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ORIGEN = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ORIGEN / "tools"))

from dsimpact import notebooks_source  # noqa: E402


def _notebook(celdas: list) -> str:
    return json.dumps({
        "cells": celdas,
        "metadata": {},
        "nbformat": 4,
        "nbformat_minor": 5,
    })


class TestCeldasCodigo(unittest.TestCase):
    def test_extrae_solo_celdas_de_codigo(self):
        nb = _notebook([
            {"cell_type": "markdown", "source": ["# titulo\n"]},
            {"cell_type": "code", "source": ["x = 1\n"], "outputs": [], "execution_count": 1},
        ])
        celdas, error = notebooks_source.celdas_codigo(nb, "nb.ipynb")
        self.assertFalse(error)
        self.assertEqual(len(celdas), 1)
        self.assertEqual(celdas[0], (1, "x = 1\n"))

    def test_source_como_lista_se_une(self):
        nb = _notebook([
            {"cell_type": "code", "source": ["x = 1\n", "y = 2\n"], "outputs": []},
        ])
        celdas, error = notebooks_source.celdas_codigo(nb, "nb.ipynb")
        self.assertEqual(celdas[0][1], "x = 1\ny = 2\n")

    def test_outputs_ignorados(self):
        nb = _notebook([
            {"cell_type": "code", "source": ["x = 1\n"], "outputs": [{"data": {"text/plain": ["1"]}}], "execution_count": 5},
        ])
        celdas, error = notebooks_source.celdas_codigo(nb, "nb.ipynb")
        self.assertFalse(error)
        self.assertEqual(celdas[0][1], "x = 1\n")

    def test_json_invalido(self):
        celdas, error = notebooks_source.celdas_codigo("{esto no es json", "nb.ipynb")
        self.assertTrue(error)
        self.assertEqual(celdas, [])

    def test_indice_correcto_con_celdas_intercaladas(self):
        nb = _notebook([
            {"cell_type": "markdown", "source": ["# a\n"]},
            {"cell_type": "code", "source": ["a = 1\n"], "outputs": []},
            {"cell_type": "markdown", "source": ["# b\n"]},
            {"cell_type": "code", "source": ["b = 2\n"], "outputs": []},
        ])
        celdas, error = notebooks_source.celdas_codigo(nb, "nb.ipynb")
        self.assertEqual([i for i, _ in celdas], [1, 3])


if __name__ == "__main__":
    unittest.main()

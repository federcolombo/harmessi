"""Tests de `tools.ds_profile.quality_flags`. Trabaja sobre un
`columnas_detalle` construido a mano -- pura agregación, no recalcula nada
de `column_stats.py`."""
from __future__ import annotations

import unittest

from tools.ds_profile.quality_flags import calcular_calidad


def _detalle(nulls_pct=0.0, flags=None):
    return {
        "dtype": "texto",
        "nulls": {"count": 0, "pct": nulls_pct, "exactitud": "exacta"},
        "unique": {"count": 1, "exactitud": "exacta"},
        "top_valores": [],
        "exactitud_estadisticos": "exacta",
        "flags": flags or [],
    }


class TestCalcularCalidad(unittest.TestCase):
    def test_columnas_totalmente_nulas(self):
        columnas = {
            "a": _detalle(nulls_pct=100.0),
            "b": _detalle(nulls_pct=50.0),
            "c": _detalle(nulls_pct=0.0),
        }
        calidad = calcular_calidad(columnas, duplicados_valor=0, exactitud_duplicados="exacta")
        self.assertEqual(calidad["columnas_totalmente_nulas"], ["a"])

    def test_columnas_constantes(self):
        columnas = {
            "a": _detalle(flags=["constante"]),
            "b": _detalle(flags=[]),
        }
        calidad = calcular_calidad(columnas, duplicados_valor=0, exactitud_duplicados="exacta")
        self.assertEqual(calidad["columnas_constantes"], ["a"])

    def test_columnas_alta_cardinalidad(self):
        columnas = {
            "a": _detalle(flags=["alta_cardinalidad", "posible_id"]),
            "b": _detalle(flags=[]),
        }
        calidad = calcular_calidad(columnas, duplicados_valor=0, exactitud_duplicados="exacta")
        self.assertEqual(calidad["columnas_alta_cardinalidad"], ["a"])

    def test_columnas_posible_problema_tipo(self):
        columnas = {
            "a": _detalle(flags=["posible_problema_tipo"]),
            "b": _detalle(flags=[]),
        }
        calidad = calcular_calidad(columnas, duplicados_valor=0, exactitud_duplicados="exacta")
        self.assertEqual(calidad["columnas_posible_problema_tipo"], ["a"])

    def test_duplicados_fila_pasa_directo(self):
        calidad = calcular_calidad({}, duplicados_valor=7, exactitud_duplicados="muestreada")
        self.assertEqual(calidad["duplicados_fila"], {"valor": 7, "exactitud": "muestreada"})

    def test_sin_columnas_devuelve_listas_vacias(self):
        calidad = calcular_calidad({}, duplicados_valor=0, exactitud_duplicados="exacta")
        self.assertEqual(calidad["columnas_totalmente_nulas"], [])
        self.assertEqual(calidad["columnas_constantes"], [])
        self.assertEqual(calidad["columnas_alta_cardinalidad"], [])
        self.assertEqual(calidad["columnas_posible_problema_tipo"], [])


if __name__ == "__main__":
    unittest.main()

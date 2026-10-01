"""Paridad del literal `SOURCE_ID_PATTERN` entre `tools/datasources/core.py` y
`tools/autonomy/core.py` (v0.8 Change 1, `spec.md` R4/R39). Ambos paquetes
declaran el mismo patrón de forma independiente y DUPLICADA a propósito (ver
`design.md` D2): este test afirma que la duplicación sigue siendo exacta, para
que no diverjan en silencio.

Mismos 5 ejemplos ya usados por los tests de `datasources`/`autonomy` (no se
inventan ejemplos nuevos): 4 rechazados
(`tools/datasources/tests/test_core.py:_SOURCE_ID_RECHAZADOS`) + `customers`
aceptado (`tools/autonomy/tests/test_core.py:TestSourceId.test_validos`).
"""
from __future__ import annotations

import re
import unittest

from tools.autonomy import core as autonomy_core
from tools.datasources import core as datasources_core

_SOURCE_ID_RECHAZADOS = (
    "dbo.Clientes.Productores",
    "project.dataset.customers",
    "/v2/customers",
    "data/raw/customers.parquet",
)

_SOURCE_ID_ACEPTADO = "customers"


class TestParidadDeLiteral(unittest.TestCase):
    def test_source_id_pattern_identico_entre_paquetes(self):
        self.assertEqual(datasources_core.SOURCE_ID_PATTERN, autonomy_core.SOURCE_ID_PATTERN)


class TestParidadDeComportamiento(unittest.TestCase):
    def _fullmatch_datasources(self, valor: str) -> bool:
        return re.compile(datasources_core.SOURCE_ID_PATTERN).fullmatch(valor) is not None

    def test_ambos_rechazan_los_mismos_ejemplos(self):
        for valor in _SOURCE_ID_RECHAZADOS:
            with self.subTest(valor=valor):
                self.assertFalse(self._fullmatch_datasources(valor), valor)
                self.assertFalse(autonomy_core.is_valid_source_id(valor), valor)

    def test_ambos_aceptan_el_mismo_ejemplo(self):
        self.assertTrue(self._fullmatch_datasources(_SOURCE_ID_ACEPTADO))
        self.assertTrue(autonomy_core.is_valid_source_id(_SOURCE_ID_ACEPTADO))


if __name__ == "__main__":
    unittest.main()

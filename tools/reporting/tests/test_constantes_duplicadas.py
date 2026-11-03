"""Constantes duplicadas entre modulos de `tools/reporting` (v0.6 Change 5, F7).

`cli.py` no importa `publish.py` (regla de la spec: `render` no usa publish) ni depende del
nombre de archivo de `core`, asi que repite algunas constantes. Este test asegura que no
divergan hasta que exista un registro unico de codigos (deuda registrada en ARCHITECTURE.md).
"""
from __future__ import annotations

import unittest

from tools.reporting import cli
from tools.reporting import core as reporting_core
from tools.reporting import publish


class TestConstantesDuplicadas(unittest.TestCase):
    def test_nombre_de_archivo_html_igual_al_del_core(self):
        self.assertEqual(cli.REPORT_HTML_FILENAME, reporting_core.REPORT_FILENAME)

    def test_codigo_plotly_no_disponible_igual_en_cli_y_publish(self):
        self.assertEqual(cli.CODE_RENDER_PLOTLY_UNAVAILABLE, publish.CODE_PLOTLY_UNAVAILABLE)

    def test_codigo_style_invalido_igual_en_cli_y_publish(self):
        self.assertEqual(cli.CODE_STYLE_INVALID, publish.CODE_STYLE_INVALID)


if __name__ == "__main__":
    unittest.main()

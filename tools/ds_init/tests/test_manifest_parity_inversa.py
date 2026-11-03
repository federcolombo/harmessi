"""R1 dirección inversa: un módulo runtime del checkout ausente del MANIFEST
lo detecta `check_manifest_parity.verificar_modulos_runtime_en_manifest`."""
from __future__ import annotations

import unittest

from tools.ds_init import check_manifest_parity as parity
from tools.ds_init import manifest as manifest_mod


class TestParidadInversa(unittest.TestCase):
    def test_detecta_modulo_runtime_ausente(self):
        destinos = {e.destino for e in manifest_mod.MANIFEST}
        self.assertIn("tools/dsguard/scope.py", destinos)
        sin_scope = destinos - {"tools/dsguard/scope.py"}
        self.assertIn("tools/dsguard/scope.py", parity.verificar_modulos_runtime_en_manifest(sin_scope))

    def test_no_reporta_solo_checkout_ni_tests(self):
        ausentes = parity.verificar_modulos_runtime_en_manifest(set())
        self.assertNotIn("tools/ds_init/cli.py", ausentes)
        self.assertFalse([a for a in ausentes if "/tests/" in a])

    def test_manifest_actual_no_tiene_ausentes(self):
        self.assertEqual(parity.verificar_modulos_runtime_en_manifest(), [])


if __name__ == "__main__":
    unittest.main()

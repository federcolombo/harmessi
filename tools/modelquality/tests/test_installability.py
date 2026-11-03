"""Tests de instalabilidad de `tools/modelquality` (R17 de `spec.md`, v0.7
Change 2): las tres entradas VERBATIM/discovery existen en `MANIFEST` y sus
fuentes existen en el repo."""
from __future__ import annotations

import unittest
from pathlib import Path

from tools.ds_init.manifest import MANIFEST, VERBATIM, raiz_repo_origen

DESTINOS_ESPERADOS = (
    "tools/modelquality/__init__.py",
    "tools/modelquality/core.py",
    "tools/modelquality/validation.py",
)


class TestInstalabilidadModelQuality(unittest.TestCase):
    def test_las_tres_entradas_existen_exactamente_una_vez(self):
        for destino in DESTINOS_ESPERADOS:
            entradas = [e for e in MANIFEST if e.destino == destino]
            self.assertEqual(len(entradas), 1, f"se esperaba exactamente una entrada para {destino!r}")

    def test_tratamiento_verbatim_y_stage_discovery(self):
        mapa = {e.destino: e for e in MANIFEST}
        for destino in DESTINOS_ESPERADOS:
            entrada = mapa[destino]
            self.assertEqual(entrada.tratamiento, VERBATIM)
            self.assertEqual(entrada.stage_minimo, "discovery")
            self.assertEqual(entrada.fuente, destino)

    def test_fuentes_existen_en_el_repo(self):
        raiz = raiz_repo_origen()
        for destino in DESTINOS_ESPERADOS:
            ruta = raiz / destino
            self.assertTrue(ruta.is_file(), f"no existe la fuente {ruta}")

    def test_tests_del_paquete_no_van_al_manifest(self):
        destinos = {e.destino for e in MANIFEST}
        for destino_prohibido in (
            "tools/modelquality/tests/__init__.py",
            "tools/modelquality/tests/test_core.py",
            "tools/modelquality/tests/test_validation.py",
            "tools/modelquality/tests/test_installability.py",
        ):
            self.assertNotIn(destino_prohibido, destinos)


if __name__ == "__main__":
    unittest.main()

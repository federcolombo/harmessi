"""Instalabilidad de `tools/datacontracts` (v0.7 Change 0, R13): el manifest del
inicializador incluye `tools/datacontracts/__init__.py` y `tools/datacontracts/core.py`
como VERBATIM en `discovery`. Los tests de `tools/datacontracts/tests/` NO se
instalan (no están en `MANIFEST`).
"""
from __future__ import annotations

import unittest
from pathlib import Path

from tools.ds_init.manifest import (
    EXCLUSIONES_PERMANENTES,
    MANIFEST,
    VERBATIM,
    manifest_para_perfil_y_stage,
)

REPO_ORIGEN = Path(__file__).resolve().parents[3]
PERFIL = "python-jupyter-data"
RUTAS_DATACONTRACTS = (
    "tools/datacontracts/__init__.py",
    "tools/datacontracts/core.py",
)


class TestInstalabilidadDataContracts(unittest.TestCase):
    def test_una_entrada_verbatim_discovery_por_ruta(self):
        for ruta in RUTAS_DATACONTRACTS:
            with self.subTest(ruta=ruta):
                por_destino = [e for e in MANIFEST if e.destino == ruta]
                por_fuente = [e for e in MANIFEST if e.fuente == ruta]
                self.assertEqual(len(por_destino), 1)
                self.assertEqual(len(por_fuente), 1)
                entrada = por_destino[0]
                self.assertEqual(entrada.fuente, ruta)
                self.assertEqual(entrada.tratamiento, VERBATIM)
                self.assertEqual(entrada.stage_minimo, "discovery")

    def test_rutas_existen_en_el_repo(self):
        for ruta in RUTAS_DATACONTRACTS:
            self.assertTrue((REPO_ORIGEN / ruta).is_file(), ruta)

    def test_stage_discovery_incluye_todas_las_rutas(self):
        destinos = {e.destino for e in manifest_para_perfil_y_stage(PERFIL, "discovery")}
        for ruta in RUTAS_DATACONTRACTS:
            self.assertIn(ruta, destinos)

    def test_core_va_tras_init_en_orden(self):
        destinos = [e.destino for e in MANIFEST]
        indice_init = destinos.index("tools/datacontracts/__init__.py")
        indice_core = destinos.index("tools/datacontracts/core.py")
        self.assertGreater(indice_core, indice_init)

    def test_los_tests_de_datacontracts_no_van_al_manifest(self):
        for entrada in MANIFEST:
            self.assertFalse(entrada.destino.startswith("tools/datacontracts/tests"), entrada.destino)
            if entrada.fuente:
                self.assertFalse(entrada.fuente.startswith("tools/datacontracts/tests"), entrada.fuente)

    def test_destinos_nuevos_fuera_de_exclusiones_permanentes(self):
        for ruta in RUTAS_DATACONTRACTS:
            for exclusion in EXCLUSIONES_PERMANENTES:
                self.assertFalse(ruta.startswith(exclusion), f"{ruta} cae en {exclusion!r}")


if __name__ == "__main__":
    unittest.main()

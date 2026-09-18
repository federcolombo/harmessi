"""Instalabilidad de `tools/reporting` (v0.6 Change 0, R13): el manifest del
inicializador incluye `__init__.py` y `core.py` como VERBATIM en `discovery`.
Los tests de `tools/reporting/tests/` NO se instalan (no están en `MANIFEST`).
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
RUTAS_REPORTING = (
    "tools/reporting/__init__.py",
    "tools/reporting/core.py",
    "tools/reporting/governance.py",
    "tools/reporting/cli.py",
    "tools/reporting/__main__.py",
)


class TestInstalabilidadReporting(unittest.TestCase):
    def test_una_entrada_verbatim_discovery_por_ruta(self):
        for ruta in RUTAS_REPORTING:
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
        for ruta in RUTAS_REPORTING:
            self.assertTrue((REPO_ORIGEN / ruta).is_file(), ruta)

    def test_stage_discovery_incluye_ambos_destinos(self):
        destinos = {e.destino for e in manifest_para_perfil_y_stage(PERFIL, "discovery")}
        for ruta in RUTAS_REPORTING:
            self.assertIn(ruta, destinos)

    def test_entradas_de_governance_y_cli_van_tras_core_en_orden(self):
        destinos = [e.destino for e in MANIFEST]
        indice_core = destinos.index("tools/reporting/core.py")
        previo = indice_core
        for ruta in RUTAS_REPORTING[2:]:
            indice = destinos.index(ruta)
            self.assertGreater(indice, previo, ruta)
            previo = indice

    def test_los_tests_de_reporting_no_van_al_manifest(self):
        for entrada in MANIFEST:
            self.assertFalse(entrada.destino.startswith("tools/reporting/tests"), entrada.destino)
            if entrada.fuente:
                self.assertFalse(entrada.fuente.startswith("tools/reporting/tests"), entrada.fuente)

    def test_destinos_nuevos_fuera_de_exclusiones_permanentes(self):
        for ruta in RUTAS_REPORTING:
            for exclusion in EXCLUSIONES_PERMANENTES:
                self.assertFalse(ruta.startswith(exclusion), f"{ruta} cae en {exclusion!r}")


if __name__ == "__main__":
    unittest.main()

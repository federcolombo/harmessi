"""Instalabilidad de `tools/autonomy` (v0.8 Change 0, R14): el manifest del
inicializador incluye `tools/autonomy/__init__.py`, `core.py` y `policy.py`
como VERBATIM en `discovery`. Los tests de `tools/autonomy/tests/` NO se
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
RUTAS_AUTONOMY = (
    "tools/autonomy/__init__.py",
    "tools/autonomy/core.py",
    "tools/autonomy/policy.py",
)


class TestInstalabilidadAutonomy(unittest.TestCase):
    def test_una_entrada_verbatim_discovery_por_ruta(self):
        for ruta in RUTAS_AUTONOMY:
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
        for ruta in RUTAS_AUTONOMY:
            self.assertTrue((REPO_ORIGEN / ruta).is_file(), ruta)

    def test_stage_discovery_incluye_todas_las_rutas(self):
        destinos = {e.destino for e in manifest_para_perfil_y_stage(PERFIL, "discovery")}
        for ruta in RUTAS_AUTONOMY:
            self.assertIn(ruta, destinos)

    def test_init_y_core_van_antes_que_policy_en_orden(self):
        destinos = [e.destino for e in MANIFEST]
        indice_policy = destinos.index("tools/autonomy/policy.py")
        self.assertGreater(indice_policy, destinos.index("tools/autonomy/__init__.py"))
        self.assertGreater(indice_policy, destinos.index("tools/autonomy/core.py"))

    def test_los_tests_de_autonomy_no_van_al_manifest(self):
        for entrada in MANIFEST:
            self.assertFalse(entrada.destino.startswith("tools/autonomy/tests"), entrada.destino)
            if entrada.fuente:
                self.assertFalse(entrada.fuente.startswith("tools/autonomy/tests"), entrada.fuente)

    def test_destinos_nuevos_fuera_de_exclusiones_permanentes(self):
        for ruta in RUTAS_AUTONOMY:
            for exclusion in EXCLUSIONES_PERMANENTES:
                self.assertFalse(ruta.startswith(exclusion), f"{ruta} cae en {exclusion!r}")


if __name__ == "__main__":
    unittest.main()

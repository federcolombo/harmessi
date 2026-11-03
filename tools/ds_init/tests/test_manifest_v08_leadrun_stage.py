"""Tests de instalabilidad de `tools/leadrun` (v0.8 Change 2,
`20260929-lead-execution-runtime`, R17 de `spec.md`). Mismo patrón que
`TestBundlesProgressivos` de `tools/ds_init/tests/test_manifest.py`
(Change 7 v0.3): corre contra los datos fijos del propio paquete (no lee
este repo a nivel de contenido de archivos).

Verifica:
- `manifest_para_perfil_y_stage("python-jupyter-data", "discovery")` NO
  incluye ningún destino de `tools/leadrun/*` ni `tools/notebook_runner.py`.
- `manifest_para_perfil_y_stage("python-jupyter-data", "experiment")` SÍ
  incluye los 7 destinos nuevos, todos `stage_minimo="experiment"` (coherente
  con las 5 entradas ya existentes de `tools/nbrunner/*`, de las que
  `tools/leadrun` depende).
"""
from __future__ import annotations

import unittest

from tools.ds_init.manifest import MANIFEST, manifest_para_perfil_y_stage

PERFIL = "python-jupyter-data"

DESTINOS_LEADRUN = (
    "tools/leadrun/__init__.py",
    "tools/leadrun/core.py",
    "tools/leadrun/allowlist.py",
    "tools/leadrun/scripts.py",
    "tools/leadrun/notebooks.py",
    "tools/leadrun/runtime.py",
    "tools/notebook_runner.py",
)


def _destinos(stage: str) -> set:
    return {e.destino for e in manifest_para_perfil_y_stage(PERFIL, stage)}


class TestLeadrunStageMinimoExperiment(unittest.TestCase):
    def test_todas_las_entradas_de_leadrun_estan_en_stage_experiment(self):
        mapa = {e.destino: e.stage_minimo for e in MANIFEST}
        for destino in DESTINOS_LEADRUN:
            self.assertIn(destino, mapa, f"falta la entrada de manifiesto para {destino!r}")
            self.assertEqual(
                mapa[destino], "experiment",
                f"{destino!r} debe tener stage_minimo='experiment' (R17: depende de tools.nbrunner)",
            )

    def test_discovery_no_incluye_leadrun_ni_notebook_runner(self):
        destinos = _destinos("discovery")
        for destino in DESTINOS_LEADRUN:
            self.assertNotIn(destino, destinos)

    def test_experiment_incluye_los_7_destinos_nuevos(self):
        destinos = _destinos("experiment")
        for destino in DESTINOS_LEADRUN:
            self.assertIn(destino, destinos)


if __name__ == "__main__":
    unittest.main()

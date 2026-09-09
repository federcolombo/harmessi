"""Smoke test genérico mínimo, instalado en el proyecto destino como
`tools/tests/test_harness_smoke.py` (GENERADO, no VERBATIM — no es la suite de
desarrollo completa de `ds_init`, que permanece solo en el repositorio
fuente del harness).

Verifica que el harness instalado en harmessi quedó operativo:
imports básicos, `.claude/settings.json` parseable, y que los hooks
esperados están registrados. No usa ningún dato ni ruta real del proyecto
más allá de su propia raíz.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

# Igual que `tools/ds_guard.py` (línea de `sys.path.insert` junto a sus
# imports): agrega `tools/` al `sys.path` explícitamente acá, sin depender de
# que `ds_guard.py` se haya importado antes en el mismo proceso. Así cada test
# de este archivo es independiente del orden de ejecución (p. ej. correrlo
# aislado con `pytest tools/tests/test_harness_smoke.py::TestImportsHarness`).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _raiz_proyecto() -> Path:
    # tools/tests/test_harness_smoke.py -> tools/tests -> tools -> raíz
    return Path(__file__).resolve().parents[2]


class TestImportsHarness(unittest.TestCase):
    def test_importa_ds_guard(self):
        import tools.ds_guard  # noqa: F401

    def test_importa_dsguard_core(self):
        import tools.dsguard.core  # noqa: F401

    def test_importa_nbrunner_core(self):
        import tools.nbrunner.core  # noqa: F401

    def test_importa_nbrunner_manifest(self):
        import tools.nbrunner.manifest  # noqa: F401


class TestSettingsJson(unittest.TestCase):
    def test_settings_json_parsea(self):
        ruta = _raiz_proyecto() / ".claude" / "settings.json"
        self.assertTrue(ruta.exists(), f"No existe {ruta}")
        with open(ruta, "r", encoding="utf-8") as f:
            datos = json.load(f)
        self.assertIsInstance(datos, dict)

    def test_hooks_esperados_presentes(self):
        ruta = _raiz_proyecto() / ".claude" / "settings.json"
        with open(ruta, "r", encoding="utf-8") as f:
            datos = json.load(f)

        matchers = {
            entrada.get("matcher")
            for entrada in datos.get("hooks", {}).get("PreToolUse", [])
        }
        self.assertIn("Bash", matchers)


if __name__ == "__main__":
    unittest.main()

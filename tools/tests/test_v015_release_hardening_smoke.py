"""Smoke de release de v0.15 (`20261026-v015-release-hardening`): invariantes de versión y notas.

Deterministas, sin red, solo lectura.
"""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_VERSION = "0.15.0"


def _semver(v: str) -> tuple:
    m = re.match(r"^(\d+)\.(\d+)\.(\d+)", v)
    return tuple(int(x) for x in m.groups()) if m else (-1, -1, -1)


class TestVersion015(unittest.TestCase):
    # Versión vigente >= 0.15.0 (un release posterior no debe romper este smoke) y coherente entre marcadores.
    def test_version_minima(self):
        from tools.ds_init.version import HARNESS_VERSION

        self.assertGreaterEqual(_semver(HARNESS_VERSION), _semver(_VERSION))

    def test_citation_coherente(self):
        from tools.ds_init.version import HARNESS_VERSION

        cff = (REPO / "CITATION.cff").read_text(encoding="utf-8")
        self.assertIn(f"version: {HARNESS_VERSION}", cff)
        self.assertRegex(cff, r'date-released:\s*"\d{4}-\d{2}-\d{2}"')

    def test_control_json_coherente(self):
        from tools.ds_init.version import HARNESS_VERSION

        control = json.loads((REPO / ".ds_init" / "control.json").read_text(encoding="utf-8"))
        self.assertEqual(control.get("harness_version"), HARNESS_VERSION)

    def test_readme_menciona_release(self):
        readme = (REPO / "README.md").read_text(encoding="utf-8")
        self.assertIn("docs/releases/v0.15.0.md", readme)
        self.assertIn("docs/releases/v0.14.0.md", readme)


class TestNotasRelease015(unittest.TestCase):
    RUTA = REPO / "docs" / "releases" / "v0.15.0.md"

    def _txt(self) -> str:
        self.assertTrue(self.RUTA.is_file(), f"falta {self.RUTA}")
        return self.RUTA.read_text(encoding="utf-8")

    def test_secciones(self):
        txt = self._txt()
        self.assertIn("Pre-v1.0 Consolidation", txt)
        for seccion in ("## What's included", "## Compatibility", "## Known limitations", "## Deferred"):
            self.assertIn(seccion, txt)

    def test_frases_clave(self):
        txt = self._txt()
        self.assertIn("pending observation", txt)
        self.assertIn("en_verificacion", txt)

    def test_menciona_los_changes(self):
        txt = self._txt()
        for n in range(0, 7):
            self.assertRegex(txt, rf"### C{n} ", f"falta C{n} en las notas")


if __name__ == "__main__":
    unittest.main()

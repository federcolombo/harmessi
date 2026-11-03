"""Smoke de release de v1.0 (`20261102-v1-release-hardening`): invariantes de versión y notas.

Deterministas, sin red, solo lectura. `test_control_json_coherente` falla hasta que el baseline
`.ds_init/control.json` se regenera con el bump de versión (esperado).
"""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_VERSION = "1.0.0"


def _semver(v: str) -> tuple:
    m = re.match(r"^(\d+)\.(\d+)\.(\d+)", v)
    return tuple(int(x) for x in m.groups()) if m else (-1, -1, -1)


class TestVersion100(unittest.TestCase):
    # Versión vigente >= 1.0.0 (un release posterior no debe romper este smoke).
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
        for nota in ("v1.0.0", "v0.15.0", "v0.14.0"):
            self.assertIn(f"docs/releases/{nota}.md", readme)

    def test_readme_declara_python(self):
        readme = (REPO / "README.md").read_text(encoding="utf-8")
        self.assertIn("Python 3.12", readme)
        self.assertIn("Python 3.9", readme)
        self.assertIn("not executed", readme)
        self.assertIn("bounded list of tests", readme)

    def test_installation_declara_python(self):
        texto = (REPO / "docs" / "installation.md").read_text(encoding="utf-8")
        self.assertIn("Python 3.9", texto)
        self.assertIn("Python 3.12", texto)
        self.assertIn("no se ejecuta", texto)
        self.assertIn("HARMESSI-LICENSE.txt", texto)

    def test_licencia_mencionada(self):
        readme = (REPO / "README.md").read_text(encoding="utf-8")
        self.assertIn("HARMESSI-LICENSE.txt", readme)


class TestNotasRelease100(unittest.TestCase):
    RUTA = REPO / "docs" / "releases" / "v1.0.0.md"

    def _txt(self) -> str:
        self.assertTrue(self.RUTA.is_file(), f"falta {self.RUTA}")
        return self.RUTA.read_text(encoding="utf-8")

    def test_secciones(self):
        txt = self._txt()
        self.assertTrue(txt.startswith("# Harmessi v1.0.0"))
        for seccion in ("## What's included", "## Compatibility", "## Known limitations", "## Deferred",
                        "### C1 ", "### C2 "):
            self.assertIn(seccion, txt)

    def test_frases_clave(self):
        txt = self._txt()
        self.assertIn("no longer verifiable", txt)  # G11
        self.assertIn("manual step", txt)  # G14
        self.assertIn("PolyForm Shield 1.0.0", txt)
        self.assertIn("upgrade --destino", txt)

    def test_menciona_asset_de_licencia(self):
        self.assertIn("HARMESSI-LICENSE.txt", self._txt())


if __name__ == "__main__":
    unittest.main()

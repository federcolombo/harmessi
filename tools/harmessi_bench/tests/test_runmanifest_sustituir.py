"""Tests de runmanifest.sustituir_superficie (v0.14 Change 2, R4)."""
from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from tools.harmessi_bench.core import EvalTarget
from tools.harmessi_bench.runmanifest import construir_manifest, sustituir_superficie

SKILL = ".claude/skills/lead-data-scientist/skills/diagnosing-bugs.md"
RAIZ_MD = ".claude/skills/lead-data-scientist/methodology.md"


class TestSustituirSuperficie(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.raiz = Path(self._tmp.name)
        for rel, txt in {SKILL: "# Skill\nBase\n", RAIZ_MD: "# Metodologia\n",
                         ".claude/guardrails.json": "{}\n"}.items():
            p = self.raiz / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(txt.encode("utf-8"))
        self.manifest = construir_manifest("r1", EvalTarget("fake"), cases_hash="h", repo_root=self.raiz)

    def test_cambia_identidad_y_no_muta_original(self):
        original = copy.deepcopy(self.manifest)
        nuevo = sustituir_superficie(self.manifest, self.raiz, SKILL, b"# Skill\nOtra\n")
        self.assertEqual(self.manifest, original)
        self.assertNotEqual(nuevo["identity_hash"], original["identity_hash"])
        self.assertNotEqual(nuevo["skills"]["diagnosing-bugs"], original["skills"]["diagnosing-bugs"])
        self.assertNotEqual(nuevo["surfaces_hash"], original["surfaces_hash"])

    def test_mismo_contenido_mismo_identity(self):
        nuevo = sustituir_superficie(self.manifest, self.raiz, SKILL, b"# Skill\nBase\n")
        self.assertEqual(nuevo["identity_hash"], self.manifest["identity_hash"])
        self.assertEqual(nuevo["surfaces_hash"], self.manifest["surfaces_hash"])

    def test_coincide_con_cambiar_el_archivo_real(self):
        nuevo = sustituir_superficie(self.manifest, self.raiz, SKILL, b"# Skill\nOtra\n")
        (self.raiz / SKILL).write_bytes(b"# Skill\nOtra\n")
        real = construir_manifest("r1", EvalTarget("fake"), cases_hash="h", repo_root=self.raiz)
        self.assertEqual(nuevo["identity_hash"], real["identity_hash"])

    def test_no_toca_el_disco(self):
        sustituir_superficie(self.manifest, self.raiz, SKILL, b"x\n")
        self.assertEqual((self.raiz / SKILL).read_bytes(), b"# Skill\nBase\n")

    def test_superficie_raiz(self):
        nuevo = sustituir_superficie(self.manifest, self.raiz, RAIZ_MD, b"# Otra\n")
        self.assertNotEqual(nuevo["surfaces_hash"], self.manifest["surfaces_hash"])
        self.assertEqual(nuevo["skills"], self.manifest["skills"])

    def test_ruta_invalida(self):
        for ruta in ("tools/x.py", ".claude/skills/lead-data-scientist/skills/no-existe.md", "", "../x.md"):
            with self.subTest(ruta=ruta):
                with self.assertRaises(ValueError):
                    sustituir_superficie(self.manifest, self.raiz, ruta, b"x")


if __name__ == "__main__":
    unittest.main()

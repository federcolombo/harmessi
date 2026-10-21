"""v0.13 R13: validación ESTRUCTURAL del workflow de portabilidad.

Lee el YAML como texto (sin PyYAML). No afirma que el workflow se haya
ejecutado de forma remota: solo que está presente y bien formado.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
WORKFLOW = RAIZ / ".github" / "workflows" / "portability-smoke.yml"


class TestWorkflowPortabilidad(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.texto = WORKFLOW.read_text(encoding="utf-8")

    def test_existe(self):
        self.assertTrue(WORKFLOW.is_file())

    def test_disparadores(self):
        for evento in ("push:", "pull_request:", "workflow_dispatch:"):
            self.assertIn(evento, self.texto)

    def test_no_usa_pull_request_target(self):
        self.assertNotIn("pull_request_target", self.texto)

    def test_tres_os_y_un_python(self):
        m = re.search(r"os:\s*\[([^\]]*)\]", self.texto)
        self.assertIsNotNone(m)
        self.assertEqual(
            sorted(x.strip() for x in m.group(1).split(",")),
            ["macos-latest", "ubuntu-latest", "windows-latest"],
        )
        m = re.search(r"python-version:\s*\[([^\]]*)\]", self.texto)
        self.assertIsNotNone(m)
        self.assertEqual([x.strip().strip('"') for x in m.group(1).split(",")], ["3.12"])

    def test_fail_fast_false(self):
        self.assertRegex(self.texto, r"fail-fast:\s*false")

    def test_permisos_minimos(self):
        self.assertRegex(self.texto, r"(?m)^permissions:\s*\n\s+contents:\s*read\s*$")
        self.assertEqual(len(re.findall(r"(?m)^\s*permissions:", self.texto)), 1)

    def test_sin_secretos(self):
        self.assertNotIn("secrets.", self.texto)

    def test_instala_solo_pytest(self):
        instalaciones = re.findall(r"pip install ([^\n]+)", self.texto)
        self.assertEqual([i.strip() for i in instalaciones], ["pytest"])

    def test_rutas_de_tests_existen_y_no_es_la_suite_completa(self):
        rutas = re.findall(r"(?m)^\s+(tools/[\w./-]+)\s*$", self.texto)
        self.assertGreaterEqual(len(rutas), 5)
        for ruta in rutas:
            with self.subTest(ruta=ruta):
                self.assertTrue((RAIZ / ruta).exists(), ruta)
        # Ninguna ruta es un directorio de suite completa (tools/ o tools/tests sueltos).
        for ruta in rutas:
            self.assertNotIn(ruta.rstrip("/"), ("tools", "tools/tests"))

    def test_endurecimiento(self):
        self.assertRegex(self.texto, r"timeout-minutes:\s*20\b")
        self.assertRegex(self.texto, r"cancel-in-progress:\s*true")
        self.assertRegex(self.texto, r"(?m)^concurrency:\s*\n\s+group:\s*\S*\$\{\{\s*github\.ref\s*\}\}")
        self.assertRegex(self.texto, r"persist-credentials:\s*false")

    def test_incluye_este_modulo(self):
        self.assertIn("tools/tests/test_v013_ci_workflow.py", self.texto)


if __name__ == "__main__":
    unittest.main()

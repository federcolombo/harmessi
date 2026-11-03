"""Tests operacionales de `tools.leadrun.allowlist` (Corrective A,
`20261005-operational-autonomy-hardening`): intérprete simétrico y semántica
`dir/**`. Archivo propio porque `test_allowlist.py` es una suite congelada de
Change 2 (`test_v08_change4_leadrun_diff`)."""
from __future__ import annotations

import unittest

from tools.leadrun import allowlist

INTERPRETE = allowlist.normalizar_interprete("/venv/bin/python")


class TestInterpreteSimetrico(unittest.TestCase):
    """R18/R20 (`20261005-operational-autonomy-hardening`): se normalizan
    `argv[0]` e `interprete_autorizado`; tests portables con `sys.executable`."""

    def setUp(self):
        import os
        import sys

        from tools.leadrun import core

        if core.contiene_metacaracter_prohibido(sys.executable):
            self.skipTest("sys.executable contiene un metacarácter prohibido (p. ej. paréntesis)")
        self.exe = sys.executable
        self.os = os
        self.alcance = ("scripts/entrenar.py",)

    def _ok(self, argv0, autorizado):
        return allowlist.evaluar_comando([argv0, "scripts/entrenar.py"], self.alcance, autorizado)[0]

    def test_mismo_ejecutable_autorizado_crudo_o_normalizado(self):
        self.assertTrue(self._ok(self.exe, self.exe))
        self.assertTrue(self._ok(self.exe, allowlist.normalizar_interprete(self.exe)))
        self.assertTrue(self._ok(allowlist.normalizar_interprete(self.exe), self.exe))

    def test_variantes_de_case_y_separadores(self):
        norm = self.os.path.normcase
        if norm("AbC") == norm("abc"):
            self.assertTrue(self._ok(self.exe.upper(), self.exe.lower()))
            self.assertTrue(self._ok(self.exe.lower(), self.exe))
        if self.os.sep == "\\":
            self.assertTrue(self._ok(self.exe.replace("\\", "/"), self.exe))
            self.assertTrue(self._ok(self.exe, self.exe.replace("\\", "/")))

    def test_texto_con_variante_de_case(self):
        if self.os.path.normcase("AbC") != self.os.path.normcase("abc"):
            self.skipTest("filesystem sensible a mayúsculas")
        texto = f'"{self.exe.upper()}" scripts/entrenar.py'
        self.assertTrue(allowlist.evaluar_comando(texto, self.alcance, self.exe)[0])

    def test_otro_ejecutable_rechazado(self):
        permitido, forma, motivo = allowlist.evaluar_comando(
            [self.exe + "_otro", "scripts/entrenar.py"], self.alcance, self.exe
        )
        self.assertFalse(permitido)
        self.assertIn("intérprete no autorizado", motivo)

    def test_autorizado_vacio_rechazado(self):
        self.assertFalse(self._ok(self.exe, ""))


class TestAlcanceDirectorioYGlob(unittest.TestCase):
    """R33/R35/R36: `dir/**`, hermanos no cubiertos, `*` dentro de un segmento."""

    def _script(self, ruta, alcance):
        return allowlist.evaluar_comando(["/venv/bin/python", ruta], alcance, INTERPRETE)[0]

    def _pytest(self, ruta, alcance):
        return allowlist.evaluar_comando(
            ["/venv/bin/python", "-m", "pytest", ruta], alcance, INTERPRETE
        )[0]

    def test_dir_doble_asterisco_cubre_descendientes(self):
        alcance = ("scripts/**",)
        self.assertTrue(self._script("scripts/a.py", alcance))
        self.assertTrue(self._script("scripts/b/c.py", alcance))
        self.assertTrue(self._pytest("scripts/b", alcance))

    def test_dir_doble_asterisco_cubre_el_directorio_mismo(self):
        # `pytest tools/tests` con solo `tools/tests/**` declarado (R33).
        alcance = ("tools/tests/**",)
        self.assertTrue(self._pytest("tools/tests", alcance))
        self.assertFalse(self._pytest("tools/tests_old", alcance))
        self.assertFalse(self._pytest("tools", alcance))

    def test_dir_doble_asterisco_no_cubre_hermano(self):
        alcance = ("scripts/**",)
        self.assertFalse(self._script("scripts_old/a.py", alcance))
        self.assertFalse(self._script("otro/scripts/a.py", alcance))

    def test_legacy_exacto_y_prefijo_plano_se_conservan(self):
        self.assertTrue(self._script("scripts/entrenar.py", ("scripts/entrenar.py",)))
        self.assertTrue(self._script("scripts/b/c.py", ("scripts",)))
        self.assertTrue(self._script("scripts/b/c.py", ("scripts/",)))
        self.assertFalse(self._script("scripts_old/a.py", ("scripts",)))

    def test_asterisco_dentro_de_segmento(self):
        alcance = ("tools/tests/test_x_*.py",)
        self.assertTrue(self._script("tools/tests/test_x_uno.py", alcance))
        self.assertTrue(self._pytest("tools/tests/test_x_dos.py", alcance))
        self.assertFalse(self._script("tools/tests/test_y_uno.py", alcance))
        self.assertFalse(self._script("tools/tests/test_x_uno.txt", alcance))

    def test_asterisco_no_trata_otros_caracteres_como_regex(self):
        self.assertFalse(self._script("tools/aXb.py", ("tools/a.b*.py",)))


if __name__ == "__main__":
    unittest.main()

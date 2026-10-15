"""Instalación real por CLI: trae la skill domain-modeling y glossary.py, NO crea GLOSSARY.md."""
from __future__ import annotations

import io
import shutil
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from tools.harmessi import doctor as doctor_mod
from tools.harmessi.tests.test_doctor import (
    _crear_interprete_falso,
    _crear_repo_git_temporal,
    _mock_solo_interprete,
)

SKILL = ".claude/skills/lead-data-scientist/skills/domain-modeling.md"
MODULO = "tools/dsguard/glossary.py"


class TestInstalacionGlosario(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_repo_git_temporal(prefix="glossary_install_")
        self.addCleanup(shutil.rmtree, self.repo, ignore_errors=True)
        from tools.ds_init.cli import main

        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            codigo = main(["install", "--destino", str(self.repo), "--nombre", "p", "--execute"])
        self.assertEqual(codigo, 0)

    def test_instala_skill_y_modulo_sin_glossary_md(self):
        self.assertTrue((self.repo / SKILL).is_file())
        self.assertTrue((self.repo / MODULO).is_file())
        self.assertFalse((self.repo / "GLOSSARY.md").exists())

    def test_doctor_sin_faltante_ni_drift_ni_contrato_roto(self):
        _crear_interprete_falso(self.repo)
        with patch("tools.harmessi.doctor.subprocess.run", side_effect=_mock_solo_interprete(0, "")):
            resultados, _exit = doctor_mod.ejecutar(self.repo)
        faltantes = [r for r in resultados if r.codigo == "HARMESSI-SKILL-FALTANTE"]
        self.assertEqual(faltantes, [])
        drift = [
            r
            for r in resultados
            if r.codigo.startswith("HARMESSI-DRIFT")
            and ("domain-modeling" in r.mensaje or "glossary.py" in r.mensaje)
        ]
        self.assertEqual(drift, [])
        contrato = [r for r in resultados if r.codigo == "HARMESSI-SKILL-CONTRATO"]
        self.assertEqual([r.nivel for r in contrato], [doctor_mod.NIVEL_OK])


if __name__ == "__main__":
    unittest.main()

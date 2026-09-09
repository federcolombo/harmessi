"""Tests de `tools.ds_init.preflight`. Cada test crea su propio repositorio
Git temporal (`tempfile.mkdtemp()` + `git init`) como destino; ninguno apunta
a este repositorio (R14/AC15)."""
from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.ds_init.preflight import (
    DestinoInvalidoError,
    detectar_colisiones,
    validar_destino,
)


def _crear_repo_git_temporal() -> Path:
    ruta = Path(tempfile.mkdtemp(prefix="ds_init_test_"))
    subprocess.run(["git", "init", str(ruta)], capture_output=True, text=True, check=True)
    subprocess.run(["git", "-C", str(ruta), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(ruta), "config", "user.name", "Test"], check=True)
    return ruta


class TestValidarDestino(unittest.TestCase):
    def setUp(self):
        self._repos_temporales = []

    def tearDown(self):
        for ruta in self._repos_temporales:
            shutil.rmtree(ruta, ignore_errors=True)

    def _nuevo_repo(self) -> Path:
        ruta = _crear_repo_git_temporal()
        self._repos_temporales.append(ruta)
        return ruta

    def test_destino_inexistente(self):
        ruta = Path(tempfile.mkdtemp(prefix="ds_init_test_")) / "no-existe"
        with self.assertRaises(DestinoInvalidoError) as cm:
            validar_destino(ruta)
        self.assertIn("no existe", str(cm.exception))

    def test_destino_no_es_repo_git(self):
        ruta = Path(tempfile.mkdtemp(prefix="ds_init_test_"))
        try:
            with self.assertRaises(DestinoInvalidoError) as cm:
                validar_destino(ruta)
            self.assertIn("no es un repositorio Git", str(cm.exception))
        finally:
            shutil.rmtree(ruta, ignore_errors=True)

    def test_working_tree_sucio(self):
        ruta = self._nuevo_repo()
        (ruta / "archivo_sucio.txt").write_text("contenido", encoding="utf-8")
        with self.assertRaises(DestinoInvalidoError) as cm:
            validar_destino(ruta)
        self.assertIn("no está limpio", str(cm.exception))

    def test_destino_valido_no_levanta(self):
        ruta = self._nuevo_repo()
        # No debe levantar ninguna excepción.
        validar_destino(ruta)


class TestDetectarColisiones(unittest.TestCase):
    def setUp(self):
        self.ruta = _crear_repo_git_temporal()

    def tearDown(self):
        shutil.rmtree(self.ruta, ignore_errors=True)

    def test_sin_colisiones(self):
        plan = ["CLAUDE.md", "tools/ds_guard.py"]
        self.assertEqual(detectar_colisiones(plan, self.ruta), [])

    def test_con_colisiones(self):
        (self.ruta / "CLAUDE.md").write_text("ya existe", encoding="utf-8")
        plan = ["CLAUDE.md", "tools/ds_guard.py"]
        self.assertEqual(detectar_colisiones(plan, self.ruta), ["CLAUDE.md"])

    def test_colision_en_subdirectorio(self):
        (self.ruta / ".claude" / "agents").mkdir(parents=True)
        (self.ruta / ".claude" / "agents" / "python-data-engineer.md").write_text(
            "ya existe", encoding="utf-8"
        )
        plan = [".claude/agents/python-data-engineer.md", ".claude/agents/notebook-runner.md"]
        self.assertEqual(
            detectar_colisiones(plan, self.ruta),
            [".claude/agents/python-data-engineer.md"],
        )


if __name__ == "__main__":
    unittest.main()

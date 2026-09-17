"""Tests de `tools.dsimpact.git_source` (R1)."""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ORIGEN = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ORIGEN / "tools"))

from dsimpact import git_source  # noqa: E402


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=str(repo), check=True, capture_output=True, text=True)


def _crear_repo() -> Path:
    repo = Path(tempfile.mkdtemp(prefix="dsimpact_git_test_"))
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "a.py").write_text("x = 1\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "inicial")
    return repo


class TestValidarRef(unittest.TestCase):
    def test_ref_valida(self):
        repo = _crear_repo()
        self.assertTrue(git_source.validar_ref(repo, "HEAD"))

    def test_ref_invalida(self):
        repo = _crear_repo()
        self.assertFalse(git_source.validar_ref(repo, "no-existe-esta-ref"))


class TestListarCambios(unittest.TestCase):
    def test_sin_diff_since_head(self):
        repo = _crear_repo()
        cambios = git_source.listar_cambios(repo, "HEAD", False)
        self.assertEqual(cambios, [])

    def test_modificado(self):
        repo = _crear_repo()
        (repo / "a.py").write_text("x = 2\n", encoding="utf-8")
        cambios = git_source.listar_cambios(repo, "HEAD", False)
        self.assertEqual(len(cambios), 1)
        self.assertEqual(cambios[0].path, "a.py")
        self.assertEqual(cambios[0].status, git_source.STATUS_MODIFIED)

    def test_agregado(self):
        repo = _crear_repo()
        (repo / "b.py").write_text("y = 1\n", encoding="utf-8")
        _git(repo, "add", ".")
        cambios = git_source.listar_cambios(repo, None, True)
        self.assertEqual(len(cambios), 1)
        self.assertEqual(cambios[0].status, git_source.STATUS_ADDED)

    def test_eliminado(self):
        repo = _crear_repo()
        (repo / "a.py").unlink()
        cambios = git_source.listar_cambios(repo, "HEAD", False)
        self.assertEqual(cambios[0].status, git_source.STATUS_DELETED)
        self.assertEqual(cambios[0].path, "a.py")

    def test_renombrado(self):
        # Renombrada PURA (mismo contenido): git la detecta al 100% de
        # similitud vía -M. Un cambio de contenido grande relativo al
        # archivo cae por debajo del umbral por defecto (50%) y git reporta
        # D+A en vez de R -- eso no es un bug de `listar_cambios`, es el
        # comportamiento correcto de `git diff -M` (ver mensaje del Lead).
        repo = _crear_repo()
        _git(repo, "mv", "a.py", "c.py")
        cambios = git_source.listar_cambios(repo, None, True)
        self.assertEqual(len(cambios), 1)
        self.assertEqual(cambios[0].status, git_source.STATUS_RENAMED)
        self.assertEqual(cambios[0].path, "c.py")
        self.assertEqual(cambios[0].old_path, "a.py")


class TestContenido(unittest.TestCase):
    def test_contenido_after_since_lee_filesystem(self):
        repo = _crear_repo()
        (repo / "a.py").write_text("x = 99\n", encoding="utf-8")
        texto = git_source.contenido_after(repo, False, "a.py")
        self.assertEqual(texto, "x = 99\n")

    def test_contenido_before_since(self):
        repo = _crear_repo()
        (repo / "a.py").write_text("x = 99\n", encoding="utf-8")
        texto = git_source.contenido_before(repo, "HEAD", False, "a.py")
        self.assertEqual(texto, "x = 1\n")

    def test_contenido_before_archivo_nuevo_es_none(self):
        repo = _crear_repo()
        (repo / "nuevo.py").write_text("z = 1\n", encoding="utf-8")
        texto = git_source.contenido_before(repo, "HEAD", False, "nuevo.py")
        self.assertIsNone(texto)

    def test_contenido_after_staged_lee_indice(self):
        repo = _crear_repo()
        (repo / "a.py").write_text("x = 5\n", encoding="utf-8")
        _git(repo, "add", ".")
        (repo / "a.py").write_text("x = 999\n", encoding="utf-8")  # sin stagear
        texto = git_source.contenido_after(repo, True, "a.py")
        self.assertEqual(texto, "x = 5\n")


class TestListarConsumidoresCandidatos(unittest.TestCase):
    def test_respeta_gitignore_y_filtra_extension(self):
        repo = _crear_repo()
        (repo / ".gitignore").write_text("ignorado.py\n", encoding="utf-8")
        (repo / "ignorado.py").write_text("z = 1\n", encoding="utf-8")
        (repo / "consumidor.py").write_text("z = 1\n", encoding="utf-8")
        (repo / "notas.txt").write_text("no me busca\n", encoding="utf-8")
        candidatos = git_source.listar_consumidores_candidatos(repo)
        self.assertIn("consumidor.py", candidatos)
        self.assertIn("a.py", candidatos)
        self.assertNotIn("ignorado.py", candidatos)
        self.assertNotIn("notas.txt", candidatos)


class TestGitSourceError(unittest.TestCase):
    def test_listar_cambios_ref_invalida_lanza(self):
        repo = _crear_repo()
        with self.assertRaises(git_source.GitSourceError):
            git_source.listar_cambios(repo, "no-existe-ref-xyz", False)


if __name__ == "__main__":
    unittest.main()

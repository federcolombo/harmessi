"""Change 20261016-v011-git-scope-fail-closed (R7): los comandos de `ds_guard.py` convierten un fallo
de Git en un mensaje explícito y exit 3 (sin traceback); `validate` con git ilegible en
`evaluar_alcance` emite el hallazgo `ALCANCE-GIT-ILEGIBLE` (exit != 0).

Se ejecutan en el mismo proceso (`args.func(args)`) con `_repo_root` parcheado hacia un repo
temporal real. `ds_guard` importa `dsguard.repo` (sin prefijo `tools.`), por eso las excepciones se
toman de `ds_guard.repo`.
"""
from __future__ import annotations

import contextlib
import io
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

REPO_ORIGEN = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ORIGEN / "tools"))

import ds_guard  # noqa: E402
from dsguard import core  # noqa: E402

CHANGE_ID = "20261016-prueba-git"
NOTEBOOK_VACIO = '{"cells": [], "metadata": {}, "nbformat": 4, "nbformat_minor": 5}\n'


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=str(repo), check=True, capture_output=True,
        text=True, encoding="utf-8",
    ).stdout


def _repo(con_commit: bool = True) -> Path:
    repo = Path(tempfile.mkdtemp(prefix="dsguard_cli_failclosed_"))
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "config", "commit.gpgsign", "false")
    if con_commit:
        (repo / "base.txt").write_text("base\n", encoding="utf-8")
        _git(repo, "add", ".")
        _git(repo, "commit", "-q", "-m", "inicial")
    return repo


def _crear_change(repo: Path, estado: str = "en_verificacion", baseline=None) -> Path:
    change_dir = repo / "openspec" / "changes" / CHANGE_ID
    change_dir.mkdir(parents=True, exist_ok=True)
    (change_dir / "tasks.md").write_text(
        f"# Tareas\n\nestado: {estado}\n\n## Tareas\n- [x] algo\n", encoding="utf-8")
    if baseline is None:
        baseline = _git(repo, "rev-parse", "HEAD").strip()
    control = {
        "schema_version": 1,
        "change_id": CHANGE_ID,
        "modo": "completo",
        "origen": "test",
        "creado_utc": core.ahora_utc(),
        "baseline": {"commit": baseline, "rama": "main", "capturado_utc": core.ahora_utc()},
        "alcance": {"rutas_autorizadas": [f"openspec/changes/{CHANGE_ID}/*"]},
        "aprobaciones": [],
        "transiciones": [],
        "sesiones": [],
    }
    core.escribir_control(change_dir / "control.json", control)
    return change_dir


def _correr(repo: Path, *argv: str):
    """(rc, stdout, stderr) de `ds_guard` en proceso, con `_repo_root` apuntando al repo temporal."""
    args = ds_guard.construir_parser().parse_args(list(argv))
    salida, error = io.StringIO(), io.StringIO()
    with mock.patch.object(ds_guard, "_repo_root", return_value=repo):
        with contextlib.redirect_stdout(salida), contextlib.redirect_stderr(error):
            rc = args.func(args)
    return rc, salida.getvalue(), error.getvalue()


class _Base(unittest.TestCase):
    def setUp(self):
        self.repo = _repo()
        self.addCleanup(shutil.rmtree, self.repo, True)

    def _assert_error_git(self, rc, err):
        self.assertEqual(rc, 3)
        self.assertIn("ALCANCE-GIT-ILEGIBLE", err)
        self.assertNotIn("Traceback", err)


class TestStatusValidate(_Base):
    def test_status_con_git_fallando_exit_3(self):
        _crear_change(self.repo)
        with mock.patch.object(
            ds_guard.repo, "files_out_of_scope", side_effect=ds_guard.repo.GitCommandError("x")
        ):
            rc, _out, err = _correr(self.repo, "status", "--change-id", CHANGE_ID)
        self._assert_error_git(rc, err)

    def test_status_con_git_ausente_exit_3(self):
        _crear_change(self.repo)
        with mock.patch.object(
            ds_guard.repo, "files_out_of_scope", side_effect=RuntimeError("git no disponible")
        ):
            rc, _out, err = _correr(self.repo, "status", "--change-id", CHANGE_ID)
        self._assert_error_git(rc, err)

    def test_validate_con_diff_check_fallando_exit_3(self):
        _crear_change(self.repo)
        with mock.patch.object(
            ds_guard.repo, "diff_check", side_effect=ds_guard.repo.GitCommandError("x")
        ):
            rc, _out, err = _correr(self.repo, "validate", "--change-id", CHANGE_ID)
        self._assert_error_git(rc, err)

    def test_validate_con_baseline_invalido_emite_hallazgo(self):
        # El fallo de git dentro de `evaluar_alcance` NO es exit 3: es un hallazgo (exit != 0).
        _crear_change(self.repo, baseline="0" * 40)
        rc, out, _err = _correr(self.repo, "validate", "--change-id", CHANGE_ID)
        self.assertNotEqual(rc, 0)
        self.assertIn("ALCANCE-GIT-ILEGIBLE", out)


class TestArchive(_Base):
    def test_archive_con_ls_files_fallando_exit_3(self):
        _crear_change(self.repo, estado="cerrada")
        falso = SimpleNamespace(returncode=128, stdout="", stderr="fatal: boom")
        with mock.patch.object(ds_guard.sdd, "gate_cierre", return_value=[]):
            with mock.patch.object(ds_guard.repo, "_git", return_value=falso):
                rc, _out, err = _correr(self.repo, "archive", "--change-id", CHANGE_ID)
        self._assert_error_git(rc, err)

    def test_archive_con_is_tree_clean_fallando_exit_3(self):
        _crear_change(self.repo, estado="cerrada")
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-q", "-m", "change")
        with mock.patch.object(ds_guard.sdd, "gate_cierre", return_value=[]):
            with mock.patch.object(
                ds_guard.repo, "is_tree_clean", side_effect=ds_guard.repo.GitCommandError("x")
            ):
                rc, _out, err = _correr(self.repo, "archive", "--change-id", CHANGE_ID)
        self._assert_error_git(rc, err)


class TestInit(unittest.TestCase):
    def _repo_con_plantillas(self, con_commit: bool) -> Path:
        repo = _repo(con_commit)
        self.addCleanup(shutil.rmtree, repo, True)
        rel = Path(".claude") / "skills" / "lead-data-scientist" / "templates"
        shutil.copytree(REPO_ORIGEN / rel, repo / rel)
        return repo

    def test_init_en_repo_sin_commits_exit_3_con_mensaje_claro(self):
        # Decisión M3: sin HEAD no hay baseline posible; no se escribe un baseline vacío.
        repo = self._repo_con_plantillas(con_commit=False)
        rc, _out, err = _correr(repo, "init", "--change-id", CHANGE_ID, "--modo", "completo")
        self.assertEqual(rc, 3)
        self.assertIn("ALCANCE-GIT-ILEGIBLE", err)
        self.assertNotIn("Traceback", err)

    def test_init_con_git_ausente_exit_3(self):
        repo = self._repo_con_plantillas(con_commit=True)
        with mock.patch.object(ds_guard.repo, "get_head", side_effect=RuntimeError("git no disponible")):
            rc, _out, err = _correr(repo, "init", "--change-id", CHANGE_ID, "--modo", "completo")
        self.assertEqual(rc, 3)
        self.assertNotIn("Traceback", err)


class TestNotebookDiffTocados(_Base):
    def test_tocados_ignora_rutas_inexistentes_en_disco(self):
        # Rename (ruta vieja ya no existe) y borrado: no deben abortar el lote.
        (self.repo / "viejo.ipynb").write_text(NOTEBOOK_VACIO, encoding="utf-8")
        (self.repo / "borrado.ipynb").write_text(NOTEBOOK_VACIO, encoding="utf-8")
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-q", "-m", "notebooks")
        _crear_change(self.repo)
        _git(self.repo, "mv", "viejo.ipynb", "nuevo.ipynb")
        (self.repo / "borrado.ipynb").unlink()
        rc, _out, err = _correr(
            self.repo, "notebook-diff", "--change-id", CHANGE_ID, "--tocados", "--contra", "HEAD")
        self.assertNotIn(rc, (2, 3), err)
        self.assertNotIn("Traceback", err)

    def test_tocados_con_git_fallando_exit_3(self):
        _crear_change(self.repo)
        with mock.patch.object(
            ds_guard.repo, "list_dirty_files", side_effect=ds_guard.repo.GitCommandError("x")
        ):
            rc, _out, err = _correr(
                self.repo, "notebook-diff", "--change-id", CHANGE_ID, "--tocados", "--contra", "HEAD")
        self._assert_error_git(rc, err)


if __name__ == "__main__":
    unittest.main()

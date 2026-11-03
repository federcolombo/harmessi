"""Tests de `tools.launcher_common`: la lógica compartida de los lanzadores
Python puros de los hooks `PreToolUse` (Bloque 2, reliability v0.2.0), que
reemplazan a `hook_launcher.sh` / `hook_launcher_presupuesto.sh`.

Usa repositorios Git temporales propios (nunca este repositorio, mismo
criterio R14/AC15 que los tests de `tools.ds_init`)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import launcher_common

# Referencia al `subprocess.run` real, capturada antes de que ningún test
# parchee `tools.launcher_common.subprocess.run` -- como ambos módulos
# comparten el mismo objeto módulo `subprocess`, parchear `.run` ahí lo
# reemplaza también para cualquier código que luego busque `subprocess.run`
# de nuevo (incluido un `side_effect` ingenuo, que recursaría sobre sí
# mismo). Mismo patrón que `_OS_REPLACE_REAL` en
# `tools/ds_init/tests/test_writer_staging.py`.
_SUBPROCESS_RUN_REAL = subprocess.run


def _mock_solo_lanzamiento_final(returncode: int = 0):
    """`side_effect` para `tools.launcher_common.subprocess.run`: dejar
    pasar sin mockear cualquier llamada a `git` (la resolución de
    `resolver_repo_root` debe correr de verdad, sobre el repo temporal real
    del test) y devolver un `CompletedProcess` fabricado únicamente para la
    llamada final que lanza el hook."""

    def _side_effect(cmd, **kwargs):
        if cmd[0] == "git":
            return _SUBPROCESS_RUN_REAL(cmd, **kwargs)
        return subprocess.CompletedProcess(args=cmd, returncode=returncode)

    return _side_effect


def _crear_repo_git_temporal(prefix: str = "launcher_common_test_") -> Path:
    ruta = Path(tempfile.mkdtemp(prefix=prefix))
    subprocess.run(["git", "init", str(ruta)], capture_output=True, text=True, check=True)
    subprocess.run(["git", "-C", str(ruta), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(ruta), "config", "user.name", "Test"], check=True)
    (ruta / "README.md").write_text("repo de prueba\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(ruta), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(ruta), "commit", "-m", "inicial"], capture_output=True, text=True, check=True
    )
    return ruta


def _crear_interprete_falso(repo_root: Path, venv_dir: str = ".venv") -> Path:
    """Crea un archivo vacío en la ruta que `ruta_interprete_venv` resuelve
    para el layout del SO real -- `is_file()` no necesita que sea un binario
    ejecutable de verdad para los checks de existencia."""
    interprete = launcher_common.ruta_interprete_venv(repo_root, venv_dir)
    interprete.parent.mkdir(parents=True, exist_ok=True)
    interprete.write_text("", encoding="utf-8")
    return interprete


def _escribir_control_json(repo_root: Path, venv_dir: str) -> None:
    dir_control = repo_root / ".ds_init"
    dir_control.mkdir(parents=True, exist_ok=True)
    (dir_control / "control.json").write_text(
        json.dumps({"configuracion": {"venv_dir": venv_dir}}, indent=2) + "\n", encoding="utf-8"
    )


class TestRutaInterpreteVenv(unittest.TestCase):
    def test_layout_windows(self):
        repo_root = Path("C:/repo")
        self.assertEqual(
            launcher_common.ruta_interprete_venv(repo_root, ".venv", windows=True),
            repo_root / ".venv" / "Scripts" / "python.exe",
        )

    def test_layout_posix(self):
        repo_root = Path("/repo")
        self.assertEqual(
            launcher_common.ruta_interprete_venv(repo_root, ".venv", windows=False),
            repo_root / ".venv" / "bin" / "python",
        )

    def test_layout_posix_con_venv_dir_custom(self):
        repo_root = Path("/repo")
        self.assertEqual(
            launcher_common.ruta_interprete_venv(repo_root, "entorno", windows=False),
            repo_root / "entorno" / "bin" / "python",
        )


class TestResolverVenvDir(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_repo_git_temporal()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_default_sin_control_json(self):
        self.assertEqual(launcher_common.resolver_venv_dir(self.repo), ".venv")

    def test_venv_dir_custom_desde_control_json(self):
        _escribir_control_json(self.repo, "entorno-custom")
        self.assertEqual(launcher_common.resolver_venv_dir(self.repo), "entorno-custom")

    def test_control_json_corrupto_usa_default(self):
        dir_control = self.repo / ".ds_init"
        dir_control.mkdir(parents=True, exist_ok=True)
        (dir_control / "control.json").write_text("{ esto no es JSON válido", encoding="utf-8")
        self.assertEqual(launcher_common.resolver_venv_dir(self.repo), ".venv")

    def test_control_json_sin_seccion_configuracion_usa_default(self):
        dir_control = self.repo / ".ds_init"
        dir_control.mkdir(parents=True, exist_ok=True)
        (dir_control / "control.json").write_text(json.dumps({"perfil": "x"}), encoding="utf-8")
        self.assertEqual(launcher_common.resolver_venv_dir(self.repo), ".venv")


class TestResolverRepoRoot(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_repo_git_temporal()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_checkout_principal(self):
        repo_root = launcher_common.resolver_repo_root(str(self.repo))
        self.assertEqual(repo_root.resolve(), self.repo.resolve())

    def test_no_es_git_devuelve_none(self):
        no_git = Path(tempfile.mkdtemp(prefix="launcher_common_test_no_git_"))
        try:
            self.assertIsNone(launcher_common.resolver_repo_root(str(no_git)))
        finally:
            shutil.rmtree(no_git, ignore_errors=True)

    def test_worktree_resuelve_al_repo_principal_no_al_worktree(self):
        worktree_dir = self.repo.parent / f"{self.repo.name}_worktree"
        subprocess.run(
            ["git", "-C", str(self.repo), "worktree", "add", "-b", "rama-worktree", str(worktree_dir)],
            capture_output=True,
            text=True,
            check=True,
        )
        try:
            repo_root = launcher_common.resolver_repo_root(str(worktree_dir))
            self.assertEqual(repo_root.resolve(), self.repo.resolve())
            self.assertNotEqual(repo_root.resolve(), worktree_dir.resolve())
        finally:
            subprocess.run(
                ["git", "-C", str(self.repo), "worktree", "remove", "--force", str(worktree_dir)],
                capture_output=True,
                text=True,
            )
            shutil.rmtree(worktree_dir, ignore_errors=True)


class TestLanzarHook(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_repo_git_temporal()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_claude_project_dir_no_definida_falla_cerrado(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CLAUDE_PROJECT_DIR", None)
            with patch("tools.launcher_common.subprocess.run") as mock_run:
                codigo = launcher_common.lanzar_hook("hook_launcher", "tools/x/hook.py")
        self.assertEqual(codigo, 2)
        mock_run.assert_not_called()

    def test_no_es_repo_git_falla_cerrado(self):
        no_git = Path(tempfile.mkdtemp(prefix="launcher_common_test_no_git_"))
        try:
            with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(no_git)}):
                with patch("tools.launcher_common.subprocess.run", wraps=subprocess.run) as mock_run:
                    codigo = launcher_common.lanzar_hook("hook_launcher", "tools/x/hook.py")
            self.assertEqual(codigo, 2)
        finally:
            shutil.rmtree(no_git, ignore_errors=True)

    def test_interprete_inexistente_falla_cerrado(self):
        with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(self.repo)}):
            with patch(
                "tools.launcher_common.subprocess.run", wraps=subprocess.run
            ) as mock_run_wrapper:
                codigo = launcher_common.lanzar_hook("hook_launcher", "tools/x/hook.py")
        self.assertEqual(codigo, 2)
        # Nunca debe llegar a intentar ejecutar el hook real (solo el `git
        # rev-parse` de resolución, que sí corre de verdad vía `wraps`).
        comandos_ejecutados = [llamada.args[0] for llamada in mock_run_wrapper.call_args_list]
        self.assertTrue(all(cmd[0] == "git" for cmd in comandos_ejecutados))

    def test_hook_inexistente_falla_cerrado(self):
        _crear_interprete_falso(self.repo)
        with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(self.repo)}):
            with patch(
                "tools.launcher_common.subprocess.run", wraps=subprocess.run
            ) as mock_run_wrapper:
                codigo = launcher_common.lanzar_hook("hook_launcher", "tools/x/hook_que_no_existe.py")
        self.assertEqual(codigo, 2)
        comandos_ejecutados = [llamada.args[0] for llamada in mock_run_wrapper.call_args_list]
        self.assertTrue(all(cmd[0] == "git" for cmd in comandos_ejecutados))

    def test_lanzamiento_exitoso_usa_interprete_y_hook_resueltos(self):
        interprete = _crear_interprete_falso(self.repo)
        hook_relativo = "tools/x/hook.py"
        (self.repo / "tools" / "x").mkdir(parents=True, exist_ok=True)
        (self.repo / hook_relativo).write_text("", encoding="utf-8")

        with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(self.repo)}):
            with patch(
                "tools.launcher_common.subprocess.run", side_effect=_mock_solo_lanzamiento_final(0)
            ) as mock_run:
                codigo = launcher_common.lanzar_hook("hook_launcher", hook_relativo)

        self.assertEqual(codigo, 0)
        # La última llamada a `subprocess.run` (después de la de `git
        # rev-parse`, que corrió de verdad) debe invocar exactamente el
        # intérprete y el hook resueltos, sin pasar por ningún shell.
        ultima_llamada = mock_run.call_args_list[-1]
        self.assertEqual(ultima_llamada.args[0], [str(interprete), str(self.repo / hook_relativo)])

    def test_propaga_el_returncode_del_hook_real(self):
        _crear_interprete_falso(self.repo)
        hook_relativo = "tools/x/hook.py"
        (self.repo / "tools" / "x").mkdir(parents=True, exist_ok=True)
        (self.repo / hook_relativo).write_text("", encoding="utf-8")

        with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(self.repo)}):
            with patch(
                "tools.launcher_common.subprocess.run", side_effect=_mock_solo_lanzamiento_final(2)
            ):
                codigo = launcher_common.lanzar_hook("hook_launcher", hook_relativo)

        self.assertEqual(codigo, 2)

    def test_venv_dir_custom_desde_control_json_se_respeta(self):
        _escribir_control_json(self.repo, "entorno-custom")
        interprete = _crear_interprete_falso(self.repo, venv_dir="entorno-custom")
        hook_relativo = "tools/x/hook.py"
        (self.repo / "tools" / "x").mkdir(parents=True, exist_ok=True)
        (self.repo / hook_relativo).write_text("", encoding="utf-8")

        with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(self.repo)}):
            with patch(
                "tools.launcher_common.subprocess.run", side_effect=_mock_solo_lanzamiento_final(0)
            ) as mock_run:
                codigo = launcher_common.lanzar_hook("hook_launcher", hook_relativo)

        self.assertEqual(codigo, 0)
        ultima_llamada = mock_run.call_args_list[-1]
        self.assertEqual(ultima_llamada.args[0][0], str(interprete))
        self.assertIn("entorno-custom", ultima_llamada.args[0][0])

    def test_worktree_usa_venv_del_repo_principal_y_hook_del_worktree(self):
        hook_relativo = "tools/x/hook.py"
        (self.repo / "tools" / "x").mkdir(parents=True, exist_ok=True)
        (self.repo / hook_relativo).write_text("contenido versionado\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.repo), "add", "."], check=True)
        subprocess.run(
            ["git", "-C", str(self.repo), "commit", "-m", "agrega hook"],
            capture_output=True,
            text=True,
            check=True,
        )
        interprete = _crear_interprete_falso(self.repo)

        worktree_dir = self.repo.parent / f"{self.repo.name}_worktree2"
        subprocess.run(
            ["git", "-C", str(self.repo), "worktree", "add", "-b", "rama-worktree2", str(worktree_dir)],
            capture_output=True,
            text=True,
            check=True,
        )
        try:
            with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(worktree_dir)}):
                with patch(
                    "tools.launcher_common.subprocess.run", side_effect=_mock_solo_lanzamiento_final(0)
                ) as mock_run:
                    codigo = launcher_common.lanzar_hook("hook_launcher", hook_relativo)

            self.assertEqual(codigo, 0)
            llamadas_no_git = [
                llamada for llamada in mock_run.call_args_list if llamada.args[0][0] != "git"
            ]
            self.assertEqual(len(llamadas_no_git), 1)
            comando_hook = llamadas_no_git[0].args[0]
            # Intérprete resuelto contra el repo PRINCIPAL (el worktree no
            # tiene `.venv` propio); script del hook resuelto contra el
            # worktree (contenido versionado, presente en su propio checkout).
            self.assertEqual(comando_hook[0], str(interprete))
            self.assertEqual(comando_hook[1], str(worktree_dir / hook_relativo))
        finally:
            subprocess.run(
                ["git", "-C", str(self.repo), "worktree", "remove", "--force", str(worktree_dir)],
                capture_output=True,
                text=True,
            )
            shutil.rmtree(worktree_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()

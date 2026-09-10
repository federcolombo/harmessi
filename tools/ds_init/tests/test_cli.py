"""Test end-to-end de `tools.ds_init.cli` en modo `--dry-run`. Crea su propio
repositorio Git temporal (`tempfile.mkdtemp()` + `git init`) como destino;
nunca escribe sobre este repositorio (R14/AC15). Verifica que `--dry-run` no
modifica el árbol de archivos del destino: ni un archivo nuevo, ni uno
modificado."""
from __future__ import annotations

import hashlib
import io
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

from tools.ds_init import writer
from tools.ds_init.cli import main


def _crear_repo_git_temporal() -> Path:
    ruta = Path(tempfile.mkdtemp(prefix="ds_init_test_cli_"))
    subprocess.run(["git", "init", str(ruta)], capture_output=True, text=True, check=True)
    subprocess.run(["git", "-C", str(ruta), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(ruta), "config", "user.name", "Test"], check=True)
    # Commit inicial para que `git status --porcelain` quede limpio.
    (ruta / "README.md").write_text("repo de prueba\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(ruta), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(ruta), "commit", "-m", "inicial"],
        capture_output=True,
        text=True,
        check=True,
    )
    return ruta


def _snapshot_arbol(ruta: Path) -> dict:
    """Nombres relativos -> hash de contenido, para todo archivo bajo `ruta`
    fuera de `.git/`. Se usa hash de contenido en vez de mtime porque el
    mtime de archivos dentro de `.git/` (p.ej. `.git/hooks/*.sample`) puede
    cambiar por motivos ajenos a la lógica bajo prueba, generando un test
    flaky; comparar contenido es evidencia real de escritura."""
    snapshot = {}
    for archivo in ruta.rglob("*"):
        if not archivo.is_file():
            continue
        relativo = archivo.relative_to(ruta)
        if ".git" in relativo.parts:
            continue
        snapshot[str(relativo)] = hashlib.sha256(archivo.read_bytes()).hexdigest()
    return snapshot


def _git_status_porcelain(ruta: Path) -> str:
    """Salida de `git status --porcelain`: confirma indirectamente que
    tampoco cambió nada dentro de `.git/` que Git considere relevante
    (staged/unstaged/untracked)."""
    resultado = subprocess.run(
        ["git", "-C", str(ruta), "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=True,
    )
    return resultado.stdout


class TestCliDryRun(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_repo_git_temporal()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_dry_run_no_modifica_el_destino(self):
        snapshot_antes = _snapshot_arbol(self.repo)
        status_antes = _git_status_porcelain(self.repo)

        codigo = main(
            [
                "--destino",
                str(self.repo),
                "--nombre",
                "proyecto-de-prueba",
                "--dry-run",
            ]
        )

        self.assertEqual(codigo, 0)

        snapshot_despues = _snapshot_arbol(self.repo)
        self.assertEqual(
            snapshot_antes,
            snapshot_despues,
            "El destino se modificó durante --dry-run",
        )
        self.assertEqual(
            status_antes,
            _git_status_porcelain(self.repo),
            "El estado de git del destino cambió durante --dry-run",
        )

    def test_dry_run_es_el_default_sin_flag(self):
        snapshot_antes = _snapshot_arbol(self.repo)
        status_antes = _git_status_porcelain(self.repo)

        codigo = main(
            [
                "--destino",
                str(self.repo),
                "--nombre",
                "proyecto-de-prueba",
            ]
        )

        self.assertEqual(codigo, 0)
        self.assertEqual(_snapshot_arbol(self.repo), snapshot_antes)
        self.assertEqual(status_antes, _git_status_porcelain(self.repo))


class TestCliExecuteAbortadoControlado(unittest.TestCase):
    """Reliability v0.2.0: si `writer.instalar` levanta
    `InstalacionAbortadaError` durante `--execute`, `main()` debe manejarla
    de forma controlada -- mensaje `[ABORTADO]` por stderr y código de salida
    != 0 -- en vez de dejar propagar un traceback crudo."""

    def setUp(self):
        self.repo = _crear_repo_git_temporal()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_fallo_de_instalacion_produce_mensaje_abortado_y_codigo_no_cero(self):
        with patch(
            "tools.ds_init.cli.writer.instalar",
            side_effect=writer.InstalacionAbortadaError("fallo inyectado por el test"),
        ):
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                codigo = main(
                    [
                        "--destino",
                        str(self.repo),
                        "--nombre",
                        "proyecto-de-prueba",
                        "--execute",
                    ]
                )

        self.assertNotEqual(codigo, 0)
        salida_error = stderr.getvalue()
        self.assertIn("[ABORTADO]", salida_error)
        self.assertIn("fallo inyectado por el test", salida_error)


if __name__ == "__main__":
    unittest.main()

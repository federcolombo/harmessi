"""Test end-to-end de `tools.harmessi.cli`: en v0.2 solo existe el
subcomando `doctor`. Usa un repositorio Git temporal propio (nunca este
repositorio, R14/AC15)."""
from __future__ import annotations

import io
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from tools import launcher_common
from tools.ds_init import writer as ds_init_writer
from tools.ds_init.planner import construir_plan
from tools.ds_init.version import HARNESS_VERSION
from tools.harmessi.cli import main

PERFIL = "python-jupyter-data"

# Igual patrón que `tools/harmessi/tests/test_doctor.py`: `doctor` usa
# `subprocess.run` tanto para sus checks de `git` (deben correr de verdad)
# como para el check RUNTIME-INTERPRETE (el único simulado acá).
_SUBPROCESS_RUN_REAL = subprocess.run


def _mock_solo_interprete(returncode: int = 0, stderr: str = ""):
    def _side_effect(cmd, **kwargs):
        if cmd[0] == "git":
            return _SUBPROCESS_RUN_REAL(cmd, **kwargs)
        return subprocess.CompletedProcess(args=cmd, returncode=returncode, stdout="", stderr=stderr)

    return _side_effect


def _crear_interprete_falso(destino: Path) -> Path:
    interprete = launcher_common.ruta_interprete_venv(destino, ".venv")
    interprete.parent.mkdir(parents=True, exist_ok=True)
    interprete.write_text("", encoding="utf-8")
    return interprete


def _crear_repo_git_temporal() -> Path:
    ruta = Path(tempfile.mkdtemp(prefix="harmessi_cli_test_"))
    subprocess.run(["git", "init", str(ruta)], capture_output=True, text=True, check=True)
    subprocess.run(["git", "-C", str(ruta), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(ruta), "config", "user.name", "Test"], check=True)
    (ruta / "README.md").write_text("repo de prueba\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(ruta), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(ruta), "commit", "-m", "inicial"], capture_output=True, text=True, check=True
    )
    return ruta


def _instalar_harness_real(destino: Path):
    nombre = "proyecto-de-prueba"
    config = {
        "perfil": PERFIL,
        "nombre": nombre,
        "notebooks_dir": "notebooks",
        "venv_dir": ".venv",
        "destino": str(destino),
        "integrar_claude": False,
        "placeholders": {
            "NOMBRE_PROYECTO": nombre,
            "NOTEBOOKS_DIR": "notebooks",
            "VENV_DIR": ".venv",
            "FECHA_INSTALACION": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "HARNESS_VERSION": HARNESS_VERSION,
            "RUTAS_PROHIBIDAS_JSON": "[]",
        },
    }
    plan = construir_plan(PERFIL, destino, config)
    return ds_init_writer.instalar(plan, destino, config)


class TestCliDoctor(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_repo_git_temporal()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_doctor_sobre_instalacion_completa_devuelve_0(self):
        _instalar_harness_real(self.repo)
        _crear_interprete_falso(self.repo)
        stdout = io.StringIO()
        with patch("tools.harmessi.doctor.subprocess.run", side_effect=_mock_solo_interprete(0, "")):
            with redirect_stdout(stdout):
                codigo = main(["doctor", "--destino", str(self.repo)])
        self.assertEqual(codigo, 0)
        self.assertIn("Harmessi doctor", stdout.getvalue())
        self.assertIn("Resumen:", stdout.getvalue())

    def test_doctor_sobre_repo_sin_instalar_devuelve_1(self):
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            codigo = main(["doctor", "--destino", str(self.repo)])
        self.assertEqual(codigo, 1)
        self.assertIn("[ERROR]", stdout.getvalue())

    def test_doctor_falla_de_orquestacion_no_crashea_crudo(self):
        stderr = io.StringIO()
        with patch(
            "tools.harmessi.cli.doctor_mod.ejecutar", side_effect=RuntimeError("boom inesperado")
        ):
            with redirect_stderr(stderr):
                codigo = main(["doctor", "--destino", str(self.repo)])
        self.assertEqual(codigo, 1)
        self.assertIn("[ABORTADO]", stderr.getvalue())

    def test_sin_subcomando_no_crashea_y_devuelve_codigo_no_cero(self):
        with self.assertRaises(SystemExit) as cm:
            main([])
        # `argparse` con subparsers `required=True` sale con código 2 (uso
        # inválido) en vez de lanzar una excepción no controlada -- no es un
        # traceback de Harmessi, es el comportamiento estándar de argparse.
        self.assertNotEqual(cm.exception.code, 0)


if __name__ == "__main__":
    unittest.main()

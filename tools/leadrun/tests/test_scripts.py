"""Tests de `tools.leadrun.scripts` (T4, R10 de
`openspec/changes/20260929-lead-execution-runtime/spec.md`).

Ejecuta subprocesos REALES contra fixtures sintéticas de
`tools/leadrun/tests/fixtures/` (a diferencia de T1-T3, acá se prueba
justamente la función que envuelve `subprocess`)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

from tools.leadrun import core, scripts

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
PYTHON = sys.executable


def _request(argv, command_form="script", timeout_seconds=10):
    return core.ExecutionRequest(
        command_form=command_form,
        interpreter=PYTHON,
        argv=tuple(argv),
        scope=(str(FIXTURES_DIR),),
        timeout_seconds=timeout_seconds,
    )


class TestEjecutarScriptExitoso(unittest.TestCase):
    def test_exit_0_stdout_corto(self):
        script = FIXTURES_DIR / "script_exit_0.py"
        request = _request([PYTHON, str(script)])
        resultado = scripts.ejecutar_script(request, REPO_ROOT)
        self.assertEqual(resultado["exit_code"], 0)
        self.assertFalse(resultado["timed_out"])
        self.assertIn("hola desde script_exit_0", resultado["stdout_summary"])
        self.assertGreaterEqual(resultado["duration_seconds"], 0.0)

    def test_stdout_summary_no_se_trunca(self):
        # Confirma explícitamente que `scripts.py` NO trunca: el texto real
        # impreso por el script llega completo (el truncado es de
        # `runtime.py`, R9 de `spec.md`).
        script = FIXTURES_DIR / "script_exit_0.py"
        request = _request([PYTHON, str(script)])
        resultado = scripts.ejecutar_script(request, REPO_ROOT)
        self.assertEqual(resultado["stdout_summary"], "hola desde script_exit_0\n")


class TestEjecutarScriptExitCodeDistinto(unittest.TestCase):
    def test_exit_1(self):
        script = FIXTURES_DIR / "script_exit_1.py"
        request = _request([PYTHON, str(script)])
        resultado = scripts.ejecutar_script(request, REPO_ROOT)
        self.assertEqual(resultado["exit_code"], 1)
        self.assertFalse(resultado["timed_out"])


class TestEjecutarScriptTimeout(unittest.TestCase):
    def test_loop_infinito_timeout(self):
        script = FIXTURES_DIR / "script_loop_infinito.py"
        request = _request([PYTHON, str(script)], timeout_seconds=1)
        resultado = scripts.ejecutar_script(request, REPO_ROOT)
        self.assertTrue(resultado["timed_out"])
        self.assertEqual(resultado["exit_code"], scripts.EXIT_CODE_TIMEOUT)
        # El test no debe tardar mucho más que el timeout declarado.
        self.assertLess(resultado["duration_seconds"], 10.0)


class TestEjecutarScriptComandoInexistente(unittest.TestCase):
    def test_interprete_inexistente_no_propaga_excepcion(self):
        interprete_falso = str(REPO_ROOT / "intérprete_que_no_existe_xyz")
        request = core.ExecutionRequest(
            command_form="script",
            interpreter=interprete_falso,
            argv=(interprete_falso, str(FIXTURES_DIR / "script_exit_0.py")),
            scope=(str(FIXTURES_DIR),),
            timeout_seconds=10,
        )
        resultado = scripts.ejecutar_script(request, REPO_ROOT)
        self.assertEqual(resultado["exit_code"], scripts.EXIT_CODE_COMANDO_NO_ENCONTRADO)
        self.assertFalse(resultado["timed_out"])
        self.assertIn("no encontrado", resultado["stderr_summary"])


class TestEjecutarPytest(unittest.TestCase):
    def test_ejecutar_pytest_target_trivial(self):
        target = FIXTURES_DIR / "test_pytest_trivial.py"
        request = _request(
            [PYTHON, "-m", "pytest", str(target)],
            command_form="pytest",
        )
        resultado = scripts.ejecutar_pytest(request, REPO_ROOT)
        self.assertEqual(resultado["exit_code"], 0)
        self.assertFalse(resultado["timed_out"])
        self.assertIn("1 passed", resultado["stdout_summary"])


if __name__ == "__main__":
    unittest.main()

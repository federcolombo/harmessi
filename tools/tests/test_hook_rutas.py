"""Tests de `tools.dsguard.hook_rutas` (Bloque 3, reliability v0.2.0): el
contrato de entrada/salida del hook `PreToolUse` de protección de rutas --
exit codes, fail-closed ante entradas corruptas, nunca traceback crudo.
Ejecuta el script real como subproceso (mismo contrato que vería Claude
Code), sobre un repositorio temporal propio."""
from __future__ import annotations

import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

REPO_ORIGEN = Path(__file__).resolve().parents[2]
HOOK_RUTAS = REPO_ORIGEN / "tools" / "dsguard" / "hook_rutas.py"

sys.path.insert(0, str(REPO_ORIGEN / "tools" / "dsguard"))
import hook_rutas  # noqa: E402
from dsguard import pathguard  # noqa: E402


def _crear_repo_temporal() -> Path:
    return Path(tempfile.mkdtemp(prefix="hook_rutas_test_"))


def _correr_hook(payload_texto: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(HOOK_RUTAS)],
        input=payload_texto,
        capture_output=True,
        text=True,
    )


class TestHookRutasContrato(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_repo_temporal()
        # `hook_rutas.py` calcula `REPO_ROOT` desde `__file__`, no desde
        # `CLAUDE_PROJECT_DIR` -- para testear contra un repo temporal
        # habría que ejecutar una copia del script ahí. En cambio, estos
        # tests corren el script REAL de este repositorio (`REPO_ORIGEN`),
        # así que las rutas evaluadas son relativas a `REPO_ORIGEN`, no a
        # `self.repo`. `self.repo` solo se usa donde no hace falta esa
        # relación (payloads inválidos).

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_payload_no_json_deniega_sin_traceback(self):
        resultado = _correr_hook("esto no es json")
        self.assertEqual(resultado.returncode, 2)
        self.assertNotIn("Traceback", resultado.stderr)
        self.assertIn("deniega por seguridad", resultado.stderr)

    def test_payload_no_es_objeto_json_deniega(self):
        resultado = _correr_hook("[1, 2, 3]")
        self.assertEqual(resultado.returncode, 2)
        self.assertNotIn("Traceback", resultado.stderr)

    def test_stdin_vacio_deniega_sin_traceback(self):
        resultado = _correr_hook("")
        self.assertEqual(resultado.returncode, 2)
        self.assertNotIn("Traceback", resultado.stderr)

    def test_tool_call_benigna_permite(self):
        payload = json.dumps({"tool_name": "Read", "tool_input": {"file_path": "README.md"}})
        resultado = _correr_hook(payload)
        self.assertEqual(resultado.returncode, 0)
        self.assertEqual(resultado.stdout, "")

    def test_tool_call_sobre_secreto_deniega(self):
        payload = json.dumps({"tool_name": "Read", "tool_input": {"file_path": ".env"}})
        resultado = _correr_hook(payload)
        self.assertEqual(resultado.returncode, 2)
        self.assertIn("secreto", resultado.stderr)

    def test_tool_desconocida_permite(self):
        payload = json.dumps({"tool_name": "Glob", "tool_input": {"pattern": "*.py"}})
        resultado = _correr_hook(payload)
        self.assertEqual(resultado.returncode, 0)


class TestHookRutasFailClosedInterno(unittest.TestCase):
    """Ejecuta `hook_rutas.main()` en proceso (no subprocess), mockeando
    `pathguard` para forzar los dos caminos de fail-closed que no conviene
    provocar tocando el `guardrails.json` real de este repositorio: config
    corrupta y una excepción interna inesperada durante la evaluación."""

    def _correr_main_con_stdin(self, payload_texto: str) -> tuple:
        stdin_original = sys.stdin
        sys.stdin = io.StringIO(payload_texto)
        stdout, stderr = io.StringIO(), io.StringIO()
        try:
            with redirect_stdout(stdout), redirect_stderr(stderr):
                codigo = hook_rutas.main()
        finally:
            sys.stdin = stdin_original
        return codigo, stdout.getvalue(), stderr.getvalue()

    def test_guardrails_json_corrupto_deniega(self):
        payload = json.dumps({"tool_name": "Read", "tool_input": {"file_path": "README.md"}})
        with patch(
            "hook_rutas.pathguard.cargar_config",
            side_effect=pathguard.ConfigGuardrailsError("guardrails.json corrupto de prueba"),
        ):
            codigo, _, stderr = self._correr_main_con_stdin(payload)
        self.assertEqual(codigo, 2)
        self.assertIn("corrupto", stderr)
        self.assertNotIn("Traceback", stderr)

    def test_error_interno_inesperado_deniega(self):
        payload = json.dumps({"tool_name": "Read", "tool_input": {"file_path": "README.md"}})
        with patch(
            "hook_rutas.pathguard.evaluar_tool_call",
            side_effect=RuntimeError("boom inesperado"),
        ):
            codigo, _, stderr = self._correr_main_con_stdin(payload)
        self.assertEqual(codigo, 2)
        self.assertIn("error interno", stderr.lower())
        self.assertNotIn("Traceback", stderr)


if __name__ == "__main__":
    unittest.main()

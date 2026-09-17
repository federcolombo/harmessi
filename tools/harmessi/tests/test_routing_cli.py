"""Test del subcomando `routing` de `tools.harmessi.cli` (v0.5 Change 2,
`provider-routing`). Usa el `policy.example.json` real bundleado en
`tools/routing/examples/` y rutas a `tmp_path` inexistentes/corruptas --
nunca invoca ninguna CLI de proveedor real."""
from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from tools.harmessi.cli import main

_EXAMPLE_POLICY_PATH = (
    Path(__file__).resolve().parents[2] / "routing" / "examples" / "policy.example.json"
)


class TestRoutingCli(unittest.TestCase):
    def test_show_sin_politica_mensaje_explicito(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            ruta_inexistente = str(Path(tmp) / "no_existe" / "routing.json")
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                codigo = main(["routing", "show", "--policy", ruta_inexistente])

        self.assertEqual(codigo, 0)
        self.assertIn("sin política de routing declarada", stdout.getvalue())

    def test_show_example_json_3_reglas(self):
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            codigo = main(["routing", "show", "--policy", str(_EXAMPLE_POLICY_PATH), "--json"])
        self.assertEqual(codigo, 0)

        datos = json.loads(stdout.getvalue())
        self.assertEqual(len(datos["rules"]), 3)
        self.assertIsNone(datos["default"])

    def test_resolve_writer_provider_claude_code(self):
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            codigo = main(
                [
                    "routing",
                    "resolve",
                    "--role",
                    "writer",
                    "--policy",
                    str(_EXAMPLE_POLICY_PATH),
                    "--json",
                ]
            )
        self.assertEqual(codigo, 0)

        decision = json.loads(stdout.getvalue())
        self.assertEqual(decision["provider_id"], "claude_code")
        self.assertTrue(decision["matched"])

    def test_resolve_rol_inexistente_matched_false_sin_error(self):
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            codigo = main(
                [
                    "routing",
                    "resolve",
                    "--role",
                    "inexistente",
                    "--policy",
                    str(_EXAMPLE_POLICY_PATH),
                    "--json",
                ]
            )
        self.assertEqual(codigo, 0)

        decision = json.loads(stdout.getvalue())
        self.assertFalse(decision["matched"])

    def test_resolve_policy_corrupta_exit_1_stderr_claro(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            ruta_corrupta = Path(tmp) / "routing.json"
            ruta_corrupta.write_text("{ esto no es json valido", encoding="utf-8")

            stderr = io.StringIO()
            with redirect_stderr(stderr):
                codigo = main(
                    ["routing", "resolve", "--role", "writer", "--policy", str(ruta_corrupta)]
                )

        self.assertEqual(codigo, 1)
        self.assertIn("routing resolve", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()

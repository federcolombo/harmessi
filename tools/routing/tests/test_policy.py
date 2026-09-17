"""Tests de `tools.routing.policy.load_policy` (v0.5 Change 2,
`provider-routing`). Deterministas, no invocan ningún proveedor real."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from tools.routing.policy import load_policy

_EXAMPLE_PATH = (
    Path(__file__).resolve().parents[1] / "examples" / "policy.example.json"
)


class TestLoadPolicy(unittest.TestCase):
    def test_sin_archivo_devuelve_policy_vacia(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            ruta_inexistente = Path(tmp) / "no_existe" / "routing.json"
            policy = load_policy(ruta_inexistente)

        self.assertEqual(policy.rules, [])
        self.assertIsNone(policy.default)

    def test_carga_example_real_3_reglas(self):
        policy = load_policy(_EXAMPLE_PATH)

        self.assertEqual(len(policy.rules), 3)
        self.assertIsNone(policy.default)

        roles = {regla.role for regla in policy.rules}
        self.assertEqual(roles, {"writer", "reviewer", "metodologo"})

        regla_writer = next(r for r in policy.rules if r.role == "writer")
        self.assertEqual(regla_writer.provider_id, "claude_code")
        self.assertEqual(regla_writer.task_type, "*")
        self.assertTrue(regla_writer.reason)

    def test_regla_sin_reason_levanta_value_error_con_indice(self):
        import tempfile

        contenido = {
            "rules": [
                {"role": "writer", "provider_id": "claude_code", "reason": "ok"},
                {"role": "reviewer", "provider_id": "claude_code", "reason": ""},
            ],
            "default": None,
        }
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "routing.json"
            ruta.write_text(json.dumps(contenido), encoding="utf-8")

            with self.assertRaises(ValueError) as contexto:
                load_policy(ruta)

        self.assertIn("1", str(contexto.exception))

    def test_regla_no_dict_levanta_value_error_con_indice(self):
        import tempfile

        contenido = {
            "rules": ["no_es_un_dict"],
            "default": None,
        }
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "routing.json"
            ruta.write_text(json.dumps(contenido), encoding="utf-8")

            with self.assertRaises(ValueError) as contexto:
                load_policy(ruta)

        mensaje = str(contexto.exception)
        self.assertIn("0", mensaje)
        self.assertNotIsInstance(contexto.exception, AttributeError)

    def test_default_no_dict_levanta_value_error_con_default(self):
        import tempfile

        contenido = {
            "rules": [],
            "default": "auto",
        }
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "routing.json"
            ruta.write_text(json.dumps(contenido), encoding="utf-8")

            with self.assertRaises(ValueError) as contexto:
                load_policy(ruta)

        mensaje = str(contexto.exception)
        self.assertIn("default", mensaje)
        self.assertNotIsInstance(contexto.exception, AttributeError)


if __name__ == "__main__":
    unittest.main()

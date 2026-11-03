"""Tests de `tools.ds_init.settings_merge`. Trabaja sobre dicts en memoria,
sin tocar ningún repositorio real (R14)."""
from __future__ import annotations

import unittest

from tools.ds_init.settings_merge import ConflictoIncompatibleError, fusionar


class TestFusionar(unittest.TestCase):
    def test_preserva_clave_existente_no_conflictiva(self):
        existente = {"worktree": {"bgIsolation": "none"}, "miClavePropia": True}
        nuevo = {
            "hooks": {
                "PreToolUse": [
                    {"matcher": "Bash", "hooks": [{"type": "command", "command": "bash hook.sh"}]}
                ]
            }
        }
        resultado = fusionar(existente, nuevo)
        self.assertEqual(resultado["miClavePropia"], True)
        self.assertEqual(resultado["worktree"], {"bgIsolation": "none"})
        self.assertIn("hooks", resultado)

    def test_no_muta_los_dicts_de_entrada(self):
        existente = {"a": 1}
        nuevo = {"b": 2}
        fusionar(existente, nuevo)
        self.assertEqual(existente, {"a": 1})
        self.assertEqual(nuevo, {"b": 2})

    def test_agrega_hooks_nuevos_sin_pisar_los_existentes(self):
        existente = {
            "hooks": {
                "PreToolUse": [
                    {"matcher": "MiMatcherPropio", "hooks": [{"type": "command", "command": "echo propio"}]}
                ]
            }
        }
        nuevo = {
            "hooks": {
                "PreToolUse": [
                    {"matcher": "Bash", "hooks": [{"type": "command", "command": "bash hook.sh"}]}
                ]
            }
        }
        resultado = fusionar(existente, nuevo)
        matchers = {entrada["matcher"] for entrada in resultado["hooks"]["PreToolUse"]}
        self.assertEqual(matchers, {"MiMatcherPropio", "Bash"})

    def test_mismo_hook_exacto_no_duplica(self):
        entrada_hook = {"matcher": "Bash", "hooks": [{"type": "command", "command": "bash hook.sh"}]}
        existente = {"hooks": {"PreToolUse": [dict(entrada_hook)]}}
        nuevo = {"hooks": {"PreToolUse": [dict(entrada_hook)]}}
        resultado = fusionar(existente, nuevo)
        self.assertEqual(len(resultado["hooks"]["PreToolUse"]), 1)

    def test_conflicto_incompatible_mismo_matcher_distinto_command(self):
        existente = {
            "hooks": {
                "PreToolUse": [
                    {"matcher": "Bash", "hooks": [{"type": "command", "command": "bash propio.sh"}]}
                ]
            }
        }
        nuevo = {
            "hooks": {
                "PreToolUse": [
                    {"matcher": "Bash", "hooks": [{"type": "command", "command": "bash hook.sh"}]}
                ]
            }
        }
        with self.assertRaises(ConflictoIncompatibleError) as cm:
            fusionar(existente, nuevo)
        self.assertIn("Bash", str(cm.exception))

    def test_conflicto_incompatible_clave_escalar(self):
        existente = {"modo": "estricto"}
        nuevo = {"modo": "laxo"}
        with self.assertRaises(ConflictoIncompatibleError):
            fusionar(existente, nuevo)

    def test_clave_escalar_igual_no_es_conflicto(self):
        existente = {"modo": "estricto"}
        nuevo = {"modo": "estricto"}
        resultado = fusionar(existente, nuevo)
        self.assertEqual(resultado["modo"], "estricto")

    def test_destino_sin_settings_previos(self):
        existente = {}
        nuevo = {
            "worktree": {"bgIsolation": "none"},
            "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": []}]},
        }
        resultado = fusionar(existente, nuevo)
        self.assertEqual(resultado["worktree"], {"bgIsolation": "none"})
        self.assertEqual(resultado["hooks"]["PreToolUse"][0]["matcher"], "Bash")


if __name__ == "__main__":
    unittest.main()

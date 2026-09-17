"""Tests de `tools.dsguard.core.validar_usuario_sin_email`
(`openspec/changes/20260917-remove-personal-email/`): heurística simple que
rechaza un `--usuario` con forma de email en los comandos de `ds_guard` que
persisten identidad humana (`approve`, `remediation extend`, `decision
add/supersede/revoke`).

Tests directos y baratos sobre la función pura, sin CLI ni git.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ORIGEN = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ORIGEN / "tools"))

from dsguard import core  # noqa: E402


class TestValidarUsuarioSinEmail(unittest.TestCase):
    def test_nombre_humano_normal_es_valido(self):
        self.assertIsNone(core.validar_usuario_sin_email("Federico Colombo"))

    def test_email_es_rechazado_con_mensaje_no_vacio_que_menciona_el_valor(self):
        mensaje = core.validar_usuario_sin_email("alguien@ejemplo.com")
        self.assertIsNotNone(mensaje)
        self.assertNotEqual(mensaje, "")
        self.assertIn("alguien@ejemplo.com", mensaje)

    def test_string_vacio_no_es_responsabilidad_de_esta_funcion(self):
        # La validación de "campo obligatorio no vacío" ya existe en otro punto
        # (p. ej. argparse `required=True` para --usuario en ds_guard.py, y
        # `decision._campos_vacios` para el ledger de decisiones) -- esta
        # función solo detecta forma de email, no la duplica acá. Un string
        # vacío no contiene '@', así que es `None` (válido) desde el punto de
        # vista de esta heurística puntual.
        self.assertIsNone(core.validar_usuario_sin_email(""))


if __name__ == "__main__":
    unittest.main()

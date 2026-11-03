"""Tests de `tools.providers.core`: `classify_availability_error` y
`list_providers` (v0.5 Change 0)."""
from __future__ import annotations

import unittest

from tools.providers.core import (
    ProviderCapabilities,
    ProviderInfo,
    classify_availability_error,
    list_providers,
)


class TestClassifyAvailabilityError(unittest.TestCase):
    def test_quota_por_rate_limit_exceeded(self):
        self.assertEqual(
            classify_availability_error(1, "Error: rate limit exceeded, try again later"), "quota"
        )

    def test_quota_por_429(self):
        self.assertEqual(classify_availability_error(1, "HTTP 429 Too Many Requests"), "quota")

    def test_unauthenticated_por_not_logged_in(self):
        self.assertEqual(
            classify_availability_error(1, "Error: not logged in"), "unauthenticated"
        )

    def test_unauthenticated_case_insensitive(self):
        self.assertEqual(
            classify_availability_error(1, "AUTHENTICATION FAILED"), "unauthenticated"
        )

    def test_unavailable_por_exit_code_127(self):
        self.assertEqual(classify_availability_error(127, ""), "unavailable")

    def test_unavailable_por_command_not_found(self):
        self.assertEqual(
            classify_availability_error(1, "bash: foo: command not found"), "unavailable"
        )

    def test_none_para_error_generico(self):
        self.assertIsNone(
            classify_availability_error(1, "SyntaxError: invalid syntax")
        )

    def test_none_para_stderr_vacio_con_exit_code_1(self):
        self.assertIsNone(classify_availability_error(1, ""))

    def test_none_para_no_such_file(self):
        # Fix 2: un archivo de configuración faltante no es indisponibilidad
        # del proveedor, es un error de configuración/código -- no debe
        # encubrirse clasificándolo como "unavailable".
        self.assertIsNone(
            classify_availability_error(1, "Error: no such file or directory: config.json")
        )

    def test_none_para_mensaje_de_exito_de_autenticacion(self):
        # Fix 2 / criterio de aceptación 2: "authentication" a secas producía
        # falsos positivos con mensajes de éxito.
        self.assertIsNone(
            classify_availability_error(1, "Authentication successful, proceeding...")
        )

    def test_none_para_429_pegado_sin_separador(self):
        # Fix 2: límite de palabra evita falso positivo cuando "429" está
        # pegado a otros caracteres sin separador.
        self.assertIsNone(classify_availability_error(1, "HTTP42900 something else"))

    def test_quota_por_429_con_limite_de_palabra_en_traceback(self):
        # Limitación conocida y aceptada (ver criterios de aceptación,
        # sección 6, punto 3): `\b429\b` SÍ matchea un traceback real como
        # este, porque los límites de palabra rodean el número igual dentro
        # de la frase. No es perfecto, es "mejor que antes" (ya no matchea
        # "42900" pegado sin separador). No nos bloqueamos en resolver este
        # caso límite acá -- documentado como conocido.
        self.assertEqual(
            classify_availability_error(1, 'File "app.py", line 429, in <module>'), "quota"
        )


class _AdapterFalsoNormal:
    provider_id = "falso_normal"
    cli_command = "falso"
    display_name = "Falso Normal"

    def detect(self):
        return ProviderInfo(
            provider_id=self.provider_id,
            display_name=self.display_name,
            cli_command=self.cli_command,
            available=True,
            authenticated=None,
            version="1.0",
            capabilities=ProviderCapabilities(),
            detail="ok",
        )


class _AdapterFalsoRoto:
    provider_id = "falso_roto"
    cli_command = "falso_roto"
    display_name = "Falso Roto"

    def detect(self):
        raise RuntimeError("boom")


class TestListProviders(unittest.TestCase):
    def test_adapter_roto_no_crashea_y_queda_no_disponible(self):
        registro = {
            "falso_normal": _AdapterFalsoNormal(),
            "falso_roto": _AdapterFalsoRoto(),
        }
        resultados = list_providers(registro)
        self.assertEqual(len(resultados), 2)

        por_id = {r.provider_id: r for r in resultados}
        self.assertTrue(por_id["falso_normal"].available)
        self.assertFalse(por_id["falso_roto"].available)
        self.assertIn("falso_roto", por_id["falso_roto"].detail)
        self.assertTrue(por_id["falso_roto"].detail)

    def test_registro_vacio_devuelve_lista_vacia(self):
        self.assertEqual(list_providers({}), [])


if __name__ == "__main__":
    unittest.main()

"""Tests de `tools.leadrun.allowlist` (T2, R8-R9 de
`openspec/changes/20260929-lead-execution-runtime/spec.md`)."""
from __future__ import annotations

import unittest

from tools.leadrun import allowlist

INTERPRETE = allowlist.normalizar_interprete("/venv/bin/python")
ALCANCE = ("scripts/entrenar.py", "tools/leadrun/tests")


class TestFormaScript(unittest.TestCase):
    def test_script_dentro_de_alcance_permitido(self):
        argv = ["/venv/bin/python", "scripts/entrenar.py", "--epochs", "10"]
        permitido, forma, motivo = allowlist.evaluar_comando(argv, ALCANCE, INTERPRETE)
        self.assertTrue(permitido)
        self.assertEqual(forma, "script")
        self.assertEqual(motivo, "")

    def test_script_fuera_de_alcance_rechazado(self):
        argv = ["/venv/bin/python", "scripts/otro.py"]
        permitido, forma, motivo = allowlist.evaluar_comando(argv, ALCANCE, INTERPRETE)
        self.assertFalse(permitido)
        self.assertIsNone(forma)
        self.assertIn("alcance", motivo)

    def test_script_con_espacio_y_metacaracter_rechazado(self):
        # Nombre de script que intenta inyectar un subshell vía `$(`.
        argv = ["/venv/bin/python", "scripts/entrenar raro $(rm -rf /).py"]
        permitido, forma, motivo = allowlist.evaluar_comando(argv, ALCANCE, INTERPRETE)
        self.assertFalse(permitido)
        self.assertIsNone(forma)

    def test_script_con_traversal_rechazado(self):
        argv = ["/venv/bin/python", "scripts/../../../etc/entrenar.py"]
        permitido, forma, motivo = allowlist.evaluar_comando(argv, ALCANCE, INTERPRETE)
        self.assertFalse(permitido)

    def test_script_con_ruta_absoluta_rechazado(self):
        argv = ["/venv/bin/python", "/scripts/entrenar.py"]
        permitido, forma, motivo = allowlist.evaluar_comando(argv, ALCANCE, INTERPRETE)
        self.assertFalse(permitido)


class TestEncadenamiento(unittest.TestCase):
    def test_argv_con_encadenamiento_rechazado(self):
        argv = ["/venv/bin/python", "scripts/entrenar.py", "&&", "rm", "-rf", "/"]
        permitido, forma, motivo = allowlist.evaluar_comando(argv, ALCANCE, INTERPRETE)
        self.assertFalse(permitido)
        self.assertIsNone(forma)

    def test_argv_con_punto_y_coma_rechazado(self):
        argv = ["/venv/bin/python", "scripts/entrenar.py;rm"]
        permitido, forma, motivo = allowlist.evaluar_comando(argv, ALCANCE, INTERPRETE)
        self.assertFalse(permitido)

    def test_texto_con_punto_y_coma_despues_de_notebook_valido_rechazado(self):
        texto = (
            '"/venv/bin/python" tools/notebook_runner.py run --manifest '
            'openspec/changes/x/runs/r.json; rm -rf data'
        )
        permitido, forma, motivo = allowlist.evaluar_comando(texto, (), INTERPRETE)
        self.assertFalse(permitido)
        self.assertIsNone(forma)


class TestInterprete(unittest.TestCase):
    def test_interprete_distinto_rechazado(self):
        argv = ["/usr/bin/python3", "scripts/entrenar.py"]
        permitido, forma, motivo = allowlist.evaluar_comando(argv, ALCANCE, INTERPRETE)
        self.assertFalse(permitido)
        self.assertIn("intérprete", motivo)


class TestFormaPytest(unittest.TestCase):
    def test_pytest_con_ruta_dentro_de_alcance_permitido(self):
        argv = ["/venv/bin/python", "-m", "pytest", "tools/leadrun/tests", "-k", "test_algo"]
        permitido, forma, motivo = allowlist.evaluar_comando(argv, ALCANCE, INTERPRETE)
        self.assertTrue(permitido)
        self.assertEqual(forma, "pytest")

    def test_pytest_con_flag_con_metacaracter_rechazado(self):
        argv = ["/venv/bin/python", "-m", "pytest", "tools/leadrun/tests", "-k", "a;b"]
        permitido, forma, motivo = allowlist.evaluar_comando(argv, ALCANCE, INTERPRETE)
        self.assertFalse(permitido)

    def test_pytest_sin_ruta_en_alcance_rechazado(self):
        argv = ["/venv/bin/python", "-m", "pytest", "otro/paquete/tests"]
        permitido, forma, motivo = allowlist.evaluar_comando(argv, ALCANCE, INTERPRETE)
        self.assertFalse(permitido)


class TestFormaNotebook(unittest.TestCase):
    def test_notebook_valido_permitido(self):
        argv = [
            "/venv/bin/python",
            "tools/notebook_runner.py",
            "run",
            "--manifest",
            "openspec/changes/x/runs/r.json",
            "--dry-run",
        ]
        permitido, forma, motivo = allowlist.evaluar_comando(argv, (), INTERPRETE)
        self.assertTrue(permitido)
        self.assertEqual(forma, "notebook")

    def test_notebook_texto_valido_permitido(self):
        texto = (
            '"/venv/bin/python" tools/notebook_runner.py run --manifest '
            'openspec/changes/x/runs/r.json --execute'
        )
        permitido, forma, motivo = allowlist.evaluar_comando(texto, (), INTERPRETE)
        self.assertTrue(permitido)
        self.assertEqual(forma, "notebook")

    def test_notebook_con_traversal_en_manifest_rechazado(self):
        argv = [
            "/venv/bin/python",
            "tools/notebook_runner.py",
            "run",
            "--manifest",
            "../../secreto.json",
        ]
        permitido, forma, motivo = allowlist.evaluar_comando(argv, (), INTERPRETE)
        self.assertFalse(permitido)
        self.assertIsNone(forma)

    def test_notebook_con_ruta_absoluta_windows_rechazado(self):
        argv = [
            "/venv/bin/python",
            "tools/notebook_runner.py",
            "run",
            "--manifest",
            r"C:\secreto.json",
        ]
        permitido, forma, motivo = allowlist.evaluar_comando(argv, (), INTERPRETE)
        self.assertFalse(permitido)

    def test_notebook_manifest_fuera_de_runs_rechazado(self):
        argv = [
            "/venv/bin/python",
            "tools/notebook_runner.py",
            "run",
            "--manifest",
            "openspec/changes/x/otra/r.json",
        ]
        permitido, forma, motivo = allowlist.evaluar_comando(argv, (), INTERPRETE)
        self.assertFalse(permitido)


class TestFormaCliDiagnostic(unittest.TestCase):
    def test_ds_guard_status_permitido_sin_alcance(self):
        argv = ["/venv/bin/python", "tools/ds_guard.py", "status"]
        permitido, forma, motivo = allowlist.evaluar_comando(argv, (), INTERPRETE)
        self.assertTrue(permitido)
        self.assertEqual(forma, "cli_diagnostic")

    def test_ds_profile_permitido_sin_alcance(self):
        argv = ["/venv/bin/python", "-m", "tools.ds_profile", "--json"]
        permitido, forma, motivo = allowlist.evaluar_comando(argv, (), INTERPRETE)
        self.assertTrue(permitido)
        self.assertEqual(forma, "cli_diagnostic")

    def test_harmessi_permitido_sin_alcance(self):
        argv = ["/venv/bin/python", "-m", "tools.harmessi", "doctor"]
        permitido, forma, motivo = allowlist.evaluar_comando(argv, (), INTERPRETE)
        self.assertTrue(permitido)
        self.assertEqual(forma, "cli_diagnostic")

    def test_modulo_no_autorizado_rechazado(self):
        argv = ["/venv/bin/python", "-m", "tools.otra_cosa"]
        permitido, forma, motivo = allowlist.evaluar_comando(argv, (), INTERPRETE)
        self.assertFalse(permitido)


class TestFormaNoReconocida(unittest.TestCase):
    def test_comando_sin_forma_reconocida_rechazado(self):
        argv = ["/venv/bin/python", "algo_no_reconocido.txt"]
        permitido, forma, motivo = allowlist.evaluar_comando(argv, ALCANCE, INTERPRETE)
        self.assertFalse(permitido)
        self.assertIsNone(forma)
        self.assertTrue(motivo)


class TestPureza(unittest.TestCase):
    """R9 -- `evaluar_comando` nunca consulta `control.json` ni filesystem
    real: no hay ningún mock de filesystem que hacer porque no hay I/O real
    que mockear. Se verifica la pureza llamando dos veces con los mismos
    argumentos y comparando resultados exactos, incluyendo un caso de cada
    forma."""

    def test_misma_llamada_da_mismo_resultado_script(self):
        argv = ["/venv/bin/python", "scripts/entrenar.py", "--epochs", "10"]
        r1 = allowlist.evaluar_comando(argv, ALCANCE, INTERPRETE)
        r2 = allowlist.evaluar_comando(argv, ALCANCE, INTERPRETE)
        self.assertEqual(r1, r2)

    def test_misma_llamada_da_mismo_resultado_rechazo(self):
        argv = ["/venv/bin/python", "scripts/entrenar.py", "&&", "rm"]
        r1 = allowlist.evaluar_comando(argv, ALCANCE, INTERPRETE)
        r2 = allowlist.evaluar_comando(argv, ALCANCE, INTERPRETE)
        self.assertEqual(r1, r2)

    def test_misma_llamada_da_mismo_resultado_cli_diagnostic_sin_alcance(self):
        argv = ["/venv/bin/python", "tools/ds_guard.py", "status"]
        r1 = allowlist.evaluar_comando(argv, (), INTERPRETE)
        r2 = allowlist.evaluar_comando(argv, (), INTERPRETE)
        self.assertEqual(r1, r2)
        self.assertEqual(r1, (True, "cli_diagnostic", ""))


if __name__ == "__main__":
    unittest.main()

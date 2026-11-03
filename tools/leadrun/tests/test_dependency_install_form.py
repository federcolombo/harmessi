"""Tests de la 5ª forma `dependency_install` de `tools.leadrun` (R24 de
`openspec/changes/20260930-project-extension-and-installer-integration/spec.md`,
M11, resolución 2026-09-30).

Archivo PROPIO de Change 4 -- deliberadamente separado de
`test_core.py`/`test_allowlist.py`/`test_runtime.py` (Change 2, cerrado) para
que esos 3 archivos queden byte-a-byte idénticos a su estado de Change 2
(R24: "los tests existentes... pasan SIN EDITAR NINGUNO" -- hallazgo
bloqueante del reviewer T8, corregido moviendo estos tests acá en vez de
agregarlos a los archivos existentes). Las fixtures de `_BaseRuntimeTest`/
`_request`/`_crudo_ok` están deliberadamente DUPLICADAS de `test_runtime.py`
(no importadas desde ahí) por el mismo motivo: ese archivo no debe ganar
ningún nuevo consumidor ni exportar nada para este Change."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.leadrun import allowlist, core, runtime

INTERPRETE = allowlist.normalizar_interprete("/venv/bin/python")


def _request(argv=None, command_form="script", timeout_seconds=10):
    return core.ExecutionRequest(
        command_form=command_form,
        interpreter="/venv/python",
        argv=tuple(argv or ["/venv/python", "scripts/entrenar.py"]),
        scope=("scripts/entrenar.py",),
        timeout_seconds=timeout_seconds,
    )


def _crudo_ok(**overrides):
    base = {
        "exit_code": 0,
        "duration_seconds": 1.5,
        "stdout_summary": "todo ok",
        "stderr_summary": "",
        "timed_out": False,
    }
    base.update(overrides)
    return base


class _BaseRuntimeTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo_root = Path(self._tmp.name)

        parches = {
            "allowlist": mock.patch.object(runtime, "allowlist"),
            "scripts": mock.patch.object(runtime, "scripts"),
            "notebooks": mock.patch.object(runtime, "notebooks"),
        }
        self.mocks = {}
        for nombre, parche in parches.items():
            self.mocks[nombre] = parche.start()
            self.addCleanup(parche.stop)

        self.mocks["allowlist"].evaluar_comando.return_value = (True, "script", "")
        self.mocks["scripts"].ejecutar_script.return_value = _crudo_ok()
        self.mocks["scripts"].ejecutar_pytest.return_value = _crudo_ok()

        parche_hash = mock.patch(
            "tools.leadrun.runtime.dsguard_core.hash_lf_v1", return_value="hash-fijo"
        )
        self.mock_hash = parche_hash.start()
        self.addCleanup(parche_hash.stop)

        parche_reloj = mock.patch(
            "tools.leadrun.runtime.dsguard_core.ahora_utc", return_value="2026-09-29T00:00:00Z"
        )
        self.mock_reloj = parche_reloj.start()
        self.addCleanup(parche_reloj.stop)

    def _ejecutar(self, **kwargs):
        defaults = dict(
            request=_request(),
            repo_root=self.repo_root,
            executed_by="lead",
            mode="autonomous",
            approval=None,
        )
        defaults.update(kwargs)
        return runtime.ejecutar(**defaults)


class TestDependencyInstallEnExecutionForms(unittest.TestCase):
    """Extraído de `test_core.py` (R24, T3a): 5ª forma aditiva, no rompe las
    4 existentes."""

    def test_dependency_install_en_execution_forms_y_es_valida(self):
        self.assertIn("dependency_install", core.EXECUTION_FORMS)
        self.assertEqual(core.validar_execution_form("dependency_install"), [])


class TestFormaDependencyInstall(unittest.TestCase):
    """Extraído de `test_allowlist.py` (R24, T3a): 5ª forma
    `dependency_install` -- patrón cerrado de 6 tokens
    `-m pip install --no-deps <nombre>==<versión>`."""

    def test_patron_exacto_permitido(self):
        argv = ["/venv/bin/python", "-m", "pip", "install", "--no-deps", "requests==2.31.0"]
        permitido, forma, motivo = allowlist.evaluar_comando(argv, (), INTERPRETE)
        self.assertTrue(permitido)
        self.assertEqual(forma, "dependency_install")
        self.assertEqual(motivo, "")

    def test_menos_de_6_tokens_falta_no_deps_rechazado(self):
        argv = ["/venv/bin/python", "-m", "pip", "install", "requests==2.31.0"]
        permitido, forma, motivo = allowlist.evaluar_comando(argv, (), INTERPRETE)
        self.assertFalse(permitido)
        self.assertIsNone(forma)

    def test_mas_de_6_tokens_flag_extra_rechazado(self):
        argv = ["/venv/bin/python", "-m", "pip", "install", "--no-deps", "requests==2.31.0", "--user"]
        permitido, forma, motivo = allowlist.evaluar_comando(argv, (), INTERPRETE)
        self.assertFalse(permitido)
        self.assertIsNone(forma)

    def test_mas_de_6_tokens_segundo_paquete_rechazado(self):
        argv = ["/venv/bin/python", "-m", "pip", "install", "--no-deps", "requests==2.31.0", "urllib3==2.0.0"]
        permitido, forma, motivo = allowlist.evaluar_comando(argv, (), INTERPRETE)
        self.assertFalse(permitido)
        self.assertIsNone(forma)

    def test_no_deps_reemplazado_por_user_rechazado(self):
        argv = ["/venv/bin/python", "-m", "pip", "install", "--user", "requests==2.31.0"]
        permitido, forma, motivo = allowlist.evaluar_comando(argv, (), INTERPRETE)
        self.assertFalse(permitido)
        self.assertIsNone(forma)

    def test_spec_sin_version_rechazado(self):
        argv = ["/venv/bin/python", "-m", "pip", "install", "--no-deps", "requests"]
        permitido, forma, motivo = allowlist.evaluar_comando(argv, (), INTERPRETE)
        self.assertFalse(permitido)
        self.assertIsNone(forma)

    def test_spec_con_espacio_incrustado_rechazado(self):
        argv = ["/venv/bin/python", "-m", "pip", "install", "--no-deps", "requests== 2.31.0"]
        permitido, forma, motivo = allowlist.evaluar_comando(argv, (), INTERPRETE)
        self.assertFalse(permitido)
        self.assertIsNone(forma)

    def test_interprete_no_autorizado_rechazado_antes_de_forma(self):
        argv = ["/usr/bin/python3", "-m", "pip", "install", "--no-deps", "requests==2.31.0"]
        permitido, forma, motivo = allowlist.evaluar_comando(argv, (), INTERPRETE)
        self.assertFalse(permitido)
        self.assertIsNone(forma)
        self.assertIn("intérprete", motivo)

    def test_metacaracter_prohibido_en_spec_rechazado_antes_de_forma(self):
        argv = ["/venv/bin/python", "-m", "pip", "install", "--no-deps", "requests==1.0;rm -rf /"]
        permitido, forma, motivo = allowlist.evaluar_comando(argv, (), INTERPRETE)
        self.assertFalse(permitido)
        self.assertIsNone(forma)


class TestDependencyInstallSinCodeHash(_BaseRuntimeTest):
    """Extraído de `test_runtime.py` (R24, T3a): `dependency_install` reusa
    el mismo camino que `cli_diagnostic` (`scripts.ejecutar_script`),
    `code_hash=None`."""

    def test_dependency_install_usa_ejecutar_script_y_code_hash_none(self):
        request = _request(
            argv=["/venv/python", "-m", "pip", "install", "--no-deps", "requests==2.31.0"],
            command_form="dependency_install",
        )
        resultado = self._ejecutar(request=request)

        self.assertIsNotNone(resultado["record"])
        self.assertEqual(resultado["record"]["command_form"], "dependency_install")
        self.assertIsNone(resultado["record"]["code_hash"])
        self.assertEqual(resultado["record"]["exit_code"], 0)
        self.assertEqual(resultado["checks"][0]["status"], "PASS")
        self.mocks["scripts"].ejecutar_script.assert_called_once()
        self.mocks["scripts"].ejecutar_pytest.assert_not_called()


if __name__ == "__main__":
    unittest.main()

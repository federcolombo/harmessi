"""Tests de `tools.leadrun.runtime` (T5, R7/R9/R12-R13/R16 de
`openspec/changes/20260929-lead-execution-runtime/spec.md`).

Mockea `allowlist`/`scripts`/`notebooks` en el namespace de `runtime` (mismo
patrón que `test_notebooks.py` usó para `nbmanifest`/`nbexecute`/etc.): no
depende de ejecución real de subprocess/notebooks, eso ya está cubierto por
T3/T4. `dsguard_core.ahora_utc` se congela para que dos llamadas con el mismo
resultado produzcan bytes idénticos (idempotencia, R16)."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.leadrun import core, runtime, scripts as scripts_real


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

        # `hash_lf_v1` toca disco: se congela para no depender de que
        # `request.argv[1]`/el manifest existan de verdad en `self.repo_root`.
        parche_hash = mock.patch(
            "tools.leadrun.runtime.dsguard_core.hash_lf_v1", return_value="hash-fijo"
        )
        self.mock_hash = parche_hash.start()
        self.addCleanup(parche_hash.stop)

        # Congela el timestamp para que dos llamadas con el mismo resultado
        # produzcan los mismos bytes (idempotencia, R16).
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


class TestComandoRechazado(_BaseRuntimeTest):
    def test_allowlist_rechaza_no_ejecuta_nada(self):
        self.mocks["allowlist"].evaluar_comando.return_value = (False, None, "fuera de alcance")

        resultado = self._ejecutar()

        self.assertIsNone(resultado["record"])
        self.assertEqual(len(resultado["checks"]), 1)
        self.assertEqual(resultado["checks"][0]["code"], core.CODE_COMMAND_REJECTED)
        self.assertEqual(resultado["checks"][0]["status"], "FAIL")
        self.mocks["scripts"].ejecutar_script.assert_not_called()
        self.assertFalse((self.repo_root / ".harmessi").exists())


class TestEjecucionScriptExitosa(_BaseRuntimeTest):
    def test_persiste_execution_record_con_campos_correctos(self):
        resultado = self._ejecutar()

        record = resultado["record"]
        self.assertIsNotNone(record)
        self.assertEqual(record["exit_code"], 0)
        self.assertEqual(record["command_form"], "script")
        self.assertEqual(record["executed_by"], "lead")
        self.assertEqual(record["mode"], "autonomous")
        self.assertIsNone(record["approval"])
        self.assertEqual(record["code_hash"], "hash-fijo")
        self.assertEqual(resultado["checks"][0]["status"], "PASS")

        archivo = self.repo_root / ".harmessi" / "executions" / record["execution_id"] / "record.json"
        self.assertTrue(archivo.exists())
        persistido = json.loads(archivo.read_text(encoding="utf-8"))
        self.assertEqual(persistido, record)


class TestCliDiagnosticSinCodeHash(_BaseRuntimeTest):
    def test_cli_diagnostic_usa_ejecutar_script_y_code_hash_none(self):
        request = _request(argv=["/venv/python", "tools/ds_guard.py", "status"], command_form="cli_diagnostic")
        resultado = self._ejecutar(request=request)

        self.assertEqual(resultado["record"]["code_hash"], None)
        self.mocks["scripts"].ejecutar_script.assert_called_once()
        self.mocks["scripts"].ejecutar_pytest.assert_not_called()


class TestRedaccionArgv(_BaseRuntimeTest):
    def test_secreto_en_argv_no_queda_en_claro(self):
        request = _request(argv=["/venv/python", "scripts/entrenar.py", "--token", "ghp_abcdefghijklmnopqrstuvwxyz012345"])

        resultado = self._ejecutar(request=request)

        argv_persistido = resultado["record"]["argv"]
        self.assertNotIn("ghp_abcdefghijklmnopqrstuvwxyz012345", argv_persistido)
        self.assertIn("[REDACTADO]", argv_persistido)


class TestRedaccionStdout(_BaseRuntimeTest):
    def test_secreto_en_stdout_reemplaza_todo_el_resumen(self):
        # El patrón de credencial en `datasources/scan.py:46`
        # (`_RE_PREFIJO_CREDENCIAL = re.compile(r"^(AKIA|ghp_|xox|sk-)")`) está
        # anclado al inicio del VALOR: solo detecta si el resumen entero ES la
        # credencial, no si aparece incrustada en texto libre (p. ej.
        # "token=ghp_..." no matchea). Este fixture simula el caso que sí se
        # detecta: un script que por error imprime únicamente el token.
        self.mocks["scripts"].ejecutar_script.return_value = _crudo_ok(
            stdout_summary="ghp_abcdefghijklmnopqrstuvwxyz012345"
        )

        resultado = self._ejecutar()

        self.assertEqual(
            resultado["record"]["stdout_summary"], "[REDACTADO: posible secreto detectado]"
        )

    def test_secreto_incrustado_en_texto_libre_no_se_detecta_limite_aceptado(self):
        """Límite CONOCIDO y ACEPTADO (no un bug de este Change): el patrón
        de `datasources/scan.py:46`
        (`_RE_PREFIJO_CREDENCIAL = re.compile(r"^(AKIA|ghp_|xox|sk-)")`) está
        anclado al inicio del valor completo. `scan_secrets` evalúa si un
        VALOR ENTERO tiene forma de credencial, no si el texto libre contiene
        una credencial incrustada en cualquier posición. Por eso un resumen
        como "log: token=ghp_... fin" NO dispara la redacción: es el mismo
        criterio best-effort ya declarado y aceptado en Change 1, no algo que
        se resuelva en `runtime.py`."""
        texto = "log: token=ghp_abcdefghijklmnopqrstuvwxyz012345 fin"
        self.mocks["scripts"].ejecutar_script.return_value = _crudo_ok(
            stdout_summary=texto
        )

        resultado = self._ejecutar()

        self.assertEqual(resultado["record"]["stdout_summary"], texto)


class TestTimeout(_BaseRuntimeTest):
    def test_timeout_produce_check_warn(self):
        self.mocks["scripts"].ejecutar_script.return_value = _crudo_ok(
            exit_code=scripts_real.EXIT_CODE_TIMEOUT, timed_out=True
        )

        resultado = self._ejecutar()

        self.assertTrue(resultado["record"]["timed_out"])
        self.assertEqual(resultado["checks"][0]["status"], "WARN")
        self.assertEqual(resultado["checks"][0]["code"], core.CODE_TIMEOUT)


class TestPersistenciaIdempotente(_BaseRuntimeTest):
    def test_misma_ejecucion_dos_veces_mismo_execution_id_sin_fallar(self):
        resultado_1 = self._ejecutar()
        resultado_2 = self._ejecutar()

        self.assertIsNotNone(resultado_1["record"])
        self.assertIsNotNone(resultado_2["record"])
        self.assertEqual(resultado_1["record"]["execution_id"], resultado_2["record"]["execution_id"])
        self.assertEqual(resultado_2["checks"][0]["status"], "PASS")


class TestColisionDeHash(_BaseRuntimeTest):
    def test_contenido_distinto_con_mismo_execution_id_no_sobreescribe(self):
        resultado_1 = self._ejecutar()
        execution_id = resultado_1["record"]["execution_id"]
        archivo = self.repo_root / ".harmessi" / "executions" / execution_id / "record.json"
        contenido_original = archivo.read_bytes()

        # Fuerza una colisión: mismo `execution_id` (mockeado directamente),
        # contenido distinto.
        with mock.patch("tools.leadrun.runtime.leadrun_core.content_sha256", return_value="0" * 64):
            resultado_1_bis = self._ejecutar()
            self.mocks["scripts"].ejecutar_script.return_value = _crudo_ok(stdout_summary="otro resultado")
            resultado_2 = self._ejecutar()

        self.assertIsNotNone(resultado_1_bis["record"])
        self.assertIsNone(resultado_2["record"])
        self.assertEqual(resultado_2["checks"][0]["status"], "FAIL")
        self.assertEqual(resultado_2["checks"][0]["kind"], "technical_error")
        # El archivo original (de la primera corrida real, sin mockear el
        # hash) no fue tocado por la colisión posterior.
        self.assertEqual(archivo.read_bytes(), contenido_original)


class TestUnicoProductor(unittest.TestCase):
    """R13: llamar `scripts.ejecutar_script`/`notebooks.ejecutar_manifest`
    directamente (bypaseando `runtime.ejecutar`) no escribe ningún archivo
    bajo `.harmessi/executions/`."""

    def test_scripts_directo_no_escribe_evidencia(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            fixture = Path(__file__).resolve().parent / "fixtures" / "script_exit_0.py"
            import sys as _sys

            request = core.ExecutionRequest(
                command_form="script",
                interpreter=_sys.executable,
                argv=(_sys.executable, str(fixture)),
                scope=(str(fixture),),
                timeout_seconds=10,
            )
            resultado = scripts_real.ejecutar_script(request, repo_root)

            self.assertEqual(resultado["exit_code"], 0)
            self.assertFalse((repo_root / ".harmessi").exists())


class TestNotebookNormalizaExitCode(_BaseRuntimeTest):
    def test_ok_y_ejecutado_true_da_exit_code_0(self):
        self.mocks["notebooks"].ejecutar_manifest.return_value = {
            "ok": True,
            "findings": [],
            "estado_aprobacion": "vigente",
            "ejecutado": True,
            "resultado_ejecucion": {
                "exit_ok": True,
                "duracion_segundos": 2.0,
                "stdout_resumen": "ok",
                "stderr_resumen": "",
                "timeout_alcanzado": False,
                "posible_proceso_huerfano": False,
                "error_info": None,
            },
            "fsdiff": {"permitidos": [], "fuera_de_contrato": [], "cuarentena": []},
        }
        request = _request(
            argv=[
                "/venv/python",
                "tools/notebook_runner.py",
                "run",
                "--manifest",
                "openspec/changes/x/runs/r.json",
                "--execute",
            ],
            command_form="notebook",
        )

        resultado = self._ejecutar(request=request)

        self.assertEqual(resultado["record"]["exit_code"], 0)
        self.assertEqual(resultado["checks"][0]["status"], "PASS")

    def test_no_ejecutado_da_exit_code_1(self):
        self.mocks["notebooks"].ejecutar_manifest.return_value = {
            "ok": False,
            "findings": [{"codigo": "APROB-AUSENTE", "mensaje": "sin aprobación", "sujeto": "x"}],
            "estado_aprobacion": "ausente",
            "ejecutado": False,
            "resultado_ejecucion": None,
            "fsdiff": None,
        }
        request = _request(
            argv=[
                "/venv/python",
                "tools/notebook_runner.py",
                "run",
                "--manifest",
                "openspec/changes/x/runs/r.json",
                "--execute",
            ],
            command_form="notebook",
        )

        resultado = self._ejecutar(request=request)

        self.assertEqual(resultado["record"]["exit_code"], 1)
        self.assertEqual(resultado["checks"][0]["status"], "FAIL")
        self.assertIn("APROB-AUSENTE", resultado["record"]["stderr_summary"])


if __name__ == "__main__":
    unittest.main()

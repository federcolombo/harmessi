"""Tests de `tools.leadrun.core` (T1, R1, R4-R7 de
`openspec/changes/20260929-lead-execution-runtime/spec.md`)."""
from __future__ import annotations

import ast
import os
import re
import unittest

from tools.leadrun import core


_IMPORTS_PERMITIDOS = {"dataclasses", "typing", "re", "json", "hashlib", "__future__"}


class TestImportsSoloStdlib(unittest.TestCase):
    """R1 -- `core.py` importa SOLO la lista fija de stdlib, sin hermanos ni
    `tools.*`."""

    def test_core_solo_importa_stdlib_permitido(self):
        ruta = os.path.join(os.path.dirname(__file__), "..", "core.py")
        with open(ruta, "r", encoding="utf-8") as f:
            arbol = ast.parse(f.read(), filename="core.py")
        encontrados = set()
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Import):
                for alias in nodo.names:
                    encontrados.add(alias.name.split(".")[0])
            elif isinstance(nodo, ast.ImportFrom):
                if nodo.module is not None:
                    encontrados.add(nodo.module.split(".")[0])
        self.assertLessEqual(
            encontrados, _IMPORTS_PERMITIDOS, f"imports no permitidos: {encontrados - _IMPORTS_PERMITIDOS}"
        )

    def test_core_no_importa_os_pathlib_sys_subprocess_importlib(self):
        ruta = os.path.join(os.path.dirname(__file__), "..", "core.py")
        with open(ruta, "r", encoding="utf-8") as f:
            arbol = ast.parse(f.read(), filename="core.py")
        prohibidos = {"os", "pathlib", "sys", "subprocess", "importlib"}
        encontrados = set()
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Import):
                for alias in nodo.names:
                    encontrados.add(alias.name.split(".")[0])
            elif isinstance(nodo, ast.ImportFrom):
                if nodo.module is not None:
                    encontrados.add(nodo.module.split(".")[0])
        self.assertEqual(encontrados & prohibidos, set())


class TestCodigos(unittest.TestCase):
    """R6 -- catálogo único de códigos `EXEC-*`."""

    def test_codes_tiene_8_codigos(self):
        self.assertEqual(len(core.CODES), 8)

    def test_codes_sin_duplicados(self):
        self.assertEqual(len(core.CODES), len(set(core.CODES)))

    def test_codes_todos_con_patron_exec(self):
        patron = re.compile(r"^EXEC-[A-Z-]+$")
        for codigo in core.CODES:
            self.assertIsNotNone(patron.fullmatch(codigo), f"{codigo!r} no matchea ^EXEC-[A-Z-]+$")


class TestValidarExecutionForm(unittest.TestCase):
    """R4 -- `ExecutionForm`."""

    def test_formas_validas(self):
        for forma in core.EXECUTION_FORMS:
            self.assertEqual(core.validar_execution_form(forma), [])

    def test_forma_invalida(self):
        hallazgos = core.validar_execution_form("shell")
        self.assertEqual(len(hallazgos), 1)
        codigo, motivo = hallazgos[0]
        self.assertEqual(codigo, core.CODE_FORM_INVALID)
        self.assertIn("shell", motivo)

    def test_forma_invalida_none(self):
        hallazgos = core.validar_execution_form(None)
        self.assertEqual(hallazgos[0][0], core.CODE_FORM_INVALID)


class TestContieneMetacaracterProhibido(unittest.TestCase):
    """R5 -- detección de metacaracteres de encadenamiento."""

    def test_cada_metacaracter_prohibido_detectado(self):
        for metacaracter in ("&", ";", "|", "`", "$", "(", ")", "<", ">", "\n"):
            with self.subTest(metacaracter=metacaracter):
                self.assertTrue(core.contiene_metacaracter_prohibido(f"scripts/entrenar.py{metacaracter}rm"))

    def test_texto_limpio_no_detectado(self):
        for texto in ("scripts/entrenar.py", "--flag=valor", "tools/leadrun/tests", "-k", "test_algo"):
            with self.subTest(texto=texto):
                self.assertFalse(core.contiene_metacaracter_prohibido(texto))

    def test_texto_no_str_no_lanza(self):
        self.assertFalse(core.contiene_metacaracter_prohibido(123))


class TestExecutionRequest(unittest.TestCase):
    """R5 -- `ExecutionRequest`."""

    def _dict_valido(self, **overrides):
        base = {
            "command_form": "script",
            "interpreter": "C:/venv/python.exe",
            "argv": ["C:/venv/python.exe", "scripts/entrenar.py"],
            "scope": ("scripts/entrenar.py",),
            "timeout_seconds": 60,
        }
        base.update(overrides)
        return base

    def test_construccion_valida(self):
        req = core.ExecutionRequest(**self._dict_valido())
        self.assertEqual(req.command_form, "script")
        self.assertEqual(req.argv, ("C:/venv/python.exe", "scripts/entrenar.py"))
        self.assertEqual(req.scope, ("scripts/entrenar.py",))

    def test_from_dict_valido(self):
        req = core.ExecutionRequest.from_dict(self._dict_valido())
        self.assertIsInstance(req, core.ExecutionRequest)

    def test_command_form_fuera_de_catalogo(self):
        with self.assertRaises(core.ExecutionError) as ctx:
            core.ExecutionRequest.from_dict(self._dict_valido(command_form="shell"))
        self.assertEqual(ctx.exception.code, core.CODE_FORM_INVALID)

    def test_argv_vacio(self):
        with self.assertRaises(core.ExecutionError) as ctx:
            core.ExecutionRequest.from_dict(self._dict_valido(argv=[]))
        self.assertEqual(ctx.exception.code, core.CODE_REQUEST_INVALID)

    def test_argv_con_metacaracter(self):
        with self.assertRaises(core.ExecutionError) as ctx:
            core.ExecutionRequest.from_dict(
                self._dict_valido(argv=["C:/venv/python.exe", "scripts/entrenar.py", "&&", "rm", "-rf", "/"])
            )
        self.assertEqual(ctx.exception.code, core.CODE_REQUEST_INVALID)

    def test_timeout_seconds_cero(self):
        with self.assertRaises(core.ExecutionError) as ctx:
            core.ExecutionRequest.from_dict(self._dict_valido(timeout_seconds=0))
        self.assertEqual(ctx.exception.code, core.CODE_REQUEST_INVALID)

    def test_timeout_seconds_negativo(self):
        with self.assertRaises(core.ExecutionError):
            core.ExecutionRequest.from_dict(self._dict_valido(timeout_seconds=-5))

    def test_timeout_seconds_no_int(self):
        with self.assertRaises(core.ExecutionError) as ctx:
            core.ExecutionRequest.from_dict(self._dict_valido(timeout_seconds=60.5))
        self.assertEqual(ctx.exception.code, core.CODE_REQUEST_INVALID)

    def test_campo_faltante(self):
        d = self._dict_valido()
        del d["timeout_seconds"]
        with self.assertRaises(core.ExecutionError) as ctx:
            core.ExecutionRequest.from_dict(d)
        self.assertEqual(ctx.exception.code, core.CODE_REQUEST_INVALID)

    def test_round_trip(self):
        req = core.ExecutionRequest.from_dict(self._dict_valido())
        reconstruido = core.ExecutionRequest.from_dict(req.to_dict())
        self.assertEqual(req.to_dict(), reconstruido.to_dict())


class TestExecutionRecord(unittest.TestCase):
    """R7 -- `ExecutionRecord`."""

    def _dict_valido(self, **overrides):
        base = {
            "execution_id": "exec-0001",
            "command_form": "script",
            "argv": ["C:/venv/python.exe", "scripts/entrenar.py"],
            "code_hash": "sha256/lf/v1:abc123",
            "exit_code": 0,
            "duration_seconds": 1.5,
            "stdout_summary": "ok",
            "stderr_summary": "",
            "outputs_hash": None,
            "executed_by": "lead",
            "mode": "autonomous",
            "approval": None,
            "generated_at": "2026-09-29T00:00:00Z",
            "timed_out": False,
        }
        base.update(overrides)
        return base

    def test_construccion_valida(self):
        rec = core.ExecutionRecord.from_dict(self._dict_valido())
        self.assertEqual(rec.execution_id, "exec-0001")

    def test_round_trip_bytes_identicos(self):
        rec = core.ExecutionRecord.from_dict(self._dict_valido())
        d1 = rec.to_dict()
        rec2 = core.ExecutionRecord.from_dict(d1)
        d2 = rec2.to_dict()
        self.assertEqual(core.canonical_json(d1), core.canonical_json(d2))

    def test_code_hash_none_para_cli_diagnostic(self):
        rec = core.ExecutionRecord.from_dict(
            self._dict_valido(command_form="cli_diagnostic", code_hash=None, argv=["C:/venv/python.exe", "tools/ds_guard.py", "status"])
        )
        self.assertIsNone(rec.code_hash)

    def test_code_hash_no_none_en_cli_diagnostic_es_error(self):
        with self.assertRaises(core.ExecutionError) as ctx:
            core.ExecutionRecord.from_dict(
                self._dict_valido(
                    command_form="cli_diagnostic",
                    code_hash="sha256/lf/v1:abc123",
                    argv=["C:/venv/python.exe", "tools/ds_guard.py", "status"],
                )
            )
        self.assertEqual(ctx.exception.code, core.CODE_REQUEST_INVALID)

    def test_approval_none_en_modo_autonomous(self):
        rec = core.ExecutionRecord.from_dict(self._dict_valido(mode="autonomous", approval=None))
        self.assertIsNone(rec.approval)

    def test_approval_no_none_en_autonomous_es_error(self):
        with self.assertRaises(core.ExecutionError) as ctx:
            core.ExecutionRecord.from_dict(
                self._dict_valido(mode="autonomous", approval={"tipo": "politica"})
            )
        self.assertEqual(ctx.exception.code, core.CODE_REQUEST_INVALID)

    def test_approval_dict_permitido_en_supervised(self):
        rec = core.ExecutionRecord.from_dict(
            self._dict_valido(mode="supervised", approval={"tipo": "politica", "vigente": True})
        )
        self.assertEqual(rec.approval, {"tipo": "politica", "vigente": True})

    def test_executed_by_invalido(self):
        with self.assertRaises(core.ExecutionError) as ctx:
            core.ExecutionRecord.from_dict(self._dict_valido(executed_by="robot"))
        self.assertEqual(ctx.exception.code, core.CODE_REQUEST_INVALID)

    def test_mode_invalido(self):
        with self.assertRaises(core.ExecutionError) as ctx:
            core.ExecutionRecord.from_dict(self._dict_valido(mode="turbo"))
        self.assertEqual(ctx.exception.code, core.CODE_REQUEST_INVALID)

    def test_command_form_invalido(self):
        with self.assertRaises(core.ExecutionError) as ctx:
            core.ExecutionRecord.from_dict(self._dict_valido(command_form="shell"))
        self.assertEqual(ctx.exception.code, core.CODE_FORM_INVALID)

    def test_timed_out_true(self):
        rec = core.ExecutionRecord.from_dict(
            self._dict_valido(timed_out=True, exit_code=124)
        )
        self.assertTrue(rec.timed_out)
        self.assertEqual(rec.exit_code, 124)

    def test_campo_faltante_lanza_request_invalid(self):
        d = self._dict_valido()
        del d["generated_at"]
        with self.assertRaises(core.ExecutionError) as ctx:
            core.ExecutionRecord.from_dict(d)
        self.assertEqual(ctx.exception.code, core.CODE_REQUEST_INVALID)


if __name__ == "__main__":
    unittest.main()

"""Tests de `tools/notebook_runner.py` (T3, R11 de
`openspec/changes/20260929-lead-execution-runtime/spec.md`).

Dos frentes:
1. El comando final que compone el CLI matchea `PATRON_COMANDO` de
   `tools/nbrunner/hook_validar_comando.py` SIN modificar ese archivo (se
   importa la regex tal cual, no se reimplementa).
2. `main(argv) -> int` (función testeable in-process, sin depender de un
   intérprete real ni de `subprocess`) devuelve los exit codes correctos:
   `0` éxito, `1` fallo de validación/ejecución, `2` error de uso.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.nbrunner.hook_validar_comando import PATRON_COMANDO  # noqa: E402
import tools.notebook_runner as notebook_runner  # noqa: E402


class TestComandoMatcheaPatron(unittest.TestCase):
    def test_comando_con_dry_run_matchea(self):
        comando = (
            '"/repo/.venv/bin/python" tools/notebook_runner.py run '
            '--manifest openspec/changes/x/runs/r.json --dry-run'
        )
        self.assertIsNotNone(PATRON_COMANDO.match(comando))

    def test_comando_con_execute_matchea(self):
        comando = (
            '"/repo/.venv/bin/python" tools/notebook_runner.py run '
            '--manifest openspec/changes/x/runs/r.json --execute'
        )
        self.assertIsNotNone(PATRON_COMANDO.match(comando))

    def test_comando_sin_flag_de_modo_matchea(self):
        # Default del CLI (sin --dry-run/--execute) también es una forma
        # válida del template -- PATRON_COMANDO la admite (el sufijo de modo
        # es opcional), y el CLI la trata como dry-run (nunca ejecuta por
        # accidente, ver docstring de `main`).
        comando = (
            '"/repo/.venv/bin/python" tools/notebook_runner.py run '
            '--manifest openspec/changes/x/runs/r.json'
        )
        self.assertIsNotNone(PATRON_COMANDO.match(comando))


class TestExitCodes(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = self.enterContext(self._tempdir())
        self.repo_root = Path(self._tmp)
        (self.repo_root / "openspec" / "changes" / "x" / "runs").mkdir(parents=True)
        self.manifest_path = self.repo_root / "openspec" / "changes" / "x" / "runs" / "r.json"
        self.manifest_path.write_text("{}", encoding="utf-8")

        parche_repo_root = mock.patch.object(notebook_runner, "_repo_root", return_value=self.repo_root)
        self.mock_repo_root = parche_repo_root.start()
        self.addCleanup(parche_repo_root.stop)

    def _tempdir(self):
        import tempfile

        class _Ctx:
            def __enter__(self_inner):
                self_inner._td = tempfile.TemporaryDirectory()
                return self_inner._td.name

            def __exit__(self_inner, *exc):
                self_inner._td.cleanup()

        return _Ctx()

    def test_exit_2_argumentos_invalidos(self):
        codigo = notebook_runner.main(["run"])  # falta --manifest
        self.assertEqual(codigo, 2)

    def test_exit_2_manifest_inexistente(self):
        codigo = notebook_runner.main(["run", "--manifest", "openspec/changes/x/runs/no_existe.json"])
        self.assertEqual(codigo, 2)

    def test_exit_0_ok(self):
        with mock.patch.object(
            notebook_runner.leadrun_notebooks,
            "ejecutar_manifest",
            return_value={
                "ok": True,
                "findings": [],
                "estado_aprobacion": "no_verificada",
                "ejecutado": False,
                "resultado_ejecucion": None,
                "fsdiff": None,
            },
        ):
            codigo = notebook_runner.main(
                ["run", "--manifest", "openspec/changes/x/runs/r.json", "--dry-run"]
            )
        self.assertEqual(codigo, 0)

    def test_exit_1_ok_false(self):
        with mock.patch.object(
            notebook_runner.leadrun_notebooks,
            "ejecutar_manifest",
            return_value={
                "ok": False,
                "findings": [{"codigo": "APROB-AUSENTE", "mensaje": "no hay aprobación"}],
                "estado_aprobacion": "ausente",
                "ejecutado": False,
                "resultado_ejecucion": None,
                "fsdiff": None,
            },
        ):
            codigo = notebook_runner.main(
                ["run", "--manifest", "openspec/changes/x/runs/r.json", "--execute"]
            )
        self.assertEqual(codigo, 1)

    def test_control_json_ausente_se_trata_como_sin_aprobaciones(self):
        capturado = {}

        def _fake_ejecutar_manifest(manifest_path, repo_root, control_data, modo):
            capturado["control_data"] = control_data
            return {
                "ok": True,
                "findings": [],
                "estado_aprobacion": "no_verificada",
                "ejecutado": False,
                "resultado_ejecucion": None,
                "fsdiff": None,
            }

        with mock.patch.object(
            notebook_runner.leadrun_notebooks, "ejecutar_manifest", side_effect=_fake_ejecutar_manifest
        ):
            codigo = notebook_runner.main(
                ["run", "--manifest", "openspec/changes/x/runs/r.json", "--dry-run"]
            )
        self.assertEqual(codigo, 0)
        self.assertEqual(capturado["control_data"], {"aprobaciones": []})


if __name__ == "__main__":
    unittest.main()

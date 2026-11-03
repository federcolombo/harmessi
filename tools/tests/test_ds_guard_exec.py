"""Tests de `ds_guard exec script` (v0.8 Change 2 T6,
`20260929-lead-execution-runtime`): composición de aprobación
`execute_project_code` x modo (R12/R14 de spec.md).

Mismo patrón que `test_ds_guard_source_cli.py`: corre `tools/ds_guard.py`
real como subproceso contra un repo git temporal sintético. `ds_guard.py`
inserta `tools/` (el real, `REPO_ORIGEN/tools`) en `sys.path[0]` al
arrancar, así que `leadrun`/`dsguard`/`autonomy`/`nbrunner` se importan sin
necesidad de tocar `PYTHONPATH`."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ORIGEN = Path(__file__).resolve().parents[2]
DS_GUARD = REPO_ORIGEN / "tools" / "ds_guard.py"

sys.path.insert(0, str(REPO_ORIGEN / "tools"))

from dsguard import core  # noqa: E402
from leadrun.allowlist import normalizar_interprete  # noqa: E402

INTERPRETER = normalizar_interprete(sys.executable)


def _crear_repo_git_temporal(prefix: str = "cli_exec_") -> Path:
    repo = Path(tempfile.mkdtemp(prefix=prefix))
    subprocess.run(["git", "init", "-q"], cwd=str(repo), check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(repo), check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(repo), check=True)
    (repo / "README.md").write_text("repo de prueba\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=str(repo), check=True)
    subprocess.run(["git", "commit", "-q", "-m", "inicial"], cwd=str(repo), check=True)
    return repo


def _correr_ds_guard(args: list, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(DS_GUARD), *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _escribir_guardrails(repo: Path, datos: dict) -> Path:
    directorio = repo / ".claude"
    directorio.mkdir(parents=True, exist_ok=True)
    ruta = directorio / "guardrails.json"
    ruta.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
    return ruta


_GUARDRAILS_AUTONOMOUS = {
    "version": 2,
    "autonomy": {
        "version": 2,
        "mode": "autonomous",
        "limits": {"max_sessions": 1, "max_total_minutes": 60},
    },
}

_GUARDRAILS_SUPERVISED = {
    "version": 2,
    "autonomy": {
        "version": 2,
        "mode": "supervised",
    },
}


def _scaffold_change(repo: Path, change_id: str, script_relativo: str) -> Path:
    change_dir = repo / "openspec" / "changes" / change_id
    change_dir.mkdir(parents=True, exist_ok=True)
    (change_dir / "tasks.md").write_text("estado: implementacion\n", encoding="utf-8")
    control = {
        "schema_version": 1,
        "change_id": change_id,
        "modo": "abreviado",
        "origen": "test",
        "creado_utc": core.ahora_utc(),
        "baseline": {"commit": "0" * 40, "rama": "main", "capturado_utc": core.ahora_utc()},
        "alcance": {"rutas_autorizadas": [script_relativo]},
        "aprobaciones": [],
        "transiciones": [],
        "sesiones": [],
    }
    core.escribir_control(change_dir / "control.json", control)
    return change_dir


def _escribir_script_ok(repo: Path, relativo: str) -> Path:
    ruta = repo / relativo
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text("import sys\nsys.exit(0)\n", encoding="utf-8")
    return ruta


class _BaseRepoGit(unittest.TestCase):
    SCRIPT_RELATIVO = "scripts/ok_script.py"
    CHANGE_ID = "20260929-lead-execution-runtime"

    def setUp(self):
        self.repo = _crear_repo_git_temporal()
        self.script_path = _escribir_script_ok(self.repo, self.SCRIPT_RELATIVO)
        self.change_dir = _scaffold_change(self.repo, self.CHANGE_ID, self.SCRIPT_RELATIVO)
        self.control_path = self.change_dir / "control.json"

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def _args_exec_script(self) -> list:
        return [
            "exec",
            "script",
            "--change-id",
            self.CHANGE_ID,
            "--interpreter",
            INTERPRETER,
            "--script",
            self.SCRIPT_RELATIVO,
            "--json",
        ]


class TestExecScriptAutonomous(_BaseRepoGit):
    def test_ejecuta_sin_aprobacion_por_corrida(self):
        _escribir_guardrails(self.repo, _GUARDRAILS_AUTONOMOUS)
        r = _correr_ds_guard(self._args_exec_script(), self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)
        payload = json.loads(r.stdout)
        self.assertIn("execution_id", payload)

        directorio_executions = self.repo / ".harmessi" / "executions"
        self.assertTrue(directorio_executions.is_dir())
        registros = list(directorio_executions.iterdir())
        self.assertEqual(len(registros), 1)
        record = json.loads((registros[0] / "record.json").read_text(encoding="utf-8"))
        self.assertEqual(record["executed_by"], "lead")
        self.assertEqual(record["mode"], "autonomous")
        self.assertIsNone(record["approval"])
        self.assertEqual(record["exit_code"], 0)


class TestExecScriptSupervisedSinAprobacion(_BaseRepoGit):
    def test_bloquea_sin_aprobacion_vigente_con_guardrails_supervised(self):
        _escribir_guardrails(self.repo, _GUARDRAILS_SUPERVISED)
        r = _correr_ds_guard(self._args_exec_script(), self.repo)
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertFalse((self.repo / ".harmessi" / "executions").exists())

    def test_bloquea_sin_aprobacion_vigente_sin_guardrails_en_absoluto(self):
        # Sin .claude/guardrails.json: default supervised (mismo criterio Change 0/1).
        r = _correr_ds_guard(self._args_exec_script(), self.repo)
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertFalse((self.repo / ".harmessi" / "executions").exists())


class TestExecScriptSupervisedConAprobacion(_BaseRepoGit):
    def test_ejecuta_con_aprobacion_humana_vigente_registrada(self):
        _escribir_guardrails(self.repo, _GUARDRAILS_SUPERVISED)

        hash_script = core.hash_lf_v1(self.script_path)
        control = json.loads(self.control_path.read_text(encoding="utf-8"))
        control["aprobaciones"].append(
            {
                "artefacto": self.SCRIPT_RELATIVO,
                "algoritmo": "sha256/lf/v1",
                "hash": hash_script,
                "registrado_utc": core.ahora_utc(),
                "usuario": "federico",
                "fecha_declarada": "2026-09-29",
                "alcance_aprobado": "script de prueba",
                "cita": "n/a",
            }
        )
        core.escribir_control(self.control_path, control)

        r = _correr_ds_guard(self._args_exec_script(), self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)
        payload = json.loads(r.stdout)
        self.assertIn("execution_id", payload)

        directorio_executions = self.repo / ".harmessi" / "executions"
        registros = list(directorio_executions.iterdir())
        self.assertEqual(len(registros), 1)
        record = json.loads((registros[0] / "record.json").read_text(encoding="utf-8"))
        self.assertEqual(record["executed_by"], "human")
        self.assertEqual(record["mode"], "supervised")
        self.assertEqual(record["approval"], {"tipo": "human_manifest_aprobado"})
        self.assertEqual(record["exit_code"], 0)


class TestExecScriptRechazoAllowlist(_BaseRepoGit):
    def test_script_fuera_de_alcance_rechazado_sin_evaluar_aprobacion(self):
        _escribir_guardrails(self.repo, _GUARDRAILS_AUTONOMOUS)
        fuera_de_alcance = _escribir_script_ok(self.repo, "otros/fuera_de_alcance.py")
        args = [
            "exec",
            "script",
            "--change-id",
            self.CHANGE_ID,
            "--interpreter",
            INTERPRETER,
            "--script",
            "otros/fuera_de_alcance.py",
            "--json",
        ]
        r = _correr_ds_guard(args, self.repo)
        self.assertEqual(r.returncode, 2, r.stdout)
        # Nunca llega a ejecutar ni a persistir ningún registro.
        self.assertFalse((self.repo / ".harmessi" / "executions").exists())
        self.assertTrue(fuera_de_alcance.exists())


if __name__ == "__main__":
    unittest.main()

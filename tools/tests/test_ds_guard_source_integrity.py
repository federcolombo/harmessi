"""Tests de integridad detectiva de fuentes externas (M12, T5 de
`20260930-project-extension-and-installer-integration`): fingerprint pre/post
alrededor de una ejecución gobernada (R14-R16) y el helper cooperativo de
output roots (R18).

Mismo patrón que `test_ds_guard_exec.py`: corre `tools/ds_guard.py` real
como subproceso contra un repo git temporal sintético."""
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

CHANGE_ID = "20260929-lead-execution-runtime"

_GUARDRAILS_AUTONOMOUS = {
    "version": 2,
    "autonomy": {
        "version": 2,
        "mode": "autonomous",
        "limits": {"max_sessions": 1, "max_total_minutes": 60},
    },
}


def _crear_repo_git_temporal(prefix: str = "source_integrity_") -> Path:
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


def _escribir_local_overrides(repo: Path, datos: dict) -> Path:
    directorio = repo / ".harmessi"
    directorio.mkdir(parents=True, exist_ok=True)
    ruta = directorio / "local-overrides.json"
    ruta.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
    return ruta


def _escribir_project_config(repo: Path, datos: dict) -> Path:
    directorio = repo / ".harmessi"
    directorio.mkdir(parents=True, exist_ok=True)
    ruta = directorio / "project-config.json"
    ruta.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
    return ruta


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


def _escribir_script(repo: Path, relativo: str, contenido: str) -> Path:
    ruta = repo / relativo
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(contenido, encoding="utf-8")
    return ruta


class _BaseRepoGit(unittest.TestCase):
    SCRIPT_RELATIVO = "scripts/ok_script.py"
    CHANGE_ID = CHANGE_ID

    def setUp(self):
        self.repo = _crear_repo_git_temporal()
        self.change_dir = _scaffold_change(self.repo, self.CHANGE_ID, self.SCRIPT_RELATIVO)
        self.control_path = self.change_dir / "control.json"
        _escribir_guardrails(self.repo, _GUARDRAILS_AUTONOMOUS)

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def _args_exec_script(self, contenido_script: str) -> list:
        _escribir_script(self.repo, self.SCRIPT_RELATIVO, contenido_script)
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


class TestSinFuentesDeclaradasCeroOverhead(_BaseRepoGit):
    """Caso 1: sin ninguna fuente declarada, una ejecución corre exactamente
    igual que antes -- cero overhead, sin fingerprints.json."""

    def test_ejecucion_normal_sin_fingerprints_json(self):
        r = _correr_ds_guard(self._args_exec_script("import sys\nsys.exit(0)\n"), self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)
        payload = json.loads(r.stdout)
        execution_id = payload["execution_id"]
        ruta_fingerprints = self.repo / ".harmessi" / "executions" / execution_id / "fingerprints.json"
        self.assertFalse(ruta_fingerprints.exists())


class TestFuenteDeclaradaSinCambios(_BaseRepoGit):
    """Caso 2: fuente declarada, el script no la toca -- ejecución exitosa,
    sin CheckResult FAIL nuevo, sin fingerprints.json (solo se persiste si
    hubo discrepancia)."""

    def test_sin_cambios_no_hay_fail_ni_fingerprints_json(self):
        externa_dir = Path(tempfile.mkdtemp(prefix="fuente_externa_"))
        self.addCleanup(shutil.rmtree, externa_dir, ignore_errors=True)
        archivo_externo = externa_dir / "dataset.csv"
        archivo_externo.write_text("a,b\n1,2\n", encoding="utf-8")

        _escribir_local_overrides(
            self.repo, {"fuentes_externas": {"externa1": {"path": str(archivo_externo)}}}
        )

        r = _correr_ds_guard(self._args_exec_script("import sys\nsys.exit(0)\n"), self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)
        payload = json.loads(r.stdout)
        execution_id = payload["execution_id"]
        ruta_fingerprints = self.repo / ".harmessi" / "executions" / execution_id / "fingerprints.json"
        self.assertFalse(ruta_fingerprints.exists())
        codigos = [res["code"] for res in payload["resultados"]]
        self.assertNotIn("AUTONOMY-STOP-07", codigos)


class TestFuenteDeclaradaModificadaDuranteLaCorrida(_BaseRepoGit):
    """Caso 3: fuente declarada, el script la modifica de verdad durante la
    corrida -- CheckResult FAIL con el código de data_loss_risk, exit code
    refleja el FAIL, y se persiste fingerprints.json con pre/post/discrepancias."""

    def test_modificacion_durante_la_corrida_produce_fail_y_evidencia(self):
        externa_dir = Path(tempfile.mkdtemp(prefix="fuente_externa_"))
        self.addCleanup(shutil.rmtree, externa_dir, ignore_errors=True)
        archivo_externo = externa_dir / "dataset.csv"
        archivo_externo.write_text("a,b\n1,2\n", encoding="utf-8")

        _escribir_local_overrides(
            self.repo, {"fuentes_externas": {"externa1": {"path": str(archivo_externo)}}}
        )

        ruta_posix = str(archivo_externo).replace("\\", "\\\\")
        script = (
            "import sys\n"
            "import time\n"
            f"with open('{ruta_posix}', 'a', encoding='utf-8') as f:\n"
            "    f.write('3,4\\n')\n"
            "time.sleep(0.05)\n"
            "sys.exit(0)\n"
        )

        r = _correr_ds_guard(self._args_exec_script(script), self.repo)
        # El exit code refleja el FAIL de integridad (checks.exit_code sobre
        # la lista completa, que ahora incluye el FAIL de data_loss_risk).
        self.assertNotEqual(r.returncode, 0, r.stdout)
        payload = json.loads(r.stdout)
        execution_id = payload["execution_id"]

        codigos = [res["code"] for res in payload["resultados"]]
        self.assertIn("AUTONOMY-STOP-07", codigos)

        ruta_fingerprints = self.repo / ".harmessi" / "executions" / execution_id / "fingerprints.json"
        self.assertTrue(ruta_fingerprints.exists())
        evidencia = json.loads(ruta_fingerprints.read_text(encoding="utf-8"))
        self.assertIn("externa1", evidencia["pre"])
        self.assertIn("externa1", evidencia["post"])
        self.assertIn("externa1", evidencia["discrepancias"])
        self.assertNotEqual(evidencia["pre"]["externa1"], evidencia["post"]["externa1"])


class TestFuenteDeclaradaDesaparece(_BaseRepoGit):
    """Caso 4: fuente declarada, el archivo desaparece durante la corrida --
    mismo comportamiento que el caso de modificación (discrepancia vía
    'existe': False)."""

    def test_archivo_borrado_durante_la_corrida_produce_fail(self):
        externa_dir = Path(tempfile.mkdtemp(prefix="fuente_externa_"))
        self.addCleanup(shutil.rmtree, externa_dir, ignore_errors=True)
        archivo_externo = externa_dir / "dataset.csv"
        archivo_externo.write_text("a,b\n1,2\n", encoding="utf-8")

        _escribir_local_overrides(
            self.repo, {"fuentes_externas": {"externa1": {"path": str(archivo_externo)}}}
        )

        ruta_posix = str(archivo_externo).replace("\\", "\\\\")
        script = f"import os\nos.remove('{ruta_posix}')\n"

        r = _correr_ds_guard(self._args_exec_script(script), self.repo)
        self.assertNotEqual(r.returncode, 0, r.stdout)
        payload = json.loads(r.stdout)
        codigos = [res["code"] for res in payload["resultados"]]
        self.assertIn("AUTONOMY-STOP-07", codigos)


class TestMensajeNoAfirmaCausalidad(_BaseRepoGit):
    """Caso 5 (R15): el mensaje de discrepancia nunca afirma que Harmessi
    demostró la modificación."""

    def test_mensaje_no_afirma_causalidad(self):
        externa_dir = Path(tempfile.mkdtemp(prefix="fuente_externa_"))
        self.addCleanup(shutil.rmtree, externa_dir, ignore_errors=True)
        archivo_externo = externa_dir / "dataset.csv"
        archivo_externo.write_text("a,b\n1,2\n", encoding="utf-8")

        _escribir_local_overrides(
            self.repo, {"fuentes_externas": {"externa1": {"path": str(archivo_externo)}}}
        )

        ruta_posix = str(archivo_externo).replace("\\", "\\\\")
        script = f"with open('{ruta_posix}', 'a', encoding='utf-8') as f:\n    f.write('x\\n')\n"

        r = _correr_ds_guard(self._args_exec_script(script), self.repo)
        payload = json.loads(r.stdout)
        mensajes = [res["message"] for res in payload["resultados"] if res["code"] == "AUTONOMY-STOP-07"]
        self.assertEqual(len(mensajes), 1)
        mensaje = mensajes[0].casefold()
        self.assertIn("ventana", mensaje)
        self.assertNotIn("harmessi demuestra", mensaje)
        self.assertNotIn("el agente la modific", mensaje)


class TestResolverOutputRoots(unittest.TestCase):
    """Caso 6: resolver_output_roots -- unión de project-config/local-overrides,
    deduplicada."""

    def setUp(self):
        self.repo = _crear_repo_git_temporal(prefix="output_roots_")

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_sin_ninguna_capa_devuelve_vacio(self):
        r = _correr_ds_guard(["output-roots", "list", "--json"], self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)
        payload = json.loads(r.stdout)
        self.assertEqual(payload["output_roots"], [])

    def test_project_config_declara_dos_rutas(self):
        _escribir_project_config(self.repo, {"output_roots": ["outputs/a", "outputs/b"]})
        r = _correr_ds_guard(["output-roots", "list", "--json"], self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)
        payload = json.loads(r.stdout)
        self.assertEqual(payload["output_roots"], ["outputs/a", "outputs/b"])

    def test_local_override_agrega_una_tercera_sin_duplicar(self):
        _escribir_project_config(self.repo, {"output_roots": ["outputs/a", "outputs/b"]})
        _escribir_local_overrides(self.repo, {"output_roots": ["outputs/b", "outputs/c"]})
        r = _correr_ds_guard(["output-roots", "list", "--json"], self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)
        payload = json.loads(r.stdout)
        self.assertEqual(payload["output_roots"], ["outputs/a", "outputs/b", "outputs/c"])


class TestOutputRootsCliTextoPlano(unittest.TestCase):
    """Caso 7: ds_guard output-roots list (sin --json) imprime una línea por
    root, o un mensaje explícito si no hay ninguno."""

    def setUp(self):
        self.repo = _crear_repo_git_temporal(prefix="output_roots_texto_")

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_sin_roots_mensaje_explicito(self):
        r = _correr_ds_guard(["output-roots", "list"], self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("sin output roots", r.stdout.casefold())

    def test_con_roots_una_linea_por_root(self):
        _escribir_project_config(self.repo, {"output_roots": ["outputs/a"]})
        r = _correr_ds_guard(["output-roots", "list"], self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("outputs/a", r.stdout)


if __name__ == "__main__":
    unittest.main()

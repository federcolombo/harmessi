"""Test end-to-end de `tools.ds_init.cli` en modo `--dry-run`. Crea su propio
repositorio Git temporal (`tempfile.mkdtemp()` + `git init`) como destino;
nunca escribe sobre este repositorio (R14/AC15). Verifica que `--dry-run` no
modifica el árbol de archivos del destino: ni un archivo nuevo, ni uno
modificado."""
from __future__ import annotations

import hashlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from tools.ds_init import control as control_mod
from tools.ds_init import writer
from tools.ds_init.cli import main


def _crear_repo_git_temporal() -> Path:
    ruta = Path(tempfile.mkdtemp(prefix="ds_init_test_cli_"))
    subprocess.run(["git", "init", str(ruta)], capture_output=True, text=True, check=True)
    subprocess.run(["git", "-C", str(ruta), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(ruta), "config", "user.name", "Test"], check=True)
    # Commit inicial para que `git status --porcelain` quede limpio.
    (ruta / "README.md").write_text("repo de prueba\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(ruta), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(ruta), "commit", "-m", "inicial"],
        capture_output=True,
        text=True,
        check=True,
    )
    return ruta


def _snapshot_arbol(ruta: Path) -> dict:
    """Nombres relativos -> hash de contenido, para todo archivo bajo `ruta`
    fuera de `.git/`. Se usa hash de contenido en vez de mtime porque el
    mtime de archivos dentro de `.git/` (p.ej. `.git/hooks/*.sample`) puede
    cambiar por motivos ajenos a la lógica bajo prueba, generando un test
    flaky; comparar contenido es evidencia real de escritura."""
    snapshot = {}
    for archivo in ruta.rglob("*"):
        if not archivo.is_file():
            continue
        relativo = archivo.relative_to(ruta)
        if ".git" in relativo.parts:
            continue
        snapshot[str(relativo)] = hashlib.sha256(archivo.read_bytes()).hexdigest()
    return snapshot


def _git_status_porcelain(ruta: Path) -> str:
    """Salida de `git status --porcelain`: confirma indirectamente que
    tampoco cambió nada dentro de `.git/` que Git considere relevante
    (staged/unstaged/untracked)."""
    resultado = subprocess.run(
        ["git", "-C", str(ruta), "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=True,
    )
    return resultado.stdout


class TestCliDryRun(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_repo_git_temporal()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_dry_run_no_modifica_el_destino(self):
        snapshot_antes = _snapshot_arbol(self.repo)
        status_antes = _git_status_porcelain(self.repo)

        codigo = main(
            [
                "--destino",
                str(self.repo),
                "--nombre",
                "proyecto-de-prueba",
                "--dry-run",
            ]
        )

        self.assertEqual(codigo, 0)

        snapshot_despues = _snapshot_arbol(self.repo)
        self.assertEqual(
            snapshot_antes,
            snapshot_despues,
            "El destino se modificó durante --dry-run",
        )
        self.assertEqual(
            status_antes,
            _git_status_porcelain(self.repo),
            "El estado de git del destino cambió durante --dry-run",
        )

    def test_dry_run_es_el_default_sin_flag(self):
        snapshot_antes = _snapshot_arbol(self.repo)
        status_antes = _git_status_porcelain(self.repo)

        codigo = main(
            [
                "--destino",
                str(self.repo),
                "--nombre",
                "proyecto-de-prueba",
            ]
        )

        self.assertEqual(codigo, 0)
        self.assertEqual(_snapshot_arbol(self.repo), snapshot_antes)
        self.assertEqual(status_antes, _git_status_porcelain(self.repo))


class TestCliExecuteAbortadoControlado(unittest.TestCase):
    """Reliability v0.2.0: si `writer.instalar` levanta
    `InstalacionAbortadaError` durante `--execute`, `main()` debe manejarla
    de forma controlada -- mensaje `[ABORTADO]` por stderr y código de salida
    != 0 -- en vez de dejar propagar un traceback crudo."""

    def setUp(self):
        self.repo = _crear_repo_git_temporal()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_fallo_de_instalacion_produce_mensaje_abortado_y_codigo_no_cero(self):
        with patch(
            "tools.ds_init.cli.writer.instalar",
            side_effect=writer.InstalacionAbortadaError("fallo inyectado por el test"),
        ):
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                codigo = main(
                    [
                        "--destino",
                        str(self.repo),
                        "--nombre",
                        "proyecto-de-prueba",
                        "--execute",
                    ]
                )

        self.assertNotEqual(codigo, 0)
        salida_error = stderr.getvalue()
        self.assertIn("[ABORTADO]", salida_error)
        self.assertIn("fallo inyectado por el test", salida_error)


def _commit_todo(repo: Path, mensaje: str = "commit de prueba") -> None:
    """`preflight.validar_destino` exige working tree limpio antes de
    cualquier `--execute` (incluido `sync`, R12): los tests que encadenan
    varios `--execute` sobre el mismo repo temporal deben confirmar los
    archivos recién instalados antes del siguiente paso, igual que un uso
    real (instalar, revisar/commitear, seguir)."""
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", mensaje],
        capture_output=True,
        text=True,
        check=True,
    )


def _ruta_control(repo: Path) -> Path:
    return repo / control_mod.DIR_CONTROL / control_mod.NOMBRE_ARCHIVO_CONTROL


def _leer_control(repo: Path) -> dict:
    return json.loads(_ruta_control(repo).read_text(encoding="utf-8"))


class TestCliInstallStage(unittest.TestCase):
    """Tests de Change 7 v0.3 (R7 de `spec.md`): `install --stage` en una
    instalación NUEVA."""

    def setUp(self):
        self.repo = _crear_repo_git_temporal()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_sin_stage_instala_experiment_por_default(self):
        codigo = main(
            ["--destino", str(self.repo), "--nombre", "proyecto-de-prueba", "--execute"]
        )
        self.assertEqual(codigo, 0)
        self.assertTrue((self.repo / ".claude" / "agents" / "python-data-engineer.md").exists())
        self.assertFalse(
            (self.repo / ".claude" / "skills" / "lead-data-scientist" / "production-readiness.md").exists()
        )
        control = _leer_control(self.repo)
        self.assertEqual(control["installation_stage"], "experiment")

    def test_stage_discovery_explicito_no_instala_agentes(self):
        codigo = main(
            [
                "--destino",
                str(self.repo),
                "--nombre",
                "proyecto-de-prueba",
                "--stage",
                "discovery",
                "--execute",
            ]
        )
        self.assertEqual(codigo, 0)
        self.assertFalse((self.repo / ".claude" / "agents" / "python-data-engineer.md").exists())
        self.assertFalse(
            (self.repo / ".claude" / "skills" / "lead-data-scientist" / "decision-ledger.md").exists()
        )
        self.assertTrue((self.repo / "tools" / "ds_guard.py").exists())
        control = _leer_control(self.repo)
        self.assertEqual(control["installation_stage"], "discovery")

    def test_stage_production_candidate_rechazado_en_instalacion_nueva(self):
        snapshot_antes = _snapshot_arbol(self.repo)
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as ctx:
                main(
                    [
                        "--destino",
                        str(self.repo),
                        "--nombre",
                        "proyecto-de-prueba",
                        "--stage",
                        "production_candidate",
                        "--execute",
                    ]
                )
        self.assertEqual(ctx.exception.code, 2)
        self.assertEqual(_snapshot_arbol(self.repo), snapshot_antes)
        self.assertFalse((self.repo / ".ds_init").exists())

    def test_stage_production_rechazado_en_instalacion_nueva(self):
        snapshot_antes = _snapshot_arbol(self.repo)
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as ctx:
                main(
                    [
                        "--destino",
                        str(self.repo),
                        "--nombre",
                        "proyecto-de-prueba",
                        "--stage",
                        "production",
                        "--execute",
                    ]
                )
        self.assertEqual(ctx.exception.code, 2)
        self.assertEqual(_snapshot_arbol(self.repo), snapshot_antes)
        self.assertFalse((self.repo / ".ds_init").exists())

    def test_accion_install_explicita_equivale_al_default(self):
        codigo = main(
            ["install", "--destino", str(self.repo), "--nombre", "proyecto-de-prueba", "--execute"]
        )
        self.assertEqual(codigo, 0)
        control = _leer_control(self.repo)
        self.assertEqual(control["installation_stage"], "experiment")


class TestCliSync(unittest.TestCase):
    """Tests de Change 7 v0.3 (R8 de `spec.md`): `sync` incremental sobre un
    destino ya instalado."""

    def setUp(self):
        self.repo = _crear_repo_git_temporal()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def _instalar_discovery(self):
        codigo = main(
            [
                "--destino",
                str(self.repo),
                "--nombre",
                "proyecto-de-prueba",
                "--stage",
                "discovery",
                "--execute",
            ]
        )
        self.assertEqual(codigo, 0)
        _commit_todo(self.repo, "instalar discovery")

    def test_discovery_a_experiment_agrega_delta_sin_tocar_discovery(self):
        self._instalar_discovery()
        hash_ds_guard_antes = hashlib.sha256((self.repo / "tools" / "ds_guard.py").read_bytes()).hexdigest()

        codigo = main(["sync", "--destino", str(self.repo), "--stage", "experiment", "--execute"])
        self.assertEqual(codigo, 0)

        self.assertTrue((self.repo / ".claude" / "agents" / "python-data-engineer.md").exists())
        self.assertTrue((self.repo / ".claude" / "agents" / "data-science-reviewer.md").exists())
        self.assertTrue((self.repo / ".claude" / "agents" / "metodologo.md").exists())
        self.assertTrue((self.repo / ".claude" / "agents" / "notebook-runner.md").exists())
        self.assertTrue(
            (self.repo / ".claude" / "skills" / "lead-data-scientist" / "decision-ledger.md").exists()
        )
        hash_ds_guard_despues = hashlib.sha256((self.repo / "tools" / "ds_guard.py").read_bytes()).hexdigest()
        self.assertEqual(hash_ds_guard_antes, hash_ds_guard_despues)

        control = _leer_control(self.repo)
        self.assertEqual(control["installation_stage"], "experiment")

    def test_sync_deja_archivos_de_control_json_con_el_set_acumulado_completo(self):
        """Hallazgo de revisión, Change 7 v0.3 (riesgo #1 de design.md §5):
        end-to-end, no solo unitario -- confirma que `control.json["archivos"]`
        tras un `sync` incluye TANTO los archivos de la corrida anterior
        (`discovery`) COMO los recién agregados (`experiment`), nunca solo el
        delta de esta corrida."""
        self._instalar_discovery()
        control_antes = _leer_control(self.repo)
        rutas_discovery = {entrada["ruta"] for entrada in control_antes["archivos"]}
        self.assertIn("tools/ds_guard.py", rutas_discovery)
        self.assertNotIn(".claude/agents/python-data-engineer.md", rutas_discovery)

        codigo = main(["sync", "--destino", str(self.repo), "--stage", "experiment", "--execute"])
        self.assertEqual(codigo, 0)

        control_despues = _leer_control(self.repo)
        rutas_despues = {entrada["ruta"] for entrada in control_despues["archivos"]}
        # Los archivos de 'discovery' (corrida anterior) siguen registrados.
        self.assertTrue(rutas_discovery.issubset(rutas_despues))
        # Los archivos nuevos de 'experiment' (delta de esta corrida) también.
        self.assertIn(".claude/agents/python-data-engineer.md", rutas_despues)
        self.assertIn(
            ".claude/skills/lead-data-scientist/decision-ledger.md", rutas_despues
        )
        # Nunca "solo el delta": el set completo crece, no se reemplaza.
        self.assertGreater(len(rutas_despues), len(rutas_discovery))

    def test_experiment_a_production_candidate_agrega_production_readiness(self):
        codigo = main(
            ["--destino", str(self.repo), "--nombre", "proyecto-de-prueba", "--execute"]
        )
        self.assertEqual(codigo, 0)
        _commit_todo(self.repo, "instalar experiment")

        codigo = main(
            ["sync", "--destino", str(self.repo), "--stage", "production_candidate", "--execute"]
        )
        self.assertEqual(codigo, 0)
        self.assertTrue(
            (self.repo / ".claude" / "skills" / "lead-data-scientist" / "production-readiness.md").exists()
        )
        self.assertFalse(
            (self.repo / ".claude" / "skills" / "lead-data-scientist" / "operations.md").exists()
        )
        control = _leer_control(self.repo)
        self.assertEqual(control["installation_stage"], "production_candidate")

    def test_production_candidate_a_production_agrega_operations(self):
        codigo = main(
            ["--destino", str(self.repo), "--nombre", "proyecto-de-prueba", "--execute"]
        )
        self.assertEqual(codigo, 0)
        _commit_todo(self.repo, "instalar experiment")
        codigo = main(
            ["sync", "--destino", str(self.repo), "--stage", "production_candidate", "--execute"]
        )
        self.assertEqual(codigo, 0)
        _commit_todo(self.repo, "sync a production_candidate")

        codigo = main(["sync", "--destino", str(self.repo), "--stage", "production", "--execute"])
        self.assertEqual(codigo, 0)
        self.assertTrue(
            (self.repo / ".claude" / "skills" / "lead-data-scientist" / "operations.md").exists()
        )
        control = _leer_control(self.repo)
        self.assertEqual(control["installation_stage"], "production")

    def test_discovery_a_production_directo_agrega_todo_el_delta(self):
        self._instalar_discovery()

        codigo = main(["sync", "--destino", str(self.repo), "--stage", "production", "--execute"])
        self.assertEqual(codigo, 0)

        for ruta in (
            ".claude/agents/python-data-engineer.md",
            ".claude/agents/data-science-reviewer.md",
            ".claude/agents/metodologo.md",
            ".claude/agents/notebook-runner.md",
            ".claude/skills/lead-data-scientist/decision-ledger.md",
            ".claude/skills/lead-data-scientist/production-readiness.md",
            ".claude/skills/lead-data-scientist/operations.md",
        ):
            self.assertTrue((self.repo / ruta).exists(), f"{ruta} debería existir tras sync directo a production")

        control = _leer_control(self.repo)
        self.assertEqual(control["installation_stage"], "production")

    def test_idempotencia_segunda_corrida_no_cambia_nada(self):
        self._instalar_discovery()
        main(["sync", "--destino", str(self.repo), "--stage", "experiment", "--execute"])
        _commit_todo(self.repo, "sync a experiment")

        snapshot_antes = _snapshot_arbol(self.repo)
        control_antes = _leer_control(self.repo)

        codigo = main(["sync", "--destino", str(self.repo), "--stage", "experiment", "--execute"])
        self.assertEqual(codigo, 0)

        self.assertEqual(_snapshot_arbol(self.repo), snapshot_antes)
        self.assertEqual(_leer_control(self.repo), control_antes)

    def test_target_igual_al_actual_es_noop_sin_escritura(self):
        codigo = main(
            ["--destino", str(self.repo), "--nombre", "proyecto-de-prueba", "--execute"]
        )
        self.assertEqual(codigo, 0)
        _commit_todo(self.repo, "instalar experiment")

        snapshot_antes = _snapshot_arbol(self.repo)
        bytes_control_antes = _ruta_control(self.repo).read_bytes()

        codigo = main(["sync", "--destino", str(self.repo), "--stage", "experiment", "--execute"])
        self.assertEqual(codigo, 0)

        self.assertEqual(_snapshot_arbol(self.repo), snapshot_antes)
        self.assertEqual(_ruta_control(self.repo).read_bytes(), bytes_control_antes)

    def test_target_menor_al_actual_es_noop_sin_escritura(self):
        codigo = main(
            ["--destino", str(self.repo), "--nombre", "proyecto-de-prueba", "--execute"]
        )
        self.assertEqual(codigo, 0)
        _commit_todo(self.repo, "instalar experiment")

        snapshot_antes = _snapshot_arbol(self.repo)
        bytes_control_antes = _ruta_control(self.repo).read_bytes()

        stdout = io.StringIO()
        with redirect_stdout(stdout):
            codigo = main(["sync", "--destino", str(self.repo), "--stage", "discovery", "--execute"])
        self.assertEqual(codigo, 0)
        self.assertIn("nada que hacer", stdout.getvalue().lower())

        self.assertEqual(_snapshot_arbol(self.repo), snapshot_antes)
        self.assertEqual(_ruta_control(self.repo).read_bytes(), bytes_control_antes)

    def test_sync_falla_en_regenerar_control_reporta_error_no_escapa_ni_miente_exito(self):
        """Hallazgo de revisión, Change 7 v0.3: un fallo en el paso posterior
        a `writer.instalar` (`regenerar_control`, que completa `archivos` con
        el set acumulado) ya no debe dejar escapar la excepción sin control
        ni imprimir el mensaje de éxito -- debe reportarse con exit != 0 y un
        mensaje explícito, dejando claro que los archivos SÍ se aplicaron
        pero el registro de control.json puede haber quedado incompleto."""
        self._instalar_discovery()

        with patch(
            "tools.ds_init.cli.control_mod.regenerar_control",
            side_effect=RuntimeError("fallo inyectado por el test"),
        ):
            stderr = io.StringIO()
            stdout = io.StringIO()
            with redirect_stderr(stderr), redirect_stdout(stdout):
                codigo = main(["sync", "--destino", str(self.repo), "--stage", "experiment", "--execute"])

        self.assertNotEqual(codigo, 0)
        self.assertIn("[ABORTADO-PARCIAL]", stderr.getvalue())
        self.assertNotIn("[EXECUTE] Sync completo", stdout.getvalue())
        # Los archivos de 'experiment' SÍ se aplicaron (writer.instalar ya
        # había terminado con éxito antes de que fallara el paso siguiente).
        self.assertTrue((self.repo / ".claude" / "agents" / "python-data-engineer.md").exists())

    def test_sync_sin_control_json_previo_error_claro(self):
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            codigo = main(["sync", "--destino", str(self.repo), "--stage", "experiment", "--execute"])
        self.assertNotEqual(codigo, 0)
        self.assertIn("[ABORTADO]", stderr.getvalue())
        self.assertFalse((self.repo / ".ds_init").exists())
        self.assertFalse((self.repo / ".claude").exists())

    def test_sync_falla_durante_aplicacion_deja_destino_intacto(self):
        self._instalar_discovery()
        snapshot_antes = _snapshot_arbol(self.repo)
        control_antes = _leer_control(self.repo)

        with patch(
            "tools.ds_init.cli.writer.instalar",
            side_effect=writer.InstalacionAbortadaError("fallo inyectado por el test"),
        ):
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                codigo = main(["sync", "--destino", str(self.repo), "--stage", "experiment", "--execute"])

        self.assertNotEqual(codigo, 0)
        self.assertIn("[ABORTADO]", stderr.getvalue())
        self.assertEqual(_snapshot_arbol(self.repo), snapshot_antes)
        self.assertEqual(_leer_control(self.repo), control_antes)

    def test_sync_dry_run_no_escribe_nada(self):
        self._instalar_discovery()
        snapshot_antes = _snapshot_arbol(self.repo)

        codigo = main(["sync", "--destino", str(self.repo), "--stage", "experiment", "--dry-run"])
        self.assertEqual(codigo, 0)
        self.assertEqual(_snapshot_arbol(self.repo), snapshot_antes)

    def test_sync_sin_flag_execute_es_dry_run_por_default(self):
        self._instalar_discovery()
        snapshot_antes = _snapshot_arbol(self.repo)

        codigo = main(["sync", "--destino", str(self.repo), "--stage", "experiment"])
        self.assertEqual(codigo, 0)
        self.assertEqual(_snapshot_arbol(self.repo), snapshot_antes)

    def test_sync_sin_stage_error_claro(self):
        self._instalar_discovery()
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as ctx:
                main(["sync", "--destino", str(self.repo), "--execute"])
        self.assertEqual(ctx.exception.code, 2)


class TestCliSyncProtegeArchivosDelUsuario(unittest.TestCase):
    """Tests de Change 7 v0.3 (R12 de `spec.md`): protección de archivos del
    usuario durante `sync`, reusando `planner._accion_para_entrada` sin
    duplicar lógica."""

    def setUp(self):
        self.repo = _crear_repo_git_temporal()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_archivo_experiment_editado_por_usuario_no_se_sobrescribe_en_sync(self):
        codigo = main(
            [
                "--destino",
                str(self.repo),
                "--nombre",
                "proyecto-de-prueba",
                "--stage",
                "discovery",
                "--execute",
            ]
        )
        self.assertEqual(codigo, 0)

        ruta_agente = self.repo / ".claude" / "agents" / "python-data-engineer.md"
        ruta_agente.parent.mkdir(parents=True, exist_ok=True)
        contenido_usuario = "---\nname: python-data-engineer\n---\n# editado a mano por el usuario\n"
        ruta_agente.write_text(contenido_usuario, encoding="utf-8")

        # `sync` exige working tree limpio (mismo preflight que cualquier
        # `--execute`) -- confirmamos el archivo editado antes de sincronizar.
        subprocess.run(["git", "-C", str(self.repo), "add", "."], check=True)
        subprocess.run(
            ["git", "-C", str(self.repo), "commit", "-m", "edicion manual del agente"],
            capture_output=True,
            text=True,
            check=True,
        )

        codigo = main(["sync", "--destino", str(self.repo), "--stage", "experiment", "--execute"])
        self.assertEqual(codigo, 0)

        self.assertEqual(ruta_agente.read_text(encoding="utf-8"), contenido_usuario)

    def test_sync_nunca_borra_nada(self):
        codigo = main(
            ["--destino", str(self.repo), "--nombre", "proyecto-de-prueba", "--execute"]
        )
        self.assertEqual(codigo, 0)
        _commit_todo(self.repo, "instalar experiment")
        archivos_antes = {
            str(p.relative_to(self.repo))
            for p in self.repo.rglob("*")
            if p.is_file() and ".git" not in p.relative_to(self.repo).parts
        }

        codigo = main(["sync", "--destino", str(self.repo), "--stage", "production", "--execute"])
        self.assertEqual(codigo, 0)

        archivos_despues = {
            str(p.relative_to(self.repo))
            for p in self.repo.rglob("*")
            if p.is_file() and ".git" not in p.relative_to(self.repo).parts
        }
        # Ningún archivo presente antes desapareció (sync solo agrega).
        self.assertTrue(archivos_antes.issubset(archivos_despues))


class TestCliSyncLegacy(unittest.TestCase):
    """Tests de Change 7 v0.3 (R6/R8 de `spec.md`): `sync` sobre un destino
    "legacy" (control.json sin `installation_stage`, como cualquier
    instalación anterior a este change)."""

    def setUp(self):
        self.repo = _crear_repo_git_temporal()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def _instalar_legacy_sin_experiment(self):
        # Instala solo 'discovery' (sin agentes/decision-ledger.md -- la
        # señal que usa `legacy.inferir_installation_stage`) y despoja
        # `installation_stage` del control.json resultante, simulando una
        # instalación anterior a Change 7 podada manualmente.
        codigo = main(
            ["--destino", str(self.repo), "--nombre", "proyecto-de-prueba", "--stage", "discovery", "--execute"]
        )
        self.assertEqual(codigo, 0)
        ruta_control = _ruta_control(self.repo)
        control = json.loads(ruta_control.read_text(encoding="utf-8"))
        control.pop("installation_stage", None)
        ruta_control.write_text(json.dumps(control, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.repo), "add", "."], check=True)
        subprocess.run(
            ["git", "-C", str(self.repo), "commit", "-m", "simular legacy sin installation_stage"],
            capture_output=True,
            text=True,
            check=True,
        )

    def test_sync_sobre_legacy_usa_inferencia_discovery_como_base_y_deja_installation_stage_explicito(self):
        # Sin `installation_stage` y sin los archivos de 'experiment' ->
        # `legacy.inferir_installation_stage` da 'discovery' (piso
        # conservador) -- el sync, tomando esa base, agrega el delta
        # acumulado completo hasta 'production_candidate' (experiment + el
        # propio de production_candidate) en una sola corrida.
        self._instalar_legacy_sin_experiment()
        self.assertNotIn("installation_stage", _leer_control(self.repo))
        self.assertFalse((self.repo / ".claude" / "agents" / "python-data-engineer.md").exists())

        codigo = main(
            ["sync", "--destino", str(self.repo), "--stage", "production_candidate", "--execute"]
        )
        self.assertEqual(codigo, 0)

        control = _leer_control(self.repo)
        self.assertEqual(control["installation_stage"], "production_candidate")
        self.assertTrue((self.repo / ".claude" / "agents" / "python-data-engineer.md").exists())
        self.assertTrue(
            (self.repo / ".claude" / "skills" / "lead-data-scientist" / "production-readiness.md").exists()
        )

    def test_sync_sobre_legacy_con_experiment_completo_infiere_production_y_es_noop(self):
        # Legacy real (como este propio repo): sin `installation_stage`, con
        # los 5 archivos de 'experiment' presentes -> se infiere 'production'
        # (máximo compatible, R6) -- sync a cualquier target <= production es
        # no-op explícito, sin escribir nada.
        codigo = main(
            ["--destino", str(self.repo), "--nombre", "proyecto-de-prueba", "--stage", "experiment", "--execute"]
        )
        self.assertEqual(codigo, 0)
        ruta_control = _ruta_control(self.repo)
        control = json.loads(ruta_control.read_text(encoding="utf-8"))
        control.pop("installation_stage", None)
        ruta_control.write_text(json.dumps(control, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.repo), "add", "."], check=True)
        subprocess.run(
            ["git", "-C", str(self.repo), "commit", "-m", "simular legacy con experiment completo"],
            capture_output=True,
            text=True,
            check=True,
        )

        snapshot_antes = _snapshot_arbol(self.repo)
        codigo = main(["sync", "--destino", str(self.repo), "--stage", "production", "--execute"])
        self.assertEqual(codigo, 0)
        self.assertEqual(_snapshot_arbol(self.repo), snapshot_antes)


class TestCliScratchInstallsImportanSinError(unittest.TestCase):
    """Tests de Change 7 v0.3 (sección "Scratch installs" de `spec.md`):
    instalaciones reales (`--execute`) en repos Git temporales, para cada
    stage, confirmando que el runtime instalado (`tools/dsguard/`,
    `tools/nbrunner/`) importa sin `ImportError` -- el código Python NUNCA se
    subdivide por stage (`design.md` §1), así que debe estar completo y
    funcional incluso en una instalación mínima `discovery`."""

    def setUp(self):
        self.repo = _crear_repo_git_temporal()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def _assert_importa_sin_error(self):
        tools_dir = self.repo / "tools"
        codigo = (
            f"import sys; sys.path.insert(0, {str(tools_dir)!r}); "
            "import dsguard.core; import nbrunner.core; import ds_guard"
        )
        resultado = subprocess.run(
            [sys.executable, "-c", codigo], capture_output=True, text=True
        )
        self.assertEqual(resultado.returncode, 0, resultado.stderr)

    def test_scratch_discovery_importa_runtime_completo(self):
        codigo = main(
            [
                "--destino",
                str(self.repo),
                "--nombre",
                "proyecto-de-prueba",
                "--stage",
                "discovery",
                "--execute",
            ]
        )
        self.assertEqual(codigo, 0)
        self._assert_importa_sin_error()

    def test_scratch_experiment_default_importa_runtime_completo(self):
        codigo = main(
            ["--destino", str(self.repo), "--nombre", "proyecto-de-prueba", "--execute"]
        )
        self.assertEqual(codigo, 0)
        self._assert_importa_sin_error()

    def test_incremental_discovery_a_experiment_via_sync_importa_runtime_completo(self):
        codigo = main(
            [
                "--destino",
                str(self.repo),
                "--nombre",
                "proyecto-de-prueba",
                "--stage",
                "discovery",
                "--execute",
            ]
        )
        self.assertEqual(codigo, 0)
        _commit_todo(self.repo, "instalar discovery")

        codigo = main(["sync", "--destino", str(self.repo), "--stage", "experiment", "--execute"])
        self.assertEqual(codigo, 0)
        self._assert_importa_sin_error()

    def test_incremental_experiment_a_production_candidate_fixtureable_sin_promote_real(self):
        """El sync no depende de `project_stage`/`readiness` real (R9): se
        puede fixturear sin simular `promote` -- ejes independientes."""
        codigo = main(
            ["--destino", str(self.repo), "--nombre", "proyecto-de-prueba", "--execute"]
        )
        self.assertEqual(codigo, 0)
        _commit_todo(self.repo, "instalar experiment")

        codigo = main(
            ["sync", "--destino", str(self.repo), "--stage", "production_candidate", "--execute"]
        )
        self.assertEqual(codigo, 0)
        self.assertFalse((self.repo / ".harmessi" / "project.json").exists())
        self.assertTrue(
            (self.repo / ".claude" / "skills" / "lead-data-scientist" / "production-readiness.md").exists()
        )
        self._assert_importa_sin_error()


if __name__ == "__main__":
    unittest.main()

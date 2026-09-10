"""Tests de `tools.harmessi.doctor` (Bloque 2, reliability v0.2.0). Usa
repositorios Git temporales propios (nunca este repositorio, mismo criterio
R14/AC15 que los tests de `tools.ds_init`); varios tests instalan el harness
de verdad con `tools.ds_init.writer.instalar` para diagnosticar una
instalación real, no un fixture artificial."""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from tools import launcher_common
from tools.ds_init import writer as ds_init_writer
from tools.ds_init.planner import construir_plan
from tools.ds_init.version import HARNESS_VERSION
from tools.harmessi import doctor as doctor_mod

PERFIL = "python-jupyter-data"

# Referencia real, capturada antes de parchear `tools.harmessi.doctor.
# subprocess.run` -- doctor usa ese mismo `subprocess.run` tanto para sus
# checks de `git` (que deben correr de verdad contra el repo temporal) como
# para el check RUNTIME-INTERPRETE (el único que se simula en los tests de
# "instalación completa exitosa"). Mismo patrón que
# `tools/tests/test_launcher_common.py`.
_SUBPROCESS_RUN_REAL = subprocess.run


def _mock_solo_interprete(returncode: int = 0, stderr: str = ""):
    def _side_effect(cmd, **kwargs):
        if cmd[0] == "git":
            return _SUBPROCESS_RUN_REAL(cmd, **kwargs)
        return subprocess.CompletedProcess(args=cmd, returncode=returncode, stdout="", stderr=stderr)

    return _side_effect


def _crear_repo_git_temporal(prefix: str = "harmessi_doctor_test_") -> Path:
    ruta = Path(tempfile.mkdtemp(prefix=prefix))
    subprocess.run(["git", "init", str(ruta)], capture_output=True, text=True, check=True)
    subprocess.run(["git", "-C", str(ruta), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(ruta), "config", "user.name", "Test"], check=True)
    (ruta / "README.md").write_text("repo de prueba\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(ruta), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(ruta), "commit", "-m", "inicial"], capture_output=True, text=True, check=True
    )
    return ruta


def _config_base(destino: Path, nombre: str = "proyecto-de-prueba") -> dict:
    return {
        "perfil": PERFIL,
        "nombre": nombre,
        "notebooks_dir": "notebooks",
        "venv_dir": ".venv",
        "destino": str(destino),
        "integrar_claude": False,
        "placeholders": {
            "NOMBRE_PROYECTO": nombre,
            "NOTEBOOKS_DIR": "notebooks",
            "VENV_DIR": ".venv",
            "FECHA_INSTALACION": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "HARNESS_VERSION": HARNESS_VERSION,
            "RUTAS_PROHIBIDAS_JSON": "[]",
        },
    }


def _instalar_harness_real(destino: Path):
    config = _config_base(destino)
    plan = construir_plan(PERFIL, destino, config)
    return ds_init_writer.instalar(plan, destino, config)


def _crear_interprete_falso(destino: Path) -> Path:
    interprete = launcher_common.ruta_interprete_venv(destino, ".venv")
    interprete.parent.mkdir(parents=True, exist_ok=True)
    interprete.write_text("", encoding="utf-8")
    return interprete


def _niveles(resultados, codigo=None):
    if codigo is None:
        return {r.nivel for r in resultados}
    return {r.nivel for r in resultados if r.codigo == codigo}


class TestChecksCore(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_repo_git_temporal()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_version_python_ok(self):
        resultados = doctor_mod._check_version_python()
        self.assertEqual(resultados[0].nivel, doctor_mod.NIVEL_OK)

    def test_git_disponible_ok(self):
        resultados = doctor_mod._check_git_disponible()
        self.assertEqual(resultados[0].nivel, doctor_mod.NIVEL_OK)

    def test_repo_git_valido_ok(self):
        resultados = doctor_mod._check_repo_git_valido(self.repo)
        self.assertEqual(resultados[0].nivel, doctor_mod.NIVEL_OK)

    def test_repo_git_invalido_error(self):
        no_git = Path(tempfile.mkdtemp(prefix="harmessi_doctor_test_no_git_"))
        try:
            resultados = doctor_mod._check_repo_git_valido(no_git)
            self.assertEqual(resultados[0].nivel, doctor_mod.NIVEL_ERROR)
        finally:
            shutil.rmtree(no_git, ignore_errors=True)

    def test_working_tree_limpio_ok(self):
        resultados = doctor_mod._check_working_tree(self.repo)
        self.assertEqual(resultados[0].nivel, doctor_mod.NIVEL_OK)

    def test_working_tree_sucio_warn(self):
        (self.repo / "archivo_sucio.txt").write_text("x", encoding="utf-8")
        resultados = doctor_mod._check_working_tree(self.repo)
        self.assertEqual(resultados[0].nivel, doctor_mod.NIVEL_WARN)

    def test_venv_faltante_warn(self):
        resultados = doctor_mod._check_venv(self.repo)
        self.assertEqual(resultados[0].nivel, doctor_mod.NIVEL_WARN)

    def test_venv_presente_ok(self):
        _crear_interprete_falso(self.repo)
        resultados = doctor_mod._check_venv(self.repo)
        self.assertEqual(resultados[0].nivel, doctor_mod.NIVEL_OK)

    def test_permisos_ok(self):
        resultados = doctor_mod._check_permisos(self.repo)
        self.assertEqual(resultados[0].nivel, doctor_mod.NIVEL_OK)

    def test_permisos_error_si_falla_escritura(self):
        with patch("tools.harmessi.doctor._probar_escritura", side_effect=OSError("sin permiso")):
            resultados = doctor_mod._check_permisos(self.repo)
        self.assertEqual(resultados[0].nivel, doctor_mod.NIVEL_ERROR)


class TestChecksHarmessiInstalacionReal(unittest.TestCase):
    """Comparten fixture: instalación real completa vía `writer.instalar`,
    para diagnosticar exactamente lo que `ds_init` produce hoy."""

    def setUp(self):
        self.repo = _crear_repo_git_temporal()
        self.resultado_instalacion = _instalar_harness_real(self.repo)

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_control_json_ok(self):
        control_data, resultados = doctor_mod._leer_control_json(self.repo)
        self.assertIsNotNone(control_data)
        self.assertEqual(resultados[0].nivel, doctor_mod.NIVEL_OK)

    def test_archivos_administrados_ok(self):
        control_data, _ = doctor_mod._leer_control_json(self.repo)
        resultados = doctor_mod._check_archivos_administrados(self.repo, control_data)
        self.assertEqual(_niveles(resultados), {doctor_mod.NIVEL_OK})

    def test_archivos_administrados_error_si_falta_critico(self):
        (self.repo / ".claude" / "settings.json").unlink()
        control_data, _ = doctor_mod._leer_control_json(self.repo)
        resultados = doctor_mod._check_archivos_administrados(self.repo, control_data)
        self.assertIn(doctor_mod.NIVEL_ERROR, _niveles(resultados))

    def test_archivos_administrados_warn_si_falta_no_critico(self):
        (self.repo / ".claude" / "skills" / "lead-data-scientist" / "templates" / "tasks.md").unlink()
        control_data, _ = doctor_mod._leer_control_json(self.repo)
        resultados = doctor_mod._check_archivos_administrados(self.repo, control_data)
        self.assertIn(doctor_mod.NIVEL_WARN, _niveles(resultados))
        self.assertNotIn(doctor_mod.NIVEL_ERROR, _niveles(resultados))

    def test_archivos_administrados_warn_sin_control_json(self):
        resultados = doctor_mod._check_archivos_administrados(self.repo, None)
        self.assertEqual(resultados[0].nivel, doctor_mod.NIVEL_WARN)

    def test_drift_ok_sin_cambios(self):
        control_data, _ = doctor_mod._leer_control_json(self.repo)
        resultados = doctor_mod._check_hashes_drift(self.repo, control_data)
        self.assertEqual(_niveles(resultados), {doctor_mod.NIVEL_OK})

    def test_drift_warn_si_archivo_modificado(self):
        ruta = self.repo / "tools" / "ds_guard.py"
        ruta.write_text(ruta.read_text(encoding="utf-8") + "\n# modificado a mano\n", encoding="utf-8")
        control_data, _ = doctor_mod._leer_control_json(self.repo)
        resultados = doctor_mod._check_hashes_drift(self.repo, control_data)
        self.assertIn(doctor_mod.NIVEL_WARN, _niveles(resultados))

    def test_drift_error_si_archivo_administrado_falta(self):
        (self.repo / "tools" / "ds_guard.py").unlink()
        control_data, _ = doctor_mod._leer_control_json(self.repo)
        resultados = doctor_mod._check_hashes_drift(self.repo, control_data)
        self.assertIn(doctor_mod.NIVEL_ERROR, _niveles(resultados))

    def test_agents_ok(self):
        resultados = doctor_mod._check_agents(self.repo)
        self.assertEqual(_niveles(resultados), {doctor_mod.NIVEL_OK})

    def test_agents_error_si_falta(self):
        (self.repo / ".claude" / "agents" / "notebook-runner.md").unlink()
        resultados = doctor_mod._check_agents(self.repo)
        self.assertIn(doctor_mod.NIVEL_ERROR, _niveles(resultados))

    def test_skill_ok(self):
        resultados = doctor_mod._check_skill_lead_data_scientist(self.repo)
        self.assertEqual(resultados[0].nivel, doctor_mod.NIVEL_OK)

    def test_skill_warn_si_falta_archivo(self):
        (self.repo / ".claude" / "skills" / "lead-data-scientist" / "verificador.md").unlink()
        resultados = doctor_mod._check_skill_lead_data_scientist(self.repo)
        self.assertEqual(resultados[0].nivel, doctor_mod.NIVEL_WARN)

    def test_settings_ok(self):
        _, resultados = doctor_mod._check_settings(self.repo)
        self.assertEqual(resultados[0].nivel, doctor_mod.NIVEL_OK)

    def test_settings_error_si_falta(self):
        (self.repo / ".claude" / "settings.json").unlink()
        _, resultados = doctor_mod._check_settings(self.repo)
        self.assertEqual(resultados[0].nivel, doctor_mod.NIVEL_ERROR)

    def test_settings_error_si_json_invalido(self):
        (self.repo / ".claude" / "settings.json").write_text("{ no es json", encoding="utf-8")
        _, resultados = doctor_mod._check_settings(self.repo)
        self.assertEqual(resultados[0].nivel, doctor_mod.NIVEL_ERROR)

    def test_hooks_ok(self):
        settings_data, _ = doctor_mod._check_settings(self.repo)
        resultados = doctor_mod._check_hooks(self.repo, settings_data)
        self.assertEqual(_niveles(resultados), {doctor_mod.NIVEL_OK})

    def test_hooks_error_si_falta_matcher(self):
        ruta_settings = self.repo / ".claude" / "settings.json"
        datos = json.loads(ruta_settings.read_text(encoding="utf-8"))
        datos["hooks"]["PreToolUse"] = [
            h for h in datos["hooks"]["PreToolUse"] if h.get("matcher") != "Bash"
        ]
        ruta_settings.write_text(json.dumps(datos), encoding="utf-8")
        settings_data, _ = doctor_mod._check_settings(self.repo)
        resultados = doctor_mod._check_hooks(self.repo, settings_data)
        self.assertIn(doctor_mod.NIVEL_ERROR, _niveles(resultados))

    def test_coherencia_version_ok(self):
        control_data, _ = doctor_mod._leer_control_json(self.repo)
        resultados = doctor_mod._check_coherencia_version(control_data)
        self.assertEqual(resultados[0].nivel, doctor_mod.NIVEL_OK)

    def test_coherencia_version_warn_si_distinta(self):
        control_data, _ = doctor_mod._leer_control_json(self.repo)
        control_data["harness_version"] = "0.0.1-otra"
        resultados = doctor_mod._check_coherencia_version(control_data)
        self.assertEqual(resultados[0].nivel, doctor_mod.NIVEL_WARN)


class TestChecksRuntimeInstalacionReal(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_repo_git_temporal()
        _instalar_harness_real(self.repo)

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_launchers_existen_ok(self):
        resultados = doctor_mod._check_launchers_existen(self.repo)
        self.assertEqual(_niveles(resultados), {doctor_mod.NIVEL_OK})

    def test_launchers_faltantes_error(self):
        (self.repo / "tools" / "nbrunner" / "hook_launcher.py").unlink()
        resultados = doctor_mod._check_launchers_existen(self.repo)
        self.assertIn(doctor_mod.NIVEL_ERROR, _niveles(resultados))

    def test_interprete_ejecuta_hooks_sin_interprete_error(self):
        resultados = doctor_mod._check_interprete_ejecuta_hooks(self.repo)
        self.assertEqual(resultados[0].nivel, doctor_mod.NIVEL_ERROR)

    def test_interprete_ejecuta_hooks_ok_mockeado(self):
        _crear_interprete_falso(self.repo)
        with patch("tools.harmessi.doctor.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stderr="")
            resultados = doctor_mod._check_interprete_ejecuta_hooks(self.repo)
        self.assertEqual(resultados[0].nivel, doctor_mod.NIVEL_OK)

    def test_interprete_ejecuta_hooks_error_si_falla_import(self):
        _crear_interprete_falso(self.repo)
        with patch("tools.harmessi.doctor.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=1, stderr="ModuleNotFoundError"
            )
            resultados = doctor_mod._check_interprete_ejecuta_hooks(self.repo)
        self.assertEqual(resultados[0].nivel, doctor_mod.NIVEL_ERROR)

    def test_hooks_configurados_existen_ok(self):
        settings_data, _ = doctor_mod._check_settings(self.repo)
        resultados = doctor_mod._check_hooks_configurados_existen(self.repo, settings_data)
        self.assertTrue(resultados)
        self.assertEqual(_niveles(resultados), {doctor_mod.NIVEL_OK})

    def test_hooks_configurados_existen_error_si_falta_script(self):
        (self.repo / "tools" / "nbrunner" / "hook_launcher.py").unlink()
        settings_data, _ = doctor_mod._check_settings(self.repo)
        resultados = doctor_mod._check_hooks_configurados_existen(self.repo, settings_data)
        self.assertIn(doctor_mod.NIVEL_ERROR, _niveles(resultados))

    def test_dependencia_shell_ok_sin_bash(self):
        """El settings.json que instala esta versión de Harmessi ya no usa
        `bash "..."`: el objetivo cross-platform del Bloque 2."""
        settings_data, _ = doctor_mod._check_settings(self.repo)
        resultados = doctor_mod._check_dependencia_shell(settings_data)
        self.assertEqual(_niveles(resultados), {doctor_mod.NIVEL_OK})

    def test_dependencia_shell_error_si_bash_no_disponible(self):
        ruta_settings = self.repo / ".claude" / "settings.json"
        datos = json.loads(ruta_settings.read_text(encoding="utf-8"))
        datos["hooks"]["PreToolUse"][0]["hooks"][0]["command"] = 'bash "${CLAUDE_PROJECT_DIR}/hook.sh"'
        with patch("tools.harmessi.doctor.shutil.which", return_value=None):
            resultados = doctor_mod._check_dependencia_shell(datos)
        self.assertIn(doctor_mod.NIVEL_ERROR, _niveles(resultados))

    def test_dependencia_shell_warn_si_bash_disponible(self):
        ruta_settings = self.repo / ".claude" / "settings.json"
        datos = json.loads(ruta_settings.read_text(encoding="utf-8"))
        datos["hooks"]["PreToolUse"][0]["hooks"][0]["command"] = 'bash "${CLAUDE_PROJECT_DIR}/hook.sh"'
        with patch("tools.harmessi.doctor.shutil.which", return_value="/usr/bin/bash"):
            resultados = doctor_mod._check_dependencia_shell(datos)
        niveles_bash = {
            r.nivel for r in resultados if "bash" in r.mensaje.lower() and r.nivel != doctor_mod.NIVEL_OK
        }
        self.assertIn(doctor_mod.NIVEL_WARN, niveles_bash)


class TestEjecutarIntegracion(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_repo_git_temporal()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_instalacion_sin_venv_tiene_solo_el_gap_de_interprete(self):
        """`ds_init` no crea el `.venv` -- eso queda para el usuario. Sin él,
        el único `ERROR` esperable es RUNTIME-INTERPRETE (nada puede
        ejecutarse sin intérprete); todo lo demás debe seguir en OK."""
        _instalar_harness_real(self.repo)
        resultados, codigo = doctor_mod.ejecutar(self.repo)
        codigos_error = {r.codigo for r in resultados if r.nivel == doctor_mod.NIVEL_ERROR}
        self.assertEqual(codigos_error, {"RUNTIME-INTERPRETE"})
        self.assertEqual(codigo, 1)

    def test_instalacion_completa_con_venv_da_exit_0(self):
        _instalar_harness_real(self.repo)
        _crear_interprete_falso(self.repo)
        with patch("tools.harmessi.doctor.subprocess.run", side_effect=_mock_solo_interprete(0, "")):
            resultados, codigo = doctor_mod.ejecutar(self.repo)
        self.assertEqual(codigo, 0)
        self.assertNotIn(doctor_mod.NIVEL_ERROR, _niveles(resultados))

    def test_falta_settings_json_da_exit_1(self):
        _instalar_harness_real(self.repo)
        (self.repo / ".claude" / "settings.json").unlink()
        resultados, codigo = doctor_mod.ejecutar(self.repo)
        self.assertEqual(codigo, 1)
        self.assertIn(doctor_mod.NIVEL_ERROR, _niveles(resultados))

    def test_repo_no_instalado_no_crashea(self):
        """Ni siquiera corrió `ds_init`: `doctor` debe seguir devolviendo un
        reporte completo (con varios ERROR/WARN esperables), nunca una
        excepción cruda."""
        resultados, codigo = doctor_mod.ejecutar(self.repo)
        self.assertIsInstance(resultados, list)
        self.assertGreater(len(resultados), 0)
        self.assertEqual(codigo, 1)

    def test_control_json_corrupto_no_crashea(self):
        _instalar_harness_real(self.repo)
        (self.repo / ".ds_init" / "control.json").write_text("{ esto rompe el json", encoding="utf-8")
        resultados, codigo = doctor_mod.ejecutar(self.repo)
        self.assertIsInstance(resultados, list)
        self.assertEqual(codigo, 1)

    def test_settings_json_corrupto_no_crashea(self):
        _instalar_harness_real(self.repo)
        (self.repo / ".claude" / "settings.json").write_text("{ esto tambien rompe", encoding="utf-8")
        resultados, codigo = doctor_mod.ejecutar(self.repo)
        self.assertIsInstance(resultados, list)
        self.assertEqual(codigo, 1)

    def test_destino_inexistente_no_crashea(self):
        no_existe = self.repo / "no-existe-de-verdad"
        resultados, codigo = doctor_mod.ejecutar(no_existe)
        self.assertIsInstance(resultados, list)
        self.assertEqual(codigo, 1)

    def test_check_individual_que_explota_no_tumba_todo_el_reporte(self):
        _instalar_harness_real(self.repo)
        with patch(
            "tools.harmessi.doctor._check_agents", side_effect=RuntimeError("boom inesperado")
        ):
            resultados, codigo = doctor_mod.ejecutar(self.repo)
        self.assertEqual(codigo, 1)
        self.assertTrue(any("EXCEPCION" in r.codigo for r in resultados))
        # El resto del reporte igual se completó (otras secciones presentes).
        self.assertIn(doctor_mod.SECCION_RUNTIME, {r.seccion for r in resultados})

    def test_formatear_incluye_secciones_y_resumen(self):
        _instalar_harness_real(self.repo)
        resultados, _ = doctor_mod.ejecutar(self.repo)
        texto = doctor_mod.formatear(resultados)
        self.assertIn("=== CORE ===", texto)
        self.assertIn("=== HARMESSI ===", texto)
        self.assertIn("=== RUNTIME ===", texto)
        self.assertIn("Resumen:", texto)
        self.assertIn("[OK]", texto)


if __name__ == "__main__":
    unittest.main()

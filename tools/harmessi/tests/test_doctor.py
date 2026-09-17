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
from tools.ds_init import legacy as legacy_mod
from tools.ds_init import writer as ds_init_writer
from tools.ds_init.manifest import ORDEN_STAGES
from tools.ds_init.planner import construir_plan
from tools.ds_init.version import HARNESS_VERSION
from tools.dsguard import checks
from tools.dsguard import maturity
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


def _instalar_harness_real_con_stage(destino: Path, stage: str):
    """Como `_instalar_harness_real`, pero pasando `stage` explícito (Change
    7 v0.3) -- usado para ejercitar el camino stage-aware de Doctor. Nota:
    escribir directamente con `writer.instalar(..., stage=...)` (en vez de
    pasar por `cli.py sync`) es una simplificación deliberada de fixture:
    la restricción de `--stage production_candidate/production` rechazado en
    una instalación NUEVA vive en `cli.py` (capa de UX), no en
    `writer.instalar`/`construir_plan` -- a ese nivel cualquier stage de
    `ORDEN_STAGES` es válido (`design.md` no distingue "install" de "sync" a
    nivel de escritura, solo a nivel de CLI)."""
    config = _config_base(destino)
    config["stage"] = stage
    plan = construir_plan(PERFIL, destino, config, stage=stage)
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


def _statuses(resultados, code=None):
    """Como `_niveles`, pero para resultados de funciones `_check_*` llamadas
    DIRECTAMENTE (sin pasar por `doctor_mod.ejecutar`) -- esas devuelven
    `list[checks.CheckResult]` (vocabulario neutral `.status`/`.code`), no
    `list[doctor_mod.ResultadoCheck]` (`.nivel`/`.codigo`)."""
    if code is None:
        return {r.status for r in resultados}
    return {r.status for r in resultados if r.code == code}


class TestChecksCore(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_repo_git_temporal()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_version_python_ok(self):
        resultados = doctor_mod._check_version_python()
        self.assertEqual(resultados[0].status, checks.STATUS_PASS)

    def test_git_disponible_ok(self):
        resultados = doctor_mod._check_git_disponible()
        self.assertEqual(resultados[0].status, checks.STATUS_PASS)

    def test_repo_git_valido_ok(self):
        resultados = doctor_mod._check_repo_git_valido(self.repo)
        self.assertEqual(resultados[0].status, checks.STATUS_PASS)

    def test_repo_git_invalido_error(self):
        no_git = Path(tempfile.mkdtemp(prefix="harmessi_doctor_test_no_git_"))
        try:
            resultados = doctor_mod._check_repo_git_valido(no_git)
            self.assertEqual(resultados[0].status, checks.STATUS_FAIL)
        finally:
            shutil.rmtree(no_git, ignore_errors=True)

    def test_working_tree_limpio_ok(self):
        resultados = doctor_mod._check_working_tree(self.repo)
        self.assertEqual(resultados[0].status, checks.STATUS_PASS)

    def test_working_tree_sucio_warn(self):
        (self.repo / "archivo_sucio.txt").write_text("x", encoding="utf-8")
        resultados = doctor_mod._check_working_tree(self.repo)
        self.assertEqual(resultados[0].status, checks.STATUS_WARN)

    def test_venv_faltante_warn(self):
        resultados = doctor_mod._check_venv(self.repo)
        self.assertEqual(resultados[0].status, checks.STATUS_WARN)

    def test_venv_presente_ok(self):
        _crear_interprete_falso(self.repo)
        resultados = doctor_mod._check_venv(self.repo)
        self.assertEqual(resultados[0].status, checks.STATUS_PASS)

    def test_permisos_ok(self):
        resultados = doctor_mod._check_permisos(self.repo)
        self.assertEqual(resultados[0].status, checks.STATUS_PASS)

    def test_permisos_error_si_falla_escritura(self):
        with patch("tools.harmessi.doctor._probar_escritura", side_effect=OSError("sin permiso")):
            resultados = doctor_mod._check_permisos(self.repo)
        self.assertEqual(resultados[0].status, checks.STATUS_FAIL)


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
        self.assertEqual(resultados[0].status, checks.STATUS_PASS)

    def test_archivos_administrados_ok(self):
        control_data, _ = doctor_mod._leer_control_json(self.repo)
        resultados = doctor_mod._check_archivos_administrados(self.repo, control_data)
        self.assertEqual(_statuses(resultados), {checks.STATUS_PASS})

    def test_archivos_administrados_error_si_falta_critico(self):
        (self.repo / ".claude" / "settings.json").unlink()
        control_data, _ = doctor_mod._leer_control_json(self.repo)
        resultados = doctor_mod._check_archivos_administrados(self.repo, control_data)
        self.assertIn(checks.STATUS_FAIL, _statuses(resultados))

    def test_archivos_administrados_warn_si_falta_no_critico(self):
        (self.repo / ".claude" / "skills" / "lead-data-scientist" / "templates" / "tasks.md").unlink()
        control_data, _ = doctor_mod._leer_control_json(self.repo)
        resultados = doctor_mod._check_archivos_administrados(self.repo, control_data)
        self.assertIn(checks.STATUS_WARN, _statuses(resultados))
        self.assertNotIn(checks.STATUS_FAIL, _statuses(resultados))

    def test_archivos_administrados_warn_sin_control_json(self):
        resultados = doctor_mod._check_archivos_administrados(self.repo, None)
        self.assertEqual(resultados[0].status, checks.STATUS_WARN)

    def test_drift_ok_sin_cambios(self):
        control_data, _ = doctor_mod._leer_control_json(self.repo)
        resultados = doctor_mod._check_hashes_drift(self.repo, control_data)
        self.assertEqual(_statuses(resultados), {checks.STATUS_PASS})

    def test_drift_warn_si_archivo_modificado(self):
        ruta = self.repo / "tools" / "ds_guard.py"
        ruta.write_text(ruta.read_text(encoding="utf-8") + "\n# modificado a mano\n", encoding="utf-8")
        control_data, _ = doctor_mod._leer_control_json(self.repo)
        resultados = doctor_mod._check_hashes_drift(self.repo, control_data)
        self.assertIn(checks.STATUS_WARN, _statuses(resultados))

    def test_drift_error_si_archivo_administrado_falta(self):
        (self.repo / "tools" / "ds_guard.py").unlink()
        control_data, _ = doctor_mod._leer_control_json(self.repo)
        resultados = doctor_mod._check_hashes_drift(self.repo, control_data)
        self.assertIn(checks.STATUS_FAIL, _statuses(resultados))

    def test_agents_ok(self):
        resultados = doctor_mod._check_agents(self.repo)
        self.assertEqual(_statuses(resultados), {checks.STATUS_PASS})

    def test_agents_error_si_falta(self):
        (self.repo / ".claude" / "agents" / "notebook-runner.md").unlink()
        resultados = doctor_mod._check_agents(self.repo)
        self.assertIn(checks.STATUS_FAIL, _statuses(resultados))

    def test_skill_ok(self):
        resultados = doctor_mod._check_skill_lead_data_scientist(self.repo)
        self.assertEqual(resultados[0].status, checks.STATUS_PASS)

    def test_skill_warn_si_falta_archivo(self):
        (self.repo / ".claude" / "skills" / "lead-data-scientist" / "verificador.md").unlink()
        resultados = doctor_mod._check_skill_lead_data_scientist(self.repo)
        self.assertEqual(resultados[0].status, checks.STATUS_WARN)

    def test_settings_ok(self):
        _, resultados = doctor_mod._check_settings(self.repo)
        self.assertEqual(resultados[0].status, checks.STATUS_PASS)

    def test_settings_error_si_falta(self):
        (self.repo / ".claude" / "settings.json").unlink()
        _, resultados = doctor_mod._check_settings(self.repo)
        self.assertEqual(resultados[0].status, checks.STATUS_FAIL)

    def test_settings_error_si_json_invalido(self):
        (self.repo / ".claude" / "settings.json").write_text("{ no es json", encoding="utf-8")
        _, resultados = doctor_mod._check_settings(self.repo)
        self.assertEqual(resultados[0].status, checks.STATUS_FAIL)

    def test_hooks_ok(self):
        settings_data, _ = doctor_mod._check_settings(self.repo)
        resultados = doctor_mod._check_hooks(self.repo, settings_data)
        self.assertEqual(_statuses(resultados), {checks.STATUS_PASS})

    def test_hooks_error_si_falta_matcher(self):
        ruta_settings = self.repo / ".claude" / "settings.json"
        datos = json.loads(ruta_settings.read_text(encoding="utf-8"))
        datos["hooks"]["PreToolUse"] = [
            h for h in datos["hooks"]["PreToolUse"] if h.get("matcher") != "Bash"
        ]
        ruta_settings.write_text(json.dumps(datos), encoding="utf-8")
        settings_data, _ = doctor_mod._check_settings(self.repo)
        resultados = doctor_mod._check_hooks(self.repo, settings_data)
        self.assertIn(checks.STATUS_FAIL, _statuses(resultados))

    def test_hooks_error_si_falta_matcher_de_rutas(self):
        """Bloque 3: el hook PreToolUse de protección de rutas (matcher con
        'NotebookEdit') debe estar presente igual que los otros dos."""
        ruta_settings = self.repo / ".claude" / "settings.json"
        datos = json.loads(ruta_settings.read_text(encoding="utf-8"))
        datos["hooks"]["PreToolUse"] = [
            h for h in datos["hooks"]["PreToolUse"] if "NotebookEdit" not in (h.get("matcher") or "")
        ]
        ruta_settings.write_text(json.dumps(datos), encoding="utf-8")
        settings_data, _ = doctor_mod._check_settings(self.repo)
        resultados = doctor_mod._check_hooks(self.repo, settings_data)
        self.assertIn(checks.STATUS_FAIL, _statuses(resultados))

    def test_coherencia_version_ok(self):
        control_data, _ = doctor_mod._leer_control_json(self.repo)
        resultados = doctor_mod._check_coherencia_version(control_data)
        self.assertEqual(resultados[0].status, checks.STATUS_PASS)

    def test_coherencia_version_warn_si_distinta(self):
        control_data, _ = doctor_mod._leer_control_json(self.repo)
        control_data["harness_version"] = "0.0.1-otra"
        resultados = doctor_mod._check_coherencia_version(control_data)
        self.assertEqual(resultados[0].status, checks.STATUS_WARN)

    def test_guardrails_json_ok(self):
        resultados = doctor_mod._check_guardrails_json(self.repo)
        self.assertEqual(resultados[0].status, checks.STATUS_PASS)

    def test_guardrails_json_warn_si_falta(self):
        (self.repo / ".claude" / "guardrails.json").unlink()
        resultados = doctor_mod._check_guardrails_json(self.repo)
        self.assertEqual(resultados[0].status, checks.STATUS_WARN)

    def test_guardrails_json_error_si_corrupto(self):
        (self.repo / ".claude" / "guardrails.json").write_text("{ esto no es json valido", encoding="utf-8")
        resultados = doctor_mod._check_guardrails_json(self.repo)
        self.assertEqual(resultados[0].status, checks.STATUS_FAIL)
        self.assertIn("fail-closed", resultados[0].message.lower())


class TestChecksRuntimeInstalacionReal(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_repo_git_temporal()
        _instalar_harness_real(self.repo)

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_launchers_existen_ok(self):
        resultados = doctor_mod._check_launchers_existen(self.repo)
        self.assertEqual(_statuses(resultados), {checks.STATUS_PASS})

    def test_launchers_faltantes_error(self):
        (self.repo / "tools" / "nbrunner" / "hook_launcher.py").unlink()
        resultados = doctor_mod._check_launchers_existen(self.repo)
        self.assertIn(checks.STATUS_FAIL, _statuses(resultados))

    def test_interprete_ejecuta_hooks_sin_interprete_error(self):
        resultados = doctor_mod._check_interprete_ejecuta_hooks(self.repo)
        self.assertEqual(resultados[0].status, checks.STATUS_FAIL)

    def test_interprete_ejecuta_hooks_ok_mockeado(self):
        _crear_interprete_falso(self.repo)
        with patch("tools.harmessi.doctor.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stderr="")
            resultados = doctor_mod._check_interprete_ejecuta_hooks(self.repo)
        self.assertEqual(resultados[0].status, checks.STATUS_PASS)

    def test_interprete_ejecuta_hooks_error_si_falla_import(self):
        _crear_interprete_falso(self.repo)
        with patch("tools.harmessi.doctor.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=1, stderr="ModuleNotFoundError"
            )
            resultados = doctor_mod._check_interprete_ejecuta_hooks(self.repo)
        self.assertEqual(resultados[0].status, checks.STATUS_FAIL)

    def test_hooks_configurados_existen_ok(self):
        settings_data, _ = doctor_mod._check_settings(self.repo)
        resultados = doctor_mod._check_hooks_configurados_existen(self.repo, settings_data)
        self.assertTrue(resultados)
        self.assertEqual(_statuses(resultados), {checks.STATUS_PASS})

    def test_hooks_configurados_existen_error_si_falta_script(self):
        (self.repo / "tools" / "nbrunner" / "hook_launcher.py").unlink()
        settings_data, _ = doctor_mod._check_settings(self.repo)
        resultados = doctor_mod._check_hooks_configurados_existen(self.repo, settings_data)
        self.assertIn(checks.STATUS_FAIL, _statuses(resultados))

    def test_dependencia_shell_ok_sin_bash(self):
        """El settings.json que instala esta versión de Harmessi ya no usa
        `bash "..."`: el objetivo cross-platform del Bloque 2."""
        settings_data, _ = doctor_mod._check_settings(self.repo)
        resultados = doctor_mod._check_dependencia_shell(settings_data)
        self.assertEqual(_statuses(resultados), {checks.STATUS_PASS})

    def test_dependencia_shell_error_si_bash_no_disponible(self):
        ruta_settings = self.repo / ".claude" / "settings.json"
        datos = json.loads(ruta_settings.read_text(encoding="utf-8"))
        datos["hooks"]["PreToolUse"][0]["hooks"][0]["command"] = 'bash "${CLAUDE_PROJECT_DIR}/hook.sh"'
        with patch("tools.harmessi.doctor.shutil.which", return_value=None):
            resultados = doctor_mod._check_dependencia_shell(datos)
        self.assertIn(checks.STATUS_FAIL, _statuses(resultados))

    def test_dependencia_shell_warn_si_bash_disponible(self):
        ruta_settings = self.repo / ".claude" / "settings.json"
        datos = json.loads(ruta_settings.read_text(encoding="utf-8"))
        datos["hooks"]["PreToolUse"][0]["hooks"][0]["command"] = 'bash "${CLAUDE_PROJECT_DIR}/hook.sh"'
        with patch("tools.harmessi.doctor.shutil.which", return_value="/usr/bin/bash"):
            resultados = doctor_mod._check_dependencia_shell(datos)
        statuses_bash = {
            r.status for r in resultados if "bash" in r.message.lower() and r.status != checks.STATUS_PASS
        }
        self.assertIn(checks.STATUS_WARN, statuses_bash)


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


class TestRetrofitChecksEngine(unittest.TestCase):
    """Tests nuevos de `20260915-checks-engine-foundation`: NO modifican
    ninguna aserción existente arriba -- solo agregan cobertura del
    vocabulario neutral interno (`checks.CheckResult`) y de la traducción a
    `ResultadoCheck` (público de Doctor, sin cambios de UX)."""

    def setUp(self):
        self.repo = _crear_repo_git_temporal()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_check_individual_devuelve_list_checkresult_con_vocabulario_nuevo(self):
        resultados = doctor_mod._check_version_python()
        self.assertEqual(len(resultados), 1)
        self.assertIsInstance(resultados[0], checks.CheckResult)
        self.assertEqual(resultados[0].status, checks.STATUS_PASS)

    def test_check_repo_git_invalido_devuelve_checkresult_fail(self):
        no_git = Path(tempfile.mkdtemp(prefix="harmessi_doctor_test_no_git_"))
        try:
            resultados = doctor_mod._check_repo_git_valido(no_git)
            self.assertIsInstance(resultados[0], checks.CheckResult)
            self.assertEqual(resultados[0].status, checks.STATUS_FAIL)
        finally:
            shutil.rmtree(no_git, ignore_errors=True)

    def test_traducir_mapea_pass_a_ok(self):
        r = checks.CheckResult(checks.STATUS_PASS, "COD", "mensaje", subject="ubi")
        traducido = doctor_mod._traducir(doctor_mod.SECCION_CORE, r)
        self.assertEqual(traducido.nivel, doctor_mod.NIVEL_OK)
        self.assertEqual(traducido.seccion, doctor_mod.SECCION_CORE)
        self.assertEqual(traducido.codigo, "COD")
        self.assertEqual(traducido.mensaje, "mensaje")
        self.assertEqual(traducido.ubicacion, "ubi")

    def test_traducir_mapea_warn_a_warn(self):
        r = checks.CheckResult(checks.STATUS_WARN, "COD", "mensaje")
        traducido = doctor_mod._traducir(doctor_mod.SECCION_HARMESSI, r)
        self.assertEqual(traducido.nivel, doctor_mod.NIVEL_WARN)

    def test_traducir_mapea_fail_a_error(self):
        r = checks.CheckResult(checks.STATUS_FAIL, "COD", "mensaje")
        traducido = doctor_mod._traducir(doctor_mod.SECCION_RUNTIME, r)
        self.assertEqual(traducido.nivel, doctor_mod.NIVEL_ERROR)

    def test_ejecutar_check_traduce_excepcion_a_resultadocheck_error(self):
        def _explota():
            raise RuntimeError("boom")

        resultados = doctor_mod._ejecutar_check(doctor_mod.SECCION_CORE, "COD-BASE", _explota)
        self.assertEqual(len(resultados), 1)
        self.assertIsInstance(resultados[0], doctor_mod.ResultadoCheck)
        self.assertEqual(resultados[0].nivel, doctor_mod.NIVEL_ERROR)
        self.assertEqual(resultados[0].codigo, "COD-BASE-EXCEPCION")

    def test_formatear_agrega_segmento_na_si_conteo_mayor_a_cero(self):
        resultados = [
            doctor_mod.ResultadoCheck(doctor_mod.NIVEL_OK, doctor_mod.SECCION_CORE, "X-OK", "ok"),
            doctor_mod.ResultadoCheck("N/A", doctor_mod.SECCION_CORE, "X-NA", "no aplica"),
        ]
        texto = doctor_mod.formatear(resultados)
        self.assertIn("[N/A]", texto)
        self.assertIn("1 [N/A]", texto.splitlines()[-1])

    def test_formatear_sin_resultados_na_no_agrega_segmento(self):
        _instalar_harness_real(self.repo)
        # Change 7 v0.3 agregó `HARMESSI-INSTALLATION-STAGE`, que da N/A si
        # falta `.harmessi/project.json` -- para seguir ejercitando el caso
        # "cero N/A" que este test verifica, hace falta que ese check
        # resuelva a PASS (project_stage <= installation_stage instalado),
        # no que falte el archivo de madurez.
        maturity.project_init(self.repo, stage="experiment")
        resultados, _ = doctor_mod.ejecutar(self.repo)
        self.assertEqual(_niveles(resultados) & {"N/A"}, set())
        texto = doctor_mod.formatear(resultados)
        self.assertNotIn("[N/A]", texto)
        ultima_linea = texto.splitlines()[-1]
        self.assertTrue(ultima_linea.startswith("Resumen: "))
        self.assertEqual(ultima_linea.count("["), 3)  # solo [OK], [WARN], [ERROR]


class TestArchivosAdministradosStageAware(unittest.TestCase):
    """Tests de Change 7 v0.3 (R10 de `spec.md`): `_check_archivos_administrados`
    usa `manifest_para_perfil_y_stage` cuando `control_data` tiene
    `installation_stage`; sin esa clave (legacy), preserva el comportamiento
    actual EXACTO -- ya cubierto por `TestChecksHarmessiInstalacionReal`
    (que instala vía `_instalar_harness_real`, sin `stage` en `config`, y por
    lo tanto sin `installation_stage` en `control.json` -- el mismo camino
    legacy que hoy)."""

    def setUp(self):
        self.repo = _crear_repo_git_temporal()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_stage_discovery_no_reclama_agentes_ni_docs_production(self):
        _instalar_harness_real_con_stage(self.repo, "discovery")
        control_data, _ = doctor_mod._leer_control_json(self.repo)
        self.assertEqual(control_data.get("installation_stage"), "discovery")

        resultados = doctor_mod._check_archivos_administrados(self.repo, control_data)
        self.assertEqual(_statuses(resultados), {checks.STATUS_PASS})

    def test_stage_experiment_no_reclama_production_candidate_ni_production(self):
        _instalar_harness_real_con_stage(self.repo, "experiment")
        control_data, _ = doctor_mod._leer_control_json(self.repo)
        self.assertEqual(control_data.get("installation_stage"), "experiment")

        resultados = doctor_mod._check_archivos_administrados(self.repo, control_data)
        self.assertEqual(_statuses(resultados), {checks.STATUS_PASS})

        # Confirmación directa: los docs de production_candidate/production
        # ni siquiera existen en el destino (nunca se instalaron en
        # 'experiment'), y sin embargo el check da PASS -- nunca se reclaman.
        self.assertFalse(
            (self.repo / ".claude" / "skills" / "lead-data-scientist" / "production-readiness.md").exists()
        )
        self.assertFalse(
            (self.repo / ".claude" / "skills" / "lead-data-scientist" / "operations.md").exists()
        )

    def test_stage_experiment_si_falta_agente_de_su_propio_bundle_sigue_reportando(self):
        _instalar_harness_real_con_stage(self.repo, "experiment")
        (self.repo / ".claude" / "agents" / "notebook-runner.md").unlink()
        control_data, _ = doctor_mod._leer_control_json(self.repo)

        resultados = doctor_mod._check_archivos_administrados(self.repo, control_data)
        self.assertIn(checks.STATUS_FAIL, _statuses(resultados))

    def test_stage_production_candidate_exige_set_acumulado_completo(self):
        _instalar_harness_real_con_stage(self.repo, "production_candidate")
        control_data, _ = doctor_mod._leer_control_json(self.repo)
        self.assertEqual(control_data.get("installation_stage"), "production_candidate")

        resultados = doctor_mod._check_archivos_administrados(self.repo, control_data)
        self.assertEqual(_statuses(resultados), {checks.STATUS_PASS})
        self.assertTrue(
            (self.repo / ".claude" / "skills" / "lead-data-scientist" / "production-readiness.md").exists()
        )
        self.assertFalse(
            (self.repo / ".claude" / "skills" / "lead-data-scientist" / "operations.md").exists()
        )

        (self.repo / ".claude" / "skills" / "lead-data-scientist" / "production-readiness.md").unlink()
        resultados = doctor_mod._check_archivos_administrados(self.repo, control_data)
        self.assertIn(checks.STATUS_WARN, _statuses(resultados))

    def test_stage_production_exige_operations_tambien(self):
        _instalar_harness_real_con_stage(self.repo, "production")
        control_data, _ = doctor_mod._leer_control_json(self.repo)
        self.assertEqual(control_data.get("installation_stage"), "production")

        resultados = doctor_mod._check_archivos_administrados(self.repo, control_data)
        self.assertEqual(_statuses(resultados), {checks.STATUS_PASS})
        self.assertTrue(
            (self.repo / ".claude" / "skills" / "lead-data-scientist" / "operations.md").exists()
        )

    def test_legacy_sin_installation_stage_se_comporta_exactamente_igual_que_hoy(self):
        """0 diff respecto del comportamiento anterior a este change: sin
        `installation_stage`, usa `manifest_para_perfil(perfil)` completo --
        un archivo de 'production_candidate'/'production' (que ni siquiera
        existe en una instalación legacy) se reporta como WARN faltante,
        exactamente como cualquier otro archivo administrado faltante."""
        _instalar_harness_real(self.repo)
        # `_instalar_harness_real` usa `construir_plan(..., stage=None)`, que
        # devuelve el manifiesto COMPLETO (R3: `manifest_para_perfil` no se
        # filtra nunca) -- eso incluye los 2 documentos nuevos de este mismo
        # change, algo que una instalación legacy REAL (anterior a que esas
        # entradas existieran en el manifiesto) nunca pudo tener. Se borran
        # acá para simular fielmente ese escenario legacy real.
        (self.repo / ".claude" / "skills" / "lead-data-scientist" / "production-readiness.md").unlink()
        (self.repo / ".claude" / "skills" / "lead-data-scientist" / "operations.md").unlink()
        control_data, _ = doctor_mod._leer_control_json(self.repo)
        self.assertNotIn("installation_stage", control_data)

        resultados = doctor_mod._check_archivos_administrados(self.repo, control_data)
        codigos_faltantes = {r.subject for r in resultados if r.status == checks.STATUS_WARN}
        self.assertIn(".claude/skills/lead-data-scientist/production-readiness.md", codigos_faltantes)
        self.assertIn(".claude/skills/lead-data-scientist/operations.md", codigos_faltantes)
        self.assertNotIn(checks.STATUS_FAIL, _statuses(resultados))


class TestCheckInstallationStage(unittest.TestCase):
    """Tests de Change 7 v0.3 (R11 de `spec.md`): `HARMESSI-INSTALLATION-STAGE`,
    solo lectura, nunca `ERROR`/`FAIL`."""

    def setUp(self):
        self.repo = _crear_repo_git_temporal()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_na_sin_project_json(self):
        _instalar_harness_real_con_stage(self.repo, "experiment")
        control_data, _ = doctor_mod._leer_control_json(self.repo)

        resultados = doctor_mod._check_installation_stage(self.repo, control_data)
        self.assertEqual(resultados[0].status, checks.STATUS_NA)

    def test_na_sin_control_data(self):
        maturity.project_init(self.repo, stage="experiment")

        resultados = doctor_mod._check_installation_stage(self.repo, None)
        self.assertEqual(resultados[0].status, checks.STATUS_NA)

    def test_na_con_project_json_corrupto(self):
        maturity.project_init(self.repo, stage="experiment")
        maturity.state_path(self.repo).write_text("{ esto rompe el json", encoding="utf-8")
        _instalar_harness_real_con_stage(self.repo, "experiment")
        control_data, _ = doctor_mod._leer_control_json(self.repo)

        resultados = doctor_mod._check_installation_stage(self.repo, control_data)
        self.assertEqual(resultados[0].status, checks.STATUS_NA)

    def test_pass_si_stages_iguales(self):
        maturity.project_init(self.repo, stage="experiment")
        _instalar_harness_real_con_stage(self.repo, "experiment")
        control_data, _ = doctor_mod._leer_control_json(self.repo)

        resultados = doctor_mod._check_installation_stage(self.repo, control_data)
        self.assertEqual(resultados[0].status, checks.STATUS_PASS)

    def test_warn_si_project_stage_mas_avanzado(self):
        estado, _ = maturity.project_init(self.repo, stage="experiment")
        maturity.calibrar(self.repo, "production_candidate", "avance de prueba")
        _instalar_harness_real_con_stage(self.repo, "experiment")
        control_data, _ = doctor_mod._leer_control_json(self.repo)

        resultados = doctor_mod._check_installation_stage(self.repo, control_data)
        self.assertEqual(resultados[0].status, checks.STATUS_WARN)
        self.assertIn("sync", resultados[0].message.lower())
        self.assertIn("production_candidate", resultados[0].message)

    def test_pass_si_installation_stage_mas_avanzado_nunca_error(self):
        maturity.project_init(self.repo, stage="discovery")
        _instalar_harness_real_con_stage(self.repo, "production")
        control_data, _ = doctor_mod._leer_control_json(self.repo)

        resultados = doctor_mod._check_installation_stage(self.repo, control_data)
        self.assertEqual(resultados[0].status, checks.STATUS_PASS)

    def test_usa_inferencia_legacy_solo_para_mostrar_sin_persistir(self):
        maturity.project_init(self.repo, stage="experiment")
        _instalar_harness_real(self.repo)  # legacy: sin 'stage' en config.
        control_data, _ = doctor_mod._leer_control_json(self.repo)
        self.assertNotIn("installation_stage", control_data)

        ruta_control = self.repo / ".ds_init" / "control.json"
        bytes_control_antes = ruta_control.read_bytes()

        resultados = doctor_mod._check_installation_stage(self.repo, control_data)
        # Legacy con los 5 archivos de 'experiment' presentes -> se infiere
        # 'production' (R6) -- 'production' >= 'experiment' -> PASS.
        self.assertEqual(resultados[0].status, checks.STATUS_PASS)

        # Nunca persiste la inferencia ni muta control.json/project.json.
        self.assertEqual(ruta_control.read_bytes(), bytes_control_antes)
        control_releido = json.loads(ruta_control.read_text(encoding="utf-8"))
        self.assertNotIn("installation_stage", control_releido)

    def test_nunca_error_ante_excepcion_inesperada_no_de_dominio(self):
        """Hallazgo de revisión, Change 7 v0.3: `maturity.leer_estado` puede
        levantar algo distinto de `MaturityEstadoError` (p. ej. una carrera
        TOCTOU real, o cualquier fallo de bajo nivel) -- este check tiene
        prohibido, bajo cualquier escenario, dejar escapar eso como
        `ERROR`/`FAIL` (R11 de spec.md). Se simula con un `OSError` genérico,
        no capturado por el `except maturity.MaturityEstadoError` interno."""
        maturity.project_init(self.repo, stage="experiment")
        _instalar_harness_real_con_stage(self.repo, "experiment")
        control_data, _ = doctor_mod._leer_control_json(self.repo)

        with patch.object(maturity, "leer_estado", side_effect=OSError("disco no disponible")):
            resultados = doctor_mod._check_installation_stage(self.repo, control_data)

        self.assertEqual(resultados[0].status, checks.STATUS_NA)
        self.assertNotEqual(resultados[0].status, checks.STATUS_FAIL)

    def test_doctor_ejecutar_nunca_muta_project_json_ni_control_json(self):
        maturity.project_init(self.repo, stage="experiment")
        _instalar_harness_real_con_stage(self.repo, "experiment")

        ruta_project = maturity.state_path(self.repo)
        ruta_control = self.repo / ".ds_init" / "control.json"
        bytes_project_antes = ruta_project.read_bytes()
        bytes_control_antes = ruta_control.read_bytes()

        doctor_mod.ejecutar(self.repo)

        self.assertEqual(ruta_project.read_bytes(), bytes_project_antes)
        self.assertEqual(ruta_control.read_bytes(), bytes_control_antes)

    def test_wireado_en_ejecutar_bajo_seccion_harmessi(self):
        maturity.project_init(self.repo, stage="experiment")
        _instalar_harness_real_con_stage(self.repo, "experiment")

        resultados, _ = doctor_mod.ejecutar(self.repo)
        encontrado = [r for r in resultados if r.codigo == "HARMESSI-INSTALLATION-STAGE"]
        self.assertEqual(len(encontrado), 1)
        self.assertEqual(encontrado[0].seccion, doctor_mod.SECCION_HARMESSI)
        self.assertEqual(encontrado[0].nivel, doctor_mod.NIVEL_OK)


class TestDoctorRegresionEsteRepositorio(unittest.TestCase):
    """R14/AC de `spec.md`: `harmessi doctor` corrido sobre ESTE repositorio
    (instalación legacy real, sin `installation_stage`) produce
    `HARMESSI-ARCHIVOS-ESPERADOS` con el mismo criterio completo que antes de
    este change -- el único drift esperado son los 2 archivos nuevos del
    propio manifiesto de Change 7 (`production-readiness.md`/`operations.md`,
    reportados como WARN por faltantes, nunca ERROR, ya que no son
    `_RUTAS_CRITICAS`)."""

    def test_este_repo_tiene_installation_stage_valido_en_su_control_json(self):
        """Desde Change 7 v0.3 (progressive capability installation), 'installation_stage' es
        un campo legítimo y esperado de control.json -- este test reemplaza al anterior
        (`test_este_repo_no_tiene_installation_stage_en_su_control_json`), que asumía la
        ausencia del campo porque predataba ese Change. Diagnosticado como test desactualizado,
        no como bug real, durante Change 5 v0.4 (release hardening)."""
        raiz = Path(__file__).resolve().parents[3]
        control_data, resultados = doctor_mod._leer_control_json(raiz)
        self.assertIsNotNone(control_data)
        self.assertIn("installation_stage", control_data)
        self.assertIn(control_data["installation_stage"], ORDEN_STAGES)

    def test_este_repo_archivos_administrados_sin_fail_inesperado(self):
        raiz = Path(__file__).resolve().parents[3]
        control_data, _ = doctor_mod._leer_control_json(raiz)
        resultados = doctor_mod._check_archivos_administrados(raiz, control_data)
        # Ningún FAIL: todos los archivos _RUTAS_CRITICAS de este propio repo
        # (ya instalados) siguen presentes: el único drift posible son WARN
        # de los 2 docs nuevos de Change 7, que todavía no están instalados
        # físicamente en este propio checkout (no son críticos).
        self.assertNotIn(checks.STATUS_FAIL, _statuses(resultados))


if __name__ == "__main__":
    unittest.main()

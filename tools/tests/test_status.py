"""Tests de `tools.dsguard.status` (Change 8, v0.3:
20260915-unified-status-surface) -- superficie unificada de status de
proyecto, de solo lectura.

Sigue el mismo patrón de `test_readiness.py`/`test_mlops_foundations.py`:
funciones puras se llaman directo sobre un repo git temporal propio (nunca
este repositorio real, salvo la clase explícita de `harness` que compara
contra `harmessi doctor` corrido sobre el checkout fuente real, mismo
criterio ya usado por `tools/harmessi/tests/test_doctor.py`).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ORIGEN = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ORIGEN / "tools"))
sys.path.insert(0, str(REPO_ORIGEN))

from dsguard import checks, lifecycle, maturity, mlops_evidence, status  # noqa: E402

DS_GUARD = REPO_ORIGEN / "tools" / "ds_guard.py"


# --- Fixtures compartidas -----------------------------------------------------

def _crear_repo_git_temporal(prefix: str = "status_test_") -> Path:
    repo = Path(tempfile.mkdtemp(prefix=prefix))
    subprocess.run(["git", "init", "-q"], cwd=str(repo), check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(repo), check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(repo), check=True)
    (repo / "README.md").write_text("repo de prueba\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=str(repo), check=True)
    subprocess.run(["git", "commit", "-q", "-m", "inicial"], cwd=str(repo), check=True)
    return repo


def _commitear_todo(repo: Path, mensaje: str = "fixture") -> None:
    subprocess.run(["git", "add", "-A"], cwd=str(repo), check=True)
    subprocess.run(["git", "commit", "-q", "-m", mensaje], cwd=str(repo), check=True)


class _BaseRepoGit(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_repo_git_temporal()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)


# --- next_target (R3) ----------------------------------------------------------

class TestNextTarget(unittest.TestCase):
    def test_secuencia_completa(self):
        self.assertEqual(status.next_target("discovery"), "experiment")
        self.assertEqual(status.next_target("experiment"), "production_candidate")
        self.assertEqual(status.next_target("production_candidate"), "production")
        self.assertIsNone(status.next_target("production"))

    def test_desconocido_o_none_devuelve_none(self):
        self.assertIsNone(status.next_target(None))
        self.assertIsNone(status.next_target("algo_invalido"))


# --- evaluar_status: forma minima (R2) ------------------------------------------

class TestEvaluarStatusForma(_BaseRepoGit):
    def test_secciones_minimas_presentes(self):
        resultado = status.evaluar_status(self.repo)
        for clave in ("project", "installation", "alignment", "lifecycle", "mlops", "readiness", "harness"):
            self.assertIn(clave, resultado)

    def test_nunca_lanza_en_repo_completamente_vacio(self):
        # Ni siquiera .git -- evaluar_status no debe asumir un repo git valido.
        vacio = Path(tempfile.mkdtemp(prefix="status_test_vacio_"))
        try:
            resultado = status.evaluar_status(vacio)
            self.assertIn("project", resultado)
        finally:
            shutil.rmtree(vacio, ignore_errors=True)


# --- project / risk (R6, R13) ---------------------------------------------------

class TestSeccionProject(_BaseRepoGit):
    def test_ausente_uninitialized(self):
        resultado = status.evaluar_status(self.repo)
        self.assertFalse(resultado["project"]["disponible"])
        self.assertFalse(resultado["project"]["tecnico"])
        self.assertIsNone(resultado["project"]["project_stage"])
        self.assertEqual(resultado["project"]["risk_status"], "unclassified")

    def test_corrupto_tecnico(self):
        ruta = maturity.state_path(self.repo)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text("esto no es json valido", encoding="utf-8")
        resultado = status.evaluar_status(self.repo)
        self.assertFalse(resultado["project"]["disponible"])
        self.assertTrue(resultado["project"]["tecnico"])

    def test_risk_none_unclassified(self):
        maturity.project_init(self.repo, stage="experiment")
        resultado = status.evaluar_status(self.repo)
        self.assertIsNone(resultado["project"]["risk_level"])
        self.assertEqual(resultado["project"]["risk_status"], "unclassified")

    def test_risk_low_medium_high_tal_cual(self):
        maturity.project_init(self.repo, stage="experiment")
        for nivel in ("low", "medium", "high"):
            maturity.set_risk(self.repo, nivel, "clasificacion de prueba")
            resultado = status.evaluar_status(self.repo)
            self.assertEqual(resultado["project"]["risk_level"], nivel)
            self.assertEqual(resultado["project"]["risk_status"], "classified")

    def test_production_candidate_con_risk_none_no_falla_solo_refleja_fail_de_readiness(self):
        maturity.project_init(self.repo, stage="experiment")
        lifecycle.lifecycle_init(self.repo)
        maturity.calibrar(self.repo, "production_candidate", "avance de prueba")
        resultado = status.evaluar_status(self.repo)
        self.assertIsNone(resultado["project"]["risk_level"])
        # status no decide nada -- solo refleja el FAIL que readiness.evaluar_readiness
        # ya produce para READINESS-RISK-CLASSIFIED (R6).
        codigos_blocking = [r["code"] for r in resultado["readiness"]["blocking"]]
        self.assertIn("READINESS-RISK-CLASSIFIED", codigos_blocking)


# --- installation / alignment (R5) ----------------------------------------------

class TestSeccionInstallationYAlignment(_BaseRepoGit):
    def _escribir_control(self, datos: dict) -> None:
        ds_init_dir = self.repo / ".ds_init"
        ds_init_dir.mkdir(parents=True, exist_ok=True)
        (ds_init_dir / "control.json").write_text(json.dumps(datos), encoding="utf-8")

    def test_control_ausente(self):
        resultado = status.evaluar_status(self.repo)
        self.assertFalse(resultado["installation"]["disponible"])
        self.assertIsNone(resultado["installation"]["installation_stage"])
        self.assertEqual(resultado["installation"]["origen"], "desconocido")
        self.assertEqual(resultado["alignment"]["estado"], "unknown")

    def test_control_corrupto(self):
        ds_init_dir = self.repo / ".ds_init"
        ds_init_dir.mkdir(parents=True, exist_ok=True)
        (ds_init_dir / "control.json").write_text("esto no es json", encoding="utf-8")
        resultado = status.evaluar_status(self.repo)
        self.assertFalse(resultado["installation"]["disponible"])
        self.assertTrue(resultado["installation"]["tecnico"])

    def test_declarado_igual_a_project_stage_aligned(self):
        maturity.project_init(self.repo, stage="experiment")
        self._escribir_control({"installation_stage": "experiment", "perfil": "python-jupyter-data"})
        resultado = status.evaluar_status(self.repo)
        self.assertEqual(resultado["installation"]["origen"], "declarado")
        self.assertEqual(resultado["alignment"]["estado"], "aligned")

    def test_project_mas_avanzado_sync_needed_con_comando(self):
        maturity.project_init(self.repo, stage="experiment")
        lifecycle.lifecycle_init(self.repo)
        maturity.calibrar(self.repo, "production_candidate", "avance de prueba")
        self._escribir_control({"installation_stage": "experiment"})
        resultado = status.evaluar_status(self.repo)
        self.assertEqual(resultado["alignment"]["estado"], "sync_needed")
        self.assertIn("ds_init sync --stage production_candidate --execute", resultado["alignment"]["mensaje"])

    def test_installation_mas_avanzado_ahead_nunca_error(self):
        maturity.project_init(self.repo, stage="discovery")
        self._escribir_control({"installation_stage": "production_candidate"})
        resultado = status.evaluar_status(self.repo)
        self.assertEqual(resultado["alignment"]["estado"], "ahead")

    def test_sin_installation_stage_con_inferencia_disponible_origen_inferido(self):
        # Repo fuente real disponible en sys.path (este proceso de test) --
        # tools.ds_init.legacy es importable, la inferencia debe funcionar.
        maturity.project_init(self.repo, stage="discovery")
        self._escribir_control({"perfil": "python-jupyter-data"})
        resultado = status.evaluar_status(self.repo)
        self.assertEqual(resultado["installation"]["origen"], "inferido")
        self.assertIn(resultado["installation"]["installation_stage"], maturity.PROJECT_STAGES)

    def test_sin_installation_stage_sin_ds_init_disponible_origen_desconocido(self):
        maturity.project_init(self.repo, stage="discovery")
        self._escribir_control({"perfil": "python-jupyter-data"})
        with patch("dsguard.status._importar_legacy", return_value=None):
            resultado = status.evaluar_status(self.repo)
        self.assertEqual(resultado["installation"]["origen"], "desconocido")
        self.assertEqual(resultado["alignment"]["estado"], "unknown")


# --- lifecycle (R7) ---------------------------------------------------------

class TestSeccionLifecycle(_BaseRepoGit):
    def test_ausente(self):
        resultado = status.evaluar_status(self.repo)
        self.assertFalse(resultado["lifecycle"]["disponible"])
        self.assertIn("lifecycle unavailable", resultado["lifecycle"]["mensaje"])

    def test_corrupto_distinto_de_ausente(self):
        ruta = lifecycle.state_path(self.repo)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text("esto no es json valido", encoding="utf-8")
        resultado = status.evaluar_status(self.repo)
        self.assertFalse(resultado["lifecycle"]["disponible"])
        self.assertTrue(resultado["lifecycle"]["tecnico"])
        self.assertNotIn("lifecycle unavailable", resultado["lifecycle"]["mensaje"])

    def test_parcial_resumen_correcto(self):
        lifecycle.lifecycle_init(self.repo)
        estado = lifecycle.leer_estado(lifecycle.state_path(self.repo))
        estado["crispdm"]["fases"]["business_understanding"]["estado"] = "cerrada"
        estado["crispdm"]["fases"]["data_understanding"]["estado"] = "cerrada"
        estado["kdd"]["pasos"]["selection"]["estado"] = "cerrada"
        lifecycle.escribir_estado(self.repo, estado)
        resultado = status.evaluar_status(self.repo)
        self.assertEqual(resultado["lifecycle"]["crispdm"]["resumen"], "2/8 closed")
        self.assertEqual(resultado["lifecycle"]["kdd"]["resumen"], "1/5 closed")

    def test_completo_resumen_correcto(self):
        lifecycle.lifecycle_init(self.repo)
        estado = lifecycle.leer_estado(lifecycle.state_path(self.repo))
        for fase in lifecycle.FASES_CRISPDM:
            estado["crispdm"]["fases"][fase]["estado"] = "cerrada"
        for paso in lifecycle.PASOS_KDD:
            estado["kdd"]["pasos"][paso]["estado"] = "cerrada"
        lifecycle.escribir_estado(self.repo, estado)
        resultado = status.evaluar_status(self.repo)
        self.assertEqual(resultado["lifecycle"]["crispdm"]["resumen"], "8/8 closed")
        self.assertEqual(resultado["lifecycle"]["kdd"]["resumen"], "5/5 closed")


# --- mlops.foundations (R8) --------------------------------------------------

class TestSeccionFoundations(_BaseRepoGit):
    def test_sin_project_json_todo_na(self):
        resultado = status.evaluar_status(self.repo)
        foundations = resultado["mlops"]["foundations"]
        self.assertEqual(len(foundations), 4)
        for r in foundations:
            self.assertEqual(r["status"], checks.STATUS_NA)

    def test_nunca_reinterpreta_a_fail(self):
        maturity.project_init(self.repo, stage="experiment")
        lifecycle.lifecycle_init(self.repo)
        resultado = status.evaluar_status(self.repo)
        foundations = resultado["mlops"]["foundations"]
        estados_validos = {checks.STATUS_PASS, checks.STATUS_WARN, checks.STATUS_NA}
        for r in foundations:
            self.assertIn(r["status"], estados_validos)
            self.assertNotEqual(r["status"], checks.STATUS_FAIL)


# --- proporcionalidad por stage (R10) + next_target por stage -----------------

class TestProporcionalidadPorStage(_BaseRepoGit):
    def test_discovery_colapsado_ambos(self):
        maturity.project_init(self.repo, stage="discovery")
        resultado = status.evaluar_status(self.repo)
        self.assertFalse(resultado["mlops"]["production_readiness"]["aplicable"])
        self.assertFalse(resultado["mlops"]["operations"]["aplicable"])
        self.assertEqual(resultado["readiness"]["next_target"], "experiment")

    def test_experiment_prodready_detalle_operations_colapsado(self):
        maturity.project_init(self.repo, stage="experiment")
        lifecycle.lifecycle_init(self.repo)
        resultado = status.evaluar_status(self.repo)
        self.assertTrue(resultado["mlops"]["production_readiness"]["aplicable"])
        self.assertFalse(resultado["mlops"]["operations"]["aplicable"])
        self.assertEqual(resultado["readiness"]["next_target"], "production_candidate")

    def test_production_candidate_ambos_detalle(self):
        maturity.project_init(self.repo, stage="experiment")
        lifecycle.lifecycle_init(self.repo)
        maturity.calibrar(self.repo, "production_candidate", "avance de prueba")
        resultado = status.evaluar_status(self.repo)
        self.assertTrue(resultado["mlops"]["production_readiness"]["aplicable"])
        self.assertTrue(resultado["mlops"]["operations"]["aplicable"])
        self.assertEqual(resultado["readiness"]["next_target"], "production")

    def test_production_ambos_detalle_sin_next_target(self):
        maturity.project_init(self.repo, stage="experiment")
        lifecycle.lifecycle_init(self.repo)
        maturity.calibrar(self.repo, "production_candidate", "avance de prueba")
        maturity.calibrar(self.repo, "production", "avance de prueba")
        resultado = status.evaluar_status(self.repo)
        self.assertTrue(resultado["mlops"]["production_readiness"]["aplicable"])
        self.assertTrue(resultado["mlops"]["operations"]["aplicable"])
        self.assertIsNone(resultado["readiness"]["next_target"])
        self.assertIn("stage final", resultado["readiness"]["mensaje"])


# --- readiness (R4) ----------------------------------------------------------

class TestSeccionReadiness(_BaseRepoGit):
    def test_ready_cuando_todo_satisfecho(self):
        # stage=discovery -> next_target="experiment", que solo exige
        # project/lifecycle validos (ver TestReadinessExperiment en
        # test_readiness.py) -- ambos lo estan.
        maturity.project_init(self.repo, stage="discovery")
        lifecycle.lifecycle_init(self.repo)
        resultado = status.evaluar_status(self.repo)
        self.assertEqual(resultado["readiness"]["next_target"], "experiment")
        self.assertTrue(resultado["readiness"]["ready"])
        self.assertEqual(resultado["readiness"]["resumen"], "READY")

    def test_not_ready_con_fail(self):
        maturity.project_init(self.repo, stage="discovery")
        # Sin lifecycle_init -- READINESS-LIFECYCLE-VALID debe fallar.
        resultado = status.evaluar_status(self.repo)
        self.assertFalse(resultado["readiness"]["ready"])
        self.assertEqual(resultado["readiness"]["resumen"], "NOT READY")
        self.assertTrue(resultado["readiness"]["blocking"])

    def test_technical_error_visible_explicitamente(self):
        maturity.project_init(self.repo, stage="experiment")
        ruta = lifecycle.state_path(self.repo)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text("esto no es json valido", encoding="utf-8")
        resultado = status.evaluar_status(self.repo)
        self.assertTrue(resultado["readiness"]["technical_error"])
        self.assertEqual(resultado["readiness"]["resumen"], "TECHNICAL ERROR")
        self.assertNotEqual(resultado["readiness"]["resumen"], "NOT READY")


# --- evidence (R9) -----------------------------------------------------------

class TestSeccionEvidencia(_BaseRepoGit):
    def test_capability_valida(self):
        maturity.project_init(self.repo, stage="experiment")
        lifecycle.lifecycle_init(self.repo)
        ruta = self.repo / "evidencia_packaging.txt"
        ruta.write_bytes(b"evidencia de packaging")
        mlops_evidence.agregar_evidencia(self.repo, "production_readiness", "packaging", ruta.name, "ok")
        resultado = status.evaluar_status(self.repo)
        capacidades = {
            c["capability"]: c for c in resultado["mlops"]["production_readiness"]["capacidades"]
        }
        self.assertTrue(capacidades["packaging"]["valido"])

    def test_capability_sin_evidencia(self):
        maturity.project_init(self.repo, stage="experiment")
        lifecycle.lifecycle_init(self.repo)
        resultado = status.evaluar_status(self.repo)
        capacidades = {
            c["capability"]: c for c in resultado["mlops"]["production_readiness"]["capacidades"]
        }
        self.assertFalse(capacidades["packaging"]["valido"])
        self.assertIn("sin evidencia", capacidades["packaging"]["detalle"])

    def test_capability_obsoleta_distinta_de_ausente(self):
        maturity.project_init(self.repo, stage="experiment")
        lifecycle.lifecycle_init(self.repo)
        ruta = self.repo / "evidencia_packaging.txt"
        ruta.write_bytes(b"evidencia de packaging")
        mlops_evidence.agregar_evidencia(self.repo, "production_readiness", "packaging", ruta.name, "ok")
        ruta.write_bytes(b"contenido modificado -- hash ya no coincide")
        resultado = status.evaluar_status(self.repo)
        capacidades = {
            c["capability"]: c for c in resultado["mlops"]["production_readiness"]["capacidades"]
        }
        self.assertFalse(capacidades["packaging"]["valido"])
        self.assertIn("obsoleta", capacidades["packaging"]["detalle"])

    def test_capability_operations_tier(self):
        maturity.project_init(self.repo, stage="experiment")
        lifecycle.lifecycle_init(self.repo)
        maturity.calibrar(self.repo, "production_candidate", "avance de prueba")
        ruta = self.repo / "evidencia_ops_monitoring.txt"
        ruta.write_bytes(b"evidencia de monitoring")
        mlops_evidence.agregar_evidencia(self.repo, "operations", "monitoring", ruta.name, "ok")
        resultado = status.evaluar_status(self.repo)
        capacidades = {c["capability"]: c for c in resultado["mlops"]["operations"]["capacidades"]}
        self.assertTrue(capacidades["monitoring"]["valido"])


# --- harness (R11) -----------------------------------------------------------

class TestSeccionHarness(_BaseRepoGit):
    def test_no_disponible_via_import_mockeado(self):
        with patch("dsguard.status._importar_doctor", return_value=None):
            resultado = status.evaluar_status(self.repo)
        self.assertFalse(resultado["harness"]["disponible"])
        self.assertIn("motivo", resultado["harness"])
        # El resto de las secciones no se corta.
        self.assertIn("project", resultado)
        self.assertIn("readiness", resultado)

    def test_falla_al_ejecutarse_no_excepcion_cruda(self):
        class _DoctorFalso:
            @staticmethod
            def ejecutar(_destino):
                raise RuntimeError("fallo simulado de doctor")

        with patch("dsguard.status._importar_doctor", return_value=_DoctorFalso):
            resultado = status.evaluar_status(self.repo)
        self.assertFalse(resultado["harness"]["disponible"])

    def test_principales_truncado_a_K_en_modo_compacto_completo_en_verbose(self):
        """Hallazgo de revisión: R11 exige 'hasta K mensajes... nunca la
        lista completa de Doctor salvo --verbose'. `evaluar_status`/
        `formatear_json` conservan la lista COMPLETA en `harness.principales`
        (mismo criterio que `readiness.blocking`, que tampoco se trunca en el
        dict); es `formatear_texto` quien aplica el corte a
        `status._K_PRINCIPALES_HARNESS` (5) en modo compacto, y lo levanta
        completo con `verbose=True`."""

        class _ResultadoFalso:
            def __init__(self, nivel, codigo):
                self.nivel = nivel
                self.codigo = codigo
                self.mensaje = f"mensaje de {codigo}"

        class _DoctorFalso:
            NIVEL_OK = "OK"
            NIVEL_WARN = "WARN"
            NIVEL_ERROR = "ERROR"

            @staticmethod
            def ejecutar(_destino):
                resultados = [
                    _ResultadoFalso("WARN", f"FALSO-WARN-{i}") for i in range(8)
                ]
                return resultados, 0

        with patch("dsguard.status._importar_doctor", return_value=_DoctorFalso):
            resultado = status.evaluar_status(self.repo)

        # El dict conserva los 8 mensajes completos, sin truncar.
        self.assertEqual(len(resultado["harness"]["principales"]), 8)

        texto_compacto = status.formatear_texto(resultado, verbose=False)
        texto_verbose = status.formatear_texto(resultado, verbose=True)

        self.assertEqual(
            sum(1 for l in texto_compacto.splitlines() if "FALSO-WARN-" in l),
            status._K_PRINCIPALES_HARNESS,
        )
        self.assertIn("más, usar --verbose", texto_compacto)
        self.assertEqual(
            sum(1 for l in texto_verbose.splitlines() if "FALSO-WARN-" in l), 8
        )
        self.assertNotIn("más, usar --verbose", texto_verbose)

    def test_disponible_desde_checkout_fuente_coincide_con_doctor_real(self):
        from tools.harmessi import doctor as doctor_mod

        resultados_directos, _exit = doctor_mod.ejecutar(REPO_ORIGEN)
        resultado_status = status._seccion_harness(REPO_ORIGEN)
        self.assertTrue(resultado_status["disponible"])
        conteos_directos = {"ok": 0, "warn": 0, "error": 0, "na": 0}
        for r in resultados_directos:
            if r.nivel == doctor_mod.NIVEL_OK:
                conteos_directos["ok"] += 1
            elif r.nivel == doctor_mod.NIVEL_WARN:
                conteos_directos["warn"] += 1
            elif r.nivel == doctor_mod.NIVEL_ERROR:
                conteos_directos["error"] += 1
            else:
                conteos_directos["na"] += 1
        self.assertEqual(resultado_status["ok"], conteos_directos["ok"])
        self.assertEqual(resultado_status["warn"], conteos_directos["warn"])
        self.assertEqual(resultado_status["error"], conteos_directos["error"])
        self.assertEqual(resultado_status["na"], conteos_directos["na"])


# --- Read-only estricto (R12) --------------------------------------------------

class TestReadOnly(_BaseRepoGit):
    def _snapshot(self) -> dict:
        rutas = (
            self.repo / ".harmessi" / "project.json",
            self.repo / ".ds_init" / "control.json",
            lifecycle.state_path(self.repo),
        )
        snap = {}
        for ruta in rutas:
            snap[str(ruta)] = ruta.read_bytes() if ruta.exists() else None
        return snap

    def test_bytes_identicos_repo_vacio(self):
        antes = self._snapshot()
        status.evaluar_status(self.repo)
        self.assertEqual(self._snapshot(), antes)

    def test_bytes_identicos_repo_completo(self):
        maturity.project_init(self.repo, stage="experiment")
        lifecycle.lifecycle_init(self.repo)
        maturity.set_risk(self.repo, "medium", "clasificacion de prueba")
        antes = self._snapshot()
        status.evaluar_status(self.repo)
        self.assertEqual(self._snapshot(), antes)

    def test_bytes_identicos_con_corrupcion(self):
        ruta = maturity.state_path(self.repo)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text("esto no es json valido", encoding="utf-8")
        antes = self._snapshot()
        status.evaluar_status(self.repo)
        self.assertEqual(self._snapshot(), antes)

    def test_bytes_identicos_con_technical_error_de_readiness(self):
        maturity.project_init(self.repo, stage="experiment")
        ruta = lifecycle.state_path(self.repo)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text("esto no es json valido", encoding="utf-8")
        antes = self._snapshot()
        status.evaluar_status(self.repo)
        self.assertEqual(self._snapshot(), antes)

    def test_status_py_nunca_llama_funciones_de_escritura(self):
        codigo = (REPO_ORIGEN / "tools" / "dsguard" / "status.py").read_text(encoding="utf-8")
        for prohibido in (
            "agregar_evidencia(",
            "escribir_estado(",
            "calibrar(",
            "promote(",
            "set_risk(",
            "project_init(",
            "lifecycle_init(",
        ):
            self.assertNotIn(prohibido, codigo, f"status.py no debe llamar a {prohibido!r}")


# --- JSON (R14) ----------------------------------------------------------------

class TestFormatearJson(_BaseRepoGit):
    def test_determinista(self):
        maturity.project_init(self.repo, stage="experiment")
        lifecycle.lifecycle_init(self.repo)
        r1 = status.formatear_json(status.evaluar_status(self.repo))
        r2 = status.formatear_json(status.evaluar_status(self.repo))
        self.assertEqual(r1, r2)

    def test_serializable_sin_encoder_custom(self):
        maturity.project_init(self.repo, stage="experiment")
        lifecycle.lifecycle_init(self.repo)
        resultado = status.formatear_json(status.evaluar_status(self.repo))
        texto = json.dumps(resultado)
        self.assertIsInstance(texto, str)
        self.assertEqual(json.loads(texto), resultado)


# --- Output humano ---------------------------------------------------------

class TestFormatearTexto(_BaseRepoGit):
    def test_determinista(self):
        maturity.project_init(self.repo, stage="experiment")
        lifecycle.lifecycle_init(self.repo)
        resultado = status.evaluar_status(self.repo)
        t1 = status.formatear_texto(resultado)
        t2 = status.formatear_texto(resultado)
        self.assertEqual(t1, t2)

    def test_compacto_no_duplica_blocking_de_readiness_en_mlops(self):
        maturity.project_init(self.repo, stage="experiment")
        lifecycle.lifecycle_init(self.repo)
        maturity.calibrar(self.repo, "production_candidate", "avance de prueba")
        resultado = status.evaluar_status(self.repo)
        texto = status.formatear_texto(resultado, verbose=False)
        # El mensaje completo de un FAIL de readiness no debe repetirse
        # palabra por palabra en el bloque de mlops.production_readiness
        # (que ya resume con su propio detalle corto, R2 del brief).
        for r in resultado["readiness"]["blocking"]:
            ocurrencias = texto.count(r["message"])
            self.assertLessEqual(ocurrencias, 1)

    def test_verbose_muestra_mas_detalle_que_compacto(self):
        maturity.project_init(self.repo, stage="discovery")
        resultado = status.evaluar_status(self.repo)
        compacto = status.formatear_texto(resultado, verbose=False)
        detallado = status.formatear_texto(resultado, verbose=True)
        self.assertGreaterEqual(len(detallado), len(compacto))


# --- CLI: no colision / regresion (R1, AC "CLI / no colisión") ------------------

class _BaseCliRepo(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_repo_git_temporal(prefix="status_cli_test_")

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def _crear_change_minimo(self, change_id: str, estado: str = "en_implementacion") -> None:
        change_dir = self.repo / "openspec" / "changes" / change_id
        change_dir.mkdir(parents=True, exist_ok=True)
        (change_dir / "tasks.md").write_text(f"# Tareas\n\nestado: {estado}\n", encoding="utf-8")
        (change_dir / "control.json").write_text(
            json.dumps({"schema_version": 1, "transiciones": [], "alcance": {"rutas_autorizadas": []}}),
            encoding="utf-8",
        )
        _commitear_todo(self.repo, f"fixture: change {change_id}")

    def _correr(self, args: list) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(DS_GUARD), *args],
            cwd=str(self.repo),
            capture_output=True,
            text=True,
            encoding="utf-8",
        )


class TestCliNoColision(_BaseCliRepo):
    def test_status_con_change_id_comportamiento_exacto_preservado(self):
        self._crear_change_minimo("20260101-fixture")
        r1 = self._correr(["status", "--change-id", "20260101-fixture", "--json"])
        r2 = self._correr(["status", "--change-id", "20260101-fixture", "--json"])
        self.assertEqual(r1.returncode, 0)
        self.assertEqual(r1.stdout, r2.stdout)
        payload = json.loads(r1.stdout)
        self.assertEqual(payload["change_id"], "20260101-fixture")
        self.assertEqual(payload["estado"], "en_implementacion")

    def test_status_con_change_id_verbose_ignorado(self):
        self._crear_change_minimo("20260101-fixture")
        sin_verbose = self._correr(["status", "--change-id", "20260101-fixture", "--json"])
        con_verbose = self._correr(["status", "--change-id", "20260101-fixture", "--json", "--verbose"])
        self.assertEqual(sin_verbose.stdout, con_verbose.stdout)

    def test_status_sin_change_id_unificado_exit_0(self):
        resultado = self._correr(["status"])
        self.assertEqual(resultado.returncode, 0)

    def test_status_sin_change_id_json_valido(self):
        resultado = self._correr(["status", "--json"])
        self.assertEqual(resultado.returncode, 0)
        payload = json.loads(resultado.stdout)
        for clave in ("project", "installation", "alignment", "lifecycle", "mlops", "readiness", "harness"):
            self.assertIn(clave, payload)

    def test_status_sin_change_id_verbose_mas_detalle(self):
        compacto = self._correr(["status"])
        detallado = self._correr(["status", "--verbose"])
        self.assertEqual(compacto.returncode, 0)
        self.assertEqual(detallado.returncode, 0)
        self.assertGreaterEqual(len(detallado.stdout), len(compacto.stdout))


if __name__ == "__main__":
    unittest.main()

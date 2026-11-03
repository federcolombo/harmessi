"""Tests de `tools.dsguard.maturity` (Change 3, v0.3:
20260915-project-maturity-state-and-calibration) -- estado de
madurez/gobernanza del proyecto (`.harmessi/project.json`): project_stage +
risk_level, eje ortogonal al lifecycle CRISP-DM/KDD/MLOps
(`openspec/lifecycle/state.json`).

Sigue el mismo patrón de `test_lifecycle.py` (funciones puras/I/O sin git,
`_crear_dir_temporal`) y de `test_kdd.py` (integración CLI real vía
subprocess sobre un repo git temporal, `_crear_repo_git_temporal`/
`_correr_ds_guard`). Cubre todos los criterios de aceptación de `spec.md`
del change.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ORIGEN = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ORIGEN / "tools"))

from dsguard import kdd_compat, lifecycle, maturity  # noqa: E402

DS_GUARD = REPO_ORIGEN / "tools" / "ds_guard.py"


def _crear_dir_temporal(prefix: str = "maturity_test_") -> Path:
    return Path(tempfile.mkdtemp(prefix=prefix))


def _crear_repo_git_temporal() -> Path:
    repo = _crear_dir_temporal("maturity_cli_test_")
    subprocess.run(["git", "init", "-q"], cwd=str(repo), check=True)
    return repo


def _correr_ds_guard(args: list, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(DS_GUARD), *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


# --- project_init: los 7 casos -------------------------------------------------

class TestProjectInitSieteCasos(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_dir_temporal()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_sin_flags_default_experiment_explicit_init(self):
        estado, creado = maturity.project_init(self.repo)
        self.assertTrue(creado)
        self.assertEqual(estado["project_stage"], "experiment")
        self.assertEqual(estado["stage_history"][-1]["via"], "explicit_init")
        self.assertIsNone(estado["risk_level"])

    def test_stage_discovery_explicit_init(self):
        estado, creado = maturity.project_init(self.repo, stage="discovery")
        self.assertTrue(creado)
        self.assertEqual(estado["project_stage"], "discovery")
        self.assertEqual(estado["stage_history"][-1]["via"], "explicit_init")

    def test_stage_experiment_explicit_init(self):
        estado, creado = maturity.project_init(self.repo, stage="experiment")
        self.assertTrue(creado)
        self.assertEqual(estado["project_stage"], "experiment")
        self.assertEqual(estado["stage_history"][-1]["via"], "explicit_init")

    def test_stage_production_candidate_rechazado(self):
        with self.assertRaises(maturity.MaturityEstadoError):
            maturity.project_init(self.repo, stage="production_candidate")
        self.assertFalse(maturity.state_path(self.repo).exists())

    def test_stage_production_rechazado(self):
        with self.assertRaises(maturity.MaturityEstadoError):
            maturity.project_init(self.repo, stage="production")
        self.assertFalse(maturity.state_path(self.repo).exists())

    def test_adopt_sin_evidencia_discovery_migration_inference(self):
        estado, creado = maturity.project_init(self.repo, adopt=True)
        self.assertTrue(creado)
        self.assertEqual(estado["project_stage"], "discovery")
        self.assertEqual(estado["stage_history"][-1]["via"], "migration_inference")
        self.assertIn("No se detectó", estado["stage_history"][-1]["reason"])

    def test_adopt_con_lifecycle_existente_experiment_migration_inference(self):
        lifecycle.lifecycle_init(self.repo)
        estado, creado = maturity.project_init(self.repo, adopt=True)
        self.assertTrue(creado)
        self.assertEqual(estado["project_stage"], "experiment")
        self.assertEqual(estado["stage_history"][-1]["via"], "migration_inference")
        self.assertIn("openspec/lifecycle/state.json", estado["stage_history"][-1]["reason"])

    def test_adopt_con_legacy_kdd_existente_experiment_migration_inference(self):
        ruta_legacy = kdd_compat.state_path_legacy(self.repo)
        ruta_legacy.parent.mkdir(parents=True, exist_ok=True)
        ruta_legacy.write_text("{}", encoding="utf-8")
        estado, creado = maturity.project_init(self.repo, adopt=True)
        self.assertTrue(creado)
        self.assertEqual(estado["project_stage"], "experiment")
        self.assertEqual(estado["stage_history"][-1]["via"], "migration_inference")
        self.assertIn("kdd/state.json", estado["stage_history"][-1]["reason"])

    def test_stage_y_adopt_juntos_rechazado(self):
        with self.assertRaises(maturity.MaturityEstadoError):
            maturity.project_init(self.repo, stage="discovery", adopt=True)
        self.assertFalse(maturity.state_path(self.repo).exists())


# --- inferir_stage: función pura de existencia ---------------------------------

class TestInferirStage(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_dir_temporal()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_sin_evidencia_discovery(self):
        stage, reason = maturity.inferir_stage(self.repo)
        self.assertEqual(stage, "discovery")
        self.assertTrue(reason)

    def test_con_lifecycle_experiment(self):
        lifecycle.lifecycle_init(self.repo)
        stage, reason = maturity.inferir_stage(self.repo)
        self.assertEqual(stage, "experiment")
        self.assertIn("lifecycle/state.json", reason)


# --- Idempotencia, corrupción, schema, lectura/escritura ------------------------

class TestProjectInitIdempotenciaYCorrupcion(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_dir_temporal()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_init_es_idempotente_no_reescribe(self):
        estado1, creado1 = maturity.project_init(self.repo)
        bytes1 = maturity.state_path(self.repo).read_bytes()
        estado2, creado2 = maturity.project_init(self.repo, stage="discovery")
        bytes2 = maturity.state_path(self.repo).read_bytes()

        self.assertTrue(creado1)
        self.assertFalse(creado2)
        self.assertEqual(bytes1, bytes2)
        self.assertEqual(estado1, estado2)
        # El --stage pasado en la segunda llamada se ignora: sigue "experiment".
        self.assertEqual(estado2["project_stage"], "experiment")

    def test_init_no_pisa_archivo_corrupto(self):
        ruta = maturity.state_path(self.repo)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text("esto no es json valido", encoding="utf-8")
        antes = ruta.read_bytes()

        with self.assertRaises(maturity.MaturityEstadoError):
            maturity.project_init(self.repo)

        self.assertEqual(ruta.read_bytes(), antes)

    def test_schema_version_desconocida_levanta_con_mensaje_explicito(self):
        ruta = maturity.state_path(self.repo)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        datos = maturity.estado_inicial("experiment", "explicit_init", "x")
        datos["schema_version"] = 999
        ruta.write_text(json.dumps(datos), encoding="utf-8")

        with self.assertRaises(maturity.MaturityEstadoError) as ctx:
            maturity.leer_estado(ruta)
        mensaje = str(ctx.exception)
        self.assertIn("999", mensaje)
        self.assertIn(str(maturity.SCHEMA_VERSION_SOPORTADA), mensaje)

    def test_lectura_no_muta_archivo_en_disco(self):
        maturity.project_init(self.repo)
        ruta = maturity.state_path(self.repo)
        bytes_antes = ruta.read_bytes()
        maturity.leer_estado(ruta)
        maturity.leer_estado(ruta)
        bytes_despues = ruta.read_bytes()
        self.assertEqual(bytes_antes, bytes_despues)

    def test_archivo_ausente_levanta_filenotfound(self):
        with self.assertRaises(FileNotFoundError):
            maturity.leer_estado(maturity.state_path(self.repo))

    def test_escritura_atomica_no_deja_temporal_residual(self):
        estado = maturity.estado_inicial("experiment", "explicit_init", "x")
        maturity.escribir_estado(self.repo, estado)
        ruta = maturity.state_path(self.repo)
        self.assertTrue(ruta.exists())
        tmp = ruta.parent / (ruta.name + ".tmp")
        self.assertFalse(tmp.exists())

    def test_round_trip_escribir_leer_estructuras_iguales(self):
        estado = maturity.estado_inicial("discovery", "explicit_init", "x")
        maturity.escribir_estado(self.repo, estado)
        releido = maturity.leer_estado(maturity.state_path(self.repo))
        self.assertEqual(estado, releido)

    def test_validar_estructura_rechaza_risk_status_persistido(self):
        datos = maturity.estado_inicial("experiment", "explicit_init", "x")
        datos["risk_status"] = "unclassified"
        with self.assertRaises(maturity.MaturityEstadoError):
            maturity.validar_estructura(datos)

    def test_validar_estructura_rechaza_project_stage_invalido(self):
        datos = maturity.estado_inicial("experiment", "explicit_init", "x")
        datos["project_stage"] = "algo_inventado"
        with self.assertRaises(maturity.MaturityEstadoError):
            maturity.validar_estructura(datos)

    def test_validar_estructura_rechaza_risk_level_invalido(self):
        datos = maturity.estado_inicial("experiment", "explicit_init", "x")
        datos["risk_level"] = "extreme"
        with self.assertRaises(maturity.MaturityEstadoError):
            maturity.validar_estructura(datos)


# --- calibrar --------------------------------------------------------------

class TestCalibrar(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_dir_temporal()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_sin_project_json_previo_error_pidiendo_init(self):
        with self.assertRaises(maturity.MaturityEstadoError) as ctx:
            maturity.calibrar(self.repo, "production", "adoptamos este proyecto")
        self.assertIn("project init", str(ctx.exception))

    def test_sin_reason_rechazado(self):
        maturity.project_init(self.repo)
        with self.assertRaises(maturity.MaturityEstadoError):
            maturity.calibrar(self.repo, "production", "")

    def test_caso_exitoso(self):
        maturity.project_init(self.repo)
        estado = maturity.calibrar(self.repo, "production", "adoptamos este proyecto que ya está en prod")
        self.assertEqual(estado["project_stage"], "production")
        ultima = estado["stage_history"][-1]
        self.assertEqual(ultima["via"], "calibrate")
        self.assertEqual(ultima["reason"], "adoptamos este proyecto que ya está en prod")
        self.assertEqual(ultima["from"], "experiment")

    def test_recalibracion_multiple_sin_promote_incluso_hacia_abajo(self):
        maturity.project_init(self.repo)
        maturity.calibrar(self.repo, "production", "r1")
        estado = maturity.calibrar(self.repo, "discovery", "r2 -- bajamos de nuevo, sin promote todavia")
        self.assertEqual(estado["project_stage"], "discovery")
        self.assertEqual(len(estado["stage_history"]), 3)
        self.assertEqual(estado["stage_history"][-1]["from"], "production")

    def test_rechazo_con_promote_ya_en_historial(self):
        maturity.project_init(self.repo)
        ruta = maturity.state_path(self.repo)
        estado = maturity.leer_estado(ruta)
        estado["stage_history"].append(
            {"from": "experiment", "to": "production", "via": "promote", "reason": "promocion simulada", "utc": "2026-01-01T00:00:00Z"}
        )
        maturity.escribir_estado(self.repo, estado)

        with self.assertRaises(maturity.MaturityEstadoError) as ctx:
            maturity.calibrar(self.repo, "discovery", "intento de bypass")
        self.assertIn("promote", str(ctx.exception))


# --- set_risk ----------------------------------------------------------------

class TestSetRisk(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_dir_temporal()
        maturity.project_init(self.repo)

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_primera_clasificacion(self):
        estado = maturity.set_risk(self.repo, "medium", "primera clasificación")
        self.assertEqual(estado["risk_level"], "medium")
        self.assertEqual(len(estado["risk_history"]), 1)
        self.assertIsNone(estado["risk_history"][0]["from"])
        self.assertEqual(estado["risk_history"][0]["via"], "explicit")

    def test_cambio_posterior_preserva_historial(self):
        maturity.set_risk(self.repo, "medium", "primera clasificación")
        estado = maturity.set_risk(self.repo, "high", "reclasificación tras hallazgo de PII")
        self.assertEqual(estado["risk_level"], "high")
        self.assertEqual(len(estado["risk_history"]), 2)
        self.assertEqual(estado["risk_history"][0]["to"], "medium")
        self.assertEqual(estado["risk_history"][1]["from"], "medium")
        self.assertEqual(estado["risk_history"][1]["to"], "high")

    def test_valor_invalido_rechazado(self):
        with self.assertRaises(maturity.MaturityEstadoError):
            maturity.set_risk(self.repo, "extreme", "motivo")

    def test_reason_faltante_rechazado(self):
        with self.assertRaises(maturity.MaturityEstadoError):
            maturity.set_risk(self.repo, "low", "")

    def test_sin_project_json_previo_error(self):
        otro_repo = _crear_dir_temporal()
        try:
            with self.assertRaises(maturity.MaturityEstadoError):
                maturity.set_risk(otro_repo, "low", "motivo")
        finally:
            shutil.rmtree(otro_repo, ignore_errors=True)


# --- estado_riesgo: función pura -----------------------------------------------

class TestEstadoRiesgo(unittest.TestCase):
    def test_none_es_unclassified(self):
        self.assertEqual(maturity.estado_riesgo({"risk_level": None}), "unclassified")

    def test_valor_es_classified(self):
        self.assertEqual(maturity.estado_riesgo({"risk_level": "low"}), "classified")


# --- project_status ------------------------------------------------------------

class TestProjectStatus(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_dir_temporal()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_status_solo_lectura_no_muta(self):
        maturity.project_init(self.repo)
        maturity.set_risk(self.repo, "low", "clasificacion inicial")
        ruta = maturity.state_path(self.repo)
        bytes_antes = ruta.read_bytes()

        payload = maturity.project_status(self.repo)

        self.assertEqual(ruta.read_bytes(), bytes_antes)
        self.assertEqual(payload["project_stage"], "experiment")
        self.assertEqual(payload["risk_level"], "low")
        self.assertEqual(payload["risk_status"], "classified")
        self.assertEqual(payload["origen_stage"]["via"], "explicit_init")
        self.assertEqual(len(payload["stage_history"]), 1)
        self.assertEqual(len(payload["risk_history"]), 1)


# --- Separación de responsabilidades: maturity <-> lifecycle -------------------

class TestSeparacionDeResponsabilidades(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_dir_temporal()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_operaciones_de_maturity_no_mutan_lifecycle_state(self):
        lifecycle.lifecycle_init(self.repo)
        ruta_lifecycle = lifecycle.state_path(self.repo)
        bytes_antes = ruta_lifecycle.read_bytes()

        maturity.project_init(self.repo, adopt=True)
        maturity.set_risk(self.repo, "medium", "motivo")
        maturity.calibrar(self.repo, "production", "motivo calibrate")

        self.assertEqual(ruta_lifecycle.read_bytes(), bytes_antes)

    def test_operaciones_de_lifecycle_no_mutan_project_json(self):
        maturity.project_init(self.repo)
        ruta_project = maturity.state_path(self.repo)
        bytes_antes = ruta_project.read_bytes()

        lifecycle.lifecycle_init(self.repo)
        estado = lifecycle.leer_estado(lifecycle.state_path(self.repo))
        estado["crispdm"]["fases"]["modeling"]["estado"] = "en_progreso"
        lifecycle.escribir_estado(self.repo, estado)

        self.assertEqual(ruta_project.read_bytes(), bytes_antes)


# --- CLI real ------------------------------------------------------------------

class TestCliProject(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_repo_git_temporal()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_project_init_cli_sin_flags(self):
        resultado = _correr_ds_guard(["project", "init", "--json"], self.repo)
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertTrue((self.repo / ".harmessi" / "project.json").exists())
        payload = json.loads(resultado.stdout)
        self.assertTrue(payload["creado"])
        self.assertEqual(payload["estado"]["project_stage"], "experiment")

        estado_directo = maturity.leer_estado(maturity.state_path(self.repo))
        self.assertEqual(estado_directo["project_stage"], "experiment")

    def test_project_init_cli_stage_y_adopt_juntos_rechazado_por_argparse(self):
        resultado = _correr_ds_guard(["project", "init", "--stage", "discovery", "--adopt"], self.repo)
        self.assertNotEqual(resultado.returncode, 0)
        self.assertFalse((self.repo / ".harmessi" / "project.json").exists())

    def test_project_status_cli_coincide_con_funcion_directa(self):
        _correr_ds_guard(["project", "init", "--stage", "discovery"], self.repo)
        resultado = _correr_ds_guard(["project", "status", "--json"], self.repo)
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        payload_cli = json.loads(resultado.stdout)
        payload_directo = maturity.project_status(self.repo)
        self.assertEqual(payload_cli["project_stage"], payload_directo["project_stage"])
        self.assertEqual(payload_cli["risk_status"], payload_directo["risk_status"])

    def test_project_status_cli_sin_project_json_da_error_claro(self):
        resultado = _correr_ds_guard(["project", "status"], self.repo)
        self.assertEqual(resultado.returncode, 2)
        self.assertIn("project init", resultado.stderr)

    def test_project_calibrate_y_set_risk_cli(self):
        _correr_ds_guard(["project", "init"], self.repo)
        resultado_cal = _correr_ds_guard(
            ["project", "calibrate", "--stage", "production", "--reason", "adopcion real", "--json"], self.repo
        )
        self.assertEqual(resultado_cal.returncode, 0, resultado_cal.stderr)

        resultado_risk = _correr_ds_guard(
            ["project", "set-risk", "high", "--reason", "PII detectado", "--json"], self.repo
        )
        self.assertEqual(resultado_risk.returncode, 0, resultado_risk.stderr)

        estado = maturity.leer_estado(maturity.state_path(self.repo))
        self.assertEqual(estado["project_stage"], "production")
        self.assertEqual(estado["risk_level"], "high")


if __name__ == "__main__":
    unittest.main()

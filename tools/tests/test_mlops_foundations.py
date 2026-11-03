"""Tests de `tools.dsguard.mlops_foundations` (Change 5, v0.3:
20260915-mlops-foundations-experiment) -- fundamentos MLOps
(reproducibilidad/versionado/lineage/artifacts) activos desde
project_stage=experiment, medidos con el motor neutral de checks
(`checks.py`) y expuestos vía `ds_guard mlops status/record`.

Sigue el mismo patrón de `test_maturity.py`/`test_kdd.py`: funciones puras se
llaman directo sobre un repo git temporal propio (`_crear_repo_git_temporal`,
necesario porque `check_reproducibilidad`/`check_versionado` usan
`repo.get_head`/`repo.list_dirty_files`, que requieren un repo Git real); la
integración CLI real corre `tools/ds_guard.py` como subproceso. Nunca usa
este repositorio real como fixture.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ORIGEN = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ORIGEN / "tools"))

from dsguard import checks, lifecycle, maturity, mlops_foundations  # noqa: E402

DS_GUARD = REPO_ORIGEN / "tools" / "ds_guard.py"


def _crear_repo_git_temporal(prefix: str = "mlops_foundations_test_") -> Path:
    """Repo git temporal con un commit inicial (README) -- working tree
    limpio por default, para que `check_reproducibilidad`/`check_versionado`
    (que llaman `repo.get_head`) tengan un HEAD real."""
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


def _crear_lockfile(repo: Path) -> None:
    (repo / "requirements-lock.txt").write_text("pandas==2.0.0\n", encoding="utf-8")


def _crear_profile(repo: Path, dataset_id: str = "ds1") -> None:
    profile_dir = repo / ".harmessi" / "profiles" / dataset_id
    profile_dir.mkdir(parents=True, exist_ok=True)
    (profile_dir / "profile.json").write_text(
        json.dumps({"fingerprint": "sha256/bin/v1:abc"}), encoding="utf-8"
    )


def _crear_data_con_contenido(repo: Path) -> None:
    data_dir = repo / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "algo.csv").write_text("a,b\n1,2\n", encoding="utf-8")


def _ensuciar_tree(repo: Path) -> None:
    (repo / "sucio.txt").write_text("cambio sin confirmar\n", encoding="utf-8")


def _commitear_todo(repo: Path, mensaje: str = "fixture") -> None:
    """Confirma todos los cambios pendientes -- deja el working tree limpio
    (necesario para que `check_reproducibilidad`, que usa
    `repo.list_dirty_files`, no reporte WARN por archivos de fixture sin
    confirmar)."""
    subprocess.run(["git", "add", "-A"], cwd=str(repo), check=True)
    subprocess.run(["git", "commit", "-q", "-m", mensaje], cwd=str(repo), check=True)


class _BaseRepoGit(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_repo_git_temporal()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)


# --- Resolución de project_stage (4 casos) ------------------------------------

class TestResolucionProjectStage(_BaseRepoGit):
    def test_project_json_ausente_da_na_informativo_y_4_capabilities_na(self):
        resultados = mlops_foundations.evaluar_foundations(self.repo)
        self.assertEqual(len(resultados), 5)
        stage_result = resultados[0]
        self.assertEqual(stage_result.status, checks.STATUS_NA)
        self.assertEqual(stage_result.code, mlops_foundations.CODIGO_PROJECT_STAGE)
        self.assertIn("project init", stage_result.message)
        for r in resultados[1:]:
            self.assertEqual(r.status, checks.STATUS_NA)
            self.assertIn("project init", r.message)

    def test_project_stage_discovery_da_4_capabilities_na_mensaje_distinto(self):
        maturity.project_init(self.repo, stage="discovery")
        resultados = mlops_foundations.evaluar_foundations(self.repo)
        stage_result = resultados[0]
        self.assertEqual(stage_result.status, checks.STATUS_PASS)
        self.assertEqual(stage_result.subject, "discovery")
        for r in resultados[1:]:
            self.assertEqual(r.status, checks.STATUS_NA)
            self.assertIn("discovery", r.message)
            self.assertNotIn("project init", r.message)

    def test_project_json_corrupto_da_technical_error_informativo(self):
        ruta = maturity.state_path(self.repo)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text("esto no es json valido", encoding="utf-8")
        resultados = mlops_foundations.evaluar_foundations(self.repo)
        stage_result = resultados[0]
        self.assertEqual(stage_result.status, checks.STATUS_FAIL)
        self.assertEqual(stage_result.kind, checks.KIND_TECHNICAL_ERROR)
        # Con project_stage no resuelto (None), los 4 checks de capability
        # deben degradarse igual que "ausente" (None), nunca crashear.
        for r in resultados[1:]:
            self.assertEqual(r.status, checks.STATUS_NA)

    def test_project_stage_valido_no_discovery_evalua_de_verdad(self):
        maturity.project_init(self.repo, stage="experiment")
        # check_lineage da N/A por diseño mientras openspec/lifecycle/state.json
        # no exista (independiente del project_stage) -- lifecycle_init acá
        # asegura que las 4 capabilities evalúen de verdad, que es la intención
        # del test.
        lifecycle.lifecycle_init(self.repo)
        resultados = mlops_foundations.evaluar_foundations(self.repo)
        stage_result = resultados[0]
        self.assertEqual(stage_result.status, checks.STATUS_PASS)
        self.assertEqual(stage_result.subject, "experiment")
        for r in resultados[1:]:
            self.assertNotEqual(r.status, checks.STATUS_NA)


# --- check_reproducibilidad ---------------------------------------------------

class TestCheckReproducibilidad(_BaseRepoGit):
    def test_todo_en_regla_pass(self):
        _crear_lockfile(self.repo)
        _commitear_todo(self.repo)
        resultado = mlops_foundations.check_reproducibilidad(self.repo, "experiment")
        self.assertEqual(len(resultado), 1)
        self.assertEqual(resultado[0].status, checks.STATUS_PASS)
        self.assertEqual(resultado[0].code, mlops_foundations.CODIGO_REPRODUCIBILIDAD)

    def test_sin_data_sin_lockfile_warn_menciona_lockfile(self):
        resultado = mlops_foundations.check_reproducibilidad(self.repo, "experiment")[0]
        self.assertEqual(resultado.status, checks.STATUS_WARN)
        self.assertIn("lockfile", resultado.message)

    def test_working_tree_sucio_warn(self):
        _crear_lockfile(self.repo)
        _ensuciar_tree(self.repo)
        resultado = mlops_foundations.check_reproducibilidad(self.repo, "experiment")[0]
        self.assertEqual(resultado.status, checks.STATUS_WARN)
        self.assertIn("working tree", resultado.message)

    def test_data_sin_fingerprint_warn(self):
        _crear_lockfile(self.repo)
        _crear_data_con_contenido(self.repo)
        resultado = mlops_foundations.check_reproducibilidad(self.repo, "experiment")[0]
        self.assertEqual(resultado.status, checks.STATUS_WARN)
        self.assertIn("fingerprint", resultado.message)

    def test_data_con_fingerprint_y_lockfile_pass(self):
        _crear_lockfile(self.repo)
        _crear_data_con_contenido(self.repo)
        _crear_profile(self.repo)
        _commitear_todo(self.repo)
        resultado = mlops_foundations.check_reproducibilidad(self.repo, "experiment")[0]
        self.assertEqual(resultado.status, checks.STATUS_PASS)

    def test_combinacion_multiples_problemas_todos_mencionados(self):
        _crear_data_con_contenido(self.repo)
        _ensuciar_tree(self.repo)
        resultado = mlops_foundations.check_reproducibilidad(self.repo, "experiment")[0]
        self.assertEqual(resultado.status, checks.STATUS_WARN)
        self.assertIn("working tree", resultado.message)
        self.assertIn("fingerprint", resultado.message)
        self.assertIn("lockfile", resultado.message)

    def test_na_por_discovery(self):
        resultado = mlops_foundations.check_reproducibilidad(self.repo, "discovery")[0]
        self.assertEqual(resultado.status, checks.STATUS_NA)

    def test_na_por_stage_none(self):
        resultado = mlops_foundations.check_reproducibilidad(self.repo, None)[0]
        self.assertEqual(resultado.status, checks.STATUS_NA)


# --- check_versionado -----------------------------------------------------------

class TestCheckVersionado(_BaseRepoGit):
    def test_sin_data_pass(self):
        resultado = mlops_foundations.check_versionado(self.repo, "experiment")[0]
        self.assertEqual(resultado.status, checks.STATUS_PASS)
        self.assertIn("no hay data/", resultado.message)

    def test_con_data_y_fingerprint_pass(self):
        _crear_data_con_contenido(self.repo)
        _crear_profile(self.repo)
        resultado = mlops_foundations.check_versionado(self.repo, "experiment")[0]
        self.assertEqual(resultado.status, checks.STATUS_PASS)
        self.assertIn("fingerprint registrado", resultado.message)

    def test_con_data_sin_fingerprint_warn(self):
        _crear_data_con_contenido(self.repo)
        resultado = mlops_foundations.check_versionado(self.repo, "experiment")[0]
        self.assertEqual(resultado.status, checks.STATUS_WARN)

    def test_na_por_discovery(self):
        resultado = mlops_foundations.check_versionado(self.repo, "discovery")[0]
        self.assertEqual(resultado.status, checks.STATUS_NA)


# --- check_lineage: NUNCA PASS -------------------------------------------------

class TestCheckLineage(_BaseRepoGit):
    def test_sin_lifecycle_na(self):
        resultado = mlops_foundations.check_lineage(self.repo, "experiment")[0]
        self.assertEqual(resultado.status, checks.STATUS_NA)

    def test_con_lifecycle_sin_evidencia_warn(self):
        lifecycle.lifecycle_init(self.repo)
        resultado = mlops_foundations.check_lineage(self.repo, "experiment")[0]
        self.assertEqual(resultado.status, checks.STATUS_WARN)
        self.assertIn("Sin evidencia indirecta", resultado.message)

    def test_con_lifecycle_y_evidencia_kdd_sigue_warn(self):
        lifecycle.lifecycle_init(self.repo)
        estado = lifecycle.leer_estado(lifecycle.state_path(self.repo))
        estado["kdd"]["pasos"]["selection"]["changes"] = ["20260101-x"]
        lifecycle.escribir_estado(self.repo, estado)
        resultado = mlops_foundations.check_lineage(self.repo, "experiment")[0]
        self.assertEqual(resultado.status, checks.STATUS_WARN)
        self.assertIn("selection", resultado.message)

    def test_na_por_discovery(self):
        lifecycle.lifecycle_init(self.repo)
        resultado = mlops_foundations.check_lineage(self.repo, "discovery")[0]
        self.assertEqual(resultado.status, checks.STATUS_NA)

    def test_nunca_pass_bajo_ningun_fixture_probado(self):
        fixtures_status = []

        # Sin lifecycle.
        fixtures_status.append(mlops_foundations.check_lineage(self.repo, "experiment")[0].status)

        # Con lifecycle, sin evidencia.
        lifecycle.lifecycle_init(self.repo)
        fixtures_status.append(mlops_foundations.check_lineage(self.repo, "experiment")[0].status)

        # Con lifecycle, con evidencia (changes) en varios pasos.
        estado = lifecycle.leer_estado(lifecycle.state_path(self.repo))
        for paso in ("selection", "preprocessing", "data_mining"):
            estado["kdd"]["pasos"][paso]["changes"] = ["c1"]
        lifecycle.escribir_estado(self.repo, estado)
        fixtures_status.append(mlops_foundations.check_lineage(self.repo, "experiment")[0].status)

        # Con lifecycle, con evidencia (evidencia[]) también.
        estado = lifecycle.leer_estado(lifecycle.state_path(self.repo))
        estado["kdd"]["pasos"]["transformation"]["evidencia"] = [{"change_id": "c2", "artefacto": "x"}]
        lifecycle.escribir_estado(self.repo, estado)
        fixtures_status.append(mlops_foundations.check_lineage(self.repo, "experiment")[0].status)

        # discovery / stage None (N/A, no PASS tampoco).
        fixtures_status.append(mlops_foundations.check_lineage(self.repo, "discovery")[0].status)
        fixtures_status.append(mlops_foundations.check_lineage(self.repo, None)[0].status)

        self.assertNotIn(checks.STATUS_PASS, fixtures_status)


# --- check_artifacts -------------------------------------------------------------

class TestCheckArtifacts(_BaseRepoGit):
    def test_nada_presente_warn(self):
        resultado = mlops_foundations.check_artifacts(self.repo, "experiment")[0]
        self.assertEqual(resultado.status, checks.STATUS_WARN)

    def test_profile_presente_pass(self):
        _crear_profile(self.repo)
        resultado = mlops_foundations.check_artifacts(self.repo, "experiment")[0]
        self.assertEqual(resultado.status, checks.STATUS_PASS)
        self.assertIn("profile", resultado.message)

    def test_models_con_contenido_pass(self):
        (self.repo / "models").mkdir()
        (self.repo / "models" / "modelo.pkl").write_bytes(b"x")
        resultado = mlops_foundations.check_artifacts(self.repo, "experiment")[0]
        self.assertEqual(resultado.status, checks.STATUS_PASS)
        self.assertIn("models/", resultado.message)

    def test_reports_con_contenido_pass(self):
        (self.repo / "reports").mkdir()
        (self.repo / "reports" / "informe.md").write_text("x", encoding="utf-8")
        resultado = mlops_foundations.check_artifacts(self.repo, "experiment")[0]
        self.assertEqual(resultado.status, checks.STATUS_PASS)
        self.assertIn("reports/", resultado.message)

    def test_directorio_vacio_no_cuenta_como_contenido(self):
        (self.repo / "models").mkdir()
        resultado = mlops_foundations.check_artifacts(self.repo, "experiment")[0]
        self.assertEqual(resultado.status, checks.STATUS_WARN)

    def test_na_por_discovery(self):
        resultado = mlops_foundations.check_artifacts(self.repo, "discovery")[0]
        self.assertEqual(resultado.status, checks.STATUS_NA)


# --- evaluar_foundations: read-only ---------------------------------------------

class TestEvaluarFoundationsReadOnly(_BaseRepoGit):
    def _bytes_o_none(self, ruta: Path):
        return ruta.read_bytes() if ruta.exists() else None

    def _assert_no_muta(self):
        ruta_lifecycle = lifecycle.state_path(self.repo)
        ruta_project = maturity.state_path(self.repo)
        antes_lifecycle = self._bytes_o_none(ruta_lifecycle)
        antes_project = self._bytes_o_none(ruta_project)

        mlops_foundations.evaluar_foundations(self.repo)

        self.assertEqual(self._bytes_o_none(ruta_lifecycle), antes_lifecycle)
        self.assertEqual(self._bytes_o_none(ruta_project), antes_project)

    def test_sin_nada_no_muta(self):
        self._assert_no_muta()

    def test_con_project_json_no_muta(self):
        maturity.project_init(self.repo, stage="experiment")
        self._assert_no_muta()

    def test_con_lifecycle_y_project_no_muta(self):
        maturity.project_init(self.repo, stage="experiment")
        lifecycle.lifecycle_init(self.repo)
        self._assert_no_muta()

    def test_con_project_json_corrupto_no_muta(self):
        ruta = maturity.state_path(self.repo)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text("no es json", encoding="utf-8")
        self._assert_no_muta()

    def test_con_discovery_no_muta(self):
        maturity.project_init(self.repo, stage="discovery")
        self._assert_no_muta()

    def test_devuelve_5_resultados_en_orden(self):
        maturity.project_init(self.repo, stage="experiment")
        resultados = mlops_foundations.evaluar_foundations(self.repo)
        self.assertEqual(
            [r.code for r in resultados],
            [
                mlops_foundations.CODIGO_PROJECT_STAGE,
                mlops_foundations.CODIGO_REPRODUCIBILIDAD,
                mlops_foundations.CODIGO_VERSIONADO,
                mlops_foundations.CODIGO_LINEAGE,
                mlops_foundations.CODIGO_ARTIFACTS,
            ],
        )


# --- evaluar_foundations: no frena ante excepción de un check individual --------

class TestEvaluarFoundationsNoShortCircuit(_BaseRepoGit):
    def test_excepcion_en_un_check_no_detiene_los_demas(self):
        maturity.project_init(self.repo, stage="experiment")
        with mock.patch.object(
            mlops_foundations, "check_versionado", side_effect=RuntimeError("boom")
        ):
            resultados = mlops_foundations.evaluar_foundations(self.repo)

        self.assertEqual(len(resultados), 5)
        por_codigo = {r.code: r for r in resultados if r.kind != checks.KIND_TECHNICAL_ERROR}
        # reproducibilidad, lineage, artifacts (los otros 3) siguen presentes con su código real.
        self.assertIn(mlops_foundations.CODIGO_REPRODUCIBILIDAD, por_codigo)
        self.assertIn(mlops_foundations.CODIGO_LINEAGE, por_codigo)
        self.assertIn(mlops_foundations.CODIGO_ARTIFACTS, por_codigo)

        # El resultado de versionado se reemplaza por un technical_error, nunca crashea.
        errores_tecnicos = [r for r in resultados if r.kind == checks.KIND_TECHNICAL_ERROR]
        self.assertEqual(len(errores_tecnicos), 1)
        self.assertEqual(errores_tecnicos[0].status, checks.STATUS_FAIL)
        self.assertIn(mlops_foundations.CODIGO_VERSIONADO, errores_tecnicos[0].code)


# --- registrar_evidencia ---------------------------------------------------------

class TestRegistrarEvidencia(_BaseRepoGit):
    def setUp(self):
        super().setUp()
        maturity.project_init(self.repo, stage="experiment")
        lifecycle.lifecycle_init(self.repo)

    def test_requiere_lifecycle_existente(self):
        otro_repo = _crear_repo_git_temporal()
        try:
            maturity.project_init(otro_repo, stage="experiment")
            resultados = mlops_foundations.evaluar_foundations(otro_repo)
            with self.assertRaises(FileNotFoundError):
                mlops_foundations.registrar_evidencia(otro_repo, resultados)
        finally:
            shutil.rmtree(otro_repo, ignore_errors=True)

    def test_agrega_snapshot_a_las_4_capabilities(self):
        resultados = mlops_foundations.evaluar_foundations(self.repo)
        resultado_registro = mlops_foundations.registrar_evidencia(self.repo, resultados)

        self.assertTrue(resultado_registro["registrado"])
        self.assertEqual(
            set(resultado_registro["capacidades_actualizadas"]),
            {"reproducibilidad", "versionado", "lineage", "artifacts"},
        )

        estado = lifecycle.leer_estado(lifecycle.state_path(self.repo))
        for cap in ("reproducibilidad", "versionado", "lineage", "artifacts"):
            entrada = estado["mlops"]["foundations"][cap]
            self.assertEqual(len(entrada["evidencia"]), 1)
            snapshot = entrada["evidencia"][0]
            self.assertEqual(snapshot["tipo"], "check_snapshot")
            self.assertIn("status", snapshot)
            self.assertIn("kind", snapshot)
            self.assertIn("message", snapshot)
            self.assertIn("utc", snapshot)

    def test_nunca_toca_estado(self):
        estado_antes = lifecycle.leer_estado(lifecycle.state_path(self.repo))
        estados_capability_antes = {
            cap: estado_antes["mlops"]["foundations"][cap]["estado"]
            for cap in ("reproducibilidad", "versionado", "lineage", "artifacts")
        }

        resultados = mlops_foundations.evaluar_foundations(self.repo)
        mlops_foundations.registrar_evidencia(self.repo, resultados)

        estado_despues = lifecycle.leer_estado(lifecycle.state_path(self.repo))
        for cap in ("reproducibilidad", "versionado", "lineage", "artifacts"):
            self.assertEqual(estado_despues["mlops"]["foundations"][cap]["estado"], estados_capability_antes[cap])

    def test_ignora_project_stage_informativo(self):
        resultados = mlops_foundations.evaluar_foundations(self.repo)
        resultado_registro = mlops_foundations.registrar_evidencia(self.repo, resultados)
        # MLOPS-FOUNDATIONS-PROJECT-STAGE no tiene slot en mlops.foundations
        # -- exactamente 4 capacidades actualizadas, nunca una quinta.
        self.assertEqual(len(resultado_registro["capacidades_actualizadas"]), 4)

    def test_dos_llamadas_seguidas_agregan_dos_entradas_sin_fallar(self):
        resultados = mlops_foundations.evaluar_foundations(self.repo)
        mlops_foundations.registrar_evidencia(self.repo, resultados)
        mlops_foundations.registrar_evidencia(self.repo, resultados)

        estado = lifecycle.leer_estado(lifecycle.state_path(self.repo))
        for cap in ("reproducibilidad", "versionado", "lineage", "artifacts"):
            self.assertEqual(len(estado["mlops"]["foundations"][cap]["evidencia"]), 2)

    def test_escritura_atomica_no_deja_temporal_residual(self):
        resultados = mlops_foundations.evaluar_foundations(self.repo)
        mlops_foundations.registrar_evidencia(self.repo, resultados)
        ruta = lifecycle.state_path(self.repo)
        tmp = ruta.parent / (ruta.name + ".tmp")
        self.assertFalse(tmp.exists())

    def test_excepcion_en_un_check_igual_registra_snapshot_technical_error(self):
        """Gap encontrado por el reviewer: un check con code
        "{codigo_base}-EXCEPCION" (ver checks.ejecutar_checks) tiene que
        seguir mapeando a su capability real en registrar_evidencia -- antes
        del fix, `_CODE_A_CAPABILITY.get(r.code)` no matcheaba ese código y
        la capability quedaba sin snapshot, silenciosamente."""
        with mock.patch.object(
            mlops_foundations, "check_versionado", side_effect=RuntimeError("boom")
        ):
            resultados = mlops_foundations.evaluar_foundations(self.repo)

        errores_tecnicos = [r for r in resultados if r.kind == checks.KIND_TECHNICAL_ERROR]
        self.assertEqual(len(errores_tecnicos), 1)
        self.assertTrue(errores_tecnicos[0].code.startswith(mlops_foundations.CODIGO_VERSIONADO))
        self.assertTrue(errores_tecnicos[0].code.endswith("-EXCEPCION"))

        resultado_registro = mlops_foundations.registrar_evidencia(self.repo, resultados)

        # Las 4 capabilities siguen actualizadas, incluida "versionado" pese a la excepción.
        self.assertEqual(
            set(resultado_registro["capacidades_actualizadas"]),
            {"reproducibilidad", "versionado", "lineage", "artifacts"},
        )

        estado = lifecycle.leer_estado(lifecycle.state_path(self.repo))
        snapshot_versionado = estado["mlops"]["foundations"]["versionado"]["evidencia"][0]
        self.assertEqual(snapshot_versionado["tipo"], "check_snapshot")
        self.assertEqual(snapshot_versionado["kind"], checks.KIND_TECHNICAL_ERROR)
        self.assertEqual(snapshot_versionado["status"], checks.STATUS_FAIL)


# --- CLI real --------------------------------------------------------------------

class TestCliMlops(_BaseRepoGit):
    def test_mlops_status_sin_project_json_exit_0_todo_na(self):
        resultado = _correr_ds_guard(["mlops", "status", "--json"], self.repo)
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        payload = json.loads(resultado.stdout)
        self.assertEqual(len(payload), 5)
        for entrada in payload:
            self.assertEqual(entrada["status"], "N/A")
        # status nunca escribe project.json ni lifecycle/state.json.
        self.assertFalse((self.repo / ".harmessi" / "project.json").exists())
        self.assertFalse(lifecycle.state_path(self.repo).exists())

    def test_mlops_status_con_experiment_evalua_de_verdad(self):
        _correr_ds_guard(["project", "init", "--stage", "experiment"], self.repo)
        # check_lineage da N/A por diseño mientras openspec/lifecycle/state.json
        # no exista (independiente del project_stage); no hay subcomando CLI
        # "lifecycle init" (solo "migrate"), así que lo armamos directo --
        # mismo patrón que test_mlops_record_con_lifecycle_persiste_evidencia.
        lifecycle.lifecycle_init(self.repo)
        resultado = _correr_ds_guard(["mlops", "status", "--json"], self.repo)
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        payload = json.loads(resultado.stdout)
        capability_codes = {
            mlops_foundations.CODIGO_REPRODUCIBILIDAD,
            mlops_foundations.CODIGO_VERSIONADO,
            mlops_foundations.CODIGO_LINEAGE,
            mlops_foundations.CODIGO_ARTIFACTS,
        }
        for entrada in payload:
            if entrada["code"] in capability_codes:
                self.assertNotEqual(entrada["status"], "N/A")

    def test_mlops_record_sin_lifecycle_error_claro_exit_2(self):
        _correr_ds_guard(["project", "init", "--stage", "experiment"], self.repo)
        resultado = _correr_ds_guard(["mlops", "record"], self.repo)
        self.assertEqual(resultado.returncode, 2)
        self.assertIn("lifecycle", resultado.stderr)

    def test_mlops_record_con_lifecycle_persiste_evidencia(self):
        _correr_ds_guard(["project", "init", "--stage", "experiment"], self.repo)
        _correr_ds_guard(["lifecycle", "migrate"], self.repo)
        # No hay legacy que migrar -- forzamos lifecycle_init directo (mismo
        # efecto de tener state.json presente antes de 'record').
        lifecycle.lifecycle_init(self.repo)

        resultado = _correr_ds_guard(["mlops", "record", "--json"], self.repo)
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        payload = json.loads(resultado.stdout)
        self.assertTrue(payload["registrado"])
        self.assertEqual(
            set(payload["capacidades_actualizadas"]),
            {"reproducibilidad", "versionado", "lineage", "artifacts"},
        )

        estado = lifecycle.leer_estado(lifecycle.state_path(self.repo))
        for cap in ("reproducibilidad", "versionado", "lineage", "artifacts"):
            self.assertEqual(len(estado["mlops"]["foundations"][cap]["evidencia"]), 1)


if __name__ == "__main__":
    unittest.main()

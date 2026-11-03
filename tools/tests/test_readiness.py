"""Tests de `tools.dsguard.readiness` (Change 6, v0.3:
20260915-readiness-and-promotion) -- matriz de readiness
(`evaluar_readiness`) + promoción secuencial gateada (`promote`).

Sigue el mismo patrón de `test_mlops_foundations.py`/`test_maturity.py`:
funciones puras se llaman directo sobre un repo git temporal propio
(necesario porque `mlops_foundations.evaluar_foundations` usa
`repo.get_head`/`repo.list_dirty_files`); la integración CLI real corre
`tools/ds_guard.py` como subproceso. Nunca usa este repositorio real como
fixture.
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

from dsguard import checks, lifecycle, maturity, mlops_evidence, readiness  # noqa: E402

DS_GUARD = REPO_ORIGEN / "tools" / "ds_guard.py"


def _crear_repo_git_temporal(prefix: str = "readiness_test_") -> Path:
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


def _commitear_todo(repo: Path, mensaje: str = "fixture") -> None:
    subprocess.run(["git", "add", "-A"], cwd=str(repo), check=True)
    subprocess.run(["git", "commit", "-q", "-m", mensaje], cwd=str(repo), check=True)


def _set_fase(repo: Path, fase: str, valor: str) -> None:
    estado = lifecycle.leer_estado(lifecycle.state_path(repo))
    estado["crispdm"]["fases"][fase]["estado"] = valor
    lifecycle.escribir_estado(repo, estado)


def _cerrar_fases_candidate(repo: Path) -> None:
    for fase in readiness._FASES_CANDIDATE:
        _set_fase(repo, fase, "cerrada")


def _preparar_foundations_pass(repo: Path) -> None:
    """reproducibilidad/versionado/artifacts en PASS (lineage siempre
    WARN/N-A, nunca PASS -- ver mlops_foundations.py)."""
    (repo / "requirements-lock.txt").write_text("pandas==2.0.0\n", encoding="utf-8")
    (repo / "models").mkdir(exist_ok=True)
    (repo / "models" / "modelo.pkl").write_bytes(b"x")
    _commitear_todo(repo)


def _agregar_evidencia_prodready_completa(repo: Path) -> None:
    for cap in lifecycle.MLOPS_CAPACIDADES["production_readiness"]:
        if cap == "environment_reproducible":
            # Satisfecho por el lockfile de _preparar_foundations_pass -- no
            # hace falta evidencia explícita para este.
            continue
        ruta = repo / f"evidencia_{cap}.txt"
        ruta.write_bytes(f"evidencia de {cap}".encode("utf-8"))
        mlops_evidence.agregar_evidencia(repo, "production_readiness", cap, ruta.name, f"evidencia de {cap}")


def _agregar_evidencia_ops_completa(repo: Path) -> None:
    for cap in lifecycle.MLOPS_CAPACIDADES["operations"]:
        ruta = repo / f"evidencia_ops_{cap}.txt"
        ruta.write_bytes(f"evidencia ops de {cap}".encode("utf-8"))
        mlops_evidence.agregar_evidencia(repo, "operations", cap, ruta.name, f"evidencia ops de {cap}")


def _preparar_candidate_completo(repo: Path) -> None:
    maturity.project_init(repo, stage="experiment")
    lifecycle.lifecycle_init(repo)
    maturity.set_risk(repo, "medium", "clasificacion inicial")
    _cerrar_fases_candidate(repo)
    _preparar_foundations_pass(repo)
    _agregar_evidencia_prodready_completa(repo)
    # `check_reproducibilidad` marca WARN si el working tree tiene cambios
    # sin confirmar -- un commit final deja el fixture "todo completo"
    # realmente limpio (project.json/lifecycle/state.json/evidencia
    # incluidos), para que READINESS-FOUNDATIONS-REPRODUCIBILIDAD de PASS.
    _commitear_todo(repo, "fixture: candidate completo")


def _preparar_production_completo(repo: Path) -> None:
    _preparar_candidate_completo(repo)
    _set_fase(repo, "deployment", "cerrada")
    _set_fase(repo, "monitoring", "en_progreso")
    _agregar_evidencia_ops_completa(repo)
    _commitear_todo(repo, "fixture: production completo")


class _BaseRepoGit(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_repo_git_temporal()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)


# --- evaluar_readiness: target=experiment --------------------------------------

class TestReadinessExperiment(_BaseRepoGit):
    def test_lifecycle_y_project_validos_todo_pass_ready(self):
        maturity.project_init(self.repo, stage="experiment")
        lifecycle.lifecycle_init(self.repo)
        resultados = readiness.evaluar_readiness(self.repo, "experiment")
        self.assertEqual(len(resultados), 2)
        for r in resultados:
            self.assertEqual(r.status, checks.STATUS_PASS)
        self.assertFalse(checks.hay_bloqueo(resultados))

    def test_lifecycle_ausente_fail_especifico(self):
        maturity.project_init(self.repo, stage="experiment")
        resultados = readiness.evaluar_readiness(self.repo, "experiment")
        por_codigo = {r.code: r for r in resultados}
        self.assertEqual(por_codigo["READINESS-LIFECYCLE-VALID"].status, checks.STATUS_FAIL)
        self.assertTrue(checks.hay_bloqueo(resultados))

    def test_project_json_corrupto_technical_error(self):
        ruta = maturity.state_path(self.repo)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text("esto no es json valido", encoding="utf-8")
        resultados = readiness.evaluar_readiness(self.repo, "experiment")
        por_codigo = {r.code: r for r in resultados}
        self.assertEqual(por_codigo["READINESS-PROJECT-VALID"].status, checks.STATUS_FAIL)
        self.assertEqual(por_codigo["READINESS-PROJECT-VALID"].kind, checks.KIND_TECHNICAL_ERROR)

    def test_no_exige_risk_crispdm_ni_foundations(self):
        maturity.project_init(self.repo, stage="experiment")
        lifecycle.lifecycle_init(self.repo)
        resultados = readiness.evaluar_readiness(self.repo, "experiment")
        codigos = [r.code for r in resultados]
        self.assertNotIn("READINESS-RISK-CLASSIFIED", codigos)
        for codigo in codigos:
            self.assertFalse(codigo.startswith("READINESS-CRISPDM-"))
            self.assertFalse(codigo.startswith("READINESS-FOUNDATIONS-"))
            self.assertFalse(codigo.startswith("READINESS-PRODREADY-"))


# --- evaluar_readiness: target=production_candidate ----------------------------

class TestReadinessProductionCandidate(_BaseRepoGit):
    def test_risk_null_fail_especifico(self):
        maturity.project_init(self.repo, stage="experiment")
        lifecycle.lifecycle_init(self.repo)
        resultados = readiness.evaluar_readiness(self.repo, "production_candidate")
        por_codigo = {r.code: r for r in resultados}
        self.assertEqual(por_codigo["READINESS-RISK-CLASSIFIED"].status, checks.STATUS_FAIL)

    def test_cada_fase_crispdm_faltante_no_iniciada(self):
        for fase in readiness._FASES_CANDIDATE:
            with self.subTest(fase=fase, estado="no_iniciada"):
                repo = _crear_repo_git_temporal()
                try:
                    _preparar_candidate_completo(repo)
                    _set_fase(repo, fase, "no_iniciada")
                    resultados = readiness.evaluar_readiness(repo, "production_candidate")
                    por_codigo = {r.code: r for r in resultados}
                    codigo = readiness._codigo_crispdm(fase)
                    self.assertEqual(por_codigo[codigo].status, checks.STATUS_FAIL)
                    self.assertIn(fase, por_codigo[codigo].message)
                finally:
                    shutil.rmtree(repo, ignore_errors=True)

    def test_cada_fase_crispdm_faltante_en_progreso(self):
        for fase in readiness._FASES_CANDIDATE:
            with self.subTest(fase=fase, estado="en_progreso"):
                repo = _crear_repo_git_temporal()
                try:
                    _preparar_candidate_completo(repo)
                    _set_fase(repo, fase, "en_progreso")
                    resultados = readiness.evaluar_readiness(repo, "production_candidate")
                    por_codigo = {r.code: r for r in resultados}
                    codigo = readiness._codigo_crispdm(fase)
                    self.assertEqual(por_codigo[codigo].status, checks.STATUS_FAIL)
                finally:
                    shutil.rmtree(repo, ignore_errors=True)

    def test_foundations_warn_en_reproducibilidad_versionado_artifacts_cada_uno(self):
        def _romper_versionado(repo):
            # data/ con contenido pero sin fingerprint registrado -> WARN en
            # mlops_foundations.check_versionado (ver mlops_foundations.py).
            (repo / "data").mkdir(exist_ok=True)
            (repo / "data" / "raw.csv").write_text("col\n1\n", encoding="utf-8")

        casos = {
            "READINESS-FOUNDATIONS-REPRODUCIBILIDAD": lambda repo: (repo / "requirements-lock.txt").unlink(),
            "READINESS-FOUNDATIONS-VERSIONADO": _romper_versionado,
            "READINESS-FOUNDATIONS-ARTIFACTS": lambda repo: shutil.rmtree(repo / "models"),
        }
        for codigo, romper in casos.items():
            with self.subTest(codigo=codigo):
                repo = _crear_repo_git_temporal()
                try:
                    _preparar_candidate_completo(repo)
                    romper(repo)
                    _commitear_todo(repo)
                    resultados = readiness.evaluar_readiness(repo, "production_candidate")
                    por_codigo = {r.code: r for r in resultados}
                    self.assertEqual(por_codigo[codigo].status, checks.STATUS_FAIL)
                finally:
                    shutil.rmtree(repo, ignore_errors=True)

    def test_lineage_warn_no_bloqueante(self):
        _preparar_candidate_completo(self.repo)
        resultados = readiness.evaluar_readiness(self.repo, "production_candidate")
        por_codigo = {r.code: r for r in resultados}
        lineage = por_codigo["READINESS-FOUNDATIONS-LINEAGE"]
        self.assertIn(lineage.status, (checks.STATUS_WARN, checks.STATUS_NA))
        self.assertFalse(checks.hay_bloqueo(resultados))

    def test_cada_capability_prodready_sin_evidencia_fail(self):
        for cap in lifecycle.MLOPS_CAPACIDADES["production_readiness"]:
            with self.subTest(cap=cap):
                repo = _crear_repo_git_temporal()
                try:
                    _preparar_candidate_completo(repo)
                    if cap == "environment_reproducible":
                        (repo / "requirements-lock.txt").unlink()
                        _commitear_todo(repo)
                    else:
                        estado = lifecycle.leer_estado(lifecycle.state_path(repo))
                        estado["mlops"]["production_readiness"][cap]["evidencia"] = []
                        lifecycle.escribir_estado(repo, estado)
                    resultados = readiness.evaluar_readiness(repo, "production_candidate")
                    por_codigo = {r.code: r for r in resultados}
                    codigo = readiness._codigo_prodready(cap)
                    self.assertEqual(por_codigo[codigo].status, checks.STATUS_FAIL)
                finally:
                    shutil.rmtree(repo, ignore_errors=True)

    def test_todo_completo_ready_true(self):
        _preparar_candidate_completo(self.repo)
        resultados = readiness.evaluar_readiness(self.repo, "production_candidate")
        self.assertFalse(checks.hay_bloqueo(resultados))


# --- evaluar_readiness: target=production ---------------------------------------

class TestReadinessProduction(_BaseRepoGit):
    def test_prerequisitos_de_candidate_siguen_aplicando(self):
        maturity.project_init(self.repo, stage="experiment")
        lifecycle.lifecycle_init(self.repo)
        resultados = readiness.evaluar_readiness(self.repo, "production")
        por_codigo = {r.code: r for r in resultados}
        self.assertEqual(por_codigo["READINESS-RISK-CLASSIFIED"].status, checks.STATUS_FAIL)
        self.assertTrue(checks.hay_bloqueo(resultados))

    def test_deployment_no_cerrada_fail(self):
        _preparar_production_completo(self.repo)
        _set_fase(self.repo, "deployment", "en_progreso")
        resultados = readiness.evaluar_readiness(self.repo, "production")
        por_codigo = {r.code: r for r in resultados}
        self.assertEqual(por_codigo["READINESS-CRISPDM-DEPLOYMENT"].status, checks.STATUS_FAIL)

    def test_monitoring_no_iniciada_fail_en_progreso_o_cerrada_no_bloquea(self):
        _preparar_production_completo(self.repo)
        _set_fase(self.repo, "monitoring", "no_iniciada")
        resultados = readiness.evaluar_readiness(self.repo, "production")
        por_codigo = {r.code: r for r in resultados}
        self.assertEqual(por_codigo["READINESS-CRISPDM-MONITORING"].status, checks.STATUS_FAIL)

        _set_fase(self.repo, "monitoring", "en_progreso")
        resultados = readiness.evaluar_readiness(self.repo, "production")
        por_codigo = {r.code: r for r in resultados}
        self.assertEqual(por_codigo["READINESS-CRISPDM-MONITORING"].status, checks.STATUS_PASS)

        _set_fase(self.repo, "monitoring", "cerrada")
        resultados = readiness.evaluar_readiness(self.repo, "production")
        por_codigo = {r.code: r for r in resultados}
        self.assertEqual(por_codigo["READINESS-CRISPDM-MONITORING"].status, checks.STATUS_PASS)

    def test_cada_capability_operations_sin_evidencia_fail(self):
        for cap in lifecycle.MLOPS_CAPACIDADES["operations"]:
            with self.subTest(cap=cap):
                repo = _crear_repo_git_temporal()
                try:
                    _preparar_production_completo(repo)
                    estado = lifecycle.leer_estado(lifecycle.state_path(repo))
                    estado["mlops"]["operations"][cap]["evidencia"] = []
                    lifecycle.escribir_estado(repo, estado)
                    resultados = readiness.evaluar_readiness(repo, "production")
                    por_codigo = {r.code: r for r in resultados}
                    codigo = readiness._codigo_ops(cap)
                    self.assertEqual(por_codigo[codigo].status, checks.STATUS_FAIL)
                finally:
                    shutil.rmtree(repo, ignore_errors=True)

    def test_evidencia_con_hash_obsoleto_fail(self):
        _preparar_production_completo(self.repo)
        cap = lifecycle.MLOPS_CAPACIDADES["operations"][0]
        (self.repo / f"evidencia_ops_{cap}.txt").write_bytes(b"contenido modificado despues de registrar")
        resultados = readiness.evaluar_readiness(self.repo, "production")
        por_codigo = {r.code: r for r in resultados}
        self.assertEqual(por_codigo[readiness._codigo_ops(cap)].status, checks.STATUS_FAIL)

    def test_todo_completo_ready_true(self):
        _preparar_production_completo(self.repo)
        resultados = readiness.evaluar_readiness(self.repo, "production")
        self.assertFalse(checks.hay_bloqueo(resultados))


# --- evaluar_readiness: read-only estricto --------------------------------------

class TestReadinessReadOnly(_BaseRepoGit):
    def _bytes_o_none(self, ruta: Path):
        return ruta.read_bytes() if ruta.exists() else None

    def _assert_no_muta(self, target: str):
        ruta_lifecycle = lifecycle.state_path(self.repo)
        ruta_project = maturity.state_path(self.repo)
        antes_lifecycle = self._bytes_o_none(ruta_lifecycle)
        antes_project = self._bytes_o_none(ruta_project)

        readiness.evaluar_readiness(self.repo, target)

        self.assertEqual(self._bytes_o_none(ruta_lifecycle), antes_lifecycle)
        self.assertEqual(self._bytes_o_none(ruta_project), antes_project)

    def test_sin_nada_target_experiment(self):
        self._assert_no_muta("experiment")

    def test_candidate_completo_no_muta(self):
        _preparar_candidate_completo(self.repo)
        self._assert_no_muta("production_candidate")

    def test_production_completo_no_muta(self):
        _preparar_production_completo(self.repo)
        self._assert_no_muta("production")

    def test_estados_incompletos_no_mutan(self):
        maturity.project_init(self.repo, stage="experiment")
        lifecycle.lifecycle_init(self.repo)
        self._assert_no_muta("production_candidate")
        self._assert_no_muta("production")


# --- promote --------------------------------------------------------------------

class TestPromote(_BaseRepoGit):
    def test_secuencia_correcta_los_3_pasos(self):
        maturity.project_init(self.repo, stage="discovery")
        lifecycle.lifecycle_init(self.repo)
        _commitear_todo(self.repo, "lifecycle inicializado")
        r1 = readiness.promote(self.repo, "experiment", "arranca desarrollo")
        self.assertTrue(r1["promovido"])
        self.assertEqual(r1["project_stage"], "experiment")

        maturity.set_risk(self.repo, "medium", "clasificacion")
        _cerrar_fases_candidate(self.repo)
        _preparar_foundations_pass(self.repo)
        _agregar_evidencia_prodready_completa(self.repo)
        _commitear_todo(self.repo, "candidate completo")
        r2 = readiness.promote(self.repo, "production_candidate", "cumple production readiness")
        self.assertTrue(r2["promovido"])
        self.assertEqual(r2["project_stage"], "production_candidate")

        _set_fase(self.repo, "deployment", "cerrada")
        _set_fase(self.repo, "monitoring", "en_progreso")
        _agregar_evidencia_ops_completa(self.repo)
        _commitear_todo(self.repo, "production completo")
        r3 = readiness.promote(self.repo, "production", "condiciones operativas alcanzadas")
        self.assertTrue(r3["promovido"])
        self.assertEqual(r3["project_stage"], "production")

        estado = maturity.leer_estado(maturity.state_path(self.repo))
        self.assertEqual(len(estado["stage_history"]), 4)  # init + 3 promotes
        self.assertEqual([e["via"] for e in estado["stage_history"][1:]], ["promote", "promote", "promote"])

    def test_salto_rechazado_sin_mutacion(self):
        maturity.project_init(self.repo, stage="discovery")
        ruta = maturity.state_path(self.repo)
        antes = ruta.read_bytes()
        with self.assertRaises(readiness.PromotionError):
            readiness.promote(self.repo, "production_candidate", "salteando experiment")
        self.assertEqual(ruta.read_bytes(), antes)

    def test_downgrade_rechazado_sin_mutacion(self):
        maturity.project_init(self.repo, stage="experiment")
        ruta = maturity.state_path(self.repo)
        antes = ruta.read_bytes()
        with self.assertRaises(readiness.PromotionError):
            readiness.promote(self.repo, "discovery", "bajando de stage")
        self.assertEqual(ruta.read_bytes(), antes)

    def test_reason_ausente_o_vacio_rechazado_sin_mutacion(self):
        maturity.project_init(self.repo, stage="discovery")
        ruta = maturity.state_path(self.repo)
        antes = ruta.read_bytes()
        with self.assertRaises(readiness.PromotionError):
            readiness.promote(self.repo, "experiment", "")
        self.assertEqual(ruta.read_bytes(), antes)

    def test_readiness_con_fail_no_muta(self):
        maturity.project_init(self.repo, stage="experiment")
        # Sin lifecycle -- readiness de production_candidate va a tener FAIL.
        ruta = maturity.state_path(self.repo)
        antes = ruta.read_bytes()
        resultado = readiness.promote(self.repo, "production_candidate", "intento sin cumplir gates")
        self.assertFalse(resultado["promovido"])
        self.assertEqual(ruta.read_bytes(), antes)

    def test_readiness_con_technical_error_tratado_como_fail_sin_mutacion(self):
        maturity.project_init(self.repo, stage="experiment")
        ruta_lifecycle = lifecycle.state_path(self.repo)
        ruta_lifecycle.parent.mkdir(parents=True, exist_ok=True)
        ruta_lifecycle.write_text("esto no es json valido", encoding="utf-8")
        ruta_project = maturity.state_path(self.repo)
        antes = ruta_project.read_bytes()
        resultado = readiness.promote(self.repo, "production_candidate", "intento con lifecycle corrupto")
        self.assertFalse(resultado["promovido"])
        self.assertEqual(ruta_project.read_bytes(), antes)

    def test_exitosa_no_reescribe_entradas_previas(self):
        maturity.project_init(self.repo, stage="discovery")
        lifecycle.lifecycle_init(self.repo)
        estado_inicial = maturity.leer_estado(maturity.state_path(self.repo))
        primera_entrada = estado_inicial["stage_history"][0]

        resultado = readiness.promote(self.repo, "experiment", "arranca desarrollo")
        self.assertTrue(resultado["promovido"])

        estado_final = maturity.leer_estado(maturity.state_path(self.repo))
        self.assertEqual(estado_final["stage_history"][0], primera_entrada)
        self.assertEqual(len(estado_final["stage_history"]), 2)

    def test_repetir_promote_mismo_stage_rechazado_sin_duplicar(self):
        maturity.project_init(self.repo, stage="discovery")
        lifecycle.lifecycle_init(self.repo)
        resultado = readiness.promote(self.repo, "experiment", "primera promocion")
        self.assertTrue(resultado["promovido"])
        estado_intermedio = maturity.leer_estado(maturity.state_path(self.repo))
        self.assertEqual(len(estado_intermedio["stage_history"]), 2)

        with self.assertRaises(readiness.PromotionError):
            readiness.promote(self.repo, "experiment", "intento repetido")

        estado_final = maturity.leer_estado(maturity.state_path(self.repo))
        self.assertEqual(len(estado_final["stage_history"]), 2)

    def test_project_json_ausente_levanta_filenotfound(self):
        with self.assertRaises(FileNotFoundError):
            readiness.promote(self.repo, "experiment", "motivo")

    def test_despues_de_promote_exitoso_calibrate_levanta_error(self):
        maturity.project_init(self.repo, stage="discovery")
        lifecycle.lifecycle_init(self.repo)
        resultado = readiness.promote(self.repo, "experiment", "primera promocion")
        self.assertTrue(resultado["promovido"])
        with self.assertRaises(maturity.MaturityEstadoError):
            maturity.calibrar(self.repo, "production", "intento de bypass via calibrate")


# --- CLI real --------------------------------------------------------------------

class TestCliReadinessYPromote(_BaseRepoGit):
    def test_project_readiness_cada_target_texto_y_json(self):
        _correr_ds_guard(["project", "init", "--stage", "discovery"], self.repo)
        _correr_ds_guard(["lifecycle", "migrate"], self.repo)
        lifecycle.lifecycle_init(self.repo)

        for target in readiness.TARGETS_VALIDOS:
            resultado_texto = _correr_ds_guard(["project", "readiness", "--target", target], self.repo)
            self.assertIn(resultado_texto.returncode, (0, 1))
            self.assertIn("Resultado:", resultado_texto.stdout)

            resultado_json = _correr_ds_guard(
                ["project", "readiness", "--target", target, "--json"], self.repo
            )
            payload = json.loads(resultado_json.stdout)
            self.assertIn("ready", payload)
            self.assertIn("resultados", payload)
            exit_code_esperado = 0 if payload["ready"] else 1
            self.assertEqual(resultado_json.returncode, exit_code_esperado)

    def test_project_promote_exito(self):
        _correr_ds_guard(["project", "init", "--stage", "discovery"], self.repo)
        lifecycle.lifecycle_init(self.repo)
        resultado = _correr_ds_guard(
            ["project", "promote", "experiment", "--reason", "arranca desarrollo", "--json"], self.repo
        )
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        payload = json.loads(resultado.stdout)
        self.assertTrue(payload["promovido"])
        self.assertEqual(payload["project_stage"], "experiment")

    def test_project_promote_fail_de_readiness_exit_1_sin_mutacion(self):
        _correr_ds_guard(["project", "init", "--stage", "experiment"], self.repo)
        ruta = maturity.state_path(self.repo)
        antes = ruta.read_bytes()
        resultado = _correr_ds_guard(
            ["project", "promote", "production_candidate", "--reason", "intento sin gates"], self.repo
        )
        self.assertEqual(resultado.returncode, 1)
        self.assertEqual(ruta.read_bytes(), antes)

    def test_project_promote_transicion_invalida_exit_1_sin_mutacion(self):
        _correr_ds_guard(["project", "init", "--stage", "discovery"], self.repo)
        ruta = maturity.state_path(self.repo)
        antes = ruta.read_bytes()
        resultado = _correr_ds_guard(
            ["project", "promote", "production_candidate", "--reason", "salto invalido"], self.repo
        )
        self.assertEqual(resultado.returncode, 1)
        self.assertEqual(ruta.read_bytes(), antes)

    def test_project_promote_reason_faltante_exit_2_argparse(self):
        _correr_ds_guard(["project", "init", "--stage", "discovery"], self.repo)
        resultado = _correr_ds_guard(["project", "promote", "experiment"], self.repo)
        self.assertEqual(resultado.returncode, 2)


class TestCliMlopsEvidenceAdd(_BaseRepoGit):
    def setUp(self):
        super().setUp()
        _correr_ds_guard(["project", "init", "--stage", "experiment"], self.repo)
        lifecycle.lifecycle_init(self.repo)

    def test_exito_exit_0(self):
        (self.repo / "artifact.txt").write_bytes(b"contenido")
        resultado = _correr_ds_guard(
            [
                "mlops", "evidence", "add",
                "--tier", "production_readiness",
                "--capability", "packaging",
                "--artifact", "artifact.txt",
                "--reason", "empaquetado documentado",
                "--json",
            ],
            self.repo,
        )
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        payload = json.loads(resultado.stdout)
        self.assertTrue(payload["agregado"])

    def test_error_de_dominio_exit_1(self):
        resultado = _correr_ds_guard(
            [
                "mlops", "evidence", "add",
                "--tier", "production_readiness",
                "--capability", "packaging",
                "--artifact", "no_existe.txt",
                "--reason", "motivo",
            ],
            self.repo,
        )
        self.assertEqual(resultado.returncode, 1)

    def test_lifecycle_ausente_exit_2(self):
        otro_repo = _crear_repo_git_temporal()
        try:
            _correr_ds_guard(["project", "init", "--stage", "experiment"], otro_repo)
            (otro_repo / "artifact.txt").write_bytes(b"x")
            resultado = _correr_ds_guard(
                [
                    "mlops", "evidence", "add",
                    "--tier", "production_readiness",
                    "--capability", "packaging",
                    "--artifact", "artifact.txt",
                    "--reason", "motivo",
                ],
                otro_repo,
            )
            self.assertEqual(resultado.returncode, 2)
            self.assertIn("lifecycle", resultado.stderr)
        finally:
            shutil.rmtree(otro_repo, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()

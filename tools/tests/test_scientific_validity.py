"""Tests de `tools.dsguard.scientific_validity` (v0.4 Change 0:
20260916-kdd-enforceable-checks) -- scientific validity checks
(cutoff/holdout/leakage/baseline) sobre `.harmessi/scientific-policy.json`
(opcional), expuestos vía `ds_guard science status`.

A diferencia de `test_mlops_foundations.py`, ninguna función de
`scientific_validity` llama `repo.get_head`/`repo.list_dirty_files`: un
`tempfile.mkdtemp()` simple alcanza para las funciones puras, sin `git init`.
La integración CLI real (subprocess) sí necesita un repo git de verdad, mismo
patrón que `test_mlops_foundations.py`/`test_status.py`.
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

from dsguard import checks, core, scientific_validity  # noqa: E402

DS_GUARD = REPO_ORIGEN / "tools" / "ds_guard.py"


# --- Fixtures compartidas -----------------------------------------------------

def _crear_repo_temporal(prefix: str = "sci_validity_test_") -> Path:
    return Path(tempfile.mkdtemp(prefix=prefix))


def _crear_repo_git_temporal(prefix: str = "sci_validity_cli_test_") -> Path:
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


def _escribir_policy(repo: Path, datos: dict) -> None:
    ruta = scientific_validity.policy_path(repo)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")


def _escribir_policy_texto(repo: Path, texto: str) -> None:
    ruta = scientific_validity.policy_path(repo)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(texto, encoding="utf-8")


def _escribir_guardrails(repo: Path, datos: dict) -> None:
    ruta = repo / ".claude" / "guardrails.json"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")


def _escribir_guardrails_texto(repo: Path, texto: str) -> None:
    ruta = repo / ".claude" / "guardrails.json"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(texto, encoding="utf-8")


def _escribir_profile(
    repo: Path,
    dataset_id: str = "ds1",
    columnas_detalle: dict | None = None,
) -> str:
    """Escribe un profile.json simulando la salida real de `ds_profile`.
    Devuelve la ruta relativa POSIX (para usarla en `temporal.profile_path`)."""
    if columnas_detalle is None:
        columnas_detalle = {
            "fecha_evento": {
                "dtype": "fecha",
                "fecha_min": "2026-01-01T00:00:00",
                "fecha_max": "2026-06-01T00:00:00",
            }
        }
    profile_dir = repo / ".harmessi" / "profiles" / dataset_id
    profile_dir.mkdir(parents=True, exist_ok=True)
    (profile_dir / "profile.json").write_text(
        json.dumps({"columnas_detalle": columnas_detalle}, ensure_ascii=False), encoding="utf-8"
    )
    return f".harmessi/profiles/{dataset_id}/profile.json"


def _escribir_evidencia(repo: Path, nombre: str = "baseline_evidence.txt", contenido: bytes = b"contenido de evidencia") -> str:
    ruta = repo / nombre
    ruta.write_bytes(contenido)
    return nombre


class _BaseRepo(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_repo_temporal()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)


# --- Policy --------------------------------------------------------------------

class TestPolicy(_BaseRepo):
    def test_ausente_todo_na(self):
        resultados = scientific_validity.evaluar_scientific_checks(self.repo)
        self.assertEqual(len(resultados), 7)
        for r in resultados:
            self.assertEqual(r.status, checks.STATUS_NA)

    def test_valida_minima_no_lanza(self):
        _escribir_policy(self.repo, {"schema_version": 1})
        resultados = scientific_validity.evaluar_scientific_checks(self.repo)
        self.assertEqual(len(resultados), 7)

    def test_json_corrupto_fail_unico(self):
        _escribir_policy_texto(self.repo, "esto no es json")
        resultados = scientific_validity.evaluar_scientific_checks(self.repo)
        self.assertEqual(len(resultados), 1)
        self.assertEqual(resultados[0].status, checks.STATUS_FAIL)
        self.assertEqual(resultados[0].code, scientific_validity.CODIGO_POLICY_ERROR)
        self.assertEqual(resultados[0].kind, checks.KIND_TECHNICAL_ERROR)

    def test_schema_version_desconocida_fail_unico(self):
        _escribir_policy(self.repo, {"schema_version": 99})
        resultados = scientific_validity.evaluar_scientific_checks(self.repo)
        self.assertEqual(len(resultados), 1)
        self.assertEqual(resultados[0].status, checks.STATUS_FAIL)
        self.assertEqual(resultados[0].code, scientific_validity.CODIGO_POLICY_ERROR)

    def test_seccion_con_tipo_incorrecto_levanta_error(self):
        _escribir_policy(self.repo, {"schema_version": 1, "temporal": "no es un dict"})
        resultados = scientific_validity.evaluar_scientific_checks(self.repo)
        self.assertEqual(len(resultados), 1)
        self.assertEqual(resultados[0].code, scientific_validity.CODIGO_POLICY_ERROR)
        with self.assertRaises(scientific_validity.ScientificPolicyError):
            scientific_validity.leer_policy(self.repo)

    def test_campos_desconocidos_extra_se_ignoran(self):
        _escribir_policy(self.repo, {"schema_version": 1, "campo_del_futuro": "algo", "temporal": {"declared": False, "campo_extra": 1}})
        resultados = scientific_validity.evaluar_scientific_checks(self.repo)
        self.assertEqual(len(resultados), 7)
        self.assertTrue(all(r.status != checks.STATUS_FAIL or r.code != scientific_validity.CODIGO_POLICY_ERROR for r in resultados))


# --- Cutoff ----------------------------------------------------------------

class TestCutoff(_BaseRepo):
    def _policy(self, **overrides) -> dict:
        base = {"declared": True, "cutoff_utc": "2026-07-01T00:00:00Z", "date_column": "fecha_evento", "profile_path": None}
        base.update(overrides)
        return {"schema_version": 1, "temporal": base}

    def test_no_declarado_na(self):
        _escribir_policy(self.repo, {"schema_version": 1, "temporal": {"declared": False}})
        r = scientific_validity.evaluar_cutoff(self.repo, {"temporal": {"declared": False}})[0]
        self.assertEqual(r.status, checks.STATUS_NA)

    def test_sin_cutoff_utc_warn(self):
        policy = self._policy(cutoff_utc=None)
        r = scientific_validity.evaluar_cutoff(self.repo, policy)[0]
        self.assertEqual(r.status, checks.STATUS_WARN)

    def test_sin_date_column_warn(self):
        policy = self._policy(date_column=None)
        r = scientific_validity.evaluar_cutoff(self.repo, policy)[0]
        self.assertEqual(r.status, checks.STATUS_WARN)

    def test_sin_profile_path_warn(self):
        policy = self._policy(profile_path=None)
        r = scientific_validity.evaluar_cutoff(self.repo, policy)[0]
        self.assertEqual(r.status, checks.STATUS_WARN)

    def test_cutoff_utc_formato_invalido_fail(self):
        policy = self._policy(cutoff_utc="no-es-una-fecha", profile_path="x.json")
        r = scientific_validity.evaluar_cutoff(self.repo, policy)[0]
        self.assertEqual(r.status, checks.STATUS_FAIL)

    def test_profile_path_inexistente_warn(self):
        policy = self._policy(profile_path=".harmessi/profiles/ausente/profile.json")
        r = scientific_validity.evaluar_cutoff(self.repo, policy)[0]
        self.assertEqual(r.status, checks.STATUS_WARN)

    def test_profile_json_corrupto_fail_technical_error(self):
        profile_dir = self.repo / ".harmessi" / "profiles" / "ds1"
        profile_dir.mkdir(parents=True, exist_ok=True)
        (profile_dir / "profile.json").write_text("esto no es json", encoding="utf-8")
        policy = self._policy(profile_path=".harmessi/profiles/ds1/profile.json")
        r = scientific_validity.evaluar_cutoff(self.repo, policy)[0]
        self.assertEqual(r.status, checks.STATUS_FAIL)
        self.assertEqual(r.kind, checks.KIND_TECHNICAL_ERROR)

    def test_date_column_no_en_profile_fail(self):
        ruta = _escribir_profile(self.repo, columnas_detalle={"otra_columna": {"dtype": "fecha", "fecha_max": "2026-01-01T00:00:00"}})
        policy = self._policy(profile_path=ruta)
        r = scientific_validity.evaluar_cutoff(self.repo, policy)[0]
        self.assertEqual(r.status, checks.STATUS_FAIL)
        self.assertIn("otra_columna", r.message)

    def test_dtype_no_fecha_fail(self):
        ruta = _escribir_profile(self.repo, columnas_detalle={"fecha_evento": {"dtype": "entero"}})
        policy = self._policy(profile_path=ruta)
        r = scientific_validity.evaluar_cutoff(self.repo, policy)[0]
        self.assertEqual(r.status, checks.STATUS_FAIL)
        self.assertIn("entero", r.message)

    def test_fecha_max_dentro_del_cutoff_pass(self):
        ruta = _escribir_profile(self.repo)
        policy = self._policy(cutoff_utc="2026-07-01T00:00:00Z", profile_path=ruta)
        r = scientific_validity.evaluar_cutoff(self.repo, policy)[0]
        self.assertEqual(r.status, checks.STATUS_PASS)
        self.assertEqual(r.subject, "fecha_evento")

    def test_fecha_max_excede_cutoff_fail(self):
        ruta = _escribir_profile(self.repo)
        policy = self._policy(cutoff_utc="2026-01-01T00:00:00Z", profile_path=ruta)
        r = scientific_validity.evaluar_cutoff(self.repo, policy)[0]
        self.assertEqual(r.status, checks.STATUS_FAIL)

    def test_profile_dentro_de_holdout_sin_excepcion_fail_menciona_holdout(self):
        ruta = _escribir_profile(self.repo)
        _escribir_guardrails(self.repo, {"holdouts": [".harmessi/**"]})
        policy = self._policy(profile_path=ruta)
        r = scientific_validity.evaluar_cutoff(self.repo, policy)[0]
        self.assertEqual(r.status, checks.STATUS_FAIL)
        self.assertIn("holdout", r.message.lower())


# --- Holdout protection ------------------------------------------------------

class TestHoldoutProteccion(_BaseRepo):
    def test_no_declarado_na(self):
        r = scientific_validity.evaluar_holdout_proteccion(self.repo, {"holdout": {"declared": False}})[0]
        self.assertEqual(r.status, checks.STATUS_NA)

    def test_declarado_sin_holdouts_en_guardrails_fail(self):
        policy = {"holdout": {"declared": True}}
        r = scientific_validity.evaluar_holdout_proteccion(self.repo, policy)[0]
        self.assertEqual(r.status, checks.STATUS_FAIL)

    def test_declarado_con_holdouts_pass(self):
        _escribir_guardrails(self.repo, {"holdouts": ["data/holdout/**"]})
        policy = {"holdout": {"declared": True}}
        r = scientific_validity.evaluar_holdout_proteccion(self.repo, policy)[0]
        self.assertEqual(r.status, checks.STATUS_PASS)

    def test_guardrails_corrupto_fail_technical_error(self):
        _escribir_guardrails_texto(self.repo, "esto no es json")
        policy = {"holdout": {"declared": True}}
        r = scientific_validity.evaluar_holdout_proteccion(self.repo, policy)[0]
        self.assertEqual(r.status, checks.STATUS_FAIL)
        self.assertEqual(r.kind, checks.KIND_TECHNICAL_ERROR)


# --- Holdout usage -----------------------------------------------------------

class TestHoldoutUso(_BaseRepo):
    def test_no_declarado_na(self):
        r = scientific_validity.evaluar_holdout_uso(self.repo, {"holdout": {"declared": False}})[0]
        self.assertEqual(r.status, checks.STATUS_NA)

    def test_sin_usage_declarations_warn(self):
        policy = {"holdout": {"declared": True}}
        r = scientific_validity.evaluar_holdout_uso(self.repo, policy)[0]
        self.assertEqual(r.status, checks.STATUS_WARN)
        self.assertIn("información insuficiente", r.message)

    def test_operacion_prohibida_usada_fail(self):
        policy = {
            "holdout": {
                "declared": True,
                "usage_declarations": [{"operation": "training", "used": True}],
            }
        }
        r = scientific_validity.evaluar_holdout_uso(self.repo, policy)[0]
        self.assertEqual(r.status, checks.STATUS_FAIL)
        self.assertIn("training", r.message)

    def test_las_5_declaradas_false_pass(self):
        declaraciones = [{"operation": op, "used": False} for op in scientific_validity.OPERACIONES_PROHIBIDAS]
        policy = {"holdout": {"declared": True, "usage_declarations": declaraciones}}
        r = scientific_validity.evaluar_holdout_uso(self.repo, policy)[0]
        self.assertEqual(r.status, checks.STATUS_PASS)

    def test_las_5_declaradas_false_mas_final_evaluation_autorizada_pass_con_mencion(self):
        declaraciones = [{"operation": op, "used": False} for op in scientific_validity.OPERACIONES_PROHIBIDAS]
        policy = {
            "holdout": {
                "declared": True,
                "usage_declarations": declaraciones,
                "final_evaluation": {"authorized": True, "reason": "evaluacion final aprobada"},
            }
        }
        r = scientific_validity.evaluar_holdout_uso(self.repo, policy)[0]
        self.assertEqual(r.status, checks.STATUS_PASS)
        self.assertIn("evaluacion final aprobada", r.message)

    def test_declaracion_parcial_warn(self):
        declaraciones = [{"operation": "training", "used": False}]
        policy = {"holdout": {"declared": True, "usage_declarations": declaraciones}}
        r = scientific_validity.evaluar_holdout_uso(self.repo, policy)[0]
        self.assertEqual(r.status, checks.STATUS_WARN)


# --- Leakage target ------------------------------------------------------------

class TestLeakageTarget(unittest.TestCase):
    def test_sin_leakage_na(self):
        r = scientific_validity.evaluar_leakage_target({})[0]
        self.assertEqual(r.status, checks.STATUS_NA)

    def test_target_ausente_na(self):
        r = scientific_validity.evaluar_leakage_target({"leakage": {}})[0]
        self.assertEqual(r.status, checks.STATUS_NA)

    def test_target_sin_features_warn(self):
        r = scientific_validity.evaluar_leakage_target({"leakage": {"target": "y"}})[0]
        self.assertEqual(r.status, checks.STATUS_WARN)

    def test_target_en_features_fail(self):
        r = scientific_validity.evaluar_leakage_target({"leakage": {"target": "y", "features": ["a", "y"]}})[0]
        self.assertEqual(r.status, checks.STATUS_FAIL)

    def test_target_fuera_de_features_pass(self):
        r = scientific_validity.evaluar_leakage_target({"leakage": {"target": "y", "features": ["a", "b"]}})[0]
        self.assertEqual(r.status, checks.STATUS_PASS)


# --- Leakage forbidden ---------------------------------------------------------

class TestLeakageForbidden(unittest.TestCase):
    def test_sin_forbidden_features_na(self):
        r = scientific_validity.evaluar_leakage_forbidden({"leakage": {}})[0]
        self.assertEqual(r.status, checks.STATUS_NA)

    def test_con_forbidden_sin_features_warn(self):
        r = scientific_validity.evaluar_leakage_forbidden({"leakage": {"forbidden_features": ["a"]}})[0]
        self.assertEqual(r.status, checks.STATUS_WARN)

    def test_interseccion_no_vacia_fail(self):
        policy = {"leakage": {"forbidden_features": ["a"], "features": ["a", "b"]}}
        r = scientific_validity.evaluar_leakage_forbidden(policy)[0]
        self.assertEqual(r.status, checks.STATUS_FAIL)
        self.assertIn("a", r.message)

    def test_interseccion_vacia_pass(self):
        policy = {"leakage": {"forbidden_features": ["a"], "features": ["b", "c"]}}
        r = scientific_validity.evaluar_leakage_forbidden(policy)[0]
        self.assertEqual(r.status, checks.STATUS_PASS)


# --- Leakage split ---------------------------------------------------------------

class TestLeakageSplit(unittest.TestCase):
    def test_sin_ninguno_na(self):
        r = scientific_validity.evaluar_leakage_split({"leakage": {}})[0]
        self.assertEqual(r.status, checks.STATUS_NA)

    def test_solo_uno_declarado_warn(self):
        r = scientific_validity.evaluar_leakage_split({"leakage": {"train_max_utc": "2026-01-01T00:00:00Z"}})[0]
        self.assertEqual(r.status, checks.STATUS_WARN)

    def test_fecha_invalida_fail(self):
        policy = {"leakage": {"train_max_utc": "no-es-fecha", "validation_min_utc": "2026-01-01T00:00:00Z"}}
        r = scientific_validity.evaluar_leakage_split(policy)[0]
        self.assertEqual(r.status, checks.STATUS_FAIL)

    def test_train_max_mayor_igual_validation_min_fail(self):
        policy = {"leakage": {"train_max_utc": "2026-02-01T00:00:00Z", "validation_min_utc": "2026-01-01T00:00:00Z"}}
        r = scientific_validity.evaluar_leakage_split(policy)[0]
        self.assertEqual(r.status, checks.STATUS_FAIL)

    def test_train_max_menor_validation_min_pass(self):
        policy = {"leakage": {"train_max_utc": "2026-01-01T00:00:00Z", "validation_min_utc": "2026-02-01T00:00:00Z"}}
        r = scientific_validity.evaluar_leakage_split(policy)[0]
        self.assertEqual(r.status, checks.STATUS_PASS)


# --- Baseline --------------------------------------------------------------------

class TestBaseline(_BaseRepo):
    def test_no_requerido_na(self):
        r = scientific_validity.evaluar_baseline(self.repo, {"baseline": {"required": False}})[0]
        self.assertEqual(r.status, checks.STATUS_NA)

    def test_requerido_sin_evidence_path_fail(self):
        r = scientific_validity.evaluar_baseline(self.repo, {"baseline": {"required": True}})[0]
        self.assertEqual(r.status, checks.STATUS_FAIL)

    def test_evidence_path_inexistente_fail(self):
        policy = {"baseline": {"required": True, "evidence_path": "no_existe.txt"}}
        r = scientific_validity.evaluar_baseline(self.repo, policy)[0]
        self.assertEqual(r.status, checks.STATUS_FAIL)

    def test_archivo_vacio_fail(self):
        ruta = _escribir_evidencia(self.repo, contenido=b"")
        policy = {"baseline": {"required": True, "evidence_path": ruta}}
        r = scientific_validity.evaluar_baseline(self.repo, policy)[0]
        self.assertEqual(r.status, checks.STATUS_FAIL)

    def test_con_contenido_sin_hash_pass(self):
        ruta = _escribir_evidencia(self.repo)
        policy = {"baseline": {"required": True, "evidence_path": ruta}}
        r = scientific_validity.evaluar_baseline(self.repo, policy)[0]
        self.assertEqual(r.status, checks.STATUS_PASS)

    def test_con_hash_que_coincide_pass(self):
        ruta = _escribir_evidencia(self.repo, contenido=b"contenido fijo")
        hash_real = scientific_validity._hash_binario_sha256(self.repo / ruta)
        policy = {"baseline": {"required": True, "evidence_path": ruta, "evidence_sha256": hash_real}}
        r = scientific_validity.evaluar_baseline(self.repo, policy)[0]
        self.assertEqual(r.status, checks.STATUS_PASS)

    def test_con_hash_que_no_coincide_fail_evidencia_obsoleta(self):
        ruta = _escribir_evidencia(self.repo, contenido=b"contenido fijo")
        policy = {"baseline": {"required": True, "evidence_path": ruta, "evidence_sha256": "0" * 64}}
        r = scientific_validity.evaluar_baseline(self.repo, policy)[0]
        self.assertEqual(r.status, checks.STATUS_FAIL)
        self.assertIn("obsoleta", r.message)

    def test_evidence_path_fuera_del_repo_fail(self):
        fuera = Path(tempfile.mkdtemp(prefix="fuera_del_repo_"))
        try:
            policy = {"baseline": {"required": True, "evidence_path": str(fuera / "evidencia.txt")}}
            r = scientific_validity.evaluar_baseline(self.repo, policy)[0]
            self.assertEqual(r.status, checks.STATUS_FAIL)
        finally:
            shutil.rmtree(fuera, ignore_errors=True)


# --- Determinismo -----------------------------------------------------------------

class TestDeterminismo(_BaseRepo):
    def test_misma_corrida_mismo_resultado(self):
        _escribir_guardrails(self.repo, {"holdouts": ["data/holdout/**"]})
        _escribir_policy(
            self.repo,
            {
                "schema_version": 1,
                "holdout": {"declared": True},
                "leakage": {"target": "y", "features": ["a", "b"]},
            },
        )
        r1 = [r.to_dict() for r in scientific_validity.evaluar_scientific_checks(self.repo)]
        r2 = [r.to_dict() for r in scientific_validity.evaluar_scientific_checks(self.repo)]
        self.assertEqual(r1, r2)


# --- Read-only ---------------------------------------------------------------------

class TestReadOnly(_BaseRepo):
    def _snapshot(self) -> dict:
        rutas = (
            self.repo / ".harmessi" / "scientific-policy.json",
            self.repo / ".harmessi" / "project.json",
            self.repo / "openspec" / "lifecycle" / "state.json",
        )
        return {str(r): core.capturar_bytes(r) for r in rutas}

    def test_no_modifica_nada_repo_vacio(self):
        policy_existia_antes = (self.repo / ".harmessi" / "scientific-policy.json").exists()
        antes = self._snapshot()
        scientific_validity.evaluar_scientific_checks(self.repo)
        despues = self._snapshot()
        self.assertEqual(antes, despues)
        self.assertEqual(policy_existia_antes, (self.repo / ".harmessi" / "scientific-policy.json").exists())
        self.assertFalse((self.repo / ".harmessi" / "scientific-policy.json").exists())

    def test_no_modifica_nada_con_policy_declarada(self):
        _escribir_policy(self.repo, {"schema_version": 1, "baseline": {"required": True, "evidence_path": "no_existe.txt"}})
        antes = self._snapshot()
        scientific_validity.evaluar_scientific_checks(self.repo)
        despues = self._snapshot()
        self.assertEqual(antes, despues)

    def test_scientific_validity_py_nunca_llama_funciones_de_escritura(self):
        codigo = (REPO_ORIGEN / "tools" / "dsguard" / "scientific_validity.py").read_text(encoding="utf-8")
        for prohibido in (
            'open(ruta_config, "w"',
            'open(ruta, "w"',
            "escribir_estado(",
            "escribir_texto_atomico(",
            "escribir_control(",
            '"w")',
            "'w')",
        ):
            self.assertNotIn(prohibido, codigo, f"scientific_validity.py no debe contener {prohibido!r}")


class TestReadOnlyCli(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_repo_git_temporal()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def _snapshot(self) -> dict:
        rutas = (
            self.repo / ".harmessi" / "scientific-policy.json",
            self.repo / ".harmessi" / "project.json",
            self.repo / "openspec" / "lifecycle" / "state.json",
        )
        return {str(r): core.capturar_bytes(r) for r in rutas}

    def test_cli_no_modifica_nada(self):
        antes = self._snapshot()
        _correr_ds_guard(["science", "status"], self.repo)
        despues = self._snapshot()
        self.assertEqual(antes, despues)
        self.assertFalse((self.repo / ".harmessi" / "scientific-policy.json").exists())


# --- CLI -----------------------------------------------------------------------

class TestCli(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_repo_git_temporal()
        _escribir_policy(
            self.repo,
            {
                "schema_version": 1,
                "leakage": {"target": "y", "features": ["a", "y"]},
            },
        )

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_texto_exit_1_con_fail(self):
        resultado = _correr_ds_guard(["science", "status"], self.repo)
        self.assertEqual(resultado.returncode, 1)
        self.assertIn("Scientific Validity", resultado.stdout)

    def test_json_valido_con_resultados_longitud_7(self):
        resultado = _correr_ds_guard(["science", "status", "--json"], self.repo)
        self.assertEqual(resultado.returncode, 1)
        payload = json.loads(resultado.stdout)
        self.assertIn("resultados", payload)
        self.assertEqual(len(payload["resultados"]), 7)

    def test_exit_0_sin_fail(self):
        repo_sin_fail = _crear_repo_git_temporal(prefix="sci_validity_cli_sin_fail_")
        try:
            resultado = _correr_ds_guard(["science", "status", "--json"], repo_sin_fail)
            self.assertEqual(resultado.returncode, 0)
            payload = json.loads(resultado.stdout)
            for r in payload["resultados"]:
                self.assertNotEqual(r["status"], checks.STATUS_FAIL)
        finally:
            shutil.rmtree(repo_sin_fail, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()

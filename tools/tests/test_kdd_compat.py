"""Tests de `tools.dsguard.kdd_compat` (Change 2, v0.3:
20260914-lifecycle-migration-and-kdd-repoint) -- migración legacy v0.2 ->
lifecycle v0.3, merge de convergencia (evaluation+interpretation), roll-up de
fase-desde-pasos, y las operaciones repuntadas (`kdd_init`/`kdd_status`/
`kdd_transition`/`validar_antes_de_cerrar`/`sync_al_cerrar`).

Llama directo a las funciones de `kdd_compat` (sin CLI/subprocess) sobre
directorios temporales propios -- mismo criterio que ya usa `test_kdd.py`
para sus tests directos, `kdd_compat.py` no conoce Git. Nunca usa este
repositorio real como fixture.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ORIGEN = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ORIGEN / "tools"))

from dsguard import kdd_compat, lifecycle  # noqa: E402


def _crear_dir_temporal(prefix: str = "kdd_compat_test_") -> Path:
    return Path(tempfile.mkdtemp(prefix=prefix))


# --- Fixtures del legacy v0.2 ------------------------------------------------

def _entrada_legacy(estado: str, changes=None, evidencia=None, actualizado_utc=None) -> dict:
    return {
        "estado": estado,
        "changes": list(changes or []),
        "evidencia": list(evidencia or []),
        "actualizado_utc": actualizado_utc or "2026-01-01T00:00:00Z",
    }


def _legacy_variado(overrides: dict = None, historial: list = None) -> dict:
    """Legacy con VARIEDAD de estados en las 10 etapas -- no todo
    `no_iniciada`, para poder verificar merge/roll-up con casos reales."""
    etapas = {
        "problem_understanding": _entrada_legacy(
            "cerrada", changes=["c1"], evidencia=[{"change_id": "c1", "artefacto": "openspec/changes/c1/proposal.md"}]
        ),
        "data_understanding": _entrada_legacy("en_progreso"),
        "data_preparation": _entrada_legacy("cerrada"),
        "feature_engineering": _entrada_legacy("en_progreso"),
        "modeling": _entrada_legacy("no_iniciada"),
        "evaluation": _entrada_legacy("cerrada"),
        "interpretation": _entrada_legacy("en_progreso"),
        "production_readiness": _entrada_legacy("futura"),
        "deployment": _entrada_legacy("futura"),
        "monitoring": _entrada_legacy("futura"),
    }
    if overrides:
        etapas.update(overrides)
    return {
        "schema_version": 1,
        "creado_utc": "2025-12-01T00:00:00Z",
        "etapas": etapas,
        "historial_transiciones": historial or [],
    }


def _escribir_legacy(repo: Path, datos: dict) -> Path:
    ruta = kdd_compat.state_path_legacy(repo)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(datos, indent=2, ensure_ascii=False), encoding="utf-8")
    return ruta


class _BaseTemp(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_dir_temporal()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)


# --- migrar_desde_legacy: migración completa ---------------------------------

class TestMigracionCompleta(_BaseTemp):
    def test_migracion_completa_puebla_8_fases_y_5_pasos(self):
        _escribir_legacy(self.repo, _legacy_variado())
        resultado = kdd_compat.migrar_desde_legacy(self.repo)

        self.assertTrue(resultado["migrado"])
        estado = resultado["estado"]
        self.assertEqual(set(estado["crispdm"]["fases"].keys()), set(lifecycle.FASES_CRISPDM))
        self.assertEqual(set(estado["kdd"]["pasos"].keys()), set(lifecycle.PASOS_KDD))

    def test_migrado_desde_formato_kdd_v1(self):
        _escribir_legacy(self.repo, _legacy_variado())
        resultado = kdd_compat.migrar_desde_legacy(self.repo)
        self.assertEqual(resultado["estado"]["migrado_desde"]["formato"], "kdd_v1")
        self.assertEqual(resultado["estado"]["migrado_desde"]["schema_version_origen"], 1)

    def test_etapas_legacy_provenance_tiene_las_10_con_estado_legacy(self):
        legacy = _legacy_variado()
        _escribir_legacy(self.repo, legacy)
        resultado = kdd_compat.migrar_desde_legacy(self.repo)
        provenance = resultado["estado"]["migrado_desde"]["etapas_legacy"]
        self.assertEqual(set(provenance.keys()), set(kdd_compat.ETAPAS))
        for etapa in kdd_compat.ETAPAS:
            self.assertEqual(provenance[etapa]["estado_legacy"], legacy["etapas"][etapa]["estado"])


# --- Migración parcial / a mitad de lifecycle -------------------------------

class TestMigracionParcial(_BaseTemp):
    def test_cada_destino_recibe_exactamente_lo_que_le_corresponde(self):
        legacy = _legacy_variado()
        _escribir_legacy(self.repo, legacy)
        resultado = kdd_compat.migrar_desde_legacy(self.repo)
        estado = resultado["estado"]

        # Fases sin roll-up: 1:1 desde la etapa legacy correspondiente.
        self.assertEqual(estado["crispdm"]["fases"]["business_understanding"]["estado"], "cerrada")
        self.assertEqual(estado["crispdm"]["fases"]["production_readiness"]["estado"], "no_iniciada")
        self.assertEqual(estado["crispdm"]["fases"]["deployment"]["estado"], "no_iniciada")
        self.assertEqual(estado["crispdm"]["fases"]["monitoring"]["estado"], "no_iniciada")

        # Pasos 1:1 (sin convergencia): data_understanding->selection, modeling->data_mining.
        self.assertEqual(estado["kdd"]["pasos"]["selection"]["estado"], "en_progreso")
        self.assertEqual(estado["kdd"]["pasos"]["data_mining"]["estado"], "no_iniciada")

        # data_understanding (fase con 1 paso) hereda el estado de su único paso.
        self.assertEqual(estado["crispdm"]["fases"]["data_understanding"]["estado"], "en_progreso")
        self.assertEqual(estado["crispdm"]["fases"]["modeling"]["estado"], "no_iniciada")


# --- futura -> no_iniciada ---------------------------------------------------

class TestFuturaANoIniciada(_BaseTemp):
    def test_futura_migra_a_no_iniciada_con_provenance(self):
        _escribir_legacy(self.repo, _legacy_variado())
        resultado = kdd_compat.migrar_desde_legacy(self.repo)
        estado = resultado["estado"]

        for etapa in ("production_readiness", "deployment", "monitoring"):
            self.assertEqual(estado["crispdm"]["fases"][etapa]["estado"], "no_iniciada")
            self.assertEqual(
                estado["migrado_desde"]["etapas_legacy"][etapa]["estado_legacy"], "futura"
            )

    def test_futura_con_evidencia_acumulada_migra_integra(self):
        overrides = {
            "production_readiness": _entrada_legacy(
                "futura",
                changes=["c-futura"],
                evidencia=[{"change_id": "c-futura", "artefacto": "openspec/changes/c-futura/verification.md"}],
            )
        }
        _escribir_legacy(self.repo, _legacy_variado(overrides=overrides))
        resultado = kdd_compat.migrar_desde_legacy(self.repo)
        estado = resultado["estado"]

        fase = estado["crispdm"]["fases"]["production_readiness"]
        self.assertEqual(fase["estado"], "no_iniciada")
        self.assertEqual(fase["changes"], ["c-futura"])
        self.assertEqual(len(fase["evidencia"]), 1)
        self.assertEqual(fase["evidencia"][0]["change_id"], "c-futura")


# --- Convergencia evaluation + interpretation -------------------------------

class TestConvergenciaEvaluationInterpretation(_BaseTemp):
    def test_a_evaluation_cerrada_interpretation_en_progreso_da_cerrada(self):
        overrides = {
            "evaluation": _entrada_legacy("cerrada", actualizado_utc="2026-01-05T00:00:00Z"),
            "interpretation": _entrada_legacy("en_progreso", actualizado_utc="2026-01-01T00:00:00Z"),
        }
        _escribir_legacy(self.repo, _legacy_variado(overrides=overrides))
        estado = kdd_compat.migrar_desde_legacy(self.repo)["estado"]
        self.assertEqual(estado["crispdm"]["fases"]["evaluation"]["estado"], "cerrada")
        self.assertEqual(estado["kdd"]["pasos"]["interpretation_evaluation"]["estado"], "cerrada")

    def test_b_evaluation_en_progreso_interpretation_cerrada_da_cerrada(self):
        overrides = {
            "evaluation": _entrada_legacy("en_progreso", actualizado_utc="2026-01-01T00:00:00Z"),
            "interpretation": _entrada_legacy("cerrada", actualizado_utc="2026-01-05T00:00:00Z"),
        }
        _escribir_legacy(self.repo, _legacy_variado(overrides=overrides))
        estado = kdd_compat.migrar_desde_legacy(self.repo)["estado"]
        self.assertEqual(estado["crispdm"]["fases"]["evaluation"]["estado"], "cerrada")
        self.assertEqual(estado["kdd"]["pasos"]["interpretation_evaluation"]["estado"], "cerrada")

    def test_c_evidencia_duplicada_entre_ambas_dedup(self):
        ev_compartida = {"change_id": "c-eval", "artefacto": "openspec/changes/c-eval/verification.md"}
        overrides = {
            "evaluation": _entrada_legacy("en_progreso", changes=["c-eval"], evidencia=[ev_compartida]),
            "interpretation": _entrada_legacy("en_progreso", changes=["c-eval"], evidencia=[dict(ev_compartida)]),
        }
        _escribir_legacy(self.repo, _legacy_variado(overrides=overrides))
        estado = kdd_compat.migrar_desde_legacy(self.repo)["estado"]
        paso = estado["kdd"]["pasos"]["interpretation_evaluation"]
        self.assertEqual(paso["changes"], ["c-eval"])
        self.assertEqual(len(paso["evidencia"]), 1)

    def test_d_timestamp_max_evaluation_mas_nuevo(self):
        overrides = {
            "evaluation": _entrada_legacy("no_iniciada", actualizado_utc="2026-02-01T00:00:00Z"),
            "interpretation": _entrada_legacy("no_iniciada", actualizado_utc="2026-01-01T00:00:00Z"),
        }
        _escribir_legacy(self.repo, _legacy_variado(overrides=overrides))
        estado = kdd_compat.migrar_desde_legacy(self.repo)["estado"]
        self.assertEqual(
            estado["kdd"]["pasos"]["interpretation_evaluation"]["actualizado_utc"], "2026-02-01T00:00:00Z"
        )

    def test_d_timestamp_max_interpretation_mas_nuevo(self):
        overrides = {
            "evaluation": _entrada_legacy("no_iniciada", actualizado_utc="2026-01-01T00:00:00Z"),
            "interpretation": _entrada_legacy("no_iniciada", actualizado_utc="2026-02-01T00:00:00Z"),
        }
        _escribir_legacy(self.repo, _legacy_variado(overrides=overrides))
        estado = kdd_compat.migrar_desde_legacy(self.repo)["estado"]
        self.assertEqual(
            estado["kdd"]["pasos"]["interpretation_evaluation"]["actualizado_utc"], "2026-02-01T00:00:00Z"
        )


# --- Roll-up data_preparation (preprocessing + transformation) --------------

class TestRollupDataPreparation(_BaseTemp):
    def _migrar_con(self, estado_preprocessing: str, estado_transformation: str) -> str:
        overrides = {
            "data_preparation": _entrada_legacy(estado_preprocessing),
            "feature_engineering": _entrada_legacy(estado_transformation),
        }
        repo = _crear_dir_temporal()
        try:
            _escribir_legacy(repo, _legacy_variado(overrides=overrides))
            estado = kdd_compat.migrar_desde_legacy(repo)["estado"]
            return estado["crispdm"]["fases"]["data_preparation"]["estado"]
        finally:
            shutil.rmtree(repo, ignore_errors=True)

    def test_a_cerrada_no_iniciada_da_en_progreso(self):
        self.assertEqual(self._migrar_con("cerrada", "no_iniciada"), "en_progreso")

    def test_b_cerrada_en_progreso_da_en_progreso(self):
        self.assertEqual(self._migrar_con("cerrada", "en_progreso"), "en_progreso")

    def test_c_ambas_cerrada_da_cerrada(self):
        self.assertEqual(self._migrar_con("cerrada", "cerrada"), "cerrada")

    def test_d_ambas_no_iniciada_da_no_iniciada(self):
        self.assertEqual(self._migrar_con("no_iniciada", "no_iniciada"), "no_iniciada")

    def test_e_invarianza_de_orden_de_construccion_del_dict_origen(self):
        etapas_a = {
            "data_preparation": _entrada_legacy("cerrada"),
            "feature_engineering": _entrada_legacy("no_iniciada"),
        }
        etapas_b = {
            "feature_engineering": _entrada_legacy("no_iniciada"),
            "data_preparation": _entrada_legacy("cerrada"),
        }
        legacy_a = _legacy_variado(overrides=etapas_a)
        legacy_b = _legacy_variado(overrides=etapas_b)

        repo_a, repo_b = _crear_dir_temporal(), _crear_dir_temporal()
        try:
            _escribir_legacy(repo_a, legacy_a)
            _escribir_legacy(repo_b, legacy_b)
            estado_a = kdd_compat.migrar_desde_legacy(repo_a)["estado"]
            estado_b = kdd_compat.migrar_desde_legacy(repo_b)["estado"]
            self.assertEqual(
                estado_a["crispdm"]["fases"]["data_preparation"]["estado"],
                estado_b["crispdm"]["fases"]["data_preparation"]["estado"],
            )
        finally:
            shutil.rmtree(repo_a, ignore_errors=True)
            shutil.rmtree(repo_b, ignore_errors=True)

    def test_e_invarianza_de_orden_directo_sobre_calcular_estado_fase(self):
        self.assertEqual(
            lifecycle.calcular_estado_fase(["cerrada", "no_iniciada"]),
            lifecycle.calcular_estado_fase(["no_iniciada", "cerrada"]),
        )


# --- historial_transiciones preservado ---------------------------------------

class TestHistorialTransiciones(_BaseTemp):
    def test_cada_entrada_legacy_aparece_con_legacy_y_traduccion(self):
        historial = [
            {"utc": "2026-01-02T00:00:00Z", "etapa": "modeling", "desde": "no_iniciada", "hacia": "en_progreso"},
            {"utc": "2026-01-03T00:00:00Z", "etapa": "interpretation", "desde": "no_iniciada", "hacia": "en_progreso"},
        ]
        _escribir_legacy(self.repo, _legacy_variado(historial=historial))
        estado = kdd_compat.migrar_desde_legacy(self.repo)["estado"]
        hist_out = estado["historial_transiciones"]
        self.assertEqual(len(hist_out), 2)

        entrada_modeling = next(h for h in hist_out if h["etapa_legacy"] == "modeling")
        self.assertEqual(entrada_modeling["fase_crispdm"], "modeling")
        self.assertEqual(entrada_modeling["paso_kdd"], "data_mining")

        entrada_interpretation = next(h for h in hist_out if h["etapa_legacy"] == "interpretation")
        self.assertEqual(entrada_interpretation["fase_crispdm"], "evaluation")
        self.assertEqual(entrada_interpretation["paso_kdd"], "interpretation_evaluation")


# --- Fail-closed: legacy corrupto / schema desconocida -----------------------

class TestLegacyCorrupto(_BaseTemp):
    def test_json_invalido_levanta_kddcompaterror_y_no_crea_lifecycle(self):
        ruta = kdd_compat.state_path_legacy(self.repo)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text("{invalido", encoding="utf-8")

        with self.assertRaises(kdd_compat.KddCompatError):
            kdd_compat.migrar_desde_legacy(self.repo)

        self.assertFalse(lifecycle.state_path(self.repo).exists())

    def test_schema_version_desconocida_levanta_kddcompaterror(self):
        legacy = _legacy_variado()
        legacy["schema_version"] = 999
        _escribir_legacy(self.repo, legacy)

        with self.assertRaises(kdd_compat.KddCompatError):
            kdd_compat.migrar_desde_legacy(self.repo)

        self.assertFalse(lifecycle.state_path(self.repo).exists())


# --- Idempotencia / fail-closed frente a lifecycle existente -----------------

class TestLifecycleExistenteONinguno(_BaseTemp):
    def test_lifecycle_ya_existe_y_valido_no_reescribe(self):
        lifecycle.lifecycle_init(self.repo)
        bytes_antes = lifecycle.state_path(self.repo).read_bytes()
        _escribir_legacy(self.repo, _legacy_variado())  # legacy también presente, no debería importar

        resultado = kdd_compat.migrar_desde_legacy(self.repo)
        bytes_despues = lifecycle.state_path(self.repo).read_bytes()

        self.assertFalse(resultado["migrado"])
        self.assertEqual(bytes_antes, bytes_despues)

    def test_lifecycle_corrupto_propaga_lifecycleestadoerror_sin_legacy(self):
        ruta = lifecycle.state_path(self.repo)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text("{invalido", encoding="utf-8")

        with self.assertRaises(lifecycle.LifecycleEstadoError):
            kdd_compat.migrar_desde_legacy(self.repo)

    def test_lifecycle_corrupto_propaga_lifecycleestadoerror_con_legacy_presente(self):
        ruta = lifecycle.state_path(self.repo)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text("{invalido", encoding="utf-8")
        _escribir_legacy(self.repo, _legacy_variado())

        with self.assertRaises(lifecycle.LifecycleEstadoError):
            kdd_compat.migrar_desde_legacy(self.repo)

        # Fail-closed: nunca cae a leer/escribir el legacy.
        bytes_legacy = kdd_compat.state_path_legacy(self.repo).read_bytes()
        datos_legacy = json.loads(bytes_legacy)
        self.assertEqual(datos_legacy["etapas"]["modeling"]["estado"], "no_iniciada")

    def test_ni_legacy_ni_lifecycle_no_crea_nada(self):
        resultado = kdd_compat.migrar_desde_legacy(self.repo)
        self.assertFalse(resultado["migrado"])
        self.assertIn("motivo", resultado)
        self.assertFalse(lifecycle.state_path(self.repo).exists())
        self.assertFalse(kdd_compat.state_path_legacy(self.repo).exists())


# --- Legacy nunca se borra ni se modifica ------------------------------------

class TestLegacyInmutable(_BaseTemp):
    def test_legacy_bytes_identicos_antes_y_despues_de_migrar(self):
        ruta = _escribir_legacy(self.repo, _legacy_variado())
        bytes_antes = ruta.read_bytes()
        kdd_compat.migrar_desde_legacy(self.repo)
        bytes_despues = ruta.read_bytes()
        self.assertEqual(bytes_antes, bytes_despues)


# --- kdd_transition repuntado -------------------------------------------------

class TestKddTransitionRepuntado(_BaseTemp):
    def test_transicion_con_paso_kdd_recalcula_fase_via_rollup(self):
        overrides = {
            "data_preparation": _entrada_legacy("cerrada"),
            "feature_engineering": _entrada_legacy("no_iniciada"),
        }
        _escribir_legacy(self.repo, _legacy_variado(overrides=overrides))
        kdd_compat.migrar_desde_legacy(self.repo)

        estado_antes = lifecycle.leer_estado(lifecycle.state_path(self.repo))
        self.assertEqual(estado_antes["crispdm"]["fases"]["data_preparation"]["estado"], "en_progreso")

        ok, findings = kdd_compat.kdd_transition(self.repo, "feature_engineering", "en_progreso")
        self.assertTrue(ok)
        self.assertEqual(findings, [])

        estado_despues = lifecycle.leer_estado(lifecycle.state_path(self.repo))
        self.assertEqual(estado_despues["kdd"]["pasos"]["transformation"]["estado"], "en_progreso")
        # preprocessing=cerrada + transformation=en_progreso -> en_progreso (sigue en_progreso, pero
        # recalculado vía rollup, no copiado directo).
        self.assertEqual(estado_despues["crispdm"]["fases"]["data_preparation"]["estado"], "en_progreso")

    def test_transicion_sin_paso_kdd_escribe_fase_directo(self):
        _escribir_legacy(self.repo, _legacy_variado(overrides={"problem_understanding": _entrada_legacy("no_iniciada")}))
        kdd_compat.migrar_desde_legacy(self.repo)

        estado_antes = lifecycle.leer_estado(lifecycle.state_path(self.repo))
        pasos_antes = json.dumps(estado_antes["kdd"]["pasos"], sort_keys=True)

        ok, findings = kdd_compat.kdd_transition(self.repo, "problem_understanding", "en_progreso")
        self.assertTrue(ok)
        self.assertEqual(findings, [])

        estado_despues = lifecycle.leer_estado(lifecycle.state_path(self.repo))
        self.assertEqual(estado_despues["crispdm"]["fases"]["business_understanding"]["estado"], "en_progreso")
        pasos_despues = json.dumps(estado_despues["kdd"]["pasos"], sort_keys=True)
        self.assertEqual(pasos_antes, pasos_despues)


# --- kdd_init sobre proyecto nuevo -------------------------------------------

class TestKddInitRepuntado(_BaseTemp):
    def test_init_sobre_proyecto_nuevo_crea_lifecycle_directo(self):
        estado, creado = kdd_compat.kdd_init(self.repo)
        self.assertTrue(creado)
        self.assertTrue(lifecycle.state_path(self.repo).exists())
        self.assertFalse(kdd_compat.state_path_legacy(self.repo).exists())


class TestOperacionesSobreLegacySinMigrar(_BaseTemp):
    def setUp(self):
        super().setUp()
        _escribir_legacy(self.repo, _legacy_variado())

    def test_kdd_init_levanta_kddcompaterror_mencionando_lifecycle_migrate(self):
        with self.assertRaises(kdd_compat.KddCompatError) as ctx:
            kdd_compat.kdd_init(self.repo)
        self.assertIn("lifecycle migrate", str(ctx.exception))

    def test_kdd_status_levanta_kddcompaterror_mencionando_lifecycle_migrate(self):
        with self.assertRaises(kdd_compat.KddCompatError) as ctx:
            kdd_compat.kdd_status(self.repo)
        self.assertIn("lifecycle migrate", str(ctx.exception))

    def test_kdd_transition_levanta_kddcompaterror_mencionando_lifecycle_migrate(self):
        with self.assertRaises(kdd_compat.KddCompatError) as ctx:
            kdd_compat.kdd_transition(self.repo, "modeling", "en_progreso")
        self.assertIn("lifecycle migrate", str(ctx.exception))


# --- sync_al_cerrar / validar_antes_de_cerrar --------------------------------

class TestSyncAlCerrarRepuntado(_BaseTemp):
    def setUp(self):
        super().setUp()
        kdd_compat.kdd_init(self.repo)

    def test_etapa_con_paso_agrega_evidencia_en_fase_y_en_paso(self):
        control = {"modo": "completo", "kdd": {"etapa_primaria": "modeling"}}
        resultado = kdd_compat.sync_al_cerrar(self.repo, control, "20260101-x")
        self.assertTrue(resultado["sincronizado"])

        estado = lifecycle.leer_estado(lifecycle.state_path(self.repo))
        self.assertIn("20260101-x", estado["crispdm"]["fases"]["modeling"]["changes"])
        self.assertIn("20260101-x", estado["kdd"]["pasos"]["data_mining"]["changes"])
        self.assertEqual(len(estado["crispdm"]["fases"]["modeling"]["evidencia"]), 1)
        self.assertEqual(len(estado["kdd"]["pasos"]["data_mining"]["evidencia"]), 1)

    def test_etapa_sin_paso_agrega_evidencia_solo_en_fase(self):
        control = {"modo": "completo", "kdd": {"etapa_primaria": "problem_understanding"}}
        resultado = kdd_compat.sync_al_cerrar(self.repo, control, "20260101-y")
        self.assertTrue(resultado["sincronizado"])

        estado = lifecycle.leer_estado(lifecycle.state_path(self.repo))
        self.assertIn("20260101-y", estado["crispdm"]["fases"]["business_understanding"]["changes"])
        for paso in estado["kdd"]["pasos"].values():
            self.assertNotIn("20260101-y", paso["changes"])

    def test_idempotente_no_duplica(self):
        control = {"modo": "completo", "kdd": {"etapa_primaria": "modeling"}}
        kdd_compat.sync_al_cerrar(self.repo, control, "20260101-x")
        kdd_compat.sync_al_cerrar(self.repo, control, "20260101-x")

        estado = lifecycle.leer_estado(lifecycle.state_path(self.repo))
        self.assertEqual(estado["crispdm"]["fases"]["modeling"]["changes"], ["20260101-x"])
        self.assertEqual(len(estado["crispdm"]["fases"]["modeling"]["evidencia"]), 1)
        self.assertEqual(estado["kdd"]["pasos"]["data_mining"]["changes"], ["20260101-x"])
        self.assertEqual(len(estado["kdd"]["pasos"]["data_mining"]["evidencia"]), 1)


class TestValidarAntesDeCerrarRepuntado(_BaseTemp):
    def test_sin_legacy_sin_lifecycle_finding_claro(self):
        control = {"modo": "completo", "kdd": {"etapa_primaria": "modeling"}}
        findings = kdd_compat.validar_antes_de_cerrar(self.repo, control)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].codigo, "KDD-NO-INICIALIZADO")

    def test_con_legacy_sin_migrar_finding_menciona_lifecycle_migrate(self):
        _escribir_legacy(self.repo, _legacy_variado())
        control = {"modo": "completo", "kdd": {"etapa_primaria": "modeling"}}
        findings = kdd_compat.validar_antes_de_cerrar(self.repo, control)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].codigo, "KDD-NO-INICIALIZADO")
        self.assertIn("lifecycle migrate", findings[0].mensaje)

    def test_con_lifecycle_corrupto_finding_kdd_estado_corrupto(self):
        kdd_compat.kdd_init(self.repo)
        lifecycle.state_path(self.repo).write_text("{invalido", encoding="utf-8")
        control = {"modo": "completo", "kdd": {"etapa_primaria": "modeling"}}
        findings = kdd_compat.validar_antes_de_cerrar(self.repo, control)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].codigo, "KDD-ESTADO-CORRUPTO")


if __name__ == "__main__":
    unittest.main()

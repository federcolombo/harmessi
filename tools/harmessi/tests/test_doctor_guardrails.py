"""Drift de `.claude/guardrails.json` y `HARMESSI-AUTONOMY-CONFIG` (R25-R31), E2E con
instalación real por la CLI de ds_init + Doctor (mismo patrón que `TestInstalacionRealPorCli`
de `test_doctor_governance.py`)."""
from __future__ import annotations

import io
import json
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from tools.harmessi import doctor as doctor_mod
from tools.harmessi.tests.test_doctor import (
    _crear_interprete_falso,
    _crear_repo_git_temporal,
    _mock_solo_interprete,
)

RUTA_GUARDRAILS = ".claude/guardrails.json"
BUDGETS_VALIDOS = {"aggregate_minutes": 120, "max_sessions": 3}


class _BaseInstalada(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_repo_git_temporal(prefix="doctor_guardrails_")
        from tools.ds_init.cli import main

        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            codigo = main(["install", "--destino", str(self.repo), "--nombre", "p", "--execute"])
        self.assertEqual(codigo, 0)
        self.ruta = self.repo / RUTA_GUARDRAILS

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def _leer(self) -> dict:
        return json.loads(self.ruta.read_text(encoding="utf-8"))

    def _escribir(self, datos: dict, **kwargs):
        self.ruta.write_text(json.dumps(datos, **kwargs), encoding="utf-8")

    def _doctor(self):
        _crear_interprete_falso(self.repo)
        with patch("tools.harmessi.doctor.subprocess.run", side_effect=_mock_solo_interprete(0, "")):
            resultados, _exit = doctor_mod.ejecutar(self.repo)
        return resultados

    @staticmethod
    def _drift(resultados, fragmento=RUTA_GUARDRAILS):
        return [
            r for r in resultados
            if r.codigo == "HARMESSI-DRIFT" and r.nivel == doctor_mod.NIVEL_WARN and fragmento in r.mensaje
        ]

    @staticmethod
    def _config(resultados):
        encontrados = [r for r in resultados if r.codigo == "HARMESSI-AUTONOMY-CONFIG"]
        assert len(encontrados) == 1, encontrados
        return encontrados[0]

    def _editar_autonomy(self, autonomy: dict, version=2):
        datos = self._leer()
        datos["version"] = version
        datos["autonomy"] = autonomy
        self._escribir(datos, indent=2)


class TestBaselineYMutables(_BaseInstalada):
    def test_baseline_limpio_sin_drift(self):
        resultados = self._doctor()
        self.assertEqual(self._drift(resultados, ""), [])
        self.assertIn(
            "HARMESSI-DRIFT", {r.codigo for r in resultados if r.nivel == doctor_mod.NIVEL_OK}
        )
        config = self._config(resultados)
        self.assertEqual(config.nivel, doctor_mod.NIVEL_OK)
        self.assertIn("supervised", config.mensaje)

    def test_version_modo_y_budgets_validos_sin_drift(self):
        self._editar_autonomy({"mode": "autonomous", "budgets": dict(BUDGETS_VALIDOS)})
        resultados = self._doctor()
        self.assertEqual(self._drift(resultados), [])
        config = self._config(resultados)
        self.assertEqual(config.nivel, doctor_mod.NIVEL_OK)
        self.assertIn("autonomous", config.mensaje)

    def test_limits_legacy_sin_drift(self):
        self._editar_autonomy(
            {"mode": "autonomous", "limits": {"max_sessions": 2, "max_total_minutes": 90}}
        )
        resultados = self._doctor()
        self.assertEqual(self._drift(resultados), [])
        config = self._config(resultados)
        self.assertEqual(config.nivel, doctor_mod.NIVEL_OK)
        self.assertIn("autonomous", config.mensaje)

    def test_reordenar_y_reformatear_sin_drift(self):
        datos = self._leer()
        invertido = {k: datos[k] for k in reversed(list(datos))}
        self._escribir(invertido, indent=4, separators=(",", " : "))
        resultados = self._doctor()
        self.assertEqual(self._drift(resultados), [])


class TestValoresInvalidosEnRutasMutables(_BaseInstalada):
    def _assert_sin_drift_con_error(self, autonomy):
        self._editar_autonomy(autonomy)
        resultados = self._doctor()
        self.assertEqual(self._drift(resultados), [])
        self.assertEqual(self._config(resultados).nivel, doctor_mod.NIVEL_ERROR)

    def test_modo_invalido(self):
        self._assert_sin_drift_con_error({"mode": "turbo", "budgets": dict(BUDGETS_VALIDOS)})

    def test_budgets_en_cero(self):
        self._assert_sin_drift_con_error(
            {"mode": "autonomous", "budgets": {"aggregate_minutes": 0, "max_sessions": 0}}
        )

    def test_budgets_no_dict(self):
        self._assert_sin_drift_con_error({"mode": "autonomous", "budgets": [1, 2]})

    def test_budget_auxiliar_invalido(self):
        self._assert_sin_drift_con_error(
            {"mode": "supervised", "budgets": {"session_minutes": True}}
        )

    def test_autonomous_sin_limites(self):
        self._assert_sin_drift_con_error({"mode": "autonomous"})

    def test_clave_desconocida_en_budgets_es_warn(self):
        self._editar_autonomy({"mode": "autonomous", "budgets": {**BUDGETS_VALIDOS, "otra": 1}})
        resultados = self._doctor()
        self.assertEqual(self._drift(resultados), [])
        self.assertEqual(self._config(resultados).nivel, doctor_mod.NIVEL_WARN)


class TestRutasNoMutablesSiMarcanDrift(_BaseInstalada):
    def _assert_drift(self, mutar, fragmento_ruta):
        datos = self._leer()
        mutar(datos)
        self._escribir(datos, indent=2)
        drift = self._drift(self._doctor())
        self.assertEqual(len(drift), 1, drift)
        self.assertIn(fragmento_ruta, drift[0].mensaje)

    def test_holdouts(self):
        self._assert_drift(lambda d: d.update(holdouts=["data/sellado/**"]), "holdouts")

    def test_write_scopes(self):
        self._assert_drift(lambda d: d.update(write_scopes={"x": ["src/**"]}), "write_scopes")

    def test_data_raw(self):
        self._assert_drift(lambda d: d.update(data_raw=["otro/**"]), "data_raw")

    def test_autonomy_source_access(self):
        def mutar(d):
            d["version"] = 2
            d["autonomy"] = {"mode": "supervised", "source_access": {"fuente_a": {"read": True, "write": False}}}

        self._assert_drift(mutar, "autonomy.source_access")

    def test_autonomy_sealed_sources(self):
        def mutar(d):
            d["version"] = 2
            d["autonomy"] = {"sealed_sources": ["fuente_a"]}

        self._assert_drift(mutar, "autonomy.sealed_sources")

    def test_clave_desconocida_top_level(self):
        self._assert_drift(lambda d: d.update(clave_nueva=1), "clave_nueva")

    def test_clave_desconocida_en_autonomy(self):
        def mutar(d):
            d["version"] = 2
            d["autonomy"] = {"mode": "supervised", "extra": 1}

        self._assert_drift(mutar, "autonomy.extra")


class TestFailClosedYOtrosVerbatim(_BaseInstalada):
    def test_json_roto_es_drift_fail_closed(self):
        self.ruta.write_text("{no es json", encoding="utf-8")
        resultados = self._doctor()
        self.assertEqual(len(self._drift(resultados)), 1)
        gj = [r for r in resultados if r.codigo == "HARMESSI-GUARDRAILS-JSON"]
        self.assertEqual([r.nivel for r in gj], [doctor_mod.NIVEL_ERROR])
        self.assertEqual(self._config(resultados).nivel, "N/A")

    def test_json_no_dict_es_drift_fail_closed(self):
        self.ruta.write_text("[1, 2]", encoding="utf-8")
        self.assertEqual(len(self._drift(self._doctor())), 1)

    def test_otro_verbatim_modificado_sigue_marcando_drift_por_hash(self):
        objetivo = self.repo / "tools" / "dsguard" / "core.py"
        objetivo.write_text(objetivo.read_text(encoding="utf-8") + "\n# modificado\n", encoding="utf-8")
        resultados = self._doctor()
        self.assertEqual(len(self._drift(resultados, "tools/dsguard/core.py")), 1)
        self.assertEqual(self._drift(resultados), [])


class TestBaselineNoIndependiente(_BaseInstalada):
    def test_destino_igual_a_origen_cae_a_warn_por_hash(self):
        self._editar_autonomy({"mode": "autonomous", "budgets": dict(BUDGETS_VALIDOS)})
        with patch.object(doctor_mod.manifest_mod, "raiz_repo_origen", return_value=self.repo):
            r = doctor_mod._drift_guardrails_json(self.ruta, RUTA_GUARDRAILS)
        self.assertIsNotNone(r)
        self.assertEqual(r.code, "HARMESSI-DRIFT")
        self.assertEqual(r.status, "WARN")

    def test_baseline_ausente_es_warn_fail_closed(self):
        self._editar_autonomy({"mode": "autonomous", "budgets": dict(BUDGETS_VALIDOS)})
        vacio = self.repo / "origen_vacio"
        vacio.mkdir()
        with patch.object(doctor_mod.manifest_mod, "raiz_repo_origen", return_value=vacio):
            r = doctor_mod._drift_guardrails_json(self.ruta, RUTA_GUARDRAILS)
        self.assertIsNotNone(r)
        self.assertEqual(r.status, "WARN")

    def test_baseline_ilegible_es_warn_fail_closed(self):
        origen = self.repo / "origen_roto"
        (origen / ".claude").mkdir(parents=True)
        (origen / ".claude" / "guardrails.json").write_text("{roto", encoding="utf-8")
        with patch.object(doctor_mod.manifest_mod, "raiz_repo_origen", return_value=origen):
            r = doctor_mod._drift_guardrails_json(self.ruta, RUTA_GUARDRAILS)
        self.assertIsNotNone(r)
        self.assertEqual(r.status, "WARN")


class TestAutonomyConfigCasosBorde(_BaseInstalada):
    def test_version_1_con_autonomous_es_error(self):
        self._editar_autonomy({"mode": "autonomous", "budgets": dict(BUDGETS_VALIDOS)}, version=1)
        resultados = self._doctor()
        self.assertEqual(self._drift(resultados), [])
        self.assertEqual(self._config(resultados).nivel, doctor_mod.NIVEL_ERROR)

    def test_limits_no_dict_es_error(self):
        self._editar_autonomy({"mode": "autonomous", "limits": [1]})
        self.assertEqual(self._config(self._doctor()).nivel, doctor_mod.NIVEL_ERROR)

    def test_autonomy_vacia_o_none_sin_error(self):
        for valor in ({}, None):
            self._editar_autonomy(valor)
            resultados = self._doctor()
            self.assertEqual(self._config(resultados).nivel, doctor_mod.NIVEL_OK, valor)
            self.assertIn("supervised", self._config(resultados).mensaje)


CAMPOS_T1_FALSOS = {
    "approval_channel": "console_confirmed",
    "confirmed_at": "2026-10-13T00:00:00Z",
    "channel_version": "console/v1",
}
RUTA_ADOPCIONES = "openspec/decisions/guardrails-adoptions.jsonl"


class _BaseAdopciones(_BaseInstalada):
    """Drift con re-adopciones (R53-R57). Usa el `guardrails_adoption` REAL."""

    def _plantilla(self) -> dict:
        origen = doctor_mod.manifest_mod.raiz_repo_origen() / RUTA_GUARDRAILS
        return json.loads(origen.read_text(encoding="utf-8"))

    def _agregar(self, clave: str, valor: str):
        datos = self._leer()
        datos.setdefault(clave, []).append(valor)
        self._escribir(datos, indent=2)

    def _adoptar(self):
        from tools.dsguard import guardrails_adoption as ga

        plan = ga.planificar_adopcion(
            self._leer(), self._plantilla(), ga.cargar_adopciones(self.repo)
        )
        self.assertFalse(plan.rechazos, plan.rechazos)
        ga.aplicar_adopcion(
            self.repo, plan, motivo="motivo", usuario="usuario", fecha="2026-10-13",
            campos_t1=CAMPOS_T1_FALSOS, esperado_hash_antes=plan.hash_antes,
        )

    def _registro(self):
        return self.repo / RUTA_ADOPCIONES

    def _pass_info(self, resultados):
        return [
            r for r in resultados
            if r.codigo == "HARMESSI-DRIFT" and r.nivel == doctor_mod.NIVEL_OK
            and "re-adopci" in r.mensaje
        ]


class TestDriftConAdopciones(_BaseAdopciones):
    def test_adicion_adoptada_sin_drift_y_pass_informativo(self):
        self._agregar("holdouts", "data/sellado/**")
        self._adoptar()
        control = self.repo / ".claude" / "harmessi" / "control.json"
        bytes_antes = control.read_bytes() if control.exists() else None
        resultados = self._doctor()
        self.assertEqual(self._drift(resultados), [])
        info = self._pass_info(resultados)
        self.assertEqual(len(info), 1, info)
        self.assertIn("holdouts", info[0].mensaje)
        # El managed hash no se actualiza para simular aceptación (R55/R59).
        if bytes_antes is not None:
            self.assertEqual(control.read_bytes(), bytes_antes)

    def test_extra_no_adoptado_warn_solo_esa_clave(self):
        self._agregar("holdouts", "data/sellado/**")
        self._adoptar()
        self._agregar("secretos_extra", "otro/**")
        drift = self._drift(self._doctor())
        self.assertEqual(len(drift), 1, drift)
        self.assertIn("rutas: secretos_extra", drift[0].mensaje)
        self.assertIn("re-adoptadas", drift[0].mensaje)

    def test_elemento_extra_en_clave_adoptada_es_drift(self):
        self._agregar("holdouts", "data/sellado/**")
        self._adoptar()
        self._agregar("holdouts", "data/otro/**")
        drift = self._drift(self._doctor())
        self.assertEqual(len(drift), 1, drift)
        self.assertIn("rutas: holdouts", drift[0].mensaje)

    def test_adoptado_eliminado_es_drift(self):
        self._agregar("holdouts", "data/sellado/**")
        self._adoptar()
        datos = self._leer()
        datos["holdouts"] = []
        datos["data_raw"] = []  # elimina un elemento de la plantilla
        self._escribir(datos, indent=2)
        drift = self._drift(self._doctor())
        self.assertEqual(len(drift), 1, drift)
        self.assertIn("data_raw", drift[0].mensaje)

    def test_clave_prohibida_cambiada_con_adopcion_de_otra_es_warn(self):
        self._agregar("holdouts", "data/sellado/**")
        self._adoptar()
        datos = self._leer()
        datos["excepciones"] = ["x/**"]
        self._escribir(datos, indent=2)
        drift = self._drift(self._doctor())
        self.assertEqual(len(drift), 1, drift)
        self.assertIn("rutas: excepciones", drift[0].mensaje)

    def test_cadena_rota_no_cubre_y_agrega_hallazgo(self):
        self._agregar("holdouts", "data/sellado/**")
        self._adoptar()
        registro = self._registro()
        lineas = registro.read_text(encoding="utf-8").splitlines()
        entrada = json.loads(lineas[0])
        entrada["motivo"] = "alterado a mano"  # el hash de la entrada ya no coincide
        lineas[0] = json.dumps(entrada)
        registro.write_text("\n".join(lineas) + "\n", encoding="utf-8")
        drift = self._drift(self._doctor())
        self.assertEqual(len(drift), 1, drift)
        self.assertIn("rutas: holdouts", drift[0].mensaje)
        self.assertIn("registro de adopciones no utilizable", drift[0].mensaje)

    def test_registro_invalido_sin_drift_de_claves_es_warn(self):
        # Solo cambia una ruta mutable (hash distinto, sin drift de claves) + registro corrupto.
        self._editar_autonomy({"mode": "autonomous", "budgets": dict(BUDGETS_VALIDOS)})
        registro = self._registro()
        registro.parent.mkdir(parents=True, exist_ok=True)
        registro.write_text("{no es json\n", encoding="utf-8")
        drift = self._drift(self._doctor())
        self.assertEqual(len(drift), 1, drift)
        self.assertIn("registro de adopciones no utilizable", drift[0].mensaje)

    def test_reorden_sin_adopcion_es_drift_no_pass(self):
        datos = self._leer()
        datos["data_raw"] = datos["data_raw"] + datos["data_raw"]  # duplicado, sin adopción
        self._escribir(datos, indent=2)
        resultados = self._doctor()
        self.assertEqual(self._pass_info(resultados), [])
        self.assertEqual(len(self._drift(resultados)), 1)

    def test_sin_registro_comportamiento_historico(self):
        self._agregar("holdouts", "data/sellado/**")
        self.assertFalse(self._registro().exists())
        resultados = self._doctor()
        drift = self._drift(resultados)
        self.assertEqual(len(drift), 1, drift)
        self.assertIn("rutas: holdouts", drift[0].mensaje)
        self.assertNotIn("re-adopt", drift[0].mensaje)
        self.assertEqual(self._pass_info(resultados), [])

    def test_guardrails_malformado_sigue_fail_closed(self):
        self._agregar("holdouts", "data/sellado/**")
        self._adoptar()
        self.ruta.write_text("{no es json", encoding="utf-8")
        drift = self._drift(self._doctor())
        self.assertEqual(len(drift), 1, drift)
        self.assertIn("no se pudo comparar", drift[0].mensaje)


class TestDriftAdopcionesModuloFalso(_BaseAdopciones):
    def test_modulo_ausente_equivale_a_sin_adopciones(self):
        self._agregar("holdouts", "data/sellado/**")
        with patch.object(doctor_mod, "guardrails_adoption", None):
            drift = self._drift(self._doctor())
        self.assertEqual(len(drift), 1, drift)
        self.assertIn("rutas: holdouts", drift[0].mensaje)

    def test_excepcion_del_modulo_es_fail_closed(self):
        from types import SimpleNamespace

        def _explota(_raiz):
            raise RuntimeError("boom")

        falso = SimpleNamespace(cargar_adopciones=_explota, rutas_cubiertas=lambda *a: set())
        self._agregar("holdouts", "data/sellado/**")
        with patch.object(doctor_mod, "guardrails_adoption", falso):
            drift = self._drift(self._doctor())
        self.assertEqual(len(drift), 1, drift)
        self.assertIn("rutas: holdouts", drift[0].mensaje)


if __name__ == "__main__":
    unittest.main()

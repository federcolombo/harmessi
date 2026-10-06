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


if __name__ == "__main__":
    unittest.main()

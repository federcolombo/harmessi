"""Unit tests de `tools/dsguard/guardrails_drift.py` (R25-R30)."""
from __future__ import annotations

import ast
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.autonomy.policy import parse_autonomy_policy  # noqa: E402
from tools.dsguard import guardrails_drift as gd  # noqa: E402

PLANTILLA = {
    "version": 1,
    "holdouts": [],
    "data_raw": ["data/raw/**"],
    "secretos_extra": [],
    "write_scopes": {},
    "excepciones": [],
}


def _con_autonomy(autonomy, version=2):
    datos = copy.deepcopy(PLANTILLA)
    datos["version"] = version
    datos["autonomy"] = autonomy
    return datos


def _validar(datos, guard=2):
    return gd.validar_autonomia_mutable(datos, guard, parse_autonomy_policy)


class TestNormalizar(unittest.TestCase):
    def test_quita_version_y_autonomy_mutable(self):
        datos = _con_autonomy({"mode": "autonomous", "version": 2, "budgets": {}, "limits": {}})
        self.assertEqual(
            gd.normalizar(datos), {k: v for k, v in PLANTILLA.items() if k != "version"}
        )

    def test_conserva_resto_de_autonomy(self):
        datos = _con_autonomy({"mode": "autonomous", "source_access": {"a": 1}})
        self.assertEqual(gd.normalizar(datos)["autonomy"], {"source_access": {"a": 1}})

    def test_no_muta_la_entrada(self):
        datos = _con_autonomy({"mode": "autonomous"})
        copia = copy.deepcopy(datos)
        gd.normalizar(datos)
        self.assertEqual(datos, copia)

    def test_no_dict_levanta(self):
        with self.assertRaises(ValueError):
            gd.normalizar([1])

    def test_rutas_mutables_cerradas(self):
        self.assertEqual(
            gd.RUTAS_MUTABLES,
            ("version", "autonomy.mode", "autonomy.version", "autonomy.budgets", "autonomy.limits"),
        )


class TestComparar(unittest.TestCase):
    def test_identicos_y_mutables_sin_drift(self):
        self.assertEqual(gd.comparar(PLANTILLA, PLANTILLA), [])
        actual = _con_autonomy({"mode": "autonomous", "budgets": {"max_sessions": 2}})
        self.assertEqual(gd.comparar(actual, PLANTILLA), [])

    def test_cada_ruta_mutable_no_da_drift_y_una_clave_fuera_si(self):
        for ruta in gd.RUTAS_MUTABLES:
            actual = copy.deepcopy(PLANTILLA)
            if "." in ruta:
                _, sub = ruta.split(".", 1)
                actual["autonomy"] = {sub: {"x": 1}}
            else:
                actual[ruta] = 99
            self.assertEqual(gd.comparar(actual, PLANTILLA), [], ruta)
        fuera = _con_autonomy({"mode": "autonomous", "no_mutable": 1})
        self.assertEqual(gd.comparar(fuera, PLANTILLA), ["autonomy.no_mutable"])

    def test_orden_de_claves_irrelevante(self):
        invertido = {k: PLANTILLA[k] for k in reversed(list(PLANTILLA))}
        self.assertEqual(gd.comparar(invertido, PLANTILLA), [])

    def test_primer_nivel(self):
        actual = copy.deepcopy(PLANTILLA)
        actual["holdouts"] = ["x"]
        actual["nueva"] = 1
        self.assertEqual(gd.comparar(actual, PLANTILLA), ["holdouts", "nueva"])

    def test_claves_de_autonomy(self):
        actual = _con_autonomy({"mode": "autonomous", "sealed_sources": ["a"], "extra": 1})
        self.assertEqual(gd.comparar(actual, PLANTILLA), ["autonomy.extra", "autonomy.sealed_sources"])

    def test_autonomy_no_dict_es_drift(self):
        self.assertEqual(gd.comparar(_con_autonomy("x"), PLANTILLA), ["autonomy"])

    def test_true_no_es_uno(self):
        a = copy.deepcopy(PLANTILLA)
        b = copy.deepcopy(PLANTILLA)
        a["flag"], b["flag"] = True, 1
        self.assertEqual(gd.comparar(a, b), ["flag"])

    def test_no_dict_levanta(self):
        with self.assertRaises(ValueError):
            gd.comparar(None, PLANTILLA)
        with self.assertRaises(ValueError):
            gd.comparar(PLANTILLA, "x")


class TestValidarAutonomiaMutable(unittest.TestCase):
    def _niveles(self, datos, guard=2):
        return {(h["path"], h["nivel"]) for h in _validar(datos, guard)}

    def test_sin_autonomy_o_valida(self):
        self.assertEqual(_validar(PLANTILLA), [])
        valida = _con_autonomy({"mode": "autonomous", "budgets": {"aggregate_minutes": 60, "max_sessions": 2}})
        self.assertEqual(_validar(valida), [])
        legacy = _con_autonomy({"mode": "autonomous", "limits": {"max_sessions": 2, "max_total_minutes": 60}})
        self.assertEqual(_validar(legacy), [])

    def test_autonomy_vacia_o_none_sin_error(self):
        self.assertEqual(_validar(_con_autonomy({})), [])
        self.assertEqual(_validar(_con_autonomy(None)), [])

    def test_no_dict_es_error(self):
        self.assertEqual([x["nivel"] for x in _validar([1])], ["error"])

    def test_limits_con_clave_extra_es_warn_y_budgets_anidado_es_error(self):
        # Cierre de revisión ciclo 2: mutable != válido, también para subárboles.
        extra = _con_autonomy({"mode": "autonomous", "limits": {"max_sessions": 2, "max_total_minutes": 60, "x": 1}})
        niveles = {h["nivel"] for h in _validar(extra)}
        self.assertEqual(niveles, {"warn"})
        anidado = _con_autonomy(
            {"mode": "supervised", "budgets": {"session_minutes": {"a": 1}}}
        )
        self.assertIn("error", {h["nivel"] for h in _validar(anidado)})

    def test_modo_invalido(self):
        self.assertIn(("mode", "error"), self._niveles(_con_autonomy({"mode": "turbo"})))

    def test_autonomous_sin_limites(self):
        niveles = {n for _p, n in self._niveles(_con_autonomy({"mode": "autonomous"}))}
        self.assertEqual(niveles, {"error"})

    def test_version_baja_o_invalida(self):
        datos = _con_autonomy({"mode": "autonomous", "budgets": {"aggregate_minutes": 1, "max_sessions": 1}}, version=1)
        self.assertTrue(any(h["nivel"] == "error" for h in _validar(datos)))
        datos["version"] = "2"
        self.assertTrue(any(h["nivel"] == "error" for h in _validar(datos)))

    def test_guard_version_baja(self):
        datos = _con_autonomy({"mode": "autonomous", "budgets": {"aggregate_minutes": 1, "max_sessions": 1}})
        self.assertTrue(any(h["nivel"] == "error" for h in _validar(datos, 1)))

    def test_budgets_invalidos(self):
        for clave in gd.CLAVES_BUDGETS:
            for malo in (0, -1, True, "3", 1.5):
                datos = _con_autonomy({"mode": "supervised", "budgets": {clave: malo}})
                self.assertIn(("budgets.%s" % clave, "error"), self._niveles(datos), (clave, malo))

    def test_budgets_y_limits_no_dict(self):
        self.assertIn(("budgets", "error"), self._niveles(_con_autonomy({"budgets": 3})))
        self.assertIn(("limits", "error"), self._niveles(_con_autonomy({"limits": []})))

    def test_claves_desconocidas_son_warn(self):
        niveles = self._niveles(_con_autonomy({"budgets": {"x": 1}, "limits": {"y": 1}}))
        self.assertIn(("budgets.x", "warn"), niveles)
        self.assertIn(("limits.y", "warn"), niveles)
        self.assertFalse(any(n == "error" for _p, n in niveles))

    def test_sin_parse_policy_fail_closed(self):
        h = gd.validar_autonomia_mutable(_con_autonomy({"mode": "autonomous"}), 2)
        self.assertEqual([(x["code"], x["nivel"]) for x in h], [("AUTONOMY-POLICY-UNAVAILABLE", "error")])
        self.assertEqual(gd.validar_autonomia_mutable(PLANTILLA, 2), [])

    def test_modo_efectivo_sale_de_la_policy(self):
        valida = _con_autonomy({"mode": "autonomous", "budgets": {"aggregate_minutes": 60, "max_sessions": 2}})
        self.assertEqual(gd.evaluar_autonomia(valida, 2, parse_autonomy_policy)[1], "autonomous")
        degradada = _con_autonomy({"mode": "autonomous"})
        self.assertEqual(gd.evaluar_autonomia(degradada, 2, parse_autonomy_policy)[1], "supervised")
        self.assertEqual(gd.evaluar_autonomia(PLANTILLA, 2, parse_autonomy_policy)[1], "supervised")


class TestSinImportDeAutonomy(unittest.TestCase):
    def test_guardrails_drift_no_referencia_autonomy(self):
        ruta = Path(gd.__file__)
        arbol = ast.parse(ruta.read_text(encoding="utf-8"))
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Import):
                for alias in nodo.names:
                    self.assertNotIn("autonomy", alias.name)
            elif isinstance(nodo, ast.ImportFrom):
                self.assertNotIn("autonomy", nodo.module or "")
                for alias in nodo.names:
                    self.assertNotEqual(alias.name, "autonomy")
            elif isinstance(nodo, ast.Call):
                f = nodo.func
                nombre = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
                if nombre in ("import_module", "__import__"):
                    textos = [
                        n.value for a in nodo.args for n in ast.walk(a)
                        if isinstance(n, ast.Constant) and isinstance(n.value, str)
                    ]
                    self.assertFalse(any("autonomy" in t for t in textos), textos)
                    self.fail("guardrails_drift.py no debe usar import dinámico")


if __name__ == "__main__":
    unittest.main()

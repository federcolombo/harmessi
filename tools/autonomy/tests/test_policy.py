"""Tests de `tools/autonomy/policy.py` (v0.8 Change 0: R8, R10, R11-resolucion)."""
from __future__ import annotations

import ast
import fnmatch
import itertools
import unittest
from pathlib import Path

from tools.autonomy import core as autonomy_core
from tools.autonomy import policy as autonomy_policy
from tools.autonomy.policy import (
    AutonomyPolicy,
    SourceAccess,
    effective_source_access,
    is_source_sealed,
    parse_autonomy_policy,
    resolve_methodological_decision,
    sealed_coherence_findings,
)

CHANGE_ID = "20260928-project-autonomy-contract"
HASH_A = "a" * 64
HASH_B = "b" * 64


def _autonomy(**extra) -> dict:
    base = {
        "mode": "autonomous",
        "limits": {"max_sessions": 3, "max_total_minutes": 120},
    }
    base.update(extra)
    return base


def _guardrails(autonomy=None, version=2, **extra) -> dict:
    g = {"version": version}
    if autonomy is not None:
        g["autonomy"] = autonomy
    g.update(extra)
    return g


def _codigos(hallazgos) -> list:
    return [h.code for h in hallazgos]


class TestParseValida(unittest.TestCase):
    def test_autonomous_valida_con_guard_2(self):
        pol, hall = parse_autonomy_policy(_guardrails(_autonomy()), 2)
        self.assertEqual(pol.mode, "autonomous")
        self.assertEqual(pol.declared_mode, "autonomous")
        self.assertEqual(pol.max_sessions, 3)
        self.assertEqual(pol.max_total_minutes, 120)
        self.assertEqual(hall, [])
        self.assertFalse(pol.sealed_unknown)

    def test_supervised_explicita(self):
        pol, hall = parse_autonomy_policy(_guardrails({"mode": "supervised"}), 2)
        self.assertEqual(pol.mode, "supervised")
        self.assertEqual(pol.declared_mode, "supervised")
        self.assertEqual(hall, [])

    def test_guard_mayor_a_2_ok(self):
        pol, hall = parse_autonomy_policy(_guardrails(_autonomy()), 5)
        self.assertEqual(pol.mode, "autonomous")
        self.assertEqual(hall, [])

    def test_sellos_y_acceso_parseados(self):
        aut = _autonomy(
            sealed_sources=["s1", "s2"],
            source_access={"a": {"read": True, "write": True}},
        )
        pol, hall = parse_autonomy_policy(_guardrails(aut), 2)
        self.assertEqual(pol.sealed_sources, ("s1", "s2"))
        self.assertEqual(pol.source_access["a"], (True, True))
        self.assertEqual(hall, [])
        with self.assertRaises(TypeError):
            pol.source_access["z"] = (True, True)  # type: ignore[index]

    def test_frozen(self):
        pol, _ = parse_autonomy_policy(None, None)
        with self.assertRaises(Exception):
            pol.mode = "autonomous"  # type: ignore[misc]


class TestParseAusencia(unittest.TestCase):
    def test_sin_autonomy_supervised_sin_hallazgos(self):
        for entrada in ({}, {"version": 1}, {"version": 2}, {"otra": 1}):
            for guard in (None, 1, 2):
                pol, hall = parse_autonomy_policy(entrada, guard)
                self.assertEqual(pol.mode, "supervised")
                self.assertEqual(hall, [])
                self.assertFalse(pol.sealed_unknown)
                self.assertEqual(pol.sealed_sources, ())

    def test_autonomy_vacio_o_none(self):
        for aut in ({}, None):
            pol, hall = parse_autonomy_policy({"version": 2, "autonomy": aut}, None)
            self.assertEqual(pol.mode, "supervised")
            self.assertEqual(hall, [])
            self.assertFalse(pol.sealed_unknown)

    def test_ausencia_no_bloquea_nada(self):
        pol, _ = parse_autonomy_policy({}, None)
        self.assertFalse(is_source_sealed(pol, "x"))
        self.assertEqual(effective_source_access(pol, "x"), SourceAccess(True, False))


class TestParseDegradacion(unittest.TestCase):
    def test_faltan_limites(self):
        for limits in (None, {}, {"max_sessions": 3}, {"max_total_minutes": 5}):
            aut = {"mode": "autonomous"}
            if limits is not None:
                aut["limits"] = limits
            pol, hall = parse_autonomy_policy(_guardrails(aut), 2)
            self.assertEqual(pol.mode, "supervised")
            self.assertEqual(pol.declared_mode, "autonomous")
            self.assertIn(autonomy_core.CODE_POLICY_LIMITS, _codigos(hall))

    def test_limites_no_positivos_bool_float(self):
        for malo in (0, -1, True, False, 1.5, 2.0, "3", None):
            aut = _autonomy(limits={"max_sessions": malo, "max_total_minutes": 10})
            pol, hall = parse_autonomy_policy(_guardrails(aut), 2)
            self.assertEqual(pol.mode, "supervised", malo)
            self.assertIn(autonomy_core.CODE_POLICY_LIMITS, _codigos(hall))
            aut = _autonomy(limits={"max_sessions": 2, "max_total_minutes": malo})
            pol, hall = parse_autonomy_policy(_guardrails(aut), 2)
            self.assertEqual(pol.mode, "supervised", malo)

    def test_version_desconocida(self):
        for version in (0, 3, "2", True, 2.5, None, -1, [2]):
            pol, hall = parse_autonomy_policy(_guardrails(_autonomy(), version=version), 2)
            self.assertEqual(pol.mode, "supervised", version)
            self.assertIn(autonomy_core.CODE_POLICY_VERSION, _codigos(hall))

    def test_version_dentro_de_autonomy_desconocida(self):
        for version in (0, 3, "2", True):
            pol, hall = parse_autonomy_policy(_guardrails(_autonomy(version=version)), 2)
            self.assertEqual(pol.mode, "supervised", version)
            self.assertIn(autonomy_core.CODE_POLICY_VERSION, _codigos(hall))

    def test_autonomy_sin_version_superior(self):
        g = {"autonomy": _autonomy(sealed_sources=["h"])}
        pol, hall = parse_autonomy_policy(g, 2)
        self.assertEqual(pol.mode, "supervised")
        self.assertEqual(pol.sealed_sources, ("h",))
        self.assertIn(autonomy_core.CODE_POLICY_VERSION, _codigos(hall))
        self.assertTrue(is_source_sealed(pol, "h"))
        pol, hall = parse_autonomy_policy({"autonomy": _autonomy()}, 2)
        self.assertEqual(pol.mode, "supervised")
        self.assertIn(autonomy_core.CODE_POLICY_VERSION, _codigos(hall))

    def test_autonomy_version_1_conserva_sellos(self):
        g = _guardrails(_autonomy(sealed_sources=["h"]), version=1)
        pol, hall = parse_autonomy_policy(g, 2)
        self.assertEqual(pol.mode, "supervised")
        self.assertEqual(pol.sealed_sources, ("h",))
        self.assertIn(autonomy_core.CODE_POLICY_VERSION, _codigos(hall))

    def test_autonomy_vacio_sin_version_sin_hallazgos(self):
        for aut in ({}, None):
            pol, hall = parse_autonomy_policy({"autonomy": aut}, None)
            self.assertEqual(pol.mode, "supervised")
            self.assertEqual(hall, [])

    def test_autonomy_con_version_1(self):
        pol, hall = parse_autonomy_policy(_guardrails(_autonomy(version=1)), 2)
        self.assertEqual(pol.mode, "supervised")
        self.assertIn(autonomy_core.CODE_POLICY_VERSION, _codigos(hall))
        pol, hall = parse_autonomy_policy(_guardrails(_autonomy(), version=1), 2)
        self.assertEqual(pol.mode, "supervised")
        self.assertIn(autonomy_core.CODE_POLICY_VERSION, _codigos(hall))

    def test_guard_none(self):
        pol, hall = parse_autonomy_policy(_guardrails(_autonomy()), None)
        self.assertEqual(pol.mode, "supervised")
        self.assertIn(autonomy_core.CODE_POLICY_UNSUPPORTED, _codigos(hall))

    def test_guard_version_1(self):
        pol, hall = parse_autonomy_policy(_guardrails(_autonomy()), 1)
        self.assertEqual(pol.mode, "supervised")
        self.assertIn(autonomy_core.CODE_POLICY_UNSUPPORTED, _codigos(hall))

    def test_guard_tipos_invalidos(self):
        for guard in (True, "2", 2.0, 0, -1, [], {}):
            pol, hall = parse_autonomy_policy(_guardrails(_autonomy()), guard)
            self.assertEqual(pol.mode, "supervised", guard)
            self.assertIn(autonomy_core.CODE_POLICY_UNSUPPORTED, _codigos(hall))

    def test_supervised_sin_sellos_no_requiere_guard(self):
        pol, hall = parse_autonomy_policy(_guardrails({"mode": "supervised"}), None)
        self.assertEqual(hall, [])
        self.assertEqual(pol.mode, "supervised")

    def test_sellos_declarados_requieren_guard(self):
        aut = {"mode": "supervised", "sealed_sources": ["s1"]}
        _, hall = parse_autonomy_policy(_guardrails(aut), None)
        self.assertIn(autonomy_core.CODE_POLICY_UNSUPPORTED, _codigos(hall))
        _, hall = parse_autonomy_policy(_guardrails(aut), 2)
        self.assertEqual(hall, [])

    def test_tipos_invalidos(self):
        casos = [
            _autonomy(mode="root"),
            _autonomy(mode=1),
            _autonomy(mode=["autonomous"]),
            _autonomy(limits=[1, 2]),
            _autonomy(limits="x"),
            _autonomy(source_access=[1]),
            _autonomy(source_access={"a": {"read": "si", "write": False}}),
            _autonomy(source_access={"a": {"read": True}}),
            _autonomy(source_access={"a": True}),
            _autonomy(source_access={1: {"read": True, "write": True}}),
            _autonomy(sealed_sources="s1"),
            _autonomy(sealed_sources=[1]),
            _autonomy(sealed_sources=["ok", ""]),
        ]
        for aut in casos:
            pol, hall = parse_autonomy_policy(_guardrails(aut), 2)
            self.assertEqual(pol.mode, "supervised", aut)
            self.assertTrue(hall, aut)

    def test_acceso_invalido_queda_cerrado(self):
        aut = _autonomy(source_access={"a": {"read": "si", "write": True}})
        pol, _ = parse_autonomy_policy(_guardrails(aut), 2)
        self.assertEqual(effective_source_access(pol, "a"), SourceAccess(False, False))

    def test_claves_desconocidas_toleradas(self):
        aut = _autonomy(bogus=True, mode_extra="autonomous")
        pol, hall = parse_autonomy_policy(_guardrails(aut), 2)
        self.assertEqual(pol.mode, "autonomous")
        self.assertEqual(
            sorted(h.path for h in hall), ["bogus", "mode_extra"]
        )
        self.assertTrue(all(h.code == autonomy_core.CODE_POLICY_UNKNOWN_KEY for h in hall))
        self.assertEqual(pol.sealed_sources, ())
        self.assertEqual(dict(pol.source_access), {})

    def test_clave_desconocida_no_habilita(self):
        aut = {"mode": "supervised", "autonomous": True, "enable": "autonomous"}
        pol, hall = parse_autonomy_policy(_guardrails(aut), 2)
        self.assertEqual(pol.mode, "supervised")
        self.assertEqual(pol.declared_mode, "supervised")
        self.assertEqual(_codigos(hall), [autonomy_core.CODE_POLICY_UNKNOWN_KEY] * 2)

    def test_entrada_no_dict_nunca_lanza(self):
        for entrada in (None, [], "x", 5, 1.5, True, (1,), object()):
            for guard in (None, 2, "x"):
                pol, _ = parse_autonomy_policy(entrada, guard)
                self.assertIsInstance(pol, AutonomyPolicy)
                self.assertEqual(pol.mode, "supervised")

    def test_no_dict_no_none_reporta_hallazgo(self):
        for entrada in ([], "x", 5):
            _, hall = parse_autonomy_policy(entrada, 2)
            self.assertEqual(_codigos(hall), [autonomy_core.CODE_POLICY_INVALID])

    def test_datos_raros_no_lanzan(self):
        raros = [
            {"autonomy": {1: 2}},
            {"autonomy": {"limits": {1: 2}, "mode": "autonomous"}},
            {"autonomy": {"source_access": {"a": {}}}},
            {"autonomy": {"sealed_sources": [None, ["x"], {}]}},
            {"autonomy": [1, 2]},
            {"autonomy": "autonomous"},
            {"autonomy": 5},
            {"autonomy": True},
            {"version": [], "autonomy": {"mode": "autonomous"}},
        ]
        for entrada in raros:
            pol, _ = parse_autonomy_policy(entrada, 2)
            self.assertEqual(pol.mode, "supervised", entrada)

    def test_modo_efectivo_nunca_autonomous_degradado(self):
        validos = _autonomy()
        degradadas = [
            (_guardrails(validos), None),
            (_guardrails(validos), 1),
            (_guardrails(validos), True),
            (_guardrails(validos, version=1), 2),
            (_guardrails(validos, version=3), 2),
            (_guardrails(validos, version="2"), 2),
            (_guardrails(validos, version=True), 2),
            (_guardrails(_autonomy(version=1)), 2),
            (_guardrails({"mode": "autonomous"}), 2),
            (_guardrails(_autonomy(limits={})), 2),
            (_guardrails(_autonomy(limits={"max_sessions": 0, "max_total_minutes": 1})), 2),
            (_guardrails(_autonomy(limits={"max_sessions": True, "max_total_minutes": 1})), 2),
            (_guardrails(_autonomy(limits={"max_sessions": 1.0, "max_total_minutes": 1})), 2),
            (_guardrails(_autonomy(mode="AUTONOMOUS")), 2),
            (_guardrails(_autonomy(mode=None)), 2),
            (_guardrails(_autonomy(sealed_sources=[3])), 2),
            (_guardrails(_autonomy(sealed_sources="a")), 2),
            (_guardrails(_autonomy(source_access="a")), 2),
            (_guardrails(_autonomy(source_access={"a": 1})), 2),
            ({"version": 2, "autonomy": "autonomous"}, 2),
            ({"version": 2, "autonomy": ["autonomous"]}, 2),
            ("autonomous", 2),
            ([], 2),
            (None, 2),
        ]
        for entrada, guard in degradadas:
            pol, _ = parse_autonomy_policy(entrada, guard)
            self.assertNotEqual(pol.mode, "autonomous", (entrada, guard))

    def test_sello_conservado_con_guard_none(self):
        aut = _autonomy(sealed_sources=["holdout"])
        pol, hall = parse_autonomy_policy(_guardrails(aut), None)
        self.assertEqual(pol.mode, "supervised")
        self.assertEqual(pol.sealed_sources, ("holdout",))
        self.assertIn(autonomy_core.CODE_POLICY_UNSUPPORTED, _codigos(hall))
        self.assertTrue(is_source_sealed(pol, "holdout"))
        self.assertEqual(effective_source_access(pol, "holdout"), SourceAccess(False, False))

    def test_sello_conservado_en_otras_degradaciones(self):
        for aut in (
            _autonomy(sealed_sources=["h"], limits={}),
            _autonomy(sealed_sources=["h"], version=1),
            _autonomy(sealed_sources=["h"], mode="x"),
        ):
            pol, _ = parse_autonomy_policy(_guardrails(aut), 2)
            self.assertEqual(pol.sealed_sources, ("h",))
            self.assertEqual(pol.mode, "supervised")
        pol, _ = parse_autonomy_policy(_guardrails(_autonomy(sealed_sources=["h"]), version=9), 2)
        self.assertEqual(pol.sealed_sources, ("h",))

    def test_sealed_unknown_autonomy_no_objeto(self):
        for aut in ("x", 5, ["a"], True):
            pol, hall = parse_autonomy_policy({"version": 2, "autonomy": aut}, 2)
            self.assertTrue(pol.sealed_unknown, aut)
            self.assertIn(autonomy_core.CODE_POLICY_INVALID, _codigos(hall))
            self.assertTrue(is_source_sealed(pol, "cualquiera"))
            self.assertEqual(effective_source_access(pol, "cualquiera"), SourceAccess(False, False))

    def test_sealed_unknown_sealed_sources_mal_formado(self):
        for sellos in ("s1", 5, {"a": 1}, [1], ["a", ""], [None], ["a", ["b"]]):
            pol, hall = parse_autonomy_policy(_guardrails({"sealed_sources": sellos}), 2)
            self.assertTrue(pol.sealed_unknown, sellos)
            self.assertIn(autonomy_core.CODE_POLICY_INVALID, _codigos(hall))
            self.assertTrue(is_source_sealed(pol, "otra"))
            self.assertEqual(effective_source_access(pol, "otra"), SourceAccess(False, False))

    def test_sealed_sources_lista_vacia_no_es_unknown(self):
        pol, hall = parse_autonomy_policy(_guardrails({"sealed_sources": []}), None)
        self.assertFalse(pol.sealed_unknown)
        self.assertEqual(hall, [])

    def test_determinista(self):
        entrada = _guardrails(_autonomy(bogus=1, zeta=2, sealed_sources=["a"]))
        r1 = parse_autonomy_policy(entrada, 2)
        r2 = parse_autonomy_policy(entrada, 2)
        self.assertEqual(r1[1], r2[1])
        self.assertEqual(r1[0].sealed_sources, r2[0].sealed_sources)


class _DictQueLanza(dict):
    def __contains__(self, key):
        raise RuntimeError("boom")

    def get(self, *args, **kwargs):
        raise RuntimeError("boom")

    def __getitem__(self, key):
        raise RuntimeError("boom")


class TestFailClosedCorreccion2(unittest.TestCase):
    def test_guardrails_no_dict_sealed_unknown(self):
        for entrada in ([], "x", 7, 1.5, True):
            pol, hall = parse_autonomy_policy(entrada, 2)
            self.assertTrue(pol.sealed_unknown, entrada)
            self.assertEqual(pol.mode, "supervised")
            self.assertEqual(_codigos(hall), [autonomy_core.CODE_POLICY_INVALID])
            self.assertTrue(is_source_sealed(pol, "cualquiera"))
            self.assertEqual(effective_source_access(pol, "cualquiera"), SourceAccess(False, False))

    def test_guardrails_none_no_bloquea(self):
        pol, hall = parse_autonomy_policy(None, None)
        self.assertFalse(pol.sealed_unknown)
        self.assertEqual(hall, [])
        self.assertFalse(is_source_sealed(pol, "cualquiera"))
        self.assertEqual(effective_source_access(pol, "cualquiera"), SourceAccess(True, False))

    def test_source_access_no_dict_cierra_todo(self):
        for acceso in ([], "x", 5, [{"a": 1}], None):
            pol, hall = parse_autonomy_policy(_guardrails({"source_access": acceso}), 2)
            self.assertTrue(pol.sealed_unknown, acceso)
            self.assertIn(autonomy_core.CODE_POLICY_INVALID, _codigos(hall))
            self.assertEqual(effective_source_access(pol, "a"), SourceAccess(False, False))

    def test_source_access_dict_valido_no_es_unknown(self):
        pol, _ = parse_autonomy_policy(_guardrails({"source_access": {"a": {"read": True, "write": False}}}), 2)
        self.assertFalse(pol.sealed_unknown)

    def test_entrada_individual_invalida_no_activa_unknown(self):
        pol, hall = parse_autonomy_policy(_guardrails({"source_access": {"a": {"read": 1}}}), 2)
        self.assertFalse(pol.sealed_unknown)
        self.assertIn(autonomy_core.CODE_POLICY_INVALID, _codigos(hall))
        self.assertEqual(effective_source_access(pol, "a"), SourceAccess(False, False))

    def test_sellos_no_canonicos(self):
        for malo in (" holdout", "Holdout", "", "a b", "holdout ", "a/b"):
            pol, hall = parse_autonomy_policy(_guardrails({"sealed_sources": ["ok", malo]}), 2)
            self.assertTrue(pol.sealed_unknown, malo)
            self.assertEqual(pol.sealed_sources, ("ok",))
            self.assertIn(
                (autonomy_core.CODE_POLICY_INVALID, autonomy_policy.DETAIL_SOURCE_ID_NOT_CANONICAL),
                [(h.code, h.detail_key) for h in hall],
            )
            self.assertEqual(effective_source_access(pol, "otra"), SourceAccess(False, False))

    def test_sellos_canonicos_no_unknown(self):
        pol, hall = parse_autonomy_policy(_guardrails({"sealed_sources": ["holdout", "a-1", "b_2"]}), 2)
        self.assertFalse(pol.sealed_unknown)
        self.assertEqual(hall, [])

    def test_clave_access_no_canonica(self):
        for malo in ("A", " a", "a b", "", 5):
            aut = {"source_access": {"ok": {"read": True, "write": True}, malo: {"read": True, "write": True}}}
            pol, hall = parse_autonomy_policy(_guardrails(aut), 2)
            self.assertTrue(pol.sealed_unknown, malo)
            self.assertIn(
                autonomy_policy.DETAIL_SOURCE_ID_NOT_CANONICAL, [h.detail_key for h in hall]
            )
            self.assertEqual(effective_source_access(pol, "ok"), SourceAccess(False, False))

    def test_consulta_id_no_canonico_sellado(self):
        pol, _ = parse_autonomy_policy(_guardrails({"sealed_sources": ["h"]}), 2)
        for consulta in ("H", " h", "h ", "", "a b", None, 3):
            self.assertTrue(is_source_sealed(pol, consulta), consulta)
            self.assertEqual(effective_source_access(pol, consulta, (True, True)), SourceAccess(False, False))
        self.assertFalse(is_source_sealed(pol, "nueva"))

    def test_coherencia_ids_no_canonicos(self):
        hall = sealed_coherence_findings(
            ["Bad"], {"data": "data/holdout/a.csv", " x": "data/holdout/b.csv", 3: "p"},
            ["data/holdout/*"], _matcher,
        )
        codigos = [(h.code, h.detail_key) for h in hall]
        self.assertEqual(codigos.count((autonomy_core.CODE_POLICY_INVALID, "source_id_not_canonical")), 3)
        self.assertIn(autonomy_core.CODE_SEALED_UNSEALED_HOLDOUT, _codigos(hall))
        # los ids no canonicos no generan comparacion
        self.assertNotIn(autonomy_core.CODE_SEALED_PATH_MISMATCH, _codigos(hall))
        self.assertEqual(sum(1 for h in hall if h.code == autonomy_core.CODE_SEALED_UNSEALED_HOLDOUT), 1)

    def test_rama_defensiva_except(self):
        entrada = _DictQueLanza({"autonomy": {"mode": "autonomous"}})
        pol, hall = parse_autonomy_policy(entrada, 2)
        self.assertEqual(pol.mode, "supervised")
        self.assertTrue(pol.sealed_unknown)
        self.assertEqual(_codigos(hall), [autonomy_core.CODE_POLICY_INVALID])
        self.assertTrue(is_source_sealed(pol, "x"))


class TestAccesoFuentes(unittest.TestCase):
    def _politica(self, sealed_unknown=False) -> AutonomyPolicy:
        aut = {
            "sealed_sources": ["sellada"],
            "source_access": {
                "rw": {"read": True, "write": True},
                "ro": {"read": True, "write": False},
                "wo": {"read": False, "write": True},
                "none": {"read": False, "write": False},
                "sellada": {"read": True, "write": True},
            },
        }
        pol, _ = parse_autonomy_policy(_guardrails(aut), 2)
        if sealed_unknown:
            pol, _ = parse_autonomy_policy({"autonomy": "x"}, 2)
        return pol

    def test_no_listada_read_only(self):
        pol = self._politica()
        self.assertEqual(effective_source_access(pol, "nueva"), SourceAccess(True, False))

    def test_sellada_cerrada_aunque_access_diga_otra_cosa(self):
        pol = self._politica()
        self.assertTrue(is_source_sealed(pol, "sellada"))
        self.assertFalse(is_source_sealed(pol, "rw"))
        self.assertEqual(effective_source_access(pol, "sellada"), SourceAccess(False, False))
        for registro in (None, SourceAccess(True, True), (True, True), {"read": True, "write": True}):
            self.assertEqual(
                effective_source_access(pol, "sellada", registro), SourceAccess(False, False)
            )

    def test_maximo_sin_registro(self):
        pol = self._politica()
        self.assertEqual(effective_source_access(pol, "rw"), SourceAccess(True, True))
        self.assertEqual(effective_source_access(pol, "ro"), SourceAccess(True, False))
        self.assertEqual(effective_source_access(pol, "wo"), SourceAccess(False, True))
        self.assertEqual(effective_source_access(pol, "none"), SourceAccess(False, False))

    def test_exhaustivo_efectivo_menor_o_igual_maximo(self):
        pol = self._politica()
        fuentes = ("rw", "ro", "wo", "none", "sellada", "nueva")
        bools = (False, True)
        for fuente in fuentes:
            if is_source_sealed(pol, fuente):
                maximo = (False, False)
            else:
                maximo = pol.source_access.get(fuente, (True, False))
            for reg_r, reg_w in itertools.product(bools, bools):
                for registro in (SourceAccess(reg_r, reg_w), (reg_r, reg_w), {"read": reg_r, "write": reg_w}):
                    ef = effective_source_access(pol, fuente, registro)
                    self.assertLessEqual(ef.read, maximo[0], (fuente, registro))
                    self.assertLessEqual(ef.write, maximo[1], (fuente, registro))
                    self.assertEqual(ef.read, maximo[0] and reg_r)
                    self.assertEqual(ef.write, maximo[1] and reg_w)
                    self.assertLessEqual(ef.read, reg_r)
                    self.assertLessEqual(ef.write, reg_w)

    def test_registro_invalido_cierra(self):
        pol = self._politica()
        for registro in ("rw", 5, [True], {"read": "x"}, (1, 1), object()):
            self.assertEqual(
                effective_source_access(pol, "rw", registro), SourceAccess(False, False), registro
            )

    def test_sealed_unknown_bloquea_todo(self):
        pol = self._politica(sealed_unknown=True)
        self.assertTrue(pol.sealed_unknown)
        for fuente in ("rw", "ro", "nueva", "sellada", ""):
            self.assertTrue(is_source_sealed(pol, fuente))
            for registro in (None, SourceAccess(True, True), (True, True)):
                self.assertEqual(
                    effective_source_access(pol, fuente, registro), SourceAccess(False, False)
                )

    def test_source_id_no_str_cerrado(self):
        pol = self._politica()
        for fuente in (None, 5, ["a"], ("a",)):
            self.assertTrue(is_source_sealed(pol, fuente))
            self.assertEqual(effective_source_access(pol, fuente), SourceAccess(False, False))


def _matcher(ruta, patrones) -> bool:
    return any(fnmatch.fnmatch(ruta, p) for p in patrones)


class TestCoherencia(unittest.TestCase):
    PATRONES = ["data/holdout/*", "data/sealed/**"]

    def test_coherente_sin_hallazgos(self):
        hall = sealed_coherence_findings(
            ["h"], {"h": "data/holdout/a.csv", "x": "data/raw/b.csv"}, self.PATRONES, _matcher
        )
        self.assertEqual(hall, [])

    def test_holdout_sin_sellar(self):
        hall = sealed_coherence_findings(
            [], {"h": "data/holdout/a.csv"}, self.PATRONES, _matcher
        )
        self.assertEqual(_codigos(hall), [autonomy_core.CODE_SEALED_UNSEALED_HOLDOUT])
        self.assertEqual(hall[0].path, "h")

    def test_sellada_sin_holdout(self):
        hall = sealed_coherence_findings(
            ["s"], {"s": "data/raw/a.csv"}, self.PATRONES, _matcher
        )
        self.assertEqual(_codigos(hall), [autonomy_core.CODE_SEALED_PATH_MISMATCH])
        self.assertEqual(hall[0].path, "s")

    def test_sellada_no_file_backed_sin_hallazgo(self):
        hall = sealed_coherence_findings(["db"], {}, self.PATRONES, _matcher)
        self.assertEqual(hall, [])
        hall = sealed_coherence_findings(["db"], {"x": "data/raw/a.csv"}, self.PATRONES, _matcher)
        self.assertEqual(hall, [])

    def test_ambas_direcciones_y_orden_determinista(self):
        fb = {"z": "data/holdout/z.csv", "a": "data/raw/a.csv", "m": "data/holdout/m.csv"}
        hall = sealed_coherence_findings(["a", "m"], fb, self.PATRONES, _matcher)
        self.assertEqual(
            [(h.code, h.path) for h in hall],
            [
                (autonomy_core.CODE_SEALED_PATH_MISMATCH, "a"),
                (autonomy_core.CODE_SEALED_UNSEALED_HOLDOUT, "z"),
            ],
        )

    def test_matcher_recibe_ruta_y_lista(self):
        vistos = []

        def matcher(ruta, patrones):
            vistos.append((ruta, list(patrones)))
            return False

        sealed_coherence_findings([], {"x": "a/b.csv"}, ("p1", "p2"), matcher)
        self.assertEqual(vistos, [("a/b.csv", ["p1", "p2"])])


def _ref(artefacto="proposal.md", hash_=HASH_A) -> dict:
    return {"change_id": CHANGE_ID, "artefacto": artefacto, "hash": hash_}


def _pre(tipo="metric_choice", **kw) -> dict:
    d = {
        "decision_type": tipo,
        "summary": "elegir metrica",
        "scope": ["notebooks/a.ipynb"],
        "approval_ref": _ref(),
    }
    d.update(kw)
    return d


class TestResolucion(unittest.TestCase):
    TIPOS = ("metric_choice", "split_strategy")

    def test_listada_valida_ambos_modos(self):
        for modo in autonomy_core.MODES:
            res = resolve_methodological_decision(modo, "metric_choice", [_pre()], self.TIPOS)
            esperado = autonomy_core.resolve_action("continue_preapproved_decision", modo)
            self.assertEqual(res.decision, esperado)
            self.assertEqual(res.approval_ref, autonomy_core.ApprovalRef(CHANGE_ID, "proposal.md", HASH_A))
            self.assertIsNone(res.decision.stop_code)

    def test_listada_instancia(self):
        inst = autonomy_core.PreApprovedDecision.from_dict(_pre())
        res = resolve_methodological_decision("autonomous", "metric_choice", [inst], self.TIPOS)
        self.assertEqual(res.approval_ref, inst.approval_ref)
        self.assertEqual(res.decision.action_class, "continue_preapproved_decision")

    def test_ref_de_la_decision_listada_exacta(self):
        lista = [
            _pre("split_strategy", approval_ref=_ref(hash_=HASH_B)),
            _pre("metric_choice", approval_ref=_ref(hash_=HASH_A)),
        ]
        res = resolve_methodological_decision("supervised", "metric_choice", lista, self.TIPOS)
        self.assertEqual(res.approval_ref.hash, HASH_A)
        res = resolve_methodological_decision("supervised", "split_strategy", lista, self.TIPOS)
        self.assertEqual(res.approval_ref.hash, HASH_B)

    def _assert_stop2(self, res, modo):
        self.assertEqual(res.decision.action_class, "decide_unlisted_methodological")
        self.assertEqual(res.decision.mode, modo)
        self.assertEqual(res.decision.outcome, "stop_human")
        self.assertEqual(res.decision.stop_code, "AUTONOMY-STOP-02")
        self.assertIsNone(res.approval_ref)

    def test_no_listada_stop_2(self):
        for modo in autonomy_core.MODES:
            for lista in ([], None, [_pre("split_strategy")], "x", 5):
                res = resolve_methodological_decision(modo, "metric_choice", lista, self.TIPOS)
                self._assert_stop2(res, modo)

    def test_tipo_desconocido_stop_2(self):
        for modo in autonomy_core.MODES:
            res = resolve_methodological_decision(modo, "raro", [_pre("raro")], self.TIPOS)
            self._assert_stop2(res, modo)
            res = resolve_methodological_decision(modo, "metric_choice", [_pre()], ())
            self._assert_stop2(res, modo)
            res = resolve_methodological_decision(modo, "metric_choice", [_pre()], None)
            self._assert_stop2(res, modo)

    def test_decision_type_no_str(self):
        for tipo in (None, 5, ["metric_choice"], ""):
            res = resolve_methodological_decision("autonomous", tipo, [_pre()], self.TIPOS)
            self._assert_stop2(res, "autonomous")

    def test_listada_invalida_stop_2(self):
        invalidas = [
            _pre(approval_ref=_ref(artefacto="design.md")),
            _pre(approval_ref=_ref(hash_="abc")),
            _pre(approval_ref=_ref(hash_=HASH_A.upper())),
            _pre(approval_ref=None),
            _pre(approval_ref={"artefacto": "proposal.md"}),
            _pre(approval_ref="x"),
            _pre(scope=[]),
            _pre(scope=["/abs/x"]),
            _pre(scope=["../x"]),
            _pre(scope=["C:/x"]),
            _pre(summary=""),
            _pre(extra=1),
        ]
        sin_ref = _pre()
        del sin_ref["approval_ref"]
        invalidas.append(sin_ref)
        for modo in autonomy_core.MODES:
            for item in invalidas:
                res = resolve_methodological_decision(modo, "metric_choice", [item], self.TIPOS)
                self._assert_stop2(res, modo)

    def test_duplicados_ambiguos_stop_2(self):
        lista = [_pre(approval_ref=_ref(hash_=HASH_A)), _pre(approval_ref=_ref(hash_=HASH_B))]
        for modo in autonomy_core.MODES:
            res = resolve_methodological_decision(modo, "metric_choice", lista, self.TIPOS)
            self._assert_stop2(res, modo)

    def test_duplicados_identicos_continuan(self):
        lista = [_pre(), _pre(summary="otro resumen")]
        for modo in autonomy_core.MODES:
            res = resolve_methodological_decision(modo, "metric_choice", lista, self.TIPOS)
            self.assertEqual(res.decision.action_class, "continue_preapproved_decision")
            self.assertEqual(res.approval_ref.hash, HASH_A)

    def test_duplicado_invalido_no_genera_ambiguedad(self):
        lista = [_pre(approval_ref=_ref(hash_=HASH_B, artefacto="design.md")), _pre()]
        res = resolve_methodological_decision("autonomous", "metric_choice", lista, self.TIPOS)
        self.assertEqual(res.approval_ref.hash, HASH_A)

    def test_invalida_primero_valida_despues(self):
        lista = [_pre(approval_ref=_ref(artefacto="otro.md")), _pre()]
        res = resolve_methodological_decision("autonomous", "metric_choice", lista, self.TIPOS)
        self.assertEqual(res.decision.action_class, "continue_preapproved_decision")
        self.assertEqual(res.approval_ref.artefacto, "proposal.md")

    def test_items_basura_no_lanzan(self):
        res = resolve_methodological_decision(
            "supervised", "metric_choice", [None, 5, "x", [], _pre()], self.TIPOS
        )
        self.assertEqual(res.decision.action_class, "continue_preapproved_decision")

    def test_modo_desconocido_lanza(self):
        for modo in ("root", "", None, 5, "AUTONOMOUS"):
            for lista in ([_pre()], []):
                with self.assertRaises(autonomy_core.AutonomyError) as cm:
                    resolve_methodological_decision(modo, "metric_choice", lista, self.TIPOS)
                self.assertEqual(cm.exception.code, autonomy_core.CODE_UNKNOWN_MODE)

    def test_frozen(self):
        res = resolve_methodological_decision("autonomous", "x", [], self.TIPOS)
        with self.assertRaises(Exception):
            res.approval_ref = None  # type: ignore[misc]

    def test_approval_ref_required_no_existe(self):
        self.assertFalse(hasattr(autonomy_policy, "approval_ref_required"))


class TestImportsYProsa(unittest.TestCase):
    PERMITIDOS = {
        "__future__", "dataclasses", "typing", "types", "re", "collections.abc",
    }

    def test_policy_no_importa_prohibidos(self):
        ruta = Path(autonomy_policy.__file__)
        arbol = ast.parse(ruta.read_text(encoding="utf-8"))
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Import):
                for alias in nodo.names:
                    self.assertIn(alias.name, self.PERMITIDOS)
            elif isinstance(nodo, ast.ImportFrom):
                if nodo.level == 1:
                    self.assertEqual([a.name for a in nodo.names], ["core"])
                else:
                    self.assertIn(nodo.module, self.PERMITIDOS)

    def test_constantes_str_publicas_sin_espacios(self):
        import re

        for nombre, valor in vars(autonomy_policy).items():
            if nombre.startswith("_") or not isinstance(valor, str):
                continue
            self.assertRegex(valor, r"^[A-Za-z0-9_.:-]+$", nombre)
            self.assertIsNotNone(re.fullmatch(r"[A-Za-z0-9_.:-]+", valor))

    def test_version_soportada(self):
        self.assertEqual(autonomy_policy.POLICY_SCHEMA_VERSION, 2)


class TestLimitsYBudgets(unittest.TestCase):
    """R6 de 20261005-operational-autonomy-hardening: `budgets` habilita `autonomous`."""

    def _parse(self, **autonomy):
        base = {"mode": "autonomous"}
        base.update(autonomy)
        return parse_autonomy_policy(_guardrails(base), 2)

    def test_budgets_only_autonomous(self):
        pol, hall = self._parse(budgets={"max_sessions": 4, "aggregate_minutes": 200})
        self.assertEqual(pol.mode, "autonomous")
        self.assertEqual(pol.max_sessions, 4)
        self.assertEqual(pol.max_total_minutes, 200)
        self.assertNotIn(autonomy_core.CODE_POLICY_LIMITS, _codigos(hall))

    def test_ambos_toma_el_minimo_en_los_dos_ordenes(self):
        pol, _ = self._parse(
            limits={"max_sessions": 3, "max_total_minutes": 300},
            budgets={"max_sessions": 5, "aggregate_minutes": 100},
        )
        self.assertEqual((pol.max_sessions, pol.max_total_minutes), (3, 100))
        pol, _ = self._parse(
            limits={"max_sessions": 9, "max_total_minutes": 50},
            budgets={"max_sessions": 5, "aggregate_minutes": 100},
        )
        self.assertEqual((pol.max_sessions, pol.max_total_minutes), (5, 50))
        self.assertEqual(pol.mode, "autonomous")

    def test_ejes_repartidos_entre_fuentes(self):
        pol, _ = self._parse(limits={"max_sessions": 3}, budgets={"aggregate_minutes": 90})
        self.assertEqual(pol.mode, "autonomous")
        self.assertEqual((pol.max_sessions, pol.max_total_minutes), (3, 90))

    def test_budgets_invalido_degrada(self):
        for valor in (0, -1, True, "5", 1.5):
            pol, hall = self._parse(
                limits={"max_sessions": 3, "max_total_minutes": 120},
                budgets={"aggregate_minutes": valor},
            )
            self.assertEqual(pol.mode, "supervised", valor)
            self.assertIn(autonomy_core.CODE_POLICY_LIMITS, _codigos(hall), valor)

    def test_budgets_sin_ejes_requeridos_degrada(self):
        pol, hall = self._parse(budgets={"session_minutes": 30})
        self.assertEqual(pol.mode, "supervised")
        self.assertIn(autonomy_core.CODE_POLICY_LIMITS, _codigos(hall))

    def test_budgets_no_dict_degrada(self):
        for valor in (None, 5, "x", [1]):
            pol, hall = self._parse(limits={"max_sessions": 3, "max_total_minutes": 120}, budgets=valor)
            self.assertEqual(pol.mode, "supervised", valor)
            self.assertIn(autonomy_core.CODE_POLICY_LIMITS, _codigos(hall), valor)

    def test_budgets_ya_no_es_clave_desconocida(self):
        _pol, hall = self._parse(budgets={"max_sessions": 4, "aggregate_minutes": 200})
        self.assertNotIn(autonomy_core.CODE_POLICY_UNKNOWN_KEY, _codigos(hall))

    def test_limits_only_identico(self):
        pol, hall = parse_autonomy_policy(_guardrails(_autonomy()), 2)
        self.assertEqual((pol.mode, pol.max_sessions, pol.max_total_minutes), ("autonomous", 3, 120))
        self.assertEqual(hall, [])


if __name__ == "__main__":
    unittest.main()

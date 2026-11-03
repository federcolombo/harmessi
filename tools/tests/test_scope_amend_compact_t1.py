"""Tests de la accion T1 compacta de `scope amend` (Change 20261027-v015-scope-closure-corrective, T4).

Reusa los fixtures CLI de `test_scope_amendments` (repo git temporal, canal T1 parcheado).
"""
from __future__ import annotations

import argparse
import dataclasses
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_scope_amendments import CID, PROPIA, _BaseCli, _resultado_ok, ds_guard, sa  # noqa: E402

from dsguard import sdd  # noqa: E402


def _rutas(n: int, prefijo: str = "src/m") -> list:
    return [f"{prefijo}{i}.py" for i in range(n)]


class TestAccionCompactaT1(_BaseCli):
    def plan_de(self, add=(), remove=()):
        args = argparse.Namespace(change_id=CID, add=list(add), remove=list(remove))
        return ds_guard._calcular_plan_scope(args, self.repo)[3]

    def test_accion_corta_conserva_formato_completo(self):
        plan = self.plan_de(add=["src/b.py"])
        accion = ds_guard._accion_scope(plan, CID)
        self.assertTrue(accion.startswith("scope-amend: +"))
        self.assertLessEqual(len(accion), 120)
        self.assertNotIn("hash=", accion)

    def test_hash_del_contexto_es_el_hash_diff_completo(self):
        rutas = _rutas(30)
        completo = sa.hash_diff(CID, self.plan_de(add=rutas))
        codigo, _o, err, m = self.correr(self.argv(add=rutas))
        self.assertEqual(codigo, 0, err)
        contexto = m.call_args[0][0]
        self.assertEqual(contexto["hash"], completo)
        self.assertEqual(len(contexto["hash"]), 64)
        self.assertLessEqual(len(contexto["accion"]), 120)
        self.assertTrue(contexto["accion"].endswith("hash=" + completo[:12]))
        self.assertNotIn("...", contexto["accion"])

    def test_rutas_distintas_misma_cantidad_dan_accion_compacta_con_hash_distinto(self):
        accion1 = ds_guard._accion_scope(self.plan_de(add=_rutas(30, "src/m")), CID)
        accion2 = ds_guard._accion_scope(self.plan_de(add=_rutas(30, "src/n")), CID)
        self.assertNotEqual(accion1, accion2)
        self.assertEqual(accion1.split(" hash=")[0], accion2.split(" hash=")[0])
        self.assertNotEqual(accion1.split("hash=")[1], accion2.split("hash=")[1])
        self.assertEqual(accion1, ds_guard._accion_scope(self.plan_de(add=_rutas(30, "src/m")), CID))

    def test_cambio_de_ruta_tras_confirmar_rechaza_sin_escribir_nada(self):
        rutas = _rutas(30)

        def carrera(_contexto):
            self.inyectar(["src/otra.py"])
            return _resultado_ok()

        codigo, _o, err, _m = self.correr(self.argv(add=rutas), efectos=carrera)
        self.assertEqual(codigo, 2)
        self.assertIn("el estado cambió", err)
        entradas = self.entradas()
        self.assertEqual(len(entradas), 1)  # solo la enmienda inyectada, ninguna de la corrida
        self.assertNotIn(rutas[0], entradas[0]["add"])

    def test_cambio_de_payload_tras_confirmar_rechaza_sin_escribir_nada(self):
        rutas = _rutas(30)
        real = ds_guard._calcular_plan_scope
        llamadas = []

        def calcular(args, repo_root):
            resultado = real(args, repo_root)
            llamadas.append(1)
            if len(llamadas) < 3:  # 1: pre-prompt, 2: replan previo al T1, 3: replan posterior
                return resultado
            change_dir, control, estado, plan, auto = resultado
            return change_dir, control, estado, dataclasses.replace(plan, hash_despues="0" * 64), auto

        with mock.patch.object(ds_guard, "_calcular_plan_scope", side_effect=calcular):
            codigo, _o, err, m = self.correr(self.argv(add=rutas))
        self.assertEqual(codigo, 2)
        m.assert_called_once()
        self.assertIn("el estado cambió", err)
        self.assertFalse(self.archivo().exists())

    def test_mas_de_60_rutas_exactas_cortas_se_confirman_y_se_guardan_completas(self):
        rutas = _rutas(65)
        codigo, _o, err, m = self.correr(self.argv(add=rutas))
        self.assertEqual(codigo, 0, err)
        m.assert_called_once()
        self.assertLessEqual(len(m.call_args[0][0]["accion"]), 120)
        entradas = self.entradas()
        self.assertEqual(len(entradas), 1)
        self.assertEqual(entradas[0]["add"], sorted(rutas + [PROPIA]))
        efectivas, hallazgos = self.efectivo()
        self.assertEqual(hallazgos, [])
        for r in rutas:
            self.assertIn(r, efectivas)

    def test_rutas_protegidas_siguen_rechazadas(self):
        for protegida in (".claude/settings.json", ".claude/guardrails.json", ".claude/settings.local.json"):
            codigo, _o, err, m = self.correr(self.argv(add=[protegida]))
            self.assertEqual(codigo, 2, protegida)
            self.assertIn("ruta protegida", err)
            self.assertIn("no puede autorizarse", err)
            m.assert_not_called()
        self.assertFalse(self.archivo().exists())

    def test_tupla_de_rutas_protegidas_intacta(self):
        self.assertEqual(sdd._ALCANCE_RUTAS_PROTEGIDAS, (
            ".claude/guardrails.json",
            ".claude/settings.json",
            ".claude/settings.local.json",
            "data/raw/x",
        ))


if __name__ == "__main__":
    unittest.main()

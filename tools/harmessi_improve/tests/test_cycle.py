"""Tests del ciclo acotado (v0.14 Change 5, R7-R9). Probes reales con FakeAdapter en tempdirs."""
from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from tools.harmessi_bench.core import EvalTarget
from tools.harmessi_improve import cycle as cy
from tools.harmessi_improve.budget import PresupuestoAgotado, PresupuestoInvalido
from tools.harmessi_improve.decision import EvidenciaInvalida
from tools.harmessi_improve.probe import ProbeCorrupto
from tools.harmessi_improve.cycle import CicloAnidado
from tools.harmessi_improve.policy import ProbePolicy
from tools.harmessi_improve.tests._fakes import MARCA_BASE, MARCA_CAND, FakeAdapter, crear_suite
from tools.harmessi_improve.tests._helpers import ACTIVO, PROVENANCE, crear_repo, snapshot

TODOS = "tok-1 tok-2 tok-3"
SOLO_1 = "tok-1"


class BaseCiclo(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._tmp_suite = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.addCleanup(self._tmp_suite.cleanup)
        self.raiz = crear_repo(Path(self._tmp.name))
        (self.raiz / ACTIVO).write_bytes(f"# Skill\n{MARCA_BASE}\n".encode("utf-8"))
        self.suite = crear_suite(Path(self._tmp_suite.name))
        self.target = EvalTarget("fake", model="m1", effort="low")
        self.dir_imp = self.raiz / ".harmessi" / "improvement"

    def presupuesto(self, **claves):
        self.dir_imp.mkdir(parents=True, exist_ok=True)
        (self.dir_imp / "budget.json").write_text(json.dumps(claves), encoding="utf-8")

    def propuesta(self, i, base_surface=ACTIVO):
        return {"base_surface": base_surface, "content": f"# Skill\n{MARCA_CAND}\nvariante {i}\n",
                "hypothesis": f"hipotesis {i}", "provenance": dict(PROVENANCE)}

    def ciclo(self, propuestas, adapter=None, policy=None):
        return cy.ejecutar_ciclo(self.raiz, propuestas, self.suite, adapter or FakeAdapter(SOLO_1, TODOS),
                                 self.target, policy or ProbePolicy())


class TestCiclo(BaseCiclo):
    def test_dos_propuestas_completas(self):
        r = self.ciclo([self.propuesta(1), self.propuesta(2)])
        self.assertIsNone(r["detenido_por"])
        self.assertEqual(r["rechazos"], [])
        self.assertEqual(len(r["resultados"]), 2)
        for x in r["resultados"]:
            self.assertEqual(x["verdict"], "candidate_better")
            self.assertEqual(x["candidate_status"], "promotable")
            self.assertEqual(x["probe_id"], cy.probe_id_de(x["candidate_id"]))
        self.assertFalse((self.dir_imp / ".cycle.lock").exists())

    def test_max_candidates_detiene(self):
        self.presupuesto(max_probe_cycles=5)
        r = self.ciclo([self.propuesta(i) for i in range(1, 5)])
        self.assertEqual(r["detenido_por"], "candidates")
        self.assertEqual(len(r["resultados"]), 3)
        self.assertTrue(all(x["candidate_status"] == "promotable" for x in r["resultados"]))

    def test_max_probe_cycles_agotado(self):
        self.presupuesto(max_probe_cycles=1, max_candidates=5)
        r = self.ciclo([self.propuesta(1), self.propuesta(2), self.propuesta(3)])
        self.assertEqual(r["detenido_por"], "probe_cycles")
        self.assertEqual(len(r["resultados"]), 2)
        self.assertEqual(r["resultados"][0]["candidate_status"], "promotable")
        self.assertIsNone(r["resultados"][1]["verdict"])
        self.assertEqual(r["resultados"][1]["candidate_status"], "proposed")

    def test_superficie_protegida_se_rechaza_y_continua(self):
        r = self.ciclo([self.propuesta(1, "tools/x.py"), self.propuesta(2)])
        self.assertEqual(len(r["rechazos"]), 1)
        self.assertEqual(r["rechazos"][0]["codigo"], "SUPERFICIE_PROTEGIDA")
        self.assertEqual(r["rechazos"][0]["indice"], 0)
        self.assertEqual(len(r["resultados"]), 1)
        self.assertIsNone(r["detenido_por"])

    def test_engine_rechazado(self):
        r = self.ciclo([self.propuesta(1, "tools/harmessi_improve/probe.py")])
        self.assertEqual(r["resultados"], [])
        self.assertEqual(r["rechazos"][0]["codigo"], "SUPERFICIE_PROTEGIDA")

    def test_propuesta_malformada(self):
        r = self.ciclo([{"content": "x"}, self.propuesta(1)])
        self.assertEqual(r["rechazos"][0]["codigo"], "PROPUESTA_INVALIDA")
        self.assertEqual(len(r["resultados"]), 1)

    def test_ciclo_anidado(self):
        self.dir_imp.mkdir(parents=True, exist_ok=True)
        (self.dir_imp / ".cycle.lock").write_text("pid=1\n", encoding="utf-8")
        with self.assertRaises(CicloAnidado):
            self.ciclo([self.propuesta(1)])
        self.assertTrue((self.dir_imp / ".cycle.lock").exists())  # el ajeno no se borra
        self.assertFalse((self.dir_imp / "candidates").exists())

    def test_lock_liberado_tras_excepcion(self):
        with mock.patch.object(cy._probe, "ejecutar_probe", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                self.ciclo([self.propuesta(1)])
        self.assertFalse((self.dir_imp / ".cycle.lock").exists())
        self.assertEqual(len(self.ciclo([self.propuesta(1)])["resultados"]), 1)

    def test_techo_duro_antes_de_empezar(self):
        self.presupuesto(max_candidates=11)
        with self.assertRaises(PresupuestoInvalido):
            self.ciclo([self.propuesta(1)])
        self.assertFalse((self.dir_imp / ".cycle.lock").exists())
        self.assertFalse((self.dir_imp / "candidates").exists())

    def test_mas_propuestas_que_el_techo(self):
        with self.assertRaises(PresupuestoInvalido):
            self.ciclo([self.propuesta(i) for i in range(11)])

    def test_no_promueve_ni_escribe_fuera_de_harmessi(self):
        antes = {k: v for k, v in snapshot(self.raiz).items() if not k.startswith(".harmessi/")}
        r = self.ciclo([self.propuesta(1), self.propuesta(2)])
        despues = snapshot(self.raiz)
        self.assertEqual({k: v for k, v in despues.items() if not k.startswith(".harmessi/")}, antes)
        self.assertEqual(r["resultados"][0]["candidate_status"], "promotable")  # promotable != promovida
        self.assertFalse((self.dir_imp / "proposals").exists())
        self.assertFalse((self.dir_imp / "lessons").exists())
        self.assertIn(MARCA_BASE, (self.raiz / ACTIVO).read_text("utf-8"))


class TestLockYEtapas(BaseCiclo):
    def lock(self):
        return self.dir_imp / ".cycle.lock"

    def test_lock_stale_se_reemplaza(self):
        self.dir_imp.mkdir(parents=True, exist_ok=True)
        self.lock().write_text("viejo\n", encoding="utf-8")
        viejo = time.time() - 100000
        os.utime(self.lock(), (viejo, viejo))
        r = self.ciclo([self.propuesta(1)])
        self.assertEqual(len(r["resultados"]), 1)
        self.assertFalse(self.lock().exists())
        self.assertEqual([p.name for p in self.dir_imp.glob(".cycle.lock*")], [])

    def test_no_borra_lock_ajeno(self):
        original = cy._probe.ejecutar_probe

        def robando(*a, **k):
            self.lock().write_text("otro-ciclo\n", encoding="utf-8")
            return original(*a, **k)

        with mock.patch.object(cy._probe, "ejecutar_probe", robando):
            self.ciclo([self.propuesta(1)])
        self.assertEqual(self.lock().read_text("utf-8"), "otro-ciclo\n")

    def test_anidado_desde_dentro(self):
        original = cy._probe.ejecutar_probe
        errores = []

        def anidando(*a, **k):
            try:
                self.ciclo([self.propuesta(9)])
            except CicloAnidado as exc:
                errores.append(exc)
            return original(*a, **k)

        with mock.patch.object(cy._probe, "ejecutar_probe", anidando):
            r = self.ciclo([self.propuesta(1)])
        self.assertEqual(len(errores), 1)
        self.assertEqual(len(r["resultados"]), 1)
        self.assertFalse(self.lock().exists())

    def test_presupuesto_agotado_en_decision(self):
        with mock.patch.object(cy._decision, "aplicar_decision",
                               side_effect=PresupuestoAgotado("max_wall_clock_s", 1)):
            r = self.ciclo([self.propuesta(1), self.propuesta(2)])
        self.assertEqual(r["detenido_por"], "wall_clock")
        self.assertEqual(len(r["resultados"]), 1)
        self.assertIsNone(r["resultados"][0]["verdict"])
        self.assertFalse(self.lock().exists())

    def test_nombres_de_recurso(self):
        self.presupuesto(max_candidates=10)
        casos = (("max_runs_per_candidate", "runs"), ("max_retries", "retries"),
                 ("lock", "lock"), ("max_candidates", "candidates"))
        for i, (clave, esperado) in enumerate(casos):
            with self.subTest(clave=clave):
                with mock.patch.object(cy._probe, "ejecutar_probe", side_effect=PresupuestoAgotado(clave, 1)):
                    r = self.ciclo([self.propuesta(100 + i)])
                self.assertEqual(r["detenido_por"], esperado)

    def test_evidencia_invalida_en_decision_es_rechazo_y_sigue(self):
        reales = cy._decision.aplicar_decision
        llamadas = []

        def f(*a, **k):
            llamadas.append(1)
            if len(llamadas) == 1:
                raise EvidenciaInvalida("alterada")
            return reales(*a, **k)

        with mock.patch.object(cy._decision, "aplicar_decision", f):
            r = self.ciclo([self.propuesta(1), self.propuesta(2)])
        self.assertEqual([x["etapa"] for x in r["rechazos"]], ["decision"])
        self.assertEqual(r["rechazos"][0]["codigo"], "EVIDENCIA_INVALIDA")
        self.assertEqual(len(r["resultados"]), 1)
        self.assertIsNone(r["detenido_por"])

    def test_corrupcion_es_rechazo(self):
        with mock.patch.object(cy._probe, "ejecutar_probe", side_effect=ProbeCorrupto("x")):
            r = self.ciclo([self.propuesta(1)])
        self.assertEqual(r["rechazos"][0]["etapa"], "probe")
        self.assertEqual(r["resultados"], [])

    def test_repeats_incompatible_con_runs_no_arranca(self):
        self.presupuesto(max_runs_per_candidate=4)
        r = self.ciclo([self.propuesta(1)], policy=ProbePolicy(repeats=3))
        self.assertEqual(r["detenido_por"], "rechazo")
        self.assertEqual(r["rechazos"][0]["codigo"], "CICLO_INVALIDO")
        self.assertFalse((self.dir_imp / "candidates").exists())
        self.assertFalse(self.lock().exists())

    def test_suite_ilegible_no_arranca(self):
        r = cy.ejecutar_ciclo(self.raiz, [self.propuesta(1)], self.raiz / "no-existe.suite.json",
                              FakeAdapter(SOLO_1, TODOS), self.target, ProbePolicy())
        self.assertEqual(r["detenido_por"], "rechazo")
        self.assertFalse((self.dir_imp / "candidates").exists())


if __name__ == "__main__":
    unittest.main()

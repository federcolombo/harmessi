"""Tests de decisión (v0.14 Change 3, R1-R11). Probes reales con FakeAdapter en tempdirs."""
from __future__ import annotations

import hashlib
import inspect
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from tools.harmessi_bench.runmanifest import calcular_identity_hash
from tools.harmessi_improve.probe import ProbeRechazado
from tools.harmessi_improve.tests._fakes import crear_suite
from tools.harmessi_bench.redact import redactar_texto
from tools.harmessi_improve import candidate as cand
from tools.harmessi_improve import decision as dec
from tools.harmessi_improve.decision import EvidenciaInvalida, PromocionNoRespaldada
from tools.harmessi_improve.policy import ProbePolicy
from tools.harmessi_improve.tests._fakes import MARCA_CAND, FakeAdapter
from tools.harmessi_improve.tests._helpers import ACTIVO, snapshot
from tools.harmessi_improve.tests.test_probe import SOLO_1, TODOS, Base

AHORA = datetime(2026, 10, 23, 13, 0, tzinfo=timezone.utc)


class AlternaAdapter(FakeAdapter):
    """El escenario 'Caso 1' del lado `lado` pasa en repeticiones impares y falla en las pares."""

    def __init__(self, lado="cand"):
        super().__init__(TODOS, TODOS)
        self.cuentas = {}
        self.lado = lado

    def invoke(self, request):
        rol = "cand" if MARCA_CAND in request.prompt else "base"
        caso1 = "Caso 1" in request.prompt
        k = self.cuentas.get((rol, caso1), 0)
        self.cuentas[(rol, caso1)] = k + 1
        falla = caso1 and rol == self.lado and k % 2 == 1
        self.salida_cand = "tok-2 tok-3" if falla else TODOS
        self.salida_base = "tok-2 tok-3" if falla else TODOS
        return super().invoke(request)


class BaseDecision(Base):
    def ruta_decision(self, probe_id="p1"):
        return self.raiz / ".harmessi" / "improvement" / "decisions" / probe_id / "decision.json"

    def ruta_json_cand(self, cid=None):
        return self.raiz / ".harmessi" / "improvement" / "candidates" / (cid or self.c.candidate_id) / "candidate.json"

    def editar_decision(self, rehash=False, probe_id="p1", **cambios):
        ruta = self.ruta_decision(probe_id)
        datos = json.loads(ruta.read_text("utf-8"))
        datos.update(cambios)
        if rehash:
            datos["decision_hash"] = dec._hash_decision(datos)
        ruta.write_text(json.dumps(datos), encoding="utf-8")

    def forzar_promotable(self, cid, probe_id, decision_hash):
        """Edita a mano candidate.json a promotable con evidencia dada (simula manipulación)."""
        ruta = self.ruta_json_cand(cid)
        datos = json.loads(ruta.read_text("utf-8"))
        ev = {"probe_id": probe_id, "decision_hash": decision_hash}
        datos["status"] = "promotable"
        datos["status_history"] += [
            {"status": "evaluated", "utc": "2026-10-23T13:00:00Z", "evidence": ev},
            {"status": "promotable", "utc": "2026-10-23T13:00:01Z", "evidence": ev},
        ]
        ruta.write_text(json.dumps(datos), encoding="utf-8")

    def promover(self):
        self.probe(FakeAdapter(SOLO_1, TODOS))
        return dec.aplicar_decision(self.raiz, "p1", ahora=AHORA)


class TestPromocion(BaseDecision):
    def test_candidate_mejor_promotable(self):
        self.probe(FakeAdapter(SOLO_1, TODOS))
        d = dec.decidir(self.raiz, "p1")
        self.assertEqual(d["verdict"], "candidate_better")
        self.assertEqual(d["candidate_status"], "promotable")
        self.assertEqual(d["evidence_kind"], "deterministic_scorers")
        c = dec.aplicar_decision(self.raiz, "p1", ahora=AHORA)
        self.assertEqual(c.status, "promotable")
        self.assertEqual([h["status"] for h in c.status_history], ["proposed", "evaluated", "promotable"])
        self.assertEqual(c.status_history[-1]["evidence"], {"probe_id": "p1", "decision_hash": d["decision_hash"]})
        v = dec.verificar_promotable(self.raiz, self.c.candidate_id)
        self.assertEqual(v, d)
        self.assertEqual(dec.cargar_decision(self.raiz, "p1"), d)

    def test_candidate_peor_rechazada(self):
        self.probe(FakeAdapter(TODOS, SOLO_1))
        d = dec.decidir(self.raiz, "p1")
        self.assertEqual((d["verdict"], d["candidate_status"]), ("baseline_better", "rejected"))
        self.assertEqual(dec.aplicar_decision(self.raiz, "p1").status, "rejected")
        with self.assertRaises(PromocionNoRespaldada):
            dec.verificar_promotable(self.raiz, self.c.candidate_id)

    def test_equivalente_rechazada(self):
        self.probe(FakeAdapter(TODOS, TODOS))
        d = dec.decidir(self.raiz, "p1")
        self.assertEqual((d["verdict"], d["candidate_status"]), ("equivalent", "rejected"))
        self.assertEqual(dec.aplicar_decision(self.raiz, "p1").status, "rejected")

    def test_equivalente_sin_casos_que_pasen_es_inconclusive(self):
        self.probe(FakeAdapter("", ""))
        d = dec.decidir(self.raiz, "p1")
        self.assertEqual((d["verdict"], d["candidate_status"]), ("inconclusive", "inconclusive"))
        self.assertEqual(dec.aplicar_decision(self.raiz, "p1").status, "inconclusive")

    def test_tie_policy_inconclusive(self):
        self.probe(FakeAdapter(TODOS, TODOS), ProbePolicy(tie_policy="inconclusive"))
        self.assertEqual(dec.decidir(self.raiz, "p1")["verdict"], "inconclusive")

    def test_tie_policy_secondary_sin_diferencia_suficiente_queda_equivalent(self):
        self.probe(FakeAdapter(TODOS, TODOS),
                   ProbePolicy(tie_policy="secondary", secondary=("mean_score",), min_delta=1000))
        self.assertEqual(dec.decidir(self.raiz, "p1")["verdict"], "equivalent")

    def test_desempate_secundario_unitario(self):
        def res(score):
            return [{"scenario_id": "a", "ok": True, "score": {"passed": True, "score": score}, "duration_s": 1}]
        pol = ProbePolicy(tie_policy="secondary", secondary=("mean_score",), min_delta=0.1)
        self.assertEqual(dec._desempatar(pol, res(0.5), res(0.9))[0], "candidate_better")
        self.assertEqual(dec._desempatar(pol, res(0.9), res(0.5))[0], "baseline_better")
        self.assertIsNone(dec._desempatar(pol, res(0.5), res(0.55))[0])
        self.assertIsNone(dec._desempatar(pol, res(0.5), res(0.5))[0])

    def test_secondary_mean_score_promovible_integrado(self):
        """Los scorers del fake son 0/1: se inyecta una diferencia de score en la agregación del
        candidate para ejercitar el camino completo equivalent -> secondary -> promotable."""
        original = dec._agregar_rol

        def con_bonus(corridas):
            agg = original(corridas)
            if corridas[0]["run_manifest"]["run_id"].endswith("-cand-r1"):
                for a in agg.values():
                    a["score"] = 1.0
                    a["p"] = a["p"]
            else:
                for a in agg.values():
                    a["score"] = 0.5
            return agg

        pol = ProbePolicy(tie_policy="secondary", secondary=("mean_score",), min_delta=0.1)
        self.probe(FakeAdapter(TODOS, TODOS), pol)
        with mock.patch.object(dec, "_agregar_rol", con_bonus):
            d = dec.decidir(self.raiz, "p1")
            self.assertEqual((d["verdict"], d["candidate_status"]), ("candidate_better", "promotable"))
            self.assertIn("mean_score", d["reason"])
            self.assertEqual(dec.aplicar_decision(self.raiz, "p1").status, "promotable")
            dec.verificar_promotable(self.raiz, self.c.candidate_id)


class TestMapeoOutcome(BaseDecision):
    def test_entorno_inconclusive_nunca_baseline_better(self):
        for lado in ("cand", "base"):
            with self.subTest(lado=lado):
                pid = f"p-{lado}"
                self.probe(FakeAdapter(TODOS, TODOS, fallos={lado: [999, "quota"]}), probe_id=pid,
                           candidate_id=self.c.candidate_id)
                d = dec.decidir(self.raiz, pid)
                self.assertEqual(d["verdict"], "inconclusive")
                self.assertNotEqual(d["verdict"], "baseline_better")
                self.assertEqual(d["candidate_status"], "inconclusive")

    def test_candidate_failure_rechazada(self):
        p = self.probe(FakeAdapter(TODOS, TODOS, fallos={"cand": [999, None]}))
        self.assertEqual(p["outcome"], "candidate_failure")
        d = dec.decidir(self.raiz, "p1")
        self.assertEqual(d["candidate_status"], "rejected")
        self.assertEqual(dec.aplicar_decision(self.raiz, "p1").status, "rejected")

    def test_probe_no_completed_no_decidible(self):
        self.probe(FakeAdapter(TODOS, TODOS))
        self.editar_probe(status="running", outcome=None)
        with self.assertRaises(EvidenciaInvalida):
            dec.decidir(self.raiz, "p1")

    def test_probe_inexistente(self):
        with self.assertRaises(EvidenciaInvalida):
            dec.decidir(self.raiz, "no-existe")


class TestEstocastico(BaseDecision):
    def test_inestables_excluidos_y_bajo_ratio_inconclusive(self):
        # MED-7: inestable solo del lado candidate con baseline estable-pass => regresión (no se excluye)
        pol = ProbePolicy(repeats=2, min_stable_ratio=0.6, min_scenarios=1)
        self.probe(AlternaAdapter("cand"), pol)
        d = dec.decidir(self.raiz, "p1")
        self.assertEqual([i["scenario_id"] for i in d["inestables"]], ["caso-1"])
        self.assertEqual(d["inestables"][0]["efecto"], "regresion_candidate")
        self.assertEqual((d["verdict"], d["candidate_status"]), ("baseline_better", "rejected"))
        self.assertEqual((d["n_escenarios"], d["n_estables"]), (3, 3))
        self.assertEqual(len(d["evidencia"]), 4)

    def test_inestable_del_baseline_se_excluye(self):
        self.probe(AlternaAdapter("base"), ProbePolicy(repeats=2, min_stable_ratio=0.6, min_scenarios=1))
        d = dec.decidir(self.raiz, "p1")
        self.assertEqual(d["inestables"][0]["efecto"], "excluido")
        self.assertEqual((d["verdict"], d["n_estables"]), ("equivalent", 2))  # caso-2 y caso-3 pasan en ambos

    def test_repeats_3(self):
        self.probe(FakeAdapter(SOLO_1, TODOS), ProbePolicy(repeats=3))
        d = dec.decidir(self.raiz, "p1")
        self.assertEqual((d["verdict"], len(d["evidencia"])), ("candidate_better", 6))
        self.assertEqual(dec.aplicar_decision(self.raiz, "p1").status, "promotable")

    def test_bajo_min_stable_ratio(self):
        self.probe(AlternaAdapter("cand"), ProbePolicy(repeats=2, min_stable_ratio=1.0))
        d = dec.decidir(self.raiz, "p1")
        self.assertEqual(d["verdict"], "inconclusive")
        self.assertIn("inestable", d["reason"])
        self.assertEqual([i["scenario_id"] for i in d["inestables"]], ["caso-1"])


class TestEvidenciaInvalida(BaseDecision):
    def setUp(self):
        super().setUp()
        self.probe(FakeAdapter(SOLO_1, TODOS))

    def test_result_json_alterado(self):
        ruta = self.evals / "p1-cand-r1" / "result.json"
        ruta.write_bytes(ruta.read_bytes() + b"\n ")
        with self.assertRaises(EvidenciaInvalida):
            dec.decidir(self.raiz, "p1")

    def test_result_json_ausente(self):
        (self.evals / "p1-base-r1" / "result.json").unlink()
        with self.assertRaises(EvidenciaInvalida):
            dec.decidir(self.raiz, "p1")

    def test_policy_alterada_en_probe(self):
        ruta = self.raiz / ".harmessi" / "improvement" / "probes" / "p1" / "probe.json"
        datos = json.loads(ruta.read_text("utf-8"))
        datos["policy"]["tie_policy"] = "inconclusive"
        ruta.write_text(json.dumps(datos), encoding="utf-8")
        with self.assertRaises(EvidenciaInvalida):
            dec.decidir(self.raiz, "p1")

    def test_identity_hash_alterado_en_probe(self):
        ruta = self.raiz / ".harmessi" / "improvement" / "probes" / "p1" / "probe.json"
        datos = json.loads(ruta.read_text("utf-8"))
        datos["runs"][0]["identity_hash"] = "0" * 64
        ruta.write_text(json.dumps(datos), encoding="utf-8")
        with self.assertRaises(EvidenciaInvalida):
            dec.decidir(self.raiz, "p1")

    def test_content_de_candidate_cambia(self):
        ruta = self.raiz / ".harmessi" / "improvement" / "candidates" / self.c.candidate_id / "content.md"
        ruta.write_text("# Otro contenido\n", encoding="utf-8")
        with self.assertRaises(EvidenciaInvalida):
            dec.decidir(self.raiz, "p1")


class TestHashYManipulacion(BaseDecision):
    def setUp(self):
        super().setUp()
        self.probe(FakeAdapter(TODOS, SOLO_1))  # baseline_better

    def test_hash_estable(self):
        a, b = dec.decidir(self.raiz, "p1"), dec.decidir(self.raiz, "p1")
        self.assertEqual(a, b)
        self.assertEqual(a["decision_hash"], dec._hash_decision(a))

    def test_registrar_y_detectar_manipulacion(self):
        d = dec.decidir(self.raiz, "p1", registrar=True)
        self.assertEqual(dec.cargar_decision(self.raiz, "p1"), d)
        dec.decidir(self.raiz, "p1", registrar=True)  # idempotente
        self.editar_decision(verdict="candidate_better", candidate_status="promotable")
        with self.assertRaises(EvidenciaInvalida):
            dec.cargar_decision(self.raiz, "p1")

    def test_aplicar_rechaza_decision_manipulada(self):
        dec.decidir(self.raiz, "p1", registrar=True)
        self.editar_decision(verdict="candidate_better", candidate_status="promotable")
        with self.assertRaises(EvidenciaInvalida):
            dec.aplicar_decision(self.raiz, "p1")
        self.assertEqual(cand.cargar_candidate(self.raiz, self.c.candidate_id).status, "proposed")

    def test_aplicar_rechaza_decision_consistente_pero_distinta_a_la_recomputada(self):
        dec.decidir(self.raiz, "p1", registrar=True)
        self.editar_decision(rehash=True, verdict="candidate_better", candidate_status="promotable")
        self.assertEqual(dec.cargar_decision(self.raiz, "p1")["verdict"], "candidate_better")
        with self.assertRaises(EvidenciaInvalida):
            dec.aplicar_decision(self.raiz, "p1")
        self.assertEqual(cand.cargar_candidate(self.raiz, self.c.candidate_id).status, "proposed")
        with self.assertRaises(PromocionNoRespaldada):
            dec.verificar_promotable(self.raiz, self.c.candidate_id)


class TestVerificarPromotable(BaseDecision):
    def test_json_editado_a_mano_con_evidencia_inventada(self):
        self.forzar_promotable(self.c.candidate_id, "inventado", "abc123")
        with self.assertRaises(PromocionNoRespaldada):
            dec.verificar_promotable(self.raiz, self.c.candidate_id)

    def test_hipotesis_mejor_sin_probe(self):
        c = self.nueva_candidate("# Skill\nesta variante es mejor\n")
        self.assertEqual(c.status, "proposed")
        with self.assertRaises(PromocionNoRespaldada):
            dec.verificar_promotable(self.raiz, c.candidate_id)

    def test_decision_de_otra_candidate(self):
        otra = self.nueva_candidate("# Skill\nOtra variante MARCA-CAND\n")
        self.probe(FakeAdapter(SOLO_1, TODOS), probe_id="p2", candidate_id=otra.candidate_id)
        dec.aplicar_decision(self.raiz, "p2")
        dec.verificar_promotable(self.raiz, otra.candidate_id)
        d = dec.cargar_decision(self.raiz, "p2")
        self.forzar_promotable(self.c.candidate_id, "p2", d["decision_hash"])
        with self.assertRaises(PromocionNoRespaldada):
            dec.verificar_promotable(self.raiz, self.c.candidate_id)

    def test_base_no_vigente(self):
        self.promover()
        dec.verificar_promotable(self.raiz, self.c.candidate_id)
        (self.raiz / ACTIVO).write_bytes(b"# Skill\ncambiado\n")
        with self.assertRaises(PromocionNoRespaldada):
            dec.verificar_promotable(self.raiz, self.c.candidate_id)

    def test_veredicto_distinto_de_candidate_better(self):
        self.probe(FakeAdapter(TODOS, SOLO_1))
        d = dec.decidir(self.raiz, "p1", registrar=True)
        self.forzar_promotable(self.c.candidate_id, "p1", d["decision_hash"])
        with self.assertRaises(PromocionNoRespaldada):
            dec.verificar_promotable(self.raiz, self.c.candidate_id)

    def test_evidencia_alterada_despues_de_promover(self):
        self.promover()
        ruta = self.evals / "p1-cand-r1" / "result.json"
        ruta.write_bytes(ruta.read_bytes() + b"\n ")
        with self.assertRaises(PromocionNoRespaldada):
            dec.verificar_promotable(self.raiz, self.c.candidate_id)


class TestEndurecimiento(BaseDecision):
    def forjar(self, run_id, mutar, probe_id="p1"):
        """Altera el manifest de un result.json y re-sincroniza sha256/identity_hash en probe.json,
        simulando un atacante que mantiene la consistencia superficial."""
        ruta = self.evals / run_id / "result.json"
        datos = json.loads(ruta.read_text("utf-8"))
        mutar(datos["run_manifest"])
        datos["run_manifest"]["identity_hash"] = calcular_identity_hash(datos["run_manifest"])
        ruta.write_text(json.dumps(datos), encoding="utf-8")
        rp = self.raiz / ".harmessi" / "improvement" / "probes" / probe_id / "probe.json"
        probe = json.loads(rp.read_text("utf-8"))
        for r in probe["runs"]:
            if r["run_id"] == run_id:
                r["sha256"] = hashlib.sha256(ruta.read_bytes()).hexdigest()
                r["identity_hash"] = datos["run_manifest"]["identity_hash"]
        rp.write_text(json.dumps(probe), encoding="utf-8")

    def test_outcome_falsificado_a_success(self):
        self.probe(FakeAdapter(TODOS, TODOS, fallos={"cand": [999, "quota"]}))
        self.editar_probe(outcome="success")
        with self.assertRaises(EvidenciaInvalida):
            dec.decidir(self.raiz, "p1")

    def test_outcome_falsificado_candidate_failure_con_fallo_de_entorno(self):
        self.probe(FakeAdapter(TODOS, TODOS, fallos={"cand": [999, "quota"]}))
        self.editar_probe(outcome="candidate_failure")
        with self.assertRaises(EvidenciaInvalida):
            dec.decidir(self.raiz, "p1")

    def test_criterios_cambiados(self):
        self.probe(FakeAdapter(TODOS, TODOS))
        self.editar_probe("p1", outcome="inconclusive", motivos=["wall_clock"])
        with self.assertRaises(ProbeRechazado) as ctx:
            self.probe(FakeAdapter(TODOS, TODOS), ProbePolicy(tie_policy="inconclusive"), probe_id="p2")
        self.assertEqual(ctx.exception.codigo, "CRITERIOS_CAMBIADOS")

    def test_probe_pendiente_de_decision(self):
        self.probe(FakeAdapter("", ""))
        ad = FakeAdapter(TODOS, TODOS)
        with self.assertRaises(ProbeRechazado) as ctx:
            self.probe(ad, probe_id="p2")
        self.assertEqual(ctx.exception.codigo, "PROBE_PENDIENTE_DE_DECISION")
        self.assertEqual(ad.invocaciones, 0)
        dec.aplicar_decision(self.raiz, "p1")  # inconclusive: la candidate sigue probable
        self.probe(FakeAdapter(TODOS, TODOS), probe_id="p2")

    def test_aplicar_sobre_probe_mas_viejo(self):
        self.probe(FakeAdapter("", ""))
        dec.aplicar_decision(self.raiz, "p1")
        self.probe(FakeAdapter(SOLO_1, TODOS), probe_id="p2")
        with self.assertRaises(EvidenciaInvalida):
            dec.aplicar_decision(self.raiz, "p1")
        self.assertEqual(dec.aplicar_decision(self.raiz, "p2").status, "promotable")

    def test_muestra_insuficiente(self):
        suite2 = crear_suite(Path(self._tmp_suite.name) / "dos", n=2)
        self.probe(FakeAdapter(SOLO_1, TODOS), suite=suite2)
        d = dec.decidir(self.raiz, "p1")
        self.assertEqual((d["verdict"], d["n_estables"]), ("inconclusive", 2))
        self.assertIn("muestra_insuficiente", d["reason"])

    def test_manifest_forjado_misma_identidad(self):
        self.probe(FakeAdapter(SOLO_1, TODOS))
        base = json.loads((self.evals / "p1-base-r1" / "result.json").read_text("utf-8"))["run_manifest"]
        self.forjar("p1-cand-r1", lambda m: m.update(skills=base["skills"], surfaces_hash=base["surfaces_hash"]))
        with self.assertRaises(EvidenciaInvalida):
            dec.decidir(self.raiz, "p1")

    def test_manifest_forjado_diferencia_material_extra(self):
        self.probe(FakeAdapter(SOLO_1, TODOS))
        self.forjar("p1-cand-r1", lambda m: m.update(guardrails_hash="f" * 64))
        with self.assertRaises(EvidenciaInvalida):
            dec.decidir(self.raiz, "p1")

    def test_manifest_forjado_seed(self):
        self.probe(FakeAdapter(SOLO_1, TODOS))
        self.forjar("p1-base-r1", lambda m: m.update(seed=7))
        with self.assertRaises(EvidenciaInvalida):
            dec.decidir(self.raiz, "p1")

    def test_evals_root_enlace(self):
        self.probe(FakeAdapter(SOLO_1, TODOS))
        with mock.patch.object(dec, "es_enlace", lambda ruta: True):
            with self.assertRaises(EvidenciaInvalida):
                dec.decidir(self.raiz, "p1")

    def test_firmas_sin_parametros_de_criterio_no_nominal(self):
        """Ninguna firma pública admite **kwargs ni parámetros variádicos que cuelen criterios."""
        for fn in (dec.decidir, dec.aplicar_decision, dec.cargar_decision, dec.verificar_promotable):
            for p in inspect.signature(fn).parameters.values():
                self.assertNotIn(p.kind, (p.VAR_KEYWORD, p.VAR_POSITIONAL), fn.__name__)
        with self.assertRaises(TypeError):
            dec.decidir(self.raiz, "p1", policy=ProbePolicy())  # type: ignore[call-arg]
        with self.assertRaises(TypeError):
            dec.aplicar_decision(self.raiz, "p1", verdict="candidate_better")  # type: ignore[call-arg]


class TestAplicar(BaseDecision):
    def test_idempotente(self):
        c1 = self.promover()
        antes = self.ruta_json_cand().read_bytes()
        c2 = dec.aplicar_decision(self.raiz, "p1", ahora=AHORA)
        self.assertEqual(c1.a_dict(), c2.a_dict())
        self.assertEqual(self.ruta_json_cand().read_bytes(), antes)
        self.assertEqual(len(c2.status_history), 3)

    def test_completa_transicion_a_medias(self):
        self.probe(FakeAdapter(SOLO_1, TODOS))
        d = dec.decidir(self.raiz, "p1")
        cand.transicionar(self.raiz, self.c.candidate_id, "evaluated",
                          {"probe_id": "p1", "decision_hash": d["decision_hash"]})
        self.assertEqual(dec.aplicar_decision(self.raiz, "p1").status, "promotable")

    def test_inconclusive_se_puede_reevaluar(self):
        self.probe(FakeAdapter("", ""))
        self.assertEqual(dec.aplicar_decision(self.raiz, "p1").status, "inconclusive")
        self.probe(FakeAdapter(SOLO_1, TODOS), probe_id="p2")
        self.assertEqual(dec.aplicar_decision(self.raiz, "p2").status, "promotable")
        dec.verificar_promotable(self.raiz, self.c.candidate_id)

    def test_no_escribe_fuera_de_lo_permitido(self):
        self.probe(FakeAdapter(SOLO_1, TODOS))
        antes = snapshot(self.raiz)
        dec.aplicar_decision(self.raiz, "p1")
        despues = snapshot(self.raiz)
        for ruta, datos in antes.items():
            if ruta.endswith("candidate.json"):
                continue
            self.assertEqual(despues.get(ruta), datos, ruta)
        for ruta in set(despues) - set(antes):
            self.assertTrue(ruta.startswith(".harmessi/improvement/decisions/"), ruta)
        self.assertEqual(despues[ACTIVO], antes[ACTIVO])


class TestApiYPrivacidad(BaseDecision):
    def test_ninguna_api_acepta_criterios(self):
        permitidos = {"repo_root", "probe_id", "evals_root", "registrar", "ahora", "candidate_id"}
        prohibidos = ("policy", "politica", "verdict", "veredicto", "criterio", "criteria", "status", "estado")
        for fn in (dec.decidir, dec.aplicar_decision, dec.cargar_decision, dec.verificar_promotable):
            with self.subTest(fn=fn.__name__):
                nombres = set(inspect.signature(fn).parameters)
                self.assertLessEqual(nombres, permitidos)
                for n in nombres:
                    self.assertFalse(any(p in n for p in prohibidos), n)

    def test_privacidad_decision_json(self):
        self.probe(FakeAdapter(SOLO_1, TODOS))
        dec.decidir(self.raiz, "p1", registrar=True)
        texto = self.ruta_decision().read_text("utf-8")
        d = json.loads(texto)
        self.assertEqual(redactar_texto(d["reason"]), d["reason"])
        self.assertNotIn(str(self.raiz), texto)
        self.assertNotIn(self.raiz.name, texto)
        self.assertNotIn(MARCA_CAND, texto)
        self.assertEqual(set(d), set(dec._CLAVES_DECISION))
        self.assertEqual(d["dimensiones_soportadas"], ["passed", "mean_score"])
        for k in ("n_escenarios", "n_estables", "suite", "target", "seed"):
            self.assertIn(k, d)


if __name__ == "__main__":
    unittest.main()

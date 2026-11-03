"""Tests de ejecución de probe (v0.14 Change 2, R3-R10). Todo sintético en tempdirs."""
from __future__ import annotations

import dataclasses
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tools.harmessi_bench import compare as cmp
from tools.harmessi_bench import storage
from tools.harmessi_bench.core import EvalTarget
from tools.harmessi_bench.redact import redactar_texto
from tools.harmessi_bench.runmanifest import diferencias_materiales
from tools.harmessi_improve import budget as bud
from tools.harmessi_improve import candidate as cand
from tools.harmessi_improve import probe as pr
from tools.harmessi_improve.policy import ProbePolicy, hash_policy
from tools.harmessi_improve.probe import GuidanceAdapter, ProbeCorrupto, ProbeIncompatible, ProbeRechazado
from tools.harmessi_improve.tests._fakes import MARCA_BASE, MARCA_CAND, FakeAdapter, crear_suite
from tools.harmessi_improve.tests._helpers import ACTIVO, PROVENANCE, crear_repo, snapshot

TODOS = "tok-1 tok-2 tok-3"
SOLO_1 = "tok-1"
BASE_T = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._tmp_suite = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.addCleanup(self._tmp_suite.cleanup)
        self.raiz = crear_repo(Path(self._tmp.name))
        (self.raiz / ACTIVO).write_bytes(f"# Skill\n{MARCA_BASE}\n".encode("utf-8"))
        self.suite = crear_suite(Path(self._tmp_suite.name))
        self.target = EvalTarget("fake", model="m1", effort="low")
        self.evals = self.raiz / ".harmessi" / "evals"
        self.c = self.nueva_candidate()

    def nueva_candidate(self, texto=None, **kw):
        return cand.crear_candidate(
            self.raiz, ACTIVO, texto or f"# Skill\n{MARCA_CAND}\n", "hipótesis", dict(PROVENANCE), **kw)

    def probe(self, adapter, policy=None, probe_id="p1", candidate_id=None, **kw):
        return pr.ejecutar_probe(
            self.raiz, candidate_id or self.c.candidate_id, kw.pop("suite", self.suite), adapter,
            kw.pop("target", self.target), policy or ProbePolicy(), probe_id, **kw)

    def run_(self, run_id):
        return storage.load_run(run_id, root=self.evals)

    def veredicto(self, probe_id="p1", k=1):
        r = cmp.compare_runs(self.run_(f"{probe_id}-base-r{k}"), self.run_(f"{probe_id}-cand-r{k}"))
        return r.verdict

    def estado_budget(self):
        return bud.estado(self.raiz)

    def escribir_budget(self, **valores):
        ruta = self.raiz / ".harmessi" / "improvement" / "budget.json"
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(json.dumps(valores), encoding="utf-8")

    def interrumpido(self, pol=None, probe_id="p1", corte=3, **kw):
        """Probe que termina `inconclusive` por wall_clock tras `corte` invocaciones (reanudable)."""
        ad = FakeAdapter(TODOS, TODOS)
        inicio = datetime.now(timezone.utc)
        reloj = lambda: inicio + timedelta(hours=2) if ad.invocaciones >= corte else inicio  # noqa: E731
        p = self.probe(ad, pol, probe_id=probe_id, ahora=reloj, **kw)
        self.assertEqual(p["motivos"], ["wall_clock"])
        return p

    def editar_probe(self, probe_id="p1", **cambios):
        ruta = self.raiz / ".harmessi" / "improvement" / "probes" / probe_id / "probe.json"
        datos = json.loads(ruta.read_text("utf-8"))
        datos.update(cambios)
        ruta.write_text(json.dumps(datos), encoding="utf-8")


class TestComparacion(Base):
    def test_candidate_mejor(self):
        p = self.probe(FakeAdapter(SOLO_1, TODOS))
        self.assertEqual(p["outcome"], "success")
        self.assertEqual(self.veredicto(), "candidate_better")

    def test_candidate_peor(self):
        self.probe(FakeAdapter(TODOS, SOLO_1))
        self.assertEqual(self.veredicto(), "baseline_better")

    def test_equivalente(self):
        self.probe(FakeAdapter(TODOS, TODOS))
        self.assertEqual(self.veredicto(), "equivalent")

    def test_guias_inyectadas(self):
        ad = FakeAdapter(TODOS, TODOS)
        self.probe(ad)
        self.assertEqual(sum(MARCA_CAND in p for p in ad.prompts), 3)
        self.assertEqual(sum(MARCA_BASE in p for p in ad.prompts), 3)
        self.assertTrue(all(p.startswith("[GUIDANCE]\n") and "\n[/GUIDANCE]\n\n" in p for p in ad.prompts))

    def test_mismas_condiciones(self):
        self.probe(FakeAdapter(TODOS, TODOS))
        b, c = self.run_("p1-base-r1"), self.run_("p1-cand-r1")
        self.assertEqual(b["cases_hash"], c["cases_hash"])
        self.assertEqual(b["target"], c["target"])
        self.assertEqual(b["evaluator_version"], c["evaluator_version"])
        self.assertEqual(b["suite"], c["suite"])
        self.assertEqual(diferencias_materiales(b["run_manifest"], c["run_manifest"]),
                         ["skills", "surfaces_hash"])

    def test_activo_intacto_y_arbol(self):
        antes = snapshot(self.raiz)
        self.probe(FakeAdapter(SOLO_1, TODOS))
        despues = snapshot(self.raiz)
        for ruta, datos in antes.items():
            if ruta.endswith("budget_state.json"):
                continue  # el probe consume budget: es el único archivo previo que cambia
            self.assertEqual(despues.get(ruta), datos, ruta)
        nuevos = set(despues) - set(antes)
        self.assertTrue(nuevos)
        for ruta in nuevos:
            self.assertTrue(ruta.startswith((".harmessi/improvement/", ".harmessi/evals/")), ruta)
        self.assertEqual(cand.cargar_candidate(self.raiz, self.c.candidate_id).status, "proposed")


class TestFallos(Base):
    def test_fallo_entorno_no_es_baseline_better(self):
        ad = FakeAdapter(TODOS, TODOS, fallos={"cand": [999, "quota"]})
        p = self.probe(ad)
        self.assertEqual(p["outcome"], "environment_failure")
        self.assertNotEqual(p["outcome"], "baseline_failure")
        cand_run = [r for r in p["runs"] if r["role"] == "candidate"][0]
        self.assertEqual(cand_run["estado"], "fallo_entorno")
        self.assertEqual(cand_run["attempts"], 2)  # 1 reintento (max_retries por defecto)
        self.assertNotEqual(self.veredicto(), "baseline_better")

    def test_fallo_solo_candidate(self):
        p = self.probe(FakeAdapter(TODOS, TODOS, fallos={"cand": [999, None]}))
        self.assertEqual(p["outcome"], "candidate_failure")
        self.assertEqual([r["attempts"] for r in p["runs"]], [1, 2])  # confirmado por 1 reintento
        self.assertEqual(p["runs"][1]["estado"], "fallo_propio")

    def test_fallo_solo_baseline(self):
        p = self.probe(FakeAdapter(TODOS, TODOS, fallos={"base": [999, None]}))
        self.assertEqual(p["outcome"], "baseline_failure")

    def test_fallo_no_confirmado_es_inconclusive(self):
        # Con 1 solo reintento disponible, el 2.º lado que falla no puede confirmarse.
        p = self.probe(FakeAdapter(TODOS, TODOS, fallos={"base": [999, None], "cand": [999, None]}))
        self.assertEqual(p["outcome"], "inconclusive")
        self.assertEqual(p["motivos"], ["fallo_no_confirmado"])
        self.assertEqual(p["runs"][1]["estado"], "fallo_no_confirmado")

    def test_fallo_en_ambos_lados_confirmado_es_entorno(self):
        self.escribir_budget(max_retries=2)
        p = self.probe(FakeAdapter(TODOS, TODOS, fallos={"base": [999, None], "cand": [999, None]}))
        self.assertEqual(p["outcome"], "environment_failure")

    def test_ambiguedad_entorno_mas_propio_es_entorno(self):
        self.escribir_budget(max_retries=2)
        p = self.probe(FakeAdapter(TODOS, TODOS, fallos={"base": [999, None], "cand": [999, "quota"]}))
        self.assertEqual(p["outcome"], "environment_failure")

    def test_reintento_cortado_por_wall_clock(self):
        ad = FakeAdapter(TODOS, TODOS, fallos={"cand": [999, "quota"]})
        inicio = datetime.now(timezone.utc)
        reloj = lambda: inicio + timedelta(hours=2) if ad.invocaciones >= 6 else inicio  # noqa: E731
        p = self.probe(ad, ahora=reloj)
        self.assertEqual(p["outcome"], "inconclusive")
        self.assertEqual(p["motivos"], ["wall_clock"])
        self.assertEqual(p["runs"][-1]["attempts"], 1)

    def test_reintento_exitoso(self):
        p = self.probe(FakeAdapter(TODOS, TODOS, fallos={"cand": [1, "quota"]}))
        self.assertEqual(p["outcome"], "success")
        self.assertEqual([r["attempts"] for r in p["runs"]], [1, 2])
        self.assertEqual(self.estado_budget()["retries_by_candidate"][self.c.candidate_id], 1)

    def test_wall_clock(self):
        ad = FakeAdapter(TODOS, TODOS)
        inicio = datetime.now(timezone.utc)  # relativo al reloj real: la candidate ya fijó started_utc
        reloj = lambda: inicio + timedelta(hours=2) if ad.invocaciones >= 3 else inicio  # noqa: E731
        p = self.probe(ad, ahora=reloj)
        self.assertEqual(p["outcome"], "inconclusive")
        self.assertEqual(p["motivos"], ["wall_clock"])
        self.assertEqual(len(p["runs"]), 1)
        self.assertEqual(ad.invocaciones, 3)


class TestBudget(Base):
    def test_consumo_exacto(self):
        self.probe(FakeAdapter(TODOS, TODOS), ProbePolicy(repeats=2))
        est = self.estado_budget()
        self.assertEqual(est["probe_cycles"], 1)
        self.assertEqual(est["runs_by_candidate"][self.c.candidate_id], 4)

    def test_agotamiento_sin_ejecutar(self):
        (self.raiz / ".harmessi" / "improvement" / "budget.json").write_text(
            json.dumps({"max_runs_per_candidate": 1}), encoding="utf-8")
        ad = FakeAdapter(TODOS, TODOS)
        with self.assertRaises(bud.PresupuestoAgotado):
            self.probe(ad)
        self.assertEqual(ad.invocaciones, 0)
        self.assertEqual(self.estado_budget()["probe_cycles"], 0)
        with self.assertRaises(ProbeCorrupto):
            pr.cargar_probe(self.raiz, "p1")
        self.assertFalse(self.evals.exists())

    def test_ciclos_agotados(self):
        (self.raiz / ".harmessi" / "improvement" / "budget.json").write_text(
            json.dumps({"max_probe_cycles": 1}), encoding="utf-8")
        self.probe(FakeAdapter(TODOS, TODOS), probe_id="p1")
        self.editar_probe("p1", outcome="inconclusive", motivos=["wall_clock"])  # no bloquea por decisión pendiente
        ad = FakeAdapter(TODOS, TODOS)
        with self.assertRaises(bud.PresupuestoAgotado):
            self.probe(ad, probe_id="p2")
        self.assertEqual(ad.invocaciones, 0)


class TestPrecondiciones(Base):
    def assertRechazo(self, codigo, **kw):
        ad = FakeAdapter(TODOS, TODOS)
        antes = snapshot(self.raiz)
        with self.assertRaises(ProbeRechazado) as ctx:
            self.probe(ad, **kw)
        self.assertEqual(ctx.exception.codigo, codigo)
        self.assertEqual(ad.invocaciones, 0)
        self.assertEqual(snapshot(self.raiz), antes)

    def test_estado_no_probable(self):
        cand.transicionar(self.raiz, self.c.candidate_id, "evaluated",
                          {"probe_id": "x", "decision_hash": "abc"})
        self.assertRechazo("ESTADO_NO_PROBABLE")

    def test_base_obsoleta(self):
        (self.raiz / ACTIVO).write_bytes(b"# Cambio externo\n")
        self.assertRechazo("BASE_OBSOLETA")

    def test_suite_incompatible(self):
        c2 = self.nueva_candidate("# Skill\notra\n", suite_ids=("otra-suite",))
        self.assertRechazo("SUITE_INCOMPATIBLE", candidate_id=c2.candidate_id)

    def test_suite_compatible_con_ids(self):
        c2 = self.nueva_candidate("# Skill\notra\n", suite_ids=("suite-fake",))
        p = self.probe(FakeAdapter(TODOS, TODOS), candidate_id=c2.candidate_id)
        self.assertEqual(p["status"], "completed")

    def test_suite_invalida(self):
        self.assertRechazo("SUITE_INVALIDA", suite=Path(self._tmp_suite.name) / "no-existe.suite.json")

    def test_probe_id_invalido(self):
        for pid in ("../x", "", "-a", "a" * 65, "a/b"):
            with self.subTest(pid=pid):
                self.assertRechazo("PROBE_ID_INVALIDO", probe_id=pid)

    def test_probe_existente(self):
        self.probe(FakeAdapter(TODOS, TODOS))
        ad = FakeAdapter(TODOS, TODOS)
        with self.assertRaises(ProbeRechazado) as ctx:
            self.probe(ad)
        self.assertEqual(ctx.exception.codigo, "PROBE_EXISTENTE")
        self.assertEqual(ad.invocaciones, 0)


class TestPoliticaYEvidencia(Base):
    def test_politica_congelada(self):
        pol = ProbePolicy(repeats=2, secondary=("mean_score",))
        self.probe(FakeAdapter(TODOS, TODOS), pol)
        datos = pr.cargar_probe(self.raiz, "p1")
        self.assertEqual(datos["policy_hash"], hash_policy(pol))
        self.assertEqual(datos["policy"], pol.a_dict())
        with self.assertRaises(dataclasses.FrozenInstanceError):
            pol.repeats = 1  # type: ignore[misc]
        self.assertFalse(hasattr(pr, "cambiar_politica"))

    def test_probe_json_running_antes_de_ejecutar(self):
        visto = {}

        class Espia(FakeAdapter):
            def invoke(inner, request):  # noqa: N805
                if "datos" not in visto:
                    visto["datos"] = pr.cargar_probe(self.raiz, "p1")
                return super().invoke(request)

        self.probe(Espia(TODOS, TODOS))
        self.assertEqual(visto["datos"]["status"], "running")
        self.assertIsNone(visto["datos"]["outcome"])
        self.assertEqual(visto["datos"]["policy_hash"], hash_policy(ProbePolicy()))

    def test_campos_y_sha(self):
        import hashlib
        p = self.probe(FakeAdapter(TODOS, TODOS))
        d = pr.cargar_probe(self.raiz, "p1")
        self.assertEqual(d["contract_version"], pr.PROBE_CONTRACT_VERSION)
        self.assertEqual(d["candidate_hash"], self.c.content_hash)
        self.assertEqual(d["baseline_surface_hash"], self.c.base_hash)
        self.assertEqual(d["suite"]["suite_id"], "suite-fake")
        self.assertEqual({r["run_id"] for r in d["runs"]}, {"p1-base-r1", "p1-cand-r1"})
        for r in d["runs"]:
            crudo = (self.evals / r["run_id"] / "result.json").read_bytes()
            self.assertEqual(r["sha256"], hashlib.sha256(crudo).hexdigest())
            self.assertEqual(r["identity_hash"], self.run_(r["run_id"])["run_manifest"]["identity_hash"])
        self.assertEqual(p, d)

    def test_privacidad(self):
        target = EvalTarget("fake", model="sk-abcdefghijk123456", effort="low")
        self.probe(FakeAdapter(TODOS, TODOS), target=target)
        texto = (self.raiz / ".harmessi" / "improvement" / "probes" / "p1" / "probe.json").read_text("utf-8")
        self.assertEqual(redactar_texto(texto), texto)
        self.assertIn("<TOKEN>", texto)
        self.assertNotIn("sk-abcdefghijk", texto)
        for prohibido in (MARCA_BASE, MARCA_CAND, "respondé", self._tmp.name, self._tmp_suite.name, "[GUIDANCE]"):
            self.assertNotIn(prohibido, texto)

    def test_cargar_probe_corrupto(self):
        self.probe(FakeAdapter(TODOS, TODOS))
        ruta = self.raiz / ".harmessi" / "improvement" / "probes" / "p1" / "probe.json"
        datos = json.loads(ruta.read_text("utf-8"))
        for mutar in (lambda d: d.update(contract_version=2), lambda d: d.update(policy_hash="0" * 64),
                      lambda d: d.pop("runs"), lambda d: d.update(outcome="raro")):
            malo = json.loads(json.dumps(datos))
            mutar(malo)
            ruta.write_text(json.dumps(malo), encoding="utf-8")
            with self.assertRaises(ProbeCorrupto):
                pr.cargar_probe(self.raiz, "p1")
        ruta.write_text("{no json", encoding="utf-8")
        with self.assertRaises(ProbeCorrupto):
            pr.cargar_probe(self.raiz, "p1")


class TestResume(Base):
    def test_resume_reutiliza_repeticiones_completas(self):
        pol = ProbePolicy(repeats=2)
        self.interrumpido(pol, corte=6)  # repetición 1 completa, la 2 sin ejecutar
        ad = FakeAdapter(TODOS, TODOS)
        p = self.probe(ad, pol, resume=True)
        self.assertEqual(ad.invocaciones, 6)  # solo la repetición 2
        self.assertEqual(p["outcome"], "success")
        self.assertEqual(len(p["runs"]), 4)
        est = self.estado_budget()
        self.assertEqual(est["probe_cycles"], 1)
        self.assertEqual(est["runs_by_candidate"][self.c.candidate_id], 6)
        self.assertEqual(len(p["sessions_utc"]), 2)

    def test_resume_sin_probe(self):
        with self.assertRaises(ProbeIncompatible):
            self.probe(FakeAdapter(TODOS, TODOS), resume=True)

    def test_probe_completado_no_se_reanuda(self):
        for pid, kw, outcome in (("pa", {}, "success"), ("pb", {"fallos": {"cand": [999, None]}}, "candidate_failure")):
            with self.subTest(outcome=outcome):
                self.probe(FakeAdapter(TODOS, TODOS, **kw), probe_id=pid)
                ad = FakeAdapter(TODOS, TODOS)
                with self.assertRaises(ProbeRechazado) as ctx:
                    self.probe(ad, probe_id=pid, resume=True)
                self.assertEqual(ctx.exception.codigo, "PROBE_COMPLETADO")
                self.assertEqual(ad.invocaciones, 0)
                if pid == "pa":
                    # 'pa' sin decisión bloquearía el probe nuevo: se marca como no bloqueante
                    # (el resume de 'pa' ya fue verificado arriba).
                    self.editar_probe("pa", outcome="inconclusive", motivos=["fallo_no_confirmado"])

    def test_resume_reutiliza_fallo_propio_y_reejecuta_entorno(self):
        self.probe(FakeAdapter(TODOS, TODOS, fallos={"cand": [999, None]}))
        self.editar_probe(status="running", outcome=None, motivos=[])
        ad = FakeAdapter(TODOS, TODOS)
        self.probe(ad, resume=True)
        self.assertEqual(ad.invocaciones, 0)  # el par con fallo_propio cuenta como completo
        # fallo_entorno: se re-ejecuta
        self.editar_probe("p1", outcome="inconclusive", motivos=["wall_clock"])  # no bloquea el probe p2
        self.probe(FakeAdapter(TODOS, TODOS, fallos={"cand": [999, "quota"]}), probe_id="p2")
        self.editar_probe("p2", status="running", outcome=None, motivos=[])
        ad2 = FakeAdapter(TODOS, TODOS)
        p = self.probe(ad2, probe_id="p2", resume=True, candidate_id=self.c.candidate_id)
        self.assertEqual(ad2.invocaciones, 6)
        self.assertEqual(p["outcome"], "success")

    def test_resume_incompatible_policy(self):
        self.interrumpido(ProbePolicy(repeats=2))
        ad = FakeAdapter(TODOS, TODOS)
        with self.assertRaises(ProbeIncompatible):
            self.probe(ad, ProbePolicy(repeats=1), resume=True)
        self.assertEqual(ad.invocaciones, 0)

    def test_resume_incompatible_candidate(self):
        self.interrumpido()
        c2 = self.nueva_candidate("# Skill\notra\n")
        with self.assertRaises(ProbeIncompatible):
            self.probe(FakeAdapter(TODOS, TODOS), candidate_id=c2.candidate_id, resume=True)

    def test_resume_incompatible_suite(self):
        self.interrumpido()
        otra = crear_suite(Path(self._tmp_suite.name) / "otra", sufijo=" distinto")
        with self.assertRaises(ProbeIncompatible):
            self.probe(FakeAdapter(TODOS, TODOS), suite=otra, resume=True)

    def test_resume_incompatible_target(self):
        self.interrumpido()
        with self.assertRaises(ProbeIncompatible):
            self.probe(FakeAdapter(TODOS, TODOS), target=EvalTarget("fake", model="m2", effort="low"),
                       resume=True)

    def test_resume_incompatible_seed(self):
        self.interrumpido(seed=1)
        with self.assertRaises(ProbeIncompatible):
            self.probe(FakeAdapter(TODOS, TODOS), seed=2, resume=True)

    def test_resume_incompatible_campos_persistidos(self):
        self.escribir_budget(max_probe_cycles=5, max_runs_per_candidate=10)
        for campo, valor in (("baseline_surface_hash", "0" * 64), ("cases_hash", "0" * 64),
                             ("budget_version", 2)):
            with self.subTest(campo=campo):
                pid = f"q-{campo[:4]}"
                self.interrumpido(probe_id=pid)
                self.editar_probe(pid, **{campo: valor})
                with self.assertRaises(ProbeIncompatible):
                    self.probe(FakeAdapter(TODOS, TODOS), probe_id=pid, resume=True)

    def test_resume_incompatible_identidad_cambio_otra_skill(self):
        pol = ProbePolicy(repeats=2)
        self.interrumpido(pol, corte=6)  # repetición 1 completa (par baseline+candidate)
        otra = self.raiz / ".claude/skills/lead-data-scientist/skills/otra-skill.md"
        otra.write_bytes(b"# nueva skill\n")
        with self.assertRaises(ProbeIncompatible):
            self.probe(FakeAdapter(TODOS, TODOS), pol, resume=True)

    def test_resume_incompatible_sha_alterado(self):
        pol = ProbePolicy(repeats=2)
        self.interrumpido(pol, corte=6)
        ruta = self.evals / "p1-base-r1" / "result.json"
        ruta.write_bytes(ruta.read_bytes() + b" ")
        with self.assertRaises(ProbeIncompatible):
            self.probe(FakeAdapter(TODOS, TODOS), pol, resume=True)


class TestRobustez(Base):
    def test_identidad_cambia_entre_repeticiones(self):
        raiz = self.raiz

        class Cambia(FakeAdapter):
            def invoke(inner, request):  # noqa: N805
                res = super().invoke(request)
                if inner.invocaciones == 7:  # primera invocación de la repetición 2
                    (raiz / ".claude/skills/lead-data-scientist/skills/extra.md").write_bytes(b"# x\n")
                return res

        p = self.probe(Cambia(TODOS, TODOS), ProbePolicy(repeats=2))
        self.assertEqual(p["outcome"], "inconclusive")
        self.assertEqual(p["motivos"], ["identidad_cambio_durante_corrida"])
        self.assertEqual(len(p["runs"]), 2)
        self.assertFalse((self.evals / "p1-base-r2").exists())

    def test_identidad_invalida(self):
        from unittest import mock
        real = pr.construir_manifest
        with mock.patch.object(pr, "construir_manifest",
                               side_effect=lambda *a, **k: {**real(*a, **k), "problemas": ["x"]}):
            ad = FakeAdapter(TODOS, TODOS)
            with self.assertRaises(ProbeRechazado) as ctx:
                self.probe(ad)
        self.assertEqual(ctx.exception.codigo, "IDENTIDAD_INVALIDA")
        self.assertEqual(ad.invocaciones, 0)

    def test_guia_demasiado_grande(self):
        c2 = self.nueva_candidate("# Skill\n" + "x" * 100_100 + "\n")
        ad = FakeAdapter(TODOS, TODOS)
        with self.assertRaises(ProbeRechazado) as ctx:
            self.probe(ad, candidate_id=c2.candidate_id)
        self.assertEqual(ctx.exception.codigo, "GUIA_DEMASIADO_GRANDE")
        self.assertEqual(ad.invocaciones, 0)
        self.assertEqual(self.estado_budget()["probe_cycles"], 0)

    def test_concurrencia_mismo_probe_id(self):
        import threading
        resultados = []

        def correr():
            try:
                self.probe(FakeAdapter(TODOS, TODOS))
                resultados.append("ok")
            except ProbeRechazado as exc:
                resultados.append(exc.codigo)

        hilos = [threading.Thread(target=correr) for _ in range(2)]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join()
        self.assertEqual(sorted(resultados), ["PROBE_EXISTENTE", "ok"])
        self.assertEqual(self.estado_budget()["probe_cycles"], 1)

    def test_evals_root_enlace(self):
        import os
        destino = Path(self._tmp_suite.name) / "real_evals"
        destino.mkdir()
        enlace = Path(self._tmp_suite.name) / "enlace_evals"
        try:
            os.symlink(destino, enlace, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks no disponibles")
        ad = FakeAdapter(TODOS, TODOS)
        with self.assertRaises(ProbeRechazado) as ctx:
            self.probe(ad, evals_root=enlace)
        self.assertEqual(ctx.exception.codigo, "RUTA_INVALIDA")
        self.assertEqual(ad.invocaciones, 0)


class TestGuidanceAdapter(unittest.TestCase):
    def test_antepone_guia_y_delega(self):
        from tools.providers.core import InvocationRequest
        ad = FakeAdapter("a", "b")
        g = GuidanceAdapter(ad, "guía X")
        req = InvocationRequest(prompt="hola", role="eval", model="m")
        g.invoke(req)
        self.assertEqual(ad.prompts[0], "[GUIDANCE]\nguía X\n[/GUIDANCE]\n\nhola")
        self.assertEqual(req.prompt, "hola")
        self.assertIsNone(g.detect())


if __name__ == "__main__":
    unittest.main()

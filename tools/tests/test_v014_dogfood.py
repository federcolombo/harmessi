"""Dogfoods A-I de Harmessi v0.14.0 (Change 6, parte B; R5 de la spec del release hardening).

Escenario base realista: un repo temporal (nombre con espacios y Unicode) que contiene una COPIA del
contenido real de `diagnosing-bugs.md` (leída del repo real, solo lectura) como superficie baseline, y
una suite sintética de debugging (4 casos con scorer `contains`). La candidate es esa skill más una
sección experimental; el adapter determinista contesta según un marcador presente en la guía inyectada.

Todo es determinista y sin red. Se corre con `python -m unittest tools.tests.test_v014_dogfood` o con
`pytest tools/tests/test_v014_dogfood.py` desde la raíz del repo. Nada escribe fuera de directorios
temporales.

Los Changes fixture con aprobaciones `console_confirmed` que arma `crear_change` son FALSOS: validan el
gate (la lógica de verificación), NO son una aprobación real del autor.
"""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tools.harmessi_bench import storage
from tools.harmessi_bench.core import EvalTarget
from tools.harmessi_bench.redact import redactar_texto
from tools.harmessi_improve import budget as bud
from tools.harmessi_improve import candidate as cand
from tools.harmessi_improve import cycle as cy
from tools.harmessi_improve import decision as dec
from tools.harmessi_improve import lessons as les
from tools.harmessi_improve import probe as pr
from tools.harmessi_improve import promotion as pm
from tools.harmessi_improve.budget import PresupuestoInvalido
from tools.harmessi_improve.candidate import CandidateRechazada
from tools.harmessi_improve.cycle import CicloAnidado
from tools.harmessi_improve.decision import PromocionNoRespaldada
from tools.harmessi_improve.lessons import LessonRechazada
from tools.harmessi_improve.policy import ProbePolicy
from tools.harmessi_improve.promotion import PromocionBloqueada
from tools.harmessi_improve.tests._fakes import FakeAdapter
from tools.harmessi_improve.tests._helpers import (
    ACTIVO, CHANGE_ID, GLOSSARY_BASICO, PROVENANCE, crear_change, crear_repo, snapshot,
)
from tools.providers.core import InvocationResult

RAIZ_REAL = Path(__file__).resolve().parents[2]
SKILL_REAL = RAIZ_REAL / ACTIVO

CASOS = ("debugging-reproducir", "debugging-hipotesis", "debugging-bisect", "debugging-verificar")
SUITE_ID = "suite-debugging"
MARCA_EXPERIMENTAL = "EXPERIMENTAL-CANDIDATA-V2"
SECCION_EXPERIMENTAL = (
    f"\n## 10. Sección experimental\n\n{MARCA_EXPERIMENTAL}: reproducir primero y luego bisectar el cambio.\n"
)
AHORA = datetime(2026, 10, 23, 14, 0, tzinfo=timezone.utc)


def _sha(datos: bytes) -> str:
    return hashlib.sha256(datos).hexdigest()


def crear_suite_debugging(directorio: Path, suite_id: str = SUITE_ID, sufijo: str = "") -> Path:
    """Suite sintética de debugging: 4 casos con scorer contains `ok-<id>`. Devuelve el manifest."""
    directorio = Path(directorio)
    directorio.mkdir(parents=True, exist_ok=True)
    escenarios = [
        {"scenario_id": c, "prompt": f"[CASO {c}] Respondé el paso{sufijo}.", "category": "debugging",
         "tags": [], "expected": {"tipo": "contains", "valores": [f"ok-{c}"]}}
        for c in CASOS
    ]
    (directorio / f"{suite_id}.cases.json").write_text(
        json.dumps({"case_contract_version": 1, "escenarios": escenarios}, ensure_ascii=False), encoding="utf-8")
    ruta = directorio / f"{suite_id}.suite.json"
    ruta.write_text(json.dumps({
        "suite_contract_version": 1, "suite_id": suite_id, "suite_version": 1,
        "cases_file": f"{suite_id}.cases.json", "case_ids": list(CASOS)}), encoding="utf-8")
    return ruta


class AdapterDebugging(FakeAdapter):
    """Determinista: distingue candidate (guía con MARCA_EXPERIMENTAL) de baseline y contesta `ok-<caso>`
    solo para los casos que ese rol 'resuelve'."""

    def __init__(self, pasa_base=CASOS, pasa_cand=CASOS, fallos=None) -> None:
        super().__init__("", "", fallos)
        self.pasa = {"base": set(pasa_base), "cand": set(pasa_cand)}

    def invoke(self, request) -> InvocationResult:
        self.invocaciones += 1
        self.prompts.append(request.prompt)
        rol = "cand" if MARCA_EXPERIMENTAL in request.prompt else "base"
        falla = self.fallos.get(rol)
        if falla and falla[0] > 0:
            falla[0] -= 1
            return InvocationResult("fake", 1, "", "fallo simulado", False, falla[1], 0.01)
        salida = " ".join(f"ok-{c}" for c in CASOS if f"[CASO {c}]" in request.prompt and c in self.pasa[rol])
        return InvocationResult("fake", 0, salida or "sin respuesta", "", True, None, 0.01)


MEJORA = (CASOS[:2], CASOS)   # baseline 2/4, candidate 4/4
EMPEORA = (CASOS, CASOS[:2])  # baseline 4/4, candidate 2/4
IGUAL = (CASOS, CASOS)


class BaseDogfood(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="dogfood ñandú ")
        self._tmp_suite = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.addCleanup(self._tmp_suite.cleanup)
        self.raiz = crear_repo(Path(self._tmp.name) / "repo con espacios ñandú")
        self.skill_real_bytes = SKILL_REAL.read_bytes()
        texto = self.skill_real_bytes.decode("utf-8").replace("\r\n", "\n")
        self.base_texto = texto
        (self.raiz / ACTIVO).write_bytes(texto.encode("utf-8"))
        self.contenido_cand = texto + SECCION_EXPERIMENTAL
        self.suite = crear_suite_debugging(Path(self._tmp_suite.name))
        self.target = EvalTarget("fake", model="m1", effort="low")
        self.evals = self.raiz / ".harmessi" / "evals"
        self.dir_imp = self.raiz / ".harmessi" / "improvement"

    # --- helpers ---
    def nueva_candidate(self, contenido=None, hipotesis="la sección experimental mejora el orden"):
        return cand.crear_candidate(self.raiz, ACTIVO, contenido or self.contenido_cand, hipotesis,
                                    dict(PROVENANCE))

    def probe(self, adapter, c=None, policy=None, probe_id="p1", **kw):
        c = c or self.nueva_candidate()
        return pr.ejecutar_probe(self.raiz, c.candidate_id, kw.pop("suite", self.suite), adapter,
                                 kw.pop("target", self.target), policy or ProbePolicy(), probe_id, **kw)

    def flujo(self, pasa, repeats=1, probe_id="p1", c=None):
        """probe + decisión aplicada. Devuelve `(candidate_final, decision)`."""
        c = c or self.nueva_candidate()
        self.probe(AdapterDebugging(*pasa), c, ProbePolicy(repeats=repeats), probe_id)
        d = dec.decidir(self.raiz, probe_id)
        return dec.aplicar_decision(self.raiz, probe_id, ahora=AHORA), d

    def escribir_budget(self, **valores):
        self.dir_imp.mkdir(parents=True, exist_ok=True)
        (self.dir_imp / "budget.json").write_text(json.dumps(valores), encoding="utf-8")

    def fuera_de_harmessi(self):
        return {k: v for k, v in snapshot(self.raiz).items() if not k.startswith(".harmessi/")}

    def promovida_lista(self):
        """Candidate promotable (flujo B) + propuesta de promoción. Devuelve `(candidate, propuesta)`."""
        c, _ = self.flujo(MEJORA)
        return c, pm.proponer_promocion(self.raiz, c.candidate_id)


class TestDogfoodA(BaseDogfood):
    """A: flujo completo baseline vs candidate con evidencia en disco, sin tocar la skill real."""

    def test_evidencia_en_disco(self):
        hash_real_antes = _sha(self.skill_real_bytes)
        activo_antes = (self.raiz / ACTIVO).read_bytes()
        c = self.nueva_candidate()
        self.probe(AdapterDebugging(*MEJORA), c, ProbePolicy(repeats=2))
        ruta_probe = self.dir_imp / "probes" / "p1" / "probe.json"
        self.assertTrue(ruta_probe.is_file())
        probe = json.loads(ruta_probe.read_text("utf-8"))
        self.assertEqual(len(probe["runs"]), 4)  # 2 * repeats
        identidades = {"baseline": set(), "candidate": set()}
        for entrada in probe["runs"]:
            result = self.evals / entrada["run_id"] / "result.json"
            self.assertTrue(result.is_file(), entrada["run_id"])
            datos = json.loads(result.read_text("utf-8"))
            manifest = datos["run_manifest"]
            self.assertTrue(manifest["identity_hash"])
            self.assertEqual(manifest["identity_hash"], entrada["identity_hash"])
            identidades[entrada["role"]].add(manifest["identity_hash"])
        self.assertEqual({k: len(v) for k, v in identidades.items()}, {"baseline": 1, "candidate": 1})
        self.assertTrue(identidades["baseline"].isdisjoint(identidades["candidate"]))
        d = dec.decidir(self.raiz, "p1", registrar=True)
        ruta_dec = self.dir_imp / "decisions" / "p1" / "decision.json"
        self.assertTrue(ruta_dec.is_file())
        guardada = json.loads(ruta_dec.read_text("utf-8"))
        self.assertEqual(guardada["decision_hash"], d["decision_hash"])
        self.assertTrue(d["decision_hash"])
        self.assertEqual(d["verdict"], "candidate_better")
        # la skill real del repo y el activo del repo temporal no cambian
        self.assertEqual(_sha(SKILL_REAL.read_bytes()), hash_real_antes)
        self.assertEqual((self.raiz / ACTIVO).read_bytes(), activo_antes)

    def test_guias_inyectadas_distinguen_baseline_y_candidate(self):
        ad = AdapterDebugging(*IGUAL)
        self.probe(ad)
        con_marca = [p for p in ad.prompts if MARCA_EXPERIMENTAL in p]
        self.assertEqual(len(con_marca), len(CASOS))
        self.assertEqual(len(ad.prompts) - len(con_marca), len(CASOS))


class TestDogfoodB(BaseDogfood):
    """B: candidate mejor (baseline 2/4, candidate 4/4) => candidate_better => promotable."""

    def test_candidate_mejor_es_promotable(self):
        c, d = self.flujo(MEJORA)
        self.assertEqual((d["verdict"], d["candidate_status"]), ("candidate_better", "promotable"))
        self.assertEqual(c.status, "promotable")
        self.assertEqual(dec.verificar_promotable(self.raiz, c.candidate_id)["verdict"], "candidate_better")
        self.assertEqual(d["n_escenarios"], 4)


class TestDogfoodC(BaseDogfood):
    """C: candidate peor => baseline_better => rejected."""

    def test_candidate_peor_es_rechazada(self):
        c, d = self.flujo(EMPEORA)
        self.assertEqual((d["verdict"], d["candidate_status"]), ("baseline_better", "rejected"))
        self.assertEqual(c.status, "rejected")
        with self.assertRaises(PromocionNoRespaldada):
            dec.verificar_promotable(self.raiz, c.candidate_id)


class TestDogfoodD(BaseDogfood):
    """D: equivalente 4/4 vs 4/4 => equivalent => rejected."""

    def test_equivalente_es_rechazada(self):
        c, d = self.flujo(IGUAL)
        self.assertEqual((d["verdict"], d["candidate_status"]), ("equivalent", "rejected"))
        self.assertEqual(c.status, "rejected")


class TestDogfoodE(BaseDogfood):
    """E: evidencia no disponible o no comparable => inconclusive y NUNCA baseline_better."""

    def test_availability_error_en_candidate(self):
        self.escribir_budget(max_retries=2)
        self.probe(AdapterDebugging(*IGUAL, fallos={"cand": [999, "quota"]}))
        runs = json.loads((self.dir_imp / "probes" / "p1" / "probe.json").read_text("utf-8"))
        self.assertIn(runs["outcome"], ("environment_failure", "inconclusive"))
        d = dec.decidir(self.raiz, "p1")
        self.assertEqual(d["verdict"], "inconclusive")
        self.assertNotEqual(d["verdict"], "baseline_better")
        self.assertEqual(dec.aplicar_decision(self.raiz, "p1", ahora=AHORA).status, "inconclusive")

    def test_fallo_de_baseline_nunca_es_baseline_better(self):
        self.escribir_budget(max_retries=2)
        self.probe(AdapterDebugging(*IGUAL, fallos={"base": [999, None]}))
        d = dec.decidir(self.raiz, "p1")
        self.assertEqual(d["verdict"], "inconclusive")

    def test_set_de_casos_distinto_no_se_compara(self):
        # probe interrumpido por wall_clock; reanudar con una suite de casos distinta es incompatible.
        ad = AdapterDebugging(*IGUAL)
        inicio = datetime.now(timezone.utc)
        reloj = lambda: inicio + timedelta(hours=2) if ad.invocaciones >= 3 else inicio  # noqa: E731
        p = self.probe(ad, ahora=reloj)
        self.assertEqual(p["outcome"], "inconclusive")
        otra = crear_suite_debugging(Path(self._tmp_suite.name) / "otra", sufijo=" distinto")
        with self.assertRaises(pr.ProbeIncompatible):
            self.probe(AdapterDebugging(*IGUAL), suite=otra, resume=True)
        # el probe interrumpido es decidible, pero nunca produce un ganador: inconclusive
        self.assertEqual(dec.decidir(self.raiz, "p1")["verdict"], "inconclusive")


class TestDogfoodF(BaseDogfood):
    """F: superficies protegidas se rechazan ANTES del probe; sin probe, sin runs, sin budget consumido."""

    PROTEGIDAS = ("tools/x.py", ".claude/agents/a.md", ".claude/guardrails.json")

    def assertSinProbe(self):
        self.assertFalse((self.dir_imp / "probes").exists())
        self.assertFalse(self.evals.exists())
        self.assertEqual(bud.estado(self.raiz)["probe_cycles"], 0)

    def test_candidate_sobre_protegida(self):
        for ruta in self.PROTEGIDAS:
            with self.subTest(ruta=ruta):
                with self.assertRaises(CandidateRechazada) as cm:
                    cand.crear_candidate(self.raiz, ruta, "# nuevo\ncontenido distinto\n", "hip",
                                         dict(PROVENANCE))
                self.assertEqual(cm.exception.codigo, "SUPERFICIE_PROTEGIDA")
        self.assertSinProbe()

    def test_ciclo_rechaza_protegidas_sin_invocar(self):
        ad = AdapterDebugging(*MEJORA)
        propuestas = [{"base_surface": ruta, "content": "# x\n", "hypothesis": "h",
                       "provenance": dict(PROVENANCE)} for ruta in self.PROTEGIDAS]
        r = cy.ejecutar_ciclo(self.raiz, propuestas, self.suite, ad, self.target, ProbePolicy())
        self.assertEqual(r["resultados"], [])
        self.assertEqual([x["codigo"] for x in r["rechazos"]], ["SUPERFICIE_PROTEGIDA"] * 3)
        self.assertEqual(ad.invocaciones, 0)
        self.assertSinProbe()


class TestDogfoodG(BaseDogfood):
    """G: propuesta de promoción, gate T1 y aplicación bloqueada sin gate."""

    def test_propuesta_produce_artefactos(self):
        c, prop = self.promovida_lista()
        carpeta = self.dir_imp / "proposals" / c.candidate_id
        self.assertTrue((carpeta / "proposal.json").is_file(), "promotion proposal ready")
        diff = (carpeta / "change.diff").read_text("utf-8")
        datos = json.loads((carpeta / "proposal.json").read_text("utf-8"))
        self.assertEqual(datos["candidate_id"], c.candidate_id)
        self.assertEqual(datos["decision_hash"], prop["decision_hash"])
        self.assertTrue(prop["decision_hash"])
        self.assertTrue(diff.strip(), "change.diff no debe estar vacío")
        self.assertIn(f"+{MARCA_EXPERIMENTAL}", diff)
        self.assertEqual(pm.cargar_propuesta(self.raiz, c.candidate_id), prop)

    def test_gate_bloquea_sin_t1(self):
        c, prop = self.promovida_lista()
        cid = c.candidate_id
        self.assertEqual(pm.evaluar_gate(self.raiz, cid, CHANGE_ID), [pm.CHANGE_INEXISTENTE])
        crear_change(self.raiz, prop["proposal_hash"], canal="declared")  # aprobaciones T0
        self.assertEqual(pm.evaluar_gate(self.raiz, cid, CHANGE_ID),
                         ["APROBACION_PROPOSAL_NO_T1", "APROBACION_SPEC_NO_T1", "APROBACION_DESIGN_NO_T1"])
        crear_change(self.raiz, prop["proposal_hash"], citar=False)  # T1 pero sin citar la propuesta
        self.assertEqual(pm.evaluar_gate(self.raiz, cid, CHANGE_ID), [pm.PROPUESTA_NO_CITADA])

    def test_aplicar_sin_gate_no_escribe(self):
        c, prop = self.promovida_lista()
        antes = snapshot(self.raiz)
        with self.assertRaises(PromocionBloqueada):
            pm.aplicar_promocion(self.raiz, c.candidate_id, CHANGE_ID)  # sin Change
        self.assertEqual(snapshot(self.raiz), antes)
        crear_change(self.raiz, prop["proposal_hash"], canal="declared")
        antes = snapshot(self.raiz)
        with self.assertRaises(PromocionBloqueada):
            pm.aplicar_promocion(self.raiz, c.candidate_id, CHANGE_ID)
        self.assertEqual(snapshot(self.raiz), antes)
        self.assertEqual((self.raiz / ACTIVO).read_text("utf-8"), self.base_texto)

    def test_gate_pasa_con_change_fixture(self):
        """ATENCIÓN: el Change lo arma `crear_change` en el test con aprobaciones `console_confirmed`
        FALSAS. Esto valida que el gate reconoce un T1 bien formado; NO es una aprobación real."""
        c, prop = self.promovida_lista()
        crear_change(self.raiz, prop["proposal_hash"])
        self.assertEqual(pm.evaluar_gate(self.raiz, c.candidate_id, CHANGE_ID), [])


class TestDogfoodH(BaseDogfood):
    """H: lesson evidence-backed sobre evidencia de B (repeats=2), con sanitización."""

    def setUp(self):
        super().setUp()
        crear_change(self.raiz, "h")  # Change abierto fixture (en_implementacion)
        self.lessons_dir = self.dir_imp / "lessons"
        _, self.decision = self.flujo(MEJORA, repeats=2)
        self.refs = [{"probe_id": "p1", "decision_hash": self.decision["decision_hash"], "suite_id": SUITE_ID}]
        self.args = dict(pattern="Las guias largas degradan el seguimiento de pasos",
                         recommendation="Preferir guias breves con pasos numerados",
                         contexts=["python-debugging"], evidence_refs=self.refs, ahora=AHORA)

    def crear(self, **kw):
        args = dict(self.args)
        args.update(kw)
        return les.crear_lesson(self.raiz, CHANGE_ID, **args)

    def codigo(self, **kw):
        with self.assertRaises(LessonRechazada) as cm:
            self.crear(**kw)
        return cm.exception.codigo

    def test_flujo_previo_no_creo_lessons(self):
        self.assertFalse(self.lessons_dir.exists())

    def test_lesson_evidence_backed(self):
        l = self.crear()
        self.assertEqual(l["status"], "evidence-backed")
        self.assertEqual(l["evidence_refs"], self.refs)
        self.assertEqual(l["applicability"], {"contexts": ["python-debugging"]})
        self.assertEqual(les.cargar_lesson(self.raiz, l["lesson_id"]), l)
        self.assertTrue((self.lessons_dir / f"{l['lesson_id']}.json").is_file())

    def test_sanitizacion(self):
        (self.raiz / "GLOSSARY.md").write_text(GLOSSARY_BASICO, encoding="utf-8")
        self.assertEqual(self.codigo(recommendation="Revisar C:\\Users\\ana\\datos"), "CONTENIDO_SENSIBLE")
        self.assertEqual(self.codigo(recommendation="Escribir a ana@ejemplo.org"), "CONTENIDO_SENSIBLE")
        self.assertEqual(self.codigo(recommendation="Reducir el churn con guias breves"),
                         "CONOCIMIENTO_DEL_PROYECTO")
        self.assertFalse(self.lessons_dir.exists())  # ningún rechazo dejó una lesson

    def test_lessons_aplicables_solo_con_contexto_coincidente(self):
        l = self.crear()
        r = les.lessons_aplicables(self.raiz, ["python-debugging", "otro-tag"])
        self.assertEqual([x["lesson_id"] for x in r["aplicables"]], [l["lesson_id"]])
        r = les.lessons_aplicables(self.raiz, ["sql-modeling"])
        self.assertEqual(r["aplicables"], [])
        self.assertEqual([x["lesson_id"] for x in r["descartadas"]], [l["lesson_id"]])


class TestDogfoodI(BaseDogfood):
    """I: budget acotado, techo duro y ciclo no anidado."""

    def propuesta(self, i):
        return {"base_surface": ACTIVO, "hypothesis": f"variante {i}", "provenance": dict(PROVENANCE),
                "content": self.base_texto + SECCION_EXPERIMENTAL + f"\nvariante {i}\n"}

    def ciclo(self, n):
        return cy.ejecutar_ciclo(self.raiz, [self.propuesta(i) for i in range(1, n + 1)], self.suite,
                                 AdapterDebugging(*MEJORA), self.target, ProbePolicy())

    def test_max_candidates(self):
        self.escribir_budget(max_probe_cycles=5)  # max_candidates = default (3)
        r = self.ciclo(4)
        self.assertEqual(r["detenido_por"], "candidates")
        self.assertEqual(len(r["resultados"]), 3)

    def test_max_probe_cycles(self):
        self.escribir_budget(max_probe_cycles=1, max_candidates=5)
        r = self.ciclo(3)
        self.assertEqual(r["detenido_por"], "probe_cycles")

    def test_techo_duro(self):
        for clave in ("max_candidates", "max_probe_cycles"):
            with self.subTest(clave=clave):
                self.escribir_budget(**{clave: bud.HARD_CEILING[clave] + 1})
                with self.assertRaises(PresupuestoInvalido):
                    self.ciclo(1)
        self.assertFalse((self.dir_imp / "candidates").exists())

    def test_ciclo_anidado(self):
        self.dir_imp.mkdir(parents=True, exist_ok=True)
        (self.dir_imp / ".cycle.lock").write_text("pid=1\n", encoding="utf-8")
        with self.assertRaises(CicloAnidado):
            self.ciclo(1)
        self.assertTrue((self.dir_imp / ".cycle.lock").exists())  # el lock ajeno no se borra


class TestMetadataNoPromovible(BaseDogfood):
    """Una candidate con status editado a mano a promotable no pasa ninguna verificación."""

    def test_status_editado_a_mano(self):
        c = self.nueva_candidate(hipotesis="esta variante es mejor")
        ruta = self.dir_imp / "candidates" / c.candidate_id / "candidate.json"
        datos = json.loads(ruta.read_text("utf-8"))
        ev = {"probe_id": "p-inexistente", "decision_hash": "abc123"}
        datos["status"] = "promotable"
        datos["status_history"] += [
            {"status": "evaluated", "utc": "2026-10-23T13:00:00Z", "evidence": ev},
            {"status": "promotable", "utc": "2026-10-23T13:00:01Z", "evidence": ev}]
        ruta.write_text(json.dumps(datos), encoding="utf-8")
        with self.assertRaises(PromocionNoRespaldada):
            dec.verificar_promotable(self.raiz, c.candidate_id)
        with self.assertRaises(PromocionNoRespaldada):
            pm.proponer_promocion(self.raiz, c.candidate_id)
        crear_change(self.raiz, "h")
        self.assertTrue(pm.evaluar_gate(self.raiz, c.candidate_id, CHANGE_ID))  # bloqueado
        self.assertEqual((self.raiz / ACTIVO).read_text("utf-8"), self.base_texto)


class TestFlujoNormalNoToca(BaseDogfood):
    """Un flujo normal (A-G) no modifica nada del repo temporal fuera de .harmessi/, no crea lessons y
    no deja rutas ni datos sensibles en lo escrito."""

    def correr_flujo(self):
        antes = self.fuera_de_harmessi()
        c, prop = self.promovida_lista()
        crear_change(self.raiz, prop["proposal_hash"], canal="declared")
        with self.assertRaises(PromocionBloqueada):
            pm.aplicar_promocion(self.raiz, c.candidate_id, CHANGE_ID)
        return antes, c

    def test_no_modifica_fuera_de_harmessi(self):
        antes = self.fuera_de_harmessi()
        c, prop = self.promovida_lista()
        with self.assertRaises(PromocionBloqueada):
            pm.aplicar_promocion(self.raiz, c.candidate_id, CHANGE_ID)  # sin Change: no aplica
        self.assertEqual(self.fuera_de_harmessi(), antes)
        self.assertFalse((self.dir_imp / "lessons").exists())

    def test_privacidad_de_lo_escrito(self):
        self.correr_flujo()
        prohibidos = {str(self.raiz), self.raiz.as_posix(), json.dumps(str(self.raiz))[1:-1]}
        revisados = 0
        for base in (self.dir_imp, self.evals):
            for ruta in sorted(base.rglob("*")):
                if not ruta.is_file():
                    continue
                texto = ruta.read_text("utf-8")
                revisados += 1
                self.assertEqual(redactar_texto(texto), texto, ruta.name)
                for p in prohibidos:
                    self.assertNotIn(p, texto, ruta.name)
        self.assertGreater(revisados, 5)


if __name__ == "__main__":
    unittest.main()

"""Tests del modelo de candidate (v0.14 Change 1, R1-R9). Todo sintético en tempdirs."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.harmessi_improve import budget as bud
from tools.harmessi_improve import candidate as cand
from tools.harmessi_improve.candidate import CandidateCorrupta, CandidateRechazada
from tools.harmessi_improve.tests._helpers import (
    ACTIVO, GLOSSARY_BASICO, PROVENANCE, crear_repo, snapshot,
)

NUEVO = "# Skill\nVersión mejorada.\n"
EVID = {"probe_id": "probe-1", "decision_hash": "abc123"}


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.raiz = crear_repo(Path(self._tmp.name))

    def crear(self, **kw):
        args = dict(base_surface=ACTIVO, content=NUEVO, hypothesis="mejora la claridad",
                    provenance=dict(PROVENANCE))
        args.update(kw)
        return cand.crear_candidate(self.raiz, **args)

    def assertRechazo(self, codigo, **kw):
        antes = snapshot(self.raiz)
        with self.assertRaises(CandidateRechazada) as ctx:
            self.crear(**kw)
        self.assertEqual(ctx.exception.codigo, codigo)
        self.assertEqual(snapshot(self.raiz), antes, "no debe escribirse nada")


class TestContrato(Base):
    def test_campos_y_contrato(self):
        c = self.crear(suite_ids=("suite-a",))
        d = c.a_dict()
        self.assertEqual(cand.CANDIDATE_CONTRACT_VERSION, 1)
        for k in ("candidate_id", "base_surface", "base_hash", "content_hash", "hypothesis",
                  "provenance", "created_utc", "status", "status_history", "suite_ids",
                  "budget_version"):
            self.assertIn(k, d)
        self.assertEqual(c.status, "proposed")
        self.assertEqual(d["suite_ids"], ["suite-a"])
        self.assertRegex(c.candidate_id, r"^cand-[0-9a-f]{12}$")
        self.assertEqual(c.provenance["proposer_kind"], "script")

    def test_id_reproducible_e_idempotente(self):
        c1 = self.crear()
        c2 = self.crear()
        self.assertEqual(c1.candidate_id, c2.candidate_id)
        self.assertEqual(bud.estado(self.raiz)["candidates"], 1)
        self.assertEqual(len(cand.listar_candidates(self.raiz)), 1)

    def test_id_depende_del_contenido(self):
        c1 = self.crear()
        c2 = self.crear(content=NUEVO + "otra linea\n")
        self.assertNotEqual(c1.candidate_id, c2.candidate_id)

    def test_roundtrip_dict(self):
        c = self.crear()
        self.assertEqual(cand.Candidate.desde_dict(c.a_dict()), c)
        self.assertEqual(cand.cargar_candidate(self.raiz, c.candidate_id), c)

    def test_leer_contenido(self):
        c = self.crear()
        self.assertEqual(cand.leer_contenido(self.raiz, c.candidate_id), NUEVO)


class TestAislamiento(Base):
    def test_solo_escribe_en_improvement(self):
        antes = snapshot(self.raiz)
        c = self.crear()
        despues = snapshot(self.raiz)
        nuevos = set(despues) - set(antes)
        self.assertTrue(nuevos)
        for rel in nuevos:
            self.assertTrue(rel.startswith(".harmessi/improvement/"), rel)
        for rel, datos in antes.items():
            self.assertEqual(despues[rel], datos, rel)
        self.assertEqual((self.raiz / ACTIVO).read_bytes(), antes[ACTIVO])
        self.assertTrue((self.raiz / ".harmessi/improvement/candidates" / c.candidate_id / "content.md").is_file())


class TestRechazos(Base):
    def test_protegidas(self):
        for ruta in ("tools/x.py", ".claude/agents/a.md", ".claude/guardrails.json",
                     ".claude/skills/lead-data-scientist/skills/*.md"):
            with self.subTest(ruta=ruta):
                self.assertRechazo(cand.SUPERFICIE_PROTEGIDA_COD, base_surface=ruta)

    def test_rutas_invalidas(self):
        for ruta in ("../x.md", ".claude/../tools/x.py", "/etc/passwd", "C:\\x.md", "", "   ", None, 5, ["a"]):
            with self.subTest(ruta=ruta):
                self.assertRechazo(cand.RUTA_INVALIDA, base_surface=ruta)

    def test_proyecto(self):
        for ruta in ("GLOSSARY.md", "docs/x.md", "openspec/changes/x/proposal.md"):
            with self.subTest(ruta=ruta):
                self.assertRechazo(cand.SUPERFICIE_PROYECTO_COD, base_surface=ruta)

    def test_base_inexistente(self):
        self.assertRechazo(cand.BASE_ILEGIBLE,
                           base_surface=".claude/skills/lead-data-scientist/skills/no-existe.md")

    def test_sin_cambio(self):
        self.assertRechazo(cand.SIN_CAMBIO, content=(self.raiz / ACTIVO).read_text(encoding="utf-8"))

    def test_sin_cambio_ignora_eol(self):
        self.assertRechazo(cand.SIN_CAMBIO, content="# Skill\r\nBase original.\r\n")

    def test_contenido_invalido(self):
        for contenido in ("", "   \n", "a\x00b", "x" * (cand.MAX_CONTENIDO_BYTES + 1), None, b"bytes"):
            with self.subTest(contenido=repr(contenido)[:20]):
                self.assertRechazo(cand.CONTENIDO_INVALIDO, content=contenido)

    def test_hipotesis_invalida(self):
        for h in ("", "  ", "h" * 1001, None, 3):
            with self.subTest(h=repr(h)[:20]):
                self.assertRechazo(cand.CONTENIDO_INVALIDO, hypothesis=h)

    def test_provenance_invalida(self):
        casos = [
            None,
            {},
            {"proposer_kind": "llm"},
            {"proposer_kind": "robot", "proposer_label": "x"},
            {"proposer_kind": "llm", "proposer_label": ""},
            {"proposer_kind": "llm", "proposer_label": "x" * 81},
            {"proposer_kind": "llm", "proposer_label": "x", "cot": "razonamiento"},
            {"proposer_kind": "llm", "proposer_label": 3},
        ]
        for p in casos:
            with self.subTest(p=repr(p)[:40]):
                self.assertRechazo(cand.PROVENANCE_INVALIDA, provenance=p)

    def test_suite_ids_invalido(self):
        self.assertRechazo(cand.CONTENIDO_INVALIDO, suite_ids=("ok", ""))
        self.assertRechazo(cand.CONTENIDO_INVALIDO, suite_ids="suite")


class TestPrivacidad(Base):
    def test_sensible(self):
        casos = {
            "ruta": "ver C:\\Users\\juan\\datos\\x.csv",
            "email": "contactar a persona@example.com",
            "token": "usar ghp_" + "a" * 36,
        }
        for nombre, texto in casos.items():
            with self.subTest(campo="content", caso=nombre):
                self.assertRechazo(cand.CONTENIDO_SENSIBLE, content=NUEVO + texto + "\n")
            with self.subTest(campo="hypothesis", caso=nombre):
                self.assertRechazo(cand.CONTENIDO_SENSIBLE, hypothesis=texto)

    def test_etiqueta_sensible(self):
        self.assertRechazo(cand.CONTENIDO_SENSIBLE,
                           provenance={"proposer_kind": "human", "proposer_label": "juan@example.com"})

    def test_glossary(self):
        (self.raiz / "GLOSSARY.md").write_text(GLOSSARY_BASICO, encoding="utf-8")
        self.assertRechazo(cand.CONOCIMIENTO_DEL_PROYECTO, content=NUEVO + "Reducir el Churn.\n")
        self.assertRechazo(cand.CONOCIMIENTO_DEL_PROYECTO, hypothesis="baja el churn")

    def test_glossary_limite_de_palabra(self):
        (self.raiz / "GLOSSARY.md").write_text(GLOSSARY_BASICO, encoding="utf-8")
        c = self.crear(content=NUEVO + "churnear no es un termino\n")
        self.assertEqual(c.status, "proposed")

    def test_glossary_ilegible_fail_closed(self):
        (self.raiz / "GLOSSARY.md").write_bytes(b"\xff\xfe\x00\x80 no utf8 \xc3\x28")
        self.assertRechazo(cand.CONOCIMIENTO_DEL_PROYECTO)


class TestIntegridad(Base):
    def test_tampering_content(self):
        c = self.crear()
        ruta = self.raiz / ".harmessi/improvement/candidates" / c.candidate_id / "content.md"
        ruta.write_text("# manipulado\n", encoding="utf-8")
        with self.assertRaises(CandidateCorrupta):
            cand.cargar_candidate(self.raiz, c.candidate_id)
        with self.assertRaises(CandidateCorrupta):
            cand.leer_contenido(self.raiz, c.candidate_id)

    def test_json_corrupto_y_contrato(self):
        c = self.crear()
        ruta = self.raiz / ".harmessi/improvement/candidates" / c.candidate_id / "candidate.json"
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        datos["contract_version"] = 99
        ruta.write_text(json.dumps(datos), encoding="utf-8")
        with self.assertRaises(CandidateCorrupta):
            cand.cargar_candidate(self.raiz, c.candidate_id)
        ruta.write_text("{no json", encoding="utf-8")
        with self.assertRaises(CandidateCorrupta):
            cand.cargar_candidate(self.raiz, c.candidate_id)

    def test_id_invalido_o_inexistente(self):
        for i in ("../x", "cand-XYZ", "cand-0123456789ab", "", None):
            with self.subTest(i=i):
                with self.assertRaises(CandidateCorrupta):
                    cand.cargar_candidate(self.raiz, i)

    def test_base_vigente(self):
        c = self.crear()
        self.assertTrue(cand.base_vigente(self.raiz, c))
        (self.raiz / ACTIVO).write_text("# Skill\nEditada.\n", encoding="utf-8")
        self.assertFalse(cand.base_vigente(self.raiz, c))

    def test_base_vigente_eol_neutral(self):
        c = self.crear()
        (self.raiz / ACTIVO).write_bytes(b"# Skill\r\nBase original.\r\n")
        self.assertTrue(cand.base_vigente(self.raiz, c))


class TestTransiciones(Base):
    def test_camino_feliz(self):
        c = self.crear()
        c = cand.transicionar(self.raiz, c.candidate_id, "evaluated", EVID)
        self.assertEqual(c.status, "evaluated")
        c = cand.transicionar(self.raiz, c.candidate_id, "promotable", EVID)
        recargada = cand.cargar_candidate(self.raiz, c.candidate_id)
        self.assertEqual(recargada.status, "promotable")
        self.assertEqual([h["status"] for h in recargada.status_history],
                         ["proposed", "evaluated", "promotable"])
        self.assertEqual(recargada.status_history[-1]["evidence"], EVID)

    def test_inconclusive_vuelve_a_evaluated(self):
        c = self.crear()
        cand.transicionar(self.raiz, c.candidate_id, "evaluated", EVID)
        cand.transicionar(self.raiz, c.candidate_id, "inconclusive", EVID)
        c = cand.transicionar(self.raiz, c.candidate_id, "evaluated", EVID)
        self.assertEqual(c.status, "evaluated")

    def test_invalidas(self):
        c = self.crear()
        for destino in ("promotable", "rejected", "inconclusive", "proposed", "bogus", None):
            with self.subTest(destino=destino):
                with self.assertRaises(CandidateRechazada) as ctx:
                    cand.transicionar(self.raiz, c.candidate_id, destino, EVID)
                self.assertEqual(ctx.exception.codigo, cand.TRANSICION_INVALIDA)

    def test_terminales(self):
        for terminal in ("promotable", "rejected"):
            with self.subTest(terminal=terminal):
                c = self.crear(content=NUEVO + terminal + "\n")
                cand.transicionar(self.raiz, c.candidate_id, "evaluated", EVID)
                cand.transicionar(self.raiz, c.candidate_id, terminal, EVID)
                for destino in cand.ESTADOS:
                    with self.assertRaises(CandidateRechazada) as ctx:
                        cand.transicionar(self.raiz, c.candidate_id, destino, EVID)
                    self.assertEqual(ctx.exception.codigo, cand.TRANSICION_INVALIDA)

    def test_evidencia_requerida(self):
        c = self.crear()
        malas = [None, {}, {"probe_id": "p"}, {"probe_id": "", "decision_hash": "h"},
                 {"probe_id": "p", "decision_hash": " "}, {"probe_id": "p", "decision_hash": 3},
                 {"probe_id": "p", "decision_hash": "h", "extra": "x"}]
        for ev in malas:
            with self.subTest(ev=repr(ev)):
                with self.assertRaises(CandidateRechazada) as ctx:
                    cand.transicionar(self.raiz, c.candidate_id, "evaluated", ev)
                self.assertEqual(ctx.exception.codigo, cand.EVIDENCIA_REQUERIDA)
        cand.transicionar(self.raiz, c.candidate_id, "evaluated", EVID)
        with self.assertRaises(CandidateRechazada) as ctx:
            cand.transicionar(self.raiz, c.candidate_id, "promotable", None)
        self.assertEqual(ctx.exception.codigo, cand.EVIDENCIA_REQUERIDA)
        self.assertEqual(cand.cargar_candidate(self.raiz, c.candidate_id).status, "evaluated")


class TestBudgetEnCreacion(Base):
    def test_cuarto_candidate_agota(self):
        b = bud.ImprovementBudget(max_candidates=3)
        for i in range(3):
            self.crear(content=NUEVO + f"v{i}\n", budget=b)
        antes = snapshot(self.raiz)
        with self.assertRaises(bud.PresupuestoAgotado) as ctx:
            self.crear(content=NUEVO + "v3\n", budget=b)
        self.assertEqual(ctx.exception.recurso, "max_candidates")
        self.assertEqual(snapshot(self.raiz), antes)
        self.assertEqual(len(cand.listar_candidates(self.raiz)), 3)

    def test_idempotente_no_consume_con_budget_agotado(self):
        b = bud.ImprovementBudget(max_candidates=1)
        c1 = self.crear(budget=b)
        c2 = self.crear(budget=b)
        self.assertEqual(c1.candidate_id, c2.candidate_id)


if __name__ == "__main__":
    unittest.main()

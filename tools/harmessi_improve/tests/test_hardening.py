"""Tests de endurecimiento (v0.14 Change 1, correcciones del reviewer)."""
from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from tools.harmessi_improve import budget as bud
from tools.harmessi_improve import candidate as cand
from tools.harmessi_improve.candidate import CandidateCorrupta, CandidateRechazada
from tools.harmessi_improve.tests._helpers import ACTIVO, PROVENANCE, crear_repo, snapshot

NUEVO = "# Skill\nVersión mejorada.\n"
EVID = {"probe_id": "probe-1", "decision_hash": "abc123"}


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.raiz = crear_repo(Path(self._tmp.name))

    def crear(self, **kw):
        args = dict(base_surface=ACTIVO, content=NUEVO, hypothesis="h", provenance=dict(PROVENANCE))
        args.update(kw)
        return cand.crear_candidate(self.raiz, **args)

    def ruta_json(self, c):
        return self.raiz / ".harmessi/improvement/candidates" / c.candidate_id / "candidate.json"


class TestLock(Base):
    def test_concurrencia_no_supera_tope(self):
        p = bud.ImprovementBudget(max_candidates=3)
        exitos, agotados = [], []

        def tarea(i):
            try:
                bud.consumir(self.raiz, "candidates", presupuesto=p)
                exitos.append(i)
            except bud.PresupuestoAgotado:
                agotados.append(i)

        hilos = [threading.Thread(target=tarea, args=(i,)) for i in range(8)]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join()
        self.assertEqual(len(exitos), 3)
        self.assertEqual(bud.estado(self.raiz)["candidates"], 3)
        self.assertFalse((self.raiz / ".harmessi/improvement/.lock").exists())

    def test_lock_ocupado_falla_cerrado(self):
        lock = self.raiz / ".harmessi/improvement/.lock"
        lock.parent.mkdir(parents=True)
        lock.write_bytes(b"")
        with self.assertRaises(bud.PresupuestoAgotado):
            with bud.bloqueo(self.raiz, espera_s=0.05):
                pass
        self.assertTrue(lock.exists())


class TestSimlinks(Base):
    def _symlink(self, destino, enlace):
        try:
            os.symlink(destino, enlace, target_is_directory=destino.is_dir())
        except (OSError, NotImplementedError):
            self.skipTest("no se pueden crear symlinks")

    def test_base_symlink_rechazada(self):
        activo = self.raiz / ACTIVO
        real = self.raiz / "docs/x.md"
        activo.unlink()
        self._symlink(real, activo)
        with self.assertRaises(CandidateRechazada) as ctx:
            self.crear()
        self.assertEqual(ctx.exception.codigo, cand.BASE_ILEGIBLE)

    def test_directorio_intermedio_symlink(self):
        d = self.raiz / ".claude/skills/lead-data-scientist/skills"
        otro = self.raiz / "otro"
        d.rename(otro)
        self._symlink(otro, d)
        with self.assertRaises(CandidateRechazada) as ctx:
            self.crear()
        self.assertEqual(ctx.exception.codigo, cand.BASE_ILEGIBLE)

    def test_improvement_symlink_rechazado(self):
        externo = Path(self._tmp.name + "_ext")
        externo.mkdir()
        self.addCleanup(lambda: __import__("shutil").rmtree(externo, ignore_errors=True))
        (self.raiz / ".harmessi").mkdir()
        self._symlink(externo, self.raiz / ".harmessi" / "improvement")
        with self.assertRaises(Exception):
            self.crear()
        self.assertEqual(list(externo.iterdir()), [])


class TestRevalidacion(Base):
    def editar(self, c, fn):
        ruta = self.ruta_json(c)
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        fn(datos)
        ruta.write_text(json.dumps(datos), encoding="utf-8")

    def test_json_editado_a_mano(self):
        casos = {
            "base_protegida": lambda d: d.update(base_surface="tools/x.py"),
            "base_no_canonica": lambda d: d.update(base_surface="./" + d["base_surface"]),
            "history0": lambda d: d["status_history"][0].update(status="evaluated"),
            "promotable_sin_evidencia": lambda d: (
                d.update(status="evaluated"),
                d["status_history"].append({"status": "evaluated", "utc": "2026-10-23T12:00:00Z"})),
            "transicion_invalida": lambda d: (
                d.update(status="promotable"),
                d["status_history"].append({"status": "promotable", "utc": "2026-10-23T12:00:00Z",
                                            "evidence": EVID})),
            "status_desconocido": lambda d: d.update(status="bogus"),
            "suite_sucia": lambda d: d.update(suite_ids=["a b"]),
        }
        for nombre, fn in casos.items():
            with self.subTest(nombre):
                # repo propio por caso: cada creación consume budget (tope 3)
                self.raiz = crear_repo(Path(tempfile.mkdtemp(dir=self._tmp.name)))
                c = self.crear(content=NUEVO + nombre + "\n")
                self.editar(c, fn)
                with self.assertRaises(CandidateCorrupta):
                    cand.cargar_candidate(self.raiz, c.candidate_id)

    def test_evidencia_estricta(self):
        c = self.crear()
        for ev in ({"probe_id": "a b", "decision_hash": "h"}, {"probe_id": "p", "decision_hash": "no-alnum!"},
                   {"probe_id": "p" * 81, "decision_hash": "h"}, {"probe_id": "p", "decision_hash": "h" * 129}):
            with self.subTest(ev=ev):
                with self.assertRaises(CandidateRechazada) as ctx:
                    cand.transicionar(self.raiz, c.candidate_id, "evaluated", ev)
                self.assertEqual(ctx.exception.codigo, cand.EVIDENCIA_REQUERIDA)

    def test_nuevo_estado_no_str(self):
        c = self.crear()
        with self.assertRaises(CandidateRechazada) as ctx:
            cand.transicionar(self.raiz, c.candidate_id, ["evaluated"], EVID)
        self.assertEqual(ctx.exception.codigo, cand.TRANSICION_INVALIDA)

    def test_id_con_salto_final(self):
        c = self.crear()
        with self.assertRaises(CandidateCorrupta):
            cand.cargar_candidate(self.raiz, c.candidate_id + "\n")


class TestRutas(Base):
    def assertRechazo(self, codigo, ruta):
        with self.assertRaises(CandidateRechazada) as ctx:
            self.crear(base_surface=ruta)
        self.assertEqual(ctx.exception.codigo, codigo)

    def test_variantes_equivalentes_mismo_id(self):
        c1 = self.crear()
        c2 = self.crear(base_surface="./" + ACTIVO.replace("/", "\\"))
        c3 = self.crear(base_surface=ACTIVO.upper().replace("CLAUDE", ".claude").replace("..", "."))
        self.assertEqual(c1.candidate_id, c2.candidate_id)
        self.assertEqual(c1.base_surface, ACTIVO)
        self.assertEqual(bud.estado(self.raiz)["candidates"], 1)
        self.assertIsNotNone(c3)

    def test_mayusculas_protegidas(self):
        self.assertRechazo(cand.SUPERFICIE_PROTEGIDA_COD, ".CLAUDE/agents/a.md")
        self.assertRechazo(cand.SUPERFICIE_PROTEGIDA_COD, ".\\tools\\x.py")

    def test_comodines(self):
        self.assertRechazo(cand.SUPERFICIE_PROTEGIDA_COD, ".claude/skills/lead-data-scientist/skills/?.md")
        self.assertRechazo(cand.SUPERFICIE_PROTEGIDA_COD, ".claude/skills/lead-data-scientist/skills/[a].md")

    def test_nul(self):
        self.assertRechazo(cand.RUTA_INVALIDA, "docs/x\x00.md")

    def test_bajo_improvement(self):
        c = self.crear()
        self.assertRechazo(cand.SUPERFICIE_PROTEGIDA_COD,
                           f".harmessi/improvement/candidates/{c.candidate_id}/content.md")


class TestBudgetExtra(Base):
    def test_budget_version_distinta(self):
        d = self.raiz / ".harmessi/improvement"
        d.mkdir(parents=True)
        (d / "budget.json").write_text(json.dumps({"budget_version": 2}), encoding="utf-8")
        with self.assertRaises(bud.PresupuestoInvalido):
            bud.cargar_presupuesto(self.raiz)

    def test_borrado_del_estado_reinicia_solo_si_ausente(self):
        bud.consumir(self.raiz, "candidates")
        (self.raiz / ".harmessi/improvement/budget_state.json").unlink()
        self.assertEqual(bud.estado(self.raiz)["candidates"], 0)

    def test_crear_usa_budget_json(self):
        d = self.raiz / ".harmessi/improvement"
        d.mkdir(parents=True)
        (d / "budget.json").write_text(json.dumps({"max_candidates": 1}), encoding="utf-8")
        self.crear()
        with self.assertRaises(bud.PresupuestoAgotado):
            self.crear(content=NUEVO + "otra\n")

    def test_fechas_naive_como_utc(self):
        naive = datetime(2026, 10, 23, 12, 0, 0)
        bud.consumir(self.raiz, "candidates", ahora=naive)
        self.assertEqual(bud.estado(self.raiz)["started_utc"], "2026-10-23T12:00:00Z")
        bud.verificar_wall_clock(naive, datetime(2026, 10, 23, 12, 0, 5, tzinfo=timezone.utc), 5)

    def test_rollback_si_falla_escritura(self):
        antes = snapshot(self.raiz)
        with mock.patch.object(cand, "escribir_atomico", side_effect=OSError("disco")):
            with self.assertRaises(OSError):
                self.crear()
        self.assertEqual(bud.estado(self.raiz)["candidates"], 0)
        self.assertEqual(cand.listar_candidates(self.raiz), [])
        despues = snapshot(self.raiz)
        self.assertEqual({k: v for k, v in despues.items() if not k.startswith(".harmessi/")}, antes)

    def test_listar_ignora_huerfanos(self):
        huerfano = self.raiz / ".harmessi/improvement/candidates/cand-0123456789ab"
        huerfano.mkdir(parents=True)
        (huerfano / "content.md").write_text("x", encoding="utf-8")
        self.assertEqual(cand.listar_candidates(self.raiz), [])


class TestRegistro(unittest.TestCase):
    def test_solo_checkout_en_ambas_listas(self):
        raiz = Path(__file__).resolve().parents[3]
        for rel in ("tools/ds_init/check_manifest_parity.py", "tools/ds_init/tests/test_manifest_completitud.py"):
            texto = (raiz / rel).read_text(encoding="utf-8")
            self.assertIn('"tools/harmessi_improve/"', texto, rel)


if __name__ == "__main__":
    unittest.main()

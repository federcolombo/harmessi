"""Tests de presupuestos de mejora (v0.14 Change 1, R10-R12). Todo sintético."""
from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tools.harmessi_improve import budget as bud
from tools.harmessi_improve.budget import (
    ImprovementBudget, PresupuestoAgotado, PresupuestoInvalido,
)

T0 = datetime(2026, 10, 23, 12, 0, 0, tzinfo=timezone.utc)


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.raiz = Path(self._tmp.name)

    def escribir(self, nombre, texto):
        ruta = self.raiz / ".harmessi" / "improvement" / nombre
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(texto, encoding="utf-8")
        return ruta


class TestConfiguracion(Base):
    def test_constantes(self):
        self.assertEqual(bud.BUDGET_VERSION, 1)
        self.assertEqual(bud.DEFAULTS, {
            "max_candidates": 3, "max_probe_cycles": 2, "max_runs_per_candidate": 6,
            "max_retries": 1, "max_wall_clock_s": 1800})
        self.assertEqual(bud.HARD_CEILING, {
            "max_candidates": 10, "max_probe_cycles": 5, "max_runs_per_candidate": 20,
            "max_retries": 3, "max_wall_clock_s": 7200})

    def test_defaults_sin_archivo(self):
        p = bud.cargar_presupuesto(self.raiz)
        self.assertEqual(p, ImprovementBudget())
        self.assertEqual(p.max_candidates, 3)

    def test_techos_validos(self):
        ImprovementBudget(**bud.HARD_CEILING).validar()

    def test_invalidos(self):
        for clave in bud.CLAVES_PRESUPUESTO:
            techo = bud.HARD_CEILING[clave]
            for valor in (True, False, 0, -1, "3", 1.5, None, techo + 1):
                with self.subTest(clave=clave, valor=valor):
                    with self.assertRaises(PresupuestoInvalido):
                        ImprovementBudget(**{clave: valor}).validar()

    def test_archivo_valido_parcial(self):
        self.escribir("budget.json", json.dumps({"max_candidates": 5}))
        p = bud.cargar_presupuesto(self.raiz)
        self.assertEqual(p.max_candidates, 5)
        self.assertEqual(p.max_retries, 1)

    def test_archivo_invalido_no_clampea(self):
        casos = [
            json.dumps({"max_candidates": 11}),
            json.dumps({"max_candidates": True}),
            json.dumps({"max_candidates": "3"}),
            json.dumps({"max_candidates": 0}),
            json.dumps({"desconocida": 1}),
            json.dumps([1, 2]),
            "{no json",
        ]
        for texto in casos:
            with self.subTest(texto=texto):
                self.escribir("budget.json", texto)
                with self.assertRaises(PresupuestoInvalido):
                    bud.cargar_presupuesto(self.raiz)


class TestConsumo(Base):
    def test_agotamiento_determinista_candidates(self):
        p = ImprovementBudget(max_candidates=3)
        for i in range(3):
            self.assertEqual(bud.consumir(self.raiz, "candidates", presupuesto=p, ahora=T0)["candidates"], i + 1)
        with self.assertRaises(PresupuestoAgotado) as ctx:
            bud.consumir(self.raiz, "candidates", presupuesto=p, ahora=T0)
        self.assertEqual(ctx.exception.recurso, "max_candidates")
        self.assertEqual(ctx.exception.limite, 3)
        self.assertEqual(bud.estado(self.raiz)["candidates"], 3)

    def test_verifica_antes_de_incrementar(self):
        p = ImprovementBudget(max_probe_cycles=2)
        with self.assertRaises(PresupuestoAgotado):
            bud.consumir(self.raiz, "probe_cycles", n=3, presupuesto=p, ahora=T0)
        self.assertEqual(bud.estado(self.raiz)["probe_cycles"], 0)

    def test_runs_y_retries_por_candidate(self):
        p = ImprovementBudget(max_runs_per_candidate=2, max_retries=1)
        bud.consumir(self.raiz, "runs", "cand-aaaaaaaaaaaa", n=2, presupuesto=p, ahora=T0)
        with self.assertRaises(PresupuestoAgotado):
            bud.consumir(self.raiz, "runs", "cand-aaaaaaaaaaaa", presupuesto=p, ahora=T0)
        # otra candidate tiene su propio contador
        bud.consumir(self.raiz, "runs", "cand-bbbbbbbbbbbb", presupuesto=p, ahora=T0)
        bud.consumir(self.raiz, "retries", "cand-aaaaaaaaaaaa", presupuesto=p, ahora=T0)
        with self.assertRaises(PresupuestoAgotado):
            bud.consumir(self.raiz, "retries", "cand-aaaaaaaaaaaa", presupuesto=p, ahora=T0)
        est = bud.estado(self.raiz)
        self.assertEqual(est["runs_by_candidate"], {"cand-aaaaaaaaaaaa": 2, "cand-bbbbbbbbbbbb": 1})
        self.assertEqual(est["retries_by_candidate"], {"cand-aaaaaaaaaaaa": 1})

    def test_argumentos_invalidos(self):
        for args, kw in [
            (("bogus",), {}),
            (("runs",), {}),
            (("retries",), {"candidate_id": ""}),
            (("candidates",), {"n": 0}),
            (("candidates",), {"n": True}),
            (("candidates",), {"n": "1"}),
        ]:
            with self.subTest(args=args, kw=kw):
                with self.assertRaises(PresupuestoInvalido):
                    bud.consumir(self.raiz, *args, ahora=T0, **kw)

    def test_persistencia_entre_cargas(self):
        bud.consumir(self.raiz, "candidates", ahora=T0)
        bud.consumir(self.raiz, "probe_cycles", ahora=T0)
        est = bud.estado(self.raiz)
        self.assertEqual((est["candidates"], est["probe_cycles"]), (1, 1))
        self.assertEqual(est["started_utc"], "2026-10-23T12:00:00Z")
        self.assertEqual(est["budget_version"], 1)
        bud.consumir(self.raiz, "candidates", ahora=T0 + timedelta(seconds=5))
        self.assertEqual(bud.estado(self.raiz)["candidates"], 2)
        self.assertEqual(bud.estado(self.raiz)["started_utc"], "2026-10-23T12:00:00Z")

    def test_estado_sin_archivo_no_escribe(self):
        self.assertEqual(bud.estado(self.raiz)["candidates"], 0)
        self.assertFalse((self.raiz / ".harmessi").exists())

    def test_estado_corrupto_fail_closed(self):
        bud.consumir(self.raiz, "candidates", ahora=T0)
        ruta = self.raiz / ".harmessi/improvement/budget_state.json"
        casos = ["{no json", "[]", json.dumps({"candidates": 0}),
                 json.dumps({**json.loads(ruta.read_text(encoding="utf-8")), "candidates": -1}),
                 json.dumps({**json.loads(ruta.read_text(encoding="utf-8")), "candidates": True}),
                 json.dumps({**json.loads(ruta.read_text(encoding="utf-8")), "started_utc": "ayer"})]
        for texto in casos:
            with self.subTest(texto=texto[:40]):
                ruta.write_text(texto, encoding="utf-8")
                with self.assertRaises(PresupuestoInvalido):
                    bud.consumir(self.raiz, "candidates", ahora=T0)
                with self.assertRaises(PresupuestoInvalido):
                    bud.estado(self.raiz)
                self.assertEqual(ruta.read_text(encoding="utf-8"), texto, "no debe reiniciarse")

    def test_sin_archivos_temporales(self):
        bud.consumir(self.raiz, "candidates", ahora=T0)
        nombres = [p.name for p in (self.raiz / ".harmessi/improvement").iterdir()]
        self.assertEqual(nombres, ["budget_state.json"])


class TestWallClock(Base):
    def test_pura(self):
        bud.verificar_wall_clock(T0, T0 + timedelta(seconds=10), 10)
        bud.verificar_wall_clock("2026-10-23T12:00:00Z", T0 + timedelta(seconds=10), 10)
        with self.assertRaises(PresupuestoAgotado) as ctx:
            bud.verificar_wall_clock(T0, T0 + timedelta(seconds=11), 10)
        self.assertEqual(ctx.exception.recurso, "max_wall_clock_s")

    def test_invalido(self):
        with self.assertRaises(PresupuestoInvalido):
            bud.verificar_wall_clock("ayer", T0, 10)

    def test_consumir_respeta_wall_clock(self):
        p = ImprovementBudget(max_wall_clock_s=60)
        bud.consumir(self.raiz, "candidates", presupuesto=p, ahora=T0)
        with self.assertRaises(PresupuestoAgotado):
            bud.consumir(self.raiz, "candidates", presupuesto=p, ahora=T0 + timedelta(seconds=61))
        self.assertEqual(bud.estado(self.raiz)["candidates"], 1)


if __name__ == "__main__":
    unittest.main()

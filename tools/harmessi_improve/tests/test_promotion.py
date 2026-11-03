"""Tests de promoción gobernada (v0.14 Change 4, R1-R7). Probes reales con FakeAdapter en tempdirs."""
from __future__ import annotations

import json
import os
import shutil
import unittest
from unittest import mock

from tools.harmessi_bench.redact import redactar_texto
from tools.harmessi_improve import promotion as pm
from tools.harmessi_improve.decision import PromocionNoRespaldada
from tools.harmessi_improve.promotion import PromocionBloqueada, PropuestaInvalida
from tools.harmessi_improve.tests import test_decision as td
from tools.harmessi_improve.tests._fakes import MARCA_BASE, MARCA_CAND, FakeAdapter
from tools.harmessi_improve.tests._helpers import ACTIVO, CHANGE_ID, crear_change, snapshot
from tools.harmessi_improve.tests.test_probe import SOLO_1, TODOS


class BasePromo(td.BaseDecision):
    def setUp(self):
        super().setUp()
        self.promover()
        self.cid = self.c.candidate_id
        self.prop = pm.proponer_promocion(self.raiz, self.cid)

    def change(self, **kw):
        return crear_change(self.raiz, kw.pop("proposal_hash", self.prop["proposal_hash"]), **kw)

    def gate(self):
        return pm.evaluar_gate(self.raiz, self.cid, CHANGE_ID)

    def ruta_prop(self, nombre="proposal.json"):
        return self.raiz / ".harmessi" / "improvement" / "proposals" / self.cid / nombre

    def editar_prop(self, rehash=True, **cambios):
        datos = json.loads(self.ruta_prop().read_text("utf-8"))
        datos.update(cambios)
        if rehash:
            datos["proposal_hash"] = pm._hash_propuesta(datos)
        self.ruta_prop().write_text(json.dumps(datos), encoding="utf-8")

    def cambiar_activo(self):
        (self.raiz / ACTIVO).write_bytes(b"# Skill\nOtra base.\n")


class TestPropuesta(BasePromo):
    def test_campos(self):
        p = self.prop
        self.assertEqual(p["proposal_id"], self.cid)
        self.assertEqual(p["candidate_id"], self.cid)
        self.assertEqual(p["base_surface"], ACTIVO)
        self.assertEqual(p["content_hash"], self.c.content_hash)
        self.assertEqual(p["probe_id"], "p1")
        self.assertEqual(p["verdict"], "candidate_better")
        self.assertEqual(p["governance"]["requires"], "console_confirmed")
        self.assertTrue(p["governance"]["distributed"])
        self.assertTrue(p["governance"]["release_verification_required"])
        self.assertEqual(p["proposal_hash"], pm._hash_propuesta(p))
        self.assertEqual(pm.cargar_propuesta(self.raiz, self.cid), p)
        self.assertIn("p1", p["ledger_text"])
        self.assertIn(p["decision_hash"], p["ledger_text"])

    def test_escribe_solo_proposals(self):
        antes = snapshot(self.raiz)
        pm.proponer_promocion(self.raiz, self.cid)
        despues = snapshot(self.raiz)
        self.assertEqual(antes, despues)  # idempotente
        nuevos = {k for k in despues if k.startswith(".harmessi/improvement/proposals/")}
        self.assertEqual(len(nuevos), 2)

    def test_diff(self):
        texto = self.ruta_prop("change.diff").read_text("utf-8")
        self.assertIn(f"--- a/{ACTIVO}", texto)
        self.assertIn(f"+++ b/{ACTIVO}", texto)
        self.assertIn(f"-{MARCA_BASE}", texto)
        self.assertIn(f"+{MARCA_CAND}", texto)

    def test_privacidad(self):
        texto = self.ruta_prop().read_text("utf-8")
        self.assertEqual(redactar_texto(self.prop["ledger_text"]), self.prop["ledger_text"])
        self.assertEqual(redactar_texto(self.ruta_prop("change.diff").read_text("utf-8")),
                         self.ruta_prop("change.diff").read_text("utf-8"))
        self.assertNotIn(str(self.raiz), texto)
        self.assertNotIn(self.raiz.as_posix(), texto)

    def test_rechaza_no_promotable(self):
        self.nueva = self.nueva_candidate("# Skill\nOtra variante.\n")
        with self.assertRaises(PromocionNoRespaldada):
            pm.proponer_promocion(self.raiz, self.nueva.candidate_id)

    def test_rechaza_metadata_editada(self):
        otra = self.nueva_candidate("# Skill\nOtra variante.\n")
        self.forzar_promotable(otra.candidate_id, "p1", "abc123")
        with self.assertRaises(PromocionNoRespaldada):
            pm.proponer_promocion(self.raiz, otra.candidate_id)

    def test_rechaza_base_cambiada(self):
        self.cambiar_activo()
        with self.assertRaises((PromocionNoRespaldada, PromocionBloqueada)):
            pm.proponer_promocion(self.raiz, self.cid)

    def test_diff_sensible_se_rechaza(self):
        with mock.patch.object(pm, "redactar_texto", lambda t: t + "x"):
            with self.assertRaises(PromocionBloqueada) as ctx:
                pm.proponer_promocion(self.raiz, self.cid)
        self.assertEqual(ctx.exception.motivos, [pm.DIFF_SENSIBLE])

    def test_diff_fiel_newline_final_y_eol(self):
        d = pm._diff("x.md", "a\nb\n", "a\nb")
        self.assertIn("-b\n", d)
        self.assertIn("+b\n\\ No newline at end of file\n", d)
        d2 = pm._diff("x.md", "a\r\n", "a\n")
        self.assertIn("-a\r\n", d2)
        self.assertIn("+a\n", d2)
        with self.assertRaises(PromocionBloqueada):
            pm._diff("x.md", "a\n", "a\n")

    def test_cargar_detecta_manipulacion(self):
        self.editar_prop(rehash=False, verdict="x")
        with self.assertRaises(PropuestaInvalida):
            pm.cargar_propuesta(self.raiz, self.cid)

    def test_cargar_detecta_diff_manipulado(self):
        with open(self.ruta_prop("change.diff"), "a", encoding="utf-8") as f:
            f.write("+extra\n")
        with self.assertRaises(PropuestaInvalida):
            pm.cargar_propuesta(self.raiz, self.cid)
        self.assertEqual(self.gate(), [pm.PROPUESTA_INVALIDA])


class TestGate(BasePromo):
    def test_pasa_con_t1_completo(self):
        self.change()
        self.assertEqual(self.gate(), [])

    def test_t0_declared_no_alcanza(self):
        self.change(canal="declared")
        self.assertEqual(self.gate(), ["APROBACION_PROPOSAL_NO_T1", "APROBACION_SPEC_NO_T1",
                                       "APROBACION_DESIGN_NO_T1"])

    def test_una_sola_aprobacion_falta(self):
        self.change(aprobar=("proposal.md", "spec.md"))
        self.assertEqual(self.gate(), ["APROBACION_DESIGN_NO_VERIFICADA"])

    def test_artefacto_cambiado_tras_aprobar(self):
        d = self.change()
        with open(d / "spec.md", "a", encoding="utf-8") as f:
            f.write("cambio\n")
        self.assertEqual(self.gate(), ["APROBACION_SPEC_NO_VERIFICADA"])

    def test_change_inexistente(self):
        self.assertEqual(self.gate(), [pm.CHANGE_INEXISTENTE])

    def test_change_no_en_implementacion(self):
        self.change(estado="aprobada_implementacion")
        self.assertEqual(self.gate(), [pm.CHANGE_NO_EN_IMPLEMENTACION])

    def test_fuera_de_scope(self):
        self.change(alcance=("docs/**",))
        self.assertEqual(self.gate(), [pm.FUERA_DE_ALCANCE])

    def test_propuesta_no_citada(self):
        self.change(citar=False)
        self.assertEqual(self.gate(), [pm.PROPUESTA_NO_CITADA])

    def test_base_cambiada(self):
        self.change()
        self.cambiar_activo()
        self.assertEqual(self.gate(), [pm.BASE_CAMBIADA])

    def test_t1_exige_channel_version(self):
        self.change(channel_version=None)
        self.assertEqual(self.gate(), ["APROBACION_PROPOSAL_NO_T1", "APROBACION_SPEC_NO_T1",
                                       "APROBACION_DESIGN_NO_T1"])

    def test_t1_version_distinta(self):
        self.change(channel_version="console/v0")
        self.assertEqual(len(self.gate()), 3)
        self.assertTrue(all(m.endswith("_NO_T1") for m in self.gate()))

    def test_stale_por_entrada_mas_reciente(self):
        d = self.change()
        ruta = d / "control.json"
        control = json.loads(ruta.read_text("utf-8"))
        vieja = next(a for a in control["aprobaciones"] if a["artefacto"] == "spec.md")
        control["aprobaciones"].append(dict(vieja, hash="1" * 64, registrado_utc="2026-10-23T13:00:00Z"))
        ruta.write_text(json.dumps(control), encoding="utf-8")
        self.assertEqual(self.gate(), ["APROBACION_SPEC_NO_VERIFICADA"])

    def test_change_solo_en_archive(self):
        d = self.change()
        destino = self.raiz / "openspec" / "archive"
        destino.mkdir(parents=True)
        shutil.move(str(d), str(destino / CHANGE_ID))
        self.assertEqual(self.gate(), [pm.CHANGE_INEXISTENTE])

    def test_control_ilegible(self):
        d = self.change()
        (d / "control.json").write_text("{no es json", encoding="utf-8")
        self.assertEqual(self.gate(), [pm.CONTROL_ILEGIBLE])

    def test_control_de_otro_change(self):
        self.change(control_change_id="20261023-otro")
        self.assertEqual(self.gate(), [pm.CONTROL_ILEGIBLE])

    def test_change_id_con_traversal(self):
        self.assertEqual(pm.evaluar_gate(self.raiz, self.cid, "../x"), [pm.CHANGE_INEXISTENTE])

    def test_cita_en_comentario_html_no_vale(self):
        self.change(texto_cita="<!-- proposal_hash: {h} -->\n")
        self.assertEqual(self.gate(), [pm.PROPUESTA_NO_CITADA])

    def test_cita_inline_sin_ancla_no_vale(self):
        self.change(texto_cita="Ver {h} en el diff.\n")
        self.assertEqual(self.gate(), [pm.PROPUESTA_NO_CITADA])

    def test_superficie_no_optimizable_editada_a_mano(self):
        self.change()
        for ruta in ("tools/x.py", ".claude/agents/a.md"):
            with self.subTest(exacto=ruta):
                self.editar_prop(base_surface=ruta)
                self.assertEqual(self.gate(), [pm.SUPERFICIE_NO_OPTIMIZABLE])
        for ruta in ("tools/x.py", ".claude/agents/a.md", "docs/x.md"):
            with self.subTest(ruta=ruta):
                self.editar_prop(base_surface=ruta)
                self.assertTrue(self.gate())
                with self.assertRaises(PromocionBloqueada):
                    pm.aplicar_promocion(self.raiz, self.cid, CHANGE_ID)

    def test_gate_no_lanza(self):
        self.assertTrue(pm.evaluar_gate(self.raiz, "no-es-id", "no-es-change"))
        self.assertTrue(pm.evaluar_gate(None, None, None))


class TestAplicar(BasePromo):
    def test_sin_gate_no_escribe(self):
        antes = snapshot(self.raiz)
        with self.assertRaises(PromocionBloqueada):
            pm.aplicar_promocion(self.raiz, self.cid, CHANGE_ID)
        self.assertEqual(antes, snapshot(self.raiz))
        self.change(canal="declared")
        antes = snapshot(self.raiz)
        with self.assertRaises(PromocionBloqueada) as ctx:
            pm.aplicar_promocion(self.raiz, self.cid, CHANGE_ID)
        self.assertIn("APROBACION_SPEC_NO_T1", ctx.exception.motivos)
        self.assertEqual(antes, snapshot(self.raiz))

    def test_con_gate_escribe_solo_superficie_y_applied(self):
        self.change()
        antes = snapshot(self.raiz)
        res = pm.aplicar_promocion(self.raiz, self.cid, CHANGE_ID)
        despues = snapshot(self.raiz)
        cambiados = {k for k in set(antes) | set(despues) if antes.get(k) != despues.get(k)}
        self.assertEqual(cambiados, {ACTIVO, f".harmessi/improvement/proposals/{self.cid}/applied.json"})
        self.assertIn(MARCA_CAND, despues[ACTIVO].decode("utf-8"))
        self.assertFalse(res["already_applied"])
        applied = json.loads(self.ruta_prop("applied.json").read_text("utf-8"))
        self.assertEqual(applied["change_id"], CHANGE_ID)
        self.assertEqual(applied["content_hash"], self.c.content_hash)
        self.assertIn("applied_utc", applied)

    def test_idempotente(self):
        self.change()
        pm.aplicar_promocion(self.raiz, self.cid, CHANGE_ID)
        antes = snapshot(self.raiz)
        res = pm.aplicar_promocion(self.raiz, self.cid, CHANGE_ID)
        self.assertTrue(res["already_applied"])
        self.assertEqual(antes, snapshot(self.raiz))

    def _fallar_al_marcar_applied(self):
        real = pm.escribir_atomico

        def falso(ruta, datos):
            if ruta.name == "applied.json" and b'"state": "applied"' in datos:
                raise OSError("fallo simulado")
            return real(ruta, datos)
        return mock.patch.object(pm, "escribir_atomico", falso)

    def test_fallo_entre_escrituras_deja_pending_y_se_recupera(self):
        self.change()
        with self._fallar_al_marcar_applied():
            with self.assertRaises(OSError):
                pm.aplicar_promocion(self.raiz, self.cid, CHANGE_ID)
        self.assertIn(MARCA_CAND, (self.raiz / ACTIVO).read_text("utf-8"))
        reg = json.loads(self.ruta_prop("applied.json").read_text("utf-8"))
        self.assertEqual(reg["state"], "pending")
        for k in ("change_id", "proposal_hash", "decision_hash", "base_hash", "content_hash", "probe_id"):
            self.assertIn(k, reg)
        # recuperación idempotente (la base ya cambió: el gate solo no pasaría)
        res = pm.aplicar_promocion(self.raiz, self.cid, CHANGE_ID)
        self.assertFalse(res["already_applied"])
        self.assertEqual(json.loads(self.ruta_prop("applied.json").read_text("utf-8"))["state"], "applied")
        antes = snapshot(self.raiz)
        self.assertTrue(pm.aplicar_promocion(self.raiz, self.cid, CHANGE_ID)["already_applied"])
        self.assertEqual(antes, snapshot(self.raiz))

    def test_recuperacion_exige_mismo_change_id(self):
        self.change()
        with self._fallar_al_marcar_applied():
            with self.assertRaises(OSError):
                pm.aplicar_promocion(self.raiz, self.cid, CHANGE_ID)
        with self.assertRaises(PromocionBloqueada):
            pm.aplicar_promocion(self.raiz, self.cid, "20261023-otro-change")

    def test_fallo_al_escribir_superficie_restaura_base(self):
        self.change()
        real = pm.escribir_atomico
        base = (self.raiz / ACTIVO).read_bytes()

        def falso(ruta, datos):
            if ruta.name == "diagnosing-bugs.md":
                raise OSError("fallo simulado")
            return real(ruta, datos)
        with mock.patch.object(pm, "escribir_atomico", falso):
            with self.assertRaises(OSError):
                pm.aplicar_promocion(self.raiz, self.cid, CHANGE_ID)
        self.assertEqual((self.raiz / ACTIVO).read_bytes(), base)

    def test_symlink_en_superficie_bloqueado(self):
        self.change()
        destino = self.raiz / "docs" / "x.md"
        activo = self.raiz / ACTIVO
        activo.unlink()
        try:
            os.symlink(destino, activo)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks no disponibles")
        antes = destino.read_bytes()
        with self.assertRaises(PromocionBloqueada):
            pm.aplicar_promocion(self.raiz, self.cid, CHANGE_ID)
        self.assertEqual(destino.read_bytes(), antes)


if __name__ == "__main__":
    unittest.main()

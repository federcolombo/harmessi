"""Tests v0.15 de endurecimiento de evidencia (B-21): cadena de hashes candidate -> probe -> decide ->
propose -> apply. Cada manipulación posterior al probe debe ser rechazada con el código/excepción real.
Probes reales con FakeAdapter en tempdirs; sin mocks de lo que ya tiene objeto real."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.harmessi_improve import lessons as les
from tools.harmessi_improve.lessons import LessonRechazada
from tools.harmessi_improve.tests._helpers import crear_repo
from tools.harmessi_improve.tests.test_lessons import CTX, BaseLessons
from tools.harmessi_improve import candidate as cand
from tools.harmessi_improve import decision as dec
from tools.harmessi_improve import promotion as pm
from tools.harmessi_improve.decision import EvidenciaInvalida, PromocionNoRespaldada
from tools.harmessi_improve.policy import ProbePolicy, hash_policy
from tools.harmessi_improve.probe import ProbeRechazado
from tools.harmessi_improve.promotion import PromocionBloqueada
from tools.harmessi_improve.tests import test_decision as td
from tools.harmessi_improve.tests._fakes import FakeAdapter
from tools.harmessi_improve.tests._helpers import ACTIVO, CHANGE_ID
from tools.harmessi_improve.tests.test_probe import SOLO_1, TODOS
from tools.harmessi_improve.tests.test_promotion import BasePromo


class BaseProbeCompleto(td.BaseDecision):
    """Candidate + probe completed (sin decidir todavía)."""

    def setUp(self):
        super().setUp()
        self.probe(FakeAdapter(SOLO_1, TODOS))

    def ruta_probe_json(self):
        return self.raiz / ".harmessi" / "improvement" / "probes" / "p1" / "probe.json"


class TestManipulacionAntesDeDecidir(BaseProbeCompleto):
    def test_a_content_md_editado_tras_el_probe(self):
        ruta = self.raiz / ".harmessi" / "improvement" / "candidates" / self.c.candidate_id / "content.md"
        ruta.write_text("# Otro contenido\n", encoding="utf-8")
        with self.assertRaises(EvidenciaInvalida):
            dec.decidir(self.raiz, "p1")
        with self.assertRaises(EvidenciaInvalida):
            dec.aplicar_decision(self.raiz, "p1")

    def test_b_base_obsoleta_rechaza_nuevo_probe_y_promocion(self):
        # La base activa cambia tras el probe: no se puede promover la candidate.
        (self.raiz / ACTIVO).write_bytes(b"# Cambio externo\n")
        with self.assertRaises(EvidenciaInvalida):
            dec.aplicar_decision(self.raiz, "p1")
        self.assertEqual(cand.cargar_candidate(self.raiz, self.c.candidate_id).status, "proposed")

    def test_c_policy_alterada_en_probe_json(self):
        datos = json.loads(self.ruta_probe_json().read_text("utf-8"))
        datos["policy"]["tie_policy"] = "inconclusive"
        self.ruta_probe_json().write_text(json.dumps(datos), encoding="utf-8")
        with self.assertRaises(EvidenciaInvalida):
            dec.decidir(self.raiz, "p1")

    def test_d_result_json_alterado(self):
        ruta = self.evals / "p1-cand-r1" / "result.json"
        ruta.write_bytes(ruta.read_bytes() + b"\n ")
        with self.assertRaises(EvidenciaInvalida):
            dec.decidir(self.raiz, "p1")

    def test_accepted_limitation_probe_json_rehasheado_consistente(self):
        """ACCEPTED LIMITATION (procedencia no criptográfica, D5): si quien edita probe.json recalcula
        `policy_hash` de forma consistente, la cadena no lo detecta por sí sola (no hay firma). La
        decisión se computa con la política editada y refleja ese cambio en `decision.policy`."""
        datos = json.loads(self.ruta_probe_json().read_text("utf-8"))
        datos["policy"]["tie_policy"] = "inconclusive"
        datos["policy_hash"] = hash_policy(ProbePolicy.desde_dict(datos["policy"]))
        self.ruta_probe_json().write_text(json.dumps(datos), encoding="utf-8")
        d = dec.decidir(self.raiz, "p1")  # no lanza: hueco conocido
        self.assertEqual(d["policy"]["tie_policy"], "inconclusive")
        self.assertEqual(d["policy_hash"], datos["policy_hash"])


class TestProbeNuevoConBaseObsoleta(td.BaseDecision):
    def test_b_base_cambiada_antes_de_probar_es_base_obsoleta(self):
        (self.raiz / ACTIVO).write_bytes(b"# Cambio externo\n")
        with self.assertRaises(ProbeRechazado) as ctx:
            self.probe(FakeAdapter(TODOS, TODOS))
        self.assertEqual(ctx.exception.codigo, "BASE_OBSOLETA")


class TestManipulacionTrasPropuesta(BasePromo):
    """Flujo completo candidate -> probe -> decide -> propose; luego se manipula la evidencia."""

    def assertApplyBloqueado(self, motivo):
        self.change()
        self.assertEqual(self.gate(), [motivo])
        with self.assertRaises(PromocionBloqueada) as ctx:
            pm.aplicar_promocion(self.raiz, self.cid, CHANGE_ID)
        self.assertEqual(ctx.exception.motivos, [motivo])

    def test_flujo_intacto_pasa(self):
        self.change()
        self.assertEqual(self.gate(), [])

    def test_a_content_md_editado_rechazado_en_toda_la_cadena(self):
        ruta = self.raiz / ".harmessi" / "improvement" / "candidates" / self.cid / "content.md"
        ruta.write_text("# Otro contenido\n", encoding="utf-8")
        with self.assertRaises(PromocionNoRespaldada):
            dec.verificar_promotable(self.raiz, self.cid)
        with self.assertRaises(PromocionNoRespaldada):
            pm.proponer_promocion(self.raiz, self.cid)
        self.assertApplyBloqueado(pm.NO_PROMOTABLE)

    def test_b_base_alterada_tras_promover(self):
        self.cambiar_activo()
        with self.assertRaises((PromocionNoRespaldada, PromocionBloqueada)):
            pm.proponer_promocion(self.raiz, self.cid)
        self.assertApplyBloqueado(pm.BASE_CAMBIADA)

    def test_c_policy_alterada_en_probe_json(self):
        ruta = self.raiz / ".harmessi" / "improvement" / "probes" / "p1" / "probe.json"
        datos = json.loads(ruta.read_text("utf-8"))
        datos["policy"]["tie_policy"] = "inconclusive"
        ruta.write_text(json.dumps(datos), encoding="utf-8")
        with self.assertRaises(PromocionNoRespaldada):
            dec.verificar_promotable(self.raiz, self.cid)
        self.assertApplyBloqueado(pm.NO_PROMOTABLE)

    def test_d_result_json_alterado(self):
        ruta = self.evals / "p1-cand-r1" / "result.json"
        ruta.write_bytes(ruta.read_bytes() + b"\n ")
        with self.assertRaises(PromocionNoRespaldada):
            dec.verificar_promotable(self.raiz, self.cid)
        self.assertApplyBloqueado(pm.NO_PROMOTABLE)

    def test_e_decision_json_editado(self):
        self.editar_decision(rehash=False, reason="otro motivo")
        with self.assertRaises(EvidenciaInvalida):
            dec.cargar_decision(self.raiz, "p1")
        with self.assertRaises(PromocionNoRespaldada):
            dec.verificar_promotable(self.raiz, self.cid)
        self.assertApplyBloqueado(pm.NO_PROMOTABLE)

    def test_e_decision_json_rehasheado_difiere_de_la_recomputada(self):
        self.editar_decision(rehash=True, reason="otro motivo")
        with self.assertRaises(PromocionNoRespaldada):
            dec.verificar_promotable(self.raiz, self.cid)
        self.assertApplyBloqueado(pm.NO_PROMOTABLE)

    def test_f_proposal_json_editado_sin_rehash(self):
        self.editar_prop(rehash=False, verdict="x")
        with self.assertRaises(pm.PropuestaInvalida):
            pm.cargar_propuesta(self.raiz, self.cid)
        self.assertApplyBloqueado(pm.PROPUESTA_INVALIDA)

    def test_f_proposal_json_editado_con_rehash_difiere_de_la_recomputada(self):
        self.editar_prop(rehash=True, verdict="x")
        self.assertEqual(pm.cargar_propuesta(self.raiz, self.cid)["verdict"], "x")  # hash interno consistente
        self.assertApplyBloqueado(pm.PROPUESTA_INVALIDA)  # el gate la recomputa y no coincide


CONTEXTO_ENMIENDA = {"approval_channel": "console_confirmed", "confirmed_at": "2026-10-23T12:30:00Z",
                     "channel_version": "console/v1"}


class TestGateScopeConEnmiendas(BasePromo):
    """B-22: el gate usa el scope efectivo (`alcance_efectivo`: aprobado + cadena de enmiendas)."""

    def enmendar(self, add):
        from tools.dsguard import scope_amendments as sa
        change_dir = self.raiz / "openspec" / "changes" / CHANGE_ID
        control = json.loads((change_dir / "control.json").read_text("utf-8"))
        plan = sa.planificar_enmienda(sa.estado_alcance(change_dir, control), add, [], [], lambda r: (r, None))
        self.assertEqual(plan.errores, ())
        sa.aplicar_enmienda(change_dir, plan, motivo="ampliar alcance en test", usuario="tester",
                            fecha="2026-10-23", campos_t1=dict(CONTEXTO_ENMIENDA),
                            esperado_hash_antes=plan.hash_antes, utc="2026-10-23T12:30:00Z")

    def test_ruta_fuera_de_scope_luego_permitida_por_enmienda(self):
        self.change(alcance=("docs/**",))
        self.assertEqual(self.gate(), [pm.FUERA_DE_ALCANCE])
        self.enmendar([ACTIVO])
        self.assertEqual(self.gate(), [])

    def test_enmienda_que_no_incluye_la_ruta_sigue_fuera(self):
        self.change(alcance=("docs/**",))
        self.enmendar(["docs/otro.md"])
        self.assertEqual(self.gate(), [pm.FUERA_DE_ALCANCE])

    def test_aplicar_respeta_enmienda(self):
        self.change(alcance=("docs/**",))
        with self.assertRaises(PromocionBloqueada) as ctx:
            pm.aplicar_promocion(self.raiz, self.cid, CHANGE_ID)
        self.assertEqual(ctx.exception.motivos, [pm.FUERA_DE_ALCANCE])
        self.enmendar([ACTIVO])
        res = pm.aplicar_promocion(self.raiz, self.cid, CHANGE_ID)
        self.assertFalse(res["already_applied"])


class TestLedgerEsSoloTextoSugerido(BasePromo):
    """B-22: `ledger_text` es texto sugerido; propose/aplicar nunca escriben el Decision Ledger."""

    def ruta_ledger(self):
        return self.raiz / "openspec" / "decisions" / "ledger.jsonl"

    def test_propose_y_aplicar_no_crean_ledger(self):
        self.assertIsInstance(self.prop["ledger_text"], str)
        self.assertFalse(self.ruta_ledger().exists())
        self.change()
        pm.aplicar_promocion(self.raiz, self.cid, CHANGE_ID)
        self.assertFalse(self.ruta_ledger().exists())
        from tools.harmessi_improve.tests._helpers import snapshot
        self.assertEqual([k for k in snapshot(self.raiz) if k.startswith("openspec/decisions")], [])

    def test_ledger_preexistente_no_se_modifica(self):
        self.ruta_ledger().parent.mkdir(parents=True)
        contenido = b'{"linea": "previa"}\n'
        self.ruta_ledger().write_bytes(contenido)
        pm.proponer_promocion(self.raiz, self.cid)
        self.change()
        pm.aplicar_promocion(self.raiz, self.cid, CHANGE_ID)
        self.assertEqual(self.ruta_ledger().read_bytes(), contenido)


class TestLessonsDegradacionYEnlaces(BaseLessons):
    def lesson(self):
        return self.crear(self.evidencia(2))

    def test_a_glossary_ausente_no_degrada(self):
        """Comportamiento real: sin GLOSSARY la lista de términos es vacía y la lesson aplica."""
        l = self.lesson()
        r = les.lessons_aplicables(self.raiz, CTX)
        self.assertEqual([x["lesson_id"] for x in r["aplicables"]], [l["lesson_id"]])
        self.assertEqual(r["descartadas"], [])

    def test_a_glossary_ilegible_degrada_a_privacidad_no_superada(self):
        l = self.lesson()
        (self.raiz / "GLOSSARY.md").write_bytes(b"\xff\xfe\x80\x81 no utf-8")
        r = les.lessons_aplicables(self.raiz, CTX)
        self.assertEqual(r["aplicables"], [])
        self.assertEqual(r["descartadas"], [{"lesson_id": l["lesson_id"], "motivo": "privacidad_no_superada"}])

    def test_b_lesson_symlink_rechazada(self):
        l = self.lesson()
        ruta = self.ruta(l["lesson_id"])
        destino = self.raiz / "docs" / "copia-lesson.json"
        destino.write_bytes(ruta.read_bytes())
        ruta.unlink()
        try:
            os.symlink(destino, ruta)
        except (OSError, NotImplementedError):
            self.skipTest("sin privilegios de symlink")
        with self.assertRaises(LessonRechazada) as cm:
            les.cargar_lesson(self.raiz, l["lesson_id"])
        self.assertEqual(cm.exception.codigo, "LESSON_CORRUPTA")
        r = les.lessons_aplicables(self.raiz, CTX)
        self.assertEqual(r["descartadas"], [{"lesson_id": l["lesson_id"], "motivo": "lesson_corrupta"}])

    def test_b_lesson_enlace_rama_cubierta_sin_symlink_real(self):
        l = self.lesson()
        with mock.patch.object(les, "es_enlace", lambda ruta: True):
            with self.assertRaises(LessonRechazada) as cm:
                les.cargar_lesson(self.raiz, l["lesson_id"])
            self.assertEqual(cm.exception.codigo, "LESSON_CORRUPTA")
            r = les.lessons_aplicables(self.raiz, CTX)
        self.assertEqual(r["aplicables"], [])
        self.assertEqual(r["descartadas"], [{"lesson_id": l["lesson_id"], "motivo": "lesson_corrupta"}])

    def test_c_lessons_son_repo_locales(self):
        l = self.lesson()
        otro_tmp = tempfile.TemporaryDirectory()
        self.addCleanup(otro_tmp.cleanup)
        otro = crear_repo(Path(otro_tmp.name))
        # Otro repo sin lessons propias: nada aplica, aunque exista una en este repo.
        self.assertEqual(les.lessons_aplicables(otro, CTX), {"aplicables": [], "descartadas": []})
        # Una lesson copiada desde otro repo es íntegra pero su evidencia no existe aquí: no aplica.
        destino = otro / ".harmessi" / "improvement" / "lessons"
        destino.mkdir(parents=True)
        (destino / f"{l['lesson_id']}.json").write_bytes(self.ruta(l["lesson_id"]).read_bytes())
        r = les.lessons_aplicables(otro, CTX)
        self.assertEqual(r["aplicables"], [])
        self.assertEqual(r["descartadas"], [{"lesson_id": l["lesson_id"], "motivo": "evidencia_no_verificable"}])


if __name__ == "__main__":
    unittest.main()

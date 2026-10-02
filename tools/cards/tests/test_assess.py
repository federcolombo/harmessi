"""Tests de `tools.cards.assess` (R26-R33, R35, R31)."""
from __future__ import annotations

import ast
import hashlib
import json
import os
import tempfile
import unittest
from unittest import mock

from tools.cards import assess, core

H1 = "a" * 64
H2 = "b" * 64
T0 = "2026-10-01T10:00:00Z"
NOW = "2026-10-02T00:00:00Z"


# ---------------------------------------------------------------------------
# Fixtures sintéticos
# ---------------------------------------------------------------------------


def codigo_de(funcion, *args, **kwargs):
    try:
        funcion(*args, **kwargs)
    except core.CardError as exc:
        return exc.code
    raise AssertionError("no lanzó CardError")


def hacer_ev(**kw):
    base = dict(evidence_id="ev1", kind="quality_evidence", ref_id="qe-1", content_sha256=H1, pinned_at=T0)
    base.update(kw)
    return core.EvidenceRef(**base)


def hacer_att(**kw):
    base = dict(
        attestation_id="at1",
        claim="afirmo X",
        actor="ana",
        authority="owner",
        attested_at=T0,
        scope="alcance",
        attestation_kind="declared",
    )
    base.update(kw)
    return core.HumanAttestation(**base)


def hacer_card(**kw):
    base = dict(
        schema_version=1,
        card_kind="data_card",
        kind_schema_version=1,
        card_id="card-a",
        title="Titulo",
        subject="sujeto-logico",
        created_at=T0,
        generated_at=T0,
    )
    base.update(kw)
    return core.CardEnvelope(**base)


def req(rid="r1", severity="required", accepts=("observed",), **kw):
    return core.Requirement(rid, severity, accepts, **kw)


def claim(cid="c1", rid="r1", supports=("ev1",)):
    return core.Claim(cid, "afirmación", supports=supports, requirement_id=rid)


def resolvers_hash(mapa):
    """Resolver para todos los kinds: `evidence_id -> Resolution` (o hash str)."""

    def _resolver(ref):
        valor = mapa[ref.evidence_id]
        if isinstance(valor, assess.Resolution):
            return valor
        return assess.Resolution(assess.RES_FOUND, valor)

    return {k: _resolver for k in core.OBSERVED_KINDS}


def resolvers_frescos():
    return {k: (lambda ref: assess.Resolution(assess.RES_FOUND, ref.content_sha256)) for k in core.OBSERVED_KINDS}


def card_simple(**kw):
    """Card con ev1 que soporta r1."""
    base = dict(evidence=(hacer_ev(),), claims=(claim(),))
    base.update(kw)
    return hacer_card(**base)


def estado_req(assessment, rid="r1"):
    for r in assessment.requisitos:
        if r[0] == rid:
            return r[2]
    raise AssertionError(f"requisito {rid} ausente")


# ---------------------------------------------------------------------------
# R1 -- imports de assess
# ---------------------------------------------------------------------------


def _imports_de_modulo(arbol):
    """Imports a nivel de módulo (incluye try/except/if), sin entrar a funciones."""
    encontrados = []

    def visitar(nodos):
        for nodo in nodos:
            if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            if isinstance(nodo, ast.Import):
                encontrados.extend(("abs", a.name.split(".")[0]) for a in nodo.names)
            elif isinstance(nodo, ast.ImportFrom):
                encontrados.append(("rel" if nodo.level else "abs", (nodo.module or "").split(".")[0] or "|".join(a.name for a in nodo.names)))
            else:
                for campo in ("body", "orelse", "finalbody", "handlers"):
                    visitar(getattr(nodo, campo, []) or [])

    visitar(arbol.body)
    return encontrados


class TestImportsAssess(unittest.TestCase):
    def test_imports_a_nivel_de_modulo(self):
        ruta = os.path.join(os.path.dirname(__file__), "..", "assess.py")
        with open(ruta, "r", encoding="utf-8") as f:
            arbol = ast.parse(f.read(), filename="assess.py")
        permitidos_abs = {
            "__future__", "datetime", "hashlib", "json", "os", "re", "sys", "tempfile",
            "dataclasses", "pathlib", "typing", "core",
        }
        for tipo, nombre in _imports_de_modulo(arbol):
            self.assertIn(nombre, permitidos_abs | {"core"}, f"import no permitido: {tipo} {nombre}")
        # dsguard se importa solo de forma perezosa (dentro de una función).
        nombres_modulo = {n for _t, n in _imports_de_modulo(arbol)}
        self.assertNotIn("dsguard", nombres_modulo)
        self.assertNotIn("tools", nombres_modulo)


# ---------------------------------------------------------------------------
# R27/R28 -- estado por evidencia (fail-closed)
# ---------------------------------------------------------------------------


class TestResolution(unittest.TestCase):
    def test_estados_validos(self):
        self.assertEqual(assess.ESTADOS_RESOLUCION, ("found", "missing", "unverifiable"))
        self.assertEqual(assess.Resolution("missing").current_sha256, None)
        for state in ("weird", "", None, "FOUND"):
            with self.subTest(state=state):
                self.assertEqual(codigo_de(assess.Resolution, state), core.CODE_FIELD_INVALID)

    def test_tipos_de_campos(self):
        self.assertEqual(codigo_de(assess.Resolution, "found", 5), core.CODE_FIELD_INVALID)
        self.assertEqual(codigo_de(assess.Resolution, "found", H1, 5), core.CODE_FIELD_INVALID)


class TestEstadoEvidencia(unittest.TestCase):
    def setUp(self):
        self.ev = hacer_ev()

    def _estado(self, resolver, kind="quality_evidence"):
        return assess.evaluar_evidencia(self.ev, {kind: resolver})

    def test_fresh_si_el_hash_coincide(self):
        self.assertEqual(self._estado(lambda r: assess.Resolution("found", H1)), assess.EV_FRESH)

    def test_stale_si_el_hash_resuelto_difiere(self):
        self.assertEqual(self._estado(lambda r: assess.Resolution("found", H2)), assess.EV_STALE)

    def test_evidencia_inexistente_es_unresolvable(self):
        self.assertEqual(self._estado(lambda r: assess.Resolution("missing")), assess.EV_UNRESOLVABLE)

    def test_resolver_unverifiable_es_unverifiable(self):
        self.assertEqual(self._estado(lambda r: assess.Resolution("unverifiable", None, "x")), assess.EV_UNVERIFIABLE)

    def test_resolver_ausente_es_unverifiable(self):
        self.assertEqual(assess.evaluar_evidencia(self.ev, None), assess.EV_UNVERIFIABLE)
        self.assertEqual(assess.evaluar_evidencia(self.ev, {}), assess.EV_UNVERIFIABLE)
        self.assertEqual(
            assess.evaluar_evidencia(self.ev, {"source_observation": lambda r: assess.Resolution("found", H1)}),
            assess.EV_UNVERIFIABLE,
        )

    def test_resolver_no_callable_es_unverifiable(self):
        for valor in (None, "x", 5, {}):
            with self.subTest(valor=valor):
                self.assertEqual(assess.evaluar_evidencia(self.ev, {"quality_evidence": valor}), assess.EV_UNVERIFIABLE)

    def test_resolver_que_lanza_es_unverifiable_y_no_propaga(self):
        def lanza(_ref):
            raise RuntimeError("boom")

        for excepcion in (RuntimeError("x"), ValueError("x"), KeyError("x"), OSError("x"), core.CardError("CARD-X", "x")):
            with self.subTest(excepcion=type(excepcion).__name__):
                def _lanza(_r, e=excepcion):
                    raise e

                self.assertEqual(self._estado(_lanza), assess.EV_UNVERIFIABLE)
        self.assertEqual(self._estado(lanza), assess.EV_UNVERIFIABLE)

    def test_resolver_que_devuelve_basura_es_unverifiable(self):
        for basura in (None, "found", H1, 5, {"state": "found", "current_sha256": H1}, (H1,), [H1], True):
            with self.subTest(basura=basura):
                self.assertEqual(self._estado(lambda r, b=basura: b), assess.EV_UNVERIFIABLE)

    def test_found_sin_hash_o_con_hash_malformado_es_unverifiable(self):
        for actual in (None, "", "XYZ", "A" * 64, "a" * 63, "a" * 65, " " + "a" * 63):
            with self.subTest(actual=actual):
                self.assertEqual(
                    self._estado(lambda r, a=actual: assess.Resolution("found", a)), assess.EV_UNVERIFIABLE
                )

    def test_entradas_que_no_son_evidenceref_son_unverifiable(self):
        for valor in (None, "ev1", {"evidence_id": "ev1"}, hacer_att()):
            with self.subTest(valor=valor):
                self.assertEqual(
                    assess.evaluar_evidencia(valor, {"quality_evidence": lambda r: assess.Resolution("found", H1)}),
                    assess.EV_UNVERIFIABLE,
                )

    def test_resolver_recibe_la_evidenceref(self):
        vistos = []

        def resolver(ref):
            vistos.append(ref)
            return assess.Resolution("found", H1)

        assess.evaluar_evidencia(self.ev, {"quality_evidence": resolver})
        self.assertEqual(vistos, [self.ev])

    def test_nunca_fresh_por_defecto(self):
        # Ningún camino de error produce fresh.
        for resolvers in (None, {}, {"quality_evidence": None}, {"quality_evidence": lambda r: None}):
            with self.subTest(resolvers=resolvers):
                self.assertNotEqual(assess.evaluar_evidencia(self.ev, resolvers), assess.EV_FRESH)


# ---------------------------------------------------------------------------
# R29 -- estado por requisito
# ---------------------------------------------------------------------------


class TestEstadoRequisito(unittest.TestCase):
    def test_satisfied_con_evidencia_fresca(self):
        ev = assess.evaluate(card_simple(), [req()], resolvers_frescos())
        self.assertEqual(estado_req(ev), assess.REQ_SATISFIED)
        self.assertEqual(ev.card_status, assess.CARD_COMPLETE)

    def test_missing_sin_claim_ligado(self):
        card = hacer_card(evidence=(hacer_ev(),), claims=(claim(rid="otro"),))
        ev = assess.evaluate(card, [req()], resolvers_frescos())
        self.assertEqual(estado_req(ev), assess.REQ_MISSING)

    def test_missing_con_claim_sin_requirement_id(self):
        card = hacer_card(evidence=(hacer_ev(),), claims=(claim(rid=None),))
        ev = assess.evaluate(card, [req()], resolvers_frescos())
        self.assertEqual(estado_req(ev), assess.REQ_MISSING)

    def test_empty_con_claim_sin_supports(self):
        card = hacer_card(claims=(claim(supports=()),))
        ev = assess.evaluate(card, [req()], resolvers_frescos())
        self.assertEqual(estado_req(ev), assess.REQ_EMPTY)
        self.assertEqual(ev.card_status, assess.CARD_INCOMPLETE)

    def test_accepted_kinds_excluye_kind_es_untrusted_type(self):
        r = req(accepted_kinds=("drift_evidence",))
        ev = assess.evaluate(card_simple(), [r], resolvers_frescos())
        self.assertEqual(estado_req(ev), assess.REQ_UNTRUSTED_TYPE)
        self.assertEqual(ev.card_status, assess.CARD_INCOMPLETE)

    def test_accepted_kinds_incluye_kind_satisface(self):
        r = req(accepted_kinds=("drift_evidence", "quality_evidence"))
        ev = assess.evaluate(card_simple(), [r], resolvers_frescos())
        self.assertEqual(estado_req(ev), assess.REQ_SATISFIED)

    def test_accepted_kinds_none_acepta_cualquier_kind(self):
        for kind in core.OBSERVED_KINDS:
            with self.subTest(kind=kind):
                card = card_simple(evidence=(hacer_ev(kind=kind),))
                ev = assess.evaluate(card, [req()], resolvers_frescos())
                self.assertEqual(estado_req(ev), assess.REQ_SATISFIED)

    def test_attestation_only_no_acepta_evidencia_observada(self):
        ev = assess.evaluate(card_simple(), [req(accepts=("attestation",))], resolvers_frescos())
        self.assertEqual(estado_req(ev), assess.REQ_UNTRUSTED_TYPE)

    def test_evidencia_stale_es_stale(self):
        ev = assess.evaluate(card_simple(), [req()], resolvers_hash({"ev1": H2}))
        self.assertEqual(estado_req(ev), assess.REQ_STALE)
        self.assertEqual(ev.evidencias, (("ev1", assess.EV_STALE),))

    def test_evidencia_inexistente_es_unresolvable_y_no_satisface(self):
        ev = assess.evaluate(card_simple(), [req()], resolvers_hash({"ev1": assess.Resolution("missing")}))
        self.assertEqual(estado_req(ev), assess.REQ_UNRESOLVABLE)
        self.assertEqual(ev.card_status, assess.CARD_INCOMPLETE)

    def test_resolver_ausente_es_unverifiable_nunca_pass(self):
        for resolvers in (None, {}):
            with self.subTest(resolvers=resolvers):
                ev = assess.evaluate(card_simple(), [req()], resolvers)
                self.assertEqual(estado_req(ev), assess.REQ_UNVERIFIABLE)
                self.assertEqual(ev.card_status, assess.CARD_INCOMPLETE)
                statuses = [r.status for r in assess.a_check_results(ev)]
                self.assertNotIn("PASS", statuses)

    def test_resolver_que_lanza_es_unverifiable(self):
        def lanza(_ref):
            raise RuntimeError("boom")

        ev = assess.evaluate(card_simple(), [req()], {"quality_evidence": lanza})
        self.assertEqual(estado_req(ev), assess.REQ_UNVERIFIABLE)
        self.assertEqual(ev.card_status, assess.CARD_INCOMPLETE)

    def test_resolver_que_devuelve_basura_es_unverifiable(self):
        for basura in (None, "found", 5, {"state": "found"}):
            with self.subTest(basura=basura):
                ev = assess.evaluate(card_simple(), [req()], {"quality_evidence": lambda r, b=basura: b})
                self.assertEqual(estado_req(ev), assess.REQ_UNVERIFIABLE)

    def test_soporte_stale_mas_soporte_fresh_es_satisfied_y_reporta_stale(self):
        card = hacer_card(
            evidence=(hacer_ev(), hacer_ev(evidence_id="ev2", ref_id="qe-2", content_sha256=H2)),
            claims=(claim(supports=("ev1", "ev2")),),
        )
        ev = assess.evaluate(card, [req()], resolvers_hash({"ev1": "c" * 64, "ev2": H2}))
        self.assertEqual(estado_req(ev), assess.REQ_SATISFIED)
        self.assertEqual(ev.card_status, assess.CARD_COMPLETE)
        self.assertEqual(ev.evidencias, (("ev1", assess.EV_STALE), ("ev2", assess.EV_FRESH)))
        # queda reportado como WARN
        codigos = [(r.status, r.code) for r in assess.a_check_results(ev)]
        self.assertIn(("WARN", core.CODE_EVIDENCE_STALE), codigos)
        self.assertIn(("PASS", assess.CODE_CARD_COMPLETE), codigos)

    def test_varios_claims_del_mismo_requisito_unen_sus_soportes(self):
        card = hacer_card(
            evidence=(hacer_ev(), hacer_ev(evidence_id="ev2", ref_id="qe-2", content_sha256=H2)),
            claims=(claim("c1", supports=("ev1",)), claim("c2", supports=("ev2",))),
        )
        ev = assess.evaluate(card, [req()], resolvers_hash({"ev1": "c" * 64, "ev2": H2}))
        self.assertEqual(estado_req(ev), assess.REQ_SATISFIED)

    def test_precedencia_entre_soportes_no_vigentes(self):
        # stale > unresolvable > unverifiable cuando ninguno es fresh.
        evs = (
            hacer_ev(evidence_id="e1", ref_id="q1"),
            hacer_ev(evidence_id="e2", ref_id="q2"),
            hacer_ev(evidence_id="e3", ref_id="q3"),
        )
        card = hacer_card(evidence=evs, claims=(claim(supports=("e1", "e2", "e3")),))
        res = {"e1": assess.Resolution("missing"), "e2": assess.Resolution("unverifiable"), "e3": H2}
        ev = assess.evaluate(card, [req()], resolvers_hash(res))
        self.assertEqual(estado_req(ev), assess.REQ_STALE)
        res["e3"] = assess.Resolution("missing")
        ev = assess.evaluate(card, [req()], resolvers_hash(res))
        self.assertEqual(estado_req(ev), assess.REQ_UNRESOLVABLE)

    def test_requisitos_ordenados_por_id_independiente_del_orden_de_entrada(self):
        card = card_simple(claims=(claim("c1", "r1"), claim("c2", "r2"), claim("c3", "r3")))
        a = assess.evaluate(card, [req("r3"), req("r1"), req("r2")], resolvers_frescos())
        b = assess.evaluate(card, [req("r1"), req("r2"), req("r3")], resolvers_frescos())
        self.assertEqual([r[0] for r in a.requisitos], ["r1", "r2", "r3"])
        self.assertEqual(a.a_dict(), b.a_dict())


# ---------------------------------------------------------------------------
# R25/R30 -- Card vacía, Card completa imposible sin evidencia
# ---------------------------------------------------------------------------


class TestCardVaciaYCompleta(unittest.TestCase):
    def test_card_vacia_con_requisito_required_nunca_complete(self):
        ev = assess.evaluate(hacer_card(), [req()], resolvers_frescos())
        self.assertEqual(estado_req(ev), assess.REQ_MISSING)
        self.assertEqual(ev.card_status, assess.CARD_INCOMPLETE)
        self.assertNotEqual(ev.card_status, assess.CARD_COMPLETE)

    def test_card_vacia_con_varios_requisitos_required_nunca_complete(self):
        ev = assess.evaluate(hacer_card(), [req("r1"), req("r2", accepts=("attestation",))], resolvers_frescos())
        self.assertEqual({r[2] for r in ev.requisitos}, {assess.REQ_MISSING})
        self.assertNotEqual(ev.card_status, assess.CARD_COMPLETE)

    def test_card_vacia_sin_requisitos_nunca_complete(self):
        # Spec R25/R30 y criterios de aceptación: «La ausencia de evidencia nunca
        # produce complete» / «Card vacía/plantilla ... nunca complete».
        for requisitos in (None, [], ()):
            with self.subTest(requisitos=requisitos):
                ev = assess.evaluate(hacer_card(), requisitos, resolvers_frescos())
                self.assertTrue(ev.sin_requisitos)
                self.assertNotEqual(ev.card_status, assess.CARD_COMPLETE)

    def test_card_con_solo_plantilla_en_blanco_no_construye(self):
        # textos en blanco son rechazados por el contrato: no hay plantilla en blanco válida.
        self.assertEqual(codigo_de(core.Claim, "c1", "   "), core.CODE_FIELD_INVALID)
        self.assertEqual(codigo_de(hacer_att, claim="  "), core.CODE_FIELD_INVALID)

    def test_complete_imposible_sin_evidencia_requerida(self):
        casos = {
            "sin claims": hacer_card(evidence=(hacer_ev(),)),
            "claim sin supports": hacer_card(claims=(claim(supports=()),)),
            "claim de otro requisito": card_simple(claims=(claim(rid="otro"),)),
            "solo atestacion en observed-only": hacer_card(
                attestations=(hacer_att(),), claims=(claim(supports=("at1",)),)
            ),
        }
        for nombre, card in casos.items():
            with self.subTest(nombre=nombre):
                ev = assess.evaluate(card, [req()], resolvers_frescos())
                self.assertNotEqual(ev.card_status, assess.CARD_COMPLETE)

    def test_soporte_inexistente_invalida_en_lugar_de_completar(self):
        card = hacer_card(claims=(claim(supports=("fantasma",)),))
        ev = assess.evaluate(card, [req()], resolvers_frescos())
        self.assertEqual(ev.card_status, assess.CARD_INVALID)
        self.assertEqual([h.code for h in ev.hallazgos], [core.CODE_DANGLING_SUPPORT])

    def test_requisito_recommended_no_satisfecho_no_impide_complete_pero_si_un_required(self):
        card = card_simple()
        ev = assess.evaluate(card, [req("r1"), req("r2", severity="recommended")], resolvers_frescos())
        self.assertEqual(ev.card_status, assess.CARD_COMPLETE)
        self.assertEqual(estado_req(ev, "r2"), assess.REQ_MISSING)
        ev = assess.evaluate(card, [req("r1"), req("r2", severity="required")], resolvers_frescos())
        self.assertEqual(ev.card_status, assess.CARD_INCOMPLETE)

    def test_complete_con_todos_los_required_satisfechos(self):
        card = card_simple(claims=(claim("c1", "r1"), claim("c2", "r2")))
        ev = assess.evaluate(card, [req("r1"), req("r2")], resolvers_frescos())
        self.assertEqual(ev.card_status, assess.CARD_COMPLETE)


# ---------------------------------------------------------------------------
# R30 -- precedencia
# ---------------------------------------------------------------------------


class TestPrecedenciaCard(unittest.TestCase):
    def test_tupla_de_precedencia(self):
        self.assertEqual(assess.PRECEDENCIA_CARD, ("invalid", "stale", "incomplete", "complete"))

    def _card_stale_e_incomplete(self):
        # r1 stale (required); r2 missing (required)
        return card_simple()

    def test_stale_mas_incomplete_es_stale(self):
        ev = assess.evaluate(self._card_stale_e_incomplete(), [req("r1"), req("r2")], resolvers_hash({"ev1": H2}))
        self.assertEqual(estado_req(ev, "r1"), assess.REQ_STALE)
        self.assertEqual(estado_req(ev, "r2"), assess.REQ_MISSING)
        self.assertEqual(ev.card_status, assess.CARD_STALE)

    def test_stale_solo_en_recommended_no_hace_stale_la_card(self):
        ev = assess.evaluate(card_simple(), [req("r1", severity="recommended")], resolvers_hash({"ev1": H2}))
        self.assertEqual(estado_req(ev, "r1"), assess.REQ_STALE)
        self.assertEqual(ev.card_status, assess.CARD_COMPLETE)

    def test_invalid_mas_stale_es_invalid(self):
        # evidencia con hash distinto + soporte colgante en otro claim
        card = card_simple(claims=(claim("c1", "r1"), claim("c2", "r2", supports=("fantasma",))))
        ev = assess.evaluate(card, [req("r1")], resolvers_hash({"ev1": H2}))
        self.assertEqual(ev.card_status, assess.CARD_INVALID)

    def test_invalid_mas_incomplete_es_invalid(self):
        card = card_simple(claims=(claim("c2", "r2", supports=("fantasma",)),))
        ev = assess.evaluate(card, [req("r1")], resolvers_frescos())
        self.assertEqual(ev.card_status, assess.CARD_INVALID)

    def test_card_invalid_no_evalua_evidencia_ni_invoca_resolvers(self):
        llamadas = []

        def resolver(ref):
            llamadas.append(ref)
            return assess.Resolution("found", H1)

        card = card_simple(claims=(claim("c2", "r2", supports=("fantasma",)),))
        ev = assess.evaluate(card, [req("r1")], {k: resolver for k in core.OBSERVED_KINDS})
        self.assertEqual(ev.card_status, assess.CARD_INVALID)
        self.assertEqual(llamadas, [])
        self.assertEqual(ev.requisitos, ())
        self.assertEqual(ev.evidencias, ())

    def test_invalid_por_ids_duplicados_y_schema(self):
        dup = hacer_card(evidence=(hacer_ev(), hacer_ev()))
        self.assertEqual(assess.evaluate(dup, [req()], resolvers_frescos()).card_status, assess.CARD_INVALID)
        sv = hacer_card(schema_version=2)
        self.assertEqual(assess.evaluate(sv, [req()], resolvers_frescos()).card_status, assess.CARD_INVALID)

    def test_invalid_por_body_sin_validador(self):
        card = hacer_card(body={"a": 1})
        self.assertEqual(assess.evaluate(card, [req()], None).card_status, assess.CARD_INVALID)
        ok = assess.evaluate(card, [req()], None, validate_body=lambda b: [])
        self.assertNotEqual(ok.card_status, assess.CARD_INVALID)

    def test_card_que_no_es_cardenvelope_es_invalid(self):
        ev = assess.evaluate({"card_id": "x"}, [req()], None)
        self.assertEqual(ev.card_status, assess.CARD_INVALID)
        self.assertEqual(ev.card_id, "")


# ---------------------------------------------------------------------------
# Entradas de evaluate
# ---------------------------------------------------------------------------


class TestEntradasEvaluate(unittest.TestCase):
    def test_requirement_id_duplicado(self):
        self.assertEqual(
            codigo_de(assess.evaluate, card_simple(), [req("r1"), req("r1")], None), core.CODE_DUPLICATE_ID
        )

    def test_requirements_con_elementos_que_no_son_requirement(self):
        for malo in (None, {"requirement_id": "r1"}, "r1", 5):
            with self.subTest(malo=malo):
                self.assertEqual(codigo_de(assess.evaluate, card_simple(), [malo], None), core.CODE_FIELD_INVALID)

    def test_requirements_no_iterable(self):
        self.assertEqual(codigo_de(assess.evaluate, card_simple(), 5, None), core.CODE_FIELD_INVALID)

    def test_resolvers_debe_ser_mapa(self):
        for malo in ([], "x", 5, lambda r: None):
            with self.subTest(malo=malo):
                self.assertEqual(codigo_de(assess.evaluate, card_simple(), [req()], malo), core.CODE_FIELD_INVALID)

    def test_requirements_acepta_tupla_y_generador(self):
        ev = assess.evaluate(card_simple(), (r for r in [req()]), resolvers_frescos())
        self.assertEqual(ev.card_status, assess.CARD_COMPLETE)


# ---------------------------------------------------------------------------
# R35 -- sin reloj del sistema en la evaluación
# ---------------------------------------------------------------------------


class TestSinRelojDelSistema(unittest.TestCase):
    def test_evaluate_no_usa_el_reloj_del_sistema(self):
        card = card_simple(attestations=(hacer_att(attested_at="2999-01-01T00:00:00Z"),))
        with mock.patch.object(assess, "_reloj_utc", side_effect=AssertionError("reloj del sistema")):
            with mock.patch.object(assess, "_datetime") as dt:
                dt.datetime.now.side_effect = AssertionError("reloj del sistema")
                dt.datetime.utcnow.side_effect = AssertionError("reloj del sistema")
                ev = assess.evaluate(card, [req()], resolvers_frescos())
                assess.a_check_results(ev)
        # sin clock, la atestación en 2999 no se cuestiona
        self.assertEqual(ev.card_status, assess.CARD_COMPLETE)

    def test_evaluate_usa_el_clock_inyectado(self):
        llamadas = []

        def reloj():
            llamadas.append(1)
            return NOW

        assess.evaluate(card_simple(attestations=(hacer_att(),)), [req()], resolvers_frescos(), reloj)
        self.assertGreaterEqual(len(llamadas), 1)

    def test_funciones_de_evaluacion_no_referencian_el_reloj(self):
        ruta = os.path.join(os.path.dirname(__file__), "..", "assess.py")
        with open(ruta, "r", encoding="utf-8") as f:
            arbol = ast.parse(f.read(), filename="assess.py")
        prohibidos = {"_reloj_utc", "now", "utcnow", "today", "time", "monotonic", "perf_counter"}
        evaluacion = {
            "evaluate", "evaluar_evidencia", "_evaluar_requisito", "_estado_card", "_validar_requirements",
            "file_sha256_resolver", "a_check_results", "read_card",
        }
        encontradas = set()
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.FunctionDef) and nodo.name in evaluacion:
                encontradas.add(nodo.name)
                for sub in ast.walk(nodo):
                    if isinstance(sub, ast.Name):
                        self.assertNotIn(sub.id, prohibidos, f"{nodo.name} usa {sub.id}")
                    if isinstance(sub, ast.Attribute):
                        self.assertNotIn(sub.attr, prohibidos, f"{nodo.name} usa {sub.attr}")
        self.assertEqual(encontradas, evaluacion)

    def test_resultado_determinista(self):
        a = assess.evaluate(card_simple(), [req()], resolvers_frescos()).a_dict()
        b = assess.evaluate(card_simple(), [req()], resolvers_frescos()).a_dict()
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))


# ---------------------------------------------------------------------------
# a_dict y estado nunca persistido
# ---------------------------------------------------------------------------


class TestADict(unittest.TestCase):
    def test_a_dict_estructura(self):
        ev = assess.evaluate(card_simple(), [req()], resolvers_frescos())
        d = ev.a_dict()
        self.assertEqual(
            set(d), {"card_id", "card_status", "sin_requisitos", "requisitos", "evidencias", "hallazgos"}
        )
        self.assertEqual(d["card_id"], "card-a")
        self.assertEqual(d["card_status"], "complete")
        self.assertEqual(d["requisitos"][0]["requirement_id"], "r1")
        self.assertEqual(d["evidencias"], [{"evidence_id": "ev1", "state": "fresh"}])
        json.dumps(d)  # serializable

    def test_a_dict_de_invalid_lista_hallazgos(self):
        card = hacer_card(claims=(claim(supports=("fantasma",)),))
        d = assess.evaluate(card, [req()], None).a_dict()
        self.assertEqual(d["card_status"], "invalid")
        self.assertEqual(d["hallazgos"][0][0], core.CODE_DANGLING_SUPPORT)

    def test_la_card_no_tiene_status_y_evaluar_no_la_modifica(self):
        card = card_simple()
        antes = card.to_dict()
        assess.evaluate(card, [req()], resolvers_frescos())
        self.assertEqual(card.to_dict(), antes)
        self.assertNotIn("status", antes)
        self.assertNotIn("card_status", antes)
        self.assertFalse(hasattr(card, "status"))


# ---------------------------------------------------------------------------
# R32/R33 -- CheckResult
# ---------------------------------------------------------------------------

FRASE = "card governance requirements not satisfied"
PROHIBIDA = "autonomous execution forbidden"


class TestCheckResults(unittest.TestCase):
    def setUp(self):
        self.checks = assess._checks_module()

    def test_requiere_cardassessment(self):
        for malo in (None, {}, "x", card_simple()):
            with self.subTest(malo=malo):
                self.assertEqual(codigo_de(assess.a_check_results, malo), core.CODE_FIELD_INVALID)

    def test_sin_requisitos_un_unico_na(self):
        ev = assess.evaluate(card_simple(), [], resolvers_frescos())
        res = assess.a_check_results(ev)
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0].status, self.checks.STATUS_NA)
        self.assertEqual(res[0].code, assess.CODE_NO_REQUIREMENTS)

    def test_required_no_satisfecho_es_fail_con_codigo_por_estado(self):
        casos = (
            (hacer_card(), None, core.CODE_REQUIREMENT_MISSING),
            (hacer_card(claims=(claim(supports=()),)), None, core.CODE_REQUIREMENT_EMPTY),
            (card_simple(), resolvers_hash({"ev1": H2}), core.CODE_REQUIREMENT_STALE),
            (card_simple(), resolvers_hash({"ev1": assess.Resolution("missing")}), core.CODE_REQUIREMENT_UNRESOLVABLE),
            (card_simple(), None, core.CODE_REQUIREMENT_UNVERIFIABLE),
            (
                hacer_card(attestations=(hacer_att(),), claims=(claim(supports=("at1",)),)),
                None,
                core.CODE_REQUIREMENT_UNTRUSTED_TYPE,
            ),
        )
        for card, resolvers, codigo in casos:
            with self.subTest(codigo=codigo):
                res = assess.a_check_results(assess.evaluate(card, [req()], resolvers))
                fallos = [r for r in res if r.status == self.checks.STATUS_FAIL]
                self.assertEqual([r.code for r in fallos], [codigo])
                self.assertEqual(fallos[0].subject, "card-a")

    def test_recommended_no_satisfecho_es_warn(self):
        ev = assess.evaluate(card_simple(), [req("r1"), req("r2", severity="recommended")], resolvers_frescos())
        res = assess.a_check_results(ev)
        self.assertEqual(
            [(r.status, r.code) for r in res],
            [(self.checks.STATUS_WARN, core.CODE_REQUIREMENT_MISSING), (self.checks.STATUS_PASS, assess.CODE_CARD_COMPLETE)],
        )

    def test_complete_incluye_pass(self):
        res = assess.a_check_results(assess.evaluate(card_simple(), [req()], resolvers_frescos()))
        self.assertEqual([r.status for r in res], [self.checks.STATUS_PASS])
        self.assertEqual(res[0].code, assess.CODE_CARD_COMPLETE)

    def test_incomplete_no_incluye_pass(self):
        res = assess.a_check_results(assess.evaluate(hacer_card(), [req()], None))
        self.assertNotIn(self.checks.STATUS_PASS, [r.status for r in res])

    def test_invalid_un_fail_por_hallazgo(self):
        card = hacer_card(
            evidence=(hacer_ev(), hacer_ev()),
            claims=(claim(supports=("fantasma",)),),
        )
        ev = assess.evaluate(card, [req()], None)
        res = assess.a_check_results(ev)
        self.assertEqual(len(res), len(ev.hallazgos))
        self.assertEqual(
            sorted(r.code for r in res), sorted([core.CODE_DUPLICATE_ID, core.CODE_DANGLING_SUPPORT])
        )
        self.assertTrue(all(r.status == self.checks.STATUS_FAIL for r in res))

    def test_invalid_sin_hallazgos_igual_da_un_fail(self):
        a = assess.CardAssessment(card_status=assess.CARD_INVALID, card_id="card-a")
        res = assess.a_check_results(a)
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0].status, self.checks.STATUS_FAIL)

    def test_evidencia_stale_genera_warn_aunque_el_requisito_sea_satisfecho(self):
        card = hacer_card(
            evidence=(hacer_ev(), hacer_ev(evidence_id="ev2", ref_id="qe-2")),
            claims=(claim(supports=("ev2",)),),
        )
        ev = assess.evaluate(card, [req()], resolvers_hash({"ev1": H2, "ev2": H1}))
        res = assess.a_check_results(ev)
        self.assertIn((self.checks.STATUS_WARN, core.CODE_EVIDENCE_STALE), [(r.status, r.code) for r in res])

    def test_mensajes_de_governance_y_nunca_autonomia(self):
        escenarios = (
            assess.evaluate(hacer_card(), [req(), req("r2", severity="recommended")], None),
            assess.evaluate(card_simple(), [req()], resolvers_hash({"ev1": H2})),
            assess.evaluate(hacer_card(claims=(claim(supports=("fantasma",)),)), [req()], None),
            assess.evaluate(card_simple(), [req()], resolvers_frescos()),
            assess.evaluate(card_simple(), [], None),
        )
        for ev in escenarios:
            for r in assess.a_check_results(ev):
                texto = f"{r.message} {r.detail or ''}".lower()
                self.assertNotIn(PROHIBIDA, texto)
                self.assertNotIn("stop", texto.split())
                self.assertNotIn("autonomy", texto)
                if r.status in (self.checks.STATUS_FAIL, self.checks.STATUS_WARN):
                    self.assertIn(FRASE, r.message)


# ---------------------------------------------------------------------------
# R31 -- file_sha256_resolver
# ---------------------------------------------------------------------------


class TestFileSha256Resolver(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.raiz = os.path.join(self._tmp.name, "repo")
        os.makedirs(os.path.join(self.raiz, "data"))
        self.contenido = b"hola\r\nmundo\n\x00\xff"
        with open(os.path.join(self.raiz, "data", "x.bin"), "wb") as f:
            f.write(self.contenido)
        self.hash_real = hashlib.sha256(self.contenido).hexdigest()
        self.resolver = assess.file_sha256_resolver(self.raiz)

    def _ref(self, locator, sha=None):
        return hacer_ev(kind="report_artifact", locator=locator, content_sha256=sha or self.hash_real)

    def test_fresh_si_el_archivo_coincide_con_el_pin(self):
        ref = self._ref("data/x.bin")
        res = self.resolver(ref)
        self.assertEqual(res.state, assess.RES_FOUND)
        self.assertEqual(res.current_sha256, self.hash_real)
        self.assertEqual(assess.evaluar_evidencia(ref, {"report_artifact": self.resolver}), assess.EV_FRESH)

    def test_hash_es_binario_no_normaliza_saltos_de_linea(self):
        res = self.resolver(self._ref("data/x.bin"))
        self.assertEqual(res.current_sha256, hashlib.sha256(b"hola\r\nmundo\n\x00\xff").hexdigest())
        self.assertNotEqual(res.current_sha256, hashlib.sha256(b"hola\nmundo\n\x00\xff").hexdigest())

    def test_stale_si_el_archivo_cambia(self):
        ref = self._ref("data/x.bin")
        with open(os.path.join(self.raiz, "data", "x.bin"), "ab") as f:
            f.write(b"mas")
        self.assertEqual(assess.evaluar_evidencia(ref, {"report_artifact": self.resolver}), assess.EV_STALE)

    def test_missing_si_el_archivo_no_existe(self):
        res = self.resolver(self._ref("data/no_existe.bin"))
        self.assertEqual(res.state, assess.RES_MISSING)
        self.assertEqual(
            assess.evaluar_evidencia(self._ref("data/no_existe.bin"), {"report_artifact": self.resolver}),
            assess.EV_UNRESOLVABLE,
        )

    def test_sin_locator_es_unverifiable(self):
        ref = hacer_ev(kind="report_artifact")
        self.assertEqual(self.resolver(ref).state, assess.RES_UNVERIFIABLE)

    def test_fuera_de_repo_root_es_unverifiable_aunque_exista(self):
        fuera = os.path.join(self._tmp.name, "secreto.txt")
        with open(fuera, "wb") as f:
            f.write(b"x")
        # un locator con '..' ni siquiera puede construirse como EvidenceRef...
        self.assertEqual(codigo_de(hacer_ev, kind="report_artifact", locator="../secreto.txt"), core.CODE_LOCATOR_NOT_PORTABLE)

        # ...y si un objeto lo trae igualmente, el resolver no sale de repo_root.
        class RefFalsa:
            locator = "../secreto.txt"

        res = self.resolver(RefFalsa())
        self.assertEqual(res.state, assess.RES_UNVERIFIABLE)

    def test_locators_absolutos_o_con_barra_invertida_en_objeto_ajeno_son_unverifiable(self):
        for locator in ("/etc/hosts", "C:\\Windows\\win.ini", "data\\x.bin", "https://h/x"):
            with self.subTest(locator=locator):
                ref = type("RefFalsa", (), {"locator": locator})()
                self.assertEqual(self.resolver(ref).state, assess.RES_UNVERIFIABLE)

    def test_locator_con_dos_puntos_es_unverifiable(self):
        # portable según core, pero el resolver lo rechaza (':' => ADS / unidad).
        locator = "data/x.bin:stream"
        self.assertTrue(core.es_locator_portable(locator))
        self.assertEqual(self.resolver(self._ref(locator)).state, assess.RES_UNVERIFIABLE)

    def test_directorio_no_es_archivo(self):
        self.assertEqual(self.resolver(self._ref("data")).state, assess.RES_UNVERIFIABLE)

    def test_enlace_simbolico_que_escapa_de_repo_root(self):
        fuera = os.path.join(self._tmp.name, "afuera.txt")
        with open(fuera, "wb") as f:
            f.write(b"x")
        enlace = os.path.join(self.raiz, "data", "link.txt")
        try:
            os.symlink(fuera, enlace)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks no disponibles en este entorno")
        self.assertEqual(self.resolver(self._ref("data/link.txt")).state, assess.RES_UNVERIFIABLE)

    def test_repo_root_invalido(self):
        self.assertEqual(codigo_de(assess.file_sha256_resolver, None), core.CODE_FIELD_INVALID)

    def test_integracion_con_evaluate_y_card_stale(self):
        ref = self._ref("data/x.bin")
        card = hacer_card(evidence=(ref,), claims=(claim(),))
        resolvers = {"report_artifact": self.resolver}
        self.assertEqual(assess.evaluate(card, [req()], resolvers).card_status, assess.CARD_COMPLETE)
        with open(os.path.join(self.raiz, "data", "x.bin"), "wb") as f:
            f.write(b"cambiado")
        ev = assess.evaluate(card, [req()], resolvers)
        self.assertEqual(ev.card_status, assess.CARD_STALE)
        self.assertEqual(estado_req(ev), assess.REQ_STALE)


if __name__ == "__main__":
    unittest.main()

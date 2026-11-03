"""Tests de `HumanAttestation` (R16-R21, R24, R19) y su efecto en la evaluación."""
from __future__ import annotations

import json
import unittest

from tools.cards import assess, core

H1 = "a" * 64
H2 = "b" * 64
T0 = "2026-10-01T10:00:00Z"
NOW = "2026-10-02T00:00:00Z"

APPROVAL_REF = {
    "change_id": "20261002-card-and-evidence-foundation",
    "artefacto": "proposal.md",
    "hash": H2,
}


def codigo_de(funcion, *args, **kwargs):
    try:
        funcion(*args, **kwargs)
    except core.CardError as exc:
        return exc.code
    raise AssertionError("no lanzó CardError")


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


def hacer_anchored(**kw):
    base = dict(attestation_kind="anchored", approval_ref=dict(APPROVAL_REF))
    base.update(kw)
    return hacer_att(**base)


def dict_att(**kw):
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
    return base


def hacer_ev(**kw):
    base = dict(evidence_id="ev1", kind="quality_evidence", ref_id="qe-1", content_sha256=H1, pinned_at=T0)
    base.update(kw)
    return core.EvidenceRef(**base)


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


def resolvers_frescos():
    return {k: (lambda ref: assess.Resolution(assess.RES_FOUND, ref.content_sha256)) for k in core.OBSERVED_KINDS}


def card_con_atestacion(att, claim_req="r1"):
    return hacer_card(
        attestations=(att,),
        claims=(core.Claim("c1", "afirmación", supports=(att.attestation_id,), requirement_id=claim_req),),
    )


# ---------------------------------------------------------------------------
# declared / anchored (R21)
# ---------------------------------------------------------------------------


class TestDeclared(unittest.TestCase):
    def test_declared_valida(self):
        a = hacer_att()
        self.assertEqual(a.attestation_kind, "declared")
        self.assertIsNone(a.approval_ref)
        self.assertEqual(a.evidence_class, "attestation")
        self.assertNotIn("approval_ref", a.to_dict())
        self.assertEqual(core.validate_card(card_con_atestacion(a)), [])

    def test_declared_con_approval_ref_es_kind_invalid(self):
        self.assertEqual(
            codigo_de(hacer_att, approval_ref=dict(APPROVAL_REF)), core.CODE_ATTESTATION_KIND_INVALID
        )

    def test_declared_con_approval_ref_aunque_sea_vacio_o_malformado_es_kind_invalid(self):
        for valor in ({}, "x", {"hash": "z"}, 5, []):
            with self.subTest(valor=valor):
                self.assertEqual(codigo_de(hacer_att, approval_ref=valor), core.CODE_ATTESTATION_KIND_INVALID)

    def test_declared_con_approval_ref_via_from_dict(self):
        self.assertEqual(
            codigo_de(core.HumanAttestation.from_dict, dict_att(approval_ref=dict(APPROVAL_REF))),
            core.CODE_ATTESTATION_KIND_INVALID,
        )

    def test_declared_con_approval_ref_null_es_valida(self):
        self.assertIsNone(core.HumanAttestation.from_dict(dict_att(approval_ref=None)).approval_ref)


class TestAnchored(unittest.TestCase):
    def test_anchored_sin_approval_ref_es_invalida(self):
        self.assertEqual(
            codigo_de(hacer_att, attestation_kind="anchored"), core.CODE_APPROVAL_REF_INVALID
        )
        self.assertEqual(
            codigo_de(core.HumanAttestation.from_dict, dict_att(attestation_kind="anchored")),
            core.CODE_APPROVAL_REF_INVALID,
        )

    def test_anchored_con_approval_ref_malformada_es_invalida(self):
        casos = {
            "no es dict": "texto",
            "lista": [APPROVAL_REF],
            "vacio": {},
            "sin hash": {"change_id": APPROVAL_REF["change_id"], "artefacto": "proposal.md"},
            "sin change_id": {"artefacto": "proposal.md", "hash": H2},
            "sin artefacto": {"change_id": APPROVAL_REF["change_id"], "hash": H2},
            "hash mayusculas": dict(APPROVAL_REF, hash="B" * 64),
            "hash corto": dict(APPROVAL_REF, hash="b" * 63),
            "hash no str": dict(APPROVAL_REF, hash=123),
            "change_id sin fecha": dict(APPROVAL_REF, change_id="card-and-evidence"),
            "change_id mayusculas": dict(APPROVAL_REF, change_id="20261002-Card"),
            "change_id no str": dict(APPROVAL_REF, change_id=20261002),
            "artefacto con barra": dict(APPROVAL_REF, artefacto="a/b.md"),
            "artefacto con barra invertida": dict(APPROVAL_REF, artefacto="a\\b.md"),
            "artefacto punto punto": dict(APPROVAL_REF, artefacto=".."),
            "artefacto punto": dict(APPROVAL_REF, artefacto="."),
            "artefacto vacio": dict(APPROVAL_REF, artefacto=""),
            "artefacto con espacios": dict(APPROVAL_REF, artefacto=" proposal.md"),
            "clave extra": dict(APPROVAL_REF, extra="x"),
        }
        for nombre, valor in casos.items():
            with self.subTest(nombre=nombre):
                self.assertEqual(codigo_de(hacer_anchored, approval_ref=valor), core.CODE_APPROVAL_REF_INVALID)

    def test_validate_approval_ref_no_lanza_y_reporta(self):
        self.assertEqual(core.validate_approval_ref(dict(APPROVAL_REF)), [])
        for valor in (None, "x", 5, [], {}, {"hash": 1}):
            with self.subTest(valor=valor):
                hallazgos = core.validate_approval_ref(valor)
                self.assertTrue(hallazgos)
                self.assertTrue(all(h.code == core.CODE_APPROVAL_REF_INVALID for h in hallazgos))

    def test_claves_mixtas_no_lanzan_typeerror_en_validate_approval_ref(self):
        casos = (
            {1: "x", "foo": "y"},
            {1: 1, None: 2},
            {**APPROVAL_REF, 1: "x", None: "y", (2, 3): "z", "foo": 1},
        )
        for valor in casos:
            with self.subTest(valor=valor):
                hallazgos = core.validate_approval_ref(valor)
                self.assertTrue(hallazgos)
                self.assertTrue(all(h.code == core.CODE_APPROVAL_REF_INVALID for h in hallazgos))
                self.assertIn("unknown_key", [h.detail for h in hallazgos])
                # determinista
                self.assertEqual(hallazgos, core.validate_approval_ref(valor))

    def test_claves_mixtas_via_constructor_solo_lanzan_carderror(self):
        casos = (
            {1: "x", "foo": "y"},
            {1: 1, None: 2},
            {**APPROVAL_REF, 1: "x", None: "y"},
        )
        for valor in casos:
            with self.subTest(valor=valor):
                self.assertEqual(codigo_de(hacer_anchored, approval_ref=valor), core.CODE_APPROVAL_REF_INVALID)

    def test_anchored_estructuralmente_valida(self):
        a = hacer_anchored()
        self.assertEqual(a.attestation_kind, "anchored")
        self.assertEqual(a.approval_ref, APPROVAL_REF)
        self.assertEqual(core.validate_card(card_con_atestacion(a)), [])

    def test_approval_ref_se_copia_y_no_comparte_estado(self):
        origen = dict(APPROVAL_REF)
        a = hacer_anchored(approval_ref=origen)
        origen["hash"] = "c" * 64
        self.assertEqual(a.approval_ref["hash"], H2)
        copia = a.to_dict()["approval_ref"]
        copia["hash"] = "d" * 64
        self.assertEqual(a.approval_ref["hash"], H2)

    def test_anchored_no_afirma_verificacion_contra_ledger(self):
        # Change 0 solo valida la FORMA: el assessment no puede afirmar
        # verificación contra control.json / ledger / hash de proposal.
        a = hacer_anchored()
        card = card_con_atestacion(a)
        requisito = req(accepts=("attestation",), min_attestation_kind="anchored")
        ev = assess.evaluate(card, [requisito], resolvers_frescos(), clock=lambda: NOW)
        self.assertEqual(ev.card_status, assess.CARD_COMPLETE)
        textos = json.dumps(ev.a_dict()).lower()
        textos += " ".join(
            (r.message + " " + (r.detail or "")) for r in assess.a_check_results(ev)
        ).lower()
        for palabra in ("verified", "verificad", "verific", "ledger", "control.json", "authentic", "autentic"):
            self.assertNotIn(palabra, textos)

    def test_anchored_malformada_dentro_de_card_via_from_dict(self):
        d = hacer_card(attestations=(hacer_anchored(),)).to_dict()
        d["attestations"][0]["approval_ref"]["hash"] = "zzz"
        self.assertEqual(codigo_de(core.CardEnvelope.from_dict, d), core.CODE_APPROVAL_REF_INVALID)


class TestAttestationKindUnion(unittest.TestCase):
    def test_kinds_validos(self):
        self.assertEqual(core.ATTESTATION_KINDS, ("declared", "anchored"))

    def test_desconocido_o_hibrido_rechazado(self):
        for valor in ("verified", "hybrid", "declared|anchored", "declared,anchored", "", "DECLARED", "Anchored", None, 1, ["declared"]):
            with self.subTest(valor=valor):
                self.assertEqual(
                    codigo_de(hacer_att, attestation_kind=valor), core.CODE_ATTESTATION_KIND_INVALID
                )
                self.assertEqual(
                    codigo_de(core.HumanAttestation.from_dict, dict_att(attestation_kind=valor)),
                    core.CODE_ATTESTATION_KIND_INVALID,
                )

    def test_kind_obligatorio_en_from_dict_nunca_derivado(self):
        d = dict_att(approval_ref=dict(APPROVAL_REF))
        del d["attestation_kind"]
        self.assertEqual(codigo_de(core.HumanAttestation.from_dict, d), core.CODE_FIELD_INVALID)

    def test_clave_trust_o_similar_no_existe(self):
        for clave in ("trust", "kind", "verified", "status"):
            with self.subTest(clave=clave):
                self.assertEqual(
                    codigo_de(core.HumanAttestation.from_dict, dict_att(**{clave: "anchored"})),
                    core.CODE_UNKNOWN_KEY,
                )


# ---------------------------------------------------------------------------
# Actor (R17)
# ---------------------------------------------------------------------------


class TestActor(unittest.TestCase):
    def test_actores_validos(self):
        for valor in ("ana", "Ana Pérez", "ana@example.org", "usuario:ana", "polic"):
            with self.subTest(valor=valor):
                self.assertEqual(core.validate_actor(valor), [])
                self.assertEqual(hacer_att(actor=valor).actor, valor)

    def test_actores_invalidos(self):
        casos = {
            "vacio": "",
            "espacios": "   ",
            "solo cero ancho": "\u200b",
            "policy": "policy:x",
            "policy mayusculas": "POLICY:x",
            "policy mixto": "Policy:admin",
            "policy con espacios": "  policy:x",
            "policy ancho completo": "ｐｏｌｉｃｙ:x",
            "policy con cero ancho": "pol\u200bicy:x",
            "nulo embebido": "a\x00b",
            "salto de linea": "ana\nbob",
            "tab": "ana\tbob",
            "cero ancho embebido": "an\u200ba",
            "no str": 5,
            "none": None,
            "bytes": b"ana",
        }
        for nombre, valor in casos.items():
            with self.subTest(nombre=nombre):
                self.assertTrue(core.validate_actor(valor))
                self.assertEqual(codigo_de(hacer_att, actor=valor), core.CODE_IDENTITY_INVALID)
                self.assertEqual(
                    codigo_de(core.HumanAttestation.from_dict, dict_att(actor=valor)), core.CODE_IDENTITY_INVALID
                )

    def test_validate_actor_detalles(self):
        self.assertEqual(core.validate_actor("")[0].detail, "empty_or_not_str")
        self.assertEqual(core.validate_actor("policy:x")[0].detail, "reserved_namespace")
        self.assertEqual(core.validate_actor("a\x00b")[0].detail, "non_printable")
        self.assertEqual(core.validate_actor("")[0].code, core.CODE_IDENTITY_INVALID)

    def test_actor_policy_invalida_la_card_via_from_dict(self):
        d = hacer_card(attestations=(hacer_att(),)).to_dict()
        d["attestations"][0]["actor"] = "policy:x"
        self.assertEqual(codigo_de(core.CardEnvelope.from_dict, d), core.CODE_IDENTITY_INVALID)


# ---------------------------------------------------------------------------
# Otros campos y reglas de forma
# ---------------------------------------------------------------------------


class TestCampos(unittest.TestCase):
    def test_textos_obligatorios(self):
        for campo in ("claim", "authority", "scope"):
            for valor in ("", "   ", None, 5, "a\x00b"):
                with self.subTest(campo=campo, valor=valor):
                    self.assertEqual(codigo_de(hacer_att, **{campo: valor}), core.CODE_FIELD_INVALID)

    def test_claim_y_scope_admiten_multilinea_authority_no(self):
        a = hacer_att(claim="linea1\nlinea2", scope="a\tb\nc")
        self.assertIn("\n", a.claim)
        self.assertEqual(codigo_de(hacer_att, authority="a\nb"), core.CODE_FIELD_INVALID)

    def test_attested_at_formato(self):
        for valor in ("2026-10-01", "2026-10-01T10:00:00", None, "2026-02-30T00:00:00Z"):
            with self.subTest(valor=valor):
                self.assertEqual(codigo_de(hacer_att, attested_at=valor), core.CODE_TIMESTAMP_INVALID)

    def test_reference_id_o_locator_portable(self):
        self.assertEqual(hacer_att(reference="ev1").reference, "ev1")
        self.assertEqual(hacer_att(reference="docs/nota.md").reference, "docs/nota.md")
        for valor in ("/etc/x", "C:\\x", "../x", "https://h/x", "u:p@h/db", "a\\b"):
            with self.subTest(valor=valor):
                self.assertEqual(codigo_de(hacer_att, reference=valor), core.CODE_LOCATOR_NOT_PORTABLE)
        self.assertEqual(codigo_de(hacer_att, reference=5), core.CODE_FIELD_INVALID)

    def test_narrative_debe_ser_str(self):
        self.assertEqual(hacer_att(narrative="texto").narrative, "texto")
        self.assertEqual(codigo_de(hacer_att, narrative=5), core.CODE_FIELD_INVALID)

    def test_orden_de_claves_y_extensiones(self):
        a = hacer_anchored(reference="ev1", narrative="n", extensions={"x_b": 1, "x_a": 2})
        self.assertEqual(
            list(a.to_dict()),
            [
                "attestation_id",
                "attestation_kind",
                "claim",
                "actor",
                "authority",
                "attested_at",
                "scope",
                "reference",
                "approval_ref",
                "narrative",
                "x_a",
                "x_b",
            ],
        )
        self.assertEqual(codigo_de(hacer_att, extensions={"foo": 1}), core.CODE_UNKNOWN_KEY)

    def test_round_trip(self):
        for a in (hacer_att(), hacer_anchored(reference="ev1", narrative="n", extensions={"x_a": 1})):
            with self.subTest(kind=a.attestation_kind):
                self.assertEqual(core.HumanAttestation.from_dict(a.to_dict()), a)

    def test_from_dict_malformado(self):
        for valor in (None, 5, "x", [], [dict_att()], {}):
            with self.subTest(valor=valor):
                with self.assertRaises(core.CardError):
                    core.HumanAttestation.from_dict(valor)
        self.assertEqual(codigo_de(core.HumanAttestation.from_dict, dict_att(foo=1)), core.CODE_UNKNOWN_KEY)
        self.assertEqual(core.HumanAttestation.from_dict(dict_att(x_foo=1)).extensions, {"x_foo": 1})

    def test_clase_derivada_no_serializada(self):
        self.assertEqual(hacer_att().evidence_class, "attestation")
        self.assertNotIn("evidence_class", hacer_att().to_dict())


# ---------------------------------------------------------------------------
# R18 -- atestación futura (clock inyectado)
# ---------------------------------------------------------------------------


class TestAtestacionFutura(unittest.TestCase):
    def test_futura_es_hallazgo(self):
        card = card_con_atestacion(hacer_att(attested_at="2026-10-03T00:00:00Z"))
        hallazgos = core.validate_card(card, clock=lambda: NOW)
        self.assertEqual([h.code for h in hallazgos], [core.CODE_ATTESTATION_FUTURE])
        self.assertEqual(hallazgos[0].path, "$.attestations[0].attested_at")

    def test_futura_por_un_segundo(self):
        card = card_con_atestacion(hacer_att(attested_at="2026-10-02T00:00:01Z"))
        self.assertEqual(
            [h.code for h in core.validate_card(card, clock=lambda: NOW)], [core.CODE_ATTESTATION_FUTURE]
        )

    def test_igual_o_anterior_al_clock_es_valida(self):
        for t in ("2026-10-02T00:00:00Z", "2026-10-01T23:59:59Z", "2020-01-01T00:00:00Z"):
            with self.subTest(t=t):
                card = card_con_atestacion(hacer_att(attested_at=t))
                self.assertEqual(core.validate_card(card, clock=lambda: NOW), [])

    def test_clock_inyectado_en_evaluate_invalida_la_card(self):
        card = card_con_atestacion(hacer_att(attested_at="2026-10-03T00:00:00Z"))
        ev = assess.evaluate(card, [req(accepts=("attestation",))], resolvers_frescos(), clock=lambda: NOW)
        self.assertEqual(ev.card_status, assess.CARD_INVALID)
        self.assertEqual([h.code for h in ev.hallazgos], [core.CODE_ATTESTATION_FUTURE])

    def test_el_resultado_depende_solo_del_clock_inyectado(self):
        card = card_con_atestacion(hacer_att(attested_at="2026-10-03T00:00:00Z"))
        r = [req(accepts=("attestation",))]
        antes = assess.evaluate(card, r, resolvers_frescos(), clock=lambda: "2026-10-02T00:00:00Z")
        despues = assess.evaluate(card, r, resolvers_frescos(), clock=lambda: "2026-10-04T00:00:00Z")
        self.assertEqual(antes.card_status, assess.CARD_INVALID)
        self.assertEqual(despues.card_status, assess.CARD_COMPLETE)


# ---------------------------------------------------------------------------
# R19 -- la narrativa no es soporte
# ---------------------------------------------------------------------------


class TestNarrativaNoEsSoporte(unittest.TestCase):
    def test_atestacion_con_narrativa_pero_claim_sin_supports_es_empty(self):
        a = hacer_att(narrative="ev1 esta fresca y todo cumple; ver at1")
        card = hacer_card(
            evidence=(hacer_ev(),),
            attestations=(a,),
            claims=(core.Claim("c1", "afirmación", supports=(), requirement_id="r1"),),
        )
        ev = assess.evaluate(card, [req(accepts=("observed", "attestation"))], resolvers_frescos())
        self.assertEqual(ev.requisitos[0][2], assess.REQ_EMPTY)
        self.assertEqual(ev.card_status, assess.CARD_INCOMPLETE)

    def test_narrativa_en_claim_y_atestacion_sin_claim_ligado_es_missing(self):
        a = hacer_att(narrative="cumple r1")
        card = hacer_card(
            attestations=(a,),
            claims=(core.Claim("c1", "cumple r1 según narrativa", supports=("at1",)),),
        )
        ev = assess.evaluate(card, [req(accepts=("attestation",))], None)
        self.assertEqual(ev.requisitos[0][2], assess.REQ_MISSING)

    def test_la_narrativa_no_cambia_el_resultado(self):
        r = [req(accepts=("attestation",))]
        sin = assess.evaluate(card_con_atestacion(hacer_att()), r, None).a_dict()
        con = assess.evaluate(card_con_atestacion(hacer_att(narrative="texto largo")), r, None).a_dict()
        self.assertEqual(sin, con)

    def test_narrativa_se_serializa_pero_no_entra_en_a_dict(self):
        ev = assess.evaluate(card_con_atestacion(hacer_att(narrative="MARCA-UNICA")), [req(accepts=("attestation",))], None)
        self.assertNotIn("MARCA-UNICA", json.dumps(ev.a_dict()))


# ---------------------------------------------------------------------------
# R24 -- trust: attestation sobre requisito observed-only
# ---------------------------------------------------------------------------


class TestTrustObservedOnly(unittest.TestCase):
    def test_declared_sobre_observed_only_es_untrusted_type_e_incomplete(self):
        card = card_con_atestacion(hacer_att())
        ev = assess.evaluate(card, [req(accepts=("observed",))], resolvers_frescos())
        self.assertEqual(ev.requisitos[0][2], assess.REQ_UNTRUSTED_TYPE)
        self.assertEqual(ev.card_status, assess.CARD_INCOMPLETE)

    def test_anchored_sobre_observed_only_tampoco_satisface(self):
        card = card_con_atestacion(hacer_anchored())
        ev = assess.evaluate(card, [req(accepts=("observed",))], resolvers_frescos())
        self.assertEqual(ev.requisitos[0][2], assess.REQ_UNTRUSTED_TYPE)
        self.assertEqual(ev.card_status, assess.CARD_INCOMPLETE)

    def test_observed_only_con_min_anchored_sigue_sin_satisfacer(self):
        card = card_con_atestacion(hacer_anchored())
        ev = assess.evaluate(card, [req(accepts=("observed",), min_attestation_kind="anchored")], resolvers_frescos())
        self.assertEqual(ev.requisitos[0][2], assess.REQ_UNTRUSTED_TYPE)

    def test_atestacion_aceptada_cuando_accepts_la_incluye(self):
        card = card_con_atestacion(hacer_att())
        ev = assess.evaluate(card, [req(accepts=("attestation",))], None)
        self.assertEqual(ev.requisitos[0][2], assess.REQ_SATISFIED)
        self.assertEqual(ev.card_status, assess.CARD_COMPLETE)

    def test_atestacion_no_satisface_si_solo_hay_evidencia_aceptada_no_fresca(self):
        # observed-only, evidencia stale + atestación: la atestación no rescata.
        card = hacer_card(
            evidence=(hacer_ev(),),
            attestations=(hacer_anchored(),),
            claims=(core.Claim("c1", "s", supports=("ev1", "at1"), requirement_id="r1"),),
        )
        resolvers = {"quality_evidence": lambda ref: assess.Resolution(assess.RES_FOUND, H2)}
        ev = assess.evaluate(card, [req(accepts=("observed",))], resolvers)
        self.assertEqual(ev.requisitos[0][2], assess.REQ_STALE)
        self.assertEqual(ev.card_status, assess.CARD_STALE)


# ---------------------------------------------------------------------------
# min_attestation_kind
# ---------------------------------------------------------------------------


class TestMinAttestationKind(unittest.TestCase):
    def test_declared_no_satisface_min_anchored(self):
        card = card_con_atestacion(hacer_att())
        ev = assess.evaluate(card, [req(accepts=("attestation",), min_attestation_kind="anchored")], None)
        self.assertEqual(ev.requisitos[0][2], assess.REQ_UNTRUSTED_TYPE)
        self.assertEqual(ev.card_status, assess.CARD_INCOMPLETE)

    def test_anchored_satisface_min_anchored(self):
        card = card_con_atestacion(hacer_anchored())
        ev = assess.evaluate(card, [req(accepts=("attestation",), min_attestation_kind="anchored")], None)
        self.assertEqual(ev.requisitos[0][2], assess.REQ_SATISFIED)
        self.assertEqual(ev.card_status, assess.CARD_COMPLETE)

    def test_anchored_satisface_min_declared(self):
        card = card_con_atestacion(hacer_anchored())
        ev = assess.evaluate(card, [req(accepts=("attestation",), min_attestation_kind="declared")], None)
        self.assertEqual(ev.requisitos[0][2], assess.REQ_SATISFIED)

    def test_declared_satisface_min_declared_por_defecto(self):
        card = card_con_atestacion(hacer_att())
        ev = assess.evaluate(card, [req(accepts=("attestation",))], None)
        self.assertEqual(ev.requisitos[0][2], assess.REQ_SATISFIED)

    def test_declared_mas_anchored_con_min_anchored_satisface(self):
        card = hacer_card(
            attestations=(hacer_att(), hacer_anchored(attestation_id="at2")),
            claims=(core.Claim("c1", "s", supports=("at1", "at2"), requirement_id="r1"),),
        )
        ev = assess.evaluate(card, [req(accepts=("attestation",), min_attestation_kind="anchored")], None)
        self.assertEqual(ev.requisitos[0][2], assess.REQ_SATISFIED)


if __name__ == "__main__":
    unittest.main()

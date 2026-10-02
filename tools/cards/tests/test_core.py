"""Tests de `tools.cards.core` (R1, R5-R9, R14, R22, R23, R34; validate_card)."""
from __future__ import annotations

import ast
import os
import unittest

from tools.cards import core
from tools.datasources import core as datasources_core

H1 = "a" * 64
T0 = "2026-10-01T10:00:00Z"
NOW = "2026-10-02T00:00:00Z"


# ---------------------------------------------------------------------------
# Fixtures sintéticos en memoria
# ---------------------------------------------------------------------------


def codigo_de(funcion, *args, **kwargs):
    """Código del `CardError` lanzado por `funcion`; falla si no lanza."""
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


# ---------------------------------------------------------------------------
# R1 -- neutralidad
# ---------------------------------------------------------------------------


class TestNeutralidad(unittest.TestCase):
    def test_core_solo_importa_stdlib_permitido(self):
        permitidos = {"dataclasses", "datetime", "hashlib", "json", "re", "unicodedata", "typing", "__future__"}
        ruta = os.path.join(os.path.dirname(__file__), "..", "core.py")
        with open(ruta, "r", encoding="utf-8") as f:
            arbol = ast.parse(f.read(), filename="core.py")
        encontrados = set()
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Import):
                for alias in nodo.names:
                    encontrados.add(alias.name.split(".")[0])
            elif isinstance(nodo, ast.ImportFrom):
                self.assertEqual(nodo.level, 0, "import relativo en core.py")
                encontrados.add((nodo.module or "").split(".")[0])
        self.assertLessEqual(encontrados, permitidos)


# ---------------------------------------------------------------------------
# R5 -- card_id, ids reservados, paridad
# ---------------------------------------------------------------------------


class TestIds(unittest.TestCase):
    def test_patron_paridad_con_datasources(self):
        origen = datasources_core.SOURCE_ID_PATTERN
        origen = getattr(origen, "pattern", origen)
        self.assertEqual(core.CARD_ID_PATTERN, origen)

    def test_card_id_validos(self):
        for valor in ("a", "0abc", "a_b-c", "a" * 64, "card-1"):
            with self.subTest(valor=valor):
                self.assertEqual(hacer_card(card_id=valor).card_id, valor)

    def test_card_id_invalidos(self):
        for valor in ("", "A", "_a", "-a", "a" * 65, "a b", "a.b", "ñandu", "a/b", None, 5, ["a"]):
            with self.subTest(valor=valor):
                self.assertEqual(codigo_de(hacer_card, card_id=valor), core.CODE_ID_INVALID)

    def test_ids_reservados_rechazados(self):
        self.assertEqual(set(core.RESERVED_CARD_IDS), {"none", "null", "default", "status"})
        for valor in core.RESERVED_CARD_IDS:
            with self.subTest(valor=valor):
                self.assertEqual(codigo_de(hacer_card, card_id=valor), core.CODE_ID_INVALID)

    def test_ids_reservados_solo_como_prefijo_son_validos(self):
        self.assertEqual(hacer_card(card_id="status-card").card_id, "status-card")

    def test_ids_de_evidencia_claim_y_atestacion_usan_el_mismo_patron(self):
        self.assertEqual(codigo_de(hacer_ev, evidence_id="Ev 1"), core.CODE_ID_INVALID)
        self.assertEqual(codigo_de(hacer_att, attestation_id="At!"), core.CODE_ID_INVALID)
        self.assertEqual(codigo_de(core.Claim, claim_id="C 1", statement="s"), core.CODE_ID_INVALID)

    def test_card_id_estable_en_revisiones(self):
        a = hacer_card(title="uno")
        b = hacer_card(title="dos")
        self.assertEqual(a.card_id, b.card_id)
        self.assertNotEqual(a.revision_id(), b.revision_id())


# ---------------------------------------------------------------------------
# R7 -- schema_version
# ---------------------------------------------------------------------------


class TestSchemaVersion(unittest.TestCase):
    def test_from_dict_schema_desconocido_falla_cerrado(self):
        base = hacer_card().to_dict()
        for valor in (2, 0, 99, -1):
            with self.subTest(valor=valor):
                d = dict(base, schema_version=valor)
                self.assertEqual(codigo_de(core.CardEnvelope.from_dict, d), core.CODE_SCHEMA_UNSUPPORTED)

    def test_schema_desconocido_se_reporta_antes_que_otras_validaciones(self):
        # Card con otros problemas: igualmente el primer error es el de schema.
        d = {"schema_version": 7, "basura": 1}
        self.assertEqual(codigo_de(core.CardEnvelope.from_dict, d), core.CODE_SCHEMA_UNSUPPORTED)

    def test_schema_tipo_erroneo_o_ausente(self):
        base = hacer_card().to_dict()
        for valor in ("1", 1.0, True, None):
            with self.subTest(valor=valor):
                self.assertEqual(
                    codigo_de(core.CardEnvelope.from_dict, dict(base, schema_version=valor)), core.CODE_FIELD_INVALID
                )
        sin = dict(base)
        del sin["schema_version"]
        self.assertEqual(codigo_de(core.CardEnvelope.from_dict, sin), core.CODE_FIELD_INVALID)

    def test_validate_card_reporta_schema_no_soportado(self):
        card = hacer_card(schema_version=2)
        codigos = [h.code for h in core.validate_card(card)]
        self.assertIn(core.CODE_SCHEMA_UNSUPPORTED, codigos)

    def test_schema_actual_es_1(self):
        self.assertEqual(core.SCHEMA_VERSION, 1)
        self.assertEqual(core.validate_card(hacer_card()), [])

    def test_kind_schema_version_minimo_1(self):
        for valor in (0, -1, "1", None, True):
            with self.subTest(valor=valor):
                self.assertEqual(codigo_de(hacer_card, kind_schema_version=valor), core.CODE_FIELD_INVALID)


# ---------------------------------------------------------------------------
# R6, R8 -- envelope
# ---------------------------------------------------------------------------


class TestEnvelope(unittest.TestCase):
    def test_card_kinds_reservados(self):
        self.assertEqual(core.CARD_KINDS, ("data_card", "model_card"))
        self.assertEqual(hacer_card(card_kind="model_card").card_kind, "model_card")
        for valor in ("dataset_card", "", None, 3):
            with self.subTest(valor=valor):
                self.assertEqual(codigo_de(hacer_card, card_kind=valor), core.CODE_FIELD_INVALID)

    def test_title_vacio_o_no_imprimible(self):
        for valor in ("", "   ", "a\x00b", "a\u200bb", None):
            with self.subTest(valor=valor):
                self.assertEqual(codigo_de(hacer_card, title=valor), core.CODE_FIELD_INVALID)

    def test_subject_es_identificador_logico_no_ruta_fisica(self):
        for valor in ("C:\\datos\\x", "/etc/passwd", "~/x", "a\\b", "../x", "a/../b", "postgres://u:p@h/db", "u:p@h"):
            with self.subTest(valor=valor):
                self.assertEqual(codigo_de(hacer_card, subject=valor), core.CODE_LOCATOR_NOT_PORTABLE)
        self.assertEqual(codigo_de(hacer_card, subject=""), core.CODE_FIELD_INVALID)
        self.assertEqual(codigo_de(hacer_card, subject=" x"), core.CODE_FIELD_INVALID)

    def test_timestamps_formato_fijo(self):
        malos = (
            "2026-10-01",
            "2026-10-01T10:00:00",
            "2026-10-01T10:00:00.123Z",
            "2026-10-01 10:00:00Z",
            "2026-02-30T10:00:00Z",
            "2026-13-01T10:00:00Z",
            "2026-10-01T25:00:00Z",
            None,
            5,
        )
        for valor in malos:
            with self.subTest(valor=valor):
                self.assertFalse(core.es_timestamp_valido(valor))
                self.assertEqual(codigo_de(hacer_card, created_at=valor), core.CODE_TIMESTAMP_INVALID)
                self.assertEqual(codigo_de(hacer_card, generated_at=valor), core.CODE_TIMESTAMP_INVALID)
        self.assertTrue(core.es_timestamp_valido(T0))

    def test_colecciones_deben_ser_tuplas_o_listas_tipadas(self):
        self.assertEqual(codigo_de(hacer_card, evidence="ev1"), core.CODE_FIELD_INVALID)
        self.assertEqual(codigo_de(hacer_card, evidence=(object(),)), core.CODE_FIELD_INVALID)
        self.assertEqual(codigo_de(hacer_card, evidence=(hacer_att(),)), core.CODE_FIELD_INVALID)
        self.assertEqual(codigo_de(hacer_card, attestations=(hacer_ev(),)), core.CODE_FIELD_INVALID)
        self.assertEqual(codigo_de(hacer_card, claims=({"claim_id": "c"},)), core.CODE_FIELD_INVALID)
        self.assertEqual(codigo_de(hacer_card, evidence=None), core.CODE_FIELD_INVALID)

    def test_listas_se_normalizan_a_tupla(self):
        card = hacer_card(evidence=[hacer_ev()], attestations=[hacer_att(attestation_id="at2")])
        self.assertIsInstance(card.evidence, tuple)
        self.assertIsInstance(card.attestations, tuple)

    def test_body_debe_ser_objeto_json(self):
        self.assertEqual(codigo_de(hacer_card, body=[]), core.CODE_BODY_INVALID)
        self.assertEqual(codigo_de(hacer_card, body=None), core.CODE_BODY_INVALID)
        self.assertEqual(codigo_de(hacer_card, body={"a": {1, 2}}), core.CODE_FIELD_INVALID)
        self.assertEqual(codigo_de(hacer_card, body={"a": float("nan")}), core.CODE_FIELD_INVALID)
        self.assertEqual(codigo_de(hacer_card, body={1: "x"}), core.CODE_FIELD_INVALID)
        self.assertEqual(hacer_card(body={"a": (1, 2)}).body, {"a": [1, 2]})

    def test_extensions_requieren_prefijo(self):
        self.assertEqual(hacer_card(extensions={"x_a": 1}).extensions, {"x_a": 1})
        self.assertEqual(codigo_de(hacer_card, extensions={"foo": 1}), core.CODE_UNKNOWN_KEY)
        self.assertEqual(codigo_de(hacer_card, extensions=[]), core.CODE_FIELD_INVALID)

    def test_envelope_es_inmutable(self):
        card = hacer_card()
        with self.assertRaises(Exception):
            card.title = "otro"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# R14, R22 -- ids duplicados, soporte colgante
# ---------------------------------------------------------------------------


class TestIdsDuplicadosYSoporteColgante(unittest.TestCase):
    def _codigos(self, card, **kw):
        return [h.code for h in core.validate_card(card, **kw)]

    def test_ids_duplicados_entre_evidencias(self):
        card = hacer_card(evidence=(hacer_ev(), hacer_ev(ref_id="qe-2")))
        hallazgos = core.validate_card(card)
        self.assertEqual([h.code for h in hallazgos], [core.CODE_DUPLICATE_ID])
        self.assertEqual(hallazgos[0].path, "$.evidence[1].evidence_id")

    def test_ids_duplicados_entre_atestaciones(self):
        card = hacer_card(attestations=(hacer_att(), hacer_att()))
        self.assertEqual(self._codigos(card), [core.CODE_DUPLICATE_ID])

    def test_id_duplicado_entre_evidencia_y_atestacion(self):
        card = hacer_card(evidence=(hacer_ev(evidence_id="x1"),), attestations=(hacer_att(attestation_id="x1"),))
        hallazgos = core.validate_card(card)
        self.assertEqual([h.code for h in hallazgos], [core.CODE_DUPLICATE_ID])
        self.assertEqual(hallazgos[0].path, "$.attestations[0].attestation_id")

    def test_claim_id_duplicado(self):
        claims = (core.Claim("c1", "uno"), core.Claim("c1", "dos"))
        self.assertEqual(self._codigos(hacer_card(claims=claims)), [core.CODE_DUPLICATE_ID])

    def test_soporte_colgante(self):
        card = hacer_card(claims=(core.Claim("c1", "s", supports=("nope",)),))
        hallazgos = core.validate_card(card)
        self.assertEqual([h.code for h in hallazgos], [core.CODE_DANGLING_SUPPORT])
        self.assertEqual(hallazgos[0].path, "$.claims[0].supports[0]")

    def test_soporte_valido_a_evidencia_y_a_atestacion(self):
        card = hacer_card(
            evidence=(hacer_ev(),),
            attestations=(hacer_att(),),
            claims=(core.Claim("c1", "s", supports=("ev1", "at1")),),
        )
        self.assertEqual(core.validate_card(card), [])

    def test_soporte_no_puede_ser_otro_claim(self):
        card = hacer_card(claims=(core.Claim("c1", "s"), core.Claim("c2", "s", supports=("c1",))))
        self.assertEqual(self._codigos(card), [core.CODE_DANGLING_SUPPORT])

    def test_claim_supports_debe_ser_secuencia_de_ids(self):
        self.assertEqual(codigo_de(core.Claim, "c1", "s", supports="ev1"), core.CODE_FIELD_INVALID)
        self.assertEqual(codigo_de(core.Claim, "c1", "s", supports=("Bad Id",)), core.CODE_ID_INVALID)
        self.assertEqual(codigo_de(core.Claim, "c1", "   "), core.CODE_FIELD_INVALID)
        self.assertEqual(core.Claim("c1", "s", supports=["a", "b"]).supports, ("a", "b"))

    def test_claim_to_dict_omite_requirement_id_ausente(self):
        self.assertEqual(list(core.Claim("c1", "s").to_dict()), ["claim_id", "statement", "supports"])
        d = core.Claim("c1", "s", requirement_id="r1").to_dict()
        self.assertEqual(list(d), ["claim_id", "requirement_id", "statement", "supports"])


# ---------------------------------------------------------------------------
# validate_card: clock, body, tipo
# ---------------------------------------------------------------------------


class TestValidateCard(unittest.TestCase):
    def test_no_lanza_con_entradas_que_no_son_card(self):
        for valor in (None, {}, "x", 5, [hacer_card()]):
            with self.subTest(valor=valor):
                hallazgos = core.validate_card(valor)
                self.assertEqual([h.code for h in hallazgos], [core.CODE_FIELD_INVALID])

    def test_body_sin_validador_debe_ser_vacio(self):
        card = hacer_card(body={"a": 1})
        self.assertEqual([h.code for h in core.validate_card(card)], [core.CODE_BODY_INVALID])
        self.assertEqual(core.validate_card(hacer_card(body={})), [])

    def test_body_con_validador_inyectado(self):
        card = hacer_card(body={"a": 1})
        self.assertEqual(core.validate_card(card, validate_body=lambda b: []), [])
        h = core.validate_card(card, validate_body=lambda b: [("CARD-BODY-INVALID", "$.body.a", "mal")])
        self.assertEqual([x.as_tuple() for x in h], [("CARD-BODY-INVALID", "$.body.a", "mal")])

    def test_validador_que_lanza_o_devuelve_basura_es_hallazgo(self):
        card = hacer_card(body={"a": 1})

        def lanza(_b):
            raise RuntimeError("boom")

        for validador in (lanza, lambda b: None, lambda b: "texto", lambda b: [object()]):
            with self.subTest(validador=validador):
                hallazgos = core.validate_card(card, validate_body=validador)
                self.assertTrue(hallazgos)
                self.assertTrue(all(h.code == core.CODE_BODY_INVALID for h in hallazgos))

    def test_clock_invalido_o_que_lanza_es_hallazgo_y_no_propaga(self):
        card = hacer_card(attestations=(hacer_att(),))

        def lanza():
            raise RuntimeError("sin reloj")

        for reloj in (lanza, lambda: "ayer", lambda: None, lambda: 5):
            with self.subTest(reloj=reloj):
                hallazgos = core.validate_card(card, clock=reloj)
                self.assertEqual([h.code for h in hallazgos], [core.CODE_TIMESTAMP_INVALID])

    def test_sin_clock_no_se_chequea_atestacion_futura(self):
        card = hacer_card(attestations=(hacer_att(attested_at="2999-01-01T00:00:00Z"),))
        self.assertEqual(core.validate_card(card), [])

    def test_hallazgo_as_tuple(self):
        h = core.Hallazgo("CARD-X", "$.p", "d")
        self.assertEqual(h.as_tuple(), ("CARD-X", "$.p", "d"))


# ---------------------------------------------------------------------------
# R23 -- Requirement
# ---------------------------------------------------------------------------


class TestRequirement(unittest.TestCase):
    def test_valido_y_defaults(self):
        r = core.Requirement("r1", "required", ["observed"])
        self.assertEqual(r.accepts, ("observed",))
        self.assertIsNone(r.accepted_kinds)
        self.assertEqual(r.min_attestation_kind, "declared")

    def test_severity_invalida(self):
        for valor in ("blocker", "", None, "REQUIRED"):
            with self.subTest(valor=valor):
                self.assertEqual(codigo_de(core.Requirement, "r1", valor, ("observed",)), core.CODE_FIELD_INVALID)

    def test_accepts_vacio_o_invalido(self):
        self.assertEqual(codigo_de(core.Requirement, "r1", "required", ()), core.CODE_FIELD_INVALID)
        self.assertEqual(codigo_de(core.Requirement, "r1", "required", ("trust",)), core.CODE_FIELD_INVALID)
        self.assertEqual(codigo_de(core.Requirement, "r1", "required", "observed"), core.CODE_FIELD_INVALID)

    def test_accepted_kinds_subconjunto_de_observed_kinds(self):
        r = core.Requirement("r1", "required", ("observed",), accepted_kinds=["quality_evidence"])
        self.assertEqual(r.accepted_kinds, ("quality_evidence",))
        self.assertEqual(
            codigo_de(core.Requirement, "r1", "required", ("observed",), accepted_kinds=("bogus",)),
            core.CODE_FIELD_INVALID,
        )

    def test_min_attestation_kind_invalido(self):
        for valor in ("hybrid", "", None, "Anchored"):
            with self.subTest(valor=valor):
                self.assertEqual(
                    codigo_de(core.Requirement, "r1", "required", ("attestation",), min_attestation_kind=valor),
                    core.CODE_ATTESTATION_KIND_INVALID,
                )


# ---------------------------------------------------------------------------
# Registro de códigos
# ---------------------------------------------------------------------------


class TestCodes(unittest.TestCase):
    def test_codes_unicos_y_con_prefijo(self):
        self.assertEqual(len(core.CODES), len(set(core.CODES)))
        for c in core.CODES:
            self.assertTrue(c.startswith("CARD-"))

    def test_todas_las_constantes_code_estan_registradas(self):
        constantes = {v for k, v in vars(core).items() if k.startswith("CODE_") and isinstance(v, str)}
        self.assertEqual(constantes, set(core.CODES))

    def test_card_error_expone_code_y_message(self):
        exc = core.CardError(core.CODE_ID_INVALID, "detalle")
        self.assertEqual(exc.code, "CARD-ID-INVALID")
        self.assertEqual(exc.message, "detalle")
        self.assertIn("CARD-ID-INVALID", str(exc))


if __name__ == "__main__":
    unittest.main()

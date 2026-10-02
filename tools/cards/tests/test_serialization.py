"""Tests de serialización de Cards (R9, R11, R34, R36-R40): round-trip, hash,
revision_id, `status` no persistido, `write_card` / `read_card`."""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import re
import tempfile
import unittest
from unittest import mock

from tools.cards import assess, core
from tools.datasources import core as datasources_core

H1 = "a" * 64
H2 = "b" * 64
T0 = "2026-10-01T10:00:00Z"
T1 = "2026-10-01T11:00:00Z"
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


def reloj():
    return NOW


def card_completa(created_at=T0, generated_at=T0, pinned_at=T0, attested_at=T0, **extra):
    """Card sintética con evidencia, ambos tipos de atestación y claims."""
    evidencia = (
        core.EvidenceRef(
            evidence_id="ev1",
            kind="quality_evidence",
            ref_id="qe-1",
            content_sha256=H1,
            pinned_at=pinned_at,
            member="metrica_a",
            schema_version=1,
            locator="reports/qe-1.json",
            extensions={"x_origen": "sintetico"},
        ),
        core.EvidenceRef(
            evidence_id="ev2",
            kind="source_provenance",
            ref_id="fuente__0123456789ab",
            content_sha256=H2,
            pinned_at=pinned_at,
            member="provenance",
        ),
    )
    atestaciones = (
        core.HumanAttestation(
            attestation_id="at1",
            claim="declaro X",
            actor="ana",
            authority="owner",
            attested_at=attested_at,
            scope="alcance",
            attestation_kind="declared",
            narrative="texto libre",
        ),
        core.HumanAttestation(
            attestation_id="at2",
            claim="aprobado",
            actor="bruno",
            authority="steward",
            attested_at=attested_at,
            scope="alcance",
            attestation_kind="anchored",
            approval_ref=dict(APPROVAL_REF),
            reference="ev1",
        ),
    )
    claims = (
        core.Claim("c1", "calidad ok", supports=("ev1", "ev2"), requirement_id="r1"),
        core.Claim("c2", "responsable", supports=("at1", "at2"), requirement_id="r2"),
    )
    base = dict(
        schema_version=1,
        card_kind="data_card",
        kind_schema_version=1,
        card_id="card-a",
        title="Titulo ñ",
        subject="sujeto-logico",
        created_at=created_at,
        generated_at=generated_at,
        evidence=evidencia,
        attestations=atestaciones,
        claims=claims,
        body={},
        extensions={"x_nota": [1, 2, {"k": None}]},
    )
    base.update(extra)
    return core.CardEnvelope(**base)


def requisitos():
    return [
        core.Requirement("r1", "required", ("observed",)),
        core.Requirement("r2", "required", ("attestation",), min_attestation_kind="anchored"),
    ]


def resolvers_frescos():
    return {k: (lambda ref: assess.Resolution(assess.RES_FOUND, ref.content_sha256)) for k in core.OBSERVED_KINDS}


# ---------------------------------------------------------------------------
# R37 -- canonical_json / content_sha256
# ---------------------------------------------------------------------------


class TestCanonicalJson(unittest.TestCase):
    def test_vector_fijo(self):
        obj = {"b": 1, "a": [1, "é", None, True], "c": {"z": 1.5, "y": "x"}}
        esperado = '{"a":[1,"é",null,true],"b":1,"c":{"y":"x","z":1.5}}'
        self.assertEqual(core.canonical_json(obj), esperado)
        self.assertEqual(core.content_sha256(obj), hashlib.sha256(esperado.encode("utf-8")).hexdigest())

    def test_paridad_byte_a_byte_con_datasources(self):
        muestras = [{}, [], {"b": 1, "a": 2}, {"k": "ñandú 日本"}, [1, 2.5, None, False], {"a": {"b": {"c": [1]}}}]
        for obj in muestras:
            with self.subTest(obj=obj):
                self.assertEqual(core.canonical_json(obj), datasources_core.canonical_json(obj))
                self.assertEqual(core.content_sha256(obj), datasources_core.content_sha256(obj))

    def test_no_serializable_es_card_error(self):
        for obj in ({"a": float("nan")}, {"a": float("inf")}, {"a": {1, 2}}, {"a": object()}):
            with self.subTest(obj=obj):
                self.assertEqual(codigo_de(core.canonical_json, obj), core.CODE_FIELD_INVALID)


# ---------------------------------------------------------------------------
# R36 / R38 -- to_dict, from_dict, round-trip
# ---------------------------------------------------------------------------


class TestRoundTrip(unittest.TestCase):
    def test_round_trip_dict(self):
        card = card_completa()
        self.assertEqual(core.CardEnvelope.from_dict(card.to_dict()), card)

    def test_round_trip_con_revision_y_via_json(self):
        card = card_completa()
        d = json.loads(json.dumps(card.to_dict(con_revision=True)))
        self.assertEqual(core.CardEnvelope.from_dict(d), card)

    def test_round_trip_con_body_no_vacio(self):
        card = card_completa(body={"a": [1, {"b": None}], "c": "ñ"})
        self.assertEqual(core.CardEnvelope.from_dict(card.to_dict()), card)

    def test_round_trip_idempotente_del_hash(self):
        card = card_completa()
        otra = core.CardEnvelope.from_dict(json.loads(json.dumps(card.to_dict())))
        self.assertEqual(otra.content_sha256(), card.content_sha256())
        self.assertEqual(otra.revision_id(), card.revision_id())
        self.assertEqual(otra.to_dict(), card.to_dict())

    def test_orden_fijo_de_claves(self):
        d = card_completa().to_dict(con_revision=True)
        self.assertEqual(
            list(d),
            [
                "schema_version", "card_kind", "kind_schema_version", "card_id", "title", "subject",
                "created_at", "generated_at", "evidence", "attestations", "claims", "body", "extensions",
                "revision_id",
            ],
        )

    def test_to_dict_es_json_puro(self):
        json.dumps(card_completa().to_dict(con_revision=True), allow_nan=False)

    def test_to_dict_devuelve_copias(self):
        card = card_completa(body={"a": [1]})
        d = card.to_dict()
        d["body"]["a"].append(2)
        d["extensions"]["x_nuevo"] = 1
        d["evidence"][0]["ref_id"] = "otro"
        self.assertEqual(card.body, {"a": [1]})
        self.assertNotIn("x_nuevo", card.extensions)
        self.assertEqual(card.evidence[0].ref_id, "qe-1")


class TestStatusNoSerializado(unittest.TestCase):
    def test_status_no_esta_en_el_dict_ni_en_el_envelope(self):
        card = card_completa()
        d = card.to_dict(con_revision=True)
        for clave in ("status", "card_status", "state"):
            self.assertNotIn(clave, d)
        self.assertNotIn("status", {f.name for f in dataclasses.fields(core.CardEnvelope)})
        self.assertFalse(hasattr(card, "status"))

    def test_status_en_el_dict_de_entrada_se_rechaza(self):
        for valor in ("complete", "incomplete", None, 1):
            with self.subTest(valor=valor):
                d = dict(card_completa().to_dict(), status=valor)
                self.assertEqual(codigo_de(core.CardEnvelope.from_dict, d), core.CODE_UNKNOWN_KEY)

    def test_status_en_el_json_de_archivo_se_rechaza(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = os.path.join(tmp, "card.json")
            d = card_completa().to_dict(con_revision=True)
            d["status"] = "complete"
            with open(ruta, "w", encoding="utf-8") as f:
                json.dump(d, f)
            self.assertEqual(codigo_de(assess.read_card, ruta), core.CODE_UNKNOWN_KEY)

    def test_archivo_escrito_no_contiene_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = os.path.join(tmp, "card.json")
            assess.write_card(ruta, card_completa(), clock=reloj)
            with open(ruta, "r", encoding="utf-8") as f:
                texto = f.read()
            datos = json.loads(texto)
            self.assertNotIn("status", datos)
            self.assertNotIn("card_status", datos)
            self.assertNotIn('"status"', texto)

    def test_claves_del_envelope_son_las_del_contrato(self):
        d = card_completa().to_dict()
        self.assertEqual(set(d), set(core._ENVELOPE_CLAVES))


# ---------------------------------------------------------------------------
# R9 -- revision_id, content_sha256
# ---------------------------------------------------------------------------


class TestRevisionId(unittest.TestCase):
    def test_formato_y_composicion(self):
        card = card_completa()
        self.assertRegex(card.revision_id(), r"^card-a__[0-9a-f]{12}$")
        self.assertEqual(card.revision_id(), "card-a__" + card.content_sha256()[:12])
        self.assertRegex(card.content_sha256(), r"^[0-9a-f]{64}$")

    def test_idempotente(self):
        a, b = card_completa(), card_completa()
        self.assertEqual(a.revision_id(), a.revision_id())
        self.assertEqual(a.revision_id(), b.revision_id())
        self.assertEqual(a.content_sha256(), b.content_sha256())

    def test_misma_card_serializada_dos_veces_mismo_revision_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            r1, r2 = os.path.join(tmp, "a.json"), os.path.join(tmp, "b.json")
            assess.write_card(r1, card_completa(), clock=reloj)
            assess.write_card(r2, card_completa(), clock=reloj)
            with open(r1, "rb") as f1, open(r2, "rb") as f2:
                self.assertEqual(f1.read(), f2.read())
            self.assertEqual(assess.read_card(r1).revision_id(), assess.read_card(r2).revision_id())

    def test_content_sha256_excluye_generated_at(self):
        a = card_completa(generated_at=T0)
        b = card_completa(generated_at=T1)
        self.assertNotEqual(a.to_dict(), b.to_dict())
        self.assertEqual(a.content_sha256(), b.content_sha256())
        self.assertEqual(a.revision_id(), b.revision_id())

    def test_content_sha256_incluye_pinned_at(self):
        self.assertNotEqual(card_completa(pinned_at=T0).content_sha256(), card_completa(pinned_at=T1).content_sha256())
        self.assertNotEqual(card_completa(pinned_at=T0).revision_id(), card_completa(pinned_at=T1).revision_id())

    def test_content_sha256_incluye_attested_at(self):
        self.assertNotEqual(
            card_completa(attested_at=T0).content_sha256(), card_completa(attested_at=T1).content_sha256()
        )

    def test_content_sha256_incluye_created_at(self):
        self.assertNotEqual(card_completa(created_at=T0).content_sha256(), card_completa(created_at=T1).content_sha256())

    def test_content_sha256_cambia_con_el_contenido(self):
        base = card_completa()
        self.assertNotEqual(base.content_sha256(), card_completa(title="otro").content_sha256())
        self.assertNotEqual(base.content_sha256(), card_completa(extensions={"x_nota": 2}).content_sha256())

    def test_revision_id_no_participa_del_hash(self):
        card = card_completa()
        self.assertEqual(
            card.content_sha256(),
            core.content_sha256({k: v for k, v in card.to_dict().items() if k != "generated_at"}),
        )

    def test_revision_declarada_que_coincide_se_acepta(self):
        card = card_completa()
        d = card.to_dict(con_revision=True)
        self.assertEqual(core.CardEnvelope.from_dict(d), card)

    def test_revision_declarada_que_no_coincide_es_mismatch(self):
        d = card_completa().to_dict(con_revision=True)
        for malo in ("card-a__000000000000", "otra__" + d["revision_id"].split("__")[1], "", None, 5, ["x"]):
            with self.subTest(malo=malo):
                self.assertEqual(
                    codigo_de(core.CardEnvelope.from_dict, dict(d, revision_id=malo)), core.CODE_REVISION_MISMATCH
                )

    def test_contenido_editado_con_revision_vieja_es_mismatch(self):
        d = card_completa().to_dict(con_revision=True)
        d["title"] = "Titulo editado a mano"
        self.assertEqual(codigo_de(core.CardEnvelope.from_dict, d), core.CODE_REVISION_MISMATCH)

    def test_revision_mismatch_en_archivo(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = os.path.join(tmp, "card.json")
            assess.write_card(ruta, card_completa(), clock=reloj)
            with open(ruta, "r", encoding="utf-8") as f:
                datos = json.load(f)
            datos["evidence"][0]["content_sha256"] = "c" * 64
            with open(ruta, "w", encoding="utf-8") as f:
                json.dump(datos, f)
            self.assertEqual(codigo_de(assess.read_card, ruta), core.CODE_REVISION_MISMATCH)

    def test_generated_at_editado_no_dispara_mismatch(self):
        d = card_completa().to_dict(con_revision=True)
        d["generated_at"] = T1
        self.assertEqual(core.CardEnvelope.from_dict(d).generated_at, T1)


# ---------------------------------------------------------------------------
# R40 -- sin rutas absolutas, DSN ni secretos en lo serializado
# ---------------------------------------------------------------------------


class TestSinRutasNiSecretos(unittest.TestCase):
    def test_strings_de_ids_y_locators_serializados_son_portables(self):
        d = card_completa().to_dict()
        textos = []
        for e in d["evidence"]:
            textos += [e["evidence_id"], e["ref_id"], e.get("member", "x"), e.get("locator", "x")]
        textos += [d["card_id"], d["subject"]]
        for t in textos:
            self.assertFalse(t.startswith("/"))
            self.assertNotIn("\\", t)
            self.assertNotIn("://", t)
            self.assertIsNone(re.search(r"^[A-Za-z]:", t))
            self.assertNotIn("..", t.split("/"))

    def test_intentos_de_colar_rutas_o_dsn_fallan(self):
        d = card_completa().to_dict()
        for campo, valor in (("ref_id", "C:\\datos\\x"), ("locator", "/abs/x"), ("member", "postgres://u:p@h/db")):
            with self.subTest(campo=campo):
                malo = json.loads(json.dumps(d))
                malo["evidence"][0][campo] = valor
                self.assertEqual(codigo_de(core.CardEnvelope.from_dict, malo), core.CODE_LOCATOR_NOT_PORTABLE)
        malo = json.loads(json.dumps(d))
        malo["subject"] = "/home/user/data.csv"
        self.assertEqual(codigo_de(core.CardEnvelope.from_dict, malo), core.CODE_LOCATOR_NOT_PORTABLE)


# ---------------------------------------------------------------------------
# Entradas malformadas -> CardError (fail-closed)
# ---------------------------------------------------------------------------


class TestEntradasMalformadas(unittest.TestCase):
    def test_no_dict(self):
        for valor in (None, 5, 1.5, "x", [], [card_completa().to_dict()], (), True, b"{}"):
            with self.subTest(valor=valor):
                with self.assertRaises(core.CardError):
                    core.CardEnvelope.from_dict(valor)

    def test_dict_vacio_y_claves_faltantes(self):
        self.assertEqual(codigo_de(core.CardEnvelope.from_dict, {}), core.CODE_FIELD_INVALID)
        base = card_completa().to_dict()
        for clave in core._ENVELOPE_CLAVES:
            with self.subTest(clave=clave):
                d = dict(base)
                del d[clave]
                with self.assertRaises(core.CardError):
                    core.CardEnvelope.from_dict(d)

    def test_tipos_erroneos_por_clave(self):
        base = card_completa().to_dict()
        malos = {
            "card_kind": ["data_card"],
            "kind_schema_version": "1",
            "card_id": 5,
            "title": None,
            "subject": 5,
            "created_at": 20261001,
            "generated_at": None,
            "evidence": "ev1",
            "attestations": {"at1": 1},
            "claims": 5,
            "body": [],
            "extensions": [],
        }
        for clave, valor in malos.items():
            with self.subTest(clave=clave):
                with self.assertRaises(core.CardError):
                    core.CardEnvelope.from_dict(dict(base, **{clave: valor}))

    def test_elementos_de_colecciones_malformados(self):
        base = card_completa().to_dict()
        for clave in ("evidence", "attestations", "claims"):
            for malo in (None, 5, "x", [], [None]):
                with self.subTest(clave=clave, malo=malo):
                    with self.assertRaises(core.CardError):
                        core.CardEnvelope.from_dict(dict(base, **{clave: [malo]}))

    def test_claves_desconocidas_salvo_x(self):
        base = card_completa().to_dict()
        for clave in ("foo", "payload", "X_a", "xa", "extra"):
            with self.subTest(clave=clave):
                self.assertEqual(codigo_de(core.CardEnvelope.from_dict, dict(base, **{clave: 1})), core.CODE_UNKNOWN_KEY)

    def test_claves_x_aceptadas_en_los_objetos_anidados(self):
        base = card_completa().to_dict()
        base["evidence"][0]["x_extra"] = {"k": 1}
        base["attestations"][0]["x_extra"] = 1
        base["claims"][0]["x_extra"] = [1]
        card = core.CardEnvelope.from_dict(base)
        self.assertEqual(card.evidence[0].extensions["x_extra"], {"k": 1})
        self.assertEqual(card.to_dict()["claims"][0]["x_extra"], [1])

    def test_clave_no_str(self):
        d = card_completa().to_dict()
        d[1] = "x"
        self.assertEqual(codigo_de(core.CardEnvelope.from_dict, d), core.CODE_UNKNOWN_KEY)

    def test_body_no_json(self):
        base = card_completa().to_dict()
        for body in ({"a": {1, 2}}, {"a": object()}, {"a": float("nan")}, {1: "x"}):
            with self.subTest(body=body):
                with self.assertRaises(core.CardError):
                    core.CardEnvelope.from_dict(dict(base, body=body))

    def test_anidamiento_excesivo_es_card_error(self):
        profundo: list = []
        actual = profundo
        for _ in range(5000):
            nuevo: list = []
            actual.append(nuevo)
            actual = nuevo
        base = card_completa().to_dict()
        with self.assertRaises(core.CardError):
            core.CardEnvelope.from_dict(dict(base, body={"a": profundo}))

    def test_nunca_excepcion_cruda(self):
        base = card_completa().to_dict()
        raros = (object(), lambda: 1, {1, 2}, 1 + 2j, bytearray(b"x"), float("nan"))
        for clave in core._ENVELOPE_CLAVES:
            for raro in raros:
                if clave == "schema_version":
                    continue
                with self.subTest(clave=clave, raro=type(raro).__name__):
                    try:
                        core.CardEnvelope.from_dict(dict(base, **{clave: raro}))
                    except core.CardError:
                        pass


# ---------------------------------------------------------------------------
# Serialize -> deserialize -> evaluate
# ---------------------------------------------------------------------------


class TestSerializarDeserializarEvaluar(unittest.TestCase):
    def test_mismo_a_dict_antes_y_despues_de_archivo(self):
        card = card_completa()
        antes = assess.evaluate(card, requisitos(), resolvers_frescos(), clock=reloj).a_dict()
        self.assertEqual(antes["card_status"], assess.CARD_COMPLETE)
        with tempfile.TemporaryDirectory() as tmp:
            ruta = os.path.join(tmp, "card.json")
            assess.write_card(ruta, card, clock=reloj)
            leida = assess.read_card(ruta)
        despues = assess.evaluate(leida, requisitos(), resolvers_frescos(), clock=reloj).a_dict()
        self.assertEqual(antes, despues)
        self.assertEqual(json.dumps(antes, sort_keys=True), json.dumps(despues, sort_keys=True))

    def test_mismo_a_dict_via_dict_en_memoria(self):
        card = card_completa()
        otra = core.CardEnvelope.from_dict(json.loads(json.dumps(card.to_dict())))
        a = assess.evaluate(card, requisitos(), None, clock=reloj).a_dict()
        b = assess.evaluate(otra, requisitos(), None, clock=reloj).a_dict()
        self.assertEqual(a, b)

    def test_a_dict_determinista_en_corridas_repetidas(self):
        card = card_completa()
        vistos = {json.dumps(assess.evaluate(card, requisitos(), resolvers_frescos(), reloj).a_dict(), sort_keys=True) for _ in range(3)}
        self.assertEqual(len(vistos), 1)


# ---------------------------------------------------------------------------
# write_card (R39)
# ---------------------------------------------------------------------------


class TestWriteCard(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = self._tmp.name
        self.ruta = os.path.join(self.dir, "card.json")

    def test_escribe_y_devuelve_la_ruta(self):
        resultado = assess.write_card(self.ruta, card_completa(), clock=reloj)
        self.assertEqual(str(resultado), self.ruta)
        self.assertEqual(assess.read_card(self.ruta), card_completa())

    def test_formato_del_archivo(self):
        assess.write_card(self.ruta, card_completa(), clock=reloj)
        with open(self.ruta, "rb") as f:
            crudo = f.read()
        self.assertNotIn(b"\r\n", crudo)
        self.assertTrue(crudo.endswith(b"}\n"))
        texto = crudo.decode("utf-8")
        self.assertTrue(texto.startswith('{\n  "'))
        self.assertIn("ñ", texto)  # ensure_ascii=False
        datos = json.loads(texto)
        self.assertEqual(list(datos), sorted(datos))  # sort_keys=True
        self.assertEqual(datos["revision_id"], card_completa().revision_id())

    def test_atomico_no_deja_tmp(self):
        assess.write_card(self.ruta, card_completa(), clock=reloj)
        self.assertEqual(os.listdir(self.dir), ["card.json"])
        assess.write_card(self.ruta, card_completa(title="v2"), clock=reloj)  # sobrescribe
        self.assertEqual(os.listdir(self.dir), ["card.json"])
        self.assertEqual(assess.read_card(self.ruta).title, "v2")

    def test_card_invalida_no_se_escribe(self):
        invalida = card_completa(evidence=(card_completa().evidence[0], card_completa().evidence[0]))
        self.assertEqual(codigo_de(assess.write_card, self.ruta, invalida, clock=reloj), core.CODE_DUPLICATE_ID)
        self.assertEqual(os.listdir(self.dir), [])

    def test_card_invalida_no_pisa_un_archivo_previo(self):
        assess.write_card(self.ruta, card_completa(), clock=reloj)
        with open(self.ruta, "rb") as f:
            antes = f.read()
        invalida = card_completa(claims=(core.Claim("c1", "s", supports=("fantasma",)),))
        self.assertEqual(codigo_de(assess.write_card, self.ruta, invalida, clock=reloj), core.CODE_DANGLING_SUPPORT)
        with open(self.ruta, "rb") as f:
            self.assertEqual(f.read(), antes)
        self.assertEqual(os.listdir(self.dir), ["card.json"])

    def test_no_escribe_card_con_atestacion_futura(self):
        futura = card_completa(attested_at="2026-10-03T00:00:00Z")
        self.assertEqual(codigo_de(assess.write_card, self.ruta, futura, clock=reloj), core.CODE_ATTESTATION_FUTURE)
        self.assertEqual(os.listdir(self.dir), [])

    def test_no_escribe_body_sin_validador(self):
        con_body = card_completa(body={"a": 1})
        self.assertEqual(codigo_de(assess.write_card, self.ruta, con_body, clock=reloj), core.CODE_BODY_INVALID)
        self.assertEqual(os.listdir(self.dir), [])
        assess.write_card(self.ruta, con_body, clock=reloj, validate_body=lambda b: [])
        self.assertEqual(assess.read_card(self.ruta).body, {"a": 1})

    def test_no_escribe_si_no_es_cardenvelope(self):
        for valor in (None, {}, "x", card_completa().to_dict()):
            with self.subTest(valor=valor):
                self.assertEqual(codigo_de(assess.write_card, self.ruta, valor, clock=reloj), core.CODE_FIELD_INVALID)
        self.assertEqual(os.listdir(self.dir), [])

    def test_directorio_padre_inexistente_es_io_error_sin_residuos(self):
        ruta = os.path.join(self.dir, "no_existe", "card.json")
        self.assertEqual(codigo_de(assess.write_card, ruta, card_completa(), clock=reloj), core.CODE_IO_ERROR)
        self.assertEqual(os.listdir(self.dir), [])

    def test_fallo_en_replace_limpia_el_tmp(self):
        with mock.patch.object(assess.os, "replace", side_effect=OSError("boom")):
            self.assertEqual(codigo_de(assess.write_card, self.ruta, card_completa(), clock=reloj), core.CODE_IO_ERROR)
        self.assertEqual(os.listdir(self.dir), [])

    def test_fallo_en_replace_no_pisa_archivo_previo(self):
        assess.write_card(self.ruta, card_completa(), clock=reloj)
        with open(self.ruta, "rb") as f:
            antes = f.read()
        with mock.patch.object(assess.os, "replace", side_effect=OSError("boom")):
            with self.assertRaises(core.CardError):
                assess.write_card(self.ruta, card_completa(title="v2"), clock=reloj)
        with open(self.ruta, "rb") as f:
            self.assertEqual(f.read(), antes)
        self.assertEqual(os.listdir(self.dir), ["card.json"])

    def test_no_define_rutas_canonicas_ni_escanea_directorios(self):
        # Se usa solo la ruta provista: ningún otro archivo/dir aparece.
        sub = os.path.join(self.dir, "sub")
        os.makedirs(sub)
        assess.write_card(os.path.join(sub, "x.json"), card_completa(), clock=reloj)
        self.assertEqual(os.listdir(self.dir), ["sub"])
        self.assertEqual(os.listdir(sub), ["x.json"])


# ---------------------------------------------------------------------------
# read_card (R39)
# ---------------------------------------------------------------------------


class TestReadCard(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = self._tmp.name

    def _escribir(self, nombre, contenido):
        ruta = os.path.join(self.dir, nombre)
        modo = "wb" if isinstance(contenido, bytes) else "w"
        kwargs = {} if isinstance(contenido, bytes) else {"encoding": "utf-8"}
        with open(ruta, modo, **kwargs) as f:
            f.write(contenido)
        return ruta

    def test_archivo_inexistente_es_io_error(self):
        self.assertEqual(codigo_de(assess.read_card, os.path.join(self.dir, "no.json")), core.CODE_IO_ERROR)

    def test_directorio_es_io_error(self):
        self.assertEqual(codigo_de(assess.read_card, self.dir), core.CODE_IO_ERROR)

    def test_ruta_invalida_es_io_error(self):
        self.assertEqual(codigo_de(assess.read_card, None), core.CODE_IO_ERROR)

    def test_json_invalido(self):
        for nombre, contenido in (("vacio.json", ""), ("roto.json", "{"), ("texto.json", "hola")):
            with self.subTest(nombre=nombre):
                self.assertEqual(codigo_de(assess.read_card, self._escribir(nombre, contenido)), core.CODE_FIELD_INVALID)

    def test_utf8_invalido(self):
        ruta = self._escribir("bytes.json", b'{"a": "\xff\xfe"}')
        self.assertEqual(codigo_de(assess.read_card, ruta), core.CODE_FIELD_INVALID)

    def test_constantes_json_no_permitidas(self):
        for constante in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(constante=constante):
                d = json.dumps(card_completa().to_dict(con_revision=True))[:-1] + ', "x_a": ' + constante + "}"
                with self.assertRaises(core.CardError):
                    assess.read_card(self._escribir("c.json", d))

    def test_json_que_no_es_objeto(self):
        for contenido in ("[]", "5", '"x"', "null", "true"):
            with self.subTest(contenido=contenido):
                with self.assertRaises(core.CardError):
                    assess.read_card(self._escribir("c.json", contenido))

    def test_schema_desconocido_en_archivo(self):
        d = card_completa().to_dict()
        d["schema_version"] = 2
        self.assertEqual(
            codigo_de(assess.read_card, self._escribir("c.json", json.dumps(d))), core.CODE_SCHEMA_UNSUPPORTED
        )

    def test_estructura_invalida_en_archivo(self):
        d = card_completa().to_dict()
        d["evidence"][0]["content_sha256"] = "XYZ"
        self.assertEqual(codigo_de(assess.read_card, self._escribir("c.json", json.dumps(d))), core.CODE_HASH_INVALID)

    def test_clave_desconocida_en_archivo(self):
        d = card_completa().to_dict()
        d["foo"] = 1
        self.assertEqual(codigo_de(assess.read_card, self._escribir("c.json", json.dumps(d))), core.CODE_UNKNOWN_KEY)

    def test_archivo_sin_revision_id_se_acepta(self):
        d = card_completa().to_dict()
        self.assertEqual(assess.read_card(self._escribir("c.json", json.dumps(d))), card_completa())

    def test_ids_duplicados_en_archivo_no_pasan_como_validos(self):
        # read_card re-verifica estructura (R39): o rechaza la Card o la devuelve
        # de modo que `validate_card`/`evaluate` la marquen `invalid`.
        d = card_completa().to_dict()
        d["evidence"].append(dict(d["evidence"][0]))
        ruta = self._escribir("c.json", json.dumps(d))
        try:
            card = assess.read_card(ruta)
        except core.CardError:
            return
        self.assertTrue(core.validate_card(card))
        self.assertEqual(assess.evaluate(card, requisitos(), resolvers_frescos()).card_status, assess.CARD_INVALID)

    def test_lee_ruta_pathlike(self):
        import pathlib

        ruta = os.path.join(self.dir, "p.json")
        assess.write_card(pathlib.Path(ruta), card_completa(), clock=reloj)
        self.assertEqual(assess.read_card(pathlib.Path(ruta)), card_completa())


# ---------------------------------------------------------------------------
# evaluate_file: archivo rechazado == estado `invalid`
# ---------------------------------------------------------------------------


class TestEvaluateFile(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = self._tmp.name

    def _escribir(self, datos):
        ruta = os.path.join(self.dir, "c.json")
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(datos if isinstance(datos, str) else json.dumps(datos))
        return ruta

    def _resolvers_espia(self):
        llamadas = []

        def _resolver(ref):
            llamadas.append(ref)
            return assess.Resolution(assess.RES_FOUND, ref.content_sha256)

        return llamadas, {k: _resolver for k in core.OBSERVED_KINDS}

    def _assert_invalid(self, datos, code):
        llamadas, resolvers = self._escribir_y_espiar(datos)
        res = assess.evaluate_file(self._ruta, requisitos(), resolvers, reloj)
        self.assertEqual(res.card_status, assess.CARD_INVALID)
        self.assertEqual(res.requisitos, ())
        self.assertEqual(res.evidencias, ())
        self.assertEqual(len(res.hallazgos), 1)
        self.assertEqual(res.hallazgos[0].code, code)
        self.assertEqual(res.hallazgos[0].path, "file")
        self.assertEqual(llamadas, [])
        self.assertEqual(res.a_dict()["card_status"], "invalid")
        return res

    def _escribir_y_espiar(self, datos):
        self._ruta = self._escribir(datos)
        return self._resolvers_espia()

    def test_revision_id_distinto_es_invalid(self):
        d = card_completa().to_dict(con_revision=True)
        d["revision_id"] = "card-a__000000000000"
        self._assert_invalid(d, core.CODE_REVISION_MISMATCH)

    def test_pin_de_hash_malformado_es_invalid(self):
        d = card_completa().to_dict()
        d["evidence"][0]["content_sha256"] = "XYZ"
        self._assert_invalid(d, core.CODE_HASH_INVALID)

    def test_archivo_con_status_es_invalid(self):
        d = card_completa().to_dict()
        d["status"] = "complete"
        self._assert_invalid(d, core.CODE_UNKNOWN_KEY)

    def test_json_invalido_es_invalid(self):
        self._assert_invalid("{", core.CODE_FIELD_INVALID)

    def test_archivo_inexistente_es_invalid(self):
        llamadas, resolvers = self._resolvers_espia()
        res = assess.evaluate_file(os.path.join(self.dir, "no.json"), requisitos(), resolvers, reloj)
        self.assertEqual(res.card_status, assess.CARD_INVALID)
        self.assertEqual(res.hallazgos[0].code, core.CODE_IO_ERROR)
        self.assertEqual(llamadas, [])

    def test_read_card_sigue_lanzando(self):
        d = card_completa().to_dict(con_revision=True)
        d["revision_id"] = "card-a__000000000000"
        self.assertEqual(codigo_de(assess.read_card, self._escribir(d)), core.CODE_REVISION_MISMATCH)

    def test_archivo_bueno_igual_que_evaluate_en_memoria(self):
        card = card_completa()
        ruta = assess.write_card(os.path.join(self.dir, "ok.json"), card, clock=reloj)
        desde_archivo = assess.evaluate_file(ruta, requisitos(), resolvers_frescos(), reloj)
        en_memoria = assess.evaluate(card, requisitos(), resolvers_frescos(), reloj)
        self.assertEqual(desde_archivo.a_dict(), en_memoria.a_dict())
        self.assertEqual(desde_archivo.card_status, assess.CARD_COMPLETE)


if __name__ == "__main__":
    unittest.main()

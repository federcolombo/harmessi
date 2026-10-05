"""Tests de `EvidenceRef` (R10-R15, R40)."""
from __future__ import annotations

import json
import unittest

from tools.cards import assess, core

H1 = "a" * 64
T0 = "2026-10-01T10:00:00Z"

CLAVES_CERRADAS_EVIDENCIA = {
    "evidence_id",
    "kind",
    "ref_id",
    "member",
    "content_sha256",
    "schema_version",
    "locator",
    "pinned_at",
}


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


def dict_ev(**kw):
    base = dict(evidence_id="ev1", kind="quality_evidence", ref_id="qe-1", content_sha256=H1, pinned_at=T0)
    base.update(kw)
    return base


class TestCamposYKinds(unittest.TestCase):
    def test_minimo_valido_y_clase_observed_no_serializada(self):
        ev = hacer_ev()
        self.assertEqual(ev.evidence_class, "observed")
        self.assertNotIn("evidence_class", ev.to_dict())
        self.assertNotIn("class", ev.to_dict())

    def test_todos_los_kinds_observados_son_validos(self):
        self.assertEqual(len(core.OBSERVED_KINDS), 13)
        for kind in core.OBSERVED_KINDS:
            with self.subTest(kind=kind):
                self.assertEqual(hacer_ev(kind=kind).kind, kind)

    def test_kind_invalido(self):
        for kind in ("human_attestation", "bogus", "", None, 5, "Quality_Evidence"):
            with self.subTest(kind=kind):
                self.assertEqual(codigo_de(hacer_ev, kind=kind), core.CODE_FIELD_INVALID)

    def test_schema_version_opcional_entero_positivo(self):
        self.assertEqual(hacer_ev(schema_version=3).schema_version, 3)
        for valor in (0, -1, "1", 1.5, True):
            with self.subTest(valor=valor):
                self.assertEqual(codigo_de(hacer_ev, schema_version=valor), core.CODE_FIELD_INVALID)

    def test_orden_fijo_de_claves(self):
        ev = hacer_ev(member="m", schema_version=2, locator="a/b.txt", extensions={"x_b": 1, "x_a": 2})
        self.assertEqual(
            list(ev.to_dict()),
            [
                "evidence_id",
                "kind",
                "ref_id",
                "member",
                "content_sha256",
                "schema_version",
                "locator",
                "pinned_at",
                "x_a",
                "x_b",
            ],
        )

    def test_opcionales_ausentes_no_se_serializan(self):
        self.assertEqual(
            list(hacer_ev().to_dict()), ["evidence_id", "kind", "ref_id", "content_sha256", "pinned_at"]
        )

    def test_pinned_at_formato(self):
        for valor in ("2026-10-01", "2026-10-01T10:00:00.5Z", None, "2026-02-30T00:00:00Z"):
            with self.subTest(valor=valor):
                self.assertEqual(codigo_de(hacer_ev, pinned_at=valor), core.CODE_TIMESTAMP_INVALID)


class TestHashObligatorio(unittest.TestCase):
    def test_sin_hash_en_from_dict_es_error(self):
        d = dict_ev()
        del d["content_sha256"]
        self.assertEqual(codigo_de(core.EvidenceRef.from_dict, d), core.CODE_FIELD_INVALID)

    def test_hash_none_es_error(self):
        self.assertEqual(codigo_de(hacer_ev, content_sha256=None), core.CODE_HASH_INVALID)

    def test_hash_malformado(self):
        malos = ("A" * 64, "a" * 63, "a" * 65, "g" * 64, "", " " + "a" * 63, "a" * 64 + "\n", 12345, b"a" * 64)
        for valor in malos:
            with self.subTest(valor=valor):
                self.assertEqual(codigo_de(hacer_ev, content_sha256=valor), core.CODE_HASH_INVALID)
                self.assertEqual(
                    codigo_de(core.EvidenceRef.from_dict, dict_ev(content_sha256=valor)), core.CODE_HASH_INVALID
                )

    def test_hash_valido(self):
        self.assertEqual(hacer_ev(content_sha256="0123456789abcdef" * 4).content_sha256, "0123456789abcdef" * 4)


class TestLocatorNoPortable(unittest.TestCase):
    def test_locators_no_portables(self):
        casos = {
            "absoluto posix": "/etc/passwd",
            "home": "~/x.csv",
            "punto punto inicial": "../x.csv",
            "punto punto medio": "a/../b.csv",
            "punto punto final": "a/..",
            "barra invertida": "a\\b.csv",
            "unidad de disco": "C:/datos/x.csv",
            "unidad de disco relativa": "C:x.csv",
            "unidad con barra invertida": "C:\\datos\\x.csv",
            "url": "https://host/x.csv",
            "url con credenciales": "https://user:pw@host/x.csv",
            "dsn con credenciales": "postgres://user:pw@host:5432/db",
            "usuario:clave@": "user:pw@host/db",
            "secreto en query": "a/b.csv?password=abc",
            "api key": "a/b.csv?api_key=abc",
            "token": "a/b.csv?token=abc",
            "segmento vacio": "a//b.csv",
            "barra final": "a/b/",
            "vacio": "",
            "solo espacios": "   ",
            "espacios en extremos": " a/b.csv",
            "no imprimible": "a/\x00b.csv",
            "cero ancho": "a/\u200bb.csv",
        }
        for nombre, valor in casos.items():
            with self.subTest(nombre=nombre):
                self.assertFalse(core.es_locator_portable(valor))
                self.assertEqual(codigo_de(hacer_ev, locator=valor), core.CODE_LOCATOR_NOT_PORTABLE)
                self.assertEqual(
                    codigo_de(core.EvidenceRef.from_dict, dict_ev(locator=valor)), core.CODE_LOCATOR_NOT_PORTABLE
                )

    def test_locator_no_str(self):
        for valor in (5, ["a"], b"a/b"):
            with self.subTest(valor=valor):
                self.assertFalse(core.es_locator_portable(valor))
                self.assertEqual(codigo_de(hacer_ev, locator=valor), core.CODE_FIELD_INVALID)

    def test_locators_portables(self):
        for valor in ("data/x.csv", "a.b/c-d_e.parquet", "x", "dir/sub dir/f.txt", ".hidden/f", "a/b.c.d"):
            with self.subTest(valor=valor):
                self.assertTrue(core.es_locator_portable(valor))
                self.assertEqual(hacer_ev(locator=valor).locator, valor)

    def test_ref_id_y_member_no_admiten_rutas_fisicas_ni_credenciales(self):
        malos = ("C:\\x", "/abs/x", "~x", "a\\b", "postgres://u:p@h/db", "u:p@h", "a/../b", "password=abc")
        for valor in malos:
            with self.subTest(valor=valor):
                self.assertEqual(codigo_de(hacer_ev, ref_id=valor), core.CODE_LOCATOR_NOT_PORTABLE)
                self.assertEqual(codigo_de(hacer_ev, member=valor), core.CODE_LOCATOR_NOT_PORTABLE)

    def test_ref_id_vacio_o_largo(self):
        self.assertEqual(codigo_de(hacer_ev, ref_id=""), core.CODE_FIELD_INVALID)
        self.assertEqual(codigo_de(hacer_ev, ref_id=" x"), core.CODE_FIELD_INVALID)
        self.assertEqual(codigo_de(hacer_ev, ref_id="x" * 257), core.CODE_FIELD_INVALID)
        self.assertEqual(hacer_ev(ref_id="x" * 256).ref_id, "x" * 256)
        self.assertEqual(codigo_de(hacer_ev, ref_id=None), core.CODE_FIELD_INVALID)

    def test_ref_id_con_formatos_reales_es_valido(self):
        for valor in ("fuente__0123456789ab", "qe-2026-10-01", "dr-1", "report_1:run_2"):
            with self.subTest(valor=valor):
                self.assertEqual(hacer_ev(ref_id=valor).ref_id, valor)


class TestSinPayloadR11(unittest.TestCase):
    def test_dict_serializado_solo_tiene_claves_cerradas(self):
        ev = hacer_ev(member="m", schema_version=1, locator="a/b.txt")
        self.assertEqual(set(ev.to_dict()), CLAVES_CERRADAS_EVIDENCIA)

    def test_dict_serializado_con_extension_solo_agrega_x(self):
        ev = hacer_ev(extensions={"x_nota": "ok"})
        extra = set(ev.to_dict()) - CLAVES_CERRADAS_EVIDENCIA
        self.assertEqual(extra, {"x_nota"})

    def test_no_hay_campo_de_payload_en_la_clase(self):
        campos = set(core.EvidenceRef.__dataclass_fields__)
        for prohibido in ("payload", "data", "content", "value", "body", "rows", "metrics", "result"):
            self.assertNotIn(prohibido, campos)

    def test_from_dict_rechaza_claves_de_payload(self):
        for clave in ("payload", "data", "content", "rows", "value", "status"):
            with self.subTest(clave=clave):
                self.assertEqual(
                    codigo_de(core.EvidenceRef.from_dict, dict_ev(**{clave: {"a": 1}})), core.CODE_UNKNOWN_KEY
                )

    def test_payload_via_constructor_solo_es_posible_con_prefijo_x(self):
        self.assertEqual(codigo_de(hacer_ev, extensions={"payload": 1}), core.CODE_UNKNOWN_KEY)

    def test_card_serializada_no_contiene_payload(self):
        card = core.CardEnvelope(
            schema_version=1,
            card_kind="data_card",
            kind_schema_version=1,
            card_id="card-a",
            title="T",
            subject="s",
            created_at=T0,
            generated_at=T0,
            evidence=(hacer_ev(),),
        )
        for e in card.to_dict()["evidence"]:
            self.assertLessEqual(set(e), CLAVES_CERRADAS_EVIDENCIA)


class TestProvenanceR13(unittest.TestCase):
    def _ref_provenance(self):
        return hacer_ev(
            evidence_id="prov1",
            kind="source_provenance",
            ref_id="fuente_x__0123456789ab",
            member="provenance",
            content_sha256="b" * 64,
        )

    def test_ref_sintetica_a_source_provenance(self):
        ev = self._ref_provenance()
        d = ev.to_dict()
        self.assertEqual(d["kind"], "source_provenance")
        self.assertEqual(d["ref_id"], "fuente_x__0123456789ab")
        self.assertEqual(d["member"], "provenance")
        self.assertEqual(core.EvidenceRef.from_dict(d), ev)

    def test_ref_a_provenance_se_resuelve_con_resolver_inyectado(self):
        ev = self._ref_provenance()
        resolvers = {"source_provenance": lambda ref: assess.Resolution(assess.RES_FOUND, "b" * 64)}
        self.assertEqual(assess.evaluar_evidencia(ev, resolvers), assess.EV_FRESH)

    def test_ref_a_provenance_dentro_de_una_card_valida(self):
        card = core.CardEnvelope(
            schema_version=1,
            card_kind="data_card",
            kind_schema_version=1,
            card_id="card-a",
            title="T",
            subject="s",
            created_at=T0,
            generated_at=T0,
            evidence=(self._ref_provenance(),),
            claims=(core.Claim("c1", "procedencia", supports=("prov1",), requirement_id="r1"),),
        )
        self.assertEqual(core.validate_card(card), [])


class TestSerializacionEvidencia(unittest.TestCase):
    def test_round_trip(self):
        ev = hacer_ev(member="m", schema_version=2, locator="a/b.txt", extensions={"x_a": [1, {"k": None}]})
        self.assertEqual(core.EvidenceRef.from_dict(ev.to_dict()), ev)

    def test_round_trip_via_json(self):
        ev = hacer_ev(member="m", locator="a/b.txt")
        d = json.loads(json.dumps(ev.to_dict()))
        self.assertEqual(core.EvidenceRef.from_dict(d), ev)

    def test_from_dict_entradas_malformadas(self):
        for valor in (None, 5, "x", [], [dict_ev()], (), {}):
            with self.subTest(valor=valor):
                self.assertIn(
                    codigo_de(core.EvidenceRef.from_dict, valor), (core.CODE_FIELD_INVALID, core.CODE_UNKNOWN_KEY)
                )

    def test_from_dict_tipos_erroneos(self):
        for clave, valor in (
            ("evidence_id", 5),
            ("kind", ["quality_evidence"]),
            ("ref_id", 5),
            ("pinned_at", 5),
            ("schema_version", "1"),
            ("member", 5),
            ("locator", 5),
        ):
            with self.subTest(clave=clave):
                with self.assertRaises(core.CardError):
                    core.EvidenceRef.from_dict(dict_ev(**{clave: valor}))

    def test_from_dict_claves_desconocidas_salvo_x(self):
        self.assertEqual(codigo_de(core.EvidenceRef.from_dict, dict_ev(foo=1)), core.CODE_UNKNOWN_KEY)
        self.assertEqual(core.EvidenceRef.from_dict(dict_ev(x_foo=1)).extensions, {"x_foo": 1})

    def test_from_dict_clave_no_str(self):
        d = dict_ev()
        d[5] = "x"
        self.assertEqual(codigo_de(core.EvidenceRef.from_dict, d), core.CODE_UNKNOWN_KEY)

    def test_extensiones_no_json_se_rechazan(self):
        self.assertEqual(codigo_de(hacer_ev, extensions={"x_a": object()}), core.CODE_FIELD_INVALID)
        self.assertEqual(codigo_de(hacer_ev, extensions={"x_a": float("inf")}), core.CODE_FIELD_INVALID)


if __name__ == "__main__":
    unittest.main()

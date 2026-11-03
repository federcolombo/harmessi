"""Paridad de contratos duplicados a propósito entre `tools/cards/core.py` y
los paquetes `datasources` / `autonomy` (v0.9 Change 0,
`20261002-card-and-evidence-foundation`, R5, R17, R21, R37 de `spec.md`).

`cards.core` es solo-stdlib y no puede importar a sus pares (R1), así que
REPLICA por forma: `canonical_json`/`content_sha256` (de `datasources.core`),
el patrón de ids (`SOURCE_ID_PATTERN`), las reglas de actor humano
(`autonomy.validate_human_identity`) y la forma de `approval_ref`
(`autonomy.ApprovalRef`). Este test afirma que la duplicación sigue siendo
exacta, para que no diverjan en silencio. Solo los tests importan ambos lados.
"""
from __future__ import annotations

import re
import unittest

from tools.autonomy import core as autonomy_core
from tools.cards import core as cards_core
from tools.datasources import core as datasources_core

# ---------------------------------------------------------------------------
# R37: canonical_json / content_sha256
# ---------------------------------------------------------------------------

_VECTORES = (
    ("vacio_dict", {}),
    ("vacio_list", []),
    ("escalares", {"b": 1, "a": None, "c": True, "d": False, "e": "x"}),
    ("orden_de_claves", {"z": 1, "a": 2, "m": {"y": 1, "b": 2}}),
    ("no_ascii", {"título": "Año ñandú", "emoji": "\U0001F600", "cjk": "データ", "acento": "é"}),
    ("escapes", {"comillas": 'a"b', "barra": "a\\b", "nl": "a\nb", "tab": "a\tb", "ctl": "\x01"}),
    ("anidado", {"a": [1, [2, [3, {"k": [{"x": None}]}]]], "b": {"c": {"d": {"e": []}}}}),
    ("floats", {"a": 1.5, "b": 0.1, "c": 1e-7, "d": 1e22, "e": -0.0, "f": 3.0, "g": 2.5e-300, "h": 123456789.123456789}),
    ("enteros_grandes", {"a": 2**63, "b": -(2**70), "c": 0}),
    ("lista_de_dicts", [{"b": 1, "a": 2}, {"a": 1}]),
    ("string_suelto", "hola ñ"),
    ("numero_suelto", 42),
    ("none_suelto", None),
    ("mixto_realista", {
        "schema_version": 1,
        "card_id": "demo",
        "evidence": [{"evidence_id": "ev-1", "content_sha256": "a" * 64, "ref_id": "obs-1"}],
        "body": {"descripción": "texto con ñ", "n": 1.25, "lista": [1, 2.5, "x"]},
    }),
)

# Valores que ambos lados deben rechazar (JSON no canónico).
_NO_SERIALIZABLES = (
    ("nan", {"a": float("nan")}),
    ("inf", {"a": float("inf")}),
    ("menos_inf", [float("-inf")]),
    ("set", {"a": {1, 2}}),
    ("bytes", {"a": b"x"}),
    ("clave_no_str_mixta", {1: "a", "b": 2}),
    ("objeto", object()),
)


class TestParidadCanonicalJson(unittest.TestCase):
    def test_canonical_json_identico_sobre_vectores_fijos(self):
        for nombre, vector in _VECTORES:
            with self.subTest(vector=nombre):
                esperado = datasources_core.canonical_json(vector)
                obtenido = cards_core.canonical_json(vector)
                self.assertEqual(obtenido, esperado)
                # Byte a byte (UTF-8), no solo igualdad de str.
                self.assertEqual(obtenido.encode("utf-8"), esperado.encode("utf-8"))

    def test_content_sha256_identico_sobre_vectores_fijos(self):
        for nombre, vector in _VECTORES:
            with self.subTest(vector=nombre):
                self.assertEqual(cards_core.content_sha256(vector), datasources_core.content_sha256(vector))

    def test_content_sha256_es_hex_minuscula_de_64(self):
        for nombre, vector in _VECTORES:
            with self.subTest(vector=nombre):
                self.assertRegex(cards_core.content_sha256(vector), r"[0-9a-f]{64}")

    def test_vector_fijo_literal(self):
        """Vector literal (no derivado de ningún módulo): protege contra un
        cambio simultáneo en ambos lados."""
        vector = {"b": [1, 2.5, None], "a": "ñ", "c": {"y": True, "x": False}}
        literal = '{"a":"ñ","b":[1,2.5,null],"c":{"x":false,"y":true}}'
        self.assertEqual(cards_core.canonical_json(vector), literal)
        self.assertEqual(datasources_core.canonical_json(vector), literal)

    def test_ambos_rechazan_lo_no_serializable(self):
        for nombre, valor in _NO_SERIALIZABLES:
            with self.subTest(valor=nombre):
                with self.assertRaises(cards_core.CardError) as ctx_cards:
                    cards_core.canonical_json(valor)
                self.assertIn(ctx_cards.exception.code, cards_core.CODES)
                with self.assertRaises(datasources_core.SourceError):
                    datasources_core.canonical_json(valor)
                with self.assertRaises(cards_core.CardError):
                    cards_core.content_sha256(valor)


# ---------------------------------------------------------------------------
# R5: patrón de ids
# ---------------------------------------------------------------------------

_IDS_ACEPTADOS = (
    "customers", "a", "0", "a-b_c", "x" * 64, "9lives", "card-01", "model_card_v2",
)
_IDS_RECHAZADOS = (
    "", "A", "Customers", "-a", "_a", "a b", "a.b", "a/b", "a\\b", "x" * 65, "ñandú",
    "a\n", "\na", "dbo.Clientes.Productores", "project.dataset.customers", "/v2/customers",
    "data/raw/customers.parquet", " a", "a ",
)


def _claim_con_id(valor):
    return cards_core.Claim(claim_id=valor, statement="afirmación")


class TestParidadPatronDeIds(unittest.TestCase):
    def test_literal_identico_a_source_id_pattern(self):
        self.assertEqual(cards_core.CARD_ID_PATTERN, datasources_core.SOURCE_ID_PATTERN)
        self.assertEqual(cards_core.CARD_ID_PATTERN, autonomy_core.SOURCE_ID_PATTERN)

    def test_id_pattern_generico_es_el_mismo_literal(self):
        self.assertEqual(cards_core.ID_PATTERN, cards_core.CARD_ID_PATTERN)

    def test_comportamiento_identico_a_datasources_y_autonomy(self):
        regex_datasources = re.compile(datasources_core.SOURCE_ID_PATTERN)
        for valor in _IDS_ACEPTADOS + _IDS_RECHAZADOS:
            with self.subTest(valor=valor):
                esperado = regex_datasources.fullmatch(valor) is not None
                self.assertEqual(re.compile(cards_core.CARD_ID_PATTERN).fullmatch(valor) is not None, esperado)
                self.assertEqual(autonomy_core.is_valid_source_id(valor), esperado)

    def test_ids_aceptados_y_rechazados_por_los_tipos_de_cards(self):
        for valor in _IDS_ACEPTADOS:
            with self.subTest(aceptado=valor):
                self.assertEqual(_claim_con_id(valor).claim_id, valor)
        for valor in _IDS_RECHAZADOS:
            with self.subTest(rechazado=valor):
                with self.assertRaises(cards_core.CardError) as ctx:
                    _claim_con_id(valor)
                self.assertEqual(ctx.exception.code, cards_core.CODE_ID_INVALID)

    def test_ids_no_str_rechazados(self):
        for valor in (None, 1, b"abc", ["a"]):
            with self.subTest(valor=valor):
                with self.assertRaises(cards_core.CardError):
                    _claim_con_id(valor)

    def test_ids_reservados_cumplen_el_patron_pero_se_rechazan_como_card_id(self):
        self.assertTrue(cards_core.RESERVED_CARD_IDS)
        for reservado in cards_core.RESERVED_CARD_IDS:
            with self.subTest(reservado=reservado):
                self.assertIsNotNone(re.compile(cards_core.CARD_ID_PATTERN).fullmatch(reservado))
                with self.assertRaises(cards_core.CardError) as ctx:
                    cards_core.CardEnvelope(
                        schema_version=1,
                        card_kind="data_card",
                        kind_schema_version=1,
                        card_id=reservado,
                        title="t",
                        subject="sujeto-logico",
                        created_at="2026-10-02T00:00:00Z",
                        generated_at="2026-10-02T00:00:00Z",
                    )
                self.assertEqual(ctx.exception.code, cards_core.CODE_ID_INVALID)


# ---------------------------------------------------------------------------
# R17: actor humano
# ---------------------------------------------------------------------------

# (caso, valor, valido_esperado). El valor esperado es el mismo en ambos
# lados; además se compara cada caso contra `autonomy.validate_human_identity`.
_ACTORES = (
    ("vacio", "", False),
    ("solo_espacios", "   ", False),
    ("solo_tab_nl", "\t\n", False),
    ("solo_formato", "​", False),
    ("no_str_none", None, False),
    ("no_str_int", 123, False),
    ("no_str_bytes", b"ana", False),
    ("policy_minuscula", "policy:x", False),
    ("policy_mayuscula", "POLICY:x", False),
    ("policy_mixto", "Policy:Revisor", False),
    ("policy_con_espacio_previo", "  policy:x", False),
    ("policy_con_formato_intercalado", "pol​icy:x", False),
    ("policy_fullwidth_nfkc", "ｐｏｌｉｃｙ:x", False),
    ("no_imprimible_ctl", "ana\x07", False),
    ("no_imprimible_formato", "ana​", False),
    ("no_imprimible_nul", "a\x00b", False),
    ("valido_simple", "ana", True),
    ("valido_con_espacio", "Ana Pérez", True),
    ("valido_email", "ana@example.org", True),
    ("valido_policy_sin_dos_puntos", "policy", True),
    ("valido_policy_en_medio", "x policy:y", True),
    ("valido_no_ascii", "José Ñandú", True),
)


def _detalle_cards(hallazgos: list) -> str:
    return hallazgos[0].detail if hallazgos else ""


def _detalle_autonomy(hallazgos: list) -> str:
    return hallazgos[0].detail_key if hallazgos else ""


class TestParidadActor(unittest.TestCase):
    def test_tabla_de_casos_valido_o_invalido(self):
        for caso, valor, valido in _ACTORES:
            with self.subTest(caso=caso):
                self.assertEqual(not cards_core.validate_actor(valor), valido)
                self.assertEqual(not autonomy_core.validate_human_identity(valor), valido)

    def test_misma_razon_que_autonomy(self):
        """El detalle estable (`empty_or_not_str` / `reserved_namespace` /
        `non_printable`) coincide con el `detail_key` de autonomy."""
        for caso, valor, _valido in _ACTORES:
            with self.subTest(caso=caso):
                self.assertEqual(
                    _detalle_cards(cards_core.validate_actor(valor)),
                    _detalle_autonomy(autonomy_core.validate_human_identity(valor)),
                )

    def test_razones_literales_de_los_casos_clave(self):
        esperadas = {
            "vacio": "empty_or_not_str",
            "solo_espacios": "empty_or_not_str",
            "policy_minuscula": "reserved_namespace",
            "policy_mayuscula": "reserved_namespace",
            "no_imprimible_ctl": "non_printable",
            "valido_simple": "",
        }
        tabla = {caso: valor for caso, valor, _ in _ACTORES}
        for caso, detalle in esperadas.items():
            with self.subTest(caso=caso):
                self.assertEqual(_detalle_cards(cards_core.validate_actor(tabla[caso])), detalle)

    def test_namespace_policy_identico_a_autonomy(self):
        for caso, valor, _valido in _ACTORES:
            if not isinstance(valor, str):
                continue
            with self.subTest(caso=caso):
                self.assertEqual(
                    cards_core._es_namespace_policy(valor),
                    autonomy_core.is_reserved_policy_namespace(valor),
                )

    def test_humanattestation_aplica_la_misma_regla(self):
        for caso, valor, valido in _ACTORES:
            with self.subTest(caso=caso):
                kwargs = dict(
                    attestation_id="att-1",
                    claim="afirmación",
                    actor=valor,
                    authority="rol",
                    attested_at="2026-10-02T00:00:00Z",
                    scope="alcance",
                    attestation_kind="declared",
                )
                if valido:
                    self.assertEqual(cards_core.HumanAttestation(**kwargs).actor, valor)
                else:
                    with self.assertRaises(cards_core.CardError) as ctx:
                        cards_core.HumanAttestation(**kwargs)
                    self.assertEqual(ctx.exception.code, cards_core.CODE_IDENTITY_INVALID)


# ---------------------------------------------------------------------------
# R16/R21: forma de approval_ref
# ---------------------------------------------------------------------------

_HASH_OK = "a" * 64
_CHANGE_OK = "20261002-card-and-evidence-foundation"

_REFS_VALIDAS = (
    ("completa", {"change_id": _CHANGE_OK, "artefacto": "proposal.md", "hash": _HASH_OK}),
    ("change_corto", {"change_id": "20261002-x", "artefacto": "spec.md", "hash": "0123456789abcdef" * 4}),
    ("change_con_digitos", {"change_id": "20261002-0abc-9", "artefacto": "design md", "hash": _HASH_OK}),
)

_REFS_INVALIDAS = (
    ("no_dict_none", None),
    ("no_dict_str", "x"),
    ("no_dict_lista", []),
    ("vacio", {}),
    ("falta_change_id", {"artefacto": "proposal.md", "hash": _HASH_OK}),
    ("falta_artefacto", {"change_id": _CHANGE_OK, "hash": _HASH_OK}),
    ("falta_hash", {"change_id": _CHANGE_OK, "artefacto": "proposal.md"}),
    ("clave_extra", {"change_id": _CHANGE_OK, "artefacto": "proposal.md", "hash": _HASH_OK, "extra": 1}),
    ("clave_status", {"change_id": _CHANGE_OK, "artefacto": "proposal.md", "hash": _HASH_OK, "status": "ok"}),
    ("clave_extension", {"change_id": _CHANGE_OK, "artefacto": "proposal.md", "hash": _HASH_OK, "x_a": 1}),
    ("change_id_sin_fecha", {"change_id": "card-foundation", "artefacto": "proposal.md", "hash": _HASH_OK}),
    ("change_id_fecha_corta", {"change_id": "2026100-x", "artefacto": "proposal.md", "hash": _HASH_OK}),
    ("change_id_mayuscula", {"change_id": "20261002-Card", "artefacto": "proposal.md", "hash": _HASH_OK}),
    ("change_id_vacio", {"change_id": "", "artefacto": "proposal.md", "hash": _HASH_OK}),
    ("change_id_no_str", {"change_id": 20261002, "artefacto": "proposal.md", "hash": _HASH_OK}),
    ("change_id_salto_final", {"change_id": _CHANGE_OK + "\n", "artefacto": "proposal.md", "hash": _HASH_OK}),
    ("artefacto_vacio", {"change_id": _CHANGE_OK, "artefacto": "", "hash": _HASH_OK}),
    ("artefacto_espacios", {"change_id": _CHANGE_OK, "artefacto": "   ", "hash": _HASH_OK}),
    ("artefacto_espacio_extremo", {"change_id": _CHANGE_OK, "artefacto": " proposal.md", "hash": _HASH_OK}),
    ("artefacto_punto", {"change_id": _CHANGE_OK, "artefacto": ".", "hash": _HASH_OK}),
    ("artefacto_con_barra", {"change_id": _CHANGE_OK, "artefacto": "a/proposal.md", "hash": _HASH_OK}),
    ("artefacto_con_contrabarra", {"change_id": _CHANGE_OK, "artefacto": "a\\proposal.md", "hash": _HASH_OK}),
    ("artefacto_dos_puntos", {"change_id": _CHANGE_OK, "artefacto": "..", "hash": _HASH_OK}),
    ("artefacto_con_dos_puntos_en_medio", {"change_id": _CHANGE_OK, "artefacto": "a..md", "hash": _HASH_OK}),
    ("artefacto_no_str", {"change_id": _CHANGE_OK, "artefacto": 5, "hash": _HASH_OK}),
    ("hash_mayuscula", {"change_id": _CHANGE_OK, "artefacto": "proposal.md", "hash": "A" * 64}),
    ("hash_corto", {"change_id": _CHANGE_OK, "artefacto": "proposal.md", "hash": "a" * 63}),
    ("hash_largo", {"change_id": _CHANGE_OK, "artefacto": "proposal.md", "hash": "a" * 65}),
    ("hash_no_hex", {"change_id": _CHANGE_OK, "artefacto": "proposal.md", "hash": "g" * 64}),
    ("hash_no_str", {"change_id": _CHANGE_OK, "artefacto": "proposal.md", "hash": 5}),
    ("hash_salto_final", {"change_id": _CHANGE_OK, "artefacto": "proposal.md", "hash": _HASH_OK + "\n"}),
    ("todo_mal", {"change_id": "x", "artefacto": "", "hash": "z", "otra": 1}),
)


def _normalizar_cards(hallazgos: list) -> set:
    """`(path, detail)` de cards sin el prefijo `approval_ref` (autonomy no lo lleva)."""
    resultado = set()
    for h in hallazgos:
        if h.path == "approval_ref":
            ruta = ""
        elif h.path.startswith("approval_ref."):
            ruta = h.path[len("approval_ref."):]
        else:
            ruta = h.path
        resultado.add((ruta, h.detail))
    return resultado


def _normalizar_autonomy(hallazgos: list) -> set:
    return {(h.path, h.detail_key) for h in hallazgos}


def _anclada(approval_ref):
    return cards_core.HumanAttestation(
        attestation_id="att-1",
        claim="afirmación",
        actor="ana",
        authority="rol",
        attested_at="2026-10-02T00:00:00Z",
        scope="alcance",
        attestation_kind="anchored",
        approval_ref=approval_ref,
    )


class TestParidadApprovalRef(unittest.TestCase):
    def test_regex_de_forma_identicos(self):
        self.assertEqual(cards_core._RE_CHANGE_ID.pattern, autonomy_core._RE_CHANGE_ID.pattern)
        self.assertEqual(cards_core._RE_SHA256.pattern, autonomy_core._RE_SHA256.pattern)

    def test_refs_validas_sin_hallazgos_en_ambos_lados(self):
        for caso, ref in _REFS_VALIDAS:
            with self.subTest(caso=caso):
                self.assertEqual(cards_core.validate_approval_ref(ref), [])
                self.assertEqual(autonomy_core.validate_approval_ref(ref), [])
                # autonomy.ApprovalRef.from_dict las acepta.
                self.assertEqual(autonomy_core.ApprovalRef.from_dict(ref).to_dict(), dict(sorted(ref.items())))

    def test_refs_invalidas_con_hallazgos_en_ambos_lados(self):
        for caso, ref in _REFS_INVALIDAS:
            with self.subTest(caso=caso):
                self.assertTrue(cards_core.validate_approval_ref(ref))
                self.assertTrue(autonomy_core.validate_approval_ref(ref))
                with self.assertRaises(autonomy_core.AutonomyError):
                    autonomy_core.ApprovalRef.from_dict(ref)

    def test_mismos_hallazgos_por_campo_y_razon(self):
        for caso, ref in _REFS_VALIDAS + _REFS_INVALIDAS:
            with self.subTest(caso=caso):
                self.assertEqual(
                    _normalizar_cards(cards_core.validate_approval_ref(ref)),
                    _normalizar_autonomy(autonomy_core.validate_approval_ref(ref)),
                )

    def test_clave_no_str_invalida_en_ambos_lados(self):
        """Ambos lados rechazan una clave no-str (el detalle exacto puede
        diferir: autonomy `non_str_key`, cards `unknown_key`), por lo que solo
        se compara la validez."""
        ref = {"change_id": _CHANGE_OK, "artefacto": "proposal.md", "hash": _HASH_OK, 1: "x"}
        self.assertTrue(cards_core.validate_approval_ref(ref))
        self.assertTrue(autonomy_core.validate_approval_ref(ref))

    def test_anchored_acepta_exactamente_las_refs_que_acepta_autonomy(self):
        for caso, ref in _REFS_VALIDAS:
            with self.subTest(caso=caso):
                att = _anclada(ref)
                self.assertEqual(att.attestation_kind, "anchored")
                self.assertEqual(att.approval_ref, dict(sorted(ref.items())))
        for caso, ref in _REFS_INVALIDAS:
            with self.subTest(caso=caso):
                with self.assertRaises(cards_core.CardError) as ctx:
                    _anclada(ref)
                self.assertEqual(ctx.exception.code, cards_core.CODE_APPROVAL_REF_INVALID)

    def test_declared_con_approval_ref_se_rechaza(self):
        with self.assertRaises(cards_core.CardError) as ctx:
            cards_core.HumanAttestation(
                attestation_id="att-1",
                claim="afirmación",
                actor="ana",
                authority="rol",
                attested_at="2026-10-02T00:00:00Z",
                scope="alcance",
                attestation_kind="declared",
                approval_ref=_REFS_VALIDAS[0][1],
            )
        self.assertEqual(ctx.exception.code, cards_core.CODE_ATTESTATION_KIND_INVALID)


if __name__ == "__main__":
    unittest.main()

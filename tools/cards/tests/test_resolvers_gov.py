"""Tests de los resolvers de gobernanza en `tools/cards/resolvers.py`
(Change `20261005-model-risk-responsible-ai`, R3, R4, R45, R56-R59).

Resolvers cubiertos: `model_card` (R57), `governance_policy` (R56) y
`evidence_document` (R45/R58), mas `default_resolvers` (R4/R59: 15 kinds).

Usan OBJETOS REALES en directorios temporales: Model Cards escritas con
`modelcard.write_model_card`, documentos de endurecimiento
`govpolicy.HardeningDocument(...).to_dict()` y archivos arbitrarios (bytes).
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tools.cards import assess, core, datacard, govpolicy, modelcard, resolvers

H = "a" * 64
T0 = "2026-10-01T10:00:00Z"
NOW = "2026-10-02T00:00:00Z"

KINDS_GOBERNANZA = {"model_card", "governance_policy", "evidence_document"}
LOS_QUINCE_KINDS = set(core.OBSERVED_KINDS) - {"report_artifact"}

REL_POLITICA = "governance/hardening/pol-gov.json"
REL_DOCUMENTO = "docs/informe.bin"

LOCATORS_HOSTILES = (
    None,
    "/abs/doc.json",
    "C:/x/doc.json",
    "C:doc.json",
    "a:b.json",
    "..\\ajeno.json",
    "docs\\informe.bin",
    "../ajeno.json",
    "docs/../../ajeno.json",
    "~/doc.json",
    "https://host/doc.json",
    "",
    5,
)


# ---------------------------------------------------------------------------
# Constructores de objetos reales y helpers
# ---------------------------------------------------------------------------


def _reloj():
    return NOW


def _model_card(model_id="modelo-a", version="1.0", descripcion="Modelo de prueba"):
    return core.CardEnvelope(
        schema_version=1,
        card_kind="model_card",
        kind_schema_version=1,
        card_id=modelcard.model_card_id(model_id, version),
        title="Modelo",
        subject=model_id,
        created_at=T0,
        generated_at=T0,
        body={"model_id": model_id, "model_version": version, "description": descripcion},
    )


def _data_card(card_id="clientes-card"):
    evidencia = core.EvidenceRef("obs-clientes", "source_observation", f"clientes__{H[:12]}", H, T0)
    return core.CardEnvelope(
        schema_version=1,
        card_kind="data_card",
        kind_schema_version=1,
        card_id=card_id,
        title="Clientes",
        subject="clientes",
        created_at=T0,
        generated_at=T0,
        evidence=(evidencia,),
        body={
            "description": "Tabla de clientes",
            "source_refs": [
                {"source_ref_id": "principal", "source_id": "clientes", "observation_evidence_id": "obs-clientes"}
            ],
        },
    )


def _documento_endurecimiento(policy_id="pol-gov", base_version=1):
    return govpolicy.HardeningDocument(policy_id=policy_id, base_version=base_version).to_dict()


def _escribir_json(raiz, rel, obj):
    ruta = Path(raiz) / rel
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    return ruta


def _escribir_bytes(raiz, rel, datos):
    ruta = Path(raiz) / rel
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(datos)
    return ruta


def _sha_bytes(datos):
    return hashlib.sha256(datos).hexdigest()


def _ref(kind, ref_id, locator=None, member=None, sha=H):
    return core.EvidenceRef("ev1", kind, ref_id, sha, T0, member=member, locator=locator)


def _falso(ref_id=None, locator=None, member=None, kind="x"):
    """Ref hostil que `EvidenceRef` real rechazaria en construccion."""
    return SimpleNamespace(ref_id=ref_id, locator=locator, member=member, kind=kind, content_sha256=H)


def _ref_model_card(card, locator="canonico"):
    if locator == "canonico":
        locator = f"governance/cards/model/{card.card_id}.json"
    return _ref("model_card", card.revision_id(), locator=locator, sha=card.content_sha256())


def _ref_politica(documento, locator=REL_POLITICA, ref_id=None):
    return _ref(
        "governance_policy",
        ref_id or documento["policy_id"],
        locator=locator,
        sha=resolvers.hash_document(documento),
    )


def _ref_documento(datos, locator=REL_DOCUMENTO, ref_id="informe-1"):
    return _ref("evidence_document", ref_id, locator=locator, sha=_sha_bytes(datos))


def _symlink(destino, origen, directorio=True):
    try:
        os.symlink(str(origen), str(destino), target_is_directory=directorio)
    except (OSError, NotImplementedError, AttributeError):
        raise unittest.SkipTest("el SO no permite crear symlinks")


def _arbol(raiz):
    salida = []
    for base, dirs, archivos in os.walk(raiz):
        for nombre in sorted(dirs) + sorted(archivos):
            ruta = Path(base) / nombre
            st = ruta.lstat()
            salida.append((ruta.relative_to(raiz).as_posix(), ruta.is_dir(), st.st_size, st.st_mtime_ns))
    return sorted(salida)


class _Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.raiz = Path(self._tmp.name).resolve()
        self.repo = self.raiz / "repo"
        self.repo.mkdir()
        self.fuera = self.raiz / "fuera"
        self.fuera.mkdir()

    def assertEstado(self, resolucion, estado):
        self.assertIsInstance(resolucion, assess.Resolution)
        self.assertEqual(resolucion.state, estado, resolucion.detail)
        if estado != assess.RES_FOUND:
            self.assertIsNone(resolucion.current_sha256)


# ---------------------------------------------------------------------------
# model_card (R57)
# ---------------------------------------------------------------------------


class TestModelCardResolver(_Base):
    def _resolver(self):
        return resolvers.model_card_resolver(self.repo)

    def _escribir(self, card=None, **kw):
        card = card or _model_card(**kw)
        modelcard.write_model_card(self.repo, card, clock=_reloj)
        return card

    def _ruta(self, card):
        return self.repo / "governance" / "cards" / "model" / f"{card.card_id}.json"

    def test_found_con_hash_de_la_card_real(self):
        card = self._escribir()
        res = self._resolver()(_ref_model_card(card))
        self.assertEstado(res, assess.RES_FOUND)
        self.assertEqual(res.current_sha256, card.content_sha256())

    def test_found_sin_locator(self):
        card = self._escribir()
        res = self._resolver()(_ref_model_card(card, locator=None))
        self.assertEstado(res, assess.RES_FOUND)
        self.assertEqual(res.current_sha256, card.content_sha256())

    def test_missing_si_no_existe_la_card(self):
        self.assertEstado(self._resolver()(_ref_model_card(_model_card())), assess.RES_MISSING)

    def test_card_incompleta_pero_integra_queda_found_y_no_se_evalua(self):
        card = self._escribir()
        evaluacion = modelcard.evaluate_model_card(card, self.repo, clock=_reloj)
        self.assertNotEqual(evaluacion.card_status, assess.CARD_COMPLETE)
        self.assertNotEqual(evaluacion.card_status, assess.CARD_INVALID)
        llamadas = []

        def _explota(*args, **kwargs):
            llamadas.append(1)
            raise AssertionError("el resolver no debe evaluar la Model Card")

        resolver = self._resolver()
        with mock.patch.object(assess, "evaluate", _explota), mock.patch.object(
            assess, "evaluate_file", _explota
        ), mock.patch.object(modelcard, "evaluate_model_card", _explota), mock.patch.object(
            assess, "evaluar_evidencia", _explota
        ):
            res = resolver(_ref_model_card(card))
        self.assertEqual(llamadas, [])
        self.assertEstado(res, assess.RES_FOUND)
        self.assertEqual(res.current_sha256, card.content_sha256())

    def test_pin_fresh_con_card_incompleta(self):
        card = self._escribir()
        defaults = resolvers.default_resolvers(self.repo)
        self.assertEqual(assess.evaluar_evidencia(_ref_model_card(card), defaults), assess.EV_FRESH)

    def test_card_editada_da_hash_distinto_y_pin_stale(self):
        card = self._escribir()
        pin = _ref_model_card(card)
        defaults = resolvers.default_resolvers(self.repo)
        self.assertEqual(assess.evaluar_evidencia(pin, defaults), assess.EV_FRESH)
        nueva = _model_card(descripcion="Modelo editado")
        modelcard.write_model_card(self.repo, nueva, replace=True, clock=_reloj)
        res = self._resolver()(pin)
        self.assertEstado(res, assess.RES_FOUND)
        self.assertNotEqual(res.current_sha256, card.content_sha256())
        self.assertEqual(res.current_sha256, nueva.content_sha256())
        self.assertEqual(assess.evaluar_evidencia(pin, defaults), assess.EV_STALE)

    def test_solo_generated_at_distinto_no_cambia_el_hash(self):
        card = self._escribir()
        otra = core.CardEnvelope.from_dict(dict(card.to_dict(), generated_at="2026-10-01T12:00:00Z"))
        modelcard.write_model_card(self.repo, otra, replace=True, clock=_reloj)
        res = self._resolver()(_ref_model_card(card))
        self.assertEstado(res, assess.RES_FOUND)
        self.assertEqual(res.current_sha256, card.content_sha256())

    def test_locator_no_canonico_es_unverifiable(self):
        card = self._escribir()
        copia = self.repo / "copia" / f"{card.card_id}.json"
        copia.parent.mkdir()
        copia.write_bytes(self._ruta(card).read_bytes())
        for locator in (
            f"copia/{card.card_id}.json",
            "governance/cards/model/otra.json",
            f"governance/cards/data/{card.card_id}.json",
            f"./governance/cards/model/{card.card_id}.json",
        ):
            with self.subTest(locator=locator):
                self.assertEstado(self._resolver()(_ref_model_card(card, locator=locator)), assess.RES_UNVERIFIABLE)

    def test_locator_hostil_es_unverifiable(self):
        card = self._escribir()
        for locator in ("/abs.json", "..\\x.json", "../x.json", "C:/x.json", 5, ""):
            with self.subTest(locator=locator):
                ref = _falso(card.revision_id(), locator=locator)
                self.assertEstado(self._resolver()(ref), assess.RES_UNVERIFIABLE)

    def test_card_kind_erroneo_es_unverifiable(self):
        # Una Data Card valida colocada en la ubicacion de Model Cards.
        dato = _data_card()
        with tempfile.TemporaryDirectory() as tmp:
            ruta = datacard.write_data_card(tmp, dato, clock=_reloj)
            contenido = Path(ruta).read_bytes()
        destino = self.repo / "governance" / "cards" / "model" / f"{dato.card_id}.json"
        destino.parent.mkdir(parents=True)
        destino.write_bytes(contenido)
        ref = _ref("model_card", dato.revision_id(), sha=dato.content_sha256())
        self.assertEstado(self._resolver()(ref), assess.RES_UNVERIFIABLE)

    def test_card_id_interno_distinto_del_ref_id_es_unverifiable(self):
        card = self._escribir()
        copia = self.repo / "governance" / "cards" / "model" / "otra-card.json"
        copia.write_bytes(self._ruta(card).read_bytes())
        ref = _ref("model_card", f"otra-card__{card.content_sha256()[:12]}", sha=card.content_sha256())
        self.assertEstado(self._resolver()(ref), assess.RES_UNVERIFIABLE)

    def test_archivo_corrupto_o_con_forma_inesperada_es_unverifiable(self):
        card = self._escribir()
        ruta = self._ruta(card)
        original = json.loads(ruta.read_text(encoding="utf-8"))
        casos = {
            "roto": b"{",
            "lista": b"[]",
            "nan": b'{"a": NaN}',
            "utf8": b"\xff\xfe",
            "vacio": b"",
            "revision_adulterada": json.dumps(dict(original, revision_id=f"{card.card_id}__000000000000")).encode(),
            "clave_status": json.dumps(dict(original, status="complete")).encode(),
            "titulo_cambiado_sin_revision": json.dumps(dict(original, title="Otro")).encode(),
        }
        for nombre, contenido in casos.items():
            with self.subTest(caso=nombre):
                ruta.write_bytes(contenido)
                self.assertEstado(self._resolver()(_ref_model_card(card)), assess.RES_UNVERIFIABLE)

    def test_ref_id_malformado_o_con_rutas_es_unverifiable(self):
        card = self._escribir()
        for ref_id in (
            card.card_id,
            f"{card.card_id}__XYZ",
            f"{card.card_id}__0123456789abc",
            f"../{card.revision_id()}",
            f"a/{card.revision_id()}",
            f"a\\{card.revision_id()}",
            f"/{card.revision_id()}",
            f"C:{card.revision_id()}",
            f"~{card.revision_id()}",
            "..__0123456789ab",
            "",
            None,
            5,
        ):
            with self.subTest(ref_id=ref_id):
                self.assertEstado(self._resolver()(_falso(ref_id)), assess.RES_UNVERIFIABLE)

    def test_excede_tamano_es_unverifiable(self):
        card = self._escribir()
        with mock.patch.object(resolvers, "MAX_BYTES_LECTURA", 10):
            self.assertEstado(self._resolver()(_ref_model_card(card)), assess.RES_UNVERIFIABLE)

    def test_directorio_en_la_ruta_es_unverifiable(self):
        card = _model_card()
        self._ruta(card).mkdir(parents=True)
        self.assertEstado(self._resolver()(_ref_model_card(card)), assess.RES_UNVERIFIABLE)

    def test_symlink_del_directorio_de_model_cards_que_escapa(self):
        card = _model_card()
        modelcard.write_model_card(self.fuera, card, clock=_reloj)
        (self.repo / "governance" / "cards").mkdir(parents=True)
        _symlink(self.repo / "governance" / "cards" / "model", self.fuera / "governance" / "cards" / "model")
        self.assertEstado(self._resolver()(_ref_model_card(card)), assess.RES_UNVERIFIABLE)

    def test_symlink_del_archivo_de_la_card_que_escapa(self):
        card = _model_card()
        ruta_fuera = modelcard.write_model_card(self.fuera, card, clock=_reloj)
        directorio = self.repo / "governance" / "cards" / "model"
        directorio.mkdir(parents=True)
        _symlink(directorio / f"{card.card_id}.json", ruta_fuera, directorio=False)
        self.assertEstado(self._resolver()(_ref_model_card(card)), assess.RES_UNVERIFIABLE)


# ---------------------------------------------------------------------------
# governance_policy (R56)
# ---------------------------------------------------------------------------


class TestGovernancePolicyResolver(_Base):
    def _resolver(self):
        return resolvers.governance_policy_resolver(self.repo)

    def _escribir(self, documento=None):
        documento = documento or _documento_endurecimiento()
        _escribir_json(self.repo, REL_POLITICA, documento)
        return documento

    def test_found_con_hash_document(self):
        documento = self._escribir()
        res = self._resolver()(_ref_politica(documento))
        self.assertEstado(res, assess.RES_FOUND)
        self.assertEqual(res.current_sha256, resolvers.hash_document(documento))

    def test_missing_si_el_archivo_no_existe(self):
        self.assertEstado(self._resolver()(_ref_politica(_documento_endurecimiento())), assess.RES_MISSING)

    def test_policy_id_interno_distinto_del_ref_id_es_unverifiable(self):
        documento = self._escribir()
        self.assertEstado(
            self._resolver()(_ref_politica(documento, ref_id="otra-politica")), assess.RES_UNVERIFIABLE
        )

    def test_documento_modificado_da_hash_distinto_y_pin_stale(self):
        original = self._escribir()
        pin = _ref_politica(original)
        defaults = resolvers.default_resolvers(self.repo)
        self.assertEqual(assess.evaluar_evidencia(pin, defaults), assess.EV_FRESH)
        modificado = self._escribir(_documento_endurecimiento(base_version=2))
        res = self._resolver()(pin)
        self.assertEstado(res, assess.RES_FOUND)
        self.assertEqual(res.current_sha256, resolvers.hash_document(modificado))
        self.assertNotEqual(res.current_sha256, resolvers.hash_document(original))
        self.assertEqual(assess.evaluar_evidencia(pin, defaults), assess.EV_STALE)

    def test_locator_hostil_es_unverifiable(self):
        documento = self._escribir()
        (self.raiz / "ajeno.json").write_text(json.dumps(documento), encoding="utf-8")
        for locator in LOCATORS_HOSTILES:
            with self.subTest(locator=locator):
                self.assertEstado(
                    self._resolver()(_falso(documento["policy_id"], locator=locator)), assess.RES_UNVERIFIABLE
                )

    def test_json_invalido_o_forma_inesperada_es_unverifiable(self):
        documento = self._escribir()
        ruta = self.repo / REL_POLITICA
        for contenido in ("{", "[]", "null", '{"policy_id": NaN}', ""):
            with self.subTest(contenido=contenido):
                ruta.write_text(contenido, encoding="utf-8")
                self.assertEstado(self._resolver()(_ref_politica(documento)), assess.RES_UNVERIFIABLE)
        ruta.write_bytes(b"\xff\xfe")
        self.assertEstado(self._resolver()(_ref_politica(documento)), assess.RES_UNVERIFIABLE)

    def test_ref_id_hostil_es_unverifiable(self):
        self._escribir()
        for ref_id in ("../pol-gov", "a/pol-gov", "a\\pol-gov", "C:pol-gov", "~pol-gov", ".pol", "", None, 5):
            with self.subTest(ref_id=ref_id):
                self.assertEstado(self._resolver()(_falso(ref_id, locator=REL_POLITICA)), assess.RES_UNVERIFIABLE)

    def test_locator_directorio_es_unverifiable(self):
        (self.repo / REL_POLITICA).mkdir(parents=True)
        self.assertEstado(self._resolver()(_ref_politica(_documento_endurecimiento())), assess.RES_UNVERIFIABLE)

    def test_excede_tamano_es_unverifiable(self):
        documento = self._escribir()
        with mock.patch.object(resolvers, "MAX_BYTES_LECTURA", 10):
            self.assertEstado(self._resolver()(_ref_politica(documento)), assess.RES_UNVERIFIABLE)

    def test_symlink_de_archivo_que_escapa(self):
        documento = _documento_endurecimiento()
        _escribir_json(self.fuera, "pol.json", documento)
        (self.repo / "governance" / "hardening").mkdir(parents=True)
        _symlink(self.repo / REL_POLITICA, self.fuera / "pol.json", directorio=False)
        self.assertEstado(self._resolver()(_ref_politica(documento)), assess.RES_UNVERIFIABLE)

    def test_symlink_de_directorio_que_escapa(self):
        documento = _documento_endurecimiento()
        _escribir_json(self.fuera, "pol-gov.json", documento)
        (self.repo / "governance").mkdir()
        _symlink(self.repo / "governance" / "hardening", self.fuera)
        self.assertEstado(self._resolver()(_ref_politica(documento)), assess.RES_UNVERIFIABLE)


# ---------------------------------------------------------------------------
# evidence_document (R45, R58)
# ---------------------------------------------------------------------------


class TestEvidenceDocumentResolver(_Base):
    CONTENIDO = b"%PDF-1.4\nreporte externo de fairness\n%%EOF\n"

    def _resolver(self):
        return resolvers.evidence_document_resolver(self.repo)

    def _escribir(self, datos=None, rel=REL_DOCUMENTO):
        datos = self.CONTENIDO if datos is None else datos
        _escribir_bytes(self.repo, rel, datos)
        return datos

    def test_integro_da_found_con_sha256_de_los_bytes(self):
        datos = self._escribir()
        res = self._resolver()(_ref_documento(datos))
        self.assertEstado(res, assess.RES_FOUND)
        self.assertEqual(res.current_sha256, hashlib.sha256(datos).hexdigest())

    def test_pin_fresh_y_cambiar_un_byte_deja_stale(self):
        datos = self._escribir()
        pin = _ref_documento(datos)
        defaults = resolvers.default_resolvers(self.repo)
        self.assertEqual(assess.evaluar_evidencia(pin, defaults), assess.EV_FRESH)
        cambiado = bytearray(datos)
        cambiado[-2] ^= 0x01
        self._escribir(bytes(cambiado))
        res = self._resolver()(pin)
        self.assertEstado(res, assess.RES_FOUND)
        self.assertNotEqual(res.current_sha256, _sha_bytes(datos))
        self.assertEqual(res.current_sha256, _sha_bytes(bytes(cambiado)))
        self.assertEqual(assess.evaluar_evidencia(pin, defaults), assess.EV_STALE)

    def test_ausente_es_missing(self):
        self.assertEstado(self._resolver()(_ref_documento(self.CONTENIDO)), assess.RES_MISSING)
        self.assertEqual(
            assess.evaluar_evidencia(_ref_documento(self.CONTENIDO), resolvers.default_resolvers(self.repo)),
            assess.EV_UNRESOLVABLE,
        )

    def test_locator_hostil_es_unverifiable(self):
        self._escribir()
        (self.raiz / "ajeno.bin").write_bytes(b"ajeno")
        for locator in LOCATORS_HOSTILES + ("..\\ajeno.bin", "../ajeno.bin"):
            with self.subTest(locator=locator):
                self.assertEstado(self._resolver()(_falso("informe-1", locator=locator)), assess.RES_UNVERIFIABLE)

    def test_directorio_es_unverifiable(self):
        (self.repo / REL_DOCUMENTO).mkdir(parents=True)
        self.assertEstado(self._resolver()(_ref_documento(self.CONTENIDO)), assess.RES_UNVERIFIABLE)

    def test_symlink_de_archivo_que_escapa(self):
        _escribir_bytes(self.fuera, "informe.bin", self.CONTENIDO)
        (self.repo / "docs").mkdir()
        _symlink(self.repo / REL_DOCUMENTO, self.fuera / "informe.bin", directorio=False)
        self.assertEstado(self._resolver()(_ref_documento(self.CONTENIDO)), assess.RES_UNVERIFIABLE)

    def test_symlink_de_directorio_que_escapa(self):
        _escribir_bytes(self.fuera, "informe.bin", self.CONTENIDO)
        _symlink(self.repo / "docs", self.fuera)
        self.assertEstado(self._resolver()(_ref_documento(self.CONTENIDO)), assess.RES_UNVERIFIABLE)

    def test_excede_max_bytes_lectura_es_unverifiable(self):
        self._escribir(b"x" * 20)
        with mock.patch.object(resolvers, "MAX_BYTES_LECTURA", 10):
            self.assertEstado(self._resolver()(_ref_documento(b"x" * 20)), assess.RES_UNVERIFIABLE)
        # Justo en el tope sigue siendo verificable.
        self._escribir(b"y" * 10)
        with mock.patch.object(resolvers, "MAX_BYTES_LECTURA", 10):
            res = self._resolver()(_ref_documento(b"y" * 10))
        self.assertEstado(res, assess.RES_FOUND)
        self.assertEqual(res.current_sha256, _sha_bytes(b"y" * 10))

    def test_cualquier_tipo_de_archivo_se_hashea_sin_interpretarlo(self):
        casos = {
            "binario_con_nul": b"\x00\x01\x02\xff\xfe\x00",
            "vacio": b"",
            "utf8_invalido": b"\xff\xfe\xfd",
            "json_no_canonico": b'{ "b" : 1,\n  "a" : NaN }',
            "json_lista": b"[1,  2]",
            "crlf": b"linea1\r\nlinea2\r\n",
            "lf": b"linea1\nlinea2\n",
        }
        hashes = set()
        for nombre, datos in casos.items():
            with self.subTest(caso=nombre):
                self._escribir(datos, rel=f"docs/{nombre}.dat")
                res = self._resolver()(_ref_documento(datos, locator=f"docs/{nombre}.dat"))
                self.assertEstado(res, assess.RES_FOUND)
                self.assertEqual(res.current_sha256, hashlib.sha256(datos).hexdigest())
                hashes.add(res.current_sha256)
        self.assertEqual(len(hashes), len(casos))

    def test_json_se_hashea_por_bytes_y_no_por_json_canonico(self):
        datos = b'{ "a" : 1 }\n'
        self._escribir(datos, rel="docs/doc.json")
        res = self._resolver()(_ref_documento(datos, locator="docs/doc.json"))
        self.assertEqual(res.current_sha256, _sha_bytes(datos))
        self.assertNotEqual(res.current_sha256, resolvers.hash_document(json.loads(datos)))

    def test_ref_id_libre_no_se_usa_para_rutas(self):
        datos = self._escribir()
        otro = b"contenido de otro archivo"
        _escribir_bytes(self.repo, "docs/doc-b", otro)
        _escribir_bytes(self.raiz, "secreto", b"fuera del repo")
        _escribir_bytes(self.repo, "secreto", b"dentro del repo")
        resolver = self._resolver()
        # Un ref_id valido que coincide con el nombre de OTRO archivo no cambia la ruta: manda el locator.
        res = resolver(_ref_documento(datos, ref_id="doc-b"))
        self.assertEstado(res, assess.RES_FOUND)
        self.assertEqual(res.current_sha256, _sha_bytes(datos))
        self.assertNotEqual(res.current_sha256, _sha_bytes(otro))
        # ref_id con traversal / rutas: unverifiable, y nunca abre otro archivo.
        for ref_id in ("../secreto", "..", "../repo/secreto", "docs/doc-b", "..\\secreto", "C:secreto", "/secreto"):
            with self.subTest(ref_id=ref_id):
                res = resolver(_falso(ref_id, locator=REL_DOCUMENTO))
                self.assertEstado(res, assess.RES_UNVERIFIABLE)
        # Sin locator, el ref_id nunca se usa como ruta aunque exista un archivo con ese nombre.
        res = resolver(_falso("secreto", locator=None))
        self.assertEstado(res, assess.RES_UNVERIFIABLE)

    def test_locator_bajo_data_es_unverifiable_y_no_se_lee_el_archivo(self):
        for rel in ("data/x", "DATA/x", "Data/x", "data/raw/y.csv", "./data/x"):
            _escribir_bytes(self.repo, rel, b"dato sensible")
        resolver = self._resolver()
        for locator in ("data/x", "DATA/x", "Data/x", "data/raw/y.csv", "./data/x"):
            with self.subTest(locator=locator):
                with mock.patch("builtins.open", side_effect=AssertionError("no debe abrir")), mock.patch.object(
                    Path, "read_bytes", side_effect=AssertionError("no debe leer")
                ), mock.patch.object(Path, "open", side_effect=AssertionError("no debe abrir")):
                    res = resolver(_falso("informe-1", locator=locator))
                self.assertEstado(res, assess.RES_UNVERIFIABLE)
                self.assertIn("data/", res.detail)

    def test_variantes_windows_de_data_son_unverifiable_sin_abrir_archivos(self):
        _escribir_bytes(self.repo, "data/x", b"dato sensible")
        resolver = self._resolver()
        locators = (
            "data./x",
            "data /x",
            "data.../x",
            "DATA /x",
            "data . /x",
            "data\\x",
            "a/../data/x",
            "./data/x",
            "docs./x",
            "docs/x. ",
        )
        for locator in locators:
            with self.subTest(locator=locator):
                with mock.patch("builtins.open", side_effect=AssertionError("no debe abrir")), mock.patch.object(
                    Path, "read_bytes", side_effect=AssertionError("no debe leer")
                ), mock.patch.object(Path, "open", side_effect=AssertionError("no debe abrir")):
                    res = resolver(_falso("informe-1", locator=locator))
                self.assertEstado(res, assess.RES_UNVERIFIABLE)

    def test_locator_fuera_de_data_sigue_found(self):
        for rel in ("docs/x.pdf", "reports/x.html", "datasets_docs/x.txt", "docs/data_notes.txt"):
            datos = b"contenido " + rel.encode()
            self._escribir(datos, rel=rel)
            with self.subTest(locator=rel):
                res = self._resolver()(_ref_documento(datos, locator=rel))
                self.assertEstado(res, assess.RES_FOUND)
                self.assertEqual(res.current_sha256, _sha_bytes(datos))

    def test_docstring_indica_que_la_evidencia_vive_fuera_de_data(self):
        doc = " ".join((resolvers.evidence_document_resolver.__doc__ or "").split())
        self.assertIn("fuera de `data/`", doc)
        self.assertIn("nunca abre datos del proyecto", doc)

    def test_ref_id_invalido_es_unverifiable(self):
        self._escribir()
        for ref_id in ("", None, 5, "A B", "x" * 65):
            with self.subTest(ref_id=ref_id):
                self.assertEstado(self._resolver()(_falso(ref_id, locator=REL_DOCUMENTO)), assess.RES_UNVERIFIABLE)

    def test_documento_que_afirma_que_el_modelo_es_justo_no_produce_conclusion(self):
        datos = (
            b"%PDF-1.4\n% informe externo\nCONCLUSION: el modelo es justo, seguro y sin sesgo.\n"
            b"\xe2\x9c\x94 aprobado por el auditor\n%%EOF\n"
        )
        self._escribir(datos)
        res = self._resolver()(_ref_documento(datos))
        # Solo existencia + hash de bytes: ningun texto del documento llega a la resolucion.
        self.assertEstado(res, assess.RES_FOUND)
        self.assertEqual(res.current_sha256, _sha_bytes(datos))
        self.assertEqual(res.detail, "")
        self.assertNotIn("justo", repr(res).lower())
        self.assertNotIn("aprobado", repr(res).lower())
        # El unico veredicto posible sobre el pin es de frescura, nunca de contenido.
        defaults = resolvers.default_resolvers(self.repo)
        self.assertEqual(assess.evaluar_evidencia(_ref_documento(datos), defaults), assess.EV_FRESH)

    def test_el_resolver_no_interpreta_el_contenido(self):
        datos = self._escribir()
        # Si hiciera cualquier parseo (json/decodificacion) se veria acá.
        with mock.patch.object(resolvers.json, "loads", side_effect=AssertionError("no debe parsear JSON")):
            res = self._resolver()(_ref_documento(datos))
        self.assertEstado(res, assess.RES_FOUND)

    def test_docstring_contiene_las_frases_de_r45(self):
        doc = " ".join((resolvers.evidence_document_resolver.__doc__ or "").split())
        frases = (
            "existencia del documento",
            "integridad de bytes",
            "NO demuestra que el contenido sea correcto",
            "que la metodología sea válida",
            "que un análisis de fairness sea bueno",
            "que privacy/security estén resueltas",
            "ni que una conclusión del documento sea verdadera",
            "«existe evidencia documental íntegra vinculada a este requisito»",
        )
        for frase in frases:
            with self.subTest(frase=frase):
                self.assertIn(frase, doc)


# ---------------------------------------------------------------------------
# default_resolvers, robustez y solo lectura (R4, R59)
# ---------------------------------------------------------------------------


class TestDefaultResolversGobernanza(_Base):
    def test_exactamente_los_quince_kinds(self):
        mapa = resolvers.default_resolvers(self.repo)
        self.assertEqual(set(mapa), LOS_QUINCE_KINDS)
        self.assertEqual(len(mapa), 15)
        self.assertTrue(KINDS_GOBERNANZA <= set(mapa))
        for kind, resolver in mapa.items():
            with self.subTest(kind=kind):
                self.assertTrue(callable(resolver))

    def test_report_artifact_sigue_unverifiable(self):
        mapa = resolvers.default_resolvers(self.repo)
        self.assertNotIn("report_artifact", mapa)
        ref = core.EvidenceRef("ev1", "report_artifact", "x-1", H, T0)
        self.assertEqual(assess.evaluar_evidencia(ref, mapa), assess.EV_UNVERIFIABLE)

    def test_constantes_de_kind_coinciden_con_core(self):
        constantes = {
            resolvers.KIND_MODEL_CARD,
            resolvers.KIND_GOVERNANCE_POLICY,
            resolvers.KIND_EVIDENCE_DOCUMENT,
        }
        self.assertEqual(constantes, KINDS_GOBERNANZA)
        self.assertTrue(constantes <= set(core.OBSERVED_KINDS))

    def test_kinds_nuevos_resuelven_por_el_mapa_por_defecto(self):
        card = _model_card()
        modelcard.write_model_card(self.repo, card, clock=_reloj)
        documento = _documento_endurecimiento()
        _escribir_json(self.repo, REL_POLITICA, documento)
        datos = b"bytes de un reporte"
        _escribir_bytes(self.repo, REL_DOCUMENTO, datos)
        mapa = resolvers.default_resolvers(self.repo)
        self.assertEqual(assess.evaluar_evidencia(_ref_model_card(card), mapa), assess.EV_FRESH)
        self.assertEqual(assess.evaluar_evidencia(_ref_politica(documento), mapa), assess.EV_FRESH)
        self.assertEqual(assess.evaluar_evidencia(_ref_documento(datos), mapa), assess.EV_FRESH)

    def test_repo_root_invalido_lanza_card_error(self):
        with self.assertRaises(core.CardError):
            resolvers.default_resolvers(None)


class TestNuncaLanzanGobernanza(_Base):
    def _basura(self):
        return (
            None,
            5,
            "texto",
            b"bytes",
            object(),
            SimpleNamespace(),
            SimpleNamespace(ref_id=b"x", locator=5, member=[], kind=None),
            SimpleNamespace(ref_id="a" * 10000, locator="b" * 10000, member="a@" + "c" * 10000),
            SimpleNamespace(ref_id="\x00", locator="\x00", member="\x00"),
            SimpleNamespace(ref_id="a__0123456789ab\x00", locator="a/\x00b.json", member="x@y"),
            _falso("pol-gov", locator="governance/hardening/pol-gov.json"),
            _falso("informe-1", locator="docs/informe.bin"),
        )

    def test_basura_nunca_lanza_y_nunca_es_found(self):
        for kind, resolver in resolvers.default_resolvers(self.repo).items():
            for i, basura in enumerate(self._basura()):
                with self.subTest(kind=kind, caso=i):
                    res = resolver(basura)
                    self.assertIsInstance(res, assess.Resolution)
                    self.assertNotEqual(res.state, assess.RES_FOUND)

    def test_repo_inexistente_no_lanza(self):
        inexistente = self.raiz / "no_existe"
        mapa = resolvers.default_resolvers(inexistente)
        for kind in KINDS_GOBERNANZA:
            with self.subTest(kind=kind):
                ref = _falso("clientes__0123456789ab", locator="c.json", member="x@y")
                self.assertIn(mapa[kind](ref).state, (assess.RES_MISSING, assess.RES_UNVERIFIABLE))

    def test_error_inesperado_de_io_se_convierte_en_unverifiable(self):
        _escribir_bytes(self.repo, REL_DOCUMENTO, b"datos")
        resolver = resolvers.evidence_document_resolver(self.repo)
        with mock.patch.object(Path, "is_file", side_effect=PermissionError("denegado")):
            res = resolver(_ref_documento(b"datos"))
        self.assertEstado(res, assess.RES_UNVERIFIABLE)


class TestSoloLecturaGobernanza(_Base):
    def test_ningun_resolver_modifica_el_arbol(self):
        card = _model_card()
        modelcard.write_model_card(self.repo, card, clock=_reloj)
        documento = _documento_endurecimiento()
        _escribir_json(self.repo, REL_POLITICA, documento)
        datos = b"%PDF reporte"
        _escribir_bytes(self.repo, REL_DOCUMENTO, datos)

        antes = _arbol(self.raiz)
        mapa = resolvers.default_resolvers(self.repo)
        refs = (
            _ref_model_card(card),
            _ref("model_card", "inexistente__0123456789ab"),
            _ref_politica(documento),
            _ref("governance_policy", "pol-otra", locator="governance/hardening/no_esta.json"),
            _ref_documento(datos),
            _ref("evidence_document", "x-1", locator="docs/no_esta.bin"),
            _falso("../../x"),
        )
        for ref in refs:
            for resolver in mapa.values():
                resolver(ref)
        self.assertEqual(_arbol(self.raiz), antes)

    def test_no_crea_directorios_en_repo_vacio(self):
        antes = _arbol(self.raiz)
        mapa = resolvers.default_resolvers(self.repo)
        for kind in KINDS_GOBERNANZA:
            mapa[kind](_ref("model_card", "x-1__0123456789ab"))
            mapa[kind](_falso("x-1", locator="docs/a.bin"))
        for resolver in mapa.values():
            resolver(_ref("model_card", "x-1__0123456789ab"))
        self.assertEqual(_arbol(self.raiz), antes)
        self.assertFalse((self.repo / ".harmessi").exists())
        self.assertFalse((self.repo / "governance").exists())


if __name__ == "__main__":
    unittest.main()

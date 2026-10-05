"""Tests de ubicación y escritura de Model Cards (`card_path`, `write_model_card`;
Change `20261005-model-cards`, R32-R34)."""
from __future__ import annotations

import dataclasses
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools.cards import assess, core, datacard, modelcard, resolvers  # noqa: F401

T0 = "2026-10-01T10:00:00Z"
NOW = "2026-10-04T00:00:00Z"
REPO = Path(__file__).resolve().parents[3]


def codigo_de(funcion, *args, **kwargs):
    try:
        funcion(*args, **kwargs)
    except core.CardError as exc:
        return exc.code
    raise AssertionError("no lanzó CardError")


def hacer_card(model_id="clasificador", model_version="1.0.0", descripcion="Modelo de prueba", **kw):
    base = dict(
        schema_version=1,
        card_kind="model_card",
        kind_schema_version=1,
        card_id=modelcard.model_card_id(model_id, model_version),
        title="Model Card de prueba",
        subject=model_id,
        created_at=T0,
        generated_at=T0,
        body={"model_id": model_id, "model_version": model_version, "description": descripcion},
    )
    base.update(kw)
    return core.CardEnvelope(**base)


class BaseTmp(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.raiz = Path(self._tmp.name).resolve()

    @property
    def governance(self):
        return self.raiz / "governance"

    def destino(self, card_id="clasificador__1_0_0"):
        return self.raiz / "governance" / "cards" / "model" / f"{card_id}.json"

    def escribir_ajeno(self, contenido: bytes, card_id="clasificador__1_0_0"):
        ruta = self.destino(card_id)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_bytes(contenido)
        return ruta

    def escribir(self, card=None, **kw):
        return modelcard.write_model_card(self.raiz, card or hacer_card(), clock=lambda: NOW, **kw)


class TestCardPath(BaseTmp):
    def test_ruta_bajo_governance_cards_model(self):
        ruta = modelcard.card_path(self.raiz, "clasificador__1_0_0")
        self.assertEqual(ruta.relative_to(self.raiz).as_posix(), "governance/cards/model/clasificador__1_0_0.json")
        self.assertEqual(modelcard.CARD_DIR_PARTES, ("governance", "cards", "model"))

    def test_acepta_project_root_str(self):
        self.assertEqual(modelcard.card_path(str(self.raiz), "m1").name, "m1.json")

    def test_no_crea_ni_escanea_nada(self):
        modelcard.card_path(self.raiz, "m1")
        self.assertFalse(self.governance.exists())

    def test_card_id_invalido_o_con_escape(self):
        invalidos = (
            "", "../x", "..", "a/b", "a\\b", "A", "C:\\x", "/abs", "x.json", "con espacio",
            "a" * 65, "none", "null", "default", "status", None, 5, ["a"],
        )
        for card_id in invalidos:
            with self.subTest(card_id=card_id):
                self.assertEqual(codigo_de(modelcard.card_path, self.raiz, card_id), core.CODE_ID_INVALID)
        self.assertFalse(self.governance.exists())

    def test_project_root_invalido(self):
        self.assertEqual(codigo_de(modelcard.card_path, None, "m1"), modelcard.CODE_PATH_INVALID)

    def test_symlink_que_escapa_de_project_root(self):
        with tempfile.TemporaryDirectory() as afuera:
            try:
                os.symlink(afuera, self.governance, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks no disponibles en este entorno")
            self.assertEqual(codigo_de(modelcard.card_path, self.raiz, "m1"), modelcard.CODE_PATH_INVALID)


class TestWriteModelCard(BaseTmp):
    def test_crea_directorios_y_escribe(self):
        self.assertFalse(self.governance.exists())
        ruta = self.escribir()
        self.assertEqual(ruta, modelcard.card_path(self.raiz, "clasificador__1_0_0"))
        self.assertTrue(ruta.is_file())
        self.assertEqual(assess.read_card(ruta).to_dict(), hacer_card().to_dict())
        self.assertEqual(os.listdir(ruta.parent), ["clasificador__1_0_0.json"])

    def test_segundo_write_sin_replace_falla_y_no_toca_el_original(self):
        ruta = self.escribir()
        antes = ruta.read_bytes()
        codigo = codigo_de(modelcard.write_model_card, self.raiz, hacer_card(descripcion="Otra"), clock=lambda: NOW)
        self.assertIn(codigo, (modelcard.CODE_EXISTS, core.CODE_IO_ERROR))
        self.assertEqual(ruta.read_bytes(), antes)
        self.assertEqual(os.listdir(ruta.parent), ["clasificador__1_0_0.json"])

    def test_misma_card_dos_veces_tambien_falla(self):
        self.escribir()
        self.assertIn(
            codigo_de(modelcard.write_model_card, self.raiz, hacer_card(), clock=lambda: NOW),
            (modelcard.CODE_EXISTS, core.CODE_IO_ERROR),
        )

    def test_replace_misma_identidad_crea_nueva_revision(self):
        ruta = self.escribir()
        antes = assess.read_card(ruta)
        self.escribir(hacer_card(descripcion="Descripción revisada"), replace=True)
        despues = assess.read_card(ruta)
        self.assertEqual(despues.card_id, antes.card_id)
        self.assertNotEqual(despues.revision_id(), antes.revision_id())
        self.assertEqual(despues.body["description"], "Descripción revisada")

    def test_replace_sin_archivo_es_not_found_y_no_crea_governance(self):
        self.assertEqual(
            codigo_de(modelcard.write_model_card, self.raiz, hacer_card(), replace=True, clock=lambda: NOW),
            modelcard.CODE_NOT_FOUND,
        )
        self.assertFalse(self.governance.exists())

    def test_replace_de_otra_version_no_pisa_la_card_existente(self):
        ruta = self.escribir(hacer_card(model_version="1.0.0"))
        antes = ruta.read_bytes()
        v2 = hacer_card(model_version="2.0.0")
        codigo = codigo_de(modelcard.write_model_card, self.raiz, v2, replace=True, clock=lambda: NOW)
        self.assertIn(codigo, (modelcard.CODE_NOT_FOUND, modelcard.CODE_IDENTITY_MISMATCH))
        self.assertEqual(ruta.read_bytes(), antes)
        self.assertEqual(os.listdir(ruta.parent), ["clasificador__1_0_0.json"])

    def test_nueva_version_sin_replace_es_otra_card_otro_archivo(self):
        self.escribir(hacer_card(model_version="1.0.0"))
        self.escribir(hacer_card(model_version="1.0.1"))
        self.assertEqual(
            sorted(os.listdir(self.destino().parent)), ["clasificador__1_0_0.json", "clasificador__1_0_1.json"]
        )

    def test_replace_con_otra_identidad_en_la_ruta_es_identity_mismatch(self):
        # Model Card de OTRO modelo guardada en la ruta de clasificador__1_0_0
        ajena = hacer_card(model_id="otro", model_version="1.0.0", card_id="clasificador__1_0_0")
        ajena = dataclasses.replace(ajena, body={})  # body vacío: se escribe con write_card sin validador
        ruta = self.destino()
        ruta.parent.mkdir(parents=True)
        assess.write_card(ruta, ajena, lambda: NOW)
        antes = ruta.read_bytes()
        self.assertEqual(
            codigo_de(modelcard.write_model_card, self.raiz, hacer_card(), replace=True, clock=lambda: NOW),
            modelcard.CODE_IDENTITY_MISMATCH,
        )
        self.assertEqual(ruta.read_bytes(), antes)

    def test_replace_sobre_card_de_otro_kind_es_identity_mismatch(self):
        data = core.CardEnvelope(
            schema_version=1, card_kind="data_card", kind_schema_version=1, card_id="clasificador__1_0_0",
            title="Data", subject="clasificador", created_at=T0, generated_at=T0,
        )
        ruta = self.destino()
        ruta.parent.mkdir(parents=True)
        assess.write_card(ruta, data, lambda: NOW)
        antes = ruta.read_bytes()
        self.assertEqual(
            codigo_de(modelcard.write_model_card, self.raiz, hacer_card(), replace=True, clock=lambda: NOW),
            modelcard.CODE_IDENTITY_MISMATCH,
        )
        self.assertEqual(ruta.read_bytes(), antes)

    def test_archivo_ajeno_no_se_sobrescribe(self):
        for contenido in (b"hola, esto no es una Card\n", b'{"a": 1}\n', b"", b"\xff\xfe\x00"):
            with self.subTest(contenido=contenido):
                ruta = self.escribir_ajeno(contenido)
                for replace in (False, True):
                    with self.assertRaises(core.CardError):
                        modelcard.write_model_card(self.raiz, hacer_card(), replace=replace, clock=lambda: NOW)
                    self.assertEqual(ruta.read_bytes(), contenido)
                self.assertEqual(
                    codigo_de(modelcard.write_model_card, self.raiz, hacer_card(), replace=True, clock=lambda: NOW),
                    modelcard.CODE_IDENTITY_MISMATCH,
                )
                self.assertIn(
                    codigo_de(modelcard.write_model_card, self.raiz, hacer_card(), clock=lambda: NOW),
                    (modelcard.CODE_EXISTS, core.CODE_IO_ERROR),
                )
                ruta.unlink()

    def test_directorio_en_la_ruta_de_la_card_no_se_sobrescribe(self):
        ruta = self.destino()
        ruta.mkdir(parents=True)
        for replace in (False, True):
            with self.assertRaises(core.CardError):
                modelcard.write_model_card(self.raiz, hacer_card(), replace=replace, clock=lambda: NOW)
        self.assertTrue(ruta.is_dir())

    def test_card_invalida_no_crea_governance(self):
        base = hacer_card()
        invalidas = {
            "clave desconocida": dataclasses.replace(base, body={**base.body, "inventada": 1}),
            "risk_level": dataclasses.replace(base, body={**base.body, "risk_level": "high"}),
            "description vacia": hacer_card(descripcion=" "),
            "schema ajeno": dataclasses.replace(base, kind_schema_version=2),
            "kind ajeno": dataclasses.replace(base, card_kind="data_card"),
            "card_id distinto": dataclasses.replace(base, card_id="otro__1_0_0"),
            "subject distinto": dataclasses.replace(base, subject="otro"),
            "colgante": dataclasses.replace(
                base,
                body={**base.body, "data_card_refs": [
                    {"data_card_ref_id": "dc", "role": "training", "evidence_id": "no-existe"}]},
            ),
        }
        for nombre, card in invalidas.items():
            for replace in (False, True):
                with self.subTest(caso=nombre, replace=replace):
                    with self.assertRaises(core.CardError):
                        modelcard.write_model_card(self.raiz, card, replace=replace, clock=lambda: NOW)
                    self.assertFalse(self.governance.exists())

    def test_argumento_que_no_es_card_no_crea_governance(self):
        for valor in (None, {}, "x", 5):
            with self.subTest(valor=valor):
                self.assertEqual(
                    codigo_de(modelcard.write_model_card, self.raiz, valor, clock=lambda: NOW),
                    core.CODE_FIELD_INVALID,
                )
        self.assertFalse(self.governance.exists())

    def test_cada_model_id_tiene_su_archivo(self):
        self.escribir(hacer_card("modelo-a"))
        self.escribir(hacer_card("modelo-b"))
        self.assertEqual(
            sorted(os.listdir(self.destino().parent)), ["modelo-a__1_0_0.json", "modelo-b__1_0_0.json"]
        )

    def test_no_toca_data_cards_ni_otros_directorios(self):
        self.escribir()
        self.assertEqual(os.listdir(self.governance), ["cards"])
        self.assertEqual(os.listdir(self.governance / "cards"), ["model"])


class TestImportarNoCreaGovernance(BaseTmp):
    def test_importar_el_modulo_no_crea_governance(self):
        existia = (REPO / "governance").exists()
        entorno = dict(os.environ)
        entorno["PYTHONPATH"] = str(REPO) + os.pathsep + entorno.get("PYTHONPATH", "")
        proc = subprocess.run(
            [sys.executable, "-c", "import tools.cards.modelcard, tools.cards.resolvers"],
            cwd=str(self.raiz),
            env=entorno,
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertFalse(self.governance.exists())
        self.assertEqual((REPO / "governance").exists(), existia)

    def test_card_path_validar_y_evaluar_no_crean_governance(self):
        modelcard.card_path(self.raiz, "m1")
        card = hacer_card()
        modelcard.validate_model_card(card)
        modelcard.requirements_for(card)
        modelcard.evaluate_model_card(card, self.raiz)
        self.assertFalse(self.governance.exists())
        self.assertEqual(os.listdir(self.raiz), [])


if __name__ == "__main__":
    unittest.main()

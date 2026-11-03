"""Tests de ubicación y escritura de Data Cards (`card_path`, `write_data_card`;
Change `20261002-data-cards`, R28, R30, R32)."""
from __future__ import annotations

import dataclasses
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools.cards import assess, core, datacard

T0 = "2026-10-01T10:00:00Z"
NOW = "2026-10-04T00:00:00Z"
H1 = "a" * 64
REPO = Path(__file__).resolve().parents[3]


def codigo_de(funcion, *args, **kwargs):
    try:
        funcion(*args, **kwargs)
    except core.CardError as exc:
        return exc.code
    raise AssertionError("no lanzó CardError")


def hacer_card(card_id="producto-a", descripcion="Producto de prueba", **kw):
    pin = core.EvidenceRef("ev-src-a", "source_observation", "ventas__aaaaaaaaaaaa", H1, T0)
    base = dict(
        schema_version=1,
        card_kind="data_card",
        kind_schema_version=1,
        card_id=card_id,
        title="Data Card de prueba",
        subject=card_id,
        created_at=T0,
        generated_at=T0,
        evidence=(pin,),
        claims=(core.Claim("c-src-a", "Observada", supports=("ev-src-a",), requirement_id="source_src-a"),),
        body={
            "description": descripcion,
            "source_refs": [
                {"source_ref_id": "src-a", "source_id": "ventas", "observation_evidence_id": "ev-src-a"}
            ],
        },
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

    def destino(self, card_id="producto-a"):
        return self.raiz / "governance" / "cards" / "data" / f"{card_id}.json"

    def escribir_ajeno(self, contenido: bytes, card_id="producto-a"):
        ruta = self.destino(card_id)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_bytes(contenido)
        return ruta


# ---------------------------------------------------------------------------
# card_path (R28)
# ---------------------------------------------------------------------------


class TestCardPath(BaseTmp):
    def test_ruta_bajo_governance_cards_data(self):
        ruta = datacard.card_path(self.raiz, "producto-a")
        self.assertEqual(ruta.relative_to(self.raiz).as_posix(), "governance/cards/data/producto-a.json")
        self.assertEqual(datacard.CARD_DIR_PARTES, ("governance", "cards", "data"))

    def test_acepta_project_root_str(self):
        ruta = datacard.card_path(str(self.raiz), "p1")
        self.assertEqual(ruta.name, "p1.json")

    def test_no_crea_ni_escanea_nada(self):
        datacard.card_path(self.raiz, "producto-a")
        self.assertFalse(self.governance.exists())

    def test_card_id_invalido_o_con_escape(self):
        invalidos = (
            "", "../x", "..", "a/b", "a\\b", "A", "C:\\x", "/abs", "x.json", "con espacio",
            "a" * 65, "none", "null", "default", "status", None, 5, ["a"],
        )
        for card_id in invalidos:
            with self.subTest(card_id=card_id):
                self.assertEqual(codigo_de(datacard.card_path, self.raiz, card_id), core.CODE_ID_INVALID)
        self.assertFalse(self.governance.exists())

    def test_project_root_invalido(self):
        self.assertEqual(codigo_de(datacard.card_path, None, "producto-a"), datacard.CODE_PATH_INVALID)

    def test_symlink_que_escapa_de_project_root(self):
        with tempfile.TemporaryDirectory() as afuera:
            try:
                os.symlink(afuera, self.governance, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks no disponibles en este entorno")
            self.assertEqual(codigo_de(datacard.card_path, self.raiz, "producto-a"), datacard.CODE_PATH_INVALID)


# ---------------------------------------------------------------------------
# write_data_card (R30, R32)
# ---------------------------------------------------------------------------


class TestWriteDataCard(BaseTmp):
    def escribir(self, card=None, **kw):
        return datacard.write_data_card(self.raiz, card or hacer_card(), clock=lambda: NOW, **kw)

    def test_crea_directorios_y_escribe(self):
        self.assertFalse(self.governance.exists())
        ruta = self.escribir()
        self.assertEqual(ruta, datacard.card_path(self.raiz, "producto-a"))
        self.assertTrue(ruta.is_file())
        self.assertEqual(assess.read_card(ruta).to_dict(), hacer_card().to_dict())
        # solo el archivo, sin temporales residuales
        self.assertEqual(os.listdir(ruta.parent), ["producto-a.json"])

    def test_segundo_write_sin_replace_falla_y_no_toca_el_original(self):
        ruta = self.escribir()
        antes = ruta.read_bytes()
        otra = hacer_card(descripcion="Otra descripción")
        codigo = codigo_de(datacard.write_data_card, self.raiz, otra, clock=lambda: NOW)
        self.assertIn(codigo, (datacard.CODE_EXISTS, core.CODE_IO_ERROR))
        self.assertEqual(ruta.read_bytes(), antes)
        self.assertEqual(os.listdir(ruta.parent), ["producto-a.json"])

    def test_misma_card_dos_veces_tambien_falla(self):
        self.escribir()
        self.assertIn(
            codigo_de(datacard.write_data_card, self.raiz, hacer_card(), clock=lambda: NOW),
            (datacard.CODE_EXISTS, core.CODE_IO_ERROR),
        )

    def test_replace_true_misma_identidad_crea_nueva_revision(self):
        ruta = self.escribir()
        antes = assess.read_card(ruta)
        nueva = hacer_card(descripcion="Descripción revisada")
        self.escribir(nueva, replace=True)
        despues = assess.read_card(ruta)
        self.assertEqual(despues.card_id, antes.card_id)
        self.assertNotEqual(despues.revision_id(), antes.revision_id())
        self.assertEqual(despues.body["description"], "Descripción revisada")

    def test_replace_true_sin_archivo_existente_es_not_found_y_no_crea_governance(self):
        self.assertEqual(
            codigo_de(datacard.write_data_card, self.raiz, hacer_card(), replace=True, clock=lambda: NOW),
            datacard.CODE_NOT_FOUND,
        )
        self.assertFalse(self.governance.exists())

    def test_replace_true_con_otra_identidad_es_identity_mismatch(self):
        # Card de datos de OTRO card_id guardada en la ruta de producto-a
        ajena = hacer_card(card_id="otro-producto")
        ruta = self.destino("producto-a")
        ruta.parent.mkdir(parents=True)
        assess.write_card(ruta, ajena, lambda: NOW, validate_body=datacard.body_validator_for(ajena))
        antes = ruta.read_bytes()
        self.assertEqual(
            codigo_de(datacard.write_data_card, self.raiz, hacer_card(), replace=True, clock=lambda: NOW),
            datacard.CODE_IDENTITY_MISMATCH,
        )
        self.assertEqual(ruta.read_bytes(), antes)

    def test_replace_true_sobre_card_de_otro_kind_es_identity_mismatch(self):
        model = core.CardEnvelope(
            schema_version=1, card_kind="model_card", kind_schema_version=1, card_id="producto-a",
            title="Model Card", subject="modelo-x", created_at=T0, generated_at=T0,
        )
        ruta = self.destino()
        ruta.parent.mkdir(parents=True)
        assess.write_card(ruta, model, lambda: NOW)
        antes = ruta.read_bytes()
        self.assertEqual(
            codigo_de(datacard.write_data_card, self.raiz, hacer_card(), replace=True, clock=lambda: NOW),
            datacard.CODE_IDENTITY_MISMATCH,
        )
        self.assertEqual(ruta.read_bytes(), antes)

    def test_archivo_no_card_ajeno_no_se_sobrescribe(self):
        for contenido in (b"hola, esto no es una Card\n", b'{"a": 1}\n', b"", b"\xff\xfe\x00"):
            with self.subTest(contenido=contenido):
                ruta = self.escribir_ajeno(contenido)
                for replace in (False, True):
                    with self.assertRaises(core.CardError):
                        datacard.write_data_card(self.raiz, hacer_card(), replace=replace, clock=lambda: NOW)
                    self.assertEqual(ruta.read_bytes(), contenido)
                codigo = codigo_de(datacard.write_data_card, self.raiz, hacer_card(), replace=True, clock=lambda: NOW)
                self.assertEqual(codigo, datacard.CODE_IDENTITY_MISMATCH)
                codigo = codigo_de(datacard.write_data_card, self.raiz, hacer_card(), clock=lambda: NOW)
                self.assertIn(codigo, (datacard.CODE_EXISTS, core.CODE_IO_ERROR))
                ruta.unlink()

    def test_directorio_en_la_ruta_de_la_card_no_se_sobrescribe(self):
        ruta = self.destino()
        ruta.mkdir(parents=True)  # un directorio llamado producto-a.json
        for replace in (False, True):
            with self.assertRaises(core.CardError):
                datacard.write_data_card(self.raiz, hacer_card(), replace=replace, clock=lambda: NOW)
        self.assertTrue(ruta.is_dir())

    def test_card_invalida_no_crea_governance(self):
        invalidas = {
            "clave desconocida": hacer_card(body={"description": "x", "inventada": 1, "source_refs": [
                {"source_ref_id": "src-a", "source_id": "ventas", "observation_evidence_id": "ev-src-a"}]}),
            "description vacia": hacer_card(descripcion=" "),
            "source_refs vacia": hacer_card(body={"description": "x", "source_refs": []}),
            "schema ajeno": dataclasses.replace(hacer_card(), kind_schema_version=2),
            "kind ajeno": dataclasses.replace(hacer_card(), card_kind="model_card"),
            "colgante": hacer_card(body={"description": "x", "source_refs": [
                {"source_ref_id": "src-a", "source_id": "ventas", "observation_evidence_id": "no-existe"}]}),
        }
        for nombre, card in invalidas.items():
            for replace in (False, True):
                with self.subTest(caso=nombre, replace=replace):
                    with self.assertRaises(core.CardError):
                        datacard.write_data_card(self.raiz, card, replace=replace, clock=lambda: NOW)
                    self.assertFalse(self.governance.exists())

    def test_argumento_que_no_es_card_no_crea_governance(self):
        for valor in (None, {}, "x", 5):
            with self.subTest(valor=valor):
                self.assertEqual(
                    codigo_de(datacard.write_data_card, self.raiz, valor, clock=lambda: NOW), core.CODE_FIELD_INVALID
                )
        self.assertFalse(self.governance.exists())

    def test_card_id_se_toma_de_la_card_y_cada_id_tiene_su_archivo(self):
        self.escribir(hacer_card("producto-a"))
        self.escribir(hacer_card("producto-b"))
        self.assertEqual(sorted(os.listdir(self.destino().parent)), ["producto-a.json", "producto-b.json"])

    def test_write_card_exclusive_de_la_foundation(self):
        card = core.CardEnvelope(
            schema_version=1, card_kind="model_card", kind_schema_version=1, card_id="m1",
            title="M", subject="m", created_at=T0, generated_at=T0,
        )
        ruta = self.raiz / "m1.json"
        assess.write_card(ruta, card, lambda: NOW, exclusive=True)
        antes = ruta.read_bytes()
        self.assertEqual(
            codigo_de(assess.write_card, ruta, card, lambda: NOW, exclusive=True), core.CODE_IO_ERROR
        )
        self.assertEqual(ruta.read_bytes(), antes)
        # default intacto: sobrescribe
        assess.write_card(ruta, card, lambda: NOW)
        self.assertEqual(os.listdir(self.raiz), ["m1.json"])


# ---------------------------------------------------------------------------
# R32 -- importar no crea governance/
# ---------------------------------------------------------------------------


class TestImportarNoCreaGovernance(BaseTmp):
    def test_importar_el_modulo_no_crea_governance(self):
        existia = (REPO / "governance").exists()
        entorno = dict(os.environ)
        entorno["PYTHONPATH"] = str(REPO) + os.pathsep + entorno.get("PYTHONPATH", "")
        proc = subprocess.run(
            [sys.executable, "-c", "import tools.cards.datacard, tools.cards.resolvers"],
            cwd=str(self.raiz),
            env=entorno,
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertFalse(self.governance.exists())
        self.assertEqual((REPO / "governance").exists(), existia)

    def test_card_path_y_validar_no_crean_governance(self):
        datacard.card_path(self.raiz, "producto-a")
        datacard.validate_data_card(hacer_card())
        datacard.requirements_for(hacer_card())
        datacard.evaluate_data_card(hacer_card(), self.raiz)
        self.assertFalse(self.governance.exists())
        self.assertEqual(os.listdir(self.raiz), [".harmessi"] if (self.raiz / ".harmessi").exists() else [])


if __name__ == "__main__":
    unittest.main()

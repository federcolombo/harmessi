"""Compat: la Data Card v1 REAL del tag v0.14.0 sigue leyendose con el lector actual.

El fixture `fixtures/compat/v0_14/data_card.json` se genera con
`fixtures/compat/generate_datacard_v014.py` (solo-checkout). Si falta, el test FALLA (no skip):
docs/versioning.md exige este fixture al subir el kind_schema_version de la Data Card.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import unittest
from pathlib import Path

from tools.cards import assess, datacard

DIR_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "compat" / "v0_14"
RUTA_CARD = DIR_FIXTURES / "data_card.json"
RUTA_MANIFIESTO = DIR_FIXTURES / "MANIFEST_data_card.json"


class TestCompatDataCardV014(unittest.TestCase):
    def setUp(self) -> None:
        if not RUTA_CARD.is_file() or not RUTA_MANIFIESTO.is_file():
            self.fail(
                f"falta el fixture real de Data Card v0.14.0 ({RUTA_CARD} / {RUTA_MANIFIESTO}); "
                "generarlo con tools/tests/fixtures/compat/generate_datacard_v014.py")
        self.card = assess.read_card(RUTA_CARD)

    def test_hash_coincide_con_manifiesto(self) -> None:
        manifiesto = json.loads(RUTA_MANIFIESTO.read_text(encoding="utf-8"))
        esperado = manifiesto["fixtures"]["data_card.json"]["sha256"]
        self.assertEqual(hashlib.sha256(RUTA_CARD.read_bytes()).hexdigest(), esperado)
        self.assertEqual(manifiesto["tag_origen"], "v0.14.0")

    def test_kind_y_schema_version(self) -> None:
        datos = json.loads(RUTA_CARD.read_text(encoding="utf-8"))
        self.assertEqual(datos["kind_schema_version"], 1)
        self.assertEqual(datos["card_kind"], "data_card")
        self.assertNotIn("temporality", datos["body"])

    def test_lector_actual_valida_la_card_v1(self) -> None:
        self.assertEqual(self.card.kind_schema_version, 1)
        self.assertEqual(datacard.validate_data_card(self.card), [])

    def test_temporality_en_v1_se_rechaza(self) -> None:
        body = dict(self.card.body)
        body["temporality"] = {"mode": "current"}
        card = dataclasses.replace(self.card, body=body, kind_schema_version=1)
        hallazgos = datacard.validate_data_card(card)
        codigos = [h.code for h in hallazgos]
        self.assertIn(datacard.CODE_BODY_INVALID, codigos)
        self.assertTrue(any("temporality" in h.detail for h in hallazgos), hallazgos)

    def test_schema_version_3_no_soportado(self) -> None:
        card = dataclasses.replace(self.card, kind_schema_version=3)
        codigos = [h.code for h in datacard.validate_data_card(card)]
        self.assertIn(datacard.CODE_SCHEMA_UNSUPPORTED, codigos)


if __name__ == "__main__":
    unittest.main()

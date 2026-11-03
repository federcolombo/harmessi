"""Test de paridad exacta contra el corpus dorado v0.7 (T5 del Change 1 de v0.8,
`openspec/changes/20260928-source-neutral-data-access/spec.md` R34/R35).

Reconstruye los 114 casos `(id, contrato, perfil)` EXACTAMENTE como los arma
`tools/datacontracts/tests/parity/build_golden_v07.py` -- importando su lista
`_CASOS` directamente (módulo fuente de verdad, sin duplicar la lógica de
construcción) -- y compara `validation.validate_contract(contrato, perfil)`
REAL contra el `caso["resultado"]` ya persistido en `golden_v07_validation.json`.

Un método de test POR CASO (loop que registra un `subTest` por id) para que un
fallo puntual señale exactamente qué caso rompió, más un guardrail de conteo
(114 casos) contra que alguien borre casos del corpus sin querer.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from tools.datacontracts import validation as v
from tools.datacontracts.tests.parity import build_golden_v07 as golden_builder

_GOLDEN_PATH = Path(__file__).resolve().parent / "parity" / "golden_v07_validation.json"

with _GOLDEN_PATH.open("r", encoding="utf-8") as _f:
    _GOLDEN = json.load(_f)

_CASOS_GOLDEN_POR_ID = {caso["id"]: caso for caso in _GOLDEN["cases"]}


class TestParidadGoldenV07(unittest.TestCase):
    """Corre `validate_contract` real sobre cada uno de los 114 casos del
    corpus dorado (`build_golden_v07._CASOS`, reutilizado sin duplicar) y
    exige igualdad exacta (lista completa de `CheckResult.to_dict()`) contra
    la foto de referencia `golden_v07_validation.json`."""

    def test_cantidad_de_casos_no_cambio(self):
        # Guardrail: 114 casos es el tamaño del corpus dorado al momento de
        # escribir este test (Parte A: reconstrucción de test_validation.py;
        # Parte B: matriz sintética por constraint_type). Si esto falla,
        # alguien borró (o agregó) casos en build_golden_v07.py sin
        # regenerar/revisar el golden.
        self.assertEqual(len(golden_builder._CASOS), 114)
        self.assertEqual(len(_GOLDEN["cases"]), 114)

    def test_ids_de_casos_coinciden_con_el_golden(self):
        ids_builder = {id_ for id_, _contrato, _perfil in golden_builder._CASOS}
        ids_golden = set(_CASOS_GOLDEN_POR_ID.keys())
        self.assertEqual(ids_builder, ids_golden)

    def test_paridad_exacta_por_caso(self):
        for id_, contrato, perfil in golden_builder._CASOS:
            with self.subTest(caso=id_):
                self.assertIn(id_, _CASOS_GOLDEN_POR_ID, f"caso {id_!r} no está en el golden")
                esperado = _CASOS_GOLDEN_POR_ID[id_]["resultado"]
                resultados = v.validate_contract(contrato, perfil)
                obtenido = [r.to_dict() for r in resultados]
                self.assertEqual(obtenido, esperado)


if __name__ == "__main__":
    unittest.main()

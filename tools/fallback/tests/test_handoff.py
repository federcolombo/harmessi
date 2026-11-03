"""Tests de `tools.fallback.handoff` (v0.5 Change 3, `fallback-and-handoffs`).
Deterministas, usan `tmp_path` para round-trip de persistencia."""
from __future__ import annotations

import unittest
from pathlib import Path

import pytest

from tools.fallback.handoff import build_handoff_context, load_handoff, save_handoff


class TestBuildHandoffContext(unittest.TestCase):
    def test_campos_validos(self):
        contexto = build_handoff_context(
            change_id="20260917-fallback-and-handoffs",
            role="python-data-engineer",
            reason="handoff de prueba",
            completed=["a"],
            pending=["b"],
            prior_findings=["c"],
        )

        self.assertEqual(contexto.change_id, "20260917-fallback-and-handoffs")
        self.assertEqual(contexto.completed, ["a"])
        self.assertEqual(contexto.pending, ["b"])
        self.assertEqual(contexto.prior_findings, ["c"])
        self.assertTrue(contexto.created_utc)

    def test_listas_none_se_normalizan_a_vacias(self):
        contexto = build_handoff_context(
            change_id="c1", role="writer", reason="motivo"
        )

        self.assertEqual(contexto.completed, [])
        self.assertEqual(contexto.pending, [])
        self.assertEqual(contexto.prior_findings, [])

    def test_change_id_vacio_levanta_value_error(self):
        with self.assertRaises(ValueError):
            build_handoff_context(change_id="", role="writer", reason="motivo")

    def test_role_vacio_levanta_value_error(self):
        with self.assertRaises(ValueError):
            build_handoff_context(change_id="c1", role="", reason="motivo")

    def test_reason_vacio_levanta_value_error(self):
        with self.assertRaises(ValueError):
            build_handoff_context(change_id="c1", role="writer", reason="")


def test_save_y_load_round_trip(tmp_path: Path):
    contexto = build_handoff_context(
        change_id="20260917-fallback-and-handoffs",
        role="python-data-engineer",
        reason="handoff de prueba",
        completed=["paso1"],
        pending=["paso2"],
    )

    ruta = save_handoff(contexto, root=tmp_path)
    assert ruta.exists()

    recuperado = load_handoff(ruta)
    assert recuperado["change_id"] == contexto.change_id
    assert recuperado["role"] == contexto.role
    assert recuperado["reason"] == contexto.reason
    assert recuperado["completed"] == ["paso1"]
    assert recuperado["pending"] == ["paso2"]


def test_save_handoff_colision_de_nombre_no_sobrescribe(tmp_path: Path):
    contexto = build_handoff_context(
        change_id="20260917-fallback-and-handoffs",
        role="python-data-engineer",
        reason="handoff de prueba",
        completed=["paso1"],
        pending=["paso2"],
    )

    ruta_1 = save_handoff(contexto, root=tmp_path)
    ruta_2 = save_handoff(contexto, root=tmp_path)

    assert ruta_1 != ruta_2
    assert ruta_1.exists()
    assert ruta_2.exists()

    recuperado_1 = load_handoff(ruta_1)
    recuperado_2 = load_handoff(ruta_2)
    assert recuperado_1["change_id"] == contexto.change_id
    assert recuperado_1["completed"] == ["paso1"]
    assert recuperado_1["pending"] == ["paso2"]
    assert recuperado_2["change_id"] == contexto.change_id
    assert recuperado_2["completed"] == ["paso1"]
    assert recuperado_2["pending"] == ["paso2"]


def test_load_handoff_ruta_inexistente_levanta_file_not_found(tmp_path: Path):
    ruta_inexistente = tmp_path / "no_existe" / "handoff.json"
    with pytest.raises(FileNotFoundError):
        load_handoff(ruta_inexistente)


if __name__ == "__main__":
    unittest.main()

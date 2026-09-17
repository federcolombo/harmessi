"""Tests de `tools/harmessi_bench/scenarios.py`: `load_scenarios`."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.harmessi_bench.scenarios import load_scenarios

_RUTA_EXAMPLES = Path(__file__).resolve().parents[1] / "scenarios" / "examples.json"


def test_load_scenarios_examples_reales():
    escenarios = load_scenarios(_RUTA_EXAMPLES)
    assert len(escenarios) == 3

    ids = [escenario.scenario_id for escenario in escenarios]
    assert ids == ["responde-ok", "suma-simple", "formato-lista"]

    primero = escenarios[0]
    assert primero.prompt == "Respondé unicamente con la palabra OK."
    assert primero.category == "instruccion-formato"
    assert primero.tags == ["demo"]
    assert primero.expected == {"tipo": "exact", "valor": "OK"}


def test_load_scenarios_escenario_mal_formado(tmp_path):
    contenido = {
        "escenarios": [
            {"scenario_id": "ok-1", "prompt": "hola", "expected": {"tipo": "exact", "valor": "hola"}},
            {"scenario_id": "sin-expected", "prompt": "chau"},
        ]
    }
    ruta = tmp_path / "escenarios_malformados.json"
    ruta.write_text(json.dumps(contenido), encoding="utf-8")

    with pytest.raises(ValueError) as excinfo:
        load_scenarios(ruta)

    assert "1" in str(excinfo.value)
    assert "expected" in str(excinfo.value)

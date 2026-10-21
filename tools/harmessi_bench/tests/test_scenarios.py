"""Tests de `tools/harmessi_bench/scenarios.py`: `load_scenarios`."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.harmessi_bench.core import CASE_CONTRACT_VERSION
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


# --- v0.13 Change 1: contrato de caso versionado ------------------------------

def _escribir(tmp_path, contenido) -> Path:
    ruta = tmp_path / "carpeta con espacios ñ" / "casos.json"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(contenido), encoding="utf-8")
    return ruta


def _caso(scenario_id="c1", **extra) -> dict:
    caso = {"scenario_id": scenario_id, "prompt": "p", "expected": {"tipo": "exact", "valor": "x"}}
    caso.update(extra)
    return caso


def test_legado_sin_version_y_defaults_nuevos(tmp_path):
    escenarios = load_scenarios(_escribir(tmp_path, {"escenarios": [_caso()]}))
    assert escenarios[0].fixtures == {}
    assert escenarios[0].surface_under_test is None
    assert CASE_CONTRACT_VERSION == 1


@pytest.mark.parametrize("version", [0, 1])
def test_versiones_soportadas(tmp_path, version):
    ruta = _escribir(tmp_path, {"case_contract_version": version, "escenarios": [_caso()]})
    assert len(load_scenarios(ruta)) == 1


@pytest.mark.parametrize("version", [2, -1, "1", 1.0, True, False, None])
def test_version_invalida_falla_cerrado(tmp_path, version):
    ruta = _escribir(tmp_path, {"case_contract_version": version, "escenarios": [_caso()]})
    with pytest.raises(ValueError, match="case_contract_version"):
        load_scenarios(ruta)


def test_ids_duplicados(tmp_path):
    ruta = _escribir(tmp_path, {"escenarios": [_caso("dup"), _caso("dup")]})
    with pytest.raises(ValueError, match="dup"):
        load_scenarios(ruta)


def test_fixtures_se_leen_y_deben_ser_objeto(tmp_path):
    ok = _escribir(tmp_path, {"escenarios": [_caso(fixtures={"k": "v"})]})
    assert load_scenarios(ok)[0].fixtures == {"k": "v"}
    mal = _escribir(tmp_path, {"escenarios": [_caso(fixtures=["no"])]})
    with pytest.raises(ValueError, match="fixtures"):
        load_scenarios(mal)


def test_surface_under_test_optimizable_se_acepta(tmp_path):
    ruta = _escribir(
        tmp_path,
        {"escenarios": [_caso(surface_under_test=".claude/skills/lead-data-scientist/skills/problem-framing.md")]},
    )
    assert load_scenarios(ruta)[0].surface_under_test.endswith("problem-framing.md")


@pytest.mark.parametrize(
    "superficie",
    [
        "tools/dsguard/hook_rutas.py",
        ".claude/settings.json",
        "openspec/changes/x/control.json",
        "GLOSSARY.md",
        "../afuera.md",
        ".claude\\skills\\lead-data-scientist\\..\\settings.json",
    ],
)
def test_surface_under_test_protegida_o_del_proyecto_se_rechaza(tmp_path, superficie):
    ruta = _escribir(tmp_path, {"escenarios": [_caso("caso-x", surface_under_test=superficie)]})
    with pytest.raises(ValueError, match="caso-x"):
        load_scenarios(ruta)


def test_surface_under_test_no_string(tmp_path):
    ruta = _escribir(tmp_path, {"escenarios": [_caso(surface_under_test=5)]})
    with pytest.raises(ValueError, match="surface_under_test"):
        load_scenarios(ruta)


@pytest.mark.parametrize(
    "extra",
    [
        {"scenario_id": ""},
        {"scenario_id": 5},
        {"prompt": ""},
        {"prompt": 7},
        {"expected": "texto"},
        {"expected": {}},
        {"expected": {"tipo": "llm-judge"}},
    ],
)
def test_campos_basicos_invalidos_fallan_cerrado(tmp_path, extra):
    ruta = _escribir(tmp_path, {"escenarios": [_caso(**extra)]})
    with pytest.raises(ValueError):
        load_scenarios(ruta)


def test_mensajes_no_incluyen_ruta_absoluta(tmp_path):
    ruta = _escribir(tmp_path, {"escenarios": [_caso(prompt="")]})
    with pytest.raises(ValueError) as excinfo:
        load_scenarios(ruta)
    assert str(tmp_path) not in str(excinfo.value)


def test_scorers_no_incluyen_llm():
    from tools.harmessi_bench.core import SCORERS

    assert sorted(SCORERS) == ["contains", "exact", "regex"]

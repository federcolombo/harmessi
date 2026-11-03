"""Tests de `tools/harmessi_bench/suite.py` (v0.13 Change 1): manifest,
validación fail-closed, hash canónico y resumen."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.harmessi_bench.core import EvalResult, EvalTarget, ScoreResult
from tools.harmessi_bench.suite import (
    Suite,
    bloque_suite,
    calcular_suite_hash,
    load_suite,
    load_suite_y_casos,
    render_resumen,
    resumir,
)

_RUTA_SUITE_PUBLICA = (
    Path(__file__).resolve().parents[1] / "suites" / "harmessi-core-synthetic.suite.json"
)


def _caso(scenario_id: str, valor: str = "x") -> dict:
    return {
        "scenario_id": scenario_id,
        "prompt": f"Prompt de {scenario_id} con acentos: canción",
        "category": "cat",
        "expected": {"tipo": "exact", "valor": valor},
    }


def _escribir_suite(directorio: Path, casos: list, case_ids: list, **extra) -> Path:
    """Escribe cases + manifest en `directorio` y devuelve la ruta del manifest."""
    directorio.mkdir(parents=True, exist_ok=True)
    (directorio / "casos.json").write_text(
        json.dumps({"case_contract_version": 1, "escenarios": casos}, ensure_ascii=False),
        encoding="utf-8",
    )
    manifest = {
        "suite_contract_version": 1,
        "suite_id": "mi-suite",
        "suite_version": 1,
        "cases_file": "casos.json",
        "case_ids": case_ids,
    }
    manifest.update(extra)
    ruta = directorio / "x.suite.json"
    ruta.write_text(json.dumps(manifest), encoding="utf-8")
    return ruta


def test_suite_publica_valida_y_cubre_categorias():
    suite, escenarios = load_suite_y_casos(_RUTA_SUITE_PUBLICA)
    assert suite.suite_id == "harmessi-core-synthetic"
    assert len(suite.case_ids) >= 8
    assert len(suite.suite_hash) == 64
    categorias = {escenario.category for escenario in escenarios}
    assert {
        "problem-framing",
        "debugging",
        "domain-modeling",
        "codebase-design",
        "recovery",
        "tool-contract",
    } <= categorias


def test_load_suite_ok_con_directorio_con_espacios_y_unicode(tmp_path):
    ruta = _escribir_suite(tmp_path / "dir con espacios ñandú", [_caso("a"), _caso("b")], ["a", "b"])
    suite = load_suite(ruta)
    assert isinstance(suite, Suite)
    assert suite.case_ids == ["a", "b"]
    assert suite.suite_version == 1
    assert suite.case_contract_version == 1


def test_hash_independiente_del_orden_y_de_crlf(tmp_path):
    ruta_1 = _escribir_suite(tmp_path / "uno", [_caso("a"), _caso("b")], ["a", "b"])
    ruta_2 = _escribir_suite(tmp_path / "dos", [_caso("b"), _caso("a")], ["b", "a"])
    # Reescribe el archivo de casos con CRLF: el hash no debe cambiar.
    casos_2 = tmp_path / "dos" / "casos.json"
    contenido = casos_2.read_bytes().replace(b",", b",\r\n")
    casos_2.write_bytes(contenido)
    assert load_suite(ruta_1).suite_hash == load_suite(ruta_2).suite_hash


def test_hash_cambia_si_cambia_el_contenido(tmp_path):
    ruta_1 = _escribir_suite(tmp_path / "uno", [_caso("a", "x")], ["a"])
    ruta_2 = _escribir_suite(tmp_path / "dos", [_caso("a", "y")], ["a"])
    assert load_suite(ruta_1).suite_hash != load_suite(ruta_2).suite_hash


def test_calcular_suite_hash_es_hex_sha256():
    from tools.harmessi_bench.core import Scenario

    valor = calcular_suite_hash([Scenario("a", "p", "c", expected={"tipo": "exact", "valor": "x"})])
    assert len(valor) == 64 and int(valor, 16) >= 0


@pytest.mark.parametrize("campo", ["suite_contract_version", "suite_id", "suite_version", "cases_file", "case_ids"])
def test_falta_campo_requerido(tmp_path, campo):
    ruta = _escribir_suite(tmp_path, [_caso("a")], ["a"])
    manifest = json.loads(ruta.read_text(encoding="utf-8"))
    del manifest[campo]
    ruta.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match=campo):
        load_suite(ruta)


@pytest.mark.parametrize("version", [0, 2, "1", True, 1.0, None])
def test_suite_contract_version_desconocida(tmp_path, version):
    ruta = _escribir_suite(tmp_path, [_caso("a")], ["a"], suite_contract_version=version)
    with pytest.raises(ValueError, match="suite_contract_version"):
        load_suite(ruta)


@pytest.mark.parametrize("version", [0, -1, "1", True, 1.5])
def test_suite_version_invalida(tmp_path, version):
    ruta = _escribir_suite(tmp_path, [_caso("a")], ["a"], suite_version=version)
    with pytest.raises(ValueError, match="suite_version"):
        load_suite(ruta)


def test_case_ids_vacio_o_duplicado(tmp_path):
    ruta = _escribir_suite(tmp_path / "v", [_caso("a")], [])
    with pytest.raises(ValueError, match="case_ids"):
        load_suite(ruta)
    ruta = _escribir_suite(tmp_path / "d", [_caso("a")], ["a", "a"])
    with pytest.raises(ValueError, match="duplicados"):
        load_suite(ruta)


def test_case_ids_distinto_del_archivo(tmp_path):
    ruta_falta = _escribir_suite(tmp_path / "f", [_caso("a")], ["a", "b"])
    with pytest.raises(ValueError, match="b"):
        load_suite(ruta_falta)
    ruta_sobra = _escribir_suite(tmp_path / "s", [_caso("a"), _caso("c")], ["a"])
    with pytest.raises(ValueError, match="c"):
        load_suite(ruta_sobra)


@pytest.mark.parametrize(
    "cases_file",
    ["../casos.json", "sub/../../casos.json", "..\\casos.json", "/etc/casos.json", "\\casos.json", "C:\\casos.json", "C:casos.json", "", 5],
)
def test_cases_file_inseguro_se_rechaza(tmp_path, cases_file):
    directorio = tmp_path / "suite"
    ruta = _escribir_suite(directorio, [_caso("a")], ["a"], cases_file=cases_file)
    # Archivo señuelo fuera del directorio, para que un chequeo por existencia no enmascare el rechazo.
    (tmp_path / "casos.json").write_text(
        json.dumps({"escenarios": [_caso("a")]}), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="cases_file"):
        load_suite(ruta)


def test_cases_file_absoluto_real_se_rechaza(tmp_path):
    destino = tmp_path / "afuera.json"
    destino.write_text(json.dumps({"escenarios": [_caso("a")]}), encoding="utf-8")
    ruta = _escribir_suite(tmp_path / "suite", [_caso("a")], ["a"], cases_file=str(destino.resolve()))
    with pytest.raises(ValueError, match="cases_file"):
        load_suite(ruta)


def test_cases_file_inexistente(tmp_path):
    ruta = _escribir_suite(tmp_path, [_caso("a")], ["a"], cases_file="no-existe.json")
    with pytest.raises(ValueError, match="cases_file"):
        load_suite(ruta)


def test_manifest_inexistente_filenotfound(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_suite(tmp_path / "no-existe.suite.json")


@pytest.mark.parametrize("clave", ["suite_hash", "extra"])
def test_clave_desconocida_en_manifest_se_rechaza(tmp_path, clave):
    ruta = _escribir_suite(tmp_path, [_caso("a")], ["a"], **{clave: "x"})
    with pytest.raises(ValueError, match=clave):
        load_suite(ruta)


def test_description_es_clave_permitida(tmp_path):
    ruta = _escribir_suite(tmp_path, [_caso("a")], ["a"], description="algo")
    assert load_suite(ruta).description == "algo"


def test_bloque_suite():
    suite = Suite("s", 2, ["a"], "h" * 64, 1)
    assert bloque_suite(suite) == {"suite_id": "s", "suite_version": 2, "suite_hash": "h" * 64}
    assert bloque_suite(None) is None
    assert bloque_suite({"suite_id": "s", "suite_version": 2, "suite_hash": "h", "extra": 1}) == {
        "suite_id": "s",
        "suite_version": 2,
        "suite_hash": "h",
    }


def _eval(scenario_id: str, passed: bool, ok: bool = True, availability_error=None) -> EvalResult:
    return EvalResult(
        run_id="r",
        scenario_id=scenario_id,
        target=EvalTarget("fake"),
        exit_code=0 if ok else 1,
        ok=ok,
        availability_error=availability_error,
        duration_s=0.0,
        stdout_excerpt="",
        score=ScoreResult(passed=passed, score=1.0 if passed else 0.0, detail=""),
        harmessi_version="0",
        timestamp_utc="2026-01-01T00:00:00+00:00",
    )


def test_resumir_cuenta_y_es_determinista():
    resultados = [
        _eval("a", True),
        _eval("b", False),
        _eval("c", False, ok=False, availability_error="quota"),
    ]
    categorias = {"a": "x", "b": "x", "c": "y"}
    suite = Suite("s", 1, ["a", "b", "c"], "h", 1)
    resumen = resumir(resultados, suite, categorias)
    assert resumen["total"] == 3
    assert resumen["pasaron"] == 1
    assert resumen["fallaron"] == 1
    assert resumen["no_disponibles"] == 1
    assert list(resumen["por_categoria"]) == ["x", "y"]
    assert resumen["por_categoria"]["x"]["pasaron"] == 1
    assert resumen["suite"]["suite_id"] == "s"
    assert resumir(resultados, suite, categorias) == resumen
    assert render_resumen(resumen) == render_resumen(resumen)
    assert "total=3" in render_resumen(resumen)


def test_resumir_acepta_dicts_de_load_run_y_sin_suite():
    resumen = resumir([{"scenario_id": "a", "ok": True, "score": {"passed": True}}])
    assert resumen["pasaron"] == 1
    assert resumen["suite"] is None
    assert "sin suite" in render_resumen(resumen)
    assert "sin-categoria" in resumen["por_categoria"]

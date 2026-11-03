"""Tests de `tools/harmessi_bench/storage.py`: round-trip `save_run`/
`load_run` y `FileNotFoundError` fail-closed."""
from __future__ import annotations

import json

import pytest

from tools.ds_init.version import HARNESS_VERSION
from tools.harmessi_bench.core import EvalResult, EvalTarget, ScoreResult
from tools.harmessi_bench.storage import load_run, save_run


def _resultado_de_ejemplo(scenario_id: str, target: EvalTarget) -> EvalResult:
    return EvalResult(
        run_id="run-1",
        scenario_id=scenario_id,
        target=target,
        exit_code=0,
        ok=True,
        availability_error=None,
        duration_s=0.5,
        stdout_excerpt="OK",
        score=ScoreResult(passed=True, score=1.0, detail="coincide"),
        harmessi_version="0.4.0",
        timestamp_utc="2026-09-17T00:00:00+00:00",
    )


def test_save_run_y_load_run_round_trip(tmp_path):
    target = EvalTarget(provider_id="fake", model=None, effort=None)
    resultados = [_resultado_de_ejemplo("s1", target), _resultado_de_ejemplo("s2", target)]

    ruta = save_run("run-1", resultados, target, root=tmp_path)

    assert ruta.exists()
    contenido_disco = json.loads(ruta.read_text(encoding="utf-8"))
    assert contenido_disco["run_id"] == "run-1"
    assert len(contenido_disco["resultados"]) == 2

    cargado = load_run("run-1", root=tmp_path)
    assert cargado == contenido_disco
    assert cargado["resultados"][0]["scenario_id"] == "s1"


def test_load_run_inexistente_lanza_filenotfound(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_run("run-que-no-existe", root=tmp_path)


def test_save_run_escribe_schema_y_evaluator_version(tmp_path):
    from tools.harmessi_bench.core import EVALUATOR_VERSION
    from tools.harmessi_bench.storage import RESULT_SCHEMA_VERSION

    target = EvalTarget(provider_id="fake")
    ruta = save_run("run-v", [_resultado_de_ejemplo("s1", target)], target, root=tmp_path)
    contenido = json.loads(ruta.read_text(encoding="utf-8"))
    assert contenido["schema_version"] == RESULT_SCHEMA_VERSION == 1
    assert contenido["evaluator_version"] == EVALUATOR_VERSION
    assert "suite" not in contenido


def test_save_run_con_suite_escribe_bloque(tmp_path):
    from tools.harmessi_bench.suite import Suite

    target = EvalTarget(provider_id="fake")
    suite = Suite("mi-suite", 3, ["s1"], "a" * 64, 1)
    ruta = save_run("run-s", [], target, root=tmp_path / "dir con espacios ñ", suite=suite)
    contenido = json.loads(ruta.read_text(encoding="utf-8"))
    assert contenido["suite"] == {"suite_id": "mi-suite", "suite_version": 3, "suite_hash": "a" * 64}


def test_load_run_legado_sin_schema_version(tmp_path):
    directorio = tmp_path / "run-legado"
    directorio.mkdir()
    legado = {"run_id": "run-legado", "resultados": []}
    (directorio / "result.json").write_text(json.dumps(legado), encoding="utf-8")
    assert load_run("run-legado", root=tmp_path) == legado


@pytest.mark.parametrize("version", [2, 99, -1, "1", 1.0, True, None])
def test_load_run_version_futura_o_invalida_falla(tmp_path, version):
    directorio = tmp_path / "run-x"
    directorio.mkdir()
    (directorio / "result.json").write_text(
        json.dumps({"schema_version": version, "run_id": "run-x", "resultados": []}), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="schema_version"):
        load_run("run-x", root=tmp_path)


def test_result_json_no_contiene_prompt_completo_ni_rutas_personales(tmp_path):
    target = EvalTarget(provider_id="fake")
    resultado = _resultado_de_ejemplo("s1", target)
    ruta = save_run("run-p", [resultado], target, root=tmp_path)
    texto = ruta.read_text(encoding="utf-8")
    assert "prompt" not in texto
    assert "Users" not in texto and "@" not in texto


def test_save_run_con_results_vacio_usa_harness_version_no_none(tmp_path):
    target = EvalTarget(provider_id="fake", model=None, effort=None)

    ruta = save_run("run-vacio", [], target, root=tmp_path)

    contenido_disco = json.loads(ruta.read_text(encoding="utf-8"))
    assert contenido_disco["harmessi_version"] == HARNESS_VERSION
    assert contenido_disco["harmessi_version"] is not None

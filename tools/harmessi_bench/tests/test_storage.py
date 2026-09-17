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


def test_save_run_con_results_vacio_usa_harness_version_no_none(tmp_path):
    target = EvalTarget(provider_id="fake", model=None, effort=None)

    ruta = save_run("run-vacio", [], target, root=tmp_path)

    contenido_disco = json.loads(ruta.read_text(encoding="utf-8"))
    assert contenido_disco["harmessi_version"] == HARNESS_VERSION
    assert contenido_disco["harmessi_version"] is not None

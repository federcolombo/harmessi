"""Tests de `tools/harmessi_bench/cli.py`: `run`/`compare` sin invocar
ninguna CLI real (provider inexistente, `FakeAdapter` monkeypatcheado en
`PROVIDER_REGISTRY`, `compare` sobre corridas guardadas con `save_run`)."""
from __future__ import annotations

import json
from pathlib import Path

from tools.harmessi_bench import storage
from tools.harmessi_bench.cli import main
from tools.harmessi_bench.core import EvalResult, EvalTarget, ScoreResult
from tools.providers.core import InvocationResult, ProviderCapabilities, ProviderInfo

_RUTA_EXAMPLES = str(Path(__file__).resolve().parents[1] / "scenarios" / "examples.json")


class FakeAdapterDisponible:
    """Adapter de test disponible: `detect()` siempre `available=True`,
    `invoke()` responde `ok=True` con el texto esperado por cada escenario
    de `examples.json` (para que los 3 escenarios demostrativos pasen)."""

    provider_id = "fake"
    cli_command = "fake"
    display_name = "Fake"

    def detect(self):
        return ProviderInfo(
            provider_id="fake",
            display_name="Fake",
            cli_command="fake",
            available=True,
            authenticated=True,
            version="0.0.0",
            capabilities=ProviderCapabilities(),
            detail="disponible (fake, test)",
        )

    def invoke(self, request):
        if "OK" in request.prompt:
            texto = "OK"
        elif "2+2" in request.prompt:
            texto = "4"
        else:
            texto = "rojo\nazul"
        return InvocationResult(
            provider_id="fake",
            exit_code=0,
            stdout=texto,
            stderr="",
            ok=True,
            availability_error=None,
            duration_s=0.05,
        )


def test_run_provider_inexistente_exit_1(capsys):
    codigo = main(
        [
            "run",
            "--scenarios",
            _RUTA_EXAMPLES,
            "--provider",
            "no-existe",
            "--run-id",
            "run-x",
        ]
    )
    assert codigo == 1
    salida = capsys.readouterr()
    assert "no-existe" in salida.err


def test_run_scenarios_inexistente_exit_1_sin_traceback(capsys, tmp_path, monkeypatch):
    import tools.providers as providers_mod

    monkeypatch.setitem(providers_mod.PROVIDER_REGISTRY, "fake", FakeAdapterDisponible())
    ruta_inexistente = str(tmp_path / "no-existe.json")

    codigo = main(
        [
            "run",
            "--scenarios",
            ruta_inexistente,
            "--provider",
            "fake",
            "--run-id",
            "run-x",
        ]
    )
    assert codigo == 1
    salida = capsys.readouterr()
    assert "no se pudieron cargar los escenarios" in salida.err
    assert "Traceback" not in salida.err


def test_compare_result_json_corrupto_exit_1(capsys, tmp_path):
    directorio = tmp_path / "run-corrupto"
    directorio.mkdir()
    (directorio / "result.json").write_text(
        json.dumps({"run_id": "run-corrupto", "resultados": [{"scenario_id": "s1"}]}),
        encoding="utf-8",
    )

    codigo = main(
        [
            "compare",
            "--baseline",
            "run-corrupto",
            "--candidate",
            "run-corrupto",
            "--root",
            str(tmp_path),
        ]
    )
    assert codigo == 1
    salida = capsys.readouterr()
    assert "Traceback" not in salida.err


def test_run_con_fake_adapter_disponible(monkeypatch, tmp_path):
    import tools.providers as providers_mod

    monkeypatch.setitem(providers_mod.PROVIDER_REGISTRY, "fake", FakeAdapterDisponible())

    codigo = main(
        [
            "run",
            "--scenarios",
            _RUTA_EXAMPLES,
            "--provider",
            "fake",
            "--run-id",
            "run-fake-1",
            "--root",
            str(tmp_path),
            "--json",
        ]
    )
    assert codigo == 0

    corrida = storage.load_run("run-fake-1", root=tmp_path)
    assert len(corrida["resultados"]) == 3
    assert all(resultado["score"]["passed"] for resultado in corrida["resultados"])


def test_compare_sobre_corridas_guardadas(tmp_path, capsys):
    target = EvalTarget(provider_id="fake", model=None, effort=None)

    resultados_baseline = [
        EvalResult(
            run_id="run-a",
            scenario_id="s1",
            target=target,
            exit_code=0,
            ok=True,
            availability_error=None,
            duration_s=0.1,
            stdout_excerpt="OK",
            score=ScoreResult(passed=True, score=1.0, detail="ok"),
            harmessi_version="0.4.0",
            timestamp_utc="2026-09-17T00:00:00+00:00",
        )
    ]
    resultados_candidate = [
        EvalResult(
            run_id="run-b",
            scenario_id="s1",
            target=target,
            exit_code=0,
            ok=True,
            availability_error=None,
            duration_s=0.1,
            stdout_excerpt="mal",
            score=ScoreResult(passed=False, score=0.0, detail="no coincide"),
            harmessi_version="0.4.0",
            timestamp_utc="2026-09-17T00:00:01+00:00",
        )
    ]

    storage.save_run("run-a", resultados_baseline, target, root=tmp_path)
    storage.save_run("run-b", resultados_candidate, target, root=tmp_path)

    codigo = main(
        [
            "compare",
            "--baseline",
            "run-a",
            "--candidate",
            "run-b",
            "--root",
            str(tmp_path),
        ]
    )
    assert codigo == 0
    salida = capsys.readouterr()
    assert "REGRESSION" in salida.out
    assert "s1" in salida.out

"""Tests de `tools/harmessi_bench/cli.py`: `run`/`compare` sin invocar
ninguna CLI real (provider inexistente, `FakeAdapter` monkeypatcheado en
`PROVIDER_REGISTRY`, `compare` sobre corridas guardadas con `save_run`)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

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


_RUTA_SUITE = str(
    Path(__file__).resolve().parents[1] / "suites" / "harmessi-core-synthetic.suite.json"
)


def test_run_id_invalido_exit_1(monkeypatch, tmp_path, capsys):
    import tools.providers as providers_mod

    monkeypatch.setitem(providers_mod.PROVIDER_REGISTRY, "fake", FakeAdapterDisponible())
    for malo in ("..\\x", "../x", str(tmp_path), "a/b", ""):
        codigo = main(["run", "--scenarios", _RUTA_EXAMPLES, "--provider", "fake", "--run-id", malo,
                       "--root", str(tmp_path)])
        assert codigo == 1
    assert "run_id inválido" in capsys.readouterr().err


def test_run_exige_exactamente_uno_de_scenarios_o_suite(capsys):
    with pytest.raises(SystemExit) as sin_ninguno:
        main(["run", "--provider", "fake", "--run-id", "r"])
    assert sin_ninguno.value.code == 2
    with pytest.raises(SystemExit) as con_ambos:
        main(
            ["run", "--scenarios", _RUTA_EXAMPLES, "--suite", _RUTA_SUITE, "--provider", "fake", "--run-id", "r"]
        )
    assert con_ambos.value.code == 2


def test_run_con_suite_guarda_bloque_suite(monkeypatch, tmp_path, capsys):
    import tools.providers as providers_mod

    monkeypatch.setitem(providers_mod.PROVIDER_REGISTRY, "fake", FakeAdapterDisponible())
    raiz = tmp_path / "evals con espacios ñ"
    codigo = main(
        ["run", "--suite", _RUTA_SUITE, "--provider", "fake", "--run-id", "run-suite", "--root", str(raiz)]
    )
    assert codigo == 0
    corrida = storage.load_run("run-suite", root=raiz)
    assert corrida["schema_version"] == 1
    assert corrida["suite"]["suite_id"] == "harmessi-core-synthetic"
    assert len(corrida["suite"]["suite_hash"]) == 64
    assert len(corrida["resultados"]) >= 8
    assert "suite: harmessi-core-synthetic" in capsys.readouterr().out


def test_run_con_suite_invalida_exit_1(monkeypatch, tmp_path, capsys):
    import tools.providers as providers_mod

    monkeypatch.setitem(providers_mod.PROVIDER_REGISTRY, "fake", FakeAdapterDisponible())
    ruta = tmp_path / "mala.suite.json"
    ruta.write_text("{}", encoding="utf-8")
    codigo = main(["run", "--suite", str(ruta), "--provider", "fake", "--run-id", "r", "--root", str(tmp_path)])
    assert codigo == 1
    assert "Traceback" not in capsys.readouterr().err


def test_suite_check_valida_publica(capsys):
    assert main(["suite-check", "--suite", _RUTA_SUITE]) == 0
    assert "harmessi-core-synthetic" in capsys.readouterr().out
    assert main(["suite-check", "--suite", _RUTA_SUITE, "--json"]) == 0
    datos = json.loads(capsys.readouterr().out)
    assert datos["valida"] is True and datos["casos"] >= 8 and len(datos["suite_hash"]) == 64


def test_suite_check_invalida_exit_1(tmp_path, capsys):
    ruta = tmp_path / "mala.suite.json"
    ruta.write_text(json.dumps({"suite_contract_version": 9}), encoding="utf-8")
    assert main(["suite-check", "--suite", str(ruta)]) == 1
    assert "inválida" in capsys.readouterr().err
    assert main(["suite-check", "--suite", str(ruta), "--json"]) == 1
    assert json.loads(capsys.readouterr().out)["valida"] is False
    assert main(["suite-check", "--suite", str(tmp_path / "no-existe.json")]) == 1


def test_compare_imprime_veredicto_y_json_lo_incluye(tmp_path, capsys):
    target = EvalTarget(provider_id="fake")

    def _res(passed):
        return [
            EvalResult("r", "s1", target, 0, True, None, 0.1, "x",
                       ScoreResult(passed=passed, score=1.0 if passed else 0.0, detail=""),
                       "0.4.0", "2026-09-17T00:00:00+00:00")
        ]

    storage.save_run("a", _res(False), target, root=tmp_path, cases_hash="h")
    storage.save_run("b", _res(True), target, root=tmp_path, cases_hash="h")
    assert main(["compare", "--baseline", "a", "--candidate", "b", "--root", str(tmp_path)]) == 0
    assert "VEREDICTO: candidate_better" in capsys.readouterr().out
    assert main(["compare", "--baseline", "a", "--candidate", "b", "--root", str(tmp_path), "--json"]) == 0
    datos = json.loads(capsys.readouterr().out)
    assert datos["verdict"] == "candidate_better"
    assert datos["verdict_reason"]


def test_run_con_scenarios_persiste_cases_hash(monkeypatch, tmp_path):
    import tools.providers as providers_mod

    monkeypatch.setitem(providers_mod.PROVIDER_REGISTRY, "fake", FakeAdapterDisponible())
    for run_id in ("r1", "r2"):
        assert main(
            ["run", "--scenarios", _RUTA_EXAMPLES, "--provider", "fake", "--run-id", run_id, "--root", str(tmp_path)]
        ) == 0
    c1 = storage.load_run("r1", root=tmp_path)
    c2 = storage.load_run("r2", root=tmp_path)
    assert len(c1["cases_hash"]) == 64 and c1["cases_hash"] == c2["cases_hash"]
    assert "suite" not in c1


def test_compare_run_inexistente_mensaje_limpio_sin_ruta(tmp_path, capsys):
    codigo = main(["compare", "--baseline", "nada", "--candidate", "nada", "--root", str(tmp_path)])
    assert codigo == 1
    err = capsys.readouterr().err
    assert "Traceback" not in err
    assert str(tmp_path) not in err


def test_run_oserror_al_cargar_exit_1_sin_ruta_absoluta(monkeypatch, tmp_path, capsys):
    import tools.providers as providers_mod

    monkeypatch.setitem(providers_mod.PROVIDER_REGISTRY, "fake", FakeAdapterDisponible())
    ruta = tmp_path / "carpeta"
    ruta.mkdir()  # un directorio en lugar de un archivo => OSError al leer
    codigo = main(["run", "--scenarios", str(ruta), "--provider", "fake", "--run-id", "r", "--root", str(tmp_path)])
    assert codigo == 1
    err = capsys.readouterr().err
    assert "Traceback" not in err
    assert str(tmp_path) not in err


def test_compare_version_futura_exit_1(tmp_path, capsys):
    directorio = tmp_path / "futuro"
    directorio.mkdir()
    (directorio / "result.json").write_text(
        json.dumps({"schema_version": 99, "resultados": []}), encoding="utf-8"
    )
    codigo = main(["compare", "--baseline", "futuro", "--candidate", "futuro", "--root", str(tmp_path)])
    assert codigo == 1
    assert "Traceback" not in capsys.readouterr().err


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

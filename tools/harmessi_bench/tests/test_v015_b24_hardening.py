"""Tests de endurecimiento v0.15 T6 (B-24): `run_id` reservados de Windows,
`load_run` con result.json corrupto, `--fail-on-failure`, `bloque_suite`
incompleto, casos v0 como suite y ids NFC/NFD."""
from __future__ import annotations

import json
import unicodedata

import pytest

from tools.harmessi_bench.cli import main
from tools.harmessi_bench.scenarios import load_scenarios
from tools.harmessi_bench.storage import load_run, validar_run_id
from tools.harmessi_bench.suite import bloque_suite, load_suite_y_casos
from tools.harmessi_bench.tests.test_cli import FakeAdapterDisponible


@pytest.mark.parametrize(
    "malo",
    ["CON", "con", "Prn", "AUX", "nul", "COM1", "com9", "LPT1", "lpt9", "con.txt", "NUL.log", "foo.", "run-1."],
)
def test_run_id_reservado_o_con_punto_final_rechazado(malo):
    with pytest.raises(ValueError):
        validar_run_id(malo)


@pytest.mark.parametrize("bueno", ["run-1", "console", "com10", "com0", "lpt10", "a.con", "aux-1"])
def test_run_id_normal_sigue_valido(bueno):
    assert validar_run_id(bueno) == bueno


def test_load_run_result_json_corrupto_valueerror(tmp_path):
    directorio = tmp_path / "run-roto"
    directorio.mkdir()
    (directorio / "result.json").write_text("{no es json", encoding="utf-8")
    with pytest.raises(ValueError, match="corrupto"):
        load_run("run-roto", root=tmp_path)


def test_compare_con_result_json_corrupto_exit_1_sin_traceback(tmp_path, capsys):
    directorio = tmp_path / "run-roto"
    directorio.mkdir()
    (directorio / "result.json").write_text("{no es json", encoding="utf-8")
    codigo = main(["compare", "--baseline", "run-roto", "--candidate", "run-roto", "--root", str(tmp_path)])
    assert codigo == 1
    err = capsys.readouterr().err
    assert err.strip() and "Traceback" not in err


def test_run_con_result_existente_corrupto_exit_1_sin_traceback(monkeypatch, tmp_path, capsys):
    import tools.providers as providers_mod

    monkeypatch.setitem(providers_mod.PROVIDER_REGISTRY, "fake", FakeAdapterDisponible())
    directorio = tmp_path / "run-roto"
    directorio.mkdir()
    (directorio / "result.json").write_text("[1, 2", encoding="utf-8")
    ruta = tmp_path / "casos.json"
    ruta.write_text(json.dumps({"escenarios": [_caso("a", "OK")]}), encoding="utf-8")
    codigo = main(["run", "--scenarios", str(ruta), "--provider", "fake", "--run-id", "run-roto",
                   "--root", str(tmp_path)])
    assert codigo == 1
    err = capsys.readouterr().err
    assert err.strip() and "Traceback" not in err


def _caso(scenario_id: str, valor: str) -> dict:
    # El FakeAdapter responde "OK" si el prompt contiene "OK".
    return {"scenario_id": scenario_id, "prompt": "Respondé OK", "expected": {"tipo": "exact", "valor": valor}}


def _correr(monkeypatch, tmp_path, casos, run_id, *extra):
    import tools.providers as providers_mod

    monkeypatch.setitem(providers_mod.PROVIDER_REGISTRY, "fake", FakeAdapterDisponible())
    ruta = tmp_path / "casos.json"
    ruta.write_text(json.dumps({"escenarios": casos}), encoding="utf-8")
    return main(["run", "--scenarios", str(ruta), "--provider", "fake", "--run-id", run_id,
                 "--root", str(tmp_path / "evals"), *extra])


def test_run_sin_flag_devuelve_0_aunque_falle(monkeypatch, tmp_path):
    assert _correr(monkeypatch, tmp_path, [_caso("a", "otra-cosa")], "r-sin") == 0


def test_run_fail_on_failure_devuelve_1_y_guarda(monkeypatch, tmp_path):
    codigo = _correr(monkeypatch, tmp_path, [_caso("a", "otra-cosa")], "r-con", "--fail-on-failure")
    assert codigo == 1
    corrida = load_run("r-con", root=tmp_path / "evals")  # se guardó antes de devolver 1
    assert corrida["resultados"][0]["score"]["passed"] is False


def test_run_fail_on_failure_devuelve_0_si_todo_pasa(monkeypatch, tmp_path):
    assert _correr(monkeypatch, tmp_path, [_caso("a", "OK")], "r-ok", "--fail-on-failure") == 0


def test_resume_sin_pendientes_devuelve_0_aunque_haya_fallo_con_flag(monkeypatch, tmp_path):
    # Comportamiento documentado en el help: con --resume y nada pendiente,
    # --fail-on-failure no aplica (devuelve 0 sin cambios).
    casos = [_caso("a", "otra-cosa")]
    assert _correr(monkeypatch, tmp_path, casos, "r-res") == 0
    assert _correr(monkeypatch, tmp_path, casos, "r-res", "--resume", "--fail-on-failure") == 0


def test_help_fail_on_failure_documenta_exit_1_y_resume():
    import argparse

    from tools.harmessi_bench.cli import _construir_parser

    parser = _construir_parser()
    sub = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    ayuda = " ".join(
        a.help for a in sub.choices["run"]._actions if "--fail-on-failure" in a.option_strings
    )
    assert "error de uso" in ayuda
    assert "nada pendiente" in ayuda


def test_bloque_suite_dict_incompleto_valueerror():
    with pytest.raises(ValueError, match="suite_hash"):
        bloque_suite({"suite_id": "s", "suite_version": 1})
    with pytest.raises(ValueError):
        bloque_suite({})


def _escribir_suite(directorio, version_casos, casos):
    directorio.mkdir(parents=True, exist_ok=True)
    contenido = {"escenarios": casos}
    if version_casos is not None:
        contenido["case_contract_version"] = version_casos
    (directorio / "casos.json").write_text(json.dumps(contenido), encoding="utf-8")
    ruta = directorio / "x.suite.json"
    ruta.write_text(json.dumps({
        "suite_contract_version": 1, "suite_id": "s", "suite_version": 1,
        "cases_file": "casos.json", "case_ids": [c["scenario_id"] for c in casos],
    }), encoding="utf-8")
    return ruta


@pytest.mark.parametrize("version_casos", [None, 0])
def test_suite_con_casos_v0_rechazada(tmp_path, version_casos):
    ruta = _escribir_suite(tmp_path, version_casos, [_caso("a", "OK")])
    with pytest.raises(ValueError, match="case_contract_version"):
        load_suite_y_casos(ruta)


def test_suite_con_casos_v1_sigue_valida(tmp_path):
    ruta = _escribir_suite(tmp_path, 1, [_caso("a", "OK")])
    suite, _ = load_suite_y_casos(ruta)
    assert suite.case_contract_version == 1


def test_run_id_no_ascii_nfc_y_nfd_ambos_rechazados():
    # El regex de run_id es ASCII-only: "é" en NFC y en NFD se rechazan por igual.
    for forma in ("NFC", "NFD"):
        with pytest.raises(ValueError):
            validar_run_id(unicodedata.normalize(forma, "corrida-é"))


def test_scenario_id_nfc_y_nfd_se_tratan_como_ids_distintos(tmp_path):
    # Documenta el comportamiento actual: `scenario_id` no tiene regex ASCII (solo
    # string no vacío) y NO se normaliza; NFC y NFD son dos ids distintos.
    nfc = unicodedata.normalize("NFC", "caso-é")
    nfd = unicodedata.normalize("NFD", "caso-é")
    assert nfc != nfd
    ruta = tmp_path / "casos.json"
    ruta.write_text(json.dumps({"escenarios": [_caso(nfc, "OK"), _caso(nfd, "OK")]}), encoding="utf-8")
    ids = [e.scenario_id for e in load_scenarios(ruta)]
    assert ids == [nfc, nfd]

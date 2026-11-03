"""Tests de endurecimiento del Change 2 (v0.13): escritura atómica, run_id,
redacción ampliada, manifest incompleto, sesiones, cambio de identidad durante
la corrida y run_manifest inválido. Todo sintético."""
from __future__ import annotations

import copy
import json
import os
import time

import pytest

from tools.harmessi_bench import cli as cli_mod
from tools.harmessi_bench import runmanifest, storage
from tools.harmessi_bench.cli import main
from tools.harmessi_bench.compare import compare_runs
from tools.harmessi_bench.core import EvalResult, EvalTarget, ScoreResult
from tools.harmessi_bench.redact import MARCADOR_RUTA, MARCADOR_TOKEN, redactar_texto
from tools.harmessi_bench.tests.test_runmanifest import (  # noqa: F401  (entorno es un fixture)
    _DIR_SKILLS,
    _Adapter,
    _guardar,
    _manifest,
    _repo_falso,
    _res,
    entorno,
)

# --- M5: redacción ampliada --------------------------------------------------------


@pytest.mark.parametrize("texto, valor", [
    ('{"api_key": "x1"}', "x1"),
    ('{"token": "q"}', ': "q"'),
    ("{'secret': 'zz'}", "zz"),
    ('{"password":"p9"}', "p9"),
    ('{"Password": "abc"}', "abc"),
])
def test_redacta_json_clave_valor_cualquier_longitud(texto, valor):
    salida = redactar_texto(texto)
    assert MARCADOR_TOKEN in salida
    assert valor not in salida
    assert redactar_texto(salida) == salida


def test_json_clave_conserva_la_clave():
    salida = redactar_texto('{"api_key": "x1", "otro": "visible"}')
    assert '"api_key"' in salida and "visible" in salida and "x1" not in salida


def test_ruta_windows_con_espacios():
    salida = redactar_texto(r"abrí C:\Users\Juan Perez\docs\a.txt ok")
    assert "Juan" not in salida and "Perez" not in salida and MARCADOR_RUTA in salida


@pytest.mark.parametrize("n", [1, 2, 3, 4])
def test_ruta_windows_con_barras_escapadas(n):
    sep = "\\" * n
    salida = redactar_texto(f"C:{sep}Users{sep}ejemplo{sep}x.py")
    assert "ejemplo" not in salida and MARCADOR_RUTA in salida


@pytest.mark.parametrize("texto", ["/HOME/ejemplo/x", "/users/ejemplo/x", "/Home/ejemplo/x"])
def test_ruta_posix_sin_distinguir_mayusculas(texto):
    assert "ejemplo" not in redactar_texto(texto)


@pytest.mark.parametrize("texto", ["bearer abcdef1234567890", "BEARER abcdef1234567890", "Bearer abcdef1234567890"])
def test_bearer_case_insensitive(texto):
    salida = redactar_texto(texto)
    assert "abcdef1234567890" not in salida and redactar_texto(salida) == salida


@pytest.mark.parametrize("token", [
    "gho_abcdefghijklmnop1234", "ghs_abcdefghijklmnop1234", "glpat-abcdefghijklmnop1234",
    "hf_abcdefghijklmnop1234", "npm_abcdefghijklmnop1234", "AIzaSyABCDEFGHIJKLMNOPQRSTUV123",
    "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ4In0.firma_falsa-123",
])
def test_prefijos_adicionales(token):
    salida = redactar_texto(f"valor {token} fin")
    assert token not in salida and MARCADOR_TOKEN in salida and "fin" in salida


@pytest.mark.parametrize("entrada", ["a" * 100_000, "a." * 50_000, "a@" * 20_000, "x" * 50_000 + "@"], ids=["a-largo", "a-punto", "a-arroba", "x-arroba-final"])
def test_rendimiento_entradas_largas(entrada):
    inicio = time.perf_counter()
    redactar_texto(entrada)
    assert time.perf_counter() - inicio < 1.0


# --- H1: escritura atómica y surrogates ---------------------------------------------


def test_surrogate_suelto_no_lanza_ni_trunca(tmp_path):
    resultado = _res()
    resultado.stdout_excerpt = "antes \ud800 despues"
    storage.save_run("r", [resultado, _res("s2")], EvalTarget(provider_id="fake"), root=tmp_path)
    corrida = storage.load_run("r", root=tmp_path)
    assert len(corrida["resultados"]) == 2
    assert corrida["resultados"][0]["stdout_excerpt"].startswith("antes ")
    assert corrida["resultados"][0]["stdout_excerpt"].endswith(" despues")


def test_result_existente_intacto_si_falla_el_reemplazo(tmp_path, monkeypatch):
    storage.save_run("r", [_res("original")], EvalTarget(provider_id="fake"), root=tmp_path)
    ruta = tmp_path / "r" / "result.json"
    antes = ruta.read_bytes()

    def _falla(*_a, **_k):
        raise OSError("fallo simulado")

    monkeypatch.setattr(os, "replace", _falla)
    with pytest.raises(OSError):
        storage.save_run("r", [_res("nuevo")], EvalTarget(provider_id="fake"), root=tmp_path)
    assert ruta.read_bytes() == antes
    assert not (tmp_path / "r" / "result.json.tmp").exists()


def test_cli_guardado_fallido_exit_1(entorno, monkeypatch, capsys):
    _adapter, _repo, _evals, correr = entorno

    def _falla(*_a, **_k):
        raise OSError("fallo simulado")

    monkeypatch.setattr(storage, "save_run", _falla)
    assert correr() == 1
    err = capsys.readouterr().err
    assert "no se pudo guardar" in err and "Traceback" not in err


# --- M5: availability_error y target redactados ---------------------------------------


def test_availability_error_y_target_se_redactan(tmp_path):
    resultado = _res()
    resultado.availability_error = "falló leyendo /home/ejemplo/x"
    target = EvalTarget(provider_id="fake", model="usuario@example.com", effort="sk-abcdefghijklmnop1234")
    storage.save_run("r", [resultado], target, root=tmp_path)
    crudo = (tmp_path / "r" / "result.json").read_text(encoding="utf-8")
    for secreto in ("ejemplo", "usuario@example.com", "sk-abcdefghijklmnop1234"):
        assert secreto not in crudo


def test_manifest_redacta_model_y_effort(tmp_path):
    m = runmanifest.construir_manifest(
        "r", EvalTarget(provider_id="fake", model="usuario@example.com", effort="ghp_abcdefghijklmnopqrst"),
        cases_hash="c" * 64, repo_root=_repo_falso(tmp_path),
    )
    texto = json.dumps(m)
    assert "usuario@example.com" not in texto and "ghp_abcdefghijklmnopqrst" not in texto


# --- L7: run_id ------------------------------------------------------------------------


@pytest.mark.parametrize("malo", ["..\\x", "../x", "a/b", "", ".oculto", "a" * 129, "x y", None])
def test_run_id_invalido_en_storage(tmp_path, malo):
    with pytest.raises(ValueError):
        storage.save_run(malo, [], EvalTarget(provider_id="fake"), root=tmp_path)
    with pytest.raises(ValueError):
        storage.load_run(malo, root=tmp_path)


def test_run_id_ruta_absoluta_invalido(tmp_path):
    with pytest.raises(ValueError):
        storage.save_run(str(tmp_path / "abs"), [], EvalTarget(provider_id="fake"), root=tmp_path)


@pytest.mark.parametrize("bueno", ["a", "run-1", "run_2.v3", "A" * 128])
def test_run_id_valido(tmp_path, bueno):
    assert storage.validar_run_id(bueno) == bueno


# --- M1: manifest incompleto -------------------------------------------------------------


def test_skills_vacio_marca_problema(tmp_path):
    raiz = _repo_falso(tmp_path, {})
    m = _manifest(raiz)
    assert "skills_vacio" in m["problemas"]
    assert "skills" in runmanifest.campos_faltantes(m)
    assert runmanifest.evaluar_compatibilidad(m, m) == ["manifest_incompleto"]


def test_directorio_de_skills_ausente_marca_problema(tmp_path):
    vacio = tmp_path / "sin skills"
    vacio.mkdir()
    m = _manifest(vacio)
    assert "directorio_skills_ausente" in m["problemas"]
    assert runmanifest.campos_faltantes(m)


def test_hash_ilegible_marca_problema(tmp_path, monkeypatch):
    raiz = _repo_falso(tmp_path)
    monkeypatch.setattr(runmanifest, "_hash_archivo", lambda _r: runmanifest.HASH_ILEGIBLE)
    m = _manifest(raiz)
    assert any(p.startswith("hash_ilegible:skill:") for p in m["problemas"])
    assert "skills" in runmanifest.campos_faltantes(m)
    assert runmanifest.evaluar_compatibilidad(m, m) == ["manifest_incompleto"]


def test_manifest_valido_no_tiene_problemas(tmp_path):
    m = _manifest(_repo_falso(tmp_path))
    assert m["problemas"] == [] and runmanifest.campos_faltantes(m) == []


def test_compare_con_manifest_incompleto_es_inconclusive(tmp_path):
    (tmp_path / "x").mkdir()
    (tmp_path / "y").mkdir()
    bueno = _manifest(_repo_falso(tmp_path / "x"))
    malo = _manifest(_repo_falso(tmp_path / "y", {}))
    r = compare_runs(_guardar(tmp_path, "a", bueno), _guardar(tmp_path, "b", malo))
    assert r.verdict == "inconclusive" and "incompleto" in r.verdict_reason


def test_cli_con_manifest_incompleto_no_corre_ni_persiste(entorno, capsys):
    adapter, raiz_repo, raiz_evals, correr = entorno
    for ruta in raiz_repo.joinpath(*_DIR_SKILLS).glob("*.md"):
        ruta.unlink()
    assert correr() == 1
    assert "manifest incompleto" in capsys.readouterr().err
    assert adapter.prompts == []
    assert not (raiz_evals / "rid" / "result.json").exists()


# --- M3: sesiones -------------------------------------------------------------------------


def test_manifest_nuevo_tiene_una_sesion_no_material(tmp_path):
    m = _manifest(_repo_falso(tmp_path), seed=5)
    assert len(m["sesiones"]) == 1
    assert set(m["sesiones"][0]) == {"started_utc", "finished_utc", "git_commit", "seed"}
    assert m["sesiones"][0]["seed"] == 5
    otro = copy.deepcopy(m)
    otro["sesiones"].append({"started_utc": "x", "finished_utc": "y", "git_commit": "z", "seed": 1})
    assert runmanifest.calcular_identity_hash(otro) == m["identity_hash"]


def test_agregar_sesion_conserva_previas_y_sintetiza_si_faltan(tmp_path):
    raiz = _repo_falso(tmp_path)
    a = _manifest(raiz, seed=1)
    b = _manifest(raiz, seed=2)
    combinado = runmanifest.agregar_sesion(a, b)
    assert len(combinado["sesiones"]) == 2
    assert combinado["sesiones"][0] == a["sesiones"][0] and combinado["sesiones"][1]["seed"] == 2
    assert combinado["started_utc"] == a["started_utc"] and combinado["identity_hash"] == a["identity_hash"]
    legado = {k: v for k, v in a.items() if k != "sesiones"}
    sintetizado = runmanifest.agregar_sesion(legado, b)
    assert len(sintetizado["sesiones"]) == 2 and sintetizado["sesiones"][0]["seed"] == 1


def test_resume_agrega_sesion(entorno):
    adapter, _, raiz_evals, correr = entorno
    adapter.fallar = [1]
    assert correr("--seed", "1") == 0
    primera = storage.load_run("rid", root=raiz_evals)["run_manifest"]
    assert len(primera["sesiones"]) == 1
    assert correr("--resume", "--seed", "2") == 0
    final = storage.load_run("rid", root=raiz_evals)["run_manifest"]
    assert len(final["sesiones"]) == 2
    assert final["sesiones"][0]["started_utc"] == primera["sesiones"][0]["started_utc"]
    assert final["sesiones"][1]["seed"] == 2
    assert final["identity_hash"] == primera["identity_hash"]


# --- H2: identidad cambia durante la corrida ---------------------------------------------


class _AdapterQueEditaSkills(_Adapter):
    def __init__(self, archivo):
        super().__init__()
        self.archivo = archivo

    def invoke(self, request):
        self.archivo.write_text("editada durante la corrida\n", encoding="utf-8")
        return super().invoke(request)


def test_cambio_de_skills_durante_la_corrida_no_escribe(entorno, monkeypatch, capsys):
    import tools.providers as providers_mod

    _adapter, raiz_repo, raiz_evals, correr = entorno
    editor = _AdapterQueEditaSkills(raiz_repo.joinpath(*_DIR_SKILLS) / "alfa.md")
    monkeypatch.setitem(providers_mod.PROVIDER_REGISTRY, "fake", editor)
    assert correr() == 1
    assert "cambió durante la corrida" in capsys.readouterr().err
    assert not (raiz_evals / "rid" / "result.json").exists()


def test_cambio_durante_resume_no_toca_el_result(entorno, monkeypatch):
    import tools.providers as providers_mod

    adapter, raiz_repo, raiz_evals, correr = entorno
    adapter.fallar = [1]
    assert correr() == 0
    antes = (raiz_evals / "rid" / "result.json").read_bytes()
    editor = _AdapterQueEditaSkills(raiz_repo.joinpath(*_DIR_SKILLS) / "alfa.md")
    monkeypatch.setitem(providers_mod.PROVIDER_REGISTRY, "fake", editor)
    assert correr("--resume") == 1
    assert (raiz_evals / "rid" / "result.json").read_bytes() == antes


def test_manifest_persistido_es_el_del_inicio(entorno):
    _adapter, _repo, raiz_evals, correr = entorno
    assert correr() == 0
    m = storage.load_run("rid", root=raiz_evals)["run_manifest"]
    assert m["started_utc"] <= m["finished_utc"]
    assert m["sesiones"][0]["finished_utc"] == m["finished_utc"]


# --- L2: run_manifest inválido en el result existente -----------------------------------


@pytest.mark.parametrize("invalido", ["texto", 5, ["lista"], True])
@pytest.mark.parametrize("flags", [(), ("--resume",)])
def test_run_manifest_no_dict_en_existente_exit_1(entorno, invalido, flags):
    adapter, _, raiz_evals, correr = entorno
    storage.save_run("rid", [_res("viejo")], EvalTarget(provider_id="fake"), root=raiz_evals,
                     run_manifest=invalido)
    antes = (raiz_evals / "rid" / "result.json").read_bytes()
    assert correr(*flags) == 1
    assert (raiz_evals / "rid" / "result.json").read_bytes() == antes
    assert adapter.prompts == []

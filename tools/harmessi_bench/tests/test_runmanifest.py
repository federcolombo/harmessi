"""Tests de `runmanifest`, `compare` con manifests y `cli run --resume`
(v0.13 Change 2, R1-R4, R7-R12). Todo sintético, con tempdirs con espacios y
Unicode; Git se simula con un directorio no-repo o parcheando `get_head`."""
from __future__ import annotations

import copy
import json
import os
import platform

import pytest

from tools.harmessi_bench import runmanifest, storage
from tools.harmessi_bench.cli import main
from tools.harmessi_bench import cli as cli_mod
from tools.harmessi_bench.compare import compare_runs
from tools.harmessi_bench.core import EvalResult, EvalTarget, ScoreResult
from tools.harmessi_bench.runmanifest import (
    MANIFEST_VERSION,
    calcular_identity_hash,
    construir_manifest,
    evaluar_compatibilidad,
    hash_contenido,
    hash_skills,
)
from tools.providers.core import InvocationResult, ProviderCapabilities, ProviderInfo

_DIR_SKILLS = (".claude", "skills", "lead-data-scientist", "skills")


def _repo_falso(base, skills=None, guardrails=None):
    """Árbol mínimo de skills en un tmp (no es un repo Git)."""
    raiz = base / "repo ñandú con espacios"
    directorio = raiz.joinpath(*_DIR_SKILLS)
    directorio.mkdir(parents=True, exist_ok=True)
    por_defecto = {"alfa": "hola\n", "beta": "mundo\n"}
    for nombre, contenido in (por_defecto if skills is None else skills).items():
        (directorio / f"{nombre}.md").write_bytes(contenido.encode("utf-8"))
    if guardrails is not None:
        (raiz / ".claude" / "guardrails.json").write_text(guardrails, encoding="utf-8")
    return raiz


def _sub(base, nombre):
    """Subdirectorio nuevo de `base` (para tener varios repos falsos en un tmp)."""
    ruta = base / nombre
    ruta.mkdir()
    return ruta


def _manifest(raiz, run_id="r1", **kw):
    return construir_manifest(run_id, EvalTarget(provider_id="fake", model="m", effort="e"),
                              cases_hash="c" * 64, repo_root=raiz, **kw)


# --- R1-R4 ------------------------------------------------------------------------


def test_manifest_campos_y_json_serializable(tmp_path):
    m = _manifest(_repo_falso(tmp_path), seed=7)
    for clave in ("manifest_version", "run_id", "harmessi_version", "git", "skills", "surfaces_hash",
                  "guardrails_hash", "target", "evaluator_version", "suite", "cases_hash", "seed",
                  "platform", "started_utc", "finished_utc", "identity_hash"):
        assert clave in m
    assert m["manifest_version"] == MANIFEST_VERSION == 1
    assert m["seed"] == 7 and m["suite"] is None and m["guardrails_hash"] is None
    assert set(m["skills"]) == {"alfa", "beta"}
    assert set(m["platform"]) == {"system", "python", "implementation"}
    assert json.loads(json.dumps(m)) == m
    assert runmanifest.campos_faltantes(m) == []


def test_manifest_sin_entorno_hostname_usuario_ni_rutas(tmp_path, monkeypatch):
    monkeypatch.setenv("VARIABLE_SECRETA_FALSA", "valor-secreto-falso-123")
    raiz = _repo_falso(tmp_path)
    texto = json.dumps(_manifest(raiz))
    assert "valor-secreto-falso-123" not in texto and "VARIABLE_SECRETA_FALSA" not in texto
    assert str(raiz) not in texto and str(tmp_path) not in texto
    assert len(platform.node()) <= 3 or platform.node() not in texto
    for usuario in (os.environ.get("USERNAME"), os.environ.get("USER")):
        if usuario and len(usuario) > 3:
            assert usuario not in texto
    assert "environ" not in texto.lower()


def test_git_desconocido_en_directorio_no_repo(tmp_path):
    m = _manifest(_repo_falso(tmp_path))
    assert m["git"] == {"commit": "unknown", "clean": None}


def test_git_desconocido_si_get_head_falla(tmp_path, monkeypatch):
    import tools.dsguard.repo as repo_mod

    def _falla(_raiz):
        raise RuntimeError("git no disponible")

    monkeypatch.setattr(repo_mod, "get_head", _falla)
    assert _manifest(_repo_falso(tmp_path))["git"] == {"commit": "unknown", "clean": None}


def test_git_limpio_none_si_is_tree_clean_falla(tmp_path, monkeypatch):
    import tools.dsguard.repo as repo_mod

    monkeypatch.setattr(repo_mod, "get_head", lambda _r: ("a" * 40, "main"))

    def _falla(_r):
        raise repo_mod.GitCommandError("x")

    monkeypatch.setattr(repo_mod, "is_tree_clean", _falla)
    assert _manifest(_repo_falso(tmp_path))["git"] == {"commit": "a" * 40, "clean": None}
    monkeypatch.setattr(repo_mod, "is_tree_clean", lambda _r: True)
    assert _manifest(_repo_falso(tmp_path))["git"]["clean"] is True


def test_hash_skills_invariante_a_crlf(tmp_path):
    lf = _repo_falso(_sub(tmp_path, "a"), {"s": "l1\nl2\n"})
    crlf = _repo_falso(_sub(tmp_path, "b"), {"s": "l1\r\nl2\r\n"})
    assert hash_skills(lf) == hash_skills(crlf)
    assert hash_skills(lf)["s"] == hash_contenido(b"l1\nl2\n")
    assert hash_contenido(b"a\r\nb") == hash_contenido(b"a\nb")
    assert hash_contenido(b"a\nb") != hash_contenido(b"a\nc")


def test_identity_hash_estable_y_sensible_a_lo_material(tmp_path):
    raiz = _repo_falso(tmp_path)
    base = _manifest(raiz, run_id="r1")
    # Mismo material, otro run_id/seed/timestamps/plataforma/git => mismo hash.
    otro = _manifest(raiz, run_id="r2", seed=3, started_utc="2020-01-01T00:00:00+00:00")
    otro["platform"] = {"system": "X", "python": "0", "implementation": "Y"}
    otro["git"] = {"commit": "z", "clean": False}
    assert otro["identity_hash"] == base["identity_hash"]
    assert calcular_identity_hash(otro) == base["identity_hash"]  # recalculado tras mutar campos no materiales
    assert len(base["identity_hash"]) == 64

    def _con(**cambios):
        m = copy.deepcopy(base)
        for clave, valor in cambios.items():
            if clave.startswith("target_"):
                m["target"][clave[7:]] = valor
            else:
                m[clave] = valor
        return calcular_identity_hash(m)

    assert _con(skills={"alfa": "0" * 64}) != base["identity_hash"]
    assert _con(target_provider_id="otro") != base["identity_hash"]
    assert _con(target_model="otro") != base["identity_hash"]
    assert _con(target_effort="otro") != base["identity_hash"]
    assert _con(evaluator_version="otro/2") != base["identity_hash"]
    assert _con(suite={"suite_id": "s", "suite_version": "1", "suite_hash": "h"}) != base["identity_hash"]
    assert _con(cases_hash="d" * 64) != base["identity_hash"]
    assert _con(guardrails_hash="e" * 64) != base["identity_hash"]


def test_identity_hash_cambia_si_cambia_una_skill_en_disco(tmp_path):
    uno = _repo_falso(_sub(tmp_path, "x"), {"s": "a\n"})
    dos = _repo_falso(_sub(tmp_path, "y"), {"s": "b\n"})
    assert _manifest(uno)["identity_hash"] != _manifest(dos)["identity_hash"]
    assert _manifest(uno)["surfaces_hash"] != _manifest(dos)["surfaces_hash"]


def test_guardrails_hash_presente_si_existe(tmp_path):
    m = _manifest(_repo_falso(tmp_path, guardrails='{"a": 1}'))
    assert len(m["guardrails_hash"]) == 64


# --- R10 --------------------------------------------------------------------------


def test_evaluar_compatibilidad(tmp_path):
    raiz = _repo_falso(tmp_path)
    a = _manifest(raiz, run_id="a")
    b = _manifest(raiz, run_id="b")
    assert evaluar_compatibilidad(a, b) == []
    # commit distinto: compatible, con advertencia.
    c = copy.deepcopy(b)
    c["git"] = {"commit": "otro", "clean": True}
    assert evaluar_compatibilidad(a, c) == []
    assert runmanifest.advertencias_compatibilidad(a, c)
    # material distinto.
    d = copy.deepcopy(b)
    d["skills"]["alfa"] = "0" * 64
    d["target"]["model"] = "otro"
    d["evaluator_version"] = "x/9"
    assert evaluar_compatibilidad(a, d) == ["evaluator_version", "skills", "target.model"]
    assert evaluar_compatibilidad(a, {"x": 1}) == ["manifest_incompleto"]
    assert evaluar_compatibilidad("no-dict", a) == ["manifest_incompleto"]


# --- R7 / R8 / R9 -----------------------------------------------------------------


def _res(scenario_id="s1", passed=True, ok=True):
    return EvalResult("r", scenario_id, EvalTarget(provider_id="fake"), 0, ok, None, 0.1, "x",
                      ScoreResult(passed=passed, score=1.0 if passed else 0.0, detail=""),
                      "0.0.0", "2026-01-01T00:00:00+00:00")


def _guardar(root, run_id, manifest, passed=True):
    storage.save_run(run_id, [_res(passed=passed)], EvalTarget(provider_id="fake"), root=root,
                     cases_hash="c" * 64, run_manifest=manifest)
    return storage.load_run(run_id, root=root)


def test_save_load_run_manifest_y_ausente(tmp_path):
    m = _manifest(_repo_falso(tmp_path))
    corrida = _guardar(tmp_path, "con", m)
    assert corrida["run_manifest"] == m and corrida["schema_version"] == 1
    storage.save_run("sin", [_res()], EvalTarget(provider_id="fake"), root=tmp_path)
    assert "run_manifest" not in storage.load_run("sin", root=tmp_path)


def test_compare_solo_un_lado_con_manifest_es_inconclusive(tmp_path):
    m = _manifest(_repo_falso(tmp_path))
    con = _guardar(tmp_path, "con", m)
    sin = _guardar(tmp_path, "sin", None)
    for a, b in ((con, sin), (sin, con)):
        r = compare_runs(a, b)
        assert r.verdict == "inconclusive" and "run_manifest" in r.verdict_reason
        assert r.config_diff == []


def test_compare_distintas_skills_se_compara_y_lista_config_diff(tmp_path):
    uno = _repo_falso(_sub(tmp_path, "u"), {"s": "a\n"})
    dos = _repo_falso(_sub(tmp_path, "v"), {"s": "b\n"})
    base = _guardar(tmp_path, "base", _manifest(uno), passed=False)
    cand = _guardar(tmp_path, "cand", _manifest(dos), passed=True)
    r = compare_runs(base, cand)
    assert r.verdict == "candidate_better"
    assert "skills" in r.config_diff and "surfaces_hash" in r.config_diff
    assert r.config_diff == sorted(r.config_diff)


def test_compare_misma_identidad_registra_repeticion(tmp_path):
    raiz = _repo_falso(tmp_path)
    a = _guardar(tmp_path, "a", _manifest(raiz, run_id="a"), passed=False)
    b = _guardar(tmp_path, "b", _manifest(raiz, run_id="b"), passed=True)
    r = compare_runs(a, b)
    assert r.verdict == "candidate_better" and r.config_diff == []
    assert "misma configuración material: repetición" in r.verdict_reason


@pytest.mark.parametrize("campo, valor", [
    ("evaluator_version", "otro/2"),
    ("manifest_version", 2),
    ("cases_hash", "f" * 64),
    ("suite", {"suite_id": "s", "suite_version": "1", "suite_hash": "h"}),
])
def test_compare_inconclusive_si_difiere_contrato(tmp_path, campo, valor):
    raiz = _repo_falso(tmp_path)
    m1 = _manifest(raiz, run_id="a")
    m2 = copy.deepcopy(m1)
    m2[campo] = valor
    r = compare_runs(_guardar(tmp_path, "a", m1), _guardar(tmp_path, "b", m2))
    assert r.verdict == "inconclusive" and campo in r.verdict_reason
    assert campo in r.config_diff


def test_compare_manifest_incompleto_es_inconclusive(tmp_path):
    raiz = _repo_falso(tmp_path)
    m = _manifest(raiz)
    roto = {"manifest_version": 1}
    r = compare_runs(_guardar(tmp_path, "a", m), _guardar(tmp_path, "b", roto))
    assert r.verdict == "inconclusive" and "incompleto" in r.verdict_reason


def test_compare_sin_manifests_no_cambia(tmp_path):
    r = compare_runs(_guardar(tmp_path, "a", None, passed=False), _guardar(tmp_path, "b", None, passed=True))
    assert r.config_diff == [] and r.verdict == "candidate_better"


# --- R11 / R12: CLI ---------------------------------------------------------------


class _Adapter:
    provider_id = "fake"
    cli_command = "fake"
    display_name = "Fake"

    def __init__(self, fallar_ids=()):
        self.prompts = []
        self.fallar = list(fallar_ids)

    def detect(self):
        return ProviderInfo(provider_id="fake", display_name="Fake", cli_command="fake", available=True,
                            authenticated=True, version="0", capabilities=ProviderCapabilities(), detail="ok")

    def invoke(self, request):
        self.prompts.append(request.prompt)
        if self.fallar:
            self.fallar.pop()
            return InvocationResult(provider_id="fake", exit_code=1, stdout="", stderr="caído", ok=False,
                                    availability_error="timeout", duration_s=0.0)
        texto = "OK" if "OK" in request.prompt else ("4" if "2+2" in request.prompt else "rojo\nazul")
        return InvocationResult(provider_id="fake", exit_code=0, stdout=texto, stderr="", ok=True,
                                availability_error=None, duration_s=0.0)


@pytest.fixture
def entorno(tmp_path, monkeypatch):
    import tools.providers as providers_mod
    from pathlib import Path

    adapter = _Adapter()
    monkeypatch.setitem(providers_mod.PROVIDER_REGISTRY, "fake", adapter)
    raiz_repo = _repo_falso(tmp_path)
    monkeypatch.setattr(cli_mod, "_REPO_ROOT_MANIFEST", raiz_repo)
    ejemplos = str(Path(__file__).resolve().parents[1] / "scenarios" / "examples.json")
    raiz_evals = tmp_path / "evals ñ con espacios"

    def correr(*extra, run_id="rid"):
        return main(["run", "--scenarios", ejemplos, "--provider", "fake", "--run-id", run_id,
                     "--root", str(raiz_evals), *extra])

    return adapter, raiz_repo, raiz_evals, correr


def test_run_guarda_manifest_y_seed(entorno):
    adapter, _, raiz_evals, correr = entorno
    assert correr("--seed", "42") == 0
    m = storage.load_run("rid", root=raiz_evals)["run_manifest"]
    assert m["seed"] == 42 and m["run_id"] == "rid" and m["target"]["provider_id"] == "fake"
    assert runmanifest.campos_faltantes(m) == []


def test_run_id_existente_con_manifest_sin_resume_falla(entorno, capsys):
    adapter, _, raiz_evals, correr = entorno
    assert correr() == 0
    antes = (raiz_evals / "rid" / "result.json").read_bytes()
    llamadas = len(adapter.prompts)
    assert correr() == 1
    assert "--resume" in capsys.readouterr().err
    assert (raiz_evals / "rid" / "result.json").read_bytes() == antes
    assert len(adapter.prompts) == llamadas


def test_run_id_legado_sin_manifest_se_sobrescribe(entorno):
    adapter, _, raiz_evals, correr = entorno
    storage.save_run("rid", [_res("viejo")], EvalTarget(provider_id="fake"), root=raiz_evals)
    assert correr() == 0
    corrida = storage.load_run("rid", root=raiz_evals)
    assert "run_manifest" in corrida and "viejo" not in {r["scenario_id"] for r in corrida["resultados"]}


def test_resume_sin_corrida_o_sin_manifest_falla(entorno):
    adapter, _, raiz_evals, correr = entorno
    assert correr("--resume") == 1
    storage.save_run("rid", [_res("viejo")], EvalTarget(provider_id="fake"), root=raiz_evals)
    assert correr("--resume") == 1
    assert adapter.prompts == []


def test_resume_incompatible_falla_sin_tocar_el_result(entorno, capsys):
    adapter, raiz_repo, raiz_evals, correr = entorno
    assert correr() == 0
    antes = (raiz_evals / "rid" / "result.json").read_bytes()
    llamadas = len(adapter.prompts)
    (raiz_repo.joinpath(*_DIR_SKILLS) / "alfa.md").write_text("cambiada\n", encoding="utf-8")
    assert correr("--resume") == 1
    err = capsys.readouterr().err
    assert "incompatible" in err and "skills" in err
    assert (raiz_evals / "rid" / "result.json").read_bytes() == antes
    assert len(adapter.prompts) == llamadas


def test_resume_incompatible_por_model(entorno, capsys):
    adapter, _, raiz_evals, correr = entorno
    assert correr() == 0
    assert correr("--model", "otro", "--resume") == 1
    assert "target.model" in capsys.readouterr().err


def test_resume_compatible_solo_corre_pendientes(entorno):
    adapter, _, raiz_evals, correr = entorno
    adapter.fallar = [1]  # un solo escenario falla (ok=False) en la primera corrida
    assert correr() == 0
    primera = storage.load_run("rid", root=raiz_evals)
    fallidos = [r["scenario_id"] for r in primera["resultados"] if r["ok"] is False]
    assert len(fallidos) == 1 and len(primera["resultados"]) == 3
    adapter.prompts.clear()
    assert correr("--resume") == 0
    assert len(adapter.prompts) == 1
    final = storage.load_run("rid", root=raiz_evals)
    assert len(final["resultados"]) == 3 and all(r["ok"] for r in final["resultados"])
    assert final["run_manifest"]["started_utc"] == primera["run_manifest"]["started_utc"]
    # Ya completa: no corre nada y no modifica el archivo.
    adapter.prompts.clear()
    antes = (raiz_evals / "rid" / "result.json").read_bytes()
    assert correr("--resume") == 0
    assert adapter.prompts == [] and (raiz_evals / "rid" / "result.json").read_bytes() == antes


def test_compare_cli_imprime_config_diff(entorno, capsys):
    adapter, raiz_repo, raiz_evals, correr = entorno
    assert correr(run_id="base") == 0
    (raiz_repo.joinpath(*_DIR_SKILLS) / "alfa.md").write_text("cambiada\n", encoding="utf-8")
    assert correr(run_id="cand") == 0
    capsys.readouterr()
    assert main(["compare", "--baseline", "base", "--candidate", "cand", "--root", str(raiz_evals)]) == 0
    assert "CONFIG_DIFF" in capsys.readouterr().out

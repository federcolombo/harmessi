"""Tests de `tools/harmessi_bench/redact.py` y de su aplicación en `storage`
(v0.13 Change 2, R5-R6). Solo strings sintéticos."""
from __future__ import annotations

import pytest

from tools.harmessi_bench import storage
from tools.harmessi_bench.core import EvalResult, EvalTarget, ScoreResult
from tools.harmessi_bench.redact import (
    MARCADOR_EMAIL,
    MARCADOR_RUTA,
    MARCADOR_TOKEN,
    redactar_texto,
)


@pytest.mark.parametrize(
    "texto, secreto",
    [
        (r"error en C:\Users\ejemplo\proyecto\x.py linea 3", "ejemplo"),
        (r"error en D:\Users\ejemplo\x", "ejemplo"),
        ("error en C:/Users/ejemplo/x.py", "ejemplo"),
        ("ruta C:\\\\Users\\\\ejemplo\\\\x (json escapado)", "ejemplo"),
        ("leyendo /home/ejemplo/x/archivo.txt ahora", "ejemplo"),
        ("leyendo /Users/ejemplo/Documents/a.md ahora", "ejemplo"),
    ],
)
def test_redacta_rutas_de_usuario(texto, secreto):
    salida = redactar_texto(texto)
    assert secreto not in salida
    assert MARCADOR_RUTA in salida


def test_redacta_email():
    salida = redactar_texto("contacto: usuario@example.com, gracias")
    assert "usuario@example.com" not in salida
    assert MARCADOR_EMAIL in salida
    assert "gracias" in salida


@pytest.mark.parametrize(
    "token",
    [
        "sk-abcdefghijklmnop1234",
        "sk-ant-api03-ABCDEFGH_ijklmnop-1234",
        "ghp_abcdefghijklmnopqrstuvwx1234",
        "github_pat_11ABCDEFG0abcdefghijkl_mnop",
        "AKIAABCDEFGHIJKLMNOP",
        "xoxb-1234567890-abcdefghij",
        "xoxp-1234567890-abcdefghij",
    ],
)
def test_redacta_tokens_con_prefijo(token):
    salida = redactar_texto(f"la clave es {token} fin")
    assert token not in salida
    assert MARCADOR_TOKEN in salida
    assert "fin" in salida


def test_redacta_bearer():
    salida = redactar_texto("Authorization: Bearer abcdef1234567890XYZ")
    assert "abcdef1234567890XYZ" not in salida
    assert MARCADOR_TOKEN in salida


@pytest.mark.parametrize("clave", ["key", "token", "secret", "password", "API_KEY", "Password"])
def test_redacta_valor_largo_tras_clave(clave):
    valor = "0123456789abcdef0123456789abcdef"
    salida = redactar_texto(f"{clave}={valor}")
    assert valor not in salida
    assert MARCADOR_TOKEN in salida


def test_valor_corto_tras_clave_no_se_toca():
    assert redactar_texto("key=abc") == "key=abc"


def test_texto_sin_sensibles_queda_igual():
    texto = "El resultado es 42. Fin del análisis ñandú."
    assert redactar_texto(texto) == texto


def test_idempotente():
    texto = (
        r"C:\Users\ejemplo\x /home/ejemplo/y usuario@example.com sk-abcdefghijklmnop1234 "
        "ghp_abcdefghijklmnopqrstuvwx1234 Bearer abcdef1234567890XYZ token=0123456789abcdef0123456789"
    )
    una_vez = redactar_texto(texto)
    assert redactar_texto(una_vez) == una_vez
    for original in ("ejemplo", "usuario@example.com", "sk-abc", "ghp_abc", "abcdef1234567890XYZ"):
        assert original not in una_vez


@pytest.mark.parametrize("valor", [None, 5, 3.2, True, ["a"], {"a": "b"}, b"bytes"])
def test_no_str_intactos(valor):
    assert redactar_texto(valor) == valor
    assert type(redactar_texto(valor)) is type(valor)


def test_nunca_lanza_con_texto_raro():
    assert isinstance(redactar_texto("\x00\ud800 ñ 日本語 \r\n"), str)
    assert redactar_texto("") == ""


# --- aplicación en storage (R6) ---------------------------------------------------


def _resultado(stdout: str, detail: str) -> EvalResult:
    return EvalResult(
        run_id="r",
        scenario_id="s1",
        target=EvalTarget(provider_id="fake"),
        exit_code=0,
        ok=True,
        availability_error=None,
        duration_s=0.1,
        stdout_excerpt=stdout,
        score=ScoreResult(passed=True, score=1.0, detail=detail),
        harmessi_version="0.0.0",
        timestamp_utc="2026-01-01T00:00:00+00:00",
    )


def test_save_run_redacta_stdout_excerpt_y_detail(tmp_path):
    raiz = tmp_path / "evals con espacios ñ"
    resultado = _resultado(
        r"salida en C:\Users\ejemplo\x con usuario@example.com",
        "detail con sk-abcdefghijklmnop1234 y /home/ejemplo/x",
    )
    storage.save_run("r", [resultado], EvalTarget(provider_id="fake"), root=raiz)
    texto_crudo = (raiz / "r" / "result.json").read_text(encoding="utf-8")
    for secreto in ("ejemplo", "usuario@example.com", "sk-abcdefghijklmnop1234"):
        assert secreto not in texto_crudo
    guardado = storage.load_run("r", root=raiz)["resultados"][0]
    assert MARCADOR_RUTA in guardado["stdout_excerpt"]
    assert MARCADOR_EMAIL in guardado["stdout_excerpt"]
    assert MARCADOR_TOKEN in guardado["score"]["detail"]


def test_save_run_no_corta_token_al_truncar_detail(tmp_path):
    token = "ghp_" + "a" * 40
    detail = ("palabra " * 36) + token
    storage.save_run("r", [_resultado("", detail)], EvalTarget(provider_id="fake"), root=tmp_path)
    guardado = storage.load_run("r", root=tmp_path)["resultados"][0]["score"]["detail"]
    assert "ghp_" not in guardado
    assert "aaaa" not in guardado


def test_save_run_acepta_resultados_dict_y_redacta(tmp_path):
    """Un resume combina dicts cargados con `load_run`: se persisten igual."""
    dict_previo = {
        "run_id": "r",
        "scenario_id": "s1",
        "ok": True,
        "stdout_excerpt": "mail usuario@example.com",
        "score": {"passed": True, "score": 1.0, "detail": "ok"},
    }
    storage.save_run("r", [dict_previo], EvalTarget(provider_id="fake"), root=tmp_path)
    guardado = storage.load_run("r", root=tmp_path)["resultados"][0]
    assert guardado["stdout_excerpt"] == "mail " + MARCADOR_EMAIL
    assert guardado["scenario_id"] == "s1"
    assert dict_previo["stdout_excerpt"] == "mail usuario@example.com"  # el original no se muta

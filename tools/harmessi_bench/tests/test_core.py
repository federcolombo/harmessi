"""Tests de `tools/harmessi_bench/core.py`: scorers puros y `aplicar_scorer`."""
from __future__ import annotations

from tools.harmessi_bench.core import (
    aplicar_scorer,
    scorer_contains,
    scorer_exact,
    scorer_regex,
)


def test_scorer_contains_todos_presentes():
    resultado = scorer_contains("el resultado es OK y listo", {"valores": ["OK", "listo"]})
    assert resultado.passed is True
    assert resultado.score == 1.0


def test_scorer_contains_ninguno_presente():
    resultado = scorer_contains("hola mundo", {"valores": ["OK", "chau"]})
    assert resultado.passed is False
    assert resultado.score == 0.0


def test_scorer_contains_parcial():
    resultado = scorer_contains("hola OK", {"valores": ["OK", "chau"]})
    assert resultado.passed is False
    assert resultado.score == 0.5


def test_scorer_contains_valores_no_es_lista_no_crashea():
    resultado = scorer_contains("hola mundo", {"valores": "hola"})
    assert resultado.passed is False
    assert resultado.score == 0.0
    assert "debe ser una lista" in resultado.detail


def test_scorer_regex_coincide():
    resultado = scorer_regex("el color es rojo", {"patron": "(?i)(rojo|azul)"})
    assert resultado.passed is True
    assert resultado.score == 1.0


def test_scorer_regex_no_coincide():
    resultado = scorer_regex("el color es verde", {"patron": "(?i)(rojo|azul)"})
    assert resultado.passed is False
    assert resultado.score == 0.0


def test_scorer_regex_patron_invalido_no_crashea():
    resultado = scorer_regex("cualquier texto", {"patron": "(rojo"})
    assert resultado.passed is False
    assert resultado.score == 0.0
    assert "patron invalido" in resultado.detail


def test_scorer_exact_coincide_con_espacios():
    resultado = scorer_exact("  OK\n", {"valor": "OK"})
    assert resultado.passed is True


def test_scorer_exact_no_coincide():
    resultado = scorer_exact("OK, listo", {"valor": "OK"})
    assert resultado.passed is False


def test_aplicar_scorer_resuelve_por_tipo():
    resultado = aplicar_scorer("OK", {"tipo": "exact", "valor": "OK"})
    assert resultado.passed is True


def test_aplicar_scorer_tipo_desconocido_no_lanza():
    resultado = aplicar_scorer("cualquier texto", {"tipo": "tipo-inexistente"})
    assert resultado.passed is False
    assert resultado.score == 0.0
    assert "desconocido" in resultado.detail


def test_aplicar_scorer_sin_tipo_no_lanza():
    resultado = aplicar_scorer("texto", {})
    assert resultado.passed is False

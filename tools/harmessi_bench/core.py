"""Tipos y scoring determinista de `harmessi_bench` (v0.5 Change 1,
`harmessi-bench`).

Este módulo es **core** en el sentido de `ARCHITECTURE.md` §1: no importa
`subprocess`, no conoce el vocabulario de flags de ningún proveedor concreto.
Este módulo no importa nada de `tools.providers` -- es puramente stdlib. El
vínculo con el contrato neutral de invocación de Change 0
(`tools.providers.core`) lo hace `runner.py`, no acá.

Scoring determinista (`contains`/`regex`/`exact`), no LLM-as-judge -- ver
`design.md` para la justificación y sus límites (proxy superficial de texto,
no medición semántica real de calidad).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional


@dataclass
class Scenario:
    """Un escenario de eval: un prompt con una expectativa de output
    verificable de forma determinista (`expected`, ver `scenarios.py` para
    la forma exacta del JSON del que se cargan)."""

    scenario_id: str
    prompt: str
    category: str
    tags: list = field(default_factory=list)
    expected: dict = field(default_factory=dict)


@dataclass
class ScoreResult:
    """Resultado de aplicar un scorer a un texto: `passed` es la decisión
    binaria, `score` una fracción en `[0, 1]` (no siempre proporcional a
    `passed`, ver `scorer_contains`), `detail` explica el porqué."""

    passed: bool
    score: float
    detail: str


@dataclass
class EvalTarget:
    """Configuración del target contra el que se corre un escenario:
    provider registrado (ver `tools.providers.PROVIDER_REGISTRY`) + model/
    effort opcionales."""

    provider_id: str
    model: Optional[str] = None
    effort: Optional[str] = None


@dataclass
class EvalResult:
    """Resultado de correr un escenario contra un target. `availability_error`
    distingue explícitamente "el proveedor no respondió" (ver `runner.py`)
    de "el proveedor respondió mal" (reflejado en `score`) -- crítico para
    que Change 2/3 puedan usar `harmessi-bench` como evidencia sin confundir
    ambos casos."""

    run_id: str
    scenario_id: str
    target: EvalTarget
    exit_code: int
    ok: bool
    availability_error: Optional[str]
    duration_s: float
    stdout_excerpt: str
    score: ScoreResult
    harmessi_version: str
    timestamp_utc: str


def scorer_contains(texto: str, params: dict) -> ScoreResult:
    """`passed=True` si TODOS los `params["valores"]` aparecen como
    substring de `texto`; `score` es la fracción de valores encontrados
    (no binario, útil para diagnóstico aunque `passed` sea `False`)."""
    valores = params.get("valores", [])
    if not valores:
        return ScoreResult(passed=False, score=0.0, detail="scorer_contains: 'valores' vacío o ausente")
    if not isinstance(valores, (list, tuple)):
        return ScoreResult(
            passed=False,
            score=0.0,
            detail=f"scorer_contains: 'valores' debe ser una lista, no {type(valores).__name__}",
        )
    valores = [valor if isinstance(valor, str) else str(valor) for valor in valores]
    encontrados = [valor for valor in valores if valor in texto]
    fraccion = len(encontrados) / len(valores)
    passed = len(encontrados) == len(valores)
    detail = f"{len(encontrados)}/{len(valores)} valores encontrados: {encontrados!r}"
    return ScoreResult(passed=passed, score=fraccion, detail=detail)


def scorer_regex(texto: str, params: dict) -> ScoreResult:
    """`passed=True` si `re.search(params["patron"], texto)` no es `None`."""
    patron = params.get("patron", "")
    if not patron:
        return ScoreResult(passed=False, score=0.0, detail="scorer_regex: 'patron' vacío o ausente")
    try:
        coincide = re.search(patron, texto) is not None
    except re.error as exc:
        return ScoreResult(
            passed=False, score=0.0, detail=f"scorer_regex: patron invalido {patron!r}: {exc}"
        )
    detail = f"patron={patron!r} {'coincide' if coincide else 'no coincide'} contra el texto"
    return ScoreResult(passed=coincide, score=1.0 if coincide else 0.0, detail=detail)


def scorer_exact(texto: str, params: dict) -> ScoreResult:
    """`passed=True` si `texto.strip() == params["valor"]` (igualdad exacta
    tras recortar espacios/saltos de línea del borde, no del contenido)."""
    valor = params.get("valor", None)
    if valor is None:
        return ScoreResult(passed=False, score=0.0, detail="scorer_exact: 'valor' ausente")
    coincide = texto.strip() == valor
    detail = f"esperado={valor!r} obtenido={texto.strip()!r}"
    return ScoreResult(passed=coincide, score=1.0 if coincide else 0.0, detail=detail)


SCORERS: Dict[str, Callable[[str, dict], ScoreResult]] = {
    "contains": scorer_contains,
    "regex": scorer_regex,
    "exact": scorer_exact,
}


def aplicar_scorer(texto: str, expected: dict) -> ScoreResult:
    """Resuelve el scorer por `expected["tipo"]` y lo aplica. Nunca lanza
    `KeyError` sin manejar ante un tipo desconocido: devuelve un
    `ScoreResult` fallido con el detalle del problema, no una excepción --
    fail-closed en el sentido de "no pasa por accidente", no en el sentido
    de crashear. Nota: `expected` debe ser un `dict` (contrato de
    `Scenario.expected`); si no lo es (p. ej. `None` por un escenario mal
    formado más arriba en la cadena), esta función SÍ deja propagar el
    `AttributeError` -- es responsabilidad de `run_scenario_set` capturar
    ese caso como error interno del escenario, no de silenciarlo acá."""
    tipo = expected.get("tipo")
    scorer = SCORERS.get(tipo) if tipo is not None else None
    if scorer is None:
        return ScoreResult(passed=False, score=0.0, detail=f"tipo de scorer desconocido: {tipo!r}")
    return scorer(texto, expected)

"""Paquete `harmessi_bench`: framework mínimo de evals de Harmessi (v0.5
Change 1, `harmessi-bench`). Separa correctness determinista (tests) de
calidad de comportamiento agentic (evals) -- ver `docs/roadmap/v0.5.md`
"Change 1 -- harmessi-bench" y `ARCHITECTURE.md` §2.1.

Reusa el contrato neutral de `tools/providers/core.py` (Change 0) para
invocar un target; no lo modifica ni lo duplica.
"""
from __future__ import annotations

from tools.harmessi_bench.core import (
    SCORERS,
    EvalResult,
    EvalTarget,
    Scenario,
    ScoreResult,
    aplicar_scorer,
    scorer_contains,
    scorer_exact,
    scorer_regex,
)

__all__ = [
    "SCORERS",
    "EvalResult",
    "EvalTarget",
    "Scenario",
    "ScoreResult",
    "aplicar_scorer",
    "scorer_contains",
    "scorer_exact",
    "scorer_regex",
]

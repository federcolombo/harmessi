"""Carga de escenarios de eval desde JSON (v0.5 Change 1, `harmessi-bench`).

Falla cerrado ante un escenario mal formado: `load_scenarios` nunca silencia
un escenario incompleto ni lo salta -- lanza `ValueError` citando el índice
del escenario problemático, para que el error se note en el momento de
cargar el set, no como un `KeyError` opaco más adelante en el runner.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import List

from tools.harmessi_bench.core import Scenario

_CAMPOS_REQUERIDOS = ("scenario_id", "prompt", "expected")


def load_scenarios(path: Path) -> List[Scenario]:
    """Lee un JSON con forma `{"escenarios": [...]}` y devuelve una lista de
    `Scenario`. Cada entrada debe tener al menos `scenario_id`/`prompt`/
    `expected`; `category`/`tags` son opcionales (default `""`/`[]`)."""
    contenido = json.loads(Path(path).read_text(encoding="utf-8"))
    escenarios_crudos = contenido.get("escenarios", [])

    escenarios: List[Scenario] = []
    for indice, crudo in enumerate(escenarios_crudos):
        faltantes = [campo for campo in _CAMPOS_REQUERIDOS if campo not in crudo]
        if faltantes:
            raise ValueError(
                f"escenario en el índice {indice} de {path} le faltan campos requeridos: {faltantes!r}"
            )
        escenarios.append(
            Scenario(
                scenario_id=crudo["scenario_id"],
                prompt=crudo["prompt"],
                category=crudo.get("category", ""),
                tags=list(crudo.get("tags", [])),
                expected=crudo["expected"],
            )
        )
    return escenarios

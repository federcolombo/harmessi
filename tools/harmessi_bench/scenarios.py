"""Carga de escenarios de eval desde JSON (v0.5 Change 1, `harmessi-bench`;
extendido en v0.13 Change 1).

Falla cerrado ante un escenario mal formado: `load_scenarios` nunca silencia
un escenario incompleto ni lo salta -- lanza `ValueError` citando el índice
del escenario problemático, para que el error se note en el momento de
cargar el set, no como un `KeyError` opaco más adelante en el runner.

v0.13: el archivo puede declarar `case_contract_version` (ausente => 0,
legado); se rechazan ids duplicados y los casos que declaran una
`surface_under_test` que no sea Optimizable (boundary de superficies).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import List, Tuple

from tools.harmessi_bench.core import CASE_CONTRACT_VERSION, SCORERS, Scenario

_CAMPOS_REQUERIDOS = ("scenario_id", "prompt", "expected")

# Versiones del contrato de casos que esta versión sabe leer (0 = legado).
_VERSIONES_SOPORTADAS = (0, CASE_CONTRACT_VERSION)


def _es_entero_puro(valor) -> bool:
    """`True` solo para `int` que no sea `bool` (en Python `True` es un int)."""
    return isinstance(valor, int) and not isinstance(valor, bool)


def _validar_superficie(indice: int, scenario_id, superficie, path) -> None:
    """Boundary de superficies: la superficie observada por un caso debe ser
    Optimizable. Import perezoso para no acoplar `scenarios` a `dsguard` en
    tiempo de import. No promueve ni escribe nada: solo valida."""
    from tools.dsguard.skill_contract import SUPERFICIE_OPTIMIZABLE, superficie_de_ruta

    clasificada = superficie_de_ruta(superficie)
    if clasificada != SUPERFICIE_OPTIMIZABLE:
        raise ValueError(
            f"escenario {scenario_id!r} (índice {indice} de {path}): surface_under_test="
            f"{superficie!r} es '{clasificada}'; solo se admiten superficies 'optimizable'"
        )


def load_scenarios_con_version(path: Path) -> Tuple[int, List[Scenario]]:
    """Como `load_scenarios` pero devuelve también la versión del contrato de
    casos del archivo (0 si es legado). Fail-closed ante versión desconocida,
    no entera o bool, ids duplicados o superficie no Optimizable."""
    contenido = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    path = Path(path).name  # los mensajes citan solo el nombre de archivo, no la ruta completa
    if not isinstance(contenido, dict):
        raise ValueError(f"{path}: el archivo de escenarios debe ser un objeto JSON")

    version = contenido.get("case_contract_version", 0)
    if not _es_entero_puro(version) or version not in _VERSIONES_SOPORTADAS:
        raise ValueError(
            f"{path}: case_contract_version={version!r} no soportada "
            f"(soportadas: {list(_VERSIONES_SOPORTADAS)})"
        )

    escenarios_crudos = contenido.get("escenarios", [])
    if not isinstance(escenarios_crudos, list):
        raise ValueError(f"{path}: 'escenarios' debe ser una lista")

    escenarios: List[Scenario] = []
    vistos = set()
    for indice, crudo in enumerate(escenarios_crudos):
        if not isinstance(crudo, dict):
            raise ValueError(f"escenario en el índice {indice} de {path} debe ser un objeto JSON")
        faltantes = [campo for campo in _CAMPOS_REQUERIDOS if campo not in crudo]
        if faltantes:
            raise ValueError(
                f"escenario en el índice {indice} de {path} le faltan campos requeridos: {faltantes!r}"
            )
        scenario_id = crudo["scenario_id"]
        if not isinstance(scenario_id, str) or not scenario_id.strip():
            raise ValueError(f"escenario en el índice {indice} de {path}: scenario_id debe ser un string no vacío")
        if not isinstance(crudo["prompt"], str) or not crudo["prompt"].strip():
            raise ValueError(f"escenario {scenario_id!r} (índice {indice}): prompt debe ser un string no vacío")
        expected = crudo["expected"]
        if not isinstance(expected, dict) or expected.get("tipo") not in SCORERS:
            raise ValueError(
                f"escenario {scenario_id!r} (índice {indice}): expected debe ser un objeto con "
                f"'tipo' en {sorted(SCORERS)}"
            )
        if scenario_id in vistos:
            raise ValueError(f"scenario_id duplicado {scenario_id!r} (índice {indice} de {path})")
        vistos.add(scenario_id)

        fixtures = crudo.get("fixtures", {})
        if not isinstance(fixtures, dict):
            raise ValueError(f"escenario {scenario_id!r}: 'fixtures' debe ser un objeto JSON")
        superficie = crudo.get("surface_under_test")
        if superficie is not None:
            if not isinstance(superficie, str):
                raise ValueError(f"escenario {scenario_id!r}: 'surface_under_test' debe ser un string")
            _validar_superficie(indice, scenario_id, superficie, path)

        escenarios.append(
            Scenario(
                scenario_id=scenario_id,
                prompt=crudo["prompt"],
                category=crudo.get("category", ""),
                tags=list(crudo.get("tags", [])),
                expected=crudo["expected"],
                fixtures=fixtures,
                surface_under_test=superficie,
            )
        )
    return version, escenarios


def load_scenarios(path: Path) -> List[Scenario]:
    """Lee un JSON con forma `{"escenarios": [...]}` y devuelve una lista de
    `Scenario`. Cada entrada debe tener al menos `scenario_id`/`prompt`/
    `expected`; `category`/`tags`/`fixtures`/`surface_under_test` son
    opcionales (default `""`/`[]`/`{}`/`None`)."""
    return load_scenarios_con_version(path)[1]

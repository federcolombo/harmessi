"""Carga/validación de `RoutingPolicy` desde disco (v0.5 Change 2,
`provider-routing`).

`.harmessi/routing.json` es una política opcional: si no existe, no hay
routing declarado -- comportamiento legítimo, nunca inferido por
heurística, mismo criterio editorial que `.harmessi/scientific-policy.json`
documentado en `README.md`. Si existe pero está mal formado, falla cerrado
(mismo patrón que `tools/harmessi_bench/scenarios.py::load_scenarios`):
`raise ValueError` citando el índice de la regla problemática, nunca un
`KeyError` opaco más adelante.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from tools.routing.core import RoutingPolicy, RoutingRule

DEFAULT_POLICY_PATH = Path(".harmessi/routing.json")

_CAMPOS_REQUERIDOS = ("role", "provider_id", "reason")


def _construir_regla(crudo: dict, etiqueta: str) -> RoutingRule:
    """Construye un `RoutingRule` desde un `dict` crudo, validando que
    `role`/`provider_id`/`reason` estén presentes y no vacíos. `etiqueta`
    identifica la regla en el mensaje de error (índice de `rules`, o
    `"default"`)."""
    if not isinstance(crudo, dict):
        raise ValueError(
            f"regla {etiqueta} de routing.json debe ser un objeto JSON, "
            f"no {type(crudo).__name__}"
        )
    faltantes = [
        campo
        for campo in _CAMPOS_REQUERIDOS
        if not crudo.get(campo)
    ]
    if faltantes:
        raise ValueError(
            f"regla {etiqueta} de routing.json le faltan campos requeridos "
            f"(no vacíos): {faltantes!r}"
        )
    return RoutingRule(
        role=crudo["role"],
        provider_id=crudo["provider_id"],
        reason=crudo["reason"],
        task_type=crudo.get("task_type", "*"),
        model=crudo.get("model"),
        effort=crudo.get("effort"),
    )


def load_policy(path: Optional[Path] = None) -> RoutingPolicy:
    """Carga una `RoutingPolicy` desde `path` (o `DEFAULT_POLICY_PATH` si
    `path is None`).

    Si el archivo resuelto no existe, devuelve `RoutingPolicy(rules=[],
    default=None)` sin levantar -- "sin política declarada" es una
    configuración legítima, nunca inferida por heurística.

    Si el archivo existe, parsea JSON con forma `{"rules": [...], "default":
    {...} | null}`. Validación fail-closed: cada regla (y `default` si no es
    `null`) debe tener `role`/`provider_id`/`reason` no vacíos -- si falta
    alguno, `raise ValueError` citando el índice de la regla problemática
    (o `"default"`)."""
    ruta = Path(path) if path is not None else DEFAULT_POLICY_PATH
    if not ruta.exists():
        return RoutingPolicy(rules=[], default=None)

    contenido = json.loads(ruta.read_text(encoding="utf-8"))

    reglas_crudas = contenido.get("rules", [])
    reglas = [
        _construir_regla(crudo, etiqueta=f"en el índice {indice} de {ruta}")
        for indice, crudo in enumerate(reglas_crudas)
    ]

    default_crudo = contenido.get("default")
    default_regla = (
        _construir_regla(default_crudo, etiqueta=f"'default' de {ruta}")
        if default_crudo is not None
        else None
    )

    return RoutingPolicy(rules=reglas, default=default_regla)

"""Tests de paridad de routing entre los 4 provider_id reales (v0.5
Change 4, `cross-provider-hardening`). Confirma que `resolve()` trata a
`claude_code`/`codex`/`gemini`/`grok` de forma idéntica -- el matching es
puramente sobre `role`/`task_type`, nunca sobre el valor de `provider_id`
(ver también `tools/tests/test_v05_core_neutrality.py`, que verifica por AST
que `tools/routing/core.py` no contiene el literal 'claude')."""
from __future__ import annotations

from pathlib import Path

import pytest

from tools.routing.core import RoutingPolicy, RoutingRule, resolve

_PROVIDER_IDS_REALES = ["claude_code", "codex", "gemini", "grok"]

_ROUTING_CORE_PATH = Path(__file__).resolve().parents[1] / "core.py"


def _policy_con_una_regla_por_provider() -> RoutingPolicy:
    """Una `RoutingRule` por cada uno de los 4 provider_id reales, mismo
    `role`, `task_type` distinto y explícito (sin comodín) para cada una --
    así el desempate de `resolve()` es exclusivamente por `task_type`, nunca
    por `provider_id`."""
    reglas = [
        RoutingRule(
            role="writer",
            provider_id=provider_id,
            task_type=f"tarea_{provider_id}",
            reason=f"regla de paridad para {provider_id}",
        )
        for provider_id in _PROVIDER_IDS_REALES
    ]
    return RoutingPolicy(rules=reglas, default=None)


@pytest.mark.parametrize("provider_id", _PROVIDER_IDS_REALES)
def test_resolve_trata_a_los_4_provider_id_de_forma_identica(provider_id):
    """Cada uno de los 4 provider_id reales, resuelto por su propio
    task_type: mismo resultado estructural para los 4 (matched=True,
    rule_source='regla_explicita'), solo cambia el provider_id/task_type
    esperado -- ningún proveedor recibe trato especial en el desempate."""
    policy = _policy_con_una_regla_por_provider()

    decision = resolve(policy, role="writer", task_type=f"tarea_{provider_id}")

    assert decision.matched is True
    assert decision.rule_source == "regla_explicita"
    assert decision.provider_id == provider_id
    assert decision.role == "writer"
    assert decision.task_type == f"tarea_{provider_id}"


def test_resolve_no_matchea_provider_id_de_otro_task_type():
    """Confirma que el desempate es realmente por task_type y no por orden
    de declaración o por provider_id: pedir el task_type de 'codex' nunca
    devuelve el provider_id de 'claude_code' (primero en la lista) ni
    ningún otro que no sea el correspondiente."""
    policy = _policy_con_una_regla_por_provider()

    decision = resolve(policy, role="writer", task_type="tarea_codex")

    assert decision.provider_id == "codex"
    assert decision.provider_id != "claude_code"


def test_routing_core_no_compara_provider_id_contra_ninguno_de_los_4_reales():
    """Verificación de lectura explícita sobre `tools/routing/core.py`: no
    debe contener el literal de ninguno de los 4 provider_id reales -- la
    lógica de `resolve()` solo debe comparar `role`/`task_type`."""
    codigo = _ROUTING_CORE_PATH.read_text(encoding="utf-8")
    violaciones = [
        pid for pid in _PROVIDER_IDS_REALES if f'"{pid}"' in codigo or f"'{pid}'" in codigo
    ]
    assert violaciones == [], (
        f"tools/routing/core.py contiene el/los literal(es) {violaciones!r} -- "
        "resolve() no debe reconocer ningún provider_id por su nombre"
    )


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__]))

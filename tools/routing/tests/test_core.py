"""Tests de `tools.routing.core.resolve` (v0.5 Change 2,
`provider-routing`). Deterministas, sin invocar ningún proveedor real --
`RoutingPolicy`/`RoutingRule` se construyen a mano."""
from __future__ import annotations

import unittest

from tools.routing.core import RoutingPolicy, RoutingRule, resolve


class TestResolve(unittest.TestCase):
    def test_task_type_exacto_gana_sobre_comodin(self):
        regla_comodin = RoutingRule(
            role="writer", task_type="*", provider_id="claude_code", reason="comodin"
        )
        regla_exacta = RoutingRule(
            role="writer",
            task_type="feature_engineering",
            provider_id="codex",
            reason="exacta",
        )
        policy = RoutingPolicy(rules=[regla_comodin, regla_exacta])

        decision = resolve(policy, role="writer", task_type="feature_engineering")

        self.assertTrue(decision.matched)
        self.assertEqual(decision.rule_source, "regla_explicita")
        self.assertEqual(decision.provider_id, "codex")
        self.assertEqual(decision.reason, "exacta")

    def test_sin_regla_pero_con_default_usa_default(self):
        default = RoutingRule(
            role="cualquiera", provider_id="claude_code", reason="default global"
        )
        policy = RoutingPolicy(rules=[], default=default)

        decision = resolve(policy, role="metodologo", task_type="revision")

        self.assertTrue(decision.matched)
        self.assertEqual(decision.rule_source, "default")
        self.assertEqual(decision.provider_id, "claude_code")
        self.assertEqual(decision.reason, "default global")

    def test_sin_regla_y_sin_default_matched_false(self):
        policy = RoutingPolicy(rules=[], default=None)

        decision = resolve(policy, role="metodologo", task_type="revision")

        self.assertFalse(decision.matched)
        self.assertEqual(decision.rule_source, "sin_regla")
        self.assertIsNone(decision.provider_id)
        self.assertIsNone(decision.model)
        self.assertIsNone(decision.effort)
        self.assertIn("metodologo", decision.reason)
        self.assertIn("revision", decision.reason)
        self.assertIsNone(decision.provider_available)

    def test_available_providers_marca_no_disponible_sin_cambiar_provider(self):
        regla = RoutingRule(role="writer", provider_id="codex", reason="regla codex")
        policy = RoutingPolicy(rules=[regla])

        decision = resolve(
            policy,
            role="writer",
            task_type="cualquiera",
            available_providers={"claude_code"},
        )

        self.assertTrue(decision.matched)
        self.assertEqual(decision.provider_id, "codex")
        self.assertFalse(decision.provider_available)

    def test_provider_available_es_informativo_y_no_altera_la_decision(self):
        # R9: la disponibilidad solo se informa; el resto de la decision es identico.
        regla = RoutingRule(
            role="writer", provider_id="codex", model="m", effort="high", reason="regla codex"
        )
        policy = RoutingPolicy(rules=[regla])

        sin_info = resolve(policy, role="writer", task_type="t")
        disponible = resolve(policy, role="writer", task_type="t", available_providers={"codex"})
        no_disponible = resolve(policy, role="writer", task_type="t", available_providers=set())

        self.assertIsNone(sin_info.provider_available)
        self.assertTrue(disponible.provider_available)
        self.assertFalse(no_disponible.provider_available)
        for decision in (disponible, no_disponible):
            self.assertEqual(decision.provider_id, sin_info.provider_id)
            self.assertEqual(decision.model, sin_info.model)
            self.assertEqual(decision.effort, sin_info.effort)
            self.assertEqual(decision.reason, sin_info.reason)
            self.assertEqual(decision.rule_source, sin_info.rule_source)
            self.assertEqual(decision.matched, sin_info.matched)

    def test_sin_available_providers_provider_available_es_none(self):
        regla = RoutingRule(role="writer", provider_id="codex", reason="regla codex")
        policy = RoutingPolicy(rules=[regla])

        decision = resolve(policy, role="writer", task_type="cualquiera")

        self.assertIsNone(decision.provider_available)

    def test_empate_mismo_rol_y_task_type_exacto_gana_la_primera(self):
        primera = RoutingRule(
            role="writer",
            task_type="feature_engineering",
            provider_id="claude_code",
            reason="primera declarada",
        )
        segunda = RoutingRule(
            role="writer",
            task_type="feature_engineering",
            provider_id="codex",
            reason="segunda declarada",
        )
        policy = RoutingPolicy(rules=[primera, segunda])

        decision = resolve(policy, role="writer", task_type="feature_engineering")

        self.assertEqual(decision.provider_id, "claude_code")
        self.assertEqual(decision.reason, "primera declarada")

    def test_regla_con_fallback_chain_se_propaga_en_decision(self):
        regla = RoutingRule(
            role="writer",
            provider_id="claude_code",
            reason="con fallback",
            fallback_chain=["codex", "gemini"],
        )
        policy = RoutingPolicy(rules=[regla])

        decision = resolve(policy, role="writer", task_type="cualquiera")

        self.assertEqual(decision.fallback_chain, ["codex", "gemini"])

    def test_regla_sin_fallback_chain_explicito_decision_lista_vacia(self):
        regla = RoutingRule(role="writer", provider_id="claude_code", reason="sin fallback")
        policy = RoutingPolicy(rules=[regla])

        decision = resolve(policy, role="writer", task_type="cualquiera")

        self.assertEqual(decision.fallback_chain, [])


if __name__ == "__main__":
    unittest.main()

"""Tests de `tools.datacontracts.evolution` (v0.7 Change 4,
`20260922-quality-integration-and-cli`).

Un caso por categoría de R7 de `spec.md`, con y sin `CompatibilityPolicy`,
determinismo (mismo input dos veces -> misma lista) y ausencia total de I/O
(constructores sin ningún argumento de ruta/archivo)."""
from __future__ import annotations

import unittest

from tools.dsguard import checks
from tools.datacontracts import core
from tools.datacontracts import evolution


def _version(v: str = "1.0.0") -> core.ContractVersion:
    return core.ContractVersion(version=v)


def _contrato(fields: tuple, constraints: tuple = (), business_rules: tuple = (), keys: tuple = (), **kwargs) -> core.DataContract:
    return core.DataContract(
        contract_id="c1",
        version=_version(),
        dataset_role="raw_table",
        fields=fields,
        constraints=constraints,
        business_rules=business_rules,
        keys=keys,
        **kwargs,
    )


def _policy(**overrides) -> core.CompatibilityPolicy:
    base = dict(
        policy_id="p1",
        on_removed_field="block",
        on_required_field_added="block",
        on_type_change="block",
        on_constraint_tightening="warn",
        on_constraint_loosening="allow",
        on_unknown_change="warn",
    )
    base.update(overrides)
    return core.CompatibilityPolicy(**base)


class TestAusenciaDePolicy(unittest.TestCase):
    def test_sin_policy_todo_status_na(self):
        old = _contrato((core.ContractField(name="a", type_family="string"),))
        new = _contrato(
            (
                core.ContractField(name="a", type_family="string"),
                core.ContractField(name="b", type_family="string", required=False),
            )
        )
        resultados = evolution.classify_contract_change(old, new)
        self.assertTrue(resultados)
        for r in resultados:
            self.assertEqual(r.status, checks.STATUS_NA)


class TestAdditiveCompatible(unittest.TestCase):
    def test_campo_nuevo_opcional_es_additive(self):
        old = _contrato((core.ContractField(name="a", type_family="string"),))
        new = _contrato(
            (
                core.ContractField(name="a", type_family="string"),
                core.ContractField(name="b", type_family="integer", required=False),
            )
        )
        resultados = evolution.classify_contract_change(old, new)
        por_codigo = {r.code: r for r in resultados}
        self.assertIn(evolution.CODE_ADDITIVE_COMPATIBLE, por_codigo)
        self.assertEqual(por_codigo[evolution.CODE_ADDITIVE_COMPATIBLE].subject, "b")

    def test_additive_siempre_pass_con_policy(self):
        old = _contrato((core.ContractField(name="a", type_family="string"),))
        new = _contrato(
            (
                core.ContractField(name="a", type_family="string"),
                core.ContractField(name="b", type_family="integer", required=False),
            )
        )
        policy = _policy()
        resultados = evolution.classify_contract_change(old, new, policy)
        por_codigo = {r.code: r for r in resultados}
        self.assertEqual(por_codigo[evolution.CODE_ADDITIVE_COMPATIBLE].status, checks.STATUS_PASS)


class TestRemoval(unittest.TestCase):
    def test_campo_eliminado_es_removal(self):
        old = _contrato(
            (
                core.ContractField(name="a", type_family="string"),
                core.ContractField(name="b", type_family="integer", required=False),
            )
        )
        new = _contrato((core.ContractField(name="a", type_family="string"),))
        resultados = evolution.classify_contract_change(old, new)
        por_codigo = {r.code: r for r in resultados}
        self.assertIn(evolution.CODE_REMOVAL, por_codigo)
        self.assertEqual(por_codigo[evolution.CODE_REMOVAL].subject, "b")

    def test_removal_mapea_block_a_fail_con_policy(self):
        old = _contrato(
            (
                core.ContractField(name="a", type_family="string"),
                core.ContractField(name="b", type_family="integer", required=False),
            )
        )
        new = _contrato((core.ContractField(name="a", type_family="string"),))
        policy = _policy(on_removed_field="block")
        resultados = evolution.classify_contract_change(old, new, policy)
        por_codigo = {r.code: r for r in resultados}
        self.assertEqual(por_codigo[evolution.CODE_REMOVAL].status, checks.STATUS_FAIL)


class TestRequiredFieldAddition(unittest.TestCase):
    def test_campo_nuevo_requerido(self):
        old = _contrato((core.ContractField(name="a", type_family="string"),))
        new = _contrato(
            (
                core.ContractField(name="a", type_family="string"),
                core.ContractField(name="b", type_family="integer", required=True),
            )
        )
        resultados = evolution.classify_contract_change(old, new)
        por_codigo = {r.code: r for r in resultados}
        self.assertIn(evolution.CODE_REQUIRED_FIELD_ADDITION, por_codigo)
        self.assertEqual(por_codigo[evolution.CODE_REQUIRED_FIELD_ADDITION].subject, "b")

    def test_flip_opcional_a_requerido_mismo_codigo(self):
        old = _contrato((core.ContractField(name="a", type_family="string", required=False),))
        new = _contrato((core.ContractField(name="a", type_family="string", required=True),))
        resultados = evolution.classify_contract_change(old, new)
        codigos = [r.code for r in resultados]
        self.assertEqual(codigos, [evolution.CODE_REQUIRED_FIELD_ADDITION])

    def test_warn_con_policy(self):
        old = _contrato((core.ContractField(name="a", type_family="string"),))
        new = _contrato(
            (
                core.ContractField(name="a", type_family="string"),
                core.ContractField(name="b", type_family="integer", required=True),
            )
        )
        policy = _policy(on_required_field_added="warn")
        resultados = evolution.classify_contract_change(old, new, policy)
        por_codigo = {r.code: r for r in resultados}
        self.assertEqual(por_codigo[evolution.CODE_REQUIRED_FIELD_ADDITION].status, checks.STATUS_WARN)


class TestTypeChange(unittest.TestCase):
    def test_type_family_distinta_un_solo_finding_con_todas_las_dimensiones(self):
        old = _contrato((core.ContractField(name="a", type_family="string", required=True, nullable=True),))
        new = _contrato((core.ContractField(name="a", type_family="integer", required=False, nullable=False),))
        resultados = evolution.classify_contract_change(old, new)
        codigos = [r.code for r in resultados]
        self.assertEqual(codigos, [evolution.CODE_TYPE_CHANGE])
        mensaje = resultados[0].message
        self.assertIn("type_family", mensaje)
        self.assertIn("required", mensaje)
        self.assertIn("nullable", mensaje)

    def test_allow_con_policy(self):
        old = _contrato((core.ContractField(name="a", type_family="string"),))
        new = _contrato((core.ContractField(name="a", type_family="integer"),))
        policy = _policy(on_type_change="allow")
        resultados = evolution.classify_contract_change(old, new, policy)
        self.assertEqual(resultados[0].status, checks.STATUS_PASS)


class TestConstraintTighteningLoosening(unittest.TestCase):
    def _contrato_con_constraint(self, valor: int) -> core.DataContract:
        campo = core.ContractField(name="a", type_family="integer")
        constraint = core.Constraint(
            constraint_id="c-min", constraint_type="min_value", field="a", params={"value": valor}
        )
        return _contrato((campo,), (constraint,))

    def test_min_value_sube_es_tightening(self):
        old = self._contrato_con_constraint(0)
        new = self._contrato_con_constraint(10)
        resultados = evolution.classify_contract_change(old, new)
        codigos = [r.code for r in resultados]
        self.assertEqual(codigos, [evolution.CODE_CONSTRAINT_TIGHTENING])

    def test_min_value_baja_es_loosening(self):
        old = self._contrato_con_constraint(10)
        new = self._contrato_con_constraint(0)
        resultados = evolution.classify_contract_change(old, new)
        codigos = [r.code for r in resultados]
        self.assertEqual(codigos, [evolution.CODE_CONSTRAINT_LOOSENING])

    def test_max_value_sube_es_loosening(self):
        campo = core.ContractField(name="a", type_family="integer")
        old = _contrato((campo,), (core.Constraint(constraint_id="c-max", constraint_type="max_value", field="a", params={"value": 10}),))
        new = _contrato((campo,), (core.Constraint(constraint_id="c-max", constraint_type="max_value", field="a", params={"value": 20}),))
        resultados = evolution.classify_contract_change(old, new)
        codigos = [r.code for r in resultados]
        self.assertEqual(codigos, [evolution.CODE_CONSTRAINT_LOOSENING])

    def test_allowed_values_subconjunto_es_tightening(self):
        campo = core.ContractField(name="a", type_family="string")
        old = _contrato(
            (campo,),
            (core.Constraint(constraint_id="c-dom", constraint_type="allowed_values", field="a", params={"values": ["x", "y", "z"]}),),
        )
        new = _contrato(
            (campo,),
            (core.Constraint(constraint_id="c-dom", constraint_type="allowed_values", field="a", params={"values": ["x", "y"]}),),
        )
        resultados = evolution.classify_contract_change(old, new)
        codigos = [r.code for r in resultados]
        self.assertEqual(codigos, [evolution.CODE_CONSTRAINT_TIGHTENING])

    def test_allowed_values_superconjunto_es_loosening(self):
        campo = core.ContractField(name="a", type_family="string")
        old = _contrato(
            (campo,),
            (core.Constraint(constraint_id="c-dom", constraint_type="allowed_values", field="a", params={"values": ["x", "y"]}),),
        )
        new = _contrato(
            (campo,),
            (core.Constraint(constraint_id="c-dom", constraint_type="allowed_values", field="a", params={"values": ["x", "y", "z"]}),),
        )
        resultados = evolution.classify_contract_change(old, new)
        codigos = [r.code for r in resultados]
        self.assertEqual(codigos, [evolution.CODE_CONSTRAINT_LOOSENING])

    def test_constraint_nueva_es_tightening(self):
        campo = core.ContractField(name="a", type_family="integer")
        old = _contrato((campo,))
        new = _contrato(
            (campo,), (core.Constraint(constraint_id="c-min", constraint_type="min_value", field="a", params={"value": 1}),)
        )
        resultados = evolution.classify_contract_change(old, new)
        codigos = [r.code for r in resultados]
        self.assertEqual(codigos, [evolution.CODE_CONSTRAINT_TIGHTENING])

    def test_constraint_eliminada_es_loosening(self):
        campo = core.ContractField(name="a", type_family="integer")
        old = _contrato(
            (campo,), (core.Constraint(constraint_id="c-min", constraint_type="min_value", field="a", params={"value": 1}),)
        )
        new = _contrato((campo,))
        resultados = evolution.classify_contract_change(old, new)
        codigos = [r.code for r in resultados]
        self.assertEqual(codigos, [evolution.CODE_CONSTRAINT_LOOSENING])

    def test_constraint_sobre_campo_eliminado_no_duplica_finding(self):
        # `fields` no puede ser vacía -- se agrega un campo neutro que
        # persiste, para aislar el efecto de "a" eliminado.
        campo = core.ContractField(name="a", type_family="integer")
        campo_neutro = core.ContractField(name="z", type_family="string")
        old = _contrato(
            (campo, campo_neutro),
            (core.Constraint(constraint_id="c-min", constraint_type="min_value", field="a", params={"value": 1}),),
        )
        new = _contrato((campo_neutro,))
        resultados = evolution.classify_contract_change(old, new)
        codigos = [r.code for r in resultados]
        self.assertEqual(codigos, [evolution.CODE_REMOVAL])

    def test_severidad_warn_a_fail_es_tightening(self):
        campo = core.ContractField(name="a", type_family="integer")
        old = _contrato(
            (campo,),
            (core.Constraint(constraint_id="c-nn", constraint_type="not_null", field="a", severity="WARN"),),
        )
        new = _contrato(
            (campo,),
            (core.Constraint(constraint_id="c-nn", constraint_type="not_null", field="a", severity="FAIL"),),
        )
        resultados = evolution.classify_contract_change(old, new)
        codigos = [r.code for r in resultados]
        self.assertEqual(codigos, [evolution.CODE_CONSTRAINT_TIGHTENING])

    def test_warn_con_policy_tightening(self):
        old = self._contrato_con_constraint(0)
        new = self._contrato_con_constraint(10)
        policy = _policy(on_constraint_tightening="warn")
        resultados = evolution.classify_contract_change(old, new, policy)
        self.assertEqual(resultados[0].status, checks.STATUS_WARN)


class TestUnknownNeedsReview(unittest.TestCase):
    def test_constraint_type_redefinido(self):
        campo = core.ContractField(name="a", type_family="integer")
        old = _contrato((campo,), (core.Constraint(constraint_id="c1", constraint_type="min_value", field="a", params={"value": 1}),))
        new = _contrato((campo,), (core.Constraint(constraint_id="c1", constraint_type="max_value", field="a", params={"value": 1}),))
        resultados = evolution.classify_contract_change(old, new)
        codigos = [r.code for r in resultados]
        self.assertEqual(codigos, [evolution.CODE_UNKNOWN_NEEDS_REVIEW])

    def test_allowed_values_conjuntos_sin_relacion(self):
        campo = core.ContractField(name="a", type_family="string")
        old = _contrato((campo,), (core.Constraint(constraint_id="c-dom", constraint_type="allowed_values", field="a", params={"values": ["x", "y"]}),))
        new = _contrato((campo,), (core.Constraint(constraint_id="c-dom", constraint_type="allowed_values", field="a", params={"values": ["y", "z"]}),))
        resultados = evolution.classify_contract_change(old, new)
        codigos = [r.code for r in resultados]
        self.assertEqual(codigos, [evolution.CODE_UNKNOWN_NEEDS_REVIEW])

    def test_invariant_nota_distinta(self):
        campo = core.ContractField(name="a", type_family="integer")
        old = _contrato((campo,), (core.Constraint(constraint_id="c-inv", constraint_type="invariant", params={"note": "nota vieja"}),))
        new = _contrato((campo,), (core.Constraint(constraint_id="c-inv", constraint_type="invariant", params={"note": "nota nueva"}),))
        resultados = evolution.classify_contract_change(old, new)
        codigos = [r.code for r in resultados]
        self.assertEqual(codigos, [evolution.CODE_UNKNOWN_NEEDS_REVIEW])

    def test_business_rule_agregada(self):
        campo = core.ContractField(name="a", type_family="integer")
        old = _contrato((campo,))
        new = _contrato((campo,), business_rules=(core.BusinessRule(rule_id="r1", statement="algo"),))
        resultados = evolution.classify_contract_change(old, new)
        codigos = [r.code for r in resultados]
        self.assertEqual(codigos, [evolution.CODE_UNKNOWN_NEEDS_REVIEW])

    def test_dataset_role_distinto(self):
        campo = core.ContractField(name="a", type_family="integer")
        old = _contrato((campo,))
        new = core.DataContract(
            contract_id="c1", version=_version(), dataset_role="feature_table", fields=(campo,)
        )
        resultados = evolution.classify_contract_change(old, new)
        codigos = [r.code for r in resultados]
        self.assertEqual(codigos, [evolution.CODE_UNKNOWN_NEEDS_REVIEW])

    def test_keys_distintas(self):
        campo = core.ContractField(name="a", type_family="integer")
        old = _contrato((campo,), keys=())
        new = _contrato((campo,), keys=("a",))
        resultados = evolution.classify_contract_change(old, new)
        codigos = [r.code for r in resultados]
        self.assertEqual(codigos, [evolution.CODE_UNKNOWN_NEEDS_REVIEW])

    def test_compatibility_policy_id_distinto(self):
        campo = core.ContractField(name="a", type_family="integer")
        old = _contrato((campo,), compatibility_policy=_policy(policy_id="p1"))
        new = _contrato((campo,), compatibility_policy=_policy(policy_id="p2"))
        resultados = evolution.classify_contract_change(old, new)
        codigos = [r.code for r in resultados]
        self.assertEqual(codigos, [evolution.CODE_UNKNOWN_NEEDS_REVIEW])

    def test_warn_con_policy(self):
        campo = core.ContractField(name="a", type_family="integer")
        old = _contrato((campo,))
        new = _contrato((campo,), business_rules=(core.BusinessRule(rule_id="r1", statement="algo"),))
        policy = _policy(on_unknown_change="warn")
        resultados = evolution.classify_contract_change(old, new, policy)
        self.assertEqual(resultados[0].status, checks.STATUS_WARN)


class TestDeterminismoYPureza(unittest.TestCase):
    def test_mismo_input_misma_lista(self):
        old = _contrato((core.ContractField(name="a", type_family="string"),))
        new = _contrato(
            (
                core.ContractField(name="a", type_family="integer"),
                core.ContractField(name="b", type_family="string", required=False),
            )
        )
        policy = _policy()
        r1 = evolution.classify_contract_change(old, new, policy)
        r2 = evolution.classify_contract_change(old, new, policy)
        self.assertEqual([r.to_dict() for r in r1], [r.to_dict() for r in r2])

    def test_sin_contrato_identico_lista_vacia(self):
        old = _contrato((core.ContractField(name="a", type_family="string"),))
        new = _contrato((core.ContractField(name="a", type_family="string"),))
        self.assertEqual(evolution.classify_contract_change(old, new), [])


if __name__ == "__main__":
    unittest.main()

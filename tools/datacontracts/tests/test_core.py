"""Tests de `tools/datacontracts/core.py` (v0.7 Change 0,
`20260922-data-contracts-core`). Cobertura de `spec.md` R1-R12 con sus
criterios de aceptación Given/When/Then. Sin I/O de red, sin pandas/numpy, sin
lectura de ningún dataset ni `profile.json` real, sin aleatoriedad (R17).
"""
from __future__ import annotations

import copy
import unittest

from tools.datacontracts import core as dc


def _campo(**overrides) -> dc.ContractField:
    base = dict(name="edad", type_family="integer")
    base.update(overrides)
    return dc.ContractField(**base)


def _version(**overrides) -> dc.ContractVersion:
    base = dict(version="1.0.0")
    base.update(overrides)
    return dc.ContractVersion(**base)


def _policy(**overrides) -> dc.CompatibilityPolicy:
    base = dict(
        policy_id="pol-1",
        on_removed_field="block",
        on_required_field_added="warn",
        on_type_change="block",
        on_constraint_tightening="warn",
        on_constraint_loosening="allow",
        on_unknown_change="block",
    )
    base.update(overrides)
    return dc.CompatibilityPolicy(**base)


def _contrato_minimo(**overrides) -> dc.DataContract:
    base = dict(
        contract_id="contrato-1",
        version=_version(),
        dataset_role="raw_table",
        fields=(_campo(),),
    )
    base.update(overrides)
    return dc.DataContract(**base)


class TestVocabularios(unittest.TestCase):
    def test_type_families(self):
        self.assertEqual(
            dc.TYPE_FAMILIES,
            ("string", "integer", "float", "boolean", "date", "datetime", "unknown"),
        )

    def test_dataset_roles(self):
        self.assertEqual(dc.DATASET_ROLES, ("raw_table", "feature_table", "scoring_output", "generic"))

    def test_constraint_types(self):
        self.assertEqual(
            dc.CONSTRAINT_TYPES,
            (
                "not_null",
                "unique",
                "allowed_values",
                "min_value",
                "max_value",
                "min_length",
                "max_length",
                "date_min",
                "date_max",
                "invariant",
            ),
        )

    def test_severities(self):
        self.assertEqual(dc.SEVERITIES, ("FAIL", "WARN"))

    def test_compat_actions(self):
        self.assertEqual(dc.COMPAT_ACTIONS, ("block", "warn", "allow"))

    def test_extension_prefix_y_schema_version(self):
        self.assertEqual(dc.EXTENSION_PREFIX, "x_")
        self.assertEqual(dc.SCHEMA_VERSION, 1)

    def test_data_contract_error_es_value_error(self):
        self.assertTrue(issubclass(dc.DataContractError, ValueError))


class TestIdsSeguros(unittest.TestCase):
    """R3: `contract_id`/`constraint_id`/`rule_id`/`policy_id`."""

    def _construir_con_id(self, valor):
        return dc.DataContract(
            contract_id=valor,
            version=_version(),
            dataset_role="raw_table",
            fields=(_campo(),),
        )

    def test_ids_invalidos(self):
        invalidos = ["", "Con-Mayuscula", "con.punto", "con/slash", "a" * 65, "con", "PRN".lower(), "com1", "lpt9"]
        for valor in invalidos:
            with self.subTest(valor=valor):
                with self.assertRaises(dc.DataContractError):
                    self._construir_con_id(valor)

    def test_id_no_str(self):
        with self.assertRaises(dc.DataContractError):
            self._construir_con_id(123)

    def test_ids_validos(self):
        for valor in ("a", "contrato-1", "contrato_1", "c" * 64):
            with self.subTest(valor=valor):
                self._construir_con_id(valor)  # no debe lanzar

    def test_constraint_id_rule_id_policy_id_mismo_patron(self):
        with self.assertRaises(dc.DataContractError):
            dc.Constraint(constraint_id="Con", constraint_type="not_null")
        with self.assertRaises(dc.DataContractError):
            dc.BusinessRule(rule_id="con", statement="regla")
        with self.assertRaises(dc.DataContractError):
            _policy(policy_id="prn")


class TestNombresDeCampo(unittest.TestCase):
    """R4: `ContractField.name`."""

    def test_nombres_invalidos(self):
        for nombre in ("", "Nombre", "1campo", "campo-1", "campo.1"):
            with self.subTest(nombre=nombre):
                with self.assertRaises(dc.DataContractError):
                    _campo(name=nombre)

    def test_nombres_validos(self):
        for nombre in ("campo_1", "a", "nombre_largo_valido"):
            with self.subTest(nombre=nombre):
                _campo(name=nombre)  # no debe lanzar


class TestContractField(unittest.TestCase):
    def test_type_family_invalido(self):
        with self.assertRaises(dc.DataContractError):
            _campo(type_family="otro")

    def test_required_nullable_no_bool(self):
        with self.assertRaises(dc.DataContractError):
            _campo(required=1)
        with self.assertRaises(dc.DataContractError):
            _campo(nullable="si")

    def test_extensions_con_prefijo_valido(self):
        campo = _campo(extensions={"x_nota": "ok"})
        self.assertEqual(campo.extensions, {"x_nota": "ok"})

    def test_extensions_sin_prefijo_invalido(self):
        with self.assertRaises(dc.DataContractError):
            _campo(extensions={"nota": "sin prefijo"})

    def test_extensions_valor_no_json_seguro(self):
        with self.assertRaises(dc.DataContractError):
            _campo(extensions={"x_obj": object()})
        with self.assertRaises(dc.DataContractError):
            _campo(extensions={"x_nan": float("nan")})

    def test_defaults(self):
        campo = _campo()
        self.assertTrue(campo.required)
        self.assertTrue(campo.nullable)
        self.assertEqual(campo.description, "")
        self.assertEqual(campo.extensions, {})


class TestConstraint(unittest.TestCase):
    def test_constraint_type_invalido(self):
        with self.assertRaises(dc.DataContractError):
            dc.Constraint(constraint_id="c1", constraint_type="otro")

    def test_severity_invalida(self):
        with self.assertRaises(dc.DataContractError):
            dc.Constraint(constraint_id="c1", constraint_type="not_null", severity="INFO")

    def test_not_null_params_vacio_o_con_claves(self):
        dc.Constraint(constraint_id="c1", constraint_type="not_null")
        dc.Constraint(constraint_id="c1", constraint_type="not_null", params={"nota": "ok"})

    def test_unique_fields_opcional(self):
        dc.Constraint(constraint_id="c1", constraint_type="unique")
        dc.Constraint(constraint_id="c1", constraint_type="unique", params={"fields": ["a", "b"]})
        with self.assertRaises(dc.DataContractError):
            dc.Constraint(constraint_id="c1", constraint_type="unique", params={"fields": ["a", ""]})
        with self.assertRaises(dc.DataContractError):
            dc.Constraint(constraint_id="c1", constraint_type="unique", params={"fields": "no-lista"})

    def test_allowed_values(self):
        with self.assertRaises(dc.DataContractError):
            dc.Constraint(constraint_id="c1", constraint_type="allowed_values")
        with self.assertRaises(dc.DataContractError):
            dc.Constraint(constraint_id="c1", constraint_type="allowed_values", params={"values": []})
        with self.assertRaises(dc.DataContractError):
            dc.Constraint(
                constraint_id="c1", constraint_type="allowed_values", params={"values": [1, 1, 2]}
            )
        restriccion = dc.Constraint(
            constraint_id="c1", constraint_type="allowed_values", params={"values": [1, 2, 3]}
        )
        self.assertEqual(restriccion.params["values"], [1, 2, 3])

    def test_min_value_max_value(self):
        with self.assertRaises(dc.DataContractError):
            dc.Constraint(constraint_id="c1", constraint_type="min_value", params={"value": True})
        with self.assertRaises(dc.DataContractError):
            dc.Constraint(constraint_id="c1", constraint_type="min_value")
        dc.Constraint(constraint_id="c1", constraint_type="min_value", params={"value": 10})
        dc.Constraint(constraint_id="c1", constraint_type="max_value", params={"value": 10.5})
        with self.assertRaises(dc.DataContractError):
            dc.Constraint(constraint_id="c1", constraint_type="min_value", params={"value": "10"})

    def test_min_length_max_length(self):
        with self.assertRaises(dc.DataContractError):
            dc.Constraint(constraint_id="c1", constraint_type="min_length", params={"value": -1})
        with self.assertRaises(dc.DataContractError):
            dc.Constraint(constraint_id="c1", constraint_type="min_length", params={"value": 1.5})
        with self.assertRaises(dc.DataContractError):
            dc.Constraint(constraint_id="c1", constraint_type="min_length", params={"value": True})
        dc.Constraint(constraint_id="c1", constraint_type="min_length", params={"value": 0})

    def test_date_min_date_max(self):
        with self.assertRaises(dc.DataContractError):
            dc.Constraint(constraint_id="c1", constraint_type="date_min", params={"value": ""})
        dc.Constraint(constraint_id="c1", constraint_type="date_min", params={"value": "2020-01-01"})
        # sin parseo de formato: cualquier str no vacío es válido
        dc.Constraint(constraint_id="c1", constraint_type="date_max", params={"value": "no-es-fecha"})

    def test_invariant(self):
        with self.assertRaises(dc.DataContractError):
            dc.Constraint(constraint_id="c1", constraint_type="invariant")
        with self.assertRaises(dc.DataContractError):
            dc.Constraint(constraint_id="c1", constraint_type="invariant", params={"note": ""})
        restriccion = dc.Constraint(
            constraint_id="c1",
            constraint_type="invariant",
            params={"note": "suma de a y b es 100", "fields": ["a", "b"]},
        )
        self.assertEqual(restriccion.params["note"], "suma de a y b es 100")

    def test_field_none_valido_field_vacio_invalido(self):
        dc.Constraint(constraint_id="c1", constraint_type="not_null", field=None)
        with self.assertRaises(dc.DataContractError):
            dc.Constraint(constraint_id="c1", constraint_type="not_null", field="")

    def test_params_no_es_ejecutable_solo_json_puro(self):
        with self.assertRaises(dc.DataContractError):
            dc.Constraint(
                constraint_id="c1",
                constraint_type="invariant",
                params={"note": "x", "lambda": lambda: True},
            )


class TestBusinessRule(unittest.TestCase):
    def test_statement_vacio(self):
        with self.assertRaises(dc.DataContractError):
            dc.BusinessRule(rule_id="r1", statement="")

    def test_defaults(self):
        regla = dc.BusinessRule(rule_id="r1", statement="algo")
        self.assertEqual(regla.rationale, "")
        self.assertIsNone(regla.reference)

    def test_reference_vacio_invalido(self):
        with self.assertRaises(dc.DataContractError):
            dc.BusinessRule(rule_id="r1", statement="algo", reference="")

    def test_reference_none_o_no_vacio_validos(self):
        dc.BusinessRule(rule_id="r1", statement="algo", reference=None)
        dc.BusinessRule(rule_id="r1", statement="algo", reference="ticket-123")

    def test_core_no_evalua_business_rule(self):
        """Ningún identificador de `core.py` combina un verbo de evaluación
        (evaluate/evaluar/check/validate_against) con `BusinessRule`."""
        import ast
        from pathlib import Path

        ruta = Path(dc.__file__)
        arbol = ast.parse(ruta.read_text(encoding="utf-8"), filename=str(ruta))
        verbos = ("evaluate", "evaluar", "check", "validate_against")
        identificadores = []
        for nodo in ast.walk(arbol):
            if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                identificadores.append(nodo.name)
            elif isinstance(nodo, ast.Name):
                identificadores.append(nodo.id)
            elif isinstance(nodo, ast.Attribute):
                identificadores.append(nodo.attr)
        violaciones = [
            ident
            for ident in identificadores
            if "businessrule" in ident.lower()
            and any(verbo in ident.lower() for verbo in verbos)
        ]
        self.assertEqual(violaciones, [])


class TestContractVersion(unittest.TestCase):
    def test_version_invalida(self):
        for valor in ("1.0", "v1.0.0", "1.0.0.1"):
            with self.subTest(valor=valor):
                with self.assertRaises(dc.DataContractError):
                    _version(version=valor)

    def test_version_valida(self):
        for valor in ("1.0.0", "0.0.1"):
            with self.subTest(valor=valor):
                _version(version=valor)

    def test_previous_version(self):
        with self.assertRaises(dc.DataContractError):
            _version(previous_version="1.0")
        _version(previous_version=None)
        _version(previous_version="0.9.0")

    def test_core_no_define_compare_diff_classify(self):
        import ast
        from pathlib import Path

        ruta = Path(dc.__file__)
        arbol = ast.parse(ruta.read_text(encoding="utf-8"), filename=str(ruta))
        nombres_funcion = [
            nodo.name for nodo in ast.walk(arbol) if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        prohibidos = ("compare", "diff", "classify")
        violaciones = [n for n in nombres_funcion if any(p in n.lower() for p in prohibidos)]
        self.assertEqual(violaciones, [])


class TestCompatibilityPolicy(unittest.TestCase):
    def test_valor_fuera_de_compat_actions(self):
        with self.assertRaises(dc.DataContractError):
            _policy(on_removed_field="ignore")

    def test_falta_un_campo_requerido_es_type_error(self):
        with self.assertRaises(TypeError):
            dc.CompatibilityPolicy(
                policy_id="pol-1",
                on_removed_field="block",
                on_required_field_added="warn",
                on_type_change="block",
                on_constraint_tightening="warn",
                on_constraint_loosening="allow",
                # falta on_unknown_change
            )

    def test_construccion_valida(self):
        politica = _policy()
        self.assertEqual(politica.on_removed_field, "block")


class TestDataContract(unittest.TestCase):
    def test_fields_vacia(self):
        with self.assertRaises(dc.DataContractError):
            _contrato_minimo(fields=())

    def test_fields_duplicados(self):
        with self.assertRaises(dc.DataContractError):
            _contrato_minimo(fields=(_campo(name="a"), _campo(name="a")))

    def test_constraints_id_duplicado(self):
        with self.assertRaises(dc.DataContractError):
            _contrato_minimo(
                fields=(_campo(name="edad"),),
                constraints=(
                    dc.Constraint(constraint_id="c1", constraint_type="not_null", field="edad"),
                    dc.Constraint(constraint_id="c1", constraint_type="unique", field="edad"),
                ),
            )

    def test_constraint_field_inexistente(self):
        with self.assertRaises(dc.DataContractError):
            _contrato_minimo(
                fields=(_campo(name="edad"),),
                constraints=(dc.Constraint(constraint_id="c1", constraint_type="not_null", field="inexistente"),),
            )

    def test_constraint_field_none_valido(self):
        contrato = _contrato_minimo(
            fields=(_campo(name="edad"),),
            constraints=(dc.Constraint(constraint_id="c1", constraint_type="invariant", params={"note": "x"}, field=None),),
        )
        self.assertEqual(len(contrato.constraints), 1)

    def test_unique_params_fields_referencia_inexistente(self):
        with self.assertRaises(dc.DataContractError):
            _contrato_minimo(
                fields=(_campo(name="a"),),
                constraints=(
                    dc.Constraint(
                        constraint_id="c1",
                        constraint_type="unique",
                        params={"fields": ["a", "inexistente"]},
                    ),
                ),
            )

    def test_business_rules_id_duplicado(self):
        with self.assertRaises(dc.DataContractError):
            _contrato_minimo(
                business_rules=(
                    dc.BusinessRule(rule_id="r1", statement="a"),
                    dc.BusinessRule(rule_id="r1", statement="b"),
                )
            )

    def test_rule_id_puede_coincidir_con_constraint_id(self):
        contrato = _contrato_minimo(
            fields=(_campo(name="edad"),),
            constraints=(dc.Constraint(constraint_id="mismo-id", constraint_type="not_null", field="edad"),),
            business_rules=(dc.BusinessRule(rule_id="mismo-id", statement="regla"),),
        )
        self.assertEqual(contrato.get_constraint("mismo-id").constraint_id, "mismo-id")
        self.assertEqual(contrato.get_business_rule("mismo-id").rule_id, "mismo-id")

    def test_keys_inexistente(self):
        with self.assertRaises(dc.DataContractError):
            _contrato_minimo(fields=(_campo(name="id"),), keys=("campo_inexistente",))

    def test_keys_vacia_o_valida(self):
        _contrato_minimo(fields=(_campo(name="id"),), keys=())
        _contrato_minimo(fields=(_campo(name="id"),), keys=("id",))

    def test_compatibility_policy_tipo_incorrecto(self):
        with self.assertRaises(dc.DataContractError):
            _contrato_minimo(compatibility_policy={"a": 1})

    def test_compatibility_policy_valida(self):
        contrato = _contrato_minimo(compatibility_policy=_policy())
        self.assertIsNotNone(contrato.compatibility_policy)

    def test_schema_version_incorrecto(self):
        with self.assertRaises(dc.DataContractError):
            _contrato_minimo(schema_version=2)

    def test_accesores_no_lanzan(self):
        contrato = _contrato_minimo(
            fields=(_campo(name="edad"),),
            constraints=(dc.Constraint(constraint_id="c1", constraint_type="not_null", field="edad"),),
            business_rules=(dc.BusinessRule(rule_id="r1", statement="algo"),),
        )
        self.assertIsNotNone(contrato.get_field("edad"))
        self.assertIsNone(contrato.get_field("inexistente"))
        self.assertIsNotNone(contrato.get_constraint("c1"))
        self.assertIsNone(contrato.get_constraint("inexistente"))
        self.assertIsNotNone(contrato.get_business_rule("r1"))
        self.assertIsNone(contrato.get_business_rule("inexistente"))
        self.assertEqual(len(contrato.constraints_for("edad")), 1)
        self.assertEqual(contrato.constraints_for(None), ())


class TestValidacionEnConstruccion(unittest.TestCase):
    """R11."""

    def test_ningun_constructor_acepta_parametros_de_datos_reales(self):
        import inspect

        prohibidos = {"data", "frame", "dataframe", "profile", "rows", "path", "ruta"}
        for clase in (
            dc.ContractField,
            dc.Constraint,
            dc.BusinessRule,
            dc.ContractVersion,
            dc.CompatibilityPolicy,
            dc.DataContract,
        ):
            firma = inspect.signature(clase.__init__)
            nombres = set(firma.parameters) - {"self"}
            interseccion = nombres & prohibidos
            self.assertEqual(interseccion, set(), f"{clase.__name__}: parámetros prohibidos {interseccion}")

    def test_extensions_mutado_por_llamador_no_afecta_al_objeto(self):
        extensiones = {"x_nota": "original"}
        campo = _campo(extensions=extensiones)
        extensiones["x_nota"] = "mutado"
        extensiones["x_nueva"] = "otra"
        self.assertEqual(campo.extensions, {"x_nota": "original"})

    def test_params_mutado_por_llamador_no_afecta_al_objeto(self):
        params = {"value": 10}
        restriccion = dc.Constraint(constraint_id="c1", constraint_type="min_value", params=params)
        params["value"] = 999
        self.assertEqual(restriccion.params, {"value": 10})


class TestSerializacionDeterminista(unittest.TestCase):
    """R12."""

    def _contrato_completo(self) -> dc.DataContract:
        return dc.DataContract(
            contract_id="contrato-completo",
            version=_version(summary="v1", previous_version="0.9.0"),
            dataset_role="feature_table",
            fields=(
                _campo(name="edad", extensions={"x_nota": "a"}),
                _campo(name="nombre", type_family="string", extensions={"x_b": 1, "x_a": 2}),
            ),
            constraints=(
                dc.Constraint(
                    constraint_id="c1",
                    constraint_type="min_value",
                    field="edad",
                    params={"value": 0},
                ),
                dc.Constraint(
                    constraint_id="c2",
                    constraint_type="unique",
                    params={"fields": ["edad", "nombre"]},
                ),
            ),
            business_rules=(dc.BusinessRule(rule_id="r1", statement="regla de negocio"),),
            keys=("edad",),
            compatibility_policy=_policy(),
            description="contrato completo de prueba",
            extensions={"x_meta": {"z": 1, "a": 2}},
        )

    def test_hash_igual_con_distinto_orden_de_claves_de_extensions(self):
        contrato_1 = _contrato_minimo(fields=(_campo(name="a", extensions={"x_1": 1, "x_2": 2}),))
        contrato_2 = _contrato_minimo(fields=(_campo(name="a", extensions={"x_2": 2, "x_1": 1}),))
        self.assertEqual(contrato_1.content_sha256(), contrato_2.content_sha256())

    def test_round_trip_from_dict_preserva_contenido_y_hash(self):
        contrato = self._contrato_completo()
        recuperado = dc.DataContract.from_dict(contrato.to_dict())
        self.assertEqual(contrato, recuperado)
        self.assertEqual(contrato.content_sha256(), recuperado.content_sha256())

    def test_to_dict_serializable_con_json_dumps(self):
        import json as json_std

        contrato = self._contrato_completo()
        json_std.dumps(contrato.to_dict())  # no debe lanzar

    def test_canonical_json_sin_espacios_ni_escapes_no_ascii(self):
        texto = dc.canonical_json({"a": 1, "b": "ñ"})
        self.assertNotIn(" ", texto)
        self.assertIn("ñ", texto)

    def test_from_dict_campo_requerido_ausente(self):
        contrato = self._contrato_completo()
        datos = contrato.to_dict()
        del datos["dataset_role"]
        with self.assertRaises(dc.DataContractError):
            dc.DataContract.from_dict(datos)

    def test_from_dict_schema_version_ausente_o_distinto(self):
        contrato = self._contrato_completo()
        datos_sin_version = contrato.to_dict()
        del datos_sin_version["schema_version"]
        with self.assertRaises(dc.DataContractError):
            dc.DataContract.from_dict(datos_sin_version)

        datos_version_distinta = contrato.to_dict()
        datos_version_distinta["schema_version"] = 2
        with self.assertRaises(dc.DataContractError):
            dc.DataContract.from_dict(datos_version_distinta)

    def test_from_dict_ignora_claves_desconocidas(self):
        contrato = self._contrato_completo()
        datos = contrato.to_dict()
        datos["clave_futura_desconocida"] = "algo"
        recuperado = dc.DataContract.from_dict(datos)
        self.assertEqual(contrato, recuperado)

    def test_canonical_json_nan_lanza_error(self):
        with self.assertRaises(dc.DataContractError):
            dc.canonical_json({"a": float("nan")})

    def test_cambiar_un_valor_de_params_cambia_el_hash(self):
        contrato_1 = self._contrato_completo()
        kwargs = dict(
            contract_id=contrato_1.contract_id,
            version=contrato_1.version,
            dataset_role=contrato_1.dataset_role,
            fields=contrato_1.fields,
            business_rules=contrato_1.business_rules,
            keys=contrato_1.keys,
            compatibility_policy=contrato_1.compatibility_policy,
            description=contrato_1.description,
            extensions=contrato_1.extensions,
        )
        kwargs["constraints"] = (
            dc.Constraint(
                constraint_id="c1",
                constraint_type="min_value",
                field="edad",
                params={"value": 999},  # distinto del 0 original
            ),
            contrato_1.constraints[1],
        )
        contrato_2 = dc.DataContract(**kwargs)
        self.assertNotEqual(contrato_1.content_sha256(), contrato_2.content_sha256())

    def test_data_contract_no_expone_generated_at(self):
        contrato = self._contrato_completo()
        self.assertNotIn("generated_at", contrato.to_dict())
        self.assertFalse(hasattr(contrato, "generated_at"))

    def test_deep_copy_de_params_no_afecta_contrato_original(self):
        contrato = self._contrato_completo()
        copia = copy.deepcopy(contrato.to_dict())
        copia["extensions"]["x_meta"]["z"] = 999
        self.assertEqual(contrato.to_dict()["extensions"]["x_meta"]["z"], 1)


if __name__ == "__main__":
    unittest.main()

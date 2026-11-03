"""Tests de `tools/datacontracts/validation.py` (v0.7 Change 1,
`20260922-data-contract-validation`). Cobertura de `spec.md` R1-R17 (criterios
Given/When/Then). Fixtures 100% sintéticas (`DataContract` + `dict` de perfil armados a
mano): nunca `ds_profile.run` ni un dataset real. Sin I/O de red, sin pandas/numpy, sin
aleatoriedad (R14).
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.datacontracts import core as dc
from tools.datacontracts import validation as v


# --- Fixtures --------------------------------------------------------------------


def _campo(**overrides) -> dc.ContractField:
    base = dict(name="id", type_family="integer", required=True, nullable=False)
    base.update(overrides)
    return dc.ContractField(**base)


def _version(**overrides) -> dc.ContractVersion:
    base = dict(version="1.0.0")
    base.update(overrides)
    return dc.ContractVersion(**base)


def _contrato(fields=None, constraints=(), keys=(), **overrides) -> dc.DataContract:
    base = dict(
        contract_id="contrato_test",
        version=_version(),
        dataset_role="generic",
        fields=fields if fields is not None else (_campo(),),
        constraints=constraints,
        keys=keys,
    )
    base.update(overrides)
    return dc.DataContract(**base)


def _constraint(**overrides) -> dc.Constraint:
    base = dict(constraint_id="c1", constraint_type="not_null", field="id")
    base.update(overrides)
    return dc.Constraint(**base)


def _col_entera(minimo=1, maximo=3, nulos=0, unique_count=3, exactitud="exacta", top_valores=None):
    return {
        "dtype": "entero",
        "nulls": {"count": nulos, "pct": 0.0, "exactitud": "exacta"},
        "unique": {"count": unique_count, "exactitud": exactitud},
        "top_valores": (
            top_valores
            if top_valores is not None
            else [{"valor": "1", "frecuencia": 1}, {"valor": "2", "frecuencia": 1}, {"valor": "3", "frecuencia": 1}]
        ),
        "min": minimo,
        "max": maximo,
    }


def _col_texto(nulos=0, unique_count=1, exactitud="exacta", top_valores=None):
    return {
        "dtype": "texto",
        "nulls": {"count": nulos, "pct": 0.0, "exactitud": "exacta"},
        "unique": {"count": unique_count, "exactitud": exactitud},
        "top_valores": top_valores if top_valores is not None else [{"valor": "a", "frecuencia": 1}],
    }


def _col_fecha(fecha_min="2019-01-01T00:00:00", fecha_max="2024-01-01T00:00:00", nulos=0, unique_count=1, exactitud="exacta"):
    return {
        "dtype": "fecha",
        "nulls": {"count": nulos, "pct": 0.0, "exactitud": "exacta"},
        "unique": {"count": unique_count, "exactitud": exactitud},
        "top_valores": [{"valor": fecha_min, "frecuencia": 1}],
        "fecha_min": fecha_min,
        "fecha_max": fecha_max,
    }


def _perfil(schema=None, columnas_detalle=None, sampling_activo=False, tamano_muestra=None, filas=3):
    return {
        "schema": schema if schema is not None else {"id": "entero"},
        "columnas_detalle": columnas_detalle if columnas_detalle is not None else {"id": _col_entera()},
        "sampling": {
            "activo": sampling_activo,
            "metodo": "reservoir_v1",
            "semilla": 42,
            "tamano_muestra": tamano_muestra,
        },
        "filas": filas,
    }


def _codigos(resultados):
    return [r.code for r in resultados]


def _por_codigo(resultados, codigo):
    return [r for r in resultados if r.code == codigo]


# --- R2: registro de códigos -------------------------------------------------------


class TestRegistroDeCodigos(unittest.TestCase):
    def test_codes_tiene_14_codigos_unicos(self):
        self.assertEqual(len(v.CODES), 14)
        self.assertEqual(len(set(v.CODES)), 14)

    def test_codes_contiene_los_14_esperados(self):
        esperados = {
            "CONTRACT-INPUT",
            "CONTRACT-EVIDENCE-MISSING",
            "CONTRACT-FIELD-MISSING",
            "CONTRACT-FIELD-UNEXPECTED",
            "CONTRACT-TYPE-MISMATCH",
            "CONTRACT-NULLABILITY",
            "CONTRACT-KEY",
            "CONTRACT-NOT-NULL-EXPECTATION",
            "CONTRACT-UNIQUENESS",
            "CONTRACT-DOMAIN",
            "CONTRACT-RANGE",
            "CONTRACT-LENGTH",
            "CONTRACT-DATE-RANGE",
            "CONTRACT-INVARIANT",
        }
        self.assertEqual(set(v.CODES), esperados)


# --- R2/R3: CONTRACT-INPUT / gate de evidencia --------------------------------------


class TestInputYGateDeEvidencia(unittest.TestCase):
    def test_contract_invalido_produce_solo_contract_input_technical_error(self):
        resultados = v.validate_contract("no soy un DataContract", _perfil())
        self.assertEqual(len(resultados), 1)
        r = resultados[0]
        self.assertEqual(r.code, "CONTRACT-INPUT")
        self.assertEqual(r.status, "FAIL")
        self.assertEqual(r.kind, "technical_error")

    def test_profile_no_dict_produce_solo_evidence_missing(self):
        resultados = v.validate_contract(_contrato(), [])
        self.assertEqual(len(resultados), 1)
        r = resultados[0]
        self.assertEqual(r.code, "CONTRACT-EVIDENCE-MISSING")
        self.assertEqual(r.status, "FAIL")
        self.assertEqual(r.kind, "technical_error")

    def test_profile_none_produce_solo_evidence_missing(self):
        resultados = v.validate_contract(_contrato(), None)
        self.assertEqual(len(resultados), 1)
        self.assertEqual(resultados[0].code, "CONTRACT-EVIDENCE-MISSING")

    def _perfil_sin(self, clave):
        p = _perfil()
        del p[clave]
        return p

    def test_falta_schema_corta_en_evidence_missing(self):
        resultados = v.validate_contract(_contrato(), self._perfil_sin("schema"))
        self.assertEqual(len(resultados), 1)
        self.assertEqual(resultados[0].code, "CONTRACT-EVIDENCE-MISSING")

    def test_falta_columnas_detalle_corta_en_evidence_missing(self):
        resultados = v.validate_contract(_contrato(), self._perfil_sin("columnas_detalle"))
        self.assertEqual(len(resultados), 1)
        self.assertEqual(resultados[0].code, "CONTRACT-EVIDENCE-MISSING")

    def test_falta_sampling_corta_en_evidence_missing(self):
        resultados = v.validate_contract(_contrato(), self._perfil_sin("sampling"))
        self.assertEqual(len(resultados), 1)
        self.assertEqual(resultados[0].code, "CONTRACT-EVIDENCE-MISSING")

    def test_falta_filas_corta_en_evidence_missing(self):
        resultados = v.validate_contract(_contrato(), self._perfil_sin("filas"))
        self.assertEqual(len(resultados), 1)
        self.assertEqual(resultados[0].code, "CONTRACT-EVIDENCE-MISSING")

    def test_sampling_activo_no_bool_produce_evidence_missing(self):
        p = _perfil()
        p["sampling"]["activo"] = "si"
        resultados = v.validate_contract(_contrato(), p)
        self.assertEqual(len(resultados), 1)
        self.assertEqual(resultados[0].code, "CONTRACT-EVIDENCE-MISSING")


# --- R3: caso sin ninguna violación posible -----------------------------------------


class TestCasoSinViolaciones(unittest.TestCase):
    def test_contrato_minimo_y_perfil_coherente_solo_pass_o_na(self):
        resultados = v.validate_contract(_contrato(), _perfil())
        self.assertTrue(resultados)
        for r in resultados:
            self.assertIn(r.status, ("PASS", "N/A"))
        # Un resultado por código aplicable de las 5 reglas estructurales (sin constraints).
        self.assertEqual(
            sorted(_codigos(resultados)),
            sorted(
                [
                    "CONTRACT-FIELD-MISSING",
                    "CONTRACT-FIELD-UNEXPECTED",
                    "CONTRACT-TYPE-MISMATCH",
                    "CONTRACT-NULLABILITY",
                    "CONTRACT-KEY",
                ]
            ),
        )


# --- R8/R9: field-missing / field-unexpected ----------------------------------------


class TestFieldMissingUnexpected(unittest.TestCase):
    def test_campo_requerido_ausente_es_fail(self):
        contrato = _contrato(fields=(_campo(name="id", required=True),))
        perfil = _perfil(schema={}, columnas_detalle={})
        resultados = v.validate_contract(contrato, perfil)
        fm = _por_codigo(resultados, "CONTRACT-FIELD-MISSING")
        self.assertEqual(len(fm), 1)
        self.assertEqual(fm[0].status, "FAIL")
        self.assertEqual(fm[0].subject, "id")

    def test_campo_opcional_ausente_no_produce_resultado(self):
        contrato = _contrato(
            fields=(
                _campo(name="id", required=True, nullable=False),
                _campo(name="opcional", required=False, type_family="string"),
            )
        )
        resultados = v.validate_contract(contrato, _perfil())
        fm = _por_codigo(resultados, "CONTRACT-FIELD-MISSING")
        # Ninguna entrada de FIELD-MISSING referencia 'opcional'; con 'id' presente, PASS único.
        self.assertEqual(len(fm), 1)
        self.assertEqual(fm[0].status, "PASS")

    def test_columna_no_declarada_es_warn(self):
        perfil = _perfil(
            schema={"id": "entero", "extra": "texto"},
            columnas_detalle={"id": _col_entera(), "extra": _col_texto()},
        )
        resultados = v.validate_contract(_contrato(), perfil)
        fu = _por_codigo(resultados, "CONTRACT-FIELD-UNEXPECTED")
        self.assertEqual(len(fu), 1)
        self.assertEqual(fu[0].status, "WARN")
        self.assertEqual(fu[0].subject, "extra")


# --- R6: bridge type_family -> dtype (los 7 valores) --------------------------------


class TestBridgeTypeFamily(unittest.TestCase):
    def _resultado_type_mismatch(self, type_family, dtype_observado, columna=None):
        contrato = _contrato(fields=(_campo(name="c", type_family=type_family, required=True, nullable=True),))
        columna = columna or {**_col_entera(), "dtype": dtype_observado}
        perfil = _perfil(schema={"c": dtype_observado}, columnas_detalle={"c": columna})
        resultados = v.validate_contract(contrato, perfil)
        return _por_codigo(resultados, "CONTRACT-TYPE-MISMATCH")

    def test_string_texto_pass(self):
        r = self._resultado_type_mismatch("string", "texto", _col_texto())
        self.assertEqual(r[0].status, "PASS")

    def test_integer_entero_pass_flotante_fail(self):
        r_pass = self._resultado_type_mismatch("integer", "entero")
        self.assertEqual(r_pass[0].status, "PASS")
        r_fail = self._resultado_type_mismatch("integer", "flotante")
        self.assertEqual(r_fail[0].status, "FAIL")

    def test_float_flotante_pass(self):
        r = self._resultado_type_mismatch("float", "flotante")
        self.assertEqual(r[0].status, "PASS")

    def test_boolean_booleano_pass(self):
        columna = {**_col_entera(), "dtype": "booleano"}
        r = self._resultado_type_mismatch("boolean", "booleano", columna)
        self.assertEqual(r[0].status, "PASS")

    def test_date_fecha_pass(self):
        r = self._resultado_type_mismatch("date", "fecha", _col_fecha())
        self.assertEqual(r[0].status, "PASS")

    def test_datetime_fecha_pass(self):
        r = self._resultado_type_mismatch("datetime", "fecha", _col_fecha())
        self.assertEqual(r[0].status, "PASS")

    def test_unknown_es_siempre_na(self):
        r = self._resultado_type_mismatch("unknown", "texto", _col_texto())
        self.assertEqual(r[0].status, "N/A")
        r2 = self._resultado_type_mismatch("unknown", "entero")
        self.assertEqual(r2[0].status, "N/A")


# --- R7: nullability / range deterministas bajo sampling.activo=True ----------------


class TestNullabilityDeterministaBajoMuestreo(unittest.TestCase):
    def test_nullable_false_sin_nulos_pass_bajo_sampling_activo(self):
        contrato = _contrato(fields=(_campo(name="id", nullable=False, required=True),))
        perfil = _perfil(sampling_activo=True, tamano_muestra=100, columnas_detalle={"id": _col_entera(nulos=0)})
        resultados = v.validate_contract(contrato, perfil)
        nb = _por_codigo(resultados, "CONTRACT-NULLABILITY")
        self.assertEqual(nb[0].status, "PASS")

    def test_nullable_false_con_nulos_fail_bajo_sampling_activo(self):
        contrato = _contrato(fields=(_campo(name="id", nullable=False, required=True),))
        perfil = _perfil(sampling_activo=True, tamano_muestra=100, columnas_detalle={"id": _col_entera(nulos=3)})
        resultados = v.validate_contract(contrato, perfil)
        nb = _por_codigo(resultados, "CONTRACT-NULLABILITY")
        self.assertEqual(nb[0].status, "FAIL")


# --- R11: CONTRACT-KEY ---------------------------------------------------------------


class TestContractKey(unittest.TestCase):
    def test_sin_keys_es_na(self):
        resultados = v.validate_contract(_contrato(keys=()), _perfil())
        k = _por_codigo(resultados, "CONTRACT-KEY")
        self.assertEqual(k[0].status, "N/A")

    def test_keys_compuesta_siempre_warn(self):
        contrato = _contrato(
            fields=(_campo(name="a", type_family="string"), _campo(name="b", type_family="string")),
            keys=("a", "b"),
        )
        perfil = _perfil(
            schema={"a": "texto", "b": "texto"},
            columnas_detalle={"a": _col_texto(), "b": _col_texto()},
        )
        resultados = v.validate_contract(contrato, perfil)
        k = _por_codigo(resultados, "CONTRACT-KEY")
        self.assertEqual(k[0].status, "WARN")

    def test_key_simple_exacta_sin_duplicados_pass(self):
        contrato = _contrato(keys=("id",))
        perfil = _perfil(columnas_detalle={"id": _col_entera(unique_count=3, exactitud="exacta")}, filas=3)
        resultados = v.validate_contract(contrato, perfil)
        k = _por_codigo(resultados, "CONTRACT-KEY")
        self.assertEqual(k[0].status, "PASS")

    def test_key_simple_exacta_con_duplicados_fail(self):
        contrato = _contrato(keys=("id",))
        perfil = _perfil(columnas_detalle={"id": _col_entera(unique_count=2, exactitud="exacta")}, filas=3)
        resultados = v.validate_contract(contrato, perfil)
        k = _por_codigo(resultados, "CONTRACT-KEY")
        self.assertEqual(k[0].status, "FAIL")


# --- R10.1: not_null ------------------------------------------------------------------


class TestConstraintNotNull(unittest.TestCase):
    def test_field_none_es_na(self):
        contrato = _contrato(constraints=(_constraint(constraint_type="not_null", field=None),))
        resultados = v.validate_contract(contrato, _perfil())
        r = _por_codigo(resultados, "CONTRACT-NOT-NULL-EXPECTATION")
        self.assertEqual(r[0].status, "N/A")

    def test_field_presente_sin_nulos_pass(self):
        contrato = _contrato(constraints=(_constraint(constraint_type="not_null", field="id"),))
        resultados = v.validate_contract(contrato, _perfil())
        r = _por_codigo(resultados, "CONTRACT-NOT-NULL-EXPECTATION")
        self.assertEqual(r[0].status, "PASS")

    def test_field_con_nulos_usa_severidad_de_constraint(self):
        contrato = _contrato(
            constraints=(_constraint(constraint_type="not_null", field="id", severity="WARN"),)
        )
        perfil = _perfil(columnas_detalle={"id": _col_entera(nulos=2)})
        resultados = v.validate_contract(contrato, perfil)
        r = _por_codigo(resultados, "CONTRACT-NOT-NULL-EXPECTATION")
        self.assertEqual(r[0].status, "WARN")
        self.assertNotEqual(r[0].code, "CONTRACT-NULLABILITY")

    def test_field_ausente_del_perfil_es_warn(self):
        contrato = _contrato(
            fields=(_campo(name="id", required=False, nullable=True),),
            constraints=(_constraint(constraint_type="not_null", field="id"),),
        )
        perfil = _perfil(schema={}, columnas_detalle={})
        resultados = v.validate_contract(contrato, perfil)
        r = _por_codigo(resultados, "CONTRACT-NOT-NULL-EXPECTATION")
        self.assertEqual(r[0].status, "WARN")


# --- R10.2/R12: unique (los tres casos de exactitud + compuesta) --------------------


class TestConstraintUnique(unittest.TestCase):
    def test_exacta_sin_duplicados_pass(self):
        contrato = _contrato(constraints=(_constraint(constraint_type="unique", field="id"),))
        perfil = _perfil(columnas_detalle={"id": _col_entera(unique_count=3, exactitud="exacta")}, filas=3)
        resultados = v.validate_contract(contrato, perfil)
        r = _por_codigo(resultados, "CONTRACT-UNIQUENESS")
        self.assertEqual(r[0].status, "PASS")

    def test_exacta_con_duplicados_usa_severidad(self):
        contrato = _contrato(
            constraints=(_constraint(constraint_type="unique", field="id", severity="WARN"),)
        )
        perfil = _perfil(columnas_detalle={"id": _col_entera(unique_count=2, exactitud="exacta")}, filas=3)
        resultados = v.validate_contract(contrato, perfil)
        r = _por_codigo(resultados, "CONTRACT-UNIQUENESS")
        self.assertEqual(r[0].status, "WARN")

    def test_muestreada_sin_duplicado_observado_es_warn(self):
        contrato = _contrato(constraints=(_constraint(constraint_type="unique", field="id"),))
        col = _col_entera(
            unique_count=3,
            exactitud="muestreada",
            top_valores=[{"valor": "1", "frecuencia": 1}, {"valor": "2", "frecuencia": 1}],
        )
        perfil = _perfil(sampling_activo=True, tamano_muestra=3, columnas_detalle={"id": col})
        resultados = v.validate_contract(contrato, perfil)
        r = _por_codigo(resultados, "CONTRACT-UNIQUENESS")
        self.assertEqual(r[0].status, "WARN")

    def test_muestreada_con_duplicado_en_muestra_usa_severidad(self):
        contrato = _contrato(constraints=(_constraint(constraint_type="unique", field="id", severity="FAIL"),))
        col = _col_entera(
            unique_count=2,
            exactitud="muestreada",
            top_valores=[{"valor": "1", "frecuencia": 2}, {"valor": "2", "frecuencia": 1}],
        )
        perfil = _perfil(sampling_activo=True, tamano_muestra=3, columnas_detalle={"id": col})
        resultados = v.validate_contract(contrato, perfil)
        r = _por_codigo(resultados, "CONTRACT-UNIQUENESS")
        self.assertEqual(r[0].status, "FAIL")

    def test_unicidad_compuesta_siempre_warn(self):
        contrato = _contrato(
            fields=(_campo(name="a", type_family="string"), _campo(name="b", type_family="string")),
            constraints=(
                dc.Constraint(
                    constraint_id="c_comp",
                    constraint_type="unique",
                    field=None,
                    params={"fields": ["a", "b"]},
                ),
            ),
        )
        perfil = _perfil(
            schema={"a": "texto", "b": "texto"},
            columnas_detalle={"a": _col_texto(), "b": _col_texto()},
        )
        resultados = v.validate_contract(contrato, perfil)
        r = _por_codigo(resultados, "CONTRACT-UNIQUENESS")
        self.assertEqual(r[0].status, "WARN")


# --- R10.3: allowed_values -------------------------------------------------------------


class TestConstraintAllowedValues(unittest.TestCase):
    def test_field_none_es_na(self):
        contrato = _contrato(
            constraints=(
                dc.Constraint(
                    constraint_id="c1", constraint_type="allowed_values", field=None, params={"values": ["a"]}
                ),
            )
        )
        resultados = v.validate_contract(contrato, _perfil())
        r = _por_codigo(resultados, "CONTRACT-DOMAIN")
        self.assertEqual(r[0].status, "N/A")

    def test_valor_fuera_de_dominio_usa_severidad(self):
        contrato = _contrato(
            fields=(_campo(name="c", type_family="string"),),
            constraints=(
                dc.Constraint(
                    constraint_id="c1",
                    constraint_type="allowed_values",
                    field="c",
                    params={"values": ["a", "b"]},
                    severity="FAIL",
                ),
            ),
        )
        perfil = _perfil(schema={"c": "texto"}, columnas_detalle={"c": _col_texto(top_valores=[{"valor": "z", "frecuencia": 1}])})
        resultados = v.validate_contract(contrato, perfil)
        r = _por_codigo(resultados, "CONTRACT-DOMAIN")
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0].status, "FAIL")

    def test_dominio_exhaustivo_exacto_es_pass(self):
        contrato = _contrato(
            fields=(_campo(name="c", type_family="string"),),
            constraints=(
                dc.Constraint(
                    constraint_id="c1", constraint_type="allowed_values", field="c", params={"values": ["a"]}
                ),
            ),
        )
        col = _col_texto(unique_count=1, exactitud="exacta", top_valores=[{"valor": "a", "frecuencia": 3}])
        perfil = _perfil(schema={"c": "texto"}, columnas_detalle={"c": col})
        resultados = v.validate_contract(contrato, perfil)
        r = _por_codigo(resultados, "CONTRACT-DOMAIN")
        self.assertEqual(r[0].status, "PASS")

    def test_dominio_no_exhaustivo_es_warn(self):
        contrato = _contrato(
            fields=(_campo(name="c", type_family="string"),),
            constraints=(
                dc.Constraint(
                    constraint_id="c1", constraint_type="allowed_values", field="c", params={"values": ["a"]}
                ),
            ),
        )
        col = _col_texto(unique_count=1, exactitud="muestreada", top_valores=[{"valor": "a", "frecuencia": 3}])
        perfil = _perfil(schema={"c": "texto"}, columnas_detalle={"c": col}, sampling_activo=True, tamano_muestra=3)
        resultados = v.validate_contract(contrato, perfil)
        r = _por_codigo(resultados, "CONTRACT-DOMAIN")
        self.assertEqual(r[0].status, "WARN")


# --- R10.4: min_value / max_value, deterministas bajo sampling ----------------------


class TestConstraintMinMaxValue(unittest.TestCase):
    def test_dtype_no_numerico_es_na(self):
        contrato = _contrato(
            fields=(_campo(name="c", type_family="string"),),
            constraints=(
                dc.Constraint(constraint_id="c1", constraint_type="min_value", field="c", params={"value": 1}),
            ),
        )
        perfil = _perfil(schema={"c": "texto"}, columnas_detalle={"c": _col_texto()})
        resultados = v.validate_contract(contrato, perfil)
        r = _por_codigo(resultados, "CONTRACT-RANGE")
        self.assertEqual(r[0].status, "N/A")

    def test_min_value_viola_es_fail_determinista_bajo_muestreo(self):
        contrato = _contrato(
            constraints=(
                dc.Constraint(
                    constraint_id="c1", constraint_type="min_value", field="id", params={"value": 10}, severity="FAIL"
                ),
            )
        )
        perfil = _perfil(sampling_activo=True, tamano_muestra=100, columnas_detalle={"id": _col_entera(minimo=5, maximo=20)})
        resultados = v.validate_contract(contrato, perfil)
        r = _por_codigo(resultados, "CONTRACT-RANGE")
        self.assertEqual(r[0].status, "FAIL")

    def test_max_value_no_viola_es_pass(self):
        contrato = _contrato(
            constraints=(
                dc.Constraint(constraint_id="c1", constraint_type="max_value", field="id", params={"value": 100}),
            )
        )
        perfil = _perfil(columnas_detalle={"id": _col_entera(minimo=1, maximo=20)})
        resultados = v.validate_contract(contrato, perfil)
        r = _por_codigo(resultados, "CONTRACT-RANGE")
        self.assertEqual(r[0].status, "PASS")


# --- R10.5: min_length / max_length, siempre WARN -------------------------------------


class TestConstraintLength(unittest.TestCase):
    def test_min_length_siempre_warn(self):
        contrato = _contrato(
            constraints=(
                dc.Constraint(constraint_id="c1", constraint_type="min_length", field="id", params={"value": 3}),
            )
        )
        resultados = v.validate_contract(contrato, _perfil())
        r = _por_codigo(resultados, "CONTRACT-LENGTH")
        self.assertEqual(r[0].status, "WARN")

    def test_max_length_siempre_warn(self):
        contrato = _contrato(
            constraints=(
                dc.Constraint(constraint_id="c1", constraint_type="max_length", field="id", params={"value": 3}),
            )
        )
        resultados = v.validate_contract(contrato, _perfil())
        r = _por_codigo(resultados, "CONTRACT-LENGTH")
        self.assertEqual(r[0].status, "WARN")


# --- R10.6: date_min / date_max --------------------------------------------------------


class TestConstraintDateMinMax(unittest.TestCase):
    def _contrato_fecha(self, **kw_constraint):
        base = dict(constraint_id="c1", constraint_type="date_min", field="f", params={"value": "2020-01-01"})
        base.update(kw_constraint)
        return _contrato(fields=(_campo(name="f", type_family="date"),), constraints=(dc.Constraint(**base),))

    def test_dtype_no_fecha_es_na(self):
        contrato = self._contrato_fecha()
        perfil = _perfil(schema={"f": "texto"}, columnas_detalle={"f": _col_texto()})
        resultados = v.validate_contract(contrato, perfil)
        r = _por_codigo(resultados, "CONTRACT-DATE-RANGE")
        self.assertEqual(r[0].status, "N/A")

    def test_valor_declarado_no_parseable_es_warn(self):
        contrato = self._contrato_fecha(params={"value": "no-es-fecha"})
        perfil = _perfil(schema={"f": "fecha"}, columnas_detalle={"f": _col_fecha()})
        resultados = v.validate_contract(contrato, perfil)
        r = _por_codigo(resultados, "CONTRACT-DATE-RANGE")
        self.assertEqual(r[0].status, "WARN")

    def test_date_min_viola_usa_severidad(self):
        contrato = self._contrato_fecha(params={"value": "2020-01-01"}, severity="FAIL")
        perfil = _perfil(
            schema={"f": "fecha"},
            columnas_detalle={"f": _col_fecha(fecha_min="2019-01-01T00:00:00", fecha_max="2024-01-01T00:00:00")},
        )
        resultados = v.validate_contract(contrato, perfil)
        r = _por_codigo(resultados, "CONTRACT-DATE-RANGE")
        self.assertEqual(r[0].status, "FAIL")

    def test_date_min_no_viola_es_pass(self):
        contrato = self._contrato_fecha(params={"value": "2018-01-01"})
        perfil = _perfil(
            schema={"f": "fecha"},
            columnas_detalle={"f": _col_fecha(fecha_min="2019-01-01T00:00:00", fecha_max="2024-01-01T00:00:00")},
        )
        resultados = v.validate_contract(contrato, perfil)
        r = _por_codigo(resultados, "CONTRACT-DATE-RANGE")
        self.assertEqual(r[0].status, "PASS")


# --- R10.7: invariant, siempre WARN -----------------------------------------------------


class TestConstraintInvariant(unittest.TestCase):
    def test_invariant_siempre_warn(self):
        contrato = _contrato(
            constraints=(
                dc.Constraint(constraint_id="c1", constraint_type="invariant", params={"note": "algo"}),
            )
        )
        resultados = v.validate_contract(contrato, _perfil())
        r = _por_codigo(resultados, "CONTRACT-INVARIANT")
        self.assertEqual(r[0].status, "WARN")


# --- R12: nunca PASS por falta de evidencia --------------------------------------------


class TestNuncaPassPorFaltaDeEvidencia(unittest.TestCase):
    def test_matriz_muestreado_sin_evidencia_nunca_pass(self):
        casos = []

        contrato_unique = _contrato(constraints=(_constraint(constraint_type="unique", field="id"),))
        col_unique = _col_entera(
            unique_count=3,
            exactitud="muestreada",
            top_valores=[{"valor": "1", "frecuencia": 1}, {"valor": "2", "frecuencia": 1}],
        )
        perfil_unique = _perfil(sampling_activo=True, tamano_muestra=3, columnas_detalle={"id": col_unique})
        casos.append((contrato_unique, perfil_unique, "CONTRACT-UNIQUENESS"))

        contrato_av = _contrato(
            fields=(_campo(name="c", type_family="string"),),
            constraints=(
                dc.Constraint(
                    constraint_id="c1", constraint_type="allowed_values", field="c", params={"values": ["a"]}
                ),
            ),
        )
        col_av = _col_texto(unique_count=1, exactitud="muestreada", top_valores=[{"valor": "a", "frecuencia": 1}])
        perfil_av = _perfil(schema={"c": "texto"}, columnas_detalle={"c": col_av}, sampling_activo=True, tamano_muestra=3)
        casos.append((contrato_av, perfil_av, "CONTRACT-DOMAIN"))

        for contrato, perfil, codigo in casos:
            resultados = v.validate_contract(contrato, perfil)
            for r in _por_codigo(resultados, codigo):
                self.assertNotEqual(r.status, "PASS")


# --- R13: kind technical_error solo en INPUT/EVIDENCE-MISSING/*-EXCEPCION -----------


class TestKindTechnicalError(unittest.TestCase):
    def test_solo_input_y_evidence_missing_son_technical_error(self):
        resultados = v.validate_contract(_contrato(), _perfil())
        for r in resultados:
            if r.code in ("CONTRACT-INPUT", "CONTRACT-EVIDENCE-MISSING") or r.code.endswith("-EXCEPCION"):
                self.assertEqual(r.kind, "technical_error")
            else:
                self.assertEqual(r.kind, "check")


# --- R14: privacidad ------------------------------------------------------------------


class TestPrivacidad(unittest.TestCase):
    def test_dataset_path_nunca_aparece_en_ningun_resultado(self):
        perfil = _perfil()
        perfil["dataset_path"] = "C:\\Users\\alguien\\datos_privados.csv"
        contrato = _contrato(
            fields=(_campo(name="id"), _campo(name="extra_no_declarado", required=False)),
            constraints=(_constraint(constraint_type="not_null", field="id"),),
        )
        perfil["schema"]["otra_no_declarada"] = "texto"
        perfil["columnas_detalle"]["otra_no_declarada"] = _col_texto()
        resultados = v.validate_contract(contrato, perfil)
        for r in resultados:
            for texto in (r.message, r.detail, r.subject):
                if texto:
                    self.assertNotIn("datos_privados", texto)
                    self.assertNotIn("C:\\Users", texto)


# --- R3: excepción inesperada -> technical_error, sin propagar ----------------------


class TestExcepcionInesperada(unittest.TestCase):
    def test_excepcion_en_una_regla_no_propaga_y_sigue_evaluando(self):
        with mock.patch.object(v, "_regla_field_missing", side_effect=RuntimeError("boom")):
            resultados = v.validate_contract(_contrato(), _perfil())
        codigos = _codigos(resultados)
        self.assertIn("CONTRACT-FIELD-MISSING-EXCEPCION", codigos)
        exc = _por_codigo(resultados, "CONTRACT-FIELD-MISSING-EXCEPCION")[0]
        self.assertEqual(exc.status, "FAIL")
        self.assertEqual(exc.kind, "technical_error")
        # El resto de las reglas siguió evaluándose (no se cortó la ejecución).
        self.assertIn("CONTRACT-NULLABILITY", codigos)
        self.assertIn("CONTRACT-KEY", codigos)


# --- R4: validate_contract_against_profile_file --------------------------------------


class TestValidateContractAgainstProfileFile(unittest.TestCase):
    def test_holdout_denegado_nunca_abre_el_archivo(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            ruta_perfil = repo_root / "profile.json"
            ruta_perfil.write_text(json.dumps(_perfil()), encoding="utf-8")

            with mock.patch.object(v, "verificar_permitido", return_value=(False, "denegado de prueba")):
                with mock.patch.object(Path, "read_bytes", side_effect=AssertionError("no debía abrirse")):
                    resultados = v.validate_contract_against_profile_file(_contrato(), ruta_perfil, repo_root)

        self.assertEqual(len(resultados), 1)
        r = resultados[0]
        self.assertEqual(r.code, "CONTRACT-EVIDENCE-MISSING")
        self.assertEqual(r.kind, "technical_error")
        self.assertEqual(r.detail, "denegado de prueba")

    def test_ruta_no_resoluble_produce_evidence_missing_con_motivo_del_guard(self):
        # Ejercita la rama real de `holdout_guard.verificar_permitido` ->
        # `_es_ruta_no_resoluble` (sin mockear `verificar_permitido`, a diferencia de
        # los demás tests de esta clase): mismo patrón que
        # `tools/ds_profile/tests/test_holdout_guard.py::test_ruta_no_resoluble_deniega_fail_closed`
        # -- `Path.resolve` lanza `OSError` para forzar "no se pudo resolver" (distinto
        # de "genuinamente fuera del repo"), lo que `holdout_guard` trata fail-closed.
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            ruta_perfil = repo_root / "cualquier.json"
            with mock.patch.object(Path, "resolve", side_effect=OSError("resolución falló")):
                with mock.patch.object(Path, "read_bytes", side_effect=AssertionError("no debía abrirse")):
                    resultados = v.validate_contract_against_profile_file(_contrato(), ruta_perfil, repo_root)

        self.assertEqual(len(resultados), 1)
        r = resultados[0]
        self.assertEqual(r.code, "CONTRACT-EVIDENCE-MISSING")
        self.assertEqual(r.status, "FAIL")
        self.assertEqual(r.kind, "technical_error")
        self.assertIsNotNone(r.detail)
        self.assertIn("no resoluble", r.detail.lower())
        self.assertIn("fail-closed", r.detail.lower())

    def test_ruta_inexistente_produce_evidence_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            ruta_perfil = repo_root / "no_existe" / "profile.json"
            with mock.patch.object(v, "verificar_permitido", return_value=(True, "ok")):
                resultados = v.validate_contract_against_profile_file(_contrato(), ruta_perfil, repo_root)
        self.assertEqual(len(resultados), 1)
        self.assertEqual(resultados[0].code, "CONTRACT-EVIDENCE-MISSING")

    def test_json_invalido_produce_evidence_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            ruta_perfil = repo_root / "profile.json"
            ruta_perfil.write_text("{ no es json valido", encoding="utf-8")
            with mock.patch.object(v, "verificar_permitido", return_value=(True, "ok")):
                resultados = v.validate_contract_against_profile_file(_contrato(), ruta_perfil, repo_root)
        self.assertEqual(len(resultados), 1)
        self.assertEqual(resultados[0].code, "CONTRACT-EVIDENCE-MISSING")

    def test_json_valido_no_dict_produce_evidence_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            ruta_perfil = repo_root / "profile.json"
            ruta_perfil.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
            with mock.patch.object(v, "verificar_permitido", return_value=(True, "ok")):
                resultados = v.validate_contract_against_profile_file(_contrato(), ruta_perfil, repo_root)
        self.assertEqual(len(resultados), 1)
        self.assertEqual(resultados[0].code, "CONTRACT-EVIDENCE-MISSING")

    def test_perfil_valido_y_permitido_igual_a_validate_contract_directo(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            ruta_perfil = repo_root / "profile.json"
            perfil = _perfil()
            ruta_perfil.write_text(json.dumps(perfil), encoding="utf-8")
            with mock.patch.object(v, "verificar_permitido", return_value=(True, "ok")):
                resultados_archivo = v.validate_contract_against_profile_file(_contrato(), ruta_perfil, repo_root)
        resultados_directo = v.validate_contract(_contrato(), json.loads(json.dumps(perfil)))
        self.assertEqual(
            [(r.status, r.code, r.message, r.subject) for r in resultados_archivo],
            [(r.status, r.code, r.message, r.subject) for r in resultados_directo],
        )


if __name__ == "__main__":
    unittest.main()

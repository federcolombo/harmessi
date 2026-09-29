"""Matriz de tests del evaluador NATIVO sobre `SourceObservation` (R29/R30/R31 de
`openspec/changes/20260928-source-neutral-data-access/spec.md`, T5 del Change 1 de
v0.8). `SourceObservation`/`FieldObservation`/`SourceProvenance` se arman A MANO acá
(sin `profile_bridge`, sin `profile.json` legacy) para poder representar escenarios que
`ds_profile` nunca produce por sí solo -- en particular, facetas de columna AUSENTES
(distintas de "presentes con valor 0/vacío"), que es justo el punto central de R30/R31.

`validate_contract_observation` usa wording NEUTRAL por defecto (no se pasa `wording`).
"""
from __future__ import annotations

import unittest

from dsguard import checks
from tools.datacontracts import validation as v
from tools.datacontracts.tests.test_validation import _campo, _constraint, _contrato
from datasources import core as ds_core


# --- Helpers locales de construcción de SourceObservation ---------------------------


def _provenance(source_id="fuente-test", **overrides) -> ds_core.SourceProvenance:
    base = dict(
        source_id=source_id,
        observer_id="tests.test_observation_native:observer_ficticio",
        observer_code_sha256=None,
        access_mode="read",
        source_kind=None,
        generated_at="2026-01-01T00:00:00",
    )
    base.update(overrides)
    return ds_core.SourceProvenance(**base)


def _campo_obs(name, type_family="integer", native_type="entero", facets=None) -> ds_core.FieldObservation:
    return ds_core.FieldObservation(
        name=name, type_family=type_family, native_type=native_type, facets=facets or {}
    )


def _observacion(fields, source_id="fuente-test", dataset=None) -> ds_core.SourceObservation:
    return ds_core.SourceObservation(
        source_id=source_id,
        provenance=_provenance(source_id=source_id),
        dataset=dataset or {},
        fields=tuple(fields),
    )


def _faceta_conteo(value, exactness="exact") -> dict:
    return {"value": value, "exactness": exactness}


def _faceta_rango(minimo, maximo, exactness="exact") -> dict:
    return {"value": {"min": minimo, "max": maximo}, "exactness": exactness}


def _faceta_distribucion(items, exactness="exact", complete=False) -> dict:
    return {"value": items, "exactness": exactness, "complete": complete}


def _por_codigo(resultados, codigo):
    return [r for r in resultados if r.code == codigo]


# --- Tests ----------------------------------------------------------------------------


class TestFacetaAusenteNuncaEsPass(unittest.TestCase):
    """R30: una faceta AUSENTE (distinta de "presente con valor 0/vacío") nunca debe
    sustentar un PASS."""

    def test_null_count_ausente_con_nullable_false_nunca_pass(self):
        contrato = _contrato(fields=(_campo(name="id", type_family="integer", required=True, nullable=False),))
        observacion = _observacion([_campo_obs("id", facets={})])  # sin "null_count"
        resultados = v.validate_contract_observation(contrato, observacion)
        nullability = _por_codigo(resultados, v.CODE_NULLABILITY)
        self.assertEqual(len(nullability), 1)
        self.assertEqual(nullability[0].status, checks.STATUS_WARN)
        self.assertNotEqual(nullability[0].status, checks.STATUS_PASS)

    def test_null_count_presente_con_valor_cero_puede_dar_pass(self):
        # Distingue "ausente" de "cero" (presente): con la faceta presente y count=0,
        # SÍ hay evidencia real de "sin nulos observados".
        contrato = _contrato(fields=(_campo(name="id", type_family="integer", required=True, nullable=False),))
        observacion = _observacion(
            [_campo_obs("id", facets={"null_count": _faceta_conteo(0)})]
        )
        resultados = v.validate_contract_observation(contrato, observacion)
        nullability = _por_codigo(resultados, v.CODE_NULLABILITY)
        self.assertEqual(len(nullability), 1)
        self.assertEqual(nullability[0].status, checks.STATUS_PASS)

    def test_value_range_observado_y_vacio_da_pass_nunca_warn(self):
        # R31: {min: None, max: None} EXACT es evidencia real (se observó la columna,
        # no hay valores no-nulos que violen) -> PASS, nunca WARN.
        contrato = _contrato(
            fields=(_campo(name="num", type_family="integer", required=True, nullable=True),),
            constraints=(
                _constraint(
                    constraint_type="min_value", field="num", constraint_id="c_min", params={"value": 0}
                ),
            ),
        )
        observacion = _observacion(
            [
                _campo_obs(
                    "num",
                    facets={"value_range": _faceta_rango(None, None, exactness="exact")},
                )
            ]
        )
        resultados = v.validate_contract_observation(contrato, observacion)
        rango = _por_codigo(resultados, v.CODE_RANGE)
        self.assertEqual(len(rango), 1)
        self.assertEqual(rango[0].status, checks.STATUS_PASS)
        self.assertNotEqual(rango[0].status, checks.STATUS_WARN)

    def test_value_range_ausente_da_warn_nunca_pass(self):
        contrato = _contrato(
            fields=(_campo(name="num", type_family="integer", required=True, nullable=True),),
            constraints=(
                _constraint(
                    constraint_type="min_value", field="num", constraint_id="c_min", params={"value": 0}
                ),
            ),
        )
        observacion = _observacion([_campo_obs("num", facets={})])  # sin "value_range"
        resultados = v.validate_contract_observation(contrato, observacion)
        rango = _por_codigo(resultados, v.CODE_RANGE)
        self.assertEqual(len(rango), 1)
        self.assertEqual(rango[0].status, checks.STATUS_WARN)
        self.assertNotEqual(rango[0].status, checks.STATUS_PASS)


class TestDistinctCountAproximado(unittest.TestCase):
    """R30: `distinct_count`/`value_distribution` con `exactness="approximate"` --
    misma asimetría violación-vs-cumplimiento que v0.7 bajo muestreo (frecuencia > 1
    SÍ es evidencia real de duplicado; ausencia de duplicado en la muestra NUNCA es
    evidencia de cumplimiento)."""

    def test_frecuencia_mayor_a_uno_aproximada_es_violacion_de_unique(self):
        contrato = _contrato(
            fields=(_campo(name="c", type_family="string", required=True, nullable=True),),
            constraints=(_constraint(constraint_type="unique", field="c", constraint_id="c_uniq"),),
        )
        observacion = _observacion(
            [
                _campo_obs(
                    "c",
                    type_family="string",
                    native_type="texto",
                    facets={
                        "distinct_count": _faceta_conteo(2, exactness="approximate"),
                        "value_distribution": _faceta_distribucion(
                            [{"value": "a", "frequency": 2}, {"value": "b", "frequency": 1}],
                            exactness="approximate",
                        ),
                    },
                )
            ]
        )
        resultados = v.validate_contract_observation(contrato, observacion)
        unicidad = _por_codigo(resultados, v.CODE_UNIQUENESS)
        self.assertEqual(len(unicidad), 1)
        # severidad default de Constraint es FAIL (ver core.py); evidencia real pese a
        # ser approximate, así que la violación SÍ se emite.
        self.assertEqual(unicidad[0].status, checks.STATUS_FAIL)
        self.assertEqual(unicidad[0].subject, "c")

    def test_sin_duplicados_en_muestra_aproximada_es_warn_no_verificable_nunca_pass(self):
        contrato = _contrato(
            fields=(_campo(name="c", type_family="string", required=True, nullable=True),),
            constraints=(_constraint(constraint_type="unique", field="c", constraint_id="c_uniq"),),
        )
        observacion = _observacion(
            [
                _campo_obs(
                    "c",
                    type_family="string",
                    native_type="texto",
                    facets={
                        "distinct_count": _faceta_conteo(2, exactness="approximate"),
                        "value_distribution": _faceta_distribucion(
                            [{"value": "a", "frequency": 1}, {"value": "b", "frequency": 1}],
                            exactness="approximate",
                        ),
                    },
                )
            ]
        )
        resultados = v.validate_contract_observation(contrato, observacion)
        unicidad = _por_codigo(resultados, v.CODE_UNIQUENESS)
        self.assertEqual(len(unicidad), 1)
        self.assertEqual(unicidad[0].status, checks.STATUS_WARN)
        self.assertNotEqual(unicidad[0].status, checks.STATUS_PASS)


class TestTypeFamilyUnknown(unittest.TestCase):
    """Un campo `type_family="unknown"` se trata igual que v0.7 trata un dtype no
    reconocido en `_regla_type_mismatch` -- verificado contra el comportamiento real
    (ver docstring nota 1 de `validation.py`: los campos "unknown" quedan absorbidos
    en el agregado N/A, no generan una entrada propia)."""

    def test_campo_unknown_unico_da_type_mismatch_na(self):
        contrato = _contrato(fields=(_campo(name="x", type_family="unknown", required=True, nullable=True),))
        observacion = _observacion(
            [_campo_obs("x", type_family="unknown", native_type="tipo_desconocido_del_origen", facets={})]
        )
        resultados = v.validate_contract_observation(contrato, observacion)
        mismatch = _por_codigo(resultados, v.CODE_TYPE_MISMATCH)
        self.assertEqual(len(mismatch), 1)
        self.assertEqual(mismatch[0].status, checks.STATUS_NA)


class TestTypeFamilyEsLaAutoridadNoNativeType(unittest.TestCase):
    """Bug real encontrado por el Lead vía el test de CLI del Change 1 de v0.8 (T6):
    `_observation_como_profile_like` reconstruía `dtype_legacy` desde `native_type` en
    vez de `type_family`, así que una observación NATIVA (no venida del bridge) con un
    `native_type` no-legacy (p. ej. `"int64"` de una API) daba FAIL de tipo aunque
    `type_family` coincidiera exactamente con lo declarado por el contrato. Corregido:
    la reconstrucción deriva de `type_family` (el campo neutral, autoridad real)."""

    def test_type_family_coincide_aunque_native_type_no_sea_legacy(self):
        contrato = _contrato(fields=(_campo(name="id", type_family="integer", required=True, nullable=True),))
        observacion = _observacion(
            [_campo_obs("id", type_family="integer", native_type="int64", facets={})]
        )
        resultados = v.validate_contract_observation(contrato, observacion)
        mismatch = _por_codigo(resultados, v.CODE_TYPE_MISMATCH)
        self.assertEqual(len(mismatch), 1)
        self.assertEqual(mismatch[0].status, checks.STATUS_PASS)

    def test_type_family_no_coincide_sigue_dando_fail(self):
        # Regression guard: el fix no vuelve la regla permisiva en general -- si el
        # type_family de la observación realmente no coincide con el del contrato,
        # sigue siendo FAIL, sin importar qué diga native_type.
        contrato = _contrato(fields=(_campo(name="id", type_family="integer", required=True, nullable=True),))
        observacion = _observacion(
            [_campo_obs("id", type_family="string", native_type="int64", facets={})]
        )
        resultados = v.validate_contract_observation(contrato, observacion)
        mismatch = _por_codigo(resultados, v.CODE_TYPE_MISMATCH)
        self.assertEqual(len(mismatch), 1)
        self.assertEqual(mismatch[0].status, checks.STATUS_FAIL)


if __name__ == "__main__":
    unittest.main()

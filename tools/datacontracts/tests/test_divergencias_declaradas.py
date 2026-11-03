"""Los 3 casos de divergencia declarados EXACTAMENTE en `design.md`/`spec.md` (R35) del
Change 1 de v0.8, ya implementados por el refactor de `validation.py`
(`_demotar_pass_sin_evidencia`, comportamiento agregado de `_regla_type_mismatch` para
`type_family="unknown"`).
"""
from __future__ import annotations

import unittest

from dsguard import checks
from tools.datacontracts import validation as v
from tools.datacontracts.tests.test_validation import _campo, _constraint, _contrato
from tools.datacontracts.tests.test_observation_native import _campo_obs, _observacion
from datasources import core as ds_core  # noqa: F401 (usado implícitamente vía helpers)


def _por_codigo(resultados, codigo):
    return [r for r in resultados if r.code == codigo]


class TestCasoA_FacetasDeColumnaAusentes(unittest.TestCase):
    """(a) Observación con facetas de columna ausentes (`null_count`, `distinct_count`,
    `value_range` -- las 3 AUSENTES, ninguna a 0/vacía) para un campo presente en el
    contrato -> cada regla aplicable da WARN, nunca PASS ni FAIL.

    Contraste con v0.7: con un `profile.json` INCOMPLETO equivalente (columna sin las
    claves `nulls`/`unique`/`min`/`max` en `columnas_detalle`), el `profile` ya no
    cumpliría la forma mínima que exige `columnas_detalle[nombre]` en cada `_regla_*`
    (`.get(...)` devolvería `{}`/`None` de la misma manera) -- v0.7 NUNCA podía producir
    ese perfil parcial desde `ds_profile.run` real (siempre trae esas claves si la
    columna existe), así que esta asimetría era practicamente inalcanzable en v0.7 pese
    a que el código ya la manejaba igual (mismos `.get()` con default). Una
    `SourceObservation` armada por un observer nuevo SÍ puede omitir facetas
    legítimamente (p. ej. si el observer no soporta `value_range` para ese tipo de
    columna), por eso R30 exige la democión explícita a WARN implementada en
    `_demotar_pass_sin_evidencia`."""

    def test_todas_las_reglas_aplicables_dan_warn_nunca_pass_ni_fail(self):
        contrato = _contrato(
            fields=(_campo(name="col", type_family="integer", required=True, nullable=False),),
            constraints=(
                _constraint(constraint_type="not_null", field="col", constraint_id="c_nn"),
                _constraint(constraint_type="unique", field="col", constraint_id="c_uniq"),
                _constraint(constraint_type="min_value", field="col", constraint_id="c_min", params={"value": 0}),
            ),
        )
        observacion = _observacion([_campo_obs("col", facets={})])  # sin null_count/distinct_count/value_range
        resultados = v.validate_contract_observation(contrato, observacion)

        codigos_aplicables = (
            v.CODE_NULLABILITY,
            v.CODE_NOT_NULL_EXPECTATION,
            v.CODE_UNIQUENESS,
            v.CODE_RANGE,
        )
        for codigo in codigos_aplicables:
            with self.subTest(codigo=codigo):
                entradas = _por_codigo(resultados, codigo)
                self.assertEqual(len(entradas), 1, f"se esperaba exactamente 1 entrada para {codigo!r}")
                self.assertEqual(entradas[0].status, checks.STATUS_WARN)
                self.assertNotIn(entradas[0].status, (checks.STATUS_PASS, checks.STATUS_FAIL))


class TestCasoB_TypeFamilyFueraDeVocabulario(unittest.TestCase):
    """(b) Campo con `type_family` fuera de los 7 valores válidos.

    `datasources.core.FieldObservation.__post_init__` valida `type_family` contra
    `OBSERVED_TYPE_FAMILIES` y RECHAZA cualquier valor fuera de ese vocabulario
    (`SourceError(CODE_OBSERVATION_INVALID, ...)`) -- no es posible construir una
    `FieldObservation` con un `type_family` inválido para reproducir ese caso
    literalmente. Caso real alcanzable, documentado por el propio pedido de tarea:
    `type_family="unknown"` con `native_type` de un dtype no reconocido del origen
    (equivalente al "dtype fuera de las 5 familias legacy" que v0.7 trataba como FAIL
    de `CONTRACT-TYPE-MISMATCH` cuando era el único campo evaluable).

    SORPRESA respecto de lo esperado por el pedido de tarea (reportado, no ocultado):
    el comportamiento REAL de `_regla_type_mismatch` (sin tocar por este Change,
    ver nota 1 del docstring del módulo) para un campo `type_family="unknown"` ÚNICO no
    es WARN "no clasificable" -- es **N/A** ("Ningún campo evaluable declara una
    type_family con mapeo de dtype (unknown)."), agregada, exactamente como v0.7 ya
    trataba cualquier `type_family="unknown"` desde antes de este Change (ver
    `_regla_type_mismatch`, rama `hubo_na`). No hay WARN en absoluto para este código en
    este escenario; y no hay FAIL como daría v0.7 para un dtype legacy REALMENTE no
    reconocido (`_DTYPE_ESPERADO_POR_FAMILIA` solo se consulta para `type_family`
    mapeadas -- `"unknown"` nunca llega a comparar dtype, se salta directo a la rama
    N/A). Este test verifica el resultado REAL, no el WARN originalmente esperado."""

    def test_campo_unico_type_family_unknown_da_na_no_warn_no_fail(self):
        contrato = _contrato(fields=(_campo(name="x", type_family="unknown", required=True, nullable=True),))
        observacion = _observacion(
            [_campo_obs("x", type_family="unknown", native_type="dtype_no_reconocido_del_origen", facets={})]
        )
        resultados = v.validate_contract_observation(contrato, observacion)
        mismatch = _por_codigo(resultados, v.CODE_TYPE_MISMATCH)
        self.assertEqual(len(mismatch), 1)
        self.assertEqual(mismatch[0].status, checks.STATUS_NA)
        self.assertNotIn(mismatch[0].status, (checks.STATUS_WARN, checks.STATUS_FAIL))


class TestCasoC_CampoSinNingunaFaceta(unittest.TestCase):
    """(c) Campo presente en el contrato pero con la observación sin ninguna faceta en
    absoluto para ese campo (`facets={}`) -> mismo criterio que (a): WARN en todo lo
    aplicable. Variación con otro tipo de campo/constraints (string + not_null/unique/
    allowed_values) para no ser una copia literal del caso (a) y cubrir también
    `CONTRACT-DOMAIN`."""

    def test_string_sin_facetas_da_warn_en_todo_lo_aplicable(self):
        contrato = _contrato(
            fields=(_campo(name="etiqueta", type_family="string", required=True, nullable=False),),
            constraints=(
                _constraint(constraint_type="not_null", field="etiqueta", constraint_id="c_nn2"),
                _constraint(constraint_type="unique", field="etiqueta", constraint_id="c_uniq2"),
                _constraint(
                    constraint_type="allowed_values",
                    field="etiqueta",
                    constraint_id="c_dom",
                    params={"values": ["a", "b"]},
                ),
            ),
        )
        observacion = _observacion(
            [_campo_obs("etiqueta", type_family="string", native_type="texto", facets={})]
        )
        resultados = v.validate_contract_observation(contrato, observacion)

        codigos_aplicables = (
            v.CODE_NULLABILITY,
            v.CODE_NOT_NULL_EXPECTATION,
            v.CODE_UNIQUENESS,
            v.CODE_DOMAIN,
        )
        for codigo in codigos_aplicables:
            with self.subTest(codigo=codigo):
                entradas = _por_codigo(resultados, codigo)
                self.assertEqual(len(entradas), 1, f"se esperaba exactamente 1 entrada para {codigo!r}")
                self.assertEqual(entradas[0].status, checks.STATUS_WARN)
                self.assertNotIn(entradas[0].status, (checks.STATUS_PASS, checks.STATUS_FAIL))


if __name__ == "__main__":
    unittest.main()

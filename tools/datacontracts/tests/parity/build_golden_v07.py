"""Script one-shot (T0.1, Change 1 de v0.8, SDD APROBADO
`openspec/changes/20260928-source-neutral-data-access/`, R34/R35 de `spec.md`, D12 de
`design.md`).

Corre el evaluador v0.7 ACTUAL (`tools.datacontracts.validation.validate_contract`, sin
tocar) sobre un corpus determinista de pares `(DataContract, profile_dict)` y escribe
`golden_v07_validation.json` junto a este script. Ese archivo es la foto de referencia
contra la que una implementación futura (fuente-neutral, Change 1+) debe mantener
paridad -- este script y su output deben existir ANTES de que cualquier otra
invocación toque `tools/datacontracts/validation.py`.

El corpus tiene dos partes:

A) Reconstrucción de TODOS los casos de `tools/datacontracts/tests/test_validation.py`
   que llaman a `v.validate_contract(contrato, perfil)` -- mismos helpers de fixtures
   (`_campo`/`_version`/`_contrato`/`_constraint`/`_col_entera`/`_col_texto`/`_col_fecha`/
   `_perfil`), copiados acá para que este script no dependa de que `tests/` sea
   importable como paquete instalado (es dev-only, se ejecuta desde este repo).

   Casos de `test_validation.py` deliberadamente EXCLUIDOS del golden (con motivo):

   - `TestRegistroDeCodigos.*` (2 métodos): no llaman a `validate_contract` en absoluto
     -- solo verifican la constante `v.CODES`. No hay nada que reconstruir.
   - `TestExcepcionInesperada.test_excepcion_en_una_regla_no_propaga_y_sigue_evaluando`:
     usa `unittest.mock.patch.object(v, "_regla_field_missing", side_effect=RuntimeError)`
     para forzar una excepción interna. No es una variación de `(contrato, perfil)`
     reconstruible con los helpers de fixtures -- es un test del mecanismo de
     contención de excepciones de `_ejecutar`, no del comportamiento de evaluación
     frente a evidencia real. Reproducirlo exigiría `unittest.mock` (fuera de la lista
     de dependencias permitidas para este script) y monkeypatchear el propio módulo
     bajo prueba, lo cual no tiene sentido como "foto de referencia" de
     `validate_contract` ante entradas legítimas.
   - `TestValidateContractAgainstProfileFile.*` (6 métodos): ejercitan
     `validate_contract_against_profile_file` (la puerta CON I/O: holdout_guard,
     lectura de archivo, `json.loads`), no la función pura `validate_contract` que es
     el objetivo de este golden (R34/R35 hablan de paridad del evaluador puro). El
     único método de esa clase que además compara contra `validate_contract` directo
     (`test_perfil_valido_y_permitido_igual_a_validate_contract_directo`) usa
     exactamente `_contrato()`/`_perfil()`, ya cubierto por los casos
     `v07_contrato_minimo_perfil_coherente` / `v07_kind_technical_error_contrato_perfil`.

B) Matriz sintética adicional por cada `constraint_type` de `core.CONSTRAINT_TYPES`,
   cruzando (según lo relevante a cada regla): exactitud exacta/muestreada, nulos
   0/>0, duplicados en `top_valores` sí/no, campo presente/ausente/de alcance-dataset,
   dtype coincide/no coincide con `type_family`, y `sampling.activo` True/False.

Determinista: sin aleatoriedad (no se usa `random` en este script -- toda la matriz es
enumerada explícitamente). `RANDOM_STATE` se deja declarado por convención del
proyecto aunque no se consuma.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# --- Bootstrap de sys.path: este script vive en tools/datacontracts/tests/parity/, y
# puede invocarse como archivo suelto (no como módulo `-m`) desde cualquier cwd -- se
# agrega la raíz del repo (4 niveles arriba) para poder usar imports absolutos
# `tools.*`, igual que el resto del repo asume cuando corre desde la raíz.
_RAIZ_REPO = Path(__file__).resolve().parents[4]
if str(_RAIZ_REPO) not in sys.path:
    sys.path.insert(0, str(_RAIZ_REPO))

from tools.datacontracts import core as dc  # noqa: E402
from tools.datacontracts import validation as v  # noqa: E402
# `dsguard.checks` no se importa directamente: solo se usa `CheckResult.to_dict()`,
# método de las instancias que ya devuelve `v.validate_contract`.

RANDOM_STATE = 42  # No hay aleatoriedad real en este script (matriz enumerada a mano).

_SALIDA = Path(__file__).resolve().parent / "golden_v07_validation.json"


# --- Helpers de fixtures (copiados de tools/datacontracts/tests/test_validation.py,
# líneas 22-99 al momento de escribir esto) ------------------------------------------


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


# --- Descripción textual determinista (trazabilidad, NO re-ejecutable) --------------


def _desc_contrato(contrato) -> dict:
    if not isinstance(contrato, dc.DataContract):
        return {"tipo": type(contrato).__name__, "valor_repr": repr(contrato)[:120]}
    return {
        "contract_id": contrato.contract_id,
        "fields": [
            f"{c.name}:{c.type_family}:required={c.required}:nullable={c.nullable}" for c in contrato.fields
        ],
        "constraints": [
            f"{c.constraint_id}:{c.constraint_type}:field={c.field}:severity={c.severity}:"
            f"params={json.dumps(c.params, sort_keys=True, ensure_ascii=False)}"
            for c in contrato.constraints
        ],
        "keys": list(contrato.keys),
    }


def _desc_perfil(perfil) -> dict:
    if not isinstance(perfil, dict):
        return {"tipo": type(perfil).__name__, "valor_repr": repr(perfil)[:120]}
    desc: dict = {
        "claves_presentes": sorted(perfil.keys()),
        "schema": perfil.get("schema") if isinstance(perfil.get("schema"), dict) else perfil.get("schema"),
        "sampling": perfil.get("sampling"),
        "filas": perfil.get("filas"),
    }
    columnas = perfil.get("columnas_detalle")
    if isinstance(columnas, dict):
        desc["columnas_detalle"] = {
            nombre: {
                "dtype": det.get("dtype") if isinstance(det, dict) else None,
                "nulls": det.get("nulls") if isinstance(det, dict) else None,
                "unique": det.get("unique") if isinstance(det, dict) else None,
            }
            for nombre, det in columnas.items()
        }
    return desc


# --- Registro central de casos -------------------------------------------------------

_CASOS: list = []  # [(id, contrato, perfil), ...]
_IDS_VISTOS: set = set()


def _agregar(id_: str, contrato, perfil) -> None:
    if id_ in _IDS_VISTOS:
        raise AssertionError(f"id de caso duplicado: {id_!r}")
    _IDS_VISTOS.add(id_)
    _CASOS.append((id_, contrato, perfil))


# ======================================================================================
# Parte A: reconstrucción de test_validation.py (una entrada por cada llamada real a
# v.validate_contract(contrato, perfil) en el archivo).
# ======================================================================================

# --- TestInputYGateDeEvidencia -------------------------------------------------------

_agregar("v07_contract_invalido", "no soy un DataContract", _perfil())
_agregar("v07_profile_no_dict", _contrato(), [])
_agregar("v07_profile_none", _contrato(), None)

_p_sin_schema = _perfil()
del _p_sin_schema["schema"]
_agregar("v07_perfil_sin_schema", _contrato(), _p_sin_schema)

_p_sin_columnas = _perfil()
del _p_sin_columnas["columnas_detalle"]
_agregar("v07_perfil_sin_columnas_detalle", _contrato(), _p_sin_columnas)

_p_sin_sampling = _perfil()
del _p_sin_sampling["sampling"]
_agregar("v07_perfil_sin_sampling", _contrato(), _p_sin_sampling)

_p_sin_filas = _perfil()
del _p_sin_filas["filas"]
_agregar("v07_perfil_sin_filas", _contrato(), _p_sin_filas)

_p_activo_no_bool = _perfil()
_p_activo_no_bool["sampling"]["activo"] = "si"
_agregar("v07_sampling_activo_no_bool", _contrato(), _p_activo_no_bool)

# --- TestCasoSinViolaciones ------------------------------------------------------------

_agregar("v07_contrato_minimo_perfil_coherente", _contrato(), _perfil())

# --- TestFieldMissingUnexpected -------------------------------------------------------

_agregar(
    "v07_campo_requerido_ausente_fail",
    _contrato(fields=(_campo(name="id", required=True),)),
    _perfil(schema={}, columnas_detalle={}),
)
_agregar(
    "v07_campo_opcional_ausente_no_produce_resultado",
    _contrato(
        fields=(
            _campo(name="id", required=True, nullable=False),
            _campo(name="opcional", required=False, type_family="string"),
        )
    ),
    _perfil(),
)
_agregar(
    "v07_columna_no_declarada_warn",
    _contrato(),
    _perfil(
        schema={"id": "entero", "extra": "texto"},
        columnas_detalle={"id": _col_entera(), "extra": _col_texto()},
    ),
)

# --- TestBridgeTypeFamily --------------------------------------------------------------


def _contrato_perfil_bridge(type_family, dtype_observado, columna=None):
    contrato = _contrato(fields=(_campo(name="c", type_family=type_family, required=True, nullable=True),))
    columna = columna or {**_col_entera(), "dtype": dtype_observado}
    perfil = _perfil(schema={"c": dtype_observado}, columnas_detalle={"c": columna})
    return contrato, perfil


_agregar("v07_bridge_string_texto_pass", *_contrato_perfil_bridge("string", "texto", _col_texto()))
_agregar("v07_bridge_integer_entero_pass", *_contrato_perfil_bridge("integer", "entero"))
_agregar("v07_bridge_integer_flotante_fail", *_contrato_perfil_bridge("integer", "flotante"))
_agregar("v07_bridge_float_flotante_pass", *_contrato_perfil_bridge("float", "flotante"))
_agregar(
    "v07_bridge_boolean_booleano_pass",
    *_contrato_perfil_bridge("boolean", "booleano", {**_col_entera(), "dtype": "booleano"}),
)
_agregar("v07_bridge_date_fecha_pass", *_contrato_perfil_bridge("date", "fecha", _col_fecha()))
_agregar("v07_bridge_datetime_fecha_pass", *_contrato_perfil_bridge("datetime", "fecha", _col_fecha()))
_agregar("v07_bridge_unknown_texto_na", *_contrato_perfil_bridge("unknown", "texto", _col_texto()))
_agregar("v07_bridge_unknown_entero_na", *_contrato_perfil_bridge("unknown", "entero"))

# --- TestNullabilityDeterministaBajoMuestreo -------------------------------------------

_agregar(
    "v07_nullable_false_sin_nulos_pass_sampling",
    _contrato(fields=(_campo(name="id", nullable=False, required=True),)),
    _perfil(sampling_activo=True, tamano_muestra=100, columnas_detalle={"id": _col_entera(nulos=0)}),
)
_agregar(
    "v07_nullable_false_con_nulos_fail_sampling",
    _contrato(fields=(_campo(name="id", nullable=False, required=True),)),
    _perfil(sampling_activo=True, tamano_muestra=100, columnas_detalle={"id": _col_entera(nulos=3)}),
)

# --- TestContractKey ---------------------------------------------------------------------

_agregar("v07_key_sin_keys_na", _contrato(keys=()), _perfil())
_agregar(
    "v07_key_compuesta_warn",
    _contrato(
        fields=(_campo(name="a", type_family="string"), _campo(name="b", type_family="string")),
        keys=("a", "b"),
    ),
    _perfil(schema={"a": "texto", "b": "texto"}, columnas_detalle={"a": _col_texto(), "b": _col_texto()}),
)
_agregar(
    "v07_key_simple_exacta_sin_duplicados_pass",
    _contrato(keys=("id",)),
    _perfil(columnas_detalle={"id": _col_entera(unique_count=3, exactitud="exacta")}, filas=3),
)
_agregar(
    "v07_key_simple_exacta_con_duplicados_fail",
    _contrato(keys=("id",)),
    _perfil(columnas_detalle={"id": _col_entera(unique_count=2, exactitud="exacta")}, filas=3),
)

# --- TestConstraintNotNull ---------------------------------------------------------------

_agregar(
    "v07_not_null_field_none_na",
    _contrato(constraints=(_constraint(constraint_type="not_null", field=None),)),
    _perfil(),
)
_agregar(
    "v07_not_null_field_presente_sin_nulos_pass",
    _contrato(constraints=(_constraint(constraint_type="not_null", field="id"),)),
    _perfil(),
)
_agregar(
    "v07_not_null_field_con_nulos_severidad",
    _contrato(constraints=(_constraint(constraint_type="not_null", field="id", severity="WARN"),)),
    _perfil(columnas_detalle={"id": _col_entera(nulos=2)}),
)
_agregar(
    "v07_not_null_field_ausente_perfil_warn",
    _contrato(
        fields=(_campo(name="id", required=False, nullable=True),),
        constraints=(_constraint(constraint_type="not_null", field="id"),),
    ),
    _perfil(schema={}, columnas_detalle={}),
)

# --- TestConstraintUnique -----------------------------------------------------------------

_agregar(
    "v07_unique_exacta_sin_duplicados_pass",
    _contrato(constraints=(_constraint(constraint_type="unique", field="id"),)),
    _perfil(columnas_detalle={"id": _col_entera(unique_count=3, exactitud="exacta")}, filas=3),
)
_agregar(
    "v07_unique_exacta_con_duplicados_severidad",
    _contrato(constraints=(_constraint(constraint_type="unique", field="id", severity="WARN"),)),
    _perfil(columnas_detalle={"id": _col_entera(unique_count=2, exactitud="exacta")}, filas=3),
)
_agregar(
    "v07_unique_muestreada_sin_duplicado_warn",
    _contrato(constraints=(_constraint(constraint_type="unique", field="id"),)),
    _perfil(
        sampling_activo=True,
        tamano_muestra=3,
        columnas_detalle={
            "id": _col_entera(
                unique_count=3,
                exactitud="muestreada",
                top_valores=[{"valor": "1", "frecuencia": 1}, {"valor": "2", "frecuencia": 1}],
            )
        },
    ),
)
_agregar(
    "v07_unique_muestreada_con_duplicado_severidad",
    _contrato(constraints=(_constraint(constraint_type="unique", field="id", severity="FAIL"),)),
    _perfil(
        sampling_activo=True,
        tamano_muestra=3,
        columnas_detalle={
            "id": _col_entera(
                unique_count=2,
                exactitud="muestreada",
                top_valores=[{"valor": "1", "frecuencia": 2}, {"valor": "2", "frecuencia": 1}],
            )
        },
    ),
)
_agregar(
    "v07_unique_compuesta_siempre_warn",
    _contrato(
        fields=(_campo(name="a", type_family="string"), _campo(name="b", type_family="string")),
        constraints=(
            dc.Constraint(
                constraint_id="c_comp",
                constraint_type="unique",
                field=None,
                params={"fields": ["a", "b"]},
            ),
        ),
    ),
    _perfil(schema={"a": "texto", "b": "texto"}, columnas_detalle={"a": _col_texto(), "b": _col_texto()}),
)

# --- TestConstraintAllowedValues -----------------------------------------------------------

_agregar(
    "v07_allowed_values_field_none_na",
    _contrato(
        constraints=(
            dc.Constraint(constraint_id="c1", constraint_type="allowed_values", field=None, params={"values": ["a"]}),
        )
    ),
    _perfil(),
)
_agregar(
    "v07_allowed_values_valor_fuera_dominio_severidad",
    _contrato(
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
    ),
    _perfil(schema={"c": "texto"}, columnas_detalle={"c": _col_texto(top_valores=[{"valor": "z", "frecuencia": 1}])}),
)
_agregar(
    "v07_allowed_values_dominio_exhaustivo_exacto_pass",
    _contrato(
        fields=(_campo(name="c", type_family="string"),),
        constraints=(
            dc.Constraint(constraint_id="c1", constraint_type="allowed_values", field="c", params={"values": ["a"]}),
        ),
    ),
    _perfil(
        schema={"c": "texto"},
        columnas_detalle={"c": _col_texto(unique_count=1, exactitud="exacta", top_valores=[{"valor": "a", "frecuencia": 3}])},
    ),
)
_agregar(
    "v07_allowed_values_dominio_no_exhaustivo_warn",
    _contrato(
        fields=(_campo(name="c", type_family="string"),),
        constraints=(
            dc.Constraint(constraint_id="c1", constraint_type="allowed_values", field="c", params={"values": ["a"]}),
        ),
    ),
    _perfil(
        schema={"c": "texto"},
        columnas_detalle={
            "c": _col_texto(unique_count=1, exactitud="muestreada", top_valores=[{"valor": "a", "frecuencia": 3}])
        },
        sampling_activo=True,
        tamano_muestra=3,
    ),
)

# --- TestConstraintMinMaxValue -----------------------------------------------------------

_agregar(
    "v07_min_max_dtype_no_numerico_na",
    _contrato(
        fields=(_campo(name="c", type_family="string"),),
        constraints=(dc.Constraint(constraint_id="c1", constraint_type="min_value", field="c", params={"value": 1}),),
    ),
    _perfil(schema={"c": "texto"}, columnas_detalle={"c": _col_texto()}),
)
_agregar(
    "v07_min_value_viola_fail_sampling",
    _contrato(
        constraints=(
            dc.Constraint(
                constraint_id="c1", constraint_type="min_value", field="id", params={"value": 10}, severity="FAIL"
            ),
        )
    ),
    _perfil(sampling_activo=True, tamano_muestra=100, columnas_detalle={"id": _col_entera(minimo=5, maximo=20)}),
)
_agregar(
    "v07_max_value_no_viola_pass",
    _contrato(
        constraints=(dc.Constraint(constraint_id="c1", constraint_type="max_value", field="id", params={"value": 100}),)
    ),
    _perfil(columnas_detalle={"id": _col_entera(minimo=1, maximo=20)}),
)

# --- TestConstraintLength ------------------------------------------------------------------

_agregar(
    "v07_length_min_siempre_warn",
    _contrato(
        constraints=(dc.Constraint(constraint_id="c1", constraint_type="min_length", field="id", params={"value": 3}),)
    ),
    _perfil(),
)
_agregar(
    "v07_length_max_siempre_warn",
    _contrato(
        constraints=(dc.Constraint(constraint_id="c1", constraint_type="max_length", field="id", params={"value": 3}),)
    ),
    _perfil(),
)

# --- TestConstraintDateMinMax ---------------------------------------------------------------


def _contrato_fecha(**kw_constraint):
    base = dict(constraint_id="c1", constraint_type="date_min", field="f", params={"value": "2020-01-01"})
    base.update(kw_constraint)
    return _contrato(fields=(_campo(name="f", type_family="date"),), constraints=(dc.Constraint(**base),))


_agregar(
    "v07_date_dtype_no_fecha_na",
    _contrato_fecha(),
    _perfil(schema={"f": "texto"}, columnas_detalle={"f": _col_texto()}),
)
_agregar(
    "v07_date_valor_no_parseable_warn",
    _contrato_fecha(params={"value": "no-es-fecha"}),
    _perfil(schema={"f": "fecha"}, columnas_detalle={"f": _col_fecha()}),
)
_agregar(
    "v07_date_min_viola_severidad",
    _contrato_fecha(params={"value": "2020-01-01"}, severity="FAIL"),
    _perfil(
        schema={"f": "fecha"},
        columnas_detalle={"f": _col_fecha(fecha_min="2019-01-01T00:00:00", fecha_max="2024-01-01T00:00:00")},
    ),
)
_agregar(
    "v07_date_min_no_viola_pass",
    _contrato_fecha(params={"value": "2018-01-01"}),
    _perfil(
        schema={"f": "fecha"},
        columnas_detalle={"f": _col_fecha(fecha_min="2019-01-01T00:00:00", fecha_max="2024-01-01T00:00:00")},
    ),
)

# --- TestConstraintInvariant ------------------------------------------------------------------

_agregar(
    "v07_invariant_siempre_warn",
    _contrato(constraints=(dc.Constraint(constraint_id="c1", constraint_type="invariant", params={"note": "algo"}),)),
    _perfil(),
)

# --- TestNuncaPassPorFaltaDeEvidencia (matriz interna del test, 2 casos) ------------------

_agregar(
    "v07_matriz_sin_evidencia_unique",
    _contrato(constraints=(_constraint(constraint_type="unique", field="id"),)),
    _perfil(
        sampling_activo=True,
        tamano_muestra=3,
        columnas_detalle={
            "id": _col_entera(
                unique_count=3,
                exactitud="muestreada",
                top_valores=[{"valor": "1", "frecuencia": 1}, {"valor": "2", "frecuencia": 1}],
            )
        },
    ),
)
_agregar(
    "v07_matriz_sin_evidencia_allowed_values",
    _contrato(
        fields=(_campo(name="c", type_family="string"),),
        constraints=(
            dc.Constraint(constraint_id="c1", constraint_type="allowed_values", field="c", params={"values": ["a"]}),
        ),
    ),
    _perfil(
        schema={"c": "texto"},
        columnas_detalle={
            "c": _col_texto(unique_count=1, exactitud="muestreada", top_valores=[{"valor": "a", "frecuencia": 1}])
        },
        sampling_activo=True,
        tamano_muestra=3,
    ),
)

# --- TestKindTechnicalError ------------------------------------------------------------------

_agregar("v07_kind_technical_error_contrato_perfil", _contrato(), _perfil())

# --- TestPrivacidad --------------------------------------------------------------------------

_p_privacidad = _perfil()
_p_privacidad["dataset_path"] = "C:\\Users\\alguien\\datos_privados.csv"
_p_privacidad["schema"]["otra_no_declarada"] = "texto"
_p_privacidad["columnas_detalle"]["otra_no_declarada"] = _col_texto()
_agregar(
    "v07_privacidad_dataset_path",
    _contrato(
        fields=(_campo(name="id"), _campo(name="extra_no_declarado", required=False)),
        constraints=(_constraint(constraint_type="not_null", field="id"),),
    ),
    _p_privacidad,
)


# ======================================================================================
# Parte B: matriz sintética por constraint_type (60 casos), cruzando exactitud, nulos,
# duplicados en top_valores, presencia del campo, coincidencia de dtype y sampling.activo
# según lo relevante para cada regla (R10.1-R10.7 de `tools/datacontracts/validation.py`).
# ======================================================================================

# --- not_null (6) ------------------------------------------------------------------------

_agregar(
    "matrix_not_null_field_none_na",
    _contrato(constraints=(_constraint(constraint_type="not_null", field=None, constraint_id="m_nn_none"),)),
    _perfil(),
)
_agregar(
    "matrix_not_null_field_ausente_warn",
    _contrato(
        fields=(_campo(name="c", type_family="integer", required=False, nullable=True),),
        constraints=(_constraint(constraint_type="not_null", field="c", constraint_id="m_nn_ausente"),),
    ),
    _perfil(schema={}, columnas_detalle={}),
)
_agregar(
    "matrix_not_null_sin_nulos_sampling_false",
    _contrato(constraints=(_constraint(constraint_type="not_null", field="id", constraint_id="m_nn_ok_s0"),)),
    _perfil(sampling_activo=False, columnas_detalle={"id": _col_entera(nulos=0)}),
)
_agregar(
    "matrix_not_null_sin_nulos_sampling_true",
    _contrato(constraints=(_constraint(constraint_type="not_null", field="id", constraint_id="m_nn_ok_s1"),)),
    _perfil(sampling_activo=True, tamano_muestra=50, columnas_detalle={"id": _col_entera(nulos=0)}),
)
_agregar(
    "matrix_not_null_con_nulos_sampling_false_warn",
    _contrato(
        constraints=(
            _constraint(constraint_type="not_null", field="id", constraint_id="m_nn_bad_s0", severity="WARN"),
        )
    ),
    _perfil(sampling_activo=False, columnas_detalle={"id": _col_entera(nulos=2)}),
)
_agregar(
    "matrix_not_null_con_nulos_sampling_true_fail",
    _contrato(
        constraints=(
            _constraint(constraint_type="not_null", field="id", constraint_id="m_nn_bad_s1", severity="FAIL"),
        )
    ),
    _perfil(sampling_activo=True, tamano_muestra=50, columnas_detalle={"id": _col_entera(nulos=2)}),
)

# --- unique (9) ----------------------------------------------------------------------------

_agregar(
    "matrix_unique_exacta_sin_dup_nulos0",
    _contrato(constraints=(_constraint(constraint_type="unique", field="id", constraint_id="m_u1"),)),
    _perfil(columnas_detalle={"id": _col_entera(unique_count=3, exactitud="exacta", nulos=0)}, filas=3),
)
_agregar(
    "matrix_unique_exacta_sin_dup_nulos_gt0",
    _contrato(constraints=(_constraint(constraint_type="unique", field="id", constraint_id="m_u2"),)),
    _perfil(columnas_detalle={"id": _col_entera(unique_count=3, exactitud="exacta", nulos=2)}, filas=5),
)
_agregar(
    "matrix_unique_exacta_con_dup_nulos0",
    _contrato(constraints=(_constraint(constraint_type="unique", field="id", constraint_id="m_u3"),)),
    _perfil(columnas_detalle={"id": _col_entera(unique_count=2, exactitud="exacta", nulos=0)}, filas=3),
)
_agregar(
    "matrix_unique_exacta_con_dup_nulos_gt0_warn",
    _contrato(
        constraints=(_constraint(constraint_type="unique", field="id", constraint_id="m_u4", severity="WARN"),)
    ),
    _perfil(columnas_detalle={"id": _col_entera(unique_count=2, exactitud="exacta", nulos=2)}, filas=5),
)
_agregar(
    "matrix_unique_muestreada_sin_dup_en_muestra_warn",
    _contrato(constraints=(_constraint(constraint_type="unique", field="id", constraint_id="m_u5"),)),
    _perfil(
        sampling_activo=True,
        tamano_muestra=3,
        columnas_detalle={
            "id": _col_entera(
                unique_count=3,
                exactitud="muestreada",
                top_valores=[{"valor": "1", "frecuencia": 1}, {"valor": "2", "frecuencia": 1}],
            )
        },
    ),
)
_agregar(
    "matrix_unique_muestreada_con_dup_en_muestra_fail",
    _contrato(
        constraints=(_constraint(constraint_type="unique", field="id", constraint_id="m_u6", severity="FAIL"),)
    ),
    _perfil(
        sampling_activo=True,
        tamano_muestra=3,
        columnas_detalle={
            "id": _col_entera(
                unique_count=2,
                exactitud="muestreada",
                top_valores=[{"valor": "1", "frecuencia": 2}, {"valor": "2", "frecuencia": 1}],
            )
        },
    ),
)
_agregar(
    "matrix_unique_field_ausente_warn",
    _contrato(
        fields=(_campo(name="c", type_family="integer", required=False, nullable=True),),
        constraints=(_constraint(constraint_type="unique", field="c", constraint_id="m_u7"),),
    ),
    _perfil(schema={}, columnas_detalle={}),
)
_agregar(
    "matrix_unique_compuesta_warn",
    _contrato(
        fields=(_campo(name="a", type_family="string"), _campo(name="b", type_family="string")),
        constraints=(
            dc.Constraint(constraint_id="m_u8", constraint_type="unique", field=None, params={"fields": ["a", "b"]}),
        ),
    ),
    _perfil(schema={"a": "texto", "b": "texto"}, columnas_detalle={"a": _col_texto(), "b": _col_texto()}),
)
_agregar(
    "matrix_unique_sin_campo_objetivo_warn",
    _contrato(constraints=(dc.Constraint(constraint_id="m_u9", constraint_type="unique", field=None, params={}),)),
    _perfil(),
)

# --- allowed_values (7) ---------------------------------------------------------------------

_agregar(
    "matrix_allowed_values_field_none_na",
    _contrato(
        constraints=(
            dc.Constraint(constraint_id="m_av1", constraint_type="allowed_values", field=None, params={"values": ["a"]}),
        )
    ),
    _perfil(),
)
_agregar(
    "matrix_allowed_values_field_ausente_warn",
    _contrato(
        fields=(_campo(name="c", type_family="string", required=False, nullable=True),),
        constraints=(
            dc.Constraint(constraint_id="m_av2", constraint_type="allowed_values", field="c", params={"values": ["a"]}),
        ),
    ),
    _perfil(schema={}, columnas_detalle={}),
)
_agregar(
    "matrix_allowed_values_fuera_dominio_severidad_fail",
    _contrato(
        fields=(_campo(name="c", type_family="string"),),
        constraints=(
            dc.Constraint(
                constraint_id="m_av3", constraint_type="allowed_values", field="c", params={"values": ["a"]}, severity="FAIL"
            ),
        ),
    ),
    _perfil(schema={"c": "texto"}, columnas_detalle={"c": _col_texto(top_valores=[{"valor": "z", "frecuencia": 1}])}),
)
_agregar(
    "matrix_allowed_values_fuera_dominio_severidad_warn",
    _contrato(
        fields=(_campo(name="c", type_family="string"),),
        constraints=(
            dc.Constraint(
                constraint_id="m_av4", constraint_type="allowed_values", field="c", params={"values": ["a"]}, severity="WARN"
            ),
        ),
    ),
    _perfil(schema={"c": "texto"}, columnas_detalle={"c": _col_texto(top_valores=[{"valor": "z", "frecuencia": 1}])}),
)
_agregar(
    "matrix_allowed_values_dominio_exacto_exhaustivo_pass",
    _contrato(
        fields=(_campo(name="c", type_family="string"),),
        constraints=(
            dc.Constraint(constraint_id="m_av5", constraint_type="allowed_values", field="c", params={"values": ["a"]}),
        ),
    ),
    _perfil(
        schema={"c": "texto"},
        columnas_detalle={"c": _col_texto(unique_count=1, exactitud="exacta", top_valores=[{"valor": "a", "frecuencia": 3}])},
    ),
)
_agregar(
    "matrix_allowed_values_dominio_muestreada_no_exhaustivo_warn",
    _contrato(
        fields=(_campo(name="c", type_family="string"),),
        constraints=(
            dc.Constraint(constraint_id="m_av6", constraint_type="allowed_values", field="c", params={"values": ["a"]}),
        ),
    ),
    _perfil(
        schema={"c": "texto"},
        columnas_detalle={
            "c": _col_texto(unique_count=1, exactitud="muestreada", top_valores=[{"valor": "a", "frecuencia": 3}])
        },
        sampling_activo=True,
        tamano_muestra=3,
    ),
)
_agregar(
    "matrix_allowed_values_dominio_exacto_no_exhaustivo_warn",
    _contrato(
        fields=(_campo(name="c", type_family="string"),),
        constraints=(
            dc.Constraint(constraint_id="m_av7", constraint_type="allowed_values", field="c", params={"values": ["a", "b"]}),
        ),
    ),
    _perfil(
        schema={"c": "texto"},
        # unique.count(5) > len(top_valores)(1): exacta pero top_valores truncado -> no exhaustivo.
        columnas_detalle={"c": _col_texto(unique_count=5, exactitud="exacta", top_valores=[{"valor": "a", "frecuencia": 1}])},
    ),
)

# --- min_value (8) -------------------------------------------------------------------------

_agregar(
    "matrix_min_value_dtype_no_numerico_na",
    _contrato(
        fields=(_campo(name="c", type_family="string"),),
        constraints=(dc.Constraint(constraint_id="m_mv1", constraint_type="min_value", field="c", params={"value": 1}),),
    ),
    _perfil(schema={"c": "texto"}, columnas_detalle={"c": _col_texto()}),
)
_agregar(
    "matrix_min_value_field_none_na",
    _contrato(constraints=(dc.Constraint(constraint_id="m_mv2", constraint_type="min_value", field=None, params={"value": 1}),)),
    _perfil(),
)
_agregar(
    "matrix_min_value_field_ausente_warn",
    _contrato(
        fields=(_campo(name="c", type_family="integer", required=False, nullable=True),),
        constraints=(dc.Constraint(constraint_id="m_mv3", constraint_type="min_value", field="c", params={"value": 1}),),
    ),
    _perfil(schema={}, columnas_detalle={}),
)
_agregar(
    "matrix_min_value_viola_severidad_fail",
    _contrato(
        constraints=(
            dc.Constraint(constraint_id="m_mv4", constraint_type="min_value", field="id", params={"value": 10}, severity="FAIL"),
        )
    ),
    _perfil(columnas_detalle={"id": _col_entera(minimo=5, maximo=20)}),
)
_agregar(
    "matrix_min_value_viola_severidad_warn",
    _contrato(
        constraints=(
            dc.Constraint(constraint_id="m_mv5", constraint_type="min_value", field="id", params={"value": 10}, severity="WARN"),
        )
    ),
    _perfil(columnas_detalle={"id": _col_entera(minimo=5, maximo=20)}),
)
_agregar(
    "matrix_min_value_no_viola_pass",
    _contrato(
        constraints=(dc.Constraint(constraint_id="m_mv6", constraint_type="min_value", field="id", params={"value": 1}),)
    ),
    _perfil(columnas_detalle={"id": _col_entera(minimo=5, maximo=20)}),
)
_agregar(
    "matrix_min_value_boundary_igual_pass",
    _contrato(
        constraints=(dc.Constraint(constraint_id="m_mv7", constraint_type="min_value", field="id", params={"value": 5}),)
    ),
    _perfil(columnas_detalle={"id": _col_entera(minimo=5, maximo=20)}),
)
_agregar(
    "matrix_min_value_dtype_flotante_viola",
    _contrato(
        constraints=(
            dc.Constraint(constraint_id="m_mv8", constraint_type="min_value", field="id", params={"value": 10.0}),
        )
    ),
    _perfil(columnas_detalle={"id": {**_col_entera(minimo=5.0, maximo=20.0), "dtype": "flotante"}}),
)

# --- max_value (8) -------------------------------------------------------------------------

_agregar(
    "matrix_max_value_dtype_no_numerico_na",
    _contrato(
        fields=(_campo(name="c", type_family="string"),),
        constraints=(dc.Constraint(constraint_id="m_xv1", constraint_type="max_value", field="c", params={"value": 1}),),
    ),
    _perfil(schema={"c": "texto"}, columnas_detalle={"c": _col_texto()}),
)
_agregar(
    "matrix_max_value_field_none_na",
    _contrato(constraints=(dc.Constraint(constraint_id="m_xv2", constraint_type="max_value", field=None, params={"value": 1}),)),
    _perfil(),
)
_agregar(
    "matrix_max_value_field_ausente_warn",
    _contrato(
        fields=(_campo(name="c", type_family="integer", required=False, nullable=True),),
        constraints=(dc.Constraint(constraint_id="m_xv3", constraint_type="max_value", field="c", params={"value": 1}),),
    ),
    _perfil(schema={}, columnas_detalle={}),
)
_agregar(
    "matrix_max_value_viola_severidad_fail",
    _contrato(
        constraints=(
            dc.Constraint(constraint_id="m_xv4", constraint_type="max_value", field="id", params={"value": 10}, severity="FAIL"),
        )
    ),
    _perfil(columnas_detalle={"id": _col_entera(minimo=1, maximo=20)}),
)
_agregar(
    "matrix_max_value_viola_severidad_warn",
    _contrato(
        constraints=(
            dc.Constraint(constraint_id="m_xv5", constraint_type="max_value", field="id", params={"value": 10}, severity="WARN"),
        )
    ),
    _perfil(columnas_detalle={"id": _col_entera(minimo=1, maximo=20)}),
)
_agregar(
    "matrix_max_value_no_viola_pass",
    _contrato(
        constraints=(dc.Constraint(constraint_id="m_xv6", constraint_type="max_value", field="id", params={"value": 100}),)
    ),
    _perfil(columnas_detalle={"id": _col_entera(minimo=1, maximo=20)}),
)
_agregar(
    "matrix_max_value_boundary_igual_pass",
    _contrato(
        constraints=(dc.Constraint(constraint_id="m_xv7", constraint_type="max_value", field="id", params={"value": 20}),)
    ),
    _perfil(columnas_detalle={"id": _col_entera(minimo=1, maximo=20)}),
)
_agregar(
    "matrix_max_value_dtype_flotante_viola",
    _contrato(
        constraints=(
            dc.Constraint(constraint_id="m_xv8", constraint_type="max_value", field="id", params={"value": 10.0}),
        )
    ),
    _perfil(columnas_detalle={"id": {**_col_entera(minimo=1.0, maximo=20.0), "dtype": "flotante"}}),
)

# --- min_length (3) ------------------------------------------------------------------------

_agregar(
    "matrix_min_length_field_presente_warn",
    _contrato(
        constraints=(dc.Constraint(constraint_id="m_ml1", constraint_type="min_length", field="id", params={"value": 3}),)
    ),
    _perfil(),
)
_agregar(
    "matrix_min_length_field_none_warn",
    _contrato(constraints=(dc.Constraint(constraint_id="m_ml2", constraint_type="min_length", field=None, params={"value": 3}),)),
    _perfil(),
)
_agregar(
    "matrix_min_length_field_ausente_warn",
    _contrato(
        fields=(_campo(name="c", type_family="string", required=False, nullable=True),),
        constraints=(dc.Constraint(constraint_id="m_ml3", constraint_type="min_length", field="c", params={"value": 3}),),
    ),
    _perfil(schema={}, columnas_detalle={}),
)

# --- max_length (3) ------------------------------------------------------------------------

_agregar(
    "matrix_max_length_field_presente_warn",
    _contrato(
        constraints=(dc.Constraint(constraint_id="m_xl1", constraint_type="max_length", field="id", params={"value": 3}),)
    ),
    _perfil(),
)
_agregar(
    "matrix_max_length_field_none_warn",
    _contrato(constraints=(dc.Constraint(constraint_id="m_xl2", constraint_type="max_length", field=None, params={"value": 3}),)),
    _perfil(),
)
_agregar(
    "matrix_max_length_field_ausente_warn",
    _contrato(
        fields=(_campo(name="c", type_family="string", required=False, nullable=True),),
        constraints=(dc.Constraint(constraint_id="m_xl3", constraint_type="max_length", field="c", params={"value": 3}),),
    ),
    _perfil(schema={}, columnas_detalle={}),
)

# --- date_min (7) --------------------------------------------------------------------------

_agregar(
    "matrix_date_min_dtype_no_fecha_na",
    _contrato_fecha(constraint_id="m_dm1"),
    _perfil(schema={"f": "texto"}, columnas_detalle={"f": _col_texto()}),
)
_agregar(
    "matrix_date_min_field_none_na",
    _contrato(
        fields=(_campo(name="f", type_family="date"),),
        constraints=(dc.Constraint(constraint_id="m_dm2", constraint_type="date_min", field=None, params={"value": "2020-01-01"}),),
    ),
    _perfil(schema={"f": "fecha"}, columnas_detalle={"f": _col_fecha()}),
)
_agregar(
    "matrix_date_min_field_ausente_warn",
    _contrato(
        fields=(_campo(name="f", type_family="date", required=False, nullable=True),),
        constraints=(dc.Constraint(constraint_id="m_dm3", constraint_type="date_min", field="f", params={"value": "2020-01-01"}),),
    ),
    _perfil(schema={}, columnas_detalle={}),
)
_agregar(
    "matrix_date_min_valor_no_parseable_warn",
    _contrato_fecha(constraint_id="m_dm4", params={"value": "no-es-fecha"}),
    _perfil(schema={"f": "fecha"}, columnas_detalle={"f": _col_fecha()}),
)
_agregar(
    "matrix_date_min_viola_severidad_fail",
    _contrato_fecha(constraint_id="m_dm5", params={"value": "2020-01-01"}, severity="FAIL"),
    _perfil(
        schema={"f": "fecha"},
        columnas_detalle={"f": _col_fecha(fecha_min="2019-01-01T00:00:00", fecha_max="2024-01-01T00:00:00")},
    ),
)
_agregar(
    "matrix_date_min_viola_severidad_warn",
    _contrato_fecha(constraint_id="m_dm6", params={"value": "2020-01-01"}, severity="WARN"),
    _perfil(
        schema={"f": "fecha"},
        columnas_detalle={"f": _col_fecha(fecha_min="2019-01-01T00:00:00", fecha_max="2024-01-01T00:00:00")},
    ),
)
_agregar(
    "matrix_date_min_no_viola_pass",
    _contrato_fecha(constraint_id="m_dm7", params={"value": "2018-01-01"}),
    _perfil(
        schema={"f": "fecha"},
        columnas_detalle={"f": _col_fecha(fecha_min="2019-01-01T00:00:00", fecha_max="2024-01-01T00:00:00")},
    ),
)

# --- date_max (7) --------------------------------------------------------------------------

_agregar(
    "matrix_date_max_dtype_no_fecha_na",
    _contrato_fecha(constraint_id="m_dx1", constraint_type="date_max"),
    _perfil(schema={"f": "texto"}, columnas_detalle={"f": _col_texto()}),
)
_agregar(
    "matrix_date_max_field_none_na",
    _contrato(
        fields=(_campo(name="f", type_family="date"),),
        constraints=(dc.Constraint(constraint_id="m_dx2", constraint_type="date_max", field=None, params={"value": "2025-01-01"}),),
    ),
    _perfil(schema={"f": "fecha"}, columnas_detalle={"f": _col_fecha()}),
)
_agregar(
    "matrix_date_max_field_ausente_warn",
    _contrato(
        fields=(_campo(name="f", type_family="date", required=False, nullable=True),),
        constraints=(
            dc.Constraint(constraint_id="m_dx3", constraint_type="date_max", field="f", params={"value": "2025-01-01"}),
        ),
    ),
    _perfil(schema={}, columnas_detalle={}),
)
_agregar(
    "matrix_date_max_valor_no_parseable_warn",
    _contrato_fecha(constraint_id="m_dx4", constraint_type="date_max", params={"value": "no-es-fecha"}),
    _perfil(schema={"f": "fecha"}, columnas_detalle={"f": _col_fecha()}),
)
_agregar(
    "matrix_date_max_viola_severidad_fail",
    _contrato_fecha(constraint_id="m_dx5", constraint_type="date_max", params={"value": "2020-01-01"}, severity="FAIL"),
    _perfil(
        schema={"f": "fecha"},
        columnas_detalle={"f": _col_fecha(fecha_min="2019-01-01T00:00:00", fecha_max="2024-01-01T00:00:00")},
    ),
)
_agregar(
    "matrix_date_max_viola_severidad_warn",
    _contrato_fecha(constraint_id="m_dx6", constraint_type="date_max", params={"value": "2020-01-01"}, severity="WARN"),
    _perfil(
        schema={"f": "fecha"},
        columnas_detalle={"f": _col_fecha(fecha_min="2019-01-01T00:00:00", fecha_max="2024-01-01T00:00:00")},
    ),
)
_agregar(
    "matrix_date_max_no_viola_pass",
    _contrato_fecha(constraint_id="m_dx7", constraint_type="date_max", params={"value": "2025-01-01"}),
    _perfil(
        schema={"f": "fecha"},
        columnas_detalle={"f": _col_fecha(fecha_min="2019-01-01T00:00:00", fecha_max="2024-01-01T00:00:00")},
    ),
)

# --- invariant (2) -------------------------------------------------------------------------

_agregar(
    "matrix_invariant_sin_fields_warn",
    _contrato(constraints=(dc.Constraint(constraint_id="m_inv1", constraint_type="invariant", params={"note": "algo"}),)),
    _perfil(),
)
_agregar(
    "matrix_invariant_con_fields_warn",
    _contrato(
        fields=(_campo(name="a", type_family="string"), _campo(name="b", type_family="string")),
        constraints=(
            dc.Constraint(
                constraint_id="m_inv2",
                constraint_type="invariant",
                params={"note": "a debe ser mayor que b", "fields": ["a", "b"]},
            ),
        ),
    ),
    _perfil(schema={"a": "texto", "b": "texto"}, columnas_detalle={"a": _col_texto(), "b": _col_texto()}),
)


# ======================================================================================
# Ejecución: correr validate_contract sobre cada caso registrado y escribir el golden.
# ======================================================================================


def _construir_golden() -> dict:
    cases = []
    for id_, contrato, perfil in _CASOS:
        resultados = v.validate_contract(contrato, perfil)
        cases.append(
            {
                "id": id_,
                "contrato_desc": _desc_contrato(contrato),
                "perfil_desc": _desc_perfil(perfil),
                "resultado": [r.to_dict() for r in resultados],
            }
        )
    return {"schema_version": 1, "generated_by": "build_golden_v07.py", "cases": cases}


def main() -> None:
    golden = _construir_golden()
    texto = json.dumps(golden, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    _SALIDA.write_text(texto, encoding="utf-8")
    print(f"{len(golden['cases'])} casos escritos en {_SALIDA}")


if __name__ == "__main__":
    main()

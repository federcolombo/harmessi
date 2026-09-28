"""Evaluación determinista de `DataContract` contra evidencia real (v0.7 Change 1,
`20260922-data-contract-validation`). Sibling de `core.py` (Change 0, sin modificar).

Dos funciones públicas, mismo patrón que `tools/reporting/validation.py`
(`validate_report` puro / `validate_report_dir` con I/O):

- `validate_contract(contract, profile)`: pura, sin I/O, sin guard, sin `Path`. `profile`
  es un `dict` YA cargado (la forma de `profile.json` de `ds_profile`). Nunca lanza.
- `validate_contract_against_profile_file(contract, profile_path, repo_root)`: puerta con
  I/O -- aplica `ds_profile.holdout_guard.verificar_permitido` ANTES de abrir el archivo
  (una ruta denegada nunca se abre), lee y parsea, y delega en `validate_contract`. Nunca
  lanza.

Frontera de imports (R1 de `spec.md`, verificada por
`tools/tests/test_v07_validation_neutrality.py`): stdlib + `dsguard.checks` + SOLO
`ds_profile.holdout_guard.verificar_permitido` (ningún otro símbolo de `ds_profile`,
nunca el paquete completo) + `tools.datacontracts.core` (sibling). Sin pandas/numpy, sin
ningún otro paquete de `tools/`.

Privacidad: ningún `CheckResult` (message/detail/subject) referencia
`profile.get("dataset_path")` ni ninguna ruta absoluta local -- los `subject` usan
nombres de campo o `constraint_id`, nunca rutas.

Vocabulario `PASS`/`WARN`/`FAIL`/`N/A`: nunca `PASS` por falta de evidencia (R12). Toda
excepción inesperada de una regla individual se convierte en
`CheckResult(FAIL, "<código-base>-EXCEPCION", ..., kind="technical_error")`
(`checks.resultado_de_excepcion`), sin propagar.

Notas de diseño / interpretaciones explícitas de `spec.md` (a confirmar por el Lead si
hiciera falta ajustarlas):

1. **`CONTRACT-TYPE-MISMATCH` es una regla agregada, no una entrada por campo.** Se
   evalúa una vez por `DataContract` (mismo lugar en el orden fijo de R3 que
   `CONTRACT-FIELD-MISSING`/`-UNEXPECTED`/`-NULLABILITY`/`-KEY`): si algún campo verificable
   viola su `type_family`, se emite una entrada `FAIL` por campo violador (mismo patrón
   `_resumir` que las otras reglas estructurales); si ninguno viola, se emite UN solo
   resultado agregado -- `PASS` si al menos un campo con `type_family` mapeada fue
   verificado y coincidió, `N/A` si todos los campos verificables son `"unknown"` (sin
   mapeo) o no hay ningún campo presente en el perfil para comparar. Los campos
   `"unknown"` individuales no generan una entrada `N/A` propia: quedan absorbidos en el
   agregado, igual que los campos opcionales ausentes no generan entrada en
   `CONTRACT-FIELD-MISSING` (R9). Motivo: R3 dice "cada regla sin violaciones emite
   EXACTAMENTE un PASS/N/A" y enumera `CONTRACT-TYPE-MISMATCH` como una sola regla del
   orden fijo, no una por campo.
2. **`unique`/`allowed_values`/`keys` bajo muestreo usan `top_valores` como evidencia de
   duplicado, no una longitud de muestra reconstruida.** `profile.json` no persiste el
   tamaño de la muestra NO NULA de una columna concreta (`sampling.tamano_muestra` es el
   tamaño de la muestra de FILAS completas, no de valores no nulos de una columna). En su
   lugar, se usa una señal directa y siempre disponible: si algún `top_valores[i]["frecuencia"]
   > 1`, eso es evidencia real e inequívoca de un valor repetido observado dentro de la
   muestra (un `Counter` no puede reportar frecuencia > 1 sin que el valor haya aparecido
   más de una vez en los datos vistos), sin importar si `top_valores` está truncado a
   `top_n`. Ausencia de cualquier frecuencia > 1 en `top_valores` nunca se interpreta como
   evidencia de PASS (podría haber un duplicado fuera de las top-N filas más frecuentes) --
   cae en `WARN` "no verificable como cumplimiento", igual que exige R10.2. Es la misma
   asimetría violación-vs-cumplimiento de `design.md`, implementada con el campo del
   perfil que sí existe.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

_TOOLS_DIR = Path(__file__).resolve().parents[1]
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from dsguard import checks  # noqa: E402
from ds_profile.holdout_guard import verificar_permitido  # noqa: E402

from . import core as datacontracts_core  # noqa: E402

# --- Códigos (R2 de spec.md) --------------------------------------------------

CODE_INPUT = "CONTRACT-INPUT"
CODE_EVIDENCE_MISSING = "CONTRACT-EVIDENCE-MISSING"
CODE_FIELD_MISSING = "CONTRACT-FIELD-MISSING"
CODE_FIELD_UNEXPECTED = "CONTRACT-FIELD-UNEXPECTED"
CODE_TYPE_MISMATCH = "CONTRACT-TYPE-MISMATCH"
CODE_NULLABILITY = "CONTRACT-NULLABILITY"
CODE_KEY = "CONTRACT-KEY"
CODE_NOT_NULL_EXPECTATION = "CONTRACT-NOT-NULL-EXPECTATION"
CODE_UNIQUENESS = "CONTRACT-UNIQUENESS"
CODE_DOMAIN = "CONTRACT-DOMAIN"
CODE_RANGE = "CONTRACT-RANGE"
CODE_LENGTH = "CONTRACT-LENGTH"
CODE_DATE_RANGE = "CONTRACT-DATE-RANGE"
CODE_INVARIANT = "CONTRACT-INVARIANT"

CODES = (
    CODE_INPUT,
    CODE_EVIDENCE_MISSING,
    CODE_FIELD_MISSING,
    CODE_FIELD_UNEXPECTED,
    CODE_TYPE_MISMATCH,
    CODE_NULLABILITY,
    CODE_KEY,
    CODE_NOT_NULL_EXPECTATION,
    CODE_UNIQUENESS,
    CODE_DOMAIN,
    CODE_RANGE,
    CODE_LENGTH,
    CODE_DATE_RANGE,
    CODE_INVARIANT,
)

# --- Bridge type_family -> dtype de ds_profile (R6, decisión de diseño 4) -----

_DTYPE_ESPERADO_POR_FAMILIA = {
    "string": frozenset({"texto"}),
    "integer": frozenset({"entero"}),
    "float": frozenset({"flotante"}),
    "boolean": frozenset({"booleano"}),
    "date": frozenset({"fecha"}),
    "datetime": frozenset({"fecha"}),  # ds_profile no distingue date de datetime
    "unknown": frozenset(),  # sin mapeo -> siempre N/A
}

_CODIGO_POR_CONSTRAINT_TYPE = {
    "not_null": CODE_NOT_NULL_EXPECTATION,
    "unique": CODE_UNIQUENESS,
    "allowed_values": CODE_DOMAIN,
    "min_value": CODE_RANGE,
    "max_value": CODE_RANGE,
    "min_length": CODE_LENGTH,
    "max_length": CODE_LENGTH,
    "date_min": CODE_DATE_RANGE,
    "date_max": CODE_DATE_RANGE,
    "invariant": CODE_INVARIANT,
}


# --- Helpers privados -----------------------------------------------------------


def _res(
    status: str,
    code: str,
    message: str,
    subject: Optional[str] = None,
    *,
    tecnico: bool = False,
    detail: Optional[str] = None,
) -> checks.CheckResult:
    return checks.CheckResult(
        status=status,
        code=code,
        message=message,
        detail=detail,
        subject=subject,
        kind=checks.KIND_TECHNICAL_ERROR if tecnico else checks.KIND_CHECK,
    )


def _ejecutar(registros: list) -> list:
    """Como `checks.ejecutar_checks`: corre cada regla, nunca frena -- una excepción
    inesperada de una regla individual se convierte en `checks.resultado_de_excepcion`
    (código `<codigo_base>-EXCEPCION`, `kind="technical_error"`) sin impedir que corran
    las siguientes."""
    resultados: list = []
    for codigo_base, funcion, args in registros:
        try:
            resultados.extend(funcion(*args))
        except Exception as exc:  # noqa: BLE001 -- nunca debe escapar de una regla individual
            resultados.append(checks.resultado_de_excepcion(codigo_base, exc))
    return resultados


def _texto_comparable(valor: Any) -> str:
    """Misma normalización que `ds_profile.column_stats._texto` (`str(valor).strip()`)
    -- reimplementada localmente para no importar `ds_profile.column_stats` (prohibido
    por R1: la única dependencia autorizada de `ds_profile` es `holdout_guard`)."""
    return str(valor).strip()


def _parsear_iso(valor: Any) -> Optional[datetime]:
    if not isinstance(valor, str):
        return None
    try:
        return datetime.fromisoformat(valor)
    except ValueError:
        return None


# --- Gate de evidencia (R5) -------------------------------------------------------


def _validar_evidencia(profile: Any) -> Optional[checks.CheckResult]:
    """`None` si `profile` tiene la forma mínima exigida; si no, el
    `CheckResult(FAIL, CONTRACT-EVIDENCE-MISSING, ..., kind="technical_error")` a
    devolver (y cortar)."""
    if not isinstance(profile, dict):
        return _res(
            checks.STATUS_FAIL,
            CODE_EVIDENCE_MISSING,
            f"El perfil no es un dict utilizable (se recibió {type(profile).__name__}).",
            tecnico=True,
        )
    if not isinstance(profile.get("schema"), dict):
        return _res(
            checks.STATUS_FAIL,
            CODE_EVIDENCE_MISSING,
            "Falta profile['schema'] (o no es dict): evidencia insuficiente para validar el contrato.",
            tecnico=True,
        )
    if not isinstance(profile.get("columnas_detalle"), dict):
        return _res(
            checks.STATUS_FAIL,
            CODE_EVIDENCE_MISSING,
            "Falta profile['columnas_detalle'] (o no es dict): evidencia insuficiente.",
            tecnico=True,
        )
    sampling = profile.get("sampling")
    if not isinstance(sampling, dict) or not isinstance(sampling.get("activo"), bool):
        return _res(
            checks.STATUS_FAIL,
            CODE_EVIDENCE_MISSING,
            "Falta profile['sampling']['activo'] (bool): evidencia insuficiente.",
            tecnico=True,
        )
    filas = profile.get("filas")
    if isinstance(filas, bool) or not isinstance(filas, int) or filas < 0:
        return _res(
            checks.STATUS_FAIL,
            CODE_EVIDENCE_MISSING,
            "Falta profile['filas'] (int >= 0): evidencia insuficiente.",
            tecnico=True,
        )
    return None


# --- Reglas estructurales (R6/R8/R9/R11) -------------------------------------------


def _regla_field_missing(contract: Any, profile: dict) -> list:
    schema = profile["schema"]
    violaciones = [
        (f"El campo requerido {campo.name!r} no está presente en el perfil observado.", campo.name)
        for campo in contract.fields
        if campo.required and campo.name not in schema
    ]
    if violaciones:
        return [_res(checks.STATUS_FAIL, CODE_FIELD_MISSING, m, s) for m, s in violaciones]
    return [
        _res(
            checks.STATUS_PASS,
            CODE_FIELD_MISSING,
            "Todos los campos requeridos del contrato están presentes en el perfil.",
        )
    ]


def _regla_field_unexpected(contract: Any, profile: dict) -> list:
    nombres_declarados = {campo.name for campo in contract.fields}
    schema = profile["schema"]
    violaciones = [
        (f"La columna {nombre!r} está presente en el perfil pero no declarada en el contrato.", nombre)
        for nombre in schema
        if nombre not in nombres_declarados
    ]
    if violaciones:
        return [_res(checks.STATUS_WARN, CODE_FIELD_UNEXPECTED, m, s) for m, s in violaciones]
    return [
        _res(
            checks.STATUS_PASS,
            CODE_FIELD_UNEXPECTED,
            "Todas las columnas del perfil están declaradas en el contrato.",
        )
    ]


def _regla_type_mismatch(contract: Any, profile: dict) -> list:
    """Agregada (ver docstring del módulo, nota 1): una entrada FAIL por campo
    violador si hay violaciones; si no, UN solo PASS/N-A agregado."""
    schema = profile["schema"]
    columnas = profile["columnas_detalle"]
    violaciones = []
    hubo_match = False
    hubo_na = False
    for campo in contract.fields:
        if campo.name not in schema:
            continue
        if campo.type_family == "unknown":
            hubo_na = True
            continue
        esperados = _DTYPE_ESPERADO_POR_FAMILIA.get(campo.type_family, frozenset())
        observado = columnas.get(campo.name, {}).get("dtype")
        if observado not in esperados:
            violaciones.append(
                (
                    f"El campo {campo.name!r} declara type_family={campo.type_family!r} pero el "
                    f"perfil observa dtype={observado!r} (fuera de {sorted(esperados)}).",
                    campo.name,
                )
            )
        else:
            hubo_match = True
    if violaciones:
        return [_res(checks.STATUS_FAIL, CODE_TYPE_MISMATCH, m, s) for m, s in violaciones]
    if hubo_match:
        return [
            _res(
                checks.STATUS_PASS,
                CODE_TYPE_MISMATCH,
                "Todos los campos verificables coinciden con el dtype observado del perfil.",
            )
        ]
    if hubo_na:
        return [
            _res(
                checks.STATUS_NA,
                CODE_TYPE_MISMATCH,
                "Ningún campo evaluable declara una type_family con mapeo de dtype (unknown).",
            )
        ]
    return [
        _res(
            checks.STATUS_NA,
            CODE_TYPE_MISMATCH,
            "Sin campos evaluables presentes en el perfil para comparar type_family.",
        )
    ]


def _regla_nullability(contract: Any, profile: dict) -> list:
    schema = profile["schema"]
    columnas = profile["columnas_detalle"]
    violaciones = []
    for campo in contract.fields:
        if campo.nullable or campo.name not in schema:
            continue
        detalle = columnas.get(campo.name, {})
        count = detalle.get("nulls", {}).get("count")
        if isinstance(count, int) and count > 0:
            violaciones.append(
                (
                    f"El campo {campo.name!r} declara nullable=False pero el perfil observa "
                    f"{count} nulo(s).",
                    campo.name,
                )
            )
    if violaciones:
        return [_res(checks.STATUS_FAIL, CODE_NULLABILITY, m, s) for m, s in violaciones]
    return [
        _res(
            checks.STATUS_PASS,
            CODE_NULLABILITY,
            "Ningún campo declarado nullable=False tiene nulos observados en el perfil.",
        )
    ]


def _evaluar_unicidad_campo(nombre_campo: str, profile: dict):
    """Devuelve `(resultado, mensaje)` con `resultado` en
    `{"ausente", "violacion", "pass", "no_verificable"}`, compartido por `CONTRACT-KEY`
    (key simple) y `constraint_type == "unique"` de un solo campo (R10.2/R11)."""
    schema = profile["schema"]
    columnas = profile["columnas_detalle"]
    if nombre_campo not in schema or nombre_campo not in columnas:
        return "ausente", f"El campo {nombre_campo!r} no está presente en el perfil."

    detalle = columnas[nombre_campo]
    filas = profile["filas"]
    nulos = detalle.get("nulls", {}).get("count")
    no_nulos = filas - nulos if isinstance(nulos, int) else None
    unique = detalle.get("unique", {})
    distintos = unique.get("count")
    exactitud = unique.get("exactitud")

    if exactitud == "exacta":
        if isinstance(distintos, int) and isinstance(no_nulos, int) and distintos < no_nulos:
            return "violacion", (
                f"El campo {nombre_campo!r} tiene valores duplicados: {distintos} valor(es) "
                f"distinto(s) sobre {no_nulos} fila(s) no nula(s) (evidencia exacta)."
            )
        return "pass", (
            f"El campo {nombre_campo!r} es único sobre {no_nulos} fila(s) no nula(s) "
            "(evidencia exacta)."
        )

    if exactitud == "muestreada":
        top_valores = detalle.get("top_valores", [])
        duplicado_en_muestra = any(
            isinstance(tv, dict) and isinstance(tv.get("frecuencia"), int) and tv["frecuencia"] > 1
            for tv in top_valores
        )
        if duplicado_en_muestra:
            return "violacion", (
                f"El campo {nombre_campo!r} muestra al menos un valor repetido dentro de la "
                "muestra observada (evidencia real de duplicado, pese al muestreo)."
            )
        return "no_verificable", (
            f"El campo {nombre_campo!r}: la muestra observada no evidenció duplicados, pero no "
            "cubre todas las filas (no verificable como cumplimiento bajo muestreo)."
        )

    return "no_verificable", f"El campo {nombre_campo!r}: exactitud de unicidad desconocida en el perfil."


def _regla_key(contract: Any, profile: dict) -> list:
    keys = contract.keys
    if not keys:
        return [_res(checks.STATUS_NA, CODE_KEY, "El contrato no declara keys.")]
    if len(keys) > 1:
        return [
            _res(
                checks.STATUS_WARN,
                CODE_KEY,
                "Unicidad compuesta no verificable: ds_profile no calcula unicidad conjunta "
                "entre columnas, solo cardinalidad por columna.",
                ",".join(keys),
            )
        ]
    campo = keys[0]
    resultado, mensaje = _evaluar_unicidad_campo(campo, profile)
    if resultado == "violacion":
        return [_res(checks.STATUS_FAIL, CODE_KEY, mensaje, campo)]
    if resultado == "pass":
        return [_res(checks.STATUS_PASS, CODE_KEY, mensaje, campo)]
    return [_res(checks.STATUS_WARN, CODE_KEY, mensaje, campo)]


# --- Reglas por constraint_type (R10) -----------------------------------------------


def _regla_not_null(constraint: Any, profile: dict) -> list:
    codigo = CODE_NOT_NULL_EXPECTATION
    campo = constraint.field
    if campo is None:
        return [
            _res(
                checks.STATUS_NA,
                codigo,
                "Constraint de alcance dataset (field=None), no evaluable como not_null de una "
                "columna concreta.",
                constraint.constraint_id,
            )
        ]
    if campo not in profile["schema"]:
        return [
            _res(
                checks.STATUS_WARN,
                codigo,
                f"No verificable: la columna {campo!r} no está presente en el perfil.",
                campo,
            )
        ]
    detalle = profile["columnas_detalle"].get(campo, {})
    count = detalle.get("nulls", {}).get("count")
    if isinstance(count, int) and count > 0:
        return [
            _res(
                constraint.severity,
                codigo,
                f"El campo {campo!r} tiene {count} valor(es) nulo(s), viola la expectativa "
                f"not_null ({constraint.constraint_id!r}).",
                campo,
            )
        ]
    return [
        _res(
            checks.STATUS_PASS,
            codigo,
            f"El campo {campo!r} no tiene nulos observados (expectativa not_null "
            f"{constraint.constraint_id!r}).",
            campo,
        )
    ]


def _regla_unique(constraint: Any, profile: dict) -> list:
    codigo = CODE_UNIQUENESS
    campos_objetivo = constraint.params.get("fields")
    if campos_objetivo is None:
        campos_objetivo = [constraint.field] if constraint.field is not None else []
    if not campos_objetivo:
        return [
            _res(
                checks.STATUS_WARN,
                codigo,
                "No verificable: constraint sin campo(s) objetivo.",
                constraint.constraint_id,
            )
        ]
    if len(campos_objetivo) > 1:
        return [
            _res(
                checks.STATUS_WARN,
                codigo,
                "No verificable: ds_profile no calcula unicidad conjunta entre columnas, solo "
                "cardinalidad por columna.",
                ",".join(campos_objetivo),
            )
        ]
    campo = campos_objetivo[0]
    resultado, mensaje = _evaluar_unicidad_campo(campo, profile)
    if resultado == "violacion":
        return [_res(constraint.severity, codigo, mensaje, campo)]
    if resultado == "pass":
        return [_res(checks.STATUS_PASS, codigo, mensaje, campo)]
    return [_res(checks.STATUS_WARN, codigo, mensaje, campo)]


def _regla_allowed_values(constraint: Any, profile: dict) -> list:
    codigo = CODE_DOMAIN
    campo = constraint.field
    if campo is None:
        return [
            _res(
                checks.STATUS_NA,
                codigo,
                "Constraint de alcance dataset no aplicable a allowed_values.",
                constraint.constraint_id,
            )
        ]
    if campo not in profile["schema"]:
        return [
            _res(
                checks.STATUS_WARN,
                codigo,
                f"No verificable: la columna {campo!r} no está presente en el perfil.",
                campo,
            )
        ]
    valores_permitidos = {_texto_comparable(v) for v in constraint.params.get("values", [])}
    detalle = profile["columnas_detalle"].get(campo, {})
    top_valores = detalle.get("top_valores", [])
    infractores = [
        tv
        for tv in top_valores
        if isinstance(tv, dict) and _texto_comparable(tv.get("valor")) not in valores_permitidos
    ]
    if infractores:
        return [
            _res(
                constraint.severity,
                codigo,
                f"El valor {tv.get('valor')!r} observado en {campo!r} no pertenece a "
                f"allowed_values (frecuencia observada: {tv.get('frecuencia')!r}).",
                campo,
            )
            for tv in infractores
        ]
    unique = detalle.get("unique", {})
    if (
        unique.get("exactitud") == "exacta"
        and isinstance(unique.get("count"), int)
        and unique["count"] <= len(top_valores)
    ):
        return [
            _res(
                checks.STATUS_PASS,
                codigo,
                f"Todos los valores distintos observados de {campo!r} están dentro de "
                "allowed_values (evidencia exacta y exhaustiva).",
                campo,
            )
        ]
    return [
        _res(
            checks.STATUS_WARN,
            codigo,
            "No verificable como cumplimiento: el dominio no está evidenciado por completo "
            "(top_valores no cubre todos los valores distintos).",
            campo,
        )
    ]


def _regla_min_max_value(constraint: Any, profile: dict) -> list:
    codigo = CODE_RANGE
    campo = constraint.field
    if campo is None:
        return [
            _res(
                checks.STATUS_NA,
                codigo,
                "Constraint sin campo objetivo, no aplica a min_value/max_value.",
                constraint.constraint_id,
            )
        ]
    if campo not in profile["schema"]:
        return [
            _res(
                checks.STATUS_WARN,
                codigo,
                f"No verificable: la columna {campo!r} no está presente en el perfil.",
                campo,
            )
        ]
    detalle = profile["columnas_detalle"].get(campo, {})
    dtype = detalle.get("dtype")
    if dtype not in ("entero", "flotante"):
        return [
            _res(
                checks.STATUS_NA,
                codigo,
                f"No aplica: la columna {campo!r} no es numérica según el perfil (dtype={dtype!r}).",
                campo,
            )
        ]
    valor_declarado = constraint.params.get("value")
    if constraint.constraint_type == "min_value":
        observado = detalle.get("min")
        viola = isinstance(observado, (int, float)) and observado < valor_declarado
        mensaje = (
            f"El mínimo observado de {campo!r} ({observado!r}) es menor que el mínimo declarado "
            f"({valor_declarado!r})."
        )
    else:
        observado = detalle.get("max")
        viola = isinstance(observado, (int, float)) and observado > valor_declarado
        mensaje = (
            f"El máximo observado de {campo!r} ({observado!r}) es mayor que el máximo declarado "
            f"({valor_declarado!r})."
        )
    if viola:
        return [_res(constraint.severity, codigo, mensaje, campo)]
    return [
        _res(
            checks.STATUS_PASS,
            codigo,
            f"El rango observado de {campo!r} cumple con {constraint.constraint_id!r}.",
            campo,
        )
    ]


def _regla_length(constraint: Any, profile: dict) -> list:
    campo = constraint.field or constraint.constraint_id
    return [
        _res(
            checks.STATUS_WARN,
            CODE_LENGTH,
            "No verificable: ds_profile no calcula estadísticas de longitud de texto.",
            campo,
        )
    ]


def _regla_date_min_max(constraint: Any, profile: dict) -> list:
    codigo = CODE_DATE_RANGE
    campo = constraint.field
    if campo is None:
        return [
            _res(
                checks.STATUS_NA,
                codigo,
                "Constraint sin campo objetivo, no aplica a date_min/date_max.",
                constraint.constraint_id,
            )
        ]
    if campo not in profile["schema"]:
        return [
            _res(
                checks.STATUS_WARN,
                codigo,
                f"No verificable: la columna {campo!r} no está presente en el perfil.",
                campo,
            )
        ]
    detalle = profile["columnas_detalle"].get(campo, {})
    dtype = detalle.get("dtype")
    if dtype != "fecha":
        return [
            _res(
                checks.STATUS_NA,
                codigo,
                f"No aplica: la columna {campo!r} no es de tipo fecha según el perfil (dtype={dtype!r}).",
                campo,
            )
        ]
    valor_declarado = constraint.params.get("value")
    clave_observada = "fecha_min" if constraint.constraint_type == "date_min" else "fecha_max"
    observado = detalle.get(clave_observada)
    fecha_declarada = _parsear_iso(valor_declarado)
    fecha_observada = _parsear_iso(observado)
    if fecha_declarada is None or fecha_observada is None:
        return [
            _res(checks.STATUS_WARN, codigo, "No verificable: formato de fecha no comparable.", campo)
        ]
    if constraint.constraint_type == "date_min":
        viola = fecha_observada < fecha_declarada
        mensaje = (
            f"La fecha mínima observada de {campo!r} ({observado!r}) es anterior a la mínima "
            f"permitida ({valor_declarado!r})."
        )
    else:
        viola = fecha_observada > fecha_declarada
        mensaje = (
            f"La fecha máxima observada de {campo!r} ({observado!r}) es posterior a la máxima "
            f"permitida ({valor_declarado!r})."
        )
    if viola:
        return [_res(constraint.severity, codigo, mensaje, campo)]
    return [
        _res(
            checks.STATUS_PASS,
            codigo,
            f"El rango de fechas observado de {campo!r} cumple con {constraint.constraint_id!r}.",
            campo,
        )
    ]


def _regla_invariant(constraint: Any, profile: dict) -> list:
    nota = constraint.params.get("note", "")
    return [
        _res(
            checks.STATUS_WARN,
            CODE_INVARIANT,
            f"Invariante declarativo ({nota!r}), no evaluable automáticamente: Change 0 no admite "
            "un lenguaje de expresiones ejecutable por diseño.",
            constraint.constraint_id,
        )
    ]


def _regla_constraint(constraint: Any, profile: dict) -> list:
    tipo = constraint.constraint_type
    if tipo == "not_null":
        return _regla_not_null(constraint, profile)
    if tipo == "unique":
        return _regla_unique(constraint, profile)
    if tipo == "allowed_values":
        return _regla_allowed_values(constraint, profile)
    if tipo in ("min_value", "max_value"):
        return _regla_min_max_value(constraint, profile)
    if tipo in ("min_length", "max_length"):
        return _regla_length(constraint, profile)
    if tipo in ("date_min", "date_max"):
        return _regla_date_min_max(constraint, profile)
    if tipo == "invariant":
        return _regla_invariant(constraint, profile)
    # Inalcanzable: `constraint_type` ya validado por `core.py` contra `CONSTRAINT_TYPES`.
    raise AssertionError(f"constraint_type inesperado (fuera de CONSTRAINT_TYPES): {tipo!r}")


# --- Funciones públicas (R3/R4) ----------------------------------------------------


def _validate_contract_interno(contract: Any, profile: Any) -> list:
    if not isinstance(contract, datacontracts_core.DataContract):
        return [
            _res(
                checks.STATUS_FAIL,
                CODE_INPUT,
                f"'contract' no es una instancia de DataContract (se recibió "
                f"{type(contract).__name__}).",
                tecnico=True,
            )
        ]

    problema_evidencia = _validar_evidencia(profile)
    if problema_evidencia is not None:
        return [problema_evidencia]

    registros = [
        (CODE_FIELD_MISSING, _regla_field_missing, (contract, profile)),
        (CODE_FIELD_UNEXPECTED, _regla_field_unexpected, (contract, profile)),
        (CODE_TYPE_MISMATCH, _regla_type_mismatch, (contract, profile)),
        (CODE_NULLABILITY, _regla_nullability, (contract, profile)),
        (CODE_KEY, _regla_key, (contract, profile)),
    ]
    for constraint in contract.constraints:
        codigo = _CODIGO_POR_CONSTRAINT_TYPE[constraint.constraint_type]
        registros.append((codigo, _regla_constraint, (constraint, profile)))
    return _ejecutar(registros)


def validate_contract(contract: Any, profile: Any) -> list:
    """Pura: sin I/O, sin guard, sin `Path`. `profile` es un `dict` YA cargado (la forma
    de `profile.json`). Nunca lanza -- ver docstring del módulo."""
    try:
        return _validate_contract_interno(contract, profile)
    except Exception as exc:  # noqa: BLE001 -- contrato: nunca lanza
        return [checks.resultado_de_excepcion("CONTRACT-VALIDATE", exc)]


def _validate_contract_against_profile_file_interno(
    contract: Any, profile_path: Any, repo_root: Any
) -> list:
    ruta = Path(profile_path)
    raiz = Path(repo_root)

    permitido, motivo = verificar_permitido(ruta, raiz)
    if not permitido:
        return [
            _res(
                checks.STATUS_FAIL,
                CODE_EVIDENCE_MISSING,
                "No se puede leer el perfil: ruta denegada por el guard de holdout.",
                tecnico=True,
                detail=motivo,
            )
        ]

    if not ruta.exists() or not ruta.is_file():
        return [
            _res(
                checks.STATUS_FAIL,
                CODE_EVIDENCE_MISSING,
                "El archivo de perfil no existe o no es un archivo regular.",
                tecnico=True,
            )
        ]

    try:
        datos_bytes = ruta.read_bytes()
    except OSError as exc:
        return [
            _res(
                checks.STATUS_FAIL,
                CODE_EVIDENCE_MISSING,
                f"No se pudo leer el archivo de perfil ({type(exc).__name__}).",
                tecnico=True,
            )
        ]

    try:
        perfil = json.loads(datos_bytes)
    except json.JSONDecodeError:
        return [
            _res(
                checks.STATUS_FAIL,
                CODE_EVIDENCE_MISSING,
                "El archivo de perfil no contiene JSON válido.",
                tecnico=True,
            )
        ]

    if not isinstance(perfil, dict):
        return [
            _res(
                checks.STATUS_FAIL,
                CODE_EVIDENCE_MISSING,
                f"El JSON del perfil no es un objeto (dict), es {type(perfil).__name__}.",
                tecnico=True,
            )
        ]

    return validate_contract(contract, perfil)


def validate_contract_against_profile_file(contract: Any, profile_path: Any, repo_root: Any) -> list:
    """Puerta con I/O: guard de holdout (`ds_profile.holdout_guard.verificar_permitido`,
    ANTES de abrir el archivo) -> existencia/tipo de archivo -> lectura -> `json.loads`
    -> delega en `validate_contract`. Nunca lanza."""
    try:
        return _validate_contract_against_profile_file_interno(contract, profile_path, repo_root)
    except Exception as exc:  # noqa: BLE001 -- contrato: nunca lanza
        return [checks.resultado_de_excepcion("CONTRACT-VALIDATE-FILE", exc)]

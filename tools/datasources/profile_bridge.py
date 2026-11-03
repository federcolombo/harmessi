"""Puente `profile.json` (`ds_profile`) -> `SourceObservation` neutral (v0.8
Change 1, `20260928-source-neutral-data-access`, spec R27).

Módulo PURO sobre dicts: sin I/O, sin `os`/`pathlib`/`sys`. Solo importa
stdlib (`datetime`, para `provenance.generated_at`) y `.core` (relativo).
No importa `ds_profile` (ese acoplamiento vive en `file_observer.py`, que
conoce el observer real).

Función pública: `profile_to_observation(profile, source_id) ->
core.SourceObservation`.

## Provenance: quién arma qué (IMPORTANTE para quien componga `runtime.py`)

Este bridge NO conoce el observer real que produjo el perfil (módulo,
`observer_code_sha256`, `source_kind`, facetas pedidas/no soportadas...) --
esa información es responsabilidad de quien invoca el observer (el runtime).
Por eso `profile_to_observation` devuelve una `SourceProvenance`
**placeholder mínima**:

- `source_id`: el mismo `source_id` recibido.
- `observer_id`: `""` (string vacío; NO es un `módulo:callable` válido, es
  intencional -- marca "todavía no asignado por el bridge").
- `observer_code_sha256`: `None`.
- `access_mode`: `"read"`.
- `source_kind`: `None`.
- `generated_at`: el instante actual (UTC, `%Y-%m-%dT%H:%M:%SZ`), calculado
  acá porque `SourceProvenance.__post_init__` exige un ISO-8601 válido para
  poder construir el objeto; el llamador puede sobreescribir este campo (o
  reemplazar la `SourceProvenance` completa) sin costo, ya que
  `content_sha256()` excluye `generated_at` (R7).
- `tool_versions`, `requested_facets`, `unsupported_facets`: vacíos.

El llamador (`file_observer.py`, o cualquier otro compositor) DEBE
sobreescribir esta `SourceProvenance` con los datos reales del observer antes
de persistir la observación (R6, R21). Este bridge nunca omite facetas por
sensibilidad: `omitted_facets` siempre sale `()` (eso también es
responsabilidad del runtime, R22).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from . import core

# ---------------------------------------------------------------------------
# Mapeos fijos (R27)
# ---------------------------------------------------------------------------

_DTYPE_A_FAMILIA = {
    "texto": "string",
    "entero": "integer",
    "flotante": "float",
    "booleano": "boolean",
    "fecha": "temporal",
}

_EXACTITUD_A_EXACTNESS = {
    "exacta": "exact",
    "muestreada": "approximate",
}


def _ahora_utc_iso() -> str:
    """`%Y-%m-%dT%H:%M:%SZ`, formato aceptado por `core._RE_ISO8601`."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _exigir_forma_minima(profile: Any) -> tuple:
    """Gate de forma mínima (R27): `profile` dict con `schema` (dict),
    `columnas_detalle` (dict), `sampling` (dict con `activo` bool), `filas`
    (int >= 0). Devuelve `(schema, columnas_detalle, sampling, filas)` o
    lanza `SourceError(core.CODE_PROFILE_INVALID, ...)`."""
    if not isinstance(profile, dict):
        raise core.SourceError(
            core.CODE_PROFILE_INVALID, f"profile: se esperaba dict, se recibió {type(profile).__name__}"
        )
    schema = profile.get("schema")
    if not isinstance(schema, dict):
        raise core.SourceError(core.CODE_PROFILE_INVALID, "profile.schema: se esperaba dict")
    columnas_detalle = profile.get("columnas_detalle")
    if not isinstance(columnas_detalle, dict):
        raise core.SourceError(core.CODE_PROFILE_INVALID, "profile.columnas_detalle: se esperaba dict")
    sampling = profile.get("sampling")
    if not isinstance(sampling, dict) or not isinstance(sampling.get("activo"), bool):
        raise core.SourceError(
            core.CODE_PROFILE_INVALID, "profile.sampling: se esperaba dict con clave 'activo' bool"
        )
    filas = profile.get("filas")
    if isinstance(filas, bool) or not isinstance(filas, int) or filas < 0:
        raise core.SourceError(core.CODE_PROFILE_INVALID, "profile.filas: se esperaba int >= 0")
    return schema, columnas_detalle, sampling, filas


def _faceta_conteo_exact(valor: int) -> dict:
    return {"value": valor, "exactness": "exact"}


def _construir_facets_campo(detalle: Optional[dict]) -> tuple:
    """Devuelve `(type_family, native_type, facets)` para un campo, dado su
    entrada (o `None`) en `columnas_detalle`."""
    if detalle is None:
        return "unknown", None, {}

    native_type = detalle.get("dtype")
    type_family = _DTYPE_A_FAMILIA.get(native_type, "unknown")

    facets: dict = {}

    # null_count (R27: forma de column_stats.py:266-270).
    nulls = detalle.get("nulls")
    if isinstance(nulls, dict) and isinstance(nulls.get("count"), int) and not isinstance(nulls.get("count"), bool):
        facets["null_count"] = _faceta_conteo_exact(nulls["count"])

    # distinct_count.
    unique = detalle.get("unique")
    exactness_distinct: Optional[str] = None
    if isinstance(unique, dict):
        exactitud = unique.get("exactitud")
        exactness_distinct = _EXACTITUD_A_EXACTNESS.get(exactitud)
        count = unique.get("count")
        if exactness_distinct is not None and isinstance(count, int) and not isinstance(count, bool):
            facets["distinct_count"] = {"value": count, "exactness": exactness_distinct}

    # value_distribution.
    top_valores = detalle.get("top_valores")
    if isinstance(top_valores, list) and top_valores:
        exactness_dist = exactness_distinct if exactness_distinct is not None else "approximate"
        items = [{"value": item["valor"], "frequency": item["frecuencia"]} for item in top_valores]
        completo = (
            isinstance(unique, dict)
            and unique.get("exactitud") == "exacta"
            and isinstance(unique.get("count"), int)
            and not isinstance(unique.get("count"), bool)
            and unique["count"] <= len(top_valores)
        )
        facets["value_distribution"] = {"value": items, "exactness": exactness_dist, "complete": bool(completo)}

    # value_range: solo dtype numérico y con las claves presentes (aunque
    # sean `None` -- "observado y vacío", R31).
    if native_type in ("entero", "flotante") and "min" in detalle and "max" in detalle:
        facets["value_range"] = {"value": {"min": detalle["min"], "max": detalle["max"]}, "exactness": "exact"}

    # time_range: solo dtype fecha.
    if native_type == "fecha" and "fecha_min" in detalle and "fecha_max" in detalle:
        facets["time_range"] = {
            "value": {"min": detalle["fecha_min"], "max": detalle["fecha_max"]},
            "exactness": "exact",
        }

    return type_family, native_type, facets


def _construir_dataset(profile: dict, sampling: dict, filas: int) -> dict:
    dataset: dict = {"row_count": _faceta_conteo_exact(filas)}

    fingerprint = profile.get("fingerprint")
    if isinstance(fingerprint, dict) and "algoritmo" in fingerprint and "hash" in fingerprint:
        dataset["fingerprint"] = {"algorithm": fingerprint["algoritmo"], "value": fingerprint["hash"]}

    seed = sampling.get("seed", sampling.get("semilla"))
    dataset["sampling"] = {
        "active": sampling["activo"],
        "method": sampling.get("metodo"),
        "sample_size": sampling.get("tamano_muestra"),
        "seed": seed,
    }
    return dataset


def profile_to_observation(profile: dict, source_id: str) -> core.SourceObservation:
    """Mapea un dict `profile.json` de `ds_profile` (o un fixture equivalente,
    ver `tools/datacontracts/tests/test_validation.py:22-99`) a una
    `SourceObservation` neutral (R27). Pura: no lanza salvo `SourceError` por
    forma mínima inválida o por `source_id` inválido (propagado desde
    `core`). Ver docstring del módulo para el tratamiento de `provenance`."""
    schema, columnas_detalle, sampling, filas = _exigir_forma_minima(profile)

    campos = []
    for nombre_campo in schema:
        detalle = columnas_detalle.get(nombre_campo)
        type_family, native_type, facets = _construir_facets_campo(detalle)
        campos.append(
            core.FieldObservation(name=nombre_campo, type_family=type_family, native_type=native_type, facets=facets)
        )

    dataset = _construir_dataset(profile, sampling, filas)

    provenance = core.SourceProvenance(
        source_id=source_id,
        observer_id="",
        observer_code_sha256=None,
        access_mode="read",
        source_kind=None,
        generated_at=_ahora_utc_iso(),
        tool_versions={},
        requested_facets=(),
        unsupported_facets=(),
    )

    return core.SourceObservation(
        source_id=source_id,
        provenance=provenance,
        dataset=dataset,
        fields=tuple(campos),
        omitted_facets=(),
    )

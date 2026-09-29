"""Tests de `tools.datasources.profile_bridge` (R27)."""
from __future__ import annotations

import pytest

from tools.datasources import core
from tools.datasources import profile_bridge as pb


# --- Fixtures (mismo estilo que test_validation.py:22-99, no importados) ---


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


def _col_flotante(minimo=None, maximo=None, nulos=0, unique_count=0, exactitud="exacta", top_valores=None):
    return {
        "dtype": "flotante",
        "nulls": {"count": nulos, "pct": 0.0, "exactitud": "exacta"},
        "unique": {"count": unique_count, "exactitud": exactitud},
        "top_valores": top_valores if top_valores is not None else [],
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


def _col_booleano(nulos=0, unique_count=2, exactitud="exacta"):
    return {
        "dtype": "booleano",
        "nulls": {"count": nulos, "pct": 0.0, "exactitud": "exacta"},
        "unique": {"count": unique_count, "exactitud": exactitud},
        "top_valores": [{"valor": "true", "frecuencia": 1}, {"valor": "false", "frecuencia": 1}],
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


_DATASET_PATH_FIXTURE = "/ruta/sensible/no_debe_aparecer/dataset.csv"


def _perfil(schema=None, columnas_detalle=None, sampling_activo=False, tamano_muestra=None, filas=3,
            fingerprint=None, sampling_extra=None):
    sampling = {
        "activo": sampling_activo,
        "metodo": "reservoir_v1",
        "semilla": 42,
        "tamano_muestra": tamano_muestra,
    }
    if sampling_extra:
        sampling.update(sampling_extra)
    perfil = {
        "dataset_path": _DATASET_PATH_FIXTURE,
        "tamano_bytes": 12345,
        "schema": schema if schema is not None else {"id": "entero"},
        "columnas_detalle": columnas_detalle if columnas_detalle is not None else {"id": _col_entera()},
        "sampling": sampling,
        "filas": filas,
    }
    if fingerprint is not None:
        perfil["fingerprint"] = fingerprint
    return perfil


def _recorrer_valores(obj):
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _recorrer_valores(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _recorrer_valores(v)
    else:
        yield obj


# --- Tests -------------------------------------------------------------


def test_perfil_completo_ejercita_todos_los_mapeos():
    schema = {
        "id": "entero",
        "monto": "flotante",
        "nombre": "texto",
        "activo": "booleano",
        "fecha_alta": "fecha",
        "sin_detalle": "entero",
    }
    columnas_detalle = {
        "id": _col_entera(minimo=1, maximo=100, unique_count=3, exactitud="exacta"),
        "monto": _col_flotante(minimo=None, maximo=None, unique_count=0, exactitud="exacta", top_valores=[]),
        "nombre": _col_texto(unique_count=1, exactitud="muestreada"),
        "activo": _col_booleano(),
        "fecha_alta": _col_fecha(fecha_min=None, fecha_max=None),
        # "sin_detalle" deliberadamente ausente de columnas_detalle.
    }
    perfil = _perfil(
        schema=schema,
        columnas_detalle=columnas_detalle,
        sampling_activo=True,
        tamano_muestra=500,
        filas=1000,
        fingerprint={"algoritmo": "sha256/bin/v1", "hash": "abc123"},
        sampling_extra={"seed": 7},
    )

    obs = pb.profile_to_observation(perfil, "customers")

    assert isinstance(obs, core.SourceObservation)
    d = obs.to_dict()

    assert d["source_id"] == "customers"
    assert d["dataset"]["row_count"] == {"value": 1000, "exactness": "exact"}
    assert d["dataset"]["fingerprint"] == {"algorithm": "sha256/bin/v1", "value": "abc123"}
    assert d["dataset"]["sampling"] == {"active": True, "method": "reservoir_v1", "sample_size": 500, "seed": 7}

    campos = {c["name"]: c for c in d["fields"]}

    assert campos["id"]["type_family"] == "integer"
    assert campos["id"]["native_type"] == "entero"
    assert campos["id"]["facets"]["value_range"] == {"value": {"min": 1, "max": 100}, "exactness": "exact"}
    assert campos["id"]["facets"]["distinct_count"] == {"value": 3, "exactness": "exact"}

    assert campos["monto"]["type_family"] == "float"
    # min/max None (observado y vacío, R31): faceta presente, exact, con None.
    assert campos["monto"]["facets"]["value_range"] == {"value": {"min": None, "max": None}, "exactness": "exact"}
    # top_valores vacío -> value_distribution no se escribe.
    assert "value_distribution" not in campos["monto"]["facets"]

    assert campos["nombre"]["type_family"] == "string"
    assert campos["nombre"]["facets"]["distinct_count"] == {"value": 1, "exactness": "approximate"}
    assert campos["nombre"]["facets"]["value_distribution"]["exactness"] == "approximate"
    assert "value_range" not in campos["nombre"]["facets"]
    assert "time_range" not in campos["nombre"]["facets"]

    assert campos["activo"]["type_family"] == "boolean"

    assert campos["fecha_alta"]["type_family"] == "temporal"
    assert campos["fecha_alta"]["facets"]["time_range"] == {"value": {"min": None, "max": None}, "exactness": "exact"}

    # Campo en schema sin entrada en columnas_detalle -> unknown, sin lanzar.
    assert campos["sin_detalle"]["type_family"] == "unknown"
    assert campos["sin_detalle"]["native_type"] is None
    assert campos["sin_detalle"]["facets"] == {}


def test_sampling_lee_seed_o_semilla():
    perfil = _perfil(sampling_activo=False, tamano_muestra=None)
    obs = pb.profile_to_observation(perfil, "customers")
    assert obs.to_dict()["dataset"]["sampling"]["seed"] == 42  # 'semilla', sin 'seed'.


def test_sampling_con_seed_explicito_tiene_prioridad():
    perfil = _perfil(sampling_activo=False, sampling_extra={"seed": 99})
    obs = pb.profile_to_observation(perfil, "customers")
    assert obs.to_dict()["dataset"]["sampling"]["seed"] == 99


def test_fingerprint_ausente_no_escribe_faceta():
    perfil = _perfil()
    obs = pb.profile_to_observation(perfil, "customers")
    assert "fingerprint" not in obs.to_dict()["dataset"]


def test_top_valores_con_unique_exacto_y_completo():
    columnas_detalle = {"id": _col_entera(unique_count=3, exactitud="exacta")}
    perfil = _perfil(columnas_detalle=columnas_detalle)
    obs = pb.profile_to_observation(perfil, "customers")
    campo = obs.to_dict()["fields"][0]
    assert campo["facets"]["value_distribution"]["complete"] is True


def test_top_valores_sin_unique_usa_approximate_por_defecto():
    columnas_detalle = {
        "id": {
            "dtype": "texto",
            "nulls": {"count": 0, "pct": 0.0, "exactitud": "exacta"},
            "top_valores": [{"valor": "a", "frecuencia": 1}],
        }
    }
    perfil = _perfil(schema={"id": "texto"}, columnas_detalle=columnas_detalle)
    obs = pb.profile_to_observation(perfil, "customers")
    campo = obs.to_dict()["fields"][0]
    assert campo["facets"]["value_distribution"]["exactness"] == "approximate"
    assert campo["facets"]["value_distribution"]["complete"] is False
    assert "distinct_count" not in campo["facets"]


def test_dataset_path_nunca_aparece_en_el_resultado():
    perfil = _perfil(fingerprint={"algoritmo": "sha256/bin/v1", "hash": "abc123"})
    obs = pb.profile_to_observation(perfil, "customers")
    d = obs.to_dict()
    for valor in _recorrer_valores(d):
        if isinstance(valor, str):
            assert _DATASET_PATH_FIXTURE not in valor
    # También confirmamos que 'tamano_bytes' no se copió a ningún lado.
    assert 12345 not in list(_recorrer_valores(d))


def test_perfil_sin_columnas_detalle_lanza_source_error():
    perfil = _perfil()
    del perfil["columnas_detalle"]
    with pytest.raises(core.SourceError) as exc_info:
        pb.profile_to_observation(perfil, "customers")
    assert exc_info.value.code == core.CODE_PROFILE_INVALID


def test_perfil_sin_schema_lanza_source_error():
    perfil = _perfil()
    del perfil["schema"]
    with pytest.raises(core.SourceError) as exc_info:
        pb.profile_to_observation(perfil, "customers")
    assert exc_info.value.code == core.CODE_PROFILE_INVALID


def test_perfil_sin_sampling_activo_bool_lanza_source_error():
    perfil = _perfil()
    perfil["sampling"] = {"activo": "si"}
    with pytest.raises(core.SourceError) as exc_info:
        pb.profile_to_observation(perfil, "customers")
    assert exc_info.value.code == core.CODE_PROFILE_INVALID


def test_perfil_no_dict_lanza_source_error():
    with pytest.raises(core.SourceError) as exc_info:
        pb.profile_to_observation(["no", "es", "dict"], "customers")
    assert exc_info.value.code == core.CODE_PROFILE_INVALID


def test_campo_en_schema_sin_entrada_en_columnas_detalle_no_lanza():
    perfil = _perfil(schema={"id": "entero", "huerfano": "texto"}, columnas_detalle={"id": _col_entera()})
    obs = pb.profile_to_observation(perfil, "customers")
    campos = {c["name"]: c for c in obs.to_dict()["fields"]}
    assert campos["huerfano"]["type_family"] == "unknown"


def test_orden_de_campos_sigue_orden_de_schema():
    schema = {"c": "entero", "a": "entero", "b": "entero"}
    columnas_detalle = {k: _col_entera() for k in schema}
    perfil = _perfil(schema=schema, columnas_detalle=columnas_detalle)
    obs = pb.profile_to_observation(perfil, "customers")
    nombres = [c["name"] for c in obs.to_dict()["fields"]]
    assert nombres == ["c", "a", "b"]


def test_omitted_facets_siempre_vacio():
    perfil = _perfil()
    obs = pb.profile_to_observation(perfil, "customers")
    assert obs.to_dict()["omitted_facets"] == []


def test_provenance_placeholder_tiene_observer_id_vacio():
    perfil = _perfil()
    obs = pb.profile_to_observation(perfil, "customers")
    prov = obs.to_dict()["provenance"]
    assert prov["observer_id"] == ""
    assert prov["access_mode"] == "read"
    assert prov["source_id"] == "customers"

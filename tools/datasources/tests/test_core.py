"""Tests de `tools.datasources.core` (R1, R3, R4-R11)."""
from __future__ import annotations

import ast
import os

import pytest

from tools.autonomy.core import SOURCE_ID_PATTERN as SOURCE_ID_PATTERN_AUTONOMY
from tools.datasources import core


# ---------------------------------------------------------------------------
# R1/R3 -- imports permitidos, ast
# ---------------------------------------------------------------------------

_IMPORTS_PERMITIDOS = {"dataclasses", "typing", "re", "json", "hashlib", "unicodedata", "__future__"}


def test_core_solo_importa_stdlib_permitido():
    ruta = os.path.join(os.path.dirname(__file__), "..", "core.py")
    with open(ruta, "r", encoding="utf-8") as f:
        arbol = ast.parse(f.read(), filename="core.py")
    encontrados = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            for alias in nodo.names:
                encontrados.add(alias.name.split(".")[0])
        elif isinstance(nodo, ast.ImportFrom):
            if nodo.module is not None:
                encontrados.add(nodo.module.split(".")[0])
    assert encontrados <= _IMPORTS_PERMITIDOS, f"imports no permitidos: {encontrados - _IMPORTS_PERMITIDOS}"


def test_core_no_ramifica_sobre_literales_de_tecnologia():
    tecnologias = ("sql", "parquet", "csv", "postgres", "snowflake", "bigquery", "s3", "http")
    ruta = os.path.join(os.path.dirname(__file__), "..", "core.py")
    with open(ruta, "r", encoding="utf-8") as f:
        arbol = ast.parse(f.read(), filename="core.py")
    for nodo in ast.walk(arbol):
        if isinstance(nodo, (ast.Compare,)):
            for comparador in nodo.comparators:
                if isinstance(comparador, ast.Constant) and isinstance(comparador.value, str):
                    assert comparador.value.lower() not in tecnologias


# ---------------------------------------------------------------------------
# SOURCE_ID_PATTERN paridad con autonomy
# ---------------------------------------------------------------------------


def test_source_id_pattern_identico_a_autonomy():
    assert core.SOURCE_ID_PATTERN == SOURCE_ID_PATTERN_AUTONOMY


# ---------------------------------------------------------------------------
# R9 -- CODES único y completo
# ---------------------------------------------------------------------------


def test_codes_sin_duplicados():
    assert len(core.CODES) == len(set(core.CODES))


def test_codes_tiene_27_codigos():
    assert len(core.CODES) == 27


def test_codes_todos_empiezan_con_source():
    assert all(c.startswith("SOURCE-") for c in core.CODES)


# ---------------------------------------------------------------------------
# R4 -- SourceRef / source_id
# ---------------------------------------------------------------------------

_SOURCE_ID_RECHAZADOS = (
    "dbo.Clientes.Productores",
    "project.dataset.customers",
    "/v2/customers",
    "data/raw/customers.parquet",
)


@pytest.mark.parametrize("source_id", _SOURCE_ID_RECHAZADOS)
def test_source_id_ejemplos_rechazados(source_id):
    d = _source_ref_dict(source_id=source_id)
    with pytest.raises(core.SourceError) as exc:
        core.SourceRef.from_dict(d)
    assert exc.value.code == core.CODE_ID_INVALID


def test_source_id_customers_aceptado():
    d = _source_ref_dict(source_id="customers")
    ref = core.SourceRef.from_dict(d)
    assert ref.source_id == "customers"


def _source_ref_dict(**overrides) -> dict:
    base = {
        "source_id": "customers",
        "role": "raw_table",
        "observer": "proyecto.observers:factory",
        "access_mode": "read",
        "sensitivity": "internal",
    }
    base.update(overrides)
    return base


def test_source_ref_access_mode_write_es_rechazado_en_from_dict():
    d = _source_ref_dict(access_mode="write")
    with pytest.raises(core.SourceError) as exc:
        core.SourceRef.from_dict(d)
    assert exc.value.code == core.CODE_ACCESS_MODE_RESERVED


def test_source_ref_access_mode_otro_valor_es_registry_invalid():
    d = _source_ref_dict(access_mode="readwrite")
    with pytest.raises(core.SourceError) as exc:
        core.SourceRef.from_dict(d)
    assert exc.value.code == core.CODE_REGISTRY_INVALID


def test_source_ref_construccion_directa_acepta_access_mode_write():
    # El dataclass en sí no valida el vocabulario reservado (spec R4): solo
    # `from_dict`/`validate_source_ref` lo rechazan.
    ref = core.SourceRef(
        source_id="customers",
        role="raw_table",
        observer="proyecto.observers:factory",
        access_mode="write",
        sensitivity="internal",
    )
    assert ref.access_mode == "write"


def test_source_ref_sensitivity_sealed_invalida():
    d = _source_ref_dict(sensitivity="sealed")
    with pytest.raises(core.SourceError) as exc:
        core.SourceRef.from_dict(d)
    assert exc.value.code == core.CODE_SENSITIVITY_INVALID


def test_source_ref_config_ref_valido():
    d = _source_ref_dict(config_ref="env:CUSTOMERS_DSN")
    ref = core.SourceRef.from_dict(d)
    assert ref.config_ref == "env:CUSTOMERS_DSN"


def test_source_ref_config_ref_invalido():
    d = _source_ref_dict(config_ref="CUSTOMERS_DSN")
    with pytest.raises(core.SourceError) as exc:
        core.SourceRef.from_dict(d)
    assert exc.value.code == core.CODE_CONFIG_REF_INVALID


def test_source_ref_options_profundidad_excedida():
    anidado = {"a": {"b": {"c": {"d": {"e": 1}}}}}
    d = _source_ref_dict(options=anidado)
    with pytest.raises(core.SourceError) as exc:
        core.SourceRef.from_dict(d)
    assert exc.value.code == core.CODE_OPTIONS_INVALID


def test_source_ref_options_roundtrip():
    d = _source_ref_dict(options={"table": "dbo.Clientes.Productores"})
    ref = core.SourceRef.from_dict(d)
    assert ref.to_dict()["options"] == {"table": "dbo.Clientes.Productores"}


def test_source_ref_extra_requiere_prefijo_x():
    d = _source_ref_dict(extra={"nota": "sin prefijo"})
    with pytest.raises(core.SourceError):
        core.SourceRef.from_dict(d)


def test_source_ref_extra_con_prefijo_ok():
    d = _source_ref_dict(extra={"x_nota": "ok"})
    ref = core.SourceRef.from_dict(d)
    assert ref.extra == {"x_nota": "ok"}


# ---------------------------------------------------------------------------
# R10 -- SourceCapabilities
# ---------------------------------------------------------------------------


def test_capabilities_execute_query_invalida():
    with pytest.raises(core.SourceError) as exc:
        core.validate_capabilities({"facets": {}, "operations": ["execute_query"]})
    assert exc.value.code == core.CODE_CAPABILITIES_INVALID


def test_capabilities_faceta_desconocida_invalida():
    with pytest.raises(core.SourceError) as exc:
        core.SourceCapabilities.from_dict({"facets": {"execute_query": ["exact"]}, "operations": []})
    assert exc.value.code == core.CODE_CAPABILITIES_INVALID


def test_capabilities_validas_roundtrip():
    caps = core.SourceCapabilities.from_dict(
        {"facets": {"row_count": ["exact"], "null_count": ["exact", "approximate"]}, "operations": ["read", "sample"]}
    )
    d = caps.to_dict()
    assert d["facets"]["row_count"] == ["exact"]
    assert set(d["operations"]) == {"read", "sample"}


def test_capabilities_exactitud_vacia_invalida():
    with pytest.raises(core.SourceError):
        core.SourceCapabilities.from_dict({"facets": {"row_count": []}, "operations": []})


# ---------------------------------------------------------------------------
# R11 -- ObservationRequest
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("clave", ["query", "sql", "statement"])
def test_observation_request_rechaza_texto_de_consulta(clave):
    d = {"source_id": "customers", clave: "select * from x"}
    with pytest.raises(core.SourceError) as exc:
        core.ObservationRequest.from_dict(d)
    assert exc.value.code == core.CODE_OBSERVATION_INVALID


def test_observation_request_serializa_a_dict_json_puro():
    req = core.ObservationRequest(source_id="customers", facets=("row_count", "null_count"), exactness="exact")
    d = req.to_dict()
    assert d == {
        "source_id": "customers",
        "facets": ["row_count", "null_count"],
        "exactness": "exact",
        "as_of": None,
        "max_rows": None,
        "sample_size": None,
    }


def test_observation_request_max_rows_debe_ser_positivo():
    with pytest.raises(core.SourceError):
        core.ObservationRequest(source_id="customers", max_rows=0)


def test_observation_request_as_of_iso8601():
    req = core.ObservationRequest(source_id="customers", as_of="2026-09-29")
    assert req.as_of == "2026-09-29"
    with pytest.raises(core.SourceError):
        core.ObservationRequest(source_id="customers", as_of="29-09-2026")


# ---------------------------------------------------------------------------
# R5/R7 -- SourceObservation: round-trip, hash, ausencia != 0
# ---------------------------------------------------------------------------


def _provenance(generated_at="2026-09-29T10:00:00Z") -> core.SourceProvenance:
    return core.SourceProvenance(
        source_id="customers",
        observer_id="proyecto.observers:factory",
        observer_code_sha256="a" * 64,
        access_mode="read",
        source_kind="table",
        generated_at=generated_at,
        tool_versions={"harmessi": "0.8.0"},
        requested_facets=("row_count",),
        unsupported_facets=(),
    )


def _observation(generated_at="2026-09-29T10:00:00Z") -> core.SourceObservation:
    campo = core.FieldObservation(
        name="id",
        type_family="integer",
        native_type="int64",
        facets={"null_count": {"value": 0, "exactness": "exact"}},
    )
    return core.SourceObservation(
        source_id="customers",
        provenance=_provenance(generated_at),
        dataset={"row_count": {"value": 100, "exactness": "exact"}},
        fields=(campo,),
        omitted_facets=(),
    )


def test_observation_roundtrip_from_dict_to_dict():
    obs = _observation()
    d = obs.to_dict()
    obs2 = core.SourceObservation.from_dict(d)
    assert obs2.to_dict() == d


def test_observation_to_dict_orden_de_claves_primer_nivel():
    obs = _observation()
    claves = list(obs.to_dict().keys())
    assert claves == ["schema_version", "source_id", "provenance", "dataset", "fields", "omitted_facets"]


def test_observation_hash_ignora_generated_at():
    obs_a = _observation(generated_at="2026-09-29T10:00:00Z")
    obs_b = _observation(generated_at="2026-09-30T11:30:00Z")
    assert obs_a.content_sha256() == obs_b.content_sha256()


def test_observation_hash_cambia_con_otro_campo():
    obs_a = _observation()
    campo = core.FieldObservation(name="id", type_family="integer", native_type="int64", facets={})
    obs_c = core.SourceObservation(
        source_id="customers",
        provenance=_provenance(),
        dataset={"row_count": {"value": 999, "exactness": "exact"}},
        fields=(campo,),
        omitted_facets=(),
    )
    assert obs_a.content_sha256() != obs_c.content_sha256()


def test_observation_ausencia_de_null_count_no_materializa_cero():
    d = _observation().to_dict()
    # Sin `null_count` en el dict de entrada de un campo: `from_dict` no debe
    # inventar `null_count: 0`.
    d["fields"] = [{"name": "id", "type_family": "integer", "native_type": "int64", "facets": {}}]
    obs = core.SourceObservation.from_dict(d)
    assert "null_count" not in obs.fields[0].facets
    assert obs.fields[0].to_dict()["facets"] == {}


def test_observation_value_range_observado_y_vacio():
    campo = core.FieldObservation(
        name="monto",
        type_family="float",
        native_type="float64",
        facets={"value_range": {"value": {"min": None, "max": None}, "exactness": "exact"}},
    )
    assert campo.facets["value_range"]["value"] == {"min": None, "max": None}


def test_observation_nombres_de_campo_duplicados_invalido():
    campo1 = core.FieldObservation(name="id", type_family="integer", native_type="int64", facets={})
    campo2 = core.FieldObservation(name="id", type_family="string", native_type="text", facets={})
    with pytest.raises(core.SourceError) as exc:
        core.SourceObservation(
            source_id="customers", provenance=_provenance(), dataset={}, fields=(campo1, campo2)
        )
    assert exc.value.code == core.CODE_OBSERVATION_INVALID

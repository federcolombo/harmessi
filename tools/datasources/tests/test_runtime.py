"""Tests de `tools.datasources.runtime` (R13, R16, R18-R23, R26).

Observers de prueba EN MEMORIA (funciones/clases de este propio módulo, sin
archivos ni SQL): se referencian como
`"tools.datasources.tests.test_runtime:_factory_..."` -- `importlib` los
resuelve contra el módulo de test ya cargado por pytest, sin escribir nada al
disco. Los dos escenarios que exigen verificar que un módulo NO se importa
(orden de R16, estática de R13) sí escriben un módulo señuelo real a un
directorio temporal (nunca importado hasta ese momento), porque un módulo ya
cargado en `sys.modules` no vuelve a ejecutar su cuerpo al reimportarse.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from tools.datasources import core, runtime
from tools.dsguard import checks


# ---------------------------------------------------------------------------
# Helpers de fixtures
# ---------------------------------------------------------------------------


def _fuente(**overrides) -> dict:
    base = {
        "source_id": "customers",
        "role": "raw_table",
        "observer": "tools.datasources.tests.test_runtime:_factory_ok",
        "access_mode": "read",
        "sensitivity": "internal",
    }
    base.update(overrides)
    return base


def _escribir_registro(repo_root: Path, *fuentes) -> None:
    directorio = repo_root / ".harmessi"
    directorio.mkdir(parents=True, exist_ok=True)
    (directorio / "sources.json").write_text(
        json.dumps({"schema_version": 1, "sources": list(fuentes)}), encoding="utf-8"
    )


def _codigos(resultados) -> list:
    return [r.code for r in resultados]


def _escribir_modulo_senuelo(tmp_dir: Path, nombre_modulo: str, marcador: Path) -> None:
    """Escribe un módulo real (nunca antes importado) que, si se importa,
    escribe `marcador` a disco. Usado para probar que `check_registry` y el
    corte temprano de `access_check` NUNCA importan el observer."""
    codigo = (
        "import pathlib\n"
        f"pathlib.Path({str(marcador)!r}).write_text('importado', encoding='utf-8')\n"
        "\n"
        "def factory(source_id, options):\n"
        "    class _Obs:\n"
        "        def capabilities(self):\n"
        "            return {'facets': {}, 'operations': []}\n"
        "        def observe(self, request):\n"
        "            return {'dataset': {}, 'fields': []}\n"
        "    return _Obs()\n"
    )
    (tmp_dir / f"{nombre_modulo}.py").write_text(codigo, encoding="utf-8")


def _access_check_permite(source_id, access_mode):
    return True, ""


def _access_check_deniega_sellada(source_id, access_mode):
    return False, "fuente sellada por policy humana"


def _access_check_deniega_generico(source_id, access_mode):
    return False, "no autorizado por policy"


# ---------------------------------------------------------------------------
# Observers en memoria
# ---------------------------------------------------------------------------


class _ObserverOK:
    def capabilities(self):
        return {"facets": {"row_count": ["exact"], "null_count": ["exact"]}, "operations": []}

    def observe(self, request):
        return {
            "dataset": {"row_count": {"value": 10, "exactness": "exact"}},
            "fields": [
                {
                    "name": "id",
                    "type_family": "integer",
                    "native_type": "int64",
                    "facets": {"null_count": {"value": 0, "exactness": "exact"}},
                }
            ],
        }


def _factory_ok(source_id, options):
    return _ObserverOK()


def _factory_raise(source_id, options):
    raise RuntimeError("boom en factory, /var/segredos/algo no debe verse completo")


class _ObserverCapsRaise:
    def capabilities(self):
        raise ValueError("boom capabilities")

    def observe(self, request):  # pragma: no cover - no debería llegar acá
        return {"dataset": {}, "fields": []}


def _factory_caps_raise(source_id, options):
    return _ObserverCapsRaise()


class _ObserverObserveRaise:
    def capabilities(self):
        return {"facets": {"row_count": ["exact"]}, "operations": []}

    def observe(self, request):
        raise RuntimeError("boom observe")


def _factory_observe_raise(source_id, options):
    return _ObserverObserveRaise()


class _ObserverCapsInvalid:
    def capabilities(self):
        return {"facets": {"execute_query": ["exact"]}, "operations": []}

    def observe(self, request):  # pragma: no cover
        return {"dataset": {}, "fields": []}


def _factory_caps_invalid(source_id, options):
    return _ObserverCapsInvalid()


class _ObserverFacetExtra:
    def capabilities(self):
        return {"facets": {"row_count": ["exact"]}, "operations": []}

    def observe(self, request):
        if "null_count" in request.get("facets", []):
            # Si esto se ejecuta, el runtime le pidió al observer una faceta
            # que el propio observer nunca declaró como soportada (bug real
            # de runtime.py, no del test) -- se hace explotar la corrida
            # para que quede como technical_error, nunca como un PASS mudo.
            raise AssertionError(
                "el runtime pidio 'null_count', una faceta no declarada por capabilities()"
            )
        return {"dataset": {"row_count": {"value": 5, "exactness": "exact"}}, "fields": []}


def _factory_facet_extra(source_id, options):
    return _ObserverFacetExtra()


class _ObserverSecreto:
    def capabilities(self):
        return {"facets": {"row_count": ["exact"]}, "operations": []}

    def observe(self, request):
        return {
            "dataset": {"row_count": {"value": 1, "exactness": "exact"}},
            "fields": [
                {
                    "name": "archivo",
                    "type_family": "string",
                    "native_type": "C:\\datos\\clientes.csv",
                    "facets": {},
                }
            ],
        }


def _factory_secreto(source_id, options):
    return _ObserverSecreto()


class _ObserverSensible:
    def capabilities(self):
        return {"facets": {"row_count": ["exact"], "value_range": ["exact"]}, "operations": []}

    def observe(self, request):
        return {
            "dataset": {"row_count": {"value": 3, "exactness": "exact"}},
            "fields": [
                {
                    "name": "edad",
                    "type_family": "integer",
                    "native_type": "int64",
                    "facets": {"value_range": {"value": {"min": 1, "max": 90}, "exactness": "exact"}},
                }
            ],
        }


def _factory_sensible(source_id, options):
    return _ObserverSensible()


# ---------------------------------------------------------------------------
# load_registry / check_registry
# ---------------------------------------------------------------------------


def test_load_registry_ausente():
    with tempfile.TemporaryDirectory() as tmp:
        data, resultados = runtime.load_registry(tmp)
        assert data is None
        assert resultados[0].status == checks.STATUS_WARN
        assert resultados[0].code == core.CODE_REGISTRY_MISSING


def test_load_registry_json_ilegible():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / ".harmessi").mkdir()
        (tmp_path / ".harmessi" / "sources.json").write_text("{no es json", encoding="utf-8")
        data, resultados = runtime.load_registry(tmp)
        assert data is None
        assert resultados[0].status == checks.STATUS_FAIL
        assert resultados[0].code == core.CODE_REGISTRY_INVALID
        assert resultados[0].kind == checks.KIND_TECHNICAL_ERROR


def test_load_registry_valido():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _escribir_registro(tmp_path, _fuente())
        data, resultados = runtime.load_registry(tmp)
        assert resultados == []
        assert data["sources"][0]["source_id"] == "customers"


def test_check_registry_no_importa_el_observer():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        marcador = tmp_path / "marcador.txt"
        nombre_modulo = "_rt_senuelo_check"
        _escribir_modulo_senuelo(tmp_path, nombre_modulo, marcador)
        _escribir_registro(tmp_path, _fuente(observer=f"{nombre_modulo}:factory"))

        resultados = runtime.check_registry(tmp)

        assert not marcador.exists()
        assert nombre_modulo not in sys.modules
        assert core.CODE_OBSERVER_UNRESOLVED not in _codigos(resultados)  # el archivo existe: resuelve bien, solo no se IMPORTA (eso es lo que este test verifica)
        for r in resultados:
            assert r.status != checks.STATUS_FAIL or r.code != core.CODE_REGISTRY_INVALID


def test_check_registry_registro_ausente_da_warn():
    with tempfile.TemporaryDirectory() as tmp:
        resultados = runtime.check_registry(tmp)
        assert _codigos(resultados) == [core.CODE_REGISTRY_MISSING]


# ---------------------------------------------------------------------------
# observe_source: orden (R16) y access_check
# ---------------------------------------------------------------------------


def test_observe_source_sin_access_check_deniega_fail_closed():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _escribir_registro(tmp_path, _fuente())
        observation, resultados = runtime.observe_source(tmp, "customers", {"source_id": "customers"}, None)
        assert observation is None
        assert _codigos(resultados) == [core.CODE_ACCESS_DENIED]


def test_observe_source_access_check_deniega_no_importa_observer():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        marcador = tmp_path / "marcador_deny.txt"
        nombre_modulo = "_rt_senuelo_deny"
        _escribir_modulo_senuelo(tmp_path, nombre_modulo, marcador)
        sys.path.insert(0, str(tmp_path))
        try:
            _escribir_registro(tmp_path, _fuente(observer=f"{nombre_modulo}:factory"))
            observation, resultados = runtime.observe_source(
                tmp, "customers", {"source_id": "customers"}, _access_check_deniega_sellada
            )
            assert observation is None
            assert _codigos(resultados) == [core.CODE_SEALED]
            assert not marcador.exists()
            assert nombre_modulo not in sys.modules
        finally:
            sys.modules.pop(nombre_modulo, None)
            if str(tmp_path) in sys.path:
                sys.path.remove(str(tmp_path))


def test_observe_source_access_check_deniega_generico():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _escribir_registro(tmp_path, _fuente())
        observation, resultados = runtime.observe_source(
            tmp, "customers", {"source_id": "customers"}, _access_check_deniega_generico
        )
        assert observation is None
        assert _codigos(resultados) == [core.CODE_ACCESS_DENIED]


def test_observe_source_access_check_lanza_excepcion():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _escribir_registro(tmp_path, _fuente())

        def _access_check_rompe(source_id, access_mode):
            raise RuntimeError("boom access_check")

        observation, resultados = runtime.observe_source(
            tmp, "customers", {"source_id": "customers"}, _access_check_rompe
        )
        assert observation is None
        assert _codigos(resultados) == [core.CODE_ACCESS_DENIED]


def test_observe_source_fuente_desconocida():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _escribir_registro(tmp_path, _fuente())
        observation, resultados = runtime.observe_source(
            tmp, "no_existe", {"source_id": "no_existe"}, _access_check_permite
        )
        assert observation is None
        assert _codigos(resultados) == [core.CODE_UNKNOWN]


# ---------------------------------------------------------------------------
# observe_source: éxito y persistencia
# ---------------------------------------------------------------------------


def test_observe_source_exito_persiste():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _escribir_registro(tmp_path, _fuente())
        observation, resultados = runtime.observe_source(
            tmp,
            "customers",
            {"source_id": "customers", "facets": ["row_count", "null_count"]},
            _access_check_permite,
        )
        assert observation is not None
        assert not any(r.status == checks.STATUS_FAIL for r in resultados)
        assert observation.provenance.observer_id == "tools.datasources.tests.test_runtime:_factory_ok"
        assert observation.provenance.observer_code_sha256 is not None

        observaciones_dir = tmp_path / ".harmessi" / "observations"
        subdirs = list(observaciones_dir.iterdir())
        assert len(subdirs) == 1
        archivo = subdirs[0] / "observation.json"
        assert archivo.is_file()
        persistido = json.loads(archivo.read_text(encoding="utf-8"))
        assert persistido["source_id"] == "customers"


def test_observe_source_es_idempotente():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _escribir_registro(tmp_path, _fuente())
        req = {"source_id": "customers", "facets": ["row_count", "null_count"]}
        obs1, res1 = runtime.observe_source(tmp, "customers", req, _access_check_permite)
        obs2, res2 = runtime.observe_source(tmp, "customers", req, _access_check_permite)
        assert obs1 is not None and obs2 is not None
        assert not any(r.status == checks.STATUS_FAIL for r in res2)


# ---------------------------------------------------------------------------
# observe_source: excepciones del observer (technical_error)
# ---------------------------------------------------------------------------


def test_observe_source_factory_lanza():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _escribir_registro(
            tmp_path, _fuente(observer="tools.datasources.tests.test_runtime:_factory_raise")
        )
        observation, resultados = runtime.observe_source(
            tmp, "customers", {"source_id": "customers"}, _access_check_permite
        )
        assert observation is None
        assert _codigos(resultados) == [core.CODE_OBSERVER_ERROR]
        assert resultados[0].kind == checks.KIND_TECHNICAL_ERROR


def test_observe_source_modulo_inexistente():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _escribir_registro(
            tmp_path, _fuente(observer="modulo_que_no_existe_para_nada:factory")
        )
        observation, resultados = runtime.observe_source(
            tmp, "customers", {"source_id": "customers"}, _access_check_permite
        )
        assert observation is None
        assert _codigos(resultados) == [core.CODE_OBSERVER_ERROR]


def test_observe_source_capabilities_lanza():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _escribir_registro(
            tmp_path, _fuente(observer="tools.datasources.tests.test_runtime:_factory_caps_raise")
        )
        observation, resultados = runtime.observe_source(
            tmp, "customers", {"source_id": "customers"}, _access_check_permite
        )
        assert observation is None
        assert _codigos(resultados) == [core.CODE_OBSERVER_ERROR]


def test_observe_source_observe_lanza():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _escribir_registro(
            tmp_path, _fuente(observer="tools.datasources.tests.test_runtime:_factory_observe_raise")
        )
        observation, resultados = runtime.observe_source(
            tmp, "customers", {"source_id": "customers"}, _access_check_permite
        )
        assert observation is None
        assert _codigos(resultados) == [core.CODE_OBSERVER_ERROR]


def test_observe_source_capabilities_invalidas():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _escribir_registro(
            tmp_path, _fuente(observer="tools.datasources.tests.test_runtime:_factory_caps_invalid")
        )
        observation, resultados = runtime.observe_source(
            tmp, "customers", {"source_id": "customers"}, _access_check_permite
        )
        assert observation is None
        assert _codigos(resultados) == [core.CODE_CAPABILITIES_INVALID]


# ---------------------------------------------------------------------------
# observe_source: facetas no declaradas nunca se piden al observer
# ---------------------------------------------------------------------------


def test_observe_source_faceta_no_declarada_no_se_pide():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _escribir_registro(
            tmp_path, _fuente(observer="tools.datasources.tests.test_runtime:_factory_facet_extra")
        )
        observation, resultados = runtime.observe_source(
            tmp,
            "customers",
            {"source_id": "customers", "facets": ["row_count", "null_count"]},
            _access_check_permite,
        )
        # Si el runtime le hubiera pedido 'null_count' al observer (que solo
        # declara 'row_count'), el observer de prueba explota -> observation
        # es None. Que sea != None prueba que la faceta no declarada NUNCA
        # llegó al observer.
        assert observation is not None
        assert core.CODE_FACET_UNSUPPORTED in _codigos(resultados)
        assert observation.provenance.unsupported_facets == ("null_count",)


# ---------------------------------------------------------------------------
# observe_source: gate de portabilidad/secretos (R19/R20)
# ---------------------------------------------------------------------------


def test_observe_source_ruta_absoluta_no_persiste_nada():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _escribir_registro(
            tmp_path, _fuente(observer="tools.datasources.tests.test_runtime:_factory_secreto")
        )
        observation, resultados = runtime.observe_source(
            tmp, "customers", {"source_id": "customers", "facets": ["row_count"]}, _access_check_permite
        )
        assert observation is None
        assert core.CODE_ABSOLUTE_PATH in _codigos(resultados)
        assert all(r.status == checks.STATUS_FAIL for r in resultados)
        observaciones_dir = tmp_path / ".harmessi" / "observations"
        assert not observaciones_dir.exists() or list(observaciones_dir.iterdir()) == []


# ---------------------------------------------------------------------------
# observe_source: sensibilidad (R22)
# ---------------------------------------------------------------------------


def test_observe_source_sensitive_omite_facetas():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _escribir_registro(
            tmp_path,
            _fuente(
                observer="tools.datasources.tests.test_runtime:_factory_sensible",
                sensitivity="sensitive",
            ),
        )
        observation, resultados = runtime.observe_source(
            tmp,
            "customers",
            {"source_id": "customers", "facets": ["row_count", "value_range"]},
            _access_check_permite,
        )
        assert observation is not None
        assert core.CODE_FACET_OMITTED in _codigos(resultados)
        campo_edad = [c for c in observation.fields if c.name == "edad"][0]
        assert "value_range" not in campo_edad.facets
        assert len(observation.omitted_facets) == 1
        assert observation.omitted_facets[0]["reason"] == "sensitivity"

        # verificacion directa sobre el archivo persistido: la faceta omitida
        # SI debe aparecer registrada en omitted_facets (R22), pero NUNCA como
        # valor observado dentro de fields[].facets de ningun campo.
        observaciones_dir = tmp_path / ".harmessi" / "observations"
        archivo = next(observaciones_dir.glob("*/observation.json"))
        persistido = json.loads(archivo.read_text(encoding="utf-8"))
        for campo in persistido["fields"]:
            assert "value_range" not in campo["facets"]
        assert any(
            o["facet"] == "value_range" and o["field"] == "edad"
            for o in persistido["omitted_facets"]
        )


# ---------------------------------------------------------------------------
# compare_fingerprint (R26, 6 casos)
# ---------------------------------------------------------------------------


def _obs(source_id="customers", fingerprint=None, algorithm="sha256", as_of=None):
    dataset: dict = {}
    if fingerprint is not None:
        dataset["fingerprint"] = {"algorithm": algorithm, "value": fingerprint}
    if as_of is not None:
        dataset["snapshot"] = {"as_of": as_of}
    return {"source_id": source_id, "dataset": dataset}


def test_compare_fingerprint_igual_pass():
    r = runtime.compare_fingerprint(_obs(fingerprint="abc"), _obs(fingerprint="abc"))
    assert r.status == checks.STATUS_PASS


def test_compare_fingerprint_distinto_fail_stale():
    r = runtime.compare_fingerprint(_obs(fingerprint="abc"), _obs(fingerprint="xyz"))
    assert r.status == checks.STATUS_FAIL
    assert r.code == core.CODE_OBSERVATION_STALE


def test_compare_fingerprint_falta_en_stored_warn():
    r = runtime.compare_fingerprint(_obs(fingerprint=None), _obs(fingerprint="abc"))
    assert r.status == checks.STATUS_WARN
    assert r.code == core.CODE_FRESHNESS_UNVERIFIABLE


def test_compare_fingerprint_falta_en_fresh_warn():
    r = runtime.compare_fingerprint(_obs(fingerprint="abc"), _obs(fingerprint=None))
    assert r.status == checks.STATUS_WARN
    assert r.code == core.CODE_FRESHNESS_UNVERIFIABLE


def test_compare_fingerprint_algoritmo_distinto_warn():
    r = runtime.compare_fingerprint(
        _obs(fingerprint="abc", algorithm="sha256"), _obs(fingerprint="abc", algorithm="md5")
    )
    assert r.status == checks.STATUS_WARN
    assert r.code == core.CODE_FRESHNESS_UNVERIFIABLE


def test_compare_fingerprint_as_of_distinto_igual_fingerprint_pass_con_detalle():
    r = runtime.compare_fingerprint(
        _obs(fingerprint="abc", as_of="2026-01-01"), _obs(fingerprint="abc", as_of="2026-02-01")
    )
    assert r.status == checks.STATUS_PASS
    assert r.detail is not None and "as_of" in r.detail


def test_compare_fingerprint_source_id_distinto():
    r = runtime.compare_fingerprint(
        _obs(source_id="a", fingerprint="abc"), _obs(source_id="b", fingerprint="abc")
    )
    assert r.status == checks.STATUS_FAIL
    assert r.code == core.CODE_OBSERVATION_INVALID

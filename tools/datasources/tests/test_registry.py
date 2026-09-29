"""Tests de `tools.datasources.registry` (R12-R14)."""
from __future__ import annotations

from tools.datasources import registry
from tools.datasources.core import (
    CODE_ABSOLUTE_PATH,
    CODE_ACCESS_MODE_RESERVED,
    CODE_ID_DUPLICATE,
    CODE_ID_INVALID,
    CODE_OBSERVER_UNRESOLVED,
    CODE_REGISTRY_INVALID,
    CODE_SECRET_DETECTED,
)


def _codigos(hallazgos):
    return [h[0] for h in hallazgos]


def _fuente(**overrides) -> dict:
    base = {
        "source_id": "customers",
        "role": "raw_table",
        "observer": "proyecto.observers:factory",
        "access_mode": "read",
        "sensitivity": "internal",
    }
    base.update(overrides)
    return base


def _registro(*fuentes) -> dict:
    return {"schema_version": 1, "sources": list(fuentes)}


# ---------------------------------------------------------------------------
# validate_registry
# ---------------------------------------------------------------------------


def test_registro_vacio_valido():
    assert registry.validate_registry(_registro()) == []


def test_registro_raiz_no_dict():
    hallazgos = registry.validate_registry(["no", "es", "dict"])
    assert CODE_REGISTRY_INVALID in _codigos(hallazgos)


def test_registro_sin_sources_es_invalido():
    hallazgos = registry.validate_registry({"schema_version": 1})
    assert CODE_REGISTRY_INVALID in _codigos(hallazgos)


def test_registro_ids_duplicados():
    hallazgos = registry.validate_registry(_registro(_fuente(), _fuente()))
    assert CODE_ID_DUPLICATE in _codigos(hallazgos)


def test_registro_id_no_canonico():
    hallazgos = registry.validate_registry(_registro(_fuente(source_id="Data/Raw")))
    assert CODE_ID_INVALID in _codigos(hallazgos)


def test_registro_access_mode_write_rechazado():
    hallazgos = registry.validate_registry(_registro(_fuente(access_mode="write")))
    assert CODE_ACCESS_MODE_RESERVED in _codigos(hallazgos)


def test_registro_scan_secretos_en_options():
    hallazgos = registry.validate_registry(
        _registro(_fuente(options={"password": "no_importa_el_valor"}))
    )
    assert CODE_SECRET_DETECTED in _codigos(hallazgos)


def test_registro_scan_localizadores_en_options():
    hallazgos = registry.validate_registry(
        _registro(_fuente(options={"path": r"C:\datos\x.csv"}))
    )
    assert CODE_ABSOLUTE_PATH in _codigos(hallazgos)


def test_registro_fuente_valida_sin_hallazgos():
    hallazgos = registry.validate_registry(_registro(_fuente(options={"table": "dbo.Clientes"})))
    assert hallazgos == []


# ---------------------------------------------------------------------------
# resolve_observer_file
# ---------------------------------------------------------------------------


def test_resolve_observer_file_encuentra_modulo_py():
    existentes = {"proyecto/observers.py"}
    ruta = registry.resolve_observer_file(None, "proyecto.observers:factory", lambda r: r in existentes)
    assert ruta == "proyecto/observers.py"


def test_resolve_observer_file_encuentra_paquete_init():
    existentes = {"proyecto/observers/__init__.py"}
    ruta = registry.resolve_observer_file(None, "proyecto.observers:factory", lambda r: r in existentes)
    assert ruta == "proyecto/observers/__init__.py"


def test_resolve_observer_file_no_encuentra_devuelve_none():
    ruta = registry.resolve_observer_file(None, "proyecto.observers:factory", lambda r: False)
    assert ruta is None


def test_resolve_observer_file_rechaza_dotdot():
    llamadas = []

    def exists_fn(r):
        llamadas.append(r)
        return True

    ruta = registry.resolve_observer_file(None, "proyecto...malo:factory", exists_fn)
    assert ruta is None
    assert llamadas == []


def test_resolve_observer_file_rechaza_absoluta_unix():
    llamadas = []

    def exists_fn(r):
        llamadas.append(r)
        return True

    ruta = registry.resolve_observer_file(None, "/etc/passwd:factory", exists_fn)
    assert ruta is None
    assert llamadas == []


def test_resolve_observer_file_rechaza_absoluta_windows():
    llamadas = []

    def exists_fn(r):
        llamadas.append(r)
        return True

    ruta = registry.resolve_observer_file(None, "C:.observers:factory", exists_fn)
    assert ruta is None
    assert llamadas == []


def test_resolve_observer_file_nunca_importa_el_modulo():
    # `exists_fn` fake no ejecuta nada real; este test documenta el contrato:
    # `resolve_observer_file` solo llama a `exists_fn`, nunca a `importlib`.
    import sys

    modulo_falso = "tools_datasources_test_modulo_senuelo"
    assert modulo_falso not in sys.modules
    registry.resolve_observer_file(None, f"{modulo_falso}:factory", lambda r: True)
    assert modulo_falso not in sys.modules


# ---------------------------------------------------------------------------
# check_registry_static
# ---------------------------------------------------------------------------


def test_check_registry_static_observer_no_resuelto_es_warn():
    hallazgos = registry.check_registry_static(_registro(_fuente()), lambda r: False)
    assert CODE_OBSERVER_UNRESOLVED in _codigos(hallazgos)


def test_check_registry_static_observer_resuelto_sin_warn():
    hallazgos = registry.check_registry_static(
        _registro(_fuente()), lambda r: r == "proyecto/observers.py"
    )
    assert CODE_OBSERVER_UNRESOLVED not in _codigos(hallazgos)


def test_check_registry_static_incluye_hallazgos_de_validate_registry():
    hallazgos = registry.check_registry_static(_registro(_fuente(), _fuente()), lambda r: True)
    assert CODE_ID_DUPLICATE in _codigos(hallazgos)

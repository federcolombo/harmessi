"""Tests de `tools.datasources.conformance` (v0.13 Change 3, R7-R10).

Fixtures 100% sinteticas: un observer conformante y observers invalidos, uno
por modo (R10). Cada invalido debe fallar el chequeo esperado. Evidencia
declarada: "fixture".
"""
from __future__ import annotations

import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

from tools.datasources import conformance, core

SOURCE_ID = "fuente-sintetica"

_CAPACIDADES = {
    "facets": {"row_count": ["exact"], "null_count": ["exact"]},
    "operations": ["read"],
}


def _observacion(source_id: str, filas: int = 3) -> dict:
    return {
        "schema_version": core.SCHEMA_VERSION,
        "source_id": source_id,
        "provenance": {
            "source_id": source_id,
            "observer_id": "fixture.sintetico:factory",
            "observer_code_sha256": None,
            "access_mode": "read",
            "source_kind": "fixture",
            "generated_at": "2026-01-01T00:00:00Z",
            "tool_versions": {},
            "requested_facets": [],
            "unsupported_facets": [],
        },
        "dataset": {"row_count": {"value": filas, "exactness": "exact"}},
        "fields": [
            {
                "name": "columna_a",
                "type_family": "integer",
                "native_type": None,
                "facets": {"null_count": {"value": 0, "exactness": "exact"}},
            }
        ],
        "omitted_facets": [],
    }


class ObserverFalso:
    """Observer sintetico; `modo` elige el defecto (o "conforme")."""

    def __init__(self, source_id: str, options: dict, modo: str = "conforme") -> None:
        self.source_id = source_id
        self.options = dict(options or {})
        self.modo = modo
        self.llamadas = 0

    def capabilities(self) -> dict:
        return copy.deepcopy(_CAPACIDADES)

    def observe(self, request: dict) -> dict:
        self.llamadas += 1
        if self.modo == "id_keyerror":
            try:
                core.ObservationRequest.from_dict(request)
            except core.SourceError:
                raise KeyError("excepcion generica no acotada")
        elif self.modo != "no_valida_id":
            core.ObservationRequest.from_dict(request)  # rechaza ids/claves invalidos
        if self.options.get("fallar") and self.modo != "error_silencioso":
            if self.modo == "error_typeerror":
                raise TypeError("excepcion generica no acotada")
            raise RuntimeError("fallo sintetico del observer")
        obs = _observacion(self.source_id, filas=3)
        if self.modo == "faceta_no_declarada":
            obs["dataset"]["fingerprint"] = {"algorithm": "sha256", "value": "abc123"}
        elif self.modo == "source_id_distinto":
            obs = _observacion("otra-fuente")
        elif self.modo == "ruta_absoluta":
            obs["fields"][0]["native_type"] = "C:\\datos\\privados\\archivo.csv"
        elif self.modo == "token_falso":
            obs["fields"][0]["name"] = "AKIAABCDEFGHIJKLMNOP"
        elif self.modo == "no_determinista":
            obs = _observacion(self.source_id, filas=self.llamadas)
        return obs


class ObserverSinCapabilities:
    def __init__(self, source_id: str, options: dict) -> None:
        self.source_id = source_id

    def observe(self, request: dict) -> dict:
        return _observacion(self.source_id)


def _factory_modo(modo: str):
    def factory(source_id: str, options: dict):
        return ObserverFalso(source_id, options, modo=modo)

    return factory


def _verificar(factory, **kwargs):
    base = dict(
        source_id=SOURCE_ID,
        options={"parametro": "valor"},
        request={"source_id": SOURCE_ID},
        options_error={"fallar": True},
    )
    base.update(kwargs)
    return conformance.verificar_observer(factory, **base)


def _fallidos(reporte) -> list:
    return [c.nombre for c in reporte.chequeos if not c.ok]


class TestObserverConformante(unittest.TestCase):
    def test_conformante_pasa_todos_los_chequeos(self):
        reporte = _verificar(_factory_modo("conforme"))
        self.assertEqual(_fallidos(reporte), [])
        self.assertTrue(reporte.ok)
        self.assertEqual(reporte.evidencia, "fixture")
        self.assertEqual(len(reporte.chequeos), 9)

    def test_evidencia_real_se_propaga(self):
        reporte = _verificar(_factory_modo("conforme"), evidencia="real")
        self.assertEqual(reporte.to_dict()["evidencia"], "real")

    def test_evidencia_invalida_lanza_valueerror(self):
        with self.assertRaises(ValueError):
            _verificar(_factory_modo("conforme"), evidencia="inventada")

    def test_sin_options_error_el_reporte_no_es_ok_ni_completo(self):
        reporte = _verificar(_factory_modo("conforme"), options_error=None)
        self.assertEqual(len(reporte.chequeos), 8)
        self.assertEqual(reporte.no_evaluados, ["error_acotado"])
        self.assertEqual(_fallidos(reporte), [])
        self.assertFalse(reporte.completo)
        self.assertFalse(reporte.ok)
        self.assertFalse(reporte.to_dict()["completo"])

    def test_permitir_no_evaluados_hace_ok_pero_no_completo(self):
        reporte = _verificar(_factory_modo("conforme"), options_error=None, permitir_no_evaluados=True)
        self.assertTrue(reporte.ok)
        self.assertFalse(reporte.completo)

    def test_reporte_completo_con_options_error(self):
        reporte = _verificar(_factory_modo("conforme"))
        self.assertTrue(reporte.completo)
        self.assertTrue(reporte.to_dict()["completo"])

    def test_reporte_json_determinista(self):
        a = _verificar(_factory_modo("conforme")).to_json()
        b = _verificar(_factory_modo("conforme")).to_json()
        self.assertEqual(a, b)
        datos = json.loads(a)
        self.assertEqual(set(datos), {"source_id", "evidencia", "ok", "completo", "chequeos", "no_evaluados"})
        for chequeo in datos["chequeos"]:
            self.assertEqual(set(chequeo), {"nombre", "ok", "detalle"})

    def test_acepta_observation_request_tipado(self):
        pedido = core.ObservationRequest(source_id=SOURCE_ID)
        reporte = _verificar(_factory_modo("conforme"), request=pedido)
        self.assertTrue(reporte.ok)


class TestObserversInvalidos(unittest.TestCase):
    def _esperar(self, factory, nombre_esperado, **kwargs):
        reporte = _verificar(factory, **kwargs)
        self.assertIn(nombre_esperado, _fallidos(reporte))
        self.assertFalse(reporte.ok)
        return reporte

    def test_faceta_no_declarada(self):
        self._esperar(_factory_modo("faceta_no_declarada"), "facetas_no_fabricadas")

    def test_source_id_distinto(self):
        self._esperar(_factory_modo("source_id_distinto"), "observacion_valida")

    def test_ruta_absoluta(self):
        reporte = self._esperar(_factory_modo("ruta_absoluta"), "sin_fuga_secretos_rutas")
        # El detalle no reproduce el valor sospechoso.
        detalle = [c.detalle for c in reporte.chequeos if c.nombre == "sin_fuga_secretos_rutas"][0]
        self.assertNotIn("privados", detalle)

    def test_token_falso(self):
        reporte = self._esperar(_factory_modo("token_falso"), "sin_fuga_secretos_rutas")
        detalle = [c.detalle for c in reporte.chequeos if c.nombre == "sin_fuga_secretos_rutas"][0]
        self.assertNotIn("AKIAABCDEFGHIJKLMNOP", detalle)

    def test_no_determinista(self):
        self._esperar(_factory_modo("no_determinista"), "reproducibilidad")

    def test_sin_capabilities(self):
        reporte = self._esperar(ObserverSinCapabilities, "forma_factory")
        self.assertIn("capacidades_validas", _fallidos(reporte))

    def test_id_invalido_no_rechazado(self):
        self._esperar(_factory_modo("no_valida_id"), "source_id_invalido_rechazado")

    def test_error_silencioso_es_observacion_parcial(self):
        self._esperar(_factory_modo("error_silencioso"), "error_acotado")

    def test_id_invalido_rechazado_con_excepcion_generica_falla_y_nombra_el_tipo(self):
        reporte = self._esperar(_factory_modo("id_keyerror"), "source_id_invalido_rechazado")
        detalle = [c.detalle for c in reporte.chequeos if c.nombre == "source_id_invalido_rechazado"][0]
        self.assertIn("KeyError", detalle)

    def test_error_con_excepcion_generica_falla_y_nombra_el_tipo(self):
        reporte = self._esperar(_factory_modo("error_typeerror"), "error_acotado")
        detalle = [c.detalle for c in reporte.chequeos if c.nombre == "error_acotado"][0]
        self.assertIn("TypeError", detalle)

    def test_excepciones_acotadas_documentadas_se_aceptan(self):
        for excepcion in (RuntimeError, ValueError, FileNotFoundError, OSError, core.SourceError):
            class ObserverError(ObserverFalso):
                def observe(self, request, _exc=excepcion):
                    if self.options.get("fallar"):
                        raise (_exc("c", "m") if _exc is core.SourceError else _exc("m"))
                    return super().observe(request)

            with self.subTest(excepcion=excepcion.__name__):
                reporte = _verificar(lambda s, o: ObserverError(s, o))
                self.assertNotIn("error_acotado", _fallidos(reporte))

    def test_systemexit_del_observer_es_chequeo_fallido(self):
        class Sale(ObserverFalso):
            def capabilities(self):
                raise SystemExit(2)

        reporte = _verificar(lambda s, o: Sale(s, o))
        self.assertIn("capacidades_validas", _fallidos(reporte))

    def test_excepcion_del_observer_es_un_chequeo_fallido_no_traceback(self):
        class Roto:
            def __init__(self, source_id, options):
                pass

            def capabilities(self):
                raise RuntimeError("fallo sintetico")

            def observe(self, request):
                raise RuntimeError("fallo sintetico")

        reporte = _verificar(Roto)
        self.assertFalse(reporte.ok)
        detalles = " ".join(c.detalle for c in reporte.chequeos)
        self.assertIn("RuntimeError", detalles)
        self.assertNotIn("fallo sintetico", detalles)

    def test_request_invalido_se_reporta_sin_traceback(self):
        reporte = _verificar(_factory_modo("conforme"), request={"source_id": SOURCE_ID, "query": "x"})
        self.assertFalse(reporte.ok)
        self.assertIn("forma_factory", _fallidos(reporte))


_PLANTILLA_MODULO = '''\
{import_inicial}
import json


_PLANTILLA = {plantilla}


class _Observer:
    def __init__(self, source_id):
        self.source_id = source_id

    def capabilities(self):
        return {{"facets": {{"row_count": ["exact"], "null_count": ["exact"]}}, "operations": ["read"]}}

    def observe(self, request):
        from tools.datasources import core
        core.ObservationRequest.from_dict(request)
        return json.loads(json.dumps(_PLANTILLA).replace("__SID__", self.source_id))


def factory(source_id, options):
    {cuerpo_factory}
    return _Observer(source_id)
'''


def _cargar_modulo_generado(directorio: Path, nombre: str, import_inicial: str, cuerpo_factory: str = "pass"):
    codigo = _PLANTILLA_MODULO.format(
        import_inicial=import_inicial,
        plantilla=repr(_observacion("__SID__")),
        cuerpo_factory=cuerpo_factory,
    )
    ruta = directorio / f"{nombre}.py"
    ruta.write_text(codigo, encoding="utf-8")
    especificacion = importlib.util.spec_from_file_location(nombre, ruta)
    modulo = importlib.util.module_from_spec(especificacion)
    sys.modules[nombre] = modulo
    try:
        especificacion.loader.exec_module(modulo)
    except Exception:
        sys.modules.pop(nombre, None)
        raise
    return modulo


class TestChequeoSinInstalacionAst(unittest.TestCase):
    def _correr(self, nombre: str, import_inicial: str, cuerpo_factory: str = "pass"):
        with tempfile.TemporaryDirectory() as tmp:
            modulo = _cargar_modulo_generado(Path(tmp), nombre, import_inicial, cuerpo_factory)
            try:
                return _verificar(modulo.factory, options_error=None)
            finally:
                sys.modules.pop(nombre, None)

    def test_modulo_limpio_pasa(self):
        reporte = self._correr("observer_generado_limpio", "import os")
        self.assertEqual(_fallidos(reporte), [])

    def test_instalacion_via_subprocess_a_nivel_de_modulo_falla(self):
        reporte = self._correr("observer_generado_subprocess", "import subprocess")
        self.assertEqual(_fallidos(reporte), ["sin_instalacion_automatica"])

    def test_instalador_a_nivel_de_modulo_falla(self):
        reporte = self._correr("observer_generado_ensurepip", "import ensurepip")
        self.assertEqual(_fallidos(reporte), ["sin_instalacion_automatica"])

    def test_import_dentro_de_funcion_tambien_se_marca(self):
        reporte = self._correr("observer_generado_en_funcion", "import os", "if False:\n        import subprocess")
        self.assertEqual(_fallidos(reporte), ["sin_instalacion_automatica"])

    def test_import_dentro_de_try_se_marca(self):
        reporte = self._correr(
            "observer_generado_en_try", "try:\n    import subprocess\nexcept ImportError:\n    subprocess = None"
        )
        self.assertEqual(_fallidos(reporte), ["sin_instalacion_automatica"])

    def test_import_bajo_type_checking_no_se_marca(self):
        reporte = self._correr(
            "observer_generado_type_checking",
            "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    import subprocess",
        )
        self.assertEqual(_fallidos(reporte), [])

    def test_import_dinamico_de_modulo_prohibido_se_marca(self):
        reporte = self._correr(
            "observer_generado_dunder_import", "import os", 'if False:\n        __import__("subprocess")'
        )
        self.assertEqual(_fallidos(reporte), ["sin_instalacion_automatica"])
        reporte = self._correr(
            "observer_generado_import_module",
            "import importlib",
            'if False:\n        importlib.import_module("pip._internal")',
        )
        self.assertEqual(_fallidos(reporte), ["sin_instalacion_automatica"])

    def test_os_system_popen_spawn_se_marcan(self):
        for i, llamada in enumerate(('os.system("x")', 'os.popen("x")', 'os.spawnl(0, "x")')):
            with self.subTest(llamada=llamada):
                reporte = self._correr(f"observer_generado_os_{i}", "import os", f"if False:\n        {llamada}")
                self.assertEqual(_fallidos(reporte), ["sin_instalacion_automatica"])

    def test_lista_ampliada_de_prohibidos(self):
        for nombre in ("uv", "poetry", "setuptools", "runpy", "ctypes", "subprocess", "pip"):
            self.assertIn(nombre, conformance.IMPORTS_PROHIBIDOS)


if __name__ == "__main__":
    unittest.main()

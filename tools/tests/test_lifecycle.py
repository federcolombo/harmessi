"""Tests de `tools.dsguard.lifecycle` (Change 1, v0.3): schema y librería base
de `openspec/lifecycle/state.json` -- catálogos CRISP-DM/KDD/MLOps, mapeo
CRISP-DM<->KDD, init idempotente, lectura/validación/escritura atómica.

No hay transición ni gating en este módulo (eso queda para Changes
posteriores del roadmap v0.3) -- estos tests solo cubren catálogo, init,
lectura, validación y escritura. Usa siempre directorios temporales propios
(`_crear_dir_temporal`, patrón de `test_kdd.py`), nunca este repositorio real
como fixture: `lifecycle.py` no conoce Git, igual que `kdd.py`.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ORIGEN = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ORIGEN / "tools"))

from dsguard import core, lifecycle  # noqa: E402


def _crear_dir_temporal(prefix: str = "lifecycle_test_") -> Path:
    return Path(tempfile.mkdtemp(prefix=prefix))


class TestLifecycleInit(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_dir_temporal()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_init_crea_state_json_inicial(self):
        estado, creado = lifecycle.lifecycle_init(self.repo)
        self.assertTrue(creado)
        self.assertTrue(lifecycle.state_path(self.repo).exists())
        self.assertEqual(estado["schema_version"], lifecycle.SCHEMA_VERSION_SOPORTADA)
        self.assertIsNone(estado["migrado_desde"])

    def test_init_es_idempotente(self):
        estado1, creado1 = lifecycle.lifecycle_init(self.repo)
        bytes1 = lifecycle.state_path(self.repo).read_bytes()
        estado2, creado2 = lifecycle.lifecycle_init(self.repo)
        bytes2 = lifecycle.state_path(self.repo).read_bytes()

        self.assertTrue(creado1)
        self.assertFalse(creado2)
        self.assertEqual(bytes1, bytes2)
        self.assertEqual(estado1, estado2)

    def test_init_no_pisa_archivo_corrupto(self):
        ruta = lifecycle.state_path(self.repo)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text("esto no es json valido", encoding="utf-8")
        antes = ruta.read_bytes()

        with self.assertRaises(lifecycle.LifecycleEstadoError):
            lifecycle.lifecycle_init(self.repo)

        self.assertEqual(ruta.read_bytes(), antes)


class TestLifecycleCatalogos(unittest.TestCase):
    def test_schema_version_correcta(self):
        estado = lifecycle.estado_inicial()
        self.assertEqual(estado["schema_version"], 1)

    def test_estructura_crispdm_8_fases_forma_exacta(self):
        estado = lifecycle.estado_inicial()
        fases = estado["crispdm"]["fases"]
        self.assertEqual(set(fases.keys()), set(lifecycle.FASES_CRISPDM))
        self.assertEqual(len(fases), 8)
        for fase, entrada in fases.items():
            self.assertEqual(entrada["estado"], "no_iniciada")
            self.assertEqual(entrada["changes"], [])
            self.assertEqual(entrada["evidencia"], [])
            self.assertIsInstance(entrada["actualizado_utc"], str)
            self.assertTrue(entrada["actualizado_utc"])

    def test_estructura_kdd_5_pasos_forma_exacta(self):
        estado = lifecycle.estado_inicial()
        pasos = estado["kdd"]["pasos"]
        self.assertEqual(set(pasos.keys()), set(lifecycle.PASOS_KDD))
        self.assertEqual(len(pasos), 5)
        for paso, entrada in pasos.items():
            self.assertEqual(entrada["estado"], "no_iniciada")
            self.assertEqual(entrada["changes"], [])
            self.assertEqual(entrada["evidencia"], [])
            self.assertIsInstance(entrada["actualizado_utc"], str)

    def test_estructura_mlops_3_tiers_16_capacidades_forma_exacta(self):
        estado = lifecycle.estado_inicial()
        mlops = estado["mlops"]
        self.assertEqual(set(mlops.keys()), set(lifecycle.MLOPS_TIERS))
        total_capacidades = 0
        for tier in lifecycle.MLOPS_TIERS:
            capacidades = mlops[tier]
            self.assertEqual(set(capacidades.keys()), set(lifecycle.MLOPS_CAPACIDADES[tier]))
            total_capacidades += len(capacidades)
            for cap, entrada in capacidades.items():
                self.assertEqual(entrada["estado"], "no_iniciada")
                self.assertEqual(entrada["changes"], [])
                self.assertEqual(entrada["evidencia"], [])
                self.assertIsInstance(entrada["actualizado_utc"], str)
        self.assertEqual(total_capacidades, 16)

    def test_mapeo_crispdm_a_kdd_exacto(self):
        esperado = {
            "business_understanding": (),
            "data_understanding": ("selection",),
            "data_preparation": ("preprocessing", "transformation"),
            "modeling": ("data_mining",),
            "evaluation": ("interpretation_evaluation",),
            "production_readiness": (),
            "deployment": (),
            "monitoring": (),
        }
        self.assertEqual(lifecycle.MAPEO_CRISPDM_A_KDD, esperado)

    def test_mapeo_kdd_a_crispdm_es_inversa_derivada(self):
        inversa_a_mano = {}
        for fase, pasos in lifecycle.MAPEO_CRISPDM_A_KDD.items():
            for paso in pasos:
                inversa_a_mano[paso] = fase
        self.assertEqual(lifecycle.MAPEO_KDD_A_CRISPDM, inversa_a_mano)
        self.assertEqual(set(lifecycle.MAPEO_KDD_A_CRISPDM.keys()), set(lifecycle.PASOS_KDD))

    def test_estado_inicial_no_incluye_fase_actual_ni_paso_actual(self):
        estado = lifecycle.estado_inicial()
        self.assertNotIn("fase_actual", estado["crispdm"])
        self.assertNotIn("paso_actual", estado["kdd"])


class TestLifecycleLectura(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_dir_temporal()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_lectura_valida_sobre_archivo_bien_formado(self):
        lifecycle.lifecycle_init(self.repo)
        estado = lifecycle.leer_estado(lifecycle.state_path(self.repo))
        self.assertEqual(estado["schema_version"], lifecycle.SCHEMA_VERSION_SOPORTADA)
        self.assertEqual(set(estado["crispdm"]["fases"].keys()), set(lifecycle.FASES_CRISPDM))

    def test_archivo_ausente_levanta_filenotfound(self):
        with self.assertRaises(FileNotFoundError):
            lifecycle.leer_estado(lifecycle.state_path(self.repo))

    def test_json_invalido_levanta_lifecycleestadoerror_sin_escribir(self):
        ruta = lifecycle.state_path(self.repo)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text("{invalido", encoding="utf-8")
        antes = ruta.read_bytes()

        with self.assertRaises(lifecycle.LifecycleEstadoError):
            lifecycle.leer_estado(ruta)

        self.assertEqual(ruta.read_bytes(), antes)

    def test_schema_version_desconocida_levanta_con_mensaje_explicito(self):
        ruta = lifecycle.state_path(self.repo)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        datos = lifecycle.estado_inicial()
        datos["schema_version"] = 999
        ruta.write_text(json.dumps(datos), encoding="utf-8")

        with self.assertRaises(lifecycle.LifecycleEstadoError) as ctx:
            lifecycle.leer_estado(ruta)
        mensaje = str(ctx.exception)
        self.assertIn("999", mensaje)
        self.assertIn(str(lifecycle.SCHEMA_VERSION_SOPORTADA), mensaje)

    def test_lectura_no_muta_archivo_en_disco(self):
        lifecycle.lifecycle_init(self.repo)
        ruta = lifecycle.state_path(self.repo)
        bytes_antes = ruta.read_bytes()
        lifecycle.leer_estado(ruta)
        lifecycle.leer_estado(ruta)
        bytes_despues = ruta.read_bytes()
        self.assertEqual(bytes_antes, bytes_despues)


class TestLifecycleValidarEstructura(unittest.TestCase):
    def test_rechaza_fase_crispdm_faltante(self):
        datos = lifecycle.estado_inicial()
        del datos["crispdm"]["fases"]["modeling"]
        with self.assertRaises(lifecycle.LifecycleEstadoError):
            lifecycle.validar_estructura(datos)

    def test_rechaza_clave_extra_no_reconocida_en_fases(self):
        datos = lifecycle.estado_inicial()
        datos["crispdm"]["fases"]["fase_inventada"] = lifecycle._entrada_inicial(core.ahora_utc())
        with self.assertRaises(lifecycle.LifecycleEstadoError):
            lifecycle.validar_estructura(datos)

    def test_rechaza_paso_kdd_faltante(self):
        datos = lifecycle.estado_inicial()
        del datos["kdd"]["pasos"]["data_mining"]
        with self.assertRaises(lifecycle.LifecycleEstadoError):
            lifecycle.validar_estructura(datos)

    def test_rechaza_capacidad_mlops_faltante(self):
        datos = lifecycle.estado_inicial()
        del datos["mlops"]["foundations"]["lineage"]
        with self.assertRaises(lifecycle.LifecycleEstadoError):
            lifecycle.validar_estructura(datos)

    def test_rechaza_estado_fuera_de_estados_validos(self):
        datos = lifecycle.estado_inicial()
        datos["crispdm"]["fases"]["modeling"]["estado"] = "futura"
        with self.assertRaises(lifecycle.LifecycleEstadoError):
            lifecycle.validar_estructura(datos)

    def test_estados_validos_no_incluye_futura(self):
        self.assertNotIn("futura", lifecycle.ESTADOS_VALIDOS)
        self.assertEqual(lifecycle.ESTADOS_VALIDOS, frozenset({"no_iniciada", "en_progreso", "cerrada"}))


class TestLifecycleEscritura(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_dir_temporal()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_escritura_atomica_no_deja_temporal_residual(self):
        estado = lifecycle.estado_inicial()
        lifecycle.escribir_estado(self.repo, estado)
        ruta = lifecycle.state_path(self.repo)
        self.assertTrue(ruta.exists())
        tmp = ruta.parent / (ruta.name + ".tmp")
        self.assertFalse(tmp.exists())
        contenido_esperado = json.dumps(estado, indent=2, ensure_ascii=False) + "\n"
        self.assertEqual(ruta.read_text(encoding="utf-8"), contenido_esperado)

    def test_round_trip_escribir_leer_estructuras_iguales(self):
        estado = lifecycle.estado_inicial()
        lifecycle.escribir_estado(self.repo, estado)
        releido = lifecycle.leer_estado(lifecycle.state_path(self.repo))
        self.assertEqual(estado, releido)


class TestLifecycleStatePath(unittest.TestCase):
    def test_state_path_devuelve_ruta_correcta(self):
        repo = Path("/algun/repo")
        esperado = repo / "openspec" / "lifecycle" / "state.json"
        self.assertEqual(lifecycle.state_path(repo), esperado)


if __name__ == "__main__":
    unittest.main()

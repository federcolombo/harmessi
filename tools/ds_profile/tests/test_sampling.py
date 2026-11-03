"""Tests de `tools.ds_profile.sampling`."""
from __future__ import annotations

import unittest

from tools.ds_profile import sampling
from tools.ds_profile.sampling import ReservoirSampler, decidir_modo


class TestDecidirModo(unittest.TestCase):
    def test_bajo_ambos_umbrales_es_exacto(self):
        self.assertFalse(decidir_modo(tamano_bytes=1000, filas_exactas=100, max_mb_exactos=500, max_filas_exactas=2_000_000))

    def test_supera_mb_es_muestreado(self):
        tamano = 501 * 1024 * 1024
        self.assertTrue(decidir_modo(tamano_bytes=tamano, filas_exactas=None, max_mb_exactos=500, max_filas_exactas=2_000_000))

    def test_exactamente_en_el_umbral_de_mb_no_dispara(self):
        tamano = 500 * 1024 * 1024
        self.assertFalse(decidir_modo(tamano_bytes=tamano, filas_exactas=None, max_mb_exactos=500, max_filas_exactas=2_000_000))

    def test_supera_filas_es_muestreado(self):
        self.assertTrue(decidir_modo(tamano_bytes=100, filas_exactas=2_000_001, max_mb_exactos=500, max_filas_exactas=2_000_000))

    def test_filas_none_no_dispara_el_chequeo_de_filas(self):
        # CSV: filas_exactas siempre None -- el umbral de filas no puede
        # evaluarse de antemano, solo el de MB sigue aplicando.
        self.assertFalse(decidir_modo(tamano_bytes=100, filas_exactas=None, max_mb_exactos=500, max_filas_exactas=1))

    def test_supera_filas_pero_bytes_bajo_igual_dispara(self):
        self.assertTrue(decidir_modo(tamano_bytes=1, filas_exactas=10, max_mb_exactos=500, max_filas_exactas=5))


class TestReservoirSampler(unittest.TestCase):
    def test_muestra_no_supera_el_tamano_configurado(self):
        sampler = ReservoirSampler(tamano_muestra=10, seed=42)
        for i in range(1000):
            sampler.observar({"i": i})
        self.assertEqual(len(sampler.muestra()), 10)

    def test_dataset_mas_chico_que_la_muestra_retiene_todo(self):
        sampler = ReservoirSampler(tamano_muestra=100, seed=42)
        for i in range(5):
            sampler.observar({"i": i})
        self.assertEqual(len(sampler.muestra()), 5)

    def test_misma_semilla_y_misma_secuencia_produce_la_misma_muestra(self):
        filas = [{"i": i} for i in range(500)]

        sampler_a = ReservoirSampler(tamano_muestra=20, seed=7)
        for fila in filas:
            sampler_a.observar(fila)

        sampler_b = ReservoirSampler(tamano_muestra=20, seed=7)
        for fila in filas:
            sampler_b.observar(fila)

        self.assertEqual(sampler_a.muestra(), sampler_b.muestra())

    def test_semillas_distintas_pueden_producir_muestras_distintas(self):
        filas = [{"i": i} for i in range(500)]

        sampler_a = ReservoirSampler(tamano_muestra=20, seed=1)
        for fila in filas:
            sampler_a.observar(fila)

        sampler_b = ReservoirSampler(tamano_muestra=20, seed=2)
        for fila in filas:
            sampler_b.observar(fila)

        self.assertNotEqual(sampler_a.muestra(), sampler_b.muestra())

    def test_tamano_muestra_cero_no_retiene_nada(self):
        sampler = ReservoirSampler(tamano_muestra=0, seed=42)
        for i in range(10):
            sampler.observar({"i": i})
        self.assertEqual(sampler.muestra(), [])

    def test_muestra_devuelve_copia_no_referencia_interna(self):
        sampler = ReservoirSampler(tamano_muestra=5, seed=42)
        for i in range(5):
            sampler.observar({"i": i})
        copia = sampler.muestra()
        copia.append({"i": "intruso"})
        self.assertEqual(len(sampler.muestra()), 5)


class TestEstimacionPorDtype(unittest.TestCase):
    """B-12: estimación de bytes por dtype (`dtype_v1`), conservadora."""

    def test_mapeo_por_prefijo_de_tipo(self):
        casos = {
            "int64": 96, "uint8": 96, "float": 96, "double": 96, "bool": 96,
            "date32[day]": 96, "timestamp[ns]": 96,
            "string": 128, "large_string": 128, "binary": 128,
            "decimal128(10, 2)": 160, "list<item: int64>": 160,
            "struct<a: int64>": 160, "dictionary<values=string, indices=int32>": 160,
            "interval": 160, "tipo_raro": 160,
            "str": sampling.BYTES_POR_CELDA,
        }
        for tipo, esperado in casos.items():
            with self.subTest(tipo=tipo):
                self.assertEqual(sampling.bytes_por_celda_dtype(tipo), esperado)

    def test_sin_schema_es_identico_al_global(self):
        self.assertEqual(sampling.estimar_bytes_exactos(10, 3), 10 * 3 * sampling.BYTES_POR_CELDA)
        self.assertEqual(sampling.estimar_bytes_exactos(10, 0), 10 * sampling.BYTES_POR_CELDA)
        self.assertIsNone(sampling.estimar_bytes_exactos(None, 3, {"a": "int64"}))
        plan = sampling.decidir_plan(10, 100, 3, 500, 2_000_000)
        self.assertEqual(plan["estimacion"], "global_v1")

    def test_con_schema_suma_bytes_por_dtype(self):
        schema = {"a": "int64", "b": "string", "c": "decimal128(10, 2)"}
        por_fila = (
            sampling.bytes_por_celda_dtype("int64")
            + sampling.bytes_por_celda_dtype("string")
            + sampling.bytes_por_celda_dtype("decimal128(10, 2)")
        )
        self.assertEqual(sampling.estimar_bytes_exactos(10, 3, schema), 10 * por_fila)
        plan = sampling.decidir_plan(10, 100, 3, 500, 2_000_000, schema=schema)
        self.assertEqual(plan["estimacion"], "dtype_v1")
        self.assertEqual(plan["estimado_bytes"], 100 * por_fila)

    def test_estimacion_dtype_nunca_baja_del_criterio_global(self):
        for tipo in ("int64", "double", "bool", "date32[day]", "string", "decimal128(10, 2)", "list<item: int64>"):
            with self.subTest(tipo=tipo):
                self.assertGreaterEqual(sampling.bytes_por_celda_dtype(tipo), sampling.BYTES_POR_CELDA)

    def test_schema_csv_str_equivale_al_global(self):
        schema = {"a": "str", "b": "str"}
        self.assertEqual(sampling.estimar_bytes_exactos(10, 2, schema), sampling.estimar_bytes_exactos(10, 2))
        self.assertEqual(sampling.decidir_plan(10, 100, 2, 500, 2_000_000, schema=schema)["estimacion"], "global_v1")

    def test_tamano_muestra_usa_bytes_por_fila_del_schema(self):
        schema = {"a": "string", "b": "string"}
        plan = sampling.decidir_plan(10, 10_000_000, 2, 1, 50_000_000, schema=schema)
        por_fila = 2 * sampling.bytes_por_celda_dtype("string")
        self.assertEqual(plan["tamano_muestra"], (1024 * 1024) // por_fila)


if __name__ == "__main__":
    unittest.main()

"""Tests de `tools.ds_profile.sampling`."""
from __future__ import annotations

import unittest

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


if __name__ == "__main__":
    unittest.main()

"""Tests de `tools.ds_profile.fingerprint`."""
from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from tools.ds_profile.fingerprint import ALGORITMO, calcular_fingerprint


class TestCalcularFingerprint(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)

    def test_algoritmo_declarado(self):
        ruta = self.dir / "a.csv"
        ruta.write_bytes(b"a,b\n1,2\n")
        resultado = calcular_fingerprint(ruta)
        self.assertEqual(resultado["algoritmo"], ALGORITMO)

    def test_hash_coincide_con_sha256_directo(self):
        ruta = self.dir / "a.csv"
        contenido = b"a,b\n1,2\n3,4\n"
        ruta.write_bytes(contenido)
        resultado = calcular_fingerprint(ruta)
        self.assertEqual(resultado["hash"], hashlib.sha256(contenido).hexdigest())

    def test_estable_entre_corridas_independientes(self):
        ruta = self.dir / "a.csv"
        ruta.write_bytes(b"contenido identico\n" * 100)
        primero = calcular_fingerprint(ruta)
        segundo = calcular_fingerprint(ruta)
        self.assertEqual(primero, segundo)

    def test_contenido_distinto_produce_hash_distinto(self):
        ruta_a = self.dir / "a.csv"
        ruta_b = self.dir / "b.csv"
        ruta_a.write_bytes(b"contenido a\n")
        ruta_b.write_bytes(b"contenido b\n")
        self.assertNotEqual(calcular_fingerprint(ruta_a)["hash"], calcular_fingerprint(ruta_b)["hash"])

    def test_chunk_size_pequeno_no_cambia_el_resultado(self):
        ruta = self.dir / "a.csv"
        contenido = b"x" * 10_000
        ruta.write_bytes(contenido)
        resultado_chunk_grande = calcular_fingerprint(ruta, chunk_size=1 << 20)
        resultado_chunk_chico = calcular_fingerprint(ruta, chunk_size=17)
        self.assertEqual(resultado_chunk_grande, resultado_chunk_chico)
        self.assertEqual(resultado_chunk_chico["hash"], hashlib.sha256(contenido).hexdigest())


if __name__ == "__main__":
    unittest.main()

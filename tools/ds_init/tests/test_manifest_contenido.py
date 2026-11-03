"""Paridad del campo `contenido` del manifiesto (R5-R7 del Change
`20261008-cross-platform-managed-hashing`): ninguna entrada con extension
tipicamente binaria puede quedar declarada como `texto`."""
from __future__ import annotations

import unittest
from pathlib import PurePosixPath

from tools.ds_init import manifest as manifest_mod

EXTENSIONES_BINARIAS = (
    ".png", ".ico", ".zip", ".whl", ".pdf", ".parquet", ".pyc", ".gif", ".jpg",
    ".jpeg", ".xlsx", ".bin", ".exe", ".dll", ".so", ".woff", ".woff2", ".ttf",
)


class TestParidadContenidoManifest(unittest.TestCase):
    def test_extensiones_binarias_declaran_contenido_binario(self):
        incorrectas = [
            entrada.destino
            for entrada in manifest_mod.MANIFEST
            if PurePosixPath(entrada.destino).suffix.lower() in EXTENSIONES_BINARIAS
            and entrada.contenido != "binario"
        ]
        self.assertEqual(incorrectas, [])

    def test_todo_contenido_declarado_es_valido(self):
        for entrada in manifest_mod.MANIFEST:
            self.assertIn(entrada.contenido, manifest_mod.CONTENIDOS_VALIDOS, entrada.destino)


if __name__ == "__main__":
    unittest.main()

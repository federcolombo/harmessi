"""R5 (Change 5 v0.11): escritura atómica de `control.json` y backup previo en
`migrar_hashes --execute`."""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.ds_init import control

RUTA_ARCHIVO = "tools/dsguard/core.py"  # ruta presente en el MANIFEST (texto)
CONTENIDO = b"x = 1\n"


def _preparar(destino: Path) -> Path:
    archivo = destino / RUTA_ARCHIVO
    archivo.parent.mkdir(parents=True, exist_ok=True)
    archivo.write_bytes(CONTENIDO)
    return destino / control.DIR_CONTROL / control.NOMBRE_ARCHIVO_CONTROL


def _escribir_control_legacy(ruta_control: Path) -> bytes:
    """Control legacy: entrada sin `hash_alg`, sha256 crudo."""
    ruta_control.parent.mkdir(parents=True, exist_ok=True)
    datos = {
        "harness_version": "0.0.0",
        "perfil": "python-jupyter-data",
        "archivos": [
            {"ruta": RUTA_ARCHIVO, "sha256": hashlib.sha256(CONTENIDO).hexdigest()}
        ],
    }
    contenido = (json.dumps(datos, indent=2) + "\n").encode("utf-8")
    ruta_control.write_bytes(contenido)
    return contenido


def _config() -> dict:
    return {"nombre": "demo", "notebooks_dir": "notebooks", "venv_dir": ".venv"}


class TestControlAtomico(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.destino = Path(self._tmp.name)
        self.ruta_control = _preparar(self.destino)

    def _temporales(self):
        return [
            p for p in self.ruta_control.parent.iterdir()
            if p.name != control.NOMBRE_ARCHIVO_CONTROL and ".bak-" not in p.name
        ]

    def test_escritura_ok_produce_archivo_sin_temporales(self):
        resultado = control.generar_control(
            self.destino, "python-jupyter-data", _config(), [RUTA_ARCHIVO]
        )
        self.assertTrue(self.ruta_control.is_file())
        self.assertEqual(json.loads(self.ruta_control.read_text("utf-8")), resultado)
        self.assertEqual(self._temporales(), [])

    def test_fallo_en_replace_deja_original_intacto_y_sin_temporal(self):
        original = _escribir_control_legacy(self.ruta_control)
        with mock.patch("tools.ds_init.control.os.replace", side_effect=OSError("boom")):
            with self.assertRaises(OSError):
                control.generar_control(
                    self.destino, "python-jupyter-data", _config(), [RUTA_ARCHIVO]
                )
        self.assertEqual(self.ruta_control.read_bytes(), original)
        self.assertEqual(self._temporales(), [])

    def test_migrar_hashes_execute_crea_backup_con_contenido_previo(self):
        original = _escribir_control_legacy(self.ruta_control)
        informe = control.migrar_hashes(self.destino, ejecutar=True)
        self.assertEqual(informe.migradas, [RUTA_ARCHIVO])
        backups = list(self.ruta_control.parent.glob("control.json.bak-*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), original)
        nuevo = json.loads(self.ruta_control.read_text("utf-8"))
        self.assertIn("hash_alg", nuevo["archivos"][0])
        self.assertEqual(self._temporales(), [])

    def test_migrar_hashes_dry_run_no_crea_backup(self):
        original = _escribir_control_legacy(self.ruta_control)
        control.migrar_hashes(self.destino, ejecutar=False)
        self.assertEqual(list(self.ruta_control.parent.glob("control.json.bak-*")), [])
        self.assertEqual(self.ruta_control.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()

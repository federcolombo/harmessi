"""Tests del lock de instalación (`tools/ds_init/lock.py`)."""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from tools.ds_init import lock


class TestLock(unittest.TestCase):
    def setUp(self):
        self.destino = Path(tempfile.mkdtemp(prefix="ds_init_test_lock_"))

    def tearDown(self):
        shutil.rmtree(self.destino, ignore_errors=True)

    def test_adquirir_crea_lock_con_pid_utc_accion(self):
        ruta = lock.adquirir_lock(self.destino, "install")
        self.assertEqual(ruta, self.destino / ".ds_init" / "lock")
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        self.assertEqual(datos["pid"], os.getpid())
        self.assertEqual(datos["accion"], "install")
        self.assertIn("utc", datos)

    def test_ocupado_levanta_error_accionable_y_no_pisa_el_lock(self):
        ruta = lock.adquirir_lock(self.destino, "sync")
        original = ruta.read_text(encoding="utf-8")
        with self.assertRaises(lock.LockOcupadoError) as cm:
            lock.adquirir_lock(self.destino, "install")
        mensaje = str(cm.exception)
        self.assertIn(str(os.getpid()), mensaje)
        self.assertIn("sync", mensaje)
        self.assertIn("borrar el archivo", mensaje)
        self.assertIn(str(ruta), mensaje)
        self.assertEqual(ruta.read_text(encoding="utf-8"), original)

    def test_liberar_es_idempotente(self):
        lock.adquirir_lock(self.destino)
        lock.liberar_lock(self.destino)
        lock.liberar_lock(self.destino)
        self.assertFalse((self.destino / ".ds_init" / "lock").exists())

    def test_context_manager_libera_al_salir(self):
        with lock.lock_instalacion(self.destino, "install"):
            self.assertTrue((self.destino / ".ds_init" / "lock").exists())
        self.assertFalse((self.destino / ".ds_init" / "lock").exists())

    def test_context_manager_libera_ante_excepcion(self):
        with self.assertRaises(RuntimeError):
            with lock.lock_instalacion(self.destino, "install"):
                raise RuntimeError("boom")
        self.assertFalse((self.destino / ".ds_init" / "lock").exists())

    def test_context_manager_no_libera_lock_ajeno_si_no_pudo_adquirir(self):
        lock.adquirir_lock(self.destino, "sync")
        with self.assertRaises(lock.LockOcupadoError):
            with lock.lock_instalacion(self.destino, "install"):
                pass
        # El lock ajeno sigue ahí (nunca se roba ni se borra al fallar).
        self.assertTrue((self.destino / ".ds_init" / "lock").exists())


if __name__ == "__main__":
    unittest.main()

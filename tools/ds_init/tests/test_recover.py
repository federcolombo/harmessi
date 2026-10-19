"""Tests de `ds_init recover` (v0.11 Change 5, R4). Las interrupciones se
simulan sobre el flujo real de `upgrade --execute`: se fuerza una excepción en
la fase deseada y se anula el rollback automático del writer (como si el
proceso hubiera muerto), dejando journal y estado a medias en disco."""
from __future__ import annotations

import json
import shutil
import os
import unittest
from pathlib import Path
from unittest import mock

from tools.ds_init import writer
from tools.ds_init.tests.test_upgrade import (
    RUTA_NUEVA,
    _BaseUpgrade,
    _commit_todo,
    _correr,
    _hashes_arbol,
)

_FALLO_ROLLBACK = [{"destino": "simulado", "error": "proceso muerto"}]


def _sin_journal(hashes: dict) -> dict:
    return {k: v for k, v in hashes.items() if not k.startswith(".ds_init/journal/")}


class TestRecover(_BaseUpgrade):
    def interrumpir_upgrade(self, fase: str) -> None:
        """Corre `upgrade --execute` interrumpido en `fase` sin rollback."""
        cuenta = {"n": 0}
        real_replace = os.replace

        def _replace_falla_en_2(origen, destino):
            cuenta["n"] += 1
            if cuenta["n"] == 2:
                raise OSError("corte simulado a mitad de la aplicación")
            return real_replace(origen, destino)

        parches = [mock.patch.object(writer, "_revertir_journal", return_value=_FALLO_ROLLBACK)]
        if fase == "preparado":
            # Corte antes de que la transacción persista la fase `aplicando`.
            parches.append(mock.patch.object(writer, "_preparar_backups", side_effect=OSError("corte")))
        elif fase == "aplicando":
            parches.append(mock.patch("os.replace", _replace_falla_en_2))
        elif fase == "control_pendiente":
            parches.append(mock.patch("tools.ds_init.control.generar_control", side_effect=OSError("corte")))
        else:
            raise ValueError(fase)
        with contextlib_exit_stack(parches):
            codigo, _out, _err = self.correr_upgrade("--execute")
        self.assertEqual(codigo, 1)
        journals = list((self.repo / ".ds_init" / "journal").iterdir())
        self.assertEqual(len(journals), 1)
        datos = json.loads((journals[0] / "journal.json").read_text(encoding="utf-8"))
        self.assertEqual(datos["fase"], fase)

    def correr_recover(self, *extra):
        return _correr(["recover", "--destino", str(self.repo), *extra])

    def _verificar_fase(self, fase: str) -> None:
        self.simular_v010()
        antes = _hashes_arbol(self.repo)
        self.interrumpir_upgrade(fase)
        # upgrade se niega a seguir y apunta a recover.
        codigo, _out, err = self.correr_upgrade("--execute")
        self.assertEqual(codigo, 1)
        self.assertIn("recover", err)
        # dry-run no escribe.
        interrumpido = _hashes_arbol(self.repo)
        codigo, salida, _err = self.correr_recover()
        self.assertEqual(codigo, 0)
        self.assertIn("fase: " + fase, salida)
        self.assertEqual(interrumpido, _hashes_arbol(self.repo))
        # execute: árbol byte-idéntico al previo al upgrade.
        codigo, _out, err = self.correr_recover("--execute")
        self.assertEqual(codigo, 0, err)
        self.assertEqual(antes, _hashes_arbol(self.repo))
        # upgrade converge y es idempotente.
        codigo, _out, err = self.correr_upgrade("--execute")
        self.assertEqual(codigo, 0, err)
        self.assertTrue((self.repo / RUTA_NUEVA).is_file())
        _commit_todo(self.repo, "post upgrade")
        tras = _hashes_arbol(self.repo)
        codigo, salida, _err = self.correr_upgrade("--execute")
        self.assertEqual(codigo, 0)
        self.assertIn("Nada que hacer", salida)
        self.assertEqual(tras, _hashes_arbol(self.repo))

    def test_recover_fase_preparado(self):
        self._verificar_fase("preparado")

    def test_recover_fase_aplicando(self):
        self._verificar_fase("aplicando")

    def test_recover_fase_control_pendiente(self):
        self._verificar_fase("control_pendiente")

    def test_completo_sin_limpiar_es_housekeeping(self):
        self.simular_v010()
        with mock.patch.object(writer, "_borrar_journal_seguro", return_value=None):
            codigo, _out, err = self.correr_upgrade("--execute")
        self.assertEqual(codigo, 0, err)
        journals = list((self.repo / ".ds_init" / "journal").iterdir())
        self.assertEqual(len(journals), 1)
        esperado = _sin_journal(_hashes_arbol(self.repo))
        codigo, _out, err = self.correr_recover("--execute")
        self.assertEqual(codigo, 0, err)
        self.assertFalse((self.repo / ".ds_init" / "journal").exists())
        # No se revirtió: el upgrade confirmado sigue vigente.
        self.assertEqual(esperado, _hashes_arbol(self.repo))
        _commit_todo(self.repo, "post upgrade")
        codigo, salida, _err = self.correr_upgrade()
        self.assertEqual(codigo, 0)
        self.assertIn("Nada que hacer", salida)

    def test_journal_ilegible_exit_2_sin_cambios(self):
        self.simular_v010()
        self.interrumpir_upgrade("aplicando")
        journal = next((self.repo / ".ds_init" / "journal").iterdir()) / "journal.json"
        journal.write_text("{ no es json", encoding="utf-8")
        antes = _hashes_arbol(self.repo)
        for extra in ((), ("--execute",)):
            codigo, _out, err = self.correr_recover(*extra)
            self.assertEqual(codigo, 2)
            self.assertIn("journal.json", err)
            self.assertEqual(antes, _hashes_arbol(self.repo))

    def test_backup_faltante_exit_2_sin_cambios(self):
        self.simular_v010()
        self.interrumpir_upgrade("aplicando")
        dir_journal = next((self.repo / ".ds_init" / "journal").iterdir())
        backups = [p for p in (dir_journal / "backups").rglob("*") if p.is_file()]
        self.assertTrue(backups)
        backups[0].unlink()
        antes = _hashes_arbol(self.repo)
        codigo, _out, err = self.correr_recover("--execute")
        self.assertEqual(codigo, 2)
        self.assertIn("backup", err)
        self.assertEqual(antes, _hashes_arbol(self.repo))

    def test_staging_huerfano_solo(self):
        antes = _hashes_arbol(self.repo)
        staging = self.repo / ".ds_init_staging_20260101T000000000000Z"
        (staging / "tools").mkdir(parents=True)
        (staging / "tools" / "x.py").write_text("x\n", encoding="utf-8")
        codigo, _out, _err = self.correr_recover()
        self.assertEqual(codigo, 0)
        self.assertTrue(staging.exists())
        codigo, _out, err = self.correr_recover("--execute")
        self.assertEqual(codigo, 0, err)
        self.assertFalse(staging.exists())
        self.assertEqual(antes, _hashes_arbol(self.repo))

    def test_nada_que_recuperar(self):
        antes = _hashes_arbol(self.repo)
        codigo, salida, _err = self.correr_recover("--execute")
        self.assertEqual(codigo, 0)
        self.assertIn("Nada que recuperar", salida)
        self.assertEqual(antes, _hashes_arbol(self.repo))

    def test_install_aborta_ante_huerfano_indicando_recover(self):
        (self.repo / ".ds_init_staging_20260101T000000000000Z").mkdir()
        codigo, _out, err = _correr(
            ["install", "--destino", str(self.repo), "--nombre", "otro", "--execute"]
        )
        self.assertEqual(codigo, 1)
        self.assertIn("recover", err)


import contextlib


@contextlib.contextmanager
def contextlib_exit_stack(parches):
    with contextlib.ExitStack() as pila:
        for p in parches:
            pila.enter_context(p)
        yield


if __name__ == "__main__":
    unittest.main()

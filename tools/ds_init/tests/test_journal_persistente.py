"""Tests del journal persistente en `.ds_init/journal/<ts>/` (v0.11 Change 5)."""
from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.ds_init import writer
from tools.ds_init.planner import construir_plan
from tools.ds_init.preflight import DestinoInvalidoError, validar_destino
from tools.ds_init.tests.test_writer_staging import (
    PERFIL,
    _config_base,
    _crear_repo_git_temporal,
    _snapshot_arbol,
)


class TestJournalPersistente(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_repo_git_temporal()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_journal_vive_en_ds_init_con_fase_y_se_elimina_tras_exito(self):
        config = _config_base(self.repo)
        plan = construir_plan(PERFIL, self.repo, config)
        fases = []
        original = writer._escribir_journal

        def _espia(journal_path, entradas, fase=writer.FASE_APLICANDO):
            self.assertIn(".ds_init", Path(journal_path).parts)
            fases.append(fase)
            return original(journal_path, entradas, fase)

        with patch("tools.ds_init.writer._escribir_journal", side_effect=_espia):
            writer.instalar(plan, self.repo, config)

        self.assertEqual(fases[0], "preparado")
        self.assertIn("control_pendiente", fases)
        self.assertEqual(fases[-1], "completo")
        self.assertFalse((self.repo / ".ds_init" / "journal").exists())
        self.assertTrue((self.repo / ".ds_init" / "control.json").exists())

    def test_journal_permanece_si_el_rollback_falla(self):
        config = _config_base(self.repo)
        plan = construir_plan(PERFIL, self.repo, config)
        with patch(
            "tools.ds_init.writer.control_mod.generar_control",
            side_effect=RuntimeError("fallo inyectado"),
        ), patch(
            "tools.ds_init.writer._revertir_journal",
            return_value=[{"destino": "x", "error": "no se pudo"}],
        ):
            with self.assertRaises(writer.InstalacionAbortadaError):
                writer.instalar(plan, self.repo, config)

        carpetas = list((self.repo / ".ds_init" / "journal").iterdir())
        self.assertEqual(len(carpetas), 1)
        datos = json.loads((carpetas[0] / "journal.json").read_text(encoding="utf-8"))
        self.assertEqual(datos["fase"], "control_pendiente")
        # El preflight lo detecta y da la instrucción literal de recover.
        with self.assertRaises(DestinoInvalidoError) as cm:
            validar_destino(self.repo)
        self.assertIn("python -m tools.ds_init recover --destino", str(cm.exception))

    def test_rollback_exitoso_elimina_el_journal(self):
        config = _config_base(self.repo)
        plan = construir_plan(PERFIL, self.repo, config)
        antes = _snapshot_arbol(self.repo)
        with patch(
            "tools.ds_init.writer.control_mod.generar_control",
            side_effect=RuntimeError("fallo inyectado"),
        ):
            with self.assertRaises(writer.InstalacionAbortadaError):
                writer.instalar(plan, self.repo, config)
        self.assertFalse((self.repo / ".ds_init").exists())
        self.assertEqual(_snapshot_arbol(self.repo), antes)

    def test_post_aplicar_que_falla_revierte_todo(self):
        config = _config_base(self.repo)
        plan = construir_plan(PERFIL, self.repo, config)
        antes = _snapshot_arbol(self.repo)

        def _falla(_resultado):
            raise RuntimeError("regenerar_control fallido")

        config["post_aplicar"] = _falla
        with self.assertRaises(writer.InstalacionAbortadaError) as cm:
            writer.instalar(plan, self.repo, config)
        self.assertIn("regenerar_control fallido", str(cm.exception))
        self.assertEqual(_snapshot_arbol(self.repo), antes)
        self.assertFalse((self.repo / ".ds_init").exists())


if __name__ == "__main__":
    unittest.main()

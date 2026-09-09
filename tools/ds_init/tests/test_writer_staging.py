"""Tests de `tools.ds_init.writer` (Sesión 2): instalación real sobre un
repositorio Git temporal propio (nunca este repositorio, R14/AC15).

Cubre: instalación exitosa (staging se limpia, archivos quedan en destino),
colisión con archivo existente (se omite, no se sobrescribe), preservación de
claves no conflictivas en `.claude/settings.json` existente, y rollback
completo ante un fallo inyectado a mitad de la aplicación del journal.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from tools.ds_init import writer
from tools.ds_init.planner import construir_plan
from tools.ds_init.version import HARNESS_VERSION

# Referencia al `os.replace` real, importada antes de que ningún test
# patchee `tools.ds_init.writer.os.replace` (ver instrucción de invocación).
import os as _os_module

_OS_REPLACE_REAL = _os_module.replace

PERFIL = "python-jupyter-data"


def _crear_repo_git_temporal() -> Path:
    ruta = Path(tempfile.mkdtemp(prefix="ds_init_test_writer_"))
    subprocess.run(["git", "init", str(ruta)], capture_output=True, text=True, check=True)
    subprocess.run(["git", "-C", str(ruta), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(ruta), "config", "user.name", "Test"], check=True)
    (ruta / "README.md").write_text("repo de prueba\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(ruta), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(ruta), "commit", "-m", "inicial"],
        capture_output=True,
        text=True,
        check=True,
    )
    return ruta


def _snapshot_arbol(ruta: Path) -> dict:
    """Nombres relativos -> hash de contenido, para todo archivo bajo `ruta`
    fuera de `.git/` (mismo criterio que `test_cli.py`, no mtime)."""
    snapshot = {}
    for archivo in ruta.rglob("*"):
        if not archivo.is_file():
            continue
        relativo = archivo.relative_to(ruta)
        if ".git" in relativo.parts:
            continue
        snapshot[str(relativo)] = hashlib.sha256(archivo.read_bytes()).hexdigest()
    return snapshot


def _dirs_staging_remanentes(ruta: Path) -> list:
    return [p.name for p in ruta.iterdir() if p.is_dir() and p.name.startswith(".ds_init_staging_")]


def _config_base(destino: Path, nombre: str = "proyecto-de-prueba") -> dict:
    return {
        "perfil": PERFIL,
        "nombre": nombre,
        "notebooks_dir": "notebooks",
        "venv_dir": ".venv",
        "destino": str(destino),
        "integrar_claude": False,
        "placeholders": {
            "NOMBRE_PROYECTO": nombre,
            "NOTEBOOKS_DIR": "notebooks",
            "VENV_DIR": ".venv",
            "FECHA_INSTALACION": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "HARNESS_VERSION": HARNESS_VERSION,
            "RUTAS_PROHIBIDAS_JSON": "[]",
        },
    }


class TestInstalacionExitosa(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_repo_git_temporal()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_instalacion_exitosa_aplica_archivos_y_no_deja_staging(self):
        config = _config_base(self.repo)
        plan = construir_plan(PERFIL, self.repo, config)

        resultado = writer.instalar(plan, self.repo, config)

        self.assertTrue(len(resultado.aplicados) > 0)
        for ruta_relativa in resultado.aplicados:
            self.assertTrue(
                (self.repo / ruta_relativa).exists(),
                f"{ruta_relativa} no quedó presente en el destino",
            )

        self.assertEqual(
            _dirs_staging_remanentes(self.repo),
            [],
            "Quedó un directorio de staging sin limpiar tras una instalación exitosa",
        )

        # Archivo emblemático del harness realmente presente.
        self.assertTrue((self.repo / "tools" / "ds_guard.py").exists())
        self.assertTrue((self.repo / ".ds_init" / "control.json").exists())


class TestColisionOmiteSinSobrescribir(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_repo_git_temporal()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_archivo_ya_existente_queda_omitido_y_no_se_sobrescribe(self):
        # `tools/ds_guard.py` es una entrada VERBATIM del manifiesto: la
        # colisionamos escribiendo contenido propio antes de instalar.
        destino_colision = self.repo / "tools" / "ds_guard.py"
        destino_colision.parent.mkdir(parents=True, exist_ok=True)
        contenido_original = "# contenido original del destino, no debe tocarse\n"
        destino_colision.write_text(contenido_original, encoding="utf-8")

        config = _config_base(self.repo)
        plan = construir_plan(PERFIL, self.repo, config)

        resultado = writer.instalar(plan, self.repo, config)

        self.assertIn("tools/ds_guard.py", resultado.omitidos)
        self.assertNotIn("tools/ds_guard.py", resultado.aplicados)
        self.assertEqual(destino_colision.read_text(encoding="utf-8"), contenido_original)


class TestPreservaConfiguracionExistente(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_repo_git_temporal()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_clave_propia_no_conflictiva_sobrevive_al_merge(self):
        dir_claude = self.repo / ".claude"
        dir_claude.mkdir(parents=True, exist_ok=True)
        settings_existente = {
            "miClaveDeProyecto": {"algo": "propio"},
        }
        (dir_claude / "settings.json").write_text(
            json.dumps(settings_existente, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        config = _config_base(self.repo)
        plan = construir_plan(PERFIL, self.repo, config)

        writer.instalar(plan, self.repo, config)

        settings_final = json.loads((dir_claude / "settings.json").read_text(encoding="utf-8"))
        self.assertIn("miClaveDeProyecto", settings_final)
        self.assertEqual(settings_final["miClaveDeProyecto"], {"algo": "propio"})
        # Y las claves propias del harness también deben haber llegado.
        self.assertIn("hooks", settings_final)


class TestRollbackAnteFalloInyectado(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_repo_git_temporal()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_fallo_a_mitad_de_journal_revierte_todo(self):
        config = _config_base(self.repo)
        plan = construir_plan(PERFIL, self.repo, config)

        snapshot_antes = _snapshot_arbol(self.repo)

        llamadas = {"n": 0}
        LIMITE_EXITOSO = 3  # deja pasar las primeras 3 aplicaciones, falla en la 4ta.

        def _replace_con_fallo(origen, destino_final):
            llamadas["n"] += 1
            if llamadas["n"] > LIMITE_EXITOSO:
                raise OSError("fallo inyectado por el test a mitad del journal")
            return _OS_REPLACE_REAL(origen, destino_final)

        with patch("tools.ds_init.writer.os.replace", side_effect=_replace_con_fallo):
            with self.assertRaises(writer.InstalacionAbortadaError):
                writer.instalar(plan, self.repo, config)

        self.assertGreater(llamadas["n"], LIMITE_EXITOSO, "el mock no llegó a inyectar el fallo")

        snapshot_despues = _snapshot_arbol(self.repo)
        self.assertEqual(
            snapshot_antes,
            snapshot_despues,
            "El destino quedó modificado tras un rollback: debía quedar exactamente como antes",
        )
        self.assertEqual(
            _dirs_staging_remanentes(self.repo),
            [],
            "Quedó un directorio de staging sin limpiar tras el rollback",
        )


class TestFalloAntesDeAplicarJournalNoDejaStaging(unittest.TestCase):
    """Hallazgo 1: un fallo en `_preparar_backups`/`_escribir_journal` (antes
    de que `_aplicar_journal` arranque) también debe abortar limpio, sin
    directorio `.ds_init_staging_*` remanente en el destino."""

    def setUp(self):
        self.repo = _crear_repo_git_temporal()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_fallo_en_preparar_backups_aborta_y_limpia_staging(self):
        config = _config_base(self.repo)
        plan = construir_plan(PERFIL, self.repo, config)

        snapshot_antes = _snapshot_arbol(self.repo)

        with patch(
            "tools.ds_init.writer._preparar_backups",
            side_effect=OSError("fallo inyectado por el test antes de aplicar el journal"),
        ):
            with self.assertRaises(writer.InstalacionAbortadaError):
                writer.instalar(plan, self.repo, config)

        snapshot_despues = _snapshot_arbol(self.repo)
        self.assertEqual(
            snapshot_antes,
            snapshot_despues,
            "El destino quedó modificado tras abortar antes de aplicar el journal",
        )
        self.assertEqual(
            _dirs_staging_remanentes(self.repo),
            [],
            "Quedó un directorio de staging sin limpiar tras un fallo en _preparar_backups",
        )


if __name__ == "__main__":
    unittest.main()

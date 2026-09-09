"""Tests de `tools.ds_init.control`: el archivo de control (R12) que se
escribe en `<destino>/.ds_init/control.json` tras una instalación exitosa.
Usa un repositorio Git temporal propio (nunca este repositorio, R14/AC15)."""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from tools.ds_init import control as control_mod
from tools.ds_init import writer
from tools.ds_init.planner import construir_plan
from tools.ds_init.version import HARNESS_VERSION

PERFIL = "python-jupyter-data"


def _crear_repo_git_temporal() -> Path:
    ruta = Path(tempfile.mkdtemp(prefix="ds_init_test_control_"))
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


class TestArchivoDeControl(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_repo_git_temporal()
        self.config = _config_base(self.repo)
        plan = construir_plan(PERFIL, self.repo, self.config)
        self.resultado = writer.instalar(plan, self.repo, self.config)
        self.ruta_control = self.repo / ".ds_init" / "control.json"

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_control_json_existe_y_es_json_valido(self):
        self.assertTrue(self.ruta_control.exists())
        contenido = json.loads(self.ruta_control.read_text(encoding="utf-8"))
        self.assertIsInstance(contenido, dict)

    def test_control_json_tiene_campos_esperados(self):
        contenido = json.loads(self.ruta_control.read_text(encoding="utf-8"))

        self.assertEqual(contenido["harness_version"], HARNESS_VERSION)
        self.assertEqual(contenido["perfil"], PERFIL)
        self.assertIn("fecha_utc", contenido)
        self.assertTrue(contenido["fecha_utc"])

        self.assertIn("configuracion", contenido)
        configuracion = contenido["configuracion"]
        self.assertEqual(configuracion["nombre"], self.config["nombre"])
        self.assertEqual(configuracion["notebooks_dir"], self.config["notebooks_dir"])
        self.assertEqual(configuracion["venv_dir"], self.config["venv_dir"])
        self.assertEqual(configuracion["destino"], self.config["destino"])

        self.assertIn("archivos", contenido)
        self.assertTrue(len(contenido["archivos"]) > 0)

    def test_hashes_coinciden_con_los_archivos_reales_del_destino(self):
        contenido = json.loads(self.ruta_control.read_text(encoding="utf-8"))

        rutas_listadas = {entrada["ruta"] for entrada in contenido["archivos"]}
        self.assertEqual(rutas_listadas, set(self.resultado.aplicados))

        for entrada in contenido["archivos"]:
            ruta_absoluta = self.repo / entrada["ruta"]
            self.assertTrue(ruta_absoluta.exists(), f"{entrada['ruta']} listado en control.json no existe")
            hash_real = control_mod._sha256_de_archivo(ruta_absoluta)
            self.assertEqual(
                entrada["sha256"],
                hash_real,
                f"hash SHA-256 de {entrada['ruta']} no coincide con el archivo real",
            )


if __name__ == "__main__":
    unittest.main()

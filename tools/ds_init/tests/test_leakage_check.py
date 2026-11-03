"""Test de la red de seguridad final de `writer._validar_staging` (R17): si
alguna cadena prohibida termina en un archivo del staging, la instalación
completa se aborta antes de tocar el destino. Usa un repositorio Git temporal
propio (nunca este repositorio, R14/AC15)."""
from __future__ import annotations

import hashlib
import shutil
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from tools.ds_init import writer
from tools.ds_init.planner import construir_plan
from tools.ds_init.version import HARNESS_VERSION

PERFIL = "python-jupyter-data"

# `writer.CADENAS_PROHIBIDAS` viene vacía por defecto (Harmessi no embebe
# cadenas propias): estos tests parchean una cadena de prueba para ejercitar
# el mecanismo de R17 sin depender de ningún contenido real embebido.
CADENA_PROHIBIDA_DE_PRUEBA = "CADENA-PROHIBIDA-DE-PRUEBA"


def _crear_repo_git_temporal() -> Path:
    ruta = Path(tempfile.mkdtemp(prefix="ds_init_test_leakage_"))
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


def _config_con_cadena_prohibida(destino: Path) -> dict:
    # `NOMBRE_PROYECTO` se sustituye literalmente (sin escapar) en varias
    # plantillas (CLAUDE.md.tmpl, SKILL_lead_data_scientist.md.tmpl,
    # smoke_test_generico.py.tmpl): usar una cadena prohibida como nombre de
    # proyecto es la forma más directa de que termine en el staging real,
    # ejercitando `_validar_staging` con el código de producción tal cual.
    nombre_prohibido = CADENA_PROHIBIDA_DE_PRUEBA
    return {
        "perfil": PERFIL,
        "nombre": nombre_prohibido,
        "notebooks_dir": "notebooks",
        "venv_dir": ".venv",
        "destino": str(destino),
        "integrar_claude": False,
        "placeholders": {
            "NOMBRE_PROYECTO": nombre_prohibido,
            "NOTEBOOKS_DIR": "notebooks",
            "VENV_DIR": ".venv",
            "FECHA_INSTALACION": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "HARNESS_VERSION": HARNESS_VERSION,
            "RUTAS_PROHIBIDAS_JSON": "[]",
        },
    }


class TestLeakageCheckAbortaInstalacion(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_repo_git_temporal()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_cadena_prohibida_en_staging_aborta_antes_de_tocar_destino(self):
        config = _config_con_cadena_prohibida(self.repo)
        plan = construir_plan(PERFIL, self.repo, config)

        snapshot_antes = _snapshot_arbol(self.repo)

        with mock.patch.object(writer, "CADENAS_PROHIBIDAS", (CADENA_PROHIBIDA_DE_PRUEBA,)):
            with self.assertRaises(writer.InstalacionAbortadaError) as ctx:
                writer.instalar(plan, self.repo, config)

        self.assertIn(CADENA_PROHIBIDA_DE_PRUEBA, str(ctx.exception))

        # El destino queda exactamente como antes: nada del plan se aplicó.
        self.assertEqual(_snapshot_arbol(self.repo), snapshot_antes)
        self.assertEqual(
            _dirs_staging_remanentes(self.repo),
            [],
            "Quedó un directorio de staging sin limpiar tras el aborto por leakage",
        )
        self.assertFalse((self.repo / ".ds_init").exists())

    def test_validar_staging_detecta_directamente_una_cadena_prohibida(self):
        # Complementa el test end-to-end de arriba ejercitando
        # `_validar_staging` en forma aislada sobre un staging armado a mano,
        # sin depender de qué plantilla del manifiesto use el placeholder.
        staging = self.repo / ".ds_init_staging_manual"
        staging.mkdir()
        archivo_filtrado = staging / "algun_archivo.txt"
        archivo_filtrado.write_text(
            f"referencia a una cadena prohibida: {CADENA_PROHIBIDA_DE_PRUEBA}\n",
            encoding="utf-8",
        )

        with mock.patch.object(writer, "CADENAS_PROHIBIDAS", (CADENA_PROHIBIDA_DE_PRUEBA,)):
            with self.assertRaises(writer.InstalacionAbortadaError) as ctx:
                writer._validar_staging(staging)

        self.assertIn(CADENA_PROHIBIDA_DE_PRUEBA, str(ctx.exception))

        shutil.rmtree(staging, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()

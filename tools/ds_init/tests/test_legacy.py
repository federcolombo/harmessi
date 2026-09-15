"""Tests de `tools.ds_init.legacy.inferir_installation_stage` (R6 de
`spec.md`, Change 7 v0.3). Usa repositorios Git temporales propios (nunca
este repositorio, R14/AC15). Función pura: nunca escribe nada -- los tests lo
verifican explícitamente."""
from __future__ import annotations

import hashlib
import shutil
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from tools.ds_init import legacy
from tools.ds_init import writer
from tools.ds_init.planner import construir_plan
from tools.ds_init.version import HARNESS_VERSION

PERFIL = "python-jupyter-data"


def _crear_repo_git_temporal(prefix: str = "ds_init_test_legacy_") -> Path:
    ruta = Path(tempfile.mkdtemp(prefix=prefix))
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


def _config_base(destino: Path, stage=None, nombre: str = "proyecto-de-prueba") -> dict:
    config = {
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
    if stage is not None:
        config["stage"] = stage
    return config


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


class TestInferirInstallationStage(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_repo_git_temporal()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_infiere_production_si_archivos_experiment_estan_completos(self):
        # Instalación "legacy simulada" -- todo el manifiesto, sin noción de
        # stage (config sin la clave 'stage'), igual que una instalación
        # anterior a este change (`incluye_todo: true`).
        config = _config_base(self.repo)
        plan = construir_plan(PERFIL, self.repo, config)
        writer.instalar(plan, self.repo, config)

        resultado = legacy.inferir_installation_stage(self.repo, PERFIL)
        self.assertEqual(resultado, "production")

    def test_infiere_discovery_si_faltan_archivos_experiment(self):
        # Instalación real pero solo hasta 'discovery': los archivos de
        # 'experiment' (agentes/decision-ledger.md) nunca se instalaron.
        config = _config_base(self.repo, stage="discovery")
        plan = construir_plan(PERFIL, self.repo, config, stage="discovery")
        writer.instalar(plan, self.repo, config)

        resultado = legacy.inferir_installation_stage(self.repo, PERFIL)
        self.assertEqual(resultado, "discovery")

    def test_infiere_discovery_en_destino_vacio(self):
        resultado = legacy.inferir_installation_stage(self.repo, PERFIL)
        self.assertEqual(resultado, "discovery")

    def test_infiere_discovery_si_falta_un_solo_archivo_experiment(self):
        config = _config_base(self.repo)
        plan = construir_plan(PERFIL, self.repo, config)
        writer.instalar(plan, self.repo, config)
        (self.repo / ".claude" / "agents" / "notebook-runner.md").unlink()

        resultado = legacy.inferir_installation_stage(self.repo, PERFIL)
        self.assertEqual(resultado, "discovery")

    def test_nunca_escribe_nada_en_el_destino(self):
        config = _config_base(self.repo)
        plan = construir_plan(PERFIL, self.repo, config)
        writer.instalar(plan, self.repo, config)

        snapshot_antes = _snapshot_arbol(self.repo)
        legacy.inferir_installation_stage(self.repo, PERFIL)
        legacy.inferir_installation_stage(self.repo, PERFIL)

        self.assertEqual(_snapshot_arbol(self.repo), snapshot_antes)


if __name__ == "__main__":
    unittest.main()

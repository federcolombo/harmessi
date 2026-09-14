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
        self.assertEqual(configuracion["destino"], ".")

        self.assertIn("archivos", contenido)
        self.assertTrue(len(contenido["archivos"]) > 0)

    def test_destino_no_es_una_ruta_absoluta(self):
        """El control.json vive dentro del propio destino instalado: grabar
        ahi la ruta absoluta de la maquina/usuario que corrio la instalacion
        no aporta informacion y filtra datos locales/privados al repo
        versionado. `configuracion.destino` debe ser una referencia
        portable, nunca una ruta absoluta (ni POSIX ni Windows)."""
        contenido = json.loads(self.ruta_control.read_text(encoding="utf-8"))
        destino_registrado = contenido["configuracion"]["destino"]

        self.assertFalse(Path(destino_registrado).is_absolute())
        self.assertFalse(destino_registrado.startswith("/"))
        self.assertNotRegex(destino_registrado, r"^[A-Za-z]:[\\/]")
        self.assertNotIn(str(self.repo), destino_registrado)

    def test_hashes_coinciden_con_los_archivos_reales_del_destino(self):
        contenido = json.loads(self.ruta_control.read_text(encoding="utf-8"))

        rutas_listadas = {entrada["ruta"] for entrada in contenido["archivos"]}
        self.assertEqual(rutas_listadas, set(self.resultado.aplicados))

        for entrada in contenido["archivos"]:
            ruta_absoluta = self.repo / entrada["ruta"]
            self.assertTrue(ruta_absoluta.exists(), f"{entrada['ruta']} listado en control.json no existe")
            hash_real = control_mod.sha256_de_archivo(ruta_absoluta)
            self.assertEqual(
                entrada["sha256"],
                hash_real,
                f"hash SHA-256 de {entrada['ruta']} no coincide con el archivo real",
            )


class TestGenerarControlSinFechaUtc(unittest.TestCase):
    """No-regresión: `generar_control()` sin pasar `fecha_utc` debe seguir
    comportándose exactamente igual que antes del cambio (estampa
    `datetime.now(timezone.utc)`)."""

    def setUp(self):
        self.repo = _crear_repo_git_temporal()
        self.config = _config_base(self.repo)
        plan = construir_plan(PERFIL, self.repo, self.config)
        self.resultado = writer.instalar(plan, self.repo, self.config)
        self.ruta_control = self.repo / ".ds_init" / "control.json"

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_generar_control_sin_fecha_utc_estampa_ahora(self):
        antes = datetime.now(timezone.utc)
        control = control_mod.generar_control(
            self.repo,
            PERFIL,
            self.config,
            self.resultado.aplicados,
        )
        despues = datetime.now(timezone.utc)

        fecha_control = datetime.strptime(control["fecha_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
        self.assertGreaterEqual(fecha_control, antes.replace(microsecond=0))
        self.assertLessEqual(fecha_control, despues)


class TestRegenerarControl(unittest.TestCase):
    """Tests de `regenerar_control()` (tarea 2/3 del change
    20260914-fix-harness-version-drift). Repo git temporal propio, nunca este
    repositorio (R14/AC15)."""

    def setUp(self):
        self.repo = _crear_repo_git_temporal()
        self.config = _config_base(self.repo)
        plan = construir_plan(PERFIL, self.repo, self.config)
        self.resultado = writer.instalar(plan, self.repo, self.config)
        self.ruta_control = self.repo / ".ds_init" / "control.json"
        self.control_previo = json.loads(self.ruta_control.read_text(encoding="utf-8"))

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_preserva_configuracion_exactamente(self):
        control_nuevo = control_mod.regenerar_control(self.repo, self.control_previo)
        self.assertEqual(control_nuevo["configuracion"], self.control_previo["configuracion"])

    def test_preserva_fecha_utc_original(self):
        control_previo = dict(self.control_previo)
        control_previo["fecha_utc"] = "2026-09-09T18:08:09Z"
        self.ruta_control.write_text(json.dumps(control_previo, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

        control_nuevo = control_mod.regenerar_control(self.repo, control_previo)
        self.assertEqual(control_nuevo["fecha_utc"], "2026-09-09T18:08:09Z")

    def test_actualiza_harness_version_al_valor_vigente(self):
        control_previo = dict(self.control_previo)
        control_previo["harness_version"] = "0.1.0"

        control_nuevo = control_mod.regenerar_control(self.repo, control_previo)
        self.assertEqual(control_nuevo["harness_version"], HARNESS_VERSION)

    def test_reconstruye_archivos_exclusivamente_desde_manifest_vigente(self):
        from tools.ds_init.manifest import manifest_para_perfil

        control_nuevo = control_mod.regenerar_control(self.repo, self.control_previo)

        rutas_esperadas = {
            entrada.destino
            for entrada in manifest_para_perfil(self.control_previo["perfil"])
            if entrada.destino != ".ds_init/control.json"
        }
        rutas_obtenidas = {entrada["ruta"] for entrada in control_nuevo["archivos"]}
        self.assertEqual(rutas_obtenidas, rutas_esperadas)

        for entrada in control_nuevo["archivos"]:
            ruta_absoluta = self.repo / entrada["ruta"]
            hash_real = control_mod.sha256_de_archivo(ruta_absoluta)
            self.assertEqual(entrada["sha256"], hash_real)

    def test_no_conserva_entradas_obsoletas(self):
        control_previo = json.loads(json.dumps(self.control_previo))
        control_previo["archivos"].append(
            {"ruta": "archivo-obsoleto-inventado.md", "sha256": "0" * 64}
        )

        control_nuevo = control_mod.regenerar_control(self.repo, control_previo)

        rutas_obtenidas = {entrada["ruta"] for entrada in control_nuevo["archivos"]}
        self.assertNotIn("archivo-obsoleto-inventado.md", rutas_obtenidas)


if __name__ == "__main__":
    unittest.main()

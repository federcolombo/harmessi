"""Tests de `ds_init upgrade` (v0.11 Change 5, R2/R3/R7). Usan repositorios Git
temporales propios (nunca este repositorio): se instala con la versión actual,
se simula un proyecto 'v0.10' (harness_version vieja, contenido managed
degradado con su hash baseline actualizado, un managed borrado del control) y
se corre `upgrade`."""
from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.ds_init import control as control_mod
from tools.ds_init import managed_hash
from tools.ds_init.cli import main
from tools.ds_init.manifest import contenido_de, raiz_repo_origen
from tools.ds_init.version import HARNESS_VERSION

RUTA_DEGRADADO_A = "tools/ds_guard.py"
RUTA_DEGRADADO_B = ".claude/agents/metodologo.md"
RUTA_NUEVA = "tools/dsguard/scope_amendments.py"  # se simula 'managed nuevo'
RUTA_DRIFT = "tools/dsguard/guardrails_drift.py"
RUTA_GUARDRAILS = ".claude/guardrails.json"
RUTAS_PROYECTO = {
    "notebooks/analisis.ipynb": '{"cells": []}\n',
    "openspec/decisions/ledger.jsonl": '{"id": 1}\n',
    "GLOSSARY.md": "# glosario propio\n",
}


def _git(repo: Path, *argumentos) -> None:
    subprocess.run(["git", "-C", str(repo), *argumentos], check=True, capture_output=True, text=True)


def _commit_todo(repo: Path, mensaje: str) -> None:
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", mensaje, "--allow-empty")


def _borrar_arbol(ruta: Path) -> None:
    def _forzar(func, path, _exc):
        os.chmod(path, stat.S_IWRITE)
        func(path)

    shutil.rmtree(ruta, onerror=_forzar)


def _correr(argv: list):
    salida, error = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(salida), contextlib.redirect_stderr(error):
        try:
            codigo = main(argv)
        except SystemExit as exc:  # parser.error
            codigo = exc.code
    return codigo, salida.getvalue(), error.getvalue()


def _hashes_arbol(repo: Path) -> dict:
    """{ruta relativa: sha256 de bytes} de todo el árbol salvo `.git`."""
    import hashlib

    resultado = {}
    for p in sorted(repo.rglob("*")):
        if p.is_file() and ".git" not in p.relative_to(repo).parts[:1]:
            resultado[p.relative_to(repo).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    return resultado


def _ruta_control(repo: Path) -> Path:
    return repo / control_mod.DIR_CONTROL / control_mod.NOMBRE_ARCHIVO_CONTROL


def _leer_control(repo: Path) -> dict:
    return json.loads(_ruta_control(repo).read_text(encoding="utf-8"))


def _escribir_control(repo: Path, control: dict) -> None:
    _ruta_control(repo).write_text(json.dumps(control, indent=2) + "\n", encoding="utf-8", newline="")


def _rebasar_hash(repo: Path, control: dict, ruta: str) -> None:
    """Actualiza en `control` el hash baseline de `ruta` al contenido actual."""
    algoritmo = managed_hash.algoritmo_para_contenido(contenido_de(ruta))
    for entrada in control["archivos"]:
        if entrada["ruta"] == ruta:
            entrada["sha256"] = managed_hash.hash_managed_file(repo / ruta, algoritmo)
            entrada["hash_alg"] = algoritmo
            return
    raise AssertionError(f"{ruta} no está en el control instalado")


class _BaseUpgrade(unittest.TestCase):
    _plantilla: Path = None

    @classmethod
    def setUpClass(cls):
        # Se instala UNA vez; cada test trabaja sobre una copia.
        cls._plantilla = Path(tempfile.mkdtemp(prefix="ds_init_test_upgrade_tpl_"))
        subprocess.run(["git", "init", str(cls._plantilla)], capture_output=True, text=True, check=True)
        _git(cls._plantilla, "config", "user.email", "test@example.com")
        _git(cls._plantilla, "config", "user.name", "Test")
        (cls._plantilla / "README.md").write_text("repo de prueba\n", encoding="utf-8")
        _commit_todo(cls._plantilla, "inicial")
        codigo, _out, err = _correr(
            ["install", "--destino", str(cls._plantilla), "--nombre", "proyecto_demo", "--execute"]
        )
        assert codigo == 0, err
        rutas = {e["ruta"] for e in _leer_control(cls._plantilla)["archivos"]}
        for ruta in (RUTA_DEGRADADO_A, RUTA_DEGRADADO_B, RUTA_NUEVA, RUTA_DRIFT, RUTA_GUARDRAILS):
            assert ruta in rutas, f"{ruta} no quedó instalado: ajustar las rutas del test"
        _commit_todo(cls._plantilla, "instalado")

    @classmethod
    def tearDownClass(cls):
        _borrar_arbol(cls._plantilla)

    def setUp(self):
        self.repo = Path(tempfile.mkdtemp(prefix="ds_init_test_upgrade_")) / "repo"
        shutil.copytree(self._plantilla, self.repo)
        self.addCleanup(_borrar_arbol, self.repo.parent)

    def simular_v010(self, con_drift: bool = False) -> None:
        """Convierte la instalación actual en un 'v0.10' sintético y commitea."""
        control = _leer_control(self.repo)
        control["harness_version"] = "0.10.0"
        for ruta in (RUTA_DEGRADADO_A, RUTA_DEGRADADO_B):
            with open(self.repo / ruta, "a", encoding="utf-8", newline="") as f:
                f.write("\n# contenido v0.10 degradado\n")
            _rebasar_hash(self.repo, control, ruta)  # pristine respecto del baseline
        # Managed 'nuevo' en el manifest actual: no estaba en la instalación v0.10.
        (self.repo / RUTA_NUEVA).unlink()
        control["archivos"] = [e for e in control["archivos"] if e["ruta"] != RUTA_NUEVA]
        if con_drift:
            # Modificado por el usuario SIN actualizar el baseline -> drift.
            with open(self.repo / RUTA_DRIFT, "a", encoding="utf-8", newline="") as f:
                f.write("\n# edición del usuario\n")
        _escribir_control(self.repo, control)
        _commit_todo(self.repo, "simulacion v0.10")

    def agregar_archivos_proyecto(self) -> None:
        for ruta, contenido in RUTAS_PROYECTO.items():
            p = self.repo / ruta
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(contenido, encoding="utf-8", newline="")
        _commit_todo(self.repo, "archivos del proyecto")

    def correr_upgrade(self, *extra):
        return _correr(["upgrade", "--destino", str(self.repo), *extra])


class TestUpgrade(_BaseUpgrade):
    def test_dry_run_no_escribe_nada(self):
        self.simular_v010(con_drift=True)
        antes = _hashes_arbol(self.repo)
        codigo, salida, _err = self.correr_upgrade()
        self.assertEqual(codigo, 0)
        self.assertEqual(antes, _hashes_arbol(self.repo))
        self.assertIn("DRY-RUN", salida)
        self.assertIn("0.10.0", salida)
        self.assertIn(RUTA_DEGRADADO_A, salida)
        self.assertIn(RUTA_NUEVA, salida)

    def test_execute_actualiza_managed_pristine(self):
        self.simular_v010()
        codigo, _out, err = self.correr_upgrade("--execute")
        self.assertEqual(codigo, 0, err)
        for ruta in (RUTA_DEGRADADO_A, RUTA_DEGRADADO_B):
            algoritmo = managed_hash.algoritmo_para_contenido(contenido_de(ruta))
            self.assertEqual(
                managed_hash.hash_managed_file(self.repo / ruta, algoritmo),
                managed_hash.hash_managed_file(raiz_repo_origen() / ruta, algoritmo),
                f"{ruta} no quedó con el contenido distribuido",
            )
        control = _leer_control(self.repo)
        self.assertEqual(control["harness_version"], HARNESS_VERSION)
        entradas = {e["ruta"]: e for e in control["archivos"]}
        algoritmo = managed_hash.algoritmo_para_contenido(contenido_de(RUTA_DEGRADADO_A))
        self.assertEqual(
            entradas[RUTA_DEGRADADO_A]["sha256"],
            managed_hash.hash_managed_file(self.repo / RUTA_DEGRADADO_A, algoritmo),
        )
        # Sin restos de transacción ni lock.
        self.assertFalse((self.repo / ".ds_init" / "lock").exists())
        self.assertFalse((self.repo / ".ds_init" / "journal").exists())
        self.assertEqual([p.name for p in self.repo.glob(".ds_init_staging_*")], [])

    def test_execute_crea_managed_nuevo(self):
        self.simular_v010()
        self.assertFalse((self.repo / RUTA_NUEVA).exists())
        codigo, _out, err = self.correr_upgrade("--execute")
        self.assertEqual(codigo, 0, err)
        self.assertTrue((self.repo / RUTA_NUEVA).is_file())
        self.assertIn(RUTA_NUEVA, {e["ruta"] for e in _leer_control(self.repo)["archivos"]})

    def test_no_toca_drift(self):
        self.simular_v010(con_drift=True)
        bytes_drift = (self.repo / RUTA_DRIFT).read_bytes()
        sha_baseline = {e["ruta"]: e["sha256"] for e in _leer_control(self.repo)["archivos"]}[RUTA_DRIFT]
        codigo, salida, err = self.correr_upgrade("--execute")
        self.assertEqual(codigo, 0, err)
        self.assertIn(RUTA_DRIFT, salida)
        self.assertEqual(bytes_drift, (self.repo / RUTA_DRIFT).read_bytes())
        sha_post = {e["ruta"]: e["sha256"] for e in _leer_control(self.repo)["archivos"]}[RUTA_DRIFT]
        self.assertEqual(sha_baseline, sha_post, "el drift no debe adoptarse en el baseline")

    def test_no_toca_project_owned_ni_guardrails_customizado(self):
        # guardrails customizado por el usuario (con baseline actualizado o no,
        # igual no se sobrescribe).
        guardrails = self.repo / RUTA_GUARDRAILS
        guardrails.write_text(guardrails.read_text(encoding="utf-8") + "\n", encoding="utf-8", newline="")
        self.agregar_archivos_proyecto()
        self.simular_v010()
        protegidos = list(RUTAS_PROYECTO) + [RUTA_GUARDRAILS]
        antes = {r: (self.repo / r).read_bytes() for r in protegidos}
        codigo, _out, err = self.correr_upgrade("--execute")
        self.assertEqual(codigo, 0, err)
        for ruta in protegidos:
            self.assertEqual(antes[ruta], (self.repo / ruta).read_bytes(), ruta)

    def test_idempotente(self):
        self.simular_v010(con_drift=True)
        codigo, _out, err = self.correr_upgrade("--execute")
        self.assertEqual(codigo, 0, err)
        _commit_todo(self.repo, "post upgrade")
        tras_primera = _hashes_arbol(self.repo)
        codigo, salida, err = self.correr_upgrade("--execute")
        self.assertEqual(codigo, 0, err)
        self.assertIn("Nada que hacer", salida)
        self.assertEqual(tras_primera, _hashes_arbol(self.repo))

    def test_nada_que_hacer_en_instalacion_actual(self):
        antes = _hashes_arbol(self.repo)
        codigo, salida, _err = self.correr_upgrade()
        self.assertEqual(codigo, 0)
        self.assertIn("Nada que hacer", salida)
        self.assertEqual(antes, _hashes_arbol(self.repo))

    def test_solo_version_distinta_actualiza_control(self):
        control = _leer_control(self.repo)
        control["harness_version"] = "0.10.0"
        _escribir_control(self.repo, control)
        _commit_todo(self.repo, "version vieja")
        codigo, _out, err = self.correr_upgrade("--execute")
        self.assertEqual(codigo, 0, err)
        self.assertEqual(_leer_control(self.repo)["harness_version"], HARNESS_VERSION)

    def test_aborta_por_staging_huerfano(self):
        self.simular_v010()
        (self.repo / ".ds_init_staging_20260101T000000000000Z").mkdir()
        antes = _hashes_arbol(self.repo)
        codigo, _out, err = self.correr_upgrade("--execute")
        self.assertEqual(codigo, 1)
        self.assertIn("recover", err)
        self.assertEqual(antes, _hashes_arbol(self.repo))

    def test_aborta_por_journal_huerfano(self):
        self.simular_v010()
        dir_journal = self.repo / ".ds_init" / "journal" / "20260101T000000000000Z"
        dir_journal.mkdir(parents=True)
        (dir_journal / "journal.json").write_text('{"fase": "aplicando", "entradas": []}\n', encoding="utf-8")
        codigo, _out, err = self.correr_upgrade("--execute")
        self.assertEqual(codigo, 1)
        self.assertIn("recover", err)

    def test_control_ilegible_exit_2(self):
        _ruta_control(self.repo).write_text("{ esto no es json", encoding="utf-8")
        codigo, _out, err = self.correr_upgrade("--execute")
        self.assertEqual(codigo, 2)
        self.assertIn("control.json", err)


if __name__ == "__main__":
    unittest.main()

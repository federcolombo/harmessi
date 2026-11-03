"""Smoke test end-to-end de `tools.ds_init.cli`: `--dry-run` no escribe nada,
`--execute` instala correctamente sobre un repositorio Git temporal propio
(nunca este repositorio, R14/AC15), y ninguna cadena prohibida termina en el
árbol instalado."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools.ds_init.cli import main

# Regresión: ninguna ruta absoluta de la máquina/repositorio de desarrollo
# (calculada en runtime, nunca hardcodeada) debe terminar en el árbol
# instalado en el repositorio Git temporal de este test.
RAIZ_REPO_ORIGEN = str(Path(__file__).resolve().parents[3])
CADENAS_PROHIBIDAS = (RAIZ_REPO_ORIGEN,)


def _crear_repo_git_temporal() -> Path:
    ruta = Path(tempfile.mkdtemp(prefix="ds_init_test_integracion_"))
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
    """Mismo criterio que `test_cli.py`: hash de contenido, no mtime."""
    snapshot = {}
    for archivo in ruta.rglob("*"):
        if not archivo.is_file():
            continue
        relativo = archivo.relative_to(ruta)
        if ".git" in relativo.parts:
            continue
        snapshot[str(relativo)] = hashlib.sha256(archivo.read_bytes()).hexdigest()
    return snapshot


def _git_status_porcelain(ruta: Path) -> str:
    resultado = subprocess.run(
        ["git", "-C", str(ruta), "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=True,
    )
    return resultado.stdout


class TestIntegracionInstalacionCompleta(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_repo_git_temporal()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_dry_run_luego_execute_instala_correctamente(self):
        snapshot_antes = _snapshot_arbol(self.repo)

        # --dry-run no debe escribir nada.
        codigo = main(
            [
                "--destino",
                str(self.repo),
                "--nombre",
                "proyecto-de-prueba",
                "--dry-run",
            ]
        )
        self.assertEqual(codigo, 0)
        self.assertEqual(_snapshot_arbol(self.repo), snapshot_antes)

        # --execute sí instala.
        codigo = main(
            [
                "--destino",
                str(self.repo),
                "--nombre",
                "proyecto-de-prueba",
                "--execute",
            ]
        )
        self.assertEqual(codigo, 0)

        archivos_clave = (
            ".claude/agents/python-data-engineer.md",
            "tools/ds_guard.py",
            "tools/dsguard/lifecycle.py",
            "tools/dsguard/kdd_compat.py",
            "tools/dsguard/maturity.py",
            "tools/dsguard/checks.py",
            "tools/dsguard/mlops_foundations.py",
            "tools/dsguard/mlops_evidence.py",
            "tools/dsguard/readiness.py",
            "tools/dsguard/status.py",
            ".ds_init/control.json",
        )
        for relativo in archivos_clave:
            self.assertTrue(
                (self.repo / relativo).exists(),
                f"Archivo clave no instalado: {relativo}",
            )

        # `.harmessi/project.json` es estado generado en uso (Change 3
        # v0.3), no contenido estático -- la instalación scratch nunca debe
        # crearlo.
        self.assertFalse(
            (self.repo / ".harmessi" / "project.json").exists(),
            "La instalación scratch no debe crear .harmessi/project.json (es estado generado en uso).",
        )

        # `ds_guard status` (sin --change-id, Change 8 v0.3:
        # 20260915-unified-status-surface) debe correr sin ImportError desde
        # el destino instalado -- ni tools/harmessi/ ni tools/ds_init/ viajan
        # con la instalación, así que status.py debe degradar con gracia
        # (harness.disponible=False esperado, ver R11/R15 de spec.md).
        resultado_status = subprocess.run(
            [sys.executable, "tools/ds_guard.py", "status", "--json"],
            cwd=str(self.repo),
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(
            resultado_status.returncode,
            0,
            f"ds_guard status (sin --change-id) falló desde el destino instalado: "
            f"stdout={resultado_status.stdout!r} stderr={resultado_status.stderr!r}",
        )
        self.assertNotIn("ImportError", resultado_status.stderr)
        self.assertNotIn("Traceback", resultado_status.stderr)
        payload_status = json.loads(resultado_status.stdout)
        self.assertIn("harness", payload_status)
        self.assertFalse(
            payload_status["harness"]["disponible"],
            "harness.disponible debería ser False desde un destino instalado sin tools/harmessi/.",
        )
        self.assertIn("installation", payload_status)

        # `git status --porcelain`: los archivos nuevos aparecen como
        # untracked (`??`), sin nada roto ni corrupto reportado por Git.
        status = _git_status_porcelain(self.repo)
        for relativo in archivos_clave:
            self.assertIn(relativo.split("/")[0], status)

        for entrada in status.splitlines():
            estado = entrada[:2]
            self.assertIn(
                estado,
                ("??", " M", "M ", "MM"),
                f"Estado de git inesperado para: {entrada!r}",
            )

        # Ninguna cadena prohibida en ningún archivo instalado.
        for archivo in self.repo.rglob("*"):
            if not archivo.is_file():
                continue
            relativo = archivo.relative_to(self.repo)
            if ".git" in relativo.parts:
                continue
            try:
                contenido = archivo.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                contenido_bytes = archivo.read_bytes()
                for cadena in CADENAS_PROHIBIDAS:
                    self.assertNotIn(
                        cadena.encode("utf-8"),
                        contenido_bytes,
                        f"Cadena prohibida {cadena!r} encontrada en {relativo} (binario)",
                    )
                continue
            for cadena in CADENAS_PROHIBIDAS:
                self.assertNotIn(
                    cadena,
                    contenido,
                    f"Cadena prohibida {cadena!r} encontrada en {relativo}",
                )


if __name__ == "__main__":
    unittest.main()

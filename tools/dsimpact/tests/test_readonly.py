"""Tests read-only (R11): `ejecutar_scan`/CLI nunca escriben nada -- working
tree, `.harmessi/project.json`, `openspec/lifecycle/state.json`,
`.harmessi/scientific-policy.json`, ni ningún archivo temporal. Mismo patrón
que Change 0 (`dsguard.core.capturar_bytes` antes/después + `git status`
idéntico)."""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ORIGEN = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ORIGEN / "tools"))

from dsguard import core, repo as repo_mod  # noqa: E402
from dsimpact import scan as scan_mod  # noqa: E402

DS_GUARD = REPO_ORIGEN / "tools" / "ds_guard.py"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=str(repo), check=True, capture_output=True, text=True)


def _crear_repo() -> Path:
    repo = Path(tempfile.mkdtemp(prefix="dsimpact_readonly_test_"))
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "m.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    (repo / "c.py").write_text("from m import f\nf()\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "inicial")
    (repo / "m.py").write_text("def f():\n    return 2\n", encoding="utf-8")
    return repo


_RUTAS_ESTADO = (
    ".harmessi/project.json",
    "openspec/lifecycle/state.json",
    ".harmessi/scientific-policy.json",
    ".ds_init/control.json",
)


def _snapshot(repo: Path) -> dict:
    return {r: core.capturar_bytes(repo / r) for r in _RUTAS_ESTADO}


class TestEjecutarScanReadOnly(unittest.TestCase):
    def test_no_modifica_nada_since(self):
        repo = _crear_repo()
        antes_estado = _snapshot(repo)
        antes_sucios = sorted(repo_mod.list_dirty_files(repo))
        scan_mod.ejecutar_scan(repo, "HEAD", False)
        despues_estado = _snapshot(repo)
        despues_sucios = sorted(repo_mod.list_dirty_files(repo))
        self.assertEqual(antes_estado, despues_estado)
        self.assertEqual(antes_sucios, despues_sucios)

    def test_no_modifica_nada_staged(self):
        repo = _crear_repo()
        antes_sucios = sorted(repo_mod.list_dirty_files(repo))
        scan_mod.ejecutar_scan(repo, None, True)
        despues_sucios = sorted(repo_mod.list_dirty_files(repo))
        self.assertEqual(antes_sucios, despues_sucios)

    def test_no_escribe_ningun_archivo_nuevo(self):
        repo = _crear_repo()
        antes = sorted(p.relative_to(repo).as_posix() for p in repo.rglob("*") if p.is_file())
        scan_mod.ejecutar_scan(repo, "HEAD", False)
        despues = sorted(p.relative_to(repo).as_posix() for p in repo.rglob("*") if p.is_file())
        self.assertEqual(antes, despues)


class TestCodigoFuenteSinEscritura(unittest.TestCase):
    """Verificación estática: ningún módulo de `tools/dsimpact/` (salvo
    tests) contiene una llamada de escritura a disco."""

    def test_sin_llamadas_de_escritura(self):
        prohibidos = (
            '"w")', "'w')", '"wb")', "'wb')", "write_text(", "write_bytes(",
            "os.replace(", "escribir_texto_atomico(", "escribir_control(", "shutil.move(",
        )
        dir_dsimpact = REPO_ORIGEN / "tools" / "dsimpact"
        for ruta in dir_dsimpact.glob("*.py"):
            codigo = ruta.read_text(encoding="utf-8")
            for prohibido in prohibidos:
                self.assertNotIn(
                    prohibido, codigo, msg=f"{ruta.name} contiene una posible escritura: {prohibido!r}"
                )


if __name__ == "__main__":
    unittest.main()

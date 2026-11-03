"""Tests de `tools.dsimpact.cli` y de la delegación `ds_guard.py impact scan
-> tools.dsimpact` (R9). Integración vía subprocess real (mismo patrón que
`tools/tests/test_scientific_validity.py`)."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ORIGEN = Path(__file__).resolve().parents[3]
DS_GUARD = REPO_ORIGEN / "tools" / "ds_guard.py"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=str(repo), check=True, capture_output=True, text=True)


def _crear_repo() -> Path:
    repo = Path(tempfile.mkdtemp(prefix="dsimpact_cli_test_"))
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "m.py").write_text("def build_features():\n    return 1\n", encoding="utf-8")
    (repo / "c.py").write_text("from m import build_features\nbuild_features()\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "inicial")
    (repo / "m.py").write_text("def build_features():\n    return 2\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "cambio")
    return repo


def _correr(args: list, cwd: Path, entorno_extra: dict = None) -> subprocess.CompletedProcess:
    import os
    env = dict(os.environ)
    # REPO_ORIGEN: para "python -m tools.dsimpact" (namespace package "tools").
    # REPO_ORIGEN/tools: para "from dsguard import ..." dentro de dsimpact/*
    # (mismo patrón de import unidireccional que el resto de tools/*).
    env["PYTHONPATH"] = (
        str(REPO_ORIGEN) + os.pathsep + str(REPO_ORIGEN / "tools") + os.pathsep + env.get("PYTHONPATH", "")
    )
    if entorno_extra:
        env.update(entorno_extra)
    return subprocess.run(
        [sys.executable, *args], cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", env=env,
    )


class TestDsImpactDirecto(unittest.TestCase):
    def test_scan_since_json(self):
        repo = _crear_repo()
        r = _correr(["-m", "tools.dsimpact", "scan", "--since", "HEAD~1", "--json"], repo)
        self.assertEqual(r.returncode, 0, msg=r.stderr)
        datos = json.loads(r.stdout)
        self.assertEqual(datos["changed"][0]["path"], "m.py")
        self.assertTrue(datos["findings"])

    def test_scan_since_texto_no_dice_broken(self):
        repo = _crear_repo()
        r = _correr(["-m", "tools.dsimpact", "scan", "--since", "HEAD~1"], repo)
        self.assertEqual(r.returncode, 0, msg=r.stderr)
        self.assertNotIn("broken", r.stdout.lower())
        self.assertIn("potentially affected", r.stdout.lower())

    def test_summary_cuenta_consumidores_unicos_no_findings(self):
        # c.py importa Y llama a build_features (IMPORT_REFERENCE +
        # SYMBOL_REFERENCE) -- 2 findings, pero 1 solo consumidor. El
        # renglón "Summary: N potentially affected consumers" debe usar N=1
        # (summary.consumers), nunca N=2 (summary.findings).
        repo = _crear_repo()
        r = _correr(["-m", "tools.dsimpact", "scan", "--since", "HEAD~1", "--json"], repo)
        datos = json.loads(r.stdout)
        self.assertGreaterEqual(datos["summary"]["findings"], 2)
        self.assertEqual(datos["summary"]["consumers"], 1)

        r_texto = _correr(["-m", "tools.dsimpact", "scan", "--since", "HEAD~1"], repo)
        self.assertEqual(r_texto.returncode, 0, msg=r_texto.stderr)
        self.assertIn("Summary: 1 potentially affected consumers", r_texto.stdout)

    def test_ref_invalida_exit_1(self):
        repo = _crear_repo()
        r = _correr(["-m", "tools.dsimpact", "scan", "--since", "ref-invalida-xyz", "--json"], repo)
        self.assertEqual(r.returncode, 1)
        self.assertNotIn("Traceback", r.stderr)

    def test_since_y_staged_mutuamente_excluyentes(self):
        repo = _crear_repo()
        r = _correr(["-m", "tools.dsimpact", "scan", "--since", "HEAD~1", "--staged"], repo)
        self.assertNotEqual(r.returncode, 0)


class TestDsGuardDelega(unittest.TestCase):
    def test_mismo_resultado_que_dsimpact_directo(self):
        repo = _crear_repo()
        r_directo = _correr(["-m", "tools.dsimpact", "scan", "--since", "HEAD~1", "--json"], repo)
        r_wrapper = _correr([str(DS_GUARD), "impact", "scan", "--since", "HEAD~1", "--json"], repo)
        self.assertEqual(r_directo.returncode, 0, msg=r_directo.stderr)
        self.assertEqual(r_wrapper.returncode, 0, msg=r_wrapper.stderr)
        self.assertEqual(json.loads(r_directo.stdout), json.loads(r_wrapper.stdout))

    def test_subparser_existe_siempre(self):
        repo = _crear_repo()
        r = _correr([str(DS_GUARD), "impact", "--help"], repo)
        self.assertEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()

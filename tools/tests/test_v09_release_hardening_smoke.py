"""Smoke de release de v0.9 (Change 5, `20261007-v09-release-hardening`): invariantes
de release sin duplicar la cobertura funcional de Changes 0-4 ni de los Correctives.

Deterministas, sin red, solo lectura. Los chequeos de git se omiten si no hay repo.
"""
from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# Changes que DESCRIBEN el sweep de privacidad (citan los patrones a buscar): se excluyen del sweep.
_EXCLUIDOS_SWEEP = re.compile(r"^openspec/changes/[^/]*(release-hardening|remove-personal-email)[^/]*/")
_ESTE_ARCHIVO = "tools/tests/test_v09_release_hardening_smoke.py"


def _git(*args: str):
    try:
        out = subprocess.run(
            ["git", *args], cwd=REPO, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout if out.returncode == 0 else None


def _tracked() -> list:
    # Versionados + nuevos no ignorados (lo que entraría al próximo commit); `-z` evita el quoting de nombres no ASCII.
    salida = _git("ls-files", "-z", "--cached", "--others", "--exclude-standard")
    return [] if salida is None else [l for l in salida.split(chr(0)) if l]


class TestVersion(unittest.TestCase):
    def test_version_canonica_coherente(self):
        from tools.ds_init.version import HARNESS_VERSION

        self.assertRegex(HARNESS_VERSION, r"^\d+\.\d+\.\d+$")
        cff = (REPO / "CITATION.cff").read_text(encoding="utf-8")
        self.assertIn(f"version: {HARNESS_VERSION}", cff)
        control = json.loads((REPO / ".ds_init" / "control.json").read_text(encoding="utf-8"))
        self.assertEqual(control.get("harness_version"), HARNESS_VERSION)

    def test_version_es_09(self):
        from tools.ds_init.version import HARNESS_VERSION

        self.assertEqual(HARNESS_VERSION, "0.9.0")

    def test_versionados_internos_independientes(self):
        from tools.ds_profile import report, sampling

        self.assertEqual(report.TOOL_VERSION, "0.1.0")
        self.assertEqual(sampling.VERSION_ALGORITMO, "bounded_v1")


class TestHigieneGit(unittest.TestCase):
    def setUp(self):
        if _git("rev-parse", "--git-dir") is None:
            self.skipTest("sin repositorio git")

    def test_feedback_y_evidencia_local_no_versionados(self):
        tracked = _tracked()
        self.assertEqual([t for t in tracked if t.startswith("docs/feedback/")], [])
        self.assertEqual([t for t in tracked if t.startswith(".harmessi/")], [])

    def test_gitignore_cubre_feedback_y_evidencia_local(self):
        gi = (REPO / ".gitignore").read_text(encoding="utf-8").splitlines()
        self.assertIn("docs/feedback/", gi)
        self.assertIn(".harmessi/", gi)

    def test_sin_artefactos_temporales_versionados(self):
        malos = [t for t in _tracked() if re.search(r"(__pycache__/|\.pyc$|\.tmp$|scratchpad|\.pytest_cache)", t)]
        self.assertEqual(malos, [])


class TestPrivacidad(unittest.TestCase):
    # Patrones armados por concatenación para no autoreferenciarse.
    PATRONES = [
        "segmen" + "tacion-pc",
        "fijaciones" + "_granos",
        "planes" + "_comerciales",
        "/Users/" + "fcolombo",
        "\\Users\\" + "fcolombo",
        "fcolombo" + "@",
        "federcolombo" + "@",
        "UN" + "CO-Intelligence",
    ]

    def setUp(self):
        if _git("rev-parse", "--git-dir") is None:
            self.skipTest("sin repositorio git")

    def test_sin_restos_privados_en_archivos_versionados(self):
        hallazgos = []
        for rel in _tracked():
            if rel == _ESTE_ARCHIVO or _EXCLUIDOS_SWEEP.match(rel) or rel == ".ds_init/control.json":
                continue
            ruta = REPO / rel
            if not ruta.is_file():
                continue
            try:
                texto = ruta.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            bajo = texto.lower()
            for patron in self.PATRONES:
                if patron.lower() in bajo:
                    hallazgos.append((rel, patron))
        self.assertEqual(hallazgos, [])


class TestDependencias(unittest.TestCase):
    MODULOS = [
        "tools/cards",
        "tools/dsguard/pep440_subset.py",
        "tools/dsguard/guardrails_drift.py",
        "tools/ds_profile",
    ]
    # Terceros permitidos: solo pyarrow, importado de forma perezosa dentro de una función/clase.
    TERCEROS_PERMITIDOS = {"pyarrow"}

    def _archivos(self):
        for m in self.MODULOS:
            p = REPO / m
            if p.is_file():
                yield p
            else:
                for f in p.rglob("*.py"):
                    if "tests" not in f.parts:
                        yield f

    def test_solo_stdlib_o_pyarrow_perezoso(self):
        stdlib = set(sys.stdlib_module_names)
        # Nombres locales del repo (módulos/paquetes bajo tools/): import dual de portabilidad.
        locales = {q.stem for q in (REPO / "tools").rglob("*.py")} | {q.name for q in (REPO / "tools").rglob("*") if q.is_dir()}
        malos = []
        for f in self._archivos():
            arbol = ast.parse(f.read_text(encoding="utf-8"))
            nivel_modulo = set(id(n) for n in arbol.body)
            for nodo in ast.walk(arbol):
                if isinstance(nodo, ast.Import):
                    nombres = [a.name.split(".")[0] for a in nodo.names]
                elif isinstance(nodo, ast.ImportFrom) and nodo.level == 0 and nodo.module:
                    nombres = [nodo.module.split(".")[0]]
                else:
                    continue
                for n in nombres:
                    if n in stdlib or n in locales or n == "__future__":
                        continue
                    if n in self.TERCEROS_PERMITIDOS and id(nodo) not in nivel_modulo:
                        continue
                    malos.append((str(f.relative_to(REPO)), n))
        self.assertEqual(malos, [])


class TestRoadmap(unittest.TestCase):
    def test_v09_refleja_changes_0_a_5_y_correctives(self):
        txt = (REPO / "docs/roadmap/v0.9.md").read_text(encoding="utf-8")
        for ident in (
            "20261002-card-and-evidence-foundation",
            "20261002-data-cards",
            "20261005-model-cards",
            "20261005-model-risk-responsible-ai",
            "20261005-cards-governance-integration",
            "20261005-operational-autonomy-hardening",
            "20261006-sdd-parsers-and-guardrail-ownership",
            "20261007-ds-profile-bounded-memory",
            "20261007-v09-release-hardening",
        ):
            self.assertIn(ident, txt)

    def test_v010_preserva_deuda_viva(self):
        txt = (REPO / "docs/roadmap/v0.10.md").read_text(encoding="utf-8").lower()
        for clave in (
            "approval origin",
            "line endings",
            "mid-change authorized scope amendment",
            "composable engineering",
            "domain-modeling",
            "one-writer",
        ):
            self.assertIn(clave, txt)

    def test_release_notes_honestas(self):
        txt = (REPO / "docs/releases/v0.9.0.md").read_text(encoding="utf-8")
        self.assertIn("Cards & Model Governance", txt)
        self.assertIn("no", txt.lower())
        self.assertRegex(txt, r"(?i)no\*\* afirma|does \*\*not\*\* claim|no afirma")
        bajo = txt.lower()
        for prometido in ("certified", "certificado", "guarantees compliance", "garantiza cumplimiento"):
            self.assertNotIn(prometido, bajo)


class TestInerciaAutonomia(unittest.TestCase):
    def test_cards_y_governance_no_importan_autonomy(self):
        malos = []
        for f in (REPO / "tools/cards").rglob("*.py"):
            if "tests" in f.parts:
                continue
            for nodo in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
                mod = None
                if isinstance(nodo, ast.ImportFrom) and nodo.module:
                    mod = nodo.module
                elif isinstance(nodo, ast.Import):
                    mod = nodo.names[0].name
                if mod and ("autonomy" in mod.split(".") or "leadrun" in mod.split(".")):
                    malos.append((f.name, mod))
        self.assertEqual(malos, [])


if __name__ == "__main__":
    unittest.main()

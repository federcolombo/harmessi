"""Smoke de release de v0.10 (Change 6, `20261015-v010-release-hardening`): invariantes
de release sin duplicar la cobertura funcional de los Changes 0-5 ni del Corrective.

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
_ESTE_ARCHIVO = "tools/tests/test_v010_release_hardening_smoke.py"

_CHANGE_RELEASE = "20261015-v010-release-hardening"
_CHANGES_CERRADOS = (
    "20261008-v010-roadmap-and-architecture-audit",
    "20261008-cross-platform-managed-hashing",
    "20261009-unicode-git-paths-corrective",
    "20261009-approval-trust-human-presence",
    "20261013-governed-amendments",
    "20261014-composable-skills-writer-semantics",
    "20261014-domain-modeling",
)


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


def _estado_tasks(change_id: str):
    """Devuelve el valor de `estado:` del tasks.md del Change (en changes/ o archive/), o None si no existe."""
    for base in ("openspec/changes", "openspec/archive"):
        ruta = REPO / base / change_id / "tasks.md"
        if ruta.is_file():
            m = re.search(r"^estado:\s*(\S+)", ruta.read_text(encoding="utf-8"), re.MULTILINE)
            return m.group(1) if m else ""
    return None


def _semver(v: str) -> tuple:
    """Parsea `X.Y.Z` (ignora sufijos prerelease) a una tupla comparable."""
    m = re.match(r"^(\d+)\.(\d+)\.(\d+)", v)
    return tuple(int(x) for x in m.groups()) if m else (-1, -1, -1)


class TestVersion010(unittest.TestCase):
    # Desde v0.11 la versión vigente avanza: estos chequeos exigen «>= 0.10.0» y coherencia con HARNESS_VERSION.
    def test_version_es_010(self):
        from tools.ds_init.version import HARNESS_VERSION

        self.assertGreaterEqual(_semver(HARNESS_VERSION), (0, 10, 0))

    def test_citation_coherente(self):
        from tools.ds_init.version import HARNESS_VERSION

        cff = (REPO / "CITATION.cff").read_text(encoding="utf-8")
        self.assertIn(f"version: {HARNESS_VERSION}", cff)

    def test_control_json_coherente(self):
        from tools.ds_init.version import HARNESS_VERSION

        control = json.loads((REPO / ".ds_init" / "control.json").read_text(encoding="utf-8"))
        self.assertEqual(control.get("harness_version"), HARNESS_VERSION)
        archivos = control.get("archivos", [])
        self.assertTrue(archivos, "control.json sin entradas en `archivos`")
        validos = {"sha256/eol-lf/v1", "sha256/bin/v1"}
        sin_alg = [a.get("ruta") for a in archivos if a.get("hash_alg") not in validos]
        self.assertEqual(sin_alg, [], "entradas sin hash_alg válido")
        rutas = [a.get("ruta") for a in archivos]
        self.assertEqual(len(rutas), len(set(rutas)), "rutas duplicadas en control.json")

    def test_sin_archivos_version_paralelos(self):
        self.assertFalse((REPO / "VERSION").exists(), "no debe existir VERSION en la raíz")
        self.assertFalse((REPO / "pyproject.toml").exists(), "no debe existir pyproject.toml en la raíz")

    def test_versionados_internos_independientes(self):
        from tools.ds_profile import report, sampling

        self.assertEqual(report.TOOL_VERSION, "0.1.0")
        self.assertEqual(sampling.VERSION_ALGORITMO, "bounded_v1")


class TestNotasRelease010(unittest.TestCase):
    RUTA = REPO / "docs" / "releases" / "v0.10.0.md"

    def _txt(self) -> str:
        self.assertTrue(self.RUTA.is_file(), f"falta {self.RUTA}")
        return self.RUTA.read_text(encoding="utf-8")

    def test_frase_console_confirmed_literal(self):
        frase = "`console_confirmed` is an interactive-presence signal, not proof of identity or authorship."
        self.assertIn(frase, self._txt())

    def test_menciona_contenido_clave(self):
        txt = self._txt()
        for clave in ("migrate-hashes", "GLOSSARY.md", "domain-modeling", "ownership", "Known limitations"):
            self.assertIn(clave, txt, f"las notas de v0.10.0 deben mencionar «{clave}»")

    def test_sin_sobrepromesa(self):
        bajo = self._txt().lower()
        for prohibida in ("tamper-proof", "unbreakable"):
            self.assertNotIn(prohibida, bajo, f"las notas no deben afirmar «{prohibida}»")
        for prohibida in ("verifiable t1 approval", "proves identity"):
            self.assertNotIn(prohibida, bajo, f"las notas no deben contener «{prohibida}»")

    def test_declara_limite_criptografico(self):
        self.assertIn("not cryptographically enforced", self._txt())


class TestChangesCerrados010(unittest.TestCase):
    """Changes 0–5 y Corrective cerrados; Change 6 en implementación/verificación/cerrado."""

    def test_changes_0_a_5_y_corrective_cerrados(self):
        malos = {}
        for cid in _CHANGES_CERRADOS:
            estado = _estado_tasks(cid)
            if estado != "cerrada":
                malos[cid] = estado
        self.assertEqual(malos, {}, "Changes que deberían estar en estado: cerrada (valor encontrado; None = sin tasks.md)")

    def test_change_6_en_implementacion_verificacion_o_cerrado(self):
        estado = _estado_tasks(_CHANGE_RELEASE)
        self.assertIn(estado, {"en_implementacion", "en_verificacion", "cerrada"})


class TestRoadmap010(unittest.TestCase):
    def test_v010_publicada(self):
        txt = (REPO / "docs/roadmap/v0.10.md").read_text(encoding="utf-8")
        self.assertIn("PUBLICADA", txt)
        self.assertIn("0.10.0", txt)
        self.assertIn("GitHub Release", txt)
        self.assertTrue((REPO / "docs/releases/v0.10.0.md").is_file(), "falta docs/releases/v0.10.0.md")

    def test_v010_menciona_los_changes(self):
        txt = (REPO / "docs/roadmap/v0.10.md").read_text(encoding="utf-8")
        for n in range(0, 7):
            self.assertRegex(txt, rf"### Change {n} ", f"falta el título de Change {n} en v0.10.md")
        self.assertIn("Domain Modeling", txt)
        self.assertIn("v0.10 Release Hardening", txt)

    def test_readme_roadmap_menciona_release(self):
        txt = (REPO / "docs/roadmap/README.md").read_text(encoding="utf-8")
        self.assertIn("v0.10.0", txt)


class TestHigieneGit010(unittest.TestCase):
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

    def test_glossary_no_versionado_en_la_raiz(self):
        # GLOSSARY.md es del proyecto usuario, no del repo del harness.
        self.assertNotIn("GLOSSARY.md", _tracked())


class TestPrivacidad010(unittest.TestCase):
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


class TestDependencias010(unittest.TestCase):
    MODULOS = [
        "tools/dsguard/skill_contract.py",
        "tools/dsguard/ownership.py",
        "tools/dsguard/glossary.py",
    ]

    def test_solo_stdlib_o_hermanos(self):
        stdlib = set(sys.stdlib_module_names)
        locales = {q.stem for q in (REPO / "tools").rglob("*.py")} | {q.name for q in (REPO / "tools").rglob("*") if q.is_dir()}
        malos = []
        for m in self.MODULOS:
            ruta = REPO / m
            self.assertTrue(ruta.is_file(), f"falta {m}")
            for nodo in ast.walk(ast.parse(ruta.read_text(encoding="utf-8"))):
                if isinstance(nodo, ast.Import):
                    nombres = [a.name.split(".")[0] for a in nodo.names]
                elif isinstance(nodo, ast.ImportFrom) and nodo.level == 0 and nodo.module:
                    nombres = [nodo.module.split(".")[0]]
                else:
                    continue  # imports relativos (hermanos) y no-imports
                for n in nombres:
                    if n not in stdlib and n not in locales and n != "__future__":
                        malos.append((m, n))
        self.assertEqual(malos, [])


class TestManagedHashing010(unittest.TestCase):
    def test_migrate_hashes_dry_run_sin_pendientes(self):
        try:
            res = subprocess.run(
                [sys.executable, "-m", "tools.ds_init", "--destino", str(REPO), "migrate-hashes"],
                cwd=REPO, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300,
            )
        except subprocess.TimeoutExpired:
            self.fail("migrate-hashes (dry-run) excedió el timeout")
        self.assertEqual(res.returncode, 0, f"returncode {res.returncode}; stderr:\n{res.stderr}")
        salida = (res.stdout or "") + (res.stderr or "")
        self.assertIn("Migrables: 0", salida, f"salida:\n{salida}")
        self.assertIn("No verificables (drift persiste, no se tocan): 0", salida, f"salida:\n{salida}")


if __name__ == "__main__":
    unittest.main()

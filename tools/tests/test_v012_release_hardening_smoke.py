"""Smoke de release de v0.12 (Change 6, `20261021-v012-release-hardening`): invariantes
de release sin duplicar la cobertura funcional de los Changes 0-5.

Deterministas, sin red, solo lectura. Los chequeos de git se omiten si no hay repo.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# Changes que DESCRIBEN el sweep de privacidad (citan los patrones a buscar): se excluyen del sweep.
_EXCLUIDOS_SWEEP = re.compile(r"^openspec/changes/[^/]*(release-hardening|remove-personal-email)[^/]*/")
_ESTE_ARCHIVO = "tools/tests/test_v012_release_hardening_smoke.py"
_SMOKE_V010 = "tools/tests/test_v010_release_hardening_smoke.py"

_VERSION = "0.12.0"
_CHANGE_RELEASE = "20261021-v012-release-hardening"
_CHANGES_CERRADOS = (
    "20261021-v012-roadmap-and-dx-skills-audit",
    "20261021-v012-harness-surfaces",
    "20261021-v012-problem-framing",
    "20261021-v012-diagnosing-bugs",
    "20261021-v012-codebase-design",
    "20261021-v012-skill-selection-composition",
)
_SKILLS_V012 = ("problem-framing", "diagnosing-bugs", "codebase-design", "domain-modeling")


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
    m = re.match(r"^(\d+)\.(\d+)\.(\d+)", v)
    return tuple(int(x) for x in m.groups()) if m else (-1, -1, -1)


class TestVersion012(unittest.TestCase):
    # Versión vigente >= 0.12.0 (un release posterior no debe romper este smoke) y coherente entre marcadores.
    def test_version_es_012(self):
        from tools.ds_init.version import HARNESS_VERSION

        self.assertGreaterEqual(_semver(HARNESS_VERSION), _semver(_VERSION))

    def test_citation_coherente(self):
        from tools.ds_init.version import HARNESS_VERSION

        cff = (REPO / "CITATION.cff").read_text(encoding="utf-8")
        self.assertIn(f"version: {HARNESS_VERSION}", cff)

    def test_readme_menciona_release(self):
        readme = (REPO / "README.md").read_text(encoding="utf-8")
        self.assertIn("v0.12", readme)
        self.assertIn("docs/releases/v0.12.0.md", readme)

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


class TestNotasRelease012(unittest.TestCase):
    RUTA = REPO / "docs" / "releases" / "v0.12.0.md"

    def _txt(self) -> str:
        self.assertTrue(self.RUTA.is_file(), f"falta {self.RUTA}")
        return self.RUTA.read_text(encoding="utf-8")

    def test_menciona_contenido_clave(self):
        txt = self._txt()
        for clave in (
            "Data Scientist Experience & Composable Skills",
            "Harness Surfaces",
            "Protected",
            "Optimizable",
            "Project-owned",
            "SKILL-ARTIFACT-SUPERFICIE-PROTEGIDA",
            "problem-framing",
            "grill-me",
            "opt-in",
            "diagnosing-bugs",
            "codebase-design",
            "reuse an existing primitive > extend it",
            "composition",
            "Traceability",
            "Skills cargados",
            "materially",
            "sdd.md",
            "Compatibility",
            "maxTurns",
            "v0.11.0",
            "Known limitations",
            "UNCONFIRMED",
            "Upgrading",
        ):
            self.assertIn(clave, txt, f"las notas de v0.12.0 deben mencionar «{clave}»")

    def test_sin_afirmaciones_prohibidas(self):
        bajo = self._txt().lower()
        prohibidas = (
            "self-improving",
            "self-improvement",
            "optimizer",
            "candidate/probe",
            "marketplace",
            "cryptographic proof",
            "tamper-proof",
            "guarantees authenticity",
        )
        for prohibida in prohibidas:
            for m in re.finditer(re.escape(prohibida), bajo):
                # Se tolera solo si la negación está en la MISMA oración (desde el último límite de oración).
                inicio = max(bajo.rfind(sep, 0, m.start()) for sep in (". ", "! ", "? ", "\n"))
                previo = bajo[inicio + 1 : m.start()]
                self.assertRegex(previo, r"\b(not|no|never|without|nor)\b", f"afirmación sin negar: «{prohibida}»")

    def test_declara_limites(self):
        txt = self._txt()
        m = re.search(r"^## Known limitations\n(.*?)(?=^## |\Z)", txt, re.MULTILINE | re.DOTALL)
        self.assertIsNotNone(m, "falta la sección «Known limitations»")
        seccion = m.group(1)
        for clave in ("guidance", "cooperative", "Windows", "UNCONFIRMED"):
            self.assertIn(clave, seccion, f"«{clave}» debe figurar en Known limitations")


class TestChangesCerrados012(unittest.TestCase):
    """Changes 0–5 cerrados; Change 6 (el propio release) en implementación/verificación/cerrado."""

    def test_changes_0_a_5_cerrados(self):
        malos = {}
        for cid in _CHANGES_CERRADOS:
            estado = _estado_tasks(cid)
            if estado != "cerrada":
                malos[cid] = estado
        self.assertEqual(malos, {}, "Changes que deberían estar en estado: cerrada (valor encontrado; None = sin tasks.md)")

    def test_change_6_en_implementacion_verificacion_o_cerrado(self):
        estado = _estado_tasks(_CHANGE_RELEASE)
        self.assertIn(estado, {"en_implementacion", "en_verificacion", "cerrada"})


class TestSkillsV012(unittest.TestCase):
    def test_skills_validas_por_contrato(self):
        from tools.dsguard.skill_contract import DIR_SKILLS, validar_directorio_skills

        for nombre in _SKILLS_V012:
            self.assertTrue((REPO / DIR_SKILLS / f"{nombre}.md").is_file(), f"falta la skill {nombre}")
        self.assertEqual(validar_directorio_skills(REPO), [])

    def test_skills_instaladas_por_manifest(self):
        from tools.ds_init.manifest import MANIFEST

        destinos = {e.destino for e in MANIFEST}
        for nombre in _SKILLS_V012:
            self.assertIn(f".claude/skills/lead-data-scientist/skills/{nombre}.md", destinos)


class TestRolesSinCambio012(unittest.TestCase):
    AGENTES = REPO / ".claude" / "agents"

    def _frontmatter(self, nombre: str) -> str:
        txt = (self.AGENTES / f"{nombre}.md").read_text(encoding="utf-8").replace("\r\n", "\n")
        return txt.split("---")[1]

    def test_max_turns_por_agente(self):
        esperado = {"python-data-engineer": 12, "data-science-reviewer": 16, "metodologo": 8, "notebook-runner": 4}
        for nombre, turnos in esperado.items():
            with self.subTest(agente=nombre):
                self.assertRegex(self._frontmatter(nombre), rf"(?m)^maxTurns: {turnos}\s*$")

    def test_tools_por_agente(self):
        esperado = {
            "python-data-engineer": "Read, Edit, Write, NotebookEdit, Grep, Glob",
            "data-science-reviewer": "Read, Grep, Glob",
            "metodologo": "Read, Grep, Glob",
            "notebook-runner": "Bash",
        }
        for nombre, herramientas in esperado.items():
            with self.subTest(agente=nombre):
                self.assertRegex(self._frontmatter(nombre), rf"(?m)^tools: {herramientas}\s*$")


class TestSuperficiesProtegidasSinCambio012(unittest.TestCase):
    def test_diff_vs_tag_v011_vacio(self):
        if _git("rev-parse", "--git-dir") is None:
            self.skipTest("sin repositorio git")
        if _git("rev-parse", "--verify", "--quiet", "refs/tags/v0.11.0") is None:
            self.skipTest("tag v0.11.0 inexistente")
        salida = _git("diff", "v0.11.0", "--stat", "--", ".claude/agents", ".claude/settings.json", ".claude/guardrails.json")
        self.assertIsNotNone(salida, "git diff falló")
        self.assertEqual(salida.strip(), "", f"roles/permisos/hooks cambiaron respecto de v0.11.0:\n{salida}")


class TestRoadmap012(unittest.TestCase):
    def test_roadmap_menciona_release(self):
        txt = (REPO / "docs/roadmap/v0.12.md").read_text(encoding="utf-8")
        self.assertIn("v0.12.0", txt)
        self.assertIn("docs/releases/v0.12.0.md", txt)
        self.assertIn("UNCONFIRMED", txt)
        self.assertTrue((REPO / "docs/releases/v0.12.0.md").is_file(), "falta docs/releases/v0.12.0.md")

    def test_roadmap_menciona_los_changes(self):
        txt = (REPO / "docs/roadmap/v0.12.md").read_text(encoding="utf-8")
        for n in range(0, 7):
            self.assertRegex(txt, rf"### Change {n} ", f"falta el título de Change {n} en v0.12.md")

    def test_roadmap_registra_direccion_futura(self):
        txt = (REPO / "docs/roadmap/v0.12.md").read_text(encoding="utf-8")
        self.assertIn("v0.13", txt)
        self.assertIn("v0.14", txt)

    def test_readme_roadmap_menciona_release(self):
        txt = (REPO / "docs/roadmap/README.md").read_text(encoding="utf-8")
        self.assertIn("v0.12.0", txt)


class TestHigieneGit012(unittest.TestCase):
    def setUp(self):
        if _git("rev-parse", "--git-dir") is None:
            self.skipTest("sin repositorio git")

    def test_feedback_y_evidencia_local_no_versionados(self):
        tracked = _tracked()
        self.assertEqual([t for t in tracked if t.startswith("docs/feedback/")], [])
        self.assertEqual([t for t in tracked if t.startswith(".harmessi/")], [])

    def test_sin_artefactos_temporales_versionados(self):
        malos = [t for t in _tracked() if re.search(r"(__pycache__/|\.pyc$|\.tmp$|scratchpad|\.pytest_cache)", t)]
        self.assertEqual(malos, [])


class TestPrivacidad012(unittest.TestCase):
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

    # Regex genéricas conservadoras (validadas contra el contenido no-test versionado: sin falsos positivos).
    RE_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+\.[A-Za-z]{2,})")
    DOMINIOS_PERMITIDOS = {"example.com", "example.org", "ejemplo.com", "empresa.com"}
    RE_RUTA_PERSONAL = re.compile(r"[A-Za-z]:\\Users\\[^<\\\s]+|/Users/[A-Za-z0-9._-]+")
    RE_TOKEN = re.compile(r"ghp_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}")

    def setUp(self):
        if _git("rev-parse", "--git-dir") is None:
            self.skipTest("sin repositorio git")

    def test_sin_restos_privados_en_archivos_versionados(self):
        hallazgos = []
        propios = (_ESTE_ARCHIVO, _SMOKE_V010, "tools/tests/test_v011_release_hardening_smoke.py")
        for rel in _tracked():
            if rel in propios or _EXCLUIDOS_SWEEP.match(rel) or rel == ".ds_init/control.json":
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
            # Barrido genérico: solo fuera de tests (los fixtures sintéticos usan emails/rutas/tokens de juguete).
            if rel.startswith("tests/") or "/tests/" in rel or Path(rel).name.startswith("test_"):
                continue
            for m in self.RE_EMAIL.finditer(texto):
                if m.group(1).lower() not in self.DOMINIOS_PERMITIDOS:
                    hallazgos.append((rel, "email"))
            for etiqueta, regex in (("ruta personal", self.RE_RUTA_PERSONAL), ("token", self.RE_TOKEN)):
                if regex.search(texto):
                    hallazgos.append((rel, etiqueta))
        self.assertEqual(hallazgos, [])


class TestManagedHashing012(unittest.TestCase):
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

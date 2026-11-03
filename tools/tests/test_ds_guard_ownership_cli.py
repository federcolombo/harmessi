"""Tests de CLI del cableado v0.10 (Change 20261014-composable-skills-writer-semantics):
`ds_guard ownership check`, hallazgos de ownership/estado divergente/skills en `validate`
y `session start --max-continuaciones` / `session status`.

Mismo patrón que `test_ds_guard_budgets_cli.py`: corre `tools/ds_guard.py` real como
subproceso contra un repo git temporal sintético.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ORIGEN = Path(__file__).resolve().parents[2]
DS_GUARD = REPO_ORIGEN / "tools" / "ds_guard.py"
_TEMPLATES_ORIGEN = REPO_ORIGEN / ".claude" / "skills" / "lead-data-scientist" / "templates"
_CHANGE_ID = "20261014-test-ownership-cli"

_SECCION_VALIDA = (
    "\n## Ownership de writers\n\n"
    "### w1 — python-data-engineer — T1\n- src/a.py\n\n"
    "### w2 — python-data-engineer — T2\n- src/b.py\n"
)
_SECCION_SOLAPADA = (
    "\n## Ownership de writers\n\n"
    "### w1 — python-data-engineer — T1\n- src/**\n\n"
    "### w2 — python-data-engineer — T2\n- src/b.py\n"
)
_SECCION_FUERA_DE_SCOPE = (
    "\n## Ownership de writers\n\n"
    "### w1 — python-data-engineer — T1\n- otro/x.py\n"
)
_SECCION_SKILL_INEXISTENTE = (
    "\n## Skills cargados\n\n- skill-que-no-existe — T1 — prueba\n"
)


def _crear_repo_git_temporal() -> Path:
    repo = Path(tempfile.mkdtemp(prefix="cli_ownership_"))
    subprocess.run(["git", "init", "-q"], cwd=str(repo), check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(repo), check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(repo), check=True)
    (repo / "README.md").write_text("repo de prueba\n", encoding="utf-8")
    shutil.copytree(_TEMPLATES_ORIGEN, repo / ".claude" / "skills" / "lead-data-scientist" / "templates")
    subprocess.run(["git", "add", "."], cwd=str(repo), check=True)
    subprocess.run(["git", "commit", "-q", "-m", "inicial"], cwd=str(repo), check=True)
    return repo


def _correr(args: list, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(DS_GUARD), *args],
        cwd=str(cwd), capture_output=True, text=True, encoding="utf-8",
    )


class _Base(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_repo_git_temporal()
        r = _correr(["init", "--change-id", _CHANGE_ID, "--modo", "completo"], self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.dir_change = self.repo / "openspec" / "changes" / _CHANGE_ID

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def _fijar_alcance(self, rutas: list) -> None:
        # Camino soportado: sección `## Alcance autorizado` de proposal.md + approve,
        # que materializa el scope anclado (no se edita control.json a mano).
        proposal = self.dir_change / "proposal.md"
        bullets = "\n".join(f"- {r}" for r in rutas)
        proposal.write_text(f"# Propuesta\n\n## Alcance autorizado\n\n{bullets}\n", encoding="utf-8")
        r = _correr(
            ["approve", "--change-id", _CHANGE_ID, "--artefacto", "proposal.md",
             "--usuario", "Test User", "--fecha", "2026-10-14", "--alcance", "x", "--cita", "x"],
            self.repo,
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def _agregar_a_tasks(self, texto: str) -> None:
        """Reemplaza la sección existente (del encabezado al siguiente `## `) por `texto`;
        si no existe, la anexa. Evita encabezados duplicados."""
        ruta = self.dir_change / "tasks.md"
        actual = ruta.read_text(encoding="utf-8")
        encabezado = texto.strip().splitlines()[0]
        patron = re.compile(rf"^{re.escape(encabezado)}[ \t]*\n.*?(?=^## |\Z)", re.DOTALL | re.MULTILINE)
        nuevo = texto.strip("\n") + "\n\n"
        if patron.search(actual):
            actual = patron.sub(lambda _m: nuevo, actual, count=1)
        else:
            actual = actual.rstrip("\n") + "\n\n" + nuevo
        ruta.write_text(actual, encoding="utf-8")

    def _codigos(self, r: subprocess.CompletedProcess) -> list:
        return [f["codigo"] for f in json.loads(r.stdout)["findings"]]

    def _ownership_check(self, *extra) -> subprocess.CompletedProcess:
        return _correr(["ownership", "check", "--change-id", _CHANGE_ID, *extra], self.repo)

    def _validate_json(self) -> subprocess.CompletedProcess:
        return _correr(["validate", "--change-id", _CHANGE_ID, "--json"], self.repo)


class TestOwnershipCheck(_Base):
    def test_ownership_valido_exit_0(self):
        self._fijar_alcance(["src/a.py", "src/b.py"])
        self._agregar_a_tasks(_SECCION_VALIDA)
        r = self._ownership_check()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_ownership_solapado_exit_1(self):
        self._fijar_alcance(["src/**"])
        self._agregar_a_tasks(_SECCION_SOLAPADA)
        r = self._ownership_check("--json")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("OWNERSHIP-SOLAPADO", self._codigos(r))

    def test_ownership_solapado_en_texto(self):
        self._fijar_alcance(["src/**"])
        self._agregar_a_tasks(_SECCION_SOLAPADA)
        r = self._ownership_check()
        self.assertEqual(r.returncode, 1)
        self.assertIn("OWNERSHIP-SOLAPADO", r.stdout)

    def test_fuera_de_scope_exit_1(self):
        self._fijar_alcance(["src/**"])
        self._agregar_a_tasks(_SECCION_FUERA_DE_SCOPE)
        r = self._ownership_check("--json")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("OWNERSHIP-FUERA-DE-ALCANCE", self._codigos(r))

    def test_sin_seccion_exit_0(self):
        self._fijar_alcance(["src/**"])
        r = self._ownership_check()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_json_valido_sin_hallazgos(self):
        self._fijar_alcance(["src/**"])
        r = self._ownership_check("--json")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(json.loads(r.stdout)["findings"], [])

    def test_change_inexistente_exit_2(self):
        r = _correr(["ownership", "check", "--change-id", "no-existe"], self.repo)
        self.assertEqual(r.returncode, 2)


class TestValidateV010(_Base):
    def test_validate_con_ownership_solapado_falla(self):
        self._fijar_alcance(["src/**"])
        self._agregar_a_tasks(_SECCION_SOLAPADA)
        r = self._validate_json()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("OWNERSHIP-SOLAPADO", self._codigos(r))

    def test_validate_sin_secciones_no_agrega_hallazgos_v010(self):
        self._fijar_alcance(["src/**"])
        codigos = self._codigos(self._validate_json())
        for codigo in codigos:
            self.assertFalse(codigo.startswith("OWNERSHIP-"), codigo)
            self.assertFalse(codigo.startswith("SKILL-"), codigo)
            self.assertNotEqual(codigo, "SDD-ESTADO-DIVERGENTE")

    def test_validate_estado_adelantado_a_mano(self):
        ruta = self.dir_change / "tasks.md"
        texto = ruta.read_text(encoding="utf-8")
        self.assertIn("estado: propuesta_pendiente", texto)
        ruta.write_text(texto.replace("estado: propuesta_pendiente", "estado: en_implementacion", 1), encoding="utf-8")
        r = self._validate_json()
        self.assertIn("SDD-ESTADO-DIVERGENTE", self._codigos(r))

    def test_validate_skill_inexistente(self):
        self._agregar_a_tasks(_SECCION_SKILL_INEXISTENTE)
        r = self._validate_json()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("SKILL-REFERENCIA-DESCONOCIDA", self._codigos(r))


class TestSessionMaxContinuaciones(_Base):
    def _start(self, *extra) -> subprocess.CompletedProcess:
        return _correr(["session", "start", "--change-id", _CHANGE_ID, *extra], self.repo)

    def _presupuesto(self) -> dict:
        control = json.loads((self.dir_change / "control.json").read_text(encoding="utf-8"))
        return control["sesiones"][-1]["presupuesto"]

    def test_sin_flag_es_1(self):
        r = self._start()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self._presupuesto()["max_continuaciones_por_subagente"], 1)

    def test_con_flag_3(self):
        r = self._start("--max-continuaciones", "3")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self._presupuesto()["max_continuaciones_por_subagente"], 3)

    def test_fuera_de_rango_exit_2(self):
        for valor in ("0", "-1", "6"):
            with self.subTest(valor=valor):
                r = self._start("--max-continuaciones", valor)
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        control = json.loads((self.dir_change / "control.json").read_text(encoding="utf-8"))
        self.assertEqual(control.get("sesiones", []), [])

    def test_status_lo_muestra(self):
        r = self._start("--max-continuaciones", "4")
        self.assertEqual(r.returncode, 0, r.stderr)
        r = _correr(["session", "status", "--change-id", _CHANGE_ID], self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("max_continuaciones_por_subagente=4", r.stdout)
        r = _correr(["session", "status", "--change-id", _CHANGE_ID, "--json"], self.repo)
        self.assertEqual(json.loads(r.stdout)["max_continuaciones_por_subagente"], 4)

    def test_status_sesion_vieja_sin_clave_muestra_1(self):
        r = self._start()
        self.assertEqual(r.returncode, 0, r.stderr)
        ruta = self.dir_change / "control.json"
        control = json.loads(ruta.read_text(encoding="utf-8"))
        del control["sesiones"][-1]["presupuesto"]["max_continuaciones_por_subagente"]
        ruta.write_text(json.dumps(control, ensure_ascii=False, indent=2), encoding="utf-8")
        r = _correr(["session", "status", "--change-id", _CHANGE_ID], self.repo)
        self.assertIn("max_continuaciones_por_subagente=1", r.stdout)


if __name__ == "__main__":
    unittest.main()

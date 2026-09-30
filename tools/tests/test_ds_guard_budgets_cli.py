"""Tests de CLI de `ds_guard init --approval-mode`, `session start` (budgets
de policy) y `session aggregate` (v0.8 Change 3 T3+T5,
`20260930-autonomous-sdd-and-remediation`).

Mismo patrón que `test_ds_guard_source_cli.py`/`test_ds_guard_exec.py`: corre
`tools/ds_guard.py` real como subproceso contra un repo git temporal
sintético.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ORIGEN = Path(__file__).resolve().parents[2]
DS_GUARD = REPO_ORIGEN / "tools" / "ds_guard.py"
_CHANGE_ID = "20260930-test-budgets-cli"


_TEMPLATES_ORIGEN = REPO_ORIGEN / ".claude" / "skills" / "lead-data-scientist" / "templates"


def _crear_repo_git_temporal(prefix: str = "cli_budgets_") -> Path:
    repo = Path(tempfile.mkdtemp(prefix=prefix))
    subprocess.run(["git", "init", "-q"], cwd=str(repo), check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(repo), check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(repo), check=True)
    (repo / "README.md").write_text("repo de prueba\n", encoding="utf-8")
    # `ds_guard init` (modo completo) copia proposal.md/spec.md/design.md/
    # tasks.md/verification.md desde acá -- mismo requisito que en un
    # proyecto instalado real (self-hosting: este repo también los tiene).
    destino_templates = repo / ".claude" / "skills" / "lead-data-scientist" / "templates"
    shutil.copytree(_TEMPLATES_ORIGEN, destino_templates)
    subprocess.run(["git", "add", "."], cwd=str(repo), check=True)
    subprocess.run(["git", "commit", "-q", "-m", "inicial"], cwd=str(repo), check=True)
    return repo


def _correr_ds_guard(args: list, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(DS_GUARD), *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _escribir_guardrails(repo: Path, datos: dict) -> Path:
    directorio = repo / ".claude"
    directorio.mkdir(parents=True, exist_ok=True)
    ruta = directorio / "guardrails.json"
    ruta.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
    return ruta


def _leer_control(repo: Path, change_id: str = _CHANGE_ID) -> dict:
    ruta = repo / "openspec" / "changes" / change_id / "control.json"
    return json.loads(ruta.read_text(encoding="utf-8"))


def _guardrails_con_budgets(budgets: dict) -> dict:
    return {
        "version": 2,
        "autonomy": {
            "version": 2,
            "mode": "supervised",
            "budgets": budgets,
        },
    }


class _BaseRepoGit(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_repo_git_temporal()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def _init(self, approval_mode: str = None, change_id: str = _CHANGE_ID) -> subprocess.CompletedProcess:
        args = ["init", "--change-id", change_id, "--modo", "completo"]
        if approval_mode is not None:
            args += ["--approval-mode", approval_mode]
        return _correr_ds_guard(args, self.repo)


class TestInitApprovalMode(_BaseRepoGit):
    def test_sin_flag_persiste_per_change(self):
        r = self._init()
        self.assertEqual(r.returncode, 0, r.stderr)
        control = _leer_control(self.repo)
        self.assertEqual(control["aprobacion_modo"], "per_change")

    def test_con_flag_checkpoints_se_persiste(self):
        r = self._init(approval_mode="checkpoints")
        self.assertEqual(r.returncode, 0, r.stderr)
        control = _leer_control(self.repo)
        self.assertEqual(control["aprobacion_modo"], "checkpoints")

    def test_flag_invalido_rechazado_por_argparse(self):
        r = self._init(approval_mode="algo_no_valido")
        self.assertNotEqual(r.returncode, 0)


class TestSessionStartBudgets(_BaseRepoGit):
    def setUp(self):
        super().setUp()
        r = self._init()
        self.assertEqual(r.returncode, 0, r.stderr)

    def _minutos_de_la_sesion(self) -> float:
        control = _leer_control(self.repo)
        return control["sesiones"][-1]["presupuesto"]["minutos"]

    def test_sin_minutos_explicito_sin_guardrails_usa_90(self):
        r = _correr_ds_guard(["session", "start", "--change-id", _CHANGE_ID], self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self._minutos_de_la_sesion(), 90)

    def test_sin_minutos_explicito_con_policy_usa_el_valor_de_policy(self):
        _escribir_guardrails(self.repo, _guardrails_con_budgets({"session_minutes": 45}))
        r = _correr_ds_guard(["session", "start", "--change-id", _CHANGE_ID], self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self._minutos_de_la_sesion(), 45)

    def test_minutos_explicito_gana_sobre_policy(self):
        _escribir_guardrails(self.repo, _guardrails_con_budgets({"session_minutes": 45}))
        r = _correr_ds_guard(
            ["session", "start", "--change-id", _CHANGE_ID, "--minutos", "30"], self.repo
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self._minutos_de_la_sesion(), 30)

    def test_valor_invalido_de_policy_rechazado_no_degrada_a_default(self):
        _escribir_guardrails(self.repo, _guardrails_con_budgets({"session_minutes": -5}))
        r = _correr_ds_guard(["session", "start", "--change-id", _CHANGE_ID], self.repo)
        self.assertEqual(r.returncode, 2, r.stdout)
        # No se abrió ninguna sesión (el error se detectó antes de escribir).
        control = _leer_control(self.repo)
        self.assertEqual(control.get("sesiones", []), [])

    def test_sin_autonomy_budgets_en_absoluto_comportamiento_identico_a_hoy(self):
        _escribir_guardrails(
            self.repo,
            {"version": 2, "autonomy": {"version": 2, "mode": "supervised"}},
        )
        r = _correr_ds_guard(["session", "start", "--change-id", _CHANGE_ID], self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self._minutos_de_la_sesion(), 90)


class TestSessionAggregate(_BaseRepoGit):
    def setUp(self):
        super().setUp()
        r = self._init()
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_change_recien_creado_sin_sesiones(self):
        r = _correr_ds_guard(
            ["session", "aggregate", "--change-id", _CHANGE_ID, "--json"], self.repo
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        payload = json.loads(r.stdout)
        self.assertEqual(payload["sesiones_totales"], 0)
        self.assertEqual(payload["sesiones_abiertas"], 0)
        self.assertEqual(payload["minutos_consumidos_totales"], 0.0)

    def test_con_una_sesion_activa_refleja_sesiones_totales_1(self):
        r = _correr_ds_guard(["session", "start", "--change-id", _CHANGE_ID], self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)
        r = _correr_ds_guard(
            ["session", "aggregate", "--change-id", _CHANGE_ID, "--json"], self.repo
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        payload = json.loads(r.stdout)
        self.assertEqual(payload["sesiones_totales"], 1)
        self.assertEqual(payload["sesiones_abiertas"], 1)

    def test_max_sessions_excedido_reporta_finding_sin_bloquear_exit_0(self):
        _escribir_guardrails(self.repo, _guardrails_con_budgets({"max_sessions": 1}))
        r = _correr_ds_guard(["session", "start", "--change-id", _CHANGE_ID], self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)
        r = _correr_ds_guard(
            ["session", "aggregate", "--change-id", _CHANGE_ID, "--json"], self.repo
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        payload = json.loads(r.stdout)
        self.assertEqual(len(payload["findings"]), 1)
        self.assertEqual(payload["findings"][0]["codigo"], "AUTONOMY-LIMIT-AGGREGATE-BUDGET")


_HASH_RELLENO = "0123456789abcdef" * 4  # 64 hex chars, no es un hash real del repo.


class TestApproveChecklistCheckpoints(_BaseRepoGit):
    def setUp(self):
        super().setUp()
        r = self._init(approval_mode="checkpoints")
        self.assertEqual(r.returncode, 0, r.stderr)

    def _escribir_proposal(self, seccion_checkpoints: str) -> None:
        ruta = self.repo / "openspec" / "changes" / _CHANGE_ID / "proposal.md"
        ruta.write_text(f"# Propuesta\n\n{seccion_checkpoints}\n", encoding="utf-8")

    def _aprobar_proposal(self) -> subprocess.CompletedProcess:
        return _correr_ds_guard(
            [
                "approve",
                "--change-id", _CHANGE_ID,
                "--artefacto", "proposal.md",
                "--usuario", "Test",
                "--fecha", "2026-09-30",
                "--alcance", "test",
                "--cita", "test",
            ],
            self.repo,
        )

    def test_checkpoint_bien_formado_se_persiste_en_decisiones_preaprobadas(self):
        self._escribir_proposal(
            "## Checkpoints de negocio\n\n"
            f"- **cp1**: resumen — alcance: tools/x.py — aprobacion: "
            f"{_CHANGE_ID}/proposal.md@{_HASH_RELLENO}\n"
        )
        r = self._aprobar_proposal()
        self.assertEqual(r.returncode, 0, r.stderr)
        control = _leer_control(self.repo)
        self.assertEqual(len(control["decisiones_preaprobadas"]), 1)
        self.assertEqual(control["decisiones_preaprobadas"][0]["decision_type"], "business_checkpoint")

    def test_checkpoint_invalido_rechaza_la_aprobacion_completa(self):
        self._escribir_proposal(
            "## Checkpoints de negocio\n\n- **cp-incompleto**: falta el resto del formato\n"
        )
        r = self._aprobar_proposal()
        self.assertEqual(r.returncode, 2, r.stdout)
        control = _leer_control(self.repo)
        self.assertEqual(control.get("aprobaciones", []), [])
        self.assertNotIn("decisiones_preaprobadas", control)

    def test_sin_seccion_de_checkpoints_aprueba_con_lista_vacia(self):
        self._escribir_proposal("## Otra sección\nsin checkpoints acá\n")
        r = self._aprobar_proposal()
        self.assertEqual(r.returncode, 0, r.stderr)
        control = _leer_control(self.repo)
        self.assertEqual(control["decisiones_preaprobadas"], [])


class TestApprovePerChangeNoParseaCheckpoints(_BaseRepoGit):
    def test_per_change_no_toca_decisiones_preaprobadas(self):
        r = self._init()  # per_change, default
        self.assertEqual(r.returncode, 0, r.stderr)
        ruta = self.repo / "openspec" / "changes" / _CHANGE_ID / "proposal.md"
        ruta.write_text(
            "# Propuesta\n\n## Checkpoints de negocio\n\n"
            "- **cp-que-no-deberia-importar**: formato ambiguo sin el resto\n",
            encoding="utf-8",
        )
        r = _correr_ds_guard(
            [
                "approve",
                "--change-id", _CHANGE_ID,
                "--artefacto", "proposal.md",
                "--usuario", "Test",
                "--fecha", "2026-09-30",
                "--alcance", "test",
                "--cita", "test",
            ],
            self.repo,
        )
        # En per_change, un checkpoint mal formado en la propuesta no importa
        # -- ni siquiera se intenta parsear.
        self.assertEqual(r.returncode, 0, r.stderr)
        control = _leer_control(self.repo)
        self.assertNotIn("decisiones_preaprobadas", control)


if __name__ == "__main__":
    unittest.main()

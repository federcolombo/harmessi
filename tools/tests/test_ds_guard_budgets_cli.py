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


def _escribir_control(repo: Path, control: dict, change_id: str = _CHANGE_ID) -> None:
    ruta = repo / "openspec" / "changes" / change_id / "control.json"
    ruta.write_text(json.dumps(control, ensure_ascii=False, indent=2), encoding="utf-8")


def _inyectar_sesion_cerrada(
    repo: Path, minutos_consumidos: float, id_sesion: str = None, change_id: str = _CHANGE_ID
) -> None:
    """Agrega una entrada de sesión YA CERRADA directamente a `control.json`
    (sin pasar por `session start`/`close` reales) -- única forma práctica de
    simular consumo acumulado de varios minutos reales en un test que corre
    en fracciones de segundo. El `id` es arbitrario (default: no secuencial,
    para probar que la suma no depende de convención de nombres) -- la
    correctitud de `presupuesto_agregado` está probada aparte, acá solo se
    usa como fixture."""
    control = _leer_control(repo, change_id)
    sesiones = control.setdefault("sesiones", [])
    sesiones.append(
        {
            "id": id_sesion or f"s-inyectada-{len(sesiones) + 1}",
            "inicio_utc": "2026-01-01T00:00:00Z",
            "cierre_utc": "2026-01-01T00:10:00Z",
            "modo": "estandar",
            "presupuesto": {
                "minutos": 90,
                "max_tareas": 3,
                "max_roles": 2,
                "max_reintentos": 2,
                "max_rondas_revision": 2,
                "max_continuaciones_por_subagente": 1,
            },
            "deadline_utc": "2026-01-01T01:30:00Z",
            "minutos_consumidos": minutos_consumidos,
            "resultado": "dentro_de_presupuesto",
            "subagentes": {"conteo": 0},
            "tareas": [],
            "roles": [],
            "reintentos": 0,
            "rondas_revision": 0,
            "estado_final": "completada",
        }
    )
    _escribir_control(repo, control, change_id)


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

    def test_max_sessions_excedido_reporta_finding_en_session_aggregate(self):
        # `session aggregate` (consulta pura) sigue siendo informativo (no
        # bloquea NADA por sí mismo, ni siquiera abrir una sesión) incluso
        # cuando el límite ya está alcanzado -- esto NO contradice R12 (que
        # exige que `session start`, no `session aggregate`, rechace abrir
        # una sesión nueva; ver el test siguiente). Distinto de la
        # afirmación ya superseded de que el EJE `aggregate_minutes` en sí
        # era "solo informativo" -- ver `TestAggregateMinutesLimitEfectivo`.
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

    def test_max_sessions_excedido_rechaza_una_session_start_adicional(self):
        # R12 de spec.md (hallazgo de revisión T8, corregido): a diferencia
        # de `aggregate_minutes` (solo informativo), `max_sessions` SÍ debe
        # bloquear una `session start` adicional -- sin escribir una entrada
        # nueva en `control["sesiones"]`.
        _escribir_guardrails(self.repo, _guardrails_con_budgets({"max_sessions": 1}))
        r = _correr_ds_guard(["session", "start", "--change-id", _CHANGE_ID], self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)
        r = _correr_ds_guard(
            ["session", "close", "--change-id", _CHANGE_ID, "--estado", "pausada"], self.repo
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        control_antes = _leer_control(self.repo)
        self.assertEqual(len(control_antes["sesiones"]), 1)

        r = _correr_ds_guard(["session", "start", "--change-id", _CHANGE_ID], self.repo)
        self.assertEqual(r.returncode, 2, r.stdout)

        control_despues = _leer_control(self.repo)
        self.assertEqual(len(control_despues["sesiones"]), 1)  # no se abrió una 2ª ventana


class TestAggregateMinutesLimitEfectivo(_BaseRepoGit):
    """`aggregate_minutes` es un LIMIT efectivo (enmienda 2026-09-30,
    decisión humana explícita registrada en el decision ledger --
    `ds_guard decision list --change-id
    20260930-autonomous-sdd-and-remediation` -- y en `verification.md` de
    ese Change), NO puramente informativo como se interpretó originalmente.
    Los 11 escenarios obligatorios de la corrección, en orden."""

    def setUp(self):
        super().setUp()
        r = self._init()
        self.assertEqual(r.returncode, 0, r.stderr)

    # 1. debajo del límite -> abre.
    def test_1_debajo_del_limite_abre(self):
        _escribir_guardrails(self.repo, _guardrails_con_budgets({"aggregate_minutes": 100}))
        _inyectar_sesion_cerrada(self.repo, 50.0)
        r = _correr_ds_guard(["session", "start", "--change-id", _CHANGE_ID], self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)

    # 2. exactamente en el límite -> bloquea (umbral >=, no solo >).
    def test_2_exactamente_en_el_limite_bloquea(self):
        _escribir_guardrails(self.repo, _guardrails_con_budgets({"aggregate_minutes": 100}))
        _inyectar_sesion_cerrada(self.repo, 100.0)
        r = _correr_ds_guard(["session", "start", "--change-id", _CHANGE_ID], self.repo)
        self.assertEqual(r.returncode, 2, r.stdout)

    # 3. por encima del límite -> bloquea.
    def test_3_encima_del_limite_bloquea(self):
        _escribir_guardrails(self.repo, _guardrails_con_budgets({"aggregate_minutes": 100}))
        _inyectar_sesion_cerrada(self.repo, 150.0)
        r = _correr_ds_guard(["session", "start", "--change-id", _CHANGE_ID], self.repo)
        self.assertEqual(r.returncode, 2, r.stdout)

    # 4. varias sesiones suman (ninguna individual llega al límite sola).
    def test_4_varias_sesiones_suman(self):
        _escribir_guardrails(self.repo, _guardrails_con_budgets({"aggregate_minutes": 100}))
        _inyectar_sesion_cerrada(self.repo, 40.0)
        _inyectar_sesion_cerrada(self.repo, 40.0)
        _inyectar_sesion_cerrada(self.repo, 40.0)  # 120 >= 100
        r = _correr_ds_guard(["session", "start", "--change-id", _CHANGE_ID], self.repo)
        self.assertEqual(r.returncode, 2, r.stdout)

    # 5. cerrar/reabrir no resetea el acumulado.
    def test_5_cerrar_reabrir_no_resetea(self):
        _escribir_guardrails(self.repo, _guardrails_con_budgets({"aggregate_minutes": 200}))
        _inyectar_sesion_cerrada(self.repo, 90.0)
        r = _correr_ds_guard(["session", "start", "--change-id", _CHANGE_ID], self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)  # 90 < 200, abre
        r = _correr_ds_guard(
            ["session", "close", "--change-id", _CHANGE_ID, "--estado", "pausada"], self.repo
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        # La sesión recién cerrada consumió minutos reales (~0, corrida
        # instantánea) -- el acumulado sigue siendo ~90, no se reseteó a 0
        # por haber cerrado. Confirmamos vía `session aggregate`.
        r = _correr_ds_guard(
            ["session", "aggregate", "--change-id", _CHANGE_ID, "--json"], self.repo
        )
        payload = json.loads(r.stdout)
        self.assertGreaterEqual(payload["minutos_consumidos_totales"], 90.0)
        # Empujamos el acumulado real por encima del límite inyectando una
        # tercera entrada y confirmamos que la reapertura sí bloquea.
        _inyectar_sesion_cerrada(self.repo, 150.0)
        r = _correr_ds_guard(["session", "start", "--change-id", _CHANGE_ID], self.repo)
        self.assertEqual(r.returncode, 2, r.stdout)

    # 6. IDs distintos (no secuenciales) no evaden la suma.
    def test_6_ids_diferentes_no_evaden(self):
        _escribir_guardrails(self.repo, _guardrails_con_budgets({"aggregate_minutes": 100}))
        _inyectar_sesion_cerrada(self.repo, 60.0, id_sesion="s-rara-xyz")
        _inyectar_sesion_cerrada(self.repo, 60.0, id_sesion="otra-convencion-2026")
        r = _correr_ds_guard(["session", "start", "--change-id", _CHANGE_ID], self.repo)
        self.assertEqual(r.returncode, 2, r.stdout)  # 120 >= 100, sin importar los ids

    # 7. max_sessions y aggregate_budget funcionan independientemente.
    def test_7a_solo_max_sessions_configurado_bloquea_por_cantidad(self):
        _escribir_guardrails(self.repo, _guardrails_con_budgets({"max_sessions": 1}))
        _inyectar_sesion_cerrada(self.repo, 1.0)  # muy poco tiempo, pero 1 sesión ya
        r = _correr_ds_guard(["session", "start", "--change-id", _CHANGE_ID], self.repo)
        self.assertEqual(r.returncode, 2, r.stdout)

    def test_7b_solo_aggregate_minutes_configurado_bloquea_por_tiempo(self):
        _escribir_guardrails(self.repo, _guardrails_con_budgets({"aggregate_minutes": 10}))
        _inyectar_sesion_cerrada(self.repo, 1.0)
        _inyectar_sesion_cerrada(self.repo, 1.0)
        _inyectar_sesion_cerrada(self.repo, 1.0)
        _inyectar_sesion_cerrada(self.repo, 1.0)
        _inyectar_sesion_cerrada(self.repo, 1.0)
        _inyectar_sesion_cerrada(self.repo, 1.0)
        _inyectar_sesion_cerrada(self.repo, 5.0)  # 11 min >= 10, pero 7 sesiones (sin límite)
        r = _correr_ds_guard(["session", "start", "--change-id", _CHANGE_ID], self.repo)
        self.assertEqual(r.returncode, 2, r.stdout)

    # 8. agregado agotado -> LIMIT/checkpoint, nunca STOP.
    def test_8_agregado_agotado_es_limit_no_stop(self):
        _escribir_guardrails(self.repo, _guardrails_con_budgets({"aggregate_minutes": 10}))
        _inyectar_sesion_cerrada(self.repo, 20.0)
        r = _correr_ds_guard(["session", "start", "--change-id", _CHANGE_ID], self.repo)
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("AUTONOMY-LIMIT-AGGREGATE-BUDGET", r.stderr)
        self.assertNotIn("AUTONOMY-STOP-", r.stderr)

    # 9. config ausente -> backward-compatible (sin límite, aunque haya
    #    mucho consumo acumulado, sigue abriendo).
    def test_9_config_ausente_backward_compatible(self):
        _inyectar_sesion_cerrada(self.repo, 100000.0)  # cualquier cantidad, sin límite configurado
        r = _correr_ds_guard(["session", "start", "--change-id", _CHANGE_ID], self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)

    # 10. config inválida -> fail-closed (no se trata como ausente).
    def test_10_config_invalida_fail_closed(self):
        _escribir_guardrails(self.repo, _guardrails_con_budgets({"aggregate_minutes": -5}))
        r = _correr_ds_guard(["session", "start", "--change-id", _CHANGE_ID], self.repo)
        self.assertEqual(r.returncode, 2, r.stdout)
        control = _leer_control(self.repo)
        self.assertEqual(control.get("sesiones", []), [])

    # 11. (end-to-end CLI del bloqueo real) -- ya cubierto por todos los
    #     tests de arriba, todos corren contra el CLI real como subproceso,
    #     no contra la función pura en memoria.


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

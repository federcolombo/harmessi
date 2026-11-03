"""Tests de límites agregados `limits` vs `budgets` (R1-R6 de
20261005-operational-autonomy-hardening, T1).

Resolvedor en proceso (`ds_guard._resolver_budgets*`) + CLI real como subproceso
contra un repo git temporal sintético (mismo patrón que `test_ds_guard_budgets_cli.py`).
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
sys.path.insert(0, str(REPO_ORIGEN / "tools"))

import ds_guard  # noqa: E402

DS_GUARD = REPO_ORIGEN / "tools" / "ds_guard.py"
_TEMPLATES_ORIGEN = REPO_ORIGEN / ".claude" / "skills" / "lead-data-scientist" / "templates"
_CHANGE_ID = "20261005-test-operational-budgets"


def _guardrails(limits=None, budgets=None) -> dict:
    autonomy = {"version": 2, "mode": "supervised"}
    if limits is not None:
        autonomy["limits"] = limits
    if budgets is not None:
        autonomy["budgets"] = budgets
    return {"version": 2, "autonomy": autonomy}


def _escribir_guardrails(repo: Path, datos: dict) -> None:
    directorio = repo / ".claude"
    directorio.mkdir(parents=True, exist_ok=True)
    (directorio / "guardrails.json").write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")


class TestResolverBudgets(unittest.TestCase):
    def setUp(self):
        self.repo = Path(tempfile.mkdtemp(prefix="op_budgets_res_"))

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def _resolver(self, **kw):
        _escribir_guardrails(self.repo, _guardrails(**kw))
        return ds_guard._resolver_budgets_con_fuentes(self.repo)

    def test_limits_only(self):
        b, f = self._resolver(limits={"max_sessions": 3, "max_total_minutes": 120})
        self.assertEqual((b["max_sessions"], b["aggregate_minutes"]), (3, 120))
        self.assertEqual((f["max_sessions"], f["aggregate_minutes"]), ("limits", "limits"))
        self.assertEqual(ds_guard._resolver_budgets(self.repo), b)

    def test_budgets_only(self):
        b, f = self._resolver(budgets={"max_sessions": 4, "aggregate_minutes": 200})
        self.assertEqual((b["max_sessions"], b["aggregate_minutes"]), (4, 200))
        self.assertEqual(f["max_sessions"], "budgets")
        self.assertEqual(f["session_minutes"], "default")

    def test_iguales(self):
        b, f = self._resolver(
            limits={"max_sessions": 4, "max_total_minutes": 200},
            budgets={"max_sessions": 4, "aggregate_minutes": 200},
        )
        self.assertEqual((b["max_sessions"], b["aggregate_minutes"]), (4, 200))
        self.assertTrue(f["max_sessions"].startswith("ambas"))
        self.assertIn("mínimo=200", f["aggregate_minutes"])

    def test_distintos_gana_el_menor_en_ambos_ordenes(self):
        b, f = self._resolver(
            limits={"max_sessions": 3, "max_total_minutes": 500},
            budgets={"max_sessions": 9, "aggregate_minutes": 100},
        )
        self.assertEqual((b["max_sessions"], b["aggregate_minutes"]), (3, 100))
        self.assertIn("mínimo=3", f["max_sessions"])
        b, _f = self._resolver(
            limits={"max_sessions": 9, "max_total_minutes": 50},
            budgets={"max_sessions": 5, "aggregate_minutes": 100},
        )
        self.assertEqual((b["max_sessions"], b["aggregate_minutes"]), (5, 50))

    def test_ninguno_usa_defaults(self):
        b, f = self._resolver()
        self.assertIsNone(b["max_sessions"])
        self.assertIsNone(b["aggregate_minutes"])
        self.assertEqual(b["session_minutes"], 90)
        self.assertEqual(set(f.values()), {"default"})

    def test_sin_archivo_usa_defaults(self):
        b, f = ds_guard._resolver_budgets_con_fuentes(self.repo)
        self.assertEqual(b, dict(ds_guard._BUDGET_DEFAULTS))

    def test_limits_invalido_levanta(self):
        for valor in (0, -3, "5", 1.5, True, None):
            for clave in ("max_sessions", "max_total_minutes"):
                _escribir_guardrails(self.repo, _guardrails(limits={clave: valor}))
                with self.assertRaises(ds_guard.BudgetsInvalidosError, msg=(clave, valor)) as ctx:
                    ds_guard._resolver_budgets(self.repo)
                self.assertEqual(ctx.exception.findings[0].codigo, "AUTONOMY-POLICY-LIMITS")

    def test_limits_no_dict_levanta(self):
        _escribir_guardrails(self.repo, _guardrails(limits=[1, 2]))
        with self.assertRaises(ds_guard.BudgetsInvalidosError):
            ds_guard._resolver_budgets(self.repo)

    def test_budgets_invalido_levanta(self):
        _escribir_guardrails(self.repo, _guardrails(budgets={"aggregate_minutes": -1}))
        with self.assertRaises(ds_guard.BudgetsInvalidosError):
            ds_guard._resolver_budgets(self.repo)

    def test_budgets_bool_levanta(self):
        _escribir_guardrails(self.repo, _guardrails(budgets={"max_sessions": True}))
        with self.assertRaises(ds_guard.BudgetsInvalidosError):
            ds_guard._resolver_budgets(self.repo)

    def test_budgets_no_dict_levanta(self):
        for valor in (None, 5, "x", [1]):
            _escribir_guardrails(
                self.repo,
                {"version": 2, "autonomy": {"version": 2, "mode": "supervised", "budgets": valor}},
            )
            with self.assertRaises(ds_guard.BudgetsInvalidosError, msg=repr(valor)) as ctx:
                ds_guard._resolver_budgets(self.repo)
            self.assertEqual(ctx.exception.findings[0].codigo, "AUTONOMY-POLICY-LIMITS")

    def test_guardrails_ilegible_avisa_y_degrada_a_defaults(self):
        ruta = self.repo / ".claude" / "guardrails.json"
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text("{ esto no es json", encoding="utf-8")
        self.assertEqual(ds_guard._aviso_guardrails_ilegible(self.repo), ds_guard.AVISO_GUARDRAILS_ILEGIBLE)
        b, f = ds_guard._resolver_budgets_con_fuentes(self.repo)
        self.assertEqual(b, dict(ds_guard._BUDGET_DEFAULTS))
        self.assertEqual(set(f.values()), {"guardrails ilegible"})

    def test_sin_archivo_o_legible_no_hay_aviso(self):
        self.assertIsNone(ds_guard._aviso_guardrails_ilegible(self.repo))
        _escribir_guardrails(self.repo, _guardrails(limits={"max_sessions": 3}))
        self.assertIsNone(ds_guard._aviso_guardrails_ilegible(self.repo))

    def test_claves_desconocidas_en_limits_se_ignoran(self):
        b, _f = self._resolver(limits={"max_sessions": 3, "otra": "x"})
        self.assertEqual(b["max_sessions"], 3)


def _crear_repo_git_temporal() -> Path:
    repo = Path(tempfile.mkdtemp(prefix="op_budgets_cli_"))
    subprocess.run(["git", "init", "-q"], cwd=str(repo), check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(repo), check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(repo), check=True)
    (repo / "README.md").write_text("repo de prueba\n", encoding="utf-8")
    shutil.copytree(_TEMPLATES_ORIGEN, repo / ".claude" / "skills" / "lead-data-scientist" / "templates")
    subprocess.run(["git", "add", "."], cwd=str(repo), check=True)
    subprocess.run(["git", "commit", "-q", "-m", "inicial"], cwd=str(repo), check=True)
    return repo


def _cli(args: list, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(DS_GUARD), *args], cwd=str(cwd), capture_output=True, text=True, encoding="utf-8"
    )


class _BaseCli(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_repo_git_temporal()
        r = _cli(["init", "--change-id", _CHANGE_ID, "--modo", "completo"], self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def _ruta_control(self) -> Path:
        return self.repo / "openspec" / "changes" / _CHANGE_ID / "control.json"

    def _control(self) -> dict:
        return json.loads(self._ruta_control().read_text(encoding="utf-8"))

    def _inyectar_cerradas(self, minutos: list) -> None:
        control = self._control()
        for i, m in enumerate(minutos):
            control["sesiones"].append(
                {
                    "id": f"s-inyectada-{i + 1}",
                    "inicio_utc": "2026-01-01T00:00:00Z",
                    "cierre_utc": "2026-01-01T00:10:00Z",
                    "modo": "estandar",
                    "presupuesto": {"minutos": 90, "max_tareas": 3, "max_roles": 2, "max_reintentos": 2,
                                    "max_rondas_revision": 2, "max_continuaciones_por_subagente": 1},
                    "deadline_utc": "2026-01-01T01:30:00Z",
                    "minutos_consumidos": m,
                    "resultado": "dentro_de_presupuesto",
                    "subagentes": {"conteo": 0},
                    "tareas": [], "roles": [], "reintentos": 0, "rondas_revision": 0,
                    "estado_final": "completada",
                }
            )
        self._ruta_control().write_text(json.dumps(control, ensure_ascii=False, indent=2), encoding="utf-8")


class TestEnforcementE2E(_BaseCli):
    def test_limits_only_minutos_agotados_rechaza_sin_escribir(self):
        _escribir_guardrails(self.repo, _guardrails(limits={"max_total_minutes": 60}))
        self._inyectar_cerradas([61.0])
        antes = self._ruta_control().read_bytes()
        r = _cli(["session", "start", "--change-id", _CHANGE_ID], self.repo)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("AUTONOMY-LIMIT-AGGREGATE-BUDGET", r.stderr)
        self.assertIn("limits", r.stderr)  # la fuente efectiva se informa
        self.assertEqual(self._ruta_control().read_bytes(), antes)

    def test_limits_only_sesiones_agotadas_rechaza_sin_escribir(self):
        _escribir_guardrails(self.repo, _guardrails(limits={"max_sessions": 2}))
        self._inyectar_cerradas([1.0, 1.0])
        antes = self._ruta_control().read_bytes()
        r = _cli(["session", "start", "--change-id", _CHANGE_ID], self.repo)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("AUTONOMY-LIMIT-AGGREGATE-BUDGET", r.stderr)
        self.assertEqual(self._ruta_control().read_bytes(), antes)

    def test_bajo_el_limite_permite(self):
        _escribir_guardrails(self.repo, _guardrails(limits={"max_sessions": 5, "max_total_minutes": 600}))
        self._inyectar_cerradas([1.0])
        r = _cli(["session", "start", "--change-id", _CHANGE_ID], self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_menor_entre_limits_y_budgets_bloquea(self):
        _escribir_guardrails(
            self.repo, _guardrails(limits={"max_total_minutes": 30}, budgets={"aggregate_minutes": 1000})
        )
        self._inyectar_cerradas([31.0])
        r = _cli(["session", "start", "--change-id", _CHANGE_ID], self.repo)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)

    def test_limits_invalido_rechaza_start(self):
        _escribir_guardrails(self.repo, _guardrails(limits={"max_sessions": -1}))
        r = _cli(["session", "start", "--change-id", _CHANGE_ID], self.repo)
        self.assertEqual(r.returncode, 2)
        self.assertIn("AUTONOMY-POLICY-LIMITS", r.stderr)
        self.assertEqual(self._control()["sesiones"], [])


class TestAvisoGuardrailsIlegibleCli(_BaseCli):
    def _corromper(self):
        ruta = self.repo / ".claude" / "guardrails.json"
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text("{ esto no es json", encoding="utf-8")

    def test_start_avisa_por_stderr_sin_cambiar_exit(self):
        self._corromper()
        r = _cli(["session", "start", "--change-id", _CHANGE_ID], self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("guardrails.json ilegible", r.stderr)
        self.assertIn("NO se aplican", r.stderr)

    def test_aggregate_texto_y_json(self):
        self._corromper()
        r = _cli(["session", "aggregate", "--change-id", _CHANGE_ID], self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("guardrails.json ilegible", r.stdout)
        d = json.loads(_cli(["session", "aggregate", "--change-id", _CHANGE_ID, "--json"], self.repo).stdout)
        self.assertEqual(len(d["avisos"]), 1)
        self.assertEqual(d["limites_fuentes"]["max_sessions"], "guardrails ilegible")

    def test_status_texto_y_json(self):
        self._corromper()
        r = _cli(["session", "status", "--change-id", _CHANGE_ID], self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("guardrails.json ilegible", r.stdout)
        d = json.loads(_cli(["session", "status", "--change-id", _CHANGE_ID, "--json"], self.repo).stdout)
        self.assertEqual(len(d["avisos"]), 1)

    def test_sin_problema_avisos_vacios(self):
        d = json.loads(_cli(["session", "aggregate", "--change-id", _CHANGE_ID, "--json"], self.repo).stdout)
        self.assertEqual(d["avisos"], [])


class TestFuentesYRestante(_BaseCli):
    def test_aggregate_json_limits_only(self):
        _escribir_guardrails(self.repo, _guardrails(limits={"max_sessions": 5, "max_total_minutes": 100}))
        self._inyectar_cerradas([30.0])
        r = _cli(["session", "aggregate", "--change-id", _CHANGE_ID, "--json"], self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)
        d = json.loads(r.stdout)
        self.assertEqual(d["limites_configurados"], {"aggregate_minutes": 100, "max_sessions": 5})
        self.assertEqual(d["limites_fuentes"], {"aggregate_minutes": "limits", "max_sessions": "limits"})
        self.assertAlmostEqual(d["restante"]["aggregate_minutes"], 70.0)
        self.assertEqual(d["restante"]["max_sessions"], 4)
        self.assertIn("minutos_consumidos_totales", d)
        self.assertIn("findings", d)

    def test_aggregate_restante_nunca_negativo(self):
        _escribir_guardrails(self.repo, _guardrails(budgets={"aggregate_minutes": 10}))
        self._inyectar_cerradas([50.0])
        d = json.loads(_cli(["session", "aggregate", "--change-id", _CHANGE_ID, "--json"], self.repo).stdout)
        self.assertEqual(d["restante"]["aggregate_minutes"], 0)
        self.assertIsNone(d["restante"]["max_sessions"])
        self.assertEqual(d["limites_fuentes"]["aggregate_minutes"], "budgets")

    def test_aggregate_texto_muestra_ambos_valores_cuando_difieren(self):
        _escribir_guardrails(
            self.repo, _guardrails(limits={"max_total_minutes": 300}, budgets={"aggregate_minutes": 100})
        )
        r = _cli(["session", "aggregate", "--change-id", _CHANGE_ID], self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("ambas (mínimo=100)", r.stdout)
        self.assertIn("budgets=100", r.stdout)
        self.assertIn("limits=300", r.stdout)
        self.assertIn("restante=", r.stdout)

    def test_status_json_agrega_limites_sin_romper_claves(self):
        _escribir_guardrails(self.repo, _guardrails(limits={"max_sessions": 5}))
        r = _cli(["session", "start", "--change-id", _CHANGE_ID], self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)
        d = json.loads(_cli(["session", "status", "--change-id", _CHANGE_ID, "--json"], self.repo).stdout)
        self.assertTrue(d["activa"])
        for clave in ("id", "minutos_transcurridos", "presupuesto", "findings"):
            self.assertIn(clave, d)
        eje = d["limites_agregados"]["max_sessions"]
        self.assertEqual((eje["efectivo"], eje["fuente"], eje["consumo"], eje["restante"]), (5, "limits", 1, 4))

    def test_status_sin_sesion_json_y_texto(self):
        _escribir_guardrails(self.repo, _guardrails(budgets={"aggregate_minutes": 60}))
        d = json.loads(_cli(["session", "status", "--change-id", _CHANGE_ID, "--json"], self.repo).stdout)
        self.assertFalse(d["activa"])
        self.assertEqual(d["limites_agregados"]["aggregate_minutes"]["fuente"], "budgets")
        t = _cli(["session", "status", "--change-id", _CHANGE_ID], self.repo).stdout
        self.assertIn("No hay sesión activa.", t)
        self.assertIn("aggregate_minutes", t)
        self.assertIn("fuente=budgets", t)


if __name__ == "__main__":
    unittest.main()

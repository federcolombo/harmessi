"""Tests del Change `20261016-v011-sessions-continuations-recovery` (R1-R8):
constante única del default de minutos, aviso anticipado, `minutos_restantes`
en `session status`, `session start --retomar` y mensaje de recuperación."""
from __future__ import annotations

import ast
import json
import shutil
import subprocess
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ORIGEN = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ORIGEN / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from dsguard import core, hook_presupuesto as hp, sdd  # noqa: E402
from test_ds_guard_budgets_cli import (  # noqa: E402
    _correr_ds_guard,
    _crear_repo_git_temporal,
    _leer_control,
    _escribir_control,
    _escribir_guardrails,
    _guardrails_con_budgets,
)

CHANGE_ID = "20261016-test-session-recovery"
FORMATO = "%Y-%m-%dT%H:%M:%SZ"


def _es_90(nodo) -> bool:
    return (
        isinstance(nodo, ast.Constant)
        and isinstance(nodo.value, (int, float))
        and not isinstance(nodo.value, bool)
        and nodo.value == 90
    )


def _hallazgos_90_de_minutos(ruta: Path) -> list:
    """Usos funcionales del literal 90 como minutos de sesión (AST acotado a
    contextos de minutos: no marca percentiles, n-gramas ni otros 90)."""
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    hallazgos = []
    for nodo in ast.walk(arbol):
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = nodo.args.posonlyargs + nodo.args.args
            for arg, default in zip(reversed(args), reversed(nodo.args.defaults)):
                if "minut" in arg.arg.lower() and _es_90(default):
                    hallazgos.append((nodo.lineno, f"default de {arg.arg}"))
            for arg, default in zip(nodo.args.kwonlyargs, nodo.args.kw_defaults):
                if default is not None and "minut" in arg.arg.lower() and _es_90(default):
                    hallazgos.append((nodo.lineno, f"default de {arg.arg}"))
        elif isinstance(nodo, ast.Dict):
            for clave, valor in zip(nodo.keys, nodo.values):
                if (
                    isinstance(clave, ast.Constant)
                    and isinstance(clave.value, str)
                    and "minut" in clave.value.lower()
                    and _es_90(valor)
                ):
                    hallazgos.append((valor.lineno, f"dict[{clave.value}]"))
        elif isinstance(nodo, ast.Call):
            if (
                isinstance(nodo.func, ast.Attribute)
                and nodo.func.attr == "get"
                and len(nodo.args) >= 2
                and isinstance(nodo.args[0], ast.Constant)
                and isinstance(nodo.args[0].value, str)
                and "minut" in nodo.args[0].value.lower()
                and _es_90(nodo.args[1])
            ):
                hallazgos.append((nodo.lineno, "get(minutos, 90)"))
            for kw in nodo.keywords:
                if kw.arg and "minut" in kw.arg.lower() and _es_90(kw.value):
                    hallazgos.append((nodo.lineno, f"kwarg {kw.arg}"))
        elif isinstance(nodo, ast.Assign):
            nombres = [t.id for t in nodo.targets if isinstance(t, ast.Name)]
            if _es_90(nodo.value) and any("minut" in n.lower() for n in nombres):
                if nombres != ["SESSION_MINUTES_DEFAULT"]:
                    hallazgos.append((nodo.lineno, f"asignación a {nombres}"))
    return hallazgos


class TestConstanteUnica(unittest.TestCase):
    def test_valor_y_referencias(self):
        self.assertEqual(core.SESSION_MINUTES_DEFAULT, 90)
        self.assertEqual(core.UMBRAL_AVISO_MINUTOS, 10)
        import ds_guard
        self.assertEqual(ds_guard._BUDGET_DEFAULTS["session_minutes"], core.SESSION_MINUTES_DEFAULT)
        import inspect
        firma = inspect.signature(sdd.session_start)
        self.assertEqual(firma.parameters["minutos"].default, core.SESSION_MINUTES_DEFAULT)

    def test_fallback_de_minutos_restantes(self):
        inicio = datetime.now(timezone.utc) - timedelta(minutes=80)
        sesion = {"inicio_utc": inicio.strftime(FORMATO), "presupuesto": {}}
        restantes = core.minutos_restantes(sesion)
        self.assertTrue(9.0 < restantes < 11.0, restantes)

    def test_sin_otro_90_funcional_de_minutos(self):
        rutas = sorted((REPO_ORIGEN / "tools" / "dsguard").glob("*.py")) + [REPO_ORIGEN / "tools" / "ds_guard.py"]
        self.assertGreater(len(rutas), 2)
        for ruta in rutas:
            self.assertEqual(_hallazgos_90_de_minutos(ruta), [], str(ruta))

    def test_detector_no_marca_falsos_positivos(self):
        tmp = Path(self._testMethodName + ".tmp.py")
        # Se analiza el código en memoria vía archivo temporal en el directorio actual de tests.
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            ruta = Path(d) / "x.py"
            ruta.write_text(
                "percentil = 90\nngram = {'max': 90}\n"
                "def f(p=90): return p\nx = d.get('q', 90)\n",
                encoding="utf-8",
            )
            self.assertEqual(_hallazgos_90_de_minutos(ruta), [])
            ruta.write_text("def g(minutos=90): return 1\n", encoding="utf-8")
            self.assertEqual(len(_hallazgos_90_de_minutos(ruta)), 1)
        del tmp


def _control_con_sesion(restantes_min: float) -> dict:
    control: dict = {}
    sdd.session_start(control)
    s = control["sesiones"][0]
    deadline = datetime.now(timezone.utc) + timedelta(minutes=restantes_min)
    s["deadline_utc"] = deadline.strftime(FORMATO)
    return control


class TestAvisoYStatusUnitario(unittest.TestCase):
    def test_sin_aviso_con_tiempo_suficiente(self):
        control = _control_con_sesion(60)
        estado = sdd.session_status(control)
        self.assertNotIn("aviso", estado)
        self.assertFalse(estado["vencida"])
        self.assertGreater(estado["minutos_restantes"], 50)
        self.assertIsNone(sdd.aviso_sesion_por_vencer(control, "c"))

    def test_aviso_en_umbral(self):
        control = _control_con_sesion(8)
        estado = sdd.session_status(control)
        self.assertIn("aviso", estado)
        self.assertFalse(estado["vencida"])
        linea = sdd.aviso_sesion_por_vencer(control, "mi-change")
        self.assertTrue(linea.startswith("AVISO-SESION-POR-VENCER"))
        self.assertIn("session close --change-id mi-change --estado pausada", linea)
        self.assertIn("--retomar", linea)
        self.assertNotIn("\n", linea)

    def test_vencida(self):
        control = _control_con_sesion(-3)
        estado = sdd.session_status(control)
        self.assertTrue(estado["vencida"])
        self.assertLessEqual(estado["minutos_restantes"], 0)
        self.assertNotIn("aviso", estado)
        self.assertIsNone(sdd.aviso_sesion_por_vencer(control, "c"))

    def test_sin_sesion_activa(self):
        self.assertIsNone(sdd.aviso_sesion_por_vencer({"sesiones": []}, "c"))
        self.assertEqual(sdd.session_status({"sesiones": []}), {"activa": False})


class _BaseCli(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_repo_git_temporal("sess_recovery_")
        r = _correr_ds_guard(["init", "--change-id", CHANGE_ID, "--modo", "completo"], self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def cli(self, *args):
        return _correr_ds_guard(list(args), self.repo)

    def sesion_cli(self, verbo, *extra):
        return self.cli("session", verbo, "--change-id", CHANGE_ID, *extra)

    def poner_restantes(self, minutos: float):
        control = _leer_control(self.repo, CHANGE_ID)
        deadline = datetime.now(timezone.utc) + timedelta(minutes=minutos)
        control["sesiones"][-1]["deadline_utc"] = deadline.strftime(FORMATO)
        _escribir_control(self.repo, control, CHANGE_ID)


class TestAvisoYStatusCli(_BaseCli):
    def test_status_json_con_minutos_restantes(self):
        self.assertEqual(self.sesion_cli("start").returncode, 0)
        r = self.sesion_cli("status", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        payload = json.loads(r.stdout)
        self.assertIn("minutos_restantes", payload)
        self.assertFalse(payload["vencida"])
        self.assertNotIn("aviso", payload)
        self.assertNotIn("AVISO-SESION-POR-VENCER", r.stderr)

    def test_status_cerca_del_vencimiento(self):
        self.sesion_cli("start")
        self.poner_restantes(5)
        r = self.sesion_cli("status", "--json")
        payload = json.loads(r.stdout)  # stdout sigue siendo JSON puro
        self.assertIn("aviso", payload)
        self.assertIn(CHANGE_ID, payload["aviso"])
        self.assertEqual(r.stderr.count("AVISO-SESION-POR-VENCER"), 1)
        self.assertNotIn("AVISO-SESION-POR-VENCER", r.stdout)

    def test_status_vencida(self):
        self.sesion_cli("start")
        self.poner_restantes(-2)
        payload = json.loads(self.sesion_cli("status", "--json").stdout)
        self.assertTrue(payload["vencida"])

    def test_status_texto_incluye_minutos_restantes(self):
        self.sesion_cli("start")
        r = self.sesion_cli("status")
        self.assertIn("minutos_restantes=", r.stdout)

    def test_aviso_en_otro_comando_que_carga_el_change_y_silencio_sin_sesion(self):
        r = self.sesion_cli("status")
        self.assertNotIn("AVISO-SESION-POR-VENCER", r.stderr)
        self.sesion_cli("start")
        self.poner_restantes(4)
        r = self.sesion_cli("note", "--tipo", "planificada", "--tarea", "t1")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stderr.count("AVISO-SESION-POR-VENCER"), 1)
        self.assertEqual(r.stdout.count("AVISO-SESION-POR-VENCER"), 0)


class TestRetomar(_BaseCli):
    def _preparar_s1(self, rondas=1):
        self.assertEqual(self.sesion_cli("start").returncode, 0)
        for _ in range(rondas):
            self.assertEqual(self.sesion_cli("note", "--rol", "reviewer", "--tipo", "ronda", "--tarea", "t1").returncode, 0)
        self.assertEqual(self.sesion_cli("note", "--rol", "writer", "--tipo", "reintento", "--tarea", "t2").returncode, 0)
        control = _leer_control(self.repo, CHANGE_ID)
        control["sesiones"][0]["subagentes"]["agente-x"] = {"continuaciones": 1, "ultimo_evento_utc": "2026-01-01T00:00:00Z"}
        _escribir_control(self.repo, control, CHANGE_ID)
        self.assertEqual(self.sesion_cli("close", "--estado", "pausada").returncode, 0)

    def test_retomar_hereda_gobernanza(self):
        self._preparar_s1()
        r = self.sesion_cli("start", "--retomar", "--minutos", "30")
        self.assertEqual(r.returncode, 0, r.stderr)
        s2 = _leer_control(self.repo, CHANGE_ID)["sesiones"][-1]
        self.assertEqual(s2["id"], "s2")
        self.assertEqual(s2["retomada_de"], "s1")
        self.assertEqual(s2["rondas_revision"], 1)
        self.assertEqual(s2["reintentos"], 1)
        self.assertEqual(sorted(s2["roles"]), ["reviewer", "writer"])
        self.assertEqual(sorted(s2["tareas"]), ["t1", "t2"])
        self.assertEqual(s2["subagentes"]["agente-x"]["continuaciones"], 1)
        self.assertEqual(s2["subagentes"]["conteo"], 0)
        self.assertEqual(s2["presupuesto"]["minutos"], 30)  # --minutos respetado
        self.assertEqual(s2["minutos_consumidos"], 0.0)

    def test_ciclo_de_reviewer_no_se_reinicia(self):
        self._preparar_s1(rondas=3)  # 3 > max_rondas_revision (2)
        self.sesion_cli("start", "--retomar")
        payload = json.loads(self.sesion_cli("status", "--json").stdout)
        self.assertEqual(payload["rondas_revision"], 3)
        codigos = [f["codigo"] for f in payload["findings"]]
        self.assertIn("SESION-LIMITE-RONDAS", codigos)

    def test_sin_retomar_nace_en_cero(self):
        self._preparar_s1()
        self.assertEqual(self.sesion_cli("start").returncode, 0)
        s2 = _leer_control(self.repo, CHANGE_ID)["sesiones"][-1]
        self.assertEqual(s2["rondas_revision"], 0)
        self.assertEqual(s2["reintentos"], 0)
        self.assertNotIn("retomada_de", s2)
        self.assertEqual(s2["subagentes"], {"conteo": 0})

    def test_retomar_sin_sesion_previa(self):
        r = self.sesion_cli("start", "--retomar")
        self.assertEqual(r.returncode, 2)
        self.assertIn("--retomar", r.stderr)
        self.assertEqual(_leer_control(self.repo, CHANGE_ID).get("sesiones", []), [])

    def test_retomar_con_sesion_activa_falla(self):
        self.sesion_cli("start")
        r = self.sesion_cli("start", "--retomar")
        self.assertEqual(r.returncode, 2)

    def test_retomar_usa_la_de_mayor_indice(self):
        self._preparar_s1()
        self.sesion_cli("start", "--retomar")
        self.sesion_cli("note", "--rol", "writer", "--tipo", "reintento")
        self.sesion_cli("close", "--estado", "pausada")
        self.sesion_cli("start", "--retomar")
        s3 = _leer_control(self.repo, CHANGE_ID)["sesiones"][-1]
        self.assertEqual(s3["retomada_de"], "s2")
        self.assertEqual(s3["reintentos"], 2)


class TestRetomarHeredaTopes(_BaseCli):
    """R4b: --retomar hereda los topes max_* de la última sesión cerrada."""

    def _s1_con_consumo(self):
        r = self.sesion_cli("start", "--max-tareas", "10", "--max-rondas", "5")
        self.assertEqual(r.returncode, 0, r.stderr)
        for i in range(8):
            r = self.sesion_cli("note", "--rol", "writer", "--tipo", "planificada", "--tarea", f"t{i}")
            self.assertEqual(r.returncode, 0, r.stderr)
        for _ in range(4):
            r = self.sesion_cli("note", "--rol", "reviewer", "--tipo", "ronda", "--tarea", "t0")
            self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.sesion_cli("close", "--estado", "pausada").returncode, 0)

    def test_retomar_sin_flags_hereda_topes_y_contadores(self):
        self._s1_con_consumo()
        r = self.sesion_cli("start", "--retomar")
        self.assertEqual(r.returncode, 0, r.stderr)
        s2 = _leer_control(self.repo, CHANGE_ID)["sesiones"][-1]
        self.assertEqual(s2["presupuesto"]["max_tareas"], 10)
        self.assertEqual(s2["presupuesto"]["max_rondas_revision"], 5)
        self.assertEqual(s2["presupuesto"]["max_reintentos"], 2)
        self.assertEqual(len(s2["tareas"]), 8)
        self.assertEqual(s2["rondas_revision"], 4)
        payload = json.loads(self.sesion_cli("status", "--json").stdout)
        codigos = [f["codigo"] for f in payload["findings"]]
        self.assertNotIn("SESION-LIMITE-TAREAS", codigos)
        self.assertNotIn("SESION-LIMITE-RONDAS", codigos)

    def test_retomar_con_flag_explicito_reemplaza_solo_ese_tope(self):
        self._s1_con_consumo()
        r = self.sesion_cli("start", "--retomar", "--max-tareas", "12")
        self.assertEqual(r.returncode, 0, r.stderr)
        s2 = _leer_control(self.repo, CHANGE_ID)["sesiones"][-1]
        self.assertEqual(s2["presupuesto"]["max_tareas"], 12)
        self.assertEqual(s2["presupuesto"]["max_rondas_revision"], 5)

    def test_sin_retomar_usa_defaults(self):
        self._s1_con_consumo()
        self.assertEqual(self.sesion_cli("start").returncode, 0)
        p = _leer_control(self.repo, CHANGE_ID)["sesiones"][-1]["presupuesto"]
        self.assertEqual((p["max_tareas"], p["max_roles"], p["max_reintentos"], p["max_rondas_revision"]), (3, 2, 2, 2))

    def test_max_sessions_se_verifica_al_retomar(self):
        _escribir_guardrails(self.repo, _guardrails_con_budgets({"max_sessions": 1}))
        self.assertEqual(self.sesion_cli("start").returncode, 0)
        self.assertEqual(self.sesion_cli("close", "--estado", "pausada").returncode, 0)
        r = self.sesion_cli("start", "--retomar")
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertEqual(len(_leer_control(self.repo, CHANGE_ID)["sesiones"]), 1)

    def test_aggregate_minutes_se_verifica_al_retomar(self):
        _escribir_guardrails(self.repo, _guardrails_con_budgets({"aggregate_minutes": 100}))
        self.assertEqual(self.sesion_cli("start").returncode, 0)
        self.assertEqual(self.sesion_cli("close", "--estado", "pausada").returncode, 0)
        control = _leer_control(self.repo, CHANGE_ID)
        control["sesiones"][0]["minutos_consumidos"] = 150.0
        _escribir_control(self.repo, control, CHANGE_ID)
        r = self.sesion_cli("start", "--retomar")
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertEqual(len(_leer_control(self.repo, CHANGE_ID)["sesiones"]), 1)


class TestMensajeRecuperacionRetomar(unittest.TestCase):
    def test_paso_3_usa_retomar(self):
        msg = hp.mensaje_recuperacion(sys.executable, CHANGE_ID)
        base = f'"{sys.executable}" tools/ds_guard.py session'
        self.assertIn(f"{base} start --change-id {CHANGE_ID} --retomar", msg)
        self.assertIn(f"{base} close --change-id {CHANGE_ID} --estado pausada", msg)

    def test_paso_3_aclara_herencia_de_reintentos(self):
        msg = hp.mensaje_recuperacion(sys.executable, CHANGE_ID)
        self.assertIn("hereda el contador de reintentos", msg)
        self.assertIn("remediation extend", msg)
        self.assertIn("--max-reintentos", msg)


class TestSdd(unittest.TestCase):
    def test_retomar_sin_previa_levanta(self):
        with self.assertRaises(sdd.SesionPreviaAusenteError):
            sdd.session_start({}, retomar=True)

    def test_retomar_no_hereda_agentes_sin_continuaciones(self):
        control: dict = {}
        sdd.session_start(control)
        control["sesiones"][0]["subagentes"]["raro"] = "no-dict"
        sdd.session_close(control, "pausada")
        nueva = sdd.session_start(control, retomar=True)
        self.assertNotIn("raro", nueva["subagentes"])


if __name__ == "__main__":
    unittest.main()

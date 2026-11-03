"""Tests de `tools/dsguard/hook_subagentes.py` y su lanzador (v0.15 C4).
Invocan el hook directamente con los payloads saneados de
`tools/tests/fixtures/hooks/`, sin depender de `.claude/settings.json`."""
from __future__ import annotations

import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ORIGEN = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ORIGEN / "tools"))

from dsguard import core, hook_presupuesto, hook_subagentes  # noqa: E402
from ds_init import settings_merge  # noqa: E402

FIXTURES = REPO_ORIGEN / "tools" / "tests" / "fixtures" / "hooks"
AGENT_ID = "a0000000000000001"
PROHIBIDOS = ("/ruta/ficticia", "<redactado>", "last_assistant_message", "agent_transcript_path",
              "transcript_path", "tool_use_id", "00000000-0000-4000-8000-000000000001")


def _fixture(nombre: str) -> dict:
    return json.loads((FIXTURES / nombre).read_text(encoding="utf-8"))


def _control(subagentes=None) -> dict:
    return {
        "schema_version": 1,
        "sesiones": [{
            "id": "s1", "estado_final": "activa", "deadline_utc": "2099-01-01T00:00:00Z",
            "presupuesto": {"max_continuaciones_por_subagente": 1},
            "subagentes": subagentes if subagentes is not None else {"conteo": 0},
        }],
    }


class _BaseRepo(unittest.TestCase):
    def setUp(self):
        self.repo = Path(tempfile.mkdtemp(prefix="hook_subagentes_test_"))
        self.addCleanup(shutil.rmtree, self.repo, ignore_errors=True)
        self.ruta = self.repo / "openspec" / "changes" / "c1" / "control.json"

    def _escribir(self, control: dict):
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        core.escribir_control(self.ruta, control)

    def _leer_texto(self) -> str:
        return self.ruta.read_text(encoding="utf-8")

    def _correr(self, entrada) -> tuple:
        """Invoca `main()` con `entrada` (dict o str) por stdin; devuelve
        `(exit_code, stderr)`."""
        texto = entrada if isinstance(entrada, str) else json.dumps(entrada)
        err = io.StringIO()
        with mock.patch.object(hook_subagentes, "REPO_ROOT", self.repo), \
                mock.patch.object(sys, "stdin", io.StringIO(texto)), \
                mock.patch.object(sys, "stderr", err):
            codigo = hook_subagentes.main()
        return codigo, err.getvalue()

    def _subs(self) -> dict:
        return json.loads(self._leer_texto())["sesiones"][0]["subagentes"]


class TestFixtures(unittest.TestCase):
    def test_launch_sin_agent_id_y_resto_con_agent_id(self):
        launch = _fixture("agent_launch.json")
        self.assertNotIn("agent_id", launch)
        self.assertNotIn("agent_type", launch)
        for nombre in ("pretool_in_subagent.json", "subagent_start.json", "subagent_stop.json"):
            datos = _fixture(nombre)
            self.assertEqual(datos["agent_id"], AGENT_ID)
            self.assertEqual(datos["agent_type"], "general-purpose")
        self.assertEqual(_fixture("subagent_stop.json")["last_assistant_message"], "<redactado>")

    def test_sin_paths_reales(self):
        for ruta in FIXTURES.glob("*.json"):
            texto = ruta.read_text(encoding="utf-8")
            self.assertNotIn("C:\\", texto)
            self.assertNotIn("Users", texto)
            self.assertNotIn("fcolombo", texto)


class TestRegistro(_BaseRepo):
    def test_start_nuevo(self):
        self._escribir(_control())
        codigo, _ = self._correr(_fixture("subagent_start.json"))
        self.assertEqual(codigo, 0)
        e = self._subs()[AGENT_ID]
        self.assertEqual((e["rol"], e["arranques"], e["paradas"], e["continuaciones"]),
                         ("general-purpose", 1, 0, 0))
        self.assertEqual(self._subs()["conteo"], 0)

    def test_reanudacion_no_toca_continuaciones(self):
        self._escribir(_control({"conteo": 0, AGENT_ID: {"rol": "general-purpose", "arranques": 1,
                                                         "paradas": 1, "continuaciones": 1}}))
        self._correr(_fixture("subagent_start.json"))
        e = self._subs()[AGENT_ID]
        self.assertEqual((e["arranques"], e["continuaciones"]), (2, 1))

    def test_stop_acumula_duracion(self):
        self._escribir(_control({"conteo": 0, AGENT_ID: {
            "rol": "general-purpose", "arranques": 1, "paradas": 0, "continuaciones": 0,
            "duracion_s": 0.0, "arranque_actual_utc": "2000-01-01T00:00:00Z"}}))
        self._correr(_fixture("subagent_stop.json"))
        e = self._subs()[AGENT_ID]
        self.assertEqual(e["paradas"], 1)
        self.assertIn("fin_utc", e)
        self.assertGreater(e["duracion_s"], 0)
        self.assertIsNone(e["arranque_actual_utc"])

    def test_stop_sin_inicio_vigente_no_suma(self):
        self._escribir(_control())
        self._correr(_fixture("subagent_stop.json"))
        e = self._subs()[AGENT_ID]
        self.assertEqual((e["paradas"], e["arranques"], e["duracion_s"]), (1, 0, 0.0))

    def test_privacidad_nada_prohibido_persistido(self):
        self._escribir(_control())
        self._correr(_fixture("subagent_start.json"))
        self._correr(_fixture("subagent_stop.json"))
        texto = self._leer_texto()
        for prohibido in PROHIBIDOS:
            self.assertNotIn(prohibido, texto)

    def test_entradas_no_dict_toleradas(self):
        self._escribir(_control({"conteo": 0, "raro": "no-dict"}))
        codigo, _ = self._correr(_fixture("subagent_start.json"))
        self.assertEqual(codigo, 0)
        self.assertEqual(self._subs()["raro"], "no-dict")

    def test_subagentes_no_dict_se_reemplaza(self):
        control = _control()
        control["sesiones"][0]["subagentes"] = "roto"
        self._escribir(control)
        self._correr(_fixture("subagent_start.json"))
        self.assertIn(AGENT_ID, self._subs())


class TestFailOpen(_BaseRepo):
    def test_sin_sesion_activa_no_escribe(self):
        control = _control()
        control["sesiones"][0]["estado_final"] = "completada"
        self._escribir(control)
        antes = self._leer_texto()
        codigo, _ = self._correr(_fixture("subagent_start.json"))
        self.assertEqual(codigo, 0)
        self.assertEqual(self._leer_texto(), antes)

    def test_sin_openspec(self):
        codigo, _ = self._correr(_fixture("subagent_start.json"))
        self.assertEqual(codigo, 0)

    def test_stdin_invalido_o_vacio(self):
        self._escribir(_control())
        for entrada in ("", "no es json", "[1, 2]"):
            codigo, _ = self._correr(entrada)
            self.assertEqual(codigo, 0)

    def test_sin_agent_id_avisa_y_no_registra(self):
        self._escribir(_control())
        payload = _fixture("subagent_start.json")
        del payload["agent_id"]
        codigo, err = self._correr(payload)
        self.assertEqual(codigo, 0)
        self.assertIn("agent_id", err)
        self.assertEqual(self._subs(), {"conteo": 0})

    def test_evento_ajeno_se_ignora(self):
        self._escribir(_control())
        codigo, _ = self._correr(_fixture("pretool_in_subagent.json"))
        self.assertEqual(codigo, 0)
        self.assertEqual(self._subs(), {"conteo": 0})

    def test_control_corrupto(self):
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        self.ruta.write_text("no es json", encoding="utf-8")
        codigo, _ = self._correr(_fixture("subagent_start.json"))
        self.assertEqual(codigo, 0)

    def test_error_de_escritura(self):
        self._escribir(_control())
        with mock.patch.object(hook_subagentes, "_escribir_atomico", side_effect=OSError("disco")):
            codigo, err = self._correr(_fixture("subagent_start.json"))
        self.assertEqual(codigo, 0)
        self.assertIn("fail-open", err)


class TestEscrituraConcurrente(_BaseRepo):
    def test_hilos_concurrentes_no_corrompen_ni_dejan_tmp(self):
        import threading
        self._escribir(_control())
        errores = []

        def trabajar(n):
            for i in range(10):
                try:
                    hook_subagentes.procesar(self.repo, "SubagentStart", f"a{n}", "general-purpose")
                    hook_subagentes.procesar(self.repo, "SubagentStop", f"a{n}", "general-purpose")
                except Exception as exc:  # carrera residual declarada: no debe corromper
                    errores.append(exc)

        hilos = [threading.Thread(target=trabajar, args=(n,)) for n in range(4)]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join()
        datos = json.loads(self._leer_texto())  # JSON válido siempre
        self.assertIsInstance(datos["sesiones"][0]["subagentes"], dict)
        self.assertEqual(list(self.ruta.parent.glob("*.tmp")), [])

    def test_tmp_unico_por_proceso_e_hilo_y_limpieza_si_falla_reemplazo(self):
        self._escribir(_control())
        with mock.patch("os.replace", side_effect=PermissionError("bloqueado")), \
                mock.patch.object(hook_subagentes, "ESPERA_REINTENTO_S", 0):
            with self.assertRaises(PermissionError):
                hook_subagentes._escribir_atomico(self.ruta, _control())
        self.assertEqual(list(self.ruta.parent.glob("*.tmp")), [])
        json.loads(self._leer_texto())


class TestCoexistenciaPorRol(_BaseRepo):
    def test_stop_sin_start_crea_instancia_con_arranques_cero(self):
        self._escribir(_control({"conteo": 0, "general-purpose": {"continuaciones": 0}}))
        self._correr(_fixture("subagent_stop.json"))
        self.assertEqual(self._subs()[AGENT_ID]["arranques"], 0)
        self.assertNotIn("arranques", self._subs()["general-purpose"])  # la entrada por rol no se contamina


class TestIntegracionTopeContinuaciones(_BaseRepo):
    def test_sendmessage_por_agent_id_se_cuenta_y_el_segundo_se_deniega(self):
        self._escribir(_control())
        self._correr(_fixture("subagent_start.json"))
        sesion = json.loads(self._leer_texto())["sesiones"][0]
        msg = {"tool_name": "SendMessage", "tool_input": {"to": AGENT_ID}}
        permitido, _, mod = hook_presupuesto.evaluar(msg, sesion, None, "c1")
        self.assertTrue(permitido)
        self.assertTrue(mod)
        self.assertEqual(sesion["subagentes"][AGENT_ID]["continuaciones"], 1)
        permitido, motivo, _ = hook_presupuesto.evaluar(msg, sesion, None, "c1")
        self.assertFalse(permitido)
        self.assertIn(AGENT_ID, motivo)


class TestLauncher(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, str(REPO_ORIGEN / "tools" / "dsguard"))
        import hook_launcher_subagentes  # noqa: E402
        self.lanzador = hook_launcher_subagentes

    def test_sin_claude_project_dir_exit_0(self):
        err = io.StringIO()
        with mock.patch.dict("os.environ", {}, clear=True), mock.patch.object(sys, "stderr", err):
            self.assertEqual(self.lanzador.main(), 0)
        self.assertIn("CLAUDE_PROJECT_DIR", err.getvalue())

    def test_import_fallido_exit_0(self):
        err = io.StringIO()
        with mock.patch.dict("os.environ", {"CLAUDE_PROJECT_DIR": "x"}), \
                mock.patch.dict(sys.modules, {"launcher_common": None}), \
                mock.patch.object(sys, "stderr", err):
            self.assertEqual(self.lanzador.main(), 0)
        self.assertIn("fail-open", err.getvalue())

    def test_returncode_distinto_de_cero_del_subproceso_exit_0(self):
        repo = Path(tempfile.mkdtemp(prefix="launcher_sub_test_"))
        self.addCleanup(shutil.rmtree, repo, ignore_errors=True)
        (repo / "tools" / "dsguard").mkdir(parents=True)
        (repo / "tools" / "dsguard" / "hook_subagentes.py").write_text("raise SystemExit(2)\n", encoding="utf-8")
        interprete = repo / "python_falso"
        interprete.write_text("", encoding="utf-8")
        err = io.StringIO()
        with mock.patch.dict("os.environ", {"CLAUDE_PROJECT_DIR": str(repo)}), \
                mock.patch("launcher_common.resolver_repo_root", return_value=repo), \
                mock.patch("launcher_common.ruta_interprete_venv", return_value=interprete), \
                mock.patch("subprocess.run", return_value=mock.Mock(returncode=2)), \
                mock.patch.object(sys, "stderr", err):
            self.assertEqual(self.lanzador.main(), 0)
        self.assertIn("terminó con 2", err.getvalue())

    def test_excepcion_interna_exit_0(self):
        err = io.StringIO()
        with mock.patch.dict("os.environ", {"CLAUDE_PROJECT_DIR": "x"}), \
                mock.patch("launcher_common.resolver_repo_root", side_effect=RuntimeError("boom")), \
                mock.patch.object(sys, "stderr", err):
            self.assertEqual(self.lanzador.main(), 0)
        self.assertIn("fail-open", err.getvalue())


class TestMergeUpgrade(unittest.TestCase):
    """Un `upgrade` sobre una instalación previa recibe el evento nuevo vía
    `settings_merge`, sin pisar hooks ni duplicar (settings sintético)."""

    NUEVO = {"hooks": {
        "SubagentStart": [{"hooks": [{"type": "command", "command": "python x/hook_launcher_subagentes.py"}]}],
        "SubagentStop": [{"hooks": [{"type": "command", "command": "python x/hook_launcher_subagentes.py"}]}],
    }}
    EXISTENTE = {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "c"}]}]}}

    def test_agrega_idempotente_y_preserva(self):
        una = settings_merge.fusionar(self.EXISTENTE, self.NUEVO)
        self.assertIn("SubagentStart", una["hooks"])
        self.assertIn("SubagentStop", una["hooks"])
        self.assertEqual(una["hooks"]["PreToolUse"], self.EXISTENTE["hooks"]["PreToolUse"])
        dos = settings_merge.fusionar(una, self.NUEVO)
        self.assertEqual(dos, una)
        self.assertEqual(len(dos["hooks"]["SubagentStart"]), 1)


if __name__ == "__main__":
    unittest.main()

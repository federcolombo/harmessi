"""Tests del flag `--channel` de `ds_guard approve` y `ds_guard exec approve ...`
(`20261009-approval-trust-human-presence`, secciones C y E).

Repo git temporal con un Change sintético (nunca el repo real). La confirmación
se inyecta parcheando `human_presence.solicitar_confirmacion`; el único test que
usa la consola real es el de SUBPROCESO con stdin por pipe, que debe fallar."""
from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_ds_guard_exec import (  # noqa: E402
    DS_GUARD,
    INTERPRETER,
    _GUARDRAILS_SUPERVISED,
    _crear_repo_git_temporal,
    _escribir_guardrails,
    _escribir_script_ok,
    _scaffold_change,
    core,
)

import ds_guard  # noqa: E402
from dsguard import human_presence, sdd  # noqa: E402

CHANGE_ID = "20261009-canal-test"
SCRIPT = "scripts/ok_script.py"
CLAVES_HISTORICAS = {
    "artefacto", "algoritmo", "hash", "registrado_utc",
    "usuario", "fecha_declarada", "alcance_aprobado", "cita",
}
CLAVES_T1 = CLAVES_HISTORICAS | {"approval_channel", "confirmed_at", "channel_version"}
CONFIRMADO_EN = "2026-10-13T12:00:00Z"


def _resultado_ok():
    return human_presence.ResultadoPresencia(
        ok=True, canal=human_presence.CANAL_CONSOLE, confirmed_at=CONFIRMADO_EN,
        channel_version="console/v1", motivo="",
    )


def _resultado_fallo(motivo="confirmacion rechazada (prueba)"):
    return human_presence.ResultadoPresencia(
        ok=False, canal=None, confirmed_at=None, channel_version=None, motivo=motivo,
    )


class _Base(unittest.TestCase):
    def setUp(self):
        self.repo = _crear_repo_git_temporal(prefix="cli_canal_")
        _escribir_script_ok(self.repo, SCRIPT)
        _escribir_guardrails(self.repo, _GUARDRAILS_SUPERVISED)
        self.change_dir = _scaffold_change(self.repo, CHANGE_ID, SCRIPT)
        self.control_path = self.change_dir / "control.json"
        control = json.loads(self.control_path.read_text(encoding="utf-8"))
        control["alcance"]["rutas_autorizadas"] = ["scripts", "tests"]
        core.escribir_control(self.control_path, control)
        for nombre in ("a.md", "b.md"):
            (self.change_dir / nombre).write_text(f"# {nombre}\n", encoding="utf-8")
        self.cwd_previo = os.getcwd()
        os.chdir(self.repo)

    def tearDown(self):
        os.chdir(self.cwd_previo)
        shutil.rmtree(self.repo, ignore_errors=True)

    def meta(self, usuario="federico"):
        return ["--usuario", usuario, "--fecha", "2026-10-13", "--alcance", "alcance de prueba", "--cita", "n/a"]

    def approve_args(self, artefactos=("a.md",), channel=None, usuario="federico"):
        args = ["approve", "--change-id", CHANGE_ID]
        for a in artefactos:
            args += ["--artefacto", a]
        args += self.meta(usuario)
        if channel:
            args += ["--channel", channel]
        return args

    def exec_script_args(self, channel=None):
        args = ["exec", "approve", "script", "--change-id", CHANGE_ID, "--interpreter", INTERPRETER,
                *self.meta(), "--script", SCRIPT]
        if channel:
            args += ["--channel", channel]
        return args

    def correr(self, argv, efectos=None, resultado=None):
        """Corre `ds_guard.main` en proceso con la confirmación inyectada.
        Devuelve (codigo, stdout, stderr, mock)."""
        out, err = io.StringIO(), io.StringIO()
        if efectos is not None:
            parche = mock.patch.object(human_presence, "solicitar_confirmacion", side_effect=efectos)
        else:
            parche = mock.patch.object(
                human_presence, "solicitar_confirmacion", return_value=resultado or _resultado_ok())
        with parche as m, contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            codigo = ds_guard.main(argv)
        return codigo, out.getvalue(), err.getvalue(), m

    def aprobaciones(self):
        return json.loads(self.control_path.read_text(encoding="utf-8"))["aprobaciones"]


class TestT0(_Base):
    def test_default_forma_historica(self):
        codigo, _o, _e, m = self.correr(self.approve_args())
        self.assertEqual(codigo, 0)
        m.assert_not_called()
        ap = self.aprobaciones()
        self.assertEqual(len(ap), 1)
        self.assertEqual(set(ap[0]), CLAVES_HISTORICAS)
        self.assertEqual(list(ap[0]), [
            "artefacto", "algoritmo", "hash", "registrado_utc",
            "usuario", "fecha_declarada", "alcance_aprobado", "cita"])

    def test_declared_explicito_identico(self):
        codigo, _o, _e, m = self.correr(self.approve_args(channel="declared"))
        self.assertEqual(codigo, 0)
        m.assert_not_called()
        self.assertEqual(set(self.aprobaciones()[0]), CLAVES_HISTORICAS)

    def test_exec_approve_default_forma_historica(self):
        codigo, _o, _e, m = self.correr(self.exec_script_args())
        self.assertEqual(codigo, 0)
        m.assert_not_called()
        self.assertEqual(set(self.aprobaciones()[0]), CLAVES_HISTORICAS)

    def test_usuario_arbitrario_no_implica_t1(self):
        for usuario in ("root", "human", "console_confirmed", "federico-t1"):
            codigo, _o, _e, m = self.correr(self.approve_args(usuario=usuario))
            self.assertEqual(codigo, 0)
            m.assert_not_called()
        self.assertTrue(all("approval_channel" not in e for e in self.aprobaciones()))

    def test_channel_tras_separador_se_rechaza(self):
        antes = self.control_path.read_bytes()
        casos = [
            self.exec_script_args() + ["--", "--channel", "console_confirmed"],
            self.exec_script_args() + ["--", "--channel=console_confirmed"],
            ["exec", "approve", "pytest", "--change-id", CHANGE_ID, "--interpreter", INTERPRETER,
             *self.meta(), "--paths", "tests/test_x.py", "--", "--channel", "console_confirmed"],
        ]
        for argv in casos:
            codigo, _o, err, m = self.correr(argv)
            self.assertEqual(codigo, 2, argv)
            self.assertIn("`--channel` debe ir antes de `--`", err)
            m.assert_not_called()
            self.assertEqual(self.control_path.read_bytes(), antes)

    def test_no_existe_flag_yes(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as cm:
            ds_guard.main(self.approve_args() + ["--yes"])
        self.assertEqual(cm.exception.code, 2)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            ds_guard.main(self.approve_args(channel="tty_confirmed"))
        self.assertEqual(self.aprobaciones(), [])


class TestT1Inyectado(_Base):
    def test_approve_registra_campos_y_nada_mas(self):
        codigo, salida, _e, m = self.correr(self.approve_args(channel="console_confirmed"))
        self.assertEqual(codigo, 0)
        m.assert_called_once()
        contexto = m.call_args.args[0]
        self.assertEqual(
            contexto,
            {"change_id": CHANGE_ID, "artefacto": "a.md",
             "hash": core.hash_lf_v1(self.change_dir / "a.md"), "accion": "approve"})
        e = self.aprobaciones()[0]
        self.assertEqual(set(e), CLAVES_T1)
        self.assertEqual(e["approval_channel"], "console_confirmed")
        self.assertEqual(e["confirmed_at"], CONFIRMADO_EN)
        self.assertEqual(e["channel_version"], "console/v1")
        self.assertEqual(e["hash"], contexto["hash"])
        self.assertIn("el hash acredita identidad de contenido, no aprobación humana", salida)
        self.assertIn("approval_channel=console_confirmed", salida)
        # privacidad: ningún dato de challenge/respuesta/usuario del SO en el archivo
        crudo = self.control_path.read_text(encoding="utf-8").lower()
        for prohibido in ("challenge", "respuesta", "codigo"):
            self.assertNotIn(prohibido, crudo)

    def test_exec_approve_script_mismos_campos(self):
        codigo, salida, _e, m = self.correr(self.exec_script_args(channel="console_confirmed"))
        self.assertEqual(codigo, 0)
        contexto = m.call_args.args[0]
        self.assertEqual(contexto["accion"], "exec-approve")
        self.assertEqual(contexto["change_id"], CHANGE_ID)
        self.assertEqual(contexto["artefacto"], SCRIPT)
        e = self.aprobaciones()[0]
        self.assertEqual(set(e), CLAVES_T1)
        self.assertEqual(e["hash"], contexto["hash"])
        self.assertEqual(e["approval_channel"], "console_confirmed")
        self.assertEqual(e["channel_version"], "console/v1")
        self.assertIn("approval_channel=console_confirmed", salida)

    def test_varios_artefactos_un_challenge_por_artefacto(self):
        codigo, _o, _e, m = self.correr(self.approve_args(("a.md", "b.md"), channel="console_confirmed"))
        self.assertEqual(codigo, 0)
        self.assertEqual(m.call_count, 2)
        self.assertEqual([c.args[0]["artefacto"] for c in m.call_args_list], ["a.md", "b.md"])
        self.assertEqual([e["artefacto"] for e in self.aprobaciones()], ["a.md", "b.md"])

    def test_cambio_posterior_marca_stale(self):
        self.correr(self.approve_args(channel="console_confirmed"))
        res = sdd.resolver_aprobacion_registrada(self.repo, CHANGE_ID, "a.md")
        self.assertEqual(res["estado"], "verified")
        (self.change_dir / "a.md").write_text("# a.md cambiado\n", encoding="utf-8")
        res = sdd.resolver_aprobacion_registrada(self.repo, CHANGE_ID, "a.md")
        self.assertEqual(res["estado"], "stale")


class TestFalloCerrado(_Base):
    def test_fallo_approve_exit_2_sin_cambios(self):
        antes = self.control_path.read_bytes()
        codigo, _o, err, _m = self.correr(
            self.approve_args(channel="console_confirmed"), resultado=_resultado_fallo("sin consola de control"))
        self.assertEqual(codigo, 2)
        self.assertIn("sin consola de control", err)
        self.assertEqual(self.control_path.read_bytes(), antes)

    def test_fallo_exec_approve_exit_2_sin_cambios(self):
        antes = self.control_path.read_bytes()
        codigo, _o, err, _m = self.correr(
            self.exec_script_args(channel="console_confirmed"), resultado=_resultado_fallo())
        self.assertEqual(codigo, 2)
        self.assertIn("confirmacion rechazada", err)
        self.assertEqual(self.control_path.read_bytes(), antes)

    def test_falla_en_el_segundo_artefacto_no_escribe_nada(self):
        antes = self.control_path.read_bytes()
        codigo, _o, _e, m = self.correr(
            self.approve_args(("a.md", "b.md"), channel="console_confirmed"),
            efectos=[_resultado_ok(), _resultado_fallo()])
        self.assertEqual(codigo, 2)
        self.assertEqual(m.call_count, 2)
        self.assertEqual(self.control_path.read_bytes(), antes)
        self.assertEqual(self.aprobaciones(), [])

    def test_control_modificado_durante_el_prompt_aborta(self):
        def _muta_y_confirma(_contexto):
            control = core.leer_control(self.control_path)
            control["aprobaciones"].append({"artefacto": "otro.md", "algoritmo": "sha256/lf/v1", "hash": "0" * 64,
                                            "registrado_utc": core.ahora_utc(), "usuario": "x",
                                            "fecha_declarada": "2026-10-13", "alcance_aprobado": "a", "cita": "n/a"})
            core.escribir_control(self.control_path, control)
            return _resultado_ok()

        for argv in (self.approve_args(channel="console_confirmed"),
                     self.exec_script_args(channel="console_confirmed")):
            if self.aprobaciones():  # segunda vuelta: partir del estado inicial limpio
                control = core.leer_control(self.control_path)
                control["aprobaciones"] = []
                core.escribir_control(self.control_path, control)
            codigo, _o, err, _m = self.correr(argv, efectos=_muta_y_confirma)
            self.assertEqual(codigo, 2)
            self.assertIn("control.json cambió durante la confirmación; reintentá", err)
            # solo quedó la entrada ajena que mutó el archivo; la T1 no se escribió
            self.assertEqual([e["artefacto"] for e in self.aprobaciones()], ["otro.md"])

    def test_orden_de_timestamps_t1(self):
        marcas = {}

        def _confirma(_contexto):
            marcas["prompt"] = core.ahora_utc()
            return human_presence.ResultadoPresencia(
                ok=True, canal=human_presence.CANAL_CONSOLE, confirmed_at=core.ahora_utc(),
                channel_version="console/v1", motivo="")

        codigo, _o, _e, _m = self.correr(self.approve_args(channel="console_confirmed"), efectos=_confirma)
        self.assertEqual(codigo, 0)
        e = self.aprobaciones()[0]
        self.assertGreaterEqual(e["registrado_utc"], marcas["prompt"])
        self.assertLessEqual(e["registrado_utc"], core.ahora_utc())
        # registrado_utc se toma tras la confirmación: nunca antes del prompt; la forma conserva el orden de claves
        self.assertEqual(list(e)[:8], [
            "artefacto", "algoritmo", "hash", "registrado_utc",
            "usuario", "fecha_declarada", "alcance_aprobado", "cita"])

    def test_mensajes_de_exito_diferidos_hasta_confirmar(self):
        (self.change_dir / "proposal.md").write_text(
            "# p\n\n## Alcance autorizado\n- scripts/nuevo.py\n", encoding="utf-8")
        argv = self.approve_args(("proposal.md",), channel="console_confirmed")
        codigo, salida, _e, _m = self.correr(argv, resultado=_resultado_fallo())
        self.assertEqual(codigo, 2)
        self.assertNotIn("alcance autorizado materializado", salida)
        self.assertNotIn("el hash acredita", salida)
        codigo, salida, _e, _m = self.correr(argv)
        self.assertEqual(codigo, 0)
        self.assertIn("alcance autorizado materializado", salida)
        self.assertLess(salida.index("alcance autorizado materializado"), salida.index("proposal.md:"))

    def test_t0_con_alcance_imprime_igual(self):
        (self.change_dir / "proposal.md").write_text(
            "# p\n\n## Alcance autorizado\n- scripts/nuevo.py\n", encoding="utf-8")
        codigo, salida, _e, _m = self.correr(self.approve_args(("proposal.md",)))
        self.assertEqual(codigo, 0)
        self.assertIn("alcance autorizado materializado", salida)
        self.assertIn("  + scripts/nuevo.py", salida)

    def test_subproceso_real_con_stdin_por_pipe_falla(self):
        canal, _motivo = human_presence.canal_consola_real()
        if canal is not None:
            canal.cerrar()
            self.skipTest("este host expone una consola de control al proceso: el caso 'sin consola' no es reproducible")
        antes = self.control_path.read_bytes()
        argv = self.approve_args(channel="console_confirmed")
        r = subprocess.run(
            [sys.executable, str(DS_GUARD), *argv], cwd=str(self.repo), input="ABC123\ny\nyes\n",
            capture_output=True, text=True, encoding="utf-8", timeout=60)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertEqual(self.control_path.read_bytes(), antes)
        self.assertEqual(self.aprobaciones(), [])


if __name__ == "__main__":
    unittest.main()

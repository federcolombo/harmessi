"""Tests de recuperación de presupuesto agotado (R11-R14, R12 en particular,
`20261005-operational-autonomy-hardening`): el mensaje generado por
`hook_presupuesto.mensaje_recuperacion` usa el intérprete real y el
`change_id` de la sesión, y cada comando `status`/`close` es aceptado por el
allowlist del mismo hook; `session start` no."""
from __future__ import annotations

import os
import re
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ORIGEN = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ORIGEN / "tools"))

from dsguard import hook_presupuesto as hp  # noqa: E402

CHANGE_ID = "20261005-cambio-de-prueba"
AUTORIZADO = hp.normalizar_interprete(sys.executable)


def _sesion(minutos: float) -> dict:
    deadline = datetime.now(timezone.utc) + timedelta(minutes=minutos)
    return {
        "estado_final": "activa",
        "deadline_utc": deadline.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "subagentes": {"revisor": {"continuaciones": 0}},
        "presupuesto": {},
    }


def _comandos(mensaje: str, verbo: str) -> list:
    """Comandos del mensaje con `session <verbo>`, en sus dos formas (líneas
    `Bash:` y `PowerShell:`; la forma PowerShell conserva el prefijo `& `)."""
    resultado = []
    for linea in mensaje.splitlines():
        linea = linea.strip()
        for etiqueta in ("Bash:", "PowerShell:"):
            if linea.startswith(etiqueta) and f" session {verbo} " in linea:
                resultado.append(linea[len(etiqueta):].strip())
    return resultado


class TestMensajeRecuperacion(unittest.TestCase):
    def test_contiene_comandos_reales(self):
        msg = hp.mensaje_recuperacion(sys.executable, CHANGE_ID)
        base = f'"{sys.executable}" tools/ds_guard.py session'
        self.assertIn(f"{base} status --change-id {CHANGE_ID}", msg)
        self.assertIn(f"{base} close --change-id {CHANGE_ID} --estado pausada", msg)
        self.assertIn(f"{base} start --change-id {CHANGE_ID}", msg)
        self.assertIn("Después de cerrar", msg)

    def test_sin_rutas_hardcodeadas_de_la_maquina(self):
        msg = hp.mensaje_recuperacion("/opt/x/bin/python", "abc")
        self.assertIn('"/opt/x/bin/python"', msg)
        self.assertNotIn(str(REPO_ORIGEN), msg)

    def test_valor_literal_sin_minusculas_forzadas(self):
        msg = hp.mensaje_recuperacion("C:\\Mi Venv\\Scripts\\Python.EXE", "Abc")
        self.assertIn('"C:\\Mi Venv\\Scripts\\Python.EXE"', msg)

    def test_sin_change_id_omite_comandos(self):
        for faltante in (None, ""):
            msg = hp.mensaje_recuperacion(sys.executable, faltante)
            self.assertNotIn("tools/ds_guard.py", msg)
            self.assertIn("change_id", msg)

    def test_sin_interprete_omite_comandos(self):
        msg = hp.mensaje_recuperacion(None, CHANGE_ID)
        self.assertNotIn("tools/ds_guard.py", msg)
        self.assertIn("intérprete", msg)

    def test_status_y_close_aceptados_por_allowlist(self):
        msg = hp.mensaje_recuperacion(sys.executable, CHANGE_ID)
        for verbo in ("status", "close"):
            comandos = _comandos(msg, verbo)
            self.assertEqual(len(comandos), 2, msg)  # Bash + PowerShell
            self.assertTrue(any(c.startswith("& ") for c in comandos))
            for comando in comandos:
                self.assertTrue(hp._matchea_allowlist(comando, AUTORIZADO), comando)

    def test_start_rechazado_por_allowlist(self):
        msg = hp.mensaje_recuperacion(sys.executable, CHANGE_ID)
        comandos = _comandos(msg, "start")
        self.assertEqual(len(comandos), 2, msg)
        for comando in comandos:
            self.assertFalse(hp._matchea_allowlist(comando, AUTORIZADO), comando)


class TestVariantesInterprete(unittest.TestCase):
    SUFIJO = " tools/ds_guard.py session status --change-id x"

    def _ok(self, token_formateado: str) -> bool:
        return hp._matchea_allowlist(token_formateado + self.SUFIJO, AUTORIZADO)

    def test_comillas_y_mayusculas_minusculas(self):
        # En POSIX el case es significativo: solo se prueban variantes de case
        # si normcase las considera equivalentes.
        variantes = [sys.executable]
        if os.path.normcase("AbC") == os.path.normcase("abc"):
            variantes += [sys.executable.upper(), sys.executable.lower()]
        for v in variantes:
            self.assertTrue(self._ok(f'"{v}"'), v)

    def test_barras(self):
        alternativa = sys.executable.replace("\\", "/")
        if os.path.normpath(alternativa) == os.path.normpath(sys.executable):
            self.assertTrue(self._ok(f'"{alternativa}"'))
        if os.sep == "\\":
            self.assertTrue(self._ok(f'"{sys.executable.replace(chr(92), "/")}"'))

    def test_sin_comillas_solo_si_no_tiene_espacios(self):
        if " " not in sys.executable:
            self.assertTrue(self._ok(sys.executable))
        else:
            self.assertFalse(self._ok(sys.executable))
        autorizado_con_espacio = hp.normalizar_interprete("/ruta con espacio/python")
        self.assertFalse(
            hp._matchea_allowlist(
                "/ruta con espacio/python" + self.SUFIJO, autorizado_con_espacio
            )
        )

    def test_ruta_relativa_rechazada(self):
        # Relativa SIN `..` (no puede rechazarse por el chequeo de `..`): I1.
        relativa = ".venv/Scripts/python.exe"
        autorizado = hp.normalizar_interprete(os.path.join(str(hp.REPO_ROOT), relativa))
        self.assertFalse(hp._matchea_allowlist(f'"{relativa}"' + self.SUFIJO, autorizado))
        self.assertFalse(hp._matchea_allowlist(relativa + self.SUFIJO, autorizado))

    def test_salto_de_linea_cr_y_unicode_en_la_cola_rechazados(self):
        # Importante 1 del ciclo 2: un CR suelto separa sentencias en PowerShell.
        exe = sys.executable
        separadores = tuple(chr(c) for c in (0x0D, 0x0B, 0x0C, 0x85, 0x2028, 0x2029))
        for sep in separadores:
            with self.subTest(sep=repr(sep)):
                cmd = f'"{exe}" tools/ds_guard.py session status --change-id x{sep}Remove-Item y'
                self.assertFalse(hp._matchea_allowlist(cmd, hp.normalizar_interprete(exe)))
        self.assertFalse(hp._matchea_allowlist("git status" + chr(0x0D) + "Remove-Item y", None))

    def test_poc_exacto_de_b1_con_basename_real(self):
        exe = sys.executable
        base = os.path.basename(exe)
        autorizado = hp.normalizar_interprete(exe)
        for cmd in (
            f'{exe};id;/../{base} tools/ds_guard.py session status --change-id x',
            f'"{exe};id;/../{base}" tools/ds_guard.py session status --change-id x',
        ):
            with self.subTest(cmd=cmd):
                self.assertFalse(hp._matchea_allowlist(cmd, autorizado))

    def test_prefijo_powershell(self):
        self.assertTrue(self._ok(f'& "{sys.executable}"'))
        if " " not in sys.executable:
            self.assertTrue(self._ok(f"& {sys.executable}"))
        # exactamente un espacio; otros prefijos no
        self.assertFalse(self._ok(f'&  "{sys.executable}"'))
        self.assertFalse(self._ok(f'&& "{sys.executable}"'))
        self.assertFalse(self._ok(f'& & "{sys.executable}"'))

    def test_inyeccion_en_token_de_interprete_rechazada(self):
        exe = sys.executable
        casos = (
            f"{exe};id;/../python",          # sin comillas, `;` y `..`
            f"{exe}&id&/../x",
            f"{exe}|id|/../x",
            f"$(cmd)/../{exe.lstrip('/')}",
            f"`id`{exe}",
            f"{exe}/../{os.path.basename(exe)}",  # `..` solo
        )
        for token in casos:
            with self.subTest(token=token, comillas=False):
                self.assertFalse(self._ok(token), token)
            with self.subTest(token=token, comillas=True):
                self.assertFalse(self._ok(f'"{token}"'), token)
        # con comillas: `$`, backtick y `..` rechazados aun con ruta correcta
        self.assertFalse(self._ok(f'"{exe}$(id)"'))
        self.assertFalse(self._ok(f'"{exe}`id`"'))
        self.assertFalse(self._ok(f'"/real/python;id;/../python"'))
        self.assertFalse(self._ok(f'"{exe}\n"'))

    def test_token_interprete_seguro_directo(self):
        seguro = hp._token_interprete_seguro
        self.assertTrue(seguro("/usr/bin/python", False))
        self.assertTrue(seguro("C:\\Program Files\\Py\\python.exe", True))
        self.assertFalse(seguro("C:\\Program Files\\Py\\python.exe", False))
        self.assertFalse(seguro("/a/../python", True))
        self.assertFalse(seguro("/a;b/python", False))
        self.assertTrue(seguro("/a;b/python", True))  # `;` entre comillas es literal
        self.assertFalse(seguro("python", True))
        self.assertFalse(seguro("rel/python", True))

    def test_nombre_sin_ruta_o_otro_ejecutable_rechazado(self):
        self.assertFalse(self._ok("python"))
        self.assertFalse(self._ok('"python"'))
        self.assertFalse(self._ok('"/usr/bin/otro"'))
        self.assertFalse(self._ok(f'"{sys.executable}x"'))

    def test_metacaracteres_rechazados(self):
        for sufijo in ("; rm -rf x", " && echo x", " | tee y", " `id`", " $(id)", " > f", "\nls"):
            cmd = f'"{sys.executable}" tools/ds_guard.py session close --change-id x{sufijo}'
            self.assertFalse(hp._matchea_allowlist(cmd, AUTORIZADO), cmd)

    def test_start_nunca_en_allowlist(self):
        cmd = f'"{sys.executable}" tools/ds_guard.py session start --change-id x'
        self.assertFalse(hp._matchea_allowlist(cmd, AUTORIZADO))


class TestEvaluarConRecuperacion(unittest.TestCase):
    def _bloqueos(self, sesion):
        payloads = (
            {"tool_name": "Bash", "tool_input": {"command": "ls"}},
            {"tool_name": "PowerShell", "tool_input": {"command": "dir"}},
            {"tool_name": "Write", "tool_input": {"file_path": "a.txt"}},
            {"tool_name": "Edit", "tool_input": {"file_path": "a.txt"}},
            {"tool_name": "Agent", "tool_input": {"agent_id": "x"}},
            {"tool_name": "SendMessage", "tool_input": {"to": "revisor"}},
            {"tool_name": "SendMessage", "tool_input": {"to": "otro"}},
        )
        for payload in payloads:
            yield payload, hp.evaluar(payload, sesion, AUTORIZADO, CHANGE_ID)

    def test_cada_rama_de_agotado_incluye_el_bloque(self):
        for payload, (permitido, motivo, _mod) in self._bloqueos(_sesion(-10)):
            with self.subTest(tool=payload["tool_name"], input=payload["tool_input"]):
                self.assertFalse(permitido)
                self.assertIn("PRESUPUESTO AGOTADO", motivo)
                self.assertIn(f"session status --change-id {CHANGE_ID}", motivo)
                self.assertIn(f"session close --change-id {CHANGE_ID} --estado pausada", motivo)
                self.assertIn(f"session start --change-id {CHANGE_ID}", motivo)

    def test_mensaje_del_hook_aceptado_por_allowlist(self):
        _p, (_perm, motivo, _m) = next(iter(self._bloqueos(_sesion(-10))))
        for verbo in ("status", "close"):
            for comando in _comandos(motivo, verbo):
                self.assertTrue(hp._matchea_allowlist(comando, AUTORIZADO), comando)

    def test_sin_change_id_no_inventa_comandos(self):
        permitido, motivo, _m = hp.evaluar(
            {"tool_name": "Write", "tool_input": {"file_path": "a"}}, _sesion(-10), AUTORIZADO
        )
        self.assertFalse(permitido)
        self.assertIn("PRESUPUESTO AGOTADO", motivo)
        self.assertNotIn("tools/ds_guard.py", motivo)

    def test_firma_previa_sigue_valida(self):
        permitido, _m, _mod = hp.evaluar(
            {"tool_name": "Write", "tool_input": {"file_path": "a"}}, _sesion(60), AUTORIZADO
        )
        self.assertTrue(permitido)

    def test_allowlist_permitido_con_presupuesto_vencido(self):
        cmd = f'"{sys.executable}" tools/ds_guard.py session close --change-id {CHANGE_ID} --estado pausada'
        permitido, _m, _mod = hp.evaluar(
            {"tool_name": "Bash", "tool_input": {"command": cmd}}, _sesion(-10), AUTORIZADO, CHANGE_ID
        )
        self.assertTrue(permitido)

    def test_session_start_bloqueado_con_presupuesto_vencido(self):
        cmd = f'"{sys.executable}" tools/ds_guard.py session start --change-id {CHANGE_ID}'
        permitido, motivo, _mod = hp.evaluar(
            {"tool_name": "Bash", "tool_input": {"command": cmd}}, _sesion(-10), AUTORIZADO, CHANGE_ID
        )
        self.assertFalse(permitido)
        self.assertIn("PRESUPUESTO AGOTADO", motivo)

    def test_sesion_no_activa_hook_permite_todo(self):
        cmd = f'"{sys.executable}" tools/ds_guard.py session start --change-id {CHANGE_ID}'
        for payload in (
            {"tool_name": "Bash", "tool_input": {"command": cmd}},
            {"tool_name": "Write", "tool_input": {"file_path": "a"}},
            {"tool_name": "Agent", "tool_input": {}},
        ):
            permitido, _m, _mod = hp.evaluar(payload, None, AUTORIZADO, CHANGE_ID)
            self.assertTrue(permitido)


if __name__ == "__main__":
    unittest.main()

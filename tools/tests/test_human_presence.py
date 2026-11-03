"""Tests de `tools/dsguard/human_presence.py` (señal T1 `console_confirmed`).

Ningún test toca la consola real: se usa un `CanalFalso` y fakes de las
llamadas de bajo nivel. El subproceso real verifica que stdin por pipe no
produce T1.
"""

from __future__ import annotations

import ast
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parents[2]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from tools.dsguard import human_presence as hp  # noqa: E402

CONTEXTO = {
    "change_id": "20261009-ejemplo",
    "artefacto": "proposal.md",
    "hash": "sha256/lf/v1:" + "ab12cd34ef56" + "0" * 52,
    "accion": "approve",
}


class CanalFalso(hp.CanalControl):
    """Canal en memoria. `respuesta` puede ser str o una excepción a lanzar."""

    def __init__(self, respuesta):
        self.respuesta = respuesta
        self.escrito: list = []
        self.preparado = False
        self.cerrado = False
        self.timeouts: list = []

    def preparar(self):
        self.preparado = True

    def escribir(self, texto):
        self.escrito.append(texto)

    def leer_linea(self, timeout_s):
        self.timeouts.append(timeout_s)
        if isinstance(self.respuesta, BaseException):
            raise self.respuesta
        return self.respuesta

    def cerrar(self):
        self.cerrado = True

    @property
    def texto(self) -> str:
        return "".join(self.escrito)


class _StdinProhibido:
    """Falla ante cualquier acceso: garantiza que no se lee sys.stdin."""

    def __getattr__(self, nombre):
        raise AssertionError(f"se accedió a sys.stdin.{nombre}")


class _Base(unittest.TestCase):
    def setUp(self):
        hp._CODIGOS_CONSUMIDOS.clear()
        self.addCleanup(hp._CODIGOS_CONSUMIDOS.clear)


class TestExito(_Base):
    def test_exito_con_codigo_inyectado(self):
        canal = CanalFalso("abc234")  # case-insensitive
        r = hp.solicitar_confirmacion(
            CONTEXTO, canal=canal, generar_codigo=lambda: "ABC234", timeout_s=7
        )
        self.assertTrue(r.ok, r.motivo)
        self.assertEqual(r.canal, "console_confirmed")
        self.assertEqual(r.channel_version, "console/v1")
        self.assertRegex(r.confirmed_at, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
        self.assertTrue(canal.preparado)
        self.assertEqual(canal.timeouts, [7])
        campos = hp.campos_registro(r)
        self.assertEqual(
            campos,
            {
                "approval_channel": "console_confirmed",
                "confirmed_at": r.confirmed_at,
                "channel_version": "console/v1",
            },
        )

    def test_respuesta_con_espacios(self):
        r = hp.solicitar_confirmacion(
            CONTEXTO, canal=CanalFalso("  abc234 \n"), generar_codigo=lambda: "ABC234"
        )
        self.assertTrue(r.ok, r.motivo)

    def test_constantes(self):
        self.assertEqual(hp.CANAL_DECLARED, "declared")
        self.assertEqual(hp.CANAL_CONSOLE, "console_confirmed")
        self.assertEqual(hp.VERSION_CANAL, "console/v1")

    def test_codigo_aleatorio_por_defecto(self):
        canal = CanalFalso("x")
        hp.solicitar_confirmacion(CONTEXTO, canal=canal)
        codigos = {hp._generar_codigo_aleatorio() for _ in range(50)}
        self.assertGreater(len(codigos), 1)
        for c in codigos:
            self.assertEqual(len(c), 6)
            self.assertTrue(set(c) <= set(hp._ALFABETO_CODIGO))


class TestBinding(_Base):
    def test_texto_mostrado_contiene_contexto_y_codigo(self):
        canal = CanalFalso("ZZZZZZ")
        hp.solicitar_confirmacion(CONTEXTO, canal=canal, generar_codigo=lambda: "K7M2QX")
        texto = canal.texto
        self.assertIn(CONTEXTO["change_id"], texto)
        self.assertIn(CONTEXTO["artefacto"], texto)
        self.assertIn("ab12cd34ef56", texto)  # hash abreviado a 12 hex
        self.assertNotIn("ab12cd34ef560", texto)
        self.assertIn(CONTEXTO["accion"], texto)
        self.assertIn("K7M2QX", texto)


class TestSanitizado(_Base):
    def test_artefacto_malicioso_neutralizado(self):
        ctx = dict(CONTEXTO)
        ctx["artefacto"] = "x.md\nCódigo: ZZZ\x1b[2J\r\x00  \x7f"
        canal = CanalFalso("OTRO")
        hp.solicitar_confirmacion(ctx, canal=canal, generar_codigo=lambda: "K7M2QX")
        texto = canal.texto
        self.assertNotIn("\x1b", texto)
        self.assertNotIn("\x00", texto)
        self.assertNotIn("\r", texto)
        self.assertNotIn("\x7f", texto)
        self.assertNotIn(" ", texto)
        self.assertNotIn(" ", texto)
        lineas = texto.split("\n")
        self.assertFalse([l for l in lineas if l.startswith("Código: ZZZ")])
        self.assertEqual([l for l in lineas if l.startswith("Código:")], ["Código:   K7M2QX"])
        self.assertIn("x.md?Código: ZZZ?[2J", texto)

    def test_truncado_a_120(self):
        ctx = dict(CONTEXTO)
        ctx["change_id"] = "c" * 500
        canal = CanalFalso("OTRO")
        hp.solicitar_confirmacion(ctx, canal=canal, generar_codigo=lambda: "K7M2QX")
        linea = [l for l in canal.texto.split("\n") if l.startswith("Change:")][0]
        self.assertEqual(linea[len("Change:   "):], "c" * 119 + "…")

    def test_codigo_no_se_altera_por_sanitizado(self):
        ctx = dict(CONTEXTO)
        ctx["accion"] = "approve\n"
        r = hp.solicitar_confirmacion(
            ctx, canal=CanalFalso("ABC234"), generar_codigo=lambda: "ABC234"
        )
        self.assertTrue(r.ok, r.motivo)


class TestExcepciones(_Base):
    def test_keyboard_interrupt(self):
        r = hp.solicitar_confirmacion(CONTEXTO, canal=CanalFalso(KeyboardInterrupt()))
        self.assertFalse(r.ok)
        self.assertIn("interrumpido por el usuario", r.motivo)

    def test_excepciones_inesperadas(self):
        import ctypes

        for exc in (ctypes.ArgumentError("x"), AttributeError("x"), ValueError("x")):
            hp._CODIGOS_CONSUMIDOS.clear()
            r = hp.solicitar_confirmacion(CONTEXTO, canal=CanalFalso(exc))
            self.assertFalse(r.ok)
            self.assertIn("error del canal de control", r.motivo)
            self.assertIn(type(exc).__name__, r.motivo)

    def test_excepcion_al_escribir_o_preparar(self):
        class Malo(CanalFalso):
            def preparar(self):
                raise AttributeError("x")

        r = hp.solicitar_confirmacion(CONTEXTO, canal=Malo("A"))
        self.assertFalse(r.ok)

    def test_canal_propio_se_cierra_ante_excepcion(self):
        canal = CanalFalso(KeyboardInterrupt())
        with mock.patch.object(hp, "canal_consola_real", return_value=(canal, "ok")):
            r = hp.solicitar_confirmacion(CONTEXTO)
        self.assertFalse(r.ok)
        self.assertTrue(canal.cerrado)

    def test_fallo_al_crear_canal(self):
        with mock.patch.object(hp, "canal_consola_real", side_effect=AttributeError("x")):
            r = hp.solicitar_confirmacion(CONTEXTO)
        self.assertFalse(r.ok)
        with mock.patch.object(hp, "canal_consola_real", side_effect=KeyboardInterrupt()):
            r = hp.solicitar_confirmacion(CONTEXTO)
        self.assertFalse(r.ok)
        self.assertIn("interrumpido", r.motivo)


class TestFallos(_Base):
    def test_respuesta_incorrecta(self):
        r = hp.solicitar_confirmacion(
            CONTEXTO, canal=CanalFalso("MALMAL"), generar_codigo=lambda: "ABC234"
        )
        self.assertFalse(r.ok)
        self.assertIsNone(r.canal)
        self.assertIsNone(r.confirmed_at)
        self.assertIn("incorrecta", r.motivo)

    def test_respuesta_con_surrogates_sueltos(self):
        for resp in ("\U0001F600", "\ud83d", "\ude00x"):
            hp._CODIGOS_CONSUMIDOS.clear()
            r = hp.solicitar_confirmacion(
                CONTEXTO, canal=CanalFalso(resp), generar_codigo=lambda: "ABC234"
            )
            self.assertFalse(r.ok, resp)
            self.assertTrue(r.motivo)

    def test_sin_reintentos(self):
        canal = CanalFalso("MALMAL")
        hp.solicitar_confirmacion(CONTEXTO, canal=canal, generar_codigo=lambda: "ABC234")
        self.assertEqual(len(canal.timeouts), 1)

    def test_eof(self):
        r = hp.solicitar_confirmacion(CONTEXTO, canal=CanalFalso(EOFError()))
        self.assertFalse(r.ok)
        self.assertIn("EOF", r.motivo)

    def test_timeout(self):
        r = hp.solicitar_confirmacion(CONTEXTO, canal=CanalFalso(TimeoutError()))
        self.assertFalse(r.ok)
        self.assertIn("timeout", r.motivo)

    def test_error_de_canal(self):
        r = hp.solicitar_confirmacion(CONTEXTO, canal=CanalFalso(OSError("x")))
        self.assertFalse(r.ok)

    def test_contexto_incompleto(self):
        for campo in ("change_id", "artefacto", "hash", "accion"):
            for valor in (None, "", "   ", 5):
                ctx = dict(CONTEXTO)
                ctx[campo] = valor
                canal = CanalFalso("ABC234")
                r = hp.solicitar_confirmacion(
                    ctx, canal=canal, generar_codigo=lambda: "ABC234"
                )
                self.assertFalse(r.ok, (campo, valor))
                self.assertIn("contexto", r.motivo)
                self.assertEqual(canal.escrito, [])
        ctx = dict(CONTEXTO)
        del ctx["hash"]
        self.assertFalse(hp.solicitar_confirmacion(ctx, canal=CanalFalso("A")).ok)
        self.assertFalse(hp.solicitar_confirmacion(None, canal=CanalFalso("A")).ok)

    def test_campos_registro_sin_ok_lanza(self):
        r = hp.solicitar_confirmacion(CONTEXTO, canal=CanalFalso(EOFError()))
        with self.assertRaises(ValueError):
            hp.campos_registro(r)


class TestSingleUse(_Base):
    def test_replay_mismo_codigo(self):
        r1 = hp.solicitar_confirmacion(
            CONTEXTO, canal=CanalFalso("ABC234"), generar_codigo=lambda: "ABC234"
        )
        self.assertTrue(r1.ok)
        canal2 = CanalFalso("ABC234")
        r2 = hp.solicitar_confirmacion(CONTEXTO, canal=canal2, generar_codigo=lambda: "ABC234")
        self.assertFalse(r2.ok)
        self.assertIn("challenge reutilizado", r2.motivo)
        self.assertEqual(canal2.timeouts, [])  # ni siquiera se lee

    def test_codigo_consumido_tras_fallo(self):
        hp.solicitar_confirmacion(
            CONTEXTO, canal=CanalFalso("MAL"), generar_codigo=lambda: "ABC234"
        )
        r = hp.solicitar_confirmacion(
            CONTEXTO, canal=CanalFalso("ABC234"), generar_codigo=lambda: "abc234"
        )
        self.assertFalse(r.ok)
        self.assertIn("reutilizado", r.motivo)


class TestSinDegradar(_Base):
    def test_canal_no_disponible(self):
        with mock.patch.object(hp, "canal_consola_real", return_value=(None, "sin consola")):
            with mock.patch.object(sys, "stdin", _StdinProhibido()):
                r = hp.solicitar_confirmacion(CONTEXTO)
        self.assertFalse(r.ok)
        self.assertIsNone(r.canal)
        self.assertIn("no hay consola de control soportada", r.motivo)
        self.assertIn("sin consola", r.motivo)

    def test_canal_real_se_cierra(self):
        canal = CanalFalso("ABC234")
        with mock.patch.object(hp, "canal_consola_real", return_value=(canal, "ok")):
            r = hp.solicitar_confirmacion(CONTEXTO, generar_codigo=lambda: "ABC234")
        self.assertTrue(r.ok)
        self.assertTrue(canal.cerrado)

    def test_ningun_camino_lee_stdin(self):
        casos = [
            CanalFalso("ABC234"),
            CanalFalso("MAL"),
            CanalFalso(EOFError()),
            CanalFalso(TimeoutError()),
        ]
        with mock.patch.object(sys, "stdin", _StdinProhibido()):
            for canal in casos:
                hp._CODIGOS_CONSUMIDOS.clear()
                hp.solicitar_confirmacion(
                    CONTEXTO, canal=canal, generar_codigo=lambda: "ABC234"
                )
            hp.solicitar_confirmacion({}, canal=CanalFalso("x"))
            with mock.patch.object(hp, "canal_consola_real", return_value=(None, "m")):
                hp.solicitar_confirmacion(CONTEXTO)
            real, _ = hp.canal_consola_real()  # no debe tocar stdin tampoco
            if real is not None:
                real.cerrar()

    def test_subproceso_stdin_pipe_no_produce_t1(self):
        codigo_hijo = (
            "import json\n"
            "from tools.dsguard import human_presence as h\n"
            "c, m = h.canal_consola_real()\n"
            "if c is not None:\n"
            "    c.cerrar()\n"
            "    print('SKIP ' + m)\n"
            "else:\n"
            "    ctx = {'change_id': 'c', 'artefacto': 'a', 'hash': 'h', 'accion': 'x'}\n"
            "    r = h.solicitar_confirmacion(ctx, timeout_s=2, generar_codigo=lambda: 'ABC234')\n"
            "    print(json.dumps({'ok': r.ok, 'canal': r.canal, 'motivo': r.motivo}))\n"
        )
        proc = subprocess.run(
            [sys.executable, "-c", codigo_hijo],
            input="ABC234\n",
            capture_output=True,
            text=True,
            cwd=str(RAIZ),
            timeout=60,
        )
        salida = proc.stdout.strip()
        if salida.startswith("SKIP"):
            self.skipTest("este host expone una consola de control real: " + salida)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        import json

        datos = json.loads(salida.splitlines()[-1])
        self.assertFalse(datos["ok"])
        self.assertIsNone(datos["canal"])
        self.assertIn("no hay consola de control soportada", datos["motivo"])


class TestPrivacidad(_Base):
    def test_campos_registro_solo_tres_claves(self):
        r = hp.solicitar_confirmacion(
            CONTEXTO, canal=CanalFalso("ABC234"), generar_codigo=lambda: "ABC234"
        )
        campos = hp.campos_registro(r)
        self.assertEqual(set(campos), {"approval_channel", "confirmed_at", "channel_version"})
        self.assertNotIn("ABC234", repr(campos))

    def test_resultado_no_contiene_challenge(self):
        r = hp.solicitar_confirmacion(
            CONTEXTO, canal=CanalFalso("ABC234"), generar_codigo=lambda: "ABC234"
        )
        self.assertNotIn("ABC234", repr(r))

    def test_solo_stdlib_sin_imports_tools(self):
        fuente = (RAIZ / "tools" / "dsguard" / "human_presence.py").read_text(encoding="utf-8")
        arbol = ast.parse(fuente)
        modulos = []
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Import):
                modulos += [a.name for a in nodo.names]
            elif isinstance(nodo, ast.ImportFrom):
                self.assertEqual(nodo.level, 0, "import relativo no permitido")
                modulos.append(nodo.module or "")
        self.assertTrue(modulos)
        stdlib = getattr(sys, "stdlib_module_names", None)
        for m in modulos:
            raiz = m.split(".")[0]
            self.assertFalse(raiz == "tools", m)
            if stdlib is not None:
                self.assertIn(raiz, stdlib, m)


class TestTeclas(unittest.TestCase):
    def test_aplicar_tecla(self):
        buf: list = []
        for ch in "AB":
            self.assertIsNone(hp._aplicar_tecla(buf, ch))
        self.assertIsNone(hp._aplicar_tecla(buf, "\x08"))
        self.assertIsNone(hp._aplicar_tecla(buf, "C"))
        self.assertIsNone(hp._aplicar_tecla(buf, "\x1b"))  # control ignorado
        self.assertEqual("".join(buf), "AC")
        self.assertEqual(hp._aplicar_tecla(buf, "\r"), "fin")
        self.assertEqual(hp._aplicar_tecla(buf, "\x03"), "cancelado")
        self.assertIsNone(hp._aplicar_tecla([], "\x08"))


class _Kernel32Falso:
    def __init__(self, ventana=1, handle=7, modo_ok=1):
        self._ventana = ventana
        self._handle = handle
        self._modo_ok = modo_ok
        self.cerrados: list = []
        self.abiertos: list = []

    def GetConsoleWindow(self):
        return self._ventana

    def CreateFileW(self, nombre, *resto):
        self.abiertos.append(nombre)
        return self._handle

    def GetConsoleMode(self, handle, ptr):
        return self._modo_ok

    def CloseHandle(self, handle):
        self.cerrados.append(handle)
        return 1

    def FlushConsoleInputBuffer(self, handle):
        return 1


@unittest.skipUnless(sys.platform == "win32", "contrato Windows")
class TestCanalWindows(unittest.TestCase):
    def _canal(self, k32):
        with mock.patch.object(hp, "_cargar_kernel32", return_value=k32):
            return hp._canal_windows()

    def test_sin_ventana_de_consola_no_disponible(self):
        k32 = _Kernel32Falso(ventana=0)
        canal, motivo = self._canal(k32)
        self.assertIsNone(canal)
        self.assertIn("GetConsoleWindow", motivo)
        self.assertEqual(k32.abiertos, [])  # ni siquiera abre CONIN$

    def test_handle_invalido(self):
        for invalido in (None, 0, -1, 0xFFFFFFFFFFFFFFFF):
            canal, motivo = self._canal(_Kernel32Falso(handle=invalido))
            self.assertIsNone(canal, invalido)
            self.assertIn("CONIN$", motivo)

    def test_modo_de_consola_invalido(self):
        k32 = _Kernel32Falso(modo_ok=0)
        canal, motivo = self._canal(k32)
        self.assertIsNone(canal)
        self.assertIn("modo", motivo)
        self.assertEqual(len(k32.cerrados), 2)

    def test_canal_valido_abre_conin_y_conout(self):
        k32 = _Kernel32Falso()
        canal, _ = self._canal(k32)
        self.assertIsNotNone(canal)
        self.assertEqual(k32.abiertos, ["CONIN$", "CONOUT$"])
        canal.preparar()
        canal.cerrar()
        self.assertEqual(len(k32.cerrados), 2)

    def test_canal_consola_real_delega_en_windows(self):
        with mock.patch.object(hp, "_canal_windows", return_value=(None, "m")) as m:
            self.assertEqual(hp.canal_consola_real(), (None, "m"))
        m.assert_called_once()

    def test_entrada_input_record_tamano(self):
        import ctypes

        self.assertEqual(ctypes.sizeof(hp._estructura_input_record()), 20)

    def test_leer_linea_timeout_sin_bloquear(self):
        class K(_Kernel32Falso):
            def WaitForSingleObject(self, h, ms):
                return hp._WAIT_TIMEOUT

        canal = hp._CanalWindows(K(), 1, 2)
        with self.assertRaises(TimeoutError):
            canal.leer_linea(0.05)

    def test_excepcion_al_abrir_cierra_lo_abierto(self):
        class K(_Kernel32Falso):
            def CreateFileW(self, nombre, *resto):
                if nombre == "CONOUT$":
                    raise AttributeError("x")
                return super().CreateFileW(nombre, *resto)

        k32 = K()
        canal, motivo = self._canal(k32)
        self.assertIsNone(canal)
        self.assertEqual(k32.cerrados, [7])

    def test_eco_backspace_con_buffer_vacio(self):
        canal = hp._CanalWindows(_Kernel32Falso(), 1, 2)
        escritos: list = []
        canal.escribir = escritos.append
        canal._eco("\x08", False)
        self.assertEqual(escritos, [])
        canal._eco("\x08", True)
        self.assertEqual(escritos, ["\b \b"])

    def test_leer_linea_handle_cerrado_es_eof(self):
        class K(_Kernel32Falso):
            def WaitForSingleObject(self, h, ms):
                return 0xFFFFFFFF

        with self.assertRaises(EOFError):
            hp._CanalWindows(K(), 1, 2).leer_linea(1)


@unittest.skipIf(sys.platform == "win32", "contrato POSIX")
class TestCanalPosix(unittest.TestCase):
    def test_sin_tty_no_disponible(self):
        with mock.patch.object(hp.os, "open", side_effect=OSError(6, "ENXIO")):
            canal, motivo = hp._canal_posix()
        self.assertIsNone(canal)
        self.assertIn("/dev/tty", motivo)

    def test_no_es_tty(self):
        with mock.patch.object(hp.os, "open", return_value=9), \
             mock.patch.object(hp.os, "isatty", return_value=False), \
             mock.patch.object(hp.os, "close") as cerrar:
            canal, motivo = hp._canal_posix()
        self.assertIsNone(canal)
        cerrar.assert_called_once_with(9)

    def test_segundo_plano_no_disponible(self):
        with mock.patch.object(hp.os, "open", return_value=9), \
             mock.patch.object(hp.os, "isatty", return_value=True), \
             mock.patch.object(hp.os, "tcgetpgrp", return_value=100), \
             mock.patch.object(hp.os, "getpgrp", return_value=200), \
             mock.patch.object(hp.os, "close"):
            canal, motivo = hp._canal_posix()
        self.assertIsNone(canal)
        self.assertIn("primer plano", motivo)

    def test_primer_plano_disponible(self):
        with mock.patch.object(hp.os, "open", return_value=9), \
             mock.patch.object(hp.os, "isatty", return_value=True), \
             mock.patch.object(hp.os, "tcgetpgrp", return_value=200), \
             mock.patch.object(hp.os, "getpgrp", return_value=200):
            canal, _ = hp._canal_posix()
        self.assertIsNotNone(canal)

    def test_leer_linea_con_pipe(self):
        import os

        r, w = os.pipe()
        try:
            canal = hp._CanalPosix(r)
            os.write(w, b"abc234\n")
            self.assertEqual(canal.leer_linea(2), "abc234")
            with self.assertRaises(TimeoutError):
                canal.leer_linea(0.05)
            os.close(w)
            w = None
            with self.assertRaises(EOFError):
                canal.leer_linea(1)
        finally:
            os.close(r)
            if w is not None:
                os.close(w)


if __name__ == "__main__":
    unittest.main()

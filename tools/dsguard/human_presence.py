"""Señal T1 de presencia interactiva (`console_confirmed`) para aprobaciones.

Contrato (Change 20261009-approval-trust-human-presence, R7-R16):

- Un único punto de entrada, `solicitar_confirmacion(contexto, ...)`, pide una
  confirmación interactiva ligada a UNA operación concreta (change, artefacto,
  hash, acción) mediante un challenge efímero de un solo uso.
- La respuesta se lee SOLO de una consola de control soportada (`CanalControl`),
  nunca de `sys.stdin`, argumentos, archivos ni variables de entorno. `isatty()`
  NO se usa como criterio: en Windows stdin=NUL reporta isatty True aun dentro
  de los runtimes de agente (falso positivo medido).
- Falla cerrado: sin canal soportado, respuesta incorrecta, EOF, timeout,
  contexto incompleto o challenge reutilizado devuelven `ok=False` con un motivo
  claro. Nunca degrada a `declared` ni lee de stdin.
- Solo stdlib; sin imports de `tools.*` ni de ningún provider.

Canales reales:

- Windows: requiere ventana de consola real (`GetConsoleWindow() != 0`), abrir
  `CONIN$`/`CONOUT$` y `GetConsoleMode(CONIN$)` válido. Se leen eventos de
  teclado con `ReadConsoleInputW` esperando con `WaitForSingleObject` (respeta
  el timeout sin bloquear). Sin ventana de consola real (estado observado en los
  runtimes de agente) el canal no está disponible.
- POSIX: `/dev/tty` abierto con `os.open`, `os.isatty(fd)` y
  `os.tcgetpgrp(fd) == os.getpgrp()` (proceso en primer plano). La lectura usa
  `select` + `os.read`.

LÍMITES (obligatorios, spec R2/R36-R38):

- A `console_confirmed` approval means that a declared approval was accompanied
  by an interactive confirmation received through a supported control console
  for that specific operation. It does not prove the identity or authorship of
  the declared user and is not resistant to a deliberately synthesized local
  console input.
- Una aprobación declarada con ese metadata fue acompañada por una señal T1 de
  presencia interactiva; Harmessi NO verificó que la persona declarada haya
  realizado físicamente esa aprobación.
- T1 NO es identidad, autoría, firma, no-repudio ni boundary criptográfico.
- Un PTY sintético (POSIX) o `WriteConsoleInputW` / nueva consola con
  `AttachConsole` (Windows) pueden fabricar la señal; NO se ejercitó
  empíricamente y queda fuera de la garantía T1. Tampoco resiste administrador,
  root, SO comprometido ni malware.
- El discriminante de consola (`GetConsoleWindow() != 0` en Windows;
  `tcgetpgrp == getpgrp` en POSIX) también se cumple para un proceso hijo que
  hereda la consola/terminal del humano (ConPTY, Windows Terminal, mismo process
  group en primer plano en POSIX): la garantía depende de que el runtime del
  agente no comparta la consola con el humano.
- El comportamiento POSIX NO fue verificado en un runtime real (solo por
  análisis y tests con fakes).
- El challenge NO es secreto (el agente puede leer stdout): la garantía proviene
  de la entrada recibida por la consola de control, no de la reserva del código.

Privacidad (R19): no se persiste ni se loguea el challenge, la respuesta, las
teclas, el usuario del SO, handles ni id de terminal. Solo se devuelven los
campos de `campos_registro`.
"""

from __future__ import annotations

import hmac
import os
import secrets
import select
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional

CANAL_DECLARED = "declared"
CANAL_CONSOLE = "console_confirmed"
VERSION_CANAL = "console/v1"

# Alfabeto sin caracteres ambiguos (sin 0/O, 1/I/L).
_ALFABETO_CODIGO = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
_LARGO_CODIGO = 6
_CAMPOS_CONTEXTO = ("change_id", "artefacto", "hash", "accion")

# Registro en memoria de challenges ya emitidos (single-use / anti-replay).
# Solo vive en el proceso; el challenge nunca se persiste.
_CODIGOS_CONSUMIDOS: set = set()
_LOCK_CODIGOS = threading.Lock()


@dataclass(frozen=True)
class ResultadoPresencia:
    ok: bool
    canal: Optional[str]
    confirmed_at: Optional[str]
    channel_version: Optional[str]
    motivo: str


class CanalControl:
    """Abstracción inyectable del canal de control (consola interactiva)."""

    def preparar(self) -> None:
        """Descarta entrada pendiente antes de mostrar el challenge."""

    def escribir(self, texto: str) -> None:
        raise NotImplementedError

    def leer_linea(self, timeout_s: float) -> str:
        """Lee una línea. Lanza EOFError si el canal se cierra y TimeoutError si vence."""
        raise NotImplementedError

    def cerrar(self) -> None:
        """Libera los recursos del canal."""


# ---------------------------------------------------------------------------
# Utilidades puras
# ---------------------------------------------------------------------------

def _ahora_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _generar_codigo_aleatorio() -> str:
    return "".join(secrets.choice(_ALFABETO_CODIGO) for _ in range(_LARGO_CODIGO))


def _normalizar(texto: str) -> str:
    return texto.strip().upper()


def _hash_abreviado(valor: str) -> str:
    """Abrevia el hash a 12 caracteres (descarta un prefijo `algoritmo:` si existe)."""
    return valor.split(":")[-1][:12]


def _validar_contexto(contexto) -> Optional[str]:
    """Devuelve un motivo de error, o None si el contexto es válido."""
    if not isinstance(contexto, dict):
        return "contexto inválido: se esperaba un dict"
    faltan = [
        c for c in _CAMPOS_CONTEXTO
        if not isinstance(contexto.get(c), str) or not contexto[c].strip()
    ]
    if faltan:
        return "contexto incompleto: faltan o están vacíos " + ", ".join(faltan)
    return None


def _fallo(motivo: str) -> ResultadoPresencia:
    return ResultadoPresencia(False, None, None, None, motivo)


_LIMITE_CAMPO = 120


def _sanitizar(texto: str, limite: int = _LIMITE_CAMPO) -> str:
    """Neutraliza caracteres de control/no imprimibles y trunca el campo.

    Evita que un campo del contexto falsee líneas del challenge (saltos de
    línea, secuencias ESC, separadores Unicode de línea/párrafo).
    """
    limpio = "".join(c if c.isprintable() else "?" for c in texto)
    if len(limpio) > limite:
        limpio = limpio[: limite - 1] + "…"
    return limpio


def _texto_challenge(contexto: dict, codigo: str, id_challenge: str) -> str:
    return (
        "\n=== Confirmación de presencia (console_confirmed) ===\n"
        f"Change:   {_sanitizar(contexto['change_id'])}\n"
        f"Artefacto: {_sanitizar(contexto['artefacto'])}\n"
        f"Hash:     {_sanitizar(_hash_abreviado(contexto['hash']))}\n"
        f"Acción:   {_sanitizar(contexto['accion'])}\n"
        f"Id:       {id_challenge}\n"
        f"Código:   {codigo}\n"
        "Escribí el código y presioná Enter para confirmar esta operación.\n"
        "Es una señal de presencia interactiva; no verifica identidad ni autoría.\n"
        "> "
    )


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def solicitar_confirmacion(
    contexto: dict,
    *,
    canal: Optional[CanalControl] = None,
    timeout_s: float = 120,
    generar_codigo: Optional[Callable[[], str]] = None,
) -> ResultadoPresencia:
    """Pide una confirmación interactiva single-use ligada a `contexto`.

    Si `canal` es None se usa la consola real; si no hay una soportada falla
    cerrado (nunca degrada a declared ni lee de stdin). Un canal inyectado lo
    cierra quien lo creó; uno obtenido internamente se cierra acá.
    """
    motivo_ctx = _validar_contexto(contexto)
    if motivo_ctx:
        return _fallo(motivo_ctx)

    propio = False
    if canal is None:
        try:
            canal, motivo = canal_consola_real()
        except KeyboardInterrupt:
            return _fallo("interrumpido por el usuario")
        except Exception as exc:  # noqa: BLE001
            return _fallo(f"error del canal de control: {type(exc).__name__}")
        if canal is None:
            return _fallo(f"no hay consola de control soportada: {motivo}")
        propio = True

    try:
        return _ejecutar_challenge(contexto, canal, timeout_s, generar_codigo)
    finally:
        if propio:
            try:
                canal.cerrar()
            except Exception:  # noqa: BLE001 - el cierre no debe tapar el resultado
                pass


def _ejecutar_challenge(contexto, canal, timeout_s, generar_codigo) -> ResultadoPresencia:
    try:
        codigo = (generar_codigo or _generar_codigo_aleatorio)()
    except KeyboardInterrupt:
        return _fallo("interrumpido por el usuario")
    except Exception as exc:  # noqa: BLE001
        return _fallo(f"error del canal de control: {type(exc).__name__}")
    if not isinstance(codigo, str) or not _normalizar(codigo):
        return _fallo("challenge inválido: código vacío")
    clave = _normalizar(codigo)

    # Se consume al emitirlo: un mismo código no se acepta dos veces, ni siquiera
    # tras un intento fallido (single-use, sin reintentos).
    with _LOCK_CODIGOS:
        if clave in _CODIGOS_CONSUMIDOS:
            return _fallo("challenge reutilizado")
        _CODIGOS_CONSUMIDOS.add(clave)

    id_challenge = secrets.token_hex(4)
    try:
        canal.preparar()
        canal.escribir(_texto_challenge(contexto, codigo, id_challenge))
        respuesta = canal.leer_linea(timeout_s)
    except TimeoutError:
        return _fallo("timeout esperando la confirmación")
    except EOFError:
        return _fallo("el canal de control se cerró (EOF) sin confirmación")
    except KeyboardInterrupt:
        return _fallo("interrumpido por el usuario")
    except Exception as exc:  # noqa: BLE001 - OSError, ArgumentError, AttributeError, ...
        return _fallo(f"error del canal de control: {type(exc).__name__}")

    if not isinstance(respuesta, str):
        return _fallo("respuesta inválida del canal de control")
    try:
        coincide = hmac.compare_digest(
            _normalizar(respuesta).encode("utf-8", errors="surrogatepass"),
            clave.encode("utf-8", errors="surrogatepass"),
        )
    except Exception:  # noqa: BLE001 - p. ej. surrogates sueltos
        return _fallo("respuesta inválida del canal de control")
    if not coincide:
        return _fallo("respuesta incorrecta")

    return ResultadoPresencia(True, CANAL_CONSOLE, _ahora_utc(), VERSION_CANAL, "confirmado")


def campos_registro(resultado: ResultadoPresencia) -> dict:
    """Campos aditivos T1 para la aprobación. Solo si `resultado.ok`."""
    if not isinstance(resultado, ResultadoPresencia) or not resultado.ok:
        raise ValueError("campos_registro requiere un ResultadoPresencia con ok=True")
    return {
        "approval_channel": CANAL_CONSOLE,
        "confirmed_at": resultado.confirmed_at,
        "channel_version": VERSION_CANAL,
    }


def canal_consola_real() -> "tuple[Optional[CanalControl], str]":
    """Devuelve (canal, motivo). Canal None si no hay consola de control soportada."""
    if sys.platform == "win32":
        return _canal_windows()
    return _canal_posix()


# ---------------------------------------------------------------------------
# Windows
# ---------------------------------------------------------------------------

_GENERIC_READ = 0x80000000
_GENERIC_WRITE = 0x40000000
_FILE_SHARE_READ = 0x1
_FILE_SHARE_WRITE = 0x2
_OPEN_EXISTING = 3
_WAIT_OBJECT_0 = 0
_WAIT_TIMEOUT = 0x102
_KEY_EVENT = 0x0001
_MAX_EVENTOS = 16


def _handle_invalido(valor) -> bool:
    if valor is None or valor == 0:
        return True
    return valor in (-1, 0xFFFFFFFF, 0xFFFFFFFFFFFFFFFF)


def _cargar_kernel32():
    """Carga kernel32 con firmas explícitas (aislada para poder parchearla en tests)."""
    import ctypes
    from ctypes import wintypes

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.GetConsoleWindow.restype = wintypes.HWND
    k32.GetConsoleWindow.argtypes = []
    k32.CreateFileW.restype = ctypes.c_void_p
    k32.CreateFileW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
        wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
    ]
    k32.GetConsoleMode.restype = wintypes.BOOL
    k32.GetConsoleMode.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD)]
    k32.WaitForSingleObject.restype = wintypes.DWORD
    k32.WaitForSingleObject.argtypes = [ctypes.c_void_p, wintypes.DWORD]
    k32.FlushConsoleInputBuffer.restype = wintypes.BOOL
    k32.FlushConsoleInputBuffer.argtypes = [ctypes.c_void_p]
    k32.ReadConsoleInputW.restype = wintypes.BOOL
    k32.ReadConsoleInputW.argtypes = [
        ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
    ]
    k32.WriteConsoleW.restype = wintypes.BOOL
    k32.WriteConsoleW.argtypes = [
        ctypes.c_void_p, wintypes.LPCWSTR, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p,
    ]
    k32.CloseHandle.restype = wintypes.BOOL
    k32.CloseHandle.argtypes = [ctypes.c_void_p]
    return k32


def _estructura_input_record():
    """Define INPUT_RECORD (solo KEY_EVENT nos interesa; 20 bytes en total)."""
    import ctypes
    from ctypes import wintypes

    class _KeyEvent(ctypes.Structure):
        _fields_ = [
            ("bKeyDown", wintypes.BOOL),
            ("wRepeatCount", wintypes.WORD),
            ("wVirtualKeyCode", wintypes.WORD),
            ("wVirtualScanCode", wintypes.WORD),
            ("uChar", ctypes.c_wchar),
            ("dwControlKeyState", wintypes.DWORD),
        ]

    class _Evento(ctypes.Union):
        _fields_ = [("KeyEvent", _KeyEvent), ("_relleno", ctypes.c_byte * 16)]

    class _InputRecord(ctypes.Structure):
        _fields_ = [("EventType", wintypes.WORD), ("Event", _Evento)]

    return _InputRecord


def _aplicar_tecla(buffer: list, caracter: str) -> Optional[str]:
    """Aplica un carácter al buffer de línea.

    Devuelve "fin" en Enter, "cancelado" en Ctrl+C / Ctrl+D, o None.
    """
    if caracter in ("\r", "\n"):
        return "fin"
    if caracter in ("\x03", "\x04"):
        return "cancelado"
    if caracter in ("\x08", "\x7f"):
        if buffer:
            buffer.pop()
        return None
    if caracter >= " ":
        buffer.append(caracter)
    return None


class _CanalWindows(CanalControl):
    def __init__(self, k32, hin, hout):
        self._k32 = k32
        self._hin = hin
        self._hout = hout

    def preparar(self) -> None:
        self._k32.FlushConsoleInputBuffer(self._hin)

    def escribir(self, texto: str) -> None:
        import ctypes
        from ctypes import wintypes

        texto = texto.replace("\r\n", "\n").replace("\n", "\r\n")
        escritos = wintypes.DWORD(0)
        if not self._k32.WriteConsoleW(
            self._hout, texto, len(texto), ctypes.byref(escritos), None
        ):
            raise OSError("no se pudo escribir en CONOUT$")

    def leer_linea(self, timeout_s: float) -> str:
        import ctypes
        from ctypes import wintypes

        registro = _estructura_input_record()
        eventos = (registro * _MAX_EVENTOS)()
        leidos = wintypes.DWORD(0)
        buffer: list = []
        limite = time.monotonic() + max(0.0, float(timeout_s))
        while True:
            restante = limite - time.monotonic()
            if restante <= 0:
                raise TimeoutError("timeout")
            espera_ms = max(1, int(min(restante, 0.5) * 1000))
            estado = self._k32.WaitForSingleObject(self._hin, espera_ms)
            if estado == _WAIT_TIMEOUT:
                continue
            if estado != _WAIT_OBJECT_0:
                raise EOFError("CONIN$ cerrado")
            if not self._leer_eventos(eventos, leidos, ctypes):
                raise EOFError("no se pudo leer CONIN$")
            for i in range(leidos.value):
                ev = eventos[i]
                if ev.EventType != _KEY_EVENT or not ev.Event.KeyEvent.bKeyDown:
                    continue
                caracter = ev.Event.KeyEvent.uChar
                habia_texto = bool(buffer)
                accion = _aplicar_tecla(buffer, caracter)
                if accion == "fin":
                    self.escribir("\n")
                    return "".join(buffer)
                if accion == "cancelado":
                    raise EOFError("entrada cancelada")
                self._eco(caracter, habia_texto)

    def _leer_eventos(self, eventos, leidos, ctypes) -> bool:
        # ReadConsoleInputW se resuelve acá para no exigir firma en los fakes.
        fn = getattr(self._k32, "ReadConsoleInputW")
        return bool(fn(self._hin, eventos, _MAX_EVENTOS, ctypes.byref(leidos)))

    def _eco(self, caracter: str, habia_texto: bool) -> None:
        # La lectura por eventos no hace eco: se reproduce de forma manual.
        if caracter in ("\x08", "\x7f"):
            if habia_texto:  # con el buffer vacío no se borra nada
                self.escribir("\b \b")
        elif caracter >= " ":
            self.escribir(caracter)

    def cerrar(self) -> None:
        for h in (self._hin, self._hout):
            try:
                self._k32.CloseHandle(h)
            except Exception:  # noqa: BLE001
                pass


def _canal_windows() -> "tuple[Optional[CanalControl], str]":
    import ctypes
    from ctypes import wintypes

    try:
        k32 = _cargar_kernel32()
    except Exception as exc:  # noqa: BLE001
        return None, f"no se pudo cargar kernel32 ({type(exc).__name__})"

    if not k32.GetConsoleWindow():
        return None, (
            "el proceso no tiene ventana de consola real (GetConsoleWindow() == 0); "
            "es el estado de los runtimes de agente y de la ejecución no interactiva"
        )

    compartir = _FILE_SHARE_READ | _FILE_SHARE_WRITE
    abiertos: list = []

    def _cerrar_abiertos():
        for h in abiertos:
            try:
                k32.CloseHandle(h)
            except Exception:  # noqa: BLE001
                pass

    try:
        hin = k32.CreateFileW(
            "CONIN$", _GENERIC_READ | _GENERIC_WRITE, compartir, None, _OPEN_EXISTING, 0, None
        )
        if _handle_invalido(hin):
            return None, "no se pudo abrir CONIN$"
        abiertos.append(hin)
        hout = k32.CreateFileW(
            "CONOUT$", _GENERIC_READ | _GENERIC_WRITE, compartir, None, _OPEN_EXISTING, 0, None
        )
        if _handle_invalido(hout):
            _cerrar_abiertos()
            return None, "no se pudo abrir CONOUT$"
        abiertos.append(hout)

        modo = wintypes.DWORD(0)
        if not k32.GetConsoleMode(hin, ctypes.byref(modo)):
            _cerrar_abiertos()
            return None, "CONIN$ no tiene un modo de consola válido"
    except Exception as exc:  # noqa: BLE001
        _cerrar_abiertos()
        return None, f"error abriendo la consola de control ({type(exc).__name__})"

    return _CanalWindows(k32, hin, hout), "consola de control Windows disponible"


# ---------------------------------------------------------------------------
# POSIX
# ---------------------------------------------------------------------------

class _CanalPosix(CanalControl):
    def __init__(self, fd: int):
        self._fd = fd

    def preparar(self) -> None:
        try:
            import termios

            termios.tcflush(self._fd, termios.TCIFLUSH)
        except Exception:  # noqa: BLE001 - descartar entrada pendiente es best-effort
            pass

    def escribir(self, texto: str) -> None:
        datos = texto.encode("utf-8", errors="replace")
        while datos:
            n = os.write(self._fd, datos)
            datos = datos[n:]

    def leer_linea(self, timeout_s: float) -> str:
        acumulado = b""
        limite = time.monotonic() + max(0.0, float(timeout_s))
        while True:
            restante = limite - time.monotonic()
            if restante <= 0:
                raise TimeoutError("timeout")
            listos, _, _ = select.select([self._fd], [], [], restante)
            if not listos:
                raise TimeoutError("timeout")
            trozo = os.read(self._fd, 1024)
            if not trozo:
                raise EOFError("/dev/tty cerrado")
            acumulado += trozo
            if b"\n" in acumulado or b"\r" in acumulado:
                linea = acumulado.replace(b"\r", b"\n").split(b"\n", 1)[0]
                return linea.decode("utf-8", errors="replace")

    def cerrar(self) -> None:
        try:
            os.close(self._fd)
        except OSError:
            pass


def _canal_posix() -> "tuple[Optional[CanalControl], str]":
    try:
        fd = os.open("/dev/tty", os.O_RDWR)
    except OSError as exc:
        return None, f"no hay terminal de control (/dev/tty: {type(exc).__name__})"

    try:
        if not os.isatty(fd):
            os.close(fd)
            return None, "/dev/tty no es un terminal"
        if os.tcgetpgrp(fd) != os.getpgrp():
            os.close(fd)
            return None, "el proceso no está en primer plano en el terminal de control"
    except OSError as exc:
        try:
            os.close(fd)
        except OSError:
            pass
        return None, f"no se pudo verificar el terminal de control ({type(exc).__name__})"

    return _CanalPosix(fd), "terminal de control POSIX disponible"

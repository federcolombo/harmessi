"""Conformance de adapters de proveedor de IA (v0.13 Change 3,
`20261021-v013-provider-adapter-conformance`, R1-R6).

Solo-checkout (no se instala en proyectos). Verifica la FORMA de un
`ProviderAdapter` sin credenciales ni red: `shutil.which` y los lanzadores de
procesos de `subprocess` (`run`, `Popen`, `check_output`, `check_call`,
`call`) se reemplazan por dobles de test durante cada chequeo, tanto a nivel
de modulo `subprocess`/`shutil` como dentro del modulo del adapter si este los
importo con `from ... import`. Todo intento de lanzar un proceso se redirige
al doble (que registra la llamada) y nunca ejecuta nada real. No modifica el
contrato de `ProviderAdapter` ni de los adapters.

Tres niveles de soporte, derivados de evidencia (nunca de documentacion):

- `contract-tested`: todos los chequeos de contrato (a)-(f) pasan contra
  dobles. NO prueba el comportamiento de la CLI real.
- `locally-smoke-tested`: ademas, `smoke=True` y el `detect()` REAL (sin
  dobles) devuelve `available=True` con version.
- `live-validated`: `live=True` Y variable `HARMESSI_LIVE_PROVIDER=1` Y una
  invocacion real minima devuelve `ok=True`. Opt-in doble; puede costar.

Los chequeos `smoke_detect_real` y `live_invocacion` son opcionales: si no
se cumplen, el nivel queda en el inmediato inferior (no se anula); un
chequeo de contrato fallido anula el nivel (`nivel_alcanzado = None`).

Los detalles de los reportes nunca copian el mensaje de una excepcion del
adapter: solo su tipo (y codigo, si lo tiene).

Entrada CLI: `python -m tools.providers.conformance [--provider ID] [--smoke]
[--live] [--json]`.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import shutil
import subprocess
import sys
from contextlib import contextmanager
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Callable, Dict, List, Optional
from unittest import mock

from tools.providers.core import (
    InvocationRequest,
    InvocationResult,
    ProviderAdapter,
    ProviderCapabilities,
    ProviderInfo,
    classify_availability_error,
)

NIVELES_SOPORTE = ("contract-tested", "locally-smoke-tested", "live-validated")

VARIABLE_LIVE = "HARMESSI_LIVE_PROVIDER"

EVIDENCIA_FIXTURE = "fixture"
EVIDENCIA_REAL = "real"
EVIDENCIA_NINGUNA = "none"

NOMBRE_SMOKE = "smoke_detect_real"
NOMBRE_LIVE = "live_invocacion"
NOMBRES_OPCIONALES = (NOMBRE_SMOKE, NOMBRE_LIVE)

# Variables de entorno de credenciales plausibles + la propia: se plantan con
# valores sinteticos y NINGUN valor debe aparecer en la llamada al proceso
# falso (args, `env=`, `input=` ni ningun otro kwarg).
VARIABLES_SECRETAS = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "XAI_API_KEY",
    "GROK_API_KEY",
    "CODEX_API_KEY",
    "HARMESSI_CONFORMIDAD_CLAVE",
)
_SECRETOS_SINTETICOS: Dict[str, str] = {
    nombre: f"sk-sintetico-{nombre.lower().replace('_', '-')}-0000000000" for nombre in VARIABLES_SECRETAS
}

_PROMPT_SINTETICO = "prompt sintetico de conformidad"
_MODELO_SINTETICO = "modelo-sintetico"
_ESFUERZO_SINTETICO = "high"

# Originales capturados al importar este modulo: sirven para reconocer, dentro
# del modulo de un adapter, atributos importados con `from subprocess import run`.
_ORIGINALES = {
    ("subprocess", "run"): subprocess.run,
    ("subprocess", "Popen"): subprocess.Popen,
    ("subprocess", "check_output"): subprocess.check_output,
    ("subprocess", "check_call"): subprocess.check_call,
    ("subprocess", "call"): subprocess.call,
    ("shutil", "which"): shutil.which,
}

# Tabla de soporte declarado (R4): provider -> nivel + evidencia textual.
# Ninguno figura `live-validated` ni `locally-smoke-tested`: no hay evidencia
# registrada en CI ni en el repo. El smoke local (detect real) depende del
# host y se reporta en `nivel_alcanzado` cuando se corre con `--smoke`.
SOPORTE_DECLARADO: Dict[str, Dict[str, str]] = {
    "claude_code": {
        "nivel_declarado": "contract-tested",
        "evidencia": (
            "smoke local (detect real) depende del host: se reporta en nivel_alcanzado "
            "cuando se corre con --smoke; sin evidencia registrada en CI"
        ),
    },
    "codex": {
        "nivel_declarado": "contract-tested",
        "evidencia": "contrato contra dobles; el adapter declara no haberse verificado contra la CLI real",
    },
    "gemini": {
        "nivel_declarado": "contract-tested",
        "evidencia": "contrato contra dobles; el adapter declara no haberse verificado contra la CLI real",
    },
    "grok": {
        "nivel_declarado": "contract-tested",
        "evidencia": "contrato contra dobles; el adapter declara no haberse verificado contra la CLI real",
    },
}


@dataclass
class ConformanceReport:
    """Reporte serializable de conformance de un provider (R1)."""

    provider_id: str
    chequeos: List[dict] = field(default_factory=list)
    nivel_alcanzado: Optional[str] = None
    advertencias: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "provider_id": self.provider_id,
            "nivel_alcanzado": self.nivel_alcanzado,
            "advertencias": list(self.advertencias),
            "chequeos": [
                {
                    "nombre": c["nombre"],
                    "ok": bool(c["ok"]),
                    "detalle": c["detalle"],
                    "evidencia": c["evidencia"],
                }
                for c in self.chequeos
            ],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, ensure_ascii=False, indent=2)


def _describir_excepcion(exc: BaseException) -> str:
    """Solo tipo (y codigo si lo tiene): nunca `str(exc)` (L1)."""
    codigo = getattr(exc, "code", None)
    if isinstance(codigo, str):
        return f"{type(exc).__name__}({codigo})"
    return type(exc).__name__


# ---------------------------------------------------------------------------
# Dobles
# ---------------------------------------------------------------------------


def _proceso_falso(returncode: int = 0, stdout: str = "", stderr: str = "") -> SimpleNamespace:
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


def _doble_popen(run: mock.MagicMock) -> mock.MagicMock:
    def popen(*args, **kwargs):
        r = run(*args, **kwargs)
        proc = mock.MagicMock()
        proc.returncode = r.returncode
        proc.communicate.return_value = (r.stdout, r.stderr)
        proc.wait.return_value = r.returncode
        proc.poll.return_value = r.returncode
        proc.__enter__.return_value = proc
        return proc

    return mock.MagicMock(side_effect=popen)


def _doble_check_output(run: mock.MagicMock) -> mock.MagicMock:
    def check_output(*args, **kwargs):
        r = run(*args, **kwargs)
        if r.returncode:
            raise subprocess.CalledProcessError(r.returncode, args[0] if args else "", r.stdout, r.stderr)
        return r.stdout

    return mock.MagicMock(side_effect=check_output)


def _doble_check_call(run: mock.MagicMock) -> mock.MagicMock:
    def check_call(*args, **kwargs):
        r = run(*args, **kwargs)
        if r.returncode:
            raise subprocess.CalledProcessError(r.returncode, args[0] if args else "")
        return 0

    return mock.MagicMock(side_effect=check_call)


def _doble_call(run: mock.MagicMock) -> mock.MagicMock:
    return mock.MagicMock(side_effect=lambda *args, **kwargs: run(*args, **kwargs).returncode)


@contextmanager
def _dobles(cli_presente: bool, cli_command: str, run: mock.MagicMock, adapter=None):
    """Reemplaza `shutil.which` y todos los lanzadores de `subprocess` (a nivel
    de modulo y, si el adapter los importo con from-import, dentro del modulo
    del adapter); todos delegan en `run`, que registra las llamadas. Planta
    secretos sinteticos en el entorno."""
    ruta = f"/ruta/sintetica/{cli_command}" if cli_presente else None
    dobles = {
        ("subprocess", "run"): run,
        ("subprocess", "Popen"): _doble_popen(run),
        ("subprocess", "check_output"): _doble_check_output(run),
        ("subprocess", "check_call"): _doble_check_call(run),
        ("subprocess", "call"): _doble_call(run),
        ("shutil", "which"): mock.MagicMock(return_value=ruta),
    }
    with contextlib.ExitStack() as pila:
        for (modulo, atributo), doble in dobles.items():
            pila.enter_context(mock.patch(f"{modulo}.{atributo}", doble))
        modulo_adapter = sys.modules.get(getattr(type(adapter), "__module__", "")) if adapter is not None else None
        if modulo_adapter is not None and modulo_adapter not in (subprocess, shutil):
            for nombre, valor in list(vars(modulo_adapter).items()):
                for clave, original in _ORIGINALES.items():
                    if valor is original:
                        pila.enter_context(mock.patch.object(modulo_adapter, nombre, dobles[clave]))
                        break
        pila.enter_context(mock.patch.dict(os.environ, _SECRETOS_SINTETICOS))
        yield


def _nuevo_run(**kwargs) -> mock.MagicMock:
    return mock.MagicMock(**kwargs)


def _comandos(run: mock.MagicMock) -> List[list]:
    comandos = []
    for llamada in run.call_args_list:
        if llamada.args:
            comandos.append(list(llamada.args[0]))
        elif "args" in llamada.kwargs:
            comandos.append(list(llamada.kwargs["args"]))
    return comandos


def _secretos_en_llamadas(run: mock.MagicMock) -> List[str]:
    """Nombres de variables cuyo valor sintetico aparece en ALGUNA llamada
    (args y kwargs completos: `env=`, `input=`, etc.)."""
    filtradas = set()
    for llamada in run.call_args_list:
        texto = repr(llamada.args) + repr(sorted(llamada.kwargs.items(), key=lambda kv: kv[0]))
        for nombre, valor in _SECRETOS_SINTETICOS.items():
            if valor in texto:
                filtradas.add(nombre)
    return sorted(filtradas)


# ---------------------------------------------------------------------------
# Chequeos de contrato (a)-(f): firma (adapter, advertencias) -> (ok, detalle)
# ---------------------------------------------------------------------------


def _chequeo_forma(adapter, advertencias) -> tuple:
    if not isinstance(adapter, ProviderAdapter):
        return False, "no es instancia de ProviderAdapter"
    for atributo in ("provider_id", "cli_command", "display_name"):
        valor = getattr(adapter, atributo, None)
        if not isinstance(valor, str) or not valor.strip():
            return False, f"atributo '{atributo}' ausente o vacio"
    return True, "subclase de ProviderAdapter con provider_id/cli_command/display_name no vacios"


def _chequeo_detect_ausente(adapter, advertencias) -> tuple:
    run = _nuevo_run()
    with _dobles(False, adapter.cli_command, run, adapter):
        info = adapter.detect()
    if not isinstance(info, ProviderInfo):
        return False, "detect() no devolvio ProviderInfo"
    if info.available is not False:
        return False, "detect() con CLI ausente devolvio available distinto de False"
    if run.call_count:
        return False, "detect() con CLI ausente intento lanzar un proceso"
    return True, "detect() con CLI ausente => available=False sin excepcion ni proceso"


def _chequeo_detect_version(adapter, advertencias) -> tuple:
    salida = f"{adapter.cli_command} 9.9.9-sintetica"
    run = _nuevo_run(return_value=_proceso_falso(0, salida + "\n", ""))
    with _dobles(True, adapter.cli_command, run, adapter):
        info = adapter.detect()
    if not isinstance(info, ProviderInfo):
        return False, "detect() no devolvio ProviderInfo"
    if not info.available:
        return False, "detect() con --version simulado no devolvio available=True"
    if not isinstance(info.version, str) or not info.version.strip():
        return False, "version no parseada (vacia)"
    comandos = _comandos(run)
    if not comandos or comandos[0][0] != adapter.cli_command or "--version" not in comandos[0]:
        return False, "detect() no consulto '<cli> --version'"
    filtradas = _secretos_en_llamadas(run)
    if filtradas:
        return False, f"detect() filtra secretos del entorno al proceso: {filtradas}"
    return True, f"version parseada: {info.version!r}"


def _armar_request() -> InvocationRequest:
    return InvocationRequest(
        prompt=_PROMPT_SINTETICO,
        role="lead",
        model=_MODELO_SINTETICO,
        effort=_ESFUERZO_SINTETICO,
        timeout_s=5.0,
    )


def _chequeo_invoke_contrato(adapter, advertencias) -> tuple:
    run = _nuevo_run(return_value=_proceso_falso(0, "respuesta sintetica", ""))
    with _dobles(True, adapter.cli_command, run, adapter):
        capacidades = adapter.detect().capabilities
        run.reset_mock()
        resultado = adapter.invoke(_armar_request())
    comandos = _comandos(run)
    if len(comandos) != 1:
        return False, f"invoke() debia ejecutar 1 comando, ejecuto {len(comandos)}"
    cmd = comandos[0]
    if not all(isinstance(parte, str) for parte in cmd):
        return False, "el comando contiene elementos que no son str"
    if cmd[0] != adapter.cli_command:
        return False, "el comando no empieza por cli_command"
    if _PROMPT_SINTETICO not in cmd:
        return False, "el comando no contiene el prompt"
    filtradas = _secretos_en_llamadas(run)
    if filtradas:
        return False, f"secretos del entorno presentes en la llamada al proceso (cmd/env/input): {filtradas}"
    if run.call_args.kwargs.get("shell"):
        return False, "invoke() uso shell=True"
    if getattr(capacidades, "thinking_effort", False) and _ESFUERZO_SINTETICO not in cmd:
        return False, "el adapter declara thinking_effort pero no paso el esfuerzo"
    if _MODELO_SINTETICO in cmd:
        indice = cmd.index(_MODELO_SINTETICO)
        if indice == 0 or not cmd[indice - 1].startswith("-"):
            return False, "el modelo se paso sin flag"
    else:
        advertencias.append(f"{adapter.provider_id}: ignora model")
    if _ESFUERZO_SINTETICO not in cmd and not getattr(capacidades, "thinking_effort", False):
        advertencias.append(f"{adapter.provider_id}: ignora effort")
    if not isinstance(resultado, InvocationResult):
        return False, "invoke() no devolvio InvocationResult"
    if not (resultado.ok is True and resultado.exit_code == 0 and resultado.availability_error is None):
        return False, "invoke() con proceso exitoso no devolvio ok=True/exit_code=0/availability_error=None"
    if resultado.provider_id != adapter.provider_id:
        return False, "provider_id del resultado no coincide con el del adapter"
    return True, "comando valido: empieza por cli_command, contiene el prompt, sin secretos"


def _invocar_con_fallo(adapter, run: mock.MagicMock) -> InvocationResult:
    with _dobles(True, adapter.cli_command, run, adapter):
        return adapter.invoke(_armar_request())


def _chequeo_fallas(adapter, advertencias) -> tuple:
    casos_stderr = (
        ("429 rate limit exceeded", "quota"),
        ("error: not logged in", "unauthenticated"),
        ("error semantico del prompt", None),
    )
    for stderr, esperado in casos_stderr:
        if classify_availability_error(1, stderr) != esperado:
            return False, "classify_availability_error no coincide con el caso base (core roto)"
        resultado = _invocar_con_fallo(adapter, _nuevo_run(return_value=_proceso_falso(1, "", stderr)))
        if resultado.ok is not False:
            return False, f"exit 1 con stderr {stderr!r} no dio ok=False"
        if resultado.availability_error != esperado:
            return False, (
                f"availability_error {resultado.availability_error!r} != {esperado!r} para stderr {stderr!r}"
            )
    resultado_os = _invocar_con_fallo(adapter, _nuevo_run(side_effect=OSError("fallo sintetico")))
    if resultado_os.ok is not False:
        return False, "OSError no dio ok=False"
    resultado_to = _invocar_con_fallo(
        adapter, _nuevo_run(side_effect=subprocess.TimeoutExpired(cmd=adapter.cli_command, timeout=1))
    )
    if resultado_to.ok is not False:
        return False, "timeout no dio ok=False"
    return True, "cuota/autenticacion/otro coherentes con classify_availability_error; OSError y timeout => ok=False"


def _chequeo_forma_info(adapter, advertencias) -> tuple:
    run = _nuevo_run(return_value=_proceso_falso(0, f"{adapter.cli_command} 9.9.9-sintetica\n", ""))
    infos = []
    with _dobles(True, adapter.cli_command, run, adapter):
        infos.append(adapter.detect())
    with _dobles(False, adapter.cli_command, _nuevo_run(), adapter):
        infos.append(adapter.detect())
    for info in infos:
        if not isinstance(info, ProviderInfo):
            return False, "detect() no devolvio ProviderInfo"
        if not isinstance(info.capabilities, ProviderCapabilities):
            return False, "capabilities no es ProviderCapabilities"
        for nombre in ("streaming", "tool_use", "thinking_effort", "handoff"):
            if not isinstance(getattr(info.capabilities, nombre, None), bool):
                return False, f"capacidad '{nombre}' no es bool (o es None)"
        if info.provider_id != adapter.provider_id or info.cli_command != adapter.cli_command:
            return False, "ProviderInfo no coincide con provider_id/cli_command del adapter"
        if not isinstance(info.detail, str) or not info.detail:
            return False, "ProviderInfo.detail vacio"
        if info.authenticated is not None and not isinstance(info.authenticated, bool):
            return False, "authenticated debe ser None o bool"
    return True, "ProviderInfo y ProviderCapabilities con forma valida (capacidades bool, nunca None)"


_CHEQUEOS_CONTRATO: List[tuple] = [
    ("forma_adapter", _chequeo_forma),
    ("detect_cli_ausente", _chequeo_detect_ausente),
    ("detect_version", _chequeo_detect_version),
    ("invoke_contrato_comando", _chequeo_invoke_contrato),
    ("fallas_clasificadas", _chequeo_fallas),
    ("forma_info_capacidades", _chequeo_forma_info),
]


def _ejecutar_chequeo(nombre: str, fn: Callable, adapter, evidencia: str, advertencias: List[str]) -> dict:
    try:
        ok, detalle = fn(adapter, advertencias)
    except (Exception, SystemExit) as exc:  # noqa: BLE001 - L2: KeyboardInterrupt se propaga
        ok, detalle = False, f"excepcion {_describir_excepcion(exc)}"
    return {"nombre": nombre, "ok": bool(ok), "detalle": detalle, "evidencia": evidencia}


# ---------------------------------------------------------------------------
# Smoke y live (opt-in)
# ---------------------------------------------------------------------------


def _chequeo_smoke(adapter, advertencias) -> tuple:
    info = adapter.detect()  # SIN dobles: usa la CLI real del host
    if not info.available:
        return False, f"CLI '{adapter.cli_command}' no disponible en este host: sin evidencia de smoke"
    if not isinstance(info.version, str) or not info.version.strip():
        return False, "detect() real disponible pero sin version"
    return True, f"detect() real: available=True, version={info.version!r}"


def _chequeo_live(adapter, advertencias) -> tuple:
    request = InvocationRequest(prompt="Responde solo: ok", role="lead", timeout_s=60.0)
    resultado = adapter.invoke(request)  # invocacion REAL
    if resultado.ok:
        return True, "invocacion real minima con ok=True"
    return False, f"invocacion real fallida (exit={resultado.exit_code}, error={resultado.availability_error})"


def live_habilitado(entorno: Optional[dict] = None) -> bool:
    """True solo si `HARMESSI_LIVE_PROVIDER=1` en el entorno."""
    entorno = os.environ if entorno is None else entorno
    return entorno.get(VARIABLE_LIVE) == "1"


# ---------------------------------------------------------------------------
# API publica
# ---------------------------------------------------------------------------


def verificar_conformidad(adapter, *, smoke: bool = False, live: bool = False) -> ConformanceReport:
    """Corre los chequeos de contrato (a)-(f) sin credenciales ni red y, solo
    si se piden explicitamente, el smoke local y el live opt-in. Nunca lanza
    por un adapter roto: lo registra como chequeo fallido."""
    provider_id = getattr(adapter, "provider_id", None) or type(adapter).__name__
    reporte = ConformanceReport(provider_id=str(provider_id))
    for nombre, fn in _CHEQUEOS_CONTRATO:
        reporte.chequeos.append(_ejecutar_chequeo(nombre, fn, adapter, EVIDENCIA_FIXTURE, reporte.advertencias))
    reporte.advertencias = sorted(set(reporte.advertencias))

    contrato_ok = all(c["ok"] for c in reporte.chequeos)
    if not contrato_ok:
        reporte.nivel_alcanzado = None
        return reporte
    nivel = NIVELES_SOPORTE[0]

    if smoke:
        chequeo = _ejecutar_chequeo(NOMBRE_SMOKE, _chequeo_smoke, adapter, EVIDENCIA_REAL, [])
        reporte.chequeos.append(chequeo)
        if chequeo["ok"]:
            nivel = NIVELES_SOPORTE[1]

    if live:
        if not live_habilitado():
            # L4: no hubo ejecucion real => evidencia "none", nunca "real".
            reporte.chequeos.append(
                {
                    "nombre": NOMBRE_LIVE,
                    "ok": False,
                    "detalle": f"omitido: falta {VARIABLE_LIVE}=1; no se invoco la CLI",
                    "evidencia": EVIDENCIA_NINGUNA,
                }
            )
        else:
            chequeo = _ejecutar_chequeo(NOMBRE_LIVE, _chequeo_live, adapter, EVIDENCIA_REAL, [])
            reporte.chequeos.append(chequeo)
            if chequeo["ok"]:
                nivel = NIVELES_SOPORTE[2]

    reporte.nivel_alcanzado = nivel
    return reporte


def nivel_declarado(provider_id: str) -> Optional[str]:
    entrada = SOPORTE_DECLARADO.get(provider_id)
    return entrada["nivel_declarado"] if entrada else None


# ---------------------------------------------------------------------------
# CLI (R6)
# ---------------------------------------------------------------------------


def _consola_segura() -> None:
    """Best-effort (v0.13 R8): con consola no UTF-8 los caracteres no
    representables se reemplazan en vez de lanzar `UnicodeEncodeError`."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


def main(argv: Optional[List[str]] = None) -> int:
    _consola_segura()
    parser = argparse.ArgumentParser(
        prog="python -m tools.providers.conformance",
        description="Conformance de adapters de proveedor (sin credenciales por defecto).",
    )
    parser.add_argument("--provider", default=None, help="id de un provider registrado (default: todos)")
    parser.add_argument("--smoke", action="store_true", help="agrega el detect() real del host")
    parser.add_argument("--live", action="store_true", help=f"invocacion real (requiere {VARIABLE_LIVE}=1)")
    parser.add_argument("--json", action="store_true", help="salida JSON determinista")
    args = parser.parse_args(argv)

    if args.live and not live_habilitado():
        print(
            f"--live requiere la variable de entorno {VARIABLE_LIVE}=1; no se invoco ninguna CLI.",
            file=sys.stderr,
        )
        return 2

    from tools.providers import PROVIDER_REGISTRY

    if args.provider is not None:
        if args.provider not in PROVIDER_REGISTRY:
            print(f"provider desconocido: {args.provider!r}", file=sys.stderr)
            return 2
        adapters = [PROVIDER_REGISTRY[args.provider]]
    else:
        adapters = [PROVIDER_REGISTRY[clave] for clave in sorted(PROVIDER_REGISTRY)]

    reportes = [verificar_conformidad(a, smoke=args.smoke, live=args.live) for a in adapters]
    if args.json:
        print(json.dumps([r.to_dict() for r in reportes], sort_keys=True, ensure_ascii=False, indent=2))
    else:
        for reporte in reportes:
            print(f"{reporte.provider_id}: nivel_alcanzado={reporte.nivel_alcanzado}")
            for c in reporte.chequeos:
                marca = "OK  " if c["ok"] else "FAIL"
                print(f"  [{marca}] {c['nombre']} ({c['evidencia']}): {c['detalle']}")
            for advertencia in reporte.advertencias:
                print(f"  [WARN] {advertencia}")
    return 0 if all(r.nivel_alcanzado is not None for r in reportes) else 1


if __name__ == "__main__":
    raise SystemExit(main())

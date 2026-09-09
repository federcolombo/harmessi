"""Ejecución real de un notebook vía `nbclient` (Sesión 3 de
`20260907-notebook-runner-controlado`).

Nada acá calcula diff de filesystem, cuarentena de escrituras, hash de
integridad de entradas, heurística de holdout, ni lock de concurrencia — eso
es de sesiones futuras (`spec.md` requisitos 5(e), 6, 9, 14). Este módulo solo
resuelve la ejecución en sí: motor `nbclient`, timeout duro por celda, y
captura estructurada de resultado.

## API

`ejecutar_notebook(notebook_path, timeout_segundos, kernel_name="python3",
cwd=None, espera_apagado_segundos=5.0) -> ResultadoEjecucion`

Devuelve un `ResultadoEjecucion` (dataclass) con, como mínimo:

- `exit_ok: bool` — `True` solo si todas las celdas ejecutaron sin excepción
  y no hubo timeout. `timeout_alcanzado=True` implica siempre `exit_ok=False`,
  sin excepción (`spec.md` requisito 7, textual).
- `duracion_segundos: float` — desde el inicio de `client.execute()` hasta
  *después* del apagado forzado del kernel (`_apagar_kernel_forzado`) y la
  espera de confirmación de muerte del proceso (`_kernel_murio_tras_espera`);
  no es solo el tiempo de ejecución de las celdas. En una corrida con
  timeout, incluye también el grace period de `terminate()`/`kill()` del
  respaldo con `psutil` y el poll de confirmación posterior.
- `stdout_resumen` / `stderr_resumen: str` — concatenación de los outputs de
  stream `stdout`/`stderr` de las celdas ejecutadas, mismo estilo que
  Jupyter/`nbclient.exceptions.stream_output_msg`.
- `timeout_alcanzado: bool`.
- `posible_proceso_huerfano: bool` — `True` si, tras un timeout, no se pudo
  confirmar (best-effort, con `psutil`) que el proceso del kernel ya murió.
- `error_info: Optional[dict]` — si una celda lanzó una excepción capturada
  vía `nbclient.exceptions.CellExecutionError`, sus `ename`/`evalue`/
  `traceback`. La función nunca deja propagar esa excepción (ni
  `CellTimeoutError`): las captura y las traduce a campos del resultado.

## Motor: `nbclient`, no `jupyter_client` de bajo nivel

Decisión ya aprobada (condición 2 de la aprobación del usuario, 2026-09-07;
`design.md` sección 6). `nbclient.NotebookClient` administra el ciclo de vida
completo del kernel.

## Timeout: por celda, no global

El parámetro `timeout` de `NotebookClient` (aquí, `timeout_segundos`) es un
timeout **por celda**, no la suma total del notebook. Para un notebook con
muchas celdas rápidas, la duración total podría superar `timeout_segundos`
sin que ninguna celda individual dispare `CellTimeoutError`. Esta es una
limitación conocida y aceptada para esta sesión (notebooks sintéticos de 2-3
celdas) — no se resuelve acá con un mecanismo adicional de timeout global
(threading/watchdog propio); eso sería alcance nuevo no pedido en esta
sesión.

## Apagado forzado del kernel: `jupyter_client` + respaldo con `psutil`

`NotebookClient.execute()` se invoca con `cleanup_kc=False` para desactivar
el cleanup automático de `nbclient` (que, por defecto, apagaría el kernel él
solo dentro de `setup_kernel`/`_cleanup_kernel` antes de que este módulo
pueda intervenir). Esto deja el kernel vivo y `client.km` accesible incluso
tras una excepción, para poder:

1. Capturar el pid real del proceso del kernel, vía
   `client.km.provisioner.pid` (o `client.km.provisioner.process.pid` como
   fallback) — la API expuesta por `jupyter_client.KernelManager` en la
   versión instalada (`jupyter_client==8.10.0`) no expone el pid
   directamente en el manager, sino en su `provisioner`
   (`jupyter_client.provisioning.local_provisioner.LocalProvisioner`).
2. Forzar el apagado explícito con `client.km.shutdown_kernel(now=True)` —
   API real de `KernelManager` (confirmada leyendo
   `jupyter_client/manager.py` de la instalación real:
   `shutdown_kernel = run_sync(_async_shutdown_kernel)`, con `now=True`
   saltando la espera de apagado ordenado) — en vez de confiar en el cleanup
   automático de `nbclient`/`jupyter_client`.
3. **Respaldo con `psutil`, siempre.** Leyendo `jupyter_client/manager.py` en
   detalle: `_async_shutdown_kernel(now=True)` internamente hace
   `_async_interrupt_kernel()` (manda una señal/evento de interrupción
   *antes* de matar, incluso con `now=True`) y luego `_async_kill_kernel()`
   (que sí espera de forma bloqueante, vía `Popen.wait()`, a que el proceso
   sea reapeado). En teoría, si esa llamada retorna sin excepción, el
   proceso ya está muerto y reapeado. En la práctica, en Windows se observó
   `PermissionError: el proceso no tiene acceso al archivo` al borrar el
   `TemporaryDirectory` raíz del test *inmediatamente después* de que
   `ejecutar_notebook` retorna — con el directorio usado como `cwd` real del
   proceso del kernel (ver sección `cwd` más abajo). Dos causas posibles, no
   excluyentes entre sí, y ambas fuera de este módulo: (a) esa llamada vive
   dentro de un `try: ... except Exception: pass` — si algo en la capa
   asyncio/zmq de Windows la hace fallar a mitad de camino (los propios
   warnings de "Proactor event loop does not implement add_reader" que
   aparecen en la corrida son evidencia de fricción real en esa capa), el
   kill nunca llega a ejecutarse y el `except` lo esconde en silencio; (b)
   aun sin excepción, hay una ventana de carrera en Windows entre "el pid ya
   no existe" y "el SO terminó de liberar el handle del directorio que ese
   proceso tenía como cwd". Por eso, además de (2), este módulo agrega
   siempre un respaldo a nivel de proceso del SO con `psutil`:
   `Process.terminate()` y, si sigue vivo tras un grace period corto,
   `Process.kill()` — y espera (poll acotado sobre `psutil.pid_exists`,
   mismo mecanismo que ya existía para el caso de timeout) a que el pid esté
   confirmado muerto antes de que `ejecutar_notebook` retorne. Esto corre en
   los **3 caminos** (éxito, error de celda, timeout), no solo timeout, que
   es lo que hace falta para no dejarle al llamador (p. ej. un test que va a
   borrar su propio tempdir) un proceso todavía vivo con ese directorio como
   cwd.
4. La verificación con `psutil` de "posible proceso huérfano"
   (`posible_proceso_huerfano=True`) sigue aplicando semánticamente solo al
   caso de timeout (`spec.md` requisito 7) — en los otros dos caminos, si
   pese a `terminate()`+`kill()` no se puede confirmar la muerte del
   proceso, no se marca ese campo (no es su alcance), pero el intento de
   matarlo igual se hizo, para no dejar kernels colgados entre corridas
   reales.

## `cwd`

Fijado a la raíz del repo (vía `dsguard.repo.find_repo_root`, resuelta a
partir de la ubicación de este propio módulo — no de la ubicación del
notebook a ejecutar, que en los tests es un archivo sintético en un
directorio temporal). Puede pasarse explícito por parámetro para no depender
de resolución de Git en los tests.

No se invoca un shell del sistema operativo para lanzar el kernel (eso lo
delega `nbclient`/`jupyter_client` vía su propio mecanismo de subproceso, sin
intérprete de comandos de por medio); ninguna operación de control de
versiones (agregar, confirmar, reiniciar ni descartar cambios) aparece en el
vocabulario de este módulo — no invoca `git` en absoluto.
"""
from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import nbformat
from nbclient import NotebookClient
from nbclient.exceptions import CellExecutionError, CellTimeoutError

try:
    import psutil

    _PSUTIL_DISPONIBLE = True
except ImportError:  # pragma: no cover - psutil ya está instalado en el .venv
    psutil = None  # type: ignore[assignment]
    _PSUTIL_DISPONIBLE = False

TOOLS_DIR = Path(__file__).resolve().parents[1]
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from dsguard.repo import find_repo_root  # noqa: E402

KERNEL_NAME_POR_DEFECTO = "python3"
ESPERA_APAGADO_SEGUNDOS_POR_DEFECTO = 5.0

# Grace period corto para el respaldo con `psutil` (`terminate()` -> `kill()`)
# a nivel de proceso del SO. Es deliberadamente más corto que
# `espera_apagado_segundos` (que gobierna la confirmación final de "el pid ya
# no existe", ver `_kernel_murio_tras_espera"): acá solo se trata de darle al
# proceso una chance de salir ordenadamente antes de matarlo a la fuerza.
ESPERA_TERMINATE_KILL_SEGUNDOS = 2.0


@dataclass
class ResultadoEjecucion:
    """Resultado estructurado de una corrida de `ejecutar_notebook`. Ver
    docstring del módulo para el significado de cada campo."""

    exit_ok: bool
    duracion_segundos: float
    stdout_resumen: str
    stderr_resumen: str
    timeout_alcanzado: bool
    posible_proceso_huerfano: bool
    error_info: Optional[dict] = None


# --- Helpers internos ------------------------------------------------------------

def _raiz_repo_por_defecto() -> Path:
    """Raíz del repo que contiene a este propio módulo, no al notebook
    a ejecutar (que en los tests es sintético, en un directorio temporal
    fuera de cualquier repo Git)."""
    return find_repo_root(Path(__file__).resolve())


def _resumen_stream(nb, nombre: str) -> str:
    """Concatenación de los outputs de stream `nombre` (`"stdout"` o
    `"stderr"`) de todas las celdas de código del notebook, en orden."""
    partes = []
    for cell in nb.get("cells", []):
        if cell.get("cell_type") != "code":
            continue
        for output in cell.get("outputs", []) or []:
            if output.get("output_type") == "stream" and output.get("name") == nombre:
                partes.append(output.get("text", ""))
    return "".join(partes)


def _obtener_pid_kernel(km) -> Optional[int]:
    """Pid del proceso del kernel, vía el `provisioner` del `KernelManager`
    (`jupyter_client==8.10.0` no expone el pid directamente en el manager).
    Best-effort: devuelve `None` si no se puede determinar."""
    if km is None:
        return None
    provisioner = getattr(km, "provisioner", None)
    if provisioner is None:
        return None
    pid = getattr(provisioner, "pid", None)
    if isinstance(pid, int):
        return pid
    proceso = getattr(provisioner, "process", None)
    pid = getattr(proceso, "pid", None)
    return pid if isinstance(pid, int) else None


def _apagar_kernel_forzado(
    client: NotebookClient,
    espera_terminate_kill_segundos: float = ESPERA_TERMINATE_KILL_SEGUNDOS,
) -> tuple[Optional[int], list[str]]:
    """Apaga el kernel explícitamente (`km.shutdown_kernel(now=True)`) en vez
    de confiar en el cleanup automático de `nbclient` (por eso `execute()` se
    invoca con `cleanup_kc=False`), y además aplica un respaldo a nivel de
    proceso del SO con `psutil` (`terminate()` -> `kill()` tras un grace
    period corto) — ver docstring del módulo, sección "Apagado forzado del
    kernel", para el porqué de este respaldo (no alcanza con confiar en que
    `shutdown_kernel(now=True)` haya matado y reapeado el proceso).

    Todos los pasos de esta función son best-effort: ninguna excepción de
    limpieza se propaga (el runner nunca debe tumbarse por un problema de
    limpieza de proceso), pero tampoco se descarta en silencio. Cada
    excepción capturada se agrega (como `repr(exc)`) a `diagnosticos`, para
    que quien llame pueda inspeccionarla (debugging manual, o una futura
    sesión que la persista en `resultado.json`) en vez de perderla.

    Devuelve una tupla `(pid, diagnosticos)`: `pid` es el capturado *antes*
    del apagado (o `None` si no se pudo determinar), para que el llamador
    pueda esperar la confirmación final de muerte con
    `_kernel_murio_tras_espera`; `diagnosticos` es la lista (posiblemente
    vacía) de mensajes de las excepciones best-effort silenciadas durante
    esta corrida de limpieza."""
    diagnosticos: list[str] = []
    km = getattr(client, "km", None)
    if km is None:
        return None, diagnosticos
    pid = _obtener_pid_kernel(km)
    try:
        if km.has_kernel:
            km.shutdown_kernel(now=True)
    except Exception as exc:
        # Best-effort: si `jupyter_client` lanza acá (p. ej. un problema de
        # event loop de asyncio en Windows), no propagamos — el runner nunca
        # debe tumbarse por un problema de limpieza. El respaldo con
        # `psutil` de más abajo se encarga de matar el proceso igual, ya que
        # no podemos confiar en que este `shutdown_kernel` haya llegado a
        # completar su propio kill interno. El mensaje queda en
        # `diagnosticos` en vez de perderse.
        diagnosticos.append(f"shutdown_kernel(now=True): {exc!r}")
    try:
        km.cleanup_resources()
    except Exception as exc:
        diagnosticos.append(f"km.cleanup_resources(): {exc!r}")
    kc = getattr(client, "kc", None)
    if kc is not None:
        try:
            kc.stop_channels()
        except Exception as exc:
            diagnosticos.append(f"kc.stop_channels(): {exc!r}")

    # Respaldo a nivel de proceso del SO, siempre (éxito, error de celda o
    # timeout) -- no solo timeout. Ver docstring del módulo para el
    # diagnóstico completo de por qué no alcanza con (2) arriba.
    if pid is not None and _PSUTIL_DISPONIBLE:
        try:
            proceso = psutil.Process(pid)
            if proceso.is_running():
                proceso.terminate()
                try:
                    proceso.wait(timeout=espera_terminate_kill_segundos)
                except psutil.TimeoutExpired:
                    proceso.kill()
                    try:
                        proceso.wait(timeout=espera_terminate_kill_segundos)
                    except psutil.TimeoutExpired:
                        # Se intentó terminate() y kill(); si sigue vivo, el
                        # llamador lo detecta con `_kernel_murio_tras_espera`
                        # (y, en el caso de timeout, lo refleja en
                        # `posible_proceso_huerfano`).
                        diagnosticos.append(
                            f"psutil: pid {pid} sigue vivo tras terminate()+kill()"
                        )
        except psutil.NoSuchProcess:
            # Ya estaba muerto -- nada que hacer, es el caso esperado si
            # `shutdown_kernel(now=True)` sí completó su kill interno.
            pass
        except Exception as exc:
            # Best-effort: nunca debe tumbar el runner por un problema de
            # limpieza de proceso, pero el mensaje queda en `diagnosticos`.
            diagnosticos.append(f"psutil.Process({pid}): {exc!r}")
    return pid, diagnosticos


def _kernel_murio_tras_espera(
    pid: Optional[int], espera_segundos: float, intervalo_segundos: float = 0.2
) -> Optional[bool]:
    """`True` si se confirmó que el proceso `pid` ya no existe dentro del
    grace period; `False` si sigue vivo al agotarse; `None` si no se puede
    determinar (sin `psutil` disponible o sin pid conocido) — en ese caso el
    llamador debe tratarlo como posible huérfano, no como confirmación de
    nada."""
    if pid is None or not _PSUTIL_DISPONIBLE:
        return None
    limite = time.monotonic() + espera_segundos
    while True:
        if not psutil.pid_exists(pid):
            return True
        if time.monotonic() >= limite:
            return False
        time.sleep(intervalo_segundos)


# --- API pública -------------------------------------------------------------

def ejecutar_notebook(
    notebook_path: Path,
    timeout_segundos: int,
    kernel_name: str = KERNEL_NAME_POR_DEFECTO,
    cwd: Optional[Path] = None,
    espera_apagado_segundos: float = ESPERA_APAGADO_SEGUNDOS_POR_DEFECTO,
) -> ResultadoEjecucion:
    """Ejecuta `notebook_path` con `nbclient`, con timeout duro (por celda,
    ver docstring del módulo) de `timeout_segundos`.

    Nunca lanza `nbclient.exceptions.CellExecutionError` ni `CellTimeoutError`
    — las captura y las traduce a campos de `ResultadoEjecucion`. Dos grupos
    de excepciones sí se propagan hoy, por motivos distintos:

    1. Errores de uso previos a `client.execute()` (p. ej. notebook
       inexistente al leerlo con `nbformat.read`, JSON inválido) — ocurren
       antes del `try`, se propagan por diseño: no son un fallo de ejecución
       del notebook, son un error de uso del runner.
    2. Cualquier excepción de nivel kernel *dentro* de `client.execute()` que
       no sea `CellExecutionError` ni `CellTimeoutError` (p. ej. si el kernel
       muere a mitad de una celda por una causa que no dispara timeout) —
       estas sí son fallas reales de ejecución, no errores de uso, pero esta
       sesión solo cubre explícitamente los dos tipos de falla de arriba; no
       todos los modos de falla del kernel están cubiertos todavía. Es una
       decisión de alcance de esta sesión: una futura que conecte esto con
       el CLI deberá decidir si envuelve este caso en su propio manejo
       genérico, para no reventar el proceso del runner.
    """
    notebook_path = Path(notebook_path)
    cwd_resuelto = Path(cwd) if cwd is not None else _raiz_repo_por_defecto()

    nb = nbformat.read(str(notebook_path), as_version=4)

    client = NotebookClient(
        nb,
        timeout=timeout_segundos,
        kernel_name=kernel_name,
        resources={"metadata": {"path": str(cwd_resuelto)}},
    )

    timeout_alcanzado = False
    posible_proceso_huerfano = False
    error_info: Optional[dict] = None

    inicio = time.monotonic()
    try:
        # cleanup_kc=False: no dejamos que nbclient apague el kernel solo,
        # así `client.km` sigue vivo/accesible en el except de abajo para
        # poder capturar el pid y forzar el apagado explícito nosotros
        # mismos (ver docstring del módulo).
        client.execute(cleanup_kc=False)
    except CellTimeoutError:
        timeout_alcanzado = True
        # `diagnosticos` (mensajes de excepciones best-effort silenciadas
        # durante la limpieza) no se persiste todavía en `ResultadoEjecucion`
        # -- ver docstring de `_apagar_kernel_forzado`; queda disponible acá
        # para debugging manual si hiciera falta.
        pid, _diagnosticos = _apagar_kernel_forzado(client)
        murio = _kernel_murio_tras_espera(pid, espera_apagado_segundos)
        posible_proceso_huerfano = murio is not True
    except CellExecutionError as exc:
        error_info = {
            "ename": exc.ename,
            "evalue": exc.evalue,
            "traceback": exc.traceback,
        }
        pid, _diagnosticos = _apagar_kernel_forzado(client)
        # No es un timeout (`posible_proceso_huerfano` no aplica acá, ver
        # docstring del módulo), pero igual esperamos confirmación de que el
        # proceso ya murió antes de retornar -- si no, dejamos su directorio
        # de trabajo (`cwd`) "en uso" para quien llame a continuación (p.
        # ej. un test que va a borrar su propio tempdir).
        _kernel_murio_tras_espera(pid, espera_apagado_segundos)
    else:
        pid, _diagnosticos = _apagar_kernel_forzado(client)
        _kernel_murio_tras_espera(pid, espera_apagado_segundos)
    duracion_segundos = time.monotonic() - inicio

    # timeout_alcanzado=True implica siempre exit_ok=False, sin excepción
    # (spec.md requisito 7, textual).
    exit_ok = not timeout_alcanzado and error_info is None

    return ResultadoEjecucion(
        exit_ok=exit_ok,
        duracion_segundos=duracion_segundos,
        stdout_resumen=_resumen_stream(nb, "stdout"),
        stderr_resumen=_resumen_stream(nb, "stderr"),
        timeout_alcanzado=timeout_alcanzado,
        posible_proceso_huerfano=posible_proceso_huerfano,
        error_info=error_info,
    )

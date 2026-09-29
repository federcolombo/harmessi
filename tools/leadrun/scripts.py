"""Ejecución de scripts/pytest del runtime de ejecución del Lead (v0.8
Change 2, `20260929-lead-execution-runtime`, T4).

Recibe un `core.ExecutionRequest` YA EVALUADO como `permitido=True` por
`allowlist.evaluar_comando` (este módulo no vuelve a evaluar la forma del
comando: confía en que el llamador ya lo hizo, R10 de `spec.md`). Ejecuta el
comando vía `subprocess.run(..., capture_output=True, text=True)` y devuelve
la porción del `ExecutionRecord` que le corresponde a este módulo. El resto
de los campos (`execution_id`, `code_hash`, `outputs_hash`, `executed_by`,
`mode`, `approval`, `generated_at`) los completa `runtime.py`.

Límite conocido (R-A/R-B de `design.md`, mismo límite que ya declara
`tools/nbrunner/execute.py` para notebooks): `subprocess.run(timeout=...)`
garantiza que el proceso *padre* termina al expirar el timeout, en cualquier
plataforma. En Windows, si ese proceso a su vez lanzó otros procesos hijos
(p. ej. un script que invoca a otro binario), esos hijos anidados pueden
sobrevivir como huérfanos — la stdlib no ofrece, por sí sola, una garantía de
terminación de todo el árbol de procesos en Windows. Este módulo no
implementa ninguna solución nueva para ese límite (documentado, no resuelto,
D9 del encargo de T4): se apoya únicamente en el timeout duro del proceso
padre.

`stdout_summary`/`stderr_summary` se devuelven TAL CUAL los produce
`subprocess` (texto completo, sin truncar y sin redactar secretos). El
truncado a `core.RESUMEN_MAXIMO_CARACTERES` y la redacción de secretos son
responsabilidad exclusiva de `runtime.py` (R9 de `spec.md`); este módulo no
duplica esa lógica.
"""
from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Union

from . import core as leadrun_core

# Sentinels de `exit_code` (convención POSIX ya fijada en `spec.md` R10):
# 124 = timeout, 127 = comando/intérprete no encontrado.
EXIT_CODE_TIMEOUT = 124
EXIT_CODE_COMANDO_NO_ENCONTRADO = 127


def ejecutar_script(request: "leadrun_core.ExecutionRequest", repo_root: Union[str, "Path"]) -> dict:
    """Ejecuta `request.argv` vía `subprocess.run` con `cwd=repo_root` y
    `timeout=request.timeout_seconds`. `request` debe venir ya evaluado como
    `permitido=True` por `allowlist.evaluar_comando` — esta función NO vuelve
    a evaluar la forma del comando.

    Devuelve un dict con la forma parcial de `core.ExecutionRecord` que le
    corresponde a este módulo:
    ``{"exit_code": int, "duration_seconds": float, "stdout_summary": str,
    "stderr_summary": str, "timed_out": bool}``.

    Nunca lanza hacia el llamador, salvo que la stdlib decida propagar algo
    fuera de `subprocess.TimeoutExpired`/`FileNotFoundError` (no esperado en
    uso normal): `FileNotFoundError` (intérprete/script inexistente) se
    atrapa y se traduce a `exit_code=127` con el mensaje en
    `stderr_summary`, sin propagar la excepción.
    """
    inicio = time.monotonic()
    try:
        resultado = subprocess.run(
            request.argv,
            cwd=repo_root,
            timeout=request.timeout_seconds,
            capture_output=True,
            text=True,
        )
    except subprocess.TimeoutExpired as exc:
        duracion = time.monotonic() - inicio
        stdout_parcial = exc.stdout if isinstance(exc.stdout, str) else (exc.stdout.decode("utf-8", "replace") if exc.stdout else "")
        stderr_parcial = exc.stderr if isinstance(exc.stderr, str) else (exc.stderr.decode("utf-8", "replace") if exc.stderr else "")
        return {
            "exit_code": EXIT_CODE_TIMEOUT,
            "duration_seconds": duracion,
            "stdout_summary": stdout_parcial,
            "stderr_summary": stderr_parcial,
            "timed_out": True,
        }
    except FileNotFoundError as exc:
        duracion = time.monotonic() - inicio
        return {
            "exit_code": EXIT_CODE_COMANDO_NO_ENCONTRADO,
            "duration_seconds": duracion,
            "stdout_summary": "",
            "stderr_summary": f"comando no encontrado: {exc}",
            "timed_out": False,
        }

    duracion = time.monotonic() - inicio
    return {
        "exit_code": resultado.returncode,
        "duration_seconds": duracion,
        "stdout_summary": resultado.stdout if resultado.stdout is not None else "",
        "stderr_summary": resultado.stderr if resultado.stderr is not None else "",
        "timed_out": False,
    }


def ejecutar_pytest(request: "leadrun_core.ExecutionRequest", repo_root: Union[str, "Path"]) -> dict:
    """Misma ejecución que `ejecutar_script`: la única diferencia entre las
    formas `script` y `pytest` está en `request.argv` (ya armado por
    `allowlist.py`/quien construye el `ExecutionRequest`). No duplica la
    llamada a `subprocess.run`."""
    return ejecutar_script(request, repo_root)

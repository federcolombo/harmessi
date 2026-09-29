"""Orquestador único del runtime de ejecución del Lead (v0.8 Change 2,
`20260929-lead-execution-runtime`, T5).

Único módulo de `tools/leadrun/` que produce y persiste un `ExecutionRecord`
(R13 de `spec.md`): `scripts.py`/`notebooks.py` devuelven dicts crudos, sin
truncar ni redactar, y no conocen `.harmessi/executions/` -- ese ensamblado
final (redacción de secretos, construcción del registro, escritura atómica)
vive exclusivamente acá.

Importa `dsguard.checks` (vocabulario `CheckResult`/`resultado_de_excepcion`)
y `datasources.scan` (`scan_secrets`/`scan_locators`) como paquetes de nivel
superior -- mismo patrón ya usado por `tools/datasources/runtime.py:9` y
`tools/datacontracts/validation.py:67-71`: se inserta `tools/` en `sys.path`
para que `import dsguard...`/`import datasources...` resuelva sin el prefijo
`tools.`. Esta es la MISMA excepción de dependencia ya documentada para M1
(`openspec/changes/20260928-source-neutral-data-access/spec.md:22-26`),
extendida acá a `datasources.scan` (R1/R9 de `spec.md` de este Change).
`runtime.py` NO importa `tools.autonomy` ni `tools.dsguard.pathguard`: esa
composición vive en `ds_guard.py` (T6, R14 de `spec.md`).

Defensa en profundidad (R13/R8): antes de ejecutar nada, `ejecutar()` vuelve
a llamar `allowlist.evaluar_comando` sobre el propio `request`, aunque el
llamador (`ds_guard.py`) ya la haya evaluado antes para decidir si componer
una aprobación. Este módulo no confía ciegamente en esa evaluación previa:
es la garantía de que ningún comando llega a `subprocess`/`nbrunner` sin
pasar por la allowlist DESDE ESTE MÓDULO.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Optional

_TOOLS_DIR = Path(__file__).resolve().parents[1]
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from dsguard import checks as dsguard_checks  # noqa: E402
from dsguard import core as dsguard_core  # noqa: E402
from datasources import scan as datasources_scan  # noqa: E402

from . import allowlist  # noqa: E402
from . import core as leadrun_core  # noqa: E402
from . import notebooks  # noqa: E402
from . import scripts  # noqa: E402

# ---------------------------------------------------------------------------
# Redacción (R9) -- opera sobre el dict crudo de argv/stdout/stderr antes de
# persistir, nunca después.
# ---------------------------------------------------------------------------

# `json_pointer` que produce `datasources.scan` para un elemento indexado
# bajo la clave "argv" de `{"argv": {"<indice>": elemento, ...}}`:
# `$/argv/<indice>` (ver `_redactar_argv`).
_RE_ARGV_POINTER = re.compile(r"^\$/argv/(\d+)$")


def _redactar_argv(argv: tuple) -> tuple:
    """Si `scan_secrets`/`scan_locators` encuentran algo en algún elemento de
    `argv`, redacta SOLO ese elemento (identificado por el índice que el
    `json_pointer` del hallazgo trae, `$/argv/<indice>`). Si algún hallazgo
    no es identificable con precisión por índice (forma de pointer
    inesperada), decisión documentada: se redacta el `argv` COMPLETO en vez
    de arriesgar dejar un valor sensible sin redactar.

    `argv` se envuelve como `{"argv": {"<indice>": elemento, ...}}` (dict
    indexado por string) y NO como `{"argv": [elemento, ...]}` (lista
    plana): `scan_secrets` solo evalúa la forma de credencial de un valor
    cuando es el VALOR de una clave de un dict (rama `elif isinstance(valor,
    str)` del caso `dict`, `tools/datasources/scan.py`); un elemento de
    lista se recorre por la rama `elif isinstance(obj, str)` del caso base,
    que solo chequea forma de DSN, no de credencial. Envolver como dict
    preserva el mismo `json_pointer` (`$/argv/<indice>`) y habilita también
    la detección de credenciales, no solo de DSN -- decisión de este módulo,
    documentada, no una reinterpretación de `scan.py` (que no se toca)."""
    payload = {"argv": {str(i): elemento for i, elemento in enumerate(argv)}}
    hallazgos = datasources_scan.scan_secrets(payload) + datasources_scan.scan_locators(payload)
    if not hallazgos:
        return tuple(argv)

    indices: set = set()
    identificados_todos = True
    for _code, pointer, _motivo in hallazgos:
        match = _RE_ARGV_POINTER.match(pointer)
        if match:
            indices.add(int(match.group(1)))
        else:
            identificados_todos = False

    redactado = list(argv)
    if identificados_todos:
        for indice in indices:
            if 0 <= indice < len(redactado):
                redactado[indice] = "[REDACTADO]"
    else:
        redactado = ["[REDACTADO]" for _ in redactado]
    return tuple(redactado)


def _redactar_resumen(texto: str, etiqueta: str) -> str:
    """Trunca primero a `core.RESUMEN_MAXIMO_CARACTERES`, luego escanea el
    texto YA TRUNCADO (no el completo): si truncar corta un secreto a la
    mitad de forma que ya no lo detecte el scan, es un límite aceptado de
    este Change, documentado acá y en `spec.md` R9 (no se resuelve con una
    solución nueva). Si el scan encuentra algo en el resumen truncado, TODO
    el resumen se reemplaza por un sentinel -- no se intenta redactar solo la
    porción sospechosa dentro de texto libre.

    Límite conocido y aceptado: una credencial incrustada en texto libre (p.
    ej. 'log: token=ghp_xxx fin') NO se detecta -- el patrón de
    `datasources.scan` está anclado al inicio del valor
    (`^(AKIA|ghp_|xox|sk-)`, `scan.py:46`) y solo identifica un valor que ES
    la credencial completa. Límite conocido y aceptado (best-effort, mismo
    criterio ya declarado en Change 1), no resuelto acá."""
    truncado = (texto or "")[: leadrun_core.RESUMEN_MAXIMO_CARACTERES]
    payload = {etiqueta: truncado}
    hallazgos = datasources_scan.scan_secrets(payload) + datasources_scan.scan_locators(payload)
    if hallazgos:
        return "[REDACTADO: posible secreto detectado]"
    return truncado


# ---------------------------------------------------------------------------
# Normalización de la forma "notebook" a la forma común (R13 del encargo,
# decisión de este módulo)
# ---------------------------------------------------------------------------


def _resumen_manifest_no_ejecutado(nb_resultado: dict) -> str:
    """Diagnóstico legible cuando `notebooks.ejecutar_manifest` no llegó a
    ejecutar el notebook (dry-run, o `execute` bloqueado por Findings/
    aprobación): no hay `resultado_ejecucion` real del que tomar
    `stderr_resumen`, así que se arma uno a partir de `estado_aprobacion` y
    los `findings` acumulados -- decisión de este módulo, no de
    `notebooks.py`, para que el `ExecutionRecord` resultante siga siendo
    diagnosticable sin tener que releer el manifest."""
    partes = [f"estado_aprobacion={nb_resultado.get('estado_aprobacion')}"]
    for hallazgo in nb_resultado.get("findings") or []:
        partes.append(f"{hallazgo.get('codigo')}: {hallazgo.get('mensaje')}")
    return "; ".join(partes)


def _ejecutar_forma_notebook(request: "leadrun_core.ExecutionRequest", repo_root: Path, control_data: dict):
    """Extrae la ruta del manifest de `request.argv` (forma (c) de
    `allowlist.py`: `... run --manifest <ruta> [--dry-run|--execute]`),
    delega en `notebooks.ejecutar_manifest` y NORMALIZA su resultado (forma
    `ok`/`findings`/`resultado_ejecucion`/... , distinta de la de
    `scripts.ejecutar_script`) a la forma común `exit_code`/
    `duration_seconds`/`stdout_summary`/`stderr_summary`/`timed_out` que el
    resto de `ejecutar()` necesita para construir un `ExecutionRecord`.

    Normalización (decisión documentada de este módulo, dentro del margen
    del encargo): `exit_code = 0` únicamente si `ok is True` **y**
    `ejecutado is True`; `1` en cualquier otro caso donde hubo un intento
    (incluye dry-run exitoso, que por definición nunca ejecuta: se considera
    "no ejecución" a efectos de `exit_code`, no un fallo de validación, pero
    tampoco un `exit_code=0` de ejecución real -- el detalle completo queda
    en `stderr_summary`/`findings` para quien inspeccione el registro)."""
    if "--manifest" not in request.argv:
        raise ValueError("argv de forma 'notebook' sin '--manifest': no se puede resolver el manifest")
    indice = request.argv.index("--manifest")
    ruta_manifest = request.argv[indice + 1]

    modo = "dry_run" if ("--dry-run" in request.argv or "--execute" not in request.argv) else "execute"

    nb_resultado = notebooks.ejecutar_manifest(ruta_manifest, repo_root, control_data, modo)

    ok = nb_resultado.get("ok") is True
    ejecutado = nb_resultado.get("ejecutado") is True
    resultado_ejecucion = nb_resultado.get("resultado_ejecucion") or {}

    if resultado_ejecucion:
        stdout_resumen = resultado_ejecucion.get("stdout_resumen", "") or ""
        stderr_resumen = resultado_ejecucion.get("stderr_resumen", "") or ""
        duracion = resultado_ejecucion.get("duracion_segundos", 0.0) or 0.0
        timed_out = bool(resultado_ejecucion.get("timeout_alcanzado", False))
    else:
        stdout_resumen = ""
        stderr_resumen = _resumen_manifest_no_ejecutado(nb_resultado)
        duracion = 0.0
        timed_out = False

    crudo = {
        "exit_code": 0 if (ok and ejecutado) else 1,
        "duration_seconds": float(duracion),
        "stdout_summary": stdout_resumen,
        "stderr_summary": stderr_resumen,
        "timed_out": timed_out,
    }

    try:
        code_hash = dsguard_core.hash_lf_v1(Path(repo_root) / ruta_manifest)
    except (OSError, UnicodeDecodeError):
        code_hash = None

    return crudo, code_hash


# ---------------------------------------------------------------------------
# Persistencia atómica (R16) -- mismo criterio de idempotencia/colisión que
# `datasources.runtime._persistir_observacion`
# (`openspec/changes/20260928-source-neutral-data-access/spec.md` R23):
# bytes idénticos a lo ya persistido -> no-op; bytes distintos con el mismo
# `execution_id` -> error de colisión, SIN sobreescribir.
# ---------------------------------------------------------------------------


def _persistir_registro(repo_root: Path, record: "leadrun_core.ExecutionRecord") -> Optional["dsguard_checks.CheckResult"]:
    dir_path = Path(repo_root) / ".harmessi" / "executions" / record.execution_id
    dir_path.mkdir(parents=True, exist_ok=True)
    file_path = dir_path / "record.json"

    payload = json.dumps(record.to_dict(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    payload_bytes = payload.encode("utf-8")

    if file_path.exists():
        existente = file_path.read_bytes()
        if existente == payload_bytes:
            return None
        return dsguard_checks.CheckResult(
            dsguard_checks.STATUS_FAIL,
            leadrun_core.CODE_RUNTIME_ERROR,
            f"colisión de hash: {record.execution_id} ya existe con contenido distinto",
            kind=dsguard_checks.KIND_TECHNICAL_ERROR,
        )

    tmp_path = dir_path / (file_path.name + ".tmp")
    try:
        tmp_path.write_bytes(payload_bytes)
        os.replace(tmp_path, file_path)
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
    return None


# ---------------------------------------------------------------------------
# Función pública
# ---------------------------------------------------------------------------


def ejecutar(
    request: "leadrun_core.ExecutionRequest",
    repo_root: Any,
    executed_by: str,
    mode: str,
    approval: Optional[dict],
    control_data: Optional[dict] = None,
) -> dict:
    """Orquesta una ejecución de punta a punta (R7/R9/R12-R13/R16 de
    `spec.md`) y devuelve
    ``{"record": Optional[dict], "checks": list[dict]}``.

    `record` tiene la forma de `core.ExecutionRecord.to_dict()`, o `None` si
    no se ejecutó nada (comando rechazado por la allowlist, o error de
    persistencia -- colisión de hash). `checks` es la lista de
    `CheckResult.to_dict()` que documentan el resultado.

    Nunca lanza hacia el llamador (red de seguridad final: cualquier
    excepción no prevista se traduce a un `CheckResult` técnico vía
    `dsguard.checks.resultado_de_excepcion`, con `record=None`)."""
    try:
        repo_root = Path(repo_root)

        # 1. Allowlist -- defensa en profundidad, ver docstring del módulo.
        permitido, _forma, motivo = allowlist.evaluar_comando(request.argv, request.scope, request.interpreter)
        if not permitido:
            return {
                "record": None,
                "checks": [
                    dsguard_checks.CheckResult(
                        dsguard_checks.STATUS_FAIL,
                        leadrun_core.CODE_COMMAND_REJECTED,
                        f"comando rechazado por la allowlist: {motivo}",
                    ).to_dict()
                ],
            }

        # 2. Ejecución según `command_form`.
        code_hash: Optional[str] = None
        if request.command_form == "pytest":
            crudo = scripts.ejecutar_pytest(request, repo_root)
        elif request.command_form == "script":
            crudo = scripts.ejecutar_script(request, repo_root)
            # `code_hash` solo se calcula para `script`: para `pytest` no hay
            # un único archivo canónico que hashear (puede haber varias
            # rutas de test en `argv`), decisión de este módulo dentro del
            # margen del encargo -- documentada, no una re-decisión de R7
            # (que solo exige `None` para `cli_diagnostic`).
            try:
                code_hash = dsguard_core.hash_lf_v1(repo_root / request.argv[1])
            except (OSError, IndexError, UnicodeDecodeError):
                code_hash = None
        elif request.command_form == "cli_diagnostic":
            # Mismo `subprocess.run` que `script` (R7: `code_hash=None`
            # siempre para esta forma, sin excepción).
            crudo = scripts.ejecutar_script(request, repo_root)
        elif request.command_form == "notebook":
            crudo, code_hash = _ejecutar_forma_notebook(request, repo_root, control_data or {})
        else:
            raise ValueError(f"command_form no soportado: {request.command_form!r}")

        # 3. Redacción (R9) -- sobre el dict crudo, antes de construir el
        # registro.
        argv_redactado = _redactar_argv(request.argv)
        stdout_resumen = _redactar_resumen(crudo["stdout_summary"], "stdout")
        stderr_resumen = _redactar_resumen(crudo["stderr_summary"], "stderr")

        # 4. `ExecutionRecord`.
        generated_at = dsguard_core.ahora_utc()
        campos_identidad = {
            "command_form": request.command_form,
            "argv": list(argv_redactado),
            "code_hash": code_hash,
            "exit_code": crudo["exit_code"],
            "duration_seconds": float(crudo["duration_seconds"]),
            "stdout_summary": stdout_resumen,
            "stderr_summary": stderr_resumen,
            "outputs_hash": None,
            "executed_by": executed_by,
            "mode": mode,
            "approval": approval,
            "timed_out": bool(crudo["timed_out"]),
        }
        # `execution_id` (decisión de este módulo, D del encargo): mismo
        # criterio que `datasources.runtime._persistir_observacion`
        # (`f"{base}__{content_sha256[:12]}"`), con `command_form` como
        # base identificadora y el hash calculado sobre los campos que
        # identifican QUÉ se pidió y QUÉ resultó -- deliberadamente SIN
        # `generated_at` (timestamp de pared, no determinista entre
        # llamadas) ni `execution_id` (circular). Esto permite que dos
        # llamadas con el mismo resultado real produzcan el mismo
        # `execution_id` (idempotencia, R16) y que un resultado distinto
        # (aunque sea solo en `stdout_summary`) produzca un `execution_id`
        # distinto en vez de una colisión espuria.
        execution_id = f"{request.command_form}__{leadrun_core.content_sha256(campos_identidad)[:12]}"

        record = leadrun_core.ExecutionRecord(
            execution_id=execution_id,
            command_form=request.command_form,
            argv=argv_redactado,
            code_hash=code_hash,
            exit_code=crudo["exit_code"],
            duration_seconds=float(crudo["duration_seconds"]),
            stdout_summary=stdout_resumen,
            stderr_summary=stderr_resumen,
            outputs_hash=None,
            executed_by=executed_by,
            mode=mode,
            approval=approval,
            generated_at=generated_at,
            timed_out=bool(crudo["timed_out"]),
        )

        # 5. Persistencia atómica (R16).
        error_persistencia = _persistir_registro(repo_root, record)
        if error_persistencia is not None:
            return {"record": None, "checks": [error_persistencia.to_dict()]}

        # 6. `CheckResult`s de resultado (no usan el prefijo `EXEC-`: ese
        # catálogo, R6 de `spec.md`, está reservado a los códigos ya
        # definidos en `core.CODES`; estos son códigos de diagnóstico propios
        # de `runtime.py`, fuera de ese catálogo cerrado).
        if record.timed_out:
            resultado_check = dsguard_checks.CheckResult(
                dsguard_checks.STATUS_WARN,
                leadrun_core.CODE_TIMEOUT,
                f"la ejecución superó el timeout de {request.timeout_seconds}s",
            )
        elif record.exit_code == 0:
            resultado_check = dsguard_checks.CheckResult(
                dsguard_checks.STATUS_PASS,
                "LEADRUN-EXIT-OK",
                "ejecución completada con exit_code 0",
            )
        else:
            resultado_check = dsguard_checks.CheckResult(
                dsguard_checks.STATUS_FAIL,
                "LEADRUN-EXIT-NONZERO",
                f"ejecución terminó con exit_code {record.exit_code}",
            )

        return {"record": record.to_dict(), "checks": [resultado_check.to_dict()]}
    except Exception as exc:  # noqa: BLE001 - red de seguridad final: nunca lanza hacia el llamador.
        return {
            "record": None,
            "checks": [dsguard_checks.resultado_de_excepcion("LEADRUN-RUNTIME", exc).to_dict()],
        }

"""Tipos base del runtime de ejecución del Lead (v0.8 Change 2,
`20260929-lead-execution-runtime`, T1).

Módulo solo-stdlib (`dataclasses`, `typing`, `re`, `json`, `hashlib`,
`__future__`): sin `os`, `pathlib`, `sys`, `subprocess`, `importlib`, sin
imports de módulos hermanos (`allowlist`, `scripts`, `notebooks`, `runtime`)
ni de `tools.*` (R1, `spec.md`).

Declara:
- `EXECUTION_FORMS`/`validar_execution_form`: vocabulario cerrado de formas de
  comando reconocidas (R4).
- `ExecutionRequest`: pedido de ejecución ya evaluado por `allowlist.py`
  (R5).
- `ExecutionRecord`: evidencia de una ejecución, serialización determinista
  (R7). `approval` se recibe ya serializado (un `dict` o `None`) desde el
  llamador: este módulo NO importa `tools.autonomy` (excepción de
  dependencia de *tipo de dato*, no de import, documentada en `spec.md` R7,
  análoga a la de M1 en
  `openspec/changes/20260928-source-neutral-data-access/spec.md:22-26`).
- `ExecutionError`: única excepción de este módulo para construcción/
  validación de tipos.
- `CODES`: registro único de códigos `EXEC-*` (R6); ningún otro módulo de
  `tools/leadrun/` declara un código `EXEC-*` fuera de esta lista.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field as _campo_dataclass
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Vocabularios
# ---------------------------------------------------------------------------

# Formas de comando reconocidas por `allowlist.evaluar_comando` (R4/R8).
EXECUTION_FORMS = ("script", "pytest", "notebook", "cli_diagnostic")

EXECUTED_BY_VALUES = ("lead", "human")
EXECUTION_MODES = ("autonomous", "supervised")

# Metacaracteres de encadenamiento prohibidos en cualquier elemento de
# `argv` (R5) — mismo criterio que `tools/nbrunner/hook_validar_comando.py`
# aplica implícitamente al anclar `PATRON_COMANDO` con `^...$` y una clase de
# caracteres cerrada.
_METACARACTERES_PROHIBIDOS = frozenset({"&", ";", "|", "`", "$", "(", ")", "<", ">", "\n"})

# Límite de truncado de resúmenes de stdout/stderr en `ExecutionRecord`
# (documentado acá, R7; el truncado real lo aplica `scripts.py`/`runtime.py`,
# este módulo solo declara el límite compartido).
RESUMEN_MAXIMO_CARACTERES = 4000

# ---------------------------------------------------------------------------
# Registro único de códigos EXEC-* (R6)
# ---------------------------------------------------------------------------

CODE_FORM_INVALID = "EXEC-FORM-INVALID"
CODE_REQUEST_INVALID = "EXEC-REQUEST-INVALID"
CODE_COMMAND_REJECTED = "EXEC-COMMAND-REJECTED"
CODE_APPROVAL_MISSING = "EXEC-APPROVAL-MISSING"
CODE_APPROVAL_STALE = "EXEC-APPROVAL-STALE"
CODE_SCOPE_VIOLATION = "EXEC-SCOPE-VIOLATION"
CODE_TIMEOUT = "EXEC-TIMEOUT"
CODE_RUNTIME_ERROR = "EXEC-RUNTIME-ERROR"

CODES = (
    CODE_FORM_INVALID,
    CODE_REQUEST_INVALID,
    CODE_COMMAND_REJECTED,
    CODE_APPROVAL_MISSING,
    CODE_APPROVAL_STALE,
    CODE_SCOPE_VIOLATION,
    CODE_TIMEOUT,
    CODE_RUNTIME_ERROR,
)


class ExecutionError(Exception):
    """Única excepción de `leadrun.core` para construcción/validación de
    tipos. `code` es uno de `CODES`."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


# ---------------------------------------------------------------------------
# Helpers de serialización determinista
# ---------------------------------------------------------------------------


def canonical_json(obj: Any) -> str:
    """JSON canónico: claves ordenadas, sin espacios, sin escapar no-ASCII,
    sin `NaN`/`Infinity`."""
    try:
        return json.dumps(
            obj,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError, RecursionError) as exc:
        raise ExecutionError(CODE_REQUEST_INVALID, f"canonical_json: objeto no serializable ({exc})") from exc


def content_sha256(obj: Any) -> str:
    """sha256 hex del JSON canónico (UTF-8) de `obj`."""
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# ExecutionForm (R4)
# ---------------------------------------------------------------------------


def validar_execution_form(valor: Any) -> list:
    """Validación pura (no lanza): devuelve `[(code, motivo)]` si `valor` no
    está en `EXECUTION_FORMS`, lista vacía si es válido."""
    if valor not in EXECUTION_FORMS:
        return [(CODE_FORM_INVALID, f"forma de comando inválida {valor!r}, se esperaba una de {EXECUTION_FORMS}")]
    return []


# ---------------------------------------------------------------------------
# Metacaracteres (R5)
# ---------------------------------------------------------------------------


def contiene_metacaracter_prohibido(texto: str) -> bool:
    """`True` si `texto` contiene alguno de los metacaracteres de
    encadenamiento prohibidos (`_METACARACTERES_PROHIBIDOS`)."""
    if not isinstance(texto, str):
        return False
    return any(caracter in texto for caracter in _METACARACTERES_PROHIBIDOS)


# ---------------------------------------------------------------------------
# ExecutionRequest (R5)
# ---------------------------------------------------------------------------

_EXECUTION_REQUEST_CLAVES = ("command_form", "interpreter", "argv", "scope", "timeout_seconds")


def validar_execution_request(d: Any) -> list:
    """Validación estructural PURA (no lanza) de un dict candidato a
    `ExecutionRequest`: devuelve `[(code, motivo), ...]`, vacía si es
    válido."""
    hallazgos: list = []
    if not isinstance(d, dict):
        return [(CODE_REQUEST_INVALID, f"se esperaba dict, se recibió {type(d).__name__}")]

    claves_desconocidas = sorted(k for k in d if k not in _EXECUTION_REQUEST_CLAVES)
    for clave in claves_desconocidas:
        hallazgos.append((CODE_REQUEST_INVALID, f"clave desconocida {clave!r}"))

    faltantes = [c for c in _EXECUTION_REQUEST_CLAVES if c not in d]
    if faltantes:
        hallazgos.append((CODE_REQUEST_INVALID, f"faltan campos {faltantes}"))

    if "command_form" in d:
        hallazgos.extend(validar_execution_form(d["command_form"]))

    if "interpreter" in d:
        interpreter = d["interpreter"]
        if not isinstance(interpreter, str) or interpreter == "":
            hallazgos.append((CODE_REQUEST_INVALID, f"interpreter inválido {interpreter!r}"))

    if "argv" in d:
        argv = d["argv"]
        if not isinstance(argv, (list, tuple)) or len(argv) == 0:
            hallazgos.append((CODE_REQUEST_INVALID, "argv no puede estar vacío"))
        else:
            for i, item in enumerate(argv):
                if not isinstance(item, str):
                    hallazgos.append((CODE_REQUEST_INVALID, f"argv[{i}]: se esperaba str, se recibió {type(item).__name__}"))
                elif contiene_metacaracter_prohibido(item):
                    hallazgos.append((CODE_REQUEST_INVALID, f"argv[{i}]: contiene un metacarácter prohibido"))

    if "scope" in d:
        scope = d["scope"]
        if not isinstance(scope, (list, tuple)):
            hallazgos.append((CODE_REQUEST_INVALID, f"scope: se esperaba list/tuple, se recibió {type(scope).__name__}"))
        else:
            for i, item in enumerate(scope):
                if not isinstance(item, str):
                    hallazgos.append((CODE_REQUEST_INVALID, f"scope[{i}]: se esperaba str, se recibió {type(item).__name__}"))

    if "timeout_seconds" in d:
        timeout_seconds = d["timeout_seconds"]
        if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, int) or timeout_seconds <= 0:
            hallazgos.append((CODE_REQUEST_INVALID, f"timeout_seconds: se esperaba int > 0, se recibió {timeout_seconds!r}"))

    return hallazgos


@dataclass(frozen=True)
class ExecutionRequest:
    """Pedido de ejecución. `command_form` debe estar en `EXECUTION_FORMS`;
    `argv` no vacío y sin metacaracteres de encadenamiento; `scope` es una
    tupla de rutas/patrones que el llamador ya resolvió (D3: este módulo no
    decide el origen del alcance); `timeout_seconds` entero positivo."""

    command_form: str
    interpreter: str
    argv: tuple
    scope: tuple
    timeout_seconds: int

    def __post_init__(self) -> None:
        argv = tuple(self.argv)
        scope = tuple(self.scope)
        hallazgos = validar_execution_request(
            {
                "command_form": self.command_form,
                "interpreter": self.interpreter,
                "argv": argv,
                "scope": scope,
                "timeout_seconds": self.timeout_seconds,
            }
        )
        if hallazgos:
            code, motivo = hallazgos[0]
            raise ExecutionError(code, motivo)
        object.__setattr__(self, "argv", argv)
        object.__setattr__(self, "scope", scope)

    def to_dict(self) -> dict:
        return {
            "command_form": self.command_form,
            "interpreter": self.interpreter,
            "argv": list(self.argv),
            "scope": list(self.scope),
            "timeout_seconds": self.timeout_seconds,
        }

    @classmethod
    def from_dict(cls, d: Any) -> "ExecutionRequest":
        hallazgos = validar_execution_request(d)
        if hallazgos:
            code, motivo = hallazgos[0]
            raise ExecutionError(code, motivo)
        return cls(
            command_form=d["command_form"],
            interpreter=d["interpreter"],
            argv=tuple(d["argv"]),
            scope=tuple(d["scope"]),
            timeout_seconds=d["timeout_seconds"],
        )


# ---------------------------------------------------------------------------
# ExecutionRecord (R7)
# ---------------------------------------------------------------------------

_EXECUTION_RECORD_CLAVES = (
    "execution_id",
    "command_form",
    "argv",
    "code_hash",
    "exit_code",
    "duration_seconds",
    "stdout_summary",
    "stderr_summary",
    "outputs_hash",
    "executed_by",
    "mode",
    "approval",
    "generated_at",
    "timed_out",
)


def _validar_execution_record_dict(d: Any) -> list:
    """Validación estructural PURA (no lanza) de un dict candidato a
    `ExecutionRecord`: devuelve `[(code, motivo), ...]`, vacía si es
    válido."""
    hallazgos: list = []
    if not isinstance(d, dict):
        return [(CODE_REQUEST_INVALID, f"se esperaba dict, se recibió {type(d).__name__}")]

    claves_desconocidas = sorted(k for k in d if k not in _EXECUTION_RECORD_CLAVES)
    for clave in claves_desconocidas:
        hallazgos.append((CODE_REQUEST_INVALID, f"clave desconocida {clave!r}"))

    faltantes = [c for c in _EXECUTION_RECORD_CLAVES if c not in d]
    if faltantes:
        hallazgos.append((CODE_REQUEST_INVALID, f"faltan campos {faltantes}"))
        return hallazgos

    execution_id = d["execution_id"]
    if not isinstance(execution_id, str) or execution_id == "":
        hallazgos.append((CODE_REQUEST_INVALID, f"execution_id inválido {execution_id!r}"))

    command_form = d["command_form"]
    hallazgos.extend(validar_execution_form(command_form))

    argv = d["argv"]
    if not isinstance(argv, (list, tuple)):
        hallazgos.append((CODE_REQUEST_INVALID, f"argv: se esperaba list/tuple, se recibió {type(argv).__name__}"))
    else:
        for i, item in enumerate(argv):
            if not isinstance(item, str):
                hallazgos.append((CODE_REQUEST_INVALID, f"argv[{i}]: se esperaba str, se recibió {type(item).__name__}"))

    code_hash = d["code_hash"]
    if code_hash is not None and not isinstance(code_hash, str):
        hallazgos.append((CODE_REQUEST_INVALID, f"code_hash: se esperaba str o None, se recibió {type(code_hash).__name__}"))
    if command_form == "cli_diagnostic" and code_hash is not None:
        hallazgos.append((CODE_REQUEST_INVALID, "code_hash debe ser None cuando command_form es cli_diagnostic"))

    exit_code = d["exit_code"]
    if isinstance(exit_code, bool) or not isinstance(exit_code, int):
        hallazgos.append((CODE_REQUEST_INVALID, f"exit_code: se esperaba int, se recibió {exit_code!r}"))

    duration_seconds = d["duration_seconds"]
    if isinstance(duration_seconds, bool) or not isinstance(duration_seconds, (int, float)) or duration_seconds < 0:
        hallazgos.append((CODE_REQUEST_INVALID, f"duration_seconds: se esperaba float >= 0, se recibió {duration_seconds!r}"))

    stdout_summary = d["stdout_summary"]
    if not isinstance(stdout_summary, str):
        hallazgos.append((CODE_REQUEST_INVALID, f"stdout_summary: se esperaba str, se recibió {type(stdout_summary).__name__}"))

    stderr_summary = d["stderr_summary"]
    if not isinstance(stderr_summary, str):
        hallazgos.append((CODE_REQUEST_INVALID, f"stderr_summary: se esperaba str, se recibió {type(stderr_summary).__name__}"))

    outputs_hash = d["outputs_hash"]
    if outputs_hash is not None and not isinstance(outputs_hash, str):
        hallazgos.append((CODE_REQUEST_INVALID, f"outputs_hash: se esperaba str o None, se recibió {type(outputs_hash).__name__}"))

    executed_by = d["executed_by"]
    if executed_by not in EXECUTED_BY_VALUES:
        hallazgos.append((CODE_REQUEST_INVALID, f"executed_by: {executed_by!r} fuera de {EXECUTED_BY_VALUES}"))

    mode = d["mode"]
    if mode not in EXECUTION_MODES:
        hallazgos.append((CODE_REQUEST_INVALID, f"mode: {mode!r} fuera de {EXECUTION_MODES}"))

    approval = d["approval"]
    if approval is not None and not isinstance(approval, dict):
        hallazgos.append((CODE_REQUEST_INVALID, f"approval: se esperaba dict o None, se recibió {type(approval).__name__}"))
    if mode == "autonomous" and approval is not None:
        hallazgos.append((CODE_REQUEST_INVALID, "approval debe ser None cuando mode es autonomous"))

    generated_at = d["generated_at"]
    if not isinstance(generated_at, str) or generated_at == "":
        hallazgos.append((CODE_REQUEST_INVALID, f"generated_at inválido {generated_at!r}"))

    timed_out = d["timed_out"]
    if not isinstance(timed_out, bool):
        hallazgos.append((CODE_REQUEST_INVALID, f"timed_out: se esperaba bool, se recibió {type(timed_out).__name__}"))

    return hallazgos


@dataclass(frozen=True)
class ExecutionRecord:
    """Evidencia de una ejecución del runtime del Lead. Serialización
    determinista: `to_dict()` construye el dict con ORDEN DE CLAVES FIJO
    (`_EXECUTION_RECORD_CLAVES`), de modo que `to_dict()`/`from_dict()` son
    inversas exactas (mismos bytes al re-serializar con `canonical_json`).

    `approval` es un `dict` plano ya serializado por el llamador (NO un tipo
    de `tools.autonomy`, R7/R1: este módulo no conoce `autonomy`)."""

    execution_id: str
    command_form: str
    argv: tuple
    code_hash: Optional[str]
    exit_code: int
    duration_seconds: float
    stdout_summary: str
    stderr_summary: str
    outputs_hash: Optional[str]
    executed_by: str
    mode: str
    approval: Optional[dict]
    generated_at: str
    timed_out: bool

    def __post_init__(self) -> None:
        argv = tuple(self.argv)
        candidato = {
            "execution_id": self.execution_id,
            "command_form": self.command_form,
            "argv": argv,
            "code_hash": self.code_hash,
            "exit_code": self.exit_code,
            "duration_seconds": self.duration_seconds,
            "stdout_summary": self.stdout_summary,
            "stderr_summary": self.stderr_summary,
            "outputs_hash": self.outputs_hash,
            "executed_by": self.executed_by,
            "mode": self.mode,
            "approval": self.approval,
            "generated_at": self.generated_at,
            "timed_out": self.timed_out,
        }
        hallazgos = _validar_execution_record_dict(candidato)
        if hallazgos:
            code, motivo = hallazgos[0]
            raise ExecutionError(code, motivo)
        object.__setattr__(self, "argv", argv)
        object.__setattr__(self, "duration_seconds", float(self.duration_seconds))
        if self.approval is not None:
            object.__setattr__(self, "approval", dict(self.approval))

    def to_dict(self) -> dict:
        return {
            "execution_id": self.execution_id,
            "command_form": self.command_form,
            "argv": list(self.argv),
            "code_hash": self.code_hash,
            "exit_code": self.exit_code,
            "duration_seconds": self.duration_seconds,
            "stdout_summary": self.stdout_summary,
            "stderr_summary": self.stderr_summary,
            "outputs_hash": self.outputs_hash,
            "executed_by": self.executed_by,
            "mode": self.mode,
            "approval": dict(self.approval) if self.approval is not None else None,
            "generated_at": self.generated_at,
            "timed_out": self.timed_out,
        }

    @classmethod
    def from_dict(cls, d: Any) -> "ExecutionRecord":
        hallazgos = _validar_execution_record_dict(d)
        if hallazgos:
            code, motivo = hallazgos[0]
            raise ExecutionError(code, motivo)
        return cls(
            execution_id=d["execution_id"],
            command_form=d["command_form"],
            argv=tuple(d["argv"]),
            code_hash=d["code_hash"],
            exit_code=d["exit_code"],
            duration_seconds=d["duration_seconds"],
            stdout_summary=d["stdout_summary"],
            stderr_summary=d["stderr_summary"],
            outputs_hash=d["outputs_hash"],
            executed_by=d["executed_by"],
            mode=d["mode"],
            approval=d["approval"],
            generated_at=d["generated_at"],
            timed_out=d["timed_out"],
        )

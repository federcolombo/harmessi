"""Hook `PreToolUse` de presupuesto de sesión (Sesión A,
`20260908-control-determinista-sesiones`). Solo biblioteca estándar, mismo
patrón que `tools/dsguard/{core,sdd,repo}.py`.

Se invoca vía `tools/dsguard/hook_launcher_presupuesto.sh`, que resuelve el
repo compartido con `git` y ejecuta este script bajo el intérprete de ese
repo (`repo_root/.venv/Scripts/python.exe`) -- este módulo aprovecha eso para
usar directamente `sys.executable` como intérprete autorizado, igual que
`tools/nbrunner/hook_validar_comando.py`.

Contrato de entrada: JSON por stdin con el payload de la tool call de Claude
Code (`tool_name`, `tool_input`, opcionalmente `agent_id`/`agent_type`
para subagentes).

Contrato de salida: para denegar, mensaje explicativo por stderr y `exit 2`.
Para permitir, `exit 0` sin salida por stdout (mismo contrato que
`hook_validar_comando.py`).

Lógica de decisión: ver `openspec/changes/20260908-control-determinista-sesiones/
design.md`, secciones 2 y 3 (puntos 1-5, 4a, 4b). Resumen:
- Sin sesión activa (o sin `control.json` legible bajo algún cambio de
  `openspec/changes/`): permite siempre -- fail-safe hacia permitir, nunca
  bloquea todo el repo por un `control.json` ausente/corrupto o un
  `deadline_utc` ilegible.
- Con sesión activa: primero el allowlist de diagnóstico/checkpoint (4a, `git
  status`/`git diff`/`ds_guard session note|status|close`, regex anclada, sin
  encadenamiento) -- se permite siempre. `Bash` y `PowerShell` comparten
  exactamente la misma lógica en todos los puntos de decisión (allowlist 4a y
  bloqueo por presupuesto): en Windows, PowerShell no puede quedar como vía de
  evasión del control. Para todo lo demás:
  - `minutos_restantes <= 0`: deniega `Agent`/`SendMessage`/`Write`/`Edit`/
    cualquier `Bash`/`PowerShell` fuera del allowlist.
  - `0 < minutos_restantes <= 5`: deniega `Agent` nuevo y `SendMessage` que
    sea continuación de un `agent_id` ya registrado en `subagentes`;
    `Write`/`Edit`/`Bash`/`PowerShell` (fuera del allowlist) siguen permitidos.
  - `minutos_restantes > 5`: permite.
- `SendMessage` cuyo `to` no matchea ninguna clave de `subagentes`: antes del
  deadline se permite sin contar (aunque esté en la ventana de 5 min);
  vencido el deadline se deniega igual que cualquier otro `SendMessage`.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Optional

# Raíz del repo: este script vive en `tools/dsguard/`, así que `parents[2]`
# es la raíz -- sin necesidad de invocar `git` de nuevo desde Python (ya lo
# hizo `hook_launcher_presupuesto.sh` para decidir bajo qué intérprete correr
# esto).
REPO_ROOT = Path(__file__).resolve().parents[2]

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dsguard import core  # noqa: E402


VENTANA_AVISO_MINUTOS = 5


def normalizar_interprete(ruta: str) -> str:
    """Igual criterio que `tools/nbrunner/hook_validar_comando.py`: comparación
    exacta post-normalización de separadores/mayúsculas, nunca una regex
    permisiva que acepte cualquier binario con forma de ruta de venv."""
    return os.path.normcase(os.path.normpath(ruta))


INTERPRETE_AUTORIZADO = normalizar_interprete(sys.executable) if sys.executable else None

# Allowlist 4a: regex ancladas al inicio y al final de la cadena de comando
# completa. Nada de prefijo/sufijo/encadenado -- `&&`, `;`, `|`, backticks,
# `$(...)` o subshells hacen que la cadena completa deje de matchear y se
# rechace (se trata como "no matchea el allowlist", igual que cualquier otro
# comando). La parte de flags/argumentos permite cualquier texto EXCEPTO los
# metacaracteres de shell que encadenan comandos (`&`, `;`, `|`, backtick,
# `$`, `(`, `)`, `<`, `>`) -- así "git status" y "git diff --check" matchean,
# pero "git status && rm -rf /" o "git status | tee log" no (el primer
# metacaracter corta el consumo del grupo opcional y el `$` final falla).
_CARACTERES_SEGUROS_TRAILING = r"[^&;|`$()<>\n]*"
_PATRON_GIT_STATUS_DIFF = re.compile(
    r"^git (status|diff)(?: " + _CARACTERES_SEGUROS_TRAILING + r")?$"
)

# `git diff --output=<archivo>`/`git diff -o <archivo>` ESCRIBEN un archivo en
# disco -- el allowlist 4a es exclusivamente de diagnóstico de solo lectura
# (el propio mensaje de bloqueo lo anuncia así), así que estos flags se
# excluyen explícitamente aunque matcheen `_PATRON_GIT_STATUS_DIFF`. Cubre
# `--output=x`, `--output x` y `-o` como flag independiente (no como parte de
# otra palabra), en cualquier posición del comando.
_PATRON_GIT_DIFF_FLAG_ESCRITURA = re.compile(r"(^|\s)(--output(=|\s)|-o(\s|$))")

# El intérprete se captura como token genérico entre comillas; la
# autorización real es la comparación exacta post-normalización contra
# `sys.executable`, no esta regex (mismo patrón que `PATRON_COMANDO` de
# hook_validar_comando.py). Mismo criterio anti-encadenado que arriba para
# los flags de `session note|status|close`.
_PATRON_DS_GUARD_SESSION = re.compile(
    r'^"(?P<interprete>[^"]+)" tools/ds_guard\.py session (note|status|close)'
    r"(?: " + _CARACTERES_SEGUROS_TRAILING + r")?$"
)


def _matchea_allowlist(comando: str, interprete_autorizado: Optional[str]) -> bool:
    if not isinstance(comando, str) or not comando:
        return False
    if _PATRON_GIT_STATUS_DIFF.match(comando):
        if _PATRON_GIT_DIFF_FLAG_ESCRITURA.search(comando):
            return False
        return True
    m = _PATRON_DS_GUARD_SESSION.match(comando)
    if m and interprete_autorizado:
        interprete_propuesto = normalizar_interprete(m.group("interprete"))
        return interprete_propuesto == interprete_autorizado
    return False


class ControlNoLegible(Exception):
    """control.json ausente/corrupto o deadline_utc ilegible: fail-safe hacia
    permitir la acción evaluada, nunca bloquear todo el repo (ver
    design.md, Riesgos)."""


def _hallar_sesion_activa(repo_root: Path) -> Optional[tuple[Path, dict, dict]]:
    """Busca, entre `openspec/changes/*/control.json`, una sesión con
    `estado_final == "activa"`. Devuelve `(control_path, control, sesion)` --
    `sesion` es una referencia dentro de `control["sesiones"]`, así que
    mutarla in-place (registrar un `Agent`, incrementar `continuaciones`)
    también muta `control`, listo para volver a escribirse con
    `core.escribir_control(control_path, control)`. Si no hay ninguno legible
    o ninguna sesión activa, devuelve `None` (caso normal: "sin sesión
    activa", se permite todo sin más). Nunca levanta: cualquier error de
    lectura/parseo de un `control.json` puntual se ignora y se sigue con el
    siguiente."""
    changes_dir = repo_root / "openspec" / "changes"
    if not changes_dir.is_dir():
        return None
    for change_dir in sorted(changes_dir.iterdir()):
        control_path = change_dir / "control.json"
        if not control_path.exists():
            continue
        try:
            control = core.leer_control(control_path)
        except (core.ControlJsonError, OSError, UnicodeDecodeError, AttributeError):
            # `AttributeError` incluido a propósito: `core.leer_control` hace
            # `datos.get("schema_version")` sin chequear el tipo primero, así
            # que un `control.json` que parsea a JSON válido pero no es un
            # objeto (lista, `null`, string) hace que `leer_control` mismo
            # levante `AttributeError` en vez de devolver el valor -- se trata
            # igual que cualquier otro control.json no legible: se ignora ese
            # cambio y se sigue con el siguiente (hallazgo bloqueante 1 del
            # reviewer, Sesión B).
            continue
        if not isinstance(control, dict):
            # Defensivo: por si `core.leer_control` alguna vez llega a
            # devolver un valor no-dict sin levantar (hoy no ocurre, ver
            # comentario arriba), no se itera `.get("sesiones")` sobre algo
            # que no lo soporta.
            continue
        for sesion in control.get("sesiones", []):
            if not isinstance(sesion, dict):
                continue
            if sesion.get("estado_final") == "activa":
                return control_path, control, sesion
    return None


def _minutos_restantes_seguro(sesion: dict) -> float:
    """`core.minutos_restantes`, pero fail-safe: si `deadline_utc` está
    ausente o mal formado, levanta `ControlNoLegible` para que el llamador
    permita la acción evaluada en vez de bloquear (ver design.md, Riesgos:
    "Reloj del sistema o formato de fecha")."""
    try:
        return core.minutos_restantes(sesion)
    except (KeyError, ValueError, TypeError) as exc:
        raise ControlNoLegible(f"deadline_utc ilegible en la sesión: {exc!r}") from exc


def _extraer_comando(tool_input: dict) -> Optional[str]:
    """Comando textual de la tool call. Sirve tanto para `Bash` como para
    `PowerShell`: ambas exponen el comando bajo la misma clave `command`."""
    valor = tool_input.get("command")
    return valor if isinstance(valor, str) else None


def _extraer_agent_id(payload: dict) -> Optional[str]:
    """Identificador registrado al lanzar el subagente. Se acepta cualquiera
    de `agent_id`/`agent_name`/`id` presente en el payload de la tool call
    `Agent`, según lo que exponga Claude Code -- se prioriza `agent_id` por
    ser el campo documentado."""
    tool_input = payload.get("tool_input") or {}
    for clave in ("agent_id", "agent_name", "id", "subagent_type", "name"):
        valor = tool_input.get(clave)
        if isinstance(valor, str) and valor:
            return valor
    return None


def _extraer_destino_sendmessage(payload: dict) -> Optional[str]:
    tool_input = payload.get("tool_input") or {}
    valor = tool_input.get("to")
    return valor if isinstance(valor, str) and valor else None


def evaluar(
    payload: dict,
    sesion: Optional[dict],
    interprete_autorizado: Optional[str],
) -> tuple[bool, str, bool]:
    """Devuelve `(permitido, motivo, sesion_modificada)`. Función pura salvo
    por la mutación in-place de `sesion["subagentes"]` cuando corresponde
    registrar un `Agent` nuevo o incrementar una continuación -- el llamador
    decide si persiste ese cambio a disco.

    `sesion` es `None` si no hay sesión activa: se permite sin más."""
    tool_name = payload.get("tool_name")

    if sesion is None:
        return True, "Sin sesión activa: el control de presupuesto no aplica.", False

    tool_input = payload.get("tool_input") or {}

    # Allowlist 4a (Bash/PowerShell git status/diff, ds_guard session
    # note|status|close): se permite siempre, incluso vencido el deadline,
    # sin mirar minutos_restantes. Bash y PowerShell comparten exactamente la
    # misma rama -- PowerShell no puede quedar como vía de evasión del
    # control en Windows.
    if tool_name in ("Bash", "PowerShell"):
        comando = _extraer_comando(tool_input)
        if _matchea_allowlist(comando, interprete_autorizado):
            return True, "Comando dentro del allowlist de diagnóstico/checkpoint.", False

    restantes = _minutos_restantes_seguro(sesion)

    if tool_name in ("Bash", "PowerShell"):
        if restantes <= 0:
            return (
                False,
                "🛑 PRESUPUESTO AGOTADO: el presupuesto de la sesión venció. Solo quedan "
                "disponibles 'git status'/'git diff' y 'ds_guard session note|status|close'.",
                False,
            )
        return True, f"{tool_name} fuera de la ventana de deadline vencido: permitido.", False

    if tool_name in ("Write", "Edit"):
        if restantes <= 0:
            return (
                False,
                "🛑 PRESUPUESTO AGOTADO: el presupuesto de la sesión venció, no se permite "
                "trabajo nuevo (Write/Edit).",
                False,
            )
        return True, "Dentro de presupuesto.", False

    if tool_name == "Agent":
        if restantes <= 0:
            return (
                False,
                "🛑 PRESUPUESTO AGOTADO: el presupuesto de la sesión venció, no se permiten "
                "convocatorias nuevas de subagente.",
                False,
            )
        if restantes <= VENTANA_AVISO_MINUTOS:
            return (
                False,
                f"⏸️ Quedan {restantes:.1f} min de presupuesto (≤5): se reserva el tiempo "
                "restante para verificación mínima y checkpoint; no se permiten convocatorias "
                "nuevas de subagente.",
                False,
            )
        agent_id = _extraer_agent_id(payload)
        if agent_id:
            subagentes = sesion.setdefault("subagentes", {})
            subagentes[agent_id] = {
                "continuaciones": 0,
                "ultimo_evento_utc": core.ahora_utc(),
            }
            return True, "Agent nuevo registrado.", True
        return True, "Agent nuevo (sin agent_id identificable): permitido, no registrado.", False

    if tool_name == "SendMessage":
        subagentes = sesion.get("subagentes", {})
        destino = _extraer_destino_sendmessage(payload)

        if destino is not None and destino in subagentes:
            # Continuación de un subagente ya registrado.
            if restantes <= 0:
                return (
                    False,
                    "🛑 PRESUPUESTO AGOTADO: el presupuesto de la sesión venció, no se "
                    "permiten continuaciones de subagente.",
                    False,
                )
            if restantes <= VENTANA_AVISO_MINUTOS:
                return (
                    False,
                    f"⏸️ Quedan {restantes:.1f} min de presupuesto (≤5): no se permiten "
                    "continuaciones nuevas de subagente.",
                    False,
                )
            entrada = subagentes[destino]
            max_continuaciones = (
                sesion.get("presupuesto", {}).get("max_continuaciones_por_subagente", 1)
            )
            if entrada.get("continuaciones", 0) >= max_continuaciones:
                return (
                    False,
                    f"Ya se usó la continuación automática permitida para '{destino}'; "
                    "requiere aprobación manual antes de relanzarlo.",
                    False,
                )
            entrada["continuaciones"] = entrada.get("continuaciones", 0) + 1
            entrada["ultimo_evento_utc"] = core.ahora_utc()
            return True, "Continuación de subagente permitida (contada).", True

        # `to` ambiguo (no matchea ninguna clave registrada): antes del
        # deadline se permite sin contar; vencido el deadline se deniega
        # igual que cualquier otro SendMessage, sin excepción por ambigüedad
        # (decisión aprobada 2026-09-08, design.md §3 punto 4).
        if restantes <= 0:
            return (
                False,
                "🛑 PRESUPUESTO AGOTADO: el presupuesto de la sesión venció, no se permite "
                "ningún SendMessage.",
                False,
            )
        return True, "SendMessage a destino no registrado como subagente: permitido, sin contar.", False

    # Cualquier otra herramienta no cubierta por el matcher del hook (no
    # debería llegar acá si el `matcher` de settings.json está bien
    # configurado, pero por robustez se permite sin evaluar).
    return True, f"Herramienta '{tool_name}' fuera del alcance de este hook: permitida.", False


def main() -> int:
    try:
        payload_texto = sys.stdin.read()
    except Exception as exc:  # noqa: BLE001 - fail-safe hacia permitir, nunca bloquear todo
        print(f"hook_presupuesto: no se pudo leer stdin ({exc!r}); se permite la acción.", file=sys.stderr)
        return 0

    try:
        payload = json.loads(payload_texto)
        if not isinstance(payload, dict):
            raise ValueError("payload no es un objeto JSON")
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"hook_presupuesto: JSON de entrada inválido ({exc!r}); se permite la acción.", file=sys.stderr)
        return 0

    try:
        repo_root = REPO_ROOT
        encontrado = _hallar_sesion_activa(repo_root)
    except Exception as exc:  # noqa: BLE001 - fail-safe: control.json ilegible no bloquea el repo
        print(
            f"hook_presupuesto: no se pudo resolver la sesión activa ({exc!r}); se permite la acción.",
            file=sys.stderr,
        )
        return 0

    if encontrado is None:
        control_path, control, sesion = None, None, None
    else:
        control_path, control, sesion = encontrado

    if not INTERPRETE_AUTORIZADO:
        print(
            "hook_presupuesto: no se pudo resolver el intérprete autorizado; se permite la acción "
            "(fail-safe), pero el allowlist de 'ds_guard session ...' no podrá matchear.",
            file=sys.stderr,
        )

    try:
        permitido, motivo, modificado = evaluar(payload, sesion, INTERPRETE_AUTORIZADO)
    except ControlNoLegible as exc:
        print(f"hook_presupuesto: {exc}; se permite la acción (fail-safe).", file=sys.stderr)
        return 0
    except Exception as exc:  # noqa: BLE001 - fail-safe hacia permitir ante cualquier bug del hook
        print(f"hook_presupuesto: error inesperado ({exc!r}); se permite la acción.", file=sys.stderr)
        return 0

    if modificado and control_path is not None and control is not None:
        try:
            core.escribir_control(control_path, control)
        except Exception as exc:  # noqa: BLE001 - no se falla la decisión por un error de escritura
            print(
                f"hook_presupuesto: no se pudo persistir control.json ({exc!r}); "
                "la decisión de esta invocación sigue en pie.",
                file=sys.stderr,
            )

    if permitido:
        return 0

    print(motivo, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())

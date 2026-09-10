"""Hook `PreToolUse` del agente `notebook-runner` (Sesión 5, reescritura de
`20260907-notebook-runner-controlado` tras el fail-open confirmado empíricamente
y los dos bugs de regex encontrados por `data-science-reviewer`).

Este script ya NO se invoca directamente por Claude Code: lo invoca
`tools/nbrunner/hook_launcher.py`, que resuelve el repo compartido con `git`
(soporta worktrees, ver `tools/launcher_common.py`) y lo ejecuta bajo el
Python real del `.venv` de ese repo -- respetando `venv_dir` de
`control.json` y el layout correcto según el SO (`Scripts/python.exe` en
Windows, `bin/python` en POSIX) -- garantía que este módulo aprovecha para no
tener que volver a invocar `git` ni adivinar el intérprete autorizado: es,
literalmente, `sys.executable`.

Contrato de entrada: JSON por stdin con el payload de la tool call de Claude
Code. La restricción solo aplica cuando `agent_type == "notebook-runner"`
(campo documentado para subagentes: https://code.claude.com/docs/en/hooks.md,
"For subagents, input includes agent_id and agent_type fields"). Si el campo
está AUSENTE (Bash de la sesión principal, no es un subagente) o pertenece a
otro subagente, el hook permite sin evaluar el comando -- no es un error, es
el caso normal.

Contrato de salida: para denegar, mensaje explicativo por stderr y `exit 2`
(con exit code 2 Claude Code lee el motivo de bloqueo desde stderr e ignora
cualquier JSON en stdout -- no se emite JSON). Para permitir, `exit 0` sin
salida por stdout.

Fail-closed SOLO cuando de verdad no se puede determinar con seguridad que la
restricción no aplica o no se puede validar: JSON de stdin inválido, o --
siendo `agent_type == "notebook-runner"` -- falta `tool_input.command`, o no
se puede resolver el intérprete autorizado.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

# Raíz del repo: este script vive en `tools/nbrunner/`, así que `parents[2]`
# es la raíz -- sin necesidad de invocar `git` de nuevo desde Python (ya lo
# hizo `hook_launcher.py` para decidir bajo qué intérprete correr esto).
REPO_ROOT = Path(__file__).resolve().parents[2]


def normalizar_interprete(ruta: str) -> str:
    """Normaliza separadores de ruta y mayúsculas/minúsculas (Windows) para
    poder comparar dos rutas de intérprete por igualdad exacta post-
    normalización, en vez de aceptar cualquier binario con "forma" de ruta de
    venv (bug de regex permisiva corregido en esta reescritura)."""
    return os.path.normcase(os.path.normpath(ruta))


# El intérprete bajo el que corre este script ES el Python autorizado, porque
# `hook_launcher.py` ya garantizó que es el intérprete autorizado del `.venv`.
INTERPRETE_AUTORIZADO = normalizar_interprete(sys.executable) if sys.executable else None

# El intérprete se captura como token genérico entre comillas (sin restringir
# su forma): la autorización real es la comparación exacta post-normalización
# de `normalizar_interprete`, no esta regex.
# El manifest usa una clase de caracteres básica solo como filtro de forma
# (letras/dígitos/`_./-`); la autorización real es la resolución canónica +
# contención dentro de `repo_root/openspec/changes/**/runs/*.json`, con
# rechazo explícito de rutas absolutas ANTES de unir con `repo_root` (el
# gotcha de `Path(base) / ruta_absoluta` descartando `base` en silencio).
PATRON_COMANDO = re.compile(
    r'^"(?P<interprete>[^"]+)" tools/notebook_runner\.py run --manifest '
    r'(?P<manifest>[A-Za-z0-9_./-]+)(?: --dry-run| --execute)?$'
)


def _validar_manifest(manifest_str: str, repo_root: Path) -> tuple[bool, str]:
    """Rechaza rutas absolutas y traversal explícitamente antes de resolver
    contra `repo_root`, y exige que la ruta canónica quede dentro de
    `repo_root/openspec/changes/<id>/runs/<run-id>.json`."""
    # Rechazo explícito de absolutos ANTES de unir: `Path(base) / absoluta`
    # descartaría `base` en silencio y dejaría pasar cualquier ruta absoluta.
    if os.path.isabs(manifest_str):
        return False, "Comando rechazado: ruta de manifest absoluta no permitida."

    if ".." in Path(manifest_str).parts:
        return False, "Comando rechazado: traversal detectado en la ruta del manifest."

    try:
        repo_root_resuelto = repo_root.resolve()
        candidato = (repo_root_resuelto / manifest_str).resolve()
    except OSError as exc:
        return False, f"No se pudo resolver la ruta del manifest: {exc!r}"

    try:
        relativa = candidato.relative_to(repo_root_resuelto)
    except ValueError:
        return False, "Comando rechazado: la ruta del manifest escapa de la raíz del repositorio."

    partes = relativa.parts
    # openspec / changes / <id> / runs / <run-id>.json
    if (
        len(partes) != 5
        or partes[0] != "openspec"
        or partes[1] != "changes"
        or partes[3] != "runs"
        or not partes[4].endswith(".json")
    ):
        return (
            False,
            "Comando rechazado: el manifest debe estar bajo "
            "openspec/changes/<id>/runs/<run-id>.json.",
        )

    return True, "Manifest dentro de la raíz autorizada."


def validar_comando(
    agent_type: object,
    comando: object,
    repo_root: Path,
    interprete_autorizado: str,
) -> tuple[bool, str]:
    """Devuelve `(permitido, motivo)`. Función pura, testeable en aislamiento
    -- sin I/O ni dependencia del filesystem real más allá de resolver rutas
    en memoria (no requiere que el manifest exista).

    La restricción solo aplica si `agent_type == "notebook-runner"`; para
    cualquier otro valor (incluida la ausencia real, aunque acá se recibe ya
    resuelto por el llamador) se permite sin evaluar el comando.
    """
    if agent_type != "notebook-runner":
        return True, "agent_type distinto de notebook-runner: el hook no aplica."

    if not isinstance(comando, str) or not comando:
        return False, "Comando vacío o de tipo inválido."

    match = PATRON_COMANDO.match(comando)
    if not match:
        return (
            False,
            "Comando rechazado: no matchea el template exacto autorizado para "
            "notebook-runner (tools/notebook_runner.py run --manifest <ruta> "
            "[--dry-run|--execute]).",
        )

    interprete_propuesto = normalizar_interprete(match.group("interprete"))
    if interprete_propuesto != interprete_autorizado:
        return (
            False,
            "Comando rechazado: el intérprete propuesto no coincide exactamente "
            "con el Python autorizado del proyecto.",
        )

    return _validar_manifest(match.group("manifest"), repo_root)


def main() -> int:
    try:
        payload_texto = sys.stdin.read()
    except Exception as exc:  # noqa: BLE001 - fail-safe explícito, nunca aprobar
        print(f"No se pudo leer stdin del hook: {exc!r}", file=sys.stderr)
        return 2

    try:
        payload = json.loads(payload_texto)
    except json.JSONDecodeError as exc:
        print(f"JSON de entrada inválido: {exc}", file=sys.stderr)
        return 2

    if not isinstance(payload, dict):
        print("Payload del hook no es un objeto JSON.", file=sys.stderr)
        return 2

    agent_type = payload.get("agent_type")
    if agent_type != "notebook-runner":
        # Caso normal: Bash de la sesión principal (agent_type ausente) u
        # otro subagente distinto de notebook-runner. No aplica la
        # restricción: se permite sin evaluar el comando.
        return 0

    try:
        comando = payload["tool_input"]["command"]
    except (KeyError, TypeError):
        print("Falta 'tool_input.command' en el payload del hook.", file=sys.stderr)
        return 2

    if not INTERPRETE_AUTORIZADO:
        print("No se pudo resolver el intérprete autorizado del proyecto.", file=sys.stderr)
        return 2

    try:
        permitido, motivo = validar_comando(agent_type, comando, REPO_ROOT, INTERPRETE_AUTORIZADO)
    except Exception as exc:  # noqa: BLE001 - red de cierre fail-safe, nunca aprobar
        print(f"Error inesperado al validar el comando del hook: {exc!r}", file=sys.stderr)
        return 2

    if permitido:
        return 0

    print(motivo, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())

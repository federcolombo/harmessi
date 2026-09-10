"""Hook `PreToolUse` de protección de rutas (Bloque 3, reliability v0.2.0):
holdouts, `data/raw`, secretos y `.claude/guardrails.json`. Solo biblioteca
estándar, mismo patrón que `tools/dsguard/hook_presupuesto.py`.

Se invoca vía `tools/dsguard/hook_launcher_rutas.py`, que resuelve el repo
compartido con `git` (soporta worktrees, ver `tools/launcher_common.py`) y lo
ejecuta bajo el Python real del `.venv` de ese repo.

Contrato de entrada: JSON por stdin con el payload de la tool call de Claude
Code (`tool_name`, `tool_input`, opcionalmente `agent_type` para subagentes).

Contrato de salida: para denegar, mensaje explicativo por stderr y `exit 2`.
Para permitir, `exit 0` sin salida por stdout (mismo contrato que
`hook_presupuesto.py`/`hook_validar_comando.py`).

Fail-closed, a propósito, a diferencia de `hook_presupuesto.py`: ese hook es
fail-safe hacia permitir porque protege disponibilidad (presupuesto de
sesión) -- bloquear todo el repo por un `control.json` ilegible sería peor
que dejar pasar una acción. Este hook protege confidencialidad (holdouts,
secretos, `data/raw`) -- ahí la asimetría es la inversa: cualquier cosa que
no se pueda evaluar con certeza se deniega. `payload` inválido,
`guardrails.json` corrupto, o cualquier excepción inesperada durante la
evaluación: los tres casos deniegan, nunca permiten.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Raíz del repo: este script vive en `tools/dsguard/`, así que `parents[2]`
# es la raíz -- sin necesidad de invocar `git` de nuevo desde Python (ya lo
# hizo `hook_launcher_rutas.py` para decidir bajo qué intérprete correr esto).
REPO_ROOT = Path(__file__).resolve().parents[2]

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dsguard import pathguard  # noqa: E402


def main() -> int:
    try:
        payload_texto = sys.stdin.read()
    except Exception as exc:  # noqa: BLE001 - fail-closed: no se pudo leer el payload
        print(f"hook_rutas: no se pudo leer stdin ({exc!r}); se deniega por seguridad.", file=sys.stderr)
        return 2

    try:
        payload = json.loads(payload_texto)
        if not isinstance(payload, dict):
            raise ValueError("payload no es un objeto JSON")
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"hook_rutas: payload inválido ({exc!r}); se deniega por seguridad.", file=sys.stderr)
        return 2

    try:
        config = pathguard.cargar_config(REPO_ROOT)
    except pathguard.ConfigGuardrailsError as exc:
        print(f"hook_rutas: guardrails.json corrupto ({exc}); se deniega por seguridad.", file=sys.stderr)
        return 2

    try:
        permitido, motivo = pathguard.evaluar_tool_call(payload, config, REPO_ROOT)
    except Exception as exc:  # noqa: BLE001 - fail-closed: error interno del pathguard
        print(
            f"hook_rutas: error interno evaluando el tool call ({exc!r}); se deniega por seguridad.",
            file=sys.stderr,
        )
        return 2

    if permitido:
        return 0

    print(motivo, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env bash
# Lanzador del hook `PreToolUse` de presupuesto de sesión (Sesión A,
# `20260908-control-determinista-sesiones`).
#
# Análogo a `tools/nbrunner/hook_launcher.sh`: no depende de
# `${CLAUDE_PROJECT_DIR}/.venv` (en un worktree no hay `.venv` propio).
# Resuelve el repositorio Git compartido con `git rev-parse
# --path-format=absolute --git-common-dir`, calcula `repo_root` como el padre
# de ese `.git`, y ejecuta el hook real con el intérprete del `.venv` de ese
# repo compartido -- válido tanto desde el checkout principal como desde
# cualquier worktree.
#
# Fail-closed a nivel lanzador: si `git rev-parse` falla o el intérprete no
# existe, mensaje a stderr + exit 2. A este nivel todavía no se leyó el
# payload, así que esto es una falla operativa visible del lanzador, no un
# bypass del control de presupuesto -- distinto del fail-safe hacia permitir
# que aplica DENTRO de `hook_presupuesto.py` cuando `control.json` está
# ausente/corrupto (ver ese módulo).
set -uo pipefail

if [ -z "${CLAUDE_PROJECT_DIR:-}" ]; then
    echo "hook_launcher_presupuesto: CLAUDE_PROJECT_DIR no está definida." >&2
    exit 2
fi

git_common_dir="$(git -C "${CLAUDE_PROJECT_DIR}" rev-parse --path-format=absolute --git-common-dir 2>/dev/null)"
if [ -z "${git_common_dir}" ]; then
    echo "hook_launcher_presupuesto: no se pudo resolver el repositorio Git compartido (git rev-parse --git-common-dir falló)." >&2
    exit 2
fi

repo_root="$(dirname "${git_common_dir}")"
interprete="${repo_root}/.venv/Scripts/python.exe"

if [ ! -f "${interprete}" ]; then
    echo "hook_launcher_presupuesto: no se encontró el intérprete autorizado en ${interprete}." >&2
    exit 2
fi

exec "${interprete}" "${CLAUDE_PROJECT_DIR}/tools/dsguard/hook_presupuesto.py"

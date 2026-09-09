#!/usr/bin/env bash
# Lanzador del hook `PreToolUse` de `notebook-runner` (Sesión 5,
# `20260907-notebook-runner-controlado`).
#
# No depende de `${CLAUDE_PROJECT_DIR}/.venv` (ese era el bug de raíz del
# fail-open confirmado empíricamente: en un worktree no hay `.venv` propio).
# Resuelve el repositorio Git compartido con `git rev-parse
# --path-format=absolute --git-common-dir`, calcula `repo_root` como el padre
# de ese `.git`, y ejecuta el hook real con el intérprete del `.venv` de ese
# repo compartido -- válido tanto desde el checkout principal como desde
# cualquier worktree.
#
# Fail-closed a nivel lanzador: si `git rev-parse` falla o el intérprete no
# existe, mensaje a stderr + exit 2. A este nivel todavía no se leyó el
# payload, así que esto es una falla operativa visible, no un bypass -- se
# aplica a cualquier llamador (incluido Bash de la sesión principal), pero es
# preferible a un fail-open silencioso ante una instalación rota.
set -uo pipefail

if [ -z "${CLAUDE_PROJECT_DIR:-}" ]; then
    echo "hook_launcher: CLAUDE_PROJECT_DIR no está definida." >&2
    exit 2
fi

git_common_dir="$(git -C "${CLAUDE_PROJECT_DIR}" rev-parse --path-format=absolute --git-common-dir 2>/dev/null)"
if [ -z "${git_common_dir}" ]; then
    echo "hook_launcher: no se pudo resolver el repositorio Git compartido (git rev-parse --git-common-dir falló)." >&2
    exit 2
fi

repo_root="$(dirname "${git_common_dir}")"
interprete="${repo_root}/.venv/Scripts/python.exe"

if [ ! -f "${interprete}" ]; then
    echo "hook_launcher: no se encontró el intérprete autorizado en ${interprete}." >&2
    exit 2
fi

exec "${interprete}" "${CLAUDE_PROJECT_DIR}/tools/nbrunner/hook_validar_comando.py"

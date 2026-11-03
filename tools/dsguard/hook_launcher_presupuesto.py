"""Lanzador Python puro (cross-platform) del hook `PreToolUse` de
presupuesto de sesión. Reemplaza a `hook_launcher_presupuesto.sh` (Bloque 2,
reliability v0.2.0): misma lógica -- resolución de worktree + intérprete
autorizado del `.venv` -- sin depender de `bash` ni de ningún shell. Ver
`tools/launcher_common.py` (compartido con
`tools/nbrunner/hook_launcher.py`) para el detalle.
"""
from __future__ import annotations

import sys
from pathlib import Path

# `tools/dsguard/hook_launcher_presupuesto.py` -> `tools/dsguard` ->
# `tools`: agrega `tools/` al `sys.path` para poder importar
# `launcher_common` como paquete de nivel superior, mismo patrón que usa
# `hook_presupuesto.py` para importar `dsguard`.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from launcher_common import lanzar_hook  # noqa: E402

NOMBRE_LANZADOR = "hook_launcher_presupuesto"
HOOK_RELATIVO = "tools/dsguard/hook_presupuesto.py"

if __name__ == "__main__":
    sys.exit(lanzar_hook(NOMBRE_LANZADOR, HOOK_RELATIVO))

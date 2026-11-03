"""Lanzador Python puro (cross-platform) del hook `PreToolUse` de
`notebook-runner`. Reemplaza a `hook_launcher.sh` (Bloque 2, reliability
v0.2.0): misma lógica -- resolución de worktree + intérprete autorizado del
`.venv` -- sin depender de `bash` ni de ningún shell. Ver
`tools/launcher_common.py` (compartido con
`tools/dsguard/hook_launcher_presupuesto.py`) para el detalle.
"""
from __future__ import annotations

import sys
from pathlib import Path

# `tools/nbrunner/hook_launcher.py` -> `tools/nbrunner` -> `tools`: agrega
# `tools/` al `sys.path` para poder importar `launcher_common` como paquete
# de nivel superior, mismo patrón que usan `hook_presupuesto.py` /
# `hook_validar_comando.py` para importar `dsguard`/`nbrunner`.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from launcher_common import lanzar_hook  # noqa: E402

NOMBRE_LANZADOR = "hook_launcher"
HOOK_RELATIVO = "tools/nbrunner/hook_validar_comando.py"

if __name__ == "__main__":
    sys.exit(lanzar_hook(NOMBRE_LANZADOR, HOOK_RELATIVO))

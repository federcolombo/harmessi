"""Lanzador Python puro (cross-platform) del hook `PreToolUse` de protección
de rutas (Bloque 3, reliability v0.2.0). Mismo patrón que
`tools/dsguard/hook_launcher_presupuesto.py` y
`tools/nbrunner/hook_launcher.py`: reusa `tools/launcher_common.py` para la
resolución de repo compartido (soporta worktrees) e intérprete autorizado del
`.venv` -- sin depender de `bash` ni de ningún shell.
"""
from __future__ import annotations

import sys
from pathlib import Path

# `tools/dsguard/hook_launcher_rutas.py` -> `tools/dsguard` -> `tools`:
# agrega `tools/` al `sys.path` para poder importar `launcher_common` como
# paquete de nivel superior, mismo patrón que los otros dos launchers.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from launcher_common import lanzar_hook  # noqa: E402

NOMBRE_LANZADOR = "hook_launcher_rutas"
HOOK_RELATIVO = "tools/dsguard/hook_rutas.py"

if __name__ == "__main__":
    sys.exit(lanzar_hook(NOMBRE_LANZADOR, HOOK_RELATIVO))

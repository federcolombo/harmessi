"""Lanzador Python puro del hook de telemetría de subagentes
(`SubagentStart`/`SubagentStop`). A diferencia de `lanzar_hook`
(`tools/launcher_common.py`, fail-closed para hooks de seguridad), este
lanzador es FAIL-OPEN: cualquier fallo (variable ausente, repo no resuelto,
intérprete o script inexistente, import fallido, excepción, returncode != 0
del hook) se avisa por stderr y termina en exit 0, porque el hook es solo
telemetría y nunca debe frenar el trabajo. Los imports de `launcher_common`
son perezosos, dentro del `try`, para que un import fallido también sea
fail-open.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

NOMBRE_LANZADOR = "hook_launcher_subagentes"
HOOK_RELATIVO = "tools/dsguard/hook_subagentes.py"


def main() -> int:
    """Siempre 0; los avisos van a stderr."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from launcher_common import (  # noqa: E402
            resolver_repo_root,
            resolver_venv_dir,
            ruta_interprete_venv,
        )

        claude_project_dir = os.environ.get("CLAUDE_PROJECT_DIR", "")
        if not claude_project_dir:
            print(f"{NOMBRE_LANZADOR}: CLAUDE_PROJECT_DIR no está definida; se omite.", file=sys.stderr)
            return 0
        repo_root = resolver_repo_root(claude_project_dir)
        if repo_root is None:
            print(f"{NOMBRE_LANZADOR}: no se pudo resolver el repositorio Git; se omite.", file=sys.stderr)
            return 0
        interprete = ruta_interprete_venv(repo_root, resolver_venv_dir(repo_root))
        if not interprete.is_file():
            print(f"{NOMBRE_LANZADOR}: no se encontró el intérprete en {interprete}; se omite.", file=sys.stderr)
            return 0
        hook_path = Path(claude_project_dir) / HOOK_RELATIVO
        if not hook_path.is_file():
            print(f"{NOMBRE_LANZADOR}: no se encontró el hook en {hook_path}; se omite.", file=sys.stderr)
            return 0
        resultado = subprocess.run([str(interprete), str(hook_path)])
        if resultado.returncode != 0:
            print(f"{NOMBRE_LANZADOR}: el hook terminó con {resultado.returncode}; se ignora.", file=sys.stderr)
    except BaseException as exc:  # noqa: BLE001 -- fail-open deliberado (incluye ImportError)
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        print(f"{NOMBRE_LANZADOR}: error ignorado (fail-open): {exc!r}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

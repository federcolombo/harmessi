"""Lógica compartida de los lanzadores Python puros de los hooks `PreToolUse`
(`tools/nbrunner/hook_launcher.py`, `tools/dsguard/hook_launcher_presupuesto.py`)
y de los checks RUNTIME/CORE de `tools/harmessi/doctor.py` (Bloque 2,
reliability v0.2.0).

Reemplaza a los antiguos `hook_launcher.sh` / `hook_launcher_presupuesto.sh`:
misma lógica (resolver el repo Git compartido para soportar worktrees,
resolver el intérprete autorizado del `.venv` de ese repo), sin depender de
`bash` ni de ningún shell -- solo `subprocess` con listas de argumentos,
nunca `shell=True`.

Solo biblioteca estándar, mismo criterio que el resto de `tools/dsguard` y
`tools/nbrunner`.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

# Default de `ds_init` (`cli.py: --venv-dir`, default `.venv`) -- se usa acá
# solo cuando `control.json` no existe, no es legible, o no declara
# `configuracion.venv_dir`. Nunca se asume a ciegas: si el proyecto se
# instaló con `--venv-dir` distinto, `resolver_venv_dir` lo respeta.
VENV_DIR_POR_DEFECTO = ".venv"


def resolver_venv_dir(repo_root: Path) -> str:
    """`venv_dir` configurado en `<repo_root>/.ds_init/control.json` si
    existe y es legible; si no (ausente, corrupto, sin ese campo, o con un
    valor que no es un string no vacío), el default de `ds_init`
    (`.venv`). Nunca lanza: un `control.json` ausente o corrupto no es un
    fallo de seguridad acá, solo hace que se use el default."""
    ruta_control = repo_root / ".ds_init" / "control.json"
    try:
        contenido = json.loads(ruta_control.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return VENV_DIR_POR_DEFECTO

    if isinstance(contenido, dict):
        configuracion = contenido.get("configuracion")
        if isinstance(configuracion, dict):
            venv_dir = configuracion.get("venv_dir")
            if isinstance(venv_dir, str) and venv_dir:
                return venv_dir

    return VENV_DIR_POR_DEFECTO


def ruta_interprete_venv(repo_root: Path, venv_dir: str, *, windows: Optional[bool] = None) -> Path:
    """Ruta esperada del intérprete de un `.venv` creado con `python -m
    venv`, con el layout correcto según el sistema operativo: `Scripts/
    python.exe` en Windows, `bin/python` en POSIX (Linux/macOS) -- a
    diferencia del bug de los `.sh` originales, que hardcodeaban el layout
    de Windows sin importar dónde corrieran.

    `windows` es inyectable (default: `os.name == "nt"`) para poder testear
    ambos layouts desde cualquier sistema operativo real, sin parchear
    estado global."""
    if windows is None:
        windows = os.name == "nt"
    venv_path = repo_root / venv_dir
    if windows:
        return venv_path / "Scripts" / "python.exe"
    return venv_path / "bin" / "python"


def resolver_repo_root(claude_project_dir: str) -> Optional[Path]:
    """Repo Git compartido, resuelto igual que los `.sh` originales:
    `git -C <claude_project_dir> rev-parse --path-format=absolute
    --git-common-dir` -- válido tanto desde el checkout principal como desde
    cualquier worktree (un worktree no tiene `.venv` propio, así que el
    `.venv` autorizado es siempre el del repo compartido). Devuelve `None`
    si `git` no está disponible, el comando falla, o no imprime nada --
    nunca lanza."""
    try:
        resultado = subprocess.run(
            [
                "git",
                "-C",
                claude_project_dir,
                "rev-parse",
                "--path-format=absolute",
                "--git-common-dir",
            ],
            capture_output=True,
            text=True,
        )
    except OSError:
        return None

    if resultado.returncode != 0:
        return None

    git_common_dir = resultado.stdout.strip()
    if not git_common_dir:
        return None

    return Path(git_common_dir).parent


def lanzar_hook(nombre_lanzador: str, hook_relativo: str) -> int:
    """Lógica compartida de ambos lanzadores: resuelve el repo Git
    compartido (soporta worktrees), el intérprete autorizado del `.venv` de
    ese repo (respetando `venv_dir` de `control.json` si está configurado, y
    el layout correcto según el SO), y ejecuta `hook_relativo` -- resuelto
    contra `CLAUDE_PROJECT_DIR` (el checkout/worktree actual, no
    necesariamente `repo_root`: el script del hook es contenido versionado,
    presente en cualquier worktree) -- bajo ese intérprete, heredando
    stdin/stdout/stderr (mismo contrato que `exec` en los `.sh` originales:
    el hook real lee el payload JSON por stdin).

    Fail-closed a nivel lanzador (igual que los `.sh` que reemplaza): si
    `CLAUDE_PROJECT_DIR` no está definida, si no se puede resolver el repo
    compartido, si el intérprete no existe, o si el script del hook no
    existe, mensaje a stderr + exit 2. A este nivel todavía no se leyó el
    payload del hook, así que esto es una falla operativa visible del
    lanzador, no un bypass del guardrail real (ver
    `hook_presupuesto.py`/`hook_validar_comando.py` para su propio
    fail-safe hacia permitir cuando `control.json` está ausente/corrupto)."""
    claude_project_dir = os.environ.get("CLAUDE_PROJECT_DIR", "")
    if not claude_project_dir:
        print(f"{nombre_lanzador}: CLAUDE_PROJECT_DIR no está definida.", file=sys.stderr)
        return 2

    repo_root = resolver_repo_root(claude_project_dir)
    if repo_root is None:
        print(
            f"{nombre_lanzador}: no se pudo resolver el repositorio Git compartido "
            f"(git rev-parse --git-common-dir falló).",
            file=sys.stderr,
        )
        return 2

    venv_dir = resolver_venv_dir(repo_root)
    interprete = ruta_interprete_venv(repo_root, venv_dir)
    if not interprete.is_file():
        print(
            f"{nombre_lanzador}: no se encontró el intérprete autorizado en {interprete}.",
            file=sys.stderr,
        )
        return 2

    hook_path = Path(claude_project_dir) / hook_relativo
    if not hook_path.is_file():
        print(
            f"{nombre_lanzador}: no se encontró el script del hook en {hook_path}.",
            file=sys.stderr,
        )
        return 2

    try:
        resultado = subprocess.run([str(interprete), str(hook_path)])
    except OSError as exc:
        print(f"{nombre_lanzador}: no se pudo ejecutar el hook real: {exc}", file=sys.stderr)
        return 2

    return resultado.returncode

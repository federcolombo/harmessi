"""Punto de entrada `python -m tools.reporting ...`."""
from __future__ import annotations

import sys

# La consola/pipe que invoca este CLI puede estar en una codificación distinta de
# UTF-8 (p. ej. cp1252 en Windows). Se fuerza stdout/stderr a UTF-8 real para que
# el texto en español y las rutas con caracteres no cp1252 sean deterministas y
# nunca provoquen `UnicodeEncodeError` -- mismo patrón que `tools/dsimpact/__main__.py`.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from .cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

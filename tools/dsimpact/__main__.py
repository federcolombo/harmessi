import sys

# La consola/pipe que invoca este CLI puede estar en una codificación distinta
# de UTF-8 (p. ej. cp1252 en Windows). Forzamos stdout/stderr a UTF-8 real para
# que el texto en español (tildes, "ñ") y el JSON de salida sean deterministas
# sin importar quién lo invoque (terminal, subprocess de test, etc.) -- mismo
# patrón que `tools/ds_guard.py`.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from .cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())

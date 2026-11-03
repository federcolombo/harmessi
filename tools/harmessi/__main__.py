"""Punto de entrada de `python -m tools.harmessi`."""
import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())

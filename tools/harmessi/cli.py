"""Interfaz de línea de comandos de `harmessi` (Bloque 2, reliability
v0.2.0). En v0.2 soporta únicamente el subcomando `doctor`; `init`
(hoy `python -m tools.ds_init`), `update` y `uninstall` quedan para
versiones futuras -- ver `tools/harmessi/__init__.py`.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import doctor as doctor_mod


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m tools.harmessi",
        description="CLI de Harmessi. En v0.2 soporta únicamente el subcomando 'doctor'.",
    )
    subparsers = parser.add_subparsers(dest="subcomando", required=True)

    doctor_parser = subparsers.add_parser(
        "doctor", help="Diagnóstico de salud (solo lectura) de una instalación de Harmessi."
    )
    doctor_parser.add_argument(
        "--destino",
        default=".",
        help="Repo del proyecto a diagnosticar (default: directorio actual).",
    )

    return parser


def main(argv: list = None) -> int:
    parser = construir_parser()
    args = parser.parse_args(argv)

    if args.subcomando == "doctor":
        try:
            resultados, codigo = doctor_mod.ejecutar(Path(args.destino))
        except Exception as exc:  # noqa: BLE001 - defensa final: doctor no debe crashear crudo
            print(f"[ABORTADO] harmessi doctor: fallo inesperado: {exc!r}", file=sys.stderr)
            return 1
        print(doctor_mod.formatear(resultados))
        return codigo

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())

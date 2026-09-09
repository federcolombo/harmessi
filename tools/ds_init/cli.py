"""Interfaz de línea de comandos de `ds_init` (R3).

`--dry-run` es el comportamiento por defecto: corre preflight + planner e
imprime el plan, sin tocar el disco del destino. `--execute` corre lo mismo y
además ejecuta la escritura real (`writer.py`: staging + journal + rollback,
R11) tras el preflight y la construcción del plan.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import writer
from .manifest import raiz_repo_origen
from .planner import construir_plan, formatear_plan
from .preflight import DestinoInvalidoError, validar_destino
from .version import HARNESS_VERSION

# Identificador público de CLI (R2). El mapeo a su directorio real bajo
# `profiles/` (con guion bajo, no se renombra) vive únicamente en
# `manifest.PERFILES` / `manifest.resolver_dir_perfil` — no se duplica acá.
PERFIL_MVP = "python-jupyter-data"


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m tools.ds_init",
        description="Inicializador del harness de agentes/tooling para proyectos "
        "de ciencia de datos (perfil python-jupyter-data).",
    )
    parser.add_argument("--destino", required=True, help="Repo local destino (debe existir, ser Git, working tree limpio).")
    parser.add_argument("--nombre", required=True, help="Nombre del proyecto, usado en placeholders de plantillas.")
    parser.add_argument("--notebooks-dir", default="notebooks", help="Directorio de notebooks del proyecto destino (default: notebooks).")
    parser.add_argument("--venv-dir", default=".venv", help="Directorio del entorno virtual del proyecto destino (default: .venv).")
    parser.add_argument("--integrar-claude", action="store_true", help="Integra un bloque delimitado en un CLAUDE.md ya existente (R9).")

    modo = parser.add_mutually_exclusive_group()
    modo.add_argument("--dry-run", action="store_true", help="Informa el plan, no escribe nada (comportamiento por defecto).")
    modo.add_argument("--execute", action="store_true", help="Ejecuta la escritura real, tras preflight exitoso.")

    return parser


def _contexto_placeholders(args: argparse.Namespace) -> dict:
    return {
        "NOMBRE_PROYECTO": args.nombre,
        "NOTEBOOKS_DIR": args.notebooks_dir,
        "VENV_DIR": args.venv_dir,
        "FECHA_INSTALACION": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "HARNESS_VERSION": HARNESS_VERSION,
        # Lista dura de rutas siempre-prohibidas de tools/nbrunner/manifest.py
        # en el proyecto destino (R6/§3 de design.md): vacía por defecto, cada
        # proyecto la completa a mano según sus propios datasets sensibles.
        "RUTAS_PROHIBIDAS_JSON": "[]",
    }


def main(argv: list = None) -> int:
    parser = construir_parser()
    args = parser.parse_args(argv)

    destino = Path(args.destino)

    try:
        validar_destino(destino)
    except DestinoInvalidoError as exc:
        print(f"[ABORTADO] {exc}", file=sys.stderr)
        return 1

    config = {
        "perfil": PERFIL_MVP,
        "nombre": args.nombre,
        "notebooks_dir": args.notebooks_dir,
        "venv_dir": args.venv_dir,
        "destino": args.destino,
        "integrar_claude": args.integrar_claude,
        "placeholders": _contexto_placeholders(args),
    }

    plan = construir_plan(PERFIL_MVP, destino, config)
    print(formatear_plan(plan))

    if args.execute:
        resultado = writer.instalar(plan, destino, config)
        print(
            f"\n[EXECUTE] Instalación completa: {len(resultado.aplicados)} archivo(s) "
            f"aplicado(s), {len(resultado.omitidos)} omitido(s) por colisión existente."
        )
        if resultado.omitidos:
            print("Omitidos (ya existían en el destino, sin sobrescribir):")
            for ruta_relativa in resultado.omitidos:
                print(f"  {ruta_relativa}")
        print(f"Archivo de control: {resultado.control_path}")
        return 0

    print("\n[DRY-RUN] No se escribió ni modificó ningún archivo del destino.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

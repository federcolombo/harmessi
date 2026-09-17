"""Interfaz de línea de comandos de `harmessi` (Bloque 2, reliability
v0.2.0; subcomando `providers` agregado en v0.5 Change 0,
`multi-provider-adapters`). Soporta `doctor` y `providers`; `init`
(hoy `python -m tools.ds_init`), `update` y `uninstall` quedan para
versiones futuras -- ver `tools/harmessi/__init__.py`.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import doctor as doctor_mod


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m tools.harmessi",
        description="CLI de Harmessi. Soporta los subcomandos 'doctor' y 'providers'.",
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

    providers_parser = subparsers.add_parser(
        "providers", help="Adapters de proveedor de IA (v0.5 Change 0)."
    )
    providers_subparsers = providers_parser.add_subparsers(
        dest="providers_subcomando", required=True
    )
    providers_list_parser = providers_subparsers.add_parser(
        "list", help="Detecta y lista los proveedores registrados (claude_code, codex, gemini, grok)."
    )
    providers_list_parser.add_argument(
        "--json", action="store_true", help="Formato de salida JSON en vez de tabla de texto."
    )

    return parser


def _formatear_providers_tabla(infos: list) -> str:
    """Tabla de texto simple (provider_id, available, version, detail),
    mismo criterio de `doctor.formatear`: una línea por entrada, sin
    dependencias de terceros."""
    lineas = ["Harmessi providers"]
    for info in infos:
        version = info.version or "-"
        lineas.append(
            f"[{'OK' if info.available else 'NO'}] {info.provider_id}: version={version} -- {info.detail}"
        )
    return "\n".join(lineas)


def _providers_info_a_dict(info) -> dict:
    return {
        "provider_id": info.provider_id,
        "display_name": info.display_name,
        "cli_command": info.cli_command,
        "available": info.available,
        "authenticated": info.authenticated,
        "version": info.version,
        "capabilities": {
            "streaming": info.capabilities.streaming,
            "tool_use": info.capabilities.tool_use,
            "thinking_effort": info.capabilities.thinking_effort,
            "handoff": info.capabilities.handoff,
        },
        "detail": info.detail,
    }


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

    if args.subcomando == "providers" and args.providers_subcomando == "list":
        # Import diferido (mismo criterio que `core.list_providers`): evita
        # cargar los 4 adapters cuando el subcomando invocado es 'doctor'.
        from tools.providers import list_providers

        try:
            infos = list_providers()
        except Exception as exc:  # noqa: BLE001 - defensa final, mismo criterio que 'doctor'
            print(f"[ABORTADO] harmessi providers list: fallo inesperado: {exc!r}", file=sys.stderr)
            return 1

        if args.json:
            print(json.dumps([_providers_info_a_dict(info) for info in infos], ensure_ascii=False, indent=2))
        else:
            print(_formatear_providers_tabla(infos))
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())

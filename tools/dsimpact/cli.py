"""CLI de `dsimpact` (R9, v0.4 Change 1): `python -m tools.dsimpact scan
--since REF [--json]` / `... --staged [--json]`. Implementación canónica --
el wrapper `ds_guard.py impact scan` delega acá, sin reimplementar nada.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dsguard import repo as repo_mod

from . import scan as scan_mod
from .git_source import GitSourceError


def _repo_root() -> Path:
    return repo_mod.find_repo_root(Path.cwd())


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dsimpact", description="Impact Preflight estático (v0.4 Change 1).")
    subparsers = parser.add_subparsers(dest="comando", required=True)
    p_scan = subparsers.add_parser(
        "scan", help="Escanea un diff de Git y reporta consumidores potencialmente afectados."
    )
    grupo = p_scan.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--since", default=None, help="Referencia Git (ej. HEAD~1) a comparar contra el estado actual.")
    grupo.add_argument("--staged", action="store_true", help="Compara el índice (staged) contra HEAD.")
    p_scan.add_argument("--json", action="store_true", dest="como_json")
    p_scan.set_defaults(func=cmd_scan)
    return parser


def cmd_scan(args: argparse.Namespace) -> int:
    try:
        repo_root = _repo_root()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 1
    try:
        resultado = scan_mod.ejecutar_scan(repo_root, args.since, args.staged)
    except GitSourceError as e:
        print(str(e), file=sys.stderr)
        return 1
    if args.como_json:
        print(json.dumps(resultado, indent=2, ensure_ascii=False))
    else:
        print(formatear_texto(resultado))
    return 0


def _linea_changed(entrada: dict) -> list:
    lineas = [f"  {entrada['path']} ({entrada['status']})" + (f" <- {entrada['old_path']}" if entrada.get("old_path") else "")]
    if entrada.get("parse_error"):
        lineas.append("    [parse_error] no se pudo parsear completamente -- ver archivo directamente")
    for s in entrada.get("symbols", []):
        lineas.append(f"    {s['kind']} {s['name']}: {s['change']}")
    for sc in entrada.get("string_contracts", []):
        lineas.append(f"    string_contract: {sc!r}")
    return lineas


def formatear_texto(resultado: dict) -> str:
    """Output humano compacto: 'Changed:' (archivo -> símbolos/strings),
    'Potentially affected:' (consumidor -> evidence_type -> changed_item, con
    ubicación), cerrando con 'Summary: N potentially affected consumers'
    (NUNCA 'N broken consumers')."""
    lineas = ["Impact Preflight"]
    ref = resultado.get("since") if not resultado.get("staged") else "staged"
    lineas.append(f"  modo: {'staged' if resultado.get('staged') else f'since={ref}'}")
    lineas.append("")
    lineas.append("Changed:")
    if not resultado.get("changed"):
        lineas.append("  (sin cambios)")
    for entrada in resultado.get("changed", []):
        lineas.extend(_linea_changed(entrada))

    lineas.append("")
    lineas.append("Potentially affected:")
    if not resultado.get("findings"):
        lineas.append("  (ningún consumidor potencial detectado)")
    else:
        por_consumer: dict = {}
        for f in resultado["findings"]:
            por_consumer.setdefault(f["consumer"], []).append(f)
        for consumer in sorted(por_consumer):
            lineas.append(f"  {consumer}")
            for f in por_consumer[consumer]:
                lineas.append(
                    f"    [{f['evidence_type']}] '{f['changed_item']}' (source={f['source_changed']}, "
                    f"location={f['location']})"
                )

    summary = resultado.get("summary", {})
    lineas.append("")
    lineas.append(
        f"Summary: {summary.get('consumers', 0)} potentially affected consumers "
        f"({summary.get('findings', 0)} findings, archivos cambiados={summary.get('changed_files', 0)}, "
        f"changed_items={summary.get('changed_items', 0)})"
    )
    return "\n".join(lineas)


def main(argv=None) -> int:
    parser = construir_parser()
    args = parser.parse_args(argv)
    return args.func(args)

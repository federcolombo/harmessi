"""CLI de reporting gobernado: `python -m tools.reporting <subcomando> ...`
(v0.6 Change 1, `20260918-reporting-governance`, spec R18).

Subcomandos (solo lectura: esta CLI no escribe nada en disco):
    check-inputs       aislamiento de inputs de un flujo (`check_flow_inputs`)
    check-destination  destino de un reporte (`evaluate_destination`)
    validate           puerta completa sobre un directorio de reporte persistido
                       (`validation.validate_report_dir`; v0.6 Change 3)

`check-inputs` suma el aislamiento por hash (`REPORT-ISOLATION-HASH`, Change 3)
SOLO cuando el índice exploratory tiene entradas, falló, quedó truncado o hay
manifests exploratory ilegibles: sin ello su salida es la de siempre. La ausencia
de una línea `REPORT-ISOLATION-HASH` significa "no había manifests exploratory
indexados", NO que el chequeo no corrió.

Exit codes:
    0 sin FAIL
    1 al menos un FAIL (`checks.exit_code`)
    2 error de uso (argumentos inválidos, `report_id` fuera del contrato de ids)
    3 error de entorno (`--repo-root` inexistente o no es un directorio)

Salida en stdout: una línea por resultado (`[STATUS] CODE [subject] mensaje`) o,
con `--json`, un objeto con claves ordenadas `allowed`, `counts` y `results`.
Los mensajes de error de uso/entorno van a stderr. Las rutas relativas se
resuelven contra `--repo-root` (default: el cwd), como `pathguard`.

El Change 4 agrega `render` registrando su subparser en `_construir_parser`.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import re
import sys
from pathlib import Path

from . import core as reporting_core
from . import evidence
from . import governance
from . import validation

_checks = governance.checks


def _agregar_comunes(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--repo-root", default=None, dest="repo_root")
    parser.add_argument("--json", action="store_true", dest="como_json")


def _construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m tools.reporting", description=__doc__)
    subparsers = parser.add_subparsers(dest="comando", required=True)

    p_inputs = subparsers.add_parser(
        "check-inputs", help="Verifica que los inputs de un flujo no provengan de un output exploratorio."
    )
    p_inputs.add_argument("--flow-scope", required=True, choices=reporting_core.DECISION_SCOPES, dest="flow_scope")
    p_inputs.add_argument("--input", required=True, action="append", dest="inputs")
    _agregar_comunes(p_inputs)
    p_inputs.set_defaults(func=cmd_check_inputs)

    ayuda_destino = (
        "Verifica que el destino de un reporte sea seguro y coherente con su scope. "
        "Un exit 0 NO reemplaza el gate completo de `publish` (fuentes, holdout, cutoff)."
    )
    p_dest = subparsers.add_parser("check-destination", help=ayuda_destino, description=ayuda_destino)
    p_dest.add_argument("--report-id", required=True, dest="report_id")
    p_dest.add_argument("--scope", required=True, choices=reporting_core.DECISION_SCOPES)
    p_dest.add_argument("--report-kind", required=True, choices=reporting_core.REPORT_KINDS, dest="report_kind")
    p_dest.add_argument("--out-dir", required=True, dest="out_dir")
    p_dest.add_argument(
        "--sensitive-artifact",
        action="append",
        default=[],
        dest="sensitive_artifacts",
        help="Id de un artefacto sensible del reporte (repetible); exige un destino sensible declarado.",
    )
    _agregar_comunes(p_dest)
    p_dest.set_defaults(func=cmd_check_destination)

    ayuda_validate = (
        "Valida un directorio de reporte persistido (manifest, integridad de artefactos, fuentes, "
        "contenido, governance y aislamiento por hash). Solo lectura."
    )
    p_validate = subparsers.add_parser("validate", help=ayuda_validate, description=ayuda_validate)
    p_validate.add_argument("--dir", required=True, dest="report_dir")
    _agregar_comunes(p_validate)
    p_validate.set_defaults(func=cmd_validate)

    return parser


def _resolver_repo_root(args: argparse.Namespace):
    """`(Path, None)` o `(None, mensaje_de_error)`."""
    crudo = args.repo_root if args.repo_root is not None else str(Path.cwd())
    repo_root = Path(crudo).resolve()
    if not repo_root.is_dir():
        return None, f"--repo-root no existe o no es un directorio: {crudo}"
    return repo_root, None


_CONTROL = re.compile("[\x00-\x1f\x7f\x85  ]")


def _escapar(texto: str) -> str:
    """Escapa caracteres de control (y separadores de línea unicode) al estilo
    repr, para que un subject/mensaje no pueda inyectar líneas falsas."""
    return _CONTROL.sub(lambda m: m.group().encode("unicode_escape").decode("ascii"), texto)


def _linea(resultado) -> str:
    subject = f" [{_escapar(resultado.subject)}]" if resultado.subject else ""
    return f"[{resultado.status}] {resultado.code}{subject} {_escapar(resultado.message)}"


def _emitir(resultados: list, como_json: bool) -> int:
    if como_json:
        salida = {
            "allowed": governance.output_allowed(resultados),
            "counts": _checks.contar_por_status(resultados),
            "results": [r.to_dict() for r in resultados],
        }
        print(json.dumps(salida, sort_keys=True, indent=2))
    else:
        for resultado in resultados:
            print(_linea(resultado))
    return _checks.exit_code(resultados)


def cmd_check_inputs(args: argparse.Namespace) -> int:
    repo_root, error = _resolver_repo_root(args)
    if error is not None:
        print(error, file=sys.stderr)
        return 3
    resultados = governance.check_flow_inputs(repo_root, args.flow_scope, args.inputs)
    # Aditivo (Change 3): el chequeo por hash solo se agrega si hay artefactos
    # exploratory indexados o el índice falló (fail-closed); si no hay nada contra
    # qué comparar, la salida previa no cambia.
    estado = evidence.exploratory_index_status(repo_root)  # una sola indexación
    if estado.index or estado.error is not None or estado.truncated or estado.unreadable_manifests > 0:
        resultados = resultados + evidence.check_inputs_hash_isolation(
            repo_root, args.flow_scope, args.inputs, index=estado
        )
    return _emitir(resultados, args.como_json)


def cmd_validate(args: argparse.Namespace) -> int:
    repo_root, error = _resolver_repo_root(args)
    if error is not None:
        print(error, file=sys.stderr)
        return 3
    return _emitir(validation.validate_report_dir(repo_root, args.report_dir), args.como_json)


def cmd_check_destination(args: argparse.Namespace) -> int:
    # Se valida el contrato de ids/vocabularios construyendo un Report mínimo.
    try:
        reporte = reporting_core.Report(
            report_id=args.report_id,
            title=args.report_id,
            report_kind=args.report_kind,
            decision_scope=args.scope,
        )
    except reporting_core.ReportingContractError as exc:
        print(f"argumentos inválidos: {exc}", file=sys.stderr)
        return 2
    repo_root, error = _resolver_repo_root(args)
    if error is not None:
        print(error, file=sys.stderr)
        return 3
    ctx = governance.context_from_report(repo_root, reporte, args.out_dir, holdout_access="none")
    # El `Report` mínimo no tiene artefactos: los sensibles se declaran por flag.
    ctx = dataclasses.replace(ctx, sensitive_artifacts=tuple(args.sensitive_artifacts))
    return _emitir(governance.evaluate_destination(ctx), args.como_json)


def main(argv=None) -> int:
    parser = _construir_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:  # argparse sale con 2 (uso) o 0 (--help)
        return exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 2)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

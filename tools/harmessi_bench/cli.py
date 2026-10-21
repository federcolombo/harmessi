"""CLI de `harmessi_bench`: `python -m tools.harmessi_bench.cli run ...` /
`compare ...` (v0.5 Change 1, `harmessi-bench`).

Sin `__main__.py` propio en este Change (limitación aceptada, ver
`design.md`/`verification.md`): se invoca como
`python -m tools.harmessi_bench.cli`, no `python -m tools.harmessi_bench`.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path

from tools.harmessi_bench import compare as compare_mod
from tools.harmessi_bench import storage
from tools.harmessi_bench.core import EvalTarget
from tools.harmessi_bench.runner import run_scenario_set
from tools.harmessi_bench.scenarios import load_scenarios_con_version
from tools.harmessi_bench.suite import (
    calcular_cases_hash,
    load_suite_y_casos,
    render_resumen,
    resumir,
)

_ROOT_EVALS_DEFAULT = Path(".harmessi/evals")


def _mensaje_error(exc: Exception) -> str:
    """Mensaje limpio de un error de carga/lectura: ante `OSError` cita solo
    el nombre de archivo (no la ruta absoluta completa) y no un traceback."""
    if isinstance(exc, OSError):
        nombre = Path(str(exc.filename)).name if exc.filename else ""
        causa = exc.strerror or type(exc).__name__
        return f"{causa}: {nombre}" if nombre else causa
    return str(exc)


def _construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m tools.harmessi_bench.cli",
        description="Framework de evals de Harmessi (v0.5 Change 1).",
    )
    subparsers = parser.add_subparsers(dest="comando", required=True)

    p_run = subparsers.add_parser("run", help="Corre un set de escenarios contra un target.")
    origen = p_run.add_mutually_exclusive_group(required=True)
    origen.add_argument("--scenarios", default=None)
    origen.add_argument("--suite", default=None, help="Manifest de suite (.suite.json).")
    p_run.add_argument("--provider", required=True)
    p_run.add_argument("--model", default=None)
    p_run.add_argument("--effort", default=None)
    p_run.add_argument("--run-id", required=True, dest="run_id")
    p_run.add_argument("--json", action="store_true")
    # --root: flag interno para tests (permite apuntar a un tmp_path en vez de
    # .harmessi/evals), no es una API estable de usuario -- oculto de --help.
    p_run.add_argument("--root", default=None, help=argparse.SUPPRESS)
    p_run.set_defaults(func=cmd_run)

    p_compare = subparsers.add_parser("compare", help="Compara dos corridas guardadas.")
    p_compare.add_argument("--baseline", required=True)
    p_compare.add_argument("--candidate", required=True)
    p_compare.add_argument("--json", action="store_true")
    # --root: flag interno para tests, mismo criterio que en `run` -- oculto de --help.
    p_compare.add_argument("--root", default=None, help=argparse.SUPPRESS)
    p_compare.set_defaults(func=cmd_compare)

    p_check = subparsers.add_parser("suite-check", help="Valida el manifest de una suite.")
    p_check.add_argument("--suite", required=True)
    p_check.add_argument("--json", action="store_true")
    p_check.set_defaults(func=cmd_suite_check)

    return parser


def cmd_suite_check(args: argparse.Namespace) -> int:
    try:
        suite, escenarios = load_suite_y_casos(Path(args.suite))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        mensaje = _mensaje_error(exc)
        if args.json:
            print(json.dumps({"valida": False, "error": mensaje}, ensure_ascii=False, indent=2))
        else:
            print(f"suite inválida: {mensaje}", file=sys.stderr)
        return 1
    if args.json:
        print(
            json.dumps(
                {
                    "valida": True,
                    "suite_id": suite.suite_id,
                    "suite_version": suite.suite_version,
                    "suite_hash": suite.suite_hash,
                    "case_contract_version": suite.case_contract_version,
                    "casos": len(escenarios),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(
            f"suite válida: {suite.suite_id} v{suite.suite_version} "
            f"({len(escenarios)} casos) hash={suite.suite_hash}"
        )
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    # Import diferido de PROVIDER_REGISTRY (mismo criterio que
    # `tools/harmessi/cli.py` de Change 0): evita cargar los adapters de
    # proveedor cuando no hace falta.
    from tools.providers import PROVIDER_REGISTRY

    adapter = PROVIDER_REGISTRY.get(args.provider)
    if adapter is None:
        print(
            f"provider desconocido: {args.provider!r} (registrados: {sorted(PROVIDER_REGISTRY)})",
            file=sys.stderr,
        )
        return 1

    info = adapter.detect()
    if not info.available:
        print(f"provider {args.provider!r} no disponible: {info.detail}", file=sys.stderr)
        return 1

    suite = None
    try:
        if args.suite:
            suite, scenarios = load_suite_y_casos(Path(args.suite))
            cases_hash = suite.suite_hash
        else:
            version_casos, scenarios = load_scenarios_con_version(Path(args.scenarios))
            cases_hash = calcular_cases_hash(scenarios, version_casos)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"no se pudieron cargar los escenarios: {_mensaje_error(exc)}", file=sys.stderr)
        return 1
    target = EvalTarget(provider_id=args.provider, model=args.model, effort=args.effort)
    resultados = run_scenario_set(scenarios, target, adapter, args.run_id)

    root = Path(args.root) if args.root else _ROOT_EVALS_DEFAULT
    try:
        ruta = storage.save_run(
            args.run_id, resultados, target, root=root, suite=suite, cases_hash=cases_hash
        )
    except OSError as exc:
        print(f"no se pudo guardar la corrida: {_mensaje_error(exc)}", file=sys.stderr)
        return 1

    total = len(resultados)
    pasaron = sum(1 for resultado in resultados if resultado.score.passed)
    categorias = {escenario.scenario_id: escenario.category for escenario in scenarios}
    resumen = resumir(resultados, suite, categorias)

    if args.json:
        print(
            json.dumps(
                {
                    "run_id": args.run_id,
                    "total": total,
                    "pasaron": pasaron,
                    "ruta": str(ruta),
                    "resumen": resumen,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(f"harmessi-bench run {args.run_id}: {pasaron}/{total} escenarios pasaron -- {ruta}")
        if suite is not None:
            print(render_resumen(resumen))

    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    root = Path(args.root) if args.root else _ROOT_EVALS_DEFAULT
    try:
        baseline = storage.load_run(args.baseline, root=root)
        candidate = storage.load_run(args.candidate, root=root)
        reporte = compare_mod.compare_runs(baseline, candidate)
    except (OSError, ValueError) as exc:
        print(_mensaje_error(exc), file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(dataclasses.asdict(reporte), ensure_ascii=False, indent=2))
        return 0

    print(f"harmessi-bench compare {args.baseline} vs {args.candidate}")
    for entrada in reporte.regressions:
        print(f"  [REGRESSION] {entrada['scenario_id']}")
    for entrada in reporte.improvements:
        print(f"  [IMPROVEMENT] {entrada['scenario_id']}")
    for scenario_id in reporte.solo_en_baseline:
        print(f"  [SOLO EN BASELINE] {scenario_id}")
    for scenario_id in reporte.solo_en_candidate:
        print(f"  [SOLO EN CANDIDATE] {scenario_id}")
    print(f"  {len(reporte.unchanged)} escenarios sin cambio")
    print(f"  VEREDICTO: {reporte.verdict} -- {reporte.verdict_reason}")

    return 0


def main(argv=None) -> int:
    parser = _construir_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

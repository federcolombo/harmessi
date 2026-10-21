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
from datetime import datetime, timezone
from pathlib import Path

from tools.harmessi_bench import compare as compare_mod
from tools.harmessi_bench import storage
from tools.harmessi_bench.core import EvalTarget
from tools.harmessi_bench.runmanifest import (
    advertencias_compatibilidad,
    agregar_sesion,
    campos_faltantes,
    construir_manifest,
    evaluar_compatibilidad,
    finalizar_manifest,
)
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


# Raíz del checkout de la que `runmanifest` lee skills/superficies/guardrails/Git.
# `None` => checkout de este paquete. Inyectable por tests (tmp).
_REPO_ROOT_MANIFEST = None


def _paso(resultado) -> bool:
    """`score.passed` de un `EvalResult` o de un dict cargado (resume)."""
    if isinstance(resultado, dict):
        return bool((resultado.get("score") or {}).get("passed"))
    return bool(resultado.score.passed)


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
    p_run.add_argument(
        "--resume",
        action="store_true",
        help="Completa una corrida existente (con run_manifest) corriendo solo los escenarios sin resultado ok.",
    )
    p_run.add_argument(
        "--seed", type=int, default=None, help="Seed informativo registrado en el manifest (el provider puede ignorarlo)."
    )
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

    try:
        storage.validar_run_id(args.run_id)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

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
    root = Path(args.root) if args.root else _ROOT_EVALS_DEFAULT

    # v0.13 Change 2: protección de `run_id` existente y resume seguro. Todo
    # se decide ANTES de invocar al provider y sin tocar el result existente.
    existente = None
    if (root / args.run_id / "result.json").exists():
        try:
            existente = storage.load_run(args.run_id, root=root)
        except (OSError, ValueError) as exc:
            print(
                f"no se pudo leer la corrida existente {args.run_id!r}: {_mensaje_error(exc)}",
                file=sys.stderr,
            )
            return 1
    manifest_existente = existente.get("run_manifest") if existente is not None else None
    if existente is not None and "run_manifest" in existente and not isinstance(manifest_existente, dict):
        # Fail-closed (L2): un run_manifest presente pero inválido no se trata como legado.
        print(
            f"la corrida existente {args.run_id!r} tiene un run_manifest inválido (no es un objeto); "
            "no se sobrescribe ni se reanuda",
            file=sys.stderr,
        )
        return 1

    if not args.resume and manifest_existente is not None:
        print(
            f"el run_id {args.run_id!r} ya existe con run_manifest: usá --resume o un run_id nuevo",
            file=sys.stderr,
        )
        return 1
    if args.resume and manifest_existente is None:
        print(
            f"--resume requiere una corrida existente con run_manifest (run_id={args.run_id!r})",
            file=sys.stderr,
        )
        return 1

    # H2: el manifest se calcula UNA vez, antes de correr (identidad vigente al
    # obtener la evidencia). M1: identidad no confiable => no se corre ni persiste.
    inicio_utc = datetime.now(timezone.utc).isoformat()
    manifest_previo = construir_manifest(
        args.run_id, target, suite=suite, cases_hash=cases_hash, seed=args.seed, repo_root=_REPO_ROOT_MANIFEST,
        started_utc=inicio_utc,
    )
    invalidos = campos_faltantes(manifest_previo)
    if invalidos:
        print(
            f"manifest incompleto, no se corre ni se persiste evidencia con identidad inválida: "
            f"{', '.join(invalidos)} ({', '.join(manifest_previo.get('problemas') or [])})",
            file=sys.stderr,
        )
        return 1

    previos_ok = {}
    if args.resume:
        incompatibilidades = evaluar_compatibilidad(manifest_existente, manifest_previo)
        if incompatibilidades:
            print(
                f"resume incompatible para run_id={args.run_id!r}: difieren {', '.join(incompatibilidades)}; "
                "no se mezcla evidencia (usá un run_id nuevo)",
                file=sys.stderr,
            )
            return 1
        for aviso in advertencias_compatibilidad(manifest_existente, manifest_previo):
            print(f"advertencia: {aviso}", file=sys.stderr)
        previos_ok = {
            r.get("scenario_id"): r
            for r in existente.get("resultados", [])
            if isinstance(r, dict) and r.get("ok") is True
        }
    pendientes = [escenario for escenario in scenarios if escenario.scenario_id not in previos_ok]

    if args.resume and not pendientes:
        print(f"harmessi-bench run {args.run_id}: nada pendiente, la corrida ya está completa (sin cambios)")
        return 0

    nuevos = run_scenario_set(pendientes, target, adapter, args.run_id)
    if args.resume:
        por_id = {resultado.scenario_id: resultado for resultado in nuevos}
        resultados = [
            previos_ok[e.scenario_id] if e.scenario_id in previos_ok else por_id[e.scenario_id]
            for e in scenarios
        ]
    else:
        resultados = nuevos

    # H2: si skills/superficies/guardrails cambiaron durante la corrida, la
    # evidencia no corresponde a la identidad registrada: no se escribe nada.
    manifest_final = construir_manifest(
        args.run_id, target, suite=suite, cases_hash=cases_hash, seed=args.seed, repo_root=_REPO_ROOT_MANIFEST,
        started_utc=inicio_utc,
    )
    if manifest_final.get("identity_hash") != manifest_previo.get("identity_hash"):
        print(
            "la configuración del harness (skills/superficies/guardrails) cambió durante la corrida: "
            "no se escribe ni se mezcla evidencia; repetí la corrida",
            file=sys.stderr,
        )
        return 1
    # Se persiste el manifest del inicio con solo `finished_utc` actualizado; en un
    # resume, los campos materiales provienen del manifest previo (ya validado
    # compatible) y se agrega una sesión.
    manifest = finalizar_manifest(manifest_previo)
    if args.resume:
        manifest = agregar_sesion(manifest_existente, manifest)
    try:
        ruta = storage.save_run(
            args.run_id, resultados, target, root=root, suite=suite, cases_hash=cases_hash,
            run_manifest=manifest,
        )
    except (OSError, ValueError) as exc:
        print(f"no se pudo guardar la corrida: {_mensaje_error(exc)}", file=sys.stderr)
        return 1

    total = len(resultados)
    pasaron = sum(1 for resultado in resultados if _paso(resultado))
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
    if reporte.config_diff:
        print(f"  CONFIG_DIFF: {', '.join(reporte.config_diff)}")
    print(f"  VEREDICTO: {reporte.verdict} -- {reporte.verdict_reason}")

    return 0


def _consola_segura() -> None:
    """Best-effort (v0.13 R8): con consola no UTF-8 los caracteres no
    representables se reemplazan en vez de lanzar `UnicodeEncodeError`."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


def main(argv=None) -> int:
    _consola_segura()
    parser = _construir_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

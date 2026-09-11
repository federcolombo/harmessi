"""CLI de `ds_profile`: `python -m tools.ds_profile run --input <ruta>
--output <dir> [...]` -- perfilado determinista de un dataset CSV/Parquet.

Exit codes (spec.md):
    0 corrida OK
    1 error de uso (archivo inexistente, extensión no soportada)
    2 denegado por guardrail (holdout, ver holdout_guard.py)
    3 dependencia faltante (pyarrow ausente al leer un .parquet)

Cada exit code distinto de 0 va acompañado de un mensaje a stderr. Nunca se
crea `profile.json` parcial si el exit code no es 0 -- `report.py` solo
escribe al final, después de calcular todo.

`--input`/`--output` se evalúan contra `.claude/guardrails.json` de
`repo_root = Path.cwd().resolve()` (holdout_guard.py) ANTES de intentar
abrir el archivo -- se asume que `ds_profile` se invoca desde la raíz del
proyecto, mismo criterio operativo que el resto de la CLI de Harmessi.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import holdout_guard, io_readers, report

DEFAULT_MAX_FILAS_EXACTAS = 2_000_000
DEFAULT_MAX_MB_EXACTOS = 500
DEFAULT_TOP_N = 20
DEFAULT_SEED = 42


def _construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m tools.ds_profile", description=__doc__)
    subparsers = parser.add_subparsers(dest="comando", required=True)

    p_run = subparsers.add_parser("run", help="Perfila un dataset CSV o Parquet.")
    p_run.add_argument("--input", required=True)
    p_run.add_argument("--output", required=True)
    p_run.add_argument("--profile-id", default=None, dest="profile_id")
    p_run.add_argument(
        "--max-filas-exactas", type=int, default=DEFAULT_MAX_FILAS_EXACTAS, dest="max_filas_exactas"
    )
    p_run.add_argument("--max-mb-exactos", type=int, default=DEFAULT_MAX_MB_EXACTOS, dest="max_mb_exactos")
    p_run.add_argument("--top-n", type=int, default=DEFAULT_TOP_N, dest="top_n")
    p_run.add_argument("--seed", type=int, default=DEFAULT_SEED)
    p_run.add_argument("--markdown", action="store_true")
    p_run.set_defaults(func=cmd_run)

    return parser


def cmd_run(args: argparse.Namespace) -> int:
    ruta_input = Path(args.input)
    ruta_output = Path(args.output)
    repo_root = Path.cwd().resolve()

    # Defensa en profundidad de holdouts: se evalúa ANTES de intentar abrir
    # el archivo (Requisito 5), incluso antes de chequear si existe.
    permitido, motivo = holdout_guard.verificar_permitido(ruta_input, repo_root)
    if not permitido:
        print(f"--input denegado por guardrail: {motivo}", file=sys.stderr)
        return 2

    permitido_salida, motivo_salida = holdout_guard.verificar_salida_permitida(ruta_output, repo_root)
    if not permitido_salida:
        print(f"--output denegado por guardrail: {motivo_salida}", file=sys.stderr)
        return 2

    try:
        resultado = report.generar_perfil(
            ruta_input=ruta_input,
            output_dir=ruta_output,
            profile_id=args.profile_id,
            max_filas_exactas=args.max_filas_exactas,
            max_mb_exactos=args.max_mb_exactos,
            top_n=args.top_n,
            seed=args.seed,
            incluir_markdown=args.markdown,
        )
    except report.ArchivoInvalidoError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except io_readers.FormatoNoSoportadoError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except io_readers.DependenciaFaltanteError as exc:
        print(str(exc), file=sys.stderr)
        return 3

    print(f"profile.json escrito en {resultado['ruta_profile_json']}")
    if resultado["ruta_profile_md"] is not None:
        print(f"profile.md escrito en {resultado['ruta_profile_md']}")
    return 0


def main(argv=None) -> int:
    parser = _construir_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

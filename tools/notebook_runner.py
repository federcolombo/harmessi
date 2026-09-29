"""CLI de nivel superior `tools/notebook_runner.py` (v0.8 Change 2,
`20260929-lead-execution-runtime`, T3, R11 de `spec.md`).

Cierra el gap del audit: `tools/nbrunner/hook_validar_comando.py` y el
agente `notebook-runner` ya esperan poder invocar

    "<intérprete>" tools/notebook_runner.py run --manifest <ruta> [--dry-run|--execute]

(`PATRON_COMANDO`, `tools/nbrunner/hook_validar_comando.py:66-69`, NO
modificado por este archivo). Este script SOLO ensambla lo que ya existe:
compone `tools.leadrun.notebooks.ejecutar_manifest` (que a su vez compone
`tools.nbrunner.{core,execute,fsdiff,manifest}`) -- ninguna lógica nueva de
validación de notebooks vive acá.

## Resolución de `repo_root`

Mismo patrón que `tools/ds_guard.py:_repo_root()` (`tools/ds_guard.py:57-58`):
`dsguard.repo.find_repo_root(Path.cwd())`.

## Resolución de `control.json`

El manifest vive siempre bajo `openspec/changes/<id>/runs/<run-id>.json`
(mismo layout exigido por `_validar_manifest`,
`tools/nbrunner/hook_validar_comando.py:72-110`). El `control.json` relevante
para `validar_aprobacion` es el del Change dueño de ese manifest --
`openspec/changes/<id>/control.json` -- MISMO archivo que ya usa
`ds_guard.py:_cargar_change`/`_change_dir` (`tools/ds_guard.py:61-82`) para
`gate_implementacion`/`approve`/`session`: no existe un `control.json` único
de proyecto, es uno por Change. Si ese `control.json` no existe todavía
(Change sin ninguna aprobación registrada), se trata como "sin
aprobaciones" (`{"aprobaciones": []}`), no como error -- consistente con que
`validar_aprobacion` ya sabe interpretar la ausencia de aprobación
(`"ausente"`/`"no_verificada"` según el modo). Si existe pero está corrupto
(`ControlJsonError`), es un error de uso/configuración real: exit code 2.

## Exit codes

- `0`: `ok=True`.
- `1`: `ok=False` por findings de validación o por ejecución fallida
  (notebook, fsdiff, aprobación bloqueante en `--execute`).
- `2`: error de uso (manifest inexistente, argumentos inválidos, repo no
  resoluble, `control.json` corrupto).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))
_REPO_ROOT_DIR = _TOOLS_DIR.parent
if str(_REPO_ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT_DIR))

from dsguard import core as dsguard_core  # noqa: E402
from dsguard import repo as dsguard_repo  # noqa: E402
from tools.leadrun import notebooks as leadrun_notebooks  # noqa: E402


def _repo_root() -> Path:
    """Mismo patrón que `tools/ds_guard.py:_repo_root()`
    (`tools/ds_guard.py:57-58`)."""
    return dsguard_repo.find_repo_root(Path.cwd())


def _control_path_para_manifest(manifest_path_abs: Path, repo_root: Path) -> Path:
    """`openspec/changes/<id>/control.json`, derivado del propio manifest
    (`openspec/changes/<id>/runs/<run-id>.json`, layout exigido por
    `_validar_manifest`, `tools/nbrunner/hook_validar_comando.py:72-110`) --
    mismo `control.json` que usa `ds_guard.py:_change_dir`
    (`tools/ds_guard.py:61-62`). Si el manifest no está en ese layout (no
    debería ocurrir si llegó por el comando autorizado, pero este script
    puede invocarse fuera del hook, p. ej. en tests), se usa el
    `control.json` de la raíz del repo como fallback -- no existe en este
    repo, así que en la práctica equivale a "sin aprobaciones"."""
    try:
        relativa = manifest_path_abs.resolve().relative_to(repo_root.resolve())
    except ValueError:
        relativa = manifest_path_abs
    partes = relativa.parts
    if len(partes) >= 3 and partes[0] == "openspec" and partes[1] == "changes":
        change_id = partes[2]
        return repo_root / "openspec" / "changes" / change_id / "control.json"
    return repo_root / "control.json"


def _leer_control_data(control_path: Path) -> dict:
    """`control.json` del Change dueño del manifest. Ausente => sin
    aprobaciones registradas todavía (no es un error de uso). Corrupto =>
    error de uso real (`ControlJsonError`), propagado como `SystemExit(2)`
    por el llamador."""
    if not control_path.exists():
        return {"aprobaciones": []}
    return dsguard_core.leer_control(control_path)


def _imprimir_finding(f: dict) -> None:
    ubicacion = f.get("ubicacion")
    sufijo = f" ({ubicacion})" if ubicacion else ""
    print(f"  - {f['codigo']}: {f['mensaje']}{sufijo}")


def _imprimir_resultado(resultado: dict) -> None:
    print(f"estado_aprobacion: {resultado['estado_aprobacion']}")
    print(f"ejecutado: {resultado['ejecutado']}")
    findings = resultado.get("findings") or []
    if findings:
        print("findings:")
        for f in findings:
            _imprimir_finding(f)
    else:
        print("findings: (ninguno)")

    resultado_ejecucion = resultado.get("resultado_ejecucion")
    if resultado_ejecucion is not None:
        print(f"resultado_ejecucion.exit_ok: {resultado_ejecucion['exit_ok']}")
        print(f"resultado_ejecucion.duracion_segundos: {resultado_ejecucion['duracion_segundos']:.2f}")
        print(f"resultado_ejecucion.timeout_alcanzado: {resultado_ejecucion['timeout_alcanzado']}")
        if resultado_ejecucion.get("error_info"):
            print(f"resultado_ejecucion.error_info: {resultado_ejecucion['error_info']}")

    fsdiff = resultado.get("fsdiff")
    if fsdiff is not None:
        print(f"fsdiff.permitidos: {fsdiff['permitidos']}")
        print(f"fsdiff.fuera_de_contrato: {fsdiff['fuera_de_contrato']}")
        print(f"fsdiff.cuarentena: {fsdiff['cuarentena']}")

    print(f"ok: {resultado['ok']}")


def _construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="notebook_runner.py")
    subparsers = parser.add_subparsers(dest="subcomando", required=True)

    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--manifest", required=True)
    grupo_modo = run_parser.add_mutually_exclusive_group()
    grupo_modo.add_argument("--dry-run", action="store_true")
    grupo_modo.add_argument("--execute", action="store_true")

    return parser


def main(argv: list) -> int:
    parser = _construir_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        # argparse ya imprimió el motivo por stderr y pide salir con 2
        # (uso inválido) -- se normaliza acá por si alguna vez cambia su
        # convención interna.
        codigo = exc.code
        return codigo if isinstance(codigo, int) else 2

    if args.subcomando != "run":
        print(f"Subcomando desconocido: {args.subcomando!r}", file=sys.stderr)
        return 2

    modo = "execute" if args.execute else "dry_run"

    try:
        repo_root = _repo_root()
    except Exception as exc:  # noqa: BLE001 - error de entorno/git, exit de uso
        print(f"No se pudo resolver la raíz del repositorio: {exc!r}", file=sys.stderr)
        return 2

    manifest_path = Path(args.manifest)
    manifest_path_abs = manifest_path if manifest_path.is_absolute() else (repo_root / manifest_path)
    if not manifest_path_abs.exists():
        print(f"No existe el manifest: {manifest_path_abs}", file=sys.stderr)
        return 2

    control_path = _control_path_para_manifest(manifest_path_abs, repo_root)
    try:
        control_data = _leer_control_data(control_path)
    except dsguard_core.ControlJsonError as exc:
        print(f"control.json inválido en {control_path}: {exc}", file=sys.stderr)
        return 2

    resultado = leadrun_notebooks.ejecutar_manifest(manifest_path_abs, repo_root, control_data, modo)
    _imprimir_resultado(resultado)

    return 0 if resultado["ok"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

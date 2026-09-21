"""CLI de reporting gobernado: `python -m tools.reporting <subcomando> ...`
(v0.6 Change 1, `20260918-reporting-governance`, spec R18).

Subcomandos (solo `render` escribe, y solo `report.html`; el resto es solo lectura):
    check-inputs       aislamiento de inputs de un flujo (`check_flow_inputs`)
    check-destination  destino de un reporte (`evaluate_destination`)
    validate           puerta completa sobre un directorio de reporte persistido
                       (`validation.validate_report_dir`; v0.6 Change 3)
    render             renderiza `report.html` (derivado, fuera del manifest) de un
                       directorio ya validado; `--check` compara sin escribir
                       (v0.6 Change 4)

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

`render` no usa `publish`: rehúsa (exit 1, nada escrito) si `validate_report_dir` da algún FAIL,
un `--style` inválido (`REPORT-STYLE-INVALID`) o una lectura/render fallidos
(`REPORT-RENDER-FAILED`). Sin bundle de plotly.js emite WARN `REPORT-RENDER-PLOTLY-UNAVAILABLE`
(exit 0) y el HTML degrada cada figura a un aviso con su tabla de respaldo.

Límite inherente de `render --check`: compara contra un render fresco hecho con el bundle
disponible AHORA (el de `chart.plotly_js_file` del proyecto o el paquete `plotly` instalado).
Si `publish` recibió un `plotly_bundle=` explícito, o cambió el entorno (plotly instalado o
desinstalado, otro bundle), `--check` puede informar "difiere" aunque el reporte no haya
cambiado. Los mensajes de error no incluyen rutas absolutas (`_sanear`).
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import re
import sys
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parents[1]
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from dsguard import core as dsguard_core  # noqa: E402

from . import core as reporting_core  # noqa: E402
from . import evidence  # noqa: E402
from . import governance  # noqa: E402
from . import plotly_backend  # noqa: E402
from . import render_html  # noqa: E402
from . import style as reporting_style  # noqa: E402
from . import validation  # noqa: E402

_checks = governance.checks

REPORT_HTML_FILENAME = "report.html"
CODE_RENDER = "REPORT-RENDER"
CODE_RENDER_CHECK = "REPORT-RENDER-CHECK"
CODE_RENDER_FAILED = "REPORT-RENDER-FAILED"
CODE_RENDER_PLOTLY_UNAVAILABLE = "REPORT-RENDER-PLOTLY-UNAVAILABLE"
CODE_STYLE_INVALID = "REPORT-STYLE-INVALID"


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

    ayuda_render = (
        "Renderiza `report.html` (autocontenido, determinista) desde un directorio de reporte "
        "persistido y validado (0 FAIL). Escribe SOLO report.html, de forma atómica. "
        "Con --check no escribe: compara el report.html existente con un render fresco."
    )
    p_render = subparsers.add_parser("render", help=ayuda_render, description=ayuda_render)
    p_render.add_argument("--dir", required=True, dest="report_dir")
    p_render.add_argument(
        "--style", default=None, dest="style_path",
        help="Ruta (dentro del repo) a un JSON de estilo; default: .harmessi/report-style.json o el estilo por defecto.",
    )
    p_render.add_argument(
        "--include-sensitive", action="store_true", dest="include_sensitive",
        help="Incluye tablas/figuras sensibles en el HTML (por defecto se omiten con un placeholder).",
    )
    p_render.add_argument(
        "--check", action="store_true", dest="check",
        help=(
            "No escribe: exit 1 si report.html falta o difiere de un render fresco hecho con el "
            "bundle de plotly.js disponible AHORA (si publish usó otro bundle o cambió el entorno, "
            "puede dar 'difiere')."
        ),
    )
    _agregar_comunes(p_render)
    p_render.set_defaults(func=cmd_render)

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


def _cargar_style(repo_root: Path, ruta):
    """`Style` del render: `--style RUTA` vía `style.load_style_file` (ruta dentro del repo,
    `read_allowed` antes de leer) o `load_style(repo_root)`. `StyleError` ante cualquier
    problema. Una ruta absoluta DENTRO del repo se relativiza; fuera del repo se pasa tal
    cual y `load_style_file` la rechaza."""
    if ruta is None:
        return reporting_style.load_style(repo_root)
    candidata = Path(ruta)
    if candidata.is_absolute():
        try:
            candidata = candidata.resolve().relative_to(repo_root)
        except (ValueError, OSError):
            pass
    # `--style` explícito: un archivo inexistente es error (no cae al default).
    return reporting_style.load_style_file(repo_root, candidata, missing_ok=False)


_RUTA_ABSOLUTA = re.compile(r"""[A-Za-z]:[\\/][^\s'"]*|(?<![\w.])/[^\s'"]+""")


def _sanear(texto, *rutas) -> str:
    """Quita rutas absolutas de un mensaje (las rutas dadas y cualquier ruta estilo
    Windows/POSIX) para no filtrar el filesystem local en la salida."""
    limpio = str(texto)
    for ruta in rutas:
        for variante in {str(ruta), Path(ruta).as_posix()}:
            if variante:
                limpio = limpio.replace(variante, "<ruta>")
    return _RUTA_ABSOLUTA.sub("<ruta>", limpio)


def _fallo_render(mensaje: str, detalle=None):
    return _checks.CheckResult(
        status=_checks.STATUS_FAIL, code=CODE_RENDER_FAILED, message=mensaje, detail=detalle,
        subject=REPORT_HTML_FILENAME,
    )


def cmd_render(args: argparse.Namespace) -> int:
    repo_root, error = _resolver_repo_root(args)
    if error is not None:
        print(error, file=sys.stderr)
        return 3
    # 1. Puerta de validación: con algún FAIL se rehúsa (nada se escribe).
    resultados = list(validation.validate_report_dir(repo_root, args.report_dir))
    if _checks.exit_code(resultados) != 0:
        return _emitir(resultados, args.como_json)
    crudo = Path(args.report_dir)
    out_dir = (crudo if crudo.is_absolute() else repo_root / crudo).resolve()
    # 2. Carga verificada (una sola lectura de cada archivo) y estilo.
    try:
        files, manifest = evidence.read_report_dir(out_dir, repo_root=repo_root)
        reporte = evidence.report_from_bytes(files, manifest)
    except evidence.EvidenceError as exc:
        detalle = f"{type(exc).__name__}: {_sanear(exc, out_dir, repo_root)}"
        return _emitir(resultados + [_fallo_render("no se pudo cargar el reporte verificado", detalle)], args.como_json)
    try:
        estilo = _cargar_style(repo_root, args.style_path)
    except reporting_style.StyleError as exc:
        resultados.append(_checks.CheckResult(
            status=_checks.STATUS_FAIL, code=CODE_STYLE_INVALID,
            message=_sanear(exc, repo_root) or "estilo inválido",
        ))
        return _emitir(resultados, args.como_json)
    # 3. Bundle de plotly.js: sin bundle se degrada de forma visible (nunca silencioso).
    motivos: list = []
    bundle = plotly_backend.find_plotly_bundle(estilo, repo_root, motivos)
    if bundle is None:
        resultados.append(_checks.CheckResult(
            status=_checks.STATUS_WARN, code=CODE_RENDER_PLOTLY_UNAVAILABLE,
            message="bundle de plotly.js no disponible: las figuras se reemplazan por un aviso y su tabla de respaldo",
            detail="; ".join(motivos) if motivos else None,
        ))
    # 4. Render puro y determinista.
    try:
        html_fresco = render_html.render_report_html(
            reporte, manifest, estilo, plotly_bundle=bundle, include_sensitive=args.include_sensitive
        )
    except Exception as exc:  # noqa: BLE001 -- el render no debería lanzar; si lo hace, se rehúsa
        return _emitir(resultados + [_fallo_render("el render falló", type(exc).__name__)], args.como_json)
    destino = out_dir / REPORT_HTML_FILENAME
    fresco_bytes = html_fresco.encode("utf-8")
    # 5a. --check: compara sin escribir.
    if args.check:
        actual = None
        if destino.is_file():
            permitido, _motivo = evidence.read_allowed(repo_root, destino)
            if permitido:
                try:
                    actual = destino.read_bytes()
                except OSError:
                    actual = None
        if actual is None:
            resultados.append(_checks.CheckResult(
                status=_checks.STATUS_FAIL, code=CODE_RENDER_CHECK, subject=REPORT_HTML_FILENAME,
                message="report.html falta o no se pudo leer",
            ))
        elif actual != fresco_bytes:
            resultados.append(_checks.CheckResult(
                status=_checks.STATUS_FAIL, code=CODE_RENDER_CHECK, subject=REPORT_HTML_FILENAME,
                message="report.html difiere de un render fresco del reporte validado",
            ))
        else:
            resultados.append(_checks.CheckResult(
                status=_checks.STATUS_PASS, code=CODE_RENDER_CHECK, subject=REPORT_HTML_FILENAME,
                message="report.html coincide con un render fresco",
            ))
        return _emitir(resultados, args.como_json)
    # 5b. Escritura atómica de SOLO report.html.
    try:
        dsguard_core.escribir_texto_atomico(destino, html_fresco)
    except OSError as exc:
        return _emitir(resultados + [_fallo_render("no se pudo escribir report.html", type(exc).__name__)], args.como_json)
    resultados.append(_checks.CheckResult(
        status=_checks.STATUS_PASS, code=CODE_RENDER, subject=REPORT_HTML_FILENAME,
        message=f"report.html escrito ({len(fresco_bytes)} bytes)",
    ))
    return _emitir(resultados, args.como_json)


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

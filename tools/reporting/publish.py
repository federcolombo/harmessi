"""Publicación del reporte completo (v0.6 Change 4, R17/R18): `publish`.

Única puerta de escritura del reporte: encadena governance -> validación ->
manifest -> reevaluación de destino (TOCTOU) -> escritura (manifest último) ->
relectura verificada -> render desde el Report verificado EN MEMORIA ->
escritura atómica de `report.html`. Ante un FAIL en cualquier paso no se escribe
nada más y `PublishResult.written` refleja lo escrito de verdad.

Lecciones de C1-C3: un `[]` de governance NO es OK (se exigen
`governance.REQUIRED_DESTINATION_CODES`); la `scientific_policy` se lee UNA vez;
toda lectura pasa por `evidence` con acceso evaluado; los mensajes no llevan
rutas locales. `report.html` es un artefacto DERIVADO: NO entra al manifest.

Solo stdlib + `reporting.*` + `dsguard.*`. Sin pandas, sin red; el paquete
`plotly` no se importa aquí (lo intenta, perezoso, `plotly_backend`).
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

_TOOLS_DIR = Path(__file__).resolve().parents[1]
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from dsguard import checks  # noqa: E402
from dsguard import core as dsguard_core  # noqa: E402
from dsguard import scientific_validity  # noqa: E402

from . import core as reporting_core  # noqa: E402
from . import evidence  # noqa: E402
from . import governance  # noqa: E402
from . import plotly_backend  # noqa: E402
from . import render_html  # noqa: E402
from . import style as style_mod  # noqa: E402
from . import validation  # noqa: E402

CODE_NO_SCIENTIFIC_POLICY = "REPORT-PUBLISH-NO-SCIENTIFIC-POLICY"
CODE_PLOTLY_UNAVAILABLE = "REPORT-RENDER-PLOTLY-UNAVAILABLE"
CODE_STYLE_INVALID = "REPORT-STYLE-INVALID"
CODE_PUBLISH_GOVERNANCE = "REPORT-PUBLISH-GOVERNANCE"
CODE_PUBLISH_DEST = "REPORT-PUBLISH-DEST"
CODE_PUBLISH_MANIFEST = "REPORT-PUBLISH-MANIFEST"
CODE_PUBLISH_WRITE = "REPORT-PUBLISH-WRITE"
CODE_PUBLISH_READBACK = "REPORT-PUBLISH-READBACK"
CODE_PUBLISH_RENDER = "REPORT-PUBLISH-RENDER"
CODE_PUBLISH_EXCEPCION = "REPORT-PUBLISH-EXCEPCION"
CODE_INCLUDE_SENSITIVE = "REPORT-PUBLISH-INCLUDE-SENSITIVE"

CODES = (
    CODE_INCLUDE_SENSITIVE,
    CODE_NO_SCIENTIFIC_POLICY,
    CODE_PLOTLY_UNAVAILABLE,
    CODE_STYLE_INVALID,
    CODE_PUBLISH_GOVERNANCE,
    CODE_PUBLISH_DEST,
    CODE_PUBLISH_MANIFEST,
    CODE_PUBLISH_WRITE,
    CODE_PUBLISH_READBACK,
    CODE_PUBLISH_RENDER,
    CODE_PUBLISH_EXCEPCION,
)

_SCOPES_FLUJO_MODELO = ("model_valid", "operational")
_AUTO = object()  # centinela: buscar el bundle de plotly.js automáticamente


@dataclass(frozen=True)
class PublishResult:
    """`results`: CheckResult acumulados de todos los pasos ejecutados. `out_dir`:
    destino usado (relativo al repo si así se pasó o resolvió; `None` si no se llegó
    a resolver). `written`: se empezó a escribir el directorio del reporte (incluye
    escrituras parciales). `html_written`: `report.html` quedó escrito.
    `plotly_bundle_used`: había bundle de plotly.js y el reporte tiene figuras."""

    results: list
    out_dir: Optional[str]
    written: bool
    html_written: bool
    plotly_bundle_used: bool


class _Estado:
    def __init__(self) -> None:
        self.results: list = []
        self.out_dir: Optional[str] = None
        self.written = False
        self.html_written = False
        self.bundle_used = False
        self.paso = "inicio"


def _res(status: str, code: str, message: str, *, subject: Optional[str] = None,
         detail: Optional[str] = None, tecnico: bool = False) -> checks.CheckResult:
    return checks.CheckResult(
        status=status, code=code, message=message, detail=detail, subject=subject,
        kind=checks.KIND_TECHNICAL_ERROR if tecnico else checks.KIND_CHECK,
    )


def _fail(code: str, message: str, *, subject: Optional[str] = None, tecnico: bool = False) -> checks.CheckResult:
    return _res(checks.STATUS_FAIL, code, message, subject=subject, tecnico=tecnico)


def _hay_fail(lista: Any) -> bool:
    return any(getattr(r, "status", None) == checks.STATUS_FAIL for r in lista)


def _sin_duplicados(resultados: list) -> list:
    """Deduplica preservando el orden por `(status, code, subject, message)`: `validate_report`
    y `validate_manifest` se repiten dentro de `validate_report_dir` (paso 6)."""
    vistos: set = set()
    unicos: list = []
    for r in resultados:
        clave = (getattr(r, "status", None), getattr(r, "code", None),
                 getattr(r, "subject", None), getattr(r, "message", None))
        if clave in vistos:
            continue
        vistos.add(clave)
        unicos.append(r)
    return unicos


def _sin_rutas(texto: Any, repo: Path) -> str:
    """Quita del texto las formas absolutas del repo (mensajes sin rutas locales)."""
    salida = str(texto)
    formas = {str(repo)}
    try:
        resuelto = repo.resolve()
        formas |= {str(resuelto), resuelto.as_posix()}
    except (OSError, RuntimeError):
        pass
    formas |= {f.replace("\\", "/") for f in list(formas)}
    for forma in sorted(formas, key=len, reverse=True):
        if forma:
            salida = salida.replace(forma, "<repo>")
    return salida


def _temporal_declarada(politica: Any) -> bool:
    temporal = politica.get("temporal") if isinstance(politica, dict) else None
    return isinstance(temporal, dict) and temporal.get("declared") is True


def _destino_fisico(repo: Path, out_dir: str) -> Path:
    ruta = Path(out_dir)
    return ruta if ruta.is_absolute() else repo / ruta


def _gobernanza_ok(resultados: Any) -> bool:
    return governance.output_allowed(resultados, require_codes=governance.REQUIRED_DESTINATION_CODES)


def _flujo(
    est: _Estado,
    report: Any,
    repo_root: Any,
    *,
    run_id: Any,
    sources: Any,
    holdout_access: Any,
    data_cutoff: Any,
    exclusions: Any,
    source_notebook: Any,
    style: Any,
    out_dir: Any,
    agent_type: Any,
    clock: Optional[Callable[[], Any]],
    plotly_bundle: Any,
    include_sensitive: bool,
) -> None:
    res = est.results
    if isinstance(sources, (list, tuple)):
        sources = list(sources)
    if isinstance(exclusions, (list, tuple)):
        exclusions = list(exclusions)

    # (0) Estilo y policy científica: se resuelven ANTES de escribir cualquier archivo.
    est.paso = "estilo"
    if style is None:
        try:
            estilo = style_mod.load_style(repo_root)
        except style_mod.StyleError as exc:
            res.append(_fail(CODE_STYLE_INVALID, f"Estilo inválido (no se escribió nada): {exc}", tecnico=True))
            return
    elif isinstance(style, style_mod.Style):
        estilo = style
    else:
        res.append(_fail(CODE_STYLE_INVALID, "style debe ser un Style (o None para el del proyecto).", tecnico=True))
        return
    res.extend(style_mod.check_style(estilo))

    est.paso = "policy científica"
    repo = Path(repo_root)
    try:
        politica = scientific_validity.leer_policy(repo)  # UNA sola lectura
    except scientific_validity.ScientificPolicyError:
        res.append(
            _fail(
                validation.CODE_SCI_POLICY,
                "Policy científica inválida (fail-closed): corregir .harmessi/scientific-policy.json; "
                "no se escribió nada.",
                tecnico=True,
            )
        )
        return
    scope = getattr(report, "decision_scope", None)
    if scope in _SCOPES_FLUJO_MODELO and not _temporal_declarada(politica):
        res.append(
            _res(
                checks.STATUS_WARN,
                CODE_NO_SCIENTIFIC_POLICY,
                f"El scope {scope!r} no tiene política científica temporal declarada "
                f"(.harmessi/scientific-policy.json): el corte temporal no se puede verificar.",
            )
        )

    # (1) Governance completa; un `[]` no es OK.
    est.paso = "governance"
    if out_dir is None:
        try:
            politica_reporting = governance.load_policy(repo_root)
            out_dir_str = governance.resolve_output_dir(politica_reporting, report.decision_scope, report.report_id)
        except governance.ReportingPolicyError:
            res.append(
                _fail(
                    governance.CODE_POLICY,
                    "No se pudo resolver el destino por defecto (policy de reporting, scope o report_id inválidos).",
                    tecnico=True,
                )
            )
            return
    else:
        if isinstance(out_dir, os.PathLike):
            out_dir = os.fspath(out_dir)
        if not isinstance(out_dir, str) or not out_dir.strip():
            res.append(_fail(governance.CODE_DEST_SAFE, "out_dir debe ser un string no vacío."))
            return
        out_dir_str = out_dir
    est.out_dir = out_dir_str

    # governance recibe RUTAS str: solo las fuentes `file` aportan su `path` (igual que
    # `validation._paso_gobernanza`); las `generated` no son rutas. Una fuente `file` mal
    # formada no se pasa a governance: la rechaza validate_manifest (esquema).
    fuentes_file = [s for s in sources if isinstance(s, dict) and s.get("kind") == "file"] if isinstance(sources, list) else []
    rutas_fuentes = tuple(s["path"] for s in fuentes_file if isinstance(s.get("path"), str))
    ctx = governance.context_from_report(
        repo_root, report, out_dir_str,
        sources=rutas_fuentes, holdout_access=holdout_access, data_cutoff=data_cutoff, agent_type=agent_type,
    )
    resultados_gov = governance.evaluate_governance(ctx)
    res.extend(resultados_gov)
    if _hay_fail(resultados_gov):
        return
    if not _gobernanza_ok(resultados_gov):
        res.append(
            _fail(
                CODE_PUBLISH_GOVERNANCE,
                f"governance no evaluó los checks requeridos {list(governance.REQUIRED_DESTINATION_CODES)}: "
                f"no se publica (un resultado vacío no es OK).",
                tecnico=True,
            )
        )
        return

    # (2) Validación del reporte (con la policy científica ya leída).
    est.paso = "validación del reporte"
    resultados_rep = validation.validate_report(report, scientific_policy=politica)
    res.extend(resultados_rep)
    if _hay_fail(resultados_rep):
        return

    # (3) Artefactos + manifest + validación del manifest.
    est.paso = "manifest"
    artefactos = evidence.prepare_artifacts(report)
    try:
        manifest = evidence.build_manifest(
            report,
            repo_root=repo_root,
            run_id=run_id,
            artifact_bytes=artefactos,
            sources=sources,
            exclusions=exclusions,
            holdout_access=holdout_access,
            data_cutoff=data_cutoff,
            source_notebook=source_notebook,
            clock=clock,
        )
    except evidence.EvidenceError as exc:
        res.append(_fail(CODE_PUBLISH_MANIFEST, f"No se pudo armar el manifest: {_sin_rutas(exc, repo)}", tecnico=True))
        return
    resultados_man = validation.validate_manifest(manifest, report)
    res.extend(resultados_man)
    if _hay_fail(resultados_man):
        return

    # (4) TOCTOU: reevaluar el destino justo antes de escribir.
    est.paso = "reevaluación del destino"
    recheck = governance.evaluate_destination(ctx)
    if _hay_fail(recheck) or not _gobernanza_ok(recheck):
        res.extend(r for r in recheck if getattr(r, "status", None) != checks.STATUS_PASS)
        res.append(
            _fail(
                CODE_PUBLISH_DEST,
                "El destino no superó la reevaluación previa a la escritura; no se escribió nada.",
                subject=out_dir_str,
                tecnico=not _hay_fail(recheck),
            )
        )
        return

    # (5) Escritura (manifest último). Todos los chequeos previos pasaron: el `report.html`
    # de una corrida anterior es un derivado que quedaría desincronizado con el manifest
    # nuevo, así que se elimina ANTES de escribir (si no se puede, no se escribe nada).
    est.paso = "escritura"
    destino = _destino_fisico(repo, out_dir_str)
    previo = destino / reporting_core.REPORT_FILENAME
    try:
        if previo.exists() or previo.is_symlink():
            previo.unlink()
    except OSError as exc:
        res.append(
            _fail(
                CODE_PUBLISH_WRITE,
                f"No se pudo eliminar el {reporting_core.REPORT_FILENAME} previo ({type(exc).__name__}); "
                f"no se escribió nada.",
                subject=out_dir_str,
                tecnico=True,
            )
        )
        return
    est.written = True  # desde aquí puede haber escrituras parciales
    try:
        evidence.write_report_dir(destino, artefactos, manifest)
    except Exception as exc:  # noqa: BLE001 -- se informa como FAIL, sin rutas
        res.append(
            _fail(CODE_PUBLISH_WRITE, f"Falló la escritura del reporte ({type(exc).__name__}).",
                  subject=out_dir_str, tecnico=True)
        )
        return

    # (6) Relectura verificada.
    est.paso = "relectura verificada"
    try:
        files, manifest_leido = evidence.read_report_dir(destino, repo_root=repo)
    except evidence.EvidenceError as exc:
        res.append(_fail(CODE_PUBLISH_READBACK, f"Relectura fallida: {_sin_rutas(exc, repo)}", tecnico=True))
        return
    resultados_dir = validation.validate_report_dir(repo_root, out_dir_str)
    res.extend(resultados_dir)
    if _hay_fail(resultados_dir):
        return

    # (7) Render desde el Report verificado en memoria + escritura atómica.
    est.paso = "render"
    try:
        verificado = evidence.report_from_bytes(files, manifest_leido)
    except evidence.EvidenceError as exc:
        res.append(_fail(CODE_PUBLISH_READBACK, f"Reconstrucción verificada fallida: {_sin_rutas(exc, repo)}", tecnico=True))
        return
    motivos: list = []
    bundle = plotly_backend.find_plotly_bundle(estilo, repo_root, motivos) if plotly_bundle is _AUTO else plotly_bundle
    bundle = bundle if isinstance(bundle, str) and bundle.strip() else None
    tiene_figuras = any(True for _ in verificado.iter_figures())
    if bundle is None and tiene_figuras:
        res.append(
            _res(
                checks.STATUS_WARN,
                CODE_PLOTLY_UNAVAILABLE,
                "Bundle de plotly.js no disponible: las figuras se muestran como aviso con su tabla de respaldo.",
                detail="; ".join(str(m) for m in motivos) or None,
            )
        )
    if include_sensitive:
        res.append(
            _res(
                checks.STATUS_WARN,
                CODE_INCLUDE_SENSITIVE,
                "report.html se renderiza CON celdas sensibles (include_sensitive=True): no compartir fuera "
                "del destino sensible. Un `render --check` posterior sin el flag dará 'difiere'.",
            )
        )
    try:
        html = render_html.render_report_html(
            verificado, manifest_leido, estilo, plotly_bundle=bundle, include_sensitive=include_sensitive
        )
    except Exception as exc:  # noqa: BLE001
        res.append(_fail(CODE_PUBLISH_RENDER, f"Falló el render HTML ({type(exc).__name__}).", tecnico=True))
        return
    try:
        dsguard_core.escribir_texto_atomico(destino / reporting_core.REPORT_FILENAME, html)
    except Exception as exc:  # noqa: BLE001
        res.append(_fail(CODE_PUBLISH_WRITE, f"Falló la escritura de report.html ({type(exc).__name__}).", tecnico=True))
        return
    est.html_written = True
    est.bundle_used = bundle is not None and tiene_figuras


def publish(
    report: Any,
    repo_root: Any,
    *,
    run_id: Any,
    sources: Any,
    holdout_access: Any,
    data_cutoff: Any = None,
    exclusions: Any = (),
    source_notebook: Any = None,
    style: Any = None,
    out_dir: Any = None,
    agent_type: Optional[str] = None,
    clock: Optional[Callable[[], Any]] = None,
    plotly_bundle: Any = _AUTO,
    include_sensitive: bool = False,
) -> PublishResult:
    """Publica `report` en `out_dir` (por defecto `resolve_output_dir`). Nunca lanza:
    una excepción interna se informa como FAIL `REPORT-PUBLISH-EXCEPCION` (sin rutas).

    `plotly_bundle`: por defecto se busca con `plotly_backend.find_plotly_bundle`;
    un `str` fuerza ese bundle y `None` fuerza "sin bundle" (aviso + WARN)."""
    est = _Estado()
    try:
        _flujo(
            est, report, repo_root,
            run_id=run_id, sources=sources, holdout_access=holdout_access, data_cutoff=data_cutoff,
            exclusions=exclusions, source_notebook=source_notebook, style=style, out_dir=out_dir,
            agent_type=agent_type, clock=clock, plotly_bundle=plotly_bundle,
            include_sensitive=bool(include_sensitive),
        )
    except Exception as exc:  # noqa: BLE001 -- contrato: nunca lanza
        est.results.append(
            _fail(
                CODE_PUBLISH_EXCEPCION,
                f"Excepción inesperada ({type(exc).__name__}) en el paso '{est.paso}'; no se publicó nada más.",
                tecnico=True,
            )
        )
    return PublishResult(
        results=_sin_duplicados(est.results),
        out_dir=est.out_dir,
        written=est.written,
        html_written=est.html_written,
        plotly_bundle_used=est.bundle_used,
    )

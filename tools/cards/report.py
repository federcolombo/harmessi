"""Adaptador Card -> `reporting.core.Report` (Change `20261005-cards-governance-integration`,
R63-R72; contrato E).

- Único renderer: este módulo SOLO construye el `Report` y delega en
  `reporting.publish.publish`; no agrega HTML/CSS (R63).
- `report_kind="governance"`, `decision_scope="exploratory"` (R64). Sin
  `FigureArtifact`, sin `Insight`. Datos en `TableArtifact`, texto en `summary` /
  `method_note` (R64).
- Las tablas de evidencia llevan `evidence_id`, kind, `ref_id`, hash12 y estado;
  NUNCA el contenido de la evidencia (R70).
- Solo refleja estados ya derivados: sin interpretación, scores ni «aprobado» (R69).
- Todo reporte lleva `NOTA_COMPLETENESS` en `summary`, `conclusion` y en el
  `method_note` de cada capítulo (R68).
- Nunca escribe bajo `governance/`: el destino lo decide `reporting.governance` (R72).
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

try:  # import dual: paquete (`tools.cards`) o módulo suelto con `tools/cards` en sys.path
    from . import assess, core, discovery
except ImportError:  # pragma: no cover - ejecución sin paquete padre
    import assess  # type: ignore[no-redef]
    import core  # type: ignore[no-redef]
    import discovery  # type: ignore[no-redef]

REPORT_KIND = "governance"
DECISION_SCOPE = "exploratory"
CODE_REPORT_SOURCE = "CARDS-REPORT-SOURCE"

_TITULO_KIND = {
    discovery.KIND_DATA: "Data Card",
    discovery.KIND_MODEL: "Model Card",
    discovery.KIND_GOVERNANCE: "Governance assessment",
}


def _reporting() -> tuple:
    """`(core, evidence, publish)` de `reporting`, todos desde la misma raíz de import."""
    for base in ("tools.reporting", "reporting"):
        try:
            rcore = __import__(f"{base}.core", fromlist=["core"])
            revidence = __import__(f"{base}.evidence", fromlist=["evidence"])
            rpublish = __import__(f"{base}.publish", fromlist=["publish"])
            return rcore, revidence, rpublish
        except ImportError:
            continue
    raise ImportError("reporting no está disponible")


def nota_completeness() -> str:
    """`modelgov.NOTA_COMPLETENESS` (texto fijo); respaldo local si no se puede importar."""
    try:
        return discovery._importar("modelgov").NOTA_COMPLETENESS
    except Exception:  # noqa: BLE001
        return discovery.NOTA_COMPLETENESS_FALLBACK


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _t(valor: Any, repo_root: Any) -> str:
    return discovery.limpiar_texto("" if valor is None else valor, repo_root)


def _report_id(card_report: Any) -> str:
    base = f"gov-{card_report.kind}-{card_report.card_id or 'invalid'}".lower()
    base = re.sub(r"[^a-z0-9_-]", "-", base)[:64].rstrip("-_")
    return base or "gov-card"


def _leer_card(repo_root: Any, rel_path: str) -> Any:
    try:
        ruta = Path(repo_root).joinpath(*rel_path.split("/"))
        if discovery._es_enlace(ruta):
            return None
        return assess.read_card(ruta)
    except Exception:  # noqa: BLE001
        return None


def _tabla(rcore: Any, table_id: str, title: str, columns: tuple, rows: list, labels: Optional[dict] = None) -> Any:
    return rcore.TableArtifact.from_rows(
        table_id, title, columns, rows, column_labels=labels or {}, sensitive=False
    )


def _estados_evidencia(card_report: Any) -> dict:
    return {e["evidence_id"]: e for e in card_report.evidence}


def _filas_evidencia(card_report: Any) -> list:
    return [[e["evidence_id"], e["kind"], e["ref_id"], e["hash12"], e["state"]] for e in card_report.evidence]


def _tabla_evidencia(rcore: Any, prefijo: str, card_report: Any, filtro: Any = None) -> Optional[Any]:
    filas = [f for f in _filas_evidencia(card_report) if filtro is None or filtro(f)]
    if not filas:
        return None
    return _tabla(
        rcore, f"{prefijo}-evidencia", "Evidencia (sin contenido)",
        ("evidence_id", "kind", "ref_id", "hash12", "estado"), filas,
    )


def _tabla_requisitos(rcore: Any, prefijo: str, card_report: Any) -> Optional[Any]:
    if not card_report.requirements:
        return None
    con_dim = card_report.kind == discovery.KIND_GOVERNANCE
    if con_dim:
        cols = ("requirement_id", "severity", "dimension", "estado")
        filas = [[r["requirement_id"], r["severity"], r.get("dimension") or "", r["state"]] for r in card_report.requirements]
    else:
        cols = ("requirement_id", "severity", "estado")
        filas = [[r["requirement_id"], r["severity"], r["state"]] for r in card_report.requirements]
    return _tabla(rcore, f"{prefijo}-requisitos", "Requisitos", cols, filas)


def _tabla_anclas(rcore: Any, prefijo: str, card_report: Any) -> Optional[Any]:
    if not card_report.anchors:
        return None
    filas = [
        [a["attestation_id"], a["state"], a.get("change_id") or "", a.get("artefacto") or "", a.get("detail") or ""]
        for a in card_report.anchors
    ]
    return _tabla(
        rcore, f"{prefijo}-anclas", "Atestaciones anchored (resolución)",
        ("attestation_id", "estado", "change_id", "artefacto", "detalle"), filas,
    )


def nota_anchor() -> str:
    """`approvals.NOTA_ANCHOR` (aclaración sobre la resolución de anclas); vacío si no se importa."""
    try:
        return str(discovery._importar("approvals").NOTA_ANCHOR)
    except Exception:  # noqa: BLE001
        return ""


def _limitaciones_assessment(body: Any, repo_root: Any) -> list:
    """Textos de `limitations` de las dimensiones (dict o lista de dimensiones)."""
    dims = body.get("dimensions") if isinstance(body, dict) else None
    items = list(dims.items()) if isinstance(dims, dict) else [(d.get("dimension", ""), d) for d in dims or [] if isinstance(d, dict)]
    filas = []
    for nombre, dim in items:
        lim = dim.get("limitations") if isinstance(dim, dict) else None
        textos = [lim] if isinstance(lim, str) else [t for t in (lim or []) if isinstance(t, str)] if isinstance(lim, (list, tuple)) else []
        for t in textos:
            filas.append([_t(nombre, repo_root), _t(t, repo_root)])
    return filas


def _tabla_hallazgos(rcore: Any, prefijo: str, card_report: Any) -> Optional[Any]:
    if not card_report.findings:
        return None
    filas = [[h["code"], h["path"], h["detail"]] for h in card_report.findings]
    return _tabla(rcore, f"{prefijo}-hallazgos", "Hallazgos", ("code", "path", "detail"), filas)


def _tabla_textos(rcore: Any, table_id: str, title: str, items: Any, repo_root: Any) -> Optional[Any]:
    if not isinstance(items, (list, tuple)) or not items:
        return None
    return _tabla(rcore, table_id, title, ("texto",), [[_t(i, repo_root)] for i in items if isinstance(i, str)] or [[""]])


def _capitulo(rcore: Any, chapter_id: str, title: str, summary: str, tablas: list, nota: str) -> Any:
    return rcore.Chapter(
        chapter_id=chapter_id,
        title=title,
        summary=summary,
        tables=tuple(t for t in tablas if t is not None),
        method_note=nota,
    )


# ---------------------------------------------------------------------------
# construir_report
# ---------------------------------------------------------------------------


def construir_report(card_report: Any, *, repo_root: Any) -> Any:
    """`CardReport` -> `reporting.core.Report` (`governance`/`exploratory`)."""
    rcore, _evidence, _publish = _reporting()
    nota = nota_completeness()
    kind = card_report.kind
    tipo = _TITULO_KIND.get(kind, "Card")
    card = _leer_card(repo_root, card_report.rel_path) if card_report.status != assess.CARD_INVALID else None
    body = card.body if card is not None else {}
    capitulos: list = []

    # Capítulo 1: identidad y estado derivado (todos los kinds).
    filas_id = [
        ["tipo", tipo],
        ["card_id", card_report.card_id],
        ["revision_id", card_report.revision_id],
        ["estado_derivado", card_report.status],
        ["archivo", card_report.rel_path],
    ]
    if card is not None:
        filas_id.append(["titulo", _t(card.title, repo_root)])
    if kind == discovery.KIND_DATA and isinstance(body, dict):
        filas_id.append(["descripcion", _t(body.get("description"), repo_root)])
    if kind == discovery.KIND_MODEL and isinstance(body, dict):
        filas_id.extend(
            [
                ["model_id", _t(body.get("model_id"), repo_root)],
                ["model_version", _t(body.get("model_version"), repo_root)],
                ["proposito_contexto", _t(body.get("description"), repo_root)],
            ]
        )
    stew = body.get("stewardship") if isinstance(body, dict) else None
    if isinstance(stew, dict):
        for clave in ("owner", "steward"):
            if stew.get(clave):
                filas_id.append([f"stewardship_{clave}", _t(stew.get(clave), repo_root)])
    t_id = _tabla(rcore, "identidad", "Identidad y estado derivado", ("campo", "valor"), filas_id)
    capitulos.append(
        _capitulo(
            rcore, "identidad", "Identidad y estado",
            f"Estado derivado de {tipo} {card_report.card_id}: {card_report.status}.", [t_id], nota,
        )
    )

    # Capítulo 2: contenido específico por kind.
    if kind == discovery.KIND_DATA:
        capitulos.append(_capitulo_data(rcore, card_report, body, repo_root, nota))
    elif kind == discovery.KIND_MODEL:
        capitulos.append(_capitulo_model(rcore, card_report, body, repo_root, nota))
    elif kind == discovery.KIND_GOVERNANCE:
        capitulos.append(_capitulo_assessment(rcore, card_report, body, repo_root, nota))

    # Capítulo 3: requisitos, evidencia, anclas y hallazgos (estados derivados).
    tablas_estado = [
        _tabla_requisitos(rcore, "estado", card_report),
        _tabla_evidencia(rcore, "estado", card_report),
        _tabla_anclas(rcore, "estado", card_report),
        _tabla_hallazgos(rcore, "estado", card_report),
    ]
    capitulos.append(
        _capitulo(
            rcore, "estado-derivado", "Requisitos, evidencia y hallazgos",
            "Estados ya derivados por la evaluación; sin interpretación adicional.", tablas_estado, nota,
        )
    )

    return rcore.Report(
        report_id=_report_id(card_report),
        title=f"{tipo}: {card_report.card_id or 'inválida'}",
        report_kind=REPORT_KIND,
        decision_scope=DECISION_SCOPE,
        chapters=tuple(capitulos),
        summary=f"Reporte estructurado de governance sobre {tipo} {card_report.card_id} (estado derivado: {card_report.status}). {nota}",
        conclusion=f"Este reporte refleja estados derivados ya calculados y no agrega conclusiones. {nota}",
        metadata={
            "card_kind": kind,
            "card_id": card_report.card_id,
            "revision_id": card_report.revision_id,
            "archivo": card_report.rel_path,
            "estado_derivado": card_report.status,
        },
    )


def _capitulo_data(rcore: Any, cr: Any, body: Any, repo_root: Any, nota: str) -> Any:
    tablas: list = []
    if isinstance(body, dict):
        evs = _estados_evidencia(cr)
        filas = []
        for ref in body.get("source_refs", []) or []:
            if not isinstance(ref, dict):
                continue
            eid = ref.get("observation_evidence_id")
            ev = evs.get(eid, {})
            filas.append(
                [_t(ref.get("source_ref_id"), repo_root), _t(ref.get("source_id"), repo_root),
                 _t(eid, repo_root), ev.get("hash12", ""), ev.get("state", "unverifiable")]
            )
        if filas:
            tablas.append(
                _tabla(rcore, "fuentes", "Fuentes (source_refs)",
                       ("source_ref_id", "source_id", "evidence_id", "hash12", "estado"), filas)
            )
        for clave, tid, titulo in (
            ("intended_uses", "usos-previstos", "Usos previstos"),
            ("out_of_scope_uses", "usos-fuera-de-alcance", "Usos fuera de alcance"),
            ("known_limitations", "limitaciones-conocidas", "Limitaciones conocidas"),
        ):
            tablas.append(_tabla_textos(rcore, tid, titulo, body.get(clave), repo_root))
    return _capitulo(rcore, "data-card", "Data Card", "Fuentes, usos y limitaciones declarados.", tablas, nota)


def _capitulo_model(rcore: Any, cr: Any, body: Any, repo_root: Any, nota: str) -> Any:
    tablas: list = []
    if isinstance(body, dict):
        evs = _estados_evidencia(cr)
        filas = []
        for ref in body.get("data_card_refs", []) or []:
            if not isinstance(ref, dict):
                continue
            eid = ref.get("evidence_id")
            ev = evs.get(eid, {})
            filas.append(
                [_t(ref.get("data_card_ref_id"), repo_root), _t(ref.get("role"), repo_root),
                 _t(eid, repo_root), ev.get("state", "unverifiable")]
            )
        if filas:
            tablas.append(
                _tabla(rcore, "data-cards-vinculadas", "Data Cards vinculadas",
                       ("data_card_ref_id", "role", "evidence_id", "estado"), filas)
            )
        tablas.append(
            _tabla_evidencia(rcore, "calidad", cr, filtro=lambda f: f[1].startswith("model_quality"))
        )
        tablas.append(_tabla_textos(rcore, "limitaciones-conocidas", "Limitaciones conocidas", body.get("known_limitations"), repo_root))
    return _capitulo(rcore, "model-card", "Model Card", "Data Cards vinculadas, evidencia de calidad y limitaciones.", tablas, nota)


def _capitulo_assessment(rcore: Any, cr: Any, body: Any, repo_root: Any, nota: str) -> Any:
    pol = cr.policy or {}
    filas = [
        ["risk_level_declarado", _t(pol.get("declared_level"), repo_root)],
        ["risk_level_efectivo", _t(pol.get("effective_level"), repo_root)],
        ["risk_floor", _t(pol.get("risk_floor"), repo_root)],
        ["governance_completeness", cr.status],
        ["estado_configuracion", _t(pol.get("config_state"), repo_root)],
    ]
    politica = pol.get("policy") if isinstance(pol.get("policy"), dict) else {}
    for lado in sorted(politica):
        valor = politica[lado]
        if isinstance(valor, dict):
            for clave in sorted(valor):
                filas.append([f"policy_{lado}_{clave}", _t(valor[clave], repo_root)])
    tablas = [_tabla(rcore, "riesgo-y-policy", "Riesgo y policy", ("campo", "valor"), filas)]
    dims = pol.get("dimensiones") or []
    if dims:
        tablas.append(
            _tabla(rcore, "dimensiones", "Dimensiones", ("dimension", "estado", "requisitos"),
                   [[d["dimension"], d["estado"], ",".join(d["requisitos"])] for d in dims])
        )
    tablas.append(_tabla_anclas(rcore, "assessment", cr))
    lim = _limitaciones_assessment(body, repo_root)
    if lim:
        tablas.append(_tabla(rcore, "assessment-limitaciones", "Limitaciones declaradas", ("dimension", "texto"), lim))
    cfg = pol.get("config_findings") or []
    if cfg:
        tablas.append(
            _tabla(rcore, "assessment-configuracion", "Estado de configuración (hallazgos)",
                   ("code", "path", "detail"), [[h["code"], h["path"], h["detail"]] for h in cfg])
        )
    na = nota_anchor()
    nota_cap = f"{nota} {na}".strip()
    return _capitulo(
        rcore, "assessment", "Governance assessment",
        ("Nivel de riesgo, policy, dimensiones, anclas y configuración. " + na).strip(), tablas, nota_cap,
    )


# ---------------------------------------------------------------------------
# publicar_card
# ---------------------------------------------------------------------------


def _falla_source(publish_mod: Any, mensaje: str) -> Any:
    res = publish_mod.checks.CheckResult("FAIL", CODE_REPORT_SOURCE, mensaje)
    return publish_mod.PublishResult(results=[res], out_dir=None, written=False, html_written=False, plotly_bundle_used=False)


def publicar_card(repo_root: Any, rel_path: str, *, out_dir: Any = None, clock: Any = None) -> tuple:
    """Valida la Card de `rel_path` y la publica con `reporting.publish.publish`.
    Devuelve `(PublishResult, ProjectValidation)`. Nunca lanza."""
    pv = discovery.validar_proyecto(repo_root, paths=[rel_path])
    try:
        rcore, revidence, rpublish = _reporting()
    except ImportError:
        raise
    if not pv.reports:
        return _falla_source(rpublish, "no se obtuvo ninguna Card para el path indicado"), pv
    card_report = pv.reports[0]
    try:
        fuente = revidence.describe_source(repo_root, rel_path, role="input")
    except Exception as exc:  # noqa: BLE001 - EvidenceError u otro
        return _falla_source(rpublish, f"no se pudo describir la Card como fuente: {discovery.limpiar_texto(exc, repo_root, 120)}"), pv
    try:
        report = construir_report(card_report, repo_root=repo_root)
    except Exception as exc:  # noqa: BLE001
        return _falla_source(rpublish, f"no se pudo construir el reporte ({type(exc).__name__})"), pv
    ahora = None
    if clock is not None:
        try:
            ahora = clock()
        except Exception:  # noqa: BLE001
            ahora = None
    run_id = revidence.new_run_id(ahora if isinstance(ahora, datetime) else None)
    try:
        resultado = rpublish.publish(
            report, repo_root,
            run_id=run_id, sources=[fuente], holdout_access="none",
            out_dir=out_dir, clock=clock,
        )
    except Exception as exc:  # noqa: BLE001 - M-8: nunca traceback
        return _falla_source(rpublish, f"la publicación falló ({type(exc).__name__})"), pv
    return resultado, pv

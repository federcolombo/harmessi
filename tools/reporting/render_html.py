"""Renderer HTML del reporting (v0.6 Change 4, `20260918-reporting-design-system-and-html-renderer`).

`render_report_html(report, manifest, style, *, plotly_bundle=None, include_sensitive=False) -> str`
produce un `report.html` AUTOCONTENIDO y DETERMINISTA a partir de un `Report` ya verificado,
el manifest (dict, forma del Change 3) y un `Style`.

Reglas:
- solo stdlib + `reporting.*`; sin red, sin pandas, sin importar `plotly` (el navegador
  necesita `plotly.js`; se embebe si el llamador pasa el texto del bundle);
- offline: cero `<link>`, `<script src>`, `@import`, `url(http...)` ni imagenes remotas; solo
  CSS/JS inline. El JSON de figuras va en `<script type="application/json">` con `<`, `>` y
  `&` escapados como `\\uXXXX` (imposible cerrar el script ni abrir `<!--`);
- todo texto de usuario pasa por `html.escape`; los textos de interfaz salen de
  `style.editorial.label(...)`; los tokens visuales salen del `Style` (sin colores literales);
- sin timestamps propios (solo `generated_at` del manifest): mismo input => mismos bytes;
- pantalla OSCURA por defecto; `@media print` redefine las variables CSS (tema claro) y un
  loader JS inline intercambia el payload `print` de cada figura en `beforeprint`. Sin JS, la
  impresion muestra la variante `screen` de las figuras (limite documentado);
- ninguna funcion muta `Report`, artefactos ni `Style`; ninguna lanza por contenido del reporte
  (una figura que no se puede construir se degrada a aviso visible).
"""
from __future__ import annotations

import html
import json
import re
from collections.abc import Mapping
from decimal import Decimal
from typing import Any, Optional

from .plotly_backend import build_figure
from .style import Style, default_style, format_date, format_number, format_percent

__all__ = [
    "render_report_html",
    "render_css",
    "render_header",
    "render_intro",
    "render_tech_sheet",
    "render_scope_banner",
    "render_chapter",
    "render_figure",
    "render_table",
    "render_method_details",
    "render_insight",
    "render_tabs",
    "render_conclusion",
    "render_glossary",
    "render_footer",
]

_REVIEW_TYPES = ("causal", "recommendation")
_CAMPOS_MAPA = ("path", "name", "id", "kind")

# Loader JS minimo (sin datos de usuario): grafica `screen` al cargar y cambia a `print`.
_LOADER_JS = (
    "(function(){var P=window.Plotly;if(!P){return;}"
    "function els(){return document.querySelectorAll('.plot[data-figure]');}"
    "function get(id,v){var s=document.getElementById('fig-'+id+'-'+v);"
    "if(!s){return null;}try{return JSON.parse(s.textContent);}catch(e){return null;}}"
    "function draw(v,fn){var l=els();for(var i=0;i<l.length;i++){var el=l[i];"
    "var f=get(el.getAttribute('data-figure'),v);if(!f||!P[fn]){continue;}"
    "if(fn==='react'){if(el.getAttribute('data-drawn')!=='1'){continue;}"
    "try{P.react(el,f.data,f.layout,{responsive:true,displaylogo:false});}catch(e){}continue;}"
    "var prev=el.innerHTML;"
    "try{el.innerHTML='';P[fn](el,f.data,f.layout,{responsive:true,displaylogo:false});"
    "el.setAttribute('data-drawn','1');}catch(e){el.innerHTML=prev;}}}"
    "function resize(){if(!P.Plots||!P.Plots.resize){return;}var l=els();"
    "for(var i=0;i<l.length;i++){try{P.Plots.resize(l[i]);}catch(e){}}}"
    "draw('screen','newPlot');"
    "window.addEventListener('beforeprint',function(){draw('print','react');});"
    "window.addEventListener('afterprint',function(){draw('screen','react');});"
    "if(window.matchMedia){var m=window.matchMedia('print');"
    "var h=function(e){draw(e.matches?'print':'screen','react');};"
    "if(m.addEventListener){m.addEventListener('change',h);}"
    "else if(m.addListener){m.addListener(h);}}"
    "document.addEventListener('change',function(e){var t=e.target;"
    "if(t&&t.classList&&t.classList.contains('tab-input')){setTimeout(resize,0);}});"
    "})();"
)

# --- Utilidades ------------------------------------------------------------------


def _e(valor: Any) -> str:
    """`html.escape` (comillas incluidas) de cualquier valor; `None` => ''."""
    return html.escape("" if valor is None else str(valor), quote=True)


def _t(style: Style, clave: str) -> str:
    """Texto de interfaz (escapado) desde `style.editorial.label`."""
    return _e(style.editorial.label(clave))


def _fill(texto: str, **valores: Any) -> str:
    """Reemplazo seguro de `{clave}` (los labels pueden llevar otras llaves)."""
    for k, v in valores.items():
        texto = texto.replace("{" + k + "}", str(v))
    return texto


def _slug(valor: Any) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "-", str(valor))


def _es_num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _json_script(script_id: str, obj: Any) -> str:
    """`<script type="application/json">` con el JSON escapado (`<`, `>`, `&` como \\uXXXX)."""
    try:
        crudo = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    except (TypeError, ValueError, RecursionError):
        crudo = "null"
    crudo = crudo.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return f'<script type="application/json" id="{_e(script_id)}">{crudo}</script>'


def _js_seguro(texto: str) -> str:
    """El bundle va inline: se neutraliza lo que cerraria el `<script>` o abriria `<!--`."""
    texto = re.sub(r"</(script)", r"<\\/\1", texto, flags=re.IGNORECASE)
    # `<!--` solo es peligroso si abre el estado "script data escaped" (seguido de `<script`).
    return re.sub(r"<!--(?=\s*<script)", r"<\\!--", texto, flags=re.IGNORECASE)


def _decimales(v: float) -> int:
    """Decimales necesarios para mostrar `v` con hasta 10 cifras significativas, sin ceros
    finales y sin perder valores pequenos (1e-7 => 7; 0.1+0.2 => 1). Tope 12."""
    try:
        exp = Decimal(format(v, ".10g")).as_tuple().exponent
    except (ArithmeticError, ValueError):
        return 6
    return min(max(0, -exp), 12) if isinstance(exp, int) else 0


def _fmt_celda(v: Any, style: Style) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "✓" if v else "✗"  # simbolos neutros (sin idioma)
    if isinstance(v, int):
        return format_number(v, 0, locale=style)
    if isinstance(v, float):
        return format_number(v, _decimales(v), locale=style)
    return str(v)


def _valores_columna(tabla: Any, columna: Optional[str]) -> list:
    if tabla is None or columna is None or columna not in tabla.columns:
        return []
    i = tabla.columns.index(columna)
    return [fila[i] for fila in tabla.rows]


class _Ctx:
    """Estado de UN render (no se comparte entre llamadas)."""

    def __init__(self, report: Any, style: Style, include_sensitive: bool, has_bundle: bool) -> None:
        self.report = report
        self.style = style
        self.include_sensitive = include_sensitive
        self.has_bundle = has_bundle
        self.tab_groups: list = []
        self.figures_drawn = 0
        self.omitidos = 0  # contador para ids opacos de placeholders sensibles


def _es_sensible_fig(fig: Any, tabla: Any) -> bool:
    return bool(fig.sensitive) or bool(tabla is not None and tabla.sensitive)


# --- Tablas ------------------------------------------------------------------------


def _tabla_html(tabla: Any, style: Style) -> str:
    """Tabla COMPLETA: numeros a la derecha (tabular-nums por CSS), unidades en el encabezado."""
    numericas = []
    for i, _col in enumerate(tabla.columns):
        vals = [fila[i] for fila in tabla.rows if fila[i] is not None]
        numericas.append(bool(vals) and all(_es_num(v) for v in vals))
    cab = []
    for col, num in zip(tabla.columns, numericas):
        etiqueta = tabla.column_labels.get(col, col)
        unidad = tabla.units.get(col, "")
        u = f' <span class="unit">({_e(unidad)})</span>' if unidad else ""
        clase = ' class="num"' if num else ""
        cab.append(f'<th scope="col"{clase}>{_e(etiqueta)}{u}</th>')
    filas = []
    for fila in tabla.rows:
        celdas = []
        for v, num in zip(fila, numericas):
            clase = ' class="num"' if num else ""
            celdas.append(f"<td{clase}>{_e(_fmt_celda(v, style))}</td>")
        filas.append("<tr>" + "".join(celdas) + "</tr>")
    return (
        '<div class="table-wrap"><table class="data"><thead><tr>' + "".join(cab)
        + "</tr></thead><tbody>" + "".join(filas) + "</tbody></table></div>"
    )


def render_table(tabla: Any, ctx: "_Ctx") -> str:
    """Tabla standalone (con titulo). Sensible => placeholder salvo `include_sensitive`."""
    style = ctx.style
    if tabla.sensitive and not ctx.include_sensitive:
        return f'<div class="notice notice-sensitive" role="note">{_t(style, "sensitive_omitted")}</div>'
    desc = f'<p class="table-desc">{_e(tabla.description)}</p>' if tabla.description else ""
    return (
        f'<div class="table-block" id="tbl-{_slug(tabla.table_id)}"><h3>{_e(tabla.title)}</h3>{desc}'
        + _tabla_html(tabla, style) + "</div>"
    )


def _tabla_respaldo(tabla: Any, ctx: "_Ctx", abierta: bool) -> str:
    style = ctx.style
    if tabla.sensitive and not ctx.include_sensitive:
        return f'<div class="notice notice-sensitive" role="note">{_t(style, "sensitive_omitted")}</div>'
    desc = f'<p class="table-desc">{_e(tabla.description)}</p>' if tabla.description else ""
    filas = f'<p class="table-note">{_t(style, "rows")}: {_e(format_number(len(tabla.rows), 0, locale=style))}</p>'
    return (
        f'<details class="backing"{" open" if abierta else ""}><summary>{_t(style, "backup_table")}: '
        f"{_e(tabla.title)}</summary>{desc}" + _tabla_html(tabla, style) + filas + "</details>"
    )


# --- Figuras -----------------------------------------------------------------------


def _leyenda_figura(fig: Any, tabla: Any, meta: Any, ctx: "_Ctx") -> str:
    style, spec = ctx.style, fig.spec
    partes = []
    if spec.top_n is not None and isinstance(meta, Mapping):
        total, mostradas = meta.get("categories_total"), meta.get("categories_shown")
        if all(isinstance(x, int) and not isinstance(x, bool) for x in (total, mostradas)):
            partes.append(_e(_fill(style.editorial.label("showing_n_of_m"),
                                   n=format_number(mostradas, 0, locale=style),
                                   m=format_number(total, 0, locale=style))))
    if spec.denominator and tabla is not None and spec.denominator in tabla.columns:
        dens = [d for d in _valores_columna(tabla, spec.denominator) if _es_num(d)]
        if dens:
            partes.append(_e(_fill(style.editorial.label("sample_size"),
                                   n=format_number(sum(dens), 0, locale=style))))
        if style.editorial.comparative_context and spec.y:
            ys = _valores_columna(tabla, spec.y[0])
            pares = [(y, d) for y, d in zip(ys, _valores_columna(tabla, spec.denominator))
                     if _es_num(y) and _es_num(d) and d > 0]
            peso = sum(d for _y, d in pares)
            if pares and peso > 0:
                ref = sum(y * d for y, d in pares) / peso
                en_unidad = all(0 <= y <= 1 for y, _d in pares)
                texto = format_percent(ref, locale=style) if en_unidad else format_number(ref, 2, locale=style)
                partes.append(f'{_t(style, "reference_global")}: {_e(texto)}')
    return " &middot; ".join(partes)


def render_figure(fig: Any, ctx: "_Ctx") -> str:
    """Figura + caption + tabla de respaldo. Sin bundle => aviso visible + tabla abierta.
    Sensible => placeholder (sin titulo, sin celdas, sin JSON)."""
    style = ctx.style
    fid = _slug(fig.figure_id)
    tabla = ctx.report.get_table(fig.backing_table_id) if fig.backing_table_id else None
    if not ctx.include_sensitive and _es_sensible_fig(fig, tabla):
        ctx.omitidos += 1  # id opaco: el id real de un artefacto sensible no se expone
        return (f'<figure class="figure figure-omitted" id="fig-omitted-{ctx.omitidos}">'
                f'<div class="notice notice-sensitive" role="note">{_t(style, "sensitive_omitted")}</div></figure>')
    screen = prn = None
    if ctx.has_bundle:
        try:
            screen = build_figure(fig, tabla, style, "screen")
            prn = build_figure(fig, tabla, style, "print")
        except Exception:  # noqa: BLE001 -- el render nunca lanza por contenido: se degrada
            screen = prn = None
    partes = [f'<figure class="figure" id="fig-{fid}">', f'<h3 class="figure-title">{_e(fig.title)}</h3>']
    if fig.description:
        partes.append(f'<p class="fig-desc">{_e(fig.description)}</p>')
    meta = None
    if screen is not None and prn is not None:
        meta = screen.get("layout", {}).get("meta") if isinstance(screen.get("layout"), Mapping) else None
        # Aviso por defecto DENTRO del contenedor: el loader lo reemplaza solo si grafica con
        # exito; sin JS o sin `window.Plotly` queda visible (nunca fallo silencioso).
        aviso = f'<div class="notice notice-figure plot-pending" role="status">{_t(style, "figure_not_rendered")}</div>'
        partes.append(f'<div class="plot" id="plot-{fid}" data-figure="{fid}" role="img" '
                      f'aria-label="{_e(fig.alt_text or fig.title)}">{aviso}</div>'
                      f'<noscript>{aviso}</noscript>')
        partes.append(_json_script(f"fig-{fid}-screen", screen))
        partes.append(_json_script(f"fig-{fid}-print", prn))
        ctx.figures_drawn += 1
    else:
        partes.append(f'<div class="notice notice-figure" role="status">{_t(style, "figure_not_rendered")}</div>')
    leyenda = _leyenda_figura(fig, tabla, meta, ctx)
    if leyenda:
        partes.append(f'<figcaption class="fig-caption">{leyenda}</figcaption>')
    if tabla is not None:
        # Siempre abierta: no hay garantia de que el grafico se dibuje (JS, bundle, navegador).
        partes.append(_tabla_respaldo(tabla, ctx, abierta=True))
    partes.append("</figure>")
    return "".join(partes)


# --- Insights ----------------------------------------------------------------------


def _evidencia_valida(ins: Any, report: Any) -> bool:
    refs = tuple(ins.evidence_refs)
    return bool(refs) and all(report.get_artifact(r) is not None for r in refs)


def _muestra_incertidumbre(ins: Any, style: Style) -> bool:
    if not ins.uncertainty.strip():
        return False
    modo = style.editorial.uncertainty_display
    if modo == "never":
        return False
    if modo == "non_descriptive":
        return ins.claim_type != "descriptive"
    return True


def render_insight(ins: Any, ctx: "_Ctx") -> str:
    """Callout (o item de lista) de un insight, aplicando audiencia, incertidumbre y la
    politica de recomendaciones. Devuelve '' si la politica la oculta."""
    style = ctx.style
    ed = style.editorial
    tag = "li" if ed.insight_style == "list" else "aside"
    iid = _e(ins.insight_id)
    if ins.claim_type == "recommendation":
        if ed.recommendations_policy == "hide":
            return ""
        if ed.recommendations_policy == "evidence_only" and not (
            _evidencia_valida(ins, ctx.report) and ins.uncertainty.strip()
        ):
            return (f'<{tag} class="callout callout-withheld" role="note" data-insight="{iid}">'
                    f'{_t(style, "recommendation_withheld")}</{tag}>')
    clase = "insight" if tag == "li" else "callout"
    partes = [f'<{tag} class="{clase} {clase}-{_slug(ins.claim_type)}" data-insight="{iid}">']
    if ins.claim_type in _REVIEW_TYPES:
        partes.append(f'<span class="badge badge-review">{_t(style, "requires_review")}</span>')
    if ins.title:
        partes.append(f'<h4 class="insight-title">{_e(ins.title)}</h4>')
    partes.append(f'<p class="claim-business">{_e(ins.business_claim)}</p>')
    if ed.audience in ("technical", "mixed"):
        if ins.technical_claim:
            partes.append(f'<p class="claim-technical">{_e(ins.technical_claim)}</p>')
        meta = []
        if ins.population:
            meta.append(f'<dt>{_t(style, "population")}</dt><dd>{_e(ins.population)}</dd>')
        if ins.time_scope:
            meta.append(f'<dt>{_t(style, "temporal_scope")}</dt><dd>{_e(ins.time_scope)}</dd>')
        if _muestra_incertidumbre(ins, style):
            meta.append(f'<dt>{_t(style, "uncertainty")}</dt><dd>{_e(ins.uncertainty)}</dd>')
        if meta:
            partes.append('<dl class="insight-meta">' + "".join(meta) + "</dl>")
    partes.append(f"</{tag}>")
    return "".join(partes)


# --- Tabs, capitulo -----------------------------------------------------------------


def render_tabs(group_id: str, panels: list) -> str:
    """Tabs CSS-only (radios). `panels`: lista de `(etiqueta_html_ya_escapada, panel_html)`."""
    gid = _slug(group_id)
    entradas, etiquetas, cuerpos = [], [], []
    for i, (etiqueta, cuerpo) in enumerate(panels, 1):
        tid = f"tab-{gid}-{i}"
        entradas.append(f'<input class="tab-input" type="radio" name="tabs-{gid}" id="{tid}"'
                        f'{" checked" if i == 1 else ""}>')
        etiquetas.append(f'<label for="{tid}">{etiqueta}</label>')
        cuerpos.append(f'<div class="tab-panel" id="panel-{gid}-{i}">{cuerpo}</div>')
    return (f'<div class="tabs" id="tabs-{gid}">' + "".join(entradas)
            + '<div class="tab-labels">' + "".join(etiquetas) + "</div>" + "".join(cuerpos) + "</div>")


def _tabs_css(group_id: str, n: int) -> str:
    gid, reglas = _slug(group_id), []
    for i in range(1, n + 1):
        sel = f"#tab-{gid}-{i}"
        lab = f'label[for="tab-{gid}-{i}"]'
        reglas.append(f"{sel}:checked ~ #panel-{gid}-{i}{{display:block}}")
        reglas.append(f"{sel}:checked ~ .tab-labels {lab}{{background:var(--accent);"
                      f"color:var(--surface);border-color:var(--accent)}}")
        reglas.append(f"{sel}:focus-visible ~ .tab-labels {lab}{{outline:2px solid var(--accent);outline-offset:2px}}")
    return "".join(reglas)


def render_method_details(chapter: Any, style: Style) -> str:
    if not chapter.method_note:
        return ""
    return (f'<details class="method"><summary>{_t(style, "method_details")}</summary>'
            f"<p>{_e(chapter.method_note)}</p></details>")


def _usa_tabs(chapter: Any) -> bool:
    return len(chapter.figures) >= 2 and chapter.metadata.get("layout") != "stack"


def render_chapter(chapter: Any, ctx: "_Ctx") -> str:
    style = ctx.style
    cid = _slug(chapter.chapter_id)
    partes = [f'<section class="chapter panel" id="ch-{cid}"><h2>{_e(chapter.title)}</h2>']
    if chapter.summary:
        partes.append(f'<p class="chapter-summary">{_e(chapter.summary)}</p>')
    if chapter.figures:
        bloques = [render_figure(f, ctx) for f in chapter.figures]
        if _usa_tabs(chapter):
            paneles = []
            for f, b in zip(chapter.figures, bloques):
                tabla = ctx.report.get_table(f.backing_table_id) if f.backing_table_id else None
                omitida = not ctx.include_sensitive and _es_sensible_fig(f, tabla)
                paneles.append((_t(style, "sensitive_omitted") if omitida else _e(f.title), b))
            ctx.tab_groups.append((f"ch-{cid}", len(paneles)))
            partes.append(render_tabs(f"ch-{cid}", paneles))
        else:
            partes.append('<div class="figures-stack">' + "".join(bloques) + "</div>")
    respaldo = {f.backing_table_id for f in chapter.figures if f.backing_table_id}
    for tabla in chapter.tables:
        if tabla.table_id not in respaldo:
            partes.append(render_table(tabla, ctx))
    bloques_ins = [b for b in (render_insight(i, ctx) for i in chapter.insights) if b]
    if bloques_ins:
        cuerpo = "".join(bloques_ins)
        if style.editorial.insight_style == "list":
            cuerpo = f'<ul class="insight-list">{cuerpo}</ul>'
        partes.append(f'<div class="insights"><h3>{_t(style, "insights")}</h3>{cuerpo}</div>')
    partes.append(render_method_details(chapter, style))
    partes.append("</section>")
    return "".join(partes)


# --- Bloques globales ----------------------------------------------------------------


def render_scope_banner(scope: Any, style: Style) -> str:
    if scope != "exploratory":
        return ""
    return f'<div class="banner banner-exploratory" role="note">{_t(style, "scope_exploratory")}</div>'


def render_header(report: Any, manifest: Mapping, style: Style) -> str:
    kind = manifest.get("report_kind") or report.report_kind
    scope = manifest.get("decision_scope") or report.decision_scope
    meta = [f'{_t(style, "kind")}: {_e(kind)}', f'{_t(style, "scope")}: {_e(scope)}']
    if manifest.get("data_cutoff"):
        meta.append(f'{_t(style, "data_cutoff")}: {_e(format_date(manifest["data_cutoff"], style))}')
    return (f'<header class="report-header"><h1>{_e(report.title)}</h1>'
            f'<p class="report-meta">{" &middot; ".join(meta)}</p></header>')


def render_intro(report: Any, style: Style) -> str:
    if not report.summary:
        return ""
    return f'<section class="intro"><p>{_e(report.summary)}</p></section>'


def _texto_simple(v: Any) -> str:
    if isinstance(v, str):
        return v
    try:
        return json.dumps(v, sort_keys=True, ensure_ascii=False, default=str)
    except (TypeError, ValueError, RecursionError):
        return str(v)


def render_tech_sheet(manifest: Mapping, style: Style) -> str:
    """Ficha tecnica colapsable con la informacion del manifest (hash corto)."""
    campos = []
    commit = manifest.get("git_commit")
    if commit:
        commit = str(commit)[:7]
        if manifest.get("git_dirty") is True:
            commit += f' ({style.editorial.label("dirty")})'
    cutoff = manifest.get("data_cutoff")
    for clave, valor in (
        ("report_id", manifest.get("report_id")), ("run_id", manifest.get("run_id")),
        ("kind", manifest.get("report_kind")), ("scope", manifest.get("decision_scope")),
        ("data_cutoff", format_date(cutoff, style) if cutoff else None),
        ("git_commit", commit), ("harmessi_version", manifest.get("harmessi_version")),
        ("generated_at", manifest.get("generated_at")),
        ("holdout_access", manifest.get("holdout_access")),
    ):
        if valor not in (None, ""):
            campos.append(f'<dt>{_t(style, clave)}</dt><dd>{_e(valor)}</dd>')
    sens = manifest.get("sensitivity")
    # Solo el booleano `contains_sensitive` y la CANTIDAD de artefactos sensibles: nunca ids
    # ni el resto del dict (podria exponer detalle sensible).
    flag = sens.get("contains_sensitive") if isinstance(sens, Mapping) else None
    ids = sens.get("sensitive_artifacts") if isinstance(sens, Mapping) else None
    if isinstance(flag, bool) or isinstance(ids, (list, tuple)):
        txt = "✓" if flag is True else ("✗" if flag is False else "")
        if isinstance(ids, (list, tuple)):
            txt = f"{txt} ({format_number(len(ids), 0, locale=style)})".strip()
    else:
        txt = style.editorial.label("none")
    campos.append(f'<dt>{_t(style, "sensitivity")}</dt><dd>{_e(txt)}</dd>')

    fuentes = manifest.get("sources")
    if isinstance(fuentes, (list, tuple)) and fuentes:
        filas = []
        for s in fuentes:
            if isinstance(s, Mapping):
                nombre = next((s[k] for k in _CAMPOS_MAPA if s.get(k)), "")
                h = str(s.get("sha256") or s.get("hash") or "")[:12]
                filas.append(
                    '<tr class="src">'
                    f"<td>{_e(nombre)}</td><td><code>{_e(h)}</code></td>"
                    f'<td class="num">{_e(_fmt_celda(s.get("rows"), style))}</td>'
                    f'<td>{_e(format_date(s.get("min_date"), style))}</td>'
                    f'<td>{_e(format_date(s.get("max_date"), style))}</td></tr>')
            else:
                filas.append(f'<tr class="src"><td>{_e(s)}</td><td></td><td></td><td></td><td></td></tr>')
        fuentes_html = (
            '<div class="table-wrap"><table class="data sources"><thead><tr class="src-head">'
            f'<th scope="col">{_t(style, "sources")}</th><th scope="col">{_t(style, "hash")}</th>'
            f'<th scope="col" class="num">{_t(style, "rows")}</th><th scope="col">{_t(style, "date_min")}</th>'
            f'<th scope="col">{_t(style, "date_max")}</th></tr></thead><tbody>'
            + "".join(filas) + "</tbody></table></div>")
    else:
        fuentes_html = f'<p><strong>{_t(style, "sources")}</strong>: {_t(style, "none")}</p>'

    excl = manifest.get("exclusions")
    if isinstance(excl, (list, tuple)) and excl:
        excl_html = "<ul>" + "".join(f"<li>{_e(_texto_simple(x))}</li>" for x in excl) + "</ul>"
    else:
        excl_html = f'<p>{_t(style, "none")}</p>'
    return (f'<details class="tech-sheet"><summary>{_t(style, "tech_sheet")}</summary>'
            f'<dl class="sheet-grid">{"".join(campos)}</dl>{fuentes_html}'
            f'<h4>{_t(style, "exclusions")}</h4>{excl_html}</details>')


def render_conclusion(report: Any, style: Style) -> str:
    if not report.conclusion:
        return ""
    return (f'<section class="conclusion panel"><h2>{_t(style, "conclusion")}</h2>'
            f"<p>{_e(report.conclusion)}</p></section>")


def _texto_reporte(report: Any, incluir_sensibles: bool) -> str:
    p = [report.title, report.summary, report.conclusion]
    for c in report.chapters:
        p += [c.title, c.summary, c.method_note]
        for t in c.tables:
            if incluir_sensibles or not t.sensitive:
                p += [t.title, t.description, *t.column_labels.values()]
        for f in c.figures:
            tabla_f = report.get_table(f.backing_table_id) if f.backing_table_id else None
            if incluir_sensibles or not _es_sensible_fig(f, tabla_f):
                p += [f.title, f.description]
        for i in c.insights:
            p += [i.title, i.technical_claim, i.business_claim, i.population, i.time_scope, i.uncertainty]
    return "\n".join(x for x in p if isinstance(x, str))


def render_glossary(report: Any, style: Style, include_sensitive: bool = False) -> str:
    """Solo terminos del glosario que aparecen en el texto del reporte, en orden estable."""
    ed = style.editorial
    if not ed.explain_terms or not ed.glossary:
        return ""
    texto = _texto_reporte(report, include_sensitive)
    usados = [t for t in ed.glossary
              if re.search(r"(?<!\w)" + re.escape(t) + r"(?!\w)", texto, flags=re.IGNORECASE)]
    if not usados:
        return ""
    usados.sort(key=lambda t: (t.casefold(), t))
    items = "".join(f"<dt>{_e(t)}</dt><dd>{_e(ed.glossary[t])}</dd>" for t in usados)
    return f'<section class="glossary panel"><h2>{_t(style, "glossary")}</h2><dl>{items}</dl></section>'


def render_footer(report: Any, manifest: Mapping, style: Style) -> str:
    hashes = manifest.get("hashes")
    h = hashes.get("report_content") if isinstance(hashes, Mapping) else None
    h = h or report.content_sha256()
    return (f'<footer class="report-footer"><span>{_t(style, "run_id")}: <code>{_e(manifest.get("run_id", ""))}</code></span> '
            f'<span>{_t(style, "content_hash")}: <code>{_e(h)}</code></span></footer>')


# --- CSS -------------------------------------------------------------------------------

_PALETA_VARS = (
    ("surface", "surface"), ("surface_alt", "surface-alt"), ("text", "text"), ("muted", "muted"),
    ("border", "border"), ("accent", "accent"), ("risk_low", "risk-low"), ("risk_medium", "risk-medium"),
    ("risk_high", "risk-high"), ("ok", "ok"), ("warn", "warn"), ("error", "error"), ("info", "info"),
)


def _vars_paleta(p: Any) -> str:
    v = "".join(f"--{css}:{getattr(p, attr)};" for attr, css in _PALETA_VARS)
    return v + "".join(f"--cat-{i}:{c};" for i, c in enumerate(p.categorical, 1))


_CSS_BASE = """
*{box-sizing:border-box}
body{margin:0;background:var(--surface);color:var(--text);font-family:@FONT_SANS@;font-size:@SIZE_BASE@px;line-height:@LH@}
.page{max-width:@W_NORMAL@px;margin:0 auto;padding:@XL@px @MD@px}
h1{font-size:@SIZE_H1@px;margin:0 0 @SM@px}
h2{font-size:@SIZE_H2@px;margin:0 0 @SM@px}
h3{font-size:@SIZE_H3@px;margin:@MD@px 0 @SM@px}
h4{margin:@SM@px 0 @XS@px}
code{font-family:@FONT_MONO@;font-size:@SIZE_SMALL@px}
.report-header{border-bottom:1px solid var(--border);padding-bottom:@MD@px;margin-bottom:@LG@px}
.report-meta,.table-note,.fig-caption,.table-desc,.fig-desc{color:var(--muted);font-size:@SIZE_SMALL@px}
.banner{padding:@SM@px @MD@px;border:1px solid var(--warn);border-radius:@R_MD@px;color:var(--warn);background:var(--surface-alt);font-weight:600;margin:@MD@px 0}
.panel,.tech-sheet{background:var(--surface-alt);border:@PANEL_BW@px solid var(--border);border-radius:@R_LG@px;padding:@PANEL_PAD@px;margin:@LG@px 0@PANEL_SHADOW@}
.sheet-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,260px),1fr));gap:@SM@px @MD@px;margin:@SM@px 0}
.sheet-grid dt{color:var(--muted);font-size:@SIZE_SMALL@px}
.sheet-grid dd{margin:0;overflow-wrap:anywhere}
.figures-stack{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,420px),1fr));gap:@MD@px}
.figure{margin:@MD@px 0;min-width:0}
.plot{width:100%;min-height:120px}
.notice{padding:@SM@px @MD@px;border:1px dashed var(--warn);border-radius:@R_MD@px;color:var(--warn);margin:@SM@px 0}
.table-wrap{overflow-x:auto;max-width:100%}
table.data{border-collapse:collapse;width:100%;font-size:@SIZE_SMALL@px}
table.data th,table.data td{padding:@CELL@px;border-bottom:1px solid var(--border);text-align:@TEXT_ALIGN@;vertical-align:top}
table.data th.num,table.data td.num{text-align:@NUM_ALIGN@@TABNUMS@}
table.data th .unit{color:var(--muted);font-weight:normal}
@ZEBRA@
details>summary{cursor:pointer;font-weight:600}
.callout,.insight{border-left:@CALLOUT_BW@px solid var(--accent);padding:@CALLOUT_PAD@px;background:var(--surface);border-radius:@R_SM@px;margin:@SM@px 0}
.callout-causal,.callout-recommendation,.callout-withheld{border-left-color:var(--warn)}
.insight-list{list-style:none;padding:0;margin:0}
.badge{display:inline-block;padding:0 @SM@px;border:1px solid var(--warn);border-radius:@R_SM@px;color:var(--warn);font-size:@SIZE_SMALL@px;margin-right:@SM@px}
.claim-technical,.insight-meta{color:var(--muted);font-size:@SIZE_SMALL@px}
.insight-meta{display:grid;grid-template-columns:max-content 1fr;gap:@XS@px @MD@px;margin:@XS@px 0 0}
.insight-meta dd{margin:0}
.tabs{margin:@MD@px 0}
.tab-input{position:absolute;opacity:0;pointer-events:none}
.tab-labels{display:flex;flex-wrap:wrap;gap:@SM@px;margin-bottom:@SM@px}
.tab-labels label{cursor:pointer;padding:@XS@px @MD@px;border:1px solid var(--border);border-radius:@R_MD@px;background:var(--surface)}
.tab-panel{display:none}
.report-footer{margin-top:@XL@px;padding-top:@MD@px;border-top:1px solid var(--border);color:var(--muted);font-size:@SIZE_SMALL@px;display:flex;flex-wrap:wrap;gap:@MD@px;overflow-wrap:anywhere}
@media (max-width:@BP_MD@px){.page{padding:@MD@px @SM@px}h1{font-size:@SIZE_H2@px}}
@media (max-width:@BP_SM@px){.sheet-grid,.insight-meta{grid-template-columns:1fr}}
@media (min-width:@BP_LG@px){.page{max-width:@W_WIDE@px}}
""".strip()

_CSS_PRINT = (
    ".tab-panel{display:block !important}.tab-labels,.tab-input{display:none !important}"
    ".plot,.figure,.callout,.insight{break-inside:avoid}"
    ".banner,.notice,.callout,.insight,.badge{-webkit-print-color-adjust:exact;print-color-adjust:exact}"
)


def render_css(style: Style, tab_groups: Optional[list] = None) -> str:
    """CSS inline: variables del tema `screen` en `:root` y del tema `print` en `@media print`."""
    v = style.visual
    ty, sp, ra, cw, tb, pn, co, rs = (v.typography, v.spacing, v.radii, v.content_widths,
                                      v.table, v.panel, v.callout, v.responsive)
    tokens = {
        "FONT_SANS": ty.font_sans, "FONT_MONO": ty.font_mono, "SIZE_BASE": ty.size_base,
        "SIZE_SMALL": ty.size_small, "SIZE_H1": ty.size_h1, "SIZE_H2": ty.size_h2,
        "SIZE_H3": ty.size_h3, "LH": ty.line_height, "XS": sp.xs, "SM": sp.sm, "MD": sp.md,
        "LG": sp.lg, "XL": sp.xl, "R_SM": ra.sm, "R_MD": ra.md, "R_LG": ra.lg,
        "W_NORMAL": cw.normal, "W_WIDE": cw.wide, "CELL": tb.cell_padding,
        "TEXT_ALIGN": tb.text_align, "NUM_ALIGN": tb.numbers_align,
        "TABNUMS": ";font-variant-numeric:tabular-nums" if tb.tabular_nums else "",
        "ZEBRA": "table.data tbody tr:nth-child(even){background:var(--surface)}" if tb.zebra else "",
        "PANEL_PAD": pn.padding, "PANEL_BW": pn.border_width,
        "PANEL_SHADOW": ";box-shadow:0 1px 3px var(--border)" if pn.shadow else "",
        "CALLOUT_PAD": co.padding, "CALLOUT_BW": co.border_width,
        "BP_SM": rs.breakpoint_sm, "BP_MD": rs.breakpoint_md, "BP_LG": rs.breakpoint_lg,
    }
    base = _CSS_BASE
    for k, val in tokens.items():
        base = base.replace(f"@{k}@", str(val))
    tabs = "".join(_tabs_css(g, n) for g, n in (tab_groups or []))
    return (f":root{{color-scheme:dark;{_vars_paleta(v.screen)}}}\n{base}\n{tabs}\n"
            f"@media print{{:root{{color-scheme:light;{_vars_paleta(v.print)}}}{_CSS_PRINT}}}")


# --- Punto de entrada ---------------------------------------------------------------------


def render_report_html(
    report: Any,
    manifest: Any,
    style: Any,
    *,
    plotly_bundle: Optional[str] = None,
    include_sensitive: bool = False,
) -> str:
    """HTML completo y autocontenido de `report`. Determinista: mismo input => mismos bytes.

    `manifest` es un dict (forma del Change 3; un valor ausente se omite, no lanza). Un
    `style` que no sea `Style` se reemplaza por `default_style()`. `plotly_bundle` es el
    TEXTO de plotly.js (se embebe una sola vez, solo si hay figuras graficadas); sin bundle
    cada figura se degrada a aviso visible + tabla de respaldo abierta."""
    if not isinstance(style, Style):
        style = default_style()
    manifest = manifest if isinstance(manifest, Mapping) else {}
    bundle = plotly_bundle if isinstance(plotly_bundle, str) and plotly_bundle.strip() else None
    ctx = _Ctx(report, style, bool(include_sensitive), bundle is not None)

    scope = manifest.get("decision_scope") or report.decision_scope
    cuerpo = [
        render_header(report, manifest, style),
        render_scope_banner(scope, style),
        render_intro(report, style),
        render_tech_sheet(manifest, style),
    ]
    cuerpo += [render_chapter(c, ctx) for c in report.chapters]
    cuerpo += [
        render_conclusion(report, style),
        render_glossary(report, style, ctx.include_sensitive),
        render_footer(report, manifest, style),
    ]
    scripts = ""
    if bundle is not None and ctx.figures_drawn:
        scripts = f"<script>{_js_seguro(bundle)}</script><script>{_LOADER_JS}</script>"
    return (
        f'<!DOCTYPE html>\n<html lang="{_e(style.editorial.locale)}"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{_e(report.title)}</title><style>{render_css(style, ctx.tab_groups)}</style>"
        # Sin JS el aviso pendiente del contenedor se oculta y queda el del <noscript>.
        + ("<noscript><style>.plot .plot-pending{display:none}</style></noscript>" if ctx.figures_drawn else "")
        + "</head>"
        f'<body><main class="page">{"".join(cuerpo)}</main>{scripts}</body></html>\n'
    )

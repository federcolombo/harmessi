"""Backend Plotly opcional del reporting (v0.6 Change 4, `20260918-reporting-design-system-and-html-renderer`).

Construye a mano, desde `FigureSpec` + tabla de respaldo, dos payloads JSON-puros
por figura (`screen` oscuro y `print` claro) con la forma `{"data": [...], "layout": {...}}`
que entiende `plotly.js`. NO importa el paquete `plotly` a nivel de modulo (ni lo
declara como dependencia): el unico import posible es perezoso y vive dentro de
`find_plotly_bundle`, protegido con `ImportError`.

Reglas: sin red, sin pandas, solo stdlib + `reporting.*`; nunca muta
`FigureArtifact`, `TableArtifact` ni `Style`; salida determinista (mismo input =>
mismo dict). Sin branding ni vocabulario de dominio. Los tokens (paleta, ChartTheme,
formato de locale) salen del `Style` real de `style.py`; los textos con valores usan
`style.format_number`. Un `style` que no sea `Style` se reemplaza por `default_style()`.
"""
from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Optional

from . import evidence
from .style import Style, default_style, format_number

VARIANTES = ("screen", "print")
UMBRAL_ETIQUETA_LARGA = 18  # caracteres: por encima, barras en horizontal
ALTO_BASE = 420
ALTO_MIN_HORIZONTAL = 320
ALTO_POR_CATEGORIA = 28
ALTO_MAX = 2400
LIMITE_TEXTO_BARRAS = 40  # sobre este numero de puntos no se rotula cada barra

_SEMANTICOS = {
    "risk": {"low": "risk_low", "medium": "risk_medium", "high": "risk_high"},
    "status": {"ok": "ok", "warn": "warn", "error": "error"},
}

_RE_EJE = re.compile(r"^[xy]axis\d*$")

# Vectores de recursos externos en un `backend_payload` (offline estricto).
_CLAVES_URL = frozenset({"source", "style", "url", "href", "topojsonurl", "src"})
_PREFIJOS_URL = ("http://", "https://", "//")
_TRAZAS_PROHIBIDAS = frozenset(
    {
        "scattergeo",
        "choropleth",
        "choroplethmap",
        "choroplethmapbox",
        "scattermapbox",
        "scattermap",
        "densitymapbox",
        "densitymap",
        "image",
    }
)


class BackendPayloadError(ValueError):
    """`backend_payload` rechazado por contener recursos externos (URLs, mapas,
    imágenes). El mensaje es genérico: no incluye URLs ni rutas."""


# --- Tokens del style ---------------------------------------------------------


def _tema(style: Any, variante: str) -> dict:
    """Tokens efectivos de la variante (`ThemePalette` + `ChartTheme` + `LocaleFormat`)."""
    if not isinstance(style, Style):
        style = default_style()
    paleta = getattr(style.visual, variante)
    chart = getattr(style.visual.chart, variante)
    formato = style.visual.locale_format
    return {
        "style": style,
        "paper": paleta.surface,
        "surface": paleta.surface_alt,
        "text": paleta.text,
        "muted": paleta.muted,
        "border": paleta.border,
        "accent": paleta.accent,
        "grid": chart.grid_color,
        "grid_w": chart.grid_width,
        "colorway": list(chart.colorway) or list(paleta.categorical),
        "risk_low": paleta.risk_low,
        "risk_medium": paleta.risk_medium,
        "risk_high": paleta.risk_high,
        "ok": paleta.ok,
        "warn": paleta.warn,
        "error": paleta.error,
        "fuente": chart.font_family,
        "tam": chart.font_size,
        "titulo_tam": chart.title_size,
        "linea": chart.line_width,
        "marcador": chart.marker_size,
        "leyenda": chart.legend_position,
        "dec": formato.decimal_sep,
        "mil": formato.thousands_sep,
        "no_disponible": style.editorial.label("not_available"),
        "tamano_muestra": style.editorial.label("sample_size"),
    }


def _texto_n(n_txt: str, tema: dict) -> str:
    """Rotulo de denominador (`sample_size` del style, placeholder `{n}`)."""
    return tema["tamano_muestra"].replace("{n}", n_txt)


def _es_num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and (not isinstance(v, float) or math.isfinite(v))


def _fmt(v: Any, tema: dict) -> str:
    """Numero con `style.format_number` (locale del style); enteros sin decimales,
    |v|<1 con 3 decimales y el resto con 2. No lanza ante None/no numerico."""
    if not _es_num(v):
        return format_number(v, locale=tema["style"])
    if isinstance(v, int) or float(v).is_integer():
        decimales = 0
    else:
        decimales = 3 if abs(v) < 1 else 2
    return format_number(v, decimales, locale=tema["style"])


def _separadores(tema: dict) -> str:
    dec = (tema["dec"] or ".")[:1]
    mil = tema["mil"][:1] if tema["mil"] else " "
    return dec + mil


# --- Sanitizado JSON-puro -----------------------------------------------------


def _sanear(valor: Any) -> Any:
    """Copia profunda JSON-pura (dict/list/str/int/float finito/bool/None)."""
    if valor is None or isinstance(valor, (bool, int, str)):
        return valor
    if isinstance(valor, float):
        return valor if math.isfinite(valor) else None
    if isinstance(valor, Mapping):
        return {str(k): _sanear(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [_sanear(v) for v in valor]
    return str(valor)


# --- Datos de la tabla --------------------------------------------------------


def _filas(tabla: Any) -> list:
    if tabla is None:
        return []
    cols = list(tabla.columns)
    return [dict(zip(cols, fila)) for fila in tabla.rows]


def _etiqueta(tabla: Any, col: Optional[str]) -> str:
    if col is None:
        return ""
    etiquetas = getattr(tabla, "column_labels", None) or {}
    return str(etiquetas.get(col, col))


def _unidad(tabla: Any, col: str) -> str:
    unidades = getattr(tabla, "units", None) or {}
    return str(unidades.get(col, "") or "")


def _titulo_eje(etiqueta: str, unidad: str) -> str:
    if unidad and unidad not in etiqueta:
        return f"{etiqueta} ({unidad})" if etiqueta else unidad
    return etiqueta


def _clave(valor: Any) -> str:
    return json.dumps(valor, sort_keys=True, default=str)


def _seleccionar(spec: Any, filas: list) -> tuple:
    """Aplica `sort` y `top_n` a lo GRAFICADO. Devuelve (filas, n_categorias_total, n_categorias_graficadas).

    Las categorias son los valores de `spec.x`; la tabla de respaldo no se toca."""
    if spec.chart_type == "histogram" and not spec.y:
        return list(filas), None, None
    orden: list = []
    suma: dict = {}
    for f in filas:
        k = _clave(f.get(spec.x))
        if k not in suma:
            suma[k] = None
            orden.append(k)
        if spec.y:
            v = f.get(spec.y[0])
            if _es_num(v):
                suma[k] = (suma[k] or 0) + v
    total = len(orden)
    if spec.sort and spec.y:
        con = [k for k in orden if suma[k] is not None]
        sin = [k for k in orden if suma[k] is None]
        con.sort(key=lambda k: suma[k], reverse=(spec.sort == "descending"))
        orden = con + sin
    if spec.top_n is not None:
        orden = orden[: spec.top_n]
    if not spec.sort and spec.top_n is None:
        return list(filas), total, total
    rango = {k: i for i, k in enumerate(orden)}
    kept = [f for f in filas if _clave(f.get(spec.x)) in rango]
    kept.sort(key=lambda f: rango[_clave(f.get(spec.x))])
    return kept, total, len(orden)


def _unicos(valores: list) -> list:
    vistos, salida = set(), []
    for v in valores:
        k = _clave(v)
        if k not in vistos:
            vistos.add(k)
            salida.append(v)
    return salida


def _color_semantico(rol: Optional[str], valor: Any, tema: dict) -> Optional[str]:
    if rol not in _SEMANTICOS or valor is None:
        return None
    token = _SEMANTICOS[rol].get(str(valor).strip().lower())
    return tema[token] if token else None


# --- Construccion desde el spec ----------------------------------------------


def _eje_base(tema: dict, titulo: str, grilla: bool = True) -> dict:
    return {
        "title": {"text": titulo, "font": {"color": tema["text"]}},
        "automargin": True,
        "showgrid": grilla,
        "gridcolor": tema["grid"],
        "gridwidth": tema["grid_w"],
        "zerolinecolor": tema["grid"],
        "linecolor": tema["border"],
        "tickfont": {"color": tema["text"]},
    }


def _leyenda(tema: dict, titulo: str) -> dict:
    leyenda = {
        "title": {"text": titulo, "font": {"color": tema["text"]}},
        "font": {"color": tema["text"]},
        "bgcolor": "rgba(0,0,0,0)",
    }
    if tema["leyenda"] == "bottom":
        leyenda.update({"orientation": "h", "yanchor": "top", "y": -0.25, "x": 0})
    elif tema["leyenda"] == "top":
        leyenda.update({"orientation": "h", "yanchor": "bottom", "y": 1.02, "x": 0})
    return leyenda


def _desde_spec(figure: Any, table: Any, tema: dict, variante: str) -> dict:
    spec = figure.spec
    filas_todas = _filas(table)
    filas, cats_total, cats_graf = _seleccionar(spec, filas_todas)
    tipo = spec.chart_type
    colorway = tema["colorway"]

    # Etiquetas y unidades.
    etiqueta_x = spec.x_label or _etiqueta(table, spec.x)
    unidad_x = _unidad(table, spec.x)
    y0 = spec.y[0] if spec.y else None
    etiqueta_y = spec.y_label or (_etiqueta(table, y0) if y0 else "")
    unidades_y = {u for u in (_unidad(table, c) for c in spec.y) if u}
    unidad_y = spec.unit or (next(iter(unidades_y)) if len(unidades_y) == 1 else "")
    titulo_x = _titulo_eje(etiqueta_x, unidad_x)
    titulo_y = _titulo_eje(etiqueta_y, unidad_y)
    if tipo == "histogram" and not spec.y:
        # Histograma de valores crudos: la unidad del spec describe la medida (eje x).
        titulo_x = _titulo_eje(etiqueta_x, spec.unit or unidad_x)
        titulo_y = spec.y_label

    # Categorias y orientacion.
    categorias = _unicos([f.get(spec.x) for f in filas])
    es_categorico = tipo in ("bar", "box") or (tipo == "histogram" and bool(spec.y))
    orientacion = spec.orientation
    if tipo in ("bar", "box") and orientacion == "v":
        if any(len(str(c)) > UMBRAL_ETIQUETA_LARGA for c in categorias):
            orientacion = "h"
    horizontal = orientacion == "h" and tipo in ("bar", "box")

    # Grupos por columna de color.
    if spec.color:
        def _nombre_grupo(f: dict) -> str:
            return tema["no_disponible"] if f.get(spec.color) is None else str(f.get(spec.color))

        nombres = _unicos([_nombre_grupo(f) for f in filas])
        grupos = [(n, [f for f in filas if _nombre_grupo(f) == n]) for n in nombres]
    else:
        grupos = [(None, filas)]

    # Series = grupos x columnas y (o solo grupos si no hay y).
    series = []
    columnas_y = list(spec.y) if spec.y else [None]
    for nombre_g, filas_g in grupos:
        for cy in columnas_y:
            if nombre_g is not None and cy is not None and len(columnas_y) > 1:
                nombre = f"{nombre_g} · {_etiqueta(table, cy)}"
            elif nombre_g is not None:
                nombre = nombre_g
            elif cy is not None:
                nombre = _etiqueta(table, cy) if len(columnas_y) > 1 else (etiqueta_y or _etiqueta(table, cy))
            else:
                nombre = etiqueta_x
            series.append((nombre, nombre_g, cy, filas_g))

    # Color por serie: semantico (por grupo) o paleta categorica.
    contador = 0
    colores_serie = []
    for nombre, nombre_g, cy, _ in series:
        color = _color_semantico(spec.semantic, nombre_g, tema) if nombre_g is not None else None
        if color is None:
            color = colorway[contador % len(colorway)]
            contador += 1
        colores_serie.append(color)

    trazas = []
    hay_puntos_semanticos = spec.semantic in _SEMANTICOS and spec.color is None and tipo == "bar" and len(series) == 1
    mostrar_texto = tipo == "bar" and len(categorias) * max(1, len(series)) <= LIMITE_TEXTO_BARRAS

    for (nombre, nombre_g, cy, filas_g), color in zip(series, colores_serie):
        xs = [f.get(spec.x) for f in filas_g]
        ys = [f.get(cy) for f in filas_g] if cy else []
        textos, hovers = [], []
        if cy:
            unidad_hover = spec.unit or _unidad(table, cy)
            for f in filas_g:
                v = f.get(cy)
                texto = _fmt(v, tema)
                x_txt = _fmt(f.get(spec.x), tema) if _es_num(f.get(spec.x)) else f.get(spec.x)
                hover = f"{x_txt}: {texto}"
                if unidad_hover:
                    hover += f" {unidad_hover}"
                if spec.denominator:
                    n_txt = _fmt(f.get(spec.denominator), tema)
                    rotulo_n = _texto_n(n_txt, tema)
                    texto = f"{texto} ({rotulo_n})"
                    hover += f" ({rotulo_n})"
                textos.append(texto)
                hovers.append(hover)

        if tipo == "bar" or (tipo == "histogram" and spec.y):
            traza: dict = {
                "type": "bar",
                "name": nombre,
                "orientation": "h" if horizontal else "v",
                "x": ys if horizontal else xs,
                "y": xs if horizontal else ys,
                "marker": {"color": color},
                "textposition": "auto",
                "cliponaxis": False,
                "hovertext": hovers,
                "hoverinfo": "text",
            }
            if mostrar_texto:
                traza["text"] = textos
            if hay_puntos_semanticos:
                puntos, extra = [], 0
                for c in xs:
                    sem = _color_semantico(spec.semantic, c, tema)
                    if sem is None:
                        sem = colorway[extra % len(colorway)]
                        extra += 1
                    puntos.append(sem)
                traza["marker"] = {"color": puntos}
        elif tipo in ("line", "scatter"):
            traza = {
                "type": "scatter",
                "mode": "lines+markers" if tipo == "line" else "markers",
                "name": nombre,
                "x": xs,
                "y": ys,
                "marker": {"color": color, "size": tema["marcador"]},
                "line": {"color": color, "width": tema["linea"]},
                "hovertext": hovers,
                "hoverinfo": "text",
            }
            if spec.denominator:
                traza["text"] = textos
            if tipo == "scatter":
                del traza["line"]
        elif tipo == "box":
            traza = {
                "type": "box",
                "name": nombre,
                "orientation": "h" if horizontal else "v",
                "marker": {"color": color},
                "boxpoints": False,
            }
            traza["x" if horizontal else "y"] = ys
            traza["y" if horizontal else "x"] = xs
        elif tipo == "histogram":
            traza = {"type": "histogram", "name": nombre, "x": xs, "marker": {"color": color}, "opacity": 0.85}
        else:  # heatmap
            traza = None
        if traza is not None:
            trazas.append(traza)

    if tipo == "heatmap":
        cx = _unicos([f.get(spec.x) for f in filas])
        cy_vals = _unicos([f.get(y0) for f in filas])
        celdas = {(_clave(f.get(y0)), _clave(f.get(spec.x))): f.get(spec.z) for f in filas}
        z = [[celdas.get((_clave(yv), _clave(xv))) for xv in cx] for yv in cy_vals]
        etiqueta_z = _titulo_eje(_etiqueta(table, spec.z), _unidad(table, spec.z))
        trazas = [
            {
                "type": "heatmap",
                "x": cx,
                "y": cy_vals,
                "z": z,
                "colorscale": [[0, tema["surface"]], [1, tema["accent"]]],
                "colorbar": {
                    "title": {"text": etiqueta_z, "font": {"color": tema["text"]}},
                    "tickfont": {"color": tema["text"]},
                },
                "hoverongaps": False,
                # La etiqueta viaja como DATO (customdata), nunca dentro del template:
                # una etiqueta con `%{...}` no se interpreta como campo de plotly.
                "customdata": [[etiqueta_z] * len(cx) for _ in cy_vals],
                "hovertemplate": "%{x} · %{y}<br>%{customdata}: %{z}<extra></extra>",
            }
        ]
        categorias_y = len(cy_vals)
    else:
        categorias_y = 0

    # Ejes.
    eje_x = _eje_base(tema, titulo_x, grilla=not (es_categorico and not horizontal))
    eje_y = _eje_base(tema, titulo_y, grilla=not (es_categorico and horizontal))
    if horizontal:
        eje_x, eje_y = _eje_base(tema, titulo_y), _eje_base(tema, titulo_x, grilla=False)
        eje_y.update({"type": "category", "categoryorder": "array", "categoryarray": categorias, "autorange": "reversed"})
    elif es_categorico:
        eje_x.update({"type": "category", "categoryorder": "array", "categoryarray": categorias})
    if tipo == "heatmap":
        eje_x["type"] = "category"
        eje_y["type"] = "category"
    if tipo != "heatmap":
        valores_valor = [f.get(c) for f in filas for c in spec.y] if spec.y else [f.get(spec.x) for f in filas]
        numericos = [v for v in valores_valor if v is not None]
        if numericos and all(_es_num(v) for v in numericos):
            eje_valor = eje_x if (horizontal or (tipo == "histogram" and not spec.y)) else eje_y
            eje_valor["tickformat"] = ",.6~f"
        if tipo == "scatter" and spec.y:
            xnum = [f.get(spec.x) for f in filas if f.get(spec.x) is not None]
            if xnum and all(_es_num(v) for v in xnum):
                eje_x["tickformat"] = ",.6~f"

    # Alto segun categorias.
    if horizontal:
        alto = min(ALTO_MAX, max(ALTO_MIN_HORIZONTAL, 140 + ALTO_POR_CATEGORIA * len(categorias) * max(1, len(series))))
    elif tipo == "heatmap":
        alto = min(ALTO_MAX, max(360, 140 + ALTO_POR_CATEGORIA * categorias_y))
    else:
        alto = ALTO_BASE

    titulo_leyenda = _etiqueta(table, spec.color) if spec.color else ""
    layout = {
        "title": {
            "text": figure.title,
            "x": 0,
            "xanchor": "left",
            "font": {"color": tema["text"], "size": tema["titulo_tam"]},
        },
        "paper_bgcolor": tema["paper"],
        "plot_bgcolor": tema["surface"],
        "font": {"family": tema["fuente"], "color": tema["text"], "size": tema["tam"]},
        "colorway": list(colorway),
        "separators": _separadores(tema),
        "xaxis": eje_x,
        "yaxis": eje_y,
        "showlegend": len(trazas) > 1 and tema["leyenda"] != "none",
        "legend": _leyenda(tema, titulo_leyenda),
        "hoverlabel": {"bgcolor": tema["surface"], "font": {"color": tema["text"], "family": tema["fuente"]}},
        "barmode": "group",
        "autosize": True,
        "height": alto,
        "margin": {"t": 64, "r": 24, "b": 56, "l": 56},
        "meta": {
            "figure_id": figure.figure_id,
            "variant": variante,
            "categories_total": cats_total,
            "categories_shown": cats_graf,
        },
    }
    if tipo == "histogram" and spec.y:
        layout["bargap"] = 0
    if tipo == "histogram" and not spec.y:
        layout["barmode"] = "overlay"
    if tipo == "heatmap":
        layout["showlegend"] = False
    return _sanear({"data": trazas, "layout": layout})


# --- Escape hatch backend_payload --------------------------------------------


def _es_url_externa(valor: Any) -> bool:
    return isinstance(valor, str) and valor.strip().lower().startswith(_PREFIJOS_URL)


def _contiene_url(valor: Any) -> bool:
    if isinstance(valor, str):
        return _es_url_externa(valor)
    if isinstance(valor, dict):
        return any(_contiene_url(v) for v in valor.values())
    if isinstance(valor, list):
        return any(_contiene_url(v) for v in valor)
    return False


def _buscar_url(nodo: Any) -> Optional[str]:
    """Nombre de la primera clave sensible con una URL externa, o `None`."""
    if isinstance(nodo, dict):
        for clave, valor in nodo.items():
            if clave.lower() in _CLAVES_URL and _contiene_url(valor):
                return clave
            hallada = _buscar_url(valor)
            if hallada is not None:
                return hallada
    elif isinstance(nodo, list):
        for valor in nodo:
            hallada = _buscar_url(valor)
            if hallada is not None:
                return hallada
    return None


def _rechazar_recursos_externos(p: dict) -> None:
    """Levanta `BackendPayloadError` (mensaje genérico, sin URLs) si el payload
    (ya saneado) puede cargar recursos externos: URLs bajo claves de recurso,
    `layout.images`, trazas de mapa/imagen o URLs en cualquier parte."""
    for traza in p.get("data", []):
        if isinstance(traza, dict) and str(traza.get("type", "")).strip().lower() in _TRAZAS_PROHIBIDAS:
            raise BackendPayloadError("backend_payload rechazado: tipo de traza no permitido (mapa/imagen)")
    layout = p.get("layout")
    if isinstance(layout, dict) and layout.get("images"):
        raise BackendPayloadError("backend_payload rechazado: 'layout.images' no permitido")
    clave = _buscar_url(p)
    if clave is not None:
        raise BackendPayloadError(f"backend_payload rechazado: recurso externo en la clave '{clave}'")


def _retematizar(payload: Any, tema: dict, variante: str, figure_id: str) -> Optional[dict]:
    """Copia del payload con SOLO el chrome re-tematizado (fondos, fuente, grillas,
    ejes, leyenda). Los colores de datos (trazas, colorway, colorscale) se respetan.

    Offline estricto: rechaza (`BackendPayloadError`) payloads con URLs externas
    bajo `source`/`style`/`url`/`href`/`topojsonURL`/`src`, `layout.images`,
    trazas de mapa o imagen; descarta `layout.template` (puede traer URLs)."""
    p = _sanear(payload)
    if not isinstance(p, dict) or not isinstance(p.get("data"), list):
        return None
    _rechazar_recursos_externos(p)
    layout = p.get("layout")
    if not isinstance(layout, dict):
        layout = {}
        p["layout"] = layout
    layout.pop("template", None)  # las plantillas pueden traer URLs: se descartan
    layout["paper_bgcolor"] = tema["paper"]
    layout["plot_bgcolor"] = tema["surface"]
    fuente = layout.get("font") if isinstance(layout.get("font"), dict) else {}
    fuente["family"] = tema["fuente"]
    fuente["color"] = tema["text"]
    layout["font"] = fuente

    def _titulo(v: Any) -> dict:
        t = {"text": v} if isinstance(v, str) else (v if isinstance(v, dict) else {})
        f = t.get("font") if isinstance(t.get("font"), dict) else {}
        f["color"] = tema["text"]
        t["font"] = f
        return t

    if "title" in layout:
        layout["title"] = _titulo(layout["title"])
    for nombre in ("xaxis", "yaxis"):
        if not isinstance(layout.get(nombre), dict):
            layout[nombre] = {}
    for clave in list(layout):
        if _RE_EJE.match(clave) and isinstance(layout[clave], dict):
            eje = layout[clave]
            eje["gridcolor"] = tema["grid"]
            eje["zerolinecolor"] = tema["grid"]
            eje["linecolor"] = tema["border"]
            tick = eje.get("tickfont") if isinstance(eje.get("tickfont"), dict) else {}
            tick["color"] = tema["text"]
            eje["tickfont"] = tick
            if "title" in eje:
                eje["title"] = _titulo(eje["title"])
    leyenda = layout.get("legend") if isinstance(layout.get("legend"), dict) else {}
    lf = leyenda.get("font") if isinstance(leyenda.get("font"), dict) else {}
    lf["color"] = tema["text"]
    leyenda["font"] = lf
    leyenda["bgcolor"] = "rgba(0,0,0,0)"
    if "title" in leyenda:
        leyenda["title"] = _titulo(leyenda["title"])
    layout["legend"] = leyenda
    layout["hoverlabel"] = {"bgcolor": tema["surface"], "font": {"color": tema["text"], "family": tema["fuente"]}}
    if not isinstance(layout.get("meta"), dict):
        layout["meta"] = {"figure_id": figure_id, "variant": variante}
    return p


# --- API publica --------------------------------------------------------------


def build_figure(figure: Any, table: Any, style: Any, variant: str) -> dict:
    """Payload plotly.js JSON-puro (`{"data", "layout"}`) de `figure` para `variant`
    en {"screen", "print"}. `table` es el `TableArtifact` de respaldo (o `None`).

    Nunca muta `figure`, `table` ni `style`. Con `figure.backend == "plotly"` y
    `backend_payload`, se copia y se re-tematiza SOLO el chrome (los colores de
    datos del payload se respetan); en otro caso se construye desde el spec.
    `ValueError` si `variant` es invalida."""
    if not isinstance(variant, str) or variant not in VARIANTES:
        raise ValueError(f"variant: se esperaba uno de {VARIANTES}, se recibió {variant!r}")
    tema = _tema(style, variant)
    if getattr(figure, "backend", None) == "plotly" and getattr(figure, "backend_payload", None) is not None:
        retematizado = _retematizar(figure.backend_payload, tema, variant, figure.figure_id)
        if retematizado is not None:
            return retematizado
    return _desde_spec(figure, table, tema, variant)


def _leer_bundle_proyecto(style: Any, repo_root: Any, motivos: list) -> Optional[str]:
    """Paso 1 de `find_plotly_bundle`: archivo declarado en `style.visual.chart.plotly_js_file`."""
    ruta = getattr(getattr(getattr(style, "visual", None), "chart", None), "plotly_js_file", None)
    if not ruta:
        return None
    if not isinstance(ruta, str):
        motivos.append("chart.plotly_js_file: no es texto")
        return None
    if (
        PurePosixPath(ruta).is_absolute()
        or PureWindowsPath(ruta).is_absolute()
        or ruta.startswith(("/", "\\"))
        or ".." in PurePosixPath(ruta.replace("\\", "/")).parts
    ):
        motivos.append("chart.plotly_js_file: la ruta debe ser relativa y dentro del repo")
        return None
    repo = Path(repo_root).resolve()
    candidato = (repo / ruta).resolve()
    try:
        candidato.relative_to(repo)
    except ValueError:
        motivos.append("chart.plotly_js_file: la ruta queda fuera del repo")
        return None
    permitido, motivo = evidence.read_allowed(repo, candidato)
    if not permitido:
        motivos.append(f"chart.plotly_js_file: lectura denegada ({motivo})")
        return None
    if not candidato.is_file():
        motivos.append("chart.plotly_js_file: el archivo no existe")
        return None
    try:
        texto = candidato.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        motivos.append("chart.plotly_js_file: no se pudo leer como texto UTF-8")
        return None
    if not texto.strip():
        motivos.append("chart.plotly_js_file: archivo vacío")
        return None
    if "Plotly" not in texto:
        motivos.append("bundle sin Plotly")
        return None
    return texto


def find_plotly_bundle(style: Any, repo_root: Any, motivos: Optional[list] = None) -> Optional[str]:
    """Texto del bundle `plotly.js` o `None`. Orden: (1) archivo del proyecto
    (`chart.plotly_js_file`, relativo, dentro del repo, evaluado con
    `evidence.read_allowed` ANTES de leer); (2) paquete `plotly` ya instalado
    (`plotly.offline.get_plotlyjs()`, import perezoso); (3) `None`. Nunca lanza.

    `motivos` (opcional, lista): se le agregan las razones por las que un paso se
    ignoro (sin rutas locales)."""
    razones = motivos if isinstance(motivos, list) else []
    try:
        texto = _leer_bundle_proyecto(style, repo_root, razones)
        if texto is not None:
            return texto
    except Exception:  # noqa: BLE001 -- nunca lanza
        razones.append("chart.plotly_js_file: error inesperado; se ignora")
    try:
        from plotly import offline as _plotly_offline  # import perezoso, opcional

        js = _plotly_offline.get_plotlyjs()
        if isinstance(js, str) and js.strip():
            if "Plotly" in js:
                return js
            razones.append("bundle sin Plotly")
        else:
            razones.append("plotly instalado pero get_plotlyjs() no devolvió texto")
    except ImportError:
        razones.append("paquete plotly no instalado")
    except Exception:  # noqa: BLE001 -- nunca lanza
        razones.append("plotly instalado pero get_plotlyjs() falló")
    return None

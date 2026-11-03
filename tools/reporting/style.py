"""Design system de reportes (v0.6 Change 4, `20260918-reporting-design-system-and-html-renderer`).

Define DATOS (dataclasses `frozen`), no HTML: tokens visuales (`VisualStyle`) y
contrato editorial (`EditorialStyle`). El renderer los traduce a CSS/HTML; este
modulo no importa render, backend grafico ni publish, ni `reporting.core`.
Solo stdlib + `dsguard.checks` + `reporting.evidence` (para la lectura del
override del proyecto).

Garantias:
- default GENERICO (idioma `en`, sin branding, sin paletas de cliente, sin
  vocabulario de dominio), fuentes del sistema solamente (offline);
- todo valor se valida al CONSTRUIR (`__post_init__`): fuera de rango, color que
  no sea `#rrggbb`, enum invalido o tipo erroneo => `StyleError`;
- `merge_style`/`default_style` devuelven objetos NUEVOS: nunca mutan `base` ni
  el default (los dicts `labels`/`glossary` se copian);
- salidas deterministas (sin reloj, sin azar, sin `strftime` dependiente del SO).
"""
from __future__ import annotations

import json
import math
import numbers
import re
import sys
from dataclasses import dataclass, field, fields, is_dataclass, replace
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping, Optional, Union

_TOOLS_DIR = Path(__file__).resolve().parents[1]
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from dsguard import checks  # noqa: E402
from dsguard.checks import CheckResult  # noqa: E402

from . import evidence  # noqa: E402

# --- Constantes ----------------------------------------------------------------

SCHEMA_VERSION = 1
STYLE_RELATIVE_PATH = ".harmessi/report-style.json"
AA_TEXT_RATIO = 4.5  # WCAG AA texto normal

CODE_STYLE_CONTRAST = "STYLE-CONTRAST"
CODE_STYLE_PALETTE = "STYLE-PALETTE"

AUDIENCES = ("technical", "business", "mixed")
UNCERTAINTY_DISPLAYS = ("always", "non_descriptive", "never")
INSIGHT_STYLES = ("callout", "list")
RECOMMENDATIONS_POLICIES = ("evidence_only", "hide", "show")
LEGEND_POSITIONS = ("bottom", "right", "top", "none")
ALIGNMENTS = ("left", "right", "center")

# Todos se aplican con `fullmatch` (sin anclas `$`, que aceptaria un `\n` final).
_HEX_RE = re.compile(r"#[0-9a-fA-F]{6}")
# Fuentes: solo nombres de familia (sin `(`, `:`, `;`, `/`, `{`): imposible colar url()/@import.
_FONT_RE = re.compile(r"[A-Za-z0-9 ,'\"_.\-]+")
_DATE_FORMAT_RE = re.compile(r"(?:%[YymdHM]|[-/. :])+")


def _quotes_balanced(texto: str) -> bool:
    """Comillas `'`/`"` balanceadas: cada apertura se cierra con la misma; la otra clase
    dentro de un par es literal. Comillas sueltas => False."""
    abierta = ""
    for ch in texto:
        if ch in ("'", '"'):
            if not abierta:
                abierta = ch
            elif ch == abierta:
                abierta = ""
    return abierta == ""
_DATE_TOKEN_RE = re.compile(r"%([YymdHM])")


class StyleError(ValueError):
    """Estilo invalido (valor, esquema, archivo de override). Mensajes sin rutas locales."""


# --- Validadores ---------------------------------------------------------------


def _fail(owner: str, name: str, msg: str) -> None:
    raise StyleError(f"{owner}.{name}: {msg}")


def _v_color(owner: str, name: str, v: Any) -> None:
    if not isinstance(v, str) or not _HEX_RE.fullmatch(v):
        _fail(owner, name, "se esperaba un color '#rrggbb'")


def _v_num(owner: str, name: str, v: Any, lo: float, hi: float, integer: bool) -> None:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        _fail(owner, name, "se esperaba un numero")
    if integer and not isinstance(v, int):
        _fail(owner, name, "se esperaba un entero")
    if isinstance(v, float) and not math.isfinite(v):
        _fail(owner, name, "numero no finito")
    if not (lo <= v <= hi):
        _fail(owner, name, f"fuera de rango [{lo}, {hi}]")


def _v_bool(owner: str, name: str, v: Any) -> None:
    if not isinstance(v, bool):
        _fail(owner, name, "se esperaba booleano")


def _v_enum(owner: str, name: str, v: Any, allowed: tuple) -> None:
    if not isinstance(v, str) or v not in allowed:
        _fail(owner, name, f"valor fuera del enum {list(allowed)}")


def _v_font(owner: str, name: str, v: Any) -> None:
    if (not isinstance(v, str) or not v.strip() or len(v) > 300
            or not _FONT_RE.fullmatch(v) or not _quotes_balanced(v)):
        _fail(owner, name, "se esperaba una lista de familias de fuente del sistema (sin url/@import)")


def _v_text(owner: str, name: str, v: Any, max_len: int, allow_empty: bool = False) -> None:
    if not isinstance(v, str) or len(v) > max_len or (not allow_empty and not v.strip()):
        _fail(owner, name, f"se esperaba texto (max {max_len} caracteres)")


def _apply_rules(obj: Any, rules: Mapping[str, tuple]) -> None:
    owner = type(obj).__name__
    for name, rule in rules.items():
        v = getattr(obj, name)
        kind = rule[0]
        if kind == "color":
            _v_color(owner, name, v)
        elif kind == "num":
            _v_num(owner, name, v, rule[1], rule[2], rule[3])
        elif kind == "bool":
            _v_bool(owner, name, v)
        elif kind == "enum":
            _v_enum(owner, name, v, rule[1])
        elif kind == "font":
            _v_font(owner, name, v)


def _coerce_colors(obj: Any, name: str) -> None:
    """Lista/tupla de colores `#rrggbb` -> tupla (frozen: via object.__setattr__)."""
    v = getattr(obj, name)
    owner = type(obj).__name__
    if not isinstance(v, (list, tuple)):
        _fail(owner, name, "se esperaba una lista de colores")
    for item in v:
        _v_color(owner, name, item)
    object.__setattr__(obj, name, tuple(v))


_SEMANTIC_NAMES = ("risk_low", "risk_medium", "risk_high", "ok", "warn", "error", "info")

_RULES_PALETTE = {
    **{n: ("color",) for n in ("surface", "surface_alt", "text", "muted", "border", "accent", *_SEMANTIC_NAMES)},
}
_RULES_TYPOGRAPHY = {
    "font_sans": ("font",),
    "font_mono": ("font",),
    "size_base": ("num", 10, 24, False),
    "size_small": ("num", 8, 20, False),
    "size_h1": ("num", 16, 64, False),
    "size_h2": ("num", 14, 48, False),
    "size_h3": ("num", 12, 36, False),
    "line_height": ("num", 1.0, 2.5, False),
}
_RULES_SPACING = {n: ("num", 0, 128, True) for n in ("xs", "sm", "md", "lg", "xl")}
_RULES_RADII = {n: ("num", 0, 64, True) for n in ("sm", "md", "lg")}
_RULES_WIDTHS = {n: ("num", 320, 2400, True) for n in ("narrow", "normal", "wide")}
_RULES_TABLE = {
    "zebra": ("bool",),
    "tabular_nums": ("bool",),
    "numbers_align": ("enum", ALIGNMENTS),
    "text_align": ("enum", ALIGNMENTS),
    "cell_padding": ("num", 0, 32, True),
}
_RULES_PANEL = {
    "padding": ("num", 0, 64, True),
    "border_width": ("num", 0, 8, True),
    "shadow": ("bool",),
}
_RULES_CALLOUT = {
    "padding": ("num", 0, 64, True),
    "border_width": ("num", 0, 12, True),
}
_RULES_RESPONSIVE = {n: ("num", 320, 2400, True) for n in ("breakpoint_sm", "breakpoint_md", "breakpoint_lg")}
_RULES_CHART_THEME = {
    "font_family": ("font",),
    "font_size": ("num", 8, 32, False),
    "title_size": ("num", 8, 48, False),
    "line_width": ("num", 0.5, 8, False),
    "marker_size": ("num", 2, 24, False),
    "grid_color": ("color",),
    "grid_width": ("num", 0, 4, False),
    "legend_position": ("enum", LEGEND_POSITIONS),
}
_RULES_LOCALE_FORMAT = {"percent_decimals": ("num", 0, 6, True)}


# --- Dataclasses del design system ----------------------------------------------


@dataclass(frozen=True)
class ThemePalette:
    """Paleta de un tema (`screen` oscuro / `print` claro)."""

    surface: str
    surface_alt: str
    text: str
    muted: str
    border: str
    accent: str
    risk_low: str
    risk_medium: str
    risk_high: str
    ok: str
    warn: str
    error: str
    info: str
    categorical: tuple = ()

    def __post_init__(self) -> None:
        _apply_rules(self, _RULES_PALETTE)
        _coerce_colors(self, "categorical")


@dataclass(frozen=True)
class Typography:
    """Solo fuentes del sistema (offline) y escala de tamanos en px."""

    font_sans: str = "system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"
    font_mono: str = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
    size_base: float = 16
    size_small: float = 13
    size_h1: float = 32
    size_h2: float = 24
    size_h3: float = 19
    line_height: float = 1.55

    def __post_init__(self) -> None:
        _apply_rules(self, _RULES_TYPOGRAPHY)


@dataclass(frozen=True)
class Spacing:
    xs: int = 4
    sm: int = 8
    md: int = 16
    lg: int = 24
    xl: int = 40

    def __post_init__(self) -> None:
        _apply_rules(self, _RULES_SPACING)


@dataclass(frozen=True)
class Radii:
    sm: int = 4
    md: int = 8
    lg: int = 12

    def __post_init__(self) -> None:
        _apply_rules(self, _RULES_RADII)


@dataclass(frozen=True)
class ContentWidths:
    narrow: int = 640
    normal: int = 960
    wide: int = 1280

    def __post_init__(self) -> None:
        _apply_rules(self, _RULES_WIDTHS)


@dataclass(frozen=True)
class TableStyle:
    zebra: bool = True
    tabular_nums: bool = True
    numbers_align: str = "right"
    text_align: str = "left"
    cell_padding: int = 8

    def __post_init__(self) -> None:
        _apply_rules(self, _RULES_TABLE)


@dataclass(frozen=True)
class PanelStyle:
    """Panels/cards."""

    padding: int = 16
    border_width: int = 1
    shadow: bool = False

    def __post_init__(self) -> None:
        _apply_rules(self, _RULES_PANEL)


@dataclass(frozen=True)
class CalloutStyle:
    padding: int = 12
    border_width: int = 4

    def __post_init__(self) -> None:
        _apply_rules(self, _RULES_CALLOUT)


@dataclass(frozen=True)
class ResponsiveStyle:
    """Breakpoints en px (ascendentes)."""

    breakpoint_sm: int = 480
    breakpoint_md: int = 768
    breakpoint_lg: int = 1200

    def __post_init__(self) -> None:
        _apply_rules(self, _RULES_RESPONSIVE)
        if not (self.breakpoint_sm < self.breakpoint_md < self.breakpoint_lg):
            _fail("ResponsiveStyle", "breakpoints", "deben ser estrictamente ascendentes")


@dataclass(frozen=True)
class ChartTheme:
    """Estilo de graficos de UN tema (fuente, tamanos, grosores, colorway, grid, leyenda)."""

    font_family: str
    font_size: float
    title_size: float
    line_width: float
    marker_size: float
    colorway: tuple
    grid_color: str
    grid_width: float
    legend_position: str

    def __post_init__(self) -> None:
        _apply_rules(self, _RULES_CHART_THEME)
        _coerce_colors(self, "colorway")


@dataclass(frozen=True)
class ChartStyle:
    screen: ChartTheme
    print: ChartTheme
    # Ruta RELATIVA dentro del repo a un bundle plotly.js del proyecto (opcional). Se lee
    # solo via `evidence.read_allowed` (lo hace `plotly_backend.find_plotly_bundle`).
    plotly_js_file: Optional[str] = None

    def __post_init__(self) -> None:
        for nombre in ("screen", "print"):
            if not isinstance(getattr(self, nombre), ChartTheme):
                _fail("ChartStyle", nombre, "se esperaba ChartTheme")
        p = self.plotly_js_file
        if p is not None:
            if (not isinstance(p, str) or not p.strip() or len(p) > 300
                    or any(ord(c) < 32 for c in p)):
                _fail("ChartStyle", "plotly_js_file", "se esperaba una ruta relativa")
            norm = p.replace("\\", "/")
            partes = norm.split("/")
            if norm.startswith("/") or re.match(r"^[A-Za-z]:", norm) or ".." in partes:
                _fail("ChartStyle", "plotly_js_file", "debe ser relativa y dentro del repo")


@dataclass(frozen=True)
class LocaleFormat:
    decimal_sep: str = "."
    thousands_sep: str = ","
    date_format: str = "%Y-%m-%d"
    percent_decimals: int = 1

    def __post_init__(self) -> None:
        _apply_rules(self, _RULES_LOCALE_FORMAT)
        if not isinstance(self.decimal_sep, str) or len(self.decimal_sep) != 1:
            _fail("LocaleFormat", "decimal_sep", "se esperaba 1 caracter")
        if not isinstance(self.thousands_sep, str) or len(self.thousands_sep) > 1:
            _fail("LocaleFormat", "thousands_sep", "se esperaba 0 o 1 caracter")
        if self.decimal_sep == self.thousands_sep:
            _fail("LocaleFormat", "thousands_sep", "no puede igualar a decimal_sep")
        if self.decimal_sep.isdigit() or self.thousands_sep.isdigit():
            _fail("LocaleFormat", "decimal_sep", "los separadores no pueden ser digitos")
        if not isinstance(self.date_format, str) or not _DATE_FORMAT_RE.fullmatch(self.date_format):
            _fail("LocaleFormat", "date_format", "solo tokens %Y %y %m %d %H %M y separadores - / . :")


@dataclass(frozen=True)
class VisualStyle:
    screen: ThemePalette
    print: ThemePalette
    chart: ChartStyle
    typography: Typography = field(default_factory=Typography)
    spacing: Spacing = field(default_factory=Spacing)
    radii: Radii = field(default_factory=Radii)
    content_widths: ContentWidths = field(default_factory=ContentWidths)
    table: TableStyle = field(default_factory=TableStyle)
    panel: PanelStyle = field(default_factory=PanelStyle)
    callout: CalloutStyle = field(default_factory=CalloutStyle)
    responsive: ResponsiveStyle = field(default_factory=ResponsiveStyle)
    locale_format: LocaleFormat = field(default_factory=LocaleFormat)

    def __post_init__(self) -> None:
        esperados = (
            ("screen", ThemePalette), ("print", ThemePalette), ("chart", ChartStyle),
            ("typography", Typography), ("spacing", Spacing), ("radii", Radii),
            ("content_widths", ContentWidths), ("table", TableStyle), ("panel", PanelStyle),
            ("callout", CalloutStyle), ("responsive", ResponsiveStyle),
            ("locale_format", LocaleFormat),
        )
        for nombre, tipo in esperados:
            if not isinstance(getattr(self, nombre), tipo):
                _fail("VisualStyle", nombre, f"se esperaba {tipo.__name__}")


# Textos de interfaz (claves) — los presets `en`/`es` deben tener EXACTAMENTE estas claves.
_LABELS_EN = {
    "tech_sheet": "Technical sheet",
    "method_details": "Method details",
    "backup_table": "Supporting table",
    "conclusion": "Conclusion",
    "glossary": "Glossary",
    "insights": "Key findings",
    "report_id": "Report ID",
    "run_id": "Run ID",
    "kind": "Kind",
    "scope": "Scope",
    "data_cutoff": "Data cutoff",
    "git_commit": "Git commit",
    "harmessi_version": "Harmessi version",
    "generated_at": "Generated at",
    "sources": "Sources",
    "exclusions": "Exclusions",
    "holdout_access": "Holdout access",
    "sensitivity": "Sensitivity",
    "rows": "Rows",
    "hash": "Hash",
    "date_min": "Earliest date",
    "date_max": "Latest date",
    "none": "None",
    "showing_n_of_m": "Showing {n} of {m}",
    "sample_size": "n={n}",
    "reference_global": "Overall reference (weighted)",
    "population": "Population",
    "temporal_scope": "Time scope",
    "uncertainty": "Uncertainty",
    "requires_review": "requires review",
    "scope_exploratory": "Not an input for feature selection / not valid for model decisions",
    "figure_not_rendered": "Figure not rendered: plotly.js bundle not available",
    "recommendation_withheld": "Recommendation withheld: insufficient evidence",
    "sensitive_omitted": "Sensitive content omitted",
    "content_hash": "Content hash",
    "not_available": "n/a",
    "dirty": "dirty",
}
_LABELS_ES = {
    "tech_sheet": "Ficha técnica",
    "method_details": "Detalle del método",
    "backup_table": "Tabla de respaldo",
    "conclusion": "Conclusión",
    "glossary": "Glosario",
    "insights": "Hallazgos clave",
    "report_id": "ID del reporte",
    "run_id": "ID de corrida",
    "kind": "Tipo",
    "scope": "Alcance",
    "data_cutoff": "Fecha de corte de datos",
    "git_commit": "Commit de git",
    "harmessi_version": "Versión de Harmessi",
    "generated_at": "Generado el",
    "sources": "Fuentes",
    "exclusions": "Exclusiones",
    "holdout_access": "Acceso a holdout",
    "sensitivity": "Sensibilidad",
    "rows": "Filas",
    "hash": "Hash",
    "date_min": "Fecha mínima",
    "date_max": "Fecha máxima",
    "none": "Ninguna",
    "showing_n_of_m": "Mostrando {n} de {m}",
    "sample_size": "n={n}",
    "reference_global": "Referencia global (ponderada)",
    "population": "Población",
    "temporal_scope": "Alcance temporal",
    "uncertainty": "Incertidumbre",
    "requires_review": "requiere revisión",
    "scope_exploratory": "No es insumo de selección de features / no válido para decisiones de modelo",
    "figure_not_rendered": "Figura no renderizada: bundle de plotly.js no disponible",
    "recommendation_withheld": "Recomendación retenida: evidencia insuficiente",
    "sensitive_omitted": "Contenido sensible omitido",
    "content_hash": "Hash de contenido",
    "not_available": "s/d",
    "dirty": "modificado",
}

LABEL_KEYS = frozenset(_LABELS_EN)

# Presets de locale: DATA del design layer (no del core). Se copian al usarlos.
LOCALE_PRESETS = {
    "en": {
        "decimal_sep": ".",
        "thousands_sep": ",",
        "date_format": "%Y-%m-%d",
        "percent_decimals": 1,
        "labels": _LABELS_EN,
    },
    "es": {
        "decimal_sep": ",",
        "thousands_sep": ".",
        "date_format": "%d/%m/%Y",
        "percent_decimals": 1,
        "labels": _LABELS_ES,
    },
}


def _preset_format(locale: str) -> LocaleFormat:
    p = LOCALE_PRESETS[locale]
    return LocaleFormat(
        decimal_sep=p["decimal_sep"],
        thousands_sep=p["thousands_sep"],
        date_format=p["date_format"],
        percent_decimals=p["percent_decimals"],
    )


@dataclass(frozen=True)
class EditorialStyle:
    locale: str = "en"
    audience: str = "mixed"
    tone: str = "neutral, precise"
    explain_terms: bool = False
    glossary: dict = field(default_factory=dict)
    comparative_context: bool = True
    uncertainty_display: str = "always"
    insight_style: str = "callout"
    recommendations_policy: str = "evidence_only"
    labels: dict = field(default_factory=lambda: dict(_LABELS_EN))

    def __post_init__(self) -> None:
        _v_enum("EditorialStyle", "locale", self.locale, tuple(LOCALE_PRESETS))
        _v_enum("EditorialStyle", "audience", self.audience, AUDIENCES)
        _v_text("EditorialStyle", "tone", self.tone, 200, allow_empty=True)
        _v_bool("EditorialStyle", "explain_terms", self.explain_terms)
        _v_bool("EditorialStyle", "comparative_context", self.comparative_context)
        _v_enum("EditorialStyle", "uncertainty_display", self.uncertainty_display, UNCERTAINTY_DISPLAYS)
        _v_enum("EditorialStyle", "insight_style", self.insight_style, INSIGHT_STYLES)
        _v_enum("EditorialStyle", "recommendations_policy", self.recommendations_policy,
                RECOMMENDATIONS_POLICIES)
        if not isinstance(self.glossary, dict):
            _fail("EditorialStyle", "glossary", "se esperaba un objeto termino -> definicion")
        for k, v in self.glossary.items():
            _v_text("EditorialStyle", "glossary", k, 100)
            _v_text("EditorialStyle", "glossary", v, 1000)
        if not isinstance(self.labels, dict):
            _fail("EditorialStyle", "labels", "se esperaba un objeto clave -> texto")
        for k, v in self.labels.items():
            if not isinstance(k, str) or k not in LABEL_KEYS:
                _fail("EditorialStyle", "labels", "clave de label desconocida")
            _v_text("EditorialStyle", "labels", v, 300)

    def label(self, key: str) -> str:
        """Texto de interfaz: label propio, luego preset del locale, luego `en`, luego la clave."""
        if key in self.labels:
            return self.labels[key]
        preset = LOCALE_PRESETS.get(self.locale, LOCALE_PRESETS["en"])["labels"]
        return preset.get(key, _LABELS_EN.get(key, key))


@dataclass(frozen=True)
class Style:
    visual: VisualStyle
    editorial: EditorialStyle

    def __post_init__(self) -> None:
        if not isinstance(self.visual, VisualStyle):
            _fail("Style", "visual", "se esperaba VisualStyle")
        if not isinstance(self.editorial, EditorialStyle):
            _fail("Style", "editorial", "se esperaba EditorialStyle")


# --- Tema por defecto -----------------------------------------------------------


class HarmessiDefaultTheme:
    """Tema GENERICO por defecto: pantalla oscura, impresion clara, paleta categorica
    daltonica-segura (base Okabe-Ito), fuentes del sistema. Sin branding."""

    @staticmethod
    def screen_palette() -> ThemePalette:
        return ThemePalette(
            surface="#0f172a", surface_alt="#1e293b", text="#e5e7eb", muted="#a3aab8",
            border="#334155", accent="#60a5fa",
            risk_low="#4ade80", risk_medium="#fbbf24", risk_high="#f87171",
            ok="#4ade80", warn="#fbbf24", error="#f87171", info="#60a5fa",
            categorical=("#56b4e9", "#e69f00", "#2fc79a", "#cc79a7",
                         "#f0e442", "#e8743b", "#a3aab8", "#8da0ff"),
        )

    @staticmethod
    def print_palette() -> ThemePalette:
        return ThemePalette(
            surface="#ffffff", surface_alt="#f3f4f6", text="#111827", muted="#4b5563",
            border="#d1d5db", accent="#1d4ed8",
            risk_low="#166534", risk_medium="#92400e", risk_high="#b91c1c",
            ok="#166534", warn="#92400e", error="#b91c1c", info="#1d4ed8",
            categorical=("#0072b2", "#d55e00", "#009e73", "#cc79a7",
                         "#b8860b", "#56b4e9", "#000000", "#7f7f7f"),
        )

    @classmethod
    def build(cls, locale: str = "en") -> Style:
        if locale not in LOCALE_PRESETS:
            raise StyleError(f"locale '{locale}' sin preset")
        typo = Typography()
        screen, prn = cls.screen_palette(), cls.print_palette()

        def chart_theme(p: ThemePalette, grid: str) -> ChartTheme:
            return ChartTheme(
                font_family=typo.font_sans, font_size=13, title_size=16, line_width=2,
                marker_size=7, colorway=p.categorical, grid_color=grid, grid_width=1,
                legend_position="bottom",
            )

        visual = VisualStyle(
            screen=screen,
            print=prn,
            chart=ChartStyle(
                screen=chart_theme(screen, "#334155"),
                print=chart_theme(prn, "#d1d5db"),
                plotly_js_file=None,
            ),
            typography=typo,
            locale_format=_preset_format(locale),
        )
        editorial = EditorialStyle(locale=locale, labels=dict(LOCALE_PRESETS[locale]["labels"]))
        return Style(visual=visual, editorial=editorial)


def default_style() -> Style:
    """Style por defecto: objeto NUEVO en cada llamada (sin estado compartido)."""
    return HarmessiDefaultTheme.build("en")


# --- Contraste WCAG -------------------------------------------------------------


def _luminance(color: str) -> float:
    if not isinstance(color, str) or not _HEX_RE.fullmatch(color):
        raise StyleError("color invalido: se esperaba '#rrggbb'")
    canales = []
    for i in (1, 3, 5):
        c = int(color[i:i + 2], 16) / 255.0
        canales.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * canales[0] + 0.7152 * canales[1] + 0.0722 * canales[2]


def contrast_ratio(fg: str, bg: str) -> float:
    """Razon de contraste WCAG 2.x entre dos colores `#rrggbb` (1.0 a 21.0)."""
    a, b = _luminance(fg), _luminance(bg)
    hi, lo = (a, b) if a >= b else (b, a)
    return (hi + 0.05) / (lo + 0.05)


# --- Overrides y merge ----------------------------------------------------------


def style_to_dict(style: Style) -> dict:
    """Copia profunda del estilo como dict JSON-compatible (tuplas -> listas)."""
    def conv(o: Any) -> Any:
        if is_dataclass(o) and not isinstance(o, type):
            return {f.name: conv(getattr(o, f.name)) for f in fields(o)}
        if isinstance(o, (list, tuple)):
            return [conv(x) for x in o]
        if isinstance(o, dict):
            return {k: conv(v) for k, v in o.items()}
        return o
    return conv(style)


def _merge_obj(obj: Any, over: Any, path: str) -> Any:
    if not isinstance(over, Mapping):
        raise StyleError(f"{path}: se esperaba un objeto")
    nombres = {f.name for f in fields(obj)}
    for k in over:
        if not isinstance(k, str) or k not in nombres:
            raise StyleError(f"{path}: clave desconocida '{k}'")
    kwargs = {}
    for f in fields(obj):
        actual = getattr(obj, f.name)
        sub = f"{path}.{f.name}"
        if is_dataclass(actual):
            # Siempre se reconstruye (aunque no haya override): el resultado no comparte
            # ningun dict mutable (`labels`/`glossary`) con `base`.
            kwargs[f.name] = _merge_obj(actual, over.get(f.name, {}), sub)
        elif f.name in over:
            v = over[f.name]
            if isinstance(actual, dict):
                if not isinstance(v, Mapping):
                    raise StyleError(f"{sub}: se esperaba un objeto")
                nuevo = dict(actual)
                nuevo.update(v)
                kwargs[f.name] = nuevo
            elif isinstance(actual, tuple):
                if not isinstance(v, (list, tuple)):
                    raise StyleError(f"{sub}: se esperaba una lista")
                kwargs[f.name] = tuple(v)
            else:
                kwargs[f.name] = v
        else:
            kwargs[f.name] = dict(actual) if isinstance(actual, dict) else actual
    # Reconstruir SIEMPRE por el constructor (valida via __post_init__).
    try:
        return type(obj)(**kwargs)
    except StyleError:
        raise
    except (TypeError, ValueError) as exc:  # tipos inesperados en __post_init__
        raise StyleError(f"{path}: valor invalido ({type(exc).__name__})") from None


def _rebase_locale(base: Style, nuevo: str) -> Style:
    """Al cambiar de locale, los labels/formato SIN personalizar pasan al preset nuevo."""
    viejo = base.editorial.locale
    if nuevo == viejo or nuevo not in LOCALE_PRESETS:
        return base
    labels = dict(base.editorial.labels)
    if labels == LOCALE_PRESETS[viejo]["labels"]:
        labels = dict(LOCALE_PRESETS[nuevo]["labels"])
    fmt = base.visual.locale_format
    if fmt == _preset_format(viejo):
        fmt = _preset_format(nuevo)
    return replace(
        base,
        editorial=replace(base.editorial, locale=nuevo, labels=labels),
        visual=replace(base.visual, locale_format=fmt),
    )


def merge_style(base: Style, overrides: Mapping) -> Style:
    """Deep-merge validado de `overrides` (`{"visual": {...}, "editorial": {...}}`) sobre `base`.

    Devuelve un `Style` NUEVO; no muta `base` ni el default. Claves desconocidas, colores
    mal formados, tipos o rangos invalidos => `StyleError`. Si `editorial.locale` cambia, los
    labels y el formato de locale que seguian el preset anterior pasan al preset nuevo
    (salvo que el override los fije explicitamente)."""
    if not isinstance(base, Style):
        raise StyleError("base: se esperaba un Style")
    if not isinstance(overrides, Mapping):
        raise StyleError("overrides: se esperaba un objeto")
    ed = overrides.get("editorial")
    if isinstance(ed, Mapping) and isinstance(ed.get("locale"), str):
        base = _rebase_locale(base, ed["locale"])
    return _merge_obj(base, overrides, "style")


def _reject_constant(nombre: str) -> Any:
    raise StyleError("JSON invalido: constante no permitida")


def _no_duplicates(pares: list) -> dict:
    d: dict = {}
    for k, v in pares:
        if k in d:
            raise StyleError("JSON invalido: clave duplicada")
        d[k] = v
    return d


def _relative_label(ruta: Any) -> str:
    """Valida que `ruta` sea relativa (sin `..`, sin absoluta, sin control) y la normaliza a
    posix. `StyleError` si no; el mensaje no incluye la ruta invalida."""
    if not isinstance(ruta, (str, Path)) or str(ruta) == "":
        raise StyleError("ruta de style: se esperaba una ruta relativa")
    texto = str(ruta)
    if any(ord(c) < 32 for c in texto):
        raise StyleError("ruta de style: caracteres invalidos")
    norm = texto.replace("\\", "/")
    if norm.startswith("/") or re.match(r"[A-Za-z]:", norm) or Path(texto).is_absolute():
        raise StyleError("ruta de style: debe ser relativa al repositorio (no absoluta)")
    if ".." in norm.split("/"):
        raise StyleError("ruta de style: no puede contener '..'")
    return norm


def _cargar_style(repo_root: Any, ruta: Any, missing_ok: bool) -> Style:
    """Nucleo comun de `load_style`/`load_style_file`. Mensajes sin rutas absolutas."""
    etiqueta = _relative_label(ruta)
    try:
        repo = Path(repo_root).resolve()
        path = repo / etiqueta
        resuelta = path.resolve()
        resuelta.relative_to(repo)
    except (ValueError, OSError, RuntimeError, TypeError):
        raise StyleError(f"{etiqueta}: la ruta queda fuera del repositorio") from None
    if not path.exists():
        if missing_ok:
            return default_style()
        raise StyleError(f"{etiqueta}: archivo de style inexistente")
    if not path.is_file():
        raise StyleError(f"{etiqueta}: no es un archivo")
    permitido, _motivo = evidence.read_allowed(repo, path)
    if not permitido:
        raise StyleError(f"{etiqueta}: lectura denegada por las guardas")
    try:
        texto = path.read_bytes().decode("utf-8-sig")
        datos = json.loads(texto, parse_constant=_reject_constant, object_pairs_hook=_no_duplicates)
    except StyleError:
        raise
    except (OSError, UnicodeDecodeError, ValueError, RecursionError):
        raise StyleError(f"{etiqueta}: ilegible o JSON corrupto") from None
    if not isinstance(datos, dict):
        raise StyleError(f"{etiqueta}: se esperaba un objeto JSON")
    version = datos.get("schema_version")
    if isinstance(version, bool) or version != SCHEMA_VERSION:
        raise StyleError(f"{etiqueta}: schema_version debe ser {SCHEMA_VERSION}")
    overrides = {k: v for k, v in datos.items() if k != "schema_version"}
    return merge_style(default_style(), overrides)


def load_style(repo_root: Any) -> Style:
    """Carga `.harmessi/report-style.json` (opcional).

    Ausente => `default_style()` (sin heuristica). Denegado por `evidence.read_allowed`,
    ilegible, JSON corrupto, `schema_version` distinta de 1, clave desconocida, color
    mal formado o valor fuera de rango => `StyleError`."""
    return _cargar_style(repo_root, STYLE_RELATIVE_PATH, True)


def load_style_file(repo_root: Any, ruta: Any, *, missing_ok: bool = True) -> Style:
    """Como `load_style` pero desde `ruta` RELATIVA dentro del repo (sin `..`, sin absoluta,
    contenida tras `resolve()`; `read_allowed` antes de leer). Mismo esquema estricto
    (`schema_version` 1, `merge_style` sobre el default). Ausente => default salvo
    `missing_ok=False` (=> `StyleError`). Mensajes sin rutas absolutas."""
    return _cargar_style(repo_root, ruta, missing_ok)


# --- check_style ----------------------------------------------------------------


def _contrast_pairs(nombre: str, p: ThemePalette) -> list:
    pares = [
        (f"{nombre}.text/surface", p.text, p.surface),
        (f"{nombre}.text/surface_alt", p.text, p.surface_alt),
        (f"{nombre}.muted/surface", p.muted, p.surface),
        (f"{nombre}.muted/surface_alt", p.muted, p.surface_alt),
        (f"{nombre}.accent/surface", p.accent, p.surface),
    ]
    pares += [(f"{nombre}.{n}/surface", getattr(p, n), p.surface) for n in _SEMANTIC_NAMES]
    return pares


def _check_contrast(style: Style) -> CheckResult:
    bajos = []
    for nombre in ("screen", "print"):
        for etiqueta, fg, bg in _contrast_pairs(nombre, getattr(style.visual, nombre)):
            ratio = contrast_ratio(fg, bg)
            if ratio < AA_TEXT_RATIO:
                bajos.append(f"{etiqueta}={ratio:.2f}")
    if bajos:
        return CheckResult(
            status=checks.STATUS_WARN, code=CODE_STYLE_CONTRAST,
            message=f"contraste bajo AA ({AA_TEXT_RATIO}:1) en {len(bajos)} par(es) de colores",
            detail="; ".join(bajos),
        )
    return CheckResult(
        status=checks.STATUS_PASS, code=CODE_STYLE_CONTRAST,
        message=f"contraste >= {AA_TEXT_RATIO}:1 en ambos temas",
    )


def _check_palette(style: Style) -> CheckResult:
    problemas = []
    grupos = (
        ("screen.categorical", style.visual.screen.categorical),
        ("print.categorical", style.visual.print.categorical),
        ("chart.screen.colorway", style.visual.chart.screen.colorway),
        ("chart.print.colorway", style.visual.chart.print.colorway),
    )
    for nombre, colores in grupos:
        if len(colores) == 0:
            problemas.append(f"{nombre}: vacia")
        elif len({c.lower() for c in colores}) != len(colores):
            problemas.append(f"{nombre}: colores repetidos")
    if problemas:
        return CheckResult(
            status=checks.STATUS_WARN, code=CODE_STYLE_PALETTE,
            message="paleta categorica vacia o con colores repetidos",
            detail="; ".join(problemas),
        )
    return CheckResult(
        status=checks.STATUS_PASS, code=CODE_STYLE_PALETTE,
        message="paletas categoricas no vacias y sin repetidos",
    )


def check_style(style: Style) -> list:
    """`[CheckResult]` con STYLE-CONTRAST y STYLE-PALETTE (WARN o PASS). Nunca lanza."""
    resultados = []
    for codigo, fn in ((CODE_STYLE_CONTRAST, _check_contrast), (CODE_STYLE_PALETTE, _check_palette)):
        try:
            resultados.append(fn(style))
        except Exception:  # noqa: BLE001 -- "nunca frena"
            resultados.append(CheckResult(
                status=checks.STATUS_WARN, code=codigo,
                message="no se pudo evaluar el estilo (objeto invalido)",
            ))
    return resultados


# --- Formato por locale ---------------------------------------------------------


def _resolve_format(locale: Any) -> LocaleFormat:
    if isinstance(locale, LocaleFormat):
        return locale
    if isinstance(locale, Style):
        return locale.visual.locale_format
    if isinstance(locale, str) and locale in LOCALE_PRESETS:
        return _preset_format(locale)
    return _preset_format("en")


def _group_thousands(digitos: str, sep: str) -> str:
    if not sep or len(digitos) <= 3:
        return digitos
    partes = []
    while len(digitos) > 3:
        partes.insert(0, digitos[-3:])
        digitos = digitos[:-3]
    partes.insert(0, digitos)
    return sep.join(partes)


def _format_decimal(valor: Any, decimales: int, fmt: LocaleFormat, escala: float = 1) -> str:
    """Formatea un real finito con separadores; sin signo negativo para ceros redondeados."""
    if isinstance(valor, int) and escala == 1:
        entero, frac, negativo = str(abs(valor)), "0" * decimales, valor < 0
    else:
        v = float(valor) * escala
        texto = f"{abs(v):.{decimales}f}"
        entero, _, frac = texto.partition(".")
        negativo = v < 0
    if negativo and not (set(entero) <= {"0"} and set(frac) <= {"0"}):
        signo = "-"
    else:
        signo = ""
    salida = signo + _group_thousands(entero, fmt.thousands_sep)
    if decimales > 0:
        salida += fmt.decimal_sep + frac
    return salida


def _es_real(valor: Any) -> bool:
    if isinstance(valor, bool) or not isinstance(valor, numbers.Real):
        return False
    try:
        return math.isfinite(float(valor))
    except (TypeError, ValueError, OverflowError):
        return False


def format_number(value: Any, decimals: Optional[int] = None,
                  locale: Union[str, LocaleFormat, Style] = "en") -> str:
    """Numero con separadores del locale. `decimals=None`: 0 decimales si es entero, si no 2.
    `None` => ""; no numerico/no finito => `str(value)` (el llamador escapa). Nunca lanza."""
    try:
        if value is None:
            return ""
        if not _es_real(value):
            return str(value)
        fmt = _resolve_format(locale)
        if decimals is None or isinstance(decimals, bool) or not isinstance(decimals, int) or decimals < 0:
            integral = isinstance(value, int) or float(value).is_integer()
            decimals = 0 if integral else 2
        return _format_decimal(value, min(decimals, 12), fmt)
    except Exception:  # noqa: BLE001 -- puro: nunca lanza
        return str(value)


def format_percent(value: Any, decimals: Optional[int] = None,
                   locale: Union[str, LocaleFormat, Style] = "en") -> str:
    """Porcentaje a partir de una FRACCION (0.256 -> "25.6%"). `decimals=None` usa
    `percent_decimals` del locale. `None` => ""; no numerico => `str(value)`. Nunca lanza."""
    try:
        if value is None:
            return ""
        if not _es_real(value):
            return str(value)
        fmt = _resolve_format(locale)
        if decimals is None or isinstance(decimals, bool) or not isinstance(decimals, int) or decimals < 0:
            decimals = fmt.percent_decimals
        return _format_decimal(value, min(decimals, 12), fmt, escala=100) + "%"
    except Exception:  # noqa: BLE001
        return str(value)


def format_date(value: Any, locale: Union[str, LocaleFormat, Style] = "en") -> str:
    """Fecha segun `date_format` del locale. Acepta `date`, `datetime` o ISO 8601 (str).
    `None` => ""; no interpretable => `str(value)`. Sin `strftime` (determinista). Nunca lanza."""
    try:
        if value is None:
            return ""
        fmt = _resolve_format(locale)
        d: Any = None
        if isinstance(value, date):  # incluye datetime
            d = value
        elif isinstance(value, str):
            s = value.strip()
            try:
                d = datetime.fromisoformat(s)
            except ValueError:
                if len(s) >= 10 and (len(s) == 10 or s[10] in "T "):
                    try:
                        d = date.fromisoformat(s[:10])
                    except ValueError:
                        d = None
        if d is None:
            return str(value)
        piezas = {
            "Y": f"{d.year:04d}", "y": f"{d.year % 100:02d}", "m": f"{d.month:02d}",
            "d": f"{d.day:02d}", "H": f"{getattr(d, 'hour', 0):02d}",
            "M": f"{getattr(d, 'minute', 0):02d}",
        }
        return _DATE_TOKEN_RE.sub(lambda m: piezas[m.group(1)], fmt.date_format)
    except Exception:  # noqa: BLE001
        return str(value)

"""Contratos neutrales de reporting (v0.6, Change 0 `20260918-reporting-core`).

Módulo solo-stdlib: describe, en memoria, un reporte como árbol de objetos
inmutables (`Report` -> `Chapter` -> `TableArtifact` / `FigureArtifact` /
`Insight`). No conoce ninguna técnica, dominio ni backend gráfico: eso lo
aportan módulos posteriores de la familia (governance, evidencia, perfiles,
renderer), que pueden importar este módulo pero nunca al revés.

Política de validación: en construcción es estricta y SOLO estructural (enums,
ids, tipos, duplicados, forma de tabla, JSON-seguridad). La completitud
semántica/evidencial (figura sin tabla de respaldo, referencias que no
resuelven, columnas ausentes, claims vacíos, insight sin evidencia) NO se
valida acá: la hace la validación determinista de un Change posterior.

Todo error de contrato lanza `ReportingContractError`.

Serialización determinista: `to_dict()`/`from_dict()` por contrato,
`canonical_json()` y `Report.content_sha256()` (identidad de contenido; el
`Report` no lleva timestamps ni datos de ejecución).

Política de evolución del esquema: todo campo nuevo en el `to_dict()` de un
contrato cambia `content_sha256()` y por lo tanto REQUIERE bump de
`SCHEMA_VERSION`. `content_sha256()` es la identidad del objeto
re-serializado; como `from_dict` ignora claves desconocidas, el hash de los
bytes persistidos de un artefacto y el del objeto pueden diferir: quien
persista artefactos debe hashear además los BYTES persistidos. Tampoco vale
`==` como identidad de contenido (`True == 1 == 1.0` dentro de tuplas): la
identidad de contenido es el hash.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from typing import Any, Iterator, Optional

# ---------------------------------------------------------------------------
# Vocabularios y constantes
# ---------------------------------------------------------------------------

# El literal "eda" es solo un valor del vocabulario `report_kind`: el core no
# contiene lógica de EDA ni de ningún otro dominio.
REPORT_KINDS = ("eda", "model", "evaluation", "production")
DECISION_SCOPES = ("exploratory", "model_valid", "operational")
CLAIM_TYPES = (
    "descriptive",
    "comparative",
    "associative",
    "predictive",
    "causal",
    "recommendation",
)
CHART_TYPES = ("bar", "line", "scatter", "histogram", "box", "heatmap")
SEMANTIC_ROLES = ("risk", "status")
ORIENTATIONS = ("v", "h")

REPORT_FILENAME = "report.html"
MANIFEST_FILENAME = "manifest.json"
INSIGHTS_FILENAME = "insights.json"
ARTIFACTS_DIRNAME = "artifacts"

SCHEMA_VERSION = 1

# Ids seguros como nombre de archivo: `^[a-z0-9][a-z0-9_-]{0,63}$`. Se aplica con
# `fullmatch` (y no `$`) para que un salto de línea final no pase la validación.
_PATRON_ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")

# Nombres de dispositivo reservados en Windows: un id (ya en minúscula) que
# coincida no es seguro como nombre de archivo en ese sistema.
_IDS_RESERVADOS = frozenset(
    ["con", "prn", "aux", "nul"]
    + [f"com{i}" for i in range(1, 10)]
    + [f"lpt{i}" for i in range(1, 10)]
)

_ORDENES_SORT = ("ascending", "descending")
_PROFUNDIDAD_MAXIMA_ITEM = 5


class ReportingContractError(ValueError):
    """Violación de un contrato de reporting (entrada estructuralmente inválida)."""


# ---------------------------------------------------------------------------
# Helpers privados de validación / normalización
# ---------------------------------------------------------------------------


def _validar_id(valor: Any, campo: str) -> str:
    """Valida un id contra `_PATRON_ID`; devuelve el mismo valor."""
    if not isinstance(valor, str):
        raise ReportingContractError(f"{campo}: se esperaba str, se recibió {type(valor).__name__}")
    if _PATRON_ID.fullmatch(valor) is None:
        raise ReportingContractError(
            f"{campo}: id inválido {valor!r} (debe cumplir ^[a-z0-9][a-z0-9_-]{{0,63}}$)"
        )
    if valor in _IDS_RESERVADOS:
        raise ReportingContractError(
            f"{campo}: id {valor!r} es un nombre de dispositivo reservado de Windows "
            "(no es seguro como nombre de archivo)"
        )
    return valor


def _exigir_str(valor: Any, campo: str) -> str:
    """Exige `str`; devuelve el mismo valor."""
    if not isinstance(valor, str):
        raise ReportingContractError(f"{campo}: se esperaba str, se recibió {type(valor).__name__}")
    return valor


def _exigir_str_no_vacio(valor: Any, campo: str) -> str:
    """Exige `str` no vacío; devuelve el mismo valor."""
    _exigir_str(valor, campo)
    if valor == "":
        raise ReportingContractError(f"{campo}: no puede ser vacío")
    return valor


def _exigir_str_no_vacio_o_none(valor: Any, campo: str) -> Optional[str]:
    """Acepta `None` o un `str` no vacío."""
    if valor is None:
        return None
    return _exigir_str_no_vacio(valor, campo)


def _exigir_bool(valor: Any, campo: str) -> bool:
    """Exige `bool` estricto (no enteros)."""
    if not isinstance(valor, bool):
        raise ReportingContractError(f"{campo}: se esperaba bool, se recibió {type(valor).__name__}")
    return valor


def _exigir_secuencia(valor: Any, campo: str) -> tuple:
    """`list`/`tuple` -> `tuple`; cualquier otro tipo (incluido `str`) es error."""
    if not isinstance(valor, (list, tuple)):
        raise ReportingContractError(
            f"{campo}: se esperaba list o tuple, se recibió {type(valor).__name__}"
        )
    return tuple(valor)


def _exigir_dict(valor: Any, campo: str) -> dict:
    """Exige `dict`; devuelve el mismo objeto (sin copiar)."""
    if not isinstance(valor, dict):
        raise ReportingContractError(f"{campo}: se esperaba dict, se recibió {type(valor).__name__}")
    return valor


def _json_puro(valor: Any, ruta: str) -> Any:
    """Copia profunda de `valor` normalizada a estructura JSON pura: `tuple` ->
    `list`, claves `str`, `float` finito. Cualquier otro tipo es error."""
    if valor is None:
        return None
    if isinstance(valor, bool):
        return bool(valor)
    if isinstance(valor, str):
        return str(valor)
    if isinstance(valor, int):
        return int(valor)
    if isinstance(valor, float):
        if not math.isfinite(valor):
            raise ReportingContractError(f"{ruta}: float no finito ({valor!r}) no es JSON-seguro")
        return float(valor)
    if isinstance(valor, (list, tuple)):
        return [_json_puro(item, f"{ruta}[{i}]") for i, item in enumerate(valor)]
    if isinstance(valor, dict):
        resultado: dict = {}
        for clave, item in valor.items():
            if not isinstance(clave, str):
                raise ReportingContractError(
                    f"{ruta}: clave no-str {clave!r} ({type(clave).__name__}) no es JSON-seguro"
                )
            resultado[clave] = _json_puro(item, f"{ruta}.{clave}")
        return resultado
    raise ReportingContractError(f"{ruta}: tipo {type(valor).__name__} no es JSON-seguro")


def _dict_json_puro(valor: Any, campo: str) -> dict:
    """Exige `dict` y devuelve su copia profunda normalizada a JSON puro; una
    estructura circular o demasiado profunda es `ReportingContractError`."""
    try:
        return _json_puro(_exigir_dict(valor, campo), campo)
    except RecursionError as exc:
        raise ReportingContractError(
            f"{campo}: estructura circular o demasiado profunda"
        ) from exc


def _requeridos(datos: Any, nombres: tuple, contrato: str) -> None:
    """Exige que `datos` sea `dict` y contenga todas las claves de `nombres`."""
    if not isinstance(datos, dict):
        raise ReportingContractError(
            f"{contrato}.from_dict: se esperaba dict, se recibió {type(datos).__name__}"
        )
    faltantes = [n for n in nombres if n not in datos]
    if faltantes:
        raise ReportingContractError(f"{contrato}.from_dict: faltan campos requeridos {faltantes}")


def _seleccionar(datos: dict, nombres: tuple) -> dict:
    """Subconjunto de `datos` limitado a `nombres` (ignora claves desconocidas)."""
    return {n: datos[n] for n in nombres if n in datos}


def _validar_celda(celda: Any, ruta: str) -> Any:
    """Celda estricta del constructor directo: `str`/`int`/`bool`/`None`/`float` finito."""
    if celda is None:
        return None
    if isinstance(celda, bool):
        return bool(celda)
    if isinstance(celda, int):
        return int(celda)
    if isinstance(celda, str):
        return str(celda)
    if isinstance(celda, float):
        if not math.isfinite(celda):
            raise ReportingContractError(f"{ruta}: float no finito ({celda!r}) no permitido")
        return float(celda)
    raise ReportingContractError(f"{ruta}: tipo de celda no soportado {type(celda).__name__}")


def _coercionar_celda(celda: Any, ruta: str, profundidad: int = 0) -> Any:
    """Coerción de celdas de `TableArtifact.from_frame` (duck typing)."""
    if celda is None:
        return None
    if isinstance(celda, bool):
        return bool(celda)
    if isinstance(celda, int):
        return int(celda)
    if isinstance(celda, float):
        return float(celda) if math.isfinite(celda) else None
    if isinstance(celda, str):
        return str(celda)
    # Un valor distinto de sí mismo (NaN/NaT/NA de cualquier librería) es nulo.
    try:
        es_nulo = bool(celda != celda)
    except Exception:  # noqa: BLE001 -- si la comparación falla, flujo normal
        es_nulo = False
    if es_nulo:
        return None
    isoformat = getattr(celda, "isoformat", None)
    if callable(isoformat):
        texto = isoformat()
        if not isinstance(texto, str):
            raise ReportingContractError(f"{ruta}: isoformat() no devolvió str")
        return texto
    item = getattr(celda, "item", None)
    if callable(item):
        if profundidad >= _PROFUNDIDAD_MAXIMA_ITEM:
            raise ReportingContractError(f"{ruta}: item() anidado en exceso")
        return _coercionar_celda(item(), ruta, profundidad + 1)
    raise ReportingContractError(f"{ruta}: tipo de celda no coercionable {type(celda).__name__}")


def canonical_json(obj: Any) -> str:
    """JSON canónico: claves ordenadas, sin espacios, sin escapar no-ASCII,
    sin `NaN`/`Infinity`. Un fallo de serialización lanza `ReportingContractError`."""
    try:
        return json.dumps(
            obj,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError, RecursionError) as exc:
        raise ReportingContractError(f"canonical_json: objeto no serializable ({exc})") from exc


# ---------------------------------------------------------------------------
# TableArtifact
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TableArtifact:
    """Tabla de respaldo: columnas, filas JSON-seguras y metadatos de presentación."""

    table_id: str
    title: str
    columns: tuple
    rows: tuple
    units: dict = field(default_factory=dict)
    column_labels: dict = field(default_factory=dict)
    description: str = ""
    sensitive: bool = False

    def __post_init__(self) -> None:
        _validar_id(self.table_id, "table_id")
        _exigir_str(self.title, "TableArtifact.title")
        _exigir_str(self.description, "TableArtifact.description")
        _exigir_bool(self.sensitive, "TableArtifact.sensitive")

        columnas = _exigir_secuencia(self.columns, "TableArtifact.columns")
        if not columnas:
            raise ReportingContractError("TableArtifact.columns: no puede ser vacía")
        for i, col in enumerate(columnas):
            _exigir_str_no_vacio(col, f"TableArtifact.columns[{i}]")
        if len(set(columnas)) != len(columnas):
            raise ReportingContractError("TableArtifact.columns: contiene duplicados")

        filas_norm = []
        for i, fila in enumerate(_exigir_secuencia(self.rows, "TableArtifact.rows")):
            fila_t = _exigir_secuencia(fila, f"TableArtifact.rows[{i}]")
            if len(fila_t) != len(columnas):
                raise ReportingContractError(
                    f"TableArtifact.rows[{i}]: largo {len(fila_t)} distinto de "
                    f"len(columns)={len(columnas)}"
                )
            filas_norm.append(
                tuple(_validar_celda(c, f"TableArtifact.rows[{i}][{j}]") for j, c in enumerate(fila_t))
            )

        object.__setattr__(self, "columns", columnas)
        object.__setattr__(self, "rows", tuple(filas_norm))
        object.__setattr__(self, "units", self._mapa_de_columnas(self.units, columnas, "units"))
        object.__setattr__(
            self,
            "column_labels",
            self._mapa_de_columnas(self.column_labels, columnas, "column_labels"),
        )

    @staticmethod
    def _mapa_de_columnas(valor: Any, columnas: tuple, campo: str) -> dict:
        """Copia validada de un mapa columna -> texto (claves dentro de `columnas`)."""
        mapa = _exigir_dict(valor, f"TableArtifact.{campo}")
        resultado: dict = {}
        for clave, texto in mapa.items():
            if not isinstance(clave, str) or clave not in columnas:
                raise ReportingContractError(
                    f"TableArtifact.{campo}: clave {clave!r} no está en columns"
                )
            _exigir_str(texto, f"TableArtifact.{campo}[{clave!r}]")
            resultado[clave] = texto
        return resultado

    @classmethod
    def from_rows(
        cls,
        table_id: str,
        title: str,
        columns: Any,
        rows: Any,
        units: Optional[dict] = None,
        column_labels: Optional[dict] = None,
        description: str = "",
        sensitive: bool = False,
    ) -> "TableArtifact":
        """Construye desde filas `list`/`tuple`: `float` no finito -> `None`,
        `list` -> `tuple`. El resto de las reglas es el del constructor directo."""
        filas_norm = []
        for i, fila in enumerate(_exigir_secuencia(rows, "TableArtifact.rows")):
            fila_t = _exigir_secuencia(fila, f"TableArtifact.rows[{i}]")
            filas_norm.append(
                tuple(
                    None if isinstance(c, float) and not math.isfinite(c) else c for c in fila_t
                )
            )
        return cls(
            table_id=table_id,
            title=title,
            columns=columns,
            rows=tuple(filas_norm),
            units={} if units is None else units,
            column_labels={} if column_labels is None else column_labels,
            description=description,
            sensitive=sensitive,
        )

    @classmethod
    def from_frame(
        cls,
        frame: Any,
        table_id: str,
        title: str,
        units: Optional[dict] = None,
        column_labels: Optional[dict] = None,
        description: str = "",
        sensitive: bool = False,
    ) -> "TableArtifact":
        """Construye desde un objeto tabular por duck typing (sin
        importar ninguna librería): lee `frame.columns` y obtiene las filas con
        `frame.astype(object).values.tolist()` si `frame` tiene `astype` (así los
        enteros no se promueven a `float`); si no, cae a `frame.values.tolist()`,
        que en frames de tipos mixtos puede promover enteros a `float` (en ese
        caso conviene `from_rows`). Coerción de celdas: `None`->`None`,
        `bool`->`bool`, `int`->`int`, `float` finito->`float` (si no, `None`),
        `str`->`str`, objeto con `isoformat()`->`str` ISO, objeto con `item()`
        (escalar) -> recursión sobre `.item()`, cualquier otro tipo -> error."""
        try:
            columnas = tuple(frame.columns)
            if hasattr(frame, "astype"):
                filas_crudas = frame.astype(object).values.tolist()
            else:
                filas_crudas = frame.values.tolist()
            filas = tuple(
                tuple(
                    _coercionar_celda(c, f"from_frame.rows[{i}][{j}]")
                    for j, c in enumerate(_exigir_secuencia(fila, f"from_frame.rows[{i}]"))
                )
                for i, fila in enumerate(_exigir_secuencia(filas_crudas, "from_frame.rows"))
            )
        except (AttributeError, TypeError, ValueError) as exc:
            # `ReportingContractError` es ValueError: se re-lanza tal cual.
            if isinstance(exc, ReportingContractError):
                raise
            raise ReportingContractError(f"from_frame: objeto tabular inválido ({exc})") from exc
        return cls(
            table_id=table_id,
            title=title,
            columns=columnas,
            rows=filas,
            units={} if units is None else units,
            column_labels={} if column_labels is None else column_labels,
            description=description,
            sensitive=sensitive,
        )

    def to_dict(self) -> dict:
        return {
            "table_id": self.table_id,
            "title": self.title,
            "columns": list(self.columns),
            "rows": [list(fila) for fila in self.rows],
            "units": dict(self.units),
            "column_labels": dict(self.column_labels),
            "description": self.description,
            "sensitive": self.sensitive,
        }

    @classmethod
    def from_dict(cls, datos: dict) -> "TableArtifact":
        _requeridos(datos, ("table_id", "title", "columns", "rows"), "TableArtifact")
        return cls(
            **_seleccionar(
                datos,
                (
                    "table_id",
                    "title",
                    "columns",
                    "rows",
                    "units",
                    "column_labels",
                    "description",
                    "sensitive",
                ),
            )
        )


# ---------------------------------------------------------------------------
# FigureSpec / FigureArtifact
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FigureSpec:
    """Especificación declarativa neutral de un gráfico (referencia columnas de
    la tabla de respaldo; no lleva datos ni backend)."""

    chart_type: str
    x: str
    y: tuple = ()
    color: Optional[str] = None
    z: Optional[str] = None
    orientation: str = "v"
    top_n: Optional[int] = None
    sort: Optional[str] = None
    x_label: str = ""
    y_label: str = ""
    unit: str = ""
    denominator: Optional[str] = None
    semantic: Optional[str] = None

    def __post_init__(self) -> None:
        if self.chart_type not in CHART_TYPES:
            raise ReportingContractError(
                f"FigureSpec.chart_type: {self.chart_type!r} fuera de {CHART_TYPES}"
            )
        _exigir_str_no_vacio(self.x, "FigureSpec.x")
        ys = _exigir_secuencia(self.y, "FigureSpec.y")
        for i, col in enumerate(ys):
            _exigir_str_no_vacio(col, f"FigureSpec.y[{i}]")
        if not ys and self.chart_type != "histogram":
            raise ReportingContractError("FigureSpec.y: requiere al menos un elemento salvo en histogram")
        _exigir_str_no_vacio_o_none(self.color, "FigureSpec.color")
        _exigir_str_no_vacio_o_none(self.z, "FigureSpec.z")
        if self.chart_type == "heatmap" and self.z is None:
            raise ReportingContractError("FigureSpec.z: heatmap requiere z")
        if self.orientation not in ORIENTATIONS:
            raise ReportingContractError(
                f"FigureSpec.orientation: {self.orientation!r} fuera de {ORIENTATIONS}"
            )
        if self.top_n is not None:
            if isinstance(self.top_n, bool) or not isinstance(self.top_n, int) or self.top_n <= 0:
                raise ReportingContractError(
                    f"FigureSpec.top_n: se esperaba int > 0 o None, se recibió {self.top_n!r}"
                )
        if self.sort is not None and self.sort not in _ORDENES_SORT:
            raise ReportingContractError(f"FigureSpec.sort: {self.sort!r} fuera de {_ORDENES_SORT}")
        _exigir_str(self.x_label, "FigureSpec.x_label")
        _exigir_str(self.y_label, "FigureSpec.y_label")
        _exigir_str(self.unit, "FigureSpec.unit")
        _exigir_str_no_vacio_o_none(self.denominator, "FigureSpec.denominator")
        if self.semantic is not None and self.semantic not in SEMANTIC_ROLES:
            raise ReportingContractError(
                f"FigureSpec.semantic: {self.semantic!r} fuera de {SEMANTIC_ROLES}"
            )
        object.__setattr__(self, "y", ys)

    def columns_used(self) -> tuple:
        """Columnas referenciadas (`x`, `y`, `color`, `z`, `denominator`): sin
        `None`, sin duplicados, ordenadas."""
        candidatas = [self.x, *self.y, self.color, self.z, self.denominator]
        return tuple(sorted({c for c in candidatas if c is not None}))

    def to_dict(self) -> dict:
        return {
            "chart_type": self.chart_type,
            "x": self.x,
            "y": list(self.y),
            "color": self.color,
            "z": self.z,
            "orientation": self.orientation,
            "top_n": self.top_n,
            "sort": self.sort,
            "x_label": self.x_label,
            "y_label": self.y_label,
            "unit": self.unit,
            "denominator": self.denominator,
            "semantic": self.semantic,
        }

    @classmethod
    def from_dict(cls, datos: dict) -> "FigureSpec":
        _requeridos(datos, ("chart_type", "x"), "FigureSpec")
        return cls(
            **_seleccionar(
                datos,
                (
                    "chart_type",
                    "x",
                    "y",
                    "color",
                    "z",
                    "orientation",
                    "top_n",
                    "sort",
                    "x_label",
                    "y_label",
                    "unit",
                    "denominator",
                    "semantic",
                ),
            )
        )


@dataclass(frozen=True)
class FigureArtifact:
    """Figura: spec declarativa + referencia a su tabla de respaldo. `backend` y
    `backend_payload` son un escape hatch opaco (ambos o ninguno) que el core
    guarda sin interpretar."""

    figure_id: str
    title: str
    spec: FigureSpec
    backing_table_id: Optional[str] = None
    description: str = ""
    alt_text: str = ""
    sensitive: bool = False
    backend: Optional[str] = None
    backend_payload: Optional[dict] = None

    def __post_init__(self) -> None:
        _validar_id(self.figure_id, "figure_id")
        _exigir_str(self.title, "FigureArtifact.title")
        if not isinstance(self.spec, FigureSpec):
            raise ReportingContractError(
                f"FigureArtifact.spec: se esperaba FigureSpec, se recibió {type(self.spec).__name__}"
            )
        if self.backing_table_id is not None:
            _validar_id(self.backing_table_id, "backing_table_id")
        _exigir_str(self.description, "FigureArtifact.description")
        _exigir_str(self.alt_text, "FigureArtifact.alt_text")
        _exigir_bool(self.sensitive, "FigureArtifact.sensitive")
        if self.backend is not None:
            _exigir_str_no_vacio(self.backend, "FigureArtifact.backend")
        if (self.backend is None) != (self.backend_payload is None):
            raise ReportingContractError(
                "FigureArtifact: backend y backend_payload deben estar ambos presentes o ambos ausentes"
            )
        if self.backend_payload is not None:
            object.__setattr__(
                self,
                "backend_payload",
                _dict_json_puro(self.backend_payload, "FigureArtifact.backend_payload"),
            )

    def to_dict(self) -> dict:
        return {
            "figure_id": self.figure_id,
            "title": self.title,
            "spec": self.spec.to_dict(),
            "backing_table_id": self.backing_table_id,
            "description": self.description,
            "alt_text": self.alt_text,
            "sensitive": self.sensitive,
            "backend": self.backend,
            "backend_payload": (
                None
                if self.backend_payload is None
                else _json_puro(self.backend_payload, "backend_payload")
            ),
        }

    @classmethod
    def from_dict(cls, datos: dict) -> "FigureArtifact":
        _requeridos(datos, ("figure_id", "title", "spec"), "FigureArtifact")
        kwargs = _seleccionar(
            datos,
            (
                "figure_id",
                "title",
                "backing_table_id",
                "description",
                "alt_text",
                "sensitive",
                "backend",
                "backend_payload",
            ),
        )
        kwargs["spec"] = FigureSpec.from_dict(datos["spec"])
        return cls(**kwargs)


# ---------------------------------------------------------------------------
# Insight
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Insight:
    """Hallazgo: separa la afirmación técnica de la de negocio y modela su
    evidencia (`evidence_refs` son ids de tablas/figuras del `Report`)."""

    insight_id: str
    technical_claim: str
    business_claim: str
    evidence_refs: tuple
    population: str
    time_scope: str
    claim_type: str
    uncertainty: str = ""
    title: str = ""

    def __post_init__(self) -> None:
        _validar_id(self.insight_id, "insight_id")
        _exigir_str(self.technical_claim, "Insight.technical_claim")
        _exigir_str(self.business_claim, "Insight.business_claim")
        refs = _exigir_secuencia(self.evidence_refs, "Insight.evidence_refs")
        for i, ref in enumerate(refs):
            _validar_id(ref, f"Insight.evidence_refs[{i}]")
        _exigir_str(self.population, "Insight.population")
        _exigir_str(self.time_scope, "Insight.time_scope")
        if self.claim_type not in CLAIM_TYPES:
            raise ReportingContractError(
                f"Insight.claim_type: {self.claim_type!r} fuera de {CLAIM_TYPES}"
            )
        _exigir_str(self.uncertainty, "Insight.uncertainty")
        _exigir_str(self.title, "Insight.title")
        object.__setattr__(self, "evidence_refs", refs)

    def to_dict(self) -> dict:
        return {
            "insight_id": self.insight_id,
            "technical_claim": self.technical_claim,
            "business_claim": self.business_claim,
            "evidence_refs": list(self.evidence_refs),
            "population": self.population,
            "time_scope": self.time_scope,
            "claim_type": self.claim_type,
            "uncertainty": self.uncertainty,
            "title": self.title,
        }

    @classmethod
    def from_dict(cls, datos: dict) -> "Insight":
        _requeridos(
            datos,
            (
                "insight_id",
                "technical_claim",
                "business_claim",
                "evidence_refs",
                "population",
                "time_scope",
                "claim_type",
            ),
            "Insight",
        )
        return cls(
            **_seleccionar(
                datos,
                (
                    "insight_id",
                    "technical_claim",
                    "business_claim",
                    "evidence_refs",
                    "population",
                    "time_scope",
                    "claim_type",
                    "uncertainty",
                    "title",
                ),
            )
        )


# ---------------------------------------------------------------------------
# Chapter
# ---------------------------------------------------------------------------


def _tupla_de_tipo(valor: Any, tipo: type, campo: str) -> tuple:
    """`list`/`tuple` cuyos elementos son todos instancias de `tipo`, como `tuple`."""
    elementos = _exigir_secuencia(valor, campo)
    for i, elemento in enumerate(elementos):
        if not isinstance(elemento, tipo):
            raise ReportingContractError(
                f"{campo}[{i}]: se esperaba {tipo.__name__}, se recibió {type(elemento).__name__}"
            )
    return elementos


@dataclass(frozen=True)
class Chapter:
    """Capítulo: agrupa tablas, figuras e insights. `metadata` es genérico."""

    chapter_id: str
    title: str
    summary: str = ""
    tables: tuple = ()
    figures: tuple = ()
    insights: tuple = ()
    method_note: str = ""
    metadata: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validar_id(self.chapter_id, "chapter_id")
        _exigir_str(self.title, "Chapter.title")
        _exigir_str(self.summary, "Chapter.summary")
        _exigir_str(self.method_note, "Chapter.method_note")
        tablas = _tupla_de_tipo(self.tables, TableArtifact, "Chapter.tables")
        figuras = _tupla_de_tipo(self.figures, FigureArtifact, "Chapter.figures")
        insights = _tupla_de_tipo(self.insights, Insight, "Chapter.insights")
        metadata = _dict_json_puro(self.metadata, "Chapter.metadata")
        object.__setattr__(self, "tables", tablas)
        object.__setattr__(self, "figures", figuras)
        object.__setattr__(self, "insights", insights)
        object.__setattr__(self, "metadata", metadata)

    def to_dict(self) -> dict:
        return {
            "chapter_id": self.chapter_id,
            "title": self.title,
            "summary": self.summary,
            "tables": [t.to_dict() for t in self.tables],
            "figures": [f.to_dict() for f in self.figures],
            "insights": [i.to_dict() for i in self.insights],
            "method_note": self.method_note,
            "metadata": _json_puro(self.metadata, "Chapter.metadata"),
        }

    @classmethod
    def from_dict(cls, datos: dict) -> "Chapter":
        _requeridos(datos, ("chapter_id", "title"), "Chapter")
        kwargs = _seleccionar(datos, ("chapter_id", "title", "summary", "method_note", "metadata"))
        for clave, contrato in (
            ("tables", TableArtifact),
            ("figures", FigureArtifact),
            ("insights", Insight),
        ):
            if clave in datos:
                kwargs[clave] = tuple(
                    contrato.from_dict(item)
                    for item in _exigir_secuencia(datos[clave], f"Chapter.from_dict.{clave}")
                )
        return cls(**kwargs)


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Report:
    """Raíz del árbol. `report_kind` y `decision_scope` son ortogonales: cada
    uno se valida solo contra su vocabulario (cualquier restricción entre ellos
    es política de governance, no del core). Sin `generated_at` ni datos de
    ejecución: `content_sha256()` identifica contenido, no una corrida."""

    report_id: str
    title: str
    report_kind: str
    decision_scope: str
    chapters: tuple = ()
    summary: str = ""
    conclusion: str = ""
    metadata: dict = field(default_factory=dict)
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _validar_id(self.report_id, "report_id")
        _exigir_str(self.title, "Report.title")
        if self.report_kind not in REPORT_KINDS:
            raise ReportingContractError(
                f"Report.report_kind: {self.report_kind!r} fuera de {REPORT_KINDS}"
            )
        if self.decision_scope not in DECISION_SCOPES:
            raise ReportingContractError(
                f"Report.decision_scope: {self.decision_scope!r} fuera de {DECISION_SCOPES}"
            )
        _exigir_str(self.summary, "Report.summary")
        _exigir_str(self.conclusion, "Report.conclusion")
        if (
            isinstance(self.schema_version, bool)
            or not isinstance(self.schema_version, int)
            or self.schema_version != SCHEMA_VERSION
        ):
            raise ReportingContractError(
                f"Report.schema_version: se esperaba {SCHEMA_VERSION}, se recibió {self.schema_version!r}"
            )
        capitulos = _tupla_de_tipo(self.chapters, Chapter, "Report.chapters")
        metadata = _dict_json_puro(self.metadata, "Report.metadata")

        # Unicidad: capítulos; tablas y figuras comparten un namespace; insights aparte.
        ids_capitulo: set = set()
        ids_artefacto: set = set()
        ids_insight: set = set()
        for capitulo in capitulos:
            if capitulo.chapter_id in ids_capitulo:
                raise ReportingContractError(f"chapter_id duplicado: {capitulo.chapter_id!r}")
            ids_capitulo.add(capitulo.chapter_id)
            for tabla in capitulo.tables:
                if tabla.table_id in ids_artefacto:
                    raise ReportingContractError(
                        f"id de artefacto duplicado (tablas y figuras comparten namespace): "
                        f"{tabla.table_id!r}"
                    )
                ids_artefacto.add(tabla.table_id)
            for figura in capitulo.figures:
                if figura.figure_id in ids_artefacto:
                    raise ReportingContractError(
                        f"id de artefacto duplicado (tablas y figuras comparten namespace): "
                        f"{figura.figure_id!r}"
                    )
                ids_artefacto.add(figura.figure_id)
            for insight in capitulo.insights:
                if insight.insight_id in ids_insight:
                    raise ReportingContractError(f"insight_id duplicado: {insight.insight_id!r}")
                ids_insight.add(insight.insight_id)

        object.__setattr__(self, "chapters", capitulos)
        object.__setattr__(self, "metadata", metadata)

    # -- accesores ---------------------------------------------------------

    def iter_tables(self) -> Iterator[TableArtifact]:
        """Tablas en orden de capítulos y luego de declaración."""
        for capitulo in self.chapters:
            yield from capitulo.tables

    def iter_figures(self) -> Iterator[FigureArtifact]:
        """Figuras en orden de capítulos y luego de declaración."""
        for capitulo in self.chapters:
            yield from capitulo.figures

    def iter_insights(self) -> Iterator[Insight]:
        """Insights en orden de capítulos y luego de declaración."""
        for capitulo in self.chapters:
            yield from capitulo.insights

    def get_table(self, table_id: Any) -> Optional[TableArtifact]:
        for tabla in self.iter_tables():
            if tabla.table_id == table_id:
                return tabla
        return None

    def get_figure(self, figure_id: Any) -> Optional[FigureArtifact]:
        for figura in self.iter_figures():
            if figura.figure_id == figure_id:
                return figura
        return None

    def get_artifact(self, artifact_id: Any) -> Optional[Any]:
        """Tabla o figura con ese id (namespace único); `None` si no existe."""
        tabla = self.get_table(artifact_id)
        if tabla is not None:
            return tabla
        return self.get_figure(artifact_id)

    # -- serialización -----------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "report_id": self.report_id,
            "title": self.title,
            "report_kind": self.report_kind,
            "decision_scope": self.decision_scope,
            "chapters": [c.to_dict() for c in self.chapters],
            "summary": self.summary,
            "conclusion": self.conclusion,
            "metadata": _json_puro(self.metadata, "Report.metadata"),
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, datos: dict) -> "Report":
        _requeridos(
            datos,
            ("report_id", "title", "report_kind", "decision_scope", "schema_version"),
            "Report",
        )
        version = datos["schema_version"]
        if isinstance(version, bool) or not isinstance(version, int) or version != SCHEMA_VERSION:
            raise ReportingContractError(
                f"Report.from_dict: schema_version {version!r} no soportado (se espera {SCHEMA_VERSION})"
            )
        kwargs = _seleccionar(
            datos,
            (
                "report_id",
                "title",
                "report_kind",
                "decision_scope",
                "summary",
                "conclusion",
                "metadata",
                "schema_version",
            ),
        )
        if "chapters" in datos:
            kwargs["chapters"] = tuple(
                Chapter.from_dict(item)
                for item in _exigir_secuencia(datos["chapters"], "Report.from_dict.chapters")
            )
        return cls(**kwargs)

    def content_sha256(self) -> str:
        """sha256 (hex) del JSON canónico de `to_dict()` en UTF-8."""
        return hashlib.sha256(canonical_json(self.to_dict()).encode("utf-8")).hexdigest()

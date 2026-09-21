"""Profile EDA (v0.6 Change 2, `20260918-eda-profile`).

Se monta sobre los contratos neutrales de `reporting.core` sin modificarlos: la
declaración de aplicabilidad viaja en `Report.metadata["eda"]` y cada capítulo
de un bloque lleva `Chapter.metadata["eda_block"]`.

Principio rector: el binario verifica ESTRUCTURA y aplicabilidad explícita; el
metodólogo y el reviewer evalúan adecuación. Ausencia de evaluación no es PASS.
Ninguna técnica se hardcodea: las familias del catálogo son solo strings
informativos y no se validan contra los capítulos.

Solo-lectura, determinista y sin red. Solo importa stdlib, `reporting.core` y
`dsguard.checks`. Los constructores (`BlockEvaluation`, `derive_evaluations`,
`coverage_table`, `build_eda_report`) lanzan `ReportingContractError` ante
contrato inválido; `validate_eda_report` NUNCA lanza.

Límites declarados (no garantías): el binario solo filtra lo obviamente vacío;
`applicable => >= 1 Insight` es gameable (deuda declarada); un PASS no equivale
a un EDA metodológicamente correcto.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

_TOOLS_DIR = Path(__file__).resolve().parents[2]
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from dsguard import checks  # noqa: E402

from .. import core  # noqa: E402

ReportingContractError = core.ReportingContractError

# --- Constantes -----------------------------------------------------------------

PROFILE_NAME = "eda"
PROFILE_VERSION = 1
STATES = ("applicable", "not_applicable", "omitted")
EXTENSION_PREFIX = "x_"

COVERAGE_CHAPTER_ID = "analysis_coverage"
COVERAGE_TABLE_ID = "eda_coverage"
COVERAGE_COLUMNS = ("block", "state", "reason", "limitations")

_SCOPES_ESTRICTOS = ("model_valid", "operational")
_MIN_PALABRAS_RAZON = 5
_MIN_LARGO_PALABRA = 3
_MIN_PALABRAS_DISTINTAS = 3
_DUPLICADOS_MINIMOS = 3
# Redundante por diseño (defensa en profundidad): todas estas razones tienen < 5 palabras
# significativas y ya las rechaza el umbral de palabras. Se conserva como red de seguridad
# explícita por si el umbral se relaja en el futuro (spec R11).
_RAZONES_TRIVIALES = frozenset({"na", "n a", "todo", "tbd", "none", "no aplica"})

_RAZON_SIN_TARGET = "estructuralmente no aplicable: sin target declarado"
_RAZON_SIN_TIEMPO = "estructuralmente no aplicable: sin columna temporal declarada"

CODE_PROFILE = "EDA-PROFILE"
CODE_APPLICABILITY_MISSING = "EDA-APPLICABILITY-MISSING"
CODE_BLOCK_UNEVALUATED = "EDA-BLOCK-UNEVALUATED"
CODE_BLOCK_UNKNOWN = "EDA-BLOCK-UNKNOWN"
CODE_BLOCK_STATE = "EDA-BLOCK-STATE"
CODE_BLOCK_REASON = "EDA-BLOCK-REASON"
CODE_REASON_DUPLICATED = "EDA-REASON-DUPLICATED"
CODE_AUTO_INVALID = "EDA-AUTO-INVALID"
CODE_BLOCK_NO_CHAPTER = "EDA-BLOCK-NO-CHAPTER"
CODE_BLOCK_NO_INSIGHT = "EDA-BLOCK-NO-INSIGHT"
CODE_BLOCK_CONTRADICTION = "EDA-BLOCK-CONTRADICTION"
CODE_CHAPTER_BLOCK_UNKNOWN = "EDA-CHAPTER-BLOCK-UNKNOWN"
CODE_TARGET_DECLARED = "EDA-TARGET-DECLARED"
CODE_TIME_DECLARED = "EDA-TIME-DECLARED"
CODE_OMITTED_SCOPE = "EDA-OMITTED-SCOPE"
CODE_LEAKAGE_REVIEW_REQUIRED = "EDA-LEAKAGE-REVIEW-REQUIRED"
CODE_EXPLORATORY_TARGET_USE = "EDA-EXPLORATORY-TARGET-USE"
CODE_COVERAGE_TABLE = "EDA-COVERAGE-TABLE"
CODE_NA_CONTRADICTS_DECLARATION = "EDA-NA-CONTRADICTS-DECLARATION"
CODE_EXTENSION_SHADOWS_CATALOG = "EDA-EXTENSION-SHADOWS-CATALOG"

CODES = (
    CODE_PROFILE,
    CODE_APPLICABILITY_MISSING,
    CODE_BLOCK_UNEVALUATED,
    CODE_BLOCK_UNKNOWN,
    CODE_BLOCK_STATE,
    CODE_BLOCK_REASON,
    CODE_REASON_DUPLICATED,
    CODE_AUTO_INVALID,
    CODE_BLOCK_NO_CHAPTER,
    CODE_BLOCK_NO_INSIGHT,
    CODE_BLOCK_CONTRADICTION,
    CODE_CHAPTER_BLOCK_UNKNOWN,
    CODE_TARGET_DECLARED,
    CODE_TIME_DECLARED,
    CODE_OMITTED_SCOPE,
    CODE_LEAKAGE_REVIEW_REQUIRED,
    CODE_EXPLORATORY_TARGET_USE,
    CODE_COVERAGE_TABLE,
    CODE_NA_CONTRADICTS_DECLARATION,
    CODE_EXTENSION_SHADOWS_CATALOG,
)

# --- Catálogo ------------------------------------------------------------------


@dataclass(frozen=True)
class BlockInfo:
    """Bloque del catálogo. `families` es solo informativo (no se valida)."""

    block_id: str
    question: str
    families: tuple
    requires_target: bool = False
    requires_time: bool = False


BLOCK_CATALOG = (
    BlockInfo(
        "data_quality",
        "¿Los datos son utilizables tal como están: completos, sin duplicados y válidos?",
        ("missingness", "duplicates_and_keys", "type_and_domain_validity", "outlier_screening"),
    ),
    BlockInfo(
        "univariate",
        "¿Cómo se comporta cada variable por separado?",
        ("distribution_summary", "dispersion_and_shape", "categorical_frequency"),
    ),
    BlockInfo(
        "bivariate_target",
        "¿Cómo se relacionan las variables con el target declarado?",
        ("association_measure", "group_contrast", "rate_by_group"),
        requires_target=True,
    ),
    BlockInfo(
        "multivariate",
        "¿Qué estructura conjunta tienen las variables?",
        ("correlation_structure", "dimensionality_reduction", "interaction_screening"),
    ),
    BlockInfo(
        "temporal",
        "¿Cómo evoluciona el fenómeno en el tiempo?",
        ("trend", "seasonality_or_periodicity", "regime_change", "cohort_like"),
        requires_time=True,
    ),
    BlockInfo(
        "concentration",
        "¿El fenómeno se concentra en pocas unidades o categorías?",
        ("top_share", "inequality_index", "long_tail"),
    ),
    BlockInfo(
        "segmentation",
        "¿Existen grupos de unidades con perfiles distintos?",
        ("unsupervised_grouping", "rule_based_segments", "profile_contrast"),
    ),
    BlockInfo(
        "entity_relations",
        "¿Cómo se relacionan las entidades entre sí?",
        ("cardinality_and_keys", "join_integrity", "graph_structure"),
    ),
    BlockInfo(
        "process_cycles",
        "¿Qué ciclos, duraciones y transiciones tiene el proceso observado?",
        ("duration_and_latency", "state_transitions", "stage_flow"),
    ),
    BlockInfo(
        "leakage_review",
        "¿Alguna variable usa información posterior al momento de decisión?",
        (
            "temporal_availability",
            "post_outcome_fields",
            "snapshot_vs_event",
            "target_proxy_screening",
        ),
    ),
    BlockInfo(
        "population_and_unit",
        "¿Cuál es la unidad de análisis y qué población cubre el análisis?",
        (
            "unit_of_analysis",
            "inclusion_exclusion",
            "denominator_definition",
            "coverage_over_time",
        ),
    ),
)

_INFO_POR_ID = {info.block_id: info for info in BLOCK_CATALOG}
_INDICE_CATALOGO = {info.block_id: i for i, info in enumerate(BLOCK_CATALOG)}


def _normalizar_id(texto: str) -> str:
    """casefold y `-`/`_` equivalentes (para detectar extensiones que sombrean el catálogo)."""
    return texto.casefold().replace("-", "_")


_IDS_CATALOGO_NORMALIZADOS = frozenset(_normalizar_id(b) for b in _INFO_POR_ID)


# --- BlockEvaluation ------------------------------------------------------------


@dataclass(frozen=True)
class BlockEvaluation:
    """Evaluación declarada de un bloque. En construcción solo se exigen tipos:
    un estado fuera de `STATES` o un bloque desconocido los reporta el validador."""

    block: str
    state: str
    reason: str = ""
    limitations: str = ""
    auto: bool = False

    def __post_init__(self) -> None:
        for campo in ("block", "state", "reason", "limitations"):
            valor = getattr(self, campo)
            if not isinstance(valor, str):
                raise ReportingContractError(
                    f"BlockEvaluation.{campo}: se esperaba str, se recibió {type(valor).__name__}"
                )
        if self.block == "":
            raise ReportingContractError("BlockEvaluation.block: no puede ser vacío")
        if not isinstance(self.auto, bool):
            raise ReportingContractError(
                f"BlockEvaluation.auto: se esperaba bool, se recibió {type(self.auto).__name__}"
            )


# --- Helpers privados ------------------------------------------------------------


def _declarado(valor: Any) -> bool:
    return isinstance(valor, str) and valor.strip() != ""


def _politica_tiene_fecha(politica: Any) -> bool:
    """`True` sii `politica["temporal"]["date_column"]` es un str no vacío. Nunca lanza."""
    try:
        if isinstance(politica, dict):
            temporal = politica.get("temporal")
            if isinstance(temporal, dict):
                return _declarado(temporal.get("date_column"))
    except Exception:  # noqa: BLE001 -- política corrupta = sin columna temporal
        pass
    return False


def _clave_orden(bloque: Any) -> tuple:
    """Orden: catálogo, luego el resto ordenado por id."""
    if isinstance(bloque, str) and bloque in _INDICE_CATALOGO:
        return (0, _INDICE_CATALOGO[bloque], "")
    return (1, 0, bloque if isinstance(bloque, str) else repr(bloque))


def _es_conocido(bloque: Any) -> bool:
    return isinstance(bloque, str) and (
        bloque in _INFO_POR_ID
        or (bloque.startswith(EXTENSION_PREFIX) and len(bloque) > len(EXTENSION_PREFIX))
    )


def _texto(valor: Any) -> str:
    return valor if isinstance(valor, str) else ""


def _subject(valor: Any) -> str:
    return valor if isinstance(valor, str) else repr(valor)


def _normalizar_razon(texto: Any) -> str:
    """strip, colapsar espacios, casefold y quitar puntuación (-> espacio)."""
    if not isinstance(texto, str):
        return ""
    limpio = "".join(c if (c.isalnum() or c.isspace()) else " " for c in texto.casefold())
    return " ".join(limpio.split())


def _razon_insuficiente(texto: Any) -> bool:
    normalizada = _normalizar_razon(texto)
    if normalizada == "" or normalizada in _RAZONES_TRIVIALES:
        return True
    palabras = [p for p in normalizada.split() if len(p) >= _MIN_LARGO_PALABRA]
    return len(palabras) < _MIN_PALABRAS_RAZON or len(set(palabras)) < _MIN_PALABRAS_DISTINTAS


def _exigir_secuencia(valor: Any, campo: str) -> tuple:
    if not isinstance(valor, (list, tuple)):
        raise ReportingContractError(
            f"{campo}: se esperaba list o tuple, se recibió {type(valor).__name__}"
        )
    return tuple(valor)


# --- Autoderivación --------------------------------------------------------------


def derive_evaluations(
    target: Optional[str],
    time_column: Optional[str],
    evaluations: Any,
    *,
    scientific_policy: Optional[dict] = None,
) -> tuple:
    """Devuelve la tupla completa de evaluaciones (orden: catálogo, luego el resto).

    Autoderiva `not_applicable` con `auto=True` los bloques `requires_target` sin
    target y `requires_time` sin columna temporal (ni `temporal.date_column` en la
    política), pisando lo que haya declarado el usuario. No completa bloques del
    catálogo sin evaluación. Una evaluación `auto=True` recibida con la
    precondición cumplida se conserva para que el validador la rechace.
    """
    por_bloque: dict = {}
    for i, evaluacion in enumerate(_exigir_secuencia(evaluations, "evaluations")):
        if not isinstance(evaluacion, BlockEvaluation):
            raise ReportingContractError(
                f"evaluations[{i}]: se esperaba BlockEvaluation, se recibió "
                f"{type(evaluacion).__name__}"
            )
        if evaluacion.block in por_bloque:
            raise ReportingContractError(f"evaluations: bloque duplicado {evaluacion.block!r}")
        por_bloque[evaluacion.block] = evaluacion

    tiene_target = _declarado(target)
    tiene_tiempo = _declarado(time_column) or _politica_tiene_fecha(scientific_policy)
    for info in BLOCK_CATALOG:
        motivo = None
        if info.requires_target and not tiene_target:
            motivo = _RAZON_SIN_TARGET
        elif info.requires_time and not tiene_tiempo:
            motivo = _RAZON_SIN_TIEMPO
        if motivo is not None:
            previa = por_bloque.get(info.block_id)
            if previa is not None and previa.state not in ("not_applicable", "omitted"):
                # Declarado `applicable` (o con estado inválido) sin precondición: se
                # conserva para que el validador emita EDA-TARGET/TIME-DECLARED o
                # EDA-BLOCK-STATE en vez de degradarlo en silencio.
                continue
            limitaciones = previa.limitations if previa is not None else ""
            por_bloque[info.block_id] = BlockEvaluation(
                info.block_id, "not_applicable", motivo, limitaciones, True
            )
    return tuple(por_bloque[b] for b in sorted(por_bloque, key=_clave_orden))


# --- Tabla y capítulo de cobertura --------------------------------------------------


def coverage_table(evaluations: Any, decision_scope: str) -> core.TableArtifact:
    """Tabla `eda_coverage`: una fila por bloque evaluado, sin score ni agregados."""
    if decision_scope not in core.DECISION_SCOPES:
        raise ReportingContractError(
            f"decision_scope: {decision_scope!r} fuera de {core.DECISION_SCOPES}"
        )
    evaluaciones = _exigir_secuencia(evaluations, "evaluations")
    for i, evaluacion in enumerate(evaluaciones):
        if not isinstance(evaluacion, BlockEvaluation):
            raise ReportingContractError(
                f"evaluations[{i}]: se esperaba BlockEvaluation, se recibió "
                f"{type(evaluacion).__name__}"
            )
    ordenadas = sorted(evaluaciones, key=lambda e: _clave_orden(e.block))
    filas = tuple((e.block, e.state, e.reason, e.limitations) for e in ordenadas)
    return core.TableArtifact(
        table_id=COVERAGE_TABLE_ID,
        title="Cobertura del análisis",
        columns=COVERAGE_COLUMNS,
        rows=filas,
        description=(
            f"Cobertura declarada del análisis para decision_scope={decision_scope}. "
            "Una fila por bloque evaluado: estado, razón y limitaciones, sin agregados."
        ),
    )


def _capitulo_cobertura(evaluations: tuple, decision_scope: str) -> core.Chapter:
    return core.Chapter(
        chapter_id=COVERAGE_CHAPTER_ID,
        title="Cobertura del análisis",
        summary="Qué bloques se evaluaron, cuáles no y por qué.",
        tables=(coverage_table(evaluations, decision_scope),),
        metadata={"eda_role": "coverage"},
    )


# --- build_eda_report ----------------------------------------------------------------


def build_eda_report(
    report_id: str,
    title: str,
    decision_scope: str,
    chapters: Any,
    evaluations: Any,
    *,
    target: Optional[str] = None,
    time_column: Optional[str] = None,
    summary: str = "",
    conclusion: str = "",
    metadata: Optional[dict] = None,
    scientific_policy: Optional[dict] = None,
) -> core.Report:
    """Arma un `Report` de kind `eda`: autoderiva, inserta el capítulo de cobertura
    PRIMERO y agrega la declaración en `metadata["eda"]`. No muta los argumentos."""
    for nombre, valor in (("target", target), ("time_column", time_column)):
        if valor is not None and not _declarado(valor):
            raise ReportingContractError(f"{nombre}: se esperaba str no vacío o None")
    if scientific_policy is not None and not isinstance(scientific_policy, dict):
        raise ReportingContractError("scientific_policy: se esperaba dict o None")
    if metadata is None:
        metadata_usuario: dict = {}
    elif isinstance(metadata, dict):
        metadata_usuario = dict(metadata)
    else:
        raise ReportingContractError(
            f"metadata: se esperaba dict o None, se recibió {type(metadata).__name__}"
        )
    if "eda" in metadata_usuario:
        raise ReportingContractError("metadata: la clave 'eda' está reservada por el profile")

    capitulos = _exigir_secuencia(chapters, "chapters")
    for i, capitulo in enumerate(capitulos):
        if not isinstance(capitulo, core.Chapter):
            raise ReportingContractError(
                f"chapters[{i}]: se esperaba Chapter, se recibió {type(capitulo).__name__}"
            )
        if capitulo.chapter_id == COVERAGE_CHAPTER_ID:
            raise ReportingContractError(f"chapter_id {COVERAGE_CHAPTER_ID!r} está reservado")
        for tabla in capitulo.tables:
            if tabla.table_id == COVERAGE_TABLE_ID:
                raise ReportingContractError(f"table_id {COVERAGE_TABLE_ID!r} está reservado")

    derivadas = derive_evaluations(
        target, time_column, evaluations, scientific_policy=scientific_policy
    )
    if decision_scope not in core.DECISION_SCOPES:
        raise ReportingContractError(
            f"decision_scope: {decision_scope!r} fuera de {core.DECISION_SCOPES}"
        )
    metadata_usuario["eda"] = {
        "profile": PROFILE_NAME,
        "profile_version": PROFILE_VERSION,
        "target": target,
        "time_column": time_column,
        "applicability": {
            e.block: {
                "state": e.state,
                "reason": e.reason,
                "limitations": e.limitations,
                "auto": e.auto,
            }
            for e in derivadas
        },
    }
    return core.Report(
        report_id=report_id,
        title=title,
        report_kind="eda",
        decision_scope=decision_scope,
        chapters=(_capitulo_cobertura(derivadas, decision_scope),) + capitulos,
        summary=summary,
        conclusion=conclusion,
        metadata=metadata_usuario,
    )


# --- validate_eda_report -----------------------------------------------------------------


def _f(codigo: str, mensaje: str, subject: Any = None, detail: Optional[str] = None,
       status: str = checks.STATUS_FAIL) -> checks.CheckResult:
    return checks.CheckResult(
        status, codigo, mensaje, detail=detail,
        subject=None if subject is None else _subject(subject),
    )


def _campo(entrada: Any, nombre: str) -> Any:
    return entrada.get(nombre) if isinstance(entrada, dict) else None


def _estado(entrada: Any) -> Optional[str]:
    estado = _campo(entrada, "state")
    return estado if isinstance(estado, str) and estado in STATES else None


def _capitulos(report: Any) -> tuple:
    try:
        return tuple(c for c in report.chapters if isinstance(c, core.Chapter))
    except Exception:  # noqa: BLE001
        return ()


def _metadata_capitulo(capitulo: Any) -> dict:
    md = getattr(capitulo, "metadata", None)
    return md if isinstance(md, dict) else {}


def _n_insights(capitulo: Any) -> int:
    insights = getattr(capitulo, "insights", None)
    return len(insights) if isinstance(insights, (list, tuple)) else 0


def validate_eda_report(report: Any, *, scientific_policy: Optional[dict] = None) -> list:
    """Valida la declaración EDA de un `Report`. Devuelve `list[CheckResult]` con un
    PASS por regla sin violaciones y un resultado por violación. NUNCA lanza."""
    try:
        return _validar(report, scientific_policy)
    except Exception as exc:  # noqa: BLE001 -- el validador es total por contrato
        return [checks.resultado_de_excepcion(CODE_PROFILE, exc)]


def _validar(report: Any, scientific_policy: Any) -> list:
    if not isinstance(report, core.Report):
        return [
            _f(
                CODE_PROFILE,
                "el objeto validado no es un Report",
                detail=f"tipo recibido: {type(report).__name__}",
            )
        ]
    metadata = report.metadata if isinstance(report.metadata, dict) else {}
    tiene_decl = "eda" in metadata
    es_eda = report.report_kind == "eda"
    if not es_eda and not tiene_decl:
        return [
            checks.CheckResult(
                checks.STATUS_NA, CODE_PROFILE, "el reporte no es de kind eda ni declara metadata eda"
            )
        ]
    if not es_eda:
        return [
            _f(
                CODE_PROFILE,
                "metadata['eda'] presente en un reporte cuyo report_kind no es 'eda'",
                detail=f"report_kind={report.report_kind!r}",
            )
        ]
    decl = metadata.get("eda")
    apl = decl.get("applicability") if isinstance(decl, dict) else None
    if not isinstance(apl, dict):
        return [
            checks.CheckResult(
                checks.STATUS_PASS, CODE_PROFILE, "report_kind eda con perfil coherente"
            ),
            _f(
                CODE_APPLICABILITY_MISSING,
                "falta la declaración metadata['eda'] con 'applicability' (dict)",
            ),
        ]
    version = decl.get("profile_version")
    perfil_ok = (
        decl.get("profile") == PROFILE_NAME
        and isinstance(version, int)
        and not isinstance(version, bool)
        and version == PROFILE_VERSION
    )
    if perfil_ok:
        resultados = [
            checks.CheckResult(
                checks.STATUS_PASS, CODE_PROFILE, "report_kind eda con perfil coherente"
            )
        ]
    else:
        resultados = [
            _f(
                CODE_PROFILE,
                f"metadata['eda'] declara un profile/versión distinto de "
                f"{PROFILE_NAME!r}/{PROFILE_VERSION}",
                detail=f"profile={decl.get('profile')!r}, profile_version={version!r}",
            )
        ]
    resultados.append(
        checks.CheckResult(
            checks.STATUS_PASS, CODE_APPLICABILITY_MISSING, "declaración de aplicabilidad presente"
        )
    )

    target_ok = _declarado(decl.get("target"))
    tiempo_ok = _declarado(decl.get("time_column")) or _politica_tiene_fecha(scientific_policy)
    scope = report.decision_scope
    claves = sorted(apl.keys(), key=_clave_orden)
    conocidos = [k for k in claves if _es_conocido(k)]
    estado_de = {k: _estado(apl[k]) for k in conocidos}
    capitulos = _capitulos(report)
    con_bloque = [(c, _metadata_capitulo(c)["eda_block"]) for c in capitulos
                  if "eda_block" in _metadata_capitulo(c)]

    def capitulos_de(bloque: str) -> list:
        return [c for c, b in con_bloque if isinstance(b, str) and b == bloque]

    def aplicables() -> list:
        return [k for k in conocidos if estado_de[k] == "applicable"]

    def sin_razon_valida() -> list:
        """Bloques not_applicable/omitted con auto no activo (candidatos a exigir razón)."""
        return [
            k for k in conocidos
            if estado_de[k] in ("not_applicable", "omitted") and _campo(apl[k], "auto") is not True
        ]

    def r_unevaluated() -> list:
        return [
            _f(CODE_BLOCK_UNEVALUATED, "bloque del catálogo sin evaluación declarada",
               subject=i.block_id)
            for i in BLOCK_CATALOG if i.block_id not in apl
        ]

    def r_unknown() -> list:
        return [
            _f(CODE_BLOCK_UNKNOWN, "bloque fuera del catálogo y sin prefijo 'x_'", subject=k)
            for k in claves if not _es_conocido(k)
        ]

    def r_state() -> list:
        return [
            _f(CODE_BLOCK_STATE, f"state inválido (válidos: {STATES})", subject=k,
               detail=f"state={_campo(apl[k], 'state')!r}")
            for k in claves if _estado(apl[k]) is None
        ]

    def r_reason() -> list:
        return [
            _f(CODE_BLOCK_REASON, "razón insuficiente para un bloque no realizado", subject=k,
               detail=f"razón normalizada={_normalizar_razon(_campo(apl[k], 'reason'))!r}")
            for k in sin_razon_valida() if _razon_insuficiente(_campo(apl[k], "reason"))
        ]

    def r_duplicated() -> list:
        grupos: dict = {}
        for k in sin_razon_valida():
            normalizada = _normalizar_razon(_campo(apl[k], "reason"))
            if normalizada:
                grupos.setdefault(normalizada, []).append(k)
        return [
            _f(CODE_REASON_DUPLICATED,
               f"la misma razón aparece en {len(bloques)} bloques distintos",
               subject=", ".join(bloques), detail=f"razón normalizada={normalizada!r}")
            for normalizada, bloques in sorted(grupos.items()) if len(bloques) >= _DUPLICADOS_MINIMOS
        ]

    def r_auto() -> list:
        out = []
        for k in claves:
            auto = _campo(apl[k], "auto")
            if auto is None or auto is False:
                continue
            if auto is not True:
                out.append(_f(CODE_AUTO_INVALID, "el campo 'auto' no es booleano", subject=k,
                              detail=f"auto={auto!r}"))
                continue
            info = _INFO_POR_ID.get(k)
            motivos = []
            if info is None or not (info.requires_target or info.requires_time):
                motivos.append("el bloque no tiene precondición estructural")
            else:
                if info.requires_target and target_ok:
                    motivos.append("el target sí está declarado")
                if info.requires_time and tiempo_ok:
                    motivos.append("la columna temporal sí está declarada")
            if _estado(apl[k]) != "not_applicable":
                motivos.append("el estado no es not_applicable")
            if motivos:
                out.append(_f(CODE_AUTO_INVALID, "auto=True no es válido", subject=k,
                              detail="; ".join(motivos)))
        return out

    def r_no_chapter() -> list:
        return [
            _f(CODE_BLOCK_NO_CHAPTER, "bloque applicable sin capítulo con ese eda_block", subject=k)
            for k in aplicables() if not capitulos_de(k)
        ]

    def r_no_insight() -> list:
        return [
            _f(CODE_BLOCK_NO_INSIGHT, "bloque applicable sin ningún Insight en sus capítulos",
               subject=k)
            for k in aplicables() if sum(_n_insights(c) for c in capitulos_de(k)) == 0
        ]

    def r_contradiction() -> list:
        out = []
        for c, b in con_bloque:
            if isinstance(b, str) and estado_de.get(b) in ("not_applicable", "omitted"):
                out.append(_f(CODE_BLOCK_CONTRADICTION,
                              f"capítulo de un bloque declarado {estado_de[b]}",
                              subject=c.chapter_id, detail=f"eda_block={b}",
                              status=checks.STATUS_WARN))
        return out

    def r_chapter_unknown() -> list:
        return [
            _f(CODE_CHAPTER_BLOCK_UNKNOWN, "capítulo con eda_block no evaluado en la declaración",
               subject=c.chapter_id, detail=f"eda_block={b!r}")
            for c, b in con_bloque if not (isinstance(b, str) and b in apl)
        ]

    def r_target() -> list:
        return [
            _f(CODE_TARGET_DECLARED, "bloque applicable que requiere target pero no hay target declarado",
               subject=k)
            for k in aplicables()
            if k in _INFO_POR_ID and _INFO_POR_ID[k].requires_target and not target_ok
        ]

    def r_time() -> list:
        return [
            _f(CODE_TIME_DECLARED,
               "bloque applicable que requiere tiempo pero no hay columna temporal declarada",
               subject=k)
            for k in aplicables()
            if k in _INFO_POR_ID and _INFO_POR_ID[k].requires_time and not tiempo_ok
        ]

    def r_omitted_scope() -> list:
        omitidos = [k for k in conocidos if estado_de[k] == "omitted"]
        if scope in _SCOPES_ESTRICTOS and omitidos:
            return [_f(CODE_OMITTED_SCOPE,
                       f"bloques omitidos con decision_scope={scope}: visibles para el reviewer",
                       subject=", ".join(omitidos), status=checks.STATUS_WARN)]
        return []

    def r_leakage() -> list:
        # Dispara si bivariate_target está applicable O si existe cualquier capítulo de ese
        # bloque (en cualquier estado declarado): omitir el target no debe evadir la regla.
        hay_bivariate = (
            estado_de.get("bivariate_target") == "applicable" or bool(capitulos_de("bivariate_target"))
        )
        if (scope in _SCOPES_ESTRICTOS and hay_bivariate
                and estado_de.get("leakage_review") != "applicable"):
            return [_f(CODE_LEAKAGE_REVIEW_REQUIRED,
                       f"análisis bivariate_target con decision_scope={scope} exige "
                       "leakage_review applicable",
                       subject="leakage_review")]
        return []

    def r_na_contradice() -> list:
        out = []
        for k in conocidos:
            info = _INFO_POR_ID.get(k)
            if info is None or estado_de[k] != "not_applicable" or _campo(apl[k], "auto") is True:
                continue
            motivos = []
            if info.requires_target and target_ok:
                motivos.append("el target sí está declarado")
            if info.requires_time and tiempo_ok:
                motivos.append("la columna temporal sí está declarada")
            if motivos:
                out.append(_f(CODE_NA_CONTRADICTS_DECLARATION,
                              "bloque not_applicable manual que contradice la declaración",
                              subject=k, detail="; ".join(motivos), status=checks.STATUS_WARN))
        return out

    def r_extension_sombrea() -> list:
        out = []
        for k in conocidos:
            if k.startswith(EXTENSION_PREFIX):
                sufijo = _normalizar_id(k[len(EXTENSION_PREFIX):])
                if sufijo in _IDS_CATALOGO_NORMALIZADOS:
                    out.append(_f(CODE_EXTENSION_SHADOWS_CATALOG,
                                  "la extensión x_ repite el id de un bloque del catálogo",
                                  subject=k, status=checks.STATUS_WARN))
        return out

    def r_exploratory() -> list:
        if scope == "exploratory" and estado_de.get("bivariate_target") == "applicable":
            return [_f(CODE_EXPLORATORY_TARGET_USE,
                       "asociación con el target en scope exploratory: "
                       "no es insumo de selección de features",
                       subject="bivariate_target", status=checks.STATUS_WARN)]
        return []

    def r_cobertura() -> list:
        cap = next((c for c in capitulos if c.chapter_id == COVERAGE_CHAPTER_ID), None)
        if cap is None:
            return [_f(CODE_COVERAGE_TABLE, f"falta el capítulo {COVERAGE_CHAPTER_ID!r}")]
        tabla = next((t for t in cap.tables if t.table_id == COVERAGE_TABLE_ID), None)
        if tabla is None:
            return [_f(CODE_COVERAGE_TABLE, f"falta la tabla {COVERAGE_TABLE_ID!r}",
                       subject=COVERAGE_CHAPTER_ID)]
        if tuple(tabla.columns) != COVERAGE_COLUMNS:
            return [_f(CODE_COVERAGE_TABLE, f"columnas distintas de {COVERAGE_COLUMNS}",
                       subject=COVERAGE_TABLE_ID, detail=f"columnas={tuple(tabla.columns)!r}")]
        esperadas = [
            (_subject(k), _texto(_campo(apl[k], "state")), _texto(_campo(apl[k], "reason")),
             _texto(_campo(apl[k], "limitations")))
            for k in claves
        ]
        reales = [tuple(fila) for fila in tabla.rows]
        out = []
        if len(reales) != len(esperadas):
            out.append(_f(CODE_COVERAGE_TABLE,
                          "la tabla tiene filas de más o de menos respecto de la declaración",
                          subject=COVERAGE_TABLE_ID,
                          detail=f"filas={len(reales)}, declaradas={len(esperadas)}"))
        for esperada, real in zip(esperadas, reales):
            if esperada != real:
                out.append(_f(CODE_COVERAGE_TABLE, "fila que no coincide con la declaración",
                              subject=esperada[0], detail=f"fila={real!r}"))
        return out

    reglas = (
        (CODE_BLOCK_UNEVALUATED, "todos los bloques del catálogo tienen evaluación", r_unevaluated),
        (CODE_BLOCK_UNKNOWN, "sin bloques fuera del catálogo", r_unknown),
        (CODE_BLOCK_STATE, "estados válidos", r_state),
        (CODE_BLOCK_REASON, "razones suficientes", r_reason),
        (CODE_REASON_DUPLICATED, "sin razones duplicadas", r_duplicated),
        (CODE_AUTO_INVALID, "autoderivaciones válidas", r_auto),
        (CODE_BLOCK_NO_CHAPTER, "bloques applicable con capítulo", r_no_chapter),
        (CODE_BLOCK_NO_INSIGHT, "bloques applicable con insight", r_no_insight),
        (CODE_BLOCK_CONTRADICTION, "sin capítulos de bloques no aplicados", r_contradiction),
        (CODE_CHAPTER_BLOCK_UNKNOWN, "capítulos con eda_block evaluado", r_chapter_unknown),
        (CODE_TARGET_DECLARED, "precondición de target declarada", r_target),
        (CODE_TIME_DECLARED, "precondición temporal declarada", r_time),
        (CODE_NA_CONTRADICTS_DECLARATION, "sin not_applicable manual contradictorio",
         r_na_contradice),
        (CODE_EXTENSION_SHADOWS_CATALOG, "sin extensiones que repitan el catálogo",
         r_extension_sombrea),
        (CODE_OMITTED_SCOPE, "sin omitidos que requieran atención en este scope", r_omitted_scope),
        (CODE_LEAKAGE_REVIEW_REQUIRED, "revisión de leakage no exigida o presente", r_leakage),
        (CODE_EXPLORATORY_TARGET_USE, "sin uso exploratorio del target", r_exploratory),
        (CODE_COVERAGE_TABLE, "tabla de cobertura coincide con la declaración", r_cobertura),
    )
    for codigo, mensaje_pass, regla in reglas:
        try:
            violaciones = regla()
        except Exception as exc:  # noqa: BLE001 -- una regla rota no frena a las demás
            resultados.append(checks.resultado_de_excepcion(codigo, exc))
            continue
        if violaciones:
            resultados.extend(violaciones)
        else:
            resultados.append(checks.CheckResult(checks.STATUS_PASS, codigo, mensaje_pass))
    return resultados

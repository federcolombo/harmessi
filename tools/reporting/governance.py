"""Governance de reportes (v0.6 Change 1, `20260918-reporting-governance`).

Output guard declarativo y de SOLO LECTURA: compone piezas ya existentes de
`dsguard` (`checks`, `pathguard`, `repo`, `scientific_validity`, `core`) con los
contratos neutrales de `reporting.core`. No agrega motores, status ni
matching propios: todo resultado es un `dsguard.checks.CheckResult` y las
corridas pasan por `checks.ejecutar_checks` ("nunca frena").

Garantías transversales (spec R1):
- nunca escribe, crea, mueve ni borra nada en disco;
- `evaluate_governance`, `evaluate_destination`, `check_flow_inputs` y
  `output_allowed` nunca propagan excepciones. Excepciones por diseño:
  `load_policy` y `resolve_output_dir` levantan `ReportingPolicyError`, y
  `context_from_report` levanta `AttributeError`/`TypeError` si `report` no es
  un `Report` válido (`GovernanceContext` no valida al construir);
- resultados deterministas (mismo disco + mismo contexto => mismos resultados
  en el mismo orden; única dependencia temporal: vencimiento de excepciones
  de lectura evaluado por `pathguard` contra el reloj UTC);
- solo evalúa RUTAS: nunca abre el contenido de holdouts ni de fuentes de datos.

Ausencia != PASS: un dato no declarado, desconocido o no verificable produce
FAIL, WARN o N/A según el check, y ningún check devuelve una lista vacía.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Optional

_TOOLS_DIR = Path(__file__).resolve().parents[1]
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from dsguard import checks, pathguard, scientific_validity  # noqa: E402
from dsguard import core as dsguard_core  # noqa: E402
from dsguard import repo as repo_mod  # noqa: E402

from . import core as reporting_core  # noqa: E402

# --- Códigos (spec R2) --------------------------------------------------------

CODE_POLICY = "REPORT-POLICY"
CODE_DEST_SAFE = "REPORT-DEST-SAFE"
CODE_DEST_SCOPE = "REPORT-DEST-SCOPE"
CODE_DEST_CROSS_SCOPE = "REPORT-DEST-CROSS-SCOPE"
CODE_SENSITIVE_DEST = "REPORT-SENSITIVE-DEST"
CODE_SOURCE_ACCESS = "REPORT-SOURCE-ACCESS"
CODE_HOLDOUT_ACCESS = "REPORT-HOLDOUT-ACCESS"
CODE_HOLDOUT_SOURCE = "REPORT-HOLDOUT-SOURCE"
CODE_ISOLATION_INPUT = "REPORT-ISOLATION-INPUT"
CODE_SCI_CUTOFF = "REPORT-SCI-CUTOFF"

CODES = (
    CODE_POLICY,
    CODE_DEST_SAFE,
    CODE_DEST_SCOPE,
    CODE_DEST_CROSS_SCOPE,
    CODE_SENSITIVE_DEST,
    CODE_SOURCE_ACCESS,
    CODE_HOLDOUT_ACCESS,
    CODE_HOLDOUT_SOURCE,
    CODE_ISOLATION_INPUT,
    CODE_SCI_CUTOFF,
)

# Códigos que un `publish` debe exigir con `output_allowed(..., require_codes=...)`.
REQUIRED_DESTINATION_CODES = (CODE_POLICY, CODE_DEST_SAFE, CODE_DEST_SCOPE)

# Código base para excepciones inesperadas fuera de un check individual
# (contexto que no es un `GovernanceContext`, etc.); termina en `-EXCEPCION`.
_CODE_GOVERNANCE_BASE = "REPORT-GOVERNANCE"

POLICY_RELATIVE_PATH = ".harmessi/reporting-policy.json"
POLICY_SCHEMA_VERSION = 1
POLICY_SOURCE_DEFAULT = "default"

_METACARACTERES_FNMATCH = frozenset("*?[]")
_SCOPE_EXPLORATORY = "exploratory"


# --- Policy (spec R3-R6) ------------------------------------------------------


class ReportingPolicyError(Exception):
    """`.harmessi/reporting-policy.json` existe pero es inválido, o un argumento
    de `resolve_output_dir` no cumple el contrato. Fail-closed: nunca se
    recupera con defaults."""


@dataclass(frozen=True)
class ReportingPolicy:
    """Policy inmutable. Nota: `destination_roots` es un `dict` y NO debe
    mutarse tras la carga (frozen impide reasignar el campo, no mutar el dict)."""

    destination_roots: dict
    sensitive_destination_roots: tuple = ()
    source: str = POLICY_SOURCE_DEFAULT


def _como_path(valor: Any) -> Optional[Path]:
    if isinstance(valor, Path):
        return valor
    if isinstance(valor, str) and valor:
        try:
            return Path(valor)
        except (ValueError, TypeError):
            return None
    return None


def _subject(valor: Any) -> str:
    return valor if isinstance(valor, str) else repr(valor)


def _validar_root(valor: Any, nombre: str) -> str:
    """Forma canónica estricta, sin normalización silenciosa (spec R4)."""
    if not isinstance(valor, str) or not valor:
        raise ReportingPolicyError(f"{nombre}: debe ser un string no vacío (recibido {valor!r})")
    if "\\" in valor:
        raise ReportingPolicyError(f"{nombre}: debe usar '/' como separador (sin '\\'): {valor!r}")
    if valor.startswith("/") or ":" in valor:
        raise ReportingPolicyError(f"{nombre}: debe ser relativo al repo (sin '/' inicial ni unidad): {valor!r}")
    if valor.endswith("/"):
        raise ReportingPolicyError(f"{nombre}: no puede terminar en '/': {valor!r}")
    for segmento in valor.split("/"):
        if segmento in ("", ".", ".."):
            raise ReportingPolicyError(
                f"{nombre}: segmentos vacíos, '.' o '..' no permitidos: {valor!r}"
            )
    if any(c in _METACARACTERES_FNMATCH for c in valor):
        raise ReportingPolicyError(f"{nombre}: no admite metacaracteres de fnmatch (* ? [ ]): {valor!r}")
    return valor


def _anidados_o_iguales(a: str, b: str) -> bool:
    a, b = a.casefold(), b.casefold()
    return a == b or a.startswith(b + "/") or b.startswith(a + "/")


def _validar_relaciones(roots: dict, sensibles: tuple) -> None:
    scopes = list(roots)
    for i in range(len(scopes)):
        for j in range(i + 1, len(scopes)):
            if _anidados_o_iguales(roots[scopes[i]], roots[scopes[j]]):
                raise ReportingPolicyError(
                    f"los roots de {scopes[i]!r} ({roots[scopes[i]]!r}) y {scopes[j]!r} "
                    f"({roots[scopes[j]]!r}) deben ser distintos y no anidados"
                )
    for sensible in sensibles:
        if not any(sensible.casefold().startswith(r.casefold() + "/") for r in roots.values()):
            raise ReportingPolicyError(
                f"sensitive_destination_root {sensible!r} debe ser subdirectorio estricto de algún root de scope"
            )


def _construir_policy(datos: Any, source: str) -> ReportingPolicy:
    if not isinstance(datos, dict):
        raise ReportingPolicyError("el contenido de reporting-policy.json debe ser un objeto JSON")
    version = datos.get("schema_version")
    if type(version) is not int or version != POLICY_SCHEMA_VERSION:
        raise ReportingPolicyError(
            f"schema_version desconocida: {version!r} (se esperaba {POLICY_SCHEMA_VERSION})"
        )
    declarados: dict = {}
    if "destination_roots" in datos:
        destination_roots = datos["destination_roots"]
        if not isinstance(destination_roots, dict):
            raise ReportingPolicyError("'destination_roots' debe ser un objeto JSON")
        for clave, valor in destination_roots.items():
            if clave not in reporting_core.DECISION_SCOPES:
                raise ReportingPolicyError(
                    f"destination_roots: clave {clave!r} fuera de {reporting_core.DECISION_SCOPES}"
                )
            declarados[clave] = _validar_root(valor, f"destination_roots[{clave!r}]")
    sensibles: tuple = ()
    if "sensitive_destination_roots" in datos:
        lista = datos["sensitive_destination_roots"]
        if not isinstance(lista, list) or not all(isinstance(x, str) for x in lista):
            raise ReportingPolicyError("'sensitive_destination_roots' debe ser una lista de strings")
        sensibles = tuple(_validar_root(x, "sensitive_destination_roots[]") for x in lista)
    roots = {
        scope: declarados.get(scope, f"reports/{scope}") for scope in reporting_core.DECISION_SCOPES
    }
    _validar_relaciones(roots, sensibles)
    return ReportingPolicy(destination_roots=roots, sensitive_destination_roots=sensibles, source=source)


def load_policy(repo_root: Any) -> ReportingPolicy:
    """Carga `.harmessi/reporting-policy.json` (solo lectura). Ausente =>
    defaults deterministas. Levanta `ReportingPolicyError` si el archivo es
    inválido o si `repo_root` no es un directorio existente (fail-closed)."""
    repo = _como_path(repo_root)
    if repo is None:
        raise ReportingPolicyError(f"repo_root inválido: {repo_root!r}")
    try:
        es_directorio = repo.is_dir()
    except OSError:
        es_directorio = False
    if not es_directorio:
        raise ReportingPolicyError(f"repo_root no existe o no es un directorio: {repo_root!r}")
    ruta = repo / POLICY_RELATIVE_PATH
    try:
        existe = ruta.exists()
    except OSError as exc:
        raise ReportingPolicyError(f"no se pudo acceder a {POLICY_RELATIVE_PATH}: {exc}") from exc
    if not existe:
        return _construir_policy({"schema_version": POLICY_SCHEMA_VERSION}, POLICY_SOURCE_DEFAULT)
    try:
        contenido = ruta.read_text(encoding="utf-8")
        datos = json.loads(contenido)
    except (OSError, ValueError) as exc:
        raise ReportingPolicyError(f"{POLICY_RELATIVE_PATH} no se pudo leer o no es JSON válido: {exc}") from exc
    return _construir_policy(datos, POLICY_RELATIVE_PATH)


def resolve_output_dir(policy: ReportingPolicy, decision_scope: Any, report_id: Any) -> str:
    """`"<root>/<report_id>"` (posix, relativo al repo). No crea nada en disco."""
    if decision_scope not in reporting_core.DECISION_SCOPES:
        raise ReportingPolicyError(
            f"decision_scope {decision_scope!r} fuera de {reporting_core.DECISION_SCOPES}"
        )
    if not reporting_core.es_id_valido(report_id):
        raise ReportingPolicyError(f"report_id inválido (contrato de ids de reporting.core): {report_id!r}")
    try:
        root = policy.destination_roots[decision_scope]
    except (AttributeError, KeyError, TypeError) as exc:
        raise ReportingPolicyError(f"policy inválida: {exc!r}") from exc
    return f"{root}/{report_id}"


def _bajo_root(ruta_relativa_posix: str, root: str) -> bool:
    """Pertenencia ESTRICTA (case-insensitive) a un root: el root mismo NO
    pertenece; `reports/exploratory-x` NO pertenece a `reports/exploratory`."""
    return repo_mod.path_matches_any(ruta_relativa_posix.casefold(), [f"{root.casefold()}/**"])


# --- Contexto (spec R7) -------------------------------------------------------


@dataclass(frozen=True)
class GovernanceContext:
    """No valida valores al construir: los valores inválidos los reporta cada
    check como FAIL, no una excepción."""

    repo_root: Any
    report_id: Any
    report_kind: Any
    decision_scope: Any
    out_dir: Any
    sources: Any = ()
    holdout_access: Optional[str] = None
    data_cutoff: Optional[str] = None
    sensitive_artifacts: Any = ()
    agent_type: Optional[str] = None

    def __post_init__(self) -> None:
        if isinstance(self.sources, list):
            object.__setattr__(self, "sources", tuple(self.sources))
        if isinstance(self.sensitive_artifacts, list):
            object.__setattr__(self, "sensitive_artifacts", tuple(self.sensitive_artifacts))


def context_from_report(
    repo_root: Any,
    report: Any,
    out_dir: Any,
    *,
    sources: Any = (),
    holdout_access: Optional[str] = None,
    data_cutoff: Optional[str] = None,
    agent_type: Optional[str] = None,
) -> GovernanceContext:
    """Arma el contexto desde un `Report` de `reporting.core`. Si `report` no es
    un `Report` válido (sin `iter_tables`/`iter_figures`/ids) levanta
    `AttributeError`/`TypeError`: no es un check y no captura. Este helper no
    valida `out_dir`, `sources` ni el resto; eso lo hacen los checks."""
    sensibles = [t.table_id for t in report.iter_tables() if t.sensitive]
    sensibles += [f.figure_id for f in report.iter_figures() if f.sensitive]
    return GovernanceContext(
        repo_root=repo_root,
        report_id=report.report_id,
        report_kind=report.report_kind,
        decision_scope=report.decision_scope,
        out_dir=out_dir,
        sources=sources,
        holdout_access=holdout_access,
        data_cutoff=data_cutoff,
        sensitive_artifacts=tuple(sensibles),
        agent_type=agent_type,
    )


# --- Helpers internos ---------------------------------------------------------


def _r(
    status: str,
    code: str,
    message: str,
    *,
    subject: Optional[str] = None,
    kind: str = checks.KIND_CHECK,
    detail: Optional[str] = None,
) -> checks.CheckResult:
    return checks.CheckResult(status, code, message, detail=detail, subject=subject, kind=kind)


def _fail_tecnico(code: str, message: str, subject: Optional[str] = None) -> checks.CheckResult:
    return _r(checks.STATUS_FAIL, code, message, subject=subject, kind=checks.KIND_TECHNICAL_ERROR)


def _secuencia(valor: Any) -> Optional[tuple]:
    return tuple(valor) if isinstance(valor, (list, tuple)) else None


def _string_no_vacio(valor: Any) -> bool:
    return isinstance(valor, str) and bool(valor.strip())


def _cargar_config(repo: Path):
    """`(config, None)` o `(None, ConfigGuardrailsError)`."""
    try:
        return pathguard.cargar_config(repo), None
    except pathguard.ConfigGuardrailsError as exc:
        return None, exc


def _decision(tool_name: str, ruta: str, agent_type: Any, config, repo: Path) -> tuple:
    """Mismo evaluador que el hook: `pathguard.evaluar_tool_call`."""
    payload = {"tool_name": tool_name, "tool_input": {"file_path": ruta}, "agent_type": agent_type}
    return pathguard.evaluar_tool_call(payload, config, repo)


def _cargar_policy_resultado(repo_root: Any) -> tuple:
    """`(policy, CheckResult REPORT-POLICY)`; `policy` es `None` si falla."""
    try:
        policy = load_policy(repo_root)
    except ReportingPolicyError as exc:
        return None, _fail_tecnico(CODE_POLICY, f"Policy de reporting inválida (fail-closed): {exc}")
    except Exception as exc:  # noqa: BLE001 - nunca debe escapar
        return None, checks.resultado_de_excepcion(CODE_POLICY, exc)
    if policy.source == POLICY_SOURCE_DEFAULT:
        mensaje = "Policy de reporting: default (sin .harmessi/reporting-policy.json)."
    else:
        mensaje = f"Policy de reporting cargada desde {policy.source}."
    return policy, _r(checks.STATUS_PASS, CODE_POLICY, mensaje)


# --- REPORT-DEST-SAFE (R9) ----------------------------------------------------


def _check_dest_safe(ctx: GovernanceContext, repo: Path) -> list:
    out_dir = ctx.out_dir
    if not _string_no_vacio(out_dir):
        return [_r(checks.STATUS_FAIL, CODE_DEST_SAFE, "out_dir debe ser un string no vacío.", subject=_subject(out_dir))]
    config, error = _cargar_config(repo)
    if error is not None:
        return [_fail_tecnico(CODE_DEST_SAFE, f"guardrails.json corrupto (fail-closed): {error}", subject=out_dir)]
    base = out_dir.rstrip("/\\") or out_dir
    rutas = [
        f"{base}/{reporting_core.REPORT_FILENAME}",
        f"{base}/{reporting_core.MANIFEST_FILENAME}",
        f"{base}/{reporting_core.INSIGHTS_FILENAME}",
        f"{base}/{reporting_core.ARTIFACTS_DIRNAME}/_",
    ]
    fallas = []
    for ruta in rutas:
        permitido, motivo = _decision("Write", ruta, ctx.agent_type, config, repo)
        if not permitido:
            fallas.append(_r(checks.STATUS_FAIL, CODE_DEST_SAFE, motivo, subject=ruta))
    if fallas:
        return fallas
    return [
        _r(
            checks.STATUS_PASS,
            CODE_DEST_SAFE,
            "Las cuatro rutas de salida canónicas están permitidas para escritura (pathguard).",
            subject=out_dir,
        )
    ]


# --- REPORT-DEST-SCOPE / REPORT-DEST-CROSS-SCOPE (R10) ------------------------


def _check_dest_scope(ctx: GovernanceContext, policy: ReportingPolicy, repo: Path) -> list:
    scope = ctx.decision_scope
    out_dir = ctx.out_dir
    if scope not in reporting_core.DECISION_SCOPES:
        return [
            _r(
                checks.STATUS_FAIL,
                CODE_DEST_SCOPE,
                f"decision_scope {scope!r} fuera de {reporting_core.DECISION_SCOPES} (el scope nunca se infiere).",
                subject=_subject(out_dir),
            )
        ]
    if not _string_no_vacio(out_dir):
        return [_r(checks.STATUS_FAIL, CODE_DEST_SCOPE, "out_dir debe ser un string no vacío.", subject=_subject(out_dir))]
    relativa, dentro = pathguard.resolver_ruta_relativa(out_dir, repo)
    if not dentro:
        return [
            _r(
                checks.STATUS_FAIL,
                CODE_DEST_SCOPE,
                "out_dir fuera del repositorio o no resoluble.",
                subject=out_dir,
            )
        ]
    root_propio = policy.destination_roots[scope]
    if _bajo_root(relativa, root_propio):
        return [
            _r(
                checks.STATUS_PASS,
                CODE_DEST_SCOPE,
                f"out_dir {relativa!r} está bajo el root del scope {scope!r} ({root_propio!r}).",
                subject=out_dir,
            )
        ]
    for otro_scope, otro_root in policy.destination_roots.items():
        if otro_scope != scope and _bajo_root(relativa, otro_root):
            return [
                _r(
                    checks.STATUS_FAIL,
                    CODE_DEST_CROSS_SCOPE,
                    f"Destino de otro scope: {relativa!r} cae bajo el root de {otro_scope!r} "
                    f"({otro_root!r}) y el reporte es {scope!r}; vector de leakage "
                    f"exploratorio <-> model_valid.",
                    subject=out_dir,
                )
            ]
    if relativa.casefold() == root_propio.casefold():
        motivo = f"out_dir es el root del scope {scope!r} ({root_propio!r}); debe ser un subdirectorio."
    else:
        motivo = f"out_dir {relativa!r} cae fuera de todos los roots; el root de {scope!r} es {root_propio!r}."
    return [_r(checks.STATUS_FAIL, CODE_DEST_SCOPE, motivo, subject=out_dir)]


# --- REPORT-SENSITIVE-DEST (R11) ----------------------------------------------


def _check_sensitive_dest(ctx: GovernanceContext, policy: ReportingPolicy, repo: Path) -> list:
    sensibles = _secuencia(ctx.sensitive_artifacts)
    if sensibles is None:
        return [_r(checks.STATUS_FAIL, CODE_SENSITIVE_DEST, "sensitive_artifacts debe ser una lista o tupla.")]
    if not sensibles:
        return [_r(checks.STATUS_NA, CODE_SENSITIVE_DEST, "Sin artefactos sensibles declarados.")]
    out_dir = ctx.out_dir
    if not _string_no_vacio(out_dir):
        return [_r(checks.STATUS_FAIL, CODE_SENSITIVE_DEST, "out_dir debe ser un string no vacío.", subject=_subject(out_dir))]
    if not policy.sensitive_destination_roots:
        return [
            _r(
                checks.STATUS_FAIL,
                CODE_SENSITIVE_DEST,
                "Hay artefactos sensibles pero la policy no declara ningún destino sensible: "
                "declarar 'sensitive_destination_roots' en .harmessi/reporting-policy.json.",
                subject=out_dir,
            )
        ]
    relativa, dentro = pathguard.resolver_ruta_relativa(out_dir, repo)
    if not dentro:
        return [_r(checks.STATUS_FAIL, CODE_SENSITIVE_DEST, "out_dir fuera del repositorio o no resoluble.", subject=out_dir)]
    if any(_bajo_root(relativa, root) for root in policy.sensitive_destination_roots):
        return [
            _r(
                checks.STATUS_PASS,
                CODE_SENSITIVE_DEST,
                f"out_dir {relativa!r} está bajo un destino sensible declarado.",
                subject=out_dir,
            )
        ]
    return [
        _r(
            checks.STATUS_FAIL,
            CODE_SENSITIVE_DEST,
            f"Hay artefactos sensibles ({', '.join(map(str, sensibles))}) y out_dir {relativa!r} "
            f"no está bajo ninguno de sensitive_destination_roots {list(policy.sensitive_destination_roots)!r}.",
            subject=out_dir,
        )
    ]


# --- REPORT-SOURCE-ACCESS (R12) -----------------------------------------------


def _check_source_access(ctx: GovernanceContext, repo: Path) -> list:
    fuentes = _secuencia(ctx.sources)
    if fuentes is None:
        return [_r(checks.STATUS_FAIL, CODE_SOURCE_ACCESS, "sources debe ser una lista o tupla de rutas.")]
    if not fuentes:
        return [_r(checks.STATUS_NA, CODE_SOURCE_ACCESS, "Sin fuentes declaradas.")]
    config, error = _cargar_config(repo)
    if error is not None:
        return [_fail_tecnico(CODE_SOURCE_ACCESS, f"guardrails.json corrupto (fail-closed): {error}")]
    resultados = []
    for fuente in fuentes:
        if not _string_no_vacio(fuente):
            resultados.append(
                _r(checks.STATUS_FAIL, CODE_SOURCE_ACCESS, "La fuente debe ser un string no vacío.", subject=_subject(fuente))
            )
            continue
        permitido, motivo = _decision("Read", fuente, None, config, repo)
        estado = checks.STATUS_PASS if permitido else checks.STATUS_FAIL
        resultados.append(_r(estado, CODE_SOURCE_ACCESS, motivo, subject=fuente))
    return resultados


# --- REPORT-HOLDOUT-ACCESS (R13) ----------------------------------------------


def _autorizacion_read(repo: Path, report_kind: Any, decision_scope: Any) -> tuple:
    """`(autorizado, detalle, error_tecnico)`."""
    try:
        policy = scientific_validity.leer_policy(repo)
    except scientific_validity.ScientificPolicyError as exc:
        return False, "", f"Policy científica inválida (SCI-POLICY): {exc}"
    faltantes = []
    if report_kind != "evaluation":
        faltantes.append(f"report_kind={report_kind!r} (se requiere 'evaluation')")
    if decision_scope not in reporting_core.DECISION_SCOPES or decision_scope == _SCOPE_EXPLORATORY:
        faltantes.append(f"decision_scope={decision_scope!r} (se requiere model_valid u operational)")
    holdout = policy.get("holdout")
    if not isinstance(holdout, dict) or holdout.get("declared") is not True:
        faltantes.append("la policy científica no declara holdout (holdout.declared != true)")
    final = holdout.get("final_evaluation") if isinstance(holdout, dict) else None
    if not isinstance(final, dict) or final.get("authorized") is not True:
        faltantes.append("holdout.final_evaluation.authorized != true en la policy científica")
    if faltantes:
        return False, "; ".join(faltantes), None
    reason = final.get("reason")
    detalle = f"reason: {reason}" if isinstance(reason, str) and reason.strip() else "sin reason declarado"
    return True, detalle, None


def _check_holdout_access(ctx: GovernanceContext, repo: Path) -> list:
    acceso = ctx.holdout_access
    if isinstance(acceso, str) and acceso == "none":
        return [_r(checks.STATUS_PASS, CODE_HOLDOUT_ACCESS, "holdout_access='none' declarado.")]
    if isinstance(acceso, str) and acceso == "read":
        autorizado, detalle, tecnico = _autorizacion_read(repo, ctx.report_kind, ctx.decision_scope)
        if tecnico is not None:
            return [_fail_tecnico(CODE_HOLDOUT_ACCESS, tecnico)]
        if autorizado:
            return [
                _r(
                    checks.STATUS_PASS,
                    CODE_HOLDOUT_ACCESS,
                    f"holdout_access='read' autorizado por la policy científica ({detalle}).",
                )
            ]
        return [
            _r(checks.STATUS_FAIL, CODE_HOLDOUT_ACCESS, f"holdout_access='read' no autorizado: {detalle}.")
        ]
    return [
        _r(
            checks.STATUS_FAIL,
            CODE_HOLDOUT_ACCESS,
            f"holdout_access no declarado o inválido ({acceso!r}): debe ser exactamente 'none' o 'read'.",
        )
    ]


# --- REPORT-HOLDOUT-SOURCE (R14) ----------------------------------------------


def _matchea_holdout(ruta_relativa_posix: str, holdouts: tuple) -> bool:
    return repo_mod.path_matches_any(ruta_relativa_posix.casefold(), [p.casefold() for p in holdouts])


def _holdout_declarado(repo: Path) -> tuple:
    """`(declarado, error_tecnico)` según `holdout.declared` de la policy científica."""
    try:
        policy = scientific_validity.leer_policy(repo)
    except scientific_validity.ScientificPolicyError as exc:
        return False, f"Policy científica inválida (SCI-POLICY): {exc}"
    holdout = policy.get("holdout")
    return isinstance(holdout, dict) and holdout.get("declared") is True, None


def _check_holdout_source(ctx: GovernanceContext, repo: Path) -> list:
    fuentes = _secuencia(ctx.sources)
    if fuentes is None:
        return [_r(checks.STATUS_FAIL, CODE_HOLDOUT_SOURCE, "sources debe ser una lista o tupla de rutas.")]
    if not fuentes:
        return [_r(checks.STATUS_NA, CODE_HOLDOUT_SOURCE, "Sin fuentes declaradas.")]
    config, error = _cargar_config(repo)
    if error is not None:
        return [_fail_tecnico(CODE_HOLDOUT_SOURCE, f"guardrails.json corrupto (fail-closed): {error}")]
    acceso = ctx.holdout_access
    cache: dict = {}
    resultados = []
    for fuente in fuentes:
        subject = _subject(fuente)
        if not _string_no_vacio(fuente):
            resultados.append(
                _r(checks.STATUS_NA, CODE_HOLDOUT_SOURCE, "Fuente inválida: la denegación la reporta REPORT-SOURCE-ACCESS.", subject=subject)
            )
            continue
        relativa, dentro = pathguard.resolver_ruta_relativa(fuente, repo)
        if not dentro:
            resultados.append(
                _r(checks.STATUS_NA, CODE_HOLDOUT_SOURCE, "Fuente fuera del repo o no resoluble: la denegación la reporta REPORT-SOURCE-ACCESS.", subject=subject)
            )
            continue
        if not config.holdouts:
            # Sin patrones estructurales: ausencia != PASS.
            if "declarado" not in cache:
                cache["declarado"] = _holdout_declarado(repo)
            declarado, tecnico = cache["declarado"]
            if tecnico is not None:
                resultados.append(_fail_tecnico(CODE_HOLDOUT_SOURCE, tecnico, subject=subject))
            elif declarado:
                resultados.append(
                    _r(
                        checks.STATUS_FAIL,
                        CODE_HOLDOUT_SOURCE,
                        "La policy científica declara holdout pero guardrails.json no tiene patrones en "
                        "'holdouts': sin protección estructural (mismo criterio que SCI-HOLDOUT-PROTECTION); "
                        "la fuente no se puede verificar.",
                        subject=subject,
                    )
                )
            else:
                resultados.append(
                    _r(
                        checks.STATUS_NA,
                        CODE_HOLDOUT_SOURCE,
                        "Sin patrones de holdout en guardrails.json y sin holdout declarado: nada contra qué verificar.",
                        subject=subject,
                    )
                )
            continue
        if not _matchea_holdout(relativa, config.holdouts):
            resultados.append(_r(checks.STATUS_PASS, CODE_HOLDOUT_SOURCE, "La fuente no cae en ningún holdout declarado.", subject=subject))
            continue
        if not (isinstance(acceso, str) and acceso == "read"):
            resultados.append(
                _r(
                    checks.STATUS_FAIL,
                    CODE_HOLDOUT_SOURCE,
                    f"La fuente cae en un holdout pero holdout_access={acceso!r} (se requiere 'read' autorizado): "
                    "contradicción entre declaración y fuentes.",
                    subject=subject,
                )
            )
            continue
        if "auth" not in cache:
            cache["auth"] = _autorizacion_read(repo, ctx.report_kind, ctx.decision_scope)
        autorizado, detalle, tecnico = cache["auth"]
        if tecnico is not None:
            resultados.append(_fail_tecnico(CODE_HOLDOUT_SOURCE, tecnico, subject=subject))
        elif not autorizado:
            resultados.append(
                _r(checks.STATUS_FAIL, CODE_HOLDOUT_SOURCE, f"La fuente cae en un holdout y 'read' no está autorizado: {detalle}.", subject=subject)
            )
        else:
            resultados.append(
                _r(
                    checks.STATUS_PASS,
                    CODE_HOLDOUT_SOURCE,
                    f"La fuente cae en un holdout con holdout_access='read' autorizado ({detalle}); "
                    "la lectura efectiva exige además una excepción vigente en guardrails.json.",
                    subject=subject,
                )
            )
    return resultados


# --- REPORT-ISOLATION-INPUT (R15) ---------------------------------------------


def _manifest_exploratorio_ancestro(repo: Path, config, relativa: str) -> Optional[str]:
    """Ruta relativa del primer `manifest.json` de reporte exploratorio en el
    input (si es directorio) o sus ancestros hasta la raíz del repo; `None` si
    no hay. Ignora manifests ajenos/ilegibles/no JSON y no abre ninguno cuya
    lectura `pathguard` deniegue."""
    repo_res = repo.resolve()
    partes = PurePosixPath(relativa).parts
    try:
        es_dir = (repo_res / relativa).is_dir()
    except OSError:
        es_dir = False
    n = len(partes) if es_dir else max(len(partes) - 1, 0)
    for k in range(n, -1, -1):
        dir_rel = "/".join(partes[:k])
        manifest_rel = f"{dir_rel}/{reporting_core.MANIFEST_FILENAME}" if dir_rel else reporting_core.MANIFEST_FILENAME
        ruta_abs = repo_res / manifest_rel
        try:
            if not ruta_abs.is_file():
                continue
        except OSError:
            continue
        permitido, _ = _decision("Read", str(ruta_abs), None, config, repo_res)
        if not permitido:
            continue
        try:
            datos = json.loads(ruta_abs.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if (
            isinstance(datos, dict)
            and "report_id" in datos
            and "decision_scope" in datos
            and datos["decision_scope"] == _SCOPE_EXPLORATORY
        ):
            return manifest_rel
    return None


def _formas_root(repo: Path, root: str) -> list:
    """Formas comparables de un root: textual y resuelta (sigue symlinks/junctions)."""
    formas = [root]
    resuelta, dentro = pathguard.resolver_ruta_relativa(root, repo)
    if dentro and resuelta is not None and resuelta not in formas:
        formas.append(resuelta)
    return formas


def _evaluar_input(repo: Path, policy: ReportingPolicy, config, entrada: Any) -> checks.CheckResult:
    subject = _subject(entrada)
    if not _string_no_vacio(entrada):
        return _r(checks.STATUS_FAIL, CODE_ISOLATION_INPUT, "El input debe ser un string no vacío (no verificable).", subject=subject)
    if any(c in _METACARACTERES_FNMATCH for c in entrada):
        return _r(
            checks.STATUS_FAIL,
            CODE_ISOLATION_INPUT,
            "El input contiene metacaracteres de glob (* ? [ ]): no verificable (fail-closed).",
            subject=subject,
        )
    relativa, dentro = pathguard.resolver_ruta_relativa(entrada, repo)
    if not dentro:
        return _r(
            checks.STATUS_FAIL,
            CODE_ISOLATION_INPUT,
            "Input fuera del repo o no resoluble: no se puede verificar su origen (fail-closed).",
            subject=subject,
        )
    if relativa == ".":
        return _r(
            checks.STATUS_FAIL,
            CODE_ISOLATION_INPUT,
            "El input es la raíz del repo: contiene el root exploratory (ancestro); no verificable.",
            subject=subject,
        )
    root_exploratory = policy.destination_roots[_SCOPE_EXPLORATORY]
    for forma in _formas_root(repo, root_exploratory):
        if _anidados_o_iguales(relativa, forma):
            return _r(
                checks.STATUS_FAIL,
                CODE_ISOLATION_INPUT,
                f"El input {relativa!r} es igual a, cae bajo o es ancestro del root exploratory ({forma!r}): "
                "un output exploratorio no puede alimentar model_valid/operational.",
                subject=subject,
            )
    manifest = _manifest_exploratorio_ancestro(repo, config, relativa)
    if manifest is not None:
        return _r(
            checks.STATUS_FAIL,
            CODE_ISOLATION_INPUT,
            f"El input cae bajo un reporte exploratorio (manifest {manifest!r} con decision_scope='exploratory').",
            subject=subject,
        )
    return _r(
        checks.STATUS_PASS,
        CODE_ISOLATION_INPUT,
        "Sin señales de origen exploratorio (root/manifest ancestro); el chequeo por hash queda diferido al Change 3.",
        subject=subject,
    )


def _check_aislamiento(repo: Path, flow_scope: Any, inputs: Any, policy: ReportingPolicy) -> list:
    if flow_scope not in reporting_core.DECISION_SCOPES:
        return [
            _r(
                checks.STATUS_FAIL,
                CODE_ISOLATION_INPUT,
                f"flow_scope {flow_scope!r} fuera de {reporting_core.DECISION_SCOPES}.",
            )
        ]
    entradas = _secuencia(inputs)
    if entradas is None:
        return [_r(checks.STATUS_FAIL, CODE_ISOLATION_INPUT, "inputs debe ser una lista o tupla de rutas.")]
    if not entradas:
        return [_r(checks.STATUS_NA, CODE_ISOLATION_INPUT, "Sin inputs declarados.")]
    if flow_scope == _SCOPE_EXPLORATORY:
        return [
            _r(
                checks.STATUS_NA,
                CODE_ISOLATION_INPUT,
                "El flujo exploratorio puede leer cualquier output.",
                subject=_subject(e),
            )
            for e in entradas
        ]
    config, error = _cargar_config(repo)
    if error is not None:
        return [
            _fail_tecnico(CODE_ISOLATION_INPUT, f"guardrails.json corrupto (fail-closed): {error}", subject=_subject(e))
            for e in entradas
        ]
    return [_evaluar_input(repo, policy, config, e) for e in entradas]


def _check_flow_inputs_publico(repo_root: Any, flow_scope: Any, inputs: Any) -> list:
    policy, resultado_policy = _cargar_policy_resultado(repo_root)
    if policy is None:
        return [resultado_policy]
    return _check_aislamiento(_como_path(repo_root), flow_scope, inputs, policy)


def check_flow_inputs(repo_root: Any, flow_scope: Any, inputs: Any) -> list:
    """Un `CheckResult` `REPORT-ISOLATION-INPUT` por input. Nunca lanza."""
    return checks.ejecutar_checks(
        [(CODE_ISOLATION_INPUT, _check_flow_inputs_publico, (repo_root, flow_scope, inputs))]
    )


# --- REPORT-SCI-CUTOFF (R16) --------------------------------------------------


def _parsear_declaracion(valor: Any) -> datetime:
    """`YYYY-MM-DD` (=> T00:00:00Z) o `YYYY-MM-DDTHH:MM:SSZ`; otro formato => ValueError."""
    if not isinstance(valor, str):
        raise ValueError(f"no es un string: {valor!r}")
    try:
        return dsguard_core.parsear_utc(valor)
    except ValueError:
        if len(valor) != 10:
            raise
        return datetime.strptime(valor, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def _check_sci_cutoff(ctx: GovernanceContext, repo: Path) -> list:
    try:
        policy = scientific_validity.leer_policy(repo)
    except scientific_validity.ScientificPolicyError as exc:
        return [_fail_tecnico(CODE_SCI_CUTOFF, f"Policy científica inválida (SCI-POLICY): {exc}")]
    temporal = policy.get("temporal")
    if not isinstance(temporal, dict) or temporal.get("declared") is not True:
        return [_r(checks.STATUS_NA, CODE_SCI_CUTOFF, "La policy científica no declara temporal: sin cutoff que comparar.")]
    cutoff_bruto = temporal.get("cutoff_utc")
    if not cutoff_bruto:
        return [
            _r(
                checks.STATUS_WARN,
                CODE_SCI_CUTOFF,
                "temporal.declared=true pero sin cutoff_utc en la policy científica: no se puede comparar.",
            )
        ]
    try:
        cutoff = dsguard_core.parsear_utc(cutoff_bruto)
    except (ValueError, TypeError):
        return [
            _r(
                checks.STATUS_FAIL,
                CODE_SCI_CUTOFF,
                f"temporal.cutoff_utc con formato inválido ({cutoff_bruto!r}); se esperaba YYYY-MM-DDTHH:MM:SSZ.",
            )
        ]
    scope = ctx.decision_scope
    if scope not in reporting_core.DECISION_SCOPES:
        return [_r(checks.STATUS_FAIL, CODE_SCI_CUTOFF, f"decision_scope {scope!r} fuera de {reporting_core.DECISION_SCOPES}.")]
    declarado = ctx.data_cutoff
    exploratorio = scope == _SCOPE_EXPLORATORY
    if declarado is None or declarado == "":
        estado = checks.STATUS_WARN if exploratorio else checks.STATUS_FAIL
        return [
            _r(
                estado,
                CODE_SCI_CUTOFF,
                f"El reporte {scope!r} no declara data_cutoff y la policy tiene cutoff_utc={cutoff_bruto}.",
            )
        ]
    try:
        fecha = _parsear_declaracion(declarado)
    except (ValueError, TypeError):
        return [
            _r(
                checks.STATUS_FAIL,
                CODE_SCI_CUTOFF,
                f"data_cutoff con formato inválido ({declarado!r}); se esperaba YYYY-MM-DD o YYYY-MM-DDTHH:MM:SSZ.",
            )
        ]
    if fecha <= cutoff:
        return [
            _r(
                checks.STATUS_PASS,
                CODE_SCI_CUTOFF,
                f"data_cutoff {declarado} <= cutoff_utc {cutoff_bruto}.",
            )
        ]
    if exploratorio:
        return [
            _r(
                checks.STATUS_WARN,
                CODE_SCI_CUTOFF,
                f"El output exploratorio cubre datos posteriores al cutoff de modelado (data_cutoff {declarado} > "
                f"cutoff_utc {cutoff_bruto}) y NO debe alimentar model_valid.",
            )
        ]
    return [
        _r(
            checks.STATUS_FAIL,
            CODE_SCI_CUTOFF,
            f"data_cutoff {declarado} posterior a cutoff_utc {cutoff_bruto}: un reporte {scope!r} no puede cubrir datos posteriores al cutoff.",
        )
    ]


# --- Agregador / output guard (R17) -------------------------------------------


def _evaluar(ctx: Any, completo: bool) -> list:
    try:
        if not isinstance(ctx, GovernanceContext):
            raise TypeError(f"ctx debe ser un GovernanceContext, no {type(ctx).__name__}")
        policy, resultado_policy = _cargar_policy_resultado(ctx.repo_root)
        if policy is None:
            return [resultado_policy]
        repo = _como_path(ctx.repo_root)
        registros = [
            (CODE_DEST_SAFE, _check_dest_safe, (ctx, repo)),
            (CODE_DEST_SCOPE, _check_dest_scope, (ctx, policy, repo)),
            (CODE_SENSITIVE_DEST, _check_sensitive_dest, (ctx, policy, repo)),
        ]
        if completo:
            registros += [
                (CODE_SOURCE_ACCESS, _check_source_access, (ctx, repo)),
                (CODE_HOLDOUT_ACCESS, _check_holdout_access, (ctx, repo)),
                (CODE_HOLDOUT_SOURCE, _check_holdout_source, (ctx, repo)),
                (CODE_ISOLATION_INPUT, _check_aislamiento, (repo, ctx.decision_scope, ctx.sources, policy)),
                (CODE_SCI_CUTOFF, _check_sci_cutoff, (ctx, repo)),
            ]
        return [resultado_policy] + checks.ejecutar_checks(registros)
    except Exception as exc:  # noqa: BLE001 - nunca debe escapar
        return [checks.resultado_de_excepcion(_CODE_GOVERNANCE_BASE, exc)]


def evaluate_destination(ctx: GovernanceContext) -> list:
    """`REPORT-POLICY`, `REPORT-DEST-SAFE`, `REPORT-DEST-SCOPE`,
    `REPORT-SENSITIVE-DEST`, en ese orden. Nunca lanza."""
    return _evaluar(ctx, completo=False)


def evaluate_governance(ctx: GovernanceContext) -> list:
    """Los cuatro checks de destino y luego fuentes, holdout, aislamiento y
    cutoff. Si la policy de reporting no carga, devuelve solo su FAIL. Nunca lanza."""
    return _evaluar(ctx, completo=True)


def output_allowed(results: Any, *, require_codes: Any = ()) -> bool:
    """`True` sii no hay ningún FAIL (WARN y N/A no bloquean) y, si
    `require_codes` no está vacío, cada código requerido aparece en `results`.
    `[]` es `True` salvo que se pidan `require_codes` (entonces `False`: "no se
    evaluó nada" no es permitido). Un `publish` debe pasar
    `require_codes=REQUIRED_DESTINATION_CODES`. Ante una entrada que no es una
    lista de `CheckResult` devuelve `False` (fail-closed)."""
    try:
        if checks.hay_bloqueo(results):
            return False
        requeridos = (require_codes,) if isinstance(require_codes, str) else tuple(require_codes)
        if requeridos:
            presentes = {r.code for r in results}
            return all(codigo in presentes for codigo in requeridos)
        return True
    except Exception:  # noqa: BLE001 - nunca debe escapar
        return False

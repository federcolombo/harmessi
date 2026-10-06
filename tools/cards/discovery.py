"""Discovery y validación de proyecto de las Cards de governance (Change
`20261005-cards-governance-integration`, R17-R23, R44-R49; contrato D).

- `descubrir(repo_root)`: solo las rutas conocidas (R19), no recursivo, orden
  lexicográfico por nombre de archivo. Un symlink o un `.json` que no es archivo
  regular se lista (para que `validar_proyecto` lo marque inválido); jamás se omite
  en silencio. Subdirectorios y archivos no `.json` se ignoran.
- `validar_proyecto(...)`: evalúa cada Card con el evaluador de su kind, con
  `anchor_verifier` real y (assessments) `ProjectGovernance` resuelto UNA vez. Nunca
  lanza: ilegible/malformado/incoherente -> `CardReport(status="invalid")`.
- Los imports de `modelcard`, `modelgov`, `govconfig` y `approvals` son perezosos y por
  kind: un proyecto con solo Data Cards no los necesita.
- Solo lectura. Salida con rutas relativas y texto de usuario sin caracteres de
  control y truncado (R49).
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Optional

try:  # import dual: paquete (`tools.cards`) o módulo suelto con `tools/cards` en sys.path
    from . import assess, core
except ImportError:  # pragma: no cover - ejecución sin paquete padre
    import assess  # type: ignore[no-redef]
    import core  # type: ignore[no-redef]

KIND_DATA = "data"
KIND_MODEL = "model"
KIND_GOVERNANCE = "governance"
KINDS = (KIND_DATA, KIND_MODEL, KIND_GOVERNANCE)

# Directorios conocidos (R19), en el orden de salida de `descubrir`.
DIRS_CONOCIDOS = (
    (KIND_DATA, "governance/cards/data"),
    (KIND_MODEL, "governance/cards/model"),
    (KIND_GOVERNANCE, "governance/model-risk"),
)
_KIND_DE_CARD_KIND = {
    "data_card": KIND_DATA,
    "model_card": KIND_MODEL,
    "governance_assessment": KIND_GOVERNANCE,
}
_CODE_IDENTITY = {
    KIND_DATA: "DATACARD-IDENTITY-MISMATCH",
    KIND_MODEL: "MODELCARD-IDENTITY-MISMATCH",
    KIND_GOVERNANCE: "GOVASSESS-IDENTITY-MISMATCH",
}
_CODE_KIND = {
    KIND_DATA: "DATACARD-KIND-INVALID",
    KIND_MODEL: "MODELCARD-KIND-INVALID",
    KIND_GOVERNANCE: "GOVASSESS-KIND-INVALID",
}
CODE_NOT_REGULAR = "CARD-PATH-NOT-REGULAR"
CODE_OUTSIDE_REPO = "CARD-PATH-OUTSIDE-REPO"
CODE_EVALUATION_FAILED = "CARD-EVALUATION-FAILED"
KIND_DESCONOCIDO = "unknown"

MAX_TEXTO = 200
_RE_RUTA_ABSOLUTA = re.compile(r"(?:(?<![A-Za-z0-9])[A-Za-z]:[\\/](?![\\/])[^\s\"'<>|]*|/(?:Users|home)/[^\s\"'<>|]*)")
_RE_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f  ​-‏‪-‮⁦-⁩]")
_ATRIBUTO_REPARSE_POINT = 0x400

NOTA_COMPLETENESS_FALLBACK = (
    "complete NO equivale a aprobación ética, de justicia, seguridad, privacidad, "
    "explicabilidad, cumplimiento ni aptitud para producción"
)


# ---------------------------------------------------------------------------
# Tipos
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DiscoveredCard:
    kind: str
    rel_path: str


@dataclass(frozen=True)
class CardReport:
    kind: str
    rel_path: str
    card_id: str
    revision_id: str
    status: str
    requirements: tuple = ()
    evidence: tuple = ()
    anchors: tuple = ()
    policy: Optional[dict] = None
    findings: tuple = ()
    check_results: tuple = ()


@dataclass(frozen=True)
class ProjectValidation:
    reports: tuple = ()
    governance: Any = None
    notes: tuple = ()


# ---------------------------------------------------------------------------
# Higiene (R49)
# ---------------------------------------------------------------------------


def limpiar_texto(valor: Any, repo_root: Any = None, maximo: int = MAX_TEXTO) -> str:
    """Texto de usuario seguro para salida: sin caracteres de control, sin la ruta
    absoluta del repo y truncado."""
    texto = valor if isinstance(valor, str) else str(valor)
    if repo_root is not None:
        for forma in {str(repo_root), Path(repo_root).as_posix()}:
            if forma:
                texto = texto.replace(forma, "<repo>")
    # Rutas absolutas de OTRO origen (p. ej. `C:\Users\<usuario>\...`, `/home/<usuario>/...`) que
    # un texto de usuario no validado por portabilidad pueda traer (R49/R71).
    texto = _RE_RUTA_ABSOLUTA.sub("<ruta>", texto)
    texto = _RE_CONTROL.sub(" ", texto)
    if len(texto) > maximo:
        texto = texto[: maximo - 3] + "..."
    return texto


def _es_enlace(ruta: Path) -> bool:
    try:
        if ruta.is_symlink():
            return True
        return bool(getattr(os.lstat(ruta), "st_file_attributes", 0) & _ATRIBUTO_REPARSE_POINT)
    except OSError:
        return False


def _es_archivo_regular(ruta: Path) -> bool:
    try:
        return not _es_enlace(ruta) and ruta.is_file()
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Discovery (R19)
# ---------------------------------------------------------------------------


def descubrir(repo_root: Any) -> list:
    """`list[DiscoveredCard]`: rutas conocidas, no recursivo, orden determinista
    (dirs en el orden de `DIRS_CONOCIDOS`, nombres lexicográficos). Nunca lanza."""
    repo = Path(repo_root)
    salida: list = []
    for kind, rel_dir in DIRS_CONOCIDOS:
        directorio = repo.joinpath(*rel_dir.split("/"))
        # I-3: un directorio de Cards (o un padre) que es symlink/junction es un hallazgo
        # explícito (se lista el directorio; `validar_proyecto` lo marca inválido).
        if _ruta_con_enlace(repo, directorio):
            salida.append(DiscoveredCard(kind, rel_dir))
            continue
        try:
            if not directorio.is_dir():
                continue
            nombres = sorted(e.name for e in os.scandir(directorio) if _es_candidato(e))
        except OSError:
            continue
        for nombre in nombres:
            salida.append(DiscoveredCard(kind, f"{rel_dir}/{nombre}"))
    # `governance/policy` (documento de hardening, R22): si es un enlace, también es un hallazgo.
    politica = repo.joinpath("governance", "policy")
    if _ruta_con_enlace(repo, politica) and not any(d.rel_path == "governance" for d in salida):
        salida.append(DiscoveredCard(KIND_GOVERNANCE, "governance/policy"))
    return salida


def _ruta_con_enlace(repo: Path, ruta: Path) -> bool:
    """`True` si algún componente de `ruta` por debajo de `repo` (incluida `ruta`) es un
    symlink/junction."""
    try:
        relativa = Path(os.path.normpath(ruta)).relative_to(Path(os.path.normpath(repo)))
    except ValueError:
        return False
    actual = Path(os.path.normpath(repo))
    for parte in relativa.parts:
        actual = actual / parte
        if _es_enlace(actual):
            return True
    return False


def _es_candidato(entrada: Any) -> bool:
    """`.json` que no es un subdirectorio real (symlinks y no-regulares sí cuentan)."""
    if not entrada.name.endswith(".json"):
        return False
    try:
        if entrada.is_symlink():
            return True
        return not entrada.is_dir(follow_symlinks=False)
    except OSError:
        return True


# ---------------------------------------------------------------------------
# Capabilities (R12, R45)
# ---------------------------------------------------------------------------

_CAPS_HISTORICAS = ("predictive_modeling",)


def estado_capabilities(control_data: Optional[dict]) -> dict:
    """Interpreta `capabilities_habilitadas` de `.ds_init/control.json` (R12): ausente
    (o control `None`) = capabilities históricas habilitadas y opt-in DESHABILITADAS;
    lista presente = literal. Claves: habilitadas (frozenset), data_cards,
    model_governance, predictive_modeling, legacy, invalida (list[str])."""
    invalida: list = []
    lista = control_data.get("capabilities_habilitadas") if isinstance(control_data, dict) else None
    legacy = lista is None
    if lista is not None and (not isinstance(lista, (list, tuple)) or not all(isinstance(c, str) for c in lista)):
        invalida.append("capabilities_habilitadas debe ser una lista de textos")
        lista, legacy = None, True
    habilitadas = frozenset(_CAPS_HISTORICAS) if lista is None else frozenset(lista)
    invalida.extend(_validar_capabilities(sorted(habilitadas)))
    return {
        "habilitadas": habilitadas,
        "data_cards": "data_cards" in habilitadas,
        "model_governance": "model_governance" in habilitadas,
        "predictive_modeling": "predictive_modeling" in habilitadas,
        "legacy": legacy,
        "invalida": invalida,
    }


def _validar_capabilities(caps: list) -> list:
    """`ds_init.manifest.validar_capabilities` si está disponible; si no, la regla
    mínima (model_governance exige predictive_modeling)."""
    for ruta in ("tools.ds_init.manifest", "ds_init.manifest"):
        try:
            modulo = __import__(ruta, fromlist=["manifest"])
            return list(modulo.validar_capabilities(caps))
        except Exception:  # noqa: BLE001 - degradación con gracia
            continue
    if "model_governance" in caps and "predictive_modeling" not in caps:
        return ["model_governance requiere predictive_modeling"]
    return []


# ---------------------------------------------------------------------------
# Imports perezosos por kind
# ---------------------------------------------------------------------------


def _importar(nombre: str) -> Any:
    """Import perezoso de un módulo hermano de `cards`. Falla -> `ImportError`."""
    try:
        return __import__(f"{__package__}.{nombre}" if __package__ else nombre, fromlist=[nombre])
    except ImportError:
        return __import__(nombre, fromlist=[nombre])


@dataclass(frozen=True)
class _ResolucionSintetica:
    """Equivalente estructural de `approvals.AnchorResolution` para el caso fail-closed
    en que `approvals` no se puede importar."""

    state: str = "unresolvable"
    detail: str = "verificador de anclas no disponible"
    change_id: Optional[str] = None
    artefacto: Optional[str] = None
    usuario: Optional[str] = None
    fecha_declarada: Optional[str] = None


@dataclass(frozen=True)
class _GobiernoNoResuelto:
    """Equivalente estructural de `govconfig.ProjectGovernance(state="unresolvable")`
    para el caso fail-closed en que `govconfig` no se puede importar."""

    state: str
    findings: tuple
    project_hardening_path: Optional[str] = None
    project_hardening_sha256: Optional[str] = None
    local_hardening_present: bool = False
    effective: Any = None
    effective_sha256: Optional[str] = None


def _verificador_sintetico(att: Any) -> Any:
    return _ResolucionSintetica()


def _verificador_ancla(repo_root: Any, notas: list) -> Any:
    """Verificador real; si `approvals` falla, uno sintético que devuelve `unresolvable`
    para todo (nunca se omite el verificador: fail-closed)."""
    try:
        return _importar("approvals").make_anchor_verifier(repo_root)
    except Exception as exc:  # noqa: BLE001
        notas.append(f"verificador de anclas no disponible ({type(exc).__name__}): las atestaciones anchored quedan unresolvable")
        return _verificador_sintetico


def _gobierno_no_resuelto(repo_root: Any, notas: list, exc: BaseException) -> Any:
    """`ProjectGovernance(state="unresolvable")` con GOVCFG-UNRESOLVABLE (adaptador no disponible)."""
    notas.append(f"configuración de governance no disponible ({type(exc).__name__}): policy no resuelta")
    hallazgo = core.Hallazgo("GOVCFG-UNRESOLVABLE", "$", "adaptador de configuración de governance no disponible")
    try:
        clase = _importar("govconfig").ProjectGovernance
        return clase(
            state="unresolvable", project_hardening_path=None, project_hardening_sha256=None,
            local_hardening_present=False, effective=None, effective_sha256=None, findings=(hallazgo,),
        )
    except Exception:  # noqa: BLE001
        return _GobiernoNoResuelto(state="unresolvable", findings=(hallazgo,))


# ---------------------------------------------------------------------------
# Construcción de CardReport
# ---------------------------------------------------------------------------


def _hallazgo_dict(h: Any, repo_root: Any) -> dict:
    if isinstance(h, dict):
        code, path, detail = h.get("code", ""), h.get("path", ""), h.get("detail", "")
    else:
        code, path, detail = getattr(h, "code", ""), getattr(h, "path", ""), getattr(h, "detail", "")
    return {
        "code": limpiar_texto(code, repo_root, 80),
        "path": limpiar_texto(path, repo_root, 120),
        "detail": limpiar_texto(detail, repo_root),
    }


def _invalido(kind: str, rel: str, card_id: str, hallazgos: list, repo_root: Any) -> CardReport:
    """Card inválida antes/sin evaluación: check_results vía `assess.a_check_results`."""
    hs = tuple(core.Hallazgo(c, p, d) for c, p, d in hallazgos)
    ca = assess.CardAssessment(card_status=assess.CARD_INVALID, hallazgos=hs, sin_requisitos=True, card_id=card_id)
    try:
        resultados = _sanear_checks(assess.a_check_results(ca), repo_root)
    except Exception:  # noqa: BLE001
        resultados = ()
    return CardReport(
        kind=kind,
        rel_path=rel,
        card_id=limpiar_texto(card_id, repo_root, 64),
        revision_id="",
        status=assess.CARD_INVALID,
        findings=tuple(_hallazgo_dict(h, repo_root) for h in hs),
        check_results=resultados,
    )


def _hash12(valor: Any) -> str:
    return valor[:12] if isinstance(valor, str) else ""


def _evidencias(card: Any, estados: Any, repo_root: Any) -> tuple:
    mapa = dict(estados)
    filas = []
    for e in sorted(card.evidence, key=lambda x: x.evidence_id):
        filas.append(
            {
                "evidence_id": limpiar_texto(e.evidence_id, repo_root, 64),
                "kind": limpiar_texto(e.kind, repo_root, 64),
                "ref_id": limpiar_texto(e.ref_id, repo_root, 120),
                "hash12": _hash12(e.content_sha256),
                "state": mapa.get(e.evidence_id, "unverifiable"),
            }
        )
    return tuple(filas)


def _opc(valor: Any, repo_root: Any) -> Optional[str]:
    return None if valor is None else limpiar_texto(valor, repo_root, 120)


def _sanear_checks(resultados: Any, repo_root: Any) -> tuple:
    """CheckResult con `message`/`detail`/`subject` sin controles, sin ruta absoluta y truncados."""
    salida = []
    for r in resultados:
        try:
            mensaje = limpiar_texto(r.message, repo_root, 400).strip() or r.code
            detalle = limpiar_texto(r.detail, repo_root) if r.detail else r.detail
            sujeto = limpiar_texto(r.subject, repo_root, 120) if r.subject else r.subject
            salida.append(replace(r, message=mensaje, detail=detalle, subject=sujeto))
        except Exception:  # noqa: BLE001
            salida.append(r)
    return tuple(salida)


def _anclas(card: Any, verificador: Any, repo_root: Any) -> tuple:
    filas = []
    for a in sorted(card.attestations, key=lambda x: x.attestation_id):
        if a.attestation_kind != "anchored":
            continue
        fila = {"attestation_id": limpiar_texto(a.attestation_id, repo_root, 64), "state": "unresolvable", "detail": ""}
        if verificador is None:  # defensivo: `validar_proyecto` nunca lo deja en None
            verificador = _verificador_sintetico
        try:
            r = verificador(a)
            # No se emite `usuario` (puede ser un nombre de usuario del sistema; M-4).
            fila.update(
                {
                    "state": limpiar_texto(getattr(r, "state", "unresolvable"), repo_root, 32),
                    "detail": limpiar_texto(getattr(r, "detail", ""), repo_root),
                    "change_id": _opc(getattr(r, "change_id", None), repo_root),
                    "artefacto": _opc(getattr(r, "artefacto", None), repo_root),
                    "fecha_declarada": _opc(getattr(r, "fecha_declarada", None), repo_root),
                }
            )
        except Exception as exc:  # noqa: BLE001
            fila["detail"] = f"verificador falló ({type(exc).__name__})"
        filas.append(fila)
    return tuple(filas)


def _evaluar_card(kind: str, ruta: Path, rel: str, card: Any, repo_root: Any, ctx: dict) -> CardReport:
    if kind not in KINDS:  # defensivo (M-3): nunca se evalúa un kind desconocido
        raise ValueError("kind desconocido")
    verificador = ctx["verificador"]()
    kwargs = {"anchor_verifier": verificador}
    anclas = _anclas(card, verificador, repo_root)
    if kind == KIND_DATA:
        datacard = _importar("datacard")
        ca = datacard.evaluate_data_card(ruta, repo_root, **kwargs)
        resultados = _sanear_checks(assess.a_check_results(ca), repo_root)
        return _desde_card_assessment(kind, rel, card, ca, anclas, resultados, repo_root)
    if kind == KIND_MODEL:
        modelcard = _importar("modelcard")
        ca = modelcard.evaluate_model_card(ruta, repo_root, **kwargs)
        resultados = _sanear_checks(assess.a_check_results(ca), repo_root)
        return _desde_card_assessment(kind, rel, card, ca, anclas, resultados, repo_root)
    modelgov = _importar("modelgov")
    gov = ctx["governance"]()
    ga = modelgov.evaluate_governance_assessment(ruta, repo_root, governance=gov, **kwargs)
    resultados = _sanear_checks(modelgov.a_check_results(ga), repo_root)
    policy = {
        "declared_level": ga.declared_level,
        "effective_level": ga.effective_level,
        "risk_floor": ga.risk_floor,
        "policy": _json_seguro(ga.policy, repo_root),
        "dimensiones": [
            {"dimension": d[0], "estado": d[1], "requisitos": list(d[2])} for d in ga.dimensiones
        ],
        "config_state": getattr(gov, "state", None),
        "config_findings": [_hallazgo_dict(h, repo_root) for h in (getattr(gov, "findings", ()) or ())],
        "nota": getattr(modelgov, "NOTA_COMPLETENESS", NOTA_COMPLETENESS_FALLBACK),
    }
    reqs = tuple(
        {
            "requirement_id": r[0],
            "severity": r[1],
            "dimension": r[2],
            "state": r[3],
            "detail": limpiar_texto(r[4], repo_root),
        }
        for r in ga.requisitos
    )
    return CardReport(
        kind=kind,
        rel_path=rel,
        card_id=limpiar_texto(ga.card_id or card.card_id, repo_root, 64),
        revision_id=card.revision_id(),
        status=ga.governance_completeness,
        requirements=reqs,
        evidence=_evidencias(card, ga.evidencias, repo_root),
        anchors=anclas,
        policy=policy,
        findings=tuple(_hallazgo_dict(h, repo_root) for h in ga.hallazgos),
        check_results=resultados,
    )


def _json_seguro(valor: Any, repo_root: Any) -> Any:
    if isinstance(valor, dict):
        return {str(k): _json_seguro(valor[k], repo_root) for k in sorted(valor, key=str)}
    if isinstance(valor, (list, tuple)):
        return [_json_seguro(v, repo_root) for v in valor]
    if isinstance(valor, str):
        return limpiar_texto(valor, repo_root)
    if valor is None or isinstance(valor, (bool, int, float)):
        return valor
    return limpiar_texto(valor, repo_root)


def _desde_card_assessment(kind, rel, card, ca, anclas, resultados, repo_root) -> CardReport:
    reqs = tuple(
        {"requirement_id": r[0], "severity": r[1], "state": r[2], "detail": limpiar_texto(r[3], repo_root)}
        for r in ca.requisitos
    )
    return CardReport(
        kind=kind,
        rel_path=rel,
        card_id=limpiar_texto(ca.card_id or card.card_id, repo_root, 64),
        revision_id=card.revision_id(),
        status=ca.card_status,
        requirements=reqs,
        evidence=_evidencias(card, ca.evidencias, repo_root),
        anchors=anclas,
        findings=tuple(_hallazgo_dict(h, repo_root) for h in ca.hallazgos),
        check_results=resultados,
    )


# ---------------------------------------------------------------------------
# validar_proyecto
# ---------------------------------------------------------------------------


def _kind_por_ubicacion(rel: str) -> Optional[str]:
    padre = rel.rsplit("/", 1)[0] if "/" in rel else ""
    for kind, rel_dir in DIRS_CONOCIDOS:
        if padre == rel_dir:
            return kind
    return None


def _resolver_ruta(repo: Path, valor: Any) -> tuple:
    """`(ruta_fisica, rel_posix)`; `rel_posix=None` si cae fuera del repo."""
    try:
        p = Path(valor)
        if not p.is_absolute():
            p = repo / p
        p = Path(os.path.normpath(p))
        rel = p.relative_to(Path(os.path.normpath(repo))).as_posix()
        return p, rel
    except (ValueError, TypeError, OSError):
        nombre = Path(str(valor)).name if valor else ""
        return None, f"<fuera-del-repo>/{limpiar_texto(nombre, None, 80)}"


def _validar_una(kind_esperado: Optional[str], ruta: Optional[Path], rel: str, repo: Path, ctx: dict, notas: list) -> CardReport:
    kind_prov = kind_esperado or KIND_DESCONOCIDO
    if ruta is None:
        return _invalido(kind_prov, rel, "", [(CODE_OUTSIDE_REPO, "file", "la ruta cae fuera del repo")], repo)
    if _ruta_con_enlace(repo, ruta) or not _es_archivo_regular(ruta):
        return _invalido(
            kind_prov, rel, "",
            [(CODE_NOT_REGULAR, "file", "no es un archivo regular (symlink/junction en la ruta, ausente o directorio)")], repo,
        )
    try:
        card = assess.read_card(ruta)
    except core.CardError as exc:
        return _invalido(kind_prov, rel, "", [(exc.code, "file", exc.message)], repo)
    except Exception as exc:  # noqa: BLE001
        return _invalido(kind_prov, rel, "", [(CODE_EVALUATION_FAILED, "file", f"lectura falló ({type(exc).__name__})")], repo)

    kind_real = _KIND_DE_CARD_KIND.get(card.card_kind, KIND_DESCONOCIDO)
    if kind_real == KIND_DESCONOCIDO:  # M-3: nunca se evalúa (ni pasa por modelgov)
        return _invalido(
            kind_prov, rel, card.card_id,
            [("CARD-KIND-INVALID", "card_kind", f"card_kind desconocido: {limpiar_texto(card.card_kind, repo, 60)}")], repo,
        )
    if kind_esperado is not None:
        if kind_real != kind_esperado:
            return _invalido(
                kind_esperado, rel, card.card_id,
                [(_CODE_KIND[kind_esperado], "card_kind", f"el directorio espera {kind_esperado}, la Card es {card.card_kind}")],
                repo,
            )
        if ruta.stem != card.card_id:
            return _invalido(
                kind_esperado, rel, card.card_id,
                [(_CODE_IDENTITY[kind_esperado], "card_id", "el nombre de archivo debe ser <card_id>.json")],
                repo,
            )
    try:
        return _evaluar_card(kind_real, ruta, rel, card, repo, ctx)
    except Exception as exc:  # noqa: BLE001 - nunca lanza
        return _invalido(
            kind_real, rel, card.card_id,
            [(CODE_EVALUATION_FAILED, "$", f"evaluación falló ({type(exc).__name__}): {limpiar_texto(exc, repo, 120)}")],
            repo,
        )


def validar_proyecto(repo_root: Any, kinds: Any = None, paths: Any = None) -> ProjectValidation:
    """Valida Cards. Sin `paths`: discovery R19 (filtrado por `kinds`). Con `paths`: cada
    archivo según su `card_kind` (fuera de las rutas conocidas se acepta con una nota de
    ubicación). Nunca lanza."""
    repo = Path(repo_root)
    filtro = set(kinds) if kinds else None
    notas: list = []
    cache: dict = {}

    def _verificador():
        if "v" not in cache:
            cache["v"] = _verificador_ancla(repo, notas)
        return cache["v"]

    def _governance():
        if "g" not in cache:
            try:
                cache["g"] = _importar("govconfig").resolve_project_governance(repo)
            except Exception as exc:  # noqa: BLE001
                cache["g"] = _gobierno_no_resuelto(repo, notas, exc)
        return cache["g"]

    ctx = {"verificador": _verificador, "governance": _governance}
    reportes: list = []
    if paths:
        for valor in paths:
            ruta, rel = _resolver_ruta(repo, valor)
            esperado = _kind_por_ubicacion(rel) if ruta is not None else None
            if ruta is not None and esperado is None:
                notas.append(f"{rel}: fuera de las rutas conocidas de governance; se valida según su card_kind")
            reporte = _validar_una(esperado, ruta, rel, repo, ctx, notas)
            if filtro is None or reporte.kind in filtro or reporte.kind == KIND_DESCONOCIDO:
                reportes.append(reporte)
    else:
        for item in descubrir(repo):
            if filtro is not None and item.kind not in filtro:
                continue
            ruta = repo.joinpath(*item.rel_path.split("/"))
            reportes.append(_validar_una(item.kind, ruta, item.rel_path, repo, ctx, notas))
    return ProjectValidation(
        reports=tuple(reportes),
        governance=cache.get("g"),
        notes=tuple(limpiar_texto(n, repo) for n in notas),
    )


# ---------------------------------------------------------------------------
# Serialización (R48)
# ---------------------------------------------------------------------------


def report_a_dict(card_report: CardReport) -> dict:
    """JSON-safe, rutas relativas, sin `check_results` (se serializan aparte)."""
    return {
        "kind": card_report.kind,
        "rel_path": card_report.rel_path,
        "card_id": card_report.card_id,
        "revision_id": card_report.revision_id,
        "status": card_report.status,
        "requirements": [dict(r) for r in card_report.requirements],
        "evidence": [dict(e) for e in card_report.evidence],
        "anchors": [dict(a) for a in card_report.anchors],
        "policy": _json_seguro(card_report.policy, None) if card_report.policy is not None else None,
        "findings": [dict(h) for h in card_report.findings],
    }

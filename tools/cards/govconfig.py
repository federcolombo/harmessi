"""Configuración efectiva de governance de proyecto (v0.9 Change 4,
`20261005-cards-governance-integration`, R24-R33).

Resuelve el contexto ACTUAL de la policy de riesgo de modelo a partir de dos rutas
fijas (R33): el documento de endurecimiento versionado
`governance/policy/model-risk-hardening.json` (`HardeningDocument`) y la capa local no
versionada `.harmessi/local-overrides.json`, clave `model_risk_hardening`.

    effective = merge(merge(BASE, proyecto), local)      (apilado, todo-o-nada)

Estados (`ProjectGovernance.state`):

- `none`: ninguna capa con hardening (policy efectiva = base).
- `resolved`: al menos una capa válida y la composición es monótona.
- `invalid`: malformación, relajación, clave desconocida o capa local ilegible/no-objeto en
  cualquier capa. NUNCA se cae a la base (un silencio relajaría la policy).
- `unresolvable`: archivo presente pero no legible/hasheable.

Una capa local que traiga otras claves (p. ej. capabilities) las ignora: la fuente de
verdad de capabilities es solo `control.json`. Solo lectura; `resolve_project_governance`
nunca lanza. Módulo adaptador de Change 4: puede importar `dsguard` en el futuro, hoy es
stdlib + hermanos (`core`, `govpolicy`; `resolvers` perezoso para el hash del pin).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

try:  # import dual: paquete (`tools.cards`) o módulo suelto
    from . import core, govpolicy
except ImportError:  # pragma: no cover - ejecución sin paquete padre
    import core  # type: ignore[no-redef]
    import govpolicy  # type: ignore[no-redef]

Hallazgo = core.Hallazgo

RUTA_HARDENING_PROYECTO = "governance/policy/model-risk-hardening.json"
RUTA_CAPA_LOCAL = ".harmessi/local-overrides.json"
CLAVE_LOCAL = "model_risk_hardening"

CODE_INVALID = "GOVCFG-INVALID"
CODE_RELAXATION = "GOVCFG-RELAXATION"
CODE_UNRESOLVABLE = "GOVCFG-UNRESOLVABLE"
CODE_HARDENING_MISMATCH = "GOVCFG-HARDENING-MISMATCH"
CODE_LOCAL_ACTIVE = "GOVCFG-LOCAL-ACTIVE"
GOVCFG_CODES = (CODE_INVALID, CODE_RELAXATION, CODE_UNRESOLVABLE, CODE_HARDENING_MISMATCH, CODE_LOCAL_ACTIVE)

ESTADOS = ("none", "resolved", "invalid", "unresolvable")

_MAX_BYTES = 4 * 1024 * 1024


@dataclass(frozen=True)
class ProjectGovernance:
    """Contexto actual de governance (inmutable). Ver el docstring del módulo."""

    state: str
    project_hardening_path: Optional[str] = None
    project_hardening_sha256: Optional[str] = None
    local_hardening_present: bool = False
    effective: Optional[govpolicy.EffectivePolicy] = None
    effective_sha256: Optional[str] = None
    findings: tuple = ()


# ---------------------------------------------------------------------------
# Lectura de capas
# ---------------------------------------------------------------------------

_AUSENTE = "ausente"
_ILEGIBLE = "ilegible"      # no se pudo leer (IO) -> unresolvable
_MALFORMADO = "malformado"  # JSON roto / no-objeto -> invalid


def _leer_capa(ruta: Path) -> tuple:
    """`(estado, dict|None, detalle)`. A diferencia de `ds_guard._leer_capa_json`, un JSON
    ilegible o cuya raíz no es objeto NO es `{}`: es `malformado` (paridad en lo demás:
    ausente -> capa vacía)."""
    try:
        if not os.path.lexists(ruta):
            return _AUSENTE, {}, ""
        if ruta.is_symlink():
            return _ILEGIBLE, None, "symlink no seguido"
        if not ruta.is_file():
            return _ILEGIBLE, None, "no es un archivo regular"
        if ruta.stat().st_size > _MAX_BYTES:
            return _ILEGIBLE, None, "excede el tamaño máximo"
        crudo = ruta.read_bytes()
    except OSError as exc:
        return _ILEGIBLE, None, f"error de lectura ({type(exc).__name__})"
    try:
        datos = json.loads(crudo.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError) as exc:
        return _MALFORMADO, None, f"JSON inválido ({type(exc).__name__})"
    if not isinstance(datos, dict):
        return _MALFORMADO, None, "la raíz no es un objeto JSON"
    return "ok", datos, ""


def _hash_documento(datos: Any) -> str:
    try:
        from . import resolvers
    except ImportError:  # pragma: no cover
        import resolvers  # type: ignore[no-redef]
    return resolvers.hash_document(datos)


def _hallazgo_policy(capa: str, exc: Exception) -> list:
    code = getattr(exc, "code", None)
    detalle = f"{capa}: {getattr(exc, 'message', None) or exc}"
    hallazgos = [Hallazgo(CODE_INVALID, capa, detalle)]
    if code == govpolicy.CODE_RELAXATION:
        hallazgos.append(Hallazgo(CODE_RELAXATION, capa, f"{code}: {detalle}"))
    elif code is not None:
        hallazgos[0] = Hallazgo(CODE_INVALID, capa, f"{code}: {detalle}")
    return hallazgos


def _fallo(estado: str, hallazgos: list, local: bool, proj_ruta: Optional[str] = None, proj_sha: Optional[str] = None) -> ProjectGovernance:
    return ProjectGovernance(
        state=estado, project_hardening_path=proj_ruta, project_hardening_sha256=proj_sha,
        local_hardening_present=local, findings=tuple(hallazgos),
    )


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


def resolve_project_governance(repo_root: Any, base: Any = govpolicy.BASE_POLICY) -> ProjectGovernance:
    """Resuelve el contexto actual (R27, R28). Nunca lanza. Precedencia de fallos:
    `invalid` > `unresolvable`; ningún fallo cae a la base."""
    try:
        return _resolver(repo_root, base)
    except Exception as exc:  # fail-closed
        return _fallo("invalid", [Hallazgo(CODE_INVALID, "$", f"resolución falló ({type(exc).__name__})")], False)


def _resolver(repo_root: Any, base: Any) -> ProjectGovernance:
    if not isinstance(base, govpolicy.GovernancePolicy):
        return _fallo("invalid", [Hallazgo(CODE_INVALID, "base", "base debe ser GovernancePolicy")], False)
    raiz = Path(repo_root)
    inv: list = []
    unres: list = []

    # Capa de proyecto (R22).
    doc_proy = None
    ruta_proy: Optional[str] = None
    sha_proy: Optional[str] = None
    est, datos, det = _leer_capa(raiz.joinpath(*RUTA_HARDENING_PROYECTO.split("/")))
    if est == _ILEGIBLE:
        unres.append(Hallazgo(CODE_UNRESOLVABLE, RUTA_HARDENING_PROYECTO, det))
    elif est == _MALFORMADO:
        inv.append(Hallazgo(CODE_INVALID, RUTA_HARDENING_PROYECTO, det))
    elif est == "ok":
        try:
            doc_proy = govpolicy.HardeningDocument.from_dict(datos)
        except govpolicy.GovPolicyError as exc:
            inv.extend(_hallazgo_policy(RUTA_HARDENING_PROYECTO, exc))
        else:
            try:
                sha_proy = _hash_documento(datos)
                ruta_proy = RUTA_HARDENING_PROYECTO
            except Exception as exc:
                doc_proy = None
                unres.append(Hallazgo(CODE_UNRESOLVABLE, RUTA_HARDENING_PROYECTO, f"no hasheable ({type(exc).__name__})"))

    # Capa local (R24, R26): solo la clave `model_risk_hardening`; el resto se ignora.
    doc_local = None
    local_presente = False
    est, datos, det = _leer_capa(raiz.joinpath(*RUTA_CAPA_LOCAL.split("/")))
    if est == _ILEGIBLE:
        unres.append(Hallazgo(CODE_UNRESOLVABLE, RUTA_CAPA_LOCAL, det))
    elif est == _MALFORMADO:
        inv.append(Hallazgo(CODE_INVALID, RUTA_CAPA_LOCAL, det))
    elif est == "ok" and CLAVE_LOCAL in datos:
        local_presente = True
        try:
            doc_local = govpolicy.HardeningDocument.from_dict(datos[CLAVE_LOCAL])
        except govpolicy.GovPolicyError as exc:
            inv.extend(_hallazgo_policy(f"{RUTA_CAPA_LOCAL}#{CLAVE_LOCAL}", exc))

    if inv:
        return _fallo("invalid", inv + unres, local_presente, ruta_proy, sha_proy)
    if unres:
        return _fallo("unresolvable", unres, local_presente, ruta_proy, sha_proy)

    # Composición apilada (R25): base -> proyecto -> local.
    try:
        efectiva = govpolicy.merge(base, doc_proy)
    except govpolicy.GovPolicyError as exc:
        return _fallo("invalid", _hallazgo_policy(RUTA_HARDENING_PROYECTO, exc), local_presente, ruta_proy, sha_proy)
    if doc_local is not None:
        try:
            efectiva = govpolicy.merge(efectiva, doc_local)
        except govpolicy.GovPolicyError as exc:
            return _fallo("invalid", _hallazgo_policy(f"{RUTA_CAPA_LOCAL}#{CLAVE_LOCAL}", exc), local_presente, ruta_proy, sha_proy)
    estado = "none" if (doc_proy is None and doc_local is None) else "resolved"
    return ProjectGovernance(
        state=estado,
        project_hardening_path=ruta_proy,
        project_hardening_sha256=sha_proy,
        local_hardening_present=local_presente,
        effective=efectiva,
        effective_sha256=efectiva.effective_sha256(),
        findings=(),
    )

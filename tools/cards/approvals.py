"""Resolución real de `ApprovalRef` (v0.9 Change 4, R35-R41).

Adaptador entre la Foundation de Cards (que solo valida la FORMA de
`approval_ref = {change_id, artefacto, hash}`) y las aprobaciones registradas en el
`control.json` de un Change de SDD. Reutiliza primitivas de `dsguard`
(`leer_control`, `hash_lf_v1`, `_aprobacion_mas_reciente`); si `dsguard` no es
importable el resultado es `unresolvable` (fail-closed).

Pasos (R35): 1) forma válida; 2) `openspec/changes/<id>/` y, si no existe,
`openspec/archive/<id>/`; 3) `control.json` legible; 4) existe una aprobación con ese
`artefacto` y `hash`; 5) es la MÁS RECIENTE del artefacto; 6) el archivo en disco
hashea (`hash_lf_v1`) al mismo valor.

Estados (R36): `verified`, `stale` (reemplazada o archivo cambiado), `missing` (sin
entrada/archivo para ese artefacto+hash), `unresolvable` (forma inválida, Change
inexistente, `control.json` ilegible, dsguard ausente).

Solo lectura (R41): nunca registra ni modifica aprobaciones. Trust model (R39): un
ancla verificada demuestra «existe una aprobación registrada, aún vigente, de ese
artefacto bajo el trust model de Harmessi»; NO identidad criptográfica, presencia del
usuario, no repudio ni que el contenido aprobado sea el claim de la atestación.
`usuario` / `fecha_declarada` son metadatos informativos: no se comparan ni validan.

Canal / trust tier (Change 20261009, R31-R38): el resultado expone, aditivamente y solo
para estado verified, `approval_channel` y `trust_tier` derivados de la entrada de
aprobación resuelta (coincide con el hash del ref y es la más reciente del artefacto); en
stale/missing/unresolvable van en `None` (un ref viejo no hereda el tier de una aprobación
posterior). Un consumidor debe leer `getattr(res, "trust_tier", None)` y tratar None como
«sin tier verificable». `console_confirmed` exacto +
`channel_version == "console/v1"` -> T1; ausente, desconocido o malformado -> `declared`/T0.
El canal no altera el estado. El `ApprovalRef` nunca declara su tier. Un ancla verificada
puede exponer el tier de la aprobación resuelta pero sigue sin probar identidad. A
`console_confirmed` approval means that a declared approval was accompanied by an
interactive confirmation received through a supported control console for that specific
operation. It does not prove the identity or authorship of the declared user and is not
resistant to a deliberately synthesized local console input.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

try:  # import dual: paquete (`tools.cards`) o módulo suelto
    from . import core
except ImportError:  # pragma: no cover - ejecución sin paquete padre
    import core  # type: ignore[no-redef]

CANAL_DECLARED = "declared"
CANAL_CONSOLE = "console_confirmed"
VERSION_CANAL_CONSOLE = "console/v1"
TIER_T0 = "T0"
TIER_T1 = "T1"

NOTA_ANCHOR = (
    "ancla verificada = existe una aprobación registrada, aún vigente, de ese artefacto "
    "bajo el trust model de Harmessi; puede exponer el trust tier (T0/T1) de la aprobación "
    "resuelta pero NO prueba identidad criptográfica, presencia del "
    "usuario, no repudio ni que el contenido aprobado sea el claim de la atestación. "
    "A `console_confirmed` approval means that a declared approval was accompanied by an "
    "interactive confirmation received through a supported control console for that specific "
    "operation. It does not prove the identity or authorship of the declared user and is not "
    "resistant to a deliberately synthesized local console input."
)

VERIFIED = "verified"
STALE = "stale"
MISSING = "missing"
UNRESOLVABLE = "unresolvable"
ESTADOS = (VERIFIED, STALE, MISSING, UNRESOLVABLE)

_MAX_META = 200


@dataclass(frozen=True)
class AnchorResolution:
    state: str
    detail: str
    change_id: Optional[str] = None
    artefacto: Optional[str] = None
    usuario: Optional[str] = None
    fecha_declarada: Optional[str] = None
    # Aditivos (Change 20261009, R31-R38): derivados de la entrada de aprobación resuelta
    # (la más reciente del artefacto). `None` salvo estado verified.
    approval_channel: Optional[str] = None
    trust_tier: Optional[str] = None

    def __post_init__(self) -> None:
        if not isinstance(self.state, str) or self.state not in ESTADOS:
            raise core.CardError(core.CODE_FIELD_INVALID, f"AnchorResolution.state inválido {self.state!r}")


def _meta(valor: Any) -> Optional[str]:
    """Metadato informativo: str sin caracteres de control, truncado."""
    if not isinstance(valor, str):
        return None
    limpio = "".join(c if c.isprintable() else " " for c in valor)
    return limpio[:_MAX_META]


def _dsguard() -> Any:
    """`(core, sdd)` de dsguard o `None` si no es importable."""
    try:
        tools_dir = str(Path(__file__).resolve().parents[1])
        if tools_dir not in sys.path:
            sys.path.insert(0, tools_dir)
        from dsguard import core as dcore  # noqa: WPS433
        from dsguard import sdd as dsdd  # noqa: WPS433

        return dcore, dsdd
    except Exception:
        return None


def resolve_approval_ref(repo_root: Any, ref: Any) -> AnchorResolution:
    """Resuelve un `approval_ref` (R35). Nunca lanza; solo lectura."""
    try:
        return _resolver(repo_root, ref)
    except Exception as exc:  # fail-closed
        return AnchorResolution(UNRESOLVABLE, f"resolución falló ({type(exc).__name__})")


def _resolver(repo_root: Any, ref: Any) -> AnchorResolution:
    # 1. Forma.
    if core.validate_approval_ref(ref):
        return AnchorResolution(UNRESOLVABLE, "approval_ref con forma inválida")
    cid, art, h = ref["change_id"], ref["artefacto"], ref["hash"]
    base = dict(change_id=cid, artefacto=art)
    modulos = _dsguard()
    if modulos is None:
        return AnchorResolution(UNRESOLVABLE, "dsguard no disponible", **base)
    dsdd = modulos[1]
    # Una sola definición de «no portable» (`sdd.artefacto_no_portable`, Corrective B).
    if dsdd.artefacto_no_portable(art):
        return AnchorResolution(UNRESOLVABLE, "artefacto no portable (':' o nombre reservado de Windows)", **base)
    # 2-6. Delegado en la fuente única de verdad (`sdd.resolver_aprobacion_registrada`):
    # Change en changes/archive, control.json, entrada artefacto+hash, la más reciente
    # y hash en disco.
    res = dsdd.resolver_aprobacion_registrada(repo_root, cid, art, h)
    entrada = res.get("entrada") if isinstance(res, dict) else None
    entrada = entrada if isinstance(entrada, dict) else {}
    meta = dict(usuario=_meta(entrada.get("usuario")), fecha_declarada=_meta(entrada.get("fecha_declarada")))
    estado = res.get("estado") if isinstance(res, dict) else None
    detalle = res.get("detalle") if isinstance(res, dict) else None
    if estado not in ESTADOS:
        return AnchorResolution(UNRESOLVABLE, "resolución de aprobación con estado desconocido", **base)
    canal = dict(approval_channel=None, trust_tier=None)
    if estado == VERIFIED:
        # Solo se lee de la entrada resuelta; nada se toma del `ref` salvo change_id/artefacto/hash.
        canal_ok, tier = _canal_y_tier(entrada)
        canal = dict(approval_channel=canal_ok, trust_tier=tier)
    return AnchorResolution(estado, str(detalle), **base, **meta, **canal)


def _canal_y_tier(entrada: Any) -> tuple:
    """`(approval_channel, trust_tier)` de una entrada de aprobación (solo lectura).

    `console_confirmed` exacto + `channel_version == "console/v1"` -> T1. Ausente,
    desconocido o malformado -> `declared`/T0 (el valor desconocido no se propaga)."""
    if (
        isinstance(entrada, dict)
        and type(entrada.get("approval_channel")) is str
        and entrada.get("approval_channel") == CANAL_CONSOLE
        and type(entrada.get("channel_version")) is str
        and entrada.get("channel_version") == VERSION_CANAL_CONSOLE
    ):
        return CANAL_CONSOLE, TIER_T1
    return CANAL_DECLARED, TIER_T0


def canal_de_aprobacion(repo_root: Any, approval_ref: Any) -> tuple:
    """`(estado, approval_channel, trust_tier)` de un `approval_ref`. Nunca lanza; solo lectura.

    Canal/tier son `None` salvo que el estado sea verified."""
    res = resolve_approval_ref(repo_root, approval_ref)
    return res.state, res.approval_channel, res.trust_tier


def make_anchor_verifier(repo_root: Any) -> Callable[[Any], AnchorResolution]:
    """`verificador(HumanAttestation) -> AnchorResolution` para el hook `anchor_verifier`."""

    def _verificar(att: Any) -> AnchorResolution:
        if getattr(att, "attestation_kind", None) != "anchored":
            return AnchorResolution(UNRESOLVABLE, "la atestación no es anchored")
        return resolve_approval_ref(repo_root, getattr(att, "approval_ref", None))

    return _verificar

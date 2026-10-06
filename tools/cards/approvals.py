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

NOTA_ANCHOR = (
    "ancla verificada = existe una aprobación registrada, aún vigente, de ese artefacto "
    "bajo el trust model de Harmessi; NO prueba identidad criptográfica, presencia del "
    "usuario, no repudio ni que el contenido aprobado sea el claim de la atestación"
)

VERIFIED = "verified"
STALE = "stale"
MISSING = "missing"
UNRESOLVABLE = "unresolvable"
ESTADOS = (VERIFIED, STALE, MISSING, UNRESOLVABLE)

_ALGORITMO = "sha256/lf/v1"
_MAX_META = 200


@dataclass(frozen=True)
class AnchorResolution:
    state: str
    detail: str
    change_id: Optional[str] = None
    artefacto: Optional[str] = None
    usuario: Optional[str] = None
    fecha_declarada: Optional[str] = None

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


_RESERVADOS_WINDOWS = frozenset(
    ["con", "prn", "aux", "nul"] + [f"com{i}" for i in range(1, 10)] + [f"lpt{i}" for i in range(1, 10)]
)


def _artefacto_no_portable(art: str) -> bool:
    """`:` (unidad/ADS de Windows) o nombre reservado de Windows (con o sin extensión)."""
    if ":" in art or art != art.rstrip(" ."):
        return True
    return art.split(".")[0].strip().lower() in _RESERVADOS_WINDOWS


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
    if _artefacto_no_portable(art):
        return AnchorResolution(UNRESOLVABLE, "artefacto no portable (':' o nombre reservado de Windows)", **base)
    modulos = _dsguard()
    if modulos is None:
        return AnchorResolution(UNRESOLVABLE, "dsguard no disponible", **base)
    dcore, dsdd = modulos
    # 2. Change.
    raiz = Path(repo_root)
    carpeta = None
    for padre in ("changes", "archive"):
        candidata = raiz / "openspec" / padre / cid
        if candidata.is_dir():
            carpeta = candidata
            break
    if carpeta is None:
        return AnchorResolution(UNRESOLVABLE, "Change inexistente (ni changes/ ni archive/)", **base)
    # 3. control.json.
    try:
        control = dcore.leer_control(carpeta / "control.json")
    except Exception as exc:
        return AnchorResolution(UNRESOLVABLE, f"control.json ilegible ({type(exc).__name__})", **base)
    aprobaciones = control.get("aprobaciones", []) if isinstance(control, dict) else None
    if not isinstance(aprobaciones, list):
        return AnchorResolution(UNRESOLVABLE, "control.json sin lista de aprobaciones válida", **base)
    propias = [a for a in aprobaciones if isinstance(a, dict) and a.get("artefacto") == art]
    # 4. Entrada con artefacto + hash.
    coincidentes = [a for a in propias if a.get("hash") == h]
    if not coincidentes:
        return AnchorResolution(MISSING, "no hay aprobación registrada para ese artefacto y hash", **base)
    # 5. La más reciente del artefacto.
    reciente = dsdd._aprobacion_mas_reciente({"aprobaciones": propias}, art)
    meta = dict(usuario=_meta((reciente or {}).get("usuario")), fecha_declarada=_meta((reciente or {}).get("fecha_declarada")))
    if reciente is None or reciente.get("hash") != h:
        otro = reciente or {}
        meta = dict(usuario=_meta(otro.get("usuario")), fecha_declarada=_meta(otro.get("fecha_declarada")))
        return AnchorResolution(STALE, "la aprobación fue reemplazada por una más reciente del artefacto", **base, **meta)
    if reciente.get("algoritmo", _ALGORITMO) != _ALGORITMO:
        return AnchorResolution(UNRESOLVABLE, "algoritmo de hash de la aprobación no soportado", **base, **meta)
    # 6. Archivo en disco.
    archivo = carpeta / art
    try:
        archivo.resolve().relative_to(carpeta.resolve())
    except (ValueError, OSError):
        return AnchorResolution(UNRESOLVABLE, "el artefacto sale del directorio del Change", **base, **meta)
    if not archivo.is_file():
        return AnchorResolution(MISSING, "el artefacto aprobado no existe en el Change", **base, **meta)
    try:
        actual = dcore.hash_lf_v1(archivo)
    except Exception as exc:
        return AnchorResolution(UNRESOLVABLE, f"no se pudo hashear el artefacto ({type(exc).__name__})", **base, **meta)
    if actual != h:
        return AnchorResolution(STALE, "el artefacto cambió después de la aprobación", **base, **meta)
    return AnchorResolution(VERIFIED, "aprobación registrada vigente", **base, **meta)


def make_anchor_verifier(repo_root: Any) -> Callable[[Any], AnchorResolution]:
    """`verificador(HumanAttestation) -> AnchorResolution` para el hook `anchor_verifier`."""

    def _verificar(att: Any) -> AnchorResolution:
        if getattr(att, "attestation_kind", None) != "anchored":
            return AnchorResolution(UNRESOLVABLE, "la atestación no es anchored")
        return resolve_approval_ref(repo_root, getattr(att, "approval_ref", None))

    return _verificar

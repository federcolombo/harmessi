"""Contexto de handoff a nivel SDD (v0.5 Change 3, `fallback-and-handoffs`):
continuidad de trabajo de un Change entre sesiones/proveedores, sin
reiniciar trabajo ya hecho ni duplicar auditorías ya corridas. Distinto del
motor de fallback técnico de `tools/fallback/core.py` (que opera sobre una
invocación puntual, no sobre metadata de Change/sesión) -- ver `design.md`
de este Change para la justificación de mantenerlos separados.

Mismo patrón de persistencia que `tools/harmessi_bench/storage.py`
(`save_run`/`load_run`): JSON plano en `.harmessi/`, sin base de datos ni
dependencias nuevas.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

_ROOT_DEFAULT = Path(".harmessi/handoffs")


@dataclass
class HandoffContext:
    """Contexto mínimo suficiente para retomar el trabajo de un Change sin
    reiniciarlo ni duplicar auditorías ya corridas. `completed`/`pending`
    documentan qué ya se hizo y qué falta (próximo paso exacto);
    `prior_findings` documenta hallazgos de reviewer/metodólogo ya
    conocidos, para no volver a auditar lo mismo."""

    change_id: str
    role: str
    reason: str
    from_provider: Optional[str] = None
    to_provider: Optional[str] = None
    completed: List[str] = field(default_factory=list)
    pending: List[str] = field(default_factory=list)
    prior_findings: List[str] = field(default_factory=list)
    created_utc: str = ""


def build_handoff_context(
    change_id: str,
    role: str,
    reason: str,
    from_provider: Optional[str] = None,
    to_provider: Optional[str] = None,
    completed: Optional[List[str]] = None,
    pending: Optional[List[str]] = None,
    prior_findings: Optional[List[str]] = None,
) -> HandoffContext:
    """Construye un `HandoffContext` válido. Falla cerrado (`raise
    ValueError`) si `change_id`/`role`/`reason` están vacíos -- mismo
    patrón fail-closed que el resto del proyecto (p. ej.
    `tools/routing/policy.py::_construir_regla`). Listas `None` se
    normalizan a `[]`."""
    if not change_id:
        raise ValueError("HandoffContext requiere 'change_id' no vacío")
    if not role:
        raise ValueError("HandoffContext requiere 'role' no vacío")
    if not reason:
        raise ValueError("HandoffContext requiere 'reason' no vacío")

    return HandoffContext(
        change_id=change_id,
        role=role,
        reason=reason,
        from_provider=from_provider,
        to_provider=to_provider,
        completed=list(completed) if completed is not None else [],
        pending=list(pending) if pending is not None else [],
        prior_findings=list(prior_findings) if prior_findings is not None else [],
        created_utc=datetime.now(timezone.utc).isoformat(),
    )


def _timestamp_compacto(created_utc: str) -> str:
    """Timestamp compacto sin caracteres problemáticos para nombre de
    directorio: quita ':' y '-' y trunca antes de los microsegundos (todo
    lo que sigue al primer '.'), mismo criterio simple usado para nombres
    de `run_id` en `tools/harmessi_bench`."""
    return created_utc.replace(":", "").replace("-", "").split(".")[0]


def save_handoff(context: HandoffContext, root: Path = _ROOT_DEFAULT) -> Path:
    """Escribe `root/<change_id>-<timestamp_compacto>/handoff.json` y
    devuelve la ruta del archivo escrito. Mismo patrón que
    `tools/harmessi_bench/storage.py::save_run`.

    Nunca sobrescribe un handoff ya guardado: ante colisión de nombre de
    directorio (mismo `change_id` en el mismo segundo, dado que
    `_timestamp_compacto` trunca a resolución de segundo), agrega un
    sufijo numérico incremental (`-2`, `-3`, ...) al nombre de directorio
    hasta encontrar uno cuyo `handoff.json` todavía no exista."""
    base = f"{context.change_id}-{_timestamp_compacto(context.created_utc)}"
    nombre_directorio = base
    sufijo = 1
    while (Path(root) / nombre_directorio / "handoff.json").exists():
        sufijo += 1
        nombre_directorio = f"{base}-{sufijo}"
    directorio = Path(root) / nombre_directorio
    directorio.mkdir(parents=True, exist_ok=True)

    ruta_archivo = directorio / "handoff.json"
    ruta_archivo.write_text(
        json.dumps(asdict(context), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return ruta_archivo


def load_handoff(path: Path) -> dict:
    """Lee un `handoff.json` y devuelve el dict completo. Falla cerrado:
    si `path` no existe, lanza `FileNotFoundError` con un mensaje claro
    (mismo patrón que `tools/harmessi_bench/storage.py::load_run`)."""
    ruta_archivo = Path(path)
    if not ruta_archivo.exists():
        raise FileNotFoundError(f"no existe un handoff guardado en {ruta_archivo}")
    return json.loads(ruta_archivo.read_text(encoding="utf-8"))

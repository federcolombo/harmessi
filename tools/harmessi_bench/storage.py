"""Almacenamiento de corridas de eval (v0.5 Change 1, `harmessi-bench`).

Mismo patrón que `ds_profile` -> `.harmessi/profiles/<profile_id>/profile.json`
(ver README.md): `.harmessi/evals/<run_id>/result.json` es la fuente de
verdad de una corrida, JSON plano, sin base de datos ni dependencias nuevas.
"""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import List

from tools.ds_init.version import HARNESS_VERSION
from tools.harmessi_bench.core import EvalResult, EvalTarget

_ROOT_DEFAULT = Path(".harmessi/evals")


def save_run(
    run_id: str,
    results: List[EvalResult],
    target: EvalTarget,
    root: Path = _ROOT_DEFAULT,
) -> Path:
    """Escribe `root/run_id/result.json` con la corrida completa y devuelve
    la ruta del archivo escrito."""
    directorio = Path(root) / run_id
    directorio.mkdir(parents=True, exist_ok=True)

    from datetime import datetime, timezone

    contenido = {
        "run_id": run_id,
        "target": dataclasses.asdict(target),
        "harmessi_version": HARNESS_VERSION,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "resultados": [dataclasses.asdict(resultado) for resultado in results],
    }

    ruta_archivo = directorio / "result.json"
    ruta_archivo.write_text(json.dumps(contenido, indent=2, ensure_ascii=False), encoding="utf-8")
    return ruta_archivo


def load_run(run_id: str, root: Path = _ROOT_DEFAULT) -> dict:
    """Lee `root/run_id/result.json` y devuelve el dict completo. Falla
    cerrado: si el `run_id` no existe, lanza `FileNotFoundError` con un
    mensaje claro (nunca devuelve `None` silenciosamente)."""
    ruta_archivo = Path(root) / run_id / "result.json"
    if not ruta_archivo.exists():
        raise FileNotFoundError(
            f"no existe una corrida guardada con run_id={run_id!r} en {root} (esperaba {ruta_archivo})"
        )
    return json.loads(ruta_archivo.read_text(encoding="utf-8"))

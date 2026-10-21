"""Almacenamiento de corridas de eval (v0.5 Change 1, `harmessi-bench`).

Mismo patrón que `ds_profile` -> `.harmessi/profiles/<profile_id>/profile.json`
(ver README.md): `.harmessi/evals/<run_id>/result.json` es la fuente de
verdad de una corrida, JSON plano, sin base de datos ni dependencias nuevas.
"""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import List, Optional

from tools.ds_init.version import HARNESS_VERSION
from tools.harmessi_bench.core import EVALUATOR_VERSION, EvalResult, EvalTarget
from tools.harmessi_bench.suite import bloque_suite

_ROOT_DEFAULT = Path(".harmessi/evals")

# Versión del schema de `result.json` (v0.13 Change 1). Ausente => 0 (legado
# v0.5, se sigue leyendo). Una versión mayor a esta se rechaza.
RESULT_SCHEMA_VERSION = 1
_VERSIONES_LEIBLES = (0, RESULT_SCHEMA_VERSION)


_MAX_DETAIL_PERSISTIDO = 300


def _serializar_resultado(resultado: EvalResult) -> dict:
    """`asdict` + acotado de `score.detail` (puede traer stderr o salida del
    modelo): se persiste evidencia acotada, nunca texto completo."""
    datos = dataclasses.asdict(resultado)
    detail = datos["score"].get("detail")
    if isinstance(detail, str) and len(detail) > _MAX_DETAIL_PERSISTIDO:
        datos["score"]["detail"] = detail[:_MAX_DETAIL_PERSISTIDO] + "…[truncado]"
    return datos


def save_run(
    run_id: str,
    results: List[EvalResult],
    target: EvalTarget,
    root: Path = _ROOT_DEFAULT,
    suite: Optional[object] = None,
    cases_hash: Optional[str] = None,
) -> Path:
    """Escribe `root/run_id/result.json` con la corrida completa y devuelve
    la ruta del archivo escrito. Agrega `schema_version`, `evaluator_version`
    y, si se pasa `suite` (`Suite` o dict), el bloque `suite`
    `{suite_id, suite_version, suite_hash}`. No persiste secretos ni el
    prompt: `cases_hash` (opcional) identifica el contenido de los casos
    corridos, también sin suite; el excerpt de cada resultado ya viene acotado por el runner."""
    directorio = Path(root) / run_id
    directorio.mkdir(parents=True, exist_ok=True)

    from datetime import datetime, timezone

    contenido = {
        "schema_version": RESULT_SCHEMA_VERSION,
        "evaluator_version": EVALUATOR_VERSION,
        "run_id": run_id,
        "target": dataclasses.asdict(target),
        "harmessi_version": HARNESS_VERSION,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "resultados": [_serializar_resultado(resultado) for resultado in results],
    }
    bloque = bloque_suite(suite)
    if bloque is not None:
        contenido["suite"] = bloque
    if cases_hash is not None:
        contenido["cases_hash"] = cases_hash

    ruta_archivo = directorio / "result.json"
    ruta_archivo.write_text(json.dumps(contenido, indent=2, ensure_ascii=False), encoding="utf-8")
    return ruta_archivo


def load_run(run_id: str, root: Path = _ROOT_DEFAULT) -> dict:
    """Lee `root/run_id/result.json` y devuelve el dict completo. Falla
    cerrado: si el `run_id` no existe, lanza `FileNotFoundError` con un
    mensaje claro (nunca devuelve `None` silenciosamente). `schema_version`
    ausente se trata como 0 (legado); 0 y 1 se leen; una versión mayor, no
    entera o bool lanza `ValueError`. El dict devuelto no se modifica."""
    ruta_archivo = Path(root) / run_id / "result.json"
    if not ruta_archivo.exists():
        raise FileNotFoundError(
            f"no existe una corrida guardada con run_id={run_id!r} (falta {run_id}/result.json bajo la raíz de evals)"
        )
    contenido = json.loads(ruta_archivo.read_text(encoding="utf-8-sig"))
    if not isinstance(contenido, dict):
        raise ValueError(f"result.json de run_id={run_id!r} debe ser un objeto JSON")
    version = contenido.get("schema_version", 0)
    if isinstance(version, bool) or not isinstance(version, int) or version not in _VERSIONES_LEIBLES:
        raise ValueError(
            f"schema_version={version!r} no soportada en run_id={run_id!r} "
            f"(soportadas: {list(_VERSIONES_LEIBLES)}); actualizá Harmessi para leer esta corrida"
        )
    return contenido

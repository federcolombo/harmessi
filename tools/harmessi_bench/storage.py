"""Almacenamiento de corridas de eval (v0.5 Change 1, `harmessi-bench`).

Mismo patrón que `ds_profile` -> `.harmessi/profiles/<profile_id>/profile.json`
(ver README.md): `.harmessi/evals/<run_id>/result.json` es la fuente de
verdad de una corrida, JSON plano, sin base de datos ni dependencias nuevas.
"""
from __future__ import annotations

import copy
import dataclasses
import json
import os
import re
from pathlib import Path
from typing import List, Optional

from tools.ds_init.version import HARNESS_VERSION
from tools.harmessi_bench.core import EVALUATOR_VERSION, EvalResult, EvalTarget
from tools.harmessi_bench.redact import redactar_texto
from tools.harmessi_bench.suite import bloque_suite

_ROOT_DEFAULT = Path(".harmessi/evals")

# Versión del schema de `result.json` (v0.13 Change 1). Ausente => 0 (legado
# v0.5, se sigue leyendo). Una versión mayor a esta se rechaza.
RESULT_SCHEMA_VERSION = 1
_VERSIONES_LEIBLES = (0, RESULT_SCHEMA_VERSION)


_MAX_DETAIL_PERSISTIDO = 300

_RE_RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")


def validar_run_id(run_id) -> str:
    """Un `run_id` es un nombre de directorio simple: `[A-Za-z0-9][A-Za-z0-9._-]{0,127}`.
    Rechaza separadores, `..`, rutas absolutas y no-str con `ValueError`."""
    if not isinstance(run_id, str) or _RE_RUN_ID.fullmatch(run_id) is None:
        raise ValueError(f"run_id inválido: {run_id!r} (se permite [A-Za-z0-9][A-Za-z0-9._-]{{0,127}})")
    return run_id


def _serializar_resultado(resultado) -> dict:
    """`asdict` (o copia profunda si ya es un dict cargado con `load_run`,
    p. ej. al combinar en un resume) + redacción best-effort de
    `stdout_excerpt` y `score.detail` (v0.13 Change 2) + acotado de
    `score.detail` (puede traer stderr o salida del modelo): se persiste
    evidencia acotada y redactada, nunca texto completo. Se redacta antes de
    acotar para no dejar un token cortado a la mitad."""
    if isinstance(resultado, dict):
        datos = copy.deepcopy(resultado)
    else:
        datos = dataclasses.asdict(resultado)
    if "stdout_excerpt" in datos:
        datos["stdout_excerpt"] = redactar_texto(datos["stdout_excerpt"])
    if "availability_error" in datos:
        datos["availability_error"] = redactar_texto(datos["availability_error"])
    objetivo = datos.get("target")
    if isinstance(objetivo, dict):
        for clave in ("model", "effort"):
            if clave in objetivo:
                objetivo[clave] = redactar_texto(objetivo[clave])
    score = datos.get("score")
    if isinstance(score, dict):
        detail = redactar_texto(score.get("detail"))
        if isinstance(detail, str) and len(detail) > _MAX_DETAIL_PERSISTIDO:
            detail = detail[:_MAX_DETAIL_PERSISTIDO] + "…[truncado]"
        score["detail"] = detail
    return datos


def save_run(
    run_id: str,
    results: List[EvalResult],
    target: EvalTarget,
    root: Path = _ROOT_DEFAULT,
    suite: Optional[object] = None,
    cases_hash: Optional[str] = None,
    run_manifest: Optional[dict] = None,
) -> Path:
    """Escribe `root/run_id/result.json` con la corrida completa y devuelve
    la ruta del archivo escrito. Agrega `schema_version`, `evaluator_version`
    y, si se pasa `suite` (`Suite` o dict), el bloque `suite`
    `{suite_id, suite_version, suite_hash}`. No persiste secretos ni el
    prompt: `cases_hash` (opcional) identifica el contenido de los casos
    corridos, también sin suite; el excerpt de cada resultado ya viene acotado por el runner."""
    validar_run_id(run_id)
    directorio = Path(root) / run_id
    directorio.mkdir(parents=True, exist_ok=True)

    from datetime import datetime, timezone

    datos_target = dataclasses.asdict(target)
    for clave in ("model", "effort"):
        datos_target[clave] = redactar_texto(datos_target.get(clave))
    contenido = {
        "schema_version": RESULT_SCHEMA_VERSION,
        "evaluator_version": EVALUATOR_VERSION,
        "run_id": run_id,
        "target": datos_target,
        "harmessi_version": HARNESS_VERSION,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "resultados": [_serializar_resultado(resultado) for resultado in results],
    }
    bloque = bloque_suite(suite)
    if bloque is not None:
        contenido["suite"] = bloque
    if cases_hash is not None:
        contenido["cases_hash"] = cases_hash
    if run_manifest is not None:
        # Aditivo (v0.13 Change 2): `schema_version` sigue en 1; ausente => corrida sin manifest.
        contenido["run_manifest"] = run_manifest

    ruta_archivo = directorio / "result.json"
    # Escritura atómica: se serializa todo primero (un surrogate suelto se
    # reemplaza, no lanza ni deja el archivo truncado), se escribe a un
    # temporal en el mismo directorio y se reemplaza con `os.replace`; si algo
    # falla, el result existente queda intacto.
    datos = json.dumps(contenido, indent=2, ensure_ascii=False).encode("utf-8", errors="replace")
    ruta_tmp = directorio / "result.json.tmp"
    try:
        ruta_tmp.write_bytes(datos)
        os.replace(ruta_tmp, ruta_archivo)
    except BaseException:
        try:
            ruta_tmp.unlink()
        except OSError:
            pass
        raise
    return ruta_archivo


def load_run(run_id: str, root: Path = _ROOT_DEFAULT) -> dict:
    """Lee `root/run_id/result.json` y devuelve el dict completo. Falla
    cerrado: si el `run_id` no existe, lanza `FileNotFoundError` con un
    mensaje claro (nunca devuelve `None` silenciosamente). `schema_version`
    ausente se trata como 0 (legado); 0 y 1 se leen; una versión mayor, no
    entera o bool lanza `ValueError`. El dict devuelto no se modifica."""
    validar_run_id(run_id)
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

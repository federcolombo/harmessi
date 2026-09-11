"""Defensa en profundidad: negarse a abrir `--input` (o a escribir en
`--output`) si la ruta cae dentro de un holdout/`data_raw` declarado en
`.claude/guardrails.json`, detrás del hook `PreToolUse` de `pathguard` (que
es best-effort para `Bash`/`PowerShell`, ver `dsguard/pathguard.py`) -- acá
la ruta ya llegó parseada por `argparse`, así que la evaluación es
determinista, no un escaneo de texto.

Reusa explícitamente `dsguard.pathguard.cargar_config` /
`dsguard.pathguard.resolver_ruta_relativa` y `dsguard.repo.path_matches_any`
(mismo patrón `sys.path.insert` que `tools/nbrunner/execute.py:145-149`).
Único módulo de `ds_profile` (junto con este mismo archivo) que depende de
`dsguard` -- por diseño, ver `design.md`.

No reimplementa el matching de excepciones a mano importando el símbolo
privado `pathguard._excepcion_vigente`: replica su lógica (accion=='read',
ruta exacta casefold, vencimiento UTC) en unas pocas líneas propias acá.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Tuple

_TOOLS_DIR = Path(__file__).resolve().parents[1]
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from dsguard import pathguard  # noqa: E402
from dsguard import repo as repo_mod  # noqa: E402
from dsguard.core import parsear_utc  # noqa: E402


def _matchea(ruta_relativa_posix: str, patrones) -> bool:
    """Réplica de `pathguard._matchea_patrones` (privada, no importada):
    comparación case-insensitive vía `dsguard.repo.path_matches_any`."""
    ruta_normalizada = ruta_relativa_posix.casefold()
    patrones_normalizados = [p.casefold() for p in patrones]
    return repo_mod.path_matches_any(ruta_normalizada, patrones_normalizados)


def _excepcion_lectura_vigente(excepciones, ruta_relativa_posix: str, ahora: datetime) -> bool:
    """Réplica de `pathguard._excepcion_vigente` (privada, no importada),
    acotada a `accion == "read"`: ruta EXACTA (no patrón) por diseño, casefold,
    fecha ilegible o vencida => no vigente (fail conservador)."""
    for excepcion in excepciones:
        if excepcion.get("accion") != "read":
            continue
        ruta_excepcion = excepcion.get("ruta")
        if not isinstance(ruta_excepcion, str):
            continue
        if ruta_excepcion.casefold() != ruta_relativa_posix.casefold():
            continue
        vence_utc = excepcion.get("vence_utc")
        if vence_utc:
            try:
                vencimiento = parsear_utc(vence_utc)
            except (ValueError, TypeError):
                continue
            if ahora > vencimiento:
                continue
        return True
    return False


def _es_ruta_no_resoluble(ruta_bruta, repo_root: Path) -> bool:
    """`True` si resolver `ruta_bruta` contra `repo_root` (mismo camino que
    `pathguard.resolver_ruta_relativa`, ver `pathguard.py:177-184`) falla con
    un error de bajo nivel (`OSError`/`RuntimeError`/`ValueError`), en vez de
    simplemente caer fuera del repo.

    `pathguard.resolver_ruta_relativa` devuelve `(None, False)` tanto para
    "genuinamente fuera del repo" como para "no se pudo resolver" -- no
    distingue los dos casos en su valor de retorno. `pathguard.py` (línea
    259-261) trata ambos como denegado (fail-closed); este helper permite que
    `holdout_guard` haga lo mismo sin duplicar el bloque `try/except` de
    `resolver_ruta_relativa` en cada función que lo necesita."""
    try:
        candidato = Path(ruta_bruta)
        if not candidato.is_absolute():
            candidato = repo_root / candidato
        candidato.resolve()
        repo_root.resolve()
    except (OSError, RuntimeError, ValueError):
        return True
    return False


def verificar_permitido(ruta_input: Path, repo_root: Path) -> Tuple[bool, str]:
    """`(True, motivo)` si `ruta_input` puede abrirse; `(False, motivo)` si
    cae dentro de un holdout declarado sin excepción de lectura vigente.

    Si `.claude/guardrails.json` no existe, usa los defaults seguros de
    `ConfigGuardrails()` (todo vacío salvo `data_raw`) -- no falla. Un
    `guardrails.json` presente pero corrupto se trata fail-closed (deniega),
    mismo criterio que el hook real."""
    repo_root = Path(repo_root)
    try:
        config = pathguard.cargar_config(repo_root)
    except pathguard.ConfigGuardrailsError as exc:
        return False, f"guardrails.json inválido en {repo_root}: {exc}"

    if _es_ruta_no_resoluble(ruta_input, repo_root):
        return False, f"Ruta no resoluble, denegado (fail-closed): {ruta_input}"

    ruta_relativa, dentro_del_repo = pathguard.resolver_ruta_relativa(str(ruta_input), repo_root)
    if not dentro_del_repo:
        # Los holdouts se declaran como rutas dentro del repo -- una ruta
        # fuera de `repo_root` no puede matchear ninguno. La verificación de
        # "existe/es legible" la hace `io_readers` después.
        return True, "Ruta fuera del repo: fuera de alcance de holdout_guard."

    if not config.holdouts:
        return True, "No hay holdouts declarados en guardrails.json."

    if not _matchea(ruta_relativa, config.holdouts):
        return True, "Ruta permitida (no matchea ningún holdout declarado)."

    if _excepcion_lectura_vigente(config.excepciones, ruta_relativa, datetime.now(timezone.utc)):
        return True, f"Holdout con excepción de lectura vigente: {ruta_relativa}."

    return False, (
        f"Ruta protegida (holdout, requiere excepción explícita de lectura en "
        f"guardrails.json): {ruta_relativa}."
    )


def verificar_salida_permitida(ruta_output: Path, repo_root: Path) -> Tuple[bool, str]:
    """Mismo criterio que `pathguard` (`pathguard.py:272-280`) para
    escritura: si `--output` cae dentro de `config.holdouts` O de
    `config.data_raw`, se niega -- ninguna excepción de `guardrails.json`
    aplica a escritura (las excepciones son solo de lectura, ver
    `_excepcion_lectura_vigente`), igual que el hook real."""
    repo_root = Path(repo_root)
    try:
        config = pathguard.cargar_config(repo_root)
    except pathguard.ConfigGuardrailsError as exc:
        return False, f"guardrails.json inválido en {repo_root}: {exc}"

    if _es_ruta_no_resoluble(ruta_output, repo_root):
        return False, f"Ruta no resoluble, denegado (fail-closed): {ruta_output}"

    ruta_relativa, dentro_del_repo = pathguard.resolver_ruta_relativa(str(ruta_output), repo_root)
    if not dentro_del_repo:
        return True, "Ruta de salida fuera del repo: fuera de alcance de holdout_guard."

    if _matchea(ruta_relativa, config.holdouts):
        return False, f"Ruta protegida (holdout, la escritura nunca está autorizada): {ruta_relativa}."

    if _matchea(ruta_relativa, config.data_raw):
        return False, f"data/raw es de solo lectura, no se puede escribir ahí: {ruta_relativa}."

    return True, "Ruta de salida permitida."

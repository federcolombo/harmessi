"""Mecanismo GENERICO de evidencia de artifact (Change 6, v0.3:
20260915-readiness-and-promotion) para los tiers `production_readiness` y
`operations` de `lifecycle.MLOPS_CAPACIDADES` -- parametrizado por
`(tier, capability)`, no conoce readiness ni project_stage.

Reusa (nunca duplica el *gating*) `pathguard.cargar_config` /
`pathguard.resolver_ruta_relativa` (ambas publicas) y
`repo.path_matches_any`, y replica LOCALMENTE el matching case-insensitive
de holdouts/secretos y la vigencia de excepciones de lectura -- mismo
precedente ya establecido por `tools/ds_profile/holdout_guard.py` (unico
otro modulo que hace esto, en vez de importar los simbolos privados
`pathguard._matchea_patrones`/`pathguard._excepcion_vigente`). Mantiene el
mismo criterio fail-closed: `guardrails.json` corrupto -> rechazado.

Hash sha256 binario chunked duplicado localmente (no importado de
`ds_profile.fingerprint.calcular_fingerprint`): mantiene la unica direccion
de dependencia cruzada existente hoy (`ds_profile -> dsguard`, nunca al
reves) -- ver `design.md` punto 2 del change.

`evidencia_valida` vive aca (co-localizada con el lado de escritura, ver
`design.md` punto 5) -- `readiness.py` solo consume el booleano/detalle,
nunca conoce el schema interno de `artifact_evidence`.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Tuple

import hashlib

from . import lifecycle
from . import pathguard
from . import repo as repo_mod
from .core import ahora_utc, parsear_utc

# "foundations" queda deliberadamente afuera: ese tier usa su propio
# mecanismo de snapshot (`mlops_foundations.registrar_evidencia`, Change 5),
# no este.
TIERS_EVIDENCIABLES: tuple = ("production_readiness", "operations")


class EvidenciaError(Exception):
    """Error de dominio de `agregar_evidencia`: tier/capability/reason/
    artifact invalido, o ruta protegida (secreto, o holdout sin excepcion de
    lectura vigente). Nunca muta nada -- toda validacion ocurre antes de
    tocar `openspec/lifecycle/state.json`."""


# --- Hash binario chunked (duplicado localmente, ver docstring del modulo) ----

def _hash_binario_sha256(ruta: Path, chunk_size: int = 1 << 20) -> str:
    hasher = hashlib.sha256()
    with open(ruta, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


# --- Replica local del matching de pathguard (ver docstring del modulo) -------

def _matchea_patrones(ruta_relativa_posix: str, patrones) -> bool:
    """Replica de `pathguard._matchea_patrones` (privada, no importada)."""
    ruta_normalizada = ruta_relativa_posix.casefold()
    patrones_normalizados = [p.casefold() for p in patrones]
    return repo_mod.path_matches_any(ruta_normalizada, patrones_normalizados)


def _excepcion_lectura_vigente(excepciones, ruta_relativa_posix: str, ahora: datetime) -> bool:
    """Replica de `pathguard._excepcion_vigente` (privada, no importada),
    acotada a `accion == "read"` (la misma acotacion que
    `ds_profile/holdout_guard.py`)."""
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


def _validar_ruta_artifact(repo_root: Path, artifact_rel_path: str) -> str:
    """Valida `--artifact`: existe, es un archivo (no directorio), resuelve
    dentro del repo, no matchea un secreto, y si matchea un holdout requiere
    excepcion de lectura vigente. Devuelve la ruta relativa POSIX dentro del
    repo. Levanta `EvidenciaError` en cualquier rechazo -- fail-closed si
    `guardrails.json` esta corrupto (nunca se asume un default seguro ante
    un error real de parseo)."""
    try:
        config = pathguard.cargar_config(repo_root)
    except pathguard.ConfigGuardrailsError as exc:
        raise EvidenciaError(f"guardrails.json invalido en {repo_root}: {exc}") from exc

    ruta_relativa, dentro_del_repo = pathguard.resolver_ruta_relativa(artifact_rel_path, repo_root)
    if not dentro_del_repo:
        raise EvidenciaError(f"--artifact fuera del repositorio o no resoluble: {artifact_rel_path!r}")

    ruta_absoluta = repo_root / ruta_relativa
    if not ruta_absoluta.exists():
        raise EvidenciaError(f"--artifact no existe: {ruta_relativa}")
    if not ruta_absoluta.is_file():
        raise EvidenciaError(f"--artifact debe ser un archivo, no un directorio: {ruta_relativa}")

    patrones_secretos = pathguard.SECRETOS_HARDCODEADOS + config.secretos_extra
    if _matchea_patrones(ruta_relativa, patrones_secretos):
        raise EvidenciaError(f"--artifact matchea un patron de secreto protegido: {ruta_relativa}")

    if _matchea_patrones(ruta_relativa, config.holdouts):
        if not _excepcion_lectura_vigente(config.excepciones, ruta_relativa, datetime.now(timezone.utc)):
            raise EvidenciaError(
                "--artifact protegido (holdout, requiere excepcion explicita de lectura en "
                f"guardrails.json): {ruta_relativa}"
            )

    return ruta_relativa


# --- Escritura -------------------------------------------------------------

def agregar_evidencia(
    repo_root: Path, tier: str, capability: str, artifact_rel_path: str, reason: str
) -> dict:
    """Valida tier/capability/reason/artifact; calcula sha256 binario;
    dedup determinista por `{capability, path, hash}`; escribe
    `{"tipo":"artifact_evidence","path","sha256","reason","utc"}` en
    `mlops.<tier>.<capability>.evidencia` vía `lifecycle.escribir_estado`
    (escritura atómica). Requiere `openspec/lifecycle/state.json` existente
    -- propaga `FileNotFoundError`/`lifecycle.LifecycleEstadoError` tal
    cual, nunca lo crea.

    Devuelve `{"agregado": bool, "duplicado": bool, "entrada": {...}}`."""
    repo_root = Path(repo_root)

    if tier not in TIERS_EVIDENCIABLES:
        raise EvidenciaError(
            f"tier invalido: {tier!r} (validos: {TIERS_EVIDENCIABLES}; 'foundations' usa el "
            "mecanismo de mlops_foundations.py, no este)"
        )
    if capability not in lifecycle.MLOPS_CAPACIDADES[tier]:
        raise EvidenciaError(
            f"capability {capability!r} no pertenece al tier {tier!r} "
            f"(validas: {lifecycle.MLOPS_CAPACIDADES[tier]})"
        )
    if not reason:
        raise EvidenciaError("'--reason' es obligatorio y no puede estar vacio")
    if not artifact_rel_path:
        raise EvidenciaError("'--artifact' es obligatorio")

    ruta_relativa = _validar_ruta_artifact(repo_root, artifact_rel_path)
    sha256 = _hash_binario_sha256(repo_root / ruta_relativa)

    # Requiere lifecycle existente -- propaga FileNotFoundError/LifecycleEstadoError, nunca lo crea.
    estado = lifecycle.leer_estado(lifecycle.state_path(repo_root))

    entrada_capability = estado["mlops"][tier][capability]
    evidencia_lista = entrada_capability.setdefault("evidencia", [])
    for existente in evidencia_lista:
        if (
            existente.get("tipo") == "artifact_evidence"
            and existente.get("path") == ruta_relativa
            and existente.get("sha256") == sha256
        ):
            return {"agregado": False, "duplicado": True, "entrada": existente}

    ahora = ahora_utc()
    nueva_entrada = {
        "tipo": "artifact_evidence",
        "path": ruta_relativa,
        "sha256": sha256,
        "reason": reason,
        "utc": ahora,
    }
    evidencia_lista.append(nueva_entrada)
    entrada_capability["actualizado_utc"] = ahora
    lifecycle.escribir_estado(repo_root, estado)

    return {"agregado": True, "duplicado": False, "entrada": nueva_entrada}


# --- Lectura/validacion -----------------------------------------------------

def evidencia_valida(repo_root: Path, tier: str, capability: str) -> Tuple[bool, str]:
    """`True` solo si existe al menos una entrada `artifact_evidence` en
    `mlops.<tier>.<capability>.evidencia` cuyo archivo TODAVIA existe, sigue
    dentro del repo, y cuyo sha256 actual coincide con el registrado.
    Evidencia ausente/obsoleta -> `False` con detalle explicativo. Requiere
    `openspec/lifecycle/state.json` existente -- propaga
    `FileNotFoundError`/`lifecycle.LifecycleEstadoError` tal cual."""
    repo_root = Path(repo_root)
    estado = lifecycle.leer_estado(lifecycle.state_path(repo_root))
    entrada_capability = estado["mlops"][tier][capability]
    evidencia_lista = entrada_capability.get("evidencia", [])

    entradas_artifact = [e for e in evidencia_lista if e.get("tipo") == "artifact_evidence"]
    if not entradas_artifact:
        return False, f"sin evidencia registrada para {tier}.{capability}"

    obsoletas = []
    for entrada in entradas_artifact:
        ruta_registrada = entrada.get("path")
        sha256_registrado = entrada.get("sha256")
        if not ruta_registrada or not sha256_registrado:
            obsoletas.append(f"{ruta_registrada!r}: entrada malformada")
            continue

        ruta_resuelta, dentro_del_repo = pathguard.resolver_ruta_relativa(ruta_registrada, repo_root)
        if not dentro_del_repo:
            obsoletas.append(f"{ruta_registrada}: ya no resuelve dentro del repo (obsoleta)")
            continue

        ruta_absoluta = repo_root / ruta_resuelta
        if not ruta_absoluta.exists() or not ruta_absoluta.is_file():
            obsoletas.append(f"{ruta_registrada}: archivo ausente (evidencia obsoleta)")
            continue

        sha256_actual = _hash_binario_sha256(ruta_absoluta)
        if sha256_actual != sha256_registrado:
            obsoletas.append(f"{ruta_registrada}: hash no coincide, el archivo cambio (evidencia obsoleta)")
            continue

        return True, f"evidencia valida: {ruta_registrada}"

    detalle = "; ".join(obsoletas)
    return False, f"evidencia obsoleta para {tier}.{capability}: {detalle}"

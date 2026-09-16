"""Capa neutral de scientific validity checks (v0.4 Change 0:
20260916-kdd-enforceable-checks): reusa `checks.CheckResult`/`STATUS_*`/
`KIND_*` -- no es un segundo checks engine. Convierte reglas científicas
clave (cutoff temporal, holdout, leakage básico, baseline) en checks
deterministas PASS/WARN/FAIL/N-A, declarados de forma opcional vía
`.harmessi/scientific-policy.json`.

Principio permanente: el LLM decide lo semántico, el binario calcula y hace
cumplir lo determinista. Las decisiones de diseño no obvias (por qué un
archivo de policy nuevo, por qué no se duplica el check de cutoff como
leakage temporal, por qué dos checks de holdout, por qué el binario nunca lee
el contenido del holdout, por qué se replica -- en vez de importar -- el
matching privado de `pathguard`, por qué el hash de baseline es opcional, por
qué las fechas se comparan como UTC-naive, y los riesgos/límites conocidos)
están documentadas en `openspec/changes/20260916-kdd-enforceable-checks/
design.md` -- no se repiten acá.

`evaluar_scientific_checks(repo_root)` es siempre de solo lectura, nunca
lanza, y es determinista (mismo estado de disco -> mismo resultado). Este
módulo NUNCA escribe nada, ni siquiera `.harmessi/scientific-policy.json`
(esa política se autoría a mano, mismo criterio editorial que
`guardrails.json`)."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from . import checks, pathguard, repo
from . import core

# --- Policy: .harmessi/scientific-policy.json (opcional, solo lectura) -------

SCHEMA_VERSION_SOPORTADA = 1


class ScientificPolicyError(Exception):
    """`.harmessi/scientific-policy.json` existe pero está corrupto o mal
    formado (JSON inválido, `schema_version` desconocida, o alguna sección
    declarada con un tipo incorrecto). El llamador debe tratar esto como
    bloqueante (un único `CheckResult` FAIL `kind=technical_error`), sin
    evaluar nada parcialmente."""


def policy_path(repo_root: Path) -> Path:
    return Path(repo_root) / ".harmessi" / "scientific-policy.json"


def validar_estructura(datos: dict) -> None:
    """Valida la forma mínima de `datos` (ya parseado desde JSON):
    `dict`, `schema_version` conocida, y -- si están presentes -- las
    secciones `temporal`/`holdout`/`leakage`/`baseline` deben ser `dict`.

    Campos desconocidos (a nivel top-level o dentro de cada sección) se
    IGNORAN silenciosamente -- decisión deliberada de forward-compat: una
    policy escrita por una versión futura de Harmessi con campos nuevos no
    debe romper una versión anterior de este validador, siempre que
    `schema_version` siga siendo la soportada."""
    if not isinstance(datos, dict):
        raise ScientificPolicyError("el contenido de scientific-policy.json debe ser un objeto JSON")
    version = datos.get("schema_version")
    if version != SCHEMA_VERSION_SOPORTADA:
        raise ScientificPolicyError(
            f"schema_version desconocida: {version!r} (se esperaba {SCHEMA_VERSION_SOPORTADA})"
        )
    for seccion in ("temporal", "holdout", "leakage", "baseline"):
        if seccion in datos and datos[seccion] is not None and not isinstance(datos[seccion], dict):
            raise ScientificPolicyError(f"la sección {seccion!r} debe ser un objeto JSON (o estar ausente)")


def leer_policy(repo_root: Path) -> dict:
    """Lee `.harmessi/scientific-policy.json`. Si no existe, devuelve la
    forma vacía por default (todas las secciones `None`, sin levantar). Si
    existe pero no es JSON válido, o falla `validar_estructura`, levanta
    `ScientificPolicyError`. NUNCA escribe nada -- solo lectura."""
    ruta = policy_path(repo_root)
    if not ruta.exists():
        return {
            "schema_version": SCHEMA_VERSION_SOPORTADA,
            "temporal": None,
            "holdout": None,
            "leakage": None,
            "baseline": None,
        }
    try:
        contenido = ruta.read_text(encoding="utf-8")
    except OSError as exc:
        raise ScientificPolicyError(f"no se pudo leer {ruta}: {exc}") from exc
    try:
        datos = json.loads(contenido)
    except ValueError as exc:
        raise ScientificPolicyError(f"{ruta} no es JSON válido: {exc}") from exc
    validar_estructura(datos)
    return datos


# --- Helper compartido de rutas seguras (replica pathguard, ver docstring) ---

@dataclass(frozen=True)
class ResultadoRutaLectura:
    ok: bool
    ruta_absoluta: Optional[Path]
    motivo: str
    tecnico: bool = False


def _matchea_patrones(ruta_relativa_posix: str, patrones) -> bool:
    """Réplica de `pathguard._matchea_patrones` (privada, no importada):
    comparación case-insensitive vía `dsguard.repo.path_matches_any`."""
    ruta_normalizada = ruta_relativa_posix.casefold()
    patrones_normalizados = [p.casefold() for p in patrones]
    return repo.path_matches_any(ruta_normalizada, patrones_normalizados)


def _excepcion_lectura_vigente(excepciones, ruta_relativa_posix: str, ahora: datetime) -> bool:
    """Réplica de `pathguard._excepcion_vigente` (privada, no importada),
    acotada a `accion == "read"`: ruta EXACTA (no patrón), casefold, fecha
    ilegible o vencida => no vigente (fail conservador)."""
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
                vencimiento = core.parsear_utc(vence_utc)
            except (ValueError, TypeError):
                continue
            if ahora > vencimiento:
                continue
        return True
    return False


def _resolver_ruta_lectura(repo_root: Path, ruta_declarada: str) -> ResultadoRutaLectura:
    """Resuelve `ruta_declarada` (declarada en la policy) contra `repo_root`,
    aplicando la misma protección de holdout/secretos que `pathguard`/
    `ds_profile.holdout_guard`: nunca se lee un profile/evidencia dentro de un
    holdout sin excepción de lectura vigente, ni un secreto hardcodeado."""
    try:
        config = pathguard.cargar_config(repo_root)
    except pathguard.ConfigGuardrailsError as exc:
        return ResultadoRutaLectura(False, None, f"guardrails.json inválido: {exc}", tecnico=True)

    ruta_relativa, dentro_del_repo = pathguard.resolver_ruta_relativa(ruta_declarada, repo_root)
    if not dentro_del_repo:
        return ResultadoRutaLectura(False, None, f"ruta fuera del repositorio o no resoluble: {ruta_declarada!r}")

    patrones_secretos = pathguard.SECRETOS_HARDCODEADOS + config.secretos_extra
    if _matchea_patrones(ruta_relativa, patrones_secretos):
        return ResultadoRutaLectura(False, None, f"ruta protegida (secreto): {ruta_relativa}")

    if _matchea_patrones(ruta_relativa, config.holdouts):
        if not _excepcion_lectura_vigente(config.excepciones, ruta_relativa, datetime.now(timezone.utc)):
            return ResultadoRutaLectura(
                False,
                None,
                f"ruta protegida (holdout, requiere excepción explícita de lectura en "
                f"guardrails.json): {ruta_relativa}",
            )

    return ResultadoRutaLectura(True, repo_root / ruta_relativa, "ruta permitida")


# --- Hash binario chunked (duplicado localmente, ver docstring del módulo) ---

def _hash_binario_sha256(ruta: Path, chunk_size: int = 1 << 20) -> str:
    hasher = hashlib.sha256()
    with open(ruta, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


# --- SCI-CUTOFF ----------------------------------------------------------------

def evaluar_cutoff(repo_root: Path, policy: dict) -> list:
    codigo = "SCI-CUTOFF"
    temporal = policy.get("temporal")
    if not isinstance(temporal, dict) or temporal.get("declared") is not True:
        return [checks.CheckResult(checks.STATUS_NA, codigo, "cutoff temporal no declarado en la policy (temporal.declared != true).")]

    cutoff_raw = temporal.get("cutoff_utc")
    if not cutoff_raw:
        return [checks.CheckResult(checks.STATUS_WARN, codigo, "temporal.declared=true pero falta 'cutoff_utc' en la policy.")]

    date_column = temporal.get("date_column")
    if not date_column:
        return [checks.CheckResult(checks.STATUS_WARN, codigo, "temporal.declared=true pero falta 'date_column' en la policy.")]

    profile_path_raw = temporal.get("profile_path")
    if not profile_path_raw:
        return [checks.CheckResult(checks.STATUS_WARN, codigo, "temporal.declared=true pero falta 'profile_path' en la policy.")]

    try:
        cutoff_dt = core.parsear_utc(cutoff_raw)
    except (ValueError, TypeError):
        return [checks.CheckResult(
            checks.STATUS_FAIL, codigo,
            f"temporal.cutoff_utc={cutoff_raw!r} no tiene el formato esperado (YYYY-MM-DDTHH:MM:SSZ).",
        )]

    resultado_ruta = _resolver_ruta_lectura(repo_root, profile_path_raw)
    if resultado_ruta.tecnico:
        return [checks.CheckResult(checks.STATUS_FAIL, codigo, resultado_ruta.motivo, kind=checks.KIND_TECHNICAL_ERROR)]
    if not resultado_ruta.ok:
        return [checks.CheckResult(
            checks.STATUS_FAIL, codigo,
            f"temporal.profile_path={profile_path_raw!r} no es legible: {resultado_ruta.motivo}",
        )]

    ruta_absoluta = resultado_ruta.ruta_absoluta
    if not ruta_absoluta.exists():
        return [checks.CheckResult(
            checks.STATUS_WARN, codigo,
            f"temporal.profile_path={profile_path_raw!r} no existe todavía -- correr ds_profile sobre el dataset.",
        )]

    try:
        perfil = json.loads(ruta_absoluta.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return [checks.CheckResult(
            checks.STATUS_FAIL, codigo,
            f"no se pudo leer/parsear {profile_path_raw!r}: {exc}",
            kind=checks.KIND_TECHNICAL_ERROR,
        )]

    columnas = perfil.get("columnas_detalle", {}) if isinstance(perfil, dict) else {}
    if date_column not in columnas:
        disponibles = ", ".join(sorted(columnas.keys())) or "(ninguna)"
        return [checks.CheckResult(
            checks.STATUS_FAIL, codigo,
            f"date_column={date_column!r} no está en columnas_detalle del profile. Columnas disponibles: {disponibles}.",
            subject=date_column,
        )]

    dtype_real = columnas[date_column].get("dtype")
    if dtype_real != "fecha":
        return [checks.CheckResult(
            checks.STATUS_FAIL, codigo,
            f"date_column={date_column!r} no es dtype 'fecha' en el profile (dtype real: {dtype_real!r}).",
            subject=date_column,
        )]

    fecha_max_raw = columnas[date_column].get("fecha_max")
    if fecha_max_raw is None:
        return [checks.CheckResult(
            checks.STATUS_FAIL, codigo,
            f"date_column={date_column!r} no tiene valores (fecha_max ausente en el profile).",
            subject=date_column,
        )]

    try:
        fecha_max_dt = datetime.fromisoformat(fecha_max_raw)
    except ValueError as exc:
        return [checks.CheckResult(
            checks.STATUS_FAIL, codigo,
            f"fecha_max={fecha_max_raw!r} de {date_column!r} no es un ISO datetime válido: {exc}",
            kind=checks.KIND_TECHNICAL_ERROR,
            subject=date_column,
        )]

    cutoff_naive = cutoff_dt.replace(tzinfo=None)
    if fecha_max_dt <= cutoff_naive:
        return [checks.CheckResult(
            checks.STATUS_PASS, codigo,
            f"{date_column}: fecha_max={fecha_max_dt.isoformat()} <= cutoff_utc={cutoff_raw}.",
            subject=date_column,
        )]
    return [checks.CheckResult(
        checks.STATUS_FAIL, codigo,
        f"{date_column}: fecha_max={fecha_max_dt.isoformat()} excede cutoff_utc={cutoff_raw} -- posible leakage temporal.",
        subject=date_column,
    )]


# --- SCI-HOLDOUT-PROTECTION / SCI-HOLDOUT-USAGE ---------------------------------

def evaluar_holdout_proteccion(repo_root: Path, policy: dict) -> list:
    """Limitación deliberada (ver `design.md` §10 del change): `holdout` en
    scientific-policy.json no declara una ruta/patrón propia del holdout del
    proyecto/corte en curso (schema minimalista, ver `design.md` §2) -- un
    PASS acá confirma solo que ALGÚN patrón está declarado en
    `guardrails.json → holdouts`, nunca que sea específicamente el holdout
    relevante de este corte/dataset."""
    codigo = "SCI-HOLDOUT-PROTECTION"
    holdout = policy.get("holdout")
    if not isinstance(holdout, dict) or holdout.get("declared") is not True:
        return [checks.CheckResult(checks.STATUS_NA, codigo, "holdout no declarado en la policy (holdout.declared != true).")]

    try:
        config = pathguard.cargar_config(repo_root)
    except pathguard.ConfigGuardrailsError as exc:
        return [checks.CheckResult(
            checks.STATUS_FAIL, codigo, f"guardrails.json inválido: {exc}", kind=checks.KIND_TECHNICAL_ERROR,
        )]

    if not config.holdouts:
        return [checks.CheckResult(
            checks.STATUS_FAIL, codigo,
            "holdout.declared=true en scientific-policy.json pero guardrails.json no tiene ningún patrón "
            "en 'holdouts' -- el holdout declarado no está estructuralmente protegido.",
        )]

    return [checks.CheckResult(
        checks.STATUS_PASS, codigo,
        f"guardrails.json declara {len(config.holdouts)} patrón(es) en 'holdouts' ({', '.join(config.holdouts)}), "
        "y pathguard nunca autoriza escritura sobre esos patrones. Esto NO verifica que sean "
        "específicamente el/los holdout(s) de este proyecto/corte -- scientific-policy.json no declara "
        "una ruta de holdout propia para comparar, solo confirma que existe protección estructural "
        "activa declarada en guardrails.json.",
    )]


OPERACIONES_PROHIBIDAS = (
    "training",
    "feature_engineering_fit",
    "model_selection",
    "hyperparameter_tuning",
    "baseline_fitting",
)


def evaluar_holdout_uso(repo_root: Path, policy: dict) -> list:
    codigo = "SCI-HOLDOUT-USAGE"
    holdout = policy.get("holdout")
    if not isinstance(holdout, dict) or holdout.get("declared") is not True:
        return [checks.CheckResult(checks.STATUS_NA, codigo, "holdout no declarado en la policy (holdout.declared != true).")]

    declaraciones = holdout.get("usage_declarations")
    if not isinstance(declaraciones, list):
        declaraciones = []

    usados: dict = {}
    for entrada in declaraciones:
        if not isinstance(entrada, dict):
            continue
        operacion = entrada.get("operation")
        usado = entrada.get("used")
        if operacion in OPERACIONES_PROHIBIDAS and isinstance(usado, bool):
            usados[operacion] = usado

    violaciones = [op for op in OPERACIONES_PROHIBIDAS if usados.get(op) is True]
    if violaciones:
        return [checks.CheckResult(
            checks.STATUS_FAIL, codigo,
            f"operación(es) prohibida(s) declaradas como usadas sobre el holdout: {', '.join(violaciones)}.",
        )]

    no_declaradas = [op for op in OPERACIONES_PROHIBIDAS if op not in usados]
    if no_declaradas:
        return [checks.CheckResult(
            checks.STATUS_WARN, codigo,
            f"información insuficiente -- operación(es) sin declarar explícitamente: {', '.join(no_declaradas)}.",
        )]

    mensaje = "las 5 operaciones prohibidas se declaran explícitamente 'used: false' sobre el holdout."
    final_eval = holdout.get("final_evaluation")
    if isinstance(final_eval, dict) and final_eval.get("authorized") is True:
        motivo = final_eval.get("reason") or "(sin motivo registrado)"
        mensaje += f" Evaluación final autorizada -- motivo declarado: {motivo}"
    return [checks.CheckResult(checks.STATUS_PASS, codigo, mensaje)]


# --- SCI-LEAKAGE-TARGET / SCI-LEAKAGE-FORBIDDEN / SCI-LEAKAGE-SPLIT ------------

def evaluar_leakage_target(policy: dict) -> list:
    codigo = "SCI-LEAKAGE-TARGET"
    leakage = policy.get("leakage")
    if not isinstance(leakage, dict):
        return [checks.CheckResult(checks.STATUS_NA, codigo, "sección 'leakage' no declarada en la policy.")]

    target = leakage.get("target")
    if not target:
        return [checks.CheckResult(checks.STATUS_NA, codigo, "leakage.target no declarado.")]

    features = leakage.get("features")
    if not isinstance(features, list) or not features:
        return [checks.CheckResult(
            checks.STATUS_WARN, codigo,
            f"leakage.target={target!r} declarado pero leakage.features está vacío/ausente -- no se puede evaluar.",
        )]

    if target in features:
        return [checks.CheckResult(
            checks.STATUS_FAIL, codigo,
            f"el target {target!r} está presente en leakage.features -- leakage directo target-en-features.",
            subject=target,
        )]
    return [checks.CheckResult(
        checks.STATUS_PASS, codigo, f"el target {target!r} no está en leakage.features.", subject=target,
    )]


def evaluar_leakage_forbidden(policy: dict) -> list:
    codigo = "SCI-LEAKAGE-FORBIDDEN"
    leakage = policy.get("leakage")
    if not isinstance(leakage, dict):
        return [checks.CheckResult(checks.STATUS_NA, codigo, "sección 'leakage' no declarada en la policy.")]

    forbidden = leakage.get("forbidden_features")
    if not isinstance(forbidden, list) or not forbidden:
        return [checks.CheckResult(checks.STATUS_NA, codigo, "leakage.forbidden_features no declarado.")]

    features = leakage.get("features")
    if not isinstance(features, list) or not features:
        return [checks.CheckResult(
            checks.STATUS_WARN, codigo,
            "leakage.forbidden_features declarado pero leakage.features está vacío/ausente -- no se puede evaluar.",
        )]

    interseccion = sorted(set(features) & set(forbidden))
    if interseccion:
        return [checks.CheckResult(
            checks.STATUS_FAIL, codigo,
            f"feature(s) explícitamente prohibidas presentes en leakage.features: {', '.join(interseccion)}.",
        )]
    return [checks.CheckResult(checks.STATUS_PASS, codigo, "ninguna feature declarada coincide con leakage.forbidden_features.")]


def evaluar_leakage_split(policy: dict) -> list:
    codigo = "SCI-LEAKAGE-SPLIT"
    leakage = policy.get("leakage")
    if not isinstance(leakage, dict):
        return [checks.CheckResult(checks.STATUS_NA, codigo, "sección 'leakage' no declarada en la policy.")]

    train_max_raw = leakage.get("train_max_utc")
    val_min_raw = leakage.get("validation_min_utc")

    if not train_max_raw and not val_min_raw:
        return [checks.CheckResult(checks.STATUS_NA, codigo, "leakage.train_max_utc/validation_min_utc no declarados.")]

    if not train_max_raw or not val_min_raw:
        faltante = "train_max_utc" if not train_max_raw else "validation_min_utc"
        return [checks.CheckResult(
            checks.STATUS_WARN, codigo,
            f"solo uno de los dos límites del split temporal está declarado -- falta leakage.{faltante}.",
        )]

    try:
        train_max_dt = core.parsear_utc(train_max_raw)
    except (ValueError, TypeError):
        return [checks.CheckResult(
            checks.STATUS_FAIL, codigo,
            f"leakage.train_max_utc={train_max_raw!r} no tiene el formato esperado (YYYY-MM-DDTHH:MM:SSZ).",
        )]
    try:
        val_min_dt = core.parsear_utc(val_min_raw)
    except (ValueError, TypeError):
        return [checks.CheckResult(
            checks.STATUS_FAIL, codigo,
            f"leakage.validation_min_utc={val_min_raw!r} no tiene el formato esperado (YYYY-MM-DDTHH:MM:SSZ).",
        )]

    if train_max_dt >= val_min_dt:
        return [checks.CheckResult(
            checks.STATUS_FAIL, codigo,
            f"train_max_utc={train_max_raw} >= validation_min_utc={val_min_raw} -- split temporal inválido (solapamiento).",
        )]
    return [checks.CheckResult(
        checks.STATUS_PASS, codigo, f"train_max_utc={train_max_raw} < validation_min_utc={val_min_raw}.",
    )]


# --- SCI-BASELINE ---------------------------------------------------------------

def evaluar_baseline(repo_root: Path, policy: dict) -> list:
    codigo = "SCI-BASELINE"
    baseline = policy.get("baseline")
    if not isinstance(baseline, dict) or baseline.get("required") is not True:
        return [checks.CheckResult(checks.STATUS_NA, codigo, "baseline no requerido en la policy (baseline.required != true).")]

    evidence_path_raw = baseline.get("evidence_path")
    if not evidence_path_raw:
        return [checks.CheckResult(checks.STATUS_FAIL, codigo, "baseline.required=true pero falta 'evidence_path' en la policy.")]

    resultado_ruta = _resolver_ruta_lectura(repo_root, evidence_path_raw)
    if resultado_ruta.tecnico:
        return [checks.CheckResult(checks.STATUS_FAIL, codigo, resultado_ruta.motivo, kind=checks.KIND_TECHNICAL_ERROR)]
    if not resultado_ruta.ok:
        return [checks.CheckResult(
            checks.STATUS_FAIL, codigo,
            f"baseline.evidence_path={evidence_path_raw!r} no es legible: {resultado_ruta.motivo}",
        )]

    ruta_absoluta = resultado_ruta.ruta_absoluta
    if not ruta_absoluta.exists() or not ruta_absoluta.is_file():
        return [checks.CheckResult(
            checks.STATUS_FAIL, codigo,
            f"baseline.evidence_path={evidence_path_raw!r} no existe o no es un archivo.",
        )]

    size = ruta_absoluta.stat().st_size
    if size == 0:
        return [checks.CheckResult(
            checks.STATUS_FAIL, codigo,
            f"baseline.evidence_path={evidence_path_raw!r} está vacío (0 bytes) -- no es evidencia real.",
        )]

    hash_declarado = baseline.get("evidence_sha256")
    if hash_declarado:
        hash_actual = _hash_binario_sha256(ruta_absoluta)
        if hash_actual != hash_declarado:
            return [checks.CheckResult(
                checks.STATUS_FAIL, codigo,
                f"baseline.evidence_sha256 declarado no coincide con el hash actual de {evidence_path_raw!r} "
                "-- evidencia obsoleta.",
            )]
        return [checks.CheckResult(
            checks.STATUS_PASS, codigo,
            f"evidencia de baseline en {evidence_path_raw!r} existe ({size} bytes), hash sha256 verificado.",
        )]

    return [checks.CheckResult(
        checks.STATUS_PASS, codigo,
        f"evidencia de baseline en {evidence_path_raw!r} existe ({size} bytes); sin hash declarado (staleness no verificada).",
    )]


# --- Orquestador ------------------------------------------------------------

CODIGO_POLICY_ERROR = "SCI-POLICY"


def evaluar_scientific_checks(repo_root) -> list:
    """Orquesta los 7 scientific validity checks (`SCI-CUTOFF`,
    `SCI-HOLDOUT-PROTECTION`, `SCI-HOLDOUT-USAGE`, `SCI-LEAKAGE-TARGET`,
    `SCI-LEAKAGE-FORBIDDEN`, `SCI-LEAKAGE-SPLIT`, `SCI-BASELINE`), siempre de
    solo lectura, nunca lanza, determinista. Si `.harmessi/
    scientific-policy.json` está corrupto, devuelve un único `CheckResult`
    FAIL `kind=technical_error` (`SCI-POLICY`) y no evalúa nada más."""
    repo_root = Path(repo_root)
    try:
        policy = leer_policy(repo_root)
    except ScientificPolicyError as exc:
        return [checks.CheckResult(
            checks.STATUS_FAIL,
            CODIGO_POLICY_ERROR,
            f".harmessi/scientific-policy.json existe pero no es válido: {exc}",
            kind=checks.KIND_TECHNICAL_ERROR,
        )]

    registros = [
        ("SCI-CUTOFF", evaluar_cutoff, (repo_root, policy)),
        ("SCI-HOLDOUT-PROTECTION", evaluar_holdout_proteccion, (repo_root, policy)),
        ("SCI-HOLDOUT-USAGE", evaluar_holdout_uso, (repo_root, policy)),
        ("SCI-LEAKAGE-TARGET", evaluar_leakage_target, (policy,)),
        ("SCI-LEAKAGE-FORBIDDEN", evaluar_leakage_forbidden, (policy,)),
        ("SCI-LEAKAGE-SPLIT", evaluar_leakage_split, (policy,)),
        ("SCI-BASELINE", evaluar_baseline, (repo_root, policy)),
    ]
    return checks.ejecutar_checks(registros)

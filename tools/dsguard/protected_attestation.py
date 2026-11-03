"""Atestación humana de cambios en rutas Protected (Change 20261027-v015-scope-closure-corrective).

Registro append-only `openspec/changes/<id>/protected-attestations.jsonl` (una entrada JSON por
línea, encadenada por hashes). Una entrada liga change_id + ruta exacta + hash del contenido ACTUAL
del archivo (`sha256/lf/v1`) a una confirmación humana `console_confirmed`. NO es una whitelist ni
una exención general: si el archivo cambia después, el hash deja de coincidir. Detecta edición
ingenua; NO es criptografía. Módulo de datos: solo stdlib + `core`; el T1 lo pide el CLI.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from . import core
from .scope_amendments import (
    CAMPOS_T1, CANAL_REQUERIDO, FORMATO_UTC, MAX_MOTIVO, MAX_USUARIO, _fecha_valida,
    _json_canonico, _sha256, _utc_valido, texto_con_caracteres_de_control,
)

SCHEMA_VERSION = 1
NOMBRE_ARCHIVO = "protected-attestations.jsonl"
ALGORITMO = "sha256/lf/v1"

# Protegidas de `sdd._ALCANCE_RUTAS_PROTEGIDAS` sin el centinela `data/raw/x`.
RUTAS_ATESTABLES = (
    ".claude/guardrails.json",
    ".claude/settings.json",
    ".claude/settings.local.json",
)

COD_ATESTADA = "ALCANCE-PROTEGIDA-ATESTADA"
COD_SIN_ATESTACION = "ALCANCE-PROTEGIDA-SIN-ATESTACION"
COD_HASH_DISTINTO = "ALCANCE-PROTEGIDA-HASH-DISTINTO"

CLAVES_ENTRADA = frozenset({
    "schema_version", "seq", "utc", "change_id", "ruta", "content_hash", "algoritmo",
    "motivo", "usuario", "fecha_declarada", "approval_channel", "confirmed_at",
    "channel_version", "prev_hash", "entry_hash",
})
_RE_HEX64 = re.compile(r"[0-9a-f]{64}")


def ruta_archivo(change_dir) -> Path:
    return Path(change_dir) / NOMBRE_ARCHIVO


def hash_entrada(entrada: dict) -> str:
    """sha256 del JSON canónico de la entrada SIN `entry_hash`."""
    return _sha256(_json_canonico({k: v for k, v in entrada.items() if k != "entry_hash"}))


def hash_contenido(path) -> Optional[str]:
    """Hash `sha256/lf/v1` del archivo; None si no existe o no es legible."""
    try:
        p = Path(path)
        if not p.is_file():
            return None
        return core.hash_lf_v1(p)
    except (OSError, UnicodeDecodeError):
        return None


def hash_binding(change_id: str, ruta_rel: str, content_hash: str, motivo: str) -> str:
    """sha256 canónico del payload {change_id, ruta, content_hash, motivo}."""
    return _sha256(_json_canonico({
        "change_id": change_id, "ruta": ruta_rel,
        "content_hash": content_hash, "motivo": motivo,
    }))


# --- Validación de la cadena -------------------------------------------------

def _validar_entrada(e: dict, idx: int, prev_hash: str) -> Optional[str]:
    if type(e["schema_version"]) is not int or e["schema_version"] != SCHEMA_VERSION:
        return "schema_version no soportada"
    if not isinstance(e["seq"], int) or isinstance(e["seq"], bool) or e["seq"] != idx:
        return f"seq fuera de orden o con huecos (esperado {idx})"
    if e["prev_hash"] != prev_hash:
        return "prev_hash no coincide con la entrada anterior"
    for clave, maximo in (("motivo", MAX_MOTIVO), ("usuario", MAX_USUARIO)):
        if not isinstance(e[clave], str) or not e[clave].strip():
            return f"{clave} ausente o vacío"
        if len(e[clave]) > maximo:
            return f"{clave} excede {maximo} caracteres"
        if texto_con_caracteres_de_control(e[clave]):
            return f"{clave} con caracteres de control/formato"
    if not _fecha_valida(e["fecha_declarada"]):
        return "fecha_declarada inválida (se espera AAAA-MM-DD)"
    for clave in ("utc", "confirmed_at"):
        if not _utc_valido(e[clave]):
            return f"{clave} con formato inválido (se espera {FORMATO_UTC})"
    if not isinstance(e["entry_hash"], str) or e["entry_hash"] != hash_entrada(e):
        return "entry_hash incorrecto (entrada alterada)"
    if e["approval_channel"] != CANAL_REQUERIDO:
        return "approval_channel distinto de console_confirmed"
    if not isinstance(e["channel_version"], str) or not e["channel_version"]:
        return "channel_version ausente"
    if not isinstance(e["change_id"], str) or not e["change_id"]:
        return "change_id ausente"
    if not isinstance(e["ruta"], str) or e["ruta"] not in RUTAS_ATESTABLES:
        return "ruta no atestable"
    if not isinstance(e["content_hash"], str) or not _RE_HEX64.fullmatch(e["content_hash"]):
        return "content_hash inválido (se espera sha256 hex de 64)"
    if e["algoritmo"] != ALGORITMO:
        return "algoritmo no soportado"
    return None


def _validar_cadena(texto: str) -> tuple:
    """`(entradas, errores)` del contenido completo."""
    errores: list = []
    entradas: list = []
    lineas = texto.split("\n")
    if lineas and lineas[-1] == "":
        lineas.pop()
    prev_hash = ""
    for idx, linea in enumerate(lineas, start=1):
        pre = f"línea {idx}: "
        try:
            e = json.loads(linea)
        except (ValueError, RecursionError):
            errores.append(pre + "JSON inválido")
            break
        if not isinstance(e, dict):
            errores.append(pre + "la entrada no es un objeto JSON")
            break
        if set(e.keys()) != CLAVES_ENTRADA:
            errores.append(pre + "claves inesperadas o faltantes")
            break
        problema = _validar_entrada(e, idx, prev_hash)
        if problema:
            errores.append(pre + problema)
            break
        entradas.append(e)
        prev_hash = e["entry_hash"]
    return entradas, errores


@dataclass(frozen=True)
class EstadoAtestaciones:
    valido: bool
    entradas: tuple
    errores: tuple


def estado_atestaciones(change_dir) -> EstadoAtestaciones:
    """Fail-closed: ausente = válido sin entradas; ilegible o inválido = inválido."""
    path = ruta_archivo(change_dir)
    if not path.exists():
        return EstadoAtestaciones(True, (), ())
    try:
        texto = path.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return EstadoAtestaciones(False, (), (f"archivo ilegible ({type(exc).__name__})",))
    entradas, errores = _validar_cadena(texto)
    if errores:
        return EstadoAtestaciones(False, (), tuple(errores))
    return EstadoAtestaciones(True, tuple(entradas), ())


# --- Plan --------------------------------------------------------------------

@dataclass(frozen=True)
class PlanAtestacion:
    change_id: str
    ruta: str
    content_hash: str
    hash_binding: str
    motivo: str
    usuario: str
    errores: tuple


def planificar_atestacion(change_dir, change_id, ruta_rel, repo_root, motivo, usuario) -> PlanAtestacion:
    """Calcula el plan desde disco (función sin efectos). `errores` vacío => aplicable."""
    errores: list = []
    if ruta_rel not in RUTAS_ATESTABLES:
        errores.append(f"ruta no atestable: {ruta_rel!r} (permitidas: {', '.join(RUTAS_ATESTABLES)})")
    estado = estado_atestaciones(change_dir)
    if not estado.valido:
        errores.append("el registro de atestaciones es inválido: " + "; ".join(estado.errores))
    h = None
    if ruta_rel in RUTAS_ATESTABLES:
        h = hash_contenido(Path(repo_root) / ruta_rel)
        if h is None:
            errores.append(f"el archivo no existe o no es legible: {ruta_rel}")
    h = h or ""
    binding = hash_binding(change_id, ruta_rel, h, motivo) if h else ""
    return PlanAtestacion(change_id, ruta_rel, h, binding, motivo, usuario, tuple(errores))


# --- Aplicación atómica ------------------------------------------------------

def aplicar_atestacion(change_dir, plan: PlanAtestacion, *, usuario: str, fecha,
                       campos_t1: dict, utc: Optional[str] = None) -> dict:
    """Agrega la entrada de forma atómica. ValueError si algo no cuadra (nada se escribe)."""
    change_dir = Path(change_dir)
    if plan.errores or not plan.content_hash:
        raise ValueError("el plan no es aplicable (con errores)")
    if not isinstance(campos_t1, dict) or set(campos_t1.keys()) != set(CAMPOS_T1):
        raise ValueError("campos_t1 debe tener exactamente approval_channel, confirmed_at y channel_version")
    if campos_t1["approval_channel"] != CANAL_REQUERIDO:
        raise ValueError("approval_channel debe ser console_confirmed")
    for k in ("confirmed_at", "channel_version"):
        if not isinstance(campos_t1[k], str) or not campos_t1[k]:
            raise ValueError("campos_t1 incompletos")

    path = ruta_archivo(change_dir)
    previo, entradas = "", []
    bytes_iniciales: Optional[bytes] = None
    if path.exists():
        try:
            bytes_iniciales = path.read_bytes()
            previo = bytes_iniciales.decode("utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise ValueError(f"registro ilegible ({type(exc).__name__})") from exc
        entradas, errores = _validar_cadena(previo)
        if errores:
            raise ValueError("registro de atestaciones inválido: " + "; ".join(errores))

    entrada = {
        "schema_version": SCHEMA_VERSION,
        "seq": len(entradas) + 1,
        "utc": utc or datetime.now(timezone.utc).strftime(FORMATO_UTC),
        "change_id": plan.change_id,
        "ruta": plan.ruta,
        "content_hash": plan.content_hash,
        "algoritmo": ALGORITMO,
        "motivo": plan.motivo,
        "usuario": usuario,
        "fecha_declarada": fecha,
        "approval_channel": campos_t1["approval_channel"],
        "confirmed_at": campos_t1["confirmed_at"],
        "channel_version": campos_t1["channel_version"],
        "prev_hash": entradas[-1]["entry_hash"] if entradas else "",
    }
    entrada["entry_hash"] = hash_entrada(entrada)

    if previo and not previo.endswith("\n"):
        previo += "\n"
    nuevo = previo + json.dumps(entrada, sort_keys=True, ensure_ascii=False) + "\n"

    change_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp_nombre = tempfile.mkstemp(dir=str(change_dir), prefix=".protected-attestations-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(nuevo.encode("utf-8"))
            fh.flush()
            os.fsync(fh.fileno())
        with open(tmp_nombre, "rb") as fh:
            _ents, errs = _validar_cadena(fh.read().decode("utf-8"))
        if errs:
            raise ValueError("la cadena resultante es inválida: " + "; ".join(errs))
        try:
            actuales = path.read_bytes() if path.exists() else None
        except OSError as exc:
            raise ValueError(f"no se pudo releer el registro ({type(exc).__name__})") from exc
        if actuales != bytes_iniciales:
            raise ValueError("el registro de atestaciones cambió durante la operación; se aborta sin escribir")
        os.replace(tmp_nombre, path)
    except BaseException:
        try:
            os.unlink(tmp_nombre)
        except OSError:
            pass
        raise
    return entrada


# --- Evaluación --------------------------------------------------------------

def evaluar_atestacion(change_dir, change_id, ruta_rel, repo_root) -> tuple:
    """`(codigo, mensaje)`. ATESTADA solo con cadena válida y una entrada que liga
    change_id + ruta exacta + hash del contenido ACTUAL del archivo."""
    if change_dir is None:
        return COD_SIN_ATESTACION, f"Ruta protegida sin atestación humana (Change sin directorio resoluble): {ruta_rel}"
    estado = estado_atestaciones(change_dir)
    if not estado.valido:
        return COD_SIN_ATESTACION, (
            f"Ruta protegida sin atestación válida: {ruta_rel} (registro de atestaciones inválido: "
            + "; ".join(estado.errores) + ")"
        )
    propias = [e for e in estado.entradas if e["change_id"] == change_id and e["ruta"] == ruta_rel]
    if not propias:
        return COD_SIN_ATESTACION, (
            f"Ruta protegida modificada sin atestación humana: {ruta_rel}; "
            "usá `ds_guard scope attest-protected`."
        )
    actual = hash_contenido(Path(repo_root) / ruta_rel)
    if actual is not None and any(e["content_hash"] == actual for e in propias):
        return COD_ATESTADA, f"Ruta protegida atestada por humano (hash {actual[:12]}): {ruta_rel}"
    return COD_HASH_DISTINTO, (
        f"Ruta protegida con atestación pero el contenido actual difiere del atestado: {ruta_rel}; "
        "reatestá con `ds_guard scope attest-protected`."
    )

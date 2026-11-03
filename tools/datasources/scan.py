"""Escaneo por patrón de secretos y localizadores físicos (R19).

Puro sobre dicts (sin I/O). Por patrón, best-effort: NO es un reemplazo de
`pathguard` (la garantía fuerte de secretos en archivos `.env`/claves sigue
siendo `tools/dsguard/pathguard.py`). Las funciones de este módulo nunca
reproducen el valor sospechoso en el mensaje (`motivo`): solo describen el
tipo de hallazgo.

`scan_locators` reporta localizadores físicos absolutos allí donde aparezcan;
es responsabilidad de quien llama decidir si el contexto permite rutas
repo-relativas (p. ej. `options` del registro las permite; una observación
persistida no admite ninguna, ni siquiera relativa con `..`, ver R19/R20 --
ese criterio adicional de `..` lo aplica el llamador, no esta función).
"""
from __future__ import annotations

import re
from typing import Any

from .core import CODE_ABSOLUTE_PATH, CODE_DSN_DETECTED, CODE_SECRET_DETECTED

# ---------------------------------------------------------------------------
# Secretos
# ---------------------------------------------------------------------------

_CLAVES_SOSPECHOSAS = (
    "password",
    "passwd",
    "pwd",
    "token",
    "secret",
    "apikey",
    "accesskey",
    "privatekey",
    "credential",
)

# Claves que, aunque largas/hex, no se marcan por valor (hash/checksum).
# `fingerprint` se incluye a propósito: `fingerprint.value`/`fingerprint.algorithm`
# (forma de `dataset.fingerprint` en `SourceObservation`, R5) son siempre
# evidencia de hashing, nunca un secreto, aunque ni la clave del campo
# (`value`/`algorithm`) ni serían detectadas solo con "hash"/"sha" en su
# propio nombre.
_CLAVES_HASH = ("hash", "sha", "fingerprint")

_RE_PREFIJO_CREDENCIAL = re.compile(r"^(AKIA|ghp_|xox|sk-)")
_RE_PEM = re.compile(r"-----BEGIN")
_RE_JWT = re.compile(r"^eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$")
_RE_HEX_LARGO = re.compile(r"^[0-9a-fA-F]{32,}$")
_RE_BASE64_LARGO = re.compile(r"^[A-Za-z0-9+/=]{32,}$")

_RE_DSN_ESQUEMA = re.compile(r"[a-z][a-z0-9+.\-]*://[^/\s:]+:[^/\s@]+@")
_RE_DSN_SERVER_PASSWORD = re.compile(r"password\s*=", re.IGNORECASE)
_RE_DSN_POSTGRES = re.compile(r"^postgres(ql)?://", re.IGNORECASE)
_RE_DSN_JDBC_PASSWORD = re.compile(r"jdbc:.*password", re.IGNORECASE | re.DOTALL)

# Localizadores físicos absolutos.
_RE_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:[\\/]")
_RE_UNC = re.compile(r"^\\\\")
_RE_FILE_URI = re.compile(r"^file://")


def _normalizar_clave(clave: str) -> str:
    return clave.casefold().replace("-", "").replace("_", "")


def _clave_es_hash(clave: str) -> bool:
    normalizada = _normalizar_clave(clave)
    return any(marcador in normalizada for marcador in _CLAVES_HASH)


def _clave_sospechosa(clave: str) -> bool:
    normalizada = _normalizar_clave(clave)
    return any(marcador in normalizada for marcador in _CLAVES_SOSPECHOSAS)


def _valor_forma_credencial(valor: str, clave_es_hash: bool) -> bool:
    if _RE_PREFIJO_CREDENCIAL.match(valor):
        return True
    if _RE_PEM.search(valor):
        return True
    if _RE_JWT.match(valor):
        return True
    if not clave_es_hash:
        if _RE_HEX_LARGO.match(valor) or _RE_BASE64_LARGO.match(valor):
            return True
    return False


def _valor_forma_dsn(valor: str) -> bool:
    if _RE_DSN_ESQUEMA.search(valor):
        return True
    if _RE_DSN_SERVER_PASSWORD.search(valor):
        return True
    if _RE_DSN_POSTGRES.match(valor):
        return True
    if _RE_DSN_JDBC_PASSWORD.search(valor):
        return True
    return False


def _json_pointer(path: str, clave: Any) -> str:
    fragmento = str(clave).replace("~", "~0").replace("/", "~1")
    return f"{path}/{fragmento}"


def scan_secrets(obj: Any, path: str = "$", padre_es_hash: bool = False) -> list:
    """Recorre `obj` (dict/list/escalares) buscando claves de nombre
    sospechoso y valores con forma de credencial o de DSN. Devuelve
    `[(code, json_pointer, motivo), ...]` sin reproducir el valor.

    La exención "clave nombrada como hash/sha/fingerprint" (R19) aplica
    SOLO al hijo inmediato de una clave hash: al evaluar un nodo, la
    exención efectiva es `_clave_es_hash(clave_de_este_nodo) or
    padre_es_hash` (si el PADRE INMEDIATO de este nodo tenía clave
    hash/sha/fingerprint) -- cubre la forma `fingerprint.value` de la
    observación (un hijo inmediato de `fingerprint`). NO se propaga más
    allá de ese hijo inmediato: al recursar hacia los HIJOS de este nodo se
    les pasa `padre_es_hash = _clave_es_hash(clave_de_este_nodo)`, evaluado
    en ESTE nivel únicamente (nunca acumulado desde niveles superiores) --
    un nieto de una clave hash (hijo de un hijo) ya NO hereda la exención."""
    hallazgos: list = []
    if isinstance(obj, dict):
        for clave, valor in obj.items():
            ruta = _json_pointer(path, clave)
            clave_str = clave if isinstance(clave, str) else str(clave)
            clave_es_hash_aqui = _clave_es_hash(clave_str)
            es_hash = clave_es_hash_aqui or padre_es_hash
            if _clave_sospechosa(clave_str):
                hallazgos.append(
                    (CODE_SECRET_DETECTED, ruta, "clave con nombre sospechoso de credencial")
                )
            elif isinstance(valor, str):
                if _valor_forma_credencial(valor, es_hash):
                    hallazgos.append(
                        (CODE_SECRET_DETECTED, ruta, "valor con forma de credencial")
                    )
                elif _valor_forma_dsn(valor):
                    hallazgos.append((CODE_DSN_DETECTED, ruta, "valor con forma de DSN"))
            hallazgos.extend(scan_secrets(valor, ruta, clave_es_hash_aqui))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            hallazgos.extend(scan_secrets(item, _json_pointer(path, i), padre_es_hash))
    elif isinstance(obj, str):
        if _valor_forma_dsn(obj):
            hallazgos.append((CODE_DSN_DETECTED, path, "valor con forma de DSN"))
    return hallazgos


def scan_locators(obj: Any, path: str = "$") -> list:
    """Recorre `obj` buscando localizadores físicos absolutos (`C:\\...`,
    UNC `\\\\...`, `file://...`, `/algo/algo...`). Devuelve
    `[(code, json_pointer, motivo), ...]`."""
    hallazgos: list = []
    if isinstance(obj, dict):
        for clave, valor in obj.items():
            ruta = _json_pointer(path, clave)
            if isinstance(valor, str) and _es_ruta_absoluta(valor):
                hallazgos.append((CODE_ABSOLUTE_PATH, ruta, "valor con forma de ruta absoluta"))
            hallazgos.extend(scan_locators(valor, ruta))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            ruta = _json_pointer(path, i)
            if isinstance(item, str) and _es_ruta_absoluta(item):
                hallazgos.append((CODE_ABSOLUTE_PATH, ruta, "valor con forma de ruta absoluta"))
            hallazgos.extend(scan_locators(item, ruta))
    elif isinstance(obj, str):
        if _es_ruta_absoluta(obj):
            hallazgos.append((CODE_ABSOLUTE_PATH, path, "valor con forma de ruta absoluta"))
    return hallazgos


def _es_ruta_absoluta(valor: str) -> bool:
    if _RE_WINDOWS_DRIVE.match(valor):
        return True
    if _RE_UNC.match(valor):
        return True
    if _RE_FILE_URI.match(valor):
        return True
    if valor.startswith("/") and len(valor) > 1 and valor[1] != "/" and "/" in valor[1:]:
        return True
    return False

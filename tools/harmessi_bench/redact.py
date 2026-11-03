"""Redacción best-effort de texto antes de persistirlo (v0.13 Change 2).

Reemplaza rutas de usuario, emails y tokens por marcadores fijos. Es una
reducción de fugas accidentales, NO una garantía criptográfica: las regex de
tokens no son exhaustivas y se prefiere sobre-redactar a dejar pasar. Puro:
solo `re`; sin providers, red ni `subprocess`; nunca escribe archivos.
Todas las regex tienen cuantificadores acotados donde importa (anti-ReDoS).
"""
from __future__ import annotations

import re

MARCADOR_RUTA = "<RUTA_USUARIO>"
MARCADOR_EMAIL = "<EMAIL>"
MARCADOR_TOKEN = "<TOKEN>"

# Rutas de usuario. Windows (`X:\Users\<n>\...`, `/` o 1-4 barras por
# separador, como en un JSON escapado); el nombre puede tener espacios y llega
# hasta el siguiente separador de ruta. POSIX `/home/<n>/` y `/Users/<n>/` sin
# distinguir mayúsculas. Se reemplaza la ruta completa.
_RE_RUTA_WINDOWS = re.compile(
    r"[A-Za-z]:[\\/]{1,4}Users[\\/]{1,4}[^\\/\r\n\"'<>|]+(?:[\\/]+[^\s\"'<>|]*)?",
    re.IGNORECASE,
)
_RE_RUTA_POSIX = re.compile(r"/(?:home|users)/[^/\s\"'<>|]+(?:/[^\s\"'<>|]*)?", re.IGNORECASE)

# Local-part acotado a 64 caracteres (anti-ReDoS sobre entradas largas).
_RE_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]{1,64}@[A-Za-z0-9.\-]{1,255}\.[A-Za-z]{2,24}")

# Tokens con prefijo conocido (incluye JWT `eyJ...`).
_RE_TOKENS_PREFIJO = (
    re.compile(r"\bsk-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{8,}"),
    re.compile(r"\bgh[opsur]_[A-Za-z0-9]{8,}"),
    re.compile(r"\bglpat-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"\bhf_[A-Za-z0-9]{8,}"),
    re.compile(r"\bnpm_[A-Za-z0-9]{8,}"),
    re.compile(r"\bAIza[0-9A-Za-z_\-]{20,}"),
    re.compile(r"\bAKIA[0-9A-Z]{8,}"),
    re.compile(r"\bxox[A-Za-z]-[A-Za-z0-9\-]{8,}"),
    re.compile(r"\beyJ[A-Za-z0-9_\-]{5,}\.[A-Za-z0-9_\-]{5,}\.[A-Za-z0-9_\-]{0,512}"),
    re.compile(r"\bbearer\s+[A-Za-z0-9._~+/=\-]{8,}", re.IGNORECASE),
)

# JSON/dict: `"api_key": "valor"` (comillas simples o dobles, cualquier
# longitud >= 1). Se conserva la clave y se redacta el valor.
_RE_JSON_CLAVE = re.compile(
    r"""((["'])[A-Za-z0-9_\-]{0,40}(?:key|token|secret|password)[A-Za-z0-9_\-]{0,40}\2\s*:\s*)(["'])[^"'\r\n]+\3""",
    re.IGNORECASE,
)

# `key|token|secret|password` seguido de `=` o `:` y una cadena larga
# hex/base64 (>= 16 caracteres). Se conserva el prefijo, se redacta el valor.
_RE_CLAVE_VALOR = re.compile(
    r"((?:key|token|secret|password)\s*[=:]\s*[\"']?)[A-Za-z0-9+/_=\-]{16,}",
    re.IGNORECASE,
)


def redactar_texto(texto):
    """Devuelve `texto` con rutas de usuario, emails y tokens reemplazados por
    marcadores. Idempotente (los marcadores no vuelven a coincidir). Un valor
    no-str (incluido `None`) se devuelve intacto. Nunca lanza."""
    if not isinstance(texto, str):
        return texto
    try:
        resultado = _RE_RUTA_WINDOWS.sub(MARCADOR_RUTA, texto)
        resultado = _RE_RUTA_POSIX.sub(MARCADOR_RUTA, resultado)
        for patron in _RE_TOKENS_PREFIJO:
            resultado = patron.sub(MARCADOR_TOKEN, resultado)
        resultado = _RE_JSON_CLAVE.sub(lambda m: m.group(1) + m.group(3) + MARCADOR_TOKEN + m.group(3), resultado)
        resultado = _RE_CLAVE_VALOR.sub(lambda m: m.group(1) + MARCADOR_TOKEN, resultado)
        resultado = _RE_EMAIL.sub(MARCADOR_EMAIL, resultado)
        return resultado
    except Exception:  # noqa: BLE001 - fail-closed: ante un fallo inesperado no se devuelve el original
        return "<REDACCION_FALLIDA>"

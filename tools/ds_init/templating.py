"""Sustitución de placeholders y manejo del bloque delimitado idempotente para
`CLAUDE.md` (R9). Solo `str.replace`/regex simple — sin motor de templating de
terceros (R13, alternativa descartada en `design.md`).
"""
from __future__ import annotations

import re

PLACEHOLDERS_CONOCIDOS = (
    "NOMBRE_PROYECTO",
    "NOTEBOOKS_DIR",
    "VENV_DIR",
    "FECHA_INSTALACION",
    "HARNESS_VERSION",
)

_PATRON_PLACEHOLDER_PENDIENTE = re.compile(r"\{\{\s*[A-Za-z0-9_]+\s*\}\}")

_MARCADOR_INICIO_TPL = "<!-- ds_init:inicio v{version} -->"
_MARCADOR_FIN = "<!-- ds_init:fin -->"
_PATRON_BLOQUE = re.compile(
    r"<!-- ds_init:inicio v[^>]*-->.*?<!-- ds_init:fin -->",
    re.DOTALL,
)


def renderizar(texto: str, contexto: dict) -> str:
    """Sustituye cada `{{CLAVE}}` presente en `texto` por `contexto[CLAVE]`,
    vía `str.replace` simple (sin lógica condicional, R13). Claves de
    `contexto` que no aparecen en `texto` se ignoran; placeholders en `texto`
    sin entrada en `contexto` quedan intactos (los detecta luego
    `verificar_sin_placeholders_pendientes`)."""
    resultado = texto
    for clave, valor in contexto.items():
        resultado = resultado.replace("{{" + clave + "}}", str(valor))
    return resultado


def verificar_sin_placeholders_pendientes(texto: str) -> bool:
    """`True` si `texto` no contiene ningún `{{...}}` sin resolver. Se usa en
    la validación de staging (R11) antes de mover nada al destino final."""
    return _PATRON_PLACEHOLDER_PENDIENTE.search(texto) is None


def insertar_bloque_claude_md(existente: str, bloque: str, version: str) -> str:
    """Inserta (o reemplaza in place, si ya existe) un bloque delimitado por
    `<!-- ds_init:inicio v<version> -->` / `<!-- ds_init:fin -->` en
    `existente` (R9). Idempotente: una segunda corrida con el mismo bloque no
    duplica nada, solo reemplaza el contenido delimitado previo."""
    marcador_inicio = _MARCADOR_INICIO_TPL.format(version=version)
    bloque_completo = f"{marcador_inicio}\n{bloque.strip()}\n{_MARCADOR_FIN}"

    if _PATRON_BLOQUE.search(existente):
        return _PATRON_BLOQUE.sub(bloque_completo, existente, count=1)

    separador = "\n\n" if existente and not existente.endswith("\n\n") else ""
    if existente and not existente.endswith("\n"):
        existente = existente + "\n"
    return f"{existente}{separador}{bloque_completo}\n"

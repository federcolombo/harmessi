"""Fingerprint de identidad de contenido de `--input`: sha256 de los bytes
crudos del archivo (a diferencia de `dsguard.core.hash_lf_v1`, que normaliza
texto a LF -- un dataset es binario/tabular, no un archivo de texto SDD, así
que acá no corresponde ninguna normalización de línea).

Local a `ds_profile` a propósito (`design.md`, "Alternativas descartadas"):
no se agrega a `dsguard/core.py` para no ampliar esa dependencia compartida
sin necesidad real hoy.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

ALGORITMO = "sha256/bin/v1"


def calcular_fingerprint(ruta: Path, chunk_size: int = 1 << 20) -> dict:
    """`{"algoritmo": "sha256/bin/v1", "hash": <hexdigest>}`. Lee el archivo
    en chunks binarios de `chunk_size` bytes -- nunca el archivo completo en
    memoria a la vez."""
    hasher = hashlib.sha256()
    with open(Path(ruta), "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            hasher.update(chunk)
    return {"algoritmo": ALGORITMO, "hash": hasher.hexdigest()}

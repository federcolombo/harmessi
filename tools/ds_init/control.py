"""Archivo de control de la instalación (R12): `<destino>/.ds_init/control.json`
con versión del harness, perfil, fecha UTC, configuración elegida y el hash
SHA-256 de cada archivo efectivamente instalado.

Se genera una única vez, al final de una instalación exitosa (`writer.py`,
después de que el staging ya fue eliminado) — los hashes se calculan sobre el
archivo real ya en su ubicación final del destino, nunca sobre la copia de
staging (AC13 de `spec.md`).
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from .version import HARNESS_VERSION

NOMBRE_ARCHIVO_CONTROL = "control.json"
DIR_CONTROL = ".ds_init"


def _sha256_de_archivo(ruta: Path) -> str:
    """Hash SHA-256 en hex de `ruta`, leído en bloques (no carga el archivo
    completo en memoria de una vez)."""
    hasher = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(65536), b""):
            hasher.update(bloque)
    return hasher.hexdigest()


def generar_control(destino, perfil: str, config: dict, archivos_aplicados: list) -> dict:
    """Arma el archivo de control de una instalación exitosa y lo escribe en
    `<destino>/.ds_init/control.json` (creando el directorio `.ds_init/` si
    hace falta). Devuelve el dict escrito.

    - `destino`: raíz del repo instalado (str o `Path`).
    - `perfil`: identificador público de perfil (p. ej. `python-jupyter-data`).
    - `config`: dict de configuración de la corrida; se usan las claves
      `nombre`, `notebooks_dir` y `venv_dir`. La clave `destino` del control
      (bajo `configuracion`) se registra siempre como `"."`, una referencia
      portable relativa a la raiz del propio repo instalado: el archivo de
      control ya vive dentro de ese destino
      (`<destino>/.ds_init/control.json`), por lo que grabar una ruta
      absoluta de una maquina/usuario particular no aporta informacion
      necesaria.
    - `archivos_aplicados`: rutas relativas (al destino) de los archivos ya
      escritos en su ubicación final — el hash se calcula leyendo cada uno de
      esos archivos reales.
    """
    destino = Path(destino)

    archivos = []
    for ruta_relativa in archivos_aplicados:
        ruta_absoluta = destino / ruta_relativa
        archivos.append(
            {
                "ruta": ruta_relativa,
                "sha256": _sha256_de_archivo(ruta_absoluta),
            }
        )

    control = {
        "harness_version": HARNESS_VERSION,
        "perfil": perfil,
        "fecha_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "configuracion": {
            "nombre": config.get("nombre"),
            "notebooks_dir": config.get("notebooks_dir"),
            "venv_dir": config.get("venv_dir"),
            "destino": ".",
        },
        "archivos": archivos,
    }

    dir_control = destino / DIR_CONTROL
    dir_control.mkdir(parents=True, exist_ok=True)
    ruta_control = dir_control / NOMBRE_ARCHIVO_CONTROL
    with open(ruta_control, "w", encoding="utf-8", newline="") as f:
        json.dump(control, f, indent=2, ensure_ascii=False)
        f.write("\n")

    return control

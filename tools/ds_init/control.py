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
from typing import Optional

from .version import HARNESS_VERSION

NOMBRE_ARCHIVO_CONTROL = "control.json"
DIR_CONTROL = ".ds_init"


def sha256_de_archivo(ruta: Path) -> str:
    """Hash SHA-256 en hex de `ruta`, leído en bloques (no carga el archivo
    completo en memoria de una vez). Pública: la reusa también
    `tools/harmessi/doctor.py` para el check de drift de archivos
    administrados, sin duplicar la lógica de hashing."""
    hasher = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(65536), b""):
            hasher.update(bloque)
    return hasher.hexdigest()


def generar_control(
    destino,
    perfil: str,
    config: dict,
    archivos_aplicados: list,
    fecha_utc: Optional[str] = None,
) -> dict:
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
    - `fecha_utc`: valor literal opcional para el campo `fecha_utc` del
      control. Si no se pasa (o es `None`), se estampa
      `datetime.now(timezone.utc)` como hasta ahora — comportamiento sin
      cambios para quien no pase este parámetro (p. ej. `writer.py`, que
      sigue llamando posicionalmente con 4 argumentos).
    """
    destino = Path(destino)

    archivos = []
    for ruta_relativa in archivos_aplicados:
        ruta_absoluta = destino / ruta_relativa
        archivos.append(
            {
                "ruta": ruta_relativa,
                "sha256": sha256_de_archivo(ruta_absoluta),
            }
        )

    control = {
        "harness_version": HARNESS_VERSION,
        "perfil": perfil,
        "fecha_utc": fecha_utc
        if fecha_utc is not None
        else datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
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


def regenerar_control(destino, control_previo: dict, *, perfil: Optional[str] = None) -> dict:
    """Recalcula y reescribe `<destino>/.ds_init/control.json` a partir de un
    `control_previo` ya existente, para recalibrar `harness_version` y
    `archivos` cuando quedaron desactualizados respecto del manifiesto
    vigente (p. ej. tras agregar archivos administrados por el harness
    directamente al repo sin pasar por una reinstalación).

    No reinstala nada: asume que los archivos administrados ya existen en
    `destino`, y solo recalcula sus hashes reales.

    - `destino`: raíz del repo instalado (str o `Path`).
    - `control_previo`: dict con el contenido previo de `control.json` (p.
      ej. cargado de disco). Se usan sus claves `perfil` (si no se pasa
      `perfil` explícito), `configuracion` y `fecha_utc`.
    - `perfil` (solo keyword): perfil a usar para recalcular el manifiesto.
      Si no se pasa, se usa `control_previo["perfil"]`.

    Comportamiento:
    - `configuracion` se preserva exactamente igual a la de `control_previo`
      (se delega en `generar_control`, que la reconstruye a partir de
      `control_previo["configuracion"]`).
    - `fecha_utc` se preserva exactamente igual a la de `control_previo` —
      no se retro-corrige la fecha de instalación original.
    - `harness_version` se actualiza al valor vigente de `HARNESS_VERSION`
      (no el de `control_previo`), porque `generar_control` siempre lo
      estampa así.
    - `archivos` se reconstruye EXCLUSIVAMENTE a partir de
      `manifest_para_perfil(perfil_efectivo)` vigente (con hashes reales
      leídos de `destino`) — nunca es una unión con
      `control_previo["archivos"]`. Cualquier entrada de
      `control_previo["archivos"]` cuya ruta ya no esté en el manifiesto
      vigente queda ausente del resultado, sin lógica extra: simplemente no
      se itera sobre `control_previo["archivos"]`.
    - Se excluye del manifiesto la entrada `.ds_init/control.json` (misma
      exclusión que ya aplica `tools/harmessi/doctor.py` al verificar
      archivos esperados), porque ese archivo se verifica aparte.
    - No introduce escritura atómica nueva: reutiliza el mismo patrón
      no-atómico de `generar_control` (escritura directa con `open`/`write`).
    """
    from .manifest import manifest_para_perfil

    perfil_efectivo = perfil or control_previo["perfil"]

    archivos_aplicados = [
        entrada.destino
        for entrada in manifest_para_perfil(perfil_efectivo)
        if entrada.destino != ".ds_init/control.json"
    ]

    return generar_control(
        destino,
        perfil_efectivo,
        control_previo["configuracion"],
        archivos_aplicados,
        fecha_utc=control_previo.get("fecha_utc"),
    )

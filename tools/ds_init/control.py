"""Archivo de control de la instalación (R12): `<destino>/.ds_init/control.json`
con versión del harness, perfil, fecha UTC, configuración elegida y el hash
SHA-256 de cada archivo efectivamente instalado.

Se genera una única vez, al final de una instalación exitosa (`writer.py`,
después de que el staging ya fue eliminado) — los hashes se calculan sobre el
archivo real ya en su ubicación final del destino, nunca sobre la copia de
staging (AC13 de `spec.md`).
"""
from __future__ import annotations

import json
import os
import shutil
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from . import managed_hash
from . import manifest as manifest_mod
from .version import HARNESS_VERSION

NOMBRE_ARCHIVO_CONTROL = "control.json"
DIR_CONTROL = ".ds_init"

_RUTA_CONTROL_EN_MANIFIESTO = ".ds_init/control.json"


def sha256_de_archivo(ruta: Path) -> str:
    """Hash SHA-256 CRUDO (bytes exactos) en hex de `ruta`, leído en bloques
    (no carga el archivo completo en memoria de una vez).

    Se conserva sin cambios de comportamiento por compatibilidad legacy, pero
    YA NO es el hash managed: el hash de los archivos administrados se calcula
    con `managed_hash.hash_managed_file` y se verifica con
    `managed_hash.verificar_entrada` (insensible a diferencias de EOL)."""
    return managed_hash.hash_crudo_file(ruta)


def generar_control(
    destino,
    perfil: str,
    config: dict,
    archivos_aplicados: list,
    fecha_utc: Optional[str] = None,
    installation_stage: Optional[str] = None,
    capabilities_habilitadas=None,
    entradas_conservadas=None,
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
    - `installation_stage`: opcional (Change 7 v0.3, R5 de `spec.md`). Si no
      es `None`, se agrega la clave `"installation_stage"` al dict resultante.
      Si es `None` (default), la clave se OMITE por completo del dict — forma
      legacy preservada byte a byte para cualquier caller que no pase este
      parámetro.
    - `capabilities_habilitadas`: opcional (M8, Change 4/Change 5 -- hallazgo
      de hardening: sin esto persistido, Doctor no puede distinguir "no
      provisionado porque la capability está deshabilitada" de "falta de
      verdad"). Iterable de strings o `None`. Si no es `None`, se agrega la
      clave `"capabilities_habilitadas"` (lista ordenada) al dict resultante.
      Si es `None` (default), la clave se OMITE por completo -- forma legacy
      preservada byte a byte para cualquier caller que no pase este
      parámetro (R5: sin esta opción, comportamiento idéntico a antes).
    - `entradas_conservadas`: opcional (modo conservador de `sync`, R27f).
      Lista de dicts de entradas previas de `archivos[]` que se copian
      VERBATIM (sin rehash) delante de las entradas nuevas. Si una ruta está
      tanto en `entradas_conservadas` como en `archivos_aplicados`, gana la
      entrada nueva (delta). Con `None` (default) no hay efecto.

    Cada entrada nueva es `{"ruta", "sha256", "hash_alg"}`: el hash se calcula
    con `managed_hash.hash_managed_file` y el algoritmo que corresponde al
    `contenido` de la entrada del manifiesto (texto -> EOL-agnóstico).
    """
    destino = Path(destino)

    nuevas = []
    for ruta_relativa in archivos_aplicados:
        ruta_absoluta = destino / ruta_relativa
        algoritmo = managed_hash.algoritmo_para_contenido(
            manifest_mod.contenido_de(ruta_relativa)
        )
        nuevas.append(
            {
                "ruta": ruta_relativa,
                "sha256": managed_hash.hash_managed_file(ruta_absoluta, algoritmo),
                "hash_alg": algoritmo,
            }
        )

    archivos = []
    if entradas_conservadas:
        rutas_nuevas = {e["ruta"] for e in nuevas}
        rutas_vistas = set()
        for previa in entradas_conservadas:
            if not isinstance(previa, dict) or "ruta" not in previa:
                continue
            ruta_previa = previa["ruta"]
            if ruta_previa in rutas_nuevas or ruta_previa in rutas_vistas:
                continue
            rutas_vistas.add(ruta_previa)
            archivos.append(dict(previa))
    archivos.extend(nuevas)

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
    if installation_stage is not None:
        control["installation_stage"] = installation_stage
    if capabilities_habilitadas is not None:
        control["capabilities_habilitadas"] = sorted(capabilities_habilitadas)

    dir_control = destino / DIR_CONTROL
    dir_control.mkdir(parents=True, exist_ok=True)
    ruta_control = dir_control / NOMBRE_ARCHIVO_CONTROL
    _escribir_control_atomico(ruta_control, control)

    return control


def _escribir_control_atomico(ruta_control: Path, control: dict) -> None:
    """Escribe `control` en `ruta_control` de forma atómica (R5 del Change
    `20261019-v011-upgrade-migration-resilience`): archivo temporal en el MISMO
    directorio + `os.replace`. Si algo falla, el temporal se elimina y el
    control original queda intacto."""
    ruta_control = Path(ruta_control)
    ruta_tmp = ruta_control.with_name(
        f"{ruta_control.name}.tmp-{os.getpid()}-{uuid.uuid4().hex[:8]}"
    )
    try:
        with open(ruta_tmp, "w", encoding="utf-8", newline="") as f:
            json.dump(control, f, indent=2, ensure_ascii=False)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(ruta_tmp, ruta_control)
    except BaseException:
        try:
            ruta_tmp.unlink()
        except OSError:
            pass
        raise


def _crear_backup_control(ruta_control: Path) -> Path:
    """Copia el control actual a `control.json.bak-<timestamp-utc>` junto al
    archivo y devuelve la ruta del backup."""
    sello = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    ruta_bak = ruta_control.with_name(f"{ruta_control.name}.bak-{sello}")
    shutil.copy2(ruta_control, ruta_bak)
    return ruta_bak


def _entradas_previas_validas(control_previo: dict) -> list:
    """Entradas de `control_previo["archivos"]` bien formadas (dict con `ruta`
    y `sha256` strings). Las malformadas se ignoran."""
    validas = []
    for entrada in (control_previo or {}).get("archivos", []) or []:
        if (
            isinstance(entrada, dict)
            and isinstance(entrada.get("ruta"), str)
            and isinstance(entrada.get("sha256"), str)
        ):
            validas.append(entrada)
    return validas


def clasificar_baseline(destino, control_previo: dict) -> dict:
    """Clasifica CADA entrada del baseline previo contra el archivo real de
    `destino`, ANTES de escribir nada (D12 del Change
    `20261008-cross-platform-managed-hashing`).

    Devuelve `{ruta: {"estado": <managed_hash.ESTADO_*>, "entrada": <dict
    previo>}}`. Las entradas malformadas se ignoran y las rutas cuyo archivo
    no existe en disco se OMITEN del resultado."""
    destino = Path(destino)
    clasificacion = {}
    for entrada in _entradas_previas_validas(control_previo):
        ruta = entrada["ruta"]
        ruta_absoluta = destino / ruta
        if not ruta_absoluta.is_file():
            continue
        try:
            estado, _detalle = managed_hash.verificar_entrada(
                ruta_absoluta, entrada, contenido=manifest_mod.contenido_de(ruta)
            )
        except OSError:
            continue
        clasificacion[ruta] = {"estado": estado, "entrada": entrada}
    return clasificacion


_ESTADOS_NO_ADOPTABLES = (managed_hash.ESTADO_DRIFT, managed_hash.ESTADO_ALG_DESCONOCIDO)


def _resolver_modo_conservador(
    destino: Path,
    rutas: list,
    control_previo: dict,
    clasificacion: dict,
    resultado,
    preexistentes=None,
) -> tuple:
    """Decide, por ruta del manifiesto vigente, si va con hash nuevo o si se
    conserva la entrada previa verbatim. Devuelve `(rutas_a_hashear,
    entradas_conservadas)`. Ver `regenerar_control` para las reglas."""
    previas = {e["ruta"]: e for e in _entradas_previas_validas(control_previo)}
    tocadas = set(getattr(resultado, "aplicados", None) or []) | set(
        getattr(resultado, "actualizados", None) or []
    )
    sin_cambios = set(getattr(resultado, "sin_cambios", None) or [])
    preexistentes = set(preexistentes) if preexistentes is not None else None

    a_hashear = []
    conservadas = []

    # Entradas previas sin `sha256` string: no se pueden clasificar ni
    # rehashear; se conservan verbatim (si el delta trae la misma ruta, gana).
    for entrada in (control_previo or {}).get("archivos", []) or []:
        if (
            isinstance(entrada, dict)
            and isinstance(entrada.get("ruta"), str)
            and not isinstance(entrada.get("sha256"), str)
        ):
            conservadas.append(entrada)

    for ruta in rutas:
        if not (destino / ruta).is_file():
            continue
        previa = previas.get(ruta)
        estado_previo = (clasificacion.get(ruta) or {}).get("estado")
        era_preexistente = preexistentes is not None and ruta in preexistentes

        if ruta in sin_cambios:
            a_hashear.append(ruta)
        elif ruta in tocadas:
            if previa is None:
                # Creado de verdad -> hash nuevo; preexistente sin baseline
                # (p. ej. merge sobre un archivo del usuario) -> no se adopta.
                if not era_preexistente:
                    a_hashear.append(ruta)
            elif estado_previo in _ESTADOS_NO_ADOPTABLES:
                conservadas.append(previa)
            elif estado_previo is None and era_preexistente:
                conservadas.append(previa)  # no clasificable (p. ej. error de E/S)
            else:
                a_hashear.append(ruta)
        elif previa is None:
            continue
        elif estado_previo in _ESTADOS_NO_ADOPTABLES or estado_previo is None:
            # drift / algoritmo desconocido / no clasificable: tal cual, sin rehash.
            conservadas.append(previa)
        elif estado_previo == managed_hash.ESTADO_OK:
            algoritmo_actual = managed_hash.algoritmo_para_contenido(
                manifest_mod.contenido_de(ruta)
            )
            if previa.get("hash_alg") == algoritmo_actual:
                conservadas.append(previa)
            else:
                a_hashear.append(ruta)
        elif estado_previo == managed_hash.ESTADO_OK_LEGACY:
            a_hashear.append(ruta)
        else:
            conservadas.append(previa)

    # Entradas fuera del manifiesto vigente: solo se conservan si son evidencia
    # de drift (drift / algoritmo desconocido); ok/ok_legacy/ausentes se descartan.
    rutas_vigentes = set(rutas)
    for ruta, previa in previas.items():
        if ruta in rutas_vigentes:
            continue
        if (clasificacion.get(ruta) or {}).get("estado") in _ESTADOS_NO_ADOPTABLES:
            conservadas.append(previa)
    return a_hashear, conservadas


def regenerar_control(
    destino,
    control_previo: dict,
    *,
    perfil: Optional[str] = None,
    stage: Optional[str] = None,
    installation_stage: Optional[str] = None,
    capabilities_habilitadas=None,
    clasificacion: Optional[dict] = None,
    resultado=None,
    preexistentes=None,
) -> dict:
    """Recalcula y reescribe `<destino>/.ds_init/control.json` a partir de un
    `control_previo` ya existente, para recalibrar `harness_version` y
    `archivos` cuando quedaron desactualizados respecto del manifiesto
    vigente (p. ej. tras agregar archivos administrados por el harness
    directamente al repo sin pasar por una reinstalación, o tras un `sync`
    de `ds_init` que amplió el bundle instalado, Change 7 v0.3).

    No reinstala nada: asume que los archivos administrados ya existen en
    `destino`, y solo recalcula sus hashes reales.

    - `destino`: raíz del repo instalado (str o `Path`).
    - `control_previo`: dict con el contenido previo de `control.json` (p.
      ej. cargado de disco). Se usan sus claves `perfil` (si no se pasa
      `perfil` explícito), `configuracion` y `fecha_utc`.
    - `perfil` (solo keyword): perfil a usar para recalcular el manifiesto.
      Si no se pasa, se usa `control_previo["perfil"]`.
    - `stage` (solo keyword, opcional, uno de `manifest.ORDEN_STAGES`): si se
      pasa, `archivos` se recalcula vía `manifest_para_perfil_y_stage(perfil,
      stage)` en vez de `manifest_para_perfil(perfil)` — R5 de `spec.md`.
    - `installation_stage` (solo keyword, opcional): si se pasa, se usa tal
      cual como el nuevo `installation_stage` del control regenerado. Si es
      `None` (default), se preserva `control_previo.get("installation_stage")`
      — nunca se borra un valor existente por el solo hecho de omitir este
      parámetro.
    - `capabilities_habilitadas` (solo keyword, opcional, M8 -- hallazgo de
      hardening de Change 5, bug real: sin esto, `regenerar_control`
      recalculaba `archivos` vía `manifest_para_perfil`/
      `manifest_para_perfil_y_stage` SIN filtrar por capabilities, incluyendo
      entradas deliberadamente no instaladas -- `sha256_de_archivo` sobre un
      archivo inexistente levantaba `FileNotFoundError`, haciendo que
      CUALQUIER `sync` sobre un proyecto con una capability deshabilitada
      rompiera por completo). Mismo criterio de herencia que
      `installation_stage`: si es `None` (default), se preserva
      `control_previo.get("capabilities_habilitadas")` -- nunca se pierde un
      valor existente por el solo hecho de omitir este parámetro. Si se pasa
      explícitamente (incluida una lista vacía), ese valor gana.

    Comportamiento:
    - `configuracion` se preserva exactamente igual a la de `control_previo`
      (se delega en `generar_control`, que la reconstruye a partir de
      `control_previo["configuracion"]`).
    - `fecha_utc` se preserva exactamente igual a la de `control_previo` —
      no se retro-corrige la fecha de instalación original.
    - `harness_version` se actualiza al valor vigente de `HARNESS_VERSION`
      (no el de `control_previo`), porque `generar_control` siempre lo
      estampa así.
    - `archivos` se reconstruye EXCLUSIVAMENTE a partir del manifiesto
      vigente (`manifest_para_perfil`/`manifest_para_perfil_y_stage` según
      corresponda, con hashes reales leídos de `destino`) — nunca es una
      unión con `control_previo["archivos"]`. Cualquier entrada de
      `control_previo["archivos"]` cuya ruta ya no esté en el manifiesto
      vigente queda ausente del resultado, sin lógica extra: simplemente no
      se itera sobre `control_previo["archivos"]`.
    - Se excluye del manifiesto la entrada `.ds_init/control.json` (misma
      exclusión que ya aplica `tools/harmessi/doctor.py` al verificar
      archivos esperados), porque ese archivo se verifica aparte.
    - Delega la escritura en `generar_control`, que es atómica (temporal en
      el mismo directorio + `os.replace`).

    Modo conservador (`clasificacion` no es `None`, usado por `sync`, R27/R28):
    en vez de rebaseline total, `clasificacion` (salida de `clasificar_baseline`
    sobre el control ANTERIOR, calculada antes de escribir) y `resultado`
    (objeto con listas `aplicados`, `actualizados`, `sin_cambios`, `omitidos`
    de rutas relativas) deciden por cada entrada del manifiesto vigente:
    - en `sin_cambios`: hash nuevo (migra al algoritmo vigente);
    - creada/actualizada/mergeada en esta corrida (`aplicados`/`actualizados`):
      sin entrada previa -> hash nuevo, salvo que la ruta esté en
      `preexistentes` (conjunto de rutas que ya existían en disco antes de la
      corrida; p. ej. un settings.json del usuario sin baseline), en cuyo caso
      NO se adopta; con entrada previa en drift/algoritmo_desconocido (o no
      clasificable y preexistente) se conserva verbatim; en otro caso hash
      nuevo;
    - no tocada: sin entrada previa -> no se incluye (no se adopta); estado
      `ok` con `hash_alg` vigente -> se conserva; `ok_legacy` -> se migra
      (rehash); drift/algoritmo_desconocido/no clasificable -> entrada previa
      tal cual, sin rehash;
    - entradas previas sin `sha256` string se conservan verbatim; entradas
      fuera del manifiesto vigente se conservan SOLO si su estado previo es
      drift/algoritmo_desconocido (evidencia de drift); el resto se descarta;
    - ruta del manifiesto ausente del disco -> no se incluye.
    Con `clasificacion=None` el comportamiento es el rebaseline total de
    siempre (escribiendo `hash_alg`).
    """
    from .manifest import (
        ORDEN_STAGES,
        manifest_para_perfil,
        manifest_para_perfil_stage_y_capabilities,
        manifest_para_perfil_y_stage,
    )

    perfil_efectivo = perfil or control_previo["perfil"]

    capabilities_efectivas = (
        capabilities_habilitadas
        if capabilities_habilitadas is not None
        else control_previo.get("capabilities_habilitadas")
    )

    if capabilities_efectivas is not None:
        stage_efectivo_capabilities = stage if stage is not None else ORDEN_STAGES[-1]
        entradas = manifest_para_perfil_stage_y_capabilities(
            perfil_efectivo, stage_efectivo_capabilities, capabilities_efectivas
        )
    elif stage is None:
        entradas = manifest_para_perfil(perfil_efectivo)
    else:
        entradas = manifest_para_perfil_y_stage(perfil_efectivo, stage)

    archivos_aplicados = [
        entrada.destino
        for entrada in entradas
        if entrada.destino != _RUTA_CONTROL_EN_MANIFIESTO
    ]

    installation_stage_efectivo = (
        installation_stage if installation_stage is not None else control_previo.get("installation_stage")
    )

    entradas_conservadas = None
    if clasificacion is not None:
        archivos_aplicados, entradas_conservadas = _resolver_modo_conservador(
            Path(destino),
            archivos_aplicados,
            control_previo,
            clasificacion,
            resultado,
            preexistentes,
        )

    return generar_control(
        destino,
        perfil_efectivo,
        control_previo["configuracion"],
        archivos_aplicados,
        fecha_utc=control_previo.get("fecha_utc"),
        installation_stage=installation_stage_efectivo,
        capabilities_habilitadas=capabilities_efectivas,
        entradas_conservadas=entradas_conservadas,
    )


@dataclass
class InformeMigracion:
    """Resultado de `migrar_hashes`: listas de rutas por categoría."""

    migradas: list = field(default_factory=list)
    ya_actuales: list = field(default_factory=list)
    no_verificables: list = field(default_factory=list)
    desconocidas: list = field(default_factory=list)


def migrar_hashes(destino, *, ejecutar: bool = False) -> InformeMigracion:
    """Migra las entradas legacy (sin `hash_alg`) de `<destino>/.ds_init/
    control.json` al algoritmo managed vigente (R20-R26).

    Solo migra entradas que verifican por la vía legacy (`ok_legacy`, o `ok`):
    reescribe `hash_alg` y recalcula `sha256` sobre el contenido ACTUAL según
    `manifest.contenido_de`. Entradas en drift se dejan intactas y se reportan
    en `no_verificables`; entradas con `hash_alg` desconocido quedan intactas
    en `desconocidas`; entradas con `hash_alg` conocido van a `ya_actuales`.
    Dry-run por defecto: solo con `ejecutar=True` y si hubo migradas se
    reescribe `control.json` (JSON determinista, resto de claves y orden de
    entradas preservados). Idempotente. Si el control no existe levanta
    `FileNotFoundError`."""
    destino = Path(destino)
    ruta_control = destino / DIR_CONTROL / NOMBRE_ARCHIVO_CONTROL
    if not ruta_control.is_file():
        raise FileNotFoundError(f"No existe el archivo de control: {ruta_control}")
    with open(ruta_control, "r", encoding="utf-8") as f:
        control = json.load(f)

    informe = InformeMigracion()
    algoritmos_conocidos = managed_hash.ALGORITMOS_CONOCIDOS

    for entrada in control.get("archivos", []) or []:
        if not isinstance(entrada, dict) or not isinstance(entrada.get("ruta"), str):
            continue
        ruta = entrada["ruta"]

        if "hash_alg" in entrada:
            if entrada["hash_alg"] in algoritmos_conocidos:
                informe.ya_actuales.append(ruta)
            else:
                informe.desconocidas.append(ruta)
            continue

        ruta_absoluta = destino / ruta
        if not ruta_absoluta.is_file() or not isinstance(entrada.get("sha256"), str):
            informe.no_verificables.append(ruta)
            continue

        contenido = manifest_mod.contenido_de(ruta)
        estado, _detalle = managed_hash.verificar_entrada(
            ruta_absoluta, entrada, contenido=contenido
        )
        if estado in (managed_hash.ESTADO_OK_LEGACY, managed_hash.ESTADO_OK):
            algoritmo = managed_hash.algoritmo_para_contenido(contenido)
            entrada["sha256"] = managed_hash.hash_managed_file(ruta_absoluta, algoritmo)
            entrada["hash_alg"] = algoritmo
            informe.migradas.append(ruta)
        elif estado == managed_hash.ESTADO_ALG_DESCONOCIDO:
            informe.desconocidas.append(ruta)
        else:
            informe.no_verificables.append(ruta)

    if ejecutar and informe.migradas:
        _crear_backup_control(ruta_control)
        _escribir_control_atomico(ruta_control, control)

    return informe

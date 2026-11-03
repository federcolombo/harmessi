"""Diff de filesystem antes/después de una corrida de notebook, y cuarentena
de escrituras fuera de contrato (Sesión 4 de `20260907-notebook-runner-controlado`).

Nada acá ejecuta un notebook ni un subprocess — eso es de `execute.py`
(Sesión 3, ya implementada). Este módulo solo compara instantáneas de
filesystem (tamaño + mtime, sin hash — `hash_lf_v1` en `dsguard.core` ya
cubre integridad de contenido para otro propósito, requisito 5(e)) y mueve a
cuarentena lo que no matchea `salidas_permitidas` del manifest.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from dsguard.repo import path_matches_any


def snapshot(root: Path, subrutas: list) -> dict:
    """Recorre (`os.walk`) cada ruta de `subrutas` (relativas a `root`) y
    devuelve `{ruta_relativa_posix: (tamaño_bytes, mtime_ns)}` de cada archivo
    encontrado. Rutas que no existen se ignoran. No sigue symlinks."""
    root = Path(root)
    resultado = {}
    for subruta in subrutas:
        base = root / subruta
        if not base.exists():
            continue
        if base.is_file():
            if base.is_symlink():
                continue
            stat = base.stat()
            rel = base.relative_to(root).as_posix()
            resultado[rel] = (stat.st_size, stat.st_mtime_ns)
            continue
        for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
            # Excluir symlinks a directorios de la recorrida.
            dirnames[:] = [
                d for d in dirnames if not (Path(dirpath) / d).is_symlink()
            ]
            for nombre in filenames:
                archivo = Path(dirpath) / nombre
                if archivo.is_symlink():
                    continue
                stat = archivo.stat()
                rel = archivo.relative_to(root).as_posix()
                resultado[rel] = (stat.st_size, stat.st_mtime_ns)
    return resultado


def diferencia(antes: dict, despues: dict) -> dict:
    """`{"agregados": [...], "eliminados": [...], "modificados": [...]}`
    (listas de rutas relativas posix), comparando `antes`/`despues` (mismo
    formato que `snapshot`)."""
    rutas_antes = set(antes.keys())
    rutas_despues = set(despues.keys())

    agregados = sorted(rutas_despues - rutas_antes)
    eliminados = sorted(rutas_antes - rutas_despues)
    modificados = sorted(
        ruta
        for ruta in (rutas_antes & rutas_despues)
        if antes[ruta] != despues[ruta]
    )

    return {
        "agregados": agregados,
        "eliminados": eliminados,
        "modificados": modificados,
    }


def clasificar(diff: dict, salidas_permitidas: list) -> tuple:
    """`(permitidos, fuera_de_contrato)`: rutas de "agregados"/"modificados"
    que matchean (fnmatch) algún patrón de `salidas_permitidas` van a
    `permitidos`; las que no matchean ninguno, a `fuera_de_contrato`.
    "eliminados" siempre van a `fuera_de_contrato`."""
    permitidos = []
    fuera_de_contrato = []

    for ruta in diff["agregados"] + diff["modificados"]:
        if path_matches_any(ruta, salidas_permitidas):
            permitidos.append(ruta)
        else:
            fuera_de_contrato.append(ruta)

    for ruta in diff["eliminados"]:
        fuera_de_contrato.append(ruta)

    return permitidos, fuera_de_contrato


def cuarentena(root: Path, rutas_fuera_de_contrato: list, destino: Path) -> list:
    """Mueve cada archivo de `rutas_fuera_de_contrato` (relativas a `root`) a
    `destino/<misma_ruta_relativa>`, creando subdirectorios en `destino`
    según haga falta. Devuelve la lista de rutas absolutas finales en
    cuarentena. Rutas que ya no existen en `root` (caso "eliminados") se
    omiten sin error."""
    root = Path(root)
    destino = Path(destino)
    movidos = []

    for ruta_relativa in rutas_fuera_de_contrato:
        origen = root / ruta_relativa
        if not origen.exists():
            continue
        destino_final = destino / ruta_relativa
        destino_final.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(origen), str(destino_final))
        movidos.append(destino_final)

    return movidos

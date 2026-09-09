"""Validaciones previas a construir/aplicar un plan de instalación.

`validar_destino` implementa R4 (existe / es repo Git / working tree limpio,
en ese orden). `detectar_colisiones` implementa la parte de R10 que necesita
tocar disco (qué archivos del plan ya existen en el destino); el resto de R10
(mostrar el plan) vive en `planner.py`.
"""
from __future__ import annotations

import subprocess
from pathlib import Path


class DestinoInvalidoError(Exception):
    """El destino no cumple alguna de las tres condiciones de R4. El mensaje
    indica explícitamente cuál falló."""


def _git(args: list, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(cwd)] + args,
        capture_output=True,
        text=True,
    )


def validar_destino(ruta: Path) -> None:
    """Levanta `DestinoInvalidoError` con mensaje específico si `ruta` no
    existe, no es un repositorio Git, o su working tree no está limpio — en
    ese orden exacto (R4, AC3/AC4/AC5 de `spec.md`)."""
    ruta = Path(ruta)

    # (a) existe como directorio.
    if not ruta.exists():
        raise DestinoInvalidoError(f"El destino no existe: {ruta}")
    if not ruta.is_dir():
        raise DestinoInvalidoError(f"El destino no es un directorio: {ruta}")

    # (b) es un repositorio Git.
    resultado = _git(["rev-parse", "--is-inside-work-tree"], ruta)
    if resultado.returncode != 0 or resultado.stdout.strip() != "true":
        raise DestinoInvalidoError(
            f"El destino no es un repositorio Git: {ruta}\n{resultado.stderr.strip()}"
        )

    # (c) working tree limpio.
    resultado = _git(["status", "--porcelain"], ruta)
    if resultado.returncode != 0:
        raise DestinoInvalidoError(
            f"No se pudo consultar el estado de Git en {ruta}\n{resultado.stderr.strip()}"
        )
    sucios = resultado.stdout.strip()
    if sucios:
        archivos = "\n".join(f"  {linea}" for linea in sucios.splitlines())
        raise DestinoInvalidoError(
            f"El working tree del destino no está limpio:\n{archivos}"
        )


def detectar_colisiones(plan: list, destino: Path) -> list:
    """Dado `plan` (lista de rutas destino relativas, tal como aparecen en
    `EntradaManifiesto.destino`), devuelve la sublista de las que ya existen
    en `destino` (R10: por defecto se omiten, nunca se sobrescriben, salvo los
    flujos propios de MERGE/GENERADO ya documentados en R8/R9)."""
    destino = Path(destino)
    colisiones = []
    for destino_relativo in plan:
        if (destino / destino_relativo).exists():
            colisiones.append(destino_relativo)
    return colisiones

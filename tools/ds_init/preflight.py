"""Validaciones previas a construir/aplicar un plan de instalación.

`validar_destino` implementa R4 (existe / es repo Git / sin staging de
`ds_init` huérfano / working tree limpio, en ese orden). `detectar_colisiones`
implementa la parte de R10 que necesita tocar disco (qué archivos del plan ya
existen en el destino); el resto de R10 (mostrar el plan) vive en
`planner.py`.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

# Prefijo de los directorios de staging temporal que crea `writer.instalar`
# (ver `writer.py`). Si uno de estos queda en el destino, es porque un
# `--execute` anterior terminó de forma abrupta (proceso matado, corte de
# luz) antes de llegar a su propia limpieza final — el rollback de
# `writer.py` solo cubre excepciones manejadas dentro del mismo proceso.
PREFIJO_STAGING_HUERFANO = ".ds_init_staging_"


class DestinoInvalidoError(Exception):
    """El destino no cumple alguna de las condiciones de R4. El mensaje
    indica explícitamente cuál falló."""


def _git(args: list, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(cwd)] + args,
        capture_output=True,
        text=True,
    )


def _detectar_staging_huerfano(ruta: Path) -> list:
    """Nombres de subdirectorios `.ds_init_staging_*` remanentes
    directamente bajo `ruta` — indicio de una instalación de `ds_init
    --execute` anterior interrumpida a mitad de camino. No intenta repararlo
    ni reanudarlo, solo lo señala para revisión manual (alcance de esta
    versión: sin recuperación automática)."""
    if not ruta.is_dir():
        return []
    return sorted(
        p.name
        for p in ruta.iterdir()
        if p.is_dir() and p.name.startswith(PREFIJO_STAGING_HUERFANO)
    )


def validar_destino(ruta: Path) -> None:
    """Levanta `DestinoInvalidoError` con mensaje específico si `ruta` no
    existe, no es un repositorio Git, tiene un staging de `ds_init` sin
    limpiar (instalación anterior interrumpida), o su working tree no está
    limpio — en ese orden exacto (R4, AC3/AC4/AC5 de `spec.md`, más la
    detección de staging huérfano agregada en la reliability v0.2.0)."""
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

    # (c) sin staging de ds_init sin limpiar. Se chequea de forma
    # independiente de si Git considera "limpio" el working tree: un
    # `.gitignore` demasiado amplio en el destino podría ocultar el
    # directorio de staging de `git status` y dejarlo pasar sin detectar.
    huerfanos = _detectar_staging_huerfano(ruta)
    if huerfanos:
        nombres = ", ".join(huerfanos)
        raise DestinoInvalidoError(
            f"El destino tiene staging de ds_init sin limpiar ({nombres}): "
            f"parece haber quedado una instalación anterior interrumpida a "
            f"mitad de camino (el proceso terminó antes de completar el "
            f"rollback o la limpieza final). ds_init no repara ni reanuda "
            f"instalaciones interrumpidas automáticamente — revisar el "
            f"contenido de ese directorio a mano (incluye journal.json y, si "
            f"corresponde, backups en '.backup/') antes de reintentar."
        )

    # (d) working tree limpio.
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

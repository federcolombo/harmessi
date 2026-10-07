"""Decisión exacto-vs-muestreado (`decidir_modo`) y `ReservoirSampler`
(algoritmo R clásico, reproducible vía semilla propia -- nunca comparte
estado global de `random`).

`decidir_modo` se evalúa ANTES de iterar el dataset, sin escaneo previo: usa
solo metadata gratis (`tamano_bytes` del filesystem, `filas_exactas` --
gratis de metadata de formato para Parquet; para CSV, un `int` real vía su
propia pasada streaming, ver `io_readers.py`).
"""
from __future__ import annotations

import random
from typing import Optional

# Estimación conservadora de memoria por celda (fila x columna) del working
# set exacto: objeto Python del valor + slot de lista + dedup/digest de fila.
# NO es una medida: es el criterio explícito que usa `decidir_plan` para
# decidir exacto vs muestreado ANTES de leer filas (el tamaño comprimido del
# archivo no es proxy de memoria).
BYTES_POR_CELDA = 96

TAMANO_MUESTRA_MAXIMO = 200_000
TAMANO_MUESTRA_MINIMO = 1_000
# Fuentes tan anchas que ni la muestra mínima entra en un working set sano.
MAX_CELDAS_MUESTRA_MINIMA = 20_000_000

VERSION_ALGORITMO = "bounded_v1"


class PresupuestoInsuficienteError(Exception):
    """La fuente no puede perfilarse de forma segura ni en modo muestreado."""


def estimar_bytes_exactos(filas: Optional[int], columnas: int) -> Optional[int]:
    """`filas x max(1, columnas) x BYTES_POR_CELDA`; `None` si no se conocen
    las filas (no se estima: aplican los demás criterios)."""
    if filas is None:
        return None
    return int(filas) * max(1, int(columnas)) * BYTES_POR_CELDA


def decidir_plan(
    tamano_bytes: int,
    filas: Optional[int],
    columnas: int,
    max_mb_exactos: int,
    max_filas_exactas: int,
) -> dict:
    """Plan de perfilado decidido solo con metadata, antes de leer filas.

    `muestreado` si el archivo supera el presupuesto en bytes (criterio
    histórico), si supera `max_filas_exactas`, o si la estimación del working
    set exacto supera el presupuesto (`max_mb_exactos` MiB). `tamano_muestra`
    es el tope de filas del reservoir (0 en modo exacto)."""
    presupuesto = max(0, int(max_mb_exactos)) * 1024 * 1024
    estimado = estimar_bytes_exactos(filas, columnas)
    motivo = None
    if tamano_bytes > presupuesto:
        motivo = "tamano_archivo"
    elif filas is not None and filas > max_filas_exactas:
        motivo = "filas"
    elif estimado is not None and estimado > presupuesto:
        motivo = "memoria_estimada"
    muestreado = motivo is not None
    tamano_muestra = 0
    if muestreado:
        if max(1, int(columnas)) * TAMANO_MUESTRA_MINIMO > MAX_CELDAS_MUESTRA_MINIMA:
            raise PresupuestoInsuficienteError(
                f"La fuente tiene {columnas} columnas: ni la muestra mínima de "
                f"{TAMANO_MUESTRA_MINIMO} filas entra en el límite de seguridad de perfilado. "
                "Reducí las columnas de la fuente (p. ej. exportá un subconjunto)."
            )
        por_presupuesto = max(TAMANO_MUESTRA_MINIMO, presupuesto // (BYTES_POR_CELDA * max(1, int(columnas))))
        tamano_muestra = max(0, min(TAMANO_MUESTRA_MAXIMO, int(max_filas_exactas), por_presupuesto))
        if filas is not None:
            tamano_muestra = min(tamano_muestra, int(filas))
    return {
        "muestreado": muestreado,
        "motivo": motivo,
        "estimado_bytes": estimado,
        "presupuesto_bytes": presupuesto,
        "tamano_muestra": tamano_muestra,
    }


def decidir_modo(
    tamano_bytes: int,
    filas_exactas: Optional[int],
    max_mb_exactos: int,
    max_filas_exactas: int,
) -> bool:
    """`True` si el dataset debe perfilarse en modo muestreado.

    `tamano_bytes > max_mb_exactos*1024*1024 OR (filas_exactas is not None
    AND filas_exactas > max_filas_exactas)`. El umbral de MB aplica siempre
    (CSV incluido); el de filas solo cuando el lector puede saberlo sin
    escanear (Parquet)."""
    if tamano_bytes > max_mb_exactos * 1024 * 1024:
        return True
    if filas_exactas is not None and filas_exactas > max_filas_exactas:
        return True
    return False


class ReservoirSampler:
    """Reservoir sampling clásico (algoritmo R de Vitter): cada fila
    observada tiene probabilidad `tamano_muestra / n_visto` de terminar en
    la muestra final, sin conocer `n` de antemano. Reproducible: misma
    secuencia de filas + misma `seed` -> misma muestra final, siempre (usa
    su propia instancia de `random.Random`, nunca el estado global del
    módulo `random`)."""

    def __init__(self, tamano_muestra: int, seed: int) -> None:
        self._tamano_muestra = max(0, int(tamano_muestra))
        self._rng = random.Random(seed)
        self._muestra: list = []
        self._vistas = 0

    def observar(self, fila: dict) -> None:
        self._vistas += 1
        if self._tamano_muestra <= 0:
            return
        if len(self._muestra) < self._tamano_muestra:
            self._muestra.append(fila)
            return
        indice = self._rng.randint(0, self._vistas - 1)
        if indice < self._tamano_muestra:
            self._muestra[indice] = fila

    def muestra(self) -> list:
        """Copia de la muestra actual (no la referencia interna, para que el
        llamador no pueda mutarla por accidente)."""
        return list(self._muestra)

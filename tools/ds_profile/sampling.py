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

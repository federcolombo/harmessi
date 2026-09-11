"""Filas, columnas, tamaño y duplicados de fila. Ningún cálculo de dtype ni
de calidad por columna acá -- eso vive en `column_stats.py`/
`quality_flags.py` respectivamente; este módulo solo arma la representación
hasheable de una fila y cuenta duplicados sobre una lista ya decidida por el
orquestador (`report.py`): la lista completa de filas en modo exacto, o las
filas de la muestra final del `ReservoirSampler` en modo muestreado.
"""
from __future__ import annotations

from collections import Counter
from typing import Sequence


def fila_a_tupla(fila: dict, columnas: Sequence[str]) -> tuple:
    """Representación hasheable y estable de una fila, en el orden fijo de
    `columnas` (no el de `fila.keys()`, que puede variar entre filas p. ej.
    en un CSV irregular). Cada valor se normaliza a `str(valor)` (o `""`
    para ausente/`None`) -- mismo criterio de "todo a texto antes de
    comparar" que usa `column_stats.py` para clasificar dtype."""
    return tuple("" if fila.get(columna) is None else str(fila.get(columna)) for columna in columnas)


def contar_duplicados(filas_como_tuplas: list) -> int:
    """Cantidad de filas que son copia exacta de otra fila ya vista antes
    (total de filas menos filas distintas) -- no la cantidad de grupos
    duplicados."""
    contador = Counter(filas_como_tuplas)
    return sum(cuenta - 1 for cuenta in contador.values() if cuenta > 1)

"""Capa de lectura desacoplada del cálculo (Requisito 3 de `spec.md`):
una interfaz común (`LectorDataset`) con dos implementaciones concretas,
`LectorCSV` (stdlib `csv`) y `LectorParquet` (`pyarrow`, import perezoso).
Pensada para poder sumar lectores de pandas/polars/duckdb más adelante sin
rediseñar `report.py`/`column_stats.py`.

Ningún lector materializa el dataset completo en memoria: `iter_filas()` es
siempre un generador (streaming fila a fila; Parquet además streamea por
row-group vía `iter_batches()`, nunca `read_table()`/`to_pandas()`
completo).
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, Iterator, Optional, Protocol


class FormatoNoSoportadoError(Exception):
    """`--input` tiene una extensión que `ds_profile` no sabe leer.

    Solo `.csv` y `.parquet` están soportados en v0.2 (Requisito 1/2 de
    `spec.md`) -- cualquier otra extensión levanta esto."""


class DependenciaFaltanteError(Exception):
    """Falta una dependencia opcional necesaria para leer el formato pedido.

    En v0.2 el único caso es Parquet sin `pyarrow` instalado -- el mensaje
    siempre nombra "pyarrow" explícitamente (Requisito 2)."""


class LectorDataset(Protocol):
    """Interfaz mínima común que necesita `report.py` para perfilar un
    dataset, sin conocer el formato concreto."""

    def schema(self) -> Dict[str, str]:
        """`{columna: tipo_crudo}` tal como lo reporta el lector -- NO es la
        clasificación semántica final (booleano/entero/flotante/fecha/texto),
        eso lo calcula `column_stats.clasificar_dtype` sobre los valores
        observados."""
        ...

    def filas_exactas(self) -> Optional[int]:
        """Cantidad de filas de datos, siempre exacta. Gratis (de metadata,
        sin escanear) para Parquet; para CSV implica una pasada streaming
        propia (ver `LectorCSV.filas_exactas`). `Optional` a nivel de
        interfaz por si un futuro lector no pudiera saberlo sin escanear."""
        ...

    def tamano_bytes(self) -> int:
        """Tamaño del archivo en disco (`Path.stat().st_size`), gratis."""
        ...

    def iter_filas(self) -> Iterator[dict]:
        """Itera el dataset fila a fila, como `dict` columna -> valor
        crudo. Streaming: nunca materializa todas las filas en una lista."""
        ...


class LectorCSV:
    """Lector CSV vía `csv.DictReader` sobre stdlib puro (Requisito 2: sin
    pandas). Los valores llegan como `str` crudos -- la inferencia de tipo
    numérico/fecha/booleano vive en `column_stats.py`, no acá."""

    def __init__(self, ruta: Path) -> None:
        self._ruta = Path(ruta)
        self._schema_cache: Optional[Dict[str, str]] = None

    def schema(self) -> Dict[str, str]:
        if self._schema_cache is None:
            with open(self._ruta, newline="", encoding="utf-8") as f:
                lector = csv.reader(f)
                try:
                    encabezado = next(lector)
                except StopIteration:
                    encabezado = []
            # "str": tipo crudo que este lector puede garantizar -- todo
            # valor de un DictReader es un string (o None si falta en la
            # fila). No es la clasificación semántica final.
            self._schema_cache = {nombre: "str" for nombre in encabezado}
        return self._schema_cache

    def filas_exactas(self) -> int:
        # Pasada streaming propia, separada de `iter_filas()`: cuenta las
        # filas de datos (sin el header) sin materializar ninguna lista en
        # memoria (memoria O(1)). Corre ANTES de la pasada principal de
        # `report.py` (para que `sampling.decidir_modo` pueda aplicar
        # `--max-filas-exactas` también a CSV, igual que ya hace con Parquet
        # vía metadata) -- el costo de una segunda lectura del archivo está
        # aceptado explícitamente para este caso.
        #
        # Usa `csv.DictReader` -- el mismo motor que `iter_filas()` -- en vez
        # de `csv.reader` crudo, para contar exactamente las mismas filas
        # que `iter_filas()` yieldea. `csv.reader` cuenta *toda* fila que
        # produce el parser, incluidas líneas en blanco del cuerpo (una
        # línea vacía produce `row == []`, que sigue siendo una iteración);
        # `DictReader.__next__` descarta explícitamente esas filas `== []`
        # antes de devolver un dict, así que contarlas con `csv.reader`
        # podía devolver un número mayor al real y desincronizar
        # `sampling.decidir_modo`.
        contador = 0
        with open(self._ruta, newline="", encoding="utf-8") as f:
            lector = csv.DictReader(f)
            for _ in lector:
                contador += 1
        return contador

    def tamano_bytes(self) -> int:
        return self._ruta.stat().st_size

    def iter_filas(self) -> Iterator[dict]:
        with open(self._ruta, newline="", encoding="utf-8") as f:
            lector = csv.DictReader(f)
            for fila in lector:
                yield dict(fila)


class LectorParquet:
    """Lector Parquet vía `pyarrow.parquet`. El import de `pyarrow` es
    perezoso (adentro de `__init__`, nunca a nivel de módulo): si falta,
    levanta `DependenciaFaltanteError` con un mensaje que nombra "pyarrow"
    explícitamente (Requisito 2)."""

    def __init__(self, ruta: Path) -> None:
        try:
            import pyarrow.parquet as pq
        except ImportError as exc:
            raise DependenciaFaltanteError(
                "Parquet requiere pyarrow, no instalado en este entorno"
            ) from exc
        self._ruta = Path(ruta)
        self._parquet_file = pq.ParquetFile(self._ruta)

    def schema(self) -> Dict[str, str]:
        return {campo.name: str(campo.type) for campo in self._parquet_file.schema_arrow}

    def filas_exactas(self) -> Optional[int]:
        # Gratis: viene de los metadatos del footer del archivo, sin leer
        # ningún dato.
        return self._parquet_file.metadata.num_rows

    def tamano_bytes(self) -> int:
        return self._ruta.stat().st_size

    def iter_filas(self) -> Iterator[dict]:
        # Streaming por row-group: `iter_batches()` nunca materializa el
        # archivo completo en memoria (ni `read_table()` ni `to_pandas()`).
        for batch in self._parquet_file.iter_batches():
            for fila in batch.to_pylist():
                yield fila


_EXTENSIONES: Dict[str, type] = {
    ".csv": LectorCSV,
    ".parquet": LectorParquet,
}


def abrir_lector(ruta: Path) -> LectorDataset:
    """Detecta el formato por extensión y devuelve el lector concreto.
    Cualquier extensión que no sea `.csv`/`.parquet` levanta
    `FormatoNoSoportadoError`. Para `.parquet` sin `pyarrow`, la excepción
    real (`DependenciaFaltanteError`) la levanta `LectorParquet.__init__`,
    invocado acá mismo -- este es el único punto de entrada del paquete que
    intenta importar `pyarrow`."""
    ruta = Path(ruta)
    extension = ruta.suffix.lower()
    clase = _EXTENSIONES.get(extension)
    if clase is None:
        raise FormatoNoSoportadoError(
            f"Extensión no soportada: {extension!r} (ruta: {ruta}). "
            "Formatos soportados: .csv, .parquet"
        )
    return clase(ruta)

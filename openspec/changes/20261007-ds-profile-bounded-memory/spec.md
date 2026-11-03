# Spec — 20261007-ds-profile-bounded-memory

Todo cambio es aditivo en el schema; fuentes pequeñas producen el mismo perfil que hoy (salvo `created_utc`).

## A. Decisión previa por presupuesto (R1–R6)
**R1.** `--max-mb-exactos` pasa a ser el PRESUPUESTO DE MEMORIA de trabajo (MiB) del perfil. Se conserva su uso previo (bytes de archivo >
presupuesto ⇒ muestreado). Sin flags nuevos.
**R2.** `sampling.estimar_bytes_exactos(filas, columnas)` = `filas × max(1, columnas) × BYTES_POR_CELDA` con `BYTES_POR_CELDA = 96`
(constante documentada: objeto + slot de lista + tupla/duplicado, conservadora). Si el lector no conoce `filas` ⇒ no se estima (se aplican los
demás criterios).
**R3.** `sampling.decidir_plan(tamano_bytes, filas, columnas, max_mb, max_filas)` devuelve `{muestreado, motivo, estimado_bytes,
presupuesto_bytes, tamano_muestra}`. `muestreado` si: bytes > presupuesto (`motivo="tamano_archivo"`), filas > `max_filas`
(`"filas"`) o estimación > presupuesto (`"memoria_estimada"`); si no, exacto (`motivo=None`). `decidir_modo` conserva firma y
semántica (bool) para compatibilidad. La decisión se toma antes de leer filas.
**R4.** `tamano_muestra = min(200 000, max_filas, max(1000, presupuesto_bytes // (BYTES_POR_CELDA × columnas)))` y nunca más que `filas` cuando se
conoce (la muestra nunca excede el working set presupuestado, salvo el piso de 1000 filas).
**R5.** Fail-safe: si `columnas × 1000 > 20 000 000` (fuente ancha) o el lector falla (pyarrow/csv/Unicode/`MemoryError`), se levanta
`LecturaFallidaError`/`PresupuestoInsuficienteError` con mensaje accionable (fuente, límite, opción: `--max-mb-exactos`/`--max-filas-exactas` o
reducir columnas); la CLI sale con código 4 y no escribe `profile.json`. Nunca traceback crudo.
**R6.** El caso real (620 570 × 27, `--max-mb-exactos 500`) decide `muestreado` con `motivo="memoria_estimada"`.

## B. Exacto por acumuladores (R7–R10)
**R7.** `AcumuladorColumna` suma contadores O(1): `n_entero`, `n_fecha`, `n_num_o_fecha`, `solo_booleano` y conjunto de floats distintos con tope 3.
**R8.** `dtype`, `binary_numeric` y `posible_problema_tipo` se derivan SIEMPRE del acumulador (exactos sobre todas las filas, en ambos modos).
En modo exacto el resultado es idéntico al previo (tests de equivalencia contra `clasificar_dtype`/`es_binario_numerico`).
**R9.** `nulls`, `min`, `max`, `media`, `std`, `fecha_min/max` siguen exactos (sin cambios).
**R10.** `clasificar_dtype`, `es_binario_numerico` se conservan (API pública) como referencia de equivalencia.

## C. Retención acotada (R11–R15)
**R11.** El modo exacto ya no retiene `filas_como_tuplas`: `duplicados_fila` se calcula con un conjunto de digests (`blake2b`, 16 bytes) por fila,
exacto salvo colisión 2⁻¹²⁸ (documentado). Las listas de valores por columna solo existen en modo exacto y su tamaño está acotado por la
estimación de R2–R3.
**R12.** En modo muestreado el reservoir retiene como máximo `tamano_muestra` filas (R4); `mediana`, `cuantiles`, `unique`, `top_valores`,
flags de cardinalidad y `duplicados_fila` salen de esa muestra y se marcan `muestreada`.
**R13.** `LectorParquet.iter_filas` usa `batch_size` explícito (`BATCH_SIZE = 8192`); la memoria transitoria es por batch. Parquet nunca usa
`read_table`/`to_pandas`. CSV es streaming.
**R14.** Determinismo: misma fuente + seed + configuración + `version_algoritmo` ⇒ misma muestra y mismo perfil. `ReservoirSampler` usa su
`random.Random(seed)` propio. Sin dependencias nuevas; `pyarrow` sigue opcional/perezoso.
**R15.** Un test verifica el tope de retención de forma determinista (conteo de celdas retenidas/instrumentación), no RSS.

## D. Metadata de salida (R16–R18)
**R16.** `sampling` agrega (aditivo): `motivo`, `filas_observadas`, `version_algoritmo` (`"bounded_v1"`), `presupuesto_bytes`,
`estimado_bytes_exactos`. `activo`, `metodo` (`reservoir_v1`), `semilla`, `tamano_muestra` conservan significado. Ningún campo numérico
existente cambia de significado salvo lo declarado en R8.
**R17.** `exactitud_estadisticos`/`unique.exactitud` siguen `exacta|muestreada`; `dtype` y flags de R8 son exactos en ambos modos.
**R18.** `profile.md` muestra el motivo cuando `muestreo activo`.

## E. Compatibilidad y pruebas (R19–R22)
**R19.** Los tests existentes de `ds_profile` pasan sin reescrituras masivas; los consumidores (`datasources`, `datacontracts`) siguen leyendo
el mismo schema.
**R20.** Tests dirigidos nuevos: pequeño/exacto sin cambios, transición por memoria estimada ANTES de leer filas, sample acotado y reproducible,
metadata, acumuladores = referencia, Parquet con row groups/batch acotado y sin `read_table`, errores (límite bajo, archivo malformado, reader
error), fixture escalada del caso real.
**R21.** Benchmark manual documentado (`tools/ds_profile/benchmark_bounded_memory.md` con script de generación; NO gateado, sin datos en el repo).
**R22.** Sin cambios fuera de `tools/ds_profile/**`, docs y tests; sin tocar `ds_init/manifest` (los archivos modificados ya se distribuyen).

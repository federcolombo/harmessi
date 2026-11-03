# Diseño — 20261007-ds-profile-bounded-memory

## Decisión metodológica/técnica
**D1 — Presupuesto explícito, decisión previa.** Se reutiliza `--max-mb-exactos` (sin flag nuevo) con significado honesto de presupuesto de
trabajo. La estimación `filas × columnas × 96 B` usa solo metadata (Parquet footer; CSV ya cuenta filas) y se evalúa antes de iterar. El criterio
legacy de bytes de archivo se conserva (solo puede adelantar el muestreo, nunca retrasarlo).
**D2 — Exacto vs muestreado se reparte por tipo de estadística.** Lo reducible a O(1) (dtype, binary_numeric, posible_problema_tipo) migra a
acumuladores y es exacto en ambos modos; esto es una mejora de precisión en modo muestreado (antes salía de la muestra) y no cambia modo exacto.
Cardinalidad/orden/duplicados requieren valores: exactos solo dentro del presupuesto; si no, muestra determinista con tope.
**D3 — Sin sketches.** Ni t-digest ni HLL: la degradación es la muestra de reservoir ya existente, ahora con tamaño dependiente del presupuesto.
**D4 — Duplicados por digest.** Reemplaza la lista de tuplas por un `set` de 16 bytes/fila: exacto salvo colisión criptográfica despreciable.
**D5 — Parquet por batches de filas.** `batch_size` fijo acota el transitorio. Columna-a-columna exigiría una lectura por columna y no resuelve
duplicados de fila; se deja como deuda. Se declara honestamente.
**D6 — Fail-safe.** Errores de lectura/ancho extremo se convierten en excepciones propias con mensaje accionable y exit 4.
**D7 — Metadata en `sampling`.** Se extiende el dict existente (consumidores solo leen claves viejas) en lugar de crear sección nueva.

## Alternativas descartadas
Flag nuevo `--max-memory-mb` (duplica semántica); mantener exacto con listas «porque entra comprimido»; `read_table`+pandas; sketches;
medir RSS en tests (frágil).

## Riesgos
La constante 96 es una estimación: se documenta como conservadora y se valida por conteo de celdas en tests; el piso de 1000 filas puede superar
el presupuesto con presupuestos ínfimos (documentado, acotado por R5).

## Reproducibilidad
`seed` (default 42) + `version_algoritmo="bounded_v1"` quedan en el perfil.

## Aprobación humana
Ver proposal.md.

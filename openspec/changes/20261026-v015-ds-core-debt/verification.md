# Verificación — 20261026-v015-ds-core-debt

## Resumen
Change de v0.15 (C3) de deuda del núcleo de ciencia de datos: `ds_profile` con estimación de bytes por dtype (B-12) y lectura columnar de dos pases para Parquet exacto (B-11); Data Card `temporality` current/as_of con kind schema v2 (B-13); decisión documentada de ciclo de vida production/deployment/monitoring (B-14); umbrales 2M/500 MB reclasificados a limitación documentada (B-15); auditoría confirmatoria de reporting/modelquality/qualityevidence/cards (D-019).

## Cambios de código
- `tools/ds_profile/sampling.py`: `bytes_por_celda_dtype`, `usa_estimacion_dtype`, `bytes_por_fila`; `schema=None` opcional en `estimar_bytes_exactos` y `decidir_plan` (sin schema, idéntico al criterio de 96 B); `plan["estimacion"]`.
- `tools/ds_profile/io_readers.py`: `LectorParquet.iter_columna`, `nombres_unicos`, `close`.
- `tools/ds_profile/report.py`: schema del lector al plan; `sampling.estimacion` y `sampling.modo_lectura` aditivos; `_perfilar_por_filas` (camino histórico), `_perfilar_columnar` (dos pases), `_puede_columnar`, cierre del lector en `finally`.
- `tools/cards/datacard.py`: `temporality`, `DATA_CARD_KIND_SCHEMA_VERSION = 2` con lectura {1, 2}, `temporality_mode`, resolvers pinneados en as_of, hallazgo `DATACARD-AS-OF-HISTORICAL`.
- `tools/cards/resolvers.py`: `source_observation_pinned_resolver`, `source_provenance_pinned_resolver`, `hash_observacion_vigente`.
- `tools/cards/assess.py` (mensaje WARN del hallazgo as_of) y `tools/cards/report.py` (tabla Temporalidad).
- Tests nuevos o ajustados: `tools/ds_profile/tests/test_columnar.py` (nuevo), `test_sampling.py`, `test_bounded_memory.py`, `tools/cards/tests/test_asof.py` (nuevo), `tools/cards/tests/test_datacard.py`, `tools/tests/test_v013_contract_inventory.py`.
- Documentación: `docs/production-lifecycle.md` (nuevo), `docs/contracts/inventory.json` (`schema-data-card-kind` v2 con `compat`), `tools/ds_profile/benchmark_bounded_memory.md`, `docs/roadmap/v0.15.md`, `docs/roadmap/v0.15-debt-matrix.md`, `ARCHITECTURE.md` §6.3, `README.md`.

## Evidencia obtenida
Resultados del Lead, ANTES de los fixes del reviewer:
- `ds_profile` en `.venv` (sin pyarrow): 162 tests OK (13 skipped).
- `ds_profile` con pyarrow 26.0.0 en venv aparte (incluye `TestParquetReal`, `TestParquetAcotado`): 162 tests OK.
- Cards y transversales (`test_asof`, `test_datacard*`, `test_resolvers*`, `test_evidence`, `test_assess`, `test_report`, parity/inert v09, inventory, compat window, `test_cards_cli`, `test_architecture_boundaries`, smokes): 565 tests OK (25 skipped).
- Revisión del reviewer (1 ciclo): 0 BLOCKER, 0 HIGH, 4 MEDIUM y 5 LOW, aplicados o documentados (ver abajo).
Re-corrida del Lead tras los fixes del reviewer:
- `ds_profile` en `.venv` (sin pyarrow): 164 tests OK (13 skipped).
- `ds_profile` con pyarrow 26.0.0 (venv aparte, fuera del repo; no cambia las dependencias del proyecto): 164 tests OK, 0 skipped.
- Cards y transversales (`test_asof`, `test_datacard`, `test_datacard_location`, `test_resolvers`, `test_assess`, `test_report`, `test_evidence`, parity/inert v09 de datacards, inventory, compat window, `test_cards_cli`, `test_architecture_boundaries`, smokes v09/v010/v013/v014): 518 tests OK (10 skipped).

Fixes del reviewer aplicados:
- M1: la estimación por dtype nunca baja de 96 B (numérico/bool/fecha/timestamp = 96; string/binary 128; complejos 160); tests derivados de `decidir_plan`/`bytes_por_celda_dtype`, cifras unificadas en spec, design, benchmark y ARCHITECTURE; los umbrales 2M/500 MB se llaman siempre heurística no validada.
- M2: `as_of` es declarativo (no se verifica contra la fecha de la observación pinneada); documentado en `datacard.py`, ARCHITECTURE, README e inventory, con test que lo fija.
- M3: ventana de compat: v0.15 lee v1 y v2, v0.14 solo v1; comentario de `DATA_CARD_KIND_SCHEMA_VERSION` ("versión máxima soportada/aceptada"); docstrings de `datacard.py` corregidos. `test_v015_compat_window.py` no referencia Data Card (sin cambios).
- M4: docstrings de `datacard.py` actualizados a {1, 2}.
- L1: `iter_columna` verifica `num_columns == 1`; nombres con "." caen a filas (test sintético).
- L3: ítem nuevo P-20 en la matriz (integraciones de deployment/monitoring), conteos D 20 y total 117; `docs/production-lifecycle.md` lo referencia.
- L4: tests de resolver de provenance pinneado y de Card v2 `current` pinneada a la vieja (stale).
- Auditoría D-019 por lectura de código y tests existentes (sin ejecución): `tools/reporting/cli.py` (`check-inputs`, `check-destination`, `validate`, `render`) y `tools/reporting/__main__.py`; `tools/reporting/tests/test_cli*.py`; `tools/modelquality/core.py` y `tests/test_core.py`; `tools/qualityevidence/core.py`, `evidence.py` y tests; `tools/cards/*` y `tools/tests/test_cards_cli.py`. Sin segunda implementación.
- No se midió el efecto del modo columnar ni de la estimación por dtype en tiempo o memoria; no se afirma ninguna cifra (ver `tools/ds_profile/benchmark_bounded_memory.md`).

## Limitaciones
- La estimación de memoria (por dtype o global) sigue siendo una estimación, no un límite duro (C-32).
- Columnar solo en Parquet + modo exacto; implica leer el archivo dos veces (menor pico de memoria, no menor tiempo).
- Los umbrales 2M filas / 500 MB no están validados contra un dataset real (B-15 reclasificado a limitación).
- Deployment/monitoring/MLOps quedan como frontera de integración (POST-v1).
- El falso fresh A -> B -> A de las Cards `current` sigue siendo una limitación conocida.

## Divergencias respecto del SDD
- Data Card as_of sin kind de evidencia nuevo `source_observation_pinned`: agregarlo a `core.OBSERVED_KINDS` rompe tests de la Foundation fuera del alcance autorizado (`test_evidence.py`, `test_resolvers_model.py`, `test_resolvers_gov.py`, `test_v09_modelgov_*`). Se reemplaza el resolver de `source_observation`/`source_provenance` en as_of (spec.md y design.md actualizados).
- Kind schema v2 exige `temporality` (en el SDD era opcional): preserva `test_datacard_location.py`, fuera de ownership, que espera inválida una Card v2 sin `temporality`.
- Criterio de `sampling.estimacion`: "dtype_v1" solo si el schema aporta algún tipo distinto de "str"; CSV queda en "global_v1".
- `DATACARD-AS-OF-HISTORICAL` no se agregó a `DATACARD_CODES` (tupla de errores de validación/IO) y se muestra como WARN en `a_check_results`.
- T3 mencionaba `test_report.py` de ds_profile; el campo `estimacion` se cubre en `test_columnar.py` y `test_bounded_memory.py`.

## Deudas
- B-15 queda como limitación documentada; validar contra un dataset real requeriría uno disponible.
- B-27 (README completo, `python -m tools.reporting` en profundidad) sigue en C6; aquí solo se agregó la mención.
- `test_io_readers.py` abre `LectorParquet` sin cerrarlo en tests preexistentes (no tocado; potencial fuga de handle en Windows).

## Resultado final
Implementación completa de T1..T18. Pendiente: resultados de tests del Lead, revisión del reviewer y cierre por el Lead.

# Tareas — 20261026-v015-ds-core-debt

estado: cerrada

## Invocaciones planificadas
- python-data-engineer (writer, secuencial por bloques A->B->C->D): implementa cada bloque en su ownership; no ejecuta.
- data-science-reviewer / reviewer único: revisa el Change completo tras el bloque D (equivalencia de caminos, semántica as_of, honestidad de la estimación).
- Lead: corre tests en `.venv` y en venv aparte con pyarrow 26.0.0; cierra el Change.

## Ownership de writers
<!-- Un solo writer secuencial; sin ownership paralelo. Rutas = "Alcance autorizado" de proposal.md. -->

## Historial de ownership
<!-- fecha — instancia — ruta — motivo (cambios de ownership hechos ANTES de que el writer edite) -->

## Skills cargados
<!-- ninguna skill cambió decisiones hasta ahora -->

## Tareas

### Bloque A — ds_profile bytes por dtype (B-12)
- [x] T1 `tools/ds_profile/sampling.py`: agregar `schema=None` a `estimar_bytes_exactos` y `decidir_plan`; tabla de bytes por prefijo de tipo (64/128/160, CSV "str"=96); `schema=None` idéntico al actual; `VERSION_ALGORITMO` intacto.
- [x] T2 `tools/ds_profile/report.py` (+ `schema.py` si hace falta): pasar `schema()` del lector a `decidir_plan`; serializar `sampling.estimacion` ("dtype_v1"|"global_v1") aditivo sin tocar `SCHEMA_VERSION`.
- [x] T3 Tests: `test_sampling.py` (mapeo por dtype, desconocido=160, CSV=96, schema=None idéntico), `test_bounded_memory.py` (recalcular asserts Parquet con `decidir_plan(schema=...)`, `TestPlanPrevio` sin cambios), `test_report.py` (campo `estimacion`).

### Bloque B — ds_profile columnar Parquet (B-11)
- [x] T4 `tools/ds_profile/io_readers.py`: método opcional `iter_columna(nombre)` en el lector Parquet (`iter_batches(columns=[col])`), errores -> `LecturaFallidaError`; Protocol sin romper.
- [x] T5 `tools/ds_profile/report.py` (+ `column_stats.py` si hace falta): camino de dos pases (digests de fila sin retener valores; luego columna por columna) solo en Parquet + exacto + schema sin list/struct/map; fallback a filas en los demás casos; `sampling.modo_lectura` ("columnar_v1"|"filas") aditivo; perfil idéntico al camino por filas.
- [x] T6 Tests `test_columnar.py` (lector sintético con `iter_columna`, sin pyarrow; fallbacks; NaN/None; orden de `top_valores`; error de lectura), equivalencia con Parquet real (skipUnless pyarrow) en `test_columnar.py`/`test_io_readers.py`.
- [x] T7 `tools/ds_profile/benchmark_bounded_memory.md`: documentar columnar (ganancia de memoria pico, doble lectura) sin cifras inventadas.

### Bloque C — Data Card as_of (B-13)
- [x] T8 `tools/cards/datacard.py` (`core.py` sin cambios; v2 exige `temporality`): `temporality`, validación (`as_of` exige `time_scope.as_of`; rechazo en kind v1), `DATA_CARD_KIND_SCHEMA_VERSION` 1->2 con lector {1,2}, docstring A->B->A actualizado.
- [x] T9 `tools/cards/resolvers.py`: resolver pinneado para `source_observation`/`source_provenance` en as_of, sin kind nuevo (resuelve `<source_id>__<hash12>` exacto; cambiado/desaparecido -> stale/unresolvable).
- [x] T10 `tools/cards/assess.py`: en as_of, requirements de fuente usan la evidencia pinneada; hallazgo `DATACARD-AS-OF-HISTORICAL`; current sin cambios; `evaluar_evidencia` intacto.
- [x] T11 `tools/cards/report.py`: mostrar modo y as_of.
- [x] T12 Tests: nuevo `tools/cards/tests/test_asof.py` (as_of vigente, pinneada intacta, pinneada cambiada/desaparecida, rechazos, v1 compat); ajustar `test_datacard.py`, `test_resolvers.py`, `test_assess.py`, `test_report.py`; revisar paridad `test_v09_datacards_parity.py` y `test_v09_datacards_inert.py`.
- [x] T13 `docs/contracts/inventory.json` (`schema-data-card-kind`: versión 2, ventana 0.14–0.15 lee v1 y v2) y `tools/tests/test_v013_contract_inventory.py` / `test_v015_compat_window.py` coherentes.

### Bloque D — decisión, auditoría y documentación (B-14, B-15, D-019)
- [x] T14 Crear `docs/production-lifecycle.md` (decisión D4 sin código).
- [x] T15 Auditoría confirmatoria reporting/modelquality/qualityevidence/cards: evidencia (rutas/CLI/tests existentes) en `docs/roadmap/v0.15-debt-matrix.md`; `README.md` documenta `python -m tools.reporting` si falta.
- [x] T16 B-15: documentar umbrales 2M/500MB como heurística no validada (benchmark + docs) sin mediciones inventadas.
- [x] T17 Actualizar `docs/roadmap/v0.15-debt-matrix.md` (B-11..B-14 "cerrado en C3", B-15 limitación), `docs/roadmap/v0.15.md` §C3 estado, `ARCHITECTURE.md` (columnar, estimación por dtype, as_of, ciclo de vida), `README.md` si corresponde.
- [x] T18 Cierre del writer: reportar `completed`/`blocked`/`needs-review` con lista de tests a correr por el Lead (`.venv` y venv con pyarrow 26.0.0).

## Dependencias
- A -> B (B reutiliza el schema y el plan de A); C independiente de A/B pero secuencial por regla; D al final (documenta lo implementado).
- T13 depende de T8; T17 depende de T1..T16.
- Verificación con pyarrow depende del Lead (venv aparte).

## Próximo paso exacto
<!-- obligatorio si estado: pausada_bloqueada -->

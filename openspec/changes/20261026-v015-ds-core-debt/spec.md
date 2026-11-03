# Spec — 20261026-v015-ds-core-debt

## Requisitos

**R1 (B-12) Estimación por dtype**
- `estimar_bytes_exactos(filas, columnas, schema=None)` y `decidir_plan(tamano_bytes, filas, columnas, max_mb, max_filas, schema=None)`.
- Con `schema=None` el resultado es idéntico al actual (96 bytes por celda global).
- Con schema: bytes por celda por prefijo de tipo pyarrow: int*/uint*/float*/double/bool/date*/timestamp* = 96 (igual que el criterio global: la estimación por dtype nunca baja de 96); string/large_string/binary = 128; decimal/list/struct/map/dictionary/desconocido = 160; tipo `"str"` (CSV) = 96. Estimado = filas × Σ bytes(dtype). `por_presupuesto` usa el promedio por columna.
- La estimación es conservadora, nunca se presenta como medida. El perfil agrega `sampling.estimacion` ("dtype_v1" | "global_v1") de forma aditiva. `VERSION_ALGORITMO="bounded_v1"` y `SCHEMA_VERSION` del perfil no cambian.

**R2 (B-11) Lectura columnar**
- Solo Parquet y modo exacto. Muestreado y CSV siguen por filas.
- Dos pases: (1) batches de todas las columnas solo para digests de fila (`duplicados_fila`), sin retener valores; (2) columna por columna con `iter_batches(columns=[col])`, alimentando `AcumuladorColumna` y los valores de esa columna, construyendo métricas y liberando.
- Método opcional `iter_columna(nombre)` en el lector; el Protocol no se rompe; si el lector no lo expone, fallback a filas. Fallback a filas también si el schema contiene list/struct/map.
- El perfil es idéntico al camino por filas, salvo `sampling.modo_lectura` ("columnar_v1" | "filas") y timestamps. Errores de lectura siguen siendo `LecturaFallidaError`. Se preserva el orden de aparición para `top_valores`.
- No se promete sandbox ni límite duro de memoria.

**R3 (B-13) Data Card as_of**
- Campo opcional `temporality: {"mode": "current"|"as_of"}` en el body (cerrado: claves desconocidas siguen dando `DATACARD-UNKNOWN-KEY`). `as_of` exige `time_scope.as_of`.
- `DATA_CARD_KIND_SCHEMA_VERSION` 1→2; el lector acepta {1,2}; v1 sin `temporality` equivale a current; `temporality` con `kind_schema_version=1` se rechaza.
- En modo as_of, la evidencia `source_observation`/`source_provenance` de la Card se resuelve con un resolver pinneado (sin kind nuevo: agregar un kind a `core.OBSERVED_KINDS` rompe tests de la Foundation fuera de este alcance): lee el directorio exacto `.harmessi/observations/<source_id>__<hash12>/` del `ref_id` y devuelve el `hash_observation` de ESA observación. Si cambió o desapareció, sigue stale/unresolvable. `evaluar_evidencia` y `default_resolvers` (15 kinds) no cambian; el cableado vive en `datacard._resolvers_por_defecto(repo_root, card)`.
- v2 EXIGE `temporality` (decisión de implementación; v1 sin `temporality` = current).
- Hallazgo informativo `DATACARD-AS-OF-HISTORICAL` cuando existe observación vigente más nueva con hash distinto (severidad según la infraestructura de hallazgos existente).
- El reporte de cards muestra modo y as_of.
- Docstring del límite A→B→A (`datacard.py:42-51`) actualizado; inventory `schema-data-card-kind` actualizado (versión y ventana de compatibilidad 0.14–0.15 lee v1 y v2).
- El comportamiento current existente (Card pinneada a B queda `CARD_STALE` al aparecer C) no cambia.

**R4 (B-14) Ciclo de vida**: `docs/production-lifecycle.md` documenta: Harmessi cubre hasta evidencia de readiness (production-readiness/operations = guidance-only); deployment/monitoring/MLOps son frontera de integración; `no_iniciada` es estado legítimo; Harmessi no integra Airflow/MLflow/Kubernetes ni CI/CD cloud; integraciones POST-v1. Sin código.

**R5 (D-019) Auditoría confirmatoria**: reporting, modelquality, qualityevidence y cards confirmados RESUELTOS en la matriz con evidencia (rutas, CLI, tests existentes); sin segunda implementación. README documenta `python -m tools.reporting` si falta.

**R6 (B-15) Umbrales**: 2M filas / 500 MB documentados como heurística no validada contra dataset real en `tools/ds_profile/benchmark_bounded_memory.md` y docs; sin mediciones inventadas.

**R7 Matriz**: B-11, B-12, B-13, B-14 pasan a "cerrado en C3" al implementarse; B-15 queda como limitación documentada.

## Criterios de aceptación
- [ ] `schema=None` produce exactamente los mismos números que antes (tests `TestPlanPrevio` de `test_bounded_memory.py` sin cambios) y smokes v09/v010 siguen verdes.
- [ ] Con schema Parquet, estimado y plan salen de `decidir_plan(..., schema=...)`; los asserts acoplados a 96 (`<=3641`) se recalculan, no son literales.
- [ ] Tests por tipo de dtype: cada prefijo mapea al valor esperado; desconocido = 160; CSV `"str"` = 96; estimación con schema >= suma conservadora esperada.
- [ ] El perfil serializa `sampling.estimacion` y `sampling.modo_lectura` aditivos; `VERSION_ALGORITMO` y `SCHEMA_VERSION` intactos; `schema-ds-profile-report` internal v1 sigue validando.
- [ ] Test de dos pases con lector sintético que expone `iter_columna` (corre sin pyarrow) da perfil idéntico al camino por filas.
- [ ] Test de equivalencia con Parquet real (skipUnless pyarrow) compara ambos caminos; verificado por el Lead en venv aparte con pyarrow 26.0.0.
- [ ] Fallback a filas con lector sin `iter_columna`, con schema anidado, en modo muestreado y en CSV; error de lectura columnar -> `LecturaFallidaError`.
- [ ] NaN/None en digests y orden de `top_valores` iguales entre caminos.
- [ ] Card `current` sin cambios de comportamiento; Card v1 existente sigue leyéndose; `temporality` en kind v1 rechazada; `as_of` sin `time_scope.as_of` rechazada; clave desconocida sigue dando `DATACARD-UNKNOWN-KEY`.
- [ ] Card as_of con observación pinneada intacta y vigente más nueva: NO stale + hallazgo `DATACARD-AS-OF-HISTORICAL`.
- [ ] Card as_of con observación pinneada cambiada o desaparecida: sigue stale/unresolvable.
- [ ] Reporte de cards muestra modo y as_of; paridad v09 (parity/inert) intacta.
- [ ] `docs/production-lifecycle.md` existe y cubre R4; `benchmark_bounded_memory.md` documenta R6 sin cifras inventadas.
- [ ] Matriz actualizada (B-11..B-14 cerrado en C3, B-15 limitación, D-019 con evidencia); inventory y `test_v013_contract_inventory.py` / `test_v015_compat_window.py` coherentes.
- [ ] Suite completa verde en `.venv` (sin pyarrow, tests de pyarrow skipped) y en venv con pyarrow.

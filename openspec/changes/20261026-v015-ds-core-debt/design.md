# Diseño — 20261026-v015-ds-core-debt

## Decisión metodológica/técnica

**D1 Estimación por dtype.** Parámetro opcional `schema` en `estimar_bytes_exactos` y `decidir_plan`. `schema=None` conserva el 96 global (compat total con tests y smokes). Con schema se mapea por prefijo del tipo pyarrow: 96 (numéricos, bool, date, timestamp: igual que el criterio global, así la estimación por dtype solo sube y no hay regresión hacia modo exacto), 128 (string/binary, conservador porque no hay estadísticas de ancho), 160 (decimal/list/struct/map/dictionary/desconocido), 96 para `"str"` de CSV (para no cambiar CSV). Estimado = filas × Σ bytes(dtype); `por_presupuesto` usa el promedio. Nunca se presenta como medida; el perfil suma `sampling.estimacion` ("dtype_v1"|"global_v1") sin tocar `VERSION_ALGORITMO` ni `SCHEMA_VERSION`. Los tests Parquet acoplados a 96 recalculan sus límites con `decidir_plan(schema=...)`.

**D2 Columnar.** Solo Parquet + exacto: el muestreado necesita orden de filas (el reservoir consume RNG por fila) y CSV re-parsearía el archivo por columna. Dos pases: pase 1 recorre todas las columnas por batches solo para el set de digests blake2b-16 por fila (`_digest_fila`; única métrica multi-columna, `duplicados_fila`); pase 2 recorre columna por columna con `iter_batches(columns=[col])`, alimenta `AcumuladorColumna` y los valores de esa columna, construye métricas y libera. Método opcional `iter_columna(nombre)` en el lector (el Protocol no se rompe); sin él, fallback a filas. El perfil resultante es idéntico al camino por filas (salvo `sampling.modo_lectura` y timestamps). La ganancia es de memoria pico (no se retienen valores de todas las columnas a la vez), no de velocidad total (se lee el archivo dos veces).

**D3 Data Card as_of.** Se agrega `temporality` opcional en el body cerrado; `as_of` exige `time_scope.as_of`. Kind schema 1→2, lector acepta {1,2}; v1 = current; `temporality` en v1 se rechaza. En as_of se cambia el resolver de `source_observation`/`source_provenance` por uno pinneado (en vez de un kind nuevo `source_observation_pinned`, que obligaría a tocar `core.OBSERVED_KINDS` y tests pinneados de la Foundation fuera del alcance): resuelve el directorio exacto `<source_id>__<hash12>` del `ref_id` y devuelve el `hash_observation` de esa observación, de modo que un cambio o desaparición real sigue siendo stale/unresolvable y no se oculta staleness. `evaluar_evidencia` no cambia (el hash pinneado se compara igual). Hallazgo informativo `DATACARD-AS-OF-HISTORICAL` cuando hay vigente más nueva con hash distinto. Se actualizan docstring A→B→A, inventory y reporte.

**D4 Ciclo de vida.** Decisión documental en `docs/production-lifecycle.md`, sin código: cobertura hasta evidencia de readiness; deployment/monitoring/MLOps como frontera de integración; `no_iniciada` legítimo; integraciones POST-v1.

**D5 Auditoría.** Confirmación de reporting/modelquality/qualityevidence/cards como RESUELTO con rutas/CLI/tests existentes en la matriz; sin reimplementar.

**D6 B-15.** No hay dataset real disponible: los umbrales 2M/500MB se documentan como heurística no validada en `benchmark_bounded_memory.md` y docs; B-15 queda como limitación.

## Target (condicional — feature_engineering, modeling)
No aplica.

## Features permitidas/prohibidas (condicional — feature_engineering)
No aplica.

## Estrategia de split/validación (condicional — holdout involucrado, modeling, evaluation)
No aplica.

## Leakage risks (condicional — feature_engineering, data_preparation, modeling)
No aplica (no hay target ni features). Riesgo análogo en as_of: una Card histórica no puede usarse para afirmar el estado actual; por eso el reporte rotula modo y as_of y emite `DATACARD-AS-OF-HISTORICAL`.

## Reproducibilidad (opcional — solo si se desvía del default: RANDOM_STATE fijo, .venv)
Se desvía: los tests con Parquet real requieren pyarrow, ausente en `.venv`; se marcan `skipUnless` y el Lead los corre en un venv aparte (pyarrow 26.0.0). El camino de dos pases se cubre sin pyarrow con un lector sintético. El modo muestreado conserva `RANDOM_STATE` sin cambios. No se ejecuta nada en este Change por el writer.

## Alternativas descartadas
- Columnar también en muestreado: rompe la semántica del reservoir.
- Columnar en CSV: reparsea el archivo por columna.
- Subir `VERSION_ALGORITMO` o `SCHEMA_VERSION`: rompe pines de smokes v09/v010; se usa campo aditivo.
- as_of como simple rótulo que suprime stale: ocultaría staleness real.
- Leer ancho real de strings desde estadísticas del footer: complejidad y dependencia de metadatos opcionales; se usa tope conservador.
- Integrar MLOps en el binario: fuera de alcance, POST-v1.

## Riesgos
- Equivalencia entre caminos: NaN/None en digests (representación `str(v)`/""), tipos anidados (fallback), orden de aparición de `top_valores`; mitigado con tests de equivalencia.
- La estimación puede seguir subestimando strings muy anchos: es estimación, no límite duro (C-32).
- Bump de kind schema 2: Cards v2 no son legibles por versiones previas; ventana de compat 0.14–0.15 lee v1 y v2, y se documenta en inventory.
- Tests de pyarrow no corren en `.venv`: dependen de la verificación del Lead.
- Tests de límites con 96 (`<=3641 = 1MiB//(96*3)`) cambiarán con schema; deben recalcularse sin literales.

## Aprobación humana
<!-- El registro de aprobación (usuario, fecha, alcance, versión de artefactos, cita) es único
por cambio y vive en la sección "Aprobación" de proposal.md — no se duplica acá. -->

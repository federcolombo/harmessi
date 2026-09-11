# Spec — 20260911-ds-profile-project-eda

## Requisitos
1. `ds_profile` debe calcular sobre CSV y Parquet: filas, columnas, tamaño en bytes, schema/dtypes, fingerprint, duplicados de fila; por columna: dtype, null count/%, unique count/cardinalidad, min/max, media/mediana/std (numéricas), cuantiles (p25/p50/p75/p95/p99), top-N valores+frecuencia (categóricas), fecha min/max (si detectable), flags `constante`/`casi_constante`/`alta_cardinalidad`/`posible_id`; calidad agregada (columnas 100% nulas, filas duplicadas, columnas con posible problema de tipo, columnas sospechosas por cardinalidad).
2. CSV se procesa con `csv`+`statistics` de stdlib, sin pandas. Parquet se procesa vía `pyarrow`, importado de forma perezosa (solo dentro de la rama que lo necesita) — si falta, `ds_profile` termina con exit code 3 y un mensaje claro indicando la dependencia faltante, sin crear ningún archivo de salida parcial.
3. La capa de lectura (`io_readers.py`) queda desacoplada del cálculo (una interfaz común entre lectores CSV/Parquet) para poder incorporar pandas/polars/duckdb más adelante sin rediseñar el resto de `ds_profile`.
4. Toda métrica que exceda un umbral configurable (`--max-filas-exactas`, default 2000000; `--max-mb-exactos`, default 500) pasa a modo muestreado (reservoir sampling reproducible, semilla fija vía `--seed`, default 42); las métricas de metadata (filas, schema, tamaño, fingerprint, nulls, min/max, media/std) son siempre exactas, calculadas en streaming (nunca cargando el dataset completo en memoria). Cada métrica en el JSON de salida declara su propio campo de exactitud (`"exacta"`/`"muestreada"`), nunca un flag global.
5. Antes de abrir `--input`, `ds_profile` reusa `dsguard.pathguard.cargar_config`/`resolver_ruta_relativa` y `dsguard.repo.path_matches_any` (import de librería, sin modificar `pathguard.py`) para negarse explícitamente (exit 2, mensaje claro) si la ruta cae dentro de un holdout declarado en `.claude/guardrails.json` sin excepción de lectura vigente — segunda capa de defensa detrás del hook `PreToolUse` existente (best-effort para Bash).
6. Output: `.harmessi/profiles/<profile_id>/profile.json` (JSON fuente de verdad, `schema_version`, `dataset_path`, `fingerprint`, `created_utc`, `tool_version`, filas/columnas/tamaño, schema, detalle por columna, calidad agregada, sampling, límites aplicados); `profile.md` opcional y derivado, solo con `--markdown`, nunca con datos que no estén en el JSON.
7. `eda.md` (skill + plantilla) define "model-valid EDA": cutoff/information boundary declarado obligatorio, holdout protegido, fingerprint/`profile_id` citado, hipótesis separadas de decisiones, riesgos de leakage explícitos. El artefacto `openspec/changes/<id>/eda.md` es opcional: se crea solo cuando el Lead determina que el cambio lo necesita, y **no** se agrega al set fijo de artefactos que crea/exige `ds_guard init`/`ds_guard validate`.
8. No se agrega ningún subagente nuevo, ni se modifica `ds_guard.py`, ni se toca `tools/nbrunner/*`, ni se agregan criterios KDD nuevos/enforceable en `kdd.py`.

## Criterios de aceptación
- [ ] `python -m tools.ds_profile run --input <csv válido> --output .harmessi/profiles/` produce `profile.json` con todos los campos del Requisito 1, exit code 0.
- [ ] Mismo comando sobre un `.parquet` válido con `pyarrow` instalado produce el mismo tipo de resultado, exit code 0.
- [ ] Mismo comando sobre un `.parquet` sin `pyarrow` instalado termina con exit code 3 y un mensaje que nombra explícitamente la dependencia faltante, sin crear `profile.json`.
- [ ] Un dataset cuyo tamaño/filas excede los umbrales configurados marca las métricas correspondientes como `"muestreada"` con método/semilla/tamaño de muestra auditables en el JSON; las métricas de metadata siguen `"exacta"`.
- [ ] Una ruta `--input` que cae dentro de un holdout declarado en `.claude/guardrails.json` (sin excepción de lectura vigente) termina con exit code 2 antes de abrir el archivo.
- [ ] Fingerprint estable: mismo archivo de entrada produce el mismo hash en dos corridas independientes.
- [ ] JSON estable: mismo input y mismos límites producen el mismo `profile.json` salvo `created_utc`.
- [ ] `.claude/skills/lead-data-scientist/eda.md` y `templates/eda.md` existen y no aparecen en la lista de artefactos que `ds_guard init --modo completo/abreviado` crea obligatoriamente ni que `ds_guard validate` exige.
- [ ] `tools/ds_init/manifest.py` incluye entradas nuevas para instalar `tools/ds_profile/*`, `eda.md` y su plantilla en un proyecto destino, y sus tests de desarrollo quedan en `EXCLUSIONES_PERMANENTES`.
- [ ] Suite completa (`tools/ds_profile/tests`, `tools/tests`, `tools/ds_init/tests`, `tools/harmessi/tests`) pasa; `check_manifest_parity` y `harmessi doctor` no reportan errores nuevos atribuibles a este cambio.

## Unidad de análisis / grain (condicional — data_understanding, feature_engineering, modeling)
No aplica: este cambio no analiza un dataset propio del proyecto, construye una herramienta de propósito general (`ds_profile`) y un proceso (Project EDA) que otros cambios usarán sobre sus propios datasets.

## Cutoff / information boundary (condicional — feature_engineering, data_preparation, modeling)
No aplica como fecha de corte de un dataset real de este cambio — sí es objeto directo del cambio en otro sentido: `ds_profile`/Project EDA son la infraestructura que hace citable y verificable el cutoff declarado por *otros* cambios futuros (ver Requisito 7 arriba y `design.md`).

## Baseline (condicional — modeling)
No aplica (no hay modelo involucrado).

## Métrica primaria (condicional — modeling, evaluation)
No aplica.

## Métricas secundarias (opcional)
No aplica.

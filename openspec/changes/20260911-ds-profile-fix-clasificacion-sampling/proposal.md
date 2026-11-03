# Propuesta — 20260911-ds-profile-fix-clasificacion-sampling

## Problema
El cambio `20260911-ds-profile-project-eda` (ya cerrado) documentó 2 limitaciones aceptadas en `verification.md`: (1) una columna entera cuyos valores observados son subconjunto de `{0,1}` se clasifica como `booleano` y pierde min/max/media/std/mediana/cuantiles; (2) `--max-filas-exactas` no aplica a CSV (`LectorCSV.filas_exactas()` siempre devuelve `None`), solo el umbral de MB dispara modo muestreado en CSV.

## Objetivo
Corregir ambas limitaciones sin reabrir ninguna otra decisión del diseño ya cerrado.

## Evidencia
- `openspec/changes/20260911-ds-profile-project-eda/verification.md`, sección "## Limitaciones", ítems 1 y 2.
- `tools/ds_profile/column_stats.py`, función `clasificar_dtype` (chequeo `distintos_normalizados <= {"0", "1"}`).
- `tools/ds_profile/io_readers.py`, `LectorCSV.filas_exactas()` (devuelve `None` siempre, con el motivo documentado en su docstring).

## Supuestos descartados
No aplica — la corrección fue especificada exacta por el usuario, no hay supuesto que la exploración haya desmentido.

## Hipótesis (condicional — solo cambios metodológicos)
No aplica: no es un cambio metodológico.

## Alcance
1. `clasificar_dtype`: una columna con valores numéricos `{0,1}` (enteros o flotantes) conserva su dtype numérico (`entero`/`flotante`) y todas sus estadísticas; se agrega un flag `binary_numeric` (dentro de la lista `flags` ya existente, junto a `constante`/`alta_cardinalidad`/etc.) cuando el conjunto de valores distintos parseados como número es exactamente `{0.0, 1.0}`. Los booleanos reales/textuales (`true`/`false`, case-insensitive) siguen clasificándose como `booleano` sin cambios. Sin inferencia por nombre de columna.
2. `LectorCSV.filas_exactas()`: deja de devolver `None` siempre — cuenta las filas del CSV en una pasada streaming propia (memoria acotada, nunca materializa todas las filas), para que `sampling.decidir_modo` pueda aplicar el umbral `--max-filas-exactas` también a CSV, igual que ya hace con Parquet vía metadata.

## Fuera de alcance
Cualquier otra parte del diseño de `ds_profile`/Project EDA ya cerrado. No se instala `pyarrow`. No se reabre Project EDA ni se agregan capacidades nuevas (HTML, report engine, etc.).

## Holdout policy (condicional — solo cambios "sensible")
No aplica.

## Impacto en production-readiness (opcional)
No aplica.

## Criterios de aceptación (spec-lite — solo SDD abreviado)
- [ ] Columna CSV con valores `"0"`/`"1"` (string, como llega de `csv.DictReader`) → `dtype: "entero"`, flag `binary_numeric` presente, `min`/`max`/`media`/`mediana`/`std`/`cuantiles` calculados normalmente.
- [ ] Columna con valores `"0.0"`/`"1.0"` → `dtype: "flotante"`, flag `binary_numeric` presente, mismas estadísticas calculadas.
- [ ] Columna con valores `"true"`/`"false"` (case-insensitive) → `dtype: "booleano"`, sin flag `binary_numeric`, sin cambios de comportamiento.
- [ ] Un dataset CSV cuyas filas superan `--max-filas-exactas` (pero no `--max-mb-exactos`) pasa a modo muestreado; uno que supera `--max-mb-exactos` (pero no filas) también; uno bajo ambos umbrales queda exacto.
- [ ] `filas`/`tamano_bytes`/`schema`/`fingerprint` siguen siempre exactos, sin importar el modo.
- [ ] Sampling reproducible: misma semilla + mismo CSV → misma muestra.
- [ ] Ningún archivo fuera de `tools/ds_profile/{column_stats.py,io_readers.py,report.py,sampling.py}` y sus tests correspondientes se modifica.

## Decisión técnica (design-lite — solo SDD abreviado)
`clasificar_dtype`: se elimina la rama `or distintos_normalizados <= {"0", "1"}` del chequeo de `booleano` (queda solo `distintos_normalizados <= {"true", "false"}`), sin tocar el resto del orden de clasificación (booleano→entero→flotante→fecha→texto). Se agrega una función nueva (nombre a elección del implementador, ej. `es_binario_numerico(valores_no_nulos, dtype) -> bool`) que evalúa, sobre los mismos `valores_orden` ya usados para clasificar, si el conjunto de valores parseados a `float` es exactamente `{0.0, 1.0}` — solo cuando `dtype` ya salió `entero`/`flotante`. `construir_metricas_columna` agrega `"binary_numeric"` a la lista `flags` cuando esa función devuelve `True`.

`LectorCSV.filas_exactas()`: implementa una pasada streaming propia (abre el archivo, cuenta filas de datos con `csv.reader`, resta el header si corresponde) — costo de una lectura adicional del archivo, aceptado explícitamente por el usuario ("una segunda pasada streaming sobre CSV es aceptable"). No cambia `iter_filas()` ni la forma en que `report.py` ya cuenta `filas_totales` en su propio loop (eso sigue siendo la fuente de verdad del campo `filas` del JSON final; `filas_exactas()` del lector solo alimenta la decisión de modo, ANTES de esa pasada principal).

## Aprobación
- Usuario: Federico Colombo
- Fecha: 2026-09-11
- Alcance aprobado: los 2 puntos de "## Alcance" arriba, exactamente como los especificó el usuario en el chat.
- Versión de artefactos referenciada: primer borrador de `proposal.md`/`tasks.md` de este cambio.
- Cita o descripción fiel de qué se aprobó: *"Antes de commitear el Bloque 6, corregí únicamente estas dos limitaciones. 1. BINARIAS NUMÉRICAS [...] 2. UMBRAL DE FILAS EN CSV [...] No tocar el diseño restante. No instalar pyarrow. No reabrir Project EDA ni agregar nuevas capacidades."*, con el detalle punto por punto de reglas y tests pedidos en ese mensaje.

## Motivo de rechazo
No aplica.

## Desacuerdo registrado
No aplica.

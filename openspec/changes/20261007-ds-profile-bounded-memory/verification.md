# Verificación — 20261007-ds-profile-bounded-memory

## Resumen ejecutivo
Corrective C de v0.9 (feedback real de Harmessi 0.8.0: memoria crítica con un Parquet 620.570 × 27, ~20 MB comprimido). SDD aprobado por hash
el 2026-10-07 con la autorización humana anticipada. Todas las ejecuciones pasaron por el runtime gobernado (`ds_guard exec pytest`).
Aislado en `tools/ds_profile/**` + docs/tests. No toca Cards, autonomy, lifecycle, installer, Doctor, reporting, modelquality ni governance.

## Causa raíz confirmada
En modo exacto `report.generar_perfil` retenía la lista completa de valores no nulos por columna y la lista completa de filas como tuplas de
strings (~2 × filas × columnas objetos Python ≈ 33 M para el caso real). La decisión exacto/muestreado usaba el tamaño COMPRIMIDO (500 MB) y
2 000 000 filas, por lo que 20 MB / 620 k filas quedaba «exacto». El reservoir muestreado no tenía tope por memoria y Parquet leía con el
`batch_size` por defecto (65 536).

## Qué entrega
- **Decisión previa por presupuesto** (`sampling.decidir_plan`): solo metadata (bytes, filas del footer/conteo CSV, columnas) contra
  `--max-mb-exactos` (ahora presupuesto de memoria de trabajo; sin flags nuevos). Estimación `filas × columnas × 96 B`; motivos
  `tamano_archivo | filas | memoria_estimada`. Caso real ⇒ `memoria_estimada`. `decidir_modo` conserva firma.
- **Exacto por acumuladores O(1)** (ambos modos): filas, nulos, min/max, media/std, fechas (ya lo eran) + `dtype`, `binary_numeric` y
  `posible_problema_tipo` (nuevos contadores; equivalencia con las funciones de referencia probada, incl. 200 casos aleatorios).
- **Retención acotada:** duplicados por digest blake2b-16 (no tuplas); reservoir con tope = `min(200 000, max_filas_exactas, presupuesto/(96·columnas))`
  (piso 1000); Parquet por batches `tamano_batch(columnas)` ≤ 8192 y ≤ 2 M celdas, nunca `read_table`/pandas.
- **Metadata aditiva en `sampling`:** `motivo`, `filas_observadas`, `version_algoritmo="bounded_v1"`, `presupuesto_bytes`, `estimado_bytes_exactos`.
- **Fail-safe:** `LecturaFallidaError`/`PresupuestoInsuficienteError` ⇒ exit 4 con mensaje accionable, sin `profile.json` parcial; `MemoryError` y
  errores del reader traducidos; bugs de programación NO se disfrazan.
- Docs: ARCHITECTURE §6.3, roadmaps v0.9/v0.10, benchmark manual no gateado (`tools/ds_profile/benchmark_bounded_memory.md`).

## Exacto vs muestreado
Exactos siempre: row count, nulls, min/max, media/std, fecha_min/max, dtype, `binary_numeric`, `posible_problema_tipo`. Exactos solo dentro del
presupuesto (si no, `muestreada`): `unique`, `top_valores`, `mediana`, `cuantiles`, flags de cardinalidad, `duplicados_fila`.
Cambios de significado declarados: (1) en modo muestreado `dtype` y los dos flags ahora son exactos sobre todas las filas (antes salían de la
muestra); (2) en modo muestreado los flags de cardinalidad usan como denominador las filas de la muestra (antes mezclaban numerador de muestra y
denominador total, lo que impedía que `alta_cardinalidad`/`casi_constante` se dispararan); (3) datasets medianos (p. ej. ≳ 200 k filas × 27 col con
el presupuesto por defecto) pasan a muestreado, y `datacontracts` ve `unique.exactitud="muestreada"` (comportamiento consciente del Change).
Modo exacto: perfil idéntico al previo (salvo metadata aditiva).

## Ejecuciones reales (runtime gobernado)
- Dirigida `tools/ds_profile` (venv del repo, sin pyarrow): **159 passed, 10 skipped**; con pyarrow (otro intérprete): **169 passed, 0 skipped** (incluye
  Parquet: batches acotados, sin `read_table`, perfil muestreado reproducible, truncado ⇒ exit 4). Una corrida intermedia tuvo 1 fallo de un test propio
  (aserción sobre el mensaje de error del reader), corregido y re-ejecutado.
- Regresión ACOTADA (solo consumidores/inercia de `ds_profile`): R1 `datasources/tests`, `datacontracts/tests`, `leadrun/test_allowlist`,
  `reporting/test_evidence|test_validation`: **508 passed, 2 skipped**. R2 `tools/tests` de arquitectura/neutralidad/scientific_validity/
  release_hardening + `ds_init/test_manifest` (+ un test de ds_profile como ancla de alcance): **232 passed**.
- Total único sin doble contar (suites distintas): 159 + 508 + 232 = **899 passed**, 12 skipped, 0 failed; la corrida con pyarrow repite la suite
  de ds_profile con otro intérprete y aporta 10 tests Parquet adicionales ejecutados (no se suma como cobertura nueva).
- **Por qué la regresión acotada es suficiente:** el cambio vive en `tools/ds_profile/**`; los únicos consumidores de su código son `datasources`
  (`file_observer`) y `datacontracts` (`holdout_guard`), más tests de arquitectura/neutralidad que inspeccionan imports de `ds_profile`. No cambió ningún
  módulo compartido (ni `dsguard`, ni manifiesto: los archivos modificados ya se distribuyen; el `.md` del benchmark no se instala). Cards, autonomy,
  reporting completo, ds_init completo, modelquality y Doctor no importan `ds_profile` ni dependen de lo cambiado.
- Benchmark manual reducido (40 k × 27): exacto pico 57 MB (≈ 53 B/celda < 96 estimados); muestreado 18 MB (muestra 1000). El benchmark completo de
  620 k × 27 no terminó en ~40 min (costo de parseo por celda preexistente + `tracemalloc`) y se abortó; documentado, no gateado.

## Proceso de revisión (2 ciclos)
- **Ciclo 1:** 0 bloqueantes. I1 flags de cardinalidad en muestreado (preexistente, ahora más visible) ⇒ denominador = muestra; I2 `except` demasiado ancho ⇒
  solo el avance del reader se traduce, `MemoryError` por separado y wrapper global; I3 batch fijo en fuentes anchas ⇒ `tamano_batch`; I4 `96 B/celda` es
  orden de magnitud ⇒ documentado; I5 efecto en consumidores ⇒ declarado y `--help` actualizado; M1 test Parquet con row group único; M4 constante muerta.
- **Ciclo 2:** sin bloqueantes ni importantes nuevos; fixes correctos.

## Limitaciones y deudas (no bloqueantes)
- `BYTES_POR_CELDA = 96` es estimación, no tope duro (strings largos o tablas muy angostas pueden excederlo ~1–2×); el piso de 1000 filas puede superar
  presupuestos ínfimos (acotado por el límite de 20 M celdas ⇒ exit 4).
- Parquet por batches de filas completas (no columna a columna); lectura columnar es deuda v0.10.
- CSV hace tres lecturas (conteo de filas, perfil, fingerprint); el conteo no se omite aunque el tamaño ya decida muestreado.
- `construir_metricas_columna` y `_parsear_fecha` por celda son costosos en fuentes enormes (preexistente).
- CSV irregular con filas más largas que el header usa clave `None` y `REGEX_POSIBLE_ID.match(None)` falla (preexistente, no corregido; sin test).
- `file_observer` propaga `LecturaFallidaError`/`PresupuestoInsuficienteError` como excepciones (solo la CLI las traduce a exit 4).
- `ds_profile.TOOL_VERSION` sigue en 0.1.0; la versión del algoritmo se registra en `sampling.version_algoritmo`.
- `core.autocrlf` avisa conversión a CRLF al commitear (deuda v0.10 LF/CRLF). `docs/feedback/` y `.harmessi/` sin versionar.

## One-writer
El Lead implementó directamente (un solo editor, sin writers paralelos); revisores de solo lectura.

## Resultado final
Corrective C completo y verde. Sin STOP nuevos. Listo para cierre.

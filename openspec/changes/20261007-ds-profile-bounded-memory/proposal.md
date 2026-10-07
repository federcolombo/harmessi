# Propuesta — 20261007-ds-profile-bounded-memory

> Corrective C de v0.9, originado en feedback real de Harmessi 0.8.0 (`docs/feedback/20261005_segmentacion-pc.md`): `ds_profile`
> llevó a la máquina a «memoria crítica» con un Parquet de 620.570 filas × 27 columnas (~20 MB comprimido, Windows 11, Python 3.12,
> pandas/pyarrow). No renumera Changes 0–5. Change 5 NO se toca.

## Problema
`report.generar_perfil` en modo EXACTO retiene en RAM (a) la lista completa de valores no nulos de cada columna
(`valores_completos`, `report.py:147,164-165`) y (b) la lista completa de filas como tuplas de strings (`filas_como_tuplas`,
`report.py:148,170`), es decir ~2 × filas × columnas objetos Python (≈ 33 M para el caso real, varios GB). La decisión exacto/muestreado
(`sampling.decidir_modo`) usa el tamaño COMPRIMIDO (500 MB) y 2.000.000 de filas: un archivo de 20 MB y 620 k filas queda
«exacto» por ambos umbrales. Además, en modo muestreado el `ReservoirSampler` retiene `S` filas completas como dict sin tope por memoria
(`S = min(200 000, max_filas_exactas)`), y `LectorParquet.iter_filas` usa `iter_batches()` con el `batch_size` por defecto de pyarrow (65 536)
sin cota explícita.

## Objetivo
Memoria acotada por diseño: la decisión exacto→muestreado ocurre ANTES de acumular, a partir de metadata y de una estimación explícita del
working set contra un presupuesto de MB; lo barato sigue exacto por acumuladores; lo que necesita muchos valores se muestrea
determinísticamente con tope; la degradación queda explícita en el perfil; sin dependencias nuevas.

## Evidencia (audit 2026-10-07)
Clasificación de cada estadística actual (`column_stats.py`, `report.py`, `schema.py`):
- **A. Solo acumuladores (ya lo son):** total, nulos, min/max numérico, media/std (Welford), fecha_min/fecha_max.
- **A. Reducibles a acumuladores O(1) (hoy dependen de la lista, se vuelven exactas en streaming):** dtype (booleano/entero/flotante/fecha/texto:
  son proporciones y un conjunto ⊆ {true,false}), flag `binary_numeric` (conjunto de floats distintos, tope 3), flag `posible_problema_tipo`
  (fracción numérica-o-fecha).
- **B. Cardinalidad:** `unique.count`, `top_valores`, flags `constante`/`casi_constante`/`alta_cardinalidad`/`posible_id` (necesitan el
  multiconjunto de valores).
- **C/D. Todos los valores / orden:** `mediana`, `cuantiles`.
- **E. Filas completas:** `duplicados_fila`.
Formatos: CSV (`csv.DictReader`, streaming), Parquet (`iter_batches`). `column_stats`/`report` son comunes: el fix beneficia a ambos.
Opciones existentes: `--max-filas-exactas` (2 000 000), `--max-mb-exactos` (500, hoy sobre bytes de archivo). Consumidores del `profile.json`
(`datasources/profile_bridge`, `datacontracts/validation`) leen `sampling.activo/metodo/semilla/tamano_muestra`, `unique.exactitud`,
`exactitud_estadisticos`: ya existe metadata de exactitud y se reutiliza.

## Supuestos descartados
- «Tamaño comprimido ≈ memoria»: falso (Parquet descomprime ×10–50 y los objetos Python añaden overhead).
- «Parquet por row-groups ⇒ memoria acotada»: el reader sí, el cálculo no (retiene todo).
- «Hace falta t-digest/HyperLogLog/columnar reader»: no; muestreo determinista acotado + acumuladores O(1) alcanzan.

## Alcance
`tools/ds_profile/` (`sampling.py`, `column_stats.py`, `report.py`, `io_readers.py`, `cli.py`) y sus tests; benchmark manual documentado;
`ARCHITECTURE.md` (fila de `ds_profile`) y roadmap v0.9/v0.10 (documentación).

## Fuera de alcance
Cards, autonomy, `ds_guard` lifecycle, installer, Doctor, reporting, modelquality, governance, Change 5, lectura columnar en dos pasadas,
algoritmos de sketch, dependencias nuevas, cambiar el schema del `profile.json` (solo campos aditivos dentro de `sampling`).

## Principios
Exacto donde es O(1)/O(k); nunca fallback silencioso; nada sampled presentado como exacto; determinismo por seed+versión; fail-safe con mensaje
accionable; backward compatible para fuentes pequeñas.

## Deudas
Parquet sigue leyéndose por batches de filas completas (no columna a columna) porque `duplicados_fila` necesita filas; lectura columnar queda para
una versión posterior. En modo muestreado las flags de cardinalidad mezclan denominador total con distintos de muestra (preexistente; se documenta).

## Criterios de cierre
Ver spec.md.

## Aprobación
- Usuario:
- Fecha:
- Alcance aprobado:
- Versión de artefactos referenciada:
- Cita o descripción fiel de qué se aprobó:

## Alcance autorizado

- openspec/changes/20261007-ds-profile-bounded-memory/**
- ARCHITECTURE.md
- docs/roadmap/v0.9.md
- docs/roadmap/v0.10.md
- tools/ds_profile/**
- tools/datasources/tests/**
- tools/datacontracts/tests/**

## Motivo de rechazo

## Desacuerdo registrado

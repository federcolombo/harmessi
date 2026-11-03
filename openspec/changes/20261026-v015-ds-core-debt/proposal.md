# Propuesta — 20261026-v015-ds-core-debt

## Problema
Cuatro deudas de ciencia de datos del núcleo (matriz v0.15, B-11..B-15) siguen abiertas:

- B-11: `ds_profile` lee todas las columnas por batches (`iter_batches` sin proyección) y, en modo exacto, retiene los valores completos de todas las columnas a la vez (`tools/ds_profile/report.py:149-312`). En Parquet esto no aprovecha la lectura columnar.
- B-12: la estimación de bytes usa un único `BYTES_POR_CELDA=96` (`tools/ds_profile/sampling.py`) sin mirar el dtype, aunque el schema de Parquet está disponible en el footer antes de leer filas.
- B-13: una Data Card pinneada a una observación histórica queda `CARD_STALE` apenas aparece una observación más nueva de la fuente (`tools/cards/assess.py:221`, `resolvers.py:285-329`, `tests/test_resolvers.py:364-372`). `time_scope` (`datacard.py:127,137`) es solo informativo. No existe semántica explícita "current" vs "as_of".
- B-14: no hay decisión documentada sobre el ciclo de vida production/deployment/monitoring: las plantillas `operations.md.tmpl` y `production-readiness.md.tmpl` son guía y deployment/monitoring quedan `no_iniciada`, sin que un documento diga que eso es legítimo.
- B-15: los umbrales de muestreo 2M filas / 500 MB no están validados contra un dataset real.

Además D-019 (reporting/modelquality/qualityevidence/cards) figura RESUELTO y la hoja de ruta pide solo una auditoría confirmatoria.

## Objetivo
Cerrar B-11..B-14 con implementación y evidencia determinista, documentar B-15 como límite explícito y confirmar con evidencia D-019 sin segunda implementación.

## Evidencia
- `tools/ds_profile/report.py:149-312` (`_generar_perfil`), `:283-293` (serialización de `sampling`).
- `tools/ds_profile/sampling.py` (`BYTES_POR_CELDA=96`, `estimar_bytes_exactos`, `decidir_plan`, `VERSION_ALGORITMO="bounded_v1"` pineado por smokes v09/v010).
- `tools/ds_profile/io_readers.py` (`schema()`: CSV `{col:"str"}`; Parquet `{col: str(pyarrow type)}` desde el footer).
- `tools/cards/assess.py:221`, `tools/cards/resolvers.py:285-329`, `tools/cards/datacard.py:42-51,127,137,484-489,517-518`, `tools/cards/tests/test_resolvers.py:364-372`.
- `docs/contracts/inventory.json`: entrada `schema-data-card-kind`.
- `docs/roadmap/v0.15.md` §C3; `docs/roadmap/v0.15-debt-matrix.md` B-11..B-15, D-019, C-32.
- pyarrow no está en `.venv`; el Lead verifica con un venv aparte (pyarrow 26.0.0).

## Supuestos descartados
- "El modo muestreado puede ser columnar": falso, el `ReservoirSampler` consume RNG por fila y exige orden de filas.
- "Subir `VERSION_ALGORITMO` es seguro": falso, está pineado por smokes v09/v010; no se toca.
- "as_of es solo un rótulo": falso, ocultar el stale real de una fuente que cambió sería peor que el falso stale actual; as_of debe seguir detectando cambio de la observación pinneada.
- "D-019 requiere trabajo": solo auditoría confirmatoria.

## Hipótesis (condicional — solo cambios metodológicos)
No aplica (cambio técnico, no metodológico).

## Alcance
- A. `ds_profile`: estimación de bytes por dtype (`schema` opcional en `estimar_bytes_exactos` y `decidir_plan`), con `schema=None` idéntico al actual; campo aditivo `sampling.estimacion`.
- B. `ds_profile`: camino columnar de dos pases solo para Parquet + modo exacto, con perfil idéntico al camino por filas; campo aditivo `sampling.modo_lectura`.
- C. Data Card: `temporality {"mode": "current"|"as_of"}`, `DATA_CARD_KIND_SCHEMA_VERSION` 1→2 con lector {1,2}, evidencia `source_observation_pinned`, hallazgo `DATACARD-AS-OF-HISTORICAL`, reporte de cards.
- D. Decisión de ciclo de vida production/deployment/monitoring (`docs/production-lifecycle.md`, sin código), auditoría confirmatoria reporting/modelquality/qualityevidence/cards, límite B-15 documentado, actualización de matriz, inventory, ARCHITECTURE y README.

## Fuera de alcance
- MLOps, integración con Airflow/MLflow/Kubernetes/CI-CD cloud (POST-v1).
- Métricas de modelo en el binario.
- Columnar para CSV o para modo muestreado.
- Subir `VERSION_ALGORITMO` o `SCHEMA_VERSION` del perfil.
- Sandbox o límite duro de memoria (C-32 sigue como limitación; la estimación nunca se presenta como medida).
- Segunda implementación de reporting/modelquality/qualityevidence/cards.
- `python -m tools.reporting` en README solo si falta (B-27 completo es de C6).
- Validar umbrales con dataset real (no hay dataset disponible; no se inventan mediciones).

## Holdout policy (condicional — solo cambios "sensible")
No aplica: no se tocan holdouts ni datasets sellados.

## Impacto en production-readiness (opcional)
`docs/production-lifecycle.md` fija que Harmessi cubre hasta evidencia de readiness; deployment y monitoring son frontera de integración.

## Criterios de aceptación (spec-lite — solo SDD abreviado)
Ver `spec.md`.

## Decisión técnica (design-lite — solo SDD abreviado)
Ver `design.md`.

## Aprobación
- Usuario:
- Fecha:
- Alcance aprobado:
- Versión de artefactos referenciada:
- Cita o descripción fiel de qué se aprobó:

## Alcance autorizado
- ARCHITECTURE.md
- README.md
- docs/roadmap/v0.15.md
- docs/roadmap/v0.15-debt-matrix.md
- docs/contracts/inventory.json
- docs/production-lifecycle.md
- tools/ds_profile/sampling.py
- tools/ds_profile/io_readers.py
- tools/ds_profile/report.py
- tools/ds_profile/column_stats.py
- tools/ds_profile/schema.py
- tools/ds_profile/tests/test_bounded_memory.py
- tools/ds_profile/tests/test_io_readers.py
- tools/ds_profile/tests/test_report.py
- tools/ds_profile/tests/test_sampling.py
- tools/ds_profile/tests/test_columnar.py
- tools/ds_profile/benchmark_bounded_memory.md
- tools/cards/datacard.py
- tools/cards/resolvers.py
- tools/cards/assess.py
- tools/cards/core.py
- tools/cards/report.py
- tools/cards/tests/test_datacard.py
- tools/cards/tests/test_resolvers.py
- tools/cards/tests/test_report.py
- tools/cards/tests/test_assess.py
- tools/cards/tests/test_asof.py
- tools/tests/test_v09_datacards_parity.py
- tools/tests/test_v09_datacards_inert.py
- tools/tests/test_v013_contract_inventory.py
- tools/tests/test_v015_compat_window.py

## Motivo de rechazo
<!-- completar solo si estado: descartada -->

## Desacuerdo registrado
<!-- completar solo si estado: pausada_bloqueada tras 2 rondas de revisión sin acuerdo -->

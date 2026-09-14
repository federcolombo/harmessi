# Tareas — 20260914-lifecycle-core-schema

estado: cerrada

## Invocaciones planificadas
<!-- rol, momento del ciclo, y qué produce cada una -->
- Python Data Engineer (implementación): crear `openspec/lifecycle/state.json` inicial +
  `tools/dsguard/lifecycle.py` completo, según `spec.md`/`design.md`. Produce: módulo + archivo
  de estado inicial.
- Data Science Reviewer (revisión de código, antes de que se ejecute nada): revisa el diff. Solo
  informa hallazgos.
- Python Data Engineer (post-revisión, planificada, corre siempre haya o no hallazgos): corrige
  si hace falta, deja `estado: en_verificacion`.
- Python Data Engineer (cierre, planificada): agrega evidencia real a la sección de verificación,
  deja `estado: cerrada`.

## Tareas
- [x] Crear `tools/dsguard/lifecycle.py`: catálogos (`FASES_CRISPDM`, `PASOS_KDD`,
  `MAPEO_CRISPDM_A_KDD`, `MAPEO_KDD_A_CRISPDM`, `MLOPS_TIERS`, `MLOPS_CAPACIDADES`,
  `ESTADOS_VALIDOS`), excepción `LifecycleEstadoError`, `estado_inicial()`.
- [x] Implementar `state_path`, `validar_estructura`, `leer_estado`, `escribir_estado`,
  `lifecycle_init` en el mismo módulo.
- [x] Crear el `openspec/lifecycle/state.json` inicial de referencia (podés generarlo llamando a
  `lifecycle_init` sobre este propio repo como parte de la tarea de implementación, ya que este
  repo es donde vive el schema real — confirmalo con el Lead antes si tenés dudas).
- [x] Tests: creación de state inicial (`lifecycle_init` sobre repo sin archivo previo).
- [x] Tests: idempotencia de `lifecycle_init` (segunda llamada no reescribe).
- [x] Tests: `schema_version` correcto en `estado_inicial()`.
- [x] Tests: estructura completa CRISP-DM (8 fases exactas, forma exacta).
- [x] Tests: estructura completa KDD (5 pasos exactos, forma exacta).
- [x] Tests: `MAPEO_CRISPDM_A_KDD` exacto y `MAPEO_KDD_A_CRISPDM` como inversa derivada.
- [x] Tests: estructura MLOps (3 tiers, 16 capacidades exactas, forma exacta).
- [x] Tests: lectura válida (`leer_estado` sobre archivo bien formado).
- [x] Tests: JSON corrupto → `LifecycleEstadoError`, fail-closed, nada escrito.
- [x] Tests: `schema_version` desconocida → `LifecycleEstadoError` con mensaje explícito.
- [x] Tests: escritura atómica.
- [x] Tests: round-trip (escribir → leer → estructuras iguales).
- [x] Tests: no mutación accidental en lectura (bytes del archivo iguales antes/después de leer
  dos veces).
- [x] Tests: `state_path` devuelve la ruta correcta.
- [x] Tests: `estado_inicial()` no incluye `fase_actual` ni `paso_actual` como claves persistidas en
  `crispdm`/`kdd`.

## Dependencias
Las tareas de código (`lifecycle.py`, catálogos, funciones) deben completarse antes que los
tests. Ninguna tarea depende del Change 0 (ya cerrado, no relacionado con esto). El archivo
`openspec/lifecycle/state.json` real de este repo depende de que `lifecycle_init`/`escribir_estado`
estén implementados y testeados.

## Próximo paso exacto
<!-- obligatorio si estado: pausada_bloqueada -->

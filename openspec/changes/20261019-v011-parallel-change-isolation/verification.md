# Verificación — 20261019-v011-parallel-change-isolation

## Resumen
Change 4 de v0.11, parte 4B (aislamiento de Changes paralelos). `scope.evaluar_alcance` clasifica las rutas fuera del alcance propio contra los demás Changes: sin dueño → `ALCANCE-RUTA`; un único dueño → `ALCANCE-ATRIBUIDA-OTRO-CHANGE` (informativo, no bloquea); doble dueño o propio+ajeno → `ALCANCE-CONFLICTO-CHANGES` (bloquea); ajeno activo con alcance no verificable → `ALCANCE-OTRO-CHANGE-INVALIDO` (bloquea). Los consumidores que deciden bloqueo (`cmd_validate`, `sdd.transition`, `cmd_archive`) filtran con `scope.bloqueantes`.

Un Change ajeno solo cuenta si, sobre su snapshot en el commit baseline del Change propio (SHA completo), tiene estado activo (`aprobada_implementacion`/`en_implementacion`/`en_verificacion`), la aprobación de todos los artefactos de `artefactos_requeridos(modo)` y un `scope_hash` que no cambió en disco; los patrones catch-all, inválidos o bajo `.claude/` se descartan. La atribución es «honesta, no autenticada»: eleva el costo de la evasión, no la hace imposible, y nunca amplía el alcance propio.

## 4A — Runtime attribution
No apareció evidencia real de payload de hook en este release. **H1 permanece UNCONFIRMED**; el hook no se tocó. No se invirtió más tiempo en buscarla.

## Incidentes y desviaciones (registro fiel)
1. **Modificación inicialmente fuera de scope.** `tools/dsguard/core.py` (helper `hash_lf_v1_bytes`) y `tools/dsguard/repo.py` (`existe_en_commit`, `leer_en_commit`) fueron modificados por el writer durante el fix del reviewer, antes de estar en el alcance autorizado del Change.
2. **Detección.** `ds_guard validate` los reportó como `ALCANCE-RUTA` para ambos archivos.
3. **Regularización.** Se regularizó mediante `scope amend` (enmienda #1, revisión de scope 1) con confirmación T1 real, `approval_channel=console_confirmed`, dada por el autor; scope_hash efectivo `4ce0f239d5569951acf0c7359d31bd63576e8b99e66052199ed7fd9209ad5c5d`. No se ocultó la desviación ni se rebaselineó. Ownership del writer actualizado en `tasks.md` (Historial) después de la enmienda.
4. **Ciclos de reviewer excedidos.** El contrato de v0.11 permite máximo 2 por Change; hubo 3 revisiones separadas (ciclo 1, ciclo 2 y ciclo 3, cada una con un agente nuevo, no como continuación de una interrumpida). Se decidió no lanzar un cuarto ciclo. Hallazgos: ciclo 1 → 1 ALTO (ajeno fabricado/no aprobado/catch-all absorbe rutas), 3 MEDIOS; ciclo 2 → 1 ALTO residual (aprobación autodeclarada), 2 MEDIOS; ciclo 3 → 1 ALTO acotado (baseline probaba existencia, no aprobación), 1 MEDIO (solo `proposal.md`). Todos se corrigieron en código, tests y docs; el último fix (estado y aprobación sobre el snapshot del baseline, ancla `scope_hash` inmutable, todos los artefactos requeridos) no pasó por revisión posterior. Es la mayor limitación de este Change.
5. **Edición del Lead.** Los docstrings pendientes de `scope.py` y la expectativa de un test los editó el Lead directamente (cambios de texto, sin lógica).
6. Spec y design se editaron tras su aprobación; se re-registró la aprobación por hash con la autorización T0 anticipada de v0.11 (sin T1 nuevo).

## Evidencia obtenida
Última corrida (P=1, tras los docstrings y el ownership): `test_parallel_change_isolation` 44 OK, `test_scope` 35 OK, `test_architecture_boundaries` 16 OK, `test_skill_methodology` 52 OK, `test_manifest_dsguard_parity` 11 OK (158 en total).
Corrida previa, tras el fix del ciclo 3 (antes del ajuste del único test fallido, ya corregido y re-ejecutado): `test_scope_amendments` 101 OK, `test_operational_scope` 32 OK, `test_git_failclosed` 42 OK (1 skipped, preexistente), `test_git_failclosed_cli` 10 OK, `test_git_paths_unicode_consumers` 17 OK, `test_session_recovery` 28 OK.
El único fallo observado (`test_ajeno_aprobado_despues_del_baseline_no_atribuye`) era una expectativa de test equivocada (los artefactos de B modificados tras el baseline también quedan como `ALCANCE-RUTA`); el código era correcto.
`validate` del Change: «Sin hallazgos» tras la enmienda.

## Diferencias contra la spec
R1/R4 reescritos durante la revisión (anclaje al baseline). R7 se cumple vía `scope.bloqueantes`; la cobertura de `transition`/`archive` es a nivel función (`sdd._findings_del_gate` + `bloqueantes`), no por CLI completa.

## Limitaciones
- Un ajeno aprobado después del baseline del Change propio no atribuye (fail-closed).
- La aprobación vive en `control.json`, editable por quien tiene el repo («honesta, no autenticada»).
- Patrones ajenos amplios pero no catch-all (p. ej. `tools/**`) pueden atribuir rutas del propio harness; no se restringió.
- La regresión completa se difiere al Change 6.

## Pendientes derivados
Change 5, Change 6 y release. Posible endurecimiento futuro: autenticar la aprobación ajena; restringir prefijos amplios.

## Resultado final
Change 4 (4B) verificado con tests dirigidos y sin hallazgos abiertos conocidos; desviaciones de alcance y de ciclos de reviewer documentadas arriba. 4A: H1 UNCONFIRMED, hook sin cambios.

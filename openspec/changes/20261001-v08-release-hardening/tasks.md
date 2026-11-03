# Tareas — 20261001-v08-release-hardening

estado: cerrada

**Fase 1 (este documento, SDD): T0 ya hecha (audit de lectura). T1 es la propia redacción de
`proposal.md`/`spec.md`/`design.md`, ya entregada para aprobación — ninguna tarea de ejecución
real empieza antes de la aprobación humana por hash.**

**Fase 2 (tras aprobación): T2-T11, en el orden de dependencia indicado.**

## T0 — Audit (hecho, Lead, solo lectura)

- [x] Confirmar que `tools/ds_init/tests/test_integracion_instalacion.py` no ejercita ningún flujo
  de trabajo del Lead sobre el proyecto instalado (solo la instalación en sí).
- [x] Confirmar que ningún test existente combina más de una capacidad de M7-M12/B5 en un mismo
  escenario end-to-end.
- [x] Confirmar que `docs/roadmap/v0.8.md` (Casos A-I) y la adenda 2026-10-01 (Caso I/domain
  context) ya fijan el QUÉ; este SDD traduce eso a un plan concreto (spec.md R0-R54).
- [x] Confirmar que `Change 4`'s 24 tests de `dependency install` y los de budgets/checkpoints de
  Change 3 ya cubren G/H a nivel unitario/CLI — sin necesidad de reimplementarlos.

## T1 — SDD (esta entrega)

- [x] `proposal.md`: problema, objetivo, evidencia de auditoría, alcance (solo SDD en esta
  entrega), fuera de alcance.
- [x] `spec.md`: R0 + R1-R54 organizados por Casos A-K, cada uno con su tipo de verificación.
- [x] `design.md`: D1-D5, clasificación de verificación por caso, 3 fixtures combinados reusables.
- [x] D5 RESUELTA por decisión explícita del autor (2026-10-01): instalación real local de
  dependencia, SÍ -- los 13 puntos exigidos ya están en `spec.md` R28-R40.

## T2 — Fixture 1 ("autonomía combinada": Casos A, B, C parcial, E, J)

- Proyecto scratch nuevo: `autonomous` + `approval_mode: checkpoints` + `predictive_modeling=false`
  + fuente externa file-backed read-only declarada + project config + local override +
  `GLOSSARY.md` sintético en la raíz (no administrado).
- Objetivo aprobado con checkpoints de negocio declarados (R1).
- Demostración en vivo conducida por el Lead: escribir → ejecutar → testear → remediar si aplica →
  reportar/evidence → cerrar, auditando `control["sesiones"]`/`ExecutionRecord`s después (R2-R4,
  D4).
- Verificar en el mismo fixture: B (R5-R7), C parcial (R8, lectura de la fuente externa), E (R16-
  R19, ambas capas de config), J (R47-R49, `GLOSSARY.md` sin drift).

## T3 — Fixture 1, continuación: integridad (Caso C completo, R9-R12)

- Sobre el mismo fixture de T2 (o una variante puntual): un script ejecutado por el runtime
  modifica la fuente externa por su cuenta → fingerprint pre/post real, `data_loss_risk` real,
  mensaje sin afirmar causalidad, diagnóstico OS real (incluido `unknown/partial` si el entorno no
  permite determinarlo).
- Confirmar `Write`/`Edit`/`NotebookEdit` reales bloqueados por `pathguard` sobre la ruta externa
  declarada; documentar honestamente el alcance best-effort de `move`/`delete` vía Bash (R9).

## T4 — Fixture 3 ("source-neutral": Caso D, R14-R15)

- Adapter mínimo `sqlite3` (stdlib) escrito en el fixture del proyecto, registrado en
  `.harmessi/sources.json`; `ds_guard source observe` real.
- Adapter `module:callable` custom adicional, mismo registro; `harmessi doctor` 0 `ERROR`.

## T5 — Fixture 2 ("adopción + dependencia": Casos F, G, R20-R40)

- Reusar/extender `TestAdopcionProyectoExistente` (Change 4, `tools/ds_init/tests/test_cli.py`) con
  un paso nuevo: `ds_guard exec script` real sobre un script preexistente del usuario (R22).
- Regresión dirigida de los 24 tests de `dependency install` (Change 4), sin editarlos.
- **Escenario nuevo de instalación real local (R28-R40, D5 resuelta)**: wheel mínimo vía `zipfile`
  + stdlib; `PIP_NO_INDEX`/`PIP_FIND_LINKS` como entorno temporal del proceso, nunca como flag del
  `argv` gobernado; los 13 puntos exigidos, cada uno un test explícito; cláusula de escape (R40) si
  el entorno real de pip no permite demostrarlo sin tocar el contrato de M11.

## T6 — Regresión dirigida de budgets/checkpoints (Caso H, R41-R44)

- Re-ejecutar `TestAggregateMinutesLimitEfectivo` + suites de checkpoints de Change 3 + el test de
  inmutabilidad de `STOP_CATALOG` — sin escenario nuevo salvo que la regresión encuentre algo.

## T7 — Métricas de eficiencia (Caso I, R45-R46)

- `ds_guard session efficiency` real sobre la sesión del Fixture 1 (T2) — reuso, no una corrida
  dedicada.

## T8 — Backward compatibility y regresión completa (Caso K, R50-R54)

- Instalación fresca sin ninguna opción nueva (discovery y experiment); upgrade desde un proyecto
  v0.7 fixture; `check_manifest_parity`; `git diff --check`; privacy sweep; portability; Doctor.
- Regresión completa final de todo `tools/` (lotes secuenciales o auto-conversión a background si
  hace falta, mismo patrón ya aceptado).

## T9 — `verification.md` y veredicto final

- Evidencia por caso A-K, citando cada test/demostración real (nunca de memoria).
- Veredicto: `READY FOR v0.8.0 RELEASE` o `NOT READY FOR v0.8.0 RELEASE`.

## T10 — Revisión (`data-science-reviewer`, solo lectura)

- Máximo 2 ciclos writer↔reviewer, mismo patrón ya usado en Changes 3-4.

## T11 — Cierre

- `ds_guard validate --gate cierre`; transición a `cerrada`; commit local.
- **Sin push, sin tag, sin release** — el veredicto `READY FOR v0.8.0 RELEASE` es documentación, no
  una acción de publicación; cualquier paso de publicación real queda para una autorización
  explícita y separada del autor.

## Dependencias

T2 antes que T3 (mismo fixture). T4/T5/T6 pueden correr en cualquier orden entre sí (fixtures/
regresiones independientes). T7 depende de que T2 ya haya corrido (reusa su sesión). T8-T9
dependen de que T2-T7 ya terminaron. T10 depende de T2-T9. T11 depende de T10.

# Tareas — 20261026-v015-provider-reality

estado: cerrada

## Invocaciones planificadas
- python-data-engineer (writer, una instancia) — T1..T8 tras la aprobación de proposal.md — produce docs, tests y cambios mínimos de código en el alcance autorizado. No ejecuta nada.
- data-science-reviewer / reviewer (uno) — tras T8 — revisa honestidad de la matriz (sin soporte superior a la evidencia), tests de fallback y alcance.
- Lead — T9 — corre la suite completa y el conformance, y registra la evidencia.

## Ownership de writers
<!-- Una sola instancia writer: no hace falta declarar ownership en paralelo. -->

## Historial de ownership
<!-- fecha — instancia — ruta — motivo (cambios de ownership hechos ANTES de que el writer edite) -->

## Skills cargados
<!-- ninguno hasta ahora -->

## Tareas
- [x] T1. Crear `docs/providers.md`: matriz provider × {detected, contract-tested, smoke-tested, live-validated, limitaciones}; registro de evidencia live del 2026-10-26 (host único); nota de no-adapter `antigravity`; límites heurísticos de conformance (B-09); sección de fallback y routing; promesa de provider-neutrality y T2 POST-v1 con razón (R1, R2, R7, R9).
- [x] T2. `tools/providers/conformance.py`: `claude_code` → `live-validated` en `SOPORTE_DECLARADO` con evidencia remitiendo al registro; actualizar el comentario L99-102; mantener los 3 restantes en `contract-tested` (R3, R4).
- [x] T3. `tools/providers/conformance.py` + `tools/providers/tests/test_conformance.py`: corregir el falso positivo de `--model=x` y agregar los tests positivo (`--model=modelo-sintetico` sin advertencia) y negativo (modelo sin flag falla) (R6).
- [x] T4. `tools/tests/test_v015_provider_matrix.py`: coincidencia doc ↔ `SOPORTE_DECLARADO`, registro de evidencia obligatorio para niveles ≥ smoke/live, test negativo de sobreventa (R1, R3, R4).
- [x] T5. Tests B-10 en `tools/fallback/tests/test_core.py` y `tools/fallback/tests/test_cross_provider_parity.py`: `ok=False` + `availability_error=None` no dispara fallback; quota/unavailable/unauthenticated sí (R5). Test en `tools/routing/tests/test_core.py`: `provider_available` informativo (R9). Si aparece un desvío en `core.py` de fallback, devolver al Lead.
- [x] T6. `tools/providers/claude_code.py`: corregir solo el docstring (versión validada `2.1.310`, host único). Sin otros cambios (R8).
- [x] T7. Documentación: README (fallback solo quota/availability, `provider_available` informativo, enlace a `docs/providers.md`), ARCHITECTURE.md (providers/fallback), `docs/contracts/inventory.json` (notas `provider-adapter` y, si cabe, `cli-providers-conformance`), `docs/roadmap/v0.15.md` y `docs/roadmap/v0.15-debt-matrix.md` (B-07..B-10 con referencia a la evidencia; B-09 parcial) (R9, R10, R11).
- [x] T8. Ajustar `tools/tests/test_v014_release_hardening_smoke.py` y `tools/tests/test_v013_release_hardening_smoke.py` y `tools/providers/tests/test_core.py` solo si afirman la tabla declarada anterior; si no dependen de ella, no tocarlos.
- [x] T9. (Lead) Ejecutar suite completa, `python -m tools.providers.conformance --json` y la validación del inventario; confirmar R1..R11 y reportar al reviewer.

## Dependencias
- T1 antes de T2 y T4: la doc es la fuente del registro de evidencia que T2 declara y T4 verifica.
- T2 antes de T4 (el test compara contra `SOPORTE_DECLARADO` ya actualizado).
- T3 es independiente; T5 y T6 son independientes entre sí y de T1..T4.
- T7 después de T1 y T5 (referencia a doc y tests); T8 después de T2.
- T9 después de T1..T8. El reviewer revisa después de T8, antes del cierre.
- Todo requiere la aprobación humana de proposal.md (alcance materializado por ds_guard).

## Próximo paso exacto
<!-- obligatorio si estado: pausada_bloqueada -->

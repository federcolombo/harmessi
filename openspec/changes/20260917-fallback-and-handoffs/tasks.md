# Tareas — 20260917-fallback-and-handoffs

estado: cerrada

## Invocaciones planificadas
1. `python-data-engineer` (esta sesión) -- completa los 4 artefactos SDD y declara el alcance real
   en `control.json` desde el arranque; implementa `tools/fallback/` completo, la extensión
   aditiva de `tools/routing/{core.py,policy.py,examples/policy.example.json,tests/*}` (Change 2),
   el wiring en `tools/harmessi/cli.py` (`fallback resolve-chain`/`fallback invoke`) y su test, y
   actualiza `ARCHITECTURE.md` §2.1.
2. Lead -- corre la suite nueva de `tools/fallback/tests`, la regresión completa de
   `tools/routing/tests` (confirma 0 regresiones de la extensión aditiva sobre los 11 tests
   preexistentes de Change 2), la regresión de `tools/harmessi/tests`, y UN smoke real de fallback
   genuino fuera de la suite automatizada: cadena `[codex, claude_code]` vía
   `harmessi fallback invoke`, donde `codex` falla limpio por no estar instalado
   (`availability_error="unavailable"`) y `claude_code` responde de verdad -- evidencia real de
   handoff automático por disponibilidad, sin fabricar nada.
3. `data-science-reviewer` -- revisa el diff completo del Change, con foco especial en que ningún
   camino de código permita fallback por una razón no elegible (error semántico/de código,
   hallazgo de reviewer, test fallido, mala calidad de output).
4. `python-data-engineer` -- aplica fixes si hay hallazgos de la revisión y escribe
   `verification.md` con los resultados reales de la corrida del Lead.
5. `python-data-engineer` (esta sesión) -- cierre: `verification.md` escrito con las 6 secciones
   requeridas por el gate de `ds_guard`; ver
   `openspec/changes/20260917-fallback-and-handoffs/verification.md`.

## Tareas
- [x] `control.json`: declarar las 15 rutas de implementación (además de las 5 rutas SDD) en
  `alcance.rutas_autorizadas` desde el arranque de la sesión.
- [x] `proposal.md`, `spec.md`, `design.md`, `tasks.md` completos, sin placeholders.
- [x] `tools/routing/core.py`: campo `fallback_chain` aditivo en `RoutingRule` y
  `RoutingDecision`; poblado en `resolve()`.
- [x] `tools/routing/tests/test_core.py`: 2 tests nuevos para `fallback_chain`.
- [x] `tools/routing/policy.py`: parseo + validación fail-closed de `fallback_chain`.
- [x] `tools/routing/tests/test_policy.py`: 2 tests nuevos (carga válida + `ValueError`).
- [x] `tools/routing/examples/policy.example.json`: `fallback_chain` en la regla `writer`, nota
  actualizada.
- [x] `tools/fallback/__init__.py`, `tools/fallback/core.py` (`is_fallback_eligible`,
  `HandoffRecord`, `FallbackOutcome`, `invoke_with_fallback`).
- [x] `tools/fallback/handoff.py` (`HandoffContext`, `build_handoff_context`, `save_handoff`,
  `load_handoff`).
- [x] `tools/fallback/tests/__init__.py`, `tools/fallback/tests/test_core.py`,
  `tools/fallback/tests/test_handoff.py`.
- [x] `tools/harmessi/cli.py`: subcomando `fallback` (`resolve-chain`, `invoke`).
- [x] `tools/harmessi/tests/test_fallback_cli.py`.
- [x] `ARCHITECTURE.md` §2.1: 2 filas nuevas (una por módulo de `tools/fallback/`).
- [x] `verification.md`: pendiente de la corrida real del Lead (tarea 4 de esta lista).

## Dependencias
- Extiende `tools/routing/core.py`, `tools/routing/policy.py`,
  `tools/routing/examples/policy.example.json` y sus tests (Change 2, `provider-routing`, ya
  cerrado) de forma aditiva -- no depende de reabrir ese Change.
- Reusa `tools/providers/core.py` (`ProviderAdapter`, `InvocationRequest`, `InvocationResult`,
  `classify_availability_error`) y `tools/providers/__init__.py::PROVIDER_REGISTRY` (Change 0,
  `multi-provider-adapters`, ya cerrado) sin modificarlos.

## Próximo paso exacto
No aplica (estado no es `pausada_bloqueada`). Próximo paso real: invocación 2 (Lead corre la
suite + smoke real) según "Invocaciones planificadas" arriba.

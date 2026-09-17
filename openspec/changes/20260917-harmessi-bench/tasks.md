# Tareas — 20260917-harmessi-bench

estado: cerrada

## Invocaciones planificadas
1. `python-data-engineer` (esta sesión) — completa los 4 artefactos SDD e implementa código +
   tests completos de `tools/harmessi_bench/`.
2. Lead — corre la suite de tests nueva + regresión de `tools/tests` (para confirmar que nada de
   `dsguard` se rompió, aunque este Change no lo toca) + UNA corrida real mínima contra
   `claude_code` con el `examples.json` bundleado; la evidencia va a `verification.md`.
3. `data-science-reviewer` — revisa el diff completo (el Lead corre `git diff` y se lo pasa).
4. `python-data-engineer` — aplica fixes si hay hallazgos del reviewer (cuenta como reintento
   correctivo solo si los hay) y escribe `verification.md` con la evidencia que el Lead le pasa,
   dejando `estado: en_verificacion` antes del cierre.

## Tareas
- [x] Crear `tools/harmessi_bench/core.py`.
- [x] Crear `tools/harmessi_bench/scenarios.py` y `tools/harmessi_bench/scenarios/examples.json`.
- [x] Crear `tools/harmessi_bench/runner.py`.
- [x] Crear `tools/harmessi_bench/storage.py`.
- [x] Crear `tools/harmessi_bench/compare.py`.
- [x] Crear `tools/harmessi_bench/cli.py`.
- [x] Crear `tools/harmessi_bench/__init__.py`.
- [x] Crear los 6 archivos de test (`tools/harmessi_bench/tests/test_core.py`, `test_scenarios.py`,
      `test_runner.py`, `test_storage.py`, `test_compare.py`, `test_cli.py`) y
      `tools/harmessi_bench/tests/__init__.py`.
- [x] Actualizar `ARCHITECTURE.md` §2.1.

## Dependencias
Reusa `tools/providers/core.py` de Change 0 (ya commiteado), no lo modifica. No depende de ningún
otro Change de v0.5 pendiente.

## Próximo paso exacto
No aplica (estado no es `pausada_bloqueada`). Próximo paso operativo: el Lead corre la suite de
tests + regresión + smoke real (invocación 2 de "Invocaciones planificadas").

# Propuesta — 20261023-v014-probe-execution

## Problema
Una candidate no se puede comparar contra el baseline en condiciones iguales con evidencia reproducible y acotada.

## Objetivo
Probe: ejecutar baseline y candidate sobre la misma suite, target, evaluator y seed, reutilizando el runner, el run manifest y `save_run` de v0.13, con política de criterios congelada y budget.

## Evidencia
`tools/harmessi_bench/runner.py` (`run_scenario_set`), `runmanifest.py` (`construir_manifest`, `calcular_identity_hash`, `evaluar_compatibilidad`), `storage.py` (`save_run`), `suite.py` (`load_suite_y_casos`), `compare.py`; `docs/roadmap/v0.14.md` D4–D6.

## Supuestos descartados
- Un runtime de evals nuevo: se reusa `run_scenario_set`; la variante se inyecta como guía en el prompt con un wrapper de adapter.
- Escribir la candidate en el archivo activo para probar: el manifest del lado candidate se deriva sustituyendo el hash de la superficie.

## Alcance
`tools/harmessi_improve/{policy,probe}.py`, función pública de sustitución en `harmessi_bench/runmanifest.py`, tests, ARCHITECTURE.md.

## Fuera de alcance
Veredicto/decisión (Change 3), promoción, lessons, CLI.

## Aprobación
- Usuario: Federico Colombo
- Fecha: 2026-10-23
- Alcance aprobado: Harmessi v0.14 Change 2
- Versión de artefactos referenciada: ver control.json

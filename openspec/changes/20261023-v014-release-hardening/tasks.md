# Tareas — 20261023-v014-release-hardening

estado: cerrada

## Invocaciones planificadas
<!-- rol, momento del ciclo, y qué produce cada una -->

## Ownership de writers
<!-- solo si se lanzan 2+ instancias writer en paralelo; declarar ANTES de lanzar.
### W1 — python-data-engineer — T1
- ruta/archivo.py
- directorio/**
-->

## Historial de ownership
<!-- fecha — instancia — ruta — motivo (cambios de ownership hechos ANTES de que el writer edite) -->

## Skills cargados
<!-- - <skill> — <tarea> — <motivo>  (solo si la skill cambió una decisión, un criterio de aceptación, la delegación —incluido el puntero a la skill en el campo 2—, el scope/ownership o el diseño; si sin ella el resultado habría sido otro. Una lectura exploratoria sin efecto, o una skill que perdió un conflicto sin influir, no lleva bullet. Un bullet por skill; si hubo conflicto, el criterio va en el motivo del bullet de la que ganó) -->

## Tareas
- [x]

## Dependencias

## Próximo paso exacto
Pausa 2026-10-23 (retomar el lunes siguiente). Hecho: marcadores 0.14.0, notas, inventario, smoke, dogfood A-I (25 OK), baseline regenerado (131 entradas, 0 drift), reviewer 1 ciclo corregido, regresión 105/256 módulos OK sin fallos (ledger en memoria: v014-regression-ledger.json).
Falta: (1) reanudar regresión con v014-runq.py invalidando antes en el ledger los módulos afectados por fixes posteriores (harmessi_improve/tests/test_cli, test_v014_*, test_v013_contract_inventory, test_v013_ci_workflow, test_v013_release_hardening_smoke, test_v014_*); (2) install limpio y upgrade desde tag v0.13.0 + idempotencia; (3) Doctor 0 ERROR; (4) verification.md del Change 6; (5) close, fetch origin, ff main, tag anotado v0.14.0, push main+tag (no v0.14-dev), gh si existe.

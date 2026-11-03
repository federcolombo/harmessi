# Tareas — 20261021-v013-eval-benchmark-foundation

estado: cerrada

## Invocaciones planificadas
- python-data-engineer (writer único): implementa R1–R20. El Lead corre los tests focalizados (el writer no ejecuta).
- data-science-reviewer: 1 ciclo sobre el diff.
- Verificación: tests de `tools/harmessi_bench`, `test_v05_core_neutrality`, `test_architecture_boundaries`, `test_manifest_completitud`, smoke del Change. Sin regresión completa.

## Ownership de writers
Una sola instancia writer: todo el alcance autorizado.

## Historial de ownership

## Skills cargados
<!-- ninguna skill cambió una decisión de este Change -->

## Tareas
- [x] T0 — Aprobación del SDD por hash (autorización anticipada, 2026-10-21).
- [x] T1 — Implementación (core/scenarios/suite/storage/compare/cli/suites).
- [x] T2 — Tests focalizados y smoke.
- [x] T3 — Docs (ARCHITECTURE, README, roadmap).
- [x] T4 — Review (1 ciclo) y fixes.
- [x] T5 — `verification.md`, cierre y commit local.

## Dependencias
T1 → T2 → T3 → T4 → T5.

## Próximo paso exacto
Aprobar y delegar T1–T3 al writer.

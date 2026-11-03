# Tareas — 20261021-v013-reproducible-harness-runs

estado: cerrada

## Invocaciones planificadas
- python-data-engineer (writer único): implementa R1–R15. El Lead corre los tests focalizados.
- data-science-reviewer: 1 ciclo.
- Verificación: tests de `tools/harmessi_bench`, neutralidad, smoke del Change, manifest-completitud. Sin regresión completa.

## Ownership de writers
Una sola instancia writer: todo el alcance autorizado.

## Historial de ownership

## Skills cargados
<!-- ninguna skill cambió una decisión de este Change -->

## Tareas
- [x] T0 — Aprobación del SDD por hash.
- [x] T1 — Implementación (runmanifest, redact, storage, compare, cli).
- [x] T2 — Tests y smoke.
- [x] T3 — Docs.
- [x] T4 — Review (1 ciclo) y fixes.
- [x] T5 — `verification.md`, cierre y commit local.

## Dependencias
T1 → T2 → T3 → T4 → T5.

## Próximo paso exacto
Aprobar y delegar al writer.

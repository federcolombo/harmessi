# Tareas — 20261021-v013-release-hardening

estado: cerrada

## Invocaciones planificadas
- python-data-engineer (writer único): marcadores de versión, notas, smoke de release, docs de roadmap. El Lead ejecuta regresión, baseline, install/upgrade, Doctor y dogfood.
- data-science-reviewer: 1 ciclo sobre notas, smoke y evidencia.

## Ownership de writers
Una sola instancia writer: todo el alcance autorizado.

## Historial de ownership

## Skills cargados
<!-- ninguna skill cambió una decisión de este Change -->

## Tareas
- [x] T0 — Aprobación del SDD por hash.
- [x] T1 — Versión, notas, smoke y docs.
- [x] T2 — Baseline managed (una vez).
- [x] T3 — Regresión completa serial.
- [x] T4 — Fresh install, upgrade, Doctor, privacidad.
- [x] T5 — Dogfood (evaluación, provider/adapter, portabilidad).
- [x] T6 — Review (1 ciclo) y fixes.
- [x] T7 — `verification.md`, cierre y commit de release.

## Dependencias
T1 → T2 → T3 → T4/T5 → T6 → T7.

## Próximo paso exacto
Aprobar y delegar T1 al writer.

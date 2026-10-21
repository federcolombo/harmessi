# Tareas — 20261021-v013-release-hardening

estado: en_implementacion

## Invocaciones planificadas
- python-data-engineer (writer único): marcadores de versión, notas, smoke de release, docs de roadmap. El Lead ejecuta regresión, baseline, install/upgrade, Doctor y dogfood.
- data-science-reviewer: 1 ciclo sobre notas, smoke y evidencia.

## Ownership de writers
Una sola instancia writer: todo el alcance autorizado.

## Historial de ownership

## Skills cargados
<!-- ninguna skill cambió una decisión de este Change -->

## Tareas
- [ ] T0 — Aprobación del SDD por hash.
- [ ] T1 — Versión, notas, smoke y docs.
- [ ] T2 — Baseline managed (una vez).
- [ ] T3 — Regresión completa serial.
- [ ] T4 — Fresh install, upgrade, Doctor, privacidad.
- [ ] T5 — Dogfood (evaluación, provider/adapter, portabilidad).
- [ ] T6 — Review (1 ciclo) y fixes.
- [ ] T7 — `verification.md`, cierre y commit de release.

## Dependencias
T1 → T2 → T3 → T4/T5 → T6 → T7.

## Próximo paso exacto
Aprobar y delegar T1 al writer.

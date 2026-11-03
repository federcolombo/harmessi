# Tareas — 20261021-v012-release-hardening

estado: cerrada

## Invocaciones planificadas
- Lead: regresión, install/upgrade, dogfood, baseline, git, publicación. Writer único `python-data-engineer` (versión, notas, smoke). Reviewer: 1 ciclo sobre notas+smoke+correctivos.

## Tareas
- [x] T0 — Aprobación SDD.
- [x] T1 — Versión, notas, smoke, roadmaps (writer).
- [x] T2 — Regresión completa por batches y correctivos.
- [x] T3 — Baseline managed y Doctor.
- [x] T4 — Fresh install, upgrade v0.11→v0.12, dogfooding A–E.
- [x] T5 — Privacidad, reviewer, verification, cierre y commit.
- [x] T6 — Publicación (main, tag, push, release).

## Dependencias
T1←T0; T2←T1; T3←T2; T4←T3; T5←T4; T6←T5.

## Próximo paso exacto
Delegar T1.

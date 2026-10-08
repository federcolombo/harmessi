# Tareas — 20261008-v010-roadmap-and-architecture-audit

estado: cerrada

## Invocaciones planificadas
- Lead: explora y audita (lectura de código y medición), coordina y hace la revisión de consistencia; sin editar archivos.
- Instancias de `python-data-engineer` con ownership DISJUNTO de archivos (declarado acá antes de lanzar), en paralelo:
  - Writer A: `proposal.md` + `tasks.md` de este Change.
  - Writer B: `spec.md` + `design.md` de este Change.
  - Writer C: `docs/roadmap/v0.10.md` + `docs/roadmap/README.md` + `ARCHITECTURE.md` (§7).
- Reviewer separado de Change 0: NO se lanza; la revisión de consistencia la hizo el Lead.
- Verificación (sin regresión completa): `tools/tests/test_v09_release_hardening_smoke.py` (smoke de roadmap existente),
  `tools/tests/test_architecture_boundaries.py`, `ds_guard validate`, chequeo de privacidad y `git diff --check`.

## Tareas
- [x] T0 — Aprobación del SDD por hash (humana, hecha por el humano en esta sesión, 2026-10-08) y decisiones M1–M5 aprobadas.
- [x] T1 — Incorporar M1–M5 aprobadas en proposal/spec/design, roadmap v0.10 (pasa a «aprobado»), README de roadmap y `ARCHITECTURE.md` §7.
- [x] T2 — Verificación: smoke de roadmap, architecture boundaries, `ds_guard validate`, privacidad, `git diff --check` (sin regresión completa).
- [x] T3 — `verification.md`, cierre del Change y commit local.

## Dependencias
Ninguna de implementación. T1 depende de T0. T2 depende de T1. T3 depende de T2.

## Próximo paso exacto
Completar T1–T3 y cerrar Change 0. Siguiente: Change 1 (Cross-platform Managed Hashing); NO abrirlo todavía.

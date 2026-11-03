# Tareas — 20261015-v010-release-hardening

estado: cerrada

## Invocaciones planificadas
- Lead: audita, valida, git, regresión; NO escribe implementación. Writers `python-data-engineer` con ownership disjunto. Reviewer `data-science-reviewer`: máx. 2 ciclos (previsto 1: notas, smoke, coherencia de versión). Regresión completa UNA vez sobre el candidato final.

## Ownership de writers
### W1 — python-data-engineer — T1
- tools/ds_init/version.py
- CITATION.cff
- README.md
- docs/releases/v0.10.0.md
- docs/roadmap/v0.10.md
- docs/roadmap/README.md
- tools/tests/test_v09_release_hardening_smoke.py

### W2 — python-data-engineer — T2
- tools/tests/test_v010_release_hardening_smoke.py

## Historial de ownership
<!-- fecha — instancia — ruta — motivo -->
- 2026-10-15 — W3 (instancia `c6-fix-manifest`) — tools/ds_init/manifest.py — corrección del manifest (3 módulos dsguard faltantes) hallada por la regresión completa; dentro del scope del Change (`tools/**`)
- 2026-10-15 — los fixes del reviewer los aplicaron las mismas instancias dueñas de cada archivo

## Skills cargados
<!-- ninguna skill componible afecta este Change -->

## Tareas
- [x] T0 — Aprobación del SDD (autorización anticipada del usuario).
- [x] T1 — Versión, notas, README, roadmap, smoke v0.9 (W1).
- [x] T2 — Smoke de release v0.10 (W2).
- [x] T3 — Reviewer (≤2 ciclos).
- [x] T4 — Baseline gestionado: verificar drift contra git, regenerar `.ds_init/control.json`, Doctor.
- [x] T5 — Regresión: smoke/sanidad, completa una vez, triage.
- [x] T6 — Verificación y cierre; commit local `Harden v0.10 release`.
- [ ] T7 — Publicación (fetch, ff main, tag, push, GitHub Release o pendiente).

## Dependencias
T2 depende de T1 (frases de las notas); T4 de T1–T3; T5 de T4; T6 de T5; T7 de T6.

## Verificación
- Detalle completo en `verification.md` de este Change.
- Regresión final: 5463 unittest (60 skipped) y 364 pytest, 0 fallos reales.
- Baseline: 127 entradas, `harness_version` 0.10.0, dry-run sin migrables ni drift.
- Reviewer: 1 ciclo, 0 bloqueantes, 3 importantes y 7 menores corregidos.
- Pendiente: T7 (publicación) por el Lead; `gh` no instalado.

## Próximo paso exacto
<!-- obligatorio si estado: pausada_bloqueada -->

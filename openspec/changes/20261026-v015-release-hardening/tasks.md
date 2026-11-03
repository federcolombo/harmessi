# Tareas — 20261026-v015-release-hardening

estado: cerrada

## Invocaciones planificadas
- python-data-engineer (writer, secuencial): versión, notas, smoke, matriz de readiness.
- Lead: baseline, regresión, install/upgrade, Doctor, privacidad, verification.md, merge/tag/push.
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
- [x] T1 Versión 0.15.0 (`version.py`, `CITATION.cff`), notas `docs/releases/v0.15.0.md`, README, smoke v015.
- [x] T2 Baseline regenerado una vez (Lead).
- [x] T3 Matriz de readiness v1 y estado del release en el roadmap.
- [x] T4 Regresión serial, install limpio, upgrade v0.14.0->v0.15.0, Doctor, privacidad (Lead) -> verification.md.
- [ ] T5 Merge a main, tag anotado, push (Lead).

## Dependencias

## Próximo paso exacto
<!-- obligatorio si estado: pausada_bloqueada -->

Cerrar el corrective 20261027-v015-scope-closure-corrective y reanudar C7 con T1-T5.

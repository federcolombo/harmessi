# Tareas — 20261019-v011-upgrade-migration-resilience

estado: en_implementacion

## Invocaciones planificadas
- Lead coordina/valida; writer único `python-data-engineer` (serial, varias invocaciones T1a–T1e); reviewer 1 ciclo (segundo solo si blocker/HIGH).

## Ownership de writers
<!-- solo si se lanzan 2+ instancias writer en paralelo; declarar ANTES de lanzar. -->

## Historial de ownership
<!-- fecha — instancia — ruta — motivo (cambios de ownership hechos ANTES de que el writer edite) -->

## Skills cargados
<!-- - <skill> — <tarea> — <motivo>  (solo si una skill componible afecta el Change) -->

## Tareas
- [x] T1a — R1 test de completitud del manifest + R5 escritura atómica de control.json y backup en migrate-hashes
- [x] T1b — R2/R3/R7 `upgrade` (plan, transacción con journal persistente, lock)
- [x] T1c — R4 `recover` + detección por fase
- [x] T1d — R6 Doctor
- [ ] T1e — R8/R9/R10 fixtures v0.10, E2E, inyección de fallos, byte-identidad, docs
- [ ] T2 — Reviewer (1 ciclo) y fixes
- [ ] T3 — verification, cierre, commit

## Dependencias

## Próximo paso exacto
<!-- obligatorio si estado: pausada_bloqueada -->

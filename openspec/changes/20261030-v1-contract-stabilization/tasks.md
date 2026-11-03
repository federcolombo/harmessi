# Tareas — 20261030-v1-contract-stabilization

estado: cerrada

## Invocaciones planificadas
<!-- rol, momento del ciclo, y qué produce cada una -->
- python-data-engineer (x3, s1): T1 generador + fixtures v0_15 + snapshot CLI; T2 tests stable; T3 inventory y docs.
- data-science-reviewer (s1): revisión parcial del diff; hallazgos H1-H2-M1..M5 y LOW en `docs/roadmap/v1-readiness.md`.
- python-data-engineer (s3, commit f287fb0): fixes H1, H2, M1.
- python-data-engineer (s4): fixes M2-M5 y LOW (redacción temporal "preparado para 1.0.0", snapshot v2 con `nargs`/posicionales,
  ds_guard por subproceso, fixtures normalizados, `commit_origen` en MANIFEST, helper único `cli_surface.py`).
  Pendiente del Lead: regenerar fixtures y correr tests (el writer no ejecuta).

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
- [x] T1 python-data-engineer: `generate_v015.py` + fixtures `v0_15/` + `cli_surface.json` (R4, R5). Código listo; los fixtures actuales son del formato anterior y deben regenerarse (snapshot_version 2, `commit_origen`, eval normalizado).
- [x] T2 python-data-engineer: tests `test_v1_stable_contracts.py` (R2, R3, R4, R5) y ajuste de `test_v013_contract_inventory.py` (R1, R7).
- [x] T3 python-data-engineer: `inventory.json` y docs (R1, R2, R6); `test_v015_compat_window.py` si hace falta.
- [ ] T4 Lead: correr tests acotados y docs/privacy.
- [ ] T5 data-science-reviewer: revisión del diff; T6 fixes; T7 verification.md y cierre.

## Dependencias

## Próximo paso exacto
<!-- obligatorio si estado: pausada_bloqueada -->

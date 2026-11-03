# Tareas — 20261027-v015-scope-closure-corrective

estado: cerrada

## Invocaciones planificadas
- (a) python-data-engineer: implementa T1..T6 (un solo writer, secuencial; ownership no requerido). Produce código, tests, docs/inventario/manifest; no ejecuta nada.
- (b) data-science-reviewer: revisa el diff (el Lead pasa `git diff`); produce hallazgos, no escribe.
- (c) python-data-engineer: corrección de hallazgos y deja `en_verificacion`; luego el Lead ejecuta tests, el dry-run real (T7) y cierra.

## Ownership de writers
<!-- No requerido: un solo writer secuencial. -->

## Historial de ownership
<!-- sin cambios -->

## Skills cargados
<!-- ninguno por ahora -->

## Tareas
- [x] T1. Ventana de cierre: sucesor más cercano por ascendencia git (helpers en `repo.py`), frontera en `archivos_tocados_desde_baseline`, fail-closed a comportamiento actual (`scope.py`, `repo.py`).
- [x] T2. Atestación protegida: `tools/dsguard/protected_attestation.py` (cadena, validación `console_confirmed`, planificar/aplicar atómico) e integración en `evaluar_alcance` (códigos ATESTADA/SIN-ATESTACION/HASH-DISTINTO; ATESTADA en `CODIGOS_INFORMATIVOS`).
- [x] T3. Comando `ds_guard scope attest-protected` (dry-run, T1 real con artefacto `protected-attestation`, sin canal `declared`) y alta del archivo en `pathguard.py` y `skill_contract.py`.
- [x] T4. T1 compacta en `cmd_scope_amend` / `_accion_scope`: acción `scope-amend: <op> +N -M hash=<12>` si excede 120; quitar rechazos; conservar replan y no-escritura si cambia el hash.
- [x] T5. Tests: `test_scope_closure_window.py` (casos 1, 2, 9, 10 parcial), `test_protected_attestation.py` (3, 4, 5, 6), `test_scope_amend_compact_t1.py` (7, 8, 9); ajustes en test_scope, test_scope_amendments, test_pathguard, test_skill_contract.
- [x] T6. Manifest, inventario y docs: `manifest.py` + `test_manifest.py`, `docs/contracts/inventory.json` + `test_v013_contract_inventory.py`, `ARCHITECTURE.md`, `docs/cli-reference.md`, `docs/security-and-trust.md`, `docs/roadmap/v0.15.md`, `docs/roadmap/v0.15-debt-matrix.md`.
- [x] T7. Verificación (Lead): suite afectada en verde y dry-run real del gate de cierre sobre C4/C5/C6 (C4 solo `.claude/settings.json`; C5 sin rutas; C6 las 6 de c6336b0). Después, acciones humanas fuera de este Change: atestación de C4 y UNA enmienda de scope de C6 (≤6 rutas exactas).

## Dependencias
- T2 depende de T1 (ventana) solo en la integración; T3 depende de T2; T5 depende de T1-T4; T6 de T1-T4; T7 de todas.
- Las acciones humanas posteriores (atestación C4, enmienda C6) requieren este Change cerrado y T1 real.

## Próximo paso exacto
<!-- obligatorio si estado: pausada_bloqueada -->
Aprobación humana de proposal.md/spec.md/design.md/tasks.md.

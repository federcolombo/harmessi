# Verificación — 20261027-v015-scope-closure-corrective

Números de las corridas del 2026-10-28 (Windows 11, Python 3.12, un host).

## Evidencia obtenida

## Tests
- Suite afectada sobre el WIP `00c6d0c` (test_scope_closure_window, test_protected_attestation, test_scope_amend_compact_t1, test_scope_amendments, test_pathguard, test_skill_contract, ds_init test_manifest): 386 ejecutados, 386 OK, 2 skipped.
- Tras los fixes de revisión (commit `7c5a2a8`; incluye test_scope): 310 ejecutados, OK, 2 skipped.

## Revisión
`data-science-reviewer`: 0 BLOCKER, 1 HIGH, 4 MEDIUM, 3 LOW. Corregidos: HIGH-1 (desempate por `change_id`), MEDIUM-1 (descartados no acotan), MEDIUM-2/4 (límites documentados), LOW-1, LOW-3. Omitidos: MEDIUM-3 (hash opaco en dry-run, conforme a R9) y LOW-2 (cubierto por el replan del CLI).

## T7 — Dry-run real del gate (`ds_guard validate`)
- C4 (runtime-observability): ventana acotada a `dc8bb19` (baseline de C5); solo bloqueaba `.claude/settings.json` (ALCANCE-PROTEGIDA-SIN-ATESTACION). Tras la atestación humana `console_confirmed` (hash `b91b7e5d8ef0`): ALCANCE-PROTEGIDA-ATESTADA.
- C5 (evidence-privacy-hardening): ventana acotada a `4b0c99a`; sin bloqueos.
- C6 (public-docs-evals): ventana acotada a `c6336b0`; 6 rutas ALCANCE-RUTA (control.json/tasks.md/verification.md de C4 y C5 escritos por c6336b0), pendientes de una enmienda T1.
- Sin globs amplios ni canal `declared` en `attest-protected` (cubierto por tests).

## Resultado final
T1–T7 completas. Gate de cierre verificado sobre C4/C5/C6 con el comportamiento esperado; pendientes humanos posteriores: enmienda T1 de scope de C6.

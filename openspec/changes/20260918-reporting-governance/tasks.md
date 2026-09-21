# Tareas — 20260918-reporting-governance

estado: cerrada

## Invocaciones planificadas
1. **Writer SDD** (esta y la anterior): completa `design.md`, `tasks.md` y el alcance de
   `control.json`; `proposal.md` y `spec.md` ya están escritos y son la fuente de verdad. Sin
   código.
2. **Writer implementación**: crea `governance.py`, `cli.py`, `__main__.py`, los dos archivos de
   tests, las tres entradas de manifest, las filas de `ARCHITECTURE.md` y las dos líneas de
   `MODULOS_CORE`. No ejecuta nada.
3. **Lead corre tests**: suite nueva (`tools/reporting/tests/`), `tools/tests/`,
   `tools/ds_init/tests/`, `test_manifest_dsguard_parity.py` y
   `python -m tools.ds_init.check_manifest_parity`; entrega los resultados al reviewer.
4. **data-science-reviewer**: revisión independiente (leakage, aislamiento exploratory ↔
   model_valid, holdouts, fail-closed, ausencia ≠ PASS, paridad con `pathguard`).
5. **Writer fixes**: corrige los hallazgos del reviewer y de los tests; el Lead re-corre.
6. **Writer cierre**: escribe `verification.md` (números de la corrida real, no de memoria) y
   tilda `[x] Change 1` en `docs/roadmap/v0.6.md`.

## Tareas
- [ ] `tools/reporting/governance.py`: `ReportingPolicy`, `ReportingPolicyError`, `load_policy`,
  `resolve_output_dir` (R3-R6)
- [ ] `governance.py`: `GovernanceContext` y `context_from_report` (R7)
- [ ] `governance.py`: checks `REPORT-POLICY`, `REPORT-DEST-SAFE`, `REPORT-DEST-SCOPE` /
  `REPORT-DEST-CROSS-SCOPE`, `REPORT-SENSITIVE-DEST` (R8-R11)
- [ ] `governance.py`: `REPORT-SOURCE-ACCESS`, `REPORT-HOLDOUT-ACCESS`, `REPORT-HOLDOUT-SOURCE`
  (R12-R14)
- [ ] `governance.py`: `check_flow_inputs` / `REPORT-ISOLATION-INPUT` (R15)
- [ ] `governance.py`: `REPORT-SCI-CUTOFF` (R16)
- [ ] `governance.py`: `evaluate_destination`, `evaluate_governance`, `output_allowed` (R17)
- [ ] `governance.py`: restricciones transversales R1 (imports permitidos, solo lectura, nunca
  lanza, determinista) y vocabulario R2 (solo `CheckResult`, ningún check devuelve lista vacía)
- [ ] `tools/reporting/cli.py` y `tools/reporting/__main__.py`: subcomandos `check-inputs` y
  `check-destination`, `--json`, exit codes 0/1/2/3 (R18)
- [ ] `tools/reporting/tests/test_governance.py` (R23; cobertura de R1-R17)
- [ ] `tools/reporting/tests/test_cli.py` (R23; cobertura de R18)
- [ ] `tools/ds_init/manifest.py`: tres entradas VERBATIM tras `tools/reporting/core.py`,
  `stage_minimo` `discovery` (R19)
- [ ] `tools/tests/test_architecture_boundaries.py`: `governance.py` y `cli.py` en `MODULOS_CORE`
  (R20)
- [ ] `ARCHITECTURE.md` §2.1: filas de `governance.py` y `cli.py` (R20)
- [ ] Verificar R21: `pathguard.py`, `scientific_validity.py`, `checks.py`, `repo.py`,
  `dsguard/core.py`, `ds_profile/*`, `.claude/guardrails.json`, `reporting/core.py` y
  `reporting/__init__.py` sin cambios (`git diff`)
- [ ] Lead: correr tests y `check_manifest_parity`
- [ ] data-science-reviewer: revisión independiente
- [ ] Aplicar fixes del reviewer y re-correr tests
- [ ] `openspec/changes/20260918-reporting-governance/verification.md` (al cierre)
- [ ] `docs/roadmap/v0.6.md`: tildar `[x] Change 1` (R22)

## Dependencias
- Change 0 (`20260918-reporting-core`): `tools/reporting/core.py` (`Report`, `REPORT_KINDS`,
  `DECISION_SCOPES`, nombres canónicos de archivos, `iter_tables`/`iter_figures`).
- `dsguard` (`checks`, `pathguard`, `repo`, `scientific_validity`, `core`) se reusa SIN
  modificarlo.
- Ningún holdout, dataset sellado, `data/raw` ni `.claude/guardrails.json` se lee o modifica.

## Próximo paso exacto
Invocación 2 (writer implementación): en estado `propuesta_pendiente` (no pausada), implementar
`tools/reporting/governance.py`, `cli.py`, `__main__.py`, los tests y los cambios aditivos listados
en Tareas, dentro de `alcance.rutas_autorizadas` de `control.json`, siguiendo `spec.md` R1-R23.

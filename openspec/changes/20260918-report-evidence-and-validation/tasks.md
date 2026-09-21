# Tareas — 20260918-report-evidence-and-validation

estado: cerrada

## Invocaciones planificadas
1. **Writer SDD** (esta): completa `proposal.md`, `spec.md`, `design.md`, `tasks.md` y el alcance
   de `control.json`. Sin código.
2. **Writer implementación, tanda A**: `tools/reporting/evidence.py` y
   `tools/reporting/tests/test_evidence.py` (R1-R11, R20, R23).
3. **Writer implementación, tanda B**: `tools/reporting/validation.py` y
   `tools/reporting/tests/test_validation.py` (R12-R17, R23).
4. **Writer implementación, tanda C**: `tools/reporting/cli.py` (`validate` y check aditivo),
   `tools/reporting/tests/test_cli_validate.py`, 2 entradas de `tools/ds_init/manifest.py`,
   aserciones de `test_installability.py`, filas de `ARCHITECTURE.md` §2.1 y `MODULOS_CORE` en
   `tools/tests/test_architecture_boundaries.py` (R18, R19, R21, R23). No ejecutan nada.
5. **Lead corre tests**: `tools/reporting/tests/`, `tools/tests/`, `tools/ds_init/tests/`,
   `test_manifest_dsguard_parity.py` y `python -m tools.ds_init.check_manifest_parity`; entrega
   resultados al reviewer.
6. **data-science-reviewer**: revisión independiente (leakage, ausencia ≠ PASS, evasión de
   hash-isolation, hash de bytes vs objeto, gaming de la puerta, límites honestos, fixtures sin
   datos reales).
7. **Writer fixes**: corrige los hallazgos del reviewer y de los tests; el Lead re-corre.
8. **Writer cierre**: escribe `verification.md` (números de la corrida real, no de memoria) y
   tilda `[x] Change 3` en `docs/roadmap/v0.6.md`.

## Tareas
- [ ] `evidence.py`: `EvidenceError`, `describe_source`, `describe_generated_source` (R3, R4)
- [ ] `evidence.py`: `prepare_artifacts`, `new_run_id`, `resolve_git_commit`,
  `resolve_harmessi_version` (R5, R6)
- [ ] `evidence.py`: `build_manifest` con esquema `schema_version: 1` (R7)
- [ ] `evidence.py`: `write_report_dir` (atómica, manifest último) y `load_report_dir` (R8, R9)
- [ ] `evidence.py`: `exploratory_hash_index` y `check_inputs_hash_isolation` (R10, R11)
- [ ] `tools/reporting/tests/test_evidence.py` (R20, R23)
- [ ] `validation.py`: `validate_report` figuras e insights, delegación EDA (R12-R14)
- [ ] `validation.py`: `validate_manifest` (R15)
- [ ] `validation.py`: `validate_report_dir` con política científica única (R16, R17)
- [ ] `tools/reporting/tests/test_validation.py` (R23)
- [ ] `cli.py`: subcomando `validate` y check aditivo en `check-inputs` (R18, R19)
- [ ] `tools/reporting/tests/test_cli_validate.py` (R23)
- [ ] `tools/ds_init/manifest.py`: 2 entradas VERBATIM tras `tools/reporting/profiles/eda.py`;
  aserciones en `test_installability.py` (R21)
- [ ] `ARCHITECTURE.md` §2.1 (filas evidence/validation, regla reporting → ds_profile solo
  `fingerprint`) y `MODULOS_CORE` (R21)
- [ ] Verificar R22: `core.py`, `governance.py`, `profiles/eda.py`, `__main__.py`, `__init__.py`
  sin cambios; `cli.py` solo aditivo (`git diff`)
- [ ] Lead: correr tests y `check_manifest_parity`
- [ ] data-science-reviewer: revisión independiente
- [ ] Aplicar fixes del reviewer y re-correr tests
- [ ] `openspec/changes/20260918-report-evidence-and-validation/verification.md` (al cierre)
- [ ] `docs/roadmap/v0.6.md`: tildar `[x] Change 3`

## Dependencias
- Change 0 (`20260918-reporting-core`): `Report`, `Chapter`, `Insight`, `TableArtifact`,
  `FigureArtifact`, `FigureSpec.columns_used`, `canonical_json`, `content_sha256`.
- Change 1 (`20260918-reporting-governance`): `GovernanceContext`, `evaluate_governance`,
  `check_flow_inputs`, `load_policy`, `REQUIRED_DESTINATION_CODES`.
- Change 2 (`20260918-eda-profile`): `profiles.eda.validate_eda_report`, `build_example_report()`
  de `examples/eda_generic.py`.
- `ds_profile.fingerprint` (solo `calcular_fingerprint`), `dsguard.repo`, `dsguard.core`,
  `dsguard.checks` y `scientific_validity.leer_policy`: se reusan SIN modificarlos.
- Ningún holdout, dataset sellado, `data/raw`, `.claude/guardrails.json` ni `.env*` se lee o
  modifica.

## Próximo paso exacto
Invocación 2 (writer implementación, tanda A): en estado `propuesta_pendiente` (no pausada),
implementar `tools/reporting/evidence.py` y `tools/reporting/tests/test_evidence.py` dentro de
`alcance.rutas_autorizadas` de `control.json`, siguiendo `spec.md` R1-R11, R20 y R23. No ejecutar
nada; reportar al Lead qué correr.

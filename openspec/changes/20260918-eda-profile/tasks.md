# Tareas — 20260918-eda-profile

estado: cerrada

## Invocaciones planificadas
1. **Writer SDD** (esta): completa `proposal.md`, `spec.md`, `design.md`, `tasks.md` y el
   alcance de `control.json`. Sin código.
2. **Writer implementación, tanda A**: `tools/reporting/profiles/__init__.py`,
   `tools/reporting/profiles/eda.py` y `tools/reporting/tests/test_eda_profile.py` (R1-R18,
   R23).
3. **Writer implementación, tanda B**: `tools/reporting/examples/__init__.py`,
   `tools/reporting/examples/eda_generic.py`, `tools/reporting/tests/test_eda_example.py`,
   4 entradas de `tools/ds_init/manifest.py`, aserciones de `test_installability.py`, filas de
   `ARCHITECTURE.md` §2.1 y rutas de `MODULOS_CORE` (R19-R21, R23). No ejecutan nada.
4. **Lead corre tests**: `tools/reporting/tests/`, `tools/tests/`, `tools/ds_init/tests/`,
   `test_manifest_dsguard_parity.py` y `python -m tools.ds_init.check_manifest_parity`; entrega
   resultados al reviewer.
5. **data-science-reviewer**: revisión independiente (leakage, ausencia ≠ PASS, gaming de
   razones/`auto`, adecuación de las reglas por scope, ejemplo sin datos reales).
6. **Writer fixes**: corrige los hallazgos del reviewer y de los tests; el Lead re-corre.
7. **Writer cierre**: escribe `verification.md` (números de la corrida real, no de memoria) y
   tilda `[x] Change 2` en `docs/roadmap/v0.6.md`.

## Tareas
- [ ] `profiles/eda.py`: `BlockInfo`, `BLOCK_CATALOG` (11 bloques, familias), `STATES` (R2, R3)
- [ ] `profiles/eda.py`: `BlockEvaluation` y `derive_evaluations` (R3, R4)
- [ ] `profiles/eda.py`: `coverage_table` y `build_eda_report` (R5-R7)
- [ ] `profiles/eda.py`: `validate_eda_report` y reglas `EDA-PROFILE`,
  `EDA-APPLICABILITY-MISSING`, `EDA-BLOCK-UNEVALUATED/UNKNOWN/STATE` (R8-R10)
- [ ] `profiles/eda.py`: `EDA-BLOCK-REASON`, `EDA-REASON-DUPLICATED`, `EDA-AUTO-INVALID`
  (R11, R12)
- [ ] `profiles/eda.py`: `EDA-BLOCK-NO-CHAPTER/NO-INSIGHT/CONTRADICTION`,
  `EDA-CHAPTER-BLOCK-UNKNOWN`, `EDA-TARGET-DECLARED`, `EDA-TIME-DECLARED` (R13, R14)
- [ ] `profiles/eda.py`: `EDA-OMITTED-SCOPE`, `EDA-LEAKAGE-REVIEW-REQUIRED`,
  `EDA-EXPLORATORY-TARGET-USE`, `EDA-COVERAGE-TABLE` (R15-R18)
- [ ] `profiles/eda.py`: restricciones transversales R1/R8 (imports, nunca lanza, determinista)
- [ ] `tools/reporting/tests/test_eda_profile.py` (R23)
- [ ] `examples/eda_generic.py` (R19) y `tools/reporting/tests/test_eda_example.py` (R23)
- [ ] `tools/ds_init/manifest.py`: 4 entradas VERBATIM tras `tools/reporting/__main__.py`,
  `stage_minimo` default; aserciones en `test_installability.py` (R20)
- [ ] `ARCHITECTURE.md` §2.1 y `MODULOS_CORE` en `test_architecture_boundaries.py` (R21)
- [ ] Verificar R22: `core.py`, `governance.py`, `cli.py`, `__main__.py`, `__init__.py` de
  reporting sin cambios (`git diff`)
- [ ] Lead: correr tests y `check_manifest_parity`
- [ ] data-science-reviewer: revisión independiente
- [ ] Aplicar fixes del reviewer y re-correr tests
- [ ] `openspec/changes/20260918-eda-profile/verification.md` (al cierre)
- [ ] `docs/roadmap/v0.6.md`: tildar `[x] Change 2`

## Dependencias
- Change 0 (`20260918-reporting-core`): `tools/reporting/core.py` (`Report`, `Chapter`,
  `Insight`, `TableArtifact`, `FigureArtifact`, `ReportingContractError`, `REPORT_KINDS`,
  `DECISION_SCOPES`).
- Change 1 (`20260918-reporting-governance`): solo como referencia del patrón de imports de
  `dsguard.checks`; el profile no importa `governance`.
- `dsguard.checks` (`CheckResult`) se reusa SIN modificarlo.
- Ningún holdout, dataset sellado, `data/raw` ni `.claude/guardrails.json` se lee o modifica.

## Próximo paso exacto
Invocación 2 (writer implementación, tanda A): en estado `propuesta_pendiente` (no pausada),
implementar `profiles/__init__.py`, `profiles/eda.py` y `test_eda_profile.py` dentro de
`alcance.rutas_autorizadas` de `control.json`, siguiendo `spec.md` R1-R18 y R23. No ejecutar
nada; reportar al Lead qué correr.

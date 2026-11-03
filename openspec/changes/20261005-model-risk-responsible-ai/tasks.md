# Tareas — 20261005-model-risk-responsible-ai

estado: cerrada

## Invocaciones planificadas
- Writer (`python-data-engineer`): T1–T5; instancias con propiedad de archivos disjunta y explícita (ver
  deuda v0.10 «One-writer concurrency semantics»).
- Reviewer (`data-science-reviewer`): tras T5; máx. 2 ciclos writer↔reviewer; foco especial en
  monotonicidad, no-relajación, N/A, aislamiento de claims, ausencia de inferencia ética y de claims de
  compliance.
- Ejecución: runtime gobernado `ds_guard exec` con aprobaciones por `ds_guard exec approve`.

## Tareas
- [x] T0 — Aprobación humana del SDD (incluida la matriz base v1, R22).
- [x] T1 — `core.py` (+kind de Card, +3 kinds observados) y ajustes mínimos de tests de Changes 0–2.
- [x] T2 — `resolvers.py`: `model_card`, `governance_policy`, `evidence_document` + `default_resolvers`.
- [x] T3 — `govpolicy.py`: tipos, orden de fuerza, `BASE_POLICY`, hardening, `merge`, hashes.
- [x] T4 — `modelgov.py`: body, identidad, validador, claims, requisitos derivados, evaluador propio,
  `card_path`, `write_governance_assessment`, `evaluate_governance_assessment`.
- [x] T5 — Tests (`tools/cards/tests/*`, `tools/tests/test_v09_modelgov_*`) y documentación
  (ARCHITECTURE regla 13/§8, roadmap v0.9).
- [x] T6 — Revisión independiente, fixes, regresión por lotes, verification.md, cierre, commit local.

## Dependencias
Changes 0, 1 y 2 cerrados. Habilita Change 4.

## Próximo paso exacto
Aprobación humana del SDD.

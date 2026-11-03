# Tareas — 20261005-model-cards

estado: cerrada

## Invocaciones planificadas
- Writer (`python-data-engineer`): T1–T5; único rol que edita código (instancias file-disjoint en
  paralelo, como en Change 1; ver deuda v0.10 «One-writer concurrency semantics»).
- Reviewer (`data-science-reviewer`): tras T5; máx. 2 ciclos writer↔reviewer.
- Ejecución: runtime gobernado `ds_guard exec` con aprobaciones por `ds_guard exec approve` (requiere la
  aprobación humana del SDD que las incluya).

## Tareas
- [x] T0 — Aprobación humana del SDD.
- [x] T1 — `core.OBSERVED_KINDS` (+3 kinds) y ajustes mínimos de tests de Changes 0–1 afectados.
- [x] T2 — `resolvers.py`: `data_card`, `model_quality_result`, `model_quality_policy`, `observed_metric`,
  `baseline_reference`, `drift_evidence`, `execution_record` + hashes públicos + `default_resolvers`.
- [x] T3 — `tools/cards/modelcard.py` (body, identidad, validador, claims, `requirements_for`,
  `card_path`, `write_model_card`, `evaluate_model_card`).
- [x] T4 — Tests (`tools/cards/tests/*` y `tools/tests/test_v09_modelcards_*`) con objetos reales.
- [x] T5 — Documentación: ARCHITECTURE (regla 13/§8), roadmap v0.9 (progreso).
- [x] T6 — Revisión independiente, fixes, regresión por lotes, verification.md, cierre, commit local.

## Dependencias
Changes 0 y 1 cerrados (`f5c3638`, `4ee222c`). Habilita Change 3 y Change 4.

## Próximo paso exacto
Aprobación humana del SDD.

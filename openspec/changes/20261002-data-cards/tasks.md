# Tareas — 20261002-data-cards

estado: cerrada

## Invocaciones planificadas
- Writer (`python-data-engineer`): T1–T5; único que edita código.
- Reviewer (`data-science-reviewer`): tras T5; máx. 2 ciclos writer↔reviewer.
- Ejecución: runtime gobernado `ds_guard exec` con aprobaciones registradas vía `ds_guard exec approve`
  (autorización humana vigente para Change 0 y el corrective; para Change 1 se requiere la aprobación del
  SDD que la incluya).

## Tareas
- [x] T0 — Aprobación humana del SDD.
- [x] T1 — `assess.write_card(exclusive=)` + tests de la extensión.
- [x] T2 — `tools/cards/datacard.py` (body, validador, `requirements_for`, `card_path`,
  `write_data_card`, `evaluate_data_card`).
- [x] T3 — `tools/cards/resolvers.py` (source_observation, source_provenance, harmessi_contract,
  quality_evidence, data_contract_result, `default_resolvers`).
- [x] T4 — Tests (`tools/cards/tests/*` y `tools/tests/test_v09_datacards_*`) con objetos reales ligeros.
- [x] T5 — Documentación: ARCHITECTURE (regla 13/§8), roadmap v0.9 (progreso), v0.10 (deuda ya agregada).
- [x] T6 — Revisión independiente, fixes, regresión por lotes, verification.md, cierre, commit local.

## Dependencias
Change 0 cerrado (`f5c3638`). Habilita Change 2 (Model Cards) y Change 4.

## Próximo paso exacto
Aprobación humana del SDD.

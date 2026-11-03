# Tareas — 20261006-sdd-parsers-and-guardrail-ownership

estado: cerrada

## Invocaciones planificadas
- Writer W-A (`python-data-engineer`): T1–T2 — dueño exclusivo de `tools/dsguard/sdd.py`, `tools/dsguard/pep440_subset.py` y de
  `tools/tests/test_sdd_checkpoints_approved.py` (parte de parser/primitiva), `tools/tests/test_pep440_subset.py`,
  `tools/tests/test_dependency_versions_subset.py`.
- Writer W-B: T3 — dueño exclusivo de `tools/ds_guard.py` (solo `approve`/`status`), `tools/cards/approvals.py` y los tests
  `tools/tests/test_checkpoints_cli.py`; usa las APIs de `sdd.py` de W-A con los nombres del spec (R1, R6–R8, R10).
- Writer W-C: T4 — dueño exclusivo de `tools/dsguard/guardrails_drift.py`, `tools/harmessi/doctor.py`, `tools/ds_init/manifest.py`
  y los tests `tools/tests/test_guardrails_drift.py`, `tools/harmessi/tests/test_doctor_guardrails.py`.
- Reviewer (`data-science-reviewer`): máx. 2 ciclos. Ejecución: `ds_guard exec` con aprobaciones por `ds_guard exec approve`.

## Tareas
- [ ] T0 — Aprobación del SDD (autorización humana anticipada, por hash).
- [ ] T1 — `sdd.py`: primitiva `resolver_aprobacion_registrada`, checkpoints `@approved` (`parsear_checkpoints_de_propuesta`,
  `checkpoints_con_placeholder_cero`, `verificar_checkpoints`) [W-A].
- [ ] T2 — Subset PEP 440 (`pep440_subset.py`) y delegación desde `sdd.py` [W-A].
- [ ] T3 — `ds_guard approve`/`status` + refactor de `cards.approvals` sobre la primitiva [W-B].
- [ ] T4 — `guardrails_drift.py`, Doctor (drift semántico + `HARMESSI-AUTONOMY-CONFIG`), manifiesto [W-C].
- [ ] T5 — Tests de inercia/instalabilidad, ARCHITECTURE, roadmaps [Lead].
- [ ] T6 — Revisión, fixes, regresión por lotes, verification.md, gate, cierre, commit local.

## Dependencias
Corrective A y Changes 0–4 cerrados. Habilita Corrective C.

## Próximo paso exacto
Aprobar el SDD por hash.

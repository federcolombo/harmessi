# Tareas — 20261002-card-and-evidence-foundation

estado: cerrada

## Invocaciones planificadas
- Writer (`python-data-engineer`): T1–T6, único que edita código.
- Reviewer (`data-science-reviewer`): tras T6; máx. 2 ciclos writer↔reviewer.
- Runtime gobernado: ejecución de tests dirigidos y suite completa (el writer no ejecuta).

## Tareas
- [x] T0 — Aprobación humana del SDD (proposal/spec/design) y resolución de O1–O3.
- [x] T1 — `tools/cards/core.py`: constantes, códigos `CARD-*`, ids, `EvidenceRef`, `HumanAttestation`,
  `Claim`, `Requirement`, `CardEnvelope`, serialización, `content_sha256`.
- [x] T2 — `tools/cards/assess.py`: `Resolution`, resolver genérico por archivo, estados de evidencia,
  evaluación de completitud, mapeo a `CheckResult`, lectura/escritura atómica por ruta.
- [x] T3 — Tests unitarios `tools/cards/tests/` (core, evidence, attestation, assess, serialization).
- [x] T4 — Tests de repo: neutralidad (AST), paridad con `datasources`, `STOP_CATALOG` intacto,
  retrocompatibilidad (sin cambios en manifest/`ds_guard`).
- [x] T5 — `ARCHITECTURE.md` regla 13 + §8 expandida; nota de estado en `docs/roadmap/v0.9.md`.
- [x] T6 — Revisión independiente, fixes, verification.md, cierre, commit local.

## Dependencias
Ninguna previa. Habilita Changes 1 y 2.

## Próximo paso exacto
Aprobación humana del SDD.

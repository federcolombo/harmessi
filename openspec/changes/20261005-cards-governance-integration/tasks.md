# Tareas — 20261005-cards-governance-integration

estado: cerrada

## Invocaciones planificadas
- Writer (`python-data-engineer`): T1–T7; instancias con propiedad de archivos disjunta y explícita (deuda v0.10
  «One-writer concurrency semantics»).
- Reviewer (`data-science-reviewer`): tras T7; máx. 2 ciclos; foco: default idéntico/opt-in real, dependencia
  `model_governance→predictive_modeling`, `sync` mismo-stage, hardening omitido/otro/viejo ⇒ stale, relajación
  local, `anchored` no verificada (sin degradación), estado derivado, tabla de severidad Doctor, no-drift de
  `governance/`, reporting sin evidencia duplicada y con aclaración, inercia de autonomía.
- Ejecución: runtime gobernado `ds_guard exec` con aprobaciones por `ds_guard exec approve`.

## Tareas
- [ ] T0 — Aprobación humana del SDD.
- [ ] T1 — `ds_init`: vocabulario opt-in, `capabilities_cualquiera`, helper de filtro único, entradas de
  `tools/cards` (verificar grafo de imports por capability), `governance/` en exclusiones, `--enable-capability`,
  dependencia, set de `sync`, `sync` mismo stage; tests de capabilities/instalabilidad.
- [ ] T2 — `tools/cards/govconfig.py` + hook/contexto aditivos en `modelgov` (R24–R33); tests de hardening.
- [ ] T3 — `tools/cards/approvals.py` + `anchor_verifier` en `assess`/`datacard`/`modelcard`/`modelgov` (R34–R42).
- [ ] T4 — `tools/cards/discovery.py` + `ds_guard cards validate|report` (R19–R23, R43–R52).
- [ ] T5 — Doctor `HARMESSI-GOV-*` (R53–R62) y filtro unificado.
- [ ] T6 — (incluye el valor aditivo `governance` en `reporting.core.REPORT_KINDS` y sus tests de vocabulario/aislamiento de holdout) — `tools/cards/report.py` (R63–R72).
- [ ] T7 — Enmiendas de tests de inercia/neutralidad, docs (ARCHITECTURE, roadmaps), tests de compatibilidad.
- [ ] T8 — Revisión independiente, fixes, regresión relevante por lotes secuenciales, verification.md, gate,
  cierre, commit local.

## Dependencias
Changes 0, 1, 2 y 3 cerrados. Habilita Change 5 (release hardening).

## Próximo paso exacto
Aprobación humana del SDD (proposal.md, spec.md, design.md) por hash.

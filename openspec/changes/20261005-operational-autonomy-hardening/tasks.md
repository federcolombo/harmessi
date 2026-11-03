# Tareas — 20261005-operational-autonomy-hardening

estado: cerrada

## Invocaciones planificadas
- Writer W-A (`python-data-engineer`): T1–T3 — dueño exclusivo de `tools/ds_guard.py`, `tools/autonomy/policy.py`,
  `tools/dsguard/sdd.py`, `tools/dsguard/scope.py`, plantilla `proposal.md` y de los tests
  `test_operational_budgets.py`, `test_operational_scope.py`, adiciones a `tools/autonomy/tests/test_policy.py`.
- Writer W-B (`python-data-engineer`), en paralelo con propiedad disjunta — dueño exclusivo de
  `tools/dsguard/hook_presupuesto.py`, `tools/dsguard/pathguard.py`, `tools/leadrun/allowlist.py` y de
  `test_operational_session_recovery.py`, `test_operational_hook_guardrails.py`, adiciones a
  `tools/leadrun/tests/test_allowlist.py`. W-B no edita `ds_guard.py`: el cambio del hash de pytest (R19) lo hace W-A
  usando `leadrun.allowlist.normalizar_interprete` ya existente.
- Reviewer (`data-science-reviewer`): tras T4; máx. 2 ciclos.
- Ejecución: runtime gobernado `ds_guard exec` con aprobaciones por `ds_guard exec approve` (autorización humana anticipada).

## Tareas
- [ ] T0 — Aprobación del SDD (autorización humana anticipada, por hash).
- [ ] T1 — Budgets/limits + fuentes + `policy.py` (R1–R7) [W-A].
- [ ] T2 — Alcance autorizado, `dir/**` en exec, `verification.md`, outputs intrínsecos, hash de pytest (R19, R22–R40) [W-A / W-B para `allowlist.py`].
- [ ] T3 — Hook: recuperación, variantes de intérprete, N1 (R11–R14, R18, R43–R46) [W-B].
- [ ] T4 — Tests de inercia/compatibilidad, ARCHITECTURE, roadmaps (reformular la deuda v0.10) [Lead].
- [ ] T5 — Re-aprobación de `proposal.md` (mismo hash) para materializar el alcance con el comando soportado.
- [ ] T6 — Revisión, fixes, regresión por lotes, verification.md, gate, cierre, commit local.

## Dependencias
Ninguna sobre Change 4 (no se toca). Bloquea la implementación de Change 4.

## Próximo paso exacto
Aprobar el SDD por hash.

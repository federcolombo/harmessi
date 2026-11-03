# Verificación — 20261026-v015-runtime-observability

## Resumen
Change C4 de v0.15: telemetría de subagentes (`hook_subagentes` + launcher fail-open), `subagentes[agent_id]` con arranques/paradas/continuaciones/duración, métricas de eficiencia, Doctor `HARMESSI-HOOKS-SUBAGENTES`. Cierra B-16 y B-17/B-18 (H1 confirmado con payloads reales y smoke en vivo); B-19 queda como limitación aceptada.

## Cambios de código
- `tools/dsguard/hook_subagentes.py`, `tools/dsguard/hook_launcher_subagentes.py` (nuevos), `tools/dsguard/efficiency.py`, `tools/dsguard/sdd.py`, `tools/ds_guard.py`, `tools/ds_init/manifest.py`, `tools/harmessi/doctor.py`.
- Tests: `tools/tests/test_hook_subagentes.py` (nuevo) y ajustes en `test_efficiency`, `test_session_recovery`, `test_skill_methodology`, `test_architecture_boundaries`, `tools/harmessi/tests/test_doctor.py`.
- Fixtures: `tools/tests/fixtures/hooks/{agent_launch,pretool_in_subagent,subagent_start,subagent_stop,sendmessage_to_agent_id}.json`.
- Docs: ARCHITECTURE §11.2, `docs/roadmap/v0.15.md` §C4, `docs/roadmap/v0.15-debt-matrix.md` (B-16..B-19), `methodology.md` y su template.

## Evidencia obtenida
- Activación humana en `.claude/settings.json` del proyecto (SubagentStart/SubagentStop → launcher), JSON válido; el global solo conserva `Notification`.
- Smoke real post-activación (2026-10-26): dos subagentes `data-science-reviewer` con `agent_id` distintos; contadores independientes (A: 1 continuación, 2 arranques y 2 paradas; B: 0 continuaciones, 1 arranque y 1 parada). `SendMessage` con `to = agent_id` incrementó `continuaciones` bajo esa clave. Una reanudación por `SendMessage` SÍ dispara `SubagentStart`.
- Tests del Lead: `test_hook_subagentes` + `test_architecture_boundaries` + `test_doctor` = 141 passed; `test_efficiency` 28, `test_session_recovery` 29, `test_skill_methodology` 71, `test_ds_guard_budgets_cli` 36, `test_autonomy_sdd` 45, ds_init `test_manifest` 42 / `test_settings_merge` 8 / `test_manifest_completitud` 4, `test_remediation` 25 passed; `test_v013_contract_inventory` falló por una constante heredada de C3 (`DATA_CARD_KIND_SCHEMA_VERSIONS_LEIDAS`), resuelta en C5 (38 passed).
- Doctor: `HARMESSI-HOOKS-SUBAGENTES` OK; 36 OK, 9 WARN (drift de archivos managed modificados, esperado hasta el baseline de C7), 0 ERROR.

## Limitaciones
- El fixture `sendmessage_to_agent_id.json` no es un payload PreToolUse crudo (el harness no lo expone): es la llamada real reconstruida; la evidencia es el efecto en el contador.
- Carrera residual de milisegundos en `control.json` (aceptada, B-19); el tope de continuaciones sigue cooperativo.
- Cierre SDD formal PENDIENTE: la transición a `cerrada` no pasa retroactivamente (gate de alcance: C4, C5 y C6 comparten `tools/tests/**` y el baseline de cada uno ve los cambios de los otros). El Change queda en `en_verificacion`, implementado, probado y revisado; ver brecha de proceso en `docs/roadmap/v0.15.md`.

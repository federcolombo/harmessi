# Tareas — 20261026-v015-runtime-observability

estado: cerrada

## Invocaciones planificadas
- python-data-engineer (writer único, secuencial T1..T12): implementa en su ownership; no ejecuta.
- reviewer único (data-science-reviewer o equivalente): revisa el Change completo tras T12 (privacidad, fail-open, merge/upgrade, honestidad de limitaciones B-18/B-19, no modificación de `hook_presupuesto.py`).
- Lead: corre tests en `.venv`, coordina el estado de hashes managed (baseline en C7) y cierra el Change.

## Ownership de writers
<!-- Un solo writer secuencial; sin ownership paralelo. Rutas = "Alcance autorizado" de proposal.md. -->

## Historial de ownership
<!-- fecha — instancia — ruta — motivo (cambios de ownership hechos ANTES de que el writer edite) -->

## Skills cargados
<!-- ninguna skill cambió decisiones hasta ahora -->

## Tareas
- [x] T1 Fixtures saneados `tools/tests/fixtures/hooks/{agent_launch,pretool_in_subagent,subagent_start,subagent_stop}.json` con ids/paths ficticios y `last_assistant_message = "<redactado>"`; estructura según la evidencia H1 (sin `agent_id` en `agent_launch`).
- [x] T2 `tools/dsguard/hook_subagentes.py`: lógica pura (alta/reanudación/stop, lista blanca de campos, duración acumulada) + `main()` fail-open, sesión activa vía `_hallar_sesion_activa` y `core.escribir_control` con re-lectura previa a la escritura; sin sesión activa no registra.
- [x] T3 `tools/dsguard/hook_launcher_subagentes.py`: launcher que mapea cualquier fallo a exit 0 con aviso a stderr; alta de ambos módulos en `MODULOS_ADAPTER` de `tools/tests/test_architecture_boundaries.py`.
- [x] T4 Solo `tools/ds_init/manifest.py` (+ `tools/ds_init/tests/test_manifest.py` si hace falta): entradas VERBATIM para `SubagentStart`/`SubagentStop` sin matcher. NO tocar `.claude/settings.json` (protegido, no autorizable); si el manifest o sus tests exigieran modificarlo, devolver `blocked` al Lead.
- [x] T5 Esquema y consumo: tolerancia a no-dict en toda iteración de `subagentes` (`tools/ds_guard.py`, `tools/dsguard/sdd.py`, `efficiency.py`), `session start --retomar` hereda entradas con `continuaciones`; `efficiency.py` con `EFICIENCIA-SUBAGENTES` (PASS/N-A, no gate, sin contar entradas por rol como instancias) y docstring corregido; `sdd.calcular_metricas_eficiencia` con `subagent_instances`, `subagent_starts`, `subagent_duration_total_seconds`.
- [x] T6 Tests del hook nuevo `tools/tests/test_hook_subagentes.py`: fixtures reales saneados, alta/reanudación/stop, privacidad (campos prohibidos ausentes), fail-open (JSON inválido, sesión corrupta, OSError, sin agent_id), sin sesión, launcher; integración con `hook_presupuesto.evaluar` (tope de continuaciones por `agent_id`); el hook se invoca directamente con los payloads saneados, sin depender de settings; merge/upgrade sobre settings sintético: `settings_merge` agrega el evento, idempotente, sin pisar hooks previos (preflight de upgrade).
- [x] T7 Ajustar tests que fijan salida/esquema: `test_efficiency.py`, `test_ds_guard_budgets_cli.py`, `test_session_recovery.py` (N/A "sin telemetría de subagentes" cuando no hay entradas).
- [x] T8 (eliminado: D7 ya no aplica; smoke v013/v014/harness no se tocan).
- [x] T9 Doctor: WARN (con snippet de activación en el mensaje) si `settings.json` no registra `SubagentStart`/`SubagentStop` o falta el launcher, en `tools/harmessi/doctor.py` + casos en `tools/harmessi/tests/test_doctor.py` (con falta, completo, sin ERROR).
- [x] T10 D6: `methodology.md` y `methodology.md.tmpl` idénticos ("H1 cerrado como evidencia; activación del hook pendiente; el tope sigue cooperativo hasta activar"; B-19 limitación aceptada; task-id/reviewer-cycle fuera del hook; límites de privacidad); revisar `FRASES_METHODOLOGY` en `test_skill_methodology.py`. No regenerar baseline.
- [x] T11 Documentación: snippet exacto de activación de `SubagentStart`/`SubagentStop` en `ARCHITECTURE.md` y en un apartado nuevo de `docs/roadmap/v0.15.md` §C4, marcado como paso humano T1 pendiente (superficie protegida, fuera del Change); `docs/roadmap/v0.15-debt-matrix.md` (B-16 cerrado; B-17 y B-18 "implementado, activación pendiente de paso humano", B-18 con salvedad de reanudación no observada; B-19 accepted limitation); `README.md`; `docs/contracts/inventory.json` si el esquema de sesión/hook está inventariado.
- [x] T12 Cierre del writer: confirmar que `hook_presupuesto.py` y `.claude/settings.json` no fueron tocados; recordar al Lead el paso humano de activación pendiente; reportar `completed`/`blocked`/`needs-review` con lista de tests para el Lead y los hashes managed pendientes de C7.

## Dependencias
- T1 -> T2 -> T3; T4 depende de T3 (el comando del manifest apunta al launcher).
- T5 es independiente de T2 pero debe preceder a T6 (integración) y T7.
- T6 depende de T1..T5; T7 depende de T5; T8 eliminado.
- Activación en `.claude/settings.json`: paso humano T1 pendiente, fuera de este Change y de sus dependencias.
- T9 depende de T3 y T4; T10 independiente; T11 depende de T1..T10.
- T12 al final. Reviewer único tras T12. Baseline de hashes managed: C7, fuera de este Change.

## Próximo paso exacto
<!-- obligatorio si estado: pausada_bloqueada -->

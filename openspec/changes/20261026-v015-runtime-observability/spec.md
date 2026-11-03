# Spec — 20261026-v015-runtime-observability

## Requisitos
- **R1 (B-17, H1)**: el payload real de `PreToolUse(Agent)`, `PreToolUse` dentro del subagente, `SubagentStart` y `SubagentStop` queda documentado y cubierto por fixtures saneados en `tools/tests/fixtures/hooks/`. No queda texto "UNCONFIRMED" en `methodology.md`, su template ni la matriz.
- **R2 (hook)**: `hook_subagentes.py` procesa `SubagentStart` y `SubagentStop` y registra en la sesión SDD activa `subagentes[agent_id] = {rol, inicio_utc, arranques, paradas, fin_utc, duracion_s, continuaciones, ultimo_evento_utc}`.
  - Alta nueva: `arranques=1`, `paradas=0`, `continuaciones=0`.
  - `agent_id` existente en `SubagentStart`: `arranques += 1`, `continuaciones` intacto.
  - `SubagentStop`: `paradas += 1`, `fin_utc`, `duracion_s` acumulada (si hay `inicio` del arranque vigente), `ultimo_evento_utc`.
- **R3 (privacidad)**: nunca se persiste `last_assistant_message`, `agent_transcript_path`, `transcript_path`, prompt ni `cwd`. Solo `agent_id`, `agent_type` (como `rol`) y marcas de tiempo.
- **R4 (fail-open)**: el hook y su launcher terminan siempre con exit 0; cualquier error (JSON inválido, sesión corrupta, escritura fallida, import fallido) va a stderr. Sin sesión activa no registra ni falla.
- **R0 (D2b, activación)**: el Change NO modifica `.claude/settings.json` (superficie protegida, no autorizable: `sdd.py:1391`). Sin la activación humana el hook está dormant: efficiency muestra N/A "sin telemetría de subagentes" y el tope de continuaciones sigue cooperativo. El snippet exacto de activación está en `ARCHITECTURE.md` y en `docs/roadmap/v0.15.md` §C4.
- **R5 (tope por agent_id, B-18; vigente una vez activado el hook)**: con la entrada por `agent_id` creada por `SubagentStart`, `SendMessage` con `to=<agent_id>` es encontrado por `hook_presupuesto` (sin modificarlo) y el tope `max_continuaciones_por_subagente` se aplica. Es consecuencia a verificar con test de integración, no una modificación de `hook_presupuesto.py`.
- **R6 (esquema, D3)**: `subagentes` conserva `conteo` (int) y entradas dict; todo código que itera `subagentes` ignora valores no-dict; `session start --retomar` hereda las entradas con `continuaciones`.
- **R7 (efficiency, B-16)**: `efficiency.py` emite `EFICIENCIA-SUBAGENTES` (PASS con datos, N-A sin datos; nunca FAIL ni gate) con instancias, arranques, continuaciones, duración total y desglose por rol. `sdd.calcular_metricas_eficiencia` suma `subagent_instances`, `subagent_starts`, `subagent_duration_total_seconds` de forma aditiva. Docstring sin "hoy muerto".
- **R8 (B-19)**: no hay enforcement de ownership por instancia; el motivo queda registrado en `methodology.md`/template, matriz y ARCHITECTURE.
- **R9 (manifest/upgrade)**: `manifest.py` declara el evento nuevo con entradas VERBATIM; un `upgrade` sobre una instalación previa lo recibe vía `settings_merge` sin pisar hooks existentes ni duplicar entradas (idempotente). `.claude/settings.json` de este repo no cambia.
- **R10 (D7 eliminado)**: los smoke v013/v014/harness no se tocan; deben seguir pasando sin cambios.
- **R11 (doctor)**: `_check_hooks` emite WARN (no ERROR) si `settings.json` no registra `SubagentStart`/`SubagentStop` o falta el launcher; el mensaje incluye el snippet de activación; sin WARN con instalación completa.
- **R12 (límites arquitectónicos)**: el módulo nuevo figura en `MODULOS_ADAPTER` y respeta `test_architecture_boundaries`.

## Criterios de aceptación
- [ ] Los 4 fixtures existen, son JSON válidos, con ids/paths ficticios y `last_assistant_message == "<redactado>"`; un test verifica que no contienen paths reales del usuario.
- [ ] Test: `agent_launch.json` NO tiene `agent_id`/`agent_type`; `pretool_in_subagent.json`, `subagent_start.json` y `subagent_stop.json` sí.
- [ ] Given sesión activa, When llega `subagent_start.json`, Then `subagentes[agent_id]` se crea con `arranques=1`, `continuaciones=0`, `rol=agent_type`.
- [ ] Given entrada existente con `continuaciones=1`, When llega otro `SubagentStart` del mismo id, Then `arranques` +1 y `continuaciones` sigue en 1.
- [ ] Given arranque registrado, When llega `subagent_stop.json`, Then `paradas=1`, `fin_utc` y `duracion_s >= 0`.
- [ ] Given cualquier evento, Then el control.json resultante no contiene `last_assistant_message`, `agent_transcript_path`, `transcript_path`, `cwd` ni el texto del prompt (assert sobre el JSON serializado y sobre los valores del fixture).
- [ ] Sin sesión activa: exit 0, sin escritura. JSON inválido/vacío en stdin, sesión corrupta, `OSError` al escribir, `agent_id` ausente: exit 0 y aviso en stderr.
- [ ] El launcher mapea excepción de import/ejecución a exit 0 con stderr (a diferencia de `lanzar_hook` fail-closed).
- [ ] Integración: con la entrada por `agent_id` creada por el hook nuevo y `max_continuaciones_por_subagente=1`, el primer `SendMessage to=<agent_id>` se permite e incrementa; el segundo es denegado por `hook_presupuesto.evaluar`.
- [ ] `subagentes` con `conteo` int y entradas dict: efficiency, `calcular_metricas_eficiencia` y `--retomar` no fallan y heredan `continuaciones`.
- [ ] `EFICIENCIA-SUBAGENTES`: PASS con entradas, N-A sin ellas; no altera el exit code de ningún gate; `test_efficiency` y `test_ds_guard_budgets_cli` actualizados para la salida/claves nuevas.
- [ ] `methodology.md` y su template quedan idénticos y sin "UNCONFIRMED"; `test_skill_methodology` pasa (frases revisadas).
- [ ] Test de upgrade/merge (sobre settings sintético en tmp, no el del repo): sin `SubagentStart/Stop`, aplicar `settings_merge`, obtener el evento nuevo, hooks previos intactos; segunda aplicación sin duplicados. `test_manifest` cubre las entradas VERBATIM y que el hash managed esperado de `.claude/settings.json` del repo no cambia.
- [ ] Los tests del hook invocan `hook_subagentes` directamente con los payloads saneados, sin depender de `.claude/settings.json`.
- [ ] `git diff` no toca `.claude/settings.json` ni `test_v013`/`test_v014`/`test_harness_smoke`.
- [ ] `test_doctor`: WARN (con snippet en el mensaje) con evento/launcher faltante, sin WARN completo, ningún ERROR nuevo; el repo actual (settings sin eventos) produce WARN, no falla.
- [ ] `ARCHITECTURE.md` y `docs/roadmap/v0.15.md` §C4 contienen el snippet exacto de activación y la advertencia de que es un paso humano pendiente.
- [ ] `test_architecture_boundaries` incluye `hook_subagentes` y `hook_launcher_subagentes` en `MODULOS_ADAPTER` y pasa.
- [ ] Matriz: B-16 cerrado, B-17 y B-18 "implementado, activación pendiente de paso humano" (H1 cerrado como hallazgo; B-18 con la salvedad "arranques tras reanudación por `SendMessage` no verificado: no se observó si `SubagentStart` se dispara en la reanudación"), B-19 ACCEPTED LIMITATION con razón.
- [ ] `git diff` no toca `tools/dsguard/hook_presupuesto.py`.

## Unidad de análisis / grain (condicional — data_understanding, feature_engineering, modeling)
No aplica.

## Cutoff / information boundary (condicional — feature_engineering, data_preparation, modeling)
No aplica.

## Baseline (condicional — modeling)
No aplica.

## Métrica primaria (condicional — modeling, evaluation)
No aplica.

## Métricas secundarias (opcional)
No aplica.

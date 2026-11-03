# Propuesta — 20261026-v015-runtime-observability

## Problema
La telemetría de subagentes (`sesion["subagentes"]`) tiene tres defectos acumulados desde v0.10:

1. **H1 UNCONFIRMED (B-17)**: el payload real de los hooks de Claude Code para `Agent`/subagentes nunca se verificó. `hook_presupuesto._extraer_agent_id` prueba `agent_id/agent_name/id/subagent_type/name` dentro de `tool_input` y termina usando `subagent_type` (el rol) como clave.
2. **Tope de continuaciones inefectivo (B-18)**: `SendMessage.to` es un `agent_id` hexadecimal que no coincide con la clave por rol, por lo que el tope `max_continuaciones_por_subagente` nunca se aplica en la práctica (hoy es cooperativo).
3. **Sin consumo (B-16)**: `efficiency.py` no consume `subagentes` y su docstring dice "hoy muerto", lo cual es falso (el hook la puebla; D-017).

Además, B-19 pregunta si el ownership puede validarse por instancia en el hook.

## Objetivo
Cerrar H1 con el payload real y construir observabilidad de runtime de subagentes por `agent_id` (hook nuevo `SubagentStart`/`SubagentStop`, informativo y fail-open), consumirla en efficiency, y dejar registrado que el ownership por instancia no tiene atribución fiable (limitación aceptada).

## Evidencia
Payload real obtenido por el Lead el 2026-10-26 con `claude -p` 2.1.310, desde un directorio fuera del repo y un `--settings` temporal cuyo hook solo volcaba stdin; sin tocar `.claude/settings.json` del proyecto; `permission-mode` default (un primer intento con `bypassPermissions` fue denegado por el clasificador y no se repitió):

- (a) `PreToolUse` de `Agent` desde el hilo principal: `{session_id, prompt_id, permission_mode, effort{level}, hook_event_name, tool_name:"Agent", tool_input:{description, prompt, subagent_type}, tool_use_id, cwd, transcript_path}`. SIN `agent_id` ni `agent_type`.
- (b) `PreToolUse` de una tool llamada dentro del subagente (p. ej. `Glob`): mismos campos más `agent_id` y `agent_type` a nivel raíz.
- (c) `SubagentStart`: `{agent_id, agent_type, hook_event_name, session_id, cwd, transcript_path}`.
- (d) `SubagentStop`: `{agent_id, agent_type, hook_event_name, stop_hook_active, agent_transcript_path, last_assistant_message [PRIVADO], background_tasks, session_crons, ...}`.

Código existente: `tools/dsguard/hook_presupuesto.py:263-273` (`_extraer_agent_id`), `:362-370` (registro por rol, `continuaciones: 0`), `:372-376` (`SendMessage` busca `destino in subagentes`); `tools/dsguard/efficiency.py:1-8` (docstring); matriz `docs/roadmap/v0.15-debt-matrix.md` filas B-16..B-19 y D-017, O-04; `docs/roadmap/v0.15.md` §C4.

## Supuestos descartados
- "El payload de `Agent` trae el `agent_id` del subagente": falso; solo lo traen las llamadas hechas dentro del subagente y los eventos `SubagentStart/Stop`.
- "El tope de continuaciones por `SendMessage` funciona": falso en la práctica (clave por rol vs. `to` por `agent_id`).
- "La telemetría de subagentes está muerta" (O-04): falso; el hook la puebla. Lo que falta es consumo.
- "Se puede vincular `agent_id` con un W# de tasks.md": no es fiable (ver Alcance, B-19).

## Hipótesis (condicional — solo cambios metodológicos)
No aplica (cambio de tooling, sin hipótesis metodológica).

## Alcance
1. **Fixtures saneados (D1)** en `tools/tests/fixtures/hooks/`: `agent_launch.json`, `pretool_in_subagent.json`, `subagent_start.json`, `subagent_stop.json`, con ids y paths ficticios; en `subagent_stop`, `last_assistant_message = "<redactado>"`. Sin datos reales.
2. **Hook nuevo (D2/D2b)** `tools/dsguard/hook_subagentes.py` + `hook_launcher_subagentes.py` para `SubagentStart` y `SubagentStop` (sin matcher), con entradas VERBATIM en `tools/ds_init/manifest.py`. El Change NO modifica `.claude/settings.json`: el harness no permite autorizarlo en un Change (`_ALCANCE_RUTAS_PROTEGIDAS`, `tools/dsguard/sdd.py:1391`; error `SDD-ALCANCE-INVALIDO`), y no se evita ni se debilita. La ACTIVACIÓN (agregar los eventos al settings.json) es un paso humano T1 pendiente, fuera del Change; el snippet exacto se entrega en `ARCHITECTURE.md` y en un apartado de `docs/roadmap/v0.15.md` §C4. Hasta entonces el hook está inactivo (dormant), efficiency muestra N/A "sin telemetría de subagentes" y el tope de continuaciones sigue cooperativo. Una vez activo, registra por `agent_id`: `{rol, inicio_utc, arranques, paradas, fin_utc, duracion_s, continuaciones, ultimo_evento_utc}`. Reanudación (agent_id existente) incrementa `arranques` sin tocar `continuaciones`; así el hook de presupuesto, que sigue sin modificarse, ahora sí encuentra `to` en `subagentes` y el tope funciona. Nunca persiste `last_assistant_message`, `agent_transcript_path`, `transcript_path`, prompt ni `cwd`. Fail-open (siempre exit 0). Sin sesión activa no registra. Alta en `MODULOS_ADAPTER` de `test_architecture_boundaries`.
3. **Esquema (D3)**: `subagentes` mezcla el int `conteo` con entradas dict; toda iteración tolera no-dict; `session start --retomar` hereda entradas con `continuaciones`.
4. **Efficiency (D4)**: check informativo `EFICIENCIA-SUBAGENTES` (PASS/N-A, nunca gate); `sdd.calcular_metricas_eficiencia` suma claves aditivas `subagent_instances`, `subagent_starts`, `subagent_duration_total_seconds`; docstring corregido; tests ajustados. Sin tokens ni costos. `task-id` y `reviewer-cycle` NO se capturan por hook (el payload no los trae y el vínculo launch↔agent_id no es fiable); siguen en `session note`/`roles`/`rondas_revision`.
5. **Ownership por instancia (D5, B-19)**: NO se agrega enforcement. ACCEPTED LIMITATION FOR v1: el payload permite atribuir llamadas a un `agent_id` y rol, pero el `Agent` launch no trae `agent_id` y emparejar por orden es heurístico bajo lanzamientos paralelos del mismo rol; el ownership sigue siendo preflight (`ds_guard ownership check`).
6. **Metodología (D6)**: `methodology.md` y su template, editados idénticamente: "H1 cerrado como evidencia (payload real documentado y fixtures); activación del hook pendiente de paso humano; el tope de continuaciones sigue cooperativo hasta activar"; revisar `FRASES_METHODOLOGY` en `test_skill_methodology`. Esto cambia hashes managed; el baseline se actualiza una sola vez en C7 (no se regenera acá).
7. **D7 eliminado**: como no se toca `.claude/settings.json`, los smoke v013/v014/harness NO se modifican ni se re-anclan.
8. **Doctor**: WARN (nunca ERROR) si `settings.json` no registra `SubagentStart`/`SubagentStop` o falta el launcher; el mensaje incluye el snippet de activación; test.
9. **Estado de matriz**: B-17 y B-18 se reportan "implementado, activación pendiente de paso humano" (H1 cerrado como hallazgo).
10. **Documentación**: matriz B-16..B-19, `docs/roadmap/v0.15.md` §C4, `ARCHITECTURE.md`, `README.md`, `docs/contracts/inventory.json` si el esquema de sesión está inventariado.

Privacidad: sin chain-of-thought, sin prompt, sin tokens inventados.

## Fuera de alcance
- Modificar `tools/dsguard/hook_presupuesto.py` (hook de seguridad) y `.claude/settings.json` (superficie protegida; activación = paso humano T1 fuera del Change).
- Enforcement de ownership por instancia (B-19, limitación aceptada).
- Captura de task-id/reviewer-cycle por hook; tokens, costos o uso de modelo.
- Locking de la sesión (la pérdida de updates con subagentes concurrentes es limitación documentada de telemetría, no de enforcement).
- Regenerar el baseline de hashes managed (C7).
- Ejecutar tests o `claude` desde este Change: lo hace el Lead.

## Holdout policy (condicional — solo cambios "sensible")
No aplica: no toca datos ni holdouts.

## Impacto en production-readiness (opcional)
Ninguno. Los fixtures son saneados y el hook no persiste contenido de conversación.

## Criterios de aceptación (spec-lite — solo SDD abreviado)
Ver spec.md (SDD completo).

## Decisión técnica (design-lite — solo SDD abreviado)
Ver design.md (SDD completo).

## Aprobación
- Usuario:
- Fecha:
- Alcance aprobado:
- Versión de artefactos referenciada:
- Cita o descripción fiel de qué se aprobó:

## Alcance autorizado
- .claude/skills/lead-data-scientist/methodology.md
- tools/ds_init/profiles/python_jupyter_data/templates/methodology.md.tmpl
- tools/dsguard/hook_subagentes.py
- tools/dsguard/hook_launcher_subagentes.py
- tools/dsguard/efficiency.py
- tools/dsguard/sdd.py
- tools/ds_guard.py
- tools/ds_init/manifest.py
- tools/ds_init/tests/test_manifest.py
- tools/tests/test_hook_subagentes.py
- tools/tests/fixtures/hooks/**
- tools/tests/test_efficiency.py
- tools/tests/test_ds_guard_budgets_cli.py
- tools/tests/test_session_recovery.py
- tools/tests/test_architecture_boundaries.py
- tools/tests/test_skill_methodology.py
- tools/harmessi/doctor.py
- tools/harmessi/tests/test_doctor.py
- ARCHITECTURE.md
- README.md
- docs/roadmap/v0.15.md
- docs/roadmap/v0.15-debt-matrix.md
- docs/contracts/inventory.json

## Motivo de rechazo
<!-- completar solo si estado: descartada -->

## Desacuerdo registrado
<!-- completar solo si estado: pausada_bloqueada tras 2 rondas de revisión sin acuerdo -->

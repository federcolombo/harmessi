# Diseño — 20261026-v015-runtime-observability

## Decisión metodológica/técnica
- **D1 H1 cerrado con evidencia**: el payload real (ver proposal.md, Evidencia) se documenta en `methodology.md`/template y se congela en 4 fixtures saneados (`agent_launch.json`, `pretool_in_subagent.json`, `subagent_start.json`, `subagent_stop.json`). Ids y paths ficticios; `last_assistant_message = "<redactado>"`. Consecuencia clave: el `PreToolUse(Agent)` desde el hilo principal NO trae `agent_id`; el `agent_id` solo aparece en eventos `SubagentStart/Stop` y en llamadas hechas dentro del subagente.
- **D2 Hook nuevo, sin tocar el de presupuesto**: `tools/dsguard/hook_subagentes.py` (lógica) + `hook_launcher_subagentes.py` (entrada), diseñado para `SubagentStart` y `SubagentStop` sin matcher.
  - **D2b (cambio obligatorio)**: `.claude/settings.json` es superficie protegida y el harness no permite autorizarlo en un Change (`_ALCANCE_RUTAS_PROTEGIDAS`, `sdd.py:1391`; `SDD-ALCANCE-INVALIDO`); no se evita ni se debilita. El Change entrega hook + launcher + entradas VERBATIM en `manifest.py` + consumo en efficiency + tests + Doctor WARN, pero NO modifica `settings.json`. La activación es un paso humano T1 pendiente: el snippet exacto se entrega en `ARCHITECTURE.md` y en `docs/roadmap/v0.15.md` §C4. Hasta entonces el hook está dormant: efficiency muestra N/A "sin telemetría de subagentes", el tope de continuaciones sigue cooperativo, y B-17/B-18 se reportan "implementado, activación pendiente de paso humano". H1 queda cerrado como hallazgo (payload real y fixtures).
  - Los tests invocan el hook directamente con los payloads saneados, sin depender de settings.
  - Reusa `_hallar_sesion_activa` (import o copia acotada, a decidir en T3 según `test_architecture_boundaries`) y `core.escribir_control`.
  - Esquema por `agent_id`: `{rol, inicio_utc, arranques, paradas, fin_utc, duracion_s, continuaciones, ultimo_evento_utc}`.
  - `SubagentStart` con id nuevo crea la entrada con `continuaciones=0`; con id existente incrementa `arranques` y NO toca `continuaciones` (las incrementa `hook_presupuesto` en `SendMessage`, que ahora sí matchea por `agent_id`).
  - `SubagentStop`: `paradas += 1`, `fin_utc`, `duracion_s += (fin - inicio del arranque vigente)`; si falta inicio vigente, no suma duración. Entrada inexistente en Stop: se crea con lo disponible (`arranques=0`).
  - Lista blanca de campos leídos del payload: `hook_event_name`, `agent_id`, `agent_type`. Nada más se lee ni persiste (R3).
  - Fail-open: `main()` captura todo, escribe a stderr, retorna 0. El launcher nuevo envuelve import y ejecución y mapea todo fallo a exit 0 con aviso (contrario a `lanzar_hook` de `tools/launcher_common.py`, que es fail-closed por seguridad). Es aceptable porque el hook es telemetría, nunca enforcement.
  - Concurrencia (revisión C4, H-2): escritura atómica propia con tmp único por proceso/hilo (`control.json.<pid>.<tid>.tmp`) + `os.replace` con 3 reintentos cortos ante `PermissionError`, re-lectura inmediata antes de mutar y escribir. Carrera residual de ms DECLARADA, limitación aceptada de telemetría Y enforcement: un alta perdida hace que `hook_presupuesto` permita el `SendMessage` sin contar; un contador de `continuaciones` puede revertirse; nunca corrompe el archivo.
  - Fail-open real (H-1): `hook_subagentes.py` no importa `dsguard` ni `hook_presupuesto` (copia mínima de la búsqueda de sesión activa); el launcher importa `launcher_common` de forma perezosa dentro del `try`.
  - M-1: `--retomar` hereda solo `continuaciones` y `rol`, para no duplicar métricas.
  - M-2: no hay payload real de `SendMessage` capturado; el formato real de `to` se congela con un fixture capturado en el smoke real post-activación (paso del Lead). H1 CONFIRMED para Agent/SubagentStart/SubagentStop; B-17 no se da por cerrado hasta ese fixture.
  - M-3: borde `to=="conteo"` (clave int de `subagentes`) con `hook_presupuesto` sin modificar: limitación aceptada (fail-open; input controlado por el modelo).
  - M-4: un Stop sin Start crea la instancia con `arranques=0` (intencional).
- **Coexistencia con las entradas por rol**: `hook_presupuesto` sigue registrando `subagentes[<subagent_type>]` al lanzar `Agent` (clave por rol, `continuaciones=0`). Las entradas por rol y por `agent_id` conviven; efficiency distingue instancias reales por la presencia de `inicio_utc`/`arranques` (campos que solo escribe el hook nuevo) y no cuenta la entrada por rol como instancia. Esto es un detalle de T5 a testear.
- **D3 Esquema**: `subagentes` mezcla `conteo` (int) con dicts; toda iteración aplica `isinstance(v, dict)`. `session start --retomar` hereda entradas con `continuaciones`; las nuevas la llevan, las viejas (solo `continuaciones`/`ultimo_evento_utc`) siguen válidas. Sin cambio de `schema_version` (aditivo).
- **D4 Efficiency**: `EFICIENCIA-SUBAGENTES` informativo (PASS con datos / N-A sin datos), nunca gate; por rol: instancias, arranques, continuaciones, duración. `sdd.calcular_metricas_eficiencia` agrega claves aditivas `subagent_instances`, `subagent_starts`, `subagent_duration_total_seconds` (0 si no hay). Docstring corregido. Sin tokens ni costos (no hay fuente fiable). task-id y reviewer-cycle no se capturan por hook: el payload no los trae y el vínculo launch↔agent_id no es fiable; permanecen en `session note`, `roles`, `rondas_revision`.
- **D5 Ownership por instancia: ACCEPTED LIMITATION FOR v1**: el payload permite atribuir llamadas a `agent_id` y rol, pero el vínculo `agent_id`↔W# de tasks.md no es fiable: el `Agent` launch no trae `agent_id`, y emparejar por orden es heurístico con lanzamientos paralelos del mismo rol. Sin vínculo fiable, un enforcement por instancia produciría falsos bloqueos o falsa seguridad. El ownership sigue siendo preflight (`ds_guard ownership check`). Reevaluar solo si Claude Code expone `agent_id` en el launch o un identificador de correlación.
- **D6 methodology.md + template**: reemplazar "H1, UNCONFIRMED" por: "H1 cerrado como evidencia (payload real documentado); activación del hook pendiente de paso humano; el tope de continuaciones sigue cooperativo hasta activar" (por `agent_id` vía `SubagentStart` una vez activo); atribución por instancia a ownership no fiable (limitación aceptada). Edición idéntica en ambos archivos; se revisa `FRASES_METHODOLOGY`. Los hashes managed cambian; el baseline se actualiza una sola vez en C7 (no se regenera aquí; los tests de baseline pueden quedar en rojo hasta C7: el Lead lo sabe y lo coordina).
- **D7 eliminado**: al no modificarse `.claude/settings.json`, los smoke v013/v014/harness siguen válidos sin cambios; no se re-ancla ni se toca ningún test de superficie protegida.
- **Doctor**: `_check_hooks` hoy solo mira `PreToolUse`. Se agrega chequeo separado WARN si `settings.json` no registra `SubagentStart`/`SubagentStop` o falta el launcher en disco, con el snippet de activación en el mensaje; nunca ERROR (este repo y los instalados previos no lo tienen hasta la activación humana).

## Target (condicional — feature_engineering, modeling)
No aplica.

## Features permitidas/prohibidas (condicional — feature_engineering)
No aplica.

## Estrategia de split/validación (condicional — holdout involucrado, modeling, evaluation)
No aplica.

## Leakage risks (condicional — feature_engineering, data_preparation, modeling)
No aplica (sin datos ni modelos). Riesgo análogo de privacidad: el payload de `SubagentStop` incluye `last_assistant_message` y paths de transcript; se mitiga con lista blanca de campos y un test que verifica su ausencia en lo persistido.

## Reproducibilidad (opcional — solo si se desvía del default: RANDOM_STATE fijo, .venv)
Sin aleatoriedad. Los tests usan fixtures estáticos y reloj inyectable/`core.ahora_utc` parcheado. El Lead corre los tests en `.venv`; el writer no ejecuta nada.

## Alternativas descartadas
- Modificar `hook_presupuesto._extraer_agent_id`: es hook de seguridad, fuera de scope; además el `Agent` launch no trae `agent_id`, así que no se arregla desde ahí.
- Emparejar launch↔`agent_id` por orden/timestamp: heurístico e incorrecto con paralelismo del mismo rol.
- Enforcement de ownership por instancia: ver D5.
- Hook fail-closed para subagentes: bloquearía el trabajo por un fallo de telemetría.
- Lock de archivo para la sesión: complejidad y riesgo de bloqueo en un hook; se acepta la pérdida de updates como limitación.
- Persistir `last_assistant_message`/transcript para auditoría: viola privacidad.
- Capturar tokens/costos: sin fuente en el payload.

## Riesgos
- **Hook dormant**: hasta que el humano aplique el snippet, no hay telemetría ni tope por `agent_id`; riesgo de que se interprete B-17/B-18 como cerrados en runtime. Mitigación: estado "implementado, activación pendiente", Doctor WARN con snippet, N/A explícito en efficiency.
- **Upgrade de instalaciones existentes**: las entradas VERBATIM del manifest llegan vía `settings_merge`; riesgos: duplicación en upgrades repetidos, pisar hooks del usuario, y que el manifest declare algo que cambie el hash managed esperado de `.claude/settings.json` de este repo (que no se modifica). Mitigación: tests de merge idempotente y de preflight de `upgrade` sobre settings sintético (T6), y verificación en T4 de que `test_manifest` no exige un `settings.json` modificado; si el manifest obligara a cambiar el settings de este repo, el writer devuelve `blocked` al Lead en vez de tocarlo.
- **SubagentStart en reanudación por `SendMessage` no observado**: no se verificó si el evento se dispara al reanudar; `arranques` tras reanudación puede quedar subcontado. Documentado como no observado en la matriz (B-18); el tope de continuaciones no depende de eso (lo incrementa `hook_presupuesto`).
- **Cambio de payload en versiones futuras de Claude Code** (evidencia con 2.1.310): fail-open + lista blanca + fixtures versionados; un campo ausente solo deja de registrar.
- **Pérdida de updates concurrentes**: telemetría, documentada.
- **Tests rojos transitorios de hashes managed** hasta C7 (D6): se coordinan con el Lead.
- **Tests que fijan la salida de efficiency/CLI** pueden romperse con claves nuevas; T7 los ajusta.
- **Clave por rol vs. por `agent_id` en `subagentes`**: riesgo de doble conteo; ver coexistencia.

## Aprobación humana
<!-- El registro de aprobación (usuario, fecha, alcance, versión de artefactos, cita) es único
por cambio y vive en la sección "Aprobación" de proposal.md — no se duplica acá. -->

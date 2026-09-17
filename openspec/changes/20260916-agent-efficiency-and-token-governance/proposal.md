# Proposal — 20260916-agent-efficiency-and-token-governance

## Contexto (audit primero — hallazgo clave)

Auditoría directa de `tools/dsguard/sdd.py` encuentra que buena parte de las "señales candidatas"
que pide el roadmap **ya se calculan y ya se persisten**, solo que nunca se agregan/re-exponen para
revisión retrospectiva:

- `chequear_limites(sesion)` ya detecta sesión que excede tareas/roles/reintentos/rondas/tiempo
  (`SESION-LIMITE-*`) — pero solo se llama sobre la sesión ACTIVA (`cmd_validate`,
  `cmd_session_status`), nunca sobre sesiones ya cerradas.
- `control["remediaciones"][].ventanas[].intentos[]` ya registra `causa`/`cambio_aplicado`/
  `resultado`/`attempt` de cada intento de remediación, y `REMEDIACION-LIMITE` ya bloquea un intento
  nuevo cuando se agota una ventana — pero nada agrega "¿cuántas remediaciones de este change
  llegaron al límite?" para revisión posterior.
- `control["sesiones"][].subagentes` existe en el schema (inicializado `{}` en `session_start`) pero
  **nunca se popula en ningún lugar del código** — es un campo muerto, no una fuente de datos real.

Esto define el alcance real y seguro de este Change: **un reporte de solo lectura que agrega señales
YA EXISTENTES**, sin inventar un mecanismo nuevo de captura automática (que requeriría un hook nuevo
sobre `Agent`/`SendMessage`, con riesgo real de efectos colaterales/concurrencia — fuera de alcance,
ver "Fuera de alcance").

## Qué se construye

1. `tools/dsguard/efficiency.py`: reusa `sdd.chequear_limites` (no la duplica) para reevaluar
   CUALQUIER sesión (activa o cerrada) de un change contra su propio presupuesto declarado; agrega
   detección determinista (comparación textual, sin juicio semántico) de remediaciones que agotaron
   su ventana vigente o cuyos intentos consecutivos declaran la misma `causa` textual (proxy de
   "retry sin variación real" — el juicio semántico real de si eso es genuinamente repetitivo sigue
   siendo del Lead).
2. CLI: `python -m tools.ds_guard efficiency report --change-id <id> [--json]`, estrictamente
   read-only (nunca llama `session_note`/`remediation_note`/`escribir_control`).
3. Integración mínima en `methodology.md` (+ `.tmpl`): cuándo el Lead puede consultar el reporte
   (al cerrar un change, o si sospecha que una sesión se volvió ineficiente) — nunca obligatorio.

## Fuera de alcance (decisión explícita, no material pero sí de foco)

- **Captura automática de "agentes lanzados/rol/task-id/duración" vía un hook nuevo sobre
  `Agent`/`SendMessage`**: el campo `subagentes` del schema de sesión existe pero está muerto.
  Poblarlo automáticamente requeriría un `PostToolUse` (o `PreToolUse`) hook nuevo, con escritura a
  `control.json` en cada llamada a `Agent`/`SendMessage` (riesgo de concurrencia si corren varios
  agentes en paralelo, y un mecanismo de captura nuevo es, en espíritu, el mismo tipo de decisión
  arquitectónica material que Change 3 — no se toma unilateralmente). Se registra como deuda
  concreta para un change futuro que la pida explícitamente.
- Fork sin output / no-op agents: sin fuente de datos hoy (no hay registro de qué produjo cada
  invocación de `Agent`) — mismo motivo que el punto anterior.
- Billing exacto, token accounting inventado, optimizador autónomo, telemetry específica de
  proveedor como core: excluidos explícitamente por el roadmap.
- No se convierte en gate de nada (`validate`/`readiness`/`promote` no se tocan).

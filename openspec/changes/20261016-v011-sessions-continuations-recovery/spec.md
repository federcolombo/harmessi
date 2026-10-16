# Spec — 20261016-v011-sessions-continuations-recovery

**R1.** `core.SESSION_MINUTES_DEFAULT = 90` es la única definición funcional del literal. `core.minutos_restantes` (fallback), `sdd.session_start` (default de firma) y `ds_guard._BUDGET_DEFAULTS["session_minutes"]` la referencian. Un test falla si aparece otro `90` funcional como minutos de sesión en `tools/dsguard/*.py` o `tools/ds_guard.py`. La policy `autonomy.budgets.session_minutes` sigue siendo la fuente efectiva; valor 90 sin cambios.
**R2.** `session status` (texto y JSON) incluye `minutos_restantes` y, si `0 < restantes <= UMBRAL_AVISO_MINUTOS (10)`, `aviso` con texto accionable; si `<= 0`, `vencida: true`.
**R3.** Los comandos que cargan un Change con sesión activa y `restantes <= 10` emiten UNA línea `AVISO-SESION-POR-VENCER` por stderr (nunca por stdout, sin alterar `--json`), con el comando literal de pausa/cierre. Sin sesión activa o con tiempo suficiente: silencio.
**R4.** `session start --retomar` copia de la última sesión cerrada del Change (la de mayor índice) `rondas_revision`, `reintentos`, `roles`, `tareas` y, por subagente, `continuaciones`; agrega `retomada_de` (id). Sin sesión previa: error claro (exit 2). Sin `--retomar` el comportamiento actual no cambia. `--retomar` respeta `--minutos` y los demás límites nuevos.
**R5.** Los límites acotados se evalúan con los valores heredados (p. ej. rondas ya usadas), de modo que retomar no reinicia el ciclo de reviewer ni los reintentos.
**R6.** El mensaje de recuperación del hook de presupuesto (`mensaje_recuperacion`) usa `session start --change-id <id> --retomar` en el paso 3; sigue siendo un comando literal permitido por el allowlist del hook.
**R7.** Docs: `methodology.md` §30 (wall-clock, T1/tests/background cuentan, aviso, `--retomar`, uso operativo de `--minutos` largo sin cambiar la policy), `SKILL.md`, `verificador.md` y plantillas con paridad.
**R8.** Tests: constante única, umbral de aviso, vencimiento, `session status`, aviso por stderr, retomar con ciclo de reviewer/ownership preservado, retomar sin sesión previa, continuación de subagente heredada, mensaje del hook, y regresión de `session` existentes.

## Criterios de aceptación
- [ ] R1–R3 [ ] R4–R6 [ ] R7–R8

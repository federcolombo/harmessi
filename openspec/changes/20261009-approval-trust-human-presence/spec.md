# Spec — 20261009-approval-trust-human-presence

Change 2 de v0.10: Approval Trust / T1 Human-Presence Semantics. Este Change es audit + SDD; no incluye implementación. Los requisitos describen el contrato que verificará el Change de implementación. Decisión material resuelta por el humano el 2026-10-13: opción B (canal T1 llamado `console_confirmed`); ver design.md D13.

Contexto verificado del código actual:
- `ds_guard approve` y `ds_guard exec approve script|pytest|notebook` registran una entrada en `control["aprobaciones"]`.
- `--usuario` solo se valida contra emails; ningún hook niega hoy un `ds_guard approve` emitido por un agente.
- El hash del artefacto aprobado sale de `hash_lf_v1` (`sha256/lf/v1`) o del builder correspondiente; no se toca.
- `tools/cards/approvals.py` resuelve ApprovalRef a los estados verified / stale / missing / unresolvable.

## A. Tiers y semántica (R1-R6)
**R1.** Tiers finales de confianza de una aprobación:
- T0 `declared`: la persona declaró la aprobación (con `--usuario` como metadata declarada). La ausencia de `approval_channel` equivale a T0 legacy `declared`. Las aprobaciones históricas siguen siendo válidas sin reescribirlas.
- T1 `console_confirmed`: señal de presencia interactiva; confirmación interactiva explícita recibida mediante una consola de control soportada durante el registro, para esa operación específica.
- T2: provider enforcement; evolución futura documentada, NO se implementa.
- T3: fuera de alcance.

**R2.** Texto normativo obligatorio en el contrato y en la documentación de usuario (inglés y castellano, mismo significado):
- «A `console_confirmed` approval means that a declared approval was accompanied by an interactive confirmation received through a supported control console for that specific operation. It does not prove the identity or authorship of the declared user and is not resistant to a deliberately synthesized local console input.»
- «una aprobación declarada con ese metadata fue acompañada por una señal T1 de presencia interactiva; Harmessi NO verificó que la persona declarada haya realizado físicamente esa aprobación.»

**R3.** T1 es una señal de presencia interactiva. NO es identidad ni autoría verificadas, firma, no-repudio, ni resistencia a un agente deliberado que sintetice input de consola, a malware, a administrador ni a root.

**R4.** T1 no es autorización ni RBAC: no decide quién puede aprobar qué.

**R5.** `--usuario` sigue siendo metadata declarada en cualquier tier; T1 no la valida.

**R6.** No se acepta ni se documenta ningún alias de canal anterior: el único valor T1 es `console_confirmed`.

## B. Primitive única de presencia (R7-R16)
**R7.** Existe un único módulo `tools/dsguard/human_presence.py`: solo stdlib, core neutral, sin protocolo de provider, sin dependencias nuevas.

**R8.** Firma: `solicitar_confirmacion(contexto, *, canal=None, timeout_s=120) -> ResultadoPresencia`, con `contexto = {change_id, artefacto, hash, accion}`.

**R9.** Challenge efímero single-use: código aleatorio generado con `secrets`, ligado a change / artefacto / hash / acción y mostrado en el canal de control. No es secreto (el agente puede leer stdout); la garantía proviene de la entrada recibida por la consola de control.

**R10.** La respuesta se lee SOLO del canal de control, nunca de `sys.stdin`, argumentos, archivo ni variable de entorno. `stdin.isatty()` nunca es criterio suficiente.

**R11.** Windows: consola real con `CONIN$` / `CONOUT$`, verificando ventana de consola presente (`GetConsoleWindow() != 0`) y modo de consola válido. Si el runtime no cumple (sin ventana de consola real) falla cerrado.

**R12.** POSIX: terminal de control real (`/dev/tty`) más las comprobaciones del diseño (p. ej. `os.tcgetpgrp` igual al grupo de procesos propio). Sin terminal de control falla cerrado. Se documenta que NO evita un PTY sintético.

**R13.** Inyección de dependencia: el parámetro `canal` permite tests con un canal falso sin tocar la consola real.

**R14.** Timeout configurable (default 120 s).

**R15.** Respuesta incorrecta, EOF, timeout o ausencia de canal producen fallo cerrado con motivo claro y código de salida 2. Nunca se degrada a `declared` y no se escribe nada.

**R16.** Single-use: un segundo intento de lectura con el mismo challenge falla (replay). Resultado: `{ok, canal="console_confirmed", confirmed_at (UTC), channel_version="console/v1", motivo}`.

## C. Registro (R17-R24)
**R17.** Campos aditivos en la entrada de `control["aprobaciones"]`: `approval_channel="console_confirmed"` (solo T1), `confirmed_at`, `channel_version="console/v1"`.

**R18.** Las aprobaciones T0 nuevas NO escriben `approval_channel`: conservan la forma histórica byte a byte. Una aprobación sin `approval_channel` es T0 legacy `declared`.

**R19.** No se persiste el challenge, la respuesta, teclas, usuario del SO, handles ni id de terminal.

**R20.** Un único helper de registro con una sola semántica de canal, compartido por `ds_guard approve` y `ds_guard exec approve script|pytest|notebook`.

**R21.** Flag `--channel {declared,console_confirmed}` (default `declared`). `--channel console_confirmed` sin canal soportado termina con exit 2 y sin escritura. El flag por sí solo NUNCA produce T1.

**R22.** El hash del artefacto se calcula como hoy (`hash_lf_v1` / builder). Cambiar proposal / spec / design / comando tras aprobar invalida la aprobación exactamente igual que hoy; el challenge NO reemplaza al hash.

**R23.** El mensaje del comando indica el nombre y las limitaciones de T1 (ver sección G).

**R24.** La inyección sintética de consola (pty en POSIX; `WriteConsoleInputW` o nueva consola con `AttachConsole` en Windows) queda registrada como: «not empirically exercised; explicitly outside T1 guarantee». El intento de probarla fue denegado por el clasificador de permisos del entorno; no se rodea ni se necesita.

## D. Resolución (R25-R29)
**R25.** `tools/cards/approvals.py` expone el canal de la aprobación resuelta como dato de solo lectura (campo aditivo en el resultado): `declared` si falta o el valor es desconocido.

**R26.** Los estados verified / stale / missing / unresolvable no cambian.

**R27.** `ApprovalRef` no cambia de forma y nunca declara su propio tier; el canal se resuelve desde la aprobación real.

**R28.** `HumanAttestation` no crea ni eleva el tier (no añade campos de canal). `NOTA_ANCHOR` se actualiza: un ancla puede exponer el tier de la aprobación pero sigue sin probar identidad.

**R29.** Valor de canal desconocido nunca cuenta como T1 (fail-closed para cualquier consumidor que exija T1).

## E. Alcance de T1 (R30-R34)
**R30.** Change 2 aplica a `approve` y `exec approve`. `decision` y `remediation` quedan T0 (fuera de alcance; nota de deuda).

**R31.** Sin policy global ni clave nueva en `guardrails.json`; no se amplía `RUTAS_MUTABLES`.

**R32.** Change 3 será el primer consumidor obligatorio de T1.

**R33.** Autonomía: el agente lleva todo hasta el checkpoint; cuando se exige T1 es un STOP humano real, y luego la autonomía continúa.

**R34.** `!` del provider NO es T1 automáticamente: depende del canal observado. Un subproceso no interactivo falla; no se infiere presencia por quién escribió el comando. Sin hooks ni heurísticas para «detectar al agente» y sin adapters de provider.

## F. Provider-neutral (R35)
**R35.** Sin dependencia de UI / CLI / MCP de ningún provider de agentes. T2 (provider enforcement) queda como evolución futura documentada.

## G. Límites explícitos (R36-R38, sección obligatoria)
**R36.** T1 detiene: `--yes` y otros flags, `--usuario`, stdin redirigido, pipes, archivos, variables de entorno, subprocesos no interactivos y los runtimes de agente observados.

**R37.** T1 NO resiste: entrada sintética deliberada (pty en POSIX; `WriteConsoleInputW` o nueva consola con `AttachConsole` en Windows; automatización de accesibilidad; inyección de procesos), administrador/root, SO comprometido ni malware.

**R38.** T1 no es un boundary criptográfico. Este texto debe aparecer en la documentación de usuario.

## H. Tests a prever (R39-R55)
**R39.** T0: aprobación histórica sin canal; `declared` explícito leído sin error; `--usuario` no prueba T1.

**R40.** El flag `--channel console_confirmed` por sí solo nunca produce T1.

**R41.** T1 éxito con canal inyectado: challenge correcto; binding a change / artefacto / hash / acción; single-use (segunda lectura con el mismo challenge falla).

**R42.** T1 fail-closed: stdin por pipe, archivo redirigido, DEVNULL, sin consola, EOF, timeout, respuesta incorrecta, replay.

**R43.** Subproceso no interactivo real `python tools/ds_guard.py approve ... --channel console_confirmed` con stdin por pipe, ejecutado desde el test: exit 2 y sin escritura.

**R44.** Mutación del artefacto tras T1: la aprobación queda stale / inválida.

**R45.** Compatibilidad histórica: control con aprobaciones sin canal sigue verificando.

**R46.** ApprovalRef resuelve el canal desde la aprobación real; Cards no inventan T1; canal desconocido se lee como `declared` y no satisface T1.

**R47.** Contratos Windows y POSIX separados: tests de plataforma con skip por `sys.platform` y fakes de las llamadas de consola.

**R48.** `approve` y `exec approve` comparten helper.

**R49.** Privacidad del registro: sin challenge, respuesta, teclas, usuario del SO, handles ni id de terminal.

**R50.** `human_presence.py` solo stdlib y sin imports de provider (test de boundaries, `test_architecture_boundaries.py`).

**R51.** Aceptación manual humana obligatoria (no automatizable), con un Change temporal descartable: el usuario corre `ds_guard approve --channel console_confirmed` en su terminal real y funciona.

**R52.** Aceptación manual humana: el mismo comando desde la herramienta de shell del agente falla cerrado.

**R53.** Aceptación manual humana: el mismo comando vía `!` del provider se evalúa según el canal observado (se espera fallo cerrado por subproceso no interactivo).

**R54.** Verificación POSIX en un host POSIX (no probado en el audit, que corrió en Windows). Terminales ConPTY / Windows Terminal / editor integrado: a verificar en la aceptación manual.

**R55.** Verificación del Change de implementación: tests dirigidos por writer, reviewer con máximo 2 ciclos, regresión relevante (sin full regression), `git diff --check` y revisión de privacidad. Sin nombres de proyectos reales, rutas personales ni emails.

## Fuera de alcance explícito
- Implementación en este Change.
- T2 (provider enforcement, adapters de provider, hooks para detectar al agente) y T3.
- T1 en `decision` y `remediation`.
- Policy global o clave nueva en `guardrails.json`; ampliar `RUTAS_MUTABLES`.
- Obligar T1 a algún consumidor (Change 3).
- Cambiar `hash_lf_v1`, la forma de `ApprovalRef` o de `HumanAttestation`.
- Validar identidad, autoría, no-repudio o firma.
- Reescribir aprobaciones históricas.

## Criterios de aceptación
- [ ] R1-R6: tiers y semántica especificados, con el texto normativo de R2 en inglés y castellano.
- [ ] R7-R16: primitive de presencia con canal de control, challenge single-use y fallo cerrado.
- [ ] R17-R24: registro aditivo, helper único, flag `--channel` y hash sin cambios.
- [ ] R25-R29: exposición de solo lectura en Cards sin alterar estados.
- [ ] R30-R35: alcance de T1 y neutralidad de provider.
- [ ] R36-R38: límites explícitos documentados.
- [ ] R39-R55: tests, aceptación manual y verificación listados.
- [ ] Sin código funcional modificado en este Change.

## Unidad de análisis / grain (condicional — data_understanding, feature_engineering, modeling)
No aplica (Change documental sin datos).

## Cutoff / information boundary (condicional — feature_engineering, data_preparation, modeling)
No aplica.

## Baseline (condicional — modeling)
No aplica.

## Métrica primaria (condicional — modeling, evaluation)
No aplica.

## Métricas secundarias (opcional)
No aplica.

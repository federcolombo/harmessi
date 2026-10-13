# Propuesta — 20261009-approval-trust-human-presence

> Change 2 de v0.10 («Integration & Stabilization + Composable Data Science Skills»), roadmap en `docs/roadmap/v0.10.md`. Cubre
> «Approval Trust / T1 Human-Presence Semantics» (decisión M1 de Change 0: T1 como señal de presencia, NO identidad; nombre final
> `console_confirmed`, ver «Decisión aprobada»). Es audit + SDD únicamente: NO implementa nada.

## Problema
Toda aprobación de Harmessi es hoy «declarada» (T0): `ds_guard approve` acepta cualquier `--usuario` (el único control es
`core.validar_usuario_sin_email`, que rechaza `@`) y ningún hook niega `ds_guard approve` emitido por un agente. Un agente con acceso a
Bash puede registrar una aprobación declarando cualquier usuario, y el registro resultante es indistinguible del de una persona. No existe
ninguna señal que diferencie «una persona interactuó» de «un proceso escribió la aprobación».

## Objetivo
Agregar una señal de presencia interactiva (T1, `console_confirmed`) más fuerte que `declared`, opt-in, sin prometer identidad ni
autorización, y con límites documentados con honestidad.

## Evidencia
Medida el 2026-10-13 en Windows 11, Python 3.12, con las herramientas Bash y PowerShell del agente de Claude Code. Código citado del
working tree de `v0.10-dev`.

### Superficies de aprobación actuales
- `ds_guard approve` (artefactos SDD): `tools/ds_guard.py::cmd_approve`, l.325-447. Escribe en `control["aprobaciones"]` la entrada
  `{artefacto, algoritmo, hash, registrado_utc, usuario, fecha_declarada, alcance_aprobado, cita}`.
- `ds_guard exec approve script|pytest|notebook`: `_registrar_aprobacion_exec`, misma estructura; el hash lo calcula el builder, nunca el
  humano.
- `ds_guard decision add|supersede|revoke` y `remediation extend|resolve`: llevan `--usuario` en el ledger/control, sin ApprovalRef.
- Checkpoints de negocio con `@approved`: se resuelven contra la aprobación real de `proposal.md`.
- `autonomy.human_approval_ref` / `approval_ref`: `tools/autonomy/core.py::_validar_ref` (`{change_id, artefacto, hash}`).
- Cards: `HumanAttestation` declared|anchored (`tools/cards/core.py`) y `tools/cards/approvals.py` (resuelve ApprovalRef a
  verified/stale/missing/unresolvable leyendo `aprobaciones`, solo lectura; su `NOTA_ANCHOR` ya dice que no prueba identidad, presencia ni
  no-repudio).
- Consumidores de `aprobaciones`: `dsguard/sdd.py` (más reciente por artefacto, `_aprobacion_mas_reciente`), `nbrunner/manifest.py`,
  `notebook_runner.py` y el runtime de exec.

### Medición del entorno del agente (Windows)
- `sys.stdin.isatty()` da **True** dentro del comando del agente aunque no haya terminal humano: `GetConsoleWindow()==0`,
  `GetConsoleMode(stdin)==0` (el stdin heredado es el dispositivo NUL, que en Windows reporta isatty True). `stdout/stderr` dan False.
  Mismo resultado en Bash y PowerShell. Conclusión: `isatty()` NO distingue humano de agente y queda prohibido como criterio suficiente.
- El agente corre en una consola privada de ese comando (`GetConsoleProcessList` devolvió 4 procesos propios). `CONIN$` y `CONOUT$` se
  abren desde el agente; `CreateFileW('CONIN$', GENERIC_READ|GENERIC_WRITE)` devuelve handle válido, `GetConsoleMode(CONIN$)` es válido
  (0x1f7) y `GetNumberOfConsoleInputEvents` funciona.
- Implicancias: un `ds_guard` que lea `CONIN$` no obtendría nada de un humano (esperaría en una consola privada: bloqueo, no
  aprobación). Pero el buffer de entrada de esa consola es escribible por el agente (`WriteConsoleInputW`), de modo que una entrada
  sintética deliberada es técnicamente posible.
- **Limitación de la evidencia**: la inyección sintética de consola NO se ejercitó empíricamente (el intento fue denegado por el
  clasificador de permisos del entorno y no se rodea). Queda como análisis de la API: *not empirically exercised; explicitly outside T1
  guarantee*.

### POSIX (NO probado: el host es Windows)
Análisis, no medición. Un comando lanzado con pipes y sin sesión de terminal no tiene terminal de control (`open('/dev/tty')` falla con
ENXIO). Pero un runtime que ejecute comandos bajo un pseudo-terminal (algunos modos de CLIs de agentes) sí lo tendría, y con stdlib
(`pty`) un agente puede crear un pty y alimentar la respuesta. Debe verificarse en un host POSIX durante la implementación.

### Atajo `!` del provider
NO se considera T1 automáticamente: depende del canal observado. Se espera que corra como subproceso no interactivo del propio runtime
(mismo entorno que la herramienta Bash, sin ventana de consola); en ese caso debe fallar cerrado. A verificar manualmente en la
aceptación. El camino humano esperado es el terminal propio del usuario.

## Supuestos descartados
1. `isatty()` como criterio de presencia humana: da True dentro del comando del agente (medido).
2. Que leer `CONIN$` baste para impedir la aprobación sintética: bloquea ante un humano ausente, pero el buffer es escribible por el
   agente (análisis de API; sin demostración empírica).
3. Que `--usuario` aporte alguna garantía: solo se rechaza `@`.
4. Que un challenge sea un secreto: el agente puede leer stdout; la garantía NO viene del challenge sino del canal de la respuesta.
5. Que POSIX sea «seguro por defecto»: un runtime con pty cambia la conclusión (sin probar).
6. Que el nombre `tty_confirmed` fuera adecuado: sugiere una terminal verificada; el mecanismo solo evidencia una consola de control
   soportada (ver «Decisión aprobada»).

## Hipótesis (condicional — solo cambios metodológicos)
No aplica: es un cambio de infraestructura/confianza, no prueba una hipótesis sobre datos.

## Alcance
Una primitive única `tools/dsguard/human_presence.py` (solo stdlib, core neutral, sin protocolo de provider) usada por `approve` y
`exec approve` mediante un único helper de registro; exposición de solo lectura del canal en Cards; tests; documentación.

### Tiers de confianza (finales)
| Tier | Canal | Qué significa | Qué NO aporta |
|---|---|---|---|
| T0 | `declared` | Existe una declaración registrada; `usuario` es metadata declarada | Presencia, identidad, autoría, no-repudio |
| T1 | `console_confirmed` | Una aprobación declarada fue acompañada por una confirmación interactiva específica para esa operación, recibida mediante una consola de control soportada; aporta una interactive-presence signal | Identidad/autoría verificadas, firma, no-repudio; resistencia a un agente deliberado que sintetice input de consola; resistencia a malware/admin/root |
| T2 | provider enforcement | FUTURO: adapter del provider que niegue `ds_guard approve` emitido por un agente. NO se implementa en este Change | — |
| T3 | PKI/firmas | Fuera de alcance | — |

### Decisión técnica (resumen; el detalle va en `design.md`)
- **Mecanismo.** Harmessi genera un challenge efímero (código aleatorio de un solo uso ligado a change, artefacto, hash y acción), lo
  muestra en el canal de control y lee la respuesta SOLO del dispositivo de consola de control, nunca de stdin, argumentos, archivo ni
  variable de entorno. Con timeout.
  - Windows: `CONIN$`/`CONOUT$` con chequeos de entorno (ventana de consola presente y modo de consola válido).
  - POSIX: `/dev/tty` con chequeo de grupo de proceso en primer plano.
- **Fallo cerrado.** Sin canal soportado se aborta; NO se degrada a `declared` (sin fallback T1→T0).
- **El challenge no es secreto.** La garantía viene de que la respuesta debe ingresarse por el canal de control, que un proceso no
  interactivo no recibe como entrada ordinaria. Challenge de un solo uso, sin replay.
- **Interfaz.** `--channel {declared,console_confirmed}` en `approve` y `exec approve` (default `declared`). Sin aliases ni
  compatibilidad con `tty_confirmed`: nunca se publicó.
- **Registro aditivo** en la entrada de `aprobaciones[]`: `approval_channel` (ausente = `declared`), `confirmed_at` (UTC),
  `channel_version` (`console/v1`). No se persiste el challenge, la respuesta, datos del terminal ni usuario del SO.
- **ApprovalRef sin cambios.** `tools/cards/approvals.py` expone el canal de la aprobación resuelta como dato de solo lectura sin alterar
  los estados verified/stale/missing/unresolvable. Cards/HumanAttestation no inventan T1.
- **Sin policy global.** T1 es opt-in; no se agrega clave nueva a `guardrails.json` (evita ampliar el drift semántico).
- **Primer consumidor obligatorio.** Change 3 (scope amendment y re-adopción de guardrails) exigirá T1 por diseño para impedir la
  auto-adopción por un agente. `decision` y `remediation` quedan en T0. Sin RBAC ni cuentas.

### Texto normativo obligatorio (docs y contrato)
- EN: «A `console_confirmed` approval means that a declared approval was accompanied by an interactive confirmation received through a
  supported control console for that specific operation. It does not prove the identity or authorship of the declared user and is not
  resistant to a deliberately synthesized local console input.»
- ES: «una aprobación declarada con ese metadata fue acompañada por una señal T1 de presencia interactiva; Harmessi NO verificó que la
  persona declarada haya realizado físicamente esa aprobación.»

### Límites explícitos
- T1 detiene: flags (`--yes`, `--usuario`), stdin redirigido, pipes, archivos, variables de entorno, subprocesos no interactivos y los
  runtimes de agente observados.
- T1 NO resiste: entrada sintética deliberada (pty, `WriteConsoleInputW`, automatización de accesibilidad, inyección de procesos),
  administrador/root ni malware. La inyección sintética no se ejercitó empíricamente: *not empirically exercised; explicitly outside T1
  guarantee*.
- No prueba identidad ni autoría. No es autorización ni RBAC.

### Decisión aprobada (2026-10-13): B — `console_confirmed`
El audit encontró que una señal sintética deliberada es posible con ~15 líneas de stdlib (análisis de API; no demostrada aquí). El autor
resolvió la decisión material con la opción B. El nombre describe la evidencia: «una confirmación interactiva fue recibida mediante una
consola de control soportada para esa operación».
- Se mantiene T1 (NO se queda en T0).
- NO se implementa T2 (provider enforcement): se documenta como evolución futura y patrón de adapter.
- T3 fuera de alcance.
- Registro de las opciones consideradas: A (`tty_confirmed`, descartada por nombre que sobre-promete), **B (`console_confirmed`,
  elegida)**, C (A + T2 mínimo, no elegida), D (mantener T0, no elegida).

### Archivos previstos
| Archivo | Cambio |
|---|---|
| `tools/dsguard/human_presence.py` (nuevo) | primitive de presencia (challenge, canal de control, timeout, fail-closed) |
| `tools/ds_guard.py` | flag `--channel` en `approve` y `exec approve`; helper único de registro |
| `tools/cards/approvals.py` | exposición de solo lectura del canal |
| `tools/tests/test_human_presence.py` (nuevo) | tests de la primitive |
| `tools/tests/test_approval_channel_cli.py` (nuevo) | tests de CLI y registro |
| `tools/tests/test_ds_guard_exec_approve.py`, `tools/cards/tests/test_approvals*.py` | ajustes si hace falta |
| `tools/tests/test_architecture_boundaries.py` | boundaries del módulo nuevo (solo stdlib) |
| `ARCHITECTURE.md` | nota de T1, límites y patrón T2 futuro |
| `docs/roadmap/v0.10.md` | estado del Change 2 |
| `.claude/skills/lead-data-scientist/sdd.md` | solo si hace falta (línea sobre STOP humano cuando se exige T1); incluido en el alcance autorizado |

## Fuera de alcance
Hashing managed, scope amendment, re-adopción de guardrails, domain modeling, writer semantics, `ds_profile`, policy engine, RBAC,
cuentas, PKI/firmas (T3), T2 (provider enforcement), `decision`/`remediation`, cambios al formato de ApprovalRef.

## Holdout policy (condicional — solo cambios "sensible")
No aplica: no se toca ningún holdout ni dataset sellado.

## Impacto en production-readiness (opcional)
Ninguno directo.

## Criterios de aceptación (spec-lite — solo SDD abreviado)
Ver `spec.md` (SDD completo).

## Decisión técnica (design-lite — solo SDD abreviado)
Ver `design.md` (SDD completo).

## Aprobación
- Usuario: Federico Colombo
- Fecha: 2026-10-13
- Alcance aprobado: Implementación y validación de Change 2 Approval Trust / T1 Human-Presence
- Versión de artefactos referenciada: proposal.md/spec.md/design.md vigentes al momento del hash
- Cita o descripción fiel de qué se aprobó: «Aprobación humana explícita del SDD de Change 2; T1 se denomina console_confirmed y representa una señal interactiva de presencia, no identidad»

## Alcance autorizado

- tools/dsguard/human_presence.py
- tools/ds_guard.py
- tools/cards/approvals.py
- tools/tests/test_human_presence.py
- tools/tests/test_approval_channel_cli.py
- tools/tests/test_ds_guard_exec_approve.py
- tools/cards/tests/**
- tools/tests/test_architecture_boundaries.py
- ARCHITECTURE.md
- docs/roadmap/v0.10.md
- .claude/skills/lead-data-scientist/sdd.md

## Motivo de rechazo
<!-- completar solo si estado: descartada -->

## Desacuerdo registrado
<!-- completar solo si estado: pausada_bloqueada tras 2 rondas de revisión sin acuerdo -->

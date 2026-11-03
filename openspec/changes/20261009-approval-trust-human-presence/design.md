# Diseño — 20261009-approval-trust-human-presence

Diseño del Change 2 de v0.10 (Approval Trust / T1 Human-Presence Semantics). Audit + SDD; sin implementación. Refina la decisión M1 de Change 0 (`docs/roadmap/v0.10.md`, `ARCHITECTURE.md` §7.1). El humano aprobó el SDD y resolvió la decisión material (D13) el 2026-10-13: opción B, canal `console_confirmed`.

## Decisión metodológica/técnica

### D1. Por qué `isatty()` no sirve (evidencia medida)
Medido el 2026-10-13 en Windows 11 con Python 3.12, desde las herramientas de shell del agente:
- `sys.stdin.isatty()` es True dentro del comando del agente aunque no hay terminal humano: `GetConsoleWindow() == 0`, `GetConsoleMode(stdin) == 0`, stdin es NUL, que en Windows reporta isatty True.
- stdout y stderr reportan isatty False.
- El agente corre en una consola privada del comando (`GetConsoleProcessList` = 4 procesos propios).
- `CONIN$` y `CONOUT$` se abren; `CreateFileW('CONIN$', GENERIC_READ|GENERIC_WRITE)` da un handle válido con `GetConsoleMode` válido (0x1f7). Leer `CONIN$` desde el agente no recibiría input humano (esperaría).
- Conclusión: `isatty()` da un falso positivo; la presencia no se puede inferir de él. Hace falta una señal positiva (una confirmación leída del canal de control), no la ausencia de redirección.

### D2. Modelo de amenaza de T1
- Adversario considerado: agente no interactivo, prompt-injected o descuidado que invoca `ds_guard approve` por una vía automatizada. No se considera usuario malicioso, root ni malware.
- T1 resiste: `--yes` y flags, `--usuario`, stdin redirigido, pipes, archivos, variables de entorno, subprocesos no interactivos y los runtimes de agente observados.
- T1 no resiste: entrada sintética deliberada (pty en POSIX; `WriteConsoleInputW` o nueva consola con `AttachConsole` en Windows; automatización de accesibilidad; inyección de procesos), administrador/root, SO comprometido, malware.
- El buffer de entrada de la consola del agente es escribible por el agente (`WriteConsoleInputW`), de modo que una entrada sintética deliberada es posible por análisis de la API. El intento de probarlo con una escritura real fue denegado por el clasificador de permisos del entorno y no se reintentó: la capacidad NO está demostrada empíricamente.
- Registro: «not empirically exercised; explicitly outside T1 guarantee» para la inyección sintética de consola; no se rodea el clasificador ni se necesita.
- Nombre y semántica: señal de presencia interactiva (`console_confirmed`). Nunca identidad, autoría, no-repudio ni firma. Texto normativo en spec R2 (inglés y castellano): «una aprobación declarada con ese metadata fue acompañada por una señal T1 de presencia interactiva; Harmessi NO verificó que la persona declarada haya realizado físicamente esa aprobación.»

### D3. Challenge efímero y su visibilidad
- Código aleatorio con `secrets`, single-use, ligado a change / artefacto / hash / acción y mostrado en el canal de control.
- El agente puede leer stdout, así que el challenge no es secreto. No lo necesita ser: lo que se verifica es que la respuesta llegue por el canal de control, que un proceso no interactivo no recibe como entrada ordinaria. El challenge evita confirmaciones ciegas (Enter automático) y liga la confirmación a un acto concreto; no sustituye al hash del artefacto.
- Single-use: la segunda lectura con el mismo challenge falla.

### D4. Canal Windows
- Se abre `CONIN$` / `CONOUT$` después de verificar ventana de consola presente (`GetConsoleWindow() != 0`) y modo de consola válido. Solo abrir `CONIN$` no basta (D1: se abre y es válido desde el agente); la ventana de consola es el chequeo discriminante medido.
- Por qué no `msvcrt.getwch` sobre stdin: depende del stdin del proceso, que puede ser NUL, un pipe o un archivo; no ata la lectura al canal de control.
- Riesgo: entrada sintética con `WriteConsoleInputW` / `AttachConsole`, no demostrada empíricamente aquí (D2).
- Terminales ConPTY / Windows Terminal / editor integrado: a verificar en la aceptación manual. Un falso negativo se resuelve con fallo cerrado y `declared` sigue disponible.

### D5. Canal POSIX
- `/dev/tty` más `os.tcgetpgrp` igual al grupo de procesos propio (el proceso tiene terminal de control y está en primer plano).
- Sin terminal de control, `open('/dev/tty')` falla con ENXIO (esperado; no probado en este host, que es Windows) y el registro falla cerrado. Se documenta que NO evita un PTY sintético.
- Riesgo: un runtime bajo pty sí tendría `/dev/tty`, y con `pty` de stdlib un agente puede fabricar uno. Es el análogo POSIX de D4 y entra en los límites de D2.
- Verificación en un host POSIX durante la aceptación manual.

### D6. Modelo de datos
- Campos aditivos en la entrada de `control["aprobaciones"]`: `approval_channel="console_confirmed"` (solo T1), `confirmed_at`, `channel_version="console/v1"`. Sin aliases ni compatibilidad con nombres anteriores (nunca se publicaron).
- `approval_channel` pertenece al registro de aprobación y no a `ApprovalRef`: el ref es una referencia (apunta a una aprobación), no una declaración; si llevara el canal, un ref podría afirmar un tier que la aprobación no tiene. El canal se resuelve desde la aprobación real.
- No se escribe `declared` explícito en T0 nuevos: la forma histórica se mantiene byte a byte, y la ausencia de campo es la forma canónica de T0 legacy `declared`. Un `declared` explícito se lee igual que la ausencia.
- Un valor desconocido se trata como `declared` y nunca satisface T1.

### D7. Helper único
- `approve` y `exec approve script|pytest|notebook` comparten un helper de registro; evita que cada comando tenga su propia semántica de canal.
- El flag `--channel` es solo la solicitud; la señal T1 la produce `human_presence.solicitar_confirmacion`. Sin canal soportado: exit 2 y sin escritura.

### D8. Exposición en Cards (solo lectura)
- `tools/cards/approvals.py` añade el canal al resultado de resolución como dato de solo lectura. Los estados verified / stale / missing / unresolvable no cambian y `ApprovalRef` conserva su forma.
- `HumanAttestation` no gana campos de canal (no inventa T1). `NOTA_ANCHOR` se actualiza: un ancla puede exponer el tier, pero no prueba identidad.

### D9. Sin policy nueva
Motivos:
- compatibilidad con CI y ejecuciones headless, donde T1 no puede existir y `declared` sigue siendo el modo normal;
- evitar ampliar la closed-list de guardrails (`RUTAS_MUTABLES`) y sumar una clave nueva en `guardrails.json`;
- el primer consumidor real de T1 llega con Change 3; definir policy antes de tener consumidor es especulativo.

### D10. `!` y provider shortcuts
- La semántica se define por el canal observado, no por el origen aparente del texto: lo que importa es si el proceso tiene un canal de control, no quién escribió el comando. `!` no es T1 automáticamente.
- Se espera que `!` lance un subproceso no interactivo del runtime (sin ventana de consola), por lo que falla cerrado. A verificar manualmente (spec R53); no hay evidencia medida.
- Sin hooks ni heurísticas para «detectar al agente» y sin adapters de provider en este Change.

### D11. Privacidad del registro
- No se persiste el challenge, la respuesta, teclas, datos del terminal, handles, id de terminal ni el usuario del SO. Solo `approval_channel`, `confirmed_at` (UTC) y `channel_version`.
- `--usuario` sigue siendo metadata declarada.

### D12. UX
- Un solo prompt corto con: change, artefacto, hash abreviado, acción y código. Una línea de respuesta.
- El mensaje incluye el nombre «señal de presencia» y sus límites, para no sobre-prometer.
- Al fallar, el motivo es claro y el código de salida es 2.

### D13. Decisión aprobada (2026-10-13): B — `console_confirmed`
Razón: el audit mostró que `isatty()` no demuestra presencia humana (en Windows es True incluso en el runtime del agente), que PTY / entrada de consola pueden sintetizarse deliberadamente (~15 líneas de stdlib; no demostrado empíricamente en este host porque el intento fue denegado por el clasificador de permisos) y que el mecanismo no es frontera criptográfica. Por eso el nombre debe describir exactamente la evidencia: «una confirmación interactiva fue recibida mediante una consola de control soportada para esa operación».

Consecuencias:
- Se mantiene T1 con el nombre `console_confirmed` (`channel_version="console/v1"`). NO se queda en T0.
- NO se implementa T2: el provider enforcement es evolución futura documentada. T3 fuera.
- «T1 obligatorio por policy» no fue opción (D9; el primer consumidor obligatorio será Change 3).

Registro histórico de las opciones consideradas:
- A. T1 opt-in con un nombre que aludía a un TTY, garantía modesta. Descartada por el nombre: sugiere un TTY verificado que el audit no puede garantizar.
- B. T1 con nombre más modesto (`console_confirmed`). ELEGIDA: misma garantía y costo que A, con un nombre que no sobre-promete.
- C. A más un T2 mínimo (adapter del provider que niegue `ds_guard approve` emitido por un agente). No elegida: específica de provider y evadible por ofuscación mientras no exista el hook estricto de Bash del Lead diferido de v0.8. Se reevaluará tras Change 3.
- D. Mantener T0 en v0.10. No elegida: Change 3 quedaría sin base para impedir la auto-adopción por un agente.

## Target (condicional — feature_engineering, modeling)
No aplica (Change documental).

## Features permitidas/prohibidas (condicional — feature_engineering)
No aplica.

## Estrategia de split/validación (condicional — holdout involucrado, modeling, evaluation)
No aplica; no se toca ningún holdout.

## Leakage risks (condicional — feature_engineering, data_preparation, modeling)
No aplica; sin datos ni features.

## Reproducibilidad (opcional — solo si se desvía del default: RANDOM_STATE fijo, .venv)
Sin desvíos. El challenge usa `secrets` por diseño (no reproducible, y no debe serlo); los tests lo fijan mediante el canal inyectado.

## Alternativas descartadas
- `sys.stdin.isatty()` como señal de presencia (D1: falso positivo medido).
- `msvcrt.getwch` / `input()` sobre stdin (D4).
- Confirmación solo con flag (`--yes`, `--channel` sin lectura de canal): el flag no puede producir T1.
- Escribir `approval_channel: declared` en T0 nuevos (rompe la forma histórica).
- Poner el canal en `ApprovalRef` o en `HumanAttestation` (D6, D8).
- Policy global o clave nueva en `guardrails.json` (D9).
- Persistir challenge, respuesta, teclas, handles, id de terminal o usuario del SO (D11).
- Nombre con alusión a TTY, T2 mínimo y permanecer en T0 (D13).

## Riesgos
- Sobre-promesa de seguridad: mitigada con nombre y limitaciones explícitas en docs y en el mensaje del comando.
- Falsos negativos en terminales atípicas (ConPTY, editor integrado, `!`): mitigados con fallo cerrado; `declared` sigue disponible.
- Diferencias de plataforma: mitigadas con contratos Windows y POSIX separados y aceptación manual en cada host. POSIX no probado.
- Entrada sintética deliberada (D2, D4, D5): límite aceptado y documentado; no demostrada empíricamente en Windows.
- Aprobaciones históricas T0 leídas como si tuvieran garantía: mitigado porque T0 sigue siendo `declared` y nada las promueve.

## Aprobación humana
<!-- El registro de aprobación (usuario, fecha, alcance, versión de artefactos, cita) es único
por cambio y vive en la sección "Aprobación" de proposal.md — no se duplica acá. -->
Ver `proposal.md`.

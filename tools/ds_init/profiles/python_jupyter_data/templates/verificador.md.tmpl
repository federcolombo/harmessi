# Verificador determinista (`ds_guard`) — referencia

Se lee bajo demanda, junto con `sdd.md` (y `kdd.md` para los comandos `kdd *`), cuando hace falta
correr o interpretar `ds_guard`. No se carga por defecto. Código real: `tools/ds_guard.py` +
`tools/dsguard/{core,repo,sdd,kdd,notebooks}.py`.

## 1. Qué es y qué no es

Verificación determinista **posterior** + scaffolding mecánico de transiciones/sesiones/
aprobaciones sobre los artefactos SDD (`tasks.md`, `control.json`) de un cambio en
`openspec/changes/<change-id>/`. Complementa, no reemplaza, los tres hooks `PreToolUse` reales
descritos abajo — cubre el alcance declarado por cambio (`control["alcance"]["rutas_autorizadas"]`)
y el resto de la mecánica SDD, que sigue siendo detección posterior (nadie impide técnicamente que
un archivo quede fuera de ese alcance en el momento de escribirlo; `ds_guard` solo lo señala al
cerrar el cambio). `init` bootstrapea `control.json` a partir de las plantillas de
`.claude/skills/lead-data-scientist/templates/`.

Primer hook: el agente `notebook-runner` (`.claude/agents/notebook-runner.md`) tiene un hook
`PreToolUse` real (`.claude/settings.json` + `tools/nbrunner/hook_launcher.py` +
`tools/nbrunner/hook_validar_comando.py`) que valida técnicamente su único comando Bash permitido
contra el manifest versionado antes de dejarlo correr. Ese bloqueo es exclusivo de ese agente y de
ese comando.

Segundo hook: `tools/dsguard/hook_presupuesto.py` + `tools/dsguard/hook_launcher_presupuesto.py`,
registrado en `.claude/settings.json` con `matcher: "Agent|SendMessage|Write|Edit|Bash|PowerShell"`.
Bloquea técnicamente, cuando hay una sesión de control activa (`sesiones[].estado_final == "activa"`
en algún `control.json` de `openspec/changes/*/`): `Agent` nuevo y `SendMessage` de continuación en
los últimos 5 minutos antes de `deadline_utc`, y — vencido `deadline_utc` — también `Write`/`Edit`/
`Bash`/`PowerShell`, salvo el allowlist (`git status`/`git diff` sin `--output`/`-o`, y
`ds_guard session note|status|close`). Cubre solo presupuesto/continuaciones de la sesión de
control, sin awareness de rutas. Fail-safe explícito: sin sesión activa, sin `control.json`
legible, o con `deadline_utc` ilegible, el hook permite siempre — nunca bloquea el repo por un dato
corrupto o ausente.

Tercer hook (Bloque 3, reliability v0.2.0): `tools/dsguard/hook_rutas.py` +
`tools/dsguard/hook_launcher_rutas.py` + `tools/dsguard/pathguard.py`, registrado con
`matcher: "Read|Grep|Edit|Write|NotebookEdit|Bash|PowerShell"` — corre siempre, con o sin sesión
activa, para **cualquier** llamador (Lead incluido). Bloquea técnicamente, contra
`.claude/guardrails.json`: secretos (lectura y escritura, siempre, sin excepción), holdouts
(escritura siempre, lectura salvo excepción explícita en `guardrails.json`), `data/raw` (escritura
denegada, lectura permitida), y el propio `guardrails.json` (protegido de `Write`/`Edit`/
`NotebookEdit`, y de un `Bash`/`PowerShell` que se detecte escribiéndolo). Garantía real para
`Write`/`Edit`/`NotebookEdit`/`Read`/`Grep` (ruta estructurada, resuelta con symlinks/`..`
incluidos); **best-effort, no equivalente**, para `Bash`/`PowerShell` (escaneo de texto, no un
parser de shell — no detecta indirección). `write_scopes` por agente es opt-in y vacío por
defecto; no aplica al Lead. Fail-closed explícito, al revés del hook de presupuesto: cualquier cosa
que no se pueda evaluar con certeza (`guardrails.json` corrupto, ruta no resoluble, error interno)
deniega, no permite.

## 2. Comandos

Todos requieren `--change-id <id>` y, salvo `approve`/`transition`/`archive`, aceptan `--json`
para salida estructurada. Exit codes generales: `0` correcto, `1` gate/validación incumplida
(incluye `SESION-AUSENTE`), `2` error de uso/configuración, `3` error de entorno/git/herramienta.

- **`status --change-id <id> [--json]`**: informativo, no falla nunca por contenido (siempre 0
  salvo error de entorno). Lee `estado:` de `tasks.md`, compara contra la última transición de
  `control.json` (discrepancia si no coinciden), sesión activa y archivos fuera de alcance.
- **`validate --change-id <id> [--gate implementacion|cierre] [--json]`**: corre chequeos de
  alcance (`ALCANCE-RUTA`, `ALCANCE-WHITESPACE` vía `git diff --check`) y, si hay sesión activa,
  límites de sesión (`SESION-LIMITE-*`). Sin `--gate`, no exige sesión. Con `--gate`, exige sesión
  activa (`SESION-AUSENTE` si no la hay) y corre `gate_implementacion` o `gate_cierre`. Exit 1 si
  hay hallazgos.
- **`approve --change-id <id> --artefacto <archivo> [--artefacto ...] --usuario <u> --fecha <f>
  --alcance <texto> --cita <texto>`**: calcula `hash_lf_v1` de cada artefacto y lo apenda a
  `control["aprobaciones"]` (append-only). El hash acredita identidad de contenido, no aprobación
  humana — eso lo aporta `--usuario/--fecha/--alcance/--cita`, provistos por quien invoca, nunca
  inferidos. `--artefacto` es repetible.
- **`transition --change-id <id> --a <estado> [--motivo texto] [--json]`**: valida la transición
  contra la tabla de estados, corre el gate del destino, y si pasa reescribe `estado:` en
  `tasks.md` y agrega la entrada a `control["transiciones"]`. Atómico: si el gate falla, no se
  escribe nada.
- **`session start --change-id <id> [--modo estandar] [--minutos 90] [--max-tareas 3]
  [--max-roles 2] [--max-reintentos 2] [--max-rondas 2]`**: abre una sesión (`SesionYaActivaError`
  si ya hay una activa → exit 2). La sesión nace con `deadline_utc`, `minutos_consumidos: 0.0`,
  `resultado: null`, `subagentes: {}` y `presupuesto.max_continuaciones_por_subagente` con
  default `1`.
- **`session note --change-id <id> --tipo planificada|reintento|ronda [--rol <rol>]
  [--tarea <id>]`**: `reintento` incrementa `reintentos`, `ronda` incrementa `rondas_revision`,
  `planificada` no incrementa nada. `--tarea` agrega el identificador a `sesiones[].tareas`
  (deduplicada). `--rol` agrega a `sesiones[].roles` si no estaba. Falla (exit 2) sin sesión
  activa.
- **`session status --change-id <id> [--json]`**: minutos transcurridos, tareas/roles/reintentos/
  rondas actuales y hallazgos de límite (`SESION-LIMITE-*`), sin cortar nada por sí solo.
- **`session close --change-id <id> --estado completada|pausada`**: cierra la sesión activa
  (`SesionAusenteError` → exit 2 si no hay ninguna). Deriva `resultado` automáticamente e imprime
  uno de tres mensajes finales según `estado_final` + `resultado`, con **`resultado == "excedida"`
  con prioridad sobre `estado_final`**.
- **`notebook-diff --change-id <id> (--path <ruta> [--path ...] | --tocados) [--contra baseline]
  [--max-celdas 200] [--json]`**: diff por celdas de uno o más `.ipynb` contra una revisión de git
  (por defecto `control["baseline"]["commit"]`). Nunca ejecuta el notebook.
- **`kdd init [--json]`**: crea `openspec/kdd/state.json` si no existe (idempotente — si ya existe
  y es válido, no lo toca; si existe y está corrupto, no lo sobreescribe: falla explícito). No
  requiere `--change-id`, opera a nivel de proyecto.
- **`kdd status [--json]`**: informativo, no falla nunca por contenido (mismo espíritu que
  `status`). Reporta `estado` y `changes` de cada una de las 10 etapas, más sus criterios
  detectables (presencia de sección esperada en al menos un cambio referenciado — nunca su
  calidad). Falla (exit 2) si `state.json` no existe todavía.
- **`kdd transition --etapa <etapa> --a no_iniciada|en_progreso|cerrada [--motivo texto]
  [--json]`**: valida estructura y tabla de transiciones de la etapa
  (`no_iniciada → en_progreso → cerrada → en_progreso`). Una etapa `futura`
  (`production_readiness`/`deployment`/`monitoring`) rechaza cualquier transición en v0.2. Cerrar
  una etapa sin evidencia registrada se rechaza. Nunca juzga contenido/calidad metodológica (v0.2).
- **`archive --change-id <id> [--dry-run] [--execute] [--json]`**: mueve
  `openspec/changes/<id>/` a `openspec/archive/<id>/` con `git mv` exclusivamente — nunca
  automático. Exige: `estado: cerrada` en `tasks.md`, gate de cierre en verde, el directorio
  versionado (`git ls-files`) y working tree limpio. Por defecto es dry-run; `--execute` hace el
  `git mv` real y reescribe `control.json` en el destino con `control["archivado"] = {utc, destino}`.

## 3. Códigos de hallazgo

- **`ALCANCE-RUTA`**: archivo sucio fuera de `alcance.rutas_autorizadas`.
- **`ALCANCE-WHITESPACE`**: línea no vacía de `git diff --check` (whitespace o conflicto sin
  resolver).
- **`ALCANCE-TREE-SUCIO`**: working tree no limpio cuando `archive` lo requiere.
- **`SDD-ESTADO-ILEGIBLE`**: no hay línea `estado:` en `tasks.md`, o el valor no es un estado SDD
  válido.
- **`SDD-ESTADO-DUPLICADO`**: hay 2+ líneas `estado:` en `tasks.md`.
- **`SDD-TRANSICION-INVALIDA`**: la transición pedida no está permitida desde el estado actual.
- **`SDD-PROXIMO-PASO-VACIO`**: sección "Próximo paso exacto" vacía al transicionar a
  `pausada_bloqueada`.
- **`SDD-SIN-EVIDENCIA`**: falta `verification.md` (modo completo) o la sección `## Verificación`
  en `tasks.md` (modo abreviado), o existe pero sin contenido real.
- **`SDD-ARCHIVO-ESTADO-INVALIDO`**: `archive` pedido sin `estado: cerrada`.
- **`SDD-ARCHIVO-NO-VERSIONADO`**: el directorio del cambio no está en `git ls-files`.
- **`APROB-AUSENTE`**: no hay aprobación registrada para un artefacto requerido, o el artefacto no
  existe en disco.
- **`APROB-HASH-DESINCRONIZADO`**: el hash actual del artefacto no coincide con el hash aprobado.
- **`SESION-AUSENTE`**: se requiere sesión activa para el gate/transición pedida y no la hay.
- **`SESION-LIMITE-TAREAS` / `-ROLES` / `-REINTENTOS` / `-RONDAS` / `-TIEMPO`**: la sesión activa
  superó el presupuesto correspondiente.
- **`NB-JSON-INVALIDO`**: el `.ipynb` no parsea como JSON.
- **`NB-ID-AUSENTE`**: celda sin `id` (siempre informativo, nunca bloquea).
- **`NB-ID-DUPLICADO`**: mismo `id` en 2+ celdas; bloqueante solo si alguna de las celdas
  duplicadas fue tocada en el diff.
- **`NB-OUTPUTS-FUERA-DE-FASE`**: `outputs`/`execution_count` cambiaron sin cambiar `source`;
  bloqueante solo si `estado` es `en_implementacion`.
- **`NB-ARCHIVO-AUSENTE`**: el `.ipynb` pedido no existe en el working tree.
- **`NB-REVISION-INVALIDA`**: la revisión de git pedida (`--contra`) no resuelve a ningún commit.
- **`KDD-NO-INICIALIZADO`**: `transition --a cerrada` de un cambio que declara etapa(s) KDD pero
  `openspec/kdd/state.json` no existe. Bloquea el cierre entero (nada se escribe).
- **`KDD-ESTADO-CORRUPTO`**: `state.json` existe pero no es JSON válido o no cumple la schema
  esperada (10 etapas exactas, campos requeridos). Bloquea igual que el anterior.
- **`KDD-ETAPA-DESCONOCIDA`**: `control["kdd"]` referencia una etapa que no está en el catálogo de
  10, o `kdd transition --etapa` recibe un valor fuera del catálogo.
- **`KDD-ETAPA-DESTINO-INVALIDO`**: `kdd transition --a` recibe un valor que no es
  `no_iniciada`/`en_progreso`/`cerrada`.
- **`KDD-ETAPA-FUTURA`**: se pidió una transición sobre una etapa en estado `futura`
  (`production_readiness`/`deployment`/`monitoring` en v0.2).
- **`KDD-TRANSICION-INVALIDA`**: la transición de etapa pedida no está permitida desde el estado
  actual de esa etapa.
- **`KDD-SIN-EVIDENCIA`**: se pidió cerrar una etapa sin ninguna entrada en su `evidencia`.

## 4. `control.json`

Campos: `schema_version`, `change_id`, `creado_utc`, `modo` (`completo`/`abreviado`), `baseline`
(`commit`, `rama`, `capturado_utc`), `alcance` (`rutas_autorizadas`), `aprobaciones[]`
(append-only), `transiciones[]` (append-only, `{utc, desde, hacia}`), `sesiones[]` (una por
`session start`, con `estado_final` `activa`/`completada`/`pausada`), `archivado` (`null` o
`{utc, destino}` tras `archive --execute`). Cada entrada de `sesiones[]` agrega `deadline_utc`,
`minutos_consumidos`, `resultado`, `subagentes`, y `presupuesto.max_continuaciones_por_subagente`.
Campo opcional `kdd` (Bloque 4): `{"etapa_primaria": "...", "etapas_afectadas": [...]}` — ver
`kdd.md` §4. Ausente en un cambio que no declara lifecycle; no es requerido por ningún gate SDD.

**`tasks.md` sigue siendo la única fuente de verdad del `estado:`** — `control.json` es historial
mecánico (aprobaciones, transiciones, sesiones), no autoridad. `status` reporta discrepancia si no
coinciden, pero nunca resuelve el conflicto por sí solo a favor de uno u otro.

## 5. `sesiones[].tareas`: lista, no contador

`sesiones[].tareas` es una **lista de identificadores únicos**, no un entero. `session note --tarea
<id>` deduplica. `chequear_limites` cuenta `len(tareas)` contra `max_tareas`.

## 6. Límites reales

- Detecta **después** de que algo pasó, nunca antes ni durante, para todo lo que no sea presupuesto
  de tiempo/continuaciones de una sesión de control activa.
- No controla datos ignorados por `.gitignore` (`git status`/`diff` no los ven).
- No controla lecturas (Read) de ningún archivo, sensible o no.
- No controla que alguien decida directamente no correrlo.
- No puede interrumpir una herramienta ya en ejecución.
- Los subcomandos de `git` que usa están en una lista blanca dura (`rev-parse`, `status`, `diff`,
  `show`, `log`, `ls-files`, `mv`); nunca `commit`/`add`/`reset`/`checkout` — no commitea nada.

## 7. Quién lo invoca

El Lead, único rol con Bash. `python-data-engineer` y `data-science-reviewer` no lo corren — si el
Lead necesita que un subagente actúe sobre lo que `ds_guard` reportó (p. ej. corregir un archivo
fuera de alcance), se lo indica en el prompt de delegación, no delega la ejecución del comando.

# Propuesta — 20261014-composable-skills-writer-semantics

## Problema
Dos deudas de v0.10 comparten archivos y evidencia (decisión de Change 0) y se tratan juntas:

- **A. «Skill» significa hoy tres cosas distintas sin contrato:** el rol Lead empaquetado como skill nativa del proveedor, documentos de referencia/metodología que el Lead lee bajo demanda (`kdd.md`, `eda.md`, `methodology.md`, …) y la futura skill `domain-modeling` (Change 5). No hay contrato mínimo, ni validación, ni regla de carga/composición/precedencia.
- **B. La semántica operativa de writers está dispersa y es contradictoria:** «one writer» (rol vs instancia), ownership de archivos, autoridad sobre el lifecycle, turn limits/reanudaciones, sesión por wall-clock y recovery son convenciones parciales. Hay incidentes reales: Change 0 (writer adelantó `estado:` a mano), Change 2 (reviewer a 16 turnos sin informe) y Change 3 (tres writers y un reviewer a `maxTurns`, sesión `s1` vencida por reloj, `pathguard.py` roto dos veces con reparación de emergencia por Bash).

## Objetivo
Formalizar Role ≠ Skill ≠ Runtime con un contrato mínimo de skill (sin framework), la semántica operativa de writers (un ROL writer; N instancias solo con ownership predeclarado, disjunto y validable; lifecycle; continuaciones; sesiones; recovery) y una guideline TDD-DS corta en `methodology.md`; dejar el terreno limpio para Change 5 (`domain-modeling`) sin implementarlo.

## Evidencia
Audit real del 2026-10-14 sobre `v0.10-dev` (baseline `1c6a4f0`). Todo lo siguiente sale de archivos leídos o de corridas de hoy.

### E1. Inventario Role / Skill / Runtime (clasificación; no se mueve ningún archivo)
| Elemento | Qué es hoy | Capa real | Observación |
|---|---|---|---|
| `.claude/skills/lead-data-scientist/SKILL.md` | skill nativa del proveedor, `disable-model-invocation: true` (SKILL.md:4), solo vía `/lead-data-scientist` | **Role** (Lead) + política de sesión/routing + **documentación de Runtime** (hooks, SKILL.md:232-292) | mezcla tres capas; no se parte en este Change |
| `.claude/agents/*.md` (4) | subagentes del proveedor | **Role** | repiten reglas de pathguard/holdout y «Aplicar CLAUDE.md» (3 agentes + Lead) |
| `methodology.md` (388 l.) | referencia bajo demanda | metodología transversal (candidata a Skill) + prohibiciones del Lead (Role) | §14 contradice `ARCHITECTURE.md` §7.1 |
| `eda.md`, `kdd.md` | referencia bajo demanda | metodología + uso de Runtime (`ds_profile`, `ds_guard kdd`) | skills «de facto», sin frontmatter |
| `decision-ledger.md`, `verificador.md`, `sdd.md` | referencia bajo demanda | documentación de Runtime/proceso (`ds_guard`) | no son skills metodológicas |
| `templates/*.md` | plantillas SDD | scaffolding de Runtime | gestionadas por manifest |
| `tools/**` (dsguard, nbrunner, hooks, ds_init) | código | **Runtime** | correcto |

Carga hoy: `SKILL.md` solo por invocación manual; los `.md` de referencia los lee el Lead bajo demanda por instrucción de SKILL.md:83-107; los subagentes reciben contexto por los 8 campos de SKILL.md:177-193 y no tienen herramienta Skill ni Agent. Todo es project-installed (copias gestionadas desde templates, `tools/ds_init/manifest.py:240-264`); Harmessi no tiene skills globales.

### E2. Mezclas y contradicciones
- **C1.** `methodology.md:192-193` dice «Nunca hay dos writers concurrentes sobre el mismo cambio»; `ARCHITECTURE.md:616` y M2 (`v0.10.md`) fijan N instancias con ownership disjunto; Change 3 usó seis instancias (A–F) en `tasks.md`.
- **C2.** SKILL.md:141-142 («reinvocar el mismo rol consume el límite de intentos») no distingue una reanudación por truncamiento técnico de un reintento por resultado insatisfactorio; el hook cuenta «continuaciones» aparte (`hook_presupuesto.py:388-401`). El «2 de 2 ciclos de reviewer» de Change 3 mezcla ronda, remediación y reintento.
- **C3.** `sdd.md:36-37` («todo artefacto SDD lo escribe `python-data-engineer`») vs. la reparación de emergencia que hizo el Lead por Bash en Change 3 (`verification.md:43-46` de ese Change).
- **C4.** El pedido de este Change lista un rol `ml-engineer`: **no existe** en el repo (grep sin resultados; 4 agentes). Roles reales: Lead (skill), `python-data-engineer`, `data-science-reviewer`, `metodologo`, `notebook-runner`.
- **C5.** Solo `data-science-reviewer` tiene guía de presupuesto de turnos (`data-science-reviewer.md:35-42`); el writer (maxTurns 12), el metodólogo (8) y el runner (4) no.
- **C6.** `session_minutes = 90` está hardcodeado en `_BUDGET_DEFAULTS` (`ds_guard.py:628-629`), en la firma `session_start(minutos=90)` (`sdd.py:784`) y en la tabla «~90 min» de SKILL.md:117-119; la derivación por policy YA existe (`ds_guard.py:1066-1069`, `autonomy.budgets.session_minutes`).

### E3. Writers y ownership
- Rol writer único: `python-data-engineer` (tools Read/Edit/Write/NotebookEdit/Grep/Glob, `maxTurns: 12`); el Lead no edita (SKILL.md:23-24). `NotebookEdit` inserta/reemplaza/borra celdas; ejecutar notebooks es de `notebook-runner` (Bash con hook validador).
- Instancias: nada las distingue técnicamente. `pathguard.py:420-425` aplica `write_scopes` por **tipo** de agente (opt-in, vacío por defecto, no aplica al Lead); `hook_rutas.py` recibe `agent_type`, no instancia. M2/Change 0 decidió: sin hook por instancia en v0.10.
- Ownership hoy: texto libre en `## Invocaciones planificadas` de `tasks.md` (ejemplo: Change 3, writers A–F con rutas entre backticks). No hay consumidor en código (grep de «Invocaciones planificadas» en `tools/**/*.py`: sin resultados). `ALCANCE-RUTA` evalúa todo el working tree contra el scope del Change, no por instancia.
- Existe lo necesario para validar sin hook: `scope.alcance_efectivo` (`scope.py:66`), `_normalizar_entrada_alcance` (`sdd.py:1249`), `parsear_alcance_autorizado` (`sdd.py:1299`) y `repo.path_matches_any` (`repo.py:205`).

### E4. Lifecycle
- Estados y transiciones: `sdd.py:29-74`. La fuente de verdad del estado es la línea `estado:` de `tasks.md` (`sdd.py:104`, `transition` la lee en `sdd.py:~540`); `control["transiciones"]` es el registro.
- Cualquier writer con `tasks.md` en su ownership puede editar `estado:` a mano. `cmd_validate` (`ds_guard.py:281-331`) no compara `estado:` contra la última transición registrada: la divergencia no se detecta. Evidencia: Change 0 (`verification.md:32` de ese Change).
- Censo de hoy: 57 Changes con `tasks.md` y `control.json`; **0** divergen entre `estado:` y la última transición (o `propuesta_pendiente` sin transiciones). Un chequeo de divergencia tiene falsos positivos históricos nulos.
- `transition` ya es idempotente/reconciliable (`sdd.py:~544-556`): sirve como camino de recuperación de una divergencia legítima (ventana entre escribir `estado:` y `control.json`).

### E5. Turn limits y continuaciones
- `maxTurns`: writer 12, reviewer 16, metodólogo 8, runner 4 (línea 7 de cada agente). Evidencia real: Change 2 (reviewer a 16 turnos sin informe), Change 3 (3 writers y 1 reviewer a su límite; todos reanudados).
- Contabilidad actual: `max_continuaciones_por_subagente` = 1 por defecto, fijo en `sdd.session_start` (`sdd.py:789,812`), **sin flag de CLI** (`ds_guard.py:5007-5011` expone `--minutos/--max-tareas/--max-roles/--max-reintentos/--max-rondas`, no continuaciones). El hook cuenta continuaciones por clave de agente (`hook_presupuesto.py:368-401`).
- **Hallazgo H1 (a verificar con payload real):** `_extraer_agent_id` prioriza `subagent_type` sobre `name` (`hook_presupuesto.py:265`): N instancias del mismo rol compartirían clave, y cada `Agent` nuevo reinicia `continuaciones` a 0 (`:361`). Además la clave registrada podría no coincidir con el `to` de `SendMessage`, en cuyo caso la continuación se permite «sin contar» (`:414`). Los tests usan payloads sintéticos (`test_operational_session_recovery.py:219-220`); nunca se verificó el payload real del proveedor. No se afirma el bug: se exige evidencia.
- Un truncamiento por turnos no deja una marca determinista: el agente cortado no puede emitir un informe final. El estado persistente real es el filesystem (archivos del ownership) y el contexto del agente solo sobrevive si se lo reanuda por mensaje.

### E6. Sesión
- Presupuesto: `session_start` calcula `deadline_utc` una vez (`sdd.py:797-800`); `hook_presupuesto.py` bloquea `Agent`/`SendMessage` en los últimos 5 min y, vencido el deadline, también `Write/Edit/Bash/PowerShell` salvo `git status/diff` y `ds_guard session note|status|close`. El reloj corre durante esperas humanas (T1) y tests largos; no hay pausa.
- Change 3: `s1` (600 min) venció por reloj con trabajo válido en curso; se cerró y se abrió `s2` (480 min). Ese es el camino de recuperación vigente y está acotado por `max_sessions`/`aggregate_minutes` si se declaran.

### E7. Incidentes de Change 3 (`verification.md:43-46` de ese Change)
- `pathguard.py` roto dos veces (nombres sin definir ⇒ el hook, fail-closed, denegó toda escritura): la 1.ª se revirtió con git; la 2.ª requirió reparación de emergencia por Bash con texto escrito por el writer.
- Bash perdió PATH en una sesión nueva; las pruebas siguieron por PowerShell: incidente de **entorno**, no de semántica de Harmessi.

## Supuestos descartados
1. Que `ml-engineer` sea un rol existente (no existe; ver C4).
2. Que el default de 90 min no derive de policy: ya deriva de `autonomy.budgets.session_minutes`; lo que queda es un fallback hardcodeado y documentación (C6).
3. Que haga falta un runtime/registry/loader de skills: `.claude/skills/lead-data-scientist/*.md` + lectura bajo demanda ya soporta la composición.
4. Que subir `maxTurns` resuelva el truncamiento: oculta el problema y quita el acotamiento (objetivo: trabajo acotado + reanudable).
5. Que una divergencia `estado:` vs transiciones sea frecuente en el histórico (censo: 0/57).
6. Que `max_continuaciones_por_subagente` esté expuesto o sea configurable por el usuario (no hay flag).
7. Que el hook distinga instancias del mismo rol (recibe tipo de agente; H1 pendiente de verificación).

## Alcance
- **Skills (foundation):** taxonomía Role/Skill/Runtime documentada; contrato de skill (frontmatter cerrado, ubicación, validación estructural barata en Doctor); semántica de carga, composición y precedencia; traza de skills cargados en `tasks.md`; plantilla de skill. Sin skill funcional.
- **Writers:** semántica rol vs instancia; sección `## Ownership de writers` en `tasks.md` + validación determinista previa a la delegación; ownership ⊆ scope efectivo y distinto de scope; lifecycle exclusivo del Lead; protocolo de intervención de emergencia; archivos self-governing; política de concurrencia.
- **Turnos y sesiones:** vocabulario (continuación / reintento / ronda / ciclo de remediación), contrato de reanudación con guardia anti-loop, marca `ESTADO-AGENTE` en agentes, flag `session start --max-continuaciones` (default sin cambio), documentación de semántica de sesión y de recovery; clasificación de incidentes de entorno.
- **TDD-DS:** guideline corta en `methodology.md`; «evals ≠ tests».
- Detalle verificable en `spec.md`; diseño en `design.md`; plan en `tasks.md`.

## Fuera de alcance
`domain-modeling` funcional, `GLOSSARY.md`, lógica de aprobación de términos (Change 5); problem-framing, diagnosing-bugs, codebase-design; ledger amend/correct y enum de decisiones; Doctor installation de ds_init; performance de `ds_profile`; T1 en POSIX; scratchpad externo; T2 de proveedor; hook por instancia; scheduler o locks distribuidos; registry/marketplace/loader/resolver de dependencias/daemon de skills; arreglar PATH de Bash/PowerShell/VS Code; cambiar `maxTurns` o el default de 90 min; renumerar el roadmap o tocar el contenido de Changes 5–6; push; full regression.

## Decisiones materiales (resueltas por el usuario el 2026-10-14)
Resolución: M1–M7 APROBADAS con la recomendación indicada, con estas precisiones: M2 admite una variante markdown más simple que la del ejemplo del usuario (mismas semánticas: id, role, task, owns); M4 mantiene maxTurns (12/16/8/4) y el default 1, con override acotado `--max-continuaciones` (nunca infinito), vocabulario continuation/retry/reviewer cycle, handoff mínimo `ESTADO-AGENTE: completed|continue|blocked|needs-review` y anti-loop; H1 queda UNCONFIRMED (el hook solo se toca si el runtime normal produce un payload real de forma segura y natural; no se pide captura manual; si no, el hook queda intacto y H1 es deuda verificada solo con tests sintéticos); M5 sin cambio de 90 ni de semántica; M6 protocolo contractual estricto (checkpoint Git, serial, único owner, smoke inmediato, rollback) sin subcomando nuevo; M7 ubicación aprobada. `ml-engineer` NO existe: solo puede mencionarse como idea futura/no implementada. N instancias del mismo rol writer: sí; N roles writer distintos: no.

- **M1 — Enforcement de ownership.** (a) solo contrato; (b) contrato + validación determinista previa a la delegación (`ds_guard ownership check` e integración en `validate`), sin hook por instancia; (c) hook por instancia. **Recomendada: (b).** (c) contradice la decisión de Change 0 (sin hook por instancia en v0.10).
- **M2 — Representación parseable de ownership.** (a) sección markdown `## Ownership de writers` en `tasks.md`; (b) JSON paralelo en `control.json`; (c) solo prosa. **Recomendada: (a)** (gramática cerrada, sin comodines salvo sufijo `/**`; el JSON de `control.json` no está autenticado ni es necesario).
- **M3 — Autoridad de lifecycle.** (a) solo contrato; (b) hallazgo `SDD-ESTADO-DIVERGENTE` en `ds_guard validate` (estado ≠ última transición); (c) hook que bloquee editar `estado:`. **Recomendada: (b)** (censo 0/57; (c) bloquearía ediciones legítimas de `tasks.md` y el hook no distingue instancias).
- **M4 — Turn limits.** Mantener `maxTurns` y el default `max_continuaciones_por_subagente = 1`; agregar `session start --max-continuaciones` (default 1) y el contrato de reanudación; corregir la clave de instancia del hook (H1) **solo si** se obtiene un payload real que lo respalde (si no, se documenta la limitación). Alternativas: subir `maxTurns` (descartada); nueva clave de policy `autonomy.budgets` para continuaciones (más superficie, sin evidencia). **Recomendada: la primera.** Resuelta: ver «Resolución» arriba.
- **M5 — Sesión por wall-clock.** (a) no cambiar default ni semántica y documentar (wall-clock ≠ cómputo, esperas T1 cuentan, recovery = cerrar/abrir sesión); (b) agregar pausa por T1, warning anticipado o nueva clave de policy. **Recomendada: (a).** El número 90 no se toca.
- **M6 — Archivos que gobiernan su propio enforcement** (`pathguard.py`, hooks y launchers, `settings.json`). (a) protocolo contractual: writer exclusivo y serial, smoke de import + tests dirigidos antes de cualquier otra escritura, receta de rollback con git, protocolo de emergencia; (b) además un subcomando `hooks smoke`. **Recomendada: (a)** (sin subsistema nuevo).
- **M7 — Ubicación de skills componibles.** (a) `.claude/skills/lead-data-scientist/skills/<name>.md` (flat, frontmatter propio); (b) junto a las referencias existentes; (c) skill nativa por directorio. **Recomendada: (a)** (separa lo bajo contrato de las referencias sin frontmatter; (c) activaría la carga automática por descripción y exige el campo nativo `description`).

## Impacto en production-readiness (opcional)
Ninguno: documentación, un validador estructural y un chequeo de consistencia; sin cambios de datos ni de modelos.

## Aprobación
- Usuario:
- Fecha:
- Alcance aprobado:
- Versión de artefactos referenciada:
- Cita o descripción fiel de qué se aprobó:

## Alcance autorizado

- tools/dsguard/skill_contract.py
- tools/dsguard/ownership.py
- tools/dsguard/sdd.py
- tools/dsguard/hook_presupuesto.py
- tools/ds_guard.py
- tools/harmessi/doctor.py
- tools/ds_init/manifest.py
- tools/tests/test_skill_contract.py
- tools/tests/test_ownership.py
- tools/tests/test_sdd_estado_divergente.py
- tools/tests/test_ds_guard_ownership_cli.py
- tools/tests/test_operational_session_recovery.py
- tools/tests/test_skill_methodology.py
- tools/tests/test_architecture_boundaries.py
- tools/harmessi/tests/test_doctor_skill_contract.py
- tools/ds_init/tests/test_manifest.py
- tools/ds_init/tests/test_manifest_dsguard_parity.py
- .claude/skills/lead-data-scientist/SKILL.md
- .claude/skills/lead-data-scientist/methodology.md
- .claude/skills/lead-data-scientist/sdd.md
- .claude/skills/lead-data-scientist/verificador.md
- .claude/skills/lead-data-scientist/templates/skill.md
- .claude/skills/lead-data-scientist/templates/tasks.md
- tools/ds_init/profiles/python_jupyter_data/templates/SKILL_lead_data_scientist.md.tmpl
- tools/ds_init/profiles/python_jupyter_data/templates/methodology.md.tmpl
- tools/ds_init/profiles/python_jupyter_data/templates/sdd.md.tmpl
- tools/ds_init/profiles/python_jupyter_data/templates/verificador.md.tmpl
- .claude/agents/python-data-engineer.md
- .claude/agents/data-science-reviewer.md
- .claude/agents/metodologo.md
- tools/ds_init/profiles/python_jupyter_data/templates/agent_python_data_engineer.md.tmpl
- tools/ds_init/profiles/python_jupyter_data/templates/agent_data_science_reviewer.md.tmpl
- tools/ds_init/profiles/python_jupyter_data/templates/agent_metodologo.md.tmpl
- ARCHITECTURE.md
- docs/roadmap/v0.10.md

## Motivo de rechazo
<!-- completar solo si estado: descartada -->

## Desacuerdo registrado
<!-- completar solo si estado: pausada_bloqueada tras 2 rondas de revisión sin acuerdo -->

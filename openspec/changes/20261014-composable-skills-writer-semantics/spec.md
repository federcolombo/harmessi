# Especificación — 20261014-composable-skills-writer-semantics

Requisitos verificables. «DEBE» = obligatorio; «PUEDE» = opcional. Los códigos de hallazgo son propuestos y se fijan al implementar. Todo requisito de código es stdlib-only, sin dependencias nuevas y provider-neutral (no importa nombres de proveedor).

## A. Role / Skill / Runtime

**R1 — Taxonomía.** `methodology.md` y `ARCHITECTURE.md` DEBEN definir: *Role* (quién actúa: permisos, tool surface, responsabilidad, límites), *Skill* (conocimiento/metodología reutilizable, sin autoridad) y *Runtime/Tool* (cálculo, ejecución, enforcement, evidencia), con el principio «Skills enseñan cómo razonar; Roles determinan quién puede actuar; Runtime hace cumplir y calcula», y la clasificación del inventario actual (E1 de `proposal.md`) sin mover archivos.
- CA: test de contenido verifica el principio y la tabla de clasificación; ningún archivo existente cambia de ruta.

**R2 — Contrato de skill.** Una skill componible es un `.md` en `.claude/skills/lead-data-scientist/skills/<name>.md` (M7) con frontmatter de lista CERRADA: obligatorios `name` (kebab-case `[a-z][a-z0-9-]*`, igual al nombre de archivo sin `.md`), `purpose` (una línea), `when_to_load` (una línea), `roles` (lista inline `[a, b]`, no vacía, ⊆ roles conocidos); opcional `artifacts` (lista inline de rutas repo-relativas literales que la skill lee o escribe; por defecto `[]`). Cualquier otra clave es inválida. Formato: subset de YAML `clave: valor` y listas inline; sin dependencia de PyYAML.
- Roles conocidos = `lead-data-scientist` + los `name` de `.claude/agents/*.md`. (`ml-engineer` no existe y no se agrega.) Si `ml-engineer` se menciona en documentación, es solo como idea futura/no implementada.
- `artifacts` tiene consumidor real: el Lead lo usa para incluir esos paths en scope/ownership del Change; la skill NO obtiene acceso por declararlos. Cada entrada pasa por la misma normalización que `## Alcance autorizado` (sin `..`, absolutas, comodines ni rutas protegidas).
- CA: tests por cada regla; claves prohibidas explícitas con mensaje propio: `tools`, `allowed-tools`, `permissions`, `hooks`, `model`, `maxTurns`, `install`, `dependencies`, `requires`, `priority`, `autonomy`, `description`.

**R3 — Validación estructural.** Un módulo core `tools/dsguard/skill_contract.py` DEBE validar frontmatter y campos (puro, sin I/O de red); Doctor DEBE exponerlo como check `HARMESSI-SKILL-CONTRATO` sobre `skills/*.md` (ausencia del directorio = OK, no hay skills todavía). No evalúa calidad metodológica.
- Códigos: `SKILL-FRONTMATTER-AUSENTE`, `SKILL-CAMPO-FALTANTE`, `SKILL-CAMPO-NO-PERMITIDO`, `SKILL-NOMBRE-INVALIDO`, `SKILL-ROL-DESCONOCIDO`, `SKILL-ARTIFACT-INVALIDO`.
- CA: archivo válido ⇒ sin hallazgos; cada violación ⇒ su código; un archivo de proyecto no gestionado en `skills/` también se valida y no produce `HARMESSI-DRIFT`.

**R4 — Carga y no-autoridad.** `SKILL.md`/`methodology.md` DEBEN fijar: el Lead detecta una necesidad metodológica → lee la skill relevante (solo cuando aplica) → aplica sus instrucciones → delega/ejecuta normalmente. Una skill NO puede modificar permisos, conceder herramientas, ampliar scope, cambiar guardrails, alterar lifecycle, aprobar artifacts ni saltar STOPs: es guidance, nunca authority. Los subagentes no cargan skills: el Lead los apunta (campo 2 de los 8 campos) al archivo si su rol figura en `roles`, sin copiar su contenido al prompt.
- CA: test de contenido de estas reglas en `SKILL.md`/`methodology.md` (y `.tmpl`).

**R5 — Composición y precedencia.** DEBE documentarse: se cargan solo las que aplican; no se duplica contexto; conflicto entre fuentes se resuelve a favor de (1) governance/runtime, (2) contrato del rol, (3) contrato del proyecto (`CLAUDE.md`), (4) guidance de la skill; conflicto entre dos skills ⇒ el Lead se detiene y consulta al usuario. NO se construye motor de prioridades.
- CA: test de contenido.

**R6 — Traza.** Cuando una skill afecta decisiones o delegación de un Change, el Lead DEBE registrarla en la sección `## Skills cargados` de `tasks.md` (bullets `- <skill> — <tarea> — <motivo>`). Si la sección existe, `ds_guard validate` DEBE emitir `SKILL-REFERENCIA-DESCONOCIDA` por cada skill citada que no exista en `skills/`.
- CA: test con skill existente (OK), inexistente (hallazgo) y sección ausente (sin hallazgo).

**R7 — Plantilla y no-implementación.** DEBE existir `templates/skill.md` (plantilla con frontmatter válido) registrada en el manifest y en Doctor. NO se crea `domain-modeling`, `GLOSSARY.md` ni lógica de aprobación de términos. Un ejemplo sintético vive solo en fixtures de tests.
- CA: no existe `skills/domain-modeling.md` ni `GLOSSARY.md`; la plantilla pasa R3.

**R8 — Sin lifecycle propio.** Las skills no tienen sesión, aprobación runtime, ownership ni entradas en registry/manifest global; cambian por el Change normal. El manifest solo gestiona la plantilla.
- CA: test de contenido + test de manifest.

## B. Writers

**R9 — Semántica rol vs instancia.** `methodology.md` §14, `SKILL.md`, `sdd.md` y `ARCHITECTURE.md` DEBEN decir: «one writer = un ROL writer autorizado» (`python-data-engineer`), NO «una única instancia serial». Se permiten N instancias concurrentes del mismo rol solo con ownership predeclarado, específico y disjunto; el Lead sigue sin escribir implementación. Se elimina la contradicción C1 (la frase «nunca dos writers concurrentes»).
- CA: test de contenido: la frase vieja ausente; la regla nueva presente en `.md` y `.tmpl`.

**R10 — Gramática de ownership.** `tasks.md` PUEDE contener `## Ownership de writers` con un bloque por instancia:
```
### <id> — <rol> — <tareas>
- ruta/literal.py
- dir/**
```
Variante markdown aprobada de M2: se prefiere el encabezado `### <id> — <rol> — <tareas>` por ser parseable sin YAML; es equivalente semánticamente a `id/role/task/owns`. Paths: repo-relativos, separador `/`, archivo exacto o directorio terminado en `/**`; sin `*` intermedio, sin `?`, sin `[]`.
`<id>` = `[A-Za-z0-9_-]+` único; `<rol>` ∈ roles writer (hoy solo `python-data-engineer`); `<tareas>` = lista informativa `T\d+` separada por comas. Entradas: ruta literal repo-relativa o `dir/**` (único comodín admitido, solo como sufijo). Se normaliza `\`→`/` y se compara sin distinguir mayúsculas (casefold, como pathguard).
- CA: casos válidos e inválidos parametrizados; `*`/`?`/`[`/`**` no-sufijo ⇒ `OWNERSHIP-PATRON-INVALIDO`.

**R11 — Validación determinista.** Un módulo core `tools/dsguard/ownership.py` DEBE parsear la sección y emitir hallazgos: `OWNERSHIP-SECCION-ILEGIBLE`, `OWNERSHIP-ID-DUPLICADO`, `OWNERSHIP-ROL-INVALIDO`, `OWNERSHIP-VACIO` (instancia sin entradas), `OWNERSHIP-PATRON-INVALIDO` (incluye rutas protegidas, absolutas, `..`, repo-wide), `OWNERSHIP-SOLAPADO` y `OWNERSHIP-FUERA-DE-ALCANCE`.
- Solape (decidible exacto con la gramática): literal=literal si iguales; literal∈`dir/**` si empieza con `dir/`; `a/**` vs `b/**` si uno es prefijo de directorio del otro (incluye iguales). Padre-comodín vs hijo ⇒ solape. Se detectan como mínimo: archivo==archivo; `dir/**` vs archivo dentro de `dir`; `dir/**` vs subdirectorio (`a/**` vs `a/b/**`); dos directorios anidados; paths equivalentes tras normalización (`./x`, `\`, mayúsculas). Ante solape: error antes de delegar (no se espera al conflicto Git). Si el ownership no es ⊆ scope efectivo: no se delega.
- Fuera de alcance: cada entrada DEBE estar cubierta por `scope.alcance_efectivo`; un `dir/**` solo si lo cubre un `X/**` igual o ancestro.
- CA: tests por cada código; ejemplo válido del pedido (A: `tools/dsguard/foo.py`+`tests/test_foo.py`; B: `bar.py`+`test_bar.py`) sin hallazgos; ejemplo inválido (A y B: `tools/dsguard/**`) ⇒ `OWNERSHIP-SOLAPADO`.

**R12 — Falla antes de delegar.** DEBE existir `ds_guard ownership check --change-id <id> [--json]` (solo lectura; exit 0 sin hallazgos, 1 con hallazgos, 2 uso) y `ds_guard validate` DEBE incluir los hallazgos de ownership cuando la sección existe. Regla del Lead (contrato): no lanzar dos o más instancias writer concurrentes sin una sección válida; ausencia de sección ⇒ ejecución serial de una instancia. Sin hook por instancia, sin locks, sin scheduler.
- CA: tests de CLI (exit codes, JSON); ownership inválido ⇒ exit 1 sin escribir nada.

**R13 — Ownership predeclarado y actualizable solo antes.** Si un writer necesita un archivo adicional: NO lo edita y lo devuelve al Lead; el Lead actualiza la sección `## Ownership de writers` (y registra el cambio en `## Historial de ownership` de `tasks.md`: fecha, instancia, ruta, motivo) y recién entonces se lo asigna. Sin perdón post-hoc.
- Ownership ≠ scope: ownership ⊆ scope efectivo (R11); una enmienda de scope NO asigna ownership; un cambio de ownership NO amplía scope. Ampliar scope sigue siendo `ds_guard scope amend` (T1).
- CA: test de contenido; test de `OWNERSHIP-FUERA-DE-ALCANCE` tras un `scope amend` simulado que no asigna ownership.

**R14 — Lead no es writer; emergencias.** El Lead puede auditar, decidir, planificar, ejecutar git, coordinar, pasar diffs, validar y lanzar/reanudar agentes; NO modifica implementación. Una *intervención de emergencia* (el Lead escribe por un canal no gobernado) solo es aceptable si: (i) el canal gobernado de escritura está inoperante por el propio enforcement (self-lock, ver R22) o falla de entorno; (ii) el contenido/diff exacto fue producido por el writer y el Lead solo lo transporta; (iii) el archivo está en scope y en ownership; (iv) es lo mínimo para restaurar el canal. Se registra en `verification.md` sección `## Intervenciones de emergencia` (UTC, causa, archivo, canal, autor del contenido, sha256 del diff, smoke posterior). Retorno al estado gobernado: smoke de import + tests dirigidos en verde, diff revisado por `data-science-reviewer` y mención en el checkpoint. No se usa de forma preventiva ni para trabajo de feature; dos en un mismo Change ⇒ pausa y consulta al usuario.
- CA: test de contenido (`methodology.md`/`sdd.md` + `.tmpl`) y de la plantilla de `verification.md` si aplica.

**R15 — Writers no controlan el lifecycle.** Motivación citada: en Change 0 un writer adelantó `estado:` a mano antes de la aprobación (`verification.md:32` de ese Change). Los writers pueden reportar `completed`, `blocked` o `needs-review` pero NO materializar aprobada / en_implementacion / en_verificacion / cerrada. Un writer NO decide aprobado / en implementación / en verificación / cerrado ni edita `estado:` ni `control.json`; puede reportar `completed | blocked | needs-review`. Las transiciones son del Lead vía `ds_guard transition`. `ds_guard validate` DEBE emitir `SDD-ESTADO-DIVERGENTE` si `estado:` en `tasks.md` ≠ última `control["transiciones"][-1].hacia` (o `propuesta_pendiente` si no hay transiciones); el mensaje indica reconciliar con `ds_guard transition --a <estado>` (idempotente, corre el gate) o restaurar `estado:` desde git.
- CA: tests: sin divergencia ⇒ nada; `estado:` adelantado a mano ⇒ hallazgo; ventana de reconciliación (estado ya escrito, transición faltante) ⇒ hallazgo y `transition` lo resuelve; los Changes históricos del repo ⇒ 0 hallazgos (censo 2026-10-14: 57/57 consistentes).

**R16 — Concurrencia.** Serial por defecto. Concurrente solo si: ownership válido y disjunto, tasks sin dependencia de orden, el overhead (8 campos + handoff por instancia) vale la pena, y ninguna toca archivos self-governing (R22). Decide el Lead; sin scheduler. `max_concurrent_subagents` sigue siendo autorreportado. N instancias del MISMO rol writer: sí. N roles writer DISTINTOS escribiendo: no, salvo que una arquitectura futura lo apruebe explícitamente.
- CA: test de contenido.

**R17 — Fronteras preservadas.** Subagentes no delegan (sin herramienta Agent); `python-data-engineer` edita notebooks (NotebookEdit: insertar/reemplazar/borrar celdas) pero no los ejecuta (`notebook-runner`/runtime); `data-science-reviewer` y `metodologo` son solo lectura (Read/Grep/Glob), reciben diffs/contexto del Lead y no corrigen; el metodólogo sigue siendo un ROL, no un patrón para cada skill. El reviewer no tiene Bash ni corrige: observa, encuentra y recomienda; el writer corrige.
- CA: test de contenido de tools en frontmatter de agentes (sin cambios) y de las frases en `SKILL.md`.

## C. Turnos, reanudaciones, sesiones, recovery

**R18 — Vocabulario.** DEBE definirse sin solaparse: *continuación* (reanudar la MISMA instancia/ciclo tras truncamiento técnico por `maxTurns`; se cuenta solo contra `max_continuaciones_por_subagente`; misma task, mismo rol, mismo ownership y, si aplica, mismo ciclo de reviewer; NO es una task nueva, NO reinicia la auditoría); *retry/reintento* (reejecución por fallo técnico o intento fallido, o reinvocación tras resultado insatisfactorio; cuenta contra `reintentos`/remediación, `sdd.md` §8; distinto de continuación); *ronda* (ajuste del usuario a un borrador antes de la primera aprobación); *ciclo de reviewer* (nueva revisión de un diff nuevo tras fixes). Una continuación NO consume ciclo de reviewer, ronda ni reintento; tampoco es ilimitada (tope por instancia y por sesión). Una continuación del reviewer dentro del mismo análisis sigue siendo el mismo ciclo; máximo 2 ciclos de reviewer por Change y las continuaciones no cuentan como ciclos.
- Para diffs grandes el Lead PUEDE partir la revisión en invocaciones planificadas del mismo ciclo (`sdd.md` §8: no consumen intentos).
- CA: test de contenido; corrige C2.

**R19 — Contrato de reanudación.** Cada agente (`python-data-engineer`, `data-science-reviewer`, `metodologo`) DEBE terminar su respuesta final con `ESTADO-AGENTE: completed|continue|blocked|needs-review`; su ausencia = truncamiento (marca neutral al proveedor). Ante truncamiento el Lead: (1) lee el estado en disco (`git diff --stat`/archivos del ownership) y arma un handoff corto (≤ ~10 líneas: hecho / falta / ownership); (2) evalúa progreso; (3) si hay progreso y queda dentro de scope y presupuesto, reanuda la MISMA tarea y la misma instancia (preferible a relanzar: conserva contexto); (4) no crea otra auditoría ni reinicia desde cero; (5) respeta el tope de continuaciones.
- *Sin progreso* = el diff de los archivos del ownership no cambió (writer) o no se entregó ningún hallazgo nuevo (reviewer) entre dos reanudaciones consecutivas ⇒ no se reanuda más: pausa y consulta.
- Agotado el tope ⇒ pausa; subir el tope o relanzar requiere aprobación humana (el hook ya lo exige).
- Handoff mínimo (breve, sin formato grande), junto a la línea de estado: hecho, falta, si hubo cambios (archivos), evidencia/tests existentes y próximo paso. Sin línea de estado válida (terminación por límite sin handoff) el Lead lo trata como incompleto / candidato a continuación, nunca como completed.
- Anti-loop: una continuación solo se permite si hubo progreso útil respecto de la anterior; con el tope agotado NO hay continuaciones ocultas: el Lead replantea la task, la divide, declara blocked o escala si hay decisión material.
- CA: test de contenido en agentes (`.md` y `.tmpl`), `SKILL.md` y `sdd.md`.

**R20 — Tope configurable sin cambiar el default.** `ds_guard session start` DEBE aceptar `--max-continuaciones N` (entero ≥ 1; default 1 = comportamiento actual) que se persiste en `presupuesto.max_continuaciones_por_subagente`; `ds_guard session status` DEBE mostrarlo. No hay nueva clave de policy. El tope nunca es infinito: se define un máximo duro razonable (p. ej. 5) y N>máximo ⇒ exit 2.
- CA: tests de CLI: sin flag ⇒ 1; con flag ⇒ N; N<1 ⇒ exit 2; N>máximo ⇒ exit 2; sesiones existentes sin la clave siguen leyéndose.

**R21 — H1 (UNCONFIRMED).** La hipótesis (subagent_type vs name; posible reset del contador) NO motiva cambios por sí sola. `hook_presupuesto.py` solo se modifica si durante este Change se obtiene un payload REAL de `Agent`/`SendMessage` producido por el runtime normal de forma segura y natural (sin interceptar datos innecesarios ni pedir capturas manuales al usuario). Si no aparece: el hook queda intacto, H1 se registra como deuda verificada solo con tests sintéticos y esto NO bloquea el Change.
- CA: sin cambios en el hook en ese caso; si hay payload, test con ese fixture y aplica R22.

**R22 — Archivos self-governing.** Cierre mínimo: `pathguard.py`, `hook_rutas.py`, `hook_launcher_rutas.py`, `hook_presupuesto.py`, `hook_launcher_presupuesto.py`, `tools/nbrunner/hook_launcher.py`, `hook_validar_comando.py` y `.claude/settings.json` (más `core.py`/`repo.py` por import, parsers u otro código equivalente que pueda bloquear toda escritura). Incidente citado: en Change 3 pathguard se auto-bloqueó dos veces (una reparación por Bash). Su edición DEBE seguir el protocolo de 8 pasos: 1) trabajo serial; 2) un único writer owner; 3) checkpoint Git limpio/conocido antes de editar; 4) modificación acotada; 5) inmediatamente smoke de sintaxis/import + tests dirigidos mínimos del propio enforcement; 6) ninguna otra escritura hasta que el smoke pase; 7) si rompe el enforcement: rollback al checkpoint conocido y corrección por el writer; 8) todo bypass/reparación de emergencia es excepcional, se documenta en verification.md, se valida después y nunca pasa a ser workflow normal (Bash NO es un escape oficial). Receta de rollback con git: `git diff` → `git restore -- <archivo>`; si el canal gobernado quedó inoperante ⇒ R14.
- CA: protocolo documentado en `methodology.md` y `sdd.md` (+ `.tmpl`); test de contenido; sin código nuevo (M6.a).

**R23 — Sesión.** Documentar sin cambiar código ni el número: `session_minutes` es una cota de seguridad por wall-clock, no minutos de trabajo efectivo; el reloj corre durante esperas humanas (T1) y tests largos; el default efectivo deriva de `autonomy.budgets.session_minutes` (fallback 90 solo si no hay policy); `--minutos` explícito manda; al elegirlo se estima wall-clock incluyendo esperas; expiración = el hook bloquea trabajo nuevo; recovery canónico = `session close` + `session start` (nueva sesión, acotada por `max_sessions`/`aggregate_minutes` si existen). La deuda residual (fallback hardcodeado duplicado, warning anticipado, pausa por T1) queda registrada, no implementada (M5.a). Documentar también: `session_minutes` (autonomy.budgets) es la policy efectiva; wall-clock; la espera humana T1, los tests largos y el trabajo en background cuentan; la expiración no invalida automáticamente el trabajo previo; recovery soportado = cerrar la sesión y abrir otra; evidencia real: Change 3 (s1 vencida → s2). Los literales 90 se clasifican, sin refactor cosmético: canónico `ds_guard.py:_BUDGET_DEFAULTS`; fallback de sesiones legacy sin presupuesto `core.py:72`; default de firma `sdd.py:784` (la CLI siempre lo pasa); resto documentación/plantillas.
- CA: test de contenido en `SKILL.md`/`verificador.md` (+ `.tmpl`).

**R24 — Recovery y entorno.** DEBE existir una tabla de recovery: writer `maxTurns` (R19), reviewer `maxTurns` (R19), sesión vencida (R23), hook/pathguard self-locking (R22/R14); y la clasificación: Bash perdió PATH, PowerShell/Git Bash/VS Code ⇒ **entorno**, no semántica de Harmessi, sin fix en este Change.
- CA: test de contenido.

## D. Calidad, tokens y neutralidad

**R25 — Guideline TDD-DS.** `methodology.md` DEBE sumar una sección corta (≤ ~30 líneas) con: código determinista (parsers, transforms, features, métricas, validación, CLI, contratos) ⇒ test-first cuando sea razonable; exploración ⇒ no test-first (pregunta → correr → inspeccionar → formalizar invariante → test si se vuelve lógica reutilizable/productiva); modelos ⇒ no testear «accuracy == X» sino schema, no-leakage, split temporal, cotas de reproducibilidad, métricas esperadas presentes, umbrales/políticas aprobados, sin NaN/inf, invariantes; notebooks ⇒ tests sobre lógica extraída y outputs/contratos relevantes, no sobre el orden de celdas. Evals ≠ tests: los tests validan comportamiento determinista; las evals miden calidad/fitness de agentes/modelos/outputs y no son gate equivalente a un unit test sin contrato explícito. NO se crea una skill `tdd`.
- CA: test de contenido; no existe `skills/tdd.md`.

**R26 — Eficiencia de tokens.** Documentar: skills bajo demanda por puntero (no copia); contexto mínimo por instancia (solo su ownership y la sección relevante de spec/tasks); handoff corto; sin reenviar el repo; sin re-auditar; reanudar la misma instancia en vez de relanzar; el costo fijo por instancia (8 campos) es una razón para el default serial. Sin accounting nuevo.
- CA: test de contenido.

**R27 — Neutralidad de proveedor.** Los conceptos *role, writer instance, ownership, continuation, reviewer cycle, skill* DEBEN definirse sin depender de Task/Agent/SendMessage; la correspondencia con Claude Code (Agent ↔ lanzar, SendMessage ↔ reanudar) se documenta como adaptación. `skill_contract.py` y `ownership.py` no importan ni nombran proveedores.
- CA: `test_architecture_boundaries.py` verifica ambas cosas.

## E. No-regresión y límites
**R28.** `maxTurns` de los agentes, el default `max_continuaciones_por_subagente = 1`, `session_minutes` (90), los hooks (salvo R21 condicional), `pathguard`, scope/amendments (Change 3), trust tiers (Change 2) y hashing managed (Change 1) NO cambian de comportamiento. Una regresión relevante (UNA) al implementar; no full regression, no push, no Change 5.

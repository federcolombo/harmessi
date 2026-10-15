# Diseño — 20261014-composable-skills-writer-semantics

Diseño aprobado con las decisiones M1–M7 resueltas por el usuario (2026-10-14), ver `proposal.md`. Principio rector: **mínima infraestructura**; contrato + validación determinista barata donde es viable; nada de frameworks, locks ni schedulers.

## 1. Arquitectura Role / Skill / Runtime
```
Lead (Role) ── detecta necesidad ──> lee Skill (guidance) ──> delega a Role(s)
                                                              │
                                    Runtime gobernado (ds_guard, hooks, nbrunner) hace cumplir y deja evidencia
```
- **Role**: define quién trabaja, permisos, tool surface, responsabilidad, límites. Hoy: Lead (skill nativa del proveedor que *empaqueta* el rol), `python-data-engineer`, `data-science-reviewer`, `metodologo`, `notebook-runner`.
- **Skill**: conocimiento/metodología reutilizable, pequeño, markdown, bajo demanda, sin permisos/hooks/instalación/bypass/autonomía propios.
- **Runtime/Tool**: cálculo determinista, ejecución, enforcement y evidencia.
- Desambiguación de vocabulario: «skill nativa del proveedor» (mecanismo de empaquetado de `SKILL.md`) ≠ «skill componible de Harmessi» (este contrato). La primera empaqueta un Role; la segunda es guidance.
- Los `.md` de referencia existentes (`kdd.md`, `eda.md`, `methodology.md`, `sdd.md`, `verificador.md`, `decision-ledger.md`) NO se mueven ni se les agrega frontmatter en v0.10: se *clasifican* (E1 de la propuesta). Son referencias; solo lo que viva en `skills/` está bajo contrato.

## 2. Contrato de skill
Ubicación (M7.a): `.claude/skills/lead-data-scientist/skills/<name>.md`. Plantilla: `templates/skill.md`.
```
---
name: domain-modeling
purpose: <una línea>
when_to_load: <una línea>
roles: [lead-data-scientist, python-data-engineer]
artifacts: [GLOSSARY.md]
---
<cuerpo markdown: guidance>
```
| Campo | Oblig. | Consumidor real |
|---|---|---|
| `name` | sí | Doctor (= nombre de archivo), `## Skills cargados` |
| `purpose` | sí | el Lead al elegir; humano |
| `when_to_load` | sí | el Lead (disparador de carga) |
| `roles` | sí | Doctor (⊆ roles conocidos) y el Lead (a quién apuntar la skill) |
| `artifacts` | no (`[]`) | el Lead (incluir paths en scope/ownership) |
Sin más metadata (sin `version`, `priority`, `tools`, `requires`…): no tiene consumidor. Versionado = Git. Parser propio de subset YAML (líneas `clave: valor` y listas inline), stdlib-only; salida: dict + hallazgos. Roles conocidos = `lead-data-scientist` ∪ `name` de `.claude/agents/*.md`.
`ml-engineer` no existe; solo idea futura/no implementada.

**Carga**: el Lead lee la skill cuando `when_to_load` aplica; no se carga «todo siempre»; a un subagente se le da el *puntero* (campo 2 de los 8 campos) si su rol está en `roles`. **Autoridad**: una skill nunca cambia permisos, tools, scope, guardrails, lifecycle ni aprobaciones, ni salta STOPs.
**Composición**: varias skills pueden cargarse (p. ej. `problem-framing` + `domain-modeling` + `model-evaluation`) sin duplicar contexto. Precedencia ante conflicto: (1) governance/runtime, (2) contrato del rol, (3) contrato del proyecto (`CLAUDE.md`), (4) skill. Dos skills en conflicto ⇒ el Lead se detiene y consulta; no hay motor de prioridades. Traza en `tasks.md`: `## Skills cargados` (`- skill — tarea — motivo`); validación: la skill citada existe.
**Skills de proyecto**: un proyecto puede agregar `skills/<x>.md` propios (no gestionados): se validan igual y no producen drift de managed.
**Lifecycle**: ninguno; archivos versionados que cambian por Change normal.
**Preparación de Change 5**: `domain-modeling` solo necesita (a) un archivo en `skills/` con el frontmatter, (b) declarar `artifacts: [GLOSSARY.md]`, (c) el trust model vigente para `approved`. Nada de eso requiere código en este Change.

## 3. Semántica de writers
**Regla central**: *one writer = un ROL writer autorizado*, no una instancia serial. N instancias del mismo rol solo con ownership predeclarado, específico y disjunto; cada instancia conoce únicamente el suyo; no edita archivos ajenos; el Lead no escribe implementación.
**Representación (M2.a)** — sección en `tasks.md`, gramática en R10 de `spec.md`. Variante markdown aprobada por el usuario (equivalente semántico a id/role/task/owns).
```
## Ownership de writers
### W1 — python-data-engineer — T1
- tools/dsguard/foo.py
- tools/tests/test_foo.py
### W2 — python-data-engineer — T2
- tools/dsguard/bar.py
- tools/tests/test_bar.py
## Historial de ownership
- 2026-10-15 — W1 — tools/dsguard/baz.py — dependencia hallada al implementar T1
```
Se descartó JSON paralelo: `control.json` no está autenticado (nadie lo valida) y duplicaría el dato; markdown legible alcanza porque la gramática es cerrada y se parsea de forma determinista.
**Algoritmo de solape** (con comodín solo como sufijo `/**`, el solape es exacto): normalizar (`\`→`/`, casefold, sin `./`); `lit-lit`: igualdad; `lit-dir/**`: `lit.startswith(dir + "/")`; `dir1/**-dir2/**`: `dir1 == dir2` o uno es prefijo-de-directorio del otro. Instancia sin entradas, id duplicado, rol no-writer, patrón fuera de gramática o ruta protegida ⇒ hallazgo. Cobertura por scope: entrada literal ⇒ `repo.path_matches_any(entrada, alcance_efectivo)`; `dir/**` ⇒ debe existir un patrón `X/**` con `dir == X` o `dir` bajo `X`. Reutiliza `_normalizar_entrada_alcance` (rechazo de protegidas/`..`/absolutas).
**Cuándo se valida (M1.b)**: `ds_guard ownership check` (solo lectura) y dentro de `ds_guard validate` si la sección existe. Es *antes* de delegar porque el Lead lo corre antes de lanzar; no hay hook (decisión de Change 0). Límite honesto: no detecta que una instancia edite un archivo ajeno *después* (no se atribuye un cambio de working tree a una instancia); eso lo cubre el contrato, el diff por instancia que el Lead pasa al reviewer y `ALCANCE-RUTA` para el conjunto.
**Ownership vs scope**: scope = qué puede tocar el Change; ownership = subconjunto de una instancia; ownership ⊆ scope efectivo; una enmienda de scope (T1) no asigna ownership; actualizar ownership no amplía scope. Archivo adicional ⇒ el writer lo devuelve; el Lead actualiza la sección + historial *antes* de que alguien lo edite. Actualizar ownership no requiere T1 (es coordinación, no autoridad); ampliar scope sí.
**Lifecycle (M3.b)**: el Lead + `ds_guard transition` son dueños; el writer solo reporta `completed|blocked|needs-review`. Nuevo `SDD-ESTADO-DIVERGENTE` en `validate`: compara `estado:` con la última transición (o `propuesta_pendiente`). Recuperación: `transition --a <estado>` es idempotente y corre el gate (reconcilia la ventana legítima); si no es un estado alcanzable, restaurar `estado:` desde git. Se descartó el hook sobre `estado:` (bloquearía ediciones legítimas de `tasks.md`; no distingue instancias). Costo: una función pura en `sdd.py` + una llamada en `cmd_validate`.
**Concurrencia**: serial por defecto; concurrente solo con ownership válido, tareas independientes, overhead justificado y sin archivos self-governing. Sin scheduler ni locks. N roles writer distintos: no.
**Fronteras**: subagentes sin Agent; notebook writer ≠ executor; reviewer solo lectura; metodólogo = rol.

## 4. Turnos, continuaciones y reanudación
Vocabulario (R18): *continuación* ≠ *reintento* ≠ *ronda* ≠ *ciclo de reviewer*. Principio: **trabajo acotado + reanudable**, no «subir maxTurns».
Qué persiste/qué se pierde al truncar: persiste el filesystem (archivos del ownership) y lo que devuelva el proveedor; se pierde el contexto del agente salvo que se lo reanude por mensaje a la misma instancia. Por eso: preferir reanudar la misma instancia (conserva contexto, barato en tokens); relanzar desde cero solo si la sesión se cerró o la reanudación fue denegada (entonces cuenta contra el mismo tope).
Detección: marca neutral `ESTADO-AGENTE: completed|continue|blocked|needs-review` en la última línea de cada agente; ausencia = truncamiento. El Lead no depende de un campo del proveedor. Handoff mínimo: hecho, falta, cambios, evidencia/tests, próximo paso. Sin handoff válido ⇒ incompleto/candidato a continuación. Anti-loop: sin progreso útil no hay continuación; con el tope agotado no hay continuaciones ocultas (replantear, dividir, blocked o escalar). `--max-continuaciones` tiene máximo duro (5).
Reanudación (R19): leer disco → handoff ≤ ~10 líneas → verificar progreso (diff del ownership cambió / hallazgos nuevos) → reanudar misma tarea/instancia → sin progreso entre dos reanudaciones ⇒ pausa. Reviewer: continuación = mismo ciclo; un diff grande se parte en invocaciones planificadas del mismo ciclo (no cuenta como ciclo nuevo). Tope: `max_continuaciones_por_subagente` por instancia/sesión (default 1) + `--max-continuaciones N` (M4, R20). Riesgo de loop acotado por tope + guardia de progreso + presupuesto de sesión.
Hook (H1/R21): UNCONFIRMED. Solo se toca con payload real obtenido de forma natural y segura del runtime normal; si no, queda intacto y H1 es deuda verificada con tests sintéticos. No se pide captura manual al usuario.
Agentes: se agrega a writer, reviewer y metodólogo un bloque corto de presupuesto de turnos (priorizar lo bloqueante, entregar informe parcial en vez de nada, terminar con `ESTADO-AGENTE`); `maxTurns` no cambia (C5).

## 5. Sesión por wall-clock (M5.a)
Hallazgo: la derivación por policy ya existe (`autonomy.budgets.session_minutes`, `--minutos` explícito manda, fallback 90). No se toca el número ni la semántica. Se documenta: cota de seguridad ≠ cómputo efectivo; el reloj corre en esperas T1 y tests largos; expiración = el hook bloquea trabajo nuevo (allowlist `git status/diff`, `ds_guard session note|status|close`); recovery = `session close` + `session start` (acotado por `max_sessions`/`aggregate_minutes`); al abrir, estimar wall-clock incluyendo esperas. Literales 90: canónico `ds_guard.py:_BUDGET_DEFAULTS`; fallback legacy `core.py:72`; default de firma `sdd.py:784` (la CLI siempre pasa el valor); docs/plantillas. Sin refactor cosmético. Documentar: policy efectiva `session_minutes`, wall-clock, T1/tests largos/background cuentan, la expiración no invalida el trabajo previo, recovery = cerrar y abrir (evidencia: Change 3 s1→s2). Deuda residual registrada (no implementada): fallback duplicado en tres lugares, warning anticipado al Lead, pausa por espera T1. Alternativas descartadas por ahora: pausar el reloj en T1 (introduce un reloj no monotónico dependiente de un canal), nueva clave de policy (superficie sin evidencia).

## 6. Self-governing y emergencias (M6.a)
Cierre mínimo de archivos que gobiernan su propio enforcement: ver R22. Causa del incidente: un edit parcial dejó nombres sin definir ⇒ el hook, **fail-closed por diseño**, denegó toda escritura. No se cambia a fail-open (regresión de seguridad). Protocolo (8 pasos): 1) trabajo serial; 2) un único writer owner; 3) checkpoint Git limpio/conocido antes de editar; 4) modificación acotada; 5) inmediatamente smoke de sintaxis/import + tests dirigidos mínimos del propio enforcement; 6) ninguna otra escritura hasta que el smoke pase; 7) si rompe el enforcement: rollback al checkpoint conocido (`git restore -- <archivo>`) y corrección por el writer; 8) todo bypass/reparación de emergencia es excepcional, se documenta en `verification.md`, se valida después y nunca pasa a ser workflow normal (Bash NO es un escape oficial). Intervención de emergencia: condiciones estrictas de R14 (dos en un Change ⇒ pausa). Alternativa descartada: subcomando `hooks smoke` (subsistema nuevo; se reevalúa con evidencia de recurrencia).
Clasificación de incidentes: **Harmessi** = truncamiento por turnos, sesión vencida, self-locking; **entorno** = PATH de Bash, PowerShell/Git Bash/VS Code (documentado, sin fix).

## 7. Guideline TDD-DS y evals ≠ tests
Sección corta en `methodology.md` (R25), sin skill `tdd` en v0.10 (M5 de Change 0). Texto base:
- Código determinista (parsers, transforms, features, métricas, validación, CLI, contratos): test-first cuando sea razonable.
- Exploración: pregunta/hipótesis → correr → inspeccionar → formalizar invariante → test si se vuelve lógica reutilizable o productiva. Sin red-green-refactor artificial.
- Modelos: no «accuracy == 0.83»; sí schema, no-leakage, split temporal, cotas de reproducibilidad, métricas esperadas presentes, umbrales/políticas aprobados, sin NaN/inf, invariantes.
- Notebooks: tests sobre la lógica extraída y outputs/contratos relevantes, no sobre el orden de celdas.
- Evals ≠ tests: los tests validan comportamiento determinista; las evals miden calidad/fitness de agentes/modelos/outputs; una eval no es gate de unit test sin contrato explícito.

## 8. Eficiencia de tokens
Skills por puntero, no por copia; contexto mínimo por instancia; handoffs de ~10 líneas; reanudar en vez de relanzar; sin re-auditar. Más instancias multiplican el costo fijo (8 campos + lectura): razón del default serial. Sin accounting nuevo (`ds_guard session efficiency` ya existe, solo observación).

## 9. Neutralidad de proveedor
Conceptos neutrales (role, writer instance, ownership, continuation, reviewer cycle, skill). Adaptación Claude Code: lanzar = `Agent`, reanudar = `SendMessage`, skill nativa = empaquetado de `SKILL.md`. Otros proveedores: sin definición en v0.10 (no se codifica nada específico). Los módulos core nuevos no nombran proveedores.

## 10. Alternativas descartadas
Hook por instancia (decisión Change 0); JSON paralelo de ownership; registry/loader/resolver de skills; subir `maxTurns`; clave de policy para continuaciones; pausar reloj en T1; `hooks smoke`; skill nativa por directorio para skills componibles (activaría carga automática por descripción y exige `description`).

## 11. Riesgos
- H1 sin payload real ⇒ continuaciones cooperativas (documentado; R21 condicional).
- `ownership check` no atribuye ediciones a instancias ⇒ cobertura parcial (declarado).
- Contenido de tests de documentación es frágil ante reescrituras ⇒ aserciones sobre frases clave mínimas.
- Nuevos módulos en `tools/dsguard/` ⇒ manifest y tests de paridad (`test_manifest*`) deben actualizarse.
- Los `.md` y sus `.tmpl` deben quedar sincronizados (test de paridad existente).

## 12. Archivos previstos
Código nuevo: `tools/dsguard/skill_contract.py`, `tools/dsguard/ownership.py`. Código tocado: `tools/dsguard/sdd.py` (divergencia), `tools/ds_guard.py` (`ownership check`, `validate`, `--max-continuaciones`, mostrar tope), `tools/harmessi/doctor.py` (`HARMESSI-SKILL-CONTRATO`), `tools/ds_init/manifest.py` (plantilla `skill.md` y módulos), condicional `tools/dsguard/hook_presupuesto.py`. Docs/plantillas (md + `.tmpl`): `SKILL.md`, `methodology.md`, `sdd.md`, `verificador.md`, `templates/skill.md` (nuevo), `templates/tasks.md`, agentes writer/reviewer/metodólogo. `ARCHITECTURE.md`, `docs/roadmap/v0.10.md`.

## 13. Tests previstos
`test_skill_contract.py` (válido/inválido, claves prohibidas, roles, artifacts, archivo de proyecto sin drift), `test_ownership.py` (gramática, solape, vacío, duplicado, rol, scope, ejemplos del pedido), `test_sdd_estado_divergente.py` (incluye ventana de reconciliación y censo histórico), `test_ds_guard_ownership_cli.py` (exit codes, JSON, `validate`, `--max-continuaciones`), `test_doctor_skill_contract.py`, hook (condicional, fixture de payload real), `test_skill_methodology.py` (frases clave: rol vs instancia, contrato, no-autoridad, precedencia, vocabulario, emergencia, TDD-DS, evals≠tests, ausencia de la frase vieja, sin `domain-modeling`/`tdd`), `test_architecture_boundaries.py` (neutralidad y stdlib-only), `test_manifest*` (plantilla y módulos nuevos). UNA regresión relevante al final; no full regression.

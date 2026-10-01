# Verificación — 20260930-autonomous-sdd-and-remediation

## Resumen ejecutivo

Change 3 de v0.8 (SDD aprobado por el autor, 2026-09-30, incluida la decisión congelada R12a fijada
en la misma aprobación) conecta el mecanismo de política de autonomía de Change 0
(`tools/autonomy/core.py`) al ciclo SDD real que sigue el Lead: `approval_mode` (`per_change`
default backward-compatible / `checkpoints` opt-in, M7 del roadmap enmendado), checkpoints de
negocio reutilizando `PreApprovedDecision` sin crear una arquitectura de approvals paralela, budgets
configurables vía `guardrails.json` con los valores de hoy como default, presupuesto agregado como
vista derivada (sin contador paralelo) con la decisión de no-evasión R12a, límite honesto/
best-effort de subagentes concurrentes, y reescritura puntual de las plantillas administradas
(`sdd.md`/`SKILL.md`) que todavía asumían "el usuario ejecuta".

Una revisión de `data-science-reviewer` (T8, solo lectura, 1 de los 2 ciclos writer↔reviewer
autorizados) encontró 1 hallazgo BLOQUEANTE real (R12: `session start` nunca bloqueaba al alcanzar
`max_sessions`) y 2 no bloqueantes (nota de trazabilidad `design.md` D2 vs. formato real de bullet;
gap de documentación de R14 en el skill instalado) — los 3 corregidos y re-verificados por el Lead
en la misma sesión de cierre. La regresión completa final corre en verde: **2986 passed, 10
skipped, 0 failed**, corrida en 6 lotes secuenciales (mismo patrón ya aceptado en el cierre de
Change 2, reintentado sin pedir autorización de nuevo tras una interrupción por presión de memoria,
per autorización explícita del autor para este Change).

**Change 3 cumple R1-R20 con las correcciones y aclaraciones documentadas** (ver "Resultado final").

## Commits del Change (orden, rama `v0.8-dev`)

| Commit | Qué aportó |
|---|---|
| `2ec0199` | T1-T5 — `resolver_approval_mode`/`parsear_checkpoints_de_propuesta`/`presupuesto_agregado`/`chequear_limite_agregado`/subagentes concurrentes en `tools/dsguard/sdd.py`; `_resolver_budgets`/`BudgetsInvalidosError`/`cmd_init --approval-mode`/`cmd_session_aggregate` en `tools/ds_guard.py`; cierre del gap real de `decisiones_preaprobadas` nunca poblada (`cmd_approve`). 38/38 tests nuevos (23 + 15). |
| `e2f6739` | T6-T7 — edición puntual de `sdd.md`/`SKILL.md` (y sus templates fuente) para dejar de asumir "el usuario ejecuta"; `test_v08_change3_neutrality.py` nuevo (R7/R18/R19). Regresión real encontrada y corregida en la misma invocación: `sdd.py` importando `autonomy.core` rompía `test_v08_autonomy_neutrality.py` de Change 0 (regla 10 de `ARCHITECTURE.md`) — resuelto con una excepción documentada y acotada a un solo archivo, mismo patrón que la excepción de M1/datacontracts. |
| `f55ce94` | T8 — fixes de la revisión: R12 (bloqueante, `max_sessions` no bloqueaba `session start`), nota de `design.md` D2 vs. bullet real, gap de documentación de R14 en el skill instalado. |

## Resultado por requisito (R1-R20)

### §1 `approval_mode` (R1-R2)

`resolver_approval_mode(control)` (`tools/dsguard/sdd.py`) resuelve `per_change` cuando la clave
`aprobacion_modo` está ausente — verificado por `TestResolverApprovalMode` (3 tests) y, a nivel CLI,
por `TestInitApprovalMode::test_sin_flag_persiste_per_change`. `ds_guard init --approval-mode
per_change|checkpoints` (default `per_change`) persiste la clave; ningún otro comando de
`tools/ds_guard.py` la escribe (grep confirmado) — no hay vía para mutarla después de `init` (R2).
**Cumplido.**

### §2 Checkpoints de negocio (R3-R7)

`parsear_checkpoints_de_propuesta` (`tools/dsguard/sdd.py`) produce dicts con la forma exacta de
`PreApprovedDecision.to_dict()` (`decision_type="business_checkpoint"`), validados sin tocar
`tools.autonomy.core.validate_pre_approved`; un bullet mal formado nunca se agrega a la lista de
válidos, siempre produce un `Finding` (R3, tests `TestParsearCheckpointsDePropuesta`). Condicional a
`approval_mode: checkpoints` — en `per_change` ni se intenta parsear (R4,
`TestApprovePerChangeNoParseaCheckpoints`). `gate_implementacion` sin tocar sigue exigiendo
aprobación humana por hash de los 3 artefactos en ambos modos — checkpoints no reduce ese gate (R5).
Continuación automática reutiliza la fila `continue_preapproved_decision` de `POLICY_TABLE`, ya
definida por Change 0, sin tocarla (R6). Los 12 `STOP_CATALOG` nunca resuelven `proceed` bajo ningún
`approval_mode` — confirmado por `resolve_action` no aceptando `approval_mode` como parámetro
(`inspect.signature`, test `test_resolve_action_no_acepta_approval_mode`) y por iterar el catálogo
real (no hardcodeado) en `TestR7StopCatalogInmutableAnteApprovalMode` (R7). **Cumplido.**

Nota de implementación documentada (no reabre `design.md`, aprobado por hash): el ejemplo
ilustrativo de D2 (`... — tipo: business_checkpoint`) no incluye `change_id`, que `ApprovalRef`
exige como campo obligatorio — el formato real implementado lo agrega explícito (`docstring` de
`parsear_checkpoints_de_propuesta`, corregido en el commit `f55ce94` para no decir que D2 "deja el
formato a criterio del implementador" cuando en realidad da un formato literal incompleto).

### §3 Budgets configurables (R8-R9)

`_resolver_budgets(repo_root)` (`tools/ds_guard.py`) — 5 claves siempre presentes con el literal de
hoy como default (`session_minutes=90`, `remediation_max_intentos_default=2`, resto `None` = sin
límite); ausencia de `guardrails.json`/`autonomy`/`autonomy.budgets`/clave individual da
comportamiento idéntico al de antes de este Change (R8, `TestSessionStartBudgets`). Un valor
presente pero inválido (no-entero, bool, ≤0) levanta `BudgetsInvalidosError` con
`AUTONOMY-POLICY-LIMITS` (código ya reservado por Change 0), nunca tratado como ausente (R9,
`test_valor_invalido_de_policy_rechazado_no_degrada_a_default`, confirma también que no se escribió
ninguna sesión). **Cumplido.**

### §4 Presupuesto agregado (R10-R12a)

`presupuesto_agregado(control)` es una vista derivada pura sobre `control["sesiones"]`, sin
contador paralelo persistido — confirmado por `test_consulta_no_consume_sesion`/`test_session_close_
no_agrega_otra_entrada` (R10). `chequear_limite_agregado` reporta `AUTONOMY-LIMIT-AGGREGATE-BUDGET`
(código reservado desde Change 0, sin productor real hasta este Change) sin bloquear nada por sí
sola — R11 (`aggregate_minutes` es puramente informativo, nunca bloquea abrir una sesión, a
diferencia de `max_sessions`, ver abajo).

**R12/R12a (hallazgo BLOQUEANTE de T8, corregido):** la revisión encontró que `cmd_session_start`
nunca consultaba `max_sessions` antes de abrir — solo `session aggregate` (informativo) lo
reportaba; los 2 tests que debían cubrir el rechazo real documentaban el comportamiento viejo.
Corregido: `cmd_session_start` ahora llama `sdd.chequear_limite_agregado(control, {"max_sessions":
...})` ANTES de `sdd.session_start` y devuelve exit 2 sin escribir `control.json` si el máximo ya
se alcanzó — `aggregate_minutes` sigue sin bloquear (R11, a propósito, son ejes distintos). La
decisión congelada R12a (reapertura tras `pausada_bloqueada` consume una nueva unidad de
`max_sessions`) ya estaba satisfecha por construcción desde T1-T2 (`session_start` siempre hace
`sesiones.append` con un `id` nuevo, nunca resume una entrada existente) — lo que faltaba era el
enforcement a nivel CLI, ahora cerrado. La secuencia de no-evasión de 7 pasos exacta de R12a corre
en `TestNoEvasionR12a::test_secuencia_completa_de_no_evasion` (detección, capa `sdd.py`) +
`test_max_sessions_excedido_rechaza_una_session_start_adicional` (bloqueo real, capa CLI,
`test_ds_guard_budgets_cli.py`, agregado en el fix de T8). **Cumplido tras el fix.**

### §5 Subagentes concurrentes (R13-R14)

`session_note(tipo="subagente", evento="abrir"|"cerrar")` puebla `activa["subagentes"]["conteo"]`
(antes `{}` sin usar); `limite_subagentes_alcanzado(control, max_concurrentes)` consulta ese conteo
sin bloquear nada por sí sola — documentado explícitamente en múltiples puntos como autorreportado,
cooperativo, **sin enforcement técnico real** (R13, ningún docstring/mensaje sugiere lo contrario,
confirmado por el reviewer). R14 (mecanismo de autorreporte) implementado; gap real encontrado por
el reviewer y cerrado: ninguna mención en el skill instalado — sin documentación, el mecanismo
quedaría funcionalmente muerto en un proyecto real. Agregado a `SKILL.md`/`SKILL_lead_data_
scientist.md.tmpl`, sección "Gestión de sesiones", distinguiendo explícitamente el cupo de roles ya
existente (Change 0) del límite nuevo de concurrencia. **Cumplido.**

### §6 Reescritura del skill/plantillas administradas (R15-R17)

Los 4 archivos (`sdd.md.tmpl`, `SKILL_lead_data_scientist.md.tmpl`, y sus copias instaladas) ya no
contienen "el usuario ejecuta" ni "ningún agente puede correr" (grep case-insensitive del Lead, 0
coincidencias, R15-R16). Edición puntual, no reescritura completa (D6 de `design.md`) — el resto de
la estructura/numeración de ambos documentos quedó intacto, confirmado por diff. `en_verificacion`
pasa a significar "ejecución y verificación en curso a cargo del Lead" en la documentación
instalada, sin que `sdd.py` cambie su máquina de estados (`ESTADOS_VALIDOS`/`TRANSICIONES_VALIDAS`
intactas, decisión 13 del roadmap, R17). **Cumplido.**

### §7 Compatibilidad hacia atrás (R18-R19)

Ningún test preexistente a este Change fue editado, salvo `tools/tests/test_v08_autonomy_
neutrality.py` (Change 0) — modificación puntual y documentada (nueva excepción acotada a
`tools/dsguard/sdd.py`, más 1 test nuevo que confirma que la excepción es real y no un agujero), no
una relajación general de la regla; confirmado por el propio diff del commit `e2f6739` (R18). Un
`control` sin ninguna clave nueva de este Change se comporta exactamente igual que antes
(`TestR18CompatibilidadHaciaAtras`, 3 tests explícitos, más la regresión completa que no requirió
editar ningún otro test existente). `approval_mode` es un eje ortogonal al modo de autonomía —
matriz 2×2 completa confirma que el único punto de ramificación por modo sigue siendo
`resolve_action` (Change 0, sin tocar), R19. **Cumplido.**

### §8 Remediation configurable (R20)

`cmd_session_note` pasa `budgets["remediation_max_intentos_default"]` a
`sdd.session_note(..., max_intentos_remediacion=...)` — único punto del CLI que llega a
`remediation_note`; `cmd_remediation_resolve`/`cmd_remediation_extend` (funciones distintas, sin
relación con este default) quedaron sin tocar, confirmado. La firma de `remediation_note` no
cambió. **Cumplido.**

## Excepción de dirección de dependencias (regla 10 de `ARCHITECTURE.md`, enmendada)

`tools/dsguard/sdd.py` importa `autonomy.core` (bare) para reutilizar `PreApprovedDecision`/
`validate_pre_approved` — invierte la dirección "nunca al revés" que Change 0 había fijado para
`tools/autonomy`. Es una consecuencia natural del propio diseño aprobado (el docstring de Change 0
en `tools/autonomy/core.py` ya anticipaba este consumidor: "Este modulo NO consulta control.json ni
ningun archivo (eso es del Change 3)") — no una decisión material nueva, documentada como excepción
única y acotada (mismo patrón que la excepción de M1/`datacontracts` de la regla 11), tanto en
`ARCHITECTURE.md` como en `test_v08_autonomy_neutrality.py` (con un test dedicado que confirma que
la excepción es real, no un agujero, y que ningún otro archivo de los paquetes previos importa
`autonomy`).

## Ejecución real (corrida por el Lead, 2026-09-30)

Regresión completa en 6 lotes secuenciales (mismo patrón aceptado en el cierre de Change 2; el lote
5/6 fue interrumpido una vez por presión de memoria del harness y reintentado sin pedir
autorización de nuevo, per instrucción explícita del autor para este Change):

| Lote | Alcance | Resultado |
|---|---|---|
| 1/6 | `tools/autonomy tools/datacontracts tools/datasources tools/leadrun tools/dsguard` | 541 passed, 411 subtests passed (7.86s) |
| 2/6 | `tools/ds_init tools/ds_profile tools/dsimpact` | 312 passed, 5 skipped, 4 subtests passed (723.93s) |
| 3/6 | `tools/fallback tools/harmessi tools/harmessi_bench tools/modelquality tools/providers tools/qualityevidence tools/routing` | 416 passed, 8 subtests passed (581.32s) |
| 4/6 | `tools/reporting` | 842 passed, 3 skipped, 637 subtests passed (147.94s) |
| 5/6 | `tools/tests` (primeras 23 de 45) | 540 passed, 2 skipped, 38 subtests passed (676.35s) |
| 6/6 | `tools/tests` (últimas 22 de 45) | 335 passed, 9 subtests passed (263.48s) |

**Total: 2986 passed, 10 skipped, 0 failed, 1107 subtests passed** — cero fallas en el conjunto
completo del repositorio (crece sobre el baseline de `2939 passed, 10 skipped` que dejó Change 2,
consistente con las ~47 pruebas nuevas de este Change). Manifest parity: N/A — este Change no tocó
`tools/ds_init/manifest.py` (confirmado por `git diff --name-only` contra el baseline; ninguna
`EntradaManifiesto` nueva era necesaria, `sdd.py`/`ds_guard.py`/las plantillas ya estaban en el
manifiesto de Changes anteriores). `git diff --check`: sin errores de whitespace. Privacy sweep:
sin paths/nombres personales fuera de las citas de aprobación ya esperadas (grep verificado).

## Proceso de revisión (1 ronda, de 2 ciclos autorizados) y disposición de hallazgos

Una invocación de `data-science-reviewer` (T8, solo lectura), auditoría parcial (presupuesto de
turnos agotado antes del barrido completo de R14-R20) pero con evidencia concreta y verificable
para cada hallazgo. El Lead verificó cada hallazgo directamente antes de corregir, y cerró
independientemente los puntos que el reviewer marcó "no verificado en esta pasada".

**1 hallazgo BLOQUEANTE, corregido y re-verificado** (commit `f55ce94`): R12, `cmd_session_start`
nunca bloqueaba al alcanzar `max_sessions` — ver "§4" arriba para el detalle completo.

**2 hallazgos NO bloqueantes, también resueltos**: nota de trazabilidad `design.md` D2 vs. formato
real de bullet (docstring corregido, sin reabrir `design.md`); gap de documentación de R14 en el
skill instalado (agregado a `SKILL.md`/su template).

**Puntos "no verificados en esta pasada" por el reviewer, cerrados directamente por el Lead**: R7
(confirmado que el test itera el catálogo real, no una copia hardcodeada — es código del propio
Lead); R18 (confirmado por diff que `test_v08_autonomy_neutrality.py` solo ganó la excepción
documentada + 1 test nuevo, nada más tocado).

No se usó el segundo ciclo writer↔reviewer autorizado — los 3 hallazgos de la única ronda se
corrigieron directamente por el Lead (cambios acotados y ya verificados por evidencia concreta del
propio reviewer), sin necesitar una segunda pasada de revisión.

## Límites y pendientes

**Change 4 (o posterior)**
- `max_concurrent_subagents` sigue siendo un límite honesto/best-effort (R13) — sin lock técnico
  real, mismo tipo de límite ya aceptado para timeouts/sandbox en Changes 1-2. No se resuelve acá.
- El formato de bullet de checkpoints de negocio (regex fijo en `parsear_checkpoints_de_propuesta`)
  es deliberadamente simple; un formato más flexible o un parser más tolerante queda fuera de
  alcance si no hay necesidad real demostrada.
- Nota de trazabilidad de `design.md` D2 (formato de bullet) queda documentada en `tasks.md`/este
  `verification.md`, no en `design.md` mismo (ya aprobado por hash) — a considerar si un Change
  futuro decide reabrir formalmente ese artefacto.

**Fuera de alcance explícito de Change 3** (según `proposal.md`): project capabilities (M8),
fuentes externas file-backed (M9), layering de configuración (M10) — Change 4; entrenamiento
automático de modelos, selección automática de features/modelos, decidir por el humano en un STOP,
commits/tags automáticos, políticas nuevas de calidad; un lock de concurrencia real de subagentes.

## Resultado final

**Change 3 cumple R1-R20 con las correcciones y aclaraciones documentadas.**

## Addendum (2026-09-30) — corrección posterior al cierre: `aggregate_minutes` es LIMIT efectivo

**No reabre `proposal.md`/`spec.md`/`design.md`** (aprobados por hash, hashes intactos — ver
`control.json` → `aprobaciones`). Documentado acá, en `docs/roadmap/v0.8.md` y en el decision
ledger (`openspec/decisions/ledger.jsonl`, `decision_id:
20260930-aggregate-budget-limit-efectivo`), per instrucción explícita del autor de no mutar
artefactos ya aprobados.

**Qué pasó**: la aprobación humana original de Change 3 fijó explícitamente "alcanzar cualquiera de
esos límites [`max_sessions`, `aggregate_budget`] produce `checkpoint_resumable`". La
implementación de T3/T5 (este `verification.md`, sección "§4 Presupuesto agregado", texto original)
solo hizo bloquear `max_sessions` en `cmd_session_start`, dejando `aggregate_minutes` puramente
informativo (expuesto solo vía `session aggregate`, de solo lectura) — una desviación real de la
aprobación humana, no detectada por la revisión de T8 (que se enfocó en `max_sessions`, el otro eje
del mismo hallazgo) ni por el Lead al cerrar el Change. El autor la detectó después del cierre y
fijó la corrección explícitamente: **`aggregate_minutes` es un LIMIT efectivo**, igual que
`max_sessions`.

**Afirmación superseded**: en "§4 Presupuesto agregado" arriba, donde dice "`aggregate_minutes`
sigue sin bloquear (R11, a propósito, son ejes distintos)" — esa lectura de R11/R12 quedó
**superseded** por la decisión del autor. La distinción real no es "un eje bloquea y el otro no":
ambos ejes agregados (`max_sessions` y `aggregate_minutes`) bloquean `session start` al alcanzarse;
la única distinción real es entre LIMIT (ambos ejes agregados, más el LIMIT de presupuesto de
sesión individual ya existente desde antes de Change 3) y STOP (los 12 STOP materiales de Change 0,
sin tocar) — LIMIT nunca pide aprobación humana ni es STOP, STOP siempre la pide.

**Corrección aplicada** (commit corrective separado, ver `git log`): `chequear_limite_agregado`
(`tools/dsguard/sdd.py`) ya soportaba ambos ejes desde T1-T2 — no requirió ningún cambio. El fix
completo vivió en `cmd_session_start` (`tools/ds_guard.py`), que ahora pasa `aggregate_minutes`
junto con `max_sessions` al chequeo que bloquea antes de abrir una sesión nueva (antes solo pasaba
`max_sessions`). Sin contador paralelo (sigue siendo vista derivada pura sobre
`control["sesiones"]`, sin ningún campo nuevo persistido). Sin STOP nuevo, sin aprobación
automática, sin reset al cerrar/reabrir (`presupuesto_agregado` suma sobre TODAS las sesiones, sin
excepción).

**Tests nuevos** (`tools/tests/test_ds_guard_budgets_cli.py::TestAggregateMinutesLimitEfectivo`, 11
escenarios, todos end-to-end contra el CLI real como subproceso): debajo del límite abre;
exactamente en el límite bloquea (umbral `>=`); encima bloquea; varias sesiones suman; cerrar/
reabrir no resetea; IDs distintos no evaden; `max_sessions`/`aggregate_minutes` funcionan
independientemente (2 sub-tests); agregado agotado da LIMIT (`AUTONOMY-LIMIT-AGGREGATE-BUDGET`)
nunca STOP; config ausente es backward-compatible; config inválida es fail-closed. Revisión acotada
de `data-science-reviewer` sobre este fix puntual (no de todo Change 3 de nuevo).

**Regresión**: dirigida (tests nuevos + `test_autonomy_sdd.py` + `test_v08_change3_neutrality.py` +
`test_v08_autonomy_neutrality.py` + `test_remediation.py` + `test_architecture_boundaries.py`, todos
en verde) — no se repitió la regresión completa de `tools/` (no aplica ninguno de los criterios que
la exigirían: sin modificación transversal inesperada, sin riesgo transversal señalado por el
reviewer, sin gate formal que la exija para este tipo de corrección puntual post-cierre).

## Addendum (2026-09-30, continuación) — M11 (dependencias pre-aprobadas) y métricas de eficiencia

**No reabre `proposal.md`/`spec.md`/`design.md`** (hashes intactos). Documentado acá, en
`docs/roadmap/v0.8.md` (M11 y "Corrección y adenda post-cierre", punto 3) y en el decision ledger
(`decision_id: 20260930-dependency-preapproval-and-efficiency-metrics`).

**M11 — clasificación de dependencias pre-aprobadas, sin vía de instalación**:
`parsear_dependencias_preaprobadas`/`clasificar_dependencia` (`tools/dsguard/sdd.py`), persistidas
al aprobar `proposal.md` en `approval_mode: checkpoints` (mismo patrón fail-closed que checkpoints
de negocio, `cmd_approve`). Parser de rangos de versión solo-stdlib (sin agregar `packaging` como
dependencia de Harmessi), simplificado a enteros dotados (sin sufijos `rc`/`post`), documentado
como tal. Nunca inventa un código STOP nuevo: busca `"new_dependency"` en el `STOP_CATALOG` público
de `tools.autonomy.core` (corregido en la revisión: la primera versión usaba el helper privado
`_stop_code`, cruzando el límite de encapsulamiento del módulo sin necesidad — `STOP_CATALOG` solo
alcanza). Subcomando `ds_guard dependency classify --change-id <id> --nombre <n> --version <v>`,
puramente informativo. Confirmado por auditoría explícita (ya citada en el roadmap): `tools/leadrun/`
no tiene ninguna primitiva gobernada de instalación, así que M11 es solo clasificación, sin ninguna
vía de instalación real.

**Métricas de eficiencia writer→Lead**: `calcular_metricas_eficiencia` (`tools/dsguard/sdd.py`),
vista derivada sobre `control["sesiones"]`/`control["remediaciones"]` más una referencia liviana a
ejecuciones (`control["metricas_eficiencia"]["ejecuciones"]`, solo `execution_id`/
`duration_seconds`/`command_form` — nunca duplica el `ExecutionRecord` completo, que sigue viviendo
en `.harmessi/executions/`). Subcomando `ds_guard session efficiency --change-id <id>`, informativo,
nunca gate. Guía de proceso (batching por unidad de trabajo, handoffs compactos) agregada a
`SKILL.md`/su template, sección "Eficiencia writer → Lead" (idéntica en ambos archivos, confirmado).

**Hallazgo real encontrado y documentado (no bloqueante, límite honesto)**: `_ejecutar_exec_comun`
(`tools/ds_guard.py`) nunca escribía `control.json` antes de esta adenda — nada lo requería hasta
que las métricas de eficiencia necesitaron una referencia persistida. Ahora sí escribe, tras una
ejecución exitosa. La revisión acotada señaló que esto abre una ventana de lectura-modificación-
escritura más larga que la de cualquier otro comando del CLI (hasta `timeout_seconds`, sin lock de
archivo entre procesos) — documentado explícitamente en el código como límite honesto no resuelto
con un mecanismo nuevo (mismo criterio que subagentes concurrentes/R13 o timeout de proceso
huérfano/Change 2 R10), dado que el modelo operativo real de Harmessi es un único Lead invocando el
CLI de forma serial.

**Revisión acotada** de `data-science-reviewer` sobre este entregable puntual: 1 hallazgo menor
(acceso a símbolo privado `autonomy_core._stop_code`), corregido a `STOP_CATALOG` público; sin
hallazgos bloqueantes en el resto de lo revisado (parser de versiones fail-closed en ambos puntos
de entrada, fail-closed de `cmd_approve`, backward-compat de `calcular_metricas_eficiencia`,
`tools/autonomy/core.py` no tocado).

**Tests**: 75/75 en verde (`test_autonomy_sdd.py` + `test_ds_guard_budgets_cli.py` +
`test_ds_guard_exec.py`, incluye las clases nuevas `TestParsearDependenciasPreaprobadas`,
`TestClasificarDependencia`, `TestCalcularMetricasEficiencia` a nivel de `sdd.py`, y
`TestApproveConDependenciasPreaprobadas`, `TestDependencyClassifyCLI`, `TestSessionEfficiencyCLI` a
nivel de CLI end-to-end). Regresión dirigida, no completa (mismo criterio que el addendum anterior).

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

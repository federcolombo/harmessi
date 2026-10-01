# Diseño — 20260930-autonomous-sdd-and-remediation

## Decisión metodológica/técnica

**D1 — Dónde vive `approval_mode`: `control.json`, no `guardrails.json`.** Un checkpoint de negocio
se declara "en la propuesta aprobada" (M7 del roadmap) — es una propiedad de un Change concreto, no
una policy global de proyecto. `guardrails.json` (Change 0/M2) sigue siendo la policy humana global
(`autonomous`/`supervised`, límites agregados **de proyecto**, fuentes selladas); `approval_mode`
vive en `control["aprobacion_modo"]` (clave nueva, ausente ⇒ `"per_change"`), fijado en
`ds_guard init --approval-mode per_change|checkpoints` (nuevo flag opcional de `init`, default
`per_change` si se omite — mismo criterio backward-compatible que el resto).

**D2 — Checkpoints de negocio: lista dentro de `control["decisiones_preaprobadas"]`, no un array
nuevo.** Change 0 no llegó a definir dónde persiste una `PreApprovedDecision` real (quedó como tipo
sin consumidor). Este Change lo resuelve: `control.json` gana `decisiones_preaprobadas: list[dict]`
(cada elemento, la forma exacta de `PreApprovedDecision.to_dict()`), poblada al aprobar `proposal.md`
a partir de su sección `## Checkpoints de negocio` (una entrada por checkpoint declarado, formato:
lista de bullets `- **<id>**: <summary> — alcance: <scope, uno o más paths/patrones> — tipo:
business_checkpoint`, parseada por una función nueva `parsear_checkpoints_de_propuesta(texto) ->
list[dict]`, análoga en espíritu a `_contenido_de_seccion` ya existente en `sdd.py`). Un Change con
`approval_mode: per_change` tiene `decisiones_preaprobadas == []` siempre (ninguna sección que
parsear). El mismo campo sirve para cualquier `PreApprovedDecision` futura que no sea un checkpoint
de negocio (p. ej. una decisión metodológica pre-aprobada, M3) — un solo array, discriminado por
`decision_type`, no dos estructuras paralelas.

**D3 — Continuación entre checkpoints: marca de "checkpoint resuelto" en `session_note`.** Cuando el
Lead llega a un checkpoint declarado y `resolve_action("continue_preapproved_decision", modo)`
permite continuar (política en `autonomous`, propuesta+aprobación humana en `supervised`), se
registra con `session_note(..., tipo="planificada", tarea=f"checkpoint:{decision_id}")` — reutiliza
el mecanismo de bookkeeping ya existente (`activa["tareas"]`), sin un campo nuevo de "checkpoints
resueltos" en la sesión. La trazabilidad de qué checkpoint se resolvió y cuándo queda en
`sesiones[].tareas` (ya versionado) y, para el caso `supervised`, en la aprobación humana que lo
habilitó (mismo patrón `approved_by`/`human_approval_ref` de `PolicyApproval`).

**D4 — Presupuesto agregado: función pura `presupuesto_agregado(control) -> dict`, en
`tools/dsguard/sdd.py` (mismo módulo que `session_status`, no un archivo nuevo).** Devuelve
`{"minutos_consumidos_totales": float, "sesiones_totales": int, "sesiones_abiertas": int}`, sumando
`minutos_consumidos`/`len(sesiones)` de `control["sesiones"]` — para una sesión todavía activa
(`estado_final == "activa"`), sus minutos consumidos se calculan igual que `session_status` (ahora
menos inicio). Sin escritura, sin estado nuevo persistido: se recalcula en cada llamada, igual que
`session_status` ya hace con la sesión individual.

**Decisión congelada (aprobación humana 2026-09-30) sobre reapertura tras `pausada_bloqueada`,
R12a de `spec.md`:** `sesiones_totales = len(control["sesiones"])` ya satisface la regla sin
ingeniería adicional, porque `session_start` (`tools/dsguard/sdd.py:642-686`, sin tocar su
mecanismo) **siempre** hace `sesiones.append(entrada)` con un `id` nuevo — nunca reutiliza ni
resume una entrada existente, incluida una reapertura tras `pausada_bloqueada`. Una consulta de
status y un checkpoint resuelto sin abrir sesión no llaman a `session_start`, así que no inflan
`sesiones_totales` por construcción. `max_sessions` (R8-R9) se compara contra `sesiones_totales` de
esta función, no contra un contador aparte — mismo principio de "vista derivada, no contador
paralelo" aplicado también a este caso.

**D5 — Budgets de policy: `autonomy.budgets` en `guardrails.json`, con validación en
`ds_guard.py` (no en `autonomy/policy.py`).** `tools/autonomy/policy.py` es de Change 0, cerrado, y
su `parse_autonomy_policy` no valida claves que no conoce (las ignora, documentado ya como
comportamiento fail-open aceptado a nivel de claves desconocidas para no romper forward-compat de
policies futuras — a diferencia de `version`, que sí es fail-closed). Este Change agrega la lectura y
validación de `autonomy.budgets` como una función nueva en `ds_guard.py` (mismo patrón que
`_resolver_aprobacion_exec` de Change 2: composición en el CLI, no en el paquete `autonomy`),
devolviendo los defaults hardcodeados de hoy cuando la clave está ausente o inválida (fail-closed
sobre valores inválidos concretos — un `session_minutes: -5` se rechaza, no se trata como ausente).

**D6 — `max_concurrent_subagents`: autorreporte vía `session_note(tipo="subagente", evento="abrir"|
"cerrar")`.** Nuevo valor de `tipo` (además de `"planificada"|"reintento"|"ronda"` existentes),
incrementa/decrementa `activa["subagentes"]["conteo"]` (entero, reemplaza el `{}` sin usar). El Lead
consulta `session_status()["subagentes"]` antes de invocar el tool `Agent`; si el conteo ya iguala el
máximo configurado, no invoca y lo reporta. Es cooperativo: nada impide técnicamente que el Lead
omita el autorreporte — se documenta como límite honesto (R13 de `spec.md`), igual que "sin sandbox"
en Changes 1/2.

## Target (condicional)

N/A.

## Features permitidas/prohibidas (condicional)

N/A.

## Estrategia de split/validación (condicional)

N/A.

## Leakage risks (condicional)

N/A — Change de infraestructura/gobernanza SDD, no toca datos ni modelado.

## Reproducibilidad (opcional)

Sin aleatoriedad nueva; ningún `RANDOM_STATE` involucrado.

## Alternativas descartadas

- **Un tipo `BusinessCheckpoint` nuevo, separado de `PreApprovedDecision`.** Descartado: duplicaría
  exactamente la validación de `scope`/`approval_ref` que `PreApprovedDecision` ya tiene, y crearía
  una segunda forma de aprobación pre-registrada — contradice directamente "no crear una arquitectura
  de approvals paralela" (instrucción explícita del autor) y la decisión 15 del roadmap.
- **Presupuesto agregado como contador persistido, actualizado en cada `session_note`.** Descartado:
  es exactamente la "segunda tabla de contadores" que `docs/roadmap/v0.8.md` § "Deuda que v0.8 no
  debe crear" prohíbe — puede desincronizarse de `sesiones[]` si una escritura falla a mitad de
  camino; una vista derivada no tiene ese riesgo por construcción.
- **`max_concurrent_subagents` como lock real (semáforo en disco, `.harmessi/locks/`).** Descartado
  para este Change: el harness no tiene un mecanismo confiable para detectar que un subagente
  efectivamente terminó (el Lead puede perder la referencia sin llamar "cerrar"); un lock que puede
  quedar huérfano es peor que un contador honesto y best-effort. Queda como límite documentado, no
  como deuda oculta.
- **`approval_mode` en `guardrails.json` (policy de proyecto) en vez de `control.json` (por
  Change).** Descartado: el propio encargo dice "el humano aprueba inicialmente... checkpoints de
  negocio declarados" **en la propuesta** — es una propiedad del Change, no del proyecto; un proyecto
  puede tener Changes en `per_change` y otros en `checkpoints` simultáneamente sin contradicción.
- **Reescribir `sdd.md.tmpl`/`SKILL.md.tmpl` a un formato completamente nuevo.** Descartado: se
  edita el texto puntual que asume ejecución humana (R15-R17), se preserva el resto de la
  estructura — consistente con "cambios pequeños/snippets sobre reescrituras completas" (`CLAUDE.md`
  §3) y con que el vocabulario SDD es aditivo (decisión 13 del roadmap).

## Riesgos

- **`decisiones_preaprobadas` mal parseada desde `proposal.md` en texto libre.** Un formato de bullet
  ambiguo puede fallar en parsear un checkpoint real o, peor, parsear algo no-intencionado como
  checkpoint válido. Mitigación: `validate_pre_approved` ya rechaza cualquier forma que no tenga los
  4 campos exigidos (R3 de `spec.md`) — un parseo defectuoso produce un hallazgo, no un checkpoint
  fantasma aceptado en silencio.
- **Confusión entre presupuesto de sesión (ya existente) y presupuesto agregado (nuevo).** Mitigación:
  nombres de código distintos y sin superposición (`SESION-LIMITE-*` vs
  `AUTONOMY-LIMIT-AGGREGATE-BUDGET`), y `presupuesto_agregado()` nunca escribe — solo lee.
- **`max_concurrent_subagents` da una falsa sensación de enforcement real.** Mitigación: R13 lo
  declara explícitamente honesto/best-effort en `spec.md`, la ayuda del CLI lo repite, mismo patrón
  ya aceptado para timeouts/sandbox en Changes 1/2 — no es deuda nueva, es el mismo tipo de límite ya
  documentado en el roadmap.
- **Reescribir `sdd.md.tmpl`/`SKILL.md.tmpl` rompe una instalación existente que ya editó esos
  archivos localmente.** Mitigación: son managed files con hash — `harmessi doctor` ya reporta drift
  si el proyecto los editó; este Change no cambia esa mecánica, y Change 4 (M10, layering de config)
  es quien agrega la vía soportada de customización sin drift.
- **`parse_autonomy_policy` (Change 0, cerrado) ignora claves desconocidas** — si `autonomy.budgets`
  se declarara mal tipado (p. ej. como string en vez de dict), hoy no lanzaría desde `policy.py`. Se
  resuelve en D5: la validación de `autonomy.budgets` vive en `ds_guard.py`, no depende de que
  `policy.py` la entienda — evita tener que reabrir Change 0 para esto.

## Aprobación humana

Ver `proposal.md` § "Aprobación" — único registro, no se duplica acá.

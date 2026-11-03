# Spec — 20260930-autonomous-sdd-and-remediation

Notación: `Rn` con criterio verificable, `Given/When/Then` cuando aplica. Ningún requisito reabre
`tools/autonomy/core.py`, `tools/autonomy/policy.py`, `tools/datasources/*` ni `tools/leadrun/*`
(Changes 0-2, cerrados) — todo lo de acá compone esos módulos sin modificarlos, salvo que un
requisito diga explícitamente lo contrario.

## 1. `approval_mode`

**R1 — Vocabulario y default.** `approval_mode` ∈ {`per_change`, `checkpoints`}. Ausente en
`control.json` ⇒ `per_change` (idéntico al comportamiento de hoy).
- Given un `control.json` sin la clave `approval_mode` (cualquier Change existente, incluidos
  Change 0/1/2 ya cerrados), When se lee, Then se resuelve como `per_change` y ningún gate/transición
  cambia de comportamiento respecto de hoy.

**R2 — Inmutable tras `aprobada_implementacion`.** Cambiar `approval_mode` después de que la
propuesta fue aprobada es STOP 11 (`scope_expansion`) — no hay una transición ni un comando que lo
permita silenciosamente.
- Given un Change en `en_implementacion` con `approval_mode: per_change`, When se intenta declarar
  `approval_mode: checkpoints`, Then la operación se rechaza con el mismo código que usa el resto del
  contrato para expansión de scope.

## 2. Checkpoints de negocio

**R3 — Un checkpoint de negocio es un `PreApprovedDecision`.** `decision_type ==
"business_checkpoint"` (valor nuevo del vocabulario `known_types` que ya recibe
`validate_pre_approved` como parámetro inyectado — `tools/autonomy/core.py:571`, sin tocar la
función). No se crea ningún tipo de dato nuevo; se reutiliza `PreApprovedDecision.scope`/`.summary`/
`.approval_ref` tal cual.
- Aceptación: un checkpoint declarado en `proposal.md` § "Checkpoints de negocio" se parsea a un
  `PreApprovedDecision(decision_type="business_checkpoint", ...)` válido según
  `validate_pre_approved` sin hallazgos, y su `approval_ref.artefacto == "proposal.md"` (mismo
  requisito que ya impone `_scope_item_detail`/la validación de `approval_ref` para cualquier
  `PreApprovedDecision`, `tools/autonomy/core.py:600-611`).

**R4 — Condicional a `approval_mode: checkpoints`.** La sección "Checkpoints de negocio" de
`proposal.md` solo es obligatoria (y solo se valida) cuando `approval_mode: checkpoints`; en
`per_change` la sección no existe o se ignora.

**R5 — Aprobación humana inicial obligatoria en ambos modos.** `checkpoints` no reduce el gate de
`gate_implementacion` (`tools/dsguard/sdd.py:235-284`, sin tocarlo): sigue exigiendo aprobación
humana registrada por hash de `proposal.md`/`spec.md`/`design.md` (modo completo) antes de
`en_implementacion`. No hay autonomía sin una concesión humana trazable — mismo principio que M3.
- Given `approval_mode: checkpoints` sin aprobación humana de `proposal.md` registrada, When se
  intenta `transition --a aprobada_implementacion`, Then falla exactamente igual que hoy
  (`APROB-AUSENTE`), sin ninguna vía alternativa.

**R6 — Continuación automática entre checkpoints.** Reutiliza la fila `continue_preapproved_decision`
de `POLICY_TABLE` (`tools/autonomy/core.py:190-191`, ya definida por Change 0, sin tocarla): en
`autonomous`, `executor="lead"`, `approval="policy"` — el Lead continúa sin pedir confirmación humana
por paso; en `supervised`, `executor="lead"`, `approval="human"` — el Lead propone continuar y el
humano aprueba. Un checkpoint declarado y alcanzado se resuelve por esta fila, nunca por una vía
nueva.
- Given un checkpoint `business_checkpoint` con `approval_ref` válida y modo `autonomous`, When el
  Lead llega al punto declarado, Then continúa sin STOP y sin pedir confirmación, dejando constancia
  (`session note`) de qué checkpoint resolvió.
- Given el mismo caso en `supervised`, When el Lead llega al checkpoint, Then propone continuar y
  espera aprobación humana antes de seguir — no continúa solo.

**R7 — Los checkpoints nunca reemplazan los 12 STOP materiales.** Test que itera
`tools.autonomy.core.STOP_CATALOG` (los 12, sin hardcodear la lista en el test — se lee del propio
catálogo) y confirma que, para cada `StopEntry`, ninguna combinación de `approval_mode` (`per_change`
o `checkpoints`) puede producir `outcome="proceed"` para la acción correspondiente — el `outcome` de
las filas STOP de `POLICY_TABLE` (`access_sealed`, `provide_secret`, `install_dependency`,
`write_outside_scope_or_source_or_raw`, `remediation_extend`, `decide_unlisted_methodological`) sigue
siendo `stop_human` en ambos modos, sin excepción, porque `approval_mode` no es un parámetro de
`resolve_action` (`tools/autonomy/core.py:244`) — este Change no le agrega uno.

## 3. Budgets configurables

**R8 — Extensión aditiva de `guardrails.json`.** Nueva clave opcional `autonomy.budgets` (bajo la
misma policy de Change 0, parseada por `autonomy.policy.parse_autonomy_policy` — sin tocar ese
módulo: la extensión vive en el llamador, `ds_guard.py`, mismo patrón que Change 1/2 compusieron
`autonomy.policy` sin modificarla): `session_minutes`, `aggregate_minutes`, `max_sessions`,
`max_concurrent_subagents`, `remediation_max_intentos_default`. Ausente cualquiera de ellas ⇒ el
valor hoy hardcodeado (`session_minutes=90`, `max_sessions`=sin límite/∞, `remediation_max_intentos_
default=2`, `max_concurrent_subagents`=sin límite/∞, `aggregate_minutes`=sin límite/∞) — cero cambio
de comportamiento sin declarar la clave.
- Given un `guardrails.json` sin `autonomy.budgets` (o sin `autonomy` en absoluto — caso ya cubierto
  por Change 0), When se abre una sesión sin pasar flags explícitos, Then el resultado es
  bit-a-bit idéntico al de antes de este Change.

**R9 — Fail-closed ante un valor de budget inválido.** Un `autonomy.budgets` con un valor no-entero,
negativo o cero para cualquier clave es un error de policy (mismo criterio fail-closed que M2/Change
0: una policy que la versión instalada no puede interpretar correctamente no degrada en silencio) —
se rechaza con un código `AUTONOMY-POLICY-*` existente (no se crea un código nuevo si alguno de los
ya definidos aplica; si ninguno aplica, se documenta en `design.md` cuál se agrega, dentro del
registro único ya existente).

## 4. Presupuesto agregado

**R10 — Vista derivada, no contador paralelo.** El presupuesto agregado (tiempo total consumido,
cantidad de sesiones abiertas) se calcula sumando `control["sesiones"]` en el momento de la consulta
— mismo patrón que `session_status` deriva `minutos_transcurridos` de la sesión activa
(`tools/dsguard/sdd.py:805-824`). No se persiste un contador agregado separado que pueda
desincronizarse de `sesiones[]`.
- Aceptación: una función pura `presupuesto_agregado(control) -> dict` (nueva, en `sdd.py` o un
  módulo hermano — nombre exacto en `design.md`) que, dado un `control["sesiones"]` con 3 sesiones
  cerradas de 40/30/25 minutos, devuelve `minutos_consumidos_totales == 95` sin leer ningún campo
  fuera de `sesiones[]`.

**R11 — Agotar el agregado produce checkpoint resumible, nunca STOP ni aprobación automática.**
Reutiliza `AUTONOMY-LIMIT-AGGREGATE-BUDGET` (`tools/autonomy/core.py:77,106-108`, ya reservado, sin
tocar el módulo) como el código que se reporta. Mismo LÍMITE vs STOP que Change 0 ya fijó: agotar el
agregado no exige una decisión humana por sí solo — termina la sesión con un checkpoint resumible; si
coincide con una condición STOP real (p. ej. el propio Change 0 STOP 8, remediation agotada), ese
STOP se reporta aparte, no lo genera el budget.
- Given un agregado configurado en 60 minutos y 95 minutos ya consumidos entre sesiones, When se
  intenta abrir una sesión nueva, Then se permite abrir (el LÍMITE no bloquea *abrir*, ver R12) pero
  el estado se reporta como agregado excedido, con checkpoint resumible sugerido en vez de una
  pregunta de aprobación.

**R12 — Los topes agregados no se evaden encadenando sesiones.** El agregado se calcula sobre TODAS
las sesiones de `control["sesiones"]`, cerradas o no — abrir una sesión nueva no resetea el consumo
ya registrado.
- Given un `max_sessions` configurado en 3 y ya hay 3 sesiones en `control["sesiones"]`
  (cerradas o no), When se intenta `session start` una cuarta, Then se rechaza con el código de
  límite agregado correspondiente (no es un `SESION-*` de sesión individual, ver R9 para el registro
  de códigos).

**R12a — Reapertura tras `pausada_bloqueada` (decisión congelada, aprobación humana 2026-09-30, ya
no es punto abierto).** Una reapertura de una sesión que llegó a `pausada_bloqueada` por agotamiento
de un LIMIT **consume una nueva unidad de `max_sessions`**, sin importar si internamente se reutiliza
el mismo `id` de sesión o se crea uno nuevo — la métrica cuenta **ventanas efectivas de ejecución**,
no `id`s físicos. Motivo: `max_sessions`/`aggregate_budget` existen para impedir que la autonomía se
extienda indefinidamente encadenando ventanas; permitir que una reapertura no cuente sería exactamente
esa evasión.

Congelado, sin excepción:

- una consulta/status (`session_status`, `presupuesto_agregado`) **no** consume sesión;
- cerrar una sesión (`session_close`) **no** consume otra;
- un checkpoint puramente informativo (continuar por `continue_preapproved_decision` sin abrir una
  sesión nueva) **no** consume sesión;
- una reapertura después de `pausada_bloqueada` **sí** consume una nueva ventana de `max_sessions`;
- no se puede resetear `max_sessions` cerrando y reabriendo;
- `aggregate_budget` sigue sumando el consumo real acumulado (R10), sin importar cuántas ventanas de
  `max_sessions` se hayan usado;
- alcanzar `max_sessions` o `aggregate_budget` produce `checkpoint_resumable` (LIMIT, R11), **nunca**
  aprobación automática;
- solo un STOP real (STOP_CATALOG, R7) requiere decisión humana — agotar un LIMIT no la convierte en
  una.

Aceptación — secuencia de no-evasión, explícita y obligatoria (no se satisface con un test genérico):

1. abrir una sesión con `max_sessions=2` configurado, agotar su LIMIT individual (p. ej. tiempo);
2. la sesión pasa a `pausada_bloqueada` (transición ya existente, sin cambios);
3. reabrir (nueva `session start` sobre el mismo Change);
4. verificar que el consumo de `max_sessions` incrementó (de 1 a 2 ventanas efectivas) — no quedó en
   1 por reutilizar el mismo Change ni por ser una "continuación" conceptual;
5. repetir agotar → pausar → reabrir hasta alcanzar el máximo configurado (2 en este caso);
6. confirmar que una reapertura adicional (la 3ª ventana) queda bloqueada por el código de límite
   agregado — no se abre una sesión nueva;
7. confirmar que ese bloqueo es un LIMIT (`AUTONOMY-LIMIT-AGGREGATE-BUDGET` o el que corresponda a
   `max_sessions`, ver R9) — nunca se transforma en un STOP del catálogo ni exige aprobación humana
   por sí solo (una aprobación humana solo entraría si, aparte, se pidiera `remediation extend` o
   equivalente — no es lo que este test verifica).

## 5. Subagentes concurrentes (límite honesto, best-effort)

**R13 — Sin lock técnico real.** El harness no tiene una primitiva de concurrencia visible a
`control.json`; `max_concurrent_subagents` es **autorreportado por el Lead**, no forzado por un
mecanismo técnico — mismo criterio honesto que "sin timeout en proceso" (Change 1, R17) y "sin
sandbox" (Change 1/2, límites documentados). Se documenta así explícitamente en `design.md` y en la
ayuda del CLI; no se afirma enforcement que no existe.

**R14 — Mecanismo de autorreporte.** Extiende `session_note` (`tools/dsguard/sdd.py:689-744`, sin
romper su firma actual: parámetros nuevos con default que preservan el comportamiento de cualquier
llamador existente) para poblar `activa["subagentes"]` (hoy `{}` sin usar, `sdd.py:678`) — el nombre
exacto de los parámetros/valores queda para `design.md`. Antes de convocar un subagente nuevo, el
Lead consulta el conteo actual contra `max_concurrent_subagents`; si excede, no convoca y reporta el
límite — el mismo patrón de "consultar antes de actuar" que ya usa para budgets de sesión.

## 6. Reescritura del skill/plantillas administradas

**R15 — `sdd.md.tmpl` no asume ejecución humana.** El texto "El usuario ejecuta y trae el output al
chat" (`.claude/skills/lead-data-scientist/sdd.md:72,106`, y su fuente
`tools/ds_init/profiles/python_jupyter_data/templates/sdd.md.tmpl`) se reemplaza por la referencia al
runtime gobernado de Change 2 (`ds_guard exec ...`) y a la resolución de `approval_mode`/política de
este Change — sin inventar un mecanismo nuevo de ejecución (Change 2 ya cerrado, se compone, no se
reabre).
- Aceptación: grep de `tools/ds_init/profiles/**/*.tmpl` y de `.claude/skills/lead-data-scientist/`
  no encuentra la cadena "el usuario ejecuta" (case-insensitive) tras este Change.

**R16 — `SKILL.md.tmpl` no asume que ningún agente puede ejecutar.** El texto de
`.claude/skills/lead-data-scientist/SKILL.md:154` ("ejecutar algo que ningún agente puede correr en
esta versión") ya no aplica desde Change 2 — se actualiza la condición de pausa correspondiente para
reflejar que el Lead ejecuta vía `ds_guard exec ...`, y que una pausa por ejecución hoy solo aplica a
un STOP material real (dependencia nueva, secreto, etc.), no a la ausencia de un ejecutor.

**R17 — `en_verificacion` no espera al usuario.** Coherente con la decisión 13 del roadmap
(vocabulario aditivo, sin estados nuevos): `en_verificacion` pasa a significar "ejecución y
verificación en curso, el Lead ya no espera al usuario" en la documentación instalada — `sdd.py` no
cambia su máquina de estados (`ESTADOS_VALIDOS`/`TRANSICIONES_VALIDAS` intactas, R2 del roadmap ya lo
exige).

## 7. Compatibilidad hacia atrás

**R18 — Un Change v0.7/v0.8 preexistente no cambia de comportamiento.** Ningún test existente de
`tools/tests/test_ds_guard.py`, `tools/dsguard/tests/*` (o su ubicación real — confirmar en el audit
de implementación) que ejercite `transition`/`session_start`/`session_note`/`remediation_note` sin
los parámetros nuevos de este Change cambia de resultado.
- Aceptación: la regresión completa existente (2939 passed antes de este Change, ver
  `openspec/changes/20260929-lead-execution-runtime/verification.md`) sigue pasando sin editar
  ningún test preexistente, solo agregando los nuevos.

**R19 — `supervised` no se duplica.** `approval_mode` es un eje ortogonal a `autonomous`/
`supervised` — no hay código específico de un `approval_mode` que rame según el modo de autonomía
fuera de consultar `POLICY_TABLE` (ya existente). Test de matriz 2×2 (`per_change`/`checkpoints` ×
`autonomous`/`supervised`) que confirma que el único punto de ramificación por modo sigue siendo
`resolve_action` (Change 0, sin tocar).

## 8. Remediation configurable

**R20 — `remediation_note` lee el default de policy, no un literal hardcodeado en el CLI.** El
parámetro `max_intentos_default: int = 2` de `remediation_note` (`tools/dsguard/sdd.py:468`, firma
sin cambios) pasa a recibir, desde `ds_guard.py`, el valor de
`autonomy.budgets.remediation_max_intentos_default` si está declarado, o `2` si no — el mecanismo de
ventanas/intentos de `remediation_note`/`remediation_extend` no cambia (siguen siendo siempre humano
para extender, R2 de Change 0, sin reabrir).

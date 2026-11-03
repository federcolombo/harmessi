# Propuesta — 20260910-decision-ledger-bounded-remediation

## Problema
Las decisiones de fondo del proyecto (target, cutoff, métrica primaria, baseline, umbrales,
excepciones metodológicas, etc.) hoy solo quedan documentadas en texto libre disperso dentro de
`proposal.md`/`design.md` de cada cambio SDD o en el chat — no hay un artefacto único, consultable
entre cambios, que registre qué se decidió, por qué, y si sigue vigente. Además, el mecanismo de
reintentos actual (`control["sesiones"][].reintentos`, `tools/dsguard/sdd.py`) es un contador
agregado por sesión sin causa/cambio aplicado/resultado por hallazgo, y sin distinguir un retry
técnico transitorio de una corrección de bug, de una remediación metodológica o de un cambio de
enfoque que en realidad requiere una decisión nueva.

## Objetivo
Agregar dos capacidades acotadas y complementarias: (1) un decision ledger append-only en
`openspec/decisions/ledger.jsonl` para decisiones de fondo explícitas, y (2) bounded remediation
(`control["remediaciones"]`) para limitar y trazar intentos de corrección por finding, evitando
loops de reintento indefinidos.

## Evidencia
- `tools/dsguard/sdd.py` (`session_note`, `chequear_limites`): `reintentos`/`rondas_revision` son
  enteros agregados por sesión, sin causa/cambio aplicado/resultado ni `finding_id` asociado.
- `tools/dsguard/hook_presupuesto.py` (`evaluar`): el único hook `PreToolUse` real sobre
  `Agent|SendMessage|Write|Edit|Bash|PowerShell` enforcea tiempo/continuaciones, nunca
  `reintentos`.
- `.claude/skills/lead-data-scientist/sdd.md` §4-5: `proposal.md`/`design.md` llevan la única
  sección "Aprobación" del cambio, en texto libre, sin tipo de decisión, sin mecanismo de
  supersede/revocación, sin índice entre cambios.
- No existe en el repo ningún archivo bajo `openspec/decisions/` ni campo `control["remediaciones"]`
  en ningún `control.json` existente (confirmado por auditoría completa del repo, sesión previa).

## Supuestos descartados
- Se creía que `sesiones[].reintentos`/`rondas_revision` ya daban trazabilidad suficiente de
  remediación — la auditoría confirmó que son solo contadores, sin `finding_id`/causa/resultado por
  intento.
- Se evaluó un ledger de remediación global nuevo (paralelo al decision ledger) — se descartó a
  favor de reusar `control.json` del cambio, preferencia explícita del usuario.
- Se evaluó guardar `estado` (activa/superseded/revocada) como campo mutable en cada entrada del
  decision ledger — se descartó por crear una segunda fuente de verdad; se deriva siempre por
  escaneo del archivo completo.
- Se evaluó `remediation reset` (reinicio de contador) — el usuario lo rechazó explícitamente a
  favor de `remediation extend` (ventanas acumulativas, nunca se borran intentos previos).

## Hipótesis (condicional — solo cambios metodológicos)
No aplica — cambio técnico de tooling/harness, sin decisión de ML de fondo.

## Alcance
- Nuevo módulo `tools/dsguard/decision.py` (ledger de decisiones: `add`/`supersede`/`revoke`/
  `list`/`show`, lectura tolerante, escritura fail-closed, estado derivado).
- Extensión de `tools/dsguard/sdd.py`: `control["remediaciones"]` con ventanas de intentos por
  finding, tipos `retry_tecnico|bug|metodologica`, `remediation_resolve`, `remediation_extend`.
- Nuevos subcomandos en `tools/ds_guard.py`: `decision {add,supersede,revoke,list,show}`,
  `remediation {resolve,extend}`, y flags nuevos (`--finding-id`, `--remediation-tipo`, `--causa`,
  `--cambio-aplicado`, `--resultado`) en `session note --tipo reintento`.
- Extensión mínima de `tools/dsguard/hook_presupuesto.py`: deniega `Agent` nuevo si
  `reintentos >= max_reintentos` de la sesión activa (agregado, no por finding).
- Tests: `tools/tests/test_decision.py`, `tools/tests/test_remediation.py`.
- Documentación: `.claude/skills/lead-data-scientist/decision-ledger.md` (nuevo), actualización de
  `sdd.md` §8, `SKILL.md` (referencias), `verificador.md` (comandos y códigos de hallazgo nuevos).

## Fuera de alcance
- Reporting, multi-provider, `ds_profile`, Project EDA (excluidos explícitamente por el usuario).
- Persistencia de findings de reviewer/metodólogo como artefacto propio (siguen efímeros; ver
  deuda v0.3+ en `design.md`).
- Enforcement en tiempo real por finding específico dentro del hook (el hook solo mira el agregado
  de sesión, nunca `finding_id`).
- Cualquier comando `remediation status` separado o nuevo hook dedicado — se extiende el hook
  existente, no se crea uno nuevo.

## Holdout policy (condicional — solo cambios "sensible")
No aplica — cambio técnico de tooling/harness, sin decisión de ML de fondo.

## Impacto en production-readiness (opcional)
No aplica (etapa futura del catálogo KDD, sin gates activos en v0.2).

## Criterios de aceptación (spec-lite — solo SDD abreviado)
No aplica — este cambio usa SDD completo; ver `spec.md`.

## Decisión técnica (design-lite — solo SDD abreviado)
No aplica — este cambio usa SDD completo; ver `design.md`.

## Aprobación
- Usuario: federico.colombo (vía chat, sesión Claude Code)
- Fecha: 2026-09-10
- Alcance aprobado: diseño completo del decision ledger y bounded remediation para el Bloque 5 de
  Harmessi v0.2.0, según la propuesta presentada por el Lead en el chat y los 14 puntos de ajuste
  indicados explícitamente por el usuario en su mensaje de aprobación (tipos de remediación
  `retry_tecnico|bug|metodologica` vía `--remediation-tipo`; comando `remediation resolve`; renombre
  de `remediation reset` a `remediation extend` con semántica de ventanas append-only; mantener
  `sesiones[].reintentos` como freno agregado documentado aparte de `remediaciones[]`; extensión
  acotada de `hook_presupuesto.py` solo al agregado de sesión; tests adicionales; regresión
  completa de la suite).
- Versión de artefactos referenciada: diseño presentado en el chat inmediatamente antes del mensaje
  de aprobación del usuario del 2026-09-10.
- Cita o descripción fiel de qué se aprobó: "Aprobado el diseño del Bloque 5 con estos ajustes
  antes de implementar." — mensaje completo del usuario, con los 14 puntos numerados (DECISION
  LEDGER 1-3, BOUNDED REMEDIATION 4-12, TESTS 13-14), tomado como especificación literal.

## Motivo de rechazo
No aplica — cambio aprobado, no descartado.

## Desacuerdo registrado
No aplica — aprobado en la primera ronda, sin desacuerdo pendiente.

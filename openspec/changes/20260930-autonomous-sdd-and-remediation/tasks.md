---
estado: aprobada_implementacion
---

# Tareas — 20260930-autonomous-sdd-and-remediation

`T0` ya está hecha (audit de lectura, evidencia citada en `proposal.md`). `T1..Tn` son invocaciones
futuras del `python-data-engineer`, en orden de dependencia: el schema de `control.json` primero
(nada más depende de él), presupuesto agregado y budgets de policy en paralelo conceptual pero
secuenciados porque ambos tocan `sdd.py`, subagentes concurrentes después (depende de
`session_note` ya extendido), CLI después de tener algo que exponer, plantillas al final porque
citan el mecanismo ya construido, tests de repo/neutralidad intercalados, revisión y regresión
completa solo en el gate de cierre — **ninguna tarea de esta lista se ejecuta todavía; este
documento es el plan, no la implementación** (fuera de alcance de esta invocación).

## T0 — Audit (hecho, Lead, solo lectura)

- [x] Confirmar el texto literal "El usuario ejecuta y trae el output al chat" en
  `.claude/skills/lead-data-scientist/sdd.md:72,106`.
- [x] Confirmar el texto de pausa en `.claude/skills/lead-data-scientist/SKILL.md:154`.
- [x] Leer `tools/dsguard/sdd.py` completo (estados, gates, sesiones, remediation).
- [x] Leer `tools/autonomy/core.py` completo (`POLICY_TABLE`, `PreApprovedDecision`,
  `LIMIT_CATALOG`, `STOP_CATALOG`).
- Evidencia de todo lo anterior: `proposal.md`, sección "Evidencia".

## T1 — Schema de `control.json` y checkpoints (`tools/dsguard/sdd.py`)

**[hecho]** `resolver_approval_mode`, `parsear_checkpoints_de_propuesta` implementadas en
`tools/dsguard/sdd.py`; tests en `tools/tests/test_autonomy_sdd.py` (13/13 pasan, corridos por el
Lead). `presupuesto_agregado`/`chequear_limite_agregado` de T2 implementadas en la misma invocación
(ambas tareas comparten módulo, se hicieron juntas).

- `control["aprobacion_modo"]` (R1 de `spec.md`); `control["decisiones_preaprobadas"]` (D2 de
  `design.md`); `parsear_checkpoints_de_propuesta(texto) -> tuple[list[dict], list[Finding]]` (nota:
  devuelve tupla `(checkpoints_validos, hallazgos)`, no solo la lista — decisión de implementación,
  más explícita que descartar hallazgos en silencio); validación de cada entrada vía
  `tools.autonomy.core.validate_pre_approved` (sin tocar ese módulo).
- **Nota de implementación — formato real del bullet de checkpoint, corrige el ejemplo ilustrativo
  de `design.md` D2 (no reabre la decisión, el formato exacto siempre quedó delegado a esta etapa):**
  el ejemplo de D2 (`- **<id>**: <summary> — alcance: ... — tipo: business_checkpoint`) no puede
  producir un `PreApprovedDecision` válido — le falta `change_id`, que
  `ApprovalRef`/`_validar_ref` de `tools/autonomy/core.py` (`_REF_CLAVES = ("artefacto",
  "change_id", "hash")`) exige como clave obligatoria; con ese formato ningún checkpoint pasaría
  nunca `validate_pre_approved` sin hallazgos, contradiciendo el criterio de aceptación de R3.
  Formato real implementado: `- **<id>**: <resumen> — alcance: <ruta1>, <ruta2> — aprobacion:
  <change_id>/proposal.md@<hash-sha256>`. `id` no es un campo de `PreApprovedDecision.to_dict()` —
  se embebe como prefijo de `summary`; `artefacto` siempre `"proposal.md"` literal; `decision_type`
  siempre `"business_checkpoint"` (ambos hardcodeados, nunca leídos del bullet). Se documenta acá en
  vez de editar `design.md` (ya aprobado por hash) — detalle completo repetido en `verification.md`
  de cierre.
- QA: round-trip de parseo; caso con formato ambiguo produce hallazgo, no checkpoint fantasma;
  `approval_mode` ausente resuelve `per_change`.
- **Pendiente de una invocación posterior (T5, CLI):** R2 (rechazar cambiar `approval_mode` tras
  `aprobada_implementacion`) y la escritura real de `control["decisiones_preaprobadas"]` en disco al
  aprobar `proposal.md` — ninguno de los dos tiene hoy un punto de enganche en `sdd.py` sin tocar el
  CLI; `sdd.py` en esta invocación solo expone las funciones puras, no decide cuándo persistir ni
  cuándo rechazar un cambio de modo.

## T2 — Presupuesto agregado (`tools/dsguard/sdd.py`)

**[hecho, misma invocación que T1]** `presupuesto_agregado`/`chequear_limite_agregado`
implementadas; test de la secuencia de 7 pasos de R12a (`TestNoEvasionR12a`) pasa, corrido por el
Lead junto con los otros 12 tests de `test_autonomy_sdd.py`.

- `presupuesto_agregado(control) -> dict` (D4, R10-R12 de `spec.md`), vista derivada pura sobre
  `control["sesiones"]`; código `AUTONOMY-LIMIT-AGGREGATE-BUDGET` reportado al exceder, sin STOP ni
  aprobación automática.
- QA: suma correcta sobre sesiones cerradas y una activa; `max_sessions` no se resetea al abrir una
  sesión nueva; **secuencia de no-evasión obligatoria de R12a (decisión congelada por aprobación
  humana 2026-09-30), los 7 pasos exactos**: (1) agotar el LIMIT de una sesión, (2) confirmar
  `pausada_bloqueada`, (3) reabrir, (4) confirmar que `max_sessions` incrementó, (5) repetir hasta el
  máximo configurado, (6) confirmar que una reapertura adicional queda bloqueada, (7) confirmar que
  el bloqueo es LIMIT (`checkpoint_resumable`), nunca STOP ni aprobación humana automática. También:
  consulta/status no consume sesión; `session_close` no consume otra; un checkpoint resuelto sin
  abrir sesión no consume sesión.

## T3 — Budgets de policy (`tools/ds_guard.py`)

**[hecho]** `_resolver_budgets`/`BudgetsInvalidosError` implementadas; `cmd_session_start`/
`cmd_session_note` las consumen. Código fail-closed de R9: `autonomy_core.CODE_POLICY_LIMITS`
(`AUTONOMY-POLICY-LIMITS`). Tests del Lead en `tools/tests/test_ds_guard_budgets_cli.py`, 11/11
pasan (compartido con T5, mismo archivo).

- Lectura/validación de `autonomy.budgets` (D5, R8-R9 de `spec.md`) — nueva función en `ds_guard.py`,
  no en `tools/autonomy/policy.py`; fail-closed sobre valores inválidos, default = literales de hoy
  si la clave está ausente.
- `session_start`/`remediation_note` reciben el valor resuelto (firma sin cambios, solo el caller
  cambia qué literal pasa) — R20 de `spec.md`.
- QA: sin `autonomy.budgets`, comportamiento bit-a-bit idéntico a hoy (R8); valor inválido rechazado,
  no tratado como ausente (R9).

## T4 — Subagentes concurrentes (`tools/dsguard/sdd.py`)

**[hecho]** `session_note(tipo="subagente", ...)`, `limite_subagentes_alcanzado` implementadas.
Tests agregados a `tools/tests/test_autonomy_sdd.py` por el Lead (writer no tenía herramienta de
ejecución, no quiso entregar tests sin poder correrlos — correcto). 23/23 pasan (archivo completo).

- `session_note(tipo="subagente", evento="abrir"|"cerrar")` (D6, R13-R14 de `spec.md`), puebla
  `activa["subagentes"]["conteo"]`; `session_status()` expone el conteo.
- QA: conteo sube/baja correctamente; documentación explícita (docstring + ayuda CLI) de que es
  autorreportado, sin enforcement técnico (R13).

## T5 — CLI (`tools/ds_guard.py`)

**[hecho]** `ds_guard init --approval-mode per_change|checkpoints` y `ds_guard session aggregate
--change-id <id> [--json]` implementados. `decisiones_preaprobadas` NO se pobla en `init` (D2 fija
que se puebla al aprobar `proposal.md`, no al crear el scaffold) — cerrado por el Lead directamente
en `cmd_approve` (`tools/ds_guard.py`): si se aprueba `proposal.md` y `approval_mode ==
"checkpoints"`, se parsea la sección de checkpoints y se persiste en
`control["decisiones_preaprobadas"]` (reemplaza en cada re-aprobación, no acumula); un checkpoint
inválido rechaza la aprobación completa (fail-closed, R3). En `per_change` no se parsea nada, ni
siquiera si la sección existe por error. Tests del Lead, 15/15 en
`tools/tests/test_ds_guard_budgets_cli.py` (T3+T5+este cierre, mismo archivo).

- `ds_guard init --approval-mode per_change|checkpoints` (default `per_change`); superficie para
  consultar `decisiones_preaprobadas`/presupuesto agregado (subcomando exacto a definir en esta
  invocación, mismo patrón `--json` + exit codes 0/2/3 del resto del CLI).
- QA: `init` sin `--approval-mode` se comporta igual que hoy.

## T6 — Plantillas administradas (`tools/ds_init/profiles/python_jupyter_data/templates/`)

- `sdd.md.tmpl`: reemplazar el texto de R15 citando el runtime de Change 2 y `approval_mode` de este
  Change; mismo criterio de edición puntual que D6 de `design.md` fija (no reescritura completa).
- `SKILL_lead_data_scientist.md.tmpl`: reemplazar el texto de R16.
- Sincronizar las copias instaladas del propio repo (`.claude/skills/lead-data-scientist/sdd.md`,
  `SKILL.md`) con las plantillas actualizadas (mismo patrón ya usado en Changes previos para
  archivos administrados que Harmessi también instala sobre sí mismo).
- QA: grep de "el usuario ejecuta" (case-insensitive) sobre `tools/ds_init/profiles/**` y
  `.claude/skills/lead-data-scientist/` da cero resultados (R15).

## T7 — Tests de repo y neutralidad

- Test de matriz 2×2 `approval_mode` × modo de autonomía (R19); test de que los 12 `STOP_CATALOG`
  nunca resuelven `proceed` bajo ningún `approval_mode` (R7); test de compatibilidad hacia atrás
  sobre los tests existentes de `sdd.py` (R18, sin editar ninguno).
- `ARCHITECTURE.md`: actualizar solo si esta invocación efectivamente cambia la clasificación de
  algún módulo (probable que no — `sdd.py` ya está clasificado como core; a confirmar en la
  invocación, no acá).

## T8 — Revisión (data-science-reviewer, solo lectura)

- Revisar T1-T7 contra `spec.md` completo (R1-R20) y contra los riesgos de `design.md`.
- Verificar en particular: R7 (los 12 STOP nunca se vuelven `proceed`), R18 (cero tests existentes
  editados), R13 (límite de subagentes declarado honesto, no sobrevendido).

## T9 — Cierre (Lead)

- Gate final: regresión completa (una sola invocación, `.venv/Scripts/python -m pytest tools -q` —
  o en lotes secuenciales documentados, patrón ya aceptado en Change 2 si hay presión de memoria).
- `verification.md` de cierre con evidencia por R1-R20.
- `docs/roadmap/v0.8.md`: tildar Change 3 en el checklist de estado, solo tras aprobación humana de
  este `proposal.md`.

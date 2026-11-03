# Propuesta — 20260910-sincronizar-plantillas-bloque5

## Problema
El Bloque 5 (`20260910-decision-ledger-bounded-remediation`, ya cerrado) modificó
`.claude/skills/lead-data-scientist/{SKILL.md,sdd.md,verificador.md}` y creó
`.claude/skills/lead-data-scientist/decision-ledger.md`, pero nunca tocó las plantillas
instalables de `ds_init` (`tools/ds_init/profiles/python_jupyter_data/templates/*.tmpl`). Un
proyecto nuevo instalado hoy con `ds_init` no recibiría la documentación de decision ledger ni de
bounded remediation en su scaffold inicial. `check_manifest_parity` ya señalaba
`sdd.md.tmpl`/`SKILL_lead_data_scientist.md.tmpl`/`verificador.md.tmpl` como `PLANTILLA` a
revisar a mano, y en efecto están desactualizadas frente a sus archivos vivos.

## Objetivo
Sincronizar el contenido de Bloque 5 hacia las plantillas instalables correspondientes, y crear
la plantilla que falta para `decision-ledger.md` (archivo nuevo sin contraparte `.tmpl` todavía),
registrándola en `tools/ds_init/manifest.py`.

## Evidencia
- `diff sdd.md.tmpl sdd.md`: falta toda la subsección "### Bounded remediation" agregada bajo §8
  por Bloque 5 (36 líneas).
- `diff SKILL_lead_data_scientist.md.tmpl SKILL.md`: faltan dos agregados puntuales — referencia a
  `decision-ledger.md` en "Rol y límites permanentes", y nota sobre `control["remediaciones"]` en
  "Límite de intentos". El placeholder `{{NOMBRE_PROYECTO}}` ya existe correctamente en el
  `.tmpl` (no se toca, no se reemplaza por "harmessi").
- `diff verificador.md.tmpl verificador.md`: faltan los comandos `decision *`/`remediation
  {resolve,extend}`, la nota de exit codes, los 14 códigos de hallazgo nuevos, y la documentación
  del campo `remediaciones[]` en `control.json`.
- `.claude/skills/lead-data-scientist/decision-ledger.md` no tiene ninguna referencia literal al
  nombre del proyecto ("harmessi") — puede copiarse verbatim como plantilla, sin placeholders,
  mismo criterio que ya usan `kdd.md.tmpl`/`verificador.md.tmpl` (ambos sin placeholders).
- `tools/ds_init/manifest.py` (`MANIFEST`) no tiene ninguna entrada con destino
  `.claude/skills/lead-data-scientist/decision-ledger.md`.
- `kdd.md.tmpl` y los 4 `agent_*.tmpl` no requieren cambios: Bloque 5 no tocó `kdd.md` ni ningún
  archivo de agente (confirmado por diff, sin diferencias).

## Supuestos descartados
- Se creía que `check_manifest_parity` marca las plantillas como "en verde" cuando su contenido
  está sincronizado — la lectura del código (`check_manifest_parity.py`,
  `listar_plantillas()`) mostró que la lista de entradas `PLANTILLA` es **incondicional**: lista
  siempre todas las entradas con ese tratamiento, sin comparar contenido ni hash. No hay un
  estado "pendiente" que limpiar — la lista de `sdd.md.tmpl`/`SKILL_lead_data_scientist.md.tmpl`/
  `verificador.md.tmpl` (y `decision-ledger.md.tmpl`, si se agrega) va a seguir apareciendo
  siempre en `[INFO]`, por diseño. Lo verificable es que el *contenido* de cada `.tmpl` sea fiel
  al archivo vivo correspondiente — eso es lo que se corrige acá.

## Alcance
- `tools/ds_init/profiles/python_jupyter_data/templates/sdd.md.tmpl`: agregar la subsección
  "### Bounded remediation" faltante.
- `tools/ds_init/profiles/python_jupyter_data/templates/SKILL_lead_data_scientist.md.tmpl`:
  agregar los dos fragmentos faltantes, preservando `{{NOMBRE_PROYECTO}}` intacto.
- `tools/ds_init/profiles/python_jupyter_data/templates/verificador.md.tmpl`: agregar los
  comandos, exit codes, códigos de hallazgo y el campo `remediaciones[]` faltantes.
- Nuevo `tools/ds_init/profiles/python_jupyter_data/templates/decision-ledger.md.tmpl` (copia
  verbatim de `decision-ledger.md`, sin placeholders) + nueva entrada en `MANIFEST`
  (`tools/ds_init/manifest.py`), tratamiento `PLANTILLA`, destino
  `.claude/skills/lead-data-scientist/decision-ledger.md`.

## Fuera de alcance
- El gap de `ds_guard scope add` (control de alcance de un cambio) — deuda v0.3+, no se toca acá.
- Persistencia de findings de reviewer/metodólogo como artefacto propio — deuda v0.3+.
- Enforcement por finding específico dentro de `hook_presupuesto.py` — deuda v0.3+.
- Hash/cadena de integridad del decision ledger — deuda v0.3+.
- Validación de doble `supersede`/`revoke` sobre una `referencia` ya afectada — deuda v0.3+.
- Comportamiento de `retry_tecnico` sin `--finding-id` — deuda v0.3+, no se cambia.
- `kdd.md.tmpl`, los 4 `agent_*.tmpl`, `nbrunner_manifest.py.tmpl`: sin cambios, Bloque 5 no los
  tocó.
- Reporting, multi-provider, `ds_profile`, Project EDA.

## Hipótesis (condicional)
No aplica — cambio técnico de tooling/harness (sincronización de plantillas), sin decisión de ML
de fondo.

## Holdout policy (condicional)
No aplica — cambio técnico de tooling/harness (sincronización de plantillas), sin decisión de ML
de fondo.

## Impacto en production-readiness (opcional)
No aplica.

## Criterios de aceptación (spec-lite — solo SDD abreviado)
No aplica — este cambio usa SDD completo; ver `spec.md`.

## Decisión técnica (design-lite — solo SDD abreviado)
No aplica — este cambio usa SDD completo; ver `design.md`.

## Aprobación
- Usuario: federico.colombo (vía chat, sesión Claude Code)
- Fecha: 2026-09-10
- Alcance aprobado: sincronizar `sdd.md.tmpl`/`SKILL_lead_data_scientist.md.tmpl`/
  `verificador.md.tmpl` con el contenido vivo de Bloque 5; crear `decision-ledger.md.tmpl` y
  registrarlo en el manifiesto; correr `tools/ds_init/tests`, `tools/tests`,
  `tools/harmessi/tests`, `check_manifest_parity` y `harmessi doctor`; revisar qué artefactos de
  `openspec/` corresponde versionar; sin tocar la deuda v0.3+ explícitamente excluida.
- Versión de artefactos referenciada: pedido del usuario en el chat del 2026-09-10, inmediatamente
  después del cierre de Bloque 5.
- Cita o descripción fiel de qué se aprobó: "Antes de commitear el Bloque 5, corregí únicamente
  la paridad del scaffold instalable" — mensaje completo del usuario, puntos 1-5, con la lista
  explícita de exclusiones ("No tocar: el gap futuro de ds_guard scope add; findings
  persistentes; enforcement por finding en hook; integridad/hash del ledger; doble
  supersede/revoke; retry_tecnico sin finding-id").

## Motivo de rechazo
No aplica — cambio aprobado, no descartado.

## Desacuerdo registrado
No aplica — aprobado en la primera ronda.

---
name: nombre-de-skill
purpose: Una línea: qué guía aporta esta skill y para qué tipo de trabajo.
when_to_load: Una línea: condición concreta bajo la cual el Lead debe cargarla.
roles: [lead-data-scientist]
artifacts: []
---

# nombre-de-skill

Plantilla de skill componible. Copiar a `.claude/skills/lead-data-scientist/skills/<name>.md`,
renombrar `name` (kebab-case, igual al nombre del archivo) y reemplazar este cuerpo.

## Reglas del contrato

- Una skill es guidance, nunca authority. No define ni concede tools, permissions, hooks,
  instalación de dependencias, scope, guardrails, aprobaciones, lifecycle, delegación ni
  ejecución.
- Precedencia ante conflicto: governance/runtime > contrato del rol > contrato del proyecto >
  skill. La skill nunca relaja una regla de nivel superior.
- Cargar solo cuando aplica (ver `when_to_load`); no cargar por defecto.
- Registrar cada skill cargada en la sección `## Skills cargados` de `tasks.md`
  (`- <skill> — <tarea> — <motivo>`).

## Guía

Contenido de la skill: criterios, checklists y advertencias en español, sin instrucciones
de ejecución ni de cambio de permisos.

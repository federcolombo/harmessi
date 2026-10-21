# Propuesta — 20261021-v012-skill-selection-composition

## Problema
Con cuatro skills distribuidas (`domain-modeling`, `problem-framing`, `diagnosing-bugs`, `codebase-design`) falta una regla clara de selección (cuáles cargar y cuáles no), de composición (cuándo dos a la vez) y de traza (cuándo registrar). Hoy: la traza `## Skills cargados` existe y se valida, pero su criterio es vago («si afecta decisiones o delegación»); el conflicto entre skills se resuelve con «el Lead se detiene y consulta»; el párrafo de skills en `SKILL.md` creció sin estructura.

## Objetivo
Hacer observable y predecible el uso de skills sin runtime nuevo: tabla de selección, carga mínima (menos contexto/tokens), composición simple por pares, conflicto resuelto semánticamente por el Lead dentro de las capas superiores, traza solo cuando la skill influye materialmente.

## Evidencia (auditoría)
- `skill_contract.referencias_skills_cargados` / `validar_referencias_skills`: la traza se parsea y valida solo existencia (`SKILL-REFERENCIA-DESCONOCIDA`); `templates/tasks.md` y `sdd.md` contienen la sección.
- `methodology.md` §28: «Dos skills en conflicto: el Lead se detiene y consulta»; ARCHITECTURE §7.2 idem. v0.12 pide que el Lead resuelva semánticamente sin violar capas superiores (D2 del roadmap).
- `SKILL.md` sección «Skills componibles»: un párrafo único con cuatro skills.

## Supuestos descartados
- Resolver de dependencias, grafo, registry, marketplace, plugins dinámicos, merge engine, telemetría: descartados.
- Nuevo código de validación o nuevos códigos de hallazgo: descartado; la mejora es de criterio (docs) más un test determinista que exige que toda skill distribuida figure en la tabla de selección.

## Alcance
`SKILL.md` (reorganizar la sección de skills), `methodology.md` §28 + nueva §40, `sdd.md`, `templates/tasks.md`, `ARCHITECTURE.md`, espejos `.tmpl`, tests de docs/contrato, roadmap.

## Fuera de alcance
Cambios en `skill_contract.py`, Doctor, manifest, hooks, permisos, roles, frontmatter; nuevas skills.

## Aprobación
- Usuario:
- Fecha:
- Alcance aprobado:
- Versión de artefactos referenciada:
- Cita o descripción fiel de qué se aprobó:

## Alcance autorizado

- .claude/skills/lead-data-scientist/SKILL.md
- .claude/skills/lead-data-scientist/methodology.md
- .claude/skills/lead-data-scientist/sdd.md
- .claude/skills/lead-data-scientist/templates/tasks.md
- tools/ds_init/profiles/python_jupyter_data/templates/SKILL_lead_data_scientist.md.tmpl
- tools/ds_init/profiles/python_jupyter_data/templates/methodology.md.tmpl
- tools/ds_init/profiles/python_jupyter_data/templates/sdd.md.tmpl
- tools/tests/test_skill_methodology.py
- tools/tests/test_skill_contract.py
- tools/tests/test_architecture_boundaries.py
- tools/ds_init/tests/test_manifest.py
- tools/harmessi/tests/test_doctor_skill_contract.py
- ARCHITECTURE.md
- docs/roadmap/v0.12.md
- openspec/changes/20261021-v012-skill-selection-composition/**

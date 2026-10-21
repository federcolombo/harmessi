# Propuesta — 20261021-v012-roadmap-and-dx-skills-audit

> Change 0 de v0.12 («Data Scientist Experience & Composable Skills»): auditoría de skills/DX y congelamiento de roadmap. Solo docs/SDD: NO implementa nada.

## Problema
Las skills diferidas (`problem-framing`, `diagnosing-bugs`, `codebase-design`) y la noción de «qué puede evolucionar» del harness no están definidas. Sin auditar
lo existente (foundation de skills v0.10, traza `## Skills cargados`, `domain-modeling`, metodólogo, reviewer, Impact Preflight) se arriesga duplicar
capacidades con otro nombre.

## Objetivo
Auditar contra `main` (`917339f`), confirmar qué ya existe y congelar un roadmap v0.12 mínimo, ordenado y con boundaries.

## Evidencia
- `tools/dsguard/skill_contract.py`: frontmatter cerrado (`CLAVES_OBLIGATORIAS/OPCIONALES/PROHIBIDAS`), `referencias_skills_cargados`, `validar_referencias_skills`.
- `.claude/skills/lead-data-scientist/methodology.md` §27–§28 (Role/Skill/Runtime, contrato, composición, conflicto = «el Lead se detiene y consulta», traza).
- `templates/tasks.md` y `sdd.md` ya contienen `## Skills cargados`.
- `tools/ds_init/manifest.py` registra `skills/domain-modeling.md`; Doctor `_ARCHIVOS_SKILL_ESPERADOS` y `HARMESSI-SKILL-CONTRATO` (WARN).
- `grep` de grill/framing/diagnos/codebase-design en skills, agentes y ARCHITECTURE: sin skill ni mecanismo equivalente.

## Supuestos descartados
- Que hiciera falta metadata nueva (`surface`) en el frontmatter: la superficie se deriva de la ruta.
- Que la traza de skills no existiera: existe y se valida.
- Que hiciera falta un runtime de selección: la selección es juicio del Lead sobre `when_to_load`.

## Alcance
`docs/roadmap/v0.12.md`, línea v0.12 en `docs/roadmap/README.md` y este SDD. Changes 1–6 con objetivo, scope, boundaries, dependencias y aceptación.

## Fuera de alcance
Implementar Changes 1–6; tocar `tools/**`, hooks, templates, manifest; roadmaps completos de v0.13/v0.14 (solo dirección registrada); versión, tag, push.

## Aprobación
- Usuario:
- Fecha:
- Alcance aprobado:
- Versión de artefactos referenciada:
- Cita o descripción fiel de qué se aprobó:

## Alcance autorizado

- docs/roadmap/v0.12.md
- docs/roadmap/README.md
- openspec/changes/20261021-v012-roadmap-and-dx-skills-audit/**

# Propuesta — 20261021-v012-codebase-design

## Problema
Antes de una modificación estructural (nuevo módulo, mover responsabilidades, cambiar un contrato interno) no hay guidance reutilizable para razonar sobre boundaries, acoplamiento, primitivas existentes y radio de impacto; el riesgo es duplicar, crear wrappers innecesarios o abrir un framework sin consumidor.

## Objetivo
Crear la skill componible `codebase-design`: razonamiento previo a cambios estructurales con la preferencia reuse > extend > new local primitive > new subsystem/framework. Asesora; no decide permisos ni runtime.

## Evidencia
- Auditoría Change 0: no existe skill equivalente; `ds_guard impact scan` / `methodology.md` §25 dan el impact preflight pero no el criterio de diseño; `ARCHITECTURE.md` §3 ya fija reglas de dependencia del propio Harmessi.

## Supuestos descartados
- Reimplementar el impact preflight: descartado, se usa `ds_guard impact scan`.
- Que la skill decida arquitectura o aprobaciones: descartado; el Lead/humano deciden, el SDD registra.

## Alcance
`skills/codebase-design.md`, manifest, Doctor, SKILL.md/methodology/ARCHITECTURE y espejos, tests.

## Fuera de alcance
Frontmatter nuevo, roles, hooks, permisos, selección/composición (Change 5), runtime nuevo, refactors del código de Harmessi.

## Aprobación
- Usuario:
- Fecha:
- Alcance aprobado:
- Versión de artefactos referenciada:
- Cita o descripción fiel de qué se aprobó:

## Alcance autorizado

- .claude/skills/lead-data-scientist/skills/codebase-design.md
- .claude/skills/lead-data-scientist/SKILL.md
- .claude/skills/lead-data-scientist/methodology.md
- tools/ds_init/profiles/python_jupyter_data/templates/SKILL_lead_data_scientist.md.tmpl
- tools/ds_init/profiles/python_jupyter_data/templates/methodology.md.tmpl
- tools/ds_init/manifest.py
- tools/harmessi/doctor.py
- tools/ds_init/tests/test_manifest.py
- tools/ds_init/tests/test_glossary_install.py
- tools/harmessi/tests/test_doctor_skill_contract.py
- tools/tests/test_skill_contract.py
- tools/tests/test_skill_methodology.py
- tools/tests/test_architecture_boundaries.py
- tools/tests/test_v010_release_hardening_smoke.py
- tools/tests/test_v011_release_hardening_smoke.py
- ARCHITECTURE.md
- docs/roadmap/v0.12.md
- openspec/changes/20261021-v012-codebase-design/**

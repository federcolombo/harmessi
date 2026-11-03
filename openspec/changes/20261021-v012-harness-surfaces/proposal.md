# Propuesta — 20261021-v012-harness-surfaces

## Problema
Harmessi no tiene un vocabulario explícito de qué partes del harness pueden evolucionar metodológicamente y cuáles jamás deben auto-modificarse. Sin él, una skill puede
declarar como `artifacts` un archivo de gobernanza (guardrails, hooks, contratos de rol) y el contrato actual no lo detecta.

## Objetivo
Formalizar tres superficies — *Protected*, *Optimizable*, *Project-owned* — derivarlas de la ruta (sin metadata nueva) y usarlas en una validación estructural barata del contrato de skill.

## Evidencia
- `tools/dsguard/skill_contract.py`: `_validar_artifacts` solo rechaza comodines y rutas inválidas; no mira qué superficie referencia.
- `ARCHITECTURE.md` §7 y `methodology.md` §27–§28 definen Role/Skill/Runtime pero no superficies.
- `.claude/`, `tools/`, `.ds_init/`, `.harmessi/` concentran enforcement y gobernanza; `skills/*.md`, `methodology.md`, `eda.md`, `kdd.md` son guidance.

## Supuestos descartados
- Campo `surface` en el frontmatter: descartado (campo ornamental; la superficie se deriva de la ruta).
- Policy engine o enforcement nuevo: descartado; solo un hallazgo estructural en el validador existente (Doctor lo expone como WARN).

## Alcance
Documentar el modelo (ARCHITECTURE, methodology, SKILL.md, plantilla de skill, verificador); función pura `superficie_de_ruta` y hallazgo `SKILL-ARTIFACT-SUPERFICIE-PROTEGIDA` en `skill_contract.py`; tests; paridad md↔tmpl.

## Fuera de alcance
Optimizer, runtime auto-modificable, candidate/probe engine, marketplace, policy engine, campos de frontmatter nuevos, cambios en hooks/permisos/roles, cambios en `ds_guard validate` más allá de lo que ya consume el validador.

## Aprobación
- Usuario:
- Fecha:
- Alcance aprobado:
- Versión de artefactos referenciada:
- Cita o descripción fiel de qué se aprobó:

## Alcance autorizado

- tools/dsguard/skill_contract.py
- tools/ds_guard.py
- tools/harmessi/doctor.py
- tools/harmessi/tests/test_doctor_skill_contract.py
- tools/tests/test_skill_contract.py
- tools/tests/test_skill_methodology.py
- tools/tests/test_architecture_boundaries.py
- tools/ds_init/tests/test_manifest.py
- ARCHITECTURE.md
- .claude/skills/lead-data-scientist/methodology.md
- .claude/skills/lead-data-scientist/SKILL.md
- .claude/skills/lead-data-scientist/verificador.md
- .claude/skills/lead-data-scientist/templates/skill.md
- tools/ds_init/profiles/python_jupyter_data/templates/methodology.md.tmpl
- tools/ds_init/profiles/python_jupyter_data/templates/SKILL_lead_data_scientist.md.tmpl
- tools/ds_init/profiles/python_jupyter_data/templates/verificador.md.tmpl
- docs/roadmap/v0.12.md
- openspec/changes/20261021-v012-harness-surfaces/**

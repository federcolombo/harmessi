# Propuesta — 20261021-v012-problem-framing

## Problema
Antes de construir o analizar algo, el Lead no tiene guidance reutilizable para hacer explícitos objetivo, decisión a soportar, unidad de análisis, población, target, restricciones,
criterios de éxito, evidencia, incógnitas y supuestos. Las ambigüedades de negocio ya tienen `domain-modeling`; falta el nivel previo (formulación del problema) y un modo opcional para
desafiar la definición cuando el humano lo pide.

## Objetivo
Crear la skill componible `problem-framing` con `grill-me` como modo opt-in interno (no otra skill), sin duplicar GLOSSARY ni Decision Ledger.

## Evidencia
- Auditoría de Change 0 (`docs/roadmap/v0.12.md`): no existe skill ni mecanismo equivalente; `domain-modeling.md` cubre solo semántica de negocio; `metodologo` cubre diseño experimental/leakage.
- Foundation: `skill_contract.py`, `templates/skill.md`; distribución por `tools/ds_init/manifest.py` y control de existencia por Doctor `_ARCHIVOS_SKILL_ESPERADOS`.

## Supuestos descartados
- Skill de interrogatorio obligatorio: descartado; solo se pregunta lo material.
- `grill-me` como skill aparte: descartado; es un modo.

## Alcance
`skills/problem-framing.md` (contrato válido, guidance), manifest, Doctor, referencias en `SKILL.md`/`methodology.md`/`ARCHITECTURE.md` y espejos `.tmpl`, tests de contrato/manifest/docs.

## Fuera de alcance
Frontmatter nuevo, roles, hooks, permisos, GLOSSARY o ledger nuevos, selección/composición (Change 5), motor de preguntas, evals.

## Aprobación
- Usuario:
- Fecha:
- Alcance aprobado:
- Versión de artefactos referenciada:
- Cita o descripción fiel de qué se aprobó:

## Alcance autorizado

- .claude/skills/lead-data-scientist/skills/problem-framing.md
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
- openspec/changes/20261021-v012-problem-framing/**

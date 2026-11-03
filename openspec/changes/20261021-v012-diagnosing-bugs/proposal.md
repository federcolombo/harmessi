# Propuesta — 20261021-v012-diagnosing-bugs

## Problema
Ante un fallo (test roto, pipeline que no corre, resultado inesperado) el Lead/writer tienden a prueba y error. No hay guidance reutilizable para un diagnóstico sistemático que separe síntoma de causa raíz, ni para atribuir un fallo durante un Change (¿lo introduje yo o ya estaba?) sin correr baselines masivos.

## Objetivo
Crear la skill componible `diagnosing-bugs`: reproduce → minimize → classify → hypothesis → instrument → test hypothesis → fix root cause → regression test → verify; con clases de fallo y clasificación baseline-aware focalizada (introduced / pre-existing / environment / inconclusive).

## Evidencia
- Auditoría Change 0: no existe skill equivalente; `methodology.md` §29 (TDD) cubre tests pero no el diagnóstico; `SKILL.md` limita reintentos/remediation sin guiar el diagnóstico previo.
- Lección v0.11: un fallo durante un Change debe evaluarse contra baseline de forma focalizada antes de atribuirlo.

## Supuestos descartados
- Debugger propio o runner nuevo: descartado (se usan `ds_guard exec` y tests existentes).
- Reemplazar tests o reviewer: descartado.
- Baseline masivo: descartado; solo focalizado.

## Alcance
`skills/diagnosing-bugs.md`, manifest, Doctor, referencias en `SKILL.md`/`methodology.md`/`ARCHITECTURE.md` y espejos, tests.

## Fuera de alcance
Frontmatter nuevo, roles, hooks, permisos, topes de remediation, selección/composición (Change 5), nuevo runtime.

## Aprobación
- Usuario:
- Fecha:
- Alcance aprobado:
- Versión de artefactos referenciada:
- Cita o descripción fiel de qué se aprobó:

## Alcance autorizado

- .claude/skills/lead-data-scientist/skills/diagnosing-bugs.md
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
- openspec/changes/20261021-v012-diagnosing-bugs/**

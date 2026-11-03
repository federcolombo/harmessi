# Propuesta — 20261021-v012-release-hardening

## Problema
Cerrados los Changes 0–5, falta el hardening de release de v0.12.0: versión, notas, baseline managed, smoke, regresión completa, fresh install, upgrade público v0.11.0 → v0.12.0, Doctor, privacidad y dogfooding con workflows realistas de Data Science.

## Objetivo
Preparar y verificar `0.12.0` sin features nuevas.

## Evidencia
Patrón de v0.11 Change 6 (`20261020-v011-release-hardening`): versión, notas en inglés, smoke de release, baseline regenerado una vez, regresión por batches seriales, dogfooding con fixtures sintéticos.

## Supuestos descartados
- Framework de evals: descartado (evals ≠ tests); los dogfoods registran observaciones cualitativas y los tests validan contrato/estructura.
- Declarar «self-improving harness»: descartado; no existe.

## Alcance (release envelope)
Version markers (`tools/ds_init/version.py`, `CITATION.cff`, `README.md`, `.ds_init/control.json`), roadmap/README de roadmap, `docs/releases/v0.12.0.md` (inglés), smoke `test_v012_release_hardening_smoke.py`, adaptación de smokes previos, tests y docs afectados, pequeños fixes de integración que surjan de la regresión.

## Fuera de alcance
Features, skills nuevas, cambios de roles/permisos/hooks, ds_profile columnar, Cards as-of, provider T2, CI cross-platform, evals/benchmarks, self-improvement.

## Aprobación
- Usuario:
- Fecha:
- Alcance aprobado:
- Versión de artefactos referenciada:
- Cita o descripción fiel de qué se aprobó:

## Alcance autorizado

- tools/ds_init/version.py
- CITATION.cff
- README.md
- .ds_init/control.json
- docs/releases/v0.12.0.md
- docs/roadmap/README.md
- docs/roadmap/v0.12.md
- tools/tests/test_v012_release_hardening_smoke.py
- tools/tests/test_v011_release_hardening_smoke.py
- tools/tests/test_v010_release_hardening_smoke.py
- tools/tests/test_v09_release_hardening_smoke.py
- tools/tests/test_v07_release_hardening_smoke.py
- tools/tests/test_harness_smoke.py
- tools/tests/test_skill_methodology.py
- tools/tests/test_skill_contract.py
- tools/tests/test_architecture_boundaries.py
- tools/ds_init/tests/test_manifest.py
- tools/ds_init/tests/test_glossary_install.py
- tools/harmessi/tests/test_doctor_skill_contract.py
- tools/ds_init/manifest.py
- tools/harmessi/doctor.py
- tools/dsguard/skill_contract.py
- ARCHITECTURE.md
- .claude/skills/lead-data-scientist/SKILL.md
- .claude/skills/lead-data-scientist/methodology.md
- .claude/skills/lead-data-scientist/sdd.md
- .claude/skills/lead-data-scientist/verificador.md
- .claude/skills/lead-data-scientist/skills/domain-modeling.md
- .claude/skills/lead-data-scientist/skills/problem-framing.md
- .claude/skills/lead-data-scientist/skills/diagnosing-bugs.md
- .claude/skills/lead-data-scientist/skills/codebase-design.md
- .claude/skills/lead-data-scientist/templates/skill.md
- .claude/skills/lead-data-scientist/templates/tasks.md
- tools/ds_init/profiles/python_jupyter_data/templates/SKILL_lead_data_scientist.md.tmpl
- tools/ds_init/profiles/python_jupyter_data/templates/methodology.md.tmpl
- tools/ds_init/profiles/python_jupyter_data/templates/sdd.md.tmpl
- tools/ds_init/profiles/python_jupyter_data/templates/verificador.md.tmpl
- openspec/changes/20261021-v012-release-hardening/**

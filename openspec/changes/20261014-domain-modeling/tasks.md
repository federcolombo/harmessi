# Tareas — 20261014-domain-modeling

estado: cerrada

## Invocaciones planificadas
- Lead: coordina, valida, git; NO escribe implementación. Writers `python-data-engineer` con ownership disjunto (abajo). Reviewer `data-science-reviewer`: máx. 2 ciclos; las continuaciones técnicas no cuentan. Regresión relevante (UNA); sin full regression en este Change.

## Ownership de writers
### W1 — python-data-engineer — T1
- tools/dsguard/glossary.py
- tools/tests/test_glossary.py

### W2 — python-data-engineer — T2
- tools/ds_guard.py
- tools/tests/test_ds_guard_glossary_cli.py

### W3 — python-data-engineer — T3
- .claude/skills/lead-data-scientist/skills/domain-modeling.md
- .claude/skills/lead-data-scientist/methodology.md
- tools/ds_init/profiles/python_jupyter_data/templates/methodology.md.tmpl

### W4 — python-data-engineer — T4
- .claude/skills/lead-data-scientist/SKILL.md
- .claude/skills/lead-data-scientist/verificador.md
- tools/ds_init/profiles/python_jupyter_data/templates/SKILL_lead_data_scientist.md.tmpl
- tools/ds_init/profiles/python_jupyter_data/templates/verificador.md.tmpl

### W5 — python-data-engineer — T5
- tools/ds_init/manifest.py
- tools/harmessi/doctor.py
- tools/ds_init/tests/test_manifest.py
- tools/harmessi/tests/test_doctor_skill_contract.py
- tools/ds_init/tests/test_glossary_install.py

### W6 — python-data-engineer — T6
- tools/tests/test_skill_methodology.py
- tools/tests/test_architecture_boundaries.py
- ARCHITECTURE.md
- docs/roadmap/v0.10.md

## Historial de ownership
<!-- fecha — instancia — ruta — motivo -->
- 2026-10-15 — fixes de reviewer aplicados por las mismas instancias dueñas de cada archivo (continuación de la misma instancia)

## Skills cargados
- domain-modeling — T3 — se escribe en este Change (autor de la skill); referencia estructural

## Tareas
- [x] T0 — Aprobación del SDD (autorización anticipada del usuario, 2026-10-14).
- [x] T1 — `glossary.py` + tests (W1).
- [x] T2 — CLI `glossary check|hash` y `validate` (W2; depende de T1).
- [x] T3 — Skill `domain-modeling.md` + methodology §33 (W3).
- [x] T4 — SKILL.md y verificador.md (W4).
- [x] T5 — Manifest, Doctor y tests de instalación (W5; depende de T1, T3).
- [x] T6 — Tests de contenido/boundaries, ARCHITECTURE, roadmap (W6).
- [x] T7 — Reviewer (máx. 2 ciclos) y fixes; regresión relevante.
- [x] T8 — Verificación y cierre; commit local sin push.

## Verificación
Detalle completo en `verification.md` de este Change.
- Regresión relevante (18 módulos): 714 tests OK (skipped=8); módulos glossary/CLI/skill_methodology/boundaries tras fixes del ciclo 2: 132 OK (skipped=1).
- `ds_guard validate` del Change: sin hallazgos.
- Reviewer: 2 ciclos, 0 bloqueantes, 0 importantes al cierre; 0 continuaciones.
- Limitaciones y pendientes derivados: ver `verification.md`.

## Dependencias
T2 y T5 dependen de T1; T5 de T3; T6 de T1–T5; T7 de T1–T6; T8 de T7.

## Próximo paso exacto
<!-- obligatorio si estado: pausada_bloqueada -->

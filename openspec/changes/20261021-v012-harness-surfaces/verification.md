# Verificación — 20261021-v012-harness-surfaces

## Resumen
Change 1 de v0.12: modelo de superficies del harness (Protected / Optimizable / Project-owned), derivado de la ruta, con una validación estructural barata en el contrato de skill.

## Evidencia obtenida
- Implementación por `python-data-engineer` (1 instancia; 1 continuación por límite de turnos, no cuenta como ciclo). `skill_contract.superficie_de_ruta` pura y fail-safe; `SKILL-ARTIFACT-SUPERFICIE-PROTEGIDA` en `_validar_artifacts`; Doctor lo expone como WARN sin cambios en `doctor.py`.
- Docs: `ARCHITECTURE.md` §9, `methodology.md` §36 y nota en §28, `SKILL.md`, `verificador.md`, `templates/skill.md`, con espejos `.tmpl` en paridad.
- Tests: `python -m unittest tools.tests.test_skill_contract tools.tests.test_skill_methodology tools.harmessi.tests.test_doctor_skill_contract tools.tests.test_architecture_boundaries tools.ds_init.tests.test_manifest` → 176 OK (antes y después de los fixes). `ds_guard validate` sin hallazgos.
- Reviewer: 1 ciclo; sin blocker ni HIGH; 3 MED y 4 LOW, todos aplicados (endurecimiento de `superficie_de_ruta`, aclaración de §28, nota «clasificación por archivo, no por contenido», lista del verificador, casos de test). Los fixes no cambian materialmente lo revisado: sin segundo ciclo.

## Archivos
Modificados: `skill_contract.py`, tests, ARCHITECTURE, methodology/SKILL/verificador/skill template y sus `.tmpl`, `docs/roadmap/v0.12.md`. Sin cambios en hooks, permisos, roles ni frontmatter.

## Limitaciones
- La clasificación es por archivo: las partes normativas de approval/scope en `methodology.md` son Protected de facto (documentado).
- El único consumidor de la superficie es la validación de `artifacts`; no hay enforcement más amplio (por diseño).
- Hashes managed se regeneran en Change 6.

## Pendientes derivados
Change 2 (problem-framing) a continuación. Sin push, tag ni merge.

## Resultado final
Change 1 cerrado, criterios R1–R8 cumplidos.

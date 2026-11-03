# Verificación — 20261021-v012-problem-framing

## Resumen
Change 2 de v0.12: skill componible `problem-framing` (con `grill-me` como modo opt-in interno), distribuida por manifest y esperada por Doctor.

## Evidencia obtenida
- Skill `skills/problem-framing.md` válida por `validar_skill` (sin `artifacts`, sin claves nuevas); manifest VERBATIM; Doctor `_ARCHIVOS_SKILL_ESPERADOS`; `SKILL.md`, `methodology.md` §37, `ARCHITECTURE.md` §9.1 y espejos `.tmpl`.
- Tests: contrato, metodología/docs, Doctor (incluye caso negativo de skill borrada), manifest, `test_glossary_install`, boundaries y smokes v010/v011 → 222 OK (corrida posterior a los fixes).
- Reviewer: 1 ciclo; sin blocker ni HIGH; MED (destino de supuestos con Change aprobado y sin Change, riesgo de cuestionario, test de Doctor sin caso negativo, test de manifest frágil) y LOW (anclaje de grill-me, derivación a metodólogo) aplicados en la skill y los tests.

## Archivos
Nuevos: `skills/problem-framing.md`. Modificados: manifest, doctor, tests, SKILL/methodology/ARCHITECTURE y `.tmpl`, roadmap.

## Limitaciones
- El matiz «Change ya aprobado» está en la skill, no repetido en SKILL.md/methodology §37 (resumen).
- Calidad metodológica de la skill: criterio de revisión, no test (evals ≠ tests).
- Hashes managed se regeneran en Change 6.

## Pendientes derivados
Change 3 (diagnosing-bugs). Sin push, tag ni merge.

## Resultado final
Change 2 cerrado, R1–R8 cumplidos.

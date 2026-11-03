# Verificación — 20261021-v012-diagnosing-bugs

## Resumen
Change 3 de v0.12: skill componible `diagnosing-bugs` (workflow de 9 pasos, 7 clases de fallo, síntoma ≠ causa raíz, atribución baseline-aware focalizada).

## Evidencia obtenida
- Skill válida por contrato (sin `artifacts`, sin claves nuevas); manifest VERBATIM; Doctor; `SKILL.md`, `methodology.md` §38, `ARCHITECTURE.md` §9.2 y espejos `.tmpl` en paridad.
- Tests: contrato, metodología/docs, Doctor (con caso negativo), manifest, glossary_install, boundaries y smokes v010/v011 → 229 OK en la corrida final.
- Reviewer: 2 ciclos (el primero dejó un HIGH: receta de baseline no explícita y potencialmente destructiva). Corregido: receta de solo lectura (`git show`/`git diff`), prohibición de `checkout/stash/reset/clean/switch`, área temporal ignorada y limpiada, `inconclusive` ante datos ausentes, nunca datasets completos ni holdouts, baseline solo ante «duda razonable», topes de remediation intactos. Segundo ciclo: sin blocker ni HIGH; 2 MED y 4 LOW aplicados.

## Archivos
Nuevos: `skills/diagnosing-bugs.md`. Modificados: manifest, doctor, tests, SKILL/methodology/ARCHITECTURE y `.tmpl`, roadmap.

## Limitaciones
- El tope de 3 ciclos sin hipótesis nueva es propio del diagnóstico (decisión del writer, aceptada), no de remediation.
- Calidad metodológica = criterio de revisión (evals ≠ tests). Hashes managed se regeneran en Change 6.

## Pendientes derivados
Change 4 (codebase-design).

## Resultado final
Change 3 cerrado, R1–R8 cumplidos.

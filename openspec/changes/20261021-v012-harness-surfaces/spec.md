# Spec — 20261021-v012-harness-surfaces

## A. Modelo
**R1.** Tres superficies: *Protected* (guardrails, permisos, approval semantics, trust model, scope enforcement, límites de seguridad, enforcement determinista), *Optimizable*
(skills metodológicas, guidance de metodología, prompts/instrucciones, tool guidance, patrones de razonamiento reutilizables), *Project-owned* (GLOSSARY, definiciones de negocio, Data Contracts, configuración y artefactos del proyecto).
**R2.** Documentado en ARCHITECTURE.md (sección nueva), methodology.md (sección nueva), SKILL.md y plantilla de skill, con paridad md↔tmpl.
**R3.** Se documenta qué NO existe: optimizer, auto-modificación, candidate/probe engine, marketplace.

## B. Derivación determinista
**R4.** `skill_contract.superficie_de_ruta(ruta)` es pura, recibe una ruta repo-relativa y devuelve `protected | optimizable | project-owned`.
Reglas: optimizable = `.claude/skills/lead-data-scientist/skills/*.md`, `methodology.md`, `eda.md`, `kdd.md` de esa carpeta; protected = el resto de `.claude/**`, `tools/**`,
`.ds_init/**`, `.harmessi/**`, y `control.json`/`amendments.jsonl` de cualquier Change; project-owned = todo lo demás. Comparación insensible a mayúsculas y a `./`/`\`.
**R5.** `validar_skill` emite `SKILL-ARTIFACT-SUPERFICIE-PROTEGIDA` si un `artifacts` apunta a superficie protegida. Sin falsos positivos para `GLOSSARY.md` ni rutas project-owned/optimizable.
**R6.** Sin claves nuevas de frontmatter; `domain-modeling` sigue válida; Doctor expone el hallazgo como WARN vía `HARMESSI-SKILL-CONTRATO` sin cambio de severidad.

## C. Verificación
**R7.** Tests unitarios del mapeo (tabla de casos incl. normalización), del hallazgo, de no-regresión de `domain-modeling` y del árbol real (todas las skills del repo válidas); paridad md↔tmpl.
**R8.** Sin regresión completa; tests específicos más smokes directamente afectados.

## Criterios de aceptación
- [ ] R1–R3 documentados y en paridad.  - [ ] R4–R6 implementados.  - [ ] R7–R8 verdes.

# Verificación — 20261021-v012-skill-selection-composition

## Resumen
Change 5 de v0.12: criterio de selección, composición, conflicto y traza de skills (`methodology.md` §40), sin runtime ni código de producción nuevo.

## Evidencia obtenida
- Auditoría de traza: ya existía `## Skills cargados` parseada y validada (`SKILL-REFERENCIA-DESCONOCIDA`); se precisó el criterio («influencia material», una definición operativa única) en §40, `sdd.md`, `templates/tasks.md` y `SKILL.md`. Formato `- <skill> — <tarea> — <motivo>` sin cambios.
- Tabla de selección (4 skills + skills de proyecto por `when_to_load`); carga mínima; composición por pares con el orden decidido por el Lead; conflicto resuelto semánticamente por el Lead sin violar capas superiores, con fallback al humano ante decisiones de §19/CLAUDE.md §3 o duda, y prevalencia de la guidance más restrictiva; foundation v0.10 preservada explícitamente.
- `SKILL.md` reorganizado en viñetas cortas con puntero a las secciones; ARCHITECTURE §9.4 y nota histórica en §7.2.
- Test determinista: toda `skills/*.md` aparece en la tabla de selección. Tests de frases ancladas por sección.
- Corrección lateral (dentro del scope): `sdd.md.tmpl` había derivado de `sdd.md` (faltaban «Aprobaciones con presencia interactiva» y «Enmiendas gobernadas», por lo que los proyectos instalados no las recibían); sincronizado, conservando la ausencia de nombres propios, con test de encabezados.
- Tests: contrato, metodología/docs, Doctor, manifest, glossary_install, boundaries y smokes v010/v011 → 245 OK.
- Reviewer: 1 ciclo; sin blocker ni HIGH; 3 MED y LOW aplicados (fallback humano en conflicto, definición de «material», deriva de sdd.md.tmpl). Fixes de redacción, sin segundo ciclo.

## Archivos
Modificados: SKILL.md, methodology.md, sdd.md, templates/tasks.md, sus `.tmpl`, ARCHITECTURE, tests, roadmap. Sin cambios en `tools/` de producción.

## Limitaciones
- La traza sigue siendo cooperativa: el binario valida existencia, no materialidad (juicio semántico del Lead).
- Hashes managed se regeneran en Change 6.

## Pendientes derivados
Change 6 (release hardening).

## Resultado final
Change 5 cerrado, R1–R9 cumplidos.

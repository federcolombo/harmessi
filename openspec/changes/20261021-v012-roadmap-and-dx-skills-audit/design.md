# Diseño — 20261021-v012-roadmap-and-dx-skills-audit

## Método
Lectura de `main`: `skill_contract.py`, `methodology.md` §27–§33, `SKILL.md`, `sdd.md`, `templates/{skill,tasks}.md`, `manifest.py`, `doctor.py`,
`ARCHITECTURE.md` §7, roadmaps v0.10/v0.11/v1.0 y `domain-modeling.md`.

## Decisiones
- **D1 — `problem-framing`.** Nombre mantenido; `grill-me` es un modo interno, no una skill.
- **D2 — Conflicto entre skills.** Pasa de «el Lead se detiene y consulta» a «el Lead resuelve semánticamente sin violar capas superiores», por pedido
  explícito de la autorización de v0.12. Es guidance de skills: no toca permisos, hooks, roles ni runtime; si el conflicto involucra una capa superior
  gana esa capa y rigen los STOPs vigentes.
- **D3 — Superficie derivada de ruta.** Evita campos ornamentales; el consumidor determinista es la validación de `artifacts` de skills.
- **D4 — Traza.** Se reutiliza `## Skills cargados`; solo se precisa el criterio «influencia material».

## No se reabre
Role ≠ Skill ≠ Runtime, un rol writer, Lead no writer, T0/T1, amendments, readopt, `domain-modeling`, `GLOSSARY.md`, recovery/upgrade de v0.11.

## Decisiones materiales pendientes
Ninguna.

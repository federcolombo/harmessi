# Spec — 20261021-v012-roadmap-and-dx-skills-audit

Change 0 de v0.12: auditoría + congelamiento de roadmap. Solo documentación.

## A. Roadmap
**R1.** `docs/roadmap/v0.12.md` contiene: objetivo, principios, tabla de auditoría (qué ya existe y su consecuencia), Changes 0–6 con boundaries,
dependencias y aceptación, decisiones D1–D4, diferidos, dirección futura v0.13/v0.14 y relación con v1.0.
**R2.** Ninguna capacidad existente se redefine como skill nueva.
**R3.** `docs/roadmap/README.md` registra v0.12 como en desarrollo; `v1.0.md` no se modifica.

## B. Alcance y privacidad
**R4.** Ningún archivo fuera de las rutas autorizadas; `git diff --stat` muestra solo docs y `openspec/`.
**R5.** Sin datos, rutas personales, emails ni nombres de proyectos reales.
**R6.** `v0.12-dev` queda local; sin push ni tag.

## C. Verificación
**R7.** `test_architecture_boundaries`, `ds_guard validate` y `git diff --check`. Sin regresión completa.

## Criterios de aceptación del Change 0
- [ ] R1–R3 roadmap completo y consistente.
- [ ] R4–R6 alcance, privacidad y ramas respetados.
- [ ] R7 verificación liviana verde.

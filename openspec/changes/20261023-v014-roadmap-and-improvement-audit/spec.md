# Spec — 20261023-v014-roadmap-and-improvement-audit

Change 0 de v0.14: auditoría + congelamiento de roadmap. Solo documentación.

## A. Roadmap
**R1.** `docs/roadmap/v0.14.md` contiene objetivo, principios, tabla de auditoría, decisiones D1–D9, Changes 0–6, fuera de alcance y relación con v1.0.
**R2.** Las primitivas de v0.13 se consumen; ninguna se redefine con otro nombre.
**R3.** `docs/roadmap/README.md` registra v0.14 en desarrollo; `v1.0.md` no se modifica.

## B. Alcance y privacidad
**R4.** Solo rutas autorizadas; `git diff --stat` muestra únicamente docs y `openspec/`.
**R5.** Sin datos, rutas personales, emails ni nombres de proyectos reales.
**R6.** `v0.14-dev` queda local; sin push ni tag.

## C. Verificación
**R7.** `ds_guard validate`, `git diff --check` y `test_architecture_boundaries`. Sin regresión completa.

## Criterios de aceptación
- [ ] R1–R3 roadmap completo y consistente.
- [ ] R4–R6 alcance, privacidad y ramas respetados.
- [ ] R7 verificación liviana verde.

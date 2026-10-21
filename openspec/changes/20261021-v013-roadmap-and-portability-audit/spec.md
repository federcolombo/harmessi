# Spec — 20261021-v013-roadmap-and-portability-audit

Change 0 de v0.13: auditoría + congelamiento de roadmap. Solo documentación.

## A. Roadmap
**R1.** `docs/roadmap/v0.13.md` contiene objetivo, principios, tabla de auditoría (existe / parcial / vivo / no duplicar), Changes 0–6 con boundaries,
decisiones D1–D5, deudas diferidas, dirección futura v0.14 y relación con v1.0.
**R2.** `harmessi_bench` se extiende; ninguna capacidad existente se redefine con otro nombre.
**R3.** `docs/roadmap/README.md` registra v0.13 como en desarrollo; `v1.0.md` no se modifica.

## B. Alcance y privacidad
**R4.** Ningún archivo fuera de las rutas autorizadas; `git diff --stat` muestra solo docs y `openspec/`.
**R5.** Sin datos, rutas personales, emails ni nombres de proyectos reales.
**R6.** `v0.13-dev` queda local; sin push ni tag.

## C. Verificación
**R7.** `test_architecture_boundaries`, `ds_guard validate` y `git diff --check`. Sin regresión completa.

## Criterios de aceptación del Change 0
- [ ] R1–R3 roadmap completo y consistente.
- [ ] R4–R6 alcance, privacidad y ramas respetados.
- [ ] R7 verificación liviana verde.

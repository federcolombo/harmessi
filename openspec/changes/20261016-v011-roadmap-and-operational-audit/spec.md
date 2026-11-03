# Spec — 20261016-v011-roadmap-and-operational-audit

Change 0 de v0.11: auditoría + congelamiento de roadmap. Solo documentación; ningún cambio en `tools/**`.

## A. Roadmap
**R1.** `docs/roadmap/v0.11.md` contiene: objetivo, principios, tabla de auditoría con estado y evidencia por deuda, Changes 0–6, dependencias, diferidos,
clasificación futura v0.12/v0.13, boundaries y relación con v1.0.
**R2.** Cada Change 1–6 tiene objetivo, problema/evidencia, scope, boundaries, dependencias, aceptación verificable, riesgos y diferidos.
**R3.** Toda divergencia respecto del roadmap candidato queda documentada en design.md (D1–D4).
**R4.** `docs/roadmap/README.md` registra v0.11 como en planificación; `v1.0.md` no se modifica.

## B. Alcance y privacidad
**R5.** Ningún archivo fuera de las 3 rutas autorizadas; `git diff --stat` muestra solo docs y `openspec/`.
**R6.** Sin datos, rutas personales, emails ni nombres de proyectos reales; `docs/feedback/` no se cita.
**R7.** `v0.11-dev` queda local; sin push, tag ni publicación.

## C. Verificación
**R8.** Se ejecutan smoke de roadmap existente, `test_architecture_boundaries`, `ds_guard validate` y `git diff --check`. Sin regresión completa.

## Criterios de aceptación del Change 0
- [ ] R1–R4 roadmap completo y consistente con las fuentes.
- [ ] R5–R7 alcance, privacidad y ramas respetados.
- [ ] R8 verificación liviana verde.

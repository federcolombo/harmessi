# Spec — 20261026-v015-debt-archaeology-and-roadmap

## Requisitos
- R1. `docs/roadmap/v0.15-debt-matrix.md` contiene una tabla única; cada ítem aparece una sola vez y en exactamente una categoría A/B/C/D/E.
- R2. Cada ítem tiene id, fuente/versión, descripción, evidencia actual, estado actual, justificación, destino y bloquea v1 (sí/no).
- R3. La matriz documenta la metodología (fuentes barridas) y un resumen de conteos por categoría, incluidos los B/C/D con bloquea=sí, calculados de la propia tabla.
- R4. Todo ítem B tiene como destino un Change C1–C7.
- R5. `docs/roadmap/v0.15.md` define estado, objetivo, principios, auditoría resumida, decisiones D1–D7, los 8 Changes con alcance y fuera de alcance, criterios de salida (READY FOR v1.0 PLANNING / NOT READY FOR v1.0 — gaps) y el mapeo de los 14 criterios de `v1.0.md`.
- R6. `docs/roadmap/README.md` incluye una entrada de índice de v0.15.
- R7. No se inventa evidencia y no se declara v1.0. No se modifica nada fuera del alcance autorizado.

## Criterios de aceptación
- [ ] Los conteos del resumen coinciden con el recuento de filas por categoría (22 / 34 / 33 / 19 / 8 = 116).
- [ ] Bloquea=sí: 20 ítems, todos en B; ninguno en A, C, D ni E.
- [ ] Ningún id se repite entre categorías.
- [ ] Los 14 criterios de `v1.0.md` están mapeados a al menos un Change.
- [ ] Los ítems B bloqueantes figuran en el roadmap con su Change destino.
- [ ] `git status` muestra cambios solo en el alcance autorizado y en los artefactos del Change.
- [ ] Las referencias cruzadas (ids, nombres de Change) son consistentes entre la matriz y el roadmap.

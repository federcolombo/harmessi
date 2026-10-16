# Diseño — 20261016-v011-roadmap-and-operational-audit

## Método
Lectura de `main` (no de memoria): `repo.py`, `scope.py`, `decision.py`, `hook_presupuesto.py`, `core.py`, `sdd.py`, `ds_guard.py`, `ds_init/{writer,preflight,cli,manifest}.py`,
`harmessi/doctor.py`, roadmaps v0.10/v1.0, notas y verification de v0.10. Los manifests se compararon contra el árbol real con un script de solo lectura.

## Decisiones respecto del roadmap candidato
- **D1 — Orden y dependencias.** Se ajusta la hipótesis inicial: 4 depende de 1 (misma superficie `scope.py`/`repo.py`); 5 espera a 2, 3 y 4 por schemas/módulos nuevos; 1, 2 y 3 son independientes.
- **D2 — Change 4 en un solo Change con dos partes.** 4B (aislamiento de Changes paralelos) es determinista y va primero; 4A (atribución, H1) queda gated por evidencia real y puede cerrar sin tocar hooks.
- **D3 — Ledger.** Naming `decision correct`, no `amend` (ya semántico en `scope amend`, que amplía autoridad). El enum de tipos se difiere: sin consumidor real.
- **D4 — Sesiones.** No se cambia el valor 90; el Change 3 unifica la fuente y agrega aviso y recovery verificable. Pausar el reloj por T1 es una decisión material que solo se tomaría en su SDD.
- **D5 — Upgrade.** El hallazgo clave es que `sync` no refresca un mismo stage y que no existe operación de upgrade: Change 5 pasa a ser el de mayor riesgo y el que gobierna el orden de 6.

## No se reabre
Role ≠ Skill ≠ Runtime, un rol writer con ownership disjunto, Lead no writer, T0/T1, `console_confirmed`, amendments, readopt, `domain-modeling`, `GLOSSARY.md`, scratchpad externo NO, intérprete relajado NO.

## Decisiones materiales pendientes
Ninguna para congelar el roadmap. Las decisiones propias de cada Change (p. ej. semántica de reloj en T1, forma exacta de `decision correct`) se toman en su SDD.

# Tareas — 20260917-v0-5-release-hardening

estado: cerrada

## Invocaciones planificadas

1. **`python-data-engineer`** (esta sesión): completa los 4 artefactos SDD (`proposal.md`,
   `spec.md`, `design.md`, `tasks.md`) y aplica los cambios mecánicos de versión/documentación que
   no dependen de evidencia de corridas (`tools/ds_init/version.py`, `CITATION.cff`, `README.md`,
   `docs/roadmap/v0.5.md`), dejando 2 placeholders deliberados en el roadmap para que el Lead los
   complete con evidencia real.
2. **Lead** (invocación posterior, sin subagente de escritura): corre las 9 suites de regresión
   completas, 1 corrida real de `harmessi-bench` contra `claude_code`, el smoke cross-provider
   (matriz de disponibilidad de los 4 `provider_id`), el smoke de routing/fallback (1 fallback
   genuino real), 2 scratch installs (`discovery` y `experiment`), el sweep de privacidad
   transversal, la corrida final de `harmessi doctor`, y la regeneración de
   `.ds_init/control.json` de este propio repo. Recolecta toda esta evidencia para pasarla al
   siguiente paso.
3. **`data-science-reviewer`** (read-only): revisión transversal del conjunto de los 5 Changes de
   v0.5 (Changes 0-4 + este Change 5 juntos), no solo del diff de este Change 5.
4. **`python-data-engineer`** (segunda invocación de esta sesión, posterior a 2 y 3): aplica fixes
   si el reviewer encuentra hallazgos bloqueantes, escribe `verification.md` con toda la evidencia
   real recolectada por el Lead en el paso 2 y los hallazgos/resolución del paso 3, y completa los
   2 placeholders de `docs/roadmap/v0.5.md` (la sección "Change 5" y la línea "Resultado final" bajo
   "## Estado") con el resultado real (`READY FOR v0.5.0 RELEASE` o `NOT READY`).

## Tareas

- [x] `tools/ds_init/version.py`: `HARNESS_VERSION = "0.5.0"`.
- [x] `CITATION.cff`: `version: 0.5.0`, `date-released: "2026-09-17"`.
- [x] `README.md`: 4 subsecciones nuevas (`harmessi providers`, `harmessi routing`, `harmessi
      fallback`, `harmessi-bench`) en `## Commands`.
- [x] `docs/roadmap/v0.5.md`: checklist de 6 Changes marcado `[x]`, resumen "Estado: DONE" por
      Change 0-4, placeholders deliberados para Change 5 y "Resultado final".
- [x] `proposal.md` completo (problema, objetivo, evidencia, supuestos descartados, alcance, fuera
      de alcance, aprobación).
- [x] `spec.md` completo (R1-R11 + criterios de aceptación Given/When/Then + secciones
      condicionales marcadas "No aplica").
- [x] `design.md` completo (decisión técnica, alternativas descartadas, riesgos, secciones
      condicionales marcadas "No aplica").
- [x] `tasks.md` completo (este archivo).
- [x] `verification.md`: escrito en la invocación 4 con la evidencia real recolectada por el Lead
      (invocación 2) y los hallazgos/resolución del reviewer transversal (invocación 3). Ver
      `openspec/changes/20260917-v0-5-release-hardening/verification.md`.
- [x] `.ds_init/control.json`: regenerado por el Lead (invocación 2), no lo tocó
      `python-data-engineer`.

## Dependencias

Ninguna — es el cierre de todo v0.5, depende únicamente de que los Changes 0-4 ya estén cerrados
(confirmado: los 5 `verification.md` de esos Changes ya existen y están completos).

## Próximo paso exacto

No aplica (`estado: propuesta_pendiente`, no `pausada_bloqueada`).

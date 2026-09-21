# Tareas — 20260918-v0-6-release-hardening

estado: cerrada

## Invocaciones planificadas

1. **`python-data-engineer`**: redacta los 4 artefactos SDD (`proposal.md`, `spec.md`,
   `design.md`, `tasks.md`) y declara el alcance en `control.json`. Sin código.
2. **`python-data-engineer`**: alinea versión y estado: `tools/ds_init/version.py`
   (`HARNESS_VERSION = "0.6.0"`), `CITATION.cff` (`version`, `date-released`) y encabezado de
   estado de `docs/roadmap/v0.6.md`. No toca `.ds_init/control.json` ni v0.7-v0.9.
3. **Lead** (sin subagente de escritura): corre la regresión secuencial de las 10 suites, los
   contract tests, los scratch installs reales (`experiment` y `discovery`) con publicación del
   EDA genérico, `validate`, `render --check` y `harmessi doctor --destino`, los smokes R7-R15,
   la backward compatibility contra `v0.5.0`, los sweeps de privacidad y portabilidad, y
   `harmessi doctor` sobre este repo. Recolecta la evidencia y no instala dependencias.
4. **`data-science-reviewer`** (read-only): revisión transversal del conjunto de los 5 Changes de
   v0.6, sin repetir revisiones individuales.
5. **`python-data-engineer`**: aplica solo correcciones de hardening acotadas a las rutas
   autorizadas, si la evidencia o el reviewer hallan defectos.
6. **Lead**: regenera `.ds_init/control.json` ÚLTIMO invocando `control.regenerar_control`
   directo (no lo hace un subagente) y re-corre lo afectado (paridad, versión, doctor, suites
   tocadas por las correcciones).
7. **`python-data-engineer`**: cierra con `verification.md` (evidencia real, hallazgos del
   reviewer, limitaciones, resultado final `READY FOR v0.6.0 RELEASE` o `NOT READY FOR v0.6.0
   RELEASE` con razones) y actualiza `docs/roadmap/v0.6.md` (`[x] Change 5` solo si
   corresponde).

## Tareas

- [ ] Artefactos SDD completos (`proposal.md`, `spec.md`, `design.md`, `tasks.md`) y
      `control.json` con `alcance.rutas_autorizadas` (invocación 1).
- [ ] `tools/ds_init/version.py` y `CITATION.cff` en `0.6.0` (invocación 2).
- [ ] `docs/roadmap/v0.6.md` con el estado real (invocaciones 2 y 7).
- [ ] Regresión secuencial de las 10 suites y contract tests (R4, R5).
- [ ] Scratch installs `experiment` y `discovery` con publicación, `validate`, `render --check` y
      doctor (R6).
- [ ] Smokes R7-R15 (EDA, aislamiento, `model_valid`, holdout, figura↔tabla, manifest, HTML
      offline/tema, override de tema, portabilidad).
- [ ] Backward compatibility contra `v0.5.0` y paridad del manifest (R16-R18).
- [ ] Sweep de privacidad transversal (R3).
- [ ] `harmessi doctor` sobre este repo sin `[ERROR]` (R19).
- [ ] Reviewer transversal y resolución de hallazgos (R20).
- [ ] Correcciones de hardening acotadas, si las hay (R21).
- [ ] `.ds_init/control.json` regenerado ÚLTIMO por el Lead (R1, R17, R18).
- [ ] `verification.md` con resultado final explícito (R22).
- [ ] Pendiente condicionante declarado: verificación con `plotly.js` real (requiere que el Lead
      presente los 5 puntos al usuario antes de cualquier `pip install`).

## Dependencias

Depende de que los Changes 0-4 de v0.6 estén cerrados (con `verification.md` propio). Sin
dependencias externas nuevas. La verificación con `plotly.js` real depende de una decisión
explícita del usuario y no bloquea la redacción ni la verificación con bundle FALSO.

## Próximo paso exacto

No aplica (`estado: propuesta_pendiente`, no `pausada_bloqueada`). Espera aprobación humana de
los artefactos antes de implementar.

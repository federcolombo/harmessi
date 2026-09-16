# Tareas — 20260916-v0-3-release-hardening

estado: cerrada

## Invocaciones planificadas
<!-- rol, momento del ciclo, y qué produce cada una -->
- Lead (audit transversal + validación E2E, sin subagente, con Bash): ya en curso — versión,
  privacidad (corregido), README, regresión, scratch installs, sync, readiness/promotion,
  evidence, status, legacy, read-only, doctor final, `control.json` final.
- Python Data Engineer (invocación única, si hace falta contenido de prosa extenso): README
  restante / release notes / known limitations / roadmap, SOLO si el Lead decide que el volumen de
  redacción amerita delegarlo en vez de escribirlo directo — a definir según avance el audit.
- Data Science Reviewer (auditoría de release, al final): busca release blockers,
  incompatibilidades, bugs de instalación, documentación materialmente falsa, fuga de privacidad
  residual, backward compatibility rota, read-only con side effects, tests que solo pasan por
  mocks, manifest/control inconsistentes, version drift residual, gates bypassables. Clasifica
  BLOCKER/IMPORTANT/MINOR/DEBT.
- Python Data Engineer (post-revisión, si hace falta corregir algo real): corrige.
- Lead (cierre): `verification.md` con veredicto final, `estado: cerrada`.

## Tareas
- [x] Audit de versión: fuente canónica identificada (`tools/ds_init/version.py`), drift
  confirmado, ~30 anotaciones históricas distinguidas de la versión actual.
- [x] Audit de privacidad: grep exhaustivo, 1 BLOCKER encontrado (ruta/org privada en 2 artefactos
  SDD ya cerrados) y corregido; confirmado sin residuos.
- [x] Import-smoke-test de `dsguard`/`ds_init`/`harmessi.doctor`: sin imports rotos.
- [x] Regresión baseline (antes de los fixes de este change): `tools/tests/` (pendiente
  confirmación), `tools/harmessi/tests/` (pendiente), `tools/ds_init/tests/` (pendiente),
  `tools/ds_profile/tests/` 134/134 OK.
- [ ] `tools/ds_init/version.py`: `HARNESS_VERSION = "0.3.0"`.
- [ ] `CITATION.cff`: `version: 0.3.0`, `date-released` actualizado.
- [ ] `README.md`: sección KDD/lifecycle corregida (CRISP-DM backbone, `project_stage`/
  `installation_stage`, MLOps, `status`, `readiness`/`promote`, progressive sync); `ds_guard.py`
  agregado a "Commands"; resto sin tocar.
- [ ] Regresión completa post-fixes: `tools/tests/`, `tools/harmessi/tests/`, `tools/ds_init/tests/`
  (re-correr si los fixes de README/version.py las tocan — `version.py` sí puede afectar tests de
  `test_control_file.py`/`test_writer_staging.py`/`test_cli.py` que verifican `HARNESS_VERSION`
  literal; diagnosticar cualquier fallo antes de asumir que es "no relacionado").
- [ ] `harmessi doctor` intermedio (post-fixes, antes de regenerar `control.json`): clasificar
  cada WARN/N-A (esperado/deuda/blocker).
- [ ] Scratch install discovery: repo temporal real, `--stage discovery --execute`, verificar
  R6 de `spec.md`.
- [ ] Scratch install experiment: repo temporal real, sin `--stage`, verificar R6 de `spec.md`.
- [ ] Progressive sync E2E: discovery→experiment→production_candidate→production, verificar R7
  de `spec.md` (idempotencia, no sobrescritura, `project_stage` no cambia, sin evidence
  automático).
- [ ] Readiness/promotion smoke: verificar R8 de `spec.md`, reusando fixtures de
  `test_readiness.py` donde alcance.
- [ ] Evidence smoke: verificar R9 de `spec.md`.
- [ ] Status smoke: verificar R10 de `spec.md` (los 4 stages + desalineación + legacy si hay
  fixture).
- [ ] Legacy/v0.2 compatibility: verificar R11 de `spec.md` (fixture mínimo si no existe uno
  reusable).
- [ ] Read-only audit final: confirmar R12 de `spec.md` (puede apoyarse en los tests ya
  existentes de Changes 3/5/6/7/8, sin re-implementar).
- [ ] Limpieza open-source: revisar archivos temporales/backups/checkpoints/caches/logs no
  trackeados accidentales (`git status` completo) — no borrar nada ambiguo sin entenderlo.
- [ ] Release notes v0.3.0 (texto en `verification.md`).
- [ ] Known limitations / deuda v0.4+ (texto en `verification.md`, revisando si las 6 limitaciones
  que lista el brief siguen aplicando).
- [ ] Roadmap post-v0.3 (texto en `verification.md`, v0.4 y v0.5+ candidatos, sin abrir ningún
  change nuevo).
- [ ] Reviewer final (auditoría de release, no de un archivo): findings clasificados
  BLOCKER/IMPORTANT/MINOR/DEBT; solo BLOCKER/IMPORTANT arreglados ahora.
- [ ] Fixes post-reviewer, si corresponden (máx. 1 ciclo adicional).
- [ ] `harmessi doctor` FINAL (después de todos los fixes, antes de regenerar `control.json`): 0
  `[ERROR]`.
- [ ] Regenerar `.ds_init/control.json` de este repo una sola vez, al final, vía
  `control.regenerar_control` (o `ds_init sync` si corresponde con el `installation_stage` real de
  este repo) — último paso de escritura real.
- [ ] `harmessi doctor` post-regeneración (confirmar que `control.json` quedó consistente, sin
  introducir un `[ERROR]` nuevo).
- [ ] Veredicto final: READY FOR v0.3.0 RELEASE o NOT READY, con justificación.

## Dependencias
Versión → README (el README puede citar la versión) → regresión post-fixes → scratch/sync/
readiness/evidence/status/legacy (independientes entre sí, pueden ordenarse libremente) → doctor
intermedio → reviewer → fixes → doctor final → `control.json` regenerado (siempre el último paso
de escritura) → veredicto.

## Próximo paso exacto
<!-- obligatorio si estado: pausada_bloqueada -->

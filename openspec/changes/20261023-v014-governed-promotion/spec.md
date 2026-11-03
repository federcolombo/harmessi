# Spec — 20261023-v014-governed-promotion

**R1.** `proponer_promocion(repo_root, candidate_id)` exige `decision.verificar_promotable` (evidencia recomputada) y `base_vigente`; si no, `PromocionNoRespaldada`/`PromocionBloqueada`. Escribe solo `.harmessi/improvement/proposals/<candidate_id>/{proposal.json,change.diff}`.
**R2.** `proposal.json` (`PROPOSAL_CONTRACT_VERSION=1`): `candidate_id`, `base_surface`, `base_hash`, `content_hash`, `probe_id`, `decision_hash`, `verdict`, resumen de evidencia (suite, n_escenarios, runs con sha256), `diff_sha256`, `governance` (`requires="console_confirmed"`, `surface_class`, `distributed=true|false`, pasos), `ledger_text` (texto sugerido para el Decision Ledger actual) y `proposal_hash` canónico. Sin prompts, secretos ni rutas absolutas; el diff se escanea con `redactar_texto`.
**R3.** `evaluar_gate(repo_root, candidate_id, change_id)` devuelve la lista de motivos de bloqueo (vacía = pasa): propuesta íntegra y recomputada; candidate aún `promotable` con evidencia vigente; archivo activo con `base_hash`; Change existente, en `en_implementacion` y con `control.json` legible; `proposal.md`, `spec.md` y `design.md` con aprobación `verified` **y** `approval_channel == "console_confirmed"` (T0 `declared` nunca alcanza); la superficie dentro del scope efectivo del Change; el `proposal.md` del Change cita el `proposal_hash`.
**R4.** `aplicar_promocion(repo_root, candidate_id, change_id)` ejecuta el gate; con cualquier motivo → `PromocionBloqueada(motivos)` sin escribir; si pasa, reemplaza la superficie activa por el contenido de la candidate (escritura atómica, solo esa ruta) y registra `applied.json`. Nunca toca `main`, managed baseline ni otras rutas, y es idempotente (segunda aplicación con el contenido ya presente no cambia nada).
**R5.** Protected/Project-owned: `base_surface` se re-clasifica Optimizable antes de proponer y aplicar.
**R6.** Una promoción no sustituye tests/reviewer/SDD: el gate exige el Change normal y la propuesta documenta que la verificación de release sigue siendo obligatoria.
**R7.** La propuesta incluye `distributed` (superficie bajo el skill Lead = distribuida por Harmessi) y el aviso de que actualizar el managed baseline es tarea del release/Change, no de esta API.

## Criterios de aceptación
- [ ] R1–R2 propuesta. - [ ] R3–R4 gate y aplicación. - [ ] R5–R7 fronteras.

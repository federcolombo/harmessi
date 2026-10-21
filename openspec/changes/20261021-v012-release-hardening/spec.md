# Spec — 20261021-v012-release-hardening

**R1.** Versión `0.12.0` en `version.py`, `CITATION.cff`, `.ds_init/control.json` (regenerado una vez por el Lead), README (sección v0.12) y roadmaps.
**R2.** `docs/releases/v0.12.0.md` en inglés: Data Scientist Experience & Composable Skills; Harness Surfaces; problem-framing; diagnosing-bugs; codebase-design; contextual composition; traceability; limitaciones y deudas diferidas; sin afirmar «self-improving harness».
**R3.** Smoke `test_v012_release_hardening_smoke.py` (estilo v011): versión consistente, notas con claves obligatorias y sin afirmaciones prohibidas, Changes 0–5 cerrados, 4 skills válidas e instalables, roles/permisos sin cambio (tools y maxTurns por agente), privacidad (sin rutas personales/emails/tokens en lo versionado), roadmap consistente. Smokes v010/v011 adaptados para tolerar versión posterior sin debilitarse.
**R4.** Regresión completa serial (P=1) por batches con tabla batch/attempted/passed/skipped/failed; un batch fallido se corrige y se repite solo ese.
**R5.** Fresh install v0.12 y upgrade desde el tag público `v0.11.0` a `0.12.0` en directorios temporales: skills nuevas instaladas, project-owned (incl. GLOSSARY.md) byte-idénticos, GLOSSARY no creado, idempotencia, Doctor sin errores de producto.
**R6.** Dogfooding A–E con fixtures sintéticos genéricos y registro cualitativo.
**R7.** Privacidad: barrido de lo cambiado desde `917339f` sin hallazgos.
**R8.** Baseline managed coherente (`migrate-hashes` dry-run sin migrables/no verificables).

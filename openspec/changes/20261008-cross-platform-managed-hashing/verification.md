# Verificación — 20261008-cross-platform-managed-hashing

## Resumen
Change 1 de v0.10 «Cross-platform Managed Hashing» (solo deuda A). SDD aprobado por hash el 2026-10-08 por Federico Colombo (proposal `93291daf832eb5163ae501f39e4b47de23bc891710f3890e0dd717afc6a2002e`, spec `78ea81e5cf787fc308b90f853c90421c0452204bcfbe8fa130219b6b68f42b1d`, design `e8fad271ed1e82f113b0582222297b9b35ebdf45a1ad3eab071d3337772c60ca`) con la decisión M-A (alcance materializado: 18 rutas). Implementación con 4 instancias de `python-data-engineer` con ownership disjunto (A: managed_hash; B: control/manifest; C: Doctor; E: planner/writer/cli) más D (docs/boundaries); el Lead no escribió código.

## Qué entrega
- Primitive única `tools/ds_init/managed_hash.py` (solo stdlib, streaming): texto `sha256/eol-lf/v1` (CRLF→LF y CR→LF por bytes, sin decodificar); binario `sha256/bin/v1` (bytes exactos). `verificar_entrada` con estados `ok` / `ok_legacy` / `drift` / `algoritmo_desconocido`; legacy acepta solo crudo/LF/CRLF y, para binario, solo crudo.
- `hash_alg` explícito por entrada de `control.json`: ausencia = legacy, desconocido = fail-closed; sin bump de schema ni de versión. `contenido` (`texto` por defecto | `binario`) en el manifest.
- `generar_control` / `regenerar_control` (rebaseline explícito conserva su semántica; modo conservador con `clasificacion` / `resultado` / `preexistentes`), `clasificar_baseline`, `migrar_hashes` y subcomando `migrate-hashes [--execute]` (dry-run por defecto, determinista, idempotente, no migra contenido modificado).
- `sync` conservador: clasifica antes de escribir contra el baseline anterior; pristine + nuevo asset → actualiza con backup/rollback; drift → no se reescribe ni se rehashea y la entrada se conserva; existente sin baseline solo se registra si es idéntico al distribuido; el merge de `settings.json`/`CLAUDE.md` se aplica pero no adopta drift ni archivos sin baseline; `control.json` conserva las entradas previas durante sync.
- Doctor EOL-independiente: legacy migrable informativo (no WARN); algoritmo desconocido → [ERROR].
- Separación migration ≠ managed upgrade ≠ re-adoption (esta última, Change 3).
- Intactos: `hash_lf_v1`, ApprovalRef, checkpoints `@approved`, Cards/EvidenceRef, SourceObservation, DataContracts, reporting y guardrails semantic drift (la closed-list `RUTAS_MUTABLES` solo se evalúa cuando el hash canónico difiere). `.gitattributes` no forma parte del correctness.
- Hallazgo F-1 (sync rehasheaba todo) resuelto por M-A. Corrección a Change 0: los «3 sin match» eran archivos vacíos.

## Evidencia obtenida
- Tests dirigidos: 157 OK (antes de los últimos fixes).
- Regresión relevante posterior a todos los fixes:
  - `tools/ds_init/tests` completo: 272 OK.
  - `tools/harmessi/tests`: 178 corridos con 2 errores de importación (`test_fallback_cli`, `test_providers_cli`: `import pytest`; pytest no instalado en el entorno; preexistentes y ajenos al Change; no se instaló pytest).
  - Lote guardrails drift + checkpoints `@approved` + architecture boundaries + manifest parity + roadmap smoke + hook_rutas + scope + cards approvals: 120 OK (1 skipped).
- `migrate-hashes` en dry-run sobre este repo: 119 managed migrables, 0 drift, 0 desconocidos.
- Doctor sobre este repo: solo WARN de working tree sucio.
- Sin regresión completa (decisión del usuario).
- Reviewer `data-science-reviewer`, 2/2 ciclos:
  - Ciclo 1: 0 blockers, 1 alto (merge con drift adoptado si fallaba `regenerar_control`) y 5 medios (R27d/R27e, pérdida de entradas en modo conservador, binarios legacy tolerantes a EOL, tests faltantes, drift de merge sin informar); todos corregidos.
  - Ciclo 2: 0 blockers/altos, 1 medio (MERGE sin baseline adoptado en control intermedio) y 2 bajos; medio y mensaje de dry-run corregidos; ventana TOCTOU documentada como límite aceptado.
  - Sin hallazgos abiertos.

## Archivos modificados
`ARCHITECTURE.md` (§8.2), `docs/roadmap/v0.10.md`, `tools/ds_init/{managed_hash (nuevo),control,manifest,planner,writer,cli}.py`, `tools/harmessi/doctor.py`; tests nuevos `test_managed_hash`, `test_control_hash_alg`, `test_manifest_contenido`, `test_sync_baseline`, `test_doctor_managed_hash`; ajustes en `test_control_file`, `test_doctor_governance`, `test_architecture_boundaries`.

## Fingerprint de dataset/artefacto
No aplica (sin datasets).

## Diferencias contra la spec
Ninguna registrada.

## Limitaciones
- Ventana de segundos entre clasificar y hashear/escribir (TOCTOU): límite aceptado.
- Baselines históricos de EOL mixto no verificables → drift (requieren rebaseline explícito).
- Downgrade a un Harmessi anterior sobre un control migrado puede dar falso drift.
- Los pins byte-exact de evidencia versionada bajo autocrlf (hallazgo F-2) quedan como candidato futuro.
- La escritura de `control.json` en `migrar_hashes` no es atómica (mismo patrón que `generar_control`).
- `.ds_init/control.json` de este repo NO se regeneró (se hace una vez en Change 6).
- Sin regresión completa; 2 errores de importación preexistentes por pytest ausente.

## Pendientes derivados
- Change 3: re-adopción.
- Change 6: regenerar `.ds_init/control.json` de este repo.
- Change 4: el estado de `tasks.md` de Change 0 fue adelantado a mano por un writer; tratar el ciclo de vida.
- Candidato futuro: F-2 (pins byte-exact bajo autocrlf).
- Cierre, transiciones y commit local pendientes del Lead (sin push).

## Resultado final
Change 1 verificado con las pruebas relevantes indicadas; sin hallazgos abiertos del reviewer. Cierre pendiente del Lead.

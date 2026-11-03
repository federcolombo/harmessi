# Tareas — 20261008-cross-platform-managed-hashing

estado: cerrada

## Invocaciones planificadas
- Lead: coordina, gobierna y hace la revisión de consistencia; NO escribe archivos.
- Instancias de `python-data-engineer` con ownership DISJUNTO de archivos (declarado acá antes de lanzar):
  - Writer A: `tools/ds_init/managed_hash.py` + `tools/ds_init/tests/test_managed_hash.py`.
  - Writer B: `tools/ds_init/control.py`, `tools/ds_init/manifest.py`, `tools/ds_init/tests/test_control_file.py`,
    `tools/ds_init/tests/test_control_hash_alg.py`.
  - Writer C: `tools/harmessi/doctor.py` + `tools/harmessi/tests/test_doctor_managed_hash.py` (+ tests de doctor existentes que dependan del
    hash crudo, si hace falta).
  - Writer E: `tools/ds_init/planner.py`, `tools/ds_init/writer.py`, `tools/ds_init/cli.py`, `tools/ds_init/tests/test_sync_baseline.py`.
  - Writer D (al final; único dueño de docs y boundaries): `tools/tests/test_architecture_boundaries.py`, `ARCHITECTURE.md`,
    `docs/roadmap/v0.10.md`.
  - Cualquier archivo existente que un writer necesite y sea de otro dueño se devuelve al Lead (no se toca).
- Reviewer `data-science-reviewer`: máximo 2 ciclos, después de los tests dirigidos. Foco: EOL estable, drift real detectado, sync no adopta
  drift, upgrade pristine funciona, migración no acepta modificados, `hash_alg` explícito, binario byte-exact, ApprovalRef/checkpoints
  intactos, guardrails intactos, primitive única, sin evidence hashes modificados, compatibilidad.
- Verificación: tests dirigidos por writer y UNA regresión global RELEVANTE al final: ds_init/control/manifest/planner/sync, Doctor/drift,
  guardrails drift, approval/checkpoints, installer/adoption, architecture boundaries. NO Cards completas, governance, ds_profile ni modeling.

## Tareas
- [x] T0 — Aprobación humana del SDD por hash y decisión M-A (hecha, 2026-10-08).
- [x] T1 — Primitive `managed_hash.py` + tests (Writer A).
- [x] T2 — Integración en `control.py` y `manifest.py` + tests (Writer B).
- [x] T3 — Doctor: `_check_hashes_drift` con legacy migrable informativo + tests (Writer C).
- [x] T4 — Migración explícita y `sync` conservador según M-A en `planner.py`, `writer.py`, `cli.py` + tests (Writer E).
- [x] T5 — Reviewer `data-science-reviewer` (máx. 2 ciclos) y fixes.
- [x] T6 — Docs/boundaries (Writer D), verificación (una regresión global relevante) y cierre.

## Dependencias
Change 0 cerrado. T1 depende de T0. T2 y T3 dependen de T1. T4 depende de T2. T5 depende de T2–T4. T6 depende de T5.

## Handoff (pausa 2026-10-08)
- **Estado**: branch `v0.10-dev`, HEAD `ff76b20` (Change 0); Change 1 `en_implementacion`, sesión `s1` PAUSADA. SDD aprobado por hash (proposal 93291daf…, spec 78ea81e5…, design e8fad271…, 18 rutas de alcance). Working tree con cambios SIN commit (válidos, no descartar): ARCHITECTURE.md, docs/roadmap/v0.10.md, tools/ds_init/{cli,control,manifest,planner,writer}.py, tools/ds_init/managed_hash.py (nuevo), tools/harmessi/doctor.py, tests nuevos (ds_init: test_managed_hash, test_control_hash_alg, test_manifest_contenido, test_sync_baseline; harmessi: test_doctor_managed_hash) y ajustes en test_control_file, test_doctor_governance y test_architecture_boundaries. Hay 1 commit local sin push (`ff76b20`).
- **Hecho**: implementación completa A/B/C/E/D. Reviewer ciclo 1 (0 blockers, 1 alto, 5 medios: corregidos) y ciclo 2 (0 blockers/altos, 1 medio + 2 bajos: medio y dry-run corregidos, TOCTOU documentado como límite aceptado). Ciclos de reviewer usados: 2/2.
- **Evidencia válida**: tests dirigidos 157 OK (antes del último fix). Regresión relevante tras los últimos fixes: ds_init completo 272 OK; harmessi tests 178 corridos con 2 errores de importación `import pytest` (test_fallback_cli, test_providers_cli; pytest no instalado, preexistentes y ajenos); lote guardrails drift / checkpoints @approved / boundaries / manifest parity / roadmap smoke / hook_rutas / scope / cards approvals 120 OK (1 skipped).
- **Falta (T6)**: escribir `verification.md` con las cifras de arriba y los límites (ventana TOCTOU, EOL mixto histórico no verificable, downgrade a Harmessi anterior, `.gitattributes` fuera del correctness); `ds_guard transition --a en_verificacion`; `validate --gate cierre`; `transition --a cerrada`; cerrar sesión; `git add` + commit local (sin push). NO regenerar `.ds_init/control.json` de este repo (se hace una vez en Change 6; `migrate-hashes` dry-run sobre este repo reconoce 119 migrables, 0 drift). No hace falta re-correr test_sync_baseline ni test_doctor_managed_hash: ya cubiertos por los lotes.
- **Decisiones congeladas**: managed text `sha256/eol-lf/v1`; managed binary `sha256/bin/v1`; `hash_alg` explícito por entrada, ausencia = legacy; migration ≠ upgrade ≠ re-adoption; sync nunca adopta drift preexistente; ApprovalRef/checkpoints (`hash_lf_v1`) y semantic guardrails drift sin cambios; `.gitattributes` no es requisito de correctness.
- **Pendiente mañana tras cerrar Change 1**: triage del feedback de uso real en `docs/feedback/` (fuera de Git) contra el código actual de `v0.10-dev`, sin implementar ni tocar el roadmap. Recordatorio para Change 4: un solo rol writer, N instancias con ownership disjunto, el Lead no escribe implementación, y el caso del writer que adelantó manualmente `estado:` de `tasks.md` en Change 0.

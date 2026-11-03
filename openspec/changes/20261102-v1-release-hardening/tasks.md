# Tareas — 20261102-v1-release-hardening

estado: cerrada

## Invocaciones planificadas
- python-data-engineer W1 y W2 (en paralelo, ownership disjunto): asset de licencia + anclas + tests de install/upgrade (W1);
  versión 1.0.0, README, docs, notas y smoke (W2).
- Lead: baseline `regenerar_control` una sola vez, regresión serial, install limpio, upgrade 0.15.0→1.0.0, Doctor, privacidad, clon sin tags.
- data-science-reviewer: revisión final del diff (máx. 2 ciclos).

## Ownership de writers
### W1 — python-data-engineer — T1
- HARMESSI-LICENSE.txt
- .gitattributes
- tools/ds_init/manifest.py
- tools/ds_init/tests/test_v1_license_asset.py
- tools/tests/test_license_anchor.py
- tools/tests/fixtures/license/**

### W2 — python-data-engineer — T2
- tools/ds_init/version.py
- CITATION.cff
- README.md
- ARCHITECTURE.md
- docs/contracts/README.md
- docs/installation.md
- docs/release-process.md
- docs/releases/v1.0.0.md
- docs/versioning.md
- tools/tests/test_v015_compat_window.py
- tools/tests/test_v1_release_hardening_smoke.py

## Historial de ownership
<!-- fecha — instancia — ruta — motivo (cambios de ownership hechos ANTES de que el writer edite) -->
2026-11-02 — Lead — `tools/tests/fixtures/license/polyform-shield-1.0.0.md` — golden oficial creado por el Lead (verificado idéntico a `LICENSE`).

## Skills cargados
<!-- - <skill> — <tarea> — <motivo> -->

## Tareas
- [x] T1 W1: `HARMESSI-LICENSE.txt` + manifest + `.gitattributes` + `test_license_anchor.py` + `test_v1_license_asset.py` (R1, R2, R5).
- [x] T2 W2: versión 1.0.0, README (Python, License, bloque v1.0.0), notas, docs en presente, smoke v1 (R3, R4, R8).
- [x] T3 Lead: baseline `regenerar_control` una sola vez; tests dirigidos (R6).
- [x] T4 Lead: regresión serial (2 lotes), privacidad, clon sin tags, Doctor; ver verification.md (R5–R7).
- [x] T5 reviewer GREEN; T6 fixes (ef8e74f); T7 verification.md y cierre.

## Dependencias
T3 depende de T1 y T2 (D4: el baseline se regenera al final). T4 depende de T3.

## Próximo paso exacto
Retomar con `--retomar`; T4: repetir regresión serial completa (2 lotes), privacidad y clon sin tags; luego T5-T7 (ver docs/roadmap/v1-readiness.md).
<!-- obligatorio si estado: pausada_bloqueada -->

# Spec — 20261020-v011-release-hardening

**R1.** `HARNESS_VERSION == "0.11.0"`, `CITATION.cff` `version: 0.11.0`, `.ds_init/control.json` `harness_version` coherente; ningún archivo de versión paralelo.
**R2.** `docs/releases/v0.11.0.md` en inglés: narrativa Operational Robustness & Recovery; cubre solo lo implementado (Git/scope fail-closed, ledger `correct`/`verify`, recovery de sesiones con `--retomar`, aislamiento de Changes paralelos 4B, `upgrade`/`recover`, completitud del manifest, Doctor); declara que H1 sigue UNCONFIRMED y que 4A no entró; no sobreactúa seguridad (tamper-evidence ≠ autenticidad, lock cooperativo, T0/declared); upgrading y known limitations.
**R3.** `test_v011_release_hardening_smoke.py`: versión coherente, Changes 0–6 cerrados/en verificación, notas con contenido clave y sin sobrepromesa, roadmap/README mencionan el release, privacidad (sin rutas personales/emails/feedback/.harmessi versionados), stdlib-only, migrate-hashes dry-run sin pendientes. Los smokes de releases anteriores que fijaban `0.10.0` se adaptan a «versión >= su release» sin perder cobertura.
**R4.** Baseline managed: `.ds_init/control.json` regenerado una sola vez (texto `sha256/eol-lf/v1`, binario `sha256/bin/v1`); dry-run de `migrate-hashes` sin migrables ni drift inesperado; cualquier excepción explicada.
**R5.** Doctor sobre este repo y sobre los proyectos dogfood: 0 ERROR; WARN/N-A explicados.
**R6.** Regresión completa por batches secuenciales (P=1, foreground, exit code por batch) con ledger `batch | attempted | passed | skipped | failed`; fallas atribuidas con baseline focalizado (`v0.10.0`); fallas nuevas corregidas y el batch repetido.
**R7.** Dogfooding reproducible con fixtures sintéticos: (A) proyecto nuevo con v0.11 (init, imports reales desde el destino instalado, Doctor, `ds_guard`, flujo mínimo de Change); (B) proyecto instalado con el tag público `v0.10.0` + estado project-owned representativo → `upgrade` dry-run, `--execute`, idempotencia, byte-identidad, Doctor; (C) upgrade interrumpido → Doctor lo detecta → `recover` → `upgrade` converge. Comandos y salidas en `verification.md`.
**R8.** Privacidad: barrido exhaustivo de lo versionado y de lo que entraría al commit; `docs/feedback/` y `.harmessi/` no versionados; fixtures genéricos.
**R9.** Publicación solo si R1–R8 verdes: `git fetch`, `origin/main == 2e76956`, fast-forward de `main`, tag anotado `v0.11.0` inexistente, push de `main` y del tag, GitHub Release si `gh` está autenticado; `v0.11-dev` NO se publica.

## Criterios de aceptación
- [ ] R1–R3 [ ] R4–R5 [ ] R6 [ ] R7 [ ] R8 [ ] R9

# Verificación — 20261015-v010-release-hardening

## Resumen
Change 6 de v0.10: endurecimiento del release 0.10.0. Implementado con instancias de `python-data-engineer` de ownership disjunto; el Lead no escribió implementación. Sin intervenciones de emergencia (sesión `s1` sin vencer).

## Qué entrega
- Versión 0.10.0: `tools/ds_init/version.py`, `CITATION.cff` (date-released 2026-10-15), `.ds_init/control.json` (`harness_version` 0.10.0). No existen archivos VERSION.
- `docs/releases/v0.10.0.md` (inglés), viñeta v0.10 en README, roadmap v0.10 y README de roadmap.
- `tools/tests/test_v010_release_hardening_smoke.py`; `test_v09_release_hardening_smoke.py` ya no fija 0.9.0 (`test_version_no_regresiona`).
- Corrección del manifest: `tools/ds_init/manifest.py` ahora instala `tools/dsguard/guardrails_adoption.py`, `human_presence.py` y `scope_amendments.py` (3 entradas VERBATIM).

## Evidencia obtenida
- Audit inicial: `migrate-hashes` dry-run = 105 migrables, 14 no verificables (drift), 0 desconocidas. Los 14 archivos con drift (3 agentes, SKILL.md, methodology.md, sdd.md, verificador.md, templates/tasks.md, ds_guard.py, dsguard/{pathguard,repo,scope,sdd}.py, dsimpact/git_source.py) figuran todos en `git diff --name-only v0.9.0..HEAD`: cambios legítimos de Changes 1–5, no corrupción.
- Se ejecutó `migrate-hashes --execute` (105 migradas, idempotente) y `ds_init.control.regenerar_control(..., stage=experiment)` (mismo mecanismo que «Refresh release control» de v0.9): `harness_version` 0.9.0 -> 0.10.0; entradas 119 -> 124 (nuevos administrados: `templates/skill.md`, `skill_contract.py`, `ownership.py`, `domain-modeling.md`, `glossary.py`) y 127 tras el fix del manifest. Todas con `hash_alg` vigente (texto `sha256/eol-lf/v1`, binario `sha256/bin/v1`). Dry-run posterior: Migrables 0, Ya actuales 127, No verificables 0, Desconocidas 0. Idempotente.
- Bug real hallado por la primera corrida de la regresión completa: el manifest no instalaba los 3 módulos dsguard de Changes 2 y 3, pero `ds_guard.py` los importa; un proyecto instalado fallaba al importar `ds_guard` (`ImportError: cannot import name 'scope_amendments'`). Lo detectaron `test_manifest_dsguard_parity` y 5 tests de instalación de `ds_init`. Corregido y baseline regenerado; no había otros módulos faltantes.
- Regresión completa final (una corrida tras el fix, en 6 flujos paralelos; runner unittest para directorios unittest y pytest del `.venv` para los pytest):
  - unittest: 5463 tests ejecutados, 60 skipped (Parquet sin `pyarrow` en el venv del repo, etc.): `tools/tests` 2085, `ds_init` 276, `harmessi` 199, `cards` 1279, modelquality 108, qualityevidence 85, datacontracts 185, autonomy 153, reporting 856, ds_profile 169, dsimpact 68.
  - pytest: 364 passed (datasources 133, leadrun 107, fallback 29, harmessi_bench 29, providers 45, routing 21).
  - 5 resultados no verdes fueron artefactos del runner: 2 tests de `test_ds_guard_exec_approve.py` y 2 módulos de `tools/harmessi/tests` (`test_fallback_cli`, `test_providers_cli`) requieren `pytest` (ausente en el Python del sistema); reejecutados con el pytest del `.venv`: 32 passed. El quinto, `test_dry_run_luego_execute_instala_correctamente` de `ds_init`, falló solo porque el `PYTHONPATH` exportado para otros lotes contaminaba el subproceso del proyecto instalado; reejecutado sin `PYTHONPATH`: OK. Resultado: 0 fallos reales.
- Smoke dirigido (`test_v010_release_hardening_smoke` + `test_v09_release_hardening_smoke` + `test_manifest_dsguard_parity` + integración de instalación): 45 OK sin `PYTHONPATH`.
- Doctor sobre el repo: 29 OK, 1 WARN (`CORE-WORKING-TREE`, esperado hasta commitear), 0 ERROR, 4 N/A; sin `HARMESSI-DRIFT`.
- Privacidad: sweep del smoke (rutas personales, proyectos, emails) en verde; `docs/feedback/` y `.harmessi/` ignorados y no versionados; `GLOSSARY.md` no existe en el repo.
- Reviewer `data-science-reviewer`, ciclo 1 de máx. 2 (sin truncamiento): 0 bloqueantes, 3 importantes (roadmap seguía diciendo Change 3 «pendiente de aceptación»; estados «pendiente de publicar con el release» obsoletos en un documento que dice PUBLICADA; sobreafirmación en las notas: «require a verifiable T1 approval» para `scope show`/dry-run) y 7 menores (acotar «standard library only», «Existing installations keep working», append-only no autenticado, aserciones débiles del smoke: returncode, `hash_alg` por entrada, nombre del test de v0.9). Todos corregidos. Ciclo 2 no necesario: los fixes son de redacción y tests, sin información nueva.
- Intervenciones de emergencia: ninguna.

## Fingerprint de dataset/artefacto (condicional — cambio sensible o reproducibilidad crítica)
No aplica (sin datasets). El baseline gestionado queda en `.ds_init/control.json` (127 entradas, `harness_version` 0.10.0).

## Diferencias contra la spec
- R6 «regresión completa en batches» se ejecutó en 6 flujos paralelos (no secuenciales) por tiempo de pared.
- R7 (publicación) se registra al final de este archivo por el Lead, no por el writer.
- Alcance: la corrección de `tools/ds_init/manifest.py` no estaba prevista en el plan inicial; quedó dentro del scope del Change (`tools/**`) y se registró en el historial de ownership.

## Limitaciones
- GitHub Release: `gh` no está instalado en el host; se crea manualmente desde la UI si no hay otra herramienta (el tag y el push son el release técnico).
- T1 validado solo en Windows.
- El hook H1 sigue UNCONFIRMED.
- La primera corrida completa (pre-fix) mostró fallos de manifest/instalación; la evidencia final corresponde a la corrida posterior al fix.

## Pendientes derivados
Deudas diferidas listadas en `docs/roadmap/v0.10.md`: ledger amend/correct, enum de decisiones, `ds_profile` columnar, T2, scratchpad externo, skills adicionales.

## Resultado final
Change 6 cumple R1–R6, R8 y R9. R7 (publicación) pendiente de ejecutar tras este cierre; el Lead lo registra aquí.

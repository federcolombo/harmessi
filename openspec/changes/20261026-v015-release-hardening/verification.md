# Verificación — 20261026-v015-release-hardening (C7)

Todos los números salen de las corridas del 2026-10-27 (Windows 11, Python 3.12, un solo host). Ledger de la
regresión y salida del runner de release: archivos locales no versionados (`%TEMP%/reg15/ledger.txt`,
`.harmessi/release_v015/evidencia.json`).

## R1/R2 — Versión y baseline
- `HARNESS_VERSION` 0.15.0, `CITATION.cff`, `.ds_init/control.json` y `docs/releases/v0.15.0.md` coherentes (commit `3cb8088`).
- Baseline regenerado una sola vez. Doctor: `HARMESSI-DRIFT` OK en checkout, instalación limpia y upgrade.

## R4 — Regresión serial (P=1, en lotes, con ledger)
| Lote | Resultado |
|---|---|
| `tools/tests` (primera corrida, `-x`) | 1945 passed, 10 skipped, 1 failed (corte) |
| `tools/tests` resto, desde el archivo que falló | 712 passed, 7 skipped, 2 failed (14002 warnings) |
| `tools` excluyendo `tools/tests` | 4575 passed, 57 skipped, 0 failed |

Los 3 fallos eran del mismo tipo y se resolvieron: `test_v012/v013/v014_release_hardening_smoke` exigían
`.claude/settings.json` idéntico al de los tags v0.11/v0.12/v0.13. El único cambio es la activación humana,
ya verificada en vivo, de los hooks `SubagentStart`/`SubagentStop` (C4). Los guards ahora comparan el resto
del archivo y aceptan solo esos dos eventos (commit de C7). Re-corridos: 84 passed.
No se repitieron módulos verdes. Los 3 archivos corregidos se re-ejecutaron tras el arreglo; el resto de la
suite corrió una sola vez.

## R4 — Install, upgrade, Doctor, privacidad (runner único, 14 pasos, todos OK)
- Install limpio (dry-run + execute), venv, entry point `ds_guard status` desde el proyecto instalado: OK.
- Upgrade v0.14.0 -> v0.15.0 (instalado con el código del tag v0.14.0): 8 actualizados, 3 creados, 0 drift.
- Upgrade repetido: "Nada que hacer", 0 a actualizar / 0 a crear / 0 drift (idempotente).
- `recover` (dry-run) tras el upgrade: OK. Interrupción/recuperación cubiertas por tests de `tools/ds_init/tests` (regresión).
- Doctor: checkout, instalación limpia y upgrade -> 36 OK, 0 WARN, 0 ERROR.
- Privacidad: `test_privacy_sweep` OK (heurístico).
- Límite: el runner no ejecutó el upgrade desde v0.13.0; esa ventana se cubre con fixtures de tags reales.

## R3 — Matriz de readiness contra `docs/roadmap/v1.0.md`
| # | Criterio | Estado | Evidencia / límite |
|---|---|---|---|
| 1 | Contratos CLI estables | PARTIAL | Exit codes de 3 CLIs public-candidate comprometidos (B-03); el resto sigue experimental/internal (inventory: 6/13/31). |
| 2 | Schemas versionados y migrables | PARTIAL | Contratos con schema_version y lector; Data Card {1,2}; `.ds_init/control.json` sin schema_version por decisión (B-02). Migración no universal. |
| 3 | Upgrade/migration probado | PASS | Corrida v0.14.0 -> v0.15.0 + idempotencia + Doctor (arriba). v0.13: solo fixtures. |
| 4 | Backward compatibility formal | PARTIAL | Ventana 0.13–0.15 solo para artefactos con test (`docs/versioning.md`); v0.14 no lee Data Card v2. |
| 5 | CI cross-platform | PARTIAL | Workflow ubuntu/windows/macos existe; solo Windows ejecutado. Remoto: pending observation. Python 3.9 sin cubrir. |
| 6 | Instalación y upgrades reproducibles | PASS | Runner único repetible; verificado en Windows únicamente. |
| 7 | Compatibilidad de providers | PARTIAL | `claude_code` live-validated (un host); codex/gemini/grok solo contract-tested (`docs/providers.md`). |
| 8 | Evals/benchmarks públicos | ACCEPTED LIMITATION | Suite y formato documentados (`docs/evaluation.md`); sin baseline numérico (B-26). |
| 9 | Release process repetible | PASS | `docs/release-process.md` seguido en este release; límite: sin comando dedicado de baseline. |
| 10 | Documentación pública completa | PARTIAL | Docs escritas (`docs/*.md`, `test_public_docs`); no validadas con lector externo. |
| 11 | Privacidad/portabilidad verificadas | PARTIAL | Barrido heurístico verde; portabilidad ejecutada solo en Windows. |
| 12 | Estrategia de deprecación | PASS | `docs/deprecation.md`, `tools/harmessi/deprecation.py`, tests (B-04). |
| 13 | Recuperación ante instalaciones parcialmente migradas | PASS | Journal + `recover` (tests `test_recover*`, `test_journal_persistente`); dry-run ejecutado tras upgrade. |
| 14 | Versionado semántico consistente | PASS | `docs/versioning.md`, `test_constantes_de_version_ancladas`. |

Sin FAIL. PASS 5, PARTIAL 8, ACCEPTED LIMITATION 1.

## Límites declarados
Procedencia no criptográfica; privacidad heurística; un solo host live-validated; solo Windows ejecutado;
CI remoto sin observar; GitHub Release UI pendiente (manual); un solo juego de 3 Changes (C4–C6) con brecha
de cierre SDD registrada en `docs/roadmap/v0.15.md`.

## Conclusión (provisoria hasta el cierre SDD de C4–C6)
Sin FAIL y con los ítems B bloqueantes cerrados o reclasificados con evidencia: **READY FOR v1.0 PLANNING**,
Condición cumplida: C4, C5, C6 y el corrective `20261027-v015-scope-closure-corrective` están en estado `cerrada` (2026-10-30).

## Evidencia obtenida
Regresión serial, install limpio, upgrade v0.14.0 -> v0.15.0 (idempotente), `recover` dry-run, Doctor (36 OK, 0 WARN, 0 ERROR) y barrido de privacidad: ver secciones R1–R4 arriba (corridas del 2026-10-27). Matriz de readiness R3 sin FAIL (PASS 5, PARTIAL 8, ACCEPTED LIMITATION 1). C4, C5, C6 y el corrective están `cerrada`; C7 pasó `validate` solo con hallazgos informativos tras dos enmiendas T1 de scope.

## Resultado final
Release técnico v0.15.0 listo: sin FAIL en readiness. Límites declarados arriba (CI remoto sin observar, GitHub Release UI pendiente, un solo host). Merge, tag y push se registran en T5.

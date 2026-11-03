# Verificación — 20261102-v1-release-hardening

Todos los números salen de las corridas del 2026-11-02 y 2026-11-03 (Windows 11, un solo host, `.venv` del proyecto).

## Commits del Change
| Commit | Contenido |
|---|---|
| `ef754f9` | WIP: asset `HARMESSI-LICENSE.txt`, ancla de licencia, versión 1.0.0, docs y notas |
| `ef8e74f` | Fixes del reviewer (M2 drift real, M3 CI acotado, L1, L3) |
| `576687f` | Baseline `.ds_init/control.json` regenerado una sola vez (1.0.0, +`HARMESSI-LICENSE.txt`; 135 archivos) |
| `baaf412` | Pausa con estado persistido |
| (cierre) | Esta verificación y cierre |

No hubo enmiendas de scope. El baseline se regeneró una sola vez (R6); no hubo regeneraciones posteriores.

## Regresión serial (corrida desde cero el 2026-11-03; la corrida incompleta del 2026-11-02 NO cuenta)
| Lote | Comando | Resultado |
|---|---|---|
| 1 | `pytest -q tools/tests` | 1 failed, 2759 passed, 17 skipped, 38161 subtests passed (43:43) |
| 2 | `pytest -q tools --ignore=tools/tests` | 4581 passed, 57 skipped, 4025 subtests passed, 0 failed (1:00:29) |

### Fallo explicado del lote 1 (preexistente, no causado por este Change)
- `tools/tests/test_parallel_change_isolation.py::TestAtribucion::test_informativos_constante` espera
  `CODIGOS_INFORMATIVOS == {"ALCANCE-ATRIBUIDA-OTRO-CHANGE"}`, pero `tools/dsguard/scope.py` suma desde el Change
  `20261027-v015-scope-closure-corrective` (commits `00c6d0c`, `7c5a2a8`) `ALCANCE-VENTANA-ACOTADA`, `ALCANCE-VENTANA-AMBIGUA`
  y `ALCANCE-PROTEGIDA-ATESTADA`. Es un test desactualizado desde v0.15; este Change no modificó `scope.py` ni ese test.
- Re-ejecutado aislado antes del fix: falla igual (1 failed).
- **Fix aplicado** (una sola enmienda T1 `console_confirmed`, 2026-11-03, scope hash `0917023b…` → `7cdbaae498091a04672ff0a9b95e7e4b29acea5104f22a1d7e2ab66aec28bf53`,
  revisión 1, registro en `amendments.jsonl`): el test ahora espera los 4 códigos vigentes. Rutas agregadas:
  `openspec/changes/20261030-v1-contract-stabilization/control.json` (telemetría y cierre residual de la sesión s4 del Change anterior)
  y `tools/tests/test_parallel_change_isolation.py`.
- Resultado tras el fix: `pytest -q tools/tests/test_parallel_change_isolation.py` → 44 passed, 19 subtests passed (3:31).
  El lote 1 queda sin fallos (era el único); no se repiten los lotes porque `scope.py` y el resto del código no cambiaron.

## Barrido de privacidad
- `pytest -q tools/tests/test_privacy_sweep.py`: 20 passed, 29 subtests passed.
- Revisión manual sobre archivos versionados: sin emails ni rutas personales. Solo aparece el handle público
  `federcolombo` (URL del repo, licencia, NOTICE, CITATION) y `"usuario": "fcolombo"` en una atestación de v0.15
  (`openspec/changes/20261026-v015-runtime-observability/protected-attestations.jsonl`, preexistente).

## Clon sin tags
- `git clone --no-tags` del HEAD (0 tags) y corrida de los 58 archivos de tests que mencionan tags o versiones `v0.1x.0`:
  1487 passed, 12 skipped, 879 subtests passed, 0 failed.

## Doctor, install y upgrade
- Doctor en el checkout: 35 [OK], 1 [WARN], 0 [ERROR], 4 [N/A]. El WARN es `CORE-WORKING-TREE` (cambios sin commitear de la
  sesión en `control.json`); sin `HARMESSI-DRIFT`.
- Evidencia de la sesión s1 (corridas del 2026-11-02, registradas en `docs/roadmap/v1-readiness.md`): install limpio 1.0.0
  (135 archivos, Doctor 0 ERROR); upgrade real desde el tag `v0.15.0` (a crear 1, drift 0, repetición "Nada que hacer", Doctor 0 ERROR).
- `.ds_init/control.json`: versión `1.0.0`, 135 archivos.

## Reviewer
- Ronda final: GREEN con los fixes M2, M3, L1, L3 aplicados (`ef8e74f`).

## Matriz de requisitos
| Req | Estado | Evidencia |
|---|---|---|
| R1 | PASS | `test_v1_license_asset.py`, manifest, baseline, install |
| R2 | PASS | `test_license_anchor.py` con golden |
| R3 | PASS | README / installation.md (3.12 verificado, 3.9 no ejecutado) |
| R4 | PASS | `test_v1_release_hardening_smoke.py`, `test_v015_compat_window.py` |
| R5 | PASS | upgrade 0.15.0→1.0.0, idempotente |
| R6 | PASS | baseline regenerado una vez; Doctor 0 ERROR |
| R7 | PASS | lotes 1 y 2 (único fallo corregido y re-verificado), privacidad, clon sin tags |
| R8 | PASS | `test_v1_stable_contracts`, `test_public_docs`, `test_privacy_sweep` verdes |

## Límites declarados
Un solo host; Python 3.9 no ejecutado; CI remoto aún no corrido sobre el commit/tag final.

## Resultado final
**GREEN**. Sin BLOCKER, HIGH ni deuda abierta de tests.

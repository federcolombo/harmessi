# Verificación — 20261030-v1-contract-stabilization

Todos los números salen de las corridas del 2026-11-02 (Windows 11, un solo host, `.venv` del proyecto).

## Alcance final
- Baseline: `1f81687` (rama `v1-dev`). Scope hash inicial `3311bf5d…`.
- Una enmienda T1 (`console_confirmed`, 2026-11-02) agregó únicamente `tools/tests/cli_surface.py`
  (hash final `f20a4a1a3bb0ef50873be11575e73356b951c4d0b3751bef7a8dcd17a6b7e20b`; registro en `amendments.jsonl`).
- No se tocó código de producción, `HARNESS_VERSION`, hooks ni el repo público.

## Commits del Change
| Commit | Contenido |
|---|---|
| `c1894bc` | WIP: fixtures `v0_15`, tests stable, inventory y docs 1.x |
| `fbdc847` | Hallazgos del reviewer (ronda 1) en `docs/roadmap/v1-readiness.md` |
| `f287fb0` | Fixes H1 (exit codes acotados), H2 (doc-test de ventana), M1 (claves desconocidas en sub-objetos) |
| `fb62461` | Fixes M2–M5 y LOW (redacción, snapshot CLI v2, fixtures reproducibles, helper único) |
| (cierre) | MEDIUM-1/2 de la ronda final y esta verificación |

## Tests
| Corrida | Resultado |
|---|---|
| `test_v1_stable_contracts`, `test_v013_contract_inventory`, `test_v015_compat_window` (tras `fb62461`) | 132 passed |
| Final: los 3 anteriores + `test_public_docs` + `test_privacy_sweep` + `tools/datasources/tests` + `tools/harmessi_bench/tests` | 660 passed, 108 subtests passed, 0 failed |

No se corrió la regresión serial completa de `tools/`: queda para el Change 2 (`v1-release-hardening`), que la incluye.

## Fixtures
- `tools/tests/fixtures/compat/v0_15/` generado desde `git archive v0.15.0` con `generate_v015.py`.
- SHA del tag `v0.15.0`: objeto del tag anotado `e788031f6edd2fbc2b7daaba623234cbf2142cb6`; **commit** `7e7c681acae2772f9dcff336b9bbc004ec5a1802`
  (registrado como `commit_origen` en el MANIFEST).
- Reproducible: dos regeneraciones consecutivas son idénticas (`diff -r` sin diferencias). `eval_result.json` normalizado (timestamps, plataforma, git y sesiones fijos).
- Privacidad: el reviewer no encontró rutas absolutas, usuarios, hosts ni UNC en los 5 archivos.

## Reviewer
- Ronda 1 (parcial): H1, H2, M1–M5 y LOW; todos aplicados salvo el LOW de abajo.
- Ronda final: **GREEN**, 0 BLOCKER, 0 HIGH, 2 MEDIUM, 5 LOW.
  - MEDIUM-1 (doc-test de ventana vacuo): resuelto, ahora ancla dentro de `## Ventana de compatibilidad`.
  - MEDIUM-2 (README decía fixtures sintéticos): resuelto.
  - LOW aceptados, sin afectar el contrato estable (pasan al Change 2 o quedan como deuda):
    - `comparar_superficie` no detecta cambios de `type`/`action` (fuera de lo prometido: subcomandos, flags, required, choices).
    - Falta test de que las entradas de `fields` ignoran claves desconocidas.
    - Exit codes anclados solo por presencia textual en el módulo (la promesa quedó acotada a 0 / distinto de 0).
    - `True` y `1.0` aceptados como `schema_version` en `tools/datasources/registry.py` (producción, fuera de scope) → Change 2.
    - `test_v015_compat_window.py` ancla `HARNESS_VERSION == "0.15.0"` → Change 2 debe actualizarlo en el bump.
  - Áreas que el reviewer declaró no alcanzar: consumidores de `SourceObservation` en `ds_guard.py` y `datacontracts/validation.py`, y el diff literal de `test_v015_compat_window.py`.

## Los 6 contratos `stable` (confirmados por inventory, spec R2 y `IDS_STABLE`)
`cli-ds-guard`, `cli-ds-init`, `cli-harmessi`, `schema-source-observation`, `schema-source-registry`, `schema-eval-result`.

## Límites declarados
Un solo host; sin regresión serial completa; promesa de exit codes acotada a 0 / distinto de 0; `HARNESS_VERSION` sigue en 0.15.0 (bump en Change 2).

## Resultado final
Sin BLOCKER ni HIGH. **GREEN**: los 6 contratos quedan preparados como `stable` para 1.0.0.

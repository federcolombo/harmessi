# Propuesta — 20261023-v014-roadmap-and-improvement-audit

## Problema
v0.13 dejó la Evaluation Foundation (casos, suites, run manifest, veredictos) pero no hay forma gobernada de proponer, probar y comparar variantes de superficies Optimizable.

## Objetivo
Auditar la base v0.13 y congelar el roadmap de v0.14 (Evidence-Driven Harness Improvement) sin duplicar primitivas.

## Evidencia
`tools/harmessi_bench/{core,runner,compare,runmanifest,suite,storage,redact}.py`; `tools/dsguard/skill_contract.py:192` (`superficie_de_ruta`); `tools/ds_init/check_manifest_parity.py` (`SOLO_CHECKOUT`); `docs/roadmap/v0.13.md`.

## Supuestos descartados
- Que hiciera falta un runtime de evals nuevo: `run_scenario_set` + `compare_runs` + `construir_manifest` alcanzan.
- Que el engine pudiera ser candidate: `tools/` es Protected por `superficie_de_ruta`.

## Alcance
`docs/roadmap/v0.14.md`, `docs/roadmap/README.md` y este SDD. Solo documentación.

## Fuera de alcance
Código, tests, cambios en `.ds_init/control.json`, push, tag.

## Aprobación
- Usuario: Federico Colombo
- Fecha: 2026-10-23
- Alcance aprobado: Harmessi v0.14 Change 0
- Versión de artefactos referenciada: ver control.json

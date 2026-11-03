# Propuesta — 20261021-v013-eval-benchmark-foundation

> Change 1 de v0.13: Evaluation & Benchmark Foundation. Extiende `tools/harmessi_bench` (v0.5); no crea un paquete paralelo.

## Problema
`harmessi_bench` mide un set de escenarios pero: el caso y el resultado no están versionados; no hay noción de suite/benchmark con manifest determinista;
`compare_runs` clasifica por escenario pero no emite un veredicto global ni verifica que las dos corridas sean comparables; no hay casos públicos incluidos en el repo;
no existe el boundary «se puede evaluar una variante Optimizable, nunca promover Protected».

## Objetivo
Dejar una primitiva pequeña, provider-neutral y determinista para evaluar el harness de forma reproducible y comparar baseline vs candidate con 4 veredictos
(`candidate_better`, `baseline_better`, `equivalent`, `inconclusive`) solo con evidencia determinista suficiente. Evals ≠ tests.

## Evidencia
- `tools/harmessi_bench/core.py` (Scenario, EvalResult, scorers `contains`/`regex`/`exact`), `scenarios.py`, `storage.py`, `compare.py`, `runner.py`, `cli.py`.
- `tools/harmessi_bench` figura como «solo checkout» en `check_manifest_parity.SOLO_CHECKOUT` y `test_manifest_completitud.SOLO_CHECKOUT`: no se instala en proyectos.
- `tools/tests/test_v05_core_neutrality.py` fija la pureza de `core.py`/`runner.py`.
- `tools/dsguard/skill_contract.superficie_de_ruta` (v0.12) clasifica rutas en protected/optimizable/project-owned.

## Supuestos descartados
- Paquete de evals nuevo: se extiende el existente.
- Scorer LLM-as-judge: no se agrega; un veredicto no puede basarse solo en juicio de LLM.
- Instalar `harmessi_bench` en proyectos: sigue siendo solo-checkout (herramienta de desarrollo de Harmessi).

## Alcance
- Contrato de caso versionado (`case_contract_version`, ausente = 0 legado) y campos opcionales `fixtures` y `surface_under_test`.
- Suite: manifest JSON determinista (`suite_contract_version`, `suite_id`, `suite_version`, `cases_file`, `case_ids`) con `suite_hash` calculado; carga fail-closed.
- Resultado versionado (`schema_version`, `evaluator_version`, bloque `suite` opcional); lectura de resultados sin versión.
- Veredicto baseline vs candidate en `compare.py` + resumen legible por máquina y por humano.
- CLI: `run --suite`, `suite-check`, `compare` imprime/emite el veredicto.
- Suite pública sintética `harmessi-core-synthetic` (casos genéricos: framing, debugging, domain modeling, codebase design, recovery, contrato de herramientas).
- Boundary de superficies: `surface_under_test` debe ser Optimizable; una ruta Protected se rechaza.
- Docs: `ARCHITECTURE.md`, `README.md`, resultado en `docs/roadmap/v0.13.md`.

## Fuera de alcance
Run manifest/identidad de corrida y resume (Change 2); conformance de providers/adapters (Change 3); generación automática de candidates, promoción, leaderboard,
servicio, telemetría, scorer LLM; instalar bench en proyectos; cambios de versión.

## Aprobación
- Usuario:
- Fecha:
- Alcance aprobado:
- Versión de artefactos referenciada:
- Cita o descripción fiel de qué se aprobó:

## Alcance autorizado

- tools/harmessi_bench/__init__.py
- tools/harmessi_bench/core.py
- tools/harmessi_bench/scenarios.py
- tools/harmessi_bench/suite.py
- tools/harmessi_bench/storage.py
- tools/harmessi_bench/compare.py
- tools/harmessi_bench/cli.py
- tools/harmessi_bench/suites/*.json
- tools/harmessi_bench/scenarios/*.json
- tools/harmessi_bench/tests/*.py
- tools/tests/test_v05_core_neutrality.py
- tools/tests/test_v013_eval_foundation_smoke.py
- ARCHITECTURE.md
- README.md
- docs/roadmap/v0.13.md
- openspec/changes/20261021-v013-eval-benchmark-foundation/**

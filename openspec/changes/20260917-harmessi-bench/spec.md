# Spec — 20260917-harmessi-bench

## Requisitos

- **R1**: `tools/harmessi_bench/core.py` define, sin importar `subprocess` ni ningún proveedor
  concreto (solo stdlib + `tools.providers.core` para tipos), los dataclasses `Scenario`,
  `ScoreResult`, `EvalTarget`, `EvalResult`.
- **R2**: `core.py` expone scorers puros `texto: str, params: dict -> ScoreResult`:
  `scorer_contains`, `scorer_regex`, `scorer_exact`, registrados en `SCORERS`, y una función
  `aplicar_scorer(texto, expected) -> ScoreResult` que resuelve por `expected["tipo"]` y nunca
  lanza `KeyError` sin manejar ante un tipo desconocido.
- **R3**: `tools/harmessi_bench/scenarios.py` expone `load_scenarios(path) -> List[Scenario]`, que
  valida `scenario_id`/`prompt`/`expected` en cada entrada y falla cerrado (`ValueError` citando el
  índice del escenario problemático) ante un escenario mal formado, sin silenciarlo.
  `tools/harmessi_bench/scenarios/examples.json` contiene 3 escenarios triviales, baratos de
  verificar, con scoring determinista, y una nota explícita de que es un set demostrativo.
- **R4**: `tools/harmessi_bench/runner.py` expone `run_scenario` y `run_scenario_set`, que invocan
  un target vía un adapter de `tools.providers.core.ProviderAdapter`, distinguen explícitamente
  indisponibilidad (`ok=False`) de mala calidad de output (scoring), soportan stdout no-JSON como
  fallback de texto a scorear, y no abortan la corrida completa si un escenario individual lanza
  una excepción inesperada.
- **R5**: `tools/harmessi_bench/storage.py` expone `save_run`/`load_run` sobre
  `.harmessi/evals/<run_id>/result.json`, con `load_run` fallando cerrado (`FileNotFoundError`) si
  el `run_id` no existe.
- **R6**: `tools/harmessi_bench/compare.py` expone `ComparisonReport` y `compare_runs(baseline,
  candidate)`, que compara por `scenario_id` sin asumir que ambas corridas comparten el mismo set de
  escenarios (regressions/improvements/unchanged/solo_en_baseline/solo_en_candidate).
- **R7**: `tools/harmessi_bench/cli.py` expone `run` y `compare` vía `argparse`, resolviendo el
  adapter desde `tools.providers.PROVIDER_REGISTRY` (import diferido), verificando disponibilidad
  con `.detect()` antes de invocar, y devolviendo exit code distinto de 0 con mensaje claro (sin
  traceback) ante provider inexistente o no disponible.
- **R8**: la suite de tests nueva (`tools/harmessi_bench/tests/test_core.py`, `test_scenarios.py`,
  `test_runner.py`, `test_storage.py`, `test_compare.py`, `test_cli.py`) cubre los 3 scorers,
  `aplicar_scorer` con tipo desconocido, `load_scenarios` sobre el `examples.json` real y sobre un
  escenario mal formado, `run_scenario`/`run_scenario_set` con un `FakeAdapter` (invocación exitosa,
  indisponible, stdout no-JSON, excepción interna), round-trip de `save_run`/`load_run` y
  `FileNotFoundError`, los 5 casos de `compare_runs`, y el CLI (provider inexistente, corrida
  exitosa con `FakeAdapter` monkeypatcheado, `compare` sobre corridas reales guardadas).
- **R9**: cero dependencias nuevas de terceros.

## Criterios de aceptación

- **R1**: Given se inspeccionan los dataclasses de `core.py`, When se revisan sus campos, Then
  coinciden exactamente con los descriptos en `design.md`/el prompt del Change (`Scenario`,
  `ScoreResult`, `EvalTarget`, `EvalResult`), y ningún import de `core.py` es `subprocess` ni un
  módulo de `tools.providers.<proveedor concreto>`.
- **R2a**: Given `scorer_contains("el resultado es OK", {"valores": ["OK"]})`, When se evalúa, Then
  `passed=True` y `score=1.0`.
- **R2b**: Given `scorer_contains("hola", {"valores": ["OK", "chau"]})`, When se evalúa, Then
  `passed=False` y `score=0.0` (ninguno de los dos valores presente).
- **R2c**: Given `aplicar_scorer("texto", {"tipo": "tipo-inexistente"})`, When se llama, Then
  devuelve `ScoreResult(passed=False, score=0.0, detail=...)` sin lanzar excepción.
- **R3a**: Given `scenarios/examples.json` real, When se llama `load_scenarios`, Then devuelve 3
  `Scenario` con `scenario_id`/`prompt`/`category`/`tags`/`expected` correctos.
- **R3b**: Given un JSON con un escenario en el índice 1 sin la clave `expected`, When se llama
  `load_scenarios`, Then lanza `ValueError` cuyo mensaje cita el índice `1`.
- **R4a**: Given un `FakeAdapter.invoke()` que devuelve `ok=True` con stdout JSON
  `{"result": "OK"}` y `scenario.expected={"tipo": "exact", "valor": "OK"}`, When se llama
  `run_scenario`, Then `score.passed=True`.
- **R4b**: Given un `FakeAdapter.invoke()` que devuelve `ok=False,
  availability_error="unavailable"`, When se llama `run_scenario`, Then el `EvalResult` tiene
  `score.passed=False` con `detail` mencionando `unavailable`, sin haber invocado ningún scorer.
- **R4c**: Given un `FakeAdapter.invoke()` con stdout que no es JSON válido, When se llama
  `run_scenario`, Then usa el stdout crudo como texto a scorear sin lanzar excepción.
- **R4d**: Given `run_scenario_set` con un escenario cuyo `expected` provoca una excepción interna
  durante el scoring, When se corre el set completo, Then el resto de los escenarios se ejecutan y
  el escenario problemático queda registrado con `ok=False` y `detail` describiendo el error.
- **R5**: Given `save_run(run_id, resultados, target, root=tmp_path)` seguido de `load_run(run_id,
  root=tmp_path)`, When se comparan, Then el dict cargado reproduce fielmente los datos guardados; y
  Given un `run_id` inexistente, When se llama `load_run`, Then lanza `FileNotFoundError`.
- **R6**: Given dos corridas fabricadas con escenarios superpuestos parcialmente (uno que regresa,
  uno que mejora, uno sin cambio, uno solo en baseline, uno solo en candidate), When se llama
  `compare_runs`, Then el `ComparisonReport` clasifica correctamente los 5 casos.
- **R7a**: Given `python -m tools.harmessi_bench.cli run --provider no-existe ...`, When se corre,
  Then el exit code es `1` y el mensaje de error no incluye traceback.
- **R7b**: Given un provider registrado cuyo `.detect().available` es `False` (monkeypatch), When se
  corre `run`, Then el exit code es `1` sin haber intentado invocar.
- **R8**: Given se corre `python -m pytest tools/harmessi_bench/tests`, When termina la corrida,
  Then todos los tests nuevos pasan (verificación real la hace el Lead, ver `tasks.md`).
- **R9**: Given se inspecciona el diff completo del Change, When se revisan los imports nuevos,
  Then no aparece ninguna dependencia de terceros no presente ya en el proyecto.

## Unidad de análisis / grain (condicional — data_understanding, feature_engineering, modeling)
No aplica — este cambio es infraestructura de evals del harness, no un dataset ni un modelo de un
proyecto DS.

## Cutoff / information boundary (condicional — feature_engineering, data_preparation, modeling)
No aplica — mismo motivo que arriba.

## Baseline (condicional — modeling)
No aplica — mismo motivo que arriba.

## Métrica primaria (condicional — modeling, evaluation)
No aplica — mismo motivo que arriba.

## Métricas secundarias (opcional)
No aplica — mismo motivo que arriba.

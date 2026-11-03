# Spec — 20261021-v013-eval-benchmark-foundation

## A. Caso de evaluación
**R1.** `Scenario` conserva sus campos; agrega `fixtures: dict` (default `{}`) y `surface_under_test: Optional[str]` (default `None`). Constante `CASE_CONTRACT_VERSION = 1`.
**R2.** `load_scenarios` acepta `case_contract_version` top-level: ausente ⇒ 0 (legado, se lee igual); 0 y 1 soportados; cualquier otro valor, no entero o bool ⇒ `ValueError` (fail-closed). Casos con `scenario_id` duplicado ⇒ `ValueError`.
**R3.** Si un caso declara `surface_under_test`, `superficie_de_ruta` debe dar `optimizable`; `protected` o `project-owned` ⇒ `ValueError` citando el caso (boundary de superficies).
**R4.** No hay scorer nuevo basado en LLM; `SCORERS` mantiene `contains`/`regex`/`exact`.

## B. Suite / benchmark
**R5.** `tools/harmessi_bench/suite.py` define `Suite` (`suite_id`, `suite_version`, `case_ids`, `suite_hash`, `case_contract_version`, `description`) y `load_suite(path)`. Manifest JSON con `suite_contract_version` (=1), `suite_id`, `suite_version` (int ≥ 1), `cases_file` (relativo al manifest, sin `..` ni absoluto) y `case_ids`.
**R6.** `load_suite` falla cerrado (`ValueError`) si: falta un campo, `suite_contract_version` desconocida, `case_ids` vacío/duplicado, `cases_file` fuera del directorio de la suite, o `case_ids` ≠ ids del archivo de casos (faltante o sobrante).
**R7.** `suite_hash` = sha256 hex de la serialización JSON canónica (claves ordenadas, `ensure_ascii`) de la lista ordenada por id de `{scenario_id, prompt, expected, case_contract_version, fixtures, surface_under_test}`; independiente del orden de archivo, de finales de línea y de rutas.
**R8.** Resumen de ejecución: `resumir(resultados, suite=None)` devuelve dict determinista (`total`, `pasaron`, `fallaron`, `no_disponibles`, `por_categoria`, `suite`) y `render_resumen(dict)` un texto humano estable. Sin leaderboard.

## C. Resultado versionado
**R9.** `storage.RESULT_SCHEMA_VERSION = 1`; `core.EVALUATOR_VERSION` (string). `save_run` escribe `schema_version`, `evaluator_version` y, si se pasa suite, `suite` = `{suite_id, suite_version, suite_hash}`. Firma retrocompatible (parámetros nuevos opcionales).
**R10.** `load_run`: `schema_version` ausente ⇒ se trata como 0 (legado); 0 y 1 soportados; mayor o inválido ⇒ `ValueError`.
**R11.** No se persisten secretos, chain-of-thought ni contexto privado: el excerpt sigue acotado y no se agrega el prompt completo.

## D. Veredicto baseline vs candidate
**R12.** `compare_runs` conserva su salida (`regressions`/`improvements`/`unchanged`/`solo_en_*`) y agrega `verdict` y `verdict_reason` a `ComparisonReport`. Valores: `candidate_better`, `baseline_better`, `equivalent`, `inconclusive`.
**R13.** Es `inconclusive` si: no hay escenarios comunes; hay `solo_en_baseline`/`solo_en_candidate`; algún resultado de cualquiera de las dos corridas tiene `ok=False` o `availability_error`; ambas declaran `suite` y difieren en `suite_id`/`suite_version`/`suite_hash`; solo una declara `suite`; ambas declaran `evaluator_version` y difieren, o solo una la declara (corrida legada); hay a la vez regresiones y mejoras.
**R14.** Si no aplica R13: solo regresiones ⇒ `baseline_better`; solo mejoras ⇒ `candidate_better`; ninguna ⇒ `equivalent`. La decisión usa únicamente `score.passed` determinista.
**R15.** `candidate_better` nunca se emite sin al menos una mejora medida por scorer determinista.

## E. CLI
**R16.** `run` acepta `--suite <manifest>` (excluyente con `--scenarios`; exactamente uno requerido) y guarda el bloque `suite`. `suite-check --suite <manifest> [--json]` valida el manifest (exit 0 válido, 1 inválido). `compare` imprime el veredicto y `--json` lo incluye. Exit codes existentes sin cambio.

## F. Suite pública
**R17.** `tools/harmessi_bench/suites/harmessi-core-synthetic.suite.json` y su archivo de casos con ≥ 8 casos que cubren framing, debugging, domain-modeling, codebase-design, recovery y contrato de herramientas; sintéticos, genéricos, sin datos, nombres, rutas ni vocabulario de negocio reales; `suite-check` los valida.

## G. Alcance y boundaries
**R18.** `core.py` y `runner.py` conservan su pureza (`test_v05_core_neutrality`); `suite.py` y `compare.py` no importan providers, `subprocess` ni red. `harmessi_bench` sigue solo-checkout.
**R19.** Nada en el paquete promueve, escribe ni modifica superficies del harness.
**R20.** Docs: `ARCHITECTURE.md` y `README.md` describen la extensión, `evals ≠ tests`, los niveles de evidencia y el boundary Protected/Optimizable.

## Criterios de aceptación
- [ ] R1–R4 caso versionado y boundary.
- [ ] R5–R8 suite.
- [ ] R9–R11 resultado.
- [ ] R12–R15 veredicto.
- [ ] R16 CLI.
- [ ] R17 suite pública.
- [ ] R18–R20 pureza, boundaries, docs.
- [ ] Tests focalizados de `tools/harmessi_bench`, neutralidad, manifest-completitud y smoke del Change verdes.

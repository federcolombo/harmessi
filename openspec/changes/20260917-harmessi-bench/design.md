# Diseño — 20260917-harmessi-bench

## Decisión metodológica/técnica
Reusar el contrato neutral de Change 0 (`tools/providers/core.py`: `ProviderAdapter`,
`InvocationRequest`, `InvocationResult`) sin duplicarlo — `harmessi-bench` arma un
`InvocationRequest` por escenario y delega la invocación real al adapter recibido, sin conocer el
vocabulario de flags de ningún proveedor concreto. Scoring determinista (`contains`/`regex`/
`exact`) en vez de LLM-as-judge: decisión explícita para v0.5 (costo real de una invocación
adicional por cada scoring + no-determinismo del juez, fuera de alcance de un framework mínimo);
queda como extensión futura candidata (v0.6+). Almacenamiento en
`.harmessi/evals/<run_id>/result.json`, mismo patrón que `ds_profile` → `.harmessi/profiles/`
(consistencia deliberada con el resto de artefactos que Harmessi escribe fuera del control de
versiones).

## Target (condicional — feature_engineering, modeling)
No aplica — no hay target de datos en este cambio.

## Features permitidas/prohibidas (condicional — feature_engineering)
No aplica — no hay features de datos en este cambio.

## Estrategia de split/validación (condicional — holdout involucrado, modeling, evaluation)
No aplica — no hay split de datos ni holdout de datos en este cambio.

## Leakage risks (condicional — feature_engineering, data_preparation, modeling)
No aplica en el sentido de anti-leakage de datos de `CLAUDE.md`. Riesgo análogo considerado: que un
scorer determinista dé una falsa sensación de "calidad medida" cuando en realidad solo mide
coincidencia superficial de texto (substring/regex/igualdad exacta), no comprensión semántica real
del output. Mitigado documentando explícitamente esa limitación acá y en `verification.md`, sin
presentarlo como una medición completa de calidad agentic.

## Reproducibilidad (opcional — solo si se desvía del default: RANDOM_STATE fijo, .venv)
No aplica `RANDOM_STATE` — no hay aleatoriedad propia del framework (el runner es determinista dado
el mismo escenario y el mismo output del target); la variabilidad, si existe, viene del proveedor
invocado, fuera del control de este Change.

## Alternativas descartadas
1. **Parametrizar evals dentro de pytest** (p. ej. `pytest.mark.parametrize` sobre escenarios).
   Descartado: el roadmap pide separación explícita de tests deterministas y evals de calidad
   agentic, y pytest no tolera bien el costo/latencia de invocaciones reales a un proveedor ni la
   comparación histórica entre corridas (no está pensado para eso).
2. **LLM-as-judge** (usar un segundo modelo para scorear la calidad del output). Descartado en este
   Change por costo (una invocación extra por cada scoring) y no-determinismo (el juez puede variar
   su veredicto entre corridas); candidato explícito para v0.6+.
3. **Leaderboard/dashboard propio**. Explícitamente fuera de alcance del roadmap v0.5 para este
   Change ("No diseñar todavía un leaderboard público complejo").

## Riesgos
1. Los scorers deterministas no capturan calidad semántica real, son proxies superficiales de
   coincidencia de texto — documentado explícitamente acá y en `verification.md`, no se presenta
   como medición completa de calidad.
2. El set de ejemplo bundleado (`scenarios/examples.json`) es demostrativo del framework, no una
   suite real de evaluación de Harmessi — cualquier uso serio de `harmessi-bench` (Change 2/3 en
   adelante) requiere que quien lo use escriba sus propios escenarios representativos de la tarea
   que quiere medir.
3. `cli.py` no tiene `__main__.py` propio en este Change (se invoca como `python -m
   tools.harmessi_bench.cli ...`, no `python -m tools.harmessi_bench ...`) — limitación aceptada,
   documentada en `verification.md`.

## Aprobación humana
Ver `proposal.md`, sección "Aprobación" (no se duplica acá).

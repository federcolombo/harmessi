# Diseño — 20260917-fallback-and-handoffs

## Decisión metodológica/técnica
Separar dos conceptos de "continuidad" distintos que el roadmap agrupa bajo un mismo Change pero
que no deben mezclarse en un mismo módulo (violaría separación de responsabilidades):

1. **Motor de fallback técnico** (`tools/fallback/core.py`): opera exclusivamente sobre
   `InvocationResult`/`availability_error` de una invocación de proveedor concreta. Ciclo de vida:
   una invocación.
2. **Contexto de handoff SDD** (`tools/fallback/handoff.py`): opera sobre metadata de
   Change/sesión (qué se hizo, qué falta, qué ya se auditó). Ciclo de vida: un Change o una sesión
   de trabajo.

La elegibilidad de fallback vive en una única función, `is_fallback_eligible`, que reusa
directamente los 3 valores ya definidos por `classify_availability_error` de Change 0 -- ninguna
heurística nueva, ninguna lista de causas inventada por este Change. Esta es la garantía
arquitectónica central: el motor de fallback nunca importa `tools.harmessi_bench` (scoring de
calidad) ni ningún módulo de `data-science-reviewer`, y esto es verificable por simple lectura del
archivo (sin ningún `import` de esos paquetes en `tools/fallback/core.py`).

## Target (condicional — feature_engineering, modeling)
No aplica.

## Features permitidas/prohibidas (condicional — feature_engineering)
No aplica.

## Estrategia de split/validación (condicional — holdout involucrado, modeling, evaluation)
No aplica.

## Leakage risks (condicional — feature_engineering, data_preparation, modeling)
No aplica en el sentido de datos de un proyecto DS. Riesgo análogo considerado explícitamente: que
alguien conecte en el futuro el scoring de `harmessi_bench` (calidad de output) como señal de
decisión de fallback -- mitigado con la separación estructural documentada arriba:
`tools/fallback/core.py` no importa `tools.harmessi_bench` en ningún lado, verificable por lectura
directa del archivo (y por el hecho de que `FallbackOutcome`/`HandoffRecord` no tienen ningún campo
de tipo `ScoreResult` ni equivalente).

## Reproducibilidad (opcional — solo si se desvía del default: RANDOM_STATE fijo, .venv)
No aplica -- este Change no introduce aleatoriedad; toda la lógica de `invoke_with_fallback` es
determinista dado el orden de la cadena y los resultados de cada `.invoke()`.

## Alternativas descartadas
1. **Permitir configurar causas de fallback adicionales vía policy** (p. ej. "fallback también si
   score bajo de harmessi-bench"). Descartado explícitamente: violaría la prohibición del roadmap
   de disparar fallback por mala calidad de output, y rompería la garantía de fuente única de
   verdad de elegibilidad (`is_fallback_eligible`).
2. **Mutar `RoutingDecision.provider_id` automáticamente cuando `provider_available=False`**
   (campo ya calculado por Change 2 en `resolve()`). Descartado: ese campo es solo informativo por
   diseño explícito de Change 2 (ver docstring de `resolve()`: "esta función NUNCA cambia
   `provider_id`... eso sería fallback automático, Change 3, fuera de alcance"); el fallback real
   vive exclusivamente en `invoke_with_fallback`, nunca en `resolve()`.
3. **Unificar `HandoffRecord` (técnico, por invocación) y `HandoffContext` (SDD, por Change/sesión)
   en una sola clase.** Descartado: representan conceptos con ciclos de vida y consumidores
   distintos (uno es un registro efímero de un intento de invocación, dentro de
   `FallbackOutcome`; el otro es un documento persistido para retomar trabajo entre sesiones) --
   forzarlos a una sola clase perdería precisión sin ganar nada.

## Riesgos
- La extensión de schema de Change 2 (`fallback_chain`), aunque aditiva, agrega superficie a un
  Change ya cerrado. Mitigación: se corre la suite completa de `tools/routing/tests` (11 tests
  preexistentes + 3 nuevos de este Change) para confirmar 0 regresiones antes de cerrar este
  Change (ver `tasks.md`, invocación del Lead).
- `fallback resolve-chain`/`fallback invoke` dependen de que los `provider_id` de la cadena estén
  registrados en `PROVIDER_REGISTRY`. Un typo en una política real haría que ese elemento de la
  cadena se reporte como `"no_registrado"` (o se salte silenciosamente en `invoke`) en vez de
  producir un error fuerte. Esto es una decisión deliberada para no crashear ante una cadena
  parcialmente mal configurada (permite que el resto de la cadena siga siendo útil), documentada
  acá como limitación conocida, no como comportamiento a "arreglar" sin discusión.

## Aprobación humana
Ver `proposal.md`, sección "Aprobación" (registro único por Change, no se duplica acá).

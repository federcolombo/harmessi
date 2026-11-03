# Diseño — 20260917-provider-routing

## Decisión metodológica/técnica
El routing es puramente declarativo y determinista: resuelve una regla ya
escrita por un humano, nunca infiere, optimiza ni inventa una preferencia de
proveedor/modelo. Se separa en dos módulos con responsabilidades distintas:

- `tools/routing/core.py`: `resolve()` resuelve `RoutingPolicy` →
  `RoutingDecision` sin ningún efecto secundario (no lee disco, no importa
  `tools.providers`). Es testeable sin ninguna CLI real y sin acoplar
  "decidir" con "detectar disponibilidad".
- `tools/routing/policy.py`: carga y valida `RoutingPolicy` desde
  `.harmessi/routing.json` (opcional, ausente = sin política declarada,
  nunca heurística -- mismo criterio que `.harmessi/scientific-policy.json`
  documentado en `README.md`).

La composición "resolver + chequear disponibilidad real" la hace el CLI
(`tools/harmessi/cli.py`, subcomando `routing resolve --check-availability`),
no `core.py`: ahí es donde se importa `tools.providers.list_providers()`
(import diferido), nunca dentro del módulo neutral de resolución.

## Target (condicional — feature_engineering, modeling)
No aplica.

## Features permitidas/prohibidas (condicional — feature_engineering)
No aplica.

## Estrategia de split/validación (condicional — holdout involucrado, modeling, evaluation)
No aplica.

## Leakage risks (condicional — feature_engineering, data_preparation, modeling)
No aplica -- este cambio no toca ningún dataset ni feature de un proyecto
de ciencia de datos.

## Reproducibilidad (opcional — solo si se desvía del default: RANDOM_STATE fijo, .venv)
No aplica -- `resolve()` es una función pura sin ningún componente
aleatorio; no hay `RANDOM_STATE` que fijar.

## Alternativas descartadas
1. **Routing automático basado en costos/latencia observados**: descartado
   explícitamente por el roadmap -- los costos/tokens no son observables de
   forma confiable hoy, y el roadmap prohíbe inventar una optimización
   automática sobre esa base.
2. **Que `resolve()` mute `provider_id` a un fallback cuando el matcheado
   no está disponible**: descartado porque eso es fallback automático,
   scope explícito de Change 3 del roadmap. Mezclar ambas
   responsabilidades en este Change violaría la secuencia deliberada
   `adapters → evals → routing → fallback`. `resolve()` solo informa
   `provider_available`, nunca actúa sobre esa información.
3. **Inferir routing por heurística de nombre de rol** (p. ej. "si el rol
   contiene 'reviewer', usar tal provider"): descartado -- todo debe ser
   explícito y trazable, de ahí que `reason` sea un campo obligatorio sin
   default en `RoutingRule`.

## Riesgos
- Sin una segunda familia de modelo/provider real disponible en este
  entorno (solo `claude_code` verificado como disponible, ver Change 0/1),
  no se puede verificar de punta a punta la recomendación del roadmap de
  "reviewer de familia de modelo distinta" -- documentado como limitación
  explícita en `verification.md`, no se finge una garantía de diversidad de
  revisión que hoy no existe.
- El desempate "primera regla en orden de lista" (para reglas del mismo
  rol+task_type exacto) puede sorprender a quien escribe una política con
  reglas ambiguas o duplicadas -- mitigado documentándolo con precisión en
  el docstring de `resolve()` y en `spec.md` (criterios de aceptación con
  test explícito).
- `RoutingPolicy`/`RoutingRule` no validan que `provider_id` corresponda a
  un provider realmente registrado en `tools.providers` -- deliberado
  (`core.py` no importa `tools.providers`); esa verificación queda a cargo
  de quien use `--check-availability` en el CLI, o de la fase de fallback
  (Change 3).

## Aprobación humana
El registro de aprobación (usuario, fecha, alcance, versión de artefactos,
cita) es único por cambio y vive en la sección "Aprobación" de
`proposal.md` -- no se duplica acá.

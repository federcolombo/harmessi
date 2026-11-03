# Spec — 20260917-provider-routing

## Requisitos

- **R1 — Tipos de `tools/routing/core.py`**: `RoutingRule` (`role`,
  `task_type="*"`, `provider_id`, `model=None`, `effort=None`, `reason`
  obligatorio sin default), `RoutingPolicy` (`rules: List[RoutingRule]`,
  `default: Optional[RoutingRule] = None`), `RoutingDecision` (`role`,
  `task_type`, `provider_id`, `model`, `effort`, `matched`, `rule_source`
  ∈ `{"regla_explicita", "default", "sin_regla"}`, `reason`,
  `provider_available: Optional[bool]`). `core.py` no importa
  `tools.providers` ni ningún proveedor concreto -- solo `stdlib`.

- **R2 — `resolve()`**: dada una `RoutingPolicy`, `role`, `task_type` y,
  opcionalmente, `available_providers: Optional[Set[str]]`, decide una
  `RoutingDecision` de forma determinista:
  1. Filtra reglas por `role` exacto.
  2. Entre las que matchean el rol, prefiere `task_type` exacto sobre
     comodín (`"*"`).
  3. Ante empate de especificidad para el mismo rol+task_type, gana la
     PRIMERA regla en el orden de `policy.rules` (orden estable,
     documentado en el docstring de `resolve()`).
  4. Si matchea: `matched=True`, `rule_source="regla_explicita"`.
  5. Si no matchea pero hay `policy.default`: `matched=True`,
     `rule_source="default"`.
  6. Si no matchea nada y no hay `default`: `matched=False`,
     `rule_source="sin_regla"`, `provider_id/model/effort=None`, `reason`
     explica explícitamente por qué (rol/task_type pedidos y ausencia de
     default), `provider_available=None`.
  7. Si se pasó `available_providers` y la decisión tiene `provider_id`
     no-`None`: `provider_available = provider_id in available_providers`.
     `resolve()` NUNCA cambia `provider_id` a otro valor -- solo informa.

- **R3 — `tools/routing/policy.py`**: `DEFAULT_POLICY_PATH =
  Path(".harmessi/routing.json")`. `load_policy(path=None)`: si el archivo
  resuelto no existe, devuelve `RoutingPolicy(rules=[], default=None)` sin
  levantar (comportamiento legítimo de "sin política declarada", nunca
  inferido por heurística, mismo criterio que
  `.harmessi/scientific-policy.json`). Si existe, parsea JSON con forma
  `{"rules": [...], "default": {...} | null}` y valida fail-closed: cada
  regla (y `default` si no es `null`) debe tener `role`/`provider_id`/
  `reason` no vacíos, si no `raise ValueError` citando el índice de la
  regla problemática.

- **R4 — `tools/routing/examples/policy.example.json`**: ejemplo ilustrativo
  de 3 reglas (writer, reviewer, metodólogo) con `"default": null` y un
  campo `"_nota"` aclarando que es un ejemplo, no la política real de este
  repo (que no declara ninguna).

- **R5 — Wiring en `tools/harmessi/cli.py`**: subcomando `routing` con
  `show` (`--policy`, `--json`) y `resolve` (`--role`, `--task-type`,
  `--policy`, `--check-availability`, `--json`), imports diferidos de
  `tools.routing`/`tools.providers` dentro de las funciones, nunca
  traceback crudo ante error de política inválida (exit 1 + mensaje claro
  a stderr), y `matched=False` es una respuesta válida (exit 0).

- **R6 — Tests deterministas** para `core.py`, `policy.py` y el subcomando
  CLI, sin invocar ningún proveedor real.

## Criterios de aceptación

**R1/R2 — desempate y ausencia de política**
- Given una `RoutingPolicy` con una regla `role="writer", task_type="*"` y
  otra `role="writer", task_type="feature_engineering"`, When se llama
  `resolve(policy, role="writer", task_type="feature_engineering")`, Then
  la decisión usa la regla de `task_type` exacto (`rule_source=
  "regla_explicita"`, `reason` de esa regla, no de la comodín).
- Given una `RoutingPolicy` sin reglas para `role="metodologo"` pero con
  `default` declarado, When se llama `resolve(policy, role="metodologo",
  task_type="cualquiera")`, Then `matched=True`, `rule_source="default"`.
- Given una `RoutingPolicy` sin reglas ni `default` para un rol pedido,
  When se llama `resolve(...)`, Then `matched=False`,
  `rule_source="sin_regla"`, `provider_id/model/effort=None`, y `reason`
  cita explícitamente el `role`/`task_type` pedidos y la ausencia de
  default.
- Given dos reglas con el mismo `role` y el mismo `task_type` exacto, When
  se llama `resolve(...)`, Then gana la primera en el orden de
  `policy.rules` (test explícito de esta regla de desempate).

**R2 — `provider_available` informativo, sin swap automático**
- Given una decisión matcheada con `provider_id="codex"` y
  `available_providers={"claude_code"}`, When se llama `resolve(...,
  available_providers=available_providers)`, Then
  `provider_available=False` y `provider_id` sigue siendo `"codex"` (nunca
  cambia a `"claude_code"` ni a ningún otro valor).
- Given la misma decisión sin pasar `available_providers`, Then
  `provider_available is None`.

**R3 — carga de política**
- Given una ruta a un archivo `.harmessi/routing.json` inexistente, When se
  llama `load_policy(path)`, Then devuelve `RoutingPolicy(rules=[],
  default=None)` sin levantar ninguna excepción.
- Given `tools/routing/examples/policy.example.json` real, When se llama
  `load_policy(path)`, Then devuelve una `RoutingPolicy` con exactamente 3
  reglas y `default=None`.
- Given un JSON fabricado con una regla en el índice 1 sin campo `reason`
  (o `reason=""`), When se llama `load_policy(path)`, Then levanta
  `ValueError` citando el índice `1`.

**R5 — CLI sin traceback**
- Given `routing show --policy <ruta-inexistente>`, When se ejecuta, Then
  imprime un mensaje explícito de "sin política de routing declarada en
  <ruta>" (no un JSON vacío sin contexto) y exit code 0.
- Given `routing show --policy <policy.example.json real> --json`, When se
  ejecuta, Then imprime JSON con exactamente 3 reglas.
- Given `routing resolve --role writer --policy <policy.example.json>
  --json`, When se ejecuta, Then imprime una decisión con
  `provider_id="claude_code"` y exit code 0.
- Given `routing resolve --role inexistente --policy <policy.example.json>
  --json`, When se ejecuta, Then imprime `"matched": false` y exit code 0
  (una decisión "no sé" no es un error de proceso).
- Given `routing resolve --policy <ruta a JSON corrupto>`, When se ejecuta,
  Then exit code 1 y un mensaje claro en stderr (nunca un traceback
  crudo).

## Unidad de análisis / grain (condicional — data_understanding, feature_engineering, modeling)
No aplica -- infraestructura de configuración del harness, no un dataset de
un proyecto DS.

## Cutoff / information boundary (condicional — feature_engineering, data_preparation, modeling)
No aplica.

## Baseline (condicional — modeling)
No aplica.

## Métrica primaria (condicional — modeling, evaluation)
No aplica.

## Métricas secundarias (opcional)
No aplica.

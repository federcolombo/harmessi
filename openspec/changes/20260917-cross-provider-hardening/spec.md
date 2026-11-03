# Spec — 20260917-cross-provider-hardening

## Requisitos

### R1 — Neutralidad estructural del core (`tools/tests/test_v05_core_neutrality.py`)

El core de v0.5 (`tools/providers/core.py`, `tools/routing/core.py`, `tools/fallback/core.py`,
`tools/harmessi_bench/core.py`) no debe tener ninguna dependencia de import ni de texto literal
acoplada a un proveedor concreto o a un módulo de medición de calidad, para que agregar/quitar un
proveedor, o correr en un entorno donde ningún adapter está instalado, nunca rompa al core.

**Given** los 4 archivos `core.py` de v0.5 listados arriba
**When** se escanean sus imports de nivel de módulo vía `ast` (mismo patrón que
`tools/tests/test_architecture_boundaries.py::_imports_nivel_modulo`)
**Then** ninguno importa `tools.providers.claude_code`, `tools.providers.codex`,
`tools.providers.gemini` ni `tools.providers.grok`.

**Given** los mismos 4 archivos
**When** se escanean sus imports de nivel de módulo
**Then** ninguno importa `subprocess` -- incluido `tools/providers/core.py`, que es el contrato
neutral de invocación y no debería necesitarlo (`subprocess` vive únicamente en los 4 adapters
concretos: `claude_code.py`, `codex.py`, `gemini.py`, `grok.py`).

**Given** `tools/routing/core.py` y `tools/fallback/core.py`
**When** se escanean sus imports de nivel de módulo
**Then** ninguno importa `tools.harmessi_bench` (separación "decidir/reintentar" vs "medir
calidad", ya confirmada en revisión de Change 3, ahora permanente y automática).

**Given** los 4 archivos `core.py`
**When** se escanea el código fuente buscando cualquier literal de string (`ast.Constant` de tipo
`str`) que contenga `"claude"` (case-insensitive) en código real -- es decir, fuera de docstrings --
sin distinguir el contexto de uso (comparación, argumento de llamada, valor por default, mensaje de
error, etc.: la implementación (`_literales_claude` en `test_v05_core_neutrality.py`) marca
CUALQUIER literal de este tipo, deliberadamente más estricta que un análisis sensible a contexto,
para priorizar no dejar pasar un acoplamiento real (falso positivo aceptable, falso negativo no)
**Then** no aparece ninguna ocurrencia -- el core no puede reconocer ni tratar especialmente al
proveedor `claude_code` por su nombre.

### R2 — Contrato paramétrico de los 4 adapters (`tools/providers/tests/test_contract_parity.py`)

Los 4 adapters concretos (`ClaudeCodeAdapter`, `CodexAdapter`, `GeminiAdapter`, `GrokAdapter`)
deben cumplir el mismo contrato de interfaz y el mismo comportamiento de degradación ante ausencia
de CLI, sin excepción para ninguno -- incluido `claude_code`, cerrando la asimetría de cobertura
que `test_adapters.py` (Change 0) dejó documentada como limitación menor.

**Given** cada una de las 4 clases de adapter, parametrizadas
**When** se instancian
**Then** cada instancia es `isinstance` de `ProviderAdapter`; `provider_id`, `cli_command` y
`display_name` no están vacíos.

**Given** las 4 instancias juntas
**When** se comparan sus `provider_id` entre sí
**Then** los 4 son distintos (ningún duplicado accidental).

**Given** cada uno de los 4 adapters, con `shutil.which` forzado (vía `monkeypatch`) a devolver
`None` sin importar el argumento
**When** se llama `.detect()`
**Then** devuelve `available=False`, `detail` no vacío, sin lanzar excepción -- para los 4 por
igual.

**Given** el mismo forzado de `shutil.which`
**When** se llama `.invoke()` con una `InvocationRequest` trivial (`prompt="hola"`, `role="lead"`)
**Then** devuelve `ok=False`, `availability_error="unavailable"`, `exit_code=127`, sin lanzar
excepción -- para los 4 por igual, incluido `claude_code` (que en Change 0 solo tenía este test
para los otros 3).

**Given** `tools.providers.list_providers()` sin mockear el registry (usa el
`PROVIDER_REGISTRY` real de `tools.providers`)
**When** se llama
**Then** devuelve exactamente 4 `ProviderInfo`, uno por cada `provider_id` único registrado.

### R3 — Paridad de fallback entre providers (`tools/fallback/tests/test_cross_provider_parity.py`)

El motor `invoke_with_fallback` debe tratar a los 4 `provider_id` reales de forma idéntica: no debe
existir ninguna rama condicional en `tools/fallback/core.py` que trate a `"claude_code"` (ni a
ningún otro `provider_id`) de forma especial.

**Given** `FakeAdapter`s con `provider_id` igual a cada uno de los 4 reales
(`claude_code`/`codex`/`gemini`/`grok`), parametrizado, como único elemento de la cadena y
configurado para responder `ok=True`
**When** se llama `invoke_with_fallback`
**Then** el resultado es idéntico en estructura para los 4 (mismo `final_provider_id` que el
adapter, `exhausted=False`, `blocked_reason=None`, un solo `HandoffRecord` con
`reason="intento primario"`).

**Given**, para cada uno de los 4 `provider_id` reales como primario (parametrizado), un primario
que falla con `availability_error="unavailable"` y un segundo adapter (con un `provider_id`
distinto de los 4) que responde `ok=True`
**When** se llama `invoke_with_fallback`
**Then** el resultado es idéntico en estructura para los 4 casos (2 `HandoffRecord`s,
`final_provider_id` es el del segundo adapter, `exhausted=False`) -- el comportamiento de fallback
no depende de cuál de los 4 sea el que falla.

**Given** el código fuente de `tools/fallback/core.py`
**When** se inspecciona por lectura/`grep`
**Then** no contiene ninguna condición `if ... provider_id == "claude_code"` (ni comparación
equivalente contra cualquiera de los otros 3 `provider_id` reales) -- confirmado también por un
test explícito que falla si aparece el string literal de alguno de los 4 `provider_id` reales
usado en una comparación dentro del archivo.

**Given** una `InvocationRequest` con `role` en `"writer"`, `"reviewer"`, `"metodologo"`
(parametrizado) y una cadena de un solo `FakeAdapter` exitoso que registra el `request` recibido
**When** se llama `invoke_with_fallback`
**Then** el `role` llega sin modificar al `adapter.invoke()` y el resultado (`FallbackOutcome`) no
varía su forma según el valor de `role` -- el motor de fallback es opaco a `role`, solo lo
reenvía.

### R4 — Paridad de routing entre providers (`tools/routing/tests/test_cross_provider_parity.py`)

`resolve()` debe tratar a los 4 `provider_id` reales de forma idéntica: la lógica de matching es
puramente sobre `role`/`task_type`, nunca sobre el valor de `provider_id`.

**Given** una `RoutingPolicy` con una `RoutingRule` por cada uno de los 4 `provider_id` reales
para el mismo `role`, cada una con un `task_type` distinto y explícito (sin comodín)
**When** se llama `resolve()` con cada combinación `role`/`task_type` (parametrizado)
**Then** cada llamada devuelve `matched=True`, `rule_source="regla_explicita"` y el `provider_id`
de la regla correspondiente -- ninguno de los 4 recibe trato especial en el desempate frente a los
otros 3 (mismo resultado estructural para los 4, solo cambia el `provider_id`/`task_type`
esperado).

**Given** el código fuente de `tools/routing/core.py`
**When** se inspecciona por lectura/`grep` y con un test explícito
**Then** la función `resolve()` no contiene el string literal `"claude"` (ni ningún otro
`provider_id` real hardcodeado) en su lógica de comparación -- solo compara `regla.role`,
`regla.task_type`, `task_type` y `role` (parámetros opacos), nunca `provider_id` contra un valor
fijo.

## Criterios de aceptación

- [ ] `tools/tests/test_v05_core_neutrality.py` implementa las 4 verificaciones de R1 y pasa.
- [ ] `tools/providers/tests/test_contract_parity.py` implementa las verificaciones de R2,
      parametrizadas sobre los 4 adapters reales de `PROVIDER_REGISTRY`, y pasa sin invocar
      ninguna CLI real.
- [ ] `tools/fallback/tests/test_cross_provider_parity.py` implementa las verificaciones de R3,
      parametrizadas sobre los 4 `provider_id` reales con `FakeAdapter`s, y pasa.
- [ ] `tools/routing/tests/test_cross_provider_parity.py` implementa las verificaciones de R4 y
      pasa.
- [ ] Ninguno de los 4 archivos invoca una CLI de proveedor real (`subprocess.run` real hacia
      `claude`/`codex`/`gemini`/`grok`) -- todo con `FakeAdapter`s o `monkeypatch`.
- [ ] Regresión completa de `tools/providers/tests`, `tools/routing/tests`, `tools/fallback/tests`
      sigue en verde tras agregar estos 4 archivos (a cargo del Lead, no de esta invocación).

## Unidad de análisis / grain (condicional — data_understanding, feature_engineering, modeling)

No aplica.

## Cutoff / information boundary (condicional — feature_engineering, data_preparation, modeling)

No aplica.

## Baseline (condicional — modeling)

No aplica -- verificación estructural del harness, no dataset/modelo de un proyecto DS.

## Métrica primaria (condicional — modeling, evaluation)

No aplica -- criterio binario pass/fail de las 4 suites de test nuevas, no una métrica de
performance de modelo.

## Métricas secundarias (opcional)

No aplica.

# Spec — 20260917-fallback-and-handoffs

## Requisitos

- **R1 — Elegibilidad de fallback única y centralizada.** Debe existir una única función,
  `tools.fallback.core.is_fallback_eligible(availability_error)`, que decida si un
  `availability_error` habilita un intento de fallback. Reusa exactamente los 3 valores definidos
  por `tools.providers.core.classify_availability_error` (Change 0): `"quota"`, `"unavailable"`,
  `"unauthenticated"`. Ningún otro punto del código decide elegibilidad por su cuenta.

- **R2 — El motor de fallback NUNCA se activa por error no elegible.** `invoke_with_fallback` debe
  cortar la cadena inmediatamente ante un `InvocationResult` con `ok=False` y
  `availability_error=None` (o cualquier valor no elegible), sin invocar al siguiente proveedor de
  la cadena, y sin perder el resultado real del error (accesible vía `FallbackOutcome.final_result`).

- **R3 — Cadena de fallback ordenada y agotable.** `invoke_with_fallback` recibe una lista ordenada
  de `ProviderAdapter`s y los prueba en orden ante fallos elegibles; si todos fallan de forma
  elegible, reporta `exhausted=True` sin lanzar excepción; si la cadena está vacía, reporta
  `exhausted=True` con un `blocked_reason` explícito, sin lanzar excepción.

- **R4 — Trazabilidad de cada intento.** Cada intento (exitoso o no) queda registrado en un
  `HandoffRecord` dentro de `FallbackOutcome.handoffs`, en orden, incluyendo el motivo (intento
  primario o razón del fallback anterior).

- **R5 — Extensión aditiva de `RoutingRule`/`RoutingDecision` (Change 2).** El campo nuevo
  `fallback_chain: List[str]` tiene default `[]` en ambas dataclasses. Cualquier `RoutingRule`
  construida sin ese argumento (código o `routing.json` preexistente) sigue funcionando
  exactamente igual que antes de este Change; los 11 tests preexistentes de
  `tools/routing/tests` siguen pasando sin modificación.

- **R6 — Propagación del campo en `resolve()`.** Cuando `resolve()` encuentra una regla ganadora,
  `RoutingDecision.fallback_chain` se puebla con la `fallback_chain` de esa regla. Cuando no hay
  regla ganadora (`matched=False`), `fallback_chain` queda en `[]` (default).

- **R7 — Validación fail-closed de `fallback_chain` en `policy.py`.** Si `fallback_chain` está
  presente en el JSON crudo de una regla pero no es una lista, `load_policy` lanza `ValueError`
  citando la etiqueta de la regla (mismo patrón que las demás validaciones de `_construir_regla`).
  Si está ausente, se asume `[]` sin error.

- **R8 — `HandoffContext` de continuidad SDD falla cerrado.** `build_handoff_context` rechaza
  (`ValueError`) `change_id`, `role` o `reason` vacíos. `save_handoff`/`load_handoff` persisten y
  recuperan el contexto en `.harmessi/handoffs/<change_id>-<timestamp>/handoff.json`; `load_handoff`
  de una ruta inexistente lanza `FileNotFoundError` claro.

- **R9 — Wiring de CLI puramente informativo para `resolve-chain`, real para `invoke`.**
  `harmessi fallback resolve-chain` nunca invoca ningún proveedor (solo `resolve()` + `.detect()`).
  `harmessi fallback invoke` sí invoca de verdad, vía `invoke_with_fallback`, y nunca crashea ante
  un `provider_id` de la cadena no registrado en `PROVIDER_REGISTRY` (lo salta y lo reporta).

## Criterios de aceptación

- **R1**: Given `availability_error` en `{"quota", "unavailable", "unauthenticated"}`, When se
  llama `is_fallback_eligible`, Then devuelve `True`. Given `availability_error is None` o un
  string arbitrario no reconocido, When se llama `is_fallback_eligible`, Then devuelve `False`.

- **R2** (caso más crítico del Change): Given una cadena de 2 adapters donde el primero devuelve
  `InvocationResult(ok=False, availability_error=None, ...)` (error semántico/de código simulado),
  When se llama `invoke_with_fallback`, Then el segundo adapter de la cadena NUNCA es invocado
  (verificable contando llamadas a `.invoke()` de un spy/mock), `FallbackOutcome.blocked_reason`
  queda seteado explicando que el error no es elegible, y `final_result` conserva el
  `InvocationResult` real del primer adapter para que el llamador pueda inspeccionar el error.

- **R3**: Given una cadena de 1 adapter exitoso, When se invoca, Then `final_provider_id` queda
  seteado, `exhausted=False`, 1 `HandoffRecord`. Given una cadena de 2 adapters ambos con fallo
  elegible, When se invoca, Then `exhausted=True`, `final_provider_id is None`,
  `final_result` es el resultado del último intento. Given una cadena vacía, When se invoca,
  Then `exhausted=True`, `blocked_reason` menciona la cadena vacía, sin excepción.

- **R4**: Given una cadena de 2 adapters, el primero falla con `"unavailable"`, el segundo tiene
  éxito, When se invoca, Then `FallbackOutcome.handoffs` tiene 2 registros en orden, el primero con
  `reason="intento primario"` y el segundo citando `"unavailable"` y el `provider_id` del primero.

- **R5**: Given una `RoutingRule` construida sin pasar `fallback_chain`, When se inspecciona,
  Then `regla.fallback_chain == []`. Given los 11 tests preexistentes de `tools/routing/tests`
  (sin modificar), When se corren junto a los nuevos, Then siguen pasando sin cambios.

- **R6**: Given una regla con `fallback_chain=["codex", "gemini"]` que matchea `resolve()`, When
  se resuelve, Then `decision.fallback_chain == ["codex", "gemini"]`. Given ninguna regla matchea
  y no hay `default`, When se resuelve, Then `decision.fallback_chain == []`.

- **R7**: Given una regla JSON con `"fallback_chain": ["codex"]`, When se carga con `load_policy`,
  Then `RoutingRule.fallback_chain == ["codex"]`. Given una regla JSON con
  `"fallback_chain": "no_es_lista"`, When se carga, Then `load_policy` lanza `ValueError` citando
  la etiqueta de la regla.

- **R8**: Given `change_id=""` (o `role=""`, o `reason=""`), When se llama
  `build_handoff_context`, Then lanza `ValueError`. Given un `HandoffContext` válido guardado con
  `save_handoff` en un directorio temporal, When se recupera con `load_handoff` sobre la ruta
  devuelta, Then el contenido recuperado coincide con el guardado. Given una ruta inexistente,
  When se llama `load_handoff`, Then lanza `FileNotFoundError`.

- **R9**: Given la regla `writer` de `policy.example.json` (con `fallback_chain=["codex"]`), When
  se corre `harmessi fallback resolve-chain --role writer`, Then la cadena reportada es
  `["claude_code", "codex"]` con disponibilidad detectada para cada uno, sin invocar nada. Given un
  rol sin ninguna regla y sin `fallback_chain`, When se corre `harmessi fallback invoke`, Then
  sale con código 1 y mensaje claro en stderr, sin invocar ningún proveedor.

## Unidad de análisis / grain (condicional — data_understanding, feature_engineering, modeling)
No aplica — infraestructura del harness, no dataset/modelo de un proyecto DS.

## Cutoff / information boundary (condicional — feature_engineering, data_preparation, modeling)
No aplica — infraestructura del harness, no dataset/modelo de un proyecto DS.

## Baseline (condicional — modeling)
No aplica — infraestructura del harness, no dataset/modelo de un proyecto DS.

## Métrica primaria (condicional — modeling, evaluation)
No aplica — infraestructura del harness, no dataset/modelo de un proyecto DS.

## Métricas secundarias (opcional)
No aplica.

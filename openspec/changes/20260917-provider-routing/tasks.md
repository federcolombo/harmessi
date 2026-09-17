# Tareas — 20260917-provider-routing

estado: cerrada

## Invocaciones planificadas
1. `python-data-engineer` (esta sesión) -- completa los 4 artefactos SDD y
   declara el alcance real en `control.json` desde el arranque; implementa
   `tools/routing/` completo (core, policy, examples, tests) y el wiring en
   `tools/harmessi/cli.py` (`routing show`/`routing resolve`) + tests del
   subcomando + actualización de `ARCHITECTURE.md` §2.1.
2. Lead -- corre la suite de tests nueva (`tools/routing/tests/`,
   `tools/harmessi/tests/test_routing_cli.py`) + smoke real de
   `harmessi routing resolve`/`harmessi routing show` usando el
   `policy.example.json` bundleado. No hace falta invocar ninguna CLI de
   proveedor real -- este Change es puramente de resolución declarativa, no
   invoca nada; el flag `--check-availability` sí llamaría a
   `tools.providers.list_providers()`, que internamente detecta con
   `--version` sin costo real, así que puede probarse sin reparo.
3. `data-science-reviewer` -- revisa el diff completo (SDD +
   implementación).
4. `python-data-engineer` -- aplica fixes si hay hallazgos de la revisión y
   escribe `verification.md`.
5. `python-data-engineer` (esta sesión) -- escribe `verification.md` con la
   evidencia real ya obtenida por el Lead (ver `verification.md`).

## Tareas
- [x] `tools/routing/core.py`: `RoutingRule`, `RoutingPolicy`,
      `RoutingDecision`, `resolve()`.
- [x] `tools/routing/policy.py`: `DEFAULT_POLICY_PATH`, `load_policy()`.
- [x] `tools/routing/examples/policy.example.json`: ejemplo de 3 reglas
      (writer, reviewer, metodólogo) + `_nota`.
- [x] `tools/routing/__init__.py`: reexports mínimos.
- [x] `tools/routing/tests/__init__.py`, `test_core.py`, `test_policy.py`.
- [x] Wiring `tools/harmessi/cli.py`: subcomando `routing` (`show`,
      `resolve`), imports diferidos.
- [x] `tools/harmessi/tests/test_routing_cli.py`.
- [x] `ARCHITECTURE.md` §2.1: fila nueva para `tools/routing/core.py`.
- [x] `verification.md` (paso 4, después de la revisión).

## Dependencias
Reusa tipos de `tools.providers.core` (`ProviderInfo`) y la función
`tools.providers.list_providers` (Change 0) desde el CLI únicamente
(import diferido); no los modifica. No depende de `tools.harmessi_bench`
(Change 1).

## Próximo paso exacto
No aplica (estado: propuesta_pendiente, no pausada_bloqueada).

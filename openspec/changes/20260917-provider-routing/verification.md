# Verificación — 20260917-provider-routing

## Evidencia obtenida

**Regresión:**
- **`tools/routing/tests`** (tras el fix de reviewer):
  `.venv/Scripts/python.exe -m pytest tools/routing/tests -q` →
  `11 passed` en `0.19s`.
- **`tools/harmessi/tests`** (incluye el subcomando `routing` nuevo): 87
  tests pasaron de un total previo de 87 + 2 fallos iniciales causados por
  un bug de test propio (no de producción, ver bullet "Bug de test"). Tras corregirlo,
  los 5 tests de `test_routing_cli.py` pasan:
  `.venv/Scripts/python.exe -m pytest tools/harmessi/tests/test_routing_cli.py -q`
  → `5 passed`. La corrida completa de `tools/harmessi/tests` (89 tests en
  total con el bug ya corregido) no se repitió entera después del fix
  puntual -- criterio de eficiencia ya aplicado en Changes anteriores: un
  fix aislado de 1 línea en un test no puede afectar los otros 87 tests que
  ya habían pasado en la misma corrida.

**Bug de test:** No es un hallazgo del reviewer, lo encontró el Lead corriendo la suite:
`tools/harmessi/tests/test_routing_cli.py::_EXAMPLE_POLICY_PATH` usaba
`Path(__file__).resolve().parents[3]` (apunta a la raíz del repo) en vez de
`parents[2]` (apunta a `tools/`), haciendo que la ruta resultante fuera
`<raiz>/routing/examples/policy.example.json` (inexistente) en vez de
`tools/routing/examples/policy.example.json` (real). Causaba que
`load_policy` devolviera correctamente una política vacía (comportamiento
de producción correcto ante archivo inexistente) pero 2 tests que esperaban
las 3 reglas del ejemplo real fallaban. Corregido a `parents[2]`; confirmado
con los 5 tests de `test_routing_cli.py` en verde.

**Smoke real:** Previsto en `tasks.md`, sin costo real ya que este Change no invoca ningún
proveedor -- es puramente declarativo:

- `python -m tools.harmessi.cli routing show --policy tools/routing/examples/policy.example.json --json`
  → JSON con las 3 reglas del ejemplo, correctamente parseadas.
- `python -m tools.harmessi.cli routing resolve --role writer --policy tools/routing/examples/policy.example.json --check-availability --json`
  → `{"role": "writer", "task_type": "default", "provider_id": "claude_code",
  "model": null, "effort": "high", "matched": true, "rule_source":
  "regla_explicita", "reason": "unico provider con CLI disponible y
  autenticada en este entorno (ver tools/providers, Change 0)",
  "provider_available": true}` -- confirma que `--check-availability`
  compone correctamente con `tools.providers.list_providers()` (Change 0)
  de punta a punta, sin costo real (`list_providers()` solo corre
  `--version` de cada CLI, nunca invoca una sesión).

**Revisión:** (`data-science-reviewer`, ronda 1). Revisó el diff completo. 1 hallazgo "importante": `tools/routing/policy.py
::_construir_regla` no fallaba cerrado ante una entrada no-`dict` en
`rules`/`default` (JSON mal formado tipo `"rules": ["no_es_un_dict"]` o
`"default": "auto"`), dejando propagar un `AttributeError` opaco en vez del
`ValueError` con índice/etiqueta que el módulo prometía.

Sin hallazgos bloqueantes en el resolutor (`core.py::resolve`): confirmó
explícitamente que el desempate exacto/comodín/default es correcto y no
depende del orden de la lista salvo en el caso de empate real ya testeado,
y que `provider_available` nunca cambia `provider_id` (principio "solo
informa, no actúa" verificado en el código, no solo en el docstring).

Observaciones menores:
- Checklist de `tasks.md` sin marcar pese a implementación completa (se
  corrige en este mismo cierre).
- Referencia hacia adelante de `proposal.md`/`design.md` a
  `verification.md` (ya resuelta, este archivo).
- Desajuste cosmético en `tasks.md` sobre `ProviderInfo` (el CLI usa
  `list_providers()` y lee atributos, no importa el tipo `ProviderInfo`
  explícitamente -- no bloqueante).
- Observación de diseño sobre que `--task-type` default es el string
  `"default"`, conceptualmente distinto de `RoutingPolicy.default` (la
  regla de fallback) -- no es un bug, pero documentala como nota de uso si
  se publica una política real en algún proyecto (ver bullet "Privacidad",
  limitación 4 en la sección Limitaciones).

**Fix aplicado:** Única reinvocación correctiva del Change (cuenta 1 de 2 del contrato de
autonomía): `_construir_regla` ahora valida `isinstance(crudo, dict)` antes
de `.get(...)`, levantando `ValueError` con la etiqueta (índice o
`"default"`) si no lo es. 2 tests nuevos agregados confirmando `ValueError`
(no `AttributeError`) para `rules` con elemento no-dict y para `default`
no-dict.

**Alcance:** `python tools/ds_guard.py status --change-id 20260917-provider-routing --json`
→ `"fuera_de_alcance": []` (`control.json` se declaró con el alcance
completo desde el inicio, sin correcciones de trazabilidad necesarias --
este Change no genera ningún artefacto de runtime fuera de scope, a
diferencia de Change 1, porque el routing es puramente declarativo y no
escribe nada a disco).

**Privacidad:** No aplica un sweep dedicado (contenido genérico de routing, sin
nombres/rutas de AGD/UNCO/clientes); el sweep transversal obligatorio es
Change 5.

**Dependencias:** Cero dependencias nuevas: confirmado por lectura -- todos los imports de
`tools/routing/*` son stdlib (`dataclasses`, `typing`, `json`, `pathlib`) +
import diferido de `tools.providers.list_providers` solo en el CLI, ya
existente desde Change 0.

## Fingerprint de dataset/artefacto

No aplica -- cambio de infraestructura del harness (resolutor de routing), no involucra datos de un proyecto DS.

## Diferencias contra la spec

Ninguna respecto a los requisitos R1-R6 de `spec.md`. El fix no cambió
ningún contrato público.

## Limitaciones

Registradas para v0.6+/deuda del roadmap; ninguna bloquea el cierre.

1. Sin una segunda familia de modelo/provider real disponible en este
   entorno (solo `claude_code`, ver Change 0/1), no se pudo verificar de
   punta a punta la recomendación del roadmap de "reviewer de familia de
   modelo distinta" -- documentado explícitamente, sin fingir una garantía
   que no existe (`policy.example.json` lo deja explícito en la regla de
   `reviewer`).
2. Este repo no declara ninguna política real de routing
   (`.harmessi/routing.json` no existe acá, deliberado -- el ejemplo vive
   en `tools/routing/examples/`).
3. Sin integración automática con resultados de `harmessi-bench` (Change
   1) -- el campo `reason` de una regla es donde un humano cita evidencia
   de evals manualmente; no hay ninguna feature de auto-sugerencia de
   routing basada en corridas de eval, decisión deliberada para no
   inventar una optimización automática.
4. El string `"default"` como valor por defecto de `--task-type`/parámetro
   `task_type` de `resolve()` es conceptualmente distinto de
   `RoutingPolicy.default` (la regla de fallback) -- puede confundir a
   quien escriba una política real pensando que son lo mismo; documentado
   acá, no resuelto con un cambio de nombre en este Change (cambiar el
   nombre sería un cambio de contrato no trivial, fuera de alcance de un
   fix menor).
5. Sin fallback automático (Change 3, próximo) -- `provider_available=False`
   es solo informativo hoy.

## Pendientes derivados

Ninguno bloqueante. Las 5 limitaciones de arriba quedan como deuda documentada para v0.6+ y para el sweep de privacidad transversal de Change 5.

## Resultado final

Change 2 (provider-routing) completo: resolutor declarativo de routing
(RoutingRule/RoutingPolicy/RoutingDecision + resolve() + carga/validacion
de politica opcional + wiring CLI) implementado, revisado (1 ronda, 1
hallazgo importante corregido) y verificado (100 tests totales entre las 2
suites afectadas + 1 bug de test propio detectado y corregido + smoke real
de show/resolve con --check-availability + alcance limpio); listo para
cierre SDD y commit local.

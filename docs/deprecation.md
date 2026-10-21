# Deprecación

Convención mínima, sin framework. La primitiva vive en `tools/harmessi/deprecation.py`
(solo-checkout, stdlib): no se instala en proyectos, no usa decoradores globales, no emite
telemetría y no escribe a disco.

## Política

- En **0.x** una deprecación vive al menos **una versión menor** antes de poder removerse
  (declarada en `0.Y.Z`, remoción no antes de `0.(Y+1).0`).
- En **1.x** vive al menos hasta la **siguiente mayor**.
- `remocion_minima` es la versión más temprana posible, no una promesa de remoción.

## Cómo deprecar

1. Agregar una `Deprecation(nombre, tipo, desde, reemplazo, remocion_minima)` a
   `DEPRECATIONS`. `tipo` ∈ `cli`, `flag`, `schema-field`, `skill-key`, `api`; las versiones
   son `X.Y.Z`; `reemplazo` no puede estar vacío; los nombres son únicos.
2. Llamar `advertir(nombre)` en el punto de uso. Emite un `DeprecationWarning` con formato
   fijo: `<nombre> está deprecado desde <desde>; usar <reemplazo>; se removerá no antes de
   <remocion_minima>`. Un nombre no registrado lanza `KeyError`.
3. Documentar el reemplazo y la versión de remoción más temprana en las notas de release y
   en `docs/contracts/inventory.json` (campo `notas` de la entrada afectada).
4. `validar_registro(DEPRECATIONS)` devuelve la lista de problemas; debe ser vacía.

`validar_registro` aplica además: en 1.x o más, `remocion_minima` debe ser al menos la
siguiente mayor; las versiones son `X.Y.Z` estrictas (sin espacios ni saltos de línea); los
nombres se comparan sin espacios en los bordes; nunca lanza (reporta problemas).
`advertir` rechaza con `ValueError` una entrada registrada inválida.

## Visibilidad del aviso

Python **silencia `DeprecationWarning` por defecto** salvo en código de `__main__` y bajo
pytest. Un usuario final puede no ver el aviso sin `-W default::DeprecationWarning` o
`PYTHONWARNINGS`. Por eso la deprecación también se documenta en las notas de release y en
el inventario; el warning solo no alcanza.

## Estado

El registro de v0.13 está **vacío**: no hay deprecaciones vigentes.

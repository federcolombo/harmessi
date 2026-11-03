# Deprecación

Convención mínima, sin framework. La primitiva vive en `tools/harmessi/deprecation.py`
(solo-checkout, stdlib): no se instala en proyectos, no usa decoradores globales, no emite
telemetría y no escribe a disco.

## Política

- En **0.x** una deprecación vive al menos **una versión menor** antes de poder removerse
  (declarada en `0.Y.Z`, remoción no antes de `0.(Y+1).0`).
- En **1.x** (desde 1.0.0, para los contratos `stable`) vive al menos hasta la **siguiente
  mayor**.
- `remocion_minima` es la versión más temprana posible, no una promesa de remoción.

## Cómo deprecar

1. Agregar una `Deprecation(nombre, tipo, desde, reemplazo, remocion_minima, guia)` a
   `DEPRECATIONS`. `tipo` ∈ `cli`, `flag`, `schema-field`, `skill-key`, `api`; las versiones
   son `X.Y.Z`; `reemplazo` y `guia` no pueden estar vacíos; los nombres son únicos.
2. Llamar `advertir(nombre)` en el punto de uso. Emite un `DeprecationWarning` con formato
   fijo: `<nombre> está deprecado desde <desde>; usar <reemplazo>; se removerá no antes de
   <remocion_minima>; guía: <guia>`. Un nombre no registrado lanza `KeyError`.
3. Documentar el reemplazo y la versión de remoción más temprana en las notas de release y
   en `docs/contracts/inventory.json` (campo `notas` de la entrada afectada).
4. `validar_registro(DEPRECATIONS)` devuelve la lista de problemas; debe ser vacía.

`validar_registro` aplica además: en 1.x o más, `remocion_minima` debe ser al menos la
siguiente mayor; las versiones son `X.Y.Z` estrictas (sin espacios ni saltos de línea); los
nombres se comparan sin espacios en los bordes; nunca lanza (reporta problemas).
`advertir` rechaza con `ValueError` una entrada registrada inválida.

## Mapeo de nombres

| Concepto | Campo |
|---|---|
| deprecated_since | `desde` |
| replacement | `reemplazo` |
| earliest_removal | `remocion_minima` |
| migration guidance | `guia` (obligatoria, no vacía) |

## Convención de nombres y cruce con inventory

`nombre` = `<id-inventory>[: detalle]`: el prefijo antes de `:` debe ser un `id` de
`docs/contracts/inventory.json`. Un test (`tools/harmessi/tests/test_deprecation.py`) cruza los
nombres del registro con el inventory: pasa con el registro vacío y falla ante un nombre cuyo
prefijo no existe.

## Ejemplo trabajado

Se depreca el flag `--viejo` de `harmessi_bench compare` en 0.16.0:

```python
Deprecation(
    nombre="cli-harmessi-bench: --viejo", tipo="flag", desde="0.16.0",
    reemplazo="--nuevo", remocion_minima="0.17.0",
    guia="reemplazar --viejo por --nuevo en scripts y CI; mismo significado",
)
```

`advertir("cli-harmessi-bench: --viejo")` emite: `cli-harmessi-bench: --viejo está deprecado
desde 0.16.0; usar --nuevo; se removerá no antes de 0.17.0; guía: reemplazar --viejo por
--nuevo en scripts y CI; mismo significado`. Además se anota en las notas de release de 0.16.0
y en `notas` de la entrada del inventory. En 0.17.0 puede removerse (en 0.x basta una menor).

## Visibilidad del aviso

Python **silencia `DeprecationWarning` por defecto** salvo en código de `__main__` y bajo
pytest. Un usuario final puede no ver el aviso sin `-W default::DeprecationWarning` o
`PYTHONWARNINGS`. Por eso la deprecación también se documenta en las notas de release y en
el inventario; el warning solo no alcanza.

## Estado

El registro (vacío desde v0.13) sigue **vacío** en v0.15: no hay deprecaciones vigentes
(un test lo ancla).

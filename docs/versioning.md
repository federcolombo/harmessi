# Versionado

Este documento formaliza la política vigente; no la cambia. Harmessi usa versionado
semántico `X.Y.Z`. El inventario de contratos está en `docs/contracts/`.

## 0.x frente a 1.x

- **0.x**: un cambio de versión *menor* (`0.Y`) puede traer cambios incompatibles, siempre
  con nota de release y camino de upgrade. Un cambio de *patch* (`0.Y.Z`) no los trae.
- **1.x** (futuro, no declarado): los cambios incompatibles solo en versión *mayor*; las
  menores y patches son compatibles.

Hoy no se promete estabilidad v1.0 para ningún contrato.

## Schemas persistidos

- Campo aditivo y opcional: sin bump de `schema_version`. Ejemplo: `cases_hash` y
  `run_manifest` en `result.json` v1.
- Cambio incompatible: bump de `schema_version` y lectura de la versión anterior dentro de
  la ventana de compatibilidad. Una versión futura (mayor que la soportada) se rechaza de
  forma explícita (fail-closed) donde el contrato lo define.
- Ausencia de `schema_version` en un artefacto heredado se lee como versión 0 (legado) donde
  el contrato así lo define (p. ej. `result.json` de evals).

## CLI

- Flag o subcomando nuevo: cambio menor.
- Remover o renombrar: primero deprecación (`docs/deprecation.md`); en 1.x, solo en mayor.
- Los exit codes inventariados son observados, no garantizados.

## Assets managed

Los archivos managed por `ds_init` se actualizan con `upgrade` (dry-run por defecto) solo
si están pristine. Un cambio de contenido managed es parte de la versión del harness; el
baseline `.ds_init/control.json` registra `harness_version` y `hash_alg` por entrada.

## `HARNESS_VERSION` y versiones de schema

`HARNESS_VERSION` (`tools/ds_init/version.py`) es la versión del producto. Las versiones de
schema (`SCHEMA_VERSION`, `RESULT_SCHEMA_VERSION`, `MANIFEST_VERSION`, etc.) son
independientes: cambian solo cuando cambia la forma persistida, no en cada release.

## Ventana de compatibilidad

Lectura soportada de artefactos de la **versión actual y las dos menores previas** (con
0.13 como actual: 0.13, 0.12 y 0.11), **limitada a los artefactos cubiertos por los tests
de compatibilidad**. Lista explícita (`tools/tests/test_v013_compat_window.py`):
resultado de eval (`result.json`, legado sin `schema_version` y v1), `SourceObservation` v1,
registro de fuentes, baseline `.ds_init/control.json` (con y sin `hash_alg`),
`control.json` de Change, frontmatter de skills y traza `## Skills cargados`. Los demás
artefactos persistidos del inventario no tienen test de compatibilidad dedicado: no entran
en la ventana documentada.

Los artefactos de versiones anteriores a la ventana se leen por mejor esfuerzo, sin
garantía. Los fixtures (`tools/tests/fixtures/compat/`) son **sintéticos**: reproducen la
forma, no datos reales. La verificación contra los tags reales `v0.11.0` y `v0.12.0` es
**opcional** (solo si existen localmente; si no, el test se saltea y no cuenta como
evidencia).

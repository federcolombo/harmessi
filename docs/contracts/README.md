# Inventario de contratos

`inventory.json` es la fuente legible por máquina; este documento es su vista humana.
Es un **inventario, no una promesa de estabilidad**: ninguna entrada, sea cual sea su
clase, compromete a Harmessi a mantenerla en v1.0. Sirve para saber qué habría que
congelar antes de declarar v1.0.

## Vocabulario

Categorías: `cli`, `schema`, `skills`, `managed-assets`, `adapter`, `provider`,
`surfaces`, `upgrade`.

Clases:
- `public-candidate`: superficie que un tercero consumiría y que ya tiene versión explícita
  o un test que ancle parte de ella. Es el candidato a congelar, no un congelamiento, y
  **no implica anclaje completo**: cada CLI `public-candidate` declara en `ancla` qué
  está realmente anclado (hoy: solo los nombres de subcomandos por test y los exit codes
  por lectura de código; los flags no tienen ancla).
- `internal`: uso interno del harness; puede cambiar sin aviso.
- `experimental`: nuevo (p. ej. v0.13) o de uso opt-in sin historial.

Regla de honestidad: lo heredado sin versión explícita y sin test que lo ancle nunca es
`public-candidate`. Lo nuevo de v0.13 que se persiste entre corridas lleva versión.

## Campos

Cada entrada: `id` (kebab-case, único), `categoria`, `clase`, `ubicacion` (ruta
repo-relativa existente), `notas`. Los `schema` suman `version` y, cuando existe una
constante, `version_ref` (`modulo.ruta:CONSTANTE`, resoluble por import). Los `cli`
suman `comando`, `subcomandos` (primer nivel) y `exit_codes`.

Los exit codes son **observados** leyendo el código, no garantizados. Los
sub-subcomandos (p. ej. `ds_guard session start`) no se inventarían. `harmessi_bench
compare` devuelve 0 aunque el veredicto sea regresión o inconcluso: el veredicto no se
refleja en el exit code.

## Qué ancla el test

`tools/tests/test_v013_contract_inventory.py` verifica: JSON válido, ids únicos y
vocabulario; rutas existentes; subcomandos de cada CLI idénticos a los reales (sin
ejecutar acciones: parsers o `--help`); cada `version_ref` coincide con su `version`;
todo schema `public-candidate` tiene versión y referencia; toda CLI del repo
(`tools/*/cli.py`, `tools/ds_guard.py`, `tools/providers/conformance.py`) figura en el
inventario, y todo script con guarda `__main__` está inventariado o excluido con motivo
(hooks, `notebook_runner.py`, `check_manifest_parity.py`); cada exit code inventariado
aparece en el módulo de su CLI y coincide con el docstring cuando este lista códigos; toda
constante de versión de módulo (`SCHEMA_VERSION`, `*_CONTRACT_VERSION`,
`MANIFEST_VERSION`, `SCHEMA_VERSION_SOPORTADA`) figura como `version_ref`. Una CLI o
constante nueva sin entrada rompe el test.

## Cómo cambiar un contrato

Ver `docs/versioning.md` (reglas de cambio y ventana de compatibilidad) y
`docs/deprecation.md` (cómo deprecar). Al agregar o cambiar una CLI, subcomando o
constante de versión, actualizar `inventory.json` en el mismo cambio.

## Inconsistencias halladas

- `.ds_init/control.json` (baseline managed) no tiene `schema_version`; se versiona
  indirectamente por `harness_version` y `hash_alg` por entrada.
- `HARNESS_VERSION` (`tools/ds_init/version.py`) cambia en cada release; por eso no se
  fija un valor en el inventario.

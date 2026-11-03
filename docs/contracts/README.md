# Inventario de contratos

`inventory.json` es la fuente legible por máquina; este documento es su vista humana.
La **promesa de estabilidad alcanza solo a las entradas `stable`** (desde 1.0.0, ver
`docs/versioning.md`): `cli-ds-guard`, `cli-ds-init`, `cli-harmessi`,
`schema-source-observation`, `schema-source-registry` y `schema-eval-result`. Las demás
entradas (`public-candidate`, `experimental`, `internal`) son inventario sin promesa y pueden
cambiar en una versión menor.

## Vocabulario

Categorías: `cli`, `schema`, `skills`, `managed-assets`, `adapter`, `provider`,
`surfaces`, `upgrade`.

Clases:
- `stable`: contrato con promesa de estabilidad desde 1.0.0 (cambio incompatible solo en
  mayor). Criterios: ventana de compatibilidad declarada; fixtures reales de un tag
  (`tools/tests/fixtures/compat/v0_15/`); lector con política de versión explícita
  (futura rechazada; ausente rechazada o legado según el contrato); ancla doc-test; y, para
  CLIs, ancla de superficie (snapshot `cli_surface.json` de subcomandos, flags, `required` y
  `choices`). Hoy son 6: las 3 CLIs `cli-ds-guard`, `cli-ds-init`, `cli-harmessi` y los 3
  schemas `schema-source-observation`, `schema-source-registry`, `schema-eval-result`.
- `public-candidate`: superficie que un tercero consumiría y que ya tiene versión explícita
  o un test que ancle parte de ella. Es el candidato a congelar, no un congelamiento, y
  **no implica anclaje completo**. Desde 1.0.0 (`HARNESS_VERSION` 1.0.0) ninguna entrada es `public-candidate`: las 6 que lo
  eran se promovieron a `stable` con el release 1.0.0 (con ancla de flags vía snapshot). La clase queda
  disponible para futuras candidatas.
- `internal`: uso interno del harness; puede cambiar sin aviso.
- `experimental`: nuevo (p. ej. v0.13 o v0.14) o de uso opt-in sin historial. En v0.14 son `experimental` la CLI
  `harmessi_improve` y los contratos de candidate, probe, decision, proposal, lesson, estado de budget y política de
  probe (versionados; ventana de compatibilidad 0.14-0.15 desde v0.15, ver abajo).

Regla de honestidad: lo heredado sin versión explícita y sin test que lo ancle nunca es
`public-candidate`. Lo nuevo de v0.13 y v0.14 que se persiste entre corridas lleva versión.

## Campos

Cada entrada: `id` (kebab-case, único), `categoria`, `clase`, `ubicacion` (ruta
repo-relativa existente), `notas`. Los `schema` suman `version` y, cuando existe una
constante, `version_ref` (`modulo.ruta:CONSTANTE`, resoluble por import). Los `cli`
suman `comando`, `subcomandos` (primer nivel) y `exit_codes`.

De los exit codes de `cli-ds-guard`, `cli-ds-init` y `cli-harmessi` (campo
`exit_codes_contrato`) solo está garantizado desde 1.0.0 que 0 es éxito y distinto de 0 es
fallo (`docs/versioning.md`); el significado de cada código distinto de 0 es observado. En las demás CLIs todos son observados. Los
sub-subcomandos (p. ej. `ds_guard session start`) no se inventarían. `harmessi_bench
compare` devuelve 0 siempre que la comparación se realice (el veredicto va en la salida);
`--fail-on-regression` (opt-in) sale con 1 si el veredicto es `baseline_better`; el exit 1
también es error de `compare`, así que un CI no los distingue sin mirar la salida.

## Compatibilidad por contrato (campo `compat`)

Los contratos versionados con test llevan `compat` con cinco claves: `lector`,
`campos_desconocidos`, `version_no_soportada`, `migracion`, `ventana`. Ventana pre-v1 y
regla de bump: `docs/versioning.md`. Test: `test_v013_contract_inventory.py`.

| Contrato | Versión | Lector | Campo desconocido | Versión no soportada | Migración | Ventana |
|---|---|---|---|---|---|---|
| candidate | `contract_version` 1 | `Candidate.desde_dict` | rechazo (`CandidateCorrupta`) | rechazo | ninguna | 0.14-0.15 |
| probe | `contract_version` 1 | `cargar_probe` | rechazo (`ProbeCorrupto`) | rechazo | ninguna | 0.14-0.15 |
| decision | `contract_version` 1 | `cargar_decision` | rechazo (`EvidenciaInvalida`) | rechazo | ninguna | 0.14-0.15 |
| proposal | `contract_version` 1 | `cargar_propuesta` | rechazo (`PropuestaInvalida`) | rechazo | ninguna | 0.14-0.15 |
| lesson | `contract_version` 1 | `cargar_lesson` | rechazo (`LessonRechazada`) | rechazo | ninguna | 0.14-0.15 |
| budget_state | `budget_version` 1 | `_leer_estado` | rechazo (`PresupuestoInvalido`) | rechazo | ninguna | 0.14-0.15 |
| policy | `policy_version` 1 | `ProbePolicy.desde_dict` | rechazo (`PolicyInvalida`) | rechazo | ninguna | 0.14-0.15 |

Schemas `stable` (promesa desde 1.0.0; fixtures reales del tag v0.15.0 en
`tools/tests/fixtures/compat/v0_15/`, anclados por `test_v1_stable_contracts.py`):

| Contrato | Lector | Versión futura | Versión ausente | Claves desconocidas | Ventana |
|---|---|---|---|---|---|
| SourceObservation | `SourceObservation.from_dict` | rechazo (`SourceError`) | rechazo | top-level tolerada (aditivo); sub-objetos (`dataset`, `provenance`) rechazan | 1.x y 0.15 |
| registro de fuentes | `validate_registry` | rechazo (problema reportado) | rechazo | top-level tolerada; entradas del registro rechazan | 1.x y 0.15 |
| resultado de eval | `load_run` | rechazo (`ValueError`) | leída como 0 (legado) | top-level tolerada | 1.x y 0.15 |

Los lectores improve exigen igualdad exacta de claves; una versión ausente, futura o bool se
rechaza. Los demás contratos: `result.json` (ausente = 0 legado, 0/1 legibles, futura ->
`ValueError`, campos desconocidos aceptados); caso de eval (0/1, ignora desconocidos); suite
(claves exactas, versión 1); run manifest (`manifest_version` futura, no entera o bool ->
incompatible con razón explícita, validación aplicada en `run --resume` vía
`evaluar_compatibilidad`; `compare` solo compara igualdad entre corridas). La tabla estricta
aplica a `budget_state.json`: el `budget.json` de configuración tolera `budget_version`
ausente y claves faltantes. Respaldo de fixtures: reales son `v0_15/` (los 3 schemas stable y `cli_surface.json`), `v0_14/` (improve) y los
baselines v0_13/v0_14 (el `control.json` del propio repo en cada tag); los demás son
sintéticos (`v0_11/`, `v0_12/`, `eval_result_cases_hash.json`) o no tienen fixture dedicado.

**Baseline `.ds_init/control.json`**: sin `schema_version` por decisión (B-02): se versiona por
`harness_version` + `hash_alg` por entrada; fixtures reales de v0.13.0 y v0.14.0.

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

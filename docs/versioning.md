# Versionado

Este documento formaliza la política de versionado. Desde v0.15 agrega la ventana de
compatibilidad pre-v1, la regla de bump, el contrato de exit codes de las CLIs candidatas y
la política de promoción. Harmessi usa versionado semántico `X.Y.Z`. El inventario de contratos está en `docs/contracts/`.

## 0.x frente a 1.x

- **0.x**: un cambio de versión *menor* (`0.Y`) puede traer cambios incompatibles, siempre
  con nota de release y camino de upgrade. Un cambio de *patch* (`0.Y.Z`) no los trae.
- **1.x** (rige desde el release 1.0.0 para los contratos `stable`): los cambios incompatibles solo en
  versión *mayor*; las menores y patches son compatibles.

La promesa v1 alcanza **solo** a los 6 contratos `stable`: `cli-ds-guard`, `cli-ds-init`,
`cli-harmessi`, `schema-source-observation`, `schema-source-registry` y
`schema-eval-result`. Todo contrato `experimental` o `internal` queda **explícitamente fuera**
de la promesa y puede cambiar en una versión menor.

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
- La superficie de las CLIs `stable` es lo anclado en el snapshot
  (`tools/tests/fixtures/compat/v0_15/cli_surface.json`): subcomandos, flags, `required` y
  `choices`. Agregar es cambio menor; quitar, renombrar o endurecer (hacer obligatorio un flag,
  restringir `choices`) es mayor.
- Los exit codes de las CLIs `stable` están garantizados en 1.x (ver "Exit codes
  garantizados"); en las demás CLIs son observados.

## Assets managed

Los archivos managed por `ds_init` se actualizan con `upgrade` (dry-run por defecto) solo
si están pristine. Un cambio de contenido managed es parte de la versión del harness; el
baseline `.ds_init/control.json` registra `harness_version` y `hash_alg` por entrada.

## `HARNESS_VERSION` y versiones de schema

`HARNESS_VERSION` (`tools/ds_init/version.py`) es la versión del producto. Las versiones de
schema (`SCHEMA_VERSION`, `RESULT_SCHEMA_VERSION`, `MANIFEST_VERSION`, etc.) son
independientes: cambian solo cuando cambia la forma persistida, no en cada release.

## Ventana de compatibilidad

**1.0**: la ventana es **1.x** más la lectura de los artefactos de **0.15** que tienen fixture
real (los 3 schemas `stable`, en `tools/tests/fixtures/compat/v0_15/`). Lo `experimental` o
`internal` no entra en la ventana 1.0.

Ventana pre-v1 (aplica a las versiones 0.x, hasta el release 1.0.0; no se mezcla con la ventana 1.0 de
arriba): lectura soportada de artefactos de la **versión actual y las dos menores
previas** (0.15, 0.14 y 0.13), **limitada a artefactos con test** (sin test dedicado no hay
promesa). Anclada por `tools/tests/test_v015_compat_window.py`, que falla si esta sección
deja de listar 0.13-0.15.

- v0.11 y v0.12 **salen de la promesa**; sus tests (`test_v013_compat_window.py`) se
  conservan como **best-effort**.
- Los contratos `harmessi_improve` nacieron en 0.14: su ventana es **0.14-0.15**. Fixtures
  reales del tag v0.14.0 en `tools/tests/fixtures/compat/v0_14/`, generados por el script
  solo-checkout `generate_v014.py` (`git archive v0.14.0`); no se editan a mano porque los
  hashes internos atan el contenido.
- Data Card v1 (v0.14.0) tiene fixture real y test (`tools/tests/fixtures/compat/v0_14/data_card.json` con `MANIFEST_data_card.json`, generado por `generate_datacard_v014.py` desde `git archive v0.14.0`; `tools/tests/test_compat_datacard_v014.py`): ventana **0.14-0.15**.
- Baseline `.ds_init/control.json`: fixtures reales de v0.13.0 y v0.14.0 (`git show <tag>:...`).

### Contratos improve: lector y regla de bump

Los siete contratos improve (candidate, probe, decision, proposal, lesson, budget_state,
policy) usan lector estricto fail-closed y **no tienen migración** mientras su versión sea 1:
campo desconocido, clave ausente, versión no soportada (incluida la futura) o versión
ausente se rechazan con la excepción propia del módulo. Tabla por contrato en
`docs/contracts/README.md`. `budget_version` y `policy_version` son campos aparte (valor 1).

**Regla de bump** (versión 1 -> 2 de cualquiera de ellos): el lector debe leer la versión
anterior dentro de la ventana **y** debe existir un fixture del tag que la produjo, con test.

### Baseline sin `schema_version` (decisión B-02)

`.ds_init/control.json` **no gana `schema_version`**: se versiona por `harness_version` +
`hash_alg` por entrada. Agregarlo tocaría el manifest de ds_init, el Doctor y el baseline
(se gestiona en C7).

### Nomenclatura

`contract_version` y `schema_version` son equivalentes (versión de la forma persistida);
cada contrato conserva el nombre que ya usa.

## SemVer: 0.x frente a 1.x por tipo de contrato

En 0.x un cambio menor puede ser incompatible (con nota de release y camino de upgrade);
el patch no. En **1.x**:

| Tipo | patch | minor | major |
|---|---|---|---|
| CLI (comando, flag, exit code) | corrección sin cambiar interfaz | comando/flag nuevo opcional; código nuevo para un caso nuevo | remover o renombrar, cambiar 0 = éxito a otro código (o éxito a fallo), hacer obligatorio un flag |
| Schema persistido | sin cambio de forma | campo aditivo opcional | cambio incompatible (bump de versión; lee la anterior dentro de la ventana) |
| SourceObservation / adapter | corrección interna | capacidad opcional nueva | cambio de campos requeridos o de semántica |
| Skills (frontmatter) | texto de la skill | clave opcional nueva | clave obligatoria nueva o clave removida |
| Cards | texto/estilo | sección o campo opcional | cambio de campos requeridos |
| Contratos improve | sin cambio de forma | campo opcional con lector que acepta ambos | bump de `contract_version` |
| `inventory.json` | notas | campos opcionales (p. ej. `compat`) | quitar/renombrar claves; sube `inventory_version` |

**Cambio incompatible**: el que hace fallar o cambiar el resultado de un consumidor que
cumplía el contrato documentado (quitar o renombrar, restringir valores aceptados, cambiar el
significado de un campo o exit code, o dejar de leer una versión dentro de la ventana).

### Exit codes garantizados

En las CLIs `stable` (`cli-ds-guard`, `cli-ds-init`, `cli-harmessi`) está garantizado en 1.x
solo esto: **0 = éxito; cualquier valor distinto de 0 = fallo** (gate incumplido, uso
inválido, error de entorno o de operación). Invertir esa relación es un cambio incompatible y
solo ocurre en una versión mayor. El significado de cada código distinto de 0 (1/2/3, listado
en `exit_codes` de `docs/contracts/inventory.json`) es **observado, no garantizado**: un código
nuevo o un refinamiento de cuál distinto de 0 corresponde a cada caso es un cambio menor.
Quien necesite distinguir causas no debe depender del número exacto. (Antes de 1.0.0, en 0.x,
un cambio así podía ocurrir en una menor.)
Los códigos por sub-subcomando no están inventariados. `harmessi_bench compare` devuelve 0
siempre que la comparación se realice (el veredicto va en la salida); el flag opt-in
`--fail-on-regression` sale con 1 si el veredicto es `baseline_better` (la regresión según
`compare.py`). Atención: el exit 1 también es el código de error de `compare` (corrida
inexistente o inválida), así que un CI no distingue regresión de error sin mirar la salida.

### Validación de `manifest_version`

`evaluar_compatibilidad` (usada por `run --resume`) rechaza con razón explícita una
`manifest_version` futura, no entera, bool o menor a 1. `compare` no valida contra la versión
soportada: solo compara igualdad de la versión entre las dos corridas (distinta -> `inconclusive`).

### `budget.json` frente a `budget_state.json`

La tabla estricta de contratos improve aplica a `budget_state.json` (estado de consumo). El
`budget.json` de configuración es otro archivo y tolera `budget_version` ausente y claves
faltantes (usa defaults); no es parte de la tabla de rechazo.

### Cambio de la dataclass `Deprecation`

Hacer obligatorio el campo `guia` (v0.15) es un cambio incompatible **interno** de la dataclass
(solo-checkout, registro vacío, sin consumidores externos); no afecta contratos públicos.

### Promoción: experimental -> public-candidate -> stable

- `experimental` -> `public-candidate`: versión explícita y test que ancle parte del contrato.
- `public-candidate` -> `stable`: ventana de compatibilidad declarada, fixtures reales de tags,
  test de lector (fail-closed) y ancla doc-test; para CLIs, además ancla de superficie.
- Se promovieron a `stable` con el release 1.0.0 (rige desde 1.0.0; el árbol declara
  `HARNESS_VERSION` 1.0.0): `cli-ds-guard`, `cli-ds-init`, `cli-harmessi`,
  `schema-source-observation`, `schema-source-registry`, `schema-eval-result`. Evidencia:
  fixtures reales del tag v0.15.0 (`tools/tests/fixtures/compat/v0_15/`, con `MANIFEST.json`
  y generador solo-checkout `generate_v015.py`), test de lector
  (`tools/tests/test_v1_stable_contracts.py`), snapshot de superficie CLI (`cli_surface.json`)
  y ancla doc-test.
- Política de claves desconocidas y versión de los 3 schemas `stable`:
  - Clave desconocida **top-level**: aditiva y tolerada en SourceObservation, registro de
    fuentes y resultado de eval.
  - **Sub-objetos**: `dataset` y las entradas de `sources` del registro **rechazan** claves
    desconocidas; `provenance` y las entradas de `fields` las ignoran. Por eso agregar un campo
    a `dataset` o a una entrada del registro **no** es aditivo: es cambio mayor para un lector
    anterior (un consumidor 1.0 rechazaría el dato nuevo). Todo campo nuevo en esos sub-objetos
    exige subir `schema_version`. Anclado por `test_v1_stable_contracts.py`.
  - Versión **futura**: rechazada en los 3.
  - Versión **ausente**: rechazada en SourceObservation y registro; en `result.json` de eval
    se lee como 0 (legado).

## Ventana anterior (v0.13, histórica)

Lista explícita (`tools/tests/test_v013_compat_window.py`):
resultado de eval (`result.json`, legado sin `schema_version` y v1), `SourceObservation` v1,
registro de fuentes, baseline `.ds_init/control.json` (con y sin `hash_alg`),
`control.json` de Change, frontmatter de skills y traza `## Skills cargados`. Los demás
artefactos persistidos del inventario no tienen test de compatibilidad dedicado: no entran
en la ventana documentada.

Los artefactos de versiones anteriores a la ventana se leen por mejor esfuerzo, sin
garantía. Fixtures en `tools/tests/fixtures/compat/`: **reales** (generados con el código del
tag o por `git show <tag>:...`) son `v0_15/` (los 3 schemas stable y `cli_surface.json`, del
tag v0.15.0), `v0_14/` (contratos improve) y los baselines
`ds_init_control.json` de `v0_13/` y `v0_14/` (el `.ds_init/control.json` del propio repo en
cada tag); **sintéticos** (reproducen la forma, no datos reales) son `v0_11/`, `v0_12/` y el
resto de `v0_13/` (`eval_result_cases_hash.json`). La verificación contra los tags reales `v0.11.0` y `v0.12.0` es
**opcional** (solo si existen localmente; si no, el test se saltea y no cuenta como
evidencia).

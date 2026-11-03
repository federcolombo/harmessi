# Diseño — 20260928-source-neutral-data-access

## Decisiones de diseño

**D1 — Paquete nuevo `tools/datasources/`, independiente.** No amplía `dsguard`, `ds_profile` ni
`datacontracts`: el contrato de fuentes es una familia propia (mismo criterio que `tools/autonomy`,
Change 0). Puede importar `dsguard.checks` (para `CheckResult`); ninguna otra familia lo importa,
salvo la excepción acotada de M1: `tools.datacontracts.validation` importa `datasources` porque el
evaluador único trabaja sobre `SourceObservation` (verificada por `test_v08_datasources_neutrality`).
Módulos y estilo de imports:
- `core.py` solo stdlib (`dataclasses`, `typing`, `re`, `json`, `hashlib`, `unicodedata`,
  `__future__`); tipos, serialización y el registro único de códigos `SOURCE-*`; sin paths, SQL,
  hosts ni DataFrames; no ramifica sobre `source_kind`.
- `scan.py` puro (secretos y localizadores).
- `registry.py` puro sobre dicts (schema del registro, validación, resolución estática del
  observer con `exists_fn` inyectable).
- `runtime.py` I/O + `importlib`: lee el registro, `check_registry`, `observe_source`,
  persistencia, frescura.
- `profile_bridge.py` puro: encapsula el vocabulario de `ds_profile`.
- `file_observer.py`: el único observer incluido (compatibilidad). Stage `experiment` como
  `ds_profile`; el resto del paquete stage `discovery`.
Los imports relativos (`from . import core`) siguen el estilo de
`datacontracts/validation.py:74`; `runtime.py` usa `from dsguard import checks` tras el
`sys.path.insert` del mismo estilo (`validation.py:67-71`).

**Doble identidad de módulos.** `ds_guard` importa de dos formas (`datacontracts.x` o
`tools.datacontracts.x`, `ds_guard.py:919-932`), de modo que `datasources.core` y
`tools.datasources.core` pueden coexistir como módulos distintos y romper `isinstance`.
Decisión: `validate_contract_observation` acepta `SourceObservation` **o dict** y normaliza con su
propio `from_dict`; ningún código de frontera usa `isinstance` contra clases de otra ruta de import.
Test dedicado (importar por ambas rutas y evaluar).

**D2 — `SourceRef` y `source_id` lógico.** Detalle de campos en `spec.md` R4. El patrón se DUPLICA
en `datasources.core` respecto de `tools/autonomy/core.py:332`; `test_v08_source_id_parity.py`
afirma su igualdad (los paquetes son independientes, evitando la deuda de acoplamientos ocultos).
`sensitivity` NO incluye "sealed": el sellado es policy humana (Change 0) y vive en
`guardrails.json`, no en el registro que puede editar el writer. `options` es opaco para Harmessi
(propiedad del observer) pero acotado en tamaño y escaneado. No se amplía el regex ni se añade un
campo de namespace: cualquier jerarquía (`schema.tabla`) es tarea del observer/`options`.

**D3 — Contrato del observer con frontera JSON.** `factory(source_id, options) -> observer`,
`observer.capabilities()`, `observer.observe(request)`; entradas/salidas dict o tipos. Así el
proyecto no necesita importar tipos de Harmessi ni instalar nada de Harmessi en su `.venv`.
El pedido no contiene texto de consulta (roadmap línea 139): cómo se obtiene la evidencia es interno
del observer. El core no invoca `read`/`write`/`sample` (test `ast`).

**D4 — Capacidades en dos ejes; vocabulario mínimo.** Facetas de observación con exactitud
(`exact`/`approximate`) y operaciones declarables (`sample`, `read`, `write`, solo informativas).
`access_ceiling = read`; `execute_query` no existe (evita SQL en el core, roadmap línea 179). El
vocabulario de facetas es **exactamente lo que un contrato v0.7 puede consumir**: no es una
biblioteca estadística (media, cuantiles, longitud de texto quedan fuera; ver riesgo de scope creep).
Mapeo respecto de la lista candidata del roadmap: `null_counts`->`null_count`, `min_max`->
`value_range`, `uniqueness`->`distinct_count` (+ `value_distribution` para duplicados en muestra),
`domain`->`value_distribution`, `time_bounds`->`time_range`; `schema`, `row_count`, `snapshot`,
`fingerprint` se mantienen.

**D5 — `SourceObservation`.** Faceta observada = `{value, exactness}`; **ausencia = no observado**,
distinta de `0`/vacío/`null`. La única excepción controlada es el rango observado y vacío
(`{"min": null, "max": null}` exact) que el evaluador necesita para conservar la paridad con
`validation.py:608,615` (una columna numérica sin no-nulos hoy da PASS y no debe pasar a WARN;
ver "Hallazgo de diseño" abajo). Familias observadas: las de `ContractField` (`core.py:58`,
`TYPE_FAMILIES`) más `temporal` (fecha sin distinguir `date`/`datetime`, porque `ds_profile` no las
distingue, `validation.py:118`).

**D6 — `SourceProvenance` y `technical_error`.** `observer_code_sha256` lo calcula el runtime del
archivo del módulo importado (no lo declara el observer, para que no se pueda falsear
inadvertidamente). `source_kind` es informativo. Los errores del observer se devuelven como
`technical_error` (mismo `CheckResult.kind` que la decisión 4 de v0.7: separado del resultado de
calidad) y nunca como FAIL de contrato.

**D7 — Registro `.harmessi/sources.json`.** Archivo del proyecto, versionado en git, fuera del
manifiesto de instalación y de `control.json["archivos"]` -> no puede producir `HARMESSI-DRIFT`
por construcción (roadmap líneas 243-246). Validación estática: el Doctor (Change 4) llamará a
`check_registry`; aquí solo se entrega la función reutilizable. El módulo del observer se resuelve
como archivo (`a/b.py` o `a/b/__init__.py`) sin importarlo; si no aparece es un hallazgo WARN, no un
error, porque el paquete puede estar instalado en el `.venv` (`SOURCE-OBSERVER-UNRESOLVED`).

**D8 — `observe_source` y orden de gates.** Registro -> `access_check` inyectado -> import ->
capacidades -> pedido acotado -> observe -> normalización -> sensibilidad -> gate portabilidad ->
persistencia atómica. Razones del orden:
- El sellado se consulta **antes de importar** el observer: importar código del proyecto ya es
  ejecutarlo (efectos de import), y una fuente sellada no debe ni tocarse.
- La sensibilidad se aplica antes del hash y de persistir, y deja `omitted_facets` (nunca omisión
  silenciosa; roadmap líneas 164-167).
- El gate de secretos/portabilidad corre sobre la observación completa **normalizada** (lo que se
  persistiría), no sobre lo que el observer devolvió crudo.
Sin timeout en proceso (M6): límite honesto.

**Composición real de `access_check` en `ds_guard`.** `datasources` no importa `autonomy` ni
`pathguard`. `ds_guard.py` (que ya hace imports perezosos) compone: `pathguard.cargar_config`
(fail-closed de versión), `parse_autonomy_policy(dict, pathguard.POLICY_VERSION_MAX)`,
`effective_source_access`, `is_source_sealed`. Guardrails ilegible o corrupto -> denegado;
`autonomy` presente con paquete `tools/autonomy` ausente -> denegado; ausencia total de `autonomy`
= sin sellos (misma semántica que la enmienda M2 del Change 0, `design.md` de Change 0). Detalle
por resolver en implementación (no decidido aquí): la firma exacta de `effective_source_access`
(`policy.py:323`) y cómo se traduce su resultado a `(permitido, motivo)`; el implementador lee la
función antes de escribirla.

**D9 — Frescura.** `compare_fingerprint` es pura y compara solo `dataset.fingerprint`;
`snapshot.as_of` se reporta pero no reemplaza al fingerprint (dos fechas pueden tener los mismos
datos; el mismo `as_of` puede tener datos distintos). Nunca PASS por ausencia: WARN
`SOURCE-FRESHNESS-UNVERIFIABLE`.

**D10 — Bridge.** El bridge concentra el vocabulario de `ds_profile` (dtypes y claves en español)
para que ningún otro módulo del core lo conozca. Mapeo en `spec.md` R27. Puntos verificados en el
código de `ds_profile`: `nulls.count` y `min`/`max` siempre exactos (acumulador en streaming,
`column_stats.py:1-14`); `unique` y `top_valores` siguen `exactitud_orden`
(`column_stats.py:271-272`); `fingerprint = {algoritmo, hash}` (`fingerprint.py:29`); el perfil
incluye `dataset_path` (`report.py:210`) que el bridge NUNCA copia. `ds_profile` y `profile.json`
schema_version 1 no cambian. El wrapper de datacontracts conserva su gate legacy
(`_validar_evidencia`) para devolver los mismos `technical_error` v0.7 y no depender de los
mensajes de `SourceError`.

**D11 — Evaluador único.** `validate_contract_observation` es nativo; las `_regla_*` de
`validation.py:238-719` pasan a operar sobre la observación. `validate_contract` /
`validate_contract_against_profile_file` quedan como wrappers (`validation.py:774,848`). Reglas
sobre facetas (semántica en `spec.md` R30). Asimetría RANGE conservada de v0.7: una violación es
válida aun con evidencia approximate (un mínimo observado ya menor que el declarado prueba la
violación); el cumplimiento solo se afirma con exact. Análogo a UNIQUE (frecuencia > 1 en muestra) y
NULLABILITY (una muestra con nulos prueba que hay nulos).

**D12 — Paridad y `wording`.** Criterio de cierre = igualdad exacta contra el golden v0.7 (R34).
Para preservar los mensajes v0.7 verbatim sin dos motores, el evaluador recibe un `wording`
(catálogo de mensajes) por **parámetro**. `LEGACY_PROFILE` vive en `legacy_wording.py` con plan de
deprecación en v0.10/v1.0. Los mensajes legacy dependen de `dtype`; el catálogo legacy usa
`native_type` y la tabla familia->dtypes (`validation.py:112-120`). El golden se genera ANTES de
tocar `validation.py` (T0), por el Lead, para que "antes" sea el código v0.7 real y no una
reconstrucción.

**D13 — CLI.** Todo en `ds_guard.py` (host único de subcomandos), con los tres patrones ya
existentes (imports perezosos, `--json`, exit codes 0/1/2/3). `contract validate` gana
`--observation` mutuamente excluyente con `--profile`; `--profile` queda idéntico. Sin `ds_guard
autonomy` (Change 3).

**D14 — Orden de implementación.** T0 (golden) -> `datasources` -> refactor de
`validation.py` -> `ds_guard` -> manifiesto -> tests de repo/ARCHITECTURE -> cierre. El orden hace
que el refactor de `validation.py` (el punto de mayor riesgo) ocurra con el golden y el bridge ya
listos.

### Hallazgo de diseño: rango observado y vacío (paridad)

`ds_profile` emite `min`/`max` (y `fecha_min`/`fecha_max`) como `null` cuando la columna no tiene
valores no nulos (`column_stats.py:278-287`). v0.7 resuelve numérico -> PASS (nada viola) y fecha ->
WARN (formato no comparable). Si "ausencia = no observado" se aplicara a rajatabla, el bridge
omitiría la faceta y el numérico pasaría de PASS a WARN: ruptura de paridad con una entrada
**conforme**. Se resuelve modelando "observado y vacío" con `{"min": null, "max": null}` exact
(R31), conservando la semántica de "ausencia" para lo realmente no observado. Se reporta al Lead
como matiz de D5.

## Compatibilidad hacia atrás

### `ds_profile`
- **No cambia:** CLI, `profile.json` schema_version 1, `fingerprint.py`, `holdout_guard.py`,
  `column_stats.py`, ni sus tests. `dataset_path` sigue existiendo en `profile.json` (es del perfil;
  la observación no lo hereda).
- **Se agrega (fuera de `ds_profile`):** `profile_bridge` (lectura pura del dict) y
  `file_observer` (orquesta `ds_profile` con import perezoso). El guard de holdout sigue siendo el
  de `ds_profile` (`holdout_guard.py:89`).
- **Dirección de dependencias:** `datasources.file_observer` -> `ds_profile`; nunca al revés.

### Data Contracts v0.7
- **Firmas:** `validate_contract(contract, profile)` y
  `validate_contract_against_profile_file(contract, profile_path, repo_root)` sin cambios;
  `validate_contract_observation(contract, observation, *, wording=None)` es nueva.
- **Códigos:** `CONTRACT-*` sin cambios (`validation.py:78-108`); `SOURCE-*` solo para lo específico
  de observación.
- **Paridad:** golden v0.7 (R34) con igualdad exacta de `CheckResult.to_dict()` y del orden;
  tests existentes intactos.
- **Divergencias declaradas (solo entradas NO conformes con lo que `ds_profile` siempre emite):**
  1. facetas por columna ausentes (`nulls`, `unique`, `top_valores`, `min`/`max`, `fecha_*`): v0.7
     daba PASS/FAIL por evidencia ausente; ahora WARN no verificable;
  2. dtype fuera de los 5 valores: v0.7 FAIL type-mismatch; ahora `unknown` -> WARN "no
     clasificable";
  3. campo en `schema` sin entrada en `columnas_detalle`: v0.7 FAIL/`ausente`; ahora `unknown` ->
     WARN;
  4. `fingerprint` ausente en el perfil (los fixtures de tests no lo traen) no afecta a las reglas
     (solo a `compare_fingerprint`).
  Todas fijadas por tests propios y por el `verification.md` futuro; el golden no las contiene.
- **Wrappers:** `gate legacy -> bridge -> evaluador` con `wording=LEGACY_PROFILE`; conservan el
  guard de holdout antes de abrir el archivo (`validation.py:789`) y sus `technical_error`.
- **Excepción de dependencias:** `tools.datacontracts.validation` importa `datasources`, hasta
  hoy solo importaba `dsguard.checks` y `ds_profile.holdout_guard` (`validation.py:71-72`).

### `source_id` canónico del Change 0
- `source_id` es el identificador **lógico** ya congelado (`[a-z0-9][a-z0-9_-]{0,63}`,
  `autonomy/core.py:332`); el registro y el sellado hablan solo de él.
- La información **física** (tabla, schema, path, bucket, endpoint, URL, dataset externo) vive en
  `options`/`config_ref` y en el código del observer; nunca en el `source_id` ni en la observación.
- Ejemplos del autor: `dbo.Clientes.Productores`, `project.dataset.customers`, `/v2/customers`,
  `data/raw/customers.parquet` ⇒ `source_id = customers`; lo físico en `options` (p. ej.
  `{"table": "dbo.Clientes.Productores"}` con el observer que sabe interpretarlo).
- Si hiciera falta jerarquía/namespace, será otro campo/contrato explícito; no se amplía el regex.
- Coherencia file-backed (roadmap líneas 271-274): la comprobación "ruta en holdout <-> source_id
  sellado" es de Change 4 (`sealed_coherence_findings`, matcher inyectado); en este Change el
  `file_observer` pasa por `verificar_permitido` en cualquier caso.

## Alternativas descartadas

1. **"adapter"/"provider" como nombre.** "adapter" ya designa adapters de hooks
   (`ARCHITECTURE.md` §2.2) y `tools/providers` designa proveedores de IA: colisión de vocabulario
   (roadmap líneas 490-491). Se elige `SourceObserver` y se documenta el mapeo.
2. **`execute_query` como capacidad.** Reintroduce SQL en el core y convierte a Harmessi en un
   ejecutor de consultas del proyecto. El observer usa SQL internamente; Harmessi nunca lo sabe.
3. **Facetas planas** (lista única mezclando `schema`, `null_count`, `sample`, `write`). Mezcla lo
   que el core puede *pedir* con lo que el proyecto puede *hacer*; se separan en dos ejes.
4. **Evaluador paralelo** (nuevo motor para observaciones más wrappers que sigan usando el viejo).
   Dos motores divergen; M1 exige uno solo. Se paga con el refactor y el golden.
5. **Extender `ds_profile` a otras fuentes.** Lo convertiría en catálogo de conectores (prohibido
   por el roadmap, línea 219).
6. **`entry_points` (E2).** Descubrimiento implícito, difícil de auditar, exige empaquetar el
   observer (roadmap línea 230).
7. **Comando externo por stdout (E3).** Fuera de v0.8; sigue siendo compatible (la observación JSON
   ya es el formato de cable).
8. **`wording` por observación** (que la observación lleve el estilo de mensaje). Contamina el dato
   con presentación y obligaría a persistir "legacy" en evidencias; se elige parámetro del
   evaluador.
9. **Persistir valores en fuentes sensibles** (y filtrarlos después). Un valor persistido ya es
   exposición; se omiten antes de persistir y se registra la omisión.
10. **Timeout en proceso** con hilos/señales. No hay forma portable y segura en el mismo proceso; se
    delega al runtime de ejecución del Change 2.

## Riesgos

1. **In-process sin sandbox.** El observer comparte permisos con el proceso; puede abrir conexiones
   propias o escribir a una fuente. Mitigación: sellado antes de importar, `access_mode` declarado,
   revisión del reviewer, cuenta de solo lectura del proyecto; límite honesto documentado (roadmap
   líneas 276-286). Harmessi no puede detectar writes a bases/APIs.
2. **Observer que hace I/O propio** (archivos, red) fuera de lo que Harmessi media: no detectable.
3. **Scan de secretos por patrón, best-effort.** Falsos negativos (credenciales atípicas) y falsos
   positivos (hex largo legítimo). Se declara así; la garantía fuerte sigue siendo `pathguard`
   (`.env`/claves) y que el observer maneje credenciales.
4. **El golden depende de que el corpus sea representativo.** Si la matriz omite un caso, la paridad
   no lo cubre. Mitigación: fixtures existentes + matriz sistemática + revisión del reviewer del
   inventario del corpus antes del refactor.
5. **Complejidad del `wording`.** El catálogo legacy replica ~40 mensajes; riesgo de desvío
   silencioso. Mitigación: el golden compara mensajes exactos; `legacy_wording.py` se deprecará
   (v0.10/v1.0).
6. **Observer colgado sin timeout hasta el Change 2.** Bloquea el proceso que lo llama.
7. **`ds_profile` no distingue `date`/`datetime`.** `temporal` cubre el hueco; un contrato
   `datetime` sobre una columna solo-fecha no puede detectarse hasta que exista un observer que sí
   distinga.
8. **Costo del refactor de `validation.py`** (855 líneas, contrato público de v0.7). Mitigación:
   golden previo, invocaciones acotadas, tests existentes sin editar; si aparece una divergencia en
   un fixture existente, se detiene y se escala.
9. **Doble identidad de módulos** (`datasources` vs `tools.datasources`): ver D1; mitigado con
   normalización por dict.
10. **Sensibilidad y contratos.** En una fuente `sensitive` RANGE/DOMAIN/DATE-RANGE quedan siempre
    WARN (no hay valores persistidos): es una consecuencia declarada, no un fallo.
11. **Dtype/tipo sobre muestra.** `ds_profile` clasifica el dtype sobre los valores de la muestra en
    modo muestreado (`column_stats.py:258`); la `type_family` no es más exacta que eso. No se
    modela `exactness` para el tipo en v0.8.
12. **Scope creep de facetas.** Cada faceta nueva exige un consumidor en un contrato v0.7; sin
    consumidor no entra.

# Spec — 20260922-data-contract-validation

## Requisitos

- **R1 — Módulo y frontera de imports**: existe `tools/datacontracts/validation.py`. Importa
  únicamente: stdlib (`__future__`, `json`, `pathlib`, `typing`, más lo estrictamente necesario),
  `dsguard.checks` (vía `sys.path.insert` al directorio `tools/`, mismo patrón que
  `tools/reporting/validation.py:64-69`), `ds_profile.holdout_guard` (SOLO ese módulo — nunca
  `ds_profile.report`, `ds_profile.column_stats`, `ds_profile.fingerprint`, `ds_profile.sampling`,
  `ds_profile.quality_flags`, `ds_profile.schema`, `ds_profile.io_readers`, ni el paquete completo
  `ds_profile` sin calificar) y `tools.datacontracts.core` (sibling). No importa pandas, numpy, ni
  ningún otro paquete de `tools/`. `core.py` de Change 0 permanece sin modificar (ni una línea).

- **R2 — Códigos de check (registro único, sin duplicados)**: constante de módulo `CODES` con
  exactamente estos 14 códigos, cada uno documentado con su significado y su severidad
  por defecto (cuando no proviene de `Constraint.severity`):
  - `CONTRACT-INPUT` (`technical_error`): `contract` no es una instancia de `DataContract`, o
    `profile` (en `validate_contract`) no es un `dict`.
  - `CONTRACT-EVIDENCE-MISSING` (`technical_error`): perfil inaccesible por holdout, ausente,
    ilegible, JSON inválido, no es `dict`, o le faltan las claves de forma mínima
    (`schema`, `columnas_detalle`, `sampling`, `filas`, cada una del tipo esperado). Ver R7.
  - `CONTRACT-FIELD-MISSING` (`FAIL`): `ContractField.required=True` cuyo `name` no está en
    `profile["schema"]`.
  - `CONTRACT-FIELD-UNEXPECTED` (`WARN`, siempre — política uniforme, ver R8): columna de
    `profile["schema"]` sin `ContractField` declarado en el contrato.
  - `CONTRACT-TYPE-MISMATCH` (`FAIL`, o `N/A` si `type_family == "unknown"`): dtype observado de
    `ds_profile` no pertenece al conjunto esperado para `ContractField.type_family` (bridge, R9).
  - `CONTRACT-NULLABILITY` (`FAIL`): `ContractField.nullable=False` y
    `columnas_detalle[name]["nulls"]["count"] > 0` (siempre verificable, R6).
  - `CONTRACT-KEY` (`FAIL` si viola, `WARN` si no verificable, `N/A` si `keys == ()`): unicidad de
    `DataContract.keys` (R11).
  - `CONTRACT-NOT-NULL-EXPECTATION` (severidad = `Constraint.severity`): `constraint_type ==
    "not_null"`, capa de expectation independiente de `ContractField.nullable` (R10.1).
  - `CONTRACT-UNIQUENESS` (severidad = `Constraint.severity`, o `WARN` si no verificable):
    `constraint_type == "unique"` (R10.2).
  - `CONTRACT-DOMAIN` (severidad = `Constraint.severity`, o `WARN` si no verificable):
    `constraint_type == "allowed_values"` (R10.3).
  - `CONTRACT-RANGE` (severidad = `Constraint.severity`, o `N/A` si el dtype no es numérico):
    `constraint_type ∈ {"min_value", "max_value"}` (R10.4).
  - `CONTRACT-LENGTH` (siempre `WARN`, no verificable con este perfil): `constraint_type ∈
    {"min_length", "max_length"}` (R10.5).
  - `CONTRACT-DATE-RANGE` (severidad = `Constraint.severity`, `WARN` si no parseable, `N/A` si el
    dtype no es `"fecha"`): `constraint_type ∈ {"date_min", "date_max"}` (R10.6).
  - `CONTRACT-INVARIANT` (siempre `WARN`, declarativo no ejecutable por diseño de Change 0):
    `constraint_type == "invariant"` (R10.7).

- **R3 — `validate_contract(contract: DataContract, profile: dict) -> list`**: función PURA (sin
  I/O, sin guard, sin `Path`). No lanza: cualquier excepción inesperada de una regla individual se
  convierte en `CheckResult(FAIL, "<código-base>-EXCEPCION", ..., kind="technical_error")`, mismo
  patrón que `checks.resultado_de_excepcion`/`tools/reporting/validation.py:169-187`. Devuelve, en
  orden fijo: primero el/los resultado(s) de `CONTRACT-INPUT`/`CONTRACT-EVIDENCE-MISSING` si
  aplica (y CORTA ahí, sin evaluar nada más — mismo patrón de corte temprano que
  `tools/reporting/validation.py:1023-1026` para el manifest ausente); si el gate de evidencia
  pasa, evalúa en este orden: `CONTRACT-FIELD-MISSING`, `CONTRACT-FIELD-UNEXPECTED`,
  `CONTRACT-TYPE-MISMATCH`, `CONTRACT-NULLABILITY`, `CONTRACT-KEY`, y luego una entrada por cada
  `Constraint` del contrato (en el orden de `contract.constraints`, código según su
  `constraint_type` según R2). Cada regla sin violaciones emite exactamente un `PASS`/`N/A`
  (nunca cero resultados); cada regla con violaciones emite una entrada por violación (mismo
  patrón `_resumir` de `tools/reporting/validation.py:190-194`). Ningún `message`/`detail` de
  ningún `CheckResult` contiene `profile.get("dataset_path")` ni ninguna ruta absoluta local
  (privacidad, ver `docs/roadmap/v0.7.md:318-319`); los `subject` usan nombres de campo/
  `constraint_id`, nunca rutas de archivo.

- **R4 — `validate_contract_against_profile_file(contract: DataContract, profile_path,
  repo_root) -> list`**: puerta con I/O. Orden: (1) `ds_profile.holdout_guard.verificar_permitido
  (profile_path, repo_root)` — si deniega, UN `CheckResult(FAIL, "CONTRACT-EVIDENCE-MISSING", ...,
  kind="technical_error")` con el motivo del guard en `detail`, y CORTA (nunca abre el archivo);
  (2) si el archivo no existe (`Path.exists()`) o no es un archivo regular, mismo código, corta;
  (3) lee los bytes, `json.loads`; un `json.JSONDecodeError` o un resultado no-`dict` produce el
  mismo código, corta; (4) si todo lo anterior pasa, delega en `validate_contract(contract,
  perfil_dict)` y devuelve su resultado tal cual (sin agregar nada). Nunca lanza (mismo `try/except`
  envolvente que `tools/reporting/validation.py:1045-1053`).

- **R5 — Gate de evidencia (`CONTRACT-EVIDENCE-MISSING` dentro de `validate_contract`)**: dado un
  `profile` que SÍ es `dict` (llegado por cualquier vía — directo a `validate_contract` o vía
  `validate_contract_against_profile_file`), se considera inválido y corta con
  `CONTRACT-EVIDENCE-MISSING` si falta cualquiera de: `profile["schema"]` (debe ser `dict`),
  `profile["columnas_detalle"]` (debe ser `dict`), `profile["sampling"]` (debe ser `dict` con
  `"activo"` bool), `profile["filas"]` (debe ser `int >= 0`). No exige ningún otro campo de
  `profile.json` (p. ej. `fingerprint`, `dataset_path`, `created_utc` pueden faltar sin que el gate
  falle — este Change no los usa).

- **R6 — Bridge `type_family → dtype` de `ds_profile`**: constante de módulo
  `_DTYPE_ESPERADO_POR_FAMILIA` — `"string"→{"texto"}`, `"integer"→{"entero"}`,
  `"float"→{"flotante"}`, `"boolean"→{"booleano"}`, `"date"→{"fecha"}`, `"datetime"→{"fecha"}`,
  `"unknown"→frozenset()` (sin mapeo). `CONTRACT-TYPE-MISMATCH`: para cada `ContractField` presente
  en `profile["schema"]` (si no está presente, ya lo cubrió `CONTRACT-FIELD-MISSING`/no aplica si
  `required=False` y ausente), si `type_family == "unknown"` → `N/A` ("familia sin mapeo declarado,
  no verificable por diseño"); si no, compara `profile["columnas_detalle"][name]["dtype"]` contra
  el set esperado — no pertenece → `FAIL`; pertenece → `PASS`. Esta comparación NO depende de
  `sampling.activo` (`dtype` se deriva de `clasificar_dtype`, que corre sobre `valores_orden`, pero
  el propio `ds_profile` no marca `dtype` como aproximado — se documenta la limitación en
  `design.md`: bajo muestreo extremo el `dtype` observado podría diferir del real si la muestra no
  es representativa; este Change confía en el `dtype` que `ds_profile` ya declaró, sin
  recalcularlo).

- **R7 — Nullability y rango/fecha son exactos SIEMPRE (verificado en `ds_profile`, no asumido)**:
  `columnas_detalle[name]["nulls"]["count"]`, `["min"]`, `["max"]`, `["fecha_min"]`,
  `["fecha_max"]` se acumulan sobre TODAS las filas (`AcumuladorColumna.observar`, llamado en cada
  fila del loop de `generar_perfil` sin importar `modo_muestreado`,
  `tools/ds_profile/report.py:151-170`, `tools/ds_profile/column_stats.py:172-196`) — por lo tanto
  `CONTRACT-NULLABILITY`, `CONTRACT-RANGE` y `CONTRACT-DATE-RANGE` se evalúan como `PASS`/`FAIL`
  determinista SIEMPRE que la columna tenga el dtype esperado, sin condicionar a
  `sampling.activo`. Los campos que sí dependen de la muestra bajo `sampling.activo=true`
  (`unique.count`, `top_valores`, `mediana`, `cuantiles`) están marcados por el propio `ds_profile`
  con su campo `exactitud`/`exactitud_estadisticos` == `"muestreada"` — este Change usa esa marca,
  nunca `sampling.activo` a nivel de perfil completo, para decidir verificabilidad campo por campo.

- **R8 — `CONTRACT-FIELD-UNEXPECTED`, política uniforme `WARN`**: toda columna de
  `profile["schema"]` cuyo nombre no tiene un `ContractField` en `contract.fields` produce una
  entrada `WARN` (nunca `FAIL`, sin excepción por `dataset_role`). `DataContract` no declara ningún
  campo `allow_extra_fields`; esta política es una decisión uniforme de este Change, documentada
  como punto a confirmar por el Lead (ver `design.md`).

- **R9 — `CONTRACT-FIELD-MISSING`**: para cada `ContractField` con `required=True`, si `name` no
  está en `profile["schema"]` → `FAIL`, `subject=name`. Campos con `required=False` ausentes del
  perfil no producen ningún resultado de este código (ni siquiera `N/A` — no son parte de la
  violación ni de la evidencia; documentado así para no inflar la lista de resultados con
  "ausencias esperadas").

- **R10 — Evaluación por `constraint_type`** (una entrada de resultado por `Constraint`, código
  según R2, mensaje siempre referencia `constraint_id` y `field`, nunca valores crudos de datos
  del dataset más allá de lo estrictamente necesario para explicar la violación — p. ej. el valor
  mínimo/máximo observado SÍ puede citarse, un valor de texto libre de `top_valores` también, pero
  nunca una fila completa):
  1. **`not_null`**: `field` no puede ser `None` (garantizado por Change 0: `Constraint.field` es
     obligatorio semánticamente para este tipo, aunque el core no lo fuerza — si `field is None`,
     este Change trata la constraint como no aplicable a ninguna columna concreta y emite `N/A`
     "constraint de alcance dataset, no de columna, no evaluable como not_null"). Si `field` no es
     `None`: viola si `columnas_detalle[field]["nulls"]["count"] > 0` → severidad de
     `constraint.severity`; si no viola → `PASS`. Si `field` no está en `profile["schema"]` (campo
     requerido ausente ya cubierto por `CONTRACT-FIELD-MISSING`, o campo opcional ausente) →
     `WARN` "no verificable: la columna no está presente en el perfil".
  2. **`unique`**: campo(s) objetivo = `params.get("fields")` si está presente (unicidad
     compuesta), si no, `[field]` (si `field is None` y no hay `params["fields"]` → `WARN` "no
     verificable: constraint sin campo(s) objetivo"). Si hay más de un campo objetivo (unicidad
     compuesta) → SIEMPRE `WARN` "no verificable: `ds_profile` no calcula unicidad conjunta entre
     columnas, solo cardinalidad por columna" (nunca se intenta aproximar). Si hay exactamente un
     campo objetivo `c`: sea `no_nulos = profile["filas"] - columnas_detalle[c]["nulls"]["count"]`
     y `distintos = columnas_detalle[c]["unique"]["count"]`. Si
     `columnas_detalle[c]["unique"]["exactitud"] == "exacta"`: `distintos < no_nulos` → violación
     (severidad de `constraint.severity`); `distintos == no_nulos` → `PASS`. Si `["exactitud"] ==
     "muestreada"`: el criterio NO es una longitud de muestra reconstruida (`profile.json` no
     persiste el tamaño de la muestra NO NULA de una columna concreta: `sampling.tamano_muestra` es
     el tamaño de la muestra de FILAS completas, no de valores no nulos de una columna dada) — en su
     lugar, la evidencia usada es directa y siempre disponible: si algún
     `columnas_detalle[c]["top_valores"][i]["frecuencia"] > 1` → violación asertable igual
     (severidad de `constraint.severity`) — un `Counter` no puede reportar frecuencia > 1 sin que el
     valor haya aparecido más de una vez en los datos vistos, así que es evidencia real e
     inequívoca de un valor repetido observado dentro de la muestra, sin importar si `top_valores`
     está truncado a `top_n`. Si ninguna frecuencia de `top_valores` es > 1 → `WARN` "no verificable
     como cumplimiento bajo muestreo: la muestra no evidenció duplicados, pero no cubre todas las
     filas" (la ausencia de frecuencia > 1 en `top_valores` NUNCA se interpreta como evidencia de
     `PASS`: podría haber un duplicado fuera de las top-N filas más frecuentes — más conservador que
     el criterio de longitud de muestra, y cumple R12 igual). Mismo criterio para `CONTRACT-KEY`
     (R11) con key simple bajo muestreo.
  3. **`allowed_values`**: sea `valores_permitidos = set(params["values"])`,
     `observados = {tv["valor"] for tv in columnas_detalle[field]["top_valores"]}` (comparación
     por representación de texto, mismo criterio que `ds_profile` usa internamente para
     `top_valores` — `_texto(v)`, ver `design.md`). Si algún valor de `observados` no está en
     `valores_permitidos` (comparado como texto) → violación (severidad de `constraint.severity`),
     una entrada por valor infractor, citando el valor y su frecuencia observada. Si ningún valor
     de `observados` viola Y (`columnas_detalle[field]["unique"]["exactitud"] == "exacta"` Y
     `columnas_detalle[field]["unique"]["count"] <= len(top_valores)`, es decir `top_valores`
     enumera TODOS los valores distintos) → `PASS`. Si ningún valor de `observados` viola pero esa
     condición de exhaustividad no se cumple → `WARN` "no verificable como cumplimiento: el
     dominio no está evidenciado por completo (`top_valores` no cubre todos los valores
     distintos)". `field is None` → `N/A` "constraint de alcance dataset no aplicable a
     allowed_values" (este `constraint_type` siempre requiere `field` para tener sentido).
  4. **`min_value` / `max_value`**: solo si `columnas_detalle[field]["dtype"] ∈ {"entero",
     "flotante"}` — si no, `N/A` "no aplica: la columna no es numérica según el perfil". Si es
     numérica: compara `params["value"]` contra `columnas_detalle[field]["min"]` (para
     `min_value`, viola si `min_observado < params["value"]`) o `["max"]` (para `max_value`, viola
     si `max_observado > params["value"]`) — severidad de `constraint.severity` si viola, `PASS`
     si no. Siempre determinista (R7): nunca `WARN` por `sampling.activo`.
  5. **`min_length` / `max_length`**: SIEMPRE `WARN`, código `CONTRACT-LENGTH`, mensaje "no
     verificable: `ds_profile` no calcula estadísticas de longitud de texto" — sin excepción, sin
     importar dtype ni sampling (limitación de evidencia permanente para este Change, ver
     `design.md`).
  6. **`date_min` / `date_max`**: solo si `columnas_detalle[field]["dtype"] == "fecha"` — si no,
     `N/A` "no aplica: la columna no es de tipo fecha según el perfil". Si es fecha: intenta
     `datetime.fromisoformat` sobre `params["value"]` Y sobre `columnas_detalle[field]
     ["fecha_min"/"fecha_max"]` (ambos strings ISO); si CUALQUIERA de los dos falla a parsear →
     `WARN` "no verificable: formato de fecha no comparable" (nunca lanza `ValueError`). Si ambos
     parsean: mismo criterio comparativo que 4 (determinista, R7).
  7. **`invariant`**: SIEMPRE `WARN`, código `CONTRACT-INVARIANT`, mensaje "invariante declarativo
     (`params['note']`), no evaluable automáticamente: Change 0 no admite un lenguaje de
     expresiones ejecutable por diseño" — sin excepción.

- **R11 — `CONTRACT-KEY` (unicidad de `DataContract.keys`)**: si `contract.keys == ()` → `N/A`
  "sin key declarada". Si `len(contract.keys) > 1` (compuesta) → SIEMPRE `WARN` "no verificable:
  `ds_profile` no calcula unicidad conjunta entre columnas" (mismo motivo que R10.2). Si
  `len(contract.keys) == 1`: mismo criterio de evaluación que `unique` de un solo campo (R10.2),
  con severidad fija `FAIL` (no hay `Constraint.severity` asociada a `keys` — es una propiedad
  estructural de `DataContract`, no una `Constraint`; se documenta este default en `design.md`,
  mismo criterio que `CONTRACT-NULLABILITY`/`CONTRACT-FIELD-MISSING`, que tampoco tienen severidad
  declarable porque son de la capa schema/structure).

- **R12 — Nunca `PASS` por falta de evidencia**: para cualquier código de R2, un resultado `PASS`
  solo se emite cuando la evidencia disponible permite AFIRMAR positivamente el cumplimiento (ver
  cada regla de R10/R11); toda ambigüedad se resuelve a `WARN` (aplicable, no verificable) o `N/A`
  (no aplica). Criterio de aceptación transversal: ningún test de `test_validation.py` construye un
  caso donde la única evidencia disponible sea parcial/muestreada y el resultado esperado sea
  `PASS`, salvo los casos explícitamente marcados como "evidencia exacta" en el propio test.

- **R13 — `technical_error` separado, vocabulario compartido**: todo `CheckResult` de
  `CONTRACT-INPUT`/`CONTRACT-EVIDENCE-MISSING` usa `kind="technical_error"`
  (`dsguard.checks.KIND_TECHNICAL_ERROR`); todos los demás usan `kind="check"` (default). Ningún
  agregado de este Change mezcla ambos conteos (decisión 4 del roadmap) — este Change no calcula
  ningún agregado propio (eso es de un consumidor futuro, p. ej. Change 4/`status`), solo produce
  la `list[CheckResult]` con el `kind` correcto en cada entrada.

- **R14 — Tests deterministas, sin datos reales**: `tools/datacontracts/tests/test_validation.py`
  (unittest) usa exclusivamente `DataContract`/`profile` sintéticos construidos en el propio test
  (diccionarios Python literales con la forma exacta de `profile.json`, nunca un archivo real ni
  `ds_profile.run`); sin I/O de red, sin pandas/numpy, sin aleatoriedad. Cubre, como mínimo: los 14
  códigos de R2 en al menos un caso `PASS`/`N-A`/`WARN` y uno con violación (`FAIL`/`WARN` según
  corresponda); el corte temprano de `CONTRACT-EVIDENCE-MISSING` (perfil `None`, no-`dict`, sin
  `"schema"`, sin `"columnas_detalle"`, sin `"sampling"`, `sampling` sin `"activo"` bool, sin
  `"filas"`); los tres casos de exactitud de `unique` (exacta sin duplicados, exacta con
  duplicados, muestreada con y sin duplicados en la muestra); el caso de unicidad compuesta
  (`WARN` siempre); el bridge de `type_family` (los 7 valores, incluido `"unknown"→N/A`); privacidad
  (`profile["dataset_path"]` con una ruta absoluta local, verificar que NINGÚN `CheckResult`
  producido contiene esa cadena en `message`/`detail`/`subject`).
  `tools/tests/test_v07_validation_neutrality.py` (patrón `ast`, R1): imports de `validation.py`
  pertenecen al set permitido; una violación de prueba (`import pandas`, `from ds_profile import
  report`, `from ds_profile.column_stats import clasificar_dtype`) se detecta.

- **R15 — Arquitectura y frontera**: `ARCHITECTURE.md` §2.1 tiene una fila nueva para
  `tools/datacontracts/validation.py` (texto exacto en `design.md`); §3 regla 7 se amplía (texto
  exacto en `design.md`) para documentar el ejercicio concreto de la cláusula de extensión
  aditiva (`ds_profile.holdout_guard`, solo ese módulo). `tools/datacontracts/validation.py` se
  agrega a `MODULOS_CORE` de `tools/tests/test_architecture_boundaries.py`. Ningún módulo existente
  fuera de `tools/datacontracts` importa `validation.py` (verificado por
  `test_v07_validation_neutrality.py`, extendiendo la lista `PAQUETES_SIN_DATACONTRACTS` ya
  existente en `test_v07_core_neutrality.py` o reusándola).

- **R16 — Backward compatibility**: `tools/datacontracts/core.py` no cambia (ni una línea, ni su
  `content_sha256()` de ningún contrato existente). Las únicas modificaciones a archivos
  preexistentes son aditivas: una fila y una ampliación de texto en `ARCHITECTURE.md`, una línea en
  `MODULOS_CORE`, y (al cierre) el tildado en `docs/roadmap/v0.7.md`.

- **R17 — Roadmap**: al cerrar el Change (última invocación) se tilda `[x] Change 1` en
  `docs/roadmap/v0.7.md`. Nada más del roadmap cambia; Changes 2-5 no se tocan.

## Criterios de aceptación

**R1 — frontera de imports**
- Given `tools/datacontracts/validation.py`, When `test_v07_validation_neutrality.py` recorre su
  AST, Then todo import pertenece a `{stdlib permitida, dsguard.checks, ds_profile.holdout_guard,
  tools.datacontracts.core}` y ninguno referencia `ds_profile.report`, `.column_stats`,
  `.fingerprint`, `.sampling`, `.quality_flags`, `.schema`, `.io_readers`, pandas, numpy.
- Given `core.py` (Change 0), When se recorre su AST de nuevo, Then sigue sin ningún import fuera
  de `{__future__, dataclasses, hashlib, json, re, typing}` (regresión, ya cubierta por
  `test_v07_core_neutrality.py`, no debe romperse).

**R2/R3 — códigos y `validate_contract`**
- Given un `DataContract` mínimo válido y un `profile` mínimo válido sin ninguna violación posible
  (todas las columnas declaradas presentes con el dtype esperado, sin nulos en campos no
  nullable), Then `validate_contract` devuelve solo `PASS`/`N/A` (ningún `FAIL`/`WARN`), un
  resultado por código aplicable.
- Given `contract` = `"no soy un DataContract"`, Then `validate_contract` devuelve exactamente un
  `CheckResult(FAIL, "CONTRACT-INPUT", ..., kind="technical_error")` y nada más.
- Given `profile` = `[]` (no es `dict`), Then exactamente un `CheckResult(FAIL,
  "CONTRACT-EVIDENCE-MISSING", ..., kind="technical_error")` y nada más.
- Given una regla individual que lanza una excepción inesperada (simulada monkeypatcheando una
  función interna en el test), Then `validate_contract` no propaga la excepción: produce un
  `FAIL`/`technical_error` con código `<base>-EXCEPCION` y sigue evaluando el resto.

**R4 — `validate_contract_against_profile_file`**
- Given una ruta bajo un holdout declarado en un `guardrails.json` de fixture (sin excepción de
  lectura vigente), Then devuelve exactamente un `CONTRACT-EVIDENCE-MISSING`/`technical_error` con
  el motivo del guard en `detail`, y el archivo NUNCA se abre (verificable con un mock/spy que
  falla si se llama `open`/`Path.read_*` sobre esa ruta).
- Given una ruta que no existe, Then mismo código, sin excepción.
- Given un archivo con JSON inválido o con un JSON válido que no es `dict` (p. ej. una lista),
  Then mismo código, sin excepción.
- Given un `profile.json` válido y permitido, Then el resultado es idéntico a llamar
  `validate_contract(contract, json.loads(bytes))` directamente (mismo `list[CheckResult]`, campo
  a campo).

**R5/R6/R7 — gate de evidencia, bridge y exactitud**
- Given un `profile` `dict` al que le falta `"schema"`, `"columnas_detalle"`, `"sampling"`, o
  `"filas"` (cuatro casos, uno por campo faltante), Then cada uno produce
  `CONTRACT-EVIDENCE-MISSING` y corta (ningún otro código en el resultado).
- Given `profile["sampling"] = {"activo": "si"}` (no bool), Then `CONTRACT-EVIDENCE-MISSING`.
- Given un `ContractField(type_family="unknown")`, Then `CONTRACT-TYPE-MISMATCH` es `N/A` sin
  importar el `dtype` observado.
- Given `type_family="integer"` y `dtype` observado `"entero"`, Then `PASS`; dado `dtype`
  observado `"flotante"`, Then `FAIL`.
- Given un campo `nullable=False` con `nulls.count=0` bajo `sampling.activo=True`, Then
  `CONTRACT-NULLABILITY` es `PASS` (determinista pese al muestreo, por R7); dado `nulls.count=3`
  bajo el mismo `sampling.activo=True`, Then `FAIL` (nunca `WARN`).
- Given una `Constraint min_value` sobre una columna con `dtype="entero"`, `min=5`,
  `sampling.activo=True`, y `params["value"]=10` (o sea el mínimo observado 5 < 10, viola), Then
  `FAIL` determinista (nunca `WARN` por el muestreo).

**R8/R9 — campo inesperado / faltante**
- Given una columna en `profile["schema"]` sin `ContractField` correspondiente, Then
  `CONTRACT-FIELD-UNEXPECTED` es `WARN` (nunca `FAIL`) sin importar `dataset_role`.
- Given un `ContractField(required=True)` ausente de `profile["schema"]`, Then
  `CONTRACT-FIELD-MISSING` `FAIL`; dado `required=False` y ausente, Then ningún resultado de ese
  código para ese campo.

**R10 — por `constraint_type`**
- Given `constraint_type="unique"`, `field="id"`, `unique.exactitud="exacta"`,
  `unique.count == filas - nulls.count`, Then `PASS`; dado `unique.count <
  filas - nulls.count`, Then severidad de `constraint.severity`.
- Given `constraint_type="unique"`, `unique.exactitud="muestreada"`, ningún `top_valores[i]
  ["frecuencia"] > 1`, Then `WARN`; dado algún `top_valores[i]["frecuencia"] > 1` (evidencia real de
  un valor repetido dentro de la muestra), Then severidad de `constraint.severity` (violación
  asertable pese al muestreo).
- Given `constraint_type="unique"` con `params={"fields": ["a", "b"]}`, Then siempre `WARN`
  (unicidad compuesta no verificable), sin importar exactitud.
- Given `constraint_type="allowed_values"`, `params={"values": ["a", "b"]}`,
  `top_valores=[{"valor": "c", ...}]`, Then `FAIL`/`WARN` según `constraint.severity` (violación:
  "c" no permitido); dado `top_valores=[{"valor": "a", ...}]` y `unique.count=1 <= len(top_valores)`
  con `exactitud="exacta"`, Then `PASS`; dado el mismo `top_valores` pero `exactitud="muestreada"`,
  Then `WARN` (no verificable como cumplimiento).
- Given `constraint_type="min_length"` (cualquier valor de `params`, cualquier dtype), Then
  siempre `WARN` con el código `CONTRACT-LENGTH`.
- Given `constraint_type="date_min"` sobre una columna `dtype="fecha"` con
  `fecha_min="2019-01-01T00:00:00"` (mínimo observado) y `params={"value": "2020-01-01"}` (mínimo
  declarado): `date_min` declara la fecha más temprana permitida, así que un `fecha_min` observado
  ANTERIOR a `params["value"]` es la violación (hay filas más viejas que lo permitido) — Then
  `FAIL`/`WARN` según `constraint.severity`; dado un `params["value"]` no parseable
  (`"no-es-fecha"`), Then `WARN`.
- Given `constraint_type="date_min"`/`"date_max"` sobre una columna `dtype="texto"`, Then `N/A`.
- Given `constraint_type="invariant"`, Then siempre `WARN` con código `CONTRACT-INVARIANT`, sin
  importar `params`.
- Given `constraint_type="not_null"` con `field=None`, Then `N/A`; dado `field` presente en el
  perfil con `nulls.count=0`, Then `PASS`; dado `nulls.count>0`, Then severidad de
  `constraint.severity` (código `CONTRACT-NOT-NULL-EXPECTATION`, DISTINTO de
  `CONTRACT-NULLABILITY`, que evalúa `ContractField.nullable`, no esta constraint).

**R11 — `CONTRACT-KEY`**
- Given `contract.keys == ()`, Then `N/A`.
- Given `contract.keys == ("a", "b")`, Then siempre `WARN`.
- Given `contract.keys == ("id",)` con `unique.count == filas - nulls.count` y
  `exactitud="exacta"`, Then `PASS`; dado `unique.count < filas - nulls.count`, Then `FAIL` (fijo,
  sin `Constraint.severity` involucrada).

**R12 — nunca `PASS` inventado**
- Given cualquier combinación de `sampling.activo=True` y `exactitud="muestreada"` sin evidencia
  suficiente (ver reglas anteriores), Then el resultado nunca es `PASS` (test de propiedad simple:
  recorrer la matriz de casos "muestreado sin duplicados/violación observada" para `unique` y
  `allowed_values`, afirmar `status != "PASS"` en cada uno).

**R13 — `technical_error`**
- Given los 14 códigos de R2, Then únicamente `CONTRACT-INPUT` y `CONTRACT-EVIDENCE-MISSING` (y
  cualquier `<código>-EXCEPCION` de una excepción inesperada) tienen `kind="technical_error"`; el
  resto siempre `kind="check"`.

**R14 — privacidad**
- Given un `profile["dataset_path"] = "C:\\Users\\alguien\\datos_privados.csv"` en el fixture,
  Then ningún `message`/`detail`/`subject` de ningún `CheckResult` devuelto por `validate_contract`
  contiene la substring `"datos_privados"` ni `"C:\\Users"`.

**R15/R16 — arquitectura y compatibilidad**
- Given `MODULOS_CORE` de `test_architecture_boundaries.py`, Then contiene
  `tools/datacontracts/validation.py` y el test sigue verde.
- Given `git diff` del Change (invocación de implementación), Then los archivos preexistentes
  modificados son solo `ARCHITECTURE.md`, `test_architecture_boundaries.py` (línea agregada) y
  `docs/roadmap/v0.7.md` (al cierre) — `tools/datacontracts/core.py` NO aparece en el diff.

**R17 — roadmap**
- Given `docs/roadmap/v0.7.md` al cierre, Then `[x] Change 1` y ningún otro ítem del roadmap
  cambia.

## Unidad de análisis / grain (condicional — data_understanding, feature_engineering, modeling)
No aplica: evaluación de infraestructura del harness (contrato de datos vs. perfil), sin dataset ni
unidad de análisis de negocio.

## Cutoff / information boundary (condicional — feature_engineering, data_preparation, modeling)
No aplica.

## Baseline (condicional — modeling)
No aplica.

## Métrica primaria (condicional — modeling, evaluation)
No aplica.

## Métricas secundarias (opcional)
No aplica.

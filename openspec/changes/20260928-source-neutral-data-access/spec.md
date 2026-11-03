# Especificación — 20260928-source-neutral-data-access

Notación: cada requisito `Rn` tiene un criterio de aceptación verificable (test o inspección
nombrada). "Falla" = devuelve `CheckResult` con status `FAIL`/`technical_error` según se indique; los
componentes públicos nunca lanzan hacia el llamador salvo donde se diga `SourceError`.

## 1. Paquete y dependencias

**R1 — Paquete `tools/datasources/`.** Módulos: `core.py`, `scan.py`, `registry.py`, `runtime.py`,
`profile_bridge.py`, `file_observer.py`, `__init__.py`.
- `core.py`: solo stdlib (`dataclasses`, `typing`, `re`, `json`, `hashlib`, `unicodedata`,
  `__future__`); sin `os`, `pathlib`, `sys`, `importlib`, sin imports de hermanos ni `tools.*`.
- `scan.py`, `registry.py`, `profile_bridge.py`: puros sobre dicts (sin I/O); pueden importar
  `core` (relativo). `registry.py` puede importar `scan`.
- `runtime.py`: I/O e `importlib`; puede importar `dsguard.checks` (patrón de
  `datacontracts/validation.py:71`) y los módulos puros propios.
- `file_observer.py`: importa `ds_profile` de forma perezosa (dentro de funciones).
- Aceptación: `tools/tests/test_v08_datasources_neutrality.py` (patrón `ast` de
  `test_v07_validation_neutrality.py`/`test_v08_autonomy_neutrality.py`) afirma estos conjuntos de
  imports por módulo.

**R2 — Dirección de dependencias.** Ninguno de `dsguard`, `ds_profile`, `dsimpact`, `reporting`,
`providers`, `routing`, `fallback`, `harmessi_bench`, `modelquality`, `qualityevidence`,
`autonomy` importa `datasources`. `datasources` no importa `autonomy` (el control de acceso se
inyecta, R25). Única excepción: `tools.datacontracts.validation` (y `legacy_wording.py` si lo
necesitara) importa `datasources.core`/`profile_bridge`; nada más en `datacontracts`.
- Aceptación: el test de R1 recorre por `ast` todos los `.py` de esos paquetes y falla ante
  cualquier import inverso; la excepción está enumerada por nombre de archivo.

**R3 — Neutralidad tecnológica del core.** `core.py` no contiene ramas (`if`/`match`/comparaciones)
sobre `source_kind` ni sobre literales de tecnología (`sql`, `parquet`, `csv`, `postgres`,
`snowflake`, `bigquery`, `s3`, `http`, ...). `source_kind` es una etiqueta informativa acotada
(`^[a-z0-9][a-z0-9_-]{0,31}$`) que solo se copia y serializa.
- Aceptación: test `ast` sobre `core.py` (comparaciones y `in` con constantes de esa lista) y test
  de comportamiento: la misma observación con `source_kind` distinto produce el mismo resultado de
  validación de contrato.

## 2. Tipos y serialización

**R4 — `SourceRef`** (frozen): `source_id`, `role`, `observer`, `access_mode`, `sensitivity`,
`config_ref` (opcional), `options`, extensiones `x_*`.
- `source_id`: `SOURCE_ID_PATTERN = r"[a-z0-9][a-z0-9_-]{0,63}"` con `fullmatch`. Constante
  duplicada respecto de `tools/autonomy/core.py:332` (paquetes independientes).
- `role`: mismo patrón que `source_id` (p. ej. `raw_table`, `feature_table`).
- `observer`: `módulo:callable`, regex `^[A-Za-z_][A-Za-z0-9_.]*:[A-Za-z_][A-Za-z0-9_]*$`.
- `access_mode`: solo `read`. `write` es vocabulario reservado: un registro que lo declara es
  inválido con `SOURCE-ACCESS-MODE-RESERVED`. Cualquier otro valor: `SOURCE-REGISTRY-INVALID`.
- `sensitivity`: `public|internal|sensitive`. "sealed" NO es un valor válido (es policy humana de
  Change 0).
- `config_ref`: `env:NOMBRE` o `ref:NOMBRE` (`NOMBRE` = `[A-Za-z_][A-Za-z0-9_]{0,63}`); referencia
  opaca, nunca un valor.
- `options`: objeto JSON no secreto, opaco para Harmessi; profundidad máxima 4, máximo 64 claves
  totales, cadenas de hasta 512 caracteres, sin `NaN`/`Infinity`; se escanea (R19).
- Aceptación: tests parametrizados válido/inválido por campo; `source_id` de los ejemplos del autor
  (`dbo.Clientes.Productores`, `project.dataset.customers`, `/v2/customers`,
  `data/raw/customers.parquet`) son rechazados con `SOURCE-ID-INVALID`; `customers` es aceptado.

**R5 — `SourceObservation`** (`schema_version` 1). Claves de primer nivel en orden fijo:
`schema_version`, `source_id`, `provenance`, `dataset`, `fields`, `omitted_facets`.
- `dataset`: `row_count`, `fingerprint {algorithm, value}`, `snapshot {as_of, cutoff}`,
  `sampling {active, method, sample_size, seed}`. Cada faceta de dataset observada es
  `{"value": ..., "exactness": "exact|approximate"}`; una faceta no observada **no se escribe**.
- `fields`: lista ORDENADA (orden de la fuente) de `FieldObservation {name, type_family,
  native_type, facets}`. `native_type` es una etiqueta opaca informativa (el core no ramifica sobre
  ella). Los nombres de campo son únicos.
- `facets` de campo: `null_count`, `distinct_count`, `value_distribution`, `value_range`,
  `time_range`. Formas: `null_count`/`distinct_count` -> `value` entero >= 0; `value_range` y
  `time_range` -> `value {min, max}` (`min`/`max` pueden ser `null` cuando se observó que no hay
  valores no nulos; ver R31); `value_distribution` -> `value` lista de `{value, frequency}` con
  `frequency` entero >= 1, más `complete: bool`.
- `OBSERVED_TYPE_FAMILIES = (string, integer, float, boolean, date, datetime, temporal, unknown)`;
  `temporal` = fecha sin distinguir `date`/`datetime`.
- Aceptación: validación estructural en `from_dict` (lanza `SourceError`); un dict con faceta
  `null_count` ausente no la materializa como 0; ausencia != 0 != vacío (test explícito).

**R6 — `SourceProvenance`.** `source_id`, `observer_id` (`módulo:callable`),
`observer_code_sha256` (R21), `access_mode` efectivo, `source_kind`, `generated_at` (ISO-8601 UTC),
`tool_versions` (dict str->str), `requested_facets` (lista), `unsupported_facets` (lista).
- Aceptación: ningún campo de la observación contiene ruta absoluta, host, DSN ni credencial (R19).

**R7 — Serialización determinista.** `to_dict()` con orden de claves fijo;
`canonical_json()` = `json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=False)` + sin
BOM; el archivo persistido usa `indent=2, sort_keys=True` y un LF final. `content_sha256()` =
sha256 de la forma canónica de `to_dict()` **excluyendo únicamente `provenance.generated_at`**.
- Aceptación: round-trip `from_dict(to_dict())` idéntico; `dumps(loads(bytes)) == bytes` para el
  archivo persistido; dos observaciones que difieren solo en `generated_at` tienen igual
  `content_sha256`; cambiar cualquier otro campo (incluido `observer_code_sha256`) lo cambia.

**R8 — `SourceError`.** Excepción de `core` para construcción/validación de tipos y del bridge. Los
puntos de entrada de `runtime` y del evaluador la convierten en `CheckResult`; no escapa.

**R9 — Registro único de códigos `SOURCE-*`.** `core.py` define `CODES` (tupla) y constantes; ningún
otro módulo declara códigos. Códigos: `SOURCE-REGISTRY-MISSING`, `SOURCE-REGISTRY-INVALID`,
`SOURCE-ID-INVALID`, `SOURCE-ID-DUPLICATE`, `SOURCE-ROLE-INVALID`, `SOURCE-OBSERVER-MALFORMED`,
`SOURCE-OBSERVER-UNRESOLVED`, `SOURCE-ACCESS-MODE-RESERVED`, `SOURCE-SENSITIVITY-INVALID`,
`SOURCE-CONFIG-REF-INVALID`, `SOURCE-OPTIONS-INVALID`, `SOURCE-SECRET-DETECTED`,
`SOURCE-ABSOLUTE-PATH`, `SOURCE-DSN-DETECTED`, `SOURCE-UNKNOWN`, `SOURCE-ACCESS-DENIED`,
`SOURCE-SEALED`, `SOURCE-OBSERVER-ERROR`, `SOURCE-CAPABILITIES-INVALID`,
`SOURCE-FACET-UNSUPPORTED`, `SOURCE-OBSERVATION-INVALID`, `SOURCE-FACET-OMITTED`,
`SOURCE-OBSERVER-CODE-UNHASHABLE`, `SOURCE-PERSIST-ERROR`, `SOURCE-OBSERVATION-STALE`,
`SOURCE-FRESHNESS-UNVERIFIABLE`, `SOURCE-PROFILE-INVALID`.
- Aceptación: test que compara `CODES` con los literales `"SOURCE-..."` hallados por `ast` en el
  paquete (ninguno fuera del registro) y unicidad.

## 3. Capacidades

**R10 — `SourceCapabilities` en dos ejes.**
1. `facets`: mapa faceta -> conjunto no vacío de exactitudes soportadas (`exact`/`approximate`).
   Facetas de dataset: `schema`, `row_count`, `fingerprint`, `snapshot`. Facetas de campo:
   `null_count`, `distinct_count`, `value_distribution`, `value_range`, `time_range`.
2. `operations`: subconjunto de `sample`, `read`, `write` (informativas; el core no las invoca).
`access_ceiling` = `read` (constante). `execute_query` no existe en el vocabulario: una capacidad
con ese nombre (o cualquier faceta/operación desconocida) es `SOURCE-CAPABILITIES-INVALID`.
- Aceptación: tests de validación; test `ast` que afirma que ningún módulo de `datasources` llama
  atributos `read`/`write`/`sample`/`execute_query` sobre un observer.

**R11 — `ObservationRequest`.** `source_id`, `facets` (subconjunto de las declaradas), `exactness`
(`any|exact`), `as_of` opcional (ISO-8601 válido), límites de muestreo opcionales
(`max_rows`, `sample_size`, enteros > 0). Nunca contiene texto de consulta; un campo desconocido es
`SOURCE-OBSERVATION-INVALID`.
- Aceptación: test de rechazo de claves `query`/`sql`/`statement`; el pedido serializa a un dict
  JSON sin objetos de Harmessi.

## 4. Registro

**R12 — Archivo `.harmessi/sources.json`.** `{"schema_version": 1, "sources": [SourceRef...]}`, ids
únicos. Es del proyecto: versionado en git, ausente del manifiesto de instalación y de
`control.json["archivos"]`.
- Aceptación: test de repo/instalación: ninguna entrada de `ds_init/manifest.py` apunta a
  `.harmessi/sources.json`; `sync` no lo crea, modifica ni reporta como drift.

**R13 — `check_registry(repo_root)` estático.** Devuelve `list[CheckResult]`:
- registro ausente -> `SOURCE-REGISTRY-MISSING` (WARN, informativo: "no hay fuentes registradas");
- JSON ilegible o schema inválido -> FAIL `SOURCE-REGISTRY-INVALID` (technical_error si ilegible);
- ids no canónicos / duplicados -> `SOURCE-ID-INVALID` / `SOURCE-ID-DUPLICATE`;
- `observer` mal formado -> `SOURCE-OBSERVER-MALFORMED`;
- módulo del observer resoluble como archivo dentro del repo **sin importarlo**: `a.b` -> `<repo>/a/b.py`
  o `<repo>/a/b/__init__.py`. Si no existe -> WARN `SOURCE-OBSERVER-UNRESOLVED` (el paquete puede
  estar instalado en el `.venv`), nunca error fatal;
- scan de secretos/localizadores sobre todo el registro (R19).
- Aceptación: tests con un módulo señuelo cuyo cuerpo escribe un archivo al importarse: tras
  `check_registry` el archivo no existe (prueba de que no se importa); `sys.modules` no gana el
  módulo del observer.

**R14 — Resolución estática del observer.** `registry.resolve_observer_file(repo_root, ref)`
(puro salvo `Path.exists`, inyectable como `exists_fn`) rechaza componentes con `..`, rutas
absolutas y separadores.

## 5. Observer y runtime

**R15 — Contrato del observer.** El registro apunta a `factory(source_id: str, options: dict) ->
observer`. El observer expone `capabilities() -> dict | SourceCapabilities` y
`observe(request: dict | ObservationRequest) -> dict | SourceObservation`. La frontera es JSON: un
proyecto puede implementar el observer sin importar tipos de Harmessi. Harmessi valida y normaliza.
- Aceptación: observer de prueba en memoria (clase en un módulo de tests, sin archivos ni SQL) que
  devuelve dicts; produce una `SourceObservation` válida.

**R16 — `observe_source(repo_root, source_id, request, access_check)`.** Orden obligatorio:
1. leer/validar registro (R13 sin scan de existencia de módulo); fuente ausente -> `SOURCE-UNKNOWN`;
2. `access_check(source_id, registry_access)` -> `(permitido, motivo)`; denegado ->
   `SOURCE-SEALED` (si el motivo lo indica) o `SOURCE-ACCESS-DENIED`, **antes de importar** el
   observer;
3. `importlib.import_module` + `getattr` de la factory; fallo de import o excepción de factory /
   `capabilities()` / `observe()` -> `technical_error` `SOURCE-OBSERVER-ERROR` (sin traza con rutas
   absolutas en `message`; `detail` con `type(exc).__name__` y mensaje truncado a 300 caracteres tras
   scan R19). Harmessi nunca instala nada;
4. `capabilities()` validadas (R10); inválidas -> `SOURCE-CAPABILITIES-INVALID`;
5. facetas pedidas ∩ declaradas; las no declaradas se listan en `unsupported_facets` y generan
   WARN `SOURCE-FACET-UNSUPPORTED`; nunca se piden al observer;
6. `observe(request)`; resultado normalizado a `SourceObservation` (`SOURCE-OBSERVATION-INVALID` si
   no cumple R5, o si trae facetas no pedidas/no declaradas);
7. inyección de provenance calculada por el runtime (R21) y aplicación de sensibilidad (R22);
8. gate de portabilidad/secretos (R19) sobre la observación completa;
9. persistencia atómica (R23).
Retorna `(SourceObservation | None, list[CheckResult])`; nunca lanza.
- Aceptación: test con un `access_check` espía verifica el orden (el import del módulo señuelo no
  ocurre si `access_check` deniega); test de observer que lanza; test de módulo inexistente.

**R17 — Sin timeout en proceso.** `observe_source` no implementa timeout (M6: en proceso). El
timeout lo aporta el runtime de ejecución del Change 2. Se documenta como límite; un observer
colgado bloquea el proceso que lo invoca.
- Aceptación: `design.md` y la ayuda del CLI (`--help` de `source observe`) lo enuncian; test de
  inspección del texto de ayuda.

**R18 — Exactitud pedida.** Con `exactness == "exact"` solo se aceptan facetas devueltas con
`exactness == "exact"`; una `approximate` devuelta se descarta con WARN `SOURCE-FACET-UNSUPPORTED`
(detalle: `exactness`) y queda en `unsupported_facets`. Con `any` se conserva la exactitud
declarada.

## 6. Secretos y portabilidad

**R19 — `scan.py`.** Funciones puras `scan_secrets(obj, path="$")` y `scan_locators(obj, path="$")`
-> lista de hallazgos `(code, json_pointer, motivo)` sin reproducir el valor sospechoso.
- Secretos: claves cuyo nombre normalizado (casefold, sin `-`/`_`) contiene `password`, `passwd`,
  `pwd`, `token`, `secret`, `apikey`, `accesskey`, `privatekey`, `credential`; valores con forma de
  credencial (prefijos `AKIA`/`ghp_`/`xox`/`sk-`, bloques PEM `-----BEGIN`, JWT
  `eyJ...\..*\..*`, cadenas hex/base64 >= 32 caracteres en claves no listadas como hash/sha) ->
  `SOURCE-SECRET-DETECTED`.
- DSN: `esquema://usuario:clave@host`, `Server=...;Password=...`, `postgres(ql)://`,
  `jdbc:` con credenciales -> `SOURCE-DSN-DETECTED`.
- Localizadores físicos absolutos: `^[A-Za-z]:[\\/]`, `^/` (con al menos un separador adicional),
  `^\\\\` (UNC), `file://` -> `SOURCE-ABSOLUTE-PATH`. Rutas repo-relativas en `options` del registro
  están permitidas; en una **observación** persistida no se admite ningún localizador (ni relativo
  con `..`).
- Es por patrón y best-effort: se declara así en `design.md` y en la ayuda del CLI.
- Aceptación: tabla de casos positivos y negativos (p. ej. `password_env: "DB_PASSWORD"` con clave
  `password_env` se marca; `config_ref: "env:CUSTOMERS_DSN"` no se marca; hash sha256 en
  `fingerprint.value` no se marca; `note: "recuento de tokens"` no se marca por valor).

**R20 — Gate antes de persistir.** El scan R19 (secretos, DSN, rutas absolutas) corre sobre
`observation.to_dict()` completo, incluido `native_type`, `value_distribution` y `provenance`. Un
hallazgo bloquea la persistencia y devuelve `(None, [FAIL SOURCE-*])`. El mensaje del hallazgo
nunca contiene el valor.
- Aceptación: observer de prueba que devuelve un `native_type` con una ruta absoluta y otro con un
  DSN -> no se escribe ningún archivo en `.harmessi/observations/`.

## 7. Provenance, sensibilidad y persistencia

**R21 — Hash del código del observer.** `observer_code_sha256` = sha256 de los bytes del archivo
fuente del módulo del observer (obtenido del módulo importado, `__file__`), tras normalizar
`\r\n`/`\r` a `\n`. Si no hay archivo (módulo sin `__file__`) -> `observer_code_sha256 = null` y WARN
`SOURCE-OBSERVER-CODE-UNHASHABLE`. Lo calcula el runtime; un valor entregado por el observer se
ignora.
- Aceptación: cambiar un byte del módulo cambia el hash; CRLF vs LF del mismo contenido igual hash.

**R22 — Sensibilidad.** Si `sensitivity == "sensitive"`, `value_distribution`, `value_range` y
`time_range` NO se persisten: se eliminan de cada `FieldObservation` y `omitted_facets` registra
`{field, facet, reason: "sensitivity"}` y se emite WARN `SOURCE-FACET-OMITTED`. Nunca se omiten en
silencio. La omisión ocurre en `runtime` antes del hash y de la persistencia; `content_sha256` la
refleja. Para `public`/`internal` no se omite nada.
- Aceptación: test de round-trip con fuente `sensitive` que verifica ausencia de valores y presencia
  de `omitted_facets`; test de que el evaluador sobre esa observación da WARN (no PASS) en
  RANGE/DOMAIN.

**R23 — Persistencia.** `.harmessi/observations/<observation_id>/observation.json`, con
`observation_id = <source_id>__<12 primeros hex de content_sha256>`. Escritura atómica (archivo
temporal en el mismo directorio + `os.replace`). Si el archivo existe con los mismos bytes, la
escritura es idempotente; si existe con otros bytes -> `SOURCE-PERSIST-ERROR`. Sin rutas absolutas
en el contenido. El directorio no está en el manifiesto.
- Aceptación: dos `observe_source` idénticos generan el mismo `observation_id`; no quedan archivos
  temporales tras error simulado de `os.replace`.

## 8. Sellado y control de acceso

**R24 — Composición real en `tools/ds_guard.py`.** `access_check` real (no en `datasources`):
lee `.claude/guardrails.json` con `pathguard.cargar_config` (fail-closed de versión,
`tools/dsguard/pathguard.py:86,115`), parsea con
`tools.autonomy.policy.parse_autonomy_policy(dict, pathguard.POLICY_VERSION_MAX)` y usa
`effective_source_access` / `is_source_sealed` (`policy.py:323,302`).
- `guardrails.json` ilegible o corrupto -> denegado.
- Clave `autonomy` presente pero paquete `tools/autonomy` ausente -> denegado.
- Fuente sellada (`is_source_sealed`) -> denegada, sin importar el observer.
- Sin clave `autonomy`: equivale a "sin sellos" (semántica de Change 0).
- Permiso efectivo = policy humana ∩ registro; el registro nunca amplía.
- Aceptación: tests de `ds_guard` con guardrails de fixtures: sellada por `source_id` aunque el
  registro la declare -> `SOURCE-SEALED` y el observer señuelo no se importa; corrupto -> denegado;
  `autonomy` presente sin paquete (simulado ocultando el import) -> denegado.

**R25 — `datasources` no importa `autonomy` ni `pathguard`.** `access_check` es un parámetro
obligatorio (`Callable[[str, str], tuple[bool, str]]`); sin él `observe_source` falla cerrado con
`SOURCE-ACCESS-DENIED`.
- Aceptación: llamada sin `access_check`/con excepción dentro de él -> `SOURCE-ACCESS-DENIED`.

## 9. Frescura

**R26 — `compare_fingerprint(stored, fresh) -> CheckResult`.** Pura.
- Ambos con `dataset.fingerprint` y mismo `algorithm`: igual `value` -> PASS; distinto ->
  FAIL `SOURCE-OBSERVATION-STALE`.
- Falta `fingerprint` en alguno, o `algorithm` distinto -> WARN `SOURCE-FRESHNESS-UNVERIFIABLE`.
  Nunca PASS por ausencia.
- Si `snapshot.as_of` difiere, se reporta en `detail` pero no sustituye al fingerprint (dos
  observaciones con igual fingerprint y distinto `as_of` siguen siendo PASS, con detalle).
- `source_id` distinto -> `SOURCE-OBSERVATION-INVALID`.
- Aceptación: tabla de 6 casos (igual, distinto, falta en stored, falta en fresh, algoritmo distinto,
  `as_of` distinto con igual fingerprint).

## 10. Bridge `profile.json` -> observación

**R27 — `profile_bridge.profile_to_observation(profile, source_id) -> SourceObservation`.** Pura.
- dtype -> familia: `texto`->`string`, `entero`->`integer`, `flotante`->`float`,
  `booleano`->`boolean`, `fecha`->`temporal`, otro/ausente->`unknown`; `native_type` = dtype original.
  El dtype se toma de `columnas_detalle[campo]["dtype"]`; si el campo está en `schema` sin entrada de
  detalle, `type_family = unknown` (divergencia declarada D12(d), ver `design.md`).
- `filas` -> `row_count` exact. `nulls.count` -> `null_count` exact (forma de
  `column_stats.py:266-270`).
- `unique{count,exactitud}` -> `distinct_count` (`exacta`->exact, `muestreada`->approximate; otro
  valor -> faceta no escrita).
- `top_valores[{valor,frecuencia}]` -> `value_distribution[{value,frequency}]` con exactness de
  `unique.exactitud` y `complete = (unique.exactitud == "exacta" and unique.count <= len(top_valores))`.
- `min`/`max` (solo dtype numérico; ds_profile siempre los computa exactos en streaming,
  `column_stats.py:1-14,278-279`) -> `value_range` exact, con `null` cuando `ds_profile` emite `null`.
- `fecha_min`/`fecha_max` (`column_stats.py:286-287`) -> `time_range` exact, con `null` si `null`.
- `fingerprint{algoritmo,hash}` (`fingerprint.py:29`) -> `dataset.fingerprint{algorithm,value}`;
  ausente en el perfil -> faceta no escrita.
- `sampling{activo,metodo,tamano_muestra,seed}` -> `dataset.sampling{active,method,sample_size,seed}`
  (claves faltantes -> `null`; los perfiles de fixtures usan `semilla` en lugar de `seed`
  -- el bridge lee `seed` y, si falta, `semilla`).
- **Nunca** copia `dataset_path`, `tamano_bytes` ni ninguna ruta (`report.py:206-230`).
- Sin la forma mínima (`schema` dict, `columnas_detalle` dict, `sampling.activo` bool, `filas`
  entero >= 0) -> `SourceError` (`SOURCE-PROFILE-INVALID`).
- Aceptación: golden del bridge con un perfil completo de `ds_profile`; test `ast`/recursivo de que
  el resultado no contiene el valor de `dataset_path`; perfil sin `columnas_detalle` -> `SourceError`.

**R28 — `file_observer`.** Único observer que Harmessi incluye (compatibilidad). `factory(source_id,
options)` acepta `options.path` (ruta repo-relativa) y opcionales de muestreo; `observe()` invoca
`ds_profile` (import perezoso) sobre el archivo, pasa por el guard de holdout
(`ds_profile/holdout_guard.py:89`, `verificar_permitido`) y devuelve `profile_to_observation`. La
ruta no aparece en la observación. Sin `ds_profile` instalado -> `SOURCE-OBSERVER-ERROR`
(instrucción de `ds_init sync --stage experiment`).
- Aceptación: observer sobre un CSV temporal pequeño coincide con `profile_to_observation` del
  perfil de `ds_profile` para el mismo archivo; ruta bajo holdout -> `technical_error`.

## 11. Evaluador único y paridad

**R29 — `validate_contract_observation(contract, observation, *, wording=None)`** en
`tools/datacontracts/validation.py`. Nativo sobre `SourceObservation` (o dict serializable), sin I/O,
nunca lanza. Devuelve la lista de `CheckResult` en el mismo orden de v0.7 (field-missing,
field-unexpected, type-mismatch, nullability, key, y luego una entrada por constraint en orden del
contrato). Contrato no `DataContract` -> `CONTRACT-INPUT` (technical_error). Observación
estructuralmente inválida -> `CONTRACT-EVIDENCE-MISSING` (technical_error).

**R30 — Reglas sobre facetas.** La faceta no observada nunca produce PASS.
- FIELD-MISSING / FIELD-UNEXPECTED: por nombres (y orden) de `fields`.
- TYPE-MISMATCH agregada (mismo esquema PASS/N-A/FAIL por campo que `validation.py:275-325`).
  Compatibilidad: declarado `string`->{`string`}; `integer`->{`integer`}; `float`->{`float`};
  `boolean`->{`boolean`}; `date` y `datetime`->{`date`,`datetime`,`temporal`}; `unknown` -> N/A. Observado
  `unknown` con familia declarada mapeada -> WARN "no clasificable" (solo observaciones nativas; ver
  R33 para el bridge).
- NULLABILITY y NOT-NULL: `null_count` exact > 0 -> violación; exact == 0 -> PASS; approximate == 0
  o faceta ausente -> WARN no verificable; approximate > 0 -> violación.
- UNIQUE/KEY (un campo): `distinct_count` exact con `row_count` y `null_count` exact: `distinct <
  row_count - null_count` -> violación, si no PASS (como `validation.py:373-382`). Approximate:
  frecuencia > 1 en `value_distribution` -> violación (`validation.py:384-393`), si no WARN. Sin
  faceta -> WARN. Unicidad compuesta -> WARN "no evidenciada" siempre en v0.8.
- ALLOWED-VALUES: valores de `value_distribution` fuera del dominio (comparación
  `str(v).strip()`) -> violación por cada infractor, en orden; PASS solo con `complete=True` y
  exactitud exact; si no WARN.
- RANGE (min_value/max_value): campo con familia observada `integer|float`; si no, N/A. Violación
  válida aunque `value_range` sea approximate (min observado < mínimo declarado, max observado >
  máximo declarado); cumplimiento (PASS) solo con exact; approximate sin violación o faceta ausente
  -> WARN. `value_range` con `min`/`max` `null` y exact -> PASS (sin valores no nulos que violen;
  paridad con `validation.py:608,615`).
- DATE-RANGE (date_min/date_max): análogo sobre `time_range`, familia `date|datetime|temporal`, si
  no N/A; `min`/`max` `null` o valor declarado/observado no ISO -> WARN "formato de fecha no
  comparable" (paridad con `validation.py:681-684`).
- LENGTH e INVARIANT: siempre WARN.
- Aceptación: una tabla de tests por regla × exactitud × presencia de faceta (matriz de R30);
  asserts explícitos de que ninguna faceta ausente produce PASS.

**R31 — Evidencia "observado y vacío".** Una columna numérica/temporal sin valores no nulos se
representa con `value_range`/`time_range` `{"min": null, "max": null}` exact (observado y vacío),
distinto de la faceta ausente (no observado).

**R32 — Wrappers v0.7.** `validate_contract(contract, profile)` y
`validate_contract_against_profile_file(contract, profile_path, repo_root)` conservan firma, códigos
`CONTRACT-*`, orden de resultados y comportamiento. `validate_contract` = gate legacy
(`_validar_evidencia`, `validation.py:191-232`, mismos `technical_error`) -> `profile_to_observation` ->
evaluador único con `wording=LEGACY_PROFILE`. El wrapper de archivo conserva `verificar_permitido`
ANTES de abrir el archivo (`validation.py:789`) y todos sus `technical_error`. No existen dos
motores: las `_regla_*` operan sobre la observación; los wrappers no reimplementan reglas.
- Aceptación: test `ast` de que las funciones `validate_contract*` no contienen lógica de reglas
  (solo llamadas al gate, bridge y evaluador); los tests existentes de datacontracts/ds_guard/
  qualityevidence pasan sin editarlos.

**R33 — `wording`.** El evaluador emite texto vía un catálogo `wording`: `NEUTRAL` (defecto;
"observación"/"fuente") y `LEGACY_PROFILE` (textos v0.7 verbatim: "perfil", `dtype=...`,
`ds_profile no calcula...`), este último en `tools/datacontracts/legacy_wording.py`. El wrapper de
perfil usa `LEGACY_PROFILE`. Los textos que dependen de dtype usan `native_type` y una tabla
familia->dtypes propia del catálogo legacy (`sorted(esperados)` de `validation.py:294-297`).
- Aceptación: R34.

**R34 — Paridad exacta (criterio de cierre).**
(a) ANTES de refactorizar `validation.py`, `tools/datacontracts/tests/parity/build_golden_v07.py`
(one-shot, lo ejecuta el Lead) corre el evaluador v0.7 sobre un corpus determinista y guarda
`tools/datacontracts/tests/parity/golden_v07_validation.json` con, por caso, la lista completa de
`CheckResult.to_dict()` (status, code, message, detail, subject, kind) y su orden. El corpus incluye
TODOS los fixtures de `test_validation.py` (reconstruidos con los mismos helpers,
`test_validation.py:22-99`) más una matriz sintética determinista: cada `constraint_type` ×
{exacta, muestreada} × {con/sin nulos} × {con/sin duplicados en `top_valores`} × {campo ausente,
campo extra} × tipos declarados × `sampling` on/off; `RANDOM_STATE` fijo si hay aleatoriedad. El
script no depende de `datasources`.
(b) `test_parity_golden.py` compara el wrapper nuevo contra el golden con IGUALDAD EXACTA de la lista
de `to_dict()` (mensajes incluidos) para todos los casos.
(c) Todos los perfiles del corpus son conformes al schema v1 de `ds_profile` (o fixtures existentes).
Si un fixture existente diverge, el implementador se DETIENE y lo informa al Lead: no se ajusta el
golden ni el evaluador para forzar paridad.
(d) Las divergencias declaradas (R35) se fijan con tests aparte, fuera del golden.
- Aceptación: `pytest tools/datacontracts -q` verde con el golden versionado; el golden se genera una
  sola vez y su diff posterior en el repo es revisión humana.

**R35 — Divergencias declaradas (solo entradas no conformes con lo que `ds_profile` siempre emite).**
a) perfil al que le faltan facetas por columna (`nulls`, `unique`, `top_valores`, `min`, `max`,
`fecha_*`): v0.7 podía dar PASS/FAIL por evidencia ausente (p. ej. `nullability` PASS con `nulls`
faltante, `validation.py:336-353`; unicidad exacta con `distintos` no entero -> PASS,
`validation.py:373-382`); el motor único da WARN no verificable (nunca PASS por falta de evidencia,
decisión 3 de v0.7).
b) dtype fuera de los 5 valores (que `ds_profile` no emite): v0.7 -> FAIL type-mismatch; ahora
`unknown` -> WARN "no clasificable".
c) campo en `schema` sin entrada en `columnas_detalle`: v0.7 -> FAIL type-mismatch / "ausente" en
unicidad; ahora `unknown` -> WARN. (Se confirma contra fixtures en T0; si un fixture existente cae
aquí, aplica R34(c).)
- Aceptación: tests `test_divergencias_declaradas.py` fijan el comportamiento nuevo; `design.md` los
  lista.

## 12. CLI

**R36 — `ds_guard source ...`** en `tools/ds_guard.py` con imports perezosos
(`_importar_perezoso`, `ds_guard.py:919`), `--json`, exit codes 0/1/2/3 (sin cuarto patrón; 3 =
paquete no instalado/repo no encontrado, 2 = entrada inválida, como `cmd_contract_validate`,
`ds_guard.py:1009-1031`):
- `source list`: fuentes del registro (id, role, observer_id, sensitivity, access_mode).
- `source check`: `check_registry` estático.
- `source observe --source-id X [--facet F ...] [--exactness any|exact] [--as-of ISO]`: usa
  `observe_source` con el `access_check` real (R24); imprime resultados y `observation_id`.
- `source check-stale --observation <path>`: lee la observación (ruta repo-relativa validada, sin
  `..`), re-observa solo `fingerprint` y aplica `compare_fingerprint`.
- Aceptación: tests de CLI (invocación in-process de `main`) por subcomando y exit code; `--help`
  menciona "best-effort" (R19) y "sin timeout en proceso" (R17).

**R37 — `contract validate --observation <path>`** aditivo y mutuamente excluyente con `--profile`
(exactamente uno; ninguno o ambos -> exit 2). Con `--record-evidence`, `fuente_role="observation"`
(`qualityevidence` no cambia: hashea cualquier archivo, `evidence.py:163`). Lee la observación
(guard de holdout sobre la ruta como en el wrapper de archivo) y llama a `validate_contract_observation`
con `wording=NEUTRAL`. El comportamiento con `--profile` es idéntico al de v0.7.
- Aceptación: los tests existentes de `contract validate` pasan sin editar; nuevo test con
  `--observation` y `--record-evidence` produce un manifest cuya fuente tiene role `observation`.

## 13. Instalabilidad y arquitectura

**R38 — Manifiesto.** Entradas VERBATIM en `tools/ds_init/manifest.py`: paquete `datasources`
(`__init__`, `core`, `scan`, `registry`, `runtime`, `profile_bridge`) en `stage_minimo=discovery`;
`file_observer.py` en `experiment`; `datacontracts/legacy_wording.py` en `discovery`. Los tests y el
corpus dorado no se instalan (mismo tratamiento que los tests de `datacontracts`; verificar el
patrón vigente al implementar).
- Aceptación: `python -m tools.ds_init.check_manifest_parity` OK; instalación en `discovery` puede
  importar `datacontracts.validation` (que importa `datasources`) sin `ds_profile` ausente que
  falle a nivel de import (el import de `ds_profile` en `file_observer` es perezoso).

**R39 — Tests de repo.** `tools/tests/test_v08_datasources_neutrality.py` (R1-R3, R10, R32),
`tools/tests/test_v08_source_id_parity.py` (igualdad de `SOURCE_ID_PATTERN` entre `datasources` y
`autonomy`), actualización de `tools/tests/test_architecture_boundaries.py` (`MODULOS_CORE`).

**R40 — Documentación.** `ARCHITECTURE.md`: filas en §2.1, regla 11 para `tools/datasources`, la
excepción de `tools.datacontracts` en las reglas de importación y ajuste de la mención en §6.
`docs/roadmap/v0.8.md`: tildar Change 1 al cerrar.
- Aceptación: revisión del reviewer; `test_architecture_boundaries.py` verde.

## 14. Given/When/Then principales

- G: registro con `customers` (observer en memoria) y policy sin sellos. W: `source observe
  --source-id customers`. T: exit 0, `observation.json` en `.harmessi/observations/customers__<12hex>/`,
  sin rutas absolutas.
- G: `customers` en `sealed_sources` de la policy humana y declarado en el registro. W: `source
  observe`. T: `SOURCE-SEALED`, el módulo del observer no se importa, no hay archivo persistido.
- G: observer que lanza `ImportError`. W: observe. T: `technical_error SOURCE-OBSERVER-ERROR`, no se
  ejecuta `validate_contract`, sin instalación de nada.
- G: observation sin `null_count` para un campo `nullable=False`. W: validate. T: WARN no
  verificable, nunca PASS.
- G: `value_range` approximate con min < mínimo declarado. W: validate RANGE. T: violación con la
  severidad del constraint.
- G: dos observaciones con igual fingerprint. W: `check-stale`. T: PASS. Fingerprint distinto: FAIL
  `SOURCE-OBSERVATION-STALE`. Observer sin `fingerprint`: WARN `SOURCE-FRESHNESS-UNVERIFIABLE`.
- G: fuente `sensitive`. W: observe con `value_range` disponible. T: sin `value_range` en el archivo;
  `omitted_facets` lo registra; WARN `SOURCE-FACET-OMITTED`.
- G: `native_type` con `C:\datos\x.csv`. W: observe. T: `SOURCE-ABSOLUTE-PATH`, nada persistido.
- G: golden v0.7. W: wrappers nuevos sobre el corpus. T: igualdad exacta de `to_dict()`.

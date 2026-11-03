# Spec — 20260922-data-contracts-core

## Requisitos

- **R1 — Paquete y módulo solo-stdlib**: existe `tools/datacontracts/__init__.py` (sin lógica ni
  imports de hermanos, cuerpo vacío salvo docstring opcional) y `tools/datacontracts/core.py`.
  `core.py` importa únicamente de la stdlib: `dataclasses`, `hashlib`, `json`, `re`, `typing`
  (más `__future__`). No importa `ds_profile`, `dsguard`, pandas, numpy, `tools.reporting` ni
  ningún módulo bajo `tools.*` distinto de sí mismo, ni ningún hermano futuro de
  `tools/datacontracts` (`evolution.py`, `cli.py`, etc., que no existen todavía). No conoce
  ningún dominio de negocio concreto: ningún nombre importado, constante ni identificador
  referencia una técnica, un backend de almacenamiento o un dataset real. Las dataclasses son
  `frozen=True`; docstrings/comentarios en español; nombres en `snake_case`.

- **R2 — Vocabularios y constantes (tuplas de módulo)**:
  `TYPE_FAMILIES = ("string", "integer", "float", "boolean", "date", "datetime", "unknown")`;
  `DATASET_ROLES = ("raw_table", "feature_table", "scoring_output", "generic")`;
  `CONSTRAINT_TYPES = ("not_null", "unique", "allowed_values", "min_value", "max_value",
  "min_length", "max_length", "date_min", "date_max", "invariant")`;
  `SEVERITIES = ("FAIL", "WARN")`; `COMPAT_ACTIONS = ("block", "warn", "allow")`;
  `EXTENSION_PREFIX = "x_"`; `SCHEMA_VERSION = 1`. Excepción `DataContractError(ValueError)`.
  Todo error de contrato del módulo lanza `DataContractError` (nunca `TypeError`/`KeyError`
  crudos por entrada inválida del usuario).

- **R3 — IDs seguros**: `contract_id`, `constraint_id`, `rule_id`, `policy_id` deben ser `str` y
  cumplir `^[a-z0-9][a-z0-9_-]{0,63}$`, rechazando además los nombres de dispositivo reservados
  de Windows (`con`, `prn`, `aux`, `nul`, `com1`..`com9`, `lpt1`..`lpt9`). Un id inválido lanza
  `DataContractError` al construir.

- **R4 — Nombres de campo**: `ContractField.name` debe ser `str` y cumplir
  `^[a-z][a-z0-9_]*$` (snake_case, sin guiones, primer carácter letra minúscula), sin límite de
  reserva de nombres de Windows (no se usa como nombre de archivo). Un nombre inválido lanza
  `DataContractError`.

- **R5 — `ContractField` (capa schema/structure)**: campos `name (str, R4), type_family (∈
  TYPE_FAMILIES), required (bool, default True), nullable (bool, default True), description
  (str, default ""), extensions (dict, default {})`. Reglas: `type_family` fuera de
  `TYPE_FAMILIES` → error; `required`/`nullable` deben ser `bool` estricto (no `int`);
  `extensions` es JSON-seguro (`str`/`int`/`float` finito/`bool`/`None`/`list`/`dict` anidado,
  claves `str`) y **todas** sus claves de primer nivel empiezan con `EXTENSION_PREFIX` ("x_"); una
  clave sin ese prefijo → `DataContractError`.

- **R6 — `Constraint` (capa quality expectations, declara severidad, no evalúa nada)**: campos
  `constraint_id (str, R3), constraint_type (∈ CONSTRAINT_TYPES), field (Optional[str], default
  None), severity (∈ SEVERITIES, default "FAIL"), params (dict, default {}), description (str,
  default "")`. Validación de `params` por `constraint_type` (solo forma, nunca evaluación):
  - `"not_null"`: `params` puede estar vacío; si trae claves, deben ser JSON-seguras (sin
    exigencia adicional).
  - `"unique"`: `params` opcional `{"fields": [str, ...]}` (composición); si está presente cada
    elemento debe ser `str` no vacío.
  - `"allowed_values"`: requiere `params["values"]` = lista no vacía de escalares JSON-seguros
    sin duplicados; ausente, vacía o con duplicados → error.
  - `"min_value"` / `"max_value"`: requiere `params["value"]` = `int` o `float` finito
    (`bool` explícitamente rechazado); ausente o de otro tipo → error.
  - `"min_length"` / `"max_length"`: requiere `params["value"]` = `int >= 0` (no `bool`);
    ausente, negativo o de otro tipo → error.
  - `"date_min"` / `"date_max"`: requiere `params["value"]` = `str` no vacío; el core NO parsea
    ni valida formato de fecha.
  - `"invariant"`: requiere `params["note"]` = `str` no vacío (nota declarativa); `params` puede
    incluir opcionalmente `"fields"` = lista de `str`. Ningún valor de `params` puede ser
    invocable ni tener forma de expresión ejecutable: el core solo acepta tipos JSON puros
    (cualquier tipo no serializable en `params` ya es rechazado por el chequeo JSON-seguro
    general).
  `field`, si no es `None`, es `str` no vacío (la existencia real entre los `fields` del contrato
  se valida en `DataContract`, no acá).

- **R7 — `BusinessRule` (capa semantic business rules, solo declarable)**: campos
  `rule_id (str, R3), statement (str no vacío), rationale (str, default ""), reference
  (Optional[str], default None; si no es None, str no vacío)`. El módulo `core.py` no define
  ninguna función que evalúe, ejecute o compare un `BusinessRule` contra datos ni contra otro
  objeto (verificable por inspección: ningún identificador de `core.py` combina un verbo de
  evaluación — `evaluate`/`evaluar`/`check`/`validate_against` — con `BusinessRule`).

- **R8 — `ContractVersion` (metadata versionada, sin lógica de diff)**: campos
  `version (str, ^\d+\.\d+\.\d+$), summary (str, default ""), previous_version (Optional[str],
  default None; si no es None, mismo patrón que version)`. Un `version`/`previous_version` que no
  cumple el patrón semver simple → `DataContractError`. El módulo no define ninguna función
  `compare`/`diff`/`classify` sobre dos `ContractVersion` ni sobre dos `DataContract`.

- **R9 — `CompatibilityPolicy` (declaración de política, sin clasificación)**: campos
  `policy_id (str, R3), on_removed_field, on_required_field_added, on_type_change,
  on_constraint_tightening, on_constraint_loosening, on_unknown_change` — los 6 últimos son
  `str ∈ COMPAT_ACTIONS`, todos requeridos (sin default). Un valor fuera de `COMPAT_ACTIONS` o un
  campo ausente → `DataContractError`. El módulo no define ninguna función que compare dos
  `DataContract` y decida a qué categoría de cambio pertenece una diferencia real (eso es
  responsabilidad del Change 4).

- **R10 — `DataContract` (raíz)**: campos `contract_id (str, R3), version (ContractVersion),
  dataset_role (∈ DATASET_ROLES), fields (tuple[ContractField], no vacía), constraints
  (tuple[Constraint], default ()), business_rules (tuple[BusinessRule], default ()), keys
  (tuple[str], default ()), compatibility_policy (Optional[CompatibilityPolicy], default None),
  description (str, default ""), extensions (dict, default {}, mismas reglas que R5), 
  schema_version (int, default SCHEMA_VERSION)`. Reglas de unicidad y referencia:
  - `fields` no vacía; `ContractField.name` únicos entre sí (mismo namespace) → duplicado lanza
    error.
  - `constraints`: `constraint_id` únicos en todo el `DataContract`; si `Constraint.field` no es
    `None`, debe existir entre los `name` de `fields` (si no existe → error); cada elemento de
    `Constraint.params["fields"]` (cuando la forma de esa `constraint_type` lo admite) también
    debe existir entre los `name` de `fields`.
  - `business_rules`: `rule_id` únicos en todo el `DataContract` (namespace propio, separado de
    `constraint_id` — un `rule_id` puede coincidir con un `constraint_id` sin error).
  - `keys`: cada elemento ∈ `name` de `fields`, sin duplicados; puede ser vacía.
  - `compatibility_policy`: `None` o instancia de `CompatibilityPolicy` (cualquier otro tipo →
    error).
  - `schema_version` debe ser exactamente `SCHEMA_VERSION`; distinto → error.
  Accesores, ninguno lanza: `get_field(name) -> Optional[ContractField]`,
  `constraints_for(field_name) -> tuple[Constraint]` (constraints con `field == field_name`, o
  con `field is None` si se pide `constraints_for(None)`), `get_constraint(constraint_id) ->
  Optional[Constraint]`, `get_business_rule(rule_id) -> Optional[BusinessRule]`.

- **R11 — Política de validación en construcción**: estricta y solo estructural (enums, ids,
  patrones, tipos, duplicados, referencias de campo existentes, JSON-seguridad de
  `params`/`extensions`). El core NO evalúa ninguna regla contra ninguna observación de datos;
  ningún constructor de este módulo acepta un argumento que represente datos, filas, un
  `DataFrame`, un `profile.json` ni una ruta de archivo. `params`/`extensions` se copian en
  profundidad al construir (no se comparte el `dict` del llamador) y se normalizan a estructura
  JSON pura (`tuple`→`list`, claves `str`).

- **R12 — Serialización determinista**: cada dataclass expone `to_dict()` (orden de campos fijo,
  solo tipos JSON) y `from_dict()` (estricto en campos requeridos y, en `DataContract`, en
  `schema_version`; ignora claves desconocidas por forward-compat). `canonical_json(obj)` =
  `json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)`
  (fallo de serialización → `DataContractError`). `DataContract.content_sha256()` = sha256 (hex)
  de `canonical_json(self.to_dict())` codificado en UTF-8. Para el mismo contenido el hash es
  idéntico entre corridas y tras `DataContract.from_dict(dc.to_dict())`. `DataContract` no
  expone `generated_at` ni ningún dato de ejecución.

- **R13 — Instalabilidad**: `tools/ds_init/manifest.py` agrega dos `EntradaManifiesto` VERBATIM
  (`tools/datacontracts/__init__.py`, `tools/datacontracts/core.py`; `fuente == destino`) con
  `stage_minimo` por defecto (`"discovery"`). Los tests de `tools/datacontracts/tests/` no van al
  manifest. `tools/ds_init/tests/test_manifest.py` y todo test que dependa de exclusiones,
  destinos únicos o monotonía de bundles siguen verdes sin editarse.

- **R14 — Arquitectura y frontera**: `ARCHITECTURE.md` §2.1 tiene una fila para
  `tools/datacontracts/core.py` (core neutral, solo-stdlib) y §3 una regla 7 (texto exacto en
  `design.md`): en la familia `tools/datacontracts`, `core.py` es solo-stdlib y no importa
  hermanos; en Changes posteriores (no en Change 0) los módulos de la familia podrán importar
  `dsguard.checks` y leer `profile.json` como archivo, pero nunca al revés (`dsguard`,
  `ds_profile`, `dsimpact`, `reporting`, `providers`, `routing`, `fallback`, `harmessi_bench` no
  importan `tools/datacontracts`). `tools/datacontracts/core.py` se agrega a `MODULOS_CORE` de
  `tools/tests/test_architecture_boundaries.py`. `tools/tests/test_v07_core_neutrality.py`
  (patrón `ast` de `test_v06_core_neutrality.py`) verifica R1 y la dirección inversa de la regla
  7.

- **R15 — Backward compatibility**: ningún archivo existente cambia de comportamiento. Las
  únicas modificaciones a archivos existentes son aditivas: dos entradas en `MANIFEST`, una fila
  y una regla en `ARCHITECTURE.md`, una línea en `MODULOS_CORE`, y (al cierre) el tildado en
  `docs/roadmap/v0.7.md`. Ningún módulo existente importa `tools.datacontracts`.

- **R16 — Roadmap**: al cerrar el Change (invocación de cierre) se tilda `[x] Change 0` en
  `docs/roadmap/v0.7.md`. Nada más del roadmap cambia en este Change; Changes 1–5 no se tocan.

- **R17 — Tests deterministas**: `tools/datacontracts/tests/test_core.py` (unittest) y
  `tools/datacontracts/tests/test_installability.py`, más
  `tools/tests/test_v07_core_neutrality.py`, sin I/O de red, sin pandas/numpy, sin lectura de
  ningún dataset ni `profile.json` real, sin aleatoriedad.

## Criterios de aceptación

**R1/R14 — neutralidad**
- Given `tools/datacontracts/core.py`, When `test_v07_core_neutrality.py` recorre su AST, Then
  todos los imports de nivel de módulo (y anidados) pertenecen a `{__future__, dataclasses,
  hashlib, json, re, typing}` y ninguno referencia `ds_profile`, `dsguard`, `pandas`, `numpy`,
  `reporting`.
- Given los módulos de `dsguard`, `ds_profile`, `dsimpact`, `reporting`, `providers`, `routing`,
  `fallback` y `harmessi_bench`, When se escanean sus imports, Then ninguno importa
  `datacontracts` (ningún estilo: `import tools.datacontracts`, `from tools.datacontracts import
  x`, `from . import datacontracts`, etc.).
- Given `MODULOS_CORE`, Then contiene `tools/datacontracts/core.py` y
  `test_architecture_boundaries.py` sigue verde (ningún adapter importado, sin `sys.stdin`).

**R2/R3/R4 — vocabularios e ids**
- Given cada valor de `TYPE_FAMILIES`, `DATASET_ROLES`, `CONSTRAINT_TYPES`, `SEVERITIES`,
  `COMPAT_ACTIONS`, Then coincide exactamente (contenido y orden) con lo declarado en R2.
- Given un `contract_id`/`constraint_id`/`rule_id`/`policy_id` inválido (vacío, con mayúscula,
  con punto, con `/`, de 65 caracteres, no-`str`, o un nombre reservado de Windows como `"con"`),
  Then `DataContractError` en cada contrato que lo reciba.
- Given un `ContractField.name` inválido (`""`, `"Nombre"`, `"1campo"`, `"campo-1"`,
  `"campo.1"`), Then `DataContractError`; dado `"campo_1"`, `"a"`, `"nombre_largo_valido"`, Then
  válido.

**R5 — `ContractField`**
- Given `type_family="otro"`, Then error.
- Given `required=1` o `nullable="si"` (no-bool), Then error.
- Given `extensions={"x_nota": "ok"}`, Then válido; dado `extensions={"nota": "sin prefijo"}`,
  Then error.
- Given `extensions` con un valor no JSON-seguro (objeto arbitrario, `float("nan")`), Then error.

**R6 — `Constraint`**
- Given `constraint_type="otro"`, Then error; dado `severity="INFO"`, Then error.
- Given `constraint_type="allowed_values"` sin `params["values"]`, con lista vacía o con
  duplicados, Then error en cada caso; con `params={"values": [1, 2, 3]}`, Then válido.
- Given `constraint_type="min_value"` con `params={"value": True}` (bool) o sin `"value"`, Then
  error; con `params={"value": 10}` o `params={"value": 10.5}`, Then válido.
- Given `constraint_type="min_length"` con `params={"value": -1}` o `params={"value": 1.5}`
  (float, no int), Then error; con `params={"value": 0}`, Then válido.
- Given `constraint_type="invariant"` sin `params["note"]` o con `params["note"]=""`, Then error;
  con `params={"note": "suma de a y b es 100"}`, Then válido.
- Given `constraint_type="date_min"` con `params={"value": ""}`, Then error; con
  `params={"value": "2020-01-01"}`, Then válido (sin parseo de formato).
- Given `field=None`, Then válido (alcance de dataset); dado `field=""`, Then error.

**R7 — `BusinessRule`**
- Given `statement=""`, Then error; dado `statement` no vacío sin `rationale`/`reference`, Then
  se construye con ambos en su default (`""`/`None`).
- Given `reference=""`, Then error; dado `reference=None` o un `str` no vacío, Then válido.
- Given el código fuente de `core.py`, Then ningún identificador combina un verbo de evaluación
  con `BusinessRule` (chequeo textual/AST en el test).

**R8 — `ContractVersion`**
- Given `version="1.0"` (falta el patch) o `version="v1.0.0"` o `version="1.0.0.1"`, Then error;
  dado `version="1.0.0"` o `"0.0.1"`, Then válido.
- Given `previous_version="1.0"`, Then error; dado `previous_version=None` o `"0.9.0"`, Then
  válido.
- Given el código fuente de `core.py`, Then no define ninguna función `compare`/`diff`/`classify`
  sobre `ContractVersion` ni `DataContract` (chequeo textual/AST en el test).

**R9 — `CompatibilityPolicy`**
- Given cualquiera de los 6 campos con un valor fuera de `COMPAT_ACTIONS` (p. ej. `"ignore"`),
  Then error.
- Given la construcción sin uno de los 6 campos (todos requeridos), Then `TypeError` de Python
  por argumento faltante (dataclass sin default) — comportamiento esperado y documentado, no un
  `DataContractError` (los campos requeridos sin default fallan antes de `__post_init__`).
- Given los 6 campos con valores válidos de `COMPAT_ACTIONS` (incluida cualquier combinación),
  Then se construye sin error.

**R10 — `DataContract`**
- Given `fields=()` (vacía), Then error.
- Given dos `ContractField` con el mismo `name`, Then error.
- Given dos `Constraint` con el mismo `constraint_id`, Then error.
- Given un `Constraint` con `field="inexistente"`, Then error; dado `field=None`, Then válido
  aunque el contrato no tenga ninguna constraint más.
- Given un `Constraint` `constraint_type="unique"` con `params={"fields": ["a", "inexistente"]}`
  donde `"a"` existe pero `"inexistente"` no, Then error.
- Given dos `BusinessRule` con el mismo `rule_id`, Then error; dado un `rule_id` igual a un
  `constraint_id` existente, Then válido (namespaces distintos).
- Given `keys=("campo_inexistente",)`, Then error; dado `keys=()` o `keys=("id",)` con `"id"` ∈
  `fields`, Then válido.
- Given `compatibility_policy=` un `dict` en vez de `CompatibilityPolicy`, Then error.
- Given `schema_version=2` (con `SCHEMA_VERSION == 1`), Then error tanto en el constructor
  directo como en `from_dict`.
- Given un `DataContract` válido, Then `get_field`/`get_constraint`/`get_business_rule` devuelven
  el objeto y `None` para un id/nombre inexistente sin lanzar; `constraints_for(field_name)`
  devuelve solo las constraints de ese campo (o las de alcance dataset si se pide con `None`).

**R11 — validación en construcción**
- Given cualquier constructor público del módulo, Then ninguno acepta un parámetro llamado
  `data`, `frame`, `dataframe`, `profile`, `rows` ni `path`/`ruta` (chequeo por firma/AST en el
  test): el módulo no tiene ninguna vía de entrada de datos reales.
- Given un `extensions`/`params` mutado por el llamador después de construir el objeto, Then el
  objeto de este módulo no cambia (copia profunda).

**R12 — serialización determinista**
- Given dos `DataContract` construidos con los mismos datos en distinto orden de claves de
  `extensions`, Then `content_sha256()` es igual.
- Given un `DataContract` completo (con `constraints`, `business_rules`, `keys`,
  `compatibility_policy`), Then `DataContract.from_dict(dc.to_dict()) == dc` (comparación de
  contenido campo a campo) y `content_sha256()` idéntico; `to_dict()` es serializable con
  `json.dumps` y `canonical_json` no contiene espacios extra ni escapa caracteres no ASCII.
- Given `from_dict` con un campo requerido ausente, o `schema_version` ausente o distinto de `1`,
  Then `DataContractError`; con claves desconocidas extra, las ignora.
- Given `canonical_json({"a": float("nan")})`, Then `DataContractError`.
- Given cambiar un solo valor de `params` de una `Constraint`, Then el hash del `DataContract`
  cambia; `DataContract` no expone `generated_at`.

**R13 — instalabilidad**
- Given `MANIFEST`, Then contiene exactamente una entrada con `destino` (y `fuente`)
  `tools/datacontracts/__init__.py` y una con `tools/datacontracts/core.py`, ambas `VERBATIM` y
  con `stage_minimo == "discovery"`, y ambas rutas existen en el repo.
- Given `manifest_para_perfil_y_stage(perfil, "discovery")`, Then incluye ambos destinos.
- Given `tools/ds_init/tests/test_manifest.py` sin modificar, Then sigue verde; ningún destino
  nuevo cae en `EXCLUSIONES_PERMANENTES`.

**R15/R16 — compatibilidad y roadmap**
- Given `git diff` del Change (invocación 2), Then los archivos preexistentes modificados son
  solo `manifest.py`, `ARCHITECTURE.md`, `test_architecture_boundaries.py` (y
  `control.json`/artefactos SDD de este Change), con cambios aditivos; la suite completa previa
  corre igual que en el baseline.
- Given `docs/roadmap/v0.7.md` al cierre (invocación 5), Then `[x] Change 0` y ningún otro Change
  del roadmap se modifica.

## Unidad de análisis / grain (condicional — data_understanding, feature_engineering, modeling)
No aplica: contrato de datos en memoria de infraestructura del harness, sin dataset.

## Cutoff / information boundary (condicional — feature_engineering, data_preparation, modeling)
No aplica.

## Baseline (condicional — modeling)
No aplica.

## Métrica primaria (condicional — modeling, evaluation)
No aplica.

## Métricas secundarias (opcional)
No aplica.

# Diseño — 20260922-data-contracts-core

## Decisión metodológica/técnica

Principio permanente: "LLM decide lo semántico; el binario calcula y hace cumplir lo
determinista" (`docs/roadmap/v0.7.md:27-29`). Flujo conceptual de v0.7
(`docs/roadmap/v0.7.md:45-71`): `DECLARACIÓN → OBSERVACIÓN → EVALUACIÓN DETERMINISTA →
EVIDENCE → INTERPRETACIÓN`. Este Change implementa únicamente el primer eslabón para datos:
`DataContract` y sus tipos asociados, en memoria, sin observar ni evaluar nada.

### Nombre de paquete: `tools/datacontracts`

Elegido `tools/datacontracts/core.py` (paquete nuevo `tools/datacontracts`, con `__init__.py`
sin lógica, siguiendo el patrón exacto de `tools/reporting/__init__.py`).

Motivo: el roadmap separa deliberadamente dos familias conceptuales con CLI candidata distinta
(`docs/roadmap/v0.7.md:355-360`: `harmessi contract ...` vs `harmessi quality ...`). Los
conceptos de este Change (`DataContract`, `ContractField`, `Constraint`, `ContractVersion`,
`CompatibilityPolicy`) son exclusivamente de **contratos de datos** — el Change 2
(`model-quality-policies`) declarará una familia paralela y distinta (`ModelQualityPolicy`,
`MetricRequirement`, `ObservedMetric`) que no comparte tipos con esta. Nombrar el paquete
`datacontracts` (en vez de un nombre genérico de "calidad") mantiene esa frontera conceptual
visible desde el nombre del paquete, igual que `tools/reporting` no se llamó `tools/output` ni
`tools/ml_output`.

Alternativas descartadas:
1. **`tools/dataquality` (o `tools/dq`)**: rechazada. "Calidad de datos" en el roadmap incluye
   tanto la declaración (este Change) como la evaluación contra `ds_profile` (Change 1); un
   nombre de paquete tan amplio invita a que Change 1 y, eventualmente, una futura idea de
   "calidad de modelo" (Change 2) terminen conviviendo bajo el mismo paquete "quality", cuando el
   roadmap las trata como dos familias CLI distintas (`contract` vs `quality`) desde el inicio.
   `datacontracts` deja lugar a que un futuro paquete de política de modelo tenga su propio
   nombre (p. ej. `tools/modelquality`) sin ambigüedad.
2. **`tools/quality/contracts_core.py`** (paquete `tools/quality` con submódulo anidado, tal como
   sugiere el brief de esta invocación como ejemplo): rechazada. Introduce un nivel de anidación
   que ningún paquete existente usa (`tools/reporting`, `tools/dsimpact`, `tools/providers`,
   `tools/routing`, `tools/fallback`, `tools/harmessi_bench` son todos paquetes de primer nivel
   con `core.py` directo); además un paquete `tools/quality` genérico corre el mismo riesgo que
   la alternativa 1 de terminar alojando conceptos de Change 2 sin frontera clara.
3. **`tools/contracts`** (sin prefijo `data`): rechazada por ambigüedad futura — un
   `ModelQualityPolicy` también podría describirse como un "contrato" en sentido amplio
   (contrato de calidad de modelo); `datacontracts` es inequívoco: contratos de **datos**,
   coherente con el nombre exacto del Change (`data-contracts-core`) y con el vocabulario ya
   usado en el roadmap ("Data Contracts" como título del ítem, `docs/roadmap/v0.7.md:105-107`).

`tools/datacontracts/core.py` es solo-stdlib (`dataclasses`, `hashlib`, `json`, `re`, `typing`,
más `__future__`, mismo patrón que `tools/reporting/core.py:30-37`); no importa `math` (no hay
celdas de tabla ni floats no finitos que filtrar como en reporting — los valores numéricos de
rango/dominio se validan con `isinstance` simple). `__init__.py` queda sin lógica ni imports,
igual que `tools/reporting/__init__.py` (verificado por `test_v06_core_neutrality.py:149-160`,
patrón que replica `test_v07_core_neutrality.py`).

### Vocabularios y constantes de `core.py`

```python
SCHEMA_VERSION = 1
EXTENSION_PREFIX = "x_"   # mismo patrón que tools/reporting/profiles/eda.py:43

TYPE_FAMILIES = ("string", "integer", "float", "boolean", "date", "datetime", "unknown")
DATASET_ROLES = ("raw_table", "feature_table", "scoring_output", "generic")
CONSTRAINT_TYPES = (
    "not_null", "unique", "allowed_values", "min_value", "max_value",
    "min_length", "max_length", "date_min", "date_max", "invariant",
)
SEVERITIES = ("FAIL", "WARN")   # mismos literales de texto que dsguard.checks.STATUS_FAIL/
                                 # STATUS_WARN (tools/dsguard/checks.py:14-17); NO se importa
                                 # checks.py -- coincidencia de vocabulario documentada, no
                                 # dependencia de código (decisión 3 del roadmap, ver más abajo).
COMPAT_ACTIONS = ("block", "warn", "allow")

class DataContractError(ValueError):
    """Violación de un contrato de datos (entrada estructuralmente inválida)."""
```

`DataContractError` es el análogo exacto de `ReportingContractError`
(`tools/reporting/core.py:82-84`): toda violación de forma al construir un objeto de este módulo
lanza esta excepción, nunca `TypeError`/`KeyError` crudos.

**Puente de `TYPE_FAMILIES` hacia los dtypes de `ds_profile` (decisión de diseño ya congelada,
documentada acá, NO implementada en este Change):** el core no importa `ds_profile` ni conoce su
vocabulario. Un futuro Change 1 mapea así, sin que este archivo lo declare en código (el mapeo
vive en el docstring, como contrato de intención, y el propio Change 1 lo codifica donde sí puede
importar ambos):

| `ContractField.type_family` | dtype de `ds_profile` (`column_stats.clasificar_dtype`,          |
|                              | `tools/ds_profile/column_stats.py:105-127`)                     |
|---|---|
| `"string"`   | `"texto"` |
| `"integer"`  | `"entero"` |
| `"float"`    | `"flotante"` |
| `"boolean"`  | `"booleano"` |
| `"date"`     | `"fecha"` (sin componente de hora) |
| `"datetime"` | `"fecha"` (con componente de hora — `ds_profile` no distingue date de datetime,   |
|              | ambas familias del contrato mapean al mismo dtype observado) |
| `"unknown"`  | sin mapeo — el Change 1 debe tratar un campo `"unknown"` como no verificable por |
|              | tipo (`WARN`/`N/A`, nunca `PASS`, coherente con decisión 3 del roadmap) |

### Dataclasses (todas `frozen=True`, `snake_case`, docstrings en español)

**IDs.** Reutiliza el patrón de ids de `tools/reporting/core.py:66-104`
(`^[a-z0-9][a-z0-9_-]{0,63}$`, más rechazo de nombres de dispositivo reservados de Windows) para
`contract_id`, `constraint_id`, `rule_id`, `policy_id`. Los nombres de **columna**
(`ContractField.name`) usan un patrón distinto, `snake_case` estricto de Python/pandas
(`^[a-z][a-z0-9_]*$`, sin guiones), porque deben poder mapear 1:1 a `schema`/`columnas_detalle`
de `profile.json` (`tools/ds_profile/report.py:217-218`), que son nombres de columna reales, no
nombres de archivo.

**`ContractField`** (capa schema/structure):
```
name: str                 # ^[a-z][a-z0-9_]*$
type_family: str          # ∈ TYPE_FAMILIES
required: bool = True      # el campo debe estar presente en la observación
nullable: bool = True      # el campo admite nulos
description: str = ""
extensions: dict = {}      # JSON-seguro; toda clave debe empezar con EXTENSION_PREFIX
```
Reglas: `name` cumple el patrón; `type_family ∈ TYPE_FAMILIES`; `required`/`nullable` son `bool`
estrictos; `extensions` es un `dict` JSON-seguro (mismo normalizador que
`tools/reporting/core.py:158-196`, adaptado sin `math` porque no hay floats no finitos en este
contexto salvo dentro de `extensions`, donde sí se reutiliza el chequeo de finitud) cuyas claves
cumplen `EXTENSION_PREFIX`.

**`Constraint`** (capa quality expectations — declara severidad, NO evalúa nada):
```
constraint_id: str         # patrón de id
constraint_type: str       # ∈ CONSTRAINT_TYPES
field: Optional[str] = None  # nombre de ContractField al que aplica; None = alcance de dataset
severity: str = "FAIL"     # ∈ SEVERITIES -- "qué pasa si se viola" (decisión 3 del roadmap)
params: dict = {}          # JSON-seguro, forma según constraint_type (ver abajo)
description: str = ""
```
`params` por `constraint_type` (validado en construcción, solo forma — nunca se evalúa contra
datos):
- `"not_null"`: `params` vacío o `{}` (la nulidad ya la declara `ContractField.nullable`; este
  tipo existe para declarar la regla como expectation de severidad independiente, p. ej. un campo
  `nullable=True` a nivel estructura pero con una expectation `WARN` de "en la práctica no
  debería haber nulos").
- `"unique"`: `params` opcional `{"fields": [...]}` (lista de nombres de campo para unicidad
  compuesta; si ausente, aplica a `field` solo).
- `"allowed_values"`: requiere `params["values"]` — lista no vacía de escalares JSON-seguros
  (`str`/`int`/`float` finito/`bool`/`None`), sin duplicados.
- `"min_value"` / `"max_value"`: requiere `params["value"]` — `int` o `float` finito (no `bool`).
- `"min_length"` / `"max_length"`: requiere `params["value"]` — `int >= 0` (no `bool`).
- `"date_min"` / `"date_max"`: requiere `params["value"]` — `str` no vacío (el core NO parsea
  fechas ni valida formato; eso es del Change 1 al comparar contra `fecha_min`/`fecha_max` del
  perfil).
- `"invariant"`: requiere `params["note"]` — `str` no vacío. Es una nota declarativa y acotada
  (`docs/roadmap/v0.7.md:169`), NUNCA una expresión ejecutable: el core no acepta código, lambda
  ni ningún campo tipo `expression`. Un invariante que involucra más de un campo puede listarlos
  en `params["fields"]` (opcional, solo referencia informativa).

Un `constraint_type` con una clave de `params` faltante o de tipo incorrecto para su forma
declarada arriba lanza `DataContractError`.

**`BusinessRule`** (capa semantic business rules — solo declarable, nunca evaluada):
```
rule_id: str
statement: str             # str no vacío; la regla de negocio en sí
rationale: str = ""
reference: Optional[str] = None   # texto libre (política, ticket, documento); str no vacío o None
```
Este módulo NO define ninguna función que evalúe un `BusinessRule` contra datos ni contra ningún
otro objeto — es responsabilidad estructural del módulo (verificable: ningún nombre de función de
`core.py` contiene "evaluate"/"evaluar"/"check" aplicado a `BusinessRule`).

**`ContractVersion`** (metadata versionada — NO lógica de diff/clasificación, eso es Change 4):
```
version: str                # ^\d+\.\d+\.\d+$ (semver simple: MAJOR.MINOR.PATCH)
summary: str = ""           # qué cambió, en texto declarado por el autor del contrato
previous_version: Optional[str] = None   # mismo patrón si no es None
```
`ContractVersion` es metadata pura: identifica una versión y enlaza opcionalmente con la
anterior por texto (linaje declarado, no calculado). No tiene `generated_at` ni ningún dato de
ejecución, por la misma razón que `Report` de reporting no lo lleva
(`tools/reporting/core.py:810-811`): así `DataContract.content_sha256()` identifica contenido,
no una corrida. La comparación real entre dos `ContractVersion` (para clasificar
`additive compatible`/`removal`/etc., `docs/roadmap/v0.7.md:373-379`) es del Change 4; este
Change no define ninguna función `compare`/`diff`.

**`CompatibilityPolicy`** (declaración de política — NO clasificación, eso es Change 4):
```
policy_id: str
on_removed_field: str            # ∈ COMPAT_ACTIONS
on_required_field_added: str     # ∈ COMPAT_ACTIONS
on_type_change: str              # ∈ COMPAT_ACTIONS
on_constraint_tightening: str    # ∈ COMPAT_ACTIONS
on_constraint_loosening: str     # ∈ COMPAT_ACTIONS
on_unknown_change: str           # ∈ COMPAT_ACTIONS
```
Los 6 campos son requeridos (sin default): la política debe declarar explícitamente qué hacer
ante cada categoría de cambio de la lista del Change 4
(`docs/roadmap/v0.7.md:373-379`), incluido `on_unknown_change` para la categoría
`"unknown / needs review"`. Este Change define solo el contrato de la política (qué acciones son
válidas); NO define ninguna función que compare dos `DataContract` y decida a qué categoría
pertenece un cambio real — eso es exactamente el trabajo del Change 4.

**`DataContract`** (raíz):
```
contract_id: str
version: ContractVersion
dataset_role: str                     # ∈ DATASET_ROLES
fields: tuple[ContractField]          # no vacía; nombres únicos
constraints: tuple[Constraint] = ()
business_rules: tuple[BusinessRule] = ()
keys: tuple[str] = ()                 # subconjunto de nombres de fields, sin duplicados
compatibility_policy: Optional[CompatibilityPolicy] = None
description: str = ""
extensions: dict = {}                 # JSON-seguro, claves EXTENSION_PREFIX
schema_version: int = SCHEMA_VERSION
```
Reglas de construcción (todas estructurales, mismo nivel que `Report.__post_init__`,
`tools/reporting/core.py:823-875`):
- `contract_id` cumple el patrón de id; `version` es instancia de `ContractVersion`;
  `dataset_role ∈ DATASET_ROLES`.
- `fields` no vacía; `ContractField.name` únicos entre sí.
- `constraints`: `constraint_id` únicos en todo el contrato; si `Constraint.field` no es `None`,
  debe existir entre los nombres de `fields` (y cada nombre de `params["fields"]`, cuando
  aplique, también); si no existe, `DataContractError` (una constraint que referencia un campo
  inexistente es un contrato mal formado, no una regla "no aplicable" — eso se decide en
  evaluación, Change 1).
- `business_rules`: `rule_id` únicos en todo el contrato (namespace propio, separado de
  `constraint_id`).
- `keys`: cada elemento ∈ nombres de `fields`, sin duplicados; puede ser vacía (sin key
  declarada).
- `compatibility_policy`: `None` o instancia de `CompatibilityPolicy`.
- `extensions` JSON-segura con claves `EXTENSION_PREFIX`.
- `schema_version` debe ser exactamente `SCHEMA_VERSION` (igual que
  `tools/reporting/core.py:836-843`).

Accesores (nunca lanzan, devuelven `None`/tupla vacía si no hay match — mismo patrón que
`Report.get_table`/`get_figure`, `tools/reporting/core.py:894-911`):
`get_field(name)`, `constraints_for(field_name)` (incluye las de alcance dataset si
`field_name is None`), `get_constraint(constraint_id)`, `get_business_rule(rule_id)`.

### Serialización determinista

Mismo patrón que `tools/reporting/core.py:264-276,960-963`: cada dataclass expone
`to_dict()`/`from_dict()` (orden de campos fijo, `from_dict` exige campos requeridos e ignora
claves desconocidas por forward-compat); `canonical_json(obj)` =
`json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)`;
`DataContract.content_sha256()` = sha256 hex de `canonical_json(self.to_dict())` en UTF-8. El
`DataContract` no lleva `generated_at` ni ningún dato de ejecución: la evidencia de una
evaluación (Change 1) y su `generated_at` viven en un objeto y una ubicación distintos, nunca
dentro de la declaración (regla explícita del roadmap,
`docs/roadmap/v0.7.md:124-125`).

**Política de evolución del esquema** (idéntica a `tools/reporting/core.py:21-28`): todo campo
nuevo en el `to_dict()` de cualquier contrato de este módulo cambia `content_sha256()` y por lo
tanto REQUIERE bump de `SCHEMA_VERSION`. `content_sha256()` es la identidad del objeto
re-serializado, no de los bytes persistidos de un archivo (esa distinción, y quién hashea los
bytes persistidos, es del Change 3).

### Relación `ContractVersion`/`CompatibilityPolicy` con este Change vs. Change 4

Este Change declara ambos tipos como **contratos de datos/política en sí mismos** (metadata
versionada serializable, acción declarada por categoría de cambio) — ninguno de los dos contiene
ni un método `diff`, ni `compare`, ni `classify`, ni ninguna lógica que examine dos
`DataContract` y decida algo. La clasificación determinista real (comparar dos versiones de un
`DataContract` y decidir `additive compatible`/`removal`/`required-field addition`/
`type change`/`constraint tightening`/`constraint loosening`/`unknown / needs review`) es
íntegramente del Change 4 (`docs/roadmap/v0.7.md:371-381`), que consumirá estos tipos como
entrada y salida de su propia función de clasificación (probablemente en un módulo aparte,
p. ej. `tools/datacontracts/evolution.py`, a decidir en el SDD de ese Change).

### Texto exacto de la regla 7 de `ARCHITECTURE.md`

A insertar en `ARCHITECTURE.md` §3 (tras la regla 6 existente), por la siguiente invocación:

> 7. Familia `tools/datacontracts` (v0.7): `core.py` es solo-stdlib y no importa hermanos ni
>    ningún paquete existente. En Changes posteriores (no en Change 0, que no produce
>    `CheckResult`), los módulos de la familia podrán importar `dsguard.checks` (para producir
>    resultados `PASS`/`WARN`/`FAIL`/`N/A`) y leer `profile.json` de `ds_profile` como archivo
>    persistido (nunca importar `ds_profile` como librería para observar datos, salvo una
>    extensión aditiva de `ds_profile` decidida explícitamente en SDD, ver decisión 2 de
>    `docs/roadmap/v0.7.md`); pero nunca al revés: `dsguard`, `ds_profile`, `dsimpact`,
>    `reporting`, `providers`, `routing`, `fallback` y `harmessi_bench` no importan
>    `tools/datacontracts`. Verificado por `tools/tests/test_v07_core_neutrality.py`.

Y la fila correspondiente en §2.1 (inventario de core), estilo idéntico a la fila de
`tools/reporting/core.py` (`ARCHITECTURE.md:46`):

> `tools/datacontracts/core.py` | Contratos neutrales de datos (v0.7 Change 0:
> `DataContract`/`ContractField`/`Constraint`/`BusinessRule`/`ContractVersion`/
> `CompatibilityPolicy`, serialización determinista y hash de contenido) -- solo stdlib; no
> observa ni evalúa ningún dato, no importa `ds_profile`, `dsguard` ni ningún hermano; separa
> estructura (schema), calidad esperada (expectations con severidad declarada) y reglas de
> negocio (solo declarables, nunca evaluadas); no conoce protocolo de hooks, es core.

### Instalabilidad

Dos entradas `VERBATIM` en `MANIFEST` (`tools/datacontracts/__init__.py`,
`tools/datacontracts/core.py`) con `stage_minimo` por defecto (`"discovery"`, mismo criterio que
reporting: la declaración de un contrato de datos es actividad temprana, disponible desde el
primer stage). Los tests del paquete no se instalan (mismo patrón que
`tools/reporting/tests/`). Insertar las entradas sin alterar el orden relativo del resto del
`MANIFEST`; los tests existentes de `tools/ds_init/tests/test_manifest.py` (destinos sin
overlap, ningún destino en `EXCLUSIONES_PERMANENTES`, bundles monotónicos) deben seguir verdes
sin edición, igual que ocurrió con las dos entradas de `tools/reporting`
(`openspec/changes/20260918-reporting-core/design.md:77-82`).

## Target (condicional — feature_engineering, modeling)
No aplica.

## Features permitidas/prohibidas (condicional — feature_engineering)
No aplica.

## Estrategia de split/validación (condicional — holdout involucrado, modeling, evaluation)
No aplica: no se toca ningún dataset ni holdout.

## Leakage risks (condicional — feature_engineering, data_preparation, modeling)
No aplica a datos. Riesgo de diseño relacionado, mitigado en este Change: si `Constraint` o
`BusinessRule` permitieran una expresión ejecutable arbitraria, un futuro evaluador (Change 1)
podría terminar corriendo código sobre datos sin pasar por `ds_profile`, duplicando el
observador (prohibido por decisión 2 del roadmap). Mitigación: `params`/`statement` son siempre
texto/escalares declarativos, nunca código.

## Reproducibilidad (opcional — solo si se desvía del default: RANDOM_STATE fijo, .venv)
No aplica aleatoriedad: no hay `RANDOM_STATE`. El determinismo se garantiza por serialización
canónica (`sort_keys`, separadores fijos, sin `NaN`, sin timestamps), igual que en
`tools/reporting/core.py`.

## Alternativas descartadas (adicionales a la elección de nombre de paquete, ver arriba)
1. **Fusionar `ContractField` y `Constraint` en un solo objeto** (cada campo lleva sus propias
   reglas de rango/dominio inline): rechazada; el roadmap exige separar explícitamente
   schema/structure de quality expectations (`docs/roadmap/v0.7.md:174-179`), y una constraint
   de alcance dataset (invariante entre columnas, unicidad compuesta) no tiene un único campo
   dueño natural.
2. **Un solo campo `severity` a nivel `DataContract`** en vez de por `Constraint`: rechazada;
   decisión 3 del roadmap exige que "cada regla declare qué pasa si se viola", no el contrato
   completo.
3. **`ContractVersion` como `int` simple** (como `Report.schema_version`) en vez de un objeto con
   semver + `summary` + `previous_version`: rechazada; el roadmap pide `ContractVersion` como
   concepto propio distinto de `schema_version` (que es la versión del *esquema de este módulo*,
   no la versión del contrato de negocio declarado por el autor).
4. **Incluir en este Change una función `evaluate(contract, profile) -> list[CheckResult]`** (aun
   como stub): rechazada explícitamente; el roadmap dice "este Change no observa ni evalúa nada"
   (`docs/roadmap/v0.7.md:146-147`); incluso un stub crearía una superficie de API que el
   Change 1 tendría que romper o mantener por compatibilidad.
5. **Permitir que `Constraint.params["invariant"]` acepte una expresión Python (`eval`/`lambda`)
   serializada como string**: rechazada de plano; viola la prohibición explícita de DSL de
   expresiones arbitrarias (`docs/roadmap/v0.7.md:183`) y abre una superficie de ejecución de
   código no controlada.
6. **Reusar el mismo patrón de id (`^[a-z0-9][a-z0-9_-]{0,63}$`) también para
   `ContractField.name`**: rechazada; los nombres de columna deben coincidir con convenciones de
   pandas/`ds_profile` (`snake_case`, sin guiones) para ser puenteables 1:1 contra
   `schema`/`columnas_detalle` de `profile.json` sin transformación.
7. **Importar `dsguard.checks.STATUS_FAIL`/`STATUS_WARN` para construir `SEVERITIES`**:
   rechazada en este Change; aunque la dirección de dependencia lo permitiría en Changes
   posteriores (`docs/roadmap/v0.7.md:118-119`, "los paquetes de v0.7 pueden importar
   `dsguard.checks`"), el roadmap dice explícitamente "no en Change 0" (instrucción de esta
   invocación) porque este Change no produce `CheckResult` — se usa el mismo literal de texto
   sin import, documentado como coincidencia de vocabulario intencional.

## Riesgos
- **`Constraint.params` como `dict` sin schema tipado por Python** (a diferencia de campos
  declarados como atributos de dataclass): mitigado con validación explícita por
  `constraint_type` en `__post_init__` (ver tabla arriba) y tests que cubren cada tipo con
  params válidos e inválidos.
- **Referencias sin resolver más allá de `fields`**: `Constraint.field`/`params["fields"]` deben
  existir entre `DataContract.fields` (se valida en construcción, a diferencia de
  `FigureArtifact.backing_table_id` en reporting, que se deja sin resolver a propósito). Motivo
  de la diferencia: en reporting la referencia sin resolver es aceptable porque el reporte puede
  construirse incrementalmente antes de tener todos los artefactos; en un `DataContract` no hay
  ninguna razón operativa para declarar una regla sobre un campo que el propio contrato no
  define — es directamente un contrato mal formado.
- **Ambigüedad `not_null` vs `ContractField.nullable`**: documentada explícitamente en la
  descripción del `constraint_type` `"not_null"` (arriba); son capas distintas (estructura vs.
  expectation con severidad propia) y pueden coexistir o divergir a propósito.
- **`SEVERITIES` como literales de texto duplicados de `dsguard.checks`** (en vez de importarlos):
  riesgo de drift de vocabulario si `dsguard.checks` cambiara sus literales; mitigado con un
  comentario explícito en el código y un test que documenta la igualdad esperada (sin importar
  `dsguard`), mismo patrón que la deuda 6 de `ARCHITECTURE.md` §4.1 ya reconoce para otros
  duplicados — se declara como deuda vigilada, no se resuelve acá (Change 0 no puede importar
  `dsguard.checks`).
- **`frozen=True` no implica inmutabilidad profunda**: `params`/`extensions` son `dict`; mismo
  riesgo y mitigación que en reporting (`openspec/changes/20260918-reporting-core/design.md:140-144`)
  — copia profunda al construir, identidad de contenido vía `content_sha256()`, no `__hash__`.
- **Precedente de instalación**: segundo paquete nuevo de v0.7 en `MANIFEST` tras
  `tools/reporting`; cada módulo futuro de `tools/datacontracts` (Change 1 en adelante)
  necesitará su propia entrada (mismo riesgo de mantenimiento ya reconocido en
  `openspec/changes/20260918-reporting-core/design.md:159-161`).

## Aprobación humana
El registro de aprobación (usuario, fecha, alcance, versión de artefactos, cita) es único por
cambio y vive en la sección "Aprobación" de `proposal.md` — no se duplica acá.

# Spec — 20260918-reporting-core

## Requisitos

- **R1 — Paquete y módulo solo-stdlib**: existe `tools/reporting/__init__.py` (sin lógica ni
  imports de hermanos) y `tools/reporting/core.py`. `core.py` importa únicamente de la stdlib:
  `dataclasses`, `hashlib`, `json`, `math`, `re`, `copy`, `typing` (más `__future__`, patrón ya
  usado en el repo). No importa Plotly, HTML/templating, pandas, numpy, `dsguard`,
  `ds_profile`, nada bajo `tools.*` ni ningún módulo hermano de `tools/reporting`. No conoce EDA
  ni ningún dominio: ningún nombre importado, constante ni identificador de `core.py` referencia
  una técnica, un dominio o un backend gráfico concreto. Las dataclasses son `frozen=True`;
  docstrings/comentarios en español; nombres en `snake_case`.

- **R2 — Vocabularios y constantes (tuplas de módulo)**:
  `REPORT_KINDS = ("eda", "model", "evaluation", "production")`;
  `DECISION_SCOPES = ("exploratory", "model_valid", "operational")`;
  `CLAIM_TYPES = ("descriptive", "comparative", "associative", "predictive", "causal",
  "recommendation")`;
  `CHART_TYPES = ("bar", "line", "scatter", "histogram", "box", "heatmap")`;
  `SEMANTIC_ROLES = ("risk", "status")`; `ORIENTATIONS = ("v", "h")`;
  `REPORT_FILENAME = "report.html"`, `MANIFEST_FILENAME = "manifest.json"`,
  `INSIGHTS_FILENAME = "insights.json"`, `ARTIFACTS_DIRNAME = "artifacts"`;
  `SCHEMA_VERSION = 1`. Excepción `ReportingContractError(ValueError)`. Todo error de contrato
  del módulo lanza `ReportingContractError` (nunca `TypeError`/`KeyError` crudos por entrada
  inválida del usuario).

- **R3 — Ortogonalidad `report_kind` × `decision_scope`**: son campos independientes de
  `Report`; cada uno se valida solo contra su propio vocabulario. Las 4×3 = 12 combinaciones son
  construibles en el core. Cualquier restricción entre ellos es política de governance
  (Change 1), no del core.

- **R4 — IDs seguros**: `report_id`, `chapter_id`, `table_id`, `figure_id`, `insight_id` deben
  ser `str` y cumplir `^[a-z0-9][a-z0-9_-]{0,63}$` (aptos como nombre de archivo: sin puntos, ni
  separadores de ruta, ni mayúsculas). Ids seguros como nombre de archivo también en Windows:
  se rechazan además los nombres de dispositivo reservados (`con`, `prn`, `aux`, `nul`,
  `com1`..`com9`, `lpt1`..`lpt9`). Un id inválido lanza `ReportingContractError` al construir.

- **R5 — `TableArtifact`**: campos `table_id, title, columns (tuple[str]), rows
  (tuple[tuple]), units (dict col→str), column_labels (dict col→str), description,
  sensitive (bool)`. Reglas: `columns` no vacía, sin duplicados, cada elemento `str` no vacío;
  cada fila con `len == len(columns)`; celdas JSON-seguras (`str`, `int`, `bool`, `None`,
  `float` finito); claves de `units` y `column_labels` ⊆ `columns` con valores `str`; `rows`
  (y cada fila) se normalizan a `tuple`. El constructor directo es estricto: rechaza `float`
  no finito (NaN/±inf). Constructores alternativos:
  `TableArtifact.from_rows(...)` normaliza `float` no finito → `None` y `list` → `tuple`;
  `TableArtifact.from_frame(frame, ...)` usa duck typing (no importa pandas): lee
  `frame.columns` y obtiene las filas con `frame.astype(object).values.tolist()` si `frame`
  tiene `astype` (verificado con `hasattr`), de modo que los enteros no se promueven a
  `float`; solo si `frame` no tiene `astype` cae al fallback `frame.values.tolist()`. Coerciona
  cada celda así: `None` → `None`;
  `bool` → `bool`; `int` → `int`; `float` → `float` si es finito, si no `None`; `str` → `str`
  (valores nativos, sin retener subclases externas); un objeto distinto de sí mismo
  (`x != x`, p. ej. NaT/NA de cualquier librería) → `None`; objeto con `isoformat()` → `str` ISO; objeto con `item()` (escalar numpy) → recursión sobre
  `.item()`; cualquier otro tipo → `ReportingContractError`.

- **R6 — `FigureSpec`** (especificación declarativa neutral; referencia columnas de la tabla de
  respaldo; ningún backend): `chart_type` (∈ `CHART_TYPES`), `x` (`str` no vacío),
  `y (tuple[str])`, `color (Optional[str])`, `z (Optional[str])`,
  `orientation ("v"|"h", default "v")`, `top_n (Optional[int] > 0)`,
  `sort (Optional["ascending"|"descending"])`, `x_label`, `y_label`, `unit`,
  `denominator (Optional[str])` (columna con el tamaño de grupo que acompaña a una tasa),
  `semantic (Optional[SEMANTIC_ROLES])`. Reglas: `y` con al menos un elemento salvo en
  `histogram`; `heatmap` requiere `z`. `columns_used() -> tuple[str]` devuelve
  `x, *y, color, z, denominator` sin `None`, sin duplicados y ordenado.

- **R7 — `FigureArtifact`**: campos `figure_id, title, spec (FigureSpec),
  backing_table_id (Optional[str]), description, alt_text, sensitive (bool),
  backend (Optional[str]), backend_payload (Optional[dict])`. `backing_table_id` puede ser
  `None` en construcción (el "gráfico sin tabla de respaldo" lo reporta el validador del
  Change 3 como `FAIL`); si no es `None` debe cumplir R4. `backend` y `backend_payload` son
  ambos `None` o ambos presentes (`backend` = `str` no vacío, `backend_payload` = dict
  JSON-seguro); el core los guarda sin interpretarlos.

- **R8 — `Insight`**: campos `insight_id, technical_claim, business_claim,
  evidence_refs (tuple[str]), population, time_scope, claim_type (∈ CLAIM_TYPES),
  uncertainty (str, default ""), title (str, default "")`. En construcción solo son estrictos
  tipos, enum e ids (`insight_id` y cada elemento de `evidence_refs` cumplen R4). Claims
  vacíos o `evidence_refs` vacío NO lanzan (Change 3).

- **R9 — `Chapter`**: campos `chapter_id, title, summary, tables (tuple), figures (tuple),
  insights (tuple), method_note, metadata (dict JSON-seguro)`. Cada elemento de `tables` es
  `TableArtifact`, de `figures` `FigureArtifact`, de `insights` `Insight`; contenedores
  `list` se normalizan a `tuple`. `metadata` es genérico (un profile adjunta sus etiquetas sin
  que el core las conozca).

- **R10 — `Report`**: campos `report_id, title, report_kind, decision_scope, chapters (tuple),
  summary, conclusion, metadata (dict JSON-seguro), schema_version`. Unicidad: `chapter_id`
  únicos entre capítulos; `table_id` y `figure_id` comparten un único namespace en todo el
  `Report` (`evidence_refs` inambiguo); `insight_id` únicos entre todos los insights del
  `Report`. Duplicados lanzan `ReportingContractError`. Accesores: `iter_tables()`,
  `iter_figures()`, `iter_insights()` (orden de capítulos, luego de declaración),
  `get_table(id)`, `get_figure(id)`, `get_artifact(id)`: devuelven `None` si el id no existe
  (no lanzan). `report` no lleva `generated_at` ni ningún dato de ejecución.

- **R11 — Política de validación en construcción**: estricta y solo estructural (enums, ids,
  tipos, duplicados, forma de tabla, JSON-seguridad). La completitud semántica/evidencial no
  se valida en construcción: figura sin `backing_table_id`, `backing_table_id` o
  `evidence_refs` que no resuelven a un artefacto del `Report`, columnas de `FigureSpec` que no
  existen en la tabla de respaldo, claims vacíos, insight sin evidencia. Esas comprobaciones
  son del Change 3 (`FAIL`/`WARN`). `metadata` y `backend_payload` se copian en profundidad al
  construir (no se comparte el dict del llamador) y se normalizan a estructura JSON pura
  (`tuple` → `list`, claves `str`).

- **R12 — Serialización determinista**: cada contrato expone `to_dict()` (orden de campos
  fijo, solo tipos JSON) y `from_dict()` (estricto en campos requeridos y, en `Report`, en
  `schema_version`; ignora claves desconocidas por forward-compat). `canonical_json(obj)` =
  `json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)`
  (un fallo de serialización se reporta como `ReportingContractError`).
  `Report.content_sha256()` = sha256 (hex) de `canonical_json(self.to_dict())` codificado en
  UTF-8. Para el mismo contenido el hash es idéntico entre corridas y tras
  `from_dict(to_dict())`.

- **R13 — Instalabilidad**: `tools/ds_init/manifest.py` agrega dos `EntradaManifiesto`
  VERBATIM (`tools/reporting/__init__.py`, `tools/reporting/core.py`; `fuente == destino`) con
  `stage_minimo` por defecto (`discovery`). Los tests de `tools/reporting/tests/` no van al
  manifest. `tools/ds_init/tests/test_manifest.py` y todo test que dependa de exclusiones,
  destinos únicos o monotonía de bundles siguen verdes sin editarse.

- **R14 — Arquitectura y frontera**: `ARCHITECTURE.md` §2.1 tiene una fila para
  `tools/reporting/core.py` (core neutral, solo-stdlib) y §3 una regla 6: en la familia
  `tools/reporting`, `core.py` es solo-stdlib y no importa hermanos; los módulos posteriores de
  la familia (governance/evidence/perfiles/renderer) podrán importar `dsguard` y
  `ds_profile.fingerprint`, pero nunca al revés (`dsguard`, `ds_profile`, `dsimpact`,
  `providers`, `routing`, `fallback`, `harmessi_bench` no importan `reporting`).
  `tools/reporting/core.py` se agrega a `MODULOS_CORE` de
  `tools/tests/test_architecture_boundaries.py` (misma lista que §2.1).
  `tools/tests/test_v06_core_neutrality.py` (patrón `ast` de `test_v05_core_neutrality.py`)
  verifica R1 y la dirección inversa de la regla 6.

- **R15 — Backward compatibility**: ningún archivo existente cambia de comportamiento. Las
  únicas modificaciones a archivos existentes son aditivas: dos entradas en `MANIFEST`, una
  fila y una regla en `ARCHITECTURE.md`, una línea en `MODULOS_CORE`, y el estado del roadmap
  `docs/roadmap/v0.6.md`. Ningún módulo existente importa `tools.reporting`.

- **R16 — Roadmap**: `docs/roadmap/v0.6.md` reemplaza el bloque "Estado: PLANIFICADA..." por
  el estado real "EN CURSO en `v0.6-dev`"; al cerrar el Change (invocación de cierre) se tilda
  `[x] Change 0`. Nada más del roadmap cambia; v0.7–v0.9 no se tocan.

- **R17 — Tests deterministas**: `tools/reporting/tests/test_core.py` (unittest) y
  `tools/reporting/tests/test_installability.py`, más `tools/tests/test_v06_core_neutrality.py`,
  sin I/O de red, sin pandas/numpy (los duck types se simulan con clases de prueba), sin
  aleatoriedad.

## Criterios de aceptación

**R1/R14 — neutralidad**
- Given `tools/reporting/core.py`, When `test_v06_core_neutrality.py` recorre su AST, Then
  todos los imports de nivel de módulo pertenecen a `{__future__, dataclasses, hashlib, json,
  math, re, copy, typing}` y ninguno referencia `plotly`, `pandas`, `numpy`, `html`, `dsguard`,
  `ds_profile` ni `tools`/hermanos de `reporting`.
- Given los módulos de `dsguard`, `ds_profile`, `dsimpact`, `providers`, `routing`, `fallback`
  y `harmessi_bench`, When se escanean sus imports, Then ninguno importa `reporting`.
- Given `MODULOS_CORE`, Then contiene `tools/reporting/core.py` y
  `test_architecture_boundaries.py` sigue verde (ningún adapter importado, sin `sys.stdin`).

**R2/R3 — vocabularios y ortogonalidad**
- Given cada uno de los 4 `REPORT_KINDS` y cada uno de los 3 `DECISION_SCOPES`, When se
  construye un `Report` mínimo, Then las 12 combinaciones se construyen sin error y conservan
  ambos valores intactos.
- Given `report_kind="invalido"` o `decision_scope="invalido"`, Then
  `ReportingContractError`.
- Given los vocabularios de R2, Then coinciden exactamente (contenido y orden) con los
  declarados.

**R4 — IDs**
- Given ids `"a"`, `"tabla_1"`, `"x-y_2"` y uno de 64 caracteres, Then son válidos.
- Given `""`, `"A"`, `"-x"`, `"a.b"`, `"a/b"`, `"a b"`, un id de 65 caracteres o un no-`str`,
  Then `ReportingContractError` en cada contrato que lo reciba.
- Given ids `"con"`, `"nul"`, `"com1"`, `"lpt9"` (nombres reservados de Windows), Then
  `ReportingContractError`; `"console"` y `"com10"` son válidos.

**R5 — `TableArtifact`**
- Given columnas vacías, duplicadas o con un elemento vacío/no-`str`, Then error.
- Given una fila con largo distinto a `len(columns)`, Then error.
- Given una celda `float("nan")`/`float("inf")` en el constructor directo, Then error; en
  `from_rows` la misma celda queda `None`.
- Given `rows` como lista de listas, Then `t.rows` es `tuple` de `tuple`.
- Given una celda `list`/`dict`/objeto arbitrario en el constructor directo, Then error.
- Given `units` o `column_labels` con una clave fuera de `columns`, Then error.
- Given un frame simulado (`columns` + `values.tolist()`) con `None`, `bool`, `int`, `float`
  NaN, `str`, un objeto con `isoformat()`, un escalar simulado con `item()` y un objeto sin
  ninguno de los anteriores, When `from_frame`, Then las celdas quedan `None`, `bool`, `int`,
  `None`, `str`, `str` ISO, el valor de `.item()` coercionado, y el último caso lanza
  `ReportingContractError`.
- Given un frame simulado con `astype(object)` cuyo `values.tolist()` conserva enteros como
  `int` (y cuyo `values` sin `astype` los devolvería como `float`), When `from_frame`, Then las
  celdas enteras quedan como `int`.
- Given un frame simulado sin `astype` (solo `columns` y `values.tolist()`), When
  `from_frame`, Then usa el fallback `frame.values.tolist()` y produce la tabla sin error.
- Given `test_core.py`, Then no importa pandas ni numpy.

**R6/R7 — figuras**
- Given `FigureSpec(chart_type="pie", ...)`, `x=""`, `orientation="d"`, `top_n=0`,
  `sort="asc"` o `semantic="otro"`, Then error.
- Given `chart_type="bar"` con `y=()`, Then error; con `chart_type="histogram"` y `y=()`,
  Then válido.
- Given `chart_type="heatmap"` sin `z`, Then error; con `z`, válido.
- Given `x="a"`, `y=("b","a")`, `color="c"`, `z=None`, `denominator="c"`, Then
  `columns_used() == ("a", "b", "c")`.
- Given una `FigureArtifact` con `backing_table_id=None`, Then se construye sin error.
- Given `backend="x"` sin `backend_payload` (o al revés), Then error; ambos presentes con
  payload JSON-seguro, válido; payload con `float("nan")` u objeto no JSON, error.
- Given un `backend_payload` mutado por el llamador después de construir, Then la
  `FigureArtifact` no cambia (copia profunda).

**R8 — `Insight`**
- Given un `Insight` con `claim_type="otro"`, Then error; con `evidence_refs=()`,
  claims vacíos, Then se construye sin error.
- Given un `evidence_refs` con un id inválido, Then error.
- Given un `Insight` con los 7 campos y sin `uncertainty`/`title`, Then ambos valen `""`.

**R9/R10 — `Chapter` y `Report`**
- Given dos capítulos con el mismo `chapter_id`, Then error.
- Given una tabla y una figura con el mismo id (aunque en capítulos distintos), Then error.
- Given dos insights con el mismo `insight_id` (aunque en capítulos distintos), Then error;
  un insight con el mismo id que una tabla es válido (namespaces distintos).
- Given un `Report` válido, Then `get_table`/`get_figure`/`get_artifact` devuelven el objeto y
  devuelven `None` para un id inexistente sin lanzar; `iter_*` respeta el orden de
  declaración.
- Given un `Report` con figura sin tabla de respaldo, `evidence_refs` a un id inexistente y un
  insight sin claims, Then se construye sin error.
- Given un `metadata` con un valor no JSON (objeto, `nan`, clave no-`str`), Then error; dado un
  `metadata` mutado luego por el llamador, Then el `Report` no cambia.

**R12 — serialización determinista**
- Given dos `Report` construidos con los mismos datos en distinto orden de claves de
  `metadata`, Then `content_sha256()` es igual.
- Given un `Report` completo, Then `Report.from_dict(r.to_dict()) == r` y
  `content_sha256()` idéntico; `to_dict()` es serializable con `json.dumps` y `canonical_json`
  no contiene espacios extra ni escapa caracteres no ASCII.
- Given `from_dict` con un campo requerido ausente, `schema_version` ausente o distinto de
  `1`, Then `ReportingContractError`; con claves desconocidas extra, las ignora.
- Given `canonical_json({"a": float("nan")})`, Then `ReportingContractError`.
- Given cambiar un solo valor de una celda, Then el hash cambia; `Report` no expone
  `generated_at`.

**R13 — instalabilidad**
- Given `MANIFEST`, Then contiene exactamente una entrada con `destino` (y `fuente`)
  `tools/reporting/__init__.py` y una con `tools/reporting/core.py`, ambas `VERBATIM` y con
  `stage_minimo == "discovery"`, y ambas rutas existen en el repo.
- Given `manifest_para_perfil_y_stage(perfil, "discovery")`, Then incluye ambos destinos.
- Given `tools/ds_init/tests/test_manifest.py` y `tools/tests/test_manifest_dsguard_parity.py`
  sin modificar, Then siguen verdes; ningún destino nuevo cae en `EXCLUSIONES_PERMANENTES`.

**R15/R16 — compatibilidad y roadmap**
- Given `git diff` del Change, Then los archivos preexistentes modificados son solo
  `manifest.py`, `ARCHITECTURE.md`, `test_architecture_boundaries.py`, `docs/roadmap/v0.6.md`
  (y `control.json`/artefactos SDD de este Change), con cambios aditivos; la suite completa
  previa corre igual que en el baseline.
- Given `docs/roadmap/v0.6.md`, Then no contiene "Sin branch `v0.6-dev`" y declara "EN CURSO"
  en `v0.6-dev`; al cierre `[x] Change 0`, sin tocar los demás Changes ni v0.7–v0.9.

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

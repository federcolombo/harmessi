# Diseño — 20260918-reporting-core

## Decisión metodológica/técnica
Principio permanente: "LLM decide lo semántico; el binario calcula y hace cumplir lo
determinista". Flujo de v0.6: Proyecto/Notebook → Report objects → Governance →
Evidence/Validation → Design System → Renderer → `report.html` + `manifest.json` +
`insights.json` + `artifacts/`. El notebook calcula; Harmessi gobierna, valida, registra y
renderiza. `.ipynb` es el artefacto reproducible; `.html` el de comunicación. Este Change
implementa únicamente el eslabón "Report objects".

**Paquete nuevo `tools/reporting/`.** El módulo `core.py` es solo-stdlib
(`dataclasses, hashlib, json, math, re, copy, typing`, más `__future__`); no importa Plotly,
HTML, pandas, numpy, `dsguard` ni ningún hermano de `tools/reporting`; no conoce EDA ni ningún
dominio. Dataclasses `frozen=True`, docstrings/comentarios en español, `snake_case`.
`__init__.py` queda sin lógica ni imports (para no acoplar la instalación de `core.py` a
módulos que aún no existen).

**Ortogonalidad.** `report_kind` (qué es el reporte) y `decision_scope` (para qué decisiones
sirve) son campos independientes de `Report`, cada uno validado solo contra su vocabulario. Las
12 combinaciones son construibles; una restricción entre ellos (p. ej. `production` exige
`operational`) es política y vive en governance (Change 1). Un test recorre las 12
combinaciones.

**Contratos (todos `frozen=True`)**
- `TableArtifact(table_id, title, columns, rows, units, column_labels, description,
  sensitive)`. Constructor directo estricto; `from_rows` normaliza no finitos a `None` y
  listas a tuplas; `from_frame` hace duck typing (sin importar pandas): lee `frame.columns` y
  obtiene las filas con `frame.astype(object).values.tolist()` si `frame` tiene `astype`
  (`hasattr`), para no promover enteros a `float`; solo si no lo tiene usa el fallback
  `frame.values.tolist()`. Coerción de celdas: `None`, `bool`, `int`,
  `float` finito o `None`, `str`, `isoformat()` → `str`, `item()` → recursión, otro tipo →
  error. Las celdas de `bool` se evalúan antes que `int` (`bool` es subclase de `int`).
- `FigureSpec`: especificación declarativa del gráfico que referencia columnas de la tabla de
  respaldo; no lleva ningún dato ni backend. `columns_used()` expone las columnas que el
  Change 3 comprobará contra `TableArtifact.columns`.
- `FigureArtifact(figure_id, title, spec, backing_table_id, description, alt_text, sensitive,
  backend, backend_payload)`: `backing_table_id` puede ser `None` al construir;
  `backend`/`backend_payload` son un escape hatch opaco (ambos o ninguno) que el core no
  interpreta.
- `Insight`: separa `technical_claim` y `business_claim` (el renderer muestra el segundo; el
  Lead/metodólogo/reviewer auditan el primero más la evidencia) y modela `evidence_refs`,
  `population`, `time_scope`, `claim_type`, `uncertainty`.
- `Chapter`: agrupa tablas, figuras e insights; su `metadata` JSON-seguro genérico permite que
  un profile (p. ej. EDA) adjunte sus etiquetas sin que el core lo conozca.
- `Report`: raíz del árbol; impone unicidad de `chapter_id`, un único namespace para
  `table_id` + `figure_id` (así `evidence_refs` apunta a un artefacto de forma inambiguna) y
  unicidad de `insight_id`.

**IDs.** Regex `^[a-z0-9][a-z0-9_-]{0,63}$`: seguros como nombre de archivo (el renderer y
`artifacts/` los usarán tal cual), sin puntos ni separadores de ruta. Ids seguros como nombre de
archivo también en Windows: se rechazan los nombres de dispositivo reservados (`con`, `prn`,
`aux`, `nul`, `com1`..`com9`, `lpt1`..`lpt9`).

**Política de evolución del esquema.** Todo campo nuevo en el `to_dict()` de un contrato cambia
`content_sha256()` y por lo tanto REQUIERE bump de `SCHEMA_VERSION`. `content_sha256()` es la
identidad del objeto re-serializado; como `from_dict` ignora claves desconocidas, el hash de los
bytes persistidos de un artefacto y el del objeto pueden diferir: el Change 3 debe hashear los
BYTES persistidos de cada artefacto además del hash de contenido del objeto.

**Política de validación.** En construcción: estricta y solo estructural (enums, ids, tipos,
duplicados, forma de tabla, JSON-seguridad). La completitud semántica/evidencial (figura sin
tabla de respaldo, referencias que no resuelven, columnas ausentes en la tabla, insight sin
evidencia, claims vacíos) no se valida en construcción: la hace la validación determinista del
Change 3 devolviendo `FAIL`/`WARN`. Motivo: un notebook debe poder construir el objeto y recibir
un resultado de validación, no una excepción a mitad de un análisis.

**Serialización determinista.** `to_dict()`/`from_dict()` por contrato (orden de campos fijo;
`from_dict` estricto en campos requeridos y `schema_version`, ignora claves desconocidas por
forward-compat). `canonical_json(obj)` = `json.dumps(obj, sort_keys=True,
separators=(",", ":"), ensure_ascii=False, allow_nan=False)`. `Report.content_sha256()` =
sha256 de `canonical_json(to_dict())` en UTF-8; el `Report` no lleva timestamps ni datos de
ejecución (el `generated_at` pertenece al manifest del Change 3), de modo que el hash
identifica contenido, no una corrida. `metadata` y `backend_payload` se copian en profundidad y
se normalizan a JSON puro (`tuple` → `list`) al construir, para que `from_dict(to_dict())`
reproduzca exactamente el mismo `to_dict()`.

**Instalabilidad.** Dos entradas VERBATIM en `MANIFEST` (`tools/reporting/__init__.py`,
`tools/reporting/core.py`) con `stage_minimo` por defecto (`discovery`, porque EDA es actividad
de discovery). Los tests no se instalan. Insertar las entradas junto al resto de paquetes (tras
la de `tools/dsimpact/scan.py`) no altera el orden relativo del resto; los tests de manifest
(`test_manifest.py:37-39`, `:57-63`, `:176-187`) siguen verdes sin edición porque las entradas
nuevas son `discovery` y sus destinos son únicos y no caen en exclusiones.

**Arquitectura.** `ARCHITECTURE.md` §2.1 fila nueva y §3 regla 6: la familia `tools/reporting`
—`core.py` solo-stdlib y sin hermanos; módulos posteriores (governance/evidence/perfiles/
renderer) podrán importar `dsguard` y `ds_profile.fingerprint`, nunca al revés (`dsguard`,
`ds_profile`, `dsimpact`, `providers`, `routing`, `fallback`, `harmessi_bench` no importan
`reporting`). `tools/reporting/core.py` entra en `MODULOS_CORE`. Un test nuevo
(`test_v06_core_neutrality.py`, mismo patrón `ast` que `test_v05_core_neutrality.py`) hace
cumplir la regla.

## Target (condicional — feature_engineering, modeling)
No aplica.

## Features permitidas/prohibidas (condicional — feature_engineering)
No aplica.

## Estrategia de split/validación (condicional — holdout involucrado, modeling, evaluation)
No aplica: no se toca ningún dataset ni holdout.

## Leakage risks (condicional — feature_engineering, data_preparation, modeling)
No aplica a datos. Riesgo de gobernanza relacionado, fuera de este Change: si `decision_scope`
`exploratory` y `model_valid` no se distinguen mecánicamente, un output exploratorio podría
alimentar modelado; el core solo entrega el campo separado, la aplicación mecánica es del
Change 1.

## Reproducibilidad (opcional — solo si se desvía del default: RANDOM_STATE fijo, .venv)
No aplica aleatoriedad: no hay `RANDOM_STATE`. El determinismo se garantiza por serialización
canónica (`sort_keys`, separadores fijos, sin `NaN`, sin timestamps).

## Alternativas descartadas
1. **`FigureArtifact` con una figura de un backend gráfico embebida** (p. ej. objeto de
   Plotly como campo tipado): rechazada, acopla el core a una librería y contradice
   `docs/roadmap/v0.6.md:211-213`. Se usa `FigureSpec` declarativa y un escape hatch opaco
   (`backend`, `backend_payload`) que el core no interpreta.
2. **Validar completitud semántica/evidencial en construcción** (exigir tabla de respaldo,
   evidencia en insights, claims no vacíos): rechazada; impide obtener un resultado de
   validación estructurado (`FAIL`/`WARN`) y fuerza excepciones a mitad de un análisis.
   Corresponde al Change 3.
3. **pydantic / attrs / cualquier dependencia de validación**: rechazada; el core debe ser
   solo-stdlib para instalarse en `discovery` sin dependencias nuevas y para poder ser
   importado desde cualquier módulo sin arrastrar terceros.
4. **`from_frame` acoplado a pandas** (`import pandas`, `isinstance(frame, DataFrame)`):
   rechazada; duck typing mantiene el core sin dependencias y testeable con dobles simples.
5. **Un solo campo que combine tipo de reporte y alcance de decisión** (p. ej.
   `"eda_exploratory"`): rechazada; confunde dos dimensiones que el roadmap pide separar y
   multiplica el vocabulario.
6. **Restringir combinaciones `report_kind` × `decision_scope` en el core**: rechazada; es
   política de governance y variaría por proyecto.
7. **Timestamp `generated_at` dentro de `Report`**: rechazada; rompería la identidad de
   contenido del hash. Vive en el manifest (Change 3).

## Riesgos
- **`frame.values.tolist()` y tipos mixtos**: mitigado con `astype(object)`. En un frame cuyas
  columnas numéricas mezclan `int` y `float`, `.values` puede promover los enteros a `float`
  (p. ej. `3` → `3.0`); por eso `from_frame` usa `frame.astype(object).values.tolist()` cuando
  `frame` tiene `astype`. El fallback `frame.values.tolist()` conserva el riesgo solo para
  objetos sin `astype`; se documenta en el docstring de `from_frame` (alternativa para el
  llamador: `TableArtifact.from_rows`).
- **Frozen no implica inmutabilidad profunda**: `units`, `column_labels`, `metadata` y
  `backend_payload` son `dict`; `frozen=True` impide reasignar campos pero no mutar el dict.
  Mitigación: copia profunda al construir (no se comparte el dict del llamador). Además, las
  instancias con campos `dict` no son hasheables (`hash()` lanza `TypeError`); la identidad de
  contenido se ofrece vía `content_sha256()`, no `__hash__`.
- **`True == 1 == 1.0` en tuplas**: dos `Report` `==` pueden tener `content_sha256` distinto
  (p. ej. celdas `True` vs `1`); la identidad de contenido es el hash, no `==`.
- **Referencias sin resolver pasan la construcción** (`backing_table_id`, `evidence_refs`,
  columnas de `FigureSpec`): deliberado (ver política de validación); el riesgo es que el
  Change 3 no las cubra. Mitigación: `spec.md` R11 las enumera explícitamente como
  responsabilidad del Change 3 y `FigureSpec.columns_used()` existe para eso.
- **Dependencia de frontera por tests `ast` solo de nivel de módulo**: un import dentro de una
  función no se detecta (límite ya asumido en `test_v05_core_neutrality.py`). Mitigación: en
  `core.py` no se usan imports anidados, y el test de neutralidad puede escanear con
  `ast.walk` (todos los imports, no solo `arbol.body`).
- **Instalabilidad sin exclusiones paralelas**: los tests de `tools/reporting/tests/` no están
  listados en `EXCLUSIONES_PERMANENTES` (como sí lo están los de `ds_profile`/`dsimpact`,
  `manifest.py:611-627`); no se instalan por no estar en `MANIFEST`. Agregar esas exclusiones
  es opcional y queda a criterio del Lead (no requerido por la spec).
- **Precedente**: los paquetes de v0.5 no están en `MANIFEST`; este es el primer paquete nuevo
  desde `dsimpact` que se instala. Es decisión aprobada; el riesgo es de mantenimiento (cada
  módulo futuro de `tools/reporting` necesitará su entrada, ver `check_manifest_parity.py`).

## Aprobación humana
El registro de aprobación (usuario, fecha, alcance, versión de artefactos, cita) es único por
cambio y vive en la sección "Aprobación" de `proposal.md` — no se duplica acá.

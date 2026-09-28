# Spec — 20260922-quality-evidence-and-drift

## Requisitos

- **R1 — Paquete y módulos, frontera de imports**: existe `tools/qualityevidence/__init__.py`
  (sin lógica ni imports de hermanos, cuerpo vacío salvo docstring opcional),
  `tools/qualityevidence/core.py` (importa únicamente `dataclasses`, `typing`, `hashlib`, `json`,
  `re`, `datetime`, `secrets` y `__future__` — NO importa `tools.datacontracts`,
  `tools.modelquality`, `tools.reporting`, `dsguard`, `ds_profile`, pandas, numpy, ni ningún otro
  paquete) y `tools/qualityevidence/evidence.py` (importa, además de stdlib —incluido `tempfile`,
  `os`—, `dsguard.checks` y `ds_profile.holdout_guard.verificar_permitido` como ÚNICO símbolo de
  `ds_profile`, y `tools.qualityevidence.core` como sibling; NO importa `tools.datacontracts`,
  `tools.modelquality`, `tools.reporting` en ninguna dirección, ni `ds_profile.fingerprint`, ni
  ningún otro símbolo de `ds_profile`, ni pandas/numpy). Dataclasses `frozen=True`; docstrings/
  comentarios en español; nombres en `snake_case`.

- **R2 — Vocabularios y constantes de `core.py`**: `SCHEMA_VERSION = 1`;
  `SUBJECT_KINDS = ("data_contract_evaluation", "model_quality_evaluation")`;
  `EVIDENCE_SOURCE_KINDS = ("file", "generated")`;
  `DRIFT_COMPARISON_MODES = ("absolute_diff", "relative_diff")`;
  `_STATUS_VALIDOS = ("PASS", "WARN", "FAIL", "N/A")` (coincidencia de texto documentada con
  `dsguard.checks.STATUS_*`, sin import); `_KINDS_VALIDOS = ("check", "technical_error")`
  (coincidencia documentada con `dsguard.checks.KIND_*`). Excepción
  `QualityEvidenceError(ValueError)`: todo error de forma del módulo la lanza, nunca
  `TypeError`/`KeyError` crudos.

- **R3 — Ids y nombres**: `evidence_id` cumple `^qe-\d{8}T\d{6}Z-[0-9a-f]{6}$`; `drift_id` cumple
  `^dr-\d{8}T\d{6}Z-[0-9a-f]{6}$` (mismo formato de timestamp UTC + sufijo hexadecimal que
  `reporting.evidence.new_run_id`, reimplementado localmente en `core.py`, validado en construcción
  del dataclass raíz). `metric_name` (de `DriftEvidence`) cumple `^[a-z][a-z0-9_]*$` (mismo patrón
  que `ObservedMetric.metric_name` de Change 2, reimplementado localmente). Un id/nombre inválido
  lanza `QualityEvidenceError` al construir.

- **R4 — `EvidenceSource`**: campos `kind (∈ EVIDENCE_SOURCE_KINDS), role (str no vacío), path
  (Optional[str], default None), sha256 (Optional[str], default None; si no es None, cadena
  hexadecimal de 64 caracteres), algorithm (str, default "sha256/bin/v1"), description
  (Optional[str], default None), params (Optional[dict], default None)`. Reglas:
  - `kind == "file"`: `path` obligatorio (no `None`), relativo al repo y posix (sin `\\`, sin `:`,
    sin segmentos `.`/`..`/vacíos, sin absoluta) — violación → `QualityEvidenceError`; `sha256`
    obligatorio (no `None`); `description`/`params` deben ser `None` (si no, error: pertenecen solo
    a `kind="generated"`).
  - `kind == "generated"`: `description` obligatorio (str no vacío); `params` obligatorio (dict
    JSON-seguro, mismas reglas de copia profunda que `tools/datacontracts/core.py:184-219`,
    reimplementadas localmente); `sha256` obligatorio (hash de `canonical_json(params)`); `path`
    debe ser `None` (si no, error).
  - `kind` fuera de `EVIDENCE_SOURCE_KINDS` → error.

- **R5 — `DeclarationRef`**: campos `declaration_kind (str no vacío), declaration_id (str no
  vacío), version (Optional[str], default None), content_sha256 (str, cadena hexadecimal de 64
  caracteres, sin default)`. `declaration_kind` NO se restringe a un enum cerrado en `core.py` (es
  informativo, extraído por el llamador de `DataContract.dataset_role`-análogo o
  `ModelQualityPolicy.model_task_role`-análogo, ver `design.md`), pero `evidence.py` (R14) exige que
  sea `"data_contract"` o `"model_quality_policy"` cuando se usa desde las funciones de conveniencia
  públicas. `content_sha256` vacío o con longitud/caracteres inválidos (no hexadecimal) →
  `QualityEvidenceError`.

- **R6 — `ScopeWindow`**: campos `population (str, default ""), time_start (Optional[str], default
  None), time_end (Optional[str], default None)`. Si ambos `time_start`/`time_end` no son `None`,
  deben ser parseables con `datetime.fromisoformat` y `time_start <= time_end` — si no, error. Un
  solo extremo declarado (el otro `None`) es válido (ventana abierta).

- **R7 — `QualityEvidenceManifest` (raíz)**: campos `schema_version (int, default SCHEMA_VERSION),
  evidence_id (str, R3), subject_kind (∈ SUBJECT_KINDS), declaration (DeclarationRef),
  source (EvidenceSource), scope (ScopeWindow, default ScopeWindow()),
  check_results (tuple[dict], default ()), technical_errors (tuple[dict], default ()),
  generated_at (str, ISO 8601 UTC, sin default), content_sha256 (str, calculado, no aceptado como
  parámetro del constructor de conveniencia de `evidence.py` — ver R13)`. Reglas:
  - `subject_kind` fuera de `SUBJECT_KINDS` → error.
  - cada elemento de `check_results`/`technical_errors` debe ser un `dict` con `status` ∈
    `_STATUS_VALIDOS`, `code` (str no vacío), `message` (str no vacío), y opcionalmente `detail`/
    `subject` (str); cualquier otra clave → `QualityEvidenceError` (forma cerrada, sin extensiones
    libres en este campo). Un elemento de `check_results` con `status == "FAIL"` y presunción de
    `kind == "technical_error"` no se valida cruzado con ninguna clave `kind` interna del dict (el
    dict de `CheckResult.to_dict()` NO incluye `kind` salvo que sea explícitamente pasado — ver
    R14, que es responsabilidad de `evidence.py` clasificar antes de construir el manifest).
  - `schema_version` debe ser exactamente `SCHEMA_VERSION` → si no, error (constructor directo y
    `from_dict`).
  - `generated_at` debe ser parseable con `datetime.fromisoformat` tras reemplazar un sufijo `"Z"`
    por `"+00:00"` (mismo criterio que el resto del repo) → si no, error.

- **R8 — `DriftEvidence` (raíz)**: campos `schema_version (int, default SCHEMA_VERSION),
  drift_id (str, R3), metric_name (str, R3), baseline_window (EvidenceSource),
  baseline_label (str no vacío), current_window (EvidenceSource), current_label (str no vacío),
  baseline_value (int o float finito, no bool), current_value (int o float finito, no bool),
  comparison_mode (∈ DRIFT_COMPARISON_MODES), observed_difference (int o float finito, no bool),
  threshold (Optional[float], default None; si no es None, >= 0), result_status (∈
  _STATUS_VALIDOS), result_message (str no vacío), generated_at (str, misma regla que R7),
  content_sha256 (str, calculado)`. Reglas:
  - `comparison_mode` fuera de `DRIFT_COMPARISON_MODES` → error.
  - `threshold` negativo o de tipo incorrecto (no `None`, no `int`/`float` finito) → error.
  - `result_status` fuera de `_STATUS_VALIDOS` → error.
  - `core.py` NO recalcula `observed_difference` a partir de `baseline_value`/`current_value`
    (eso es responsabilidad de `evidence.py`, R15): solo valida que sea un número finito no-`bool`.

- **R9 — Validación en construcción**: estricta y solo estructural. Ningún constructor de
  `core.py` acepta un argumento que represente datos crudos, un `DataFrame`, una ruta de dataset/
  holdout, ni ningún parámetro llamado `data`/`frame`/`dataframe`/`predictions`/`rows`. `params`
  (de `EvidenceSource`) se copia en profundidad al construir (no se comparte el `dict` del
  llamador) y se normaliza a estructura JSON pura, mismas reglas que Change 0
  (`tools/datacontracts/core.py:184-219`), reimplementadas localmente.

- **R10 — Serialización determinista (`core.py`)**: cada dataclass expone `to_dict()` (orden de
  campos fijo, solo tipos JSON) y `from_dict()` (estricto en campos requeridos y, en
  `QualityEvidenceManifest`/`DriftEvidence`, en `schema_version`; ignora claves desconocidas por
  forward-compat). `canonical_json(obj)` = `json.dumps(obj, sort_keys=True,
  separators=(",", ":"), ensure_ascii=False, allow_nan=False)` (fallo de serialización →
  `QualityEvidenceError`). `content_sha256()` de `QualityEvidenceManifest` y de `DriftEvidence` =
  sha256 (hex) de `canonical_json(to_dict() SIN las claves "generated_at" ni "content_sha256")`
  codificado en UTF-8; idéntico entre corridas para el mismo contenido, e idéntico tras
  `from_dict(x.to_dict())`. Cambiar `generated_at` manteniendo todo lo demás igual NO cambia
  `content_sha256()`.

- **R11 — Códigos de `evidence.py`** (registro completo, sin duplicar entre módulos — deuda 6 de
  `ARCHITECTURE.md` §4.1): `QUALITYEVIDENCE-INPUT`, `QUALITYEVIDENCE-SOURCE-DENIED`,
  `QUALITYEVIDENCE-SOURCE-MISSING`, `QUALITYEVIDENCE-WRITE`, `QUALITYEVIDENCE-READ`,
  `QUALITYEVIDENCE-STALE`, `QUALITYEVIDENCE-DRIFT-FIELD`, `QUALITYEVIDENCE-DRIFT-DENIED`.

- **R12 — Hash y escritura de archivos (`evidence.py`)**: `_sha256_archivo(ruta)` calcula sha256
  binario chunked (`hashlib.sha256`, lectura por bloques de 1 MiB) — idéntico algoritmo/formato de
  salida que `ds_profile.fingerprint.calcular_fingerprint`/`tools/dsguard/mlops_evidence.py:
  _hash_binario_sha256`, reimplementado localmente (NO importa ninguno de los dos). Escritura
  atómica (`_escribir_atomico(ruta, contenido_bytes)`): escribe a un archivo temporal en el mismo
  directorio y hace `os.replace` (mismo patrón que `dsguard.core.escribir_texto_atomico`,
  reimplementado localmente con stdlib `tempfile`/`os`, sin importar `dsguard.core`).

- **R13 — `describe_source_file(repo_root, path, *, role) -> EvidenceSource`**: puerta con I/O.
  Aplica `ds_profile.holdout_guard.verificar_permitido(ruta_resuelta, repo_root)` ANTES de abrir el
  archivo; denegado → levanta `QualityEvidenceError` con código informativo
  `QUALITYEVIDENCE-SOURCE-DENIED` en el mensaje (el archivo NUNCA se abre). Ruta fuera del repo,
  inexistente o no-archivo → `QualityEvidenceError` (`QUALITYEVIDENCE-SOURCE-MISSING`). Si es
  accesible, calcula sha256 (R12) y devuelve `EvidenceSource(kind="file", role=role,
  path=<relativo posix>, sha256=..., algorithm="sha256/bin/v1")`. `describe_source_generated
  (description, params, *, role) -> EvidenceSource`: pura, sin I/O, calcula `sha256` de
  `canonical_json(params)`, devuelve `EvidenceSource(kind="generated", ...)`. Ninguna de las dos
  funciones copia `profile.get("dataset_path")` literal (portabilidad, `docs/roadmap/v0.7.md:
  318-320`): quien llama a `describe_source_file` con el `profile.json` mismo (no con
  `dataset_path`) obtiene automáticamente una ruta repo-relativa segura.

- **R14 — `build_manifest(*, subject_kind, declaration, source, results, scope=None,
  clock=None) -> QualityEvidenceManifest`**: pura salvo `results` ya en memoria (no abre ningún
  archivo). `results` es `list[dsguard.checks.CheckResult]` (cualquier otro tipo/elemento →
  `QualityEvidenceError`, código `QUALITYEVIDENCE-INPUT`). Separa `results` en `check_results`
  (`r.kind == checks.KIND_CHECK`) y `technical_errors` (`r.kind == checks.KIND_TECHNICAL_ERROR`),
  cada uno serializado con `r.to_dict()`, preservando el orden original dentro de cada grupo.
  `declaration` debe ser una `DeclarationRef` con `declaration_kind` ∈
  `{"data_contract", "model_quality_policy"}` (si no, `QualityEvidenceError`,
  `QUALITYEVIDENCE-INPUT`) — coherente con `subject_kind` (`"data_contract_evaluation"` ↔
  `declaration_kind == "data_contract"`; `"model_quality_evaluation"` ↔
  `declaration_kind == "model_quality_policy"`; incoherencia → `QualityEvidenceError`). `scope`
  default `ScopeWindow()`. `generated_at` se resuelve con `clock` (mismo contrato que
  `reporting.evidence._generated_at`, reimplementado localmente: `None` → UTC real; `datetime` fijo
  → formateado). `evidence_id` se genera con `new_evidence_id(now=clock() si clock else None)`.

- **R15 — `write_manifest(repo_root, manifest: QualityEvidenceManifest) -> Path`**: escribe
  `.harmessi/quality/<evidence_id>/manifest.json` de forma atómica (R12), directorio padre creado
  si falta. Falla ante colisión de directorio ya existente con contenido distinto (mismo
  `evidence_id`, distinto `content_sha256`) → `QualityEvidenceError`
  (`QUALITYEVIDENCE-WRITE`); si el directorio existe con contenido IDÉNTICO
  (`content_sha256` igual), no re-escribe y devuelve la ruta existente (idempotencia). Nunca
  escribe fuera de `.harmessi/quality/` bajo `repo_root`.

- **R16 — `read_manifest(repo_root, evidence_id) -> QualityEvidenceManifest`**: lee
  `.harmessi/quality/<evidence_id>/manifest.json`, verifica que
  `QualityEvidenceManifest.from_dict(json.load(...)).content_sha256()` coincide con el
  `content_sha256` persistido en el archivo — si no coincide o el archivo no existe/es JSON
  inválido → `QualityEvidenceError` (`QUALITYEVIDENCE-READ`). Esta función NO aplica
  `verificar_permitido` (los manifests de `.harmessi/quality/` son metadata generada por el propio
  harness, no datos ni holdout — ver `proposal.md`, "Holdout policy").

- **R17 — `build_drift_evidence(*, metric_name, baseline_value, current_value, baseline_window,
  baseline_label, current_window, current_label, comparison_mode, threshold=None,
  clock=None) -> DriftEvidence`**: pura, sin I/O. Calcula `observed_difference`:
  - `"absolute_diff"`: `current_value - baseline_value`, siempre calculable.
  - `"relative_diff"`: si `baseline_value == 0` → `result_status = "WARN"`, `observed_difference =
    0.0` (placeholder documentado, nunca división por cero ni excepción),
    `result_message` = "no verificable: baseline en cero"; si no, `(current_value -
    baseline_value) / baseline_value`.
  Determina `result_status`/`result_message`:
  - `threshold is None` → `result_status = "N/A"`, `result_message` = "sin threshold declarado:
    evidencia registrada sin veredicto".
  - `threshold` declarado y `comparison_mode != "relative_diff"` con `baseline_value == 0` (caso
    imposible salvo `relative_diff`, N/A no aplica aquí) → evalúa
    `abs(observed_difference) <= threshold` → `"PASS"` si cumple, `"FAIL"` si no.
  - Para `"relative_diff"` con `baseline_value == 0`: el resultado queda en `"WARN"` sin importar
    `threshold` (no verificable tiene prioridad sobre cualquier threshold declarado).
  `generated_at`/`drift_id` se resuelven igual que R14 (`clock`).

- **R18 — `drift_from_profiles(repo_root, *, metric_name, baseline_profile_path,
  current_profile_path, field, column=None, comparison_mode, threshold=None,
  baseline_label="baseline", current_label="current", clock=None) -> DriftEvidence`**: puerta con
  I/O. `field` debe pertenecer a `_CAMPOS_NUMERICOS_PERMITIDOS = ("filas", "nulls_count",
  "unique_count", "min", "max")` — si no, `QualityEvidenceError` (`QUALITYEVIDENCE-DRIFT-FIELD`),
  SIN abrir ningún archivo. `field == "filas"` exige `column is None` (nivel dataset); los otros 4
  exigen `column` (str no vacío, nivel columna) — incoherencia → `QualityEvidenceError`
  (`QUALITYEVIDENCE-DRIFT-FIELD`). Aplica `ds_profile.holdout_guard.verificar_permitido` a AMBAS
  rutas ANTES de abrir cualquiera de las dos; cualquiera denegada → `QualityEvidenceError`
  (`QUALITYEVIDENCE-DRIFT-DENIED`), NINGUNA de las dos se abre (fail-closed simétrico, ver
  `design.md` "Leakage risks"). Lee y parsea ambos `profile.json`; extrae el valor numérico según
  `field`/`column` (`"filas"` → `profile["filas"]`; `"nulls_count"` →
  `profile["columnas_detalle"][column]["nulls"]["count"]`; `"unique_count"` →
  `profile["columnas_detalle"][column]["unique"]["count"]`; `"min"`/`"max"` →
  `profile["columnas_detalle"][column]["min"/"max"]`); valor ausente, no numérico o columna
  inexistente → `QualityEvidenceError` (`QUALITYEVIDENCE-DRIFT-FIELD`, mensaje indicando cuál de
  las dos ventanas falló). Construye `baseline_window`/`current_window` con
  `describe_source_file(repo_root, <profile_path>, role="profile")` (R13) y delega en
  `build_drift_evidence` (R17). Nunca lanza fuera de `QualityEvidenceError`: cualquier excepción
  inesperada se envuelve en `QualityEvidenceError` con el nombre del tipo original.

- **R19 — `resolve_evidence_ref(evidence_ref, repo_root) -> dict`**: nunca lanza. Si
  `evidence_ref` no es un `str` que empiece con el prefijo `"quality:"` → `{"resolvable": False,
  "detail": "no sigue la convención quality:<ruta>"}`. Si sigue el prefijo, extrae
  `evidence_id` de la ruta (`quality:.harmessi/quality/<evidence_id>/manifest.json`; cualquier otra
  forma tras el prefijo → `{"resolvable": True, "valid": False, "detail": "ruta con forma
  inesperada"}`), intenta `read_manifest(repo_root, evidence_id)` (R16); éxito →
  `{"resolvable": True, "valid": True, "detail": "...", "manifest": manifest.to_dict()}`; fallo
  (`QualityEvidenceError`) → `{"resolvable": True, "valid": False, "detail": str(exc),
  "manifest": None}`.

- **R20 — Privacidad**: ningún `EvidenceSource.path`, ningún mensaje de error, ningún
  `result_message` de `evidence.py` contiene una ruta absoluta de filesystem local — todas las
  rutas reportadas son relativas al repo y posix (R4, R13); ningún mensaje reproduce
  `profile.get("dataset_path")` sin normalizar (R13, nota de portabilidad).

- **R21 — Arquitectura y frontera**: `ARCHITECTURE.md` §2.1 tiene una fila para
  `tools/qualityevidence/core.py` y otra para `tools/qualityevidence/evidence.py`; §3 tiene una
  regla 9 (texto exacto en `design.md`). Ambos módulos se agregan a `MODULOS_CORE` de
  `tools/tests/test_architecture_boundaries.py`.
  `tools/tests/test_v07_qualityevidence_neutrality.py` (patrón `ast` de
  `test_v07_modelquality_neutrality.py`) verifica R1 y la dirección inversa de la regla 9
  (`dsguard`, `ds_profile`, `dsimpact`, `reporting`, `tools.datacontracts`, `tools.modelquality`,
  `providers`, `routing`, `fallback`, `harmessi_bench` no importan `tools.qualityevidence`, ningún
  estilo de import).

- **R22 — Instalabilidad**: `tools/ds_init/manifest.py` agrega tres `EntradaManifiesto` VERBATIM
  (`tools/qualityevidence/__init__.py`, `tools/qualityevidence/core.py`,
  `tools/qualityevidence/evidence.py`; `fuente == destino`) con `stage_minimo` por defecto
  (`"discovery"`). Los tests de `tools/qualityevidence/tests/` no van al manifest.
  `tools/ds_init/tests/test_manifest.py` y todo test que dependa de exclusiones, destinos únicos o
  monotonía de bundles siguen verdes sin editarse.

- **R23 — Backward compatibility**: ningún archivo existente cambia de comportamiento. Las únicas
  modificaciones a archivos existentes son aditivas: tres entradas en `MANIFEST`, dos filas y una
  regla en `ARCHITECTURE.md`, dos líneas en `MODULOS_CORE`, y (al cierre) el tildado en
  `docs/roadmap/v0.7.md`. Ningún módulo existente importa `tools.qualityevidence`.
  `tools/datacontracts/{core,validation}.py`, `tools/modelquality/{core,validation}.py` y todo
  `tools/reporting/*` no tienen ningún diff.

- **R24 — Roadmap**: al cerrar el Change (invocación de cierre) se tilda `[x] Change 3` en
  `docs/roadmap/v0.7.md`. Nada más del roadmap cambia en este Change; Changes 0, 1, 2, 4, 5 no se
  tocan.

- **R25 — Tests deterministas**: `tools/qualityevidence/tests/test_core.py`,
  `tools/qualityevidence/tests/test_evidence.py`,
  `tools/qualityevidence/tests/test_installability.py` (unittest), más
  `tools/tests/test_v07_qualityevidence_neutrality.py`, sin I/O de red, sin pandas/numpy, sin
  aleatoriedad no controlada (usan `clock`/`suffix` fijos donde el test necesita determinismo). Los
  fixtures de `profile.json` usados por `test_evidence.py` son valores sintéticos escritos a mano o
  generados con `tempfile`, nunca un dataset ni perfil real; se limpian tras cada test.

## Criterios de aceptación

**R1/R21 — neutralidad**
- Given `tools/qualityevidence/core.py`, When `test_v07_qualityevidence_neutrality.py` recorre su
  AST, Then todos los imports pertenecen a `{__future__, dataclasses, datetime, hashlib, json, re,
  secrets, typing}` y ninguno referencia `tools.datacontracts`, `tools.modelquality`,
  `tools.reporting`, `ds_profile`, `dsguard`, `pandas`, `numpy`.
- Given `tools/qualityevidence/evidence.py`, Then sus imports pertenecen a `{stdlib (incluye os,
  tempfile, pathlib)} ∪ {dsguard.checks, ds_profile.holdout_guard, tools.qualityevidence.core}`,
  sin `ds_profile.fingerprint`, sin `tools.datacontracts`, `tools.modelquality`, `tools.reporting`,
  pandas, numpy.
- Given los módulos de `dsguard`, `ds_profile`, `dsimpact`, `reporting`, `tools.datacontracts`,
  `tools.modelquality`, `providers`, `routing`, `fallback`, `harmessi_bench`, When se escanean sus
  imports, Then ninguno importa `tools.qualityevidence`.
- Given `MODULOS_CORE`, Then contiene `tools/qualityevidence/core.py` y
  `tools/qualityevidence/evidence.py`; `test_architecture_boundaries.py` sigue verde.

**R2/R3 — vocabularios e ids**
- Given cada valor de `SUBJECT_KINDS`, `EVIDENCE_SOURCE_KINDS`, `DRIFT_COMPARISON_MODES`, Then
  coincide exactamente (contenido y orden) con R2.
- Given `QualityEvidenceManifest(..., evidence_id="qe-20260922T120000Z-abc123", ...)`, Then válido;
  dado `evidence_id="evidencia-1"` (fuera del patrón), Then `QualityEvidenceError`.
- Given `metric_name="AUC"` o `"1_metric"`, Then error; dado `"nulls_rate"`, Then válido.

**R4 — `EvidenceSource`**
- Given `kind="file", path="C:/abs/ruta.json"` (absoluta), Then error.
- Given `kind="file", path="data/x.json", sha256="abc"` (no hex-64), Then error.
- Given `kind="file", path="data/x.json", sha256="a"*64`, Then válido.
- Given `kind="generated", description="", params={}`, Then error (`description` vacío).
- Given `kind="generated", description="conteo sintético", params={"n": 10}, sha256="a"*64`, Then
  válido.
- Given `kind="file"` con `description` no-`None`, Then error (campo ajeno a `kind="file"`).

**R5/R6 — `DeclarationRef`/`ScopeWindow`**
- Given `DeclarationRef(declaration_kind="data_contract", declaration_id="c1", content_sha256="z")`
  (no hexadecimal), Then error.
- Given `ScopeWindow(time_start="2026-09-01", time_end="2026-08-01")` (start > end), Then error.
- Given `ScopeWindow(time_start="2026-09-01", time_end=None)`, Then válido.

**R7 — `QualityEvidenceManifest`**
- Given `subject_kind="otro"`, Then error.
- Given `check_results=({"status": "PASS", "code": "X", "message": "ok", "extra": 1},)` (clave
  ajena), Then error.
- Given `schema_version=2` (con `SCHEMA_VERSION == 1`), Then error, tanto en el constructor directo
  como en `from_dict`.
- Given `generated_at="no es fecha"`, Then error.

**R8 — `DriftEvidence`**
- Given `comparison_mode="percentual"` (fuera de `DRIFT_COMPARISON_MODES`), Then error.
- Given `threshold=-0.1`, Then error; dado `threshold=None`, Then válido.
- Given `result_status="OK"` (fuera de `_STATUS_VALIDOS`), Then error.

**R10 — serialización determinista**
- Given un `QualityEvidenceManifest` completo, Then
  `QualityEvidenceManifest.from_dict(m.to_dict())` produce un objeto con `content_sha256()`
  idéntico al original.
- Given dos manifests idénticos salvo `generated_at`, Then `content_sha256()` idéntico entre
  ambos.
- Given cambiar un solo `check_results[0]["message"]`, Then `content_sha256()` cambia.
- Given un `DriftEvidence` completo, Then round-trip determinista análogo.

**R12/R13 — hash, escritura y `describe_source_*`**
- Given un archivo con contenido conocido, Then `_sha256_archivo` produce el mismo hex que
  `hashlib.sha256(contenido).hexdigest()`.
- Given una ruta bajo un holdout declarado sin excepción vigente en `guardrails.json` de fixture,
  Then `describe_source_file` levanta `QualityEvidenceError` mencionando
  `QUALITYEVIDENCE-SOURCE-DENIED`, y el archivo NUNCA se lee (verificado con un mock/spy que
  detecta si se intentó abrir).
- Given una ruta inexistente, Then `QualityEvidenceError`
  (`QUALITYEVIDENCE-SOURCE-MISSING`).
- Given `path` accesible bajo el repo, Then `EvidenceSource.path` es relativo y posix, nunca
  absoluto ni con `\\`.
- Given `describe_source_generated("desc", {"a": 1})`, Then determinista: mismo `sha256` en dos
  llamadas con los mismos `params`.

**R14/R15/R16 — manifest, escritura, lectura**
- Given `results=[CheckResult(PASS, "X", "ok"), CheckResult(FAIL, "Y", "mal",
  kind="technical_error")]`, Then `build_manifest(...).check_results` tiene 1 elemento y
  `.technical_errors` tiene 1 elemento, cada uno con las claves de `CheckResult.to_dict()`.
- Given `declaration_kind="data_contract"` con `subject_kind="model_quality_evaluation"`
  (incoherente), Then `QualityEvidenceError`.
- Given `results="no es una lista"`, Then `QualityEvidenceError`
  (`QUALITYEVIDENCE-INPUT`).
- Given un `manifest` válido, When `write_manifest(repo_root, manifest)`, Then el archivo
  `.harmessi/quality/<evidence_id>/manifest.json` existe y
  `read_manifest(repo_root, manifest.evidence_id) == manifest` (contenido campo a campo).
- Given escribir el MISMO manifest dos veces (mismo `evidence_id`, mismo `content_sha256`), Then
  la segunda llamada no falla y devuelve la misma ruta (idempotencia).
- Given escribir dos manifests DISTINTOS que, por una colisión de reloj/sufijo fabricada en el
  test, comparten `evidence_id` pero difieren en `content_sha256`, Then
  `QualityEvidenceError` (`QUALITYEVIDENCE-WRITE`).
- Given manipular a mano el `manifest.json` persistido (cambiar `"message"` de un `check_results`
  sin recalcular `content_sha256`), Then `read_manifest` levanta `QualityEvidenceError`
  (`QUALITYEVIDENCE-READ`).

**R17/R18 — drift**
- Given `comparison_mode="absolute_diff", baseline_value=0.02, current_value=0.07,
  threshold=0.03`, Then `observed_difference == 0.05` (con tolerancia de punto flotante) y
  `result_status == "FAIL"`.
- Given `comparison_mode="absolute_diff", baseline_value=0.02, current_value=0.03,
  threshold=0.03`, Then `result_status == "PASS"`.
- Given `comparison_mode="relative_diff", baseline_value=1000, current_value=1200,
  threshold=0.15`, Then `observed_difference ≈ 0.20` y `result_status == "FAIL"`.
- Given `comparison_mode="relative_diff", baseline_value=0, current_value=5, threshold=0.1`, Then
  `result_status == "WARN"`, `observed_difference == 0.0`, nunca `ZeroDivisionError`.
- Given `threshold=None` en cualquier `comparison_mode`, Then `result_status == "N/A"`.
- Given `field="unique_count"` sin `column`, Then `QualityEvidenceError`
  (`QUALITYEVIDENCE-DRIFT-FIELD`), sin abrir ningún archivo.
- Given `field="percentil_95"` (fuera del allowlist), Then `QualityEvidenceError`
  (`QUALITYEVIDENCE-DRIFT-FIELD`).
- Given dos `profile.json` sintéticos de fixture con `filas=1000` (baseline) y `filas=1200`
  (actual), `field="filas", comparison_mode="relative_diff", threshold=0.15`, Then
  `drift_from_profiles(...)` produce un `DriftEvidence` con `result_status == "FAIL"` y
  `baseline_window`/`current_window` con `path` relativo a cada fixture.
- Given una de las dos rutas de `profile.json` bajo un holdout de fixture sin excepción vigente,
  Then `QualityEvidenceError` (`QUALITYEVIDENCE-DRIFT-DENIED`), y NINGUNO de los dos archivos se
  llega a leer (verificado con spy).

**R19 — `resolve_evidence_ref`**
- Given `evidence_ref="notas/celda-3"` (no sigue la convención), Then
  `{"resolvable": False, ...}`, nunca lanza.
- Given `evidence_ref="quality:.harmessi/quality/qe-.../manifest.json"` apuntando a un manifest
  válido ya escrito, Then `{"resolvable": True, "valid": True, ...}`.
- Given el mismo prefijo apuntando a un `evidence_id` inexistente, Then
  `{"resolvable": True, "valid": False, ...}`, nunca lanza.

**R22 — instalabilidad**
- Given `MANIFEST`, Then contiene exactamente una entrada `VERBATIM`/`discovery` por cada uno de
  `tools/qualityevidence/__init__.py`, `tools/qualityevidence/core.py`,
  `tools/qualityevidence/evidence.py`, y las tres rutas existen en el repo.
- Given `tools/ds_init/tests/test_manifest.py` sin modificar, Then sigue verde.

**R23/R24 — compatibilidad y roadmap**
- Given `git diff` del Change (invocación 2), Then los archivos preexistentes modificados son solo
  `manifest.py`, `ARCHITECTURE.md`, `test_architecture_boundaries.py` (y `control.json`/artefactos
  SDD de este Change), con cambios aditivos; `tools/datacontracts/`, `tools/modelquality/` y
  `tools/reporting/` no tienen ningún diff; la suite completa previa corre igual que en el
  baseline.
- Given `docs/roadmap/v0.7.md` al cierre (invocación 5), Then `[x] Change 3` y ningún otro Change
  del roadmap se modifica.

## Unidad de análisis / grain (condicional — data_understanding, feature_engineering, modeling)
No aplica: tipos de evidencia en memoria/disco, infraestructura del harness, sin dataset.

## Cutoff / information boundary (condicional — feature_engineering, data_preparation, modeling)
No aplica.

## Baseline (condicional — modeling)
No aplica a este SDD en sí (este Change DECLARA el concepto `DriftEvidence.baseline_window` como
tipo de infraestructura del harness; no fija ningún baseline metodológico real de ningún modelo o
dataset).

## Métrica primaria (condicional — modeling, evaluation)
No aplica.

## Métricas secundarias (opcional)
No aplica.

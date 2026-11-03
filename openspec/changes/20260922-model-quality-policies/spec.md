# Spec — 20260922-model-quality-policies

## Requisitos

- **R1 — Paquete y módulos solo-stdlib/`dsguard.checks`**: existe `tools/modelquality/__init__.py`
  (sin lógica ni imports de hermanos, cuerpo vacío salvo docstring opcional),
  `tools/modelquality/core.py` (importa únicamente `dataclasses`, `typing`, `hashlib`, `json`, `re`
  y `__future__` — mismo set que `tools/datacontracts/core.py`; NO importa `tools.datacontracts`,
  `dsguard`, `ds_profile`, pandas, numpy, ni ningún otro paquete) y
  `tools/modelquality/validation.py` (importa, además de stdlib, `dsguard.checks` y
  `tools.modelquality.core` — sibling; NO importa `tools.datacontracts`, `ds_profile`, pandas,
  numpy, ni ningún otro paquete de `tools/`). Dataclasses `frozen=True`; docstrings/comentarios en
  español; nombres en `snake_case`.

- **R2 — Vocabularios y constantes de `core.py`**:
  `MODEL_TASK_ROLES = ("classification", "regression", "ranking", "clustering", "forecasting",
  "generic")`; `DIRECTIONS = ("higher_is_better", "lower_is_better")`; `SPLITS = ("train",
  "validation", "test", "holdout", "out_of_time", "cross_validation", "custom")`;
  `COMPARISON_MODES = ("absolute", "relative_to_baseline", "absolute_diff_from_baseline")`;
  `UNCERTAINTY_KINDS = ("standard_error", "confidence_interval")`; `SEVERITIES = ("FAIL", "WARN")`;
  `EXTENSION_PREFIX = "x_"`; `SCHEMA_VERSION = 1`. Excepción `ModelQualityError(ValueError)`: todo
  error de forma del módulo la lanza, nunca `TypeError`/`KeyError` crudos.

- **R3 — Ids y nombres**: `policy_id`, `requirement_id`, `context_id`, `baseline_id` cumplen
  `^[a-z0-9][a-z0-9_-]{0,63}$` y rechazan los nombres de dispositivo reservados de Windows (`con`,
  `prn`, `aux`, `nul`, `com1`..`com9`, `lpt1`..`lpt9`) — implementación propia en
  `tools/modelquality/core.py`, sin importar el helper equivalente de
  `tools/datacontracts/core.py` (familias independientes, ver `design.md` decisión 1). `metric_name`
  (de `MetricRequirement`, `ObservedMetric` y `BaselineReference`) cumple
  `^[a-z][a-z0-9_]*$` (mismo patrón que `ContractField.name` de Change 0, reimplementado
  localmente). Un id o nombre inválido lanza `ModelQualityError` al construir.

- **R4 — `EvaluationContext`**: campos `context_id (str, R3), split (∈ SPLITS), population (str,
  default ""), description (str, default ""), extensions (dict, default {})`. `split` fuera de
  `SPLITS` → error. `extensions` JSON-segura (mismas reglas que
  `tools/datacontracts/core.py:222-232`) con claves `EXTENSION_PREFIX`.

- **R5 — `MetricRequirement`**: campos `requirement_id (str, R3), metric_name (str, R3), direction
  (∈ DIRECTIONS), threshold_value (Optional[float], default None), threshold_severity (∈
  SEVERITIES, default "FAIL"), required_context (EvaluationContext, sin default), baseline_required
  (bool, default False), comparison_mode (∈ COMPARISON_MODES, default "absolute"),
  comparison_tolerance (Optional[float], default None), baseline_severity (∈ SEVERITIES, default
  "FAIL"), min_sample_size (Optional[int], default None), uncertainty_required (bool, default
  False), description (str, default ""), extensions (dict, default {})`. Reglas:
  - `direction` fuera de `DIRECTIONS`, `threshold_severity`/`baseline_severity` fuera de
    `SEVERITIES`, o `comparison_mode` fuera de `COMPARISON_MODES` → error.
  - `threshold_value`, si no es `None`, debe ser `int`/`float` finito (no `bool`) → si no, error.
  - `comparison_tolerance`, si no es `None`, debe ser `int`/`float` finito ≥ 0 (no `bool`) → si no,
    error.
  - `min_sample_size`, si no es `None`, debe ser `int >= 1` (no `bool`) → si no, error.
  - `required_context` debe ser instancia de `EvaluationContext` → si no, error.
  - **Regla de coherencia mínima**: al menos uno de `threshold_value is not None` o
    `baseline_required is True` → si ninguno se cumple (requirement vacuo, no exige nada
    verificable), `ModelQualityError`.

- **R6 — `ObservedMetric`**: campos `metric_name (str, R3), value (int o float finito, no bool, sin
  default), context (EvaluationContext, sin default), evidence_ref (Optional[str], default None; si
  no es None, str no vacío), sample_size (Optional[int], default None; si no es None, int >= 1, no
  bool), uncertainty (Optional[dict], default None; ver R7 para su forma), description (str,
  default ""), extensions (dict, default {})`. `value` no finito (`NaN`/`inf`) o de tipo incorrecto
  → error. `context` no instancia de `EvaluationContext` → error.

- **R7 — Forma de `ObservedMetric.uncertainty` (validación estructural, nunca metodológica)**:
  cuando `uncertainty` no es `None`, debe ser un `dict` JSON-seguro con `"kind"` ∈
  `UNCERTAINTY_KINDS`:
  - `"standard_error"`: requiere `"value"` = `int`/`float` finito ≥ 0 (no `bool`); ausente o de
    otro tipo/signo → error.
  - `"confidence_interval"`: requiere `"lower"` y `"upper"` = `int`/`float` finitos con
    `lower <= upper`, y `"confidence_level"` = `float` en el intervalo abierto `(0, 1)`; ausente,
    de otro tipo, o `lower > upper`, o `confidence_level` fuera de `(0, 1)` → error.
  Un `"kind"` fuera de `UNCERTAINTY_KINDS`, o `uncertainty` sin clave `"kind"`, → error. El módulo
  no evalúa si la incertidumbre reportada es metodológicamente adecuada (eso es del metodólogo,
  `docs/roadmap/v0.7.md:250-252`), solo que su FORMA sea la declarada arriba.

- **R8 — `BaselineReference`**: campos `baseline_id (str, R3), metric_name (str, R3), value (int o
  float finito, no bool, sin default), context (EvaluationContext, sin default), source (str no
  vacío, sin default), evidence_ref (Optional[str], default None; misma regla que R6),
  description (str, default ""), extensions (dict, default {})`. `source=""` → error (declarar QUÉ
  es el baseline es obligatorio; el módulo no clasifica ni valida ese texto).

- **R9 — `ModelQualityPolicy` (raíz)**: campos `policy_id (str, R3), model_task_role (∈
  MODEL_TASK_ROLES), requirements (tuple[MetricRequirement], no vacía), description (str, default
  ""), extensions (dict, default {}), schema_version (int, default SCHEMA_VERSION)`. Reglas:
  - `requirements` no vacía; `requirement_id` únicos entre sí (namespace propio de la política) →
    duplicado lanza error.
  - `model_task_role` fuera de `MODEL_TASK_ROLES` → error.
  - `schema_version` debe ser exactamente `SCHEMA_VERSION` → distinto, error (constructor directo y
    `from_dict`).
  Accesores, ninguno lanza: `get_requirement(requirement_id) -> Optional[MetricRequirement]`,
  `requirements_for(metric_name) -> tuple[MetricRequirement]` (requirements con ese
  `metric_name`, en cualquier contexto — un `metric_name` puede repetirse entre requirements con
  `required_context` distinto, eso es válido, ver R5).

- **R10 — Validación en construcción**: estricta y solo estructural (enums, ids, patrones, tipos,
  duplicados, JSON-seguridad de `extensions`/`uncertainty`). Ningún constructor de este módulo
  acepta un argumento que represente datos crudos, predicciones, un `DataFrame`, una ruta de
  dataset/holdout, ni ningún parámetro llamado `data`/`frame`/`dataframe`/`predictions`/`rows`/
  `path`/`ruta`. `extensions`/`uncertainty` se copian en profundidad al construir (no se comparte el
  `dict` del llamador) y se normalizan a estructura JSON pura.

- **R11 — Serialización determinista (`core.py`)**: cada dataclass expone `to_dict()` (orden de
  campos fijo, solo tipos JSON) y `from_dict()` (estricto en campos requeridos y, en
  `ModelQualityPolicy`, en `schema_version`; ignora claves desconocidas por forward-compat).
  `canonical_json(obj)` = `json.dumps(obj, sort_keys=True, separators=(",", ":"),
  ensure_ascii=False, allow_nan=False)` (fallo de serialización → `ModelQualityError`).
  `ModelQualityPolicy.content_sha256()` = sha256 (hex) de `canonical_json(self.to_dict())`
  codificado en UTF-8; idéntico entre corridas y tras `ModelQualityPolicy.from_dict(p.to_dict())`.
  `EvaluationContext`, `MetricRequirement`, `ObservedMetric`, `BaselineReference` exponen
  `to_dict()`/`from_dict()` pero NO `content_sha256()` (ver `design.md`, decisión 2: no son
  declaración versionada en git, son valores de evidencia en tiempo de evaluación). Ninguna
  dataclass de este módulo expone `generated_at`.

- **R12 — Códigos de `validation.py`** (registro completo, sin duplicar entre módulos —
  deuda 6 de `ARCHITECTURE.md` §4.1): `QUALITY-INPUT`, `QUALITY-METRIC-MISSING`,
  `QUALITY-CONTEXT-MISMATCH`, `QUALITY-METRIC-AMBIGUOUS`, `QUALITY-EVIDENCE-MISSING`,
  `QUALITY-UNCERTAINTY-MISSING`, `QUALITY-SAMPLE-SIZE`, `QUALITY-THRESHOLD`,
  `QUALITY-BASELINE-MISSING`, `QUALITY-BASELINE`, `QUALITY-RESULT`.

- **R13 — `evaluate_policy(policy, observed_metrics, baselines=()) -> list[CheckResult]`**: función
  pura, sin I/O, sin `Path`, sin ningún guard (ver `proposal.md`, "Holdout policy": no hay
  superficie de archivo en este Change). `policy` debe ser instancia de `ModelQualityPolicy`;
  `observed_metrics` una lista/tupla de `ObservedMetric`; `baselines` una lista/tupla de
  `BaselineReference` (default vacía). Si `policy` no es del tipo esperado, o `observed_metrics`/
  `baselines` no son `list`/`tuple`, o contienen un elemento del tipo incorrecto → una única entrada
  `CheckResult(FAIL, "QUALITY-INPUT", ..., kind="technical_error")`, sin evaluar nada más. Nunca
  lanza: cualquier excepción inesperada al evaluar un `MetricRequirement` individual se convierte
  en `checks.resultado_de_excepcion("QUALITY-<requirement_id>", exc)` sin impedir que se evalúen
  los demás requirements (mismo patrón que `_ejecutar`/`checks.ejecutar_checks`,
  `tools/datacontracts/validation.py:158-169`).

- **R14 — Orden de evaluación por `MetricRequirement` (fijo, ver `design.md` decisión 6)**: para
  cada `requirement` de `policy.requirements`, en el orden en que aparecen en la tupla:
  1. **Selección de `ObservedMetric`** ("métrica observada"): filtrar `observed_metrics` por
     `metric_name == requirement.metric_name`; si ninguno →
     `CheckResult(FAIL, "QUALITY-METRIC-MISSING", ..., subject=requirement.requirement_id)`, y NO
     se evalúan las etapas siguientes para este requirement (salvo `QUALITY-RESULT`, que replica el
     mismo status). Si al menos uno, filtrar por coincidencia de contexto (`observed.context.split
     == requirement.required_context.split` AND (`requirement.required_context.population == ""`
     OR `observed.context.population == requirement.required_context.population`)); si ninguno
     coincide → `CheckResult(FAIL, "QUALITY-CONTEXT-MISMATCH", ...)`, mismo corte. Si más de uno
     coincide → `CheckResult(WARN, "QUALITY-METRIC-AMBIGUOUS", ...)`, mismo corte. Si exactamente
     uno coincide, se usa para las etapas siguientes.
  2. **Evidencia vigente** (solo si la selección tuvo éxito): `QUALITY-EVIDENCE-MISSING` — `WARN`
     si `observed.evidence_ref` es `None`/vacío, `PASS` si no; SIEMPRE evaluado (no condicional a
     ningún campo de la política). `QUALITY-UNCERTAINTY-MISSING` — solo si
     `requirement.uncertainty_required` es `True` (si es `False`, se omite esta entrada por
     completo, sin `N/A`): `WARN` si `observed.uncertainty` es `None` o si su forma no cumple R7;
     `PASS` si cumple R7. `QUALITY-SAMPLE-SIZE` — solo si `requirement.min_sample_size` no es
     `None` (si es `None`, se omite por completo): `WARN` si `observed.sample_size` es `None`;
     `FAIL` si `observed.sample_size < requirement.min_sample_size`; `PASS` si
     `observed.sample_size >= requirement.min_sample_size`.
  3. **Threshold** (solo si la selección tuvo éxito): `QUALITY-THRESHOLD` — `N/A` si
     `requirement.threshold_value is None`. Si no es `None`: con `direction ==
     "higher_is_better"`, `PASS` si `observed.value >= requirement.threshold_value`, si no
     `requirement.threshold_severity`; con `direction == "lower_is_better"`, `PASS` si
     `observed.value <= requirement.threshold_value`, si no `requirement.threshold_severity`.
  4. **Baseline/reference** (solo si la selección tuvo éxito): `N/A` (sin entrada `QUALITY-BASELINE`
     ni `QUALITY-BASELINE-MISSING`, se omite todo) si `requirement.baseline_required is False`. Si
     `True`: seleccionar `BaselineReference` de `baselines` con el mismo procedimiento del punto 1
     (filtrar por `metric_name`, luego por coincidencia de contexto contra
     `requirement.required_context`); si no hay exactamente uno →
     `CheckResult(requirement.baseline_severity, "QUALITY-BASELINE-MISSING", ...)` (nunca `PASS`).
     Si hay exactamente uno, aplicar `requirement.comparison_mode` con `t =
     requirement.comparison_tolerance or 0.0`, `v = observed.value`, `b = baseline.value`:
     - `"absolute"`: `higher_is_better` → `PASS` si `v >= b - t`, si no
       `requirement.baseline_severity`; `lower_is_better` → `PASS` si `v <= b + t`, si no
       `requirement.baseline_severity`.
     - `"absolute_diff_from_baseline"`: `PASS` si `abs(v - b) <= t`, si no
       `requirement.baseline_severity` (sin distinguir dirección).
     - `"relative_to_baseline"`: si `b == 0` → `WARN` "no verificable (baseline en cero)"; si no,
       `higher_is_better` → `PASS` si `(v - b) / b >= -t`, si no `requirement.baseline_severity`;
       `lower_is_better` → `PASS` si `(v - b) / b <= t`, si no `requirement.baseline_severity`.
     Resultado va en `CheckResult(status, "QUALITY-BASELINE", ...)`.
  5. **`QUALITY-RESULT`**: fold monotónico (nunca mejora, solo empeora o mantiene, ver `design.md`
     decisión 6) de los status no-`N/A` de las etapas anteriores aplicables a este requirement, en
     el orden dado arriba (si el requirement se cortó en la selección, `QUALITY-RESULT` replica ese
     único status; si no, se pliega evidencia → threshold → baseline). Si todas las etapas
     aplicables fueran `N/A` (caso imposible dado R5, que exige threshold o baseline declarados,
     pero verificado igual por robustez), `QUALITY-RESULT` = `N/A`.

- **R15 — Nunca `PASS` por falta de evidencia**: ningún camino de `evaluate_policy` puede producir
  `QUALITY-RESULT = PASS` si `QUALITY-EVIDENCE-MISSING` fue `WARN` para ese requirement (el fold
  monotónico de R14.5 lo garantiza estructuralmente: `WARN` nunca puede "mejorarse" a `PASS` al
  incorporar etapas posteriores). Ídem para `QUALITY-METRIC-MISSING`/`QUALITY-CONTEXT-MISMATCH`/
  `QUALITY-METRIC-AMBIGUOUS`/`QUALITY-BASELINE-MISSING`: ninguno es nunca `PASS`.

- **R16 — Privacidad**: ningún `CheckResult` (`message`/`detail`/`subject`) de `validation.py`
  incluye una ruta absoluta de filesystem local — no aplica en sentido literal (este Change no
  toca rutas de dataset ni de perfil), pero se verifica igualmente por consistencia con el resto
  del repo: ningún mensaje reproduce texto libre de `evidence_ref` sin control (se cita entre
  comillas simples, nunca interpolado como si fuera confiable/ejecutable).

- **R17 — Instalabilidad**: `tools/ds_init/manifest.py` agrega tres `EntradaManifiesto` VERBATIM
  (`tools/modelquality/__init__.py`, `tools/modelquality/core.py`,
  `tools/modelquality/validation.py`; `fuente == destino`) con `stage_minimo` por defecto
  (`"discovery"`). Los tests de `tools/modelquality/tests/` no van al manifest.
  `tools/ds_init/tests/test_manifest.py` y todo test que dependa de exclusiones, destinos únicos o
  monotonía de bundles siguen verdes sin editarse.

- **R18 — Arquitectura y frontera**: `ARCHITECTURE.md` §2.1 tiene una fila para
  `tools/modelquality/core.py` y otra para `tools/modelquality/validation.py`; §3 tiene una regla 8
  (texto exacto en `design.md`): `core.py` es solo-stdlib y no importa hermanos ni ningún paquete
  existente (incluido `tools.datacontracts`); `validation.py` importa `dsguard.checks` y
  `tools.modelquality.core`, nunca `ds_profile` ni `tools.datacontracts`; nunca al revés (`dsguard`,
  `ds_profile`, `dsimpact`, `reporting`, `tools.datacontracts`, `providers`, `routing`, `fallback`,
  `harmessi_bench` no importan `tools/modelquality`). Ambos módulos se agregan a `MODULOS_CORE` de
  `tools/tests/test_architecture_boundaries.py`. `tools/tests/test_v07_modelquality_neutrality.py`
  (patrón `ast` de `test_v07_core_neutrality.py`/`test_v07_validation_neutrality.py`, cubriendo
  ambos módulos) verifica R1 y la dirección inversa de la regla 8.

- **R19 — Backward compatibility**: ningún archivo existente cambia de comportamiento. Las únicas
  modificaciones a archivos existentes son aditivas: tres entradas en `MANIFEST`, dos filas y una
  regla en `ARCHITECTURE.md`, dos líneas en `MODULOS_CORE`, y (al cierre) el tildado en
  `docs/roadmap/v0.7.md`. Ningún módulo existente importa `tools.modelquality`.
  `tools/datacontracts/{core,validation}.py` no tienen ningún diff.

- **R20 — Roadmap**: al cerrar el Change (invocación de cierre) se tilda `[x] Change 2` en
  `docs/roadmap/v0.7.md`. Nada más del roadmap cambia en este Change; Changes 0, 1, 3, 4, 5 no se
  tocan.

- **R21 — Tests deterministas**: `tools/modelquality/tests/test_core.py`,
  `tools/modelquality/tests/test_validation.py`, `tools/modelquality/tests/test_installability.py`
  (unittest), más `tools/tests/test_v07_modelquality_neutrality.py`, sin I/O de red, sin
  pandas/numpy, sin lectura de ningún dataset/`profile.json`/archivo real, sin aleatoriedad. Los
  fixtures de `ObservedMetric`/`BaselineReference`/`ModelQualityPolicy` son valores sintéticos
  escritos a mano (ninguna métrica ni valor de ningún dataset real).

## Criterios de aceptación

**R1/R18 — neutralidad**
- Given `tools/modelquality/core.py`, When `test_v07_modelquality_neutrality.py` recorre su AST,
  Then todos los imports pertenecen a `{__future__, dataclasses, hashlib, json, re, typing}` y
  ninguno referencia `tools.datacontracts`, `ds_profile`, `dsguard`, `pandas`, `numpy`, `reporting`.
- Given `tools/modelquality/validation.py`, Then sus imports pertenecen a `{stdlib} ∪
  {dsguard.checks, tools.modelquality.core}`, sin `tools.datacontracts`, `ds_profile`, pandas,
  numpy, ni ningún otro paquete de `tools/`.
- Given los módulos de `dsguard`, `ds_profile`, `dsimpact`, `reporting`, `tools.datacontracts`,
  `providers`, `routing`, `fallback`, `harmessi_bench`, When se escanean sus imports, Then ninguno
  importa `tools.modelquality` (ningún estilo de import).
- Given `MODULOS_CORE`, Then contiene `tools/modelquality/core.py` y
  `tools/modelquality/validation.py`; `test_architecture_boundaries.py` sigue verde.

**R2/R3 — vocabularios e ids**
- Given cada valor de `MODEL_TASK_ROLES`, `DIRECTIONS`, `SPLITS`, `COMPARISON_MODES`,
  `UNCERTAINTY_KINDS`, `SEVERITIES`, Then coincide exactamente (contenido y orden) con R2.
- Given un `policy_id`/`requirement_id`/`context_id`/`baseline_id` inválido (vacío, con mayúscula,
  con `.`, con `/`, de 65 caracteres, no-`str`, o `"con"`), Then `ModelQualityError`.
- Given un `metric_name` inválido (`""`, `"AUC"`, `"1_metric"`, `"metric-1"`), Then error; dado
  `"roc_auc"`, `"f1_score"`, `"rmse"`, Then válido.

**R4 — `EvaluationContext`**
- Given `split="otro"`, Then error; dado `split="test"`, `population=""`, Then válido.
- Given `extensions={"nota": "sin prefijo"}`, Then error; dado `extensions={"x_nota": "ok"}`, Then
  válido.

**R5 — `MetricRequirement`**
- Given `direction="mejor"` (fuera de `DIRECTIONS`), Then error.
- Given `threshold_value=None` y `baseline_required=False` (ningún requisito declarado), Then
  `ModelQualityError` (regla de coherencia mínima).
- Given `threshold_value=0.75, baseline_required=False`, Then válido (solo threshold).
- Given `threshold_value=None, baseline_required=True`, Then válido (solo baseline).
- Given `comparison_tolerance=-0.1` o `comparison_tolerance=True` (bool), Then error; dado
  `comparison_tolerance=0.02`, Then válido.
- Given `min_sample_size=0` o `min_sample_size=1.5`, Then error; dado `min_sample_size=30`, Then
  válido.
- Given `required_context=` un `dict` en vez de `EvaluationContext`, Then error.

**R6/R7 — `ObservedMetric` y `uncertainty`**
- Given `value=float("nan")` o `value=True` (bool), Then error; dado `value=0.83`, Then válido.
- Given `evidence_ref=""`, Then error; dado `evidence_ref=None` o un `str` no vacío, Then válido.
- Given `uncertainty={"kind": "standard_error", "value": -0.1}`, Then error; dado
  `{"kind": "standard_error", "value": 0.02}`, Then válido.
- Given `uncertainty={"kind": "confidence_interval", "lower": 0.9, "upper": 0.8,
  "confidence_level": 0.95}` (lower > upper), Then error; dado `{"kind": "confidence_interval",
  "lower": 0.80, "upper": 0.90, "confidence_level": 0.95}`, Then válido.
- Given `uncertainty={"kind": "otro"}`, Then error.

**R8 — `BaselineReference`**
- Given `source=""`, Then error; dado `source="modelo anterior v1.2"`, Then válido.

**R9 — `ModelQualityPolicy`**
- Given `requirements=()` (vacía), Then error.
- Given dos `MetricRequirement` con el mismo `requirement_id`, Then error.
- Given dos `MetricRequirement` con el mismo `metric_name` pero `required_context` distinto, Then
  válido (no es un duplicado).
- Given `schema_version=2` (con `SCHEMA_VERSION == 1`), Then error, tanto en el constructor directo
  como en `from_dict`.
- Given una `ModelQualityPolicy` válida, Then `get_requirement`/`requirements_for` nunca lanzan y
  devuelven `None`/tupla vacía para un id/nombre inexistente.

**R11 — serialización determinista**
- Given una `ModelQualityPolicy` completa (con varios `MetricRequirement`), Then
  `ModelQualityPolicy.from_dict(p.to_dict()) == p` (contenido campo a campo) y
  `content_sha256()` idéntico entre corridas.
- Given cambiar un solo valor de `comparison_tolerance` de un `MetricRequirement`, Then el hash de
  la `ModelQualityPolicy` cambia.
- Given `EvaluationContext`/`ObservedMetric`/`BaselineReference`, Then exponen `to_dict()`/
  `from_dict()` (round-trip determinista) pero NO exponen ningún método `content_sha256`.

**R13/R14/R15 — `evaluate_policy`, orden fijo, nunca `PASS` sin evidencia**
- Given `policy=None` o `observed_metrics="no es lista"`, Then una única entrada
  `CheckResult(FAIL, "QUALITY-INPUT", kind="technical_error")`, sin ninguna otra entrada.
- Given un `requirement` cuyo `metric_name` no aparece en ningún `ObservedMetric` de
  `observed_metrics`, Then `QUALITY-METRIC-MISSING (FAIL)` y `QUALITY-RESULT (FAIL)`, sin ninguna
  entrada `QUALITY-EVIDENCE-MISSING`/`QUALITY-THRESHOLD`/`QUALITY-BASELINE*` para ese requirement.
- Given un `ObservedMetric` con `metric_name` correcto pero `context.split` distinto del
  `required_context.split`, Then `QUALITY-CONTEXT-MISMATCH (FAIL)` y `QUALITY-RESULT (FAIL)`, mismo
  corte.
- Given dos `ObservedMetric` con el mismo `metric_name` y contexto idéntico (`split` y
  `population` iguales al requerido), Then `QUALITY-METRIC-AMBIGUOUS (WARN)` y `QUALITY-RESULT
  (WARN)`, mismo corte.
- Given un `ObservedMetric` correctamente seleccionado con `evidence_ref=None` y un
  `requirement.threshold_value` que el `value` SÍ cumple (p. ej. `value=0.90 >=
  threshold_value=0.75`, `higher_is_better`), Then `QUALITY-EVIDENCE-MISSING (WARN)`,
  `QUALITY-THRESHOLD (PASS)`, y `QUALITY-RESULT (WARN)` — nunca `PASS` pese a que el threshold se
  cumple (R15).
- Given `evidence_ref` no vacío, `threshold_value=0.75, direction="higher_is_better"`, y
  `observed.value=0.70`, Then `QUALITY-EVIDENCE-MISSING (PASS)`, `QUALITY-THRESHOLD (FAIL)`
  (usando `requirement.threshold_severity`), `QUALITY-BASELINE-MISSING`/`QUALITY-BASELINE` ausentes
  (`baseline_required=False`), `QUALITY-RESULT (FAIL)`.
- Given `requirement.uncertainty_required=True` y `observed.uncertainty=None`, Then
  `QUALITY-UNCERTAINTY-MISSING (WARN)` presente y contribuye al fold; dado
  `uncertainty_required=False`, Then esa entrada NO se emite en absoluto para ese requirement.
- Given `requirement.min_sample_size=100` y `observed.sample_size=50`, Then
  `QUALITY-SAMPLE-SIZE (FAIL)`; dado `observed.sample_size=None`, Then
  `QUALITY-SAMPLE-SIZE (WARN)`; dado `min_sample_size=None`, Then esa entrada no se emite.
- Given `threshold_value=None` (sin declarar), Then `QUALITY-THRESHOLD (N/A)`.
- Given `baseline_required=True` y ningún `BaselineReference` con `metric_name`/contexto
  coincidentes en `baselines`, Then `QUALITY-BASELINE-MISSING` con severidad =
  `requirement.baseline_severity` (nunca `PASS`), y ninguna entrada `QUALITY-BASELINE`.
- Given `baseline_required=False`, Then ninguna entrada `QUALITY-BASELINE-MISSING` ni
  `QUALITY-BASELINE` para ese requirement (ambas se omiten, sin `N/A` explícito).
- Given `comparison_mode="absolute"`, `direction="higher_is_better"`, `comparison_tolerance=0.01`,
  `observed.value=0.80`, `baseline.value=0.805`, Then `QUALITY-BASELINE (PASS)` (`0.80 >= 0.805 -
  0.01 == 0.795`); dado `baseline.value=0.82`, Then `QUALITY-BASELINE` con severidad =
  `baseline_severity` (`0.80 < 0.82 - 0.01 == 0.81`).
- Given `comparison_mode="absolute_diff_from_baseline"`, `comparison_tolerance=0.02`,
  `observed.value=0.81`, `baseline.value=0.80`, Then `QUALITY-BASELINE (PASS)` (`abs(0.01) <=
  0.02`); dado `baseline.value=0.75`, Then severidad `baseline_severity` (`abs(0.06) > 0.02`),
  independientemente de la dirección declarada.
- Given `comparison_mode="relative_to_baseline"`, `direction="lower_is_better"`,
  `comparison_tolerance=0.05`, `observed.value=10.0`, `baseline.value=10.4`, Then
  `QUALITY-BASELINE (PASS)` (`(10.0-10.4)/10.4 ≈ -0.038 <= 0.05`); dado `baseline.value=0.0`, Then
  `QUALITY-BASELINE (WARN)` "no verificable (baseline en cero)", nunca excepción.
- Given un `requirement` con `threshold_value` cumplido (`PASS`) y `baseline_required=True` con
  baseline ausente, Then `QUALITY-RESULT` = severidad de `QUALITY-BASELINE-MISSING` (el fold
  conserva el peor de threshold=PASS y baseline_missing=WARN/FAIL, nunca PASS si baseline_missing
  es WARN o FAIL).
- Given un `requirement` cuyas etapas dan, en orden, evidencia=PASS, threshold=WARN, baseline=FAIL,
  Then `QUALITY-RESULT (FAIL)` (el peor de las tres, sin importar el orden de severidad de cada
  una individualmente — la función `_peor` nunca "sube").
- Given una excepción inesperada al evaluar un `requirement` (simulada en test), Then
  `CheckResult(FAIL, "QUALITY-<requirement_id>-EXCEPCION", kind="technical_error")` para ESE
  requirement, y los demás requirements de la misma `policy` se evalúan igual (no se propaga ni
  interrumpe el resto).

**R17 — instalabilidad**
- Given `MANIFEST`, Then contiene exactamente una entrada `VERBATIM`/`discovery` por cada uno de
  `tools/modelquality/__init__.py`, `tools/modelquality/core.py`,
  `tools/modelquality/validation.py`, y las tres rutas existen en el repo.
- Given `tools/ds_init/tests/test_manifest.py` sin modificar, Then sigue verde.

**R19/R20 — compatibilidad y roadmap**
- Given `git diff` del Change (invocación 2), Then los archivos preexistentes modificados son solo
  `manifest.py`, `ARCHITECTURE.md`, `test_architecture_boundaries.py` (y `control.json`/artefactos
  SDD de este Change), con cambios aditivos; `tools/datacontracts/` no tiene ningún diff; la suite
  completa previa corre igual que en el baseline.
- Given `docs/roadmap/v0.7.md` al cierre (invocación 5), Then `[x] Change 2` y ningún otro Change
  del roadmap se modifica.

## Unidad de análisis / grain (condicional — data_understanding, feature_engineering, modeling)
No aplica: políticas de calidad de modelo en memoria, infraestructura del harness, sin dataset.

## Cutoff / information boundary (condicional — feature_engineering, data_preparation, modeling)
No aplica.

## Baseline (condicional — modeling)
No aplica a este SDD en sí (este Change DECLARA el concepto `BaselineReference` como tipo de
infraestructura del harness; no fija ningún baseline metodológico real de ningún modelo).

## Métrica primaria (condicional — modeling, evaluation)
No aplica.

## Métricas secundarias (opcional)
No aplica.

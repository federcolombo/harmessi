# Diseño — 20260922-model-quality-policies

## Decisión metodológica/técnica

Flujo conceptual de v0.7 (`docs/roadmap/v0.7.md:45-71`): `DECLARACIÓN → OBSERVACIÓN → EVALUACIÓN
DETERMINISTA → EVIDENCE → INTERPRETACIÓN`. Para datos, Change 0 implementó `DECLARACIÓN` y Change 1
`EVALUACIÓN DETERMINISTA`, en dos Changes separados. Para modelos, el roadmap NO desglosa esas dos
etapas en dos Changes: Change 2 es el único Change de "políticas de calidad de modelo" antes de
Change 3 (evidencia/drift) — por lo tanto este Change entrega, en un solo paquete, el análogo
completo de `core.py` + `validation.py`. `OBSERVACIÓN` (el cálculo real de la métrica) ocurre fuera
de Harmessi, en el proyecto (notebook/código) — decisión 1, la más importante de este Change.
`EVIDENCE` (persistencia con hash/`generated_at`, drift) es Change 3; `INTERPRETACIÓN` es del
Lead/metodólogo/reporting, nunca de este módulo.

### Decisión 1 — Nombre del paquete: `tools/modelquality` (`core.py` + `validation.py`)

Paquete nuevo de primer nivel, mismo patrón exacto que `tools/reporting` y `tools/datacontracts`:
`__init__.py` sin lógica, `core.py` (declaración, solo-stdlib), `validation.py` (evaluación,
produce `CheckResult`). A diferencia de `tools/datacontracts` (Changes 0-1, dos Changes), ambos
módulos de `tools/modelquality` se entregan en este único Change 2.

Alternativas descartadas:
1. **Extender `tools/datacontracts` con los tipos de política de modelo** (p. ej.
   `tools/datacontracts/model_quality.py`, mismo paquete): rechazada. Change 0 documentó
   explícitamente la frontera conceptual opuesta: "los conceptos de este Change... son
   exclusivamente de contratos de datos — el Change 2 (`model-quality-policies`) declarará una
   familia paralela y distinta... que no comparte tipos con esta"
   (`openspec/changes/20260922-data-contracts-core/design.md:19-24`). Fusionar ambas familias en un
   solo paquete borraría esa frontera ya fijada y obligaría a `tools/datacontracts` a depender
   implícitamente de conceptos de modelo que nada tienen que ver con estructura/calidad de datos.
2. **`tools/quality/` genérico con submódulos `data.py`/`model.py`**: rechazada, mismo motivo que
   la alternativa 2 de Change 1 rechazó `tools/quality/contracts_core.py`
   (`openspec/changes/20260922-data-contract-validation/design.md:27-34`): ningún paquete existente
   de este repo usa un nivel de anidación así (`tools/reporting`, `tools/datacontracts`,
   `tools/dsimpact`, `tools/providers`, `tools/routing`, `tools/fallback`, `tools/harmessi_bench`
   son todos paquetes de primer nivel con `core.py` directo); y un paquete `quality` genérico
   invitaría, otra vez, a que datos y modelo terminen conviviendo sin frontera clara, exactamente
   el riesgo que Change 0 ya identificó y evitó nombrando su propio paquete `datacontracts` en vez
   de `dataquality`.
3. **`tools/modelmetrics` (en vez de `tools/modelquality`)**: rechazada; "metrics" sugeriría que el
   paquete calcula o almacena métricas, cuando el paquete NO calcula ninguna (decisión 1 del
   roadmap) — solo declara políticas y evalúa valores ya reportados contra ellas. `modelquality` es
   el nombre que el propio Change 0 ya reservó por escrito para este propósito exacto
   (`openspec/changes/20260922-data-contracts-core/design.md:27-33`, alternativa descartada 1:
   "...un futuro paquete de política de modelo tenga su propio nombre (p. ej.
   `tools/modelquality`)"), evitando reabrir una decisión de nombre ya anticipada y documentada.

`tools/modelquality/core.py` y `tools/modelquality/validation.py` son ambos solo-stdlib +
`dsguard.checks` (solo `validation.py`) + `tools.modelquality.core` (sibling, solo desde
`validation.py`) — **ninguno de los dos importa `tools.datacontracts`**, ni al revés: son familias
independientes sin tipos compartidos, incluida la coincidencia de vocabulario `SEVERITIES =
("FAIL", "WARN")` (misma decisión que Change 0 tomó para no importar `dsguard.checks` desde
`core.py`, `tools/datacontracts/core.py:72-76`) — se duplica el literal de texto, documentado como
coincidencia intencional, no como dependencia de código.

### Decisión 2 — Firma de `ObservedMetric` (y `BaselineReference`)

```python
@dataclass(frozen=True)
class ObservedMetric:
    metric_name: str                    # ^[a-z][a-z0-9_]*$ (mismo patrón que ContractField.name)
    value: float                        # int o float finito, no bool -- el número YA reportado
    context: EvaluationContext          # split/población donde se midió
    evidence_ref: Optional[str] = None  # procedencia genérica; ver justificación abajo
    sample_size: Optional[int] = None   # >= 1 si está presente, no bool
    uncertainty: Optional[dict] = None  # JSON-seguro; forma validada por "kind" (ver decisión 3)
    description: str = ""
    extensions: dict = {}               # JSON-seguro, claves EXTENSION_PREFIX
```

```python
@dataclass(frozen=True)
class BaselineReference:
    baseline_id: str                    # patrón de id (^[a-z0-9][a-z0-9_-]{0,63}$)
    metric_name: str                    # mismo patrón que ObservedMetric.metric_name
    value: float                        # int o float finito, no bool
    context: EvaluationContext          # split/población donde se midió el baseline
    source: str                         # texto libre: qué es el baseline (modelo anterior,
                                         # heurística, modelo dummy) -- declarado, no clasificado
    evidence_ref: Optional[str] = None  # misma semántica que ObservedMetric.evidence_ref
    description: str = ""
    extensions: dict = {}
```

**`evidence_ref: Optional[str]` genérico, sin hash ni `generated_at` (decisión explícita, no un
adelanto accidental de Change 3).** Justificación de qué campos son razonables en este Change:

- La decisión 1 del roadmap describe la forma conceptual completa a nivel de TODO v0.7: "Un
  `ObservedMetric` es un valor reportado con procedencia (evidence ref + hash + contexto)"
  (`docs/roadmap/v0.7.md:79`). Pero el "hash" ahí referido es el hash de **bytes de un archivo de
  evidencia persistida** — un concepto que solo existe una vez que Change 3 define el formato de
  esa evidencia (`docs/roadmap/v0.7.md:297-321`: "hashes", "`generated_at`", ubicación bajo
  `.harmessi/`). Este Change 2 no define ningún formato de archivo de evidencia; no hay bytes que
  hashear todavía.
- `evidence_ref` es, por lo tanto, un `str` de propósito general: un identificador o puntero de
  procedencia declarado por quien reporta la métrica (ruta de un reporte, id de una corrida de
  entrenamiento, referencia a una celda de notebook, URI de un tracking server) — sin ninguna
  semántica de archivo, sin que este Change lo abra, lo lea ni lo verifique más allá de "¿está
  presente y no vacío?". Es deliberadamente más débil que un hash: no prueba que el valor sea
  correcto ni que no haya cambiado, solo que quien reportó el valor dejó un rastro de dónde vino.
  Change 3 podrá, en su propio SDD, decidir si reinterpreta `evidence_ref` como una ruta bajo
  `.harmessi/` con hash verificable, sin que este Change se comprometa de antemano con esa forma.
- `Optional[str]` (no `str` obligatorio no vacío): un `ObservedMetric` sin `evidence_ref` es
  estructuralmente válido de CONSTRUIR (Change 2 no impone en `core.py` que toda métrica reportada
  tenga procedencia — sería demasiado estricto para, por ejemplo, un fixture de test o un borrador)
  pero **nunca puede alcanzar `PASS`** en `validation.py` (ver decisión 5): la ausencia de
  `evidence_ref` es un problema de VERIFICABILIDAD, decidido en evaluación, no de forma estructural
  en construcción — mismo criterio que Change 1 aplicó a `CONTRACT-EVIDENCE-MISSING` (la ausencia
  de perfil no impide construir un `DataContract`, impide `PASS` al validarlo).
- `context: EvaluationContext` (no un `str` de split suelto): reutiliza el mismo tipo declarado que
  `MetricRequirement.required_context`, permitiendo comparación estructural directa
  (`context.split`, `context.population`) sin parsear texto libre.
- `sample_size: Optional[int]` y `uncertainty: Optional[dict]`: metadata de muestra/población e
  incertidumbre que el roadmap pide poder declarar (`docs/roadmap/v0.7.md:248-252`); ambos
  opcionales porque no toda métrica reportada trae esta información, y su ausencia se evalúa según
  lo que la política exija (`MetricRequirement.min_sample_size`/`uncertainty_required`), nunca
  como un error de construcción.

Alternativas descartadas:
1. **`evidence_ref` como objeto con `path: str`, `sha256: str`, `generated_at: str`** (adelantando
   la forma completa de evidencia persistida de Change 3): rechazada explícitamente; el propio
   brief de esta invocación lo señala como riesgo a evitar. Comprometerse ahora con la forma exacta
   de hash/timestamp que usará Change 3 sin haber diseñado ese Change sería una decisión prematura
   que Change 3 podría tener que romper.
2. **Sin ningún campo de procedencia en absoluto** (confiar solo en `description` de texto libre):
   rechazada; la decisión 1 del roadmap exige "procedencia" como parte constitutiva del concepto
   `ObservedMetric`, no como nota opcional sin estructura — un campo dedicado (`evidence_ref`)
   permite que `validation.py` lo verifique de forma determinista (presencia), cosa que un texto
   libre en `description` no permitiría sin heurísticas.
3. **`value` como `Optional[float]` (permitir un `ObservedMetric` "vacío" declarado antes de
   tener el número)**: rechazada; el propio concepto de `ObservedMetric` es "un valor reportado"
   (`docs/roadmap/v0.7.md:270`, "valor reportado por el proyecto") — un valor ausente no es una
   métrica observada, es la ausencia de una (que ya se representa con la ausencia del objeto
   completo en la lista `observed_metrics` que recibe `evaluate_policy`).

### Decisión 3 — Vocabulario cerrado de "modo de comparación" contra baseline

`MetricRequirement.comparison_mode ∈ COMPARISON_MODES = ("absolute", "relative_to_baseline",
"absolute_diff_from_baseline")`, con un único parámetro numérico declarativo,
`comparison_tolerance: Optional[float]` (mismo principio que `Constraint.params` de Change 0:
declara FORMA, nunca evalúa código — `tools/datacontracts/core.py:235-309`). Ningún modo admite
una expresión arbitraria, lambda ni código serializado.

Semántica exacta (aplicada solo en la etapa "baseline/reference", nunca en la etapa "threshold",
que siempre compara `ObservedMetric.value` contra `MetricRequirement.threshold_value` directamente
— ver decisión 6 para por qué ambas etapas son independientes):

Sea `v = ObservedMetric.value`, `b = BaselineReference.value`, `t = comparison_tolerance or 0.0`,
`dir = MetricRequirement.direction`.

- **`"absolute"`** (margen de no-regresión en unidades crudas, con dirección — un solo lado):
  `higher_is_better`: PASS si `v >= b - t`. `lower_is_better`: PASS si `v <= b + t`.
  Uso típico: "el AUC no debe caer más de 0.01 respecto del baseline".
- **`"absolute_diff_from_baseline"`** (cercanía en unidades crudas, SIN dirección — dos lados):
  PASS si `abs(v - b) <= t`. No juzga si `v` es mejor o peor que `b`, solo si está "cerca". Uso
  típico: chequeos de estabilidad/drift de una métrica que no debería moverse mucho en ningún
  sentido.
- **`"relative_to_baseline"`** (margen de no-regresión como fracción del baseline, con dirección):
  si `b == 0`, el modo es no verificable (`WARN`, división por cero — nunca `FAIL` ni excepción).
  Si `b != 0`: `higher_is_better`: PASS si `(v - b) / b >= -t`. `lower_is_better`: PASS si
  `(v - b) / b <= t`. Uso típico: "el RMSE no debe empeorar más de un 5% respecto del baseline".

`t` (tolerancia) por defecto es `0.0` cuando `comparison_tolerance` es `None`: en `"absolute"` y
`"relative_to_baseline"` eso exige "no peor que el baseline, sin margen"; en
`"absolute_diff_from_baseline"` exige igualdad exacta (`v == b`) salvo que se declare una
tolerancia positiva — comportamiento consistente, sin caso especial adicional.

Alternativas descartadas:
1. **Un único modo `"diff"` con un booleano `"relative": bool` en vez de dos `constraint_type`
   separados**: rechazada; el roadmap enumera "valor absoluto, diferencia absoluta o relativa
   contra baseline" (`docs/roadmap/v0.7.md:279-281`) como tres nociones distintas con nombre
   propio, y un vocabulario cerrado explícito (`COMPARISON_MODES`) es más auditable y más fácil de
   validar en construcción que un booleano combinado con otro campo.
2. **Que `"absolute"` y `"absolute_diff_from_baseline"` sean el mismo modo** (dado que, con
   dirección, `v >= b - t` y `abs(v-b) <= t` coinciden solo cuando además se exige `v <= b + t`):
   rechazada tras análisis explícito; son fórmulas distintas con semántica distinta (un lado vs.
   dos lados, direccional vs. no direccional) — fusionarlas perdería la capacidad de declarar un
   chequeo de estabilidad simétrico (`absolute_diff_from_baseline`) sin también exigir que el valor
   sea "mejor", que es un caso de uso real y distinto (drift/estabilidad vs. no-regresión).
3. **Permitir una expresión de comparación con `eval`/lambda serializada como string** (para dar
   flexibilidad total a métricas verdaderamente custom): rechazada de plano; prohibido
   explícitamente por el brief de esta invocación y por el precedente de Change 0
   (`docs/roadmap/v0.7.md:182-183`).

### Decisión 4 — Selección determinista de qué `ObservedMetric`/`BaselineReference` "gobierna"

`evaluate_policy` recibe listas completas (`observed_metrics: list[ObservedMetric]`, `baselines:
list[BaselineReference] = ()`), nunca un único valor preseleccionado por el llamador. Para cada
`MetricRequirement`, la selección (etapa "métrica observada" del orden fijo) es puramente
estructural, sin heurística de negocio:

1. Filtrar candidatos cuyo `metric_name == requirement.metric_name`.
2. Si no queda ninguno → `QUALITY-METRIC-MISSING` (`FAIL`), corte del requirement (ver decisión 6).
3. Filtrar, entre los anteriores, los que coinciden de contexto contra `requirement.required_context`
   — coincidencia = `observed.context.split == required_context.split` AND (`required_context.population
   == ""` OR `observed.context.population == required_context.population`). `context_id` de ambos
   lados NUNCA se compara (es una etiqueta/label, no parte de la identidad lógica del contexto).
4. Si no queda ninguno tras el filtro de contexto (pero sí había candidatos por nombre) →
   `QUALITY-CONTEXT-MISMATCH` (`FAIL`), corte del requirement.
5. Si queda exactamente uno → se usa ese `ObservedMetric` para las etapas siguientes.
6. Si queda más de uno (dos reportes distintos para el mismo `metric_name` y mismo contexto exacto)
   → `QUALITY-METRIC-AMBIGUOUS` (`WARN`, "no verificable cuál gobierna"), corte del requirement.

Mismo procedimiento, mismo orden, para `BaselineReference` cuando `baseline_required` es `True`
(usando `baselines` en vez de `observed_metrics`); si no hay match → `QUALITY-BASELINE-MISSING`
(severidad = `MetricRequirement.baseline_severity`, nunca `PASS`).

Alternativas descartadas:
1. **Elegir automáticamente el "mejor" o el "más reciente" candidato cuando hay más de uno**:
   rechazada de plano; el roadmap prohíbe explícitamente que el binario "infiera qué métrica
   debería importar" (`docs/roadmap/v0.7.md:291`) — elegir por valor (el mejor) sería
   literalmente inventar un criterio de negocio; elegir por "más reciente" requeriría un
   `generated_at` que este Change no tiene (Change 3).
2. **Exigir unicidad de `metric_name` en TODA la lista `observed_metrics`, sin considerar contexto**
   (un único valor posible por nombre, sin importar el split): rechazada; el roadmap espera
   reportar la misma métrica en distintos contextos de forma legítima (p. ej. AUC en `train` y en
   `test`, cada una con su propio `MetricRequirement`), así que la selección debe considerar
   contexto, no solo nombre.
3. **Ignorar `population` en la comparación de contexto, comparar solo `split`**: rechazada;
   descartaría información real que una política puede querer exigir (p. ej. "el F1 reportado para
   el segmento `region=AMBA`"); se prioriza `split` como obligatorio (siempre se compara) y
   `population` como opcional (solo se compara si la política la declara no vacía), balance
   explícito documentado acá.

### Decisión 5 — Qué significa "evidencia vigente" en este Change

Sin Change 3 (sin hash, sin `generated_at`), "vigente" se acota exactamente a verificación
ESTRUCTURAL, nunca criptográfica ni de frescura temporal — mismo principio que Change 1 aplicó a
`ds_profile` sin inventar una noción de "vigente" más fuerte de lo que la evidencia disponible
permite (`openspec/changes/20260922-data-contract-validation/proposal.md:102-108`). Concretamente,
la etapa "evidencia vigente" de `evaluate_policy` (solo alcanzada si la selección del `ObservedMetric`
tuvo éxito, ver decisión 4) evalúa, siempre en este orden, sin cortar entre sub-chequeos (a
diferencia de la selección, que sí corta):

- **`QUALITY-EVIDENCE-MISSING`** (siempre evaluado, incondicional — no configurable por política,
  ver `proposal.md`, "Supuestos descartados"): `WARN` si `observed.evidence_ref` es `None` o
  cadena vacía; `PASS` si es un `str` no vacío. Nunca criptográfico: no se verifica que la ruta o
  id referenciado exista, sea legible ni corresponda a nada real — eso excede lo que este Change
  puede verificar sin Change 3.
- **`QUALITY-UNCERTAINTY-MISSING`** (solo si `requirement.uncertainty_required` es `True`; si es
  `False`, este código se omite por completo — sin `N/A` artificial): `WARN` si
  `observed.uncertainty` es `None`; si no es `None`, se valida su FORMA (nunca su adecuación
  metodológica — eso lo juzga el metodólogo, `docs/roadmap/v0.7.md:250-252`): debe ser un `dict`
  con `"kind"` ∈ `UNCERTAINTY_KINDS = ("standard_error", "confidence_interval")`; para
  `"standard_error"`, requiere `"value"` (float ≥ 0, finito); para `"confidence_interval"`, requiere
  `"lower"`/`"upper"` (float, `lower <= upper`) y `"confidence_level"` (float en `(0, 1)`). Forma
  inválida → `WARN` "declarado pero mal formado"; forma válida → `PASS`.
- **`QUALITY-SAMPLE-SIZE`** (solo si `requirement.min_sample_size` no es `None`; si es `None`, se
  omite): `WARN` si `observed.sample_size` es `None` (no reportado, no verificable); `FAIL` si
  `observed.sample_size` está presente y es menor que `min_sample_size` (violación real,
  determinista); `PASS` si está presente y es `>= min_sample_size`.

Ninguno de los tres sub-chequeos anteriores lanza ni requiere abrir ningún archivo — todos operan
sobre el `ObservedMetric` ya construido en memoria.

Alternativas descartadas:
1. **Tratar `evidence_ref` ausente como `FAIL` en vez de `WARN`**: rechazada; "aplicable pero no
   verificable → `WARN`, nunca un `PASS` inventado" es el mismo criterio que decisión 3 del roadmap
   aplica a datos (`docs/roadmap/v0.7.md:89-91`) — la ausencia de procedencia no prueba que el
   valor sea incorrecto, solo que no puede confirmarse su origen; `WARN` es la severidad honesta
   para "no verificable", reservando `FAIL` para violaciones deterministas y comprobables (como
   `QUALITY-SAMPLE-SIZE` cuando el tamaño reportado sí es insuficiente).
2. **Intentar verificar que `evidence_ref` "existe" resolviéndolo como ruta de archivo del repo**:
   rechazada; `evidence_ref` es explícitamente genérico (decisión 2) — podría ser un id de corrida,
   una URI externa, una celda de notebook, no necesariamente una ruta de archivo del repo; intentar
   resolverlo como `Path` y verificar existencia sería asumir una forma no declarada, e introduciría
   I/O de filesystem en lo que hoy es una función pura.

### Decisión 6 — Aplicación de "cada etapa solo puede empeorar el resultado, nunca mejorarlo"

`validation.py` define un orden total de severidad y una función de "peor de dos", reutilizada
para acumular el resultado FINAL de cada `MetricRequirement` (código `QUALITY-RESULT`) recorriendo
las etapas en el orden fijo del roadmap:

```python
_RANGO_SEVERIDAD = {"PASS": 0, "WARN": 1, "FAIL": 2}

def _peor(a: str, b: str) -> str:
    """El más severo entre dos status PASS/WARN/FAIL (nunca recibe N/A)."""
    return a if _RANGO_SEVERIDAD[a] >= _RANGO_SEVERIDAD[b] else b

def _acumular(statuses_en_orden: list) -> str:
    """Pliega una lista de status (algunos pueden ser 'N/A') en un único resultado final,
    respetando el orden recibido: los N/A se ignoran (ni empeoran ni mejoran); si TODOS son
    N/A, el resultado final es N/A; si no, es el peor de los no-N/A, considerados en el orden
    dado (la función nunca 'mejora' un resultado ya alcanzado -- solo puede igualarlo o
    empeorarlo al incorporar la siguiente etapa)."""
    final = None
    for status in statuses_en_orden:
        if status == "N/A":
            continue
        final = status if final is None else _peor(final, status)
    return "N/A" if final is None else final
```

Aplicado por `MetricRequirement`, en el orden exacto del roadmap (`docs/roadmap/v0.7.md:262-267`):

1. Si la selección del `ObservedMetric` (etapa "métrica observada") NO tuvo éxito
   (`QUALITY-METRIC-MISSING`/`QUALITY-CONTEXT-MISMATCH`/`QUALITY-METRIC-AMBIGUOUS`), el `status` de
   esa única entrada YA ES el resultado final (`QUALITY-RESULT` = mismo status); las etapas
   siguientes (evidencia, threshold, baseline) NO se evalúan — no hay ningún `ObservedMetric.value`
   contra el cual compararlas (mismo criterio de corte temprano que `_validar_evidencia` de Change
   1, `tools/datacontracts/validation.py:191-232`, aplicado aquí a nivel de un `requirement`
   individual en vez de a nivel de todo el `DataContract`).
2. Si la selección tuvo éxito: se evalúan, EN ORDEN, evidencia vigente (los sub-chequeos de
   decisión 5, cuyo peor status entre los aplicables es la contribución de esta etapa), threshold
   (`QUALITY-THRESHOLD`), y baseline/reference (`QUALITY-BASELINE-MISSING` o `QUALITY-BASELINE`,
   según corresponda). `QUALITY-RESULT` = `_acumular([status_evidencia, status_threshold,
   status_baseline])`, donde cada `status_*` ya es, a su vez, el resultado de plegar sus propios
   sub-chequeos si los tiene (evidencia) o `N/A` si la etapa no aplica (threshold sin
   `threshold_value` declarado; baseline sin `baseline_required`).

Cada `MetricRequirement` produce, entonces, TANTO las entradas granulares por código (diagnóstico
detallado, mismo criterio "check everything, report everything" de `tools/dsguard/checks.py:6-7` y
del patrón `_regla_*` de Change 1) COMO una entrada `QUALITY-RESULT` final que resume, de forma
monotónicamente no creciente en calidad, el veredicto del requirement completo. La agregación entre
MÚLTIPLES `MetricRequirement` de una misma `ModelQualityPolicy` (p. ej. "¿la política completa
pasa?") NO es responsabilidad de este módulo: `evaluate_policy` devuelve la lista plana de
`CheckResult` de todos los requirements: cualquier agregado de nivel-política se calcula con las
utilidades ya existentes (`dsguard.checks.hay_bloqueo`/`contar_por_status`), consistente con
decisión 5 del roadmap ("quality no es gate", ningún módulo de v0.7 decide por sí mismo un
veredicto binario final).

Alternativas descartadas:
1. **Devolver solo la entrada `QUALITY-RESULT` final, sin las entradas granulares por etapa**:
   rechazada; pierde exactamente la trazabilidad que "evidence, resultados reproducibles" exige
   (`docs/roadmap/v0.7.md:57`) y el patrón "check everything, report everything" ya establecido;
   además, sin las entradas granulares sería imposible auditar POR QUÉ un requirement quedó en
   `WARN` (¿evidencia? ¿threshold? ¿baseline?) sin volver a ejecutar la evaluación con más detalle.
2. **Cortar la evaluación completa de la `ModelQualityPolicy` (todos los requirements) ante el
   primer requirement con selección fallida**: rechazada; cada `MetricRequirement` es
   independiente entre sí (mismo criterio que Change 1 nunca corta la evaluación de un
   `DataContract` completo por una sola constraint fallida, salvo el gate global de evidencia); un
   requirement mal reportado no debe impedir evaluar los demás.
3. **Considerar `N/A` como "mejor que `PASS`" en el orden de severidad** (para que una etapa `N/A`
   pudiera "limpiar" un resultado peor de una etapa anterior): rechazada de plano; violaría
   literalmente "cada etapa solo puede empeorar el resultado, nunca mejorarlo" — por eso `_acumular`
   ignora los `N/A` en vez de tratarlos como un rango de severidad participante.

### Vocabulario completo de `core.py`

```python
SCHEMA_VERSION = 1
EXTENSION_PREFIX = "x_"                          # mismo patrón que tools/datacontracts/core.py:56

MODEL_TASK_ROLES = ("classification", "regression", "ranking", "clustering", "forecasting", "generic")
DIRECTIONS = ("higher_is_better", "lower_is_better")
SPLITS = ("train", "validation", "test", "holdout", "out_of_time", "cross_validation", "custom")
COMPARISON_MODES = ("absolute", "relative_to_baseline", "absolute_diff_from_baseline")
UNCERTAINTY_KINDS = ("standard_error", "confidence_interval")
SEVERITIES = ("FAIL", "WARN")   # mismo literal de texto que dsguard.checks.STATUS_FAIL/STATUS_WARN
                                 # y que tools/datacontracts/core.py:76 -- coincidencia de
                                 # vocabulario documentada, no dependencia de código (mismo criterio
                                 # que Change 0, decisión 3 del roadmap).

class ModelQualityError(ValueError):
    """Violación de una política de calidad de modelo (entrada estructuralmente inválida)."""
```

**Ids**: reutiliza el mismo patrón que `tools/datacontracts/core.py` (`^[a-z0-9][a-z0-9_-]{0,63}$`
+ rechazo de nombres reservados de Windows) para `policy_id`, `requirement_id`, `context_id`,
`baseline_id` — **reimplementado localmente** en `tools/modelquality/core.py` (no importado de
`tools.datacontracts.core`), por la misma razón que Change 0 duplicó el literal de `SEVERITIES` en
vez de importar `dsguard.checks`: familias independientes sin tipos ni helpers compartidos (ver
decisión 1). `metric_name` reutiliza el patrón de `ContractField.name`
(`^[a-z][a-z0-9_]*$`), también reimplementado localmente, por ser el nombre de una columna/valor
referenciable, no un id de archivo.

**`EvaluationContext`** (frozen):
```
context_id: str            # patrón de id
split: str                 # ∈ SPLITS
population: str = ""       # texto libre: segmento/población (vacío = "cualquiera", ver decisión 4)
description: str = ""
extensions: dict = {}
```

**`MetricRequirement`** (frozen):
```
requirement_id: str
metric_name: str                     # ^[a-z][a-z0-9_]*$
direction: str                       # ∈ DIRECTIONS
threshold_value: Optional[float] = None     # None => etapa threshold N/A
threshold_severity: str = "FAIL"     # ∈ SEVERITIES
required_context: EvaluationContext  # requerido, sin default
baseline_required: bool = False
comparison_mode: str = "absolute"    # ∈ COMPARISON_MODES
comparison_tolerance: Optional[float] = None   # >= 0 si está presente, finito
baseline_severity: str = "FAIL"      # ∈ SEVERITIES
min_sample_size: Optional[int] = None       # >= 1 si está presente, no bool
uncertainty_required: bool = False
description: str = ""
extensions: dict = {}
```
Regla de construcción propia (no estructural de tipo, sino de coherencia mínima): al menos uno de
`threshold_value is not None` o `baseline_required is True` — un requirement que no declara NI
threshold NI baseline no exige nada verificable, `ModelQualityError` al construir.

**`ModelQualityPolicy`** (raíz, frozen):
```
policy_id: str
model_task_role: str                  # ∈ MODEL_TASK_ROLES
requirements: tuple[MetricRequirement]  # no vacía; requirement_id únicos
description: str = ""
extensions: dict = {}
schema_version: int = SCHEMA_VERSION
```
Accesores (nunca lanzan): `get_requirement(requirement_id)`, `requirements_for(metric_name)`.
Serialización: `to_dict()`/`from_dict()`/`canonical_json()`/`content_sha256()` (mismo patrón exacto
que `DataContract`, `tools/datacontracts/core.py:736-795`). Solo `ModelQualityPolicy` (la raíz
versionable, declarada en git) expone `content_sha256()`; `ObservedMetric`/`BaselineReference` son
valores de evidencia en tiempo de evaluación, sin identidad de contenido persistida en este Change
(esa forma la define Change 3, ver decisión 2) — sí exponen `to_dict()`/`from_dict()` para
determinismo de tests y para que un futuro Change 3 los serialice sin reinventar el mapeo de campos.

### Texto exacto de la regla 8 de `ARCHITECTURE.md`

A insertar en `ARCHITECTURE.md` §3 (tras la regla 7 existente), por la invocación 2:

> 8. Familia `tools/modelquality` (v0.7 Change 2): `core.py` es solo-stdlib y no importa hermanos
>    ni ningún paquete existente, incluido `tools.datacontracts` (familia independiente, sin tipos
>    compartidos: ver `design.md` del Change). `validation.py` importa `dsguard.checks` (para
>    producir `CheckResult`) y `tools.modelquality.core` (sibling); no importa `ds_profile` ni
>    `tools.datacontracts` en ninguna dirección, ni ningún otro paquete de `tools/` -- no tiene
>    ninguna superficie de I/O ni de lectura de archivo en este Change (a diferencia de
>    `tools/datacontracts/validation.py`, que sí lee `profile.json`): `ObservedMetric`/
>    `BaselineReference` se reciben siempre como objetos ya construidos en memoria. Nunca al revés:
>    `dsguard`, `ds_profile`, `dsimpact`, `reporting`, `tools.datacontracts`, `providers`, `routing`,
>    `fallback` y `harmessi_bench` no importan `tools/modelquality`. Verificado por
>    `tools/tests/test_v07_modelquality_neutrality.py`.

Y las dos filas correspondientes en §2.1, estilo idéntico a las filas de `tools/datacontracts`:

> `tools/modelquality/core.py` | Políticas de calidad de modelo neutrales (v0.7 Change 2:
> `ModelQualityPolicy`/`MetricRequirement`/`EvaluationContext`/`ObservedMetric`/
> `BaselineReference`, serialización determinista y hash de contenido de `ModelQualityPolicy`) --
> solo stdlib; no entrena modelos, no calcula ninguna métrica, no observa ningún dato; familia
> independiente de `tools/datacontracts`, sin tipos compartidos; no conoce protocolo de hooks, es
> core.
>
> `tools/modelquality/validation.py` | Evaluación de `ModelQualityPolicy` contra métricas ya
> reportadas (v0.7 Change 2: `evaluate_policy`, códigos `QUALITY-*`, produce
> `dsguard.checks.CheckResult`) -- importa `dsguard.checks` y `tools.modelquality.core` (sibling);
> sin ninguna superficie de I/O ni de lectura de archivo; nunca recalcula ni verifica que el valor
> reportado sea numéricamente correcto (decisión 1 del roadmap); vocabulario `PASS`/`WARN`/`FAIL`/
> `N/A`, nunca `PASS` por falta de evidencia; no conoce protocolo de hooks, es core.

### Instalabilidad

Tres entradas `VERBATIM` en `MANIFEST` (`tools/modelquality/__init__.py`,
`tools/modelquality/core.py`, `tools/modelquality/validation.py`) con `stage_minimo` por defecto
(`"discovery"`, mismo criterio que `tools/datacontracts`: declarar/evaluar política de modelo es
actividad disponible desde el primer stage, sin depender de `ds_profile`/`dsimpact` opcionales).
Los tests del paquete no se instalan (mismo patrón que `tools/reporting/tests/` y
`tools/datacontracts/tests/`).

## Target (condicional — feature_engineering, modeling)
No aplica.

## Features permitidas/prohibidas (condicional — feature_engineering)
No aplica.

## Estrategia de split/validación (condicional — holdout involucrado, modeling, evaluation)
No aplica un split de modelado propio de este Change: `EvaluationContext.split` es un campo
DECLARADO por quien construye `ObservedMetric`/`BaselineReference`/`MetricRequirement.
required_context`, nunca calculado ni verificado contra un dataset real por este módulo (ver
"Holdout policy" en `proposal.md`).

## Leakage risks (condicional — feature_engineering, data_preparation, modeling)
No aplica a features de modelado (este Change no entrena ni calcula nada). Riesgo de diseño
relacionado, mitigado explícitamente: si `evaluate_policy` alguna vez recalculara una métrica desde
datos crudos en vez de recibir `ObservedMetric.value` ya reportado, correría el riesgo de tener que
abrir un holdout sin pasar por ningún guard (porque este módulo no tiene guard de holdout, ver
"Holdout policy"). Mitigación: `evaluate_policy` y todo el paquete `tools/modelquality` NO aceptan
en ningún constructor un parámetro que represente datos crudos, predicciones, un `DataFrame` ni una
ruta de dataset/holdout — la única entrada numérica es `ObservedMetric.value`, un `float` ya
calculado externamente.

## Reproducibilidad (opcional — solo si se desvía del default: RANDOM_STATE fijo, .venv)
No aplica aleatoriedad: no hay `RANDOM_STATE`. El determinismo se garantiza por la misma
serialización canónica (`sort_keys`, separadores fijos, sin `NaN`) que `tools/datacontracts/core.py`,
y porque `evaluate_policy` es una función pura (misma entrada → misma salida, mismo orden).

## Alternativas descartadas (adicionales a las de cada decisión numerada arriba)
1. **Un solo módulo `tools/modelquality/core.py` con TODO (declaración + evaluación)**, sin separar
   `validation.py`: rechazada; rompería el patrón dual ya establecido por
   `tools/datacontracts` (Changes 0-1) y por `tools/reporting` (`core.py` + `validation.py`), sin
   ninguna ganancia — mezclar dataclasses `frozen=True` de declaración con funciones que producen
   `CheckResult` (que sí necesitan importar `dsguard.checks`) forzaría a que la declaración misma
   dejara de ser "solo-stdlib", perdiendo la propiedad de neutralidad que Change 0 estableció como
   valiosa para reutilización futura (p. ej. Change 3/v0.8 podrían querer importar solo `core.py`
   sin arrastrar `dsguard`).
2. **`MetricRequirement` con un único campo `severity` (en vez de `threshold_severity` y
   `baseline_severity` separados)**: rechazada; threshold y baseline son etapas de evaluación
   independientes (decisión 6) que pueden, legítimamente, tener consecuencias distintas si fallan
   (p. ej. "el umbral mínimo absoluto es un `FAIL` duro, pero una pequeña regresión respecto del
   baseline solo amerita `WARN`") — mismo criterio que Change 0 exige severidad por regla, no por
   contrato completo (`docs/roadmap/v0.7.md:89-91`).
3. **No separar `EvaluationContext` como tipo propio, usar un `str` de split suelto en cada
   lugar**: rechazada; el roadmap lista `EvaluationContext` como concepto propio de primera clase
   (`docs/roadmap/v0.7.md:239`), y reutilizarlo como un único tipo compartido entre
   `MetricRequirement.required_context`, `ObservedMetric.context` y `BaselineReference.context`
   permite comparación estructural directa (decisión 4) en vez de parsear texto libre en cada
   punto de comparación.

## Riesgos
- **`Optional[str]` para `evidence_ref` en vez de obligatorio**: riesgo de que un llamador
  construya `ObservedMetric` sin procedencia "por comodidad" y nunca lo note hasta evaluar; mitigado
  porque `evaluate_policy` NUNCA emite `PASS` en ese caso (decisión 5) — el costo se paga en
  evaluación, no en construcción, documentado explícitamente como decisión (no como omisión).
- **Duplicación de helpers de id/nombre entre `tools/datacontracts/core.py` y
  `tools/modelquality/core.py`** (mismo patrón regex, dos implementaciones): riesgo de drift si un
  patrón cambia en un módulo y no en el otro; aceptado por la misma razón que Change 0 aceptó
  duplicar `SEVERITIES` en vez de importar `dsguard.checks` — mantener las dos familias sin
  dependencia cruzada es más valioso que evitar esta duplicación puntual y pequeña; se documenta
  como deuda vigilada (mismo criterio que la deuda 6 de `ARCHITECTURE.md` §4.1).
- **Selección de `ObservedMetric` puramente estructural (decisión 4) puede quedar `WARN`
  "ambiguo" en casos donde un humano vería trivialmente cuál métrica es la correcta** (p. ej. dos
  reportes idénticos por error de doble ejecución): aceptado; el binario no debe adivinar — un
  `WARN` visible es preferible a una elección silenciosa incorrecta, y corresponde al Lead/
  metodólogo limpiar la duplicación en el reporte de evidencia.
- **Vocabulario `COMPARISON_MODES`/`UNCERTAINTY_KINDS` cerrado**: si en el futuro aparece una
  necesidad real de un modo de comparación o un tipo de incertidumbre no cubierto, requiere un SDD
  propio para extender el vocabulario (mismo patrón que `CONSTRAINT_TYPES` de Change 0); riesgo
  aceptado como el costo normal de un vocabulario cerrado sin DSL arbitrario.

## Aprobación humana
El registro de aprobación (usuario, fecha, alcance, versión de artefactos, cita) es único por
cambio y vive en la sección "Aprobación" de `proposal.md` — no se duplica acá.

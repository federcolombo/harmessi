# Propuesta — 20260922-model-quality-policies

## Problema
Harmessi v0.7 puede hoy declarar y evaluar expectativas de **datos** (`DataContract` +
`validate_contract`, Changes 0-1), pero no existe ningún objeto que declare qué calidad mínima se
exige a un **modelo**, ni ninguna función que compare una métrica reportada contra esa exigencia
(`docs/roadmap/v0.7.md:18-19`: "qué calidad mínima se exige a un modelo; qué métricas reales fueron
observadas; contra qué baseline o referencia se compararon"). Sin esto, Harmessi no puede "hacer
cumplir lo determinista" (`docs/roadmap/v0.7.md:29`) sobre calidad de modelo, y cualquier intento
futuro (reporting de resultados de evaluación, Change 4 CLI, v0.8 Model Cards) reinventaría su
propia noción ad-hoc de "esta métrica pasa/no pasa", repitiendo el problema que `DataContract`/
`validate_contract` ya resolvieron para datos.

El riesgo central, ya identificado y congelado como decisión 1 del roadmap
(`docs/roadmap/v0.7.md:77-83`), es que "formalizar calidad de modelo" se confunda con "calcular
métricas de modelo": Harmessi v0.7 explícitamente NO entrena modelos, NO calcula AUC/F1/RMSE ni
ninguna métrica desde predicciones — eso lo calcula el proyecto (notebook/código), fuera de
Harmessi. Sin una declaración de diseño escrita, un futuro Change (o una implementación apurada de
este mismo) podría deslizarse hacia "conviene que el binario recalcule la métrica para estar
seguro", lo cual es exactamente la expansión de scope que la decisión 1 marca como STOP.

## Objetivo
Crear un paquete nuevo `tools/modelquality/` con dos módulos, mismo patrón dual que
`tools/datacontracts/core.py` + `validation.py` (Changes 0-1) pero entregados en un solo Change:

- `core.py` (declaración, solo-stdlib): `ModelQualityPolicy`, `MetricRequirement`,
  `EvaluationContext`, `ObservedMetric`, `BaselineReference` — tipos neutrales, serializables,
  deterministas, sin observar ni calcular ninguna métrica.
- `validation.py` (evaluación determinista): `evaluate_policy(policy, observed_metrics, baselines)
  -> list[CheckResult]`, que verifica existencia y vigencia estructural de evidencia, contexto de
  evaluación, threshold y baseline/reference, en el orden fijo confirmado por el usuario (ver
  "Aprobación"), **sin recalcular ni verificar que el valor reportado sea el correcto**.

## Evidencia
- `docs/roadmap/v0.7.md:228-294` (Change 2 completo): objetivo ("formalizar políticas de calidad
  del modelo sin entrenar modelos y sin calcular métricas"), conceptos candidatos
  (`ModelQualityPolicy`, `MetricRequirement`, `ObservedMetric`, `BaselineReference`,
  `EvaluationContext`), lo que una política debe declarar, el orden de evaluación fijo, y lo que
  este Change NO hace (entrenar, elegir algoritmo, seleccionar features, inferir qué métrica
  importa, decidir trade-offs de negocio).
- `docs/roadmap/v0.7.md:77-83` (decisión 1, congelada, la más relevante de este Change): "El
  binario no calcula métricas de modelo... Un `ObservedMetric` es un valor reportado con
  procedencia (evidence ref + hash + contexto). El binario verifica el valor contra umbral y
  baseline, y que la evidencia exista y esté vigente; no verifica que el número sea el correcto...
  No se implementan calculadores de AUC/F1/RMSE/etc."
- `docs/roadmap/v0.7.md:256-268` (orden de evaluación, texto fuente del diagrama): "métrica
  observada → evidencia vigente → threshold → baseline/reference → PASS/WARN/FAIL/N/A", con la
  descripción semántica de cada etapa y la regla "cada etapa solo puede empeorar el resultado,
  nunca mejorarlo".
- `docs/roadmap/v0.7.md:64-71` (reglas de separación DECLARACIÓN/OBSERVACIÓN/EVALUACIÓN): "el
  contrato/política no contiene observaciones, y la observación no contiene reglas"; "la evaluación
  es una función pura `(declaración, observación) → list[CheckResult]`"; "lo que el binario no
  puede verificar... se reporta como no verificable (WARN/N/A), nunca como PASS".
- `docs/roadmap/v0.7.md:89-91` (decisión 3): severidad declarada en la política, verificabilidad
  decidida por el binario; no verificable → `WARN`/`N/A`, nunca `PASS`.
- `docs/roadmap/v0.7.md:92-95` (decisión 4): `technical_error` no es un resultado de calidad, se
  reporta aparte, sin contaminar el conteo.
- `docs/roadmap/v0.7.md:96-101` (decisión 5): quality no es gate; este Change no modifica
  readiness/promotion/lifecycle ni produce ningún side-effect sobre esas superficies.
- `docs/roadmap/v0.7.md:297-346` (Change 3, para no adelantarlo): evidencia persistida con hashes,
  `generated_at`, drift — explícitamente fuera de este Change; `ObservedMetric`/`BaselineReference`
  de este Change 2 llevan solo una referencia de procedencia genérica (`evidence_ref: str`), sin
  hash de bytes persistidos ni `generated_at`, que es responsabilidad de Change 3.
- `tools/datacontracts/core.py:1-39` (docstring completo) y `tools/datacontracts/validation.py:1-58`
  (docstring completo): patrón de referencia más cercano en todo el repo — dataclasses
  `frozen=True` para la declaración, función pura + (cuando aplica) puerta de I/O para la
  evaluación, `dsguard.checks.CheckResult` como tipo de retorno, nunca `PASS` por falta de
  evidencia, severidad declarada vs. verificabilidad decidida por el binario. Este Change 2 replica
  el patrón dual `core.py`/`validation.py`, pero — a diferencia de Changes 0-1 — entrega AMBOS
  módulos en un solo Change, porque el roadmap no desglosa "declaración" y "evaluación" de
  políticas de modelo en dos Changes separados (solo Changes 3-5 siguen a Change 2).
- `tools/dsguard/checks.py:14-56`: vocabulario `STATUS_PASS/WARN/FAIL/N_A`,
  `KIND_CHECK`/`KIND_TECHNICAL_ERROR`, `CheckResult(status, code, message, detail, subject, kind)`
  — el tipo de retorno exacto de `evaluate_policy`.
- `openspec/changes/20260922-data-contracts-core/design.md:27-33` (alternativa descartada 1 de
  Change 0): "`datacontracts` deja lugar a que un futuro paquete de política de modelo tenga su
  propio nombre (p. ej. `tools/modelquality`) sin ambigüedad" — Change 0 ya reservó explícitamente
  ese nombre candidato para este Change 2.
- `ARCHITECTURE.md:103-150` (§3, reglas de dependencia 1-7): la regla 7 (familia
  `tools/datacontracts`) es el precedente directo para una regla 8 nueva de este Change
  (`tools/modelquality`); hoy no existe ninguna fila en §2.1 ni regla en §3 para un paquete de
  políticas de modelo.
- `openspec/changes/20260922-data-contract-validation/design.md:41-69` (decisión de diseño 2 de
  Change 1): patrón función-pura-sin-I/O vs. puerta-con-I/O, replicado en el diseño de
  `evaluate_policy` de este Change — aunque, a diferencia de Change 1, este Change 2 **no necesita**
  una puerta de I/O propia (ver "Supuestos descartados").

## Supuestos descartados
- Que este Change deba leer un archivo de evidencia persistida (equivalente a
  `validate_contract_against_profile_file`) para cargar `ObservedMetric`/`BaselineReference` desde
  disco, con su propio guard de holdout. Descartado: la persistencia de evidencia con hash y
  `generated_at` es explícitamente Change 3 (`quality-evidence-and-drift`,
  `docs/roadmap/v0.7.md:297-321`); este Change 2 solo declara la FORMA en memoria de
  `ObservedMetric`/`BaselineReference` (valores ya reportados, pasados como objetos Python) y una
  función pura de evaluación — sin ningún formato de archivo propio todavía, por lo tanto sin
  ninguna superficie de I/O ni de holdout guard que aplicar en este Change.
- Que `ObservedMetric` deba incluir un hash de contenido y un `generated_at` reales (como
  anticipa, de forma resumida, la decisión 1 del roadmap: "evidence ref + hash + contexto").
  Descartado para este Change específicamente: la decisión 1 describe la FORMA CONCEPTUAL completa
  de la idea "métrica con procedencia" a nivel de todo v0.7, pero el hash de bytes persistidos y
  `generated_at` solo tienen sentido una vez que existe un formato de evidencia persistida real
  (Change 3). En este Change, `evidence_ref` es un `str` genérico (identificador/puntero de
  procedencia: ruta, id de corrida, celda de notebook, URI) sin verificación criptográfica ni de
  frescura temporal — ver `design.md`, decisión 2, para la justificación completa de qué campos son
  razonables en este Change sin adelantar Change 3.
- Que `ModelQualityPolicy` deba incluir un tipo de "versión de política" análogo a
  `ContractVersion` de Change 0. Descartado: el roadmap no lista ningún concepto de versión para
  Change 2 (solo `ModelQualityPolicy`, `MetricRequirement`, `ObservedMetric`, `BaselineReference`,
  `EvaluationContext`, `docs/roadmap/v0.7.md:233-239`); agregar uno sería inventar superficie de
  API no pedida (mismo criterio que Change 0 rechazó un stub de `evaluate` "por si acaso",
  `openspec/changes/20260922-data-contracts-core/design.md:335-338`). `ModelQualityPolicy` sí lleva
  `schema_version` (versión del ESQUEMA de este módulo, mismo patrón que `DataContract`), no una
  versión de negocio del contenido de la política.
- Que el "modo de comparación" contra baseline deba admitir una expresión arbitraria (fórmula
  libre). Descartado de plano: el propio brief de esta invocación exige "nada de
  `eval`/lambda/código serializado", igual que Change 0 prohibió un DSL de invariantes
  (`docs/roadmap/v0.7.md:182-183`); se adopta un vocabulario cerrado de 3 modos declarativos
  (`absolute`, `relative_to_baseline`, `absolute_diff_from_baseline`) con parámetros
  (`comparison_tolerance`), análogo a como `Constraint.params` de Change 0 declara forma sin
  evaluar código (ver `design.md`, decisión 3).
- Que "evidencia requerida" (`evidence_ref` no vacío) deba ser un campo configurable por política
  (p. ej. `evidence_required: bool` en `MetricRequirement`, espejando el patrón inicial explorado
  para datos). Descartado: la decisión 1 del roadmap lo formula como regla ABSOLUTA, no
  configurable ("Sin evidencia vigente no hay `PASS`, aunque el valor cumpla el umbral" —
  `docs/roadmap/v0.7.md:271-272`, sin condicional de política); el binario siempre intenta
  verificar `evidence_ref`, para toda métrica observada, sin que ninguna política pueda desactivar
  ese chequeo. Lo que sí es configurable por política es `uncertainty_required` (el propio roadmap
  lo formula condicionalmente: "incertidumbre/evidencia requerida **cuando corresponda**",
  `docs/roadmap/v0.7.md:250-252`).
- Que el binario deba decidir automáticamente cuál `ObservedMetric` "gobierna" cuando el proyecto
  reporta varias métricas con el mismo `metric_name` pero contextos distintos (p. ej. AUC en
  `train` y AUC en `test`), aplicando alguna heurística de prioridad (p. ej. "usar siempre la de
  `test`"). Descartado: sería una decisión metodológica ("qué métrica importa"), prohibida
  explícitamente para este Change (`docs/roadmap/v0.7.md:291`, "inferir qué métrica debería
  importar"); en cambio, la selección es puramente estructural — por `metric_name` y coincidencia
  exacta de contexto contra `MetricRequirement.required_context` — y un caso ambiguo (más de un
  candidato tras filtrar por contexto) es `WARN` "no verificable cuál gobierna", nunca una elección
  automática (ver `design.md`, decisión 4).

## Hipótesis (condicional — solo cambios metodológicos)
No aplica.

## Alcance
- `tools/modelquality/__init__.py` y `tools/modelquality/core.py` (solo stdlib): vocabularios,
  `ModelQualityError`, `EvaluationContext`, `MetricRequirement`, `ObservedMetric`,
  `BaselineReference`, `ModelQualityPolicy`, `canonical_json`,
  `ModelQualityPolicy.content_sha256()`.
- `tools/modelquality/validation.py`: códigos `QUALITY-*`, `evaluate_policy(policy,
  observed_metrics, baselines) -> list[CheckResult]` (pura, sin I/O), fold monotónico
  PASS→WARN→FAIL de "solo puede empeorar", las reglas de selección/evidencia/threshold/baseline
  descritas en `design.md`.
- `tools/modelquality/tests/__init__.py`, `test_core.py`, `test_validation.py`,
  `test_installability.py`.
- `tools/tests/test_v07_modelquality_neutrality.py` (nuevo, patrón `ast` análogo a
  `test_v07_core_neutrality.py`/`test_v07_validation_neutrality.py`, cubriendo ambos módulos de
  este Change en un solo archivo) y agregar `tools/modelquality/core.py` y
  `tools/modelquality/validation.py` a `MODULOS_CORE` en `tools/tests/test_architecture_boundaries.py`.
- `tools/ds_init/manifest.py`: tres entradas VERBATIM (`tools/modelquality/__init__.py`,
  `tools/modelquality/core.py`, `tools/modelquality/validation.py`) con `stage_minimo` por defecto
  (`discovery`).
- `ARCHITECTURE.md`: filas nuevas en §2.1 (una por módulo) y regla 8 en §3.
- `docs/roadmap/v0.7.md`: al cerrar el Change, tildar `[x] Change 2`.
- `openspec/changes/20260922-model-quality-policies/verification.md` (al cierre, invocación 5).

Ver `tasks.md` para el desglose exacto de rutas por invocación.

## Fuera de alcance
- Entrenar modelos, elegir algoritmo, seleccionar features, o cualquier forma de AutoML.
- Calcular, aproximar o recalcular cualquier métrica de modelo (AUC, F1, RMSE, precision, recall,
  calibración, etc.) desde predicciones, residuos o cualquier dato crudo. `ObservedMetric.value` es
  siempre un valor YA reportado por el proyecto; este Change no lo produce ni lo verifica
  numéricamente.
- Inferir qué métrica debería importar para una tarea dada, o decidir trade-offs de negocio entre
  métricas (p. ej. precision vs. recall) — decisión metodológica del Lead/metodólogo.
- Persistencia de evidencia con hash de bytes, `generated_at`, staleness temporal real, y
  cualquier noción de drift: Change 3 (`quality-evidence-and-drift`).
- Cualquier formato de archivo propio para `ObservedMetric`/`BaselineReference`/
  `ModelQualityPolicy` en disco (lectura/escritura), y por lo tanto cualquier guard de holdout
  sobre esa lectura: no existe superficie de I/O en este Change (ver "Supuestos descartados").
- CLI (`harmessi quality ...`), integración con `status`, impact preflight de políticas de modelo:
  Change 4 (`quality-integration-and-cli`).
- Cualquier cambio a `tools/datacontracts/{core,validation}.py` (Changes 0-1, cerrados e
  inmutables); `tools/modelquality` es una familia paralela e independiente, sin tipos
  compartidos con `tools/datacontracts` (mismo criterio de frontera conceptual que Change 0 ya
  documentó, `openspec/changes/20260922-data-contracts-core/design.md:19-24`).
- Cualquier cambio a `dsguard`, `ds_profile`, `dsimpact`, `reporting`, `providers`, `routing`,
  `fallback`, `harmessi_bench` salvo el registro de manifest y la fila/regla de
  `ARCHITECTURE.md` listados en "Alcance".
- Leer, escribir o inferir sobre cualquier dataset o holdout real, sintético o de ejemplo.

## Holdout policy (condicional — solo cambios "sensible")
No aplica, y esto se confirma razonando, no se asume: este Change declara tipos en memoria
(`ModelQualityPolicy`, `MetricRequirement`, `EvaluationContext`, `ObservedMetric`,
`BaselineReference`) y una función pura de evaluación que los compara entre sí. `ObservedMetric`
es, por decisión 1 del roadmap, "un valor ya reportado" — un número que el proyecto YA calculó
externamente (posiblemente, en la práctica, sobre un split `holdout`, según el propio roadmap
señala: "la evaluación sobre un split `holdout` solo tiene sentido en la fase de evaluación final",
`docs/roadmap/v0.7.md:286-287`) y que este Change recibe como argumento de un objeto Python, nunca
como una ruta de archivo o un dataset. Este Change **no abre ningún archivo**, no conoce ninguna
ruta de dataset ni de perfil, y por lo tanto no tiene ninguna superficie donde el guard de holdout
existente (`ds_profile.holdout_guard`) pudiera aplicarse — a diferencia de Change 1, que sí lee
`profile.json` desde disco y por eso sí aplicó el guard. Si un `ObservedMetric.context.split ==
"holdout"` llega a este módulo, se evalúa exactamente igual que cualquier otro split declarado: el
binario nunca abre el holdout, solo compara el número ya reportado
(`docs/roadmap/v0.7.md:287-288`, "el binario nunca abre el holdout: consume un `ObservedMetric` ya
reportado con su evidencia").

## Impacto en production-readiness (opcional)
No aplica en este bloque: decisión 5 del roadmap (`docs/roadmap/v0.7.md:96-101`) fija que ningún
resultado de v0.7 modifica readiness, promotion gates ni el lifecycle; `evaluate_policy` produce
únicamente `list[CheckResult]` en memoria, sin ningún side-effect sobre `status`/`project
readiness`/`project promote`.

## Criterios de aceptación (spec-lite — solo SDD abreviado)
Ver `spec.md` (SDD completo).

## Decisión técnica (design-lite — solo SDD abreviado)
Ver `design.md` (SDD completo).

## Aprobación
- Usuario: Federico Colombo
- Fecha: 2026-09-22
- Alcance aprobado: "Change 2 — model-quality-policies (docs/roadmap/v0.7.md)"
- Versión de artefactos referenciada: esta versión de los 4 archivos (commit de este Change)
- Cita del contrato de autonomía: "Ejecutá autónomamente los Changes de docs/roadmap/v0.7.md ...
  Change 2 — model-quality-policies ... audit acotado → SDD → validación contra
  roadmap/arquitectura → implementación → tests → reviewer → fixes → re-tests → verification →
  cierre → commit local (instrucción explícita del usuario, 2026-09-22, bajo el Contrato de
  autonomía de `docs/roadmap/README.md`)."
- Confirmación EXPLÍCITA del usuario sobre el orden de evaluación de métricas, transcripta literal
  (contrato fijo para este Change, no reabribible sin STOP):
  > "1. En v0.7 Harmessi NO calcula métricas de modelo... El binario de Harmessi verifica de forma
  > determinista: existencia y vigencia de evidencia; contexto de evaluación; threshold;
  > baseline/reference; dirección de la métrica; resultado PASS/WARN/FAIL/N/A. No verifica en v0.7
  > que la métrica haya sido correctamente calculada... No implementar calculators de
  > AUC/F1/RMSE/etc."

## Motivo de rechazo
No aplica.

## Desacuerdo registrado
No aplica.

# Propuesta — 20260922-quality-evidence-and-drift

## Problema
Harmessi v0.7 ya puede declarar y evaluar expectativas de datos (`DataContract` +
`validate_contract`, Changes 0-1) y de modelo (`ModelQualityPolicy` + `evaluate_policy`, Change 2),
produciendo `list[dsguard.checks.CheckResult]` en memoria. Pero ninguno de esos resultados se
**persiste**: hoy, en cuanto termina el proceso Python que llamó a `validate_contract`/
`evaluate_policy`, la evidencia de que esa evaluación ocurrió (contra qué versión de contrato/
política, con qué hash, en qué momento, contra qué evidencia de origen) desaparece. Tampoco existe
ningún objeto que compare dos observaciones del mismo dataset/métrica a través del tiempo
(`docs/roadmap/v0.7.md:20-21`: "qué cambió entre versiones de un contrato; qué evidencia sostiene
el resultado" y sección Change 3, `docs/roadmap/v0.7.md:297-346`). Sin esto, ni Reporting v0.6 ni
un futuro `harmessi status`/`quality` (Change 4) ni v0.8 (Model/Data Cards) tienen ningún archivo
real al que apuntar como evidencia de calidad: cada consumidor reinventaría su propio formato ad
hoc, y "drift" quedaría sin ninguna definición operativa acotada en el repo.

El riesgo central, ya identificado y congelado como decisión 6 del roadmap
(`docs/roadmap/v0.7.md:102-104`), es que "drift" se confunda con una alerta o un veredicto
("¿el modelo driftió, sí o no?"): el roadmap exige que drift sea evidencia comparativa explícita
(ventana de referencia, ventana actual, métrica, diferencia observada, umbral/política, resultado),
nunca una afirmación de "model drift" sin ese contexto completo. Un segundo riesgo, señalado
explícitamente en el brief de esta invocación y en `tools/reporting/evidence.py` (v0.6 Change 3,
`docs/roadmap/v0.7.md:337-343`), es duplicar sin necesidad la infraestructura de evidencia que ya
existe en el repo (`reporting.evidence`, `mlops_evidence.py`) en vez de decidir con evidencia real
si conviene reutilizarla o si crea una dependencia cruzada nueva no prevista.

## Objetivo
Crear un paquete nuevo `tools/qualityevidence/` con dos módulos, mismo patrón dual `core.py` +
módulo-de-evaluación/IO que `tools/datacontracts` y `tools/modelquality`:

- `core.py` (declaración de la FORMA de la evidencia, solo-stdlib): `QualityEvidenceManifest`,
  `DriftEvidence`, `EvidenceSource`, `DeclarationRef`, `ScopeWindow` — tipos neutrales,
  serializables, deterministas, que NO calculan nada ni tocan disco.
- `evidence.py` (persistencia y drift, con I/O acotado): construye y escribe manifests de evidencia
  de calidad (envolviendo `list[CheckResult]` ya producidos por `validate_contract`/
  `evaluate_policy`) bajo `.harmessi/quality/`, con hash de contenido y `generated_at` separado; y
  calcula `DriftEvidence` comparando dos observaciones (naturalmente, dos `profile.json`) con un
  vocabulario cerrado de dos modos de comparación acotados (diferencia absoluta, diferencia
  relativa), nunca una biblioteca estadística universal.

Un reporte de Reporting v0.6 puede consumir esta evidencia como un archivo más con hash (vía
`reporting.evidence.describe_source`, ya existente, sin que `tools/reporting` importe
`tools.qualityevidence` ni viceversa) — ver `design.md`, decisión 2.

## Evidencia
- `docs/roadmap/v0.7.md:297-346` (Change 3 completo): objetivo, campos que la evidencia debe poder
  registrar, requisitos de la evidencia (reproducible, portable/sin datos privados, separa
  `technical_error`, ubicación distinta de la declaración), campos separados de drift, "observador
  natural: dos `profile.json`", integración con Reporting v0.6, fuera de alcance.
- `docs/roadmap/v0.7.md:102-104` (decisión 6, congelada): "Drift es evidencia comparativa, no un
  veredicto... No se afirma 'model drift' por un cambio de distribución sin contexto suficiente."
- `docs/roadmap/v0.7.md:318-321`: "portable y sin datos privados: paths repo-relativos. Nota
  concreta: `ds_profile` persiste `dataset_path` como `str(ruta_input)`, que puede ser absoluto; la
  evidencia de v0.7 no debe copiarlo tal cual."
- `docs/roadmap/v0.7.md:337-343` (integración con Reporting v0.6): "un reporte puede consumir
  resultados de calidad como fuentes/evidence refs con hash, usando el manifest y la validación
  stale existentes; reporting no genera la evidencia, no convierte `WARN` en `PASS` y no altera
  lifecycle/readiness por mostrar un resultado; si la integración exige cambiar el schema del
  manifest de v0.6 de forma incompatible → STOP."
- `docs/roadmap/v0.7.md:112-127` (reglas de arquitectura para el código de v0.7): "los paquetes de
  v0.7 pueden importar `dsguard.checks` y consumir `profile.json` como archivo; `dsguard`,
  `ds_profile`, `dsimpact`, `reporting`... no importan los paquetes de v0.7"; "reporting consume
  evidencia de calidad **como archivo con hash**..., no importando el paquete de calidad" — fija
  UNA dirección (reporting no importa quality); no fija la dirección inversa, resuelta en
  `design.md` decisión 2 con evidencia real, no por omisión.
- `tools/reporting/evidence.py:1-43` (docstring completo): manifest de reportes con `hashes`,
  `generated_at`, `sources`, escritura atómica (`write_report_dir`), lectura verificada
  (`load_report_dir`), aislamiento por hash — mecanismo de referencia más cercano en todo el repo,
  pero acoplado a la FORMA de un `Report` (`report_id`, `decision_scope`, `holdout_access`,
  `source_notebook`, `sensitivity`) que no tiene sentido para evidencia de calidad de datos/modelo.
- `tools/dsguard/mlops_evidence.py:1-23,50-60` (docstring + hash local): precedente EXPLÍCITO en
  este mismo repo de "duplicar un primitivo pequeño (sha256 chunked) en vez de importar el módulo
  hermano que ya lo tiene, para preservar la dirección de dependencia establecida" — la
  justificación textual ("mantiene la única dirección de dependencia cruzada existente hoy") es
  exactamente el mismo razonamiento que aplica acá para decidir NO importar
  `tools.reporting.evidence` (ver `design.md`, decisión 2).
- `ARCHITECTURE.md:107-165` (§3, reglas 1-8): ninguna regla existente cubre un paquete nuevo que
  registre evidencia de AMBAS familias (datos y modelo); la regla 6 (reporting) fija que
  `dsguard`/`ds_profile`/`dsimpact`/`providers`/`routing`/`fallback`/`harmessi_bench` no importan
  `reporting`, pero no menciona `tools.datacontracts`/`tools.modelquality` (paquetes que no
  existían cuando se escribió la regla 6, v0.6 Change 4) — hace falta una regla 9 nueva (ver
  `design.md`, decisión 6).
- `tools/datacontracts/core.py:1-39,793-796` y `tools/modelquality/core.py:1-32,721-724`
  (docstrings + `content_sha256()`): patrón exacto de serialización determinista/hash de contenido
  que `QualityEvidenceManifest`/`DriftEvidence` replican, sin importar ninguno de los dos módulos
  (ver "Alcance" y `design.md`).
- `tools/modelquality/core.py:479-519` (`ObservedMetric`) y
  `openspec/changes/20260922-model-quality-policies/design.md:85-118` (decisión 2 de Change 2):
  "`evidence_ref` es... deliberadamente genérico... Change 3 podrá, en su propio SDD, decidir si
  reinterpreta `evidence_ref` como una ruta bajo `.harmessi/` con hash verificable, sin que este
  Change se comprometa de antemano con esa forma" — punto de conexión explícito que este Change
  resuelve por CONVENCIÓN externa (ver `design.md`, decisión 5), sin tocar
  `tools/modelquality/core.py` (inmutable, Change 2 cerrado).
- `tools/dsguard/checks.py:14-56`: vocabulario `CheckResult`/`STATUS_*`/`KIND_*` — tipo que
  `evidence.py` envuelve (recibe `list[CheckResult]` ya producidos por el llamador) y que reutiliza
  para sus propios `CheckResult` de resultado de drift/staleness.
- `tools/ds_profile/fingerprint.py:15,18-29` (`ALGORITMO = "sha256/bin/v1"`,
  `calcular_fingerprint`): algoritmo de hash de referencia en todo el repo — este Change reimplementa
  localmente el mismo cálculo (sha256 binario chunked) sin importar `ds_profile.fingerprint` (ver
  `design.md`, decisión 2).
- `tools/ds_profile/holdout_guard.py:89-104` (`verificar_permitido(ruta_input, repo_root) ->
  (bool, str)`): mismo guard ya reutilizado por `tools/datacontracts/validation.py:71-72,789` para
  leer `profile.json`; este Change lo reutiliza igual, para leer los dos `profile.json` de una
  comparación de drift.

## Supuestos descartados
- Que este Change deba importar `tools.reporting.evidence` para reusar sus funciones de hash/
  manifest, por el precedente de "no duplicar" (`docs/roadmap/v0.7.md:38,122-123`, "Reutilizar
  capacidades existentes siempre que sea posible"). Descartado tras comparar el costo real: importar
  `reporting.evidence` arrastra `reporting.core`, `reporting.governance` (destinos por scope,
  aislamiento exploratory, `pathguard.evaluar_tool_call`) y produce un manifest con forma de
  REPORTE (`report_id`, `decision_scope`, `holdout_access`, `sensitivity`, `source_notebook`) que no
  mapea a evidencia de calidad de datos/modelo; y crearía una dirección de dependencia nueva
  (`tools.qualityevidence -> tools.reporting`) no prevista por ninguna regla de `ARCHITECTURE.md`.
  "Reutilizar capacidades" se satisface reutilizando el mismo ALGORITMO de hash (`sha256/bin/v1`,
  documentado como coincidencia, mismo criterio que `SEVERITIES` entre Changes 0-2) y el mismo
  patrón de manifest (hashes + `generated_at` separado + escritura atómica), no necesariamente vía
  `import`. Precedente directo en el propio repo: `mlops_evidence.py` ya tomó esta misma decisión
  para no depender de `ds_profile.fingerprint` (ver "Evidencia"). Ver `design.md`, decisión 2, para
  el análisis completo con las 3 alternativas.
- Que `tools/qualityevidence` deba importar `tools.datacontracts.core`/`tools.modelquality.core`
  para tipar `DeclarationRef` con las dataclasses reales (`DataContract`/`ModelQualityPolicy`).
  Descartado: mantener a `tools.qualityevidence` sin ninguna dependencia de ninguna de las dos
  familias preserva la independencia ya establecida entre `datacontracts` y `modelquality`
  (`ARCHITECTURE.md:154-159`, regla 8: "familia independiente, sin tipos compartidos") y evita que
  `qualityevidence` se vuelva un "hub" que ambas familias deban actualizar. El llamador (quien ya
  tiene el `DataContract`/`ModelQualityPolicy` en memoria) extrae `contract_id`/`policy_id`/
  `version`/`content_sha256()` y pasa esos valores como `str` planos — mismo criterio que
  `evaluate_policy` recibe `ObservedMetric.value` como número ya calculado, nunca el objeto que lo
  calculó.
- Que `evaluate_policy`/`validate_contract` deban invocarse DESDE `tools.qualityevidence` (una
  función `record_and_evaluate(...)` que llame a ambos). Descartado: importar
  `tools.datacontracts.validation`/`tools.modelquality.validation` mezclaría EVALUACIÓN (Changes
  1-2, cerrados) con EVIDENCE (este Change), violando la separación de etapas del roadmap
  (`docs/roadmap/v0.7.md:45-71`, "DECLARACIÓN → OBSERVACIÓN → EVALUACIÓN DETERMINISTA → EVIDENCE →
  INTERPRETACIÓN", flujo unidireccional). `tools.qualityevidence` recibe siempre
  `results: list[CheckResult]` ya producidos por el llamador (el mismo patrón que
  `reporting.evidence.build_manifest` recibe un `Report` ya construido, sin construirlo él mismo).
- Que "drift" requiera una biblioteca estadística (tests de hipótesis, bootstrapping, series de
  tiempo). Descartado de plano por el brief y por el roadmap (`docs/roadmap/v0.7.md:333-335,345-346`
  y la instrucción de esta invocación): se implementan únicamente dos modos de comparación
  deterministas y acotados (diferencia absoluta, diferencia relativa) entre dos números YA
  observados, nunca calculados por este módulo desde datos crudos.
- Que este Change deba definir su propio `git_commit`/`git_dirty`/`harmessi_version` en el manifest
  (como hace `reporting.evidence.build_manifest`). Descartado para mantener acotado el import
  surface (evitaría importar `dsguard.repo` y leer `.ds_init/control.json`): el roadmap solo exige
  "artefacto/run de origen", que ya se cubre con `EvidenceSource` (hash del archivo/objeto de
  origen) y `evidence_id`; agregar procedencia de git es una extensión aditiva futura, sin romper
  `schema_version`, si algún Change posterior la necesita.

## Hipótesis (condicional — solo cambios metodológicos)
No aplica.

## Alcance
- `tools/qualityevidence/__init__.py` y `tools/qualityevidence/core.py` (solo stdlib):
  `QualityEvidenceError`, vocabularios (`SUBJECT_KINDS`, `DRIFT_COMPARISON_MODES`,
  `EVIDENCE_SOURCE_KINDS`, `SCHEMA_VERSION`), `EvidenceSource`, `DeclarationRef`, `ScopeWindow`,
  `QualityEvidenceManifest`, `DriftEvidence`, `to_dict()`/`from_dict()`/`canonical_json()`/
  `content_sha256()` por dataclass raíz.
- `tools/qualityevidence/evidence.py`: construcción y escritura atómica de
  `QualityEvidenceManifest` bajo `.harmessi/quality/<evidence_id>/manifest.json`; lectura verificada
  (hash propio); `describe_source`/`describe_generated_source` reimplementados localmente (sin
  importar `reporting.evidence`); `new_evidence_id`; construcción de `DriftEvidence` con las dos
  fórmulas acotadas, incluida una variante que lee dos `profile.json` (guardadas con
  `ds_profile.holdout_guard.verificar_permitido`) para un campo numérico de un allowlist acotado.
- `tools/qualityevidence/tests/__init__.py`, `test_core.py`, `test_evidence.py`,
  `test_installability.py`.
- `tools/tests/test_v07_qualityevidence_neutrality.py` (patrón `ast`, análogo a
  `test_v07_modelquality_neutrality.py`) y agregar ambos módulos a `MODULOS_CORE` de
  `tools/tests/test_architecture_boundaries.py`.
- `tools/ds_init/manifest.py`: dos entradas VERBATIM (`tools/qualityevidence/__init__.py`,
  `tools/qualityevidence/core.py`, `tools/qualityevidence/evidence.py` — tres en total) con
  `stage_minimo` por defecto (`discovery`).
- `ARCHITECTURE.md`: dos filas nuevas en §2.1 y regla 9 en §3 (texto exacto en `design.md`).
- `docs/roadmap/v0.7.md`: al cerrar el Change, tildar `[x] Change 3`.
- `openspec/changes/20260922-quality-evidence-and-drift/verification.md` (al cierre).

Ver `tasks.md` para el desglose exacto de rutas por invocación.

## Fuera de alcance
- Cualquier cambio a `tools/datacontracts/{core,validation}.py` o `tools/modelquality/{core,
  validation}.py` (Changes 0-2, cerrados e inmutables). En particular, `ObservedMetric.evidence_ref`
  y `BaselineReference.evidence_ref` NO cambian de tipo ni de forma: siguen siendo `Optional[str]`
  genérico; este Change solo define una CONVENCIÓN externa (formato de ruta bajo `.harmessi/
  quality/`) que `tools.qualityevidence` puede resolver si el `str` la sigue, nunca una obligación.
- Cualquier cambio a `tools/reporting/*` (v0.6, cerrado): este Change decide explícitamente NO
  importar `tools.reporting` (ver `design.md`, decisión 2) y por lo tanto no lo toca en absoluto.
- Monitoring continuo, scheduling, alertas, retraining automático, cualquier afirmación de "model
  drift" sin el contexto completo (ventana de referencia, ventana actual, métrica, diferencia,
  umbral, resultado) — `DriftEvidence` SIEMPRE lleva los seis campos juntos, nunca un booleano
  suelto de "hay drift".
- Cualquier estadística no acotada: tests de hipótesis, bootstrapping, series de tiempo, cálculo de
  percentiles/cuantiles no persistidos ya en `profile.json`. Los dos modos de `DRIFT_COMPARISON_
  MODES` son los únicos que este Change implementa.
- CLI (`harmessi quality ...`/`harmessi contract ...`), integración con `status`, impact preflight:
  Change 4 (`quality-integration-and-cli`).
- Calcular, recalcular o verificar numéricamente ninguna métrica de modelo ni estadística de datos
  no persistida ya por `ds_profile` (decisión 1 del roadmap, heredada de Change 2).
- Leer, escribir o inferir sobre cualquier dataset o holdout real, sintético o de ejemplo (solo se
  leen `profile.json` ya persistidos, con el guard existente).
- Cualquier cambio a `dsguard`, `ds_profile`, `dsimpact`, `reporting`, `providers`, `routing`,
  `fallback`, `harmessi_bench` salvo el registro de manifest y la fila/regla de `ARCHITECTURE.md`
  listados en "Alcance".

## Holdout policy (condicional — solo cambios "sensible")
Aplica parcialmente, y se razona en detalle porque este Change SÍ puede leer archivos del repo
(a diferencia de Change 2, que no tenía ninguna superficie de I/O). Dos superficies de lectura:

1. **Manifests de evidencia propios** (`.harmessi/quality/**/manifest.json`, ya escritos por este
   mismo paquete): no son datos ni holdout, son metadata de evaluación generada por Harmessi — se
   leen sin guard, mismo criterio que `reporting.evidence.load_report_dir` sin `repo_root` (uso
   local) y que `resolve_harmessi_version` lee `.ds_init/control.json` sin guard
   (`tools/reporting/evidence.py:407-415`, "config del harness, no datos").
2. **`profile.json` de origen para `DriftEvidence`** (dos archivos, baseline y actual): estos SÍ
   pueden estar bajo un directorio protegido según `guardrails.json` (p. ej. si alguien persistió un
   `profile.json` dentro de un holdout declarado, aunque no sea la práctica habitual). Este Change
   NUNCA lee un `profile.json` sin pasar antes por `ds_profile.holdout_guard.verificar_permitido`
   (mismo guard, mismo símbolo único, que `tools/datacontracts/validation.py:71-72,789` ya reutiliza
   para el mismo propósito) — una ruta denegada por el guard nunca se abre, y el resultado es un
   `CheckResult`/`DriftEvidence.result` `FAIL kind="technical_error"` explicando el rechazo, nunca
   un `PASS` ni una excepción sin capturar.

Este Change **no abre ningún dataset crudo, columna de datos ni holdout directamente**: solo abre
`profile.json` (metadata ya agregada/anonimizada por `ds_profile`, el observador autorizado por
decisión 2 del roadmap) y sus propios manifests de evidencia.

## Impacto en production-readiness (opcional)
No aplica: decisión 5 del roadmap (`docs/roadmap/v0.7.md:96-101`) fija que ningún resultado de v0.7
modifica readiness, promotion gates ni el lifecycle. Este Change persiste evidencia y compara
observaciones, sin ningún side-effect sobre `status`/`project readiness`/`project promote`.

## Criterios de aceptación (spec-lite — solo SDD abreviado)
Ver `spec.md` (SDD completo).

## Decisión técnica (design-lite — solo SDD abreviado)
Ver `design.md` (SDD completo).

## Aprobación
- Usuario: Federico Colombo
- Fecha: 2026-09-22
- Alcance aprobado: "Change 3 — quality-evidence-and-drift (docs/roadmap/v0.7.md)"
- Versión de artefactos referenciada: esta versión de los 4 archivos (commit de este Change)
- Cita del contrato de autonomía: "Ejecutá autónomamente los Changes de docs/roadmap/v0.7.md ...
  Change 3 — quality-evidence-and-drift ... audit acotado → SDD → validación contra
  roadmap/arquitectura → implementación → tests → reviewer → fixes → re-tests → verification →
  cierre → commit local (instrucción explícita del usuario, 2026-09-22, bajo el Contrato de
  autonomía de `docs/roadmap/README.md`)." (adaptada de la cita transcripta para Change 2 en
  `openspec/changes/20260922-model-quality-policies/proposal.md:225-229`, mismo contrato de
  autonomía vigente, aplicado ahora a Change 3)

## Motivo de rechazo
No aplica.

## Desacuerdo registrado
No aplica.

# Propuesta — 20260922-data-contract-validation

## Problema
Change 0 (`data-contracts-core`) dejó `DataContract`/`ContractField`/`Constraint`/`BusinessRule`
declarables, serializables y versionables, pero explícitamente sin evaluarlos contra nada
(`tools/datacontracts/core.py:12-17`: "Este módulo NO observa ni evalúa ningún dato... la
evaluación de un `DataContract` contra una observación real (`ds_profile`) es responsabilidad de
un Change posterior"). Hoy no existe ningún código que responda "¿qué estructura se observó?" ni
"¿cuáles reglas pasan/fallan/no aplican?" (`docs/roadmap/v0.7.md:15-17`): un `DataContract`
completo y un `profile.json` real de `ds_profile` conviven sin que nada los compare, así que
Harmessi no puede todavía "hacer cumplir lo determinista" (`docs/roadmap/v0.7.md:29`) sobre
estructura y calidad de datos.

Además, sin este Change, cualquier intento futuro de comparar un contrato contra evidencia real
(Change 2 políticas de modelo, Change 4 CLI/impact) reinventaría su propia noción de "evaluación",
repitiendo el problema que ya resolvió `tools/reporting/validation.py` para reportes: una función
pura `(declaración, observación) → list[CheckResult]` (`docs/roadmap/v0.7.md:68`) reusable, en vez
de lógica de comparación dispersa.

## Objetivo
Crear `tools/datacontracts/validation.py` (mismo paquete que Change 0) con `validate_contract(contract,
profile) -> list[CheckResult]`, una función pura que evalúa un `DataContract` YA construido contra
un `profile.json` YA cargado en memoria como `dict`, produciendo `dsguard.checks.CheckResult`
(`PASS`/`WARN`/`FAIL`/`N/A`, nunca `PASS` por falta de evidencia); y una puerta con I/O,
`validate_contract_against_profile_file(contract, profile_path, repo_root)`, que respeta el guard
de holdout existente antes de leer el archivo, sin construir un segundo profiler ni duplicar la
lógica de `holdout_guard`.

## Evidencia
- `docs/roadmap/v0.7.md:193-225` (Change 1 completo): alcance ("evaluar observaciones reales contra
  `DataContract`s, produciendo `CheckResult`"), checks candidatos (campo requerido ausente,
  inesperado, tipo incompatible, nullability, unicidad "solo cuando exista evidencia suficiente",
  rango/dominio "con min/max exactos del perfil", key/invariante "cuando sea determinista",
  evidencia faltante/stale), reglas (vocabulario `PASS/WARN/FAIL/N/A`, "nunca PASS por falta de
  información", degradación bajo `sampling.activo`, reuso del guard de holdout existente, sin
  segundo profiler).
- `docs/roadmap/v0.7.md:73-110` (decisiones 1-8, congeladas): decisión 2 ("`ds_profile` es el único
  observador de datos"; extensión aditiva solo si se decide en SDD, sin romper el schema del
  perfil); decisión 3 ("severidad declarada en el contrato, verificabilidad decidida por el
  binario"; no verificable → `WARN`/`N/A`, nunca `PASS`); decisión 4 (`technical_error` separado,
  no contamina el conteo de calidad); decisión 5 (quality no es gate — este Change no toca
  readiness/promotion).
- `docs/roadmap/v0.7.md:112-127`: dirección de dependencias — los paquetes de v0.7 pueden importar
  `dsguard.checks` y consumir `profile.json` como archivo; `dsguard`/`ds_profile`/`dsimpact`/
  `reporting`/`providers`/`routing`/`fallback`/`harmessi_bench` no importan los paquetes de v0.7.
- `tools/datacontracts/core.py:58,60-71,357-796`: `TYPE_FAMILIES`, `DATASET_ROLES`,
  `CONSTRAINT_TYPES` (10 tipos), `SEVERITIES = ("FAIL","WARN")`, `ContractField`
  (`name/type_family/required/nullable`), `Constraint` (`constraint_type/field/severity/params`),
  `DataContract` (`fields/constraints/keys`, accesores `get_field`/`constraints_for`/
  `get_constraint`) — el objeto exacto que este Change consume, sin modificarlo.
- `tools/datacontracts/core.py:79-96` (docstring del "Puente de `TYPE_FAMILIES`..."): tabla de mapeo
  `string→texto, integer→entero, float→flotante, boolean→booleano, date→fecha, datetime→fecha,
  unknown→sin mapeo (WARN/N/A)` — documentada como intención en Change 0, sin código; este Change
  la implementa en `validation.py`.
- `tools/ds_profile/report.py:151-170,191-232`: el loop de `generar_perfil` llama
  `acumuladores[nombre].observar(valor)` en TODAS las filas, sin importar `modo_muestreado`; el
  dict final de `profile.json` (`schema`, `columnas_detalle`, `calidad`, `sampling.activo`, `filas`,
  sin `dataset_path` reproducido en ningún resultado de este Change por privacidad).
- `tools/ds_profile/column_stats.py:163-196,243-306`: `AcumuladorColumna.observar` actualiza
  `min_numerico`/`max_numerico`/`min_fecha`/`max_fecha`/`nulos` en CADA fila observada (streaming
  completo, independiente de `modo_muestreado`); `construir_metricas_columna` usa esos acumulados
  (SIEMPRE exactos) para `min`/`max`/`fecha_min`/`fecha_max`/`nulls`, pero usa `valores_orden`
  (completo en modo exacto, MUESTRA en modo muestreado) para `unique.count`, `top_valores`,
  `mediana`/`cuantiles` (`exactitud_orden`/`unique.exactitud`/`exactitud_estadisticos` marcan cuál
  es cuál). Hallazgo clave de esta invocación, no asumido de memoria: `min`/`max`/`fecha_min`/
  `fecha_max`/`nulls` son exactos SIEMPRE (incluso con `sampling.activo=true`), mientras que
  `unique.count`/`top_valores`/`mediana`/`cuantiles` son aproximados bajo muestreo — el schema de
  `ds_profile` ya distingue ambos casos con su propio campo `exactitud`, sin necesidad de que este
  Change adivine nada.
- `tools/ds_profile/column_stats.py:105-127` (`clasificar_dtype`): las 5 familias de dtype
  (`texto/booleano/entero/flotante/fecha`), orden de clasificación fijo.
- `tools/ds_profile/holdout_guard.py:1-17,89-125`: único módulo de `ds_profile` (junto con
  `hook_rutas.py`/`pathguard.py`) pensado para reusarse; `verificar_permitido(ruta_input, repo_root)
  -> (bool, motivo)` ya implementa exactamente "no leer holdout sin excepción vigente" — la función
  concreta que el roadmap pide reusar ("se reutiliza el guard existente, no se replica",
  `docs/roadmap/v0.7.md:221-222`).
- `tools/dsguard/checks.py:14-22,25-56`: vocabulario `STATUS_PASS/WARN/FAIL/N_A`,
  `KIND_CHECK`/`KIND_TECHNICAL_ERROR`, `CheckResult(status, code, message, detail, subject, kind)` —
  el tipo de retorno exacto de `validate_contract`.
- `tools/reporting/validation.py:1-52,157-194,405-412,1045-1053`: patrón de referencia más cercano
  en todo el repo — función pura (`validate_report`) + puerta con I/O (`validate_report_dir`), helper
  `_res`/`_resumir` (PASS único si no hay violaciones, una entrada por violación si las hay), nunca
  lanza (try/except envolvente que convierte cualquier excepción en `FAIL`/`technical_error`).
- `ARCHITECTURE.md:132-140` (regla 7, ya escrita por Change 0): "en Changes posteriores (no en
  Change 0)... podrán importar `dsguard.checks`... y leer `profile.json` de `ds_profile` como
  archivo persistido (nunca importar `ds_profile` como librería para observar datos... salvo una
  extensión aditiva de `ds_profile` decidida explícitamente en SDD)" — la cláusula que este Change
  ejercita explícitamente para `ds_profile.holdout_guard` (ver `design.md`, decisión de diseño 2).
- `ARCHITECTURE.md:46-57` (filas de `tools/reporting/governance.py`/`evidence.py`/`validation.py`):
  precedente de que cada módulo nuevo de una familia recibe su propia fila en §2.1, no solo el
  primero.
- `tools/tests/test_v07_core_neutrality.py:1-46`: patrón `ast` exacto que Change 0 ya construyó
  para `core.py`; este Change necesita un escáner análogo, más permisivo, para `validation.py`.

## Supuestos descartados
- Que la evaluación deba recibir la RUTA de un `profile.json` y leerlo ella misma en la función
  "pura" principal. Descartado: separar `validate_contract(contract, profile: dict)` (pura, sin
  I/O) de `validate_contract_against_profile_file(contract, profile_path, repo_root)` (con I/O y
  guard) es el mismo patrón exacto de `tools/reporting/validation.py` (`validate_report` vs.
  `validate_report_dir`), y permite testear la lógica de evaluación con fixtures `dict` sin tocar
  filesystem ni guard en la mayoría de los tests.
- Que "evidencia stale" en este Change signifique comparar el `fingerprint` del perfil contra una
  recomputación en vivo del dataset. Descartado explícitamente (ver `design.md`, decisión 3):
  recomputar el fingerprint exigiría leer el dataset crudo de nuevo (no solo `profile.json`),
  duplicando al observador (`ds_profile`) de una forma que el roadmap reserva para Change 3
  (`quality-evidence-and-drift`, que sí tiene `generated_at`). "Stale" en este Change se acota a
  "perfil ausente, no legible o con forma inválida" — la frescura temporal contra el dataset vivo
  queda fuera de alcance, documentada como límite explícito, no como omisión silenciosa.
- Que `min_value`/`max_value`/`date_min`/`date_max` queden siempre "no verificable" bajo
  `sampling.activo=true`, por lectura literal de `docs/roadmap/v0.7.md:219` ("si sampling.activo es
  verdadero, las reglas que dependen de valores exactos no pasan"). Descartado tras leer el código
  real de `ds_profile` (evidencia arriba): `min`/`max`/`fecha_min`/`fecha_max`/`nulls` se acumulan
  sobre TODAS las filas, nunca solo sobre la muestra final — son exactos incluso bajo muestreo. Los
  campos que sí dependen de la muestra (`unique.count`, `top_valores`, `mediana`, `cuantiles`) ya
  vienen marcados por `ds_profile` con su propio campo `exactitud`/`exactitud_estadisticos`. Este
  Change usa esas marcas del propio perfil para decidir verificabilidad campo por campo, en vez de
  una regla global "si sampling.activo, todo es no verificable" que sería más conservadora de lo
  que la evidencia real permite y contradiría "check everything" sin necesidad.
- Que `min_length`/`max_length` sean verificables de alguna forma con el perfil actual.
  Descartado: `ds_profile` no calcula ninguna estadística de longitud de texto
  (`tools/ds_profile/column_stats.py:243-306` no tiene ningún campo `length`/`longitud`); este
  Change los deja siempre `WARN` "no verificable con la evidencia actual" y documenta la posible
  extensión aditiva de `ds_profile` sin implementarla (ver `design.md`, "Extensión aditiva
  evaluada y no tomada").
- Que este Change deba importar `ds_profile` como paquete completo (p. ej. `ds_profile.report`,
  `ds_profile.column_stats`) para poder construir o interpretar el perfil. Descartado: la única
  necesidad real de `ds_profile` es reusar `holdout_guard.verificar_permitido` (una función de
  permiso de lectura, no de observación de datos); `profile.json` se interpreta con `json.loads`
  puro, sin ningún import de `ds_profile.report`/`column_stats`/`fingerprint`/`sampling`/
  `quality_flags`/`schema`/`io_readers` (ver `design.md`, decisión de diseño 2, marcada como punto a
  confirmar por el Lead).
- Que "campo inesperado" deba tener severidad `FAIL` para roles de dataset "estrictos" (p. ej.
  `raw_table`) y `WARN` para otros. Descartado por ahora: `DataContract` no declara ningún campo
  `allow_extra_fields` (confirmado leyendo `tools/datacontracts/core.py` completo — no existe);
  inventar una política diferenciada por `dataset_role` sería una decisión metodológica no pedida
  por el roadmap ni congelada en ninguna decisión de diseño; se adopta una política uniforme (`WARN`
  siempre, nunca `FAIL`) documentada como punto a confirmar por el Lead (ver `design.md`).

## Hipótesis (condicional — solo cambios metodológicos)
No aplica.

## Alcance
- `tools/datacontracts/validation.py` (nuevo): códigos `CONTRACT-*`, `validate_contract(contract,
  profile) -> list[CheckResult]` (pura), `validate_contract_against_profile_file(contract,
  profile_path, repo_root) -> list[CheckResult]` (con guard de holdout e I/O), bridge
  `type_family → dtype` de `ds_profile`, todas las reglas de checks candidatos del roadmap Change 1
  cubiertas por evidencia real o marcadas `WARN`/`N/A` explícitamente.
- `tools/datacontracts/tests/test_validation.py` (nuevo): fixtures 100% sintéticas de
  `DataContract` + `profile.json` en memoria (nunca datasets reales), cubriendo cada código y cada
  combinación relevante de `sampling.activo`/`exactitud`.
- `tools/tests/test_v07_validation_neutrality.py` (nuevo): patrón `ast` análogo a
  `test_v07_core_neutrality.py`, específico de `validation.py` (imports permitidos: stdlib +
  `dsguard.checks` + `ds_profile.holdout_guard` (solo ese módulo) + `tools.datacontracts.core`;
  prohibidos: pandas, numpy, `ds_profile.report`/`column_stats`/`fingerprint`/`sampling`/
  `quality_flags`/`schema`/`io_readers`, cualquier otro paquete de `tools`).
- `tools/tests/test_architecture_boundaries.py`: agregar `tools/datacontracts/validation.py` a
  `MODULOS_CORE`.
- `ARCHITECTURE.md`: fila nueva en §2.1 para `tools/datacontracts/validation.py`; ampliar el texto
  de la regla 7 en §3 para documentar el ejercicio concreto de la cláusula de extensión aditiva
  (import narrow de `ds_profile.holdout_guard`, ver `design.md` para el texto exacto).
- `docs/roadmap/v0.7.md`: al cerrar el Change, tildar `[x] Change 1`.
- `openspec/changes/20260922-data-contract-validation/verification.md` (al cierre, última
  invocación).

Ver `tasks.md` para el desglose exacto de rutas por invocación.

## Fuera de alcance
- Cualquier modificación a `tools/datacontracts/core.py` (inmutable salvo bug real de Change 0; si
  se encuentra uno, se señala al Lead, no se edita en este Change).
- Recomputar el `fingerprint` del dataset vivo para detectar staleness temporal, y cualquier campo
  `generated_at`/hash de evidencia persistida: Change 3 (`quality-evidence-and-drift`).
- `ModelQualityPolicy`/`MetricRequirement`/`ObservedMetric`/`BaselineReference`: Change 2
  (`model-quality-policies`).
- CLI (`harmessi contract ...`), clasificación de compatibilidad entre versiones de contrato,
  impact preflight de contratos: Change 4 (`quality-integration-and-cli`).
- Cualquier extensión real de `ds_profile` para calcular longitud de texto, unicidad compuesta
  exacta bajo muestreo, o cualquier otra estadística nueva: evaluada y explícitamente NO tomada en
  este Change (ver `design.md`, "Extensión aditiva evaluada y no tomada" — no es una omisión, es
  una decisión).
- Cualquier cambio a `dsguard`, `ds_profile`, `dsimpact`, `reporting`, `providers`, `routing`,
  `fallback`, `harmessi_bench` salvo la lectura ya autorizada por la regla 7 de `ARCHITECTURE.md`.
- Modificar readiness, promotion gates, exit code de `status`/`project readiness`/`project promote`,
  ni lifecycle (decisión 5 del roadmap): este Change no produce ningún side-effect sobre esas
  superficies, solo `list[CheckResult]` en memoria.
- Leer, escribir o inferir sobre cualquier dataset real: todos los fixtures de test son
  sintéticos, y `validate_contract` recibe siempre un `dict` de perfil ya cargado (nunca abre un
  dataset).

## Holdout policy (condicional — solo cambios "sensible")
Aplica de forma directa (a diferencia de Change 0): este Change SÍ lee evidencia persistida
(`profile.json`) desde disco, en `validate_contract_against_profile_file`. Se reusa
`ds_profile.holdout_guard.verificar_permitido(profile_path, repo_root)` (`tools/ds_profile/
holdout_guard.py:89-125`) ANTES de abrir el archivo — mismo criterio que `tools/reporting/
validation.py:924-930` para fuentes (`REPORT-SOURCE-UNVERIFIABLE`): una ruta denegada nunca se abre,
nunca es `PASS` ni "stale", es `FAIL`/`technical_error` (`CONTRACT-EVIDENCE-MISSING`). Distinción
importante documentada en `design.md`: `holdout_guard.verificar_permitido` evalúa la ruta del
`profile.json` YA GENERADO (un artefacto derivado en `.harmessi/profiles/`, normalmente fuera de
cualquier holdout declarado), no la ruta del dataset crudo que `ds_profile run` leyó para generarlo
— ese guard ya se aplicó una vez, en el momento en que se corrió `ds_profile run` sobre el dataset
(fuera del alcance de este Change). Aun así, se evalúa el guard sobre la ruta del `profile.json`
mismo por dos razones: (1) nada impide que un perfil se guarde dentro de un directorio declarado
holdout por error o por diseño (p. ej. un perfil de un dataset de evaluación final), y (2) es
exactamente lo que pide el roadmap ("no leer holdout si la scientific/governance policy lo prohíbe:
se reutiliza el guard existente, no se replica", `docs/roadmap/v0.7.md:221-222`) sin condicionarlo a
qué tipo de archivo es. No se toca en ningún momento el dataset original ni ningún otro archivo bajo
el guard salvo el propio `profile.json`.

## Impacto en production-readiness (opcional)
No aplica: decisión 5 del roadmap (`docs/roadmap/v0.7.md:96-101`) fija que ningún resultado de v0.7
modifica readiness, promotion gates ni lifecycle; este Change produce únicamente `list[CheckResult]`
en memoria, sin ningún efecto sobre `status`/`project readiness`/`project promote`.

## Criterios de aceptación (spec-lite — solo SDD abreviado)
Ver `spec.md` (SDD completo).

## Decisión técnica (design-lite — solo SDD abreviado)
Ver `design.md` (SDD completo).

## Aprobación
- Usuario: Federico Colombo
- Fecha: 2026-09-22
- Alcance aprobado: "Change 1 — data-contract-validation (docs/roadmap/v0.7.md)"
- Versión de artefactos referenciada: esta versión de los 4 archivos (commit de este Change)
- Cita: "Ejecutá autónomamente los Changes de docs/roadmap/v0.7.md ... Change 1 —
  data-contract-validation ... audit acotado → SDD → validación contra roadmap/arquitectura →
  implementación → tests → reviewer → fixes → re-tests → verification → cierre → commit local
  (instrucción explícita del usuario, 2026-09-22, bajo el Contrato de autonomía de
  `docs/roadmap/README.md`)."

## Motivo de rechazo
No aplica.

## Desacuerdo registrado
No aplica.

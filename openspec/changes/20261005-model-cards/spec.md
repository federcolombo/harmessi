# Spec — 20261005-model-cards

Notación: cada `Rn` tiene criterio de aceptación verificable. Hallazgos/errores con códigos `MODELCARD-*`
(tupla `MODELCARD_CODES` propia de `modelcard.py`); la Foundation y Data Cards no se reabren
históricamente (solo extensiones aditivas, R3–R5).

## Requisitos

### A. Paquete y dependencias (R1–R5)
**R1** `modelcard.py` vive en `tools/cards/`, solo stdlib, importa solo `core`/`assess` (y `resolvers`
perezoso) del mismo paquete; ni `modelquality`, `qualityevidence`, `datasources`, `datacontracts`,
`autonomy`, `leadrun`, `reporting`, `ds_init` desde código de producción (regla 13). Los tests sí
construyen objetos reales de esos paquetes. Se actualizan las tablas de hermanos permitidos de
`test_v09_cards_neutrality.py`/`test_v09_datacards_inert.py` (cambio mínimo y estricto).
**R2** Sin cambios en `ds_guard.py`, `ds_init/*` (incl. `MANIFEST`, `CAPABILITIES_CONOCIDAS`,
`EXCLUSIONES_PERMANENTES`), Doctor, `autonomy`, `STOP_CATALOG`, `leadrun`, `modelquality`,
`qualityevidence`, `datacontracts`, `datasources`, `reporting`.
**R3 — Extensión aditiva de vocabulario (foundation-level):** `core.OBSERVED_KINDS` gana al final
`data_card`, `model_quality_result`, `model_quality_policy` (13 kinds). Justificación: son artefactos de
Harmessi ya existentes que cualquier Card posterior puede citar; no son específicos de ModelCard. Las
Cards ya serializadas siguen siendo válidas.
**R4** `resolvers.default_resolvers` pasa a resolver además `data_card`, `model_quality_result`,
`model_quality_policy`, `observed_metric`, `baseline_reference`, `drift_evidence`, `execution_record`
(12 kinds; `report_artifact` sigue sin resolver → `unverifiable`). Los tests de Change 0/1 que fijaban
«10 kinds», «5 resolvers» y «el resto unverifiable» se actualizan de forma mínima.
**R5** Todas las pruebas de Changes 0–1 pasan, salvo los ajustes mínimos de R1 y R4 (documentados en
verification.md).

### B. Identidad (R6–R10)
**R6 — Una Model Card documenta UNA versión.** Envelope: `card_kind="model_card"`,
`kind_schema_version=1`. `subject == model_id`.
**R7 — Identificadores (precisión 1 del autor).** `model_id`: `[a-z0-9]+([_-][a-z0-9]+)*` (sin `__`).
`model_version`: `[a-z0-9]+([.-][a-z0-9]+)*` — versión lógica propia del proyecto, NO se asume SemVer;
lowercase file-safe; `_` NO es válido en la fuente (reservado para la codificación de `.`); sin separadores
consecutivos. Rechazar rutas, `\`, DSN. **Longitud:** no hay límite arbitrario por campo; el único límite
real es el de la Foundation sobre `card_id` (`CARD_ID_PATTERN`, ≤ 64):
`len(model_id) + 2 + len(model_version) ≤ 64` (violación → `MODELCARD-IDENTITY-INVALID`, con mensaje que
indica el presupuesto). Ampliar ese límite reabriría Change 0 y no se hace.
**R8 — `card_id` derivado, obligatorio y reversible:** `card_id == model_card_id(model_id, model_version)` =
`model_id + "__" + model_version.replace(".", "_")`. La codificación es reversible sin hashing: `model_id` no
contiene `__`, la versión codificada no contiene `__` (no hay separadores consecutivos) y solo contiene `_`
donde la fuente tenía `.`; por tanto `card_id` se parte de forma única en el único `__` y
`decode(card_id)` recupera `(model_id, model_version)` (propiedad testeada con una tabla y generación
exhaustiva de combinaciones cortas). Violación → `MODELCARD-IDENTITY-MISMATCH`. Una nueva versión del modelo ⇒ `card_id` distinto ⇒ Card distinta; no puede
escribirse sobre la Card de otra versión (ver R30).
**R9 — Revisión.** `revision_id()` (`card_id__hash12`) = revisión del documento (corregir/ampliar la
documentación de la MISMA versión). Es independiente de `model_version` y de los pins de evidencia.
**R10** No existe registry ni índice de modelos: no hay función que liste modelos ni versiones.

### C. Body (R11–R17)
Claves cerradas (desconocida → `MODELCARD-UNKNOWN-KEY`, salvo `x_*`, validadas recursivamente contra
rutas/DSN/credenciales).
**R11 — Obligatorios:** `model_id`, `model_version`, `description` (str no vacío). Nada más es obligatorio.
**R12 — Opcionales descriptivos:** `task` `{role, description?, target_reference?, output_meaning?}` con
`role` identificador libre (`[a-z][a-z0-9_]*`; sugeridos los de `modelquality.MODEL_TASK_ROLES`; SIN enum
ni acoplamiento a sklearn); `population`, `intended_uses[]`, `out_of_scope_uses[]`, `known_limitations[]`,
`stewardship {owner, steward?}` (roles/equipos, sin '@' ni contacto personal).
**R13 — `data_card_refs[]`:** `{data_card_ref_id, role, evidence_id}`; `role` identificador libre
(convención sugerida: training, validation, test, calibration, inference_reference; sin enum);
`evidence_id` → EvidenceRef de la Card con `kind="data_card"`. No se copian fuentes, esquemas, poblaciones
ni `contract_refs` de la Data Card.
**R14 — `evaluation_refs[]`** (referencias a evidencia de v0.7): `{evaluation_ref_id, role?,
result_evidence_id?, policy_evidence_id?, metric_evidence_ids[], baseline_evidence_ids[],
drift_evidence_ids[]}` con kinds `model_quality_result`, `model_quality_policy`, `observed_metric`,
`baseline_reference`, `drift_evidence`. Al menos un pin por referencia. Ninguna métrica se copia ni
calcula; el contexto de evaluación es el que lleva la `ObservedMetric` pineada.
**R15 — `provenance_refs[]`:** `{provenance_ref_id, role?, evidence_id}` → EvidenceRef `execution_record` o
`report_artifact` (artefacto/ejecución que produjo o describe el modelo). Technology-neutral: no hay campo
de ruta de modelo, ni formato (`.pkl`, ONNX, MLflow, URIs). Opcional.
**R16 — Consistencia de pins:** todo `evidence_id` citado existe en `card.evidence` con el kind esperado
(`MODELCARD-DANGLING-EVIDENCE`/`MODELCARD-REF-INCONSISTENT`). Para `data_card`: `ref_id ==
<card_id>__<12 hex>` y hash12 == `content_sha256[:12]` del pin; si hay `locator`, debe ser
`governance/cards/data/<card_id>.json`. Para `model_quality_result`: `ref_id` con patrón de `evidence_id`
(`qe-…`). Para `drift_evidence`: patrón `dr-…`. Ids locales únicos.
**R17 — Sin RAI.** No existen campos `risk_level`, fairness, explainability, privacy, security,
accountability ni human oversight; presencia → `MODELCARD-UNKNOWN-KEY` (el espacio lo cubre `x_*` y
Change 3).

### D. Evidencia y atestaciones (R18–R22)
**R18** Afirmaciones empíricas ⇒ `EvidenceRef` real; humanas/proceso ⇒ `HumanAttestation` (`declared`/
`anchored` estructural, sin verificación contra ledger); texto libre del body ⇒ contexto, no evidencia.
**R19 — Requisitos derivados (no persistidos)** por `requirements_for(card)`: por CADA pin citado desde el
body, `evidence_<evidence_id>` (`required`, `accepts=("observed",)`, `accepted_kinds=(kind del pin,)`;
≤ 64 chars → `evidence_id` ≤ 55); y `ownership` (`recommended`, `accepts=("attestation",)`,
`min_attestation_kind="declared"`). Los pins de `provenance_refs` son `recommended`. «Declarar implica
respaldar»: lo que la Card cita debe estar soportado por su claim; qué evidencia debe EXISTIR queda para
Change 3.
**R20 — Consistencia de claims:** un claim cuyo `requirement_id` sea `evidence_<eid>` debe tener
`supports == (eid,)` (exactamente su propio pin; sin enmascarar el stale con otro) y `eid` debe ser un pin
citado; `ownership` se apoya solo en atestaciones; otra forma → `MODELCARD-CLAIM-SUPPORT-INCONSISTENT`.
**R21 — Una atestación nunca satisface** un requisito `evidence_*` (métrica, evaluación, baseline, drift,
Data Card, política): test explícito por kind.
**R22 — Ninguna conclusión semántica:** ni `requirements_for` ni la evaluación comparan valores de
métricas, umbrales ni producen «bueno/malo»; la salida solo informa estados de evidencia/requisito/Card.

### E. Resolvers (R23–R31) — en `resolvers.py`; devuelven `Resolution`, nunca lanzan (error → `unverifiable`)
**R23 — `data_card` (precisión 2 del autor):** `ref_id=<card_id>__<hash12>`; lee
`governance/cards/data/<card_id>.json` con `assess.read_card` (valida estructura y `revision_id`), exige
`card_kind=="data_card"` y `card_id` coincidente; `current_sha256 = card.content_sha256()`. El pin valida
exactamente cuatro cosas: **identidad, existencia, integridad/hash y revisión pineada**. NO hereda el estado
de governance de la Data Card: una Data Card estructuralmente válida pero `incomplete` con pin íntegro ⇒ el
`data_card_ref` queda resuelto (`fresh`). Exigir que la Data Card esté `complete` o tenga cierto nivel de
evidencia es Change 3. El resolver no invoca `evaluate`/`evaluate_data_card` ni resuelve recursivamente la
evidencia de la Data Card (sin cascadas). Ausente → `missing`.
**R24 — `model_quality_result`:** como `data_contract_result` pero exige `subject_kind ==
"model_quality_evaluation"` (integridad del hash persistido del manifest verificada).
**R25 — `model_quality_policy`:** `ref_id=<policy_id>`; `locator` relativo portable a un JSON de política;
`policy_id` interno == `ref_id`; hash = `hash_contract`-equivalente (canonical sha256 del dict).
**R26 — `observed_metric` / `baseline_reference` (precisión 3 del autor):** el pin cubre el DOCUMENTO
completo (`locator` a un JSON-lista, formato que consume `ds_guard quality evaluate`; `content_sha256` = hash
canónico del documento entero) y `member` es un **selector semántico y determinista** de la entrada dentro de
él: nunca índice, posición ni «primer match». Identidad real auditada en v0.7: `ObservedMetric` no tiene id y
`modelquality.validation` la identifica por `metric_name` + `context.context_id` (duplicados ⇒
`QUALITY-METRIC-AMBIGUOUS`); `BaselineReference` tiene `baseline_id`. Sintaxis canónica de `member`:
`<metric_name>@<context_id>` para métricas y `<baseline_id>` para baselines (`@` no puede aparecer en
`metric_name` ni `context_id`; la heurística de portabilidad solo rechaza `@` precedido de `:`). El resolver
exige que el documento sea una lista y: 0 coincidencias ⇒ `missing`; >1 coincidencia ⇒ `unverifiable`
(fail-closed, nunca se elige una); entrada con identidad malformada ⇒ `unverifiable`. Al cubrir el documento
completo, cambiar CUALQUIER entrada del archivo vuelve `stale` los pins sobre ese archivo (conservador,
documentado). `current_sha256` es el hash del documento, solo si el `member` resuelve a exactamente una
entrada.
**R27 — `drift_evidence`:** `locator` a un JSON guardado por el usuario (`DriftEvidence.to_dict`);
`drift_id` interno == `ref_id`; hash = canonical sha256 sin `generated_at`.
**R28 — `execution_record`:** `ref_id=<command_form>__<hash12>`;
`.harmessi/executions/<id>/record.json`; hash = canonical sha256 del dict sin `generated_at`.
**R29 — Staleness conservadora (sin «latest»):** cada resolver resuelve EXACTAMENTE el artefacto pineado
(por id inmutable o por locator/member) y compara su hash con el pin: archivo cambiado ⇒ `stale`;
ausente ⇒ `missing`; integridad rota ⇒ `unverifiable`. Ninguna Card se declara stale por existir otra
evidencia más nueva. Una Data Card citada que fue revisada ⇒ el pin `data_card` queda `stale` (hay que
reemitir la Model Card); la completitud de la Data Card no se hereda.
**R30 — Sin persistencia nueva:** los resolvers solo leen bajo `repo_root` (mismas garantías de Change 1:
rutas contenidas, tamaño acotado, sin NaN, sin symlinks que escapen).
**R31** El hash del documento es sobre el JSON canónico tal como está en el archivo (limitación
documentada: un archivo escrito a mano con defaults omitidos hashea distinto que su forma normalizada).
`hash_document(obj)` es público; la entrada seleccionada solo se usa para verificar existencia/unicidad.

### F. Ubicación y escritura (R32–R36)
**R32** `governance/cards/model/<card_id>.json`, relativa a la raíz del proyecto; project-owned, fuera de
`.harmessi/` y del manifest; sin `HARMESSI-DRIFT`. `card_path(project_root, card_id)` valida id y
contención.
**R33** `write_model_card(project_root, card, *, replace=False, clock=None)`: valida antes de tocar el
disco; `replace=False` → `exclusive` (sin overwrite); `replace=True` exige archivo existente de la MISMA
identidad (`card_id`, `model_id`, `model_version`, `card_kind`); otra versión/identidad →
`MODELCARD-IDENTITY-MISMATCH`; archivo ajeno → error sin sobrescribir.
**R34** No se crea `governance/` al importar ni al validar; solo `write_model_card` crea directorios.
**R35** `evaluate_model_card(card_or_path, repo_root, clock=None)` = `evaluate`/lectura con
`requirements_for`, `body_validator_for` y `default_resolvers`; archivo mal formado ⇒ `invalid` sin
excepción cruda.
**R36** Serialización determinista de la Foundation; sin `status` persistido; round-trip→evaluate
idéntico.

### G. Inercia y compatibilidad (R37–R39)
**R37** Sin Model Cards no cambia nada; suites de v0.6–v0.8, Change 0, Change 1 verdes (salvo R5).
**R38** Tests de inercia: `STOP_CATALOG` intacto; `MANIFEST` sin `cards`/`governance`;
`CAPABILITIES_CONOCIDAS == ("predictive_modeling",)`; `model_governance`/`data_cards`/`modelcard` ausentes
de `ds_init`, `autonomy`, `harmessi`, `ds_guard`.
**R39** `anchored` sigue siendo estructural; ningún mensaje afirma verificación.

## Criterios de aceptación (Given/When/Then)
- Given `model_version` `"1.2.0"`, `"1-2-0"` y `"1.2"` → `card_id` distintos y `decode(card_id)` recupera
  cada par; given una versión con `_`, mayúsculas o `..` → inválida; given un par que excede 64 en total →
  `MODELCARD-IDENTITY-INVALID` con el presupuesto.
- Given una Data Card `incomplete` pero íntegra y pineada → `data_card_ref` fresh; given la misma Data Card
  editada → pin stale; el resolver no reevalúa la Data Card.
- Given dos entradas de métrica con el mismo `metric_name@context_id` → pin `unverifiable`; member
  inexistente → `missing`; el `member` se resuelve por identidad y no por posición.
- Given una Model Card mínima (`model_id`, `model_version`, `description`, `card_id` derivado) sin
  evidencia ni claims → válida estructuralmente pero `incomplete` (plantilla vacía ≠ evidencia).
- Given `card_id` ≠ derivado de `model_id`+`model_version` → inválida; given `model_version` nueva →
  `card_id` nuevo y `replace` sobre la Card anterior falla.
- Given dos `data_card_refs` con roles `training` y `test` pineando Data Cards reales → ambos `fresh`;
  Data Card editada → pin `stale` ⇒ Model Card `stale`.
- Given manifest real `model_quality_evaluation`, política real y métrica/baseline reales pineados con
  claims propios → `complete`; métrica alterada → `stale`; manifest ausente → `incomplete`.
- Given requisito `evidence_*` y solo una atestación → `untrusted_type`/inválido por R20.
- Given `task.role="forecasting"`/«custom_role» → válido (sin enum).
- Given clave `risk_level` en el body → inválido.
- Given Card en `governance/cards/model/` y Doctor real → sin drift; archivo existente → sin overwrite.
- Given ruta absoluta/DSN/`\` en cualquier string → rechazo.

## Unidad de análisis / grain (condicional)
No aplica (la Card transporta `population`/`target_reference` solo como descripción).

## Cutoff / information boundary (condicional)
No aplica: no se calculan métricas ni features; los resolvers solo leen evidencia indicada, nunca datos de
proyecto ni holdouts.

## Baseline (condicional)
No aplica: las baselines se citan por pin, no se definen ni comparan aquí.

## Métrica primaria (condicional)
No aplica.

## Métricas secundarias (opcional)
No aplica.

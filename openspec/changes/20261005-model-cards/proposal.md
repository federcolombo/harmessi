# Propuesta — 20261005-model-cards

> Change 2 de v0.9 (`docs/roadmap/v0.9.md`). Construido sobre `tools/cards` (Change 0, `f5c3638`) y
> mirrorea Change 1 (Data Cards, `4ee222c`). No implementa riesgo/RAI (Change 3) ni CLI/Doctor/
> rendering/installer/capabilities (Change 4).

## Problema
Hay Foundation y Data Cards, pero nada describe de forma gobernada **una versión concreta de un modelo** ni
la ata a la evidencia real que ya existe en v0.7 (calidad, políticas, métricas observadas, baselines,
drift) y a las Data Cards que lo alimentan. Además, el audit muestra tres huecos que condicionan el
diseño:
- **No existe identidad de modelo en Harmessi** (`model_id`, `model_version`, artefacto: *not found*).
- **v0.7 no persiste** `ObservedMetric`, `BaselineReference`, `EvaluationContext` ni la política: viven en
  archivos JSON del proyecto sin ruta convencional; el manifest de `qualityevidence` solo guarda
  `CheckResult`s, el hash de la política (`declaration.content_sha256`) y el sha256 del archivo de métricas.
  El drift no se persiste en absoluto.
- **No hay semántica de «última evidencia»**: los manifests son directorios inmutables, las políticas no
  tienen versión y no existe supersession.

## Objetivo
Definir y probar la **Model Card**: vista de governance estructurada y respaldada por evidencia sobre UNA
versión de modelo, que referencia (por pin) evidencia de v0.7 y Data Cards de Change 1, con identidad
formalizada (`model_id` + `model_version` ⇒ Card distinta por versión), ubicación project-owned y
semántica de staleness conservadora (pin/integridad, sin «latest»). Sin calcular métricas, sin registry,
sin entrenar, sin RAI.

## Evidencia
Audit read-only del 2026-10-05:
- `tools/modelquality/core.py:301,347,480,560,618,721`: `EvaluationContext`, `MetricRequirement`,
  `ObservedMetric` (sin id: se identifica por `metric_name` + `context.context_id`), `BaselineReference`
  (`baseline_id`), `ModelQualityPolicy` (solo la política tiene `content_sha256()`; sin campo `version`);
  `MODEL_TASK_ROLES = classification, regression, ranking, clustering, forecasting, generic` (`:51`);
  `validation.py:449` `evaluate_policy` pura. CLI `ds_guard quality evaluate --policy --metrics
  [--baselines] [--record-evidence]` (`ds_guard.py:2991`) lee JSON arbitrario.
- `tools/qualityevidence/core.py:55,359,435,507,545` y `evidence.py:82,293-340,549`:
  `SUBJECT_KINDS = (data_contract_evaluation, model_quality_evaluation)`, manifest en
  `.harmessi/quality/<evidence_id>/manifest.json`, `DriftEvidence` (`dr-…`, sin persistencia).
- `tools/cards/core.py:45-56` (`OBSERVED_KINDS`, 10 kinds), `resolvers.py:327,370` (`quality_evidence` ya
  resuelve manifests de cualquier `subject_kind`; solo 5 kinds resolubles), `datacard.py` (patrón
  mirror: body cerrado, `_validar_claims`, `card_path`, `write_data_card`).
- `tools/leadrun/core.py:361` `ExecutionRecord` (`outputs_hash` siempre `None`); `reporting/evidence.py:458`
  manifests con `artifacts[].sha256`.
- `dsguard/maturity.py:20` `RISK_LEVELS` es madurez de proyecto: Change 2 no lo toca.

## Supuestos descartados
- «Hay identidad/artefacto de modelo reutilizable»: no; no se construye registry.
- «La política de calidad se cita como contrato»: `harmessi_contract` exige `<id>@<semver>` y la política
  no tiene versión ni `contract_id`: necesita su propio kind.
- «Las métricas están en el manifest»: no; sólo el hash del archivo de métricas.
- «Hay una evidencia más reciente que reemplaza a otra»: no existe tal semántica; se evita el patrón
  historical-stale de Data Cards.

## Alcance
- `tools/cards/modelcard.py`: contrato del cuerpo (`kind_schema_version=1`), identidad
  (`model_card_id`), validador, `requirements_for`, `card_path`, `write_model_card`, `evaluate_model_card`.
- Extensión aditiva de la Foundation y de los resolvers: tres kinds nuevos en `OBSERVED_KINDS`
  (`data_card`, `model_quality_result`, `model_quality_policy`) y resolvers para ellos y para los kinds ya
  declarados pero sin resolver que Model Cards necesita (`observed_metric`, `baseline_reference`,
  `drift_evidence`, `execution_record`).
- Ubicación `governance/cards/model/<card_id>.json`.
- Tests con objetos reales de v0.7/v0.8/Change 1; docs mínimas (ARCHITECTURE, roadmap).

## Fuera de alcance
- `risk_level`, fairness, explainability, privacy, security, accountability, human oversight, gating
  (Change 3); policy de requisitos por riesgo.
- `cards validate`, Doctor, rendering HTML, installer/manifest, capabilities `data_cards`/
  `model_governance` y su validación (Change 4); resolución real de `ApprovalRef`.
- Calcular o interpretar métricas; derivar conclusiones («el modelo es bueno»); registry de modelos;
  carga/hash de binarios de modelo; lineage; domain-modeling.
- Persistir métricas/baselines/drift en `.harmessi/` o cambiar `modelquality`/`qualityevidence`.
- Corregir limitaciones de Data Cards (historical-stale, A→B→A, `.harmessi/` tras clon, semver,
  `quality_evidence_ids`): solo se evita repetir sus patrones.
- Autonomy, `STOP_CATALOG`, runtime, `ds_guard`, Doctor.

## Principios aplicados
Model Card references evidence; it does not generate it. Cards are evidence-backed views. Empty template
!= evidence. Narrativa ≠ evidencia. Una atestación humana nunca satisface un requisito empírico. Una Card
«completa» no significa que el modelo sea bueno ni esté gobernado: sólo que lo que declara está respaldado.

## Deudas preservadas
Change 4: resolución real de `anchored` (ApprovalRef), integración de capabilities, `governance/` con
Doctor/ownership, combinaciones inválidas de config (`model_governance` sin `predictive_modeling`).
v0.10: approval-origin authenticity, LF/CRLF hashing, authorized-scope UX, composable skills/
domain-modeling, one-writer concurrency semantics (registrada).

## Criterios de cierre
Ver spec.md: Model Card mínima y rica evaluables con resolvers reales sobre objetos reales; identidad
por versión; Data Card refs pineadas; evidencia v0.7 pineada; stale/missing/mismatch fail-closed;
inercia fuera de `tools/cards`; regresión relevante verde.

## Impacto en production-readiness (opcional)
Aditivo e inerte: sin Model Cards el comportamiento de Harmessi es idéntico.

## Aprobación
- Usuario:
- Fecha:
- Alcance aprobado:
- Versión de artefactos referenciada:
- Cita o descripción fiel de qué se aprobó:

## Motivo de rechazo

## Desacuerdo registrado

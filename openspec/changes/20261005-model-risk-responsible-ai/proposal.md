# Propuesta — 20261005-model-risk-responsible-ai

> Change 3 de v0.9 (`docs/roadmap/v0.9.md`). Construido sobre Changes 0–2 (`f5c3638`, `4ee222c`,
> `fcb0068`). Define el contrato PURO de policy y evaluación de governance de modelo; Change 4 lo cablea
> (CLI, Doctor, rendering, config, capabilities, resolución real de `ApprovalRef`).

## Problema
Existen Model Cards (documentan UNA versión de modelo y citan evidencia), pero nada gobierna qué
evidencia de governance de riesgo / Responsible AI debe existir para ese modelo, en función de un
`risk_level`, ni cómo evaluarlo sin que Harmessi calcule o infiera nada científico/ético. Reglas ya
congeladas: Harmessi GOBIERNA evidencia, no la genera; `HumanAttestation` no sustituye evidencia
empírica; el status es derivado; capas inferiores solo endurecen; D1 (sin STOP ni gating de autonomía);
D5 (la policy no vive en `guardrails.json`); la taxonomía `low/medium/high`.

El audit (2026-10-05) agrega restricciones de diseño:
- `ModelCard` v1 rechaza explícitamente `risk_level` y las claves RAI (`test_modelcard.py`): el riesgo no
  puede vivir en el body de la Model Card.
- `assess` satisface un requisito con CUALQUIER soporte fresco: la regla «lo citado debe estar fresco»
  exige un evaluador propio (no hay desglose público por claim).
- No existe hoy un kind resoluble para evidencia documental externa (`report_artifact` queda siempre
  `unverifiable`): sin una primitiva de «documento fijado por hash» ninguna dimensión RAI podría respaldarse
  con observación.
- `CARD_KINDS` y `OBSERVED_KINDS` están fijados por tests de conteo (ajuste mínimo, como en Change 2).
- No existe un helper genérico de «merge monotónico»; el precedente (`resolver_modo_efectivo`,
  `parse_autonomy_policy`) solo opera sobre vocabularios cerrados de una dimensión.
- `dsguard.maturity.RISK_LEVELS = (low, medium, high)` es madurez de proyecto: no se toca ni se lee.

## Objetivo
Definir y probar, en `tools/cards/`, un artefacto separado **ModelGovernanceAssessment** (envelope
`governance_assessment`) que evalúa una Model Card concreta contra una **policy pineada y versionada**:
base mínima de Harmessi por `risk_level` + endurecimiento de proyecto (monotónico, fail-closed), con seis
dimensiones (fairness, explainability, privacy, security, accountability, human_oversight) estructuradas,
respaldadas por evidencia y atestaciones, y con completitud DERIVADA. Sin calcular fairness ni nada
equivalente, sin inferir «fair/safe/ethical», sin compliance, sin tocar autonomía.

## Evidencia
Audit read-only del 2026-10-05: `tools/cards/core.py:43,45-59,800` (`CARD_KINDS`, `OBSERVED_KINDS`,
validación del kind); `assess.py:255-300` (`_evaluar_requisito`: ANY-fresh), `_estado_card`, `CardAssessment`;
`modelcard.py:84-95,544,668-714,730-859` y `datacard.py` (helpers a espejar); `resolvers.py:435,477,607`
(`data_card_resolver`, `model_quality_policy_resolver`, `default_resolvers` con 12 kinds); precedentes de
capas: `ds_guard.py:575-640`, `autonomy/policy.py:152-323`; `dsguard/maturity.py:20,190`;
`test_modelcard.py:1347-1360` (claves RAI rechazadas); tests de conteo y tablas de hermanos/inercia:
`test_core.py:180`, `test_evidence.py:52`, `test_v09_modelcards_inert.py:82-93,246-259`,
`test_v09_cards_neutrality.py:261-265`, `test_modelcard.py:1603-1608`.

## Supuestos descartados
- «El riesgo puede ser un campo del body de la Model Card»: contradice el contrato congelado de ModelCard
  v1 y mezclaría documentación de una versión con una evaluación reemitible.
- «Un `Requirement` estático alcanza»: la exigencia depende del `risk_level` y de capas de policy.
- «`report_artifact` sirve para evidencia documental»: no tiene resolver; haría imposible satisfacer nada.
- «Se puede inferir el nivel de riesgo»: prohibido; es una declaración humana/proyecto.
- «El estado de la Model Card se hereda»: el pin solo valida identidad/integridad (como en Change 2).

## Alcance
- `tools/cards/govpolicy.py`: tipos de policy (niveles, dimensiones, requisitos por nivel), policy base v1
  (constante de código con id/versión/hash), merge monotónico con endurecimiento de proyecto, orden de
  fuerza y validación fail-closed.
- `tools/cards/modelgov.py`: body de `governance_assessment`, identidad, validador, claims, derivación de
  requisitos, evaluación (`GovernanceAssessment` con completitud global y por dimensión), `card_path`,
  `write_governance_assessment`, `evaluate_governance_assessment`.
- Extensión aditiva de la Foundation: `CARD_KINDS += governance_assessment`; `OBSERVED_KINDS += model_card,
  governance_policy, evidence_document`; resolvers para esos tres kinds.
- Ubicación `governance/model-risk/<card_id>.json`. Tests con evidencia real ligera de Changes 0–2/v0.7.

## Fuera de alcance
- Calcular o interpretar fairness/explicabilidad/privacidad/seguridad; scanners; scores; clasificador
  automático de riesgo; cuestionario universal; mapeo regulatorio; claims de compliance.
- CLI pública, Doctor, rendering HTML, installer/manifest, capabilities, lectura de config
  (`project-config`/`local-overrides`), `ApprovalRef` real, combinación inválida de capabilities (Change 4).
- Waiver framework; crear checkpoints; segundo approval framework; nuevos STOP; gating de ejecución.
- Modificar `ModelCard` v1, `DataCard`, `modelquality`, `qualityevidence`, `datasources`, autonomy, runtime.
- Persistir en `guardrails.json` o `.harmessi/`.

## Principios aplicados
Harmessi gobierna evidencia: la policy dice QUÉ debe existir; el evaluador dice si está presente,
ausente, stale o `unverifiable`. `complete` = los requisitos de la policy están satisfechos; NO = modelo
éticamente aprobado, justo, seguro, explicable ni apto para producción. El `risk_level` es una declaración
humana (atestación), nunca una inferencia. La policy es monotónica: las capas inferiores solo endurecen.
Todo estado se deriva; nada de `fair=true` ni `status=passed` editables.

## Deudas preservadas
Change 4: lectura de policy/hardening desde config, CLI, Doctor, reporting, capabilities
(`data_cards`/`model_governance` opt-in; `model_governance` sin `predictive_modeling` inválido), resolución
real de `anchored`/`ApprovalRef`, integración de `governance/` con Doctor/exclusiones. v0.10: approval-origin
authenticity, LF/CRLF hashing, authorized-scope UX, composable skills/domain-modeling, one-writer.

## Criterios de cierre
Ver spec.md: assessments low/medium/high evaluables; monotonicidad verificable; relajación de proyecto
rechazada; atestación nunca suple evidencia observada exigida; completitud derivada; staleness por pin de
Model Card/policy/evidencia; inercia total fuera de `tools/cards`; regresión relevante verde.

## Impacto en production-readiness (opcional)
Aditivo e inerte: sin assessments el comportamiento de Harmessi es idéntico.

## Aprobación
- Usuario:
- Fecha:
- Alcance aprobado:
- Versión de artefactos referenciada:
- Cita o descripción fiel de qué se aprobó:

## Motivo de rechazo

## Desacuerdo registrado

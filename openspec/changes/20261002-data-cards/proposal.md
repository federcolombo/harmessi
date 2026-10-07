# Propuesta — 20261002-data-cards

> Change 1 de v0.9 (`docs/roadmap/v0.9.md`). Construido sobre `tools/cards` (Change 0, cerrado,
> commit `f5c3638`). No implementa Model Cards, riesgo/RAI, CLI, Doctor, rendering, installer ni
> capabilities (Changes 2–4).

## Problema
Change 0 dejó el contrato base de una Card (identidad, `EvidenceRef`, `HumanAttestation`, evaluación
derivada), pero no existe todavía ninguna Card concreta: nada describe un dataset/data product de forma
gobernada ni lo ata a observaciones de fuente reales de v0.8 o a evidencia de contratos de v0.7. Además,
Change 0 dejó sin resolver (O2) dónde viven físicamente las Cards, y no hay resolvers que sepan
comparar un pin de `EvidenceRef` con los artefactos reales (`SourceObservation`, manifests de
`qualityevidence`, `DataContract`).

## Objetivo
Definir y probar la **Data Card**: una vista de governance estructurada y respaldada por evidencia de un
dataset/data product LÓGICO (`1..N` fuentes), con resolvers que detectan cuándo la evidencia que cita
cambió, y una ubicación física project-owned. Sin recalcular nada, sin copiar evidencia, sin conectores.

## Evidencia
Audit read-only del 2026-10-02:
- `tools/datasources/core.py:744,861,936` (`SourceProvenance`, `SourceObservation`, `content_sha256()`
  sin `provenance.generated_at`); `runtime.py:574` (persistencia `.harmessi/observations/<source_id>__<hash12>/
  observation.json`; el id embebe el hash); `runtime.py:616` (`compare_fingerprint`); `core.py:392`
  (`SourceRef`, `role` de patrón libre; solo `raw_table` aparece en el repo); `.harmessi/sources.json`.
  **No existe loader/resolver de observaciones por id**: lo debe escribir este Change.
- `tools/datacontracts/core.py:601,793` (`DataContract.content_sha256()`); no hay artefacto persistido de
  «resultado de contrato» propio: `ds_guard contract validate --record-evidence` persiste un manifest de
  `qualityevidence` (`subject_kind=data_contract_evaluation`, `declaration.content_sha256` = hash del contrato).
- `tools/qualityevidence/core.py:359,435,507`, `evidence.py:324,549` (manifest en
  `.harmessi/quality/<evidence_id>/manifest.json`, hash persistido que excluye `generated_at`).
- `tools/harmessi/doctor.py:456` (drift solo sobre `.ds_init/control.json["archivos"]`);
  `tools/ds_init/manifest.py:897-905` (`EXCLUSIONES_PERMANENTES`, `MANIFEST` sin `cards`);
  `.gitignore` del repo no ignora `.harmessi/`: la evidencia runtime queda untracked por defecto;
  `.claude/guardrails.json` no restringe ninguna ruta candidata.
- `tools/cards/*` (API de Change 0: `validate_body` hook, `Requirement`, `evaluate`, `write_card`).
- No existen `data_product`, `unit_of_analysis`, `dataset_id` en el repo: la Data Card introduce la
  identidad de dataset lógico y referencia por pin lo ya existente (population/time en
  `qualityevidence.ScopeWindow`, `dataset.snapshot` de la observación).

## Supuestos descartados
- «Hay un resolver de observaciones»: no; el único lector es `ds_guard._validar_contrato_contra_observacion`.
- «El hash de archivo sirve de pin»: no; el hash de la observación excluye `generated_at`, el de bytes
  de archivo lo incluye (`file_sha256_resolver` daría stale falso).
- «Hay un artefacto de resultado de contrato»: no; el resultado es el manifest de `qualityevidence`.
- «`.harmessi/cards` es buen hogar»: mezcla governance durable con evidencia runtime untracked.

## Alcance
- `tools/cards/datacard.py`: contrato del cuerpo de una Data Card (`kind_schema_version=1`),
  `validate_data_card_body`, `requirements_for`, helpers de ubicación (`card_path`, `write_data_card`).
- `tools/cards/resolvers.py`: resolvers puros-stdlib por `kind` (`source_observation`,
  `source_provenance`, `harmessi_contract`, `quality_evidence`, `data_contract_result`) y
  `default_resolvers(repo_root)`.
- Extensión aditiva mínima de la Foundation: `write_card(..., exclusive=False)`.
- Ubicación: `governance/cards/data/<card_id>.json` (project-owned).
- Tests (objetos reales ligeros de v0.8/v0.7) y documentación mínima (ARCHITECTURE, roadmap).

## Fuera de alcance
- Model Cards, `risk_level`/RAI, policy de riesgo (Changes 2–3).
- `cards validate`, Doctor, rendering, capabilities `data_cards`/`model_governance`, entrada en el
  `MANIFEST`/`EXCLUSIONES_PERMANENTES`, provisioning (Change 4).
- Resolver real de `ApprovalRef` contra `control.json`/ledger (Change 4).
- Generar Cards automáticamente, profiling nuevo, recalcular contratos/calidad, lineage/DAG, catálogo,
  conectores, `domain-modeling`/glosario (v0.10).
- Reabrir Change 0 o cambiar `STOP_CATALOG`, autonomy, runtime, `ds_guard`.

## Principios aplicados
Cards are evidence-backed views, not evidence generators. Empty template != evidence. Una Data Card NO es
un Data Contract: describe el data product; el contrato valida estructura. La Card nunca se actualiza
sola: si lo observado cambia, queda `stale` hasta que se reemita.

## Deudas preservadas (no se resuelven aquí)
Change 4: resolución real de `ApprovalRef` (`anchored`), `data_cards` y `model_governance` opt-in (no por
default en `CAPABILITIES_CONOCIDAS`), `model_governance=true` + `predictive_modeling=false` inválido,
entrada de `governance/` en `EXCLUSIONES_PERMANENTES`. v0.10: approval origin/authenticity, hashing
LF/CRLF, composable skills/domain-modeling, authorized-scope mutation UX (registrada en
`docs/roadmap/v0.10.md` como parte de este Change).

## Criterios de cierre
Ver spec.md: Data Card de 1 y de N fuentes evaluables con resolvers reales sobre objetos reales de v0.8/
v0.7; stale/missing/mismatch fail-closed; ninguna ruta física filtrada; Card project-owned sin drift;
inercia total fuera de `tools/cards`; regresión relevante verde.

## Impacto en production-readiness (opcional)
Aditivo e inerte: sin Data Cards el comportamiento de Harmessi es idéntico.

## Aprobación
- Usuario:
- Fecha:
- Alcance aprobado:
- Versión de artefactos referenciada:
- Cita o descripción fiel de qué se aprobó:

## Motivo de rechazo

## Desacuerdo registrado

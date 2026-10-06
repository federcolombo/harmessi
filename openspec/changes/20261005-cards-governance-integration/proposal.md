# Propuesta — 20261005-cards-governance-integration

> Change 4 de v0.9 (`docs/roadmap/v0.9.md`). Construido sobre Changes 0–3 (`f5c3638`, `4ee222c`, `fcb0068`,
> `259b4f0`). Es integración/plumbing: NO crea conceptos científicos ni de governance nuevos.

## Problema
Changes 0–3 dejaron en `tools/cards/` un contrato puro (Foundation, Data Card, Model Card,
ModelGovernanceAssessment, policy) que ningún proyecto puede usar todavía: no se distribuye, no hay
capability que lo active, no hay CLI, Doctor ni reporting, y dos deudas explícitas quedaron reservadas:
(1) `anchored` es solo estructural (el `ApprovalRef` no se resuelve) y (2) un assessment que omite el
hardening vigente del proyecto puede quedar `complete` evaluado solo con la base (limitación I3 de Change 3).

## Objetivo
Integrar Cards y governance de modelo al producto con la mínima superficie: dos capabilities opt-in, provisioning
capability-aware, configuración efectiva de governance (base → proyecto → local), hardening actual obligatorio,
resolución real de `ApprovalRef`, `ds_guard cards validate|report`, integración con Doctor y renderizado vía
`tools/reporting/` (sin segundo renderer).

## Evidencia (audit read-only, 2026-10-05)
- Capabilities: `tools/ds_init/manifest.py:48` (`CAPABILITIES_CONOCIDAS=("predictive_modeling",)`, semántica «todas
  las conocidas habilitadas menos `--disable-capability`», `cli.py:161,241`); persistencia en
  `.ds_init/control.json["capabilities_habilitadas"]` (`control.py:109-110`); `sync` NO lee lo persistido y
  recalcula el default (`cli.py:241`, test `test_cli.py:905-929`); `sync` con stage igual o menor sale con «nada
  que hacer» (`cli.py:223-228`); filtro de entradas = subconjunto estricto (`manifest.py:1014-1019`, sin
  «cualquiera de»); Doctor trata `capabilities_habilitadas` ausente como «todo habilitado» (`doctor.py:412-417`).
- `tools/cards` NO está en `MANIFEST` (test_v09_cards_inert.py:99-115 lo exige hasta este Change);
  `tools/reporting` sí (siempre provisionado); `tools/harmessi` (Doctor) no se distribuye.
- Drift: `_check_hashes_drift` recorre solo `control["archivos"]` (`doctor.py:461-526`); `governance/` no está en
  `EXCLUSIONES_PERMANENTES` ni en el manifest y nadie lo escanea hoy.
- Config v0.8: `resolver_project_config` / `resolver_local_override` (`ds_guard.py:583-690`) sin schema ni
  validador central; precedente «local solo restringe»: `resolver_modo_efectivo`. Doctor no valida su contenido.
- Aprobaciones: único registro direccionable por `{change_id, artefacto, hash}` = `control.json["aprobaciones"]`
  (`ds_guard.py:315-384`); verificación existente: `dsguard.core.hash_lf_v1`, `sdd._aprobacion_mas_reciente`,
  `sdd.gate_implementacion`; ninguna función resuelve hoy un `ApprovalRef` (ni siquiera autonomy:
  `policy.py:405` solo compara). Ledger y aprobaciones de ejecución NO encajan con la forma del ref.
  Changes archivados viven en `openspec/archive/<id>` (`ds_guard.py:3193`).
- Reporting: modelo `Report > Chapter > {TableArtifact, FigureArtifact, Insight}` (`reporting/core.py`);
  `publish.publish(...)` exige ≥1 `source` (`validation.py:588`); `report_kind="eda"` activa el perfil EDA
  (`validation.py:400`); `reporting/governance.py` es un guard de destinos, no secciones; ningún paquete de dominio
  usa reporting hoy (cards sería el primer consumidor).
- CLI: dominios con CLI viven en `ds_guard` con import perezoso (`_importar_perezoso`, `ds_guard.py:1652`;
  `contract`, `quality`, `source`); `--json` por hoja; exit 0/1/2/3 (`dsguard/checks.py:98`).
- Tests de inercia v0.9 (Changes 0–3) prohíben textualmente «cards», `data_cards`, `model_governance` en
  `ds_guard.py`, `doctor.py`, `ds_init`, `autonomy`, `harmessi`, imports hacia `cards` desde fuera y entradas
  `cards` en `MANIFEST`: se enmiendan explícitamente en este Change; los de `STOP_CATALOG`/autonomía NO se tocan.

## Supuestos descartados
- «Agregar los nombres a `CAPABILITIES_CONOCIDAS` es neutral»: lo vuelve default-on (instalaciones nuevas y todo
  `sync` recibirían Cards y persistirían los nombres) y rompe tests que fijan la tupla.
- «`sync` hereda lo persistido»: hoy no lo hace y un test lo fija como «habilitar después vía sync»; se preserva
  para las capabilities históricas y solo las opt-in nuevas se heredan.
- «`capabilities_habilitadas` ausente = todo habilitado» es válido para las nuevas: sería activación implícita en
  instalaciones legacy; para opt-in ausente = deshabilitado.
- «Las aprobaciones de ejecución o el ledger sirven de `ApprovalRef`»: sus nombres/ids no cumplen la forma del ref.
- «El hardening de proyecto puede vivir dentro de `project-config.json`»: el assessment lo pinea como documento
  (`governance_policy`, hash del documento completo); pinear un archivo de config compartido volvería `stale`
  todo assessment ante cualquier edición ajena de ese archivo.
- «Reporting tiene bloques/callouts de primera clase»: no; se usan tablas, `summary` y `method_note` del Chapter.

## Alcance
- `ds_init`: capabilities opt-in `data_cards`/`model_governance` (`--enable-capability`), regla de dependencia,
  campo de manifiesto «cualquiera de», entradas de `tools/cards` (módulos, sin tests), `governance/` en
  `EXCLUSIONES_PERMANENTES`, `sync` en el mismo stage cuando cambia el set de capabilities.
- `tools/cards` (aditivo): `govconfig` (config efectiva + hardening actual), `approvals` (resolución de
  `ApprovalRef`), `discovery` (+ orquestación de validación de proyecto), `report` (adaptador a reporting); hook
  `anchor_verifier` y contexto de governance opcionales en los evaluadores (default = comportamiento de Changes 0–3).
- `ds_guard cards validate` y `ds_guard cards report`.
- Doctor: checks `HARMESSI-GOV-*` con tabla determinista de severidad.
- Documentación (ARCHITECTURE regla 13/§8, roadmap) y enmienda explícita de tests de inercia.

## Fuera de alcance
CRUD de Cards, list/edit/wizard/registry/UI; plantillas o Cards vacías; nuevos kinds de evidencia o
dimensiones; modificar `ModelCard`/`DataCard`/`BASE_POLICY` v1; STOP/autonomía/checkpoints/`approval_mode`;
`guardrails.json`; segundo approval store, firmas/PKI/identidad (deuda v0.10 «Approval origin / human
authorization authenticity»); segundo renderer o nuevas dependencias; migraciones o movimiento de archivos;
lifecycle framework de capabilities (solo se distingue enabled/disabled/installed-but-disabled en Doctor).

## Principios aplicados
Harmessi gobierna evidencia, no la genera. `complete` ≠ ético/seguro/justo/compliant. Estado siempre derivado.
Capas inferiores solo endurecen. Fail-closed: lo no verificable no cuenta ni se degrada a algo más débil que
satisfaga. D1/D5/D6 intactos. Validación de governance ≠ decisión de autonomía.

## Deudas preservadas
v0.10: approval-origin authenticity, LF/CRLF hashing, mid-Change authorized scope amendment UX (reformulada por el Corrective A),
composable skills, domain-modeling, one-writer. Nuevas registradas por este audit (no se resuelven acá): (a) la capa
local de hardening es por máquina; (b) `ApprovalRef` solo ancla aprobaciones de artefactos de un Change (nombre
simple), no archivos arbitrarios. (La deuda previa «sync no hereda las capabilities históricas» se RESUELVE en este
Change para el camino con flags: ver R5.)

## Criterios de cierre
Ver spec.md. Resumen: default sin flags idéntico (plan e instalación byte-idénticos); opt-in funcional;
`model_governance` sin `predictive_modeling` rechazado (installer y Doctor); hardening actual detectado
(omitido/otro/hash viejo ⇒ `stale`, inválido ⇒ fail-closed); `anchored` verificado contra `control.json`;
CLI/Doctor/reporting operativos; cero cambios de autonomía; regresión relevante verde.

## Impacto en production-readiness (opcional)
Aditivo y opt-in: sin flags nuevos, comportamiento anterior idéntico.

## Aprobación
- Usuario:
- Fecha:
- Alcance aprobado:
- Versión de artefactos referenciada:
- Cita o descripción fiel de qué se aprobó:

## Decisión material resuelta: `report_kind="governance"`
Aprobada por el autor (2026-10-06). `tools/reporting` define `REPORT_KINDS = (eda, model, evaluation, production)`
(`core.py:45`) y `DECISION_SCOPES = (exploratory, model_valid, operational)`. Audit: `evaluation` significa evaluación de
modelo y es la clave que `reporting.governance._autorizacion_read` exige (junto a `model_valid`/`operational`) para
autorizar lectura de holdout; `model` no describe una Data Card. Se agrega, de forma ADITIVA, el único valor neutral
`governance` a `REPORT_KINDS`: «reporte estructurado de governance/documentación/evidence sobre datos, modelos o
evaluaciones de governance». NO significa evaluación, resultado, validación, readiness, aprobación ni compliance, y NO
otorga acceso a holdout: `_autorizacion_read` queda sin cambios (solo `evaluation` + `model_valid|operational`), y
`governance` + `exploratory` permanece aislado de toda autorización de holdout (tests explícitos). No cambia ninguna otra
política de reporting. `decision_scope="exploratory"` se mantiene (su semántica documentada es verdadera para una Card);
no se agrega ningún `decision_scope` nuevo en v0.9.

## Alcance autorizado

- openspec/changes/20261005-cards-governance-integration/**
- ARCHITECTURE.md
- docs/roadmap/v0.9.md
- docs/roadmap/v0.10.md
- tools/ds_guard.py
- tools/ds_init/manifest.py
- tools/ds_init/cli.py
- tools/ds_init/control.py
- tools/ds_init/planner.py
- tools/ds_init/tests/**
- tools/cards/**
- tools/harmessi/doctor.py
- tools/harmessi/tests/**
- tools/reporting/core.py
- tools/reporting/tests/**
- tools/tests/**
- tools/autonomy/tests/**
- tools/leadrun/tests/**
- tools/modelquality/tests/**
- tools/qualityevidence/tests/**
- tools/datasources/tests/**
- tools/datacontracts/tests/**

## Motivo de rechazo

## Desacuerdo registrado

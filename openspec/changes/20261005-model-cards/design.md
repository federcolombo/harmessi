# Diseño — 20261005-model-cards

## Decisión metodológica/técnica

**D1 — Composición sobre la Foundation, espejo de Data Cards.** Una Model Card es un `CardEnvelope`
(`card_kind="model_card"`) cuyo `body` valida `modelcard.py` vía el hook `validate_body`; reutiliza
`EvidenceRef`, `HumanAttestation`, `Claim`, `Requirement`, `evaluate`, `evaluate_file`, serialización,
`write_card(exclusive)`. Se mantiene la estructura de módulos de `datacard.py` (cuerpo cerrado,
`_validar_claims`, `card_path`, `write_*`, `evaluate_*`), sin un tipo nuevo de Card ni una jerarquía
paralela. Un módulo aparte (no `datacard.py` extendido) evita acoplar dominios.

**D2 — Identidad por versión, mecanismo mínimo sin registry.** El requisito del autor («nueva versión ⇒
nueva Card; las revisiones corrigen la MISMA versión») se garantiza **estructuralmente**: `card_id` es una
función determinista y verificable de `(model_id, model_version)`. Con patrones restringidos (R7: sin `__`
en `model_id`, sin `_` en `model_version`, sin separadores consecutivos) el mapeo es inyectivo y reversible
(se parte en el único `__`) sin hashing opaco. Así: (a) cambiar `model_version` cambia `card_id`; (b) `write_model_card(replace=True)`
exige la misma identidad, por lo que una Card de v2 jamás puede sobrescribir la de v1; (c) `revision_id`
(hash del documento) sólo varía por edición documental. No se crea índice, listado ni registry. Costo: las
versiones se limitan a minúsculas/`.`/`-` (sin asumir SemVer; fechas, semver, hashes cortos y etiquetas
propias caben); versiones con `_` o mayúsculas deben normalizarse. No se fija un límite arbitrario por
campo: el único tope es el presupuesto compartido de `card_id` ≤ 64 de la Foundation
(`len(model_id) + 2 + len(model_version) ≤ 64`); subirlo reabriría Change 0 y no está justificado. Alternativa descartada: `card_id` libre +
`model_version` como metadato (permite pisar una versión con otra silenciosamente).

**D3 — Pin por tipo, sin «latest».** Auditoría: los manifests de calidad son directorios inmutables por id
(`qe-…`), las políticas no tienen versión, y métricas/baselines/drift viven en archivos del proyecto sin
supersession. Por eso cada resolver resuelve EXACTAMENTE lo pineado y compara hash: nunca se busca «lo más
reciente» (a diferencia de `source_observation` en Data Cards, donde el id embebe el hash y hace falta la
noción de fuente lógica). Se evita así repetir el historical-stale y el falso-fresh A→B→A. Efecto: una
Model Card sólo se vuelve `stale` si lo que pineó cambió; la existencia de una métrica nueva no la
invalida.

**D4 — Qué se pinea de v0.7 (reuso, no segunda representación).**
- Resultado de calidad: manifest `model_quality_evaluation` (`kind=model_quality_result`, por `evidence_id`);
  reutiliza la verificación de integridad del hash persistido ya usada en Change 1.
- Política: `kind=model_quality_policy` (`ref_id=policy_id`, `locator` al JSON, hash canónico del dict).
  `harmessi_contract` no sirve (exige `id@semver`).
- `ObservedMetric` / `BaselineReference`: `kind=observed_metric|baseline_reference` con `locator` al JSON-
  lista que consume `ds_guard quality evaluate`; el pin cubre el documento entero y `member` selecciona
  semánticamente la entrada con la identidad real de v0.7 (`<metric_name>@<context_id>` / `baseline_id`),
  fail-closed ante inexistente o duplicado, nunca posicional (R26, R31). Es la única forma de citar a nivel de entrada porque v0.7 no las
  persiste ni les da id.
- Drift: `kind=drift_evidence` sobre un JSON que el usuario guardó (v0.7 no lo persiste a propósito).
- Contexto de evaluación: viaja dentro de la `ObservedMetric` pineada; no se duplica.
Todos son punteros con hash; nada se copia ni recalcula.

**D5 — Data Cards por pin de revisión.** `kind=data_card` con `ref_id=<card_id>__<hash12>` = `revision_id`
de la Data Card, `content_sha256` = hash de su envelope. El resolver lee con `assess.read_card` (valida
estructura y revisión) y NO reevalúa su completitud: la Model Card cita *qué* Data Card, no *cuán buena* es.
El pin valida identidad, existencia, integridad y revisión; no hereda el estado de governance de la Data
Card ni dispara evaluaciones recursivas (exigir una Data Card `complete` es Change 3).
Revisar la Data Card deja el pin stale y fuerza reemitir la Model Card (semántica de integridad deliberada,
no de «latest»).

**D6 — Artefacto del modelo: neutral y opcional.** No hay identidad de artefacto en Harmessi
(`outputs_hash` de `ExecutionRecord` es siempre `None`). `provenance_refs` acepta `execution_record`
(resolvible: hash del record sin `generated_at`) o `report_artifact`, ambos primitives existentes. Sin
campos de ruta/formato/URI; no se hashean binarios. Si el proyecto necesita pinear un binario, lo hará con
un mecanismo futuro; el contrato no lo impide (`x_*`).

**D7 — Requisitos derivados y uniformes.** Un requisito por pin citado (`evidence_<evidence_id>`,
`required`) + `ownership` (`recommended`). «Lo que se cita debe estar respaldado», sin decidir qué
evidencia debe existir (eso es riesgo → Change 3). Más simple y menos permisivo que requisitos por familia;
`_validar_claims` exige `supports == (eid,)` por claim, lo que evita enmascarar el stale de un pin con otro
(lección del bloqueante B1 de Data Cards).

**D8 — Task neutral.** `task.role` es un identificador libre (patrón), con los roles de `modelquality`
sólo como convención documentada; sin enum, sin scikit-learn, sin taxonomía.

**D9 — Sin RAI ni conclusiones.** El cuerpo es cerrado: `risk_level`, fairness, etc. son claves desconocidas
(rechazadas). Ni requisitos ni evaluación leen valores de métricas: «el modelo es bueno» no se infiere.
`Card complete` ≠ modelo bueno ni gobernado: se documenta explícitamente.

**D10 — Ubicación.** `governance/cards/model/<card_id>.json` (singular `model`, simétrico con `data`);
mismos argumentos que Data Cards (project-owned, Git, fuera de `.harmessi/` y del manifest, sin drift,
sin overwrite).

**D11 — Extensión de vocabulario de la Foundation.** Tres kinds nuevos al final de `OBSERVED_KINDS`
(`data_card`, `model_quality_result`, `model_quality_policy`) más resolvers para ellos y para
`observed_metric`, `baseline_reference`, `drift_evidence`, `execution_record` (ya declarados pero sin
resolver). Es aditivo: las Cards existentes no cambian, y las pruebas que fijaban los conteos se
actualizan de forma mínima. Foundation-level porque son artefactos de Harmessi citables por cualquier Card.

## Archivos previstos
Nuevos: `tools/cards/modelcard.py`, `tools/cards/tests/{test_modelcard,test_modelcard_location,
test_resolvers_model}.py`, `tools/tests/test_v09_modelcards_{parity,inert}.py`.
Modificados: `tools/cards/core.py` (3 kinds), `tools/cards/resolvers.py` (7 resolvers + hashes),
tests de Changes 0–1 estrictamente afectados por los conteos (`test_evidence.py`, `test_resolvers.py`,
neutralidad/inercia), `ARCHITECTURE.md` (regla 13/§8), `docs/roadmap/v0.9.md` (progreso),
`docs/roadmap/v0.10.md` (deuda ya agregada). No se tocan: `ds_guard.py`, `ds_init/*`, Doctor, `autonomy`,
`leadrun`, `modelquality`, `qualityevidence`, `datacontracts`, `datasources`, `reporting`.

## Tests previstos
Objetos reales ligeros: `ModelQualityPolicy`/`ObservedMetric`/`BaselineReference` reales de
`modelquality`; manifest real `model_quality_evaluation` escrito con `qualityevidence` (via
`evaluate_policy` + `build/write_manifest`); `DriftEvidence` real guardado como JSON; `ExecutionRecord`
real; Data Card real escrita con `write_data_card`. Casos: Card mínima; identidad (`card_id` derivado,
versión nueva ⇒ Card nueva, `replace` entre versiones falla, revisión documental ⇒ mismo `card_id`,
`revision_id` distinto); múltiples `data_card_refs` con roles; evidencia v0.7 completa; métrica/baseline
alterados ⇒ stale; manifest ausente/adulterado/subject incorrecto; política modificada ⇒ stale; Data Card
revisada ⇒ stale; drift y execution_record; atestación `declared`/`anchored` estructural; atestación no
satisface `evidence_*` por kind; claim con soporte ajeno ⇒ inconsistente; `task.role` libre;
`risk_level` rechazado; claves desconocidas; ruta física/DSN; serialización determinista y round-trip;
archivo mal formado ⇒ invalid; ubicación/no overwrite/no drift; paridad de hashes con `modelquality`/
`qualityevidence`/`ExecutionRecord`; inercia (STOP, manifest, capabilities, `ds_guard`/Doctor/autonomy);
regresión Changes 0–1 y suites v0.7/v0.8.

## Target (condicional)
No aplica (`target_reference` es descriptivo).

## Features permitidas/prohibidas (condicional)
No aplica.

## Estrategia de split/validación (condicional)
No aplica: no se evalúan modelos; los resolvers jamás leen datos de proyecto ni holdouts.

## Leakage risks (condicional)
No hay datasets ni features. Riesgo análogo de integridad: que una Model Card afirme calidad sobre
evidencia distinta de la citada o que se reutilice la Card de una versión para otra. Mitigaciones: pin por
hash, `supports == (eid,)`, `card_id` derivado de la versión, `replace` con misma identidad, atestación ≠
evidencia empírica.

## Reproducibilidad (opcional)
Sin aleatoriedad; relojes inyectables; JSON canónico determinista.

## Alternativas descartadas
- Registry/índice de modelos o `model_version` solo como metadato.
- Semántica «latest» para evidencia de calidad (no existe supersession en v0.7).
- Persistir métricas/baselines/drift en `.harmessi/` (cambia `modelquality`/`qualityevidence`).
- Copiar métricas/valores a la Card o derivar «bueno/malo».
- Enum cerrado de tasks / acoplar a sklearn.
- Requisitos por familia (más reglas de claim) en lugar de uno por pin.
- Pinear binarios de modelo (`.pkl`, ONNX, MLflow, URIs).

## Riesgos
- *Extensión de la Foundation*: mitigada por aditividad y actualización mínima de tests de conteo.
- *Limitación R31 de hash de entradas escritas a mano* (misma clase que contratos): documentada.
- *Pins de Data Card ruidosos* (cada revisión de Data Card obliga a reemitir): es el trade-off de
  integridad elegido; Change 3 podrá matizarlo con policy.
- *Evidencia untracked en clones* (`.harmessi/quality`, `.harmessi/executions`): mismos efectos que R27 de
  Data Cards (missing ⇒ incomplete, fail-closed). Políticas y listas de métricas, al ser archivos del
  proyecto, sí viajan con Git.
- *Scope creep a RAI*: cuerpo cerrado y rechazo explícito de claves de riesgo.

## Decisiones materiales
Ninguna pendiente. Quedan informadas para el registro: (i) identidad por versión mediante `card_id`
derivado (D2) — mecanismo para la preferencia ya expresada; (ii) extensión aditiva de vocabulario de la
Foundation (D11), expresamente permitida.

## Aprobación humana
<!-- El registro de aprobación (usuario, fecha, alcance, versión de artefactos, cita) es único
por cambio y vive en la sección "Aprobación" de proposal.md — no se duplica acá. -->

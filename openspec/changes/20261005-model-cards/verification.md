# Verificación — 20261005-model-cards

## Resumen ejecutivo
Change 2 de v0.9: **Model Card** como especialización por composición de la Foundation, una Card por
versión de modelo, que referencia por pin evidencia real de v0.7 y Data Cards de Change 1. SDD aprobado por
hash el 2026-10-05 con tres precisiones del autor incorporadas antes de aprobar (model_version file-safe e
inyectivo sin asumir SemVer; pin de Data Card sin herencia de governance; `member` semántico no
posicional). Todas las ejecuciones pasaron por el runtime gobernado (`ds_guard exec pytest`), aprobadas con
`ds_guard exec approve`. Sin cambios en `ds_guard.py`, manifest, Doctor, capabilities, autonomy, runtime,
`STOP_CATALOG`, `modelquality`, `qualityevidence`, `datasources`, `datacontracts` ni `reporting`.

## Qué entrega
- `tools/cards/modelcard.py`: `CardEnvelope(card_kind="model_card", kind_schema_version=1)` con body
  cerrado (obligatorios `model_id`, `model_version`, `description`; opcionales `task`, `population`,
  `intended_uses`, `out_of_scope_uses`, `known_limitations`, `stewardship`, `data_card_refs`,
  `evaluation_refs`, `provenance_refs`, `x_*`). Identidad: `card_id = model_id__<model_version con "."→"_">`,
  reversible (`decode_model_card_id`), con presupuesto `len(model_id)+2+len(model_version) ≤ 64`
  (límite de la Foundation sobre `card_id`; sin límites arbitrarios por campo). Requisitos derivados: uno
  `required` por pin citado (`evidence_<evidence_id>`) y `ownership` `recommended`; `_validar_claims`
  exige `supports == (eid,)` (aislamiento de claims). `card_path`, `write_model_card` (sin overwrite),
  `evaluate_model_card`.
- `tools/cards/resolvers.py` (+7): `data_card`, `model_quality_result`, `model_quality_policy`,
  `observed_metric`, `baseline_reference`, `drift_evidence`, `execution_record`; hashes públicos
  `hash_document`, `hash_policy`, `hash_drift`, `hash_execution_record`. `default_resolvers` cubre 12 kinds
  (solo `report_artifact` sin resolver).
- `tools/cards/core.py`: `OBSERVED_KINDS` +3 al final (`data_card`, `model_quality_result`,
  `model_quality_policy`; 13 en total). Extensión aditiva de vocabulario; las Cards existentes no cambian.
- Ubicación: `governance/cards/model/<card_id>.json` (project-owned, fuera de `.harmessi/` y del manifest;
  sin drift, probado con `_check_hashes_drift` real).
- Docs: ARCHITECTURE (regla 13), roadmap v0.9 (progreso).

## Qué significa `complete` (explícito)
`complete` en Change 2 = «el documento está completo según su contrato actual: lo que la Model Card cita
está respaldado y es verificable». NO significa modelo bueno, seguro, fair, aprobado, listo para
producción ni Responsible AI satisfecho; la exigencia de qué evidencia debe existir según el riesgo es
Change 3. Ninguna métrica se recalcula ni se compara y no se infiere «bueno/malo».

## Ejecuciones reales
Dirigida: primera corrida 866 passed / 2 failed; tras ajustes de tests (ver abajo) y fixes:
**870 passed, 20 skipped, 2275 subtests, 0 failed, pytest exit 0**.

Regresión relevante, lotes SECUENCIALES (exit code real del proceso pytest leído del `ExecutionRecord`):

| Lote | Suite | Resultado | pytest exit |
|---|---|---|---|
| 1 | `tools/tests` (architecture, neutralidad, inercia, manifest, exec, …) | 1164 passed, 6 skipped, 743 subtests | 0 |
| 2 | `modelquality`, `qualityevidence`, `datasources`, `datacontracts` (tests) | 511 passed, 150 subtests | 0 |
| 3 | `autonomy`, `leadrun` (tests) | 241 passed, 261 subtests | 0 |
| 4 | `tools/cards/tests` (11 archivos) | 719 passed, 20 skipped, 1586 subtests | 0 |

**Agregado: 2635 passed, 26 skipped, 0 failed, 2740 subtests passed; 4 lotes; 0 reintentos por memoria.**
Doctor: 27 OK, 1 WARN (working tree con cambios sin confirmar), 0 ERROR. Los skips son tests de symlink
(el SO no permite crearlos sin privilegio).

## Hallazgos durante la implementación
- **Bug real de producción detectado por tests:** `resolvers.hash_drift` incluía la clave `content_sha256`
  que `DriftEvidence.to_dict()` agrega y `DriftEvidence.content_sha256()` no hashea → pin siempre stale.
  Corregido (excluye `generated_at` y `content_sha256`); el resolver además trata un `content_sha256`
  persistido que no coincide con el recomputado como integridad rota (`unverifiable`).
- Dos tests fallaron en la primera corrida por supuestos de test (no de producción): el de drift alteraba
  el JSON sin recalcular el hash persistido (ahora hay un test de alteración legítima → stale y otro de
  alteración sin recalcular → unverifiable), y un test de Change 1 suponía el conjunto de 5 kinds.

## Ajustes mínimos a tests de Changes 0–1 (documentados)
Por la extensión aditiva de vocabulario y los resolvers nuevos: `test_evidence.py` (10 → 13 kinds),
`test_resolvers.py` (5 → 12 resolvers; solo `report_artifact` sin resolver), `test_datacard.py` (un test
comparaba contra el conjunto fijo de 5 kinds), y las tablas de hermanos permitidos de
`test_v09_cards_neutrality.py` / `test_v09_datacards_inert.py` (+`modelcard.py`). Ninguna aserción de fondo
se debilitó; los conteos eran invariantes internos de test, no contrato público.

## Proceso de revisión (ciclo 1 de máximo 2; no hizo falta el 2)
0 bloqueantes; 2 importantes de precisión documental; menores documentados:
- **Corrección de atribución (spec R26, aprobado por hash y por eso no editado):** el spec dice que v0.7
  identifica la métrica por `metric_name` + `context.context_id`; en realidad `modelquality.validation`
  selecciona por `metric_name` y coincidencia de contexto (split, etc.) y **nunca compara `context_id`**.
  El selector `<metric_name>@<context_id>` es una convención propia de Harmessi Cards (determinista,
  inyectiva, fail-closed). Consecuencia: dos entradas con el mismo `metric_name` y split pero distinto
  `context_id` resuelven como members distintos aquí, y `ds_guard quality evaluate` las vería ambiguas. La
  corrección está en los docstrings de `resolvers.py`.
- **R33 vs comportamiento:** `write_model_card(replace=True)` con otra versión apunta a otro `card_id`/
  archivo y devuelve `MODELCARD-NOT-FOUND` (nunca escribe sobre la Card de otra versión);
  `MODELCARD-IDENTITY-MISMATCH` aplica cuando hay un archivo de otra identidad en esa ruta. Los criterios
  Given/When/Then del spec decían «→ MISMATCH» para este caso; el comportamiento es más seguro y los tests
  aceptan ambos códigos. Documentado en `modelcard.py`.
- Menores aceptados: pins en `card.evidence` no citados desde el body no generan requisito (solo WARN de
  evidencia stale); `execution_record` no verifica que el hash12 del id coincida con el hash de identidad
  (el hash del documento queda pineado); ventana TOCTOU residual en `replace` (igual que Data Cards).

## Limitaciones conocidas y deuda (no bloqueantes)
- **Staleness conservadora:** pin exacto, sin «latest»; una métrica nueva NO vuelve stale la Card. Efecto
  deliberado: una Data Card citada que se revisa vuelve stale su pin (hay que reemitir la Model Card). El
  pin de Data Card no hereda su estado de governance ni dispara evaluaciones recursivas.
- Pin de `observed_metric`/`baseline_reference` cubre el documento completo: cambiar cualquier entrada del
  archivo vuelve stale los pins sobre ese archivo; el hash es sobre el JSON tal como está en el archivo
  (un archivo a mano con defaults omitidos hashea distinto de su forma normalizada).
- v0.7 no persiste métricas/baselines/política ni drift: los pins dependen de archivos del proyecto (que
  viajan con Git) o de `.harmessi/` (untracked por defecto → `missing` tras un clon, fail-closed).
- `title`, `Claim.statement` y textos de atestaciones no se validan (Foundation); la heurística de
  portabilidad de texto libre solo detecta rutas al inicio, `\`, `://` y credenciales.
- `anchored` sigue siendo estructural; las aprobaciones son declaraciones registradas, no firmas.
- Limitaciones de Data Cards sin cambios (historical-stale, A→B→A, `.harmessi/` tras clon, semver,
  longitud de ids de requisito, `quality_evidence_ids`): no se tocaron.
- Change 4: resolución real de `ApprovalRef`, `data_cards`/`model_governance` opt-in, combinación inválida
  `model_governance` sin `predictive_modeling`, `governance/` con Doctor/exclusiones. Change 3: risk_level,
  fairness, explainability, privacy, security, accountability, human oversight y requisitos por riesgo.
  v0.10: authenticity de aprobaciones, LF/CRLF hashing, authorized-scope UX, composable skills/
  domain-modeling, one-writer concurrency semantics (registrada).
- Fin de línea: archivos nuevos en LF; `core.autocrlf` avisa conversión a CRLF al commitear (deuda v0.10).

## One-writer
Se usaron instancias del writer en paralelo con propiedad de archivos disjunta y explícita (resolvers/core
y tests de conteo; `modelcard.py`; tests de Model Card; tests de resolvers/paridad/inercia), sin solapes.

## Resultado final
Change 2 completo y verde. Listo para cierre.

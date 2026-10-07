# Verificación — 20261002-data-cards

## Resumen ejecutivo
Change 1 de v0.9: **Data Card** como especialización por composición de la Foundation (Change 0). SDD
aprobado por hash el 2026-10-02 (sin decisiones materiales pendientes). Todas las ejecuciones pasaron por
el runtime gobernado (`ds_guard exec pytest`), aprobadas con `ds_guard exec approve`. Sin cambios en
`ds_guard.py`, manifest, Doctor, capabilities, autonomy, runtime ni `STOP_CATALOG`.

## Qué entrega
- `tools/cards/datacard.py`: `DataCard = CardEnvelope(card_kind="data_card", kind_schema_version=1)` con
  body cerrado (obligatorios `description` y `source_refs` 1..N; el resto opcional y `x_*`);
  `source_refs[]` (`source_ref_id`, `source_id` lógico, `role` libre, `observation_evidence_id`,
  `provenance_evidence_id`, `time_scope`) que referencian pins de `card.evidence` sin copiar la observación;
  `contract_refs[]` (declaración pineada + resultados), `body_validator_for`, `validate_data_card`,
  `requirements_for` (derivados, no persistidos), `card_path`, `write_data_card` (no overwrite),
  `evaluate_data_card`.
- `tools/cards/resolvers.py`: resolvers stdlib `source_observation`, `source_provenance`,
  `harmessi_contract`, `quality_evidence`, `data_contract_result` y hashes públicos (`hash_observation`,
  `hash_provenance`, `hash_contract`, `hash_quality_manifest`) con paridad testeada contra los tipos
  reales de v0.7/v0.8, sin importarlos.
- Extensión aditiva de la Foundation: `assess.write_card(..., exclusive=False)` (publicación con
  `os.link`, sin overwrite; fallback sólo por falta de hard links; fail-closed).
- Ubicación: `governance/cards/data/<card_id>.json` (project-owned, fuera de `.harmessi/`, fuera del
  manifest: crear/editar no produce `HARMESSI-DRIFT`, probado con `_check_hashes_drift` real).
- Documentación: ARCHITECTURE (regla 13/§8), roadmap v0.9 (progreso) y v0.10 (deuda de UX de scope).

## Identidad
`card_id` = data product lógico; `revision_id` = revisión del documento; el pin
(`source_id__hash12` + `content_sha256`) = revisión de la evidencia citada. Tres cosas distintas,
verificadas por test (misma observación, distinta revisión de Card).

## Ejecuciones reales
Corridas dirigidas (ciclos): primera 536 passed/1 failed (test de neutralidad de Change 0 que no conocía
los módulos hermanos nuevos → ajuste mínimo y estricto); tras reviewer ciclo 1: 4 fallos de fixtures
alineados; **final: 578 passed, 10 skipped, 1308 subtests, 0 failed, pytest exit 0**.

Regresión relevante, lotes SECUENCIALES (exit code real del proceso pytest leído del `ExecutionRecord`):

| Lote | Suite | Resultado | pytest exit |
|---|---|---|---|
| 1 | `tools/tests` (architecture, neutralidad, inercia, manifest, exec, …) | 1108 passed, 6 skipped, 548 subtests | 0 |
| 2 | `tools/datasources/tests`, `tools/datacontracts/tests`, `tools/qualityevidence/tests` | 403 passed, 150 subtests | 0 |
| 3 | `tools/autonomy/tests`, `tools/leadrun/tests` | 241 passed, 261 subtests | 0 |
| 4 | `tools/cards/tests` (8 archivos) | 483 passed, 10 skipped, 814 subtests | 0 |

**Agregado: 2235 passed, 16 skipped, 0 failed, 1773 subtests passed; 4 lotes; 0 reintentos por
memoria.** Doctor: 27 OK, 1 WARN (working tree con cambios sin confirmar), 0 ERROR. Los 10 skips son
tests de symlink que el SO no permite crear sin privilegio.

## Proceso de revisión (2 ciclos, máximo permitido)
- **Ciclo 1:** 0 violaciones de arquitectura; 1 bloqueante (B1) + 5 importantes. B1: un claim
  `source_<X>` podía satisfacerse con evidencia de otra fuente o ocultar el stale de la propia →
  `_validar_claims` exige la observación propia y sólo soportes de la misma source_ref (código
  `DATACARD-CLAIM-SUPPORT-INCONSISTENT`; Card `invalid`). I2/I3: `ref_id` exige `fullmatch
  <source_id>__<12 hex>` y, para observaciones, hash12 == `content_sha256[:12]`. I1: strings bajo `x_*`
  validados contra rutas/DSN. I5: parseo de `generated_at` robusto en 3.9–3.12. M1: `exclusive` sólo hace
  fallback por falta de hard links; `PermissionError` nunca sale crudo.
- **Ciclo 2:** 0 bloqueantes; hallazgos cerrados; 1 importante (falso fresh A→B→A, ver limitaciones),
  documentado y fijado por test; menores documentados/cubiertos.

## Divergencias del SDD aprobado (documentadas, no materiales)
- Ids de requisito: `source_<source_ref_id>`, `contract_<contract_id>`, `ownership` en lugar de
  `source:<…>`/`contract:<…>`: el patrón de ids de la Foundation (`[a-z0-9][a-z0-9_-]{0,63}`) no admite
  `:` y no se reabre Change 0. Los helpers `requirement_id_for_*` son la única fuente del formato; implica
  `source_ref_id` ≤ 57 y `contract_id` ≤ 55 caracteres (testeado).
- `semver` de `contract_refs` rechaza ceros a la izquierda (`01.0.0`), más estricto que
  `datacontracts` (que los acepta): no se puede citar una versión de contrato inválida según semver.
- Los claims `contract_*` sólo pueden apoyarse en la declaración y los resultados de sus `contract_refs`;
  `quality_evidence_ids` se evalúan por pin (stale/missing → WARN) pero no pueden ser soporte de claims.

## Limitaciones conocidas y deuda (no bloqueantes)
- **Historical-stale (D6, aceptada por el autor):** una Data Card que documenta deliberadamente una
  observación histórica queda `stale` mientras exista una observación posterior del mismo `source_id`.
  Candidato futuro (sin versión asignada): *historical / as-of freshness semantics*.
- **Falso fresh en A→B→A:** el runtime v0.8 no reescribe un directorio de observación existente
  (`_persistir_observacion` compara bytes, incluido `generated_at`; una re-observación idéntica con otro
  `generated_at` reporta "colisión de hash" y no actualiza). Tras A(T1), B(T2), A(T3) el «vigente» sigue
  siendo B por mayor `generated_at`: un pin de B figura `fresh` aunque la fuente haya vuelto a A, y el pin
  de A queda `stale`. Es fail-open en ese caso borde; test que lo fija. No se corrige en v0.8.
- **R27:** `.harmessi/` es untracked por defecto; en un clon nuevo los pins quedan `missing` →
  `incomplete` (fail-closed) hasta re-observar y reconstruir evidencia local. No se resuelve portabilidad
  de runtime evidence.
- `hash_contract` hashea el dict crudo: sólo coincide con `DataContract.content_sha256()` si el archivo es
  un dump de `to_dict()`; un contrato escrito a mano con defaults omitidos produce otro hash (test lo fija).
- Los pins de resultado de contrato no se ligan al contrato citado más allá de la restricción de soportes;
  una declaración stale puede quedar enmascarada por un resultado fresco del mismo `contract_id` en el
  requisito recomendado (la evidencia stale se reporta igual); `contract_<id>` se deduplica entre versiones.
- El hash12 del `ref_id` de provenance no se cruza con el de la observación.
- La heurística de portabilidad de textos libres sólo detecta rutas al inicio, `\`, `://` y credenciales;
  `title`, `Claim.statement` y textos de atestaciones pertenecen a la Foundation y no se validan.
- En FAT/exFAT o shares sin hard links la creación exclusiva falla cerrada (`CARD-IO-ERROR`).
- `anchored` sigue siendo estructural (resolución real del `ApprovalRef` en Change 4); las aprobaciones son
  declaraciones registradas, no firmas ni prueba de autoría (deuda v0.10).
- Change 4: `data_cards`/`model_governance` opt-in (no en `CAPABILITIES_CONOCIDAS` por defecto),
  `model_governance=true` + `predictive_modeling=false` inválido, integración de `governance/` con
  Doctor/exclusiones. v0.10: authenticity de aprobaciones, LF/CRLF hashing, composable skills y
  domain-modeling, authorized-scope mutation UX (registrada).
- Fin de línea: archivos nuevos en LF; `core.autocrlf` avisa conversión a CRLF al commitear (deuda LF/CRLF
  de v0.10).

## Resultado final
Change 1 completo y verde. Listo para cierre.

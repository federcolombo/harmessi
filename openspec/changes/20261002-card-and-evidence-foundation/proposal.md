# Propuesta — 20261002-card-and-evidence-foundation

## Problema
v0.9 agrega Data Cards (Change 1), Model Cards (Change 2) y model risk / Responsible AI (Change 3).
Sin un contrato base compartido, cada Change redefiniría identidad, referencias a evidencia, atestaciones
humanas y semántica de completitud/stale, con divergencias entre Cards. Hoy no existe en el código
ninguna primitiva de Card, `HumanAttestation` ni enum de completitud (audit: `HumanAttestation`,
`Attestation`, tipos Card y enum `complete/incomplete/stale` → no encontrados; solo aparecen en
`docs/roadmap/v0.9.md` y `ARCHITECTURE.md` §8).

## Objetivo
Definir y probar, en un paquete neutral `tools/cards/`, el contrato base de una Card respaldada por
evidencia: identidad, versionado, referencias a evidencia observada, `HumanAttestation`, evaluación
determinista de completitud/stale y serialización, sin ninguna Card concreta.

## Evidencia
Audit read-only del 2026-10-02 (reuso v0.6–v0.8). Primitivas reutilizables como CONVENCIÓN (no como
import, regla de familias independientes de `ARCHITECTURE.md` §3):
- `tools/datasources/core.py`: `SCHEMA_VERSION`, `SOURCE_ID_PATTERN` (:56), `canonical_json` (:301),
  `content_sha256` (:316), `SourceObservation.content_sha256()` que excluye `generated_at` (:861),
  prefijo de extensiones `x_` (:50), id `<base>__<hash12>` (`runtime.py:574`),
  `compare_fingerprint` PASS/FAIL/WARN (`runtime.py:616`).
- `tools/qualityevidence/core.py`: `DeclarationRef` (:359) y `EvidenceSource` (:277) como patrón de
  referencia por id+versión+hash; `resolve_evidence_ref` (`evidence.py:549`) que nunca lanza.
- `tools/modelquality/core.py`: `ObservedMetric` (:480) y `BaselineReference` (:560) con `evidence_ref`
  libre (str) — la Card los referencia por contenedor + `member`.
- `tools/leadrun/core.py`: `ExecutionRecord` (:360), id `<command_form>__<hash12>`.
- `tools/autonomy/core.py`: `ApprovalRef` (:381, `change_id`/`artefacto`/`hash`), sin timestamp;
  `validate_human_identity` (:427).
- `tools/dsguard/checks.py`: `CheckResult` y `STATUS_PASS/WARN/FAIL/NA`; `dsguard/core.py`:
  `ahora_utc` (`%Y-%m-%dT%H:%M:%SZ`), `escribir_texto_atomico`.
- Convención de Changes: `openspec/changes/20261001-v08-release-hardening/`.

## Supuestos descartados
- "Reusar `ApprovalRef` como atestación": no tiene actor, claim, scope ni timestamp; es solo un ancla de
  hash. `HumanAttestation` es nuevo y lo contiene opcionalmente (forma validada, sin importar `autonomy`).
- "Existe un enum de completitud/stale": solo existen códigos sueltos (`SOURCE-OBSERVATION-STALE`,
  `QUALITYEVIDENCE-STALE`, `REPORT-SOURCE-STALE`); el enum es nuevo y se DERIVA de ellos.
- "Hay un resolver común de evidencia": no hay helpers compartidos entre paquetes (duplicación
  deliberada); la resolución se inyecta.

## Alcance
- Paquete `tools/cards/` (solo stdlib): `core.py` (tipos, ids, serialización, códigos) y `assess.py`
  (resolución inyectada, estados de evidencia, completitud derivada, salida `CheckResult`).
- Tipos: `CardEnvelope`, `EvidenceRef`, `HumanAttestation`, `Claim`, `Requirement`, `Resolution`,
  `CardAssessment`.
- Reglas 13 de dependencia + tests de neutralidad/paridad/no-STOP.
- Expansión mínima de `ARCHITECTURE.md` (§3 regla 13, §8).

## Fuera de alcance
- Data Card / Model Card concretas, `source_refs` multi-fuente (Change 1), referencias específicas a
  v0.7 de Model Card (Change 2); `risk_level`, dimensiones Responsible AI, policy de riesgo (Change 3).
- `cards validate`, Doctor, rendering, capabilities `data_cards`/`model_governance`, instalación vía
  `ds_init`/manifest, cambios en `ds_guard.py` (Change 4).
- Cualquier STOP nuevo o cambio de `STOP_CATALOG`, `approval_mode` o autonomy policy (D1, D6).
- Resolvers específicos por tipo de evidencia (los provee quien integra, Change 1/2/4); el único
  resolver incluido es genérico por hash de archivo.
- Frescura por tiempo (ventanas de antigüedad): es policy (Change 3).
- Verificación de que una `ApprovalRef` exista en `control.json`/ledger (solo validación de forma).
- Copiar payloads de evidencia en la Card.

## Impacto en production-readiness (opcional)
Ninguno: paquete inerte, no instalado, sin cambios de comportamiento en proyectos v0.8.

## Aprobación
- Usuario:
- Fecha:
- Alcance aprobado:
- Versión de artefactos referenciada:
- Cita o descripción fiel de qué se aprobó:

## Motivo de rechazo

## Desacuerdo registrado

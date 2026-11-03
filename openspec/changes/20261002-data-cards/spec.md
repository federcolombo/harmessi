# Spec — 20261002-data-cards

Notación: cada `Rn` tiene criterio de aceptación verificable. Errores de contrato: `CardError` o
`Hallazgo` con códigos `DATACARD-*` (tupla `DATACARD_CODES` propia de `datacard.py`); la Foundation no se
reabre.

## Requisitos

### A. Paquete y dependencias (R1–R4)
**R1** `datacard.py` y `resolvers.py` viven en `tools/cards/`, solo stdlib, importan únicamente
`core`/`assess` del mismo paquete. Ni `datasources`, `qualityevidence`, `datacontracts`, `modelquality`,
`autonomy`, `leadrun`, `reporting` ni `ds_init` se importan desde código de producción de `cards`
(regla 13). Los tests SÍ construyen objetos reales de esos paquetes.
**R2** Sin cambios en `ds_guard.py`, `ds_init/*` (incl. `MANIFEST`, `CAPABILITIES_CONOCIDAS`,
`EXCLUSIONES_PERMANENTES`), Doctor, `autonomy`, `STOP_CATALOG`, `leadrun`, `nbrunner`.
**R3** Extensión aditiva de la Foundation, justificada como foundation-level (aplica a toda Card, no solo
Data Cards): `assess.write_card(path, card, clock=None, *, validate_body=None, exclusive=False)`;
con `exclusive=True` falla con `CARD-IO-ERROR` si el archivo existe y no lo sobrescribe (creación
atómica sin carrera: `os.link`/`O_EXCL` o chequeo previo + `os.replace` documentado). Default intacto.
**R4** Todas las pruebas de Change 0 pasan sin editarse.

### B. Definición de la Data Card (R5–R14)
Una Data Card es un `CardEnvelope` con `card_kind="data_card"`, `kind_schema_version=1`.
**R5 — Identidad.** `card_id` = identidad estable del data product lógico (patrón de Change 0);
`subject` = id lógico del data product (mismo patrón, sin rutas). La *revisión* de la Card es
`revision_id()` (`card_id__hash12`); es independiente de la revisión de cualquier observación de fuente.
**R6 — `body` (versión 1).** Claves cerradas, todas validadas estrictamente (clave desconocida →
`DATACARD-UNKNOWN-KEY`, salvo `x_*`):
- `description` (str no vacío, obligatorio): propósito/qué es.
- `source_refs` (lista no vacía, obligatorio): ver R7.
- `business_meaning`, `population`, `unit_of_analysis`, `derivation_note` (str opcionales; descriptivos,
  NO son un modelo de dominio ni linaje).
- `time_scope` (objeto opcional; claves opcionales `as_of`, `cutoff`, `period_start`, `period_end`,
  strings ISO-8601 fecha o datetime; descriptivo/declarado).
- `stewardship` (objeto opcional `{owner: str, steward: str?}`; roles/equipos, **nunca emails ni datos de
  contacto personal**: se rechaza `@` como en `validar_usuario_sin_email`).
- `contract_refs` (lista opcional): ver R9.
- `quality_evidence_ids` (lista opcional de `evidence_id` de kind `quality_evidence`).
- `intended_uses`, `out_of_scope_uses`, `known_limitations` (listas opcionales de str no vacíos).
- `extensions`: claves `x_*` en cualquier objeto del body.
Nada más es obligatorio (la governance progresiva entra en Change 3).
**R7 — `source_refs[]`** (1..N). Cada elemento: `source_ref_id` (id lógico local único), `source_id`
(patrón `SOURCE_ID_PATTERN`; fuente lógica de v0.8), `role` (opcional, patrón `ROLE_PATTERN` libre de v0.8,
sin enum; el SDD sólo sugiere `primary`/`enrichment`/`derived_input` como convención documentada),
`observation_evidence_id` (obligatorio: `evidence_id` de un `EvidenceRef` de la Card con
`kind="source_observation"`), `provenance_evidence_id` (opcional: `EvidenceRef` `source_provenance`),
`time_scope` (opcional, misma forma que R6). La Data Card NO copia campos de `SourceObservation`,
`SourceProvenance` ni esquema/profiling: sólo los referencia por pin.
**R8 — Consistencia source↔pin.** Para cada `source_ref`: la evidencia referida existe en
`card.evidence` y es del kind esperado; `evidence.ref_id` empieza con `source_id + "__"` (id lógico
coherente con el id de observación de v0.8); `source_ref_id` y `source_id` únicos donde corresponde
(mismo `source_id` puede aparecer varias veces sólo con `source_ref_id` distinto, p. ej. otro período).
Violación → `DATACARD-SOURCE-REF-INCONSISTENT`.
**R9 — `contract_refs[]`.** Cada elemento: `contract_id` (patrón de id), `version` (semver X.Y.Z),
`declaration_evidence_id` (EvidenceRef `harmessi_contract` con `ref_id == contract_id + "@" + version`),
`result_evidence_ids` (lista opcional de EvidenceRef `data_contract_result`). Data Card ≠ Data Contract:
sólo cita; no incluye ni duplica campos, constraints ni reglas.
**R10 — Evidencia = `card.evidence` de la Foundation.** Todo pin vive en `card.evidence`
(`EvidenceRef`); el body sólo lo referencia por `evidence_id`. Referencia a un `evidence_id` inexistente →
`DATACARD-DANGLING-EVIDENCE`.
**R11 — Afirmaciones humanas.** Las afirmaciones no empíricas (p. ej. «el dueño es X») se expresan con
`HumanAttestation` (`declared`/`anchored` estructural, sin verificación contra ledger; Change 4) y
`Claim`s. El texto libre del body no es evidencia.
**R12 — Sin rutas físicas.** Ningún string del body ni de `source_refs` puede ser ruta absoluta, contener
`\`, DSN/URL con credenciales (reglas de portabilidad de Change 0 aplicadas a todos los strings de
identificadores/roles/locators). `locator` de pins: relativo POSIX.
**R13 — Validador de body.** `validate_data_card_body(card_or_body, evidence)` es el `validate_body` hook
de Change 0 (firma compatible: se provee una función `body_validator_for(card)` o equivalente que cierre
sobre la evidencia de la Card); fail-closed: cualquier excepción/forma inválida →
`CARD-BODY-INVALID`/`DATACARD-*`. Nunca lanza fuera de `CardError`.
**R14 — Constructor/versión.** `DATA_CARD_KIND_SCHEMA_VERSION = 1`; `kind_schema_version` distinto →
`DATACARD-SCHEMA-UNSUPPORTED` (fail-closed).

### C. Requisitos de completitud (R15–R17)
**R15 — `requirements_for(card)`** devuelve `Requirement`s DERIVADOS de las `source_refs`:
por cada fuente, `source:<source_ref_id>` (`required`, `accepts=("observed",)`,
`accepted_kinds=("source_observation",)`): una fuente sin claim soportado por su observación fresca deja la
Card `incomplete`; una observación cambiada la deja `stale`. Además `ownership` (`recommended`,
`accepts=("attestation",)`, `min_attestation_kind="declared"`) y, si hay `contract_refs`,
`contract:<contract_id>` (`recommended`, `accepts=("observed",)`,
`accepted_kinds=("harmessi_contract","data_contract_result","quality_evidence")`).
**R16** Los requisitos NO se persisten en la Card (derivados en cada evaluación). Un `Claim` que cubra una
fuente tiene `requirement_id == "source:<source_ref_id>"` y `supports` ⊇ {observation evidence id}.
**R17 — Una atestación nunca satisface un requisito empírico** (`source:*`, `contract:*`): se verifica con
tests (herencia de R24 de Change 0).

### D. Resolvers (R18–R27) — `resolvers.py`
Todos devuelven `assess.Resolution`; nunca lanzan (fail-closed: cualquier error → `unverifiable`).
**R18 — `source_observation`.** Lee `.harmessi/observations/<dir>/observation.json` con `json` (sin
importar `datasources`). `ref_id = <source_id>__<hash12>`. Calcula `content_sha256` = sha256 del JSON
canónico (idéntico a `datasources.core.content_sha256`) del dict **sin `provenance.generated_at`**.
**R19 — Semántica de stale por fuente (decisión de diseño).** El resolver compara el pin contra la
observación **vigente más reciente del mismo `source_id`** (máximo `provenance.generated_at`; desempate
por nombre de directorio): hash vigente ≠ pin → `found` con `current_sha256` distinto → **stale**. Si el
`source_id` no tiene ninguna observación → `missing`. Una re-observación con contenido idéntico produce
el mismo id y queda `fresh`. Una observación cambiada NO actualiza la Card: la deja stale hasta reemitirla.
**R20 — Integridad.** Un `observation.json` ilegible o cuyo `source_id` interno ≠ el del directorio →
`unverifiable`. Rechaza ids con `..`, separadores o rutas absolutas.
**R21 — `source_provenance`.** Misma ubicación; `member="provenance"`; hash = sha256 canónico del
sub-objeto `provenance` sin `generated_at`; misma semántica de vigencia por `source_id`.
**R22 — `harmessi_contract`.** Lee el archivo de contrato en `locator` (relativo, portable, dentro de
`repo_root`); `ref_id = <contract_id>@<version>` debe coincidir con el contenido; hash = sha256 canónico
del dict del contrato (idéntico a `DataContract.content_sha256()`; test de paridad con un contrato real).
**R23 — `quality_evidence` y `data_contract_result`.** Leen
`.harmessi/quality/<evidence_id>/manifest.json`; verifican que el hash persistido coincide con el
recomputado (sha256 canónico excluyendo `generated_at` y `content_sha256`; paridad con
`QualityEvidenceManifest.content_sha256()`); discrepancia → `unverifiable` (integridad rota).
`data_contract_result` exige además `subject_kind == "data_contract_evaluation"` (alias específico de
`quality_evidence`); otro subject → `unverifiable`. Manifest ausente → `missing`.
**R24 — `default_resolvers(repo_root)`** devuelve el mapa `kind → resolver` para los kinds de R18–R23.
Los demás kinds siguen sin resolver (→ `unverifiable`).
**R25 — Sin escritura** y sin red; sólo lectura bajo `repo_root`; rutas validadas dentro de `repo_root`
(sin `..`, symlinks que escapan → `unverifiable`).
**R26 — Sin holdout**: los resolvers sólo leen los directorios de evidencia indicados y el archivo de
contrato del locator; nunca datos de proyecto (`data/`).
**R27 — Evidencia no portable entre clones (limitación documentada):** `.harmessi/` está untracked por
defecto; en un clon nuevo los pins quedan `missing` (→ `incomplete`, fail-closed) hasta re-observar
(`ds_guard source observe`) y regenerar evidencia; contenido idéntico reproduce el mismo id.

### E. Ubicación física y ownership (R28–R32)
**R28 — Ubicación elegida:** `governance/cards/data/<card_id>.json`, relativa a la raíz del proyecto.
Justificación en design D7. `card_path(project_root, card_id)` valida `card_id`, construye la ruta
relativa bajo `project_root` y rechaza escapes; no escanea directorios.
**R29 — Project-owned.** `governance/` no está en `MANIFEST`, no entra en `.ds_init/control.json`
`archivos` y por tanto crear/editar/borrar una Card nunca produce `HARMESSI-DRIFT*` (test con Doctor
real sobre un proyecto de prueba).
**R30 — Colisión fail-closed.** `write_data_card(project_root, card, *, replace=False)`: crea
directorios, y con `replace=False` falla (`exclusive=True`, R3) si el archivo existe; con `replace=True`
exige que el archivo exista y que su `card_id` interno coincida (nunca sobrescribe una Card de otra
identidad ni un archivo ajeno). Un archivo no-Card en esa ruta → error, no overwrite.
**R31** Una Card editada legítimamente = nueva revisión del mismo `card_id` (cambia `revision_id()`),
controlada por Git del proyecto; la Card no guarda historial de revisiones.
**R32** Ninguna función de este Change crea el directorio `governance/` al importar; sólo
`write_data_card` lo crea al escribir.

### F. Serialización y evaluación (R33–R36)
**R33** Serialización/`revision_id`/`evaluate_file` de Change 0 se reutilizan sin cambios; la Data Card
serializada es determinista (mismo objeto → mismos bytes), round-trip→`evaluate` idéntico.
**R34** `evaluate_data_card(card_or_path, repo_root, clock=None)` = `evaluate`/`evaluate_file` con
`requirements_for`, `default_resolvers(repo_root)` y el validador de body cableados (azúcar sin lógica
nueva).
**R35** Archivo mal formado, clave de body desconocida, `kind_schema_version` ajeno,
`source_refs` vacío, evidencia colgante → `invalid` (nunca excepción cruda, nunca PASS).
**R36** Precedencia `invalid > stale > incomplete > complete` heredada; una fuente con observación
cambiada ⇒ `stale`; sin observación ⇒ `incomplete`.

### G. Inercia y compatibilidad (R37–R40)
**R37** Sin Data Cards no cambia nada: suites de v0.6–v0.8 y de Change 0 verdes sin editarse.
**R38** Tests de inercia: `STOP_CATALOG` intacto; `MANIFEST` sin `cards`/`governance`;
`CAPABILITIES_CONOCIDAS == ("predictive_modeling",)`; sin `data_cards` en `ds_init`/`autonomy`/`harmessi`.
**R39** `anchored` sigue siendo estructural; ningún mensaje afirma verificación.
**R40** La documentación (ARCHITECTURE regla 13/§8, roadmap v0.9, deuda v0.10) refleja el alcance real.

## Criterios de aceptación (Given/When/Then)
- Given una Data Card con 1 fuente real (observación generada con `datasources`) y claim que la soporta →
  `complete` (con `ownership` recomendado ausente → WARN, no bloquea).
- Given 3 fuentes (2 observadas + 1 sin observación) → `incomplete`, requisito de la tercera `missing`/
  `unresolvable`.
- Given una re-observación con contenido distinto del mismo `source_id` → esa fuente `stale` ⇒ Card
  `stale`; con contenido idéntico ⇒ `fresh`.
- Given observación con hash pinneado alterado en el archivo → `unverifiable`/`stale`, nunca `fresh`.
- Given contrato real + manifest de `qualityevidence` real → fresh; contrato modificado → stale; manifest
  inexistente → missing; manifest adulterado → unverifiable.
- Given requisito `source:*` y sólo una `HumanAttestation` → `untrusted_type`.
- Given `declared` y `anchored` estructural → válidas; sin afirmar verificación.
- Given dos revisiones de la Card sobre la misma observación → `revision_id` distinto, mismo pin.
- Given Card en `governance/cards/data/` y Doctor real → sin drift; archivo existente → `write_data_card`
  falla sin sobrescribir.
- Given ruta absoluta/DSN/`\` en `source_refs`/`locator` → rechazo `CARD-LOCATOR-NOT-PORTABLE`/`DATACARD-*`.

## Unidad de análisis / grain (condicional)
No aplica a este Change (la Data Card sólo transporta `unit_of_analysis` como descripción).

## Cutoff / information boundary (condicional)
No aplica (sin features ni modelado). Los resolvers no leen datos de proyecto (R26).

## Baseline (condicional)
No aplica.

## Métrica primaria (condicional)
No aplica.

## Métricas secundarias (opcional)
No aplica.

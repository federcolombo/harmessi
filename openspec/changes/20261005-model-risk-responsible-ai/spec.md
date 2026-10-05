# Spec — 20261005-model-risk-responsible-ai

Notación: cada `Rn` tiene criterio de aceptación verificable. Códigos `GOVPOLICY-*` (policy) y `GOVASSESS-*`
(assessment) en tuplas propias; la Foundation y Changes 1–2 no se reabren históricamente (solo extensiones
aditivas, R3–R5).

## Requisitos

### A. Paquete y dependencias (R1–R5)
**R1** `govpolicy.py` y `modelgov.py` viven en `tools/cards/`, solo stdlib; `govpolicy` importa solo `core`;
`modelgov` importa `core`, `assess`, `govpolicy` y `resolvers` (perezoso). Ni `modelquality`,
`qualityevidence`, `datasources`, `datacontracts`, `autonomy`, `leadrun`, `reporting`, `ds_init`, `dsguard`
(salvo el import perezoso de `CheckResult` ya existente en `assess`) desde código de producción.
**R2** Sin cambios en `ds_guard.py`, `ds_init/*` (manifest, capabilities, exclusiones), Doctor, `autonomy`,
`STOP_CATALOG`, `leadrun`, `modelquality`, `qualityevidence`, `datacontracts`, `datasources`, `reporting`,
`dsguard.maturity`, `guardrails.json`. Los niveles de este Change NO leen ni escriben
`.harmessi/project.json`.
**R3 — Extensión aditiva de vocabulario (foundation-level):** `core.CARD_KINDS` += `governance_assessment`
(3 kinds); `core.OBSERVED_KINDS` += `model_card`, `governance_policy`, `evidence_document` al final (16
kinds). Justificación: son artefactos/primitivas citables por cualquier Card (Card pineada, documento de
policy, documento fijado por hash).
**R4** `resolvers.default_resolvers` pasa a resolver además `model_card`, `governance_policy`,
`evidence_document` (15 kinds; solo `report_artifact` sin resolver).
**R5** Tests de Changes 0–2 pasan salvo los ajustes mínimos de conteo/tablas (CARD_KINDS, OBSERVED_KINDS,
default map, hermanos permitidos), documentados en verification.md. `ModelCard` v1 y `DataCard` no cambian
(`test_claves_rai_rechazadas` sigue verde).

### B. Artefacto, identidad y relación con la Model Card (R6–R12)
**R6 — Artefacto separado.** `ModelGovernanceAssessment` = `CardEnvelope` con
`card_kind="governance_assessment"`, `kind_schema_version=1`. NO se agrega ningún campo de riesgo/RAI a
`ModelCard` ni a `DataCard`. Se usa `CardEnvelope` como sobre de documento de governance (identidad,
evidence, attestations, claims, serialización, revisión, hash) sin heredar su semántica documental.
**R7 — Subject.** Toda evaluación aplica a UNA Model Card concreta: el body exige `model_card_ref
{evidence_id}` → `EvidenceRef` de la Card con `kind="model_card"`, `ref_id == <model_card_id>__<12 hex>`
(revisión de la Model Card), hash12 == `content_sha256[:12]` del pin; `locator` opcional ==
`governance/cards/model/<model_card_id>.json`. No existe evaluación de un `model_id` sin versión ni se copia
la Model Card.
**R8 — Identidad.** `card_id` del assessment == `model_card_id` de la Model Card evaluada (derivable de
`ref_id`); `subject == model_id` (decodificado con `modelcard.decode_model_card_id` equivalente del módulo,
sin importar `modelcard`: se duplica la regla con test de paridad). Violación → `GOVASSESS-IDENTITY-MISMATCH`.
Un assessment por Model Card (versión de modelo); modelo versión N+1 ⇒ otra Model Card ⇒ otro assessment.
**R9 — Revisión.** `revision_id()` = revisión documental del assessment. El `risk_level` declarado, la
policy usada (id/versión/hashes) y la Model Card pineada son campos explícitos del body (no se infieren), de
modo que cambiarlos es una edición visible de la revisión y no se confunde con una nueva versión de modelo.
**R10 — Historial.** Una policy nueva NO reescribe un assessment histórico: el assessment vigente pinea su
policy; si la policy efectiva recomputada difiere, el assessment queda `stale` (R50) hasta que se reemita
explícitamente. El historial vive en Git del proyecto; Harmessi no guarda revisiones.
**R11** No hay registry ni índice de modelos/assessments.
**R12** `kind_schema_version` distinto de 1 → `GOVASSESS-SCHEMA-UNSUPPORTED` (fail-closed).

### C. Contrato de policy (`govpolicy.py`) (R13–R20)
**R13 — Vocabularios cerrados.** `LEVELS = ("low","medium","high")` (sin `critical`, scores ni
`unassessed`: la ausencia de nivel NO es un nivel). `DIMENSIONS = ("fairness","explainability","privacy",
"security","accountability","human_oversight")`. Un test de paridad fija que `LEVELS` coincide con
`dsguard.maturity.RISK_LEVELS` sin importarlo en producción.
**R14 — `LevelSpec`:** `severity ∈ {required, recommended}`; `accepts ⊆ {observed, attestation}` no vacío;
`accepted_kinds` (opcional, ⊆ `OBSERVED_KINDS`; `None` = todos los kinds de evidencia permitidos);
`min_attestation_kind ∈ {declared, anchored}`. Se valida estrictamente (clave desconocida → error).
**R15 — `PolicyRequirement`:** `requirement_id` (patrón de ids de la Foundation, ≤ 64, no reservado),
`dimension ∈ DIMENSIONS`, `description` opcional, `levels: {level → LevelSpec}`. Un nivel ausente = el
requisito no aplica en ese nivel.
**R16 — `GovernancePolicy`:** `policy_id`, `version` (entero ≥ 1), `requirements` (ids únicos),
`schema_version=1`. `to_dict`/`from_dict` estrictos; `content_sha256()` = sha256 del JSON canónico
(`core.canonical_json`).
**R17 — Orden de fuerza (única definición de «endurecer»).** Átomos aceptables de un `LevelSpec`: cada kind
observado permitido (los de `accepted_kinds`, o todos los permitidos si es `None`, solo si `accepts`
contiene `observed`), `att_declared` y `att_anchored` (según `min_attestation_kind`, solo si `accepts`
contiene `attestation`). `B es al menos tan fuerte como A` ⇔ `severity(B) ≥ severity(A)`
(`recommended < required`) y `atoms(B) ⊆ atoms(A)`. Un requisito ausente en un nivel es más débil que
cualquier spec presente.
**R18 — Monotonicidad entre niveles.** Toda policy válida cumple, para cada requisito, que el spec de un
nivel superior es al menos tan fuerte como el del inferior y que la presencia no desaparece al subir de
nivel; `GovernancePolicy.validate_monotonic()` devuelve hallazgos; una policy no monotónica es inválida
(`GOVPOLICY-NOT-MONOTONIC`).
**R19 — Kinds permitidos como evidencia observada de governance:** `EXTERNAL_EVIDENCE_KINDS = evidence_document,
execution_record, observed_metric, baseline_reference, model_quality_result, drift_evidence`. `report_artifact`
queda excluido mientras no tenga resolver.
**R20 — Sin lenguaje de cumplimiento.** Ningún texto/código de `govpolicy`/`modelgov` afirma conformidad con
EU AI Act, NIST, ISO, GDPR ni leyes (test de texto).

### D. Policy base de Harmessi v1 — mínimo DOCUMENTAL (R21–R24)
**R21** `BASE_POLICY` es una constante de código: `policy_id="harmessi-base"`, `version=1`, hash
determinista (`BASE_POLICY_SHA256`, congelado por test con hex literal). Define mínimos de
documentación/evidencia, NO mínimos éticos sustantivos.
**R22 — Matriz base v1** (`R` = required, `r` = recommended, `–` = no aplica; «A*» = atestación `declared` o
`anchored`; «A⚓» = atestación `anchored`; «EXT» = `EXTERNAL_EVIDENCE_KINDS`):

| requirement_id | dimensión | low | medium | high |
|---|---|---|---|---|
| `accountability_risk_declaration` | accountability | R · A* | R · A* | R · A⚓ |
| `accountability_owner` | accountability | R · A* | R · A* | R · A⚓ |
| `human_oversight_process` | human_oversight | – | r · A*/EXT | R · A⚓/EXT |
| `fairness_evidence` | fairness | – | R · A*/EXT | R · EXT |
| `explainability_evidence` | explainability | – | r · A*/EXT | R · A⚓/EXT |
| `privacy_evidence` | privacy | r · A*/EXT | R · A*/EXT | R · A⚓/EXT |
| `security_evidence` | security | r · A*/EXT | R · A*/EXT | R · A⚓/EXT |

Regla de construcción: low ⊆ medium ⊆ high en presencia y fuerza (R17/R18 verificadas por test sobre
`BASE_POLICY`). «Evidencia» significa: existe, es del tipo exigido y está íntegra/fresca; Harmessi NO evalúa
su contenido ni su conclusión (ej. `fairness_evidence` con un `evidence_document` íntegro NO dice que el
modelo sea justo).
**R22b — Matriz APROBADA Y CONGELADA por el autor (2026-10-05).** Es un baseline de DOCUMENTACIÓN/EVIDENCIA:
no es una definición universal de riesgo ético, no es un framework de compliance ni un juicio de que el
modelo sea fair/seguro/privado. Se congela como `policy_id="harmessi-base"`, `version=1` y hash canónico
(`BASE_POLICY_SHA256`, vector literal en tests). NO se modifica durante la implementación para hacer pasar
tests; cualquier cambio posterior a la matriz ⇒ NUEVA versión de policy (R24).
**R23** `accountability_owner`: atestación estructurada de responsable (rol/equipo; sin emails ni contacto
personal). `human_oversight_process` puede apoyarse en una atestación `anchored` cuya `approval_ref` cite un
`ApprovalRef`, o en `execution_record`/`evidence_document`; NO crea checkpoints ni toca `approval_mode`
(D6).
**R24** La matriz es un default conservador y reemplazable por endurecimiento; cambiarla requiere nueva
`version` y nuevo hash (los assessments existentes pasan a `stale`, R50).

### E. Endurecimiento de proyecto y merge monotónico (R25–R31)
**R25 — Documento de endurecimiento** (`HardeningDocument`, JSON neutral; la lectura desde config/archivo es
Change 4): `{schema_version:1, policy_id, base_version, risk_floor?, overrides:[{requirement_id, levels:{...}}],
additional:[PolicyRequirement]}`. `content_sha256()` canónico.
**R26** `merge(base, hardening) → EffectivePolicy` (puro, determinista, fail-closed): `policy_id` y
`base_version` deben coincidir con la base (si no → `GOVPOLICY-BASE-MISMATCH`).
**R27 — Monotonicidad (obligatoria).** Para cada override, el spec resultante de CADA nivel debe ser al menos
tan fuerte (R17) que el de la base (o la base ausente en ese nivel); NO se puede: bajar `risk_floor`
(solo subirlo; `risk_floor` es un nivel mínimo), convertir `required` en `recommended`/ausente, ampliar
`accepts`/`accepted_kinds`/bajar `min_attestation_kind`, eliminar un requisito o una dimensión base, reducir
el nivel efectivo, ni reutilizar un id base en `additional`. Cualquier violación rechaza TODO el
endurecimiento (`GOVPOLICY-RELAXATION`); nunca se aplica parcialmente.
**R28** Tras el merge la policy efectiva debe seguir siendo monótona entre niveles (R18); si el
endurecimiento rompe eso → `GOVPOLICY-NOT-MONOTONIC`.
**R29 — `EffectivePolicy`:** `policy_id`, `base_version`, `base_sha256`, `hardening_sha256|None`,
`risk_floor|None`, `requirements`, y `effective_sha256` = sha256 canónico de
`{policy_id, base_version, base_sha256, hardening_sha256, risk_floor, requirements}`. Determinista:
mismas entradas ⇒ mismo hash e igual orden.
**R30 — Capas.** Este Change define un único nivel de endurecimiento (proyecto). La restricción local
(`local-overrides`) y la lectura de config son Change 4 y deben reutilizar `merge` (una capa más estricta
encima, mismas reglas). `guardrails.json` no participa (D5).
**R31** Nivel efectivo = `max(declarado, risk_floor)`; un nivel declarado menor que el `risk_floor` no
relaja: se evalúa con el nivel efectivo y se agrega el hallazgo `GOVASSESS-RISK-BELOW-FLOOR` (assessment
`incomplete`).

### F. Body y declaración de `risk_level` (R32–R38)
**R32 — Body cerrado** (clave desconocida → `GOVASSESS-UNKNOWN-KEY`, salvo `x_*` validados contra
rutas/DSN): `model_card_ref` (obligatorio, R7); `policy_ref` (obligatorio): `{base_policy_id, base_version,
base_sha256, effective_sha256, hardening_evidence_id?}`; `risk_declaration` (opcional): `{level,
attestation_id}`; `dimensions` (opcional): objeto con claves ⊆ `DIMENSIONS`, cada una `{context?: str,
limitations?: [str], not_applicable?: [{requirement_id, rationale, attestation_id}]}`; `notes` (str opcional).
NO existen campos `fair`, `status`, `passed`, `score`, `risk_assessment_result` ni equivalentes (rechazados).
**R33 — Declaración de riesgo.** El `risk_level` es una declaración humana/proyecto: `risk_declaration.level
∈ LEVELS` + `attestation_id` de una `HumanAttestation` de la Card cuyo `claim` sea exactamente
`risk_level=<level>`. No hay clasificador, cuestionario ni inferencia. `declared` o `anchored` estructural
según el requisito `accountability_risk_declaration` del nivel (en high exige `anchored`); la resolución real
del `ApprovalRef` es Change 4.
**R33b — La misma atestación satisface el requisito de declaración (sin duplicar).** La atestación
`risk_level=<level>` PUEDE ser el soporte de `accountability_risk_declaration` si cumple el trust mínimo del
nivel efectivo (low: `declared`; high: `anchored`); no se exige una segunda atestación redundante.
`accountability_owner` sigue siendo un requisito distinto con su propia atestación.
**R33c — Declaración inequívoca (fail-closed).** Se examinan TODAS las atestaciones de la Card cuyo `claim`
coincide con `^risk_level=(low|medium|high)$`. 0 válidas ⇒ `incomplete` (R34). Varias con el MISMO nivel ⇒ se
deduplican determinísticamente (no es error). Varias con niveles DISTINTOS ⇒ `invalid`
(`GOVASSESS-RISK-DECLARATION-CONTRADICTORY`): nunca se elige el máximo, la más reciente ni la primera. Si el
nivel de `risk_declaration.level` difiere del de la(s) atestación(es) ⇒ `invalid`. `max(declarado, risk_floor)`
(R31) se aplica DESPUÉS de resolver una única declaración válida.
**R34 — Ausencia de nivel.** Sin `risk_declaration`: el requisito `accountability_risk_declaration` queda
insatisfecho y el assessment `incomplete` (se informa el nivel efectivo como `max(floor, low)` solo a
título informativo). Nunca hay PASS por ausencia ni un nivel por defecto «aceptado».
**R35 — `policy_ref`.** Debe coincidir con la policy efectiva recomputada (R50). El `hardening_evidence_id`
apunta a un `EvidenceRef` `governance_policy` (R56) de la Card.
**R36 — No aplicabilidad (`not_applicable`).** Solo para requisitos cuya severidad efectiva sea
`recommended` en el nivel efectivo, con `rationale` no vacío y una atestación (`declared` suficiente) que la
respalde. Un requisito `required` NO puede declararse N/A (`GOVASSESS-NA-NOT-ALLOWED`; assessment
`invalid`); tampoco una dimensión completa si contiene algún requisito `required`. N/A no es un waiver
universal: las excepciones a requisitos base son governance explícita futura.
**R37 — Dimensiones** (`fairness`, `explainability`, `privacy`, `security`, `accountability`,
`human_oversight`): cada una agrupa los requisitos de la policy con esa dimensión; el contexto/limitaciones
son descriptivos (no evidencia). Cada dimensión tiene estado DERIVADO (R49).
**R38 — Sin estado editable.** El archivo no contiene `status`/`governance_completeness`; `from_dict`
rechaza esas claves.

### G. Evidencia, atestaciones y claims (R39–R45)
**R39 — Dos clases (D2).** Observada/de sistema = `EvidenceRef` real; humana/proceso = `HumanAttestation`
(`declared`/`anchored` estructural). Una atestación NO satisface un requisito cuyo spec no acepte
`attestation`, ni uno cuyo `min_attestation_kind` supere la suya.
**R40 — Requisitos derivados (no persistidos)** por nivel efectivo: (a) estructurales
`model_card_pin` (required, `observed`, kind `model_card`) y, si hay endurecimiento citado,
`policy_hardening_pin` (required, `observed`, kind `governance_policy`); (b) los de la policy efectiva activos
en el nivel efectivo (los `–` no se derivan). Ids de requisito = ids de la policy; los estructurales están
reservados.
**R41 — Aislamiento de claims (lección B1).** `supports` de un claim con `requirement_id` solo puede contener
ids existentes en la Card; `model_card_pin` y `policy_hardening_pin` exigen `supports == (eid,)`;
`accountability_risk_declaration` exige que `risk_declaration.attestation_id ∈ supports`. Un `requirement_id`
que no sea estructural ni de la policy efectiva → `GOVASSESS-CLAIM-SUPPORT-INCONSISTENT` (Card `invalid`).
Claims sin `requirement_id` son libres.
**R42 — Regla «todo lo citado debe estar respaldado y vigente».** Un requisito está `satisfied` solo si TODOS
los soportes de sus claims son aceptables para su spec Y frescos; un soporte inaceptable ⇒
`untrusted_type`; un soporte `stale` ⇒ `stale`; `unresolvable`/`unverifiable` ⇒ ese estado. Ningún soporte
fresco oculta el estado de otro (a diferencia del ANY de la Foundation; implementado en el evaluador
propio, reutilizando `assess.evaluar_evidencia` y las constantes de estado).
**R43 — Matriz de estados por requisito:** `satisfied`, `not_applicable` (R36), `missing` (sin claim),
`empty` (claim sin soportes), `untrusted_type`, `stale`, `unresolvable`, `unverifiable`.
**R44 — Tipos de evidencia reutilizados:** `model_card`, `data_card`, `model_quality_result`,
`model_quality_policy`, `observed_metric`, `baseline_reference`, `drift_evidence`, `execution_record`,
`harmessi_contract`/`data_contract_result`, `evidence_document` y cualquier `EvidenceRef` válido, según lo
que acepte cada spec.
**R45 — `evidence_document`:** primitiva neutral «documento fijado por hash»: `locator` relativo portable a un
archivo del proyecto, `content_sha256` = sha256 de los BYTES (`sha256/bin/v1`), `ref_id` = identificador
lógico libre (patrón de ids). Respalda reportes externos de fairness/explicabilidad/privacidad/seguridad sin
que Harmessi los interprete: acredita existencia e integridad del documento, NO su contenido ni su
conclusión. **Semántica precisa (aprobada por el autor):** `evidence_document` demuestra (1) existencia del
documento, (2) integridad de bytes, (3) identidad/pin y (4) frescura/integridad según el resolver. NO
demuestra que el contenido sea correcto, que la metodología sea válida, que un análisis de fairness sea
bueno, que privacy/security estén resueltas ni que una conclusión del documento sea verdadera. Un requisito
que acepta `evidence_document` solo permite afirmar «existe evidencia documental íntegra vinculada a este
requisito», nunca «Harmessi verificó sustantivamente el contenido». Esto debe figurar en los docstrings del
resolver/módulos y en `verification.md`. No hay parsing semántico de PDFs/docs/reportes.

### H. Evaluación (R46–R55)
**R46** `evaluate_governance_assessment(card_or_path, repo_root, *, base=BASE_POLICY, clock=None)` devuelve
`GovernanceAssessment` (frozen): `governance_completeness`, `effective_level`, `declared_level`,
`risk_floor`, `policy` (ids/versiones/hashes pineados y recomputados), `dimensiones` (por dimensión: estado
derivado y sus requisitos), `requisitos`, `evidencias`, `hallazgos`, `nota`, y `a_dict()` determinista.
**R47 — Nombre y semántica.** El campo es `governance_completeness` ∈ {`invalid`, `stale`, `incomplete`,
`complete`} con la precedencia de la Foundation `invalid > stale > incomplete > complete`. `complete` =
«todos los requisitos `required` de la policy efectiva están satisfechos y los pins estructurales están
íntegros». `a_dict()["nota"]` y los mensajes dicen explícitamente que NO equivale a aprobación ética, de
justicia, seguridad, explicabilidad, cumplimiento ni aptitud para producción.
**R48** Estado derivado en cada evaluación: evidencia → requisito → dimensión → assessment. Nada se persiste.
**R49 — Estado por dimensión:** derivado de los requisitos `required` de esa dimensión con la misma
precedencia (stale > incompleto > completo); una dimensión sin requisitos aplicables en el nivel efectivo se
informa `not_required` (no es PASS de nada).
**R50 — Staleness conservadora.** (a) `model_card_ref` pin con hash distinto (Model Card revisada) ⇒
`stale`; ausente ⇒ `unresolvable` (incomplete). (b) `policy_ref.base_sha256` ≠ `BASE_POLICY_SHA256` actual o
`effective_sha256` recomputado ≠ pineado ⇒ `stale` (`GOVASSESS-POLICY-CHANGED`); (c) endurecimiento citado
que no se puede resolver ⇒ no se puede computar la policy efectiva ⇒ `incomplete` (nunca se evalúa «solo
con la base» por haber desaparecido el endurecimiento). (d) evidencia citada stale ⇒ `stale`. No hay
semántica de «latest».
**R51 — Fail-closed.** Body inválido, kind/versión ajenos, claim inconsistente, N/A de requisito required,
id/identidad inconsistente ⇒ `invalid`; resolvers ausentes/erróneos ⇒ `unverifiable`; ninguna excepción
cruda desde la API pública; ausencia nunca produce `complete`.
**R52 — Salida `CheckResult`:** `required` insatisfecho ⇒ FAIL; `recommended` ⇒ WARN; `complete` ⇒ PASS con
mensaje que incluye la frase de R47; códigos `GOVASSESS-*`. Los mensajes no mencionan autonomía/STOP ni
afirmaciones normativas.
**R53 (D1)** La evaluación NO consulta ni modifica autonomía/`approval_mode`/STOP/runtime; un assessment
`invalid`/`incomplete`/`stale` no bloquea técnicamente nada en v0.9.
**R54 (D6)** Human oversight solo CITA `ApprovalRef`/checkpoints/ledger/`ExecutionRecord` (por atestación
`anchored` o `execution_record`); no crea checkpoints, no modifica `approval_mode`, no duplica el ledger.
**R55** Sin cálculo ni comparación de métricas, ni inferencia de «fair/explainable/private/secure/
accountable/safe/ethical»; la salida solo informa presencia/ausencia/stale/unverifiable y satisfacción de
requisitos explícitos.

### I. Resolvers nuevos (R56–R59) — `resolvers.py`; devuelven `Resolution`, nunca lanzan
**R56 — `governance_policy`:** `ref_id=<policy_id>`; `locator` relativo portable a un JSON de documento de
endurecimiento; `policy_id` interno == `ref_id`; hash = canónico del documento (`hash_document`).
**R57 — `model_card`:** espejo de `data_card` con `governance/cards/model/<card_id>.json`,
`card_kind=="model_card"`; lee con `assess.read_card`; NO reevalúa la Model Card ni su evidencia.
**R58 — `evidence_document`:** lee los BYTES del archivo en `locator` (dentro de `repo_root`, tope de
tamaño, sin symlinks que escapen) y devuelve sha256; ausente ⇒ `missing`.
**R59** `default_resolvers` = 15 kinds.

### J. Ubicación y serialización (R60–R64)
**R60** `governance/model-risk/<card_id>.json` (project-owned, Git, fuera de `.harmessi/` y del manifest, sin
`HARMESSI-DRIFT`); `card_path(project_root, card_id)` valida id y contención.
**R61** `write_governance_assessment(project_root, card, *, replace=False, clock=None)`: valida antes de
tocar el disco; sin overwrite; `replace=True` exige el mismo `card_id`/identidad; archivo ajeno → error sin
sobrescribir; `governance/` solo se crea al escribir.
**R62** Serialización determinista de la Foundation; round-trip→evaluate idéntico; archivo mal formado ⇒
`invalid`.
**R63** Los textos libres (`context`, `limitations`, `rationale`, `notes`, `x_*`) rechazan rutas
absolutas/DSN/credenciales con las reglas de Cards previas; `stewardship`-like contenido sin emails.
**R64** Hash de policy base congelado con vector literal; `effective_sha256` determinista (mismas entradas ⇒
mismo valor, independiente del orden de claves).

### K. Inercia y compatibilidad (R65–R68)
**R65** Sin assessments no cambia nada; suites de v0.6–v0.8 y de Changes 0–2 verdes (salvo R5).
**R66** Inercia: `STOP_CATALOG` intacto; `MANIFEST` sin `cards`/`governance`; `CAPABILITIES_CONOCIDAS ==
("predictive_modeling",)`; `model_governance`/`data_cards`/`modelgov`/`govpolicy` ausentes de `ds_init`,
`autonomy`, `harmessi`, `ds_guard`, Doctor.
**R67** `anchored` sigue siendo estructural; ningún mensaje afirma verificación.
**R68** Sin dependencias nuevas.

## Criterios de aceptación (Given/When/Then)
- Given un assessment low/medium/high con evidencia real ligera y claims propios → requisitos de ese nivel
  derivados; `complete` solo si todos los `required` están satisfechos y los pins íntegros.
- Given ausencia de `risk_declaration` → `incomplete`; given nivel declarado < `risk_floor` → evaluado en
  el piso e `incomplete`.
- Given hardening que baja un requisito, amplía `accepts`, baja el piso o reutiliza un id base → rechazo
  total `GOVPOLICY-RELAXATION`; given hardening que endurece → policy efectiva más estricta y determinista.
- Given `fairness_evidence` en high con solo una atestación → `untrusted_type`/`incomplete`; con
  `evidence_document` íntegro → `satisfied`; con el documento modificado → `stale`.
- Given low con `risk_level=low` `declared` → satisface `accountability_risk_declaration`; given high con
  `risk_level=high` solo `declared` → insatisfecho (requiere `anchored`); given declaraciones con niveles
  distintos → `invalid`; given la misma declaración repetida → deduplicada.
- Given hardening que baja el floor, convierte required en recommended o amplía lo aceptado →
  `GOVPOLICY-RELAXATION` (rechazo total); given hardening que restringe evidencia aceptada, exige `anchored`,
  sube el floor o agrega requisitos → válido.
- Given `fairness_evidence` en high solo con atestación → `incomplete`; con `evidence_document` íntegro →
  satisface la presencia documental (sin claim semántico); con el documento corrupto/modificado →
  `stale`/`unverifiable`.
- Given dos soportes (uno fresco, uno stale) en un mismo requisito → NO satisfecho.
- Given un requisito `required` marcado N/A → `invalid`; `recommended` con rationale+atestación → N/A.
- Given Model Card revisada → assessment `stale`; policy base/hardening cambiada → `stale`.
- Given hardening citado y archivo borrado → `incomplete` (no se cae a la base).
- Given dos pins donde uno es stale y otro fresco bajo el mismo requisito → `stale` (no enmascarado).
- Given `human_oversight_process` apoyado en una atestación `anchored` con `approval_ref` → satisfecho; no
  se crea checkpoint ni cambia ningún modo.
- Given claves `fair`, `status`, `score` en el body → rechazo; `complete` no aparece en el archivo.
- Given el assessment `invalid` → ningún cambio en autonomía/STOP/runtime.

## Unidad de análisis / grain (condicional)
No aplica.

## Cutoff / information boundary (condicional)
No aplica: no se calculan métricas ni features; los resolvers solo leen evidencia indicada, nunca datos de
proyecto ni holdouts.

## Baseline (condicional)
No aplica a datos; la «baseline» aquí es la policy base de documentación (R21–R24), no un modelo de
referencia.

## Métrica primaria (condicional)
No aplica.

## Métricas secundarias (opcional)
No aplica.

# Diseño — 20261005-model-risk-responsible-ai

## Decisión metodológica/técnica

**D1 — Artefacto separado, no campos en ModelCard.** La Model Card documenta una versión de modelo; la
evaluación de riesgo/RAI es una evaluación de governance SOBRE esa Card que puede reemitirse (nueva policy,
nueva evidencia, nuevo nivel) sin falsear que cambió la versión del modelo. El audit confirma que la
separación no contradice nada: `ModelCard` v1 ya rechaza `risk_level` y las claves RAI por contrato y por
test. Elegido: `ModelGovernanceAssessment` con `card_kind="governance_assessment"`.

**D2 — Composición mínima sobre `CardEnvelope`.** Se reutiliza el envelope (identidad, `evidence`,
`attestations`, `claims`, serialización determinista, `revision_id`, hash, `write_card(exclusive)`,
`read_card`) como «sobre de documento de governance». Alternativas descartadas: (a) tipo propio y
serialización paralela (duplica evidence/attestation/hash: prohibido); (b) forzar semántica de «Card» en
nombres de API (se evita: módulos `govpolicy`/`modelgov`, kind propio). Un solo `CARD_KINDS` adicional.

**D3 — Subject = una Model Card concreta, identidad compartida.** El assessment pinea la Model Card
(`model_card` kind, `ref_id=<model_card_id>__<hash12>`) y adopta su `card_id` (identidad de la versión del
modelo). Así modelo v1 y v2 tienen assessments distintos, y no existe evaluación de un `model_id` flotante.
Revisión (`revision_id`) = documento; policy, nivel y Model Card pineada son campos explícitos del body.
Historial = Git del proyecto; la policy se pinea, no se re-evalúa retroactivamente.

**D4 — `risk_level` como declaración, nunca inferencia.** `low/medium/high` (sin `critical`, `unassessed`
ni scores). Se declara con una `HumanAttestation` cuyo claim es exactamente `risk_level=<level>`; la
policy exige `declared` en low/medium y `anchored` (estructural) en high; la verificación real del
`ApprovalRef` es Change 4. Ausencia ⇒ requisito insatisfecho ⇒ `incomplete`. El nivel efectivo es
`max(declarado, risk_floor)`: un proyecto puede subir el piso, nunca bajar.

**D5 — Policy como datos con una definición única de «endurecer».** El monotonic merge del repo solo
existe para vocabularios cerrados de una dimensión; aquí se necesita un orden sobre specs de evidencia.
Se define por inclusión de conjuntos de «átomos aceptables» (kinds observados + clases de atestación) y
severidad (R17): es pequeño, determinista y verificable por test exhaustivo. Sirve para tres controles con
la misma función: monotonicidad entre niveles de la base, relajación por hardening, y consistencia de la
policy efectiva. Todo fallo es fail-closed y rechaza el endurecimiento COMPLETO (nada parcial).

**D6 — Base policy v1: piso DOCUMENTAL conservador.** Siete requisitos en seis dimensiones, progresivos por
inclusión (R22). Principio: lo que se exige es que exista evidencia/atestación respaldada e íntegra, no un
resultado. La fila más normativa es `fairness_evidence` en high (solo evidencia externa observable, sin
atestación): es el único punto donde la base prohíbe que una declaración humana baste, coherente con D2 del
roadmap. Cualquier proyecto puede endurecer; ninguno puede relajar. Es la parte del Change más sensible a
revisión humana: se presenta como tabla en la spec y su cambio implica nueva `version`/hash (R24).

**D7 — Pin de policy en tres partes.** Base (constante de código con `policy_id`, `version`, hash
congelado), endurecimiento (documento de proyecto pineado con `governance_policy`) y policy efectiva
(hash recomputado). El assessment guarda los tres; cualquier cambio ⇒ `stale` explícito. Si el
endurecimiento citado desaparece NO se degrada a «solo base» (sería una vía de evasión): queda
`incomplete`. Descubrir que existe un endurecimiento no citado es plumbing de config → Change 4 (se
registra como requisito: la lectura de config debe ser obligatoria y comparable, no opcional).

**D8 — Evaluador propio con regla «todo lo citado respaldado y fresco».** `assess.evaluate` marca un
requisito `satisfied` con cualquier soporte fresco, lo que permitiría que un soporte fresco oculte uno
stale (el bloqueante B1 de Data Cards en otra forma). Aquí cada requisito de policy puede aceptar varios
tipos, así que se usa la regla estricta R42 en un evaluador propio que reutiliza `assess.evaluar_evidencia`,
los estados `EV_*/REQ_*`, la validación estructural de la Foundation y la precedencia
`invalid > stale > incomplete > complete`. No hay framework paralelo de estados.

**D9 — N/A acotado.** `not_applicable` solo para requisitos efectivamente `recommended`, con rationale y
atestación; nunca para `required`, ni para una dimensión que contenga alguno. No hay waivers: una excepción
a un mínimo base sería governance explícita futura, no un booleano escondido.

**D10 — `evidence_document`: primitiva neutral de evidencia documental.** Sin ella ninguna dimensión RAI
podría respaldarse con observación (el único kind documental, `report_artifact`, no tiene resolver). Se
pinea un archivo del proyecto por sha256 de bytes; Harmessi acredita existencia e integridad, no
contenido. No es scanner ni parser de reportes; evita acoplarse a herramientas de fairness/XAI/privacidad.

**D11 — Fairness/explainability/privacy/security/accountability/oversight.** Seis dimensiones, una por
vocabulario cerrado, cada una con requisitos de policy y descripciones neutras. Fairness y explicabilidad
no suponen features, árboles ni coeficientes; privacy y security no son scanners (no se afirma «privado» ni
«seguro» por ausencia de hallazgos); accountability usa atestaciones de rol/equipo sin emails; human
oversight CITA aprobaciones existentes (D6 del roadmap) sin crear checkpoints ni tocar autonomía.

**D12 — Estado derivado y nombre honesto.** El campo se llama `governance_completeness` y la salida
incluye una nota fija: «complete = requisitos de la policy satisfechos; no implica aprobación ética, de
justicia, seguridad, explicabilidad, cumplimiento ni aptitud para producción». No hay `status`, `fair`,
`passed` ni score persistidos ni aceptados.

**D13 — Ubicación.** `governance/model-risk/<card_id>.json` (misma familia `governance/`, project-owned,
Git, fuera de `.harmessi/` y del manifest; sin drift; sin overwrite; `card_id` = el de la Model Card).

## Archivos previstos
Nuevos: `tools/cards/govpolicy.py`, `tools/cards/modelgov.py`,
`tools/cards/tests/{test_govpolicy,test_modelgov,test_modelgov_location,test_resolvers_gov}.py`,
`tools/tests/test_v09_modelgov_{parity,inert}.py`.
Modificados: `tools/cards/core.py` (+1 `CARD_KIND`, +3 `OBSERVED_KINDS`), `tools/cards/resolvers.py`
(+3 resolvers: `model_card`, `governance_policy`, `evidence_document`), tests de Changes 0–2 afectados por
conteos/tablas (`test_core.py`, `test_evidence.py`, `test_modelcard.py`, `test_datacard.py` si aplica,
`test_v09_cards_neutrality.py`, `test_v09_datacards_inert.py`, `test_v09_modelcards_inert.py`),
`ARCHITECTURE.md` (regla 13/§8), `docs/roadmap/v0.9.md` (progreso).
No se tocan: `ds_guard.py`, `ds_init/*`, Doctor, `autonomy`, `leadrun`, `modelquality`,
`qualityevidence`, `datacontracts`, `datasources`, `reporting`, `dsguard.maturity`, `guardrails.json`.

## Tests previstos (evidencia real ligera de Changes 0–2/v0.7, sin mocks triviales)
Policy: validación de tipos; `BASE_POLICY` monótona por construcción y hash congelado con vector literal;
orden de fuerza (tabla exhaustiva de pares de specs); merge: endurecimiento válido por nivel, relajación
(baja severidad, amplía accepts, baja min_attestation_kind, baja floor, elimina requisito, reusa id base)
⇒ rechazo total, policy efectiva monótona, determinismo/orden de `effective_sha256`. Assessment: low,
medium, high; ausencia de `risk_level`; nivel declarado < floor; Model Card válida / ausente / revisada
(stale); policy pin/versión; policy base o hardening cambiados (stale); hardening citado desaparecido
(incomplete, no base-only); evidencia observada válida / missing / stale / unverifiable con objetos reales
(`evidence_document`, `execution_record`, `observed_metric`, `model_quality_result`, Data Card/Model Card
reales); atestación `declared`/`anchored` válida donde corresponde; atestación intentando suplir un
requisito empírico (fairness high) ⇒ no satisface; fairness sin evidencia requerida; explicabilidad con
documento externo; privacidad con atestación; accountability owner/equipo (rechazo de emails); human
oversight con `approval_ref` y sin creación de checkpoint ni cambio de modo; requisito required N/A ⇒
invalid; N/A de recommended ok; contaminación cruzada (un soporte fresco no oculta uno stale); claims
inconsistentes; estado derivado y no persistido (`status/fair/score` rechazados); serialización
determinista y round-trip→evaluate idéntico; archivo mal formado ⇒ invalid; ninguna inferencia ética
(valores de métricas distintos ⇒ mismo resultado); ubicación/no overwrite/sin drift; resolvers nuevos;
paridad (`LEVELS` vs `maturity.RISK_LEVELS`, canonical hash, reglas duplicadas de id de modelo);
inercia (STOP, manifest, capabilities, ds_guard/Doctor/autonomy); regresión Changes 0–2 y v0.7/v0.8.

## Target (condicional)
No aplica.

## Features permitidas/prohibidas (condicional)
No aplica.

## Estrategia de split/validación (condicional)
No aplica: no se evalúan modelos ni datos.

## Leakage risks (condicional)
No hay datasets ni features. Riesgo análogo de integridad: relajar la policy por la puerta de atrás
(hardening «que baja», N/A, declarar un nivel menor, borrar el hardening, mezclar soportes frescos y
stale, o usar una atestación como evidencia). Mitigaciones: merge monotónico fail-closed, N/A acotado,
`max(declarado, floor)`, hardening citado no degradable, regla R42 y R39.

## Reproducibilidad (opcional)
Sin aleatoriedad; JSON canónico; reloj inyectable.

## Alternativas descartadas
- Campos de riesgo/RAI en `ModelCard` v1 (contrato congelado; mezcla documento con evaluación).
- Policy en `guardrails.json` (D5 del roadmap).
- Un `status` o `fair=true` editable; scores; clasificador automático; cuestionario universal.
- Waivers/excepciones genéricas; `unassessed` como nivel.
- Reusar el ANY-fresh de la Foundation para requisitos multi-tipo (enmascara stale).
- Evaluar con la policy más reciente sin pin (reescribiría la historia).
- Que el hardening ausente degrade a la base.
- Cálculo/lectura de métricas de fairness/explicabilidad o scanners.

## Riesgos
- *Matriz base normativa*: es un default documental y conservador, de lectura obligatoria al aprobar; su
  cambio es explícito y versionado.
- *Plumbing de hardening diferido a Change 4*: un hardening no citado en el assessment no se detecta aquí;
  Change 4 debe volver obligatoria la lectura de config y comparar contra el pin (requisito registrado).
- *Extensión de la Foundation* (+1 kind de Card, +3 kinds observados): aditiva; ajustes mínimos de tests de
  conteo.
- *Falsa sensación de aprobación*: mitigada por el nombre `governance_completeness`, la nota fija y los
  mensajes.
- *`evidence_document` demasiado laxo*: solo acredita integridad de un archivo; la semántica queda en la
  policy de proyecto (hardening) y en las atestaciones.
- *Scope creep a RAI sustantivo*: sin cálculo, sin scanners, sin compliance.

## Decisiones materiales — RESUELTAS por el autor (2026-10-05)
La matriz base v1 (R22) fue APROBADA y CONGELADA como baseline de documentación/evidencia (`harmessi-base`
v1, hash canónico); no se modifica durante la implementación. La misma atestación `risk_level=<level>`
satisface `accountability_risk_declaration` (R33b); declaraciones contradictorias ⇒ `invalid` (R33c);
`evidence_document` solo acredita existencia/integridad del documento (R45); todos los soportes de un
requisito deben ser aceptables y frescos (R42). Change 4: si existe un hardening efectivo y el assessment no
lo cita, debe detectarse (sin heurísticas de filesystem aquí).

## Decisiones materiales (histórico previo a la aprobación)
Ninguna bloqueaba: arquitectura (artefacto separado), vocabulario (`low/medium/high`, seis dimensiones),
monotonicidad, ubicación y semánticas están fijadas por las instrucciones del autor o por contratos
existentes. Se informa para el registro, como lo más sensible de revisar, la **matriz base v1** (R22): es
un piso de documentación decidido por mí con criterio conservador y progresivo; ajustarla es cambiar una
tabla (y la `version`), no el diseño.

## Aprobación humana
<!-- El registro de aprobación (usuario, fecha, alcance, versión de artefactos, cita) es único
por cambio y vive en la sección "Aprobación" de proposal.md — no se duplica acá. -->

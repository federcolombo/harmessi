# Verificación — 20261005-model-risk-responsible-ai

## Resumen ejecutivo
Change 3 de v0.9: **ModelGovernanceAssessment**, un artefacto SEPARADO de la Model Card que evalúa una
Model Card concreta contra una policy pineada y versionada: base mínima de Harmessi por `risk_level`
(`low/medium/high`) + endurecimiento de proyecto monotónico y fail-closed, con seis dimensiones (fairness,
explainability, privacy, security, accountability, human_oversight), evidencia y atestaciones, y completitud
DERIVADA. SDD aprobado por hash el 2026-10-05, con la matriz base v1 aprobada y congelada y las precisiones del
autor incorporadas antes de aprobar (declaración de riesgo única que satisface el requisito, contradicciones ⇒
invalid, semántica de `evidence_document`, todos los soportes). Todas las ejecuciones pasaron por el runtime
gobernado (`ds_guard exec pytest`), aprobadas con `ds_guard exec approve`.

## QUÉ SIGNIFICA `complete` (explícito)
`governance_completeness == "complete"` significa SOLAMENTE: todos los requisitos efectivos de governance
definidos por la policy fueron satisfechos con tipos de soporte aceptables e íntegros, y los pins
estructurales (Model Card, policy) están íntegros. NO significa que el modelo sea fair, ético, seguro, safe,
privado, explicable, production-ready ni compliant. Harmessi no calcula ni infiere nada de eso; no hay
claims de compliance (ni EU AI Act, NIST, ISO, GDPR, ni leyes). La salida lleva una nota fija
(`NOTA_COMPLETENESS`).

## QUÉ DEMUESTRA `evidence_document` (explícito)
Demuestra: existencia del documento, integridad de bytes (sha256), identidad/pin y frescura/integridad según
el resolver. NO demuestra que el contenido sea correcto, que la metodología sea válida, que un análisis de
fairness sea bueno, que privacy/security estén resueltas ni que una conclusión del documento sea verdadera.
Harmessi solo puede afirmar «existe evidencia documental íntegra vinculada a este requisito». No hay parsing
semántico. Los documentos bajo `data/` se rechazan (no se abren datos del proyecto).

## Qué entrega
- `tools/cards/govpolicy.py`: `LEVELS`, `DIMENSIONS`, `LevelSpec`/`PolicyRequirement`/`GovernancePolicy`
  (tipos inmutables, `levels` de solo lectura), orden de fuerza único (`at_least_as_strong`), monotonicidad
  entre niveles, `BASE_POLICY` (`harmessi-base` v1, hash congelado
  `ee6b6188a1db05fbc51b12709e1f4dba4211040d11e3ac8e1ed164ee58ccdb53`), `HardeningDocument`, `merge`
  monotónico todo-o-nada (`GOVPOLICY-RELAXATION`) que acepta también un `EffectivePolicy` como base
  (capas apiladas: Change 4), `EffectivePolicy.effective_sha256()`.
- `tools/cards/modelgov.py`: body cerrado, identidad (el assessment adopta el `card_id` de la Model Card
  pineada), `risk_declaration` por atestación `risk_level=<level>`, claims aislados, evaluador propio con la
  regla «todos los soportes aceptables y frescos», dimensiones, N/A acotado, `GovernanceAssessment`
  (`governance_completeness` ∈ invalid/stale/incomplete/complete), `card_path`, `write_governance_assessment`
  (sin overwrite), `evaluate_governance_assessment`, `a_check_results`.
- Foundation (aditivo): `CARD_KINDS += governance_assessment`; `OBSERVED_KINDS += model_card,
  governance_policy, evidence_document` (16); resolvers para esos tres kinds (15 kinds resolubles,
  `report_artifact` sin resolver); `leer_documento_json`.
- Ubicación `governance/model-risk/<card_id>.json` (project-owned, fuera de `.harmessi/` y del manifest, sin
  drift: probado con `_check_hashes_drift` real). Docs: ARCHITECTURE (regla 13), roadmap v0.9.

## Matriz base v1 (aprobada y congelada; verificada celda por celda contra el spec)
accountability_risk_declaration y accountability_owner: low/medium required atestación, high required anchored;
human_oversight_process: – / recommended atestación|externa / required anchored|externa;
fairness_evidence: – / required atestación|externa / required SOLO evidencia externa (sin atestación);
explainability_evidence: – / recommended / required anchored|externa; privacy_evidence y security_evidence:
recommended / required / required anchored|externa. low ⊆ medium ⊆ high en presencia y fuerza (test).

## Ejecuciones reales
Dirigida: primera corrida 1315 passed / 9 failed (8 por fixtures no monótonas en `test_govpolicy` —la policy las
rechaza correctamente— y 1 por un conteo de Change 2); tras ajustes de tests, review ciclo 1 y ciclo 2:
**1361 passed, 28 skipped, 30893 subtests, 0 failed, pytest exit 0**.

Regresión relevante, lotes SECUENCIALES (exit code real del proceso pytest leído del `ExecutionRecord`):

| Lote | Suite | Resultado | pytest exit |
|---|---|---|---|
| 1 | `tools/tests` (architecture, neutralidad, inercia, paridad, manifest, exec, …) | 1247 passed, 6 skipped, 28446 subtests | 0 |
| 2 | `modelquality`, `qualityevidence`, `datasources`, `datacontracts` (tests) | 511 passed, 150 subtests | 0 |
| 3 | `autonomy`, `leadrun` (tests) | 241 passed, 261 subtests | 0 |
| 4 | `tools/cards/tests` (15 archivos: Foundation, Data/Model Cards, govpolicy, modelgov, resolvers) | 1127 passed, 28 skipped, 2501 subtests | 0 |

**Agregado: 3126 passed, 34 skipped, 0 failed, 31358 subtests passed; 4 lotes; 0 reintentos por memoria.**
Doctor: 27 OK, 1 WARN (working tree con cambios sin confirmar), 0 ERROR. Los skips son tests de symlink.

## Proceso de revisión (2 ciclos, máximo permitido)
- **Ciclo 1:** 0 bloqueantes; los tests centrales NO son tautológicos (verificado por el reviewer);
  matriz idéntica al spec. 3 importantes resueltos: (I1) toda evidencia stale de la Card (citada por
  required/recommended/inactivo/claim libre/huérfana) deja el assessment `stale` (R50d); las huérfanas
  unresolvable/unverifiable no cambian el estado global; (I2) la atestación `risk_level=…` queda RESERVADA
  para `accountability_risk_declaration` (no puede soportar owner, fairness ni claims libres; R33b);
  (I3) hardening no citado: limitación abierta, ver abajo. Menores resueltos: M1 `levels` inmutable, M3
  near-miss de declaraciones de riesgo ⇒ invalid, M4 exclusión de `data/` en `evidence_document`, M5 chequeo
  de hash del hardening al leerlo (TOCTOU ⇒ stale), M6 test vacuo reescrito.
- **Ciclo 2:** 0 bloqueantes; 1 importante cerrado: la exclusión de `data/` podía evadirse en Windows con
  `data./x` o `data /x` (normalización de puntos/espacios finales) ⇒ se normaliza cada segmento y se
  rechazan segmentos terminados en punto/espacio; además la atestación de riesgo reservada tampoco puede
  justificar un N/A.

## Precisiones de contrato por encima del spec aprobado (consistentes con él; el spec no se editó)
- R33b: la atestación de riesgo es EXCLUSIVA de `accountability_risk_declaration` (aislamiento).
- R50(d) se aplica a TODA evidencia de la Card, no solo a la de requisitos required.
- Near-miss: un claim de cualquier atestación que EMPIECE con `risk level`/`risk_level`/`risk-level` seguido
  de `=` o `:` fuera del formato exacto se trata como declaración malformada (invalid, fail-closed). Falso
  positivo acotado aceptado (p. ej. «Risk level: reviewed by committee» como inicio de un claim ajeno).
- `merge` acepta un `EffectivePolicy` como base (capas apiladas), con `risk_floor=None` = heredar y un nivel
  menor = relajación; permite el rechazo de «bajar el piso» que el spec exigía probar.
- `evidence_document` rechaza locators bajo `data/` (anti-leakage del proyecto).

## Ajustes mínimos a tests de Changes 0–2 (documentados)
`test_core.py` (CARD_KINDS 3), `test_evidence.py` (13→16 kinds), `test_resolvers.py` y `test_modelcard.py`
(mapa de resolvers 12→15), `test_resolvers_model.py` (conteo de kinds), `test_v09_modelcards_inert.py`
(slices de OBSERVED_KINDS y hermanos permitidos), `test_v09_datacards_inert.py` y
`test_v09_cards_neutrality.py` (hermanos permitidos). Ninguna aserción de fondo se debilitó; ModelCard v1
sigue rechazando `risk_level` y las claves RAI.

## Limitaciones conocidas y deuda (no bloqueantes)
- **Hardening no citado (I3):** si el assessment omite `hardening_evidence_id` (o se borra del body y se
  re-pinea la policy efectiva base-only), queda `complete` evaluado solo con la base. Requisito de Change 4:
  la lectura de config/hardening debe ser obligatoria cuando existe y compararse con el pin del assessment
  (sin heurísticas de filesystem aquí).
- Los pins huérfanos no citados solo afectan el estado global si están stale.
- `leer_documento_json` no aplica la exclusión de `data/` (lee solo documentos JSON de policy indicados
  explícitamente).
- `PolicyRequirement.levels` es inmutable por API pública (no a prueba de acceso deliberado a un atributo
  privado); un `EffectivePolicy` construido a mano no se contrasta con la base real (el flujo usa `merge`).
- La matriz base v1 es un piso de documentación; cambiarla exige nueva `version`/hash y deja los assessments
  existentes `stale`.
- Un claim de accountability que EMPIECE con «Risk level:» es tratado como declaración malformada (ver arriba).
- `anchored` sigue siendo estructural (resolución real del `ApprovalRef` en Change 4); las aprobaciones son
  declaraciones registradas, no firmas ni prueba de autoría (deuda v0.10).
- Change 4: lectura de project governance config, hardening obligatorio y comparación contra el pin, resolución
  real de `anchored`, CLI, Doctor, reporting, capabilities (`data_cards`/`model_governance` opt-in;
  `model_governance` sin `predictive_modeling` inválido), integración de `governance/` con Doctor/exclusiones.
  v0.10: approval-origin authenticity, LF/CRLF hashing, authorized-scope UX, composable skills/
  domain-modeling, one-writer.
- Limitaciones de Data Cards y Model Cards heredadas sin cambios (historical-stale, A→B→A, `.harmessi/` tras
  clon, etc.).
- Fin de línea: archivos nuevos en LF; `core.autocrlf` avisa conversión a CRLF al commitear (deuda v0.10).

## One-writer
Se usaron instancias del writer en paralelo con propiedad de archivos disjunta y explícita; una vez se
reasignó brevemente la edición de `resolvers.py` y de un test a otra instancia cuando el dueño original ya
había terminado, sin solapes concurrentes.

## Resultado final
Change 3 completo y verde. Sin STOP nuevos ni cambios en autonomía/runtime/manifest/Doctor. Listo para cierre.

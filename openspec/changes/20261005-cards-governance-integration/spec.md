# Spec — 20261005-cards-governance-integration

Notación: cada `Rn` tiene criterio de aceptación verificable. Códigos nuevos: `GOVCFG-*` (configuración
efectiva), `ANCHOR-*` (resolución de `ApprovalRef`), `HARMESSI-GOV-*` (Doctor). Changes 0–3 no se reabren:
solo extensiones aditivas con default = comportamiento previo.

## A. Capabilities y provisioning (R1–R16)

**R1 — Vocabulario.** `CAPABILITIES_CONOCIDAS` NO cambia (`("predictive_modeling",)`, default-on histórico).
Se agrega `CAPABILITIES_OPT_IN = ("data_cards", "model_governance")` y `CAPABILITIES_VALIDAS = CONOCIDAS + OPT_IN`.
Sin segunda infraestructura: el mismo campo `capabilities_habilitadas` de `control.json`, el mismo filtro de
manifiesto. No hay flags separados para model_cards/fairness/explainability/privacy/etc.
**R2 — Default idéntico.** `install`/`sync` sin flags nuevos: el set efectivo, el plan, los archivos aplicados, el
`control.json` (incluida la lista persistida `["predictive_modeling"]`) y el manifiesto filtrado son idénticos a
los de v0.8 (test de equivalencia sobre el plan completo y sobre `control.json`).
**R3 — Flags.** `--enable-capability {data_cards,model_governance}` (repetible) en `install` y `sync`;
`--disable-capability` amplía sus `choices` a `CAPABILITIES_VALIDAS`. `--enable-capability` acepta TODAS las
capabilities válidas (también las históricas, para re-habilitar una deshabilitada de forma explícita y persistente).
**R4 — Dependencia.** El set resultante con `model_governance` y sin `predictive_modeling` se rechaza ANTES de
cualquier escritura: exit 2, mensaje que nombra ambas capabilities. Aplica a `install`, `sync` y a combinaciones
`--enable-capability model_governance --disable-capability predictive_modeling`. `data_cards` no requiere nada.
Si `sync --enable-capability model_governance` encuentra `predictive_modeling` deshabilitado en lo persistido, se
rechaza (exit 2) indicando `--enable-capability predictive_modeling`: la dependencia nunca se satisface en silencio.
**R5 — Set de `sync`** (evidencia del audit, proyecto temporal: instalado con `--disable-capability
predictive_modeling`, `sync` sin flags planifica y provisiona `tools/modelquality/*`, es decir re-habilita en silencio
una capability histórica deshabilitada; con `--enable-capability model_governance` eso satisfaría R4 por accidente).
(a) `sync` SIN flags de capability: histórica = `CONOCIDAS − disable` (v0.8 intacto, test «habilitar después vía
sync» intacto); opt-in = persistidas (nunca se descartan en silencio). (b) `sync` CON algún `--enable-capability` o
`--disable-capability` y `capabilities_habilitadas` persistida: el set parte de lo PERSISTIDO completo (históricas
incluidas), luego `∪ enable − disable`; nada deshabilitado se re-habilita ni nada habilitado se pierde sin pedirlo.
(c) control legacy sin lista: se parte del default histórico.
**R6 — `sync` en el mismo stage.** `target < actual`: «nada que hacer» (sin cambio). `target == actual`: procede
solo si hay `--enable-capability` o `--disable-capability` explícitos que cambian el set efectivo respecto del
persistido; sin ellos mantiene «nada que hacer». `target > actual`: sin cambio. Todo lo posterior es idempotente
(sin sobrescribir, `regenerar_control`).
**R7 — Manifiesto «cualquiera de».** `EntradaManifiesto` suma `capabilities_cualquiera: tuple = ()` (aditivo,
default sin efecto). Una entrada con ambos campos vacíos aplica siempre; `capabilities` mantiene «subconjunto
estricto»; `capabilities_cualquiera` exige intersección no vacía con las habilitadas. Existe UN helper de filtro
reutilizado por el planner, `regenerar_control` y Doctor (hoy Doctor filtra inline: se unifica sin cambiar su
resultado para entradas existentes).
**R8 — Entradas de `tools/cards`** (VERBATIM, sin tests; `stage_minimo="discovery"`): compartidos
(`__init__`, `core`, `assess`, `resolvers`, `approvals`, `discovery`, `report`) con `capabilities_cualquiera=
("data_cards","model_governance")`; `datacard` → `capabilities=("data_cards",)`; `modelcard`, `govpolicy`,
`modelgov`, `govconfig` → `capabilities=("model_governance",)`. El grafo de imports de producción de cada módulo
se verifica por test: ningún módulo provisionado importa (ni perezosa ni estáticamente) un módulo no provisionado
bajo la misma combinación de capabilities (los imports de módulos de una capability ausente son perezosos y
condicionados al kind). `tools/reporting` y `dsguard` ya se distribuyen siempre.
**R9 — Sin contenido.** Habilitar una capability instala tooling, nunca crea `governance/`, Cards, assessments,
plantillas ni documentos de hardening (test: tras install con ambas capabilities no existe `governance/`).
**R10 — Exclusiones.** `governance/` se agrega a `EXCLUSIONES_PERMANENTES` (guard de escritura: el instalador
jamás despliega ahí; nunca sobrescribe). `tools/cards/tests/` queda no distribuido (test de instalabilidad).
**R11 — Disable sin pérdida.** Quitar una capability del set (sync con `--disable-capability`) la elimina de la
lista persistida y de `archivos`; NO borra ningún archivo (test: los archivos siguen en disco, byte-idénticos).
**R12 — Legacy.** `capabilities_habilitadas` ausente (control legacy) significa, como hoy, «capabilities
históricas habilitadas»; para las opt-in significa DESHABILITADAS (en Doctor, installer y CLI). Un control con la
lista presente se interpreta literalmente.
**R13 — Stage ortogonal.** `installation_stage` y capabilities siguen siendo ejes separados; las entradas de
cards usan `stage_minimo="discovery"`. Ningún código deriva una capability de un stage ni viceversa.
**R14 — Estado derivado en Doctor.** Por capability opt-in: `enabled` (en la lista), `disabled` (ausente) e
`installed-but-disabled` (disabled con archivos de tooling presentes). Sin lifecycle framework: es solo un
reporte.
**R15 — Nombres validados.** Un nombre desconocido en `capabilities_habilitadas` no rompe nada (Doctor WARN
`HARMESSI-GOV-CAPABILITY-UNKNOWN`, nunca ERROR).
**R16 — Sin dependencias nuevas.** Solo stdlib y paquetes ya del repo (`dsguard`, `reporting`, `ds_init`).

## B. Ownership, discovery y exclusiones (R17–R23)

**R17 — Project-owned.** Todo `governance/` es contenido del proyecto: fuera del manifiesto, fuera de
`control["archivos"]`, fuera de `.harmessi/`. Editarlo NO produce `HARMESSI-DRIFT` (test con `_check_hashes_drift`
real, contenido modificado y creado después de la instalación).
**R18 — Exclusión ≠ invisibilidad.** `EXCLUSIONES_PERMANENTES` solo gobierna lo que el instalador escribe.
Doctor y `cards validate` inspeccionan `governance/` por sus rutas conocidas. Un `control["archivos"]` que liste
una ruta bajo `governance/` ⇒ Doctor WARN `HARMESSI-GOV-OWNERSHIP`.
**R19 — Discovery determinista.** Solo estas rutas, no recursivas, orden lexicográfico por nombre de archivo:
`governance/cards/data/*.json`, `governance/cards/model/*.json`, `governance/model-risk/*.json`. Otros archivos
(no `.json`) y subdirectorios se ignoran; un symlink o un `.json` ilegible/no-objeto en esas rutas es un hallazgo
(Card inválida), no se omite en silencio. Sin escaneo del repo, sin catálogo persistente.
**R20 — Coherencia ruta/identidad.** El nombre de archivo debe ser `<card_id>.json` según `card_path` de cada
módulo; discrepancia ⇒ Card inválida (`CARD-IDENTITY-MISMATCH` existente o equivalente por kind).
**R21 — Kind por ubicación.** El directorio determina el kind esperado; un JSON con otro `card_kind` en ese
directorio es inválido.
**R22 — Documento de hardening.** Ruta fija `governance/policy/model-risk-hardening.json` (esquema
`HardeningDocument` de Change 3). No es Card, no se descubre como tal y no se crea automáticamente.
**R23 — Mutación.** Ningún comando de Change 4 escribe bajo `governance/` salvo `cards report` hacia el destino
de reporting (que NO es `governance/`).

## C. Configuración efectiva de governance (R24–R33)

**R24 — Capas.** `BASE_POLICY` (código) → hardening de proyecto (R22, versionado) → restricción local
(`.harmessi/local-overrides.json`, clave `model_risk_hardening`, mismo esquema `HardeningDocument` inline, no
versionado). `project-config.json` y `guardrails.json` NO se usan para riesgo de modelo (D5).
**R25 — Composición.** `effective = merge(merge(BASE, proyecto), local)` con el `merge` de Change 3 (apilado,
todo-o-nada, `risk_floor=None` hereda). Cada capa solo endurece; la local nunca puede ampliar lo permitido por
la de proyecto ni por la base.
**R26 — Lectura de capas.** Lector independiente y duplicado (regla 13 / precedente `pathguard`), con test de
paridad contra `ds_guard._leer_capa_json`: archivo ausente ⇒ capa vacía; JSON ilegible/no-objeto ⇒ capa
`inválida` (no `{}` silencioso, a diferencia del uso histórico, porque aquí un silencio relajaría la policy).
**R27 — `ProjectGovernance`.** Resultado inmutable de `govconfig.resolve_project_governance(repo_root)` con:
`state ∈ {none, resolved, invalid, unresolvable}`, `project_hardening` (ruta relativa, `content_sha256`),
`local_hardening_present`, `effective` (`EffectivePolicy` o `None`), `effective_sha256`, `findings`.
`none` = ni documento de proyecto ni capa local con hardening (policy efectiva = base).
**R28 — Fail-closed.** Relajación, clave desconocida, tipo inválido o documento malformado en cualquier capa ⇒
`invalid` (`GOVCFG-INVALID`, `GOVCFG-RELAXATION` con el código de Change 3 en el detalle): ninguna evaluación
usa «la base» como reemplazo. Archivo presente pero no legible/no hasheable ⇒ `unresolvable`
(`GOVCFG-UNRESOLVABLE`). Una capa local que intenta habilitar capabilities no tiene efecto: la fuente de verdad
de capabilities es solo `control.json`.
**R29 — Semántica hardening actual vs assessment** (evaluación con contexto de proyecto):

| Contexto actual | Assessment | Resultado |
|---|---|---|
| `none` | base-only (sin `hardening_evidence_id`), pins de base correctos | evaluable normalmente |
| `none` | cita un hardening | `incomplete` (no se evalúa solo con la base; comportamiento de Change 3) |
| `resolved` con documento de proyecto | cita exactamente ese documento (`locator`, `content_sha256`) y `effective_sha256` actual | evaluable normalmente |
| `resolved` | omite el hardening / cita otro documento / cita hash anterior / `effective_sha256` distinto | `stale` (`GOVCFG-HARDENING-MISMATCH`) |
| `resolved` solo por capa local | `effective_sha256` ≠ actual | `stale` (`GOVCFG-LOCAL-ACTIVE`) |
| `invalid` | cualquiera | `invalid` (`GOVCFG-INVALID`), sin evaluar requisitos |
| `unresolvable` | cualquiera | `incomplete` (`GOVCFG-UNRESOLVABLE`), sin `complete` posible |

Nunca `complete` en las filas `stale`/`invalid`/`incomplete`. Los requisitos se evalúan contra la policy efectiva
ACTUAL (no la pineada).
**R30 — Historia.** Un assessment histórico no se reescribe ni se declara «incorrecto»: el resultado describe su
estado respecto del contexto actual; el archivo previo queda como evidencia histórica en Git del proyecto.
**R31 — Capa local por máquina.** La capa local no es versionada; sus efectos se detectan por `effective_sha256`
y el mensaje lo dice (`GOVCFG-LOCAL-ACTIVE`: «restricción local activa en esta máquina»). Es una consecuencia
aceptada y documentada, no un defecto.
**R32 — API aditiva.** `evaluate_governance_assessment(..., governance=None)`: `None` conserva exactamente el
comportamiento de Change 3 (tests de Change 3 intactos); `ProjectGovernance` activa R29. `base=` sigue siendo la
base; con `governance` provisto, la base se toma de `governance` y un `base` distinto del código se rechaza.
**R33 — Sin heurísticas de filesystem** más allá de las dos rutas fijas (R22, R24).

## D. Resolución real de `ApprovalRef` (R34–R42)

**R34 — Hook.** Los evaluadores (`assess.evaluate`/`evaluate_file`, `datacard`, `modelcard`, `modelgov`) aceptan
`anchor_verifier: Optional[Callable[[HumanAttestation], AnchorResolution]]`. `None` = comportamiento estructural
de Changes 0–3 (todos sus tests intactos). La forma del `approval_ref` (`{change_id, artefacto, hash}`) no cambia.
**R35 — Resolución** (`approvals.resolve_approval_ref(repo_root, ref)`), reutilizando primitivas de `dsguard`:
1) forma válida (`validate_approval_ref`); 2) localizar `openspec/changes/<change_id>/` y, si no existe,
`openspec/archive/<change_id>/`; 3) `control.json` legible (`leer_control`); 4) existe una entrada de
`aprobaciones` con ese `artefacto` y `hash`; 5) esa entrada es la más reciente del artefacto
(`_aprobacion_mas_reciente`); 6) el archivo en disco hashea (`hash_lf_v1`) al mismo valor. Sin store nuevo.
**R36 — Estados:** `verified` (1–6 OK); `stale` (existe la entrada pero fue reemplazada por una más reciente o
el archivo cambió); `missing` (no hay entrada/archivo para ese artefacto+hash); `unresolvable` (forma inválida,
Change inexistente, `control.json` ilegible).
**R37 — Efecto (fail-closed).** `verified` ⇒ cuenta como `anchored`. `stale` ⇒ la atestación no satisface
ningún requisito y el estado de la Card es `stale`. `missing`/`unresolvable` ⇒ la atestación no satisface ningún
requisito (`unverifiable`) y la Card queda `incomplete` si el requisito es necesario. Una `anchored` no verificada
NO se degrada a `declared` ni satisface requisitos que aceptan `declared`: afirma más de lo que prueba.
**R38 — `declared`.** Nunca se resuelve ni consulta approvals (test).
**R39 — Trust model.** Un `ApprovalRef` verificado demuestra «existe una aprobación registrada, aún vigente, de
ese artefacto bajo el trust model de Harmessi». No demuestra identidad criptográfica, presencia del usuario,
no repudio, ni que el contenido aprobado sea el claim de la atestación. `usuario`/`fecha_declarada`/`cita` se
devuelven como metadatos informativos; no se comparan ni validan. Texto fijo `NOTA_ANCHOR` en las salidas.
**R40 — Alcance.** Solo aprobaciones de artefactos de un Change (nombre simple). Ledger y aprobaciones de
ejecución no son anclas (forma incompatible). Recomendación documentada: aprobar con `ds_guard approve` un
artefacto del Change que contenga la declaración y referenciarlo.
**R41 — Sin escritura.** La resolución es de solo lectura; nunca registra ni modifica aprobaciones.
**R42 — Aplicación uniforme.** `cards validate`, Doctor y `report` usan siempre el verificador real; la API
sin verificador queda para uso de librería/tests.

## E. CLI (R43–R52)

**R43 — Superficie.** `ds_guard cards validate` y `ds_guard cards report`; import perezoso
(`_importar_perezoso("cards", …)`), exit 3 con `_mensaje_paquete_no_instalado` si el tooling no está instalado.
Exit codes de `ds_guard`: 0 ok, 1 FAIL, 2 uso/configuración, 3 entorno. Sin list/edit/new/wizard.
**R44 — `validate`.** `cards validate [--path RUTA]… [--kind data|model|governance] [--json]`. Sin `--path`: discovery
R19 (filtrado por `--kind`). Con `--path`: el archivo se valida según su `card_kind` (fuera de las rutas conocidas
se acepta explícitamente, con aviso de ubicación). Cada Data/Model Card se evalúa con su `evaluate_*_file`;
cada assessment con `ProjectGovernance` actual y `anchor_verifier` real (R29, R37).
**R45 — Gating por capability.** Con `control.json` presente: kinds de una capability no habilitada ⇒ resultado
`N/A` en discovery (no se validan) y exit 2 si se pidió explícitamente por `--path`/`--kind`;
`model_governance` sin `predictive_modeling` ⇒ exit 2. Sin `control.json` (repo de desarrollo/legacy) ⇒ sin gating.
**R46 — Mapeo a `CheckResult`.** Se reutilizan `datacard/modelcard.a_check_results` y
`modelgov.a_check_results` (invalid ⇒ FAIL; requisito `required` insatisfecho ⇒ FAIL; `recommended`, stale,
hallazgos de config/ancla ⇒ WARN; completo ⇒ PASS). Exit 1 si hay algún FAIL (validación de governance,
nunca decisión de autonomía).
**R47 — Salida humana.** Por Card: tipo, `card_id`, `revision_id`, estado derivado (`complete/incomplete/stale/
invalid`; `governance_completeness` para assessments), requisitos (id, severidad, estado), evidencias
stale/missing/unverifiable y atestaciones `anchored` con su `AnchorResolution`, y para assessments: `risk_level`
declarado/efectivo, `policy_id`/versión/hash (base, hardening, efectiva) y estado de configuración. Siempre la
nota `complete` ≠ éticamente aceptable/seguro/justo/compliant.
**R48 — Salida JSON.** `--json`: `{"resultados":[CheckResult.to_dict()…], "cards":[{kind, card_id,
revision_id, status, requirements, evidence, anchors, policy}], "nota": …}` en una línea (`ensure_ascii=False`),
orden determinista; errores a stderr nunca JSON.
**R49 — Higiene de salida.** Solo rutas relativas al repo; sin rutas absolutas ni nombres de usuario del
sistema; sin secretos; los valores de campos provistos por el usuario se escapan de caracteres de control y se
truncan; ninguna afirmación ética/compliance.
**R50 — `report`.** `cards report --path RUTA [--out-dir DIR] [--json]`: ejecuta la misma validación y publica con
`reporting.publish.publish` (R53–R60). Sin `--path` no hay modo «todas».
**R51 — Solo lectura de governance.** `validate` no escribe nada; `report` solo escribe en el destino de
reporting validado por `reporting.governance`.
**R52 — Sin cambios a otros comandos** de `ds_guard`.

## F. Doctor (R53–R62)

**R53 — Integración.** Nueva función(es) `HARMESSI-GOV-*` cableadas en `ejecutar()` tras los checks de
instalación existentes, protegidas por `_ejecutar_check` (una excepción ⇒ ERROR `…-EXCEPCION`, comportamiento
existente). Solo lectura. Doctor sigue sin `--json`.
**R54 — Fuente de capabilities.** Solo `control.json` (R12). Capability deshabilitada ⇒ `N/A`, sin validar
contenido.
**R55 — Tabla de severidad (determinista, normativa):**

| Código | Condición | Nivel |
|---|---|---|
| `HARMESSI-GOV-CAPABILITY` | ninguna capability opt-in habilitada | N/A |
| `HARMESSI-GOV-CAPABILITY-INVALID` | `model_governance` sin `predictive_modeling` | ERROR |
| `HARMESSI-GOV-CAPABILITY-UNKNOWN` | nombre no reconocido en la lista | WARN |
| `HARMESSI-GOV-INSTALLED-DISABLED` | tooling de cards presente y capability deshabilitada | N/A |
| `HARMESSI-GOV-CONTENT-DISABLED` | hay Cards/hardening en rutas conocidas y su capability está deshabilitada (no se validan) | N/A |
| `HARMESSI-GOV-NONE` | capability habilitada, sin Cards, y `project_stage` ∈ {production_candidate, production} | WARN |
| `HARMESSI-GOV-NONE` | capability habilitada, sin Cards, cualquier otro caso | N/A |
| `HARMESSI-GOV-CONFIG-INVALID` | hardening/capa local inválida o relajada (R28) | ERROR |
| `HARMESSI-GOV-CONFIG-UNRESOLVABLE` | hardening presente pero no resoluble | WARN |
| `HARMESSI-GOV-CARD-INVALID` | Card/assessment ilegible, malformado, identidad o ruta incoherente, estado `invalid` | ERROR |
| `HARMESSI-GOV-CARD-STALE` | Data/Model Card `stale` | WARN |
| `HARMESSI-GOV-CARD-INCOMPLETE` | Data/Model Card `incomplete` | WARN |
| `HARMESSI-GOV-CARD-COMPLETE` | Data/Model Card `complete` | OK |
| `HARMESSI-GOV-ASSESSMENT-STALE` | `governance_completeness=stale` (incluye `GOVCFG-HARDENING-MISMATCH`/`-LOCAL-ACTIVE`, policy cambiada) | WARN |
| `HARMESSI-GOV-ASSESSMENT-INCOMPLETE` | `incomplete` | WARN |
| `HARMESSI-GOV-ANCHOR-UNVERIFIED` | atestación `anchored` en estado `missing`/`unresolvable`/`stale` | WARN |
| `HARMESSI-GOV-ASSESSMENT-COMPLETE` | `complete` (con nota R47) | OK |
| `HARMESSI-GOV-OWNERSHIP` | `archivos` lista una ruta bajo `governance/` | WARN |

Ningún estado `incomplete`/`stale` produce ERROR; ERROR queda reservado a configuración inválida, combinación
de capabilities inválida y artefactos inválidos. El exit code de Doctor sigue siendo 1 solo con algún ERROR; los
mensajes dicen «card governance requirements not satisfied» y nunca mencionan autonomía/ejecución.
**R56 — Sin drift.** Estos checks no tocan `_check_hashes_drift`, `control["archivos"]` ni el manifiesto.
**R57 — Tooling ausente.** Si una capability está habilitada pero faltan archivos de tooling, rigen los
`HARMESSI-ARCHIVO-FALTANTE` existentes (WARN/FAIL por criticidad); no se duplican.
**R58 — Import de cards desde Doctor** perezoso; si falla ⇒ WARN `HARMESSI-GOV-TOOLING` (no ERROR).
**R59–R62** reservadas para ajustes de implementación que no cambien la tabla.

## G. Reporting (R63–R72)

**R63 — Único renderer.** `tools/cards/report.py` construye `reporting.core.Report` y delega en
`reporting.publish.publish`/`render_html`; no se agrega HTML/CSS/estilos ni cambios a `tools/reporting` salvo el valor aditivo `governance` (R64a). Se
reutiliza el manifiesto/procedencia de v0.6 (`describe_source` sobre el archivo de la Card; `holdout_access="none"`).
**R64 — Mapeo.** `decision_scope="exploratory"` (su semántica documentada —«no válido para decisiones de
modelo»— es verdadera para una Card; banner del renderer incluido) y `report_kind="governance"` (R73a; nunca
`evaluation`, que es la clave de autorización de lectura de holdout, ni `model`, ni `eda`). Un capítulo por sección; datos en `TableArtifact`; texto en
`summary`/`method_note`. Sin `FigureArtifact`, sin `Insight`.
**R64a — `governance` en `REPORT_KINDS`.** Cambio ADITIVO y único de `tools/reporting`: `core.REPORT_KINDS` pasa a
`("eda", "model", "evaluation", "production", "governance")` (los cuatro previos, mismo orden, intactos). Semántica:
reporte estructurado de governance/documentación/evidence sobre datos, modelos o evaluaciones de governance; NO significa
evaluación, resultado, validación, readiness, aprobación ni compliance. Los reportes v0.6 existentes se comportan
exactamente igual. Solo se actualizan los tests que fijan `REPORT_KINDS` exhaustivamente (`reporting/tests/test_core.py`),
sin debilitar sus invariantes (el producto cartesiano kind×scope los incluye).
**R64b — Aislamiento de holdout.** `reporting.governance._autorizacion_read` y toda otra condición sobre
`report_kind` (`"evaluation"`, `"eda"`) quedan sin cambios: `governance` NO autoriza lectura de holdout, NO equivale a
`evaluation` ni a `model`, NO activa `model_valid`/`operational`, la política temporal de modelo ni el perfil EDA.
`governance` + `exploratory` sigue denegado donde hoy se deniega (tests: `_autorizacion_read` con `governance` en las 3
scopes devuelve no autorizado y lista `report_kind` entre los faltantes; `publish` de un reporte `governance` no concede
lectura de holdout; los 4 kinds previos conservan su resultado en las 3 scopes).
**R65 — Data Card:** identidad/revisión, descripción, fuentes (`source_refs`: id, estado de evidencia, hash12),
estado derivado, limitaciones conocidas, usos previstos/fuera de alcance, stewardship si existe.
**R66 — Model Card:** modelo/versión, propósito/contexto, Data Cards vinculadas (ref + estado), evidencia de
calidad (`model_quality_*`: ref + estado), limitaciones, procedencia.
**R67 — Assessment:** nivel de riesgo declarado y efectivo, policy (id/versión/hashes base-hardening-efectiva),
requisitos por dimensión con estado, estado de evidencias, atestaciones `anchored` con su resolución,
`governance_completeness`, limitaciones y estado de configuración.
**R68 — Aclaración obligatoria.** Todo reporte incluye en `Report.summary`, `Report.conclusion` y en el
`method_note` de cada capítulo de assessment: `complete` ≠ ético/seguro/justo/compliant (texto fijo
`NOTA_COMPLETENESS`); un test verifica su presencia en HTML renderizado.
**R69 — Sin conclusiones nuevas.** El reporte solo refleja estados derivados ya calculados; no agrega
interpretación, scores ni «aprobado/rechazado».
**R70 — Sin duplicar evidencia.** Las tablas contienen `evidence_id`, kind, `ref_id`, hash12 y estado; nunca el
contenido de la evidencia ni payloads (test: ningún valor de payload de fixtures aparece en `artifacts/*.json`).
**R71 — Escape/privacidad.** Reutiliza el escape del renderer; sin rutas absolutas; los campos de usuario
siguen las reglas de R49.
**R72 — Destino.** Lo decide `reporting.governance` (`reports/<scope>/<report_id>/` o `--out-dir` validado);
nunca bajo `governance/`.

## H. Autonomía e inercia (R73–R77)

**R73 — D1/D6.** Sin cambios en `STOP_CATALOG`, `POLICY_TABLE`, `approval_mode`, checkpoints ni `leadrun`;
`tools/autonomy` no se modifica (ni se menciona «cards» allí). Ningún resultado de `cards validate`/Doctor se
traduce en denegación de ejecución (test: sin imports ni referencias cruzadas; los snapshots de `STOP_CATALOG`
de los cuatro tests de inercia siguen verdes).
**R74 — D5.** Nada se persiste en `guardrails.json`.
**R75 — Enmiendas explícitas de tests de inercia** (documentadas en verification.md): se levantan SOLO las
prohibiciones textuales/estructurales que este Change debe romper (`MANIFEST` sin `cards`, «cards»/capabilities
nuevas en `ds_guard`/`doctor`/`ds_init`, import perezoso desde `ds_guard`/`doctor`, `CAPABILITIES_CONOCIDAS`
sigue fijada) y se reemplazan por aserciones equivalentes más precisas (p. ej. lista cerrada de módulos
permitidos a importar `cards`). Los tests de `STOP_CATALOG`/autonomía no se modifican.
**R76 — Dirección de dependencias.** `tools/cards` puede importar `dsguard` y `reporting` SOLO desde los módulos
de adaptador nuevos (`approvals`, `report`, `discovery`, `govconfig`); `core/assess/resolvers/datacard/modelcard/
govpolicy/modelgov` siguen stdlib-only (los tests de neutralidad actuales se mantienen para ellos).
**R77 — `reporting` no importa `cards`** (test).

## I. Compatibilidad hacia atrás (R78–R81)

**R78** Proyecto sin capabilities nuevas ⇒ comportamiento previo idéntico en installer, Doctor (mismo conteo de
checks salvo el N/A `HARMESSI-GOV-CAPABILITY` que no altera exit code ni OK/WARN/ERROR) y reporting.
**R79** Upgrade de v0.8/v0.9 parcial ⇒ nunca elimina assets; Cards existentes en `governance/` siguen válidas.
**R80** Proyectos de desarrollo creados durante Changes 0–3 (sin `control.json`) funcionan sin gating (R45).
**R81** Todas las suites de Changes 0–3 pasan salvo las enmiendas de R75.

## Tests requeridos (mínimo)
Capabilities: default sin flags (plan/control byte-idénticos), opt-in por flag, `model_governance` + `predictive=false`
inválido (install/sync/Doctor), data_cards sin predictive, enable-later vía `sync` mismo stage, disable no borra,
legacy sin lista, E2E de `sync` (persistido `predictive_modeling=false` + `sync --enable-capability model_governance` ⇒
exit 2 sin escribir; `--enable-capability predictive_modeling --enable-capability model_governance` ⇒ OK; `--enable-capability
data_cards` NO re-habilita `predictive_modeling`; `sync` sin flags de capability = v0.8), filtro «cualquiera de», entradas del manifiesto e instalabilidad (sin tests, sin `governance/`).
Hardening: sin hardening, correcto pineado, omitido ⇒ stale, otro documento/hash ⇒ stale, hash de policy efectiva
distinto ⇒ stale, relajación ⇒ invalid, ilegible ⇒ incomplete, local-only ⇒ stale, local relaja ⇒ invalid,
local no habilita capabilities, `governance=None` ⇒ Change 3 intacto. ApprovalRef: verified, entrada ausente, hash
distinto, Change/artefacto equivocado, reemplazada ⇒ stale, archivo modificado ⇒ stale, Change archivado,
`control.json` ilegible, `declared` sin consulta, `anchored` no verificada no satisface `declared`. CLI: Data/Model
Card/assessment, humano, JSON, archivo malformado, capability deshabilitada, rutas fuera de lo conocido, exit
codes. Doctor: cada fila de R55, governance no produce drift, legacy. Reporting: vocabulario (`governance` aceptado, los previos intactos), aislamiento de holdout (R64b), las tres Cards,
renderer existente, sin evidencia duplicada, aclaración semántica, escape. Compatibilidad: inercia supervised/autonomous,
installer, Doctor legacy, reporting legacy.

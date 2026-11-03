# Diseño — 20261005-cards-governance-integration

## Decisiones

**D1 — Opt-in real: vocabulario separado, no ampliar `CAPABILITIES_CONOCIDAS`.** Hoy «conocida» ≡ «habilitada
por default» (`cli.py:161,241`). Ampliar la tupla activaría Cards en toda instalación nueva y en todo `sync`.
Se agrega `CAPABILITIES_OPT_IN` (default-off) y se reutiliza el mismo campo persistido y el mismo filtro del
manifiesto; solo cambia el cómputo del set (R2, R5). Alternativa descartada: segundo mecanismo de capabilities
(prohibido por el pedido y duplicaría el filtro).

**D2 — `sync`: herencia según presencia de flags y mismo-stage condicionado.** Audit empírico (proyecto temporal
con `predictive_modeling` deshabilitado): `sync` sin flags re-habilita y provisiona `modelquality`; un `sync
--enable-capability model_governance` lo re-habilitaría y haría pasar la dependencia R4 por accidente. Sin flags de
capability se conserva el v0.8 para las históricas (un test lo fija como «habilitar después vía sync»); con flags
(camino nuevo, sin compatibilidad que romper) el set parte de lo persistido completo. Las opt-in persistidas se
heredan siempre; se quitan solo con `--disable-capability`. `target == actual` procede únicamente si hay flags explícitos que cambian el set; así
`sync` sin flags sigue diciendo «nada que hacer» (compatibilidad) y habilitar después funciona sin subir de stage.

**D3 — Manifiesto «cualquiera de».** `data_cards` y `model_governance` comparten `core/assess/resolvers`; el
filtro actual es subconjunto estricto (exigiría ambas). Se agrega `capabilities_cualquiera` (aditivo, default
vacío, sin efecto en entradas existentes) y un único helper de filtro compartido por planner, `regenerar_control` y
Doctor (hoy Doctor filtra inline). Alternativa descartada: una entrada por capability para el mismo destino
(duplicaría destinos y rompería la unicidad del manifiesto).

**D4 — Dependencia `model_governance → predictive_modeling` validada en el set final.** Una sola función pura
`validar_capabilities(set)` usada por install, sync y Doctor (misma fuente de verdad); el installer la aplica
antes de escribir (exit 2). Doctor la aplica al set persistido (ERROR).

**D5 — Governance project-owned, sin tocar el manifiesto.** `governance/` queda fuera de manifest/drift/`.harmessi/`
como definieron Changes 1–3. Se agrega a `EXCLUSIONES_PERMANENTES` solo como guard de escritura del instalador.
Doctor/`validate` leen rutas fijas (R19); nada de escaneo ni catálogo. El hardening de proyecto tiene ruta fija
propia (`governance/policy/model-risk-hardening.json`): es un documento, no una Card, y es lo que el assessment
ya pinea (`governance_policy`, hash del documento completo).

**D6 — Capas de config: documento versionado + capa local reutilizando `local-overrides.json`.** Para que el pin del
assessment tenga sentido, el hardening de proyecto debe ser un documento aislado; meterlo en `project-config.json`
(archivo compartido por otras claves) haría `stale` todo assessment ante ediciones ajenas. La restricción local
reutiliza `.harmessi/local-overrides.json` (infra v0.8) bajo una clave propia y el esquema `HardeningDocument`.
El orden base → proyecto → local se materializa con el `merge` apilado de Change 3 (que ya acepta
`EffectivePolicy` como base), sin segundo algoritmo ni segundo vocabulario. A diferencia del uso histórico de las
capas (`{}` ante JSON roto), aquí un archivo ilegible es `invalid`: un silencio relajaría la policy.

**D7 — Hardening actual: el evaluador recibe el contexto, no lo descubre.** `evaluate_governance_assessment`
mantiene su pureza (Change 3 prohibió heurísticas de filesystem en el evaluador). `govconfig` resuelve el contexto
actual (`ProjectGovernance`) y se lo pasa; con `governance=None` el comportamiento es el de Change 3. Con contexto:
(1) invalid ⇒ `invalid` antes de evaluar; (2) unresolvable ⇒ `incomplete`; (3) se compara lo pineado contra lo
actual (documento citado, su hash, `effective_sha256`); cualquier diferencia ⇒ `stale` con hallazgo específico;
(4) los requisitos se evalúan contra la policy efectiva ACTUAL. Cierra I3 sin reescribir artefactos históricos.

**D8 — `ApprovalRef`: hook inyectable + adaptador con primitivas existentes.** Foundation sigue stdlib-only y sin
conocer `control.json`: los evaluadores aceptan `anchor_verifier` (default `None` = estructural). El adaptador
`approvals.py` (único que importa `dsguard`) implementa R35 con `leer_control`, `_aprobacion_mas_reciente` y
`hash_lf_v1`. Se exige que la entrada sea la más reciente del artefacto y que el archivo siga con ese hash
(equivale al gate de implementación de SDD): una aprobación reemplazada o un artefacto editado después ⇒ `stale`,
coherente con «estado derivado». Alternativa descartada: ledger o aprobaciones de ejecución como anclas (su forma
no calza con `{change_id, artefacto, hash}`; adaptar el ref rompería la unión estricta de Change 0).

**D9 — `anchored` no verificada no satisface nada.** Degradarla a `declared` convertiría un ref roto en una
declaración válida para cualquier requisito que acepte `declared` (p. ej. `low/medium` aceptan `declared`): un
vector de evasión por romper el ref. Fail-closed: no cuenta ni como `anchored` ni como `declared`.
`declared` jamás consulta approvals.

**D10 — CLI en `ds_guard`, no `python -m`.** Precedente: `contract`, `quality`, `source` viven en `ds_guard` con
import perezoso; `ds_guard.py` ya se distribuye y comparte exit codes y salida `--json`. Dos hojas: `validate`
(el pedido) y `report` (único punto de entrada para reporting; sin él el requisito de renderizar no sería
alcanzable). Se reutilizan los `a_check_results` de cada módulo para el mapeo a `CheckResult`.

**D11 — Doctor lee estado, no lo decide.** Cada fila de la tabla R55 sale de un estado ya derivado por los
módulos (`invalid/stale/incomplete/complete`, `ProjectGovernance.state`, resolución de anclas); no hay
umbrales nuevos. ERROR se reserva a lo que no se puede confiar o no es una configuración válida; carencias
(`incomplete`/`stale`) son WARN: reportar honestamente sin burocracia universal ni efecto de runtime (D1).
Capability deshabilitada ⇒ N/A (se ve como `installed-but-disabled`/`content-disabled`, sin lifecycle framework).
La única fila dependiente de etapa (`HARMESSI-GOV-NONE`) usa `project_stage` (madurez real) y solo emite WARN en
`production_candidate`/`production`; `installation_stage` no cuenta (es qué está instalado, no qué aplica).

**D12 — Reporting vía adaptador; `report_kind="governance"` aditivo.** `report.py` traduce Card/assessment a `Report`
(Chapter + TableArtifact + texto) y llama a `publish`. Audit: `evaluation` es falso (evaluación de modelo; clave de
autorización de holdout en `reporting.governance._autorizacion_read`), `model` no describe una Data Card y ningún valor
describe «governance». Decisión aprobada: agregar al vocabulario un único valor neutral `governance` (aditivo,
`core.REPORT_KINDS`), sin lógica asociada: la única lógica que mira `report_kind` en reporting es `"eda"` (perfil EDA,
`validation.py:400`) y `"evaluation"` (holdout), y ninguna cambia; `render_html` imprime el kind como texto escapado y
las validaciones solo chequean pertenencia al vocabulario. Se prueba explícitamente que `governance` + `exploratory`
(y en las otras scopes) NO autoriza holdout y que los kinds previos se comportan igual. `decision_scope="exploratory"`
se mantiene (banner «no válido para decisiones de modelo», aislamiento). Las tablas guardan referencias y estados, no
contenido de evidencia. La aclaración `complete` ≠ ético/seguro/justo/compliant va en summary, conclusión y method_note.
La fuente declarada del manifiesto es el archivo de la Card (describe_source), `holdout_access="none"`.

**D13 — Primer consumidor de reporting: fronteras explícitas.** Hoy ningún paquete de dominio usa reporting y
varias reglas lo prohíben a otros. Se permite SOLO a `tools/cards/report.py`; los módulos de contrato siguen
puros y los tests de neutralidad se reescriben con una lista cerrada de importadores permitidos (R75-R77).

## Flujo de `cards validate`
1. `ds_guard` carga `cards` perezosamente; resuelve capabilities de `control.json` (R45).
2. `discovery` lista rutas conocidas (R19) o toma `--path`.
3. Para cada archivo: Data/Model Card ⇒ `evaluate_*_file(..., anchor_verifier=real)`; assessment ⇒
   `govconfig.resolve_project_governance` (una vez) + `evaluate_governance_assessment(..., governance=ctx,
   anchor_verifier=real)`.
4. Se mapea a `CheckResult` y a la estructura de salida; exit por `checks.exit_code`.

## Riesgos y mitigaciones
- **Romper el default histórico:** R2 con test de plan/`control.json` byte-idénticos antes/después.
- **Cambiar semántica de `sync` existente:** solo se agregan ramas con flags explícitos; los tests existentes de
  sync no se tocan.
- **Tests de inercia v0.9:** se enmiendan solo las aserciones que impiden la integración (R75) y se listan en
  verification.md; los de autonomía/STOP quedan intactos.
- **Anclas con Changes archivados:** se resuelve `openspec/archive/<id>` además de `changes/`; si el layout cambiara,
  el estado es `unresolvable` (fail-closed), no `verified`.
- **Divergencia de lectores de capa:** test de paridad contra `ds_guard._leer_capa_json` (regla 13).

## Archivos previstos
- `tools/ds_init/manifest.py` (vocabulario, campo, helper de filtro, entradas, `EXCLUSIONES_PERMANENTES`),
  `tools/ds_init/cli.py`, `tools/ds_init/control.py` (solo si hace falta), `tools/ds_init/planner.py` (filtro único).
- `tools/cards/{govconfig,approvals,discovery,report}.py` (nuevos); ediciones aditivas mínimas en
  `assess.py`, `datacard.py`, `modelcard.py`, `modelgov.py` (hook y contexto opcionales).
- `tools/ds_guard.py` (subcomando `cards`), `tools/harmessi/doctor.py` (checks `HARMESSI-GOV-*`, filtro unificado).
- Tests: `tools/cards/tests/test_{govconfig,approvals,discovery,report,integration_hooks}.py`,
  `tools/ds_init/tests/test_cards_capabilities.py` (+ ajustes), `tools/harmessi/tests/test_doctor_governance.py`,
  `tools/tests/test_cards_cli.py`, `tools/tests/test_v09_integration_{inert,neutrality}.py`; enmiendas de los
  `test_v09_*` de Changes 0–3.
- Docs: `ARCHITECTURE.md` (regla 13/§8), `docs/roadmap/v0.9.md`, `docs/roadmap/v0.10.md` (deudas nuevas).

## Out of scope
Ver proposal.md. En particular: authenticity de aprobaciones, CRUD/UX de Cards, nuevos kinds/dimensiones,
cambios a `BASE_POLICY`, lifecycle de capabilities, segundo renderer.

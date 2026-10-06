# Verificación — 20261005-cards-governance-integration

## Resumen ejecutivo
Change 4 de v0.9: integra al producto lo construido en Changes 0–3 (Foundation, Data Cards, Model Cards,
ModelGovernanceAssessment, policy, `HumanAttestation anchored`, hardening de proyecto) mediante capabilities opt-in,
provisioning/sync capability-aware, configuración efectiva de governance, hardening ACTUAL obligatorio, resolución real
de `ApprovalRef`, `ds_guard cards validate|report`, Doctor y reporting vía `tools/reporting/`. SDD aprobado por hash el
2026-10-06 (incluida la decisión material `report_kind="governance"` y la resolución del bug de `sync` auditado), sobre
baseline `64df7f3` (HEAD posterior a Corrective A; re-baseline mediante `ds_guard init` sobre el Change aún sin
aprobaciones, sin editar JSON). Todas las ejecuciones pasaron por el runtime gobernado (`ds_guard exec pytest`).

## QUÉ SIGNIFICA `complete` (sin cambios)
Solo que los requisitos de la policy están satisfechos con soportes aceptables e íntegros. NO significa ético, seguro,
justo, fair ni compliant. La nota `complete ≠ …` viaja en CLI, Doctor y reporting.

## QUÉ DEMUESTRA `ApprovalRef` verificado (explícito)
Existe una aprobación REGISTRADA, aún VIGENTE, de ese artefacto de un Change bajo el trust model de Harmessi
(`control.json` + `hash_lf_v1`). NO demuestra identidad criptográfica, presencia del usuario ni no repudio, ni que el
contenido aprobado sea el claim de la atestación. La deuda «Approval origin / human authorization authenticity» sigue en v0.10.

## Qué entrega
- **Capabilities** (`ds_init`): `CAPABILITIES_CONOCIDAS` intacta; `CAPABILITIES_OPT_IN = (data_cards, model_governance)`
  default-off con `--enable-capability`; `model_governance` exige `predictive_modeling` (`validar_capabilities`, usada por
  install, sync y Doctor; rechazo ANTES de escribir, exit 2). `data_cards` no requiere nada.
- **Sync (final):** SIN flags de capability = v0.8 intacto (históricas recalculadas, opt-in persistidas conservadas). CON
  algún `--enable-capability`/`--disable-capability` y lista persistida: el set parte del persistido COMPLETO (históricas
  incluidas) `∪ enable − disable`; `--enable-capability` acepta también históricas. Caso crítico verificado E2E: persistido
  `predictive_modeling=false` + `sync --enable-capability model_governance` ⇒ exit 2 sin escribir (no reactiva implícitamente);
  `--enable-capability predictive_modeling --enable-capability model_governance` ⇒ OK; `--enable-capability data_cards`
  no re-habilita `predictive_modeling`. `sync` en el mismo stage solo con flags que cambian el set. Un control persistido
  inválido (p. ej. editado a mano) ⇒ exit 2. Disable no borra archivos.
- **Provisioning:** 12 entradas VERBATIM de `tools/cards` (sin tests), campo `capabilities_cualquiera` («cualquiera de») y un
  único helper de filtro compartido por planner, `regenerar_control` y Doctor. `governance/` en `EXCLUSIONES_PERMANENTES`;
  el instalador nunca crea Cards, assessments ni hardening. Test de instalación aislada data_cards-only (sin módulos de
  model_governance) importa y valida.
- **Governance config / hardening actual** (`govconfig.py`): base → `governance/policy/model-risk-hardening.json` →
  `.harmessi/local-overrides.json["model_risk_hardening"]`, `merge` apilado todo-o-nada. Estados `none/resolved/invalid/
  unresolvable`; invalid/relajado NUNCA cae a `BASE_POLICY`. Tabla R29 en `modelgov.evaluate_governance_assessment
  (governance=…)`: base-only con hardening vigente / omitido / otro documento / hash viejo / effective hash viejo ⇒ `stale`;
  inválido ⇒ `invalid`; no resoluble ⇒ `incomplete`; `governance=None` ⇒ comportamiento exacto de Change 3. Cierra la
  limitación I3 de Change 3.
- **ApprovalRef** (`approvals.py`): 6 pasos (forma, Change en `changes/` o `archive/`, `control.json` legible, entrada
  artefacto+hash, la MÁS RECIENTE, archivo con el mismo hash). Hook `anchor_verifier` en assess/datacard/modelcard/modelgov
  (default None = Changes 0–3): verified ⇒ anchored; stale ⇒ no satisface y deja stale; missing/unresolvable ⇒ no
  satisface (ni anchored ni declared) ⇒ incomplete. `declared` nunca consulta aprobaciones. Rechaza artefactos no portables
  (`:`, nombres reservados, escape del Change).
- **CLI:** `ds_guard cards validate [--path] [--kind] [--json]` y `cards report --path [--out-dir]`; exit 0/1/2/3; gating
  por capability con control legible (control ilegible ⇒ exit 2); rutas relativas, sin secretos ni rutas absolutas;
  `validate` no escribe.
- **Doctor:** `_check_governance` (`HARMESSI-GOV-*`) con la tabla R55: capability disabled ⇒ N/A; combinación inválida,
  hardening/config inválida y artefacto invalid ⇒ ERROR; stale/incomplete ⇒ WARN; complete ⇒ OK sin «aprobado»; sin drift
  de `governance/`; instalación por defecto conserva el PASS `HARMESSI-ARCHIVOS-ESPERADOS` (sin N/A espurios por opt-in).
- **Reporting:** `tools/cards/report.py` construye un `Report` y delega en `publish` (sin segundo renderer);
  `report_kind="governance"` (único cambio de `tools/reporting`: valor aditivo en `REPORT_KINDS`),
  `decision_scope="exploratory"`. Tablas con referencias y estados (nunca contenido de evidencia); aclaración en
  summary/conclusión/method_note.
- **Aislamiento de holdout:** `reporting.governance._autorizacion_read` y toda condición sobre `evaluation`/`eda` SIN
  cambios; tests: `governance` (en las 3 scopes) no autoriza lectura de holdout ni equivale a `evaluation`/`model`; los 4
  kinds previos conservan su resultado; `publish` con `governance` no concede lectura de holdout.
- **Autonomía (D1/D5/D6):** sin cambios a `STOP_CATALOG`, `POLICY_TABLE`, `approval_mode`, checkpoints, leadrun ni
  `guardrails.json`; un FAIL de `cards validate` o un ERROR de Doctor no es una decisión de ejecución.
- Enmiendas explícitas de los tests de inercia/neutralidad v0.9 (R75): se reemplazaron prohibiciones por listas cerradas
  (12 módulos de `tools/cards` en el manifiesto; nombres/`cards` solo en `ds_init/{manifest,cli}`, `ds_guard`, `doctor` y
  tests; importadores de `cards` = `ds_guard` y `doctor`, ambos perezosos; adaptadores con su propia lista). La Foundation
  conserva todas sus prohibiciones y `tools/autonomy` sigue sin mencionar cards/capabilities.

## Ejecuciones reales (runtime gobernado)
Dirigida final (todos los tests nuevos y tocados + `test_v09_*` + doctor + reporting + capabilities): **646 passed,
6 skipped, 30350 subtests, 0 failed** (tras el último ajuste `test_doctor.py` 97 passed).

Regresión relevante, lotes SECUENCIALES (exit code real del `ExecutionRecord`):

| Lote | Suite | Resultado |
|---|---|---|
| 1 | `tools/tests` | 1380 passed, 6 skipped, 30215 subtests |
| 2 | modelquality, qualityevidence, datasources, datacontracts | 511 passed, 150 subtests |
| 3 | autonomy, leadrun | 260 passed, 261 subtests |
| 4 | `tools/cards/tests` | 1230 passed, 34 skipped, 2577 subtests |
| 5 | ds_init, harmessi (Doctor), reporting | 1ª corrida (`pytest__e9d5ffb36e59`): 1176 passed, 3 skipped, 2 failed = 1181 tests = ds_init 180 + harmessi/reporting 1001 (colección). Rerun solo de ds_init tras la enmienda de `test_manifest` (`pytest__5c78828dd0ce`): 180 passed |

**Total único de la regresión (sin doble contar el rerun):** 1380 + 511 + 260 + 1230 + 1178 = **4559 passed**, 43 skipped
(6 + 0 + 0 + 34 + 3), **0 failed** al cierre. El lote 5 final = 998 passed de harmessi+reporting (1176 − 178 passed de ds_init en
la 1ª corrida; 998 + 3 skipped = 1001 tests colectados) + 180 passed de ds_init en el rerun (que incluye los 2 tests enmendados).
Cuidado al sumar: la fila «180» del rerun NO incluye harmessi/reporting; sumar solo las cuatro primeras filas y 180 da 3561
y omite los 998 passed de harmessi+reporting. Corrección post-cierre del 2026-10-06 (el reporte humano había dado «≈4560»
sin desglosar el lote 5); los números salen de los `ExecutionRecord` y de un conteo por colección (`--collect-only`, sin
re-ejecutar suites). Los 2 fallos del lote 5 eran premisas obsoletas de `test_manifest.py` («sin `capabilities` = sin filtro» y
«`{predictive_modeling}` habilitadas = todo el manifiesto»), que con `capabilities_cualquiera` y opt-in default-off dejan de
valer; se enmendaron preservando la intención (ver abajo).

## Proceso de revisión (2 ciclos, máximo)
- **Ciclo 1** (2 revisores, partes A y B): 0 bloqueantes. Importantes corregidos: I1 Doctor emitía N/A por archivos opt-in
  nunca habilitados (rompía el conteo de instalaciones por defecto); I2 ownership ignoraba capabilities; I3/I4 tests de grafo
  de imports y de baseline R2 débiles; fail-open en discovery si no importaba govconfig/approvals (ahora unresolvable y
  verificador sintético); N/A de requisito recommended apoyado en ancla no verificada; directorios enlazados omitidos en
  silencio; M1–M4 de sync (nombres persistidos, control persistido inválido, mensaje, aviso de flags ignorados); `--kind`
  vs `--path`; `card_kind` desconocido; higiene de salida (`usuario` fuera de anchors); artefactos no portables en
  `ApprovalRef`; symlink en govconfig; contenido del reporte; `publish` que lanza.
- **Ciclo 2:** B1 un test de reporting roto (`test_core` contaba 12 combinaciones kind×scope; ahora 15) y N-3 `cards report`
  fail-open con `control.json` ilegible (corregido a exit 2, con test); T-1/T-2 tests débiles reforzados (FAIL de holdout
  específico; escape HTML afirmado); N-7 rutas absolutas ajenas en textos de usuario (redacción en `limpiar_texto`); m-1
  validación de tipo del control persistido.

## Precisiones por encima del spec aprobado (el spec no se editó; todas más estrictas)
- Anclas no verificadas: además de no satisfacer, fallan cerrado dentro de N/A de requisitos recommended.
- Un control persistido inválido o con tipos raros se rechaza (exit 2) en `sync`, con o sin flags.
- `cards validate/report` con `control.json` ilegible ⇒ exit 2 (spec R45 no lo precisaba).
- Doctor: los archivos de capabilities opt-in nunca habilitadas no generan N/A por archivo (se informa una sola línea
  `HARMESSI-GOV-CAPABILITY`), para no alterar el resumen de las instalaciones por defecto (R78).
- `enmienda test_manifest.py` (2 tests, intención preservada) y `test_core.py` de reporting (cuenta 15 combinaciones).
- `limpiar_texto` redacta rutas absolutas de usuario (`C:\…`, `/home/…`, `/Users/…`) en salidas.
- `interfaces.md` en el directorio del Change es un apoyo de coordinación entre writers (no es artefacto aprobado).

## Limitaciones conocidas y deuda (no bloqueantes)
- **Semántica ANY-fresh en Data/Model Cards (N-1):** un requisito con un soporte fresco y una atestación `anchored` stale o
  no resoluble queda `satisfied` (WARN `ANCHOR-*`); en assessments (modelgov) un soporte stale citado SÍ deja el requisito
  stale. Es la semántica documentada de la Foundation (Change 1); no se reabrió.
- **Anclas stale no citadas o en requisitos recommended (N-2)** de un assessment solo producen finding, no cambian el estado
  global (R37 era ambiguo). Documentado.
- **Asimetría de `sync` con/sin flags (decisión aprobada):** con persistido `["data_cards"]`, `sync --stage X` sin flags
  re-habilita `predictive_modeling` (v0.8) y con flags no. Fue la resolución aprobada para no romper el comportamiento v0.8.
- La capa local de hardening es por máquina (puede dejar un assessment `stale` solo allí).
- `ApprovalRef` solo ancla aprobaciones de artefactos de un Change (nombre simple).
- Mixed `capabilities` + `capabilities_cualquiera` en una entrada exige ambos (hoy no existe ninguna).
- TOCTOU de lecturas dobles (Card leída para kind y luego evaluada) con ventana mínima y consecuencias fail-closed.
- Los tests de symlink se saltan en SO sin privilegio; los de junction de Windows no están cubiertos.
- `tools/cards/discovery.py` usa `ds_init.manifest.validar_capabilities` si importa y una regla duplicada si no (ds_init no
  se distribuye); sin test de paridad entre ambos caminos.
- Fin de línea: archivos nuevos en LF; `core.autocrlf` avisa conversión a CRLF al commitear (deuda v0.10).
- v0.10: approval-origin authenticity, LF/CRLF hashing, mid-Change authorized scope amendment UX, composable skills/
  domain-modeling, one-writer. Corrective B (checkpoints circulares, `.postN`, drift de `guardrails.json`) y C (`ds_profile`)
  pendientes y NO abiertos. `docs/feedback/` queda untracked y fuera del commit.

## One-writer
Cuatro instancias `python-data-engineer` en paralelo con propiedad de archivos disjunta y explícita (W1 `ds_init`; W2
`govconfig`/`approvals`/hooks de Foundation; W3 `discovery`/`report`/CLI/reporting; W4 Doctor), más una reasignación del
archivo de tests de inercia v0.9 a W1 una vez libre. El Lead editó directamente solo tests y ajustes puntuales tras el
cierre de cada ola de writers (`test_govconfig` fixture, `test_manifest`, `test_core` de reporting, `ds_guard` gating y
`discovery.limpiar_texto`), sin solapes concurrentes.

## Resultado final
Change 4 completo y verde. Autonomía/STOP/runtime intactos; reporting solo con el valor aditivo `governance`. Listo para cierre.

# Spec — 20260915-unified-status-surface

## Requisitos

### R1 — CLI, sin colisión con el `status` existente
`python -m tools.ds_guard status [--change-id <id>] [--json] [--verbose]`. Con `--change-id`:
comportamiento EXACTO actual (`cmd_status` sin cambios de lógica, `--verbose` ignorado si se
pasa junto con `--change-id`). Sin `--change-id`: nuevo status unificado de proyecto —
`status.evaluar_status(repo_root)` + `status.formatear_texto`/`formatear_json`. Exit code: `0`
siempre para el modo unificado (es informativo, nunca "falla" por contenido — mismo criterio que
`project status`/`mlops status` existentes salvo error de entorno real, p. ej. no estar en un
repo Git, que sigue devolviendo `3`).

### R2 — Secciones mínimas
`evaluar_status` devuelve un dict con, como mínimo: `project` (`project_stage`, `risk_level`,
`risk_status`), `installation` (`installation_stage`, `origen`: `"declarado"`|`"inferido"`|
`"desconocido"`), `alignment` (`"aligned"`|`"sync_needed"`|`"ahead"`|`"unknown"`), `lifecycle`
(`crispdm`: resumen de 8 fases, `kdd`: resumen de 5 pasos canónicos), `mlops` (`foundations`:
4 `CheckResult`, `production_readiness`: 5 capabilities, `operations`: 7 capabilities),
`readiness` (`next_target`, `ready`/`not_ready`/`technical_error`/`none`, `blocking`, `warnings`),
`harness` (`disponible: bool`, conteos si disponible, principales WARN/ERROR).

### R3 — `next_target` (nunca persistido)
`discovery→experiment`, `experiment→production_candidate`, `production_candidate→production`,
`production→None`. Función pura, sin I/O, derivada de `project_stage` en el momento de la
consulta — nunca escrita a ningún archivo.

### R4 — Readiness (reuso estricto de Change 6)
Si `next_target` es `None` (project_stage=production): `readiness.next_target=None`,
mensaje explícito "production ya es el stage final — no existe próximo target normal" (nunca se
inventa madurez post-producción). Si no: `readiness.evaluar_readiness(repo_root, next_target)`
(sin reimplementar gates); `ready` deriva de `checks.hay_bloqueo` (nunca invertido a mano);
`technical_error: bool` = `any(r.kind == checks.KIND_TECHNICAL_ERROR for r in resultados)` — si
`True`, el resumen textual es `"TECHNICAL ERROR"` en vez de `"NOT READY"` (nunca oculto, R14 del
brief); `blocking` = resultados con `status==FAIL` (incluye los `technical_error`, marcados
explícitamente como tales en el mensaje/campo); `warnings` = resultados con `status==WARN`.

### R5 — `project_stage` vs `installation_stage`
`alignment`: `"aligned"` si iguales; `"sync_needed"` (nunca `"ERROR"`) si
`index(project_stage) > index(installation_stage)`, con mensaje accionable ("correr `ds_init sync
--stage <project_stage> --execute`"); `"ahead"` (permitido, nunca tratado como corrupción) si
`index(installation_stage) > index(project_stage)`; `"unknown"` si no se puede determinar alguno
de los dos. `installation_stage` se lee de `.ds_init/control.json` (JSON plano, sin depender de
`tools.ds_init`) cuando esa clave está presente (`origen="declarado"`); si está ausente, se
intenta `legacy.inferir_installation_stage` vía import perezoso opcional
(`origen="inferido"` si funcionó, `origen="desconocido"` si `tools.ds_init` no está disponible en
este árbol — nunca excepción cruda).

### R6 — Risk
`risk_level` mostrado tal cual (`low`/`medium`/`high`/`None`→`"unclassified"`), derivado de
`maturity.estado_riesgo` (reusado, no reimplementado). Sin governance específica por nivel. Si
`project_stage >= production_candidate` y `risk_level is None`, `status` NO decide nada — solo
refleja el `FAIL` que `readiness.evaluar_readiness` ya produce para `READINESS-RISK-CLASSIFIED`.

### R7 — CRISP-DM/KDD
`lifecycle.crispdm`: `{"fases": {<8 nombres canónicos>: {"estado": ..., "cerrada": bool}},
"resumen": "N/8 closed"}`. `lifecycle.kdd`: mismo patrón para los 5 pasos canónicos
(`selection`/`preprocessing`/`transformation`/`data_mining`/`interpretation_evaluation`) — nunca
se muestran las 10 etapas legacy como ontología principal (compatibilidad legacy sigue interna,
`kdd_compat.py` no se toca ni se expone). Si `openspec/lifecycle/state.json` no existe:
`lifecycle.disponible=False`, mensaje "lifecycle unavailable — correr `ds_guard lifecycle
migrate` o inicializar el lifecycle". Si existe pero corrupto: `lifecycle.disponible=False`,
`tecnico=True`, mensaje explícito de corrupción (nunca oculto como simple N/A silencioso, R17).

### R8 — MLOps Foundations
Reuso directo de `mlops_foundations.evaluar_foundations(repo_root)` (Change 5) — sin
reinterpretar severidad acá (eso es exclusivo de `readiness.py` para el contexto de promoción,
Change 6 R16/R17 — `status` muestra el WARN de `mlops_foundations` como WARN, tal cual, nunca lo
convierte a FAIL fuera del contexto de `readiness`).

### R9 — Production Readiness / Operations (reuso directo de Change 6)
Por cada una de las 5 capabilities de `production_readiness` y las 7 de `operations`:
`mlops_evidence.evidencia_valida(repo_root, tier, capability)` (Change 6, sin reimplementar) →
`{"capability": ..., "valido": bool, "detalle": <mensaje devuelto tal cual, ya distingue
ausente/obsoleta, sin re-parsearlo a un enum nuevo>}`. Nunca se llama
`mlops_evidence.agregar_evidencia` desde `status` (solo lectura estricta).

### R10 — Proporcionalidad por stage (nunca oculta datos, solo resume)
- `project_stage=discovery`: `mlops.production_readiness`/`mlops.operations` se muestran
  colapsados (`"aplicable": False`, mensaje "not applicable at current stage"), sin evaluar las
  12 capabilities una por una en el output compacto (si `--verbose`, sí se listan igual, con el
  mismo `"aplicable": False` por capability, para quien lo pida explícitamente).
- `project_stage=experiment`: `mlops.production_readiness` se muestra en detalle;
  `mlops.operations` colapsado (`"aplicable": False`, "future").
- `project_stage∈{production_candidate,production}`: ambas secciones en detalle completo.
Esta proporcionalidad NUNCA afecta a `readiness.evaluar_readiness` (Change 6 sigue evaluando el
target pedido siempre completo, sin importar el stage actual) — solo afecta qué tan detallado se
muestra el INVENTARIO de capabilities en `mlops.*`.

### R11 — Harness integrity (degradación con gracia, sin copiar Doctor)
`harness.disponible`: `True` solo si `tools.harmessi.doctor` puede importarse Y
`doctor.ejecutar(repo_root)` corre sin excepción — ambos casos envueltos en un único
`try/except Exception` (import perezoso + llamada), nunca una excepción cruda escapa de esta
sección. Si `disponible=True`: `{"ok": N, "warn": N, "error": N, "na": N, "principales":
[hasta K mensajes WARN/ERROR más relevantes]}` (K pequeño, ej. 5 — nunca la lista completa de
Doctor salvo `--verbose`). Si `disponible=False`: `{"disponible": False, "motivo": "doctor no
disponible en este árbol — correr 'harmessi doctor' desde el checkout fuente de Harmessi para
diagnóstico completo"}` — nunca se trata como error, es un estado legítimo y esperado para
cualquier proyecto instalado (Doctor y `ds_init` nunca se instalan en destinos, confirmado en
`proposal.md § Evidencia`).

### R12 — Read-only estricto (gate fuerte)
`evaluar_status`/`formatear_texto`/`formatear_json` NUNCA escriben: `.harmessi/project.json`,
`.ds_init/control.json`, `openspec/lifecycle/state.json`, ninguna evidencia MLOps, ningún
`decision`, ningún `openspec/changes/*`. Tests byte-a-byte antes/después para cada archivo
relevante, en todos los escenarios del §25 del brief.

### R13 — Ausencia/corrupción (fail closed, nunca traceback crudo)
- `.harmessi/project.json` ausente → `project.disponible=False`, `project_stage=None`
  ("uninitialized"), `risk_level="unclassified"`.
- `.harmessi/project.json` corrupto → `project.disponible=False`, `tecnico=True`, mensaje
  explícito (nunca simplemente "unclassified" silencioso — la corrupción se distingue de la
  ausencia legítima).
- `.ds_init/control.json` ausente → `installation.disponible=False`, `installation_stage=None`
  ("unknown").
- `.ds_init/control.json` corrupto → `installation.disponible=False`, `tecnico=True`.
- `openspec/lifecycle/state.json` ausente/corrupto → ver R7.
- Ninguna excepción no controlada escapa de `evaluar_status` bajo ningún escenario de los
  anteriores — cada sub-sección maneja sus propios errores de dominio (mismo patrón "con-dato" ya
  usado en `mlops_foundations.py`/`doctor.py`/`readiness.py`).

### R14 — JSON estable, explícitamente experimental
`formatear_json`/`status.evaluar_status` producen un dict serializable determinista (mismo input
→ mismo output, salvo timestamps si los hubiera — este change no persiste ninguno nuevo). Forma
conceptual: `{"project": {...}, "installation": {...}, "alignment": {...}, "lifecycle": {...},
"mlops": {...}, "readiness": {...}, "harness": {...}}`. Se documenta explícitamente como
"experimental/interno, sin garantía de estabilidad de schema todavía" (mismo criterio que
`design.md` de Changes previas para superficies nuevas sin contrato público comprometido) — no se
versiona como schema público en este change.

### R15 — Manifest
`tools/dsguard/status.py` con entrada VERBATIM en `MANIFEST`. Test de paridad explícito. Scratch
install: el archivo debe quedar presente y `ds_guard status` (sin `--change-id`) debe correr sin
`ImportError` desde el destino instalado — incluida la degradación con gracia de `harness`
(§R11, ya que `tools/harmessi/doctor.py` NO se instala) y de `installation`/`origen="inferido"`
cuando corresponda (`tools/ds_init/legacy.py` tampoco se instala).

## Criterios de aceptación

**CLI / no colisión:**
- `ds_guard status --change-id <id>` (existente) sin cambios: mismos resultados que antes de
  este change, byte a byte donde aplique.
- `ds_guard status` (sin `--change-id`) → nuevo status unificado, exit 0.
- `ds_guard status --json` (sin `--change-id`) → JSON válido, mismas secciones.
- `ds_guard status --verbose` (sin `--change-id`) → detalle completo de checks, no solo resumen.

**Stages (project_stage):**
- `discovery`: `mlops.production_readiness`/`operations` colapsados; `readiness.next_target ==
  "experiment"`.
- `experiment`: `production_readiness` en detalle, `operations` colapsado;
  `next_target == "production_candidate"`.
- `production_candidate`: ambos en detalle; `next_target == "production"`.
- `production`: ambos en detalle; `next_target is None`, mensaje explícito de "stage final".

**Alignment:**
- `project_stage == installation_stage` → `"aligned"`.
- `project_stage` más avanzado → `"sync_needed"`, mensaje con el comando `sync` exacto.
- `installation_stage` más avanzado → `"ahead"` (nunca `"error"`/tratado como corrupción).
- `control.json` sin `installation_stage`, con inferencia disponible (repo fuente) →
  `origen="inferido"`, resultado correcto según `legacy.inferir_installation_stage`.
- `control.json` sin `installation_stage`, sin `tools.ds_init` disponible (simulado con
  monkeypatch de import) → `origen="desconocido"`, `alignment="unknown"`, sin excepción.

**Risk:**
- `risk_level=None` → `"unclassified"`.
- `low`/`medium`/`high` → mostrados tal cual.
- `project_stage>=production_candidate` con `risk_level=None` → `status` no falla, solo refleja
  el `FAIL` correspondiente que ya viene de `readiness.evaluar_readiness` en `blocking`.

**Lifecycle:**
- Parcial (algunas fases cerradas) → resumen correcto `N/8`/`N/5`.
- Completo (8/8, 5/5) → resumen correcto.
- Ausente → `lifecycle.disponible=False`, mensaje "lifecycle unavailable".
- Corrupto → `lifecycle.disponible=False`, `tecnico=True`, mensaje distinto del de ausencia.

**Foundations:**
- Cada uno de los 4 resultados de `mlops_foundations.evaluar_foundations` se refleja tal cual
  (`PASS`/`WARN`/`N/A`), nunca reinterpretado a `FAIL` (eso es exclusivo de `readiness.py`).
- `.harmessi/project.json` ausente → `N/A` (mismo comportamiento que `mlops_foundations.py` ya
  documenta), `status` no lo oculta ni lo reinterpreta.

**Readiness:**
- `next_target` con todo satisfecho → `"READY"`.
- Con algún `FAIL` → `"NOT READY"`, `blocking` lista los `FAIL` principales.
- Con algún `technical_error` → resumen `"TECHNICAL ERROR"` (nunca `"NOT READY"` genérico que lo
  esconda), visible explícitamente en `blocking`.
- `project_stage=production` → `next_target=None`, sin evaluar ningún target ("no existe próximo
  stage normal", nunca se inventa madurez post-producción).

**Evidence (production_readiness/operations):**
- Capability con evidencia válida → `valido=True`.
- Sin evidencia → `valido=False`, detalle "sin evidencia" (o equivalente).
- Evidencia obsoleta (archivo borrado/modificado tras registrar) → `valido=False`, detalle
  distingue "obsoleta" de "ausente" (reusa el mensaje de `mlops_evidence.evidencia_valida` tal
  cual, sin reimplementar la distinción).

**Harness:**
- Corrido desde el checkout fuente de Harmessi (este repo) → `disponible=True`, conteos
  correctos, coinciden con `harmessi doctor` corrido directo sobre el mismo repo en el mismo
  instante (mismo conteo OK/WARN/ERROR/N-A).
- Simulado "proyecto instalado" (mock de `ImportError` en el import perezoso, o fixture de
  destino real sin `tools/harmessi/`) → `disponible=False`, mensaje claro, sin excepción, el
  resto de las secciones de `status` se muestran igual (no se corta el resto del output).

**Read-only:**
- Bytes idénticos de `.harmessi/project.json`, `.ds_init/control.json`,
  `openspec/lifecycle/state.json` antes/después de `evaluar_status`, en TODOS los escenarios
  anteriores (incluidos los de ausencia/corrupción/technical_error).
- Ninguna llamada a `agregar_evidencia`/`escribir_estado`/`calibrar`/`promote`/`set_risk` desde
  `status.py` (grep explícito, cero ocurrencias).

**JSON:**
- Determinista: mismo estado de disco → mismo JSON, dos corridas seguidas.
- Serializable con `json.dumps` sin necesitar un encoder custom.
- No muta nada (mismo criterio read-only que el resto).

**Output humano:**
- Determinista, compacto (sin repetir el mismo hallazgo en dos secciones distintas de forma
  redundante — p. ej. un `FAIL` de readiness no se repite palabra por palabra también en
  `mlops.production_readiness` si ya se resume ahí con su propio detalle corto).

**Regresión:**
- `tools/tests/`, `tools/harmessi/tests/`, `tools/ds_init/tests/` completos sin regresión.
- Manifest: paridad explícita para `status.py`; scratch install deja el archivo presente y
  `ds_guard status` corre sin `ImportError` desde el destino (con `harness.disponible=False`,
  esperado).
- `harmessi doctor` sobre este repo: mismo conteo de `[ERROR]` que el baseline declarado (26 OK /
  5 WARN / 0 ERROR / 1 N/A), sin corregir WARN/N-A existentes salvo bug real revelado por este
  change (ninguno esperado, ya que `status.py` es aditivo puro).

## Unidad de análisis / grain (condicional — data_understanding, feature_engineering, modeling)
No aplica — cambio de arquitectura/tooling del harness.

## Cutoff / information boundary (condicional — feature_engineering, data_preparation, modeling)
No aplica.

## Baseline (condicional — modeling)
No aplica.

## Métrica primaria (condicional — modeling, evaluation)
No aplica.

## Métricas secundarias (opcional)
No aplica.

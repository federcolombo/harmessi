# Spec — 20260915-lead-methodology-awareness

## Requisitos

### R1 — `methodology.md` (nuevo)
Nuevo documento en `.claude/skills/lead-data-scientist/methodology.md` (+ fuente
`tools/ds_init/profiles/python_jupyter_data/templates/methodology.md.tmpl`, tratamiento
`PLANTILLA`, `stage_minimo="discovery"` — debe estar disponible desde el primer momento, no es
contenido de un stage superior). Leído bajo demanda desde `SKILL.md` (mismo patrón que `kdd.md`/
`eda.md`/`decision-ledger.md` — nunca por defecto). Contenido mínimo, cada uno como sección
propia y verificable:

- **Jerarquía metodológica** (brief §2): CRISP-DM como backbone del lifecycle del proyecto; KDD
  como proceso técnico subordinado dentro de las fases relevantes (`data_understanding→selection`,
  `data_preparation→preprocessing+transformation`, `modeling→data_mining`,
  `evaluation→interpretation_evaluation`); MLOps como capacidades progresivas desde `experiment`;
  SDD como protocolo transversal para cambios controlados. Nunca presentados como 4 metodologías
  competidoras. No se cambia el schema de `openspec/lifecycle/state.json`.
- **Comportamiento por `project_stage`** (brief §3): `discovery` (liviano, viabilidad/perfilado,
  no exige modelo/packaging/inference contract/monitoring/operations, no delega trabajo de
  producción prematuramente), `experiment` (default del trabajo DS normal, stack completo,
  reproducibilidad básica/artifacts/foundations MLOps), `production_candidate` (prioriza
  packaging/environment/inference contract/inference tests/trazabilidad fuerte/deployment
  readiness/operations gaps, nunca asume production-ready solo por scaffold instalado),
  `production` (prioriza deployment/monitoring/drift/alerts/rollback/retraining, nunca inventa un
  stage posterior).
- **Status como puerta de entrada** (brief §4): antes de planificar trabajo sustancial, consultar
  `python -m tools.ds_guard status --json` (o equivalente humano); nunca recalcular manualmente lo
  que `status`/`readiness` ya calculan; si no está disponible por razones legítimas (proyecto
  instalado sin `tools/harmessi/doctor.py`/`tools/ds_init/legacy.py`, Change 8), degradar con
  gracia usando las fuentes existentes, nunca inventar valores.
- **`project_stage` ≠ `installation_stage`** (brief §5): distinción explícita permanente;
  `project_stage > installation_stage` → indicar sync pendiente, nunca bajar `project_stage` ni
  sincronizar silenciosamente; `installation_stage > project_stage` → herramientas disponibles
  anticipadamente, nunca asumir mayor madurez ni promover; nunca usar `installation_stage` como
  proxy de readiness.
- **Readiness** (brief §6): usar `python -m tools.ds_guard project readiness --target <stage>`
  cuando el objetivo implique promoción; PASS/WARN/FAIL/N-A vienen del engine, nunca
  reinterpretados por intuición; `technical_error` siempre tratado como problema técnico; nunca
  recomendar `promote` si `readiness` no está READY.
- **Promotion** (brief §7): recomendar/ejecutar `promote` solo cuando el usuario lo pide o forma
  parte del objetivo aprobado, `readiness` está READY, y el target es el siguiente stage
  permitido; `calibrate` nunca como bypass de promoción normal (es adopción/calibración
  excepcional); nunca escribir `project.json` manualmente. Sintaxis exacta documentada:
  `ds_guard project promote <stage> --reason "<texto>"` (posicional, sin `--target`).
- **Risk level** (brief §8): `null`→unclassified, `low|medium|high`→classified; nunca inferir risk
  automáticamente en adopción/migración; señalar clasificación pendiente si una promoción a
  `production_candidate` la requiere; sin governance distinta por nivel (fuera de alcance).
- **Lifecycle** (brief §9): nunca marcar una fase cerrada "porque parece terminada" — exigir
  evidencia real/change asociado/operación determinista existente; nunca escribir
  `lifecycle/state.json` manualmente salvo flujo gobernado explícito; `fase_actual`/`paso_actual`
  nunca se persisten (son derivados, ya así desde Change 1).
- **KDD** (brief §10): razonar con los 5 pasos canónicos (`selection`, `preprocessing`,
  `transformation`, `data_mining`, `interpretation_evaluation`); las 10 etapas legacy existen solo
  como compatibilidad (pueden aparecer en SDD/decision ledger antiguos), nunca como taxonomía
  metodológica principal; sin romper compatibilidad con `kdd_compat.py`.
- **MLOps foundations** (brief §11): reproducibilidad/versionado/lineage/artifacts desde
  `experiment`; foundation PASS ≠ production ready (ejemplo explícito: `artifacts` PASS por
  `profile.json` no implica packaging/inference contract).
- **Evidence** (brief §12): `mlops evidence add` registra integridad determinista (archivo
  identificado, hash, persistencia) — nunca demuestra automáticamente calidad semántica,
  suficiencia metodológica o corrección científica; LLM/reviewer evalúa semántica, binario valida
  integridad/gate; nunca registrar templates/scaffold como evidencia real.
- **SDD** (brief §13): protocolo transversal, proporcional (no burocracia innecesaria para
  correcciones mínimas si las reglas actuales ya permiten un camino más liviano); consultar el
  estado SDD existente antes de actuar; nunca crear changes paralelos para el mismo objetivo.
- **Decision ledger** (brief §14): decisiones metodológicas/relevantes reales solamente; nunca
  ruido, cada test, cada edición, cada promoción automática, o información que ya vive en
  `stage_history`.
- **One writer** (brief §15): solo `python-data-engineer` edita código/notebooks; Lead decide/
  orquesta; `metodologo` revisión metodológica; `data-science-reviewer` revisión técnica read-only;
  `notebook-runner` ejecución controlada; nunca múltiples writers concurrentes sobre el mismo
  cambio; nunca delegación entre subagentes (ninguno tiene la herramienta Agent, ya así desde
  `SKILL.md` actual).
- **Delegación proporcional** (brief §16): las 6 preguntas previas a usar Agent; nunca delegar por
  reflejo; nunca agentes de espera/monitoreo/placeholder; nunca subagentes para tareas
  administrativas triviales.
- **Bounded remediation** (brief §17): patrón writer→reviewer→writer fixes→cierre, máximo 2 ciclos,
  después STOP y escalar; reanudar el mismo task-id por turn limit en vez de abrir otro agente
  equivalente (ya el criterio de eficiencia usado en Changes 6-8 de esta misma serie).
- **Notebooks** (brief §18): `NotebookEdit` modifica estructura/celdas, NO ejecuta; "los números
  salen de la corrida", nunca se infieren métricas sin corrida real.
- **EDA** (brief §19): separación Project EDA (model-valid: cutoff/holdout/leakage/fingerprints) vs
  exploratory/reporting flexible (debe etiquetarse explícitamente no-model-valid cuando
  corresponda); nunca mezclar ambos; reporting avanzado sigue fuera de alcance.
- **Human-in-the-loop** (brief §20): lista de detenciones reales (definición de problema, decisión
  de negocio, risk classification con criterio humano, trade-offs metodológicos materiales,
  aceptación de deuda/riesgo, cambio arquitectónico, bypass/exemption no previsto, interpretación
  que el binario no resuelve); nunca preguntar por cuestiones mecánicas que el sistema ya
  determina.
- **Fail-closed** (brief §21): ante `project.json`/`lifecycle`/`control` corrupto, `technical_error`,
  o contradicción de fuentes — nunca continuar como si fuera N/A; identificar el problema técnico,
  repararlo antes de decisiones dependientes, nunca inventar estado.
- **Nuevo proyecto vs adopción** (brief §22): nuevo proyecto → `experiment` por defecto, `discovery`
  solo si elegido explícitamente; proyecto adoptado → reglas de adopción/migración existentes
  (`maturity.py`), nunca inferir risk, nunca reescribir madurez arbitrariamente, sin heurísticas
  nuevas fuera de `maturity.py`.
- **Workflow base** (brief §23): Inspect (status/objetivo humano/estado SDD) → Classify
  (project_stage/área de lifecycle/riesgo/si requiere cambio controlado) → Plan (mínimo trabajo
  necesario/roles estrictamente necesarios/gates aplicables) → Execute (one writer/herramientas
  deterministas/evidencia real) → Verify (tests/corrida/reviewer si corresponde/readiness solo
  cuando aplica) → Close (SDD/status/decisión humana pendiente). No es una nueva máquina de
  estados — es guía de proceso, sin persistencia propia.
- **Acciones prohibidas del Lead** (brief §24): lista explícita verbatim de las 15 prohibiciones
  del brief (editar `project_stage`/`installation_stage` manualmente, cerrar lifecycle por
  intuición, inventar PASS, convertir WARN en PASS, registrar template como evidencia, usar
  `calibrate` como bypass, promover con FAIL, instalar capabilities silenciosamente, duplicar
  gates en prompts, inferir risk en adopción, asumir datos/métricas no ejecutados, abrir agentes
  de espera, delegar al reviewer escritura, permitir dos writers).

### R2 — `SKILL.md`
Sección `## KDD (lifecycle del proyecto)` (líneas 88-98 actuales) corregida: ya NO describe KDD
como "el lifecycle del proyecto" con las 10 etapas legacy como referencia primaria — encuadra
CRISP-DM como backbone, apunta a `methodology.md` para la jerarquía completa (lectura bajo
demanda), y preserva sin cambios el resto del contenido operativo ya correcto de esa sección
(cómo un change declara su etapa KDD, `sync` al cerrar — eso sigue siendo válido y no se toca).
Nuevo pointer a `methodology.md` agregado en el lugar natural (junto a los pointers existentes a
`sdd.md`/`kdd.md`/`eda.md`), mismo patrón "se lee bajo demanda, nunca por defecto". `SKILL.md` NO
crece de forma descontrolada — el contenido nuevo sustancial vive en `methodology.md`, no en
`SKILL.md`.

### R3 — `kdd.md`/`decision-ledger.md`
Frase de encuadre corregida en ambos (`kdd.md §1`, `decision-ledger.md §1`): ya no afirman que
"KDD es el lifecycle del proyecto" sin matiz — aclaran que CRISP-DM es el backbone real y KDD es
subordinado dentro de él, con pointer a `methodology.md`. El resto de ambos documentos (modelo de
datos, comandos, ownership) no se reescribe salvo esa frase puntual.

### R4 — `verificador.md`
Nuevas entradas, mismo estilo terso ya usado (nombre + firma + una línea de comportamiento +
exit codes si difieren del patrón general ya documentado), para: `lifecycle migrate`; `project
init [--stage|--adopt] [--json]`, `project calibrate --stage <stage> --reason <texto> [--json]`,
`project set-risk <nivel> --reason <texto> [--json]`, `project status [--json]`, `project
readiness --target <stage> [--json]`, `project promote <stage> --reason <texto> [--json]`; `mlops
status [--json]`, `mlops record [--json]`, `mlops evidence add --tier <tier> --capability <cap>
--artifact <ruta> --reason <texto> [--json]`; `status [--change-id <id>] [--json] [--verbose]`
(unificado, sin `--change-id`). Nunca duplica el detalle de diseño/gates (vive en los `design.md`
de Changes 1/3/5/6/8) — solo sintaxis de invocación y comportamiento observable, mismo nivel de
detalle que las entradas ya existentes de `session *`/`decision *`.

### R5 — Corrección de sintaxis en `production-readiness.md.tmpl`/`operations.md.tmpl`
Ambos archivos: `ds_guard project promote --target <stage> --reason <texto>` →
`ds_guard project promote <stage> --reason <texto>` (elimina `--target`, `<stage>` pasa a
posicional) — coincide exactamente con `tools/ds_guard.py:1473-1479`. Único cambio de contenido en
estos dos archivos; el resto no se toca.

### R6 — Sincronización `.tmpl` ↔ copia renderizada
Todo archivo tocado (`SKILL.md`, `kdd.md`, `decision-ledger.md`, `verificador.md`,
`production-readiness.md`, `operations.md`, `methodology.md` nuevo) se edita en AMBAS ubicaciones:
la fuente `.tmpl` en `tools/ds_init/profiles/python_jupyter_data/templates/` y la copia renderizada
en `.claude/skills/lead-data-scientist/` de este propio repo (self-hosted) — ambas deben quedar
consistentes (mismo contenido salvo los placeholders `{{...}}` que solo existen en el `.tmpl`, si
los hubiera; estos documentos en particular no usan placeholders de proyecto, así que deben quedar
byte-idénticos salvo diferencias triviales de línea final).

### R7 — Manifest
`methodology.md.tmpl` con entrada `PLANTILLA` en `MANIFEST`, mismo patrón que `kdd.md.tmpl`/
`eda.md.tmpl`/`decision-ledger.md.tmpl` (`fuente=f"{_dir_templates(...)}/methodology.md.tmpl"`,
`tratamiento=PLANTILLA`, `destino=".claude/skills/lead-data-scientist/methodology.md"`,
`stage_minimo` default = `"discovery"`, sin necesidad de especificarlo explícito ya que ese es el
default). Ningún otro archivo cambia su clasificación de `stage_minimo` (los 5 docs existentes que
se editan mantienen exactamente el `stage_minimo` que ya tenían desde Change 7).

### R8 — No cambiar runtime salvo el bug demostrado
Ningún archivo de `tools/dsguard/`, `tools/harmessi/`, `tools/ds_init/{cli,planner,writer,control,
legacy,manifest}.py` (salvo la nueva entrada de manifest del R7) se modifica. La única excepción es
puramente de contenido de documentación (R5), no de comportamiento de `ds_guard.py` en sí — el
propio `ds_guard.py` ya acepta correctamente la sintaxis posicional hoy, no se toca su parser.

## Criterios de aceptación

**Contenido — presencia de conceptos clave** (verificable con búsqueda de texto simple sobre los
`.tmpl`, sin parser de Markdown):
- `methodology.md.tmpl` contiene los 5 pasos KDD canónicos por nombre exacto, las 8 fases
  CRISP-DM por nombre exacto, y las 4 llaves de `PROJECT_STAGES`
  (discovery/experiment/production_candidate/production) por nombre exacto.
- `methodology.md.tmpl` contiene la frase (o equivalente verificable) que distingue
  `project_stage` de `installation_stage` explícitamente, y no los presenta como sinónimos.
- `methodology.md.tmpl` contiene la sintaxis exacta `ds_guard project promote <stage> --reason`
  (sin `--target`) y `ds_guard project readiness --target <stage>` (con `--target`) — cada
  comando con su sintaxis real, no intercambiadas.
- `methodology.md.tmpl` contiene las 14 prohibiciones explícitas del brief §24 (verificable por
  presencia de cada frase clave — "no editar project_stage manualmente", "no usar calibrate como
  bypass", "no registrar template como evidencia", etc.).
- `methodology.md.tmpl` NO contiene las 10 etapas legacy (`problem_understanding`, etc.)
  presentadas como catálogo principal — pueden mencionarse solo en el contexto de "compatibilidad
  legacy", nunca como la lista canónica de pasos.

**No referencias obsoletas**:
- `SKILL.md` ya NO contiene la frase "KDD... es en qué etapa del lifecycle de Data Science está el
  proyecto" sin matiz de CRISP-DM backbone.
- `kdd.md`/`decision-ledger.md` corregidos de la misma forma puntual.
- Ningún documento de la skill (los 7 tocados) presenta CRISP-DM/KDD/MLOps/SDD como "cuatro
  metodologías" coordinadas/paralelas sin jerarquía.

**Sintaxis de CLI corregida**:
- `production-readiness.md.tmpl`/`operations.md.tmpl` ya NO contienen `--target` en la línea de
  `promote` — contienen `<stage>` posicional, verificado por búsqueda de texto exacta.
- Ningún comando documentado en `verificador.md`/`methodology.md`/`production-readiness.md`/
  `operations.md` usa una sintaxis que `tools/ds_guard.py` rechace (verificable corriendo cada
  comando documentado con `--help` o en modo dry/read-only real, sin mutar nada).

**Sincronización `.tmpl` ↔ renderizado**:
- Cada uno de los 7 archivos tocados tiene contenido idéntico entre su `.tmpl` fuente y su copia
  en `.claude/skills/lead-data-scientist/` de este repo (diff vacío o solo diferencias triviales
  de terminador de línea).

**Manifest**:
- `methodology.md.tmpl` presente en `MANIFEST` con tratamiento `PLANTILLA`, destino correcto.
- Test de paridad no rompe (el nuevo archivo sigue el mismo patrón que sus hermanos).
- Scratch install (discovery y experiment, según Change 7) deja `methodology.md` presente en el
  destino en ambos stages (es `stage_minimo="discovery"`, siempre incluido).

**Regresión**:
- `tools/tests/`, `tools/harmessi/tests/`, `tools/ds_init/tests/` completos sin regresión.
- `harmessi doctor` sobre este repo: mismo conteo de `[ERROR]` que el baseline vigente (ver
  verification.md para el valor exacto capturado al momento de correr) — el único cambio esperable
  es el drift transitorio ya conocido de trabajo sin commitear, nunca un `[ERROR]` nuevo.
- Manifest parity: `methodology.md.tmpl` cubierto por el mecanismo de paridad ya existente (mismo
  patrón AST-scan/lista explícita que el resto de `.tmpl` de la skill — confirmar si esos ya están
  cubiertos por el test genérico o necesitan una entrada explícita, y actuar en consecuencia sin
  inventar un mecanismo de test nuevo).

## Unidad de análisis / grain (condicional — data_understanding, feature_engineering, modeling)
No aplica — cambio de documentación/orquestación del harness.

## Cutoff / information boundary (condicional — feature_engineering, data_preparation, modeling)
No aplica.

## Baseline (condicional — modeling)
No aplica.

## Métrica primaria (condicional — modeling, evaluation)
No aplica.

## Métricas secundarias (opcional)
No aplica.

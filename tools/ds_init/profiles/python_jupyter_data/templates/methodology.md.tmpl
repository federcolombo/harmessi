# Metodología del Lead — jerarquía, comportamiento y prohibiciones (referencia)

Se lee bajo demanda, nunca por defecto — mismo patrón que `kdd.md`/`eda.md`/`decision-ledger.md`.
Documento de referencia transversal: no duplica el detalle operativo de comandos que ya vive en
`verificador.md`/`kdd.md`/`eda.md`/`decision-ledger.md`/`production-readiness.md`/`operations.md`
— enlaza a esos documentos para eso. Este documento resuelve la pregunta que ninguno de ellos
responde por sí solo: **cómo se relacionan entre sí, y qué espera el brief del Lead en cada caso.**

## 1. Jerarquía metodológica: no son cuatro metodologías paralelas

CRISP-DM es el **backbone** del lifecycle del proyecto — las 8 fases de
`openspec/lifecycle/state.json` (`tools/dsguard/lifecycle.py`, `FASES_CRISPDM`):
`business_understanding`, `data_understanding`, `data_preparation`, `modeling`, `evaluation`,
`production_readiness`, `deployment`, `monitoring`.

KDD es el **proceso técnico subordinado**, dentro de las fases CRISP-DM relevantes — los 5 pasos
canónicos (`PASOS_KDD`): `selection`, `preprocessing`, `transformation`, `data_mining`,
`interpretation_evaluation`. Mapeo exacto (`MAPEO_CRISPDM_A_KDD`):

| Fase CRISP-DM | Paso(s) KDD |
|---|---|
| `data_understanding` | `selection` |
| `data_preparation` | `preprocessing`, `transformation` |
| `modeling` | `data_mining` |
| `evaluation` | `interpretation_evaluation` |

MLOps son **capacidades progresivas** que se acumulan desde `experiment` en adelante
(`foundations` → `production_readiness` → `operations`, ver §10).

SDD es el **protocolo transversal** para cambios controlados — no una etapa del lifecycle, corre
sobre cualquier fase/paso/tier (ver §12).

Nunca se presentan como cuatro metodologías competidoras o coordinadas en pie de igualdad: CRISP-DM
es el marco, KDD vive adentro de CRISP-DM, MLOps es una dimensión ortogonal de madurez técnica, y
SDD es el mecanismo con el que se ejecuta cualquier cambio dentro de todo lo anterior. No se cambia
el schema de `openspec/lifecycle/state.json` para expresar esto — es una lectura del schema ya
existente, no una estructura nueva.

## 2. Comportamiento por `project_stage`

`project_stage` (`tools/dsguard/maturity.py`, `PROJECT_STAGES`) tiene 4 valores:
`discovery`, `experiment`, `production_candidate`, `production`. El Lead adapta su comportamiento
según cuál esté vigente:

- **`discovery`**: liviano — viabilidad y perfilado de datos. No exige modelo entrenado, packaging,
  inference contract ni monitoring/operations. No delega trabajo de nivel producción
  prematuramente (packaging, contratos de inferencia, CI/CD) solo porque el harness ya tenga las
  herramientas instaladas.
- **`experiment`**: el default del trabajo de Data Science normal. Stack completo disponible,
  reproducibilidad básica, artifacts y foundations MLOps ya exigibles (§10).
- **`production_candidate`**: prioriza packaging, entorno reproducible, inference contract,
  inference tests y trazabilidad fuerte (§5-§6, `production-readiness.md`). Nunca asume que el
  proyecto ya es production-ready solo porque el scaffold de esa etapa está instalado
  (`installation_stage`, ver §4) — eso es exactamente la confusión que §4 prohíbe.
- **`production`**: prioriza deployment, monitoring, drift, alerts, rollback y retraining
  (`operations.md`). Nunca inventa un stage posterior a `production` — es el último de
  `PROJECT_STAGES`.

## 3. `status` como puerta de entrada

Antes de planificar trabajo sustancial, el Lead consulta `python -m tools.ds_guard status --json`
(status unificado, sin `--change-id` — Change 8) o su equivalente legible por humano
(`ds_guard status`). Nunca recalcula a mano lo que `status`/`readiness` ya calculan (`project_stage`
vigente, gaps de foundations, próximo target sugerido). Si `status` no está disponible por una
razón legítima (proyecto instalado sin `tools/harmessi/doctor.py` ni `tools/ds_init/legacy.py`
— superficies opcionales, ver `tools/dsguard/status.py`), el Lead degrada con gracia usando las
fuentes deterministas que sí existan (`project status`, `mlops status`, `project readiness`) —
nunca inventa un valor que no pudo leer.

## 4. `project_stage` ≠ `installation_stage`

Distinción explícita y permanente, nunca sinónimos:

- **`project_stage`** (`.harmessi/project.json`, `maturity.py`): madurez **real** alcanzada por el
  proyecto — se avanza con `project calibrate`/`project promote`, nunca a mano.
- **`installation_stage`**: qué bundle de capacidades **físicas** tiene instalado el harness en este
  repo (`tools/ds_init/manifest.py`, `ORDEN_STAGES`) — un eje de instalación, no de madurez.

Reglas:
- Si `project_stage > installation_stage`: hay sync pendiente — el Lead lo señala (sugiere
  `ds_init sync --stage <stage>`), **nunca** baja `project_stage` ni sincroniza en silencio.
- Si `installation_stage > project_stage`: hay herramientas disponibles anticipadamente (p. ej.
  `production-readiness.md` ya instalado en un proyecto todavía en `experiment`) — el Lead
  **nunca** asume mayor madurez real ni recomienda `promote` solo porque la referencia esté
  disponible.
- `installation_stage` **nunca** se usa como proxy de `readiness` — son fuentes distintas
  (`tools/ds_init/manifest.py` vs. `tools/dsguard/readiness.py`), y solo la segunda gatea
  `promote`.

## 5. Readiness

Cuando el objetivo implica promoción, el Lead corre
`python -m tools.ds_guard project readiness --target <stage>` (con `--target`, targets válidos:
`experiment`, `production_candidate`, `production` — `TARGETS_VALIDOS` de `readiness.py`). Los
resultados `PASS`/`WARN`/`FAIL`/`N/A` vienen del engine (`tools/dsguard/checks.py`,
`STATUS_PASS`/`STATUS_WARN`/`STATUS_FAIL`/`STATUS_NA`) — el Lead nunca los reinterpreta por
intuición (un `WARN` no se lee como `PASS`, un `FAIL` no se minimiza). `technical_error`
(`KIND_TECHNICAL_ERROR` de `checks.py`) siempre se trata como problema técnico a resolver, nunca
como "no aplica" o dato ausente que se puede ignorar. El Lead **nunca** recomienda `promote` si
`readiness` no reporta el target como `READY`.

## 6. Promotion

El Lead recomienda o ejecuta `promote` solo cuando: (a) el usuario lo pide, o forma parte de un
objetivo ya aprobado, (b) `readiness --target <stage>` está `READY` para ese target, y (c) el
target es el siguiente stage permitido en la secuencia (`discovery → experiment →
production_candidate → production`, nunca un salto). `calibrate` **nunca** se usa como atajo para
evitar el camino normal de promoción — es para adopción o calibración excepcional de un proyecto
existente (§21), no un reemplazo conveniente de `promote`. El Lead **nunca** escribe
`.harmessi/project.json` a mano — siempre vía los comandos de `ds_guard project *`.

Sintaxis exacta (posicional, sin `--target` — a diferencia de `readiness`, que sí usa `--target`):

```
ds_guard project promote <stage> --reason "<texto>"
```

## 7. Risk level

`risk_level` (`.harmessi/project.json`, `RISK_LEVELS = ("low", "medium", "high")`) deriva un estado
binario: `null` → `unclassified`, cualquiera de `low`/`medium`/`high` → `classified`
(`estado_riesgo`, `maturity.py`). El Lead **nunca** infiere `risk_level` automáticamente durante una
adopción o migración — eso requiere criterio humano explícito (`project set-risk <nivel> --reason
<texto>`). Si una promoción a `production_candidate` la requiere y sigue `unclassified`, el Lead lo
señala como bloqueante y pendiente de decisión humana, no lo completa por su cuenta. No hay
gobernanza diferenciada por nivel de riesgo en esta versión (fuera de alcance) — `risk_level` es
clasificación, no un gate adicional per se.

## 8. Lifecycle

El Lead **nunca** marca una fase CRISP-DM o un paso KDD como `cerrada` "porque parece terminada" —
exige evidencia real: un change SDD asociado, una operación determinista existente
(`ds_guard lifecycle migrate`, `mlops record`, etc.), nunca una impresión. **Nunca** escribe
`openspec/lifecycle/state.json` a mano, salvo un flujo gobernado explícito y documentado como tal.
`fase_actual`/`paso_actual` son siempre **derivados** (roll-up determinista, nunca persistidos —
así desde Change 1): no existen como campo que alguien pueda "corregir" directamente.

## 9. KDD

El Lead razona en términos de los 5 pasos canónicos de KDD (`selection`, `preprocessing`,
`transformation`, `data_mining`, `interpretation_evaluation`, ver §1) como el vocabulario técnico
vigente. Las 10 etapas legacy de `openspec/kdd/state.json` (`problem_understanding` →
`data_understanding` → `data_preparation` → `feature_engineering` → `modeling` → `evaluation` →
`interpretation` → `production_readiness` → `deployment` → `monitoring`) existen **solo** como
superficie de compatibilidad v0.2 — pueden aparecer citadas en SDD o decision ledger antiguos, pero
**nunca** se usan como la taxonomía metodológica principal para trabajo nuevo. Esto no rompe
compatibilidad con el adapter existente (`tools/dsguard/kdd_compat.py`) — ambos vocabularios
coexisten, uno es el canónico (KDD de 5 pasos, dentro de CRISP-DM) y el otro es histórico.

## 10. MLOps foundations

Reproducibilidad, versionado, lineage y artifacts (`MLOPS_CAPACIDADES["foundations"]`,
`tools/dsguard/lifecycle.py`) son exigibles desde `experiment` en adelante — no son exclusivos de
etapas de producción. Un `PASS` de foundations **no implica** production-ready: ejemplo explícito,
`artifacts` puede dar `PASS` solo por la presencia de `profile.json`, y eso no implica que exista
packaging ni inference contract (esos viven en el tier `production_readiness`, §5-§6). El Lead nunca
confunde "tiene las bases MLOps" con "está listo para producción".

## 11. Evidence

`ds_guard mlops evidence add --tier <tier> --capability <cap> --artifact <ruta> --reason <texto>`
registra **integridad determinista**: que el archivo referenciado existe, se identificó, y su hash
quedó persistido. Eso **nunca** demuestra automáticamente calidad semántica, suficiencia
metodológica ni corrección científica de lo que ese archivo contiene — esa evaluación es del
LLM/reviewer humano, nunca del binario. El binario valida integridad y gatea la matriz; el Lead (o
el `metodologo`/`data-science-reviewer` si corresponde) evalúa si el contenido realmente alcanza. El
Lead **nunca** registra un template o scaffold sin contenido real como si fuera evidencia — eso
rompe la garantía que el propio comando existe para dar.

## 12. SDD

SDD es el protocolo transversal para cambios controlados (`sdd.md`) — se aplica de forma
**proporcional**: no es burocracia obligatoria para correcciones mínimas si las reglas de
`SKILL.md` (categoría "Pequeña y clara") ya habilitan un camino más liviano. Antes de actuar, el
Lead consulta el estado SDD existente (`ds_guard status --change-id <id>` o el `status` unificado)
— **nunca** crea un change paralelo para el mismo objetivo que otro change ya en curso está
cubriendo.

## 13. Decision ledger

El decision ledger (`decision-ledger.md`) registra decisiones metodológicas o de fondo **reales**,
ya aprobadas explícitamente por el usuario — nunca ruido. No se registra cada test, cada edición
menor, cada promoción, ni información que ya vive en `stage_history`/`control["transiciones"]`. El
criterio es: ¿esto vale la pena poder citar después sin releer el chat original? Si no, no se
registra.

## 14. One writer

`python-data-engineer` es el único subagente con permiso de escritura sobre código/notebooks. El
Lead decide y orquesta, nunca edita archivos él mismo. `metodologo` hace revisión metodológica de
solo lectura; `data-science-reviewer` hace revisión técnica de solo lectura; `notebook-runner`
ejecuta de forma controlada, sin editar. **Nunca** hay dos writers concurrentes sobre el mismo
cambio, y **nunca** un subagente delega a otro — ninguno tiene la herramienta Agent (ya así en
`SKILL.md`).

## 15. Delegación proporcional

Antes de convocar un subagente vía Agent, el Lead se hace 6 preguntas (guía de juicio, sin
mecanismo nuevo que las fuerce):

1. ¿Agrega valor real este subagente, o el Lead puede resolverlo directo con Read/Grep/Glob?
2. ¿Hay una decisión de fondo ya tomada, o la tarea es en sí misma una decisión metodológica que
   necesita `metodologo` antes de implementar?
3. ¿La tarea exige escritura real (solo `python-data-engineer` la tiene), o alcanza con lectura?
4. ¿El cupo de subagentes/intentos de la sesión actual lo permite (`SKILL.md` § Gestión de
   sesiones)?
5. ¿El contexto acotado que se le va a pasar (los 8 campos de «Contexto acotado al delegar») está
   completo, o se estaría delegando sin insumos reales?
6. ¿Convocar ahora evita releer/reexplorar innecesariamente, o es prematuro — falta evidencia que
   el Lead todavía no reunió?

Nunca se delega por reflejo. Nunca se abren agentes de espera, monitoreo o placeholder (ningún
subagente "espera" a que otra cosa termine — las convocatorias son síncronas y con un objetivo
concreto). Nunca se convocan subagentes para tareas administrativas triviales (renombrar una
variable, corregir un typo) que el routing de `SKILL.md` ya clasifica como "Pequeña y clara".

## 16. Bounded remediation

Patrón writer → reviewer → writer-corrige → cierre, con un máximo de 2 ciclos por finding
(`control["remediaciones"]`, `sdd.md` §8) — agotados, el Lead para y escala al usuario en vez de
seguir reintentando. Si lo que se agota es el presupuesto de turnos de un subagente (`maxTurns`),
el criterio es **reanudar el mismo `task-id`** en vez de abrir un agente nuevo equivalente — mismo
criterio de eficiencia ya aplicado en los changes de reliability v0.2.0/v0.3.

## 17. Notebooks

`NotebookEdit` modifica estructura y contenido de celdas — **nunca ejecuta** el notebook. "Los
números salen de la corrida" es literal: ninguna métrica, output ni resultado se infiere ni se
redacta sin una corrida real (`notebook-runner`, con su manifest versionado). El Lead nunca reporta
un número que no salió de un archivo o una corrida verificable.

## 18. EDA

Ver `eda.md` para el detalle completo. Distinción central: **Project EDA** (model-valid — respeta
cutoff/holdout/leakage, reproducible vía `profile_id`/fingerprint) es la única válida como insumo
de decisiones de modelado. **Exploratory/reporting** es más flexible, pero debe etiquetarse
explícitamente como *no-model-valid* cuando corresponda. Nunca se mezclan ambos tipos de EDA en el
mismo artefacto sin dejar claro cuál es cuál. Reporting avanzado sigue fuera de alcance de esta
versión.

## 19. Human-in-the-loop

El Lead se detiene y consulta al usuario, siempre, ante:

- Definición del problema u objetivo de negocio.
- Cualquier decisión de negocio real.
- Clasificación de `risk_level` (requiere criterio humano, nunca inferencia automática — §7).
- Trade-offs metodológicos materiales (target, features, validación, métrica, umbral).
- Aceptación consciente de deuda técnica o riesgo conocido.
- Cambio arquitectónico.
- Cualquier bypass o excepción no prevista por las reglas ya deterministas.
- Interpretación de un resultado que el binario no resuelve por sí solo (p. ej. si una evidencia
  "alcanza" metodológicamente).

Nunca se pregunta por cuestiones mecánicas que el sistema ya determina (un `PASS`/`FAIL` de
`readiness`, si un archivo está en `MANIFEST`, etc.) — eso se lee, no se consulta.

## 20. Fail-closed

Ante `.harmessi/project.json`, `openspec/lifecycle/state.json` o `control.json` corrupto, un
`technical_error` reportado por cualquier engine, o una contradicción entre fuentes (p. ej.
`tasks.md estado:` vs. la última transición de `control.json`) — el Lead **nunca** continúa como si
fuera "no aplica" ni sigue adelante con la decisión dependiente. Identifica el problema técnico
concreto, lo repara (o pide que se repare) antes de tomar cualquier decisión que dependiera de ese
dato, y nunca inventa un valor de reemplazo.

## 21. Nuevo proyecto vs. adopción

- **Proyecto nuevo**: `project_stage` por defecto es `experiment` — `discovery` solo si se elige
  explícitamente (`project init --stage discovery`).
- **Proyecto adoptado** (código/datos preexistentes que se incorporan al harness): siguen las
  reglas de adopción/migración ya existentes en `maturity.py` (`project init --adopt`). El Lead
  **nunca** infiere `risk_level` en una adopción, **nunca** reescribe la madurez detectada de forma
  arbitraria, y no inventa heurísticas nuevas fuera de las que ya implementa `maturity.py` — si el
  engine no cubre un caso, se consulta al usuario, no se improvisa.

## 22. Workflow base

No es una máquina de estados nueva ni tiene persistencia propia — es guía de proceso sobre el
trabajo ya existente (SDD, sesiones, delegación):

1. **Inspect**: `status`/`readiness` (§3), objetivo humano del pedido, estado SDD existente (§12).
2. **Classify**: `project_stage` vigente (§2), a qué área del lifecycle pertenece (§1), nivel de
   riesgo, si requiere un change SDD controlado (categoría de `SKILL.md`).
3. **Plan**: el trabajo mínimo necesario, los roles estrictamente necesarios (§15), los gates
   aplicables (§5-§6, §10-§11).
4. **Execute**: un solo writer (§14), herramientas deterministas (`ds_guard`), evidencia real
   (§11).
5. **Verify**: tests/corrida real, reviewer si corresponde, `readiness` solo cuando aplica (nunca
   se corre por rutina si el objetivo no implica promoción).
6. **Close**: SDD cerrado según corresponda, `status` reflejando el estado real, cualquier decisión
   humana pendiente señalada explícitamente — nunca cerrada por el Lead en su lugar.

## 23. Acciones prohibidas del Lead

Lista explícita, verbatim del brief — ninguna de estas 17 acciones es aceptable bajo ninguna
circunstancia, sin excepción implícita:

1. No editar `project_stage` manualmente.
2. No editar `installation_stage` manualmente.
3. No cerrar una fase de lifecycle por intuición ("parece que ya terminó").
4. No inventar un `PASS` que el engine no reportó.
5. No convertir un `WARN` en `PASS` por conveniencia o para destrabar una promoción.
6. No registrar un template o scaffold como evidencia real.
7. No usar `calibrate` como bypass de la promoción normal.
8. No promover (`promote`) con algún `FAIL` pendiente en la matriz de `readiness`.
9. No instalar capabilities silenciosamente (todo cambio de `installation_stage` es explícito, vía
   `ds_init sync`, nunca implícito).
10. No duplicar gates dentro de prompts de delegación — los gates viven en `ds_guard`, no se
    reimplementan en texto.
11. No inferir `risk_level` en una adopción.
12. No asumir datos o métricas que no salieron de una corrida real ejecutada.
13. No abrir agentes de espera (ningún subagente que quede "esperando" sin un objetivo síncrono
    concreto).
14. No delegarle escritura al `data-science-reviewer` (es de solo lectura, siempre).
15. No permitir dos writers concurrentes sobre el mismo cambio.
16. No inventar un PASS de scientific validity que el engine no reportó.
17. No tratar un N/A de scientific validity como evidencia de que la regla no aplica al proyecto
    real, sin verificar antes si lo que falta es declarar la política.

## 24. Scientific validity checks

`ds_guard science status` (y `--json`) da los checks científicos deterministas: cutoff temporal,
protección/uso de holdout, target-leakage, forbidden-features, split temporal, y baseline. Todos
se definen vía `.harmessi/scientific-policy.json` (opcional, declarativo) — nunca inferidos por
heurística.

- PASS/WARN/FAIL/N-A vienen del binario (`tools/dsguard/scientific_validity.py`) — el Lead nunca
  inventa un PASS ni reinterpreta un FAIL/WARN (mismo criterio que §5 de readiness).
- N/A significa que la regla no es evaluable según lo declarado (sección ausente o
  `declared`/`required` != true en la policy) — no "no aplica al proyecto real". Si el proyecto
  tiene un cutoff/holdout/target real pero la policy no lo declara, el N/A es señal de que falta
  declarar la política, no evidencia de que no corresponde.
- Leakage semántico (una columna que "parece" leakage sin estar en `forbidden_features`
  declaradas) sigue exigiendo juicio del Lead/`metodologo` — el binario solo detecta
  target-en-features, forbidden-features explícitas y split temporal inválido, nunca
  correlaciones ni heurísticas de nombre de columna.
- `SCI-BASELINE` en PASS nunca implica calidad del baseline — solo confirma que existe un
  artifact de evidencia no vacío (y, si se declaró hash, que no cambió). La razonabilidad del
  baseline elegido sigue siendo evaluación semántica del Lead/metodólogo.
- Antes de afirmar validez científica de un cambio, el Lead consulta `ds_guard science status` —
  nunca lo calcula a mano ni lo asume de memoria.
- `science status` es estrictamente de solo lectura — nunca escribe `.harmessi/
  scientific-policy.json`; ese archivo se declara/edita explícitamente (mismo criterio editorial
  que `guardrails.json`), nunca se genera automáticamente por observar.
- No wireado a `readiness`/`promote` todavía (decisión explícita de v0.4 Change 0, ver
  `design.md` del change) — un PASS/FAIL de scientific validity no bloquea ni habilita una
  promoción por sí solo en esta versión.

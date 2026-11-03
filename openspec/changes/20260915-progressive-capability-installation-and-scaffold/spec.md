# Spec — 20260915-progressive-capability-installation-and-scaffold

## Requisitos

### R1 — Modelo de bundles (acumulativo, sin downgrade físico)
`ORDEN_STAGES = ("discovery", "experiment", "production_candidate", "production")`. Cada archivo
administrado del manifiesto tiene `stage_minimo` en ese vocabulario. `discovery` = archivos con
`stage_minimo="discovery"`. `experiment` = discovery + archivos con `stage_minimo="experiment"`.
`production_candidate` = experiment + los propios. `production` = production_candidate + los
propios. No existe ninguna operación de downgrade físico (eliminar archivos de un bundle
superior) en este change.

### R2 — Clasificación de componentes (decisión de producto de este change, ver `design.md` para
la justificación completa)
- **`stage_minimo="discovery"` (default, todo lo no re-etiquetado)**: TODO `tools/dsguard/*.py`,
  `tools/ds_guard.py`, `tools/nbrunner/*.py`, `tools/launcher_common.py`, `tools/ds_profile/*.py`
  (código runtime completo — no se puede subdividir, ver `proposal.md § Evidencia`);
  `.claude/settings.json`, `.claude/guardrails.json`; `.claude/skills/lead-data-scientist/
  {SKILL.md, sdd.md, verificador.md, kdd.md, eda.md, templates/*.md}`; `CLAUDE.md`;
  `.ds_init/control.json`.
- **`stage_minimo="experiment"`**: `.claude/agents/{python-data-engineer,data-science-reviewer,
  metodologo,notebook-runner}.md`; `.claude/skills/lead-data-scientist/decision-ledger.md`.
- **`stage_minimo="production_candidate"`**: `.claude/skills/lead-data-scientist/
  production-readiness.md` (nuevo — explica los 5 gates de `production_readiness` y cómo
  registrar evidencia vía `mlops evidence add`, sin contenido semántico de packaging/contratos).
- **`stage_minimo="production"`**: `.claude/skills/lead-data-scientist/operations.md` (nuevo —
  explica los 7 gates de `operations` y cómo registrar evidencia, sin integrar herramientas
  reales).
No se crean archivos de scaffold adicionales (contratos, configs de CI/CD, manifests de
deployment) — ver `proposal.md § Supuestos descartados`.

### R3 — Manifest
`EntradaManifiesto` gana `stage_minimo: str = "discovery"` (compatible hacia atrás — cualquier
construcción `EntradaManifiesto(fuente=..., tratamiento=..., destino=...)` existente sin ese
kwarg sigue funcionando igual, clasificada `discovery` por default). `manifest_para_perfil_y_stage
(perfil, stage)`: primero filtra por perfil (reusa `manifest_para_perfil`), después por
`ORDEN_STAGES.index(entrada.stage_minimo) <= ORDEN_STAGES.index(stage)`. `manifest_para_perfil`
NO se modifica (sigue devolviendo el set completo, comportamiento actual intacto para cualquier
caller que no pase stage).

### R4 — `construir_plan`/`writer.instalar` con stage opcional
`construir_plan(perfil, destino, config, stage=None)`: si `stage` es `None`, usa
`manifest_para_perfil(perfil)` (comportamiento actual, sin cambios). Si se pasa, usa
`manifest_para_perfil_y_stage(perfil, stage)`. `writer.instalar` lee `config.get("stage")` con el
mismo criterio para construir `entradas`/`entradas_por_destino` de forma consistente con el
`plan` recibido (ambos deben usar el mismo conjunto de entradas — nunca un `KeyError` por
desalineación). El resto de la mecánica de `writer.instalar` (staging, journal, rollback,
`_armar_staging`, `_validar_staging`) NO se modifica.

### R5 — `control.json` — campo opcional `installation_stage`
`generar_control(destino, perfil, config, archivos_aplicados, fecha_utc=None,
installation_stage=None)`: si `installation_stage is not None`, se agrega la clave
`"installation_stage"` al dict resultante; si es `None`, la clave se OMITE por completo (forma
legacy preservada byte a byte para cualquier caller que no pase el nuevo parámetro).
`regenerar_control(destino, control_previo, *, perfil=None, stage=None, installation_stage=None)`:
`stage` (si se pasa) hace que `archivos` se recalcule vía `manifest_para_perfil_y_stage` en vez de
`manifest_para_perfil`; `installation_stage` (si se pasa) se usa tal cual; si es `None`, se
preserva `control_previo.get("installation_stage")` (nunca borra un valor existente por omisión).
`_CAMPOS_CONTROL_ESPERADOS` de `doctor.py` NO incluye `installation_stage` (sigue siendo opcional,
un control.json legacy sin esa clave sigue siendo "válido").

### R6 — Inferencia legacy (`tools/ds_init/legacy.py`, nuevo)
`inferir_installation_stage(destino, perfil) -> str`: `"production"` si TODOS los archivos con
`stage_minimo="experiment"` del manifiesto vigente están presentes en `destino` (única señal
confiable disponible para instalaciones anteriores a este change — que siempre instalaban el
100% del manifiesto de su época); `"discovery"` en cualquier otro caso. Nunca distingue
`experiment`/`production_candidate`/`production` entre sí a partir de archivos legacy (no hay
señal para eso — se asume el máximo compatible con lo pedido por el usuario). Función pura,
nunca escribe nada, nunca se invoca automáticamente en una lectura simple (solo la usan `sync` —
como base antes de calcular el delta — y el nuevo check de doctor — solo para mostrar, nunca para
persistir).

### R7 — CLI `ds_init` — instalación nueva
`--stage` nuevo, opcional, `choices=["discovery","experiment"]`, default `"experiment"`. Rechaza
explícitamente (error de argparse, exit 2) `production_candidate`/`production` como stage de una
instalación NUEVA (bypass de madurez, prohibido por R9/§9 del brief). El resto de la CLI
(`--destino --nombre --notebooks-dir --venv-dir --integrar-claude --dry-run/--execute`) no
cambia de forma ni de comportamiento cuando se omite `sync` (ver R8).

### R8 — CLI `ds_init sync`
Nuevo: `python -m tools.ds_init sync --destino <path> --stage
<discovery|experiment|production_candidate|production> [--dry-run|--execute]`. Implementado como
un positional `accion` opcional con default `"install"` (preserva la invocación plana actual
100% funcionando sin cambios). Reglas:
- `--nombre`/`--notebooks-dir`/`--venv-dir`/`--integrar-claude` NO se piden para `sync` — se
  reconstruyen desde `control_previo["configuracion"]` del `.ds_init/control.json` ya existente
  en el destino.
- Requiere que `.ds_init/control.json` ya exista en `destino` (si no: error claro, "correr una
  instalación inicial primero", sin escribir nada).
- Stage base: `control_previo.get("installation_stage")` si está presente; si no,
  `legacy.inferir_installation_stage(destino, perfil)` (solo para decidir qué falta, nunca se
  persiste por el solo hecho de inferir).
- Si `ORDEN_STAGES.index(target) <= ORDEN_STAGES.index(stage_base)`: no-op explícito (mensaje
  claro, "ya instalado en un stage igual o superior — nada que hacer"), exit 0, NO escribe nada
  (ni siquiera `installation_stage`, para no fabricar una "actualización" que no ocurrió).
- Si `target` es mayor: calcula el plan con `construir_plan(perfil, destino, config, stage=target)`
  (mismo `preflight.validar_destino` que cualquier `--execute`), aplica con `writer.instalar`
  (agrega SOLO lo faltante — el resto ya son colisiones `ACCION_OMITIR_EXISTENTE`, nunca se
  tocan), y si la aplicación fue exitosa, completa `control.json` con
  `regenerar_control(destino, control_recién_escrito, perfil=perfil, stage=target,
  installation_stage=target)` (recalcula `archivos` sobre el set ACUMULADO completo hasta
  `target`, no solo el delta de esta corrida — evita que `control.json` "olvide" archivos
  instalados en corridas anteriores).
- `--dry-run` (default si no se pasa `--execute`) solo informa el plan (delta a aplicar), no
  escribe nada — mismo criterio que la instalación normal.

### R9 — `project_stage` vs `installation_stage`: independencia
Ninguna operación de este change (`sync`, `init`, `regenerar_control`) modifica
`.harmessi/project.json`. Ninguna operación de `tools/dsguard/maturity.py`/`readiness.py`
(`project init`, `calibrate`, `promote`) modifica `.ds_init/control.json`. `promote` (Change 6)
sigue teniendo exactamente su responsabilidad actual (validar readiness + actualizar
`project_stage`/`stage_history`) — no se lo toca en este change.

### R10 — Doctor: `_check_archivos_administrados` consciente de `installation_stage`
Si `control_data.get("installation_stage")` está presente: usa
`manifest_para_perfil_y_stage(perfil, installation_stage)` en vez de `manifest_para_perfil(perfil)`
para calcular el set esperado — un archivo de un stage superior al instalado NUNCA se reporta
como faltante (ni `FAIL` ni `WARN`). Si está ausente (legacy): comportamiento EXACTO actual
(`manifest_para_perfil(perfil)` completo) — 0 cambio de UX/severidad para instalaciones legacy.
`_RUTAS_CRITICAS`/severidad `ERROR` vs `WARN` por archivo NO cambia — solo cambia el universo de
archivos que se evalúa.

### R11 — Doctor: nuevo check `HARMESSI-INSTALLATION-STAGE`
Solo lectura, nunca muta nada. Lee `.harmessi/project.json` (`project_stage`, si existe y es
válido) y `control_data.get("installation_stage")` (o, si está ausente,
`legacy.inferir_installation_stage(destino, perfil)` — usado solo para MOSTRAR, nunca se
persiste desde Doctor). Reglas:
- Sin datos suficientes (`.harmessi/project.json` ausente/corrupto, o `control_data` ausente) →
  `N/A` con mensaje explicando qué falta.
- `ORDEN_STAGES.index(project_stage) > ORDEN_STAGES.index(installation_stage)` → `WARN`
  accionable: "capabilities físicas pendientes de sync — correr `python -m tools.ds_init sync
  --stage <project_stage> --execute`".
- `ORDEN_STAGES.index(installation_stage) >= ORDEN_STAGES.index(project_stage)` → `PASS`. Nunca
  `ERROR`/`FAIL` en este check bajo ningún escenario (regla explícita del usuario, §18).
No convierte Doctor en unified status (Change 8) — un único check adicional, sin nueva superficie
de UX.

### R12 — Protección de archivos del usuario
Reusa sin duplicar: `preflight.validar_destino` (working tree limpio + repo Git + sin staging
huérfano) antes de cualquier `--execute` de `sync`; `planner._accion_para_entrada` (cualquier
destino ya existente → `ACCION_OMITIR_EXISTENTE`, nunca sobrescrito, salvo los casos MERGE/
CLAUDE.md ya existentes y sin cambios). `sync` no introduce ningún mecanismo nuevo de merge de
contenido — un archivo `MERGE`/`CLAUDE.md` que necesite fusionarse en un `sync` sigue el mismo
camino que ya usa una reinstalación normal.

### R13 — Scaffold neutral, sin datos privados
Los 2 documentos nuevos (`production-readiness.md`, `operations.md`) no contienen rutas
absolutas, nombres de organización, datasets propios de este repo, ni ninguna referencia
específica a Harmessi-dev-repo — igual que el resto de la skill instalable. Ningún archivo de
scaffold cuenta como `artifact_evidence` (Change 6) — ninguna operación de este change llama
`mlops_evidence.agregar_evidencia` ni escribe en `openspec/lifecycle/state.json`.

### R14 — Backward compatibility (invariante dura)
`python -m tools.ds_init --destino X --nombre Y [flags existentes]` (sin `sync`, sin `--stage`)
produce EXACTAMENTE el mismo resultado que hoy: instala TODO (comportamiento default es
`--stage experiment`, que en la práctica instala discovery+experiment — es decir, todo MENOS los
2 documentos nuevos de `production_candidate`/`production`, que son contenido 100% nuevo de este
change y por lo tanto no rompen nada preexistente). `harmessi doctor` corrido sobre ESTE repo
(instalación legacy, sin `installation_stage`) produce el mismo output, check por check, que
antes de este change (0 diff, salvo el propio drift esperado de archivos nuevos del manifiesto
de este mismo change, igual que en changes anteriores).

## Criterios de aceptación

**Manifest / bundles:**
- `discovery` (vía `manifest_para_perfil_y_stage(perfil, "discovery")`) contiene únicamente
  entradas `stage_minimo="discovery"` — ningún agente, ningún doc de `experiment`+.
- `experiment` = `discovery` ∪ entradas `stage_minimo="experiment"` (verificado por igualdad de
  conjuntos, no por conteo).
- `production_candidate` = `experiment` ∪ `{production-readiness.md}`.
- `production` = `production_candidate` ∪ `{operations.md}`.
- Los 4 conjuntos son estrictamente monotónicos crecientes (cada uno subconjunto del siguiente).
- Ningún archivo tiene `stage_minimo` ambiguo (cada `destino` aparece una sola vez en `MANIFEST`,
  invariante ya implícito, confirmado que sigue así).
- `manifest_para_perfil("python-jupyter-data")` (sin stage) sigue devolviendo el set COMPLETO,
  igual que antes de este change (comportamiento no roto).

**Instalación nueva (`ds_init`, sin `sync`):**
- Sin `--stage`: instala `experiment` (default).
- `--stage discovery`: instala solo discovery (agentes/decision-ledger.md/production-readiness/
  operations AUSENTES en el destino).
- `--stage production_candidate`/`--stage production` en una instalación NUEVA: rechazado por
  argparse (`choices` no los incluye), exit 2, nada escrito.
- `installation_stage` queda correctamente registrado en `control.json` tras una instalación
  nueva (`"discovery"` o `"experiment"` según lo pedido).

**Sync incremental:**
- `discovery` → `experiment`: agrega los 5 archivos de `experiment` faltantes, no toca nada de
  `discovery` ya instalado (mismos bytes/hash).
- `experiment` → `production_candidate`: agrega `production-readiness.md`.
- `production_candidate` → `production`: agrega `operations.md`.
- `discovery` → `production` directo: agrega TODO el delta acumulado (5 + 1 + 1 archivos) en una
  sola corrida.
- Idempotencia: correr `sync --stage X` dos veces seguidas — la segunda no cambia nada (todo
  colisiona, `ACCION_OMITIR_EXISTENTE`), `control.json` idéntico.
- Target menor al `installation_stage` actual (o igual): no-op explícito, exit 0, `control.json`
  NO se toca (bytes idénticos antes/después).
- `sync` sin `.ds_init/control.json` previo en el destino: error claro, exit distinto de 0, nada
  escrito.
- Un fallo simulado durante la aplicación (p. ej. mock de una excepción) deja el destino intacto
  y `control.json` sin mentir (ni parcialmente actualizado, ni con `installation_stage`
  incorrecto) — reusa el rollback ya probado de `writer.py`.
- `sync --dry-run` (o sin flag de ejecución) no escribe nada, solo informa el plan del delta.

**`project_stage` vs `installation_stage`:**
- Iguales (p. ej. ambos `experiment`) → `HARMESSI-INSTALLATION-STAGE` da `PASS`.
- `project_stage` más avanzado que `installation_stage` → `WARN`, mensaje menciona el comando
  `sync` exacto a correr.
- `installation_stage` más avanzado que `project_stage` (alguien instaló capacidades
  anticipadamente) → `PASS` (nunca `ERROR`, nunca se considera corrupción), y confirmar que esto
  NO promueve `project_stage` ni genera ningún side-effect en `readiness`/`maturity`.
- Ninguna corrida de Doctor muta `.harmessi/project.json` ni `.ds_init/control.json` en ningún
  escenario.

**Legacy / migración:**
- `control.json` sin `installation_stage`, con los 5 archivos `experiment` presentes (como ESTE
  propio repo) → `inferir_installation_stage` devuelve `"production"`.
- `control.json` sin `installation_stage`, sin los archivos `experiment` (agentes ausentes,
  escenario sintético) → devuelve `"discovery"`.
- `sync` sobre un destino legacy (sin `installation_stage`) usa correctamente la inferencia como
  base antes de calcular el delta, y dejar `installation_stage` explícito al terminar.
- Doctor sobre un destino legacy no muta `control.json` con la sola lectura (la inferencia es
  solo para mostrar en `HARMESSI-INSTALLATION-STAGE`, nunca se persiste desde ahí).
- Doctor sobre este propio repositorio (legacy real, sin `installation_stage`) produce
  `HARMESSI-ARCHIVOS-ESPERADOS` EXACTAMENTE igual que antes de este change (mismo conteo, mismo
  criterio completo) — 0 regresión.

**Protección de archivos:**
- `sync` sobre un destino donde un archivo de `experiment` (p. ej. un agente) ya fue editado por
  el usuario → NO se sobrescribe (mismo hash que antes de `sync`, confirmado byte a byte).
- Un archivo `MERGE` (`.claude/settings.json`) durante `sync`: mismo comportamiento de fusión que
  una reinstalación normal, sin duplicar lógica.
- `sync` nunca borra ningún archivo, en ningún escenario (ni siquiera con target menor).

**Doctor — regresión y nuevo comportamiento:**
- Instalación `discovery` real (scratch): `HARMESSI-ARCHIVOS-ESPERADOS` no reclama agentes ni
  `decision-ledger.md`/`production-readiness.md`/`operations.md` como faltantes.
- Instalación `experiment` real: si los agentes existen, `PASS`; si algún archivo de discovery
  falta, se sigue reportando igual que hoy (severidad sin cambios).
- Instalación `production_candidate`/`production` real (vía `sync` en el fixture): Doctor exige
  correctamente el conjunto acumulado completo hasta ese stage.
- Legacy (este repo): sin cambios respecto al Doctor actual (ver arriba).
- `harmessi doctor` corrido sobre este repositorio real, antes/después de este change: mismo
  conteo de `[ERROR]`, sin regresión salvo drift esperado de archivos nuevos del propio change.

**Scratch installs:**
- Scratch `discovery` real vía `ds_init --execute` en un directorio Git temporal.
- Scratch `experiment` real (default).
- Incremental `discovery` → `experiment` real vía `sync --execute` sobre el fixture anterior.
- Incremental `experiment` → `production_candidate` fixtureable sin necesidad de simular
  `promote`/`readiness` real (el sync no depende de `project_stage`/`readiness` para funcionar —
  son ejes independientes, R9).
- Imports desde el destino instalado funcionan (`ds_guard.py`/`harmessi doctor` corridos contra
  el propio destino scratch, sin `ImportError`, para cada stage).

**Manifest / regresión:**
- Test de paridad extendido para `tools/ds_init/legacy.py`.
- Ausencia de duplicados de `destino` en `MANIFEST` (test explícito, ya implícito pero ahora con
  consecuencias reales si se rompe).
- `tools/tests/`, `tools/harmessi/tests/`, `tools/ds_init/tests/` completos sin regresión.
- `harmessi doctor` sobre este repo: 0 `[ERROR]` nuevo.

## Unidad de análisis / grain (condicional — data_understanding, feature_engineering, modeling)
No aplica — cambio de arquitectura/tooling del harness, no de datos de un proyecto DS.

## Cutoff / information boundary (condicional — feature_engineering, data_preparation, modeling)
No aplica.

## Baseline (condicional — modeling)
No aplica.

## Métrica primaria (condicional — modeling, evaluation)
No aplica.

## Métricas secundarias (opcional)
No aplica.

# Propuesta — 20260915-progressive-capability-installation-and-scaffold

## Problema
Hoy `ds_init` instala TODO el stack de Harmessi de una sola vez (`incluye_todo: true`), sin
relación con `project_stage` (Change 3) ni con la matriz de readiness (Change 6). Un proyecto en
`discovery` recibe exactamente el mismo scaffold físico que uno en `production`, lo cual
contradice el principio de progresividad del roadmap v0.3 y obliga a instalar capacidades que
todavía no aplican.

## Objetivo
Hacer que la instalación física de Harmessi sea progresiva por `installation_stage`
(`discovery|experiment|production_candidate|production`), reusando el instalador (`ds_init`)
existente casi sin cambios de mecánica (staging/journal/rollback/omisión de existentes ya
resuelven idempotencia y protección de archivos del usuario), agregando: metadata de
bundle/stage al manifiesto, una operación `sync` incremental, un campo opcional
`installation_stage` en `.ds_init/control.json`, una estrategia de inferencia para instalaciones
legacy, y un ajuste de `harmessi doctor` para que verifique integridad relativa al stage
realmente instalado — sin convertir `installation_stage` en lo mismo que `project_stage`, y sin
que instalar scaffold cuente como evidencia de readiness.

## Evidencia
- **Restricción arquitectónica clave, confirmada por lectura directa**: `tools/ds_guard.py:34-46`
  importa TODOS los módulos de `tools/dsguard/` a nivel de módulo, incondicionalmente (`from
  dsguard import (checks, core, decision, kdd, kdd_compat, lifecycle, maturity, mlops_evidence,
  mlops_foundations, notebooks, readiness, repo, sdd)`). Esto significa que el código Python de
  `tools/dsguard/*.py` NO puede subdividirse por stage sin inventar un mecanismo de import
  perezoso/condicional (explícitamente fuera de alcance, §22 del brief: "no crear... feature
  flags framework"). Por lo tanto los "bundles" de este change son, en la práctica, agentes
  (`.claude/agents/*.md`) + docs de referencia de la skill (`.claude/skills/lead-data-scientist/
  *.md`) + scaffold nuevo — NUNCA el código runtime (`tools/`), que permanece siempre completo.
- **Segunda restricción confirmada**: `.claude/settings.json:5-35` (tratamiento `MERGE`, un único
  archivo) conecta los 3 hooks `PreToolUse` (`tools/nbrunner/hook_launcher.py`,
  `tools/dsguard/hook_launcher_presupuesto.py`, `tools/dsguard/hook_launcher_rutas.py`)
  INCONDICIONALMENTE, sin relación con stage. Por lo tanto `tools/nbrunner/*.py` y
  `tools/launcher_common.py` deben permanecer en `CORE_DISCOVERY` (nunca "experiment"), aunque el
  *agente* `notebook-runner.md` (rol, no infraestructura) sí sea `EXPERIMENT` — distinción
  explícita: agente ≠ infraestructura de hook que lo sostiene.
- `tools/ds_init/planner.py:33-59` (`_accion_para_entrada`) — YA trata cualquier destino
  existente (fuera de `MERGE`/`CLAUDE.md`) como `ACCION_OMITIR_EXISTENTE` (nunca sobrescribe). Esto
  YA da exactamente la protección de archivos del usuario e idempotencia que necesita `sync` — no
  hace falta inventar un mecanismo nuevo de diffing.
- `tools/ds_init/preflight.py:50-99` (`validar_destino`) — YA exige working tree limpio + repo Git
  válido + sin staging huérfano antes de cualquier `--execute`. Reusado sin cambios para `sync`.
- `tools/ds_init/manifest.py:61-89` (`EntradaManifiesto`, `@dataclass(frozen=True)`) — todas las
  entradas actuales de `MANIFEST` se construyen con kwargs; agregar un campo nuevo con default es
  compatible hacia atrás sin romper ningún caller existente.
- `tools/ds_init/control.py:36-158` (`generar_control`/`regenerar_control`) — `generar_control`
  arma `archivos` a partir de `archivos_aplicados` (parámetro explícito, no recalculado); crítico:
  dentro de `writer.instalar`, `archivos_aplicados` hoy es SOLO lo aplicado en la corrida actual
  (`entradas_journal`), nunca el set acumulado completo. Para una instalación fresca esto coincide
  con el set completo (todo se crea en la misma corrida), pero para una reinstalación/`sync`
  parcial (algunas entradas `ACCION_OMITIR_EXISTENTE`) NO coincide — si se usara tal cual para
  `sync`, `control.json` perdería el registro de archivos ya instalados en corridas anteriores.
  Resuelto sin tocar `writer.instalar`: `sync` completa el control.json con una llamada posterior
  a `regenerar_control` (que YA recalcula `archivos` desde el manifiesto vigente, no desde
  `archivos_aplicados` de una corrida puntual) — mecanismo ya existente, extendido con
  `stage`/`installation_stage` opcionales.
- `tools/harmessi/doctor.py:374-415` (`_check_archivos_administrados`) — hoy compara contra
  `manifest_mod.manifest_para_perfil(perfil)` COMPLETO, no contra `control_data["archivos"]`
  (que sí refleja lo realmente aplicado). Confirmado que, sin ajuste, introducir bundles rompería
  Doctor para cualquier instalación parcial (reportaría FAIL/WARN por archivos de stages
  superiores que nunca se instalaron) — exactamente el riesgo que el usuario señaló en §17/§18.
- `tools/harmessi/doctor.py:52-70` (`_RUTAS_CRITICAS`) — incluye los 4 agentes como críticos
  (ausencia = `ERROR`). Confirma que los agentes hoy se tratan como "siempre esperados"; este
  change los mueve a `EXPERIMENT` sin cambiar su severidad DENTRO de ese stage (siguen siendo
  críticos si el stage instalado los incluye, pero dejan de reclamarse en `discovery`).
- `tools/ds_init/version.py`, `tools/ds_init/cli.py:27-107` — CLI plana actual, sin subcomandos,
  sin concepto de stage. `--nombre` es `required=True` hoy; cualquier extensión debe preservar
  `python -m tools.ds_init --destino X --nombre Y ...` funcionando exactamente igual.
- Roadmap v0.3 aprobado (Change 7 de la serie); Changes 3/6 ya cerrados
  (`project_stage`/`readiness`/`mlops evidence`), consumidos sin modificarse.

## Supuestos descartados
No se crea un plugin manager, resolver de dependencias genérico, framework de feature flags,
framework de migración universal, motor de templating nuevo, ni transacciones de filesystem
nuevas — se reusa el staging/journal/rollback ya existente de `writer.py` tal cual. No se
subdivide el código Python de `tools/dsguard/`/`tools/nbrunner/`/`tools/ds_profile/` por stage
(imposible sin romper el import incondicional de `ds_guard.py` y el hook global de
`settings.json` — ver Evidencia). No se crea contenido semántico "de mentira" para packaging/
inference contract/inference tests/trazabilidad fuerte/deployment/CI-CD/monitoring/rollback/
drift/alerts/retraining — el scaffold de `production_candidate`/`production` se limita a DOS
nuevos documentos de referencia de la skill (explican los gates y cómo registrar evidencia real
vía `mlops evidence add`), nunca archivos que puedan confundirse con evidencia real. No se
implementa `harmessi init` público. No se modifica `promote` para instalar nada. No se cambia el
schema de `openspec/lifecycle/state.json`.

## Hipótesis (condicional — solo cambios metodológicos)
No aplica — cambio de arquitectura/tooling del harness.

## Alcance
1. **`tools/ds_init/manifest.py`**: campo nuevo `stage_minimo: str = "discovery"` en
   `EntradaManifiesto` (compatible hacia atrás); `ORDEN_STAGES = ("discovery", "experiment",
   "production_candidate", "production")`; re-etiquetar los 4 agentes + `decision-ledger.md` como
   `stage_minimo="experiment"`; 2 entradas nuevas (`production-readiness.md`,
   `operations.md`, `stage_minimo="production_candidate"`/`"production"` respectivamente, vía
   plantillas `.tmpl` nuevas, mismo patrón que `eda.md`); `manifest_para_perfil_y_stage(perfil,
   stage)` (filtra por `stage_minimo` acumulativo, sin tocar `manifest_para_perfil` existente).
2. **`tools/ds_init/planner.py`/`writer.py`**: `construir_plan(..., stage=None)` — cuando se pasa
   `stage`, usa `manifest_para_perfil_y_stage` en vez de `manifest_para_perfil`; `stage=None`
   preserva el comportamiento actual byte a byte. `writer.instalar` lee `config.get("stage")` con
   el mismo criterio (pasa el manifiesto correcto a `_armar_staging`).
3. **`tools/ds_init/control.py`**: `generar_control`/`regenerar_control` ganan un parámetro
   opcional `installation_stage` (se omite del dict si es `None`, preserva forma legacy) y
   `regenerar_control` gana `stage` opcional (usa `manifest_para_perfil_y_stage` si se pasa).
4. **`tools/ds_init/legacy.py`** (nuevo, pequeño): `inferir_installation_stage(destino, perfil)` —
   `"production"` si los archivos re-etiquetados `experiment` están todos presentes (única señal
   confiable: toda instalación pre-Change-7 instalaba el 100% del manifiesto, no hay forma de
   distinguir experiment/candidate/production entre sí con archivos viejos — se asume el máximo
   compatible, tal como pide el usuario), `"discovery"` en caso contrario. Nunca escribe nada.
5. **`tools/ds_init/cli.py`**: `--stage` nuevo (`choices=["discovery","experiment"]`, default
   `"experiment"`) para instalación nueva — rechaza explícitamente `production_candidate`/
   `production` en un `init` nuevo (evita bypass de madurez). Subcomando `sync` nuevo (positional
   `accion` con default `"install"`, 100% compatible con la invocación plana actual): `python -m
   tools.ds_init sync --destino <path> --stage <cualquiera de los 4> [--dry-run|--execute]` —
   opera sobre un destino YA instalado (`.ds_init/control.json` debe existir), reconstruye
   placeholders desde `control.json["configuracion"]` (no repite `--nombre` etc.), calcula el
   stage base (declarado o inferido), agrega solo lo faltante hasta el stage objetivo, y
   completa `control.json` con `regenerar_control(..., stage=target, installation_stage=target)`
   tras una aplicación exitosa. Target menor al stage actual → no-op explícito, sin escribir nada.
6. **`tools/harmessi/doctor.py`**: `_check_archivos_administrados` usa
   `manifest_para_perfil_y_stage(perfil, installation_stage)` si `control_data` tiene
   `installation_stage`; si no (legacy), preserva el comportamiento actual EXACTO (compat total,
   0 diff para instalaciones legacy incluido este propio repo). Nuevo check
   `HARMESSI-INSTALLATION-STAGE` (solo lectura): compara `project_stage`
   (`.harmessi/project.json`) contra `installation_stage`; `project_stage` más avanzado → `WARN`
   accionable ("correr `ds_init sync --stage X`"); `installation_stage` más avanzado o igual →
   `PASS`; sin datos suficientes → `N/A`. Nunca `ERROR`, nunca muta nada.
7. **Manifest de MANIFEST**: entradas VERBATIM de `tools/ds_init/legacy.py` (nuevo módulo del
   propio instalador, no se instala en destinos — igual que el resto de `tools/ds_init/`, que
   nunca se copia a un proyecto instalado).
8. **Tests**: cobertura completa según lista de la sección 21 del brief del usuario (bundles,
   init nuevo, sync incremental, `project_stage` vs `installation_stage`, legacy/migración,
   protección de archivos, doctor, scratch installs, manifest, regresión completa).

## Fuera de alcance
Unified status completo (Change 8), Lead methodology awareness (Change 9), `harmessi` CLI pública
nueva, auto-sync dentro de `promote`, downgrade/uninstall físico, waivers, instalación específica
por `risk_level`, cutoff/baseline enforceable, reporting, dsimpact, multi-provider, Agent
Efficiency telemetry, deployment/CI-CD/monitoring reales, Kubernetes/Docker obligatorio/GitHub
Actions obligatorio/MLflow/cloud provider/monitoring vendor. Ningún cambio de schema de
`openspec/lifecycle/state.json`. Ninguna generación automática de `artifact_evidence` por
instalar scaffold.

## Holdout policy (condicional — solo cambios "sensible")
No aplica.

## Impacto en production-readiness (opcional)
Indirecto — los 2 nuevos docs de referencia (`production-readiness.md`/`operations.md`) ayudan al
usuario a saber QUÉ evidencia registrar para los gates de Change 6, pero no satisfacen ningún
gate por sí mismos (ninguna instalación de scaffold cuenta como `artifact_evidence`).

## Criterios de aceptación (spec-lite — solo SDD abreviado)
Ver `spec.md`.

## Decisión técnica (design-lite — solo SDD abreviado)
Ver `design.md`.

## Aprobación
- Usuario: Federico Colombo
- Fecha: 2026-09-15
- Alcance aprobado: "progressive-capability-installation-and-scaffold — 4 bundles acumulativos
  (discovery/experiment/production_candidate/production), instalación progresiva vía ds_init
  extendido (--stage, sync), installation_stage en control.json separado de project_stage,
  migración legacy por inferencia explícita, protección de archivos del usuario reusando el
  installer existente, doctor consciente de installation_stage sin convertirse en unified status"
- Versión de artefactos referenciada: hashes a registrar en `control.json` de este change
- Cita o descripción fiel de qué se aprobó: brief íntegro del usuario para Change 7 ("BOUNDED
  AUTONOMY ... Ejecutar de punta a punta ... project_stage → describe madurez alcanzada;
  installation capabilities → describen qué componentes físicos de Harmessi están instalados. NO
  deben convertirse en la misma cosa ni escribirse implícitamente entre sí.").

## Motivo de rechazo
<!-- completar solo si estado: descartada -->

## Desacuerdo registrado
<!-- completar solo si estado: pausada_bloqueada tras 2 rondas de revisión sin acuerdo -->

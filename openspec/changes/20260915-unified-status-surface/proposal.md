# Propuesta — 20260915-unified-status-surface

## Problema
Hoy entender el estado real de un proyecto Harmessi requiere correr por separado `project
status`, `lifecycle` (vía lectura directa de `state.json`, sin CLI dedicada de status), `mlops
status`, `project readiness --target`, y `harmessi doctor` — sin ningún lugar que los consolide.
No existe una vista única, de solo lectura, que muestre madurez/riesgo/lifecycle/MLOps/readiness/
instalación/integridad del harness de un vistazo.

## Objetivo
Agregar `python -m tools.ds_guard status` (sin `--change-id`) como superficie unificada de
solo lectura que consolida las fuentes de verdad YA existentes (`.harmessi/project.json`,
`openspec/lifecycle/state.json`, `.ds_init/control.json`, el motor de checks/readiness/
foundations/evidence de Changes 4-7), sin crear un nuevo estado persistido ni un segundo engine.

## Evidencia
- **Colisión de nombre confirmada**: `ds_guard.py` YA tiene un subcomando `status`
  (`tools/ds_guard.py:1290-1293`, `cmd_status`, `--change-id` `required=True`) para estado de un
  change SDD — usado activamente por el propio flujo SDD de este proyecto (incluida esta misma
  sesión, changes 0-7). El brief pide literalmente `python -m tools.ds_guard status`. Resuelto sin
  romper nada: `--change-id` pasa a opcional; con `--change-id` → comportamiento SDD actual
  EXACTO, sin cambios; sin `--change-id` → nuevo status unificado de proyecto. Invariante dura:
  cualquier invocación existente (`status --change-id X [--json]`) sigue funcionando idéntica.
- **Restricción arquitectónica confirmada por lectura directa**: ni `tools/harmessi/doctor.py` ni
  ningún módulo de `tools/ds_init/` se instalan en un proyecto destino — `doctor.py` "corre desde
  el checkout FUENTE de Harmessi apuntando `--destino` a cualquier repo" (docstring propio,
  confirmado en Change 7); `tools/ds_init/*` nunca aparece en `MANIFEST` (confirmado explícitamente
  en el audit de Change 7 — "tools/ds_init/* en general nunca se instala en destinos"). Esto
  significa que un proyecto YA instalado, corriendo `ds_guard status` con SU PROPIO
  `tools/ds_guard.py`, NO tiene `tools/harmessi/doctor.py` ni `tools/ds_init/legacy.py` en su
  propio árbol — importarlos incondicionalmente rompería `ModuleNotFoundError` en el caso más
  común (exactamente lo que el requisito 24 del brief exige que NO pase: "Status debe funcionar
  desde proyecto instalado, no solo desde repo Harmessi"). Resuelto con imports perezosos
  opcionales (`try/except ImportError`), degradando con gracia (nunca excepción cruda) cuando esas
  piezas no están disponibles — consistente con §13 del brief ("si reutilizar Doctor introduce
  acoplamiento incorrecto: preferir una extracción/reuso mínimo compatible") y con §17
  ("degradar correctamente... fail closed donde corresponde").
- Sin embargo, `installation_stage` en sí (cuando ya está declarado explícitamente en
  `.ds_init/control.json`, el caso normal para cualquier proyecto sincronizado vía Change 7) se
  lee con `json.load()` PLANO, sin depender de `tools.ds_init` en absoluto — solo la INFERENCIA
  legacy (`legacy.inferir_installation_stage`, para `control.json` sin esa clave) necesita el
  import perezoso opcional, ya que requiere el catálogo del manifiesto (que tampoco se instala).
- `tools/dsguard/checks.py` (Change 4), `maturity.py` (Change 3), `lifecycle.py` (Change 1),
  `mlops_foundations.py` (Change 5), `readiness.py`/`mlops_evidence.py` (Change 6) — todos
  reusados TAL CUAL, ninguno modificado. `readiness.evaluar_readiness(repo_root, target)` ya
  produce exactamente los `CheckResult` que la sección "Readiness" necesita, incluido
  `kind=technical_error` cuando corresponde (Change 6, R11).
- `tools/dsguard/lifecycle.py:22-31,72-90` — 8 fases CRISP-DM, 5 pasos KDD canónicos, 3 tiers
  MLOps — catálogo ya definido, reusado sin duplicar.
- Roadmap v0.3 aprobado (Change 8 de la serie); Changes 0-7 cerrados, consumidos sin modificarse
  (salvo la extensión aditiva y backward-compatible de `cmd_status`/`construir_parser` en
  `ds_guard.py`, que no es un módulo de dominio sino el wiring de CLI).

## Supuestos descartados
No se crea un `status.json` persistido, ni un segundo engine de evaluación, ni un health score
numérico (`Health = 83%`, prohibido explícitamente). No se copian las ~1000 líneas de
`doctor.py` — se reusa vía import perezoso opcional cuando está disponible (checkout fuente),
degradando con gracia cuando no (proyecto instalado). No se implementa `harmessi status` público
(CLI pública, queda para una capa posterior). No se permite promover/sincronizar/calibrar/
registrar evidencia desde `status` — es estrictamente de solo lectura. No se reimplementan gates
de readiness ni evaluadores de evidencia — se reusa `readiness.py`/`mlops_evidence.py` tal cual.

## Hipótesis (condicional — solo cambios metodológicos)
No aplica — cambio de arquitectura/tooling del harness.

## Alcance
1. **`tools/dsguard/status.py`** (nuevo): `evaluar_status(repo_root) -> dict` (orquesta todas las
   secciones, solo lectura, nunca lanza excepción no controlada); `formatear_texto(status) ->
   str`; `formatear_json(status) -> str` (o dict serializable). Secciones: `project`,
   `installation`, `alignment`, `lifecycle`, `mlops` (`foundations`/`production_readiness`/
   `operations`), `readiness` (próximo target), `harness` (integridad, degradable).
2. **`ds_guard.py`**: `cmd_status` extendido (`--change-id` ahora opcional; rama nueva sin
   `--change-id` → `status.evaluar_status` + `formatear_texto`/`formatear_json`); `--verbose`
   nuevo, opcional, solo aplica a la rama sin `--change-id` (muestra detalle completo de checks en
   vez del resumen compacto).
3. **Manifest**: entrada VERBATIM de `status.py`; test de paridad extendido; `archivos_clave` de
   scratch install.
4. **Tests**: cobertura completa según §25 del brief — stages, alignment, risk, lifecycle,
   foundations, readiness, evidence, harness, read-only, JSON, output humano, regresión.

## Fuera de alcance
Lead methodology awareness (Change 9), cutoff/baseline checks, reporting, dsimpact, Portable
Core, multi-provider, evals/harmessi-bench, Agent Efficiency telemetry, Responsible AI,
gobernanza específica por riesgo, `harmessi` CLI pública, auto-sync/auto-promote desde `status`.
Ningún cambio de schema en `lifecycle.py`/`maturity.py`/`checks.py`/`readiness.py`/
`mlops_evidence.py`/`mlops_foundations.py`. Ningún `status.json`/health score/dashboard/TUI/cache
persistente/telemetry.

## Holdout policy (condicional — solo cambios "sensible")
No aplica.

## Impacto en production-readiness (opcional)
Ninguno directo — `status` observa readiness, no la modifica.

## Criterios de aceptación (spec-lite — solo SDD abreviado)
Ver `spec.md`.

## Decisión técnica (design-lite — solo SDD abreviado)
Ver `design.md`.

## Aprobación
- Usuario: Federico Colombo
- Fecha: 2026-09-15
- Alcance aprobado: "unified-status-surface — `ds_guard status` (sin --change-id) como vista
  unificada de solo lectura, consolidando project/installation/lifecycle/mlops/readiness/harness
  sin crear nuevas fuentes de verdad ni duplicar lógica, con degradación con gracia para proyecto
  instalado sin doctor.py/ds_init"
- Versión de artefactos referenciada: hashes a registrar en `control.json` de este change
- Cita o descripción fiel de qué se aprobó: brief íntegro del usuario para Change 8 ("BOUNDED
  AUTONOMY ... Unified status: NO decide, NO promueve, NO instala, NO calibra, NO registra
  evidencia, NO modifica lifecycle. Solo observa y explica el estado que ya existe.").

## Motivo de rechazo
<!-- completar solo si estado: descartada -->

## Desacuerdo registrado
<!-- completar solo si estado: pausada_bloqueada tras 2 rondas de revisión sin acuerdo -->

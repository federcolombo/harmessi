# Propuesta — 20260915-project-maturity-state-and-calibration

## Problema
Harmessi v0.3 (Changes 1-2, cerrados) ya tiene `openspec/lifecycle/state.json` como fuente de verdad metodológica (CRISP-DM/KDD/MLOps). Pero no existe ningún estado de MADUREZ/gobernanza del proyecto (`project_stage`, `risk_level`) — un eje ortogonal al lifecycle, ya diseñado conceptualmente en el roadmap v0.3 aprobado pero nunca implementado.

## Objetivo
Crear `.harmessi/project.json` (estado persistente de madurez), los comandos `ds_guard project init/calibrate/set-risk/status`, y la lógica en `tools/dsguard/maturity.py` — sin readiness, sin promotion, sin checks engine, sin scaffold progresivo, sin `harmessi project` público todavía.

## Evidencia
- `tools/dsguard/lifecycle.py` (Change 1) y `tools/dsguard/kdd_compat.py` (Change 2) — precedente directo de patrón: catálogo + excepción `<Modulo>EstadoError`/`<Modulo>Error` + `state_path`/`leer_estado`/`validar_estructura`/`escribir_estado`/`<modulo>_init` idempotente, escritura atómica vía `core.escribir_texto_atomico`.
- `openspec/changes/20260914-lifecycle-core-schema/design.md` punto 5 (ajuste del usuario, K2 de esa ronda): decisión de NO persistir `fase_actual`/`paso_actual` en `lifecycle.py` porque son derivables y persistirlos arriesga divergencia entre dos fuentes dentro del mismo archivo — precedente directo aplicado en este change a la pregunta `risk_status` vs `risk_level is null` (ver `design.md` de este change).
- `tools/harmessi/cli.py` — ya existe como wrapper delgado (`argparse` → llama funciones de `doctor.py`, no reimplementa lógica) — precedente exacto de la arquitectura CLI que este change debe dejar preparada para `harmessi project ...` sin implementarla todavía.
- `tools/ds_init/manifest.py` — sin ninguna entrada `.harmessi/` hoy (confirmado por grep); `.harmessi/profiles/` (ds_profile, v0.2) ya es precedente de "`.harmessi/` es estado generado, no instalado por ds_init".
- Roadmap v0.3 aprobado por el usuario (Change 3 de la serie: `project-maturity-state-and-calibration`).

## Supuestos descartados
No se implementa `project promote`, readiness, checks engine, PASS/WARN/FAIL/N/A, MLOps checks, scaffold progresivo, `harmessi init` unificado, Lead methodology awareness, lifecycle unified status, cutoff/baseline enforceable, reporting, multi-provider, dsimpact — todos changes posteriores del roadmap. No se agrega `set-stage` genérico ni downgrade normal. No se toca `lifecycle.py`/`kdd.py`/`kdd_compat.py`/`ds_init/control.py` con lógica de `project_stage` (separación de responsabilidades explícita).

## Hipótesis (condicional — solo cambios metodológicos)
No aplica.

## Alcance
1. **`tools/dsguard/maturity.py`** (nuevo): catálogos (`PROJECT_STAGES` — tupla ordenada de 4 valores, `RISK_LEVELS`, `STAGES_INIT_PERMITIDOS` — ver design.md para la restricción), excepción `MaturityEstadoError`, `state_path`, `estado_inicial`, `inferir_stage` (lee SOLO existencia de `openspec/lifecycle/state.json`/`openspec/kdd/state.json`, nunca su contenido — importa `lifecycle.state_path`/`kdd_compat.state_path_legacy` únicamente para construir las rutas, sin acoplar lógica), `validar_estructura`, `leer_estado`, `escribir_estado`, `project_init`, `calibrar`, `set_risk`, `project_status`, `estado_riesgo` (helper puro que deriva "unclassified"/"classified" de `risk_level is None` — ver `design.md` para por qué NO se persiste como campo separado). `project_init` acepta `stage` (proyecto nuevo, default `"experiment"`) y `adopt` (booleano, dispara inferencia) como parámetros mutuamente excluyentes — ver `design.md` punto 3.
2. **`ds_guard.py`**: nuevo grupo `project` con subcomandos `init`, `calibrate`, `set-risk`, `status` — mismo patrón que los grupos `kdd`/`lifecycle` ya existentes (wrappers delgados, `--json` opcional).
3. **Manifest**: entrada VERBATIM de `tools/dsguard/maturity.py`; `.harmessi/` agregado a `EXCLUSIONES_PERMANENTES` (estado generado por proyecto, no instalado — mismo criterio que `openspec/lifecycle/` en Change 2).
4. **Tests**: ver `tasks.md` — cobertura de creación/idempotencia/validación/inferencia/calibrate/set-risk/separación de responsabilidades/manifest/instalación scratch.

## Fuera de alcance
`project promote`, readiness, checks engine, PASS/WARN/FAIL/N/A, MLOps checks, progressive capability bundles, scaffold data/src/notebooks, `harmessi init` unificado, Lead methodology awareness, lifecycle unified status (Change 8), cutoff/baseline enforceable, reporting, multi-provider, dsimpact. `set-stage` genérico / downgrade normal (ver `design.md` § Downgrade). Wiring de `harmessi project ...` en `tools/harmessi/cli.py` (queda preparado pero no implementado — ver `design.md`).

## Holdout policy (condicional — solo cambios "sensible")
No aplica.

## Impacto en production-readiness (opcional)
Ninguno directo — `project_stage`/`risk_level` son metadata declarativa en este change, sin ningún gate ni check todavía; sienta la base de datos que Changes futuros (readiness/promotion) van a leer.

## Criterios de aceptación (spec-lite — solo SDD abreviado)
Ver `spec.md`.

## Decisión técnica (design-lite — solo SDD abreviado)
Ver `design.md`.

## Aprobación
- Usuario: pendiente
- Fecha: pendiente
- Alcance aprobado: pendiente
- Versión de artefactos referenciada: pendiente
- Cita o descripción fiel de qué se aprobó: pendiente

## Motivo de rechazo
<!-- completar solo si estado: descartada -->

## Desacuerdo registrado
<!-- completar solo si estado: pausada_bloqueada tras 2 rondas de revisión sin acuerdo -->

# Proposal — 20260916-kdd-enforceable-checks

## Contexto

v0.3 dejó gobernanza metodológica (lifecycle CRISP-DM/KDD/MLOps, checks engine PASS/WARN/FAIL/N-A,
maturity/readiness/promotion, status unificado, Lead methodology-aware). v0.4 pasa de "metodología
gobernada" a "calidad científica y cambio controlado de forma determinista". Este Change 0 convierte
reglas científicas clave en checks enforceables: cutoff temporal, holdout, leakage básico, baseline.

Principio permanente: el LLM decide lo semántico, el binario calcula y hace cumplir lo determinista.

## Qué se construye

1. **Modelo de scientific checks** (`tools/dsguard/scientific_validity.py`): capa neutral que reusa
   `checks.CheckResult`/`STATUS_*`/`KIND_*` — no es un segundo checks engine.
2. **Política científica declarativa** (`.harmessi/scientific-policy.json`, opcional, schema_version=1):
   único archivo nuevo. No reemplaza `project.json` ni `lifecycle/state.json`. No contiene resultados
   derivados. Ausencia de una sección aplicable → N/A, nunca FAIL.
3. **Cutoff temporal**: verifica `max(fecha de una columna declarada) <= cutoff declarado`, leyendo
   `profile.json` de `ds_profile` (nunca el dataset completo, nunca pandas obligatorio).
4. **Holdout**: verifica identificación/protección estructural (reusa `pathguard`) y uso declarado
   (operaciones prohibidas: training/feature_engineering_fit/model_selection/hyperparameter_tuning/
   baseline_fitting vs. evaluación final autorizada).
5. **Leakage determinista básico**: target-en-features, forbidden-features explícitas, split temporal
   inválido. Leakage temporal reusa el check de cutoff (no se duplica).
6. **Baseline**: existencia/integridad de evidencia (archivo no vacío, hash opcional contra staleness)
   cuando `baseline.required = true`. Nunca exige un algoritmo concreto.
7. **CLI**: `python -m tools.ds_guard science status [--json]`, estrictamente read-only.
8. **Status unificado**: nueva sección `"science"` en `ds_guard status` (sin `--change-id`).
9. **Lead**: actualización mínima de `methodology.md` (vivo + `.tmpl` de instalación).
10. **Manifest**: entrada VERBATIM para `scientific_validity.py`. Sin template de policy (mismo
    criterio que `.harmessi/project.json`: `.harmessi/` ya está en `EXCLUSIONES_PERMANENTES`, se crea
    manualmente cuando aplica, nunca generado con reglas falsas).

## Qué NO se construye (fuera de alcance explícito)

Impact Preflight, Scope & Change Isolation, Portable Core, Agent Efficiency telemetry, Reporting,
harmessi-bench, Data Contracts avanzados, multi-provider, Responsible AI, nuevos readiness gates,
deployment/monitoring, inferencia semántica de leakage vía LLM, auto feature selection, auto baseline
selection. No se modifica `readiness.py`/la matriz de promotion de v0.3. No se cambia el schema de
`openspec/lifecycle/state.json`. No se agregan fases CRISP-DM nuevas.

## Decisión/deuda registrada (para v0.4 futuro, no este Change)

Si algún scientific check (p. ej. `SCI-CUTOFF`, `SCI-BASELINE`) debe incorporarse como gate de
`readiness`/`promote`, eso se decide y ejecuta en un change posterior — no automáticamente acá.

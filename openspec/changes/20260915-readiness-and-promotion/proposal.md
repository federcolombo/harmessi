# Propuesta — 20260915-readiness-and-promotion

## Problema
`project_stage` (Change 3) hoy solo se mueve vía `calibrate` (adopción/corrección puntual, sin
gates) o `project init`. No existe ningún mecanismo que verifique que un proyecto realmente
cumple los requisitos de madurez antes de avanzar de etapa, ni una promoción real y secuencial
gateada por evidencia. `project_stage=production_candidate`/`production` deben representar
madurez ALCANZADA, no solo declarada.

## Objetivo
Implementar `project readiness --target <stage>` (solo lectura, matriz completa de gates vía
`checks.py`) y `project promote <stage> --reason "..."` (promoción estrictamente secuencial,
gateada por la readiness del target, atómica), más un mecanismo genérico de evidencia de artifact
(`mlops evidence add --tier --capability --artifact --reason`) para los tiers
`production_readiness`/`operations`, reusando el motor neutral de checks y sin inventar ni
relajar ningún gate de la matriz aprobada por el usuario.

## Evidencia
- `tools/dsguard/maturity.py:168-192` — `calibrar()` ya bloquea si existe un `stage_history` con
  `via=="promote"` (`if any(e.get("via") == "promote" for e in estado.get("stage_history", []))`)
  — mecanismo de lock ya construido en Change 3, este change lo activa por primera vez al ser
  quien puede escribir `via="promote"`.
- `tools/dsguard/maturity.py:18-19` — `PROJECT_STAGES = ("discovery", "experiment",
  "production_candidate", "production")`, `STAGES_INIT_PERMITIDOS = ("discovery", "experiment")`.
  Sin mecanismo de downgrade en ningún lugar del código — se mantiene así.
- `tools/dsguard/checks.py` (Change 4) — `CheckResult(status,code,message,detail,subject,kind)`,
  `ejecutar_checks(registros)` (cada función debe devolver `list[CheckResult]`, no un
  `CheckResult` suelto — error real cometido y corregido en Change 5, a evitar de nuevo),
  `hay_bloqueo`/`exit_code` (bloquean solo por `FAIL`, `kind` no cambia esa semántica).
- `tools/dsguard/lifecycle.py:22-31,72-90` — 8 fases CRISP-DM, `MLOPS_CAPACIDADES =
  {"foundations": (...4), "production_readiness": ("packaging", "environment_reproducible",
  "inference_contract", "inference_tests", "trazabilidad_fuerte"), "operations": ("deployment",
  "cicd", "monitoring", "rollback", "drift", "alerts", "retraining")}` — catálogo ya definido en
  Change 1, sin capacidades evaluadas todavía.
- `tools/dsguard/lifecycle.py:143-186` (`validar_estructura`) — confirmado por lectura directa:
  solo valida que `evidencia` sea una `list`, nunca inspecciona las claves internas de cada
  entrada. Ya conviven en esa lista `{change_id, artefacto}` (Change 2) y `{tipo:"check_snapshot",
  status, kind, message, utc}` (Change 5) sin bump de `schema_version`. Confirma que la nueva
  forma `{tipo:"artifact_evidence", path, sha256, reason, utc}` de este change NO requiere romper
  el schema — no aplica el trigger de STOP del §6 del brief del usuario.
- `tools/dsguard/mlops_foundations.py` (Change 5) — `evaluar_foundations(repo_root) ->
  list[CheckResult]` ya mide `reproducibilidad`/`versionado`/`lineage`/`artifacts`; `lineage`
  nunca da `PASS` (siempre `WARN` o `N/A`), confirmado leyendo el código fuente
  (`check_lineage:170-203`). Este change reinterpreta esos resultados con severidad de contexto
  (WARN/FAIL/N-A → FAIL para `production_candidate`, excepto `lineage`) sin tocar
  `mlops_foundations.py`.
- `tools/dsguard/pathguard.py` — `cargar_config`, `resolver_ruta_relativa`,
  `SECRETOS_HARDCODEADOS`, holdouts/excepciones de lectura — mecanismo existente de protección de
  rutas, reusado (no duplicado) para validar `--artifact` en `mlops evidence add`.
- `tools/ds_profile/fingerprint.py` — `calcular_fingerprint` (sha256 binario) es local a
  `ds_profile` a propósito ("no se agrega a dsguard/core.py... sin necesidad real hoy", docstring
  propio). Decisión de este change: duplicar localmente las ~10 líneas de hash binario en
  `dsguard/mlops_evidence.py` en vez de crear una dependencia inversa `dsguard → ds_profile` (la
  única dependencia cruzada existente hoy es `ds_profile → dsguard`, ver
  `ds_profile/holdout_guard.py`). No es una decisión de schema/contrato — no dispara ningún
  trigger de STOP.
- Mensaje íntegro del usuario (brief de Change 6): matriz de readiness completa por transición
  (discovery→experiment, experiment→production_candidate, production_candidate→production),
  mecanismo de evidencia, reglas de N/A/technical_error, atomicidad/read-only — "decisión de
  producto ya aprobada... Claude NO debe inventar gates nuevos ni relajar gates definidos acá."

## Supuestos descartados
No se toca `checks.py`/`lifecycle.py`/`maturity.py`/`mlops_foundations.py` (solo se consumen). No
se implementa `harmessi project ...` (superficie pública unificada, change futuro). No se
implementa scaffold progresivo, waivers/exemptions, severidad por `risk_level`, ni se integra
ninguna herramienta externa real (CI/CD, monitoring, cloud, MLflow, Docker/Kubernetes). No se
registra la promoción en el decision ledger (`stage_history` ya es el audit trail de madurez) —
si apareciera una razón fuerte para además duplicarlo en el ledger, es un trigger de STOP
explícito del usuario, no una decisión de este change.

## Hipótesis (condicional — solo cambios metodológicos)
No aplica — cambio de arquitectura/tooling del harness, no de datos de un proyecto DS concreto.

## Alcance
1. **`tools/dsguard/mlops_evidence.py`** (nuevo): mecanismo genérico de evidencia de artifact para
   los tiers `production_readiness`/`operations` — `agregar_evidencia(repo_root, tier, capability,
   artifact_rel_path, reason) -> dict` (valida tier/capability/existencia/tipo-archivo/dentro del
   repo/protecciones de pathguard/`reason` no vacío; calcula sha256 binario; dedup determinista
   por `{capability, path, hash}`; escritura atómica vía `lifecycle.escribir_estado`) y
   `evidencia_valida(repo_root, tier, capability) -> (bool, detalle)` (PASS solo si existe al
   menos una entrada `artifact_evidence` cuyo archivo sigue existiendo, dentro del repo, y cuyo
   sha256 actual coincide con el registrado — nunca trata evidencia obsoleta como válida).
2. **`tools/dsguard/readiness.py`** (nuevo): `evaluar_readiness(repo_root, target) ->
   list[CheckResult]` (matriz completa por target, sin short-circuit, reusando
   `mlops_foundations.evaluar_foundations`/`mlops_evidence.evidencia_valida`/`lifecycle.leer_estado`
   /`maturity.leer_estado`) y `promote(repo_root, target, reason) -> dict` (solo próximo stage
   secuencial permitido; re-evalúa readiness antes de escribir; si hay `FAIL` no muta nada; si
   pasa, muta únicamente `project.json` vía `maturity.escribir_estado`, agregando una entrada
   `stage_history` con `via="promote"`).
3. **`ds_guard.py`**: `project readiness --target <stage> [--json]`, `project promote <stage>
   --reason "..." [--json]`, `mlops evidence add --tier --capability --artifact --reason
   [--json]` (subgrupo nuevo `evidence` bajo `mlops`).
4. **Manifest**: entradas VERBATIM de `mlops_evidence.py`/`readiness.py`; test de paridad
   extendido; `archivos_clave` de scratch install.
5. **Tests**: cobertura completa de la matriz de readiness por transición, evidencia (válida,
   fuera de repo, inexistente, hash stale, dedup, protecciones pathguard), promoción (secuencial,
   downgrade, salteo, reason obligatorio, atomicidad, idempotencia, lock de calibrate),
   technical_error, read-only estricto, regresión completa.

## Fuera de alcance
`harmessi project ...` (superficie pública unificada), progressive capability
installation/scaffold por stage (Change 7), unified status surface (Change 8), Lead methodology
awareness (Change 9), cutoff/baseline enforceable, waivers/exemptions, severidad de gates por
`risk_level`, Responsible AI/governance completo, deployment/CI/CD/monitoring/cloud/MLflow/Docker
reales, reporting, dsimpact, multi-provider, Agent Efficiency telemetry. Ningún cambio de schema
en `lifecycle.py`/`maturity.py`/`checks.py`. Ningún registro automático en el decision ledger.

## Holdout policy (condicional — solo cambios "sensible")
No aplica — este change no accede a datos de proyecto ni holdouts; `mlops evidence add` reusa
(nunca duplica) la protección de holdouts/secretos ya existente en `pathguard.py` para el
`--artifact` que el usuario declare, con el mismo criterio fail-closed que el resto del harness.

## Impacto en production-readiness (opcional)
Directo — este change ES el mecanismo real de production-readiness gating del harness (gates
`production_readiness`/`operations` de `MLOPS_CAPACIDADES`, hasta ahora solo catalogados sin
evaluar).

## Criterios de aceptación (spec-lite — solo SDD abreviado)
Ver `spec.md`.

## Decisión técnica (design-lite — solo SDD abreviado)
Ver `design.md`.

## Aprobación
- Usuario: Federico Colombo
- Fecha: 2026-09-15
- Alcance aprobado: "readiness-and-promotion — `project readiness --target`, `project promote
  --reason`, mecanismo genérico de evidencia `mlops evidence add`, matriz de gates completa según
  el brief dado (discovery→experiment, experiment→production_candidate,
  production_candidate→production), sin inventar ni relajar gates"
- Versión de artefactos referenciada: hashes a registrar en `control.json` de este change
- Cita o descripción fiel de qué se aprobó: brief íntegro del usuario para Change 6 ("BOUNDED
  AUTONOMY ... Ejecutar de punta a punta: audit → SDD → implementación → tests → reviewer → fixes
  → re-tests → verification → cierre. Sin check-ins intermedios ... La matriz de readiness de
  este prompt es una decisión de producto ya aprobada. Claude NO debe inventar gates nuevos ni
  relajar gates definidos acá.").

## Motivo de rechazo
<!-- completar solo si estado: descartada -->

## Desacuerdo registrado
<!-- completar solo si estado: pausada_bloqueada tras 2 rondas de revisión sin acuerdo -->

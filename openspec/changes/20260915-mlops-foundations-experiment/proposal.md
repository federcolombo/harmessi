# Propuesta — 20260915-mlops-foundations-experiment

## Problema
El roadmap v0.3 requiere que MLOps no empiece recién en producción: desde
`project_stage=experiment` debe existir una base mínima para responder "¿qué código/datos/config
produjo este resultado?, ¿hay artifacts persistidos?". Hoy `openspec/lifecycle/state.json`
(Change 1) ya tiene el bloque `mlops.foundations` con las 4 capacidades (`reproducibilidad`,
`versionado`, `lineage`, `artifacts`) pero sin ningún mecanismo que las evalúe. Change 4 ya dio el
motor neutral de checks (`PASS/WARN/FAIL/N-A` + `kind`).

## Objetivo
Implementar checks reales para las 4 foundations MLOps usando `tools/dsguard/checks.py`,
exponerlos vía `ds_guard mlops status` (solo lectura) y `ds_guard mlops record` (persistencia
explícita de evidencia, nunca implícita), sin convertirlos todavía en gates de promoción ni
acoplar `checks.py` a `project_stage`.

## Evidencia
- `tools/dsguard/lifecycle.py` — `MLOPS_CAPACIDADES["foundations"] = ("reproducibilidad",
  "versionado", "lineage", "artifacts")` (Change 1), cada entrada con forma
  `{estado, changes, evidencia, actualizado_utc}`, `ESTADOS_VALIDOS = {no_iniciada, en_progreso,
  cerrada}` — sin relación con el vocabulario PASS/WARN/FAIL/N-A del engine (son dos vocabularios
  distintos, ver `design.md`).
- `tools/dsguard/checks.py` (Change 4) — `CheckResult(status, code, message, detail, subject,
  kind)`, `ejecutar_checks`, `resultado_de_excepcion` (excepción → `FAIL`/`technical_error`).
- `tools/dsguard/maturity.py` (Change 3) — `state_path`, `leer_estado`,
  `project_stage ∈ {discovery, experiment, production_candidate, production}`,
  `MaturityEstadoError`.
- `tools/dsguard/repo.py:46-91` — `get_head(repo_root)` (commit, rama),
  `list_dirty_files(repo_root)` (working tree sucio).
- `tools/ds_profile/fingerprint.py` — `calcular_fingerprint(ruta)` (`sha256/bin/v1`), usado por
  `ds_profile` para generar `.harmessi/profiles/<id>/profile.json` — única fuente real de
  "dataset fingerprint" hoy.
- Confirmado por auditoría directa: no existe `requirements.txt`/`requirements-lock.txt`/lockfile
  en este propio repo ni convención de `models/`/`reports/` scaffoldeada (Change 7, progressive
  scaffold, sigue sin implementar) — los checks de este change deben ser honestos sobre esa
  ausencia, nunca asumir que existen.
- `tools/harmessi/doctor.py` (`_ejecutar_check_con_dato`, Change 4) — precedente del patrón
  "resolver un dato compartido (ej. `control_data`) antes de correr checks que lo usan, con
  manejo de excepción propio" — reusado acá para resolver `project_stage` antes de correr las 4
  checks de capability.
- Roadmap v0.3 aprobado (Change 5 de la serie).

## Supuestos descartados
No se implementa readiness real ni gates hacia `production_candidate`/`production` (Change 6). No
se acopla `checks.py` a `project_stage` — la lógica de gating por stage vive en
`mlops_foundations.py`, no en el engine. No se construye un motor de lineage real (grafo
datos→features→modelo) — el check de `lineage` en este change WARN siempre que esté activo,
nunca PASS (ver `design.md`, justificación explícita). No se infiere `PASS` de "el repo usa Git"
solamente — reproducibilidad exige evidencia adicional (working tree limpio, fingerprint si hay
datos, lockfile de entorno). No se cambia severidad por `risk_level` (ortogonal, sin tocar en
este change). No se crea infraestructura de lineage/registry/experiment-tracker nueva.

## Hipótesis (condicional — solo cambios metodológicos)
No aplica — cambio de arquitectura/tooling del harness que define checks genéricos, no una
hipótesis sobre un dataset concreto.

## Alcance
1. **`tools/dsguard/mlops_foundations.py`** (nuevo): 4 funciones de check
   (`check_reproducibilidad`, `check_versionado`, `check_lineage`, `check_artifacts`), cada una
   `(repo_root, project_stage) -> checks.CheckResult`; `evaluar_foundations(repo_root) ->
   list[checks.CheckResult]` (read-only, resuelve `project_stage` primero con manejo de
   excepción propio, corre las 4 vía `checks.ejecutar_checks`); `registrar_evidencia(repo_root,
   resultados) -> dict` (operación EXPLÍCITA y separada, nunca llamada por `evaluar_foundations`,
   agrega un snapshot `{tipo: "check_snapshot", status, kind, message, utc}` a
   `mlops.foundations.<capability>.evidencia`, nunca toca `estado`, escritura atómica vía
   `lifecycle.escribir_estado`, requiere que `lifecycle/state.json` ya exista).
2. **`ds_guard.py`**: nuevo grupo `mlops` con `status` (solo lectura) y `record` (evaluar +
   persistir), mismo patrón que `kdd`/`lifecycle`/`project`.
3. **Manifest**: entrada VERBATIM de `mlops_foundations.py`; test de paridad extendido.
4. **Tests**: ver `tasks.md` — cobertura completa de los 4 checks, resolución de `project_stage`
   (incluidos los 3 casos: discovery, sin `project.json`, corrupto), `registrar_evidencia`,
   separación read-only/mutación, manifest/scratch install.

## Fuera de alcance
`project promote`, readiness de `production_candidate`/`production`, inference contract/tests,
packaging, deployment, CI/CD real, monitoring, rollback, drift, alerts, retraining, MLflow,
Docker, cloud, cutoff/baseline enforceable, scaffold progresivo (`models/`/`reports/` no se
crean, solo se consultan si ya existen), unified status (Change 8), Lead awareness, reporting,
dsimpact, multi-provider, Agent Efficiency telemetry. Ningún cambio a
`checks.py`/`lifecycle.py`/`maturity.py` (solo se consumen). Ninguna severidad distinta por
`risk_level`.

## Holdout policy (condicional — solo cambios "sensible")
No aplica.

## Impacto en production-readiness (opcional)
Ninguno directo — mide/reporta fundamentos desde `experiment`, sin gatear nada; sienta la base de
evidencia que Change 6 (readiness) va a reutilizar con severidad más fuerte.

## Criterios de aceptación (spec-lite — solo SDD abreviado)
Ver `spec.md`.

## Decisión técnica (design-lite — solo SDD abreviado)
Ver `design.md`.

## Aprobación
- Usuario: Federico Colombo
- Fecha: 2026-09-15
- Alcance aprobado: "Fundamentos MLOps (reproducibilidad/versionado/lineage/artifacts) vía
  checks.py, CLI `ds_guard mlops status/record`, persistencia explícita separada de la medición
  read-only"
- Versión de artefactos referenciada: hashes a registrar en `control.json` de este change
- Cita o descripción fiel de qué se aprobó: "BOUNDED AUTONOMY ... Ejecutar el change completo sin
  pausas intermedias: audit → proposal/spec/design/tasks → aprobación SDD correspondiente →
  implementación → tests → reviewer → correcciones → re-tests → verification → cierre." (mensaje
  del usuario autorizando Change 5 completo en autonomía acotada).

## Motivo de rechazo
<!-- completar solo si estado: descartada -->

## Desacuerdo registrado
<!-- completar solo si estado: pausada_bloqueada tras 2 rondas de revisión sin acuerdo -->

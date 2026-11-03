# Spec — 20260915-project-maturity-state-and-calibration

## Requisitos
Ver `proposal.md § Alcance` y `design.md`. Schema completo de `.harmessi/project.json`:

```json
{
  "schema_version": 1,
  "creado_utc": "...",
  "project_stage": "experiment",
  "risk_level": null,
  "stage_history": [
    {"from": null, "to": "experiment", "via": "migration_inference", "reason": "...", "utc": "..."}
  ],
  "risk_history": []
}
```

`project_stage ∈ {"discovery", "experiment", "production_candidate", "production"}`. `risk_level ∈ {null, "low", "medium", "high"}`. `stage_history`/`risk_history`: listas append-only de `{from, to, via, reason, utc}` — `via ∈ {"explicit_init", "migration_inference", "calibrate", "promote"}` para `stage_history` (`"promote"` reservado, no se genera en este change); `via ∈ {"explicit"}` para `risk_history` en este change (vocabulario abierto a extensión futura, no cerrado por schema).

**NO hay campo `risk_status` persistido** — se deriva puro de `risk_level is None` vía `maturity.estado_riesgo()` (ver `design.md` para la justificación completa, con precedente directo de Change 1).

## Criterios de aceptación
- `project_init(repo_root)` (sin flags) → `project_stage: "experiment"`, `via: "explicit_init"`.
- `project_init(repo_root, stage="discovery")` → `project_stage: "discovery"`, `via: "explicit_init"`.
- `project_init(repo_root, stage="experiment")` → `project_stage: "experiment"`, `via: "explicit_init"`.
- `project_init(repo_root, stage="production_candidate")` o `"production"` → **rechazado** (`MaturityEstadoError` o similar, mensaje claro apuntando a `project calibrate`) — `project init` solo acepta `discovery`/`experiment` explícitos, sea vía `--stage` o vía default (ver `design.md` para la justificación de esta restricción).
- `project_init(repo_root, adopt=True)` sin `openspec/lifecycle/state.json` ni `openspec/kdd/state.json` → `project_stage: "discovery"`, `via: "migration_inference"`, `reason` explica la ausencia de evidencia.
- `project_init(repo_root, adopt=True)` con `openspec/lifecycle/state.json` (o legacy `kdd/state.json`) existente → `project_stage: "experiment"`, `via: "migration_inference"`, `reason` menciona qué se detectó.
- `project_init(repo_root, stage="discovery", adopt=True)` (ambos a la vez) → rechazado con mensaje claro (mutuamente excluyentes).
- `.harmessi/project.json` ya existe y es válido → `project_init` es no-op idempotente (no reescribe, mismos bytes), sin importar el `--stage` pasado.
- `.harmessi/project.json` existe pero corrupto → `MaturityEstadoError`, no se sobreescribe.
- `schema_version` desconocida → `MaturityEstadoError` con mensaje explícito.
- Lectura (`leer_estado`) nunca escribe nada, ni siquiera con dos lecturas consecutivas (bytes idénticos antes/después).
- Escritura (`escribir_estado`) es atómica (mismo patrón que `core.escribir_texto_atomico`, sin `open(..., "w")` directo que la esquive).
- Round-trip: escribir → leer da estructura idéntica.
- `calibrar(repo_root, stage, reason)` sobre un proyecto SIN `.harmessi/project.json` todavía → error claro pidiendo correr `project init` primero (no bootstrapea implícitamente).
- `calibrar(...)` sin `reason` (vacío o `None`) → rechazado, `reason` es obligatorio siempre (no solo para stages de producción).
- `calibrar(repo_root, "production", "adoptamos este proyecto que ya está en prod")` sobre un proyecto con `project.json` existente → `project_stage` pasa a `"production"`, nueva entrada en `stage_history` con `via: "calibrate"`, `reason` preservado literal, `from` = el stage anterior.
- `calibrar(...)` puede usarse más de una vez mientras NO haya ninguna entrada `via: "promote"` en `stage_history` (incluye poder recalibrar hacia un stage MÁS BAJO que el actual, sin restricción especial mientras no haya promote).
- `calibrar(...)` sobre un `stage_history` que YA contiene una entrada `via: "promote"` → rechazado explícitamente, mensaje claro indicando que el proyecto ya tiene una promoción registrada y debe usarse `project promote` (change futuro) en su lugar. Verificable inyectando a mano una entrada `via: "promote"` en el fixture de test (ya que `promote` no existe todavía para generarla de forma real).
- `set_risk(repo_root, "medium", "primera clasificación")` sobre `risk_level: null` → `risk_level` pasa a `"medium"`, `risk_history` gana una entrada `via: "explicit"`, `from: null`.
- `set_risk(repo_root, "high", "reclasificación tras hallazgo de PII")` sobre un `risk_level` ya clasificado → cambia el valor, preserva el anterior como `from` en la nueva entrada, NO borra ni modifica entradas previas de `risk_history`.
- `set_risk(...)` sin `reason` → rechazado (reason siempre obligatorio, ver `design.md`).
- `set_risk(repo_root, "extreme", ...)` (valor inválido) → rechazado con mensaje claro (validación antes de tocar el archivo).
- `maturity.estado_riesgo({"risk_level": None, ...}) == "unclassified"`; `maturity.estado_riesgo({"risk_level": "low", ...}) == "classified"` — función pura, sin I/O.
- `project_status(repo_root)` (solo lectura) devuelve `project_stage`, `risk_level`, el estado derivado (`unclassified`/`classified`), el origen del stage actual (última entrada de `stage_history`: `via`+`reason`+`utc`), y ambos historiales — sin mutar nada.
- Operaciones de `maturity.py` (`project_init`/`calibrar`/`set_risk`) NUNCA escriben en `openspec/lifecycle/state.json` (verificable: bytes idénticos antes/después). Operaciones de `lifecycle.py`/`kdd_compat.py` NUNCA escriben en `.harmessi/project.json`.
- `tools/dsguard/maturity.py` tiene entrada VERBATIM en `MANIFEST`; `.harmessi/` está en `EXCLUSIONES_PERMANENTES`; instalación scratch deja `maturity.py` presente en destino Y **no** crea `.harmessi/project.json` (no es contenido estático, es estado generado en uso).

## Unidad de análisis / grain (condicional — data_understanding, feature_engineering, modeling)
No aplica — cambio de arquitectura/tooling del harness, no de datos de un proyecto DS.

## Cutoff / information boundary (condicional — feature_engineering, data_preparation, modeling)
No aplica — cambio de arquitectura/tooling del harness, no de datos de un proyecto DS.

## Baseline (condicional — modeling)
No aplica — cambio de arquitectura/tooling del harness, no de datos de un proyecto DS.

## Métrica primaria (condicional — modeling, evaluation)
No aplica — cambio de arquitectura/tooling del harness, no de datos de un proyecto DS.

## Métricas secundarias (opcional)
No aplica — cambio de arquitectura/tooling del harness, no de datos de un proyecto DS.

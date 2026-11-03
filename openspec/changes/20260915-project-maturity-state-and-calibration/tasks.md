# Tareas — 20260915-project-maturity-state-and-calibration

estado: cerrada

## Invocaciones planificadas
- Python Data Engineer (implementación + tests, invocación única): `tools/dsguard/maturity.py` completo, grupo `project` en `ds_guard.py`, manifest, tests. Produce: código + tests en un solo paso (política de eficiencia del usuario: minimizar intervenciones del writer).
- Data Science Reviewer (revisión de código, antes de que se ejecute nada, DESPUÉS de que la implementación esté completa): revisa el diff. Solo informa hallazgos.
- Python Data Engineer (post-revisión, planificada, corre siempre): corrige si hace falta, deja `estado: en_verificacion`.
- Python Data Engineer (cierre, planificada): `verification.md` con evidencia real, deja `estado: cerrada`.

## Tareas
- [x] `tools/dsguard/maturity.py`: catálogos (`PROJECT_STAGES`, `RISK_LEVELS`, `STAGES_INIT_PERMITIDOS`), excepción `MaturityEstadoError`, `state_path`, `estado_inicial`, `validar_estructura`, `leer_estado`, `escribir_estado`.
- [x] `inferir_stage(repo_root)`: existencia de `lifecycle.state_path`/`kdd_compat.state_path_legacy`, sin leer contenido.
- [x] `project_init(repo_root, stage=None, adopt=False)`: idempotente; sin flags o con `stage` → proyecto nuevo, `via: "explicit_init"` (default `"experiment"` si `stage` es `None` y `adopt` es `False`); con `adopt=True` → inferencia, `via: "migration_inference"`; `stage` y `adopt` mutuamente excluyentes (error de uso si se pasan ambos); rechaza `production_candidate`/`production` en cualquier modo explícito.
- [x] `calibrar(repo_root, stage, reason)`: exige `project.json` existente, exige `reason`, chequea `via: "promote"` en `stage_history` antes de escribir.
- [x] `set_risk(repo_root, nivel, reason)`: exige `reason` siempre, valida `nivel`, preserva historial.
- [x] `estado_riesgo(project_data)`: función pura.
- [x] `project_status(repo_root)`: solo lectura, incluye origen del stage actual y ambos historiales.
- [x] Grupo `project` en `ds_guard.py`: `init [--stage] [--adopt] [--json]` (`--stage` y `--adopt` mutuamente excluyentes, error de uso si se pasan ambos), `calibrate --stage --reason [--json]`, `set-risk {low,medium,high} --reason [--json]`, `status [--json]` — mismo patrón que `kdd`/`lifecycle`.
- [x] `tools/ds_init/manifest.py`: entrada VERBATIM de `maturity.py`; `.harmessi/` en `EXCLUSIONES_PERMANENTES`.
- [x] `tools/tests/test_manifest_dsguard_parity.py`: extender con aserción explícita para `maturity.py` (mismo patrón que `lifecycle.py`/`kdd_compat.py` de Change 2).
- [x] Tests — creación válida; `init` sin flags → `experiment`/`explicit_init` (default proyecto nuevo); `--stage` explícito (discovery/experiment) → `explicit_init`; `--adopt` inferido (discovery sin evidencia, experiment con lifecycle o legacy presente) → `migration_inference`; `--stage` y `--adopt` juntos → rechazado (error de uso, mutuamente excluyentes); rechazo de `--stage production_candidate/production` en init.
- [x] Tests — `schema_version` correcta, lectura válida, corrupto → fail-closed, schema desconocida → error controlado.
- [x] Tests — init idempotente (no reescribe), escritura atómica, round-trip, lectura no muta.
- [x] Tests — inferencia auditada en `stage_history` (entrada `via: "migration_inference"` con `reason` explicativo), risk nunca inferido (`risk_level` siempre `null` en cualquier inicialización, sea explícita o inferida).
- [x] Tests — `calibrate` sin `project.json` previo → error pidiendo `init`; con `reason` faltante → rechazado; caso exitoso con `via: "calibrate"` y `reason` preservado; recalibración múltiple sin `promote` previo (incluye hacia abajo); rechazo cuando `stage_history` ya tiene `via: "promote"` (inyectado a mano en el fixture).
- [x] Tests — `set_risk`: primera clasificación desde `null`, cambio posterior preservando historial, valor inválido rechazado, `reason` faltante rechazado.
- [x] Tests — separación de responsabilidades: operaciones de `maturity.py` no mutan `openspec/lifecycle/state.json` (bytes idénticos antes/después); operaciones de `lifecycle.py`/`kdd_compat.py` no mutan `.harmessi/project.json`.
- [x] Tests — manifest: `maturity.py` con entrada VERBATIM (test explícito hardcodeado); instalación scratch deja `maturity.py` presente y **no** crea `.harmessi/project.json`.
- [x] Ejecutar suite completa (`tools/tests/`, `tools/ds_init/tests/`) para confirmar sin regresión, y `harmessi doctor` para confirmar 0 ERROR.

## Dependencias
Catálogos/excepción antes que las funciones de lectura/escritura; `inferir_stage` antes que `project_init`; `project_init` antes que `calibrar`/`set_risk` (tests de calibrate necesitan un `project.json` previo); CLI depende de que `maturity.py` esté completo; manifest/parity puede ir en paralelo; tests al final de cada pieza. Depende de Change 1 (`lifecycle.state_path`) y Change 2 (`kdd_compat.state_path_legacy`), ambos ya cerrados.

## Próximo paso exacto
<!-- obligatorio si estado: pausada_bloqueada -->

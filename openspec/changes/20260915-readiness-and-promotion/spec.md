# Spec — 20260915-readiness-and-promotion

## Requisitos

### R1 — Principio de promoción (no negociable)
`project_stage` representa madurez ALCANZADA. `production_candidate` implica que ya se
completaron los requisitos básicos de production-readiness. `production` implica condiciones
operativas reales alcanzadas. Ninguna promoción se aplica solo porque el usuario la pidió —
siempre gateada por `evaluar_readiness`.

### R2 — Promoción secuencial estricta
Única transición normal permitida: `discovery→experiment`, `experiment→production_candidate`,
`production_candidate→production`. Prohibido: cualquier salto (`discovery→production_candidate`,
`discovery→production`, `experiment→production`) y cualquier downgrade. `calibrate` sigue
exclusivamente como mecanismo de adopción inicial, ya bloqueado desde que exista un
`stage_history` con `via="promote"` (`maturity.py:181-185`, sin tocar).

### R3 — CLI
```
python -m tools.ds_guard project readiness --target <experiment|production_candidate|production> [--json]
python -m tools.ds_guard project promote <experiment|production_candidate|production> --reason "<texto>" [--json]
python -m tools.ds_guard mlops evidence add --tier <production_readiness|operations> --capability <nombre> --artifact <ruta-relativa-al-repo> --reason "<texto>" [--json]
```
`readiness` es de solo lectura, siempre. `promote` requiere `--reason` (obligatorio, no vacío),
requiere `<stage>` explícito, solo permite el próximo stage secuencial exacto desde el
`project_stage` actual, re-evalúa `evaluar_readiness(repo_root, target)` inmediatamente antes de
escribir: si hay algún `FAIL` → no modifica `project.json`; si todo pasa → actualiza
`project_stage` y agrega a `stage_history`: `{"from": ..., "to": ..., "via": "promote", "reason":
..., "utc": ...}`. No se implementa `harmessi project ...` en este change.

### R4 — Readiness discovery→experiment
`evaluar_readiness(repo_root, "experiment")` — `PASS` requerido:
- `.harmessi/project.json` existe y es válido (código `READINESS-PROJECT-VALID`).
- `openspec/lifecycle/state.json` existe y es válido (código `READINESS-LIFECYCLE-VALID`).
No se exige todavía: `risk_level` clasificado, MLOps foundations en `PASS`, modelo, baseline,
cutoff, artifacts de producción. Si el lifecycle no existe → `FAIL` con mensaje accionable
("correr `ds_guard lifecycle migrate` o inicializar el lifecycle"); nunca se crea silenciosamente
desde acá.

### R5 — Readiness experiment→production_candidate
`evaluar_readiness(repo_root, "production_candidate")` evalúa, siempre en este orden, sin
short-circuit:
1. **Prerrequisitos** (R4 repetido: `READINESS-PROJECT-VALID`, `READINESS-LIFECYCLE-VALID`) — si
   cualquiera de los dos no está disponible, el resto de los gates que dependen de leer esos
   archivos se reportan igual, cada uno `FAIL` con mensaje explícito "no se pudo evaluar: <cuál
   prerrequisito falta>" (nunca se omiten silenciosamente — "report ALL checks, no short
   circuit").
2. **Gobernanza mínima** (`READINESS-RISK-CLASSIFIED`) — GATE: `risk_level` debe estar clasificado
   (`low|medium|high`); `risk_level=null` → `FAIL`. No se agregan controles distintos por nivel.
3. **Lifecycle CRISP-DM** — GATE, una entrada por fase, código
   `READINESS-CRISPDM-<FASE-EN-MAYUSCULAS-CON-GUIONES>`: `business_understanding`,
   `data_understanding`, `data_preparation`, `modeling`, `evaluation`, `production_readiness` deben
   estar `cerrada`. Cualquier otro estado (`no_iniciada`/`en_progreso`) → `FAIL` específico por
   fase, mensaje nombra la fase y su estado actual.
4. **MLOps foundations** (reusa `mlops_foundations.evaluar_foundations`, nunca lo modifica):
   - `reproducibilidad`, `versionado`, `artifacts`: código `READINESS-FOUNDATIONS-<CAP>`. `PASS`
     subyacente → `PASS`. Cualquier otro status subyacente (`WARN`/`FAIL`/`N/A`) → `FAIL` en este
     contexto de readiness (severidad es contextual a readiness, `mlops_foundations.py` no se
     toca ni cambia su propio significado).
   - `lineage`: código `READINESS-FOUNDATIONS-LINEAGE`. Status subyacente se preserva TAL CUAL
     (`WARN`/`N/A` no bloquean — excepción explícita y única de este change; si alguna vez diera
     `PASS`/`FAIL`, también se preserva tal cual).
5. **Production Readiness capabilities** — GATE, código `READINESS-PRODREADY-<CAP>` para cada una
   de las 5: `packaging`, `environment_reproducible`, `inference_contract`, `inference_tests`,
   `trazabilidad_fuerte`. `PASS` solo si `mlops_evidence.evidencia_valida(repo_root,
   "production_readiness", cap)` es `True`. Reglas específicas (R7/R8).

### R6 — Mecanismo de evidencia genérico (`mlops_evidence.py`)
`agregar_evidencia(repo_root, tier, capability, artifact_rel_path, reason) -> dict`:
- `tier` debe ser `production_readiness` u `operations` (nunca `foundations`, que usa su propio
  mecanismo de snapshot desde Change 5).
- `capability` debe pertenecer a `lifecycle.MLOPS_CAPACIDADES[tier]`.
- `--artifact` obligatorio; el archivo debe existir; debe ser un archivo, no un directorio (en
  esta versión); debe resolver dentro del repo (`pathguard.resolver_ruta_relativa`); se rechaza
  fuera del repo.
- Respeta las protecciones existentes de `pathguard` (holdouts/secretos): si la ruta matchea un
  patrón de secreto (`pathguard.SECRETOS_HARDCODEADOS` + `secretos_extra`) o un holdout sin
  excepción de lectura vigente → rechazado. `guardrails.json` corrupto → fail-closed (rechazado).
- `--reason` obligatorio, no vacío.
- Se calcula SHA-256 binario del contenido (chunked, nunca el archivo completo en memoria).
- Timestamp UTC.
- Se guarda la ruta relativa al repo (POSIX).
- Operación explícita y atómica — nunca invocada implícitamente por `readiness`.
- Forma del registro: `{"tipo": "artifact_evidence", "path": "...", "sha256": "...", "reason":
  "...", "utc": "..."}`, agregado a `mlops.<tier>.<capability>.evidencia` en
  `openspec/lifecycle/state.json` (coexiste con las formas `{change_id, artefacto}` y
  `{tipo:"check_snapshot",...}` ya presentes en esa misma lista heterogénea, sin bump de
  `schema_version` — confirmado que `lifecycle.validar_estructura` nunca inspecciona las claves
  internas de cada entrada).
- Requiere que `openspec/lifecycle/state.json` ya exista (propaga `FileNotFoundError`/
  `LifecycleEstadoError`, nunca lo crea).

### R7 — Validación de evidencia
`evidencia_valida(repo_root, tier, capability) -> (bool, detalle)`: `True` solo si existe al menos
una entrada `{"tipo":"artifact_evidence", ...}` en `mlops.<tier>.<capability>.evidencia` cuyo
archivo TODAVÍA existe, cuya ruta sigue dentro del repo, y cuyo SHA-256 actual coincide con el
registrado. Si la evidencia existe pero el archivo desapareció/cambió/el hash no coincide → esa
entrada se trata como inválida (nunca se toma evidencia obsoleta como válida); si ninguna entrada
es válida → `False` con detalle explicando por qué (ausente vs. obsoleta).

### R8 — Reglas por capability de production_readiness
- `packaging`: `PASS` = evidencia válida asociada a `packaging`. Sin formato específico impuesto.
- `environment_reproducible`: `PASS` si existe una señal determinista de entorno reproducible —
  reusa los mismos lockfiles ya reconocidos por Change 5
  (`requirements-lock.txt`/`poetry.lock`/`Pipfile.lock`, ver
  `mlops_foundations._ARCHIVOS_LOCKFILE`) — o, si no hay lockfile, satisfacible vía evidencia
  explícita válida. No se inventan nuevos gestores de paquetes.
- `inference_contract`: `PASS` = evidencia explícita válida (puede representar contrato
  online/batch/scoring interface; Harmessi no impone HTTP serving).
- `inference_tests`: `PASS` = evidencia explícita válida de tests de inferencia/scoring.
- `trazabilidad_fuerte`: `PASS` = evidencia explícita válida que documente/reconstruya relación
  código/datos/modelo/resultado suficiente. Nunca se asume que el `lineage` WARN actual equivale a
  trazabilidad fuerte.

### R9 — Readiness production_candidate→production
`evaluar_readiness(repo_root, "production")` incluye TODOS los gates de R5 (deben seguir
cumpliéndose), MÁS:
- CRISP-DM: `production_readiness` → `cerrada` (repetido de R5); `deployment` → `cerrada`
  (`READINESS-CRISPDM-DEPLOYMENT`); `monitoring` → al menos `en_progreso` o `cerrada`
  (`READINESS-CRISPDM-MONITORING`, `no_iniciada` → `FAIL`).
- MLOps operations — GATE, código `READINESS-OPS-<CAP>` para cada una de las 7:
  `deployment`, `cicd`, `monitoring`, `rollback`, `drift`, `alerts`, `retraining`. `PASS` solo si
  `mlops_evidence.evidencia_valida(repo_root, "operations", cap)` es `True`. Interpretación:
  `retraining` no exige reentrenamiento automático (evidencia puede documentar una política/
  procedimiento manual o una decisión explícita de cuándo/si reentrenar); `cicd` representa
  cualquier mecanismo operativo adoptado, sin forzar un proveedor específico; `deployment` no
  implica Kubernetes/nube específica; `monitoring`/`rollback`/`drift`/`alerts` requieren evidencia
  auditable de cómo se resuelve esa responsabilidad. No se integra ninguna herramienta externa.

### R10 — N/A, WARN, FAIL, technical_error
Para un gate obligatorio del target: `PASS` satisface; `WARN` no satisface si la matriz lo define
como gate; `FAIL` no satisface; `N/A` no satisface cuando el requisito es obligatorio para ese
target. Excepción explícita única: `lineage` en `production_candidate`/`production` permanece no
bloqueante (`WARN`/`N/A` se preservan, nunca se convierten a `FAIL`). No se construye ningún
sistema de waivers/exemptions en este change. `CheckResult(FAIL, kind="technical_error")` (p. ej.
`project.json`/`lifecycle/state.json` corruptos) SIEMPRE bloquea la promoción; nunca se trata como
incumplimiento normal; nunca muta `project_stage`.

### R11 — Read-only / atomicidad
`project readiness` es estrictamente de solo lectura: no modifica `.harmessi/project.json`,
`openspec/lifecycle/state.json`, el decision ledger, ni ninguna evidencia MLOps. `project promote`
debe: (1) correr readiness de solo lectura; (2) si hay algún `FAIL` → devolver los resultados, no
mutar nada; (3) si pasa → modificar ÚNICAMENTE `.harmessi/project.json` (`project_stage` +
`stage_history`). Nunca modifica el lifecycle automáticamente durante `promote`.

### R12 — Salida de `readiness`
Reporta TODOS los checks, sin short-circuit. Formato texto simple (sin UX sofisticada): título
según target, una línea por resultado (`STATUS  mensaje`), resumen final `Resultado: READY` o
`Resultado: NOT READY` (`READY` sii no hay `FAIL` entre los resultados, vía
`checks.hay_bloqueo` — mismo criterio que el engine, sin reinventar lógica de bloqueo). `--json`
expone la lista de `CheckResult.to_dict()` más un campo `ready: bool`, sin duplicar lógica de
formato.

### R13 — Idempotencia/atomicidad de promoción y evidencia
Un `promote` exitoso agrega EXACTAMENTE una entrada nueva a `stage_history`. Repetir `promote
production_candidate` estando ya en ese stage → error controlado explícito (transición inválida,
mismo criterio que R2), sin mutar nada, sin duplicar historial (se deriva naturalmente: el
"próximo stage secuencial" desde `production_candidate` es `production`, nunca
`production_candidate` de nuevo). `mlops evidence add`: registrar exactamente el mismo
`{capability, path, hash}` → no duplica (dedup determinista, devuelve la entrada existente con
`agregado=False, duplicado=True`).

### R14 — Riesgo (alcance acotado)
`risk_level` clasificado es gate desde `production_candidate` en adelante (R5.2); este change NO
cambia requisitos según el valor específico (low/medium/high) — gobernanza basada en riesgo queda
fuera de alcance.

### R15 — Decision ledger
No se modifica el schema del ledger. `promote` NO registra automáticamente un evento en el
decision ledger — `stage_history` ya es el audit trail de madurez.

### R16 — Principio explícito (foundations ≠ production-ready)
Un `PASS` de `mlops foundations` NO implica "production ready" — p. ej. `artifacts` da `PASS`
porque existe un `profile.json`, pero `production_candidate` sigue exigiendo packaging +
inference contract/tests + trazabilidad fuerte + lifecycle + risk clasificado. Ambos conceptos
nunca se confunden en el código ni en los mensajes.

### R17 — Manifest
`tools/dsguard/readiness.py` y `tools/dsguard/mlops_evidence.py` con entrada VERBATIM en
`MANIFEST`. Test de paridad extendido (clase explícita hardcodeada, mismo patrón que las 4 clases
ya existentes en `test_manifest_dsguard_parity.py`). `archivos_clave` de
`test_integracion_instalacion.py` incluye ambos módulos. Scratch install verificado.

## Criterios de aceptación

**`mlops_evidence.py`:**
- `agregar_evidencia` con artifact válido dentro del repo → agrega entrada `artifact_evidence`
  con sha256/reason/utc correctos, devuelve `{"agregado": True, "duplicado": False, "entrada":
  {...}}`.
- Artifact fuera del repo (ruta absoluta fuera de `repo_root`, o `../` que escapa) → error de
  dominio (`EvidenciaError`), no muta nada.
- Artifact inexistente → `EvidenciaError`, no muta nada.
- Artifact que es un directorio → `EvidenciaError`, no muta nada.
- `tier` inválido (ni `production_readiness` ni `operations`) → `EvidenciaError`.
- `tier="foundations"` → `EvidenciaError` (ese tier usa el mecanismo de Change 5, no este).
- `capability` que no pertenece al `tier` dado → `EvidenciaError`.
- `--reason` vacío/ausente → `EvidenciaError`.
- Artifact dentro de un holdout declarado en `guardrails.json`, sin excepción de lectura vigente →
  `EvidenciaError` (rechazado, mismo criterio que `pathguard`).
- Artifact que matchea un patrón de `SECRETOS_HARDCODEADOS`/`secretos_extra` → `EvidenciaError`.
- `guardrails.json` corrupto → `EvidenciaError` (fail-closed, no se asume default seguro).
- Registrar dos veces exactamente `{capability, path, hash}` → segunda llamada no duplica entrada,
  devuelve `duplicado=True`.
- Modificar el contenido del artifact entre dos registros con la misma ruta → hash distinto → SÍ
  agrega una segunda entrada (no es el mismo `{capability, path, hash}`).
- `openspec/lifecycle/state.json` ausente → propaga `FileNotFoundError`, no lo crea.
- `evidencia_valida`: archivo presente + hash coincide → `True`. Archivo borrado después de
  registrar → `False` con detalle "obsoleta". Archivo modificado después de registrar (hash ya no
  coincide) → `False`. Sin ninguna entrada `artifact_evidence` para esa capability → `False` con
  detalle "sin evidencia".

**`readiness.py` — `evaluar_readiness`:**
- `target="experiment"`, lifecycle válido + project.json válido → todos `PASS`, `ready=True`.
- `target="experiment"`, lifecycle ausente → `FAIL` específico, `ready=False`, no muta nada.
- `target="experiment"`, `project.json` corrupto → `technical_error`, `FAIL`, no muta nada.
- `target="experiment"` no exige `risk_level`/foundations/producción — confirmado que ninguno de
  esos gates aparece en la matriz de este target.
- `target="production_candidate"`, `risk_level=null` → `FAIL` específico de riesgo, resto de
  checks igual se reportan (no short-circuit).
- `target="production_candidate"`, cada fase CRISP-DM faltante (una por una, `no_iniciada` y
  `en_progreso`) → `FAIL` específico de esa fase, mensaje nombra la fase.
- `target="production_candidate"`, `mlops_foundations` da `WARN` en `reproducibilidad` → readiness
  `FAIL` en `READINESS-FOUNDATIONS-REPRODUCIBILIDAD` (mismo patrón para `versionado`/`artifacts`).
- `target="production_candidate"`, `lineage` en `WARN` → readiness `WARN` en
  `READINESS-FOUNDATIONS-LINEAGE`, NO bloquea (`ready` puede seguir `True` si todo lo demás pasa).
- `target="production_candidate"`, cada una de las 5 `production_readiness` capabilities sin
  evidencia → `FAIL` específico por capability (una por una).
- `target="production_candidate"` con TODO completo (risk clasificado, 6 fases CRISP-DM cerradas,
  foundations reproducibilidad/versionado/artifacts en `PASS`, lineage en `WARN` no bloqueante, 5
  capabilities con evidencia válida) → `ready=True`.
- `target="production"`, prerequisitos de `production_candidate` incumplidos → siguen bloqueando
  igual (se re-evalúan, no se asumen).
- `target="production"`, fase `deployment` no `cerrada` → `FAIL` específico.
- `target="production"`, fase `monitoring="no_iniciada"` → `FAIL` específico; `en_progreso` o
  `cerrada` → no bloquea ese gate.
- `target="production"`, cada una de las 7 `operations` capabilities sin evidencia → `FAIL`
  específico por capability (una por una).
- `target="production"`, evidencia de una capability presente pero con hash obsoleto (archivo
  modificado después de registrar) → `FAIL` (evidencia stale nunca es válida).
- `target="production"` con TODO completo → `ready=True`, se puede promover.
- `evaluar_readiness` nunca modifica `.harmessi/project.json`, `openspec/lifecycle/state.json`,
  el decision ledger, ni evidencia MLOps, en ningún escenario (bytes idénticos antes/después,
  verificado en cada test relevante).

**`readiness.py` — `promote`:**
- Secuencia correcta (`discovery→experiment`, `experiment→production_candidate`,
  `production_candidate→production`) con readiness satisfecha → `project_stage` actualizado,
  exactamente una entrada nueva en `stage_history` con `via="promote"`.
- Salto (p. ej. `discovery→production_candidate`) → rechazado, error de dominio, sin mutación.
- Downgrade (p. ej. `production_candidate→experiment`) → rechazado, sin mutación.
- `--reason` ausente/vacío → rechazado, sin mutación.
- Readiness con algún `FAIL` → `promote` devuelve los resultados, `project.json` NO se modifica
  (bytes idénticos antes/después).
- Readiness con `technical_error` → tratado igual que cualquier `FAIL` (bloquea, sin mutación).
- Promoción exitosa → `stage_history` gana +1 entrada, nunca reescribe entradas previas.
- Repetir `promote production_candidate` estando ya en `production_candidate` → error de dominio
  (el próximo stage secuencial válido es `production`, no `production_candidate`), sin duplicar
  historial.
- Después de un `promote` exitoso, `maturity.calibrar(...)` levanta `MaturityEstadoError` (lock ya
  construido en Change 3, confirmado en este change end-to-end).

**CLI (`ds_guard.py`), subprocess real contra repo git temporal:**
- `project readiness --target <cada uno de los 3>` — texto y `--json`, exit code
  `checks.exit_code` (1 si algún `FAIL`, 0 si no).
- `project promote <stage> --reason "..."` — éxito (exit 0, `project_stage` actualizado), FAIL de
  readiness (exit 1, sin mutación), transición inválida (exit 1, sin mutación), `--reason`
  faltante (error de argparse, exit 2).
- `mlops evidence add --tier ... --capability ... --artifact ... --reason ...` — éxito (exit 0),
  cada error de dominio (`EvidenciaError`) → exit 1, `lifecycle/state.json` ausente → exit 2 con
  mensaje accionable.

**Regresión:**
- Suite completa `tools/tests/`, `tools/harmessi/tests/`, `tools/ds_init/tests/` sin regresión.
- Manifest: paridad explícita para `readiness.py`/`mlops_evidence.py`; scratch install deja ambos
  archivos presentes; instalación scratch no requiere ningún import faltante para correr
  `readiness`/`promote`/`mlops evidence`/`mlops status`/`project status`/`checks`.
- `harmessi doctor` sobre este repo: mismo conteo de ERROR (0 nuevos), sin regresión de WARN
  preexistentes salvo hallazgo real nuevo explicado.

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

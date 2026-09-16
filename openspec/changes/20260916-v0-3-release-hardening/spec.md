# Spec — 20260916-v0-3-release-hardening

## Requisitos

### R1 — Versión canónica única
`tools/ds_init/version.py:HARNESS_VERSION = "0.3.0"`. `CITATION.cff:version: 0.3.0`,
`date-released` actualizado a la fecha real de este cierre. Ninguna otra constante de versión
nueva se introduce. Las ~30 anotaciones históricas "Bloque N, reliability v0.2.0" (docstrings que
documentan CUÁNDO se introdujo un mecanismo pasado) NO se modifican — no son la versión actual del
harness, cambiarlas sería introducir información falsa.

### R2 — Privacidad (ya corregido durante el audit, verificado como criterio de cierre)
Grep exhaustivo sobre el working tree completo (`.py`/`.md`/`.json`/`.cff`/`.txt`) para: `AGD`,
`UNCO`, `Model-churn`/`Model_churn`, nombres de cliente/proyecto privados, `Federico`/`fcolombo`
fuera de metadata pública legítima (autoría en `CITATION.cff`/`LICENSE`/mensajes de aprobación
SDD, que SÍ son legítimos), rutas `C:\Datos\`/`C:\Users\`, rutas absolutas locales, emails
personales fuera de metadata pública, tokens/secrets, URLs privadas — cero resultados salvo
metadata pública legítima (autoría, URL de GitHub pública ya en `README.md`/`CITATION.cff`).

### R3 — README mínimamente correcto
`README.md` debe mencionar, sin necesidad de reescritura completa: `ds_guard.py` como CLI (no solo
`doctor`/`ds_profile`/`ds_init`); `project_stage`/`installation_stage` como ejes distintos;
CRISP-DM como lifecycle backbone con KDD subordinado y MLOps progresivo; `status` unificado;
`readiness`/`promote`; progressive sync (`ds_init sync`); limitaciones relevantes (runtime
completo en discovery, sin deployment/monitoring reales). No se reescribe la sección "Platform
compatibility"/"Development"/"License" si siguen siendo correctas.

### R4 — Regresión completa, 0 failures no diagnosticados
`tools/tests/`, `tools/harmessi/tests/`, `tools/ds_init/tests/`, `tools/ds_profile/tests/`
completos. Cualquier fallo se diagnostica explícitamente (fixture bug vs. bug real) antes de
tocar nada — un fixture bug se corrige solo si está claramente demostrado por lectura del código
de producción real (mismo criterio ya aplicado en Changes 5-9). Ninguna suite se descarta como
"no relacionada" sin ese diagnóstico explícito documentado.

### R5 — `harmessi doctor` final, 0 ERROR
Corrido con el repo en el estado final de este change (después de todos los fixes, antes de
`control.json` regenerado — ver R8 para el orden exacto). Cada WARN/N-A restante se clasifica
explícitamente: esperado (drift de working tree sin commitear, drift histórico de self-hosting ya
documentado en changes anteriores), deuda conocida, o blocker. Ningún WARN se "arregla"
automáticamente solo por aparecer — solo si es un bug real.

### R6 — Scratch installs E2E (discovery y experiment)
Dos repos git temporales reales, independientes (nunca mocks para esto). Discovery
(`--stage discovery --execute`): instalación exitosa; repo Git válido; `.ds_init/control.json`
correcto (`installation_stage: "discovery"`); imports disponibles (`ds_guard.py` importable);
`ds_guard status` (sin `--change-id`) funciona; ningún componente de `experiment` instalado
(agentes, `decision-ledger.md` ausentes). Experiment (`--nombre X --execute`, sin `--stage`
explícito): default `experiment`; agentes de `experiment` instalados; lifecycle/project state
coherentes (pueden no existir todavía — `project_stage`/lifecycle nacen perezosos, `ds_init` no
los crea); `status` funciona; `mlops foundations` evaluable sin `ImportError`; `control.json`
correcto.

### R7 — Progressive sync E2E
Sobre el fixture de discovery de R6 (o uno nuevo equivalente): `sync --stage experiment --execute`
→ `sync --stage production_candidate --execute` → `sync --stage production --execute`, secuencial,
con commits entre pasos (working tree limpio exigido por `preflight`). En cada salto: solo el
delta faltante se agrega (verificado con hash de un archivo de discovery sin cambios); segundo
`sync` al mismo target es no-op idempotente (sin escritura, `control.json` bytes idénticos);
`installation_stage` avanza correctamente; `project_stage` NO cambia en ningún momento (verificado
leyendo `.harmessi/project.json` antes/después, si existe); ningún `artifact_evidence` se registra
automáticamente. Para el salto a `production_candidate`/`production` que requeriría `project_stage`
real vía `promote` normal (no aplica a `sync`, que es un eje físico independiente — R7 no necesita
`project_stage` para funcionar, confirmado en Change 7/8) — sin bypass oculto, `sync` opera
puramente sobre `installation_stage`.

### R8 — Readiness/promotion smoke
Reusar fixtures ya existentes de `tools/tests/test_readiness.py` cuando sea suficiente — no
reconstruir la matriz completa. Smoke real: `project readiness --target experiment` (repo con
lifecycle válido → READY); `project readiness --target production_candidate` (repo sin risk
clasificado → NOT READY, FAIL específico); `project readiness --target production` (repo
incompleto → NOT READY). Promoción secuencial: salto rechazado sin mutación; `FAIL` no muta
`project_stage`; promoción exitosa agrega exactamente una entrada a `stage_history`; repetir el
mismo `promote` no duplica; un escenario con `technical_error` (p. ej. `project.json` corrupto)
bloquea igual que un `FAIL` normal.

### R9 — Evidence smoke
`mlops evidence add` con: artifact real válido dentro del repo (`agregado: True`); mismo
`{capability, path, hash}` repetido (`duplicado: True`, sin segunda entrada); archivo modificado
entre dos registros con la misma ruta (sí agrega, hash distinto); evidencia con archivo borrado
después de registrar → `evidencia_valida` da `False` ("obsoleta"); path fuera del repo → rechazado
(`EvidenciaError`); ningún template/scaffold (`production-readiness.md`/`operations.md`) se cuenta
automáticamente como evidencia solo por existir. No se agregan tipos de evidencia nuevos.

### R10 — Status smoke
`ds_guard status` (texto y `--json`) corrido sobre: discovery, experiment, production_candidate,
production (fixtures reales o reusados de `test_status.py`), un proyecto con `installation_stage`
desalineado de `project_stage` (ambos sentidos), y un proyecto legacy (`control.json` sin
`installation_stage`) si hay fixture ya disponible. Verificado: read-only (bytes idénticos
antes/después); `next_target` correcto por stage; degradación con gracia de `harness` en un
destino scratch (sin `tools/harmessi/` instalado); JSON serializable y determinista (dos corridas
seguidas, mismo input → mismo output); ningún gate duplicado (compara contra lo que
`readiness.evaluar_readiness` devuelve directamente, sin reinterpretación adicional).

### R11 — Compatibilidad legacy/v0.2
Reusar fixture v0.2 si ya existe en algún test de Changes 1/2/7 (`kdd_compat`/`legacy`); si no,
crear un fixture mínimo representativo (NO una copia gigante del repo real): `control.json` sin
`installation_stage`, `openspec/kdd/state.json` con las 10 etapas legacy, sin
`openspec/lifecycle/state.json`. Verificar: `lifecycle migrate` funciona; inferencia legacy de
`installation_stage` funciona sin mutar nada; `harmessi doctor` no explota; `status` no explota
(degrada con gracia); `sync` posterior funciona usando la inferencia como base. Ninguna lectura
simple (`doctor`, `status`, `kdd status`) reescribe el estado legacy.

### R12 — Read-only audit (confirmación final, no nueva implementación)
Para `status.evaluar_status`, `readiness.evaluar_readiness`, `doctor.ejecutar`,
`mlops_foundations.evaluar_foundations`, `legacy.inferir_installation_stage`: bytes idénticos de
`.harmessi/project.json`, `.ds_init/control.json`, `openspec/lifecycle/state.json` antes/después,
en al menos un escenario real por función (reusando tests ya existentes de Changes 3/5/6/7/8 más
los nuevos smoke tests de este change).

### R13 — Apertura/cierre del cambio, y regeneración final de `control.json`
El único paso de escritura real sobre ESTE repo (más allá de los archivos propios del change SDD y
los fixes de contenido de R1-R3) es la regeneración de `.ds_init/control.json`
(`control.regenerar_control`, mecanismo ya existente, sin reimplementar), ejecutada UNA SOLA VEZ,
al final, después de que todos los demás archivos de este change ya estén en su versión final —
nunca prematuramente (si se regenerara antes de terminar los demás fixes, quedaría desactualizado
de nuevo).

## Criterios de aceptación
Ver el detalle de cada verificación E2E en R4-R12 arriba — son, en sí mismos, los criterios de
aceptación de este change (cada uno debe ejecutarse realmente y su resultado quedar documentado en
`verification.md` con evidencia concreta, nunca solo "debería funcionar"). Adicionalmente:

- `harmessi doctor` final: 0 `[ERROR]`, y cada `[WARN]`/`[N/A]` clasificado explícitamente.
- Las 4 suites de test: 0 failures sin diagnóstico.
- README/CITATION.cff/`version.py` consistentes entre sí (misma versión `0.3.0` en los tres).
- `verification.md` incluye el texto completo de release notes de v0.3.0 y la lista de known
  limitations/deuda v0.4+, sin publicar ningún release real.
- `git status`/`git diff --stat` finales limpios de cualquier archivo temporal/backup/checkpoint
  de notebook/cache accidental (ninguno esperado, pero verificado explícitamente).
- `.ds_init/control.json` de este repo, regenerado al final: `harness_version: "0.3.0"`,
  `archivos[]` incluye todos los módulos VERBATIM/PLANTILLA vigentes de Changes 1-9.

## Unidad de análisis / grain (condicional — data_understanding, feature_engineering, modeling)
No aplica — cambio de hardening/release del harness, no de datos de un proyecto DS.

## Cutoff / information boundary (condicional — feature_engineering, data_preparation, modeling)
No aplica.

## Baseline (condicional — modeling)
No aplica.

## Métrica primaria (condicional — modeling, evaluation)
No aplica.

## Métricas secundarias (opcional)
No aplica.

# ARCHITECTURE.md — Harmessi core/adapter boundary

Producido por v0.4 Change 3 (`20260916-portable-core`). Documenta la separación core/adapter que
**ya existe en la práctica** dentro de `tools/`, formaliza las reglas de dependencia entre ambos, y
registra explícitamente dónde esa separación está incompleta hoy — sin mover, renombrar ni
reestructurar ningún archivo. La reestructuración física, si se decide, es alcance de un change
futuro (ver "Deuda registrada" al final).

## 1. Principio

**Core**: lógica Python neutral respecto de quién la invoca. No lee `stdin` esperando el JSON de un
hook de Claude Code, no conoce el protocolo `PreToolUse` (nombres de campo, exit-code-como-decisión),
no asume que el invocador es un agente de IA. Recibe/devuelve tipos simples (`str`/`Path`/`dict`/
`list`) o dataclasses propias del dominio (`CheckResult`, `Finding`, `ArchivoCambiado`, etc.).

**Adapter**: la capa fina que traduce el mecanismo específico de Claude Code (hooks `PreToolUse` vía
stdin JSON + exit code, lanzadores que resuelven el intérprete del `.venv` del repo) hacia/desde
llamadas a funciones de core. Un adapter puede importar core; core nunca importa un adapter.

Esta separación existe hoy de forma **desigual**: en algunos casos ya está limpia (pathguard), en
otros la lógica de decisión vive mezclada con la lectura de stdin en el mismo archivo (ver §4).

## 2. Inventario

### 2.1 Core (neutral, sin protocolo de Claude Code)

| Módulo | Rol |
|---|---|
| `tools/dsguard/core.py`, `repo.py`, `checks.py` | Utilidades base: JSON/hash/git/vocabulario de checks |
| `tools/dsguard/sdd.py`, `scope.py`, `decision.py` | Estado y reglas de SDD/alcance/decision ledger |
| `tools/dsguard/lifecycle.py`, `kdd.py`, `kdd_compat.py`, `maturity.py` | Lifecycle CRISP-DM/KDD/madurez |
| `tools/dsguard/readiness.py`, `mlops_foundations.py`, `mlops_evidence.py` | Readiness/MLOps |
| `tools/dsguard/scientific_validity.py` | Scientific validity checks (v0.4 Change 0) |
| `tools/dsguard/notebooks.py` | Diff de notebooks (no ejecuta nada) |
| `tools/dsguard/status.py` | Status unificado (agrega los anteriores) |
| `tools/dsguard/guardrails_drift.py`, `pep440_subset.py` | Módulos solo-stdlib de dsguard (drift semántico de `guardrails.json`; subconjunto PEP 440); `guardrails_drift.py` no importa `autonomy`: el llamador (doctor) inyecta `parse_autonomy_policy` |
| `tools/dsimpact/*` (todo el paquete) | Impact preflight (v0.4 Change 1) |
| `tools/ds_profile/*` (todo excepto lo que reusa `pathguard` como config) | Profiling de datasets |
| `tools/nbrunner/core.py`, `execute.py`, `fsdiff.py`, `manifest.py` | Ejecución controlada de notebooks (invocada por el adapter, no es adapter en sí) |
| `tools/launcher_common.py` | **Mixto, ver §2.3** — la mayoría de sus funciones (`resolver_venv_dir`, `ruta_interprete_venv`, `resolver_repo_root`) son utilidades neutras de resolución de venv/repo Git, usadas también por `tools/harmessi/doctor.py` (core, diagnóstico) — pero también contiene `lanzar_hook`, que sí es específica de Claude Code |
| `tools/ds_guard.py`, `tools/ds_profile/cli.py`, `tools/dsimpact/cli.py`, `tools/harmessi/cli.py`, `tools/notebook_runner.py` | CLIs `argparse` — portables: cualquier orquestador que pueda invocar un proceso puede usarlos, no conocen el protocolo de hooks (`tools/notebook_runner.py`, v0.8 Change 2, cierra el gap del audit de `notebook-runner`: mismo patrón `_repo_root()` que `ds_guard.py`, compone `tools.leadrun.notebooks` -- único import calificado `tools.*` de todo el paquete `leadrun`, sin lógica nueva de validación) |
| `tools/ds_init/*` | Instalador/scaffolding — su propia lógica (planner, writer, templating, control.json) es agnóstica; el *contenido* que instala está hoy pensado para Claude Code, pero el instalador mismo no se invoca como hook ni depende del protocolo de hooks |
| `tools/providers/core.py` | Contrato neutral de invocación multi-proveedor (v0.5 Change 0) — "adapter" en el sentido de patrón de diseño (adapter de proveedor de IA), no confundir con la acepción "Adapter" de §2.2 (protocolo `PreToolUse` de Claude Code); este módulo es core porque no conoce ningún protocolo específico de invocador, es un contrato neutral que las 4 implementaciones concretas satisfacen |
| `tools/harmessi_bench/core.py` | Tipos neutrales y scoring determinista del framework de evals (v0.5 Change 1) — no importa `tools.providers` ni ningún proveedor concreto; `runner.py` (no listado acá, mismo criterio que las 4 implementaciones de adapters de Change 0) es quien invoca un target reusando el contrato de `tools/providers/core.py` y `storage.py` quien persiste resultados en `.harmessi/evals/<run_id>/result.json` (mismo patrón de `ds_profile` → `.harmessi/profiles/`); no conoce protocolo de hooks, es core. |
| `tools/routing/core.py` | Resolución determinista de routing provider/model/effort por rol+tarea (v0.5 Change 2; extendido de forma aditiva con `fallback_chain` en v0.5 Change 3) -- puramente declarativo (lee una `RoutingPolicy` ya construida, nunca infiere ni mide nada); no importa `tools.providers` ni ningún proveedor concreto, es core. `policy.py` (no listado acá, mismo criterio que Change 0/1) carga la política opcional desde `.harmessi/routing.json` (ausente = sin política declarada, nunca heurística) y valida su forma. |
| `tools/fallback/core.py` | Motor de fallback técnico entre proveedores (v0.5 Change 3) -- decide reintentar SOLO cuando `InvocationResult.availability_error` es elegible (`quota`/`unavailable`/`unauthenticated`, ver `classify_availability_error` de Change 0); nunca por error semántico/de código, hallazgo de reviewer, test fallido o mala calidad de output (esas señales ni siquiera se importan acá) -- es core, no conoce protocolo de hooks. |
| `tools/reporting/core.py` | Contratos neutrales de reporting gobernado (v0.6 Change 0: `Report`/`Chapter`/`TableArtifact`/`FigureArtifact`/`FigureSpec`/`Insight`, serialización determinista y hash de contenido) -- solo stdlib; no importa Plotly, HTML, pandas, numpy, `dsguard`, `ds_profile` ni ningún hermano de `tools/reporting`, ni conoce un dominio (p. ej. EDA) o backend gráfico concreto; valida solo estructura (la completitud semántica/evidencial es de un Change posterior); no conoce protocolo de hooks, es core. |
| `tools/reporting/governance.py` | Output guard declarativo de reportes (v0.6 Change 1) -- solo lectura: compone `dsguard` (`checks`, `pathguard`, `repo`, `scientific_validity`, `core`) y `reporting.core` con policy opcional `.harmessi/reporting-policy.json` (destino por scope, aislamiento exploratorio, holdout, cutoff); todo resultado es un `dsguard.checks.CheckResult` (sin engine propio) y solo evalúa rutas, nunca abre datos; importa `dsguard` (dirección permitida por la regla 6) pero no `ds_profile`; no conoce protocolo de hooks (usa `pathguard.evaluar_tool_call` como función, no lee stdin), es core. |
| `tools/reporting/cli.py` | CLI `argparse` de reporting gobernado (v0.6 Change 1: `check-inputs`, `check-destination`; Change 3: `validate` y `REPORT-ISOLATION-HASH` aditivo en `check-inputs`; `python -m tools.reporting`) -- Change 4: `render` (escribe `report.html` de forma atómica; con `--check` no escribe); `check-inputs`, `check-destination` y `validate` son de solo lectura -- portable, exit codes 0/1/2/3 y salida `--json` opcional; no conoce el protocolo de hooks ni lee stdin. |
| `tools/reporting/profiles/eda.py` | Profile EDA sobre el core de reporting (v0.6 Change 2) -- catálogo de bloques, declaración de aplicabilidad en `Report.metadata["eda"]`, autoderivación estructural y validador `EDA-*` que devuelve `dsguard.checks.CheckResult`; importa `reporting.core` y `dsguard.checks` (dirección permitida por la regla 6), pero no `governance`, pandas ni backends gráficos; verifica estructura y aplicabilidad explícita, no adecuación metodológica; solo lectura y determinista, es core, no conoce protocolo de hooks. |
| `tools/reporting/examples/eda_generic.py` | Ejemplo genérico de reporte EDA (v0.6 Change 2) -- datos 100% sintéticos con `random.Random(RANDOM_STATE)` y estadísticas con stdlib; construye un `Report` con el profile `eda` que pasa `validate_eda_report` sin FAIL y es determinista; sin pandas, sin datos reales, es core. |
| `tools/reporting/evidence.py` | Evidencia de reportes (v0.6 Change 3) -- descripción de fuentes con hash, construcción del manifest, escritura atómica y lectura del directorio de reporte, e índice de artefactos exploratory para el aislamiento por hash (`REPORT-ISOLATION-HASH`); importa `reporting.governance`, `dsguard` (dirección permitida por la regla 6) y, de `ds_profile`, SOLO `fingerprint`; no decide permisos de escritura (eso es del guard de governance/publish), no conoce protocolo de hooks ni lee stdin, es core. |
| `tools/reporting/validation.py` | Validador de reportes (v0.6 Change 3) -- reglas de figuras, insights y manifest, y puerta completa `validate_report_dir` sobre un directorio persistido (integridad, fuentes, contenido, governance, aislamiento); importa `reporting.profiles.eda`, `reporting.evidence` y `reporting.governance`, todo resultado es un `dsguard.checks.CheckResult`; solo lectura y determinista, verifica estructura y evidencia, no adecuación metodológica; es core, no conoce protocolo de hooks. |
| `tools/reporting/style.py` | Design system de reportes (v0.6 Change 4) -- contratos `Style`/`VisualStyle`/`EditorialStyle` (dataclasses frozen), `default_style()` genérico, presets de locale como data, overrides opcionales `.harmessi/report-style.json` (esquema estricto, lectura vía `evidence.read_allowed`) y `check_style` (contraste/paleta); importa solo stdlib, `dsguard.checks` y `reporting.evidence` (`read_allowed`, para la carga gobernada de overrides; no importa `reporting.core`), desacoplado del renderer (no importa `render_html` ni `plotly_backend`); es core, no conoce protocolo de hooks. |
| `tools/reporting/plotly_backend.py` | Backend opcional de figuras (v0.6 Change 4) -- `build_figure` arma a mano un dict JSON-puro tipo Plotly desde `FigureSpec` + tabla, sin mutar los artefactos; NO importa `plotly` a nivel de módulo (solo `find_plotly_bundle` intenta un import perezoso para localizar `plotly.js`, sin declarar dependencia); es core, no conoce protocolo de hooks. |
| `tools/reporting/render_html.py` | Renderer HTML (v0.6 Change 4) -- `render_report_html` compone `report.html` con funciones puras sobre stdlib (`html.escape` en todo texto de usuario); determinista (mismo input, mismos bytes) y offline (solo CSS/JS inline); sin pandas ni red; es core, no conoce protocolo de hooks. |
| `tools/reporting/publish.py` | Publicación de reportes (v0.6 Change 4) -- `publish` orquesta governance → validation → evidence → render y escribe el directorio del reporte más `report.html`; importa solo `reporting.*` y `dsguard.*` vía los módulos existentes; única puerta de escritura del reporte completo; es core, no conoce protocolo de hooks. |
| `tools/datacontracts/core.py` | Contratos neutrales de datos (v0.7 Change 0: `DataContract`/`ContractField`/`Constraint`/`BusinessRule`/`ContractVersion`/`CompatibilityPolicy`, serialización determinista y hash de contenido) -- solo stdlib; no observa ni evalúa ningún dato, no importa `ds_profile`, `dsguard` ni ningún hermano; separa estructura (schema), calidad esperada (expectations con severidad declarada) y reglas de negocio (solo declarables, nunca evaluadas); no conoce protocolo de hooks, es core. |
| `tools/datacontracts/validation.py` | Evaluación de `DataContract` contra evidencia real (v0.7 Change 1: `validate_contract`/`validate_contract_against_profile_file`, códigos `CONTRACT-*`, produce `dsguard.checks.CheckResult`) -- importa `dsguard.checks` (dirección permitida por la regla 7) y, de `ds_profile`, SOLO `holdout_guard.verificar_permitido` (nunca `ds_profile.report`, `.column_stats`, `.fingerprint` ni ningún otro símbolo: no observa datos, solo reusa el guard de lectura de holdout); consume `profile.json` como `dict` ya cargado, nunca recalcula estadísticas ni reabre el dataset original; vocabulario `PASS`/`WARN`/`FAIL`/`N/A`, nunca `PASS` por falta de evidencia; no conoce protocolo de hooks, es core. |
| `tools/datacontracts/evolution.py` | Clasificación determinista de compatibilidad entre dos versiones de un `DataContract` (v0.7 Change 4: `classify_contract_change`, códigos `CONTRACT-EVOLUTION-*`, produce `dsguard.checks.CheckResult`) -- importa únicamente `dsguard.checks` y el sibling `tools.datacontracts.core`; sin `policy` todo `status` es `N/A` (clasificado, nunca evaluado), con `policy` mapea `CompatibilityPolicy.COMPAT_ACTIONS`; pura, sin I/O, sin leer `profile.json` ni ningún archivo; único agregado a un paquete de un Change anterior, excepción prevista por el propio Change 0; no conoce protocolo de hooks, es core. |
| `tools/autonomy/core.py` | Contrato neutral de autonomía (v0.8 Change 0) -- modos `autonomous`/`supervised` (por defecto `supervised`); `POLICY_TABLE` + `resolve_action` (clase de acción × modo → ejecutor/aprobación/resultado); catálogos STOP 1-12 y LIMIT; registro único de códigos `AUTONOMY-*`; roles + `ROLE_CAPABILITIES` + `role_responsibilities` (vista derivada) y `narrow_mode`; `ApprovalRef`, `PolicyApproval` y su validación; namespace reservado `policy:` (`is_reserved_policy_namespace`, `validate_human_identity`, `validate_human_approval_entry`); `PreApprovedDecision`/`validate_pre_approved`; `PolicyFinding` y `AutonomyError` -- solo stdlib (`re`, `unicodedata`, `dataclasses`, `typing`); no lee `guardrails.json` ni ningún archivo, no ejecuta nada; no importa `tools.*` ni hermanos; no conoce protocolo de hooks, es core. |
| `tools/autonomy/policy.py` | Política de autonomía humana de `guardrails.json` (v0.8 Change 0) -- `parse_autonomy_policy` (parseo fail-closed; recibe `guard_policy_version_max` del llamador y NO importa `dsguard.pathguard`, cuyo `cargar_config` rechaza versiones no soportadas), `AutonomyPolicy`, `is_source_sealed`/`effective_source_access` (policy ∩ registro), `sealed_coherence_findings` (matcher inyectado, sin leer rutas) y `resolve_methodological_decision` -- solo stdlib acotada; depende únicamente de `core`; puro, sin I/O; sin policy equivale a v0.7 (`supervised`); no conoce protocolo de hooks, es core. |
| `tools/datasources/core.py` | Tipos neutrales de fuentes de datos (v0.8 Change 1: `SourceRef`/`SourceCapabilities`/`ObservationRequest`/`SourceObservation`/`FieldObservation`/`SourceProvenance`/`SourceError`, `CODES` -- registro único de `SOURCE-*`) -- solo stdlib (`dataclasses`, `typing`, `re`, `json`, `hashlib`, `unicodedata`, `__future__`); sin `os`/`pathlib`/`sys`/`importlib`, sin hermanos ni `tools.*`; `source_kind`/`native_type` son etiquetas informativas acotadas por regex que solo se copian/serializan, el módulo NO ramifica sobre tecnología (R3); serialización determinista (`to_dict()` orden fijo, `canonical_json()`, `content_sha256()` excluye `provenance.generated_at`); no conoce protocolo de hooks, es core. |
| `tools/datasources/scan.py` | Escaneo por patrón de secretos y localizadores físicos (v0.8 Change 1: `scan_secrets`/`scan_locators`, R19) -- puro sobre dicts, sin I/O; importa solo stdlib (`re`, `typing`) y `.core` (relativo, para los códigos `SOURCE-SECRET-DETECTED`/`SOURCE-DSN-DETECTED`/`SOURCE-ABSOLUTE-PATH`); best-effort por diseño (no reemplaza a `pathguard`), nunca reproduce el valor sospechoso en el hallazgo; no conoce protocolo de hooks, es core. |
| `tools/datasources/registry.py` | Validación estática y pura del registro `.harmessi/sources.json` (v0.8 Change 1: `validate_registry`, `resolve_observer_file` con `exists_fn` inyectable, `check_registry_static`, R12-R14) -- importa solo stdlib (`re`, `typing`) y `.core`/`.scan` (relativos); `resolve_observer_file` nunca importa el módulo del observer ni toca el sistema de archivos directamente (el I/O real lo inyecta el llamador); no conoce protocolo de hooks, es core. |
| `tools/datasources/runtime.py` | Capa de I/O e `importlib` de `datasources` (v0.8 Change 1: `load_registry`/`check_registry`, `observe_source` con el orden obligatorio de R16, `compare_fingerprint` R26, persistencia atómica en `.harmessi/observations/<observation_id>/observation.json` R23) -- importa stdlib (`os`, `pathlib`, `importlib`, `hashlib`, `json`, `datetime`, `sys`, `typing`) más `dsguard.checks` (vía `sys.path.insert`, mismo patrón que `tools/datacontracts/validation.py`) y los módulos puros propios (`.core`/`.registry`/`.scan`, relativos); **compone `access_check` inyectado como parámetro obligatorio de `observe_source` -- NO importa `tools.autonomy` ni `tools.dsguard.pathguard` directamente** (D8/R25): el control de acceso real lo arma `tools/ds_guard.py`; sin timeout en proceso (R17, límite documentado); no conoce protocolo de hooks, es core. |
| `tools/datasources/profile_bridge.py` | Puente `profile.json` (`ds_profile`) → `SourceObservation` neutral (v0.8 Change 1: `profile_to_observation`, R27) -- puro sobre dicts, sin I/O; importa solo stdlib (`datetime`, `typing`) y `.core` (relativo); NO importa `ds_profile` (ese acoplamiento vive en `file_observer.py`); nunca copia `dataset_path` ni ninguna ruta; devuelve una `SourceProvenance` placeholder que el llamador debe sobrescribir; no conoce protocolo de hooks, es core. |
| `tools/datasources/file_observer.py` | Único observer que Harmessi incluye (v0.8 Change 1: `FileObserver`/`factory`/`factory_with_repo_root`, R28) -- observa archivos locales (CSV/Parquet) vía `ds_profile`; **importa `ds_profile` de forma perezosa, siempre dentro de funciones/métodos, nunca a nivel de módulo** (así el paquete `datasources` puede convivir en stage `discovery` sin forzar `ds_profile` instalado; este archivo mismo se instala en `experiment`, R38); a nivel de módulo importa solo stdlib (`tempfile`, `pathlib`, `typing`) y `.profile_bridge` (relativo); pasa por el guard de holdout (`ds_profile.holdout_guard.verificar_permitido`) antes de leer; la ruta nunca aparece en la observación devuelta; no conoce protocolo de hooks, es core. |
| `tools/fallback/handoff.py` | Contexto de handoff a nivel SDD (v0.5 Change 3) -- contexto mínimo suficiente para continuar un Change entre sesiones/proveedores sin reiniciar trabajo ni duplicar auditorías (`completed`/`pending`/`prior_findings`); persistido en `.harmessi/handoffs/<id>/handoff.json`, mismo patrón que `.harmessi/evals/`. |
| `tools/modelquality/core.py` | Políticas de calidad de modelo neutrales (v0.7 Change 2: `ModelQualityPolicy`/`MetricRequirement`/`EvaluationContext`/`ObservedMetric`/`BaselineReference`, serialización determinista y hash de contenido de `ModelQualityPolicy`) -- solo stdlib; no entrena modelos, no calcula ninguna métrica, no observa ningún dato; familia independiente de `tools/datacontracts`, sin tipos compartidos; no conoce protocolo de hooks, es core. |
| `tools/modelquality/validation.py` | Evaluación de `ModelQualityPolicy` contra métricas ya reportadas (v0.7 Change 2: `evaluate_policy`, códigos `QUALITY-*`, produce `dsguard.checks.CheckResult`) -- importa `dsguard.checks` y `tools.modelquality.core` (sibling); sin ninguna superficie de I/O ni de lectura de archivo; nunca recalcula ni verifica que el valor reportado sea numéricamente correcto (decisión 1 del roadmap); vocabulario `PASS`/`WARN`/`FAIL`/`N/A`, nunca `PASS` por falta de evidencia; no conoce protocolo de hooks, es core. |
| `tools/qualityevidence/core.py` | Tipos neutrales de evidencia de calidad (v0.7 Change 3: `QualityEvidenceManifest`/`DriftEvidence`/`EvidenceSource`/`DeclarationRef`/`ScopeWindow`, serialización determinista y hash de contenido que excluye `generated_at`) -- solo stdlib; no calcula nada desde datos crudos, no observa ningún dataset; familia independiente de `tools.datacontracts`/`tools.modelquality`/`tools.reporting`, sin tipos compartidos; no conoce protocolo de hooks, es core. |
| `tools/leadrun/core.py`, `allowlist.py` | Tipos y allowlist puros del runtime de ejecución del Lead (v0.8 Change 2, `20260929-lead-execution-runtime`) -- `core.py` es solo-stdlib (`hashlib`, `json`, `re`, `dataclasses`, `typing`, `__future__`), sin imports relativos ni de `os`/`pathlib`/`sys`/`subprocess`/`importlib`: declara `ExecutionForm`/`ExecutionRequest`/`ExecutionRecord` y el registro único de códigos `EXEC-*` (`CODES`); `approval` se recibe ya serializado como `dict`/`None` porque este módulo NO importa `tools.autonomy` (excepción de tipo de dato, no de import). `allowlist.py` es puro sobre `str`/`tuple` (importa `os.path` solo para manipulación de strings en memoria -- `normcase`/`normpath` -- nunca para tocar el disco, más `re`/`typing`/`.core`): reconoce la FORMA de un comando (script/pytest/notebook/cli_diagnostic) sin decidir autorización semántica ni consultar `control.json`; no conoce protocolo de hooks, es core. |
| `tools/leadrun/scripts.py`, `notebooks.py`, `runtime.py` | Capa de I/O del runtime de ejecución del Lead (v0.8 Change 2) -- `scripts.py` importa `subprocess`/`time`/`pathlib`/`typing` + `.core` (relativo) y ejecuta vía `subprocess.run(..., capture_output=True, text=True)`, sin volver a evaluar la allowlist. `notebooks.py` compone `tools.nbrunner.{core,fsdiff,manifest}` y `tools.launcher_common` a nivel de módulo, más `.core` (relativo); `tools.nbrunner.execute` (que importa `nbformat`/`nbclient` a nivel de módulo) se importa de forma PEREZOSA, solo dentro de `ejecutar_manifest`, mismo criterio que `ds_profile` en `tools/datasources/file_observer.py` (regla 11). `runtime.py` es el único módulo del paquete que produce y persiste un `ExecutionRecord` (`.harmessi/executions/<id>/record.json`, escritura atómica); importa `dsguard.checks`/`datasources.scan` (vía `sys.path.insert`, mismo patrón que `tools/datasources/runtime.py`) y `.allowlist`/`.core`/`.notebooks`/`.scripts` (relativos), pero **no importa `tools.autonomy` ni `tools.dsguard.pathguard`**: esa composición de aprobación vive en `tools/ds_guard.py` (mismo patrón que la regla 11 para `access_check`); no conoce protocolo de hooks, es core. |
| `tools/qualityevidence/evidence.py` | Persistencia de evidencia de calidad y cómputo de drift (v0.7 Change 3: construcción/escritura atómica/lectura verificada de `QualityEvidenceManifest` bajo `.harmessi/quality/`, `build_drift_evidence`/`drift_from_profiles` con `DRIFT_COMPARISON_MODES` acotado a diferencia absoluta/relativa, `resolve_evidence_ref` como convención opcional sobre `ObservedMetric.evidence_ref`/`BaselineReference.evidence_ref` de Change 2, sin modificarlo) -- importa `dsguard.checks` y `ds_profile.holdout_guard.verificar_permitido` (único símbolo); reimplementa localmente hash sha256 chunked/JSON canónico/escritura atómica (mismo criterio que `tools/dsguard/mlops_evidence.py`); nunca lee un `profile.json` sin el guard; nunca `PASS`/`FAIL` de drift sin threshold declarado (`N/A` "evidencia registrada sin veredicto"); no conoce protocolo de hooks, es core. |

Las 4 implementaciones concretas del contrato de `tools/providers/core.py` —
`tools/providers/claude_code.py`, `codex.py`, `gemini.py`, `grok.py` (v0.5 Change 0) — no están
listadas en la tabla de arriba: cada una sí conoce el vocabulario de flags y el formato de salida
de la CLI de un proveedor específico (`claude`, `codex`, `gemini`, `grok`), así que son la capa fina
que traduce ese conocimiento específico hacia/desde el contrato neutral de `core.py` — misma lógica
de separación que el resto de este documento, aplicada a un invocador nuevo en vez de a un hook de
Claude Code.

### 2.2 Adapter (protocolo `PreToolUse` de Claude Code)

| Módulo | Rol | ¿Separa lógica de decisión del I/O de stdin? |
|---|---|---|
| `tools/dsguard/hook_rutas.py` | Hook de pathguard | **Sí** — delega en `pathguard.evaluar_tool_call(payload, ...)` |
| `tools/dsguard/hook_launcher_rutas.py` | Lanzador del anterior | N/A (solo resuelve intérprete/venv) |
| `tools/dsguard/hook_presupuesto.py` | Hook de presupuesto de sesión | **No** — la lógica de decisión (allowlist, ventanas de minutos, denegación) vive en el mismo archivo que lee stdin |
| `tools/dsguard/hook_launcher_presupuesto.py` | Lanzador del anterior | N/A |
| `tools/nbrunner/hook_validar_comando.py` | Hook del agente notebook-runner | **No** — mismo patrón que `hook_presupuesto.py`: regex/validación de comando inline |
| `tools/nbrunner/hook_launcher.py` | Lanzador del anterior | N/A — delega en `launcher_common.lanzar_hook` |

### 2.3 Caso especial: `pathguard.py` (core con contrato de datos con forma de adapter)

`tools/dsguard/pathguard.py` no lee `stdin`, no conoce exit codes — en ese sentido es core. Pero su
función pública `evaluar_tool_call(payload: dict, config, repo_root)` espera que `payload` tenga
exactamente la forma del JSON de un evento `PreToolUse` de Claude Code (`tool_name`, `tool_input`,
`agent_type`). Un futuro adapter para otro proveedor tendría que construir un `payload` con ESA
forma específica para reusar `pathguard`, en vez de que `pathguard` acepte una forma neutral propia.
Es la pieza de core más cercana a estar lista para un adapter nuevo, pero no está desacoplada del
todo — ver deuda §4.

**Segundo caso análogo: `tools/launcher_common.py`.** Tres de sus cuatro funciones públicas
(`resolver_venv_dir`, `ruta_interprete_venv`, `resolver_repo_root`) son utilidades neutras —
`tools/harmessi/doctor.py` (core, un diagnóstico de venv) las importa directamente, sin que eso
implique conocer el protocolo de hooks. La cuarta, `lanzar_hook`, sí lee
`os.environ["CLAUDE_PROJECT_DIR"]` (variable que solo existe porque Claude Code la define al invocar
un hook) y por lo tanto es genuinamente adapter — pero vive en el mismo archivo que las tres
neutras. Los tres lanzadores reales (`hook_launcher_rutas.py`, `hook_launcher_presupuesto.py`,
`nbrunner/hook_launcher.py`) son los que llaman a `lanzar_hook`; son ellos, no `launcher_common.py`
en sí, los adapters "de punta a punta". Clasificar `launcher_common.py` como core en el inventario
de §2.1 (con esta nota) es más honesto que forzarlo a una de las dos categorías — es exactamente el
mismo patrón de "archivo mixto sin separar" que la deuda #1 de §4, solo que acá la mayoría del
archivo es neutral y una función es adapter, al revés que `hook_presupuesto.py`.

## 3. Reglas de dependencia

1. Core nunca importa un módulo `adapter` (§2.2), ni conoce `sys.stdin`/exit-code-como-decisión.
2. Un adapter puede importar cualquier módulo core.
3. Dirección ya establecida entre paquetes core: `ds_profile -> dsguard`, `dsimpact -> dsguard`
   (nunca al revés — `dsguard` es el core más básico, instalado siempre desde `discovery`;
   `ds_profile`/`dsimpact` son opcionales por stage).
4. `dsguard` nunca importa `ds_profile` ni `dsimpact` (documentado explícitamente ya en Change 1/2
   para evitar romper instalaciones en `discovery`, donde esos paquetes opcionales pueden no
   existir).
5. Dirección de dependencia entre los paquetes nuevos de v0.5 (`tools/providers`,
   `tools/harmessi_bench`, `tools/routing`, `tools/fallback`): `harmessi_bench` → `providers` (vía
   `runner.py`, no desde `core.py`); `fallback` → `providers` (vía `core.py`); `routing` y
   `fallback` nunca importan `harmessi_bench` (separación decidir/reintentar vs medir calidad, ver
   `design.md` de Change 3); ningún paquete nuevo de v0.5 importa `dsguard`/`ds_profile`/`dsimpact`
   ni viceversa (familias independientes). Verificado por
   `tools/tests/test_v05_core_neutrality.py`.
6. Familia `tools/reporting` (v0.6): `core.py` es solo-stdlib y no importa hermanos; los módulos
   posteriores de la familia (`governance.py` ya importa `dsguard`; evidencia, perfiles y renderer
   podrán importar `dsguard`; hacia `ds_profile` la dependencia de `reporting` es SOLO `ds_profile.fingerprint`, usada por `evidence.py`),
   pero nunca al revés: `dsguard`, `ds_profile`, `dsimpact`, `providers`,
   `routing`, `fallback` y `harmessi_bench` no importan `reporting`. Verificado por
   `tools/tests/test_v06_core_neutrality.py`.
   Dirección de dependencias del Change 4: `style`, `plotly_backend`, `render_html` y `publish`
   dependen del core, `governance`, `evidence` y `validation` (`style` solo de `dsguard.checks` y
   `evidence`, para la carga gobernada de overrides); el core (`core.py`,
   `governance.py`, `evidence.py`, `validation.py`, `profiles/`) NO conoce style, render ni
   backend. `report.html` es un artefacto derivado y reproducible, fuera del manifest (su
   integridad se verifica re-renderizando con `render --check`); el escape de todo texto de
   usuario ocurre en `render_html`, nunca en el core.
7. Familia `tools/datacontracts` (v0.7): `core.py` es solo-stdlib y no importa hermanos ni
   ningún paquete existente. En Changes posteriores (no en Change 0, que no produce
   `CheckResult`), los módulos de la familia podrán importar `dsguard.checks` (para producir
   resultados `PASS`/`WARN`/`FAIL`/`N/A`) y leer `profile.json` de `ds_profile` como archivo
   persistido (nunca importar `ds_profile` como librería para observar datos, salvo una
   extensión aditiva de `ds_profile` decidida explícitamente en SDD, ver decisión 2 de
   `docs/roadmap/v0.7.md`); pero nunca al revés: `dsguard`, `ds_profile`, `dsimpact`,
   `reporting`, `providers`, `routing`, `fallback` y `harmessi_bench` no importan
   `tools/datacontracts`. Verificado por `tools/tests/test_v07_core_neutrality.py`.

   Change 1 (`data-contract-validation`) ejercita esta cláusula de extensión aditiva de forma
   concreta y acotada: `tools/datacontracts/validation.py` importa únicamente
   `ds_profile.holdout_guard.verificar_permitido` (un solo símbolo, de un solo módulo, que decide
   permiso de lectura de una ruta -- no observa ni agrega datos) para no replicar la lógica de
   guard de holdout, siguiendo la instrucción explícita del roadmap ("se reutiliza el guard
   existente, no se replica"). No importa ningún otro símbolo de `ds_profile` (`report`,
   `column_stats`, `fingerprint`, `sampling`, `quality_flags`, `schema`, `io_readers` quedan
   fuera). Verificado por `tools/tests/test_v07_validation_neutrality.py`.

   Change 4 (`quality-integration-and-cli`) agrega la única extensión aditiva dentro del propio
   paquete: `tools/datacontracts/evolution.py` importa únicamente `dsguard.checks` y el sibling
   `tools.datacontracts.core` (nunca `ds_profile`, `dsimpact`, `tools.modelquality`,
   `tools.qualityevidence`, `tools.reporting`, pandas ni numpy) -- pura, sin I/O, sin leer
   `profile.json` ni ningún archivo (a diferencia de `validation.py`, que sí lee evidencia). Los 6
   subcomandos `contract`/`quality` de ese mismo Change viven en `tools/ds_guard.py` (adapter
   top-level, fuera de esta familia y fuera del perímetro de neutralidad v0.7), que compone
   `tools.datacontracts.{core,validation,evolution}` junto con `tools.modelquality`,
   `tools.qualityevidence` y `tools.dsimpact` -- nunca al revés, y ningún paquete de esta lista
   importa a otro directamente entre sí. Verificado por
   `tools/tests/test_v07_evolution_neutrality.py`.

8. Familia `tools/modelquality` (v0.7 Change 2): `core.py` es solo-stdlib y no importa hermanos
   ni ningún paquete existente, incluido `tools.datacontracts` (familia independiente, sin tipos
   compartidos: ver `design.md` del Change). `validation.py` importa `dsguard.checks` (para
   producir `CheckResult`) y `tools.modelquality.core` (sibling); no importa `ds_profile` ni
   `tools.datacontracts` en ninguna dirección, ni ningún otro paquete de `tools/` -- no tiene
   ninguna superficie de I/O ni de lectura de archivo en este Change (a diferencia de
   `tools/datacontracts/validation.py`, que sí lee `profile.json`): `ObservedMetric`/
   `BaselineReference` se reciben siempre como objetos ya construidos en memoria. Nunca al revés:
   `dsguard`, `ds_profile`, `dsimpact`, `reporting`, `tools.datacontracts`, `providers`, `routing`,
   `fallback` y `harmessi_bench` no importan `tools/modelquality`. Verificado por
   `tools/tests/test_v07_modelquality_neutrality.py`.

9. Familia `tools/qualityevidence` (v0.7 Change 3): `core.py` es solo-stdlib y no importa
   hermanos ni ningún paquete existente (ni `tools.datacontracts`, ni `tools.modelquality`, ni
   `tools.reporting`: ver `design.md` del Change, decisiones 1-2). `evidence.py` importa
   `dsguard.checks` (para envolver `list[CheckResult]` ya producidos por el llamador) y
   `ds_profile.holdout_guard.verificar_permitido` (único símbolo, mismo criterio que la regla 7
   aplicó a `tools/datacontracts/validation.py`, para leer `profile.json` en `DriftEvidence`);
   reimplementa localmente sus propias primitivas de hash sha256 chunked, JSON canónico y
   escritura atómica (mismo criterio que `tools/dsguard/mlops_evidence.py`, sin importar
   `ds_profile.fingerprint` ni `tools.reporting.evidence`). `tools.qualityevidence` NO importa
   `tools.datacontracts` ni `tools.modelquality` en ninguna dirección (el llamador extrae
   `contract_id`/`policy_id`/`version`/`content_sha256()` como valores planos antes de invocar
   `evidence.py`) y NO importa `tools.reporting` en ninguna dirección (la integración con
   Reporting v0.6 ocurre exclusivamente porque `reporting.evidence.describe_source` puede hashear
   cualquier archivo del repo, incluido un manifest de `qualityevidence`, sin que ninguno de los
   dos paquetes importe al otro). Nunca al revés: `dsguard`, `ds_profile`, `dsimpact`, `reporting`,
   `tools.datacontracts`, `tools.modelquality`, `providers`, `routing`, `fallback` y
   `harmessi_bench` no importan `tools.qualityevidence`. Verificado por
   `tools/tests/test_v07_qualityevidence_neutrality.py`.
10. Familia `tools/autonomy` (v0.8): `core.py` es solo-stdlib (`dataclasses`, `typing`, `re`,
   `unicodedata`) y no importa `tools.*` ni hermanos; `policy.py` importa solo stdlib acotada
   (`dataclasses`, `typing`, `types`, `re`, `collections.abc`) y `from . import core`. Ninguno de los
   dos usa `json`, `os`, `pathlib` ni `sys`, ni importa `dsguard.pathguard`: `policy.py` recibe
   `guard_policy_version_max` del llamador, y `pathguard.cargar_config` rechaza (fail-closed) una
   `version` de `guardrails.json` no soportada. Nunca al revés: `dsguard`, `ds_profile`, `dsimpact`,
   `reporting`, `providers`, `routing`, `fallback`, `harmessi_bench`, `tools.datacontracts`,
   `tools.modelquality` y `tools.qualityevidence` no importan `tools.autonomy`.

   **Excepción documentada (v0.8 Change 3, `20260930-autonomous-sdd-and-remediation`):**
   `tools/dsguard/sdd.py` importa `autonomy.core` (bare) para reutilizar `PreApprovedDecision`/
   `validate_pre_approved` al implementar checkpoints de negocio (`decision_type=
   "business_checkpoint"`, R3 de ese Change) -- el propio docstring de Change 0 en
   `tools/autonomy/core.py` ya anticipaba este consumidor ("Este modulo NO consulta control.json ni
   ningun archivo (eso es del Change 3)"). Es la única excepción a la regla anterior: ningún otro
   archivo de `tools/dsguard` ni de ningún otro paquete listado la importa. Verificado por
   `tools/tests/test_v08_autonomy_neutrality.py`.
11. Familia `tools/datasources` (v0.8 Change 1, `20260928-source-neutral-data-access`): `core.py`
   es solo-stdlib (`dataclasses`, `typing`, `re`, `json`, `hashlib`, `unicodedata`) y no importa
   hermanos ni `tools.*`; `scan.py`/`registry.py`/`profile_bridge.py` son puros sobre dicts (sin
   I/O) e importan solo stdlib acotada más `.core` (relativo; `registry.py` también `.scan`);
   `runtime.py` hace I/O e `importlib`, importa `dsguard.checks` (vía `sys.path.insert`, mismo
   patrón que la regla 7) y los módulos puros propios, pero **no importa `tools.autonomy` ni
   `tools.dsguard.pathguard`**: el control de acceso real (`access_check`) lo compone
   `tools/ds_guard.py` y se inyecta como parámetro obligatorio de `observe_source` (D8/R25);
   `file_observer.py` importa `ds_profile` de forma perezosa (dentro de funciones, nunca a nivel
   de módulo), único observer incluido por Harmessi. Nunca al revés: `dsguard`, `ds_profile`,
   `dsimpact`, `reporting`, `providers`, `routing`, `fallback`, `harmessi_bench`,
   `tools.autonomy`, `tools.modelquality` y `tools.qualityevidence` no importan `tools.datasources`.

   **Excepción documentada:** `tools/datacontracts/validation.py` (y `legacy_wording.py` si lo
   necesitara) importa `datasources.core`/`datasources.profile_bridge` -- es la única excepción a
   la regla anterior, y ejercita la extensión aditiva ya prevista por la regla 7: "un único motor
   de validación de contratos" que evalúa sobre `SourceObservation` (M1 del roadmap de v0.8,
   `docs/roadmap/v0.8.md`: "Un único motor de validación de contratos... `datacontracts.validation`
   evalúa sobre `SourceObservation`; `validate_contract` y las APIs de v0.7 son wrappers con
   paridad exacta"). Nada más en `tools/datacontracts` importa `datasources`. Verificado por
   `tools/tests/test_v08_datasources_neutrality.py` y `tools/tests/test_v08_source_id_parity.py`
   (paridad exacta del literal `SOURCE_ID_PATTERN`, duplicado a propósito entre `datasources.core`
   y `autonomy.core`, paquetes independientes).

12. Familia `tools/leadrun` (v0.8 Change 2, `20260929-lead-execution-runtime`): `core.py` es
   solo-stdlib (`hashlib`, `json`, `re`, `dataclasses`, `typing`) y no importa hermanos ni
   `tools.*`, sin imports relativos ni de `os`/`pathlib`/`sys`/`subprocess`/`importlib`;
   `allowlist.py` es puro sobre `str`/`tuple` (`os.path` solo para manipulación de strings en
   memoria, `re`, `typing`, `.core` relativo); `scripts.py` hace I/O (`subprocess`, `time`,
   `pathlib`, `typing`, `.core`); `notebooks.py` compone `tools.nbrunner.{core,fsdiff,manifest}` y
   `tools.launcher_common` a nivel de módulo más `.core` (relativo), con `tools.nbrunner.execute`
   importado de forma perezosa solo dentro de `ejecutar_manifest` (mismo criterio que `ds_profile`
   en la regla 11); `runtime.py` importa `dsguard.checks`/`datasources.scan` (vía
   `sys.path.insert`) y `.allowlist`/`.core`/`.notebooks`/`.scripts` (relativos), pero **no
   importa `tools.autonomy` ni `tools.dsguard.pathguard`**: esa composición de aprobación vive en
   `tools/ds_guard.py`, en imports perezosos dentro de funciones (`_importar_perezoso`/
   `_leadrun_modulos()`, mismo patrón ya usado para `datasources`/`autonomy`/`qualityevidence`/
   etc.), así que tampoco cuenta como import de `leadrun` a nivel de módulo de `ds_guard.py`.
   `tools/notebook_runner.py` importa `dsguard.core`/`dsguard.repo` más `tools.leadrun.notebooks`
   (único import calificado `tools.*` de todo el paquete). A diferencia de la regla 11
   (`tools/datasources`), acá la dirección es completamente asimétrica y **sin ninguna excepción
   documentada**: `tools/leadrun` importa de `nbrunner`/`dsguard`/`datasources`, pero ningún
   paquete (`dsguard`, `ds_profile`, `dsimpact`, `reporting`, `providers`, `routing`, `fallback`,
   `harmessi_bench`, `autonomy`, `modelquality`, `qualityevidence`, `datasources`,
   `datacontracts`, `nbrunner`) importa `tools.leadrun`/`leadrun`, ni siquiera `ds_guard.py` a
   nivel de módulo. Verificado por `tools/tests/test_v08_leadrun_neutrality.py`.

13. Familia `tools/cards` (v0.9 Change 0, `20261002-card-and-evidence-foundation`): `core.py` es solo-stdlib y no importa
    `tools.*` ni hermanos; `assess.py` importa solo `core` y, de forma perezosa dentro de una función,
    `dsguard.checks`. Ningún paquete existente importa `cards` y `cards` no importa `autonomy`,
    `datasources`, `qualityevidence`, `modelquality`, `datacontracts`, `leadrun`, `reporting` ni
    `ds_init`: las referencias a evidencia son punteros (`kind` + `ref_id` + `content_sha256`) y su
    resolución se inyecta. Los helpers (`canonical_json`, `content_sha256`, patrón de ids, reglas de
    identidad humana, forma de `ApprovalRef`) se duplican a propósito, con tests de paridad. Change 1 (`20261002-data-cards`) agrega `datacard.py` (Data Card = `CardEnvelope` con
    `card_kind=data_card` y body cerrado; `assess` y `resolvers` son los únicos hermanos permitidos) y
    `resolvers.py` (resolvers stdlib que releen `.harmessi/observations|quality` y archivos de contrato y
    recomputan hashes con paridad testeada contra `datasources`/`datacontracts`/`qualityevidence`, sin
    importarlos). Las Cards viven en `governance/cards/data/<card_id>.json`, project-owned y fuera del
    manifest. Change 2 (`20261005-model-cards`) agrega `modelcard.py` (Model Card = `CardEnvelope` con `card_kind=model_card`;
    identidad `card_id = model_id__<model_version con '.'→'_'>`, una Card por versión de modelo) y amplía
    `resolvers.py` con resolvers para `data_card`, `model_quality_result`, `model_quality_policy`,
    `observed_metric`, `baseline_reference`, `drift_evidence` y `execution_record` (pin exacto, sin «latest»;
    `member` semántico para entradas de métricas/baselines). Las Model Cards viven en
    `governance/cards/model/<card_id>.json`.
    Change 3 (`20261005-model-risk-responsible-ai`) agrega `govpolicy.py` (policy de governance como datos:
    niveles `low/medium/high`, seis dimensiones, orden de fuerza único, policy base `harmessi-base` v1 con hash
    congelado y merge monotónico fail-closed de endurecimientos) y `modelgov.py` (`ModelGovernanceAssessment`:
    `card_kind=governance_assessment`, una evaluación por Model Card concreta, `risk_level` declarado por
    atestación, completitud `governance_completeness` derivada con regla «todos los soportes aceptables y
    frescos»). Vive en `governance/model-risk/<card_id>.json`. `complete` significa que los requisitos de la
    policy están satisfechos; no equivale a aprobación ética, de justicia, seguridad ni cumplimiento.
    La Foundation suma los kinds observados `model_card`, `governance_policy` y `evidence_document`
    (este último acredita existencia e integridad de un documento, no su contenido).
    No está en
    el manifest administrado hasta Change 4. Verificado por `tools/tests/test_v09_cards_neutrality.py`,
    `test_v09_cards_parity.py` y `test_v09_cards_inert.py`.

Estas reglas ya se cumplen hoy (verificado, ver `tools/tests/test_architecture_boundaries.py`,
Change 3) — este documento las hace explícitas, no las introduce de cero.

## 4. Deuda registrada (no resuelta en este Change)

1. **`hook_presupuesto.py` y `hook_validar_comando.py` no separan lógica de decisión del I/O de
   stdin**, a diferencia de `pathguard.py`/`hook_rutas.py`. Extraer esa lógica a un módulo core
   (p. ej. `dsguard/presupuesto.py`, `nbrunner/validar_comando.py`) con una función pura
   `evaluar(payload: dict, ...) -> (permitido, motivo)`, dejando el hook como adapter fino, es
   trabajo real de refactor — no se hace en este Change (riesgo de romper el contrato de hooks de
   instalaciones existentes si se hace mal). Candidato concreto para el change de reestructuración
   física futuro.
2. **`pathguard.evaluar_tool_call` acopla su contrato de datos a la forma exacta del JSON de
   `PreToolUse`** (`tool_name`/`tool_input`/`agent_type`) en vez de una forma neutral propia. Un
   adapter para otro proveedor de IA necesitaría reconstruir esa forma exacta, no una interfaz
   neutral de Harmessi. Se documenta como el punto de entrada más probable para diseñar el contrato
   neutral cuando se aborde multi-provider real (fuera de alcance de v0.4).
3. **`tools/ds_guard.py` importa todo `dsguard.*` a nivel de módulo, siempre**, sin importar qué
   subcomando se invoque. No es un blocker de portabilidad (son módulos livianos, sin dependencias
   pesadas) pero es carga innecesaria en cada invocación de CLI. Candidato de limpieza de bajo
   riesgo para un change futuro (imports perezosos por subcomando), no urgente.
4. **`tools/ds_init/*` instala contenido pensado específicamente para Claude Code** (`.claude/`,
   agentes, skills) aunque su propia lógica de instalación sea neutral. Preparar un instalador
   multi-target (otro adapter que instale un layout distinto) es trabajo de un change futuro de
   multi-provider, no de v0.4.

5. **`tools/launcher_common.py` mezcla utilidades neutras (`resolver_venv_dir`,
   `ruta_interprete_venv`, `resolver_repo_root`) con una función adapter (`lanzar_hook`, que lee
   `CLAUDE_PROJECT_DIR`)** en el mismo archivo (ver §2.3). Separar `lanzar_hook` a un módulo adapter
   dedicado (o a cada lanzador) es trabajo del mismo change de reestructuración física que el punto
   1 — no se hace acá.

Ninguno de estos 5 puntos se resuelve en Change 3 — quedan como deuda explícita para cuando exista
una necesidad real de un adapter nuevo (fuera de alcance de v0.4, ver `docs/roadmap/v0.5.md` y
posteriores).

### 4.1 Deuda registrada de v0.6 (no implementada)

Declarada tras el hardening de v0.6; ninguno de estos puntos se resuelve en v0.6:

1. **Registro de profiles**: `validation.py` importa `profiles.eda` de forma directa; un profile
   nuevo exige tocar `validation`. Falta un registro/lookup por nombre de profile.
2. **Enforcement de lectura vía hook**: ver §5 (hueco de aislamiento exploratory↔model_valid).
3. **Verificación con `plotly.js` real**: verificado en el hardening de v0.6 (Edge/Chrome 153,
   plotly.js v4.1.1, incluido `Plotly.react` en `beforeprint` real). Persiste solo la
   verificación en otros navegadores/SO y con otras versiones de plotly.js; `render --check`
   depende del bundle disponible en ese momento (proyecto o plotly instalado), no del que usó
   `publish`.
4. **Subcomando `publish` en el CLI**: hoy `publish` es solo API Python.
5. **`sys.path.insert` y estilo de imports**: los módulos de `reporting` usan
   `sys.path.insert(0, tools_dir)` + `from dsguard import ...` (identidad dual de módulo frente a
   `tools.dsguard`); unificar el estilo de imports del paquete es trabajo futuro.
6. **Registro único de códigos/constantes**: hay constantes duplicadas (p. ej.
   `REPORT-RENDER-PLOTLY-UNAVAILABLE`, `REPORT-STYLE-INVALID` en `cli.py` y `publish.py`;
   `report.html` en `cli.py` y `core.REPORT_FILENAME`); hoy solo un test afirma su igualdad.
7. **Carga de archivos en `style.py`**: separar la carga/lectura gobernada de overrides de los
   dataclasses puros del design system.
8. **Textos en español del profile EDA** (`_RAZON_SIN_TARGET`, preguntas de `BLOCK_CATALOG`,
   `_RAZONES_TRIVIALES`) frente al tema por defecto `en`: mover a data por locale.
9. **Alcance acotado de los tests de neutralidad**: `PAQUETES_SIN_REPORTING` omite `tools/ds_init`,
   `tools/nbrunner` y los `tools/*.py` de nivel superior.
10. **README** sin documentar `python -m tools.reporting`.
11. **`.gitattributes -text` para `reports/**`**: con `core.autocrlf` los bytes de los artefactos
    pueden cambiar y romper los hashes del manifest.
12. **Ancla externa del hash del manifest**: el manifest se autodescribe; un atacante con escritura
    puede regenerarlo coherente. Falta un ancla externa (p. ej. hash registrado fuera del directorio).

## 5. Límites del aislamiento exploratory↔model_valid (v0.6)

El aislamiento es mecánico en `publish`, `validate` y `check-inputs`/`check-destination`:
escritura controlada por destino de scope; lectura controlada por path, por manifest ancestro y
por hash de una copia byte-idéntica de un artefacto exploratory.

Límite real: un notebook o script de modelado que LEA `reports/exploratory/**` sin declarar sus
inputs al binario NO es interceptado. El hook de `pathguard` no puede llamar a `reporting`
(`dsguard` no importa `reporting`, regla 6). Cerrar ese hueco (p. ej. una regla de guardrails/hook
para agentes de modelado) es deuda de v0.7+.

## 6. Dirección arquitectónica planificada para v0.8 (NO implementada)

Esta sección describe una dirección **futura** (`docs/roadmap/v0.8.md`, alcance congelado; las
decisiones materiales M1-M6 fueron confirmadas por el autor). Nada de lo descrito acá existe todavía
en el código; al implementarse, el inventario pasa a §2 y las reglas a §3.

**Deuda que motiva la sección.** Hoy el único observador de datos, `tools/ds_profile`, está atado a
archivos (`io_readers` solo CSV/Parquet, entrada por ruta, `profile.json` con `dataset_path`), y la
validación de contratos (`tools/datacontracts/validation.py`) consume la forma exacta de
`profile.json`. El guard de holdouts (`pathguard`/`guardrails.json`) es por ruta. No hay capa entre
"dónde está el dato" y "qué observó Harmessi".

**Capas previstas:**

```
fuente real  →  extensión del proyecto (adapter)  →  SourceObservation (neutral)  →  Harmessi
                                                     (contratos / governance / evidence / reporting)
```

- El core operará solo sobre una observación neutral (solo-stdlib, sin paths, SQL ni DataFrames) y no
  ramificará por CSV, Parquet, SQL, warehouse, API ni proveedor cloud.
- `ds_profile` y `profile.json` v1 no cambian; se agrega un bridge `profile.json → SourceObservation`
  que encapsula el vocabulario de tipos de `ds_profile` (M1).
- **Un único motor de validación de contratos (M1):** `datacontracts.validation` evalúa sobre
  `SourceObservation`; `validate_contract` y las APIs de v0.7 son wrappers con paridad exacta de
  resultados y códigos `CONTRACT-*`. El evaluador nativo no lee archivos; el wrapper conserva las
  verificaciones de acceso/holdout.
- **Extensión (M6):** los adapters, sus dependencias y las credenciales son del proyecto. Se
  registran en un archivo de proyecto **no administrado** y versionado en git, sin secretos, que
  apunta a un `módulo:callable` resuelto por `importlib` y ejecutado en proceso en el `.venv` del
  proyecto; por eso no entran en el cálculo de drift de `harmessi doctor`. Un error del adapter es
  `technical_error`; el hash de su código forma parte de la procedencia; Doctor valida el registro
  de forma estática y no importa código del proyecto. Un adapter por comando externo/stdout queda
  compatible pero fuera de v0.8.
- **Policy humana (M2):** `.claude/guardrails.json`, extendido de forma aditiva, es el máximo permiso
  posible (modo de autonomía, límites agregados, fuentes selladas por `source_id`, permisos de
  lectura/escritura de fuentes); el registro del proyecto solo puede restringirlo (efectivo =
  policy ∩ registro). Hoy `pathguard.cargar_config` ignora las claves desconocidas y no valida
  `version`; por eso se exige una versión reconocible de la policy y un comportamiento fail-closed
  (un guard/runtime que no entienda una capacidad de seguridad requerida no habilita `autonomous` ni
  gobierna fuentes selladas en silencio), detectado por Doctor, con upgrade previo del guard.
- **Ejecución (M5):** solo las ejecuciones hechas por el runtime gobernado cuentan como evidencia de
  ejecución y de cierre de un Change autónomo; el hook estricto global sobre el Bash del Lead queda
  para v0.10 y reutilizará la misma función pura de evaluación (que vive en core, ver deuda 1 de §4).

**Implementado en Change 1 (`20260928-source-neutral-data-access`).** La regla de dependencias
descrita en el párrafo original de esta sección ya está en vigor como la regla 11 de §3 (paquete
`tools/datasources`, filas en §2.1); la sección completa queda como registro histórico de la
planificación, no como pendiente.

**Implementado en Change 2 (`20260929-lead-execution-runtime`).** La parte de "Ejecución (M5)"
descrita arriba -- runtime gobernado que produce evidencia de ejecución vía `ExecutionRecord`,
allowlist declarativa de forma de comando reutilizable por el futuro hook estricto de v0.10 -- ya
está en vigor como la regla 12 de §3 (paquete `tools/leadrun`, filas en §2.1). El hook estricto
global sobre el Bash del Lead sigue fuera de alcance (queda para v0.10, como ya aclaraba el párrafo
original).

**Enmienda 2026-09-30.** `docs/roadmap/v0.8.md` agregó cuatro decisiones materiales (M7-M10, todas
opt-in/backward-compatible) para Changes 3-5, sin reabrir Changes 0-2: `approval_mode: checkpoints`
(M7, extiende el ciclo de aprobación de Change 3 sin crear una segunda arquitectura de approvals);
project capabilities / instalación capability-aware (M8, extiende `tools/ds_init/manifest.py` y el
modelo `Core → capabilities → assets provisionados`, dimensión distinta de `installation_stage`);
fuentes externas file-backed de solo lectura (M9, extiende el registro de `tools/datasources` de
Change 1 sin modificar `SourceObservation`/`SourceRef`, la ruta absoluta nunca entra a un artefacto
portable); layering de configuración `managed defaults → project config → local overrides →
effective config` (M10, `permiso efectivo = policy humana ∩ project config ∩ local override`,
fail-closed, mismo principio ya en vigor para M2). **M7 ya está implementada** (Change 3,
`20260930-autonomous-sdd-and-remediation`, cerrado -- `tools/dsguard/sdd.py`/`tools/ds_guard.py`,
regla 10 de §3 arriba documenta la excepción real de dependencias que introdujo). **M8-M10 ya están
implementadas** (Change 4, `20260930-project-extension-and-installer-integration` -- ver "Implementado
en Change 4" más abajo).

**Adenda 2026-09-30 (costos residuales).** Dos decisiones materiales más (M11-M12), sin reabrir
Changes 0-2 ni los artefactos aprobados por hash de Change 3 (ya cerrado): pre-aprobación de
dependencias del proyecto (M11 -- extiende `approval_mode: checkpoints` de M7/Change 3 y el STOP ya
existente `new_dependency`, sin modificar `tools/autonomy/core.py`); integridad detectiva de fuentes
externas read-only (M12 -- fingerprint tamaño+`mtime` antes/después de una ejecución gobernada de
Change 2, mapeado al STOP ya existente `data_loss_risk`, sin STOP nuevo ni cambios a
`tools/leadrun/core.py`/`runtime.py`; diagnóstico de permisos OS de solo lectura en `harmessi
doctor`, nunca mutación). **M11-M12 ya están implementadas** (Change 4 -- ver "Implementado en Change
4" más abajo). Dos correcciones puntuales ya aplicadas sobre Change 3 (cerrado) sin reabrir sus
artefactos aprobados: `aggregate_minutes` pasó a ser LIMIT efectivo
(`tools/ds_guard.py::cmd_session_start`, documentado en `openspec/decisions/ledger.jsonl` y en
`verification.md` de ese Change); eficiencia writer→Lead, modelada en la misma adenda.

**Resolución M11 2026-09-30 (aditiva, confirmada por el autor -- implementada en Change 4).**
Auditado: `tools/leadrun/` no tenía ninguna primitiva gobernada de instalación. En vez de dejar M11
como "solo clasificación, sin vía de instalación real", Change 4 agregó una 5ª forma cerrada
`dependency_install` al vocabulario público de Change 2 (`EXECUTION_FORMS`), reutilizando
`scripts.ejecutar_script`/`runtime.ejecutar` de punta a punta (mismo camino que ya usa
`cli_diagnostic`, `code_hash=None`) -- ninguna de las 4 formas/campos/funciones existentes cambió de
comportamiento; verificado por diff dirigido (`tools/tests/test_v08_change4_leadrun_diff.py`): los 4
suites de `tools/leadrun/tests/` pasan sin una sola línea editada. Guardas de contrato: intérprete
`.venv` construido por el runtime, nunca recibido libre (`cmd_dependency_install` resuelve vía
`launcher_common.resolver_venv_dir`/`ruta_interprete_venv`, normalizado con
`leadrun.allowlist.normalizar_interprete`); identidad de paquete validada/canonicalizada (PEP 503,
`sdd.validar_forma_nombre_paquete`/`sdd._canonicalizar_nombre_paquete`), rechazo explícito de
URL/path/VCS/extras/múltiples paquetes; el rango aprobado nunca llega a pip -- solo versión exacta,
verificada contra el rango (`dependencias_efectivas`, compone M10) antes de construir el comando;
evidencia de entorno pre/post vía `importlib.metadata`, sin dependencia nueva; `--no-deps`
obligatorio, transitivas nunca autoinstaladas. El gate de aprobación por-ejecución genérico
(`_resolver_aprobacion_exec`, el mismo que usan `script`/`pytest`/`notebook`) no aplica a esta forma
(`_ejecutar_exec_comun(..., omitir_gate_por_artefacto=True)`): la autorización puntual ya la da la
clasificación (`sdd.clasificar_dependencia`) antes de construir el `ExecutionRequest`, evitando que
`supervised` quede bloqueado siempre por falta de un mecanismo de aprobación-por-artefacto aplicable a
un par nombre/versión (hallazgo real de implementación, corregido). Texto completo: `spec.md` R24-R41
y `design.md` D7-D8 de `openspec/changes/20260930-project-extension-and-installer-integration/`.

**Implementado en Change 4 (`20260930-project-extension-and-installer-integration`).** M8
(`tools/ds_init/manifest.py::capabilities`/`manifest_para_perfil_stage_y_capabilities`, vocabulario
inicial `predictive_modeling` sobre `tools/modelquality/*`); M9 (`tools/datasources/file_observer.py`
gana la opción `ruta_externa_absoluta` inyectada por el llamador, sin import nuevo hacia
`tools.dsguard`/`tools.ds_guard`; `tools/datasources/runtime.py::observe_source` gana
`options_extra`, aditivo, `setdefault` nunca pisa una clave ya declarada por el registro; enforcement
de solo lectura en `tools/dsguard/pathguard.py` -- `leer_fuentes_externas_declaradas` (pública) +
excepción de lectura SOLO para `Read`/`Grep` sobre una ruta externa declarada en
`.harmessi/local-overrides.json`, `Write`/`Edit`/`NotebookEdit` siguen denegados sin cambio de código
sobre cualquier ruta fuera del repo); M10 (`tools/ds_guard.py::resolver_project_config`/
`resolver_local_override`/`resolver_modo_efectivo`, unión-de-restricciones fail-closed sobre
`.harmessi/project-config.json`/`.harmessi/local-overrides.json`, sin tocar `pathguard.py` más allá
del lector puntual de M9); M11 (ver resolución arriba); M12 (fingerprint tamaño+`mtime` compuesto en
`_ejecutar_exec_comun`, evidencia local en `.harmessi/executions/<id>/fingerprints.json`; diagnóstico
de permisos OS en `tools/harmessi/doctor.py::_check_fuentes_externas_permisos_os`, solo lectura;
helper cooperativo de output roots, `resolver_output_roots`/`ds_guard output-roots list`); B5/adopción
(mensaje de colisión enriquecido en `tools/ds_init/cli.py::_imprimir_omitidos`, sin tocar
`planner.py`/`preflight.py`; ownership de 5 vías en `tools/harmessi/doctor.py::_check_ownership_5_vias`,
complementa sin duplicar `_check_archivos_administrados`/`_check_hashes_drift`). Ninguna pieza importa
`tools.autonomy`/`tools.datasources.core`/`tools.leadrun.core`/`tools.leadrun.runtime` de forma nueva
fuera de los puntos ya documentados arriba; cuando este Change cierre, este inventario pasa a §2 y
las reglas a §3, mismo patrón que Change 1/Change 2.

**Vocabulario.** "Adapter" ya tiene dos acepciones en este documento (§2.2: hooks de Claude Code;
`tools/providers`: proveedores de IA). El adapter de fuente sería una tercera; "provider" no debe
usarse para fuentes de datos porque ya lo ocupa `tools/providers`.

**Límite que se mantiene.** Harmessi no sandboxea código del proyecto: gobierna el acceso que media
(adapter declarado, capacidades, fuente sellada por `source_id`, evidencia sin secretos) pero no
intercepta un script que abre su propia conexión. Es el mismo tipo de límite que §5 y que el
enforcement best-effort de `Bash`/`PowerShell`.

### 6.1 Límites agregados de autonomía (Corrective A de v0.9)

`autonomy.budgets` (`aggregate_minutes`, `max_sessions`, `session_minutes`, ...) es la representación canónica y la
única que se documenta; `autonomy.limits` (`max_sessions`, `max_total_minutes`) sigue legible por compatibilidad.
Si ambas existen, el límite efectivo por eje es el MENOR; un valor inválido en cualquiera falla cerrado. Ambos ejes
alcanzan `checkpoint_resumable`/LIMIT (nunca STOP). El alcance de un Change se declara en `proposal.md`
(`## Alcance autorizado`, aprobado por hash); `dir/**` significa el directorio y sus descendientes.
`.harmessi/executions/**` y `openspec/decisions/ledger.jsonl` son outputs internos del harness, no scope funcional.

### 6.2 Checkpoints no circulares, subset PEP 440 y drift semántico de guardrails (Corrective B de v0.9)

- **Checkpoints.** El bullet de `## Checkpoints de negocio` se escribe `aprobacion: <change_id>/proposal.md@approved` (sin el hash del
  propio proposal). Al aprobar `proposal.md`, `ds_guard approve` calcula el hash real una vez y lo materializa en
  `control["decisiones_preaprobadas"]`; `@<64 hex>` legacy sigue aceptándose y 64 ceros se acepta sintácticamente pero NUNCA cuenta como
  aprobado (aviso `deprecated`; `status` lo muestra `placeholder`). La resolución de «aprobación vigente» es UNA primitiva de dsguard
  (`sdd.resolver_aprobacion_registrada`) compartida con `tools/cards/approvals.py`; no hay segundo resolver ni store.
- **Versiones.** `tools/dsguard/pep440_subset.py` implementa un SUBSET documentado de PEP 440 (release, `aN/bN/rcN`, `.postN`, `.devN`, `+local`
  solo en la versión consultada; incluye la exclusión de pre/post-releases de la misma release en `<V`/`>V`) y falla cerrado fuera de él.
  No es PEP 440 completo ni usa `packaging`.
- **Guardrails.** `.claude/guardrails.json` sigue siendo managed/protegido, pero Doctor compara SEMÁNTICAMENTE contra la plantilla
  distribuida ignorando solo la lista cerrada de paths mutables (`version`, `autonomy.mode`, `autonomy.version`, `autonomy.budgets`,
  `autonomy.limits`); cualquier otra clave (holdouts, data_raw, secretos_extra, write_scopes, excepciones, sealed_sources, source_access,
  desconocidas) sigue marcando `HARMESSI-DRIFT`. `HARMESSI-AUTONOMY-CONFIG` valida los valores mutables (mutable ≠ válido).

### 6.3 `ds_profile` con memoria acotada (Corrective C de v0.9)

`ds_profile` decide exacto vs muestreado ANTES de leer filas (`sampling.decidir_plan`): solo metadata (bytes, filas del footer/conteo CSV,
columnas) contra `--max-mb-exactos`, que ahora es el PRESUPUESTO de memoria de trabajo (estimación `filas × columnas × 96 B`; no se confía en
el tamaño comprimido). Exactos en ambos modos por acumuladores O(1): filas, nulos, min/max, media/std, fechas, `dtype`, `binary_numeric`,
`posible_problema_tipo`. `unique`, `top_valores`, `mediana`, `cuantiles`, flags de cardinalidad y `duplicados_fila` son exactos solo dentro
del presupuesto; si no, salen de un reservoir determinista (seed + `version_algoritmo`) con tope por presupuesto y se marcan `muestreada`.
`profile.json.sampling` agrega (aditivo) `motivo`, `filas_observadas`, `version_algoritmo`, `presupuesto_bytes`, `estimado_bytes_exactos`.
Parquet se lee por batches acotados (`BATCH_SIZE`), nunca `read_table`/pandas; fallas de lectura o fuentes demasiado anchas terminan con exit 4
y mensaje accionable. Sin dependencias nuevas.

## 7. Dirección arquitectónica planificada para v0.10 (roles ≠ skills ≠ runtime, NO implementada)

Registrado 2026-10-01 (feedback externo, preservado como línea de evolución -- ver `v0.10.md`,
"Composable Engineering & Data Science Skills", para el desglose completo de candidatas y
principios). **Nada de esta sección (la separación Role/Skill/Runtime y las Composable Skills) está implementado en v0.9.** (actualizado: la foundation de skills componibles y la semántica de writers se implementó en v0.10 Change 4; ver §7.2) Lo que sí existe en v0.9 es
el contrato base de `tools/cards` (identidad, `EvidenceRef`, `HumanAttestation` declared/anchored, evaluación derivada
`invalid > stale > incomplete > complete`), las Data/Model Cards, la governance de modelo y su integración (CLI, Doctor, capabilities, reporting; ver §8).
`anchored` significa estructuralmente coherente
(con `ApprovalRef` válido), no verificado contra `control.json`/ledger; las aprobaciones de Harmessi son
declaraciones humanas registradas bajo el modelo de confianza del harness, no firmas ni prueba de autoría.

Separación conceptual que Harmessi preserva hacia v0.10: **Agent/Role** (quién trabaja y con qué
permisos -- Lead, writer, reviewer, metodólogo, ya estables en §2) ≠ **Skill** (cómo abordar
metodológicamente una clase de problema -- pequeña, componible, seleccionada por el Lead según la
tarea) ≠ **Runtime/Tool** (qué se ejecuta determinísticamente y deja evidencia -- `tools/leadrun/`,
ya implementado). Harmessi no crea un agente nuevo por cada capacidad nueva, ni convierte al Lead en
un mega-agente con toda la metodología embebida.

Principios ya fijados para cuando esto se implemente (no se negocian en el SDD que lo implemente,
solo su alcance/nombres exactos):

- una skill NO obtiene permisos adicionales por existir -- los permisos vienen del rol/runtime
  (regla 1 de §3 sigue aplicando sin excepción);
- una skill NO bypassa STOP, NO instala dependencias por su cuenta (fuera del mecanismo gobernado ya
  existente, regla 10 de §3), NO cambia governance;
- composición de skills observable/trazable cuando afecte un Change (mismo principio que evidence/
  `ExecutionRecord` ya exige para ejecución);
- skills específicas de un proyecto deberían poder existir sin modificar el core de Harmessi (mismo
  principio que M6/adapters de `tools/datasources`, regla 11).

Candidata prioritaria de este catálogo futuro: `domain-modeling` (lenguaje de dominio compartido del
proyecto -- términos, definiciones, unidad de análisis, invariantes, ambigüedades que requieren
decisión humana). Separación obligatoria, ya registrada en `v0.10.md`, para cuando se implemente:
domain model/glossary (qué significa un concepto) ≠ decision ledger (por qué se tomó una decisión,
ya existente, `tools/dsguard/decision.py`) ≠ Data Contract (qué estructura/evidencia esperamos de
los datos, ya existente, `tools/datacontracts/`) -- nunca se mezclan. El domain model es propiedad
del PROYECTO, nunca branding ni conocimiento hardcodeado del harness.

Antes de implementar cualquier skill de este catálogo: auditar qué capacidades ya existen en Lead/
reviewer/metodólogo/SDD/`tools/dsimpact`/tests/remediation -- no duplicar una capacidad ya presente
solo porque tenga otro nombre.

### 7.1 Congelado por Change 0 de v0.10 (aprobado 2026-10-08)

Fijado por `20261008-v010-roadmap-and-architecture-audit`. Es dirección congelada: Implementado por Change 4 salvo lo indicado en §7.2 (re-adopción de guardrails: Change 3; domain-modeling: Change 5).

- **Role vs Skill vs Runtime; contrato de skill.** Una composable skill es un markdown pequeño, versionado, cargado bajo demanda y reusable, sin
  permisos/hooks propios (los permisos vienen del rol/runtime), sin instalar dependencias y sin bypass de STOP/governance. Frontmatter mínimo:
  `name`, `purpose`, `when_to_load`, `roles`, `artifacts`. Sin marketplace; no se crea un runtime de skills nuevo si
  `.claude/skills/lead-data-scientist/*.md` ya soporta la composición.
- **Frontera domain-modeling.** Domain Model (qué significa un concepto) ≠ Decision Ledger (por qué se decidió) ≠ Data Contract (qué
  estructura/evidencia cumple el dato) ≠ Data Card (qué describe un data product concreto); sin duplicar, con referencias por id. El domain model
  vive en `GLOSSARY.md` en la raíz del proyecto: project-owned, versionable en Git, no managed, sin registry/DB y sin evidencia de runtime. Estados
  `hypothesis` | `approved`; `approved` exige aprobación verificable bajo el trust model vigente (sin ella es inválido, fail-closed) y nunca se infiere
  por uso repetido ni por una inferencia del LLM.
- **Frontera trust/authenticity.** `ApprovalRef` sigue siendo «aprobación registrada bajo el trust model». T0 `declared` = declaración registrada
  (`--usuario` es metadata declarada; no demuestra presencia ni identidad). T1 `console_confirmed` = confirmación interactiva desde una consola de
  control soportada: una señal de presencia interactiva, NO prueba de identidad, autoría criptográfica ni non-repudiation. T2 (canal
  separado/restricciones de adapter) es diseño futuro documentado; T3 (PKI/firmas) está fuera de alcance. Todo tier es aditivo y no cambia las Cards.
- **Writer-concurrency.** Un único rol writer, con N instancias solo con ownership de archivos disjunto declarado en `tasks.md` antes de lanzar. El
  Lead coordina y gobierna; no es writer.
- **Re-adopción de guardrails.** Acotada a una closed list; no equivale a «aceptar el baseline actual» ni a ignorar drift. Fuera de la lista sigue
  siendo drift, y los controles de seguridad no se re-adoptan.

### 7.2 Skills componibles y semántica de writers (v0.10 Change 4)

Change `20261014-composable-skills-writer-semantics`. Es la foundation: no existe ninguna skill componible todavía (ni `domain-modeling`,
ni `GLOSSARY.md`, ni `tdd`) y `ml-engineer` no existe.

- **Capas.** Role (quién trabaja y con qué permisos) ≠ Skill (cómo abordar una clase de problema) ≠ Runtime (qué se ejecuta y deja
  evidencia). Una skill no otorga permisos, hooks ni dependencias; los permisos vienen del rol/runtime.
- **Contrato de skill.** Markdown en `.claude/skills/lead-data-scientist/`; plantilla `templates/skill.md`. Frontmatter cerrado
  `name`/`purpose`/`when_to_load`/`roles` más `artifacts` opcional. `tools/dsguard/skill_contract.py` valida la estructura: claves
  prohibidas, roles conocidos, `artifacts` sin comodines; importa `sdd` de forma perezosa. Sin registry. Doctor lo expone como
  `HARMESSI-SKILL-CONTRATO` (WARN, nunca FAIL) y `ds_guard validate` agrega `SKILL-REFERENCIA-DESCONOCIDA`.
- **Ownership de writers.** `## Ownership de writers` en `tasks.md`, validado por `tools/dsguard/ownership.py` y
  `ds_guard ownership check`. Gramática chica: archivo exacto o `dir/**`. Valida ids únicos, rol writer conocido, no vacío, solape
  determinista y ownership ⊆ scope efectivo. El escaneo propio de la sección detecta un encabezado con sufijo y una sección duplicada.
  Un solo rol writer; N instancias solo con ownership disjunto declarado antes de lanzar. El Lead coordina y no es writer.
- **Lifecycle.** `sdd.chequear_estado_divergente` (`SDD-ESTADO-DIVERGENTE`) detecta un `estado:` de `tasks.md` editado a mano que
  difiere del de `control.json`. Integrado en `ds_guard validate`.
- **Continuación vs retry vs ciclo de reviewer.** La continuación reanuda al mismo subagente con la misma tarea y ownership tras
  `ESTADO-AGENTE: continue`; no es una tarea nueva ni un ciclo de revisión. El retry repite una tarea fallida; el ciclo de reviewer es la
  revisión. Cada agente cierra con `ESTADO-AGENTE: completed|continue|blocked|needs-review` y un handoff. `ds_guard session start
  --max-continuaciones N` (1-5, default 1) se muestra en `session status`.
- **Conflicto entre skills (histórico).** En v0.10 dos skills en conflicto se resolvían con «el Lead se detiene y consulta», sin motor de
  prioridades. v0.12 Change 5 reemplaza esa regla (ver §9.4).
- **Sin cambio.** `maxTurns` (12/16/8/4), default `max_continuaciones_por_subagente = 1`, sesión de 90 min wall-clock, hooks,
  pathguard, scope/amendments, trust tiers y hashing managed.
- **Self-governing.** El protocolo de `methodology.md` §31 y las intervenciones de emergencia son contractuales, sin enforcement.
- **Límites honestos.** La validación de ownership es previa a la delegación: no hay hook por instancia ni atribución post-hoc de
  ediciones. H1 (hook: `subagent_type` vs `name`, posible reset del contador) quedó UNCONFIRMED y el hook intacto, por lo que las
  continuaciones son cooperativas. `SDD-ESTADO-DIVERGENTE` detecta ediciones manuales de `estado:`, pero `control.json` no está
  autenticado. Deuda residual de sesión: el literal 90 en tres lugares (canónico en `_BUDGET_DEFAULTS`), sin warning anticipado ni pausa
  por T1. `.ds_init/control.json` se regenera en Change 6.

### 7.3 Domain modeling (v0.10 Change 5)

Change `20261014-domain-modeling`. Primera skill componible metodológica; usa la foundation de §7.2 sin agregar registry ni loader.

- **Skill y artefacto.** `.claude/skills/lead-data-scientist/skills/domain-modeling.md` (roles `lead-data-scientist`, `python-data-engineer`,
  `metodologo`, `data-science-reviewer`; `artifacts: [GLOSSARY.md]`). `GLOSSARY.md` vive en la raíz del proyecto: project-owned,
  Git-versionable, no managed y no creado ni sobrescrito por el installer.
- **Estados.** Cada entrada es `hypothesis` o `approved`. `approved` exige aprobación verificable T1 con `console_confirmed`, reutilizando
  approvals sin tocar `human_presence.py`; sin ella es inválido (fail-closed). Nunca se infiere por uso repetido ni hay promoción por LLM.
- **Ambigüedad material.** Definiciones plausibles alternativas que cambian target, población, unidad de análisis, cutoff, métrica o regla de
  inclusión/exclusión disparan un checkpoint humano. Un sinónimo o wording menor no lo dispara.
- **CLI.** `tools/dsguard/glossary.py` (stdlib; solo importa `.core`; no importa cards, decision, datacontracts ni proveedores) expone
  `ds_guard glossary check` (códigos `GLOSSARY-*`, p. ej. `GLOSSARY-APROBACION-SIN-T1`) y `ds_guard glossary hash`.
- **Separación.** Domain Model (qué significa un concepto) ≠ Decision Ledger (por qué se decidió) ≠ Data Contract (qué estructura/evidencia
  cumple el dato) ≠ Data Card (qué describe un data product). Se referencian por id, sin duplicar.
- **Límites honestos.** T1 es presencia humana, no identidad. El vínculo artefacto↔definición es textual, por hash. `control.json` no está
  autenticado. No hay resolución semántica de sinónimos.

## 8. Dirección arquitectónica planificada para v0.9 (Cards = vistas de governance, NO implementada)

Registrado 2026-10-02 (ver `docs/roadmap/v0.9.md` para el alcance congelado). **Nada de esta sección
existe todavía en el código**; es dirección, no contrato.

Las Data Cards y Model Cards son **vistas de governance estructuradas y respaldadas por evidencia**:
referencian artefactos existentes (v0.7 quality/contracts/drift, v0.8 `SourceObservation`/
`SourceProvenance`/`ExecutionRecord`) y validan completitud, pero no generan evidencia ni cambian la
autonomía. Distinguen evidencia observada/de sistema de `HumanAttestation`, que no satisface requisitos
empíricos. La validación de Cards es un dominio de governance separado de la decisión de
runtime/autonomía (no agrega STOP, no vive en `guardrails.json`).

### 8.1 Integración de Cards al producto (v0.9 Change 4, `20261005-cards-governance-integration`)

- **Capabilities opt-in.** `CAPABILITIES_CONOCIDAS` conserva su semántica histórica (default-on, `predictive_modeling`);
  `data_cards` y `model_governance` viven en `CAPABILITIES_OPT_IN` (default-off, `--enable-capability`).
  `model_governance` exige `predictive_modeling` (validado por `validar_capabilities` en install, sync y Doctor). Con
  flags de capability, `sync` parte del set persistido completo; sin ellos conserva el comportamiento v0.8.
- **Provisioning.** `tools/cards` se distribuye como entradas VERBATIM capability-aware (campo `capabilities_cualquiera`
  para los módulos compartidos); `tools/cards/tests` y `governance/` (project-owned, `EXCLUSIONES_PERMANENTES`) nunca. El
  instalador no crea Cards, assessments ni hardening.
- **Adaptadores** (únicos módulos de `tools/cards` que pueden importar `dsguard`/`reporting`/`ds_init`): `govconfig`
  (configuración efectiva de governance y hardening ACTUAL), `approvals` (resolución real de `ApprovalRef` contra
  `control.json`; prueba una aprobación registrada bajo el trust model, NO identidad criptográfica), `discovery`, `report`.
  La Foundation sigue stdlib-only y recibe el verificador/contexto por parámetro.
- **Superficie:** `ds_guard cards validate|report`, Doctor `HARMESSI-GOV-*` y reporting vía `tools/reporting`
  (`report_kind="governance"`, `decision_scope="exploratory"`). `governance` en `REPORT_KINDS` es solo vocabulario: no
  autoriza lectura de holdout ni equivale a `evaluation`/`model`.
- **Autonomía intacta (D1/D5/D6):** un FAIL de `cards validate` o un ERROR de Doctor no es una decisión de ejecución.

### 8.2 Frontera de hashing managed vs evidence (v0.10 Change 1)

Change `20261008-cross-platform-managed-hashing`. Existe una única primitive para hashes de archivos managed
(`tools/ds_init/managed_hash.py`, stdlib-only, lectura en streaming); no es una abstracción para todos los hashes
del proyecto. Solo la usan `tools/ds_init/` y `tools/harmessi/doctor.py`; cards, datasources, reporting, `ds_profile` y
dsguard no la importan (lo verifica `tools/tests/test_architecture_boundaries.py`).

| Superficie | Contrato de hash |
|---|---|
| Managed texto | `sha256/eol-lf/v1` (bytes; CRLF y CR solitario -> LF; sin tocar BOM ni espacios) |
| Managed binario | `sha256/bin/v1` (bytes exactos) |
| Aprobaciones / ApprovalRef / checkpoints | `sha256/lf/v1` / `hash_lf_v1` (sin cambios) |
| Pins / evidence (Cards, EvidenceRef) | `sha256/bin/v1` (bytes exactos; sin cambios) |
| JSON canónico | lógico (sin cambios) |

- **`hash_alg` por entrada.** Cada entrada de `control.json` lleva `{ruta, sha256, hash_alg}`. Una entrada sin `hash_alg` es
  legacy (hash de bytes crudos). Un `hash_alg` desconocido es `algoritmo_desconocido` y falla cerrado (nunca `ok`).
- **Legacy.** Se verifica sin regenerar aceptando SOLO diferencias de EOL (forma cruda, LF o CRLF); en binarios, solo el hash crudo.
  `migrate-hashes [--execute]` (dry-run por defecto) migra las entradas verificables al algoritmo vigente.
- **Semántica de `sync`.** Reconcilia, NO adopta: clasifica contra el baseline anterior antes de escribir. Pristine o legacy
  verificado se actualiza (journal con backup y rollback) y se rehashea con el algoritmo vigente; drift real conserva archivo y
  entrada tal cual; un archivo existente sin entrada no se adopta salvo que coincida con lo distribuido. `regenerar_control`
  explícito sigue siendo el rebaseline total de mantenimiento. Migración de hash != managed upgrade != re-adopción (Change 3).
- **`.gitattributes`.** Harmessi no lo gestiona ni lo sobrescribe y no forma parte del correctness: funciona con o sin `core.autocrlf`.
- **Límite honesto.** El modo legacy acepta únicamente diferencias de EOL. Un EOL mixto histórico (ni crudo, ni LF, ni CRLF puro)
  no es verificable y se reporta como drift. Un downgrade a un Harmessi anterior puede mostrar falso drift sobre entradas con
  `hash_alg`. El hash que se registra se relee del disco al final de la corrida, así que existe una ventana de segundos entre la
  clasificación del baseline y la escritura/hash en la que una edición concurrente del usuario podría pisarse (si el archivo era
  pristine al clasificar) o registrarse (si estaba en `sin_cambios`/`solo_si_identico`); es un límite aceptado de v0.10 y no se
  cierra con locks. Los pins byte-exact de evidencia bajo `autocrlf` (F-2) quedan como candidato futuro.

### 8.3 Trust tiers de aprobación (v0.10 Change 2)

Change `20261009-approval-trust-human-presence`. Tiers:

| Tier | Canal | Estado |
|---|---|---|
| T0 | `declared` | vigente, backward compatible |
| T1 | `console_confirmed` (`channel_version = console/v1`) | implementado |
| T2 | enforcement del provider | futuro, NO implementado |
| T3 | PKI / firmas | fuera de alcance |

- **Texto normativo (EN).** A `console_confirmed` approval means that a declared approval was accompanied by an interactive
  confirmation received through a supported control console for that specific operation. It does not prove the identity or
  authorship of the declared user and is not resistant to a deliberately synthesized local console input.
- **Texto normativo (ES).** Una aprobación declarada con ese metadata fue acompañada por una señal T1 de presencia interactiva;
  Harmessi NO verificó que la persona declarada haya realizado físicamente esa aprobación.
- **Registro aditivo.** La aprobación T1 agrega `approval_channel`, `confirmed_at` y `channel_version`; una aprobación sin esos
  campos sigue siendo `declared`. `ApprovalRef` no cambia y solo expone el tier si el estado es `verified`.
- **`isatty()` no es criterio.** En Windows devuelve True incluso en el runtime del agente (stdin=NUL); el canal exige una consola de
  control real (ver `tools/dsguard/human_presence.py`). Sin ella falla cerrado.
- **Inyección sintética.** PTY sintético (POSIX) o `WriteConsoleInputW`/`AttachConsole` (Windows): not empirically exercised;
  explicitly outside T1 guarantee.
- **`!` del provider.** Ejecutar con `!` no es T1 automáticamente: depende del canal observado por el proceso.
- **T1 no es autorización ni RBAC.** Es una señal de presencia, no un permiso ni una identidad. T1 no es un boundary criptográfico.
- **Qué detiene T1.** Flags, `--usuario`, stdin por pipe/archivo/DEVNULL, variables de entorno, subprocesos no interactivos y los
  runtimes de agente observados no obtienen `console_confirmed`.
- **Qué no detiene.** T1 no resiste administrador/root, SO comprometido ni malware.
- **El tier es un registro, no una prueba.** `control.json` no está autenticado ni protegido por pathguard (solo
  `.claude/guardrails.json` lo está): quien pueda editarlo puede escribir `approval_channel`/`channel_version` y el resolver lo leerá
  como T1. La protección frente a eso pertenece a T2 / hook estricto del Bash del Lead (diferido) y a que Change 3 lo consuma junto
  con otras garantías.
- **Dependencia de entorno (Windows).** `GetConsoleWindow() != 0` también es verdadero para un runtime que herede la consola del
  terminal humano (ConPTY/Windows Terminal/shell hijo): un agente podría leer el buffer de pantalla y escribir entrada. Es el mismo
  límite de entrada sintética; la garantía depende de que el runtime del agente no comparta la consola con el humano (caso
  observado: consola privada sin ventana).
- **Alcance (R30).** `decision` y `remediation` siguen T0 (`declared`).
- **Concurrencia de `control.json`.** La concurrencia optimista durante la confirmación reduce pero no elimina la ventana de pérdida
  de actualización (milisegundos entre la verificación y la escritura).
- **Qué ve el humano en `exec approve`.** Confirma `artefacto` + hash abreviado + acción; no ve el intérprete ni el argv real (límite
  documentado; mejora futura posible).
- **Consola heredada (ampliación).** El discriminante de consola también se cumple para un hijo que herede la consola/terminal del
  humano (Windows: ConPTY/Windows Terminal/shell hijo; POSIX: mismo process group en primer plano), así que la garantía depende de
  que el runtime del agente no comparta la consola con el humano.
- **POSIX no verificado.** El comportamiento POSIX NO fue verificado en un runtime real (solo análisis y tests con fakes).
- Aceptación manual ejecutada el 2026-10-13 en una terminal real de Windows: una aprobación `console_confirmed` quedó registrada con las claves históricas más `approval_channel`, `confirmed_at` y `channel_version`; ejecuciones desde las herramientas Bash y PowerShell del agente fallaron cerradas (exit 2, 0 aprobaciones). POSIX y terminales ConPTY/Windows Terminal específicas no fueron verificados.
- **Sintaxis de `exec approve`.** `--channel` debe ir antes de `--`; después se rechaza.
- **Frontera.** `human_presence.py` es stdlib-only y provider-neutral; Cards no lo importan (no crean ni elevan T1). Lo verifica
  `tools/tests/test_architecture_boundaries.py`.
- **Consumo.** Change 3 (Governed Amendments, §8.4) es el primer consumidor obligatorio de T1.

### 8.4 Governed amendments (v0.10 Change 3)

Change `20261013-governed-amendments`. Comandos: `ds_guard scope amend|show` y `ds_guard guardrails readopt`.

- **T1 obligatorio.** Ambas mutaciones exigen `console_confirmed`; no existe `--channel declared`. Fallan cerradas sin consola real.
- **Cadenas propias, append-only.** `openspec/changes/<id>/amendments.jsonl` (scope) y `openspec/decisions/guardrails-adoptions.jsonl`
  (adopciones). NO son el decision ledger.
- **Lectura única del scope.** `scope.alcance_efectivo` es el único lector; la caché de `control.json` nunca supera a la cadena
  (`ALCANCE-CACHE-DIVERGENTE`, `ALCANCE-ENMIENDA-INVALIDA`). Ancla: `alcance.scope_hash`.
- **Closed list de re-adopción.** Exactamente `holdouts`, `data_raw`, `secretos_extra`, `autonomy.sealed_sources`, y SOLO adiciones.
  Excluidos: `excepciones`, `write_scopes`, `autonomy.source_access`, remociones, claves desconocidas y las claves mutables de
  Corrective B (no producen drift). Lo que queda fuera sigue siendo drift contra la plantilla.
- **Doctor.** Baseline = plantilla ∪ adopciones válidas de la cadena.
- **pathguard.** Protege ambos registros (`RUTAS_REGISTROS_GOBERNADOS_PROTEGIDAS`) contra Write/Edit/shell de escritura; no bloquea
  lectura ni el CLI gobernado.
- **Otras reglas.** Re-aprobar un proposal con enmiendas se rechaza; `sync` nunca re-adopta.
- **Operation binding.** Cada operación liga `hash_diff`. Orden de atomicidad: recalcular -> concurrencia optimista -> T1 -> releer ->
  escritura temporal + validar cadena -> `os.replace` -> caché best-effort -> validación posterior.
- **Frontera.** `scope_amendments.py` y `guardrails_adoption.py` son stdlib + imports relativos de `dsguard`; no importan
  `human_presence` (reciben `campos_t1` ya resueltos; la presencia se invoca solo desde `ds_guard.py`) y ni Cards, datasources,
  reporting ni ds_profile los importan. Lo verifica `tools/tests/test_architecture_boundaries.py`.
- **Límites honestos.** Sin criptografía. T1 es presencia, no identidad. pathguard no autentica el registro: la seguridad es
  T1 + binding + cadena + validación + Git. Un agente que escriba fuera de pathguard o sintetice input puede falsificar.
  `readopt` requiere el clon de Harmessi (plantilla del repo origen, como Doctor) y `--destino`.

### 8.5 Upgrade transaccional y recovery (v0.11 Change 5)

Change `20261019-v011-upgrade-migration-resilience`. Comandos: `python -m tools.ds_init upgrade|recover --destino <ruta> [--execute]` (dry-run por defecto).

- **Upgrade transaccional.** Reusa la transacción de `writer.instalar`: staging, journal y backups; `control.json` se regenera DENTRO de la transacción (hook `post_aplicar`) y se escribe de forma atómica (temporal + `os.replace`).
- **Journal persistente.** Vive en `.ds_init/journal/<ts>/` (fuera del staging descartable) con fase (`preparado`, `aplicando`, `control_pendiente`, `completo`) y backups; se escribe de forma atómica (temporal + fsync + `os.replace`), la fase `aplicando` se persiste ANTES del primer movimiento, cada entrada registra `sha256_nuevo`, y al limpiar `journal.json` se borra en último lugar. Solo se borra tras éxito o rollback exitoso.
- **Rollback, no roll-forward.** `recover` restaura backups, borra lo creado y elimina staging y journal; vuelve a detectar con el lock tomado. Aborta (exit 2) sin tocar nada si el journal es ilegible, si falta un backup necesario (un backup ausente es fallo, no skip), si una ruta del journal es inválida (absoluta, `..`, `:`, `.git/`, fuera del destino tras resolver symlinks del padre, o fuera del MANIFEST y de `.ds_init/`), o si un archivo a revertir fue editado tras la interrupción (hash distinto del escrito y del backup) salvo `--forzar`, que conserva la copia como `<ruta>.recover-bak`. Un journal `completo` o un directorio sin `journal.json` se tratan como housekeeping. `migrate-hashes --execute` toma el lock, aborta ante huérfanos y sus `control.json.bak-*` se conservan (recover no los limpia).
- **Plan de upgrade.** Solo managed pristine (`ok`/`ok_legacy`) con contenido distinto, managed nuevos del manifest (stage y capabilities persistidos) y merge de `settings.json`; drift reportado sin adoptar; project-owned, `EXCLUSIONES_PERMANENTES` y un `guardrails.json` existente nunca se tocan. Idempotente.
- **Lock.** `.ds_init/lock` (`O_EXCL`, pid y timestamp) serializa install/sync/upgrade/recover; un lock existente nunca se ignora ni se roba.
- **Doctor.** `HARMESSI-VERSION` (WARN con remedio `upgrade`) y `HARMESSI-MIGRACION` (FAIL ante staging/journal parcial, WARN ante lock o journal completo residual).
- **Límites honestos.** Sin downgrade; sin migración de datos; el lock es cooperativo, no defensa ante un actor hostil, y tras un kill puede quedar `.ds_init/lock` (borrarlo a mano si no hay proceso vivo; sin detección de pid a propósito); Doctor corre desde el checkout; `upgrade` no recrea un managed borrado a mano (se restaura desde Git); un corte entre `os.replace` y la marca `aplicado` se cubre restaurando siempre el backup de los `reemplazar-merge`.

## 9. Harness Surfaces (v0.12)

Change `20261021-v012-harness-surfaces`. Vocabulario de qué puede evolucionar metodológicamente y qué no; la superficie se DERIVA de la ruta, sin metadata nueva.

- **Protected.** Guardrails, permisos, semántica de aprobación, trust model, scope enforcement, límites de seguridad y enforcement determinista: `.claude/**` (salvo lo optimizable), `tools/**`, `.ds_init/**`, `.harmessi/**` y `control.json`/`amendments.jsonl` de cualquier Change.
- **Optimizable.** Skills metodológicas, guidance de metodología, prompts/instrucciones, tool guidance y patrones de razonamiento reutilizables: `.claude/skills/lead-data-scientist/skills/*.md` (un nivel), `methodology.md`, `eda.md`, `kdd.md` de esa carpeta.
- **Project-owned.** `GLOSSARY.md`, definiciones de negocio, Data Contracts, configuración y artefactos del proyecto: todo lo demás.
- **Derivación.** `tools/dsguard/skill_contract.py::superficie_de_ruta(ruta)`, pura (normaliza `\` y `./`, sin distinguir mayúsculas; `..` ⇒ protected, fail-safe). `_validar_artifacts` emite `SKILL-ARTIFACT-SUPERFICIE-PROTEGIDA` si un `artifacts` cae en Protected; Doctor lo expone como WARN vía `HARMESSI-SKILL-CONTRATO`. Sin claves nuevas de frontmatter.
- **Qué NO existe.** Optimizer, auto-modificación del harness, candidate/probe engine, marketplace ni policy engine. Optimizable ≠ auto-modificable: modificar una superficie optimizable sigue siendo un Change normal (SDD, alcance, aprobación, verificación).
- **Por archivo, no por contenido.** Las partes normativas de approval/scope dentro de `methodology.md` se tratan como Protected de facto; toda modificación sigue siendo un Change normal.

### 9.1 Problem framing (v0.12)

Change `20261021-v012-problem-framing`. Skill componible `problem-framing` (`.claude/skills/lead-data-scientist/skills/problem-framing.md`, superficie Optimizable, distribuida VERBATIM por el manifest y esperada por Doctor). Es guidance, nunca authority, y no agrega frontmatter, roles, hooks ni artefactos. Se carga solo ante un brief ambiguo; distingue tres niveles (inferible, ambigua no material con supuesto trazable, material con checkpoint humano) y deriva la semántica de negocio a `domain-modeling` sin duplicar GLOSSARY ni Decision Ledger. `grill-me` es un modo opt-in interno (solo si el humano pide desafiar la definición), no otra skill ni un interrogatorio por defecto.

### 9.2 Diagnosing bugs (v0.12)

Change `20261021-v012-diagnosing-bugs`. Skill componible `diagnosing-bugs` (`.claude/skills/lead-data-scientist/skills/diagnosing-bugs.md`, superficie Optimizable, distribuida VERBATIM por el manifest y esperada por Doctor). Es guidance, nunca authority, y no agrega frontmatter, roles, hooks, permisos ni artefactos. Define un workflow de nueve pasos con evidencia observable (reproduce → verify), siete clases de fallo y una atribución baseline-aware focalizada y de solo lectura, solo ante un fallo durante un Change con duda razonable (no ante todo fallo): `git show`/`git diff` del commit baseline y, si hay que ejecutar, extracción mínima con `git show` al «área temporal» (un único directorio temporal en el scope del Change, verificado con `git check-ignore`, nunca `data/` ni `.harmessi/`, limpiado al terminar; si no hay uno, `inconclusive`) con solo el test concreto; nunca la suite completa, nunca datasets completos ni holdouts, ni `git checkout/stash/reset/clean/switch` sobre el árbol del usuario (`introduced|pre-existing|environment|inconclusive`; datos ausentes nunca es `pre-existing`). No hay debugger ni runner nuevo: el Lead ejecuta vía `ds_guard exec`, el writer corrige la causa raíz con su regression test y los topes de remediation/reintentos no cambian.

### 9.3 Codebase design (v0.12)

Change `20261021-v012-codebase-design`. Skill componible `codebase-design` (`.claude/skills/lead-data-scientist/skills/codebase-design.md`, superficie Optimizable, distribuida VERBATIM por el manifest y esperada por Doctor). Es guidance, nunca authority, y no agrega frontmatter, roles, hooks, permisos ni artefactos. Se carga solo ante un cambio estructural en la codebase del proyecto (no ante cambios locales) y no impone la arquitectura de Harmessi. Razona de forma proporcional los temas pertinentes de once posibles (boundaries, ownership de módulos, acoplamiento, cohesión, primitivas existentes, contrato público/interno, dirección de dependencias, impact radius, compatibilidad hacia atrás, migración y test seams) con la preferencia ordenada reuse > extend > new local primitive > new subsystem/framework y el criterio de un consumidor real y concreto. El radio de impacto sigue siendo `ds_guard impact scan` / `methodology.md` §25 (lo corre el Lead, solo estático; no se reimplementa); el razonamiento se registra sin artefactos nuevos (`design.md` si el Change no está aprobado; `verification.md` o nota del Lead si ya lo está; mensaje al humano si no hay SDD) y el Decision Ledger lo propone el Lead o el `metodologo`, lo registra el Lead y lo aprueba el usuario. Asesora al Lead: cambio incompatible, dependencia nueva relevante o expansión de scope siguen siendo decisión humana / STOP.

### 9.4 Selección y composición de skills (v0.12)

Change `20261021-v012-skill-selection-composition`. Criterio documental (`methodology.md` §40), sin código de producción ni nuevos códigos de hallazgo. Tabla de selección de las cuatro skills distribuidas por señal del pedido; carga mínima (solo las pertinentes, ninguna si ninguna aplica, bajo demanda); composición por pares sin resolver de dependencias, grafo, registry, marketplace ni plugins. Conflicto entre dos skills: el Lead resuelve semánticamente sin violar capas superiores y deja el criterio en el motivo de la traza; si involucra una capa superior gana esa y rigen los STOPs (la regla no permite saltarlos); si la resolución implica una decisión de `methodology.md` §19 / `CLAUDE.md` §3 o hay duda sobre la capa, el Lead propone al humano en vez de resolver, y ante empate prevalece la guidance más restrictiva; sin merge engine (reemplaza la regla histórica de §7.2). La traza `## Skills cargados` (`referencias_skills_cargados` / `SKILL-REFERENCIA-DESCONOCIDA`, sin cambios) se registra solo ante influencia material (la skill cambió una decisión, un criterio de aceptación, la delegación, el scope/ownership o el diseño; sin ella el resultado habría sido otro), un bullet por skill, sin telemetría. La foundation v0.10 se preserva: markdown, bajo demanda, sin permisos, hooks ni ejecución.

## 10. Evaluation & Benchmark Foundation (v0.13)

Change `20261021-v013-eval-benchmark-foundation`. Extiende `tools/harmessi_bench` (no hay paquete paralelo); todo lo nuevo es opcional y retrocompatible, solo stdlib.

- **Caso, suite y resultado versionados.** `Scenario` suma `fixtures` y `surface_under_test`; `case_contract_version` (ausente ⇒ 0, legado; 0 y 1 soportados, otro valor ⇒ `ValueError`). `suite.py`: manifest `suite_contract_version` = 1 con `cases_file` relativo al manifest (sin `..`, absoluto ni escape del directorio) y `case_ids` exactos; `suite_hash` = sha256 del JSON canónico de los casos, independiente de orden, CRLF/LF y rutas. `result.json` agrega `schema_version` (1; ausente ⇒ 0; mayor ⇒ falla), `evaluator_version` y bloque `suite`.
- **Veredicto.** `compare_runs` agrega `verdict`/`verdict_reason`: `candidate_better|baseline_better|equivalent|inconclusive`, solo por `score.passed` determinista y conservador (`inconclusive` ante sets distintos, indisponibilidad, suite o `evaluator_version` distinto o declarado en un solo lado, o regresiones y mejoras a la vez). Disponibilidad ≠ calidad.
- **Evals ≠ tests.** Los tests prueban corrección determinista del código; los evals observan comportamiento de un target y dan evidencia comparativa, nunca una promoción ni una garantía.
- **Boundary Protected/Optimizable.** Un caso puede declarar `surface_under_test` solo si `superficie_de_ruta` (§9) da `optimizable`; `protected` o `project-owned` ⇒ `ValueError`. El paquete no promueve, escribe ni modifica superficies.
- **Pureza.** `core.py`/`runner.py` conservan `test_v05_core_neutrality`; `suite.py` y `compare.py` no importan providers, `subprocess` ni red. Solo-checkout: no se amplía el manifest instalado.
- **Comparar sin suite (`cases_hash`).** `run` persiste SIEMPRE `cases_hash` (mismo cálculo canónico que `suite_hash`, sobre los casos cargados, también con `--scenarios`). Si ninguna corrida declara `suite`: ambos `cases_hash` iguales ⇒ se compara; distintos o solo uno ⇒ `inconclusive`; ninguno pero alguna con `evaluator_version` (corrida v1 sin hash) ⇒ `inconclusive`; ninguna con hash ni evaluator (legadas puras) ⇒ se compara con una nota en `verdict_reason`. Con `cases_hash` en ambas y distintos ⇒ `inconclusive` aunque la suite coincida. Esta regla complementa R13 y se registra en `verification.md`.
- **Niveles de evidencia.** (1) test determinista: prueba el código, reproducible; (2) eval de una muestra: una corrida por caso contra un target estocástico, `verdict_reason` informa `n`, pasados por lado y "una sola muestra"; un `equivalent` con 0 pasados en ambos lados lleva un aviso explícito; (3) eval repetida con estadística: no soportada todavía, no se afirma.
- **Límites honestos.** Los scorers deterministas (`contains`/`regex`/`exact`) son un proxy superficial de texto, no medición semántica; sin LLM-as-judge, sin leaderboard ni servicio; una corrida real contra un proveedor es estocástica y un `equivalent` no prueba igualdad de calidad.

### 10.1 Reproducible Harness Runs (v0.13 Change 2)

Change `20261021-v013-reproducible-harness-runs`. Extiende `tools/harmessi_bench`; aditivo, solo stdlib, cero telemetría (todo local en `.harmessi/evals/<run_id>/`).

- **Run manifest.** `runmanifest.py` (`MANIFEST_VERSION = 1`) agrega a `result.json` el bloque opcional `run_manifest` (`schema_version` sigue en 1; ausente ⇒ corrida sin manifest): versión de harmessi, `git` (`commit`, `clean`), hash de contenido de cada skill, `surfaces_hash` (superficies Optimizable), `guardrails_hash` (o `null`), `target`, `evaluator_version`, `suite`, `cases_hash`, `seed`, plataforma mínima, timestamps e `identity_hash`. Solo ids, hashes y versiones: nunca entorno, hostname, usuario, rutas absolutas, prompts ni salidas del modelo. Los hashes normalizan CRLF a LF. `identity_hash` cubre solo lo material (no `run_id`, timestamps, plataforma, `git` ni `seed`). Git se lee solo vía `dsguard.repo`; si falla ⇒ `commit = "unknown"`, `clean = null` (unknown no es limpio). El `commit` es informativo: cambia en cada Change sin alterar las superficies, cuya identidad es el hash de contenido.
- **Redacción best-effort.** `redact.redactar_texto` reemplaza rutas de usuario, emails y tokens comunes por `<RUTA_USUARIO>`, `<EMAIL>`, `<TOKEN>`; `save_run` la aplica a `stdout_excerpt` y `score.detail`. Es idempotente y prefiere sobre-redactar, pero NO es una garantía: las regex de tokens no son exhaustivas y un secreto con otro formato puede persistir.
- **Resume seguro.** `run --resume` exige un `result.json` existente con `run_manifest`; si `evaluar_compatibilidad` encuentra diferencias materiales (versión de manifest/harmessi, suite, casos, skills, superficies, guardrails, evaluator, provider, model, effort) falla con exit 1 sin tocar el resultado ni invocar al provider. Si es compatible, solo corre los escenarios sin resultado `ok=True` y combina. Sin `--resume`, un `run_id` existente con manifest falla; uno legado sin manifest se sobrescribe. `git.commit` distinto solo emite una advertencia.
- **Comparación.** `compare_runs` agrega `config_diff` (claves materiales distintas). Con manifest en un solo lado, manifest incompleto, o distinto `manifest_version`/`evaluator_version`/suite/casos ⇒ `inconclusive`. Skills, superficies, provider y model pueden diferir: es lo que se evalúa y se lista en `config_diff`. Misma `identity_hash` ⇒ se anota «repetición» y el veredicto sigue decidiéndose por score.
- **Tres niveles, sin promesa bit a bit.** (1) *Configuration reproducibility*: el `identity_hash` dice si dos corridas usaron la misma configuración material; no garantiza el mismo resultado. (2) *Execution determinism*: solo los scorers y `compare` son deterministas; el modelo no lo es, y `--seed` se registra como dato informativo sin afirmar que el provider lo respete. (3) *Stochastic outcome*: la salida de un LLM varía entre corridas; una sola muestra por caso no es evidencia estadística.
- **Robustez y límites.** `save_run` escribe de forma atómica (temporal + `os.replace`; un fallo deja intacto el result existente) y valida `run_id` (`[A-Za-z0-9][A-Za-z0-9._-]{0,127}`). El manifest se calcula una vez antes de correr; si skills/superficies/guardrails cambian durante la corrida, `run` falla sin escribir. Un manifest con identidad no confiable (skills vacío, directorio ausente o hash ilegible) es incompleto: `run` no corre y `compare` da `inconclusive`. Un `run_manifest` no-dict en un result existente falla cerrado. `sesiones` registra cada ejecución (inicio/resume) y no es material. Límites declarados: no hay soporte de ejecuciones concurrentes sobre el mismo `run_id` (single-writer); la identidad cubre skills, superficies, guardrails, evaluator y target, pero no agents, `CLAUDE.md` ni el código de `tools/`; el `commit` es informativo (R10); la redacción es best-effort.
- **Boundaries.** `runmanifest.py` y `redact.py` no importan providers, red ni `subprocess` (Git es un import diferido de `dsguard.repo`) y no escriben fuera de `storage`; nada promueve ni modifica superficies.

### 10.2 Provider & Adapter Conformance (v0.13 Change 3)

Change `20261021-v013-provider-adapter-conformance`. Dos conceptos separados; no se modifica el contrato de `ProviderAdapter`, `SourceObservation` ni `SourceCapabilities`. Sin telemetría ni red.

| Módulo | Alcance | Instalado |
|---|---|---|
| `tools/providers/conformance.py` | conformance de providers de modelo (`verificar_conformidad`, `SOPORTE_DECLARADO`, CLI `python -m tools.providers.conformance`) | no (solo-checkout) |
| `tools/datasources/conformance.py` | conformance de observers de fuente (`verificar_observer`); solo stdlib + `core`/`scan`; MANIFEST VERBATIM, `MODULOS_CORE` | sí |

- **Niveles de soporte (providers).** `contract-tested` (chequeos de forma, detección, parseo de versión, comando de invocación, clasificación de fallas y forma de capacidades contra dobles de `shutil.which`/`subprocess.run`); `locally-smoke-tested` (además `detect()` real con versión en este host); `live-validated` (invocación real mínima, doble opt-in `--live` + `HARMESSI_LIVE_PROVIDER=1`). El nivel se deriva de evidencia, nunca de documentación; un chequeo de contrato fallido anula el nivel, y smoke/live no cumplidos dejan el nivel inferior.
- **`SOPORTE_DECLARADO` real.** Los 4 providers (`claude_code`, `codex`, `gemini`, `grok`) figuran `contract-tested`; ninguno `locally-smoke-tested` ni `live-validated`. Para `claude_code` el `detect()` se observó en el host de desarrollo, pero el smoke depende del host: se reporta en `nivel_alcanzado` con `--smoke`, sin evidencia registrada en CI. Un test ancla la tabla a `PROVIDER_REGISTRY` y exige que la suite alcance exactamente lo declarado.
- **Dobles y secretos.** Los dobles cubren `subprocess.run/Popen/check_output/check_call/call` y `shutil.which` (a nivel de módulo y dentro del módulo del adapter si usó from-import); todo delega en un doble que registra la llamada. Se plantan valores sintéticos en `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `XAI_API_KEY`, `GROK_API_KEY`, `CODEX_API_KEY` y una variable propia; ninguno puede aparecer en args, `env=`, `input=` ni otro kwarg. `advertencias` del reporte marca `ignora model`/`ignora effort` (no falla; solo falla si la capability `thinking_effort` lo promete). Un live omitido registra evidencia `none`.
- **Real vs fixture.** Real: `detect()` de `claude` (solo con `HARMESSI_SMOKE_LOCAL=1` y la CLI en PATH) y `FileObserver` sobre un CSV sintético temporal con espacios/Unicode (skip si falta `ds_profile`/`pandas`). Fixture: contrato de los 4 providers contra dobles, y los observers conformante/inválidos. El reporte de observers lleva `evidencia` real|fixture, declarada por quien llama.
- **Observers.** Chequeos: forma del factory, `validate_capabilities`, observación que reconstruye `SourceObservation` con `source_id`/`schema_version`, facetas ⊆ declaradas, `source_id` inválido rechazado, sin secretos/rutas absolutas (`scan`, heurístico), `content_sha256` reproducible, sin instaladores ni lanzadores de procesos (AST del archivo del factory: imports de `subprocess`/`pip`/`uv`/`poetry`/`setuptools`/`runpy`/`ctypes` a cualquier nivel salvo bajo `TYPE_CHECKING`, `__import__`/`import_module` con constante prohibida, `os.system/popen/spawn*/exec*`) y error acotado (requiere `options_error`). «Acotado» = `SourceError`, `RuntimeError`, `ValueError`, `FileNotFoundError`, `OSError`; cualquier otra clase falla nombrando el tipo. Un chequeo no evaluado deja `ok=False` y `completo=False` salvo `permitir_no_evaluados=True`. Los detalles nunca copian `str(exc)`: solo tipo y código; `SystemExit` es un chequeo fallido y `KeyboardInterrupt` se propaga.
- **Límites.** Pasar el contrato contra dobles no garantiza el comportamiento de la CLI real; live nunca corre por defecto. El AST no es exhaustivo (no sigue módulos hermanos ni nombres dinámicos). Límites menores registrados (L3, L5–L8 del review): el chequeo de secretos/rutas es heurístico; la reproducibilidad solo se mide con dos observaciones consecutivas; el mapeo de originales para from-import depende de que el adapter lo haga a nivel de módulo; `evidencia` real|fixture la declara quien llama y la suite no la verifica; los dobles no emulan semántica completa de `Popen` (streams, señales).

### 10.3 Portability & Cross-Platform Hardening (v0.13 Change 4)

Change `20261021-v013-portability-hardening`. Sin cambios a hooks, permisos, roles ni a `dsguard.repo`; sin dependencias nuevas.

- **dsimpact fail-closed.** `git_source.contenido_before(..., status=)` / `contenido_after(..., status=)` devuelven `None` solo cuando la ausencia es esperada por el status (`added` antes, `deleted` después); en otro caso un contenido ilegible (git no disponible, blob ausente, `returncode != 0`, archivo del working tree ilegible) lanza `GitSourceError` sin rutas absolutas. Para `renamed` el «antes» se lee de `old_path`. `scan` propaga la excepción y la CLI la traduce a mensaje + exit code 1: nunca «0 consumidores» sobre evidencia no leída (unknown ≠ empty). `--staged` con status `U`/`T` se trata como `modified`: si el blob falta, falla cerrado. Los consumidores que no pueden analizarse (ilegibles, ausentes, `SyntaxError`/JSON inválido) y los cambios con excepción inesperada no abortan el scan pero se listan en `summary.consumidores_no_analizados` / `summary.cambios_no_analizados` (`[{path, motivo}]`, ordenado, sin mensajes); sin findings, la CLI imprime «resultado no concluyente» en vez de «ningún consumidor». Exit code sin cambio.
- **Traza duplicada.** `validar_referencias_skills` emite `SKILL-TRAZA-SECCION-DUPLICADA` (una vez por archivo) si `## Skills cargados` aparece más de una vez como título real (fuera de fences ``` / ~~~ y de comentarios HTML). No se fusiona: las referencias se leen de la primera sección REAL (mismo criterio que el contador). `verificador.md` no se actualizó con el nuevo hallazgo (deuda).
- **Consola.** `_consola_segura()` (best-effort, `reconfigure(errors="replace")`) en `harmessi_bench.cli` y `providers.conformance`.
- **Auditoría y tests.** `docs/portability.md` es el inventario vivo; `test_v013_portability_audit.py` (AST) impide patrones no portables en los módulos v0.13 y `test_v013_portability_smoke.py` ejercita el host real.
- **CI.** `.github/workflows/portability-smoke.yml` (ubuntu/windows/macos × Python 3.12, `contents: read`, solo `pytest`, lista acotada de tests). Real: Windows (este host). Contractual: Linux/macOS — workflow presente; ejecución remota no observada.

### 10.4 Contract Inventory, Compatibility & Deprecation (v0.13 Change 5)

Change `20261021-v013-contract-inventory-compat`. Sin cambios a CLIs, exit codes ni schemas existentes; sin dependencias nuevas.

- **Inventario, no promesa de estabilidad.** `docs/contracts/inventory.json` clasifica los contratos consumibles (`public-candidate` / `internal` / `experimental`); ninguna clase implica estabilidad v1.0. El test `test_v013_contract_inventory.py` lo compara con el código (subcomandos exactos de cada CLI, constantes de versión por `version_ref`, rutas, CLIs sin clasificar).
- **Ventana de compatibilidad.** Lectura soportada de artefactos de la versión actual y las dos menores previas (`docs/versioning.md`); `test_v013_compat_window.py` usa fixtures sintéticos de v0.11/v0.12 y, si existen localmente, los tags reales.
- **Deprecación.** Convención en `docs/deprecation.md` y primitiva mínima solo-checkout `tools/harmessi/deprecation.py` (registro vacío; sin framework, sin telemetría, sin escritura a disco; no entra al manifest instalado).

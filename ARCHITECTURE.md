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
| `tools/dsimpact/*` (todo el paquete) | Impact preflight (v0.4 Change 1) |
| `tools/ds_profile/*` (todo excepto lo que reusa `pathguard` como config) | Profiling de datasets |
| `tools/nbrunner/core.py`, `execute.py`, `fsdiff.py`, `manifest.py` | Ejecución controlada de notebooks (invocada por el adapter, no es adapter en sí) |
| `tools/launcher_common.py` | **Mixto, ver §2.3** — la mayoría de sus funciones (`resolver_venv_dir`, `ruta_interprete_venv`, `resolver_repo_root`) son utilidades neutras de resolución de venv/repo Git, usadas también por `tools/harmessi/doctor.py` (core, diagnóstico) — pero también contiene `lanzar_hook`, que sí es específica de Claude Code |
| `tools/ds_guard.py`, `tools/ds_profile/cli.py`, `tools/dsimpact/cli.py`, `tools/harmessi/cli.py` | CLIs `argparse` — portables: cualquier orquestador que pueda invocar un proceso puede usarlos, no conocen el protocolo de hooks |
| `tools/ds_init/*` | Instalador/scaffolding — su propia lógica (planner, writer, templating, control.json) es agnóstica; el *contenido* que instala está hoy pensado para Claude Code, pero el instalador mismo no se invoca como hook ni depende del protocolo de hooks |
| `tools/providers/core.py` | Contrato neutral de invocación multi-proveedor (v0.5 Change 0) — "adapter" en el sentido de patrón de diseño (adapter de proveedor de IA), no confundir con la acepción "Adapter" de §2.2 (protocolo `PreToolUse` de Claude Code); este módulo es core porque no conoce ningún protocolo específico de invocador, es un contrato neutral que las 4 implementaciones concretas satisfacen |
| `tools/harmessi_bench/core.py` | Tipos neutrales y scoring determinista del framework de evals (v0.5 Change 1) — no importa `tools.providers` ni ningún proveedor concreto; `runner.py` (no listado acá, mismo criterio que las 4 implementaciones de adapters de Change 0) es quien invoca un target reusando el contrato de `tools/providers/core.py` y `storage.py` quien persiste resultados en `.harmessi/evals/<run_id>/result.json` (mismo patrón de `ds_profile` → `.harmessi/profiles/`); no conoce protocolo de hooks, es core. |
| `tools/routing/core.py` | Resolución determinista de routing provider/model/effort por rol+tarea (v0.5 Change 2; extendido de forma aditiva con `fallback_chain` en v0.5 Change 3) -- puramente declarativo (lee una `RoutingPolicy` ya construida, nunca infiere ni mide nada); no importa `tools.providers` ni ningún proveedor concreto, es core. `policy.py` (no listado acá, mismo criterio que Change 0/1) carga la política opcional desde `.harmessi/routing.json` (ausente = sin política declarada, nunca heurística) y valida su forma. |
| `tools/fallback/core.py` | Motor de fallback técnico entre proveedores (v0.5 Change 3) -- decide reintentar SOLO cuando `InvocationResult.availability_error` es elegible (`quota`/`unavailable`/`unauthenticated`, ver `classify_availability_error` de Change 0); nunca por error semántico/de código, hallazgo de reviewer, test fallido o mala calidad de output (esas señales ni siquiera se importan acá) -- es core, no conoce protocolo de hooks. |
| `tools/reporting/core.py` | Contratos neutrales de reporting gobernado (v0.6 Change 0: `Report`/`Chapter`/`TableArtifact`/`FigureArtifact`/`FigureSpec`/`Insight`, serialización determinista y hash de contenido) -- solo stdlib; no importa Plotly, HTML, pandas, numpy, `dsguard`, `ds_profile` ni ningún hermano de `tools/reporting`, ni conoce un dominio (p. ej. EDA) o backend gráfico concreto; valida solo estructura (la completitud semántica/evidencial es de un Change posterior); no conoce protocolo de hooks, es core. |
| `tools/reporting/governance.py` | Output guard declarativo de reportes (v0.6 Change 1) -- solo lectura: compone `dsguard` (`checks`, `pathguard`, `repo`, `scientific_validity`, `core`) y `reporting.core` con policy opcional `.harmessi/reporting-policy.json` (destino por scope, aislamiento exploratorio, holdout, cutoff); todo resultado es un `dsguard.checks.CheckResult` (sin engine propio) y solo evalúa rutas, nunca abre datos; importa `dsguard` (dirección permitida por la regla 6) pero no `ds_profile`; no conoce protocolo de hooks (usa `pathguard.evaluar_tool_call` como función, no lee stdin), es core. |
| `tools/reporting/cli.py` | CLI `argparse` de reporting gobernado (v0.6 Change 1: `check-inputs`, `check-destination`; Change 3: `validate` y `REPORT-ISOLATION-HASH` aditivo en `check-inputs`; `python -m tools.reporting`) -- portable, solo lectura, exit codes 0/1/2/3 y salida `--json` opcional; no conoce el protocolo de hooks ni lee stdin. |
| `tools/reporting/profiles/eda.py` | Profile EDA sobre el core de reporting (v0.6 Change 2) -- catálogo de bloques, declaración de aplicabilidad en `Report.metadata["eda"]`, autoderivación estructural y validador `EDA-*` que devuelve `dsguard.checks.CheckResult`; importa `reporting.core` y `dsguard.checks` (dirección permitida por la regla 6), pero no `governance`, pandas ni backends gráficos; verifica estructura y aplicabilidad explícita, no adecuación metodológica; solo lectura y determinista, es core, no conoce protocolo de hooks. |
| `tools/reporting/examples/eda_generic.py` | Ejemplo genérico de reporte EDA (v0.6 Change 2) -- datos 100% sintéticos con `random.Random(RANDOM_STATE)` y estadísticas con stdlib; construye un `Report` con el profile `eda` que pasa `validate_eda_report` sin FAIL y es determinista; sin pandas, sin datos reales, es core. |
| `tools/reporting/evidence.py` | Evidencia de reportes (v0.6 Change 3) -- descripción de fuentes con hash, construcción del manifest, escritura atómica y lectura del directorio de reporte, e índice de artefactos exploratory para el aislamiento por hash (`REPORT-ISOLATION-HASH`); importa `reporting.governance`, `dsguard` (dirección permitida por la regla 6) y, de `ds_profile`, SOLO `fingerprint`; no decide permisos de escritura (eso es del guard de governance/publish), no conoce protocolo de hooks ni lee stdin, es core. |
| `tools/reporting/validation.py` | Validador de reportes (v0.6 Change 3) -- reglas de figuras, insights y manifest, y puerta completa `validate_report_dir` sobre un directorio persistido (integridad, fuentes, contenido, governance, aislamiento); importa `reporting.profiles.eda`, `reporting.evidence` y `reporting.governance`, todo resultado es un `dsguard.checks.CheckResult`; solo lectura y determinista, verifica estructura y evidencia, no adecuación metodológica; es core, no conoce protocolo de hooks. |
| `tools/reporting/style.py` | Design system de reportes (v0.6 Change 4) -- contratos `Style`/`VisualStyle`/`EditorialStyle` (dataclasses frozen), `default_style()` genérico, presets de locale como data, overrides opcionales `.harmessi/report-style.json` (esquema estricto, lectura vía `evidence.read_allowed`) y `check_style` (contraste/paleta); solo stdlib y `reporting.evidence`/`dsguard.checks`, desacoplado del renderer (no importa `render_html` ni `plotly_backend`); es core, no conoce protocolo de hooks. |
| `tools/reporting/plotly_backend.py` | Backend opcional de figuras (v0.6 Change 4) -- `build_figure` arma a mano un dict JSON-puro tipo Plotly desde `FigureSpec` + tabla, sin mutar los artefactos; NO importa `plotly` a nivel de módulo (solo `find_plotly_bundle` intenta un import perezoso para localizar `plotly.js`, sin declarar dependencia); es core, no conoce protocolo de hooks. |
| `tools/reporting/render_html.py` | Renderer HTML (v0.6 Change 4) -- `render_report_html` compone `report.html` con funciones puras sobre stdlib (`html.escape` en todo texto de usuario); determinista (mismo input, mismos bytes) y offline (solo CSS/JS inline); sin pandas ni red; es core, no conoce protocolo de hooks. |
| `tools/reporting/publish.py` | Publicación de reportes (v0.6 Change 4) -- `publish` orquesta governance → validation → evidence → render y escribe el directorio del reporte más `report.html`; importa solo `reporting.*` y `dsguard.*` vía los módulos existentes; única puerta de escritura del reporte completo; es core, no conoce protocolo de hooks. |
| `tools/fallback/handoff.py` | Contexto de handoff a nivel SDD (v0.5 Change 3) -- contexto mínimo suficiente para continuar un Change entre sesiones/proveedores sin reiniciar trabajo ni duplicar auditorías (`completed`/`pending`/`prior_findings`); persistido en `.harmessi/handoffs/<id>/handoff.json`, mismo patrón que `.harmessi/evals/`. |

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
   dependen del core, `governance`, `evidence` y `validation`; el core (`core.py`,
   `governance.py`, `evidence.py`, `validation.py`, `profiles/`) NO conoce style, render ni
   backend. `report.html` es un artefacto derivado y reproducible, fuera del manifest (su
   integridad se verifica re-renderizando con `render --check`); el escape de todo texto de
   usuario ocurre en `render_html`, nunca en el core.

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

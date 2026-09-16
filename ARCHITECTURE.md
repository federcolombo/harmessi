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

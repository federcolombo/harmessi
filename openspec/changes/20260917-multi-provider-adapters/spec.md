# Spec — 20260917-multi-provider-adapters

## Requisitos

- **R1**: `tools/providers/core.py` define un contrato neutral (`ProviderCapabilities`,
  `ProviderInfo`, `InvocationRequest`, `InvocationResult`, `ProviderAdapter`) sin importar
  `subprocess` con flags específicos de un proveedor, sin leer `stdin`, y sin conocer el protocolo
  `PreToolUse` de Claude Code.
- **R2**: `core.py` expone `classify_availability_error(exit_code, stderr) -> Optional[str]`, una
  heurística best-effort de texto sobre `stderr` (case-insensitive) que distingue `"quota"`,
  `"unauthenticated"`, `"unavailable"` de cualquier otro fallo (que devuelve `None`), como única
  fuente de esa distinción para que Change 3 (fallback) no la reinvente por proveedor.
- **R3**: `core.py` expone `PROVIDER_REGISTRY` (poblado en `tools/providers/__init__.py`, no en
  `core.py`) y `list_providers(registry=None)`, que usa `PROVIDER_REGISTRY` vía import diferido si
  no recibe un registro explícito, y nunca deja que la excepción de un adapter individual crashee
  toda la función.
- **R4**: cuatro adapters concretos (`claude_code.py`, `codex.py`, `gemini.py`, `grok.py`), cada
  uno en su propio archivo, heredan de `ProviderAdapter` e implementan `detect()` e `invoke()`
  usando `shutil.which` + `subprocess.run` contra la CLI real del proveedor, sin intentar instalar
  ni asumir disponibilidad no verificada.
- **R5**: `ClaudeCodeAdapter` está verificado contra la CLI real disponible en este entorno
  (`claude --version`, `claude --help` con `--effort`); los otros tres adapters documentan
  explícitamente qué partes de su comando de invocación son best-effort/no verificadas por ausencia
  de la CLI en este entorno.
- **R6**: `tools/providers/__init__.py` instancia los 4 adapters, arma `PROVIDER_REGISTRY` y
  re-exporta el contrato neutral de `core.py` vía `__all__`.
- **R7**: `tools/harmessi/cli.py` agrega el subcomando `providers list` (con `--json` opcional) sin
  reescribir el subcomando `doctor` existente, siguiendo el mismo patrón de formateo que
  `doctor.formatear`.
- **R8**: la suite de tests nueva (`tools/providers/tests/test_core.py`,
  `tools/providers/tests/test_adapters.py`, `tools/harmessi/tests/test_providers_cli.py`) cubre
  `classify_availability_error`, `list_providers` con un adapter roto, conformidad de interfaz de
  los 4 adapters, detección/invocación sin CLI instalada para `codex`/`gemini`/`grok` (vía
  `monkeypatch`), detección real (no simulada) de `claude_code` cuando la CLI está presente, el
  armado del comando de `ClaudeCodeAdapter.invoke()` (vía `monkeypatch` sobre `subprocess.run`, sin
  invocar el binario real), y el subcomando `providers list --json` de la CLI.

## Criterios de aceptación

- **R1**: Given se inspecciona `tools/providers/core.py`, When se revisan sus imports y su cuerpo,
  Then no aparece ningún `import subprocess` que arme flags específicos de un proveedor, ninguna
  lectura de `sys.stdin`, y ninguna referencia a `tool_name`/`tool_input`/`agent_type`.
- **R2a**: Given un `stderr` que contiene "rate limit exceeded", When se llama
  `classify_availability_error(1, stderr)`, Then devuelve `"quota"`.
- **R2b**: Given un `stderr` que contiene "Error: not logged in", When se llama
  `classify_availability_error(1, stderr)`, Then devuelve `"unauthenticated"`.
- **R2c**: Given `exit_code=127`, When se llama `classify_availability_error(127, "")`, Then
  devuelve `"unavailable"`.
- **R2d**: Given un `stderr` de error genérico tipo "SyntaxError: invalid syntax", When se llama
  `classify_availability_error(1, stderr)`, Then devuelve `None`.
- **R3**: Given un registro de prueba con dos adapters, uno normal y otro cuyo `.detect()` lanza
  una excepción, When se llama `list_providers(registro)`, Then la función devuelve 2
  `ProviderInfo` sin propagar la excepción, y el segundo tiene `available=False` con `detail` no
  vacío.
- **R4a**: Given `codex`/`gemini`/`grok` no están en PATH (forzado con `monkeypatch` sobre
  `shutil.which`), When se llama `.detect()` de cada adapter, Then `available=False` y `detail` no
  vacío, sin excepción.
- **R4b**: Given la CLI ausente (mismo `monkeypatch`), When se llama `.invoke(request)`, Then
  devuelve `ok=False, availability_error="unavailable", exit_code=127`, sin lanzar excepción.
- **R5**: Given `claude` está presente en PATH en este entorno, When se llama
  `ClaudeCodeAdapter().detect()` sin mocks, Then `available=True` y `exit_code` de `claude
  --version` fue `0`.
- **R6**: Given se importa `tools.providers`, When se inspecciona `PROVIDER_REGISTRY`, Then
  contiene exactamente las claves `claude_code`, `codex`, `gemini`, `grok`, cada una mapeada a una
  instancia de su adapter correspondiente.
- **R7**: Given se corre `python -m tools.harmessi providers list --json`, When se parsea la
  salida como JSON, Then es una lista con 4 objetos, uno por `provider_id`.
- **R8**: Given se corre `python -m pytest tools/providers/tests tools/harmessi/tests`, When
  termina la corrida, Then todos los tests nuevos pasan (verificación real la hace el Lead, ver
  `tasks.md`).

## Unidad de análisis / grain (condicional — data_understanding, feature_engineering, modeling)
No aplica — este cambio no involucra un dataset, split temporal ni modelo; es infraestructura del
harness (adapters de proveedor).

## Cutoff / information boundary (condicional — feature_engineering, data_preparation, modeling)
No aplica — mismo motivo que arriba.

## Baseline (condicional — modeling)
No aplica — mismo motivo que arriba.

## Métrica primaria (condicional — modeling, evaluation)
No aplica — mismo motivo que arriba.

## Métricas secundarias (opcional)
No aplica — mismo motivo que arriba.

# Diseño — 20260917-multi-provider-adapters

## Decisión metodológica/técnica
Contrato neutral vía `subprocess` + CLI nativa por proveedor (nunca SDKs/APIs con key), siguiendo
los principios del roadmap "subscription-first" y "usar CLIs nativas". Cada adapter resuelve
detección (`shutil.which` + `--version`, sin intentar instalar) e invocación (`subprocess.run` con
los flags reales de cada CLI cuando se pudieron verificar, o el modo no interactivo documentado
públicamente cuando no, dejándolo explícitamente marcado como no verificado). La clasificación de
error de disponibilidad/cuota vs. semántico/de código vive en una única función de `core.py`
(`classify_availability_error`), heurística sobre texto de `stderr`, para que Change 3 (fallback)
tenga una sola fuente de verdad y no cada adapter reinvente su propio criterio.

## Target (condicional — feature_engineering, modeling)
No aplica — no hay target de datos en este cambio.

## Features permitidas/prohibidas (condicional — feature_engineering)
No aplica — no hay features de datos en este cambio.

## Estrategia de split/validación (condicional — holdout involucrado, modeling, evaluation)
No aplica — no hay split de datos ni holdout de datos en este cambio.

## Leakage risks (condicional — feature_engineering, data_preparation, modeling)
No aplica en el sentido de anti-leakage de datos de `CLAUDE.md`. Riesgo análogo considerado: que
`classify_availability_error` sea usada más adelante (Change 3) para encubrir errores
semánticos/de código como si fueran de disponibilidad. Mitigado dejando la función explícitamente
documentada como heurística best-effort y con un criterio de clasificación conservador: solo
clasifica como disponibilidad/cuota patrones de texto inequívocamente asociados a esas causas; todo
lo demás cae en `None`.

## Reproducibilidad (opcional — solo si se desvía del default: RANDOM_STATE fijo, .venv)
No aplica — no hay aleatoriedad ni `RANDOM_STATE` involucrado; los adapters son deterministas dado
el mismo comando y el mismo estado de la CLI externa.

## Alternativas descartadas
1. **Usar los SDKs Python oficiales de cada proveedor** (Anthropic SDK, OpenAI SDK,
   `google-generativeai`, xAI SDK). Descartado porque el roadmap exige explícitamente CLIs nativas
   y "subscription-first" (los SDKs suelen requerir API key de pago por token, no la suscripción de
   la CLI) y porque agregar 4 SDKs como dependencias nuevas sería una decisión de dependencia
   relevante (condición STOP del roadmap) sin necesidad real todavía.
2. **Un único adapter genérico parametrizado por flags de configuración**, en vez de una clase por
   proveedor. Descartado porque cada CLI tiene su propio vocabulario de flags y formato de salida;
   mezclarlos en un único módulo va contra "adapters finos" y core neutral, y dificultaría degradar
   un proveedor sin afectar a los demás.

## Riesgos
1. La heurística de `classify_availability_error` es best-effort sobre texto de `stderr`, puede
   tener falsos negativos/positivos. Mitigado documentándola como tal y no usándola todavía para
   ninguna decisión automática (eso es Change 3, con más evidencia disponible para ese momento).
2. Los flags de invocación de `codex`/`gemini`/`grok` no están verificados contra la CLI real (no
   instalada en este entorno). Mitigado dejándolo explícito en el código y en este documento; el
   contrato de detección (la parte crítica y verificable sin la CLI instalada) sí está probado con
   tests reales vía `monkeypatch`.
3. El campo `InvocationRequest.role` y `ProviderAdapter.translate_role()` están declarados en el
   contrato pero sin uso real en este Change (ningún adapter lo overridea, ningún caller lo lee más
   allá de pasarlo). Es deliberado: es el placeholder de contrato para Change 2
   (`provider-routing`), que sí necesitará rutear por rol. No es un olvido de esta implementación.

## Aprobación humana
Ver `proposal.md`, sección "Aprobación" (no se duplica acá).

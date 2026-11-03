# Diseño — 20260917-cross-provider-hardening

## Decisión metodológica/técnica

Verificación en dos niveles, complementarios y ambos necesarios (ninguno reemplaza al otro):

1. **Estructural/AST** (`tools/tests/test_v05_core_neutrality.py`): confirma que el core de v0.5
   no depende de qué proveedor esté instalado en el entorno -- escanea imports de nivel de módulo
   (mismo patrón ya validado en `tools/tests/test_architecture_boundaries.py`, v0.4 Change 3) y
   literales de código relevantes, no ejecuta nada. Corre igual con 0 o 4 CLIs instaladas.
2. **Contractual paramétrico** (los otros 3 archivos): confirma que el comportamiento observable
   es idéntico para los 4 `provider_id` reales, usando `FakeAdapter`s/`monkeypatch` sobre
   `shutil.which`/`subprocess.run` (mismo criterio que Changes 0 y 3) -- sin costo real, sin
   depender de qué esté instalado.

Ningún smoke test real nuevo contra Codex/Gemini/Grok: no están instalados en este entorno y no se
fabrica disponibilidad. El smoke real de `claude_code` (`test_claude_code_detect_real`,
`TestClaudeCodeInvokeArmadoComando`) ya está cubierto por Changes 0/1/3 -- no se repite acá por
eficiencia; `verification.md` documenta la matriz de cobertura real resultante
(`claude_code=REAL`, `codex/gemini/grok=N/A no instalados`), a completar por el Lead tras correr
las 4 suites nuevas.

## Target (condicional — feature_engineering, modeling)

No aplica.

## Features permitidas/prohibidas (condicional — feature_engineering)

No aplica.

## Estrategia de split/validación (condicional — holdout involucrado, modeling, evaluation)

No aplica.

## Leakage risks (condicional — feature_engineering, data_preparation, modeling)

No aplica -- no hay dataset ni target de un proyecto DS involucrado en este Change.

## Reproducibilidad (opcional — solo si se desvía del default: RANDOM_STATE fijo, .venv)

No aplica: los 4 archivos de test son deterministas por construcción (sin aleatoriedad, sin
dependencia de red ni de CLIs externas reales), no requieren `RANDOM_STATE`.

## Alternativas descartadas

1. **Instalar Codex CLI, Gemini/Antigravity y Grok CLI en este entorno para lograr smoke test real
   de los 4 proveedores.** Descartado: prohibido explícitamente por las reglas de autonomía del
   usuario ("NO instales automáticamente Codex CLI, Gemini/Antigravity, Grok CLI ni ninguna otra
   herramienta") y fuera del alcance de un Change de hardening/verificación, que no debe requerir
   nueva infraestructura para poder verificar.
2. **Simular un smoke test "real" con un fake disfrazado de CLI real (p. ej. un script de PATH que
   imite la salida esperada de `codex exec`).** Descartado: sería inventar disponibilidad y
   fabricar una señal de verificación falsa -- exactamente lo que `classify_availability_error` y
   el criterio general del proyecto ("ante la duda, `False`, nunca inventar disponibilidad de una
   capacidad no verificada", `tools/providers/core.py`) prohíben. Un fake de este tipo no puede
   probar nada sobre el formato de salida REAL de esas CLIs, solo sobre lo que el propio Change ya
   asume -- test sin valor añadido, riesgo de falsa confianza.

## Riesgos

- Los tests de paridad con `FakeAdapter`s/`monkeypatch` no pueden detectar una incompatibilidad
  real de FORMATO de salida de una CLI no instalada -- por ejemplo, si `codex exec` en la
  realidad no devolviera exactamente lo que `tools/providers/codex.py` asume (JSON vs texto plano,
  flags distintos a `exec`, etc.), ningún test de este Change lo detectaría, porque el adapter en
  sí (`codex.py`, `gemini.py`, `grok.py`) ya está marcado en su propio docstring como "no verificado
  contra la CLI real en este entorno" desde Change 0. Esta limitación queda documentada
  explícitamente acá, no resoluble sin acceso real a esas CLIs -- si en el futuro se instala
  alguna, corresponde una verificación de smoke real puntual (fuera del alcance actual).
- El escaneo AST de neutralidad del core (R1) es preciso solo hasta donde alcanza un análisis
  sintáctico de nivel de módulo: no detecta, por ejemplo, un import diferido (`import` dentro de
  una función) de un módulo de adapter concreto dentro de un `core.py` -- mismo límite deliberado
  ya documentado en `tools/tests/test_architecture_boundaries.py` para el boundary Core/Adapter de
  `ARCHITECTURE.md`. Si aparece un caso así en el futuro, se documenta en prosa como excepción,
  igual que los dos casos ya registrados en ese archivo (`pathguard.py`, `launcher_common.py`).

## Aprobación humana

Ver `proposal.md`, sección "Aprobación" -- registro único por Change, no se duplica acá.

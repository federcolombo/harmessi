# Verificación — 20260917-cross-provider-hardening

## Evidencia obtenida

- **Regresión, 4 suites nuevas**: `.venv/Scripts/python.exe -m pytest tools/tests/test_v05_core_neutrality.py tools/providers/tests/test_contract_parity.py tools/fallback/tests/test_cross_provider_parity.py tools/routing/tests/test_cross_provider_parity.py -q` → `40 passed` en `0.53s`.
- **Regresión, suites afectadas de Changes 0-3**: `.venv/Scripts/python.exe -m pytest tools/providers/tests tools/routing/tests tools/fallback/tests tools/harmessi_bench/tests -q` → `123 passed, 8 subtests passed` en `1.36s` -- 0 regresiones.
- **Regresión completa, `tools/tests`** (incluye la suite de dsguard/core y la nueva `test_v05_core_neutrality.py`): `.venv/Scripts/python.exe -m pytest tools/tests -q` → `629 passed, 2 skipped, 32 subtests passed` en `700.57s` (0:11:40) -- consistente con el baseline previo de 625 passed + 4 tests nuevos de neutralidad.
- **Tras el fix de reviewer** (que agregó 1 test nuevo a `tools/fallback/tests/test_cross_provider_parity.py`, sin tocar código de producción): `.venv/Scripts/python.exe -m pytest tools/fallback/tests -q` → `29 passed` en `0.31s` (era 28 antes del fix, +1 test nuevo).
- **Reviewer, ronda 1** (`data-science-reviewer`), con foco en genuinidad de la "paridad" y precisión del escaneo AST: confirmó explícitamente que la paridad entre los 4 providers es GENUINA en los 3 archivos de paridad (cada caso paramétrico atraviesa código de producción real con un dato distinto, no es decorativo), que la asimetría de cobertura de Change 0 (claude_code vs los otros 3) quedó cerrada genuinamente, y que los tests de fallback/routing incluyen verificación de LECTURA de código fuente (no solo de comportamiento) confirmando ausencia de literales de `provider_id` reales en la lógica. Sobre el escaneo AST de `test_v05_core_neutrality.py`: confirmó que escanea solo imports de nivel de módulo (límite documentado y aceptado, mismo patrón que `test_architecture_boundaries.py` de v0.4, sin gap real hoy porque ningún `core.py` tiene imports diferidos de adapters/subprocess), y que el chequeo de literales "claude" SÍ detecta apariciones dentro de f-strings (`ast.JoinedStr`), descartando la sospecha inicial de un bypass ahí. 1 hallazgo "importante": el test de opacidad de `role` en fallback solo verificaba comportamiento, no ausencia de literal en el código fuente (asimetría con la verificación de `provider_id`, que sí tenía ambas capas). 4 hallazgos "menor": límite de escaneo a nivel de módulo (documentado, aceptado, sin gap real); posible solapamiento de cobertura con `test_adapters.py` de Change 0 (no es un defecto); discrepancia entre `spec.md` (describía un análisis "sensible a contexto") y la implementación real (marca cualquier literal "claude" sin distinguir contexto).
- **Fixes aplicados** (única reinvocación correctiva del Change, cuenta 1 de 2 del contrato de autonomía): agregado `test_fallback_core_no_compara_role_contra_ningun_valor_conocido` en `test_cross_provider_parity.py` (fallback), simétrico al test ya existente de `provider_id`, confirmando por lectura de fuente que `tools/fallback/core.py` no compara contra ningún valor de rol conocido (`writer`/`reviewer`/`metodologo`); `spec.md` corregido para describir el comportamiento real del escaneo de literales (sin distinción de contexto, trade-off explícito de falso positivo aceptable/falso negativo no). Ningún código de producción fue tocado en todo el Change (ni en la implementación original, ni en el fix) -- consistente con el mandato del roadmap de "no agregar features nuevas... salvo fixes necesarios para compatibilidad real", y en este caso no se descubrió ninguna incompatibilidad real que ameritara un fix de producción.
- **Matriz de cobertura de smoke por adapter** (documentada, no fabricada -- ningún smoke nuevo se ejecutó en este Change, se consolida la evidencia ya real de Changes 0/1/3):

  | Provider | Smoke real ejecutado | Evidencia |
  |---|---|---|
  | `claude_code` | SÍ, real, múltiples veces | Change 0 (`claude -p` directo), Change 1 (`harmessi-bench run` 3/3 escenarios), Change 3 (`harmessi fallback invoke` real, fallback exitoso a este provider) |
  | `codex` | N/A -- CLI no instalada en este entorno | Detección limpia confirmada real en Change 0/3/4 (`available=False`, sin intento de instalación); invocación (`codex exec`) sigue sin verificar contra un binario real |
  | `gemini` | N/A -- CLI no instalada en este entorno | Igual que `codex`: detección limpia real, invocación (`gemini -p`) sin verificar |
  | `grok` | N/A -- CLI no instalada en este entorno | Igual que `codex`/`gemini`: detección limpia real, invocación (`grok <prompt>`) sin verificar |

- **Alcance**: `python tools/ds_guard.py status --change-id 20260917-cross-provider-hardening --json` → `"fuera_de_alcance": []`.
- **Privacidad**: no aplica un sweep dedicado (contenido genérico de tests); el sweep transversal obligatorio es Change 5.
- **Cero dependencias nuevas ni código de producción modificado**: confirmado -- este Change es exclusivamente `tools/tests/`+`tools/*/tests/` nuevos.

## Fingerprint de dataset/artefacto

No aplica -- cambio de verificación/hardening del harness, no involucra datos de un proyecto DS.

## Diferencias contra la spec

Ninguna respecto a R1-R4, salvo la corrección de redacción de R1 ya aplicada como parte del fix del reviewer (ver Evidencia obtenida).

## Limitaciones

1. El escaneo AST de `test_v05_core_neutrality.py` solo cubre imports de nivel de módulo -- un import diferido dentro de una función escaparía la detección (límite compartido con `test_architecture_boundaries.py` de v0.4, sin gap real hoy).
2. Sin verificación real de las CLIs de `codex`/`gemini`/`grok` -- sus comandos de invocación siguen siendo best-effort, no confirmados contra binarios reales (limitación heredada de Change 0, no resuelta ni pretendida resolverse en este Change, ver `design.md`).
3. Posible solapamiento de cobertura entre `tools/providers/tests/test_contract_parity.py` (Change 4) y `tools/providers/tests/test_adapters.py` (Change 0) para los escenarios de `codex`/`gemini`/`grok` sin CLI -- no es un defecto, ambos test suites siguen siendo válidos y deterministas, pero no se consolidaron en un único archivo (decisión de mantener Change 0 y Change 4 como unidades de trabajo separadas y no reabrir Change 0 ya cerrado).

## Pendientes derivados

Ninguno bloqueante. Las 3 limitaciones de arriba quedan como deuda documentada para v0.6+ (verificación real de más de un provider) y para el sweep de privacidad transversal de Change 5.

## Resultado final

**Change 4 (cross-provider-hardening) completo: 4 suites de test nuevas (neutralidad estructural del core vía AST, paridad de contrato de los 4 adapters, paridad de fallback entre los 4 provider_id, paridad de routing entre los 4 provider_id) implementadas sin tocar ningun codigo de produccion, revisadas (1 ronda, 1 hallazgo importante + 4 menores, todos resueltos o aceptados como limitacion documentada) y verificadas (792 tests totales entre las 4 suites nuevas + regresion de Changes 0-3 + regresion completa de tools/tests, 0 regresiones); cobertura de smoke real documentada honestamente (claude_code real, codex/gemini/grok N/A por ausencia de CLI, sin fabricar disponibilidad); listo para cierre SDD y commit local.**

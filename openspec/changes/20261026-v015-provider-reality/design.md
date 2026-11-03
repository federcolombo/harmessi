# Diseño — 20261026-v015-provider-reality

## Decisión metodológica/técnica
- D1. Matriz en `docs/providers.md` (fuente publicada) con niveles ordenados: detected < contract-tested < smoke-tested < live-validated. Registro de evidencia live con fecha, OS, versión de CLI, comando exacto y resultado. La evidencia es de host único; no se generaliza. Los providers sin CLI instalada (codex, gemini, grok) quedan `contract-tested`: sus adapters declaran no haberse verificado contra la CLI real y no se afirma más. No hay adapter `antigravity`; Gemini/Antigravity se cubre por `gemini`.
- D2. `SOPORTE_DECLARADO`: `claude_code` → `live-validated`, con texto de evidencia que remite al registro de `docs/providers.md`. Test `test_v015_provider_matrix.py` (parseo de la tabla y del registro en markdown): (a) la tabla coincide con `SOPORTE_DECLARADO`; (b) todo nivel ≥ smoke-tested/live-validated tiene registro coincidente (provider, nivel); (c) sin registro no hay nivel por encima de `contract-tested`. Un test negativo con una tabla sintética prueba que el chequeo detecta el sobreventa. Esto ancla "no sobrevender" a un chequeo mecánico, no a convención.
- D3. B-10: `is_fallback_eligible` ya es la única decisión (`tools/fallback/core.py` L37-41, uso en L128). Se agregan tests (fallback core, paridad cross-provider, routing) y documentación. Si algún test revela un comportamiento distinto al documentado, se reporta al Lead: no se cambia `core.py` de fallback, que no está en el alcance. `provider_available` sigue informativo.
- D4. B-09: en `_chequeo_invoke_contrato` (L346-351) se reconoce también un elemento `-...=modelo-sintetico`. Cambio mínimo: se busca el índice del modelo como elemento exacto con flag previo, o como elemento que empieza por `-` y termina en `=` + `_MODELO_SINTETICO`. El resto de las evasiones se documenta como límite heurístico (el chequeo ya se declara no exhaustivo); implementarlas no es barato y se difiere.
- D5. Docstring de `claude_code.py` L3: pasa a describir la versión validada en vivo (`2.1.310`, 2026-10-26, host único) sin afirmar compatibilidad de otras versiones. Se autoriza `tools/providers/claude_code.py` solo para el docstring. El fixture `version="2.1.274"` en `tools/harmessi/tests/test_providers_cli.py` es un dato sintético de test y no se toca.
- D6. Provider-neutrality real: los 4 adapters implementan el mismo contrato `ProviderAdapter` y pasan conformance con dobles; solo Claude Code está validado en vivo; el fallback solo opera por quota/availability. T2 = POST-v1. Razón: requiere providers instalados y credenciales para validar equivalencia de comportamiento, fuera de lo verificable en este entorno; v1 no lo exige, porque su criterio es una matriz sin soporte superior a la evidencia.
- D7. Inventario: notas de `provider-adapter` (y `cli-providers-conformance` si cabe) reflejan el estado de soporte, con remisión a `docs/providers.md`. No cambia `clase`.

## Target (condicional — feature_engineering, modeling)
No aplica.

## Features permitidas/prohibidas (condicional — feature_engineering)
No aplica.

## Estrategia de split/validación (condicional — holdout involucrado, modeling, evaluation)
No aplica.

## Leakage risks (condicional — feature_engineering, data_preparation, modeling)
No aplica.

## Reproducibilidad (opcional — solo si se desvía del default: RANDOM_STATE fijo, .venv)
Sin aleatoriedad. La evidencia live es de host único y no reproducible en CI: se registra con comando exacto para que pueda repetirse. Los tests nuevos no invocan CLIs reales; usan dobles y parseo de markdown.

## Alternativas descartadas
- Declarar `live-validated` sin registro en la doc: descartado; es sobreventa no verificable.
- Instalar codex/gemini/grok para validarlos: fuera de alcance por decisión (sin instalaciones ni credenciales).
- Implementar detección de `communicate`/`os.system`/from-imports/`partial`: costoso, y el chequeo es heurístico por diseño; se documenta el límite.
- Crear un adapter `antigravity`: no hay CLI ni evidencia; se cubre por `gemini`.
- Hacer un test live en CI: no reproducible; la evidencia vive como registro.
- T2 en v0.15: descartado, POST-v1 (ver D6).

## Riesgos
- La tabla markdown puede romper el parseo del test si cambia el formato: el test usa un formato estricto y mensajes claros.
- La evidencia de host único puede interpretarse como soporte general: mitigado con la declaración explícita de límites en la doc y en la `evidencia`.
- Tests de smoke v0.13/v0.14 pueden afirmar los 4 `contract-tested`: se ajustan (por eso están en el alcance).
- La versión de CLI cambia sin que el registro se actualice: el registro es histórico, no una promesa vigente.
- Si los tests de fallback revelan un desvío en `tools/fallback/core.py`: se devuelve al Lead; ese archivo no está en el alcance.

## Aprobación humana
<!-- El registro de aprobación (usuario, fecha, alcance, versión de artefactos, cita) es único
por cambio y vive en la sección "Aprobación" de proposal.md — no se duplica acá. -->

# Diseño — 20260914-lifecycle-migration-and-kdd-repoint

## Decisión metodológica/técnica
1. **Arquitectura de 3 módulos (ajuste del usuario tras revisión)**: `lifecycle.py` (Change 1, permanece 100% neutral — no sabe que existe legacy) ← `kdd_compat.py` (NUEVO — conoce AMBAS ontologías: catálogo legacy, mapeo, merge, migración, y las implementaciones reales repuntadas de las operaciones que antes vivían en `kdd.py`) ← `kdd.py` (se convierte en adaptador público delgado: re-exporta `ETAPAS`/`ETAPAS_FUTURAS` desde `kdd_compat.py`, define `KddEstadoError`, sus funciones son wrappers que delegan en `kdd_compat.py` y envuelven excepciones en el borde). Dependencia unidireccional, sin ciclos.

**Problema real encontrado y resuelto**: si el catálogo legacy (`ETAPAS`) permanece en `kdd.py` mientras `kdd_compat.py` lo necesita para construir el mapeo, y `kdd.py` a su vez necesita importar `kdd_compat.py` para delegarle la lógica, se produce un import circular (`kdd.py` → `kdd_compat.py` → `kdd.py`). Resolución: el catálogo legacy (`ETAPAS`, `ETAPAS_FUTURAS`, la tabla de transiciones válidas `_TRANSICIONES_VALIDAS_ETAPA`) se muda a `kdd_compat.py` — que entonces solo depende de `lifecycle.py`, nunca de `kdd.py`. `kdd.py` re-exporta esas constantes (`from .kdd_compat import ETAPAS, ETAPAS_FUTURAS`), de modo que `kdd.ETAPAS` sigue siendo válido para todo el código externo (`ds_guard.py`, `dsguard/decision.py`) sin ningún cambio — el contrato público no se rompe, solo cambia dónde vive la definición real.

Por qué el módulo separado es preferible a concentrar todo en `kdd.py` (como se había propuesto originalmente): evita que `kdd.py` mezcle storage-adapter + motor de migración + mapeos + criterios detectables + compatibilidad en un solo archivo creciente — cada módulo tiene una responsabilidad clara y `kdd.py` queda genuinamente delgado (adapter + criterios detectables, que son una preocupación de UX del comando `status`, no de storage).

2. **Manejo de excepciones**: `lifecycle.LifecycleEstadoError` (nueva, de Change 1) NO se propaga cruda hacia `ds_guard.py` desde las funciones repuntadas de `kdd.py` — se captura y se re-envuelve como `kdd.KddEstadoError(str(e))` antes de propagar. Razón: `tools/ds_guard.py` ya tiene `except kdd.KddEstadoError` en varios `cmd_kdd_*`/`cmd_transition`; si las funciones repuntadas empezaran a levantar `LifecycleEstadoError` sin envolver, esos `except` dejarían de capturarla y el CLI crashearía sin mensaje limpio en vez de devolver el error controlado de siempre. Alternativa descartada: actualizar cada `except` de `ds_guard.py` para además atrapar `LifecycleEstadoError` — más puntos de cambio, mismo resultado; envolver en el borde de `kdd.py` es más contenido y menos propenso a que un `except` quede desactualizado en el futuro.

3. **Regla de transición dual (CRISP-DM + KDD simultáneos)**: `kdd_transition(repo_root, etapa_legacy, hacia, ...)` repuntado transiciona `crispdm.fases[fase]` y, si `MAPEO_LEGACY_A_KDD[etapa_legacy]` no es `None`, también `kdd.pasos[paso]`, al mismo valor `hacia`, en una sola escritura atómica. Nunca toca `mlops` (ninguna etapa legacy tiene un mapeo automático a una capacidad MLOps específica — ver punto 5). Si dos etapas legacy distintas comparten el mismo destino CRISP-DM pero difieren en KDD (`data_preparation`/`feature_engineering`, ambas → `crispdm.fases.data_preparation`, pero `preprocessing`/`transformation` respectivamente), cada llamada de transición escribe directamente el paso pedido y luego recalcula el `estado` de `crispdm.fases.data_preparation` vía roll-up (`calcular_estado_fase`, ver punto 9) sobre el estado actual de ambos pasos — ya no es "último write gana" sobre la fase (ver punto 9 para el reemplazo de esta regla, ajuste del usuario tras revisión).

4. **`evaluation`/`interpretation` se vuelven sinónimos funcionales post-migración**: ambos legacy names apuntan al mismo destino (`crispdm.evaluation` + `kdd.interpretation_evaluation`) — consecuencia directa, ya aprobada, de plegar Interpretation dentro de Evaluation (Change 1). `kdd status`/`kdd transition` los tratan como intercambiables después de migrar. Documentado explícitamente para que no se lea como bug.

5. **MLOps NO se auto-puebla desde legacy**: las 3 etapas "MLOps-flavored" (`production_readiness`/`deployment`/`monitoring`) migran su evidencia/changes únicamente a su fase CRISP-DM 1:1 correspondiente. Ninguna capacidad específica de `mlops.*` (16 en total) recibe datos automáticamente. Razón: en v0.2 cada una de esas 3 etapas era una sola entrada coarse; el nuevo modelo MLOps tiene hasta 7 capacidades por tier — inventar a cuál de ellas correspondía la evidencia legacy sería una atribución arbitraria no respaldada por los datos originales (que nunca distinguieron "esto es sobre packaging" vs "esto es sobre CI/CD"). Decidir esa correspondencia, si hace falta, es trabajo humano/de un change posterior — no una heurística de migración.

6. **Manifest**: se agrega la entrada faltante de `lifecycle.py` (bug real encontrado, mismo patrón que el blocker histórico de `decision.py`), más la entrada nueva de `kdd_compat.py` (punto 1), y se evalúa (no obligatorio, ver Riesgos) agregar `openspec/lifecycle/` a `EXCLUSIONES_PERMANENTES` por simetría con `openspec/kdd/` — refuerzo defensivo, no corrige ningún bug activo (nada en `MANIFEST` apunta ahí hoy).

9. **Roll-up de fase CRISP-DM (ajuste del usuario, K4)**: `lifecycle.py` gana una función pura nueva, `calcular_estado_fase(estados_pasos: list) -> str`: todos `no_iniciada`→`no_iniciada`; todos `cerrada`→`cerrada`; cualquier mezcla→`en_progreso`. No requiere conocimiento legacy (opera solo sobre el vocabulario `ESTADOS_VALIDOS` de `lifecycle.py`), así que no compromete la neutralidad del módulo — es simplemente lógica de dominio CRISP-DM/KDD que Change 1 no necesitó porque no había transición todavía. Reemplaza mi diseño original de merge para fases con pasos subordinados: en vez de calcular el estado de la fase de forma independiente a partir de "la etapa legacy más avanzada que converge ahí", la fase SIEMPRE deriva su estado de sus pasos KDD subordinados vía roll-up — tanto en migración (después de migrar cada paso) como en transición en vivo (después de escribir el paso transicionado, se recalcula la fase). Para las 4 fases sin pasos subordinados (`business_understanding`/`production_readiness`/`deployment`/`monitoring`), no hay roll-up: la fase se escribe 1:1 directo, igual que antes. La regla de "más avanzado gana" (`cerrada`>`en_progreso`>`no_iniciada`) queda reservada exclusivamente para el caso de convergencia AL MISMO paso KDD (`evaluation`+`interpretation`→`interpretation_evaluation`), que es un nivel distinto del roll-up fase-desde-pasos y solo ocurre en migración (post-migración son sinónimos sobre una entrada ya unificada).

## Target (condicional — feature_engineering, modeling)
No aplica — cambio de arquitectura/tooling del harness, no de datos de un proyecto DS.

## Features permitidas/prohibidas (condicional — feature_engineering)
No aplica — cambio de arquitectura/tooling del harness, no de datos de un proyecto DS.

## Estrategia de split/validación (condicional — holdout involucrado, modeling, evaluation)
No aplica — cambio de arquitectura/tooling del harness, no de datos de un proyecto DS.

## Leakage risks (condicional — feature_engineering, data_preparation, modeling)
No aplica — cambio de arquitectura/tooling del harness, no de datos de un proyecto DS.

## Reproducibilidad (opcional — solo si se desvía del default: RANDOM_STATE fijo, .venv)
No aplica — cambio de arquitectura/tooling del harness, no de datos de un proyecto DS.

## Alternativas descartadas
- Reescribir `kdd.py` desde cero en vez de adaptarlo in-place — rechazada: rompería el contrato público (`test_kdd.py` y `ds_guard.py` llaman sus funciones directamente) sin necesidad; adaptar in-place preserva la firma y minimiza el diff.
- Poner el mapeo/migración en `lifecycle.py` — rechazada, ver punto 1.
- Auto-poblar capacidades MLOps específicas desde legacy con alguna heurística (ej. `deployment` → `mlops.operations.deployment`) — rechazada, ver punto 5: es una atribución no respaldada por los datos legacy reales.
- Agregar `ds_guard lifecycle status`/`transition` de propósito general en este change — rechazada: no fue pedido, el roadmap ya lo ubica como change posterior (`unified-status-surface`), y agregarlo ahora expande el alcance sin necesidad demostrada.
- Actualizar `except kdd.KddEstadoError` en cada call site de `ds_guard.py` para además atrapar `LifecycleEstadoError` — rechazada a favor de envolver en el borde (punto 2).
- "Última escritura gana" entre fase CRISP-DM y sus pasos KDD subordinados — rechazada por el usuario (K4): puede dejar la fase en un estado inconsistente con sus propios pasos según el orden de ejecución de comandos legacy. Reemplazada por el roll-up determinista (punto 9).

## Riesgos
- `.claude/skills/lead-data-scientist/kdd.md` y su template (`kdd.md.tmpl`) reciben una actualización FACTUAL MÍNIMA en este change (ver `proposal.md` § Alcance punto 8) — no el rewrite completo de Lead methodology awareness, que sigue siendo un change posterior. Riesgo residual: `decision-ledger.md`/`decision-ledger.md.tmpl` NO se tocan (no describen el modelo de etapas de la misma forma que `kdd.md`, y no fueron pedidos) — quedan sin actualizar hasta el change de Lead-awareness, sin que eso implique una afirmación falsa sobre el storage.
- Comportamiento sinónimo `evaluation`/`interpretation` puede sorprender a alguien que no leyó este design — mitigado documentándolo en el docstring de `kdd.py` y en la salida de `kdd status`.
- Test suite existente (`test_kdd.py`, `test_decision.py`, `test_remediation.py`) asume storage legacy directo — requiere reescritura sustancial para seguir siendo válida post-repunte; riesgo de regresión si algún caso no se migra 1:1. Mitigación: cobertura exhaustiva nueva (ver `tasks.md`), corridos contra el CLI real (mismo patrón `subprocess` que ya usa `test_kdd.py`).
- Riesgo resuelto: el roll-up (punto 9) ya gobierna la consistencia fase↔pasos, tanto en migración como en vivo.

## Aprobación humana
Ver `proposal.md` § Aprobación.

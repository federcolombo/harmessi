# Spec — 20260915-mlops-foundations-experiment

## Requisitos
Remitir a `proposal.md § Alcance` y `design.md`. Se dejan explícitas las 4 reglas de decisión
(Given/When/Then detallado en Criterios de aceptación abajo) y el mapeo de
`_CODE_A_CAPABILITY`:
```python
_CODE_A_CAPABILITY = {
    "MLOPS-FOUNDATIONS-REPRODUCIBILIDAD": "reproducibilidad",
    "MLOPS-FOUNDATIONS-VERSIONADO": "versionado",
    "MLOPS-FOUNDATIONS-LINEAGE": "lineage",
    "MLOPS-FOUNDATIONS-ARTIFACTS": "artifacts",
}
```
Y el código informativo `MLOPS-FOUNDATIONS-PROJECT-STAGE` (siempre PASS o N/A, nunca FAIL salvo
`technical_error` por corrupción de `project.json`).

## Criterios de aceptación
<!-- checklist o Given/When/Then, verificables -->

*Resolución de `project_stage`:*
- `.harmessi/project.json` no existe → los 4 checks de capability devuelven `N/A` con mensaje que
  menciona `ds_guard project init`; `MLOPS-FOUNDATIONS-PROJECT-STAGE` es `N/A` (no
  `technical_error` — es un estado legítimo, no un error).
- `.harmessi/project.json` existe pero corrupto (JSON inválido o schema desconocida) →
  `evaluar_foundations` propaga esto como `technical_error` (vía `checks.resultado_de_excepcion`,
  mismo patrón que `doctor._ejecutar_check_con_dato`) — no crashea, se refleja como
  `CheckResult(FAIL, kind="technical_error")`.
- `project_stage == "discovery"` → los 4 checks de capability devuelven `N/A` con mensaje "no
  aplica en discovery — los fundamentos MLOps aplican desde experiment" (mensaje DISTINTO al de
  "project.json no existe", para no confundir "elegí discovery a propósito" con "no configuré
  nada todavía").
- `project_stage ∈ {experiment, production_candidate, production}` → los 4 checks se evalúan con
  la lógica real (ver abajo). Ningún comportamiento especial adicional para
  `production_candidate`/`production` en este change (esa diferenciación es Change 6).

*`check_reproducibilidad`:*
- Working tree limpio + (sin `data/` con contenido O `data/` con contenido y evidencia de
  fingerprint en `.harmessi/profiles/*/profile.json`) + al menos un lockfile de entorno
  (`requirements-lock.txt`/`poetry.lock`/`Pipfile.lock`) presente → `PASS`.
- Cualquier combinación con working tree sucio, o `data/` con contenido sin fingerprint, o sin
  lockfile → `WARN`, mensaje lista específicamente qué falta.
- Nunca `FAIL` funcional en este change (solo `technical_error` si algo interno falla
  inesperadamente).

*`check_versionado`:*
- Sin `data/` con contenido, o `data/` con contenido y fingerprint presente → `PASS` (código
  siempre versionado por git, ya garantizado por el contexto de ejecución).
- `data/` con contenido sin fingerprint → `WARN`.

*`check_lineage`:*
- `openspec/lifecycle/state.json` no existe → `N/A` ("no existe todavía").
- Si existe → **siempre `WARN`** (nunca `PASS` en este change — no hay motor de lineage real; el
  mensaje debe explicar esto explícitamente y mencionar si hay evidencia indirecta vía pasos KDD
  con `evidencia`/`changes` no vacíos). Verificable con un test que confirma que NINGÚN input
  produce `PASS` para este check (salvo los casos N/A ya cubiertos).

*`check_artifacts`:*
- Al menos uno de {`.harmessi/profiles/*/profile.json` presente, `models/` con contenido,
  `reports/` con contenido} → `PASS`, mensaje lista qué se encontró.
- Ninguno presente → `WARN`.

*`evaluar_foundations`:*
- Nunca escribe en disco bajo ninguna circunstancia (verificable: bytes de
  `lifecycle/state.json`/`project.json` idénticos antes/después de llamarla, en cualquiera de los
  casos anteriores).
- Devuelve una lista que incluye el resultado informativo `MLOPS-FOUNDATIONS-PROJECT-STAGE` más
  los 4 resultados de capability, en ese orden.
- No falla nunca de forma cruda — cualquier excepción de un check individual se refleja como
  `technical_error`, sin detener la evaluación de los demás (mismo principio "check everything,
  report everything" de Change 4).

*`registrar_evidencia`:*
- Requiere que `openspec/lifecycle/state.json` ya exista — si no, `FileNotFoundError`/error
  claro, no lo crea.
- Para cada uno de los 4 resultados de capability (ignora `MLOPS-FOUNDATIONS-PROJECT-STAGE`, que
  no tiene slot en `mlops.foundations`), agrega exactamente un `{tipo: "check_snapshot", status,
  kind, message, utc}` a `evidencia[]` de esa capability, y actualiza `actualizado_utc`.
- **Nunca modifica el campo `estado`** de ninguna capability — permanece exactamente igual
  antes/después (verificable).
- Escritura atómica (mismo patrón que `lifecycle.escribir_estado`, sin duplicar lógica).
- Idempotente en el sentido de "no falla si se llama dos veces" — cada llamada simplemente AGREGA
  una entrada nueva a `evidencia[]` (append-only, no dedup necesario porque cada snapshot tiene
  su propio `utc`).

*CLI:*
- `ds_guard mlops status [--json]` — solo lectura, nunca escribe, exit code =
  `checks.exit_code(resultados)` (0 salvo `technical_error`).
- `ds_guard mlops record [--json]` — evalúa + persiste, exit code refleja si la persistencia tuvo
  éxito (además del resultado de los checks).

## Unidad de análisis / grain (condicional — data_understanding, feature_engineering, modeling)
No aplica — este change define checks genéricos reutilizables por cualquier proyecto, no analiza
un dataset concreto.

## Cutoff / information boundary (condicional — feature_engineering, data_preparation, modeling)
No aplica — no hay features ni target involucrados.

## Baseline (condicional — modeling)
No aplica — no hay modelo involucrado en este change.

## Métrica primaria (condicional — modeling, evaluation)
No aplica.

## Métricas secundarias (opcional)
No aplica.

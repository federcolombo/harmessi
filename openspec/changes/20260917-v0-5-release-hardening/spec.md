# Spec — 20260917-v0-5-release-hardening

## Requisitos

- **R1 — Versión consistente**: `tools/ds_init/version.py` (`HARNESS_VERSION`) y `CITATION.cff`
  (`version`, `date-released`) declaran `0.5.0` / fecha de hoy, y ninguna otra línea/anotación
  histórica de esos archivos fue tocada.
- **R2 — README con las 4 capacidades nuevas documentadas**: `README.md` describe, en la sección
  `## Commands`, `harmessi providers`, `harmessi routing`, `harmessi fallback` y `harmessi-bench`
  con el mismo nivel de detalle/tono que `harmessi doctor`/`ds_profile` (comando, qué hace, dónde
  persiste estado, limitaciones honestas), sin reordenar secciones existentes.
- **R3 — Privacidad transversal sin hallazgos nuevos**: un sweep sobre todo el working tree
  (`.py`/`.md`/`.json`/`.cff`) para nombres de clientes/proyecto (`AGD`, `UNCO-Intelligence`,
  `Model-churn`), rutas locales (`C:\Users\...`, `C:\Datos\...`) y el email del usuario no revela
  ninguna fuga real introducida por v0.5.
- **R4 — Regresión completa final (9 suites)**: `tools/tests`, `tools/harmessi/tests`,
  `tools/ds_init/tests`, `tools/ds_profile/tests`, `tools/dsimpact/tests`, `tools/providers/tests`,
  `tools/harmessi_bench/tests`, `tools/routing/tests`, `tools/fallback/tests` corren sin
  `failures` (skips documentados y ya conocidos, p. ej. dependencias de `pyarrow`, son aceptables).
- **R5 — Evals mínimas**: al menos 1 corrida real de `harmessi-bench run` contra el provider
  `claude_code` produce un `result.json` válido con escenarios que pasan.
- **R6 — Smoke cross-provider**: una matriz real de disponibilidad de los 4 `provider_id`
  (`claude_code`, `codex`, `gemini`, `grok`) vía `harmessi providers list`, documentando
  honestamente cuáles son N/A por ausencia de CLI real en este entorno.
- **R7 — Smoke routing/fallback**: al menos 1 demostración real de fallback genuino (un provider
  indisponible seguido de un fallback exitoso a otro), reusando el patrón ya probado en Change 3.
- **R8 — Backward compatibility + scratch installs**: al menos 2 instalaciones reales
  (`discovery` y `experiment`) confirman que v0.5 no rompió el comportamiento de instalación ya
  verificado en v0.4.
- **R9 — `harmessi doctor` final sin `[ERROR]`**: la corrida final de `harmessi doctor` sobre este
  propio repo no reporta ningún `[ERROR]` (WARN/N/A esperados están permitidos si ya lo estaban en
  v0.4).
- **R10 — `.ds_init/control.json` regenerado**: el `control.json` de este propio repo se regenera
  con `harness_version: "0.5.0"` y un `archivos[]` consistente con un scratch install fresco al
  mismo stage.
- **R11 — Reviewer transversal**: `data-science-reviewer` revisa el conjunto de los 5 Changes de
  v0.5 (no cada uno por separado), y sus hallazgos (si los hay) quedan resueltos o aceptados como
  limitación documentada antes del cierre.

## Criterios de aceptación

- **R1**: Given `tools/ds_init/version.py` y `CITATION.cff` antes del Change, When se aplican los
  cambios mecánicos de este Change, Then `HARNESS_VERSION == "0.5.0"`, `CITATION.cff:version ==
  0.5.0`, `CITATION.cff:date-released == "2026-09-17"`, y un `git diff` de ambos archivos muestra
  solo esas líneas modificadas.
- **R2**: Given el estado de `README.md` antes del Change, When se agregan las 4 subsecciones
  nuevas, Then `## Commands` contiene `harmessi providers`/`harmessi routing`/`harmessi
  fallback`/`harmessi-bench` con comando+explicación+limitaciones, y ninguna sección preexistente
  cambió de contenido u orden relativo.
- **R3**: Given el working tree completo de v0.5, When se corre un `grep` recursivo para los
  patrones de nombres de cliente/proyecto/rutas locales/email, Then no aparece ningún hallazgo real
  (los que aparezcan, si aparecen, son referencias al propio patrón de búsqueda, no una fuga).
- **R4**: Given las 9 suites listadas en R4, When se corren completas tras el cierre de
  implementación de este Change, Then el resultado es `0 failures` (skips documentados aceptables).
- **R5**: Given `tools/harmessi_bench/scenarios/examples.json` (u otro set de escenarios), When se
  corre `harmessi_bench.cli run --provider claude_code`, Then el `result.json` generado reporta al
  menos 1 escenario y ninguno con un error de ejecución no esperado.
- **R6**: Given los 4 adapters de `tools/providers/`, When se corre `harmessi providers list
  --json`, Then el resultado documenta `available=True` para `claude_code` y `available=False` (sin
  traceback) para los que no tengan CLI instalada en este entorno.
- **R7**: Given una política de routing con un provider primario indisponible y un
  `fallback_chain` con uno disponible, When se corre `harmessi fallback invoke`, Then el
  `FallbackOutcome` final reporta éxito con el segundo provider y ambos intentos (fallido y
  exitoso) quedan registrados como `HandoffRecord`.
- **R8**: Given un repo git temporal limpio, When se instala con `--stage discovery` y otro con
  `--stage experiment`, Then ambas instalaciones terminan sin error y con el comportamiento ya
  documentado en el hardening de v0.4 (mismos archivos base, mismo manejo de `ds_guard
  impact scan` degradado en `discovery`).
- **R9**: Given el estado final de este repo tras cerrar el Change, When se corre `harmessi
  doctor`, Then el conteo de `[ERROR]` es 0.
- **R10**: Given el `.ds_init/control.json` actual de este repo, When se regenera vía
  `control.regenerar_control`, Then `harness_version == "0.5.0"` y el conteo de `archivos[]`
  coincide con un scratch install fresco al mismo stage.
- **R11**: Given el diff acumulado de los 5 Changes de v0.5, When `data-science-reviewer` lo
  revisa como unidad, Then cualquier hallazgo queda resuelto o registrado como limitación explícita
  en `verification.md` antes de declarar `READY FOR v0.5.0 RELEASE`.

## Unidad de análisis / grain (condicional — data_understanding, feature_engineering, modeling)

No aplica — hardening de release del harness, no dataset/modelo de un proyecto DS.

## Cutoff / information boundary (condicional — feature_engineering, data_preparation, modeling)

No aplica — hardening de release del harness, no dataset/modelo de un proyecto DS.

## Baseline (condicional — modeling)

No aplica — hardening de release del harness, no dataset/modelo de un proyecto DS.

## Métrica primaria (condicional — modeling, evaluation)

No aplica — hardening de release del harness, no dataset/modelo de un proyecto DS.

## Métricas secundarias (opcional)

No aplica.

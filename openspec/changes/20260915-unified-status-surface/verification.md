# Verificación — 20260915-unified-status-surface

## Evidencia obtenida
Implementación bajo autonomía acotada autorizada por el usuario, en 1 delegación principal de
implementación (código + tests, resumida 4 veces por límite de turnos del subagente — no cuentan
como nuevas delegaciones) + 1 delegación de reviewer (resumida 1 vez) + 1 fix aplicado
directamente por el Lead (sin subagente adicional, hallazgo bien acotado):

- **`tools/dsguard/status.py`** (nuevo): `next_target`, 8 funciones de sección de solo lectura
  (`_seccion_project`, `_seccion_installation`, `_seccion_alignment`, `_seccion_lifecycle`,
  `_seccion_mlops_foundations`, `_seccion_mlops_evidencia`/`_seccion_mlops`, `_seccion_readiness`,
  `_seccion_harness`), `evaluar_status`, `formatear_texto`, `formatear_json`; imports perezosos
  opcionales de `tools.harmessi.doctor`/`tools.ds_init.legacy`, nunca a nivel de módulo.
- **`tools/ds_guard.py`**: `status --change-id` ahora opcional, bifurca a `cmd_status_unificado`
  cuando se omite; `--verbose` nuevo; la rama `--change-id` existente quedó intacta.
- **`tools/ds_init/manifest.py`**: entrada VERBATIM de `status.py`.
- **`tools/tests/test_status.py`** (nuevo, ~45 tests): cobertura completa de los criterios de
  aceptación de `spec.md`.
- **`tools/tests/test_manifest_dsguard_parity.py`**/**`tools/ds_init/tests/
  test_integracion_instalacion.py`**: extendidos.

El subagente implementador no encontró ninguna contradicción real entre `spec.md`/`design.md` y
el código existente. Decisiones de implementación propias documentadas (razonables, revisadas por
el Lead): forma dual de import perezoso (`from harmessi import doctor` / `from tools.harmessi
import doctor`, según contexto de invocación); `evaluar_status` no toma `verbose` (el dato
completo siempre vive en el dict, la proporcionalidad de presentación es responsabilidad de
`formatear_texto`); `readiness` incluye tanto un campo `status` enum como un `resumen` de texto;
`project_stage=None` tratado igual que `discovery` para proporcionalidad; el resultado
informativo `MLOPS-FOUNDATIONS-PROJECT-STAGE` se omite de `mlops.foundations` para no duplicar el
mismo dato que ya vive en la sección `project`.

**Reviewer (`data-science-reviewer`)**: sin hallazgos bloqueantes. 1 hallazgo **importante**: el
límite `K=5` de `harness.principales` (R11 de `spec.md`: "nunca la lista completa de Doctor salvo
--verbose") estaba definido (`_K_PRINCIPALES_HARNESS`) pero nunca aplicado — tanto el dict como
`formatear_texto` en modo compacto mostraban siempre la lista completa. Enmascarado en este repo
porque el baseline tiene coincidentemente 5 WARN (mismo valor que K). **Corregido**: se preserva
la lista COMPLETA en el dict (`evaluar_status`/`formatear_json`, mismo criterio que
`readiness.blocking`, que tampoco se trunca ahí), y se aplica el corte a K exclusivamente en
`formatear_texto` en modo compacto (idéntico patrón al ya usado para `readiness.blocking`), con
un mensaje "... (N más, usar --verbose)" cuando corresponde. Test nuevo:
`test_principales_truncado_a_K_en_modo_compacto_completo_en_verbose` (usa un doctor falso
mockeado con 8 WARN para ejercitar el corte real, algo que el baseline actual de este repo no
permitía probar por casualidad de conteo).

Verificación real ejecutada por el Lead (nunca por el subagente, que no tiene Bash):
- `tools/tests/`: primera corrida 496/496 OK (2 skipped, sin fixture bugs — primera vez en la
  serie de changes 6-8 que la implementación pasa limpio en el primer intento). Segunda corrida
  (tras el fix + test nuevo del reviewer): 497/497 OK.
- `tools/harmessi/tests/`: 82/82 OK, sin regresión (doctor.py no fue tocado).
- `tools/ds_init/tests/`: 112/112 OK, sin regresión.
- `harmessi doctor` sobre este repo, comparado byte a byte con `git stash` antes/después: el
  ÚNICO diff es `CORE-WORKING-TREE` (limpio → sucio, esperado, desarrollo activo sin commit).
  Antes: **26 OK, 5 WARN, 0 ERROR, 1 N/A** (coincide EXACTAMENTE con el baseline declarado por el
  usuario). Después: 25 OK, 6 WARN, 0 ERROR, 1 N/A (mismo total, un ítem migra de OK→WARN por el
  working tree sucio, nada más). **0 ERROR, 0 regresión real.**

## Fingerprint de dataset/artefacto (condicional — cambio sensible o reproducibilidad crítica)
No aplica.

## Diferencias contra la spec
Ninguna sustancial. El fix del reviewer es un endurecimiento de un requisito explícito (R11) que
no estaba correctamente aplicado, no un cambio de alcance.

## Limitaciones
`harness.disponible`/`installation.origen="inferido"` solo funcionan corriendo desde el checkout
fuente de Harmessi (donde `tools/harmessi/doctor.py`/`tools/ds_init/legacy.py` existen) —
limitación estructural real y preexistente (Doctor y `ds_init` nunca se instalan en proyectos
destino, confirmado desde Change 7), no introducida por este change; documentada explícitamente
en `design.md` punto 2 y reflejada honestamente en el output (`disponible=False` con mensaje
claro, nunca una aproximación falsa).

## Pendientes derivados
Ninguno bloqueante. `--json` de `status` queda explícitamente documentado como
experimental/interno (R14) — una futura CLI pública `harmessi status` (fuera de alcance de este
change) podría eventualmente estabilizar ese contrato.

## Resultado final
Todos los requisitos R1-R15 de `spec.md` implementados con evidencia real. Reviewer con 1
hallazgo importante, corregido y verificado con test dedicado. Regresión completa limpia
(497/497 + 82/82 + 112/112, baseline de doctor preservado exactamente). Change listo para cierre.

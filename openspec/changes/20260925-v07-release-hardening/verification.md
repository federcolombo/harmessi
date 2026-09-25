# Verificación — 20260925-v07-release-hardening

Evidencia real aportada por el Lead, ordenada por los requisitos de `spec.md`. Los números salen
de las corridas, no de memoria. Este `verification.md` cierra el ÚLTIMO Change de v0.7 y consolida
el conjunto completo (Changes 0-5).

## (a) Resumen de Changes 0-4 (citados, no repetidos en extenso)

- **Change 0 — `data-contracts-core`** (`openspec/changes/20260922-data-contracts-core/
  verification.md`): CERRADO. Suite nueva 218 passed + 28 subtests, 0 failed; regresión completa
  2108 passed, 10 skipped, 709 subtests, 0 failed (1552.28s); `check_manifest_parity` OK; doctor 26
  OK / 13 WARN preexistentes / 0 ERROR / 1 N/A; reviewer con **0 hallazgos** (0 de 2 ciclos de
  remediación usados).
- **Change 1 — `data-contract-validation`** (`openspec/changes/20260922-data-contract-validation/
  verification.md`): CERRADO. Suite nueva 307 passed, 5 skipped + 32 subtests, 0 failed; regresión
  completa 2180 passed, 10 skipped, 709 subtests, 0 failed (1530.38s); manifest parity OK; doctor 0
  ERROR; reviewer con 0 hallazgos bloqueantes y 3 no bloqueantes (2 aplicados, 1 riesgo aceptado y
  diferido) — 1 de 2 ciclos de remediación usados.
- **Change 2 — `model-quality-policies`** (`openspec/changes/20260922-model-quality-policies/
  verification.md`): CERRADO. Suite nueva 416 passed + 28 subtests, 0 failed; regresión completa
  2306 passed, 10 skipped, 709 subtests, 0 failed (1639.77s); manifest parity OK; doctor 0 ERROR;
  reviewer con 0 hallazgos bloqueantes y 1 observación cosmética aceptada sin fix — 0 de 2 ciclos de
  remediación de revisión usados (el único fix, sobre 2 tests de sanidad del propio detector, fue
  pre-revisión).
- **Change 3 — `quality-evidence-and-drift`** (`openspec/changes/20260922-quality-evidence-and-drift/
  verification.md`): CERRADO. 2 bugs reales encontrados y corregidos pre-revisión, el más importante
  un patrón de mensaje de error `{{n}}` que rompía toda instalación real vía `ds_init`/`writer.py`;
  regresión completa final 2410 passed, 10 skipped, 709 subtests, 0 failed; manifest parity OK;
  doctor 0 ERROR; reviewer con 1 hallazgo bloqueante (privacidad, ruta absoluta en mensajes de
  error de `write_manifest`/`read_manifest`) y 1 no bloqueante, ambos resueltos — 1 de 2 ciclos de
  remediación usados.
- **Change 4 — `quality-integration-and-cli`** (`openspec/changes/20260922-quality-integration-and-cli/
  verification.md`): CERRADO. Ciclo de remediación con fix real de `evolution.py`
  (`_campo_cubierto`/`campos_cubribles`, para que solo campos genuinamente nuevos/eliminados
  supriman constraints); suite nueva 648 passed + 28 subtests, 0 failed (614.60s); manifest parity
  OK; doctor 26 OK / 14 WARN / 0 ERROR / 1 N/A; cero diff confirmado con dos métodos independientes
  en las 7 rutas críticas de no-alteración de readiness/promote/lifecycle; reviewer con 0 hallazgos
  bloqueantes (1 no bloqueante + 2 gaps de cobertura, resueltos) — 1 de 2 ciclos de remediación
  usados. Nota explícita de ese cierre: la regresión total (`pytest tools -q`) **no se corrió** en
  esa invocación, quedando reservada como gate obligatorio de este Change 5.

En conjunto, Changes 0-4: **0 hallazgos bloqueantes sin resolver**, 2 bugs reales pre-revisión
(Change 3), 3 ciclos de remediación de revisión usados de un máximo de 2 por Change (Change 1: 1/2;
Change 3: 1/2; Change 4: 1/2; Changes 0 y 2: 0/2), todos con regresión y manifest parity en verde en
su propio cierre.

## (b) Evidencia nueva de Change 5

- **Smokes nuevos aislados** (`tools/tests/test_v07_release_hardening_smoke.py`): **5 passed**
  (0.20-1.45s).
- **Regresión completa FINAL** (`pytest tools -q`, corrida DESPUÉS del fix de manifest.py descrito
  en (c)): **2475 passed, 10 skipped, 709 subtests passed, 0 failed, 1673.94s (0:27:53)**.
- `check_manifest_parity`: OK.
- Scratch install `experiment` fresco (repo git temporal + `.venv --without-pip`, mismo criterio
  que v0.6 para evitar el artefacto conocido de `RUNTIME-INTERPRETE`): las ~10 entradas VERBATIM de
  Changes 0-4 (incluida la recién corregida) se instalan correctamente; `harmessi doctor --destino`
  → 27 OK, 1 WARN (working tree del scratch, esperado), **0 ERROR**, 1 N/A.
- Scratch install `discovery` fresco (mismo criterio): mismas ~10 entradas se instalan
  correctamente (confirmado con `ls`); `harmessi doctor --destino` → 23 OK, 1 WARN, **4 ERROR**, 1
  N/A. Ver (d) para el análisis de estos 4 ERROR.
- Backward compatibility (R17): `git diff --stat v0.6.0..HEAD` sobre `tools/dsguard tools/ds_profile
  tools/dsimpact tools/providers tools/routing tools/fallback tools/harmessi_bench tools/nbrunner
  tools/harmessi tools/ds_guard.py tools/launcher_common.py tools/reporting` → únicamente
  `tools/ds_guard.py` (681 insertions, 2 deletions); cero diff en el resto, incluido
  `tools/reporting/**` completo.
- Privacidad transversal (R18): sweep sobre `git diff 37fc3e3..HEAD` completo, sin hallazgos reales
  (los únicos matches de patrones de ruta absoluta fueron fixtures de test deliberadamente
  sintéticas probando que esas rutas NO se filtran, p. ej. `test_evolution_neutrality.py`/
  `test_validation.py` con `"C:\\Users\\alguien\\datos_privados.csv"` como dato de prueba).
- Portabilidad (R19): confirmado, paths repo-relativos en toda la evidencia de v0.7.
- `harmessi doctor` sobre este propio repo: 26 OK, 14 WARN (drift esperado de archivos modificados
  por v0.7, no relacionado), 0 ERROR, 1 N/A.

## (c) Bug de manifest.py encontrado y corregido — hallazgo más importante del hardening

**Bug real de paridad de manifest (R20)**: `tools/datacontracts/validation.py` (implementado en el
Change 1, ya cerrado) **nunca se había agregado** a `tools/ds_init/manifest.py`. Confirmado con
`git log --oneline -- tools/ds_init/manifest.py`: el commit del Change 1 (`e964109`) no aparece
ahí, a diferencia de Change 0 (`713457e`), Change 2 (`07ea73d`), Change 3 (`c44eef0`) y Change 4
(`4be6387`), que sí lo tocaron.

**Efecto**: un scratch install fresco **nunca instalaba** `tools/datacontracts/validation.py`, pese
a ser código ya cerrado y en uso desde el Change 1.

**Corrección**: entrada VERBATIM nueva en `manifest.py`, `stage_minimo="discovery"`, mismo patrón
que las entradas hermanas de `core.py`/`evolution.py`.

**Verificación de la corrección**:
- `tools/ds_init/tests/test_manifest.py` + `tools/tests/test_manifest_dsguard_parity.py` → **40
  passed** tras el fix.
- `git diff --stat 4be6387 -- tools/ds_init/manifest.py` → 7 insertions, única entrada nueva.
- `git diff --stat 4be6387 -- tools/datacontracts/` → vacío (ningún cambio de comportamiento en
  `validation.py`/`core.py`/`evolution.py` en sí; el fix fue puramente de registro en el manifest).

Este es el hallazgo más importante de todo el hardening de v0.7: un defecto de instalación real que
había quedado sin detectar durante 4 Changes consecutivos (Changes 1-4), y que solo la verificación
sistemática de paridad de manifest de este Change 5 sacó a la luz. Es consistente con el patrón ya
visto en el Change 3 (el bug del placeholder `{{n}}` que rompía `ds_init`): los defectos de
instalación real son la categoría de bug que más vale seguir vigilando en Changes futuros.

## (d) Limitación preexistente de `doctor.py` — NO bloqueante, NO introducida por v0.7

**Hallazgo NO bloqueante, preexistente, fuera de alcance de v0.7**: los 4 ERROR de la corrida de
scratch install `discovery` (ver (b)) son `HARMESSI-AGENTE-FALTANTE` —
`tools/harmessi/doctor.py::_check_agents` (líneas ~498-538) no es consciente de
`installation_stage` (a diferencia de `HARMESSI-ARCHIVOS-ESPERADOS`, que sí lo es), así que espera
los 4 archivos de agente aunque el stage `discovery` legítimamente no los instale.

**Confirmación de que es preexistente, no introducido por v0.7**:
- `git log 37fc3e3..HEAD -- tools/harmessi/doctor.py` está vacío: ningún commit de v0.7 tocó ese
  archivo.
- `git show v0.6.0:tools/harmessi/doctor.py` contiene la misma función `_check_agents` (2
  ocurrencias del nombre, idéntico patrón), confirmando que el límite existe desde antes de v0.7.

El reviewer coincidió en la evaluación (con la salvedad de no poder correr `git` él mismo, pero
confirmando por lectura de código que `_check_agents` en efecto no consulta `installation_stage`).

Queda registrado como deuda para una futura corrección de `doctor.py::_check_agents` (hacerlo
consciente de `installation_stage`, mismo patrón que `HARMESSI-ARCHIVOS-ESPERADOS`), fuera del
alcance de v0.7 (sin features nuevas en el Change de hardening).

## (e) Revisión transversal (invocación 4, `data-science-reviewer`)

Revisó coherencia de vocabulario entre las 4 familias de códigos (`CONTRACT-*`,
`CONTRACT-EVOLUTION-*`, `QUALITY-*`, `QUALITYEVIDENCE-*`): sin colisiones. "Nunca PASS sin
evidencia" consistente en las 4 evaluaciones (`validate_contract`, `evaluate_policy`,
`classify_contract_change`, drift). El STOP de readiness/promotion confirmado con lectura fresca
sin ninguna interacción sutil entre Changes. Los 2 smokes nuevos ejercitan código real (no mocks).
El fix de `manifest.py` correcto, con 1 observación cosmética no bloqueante sobre `stage_minimo`
explícito vs. implícito, sin efecto de comportamiento, no corregida. Coincidió con la evaluación
del hallazgo de `doctor.py::_check_agents` como límite preexistente.

**0 hallazgos bloqueantes. 0 ciclos de remediación usados** (no hizo falta ningún fix más allá del
de `manifest.py`, que ya estaba aplicado antes de la revisión).

## (f) Checklist final — Decisiones de diseño del roadmap (`docs/roadmap/v0.7.md`)

Las 8 decisiones de diseño siguen respetadas tras la integración completa de v0.7:

1. **El binario no calcula métricas de modelo** — respetada. `tools/modelquality/{core,
   validation}.py` (Change 2) consume `ObservedMetric` ya reportado por el proyecto, con
   procedencia (evidence ref + hash + contexto); no hay calculadores de AUC/F1/RMSE ni similares en
   ningún Change. Confirmado en el cierre del Change 2 y sin diff sobre esos archivos en los
   Changes 3-5.
2. **`ds_profile` es el único observador de datos** — respetada. `validate_contract` (Change 1) y
   `drift_from_profiles` (Change 3) consumen `profile.json` persistido; ningún Change construyó un
   segundo profiler.
3. **Severidad declarada en el contrato, verificabilidad decidida por el binario** — respetada.
   Vocabulario `PASS`/`WARN`/`FAIL`/`N/A` consistente en las 4 evaluaciones (confirmado por la
   revisión transversal en (e)); nunca `PASS` sin evidencia suficiente.
4. **`technical_error` no es un resultado de calidad** — respetada. `CheckResult.kind` reutilizado
   en las 4 familias, reportado aparte del conteo de calidad en todos los Changes.
5. **Quality no es gate** — respetada, con verificación reforzada específicamente. El Change 4
   confirmó **cero diff** con dos métodos independientes (`git diff --name-only` y `git diff
   --exit-code` contra `c44eef0`) en las 7 rutas críticas (`tools/dsguard/status.py`,
   `tools/dsguard/readiness.py`, `tools/datacontracts/core.py`, `tools/datacontracts/validation.py`,
   `tools/modelquality/`, `tools/qualityevidence/`, `tools/dsimpact/`), más 3 tests dedicados
   (`tools/tests/test_v07_readiness_promote_status_no_alteration.py`) que garantizan
   comportamiento y exit code idénticos de readiness/promote con y sin evidencia de calidad
   presente. Este Change 5 confirma la ausencia de alteración de forma transversal: la revisión de
   (e) releyó el STOP de readiness/promotion sin encontrar ninguna interacción sutil entre Changes,
   y la regresión completa final (2475 passed, 0 failed) incluye esos 3 tests dedicados en verde.
6. **Drift es evidencia comparativa, no un veredicto** — respetada. `DriftEvidence` (Change 3)
   registra ventana de referencia, ventana actual, métrica, diferencia observada, umbral/política y
   resultado; `result_status` nunca es `PASS`/`FAIL` sin `threshold`.
7. **Feature quality se absorbe en Data Contracts** — respetada. No se introdujo scoring,
   importancia ni selección de features en ningún Change; el rol `feature_table` de `DataContract`
   cubre el caso.
8. **Sin dependencias nuevas** — respetada. Ningún Change de v0.7 instaló dependencias; stdlib +
   capacidades existentes en los 6 Changes. Confirmado indirectamente por los tests de neutralidad
   de cada familia (`test_v07_core_neutrality.py`, `test_v07_validation_neutrality.py`,
   `test_v07_modelquality_neutrality.py`, `test_v07_qualityevidence_neutrality.py`,
   `test_v07_evolution_neutrality.py`) y por el smoke agregado nuevo de este Change 5.

## Resultado final

**`READY FOR v0.7.0 RELEASE`**

Razones concretas:

- Regresión completa FINAL en verde: **2475 passed, 10 skipped, 709 subtests passed, 0 failed**
  (1673.94s), corrida después de aplicar el fix de `manifest.py`.
- **0 hallazgos bloqueantes acumulados sin resolver** a lo largo de los 6 Changes de v0.7 (Changes
  0-5): todos los hallazgos bloqueantes que surgieron durante el desarrollo (Change 1: 0 real
  bloqueante, 3 no bloqueantes resueltos; Change 3: 1 bloqueante de privacidad, resuelto; Change 4:
  0 bloqueantes, 1 no bloqueante + 2 gaps resueltos) fueron aplicados y verificados en su propio
  ciclo de remediación antes de este cierre.
- **1 bug real encontrado y corregido durante el propio hardening**: la ausencia de
  `tools/datacontracts/validation.py` en `manifest.py` (ver (c)), que rompía la instalación real de
  ese archivo desde el Change 1 y solo se detectó con la verificación sistemática de paridad de
  manifest de este Change 5. Corregido y re-verificado (40 passed).
- **1 limitación preexistente no bloqueante documentada**: `doctor.py::_check_agents` no consciente
  de `installation_stage` (ver (d)), confirmada por dos vías independientes (`git log` y `git show
  v0.6.0`) como anterior a v0.7 y no introducida por esta versión.
- **Backward compatibility formal confirmada**: `git diff --stat v0.6.0..HEAD` sobre las rutas
  críticas preexistentes → únicamente `tools/ds_guard.py` (681 insertions, 2 deletions), cero diff
  en el resto, incluido `tools/reporting/**` completo.
- **Privacidad confirmada**: sweep transversal sobre `git diff 37fc3e3..HEAD` completo sin
  hallazgos reales.
- Revisión transversal del `data-science-reviewer` (invocación 4) sin hallazgos bloqueantes y 0
  ciclos de remediación necesarios.
- Las 8 decisiones de diseño del roadmap siguen respetadas tras la integración completa (ver (f)),
  en particular la decisión 1 (el binario no calcula métricas) y la decisión 5 (readiness/promotion
  sin alteración, con verificación reforzada de doble método + 3 tests dedicados + confirmación
  transversal).

**Aclaración explícita**: este veredicto **NO autoriza** push, merge, tag ni release por sí solo —
sigue pendiente de aprobación humana final. La alineación de versión canónica
(`tools/ds_init/version.py`, `CITATION.cff`) y la regeneración de `.ds_init/control.json`
(invocación 7 de `tasks.md`) están **fuera de esta invocación**, condicionadas a autorización
explícita posterior del usuario, tal como quedó definido en `tasks.md`.

# Verificación — 20260915-readiness-and-promotion

## Evidencia obtenida
Implementación bajo autonomía acotada autorizada por el usuario, en 1 delegación principal de
implementación (código + tests, resumida 3 veces por límite de turnos del subagente — no cuentan
como nuevas delegaciones) + 1 delegación de reviewer (resumida 1 vez por límite de turnos) + 1
fix de test (fixture faltante) + 1 fix menor de cobertura (caso `versionado` faltante en el test
de reinterpretación WARN→FAIL), ambos aplicados directamente por el Lead sin subagente adicional:

- **`tools/dsguard/mlops_evidence.py`** (nuevo): mecanismo genérico de evidencia de artifact
  (`agregar_evidencia`, `evidencia_valida`) para tiers `production_readiness`/`operations`, hash
  sha256 binario local, reuso replicado de `pathguard` (holdouts/secretos/excepciones de
  lectura), dedup por `{capability,path,hash}`.
- **`tools/dsguard/readiness.py`** (nuevo): `evaluar_readiness(repo_root, target)` para los 3
  targets (`experiment`, `production_candidate`, `production`) según la matriz exacta de
  `spec.md`, y `promote(repo_root, target, reason)` (secuencial, atómico, read-only hasta el
  momento de escribir).
- **`tools/ds_guard.py`**: `project readiness --target`, `project promote <stage> --reason`,
  subgrupo `mlops evidence add`.
- **`tools/ds_init/manifest.py`**: entradas VERBATIM de ambos módulos nuevos.
- **`tools/tests/test_mlops_evidence.py`** (nuevo) y **`tools/tests/test_readiness.py`** (nuevo):
  cobertura completa de los criterios de aceptación de `spec.md`.
- **`tools/tests/test_manifest_dsguard_parity.py`** y
  **`tools/ds_init/tests/test_integracion_instalacion.py`**: extendidos con ambos módulos nuevos.

Durante la implementación no surgió ninguna contradicción real entre `spec.md`/`design.md` y el
código existente (confirmado explícitamente por el subagente implementador al cierre de su
tarea) — solo decisiones menores de implementación no cubiertas literalmente por `design.md`
(forma exacta del envelope `--json` de `readiness`, código compartido de
`environment_reproducible`, exit code 0 para dedup de evidencia, no-gating explícito redundante
en la reinterpretación de foundations), todas documentadas por el propio subagente y revisadas
por el Lead como razonables y consistentes con el resto del harness.

Verificación real ejecutada por el Lead (nunca por el subagente, que no tiene Bash):
- `tools.tests.test_readiness`/`test_mlops_evidence` + suite completa `tools/tests/`: primera
  corrida completa 443/444 OK (1 fallo real de fixture: `test_secuencia_correcta_los_3_pasos`
  intentaba promover a `experiment` sin haber corrido `lifecycle.lifecycle_init()` primero,
  violando el propio gate `READINESS-LIFECYCLE-VALID` de R4 — bug de test, no de producción,
  confirmado leyendo `readiness.py` directamente; corregido agregando el `lifecycle_init()`
  faltante al fixture).
- Segunda corrida completa: 443/444 OK con 1 fallo (`ImportError: cannot import name
  'mlops_evidence'`) diagnosticado como falso positivo del propio Lead: un `git stash -u` lanzado
  en paralelo (para comparar `harmessi doctor` antes/después) sacó temporalmente del disco los
  archivos sin trackear (`mlops_evidence.py`/`readiness.py`) mientras un subprocess de test
  intentaba importarlos — confirmado re-corriendo el test aislado inmediatamente después (sin
  stash activo): `ok`.
- Reviewer (`data-science-reviewer`): sin hallazgos bloqueantes ni importantes. 1 hallazgo menor
  (cobertura de test incompleta: faltaba el caso `READINESS-FOUNDATIONS-VERSIONADO` en el test de
  reinterpretación WARN→FAIL) — corregido por el Lead agregando el caso faltante
  (`tools/tests/test_readiness.py`), confirmado con corrida aislada y luego regresión completa.
- Corrida final completa `tools/tests/`: **444/444 OK (2 skipped, mismos de siempre, no
  relacionados con este change)**.
- `tools/harmessi/tests/`: 64/64 OK (sin cambios, doctor no fue tocado).
- `tools/ds_init/tests/`: 59/59 OK, incluida la instalación scratch con ambos módulos nuevos
  presentes (58→60 archivos administrados).
- `harmessi doctor`: 26 [OK] / 4 [WARN] / 0 [ERROR] — único WARN nuevo respecto al baseline
  (`git stash` before/after) es `CORE-WORKING-TREE` (working tree con cambios sin confirmar,
  esperado durante desarrollo activo, sin commit todavía); `HARMESSI-ARCHIVOS-ESPERADOS` pasó de
  58 a 60 archivos administrados (los 2 módulos nuevos), sin ningún `[ERROR]` nuevo.

## Fingerprint de dataset/artefacto (condicional — cambio sensible o reproducibilidad crítica)
No aplica — no hay dataset ni artefacto de modelo propio en este change (el mecanismo de
evidencia registra hashes de artifacts QUE EL USUARIO declare en un proyecto real, no produce
ninguno acá).

## Diferencias contra la spec
Ninguna sustancial. La única extensión más allá de lo literal de `spec.md` fue agregar el caso
`READINESS-FOUNDATIONS-VERSIONADO` al test que ya cubría `REPRODUCIBILIDAD`/`ARTIFACTS` —
completa la cobertura prometida por el propio criterio de aceptación ("mismo patrón para
versionado/artifacts"), no cambia ningún comportamiento de producción.

## Limitaciones
El mecanismo de evidencia de `production_readiness`/`operations` es enteramente manual/explícito
(`mlops evidence add`) — no hay scaffold que sugiera dónde poner artifacts (Change 7, progressive
capability installation, sigue pendiente). `lineage` sigue siendo la misma medición honesta y
limitada de Change 5 (WARN/N-A permanente), ahora explícitamente no-bloqueante para
`production_candidate`/`production` por diseño de este change, tal como pidió el usuario. No
existe todavía `harmessi project ...` (superficie pública unificada) — se sigue usando
`ds_guard project readiness`/`promote` directamente.

## Pendientes derivados
Ninguno bloqueante. El catálogo `MLOPS_CAPACIDADES` de `lifecycle.py` (Change 1) queda ahora
completamente evaluable en los 3 tiers (`foundations` desde Change 5, `production_readiness`/
`operations` desde este change) — sienta la base para que Change 7 (progressive capability
installation) pueda scaffoldear ubicaciones sugeridas de evidencia sin necesitar más cambios en
`readiness.py`/`mlops_evidence.py`.

## Resultado final
Todos los requisitos R1-R17 de `spec.md` implementados con evidencia real, sin gates inventados
ni relajados respecto a la matriz aprobada por el usuario. Reviewer sin hallazgos bloqueantes.
Regresión completa limpia (444/444 + 64/64 + 59/59, 0 ERROR en doctor). Change listo para cierre.

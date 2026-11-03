# Spec — 20260925-v07-release-hardening

Sin features nuevas: este Change verifica el gate candidato completo de
`docs/roadmap/v0.7.md:397-420`, corrige solo defectos de hardening y decide el resultado final. El
"cómo" lo ejecuta el Lead (regresión, scratch installs, sweeps) salvo los smokes/fixtures nuevos
explícitamente asignados a `python-data-engineer` en `tasks.md`.

Cada requisito indica su estado de partida: **[YA CUBIERTO]** (Changes 0-4 ya lo verificaron; este
Change solo confirma que sigue verde) o **[NUEVO]** (no existe hoy, requiere smoke/fixture o
verificación propia de este Change).

## Requisitos

- **R1 — Regresión completa `pytest tools -q` [NUEVO como corrida total]**: el repo completo
  (todas las suites bajo `tools/`, incluidas `tools/datacontracts/tests`,
  `tools/modelquality/tests`, `tools/qualityevidence/tests` y las 6 suites de neutralidad/no-
  alteración de v0.7) corre en una sola invocación sin `failed`; se corre completo al menos una vez
  más después de cualquier corrección de hardening.
- **R2 — DataContract contract tests [YA CUBIERTO, Change 0]**: `tools/datacontracts/tests/
  test_core.py` (round-trip determinista, versionado, validación estructural del propio contrato)
  sigue en verde dentro de R1.
- **R3 — Versionado/compatibilidad [YA CUBIERTO, Change 0 y Change 4]**: `ContractVersion`/
  `CompatibilityPolicy` (Change 0) y `classify_contract_change`/`CONTRACT-EVOLUTION-*` (Change 4,
  `tools/datacontracts/tests/test_evolution.py`) siguen en verde dentro de R1.
- **R4 — Fixtures de validación de datos [YA CUBIERTO, Change 1]**: `tools/datacontracts/tests/
  test_validation.py` (campo requerido ausente, campo inesperado, tipo incompatible, nullability,
  unicidad, rango/dominio, evidencia faltante/stale, `technical_error`) sigue en verde dentro de
  R1.
- **R5 — Fixtures de políticas de calidad de modelo [YA CUBIERTO, Change 2]**:
  `tools/modelquality/tests/test_validation.py` (orden de evaluación métrica→evidencia→
  threshold→baseline, `technical_error` separado) sigue en verde dentro de R1.
- **R6 — Fixture de métrica custom [YA CUBIERTO, Change 2]**: al menos un caso de
  `tools/modelquality/tests/test_validation.py` declara una métrica por nombre + dirección + modo
  de comparación fuera de cualquier lista cerrada, y se evalúa correctamente.
- **R7 — Comportamiento con evidencia faltante [YA CUBIERTO, Change 1 y Change 3]**:
  `CONTRACT-EVIDENCE-MISSING` (Change 1) y los casos de `QUALITYEVIDENCE-*` sin evidencia
  (Change 3) siguen en verde dentro de R1; ninguno produce `PASS`.
- **R8 — Evidencia stale [YA CUBIERTO, Change 1 y Change 3]**: el límite de staleness documentado
  en `tools/datacontracts/validation.py` (Change 1) y la separación `generated_at`/hash de
  `tools/qualityevidence/core.py` (Change 3) siguen en verde dentro de R1.
- **R9 — Separación de `technical_error` [YA CUBIERTO, Changes 1-4]**: en ningún resultado agregado
  de v0.7 un `technical_error` contamina el conteo de calidad (decisión 4 del roadmap); verificado
  transitivamente por las suites de cada Change dentro de R1.
- **R10 — Comparaciones contra baseline [YA CUBIERTO, Change 2 y Change 3]**: `BaselineReference`
  (Change 2) y `DriftEvidence` con ventana de referencia/actual (Change 3) siguen en verde dentro
  de R1; baseline exigido y ausente nunca produce `PASS`.
- **R11 — Reproducibilidad de la evidencia de calidad [YA CUBIERTO, Change 3]**:
  `content_sha256()` de `QualityEvidenceManifest`/`DriftEvidence` excluye `generated_at` y produce
  el mismo hash en 2 corridas con la misma entrada; verificado dentro de R1.
- **R12 — Smoke de consumo desde reporting [NUEVO]**: un test en
  `tools/tests/test_v07_release_hardening_smoke.py` construye un `QualityEvidenceManifest`
  sintético (Change 3), lo persiste con `write_manifest` bajo un directorio temporal dentro de un
  repo git de prueba, y llama a `reporting.evidence.describe_source` sobre ese archivo; confirma
  que el hash reportado coincide con el hash real del archivo y que ni `tools.reporting` importa
  `tools.qualityevidence` ni viceversa (grep de imports sobre los módulos concretos usados en el
  test, no solo el resultado funcional).
- **R13 — Smoke de integración con impact [YA CUBIERTO, Change 4 — confirmar suficiencia]**:
  `tools/tests/test_ds_guard_contract_quality_cli.py::TestContractImpact` (2 tests:
  `test_staged_potentially_affected`, `test_texto_vocabulario_potentially_affected`) sigue en
  verde dentro de R1 y se confirma explícitamente en `verification.md` que el vocabulario
  "potentially affected" se usa (nunca "roto"/"afectado" en tono afirmativo).
- **R14 — Smoke de holdout/scientific-governance [YA CUBIERTO, Change 1 y Change 3]**:
  `ds_profile.holdout_guard.verificar_permitido` (Change 1,
  `tools/datacontracts/tests/test_validation.py`) y el guard simétrico en `drift_from_profiles`
  (Change 3, `tools/qualityevidence/tests/test_evidence.py`) siguen en verde dentro de R1; ningún
  holdout real se abre en ningún test de este Change.
- **R15 — No-alteración de readiness/promote/lifecycle [YA CUBIERTO, Change 4]**:
  `tools/tests/test_v07_readiness_promote_status_no_alteration.py` sigue en verde dentro de R1;
  se reconfirma con `git diff --name-only`/`git diff --exit-code` contra el commit de cierre de
  Change 4 (`4be6387`) sobre `tools/dsguard/status.py`, `tools/dsguard/readiness.py` (cero diff
  esperado, salvo que una corrección de hardening de este Change los toque explícitamente, lo que
  sería motivo de parada por cambio arquitectónico material).
- **R16 — Scratch installs frescos [NUEVO como corrida]**: `python -m tools.ds_init` instala
  `experiment` y `discovery` en un repo git temporal del scratchpad de la sesión; el manifest
  instalado incluye las ~9 entradas VERBATIM nuevas de Changes 0-4 (`tools/datacontracts/*`,
  `tools/modelquality/*`, `tools/qualityevidence/*`, `tools/ds_guard.py` actualizado); sin `ERROR`
  al correr `harmessi doctor --destino` sobre el proyecto instalado.
- **R17 — Backward compatibility [NUEVO como consolidación formal]**: `git diff --stat
  v0.6.0..HEAD` sobre `tools/dsguard tools/ds_profile tools/dsimpact tools/providers tools/routing
  tools/fallback tools/harmessi_bench tools/nbrunner tools/harmessi tools/ds_guard.py
  tools/launcher_common.py tools/reporting` muestra únicamente los cambios ya documentados y
  aprobados Change a Change de v0.7 (en particular las ~683 líneas nuevas de `tools/ds_guard.py`
  del Change 4, sin diff en `tools/reporting/**` salvo lo confirmado explícitamente sin diff por el
  reviewer de Change 3); ninguna sorpresa fuera de lo ya cerrado.
- **R18 — Privacidad transversal [NUEVO como sweep del diff completo]**: sweep sobre todo el diff
  de v0.7 (`git diff --stat 37fc3e3..HEAD` y grep de patrones, donde `37fc3e3` es el commit "Define
  Harmessi v0.7 roadmap", inmediatamente posterior al merge de `v0.6.0`) buscando nombres de
  cliente/proyecto reales, rutas locales (`C:\Users\...`/`C:\Datos\...`), emails reales y nombres
  de usuarios reales fuera de "Federico Colombo" en el registro de aprobación: 0 hallazgos reales
  (los que aparezcan son texto del propio patrón de búsqueda en `spec.md`, mismo criterio que
  v0.3-v0.6).
- **R19 — Portabilidad [YA CUBIERTO en cada Change — confirmar consolidado]**: paths
  repo-relativos en toda la evidencia de v0.7 (`ds_profile` persiste `dataset_path` absoluto, pero
  ninguna evidencia de v0.7 lo copia tal cual, ver `docs/roadmap/v0.7.md:318-319`); sin separadores
  de SO ni rutas absolutas hardcodeadas en `tools/datacontracts/*`, `tools/modelquality/*`,
  `tools/qualityevidence/*` no-test; ejecutado solo en Windows (misma limitación declarada que
  v0.6).
- **R20 — Paridad de manifest [YA CUBIERTO en cada Change — confirmar consolidado]**:
  `check_manifest_parity` da `OK`; todo `tools/datacontracts/**/*.py`,
  `tools/modelquality/**/*.py`, `tools/qualityevidence/**/*.py` no-test tiene entrada VERBATIM en
  `.ds_init/manifest.py`; el conjunto de rutas de un scratch install `experiment` fresco coincide
  con el manifest declarado (sin regenerar `.ds_init/control.json` en esta invocación 1).
- **R21 — `harmessi doctor` sin `ERROR` [YA CUBIERTO en cada Change — confirmar consolidado]**:
  0 `[ERROR]` sobre este repo y sobre el scratch install fresco de R16.
- **R22 — Reviewer transversal**: `data-science-reviewer` revisa el conjunto de los 5 Changes de
  v0.7 como unidad (no repite revisiones individuales ya cerradas); hallazgos resueltos o
  registrados como limitación en `verification.md`.
- **R23 — Sin features nuevas ni publicación**: el diff de este Change contiene únicamente
  `verification.md`, los 4 artefactos SDD, el smoke/fixture nuevo de R12/neutralidad agregada, y
  correcciones de hardening acotadas si las hubiera; sin push, merge, tag, release ni cambio de
  `.ds_init/control.json` en esta invocación 1.
- **R24 — Resultado final explícito**: `verification.md` consolida (citando, no repitiendo en
  extenso) los 5 `verification.md` de Changes 0-4 más la evidencia nueva de este Change, y termina
  con `READY FOR v0.7.0 RELEASE` o `NOT READY FOR v0.7.0 RELEASE` con razones concretas.

## Criterios de aceptación

- **R1**: Given el repo en el estado final de este Change, When se corre `pytest tools -q`, Then
  el resultado es `0 failed` y el conteo de `passed`/`skipped`/`subtests` sale de la corrida real
  (nunca de memoria), documentado en `verification.md`.
- **R2-R11, R13-R15**: Given las suites nombradas de cada Change, When corren dentro de R1, Then
  0 failures; el `verification.md` de este Change cita el resultado agregado de R1 y, para R13,
  además confirma por lectura que el texto usa "potentially affected".
- **R12**: Given un `QualityEvidenceManifest` sintético persistido en un directorio temporal, When
  se llama `reporting.evidence.describe_source` sobre ese archivo, Then el hash reportado coincide
  con `hashlib.sha256` del archivo real y una inspección de imports de
  `tools/reporting/evidence.py` y `tools/qualityevidence/{core,evidence}.py` confirma que ninguno
  importa al otro.
- **R16**: Given un repo git temporal en el scratchpad de la sesión, When se instala `experiment` y
  `discovery` con `--execute`, Then ambas instalaciones terminan sin `ERROR`, incluyen las ~9
  entradas VERBATIM nuevas de Changes 0-4, y `harmessi doctor --destino` sobre el proyecto
  instalado da 0 `[ERROR]`.
- **R17**: Given `v0.6.0..HEAD`, When se corre `git diff --stat` sobre las rutas de R17, Then todo
  cambio mostrado corresponde a alguno de los 5 Changes de v0.7 ya cerrados (sin sorpresas fuera de
  lo documentado en sus `verification.md`).
- **R18**: Given el diff completo de v0.7 (`37fc3e3..HEAD`), When se corre el sweep de R18, Then
  0 hallazgos reales.
- **R19**: Given el código no-test de las 3 familias nuevas, When se buscan rutas absolutas y
  separadores de SO hardcodeados, Then 0 hallazgos, y `verification.md` declara "solo Windows"
  como limitación (mismo criterio que R15 del hardening de v0.6).
- **R20**: Given el repo en su estado final, When se corre `check_manifest_parity` y se compara con
  un scratch install `experiment` fresco, Then paridad `OK` y conjunto de rutas idéntico.
- **R21**: Given el estado final (repo y scratch install), When se corre `harmessi doctor`, Then
  0 `[ERROR]` en ambos casos.
- **R22**: Given el diff acumulado de los 5 Changes de v0.7, When el reviewer lo revisa como
  unidad, Then cada hallazgo queda resuelto o registrado como limitación.
- **R23**: Given el diff de este Change, When se inspecciona con `git diff --stat`, Then solo
  aparecen los artefactos SDD, `verification.md`, el smoke nuevo y correcciones de hardening
  acotadas; `.ds_init/control.json` sin tocar en esta invocación 1; sin push/merge/tag/release.
- **R24**: Given toda la evidencia recolectada, When se cierra el Change, Then `verification.md`
  contiene el veredicto literal con razones concretas y cita (sin repetir en extenso) los 5
  `verification.md` de Changes 0-4.

## Unidad de análisis / grain (condicional)

No aplica — hardening de release del harness.

## Cutoff / information boundary (condicional)

No aplica — ningún dato con fecha de corte real está involucrado; los fixtures sintéticos de R12
no declaran `data_cutoff`.

## Baseline (condicional)

No aplica. La referencia de compatibilidad es el tag `v0.6.0` (R17).

## Métrica primaria (condicional)

No aplica.

## Métricas secundarias (opcional)

No aplica.

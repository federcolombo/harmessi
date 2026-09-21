# Spec — 20260918-v0-6-release-hardening

Sin features nuevas: este Change verifica, corrige solo defectos de hardening, alinea
versión/estado y decide el resultado final. El "cómo" lo ejecuta el Lead.

## Requisitos

- **R1 — Versión consistente `0.6.0`**: `tools/ds_init/version.py` (`HARNESS_VERSION`),
  `CITATION.cff` (`version`, `date-released`) y `.ds_init/control.json` (regenerado) declaran
  `0.6.0`; ninguna otra línea de esos archivos fue tocada.
- **R2 — Roadmap con estado real**: `docs/roadmap/v0.6.md` tiene encabezado de estado y checklist
  `[x] Change 5` solo si corresponde al cierre; v0.7-v0.9 y `docs/roadmap/README.md` no se tocan.
- **R3 — Privacidad transversal**: sweep sobre todo lo rastreado (`AGD`, `UNCO-Intelligence`,
  `Model-churn`, rutas locales `C:\Users\...`/`C:\Datos\...`, emails, nombres de usuarios reales
  fuera de "Federico Colombo" en el registro de aprobación, datasets/empresas/clientes/logos/
  branding) sin fugas reales.
- **R4 — Regresión completa SECUENCIAL (memoria)** de 10 suites: `tools/tests`,
  `tools/harmessi/tests`, `tools/ds_init/tests`, `tools/ds_profile/tests`, `tools/dsimpact/tests`,
  `tools/providers/tests`, `tools/harmessi_bench/tests`, `tools/routing/tests`,
  `tools/fallback/tests`, `tools/reporting/tests`; 0 failures, skips condicionales documentados.
- **R5 — Reporting contract tests**: paquete completo + `test_v06_core_neutrality` +
  `test_architecture_boundaries` + manifest parity.
- **R6 — Scratch project real**: instalación con `python -m tools.ds_init --destino <repo git
  temporal> --nombre ... --stage experiment --execute` (y una `discovery`) en el scratchpad de la
  sesión; desde el proyecto instalado: publicar el EDA genérico, `python -m tools.reporting
  validate`, `render --check` y `harmessi doctor --destino` sin ERROR.
- **R7 — EDA de ejemplo genérico**: publicado y validado con 0 FAIL, determinista (mismo hash y
  mismo HTML en 2 corridas), sin datos privados en HTML ni artefactos.
- **R8 — Aislamiento `exploratory`**: destino cruzado ⇒ FAIL `REPORT-DEST-CROSS-SCOPE`;
  `check-inputs` por path, por manifest ancestro y por hash de copia byte-idéntica ⇒ FAIL.
- **R9 — Smoke `model_valid`**: reporte que usa un output exploratory como fuente es rehusado por
  `publish` sin escribir nada; uno legítimo (policy científica, `data_cutoff` ≤ cutoff) se publica.
- **R10 — Smoke holdout**: fuente/dir input con holdout ⇒ denegado sin abrir;
  `holdout_access="read"` solo con `evaluation` + `final_evaluation.authorized`.
- **R11 — Figura↔tabla**: figura sin tabla, columnas ausentes, tabla vacía o ref colgante ⇒ FAIL.
- **R12 — Reproducibilidad del manifest**: byte a byte con reloj y `run_id` fijos.
- **R13 — HTML offline y tema de impresión**: parser con 0 recursos externos; dark en pantalla y
  light en `@media print`, verificados con bundle FALSO. Queda EXPLÍCITO que el `plotly.js` real y
  `Plotly.react` en `beforeprint` NO se verificaron.
- **R14 — Project theme override**: `.harmessi/report-style.json` válido cambia colores; inválido
  ⇒ FAIL sin escribir; el default no muta.
- **R15 — Portabilidad**: sin rutas absolutas ni separadores de SO hardcodeados en
  código/artefactos rastreados de reporting; manifest con rutas posix; tests sin depender del cwd.
  Se ejecutó solo en Windows: los otros SO quedan como limitación declarada, incluida la nota de
  `git core.autocrlf` sobre bytes de `reports/**`.
- **R16 — Backward compatibility**: `git diff --stat v0.5.0..HEAD` sobre `tools/dsguard
  tools/ds_profile tools/dsimpact tools/providers tools/routing tools/fallback
  tools/harmessi_bench tools/nbrunner tools/harmessi tools/ds_guard.py` vacío salvo lo
  explícitamente autorizado; el manifest de `ds_init` solo crece de forma aditiva; las 9 suites
  previas de v0.5 verdes.
- **R17 — Consistencia de versión**: `version.py` == `.ds_init/control.json` == `CITATION.cff`;
  `HARMESSI-DRIFT` de doctor OK.
- **R18 — Manifest parity**: `check_manifest_parity` OK; todo `tools/reporting/**/*.py` no-test
  tiene entrada VERBATIM; `.ds_init/control.json` regenerado con el MISMO conjunto de rutas que un
  scratch install `experiment` fresco.
- **R19 — `harmessi doctor` sobre este repo** sin `[ERROR]`.
- **R20 — Reviewer transversal**: `data-science-reviewer` sobre el conjunto de los 5 Changes de
  v0.6 (no repite revisiones individuales); hallazgos resueltos o aceptados como limitación.
- **R21 — Sin features nuevas ni publicación**: el diff del Change solo contiene
  versión/estado/verificación/correcciones de hardening; sin push, merge, tag ni release.
- **R22 — Resultado final explícito**: `READY FOR v0.6.0 RELEASE` o `NOT READY FOR v0.6.0
  RELEASE` con razones concretas y evidencia. Mientras la verificación con `plotly.js` real siga
  pendiente, el veredicto debe reflejarla como condicionante (ver design.md).

## Criterios de aceptación

- **R1**: Given los archivos antes del Change, When se aplica el cambio mecánico, Then
  `HARNESS_VERSION == "0.6.0"`, `CITATION.cff:version == 0.6.0`, `date-released` es la fecha de
  cierre, `.ds_init/control.json:harness_version == "0.6.0"`, y `git diff` de `version.py` y
  `CITATION.cff` muestra solo esas líneas.
- **R2**: Given `docs/roadmap/v0.6.md`, When se actualiza al cierre, Then el encabezado refleja el
  estado real, `[x] Change 5` figura solo si el veredicto está emitido, y `git diff` no toca
  v0.7-v0.9 ni `docs/roadmap/README.md`.
- **R3**: Given el árbol rastreado, When se corre el sweep con los patrones de R3, Then no hay
  hallazgo real (los que aparezcan son referencias al patrón de búsqueda o al registro de
  aprobación de "Federico Colombo").
- **R4**: Given las 10 suites, When se corren una por vez, Then cada una da 0 failures y todo skip
  queda listado con su causa condicional.
- **R5**: Given el paquete de tests de reporting y los tres tests de contrato nombrados, When se
  corren, Then 0 failures.
- **R6**: Given un repo git temporal en el scratchpad de la sesión, When se instala `experiment`
  (y `discovery`) con `--execute` y desde el instalado se publica el EDA, se corre `validate`,
  `render --check` y `harmessi doctor --destino`, Then todo termina sin ERROR y nada se escribe
  fuera del repo del proyecto ni del scratchpad.
- **R7**: Given el EDA genérico, When se publica dos veces, Then hash y HTML son idénticos, la
  validación da 0 FAIL, y una búsqueda de patrones privados sobre HTML y artefactos da 0 hallazgos.
- **R8**: Given un reporte `exploratory`, When su destino es de otro scope, Then FAIL
  `REPORT-DEST-CROSS-SCOPE`; When se usa como input por path, por manifest ancestro o por copia
  byte-idéntica (hash), Then `check-inputs` da FAIL en cada caso.
- **R9**: Given un reporte `model_valid` con fuente exploratory, When se llama `publish`, Then se
  rehúsa y no queda ningún archivo escrito; Given uno con policy científica y `data_cutoff` ≤
  cutoff, When se publica, Then queda publicado.
- **R10**: Given una fuente o dir input con holdout, When se solicita, Then se deniega sin abrir;
  Given `holdout_access="read"`, When el stage no es `evaluation` o falta
  `final_evaluation.authorized`, Then se deniega; solo con ambos se permite.
- **R11**: Given cuatro casos (figura sin tabla, columnas ausentes, tabla vacía, ref colgante),
  When se valida, Then cada uno da FAIL con su código.
- **R12**: Given reloj y `run_id` fijos, When se genera el manifest dos veces, Then los bytes son
  idénticos.
- **R13**: Given el HTML renderizado con bundle FALSO, When un parser lo recorre, Then hay 0
  recursos externos, dark en pantalla y light en `@media print`; and `verification.md` declara que
  `plotly.js` real y `Plotly.react` en `beforeprint` no se verificaron.
- **R14**: Given `.harmessi/report-style.json` válido, When se renderiza, Then cambian los
  colores; Given uno inválido, Then FAIL sin escribir; and el tema default no muta entre corridas.
- **R15**: Given el código y artefactos rastreados de reporting, When se buscan rutas absolutas y
  separadores de SO hardcodeados, Then 0 hallazgos; el manifest usa rutas posix; los tests pasan
  desde otro cwd; y `verification.md` declara "solo Windows" y la nota de `core.autocrlf`.
- **R16**: Given `v0.5.0..HEAD`, When se corre `git diff --stat` sobre las rutas de R16, Then
  vacío salvo lo autorizado; el manifest solo agrega entradas; las 9 suites de v0.5 pasan.
- **R17**: Given los tres archivos de versión, When se comparan, Then coinciden y doctor no
  reporta `HARMESSI-DRIFT`.
- **R18**: Given el repo tras las correcciones, When se corre `check_manifest_parity` y se
  compara `.ds_init/control.json` con un scratch install `experiment` fresco, Then la paridad da
  OK y el conjunto de rutas es idéntico.
- **R19**: Given el estado final, When se corre `harmessi doctor`, Then 0 `[ERROR]`.
- **R20**: Given el diff acumulado de los 5 Changes, When el reviewer lo revisa como unidad, Then
  cada hallazgo queda resuelto o registrado como limitación en `verification.md`.
- **R21**: Given el diff de este Change, When se inspecciona, Then solo hay versión, estado,
  verificación y correcciones acotadas de hardening, y no existe push, merge, tag ni release.
- **R22**: Given toda la evidencia, When se cierra el Change, Then `verification.md` y
  `docs/roadmap/v0.6.md` contienen el veredicto literal con razones concretas.

## Unidad de análisis / grain (condicional)

No aplica — hardening de release del harness.

## Cutoff / information boundary (condicional)

No aplica — los `data_cutoff` de R9 son de fixtures sintéticos.

## Baseline (condicional)

No aplica. La referencia de compatibilidad es el tag `v0.5.0` (R16).

## Métrica primaria (condicional)

No aplica.

## Métricas secundarias (opcional)

No aplica.

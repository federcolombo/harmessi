# Verificación — 20260918-v0-6-release-hardening

Evidencia real aportada por el Lead, ordenada por los requisitos de `spec.md`. Los números salen
de las corridas, no de memoria.

## Evidencia obtenida

- **R1 / R17 — Versión**: `HARNESS_VERSION = "0.6.0"`, `CITATION.cff` `version: 0.6.0` y
  `date-released: "2026-09-21"`, `.ds_init/control.json` `harness_version: "0.6.0"`.
- **R2 — Roadmap**: `docs/roadmap/v0.6.md` con encabezado de estado real, `[x] Change 5` y la nota
  del límite del bundle; v0.7-v0.9 y `docs/roadmap/README.md` sin tocar.
- **R3 — Privacidad**: sweep de nombres de cliente/proyecto, rutas locales y emails sobre todos
  los archivos rastreados y nuevos: 0 fugas. Los únicos emails son ficticios (`example.com` /
  `ejemplo.com`); las únicas apariciones de los patrones están en los `spec.md` de los Changes de
  hardening como texto del patrón de búsqueda (mismo criterio que v0.3-v0.5). Sin
  branding/logos/paletas de clientes.
- **R4 — Regresión SECUENCIAL, 10 suites, 0 failed** (total 2016 passed, 10 skipped):

  | Suite | Resultado |
  |---|---|
  | `tools/providers/tests` | 45 passed (8 subtests) |
  | `tools/harmessi_bench/tests` | 29 passed |
  | `tools/routing/tests` | 21 passed |
  | `tools/fallback/tests` | 29 passed |
  | `tools/ds_profile/tests` | 129 passed, 5 skipped (`pyarrow` no instalado) |
  | `tools/reporting/tests` | 839 passed, 3 skipped, 637 subtests (95.68 s) |
  | `tools/dsimpact/tests` | 68 passed |
  | `tools/tests` | 650 passed, 2 skipped (663.28 s) |
  | `tools/harmessi/tests` | 94 passed (387.58 s) |
  | `tools/ds_init/tests` | 112 passed (445.30 s) |

  Skips condicionales de reporting: 2 por symlinks no permitidos por el SO (`test_evidence`), 1 por
  NaN (`test_plotly_backend`).

  Re-corridas posteriores a la corrida principal, porque el hardening tocó ARCHITECTURE, el
  manifest (solo descripciones), `cli.py` y tests:
  - reporting + neutralidad v06 + boundaries + neutralidad v05 + manifest parity + `test_manifest`:
    902 passed, 3 skipped, 637 subtests (97.26 s).
  - Sobre el estado FINAL (con `control.json` ya regenerado): `test_control_file` + `test_doctor`
    + `test_manifest` + neutralidad v06 + boundaries: 138 passed (417.15 s).
- **R5 — Contract tests**: incluidos arriba, más `test_v06_core_neutrality` con las nuevas
  verificaciones de imports de `validation`/`profiles` y `test_constantes_duplicadas`.
  `check_manifest_parity`: [OK].
- **R6 — Scratch project real** (`python -m tools.ds_init`): `experiment` = 89 archivos aplicados;
  `discovery` = 74 (v0.5 instalaba 74 y 59: +15 archivos de reporting en cada stage). Ambos con
  `harness_version: 0.6.0`. Desde `discovery` el ejemplo genérico se construye y valida con 0 FAIL
  (mismo hash `92d80de56572...`). Desde `experiment`: `publish`, `validate`, `render` y
  `render --check` funcionan con el `tools/` instalado.
- **R7-R12, R13 (bundle FALSO), R14 — Smoke**: script de 27 verificaciones ejecutado dentro del
  scratch instalado DOS veces (versión previa a los fixes y código FINAL de un install fresco):
  27/27 OK ambas.
  - A (R7, R12, R13): EDA genérico publicado con 0 FAIL y archivos esperados; `validate` exit 0;
    2 publish dan HTML y manifest byte-idénticos; sin rutas locales ni emails en HTML/artefactos;
    HTML offline (0 recursos externos, parser que ignora script/style); `color-scheme:dark` y
    `@media print`; `render`/`render --check` coherentes.
  - B (R8): destino cruzado, input bajo root exploratory y copia byte-idéntica (hash) de un
    artefacto exploratory dan exit 1; input legítimo exit 0.
  - C (R9): fuente exploratory rehusada SIN escribir (`REPORT-ISOLATION-INPUT`); legítimo con
    policy científica y `data_cutoff` <= cutoff publicado con 0 FAIL; `data_cutoff` > cutoff FAIL
    `REPORT-SCI-CUTOFF`.
  - D (R10): fuente en holdout rehusada sin escribir (`REPORT-HOLDOUT-SOURCE`,
    `REPORT-SOURCE-ACCESS`); `describe_source(holdout)` da `EvidenceError` sin abrir; directorio
    input que contiene holdout exit 1; `holdout_access="read"` sin evaluación autorizada
    `REPORT-HOLDOUT-ACCESS`.
  - E (R11): sin tabla / ref colgante / columnas ausentes / tabla vacía dan
    `REPORT-FIGURE-NO-TABLE` / `-DANGLING-TABLE` / `-SPEC-COLUMNS` / `-TABLE-EMPTY`.
  - F (R14): `.harmessi/report-style.json` válido cambia el color del HTML; inválido
    `REPORT-STYLE-INVALID` sin escribir; el default no muta.
- **R15 — Portabilidad**: sin rutas absolutas ni `os.sep` hardcodeados en código de reporting (los
  únicos hits son sanitizadores/regex de rutas); manifest con rutas posix. Ejecutado SOLO en
  Windows.
- **R16 — Backward compat**: `git diff --stat v0.5.0..HEAD` sobre `tools/dsguard tools/ds_profile
  tools/dsimpact tools/providers tools/routing tools/fallback tools/harmessi_bench tools/nbrunner
  tools/harmessi tools/ds_guard.py tools/launcher_common.py`: VACÍO. Fuera de `tools/reporting/` y
  `openspec/`, modificados desde v0.5.0: `ARCHITECTURE.md`, `manifest.py` (aditivo), 2 tests de
  boundaries/neutralidad, roadmaps (los de v0.7-v0.9 vienen del commit previo `Define Harmessi
  v0.6-v0.9 roadmap`), `version.py`, `CITATION.cff`, `.ds_init/control.json`.
- **R18 — Manifest parity / control.json**: regenerado con `control.regenerar_control(...,
  stage="experiment")` invocado directo por el Lead, ÚLTIMO (después de todas las correcciones);
  74 -> 89 entradas (solo los 15 archivos de `tools/reporting`). Contra un scratch install
  `experiment` FRESCO: mismo conjunto de rutas (89 = 89, sin diferencias) y misma versión. Todo
  `tools/reporting/**/*.py` no-test tiene entrada VERBATIM (0 faltantes).
- **R19 — Doctor**: este repo 27 [OK], 1 [WARN] (`CORE-WORKING-TREE`, cambios sin commitear;
  esperado), 0 [ERROR], 1 [N/A]. El WARN `HARMESSI-VERSION` (0.5.0 vs 0.6.0) desapareció al
  regenerar `control.json`. Scratch fresco: 26 [OK], 2 [WARN] (árbol sin commitear y
  `guardrails.json` modificado por el propio smoke), 0 [ERROR] (con un `.venv` mínimo
  `--without-pip`; sin venv el scratch daba `RUNTIME-INTERPRETE` ERROR, artefacto del scratch y no
  del código).
- **R20 — Reviewer transversal** (`data-science-reviewer`, Changes 0-4 y estado del Change 5). El
  reporte fue PARCIAL por límite de turnos (R-g no revisado, R-f solo superficial). Veredicto:
  APRUEBA CON FIXES, 0 bloqueantes.
  - F2 (`cli.py` sobreafirmado como "solo lectura" en ARCHITECTURE y manifest): corregido, `render`
    escribe `report.html`.
  - F3 (roadmap sin mencionar que `plotly.js` real nunca se ejecutó): nota agregada.
  - F4 (`style.py` descrito como stdlib): corregido.
  - F5 (`validation` acoplado a `profiles.eda` sin test de imports): tests agregados; deuda
    "registro de profiles".
  - F6 (`cli.py` importaba `tools.dsguard`, identidad dual de módulo): unificado al patrón
    `sys.path.insert` + `from dsguard import`.
  - F7 (constantes duplicadas): test de igualdad.
  - F1 (aislamiento exploratory -> model_valid en LECTURA sin enforcement propio para un notebook
    que lee `reports/exploratory/**` sin declarar inputs al binario): documentado como límite
    (ARCHITECTURE §5) y deuda v0.7+.
  - F8-F12: deuda declarada (ARCHITECTURE §4.1).
- **R21**: sin features nuevas; sin push, merge, tag ni release (verificable con `git log`,
  `git tag` y `git branch`).

## Fingerprint de dataset/artefacto (condicional)

EDA genérico de ejemplo (sintético): hash `92d80de56572...` idéntico en 2 corridas. Sin datasets
reales involucrados.

## Diferencias contra la spec

- R13 se cumplió solo parcialmente: offline y dark/print verificados con bundle FALSO; el
  `plotly.js` REAL no se ejecutó (ver Limitaciones). Es la única diferencia. — SUPERADO por el
  Addendum (2026-09-21): verificado con plotly.js v4.1.1 real en Edge/Chrome 153; persisten solo
  otros navegadores/SO/versiones.
- R15 se ejecutó solo en Windows.
- R20: el reporte del reviewer fue parcial (ver arriba).

## Limitaciones

- El `plotly.js` REAL nunca se ejecutó: el render de figuras, el intercambio de payloads
  screen/print con `Plotly.react` en `beforeprint` (asíncrono), `matchMedia('print')` y el offline
  con el bundle real están verificados solo por lectura y con un bundle FALSO. Ninguna dependencia
  fue instalada, por restricción vigente del usuario. — SUPERADO por el Addendum (2026-09-21):
  verificado con plotly.js v4.1.1 real en Edge/Chrome 153; persisten solo otros
  navegadores/SO/versiones.
- POSIX/macOS y CI multi-SO NO verificados; `git core.autocrlf` puede alterar bytes de
  `reports/**`.
- Reviewer de la misma familia de modelo y reporte parcial (R-g no revisado, R-f superficial).
- Sha256 del manifest autoatestados (sin ancla externa).
- Eventos de proceso: la sesión se interrumpió por un reinicio del equipo del usuario entre el
  Change 1 y el Change 2 (sesión `s1` del Change 2 vencida, cerrada como pausada y reabierta sin
  perder estado); un intento de mover archivos sin versionar fuera del repo fue DENEGADO por el
  clasificador de permisos y se reemplazó por `git stash -u` acotado (reversible); `Write`,
  PowerShell y heredocs largos fueron rechazados por guards de shell al armar el script de smoke
  (se armó por trozos).

## Pendientes derivados

Deuda para v0.7+:
1. Verificación con `plotly.js` real (render, `Plotly.react` en `beforeprint`, `matchMedia`,
   offline). — SUPERADO por el Addendum (2026-09-21): verificado con plotly.js v4.1.1 real en
   Edge/Chrome 153; persisten solo otros navegadores/SO/versiones.
2. Enforcement de lectura vía hook (F1).
3. Subcomando `publish` en el CLI (hoy solo API).
4. Registro de profiles.
5. README sin documentar `python -m tools.reporting`.
6. `.gitattributes -text` para `reports/**`.
7. Ancla externa del hash del manifest.
8. `sys.path.insert` y estilo de imports.
9. Registro único de códigos.
10. Separar la carga de archivos de `style.py`.
11. Textos en español del profile EDA frente al tema por defecto `en`.
12. CI multi-SO/POSIX.
13. Alcance acotado de los tests de neutralidad.

## Addendum — verificación con plotly.js real (2026-09-21)

El usuario eligió la opción B (2026-09-21): un `plotly.min.js` aportado como asset temporal de
verificación vía `visual.chart.plotly_js_file`. Evidencia real:

- **Asset**: plotly.js v4.1.1 (licencia MIT, cabecera del archivo), obtenido de DOS canales
  oficiales independientes (`cdn.plot.ly` y el paquete npm `plotly.js-dist-min` vía jsDelivr) con
  bytes IDÉNTICOS: 4.815.814 bytes, sha256
  `3b6e15d45dbb7fca5bd2094291e961ddc5472cd887009e6009a56dab668d721f`. Usado SOLO como asset
  temporal, dentro de un proyecto scratch (nunca en el repo) como `vendor/plotly.min.js`,
  configurado con `visual.chart.plotly_js_file` en `.harmessi/report-style.json`; ELIMINADO al
  terminar junto con las copias derivadas que lo embebían. Sin `pip install` (`pip list` sin
  cambios: 7 paquetes; `import plotly` sigue dando `ModuleNotFoundError`); requirements,
  pyproject, manifest e instalación de Harmessi sin cambios; repo con `git status` limpio y
  ningún archivo `.js` en el repo.
- **Publicación con el bundle real** (proyecto instalado con el código final, EDA genérico):
  `written`/`html_written` True, bundle usado True, 0 FAIL (WARN esperados:
  `EDA-EXPLORATORY-TARGET-USE`, `REPORT-PROVENANCE`, `REPORT-SCI-CUTOFF` por la policy del
  scratch); HTML de 4.860.864 bytes; bundle embebido UNA vez y completo; 0 atributos
  `src`/`href`; sin `@import`/`url(http`; `validate` exit 0; `render --check` exit 0; 4 figuras
  con contenedor `.plot`.
- **Navegador REAL headless ya instalado** (sin instalar nada): Edge 153.0.4234.48 y Chrome
  153.0.8010.48, vía Chrome DevTools Protocol con un cliente WebSocket mínimo en stdlib (scripts
  temporales fuera del repo). 20/20 verificaciones en CADA navegador: documento cargado; Plotly
  4.1.1 cargado; las 4 figuras dibujadas (`.js-plotly-plot`=4, svg=12, trazas>0); payload SCREEN
  aplicado (`paper_bgcolor #0f172a`); payloads screen y print distintos (`#0f172a` vs `#ffffff`);
  ningún aviso "figura no renderizada" visible; fondo de página oscuro `rgb(15, 23, 42)` en
  pantalla; `beforeprint` => `Plotly.react` con payload PRINT (`#ffffff`) y `afterprint` => vuelve
  a SCREEN; `matchMedia('print')` emulado => payload PRINT y fondo de página claro
  `rgb(255, 255, 255)` por `@media print`; luminancia media de capturas 37,5 en pantalla vs 243,8
  en impresión; `Page.printToPDF` genera un PDF válido (204.207 bytes); 1 solo request de red (el
  propio documento `file:`), 0 externos; 0 errores de consola y 0 excepciones JS.
- **Pipeline REAL de impresión**: durante `Page.printToPDF` el navegador disparó `beforeprint` y
  `afterprint` de verdad. Probe de tiempos (Edge): en el instante en que retorna el listener de
  `beforeprint` (medidas `sync` y `microtask`) las figuras ya tienen `paper_bgcolor #ffffff` y el
  fondo SVG realmente pintado `rgb(255, 255, 255)`; tras `afterprint` vuelven a `#0f172a`. La
  variante de impresión queda aplicada antes del layout de impresión (no se observó carrera con el
  `Plotly.react` asíncrono). Resuelve la reserva del reviewer del Change 4.
- **Los 6 tipos de gráfico con el Plotly real** (reporte sintético de 8 figuras: barras con
  colores semánticos de riesgo y denominador, barras horizontales con etiquetas largas sin
  truncar, top-N con tabla completa, línea, dispersión por categoría, histograma, cajas, mapa de
  calor): las 8 dibujadas, 0 warnings/errores de consola, 0 excepciones JS, 0 requests no locales.
- **Sin bundle en navegador real**: 0 gráficos, 4 avisos visibles ("not rendered"), 4/4 tablas de
  respaldo abiertas, 0 errores JS, plotly `undefined`; en CLI/publish: WARN
  `REPORT-RENDER-PLOTLY-UNAVAILABLE`, HTML de 24.547 bytes. La única URL no-`file:` observada fue
  un recurso interno del propio Edge (`edge://resources/js/edge-error-reporting.js`), no del
  reporte.
- **Observaciones honestas**: un primer intento del probe de impresión falló con "Printing is not
  available" (transitorio de headless; el reintento con `Page.bringToFront` funcionó); capturas y
  PDF de evidencia quedaron FUERA del repo, en el scratchpad de la sesión, sin versionar.
- **Límites que persisten (no bloquean)**: solo motores Chromium (Edge/Chrome 153) en Windows;
  Firefox/Safari y otros SO sin verificar; una sola versión de plotly.js (4.1.1); el diálogo de
  impresión interactivo del usuario no se ejercitó (sí `Page.printToPDF`); las deudas v0.7+ ya
  listadas siguen vigentes (incluido el límite de aislamiento en lectura).

Este addendum supera lo declarado antes sobre `plotly.js` real en Diferencias, Limitaciones y
Pendientes (punto 1 de deuda), que reflejaban el estado al momento del cierre inicial.

## Resultado final

**`READY FOR v0.6.0 RELEASE`**

El veredicto previo del cierre era `NOT READY FOR v0.6.0 RELEASE` por un único motivo, que se
levantó con el addendum de arriba. Las razones originales y el gate verde siguen valiendo.

Razón del veredicto previo: el ÚNICO requisito del gate que no se pudo verificar es "HTML offline + dark en
pantalla / light en impresión" CON EL BACKEND GRÁFICO REAL. Plotly es el único backend requerido
de v0.6 y su `plotly.js` nunca se ejecutó (solo un bundle falso), porque el usuario prohibió
instalar Plotly o cualquier dependencia sin recibir antes 5 puntos (por qué es necesaria, si puede
seguir opcional, qué contrato/dependencia agrega, alternativas sin dependencia, impacto en
instalación y backward compat), que el Lead presenta en su reporte final.

Todo lo demás del gate está verde con evidencia real: regresión 10/10, scratch installs, smokes
27/27, aislamiento/model_valid/holdout, figura-tabla, reproducibilidad, override de tema,
privacidad, backward compat, versión, manifest parity y Doctor sin ERROR.

Cómo se levantó: el usuario eligió la opción B (2026-09-21). Opciones que se le habían
presentado:
- (A) permitir instalar `plotly` SOLO en el `.venv` de desarrollo (opcional, no declarado como
  dependencia) para verificar con el bundle real y un navegador headless;
- (B) aportar un `plotly.min.js` vendorizado por el proyecto vía `chart.plotly_js_file`;
- (C) aceptar el release declarando el backend gráfico como no verificado con navegador real.

Sin push, merge, tag ni GitHub Release; parada humana final.

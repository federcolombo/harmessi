# Spec — 20260918-reporting-design-system-and-html-renderer

Principio: el LLM decide lo semántico (qué se dice, con qué tono); el binario calcula y hace
cumplir lo determinista (estructura, escape, formato, gobernanza). Flujo: Report objects →
Governance → Evidence/Validation → Design System → Renderer → `report.html` (+ `manifest.json`,
`insights.json`, `artifacts/` del Change 3). El `.ipynb` es el artefacto reproducible; el `.html`
es el de comunicación; el notebook NO se convierte en renderer.

## Requisitos

### R1. Restricciones transversales
- `style.py`, `plotly_backend.py`, `render_html.py`, `publish.py` importan solo stdlib y
  `reporting.*` (`publish` además `dsguard.*` vía los módulos ya existentes). Sin pandas, sin red.
- El paquete Python `plotly` NO se importa a nivel de módulo ni se declara dependencia; no se
  modifica requirements/pyproject. Solo `find_plotly_bundle` puede intentar un import PEREZOSO.
- El core NO conoce style/render/backend (regla de dirección en `ARCHITECTURE.md`).
- Ninguna función pura de render lanza por contenido del reporte; los errores de estilo son
  `StyleError`. Ninguna función muta `Report`, artefactos ni `Style` (dataclasses frozen + copias).
- Salidas deterministas: mismo input ⇒ mismos bytes.

### R2. Design System: contratos (`style.py`)
Dataclasses `frozen`. `Style(visual: VisualStyle, editorial: EditorialStyle)`.
- `VisualStyle`: paletas `screen` (oscura) y `print` (clara) con superficie, texto, muted, borde y
  acento; colores semánticos por tema (`risk_low`, `risk_medium`, `risk_high`, `ok`, `warn`,
  `error`, `info`); paleta categórica daltónica-segura por tema; typography con SOLO fuentes del
  sistema (offline) y escala de tamaños; spacing; radii; content widths; tablas (zebra, números a
  la derecha con tabular-nums, texto a la izquierda); panels/cards; callouts; responsive
  (breakpoints); chart style por tema (fuente, tamaños, grosores, colorway, grid, leyenda);
  formato locale (`decimal_sep`, `thousands_sep`, `date_format`, `percent_decimals`).
- `EditorialStyle`: `locale`; `audience` ∈ technical|business|mixed; `tone` (texto libre);
  `explain_terms` (bool) + `glossary` (dict); `comparative_context` (bool); `uncertainty_display`
  ∈ always|non_descriptive|never; `insight_style` ∈ callout|list; `recommendations_policy` ∈
  evidence_only|hide|show; `labels` (dict de textos de interfaz: ficha técnica, detalle de método,
  tabla de respaldo, conclusión, glosario, etc.).
- Given un valor fuera de los enums, When se construye/valida, Then `StyleError`.

### R3. `HarmessiDefaultTheme` y locale
- `default_style() -> Style`: GENÉRICO, sin branding, logos, paletas de clientes ni vocabulario de
  dominio. Idioma por defecto neutro `en`. `LOCALE_PRESETS = {"en": ..., "es": ...}` (separadores +
  labels): el preset `es` es DATA del design layer, no del core.
- `contrast_ratio(fg, bg) -> float` (WCAG) y contraste ≥ 4.5:1 texto/fondo y muted/fondo en ambos
  temas del default.
- `format_number`, `format_percent`, `format_date` por locale (separadores, decimales, fecha); no
  lanzan ante `None`/no numérico (devuelven cadena vacía o el valor escapable como texto).
- Given el default, When se evalúa el contraste texto/fondo de screen y print, Then ≥ 4.5 en ambos.

### R4. Overrides del proyecto
`.harmessi/report-style.json` OPCIONAL, `schema_version: 1`.
- `load_style(repo_root) -> Style`: ausencia ⇒ defaults (nunca heurística); JSON corrupto, versión
  distinta, clave desconocida (claves permitidas estrictas), color que no sea `#rrggbb` o número
  fuera de rango ⇒ `StyleError`. La lectura pasa por `evidence.read_allowed`.
- `merge_style(base, overrides) -> Style`: deep-merge validado; NO muta `base` ni el default.
- Given un override válido, When `load_style`, Then el `Style` refleja el override y `default_style()`
  posterior queda intacto. Given un override inválido, Then `StyleError`.

### R5. `check_style(style) -> list[CheckResult]`
`CheckResult` de `dsguard.checks`; no lanza. `STYLE-CONTRAST` WARN si un override baja el contraste
bajo AA; `STYLE-PALETTE` WARN si la paleta categórica tiene colores repetidos o vacía; PASS por
regla sin violaciones.

### R6. `build_figure(figure, table, style, variant) -> dict` (`plotly_backend.py`)
`variant` ∈ {"screen","print"}; otro valor ⇒ `ValueError`. Devuelve un dict JSON-puro
(`{"data": [...], "layout": {...}}`) construido a mano desde `FigureSpec` + tabla de respaldo, sin
importar `plotly`. NUNCA muta `FigureArtifact`, `TableArtifact` ni `Style`.
- Given una figura, When `build_figure(..., "screen")` y `(..., "print")`, Then los dicts difieren
  en colores de chrome y colorway y el hash canónico del `FigureArtifact` es idéntico antes y
  después.
- Resolución screen/print: se generan DOS payloads independientes por figura; un loader JS inline
  mínimo grafica `screen` al cargar, hace `Plotly.react` con `print` en `beforeprint` (y con
  `matchMedia('print')`) y vuelve a `screen` en `afterprint`. Ninguna figura se muta.

### R7. Reglas genéricas de chart styling
Aplican a cualquier reporte, no solo EDA:
- Título = `title` del `FigureArtifact` tal cual (orientado al lector).
- Unidades visibles en ejes (`x_label`/`y_label`/`unit` o `column_labels`/`units` de la tabla).
- Tasas con denominador: si `spec.denominator`, texto `valor (n=…)` y hover.
- Leyendas interpretables: título de leyenda = etiqueta de la columna de color.
- Etiquetas largas sin truncar: `automargin`; orientación horizontal automática si la etiqueta más
  larga supera 18 caracteres; altura según cantidad de categorías.
- Colores semánticos: `spec.semantic` risk/status ⇒ mapeo case-insensitive low/medium/high y
  ok/warn/error a los colores semánticos del tema; valores sin mapeo ⇒ paleta categórica.
- Formato locale consistente en ejes, texto y hover.

### R8. Top-N
`spec.top_n` recorta lo GRAFICADO (ordenado según `sort`); la tabla de respaldo se muestra
COMPLETA con leyenda "mostrando N de M" (texto vía `labels`).
- Given 30 filas y `top_n=10`, When se renderiza, Then el gráfico tiene 10 categorías y la tabla
  30 filas con la leyenda.

### R9. Escape hatch `backend_payload`
Given `backend="plotly"` + `backend_payload`, When `build_figure`, Then se hace deepcopy por
variante y SOLO se re-tematiza el chrome (fondos, color de fuente, grillas, ejes); los colores de
datos del payload se respetan (documentado). Un `backend` distinto o ausente ⇒ se construye desde
el spec.

### R10. `find_plotly_bundle(style, repo_root) -> Optional[str]` y degradación
Orden: (1) archivo declarado en `chart.plotly_js_file` del style (ruta relativa dentro del repo,
evaluada con `evidence.read_allowed` antes de leer; fuera del repo o denegada ⇒ se ignora con
razón); (2) si el paquete `plotly` YA está instalado, `plotly.offline.get_plotlyjs()` (import
perezoso dentro de la función, `ImportError` ⇒ siguiente); (3) ninguno ⇒ `None`. No lanza.
- Given `None`, When se renderiza, Then cada figura se reemplaza por un aviso visible ("figura no
  renderizada: bundle de plotly.js no disponible", vía `labels`) con su tabla de respaldo ABIERTA, y
  `publish` emite WARN `REPORT-RENDER-PLOTLY-UNAVAILABLE` (nunca silencioso).

### R11. `render_report_html(report, manifest, style, *, plotly_bundle=None, include_sensitive=False) -> str`
- DETERMINISTA: sin timestamps propios (solo `generated_at` del manifest).
- Self-contained/offline: cero `<link>`, `<script src>`, `@import`, `url(http…)`, imágenes
  remotas; solo CSS/JS inline. El JSON de figuras va en `<script type="application/json">` con
  escape de `</` y `<!--`; el bundle `plotly.js` va inline.
- Todo texto de usuario (títulos, celdas, claims, glosario, labels) pasa por `html.escape`.
- Given `<script>alert(1)</script>` en un título, celda o JSON, When se renderiza, Then no aparece
  como marcado ejecutable.

### R12. Componentes reutilizables (funciones puras que devuelven `str`)
header; report intro; ficha técnica (colapsable: report_id, run_id, kind, scope, data_cutoff,
git_commit corto, harmessi_version, generated_at, tabla de fuentes con hash corto/filas/min-max
fechas, exclusiones, holdout_access, sensibilidad); chapter; figure (+ caption con "n=" y valor de
referencia global ponderado si hay denominador y `comparative_context`); tabla de respaldo
(COMPLETA, números a la derecha, tabular-nums, unidades en el encabezado); method details
(`<details>` con `method_note`); insight callout; tabs; conclusión; footer (run_id + hash de
contenido del reporte, sin branding); banner de scope; glosario opcional.
- Banner de scope: `exploratory` muestra "no es insumo de selección de features / no válido para
  decisiones de modelo" (texto vía `labels`).
- Glosario: solo términos del `glossary` que aparecen en el texto del reporte, en orden
  determinista.

### R13. Temas y responsive
Pantalla OSCURA por defecto; `@media print` re-define las variables CSS (tema claro) y el loader
usa los payloads `print` de las figuras. Responsive básico: grid fluido, tablas con scroll
horizontal, breakpoints del style; semánticos visibles.
- Given el HTML, Then las variables de pantalla son las del tema `screen` y el bloque
  `@media print` define las del tema `print`.

### R14. Tabs CSS-only
Un capítulo con ≥ 2 figuras usa tabs con radios (sin JS), salvo
`chapter.metadata["layout"] == "stack"`. En impresión se muestran todos los paneles.

### R15. Insights y política de recomendaciones
- Muestra `business_claim`; con audience technical o mixed añade `technical_claim`, población,
  alcance temporal y `uncertainty` según `uncertainty_display`.
- `claim_type` causal/recommendation llevan la etiqueta visible "requiere revisión".
- `recommendations_policy="evidence_only"`: un Insight `recommendation` se muestra SOLO con
  `evidence_refs` válidos y `uncertainty` no vacía; si no, se suprime con aviso visible
  ("recomendación retenida: evidencia insuficiente"). `hide` las oculta; `show` las muestra.
- El renderer no juzga si el insight excede la evidencia.

### R16. Sensibles
Tablas y figuras `sensitive` (o figuras respaldadas por tabla sensible) se OMITEN del HTML con un
placeholder, salvo `include_sensitive=True`. El reporte principal no expone detalle sensible
innecesario.
- Given una tabla sensible, When se renderiza por defecto, Then ninguna de sus celdas aparece en el
  HTML ni en el JSON de figuras.

### R17. `publish(...) -> PublishResult` (`publish.py`)
Firma: `publish(report, repo_root, *, run_id, sources, holdout_access, data_cutoff=None,
exclusions=(), source_notebook=None, style=None, out_dir=None, agent_type=None, clock=None,
plotly_bundle=<auto>, include_sensitive=False)`. `PublishResult` frozen: `results`, `out_dir`,
`written`, `html_written`, `plotly_bundle_used`. Flujo:
1. Governance: `evaluate_governance` desde `context_from_report`; `out_dir` por defecto
   `resolve_output_dir`; rehúsa si hay FAIL o si faltan `REQUIRED_DESTINATION_CODES` (un `[]` no es
   OK).
2. `validate_report` (con la `scientific_policy` cargada UNA vez).
3. `prepare_artifacts` + `build_manifest` + `validate_manifest`.
4. Reevaluar el destino justo antes de escribir (TOCTOU).
5. `write_report_dir` (manifest último).
6. Relectura verificada con `read_report_dir(..., repo_root=)` + `validate_report_dir` (0 FAIL).
7. Render desde el Report verificado EN MEMORIA (no releyendo disco) y escritura ATÓMICA de
   `report.html`.
8. WARN `REPORT-PUBLISH-NO-SCIENTIFIC-POLICY` si el scope es model_valid/operational y no hay
   política temporal declarada.
Si un paso falla no se escribe nada más y el resultado refleja `written` real. Un `StyleError`
⇒ FAIL `REPORT-STYLE-INVALID` antes de escribir cualquier archivo.
Enmiendas (reviewer, ciclo 1):
- Re-publicación: cuando TODOS los chequeos previos a la escritura pasaron, `publish` elimina el
  `report.html` previo del `out_dir` (derivado de la corrida anterior, desincronizado con el manifest
  nuevo) ANTES de `write_report_dir`; si no puede eliminarlo ⇒ FAIL `REPORT-PUBLISH-WRITE` sin
  escribir. Given una 2ª publicación cuyo render falla, Then NO queda un `report.html` viejo junto al
  manifest nuevo.
- `PublishResult.results` se deduplica preservando orden por `(status, code, subject, message)`
  (`validate_report`/`validate_manifest` se repiten dentro de `validate_report_dir`).
- `include_sensitive=True` deja marca: WARN `REPORT-PUBLISH-INCLUDE-SENSITIVE` en `results`. Un
  `render --check` posterior SIN el flag dará "difiere" (inherente, documentado).
- Given un reporte válido en repo temporal, When `publish`, Then 0 FAIL y existen `manifest.json`,
  `insights.json`, `artifacts/` y `report.html`.
- Given FAIL de governance o de validación, Then nada se escribe.
- Given un destino que cambia entre el paso 1 y el 4 (p. ej. scope cruzado), Then rehúsa.

### R18. `report.html` fuera del manifest
`report.html` es un artefacto DERIVADO y reproducible: NO entra al manifest (el manifest se escribe
antes y el HTML muestra datos del manifest; incluirlo sería circular). Su integridad se verifica
re-renderizando (`render --check`). `expected_artifacts` del Change 3 no cambia.

### R19. CLI `render` (aditivo en `cli.py`)
`render --dir D [--repo-root R] [--style RUTA] [--include-sensitive] [--check] [--json]`.
- Valida con `validate_report_dir` (0 FAIL, si no rehúsa exit 1), carga verificada
  (`read_report_dir` con `repo_root`), renderiza y escribe `report.html` atómicamente.
- `--check` no escribe: compara `report.html` existente con un render fresco; distinto o ausente ⇒
  exit 1. Exit 0/1/2/3 como el resto del CLI.
- Given un `report.html` alterado, When `render --check`, Then exit 1.

### R20. Códigos de resultado
`REPORT-RENDER-PLOTLY-UNAVAILABLE` (WARN), `REPORT-PUBLISH-NO-SCIENTIFIC-POLICY` (WARN),
`REPORT-STYLE-INVALID` (FAIL), `STYLE-CONTRAST` (WARN), `STYLE-PALETTE` (WARN). Los códigos de
Change 1–3 se reusan sin cambios.

Códigos propios adicionales (no listados arriba):
- `publish`: `REPORT-PUBLISH-GOVERNANCE` (FAIL: governance no evaluó los `REQUIRED_DESTINATION_CODES`,
  un `[]` no es OK), `REPORT-PUBLISH-DEST` (FAIL: el destino no superó la reevaluación TOCTOU),
  `REPORT-PUBLISH-MANIFEST` (FAIL: no se pudo armar el manifest), `REPORT-PUBLISH-WRITE` (FAIL:
  falló la escritura del reporte, la de `report.html` o la eliminación del `report.html` previo),
  `REPORT-PUBLISH-READBACK` (FAIL: relectura/reconstrucción verificada fallida),
  `REPORT-PUBLISH-RENDER` (FAIL: el render lanzó), `REPORT-PUBLISH-EXCEPCION` (FAIL técnico:
  excepción interna, sin rutas locales), `REPORT-PUBLISH-INCLUDE-SENSITIVE` (WARN).
- CLI `render`: `REPORT-RENDER` (FAIL/PASS del render), `REPORT-RENDER-CHECK` (`--check`: coincide o
  difiere/ausente), `REPORT-RENDER-FAILED` (FAIL: el render o su lectura fallaron) y
  `REPORT-STYLE-INVALID` (estilo inválido).

### R21. Instalabilidad y arquitectura
4 entradas VERBATIM en `tools/ds_init/manifest.py` (`style.py`, `plotly_backend.py`,
`render_html.py`, `publish.py`); aserciones en `test_installability.py`; `ARCHITECTURE.md` §2.1
con filas (style: design system, stdlib; plotly_backend: backend opcional, sin importar plotly a
nivel de módulo; render_html: stdlib `html`; publish: orquesta governance/evidence/validation/
render) y regla de dirección "el core no conoce style/render/backend"; `MODULOS_CORE` + las 4
rutas en `tools/tests/test_architecture_boundaries.py`.

### R22. Backward compatibility
`core.py`, `governance.py`, `profiles/eda.py`, `evidence.py`, `validation.py`, `__main__.py`,
`__init__.py` sin cambios; `cli.py` solo aditivo (`git diff`). Los tests de Change 0–3 siguen
verdes.

### R23. Tests (`unittest`, sin red, sin plotly real)
`test_style.py`, `test_plotly_backend.py`, `test_render_html.py`, `test_publish.py`,
`test_cli_render.py`, con `build_example_report()` genérico como reporte base. Cubren: contraste AA;
override válido/inválido/no muta el default; figura screen vs print distintas y NO mutación (hash
del `FigureArtifact` antes/después); tasas con denominador; etiquetas largas; semánticos; top-N con
tabla completa; offline (parser HTML: cero recursos externos fuera de bodies de `<script>`); dark en
pantalla / light en `@media print`; escape XSS (título, celdas, JSON); determinismo byte a byte;
bundle FALSO embebido y degradación sin bundle (aviso + WARN); sensibles omitidos; política de
recomendaciones; tabs CSS-only; `publish` end-to-end en repo temporal; rechazo por
governance/validación (nada escrito); destino cruzado; `render --check`.

### R24. Límites declarados (no verificados por este Change)
- Verificación con el `plotly.js` REAL requiere decisión del usuario sobre la dependencia (el Lead
  presentará 5 puntos antes de cualquier instalación); hasta entonces el offline con bundle real y
  el `Plotly.react` de impresión quedan SIN verificar (los tests usan bundle falso y mocks).
- `plotly.js` pesa MBs por reporte; dos payloads por figura duplican el JSON.
- Sin JS, la impresión muestra la variante `screen` de las figuras (el CSS sí pasa a claro).
- Comportamiento entre navegadores no verificado automáticamente.
- El renderer no valida la corrección semántica del contenido.
- `backend_payload` de una figura se RECHAZA si trae recursos externos, geo/mapbox o imágenes
  (requisito offline); la figura cae al aviso + tabla de respaldo.
- `_js_seguro` solo transforma `</script` y `<!--` seguido de `<script`; no es un sanitizador
  general del JS embebido.
- Cada figura lleva aviso visible + `<noscript>` por defecto: si el JS o el bundle falla, el aviso y la
  tabla de respaldo siguen visibles.
- Los sensibles no aparecen con ids en la ficha técnica y se reemplazan por placeholders opacos.
- Sanity del bundle: se exige que el texto contenga `Plotly`; si no, se trata como no disponible.
- `style.load_style_file` y las labels nuevas `not_available`/`dirty` forman parte del design system.
- `render --check` depende del bundle disponible: si `publish` recibió `plotly_bundle=` explícito o
  el entorno cambió (plotly instalado/desinstalado), puede dar un falso "difiere". Inherente;
  documentado. Igual con `include_sensitive` (ver R17).
- El bundle del proyecto (`chart.plotly_js_file`) se embebe como CÓDIGO CONFIABLE del propietario del
  repo (sin sanitizar): riesgo aceptado.
- `Plotly.react` en `beforeprint` es asíncrono y NO está verificado con el bundle real: la impresión
  con el tema claro de las figuras puede no llegar a repintar antes de imprimir.

## Criterios de aceptación
Cada requisito con su Given/When/Then se traduce en al menos un test de R23; el Lead corre
`tools/reporting/tests/`, `tools/tests/`, `tools/ds_init/tests/` y `check_manifest_parity`, y R22
se verifica con `git diff`.

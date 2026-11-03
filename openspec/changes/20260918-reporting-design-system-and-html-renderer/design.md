# Diseño — 20260918-reporting-design-system-and-html-renderer

## Decisión metodológica/técnica

### D1. El LLM decide lo semántico; el binario hace cumplir lo determinista
Qué decir, tono y qué insight incluir son del Lead. El binario garantiza estructura, escape,
formato, gobernanza y reproducibilidad. Flujo: Report objects → Governance → Evidence/Validation →
Design System → Renderer → `report.html` (+ `manifest.json`, `insights.json`, `artifacts/` de
Change 3). Cada etapa consume la salida verificada de la anterior; el renderer nunca recibe algo
que no pasó la puerta.

### D2. Notebook reproducible, HTML de comunicación
El `.ipynb` es el artefacto reproducible (código, datos); el `.html` es el artefacto de
comunicación derivado. El notebook NO se convierte en renderer: no hay ejecución de celdas para
generar el HTML, y el HTML no se parsea de vuelta.

### D3. Core intacto; cambios aditivos
`core.py`, `governance.py`, `profiles/eda.py`, `evidence.py`, `validation.py` no se modifican;
`cli.py` recibe solo el subcomando `render`. Dirección de dependencias: style/plotly_backend/
render_html/publish → reporting core, governance, evidence, validation; el core no conoce ninguno
de ellos. `FigureArtifact` sigue neutral (Change 0): `backend`/`backend_payload` ya existían como
escape hatch opcional.

### D4. Dependencias: Plotly opcional, sin importar el paquete
Restricción explícita del usuario: no se instala Plotly ni ninguna dependencia; no se toca
requirements/pyproject. Plotly es el ÚNICO backend gráfico de v0.6 pero opcional y fuera del
contrato central. El backend construye los JSON de figura como dicts a mano desde `FigureSpec` +
tabla; solo el navegador necesita `plotly.js`. Proveedor del bundle (`find_plotly_bundle`): (1)
archivo del proyecto (`chart.plotly_js_file`, relativo, `read_allowed` antes de leer); (2) paquete
`plotly` ya instalado vía `get_plotlyjs()` con import perezoso; (3) ninguno ⇒ degradación explícita
(aviso visible por figura + tabla abierta + WARN `REPORT-RENDER-PLOTLY-UNAVAILABLE`). Nunca hay
degradación silenciosa. Los tests usan bundle FALSO y mocks; la verificación con el `plotly.js`
real espera la decisión del usuario.

### D5. Design System desacoplado del renderer
`style.py` define datos (dataclasses frozen), no HTML. `VisualStyle` = tokens; `EditorialStyle` =
contrato editorial configurable (audiencia, tono, incertidumbre, recomendaciones, labels), no
hardcodeado en el core. El renderer traduce tokens a variables CSS y consume `labels`/`locale`; no
contiene texto de interfaz literal salvo los defaults `en` del preset. `LOCALE_PRESETS` (`en`,
`es`) es DATA del design layer. Overrides del proyecto vía `.harmessi/report-style.json` con
esquema estricto: ausencia ⇒ defaults (sin heurística), desconocido/corrupto ⇒ `StyleError` ⇒ FAIL
(mismo criterio "ausencia ≠ PASS silencioso, error ≠ ignorado" del Change 3). `merge_style` no
muta el default. `check_style` advierte contraste/paleta cuando un override degrada la legibilidad,
sin bloquear.

### D6. Screen/print: dos payloads por figura
Plotly materializa colores en el JSON; `@media print` no retematiza una figura renderizada. Se
generan dos payloads independientes (`screen` oscuro, `print` claro) desde spec + tabla. Un loader
JS inline mínimo grafica `screen`, hace `Plotly.react` con `print` en `beforeprint`/
`matchMedia('print')` y vuelve a `screen` en `afterprint`. Ninguna figura se muta. Con
`backend_payload` del llamador se deepcopy-a por variante y solo se re-tematiza el chrome; los
colores de datos se respetan.

### D7. Render puro y determinista
Componentes = funciones puras que devuelven `str`; sin timestamps propios (solo el `generated_at`
del manifest); orden estable; `html.escape` en todo texto de usuario; JSON de figuras en
`<script type="application/json">` con escape de `</` y `<!--`; CSS/JS inline. Mismo input ⇒ mismos
bytes, lo que habilita `render --check`.

### D8. Sensibilidad y política editorial aplicadas por el binario
Sensibles se omiten por defecto (placeholder); recomendaciones `evidence_only` se suprimen sin
`evidence_refs` válidos o sin `uncertainty`, con aviso visible; `causal`/`recommendation` llevan
etiqueta "requiere revisión". Es política determinista de presentación; si la afirmación es
correcta sigue siendo juicio humano.

### D9. `publish` como única puerta de escritura del reporte completo
Encadena governance → validación → manifest → reevaluación de destino (TOCTOU) → escritura
(manifest último) → relectura verificada (`read_report_dir(..., repo_root=)` +
`validate_report_dir`) → render desde el Report verificado en memoria → escritura atómica de
`report.html`. Lecciones aplicadas de C1–C3: `[]` de governance no es OK (se exigen
`REQUIRED_DESTINATION_CODES`), `scientific_policy` cargada una vez, lectura siempre con acceso
evaluado, mensajes sin rutas locales. WARN `REPORT-PUBLISH-NO-SCIENTIFIC-POLICY` cuando
model_valid/operational carecen de política temporal declarada (recomendación de reviewers de
C1/C3).

Enmiendas del reviewer (ciclo 1): (a) antes de escribir —solo si todos los chequeos previos pasaron—
se elimina el `report.html` previo del destino (derivado que quedaría desincronizado con el manifest
nuevo); si falla la eliminación ⇒ FAIL `REPORT-PUBLISH-WRITE`; (b) `results` se deduplica por
`(status, code, subject, message)` preservando orden (validate_report/validate_manifest se repiten en
`validate_report_dir`); (c) `include_sensitive=True` deja WARN `REPORT-PUBLISH-INCLUDE-SENSITIVE`; un
`render --check` posterior sin el flag dará "difiere". Códigos propios de publish y del CLI `render`:
ver spec R20.

### D10. `report.html` fuera del manifest
El manifest se escribe antes del HTML y el HTML muestra datos del manifest; incluirlo sería
circular. El HTML es derivado: su integridad se verifica re-renderizando desde el directorio
validado (`render --check`), no con un hash persistido.

## Target / Features / Split
No aplica (sin modelado).

## Leakage risks
- El HTML no debe filtrar contenido sensible ni de holdout: sensibles omitidos por defecto;
  el reporte llega ya validado por governance; no se lee ningún holdout.
- Lecturas nuevas (style del proyecto, bundle `plotly.js` del proyecto) pasan por `read_allowed`
  antes de abrir; ruta fuera del repo o denegada ⇒ ignorada/StyleError, nunca leída.
- Un reporte `exploratory` no autoriza selección de features: el banner lo declara, pero la
  decisión sigue siendo del metodólogo (CLAUDE.md §2).
- XSS/inyección vía contenido del reporte: escape total + escape del JSON embebido.
- TOCTOU entre validar y escribir: se reevalúa el destino y el render usa el Report verificado en
  memoria; la ventana no se elimina por completo (límite heredado de Change 3).

## Reproducibilidad
Sin aleatoriedad. Con `run_id`, `clock` y bundle fijos, mismo Report + estilo ⇒ `report.html`
idéntico byte a byte (test).

## Alternativas descartadas
- **Plotly como dependencia obligatoria**: contradice la instrucción del usuario, acopla el
  contrato central y rompe instalaciones sin red/paquete; queda opcional.
- **CSS-only para el tema de impresión de Plotly**: no retematiza el JSON ya materializado.
- **Mutar la figura para imprimir**: rompe el hash del `FigureArtifact` y la neutralidad; se
  generan variantes nuevas por copia.
- **Meter `report.html` en el manifest**: circular; se verifica por re-render.
- **Framework CSS/JS**: peso, red y dependencias; CSS/JS mínimos inline.
- **Branding/paletas de cliente/vocabulario de dominio**: fuera de alcance; el default es genérico.
- **Jinja/templating externo**: dependencia nueva y menor control del escape; componentes puros en
  stdlib.
- **Convertir el notebook en renderer**: mezcla ejecución con presentación y no es determinista.

## Riesgos
- Bundle real de `plotly.js` sin verificar hasta decisión del usuario; el camino de degradación sí
  se prueba.
- `plotly.js` pesa MBs y hay dos payloads por figura: HTML grande.
- Tema print de figuras depende de JS (`beforeprint`); sin JS se imprime la variante screen.
- Diferencias entre navegadores en `beforeprint`/`matchMedia`.
- Contraste de overrides de proyecto: solo WARN, no bloqueo.
- `cli.py` es archivo compartido: cambio aditivo y tests previos deben seguir verdes.
- `backend_payload` con recursos externos/geo/mapbox/imágenes se rechaza (offline); `_js_seguro` solo
  transforma `</script` y `<!--` seguido de `<script`; aviso visible + `<noscript>` por defecto en
  figuras; sensibles sin ids en la ficha técnica y con placeholders opacos; sanity del bundle
  (`Plotly`); `load_style_file`; labels nuevas `not_available`/`dirty`.
- `render --check` depende del bundle disponible y de `include_sensitive`: un `plotly_bundle=`
  explícito en `publish`, un cambio de entorno o el flag pueden dar un falso "difiere" (inherente).
- El bundle del proyecto se embebe como código confiable del propietario (riesgo aceptado).
- `Plotly.react` en `beforeprint` es asíncrono y NO está verificado con el bundle real.

## Aprobación humana
El registro de aprobación vive en `proposal.md` (sección "Aprobación").

# Verificación — 20260918-reporting-design-system-and-html-renderer

## Evidencia obtenida

- **Tests del Change** (`pytest tools/reporting/tests tools/tests/test_v06_core_neutrality.py tools/tests/test_architecture_boundaries.py tools/tests/test_v05_core_neutrality.py tools/tests/test_manifest_dsguard_parity.py tools/ds_init/tests/test_manifest.py`):
  - Tandas A/B por módulo: `test_style` 57 passed; `test_plotly_backend` 51 passed, 1 skipped (tras alinear el backend a la API real de `style.py`: 110 passed, 1 skipped entre ambos); `test_render_html` 42 passed.
  - 1ª corrida completa con `publish`: 838 passed + 17 failed. Bug real de `publish.py`: pasaba a governance los descriptores de fuente completos (`kind: generated`) en lugar de las rutas `str` de las fuentes `file`; corregido. Resultado: 855 passed, 3 skipped, 591 subtests (con 2 reintentos técnicos sobre tests: un helper de test que trataba `None` como "usar default").
  - Tras los fixes del reviewer: 895 passed + 1 failed (aserción de test errónea: `REPORT-PROVENANCE` se emite legítimamente 2 veces, con distinto subject). Final: `896 passed`, 3 skipped, 637 subtests, en `93.73s`.
  - Los 3 skips: `test_evidence.py:253` ("el SO no permite symlinks"), `:899` ("el SO no permite symlinks de archivo") y `test_plotly_backend.py:500` ("el core rechaza payloads con NaN", skip condicional).
- **Paridad de manifest** (`check_manifest_parity`): `[OK]`.
- **Suites lentas que consumen `MANIFEST`** (`tools/ds_init/tests/test_control_file.py` + `tools/harmessi/tests/test_doctor.py`): `94 passed` en `427.08s`, con las 4 entradas de manifest del Change; los fixes posteriores no tocaron `manifest.py`.
- **Smoke E2E real de `publish`** (repo temporal, ejemplo genérico, bundle JS FALSO):
  - `written` y `html_written` True, 0 FAIL. HTML de ~43.7 KB con bundle y ~24.5 KB sin bundle.
  - 0 referencias externas (`src`/`href` a `http(s)://` o `//`; parser HTML ignorando cuerpos de script/style). `@media print` presente; tema oscuro por defecto (`color-scheme:dark`, `:root` con superficies, textos, semánticos y paleta categórica).
  - Bundle falso embebido exactamente 1 vez; misma corrida repetida: HTML byte-idéntico.
  - Sin bundle: WARN `REPORT-RENDER-PLOTLY-UNAVAILABLE` visible y aviso en el HTML.
  - Estructura: header, intro, ficha técnica colapsable, capítulos con paneles, figura con tabla de respaldo `<details>`, callouts, método.
- **Reviewer** (`data-science-reviewer`, 1 pasada): APRUEBA CON FIXES; 0 bloqueantes; 5 importantes:
  1. `backend_payload` permitía recursos externos (imágenes, trazas geo/mapbox, `topojsonURL`, `layout.images`): ahora `BackendPayloadError` + degradación con aviso visible; `layout.template` descartado.
  2. `_js_seguro` reescribía `<!--` del bundle (podía romper código válido): ahora solo `</script` y `<!--` seguido de `<script`.
  3. Fallo silencioso de figuras sin JS o con bundle defectuoso: aviso visible por defecto reemplazado al graficar + `<noscript>`, tabla de respaldo abierta.
  4. Re-publicación fallida dejaba un `report.html` viejo junto a un manifest nuevo: se elimina el HTML previo justo antes de escribir.
  5. `PublishResult.results` con duplicados por construcción: deduplicado por `(status, code, subject, message)`.
  - Menores aplicados: sensibles sin ids en la ficha técnica y con placeholders opacos; `include_sensitive=True` emite WARN `REPORT-PUBLISH-INCLUDE-SENSITIVE`; regex con `fullmatch` y fuentes sin comillas sueltas; literales de idioma movidos a labels de style (`not_available`, `dirty`, `sample_size`); orientación horizontal también para `box`; formato de floats sin ceros espurios; `cli` reutiliza `style.load_style_file` (`--style` explícito inexistente da error, no default) y sanea rutas; sanity `Plotly` del bundle; heatmap sin concatenar etiquetas crudas; hallazgo 15 (cosmético) resuelto.
  - No se hizo 2ª pasada de reviewer (no hubo bloqueantes); los fixes se verificaron con tests y con el smoke E2E.
- **Privacidad**: grep de nombres, rutas y emails privados en `tools/reporting`, este Change y `ARCHITECTURE.md`: 0 resultados. Sin branding, logos, paletas de clientes ni vocabulario de dominio. Sin `import plotly` a nivel de módulo ni en tests (verificado por grep); `python -c "import plotly"` da `ModuleNotFoundError`: NO se instaló ninguna dependencia.
- **Alcance / backward compat**: `git diff` de `core.py`, `governance.py`, `evidence.py`, `validation.py` y `profiles/eda.py` vacío. `cli.py` cambió solo aditivamente (`render`).

## Fingerprint de dataset/artefacto

No aplica -- infraestructura del harness con datos sintéticos, sin dataset real.

## Diferencias contra la spec

- Enmiendas (R17, R20, R24, D9, riesgos) re-aprobadas por hash.
- Códigos propios documentados: `REPORT-PUBLISH-*`, `REPORT-RENDER*`, `REPORT-STYLE-INVALID`.
- `report.html` fuera del manifest (artefacto derivado; se verifica con `render --check`).

## Limitaciones

1. El `plotly.js` REAL NUNCA se ejecutó: todo el comportamiento de figuras (payloads screen/print, `Plotly.react` en `beforeprint` —asíncrono, puede no terminar antes del layout de impresión—, `matchMedia`) está verificado solo por lectura y con un bundle FALSO. El offline y dark/print con el bundle real quedan SIN verificar hasta que el usuario decida sobre la dependencia: restricción explícita vigente (2026-09-21: "NO instales Plotly ni ninguna dependencia nueva"). El Lead presentará los 5 puntos (por qué es necesaria, si puede seguir opcional, contrato/dependencia, alternativas sin dependencia, impacto en instalación y backward compat) antes de cualquier `pip install`.
2. Sin JS, la impresión muestra la variante screen.
3. `render --check` compara contra el bundle disponible AHORA (puede dar un falso "difiere" si cambió el entorno o `publish` recibió `plotly_bundle=` explícito).
4. El bundle del proyecto se embebe como código confiable del propietario.
5. `include_sensitive=True` no queda marcado en el manifest (solo WARN en `publish`).
6. `git core.autocrlf` puede alterar bytes de `reports/**` (pendiente hardening: `.gitattributes -text`).
7. Heatmap, box e histograma sin verificar visualmente en navegador real.
8. El loader `beforeprint`/`afterprint`/`matchMedia` y el HTML con el `plotly.js` real no se ejecutaron.

## Pendientes derivados

Para el Change 5 (hardening): verificar offline/dark/print con el `plotly.js` real (previa decisión del usuario); scratch project con `ds_init`; manifest parity y regeneración de `.ds_init/control.json`; `.gitattributes` para `reports/**`; ancla externa del hash del manifest; smokes exploratory/model_valid/holdout con el ejemplo genérico; privacidad transversal; portabilidad; backward compatibility; versión (`HARNESS_VERSION` 0.6.0); Doctor sin ERROR.

## Resultado final

CERRADO -- Change 4 cumple la spec (R1-R24 enmendada), con la verificación del `plotly.js` real PENDIENTE de decisión del usuario.

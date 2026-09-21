# Propuesta — 20260918-reporting-design-system-and-html-renderer

## Problema
Tras el Change 3 un reporte es auditable en disco (manifest, artefactos con hash, puerta
`validate_report_dir`), pero no es comunicable: no existe artefacto legible para un lector no
técnico. Falta:
- Un **Design System** desacoplado de cualquier renderer (tokens visuales + contrato editorial),
  para que el mismo `Report` se presente distinto sin tocar el core ni el renderer.
- Un **renderer HTML self-contained/offline** que consuma solo objetos ya validados y respete la
  gobernanza (sensibles, scope exploratory, recomendaciones sin evidencia).
- Un **backend gráfico** que no contamine el contrato neutral: `FigureArtifact` no conoce Plotly
  (`tools/reporting/core.py:569`, `backend`/`backend_payload` opcionales en `:581-582`).
- Un **flujo único de publicación** que encadene governance → validación → evidencia → render sin
  atajos (TOCTOU, `[]` tomado como OK, escritura parcial).
- Una **estrategia screen/print** compatible con la limitación real de Plotly: los colores quedan
  materializados en el JSON de la figura y `@media print` no los retematiza
  (`docs/roadmap/v0.6.md`, Change 4).

## Objetivo
Renderizar un `Report` validado a un `report.html` determinista y offline, con Design System
desacoplado (`VisualStyle` + `EditorialStyle`), tema oscuro en pantalla y claro en impresión, y un
`publish` que haga cumplir el flujo completo.

## Evidencia
- Contratos que se consumen sin modificar: `core.py:285` `TableArtifact` (`units :292`,
  `column_labels :293`, `sensitive :295`); `:466` `FigureSpec` (`top_n :476`, `denominator :481`,
  `semantic :482`, `columns_used :520`); `:569` `FigureArtifact` (`sensitive :580`, `backend :581`,
  `backend_payload :582`); `:652` `Insight`; `:746` `Chapter` (`method_note :755`); `:807` `Report`.
- Evidencia/validación (Change 3): `evidence.py:156` `read_allowed`, `:336` `expected_artifacts`,
  `:350` `prepare_artifacts`, `:458` `build_manifest`, `:520` `manifest_to_bytes`, `:528`
  `write_report_dir`, `:622` `report_from_bytes`, `:667` `read_report_dir`; `validation.py:405`
  `validate_report`, `:626` `validate_manifest`, `:1045` `validate_report_dir`.
- Governance (Change 1): `governance.py:70` `REQUIRED_DESTINATION_CODES`, `:219`
  `resolve_output_dir`, `:266` `context_from_report`, `:943` `evaluate_destination`, `:949`
  `evaluate_governance`, `:955` `output_allowed`.
- Roadmap: `docs/roadmap/v0.6.md` sección "Change 4".
- `spec.md` de Change 3 R2: `report.html` "Change 4, no generado acá".

## Supuestos descartados
- "El notebook puede ser el renderer": el `.ipynb` es el artefacto REPRODUCIBLE; el `.html` es el de
  COMUNICACIÓN. Convertir el notebook mezcla ejecución con presentación y no es determinista.
- "`@media print` alcanza para el tema de impresión": no retematiza una figura Plotly ya
  materializada; se generan dos payloads por figura.
- "Plotly debe ser dependencia": no. Es backend opcional; el proyecto no puede instalarlo sin
  decisión del usuario (ver Alcance y R1).
- "El HTML puede entrar al manifest": sería circular (el HTML muestra datos del manifest).

## Alcance
- `tools/reporting/style.py`: Design System (`VisualStyle`, `EditorialStyle`, `Style`,
  `HarmessiDefaultTheme`, presets de locale, overrides `.harmessi/report-style.json`, formato).
- `tools/reporting/plotly_backend.py`: construcción de JSON de figura a mano (dicts) desde
  `FigureSpec` + tabla, variantes screen/print, `find_plotly_bundle`. SIN importar el paquete
  `plotly` a nivel de módulo.
- `tools/reporting/render_html.py`: renderer HTML puro, determinista, offline.
- `tools/reporting/publish.py`: orquestación governance → validación → evidencia → render.
- `tools/reporting/cli.py`: subcomando aditivo `render`.
- Instalabilidad (`manifest.py`, `test_installability.py`), `ARCHITECTURE.md`, `MODULOS_CORE`.
- Tests: `test_style.py`, `test_plotly_backend.py`, `test_render_html.py`, `test_publish.py`,
  `test_cli_render.py`.

## Fuera de alcance
- Modificar `core.py`, `governance.py`, `profiles/eda.py`, `evidence.py`, `validation.py`.
- Instalar Plotly o cualquier dependencia; modificar requirements/pyproject.
- Branding, logos, paletas de clientes, vocabulario de dominio, otras librerías gráficas, editor
  visual de themes, framework CSS, servidor web, dashboard interactivo, Jinja/templating externo.
- Verificar el offline con el `plotly.js` real (queda SIN verificar hasta la decisión del usuario).
- Juzgar si un insight es correcto o suficiente: sigue siendo del Lead/metodólogo/reviewer.

## Holdout policy
No aplica: el Change no lee ni escribe holdouts. Toda lectura de archivo (fuentes, bundle
`plotly.js` del proyecto, style del proyecto) pasa por `evidence.read_allowed`; los tests usan
repos temporales y datos sintéticos.

## Impacto en production-readiness
`report.html` es el entregable de comunicación de las etapas de evaluación/producción futuras; sin
cambio de comportamiento del harness existente (cambios aditivos).

## Aprobación
- Usuario: Federico Colombo
- Fecha: 2026-09-18
- Alcance aprobado: Change 4 — reporting-design-system-and-html-renderer (docs/roadmap/v0.6.md)
- Versión de artefactos referenciada: esta versión de proposal.md, spec.md, design.md, tasks.md
  (commit de este Change)
- Cita o descripción fiel de qué se aprobó: "Ejecutá autónomamente Harmessi v0.6 completa: ...
  Change 4 — reporting-design-system-and-html-renderer ... Para cada Change: audit → SDD →
  implementación → tests → reviewer → fixes → re-tests → verification → close → commit local" y
  "NO instales Plotly ni ninguna dependencia nueva por tu cuenta ... antes de ejecutar cualquier
  pip install, modificar requirements/pyproject o incorporar una dependencia nueva al proyecto,
  STOP" (instrucciones explícitas del usuario, 2026-09-18 y 2026-09-21, bajo el Contrato de
  autonomía de docs/roadmap/README.md).

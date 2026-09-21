# Tareas — 20260918-reporting-design-system-and-html-renderer

estado: cerrada

## Invocaciones planificadas
1. **Writer SDD** (esta): completa `proposal.md`, `spec.md`, `design.md`, `tasks.md` y el alcance
   de `control.json`. Sin código.
2. **Writer implementación, tanda A**: `tools/reporting/style.py` y
   `tools/reporting/tests/test_style.py` (R2-R5).
3. **Writer implementación, tanda B** (en paralelo con A): `tools/reporting/plotly_backend.py` y
   `tools/reporting/tests/test_plotly_backend.py` (R6-R10).
4. **Writer implementación, tanda C**: `tools/reporting/render_html.py` y
   `tools/reporting/tests/test_render_html.py` (R11-R16); depende de A y B.
5. **Writer implementación, tanda D**: `tools/reporting/publish.py`,
   `tools/reporting/cli.py` (subcomando `render`, aditivo), `tools/reporting/tests/test_publish.py`,
   `tools/reporting/tests/test_cli_render.py`, 4 entradas de `tools/ds_init/manifest.py`,
   aserciones de `test_installability.py`, filas de `ARCHITECTURE.md` §2.1 y `MODULOS_CORE` (R17-R21).
   Ninguna tanda ejecuta nada.
6. **Lead corre tests**: `tools/reporting/tests/`, `tools/tests/`, `tools/ds_init/tests/`,
   `test_manifest_dsguard_parity.py` y `python -m tools.ds_init.check_manifest_parity`; entrega
   resultados al reviewer.
7. **data-science-reviewer**: revisión independiente (fuga por HTML, sensibles, XSS, offline real,
   determinismo, política de recomendaciones, mutación de artefactos, TOCTOU en `publish`, límites
   honestos, fixtures sin datos reales).
8. **Writer fixes**: corrige hallazgos del reviewer y de los tests; el Lead re-corre.
9. **Writer cierre**: escribe `verification.md` (números de la corrida real, no de memoria) y
   tilda `[x] Change 4` en `docs/roadmap/v0.6.md`.

## Tareas
- [ ] `style.py`: dataclasses `VisualStyle`, `EditorialStyle`, `Style`, `StyleError` (R2)
- [ ] `style.py`: `default_style()`, `LOCALE_PRESETS`, `contrast_ratio`, `format_*` (R3)
- [ ] `style.py`: `load_style`, `merge_style`, `check_style` (R4, R5)
- [ ] `tools/reporting/tests/test_style.py` (R23)
- [ ] `plotly_backend.py`: `build_figure` screen/print sin mutación, reglas de chart styling,
  top-N, escape hatch `backend_payload` (R6-R9)
- [ ] `plotly_backend.py`: `find_plotly_bundle` con import perezoso y degradación (R10)
- [ ] `tools/reporting/tests/test_plotly_backend.py` (R23)
- [ ] `render_html.py`: `render_report_html` determinista, offline, escape total (R11)
- [ ] `render_html.py`: componentes, temas, tabs CSS-only, política de recomendaciones, sensibles
  (R12-R16)
- [ ] `tools/reporting/tests/test_render_html.py` (R23)
- [ ] `publish.py`: `publish` y `PublishResult` con el flujo de 8 pasos (R17, R18, R20)
- [ ] `cli.py`: subcomando `render` con `--check` (R19)
- [ ] `tools/reporting/tests/test_publish.py` y `test_cli_render.py` (R23)
- [ ] `tools/ds_init/manifest.py`: 4 entradas VERBATIM; aserciones en `test_installability.py` (R21)
- [ ] `ARCHITECTURE.md` §2.1 (4 filas + regla "core no conoce style/render/backend") y
  `MODULOS_CORE` con las 4 rutas (R21)
- [ ] Verificar R22: `core.py`, `governance.py`, `profiles/eda.py`, `evidence.py`, `validation.py`,
  `__main__.py`, `__init__.py` sin cambios; `cli.py` solo aditivo (`git diff`)
- [ ] Lead: correr tests y `check_manifest_parity`
- [ ] data-science-reviewer: revisión independiente
- [ ] Aplicar fixes del reviewer y re-correr tests
- [ ] `openspec/changes/20260918-reporting-design-system-and-html-renderer/verification.md` (al
  cierre), incluyendo el límite R24 (bundle real sin verificar)
- [ ] `docs/roadmap/v0.6.md`: tildar `[x] Change 4`

## Dependencias
- Change 0 (`20260918-reporting-core`): `Report`, `Chapter`, `Insight`, `TableArtifact`,
  `FigureArtifact`, `FigureSpec`, `canonical_json`, `content_sha256`.
- Change 1 (`20260918-reporting-governance`): `GovernanceContext`, `context_from_report`,
  `evaluate_governance`, `resolve_output_dir`, `REQUIRED_DESTINATION_CODES`.
- Change 2 (`20260918-eda-profile`): `build_example_report()` de `examples/eda_generic.py`.
- Change 3 (`20260918-report-evidence-and-validation`): `read_allowed`, `prepare_artifacts`,
  `build_manifest`, `write_report_dir`, `read_report_dir`, `report_from_bytes`, `validate_report`,
  `validate_manifest`, `validate_report_dir`.
- Ninguna dependencia nueva: NO se instala Plotly ni se modifica requirements/pyproject. Cualquier
  instalación exige STOP y decisión del usuario (el Lead presentará 5 puntos).
- Ningún holdout, dataset sellado, `data/raw`, `.claude/guardrails.json` ni `.env*` se lee o
  modifica.

## Próximo paso exacto
Invocaciones 2 y 3 (tandas A y B en paralelo): con el Change en estado aprobado por el Lead,
implementar `style.py` + `test_style.py` y `plotly_backend.py` + `test_plotly_backend.py` dentro de
`alcance.rutas_autorizadas` de `control.json`, siguiendo `spec.md` R2-R10 y R23. No ejecutar nada;
reportar al Lead qué correr.

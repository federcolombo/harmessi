# Propuesta — 20260918-eda-profile

## Problema
El Reporting Core (Change 0) define contratos neutrales (`Report`, `Chapter`, `Insight`,
`TableArtifact`) y la gobernanza (Change 1) decide si un reporte puede escribirse en un destino,
pero no existe todavía ningún profile que exprese qué significa "un EDA" sobre esos contratos.
Sin él, un EDA es un checklist de técnicas o un documento libre: no queda registrado qué bloques
del análisis se evaluaron, cuáles no aplican, cuáles se omitieron y por qué. Dos riesgos
concretos:

- Un EDA "completo" medido por cuántas técnicas ejecuta incentiva el ritual (correr todo sin
  conclusión) y tapa lo que se debió justificar y no se hizo.
- Un EDA que mide asociación con el target sin revisar si el campo estaba disponible antes del
  corte reintroduce leakage por la puerta de la exploración (CLAUDE.md §2, anti-leakage).

## Objetivo
Definir el EDA como un profile (`tools/reporting/profiles/eda.py`) encima del Reporting Core, que
verifica ESTRUCTURA y aplicabilidad explícita por bloque de análisis, sin hardcodear ninguna
técnica y sin modificar `core.py`, más un ejemplo genérico reutilizable en los Changes 3-5.

## Evidencia
- `docs/roadmap/v0.6.md`, sección "Change 2 — eda-profile": "EDA debe ser un profile encima del
  Reporting Core, no el Reporting Core mismo"; lista 9 bloques candidatos (`data_quality`,
  `univariate`, `bivariate_target`, `multivariate`, `temporal`, `concentration`, `segmentation`,
  `entity_relations`, `process_cycles`) "a evaluar, no a ejecutar incondicionalmente".
- `tools/reporting/core.py:45-46`: `REPORT_KINDS` incluye `"eda"`; `DECISION_SCOPES` =
  `exploratory | model_valid | operational` (ortogonales al kind).
- `tools/reporting/core.py:746-756` y `:807-820`: `Chapter.metadata` y `Report.metadata` son
  dicts genéricos JSON-puros; el core no interpreta su contenido, por lo que el profile puede
  usarlos como canal de declaración sin tocar el core.
- `tools/reporting/core.py:652-664` (`Insight`): `evidence_refs`, `population`, `time_scope`,
  `claim_type`, `uncertainty` permiten exigir que un bloque aplicado tenga al menos una
  conclusión trazable. `tools/reporting/core.py:285-295` (`TableArtifact`): base de la tabla de
  cobertura.
- Consulta metodológica, 2026-09-18, 8 puntos, adoptados con los ajustes indicados (Lead). Sus
  resultados son la base de las decisiones de spec.md y design.md: el binario verifica
  estructura y el metodólogo/reviewer evalúan adecuación; sin score de cobertura; estado
  `omitted` con razón; bloque `leakage_review` obligatorio para asociación con target en scopes
  no exploratorios; ninguna técnica hardcodeada.

## Supuestos descartados
- "Un EDA completo es el que ejecuta todos los bloques": descartado; completo significa que
  todo bloque fue evaluado y lo no realizado está justificado.
- "El binario puede juzgar si el análisis es adecuado": descartado; solo filtra lo
  obviamente vacío. La suficiencia de razones e insights y la adecuación metodológica quedan
  para metodólogo/reviewer (deuda declarada, no garantía).
- "Hace falta un campo `fit_population` para marcar con qué población se ajusta": descartado; se
  consume el cutoff/tiempo de `.harmessi/scientific-policy.json` (como dict) y la población se
  audita por el capítulo `population_and_unit`.

## Hipótesis
No aplica (cambio de diseño de contratos, no prueba una hipótesis metodológica).

## Alcance
- `tools/reporting/profiles/__init__.py` (vacío) y `tools/reporting/profiles/eda.py`:
  `BlockInfo`, `BLOCK_CATALOG` (11 bloques), `STATES`, `BlockEvaluation`, `derive_evaluations`,
  `coverage_table`, `build_eda_report`, `validate_eda_report` (reglas `EDA-*`).
- `tools/reporting/examples/__init__.py` (vacío) y `tools/reporting/examples/eda_generic.py`:
  `build_example_report()` con datos sintéticos genéricos, stdlib solamente.
- Tests `tools/reporting/tests/test_eda_profile.py` y `test_eda_example.py`; aserciones en
  `test_installability.py`.
- Cuatro entradas VERBATIM en `tools/ds_init/manifest.py`; filas en `ARCHITECTURE.md` §2.1;
  dos rutas en `MODULOS_CORE` de `tools/tests/test_architecture_boundaries.py`.
- Tildar `[x] Change 2` en `docs/roadmap/v0.6.md` solo en la invocación de cierre.

### Extensión del catálogo candidato del roadmap (REVERSIBLE)
El roadmap lista 9 bloques. Se agregan 2, adoptados de la consulta metodológica, declarados
aquí como extensión y reversibles (quitarlos es borrar dos entradas del catálogo):
- `leakage_review`: responde "¿el campo/asociación estaba disponible antes del corte?" (campos
  post-outcome, snapshot vs evento, proxies del target). Motivo: sin este bloque, `bivariate_target`
  puede producir asociaciones que son leakage y nada en el reporte lo cuestiona.
- `population_and_unit`: unidad de análisis, inclusión/exclusión, denominador, cobertura
  temporal. Motivo: reemplaza al descartado `fit_population`; toda tasa o porcentaje del EDA es
  ambiguo sin denominador y población explícitos.
NO se agrega `target_definition`: definir el target es decisión del usuario (CLAUDE.md §3).

## Fuera de alcance
- Modificar `core.py`, `governance.py` o cualquier archivo existente más allá de las adiciones
  listadas (manifest, `ARCHITECTURE.md`, `MODULOS_CORE`, `test_installability.py`, roadmap).
- Renderizado (Plotly/HTML) y validación de evidencia numérica: Changes 3 y 4.
- Calcular técnicas: el profile no implementa PCA, clustering, RFM, Pareto, cohortes, bootstrap,
  pruebas de hipótesis ni ninguna otra; el proyecto decide cómo calcular.
- Leer `.harmessi/scientific-policy.json` de disco (se recibe como dict).
- Notebooks, datos reales, holdouts y `data/raw`.

## Holdout policy
No aplica: ninguna tarea toca ni lee holdouts, datasets sellados, `data/raw` ni
`.claude/guardrails.json`. El ejemplo usa datos sintéticos generados en memoria.

## Impacto en production-readiness
Ninguno directo. El scope `operational` recibe reglas más estrictas (`EDA-OMITTED-SCOPE`,
`EDA-LEAKAGE-REVIEW-REQUIRED`) para cuando el profile se use en esa etapa.

## Criterios de aceptación
Ver `spec.md` (R1-R24, Given/When/Then verificables).

## Decisión técnica
Ver `design.md`.

## Aprobación
- Usuario: Federico Colombo
- Fecha: 2026-09-18
- Alcance aprobado: Change 2 — eda-profile (docs/roadmap/v0.6.md)
- Versión de artefactos referenciada: esta versión de proposal.md, spec.md, design.md, tasks.md
  (commit de este Change)
- Cita o descripción fiel de qué se aprobó: "Ejecutá autónomamente Harmessi v0.6 completa: ...
  Change 2 — eda-profile ... Para cada Change: audit → SDD → implementación → tests → reviewer →
  fixes → re-tests → verification → close → commit local" (instrucción explícita del usuario,
  2026-09-18, bajo el Contrato de autonomía de docs/roadmap/README.md).

## Motivo de rechazo
No aplica.

## Desacuerdo registrado
No aplica.

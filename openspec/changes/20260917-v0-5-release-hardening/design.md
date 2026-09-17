# Diseño — 20260917-v0-5-release-hardening

## Decisión metodológica/técnica

Reutilizar exactamente el mismo patrón de hardening ya usado en
`openspec/changes/20260917-v0-4-release-hardening`, sin inventar un proceso nuevo: la misma
estructura de gate (versión → docs → regresión completa → evals mínimas → smoke cross-provider →
smoke routing/fallback → backward compatibility/scratch installs → privacidad/portabilidad →
reviewer transversal → regeneración de `.ds_init/control.json` → `harmessi doctor` final). La
única diferencia de alcance frente a v0.4 es que este Change tiene 4 capacidades nuevas que
documentar en README (`providers`/`routing`/`fallback`/`harmessi-bench`) en vez de las de v0.4, y
9 suites de regresión en vez de 5 (las 5 de v0.4 más las 4 nuevas de v0.5:
`tools/providers/tests`, `tools/harmessi_bench/tests`, `tools/routing/tests`,
`tools/fallback/tests`).

## Target (condicional — feature_engineering, modeling)

No aplica.

## Features permitidas/prohibidas (condicional — feature_engineering)

No aplica.

## Estrategia de split/validación (condicional — holdout involucrado, modeling, evaluation)

No aplica.

## Leakage risks (condicional — feature_engineering, data_preparation, modeling)

No aplica — este Change no produce features ni modelos de un proyecto DS; es hardening de release
del harness. No existe una noción de leakage temporal/de target aplicable acá. El riesgo análogo
más cercano — filtrar información de proyectos de cliente reales (AGD/UNCO-Intelligence/rutas
locales) dentro de la documentación pública de Harmessi — se cubre explícitamente en R3
("privacidad transversal") de `spec.md`, no como un riesgo de leakage metodológico.

## Reproducibilidad (opcional — solo si se desvía del default: RANDOM_STATE fijo, .venv)

No aplica — sin aleatoriedad involucrada en cambios de versión/documentación. Los tests
determinísticos y las corridas reales de `harmessi-bench`/`fallback` referenciadas en
`verification.md` ya declaran su propia reproducibilidad en sus Changes de origen.

## Alternativas descartadas

1. **Crear un `CHANGELOG.md` nuevo**: descartado. No es el patrón ya establecido en este repo — ni
   v0.3 ni v0.4 lo usaron; las release notes de cada versión viven en el archivo de roadmap
   correspondiente (`docs/roadmap/v0.X.md`) más el `verification.md` del Change de hardening. Crear
   un archivo nuevo para v0.5 rompería esa consistencia sin necesidad real.
2. **Registrar los 4 paquetes nuevos de v0.5 (`tools/providers`, `tools/routing`, `tools/fallback`,
   `tools/harmessi_bench`) en el manifiesto de instalación de `tools/ds_init/`**: descartado — ver
   "Supuestos descartados" de `proposal.md`. `tools/harmessi/cli.py` (el CLI base ya existente desde
   v0.2) tampoco está en ese manifiesto; el patrón establecido es que estas herramientas se corren
   desde un checkout de Harmessi, no se instalan en el destino.

## Riesgos

Sin una segunda familia de modelo/provider real disponible en este entorno (solo `claude_code` con
CLI instalada), no es posible ejecutar un "reviewer transversal" de alto riesgo con una familia de
modelo genuinamente distinta al writer — misma limitación ya documentada explícitamente en los
Changes 2 y 3 de v0.5. Este Change no la resuelve tampoco; se reafirma honestamente en
`verification.md` en vez de fingir una garantía inexistente.

## Aprobación humana

El registro de aprobación (usuario, fecha, alcance, versión de artefactos, cita) es único por
cambio y vive en la sección "Aprobación" de `proposal.md` — no se duplica acá.

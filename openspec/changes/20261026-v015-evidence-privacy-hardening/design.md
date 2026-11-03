# Diseño — 20261026-v015-evidence-privacy-hardening

## Decisión metodológica/técnica
Cambio técnico (no metodológico). Principios: (1) tests deterministas sobre comportamiento observable; (2) aditivo y retrocompatible: nada que cambie contratos persistidos sin fixture v0.14.0 que lo cubra; (3) la privacidad es heurística y se declara así; (4) el fixture de Data Card v1 se genera con el código del tag (`git archive v0.14.0` en un directorio fuera del repo), nunca a mano, y se lee con el lector v0.15; (5) `--fail-on-failure` opt-in en vez de cambiar el exit code por defecto, igual que `--fail-on-regression` de C1; (6) si un hueco exigiera modificar un schema persistido, se reclasifica como ACCEPTED LIMITATION en vez de romper compatibilidad.

## Target (condicional — feature_engineering, modeling)

## Features permitidas/prohibidas (condicional — feature_engineering)

## Estrategia de split/validación (condicional — holdout involucrado, modeling, evaluation)

## Leakage risks (condicional — feature_engineering, data_preparation, modeling)
<!-- riesgos considerados por quien propone, incluida la clase "foto sin fecha" de CLAUDE.md;
complementa, no reemplaza, la revisión independiente de data-science-reviewer -->

## Reproducibilidad (opcional — solo si se desvía del default: RANDOM_STATE fijo, .venv)

## Alternativas descartadas
- Firmar evidencia/proposals (PKI): fuera de alcance, D5.
- Cambiar a exit 1 por defecto cuando todo `ok=False`: breaking.
- Escribir el fixture de Data Card a mano: el hash interno ata el contenido; debe generarlo el código del tag.

## Riesgos
- Falsos positivos del barrido de privacidad en docs históricos: lista blanca explícita y mínima, justificada por patrón.
- Tests de symlink se saltan sin privilegios en Windows: el skip se reporta explícitamente; no cuenta como cobertura demostrada si se salta.
- Memoria: correr suites por lotes serial (P=1).

## Aprobación humana
<!-- El registro de aprobación (usuario, fecha, alcance, versión de artefactos, cita) es único
por cambio y vive en la sección "Aprobación" de proposal.md — no se duplica acá. -->

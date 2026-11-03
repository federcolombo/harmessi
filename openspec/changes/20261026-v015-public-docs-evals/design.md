# Diseño — 20261026-v015-public-docs-evals

## Decisión metodológica/técnica
Cambio de documentación con un test de consistencia. Principios: (1) los docs se derivan del código (parsers argparse, JSON de suite, workflow de CI) y un test fija las coincidencias verificables; (2) ninguna afirmación sin observación: CI remoto = pending observation, baseline numérico = no publicado; (3) `.gitattributes` acotado a rutas byte-exact para no renormalizar el resto del repo; (4) editar el template de `verificador.md` cambia hashes managed: el baseline se gestiona una sola vez en C7; (5) el barrido de privacidad de C5 ya cubre `docs/**` y detecta fugas en lo nuevo.

## Target (condicional — feature_engineering, modeling)

## Features permitidas/prohibidas (condicional — feature_engineering)

## Estrategia de split/validación (condicional — holdout involucrado, modeling, evaluation)

## Leakage risks (condicional — feature_engineering, data_preparation, modeling)
<!-- riesgos considerados por quien propone, incluida la clase "foto sin fecha" de CLAUDE.md;
complementa, no reemplaza, la revisión independiente de data-science-reviewer -->

## Reproducibilidad (opcional — solo si se desvía del default: RANDOM_STATE fijo, .venv)

## Alternativas descartadas
- Publicar baseline medido con una sola muestra: sobre-afirmación.
- Instalar Doctor en proyectos instalados: cambia manifest/baseline, fuera de alcance.
- `* text=auto eol=lf` global: renormaliza todo el repo; riesgo innecesario.

## Riesgos
- Docs que divergen del código: mitigado por el test de consistencia y por derivar comandos de los parsers.
- `.gitattributes` no corrige fixtures ya commiteados con CRLF: se verifica con `git ls-files --eol` que el índice esté en LF.
- Editar el template de verificador cambia hashes managed: se recoge en C7.

## Aprobación humana
<!-- El registro de aprobación (usuario, fecha, alcance, versión de artefactos, cita) es único
por cambio y vive en la sección "Aprobación" de proposal.md — no se duplica acá. -->

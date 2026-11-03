# Diseño — 20261026-v015-release-hardening

## Decisión metodológica/técnica
Release sin features: solo versión, baseline, notas y evidencia. La conclusión de readiness se deriva de la matriz, no se declara. Las brechas de proceso (C4-C6 en `en_verificacion`) y de observación (CI remoto, Windows único host) se listan como gaps.

## Target (condicional — feature_engineering, modeling)

## Features permitidas/prohibidas (condicional — feature_engineering)

## Estrategia de split/validación (condicional — holdout involucrado, modeling, evaluation)

## Leakage risks (condicional — feature_engineering, data_preparation, modeling)
<!-- riesgos considerados por quien propone, incluida la clase "foto sin fecha" de CLAUDE.md;
complementa, no reemplaza, la revisión independiente de data-science-reviewer -->

## Reproducibilidad (opcional — solo si se desvía del default: RANDOM_STATE fijo, .venv)

## Alternativas descartadas
- Forzar el cierre SDD de C4-C6 editando control.json: falsea el registro.
- Retrasar el release hasta observar CI remoto: no es observable antes del push.

## Riesgos
- Regresión larga y con presión de memoria: serial P=1 con ledger resumible, en background.
- Cambiar hashes managed sin querer: se compara el diff del baseline.

## Aprobación humana
<!-- El registro de aprobación (usuario, fecha, alcance, versión de artefactos, cita) es único
por cambio y vive en la sección "Aprobación" de proposal.md — no se duplica acá. -->

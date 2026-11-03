# Spec — 20261026-v015-public-docs-evals

## Requisitos
- R1: `.gitattributes` fija `eol=lf` para `tools/tests/fixtures/compat/**`, `tools/datacontracts/tests/parity/golden_*.json` y `tools/ds_init/profiles/**/templates/**`, sin regla global.
- R2: existen `docs/{installation,concepts,cli-reference,evaluation,security-and-trust,release-process}.md`, cada uno derivado del código/estado real (rutas y comandos existentes), con límites explícitos y sin afirmar lo no observado.
- R3: `docs/evaluation.md` declara suite_id, suite_version, suite_hash y los case_ids reales, el formato de resultado, los verdicts de compare y los límites; declara que no hay baseline numérico publicado y por qué.
- R4: README enlaza los docs nuevos y documenta `python -m tools.reporting`; ARCHITECTURE §4/§4.1 distingue resuelto de vigente.
- R5: `verificador.md` (checkout y template) documenta `SKILL-TRAZA-SECCION-DUPLICADA`.
- R6: `docs/installation.md` documenta que Doctor corre desde un checkout con `--destino` y por qué no existe en el proyecto instalado.
- R7: `docs/release-process.md` es un runbook ejecutable paso a paso (bump, regresión, fixtures, Doctor, baseline, tag anotado, push, CI remoto, GitHub Release manual) y marca qué se observa y qué queda pendiente.
- R8: `tools/tests/test_public_docs.py` verifica lo anterior de forma determinista.

## Criterios de aceptación
- [ ] B-26..B-30 y B-34 cerrados o reclasificados en la matriz con evidencia y límites.
- [ ] `test_public_docs.py`, `test_skill_methodology.py`, `test_skill_contract.py` y `test_privacy_sweep.py` verdes (el barrido ahora cubre `docs/**`).
- [ ] Sin rutas personales/emails; sin comandos ni flags inventados (cada comando citado existe en el parser).
- [ ] Ninguna afirmación de CI remoto, baseline numérico ni soporte multi-provider no observados.
<!-- checklist o Given/When/Then, verificables -->

## Unidad de análisis / grain (condicional — data_understanding, feature_engineering, modeling)
<!-- qué representa cada fila del dataset sobre el que se trabaja -->

## Cutoff / information boundary (condicional — feature_engineering, data_preparation, modeling)
<!-- fecha de corte y qué información es anterior/posterior a ella; base del chequeo anti-leakage -->

## Baseline (condicional — modeling)
<!-- modelo/heurística de referencia y su métrica, contra la que se compara todo lo nuevo -->

## Métrica primaria (condicional — modeling, evaluation)

## Métricas secundarias (opcional)

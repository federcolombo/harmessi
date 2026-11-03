# Spec — 20261026-v015-release-hardening

## Requisitos
- R1: `HARNESS_VERSION == "0.15.0"` coherente con `CITATION.cff`, `.ds_init/control.json` y las notas `docs/releases/v0.15.0.md`; README enlaza las notas.
- R2: el baseline se regenera una sola vez y su diff contra HEAD solo contiene harness_version y hashes de archivos modificados en v0.15.
- R3: la matriz de readiness cubre los 14 criterios literales de `docs/roadmap/v1.0.md` con evidencia verificable y límites; conclusión explícita.
- R4: evidencia en `verification.md`: regresión serial completa (n módulos, pasados, skipped, fallos), install limpio, upgrade idempotente, Doctor (0 ERROR), privacidad.
- R5: tag anotado `Harmessi v0.15.0` sobre main tras merge; push; CI remoto «pending observation».

## Criterios de aceptación
- [ ] Regresión completa serial sin fallos (o fallos explicados y resueltos), con ledger.
- [ ] Doctor 0 ERROR.
- [ ] Instalación limpia y upgrade desde v0.14.0 verdes e idempotentes.
- [ ] Matriz de readiness sin afirmaciones no observadas.
<!-- checklist o Given/When/Then, verificables -->

## Unidad de análisis / grain (condicional — data_understanding, feature_engineering, modeling)
<!-- qué representa cada fila del dataset sobre el que se trabaja -->

## Cutoff / information boundary (condicional — feature_engineering, data_preparation, modeling)
<!-- fecha de corte y qué información es anterior/posterior a ella; base del chequeo anti-leakage -->

## Baseline (condicional — modeling)
<!-- modelo/heurística de referencia y su métrica, contra la que se compara todo lo nuevo -->

## Métrica primaria (condicional — modeling, evaluation)

## Métricas secundarias (opcional)

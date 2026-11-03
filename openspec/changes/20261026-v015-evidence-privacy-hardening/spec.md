# Spec — 20261026-v015-evidence-privacy-hardening

## Requisitos
- R1: existe un test determinista de barrido de privacidad con patrones declarados y falla ante un artefacto publicable con ruta personal, email o secreto de ejemplo inyectado (test positivo y negativo).
- R2: cada eslabón de la cadena improve rechaza manipulación (test por eslabón); el hueco restante se documenta.
- R3: el gate de promoción respeta `scope_hash`/enmiendas y no escribe el Decision Ledger.
- R4: lesson como symlink/junction se rechaza (test, skip explícito sin privilegios); GLOSSARY ausente degrada a `privacidad_no_superada`.
- R5: `run_id` reservado de Windows, `result.json` corrupto, bloque de suite incompleto y caso v0 como suite fallan con error claro, sin traceback; `--fail-on-failure` opt-in; default sin cambio.
- R6: fixture Data Card v1 real del tag v0.14.0 con MANIFEST (sha256, tag_origen) y test de lectura con el lector v0.15.

## Criterios de aceptación
- [ ] B-20..B-25 cerrados o reclasificados en la matriz con evidencia (tests) y límites explícitos.
- [ ] Suites afectadas verdes (harmessi_bench, harmessi_improve, cards, tests nuevos), corridas por lotes, sin repetir suites verdes sin causa.
- [ ] Ningún cambio de exit code o schema por defecto sin retrocompatibilidad con fixtures v0.14.0.
- [ ] Sin rutas personales ni emails reales en lo que se agrega (fixtures con ids/paths ficticios).
<!-- checklist o Given/When/Then, verificables -->

## Unidad de análisis / grain (condicional — data_understanding, feature_engineering, modeling)
<!-- qué representa cada fila del dataset sobre el que se trabaja -->

## Cutoff / information boundary (condicional — feature_engineering, data_preparation, modeling)
<!-- fecha de corte y qué información es anterior/posterior a ella; base del chequeo anti-leakage -->

## Baseline (condicional — modeling)
<!-- modelo/heurística de referencia y su métrica, contra la que se compara todo lo nuevo -->

## Métrica primaria (condicional — modeling, evaluation)

## Métricas secundarias (opcional)

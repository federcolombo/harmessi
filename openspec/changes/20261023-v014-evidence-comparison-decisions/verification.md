# Verificación — 20261023-v014-evidence-comparison-decisions

## Resumen
`decision.py`: decisión recomputada desde `result.json` y la política congelada del probe, veredicto vía `compare_runs`, `decision.json` con hash, único camino a `evaluated/promotable/rejected/inconclusive` y `verificar_promotable`.

## Evidencia obtenida
- Suite de `tools/harmessi_improve/tests`: 174 tests; 172 OK en la corrida completa y los 2 restantes (defectos de test) corregidos y verificados junto con `TestResume`, `test_policy`, neutralidad, arquitectura y completitud del manifest (46 OK).
- Reviewer (1 ciclo): 0 BLOCKER, 4 HIGH, 3 MED, 2 LOW. Corregidos: cherry-picking (criterios congelados por candidate, probe nuevo exige decisión previa, solo se aplica el probe más reciente); muestra mínima (`min_scenarios=3`); outcome re-derivado de los `result.json` (un `probe.json` editado no cambia el veredicto); desempate solo por `mean_score` determinista con `min_delta>0`; recomputo de `identity_hash`, igualdad de target/seed y manifest candidate == `sustituir_superficie`; parseo de los mismos bytes hasheados y transiciones bajo un solo lock; inestables del candidate cuentan como regresión.

## Limitaciones
Procedencia no criptográfica: la consistencia interna de `.harmessi/improvement` y `.harmessi/evals` no prueba quién escribió los archivos (el roadmap no promete identidad criptográfica; `.harmessi/` es raíz Protected). Un probe reanudable con decisión ya registrada no tiene camino de regeneración. `duration_s` queda fuera de los desempates por no ser determinista; tokens/retries/STOP no se soportan.

## Divergencias respecto del SDD
Más estricto que el spec: `secondary` solo admite `mean_score`; `candidate_failure` mapea a `baseline_better`/`rejected`; se agregan `min_scenarios` y reglas de congelamiento por candidate.

## Resultado final
Change 3 cerrado; R1–R11 verificados por tests.

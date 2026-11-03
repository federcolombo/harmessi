# Verificación — 20261023-v014-probe-execution

## Resumen
Probe: política congelada (`policy.py`), `GuidanceAdapter`, ejecución baseline/candidate con el runner, manifest y `save_run` de v0.13 (`probe.py`) y `runmanifest.sustituir_superficie`.

## Evidencia obtenida
- `python -m unittest discover -s tools/harmessi_improve/tests -t .`: 126 tests OK (4 skips: symlinks no disponibles).
- `test_runmanifest_sustituir`, `test_v014_improve_neutrality`, `test_architecture_boundaries`: 29 OK.
- Reviewer (1 ciclo): 0 BLOCKER, 3 HIGH, 3 MED, 6 LOW. Corregidos: TOCTOU de la guía baseline y fijación del `identity_hash` de preflight por run (H1); resume solo de probes interrumpidos, sin reabrir `completed` ni esquivar `max_probe_cycles` (H2); identidad/sha de repeticiones reutilizadas verificadas en resume (H3); lock por probe_id con creación `O_EXCL` (M1); tope de tamaño de guía (M2); reintento confirmatorio antes de atribuir un fallo a un lado (M3); seed en resume, symlinks en evals, OverflowError en política, R11 por nombre importado.
- Un test dio un bug real durante la corrección (múltiples reintentos agotaban el budget del otro lado): ahora máximo 1 reintento confirmatorio por corrida.

## Limitaciones
Dos resumes simultáneos de un mismo probe `running` no se bloquean entre sí durante la ejecución (el lock cubre la sección crítica). R10: además de `probes/` y `evals/`, el probe escribe `budget_state.json` y `.lock` bajo `.harmessi/improvement/`. Un probe que cae entre el consumo de budget y la escritura de `probe.json` no es recuperable (budget perdido, documentado).

## Divergencias respecto del SDD
Resume solo para probes `running` o `inconclusive` por wall_clock/identidad (más estricto que R9). Clasificación de fallos con reintento confirmatorio (más conservadora que R7).

## Resultado final
Change 2 cerrado; R1–R11 verificados por tests.

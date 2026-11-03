# Tareas — 20261007-ds-profile-bounded-memory

estado: cerrada

## Invocaciones planificadas
- Lead implementa directamente (cambio acotado a `tools/ds_profile/`); un solo editor, sin writers paralelos.
- Reviewer (`data-science-reviewer`): máx. 2 ciclos. Ejecución: `ds_guard exec` con aprobaciones por `ds_guard exec approve`.

## Tareas
- [ ] T0 — Aprobación del SDD por hash (autorización humana anticipada).
- [ ] T1 — `sampling.py`: estimación, `decidir_plan`, tamaño de muestra, errores.
- [ ] T2 — `column_stats.py`: acumuladores O(1) y dtype/flags derivados.
- [ ] T3 — `report.py`/`io_readers.py`/`cli.py`: plan previo, digests, metadata, batch_size, fail-safe exit 4.
- [ ] T4 — Tests dirigidos, benchmark manual, docs.
- [ ] T5 — Revisión, regresión acotada, verification.md, gate, cierre, commit local.

## Dependencias
Corrective B cerrado. Habilita Change 5.

## Próximo paso exacto
Aprobar el SDD por hash.

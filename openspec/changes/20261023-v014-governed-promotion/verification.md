# Verificación — 20261023-v014-governed-promotion

## Resumen
`promotion.py`: propuesta de promoción (diff + evidencia + hashes), gate fail-closed y aplicación gobernada solo dentro de un Change normal con aprobaciones T1.

## Evidencia obtenida
- `test_promotion` + `test_v014_improve_neutrality`: 45 tests OK (1 skip: symlinks no disponibles).
- Reviewer (1 ciclo): 0 BLOCKER, 0 HIGH, 3 MED, 5 LOW. Corregidos: T1 canónico (`approval_channel=console_confirmed` y `channel_version=console/v1`, igual que `tools/cards/approvals.py`); write-ahead de `applied.json` (`pending`→`applied`), lectura única de `content.md`, re-verificación de `base_hash` antes de reemplazar y recuperación idempotente; diff fiel a los bytes (sin normalizar EOL, aviso de newline final, diff vacío rechazado); cita anclada `proposal_hash: <hash>` fuera de comentarios, `change_id` ligado a `control.json`, `sys.path.append`.
- La propuesta documenta que Evaluation ≠ verificación de release: el Change normal sigue exigiendo tests, reviewer y aprobaciones.

## Limitaciones
No se probó el scope anclado con `scope_hash` ni enmiendas; el estado `en_implementacion` sale de `tasks.md`. Sin Decision Ledger automático: solo `ledger_text` sugerido. La actualización del managed baseline queda para el release/Change.

## Divergencias respecto del SDD
Gate más estricto que R3 (`channel_version`, cita anclada, `control.change_id`). `applied.json` ahora tiene estados `pending|applied`.

## Resultado final
Change 4 cerrado; R1–R7 verificados por tests.

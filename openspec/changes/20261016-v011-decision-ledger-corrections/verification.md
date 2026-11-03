# Verificación — 20261016-v011-decision-ledger-corrections

## Resumen
Change 2 de v0.11: `decision correct` (append-only) y `decision verify` (integridad), con escritura que preserva bytes previos y cadena `prev_hash` en entradas nuevas. SDD aprobado por hash (T0/declared).

## Evidencia obtenida
- Tests (foreground, serial): `test_decision_correct` 28 OK + `test_decision` 24 OK (52 en conjunto); `test_ds_guard_usuario_guard` 7 OK; `test_manifest_dsguard_parity` 11 OK; `ds_init.test_integracion_instalacion` 1 OK (instalador sin placeholders `{{}}`).
- `ds_guard decision verify` sobre el ledger real del repo: «Sin hallazgos» (el ledger legacy no se modificó).
- Reviewer ciclo 1: 0 altos, 7 medios, 8 bajos. Aplicados: #1–#9, #11, #12 y el bug de CRLF del test. Omitidos con motivo: #10 (referencias hacia adelante), #13 (errores de E/S sin traceback manejado), #14 (huecos de cobertura menores). No hubo ciclo 2 (sin HIGH ni blockers).
- Primer fallo de test tras los fixes: helper de test sin `mkdir`; corregido y re-corrido.

## Implementación
`decision.py` (acción `corregir`, `verificar_integridad`, append sin reserializar, `prev_hash`, `schema_version` 2, efectivo/correcciones), `ds_guard.py` (`decision correct|verify`, list/show con efectivo), `decision-ledger.md` + plantilla, tests nuevos.

## Limitaciones honestas (documentadas)
Tamper-evidence contra edición ingenua, no autenticidad: el prefijo legacy salvo su última línea no queda protegido; borrar la cola no se detecta; escrituras read-modify-write sin lock (concurrencia puede perder una entrada); `usuario` es declarado (T0). Un ledger v0.10 inconsistente queda bloqueado para escribir hasta corregirlo a mano (sin auto-reparación). El enum de tipos no cambia.

## Divergencias respecto del SDD
Se agregó `DECISION-CORRECCION-SIN-CAMBIO` (rechazo de correcciones no-op) y filtro `--change-id` por valor efectivo, ambos derivados del reviewer; `verificador.md` no documenta el código nuevo (pendiente menor).

## Pendientes
Change 3. Regresión completa en Change 6.

## Resultado final
Change 2 verificado con tests dirigidos y afectados; sin hallazgos abiertos.

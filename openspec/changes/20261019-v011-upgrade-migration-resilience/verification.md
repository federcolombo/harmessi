# Verificación — 20261019-v011-upgrade-migration-resilience

## Resumen
Change 5 de v0.11: `ds_init upgrade` y `ds_init recover` transaccionales (dry-run por defecto), journal persistente con fases, lock de archivo, `control.json` atómico, test de completitud del manifest, checks de Doctor (`HARMESSI-VERSION` con remedio, `HARMESSI-MIGRACION`), docs. SDD aprobado por hash (T0/declared).

## Evidencia obtenida
Tests en foreground, serial, por módulo (todos OK):
- Nuevos: `test_manifest_completitud` 4, `test_manifest_parity_inversa` 3, `test_control_atomico` 4, `test_lock` 6, `test_journal_persistente` 4, `test_upgrade` 11, `test_recover` 9, `test_recover_robustez` 9, `test_upgrade_preservacion` 2, `harmessi.test_doctor_migracion` 11.
- Afectados: `test_writer_staging` 12, `test_preflight` 9, `test_cli` 35, `test_sync_baseline` 13, `test_control_file` 22, `test_integracion_instalacion` 1, `harmessi.test_doctor` 97 (corrido tras T1d), `test_doctor_managed_hash` 12, `test_doctor_skill_contract` 9, `tests.test_manifest_dsguard_parity` 11, `test_skill_methodology` 52, `test_architecture_boundaries` 16.
- Reviewer ciclo 1: 0 altos, 5 medios (M1 fase `preparado` con replace ya hecho; M2 TOCTOU en recover; M3 ediciones del usuario tras la interrupción; M4 validación de rutas del journal; M5 journal no atómico), 8 bajos. Resueltos M1–M5, B1 (doc), B2, B4 y B7. No resueltos/omitidos con motivo: B3 (inferencia de `crear` sin marca sin test), B5 (FECHA_INSTALACION latente), B6 (cobertura de settings.json reformateado), B8 parcial. No hubo ciclo 2 (sin HIGH).
- El primer test estricto de imports (B7a) reveló imports perezosos opcionales por diseño (`ds_guard._ruta_plantilla_guardrails`, `dsguard/status.py`); se agregaron a una allowlist explícita y justificada.
- Incidente corregido: tests simulaban "v0.10" con la versión actual (`0.10.0`); se usó `0.0.1-previa`.

## Garantías y límites honestos
Rollback al estado previo, no roll-forward; lock cooperativo (un kill puede dejar `.ds_init/lock`, se borra a mano; sin detección de pid); `recover` aborta ante ediciones del usuario salvo `--forzar` (con copia `.recover-bak`); `upgrade` no recrea managed borrado a mano ni adopta drift; sin downgrade ni migración de datos; Doctor corre desde el checkout; el fixture «v0.10» de los tests es sintético: el upgrade desde el tag público v0.10.0 real se ejercita en el dogfooding del Change 6.

## Divergencias respecto del SDD
Se agregó `recover --forzar` y `sha256_nuevo` en el journal (derivados del reviewer); `check_manifest_parity.py` ganó la dirección inversa (R1).

## Pendientes
`test_cards_capabilities` y el resto de la regresión completa quedan para Change 6 (batches seriales). Change 6.

## Resultado final
Change 5 verificado con tests dirigidos y afectados; sin hallazgos abiertos altos.

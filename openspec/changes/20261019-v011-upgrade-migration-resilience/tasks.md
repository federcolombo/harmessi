# Tareas — 20261019-v011-upgrade-migration-resilience

estado: en_implementacion

## Invocaciones planificadas
- Lead coordina/valida; writer único `python-data-engineer` (serial, varias invocaciones T1a–T1e); reviewer 1 ciclo (segundo solo si blocker/HIGH).

## Ownership de writers
<!-- solo si se lanzan 2+ instancias writer en paralelo; declarar ANTES de lanzar. -->

## Historial de ownership
<!-- fecha — instancia — ruta — motivo (cambios de ownership hechos ANTES de que el writer edite) -->

## Skills cargados
<!-- - <skill> — <tarea> — <motivo>  (solo si una skill componible afecta el Change) -->

## Tareas
- [x] T1a — R1 test de completitud del manifest + R5 escritura atómica de control.json y backup en migrate-hashes
- [x] T1b — R2/R3/R7 `upgrade` (plan, transacción con journal persistente, lock)
- [x] T1c — R4 `recover` + detección por fase
- [x] T1d — R6 Doctor
- [x] T1e — R8/R9/R10 fixtures v0.10, E2E, inyección de fallos, byte-identidad, docs
- [ ] T2 — Reviewer (1 ciclo) y fixes
- [ ] T3 — verification, cierre, commit

## Dependencias

## Próximo paso exacto
<!-- obligatorio si estado: pausada_bloqueada -->

## PUNTO DE CORTE (2026-10-19, fin de jornada)
Estado: Change 5 en `en_implementacion`. T1a–T1e hechos y commiteados (WIP). Reviewer ciclo 1 hecho (0 altos, 5 medios M1–M5, bajos); los fixes M1–M5, B1, B2, B4, B7 ya están escritos por el writer (SIN commitear al momento del corte salvo que el commit de corte los incluya).
Verificado verde tras los fixes: test_manifest_parity_inversa 3, test_journal_persistente 4, test_recover_robustez 9.
FALLA ABIERTA (única): `tools.ds_init.tests.test_manifest_completitud.test_ningun_modulo_instalado_importa_solo_checkout` — `tools/ds_guard.py` (6 pares) importa `tools/ds_init/*` (__init__, manifest, ...). Triage: probablemente imports perezosos de comandos checkout-only (p. ej. `guardrails readopt` exige el clone de Harmessi). Decidir: (a) si son lazy y por diseño solo-checkout → allowlist explícita y justificada de esos pares en el test (documentar), o (b) si un comando instalado los necesita → agregar al MANIFEST. No es regresión de producto, es el nuevo test (B7a) siendo estricto.
PENDIENTE de correr (serial, foreground, uno por uno; el último lote puede exceder 10 min: dividir): tools.ds_init.tests.{test_recover (≈250 s), test_upgrade (≈210 s), test_upgrade_preservacion (≈75 s), test_writer_staging (≈95 s), test_preflight, test_control_atomico, test_lock, test_cli (puede tardar), test_cards_capabilities (≈360 s), test_integracion_instalacion}, tools.harmessi.tests.{test_doctor_migracion (≈150 s), test_doctor_skill_contract}, tools.tests.{test_manifest_dsguard_parity, test_skill_methodology, test_architecture_boundaries}. NO correr suites amplias ni en background/paralelo (OOM previo).
Luego: arreglar lo que falle (vía writer `python-data-engineer`, que NO tiene ejecución; 12 turnos → SendMessage para continuar), 2º reviewer solo si hay HIGH/blocker, `verification.md` (secciones `## Evidencia obtenida` y `## Resultado final`), `en_verificacion` → `cerrada` con sesión activa (la sesión s1 de este Change se cerró como pausada: abrir con `session start --change-id 20261019-v011-upgrade-migration-resilience --minutos 480 --retomar`), `session close --estado completada`, commit. Después: Change 6.

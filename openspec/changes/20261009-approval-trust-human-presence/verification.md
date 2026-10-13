# Verificación — 20261009-approval-trust-human-presence

## Resumen
Change 2 de v0.10 «Approval Trust / T1 Human-Presence Semantics». SDD aprobado por hash el 2026-10-13 por Federico Colombo bajo el trust model T0 (proposal `d19cc3b2edfc1c715bda739de0f1a2d64edc74dcfdc0418d3a89011eb741adc6`, spec `1347471f0dd44250f38b4cde5340eba7befedc4fb2667507770b3f37f7eb52f2`, design `d46d0ce1d52570ab11564ef5d1a84031395fc7c683946d7581f38c787b5cc473`) con la decisión B: T1 = `console_confirmed` (`console/v1`); descartado el nombre `tty_confirmed`; sin T2; T3 fuera. Implementación con 4 instancias de `python-data-engineer` con ownership disjunto (A: `tools/dsguard/human_presence.py` + tests; B: `tools/ds_guard.py` + tests; C: `tools/cards/approvals.py` + tests; D: boundaries/docs); el Lead no escribió código.

## Qué entrega
- Primitive `tools/dsguard/human_presence.py` (solo stdlib, neutral): challenge efímero con `secrets`, single-use, ligado a change/artefacto/hash/acción, sanitizado en pantalla, con timeout. Lee solo del canal de control (Windows: `GetConsoleWindow() != 0` + `CONIN$`/`CONOUT$` con `ReadConsoleInputW`; POSIX: `/dev/tty` + `tcgetpgrp`); nunca `sys.stdin`. Fail-closed; `KeyboardInterrupt` y excepciones dan `ok=False`.
- `--channel {declared,console_confirmed}` en `approve` y `exec approve` con helper único de registro: T0 conserva la forma histórica; T1 agrega `approval_channel`, `confirmed_at` y `channel_version`. Confirmaciones todo-o-nada; concurrencia optimista de `control.json` que reduce la ventana de pérdida de actualización; `--channel` tras `--` se rechaza.
- `tools/cards/approvals.py` expone `approval_channel`/`trust_tier` solo en estado `verified` (canal desconocido nunca T1). `ApprovalRef` y `HumanAttestation` sin cambios.
- El Change 0 congelado conserva el nombre `tty_confirmed` en su SDD (histórico; supersedido por la nota del roadmap).

## Evidencia obtenida
- Hallazgos del audit: `isatty()` da True en el runtime del agente (stdin es NUL; `GetConsoleWindow() == 0`); la consola del agente es privada; `CONIN$` se abre con lectura/escritura. La inyección sintética de consola NO se ejercitó (denegada por el clasificador de permisos, no se rodeó): «not empirically exercised; explicitly outside T1 guarantee».
- Tests dirigidos: 136 OK (5 skipped, contratos POSIX en host Windows), incluidos los 2 E2E de subproceso real con stdin por pipe.
- Regresión relevante posterior a todos los fixes: 228 OK (6 skipped) en approvals SDD, exec approve, ApprovalRef/Cards approvals, checkpoints `@approved`, autonomy_sdd, checkpoints cli, exec, boundaries y smoke de roadmap. Además 153 OK en `tools/autonomy/tests`.
- Sin regresión completa, sin `ds_profile`, sin hashing managed.
- Prueba negativa del agente (repo temporal equivalente): desde la herramienta Bash con `ABC123` por stdin, `exit=2` y 0 aprobaciones; desde la herramienta PowerShell, `exit=2` y 0 aprobaciones. Mensaje: «no hay consola de control soportada: el proceso no tiene ventana de consola real (GetConsoleWindow() == 0)…».
- ACEPTACIÓN MANUAL HUMANA (T6), ejecutada por el usuario en su terminal real de Windows el 2026-10-13 sobre un Change temporal descartable fuera del repo real: quedó 1 aprobación con `alcance_aprobado="aceptacion manual"`, `cita="prueba T1 descartable"`, las claves históricas más `approval_channel="console_confirmed"`, `confirmed_at` y `channel_version="console/v1"`, y nada más (privacidad OK). El usuario además ejecutó un comando vía `!` (con `alcance="x"`) y no se registró ninguna aprobación nueva: el `!` no obtuvo T1 (conclusión por el estado resultante; el Lead no vio la salida de ese comando).
- Reviewer `data-science-reviewer`, 2/2 ciclos:
  - Ciclo 1: 0 blockers; 2 altos (test E2E que siempre se saltaba por un `is not None` sobre una tupla; pérdida de actualización de `control.json` durante la espera del prompt); medios (orden de `registrado_utc`, spoofing del texto del challenge por caracteres de control/ANSI, sobre-promesa y huecos en docs, el tier es un registro no una prueba). Todo corregido. El reviewer llegó a su límite de 16 turnos sin informe y hubo que reanudarlo.
  - Ciclo 2: 0 blockers/altos; 1 medio (respuesta con surrogates sueltos lanzaba excepción no capturada; corregido); bajos: ventana TOCTOU residual documentada, `exec approve` muestra artefacto + hash abreviado y no el argv real (límite documentado), `--channel` tras `--` tragado (ahora rechazado), notas de consola heredada y POSIX no verificado documentadas.
  - Sin hallazgos abiertos.

## Fingerprint de dataset/artefacto
No aplica (sin datasets).

## Diferencias contra la spec
Ninguna registrada.

## Limitaciones
- T1 no prueba identidad, autoría ni no-repudio.
- No resiste input de consola sintetizado deliberadamente (pty/`WriteConsoleInputW`/nueva consola), admin/root, malware ni un runtime que herede la consola del humano.
- El tier es un registro editable: `control.json` no está autenticado ni protegido por pathguard.
- POSIX no verificado en un runtime real (solo tests con fakes).
- No se identificó qué emulador de terminal usó el usuario (ConPTY/Windows Terminal/conhost).
- `decision`/`remediation` siguen T0.
- Ventana TOCTOU residual en la escritura de `control.json`.
- Sin regresión completa.

## Pendientes derivados
- Change 3 será el primer consumidor obligatorio de T1.
- Change 4: evidencia de turn limits/reanudaciones de reviewers (el reviewer del ciclo 1 llegó a 16 turnos sin informe).
- Verificación POSIX en un runtime real y por emulador de terminal, cuando haya host disponible.
- Cierre y commit local a cargo del Lead.

## Resultado final
Change 2 verificado con las pruebas relevantes indicadas y la aceptación manual humana (T6) ejecutada el 2026-10-13; sin hallazgos abiertos del reviewer.

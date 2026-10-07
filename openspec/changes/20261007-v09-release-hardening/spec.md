# Spec — 20261007-v09-release-hardening

## A. Versión y roadmap (R1–R5)
**R1.** `HARNESS_VERSION`, `CITATION.cff.version` y `.ds_init/control.json.version` valen `0.9.0`; `date-released` = fecha de preparación. Una sola fuente
canónica (`version.py`); sin otras fuentes. Versionados internos independientes (`ds_profile.TOOL_VERSION`, `version_algoritmo`) NO cambian.
**R2.** `.ds_init/control.json` se regenera UNA vez, al final, con el procedimiento conocido (hashes raw sha256 de los archivos managed).
**R3.** `docs/roadmap/v0.9.md` refleja Changes 0–5, correctives, estado final, decisiones congeladas y limitaciones trasladadas, sin borrar historia.
`docs/roadmap/README.md` marca v0.9 lista para publicar (no «publicada» hasta el release humano).
**R4.** `docs/roadmap/v0.10.md` conserva approval-origin authenticity, LF/CRLF, mid-Change scope amendment UX, composable skills, domain-modeling,
one-writer; sin deudas ya resueltas marcadas pendientes.
**R5.** Sin features nuevas: ningún cambio funcional en `tools/**` salvo `version.py`.

## B. Documentación y release notes (R6–R9)
**R6.** README: sección acotada de v0.9 (Data Cards, Model Cards, Model Governance, capabilities opt-in, límites de Responsible AI, `ds_profile` exact→sampled).
**R7.** `docs/releases/v0.9.0.md` — «Harmessi v0.9.0 — Cards & Model Governance»: features, correctives, limitaciones públicas conocidas; sin promesas de
compliance ni menciones de proyectos reales.
**R8.** Lenguaje honesto: Harmessi gobierna evidencia; NO afirma ethical/fair/safe/private/secure/compliant.
**R9.** Las limitaciones públicas se distinguen de la deuda interna.

## C. Privacidad e higiene (R10–R13)
**R10.** Sweep sobre archivos tracked: sin `segmentacion-pc`, nombres de datasets del feedback, rutas personales (`C:\Users\<usuario>`, `/c/Users/<usuario>`), emails
personales ni credenciales (fixtures ficticias de tests permitidas). Se sanitizan los 5 restos hallados.
**R11.** `git ls-files docs/feedback .harmessi` vacío; `.gitignore` incluye `docs/feedback/`; el directorio local no se borra.
**R12.** Smoke de release `tools/tests/test_v09_release_hardening_smoke.py`: coherencia de versión, higiene de tracked, sweep de privacidad (patrones por
concatenación; excluye Changes de release-hardening/remove-personal-email que describen el sweep), dependencias (módulos Cards/governance/pep440/ds_profile solo stdlib
+ `pyarrow` perezoso), roadmap v0.10 con los ítems requeridos y v0.9 con Changes 0–5.
**R13.** `.harmessi/` no es requisito de una instalación nueva (los tests de instalación usan directorios temporales).

## D. Verificación de release (R14–R19)
**R14.** Matriz de instalación A–E: cubierta por `test_cards_capabilities.py` + una corrida real por CLI en directorios temporales (default, `data_cards`,
`model_governance` con `predictive_modeling`, inválido sin escribir, sync sin reactivación implícita).
**R15.** Adopción de proyecto pre-v0.9: sync sin sobrescribir contenido del usuario, sin Cards automáticas, `governance/` project-owned.
**R16.** Cards E2E (Data/Model/Governance: validate→report; complete, stale/mismatch, config inválida) y `report_kind="governance"` aditivo sin habilitar holdout:
tests existentes de `tools/cards` y `tools/reporting`.
**R17.** Inercia de autonomía: Cards/governance/reporting no cambian `STOP_CATALOG`, `approval_mode`, checkpoints de runtime ni permisos autónomos (tests de
neutralidad existentes); Correctives A/B/C revalidados dentro de la regresión global.
**R18.** UNA regresión global final en lotes secuenciales, con totales derivados de los ExecutionRecords, sin doble contar re-runs.
**R19.** Doctor final sin ERROR (WARN solo por `.harmessi/` y `docs/feedback/` untracked); `git diff --check` limpio.
